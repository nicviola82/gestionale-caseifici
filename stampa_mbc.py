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


# TODO: da ricollegare quando il Registro verra' riscritto (foglio Excel dinamico).
# Per ora ritorna 0 / vuoto: le celle restano compilabili a mano finche' non e' pronto.
def get_registro_giacenza_apertura(client, caseificio_id, data_giorno):
    return 0.0


def get_registro_trasformato_dop(client, caseificio_id, data_giorno):
    return 0.0


def get_registro_extra_dop(client, caseificio_id, data_giorno):
    return 0.0


def get_registro_giacenza_chiusura(client, caseificio_id, data_giorno):
    return 0.0


# ------------------------------------------------------------
# BLOCCO: NUMERO SCHEDA (progressivo = giorno dell'anno)
# Assunzione confermata: usare il giorno dell'anno (1-366).
# Se in futuro serve un contatore diverso, cambiare solo qui.
# ------------------------------------------------------------
def numero_scheda(data_giorno):
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
    ws["C3"] = numero_scheda(data_giorno)
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
    kg_mozzarella = get_produzione_giorno(client, caseificio_id, data_giorno, "Mozzarella di Bufala Campana DOP")
    ws["R10"] = kg_mozzarella
    ws["W10"] = f"{data_giorno.strftime('%Y%m%d')}-{numero_scheda(data_giorno)}"  # lotto

    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    # Esempio d'uso manuale (va richiamato dalla pagina Streamlit "Fogli Stampabili")
    from db import get_client
    client = get_client()
    genera_mbc(client, caseificio_id=1, data_giorno=_dt.date.today(), output_path="MBC_compilato.xlsx")
    print("File generato: MBC_compilato.xlsx")
