# ============================================================
# MODULO: STAMPA RBC
# Compila il foglio "RBC" del template ufficiale RINA
# (templates_dop.xlsx) per una singola giornata di lavorazione.
#
# IMPORTANTE: il foglio RBC e' un documento ufficiale statico,
# come MBC - la struttura del file non viene mai modificata.
#
# NOTA: Scheda N. (Q5) e Data (U5) sul foglio RBC sono gia'
# collegate con formula al foglio MBC dello stesso workbook
# (=MBC!C3 e =MBC!H3) - non serve scriverle qui, basta che
# genera_mbc() sia stata eseguita sullo stesso file prima
# (o nello stesso momento) di genera_rbc().
# ============================================================
import shutil
import openpyxl

from stampa_mbc import get_anagrafica, get_impostazione, get_produzione_giorno, numero_scheda

FOGLIO = "RBC"


# ------------------------------------------------------------
# BLOCCO: DATI DAL FOGLIO SIERO (non ancora costruito nel
# gestionale). Placeholder isolati, da ricollegare quando la
# fase Siero sara' pronta - stesso principio delle funzioni
# TODO in stampa_mbc.py.
# ------------------------------------------------------------
def get_siero_acquistato(client, caseificio_id, data_giorno):
    """Ritorna al massimo 1 riga (confermato: max un acquisto di siero da altro caseificio a giornata)."""
    # TODO: collegare al foglio Siero quando pronto
    return None  # es. futuro: {"origine": ..., "ddt": ..., "kg": ..., "ora_rottura": ..., "tank": ...}


def get_siero_autoprodotto(client, caseificio_id, data_giorno):
    """Ritorna fino a 2 cicli (confermato: max 2 cicli di lavorazione al giorno)."""
    # TODO: collegare al foglio Siero quando pronto
    return []  # es. futuro: [{"origine": ..., "kg": ..., "ora_rottura": ..., "tank": ...}, ...]


def get_siero_kg_totale_lavorato(client, caseificio_id, data_giorno):
    # TODO: collegare al foglio Siero quando pronto
    return 0.0


# ------------------------------------------------------------
# BLOCCO: COMPILAZIONE FOGLIO RBC
# Va chiamata sullo STESSO file .xlsx su cui e' gia' stata
# chiamata genera_mbc() per lo stesso giorno.
# ------------------------------------------------------------
def genera_rbc(client, caseificio_id, data_giorno, output_path):
    wb = openpyxl.load_workbook(output_path)
    ws = wb[FOGLIO]

    anagrafica = get_anagrafica(client, caseificio_id)

    # --- Intestazione ---
    ws["C5"] = anagrafica.get("ragione_sociale", "")
    # ws["L5"] = codice RINA AGRIFOOD -> non ancora presente in Anagrafica, lasciato vuoto
    # Q5 (Scheda N.) e U5 (Data) restano le formule originali =MBC!C3 / =MBC!H3, non toccarle

    # --- Primo Siero Acquistato (max 1 riga, come confermato) ---
    # NOTA: A11:D12, E11:H12, I11:L12, M11:R12, S11:W12 sono le 5 celle unite reali -
    # origine/ddt/kg/ora_rottura/tank vanno scritti sugli anchor A11/E11/I11/M11/S11.
    acquistato = get_siero_acquistato(client, caseificio_id, data_giorno)
    if acquistato:
        ws["A11"] = acquistato.get("origine", "")
        ws["E11"] = acquistato.get("ddt", "")
        ws["I11"] = acquistato.get("kg", 0)
        ws["M11"] = acquistato.get("ora_rottura", "")
        ws["S11"] = acquistato.get("tank", "")

    # --- Primo Siero Autoprodotto (max 2 cicli, come confermato) ---
    # ATTENZIONE: righe 25-26 e 27-28 NON hanno la stessa struttura di colonne unite
    # (la riga 25 ha 4 blocchi larghi A/L/P/T, la riga 27 ne ha 7 piu' stretti A/F/H/J/L/P/T) -
    # non e' un semplice ciclo "riga base + i" come nelle altre sezioni. Struttura da
    # verificare con calma quando costruiamo davvero il collegamento al foglio Siero
    # (per ora get_siero_autoprodotto() ritorna sempre lista vuota, quindi questo blocco
    # non viene mai eseguito e non causa errori).
    autoprodotto = get_siero_autoprodotto(client, caseificio_id, data_giorno)
    if autoprodotto:
        raise NotImplementedError(
            "Scrittura Primo Siero Autoprodotto non ancora implementata: "
            "la struttura delle celle unite (righe 25-28) va verificata prima di scrivere qui."
        )

    # --- Lavorazione ---
    ws["H41"] = get_siero_kg_totale_lavorato(client, caseificio_id, data_giorno)  # TODO Siero
    ws["N41"] = 1  # default automatico confermato, modificabile a mano prima della stampa

    # K45 (acidita' primo siero) e K51 (sale) restano le formule originali del template - non toccarle

    ws["F53"] = get_impostazione(client, caseificio_id, "acidita_primo_siero", data_giorno)
    ws["F59"] = get_impostazione(client, caseificio_id, "temperatura_latte", data_giorno)

    # --- Caratteristiche prodotto finito: default "Idoneo" come nel template originale ---
    # NOTA: F68:H69 e F70:H71 sono celle unite nel template - si scrive solo nella cella
    # "principale" (in alto a sinistra) di ciascuna, F69 NON e' scrivibile (dentro il merge F68:H69).
    for cella in ["F68", "F70"]:
        ws[cella] = "Idoneo"

    # --- Confezionamento (Ricotta di Bufala DOP prodotta) ---
    kg_ricotta = get_produzione_giorno(client, caseificio_id, data_giorno, "Ricotta di Bufala DOP")
    ws["D78"] = kg_ricotta  # D78 e' l'anchor del merge D78:G79 (F78 e' dentro il merge, non scrivibile)
    ws["P78"] = f"{data_giorno.strftime('%Y%m%d')}-{numero_scheda(data_giorno)}"  # lotto - P78 anchor di P78:S79 (Q78 non scrivibile)

    wb.save(output_path)
    return output_path
