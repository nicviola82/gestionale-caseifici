# ============================================================
# MODULO: STAMPA MBC
# Compila il foglio "MBC" del template ufficiale RINA
# (templates_dop.xlsx) per una singola giornata di lavorazione.
#
# IMPORTANTE: il foglio MBC e' un documento ufficiale statico.
# Questo script NON modifica la struttura del file (righe,
# colonne, formule esistenti restano intatte) - scrive SOLO i
# valori nelle celle dati, secondo la mappatura concordata.
# ============================================================
import datetime as _dt
import shutil
import openpyxl

import registro_calc

TEMPLATE_PATH = "templates_dop.xlsx"  # percorso del file originale scaricato da GitHub
FOGLIO = "MBC"


# ------------------------------------------------------------
# BLOCCO: LETTURA DATI DA SUPABASE
# Ogni funzione isola una fonte dati, cosi' quando il Registro
# verra' riscritto basta aggiornare le funzioni segnate TODO.
# ------------------------------------------------------------

def get_anagrafica(client, caseificio_id):
    return client.table("caseifici").select("*").eq("id", caseificio_id).single().execute().data


def get_refrigerante_principale(client, caseificio_id):
    righe = (
        client.table("refrigeranti")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .order("codice")
        .limit(1)
        .execute()
        .data
    )
    return righe[0]["codice"] if righe else ""


def get_impostazione(client, caseificio_id, campo, alla_data):
    righe = (
        client.table("impostazioni_registro")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("campo", campo)
        .lte("data_da", str(alla_data))
        .order("data_da", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return righe[0]["valore"] if righe else ""


def get_conferimenti_per_categoria(client, caseificio_id, data_giorno, tipi_conferitore, tipo_latte):
    """Somma kg conferiti nel giorno per una categoria di conferitori (es. allevatori DOP)."""
    conferitori = (
        client.table("conferitori")
        .select("*, conferitori_tipi_latte(tipo_latte)")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .in_("tipo", tipi_conferitore)
        .execute()
        .data
    )
    ids = [
        c["id"] for c in conferitori
        if tipo_latte in [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]
    ]
    if not ids:
        return 0.0, []
    conferimenti = (
        client.table("conferimenti")
        .select("*")
        .in_("conferitore_id", ids)
        .eq("data", str(data_giorno))
        .execute()
        .data
    )
    totale = sum(float(c["kg"] or 0) for c in conferimenti)
    ddt_list = [c["ddt"] for c in conferimenti if c.get("ddt")]
    return totale, ddt_list


def get_conferimenti_caseificio_dop_dettaglio(client, caseificio_id, data_giorno):
    """Conferimenti giornalieri da conferitori tipo 'caseificio' con bufala_dop, UNO PER RIGA
    (non sommati) - servono per D15/D16 (righe gia' presenti nel template, una per ogni
    caseificio DOP da cui si e' acquistato quel giorno, confermato dall'utente)."""
    conferitori = (
        client.table("conferitori")
        .select("*, conferitori_tipi_latte(tipo_latte)")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .eq("tipo", "caseificio")
        .execute()
        .data
    )
    conferitori = [
        c for c in conferitori
        if "bufala_dop" in [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]
    ]
    righe = []
    for c in conferitori:
        rec = (
            client.table("conferimenti")
            .select("*")
            .eq("conferitore_id", c["id"])
            .eq("data", str(data_giorno))
            .execute()
            .data
        )
        if rec and float(rec[0].get("kg") or 0) > 0:
            righe.append({"kg": float(rec[0]["kg"]), "ddt": rec[0].get("ddt") or ""})
    return righe


def get_produzione_giorno(client, caseificio_id, data_giorno, contiene_nel_nome):
    """Somma kg_totale del giorno per prodotti il cui nome contiene una parola chiave (case-insensitive)."""
    prodotti = (
        client.table("prodotti")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .execute()
        .data
    )
    match = [p for p in prodotti if contiene_nel_nome.lower() in p["nome"].lower()]
    totale = 0.0
    for p in match:
        rec = (
            client.table("produzioni")
            .select("*")
            .eq("prodotto_id", p["id"])
            .eq("data", str(data_giorno))
            .execute()
            .data
        )
        if rec:
            totale += float(rec[0].get("kg_totale") or 0)
    return totale


# Ricollegate al vero Registro (registro_calc.py) - stessa logica usata dalla pagina Registro.
def get_registro_giacenza_apertura(client, caseificio_id, data_giorno):
    return registro_calc.giacenza_apertura(client, caseificio_id, "bufala_dop", data_giorno)


def get_registro_trasformato_dop(client, caseificio_id, data_giorno):
    return registro_calc.trasformato(client, caseificio_id, "bufala_dop", data_giorno)


def get_registro_extra_dop(client, caseificio_id, data_giorno):
    return registro_calc.extra_dop_consumato(client, caseificio_id, data_giorno)


def get_registro_giacenza_chiusura(client, caseificio_id, data_giorno):
    return registro_calc.giacenza_chiusura(client, caseificio_id, "bufala_dop", data_giorno)


# ------------------------------------------------------------
# BLOCCO: NUMERO SCHEDA (progressivo = giorno dell'anno)
# Confermato con l'utente: 25 febbraio = 56° giorno dell'anno = "56/26M" - il numero e'
# sempre positivo (1-366), MAI negativo. Formato finale: "NNN/AA" + lettera (M per MBC, R per RBC).
# ATTENZIONE: questa funzione e' SOLO per il campo "Scheda N." - il lotto dei prodotti (V10 ecc.)
# e' un'altra cosa, dipende dal tipo di lotto scelto per il prodotto in Prodotti (da rivedere).
# ------------------------------------------------------------
def scheda_n(data_giorno, lettera="M"):
    giorno_anno = data_giorno.timetuple().tm_yday
    anno_breve = data_giorno.strftime("%y")
    return f"{giorno_anno}/{anno_breve}{lettera}"


def numero_scheda(data_giorno):
    # Mantenuta per compatibilita' con la generazione provvisoria del lotto prodotti
    # (in attesa di rifare il lotto secondo il tipo_lotto del prodotto, come richiesto)
    return data_giorno.timetuple().tm_yday


# ------------------------------------------------------------
# BLOCCO: COMPILAZIONE FOGLIO MBC
# ------------------------------------------------------------
def genera_mbc(client, caseificio_id, data_giorno, output_path):
    shutil.copy(TEMPLATE_PATH, output_path)
    wb = openpyxl.load_workbook(output_path)
    ws = wb[FOGLIO]

    anagrafica = get_anagrafica(client, caseificio_id)

    # --- Intestazione ---
    ws["C1"] = anagrafica.get("ragione_sociale", "")
    # ws["T1"] = codice RINA AGRIFOOD -> campo non ancora presente in Anagrafica, lasciato vuoto
    ws["C3"] = scheda_n(data_giorno, lettera="M")
    ws["H3"] = data_giorno.strftime("%d/%m/%Y")

    ws["H5"] = get_impostazione(client, caseificio_id, "ora_ricevimento_latte", data_giorno)
    ws["M5"] = get_impostazione(client, caseificio_id, "ora_inizio_lavorazione", data_giorno)
    ws["U5"] = get_impostazione(client, caseificio_id, "ora_fine_lavorazione", data_giorno)

    # --- Sezione Ricevimento ---
    ws["D10"] = get_registro_giacenza_apertura(client, caseificio_id, data_giorno)  # TODO Registro
    ws["E10"] = get_refrigerante_principale(client, caseificio_id)

    kg_allevamento, _ = get_conferimenti_per_categoria(
        client, caseificio_id, data_giorno, ["allevatore"], "bufala_dop"
    )
    ws["D13"] = kg_allevamento

    kg_raccoglitore, ddt_raccoglitore = get_conferimenti_per_categoria(
        client, caseificio_id, data_giorno, ["intermediario"], "bufala_dop"
    )
    ws["D14"] = kg_raccoglitore
    ws["E14"] = ", ".join(ddt_raccoglitore)

    # D15/D16: latte da caseifici DOP - una riga per ogni caseificio (max 2/giorno, confermato
    # dall'utente che le righe esistono gia' nel template, nessuna modifica di struttura)
    caseifici_dop = get_conferimenti_caseificio_dop_dettaglio(client, caseificio_id, data_giorno)
    if len(caseifici_dop) >= 1:
        ws["D15"] = caseifici_dop[0]["kg"]
        ws["E15"] = caseifici_dop[0]["ddt"]
    if len(caseifici_dop) >= 2:
        ws["D16"] = caseifici_dop[1]["kg"]
        ws["E16"] = caseifici_dop[1]["ddt"]

    # --- Sezione Lavorazione ---
    ws["G10"] = get_impostazione(client, caseificio_id, "temperatura_attivazione", data_giorno)
    ws["G11"] = get_impostazione(client, caseificio_id, "tipo_siero_innesto", data_giorno)
    ws["G12"] = get_impostazione(client, caseificio_id, "caglio_fornitore", data_giorno)
    ws["J12"] = get_impostazione(client, caseificio_id, "caglio_lotto", data_giorno)
    ws["G13"] = get_impostazione(client, caseificio_id, "acidita_primo_siero", data_giorno)  # pH finale
    ws["G14"] = get_impostazione(client, caseificio_id, "temperatura_latte", data_giorno)    # tempo maturazione
    ws["G16"] = 0  # Acidita' Primo Siero: per ora 0, in attesa del foglio Siero
    ws["G22"] = get_impostazione(client, caseificio_id, "cicli_lavorazione", data_giorno)
    ws["K21"] = get_registro_trasformato_dop(client, caseificio_id, data_giorno)  # TODO Registro
    ws["K25"] = get_registro_extra_dop(client, caseificio_id, data_giorno)        # TODO Registro
    ws["K27"] = get_registro_giacenza_chiusura(client, caseificio_id, data_giorno)  # TODO Registro

    # --- Sezione Filatura ---
    ws["M9"] = get_impostazione(client, caseificio_id, "temperatura_acqua_filatura", data_giorno)

    kg_affumicata = get_produzione_giorno(client, caseificio_id, data_giorno, "affumicat")
    if kg_affumicata > 0:
        ws["M21"] = "X"
        ws["M22"] = ""
    else:
        ws["M21"] = ""
        ws["M22"] = "X"

    # --- Sezione Produzioni ---
    # NOTA: intestazioni reali sono R9='Prodotto' (testo), V9='lotto n.', W9='Q.tà (kg)' -
    # la versione precedente scriveva la quantita' in R10 (che vuole il NOME prodotto) e il
    # lotto in W10 (che vuole la quantita'): erano scambiate, corretto qui.
    kg_mozzarella = get_produzione_giorno(client, caseificio_id, data_giorno, "Mozzarella di Bufala Campana DOP")
    ws["R10"] = "Mozzarella di Bufala Campana DOP"
    ws["V10"] = f"{data_giorno.strftime('%Y%m%d')}-{numero_scheda(data_giorno)}"  # lotto
    ws["W10"] = kg_mozzarella  # quantita' kg
    ws["K26"] = ""  # TODO: "ceduto a terzi" - manca ancora una fonte dati (kg latte DOP ceduto quel giorno);
                     # lasciato vuoto invece della formula #REF! originale, in attesa di costruire questa parte

    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    # Esempio d'uso manuale (va richiamato dalla pagina Streamlit "Fogli Stampabili")
    from db import get_client
    client = get_client()
    genera_mbc(client, caseificio_id=1, data_giorno=_dt.date.today(), output_path="MBC_compilato.xlsx")
    print("File generato: MBC_compilato.xlsx")
