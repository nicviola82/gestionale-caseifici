# ============================================================
# MODULO: STAMPA TR
# Compila il foglio "tr" (tabellone giornaliero) del template
# ufficiale (templates_dop.xlsx).
#
# REGOLA DELLE RIGHE DINAMICHE (solo per questo foglio, MBC/RBC
# restano sempre statici):
#   - un blocco/riga esiste se e solo se esiste un CONFERITORE
#     ATTIVO registrato per quella categoria - NON in base al
#     fatto che abbia consegnato qualcosa quel giorno. Un
#     conferitore attivo compare sempre, anche con 0 kg quel
#     giorno.
#   - i blocchi "allevamenti dop" e "caseifici dop" esistono
#     SOLO se il caseificio stesso e' DOP (caseifici.is_dop).
#     Se il caseificio non e' DOP, quei blocchi non vengono
#     nemmeno considerati.
#   - i prodotti finiti elencano SEMPRE tutti i prodotti attivi
#     (tabella Prodotti), anche con quantita' 0 quel giorno.
#
# Le formule originali del template sono quasi tutte #REF! rotte
# (collegate a un workbook che non esiste piu'), quindi qui NON
# proviamo a ripararle: scriviamo valori diretti calcolati in
# Python, comprese le celle di totale.
# ============================================================
import random
import copy
import shutil
import openpyxl

from stampa_mbc import get_registro_giacenza_apertura, TEMPLATE_PATH  # ora collegata al vero Registro

FOGLIO = "tr"

# (nome, riga_inizio, n_righe_template, tipi_conferitore, tipo_latte, richiede_caseificio_dop)
BLOCCHI = [
    ("allevamenti_dop", 12, 17, ["allevatore"], "bufala_dop", True),
    ("caseifici_dop", 29, 4, ["caseificio"], "bufala_dop", True),
    ("caseificio_non_dop", 33, 5, ["caseificio"], "bufala", False),
    ("allevamenti_non_dop", 38, 2, ["allevatore"], "bufala", False),
    ("vaccino", 40, 3, ["allevatore", "caseificio", "intermediario"], "vaccino", False),
    ("semilavorato_bufala", 43, 2, ["allevatore", "caseificio", "intermediario"], "semilavorato_bufala", False),
    ("semilavorato_vaccino", 45, 2, ["allevatore", "caseificio", "intermediario"], "semilavorato_vaccino", False),
]


def _acidita_random():
    return f"3,{random.randint(5, 9)} °SH/50ml"


def _temperatura_random():
    return f" T°C {random.randint(3, 5)},{random.randint(1, 9)}"


def _caseificio_is_dop(client, caseificio_id):
    c = client.table("caseifici").select("is_dop").eq("id", caseificio_id).single().execute().data
    return bool(c and c.get("is_dop"))


def _conferitori_attivi_categoria(client, caseificio_id, tipi_conferitore, tipo_latte):
    """Ritorna TUTTI i conferitori attivi di quella categoria (indipendentemente da cosa
    hanno conferito quel giorno) - determina se il blocco esiste."""
    conferitori = (
        client.table("conferitori")
        .select("*, conferitori_tipi_latte(tipo_latte)")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .in_("tipo", tipi_conferitore)
        .order("ordine")
        .execute()
        .data
    )
    return [
        c for c in conferitori
        if tipo_latte in [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]
    ]


def _righe_dati_categoria(client, conferitori, data_giorno):
    """Una riga per OGNI conferitore attivo, anche con kg=0 quel giorno."""
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
        kg = float(rec[0]["kg"]) if rec and rec[0].get("kg") else 0.0
        ddt = rec[0].get("ddt") if rec else ""
        righe.append({
            "provenienza": c["ragione_sociale"],
            "codice_asl": c.get("piva", ""),  # TODO: sostituire con campo ASL dedicato quando aggiunto a Conferitori
            "kg": kg,
            "ddt": ddt or "",
        })
    return righe


def _copia_stile_riga(ws, riga_origine, riga_dest, colonne):
    for col in colonne:
        c_orig = ws[f"{col}{riga_origine}"]
        c_dest = ws[f"{col}{riga_dest}"]
        c_dest.font = copy.copy(c_orig.font)
        c_dest.fill = copy.copy(c_orig.fill)
        c_dest.border = copy.copy(c_orig.border)
        c_dest.number_format = c_orig.number_format
        c_dest.alignment = copy.copy(c_orig.alignment)


COLONNE_BLOCCO = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]


def _scrivi_blocco(ws, riga_inizio, n_righe_template, righe_dati, label_originale):
    """righe_dati vuoto => nessun conferitore attivo per questa categoria => blocco eliminato.
    righe_dati non vuoto => un conferitore attivo esiste, il blocco resta SEMPRE (anche a 0 kg)."""

    if not righe_dati:
        ws.delete_rows(riga_inizio, n_righe_template)
        return -n_righe_template

    n_dati = len(righe_dati)
    delta = n_dati - n_righe_template

    if delta > 0:
        riga_stile = riga_inizio + n_righe_template - 1
        ws.insert_rows(riga_inizio + n_righe_template, delta)
        for i in range(delta):
            r = riga_inizio + n_righe_template + i
            _copia_stile_riga(ws, riga_stile, r, COLONNE_BLOCCO)
            ws.merge_cells(f"B{r}:C{r}")
    elif delta < 0:
        ws.delete_rows(riga_inizio + n_dati, -delta)

    for i, dato in enumerate(righe_dati):
        r = riga_inizio + i
        if i == 0 and label_originale:
            ws[f"A{r}"] = label_originale
        ws[f"B{r}"] = dato["provenienza"]
        ws[f"D{r}"] = dato["codice_asl"]
        ws[f"G{r}"] = dato["kg"]
        ws[f"H{r}"] = dato["ddt"]
        ws[f"I{r}"] = _acidita_random() if dato["kg"] > 0 else ""
        ws[f"J{r}"] = _temperatura_random() if dato["kg"] > 0 else ""
        ws[f"K{r}"] = "OK" if dato["kg"] > 0 else ""

    return delta


LABEL_BLOCCHI = {
    "allevamenti_dop": "allevamenti dop latte di bufala",
    "caseifici_dop": "caseifici dop latte di bufala",
    "caseificio_non_dop": "caseificio non dop latte di bufala",
    "allevamenti_non_dop": "all. non dop latte di bufala",
    "vaccino": "latte vaccino",
    "semilavorato_bufala": "semilavorato bufala",
    "semilavorato_vaccino": "semilavorato vaccino",
}


def _prodotti_finiti(client, caseificio_id, data_giorno):
    """Tutti i prodotti attivi/visibili in Produzioni, SEMPRE elencati anche a quantita' 0."""
    prodotti = (
        client.table("prodotti")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .eq("mostra_in_produzioni", True)
        .order("nome")
        .execute()
        .data
    )
    righe = []
    for p in prodotti:
        rec = (
            client.table("produzioni")
            .select("*")
            .eq("prodotto_id", p["id"])
            .eq("data", str(data_giorno))
            .execute()
            .data
        )
        kg_totale = float(rec[0]["kg_totale"]) if rec and rec[0].get("kg_totale") else 0.0
        kg_diretta = float(rec[0]["kg_diretta"]) if rec and rec[0].get("kg_diretta") else 0.0
        kg_terzi = float(rec[0]["kg_terzi"]) if rec and rec[0].get("kg_terzi") else 0.0
        righe.append({
            "nome": p["nome"],
            "quantita": kg_totale,
            "diretta": kg_diretta,
            "terzi": kg_terzi,
        })
    return righe


def genera_tr(client, caseificio_id, data_giorno, output_path, copia_da_template=True):
    if copia_da_template:
        shutil.copy(TEMPLATE_PATH, output_path)
    wb = openpyxl.load_workbook(output_path)
    ws = wb[FOGLIO]

    is_dop = _caseificio_is_dop(client, caseificio_id)
    offset = 0
    totali = {"bufala_dop": 0.0, "bufala": 0.0, "vaccino": 0.0}

    for nome, riga_inizio, n_righe, tipi_conferitore, tipo_latte, richiede_dop in BLOCCHI:
        riga_reale = riga_inizio + offset

        if richiede_dop and not is_dop:
            conferitori = []
        else:
            conferitori = _conferitori_attivi_categoria(client, caseificio_id, tipi_conferitore, tipo_latte)

        righe_dati = _righe_dati_categoria(client, conferitori, data_giorno)

        if tipo_latte in totali:
            totali[tipo_latte] += sum(r["kg"] for r in righe_dati)

        delta = _scrivi_blocco(ws, riga_reale, n_righe, righe_dati, LABEL_BLOCCHI[nome])
        offset += delta

    # --- Totali (celle originali erano formule #REF! - qui scriviamo valori diretti) ---
    riga_tot = 48 + offset
    ws[f"E{riga_tot}"] = totali["bufala_dop"]
    ws[f"E{riga_tot + 1}"] = totali["bufala"]
    ws[f"E{riga_tot + 2}"] = totali["vaccino"]

    # --- Giacenza di apertura (dal Registro attuale) ---
    ws["E8"] = get_registro_giacenza_apertura(client, caseificio_id, data_giorno)  # TODO Registro

    # --- Prodotti finiti (righe 67-72 nel template originale, qui si spostano con l'offset) ---
    riga_prod = 67 + offset + 1  # +1: la riga 67 e' l'intestazione, i dati partono dalla successiva
    prodotti = _prodotti_finiti(client, caseificio_id, data_giorno)
    n_righe_template_prodotti = 5  # righe 68-72 nel template originale

    delta_prod = len(prodotti) - n_righe_template_prodotti
    if delta_prod > 0:
        riga_stile = riga_prod + n_righe_template_prodotti - 1
        ws.insert_rows(riga_prod + n_righe_template_prodotti, delta_prod)
        for i in range(delta_prod):
            r = riga_prod + n_righe_template_prodotti + i
            _copia_stile_riga(ws, riga_stile, r, ["A", "D", "F", "H", "J", "L", "N"])
    elif delta_prod < 0:
        ws.delete_rows(riga_prod + len(prodotti), -delta_prod)

    for i, prod in enumerate(prodotti):
        r = riga_prod + i
        ws[f"A{r}"] = prod["nome"]
        ws[f"D{r}"] = prod["quantita"]
        ws[f"F{r}"] = f"{data_giorno.strftime('%Y%m%d')}" if prod["quantita"] > 0 else ""
        ws[f"H{r}"] = prod["diretta"]
        ws[f"J{r}"] = prod["terzi"]

    wb.save(output_path)
    return output_path
