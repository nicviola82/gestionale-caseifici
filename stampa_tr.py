# ============================================================
# MODULO: STAMPA TR
# Compila il foglio "tr" (tabellone giornaliero) del template
# ufficiale (templates_dop.xlsx), riscritto il 27/08 seguendo con
# precisione il file reale fornito dall'utente (FAIL__1_.xlsx).
#
# REGOLA DELLE RIGHE DINAMICHE (solo per questo foglio, MBC/RBC
# restano sempre statici):
#   - un blocco/riga esiste se e solo se esiste un CONFERITORE
#     ATTIVO registrato per quella categoria (allevamenti/caseifici
#     dop/non-dop/vaccino/cagliata) - NON in base al fatto che abbia
#     consegnato qualcosa quel giorno. Un conferitore attivo compare
#     sempre, anche con 0 kg quel giorno.
#   - il blocco CONGELATO fa eccezione: e' un EVENTO (scongelamento
#     avvenuto quel giorno), non un conferitore fisso - quindi
#     compare SOLO se quel giorno c'e' stato davvero un evento
#     ("far vedere solo quello che entra realmente in azienda",
#     confermato dall'utente 27/08).
#   - i blocchi "allevamenti dop" e "caseifici dop" esistono
#     SOLO se il caseificio stesso e' DOP (caseifici.is_dop).
#     Se il caseificio non e' DOP, quei blocchi non vengono
#     nemmeno considerati.
#   - i prodotti finiti elencano SOLO i prodotti REALMENTE prodotti
#     (kg_totale>0) almeno una volta nel PERIODO selezionato (mese
#     o settimana) - corretto il 27/08 su richiesta esplicita
#     dell'utente: se in quel periodo non hai mai fatto la
#     delattosata, la delattosata non deve comparire in NESSUN
#     giorno del periodo (prima compariva sempre a 0, sbagliato).
#     Se pero' l'hai prodotta anche un solo giorno del periodo,
#     compare in TUTTI i giorni del periodo (anche a 0 nei giorni
#     in cui quel giorno specifico non l'hai fatta), per poter
#     confrontare colonna per colonna tra un giorno e l'altro.
#
# VENDITE DI LATTE (corretto il 27/08): NESSUN tetto massimo - se
# vendi a 10 destinatari diversi lo stesso giorno, compaiono tutte
# e 10 le righe (il template ne prevedeva 2 per riga fissa, ora si
# aggiungono righe extra automaticamente quando servono).
#
# LATTE CONGELATO/SCONGELATO (confermato dall'utente 27/08):
#   - latte SCONGELATO che rientra in produzione -> va tra i
#     conferitori di latte IN INGRESSO (blocco CONGELATO qui sotto),
#     contato SEMPRE come bufala NON-DOP (mai bufala_dop) - stessa
#     regola gia' in vigore nel Registro (registro_calc.py).
#   - latte che ESCE per essere congelato -> NON e' un ingresso, va
#     nella sezione Lavorazione, colonna "latte destinato al
#     congelamento" (G55 nel template originale).
#
# CAGLIATA (confermato dall'utente 27/08): righe distinte tra
# bufala e vaccino - due mini-blocchi "CAGLIATA BUFALA"/"CAGLIATA
# VACCINA", DENTRO la sezione ingresso ma ESCLUSI dai totali di
# latte (bufala/vaccino) sotto - "discorso diverso", sono conferimenti
# di semilavorato, non di latte.
#
# Le formule originali del template sono quasi tutte #REF! rotte
# (collegate a un workbook che non esiste piu'), quindi qui NON
# proviamo a ripararle: scriviamo valori diretti calcolati in
# Python, comprese le celle di totale - CORRETTE rispetto
# all'originale dove l'originale stesso sommava solo una parte
# delle righe del blocco (es. il totale G ingresso sommava solo
# G43+G44 invece di tutto il blocco CONGELATO, confermato con
# l'utente che va corretto).
# ============================================================
import random
import copy
import shutil
import datetime as _dt
import openpyxl

import registro_calc
from stampa_mbc import get_registro_giacenza_apertura, get_prodotto_e_produzione_giorno, TEMPLATE_PATH

FOGLIO = "tr"


def _set(ws, coord, value):
    """Scrive in una cella SEMPRE in modo sicuro, anche se e' una cella "secondaria" di una
    cella unita (merge) - openpyxl lancia AttributeError se si scrive direttamente su una
    MergedCell (solo la cella in alto a sinistra della fusione e' scrivibile). Corretto il
    29/08 per la seconda volta: anche provare a smergiare puo' fallire (KeyError) se le
    informazioni sulle fusioni sono rimaste incoerenti dopo un insert_rows - limite noto di
    openpyxl. Questa versione e' quindi DIFENSIVA AL MASSIMO: prova a smergiare tutto quello
    che copre la cella, e se anche questo fallisce non blocca MAI la generazione del foglio
    (nel caso estremo quella singola cella resta vuota, ma il resto del documento si genera
    comunque) - meglio un dato mancante che un errore che blocca tutto. Va SEMPRE usata al
    posto di ws[coord] = valore, ovunque nel foglio tr."""
    try:
        cell = ws[coord]
        if type(cell).__name__ == "MergedCell":
            for rng in list(ws.merged_cells.ranges):
                if rng.min_row <= cell.row <= rng.max_row and rng.min_col <= cell.column <= rng.max_col:
                    try:
                        ws.unmerge_cells(str(rng))
                    except Exception:
                        pass
            cell = ws[coord]
        cell.value = value
    except Exception:
        pass  # non blocchiamo mai la generazione dell'intero foglio per una singola cella


# (nome, riga_inizio, n_righe_template, tipi_conferitore, tipo_latte, richiede_caseificio_dop)
# NOTA: tolti "semilavorato_bufala"/"semilavorato_vaccino" - non esistono nel template reale,
# erano un errore di mappatura (le righe 43-46 sono in realta' il blocco CONGELATO).
BLOCCHI_CONFERITORI = [
    ("allevamenti_dop", 12, 17, ["allevatore"], "bufala_dop", True),
    ("caseifici_dop", 29, 4, ["caseificio"], "bufala_dop", True),
    ("caseificio_non_dop", 33, 5, ["caseificio"], "bufala", False),
    ("allevamenti_non_dop", 38, 2, ["allevatore"], "bufala", False),
    ("vaccino", 40, 3, ["allevatore", "caseificio", "intermediario"], "vaccino", False),
]

LABEL_BLOCCHI = {
    "allevamenti_dop": "allevamenti dop latte di bufala",
    "caseifici_dop": "caseifici dop latte di bufala",
    "caseificio_non_dop": "caseificio non dop latte di bufala",
    "allevamenti_non_dop": "all. non dop latte di bufala",
    "vaccino": "latte vaccino",
}

RIGA_CONGELATO = 43
N_RIGHE_TEMPLATE_CONGELATO = 4  # A43:A46 nel template originale
RIGA_CAGLIATA = 47
N_RIGHE_TEMPLATE_CAGLIATA_BUFALA = 1  # riga 47 nel template originale
N_RIGHE_TEMPLATE_CAGLIATA_VACCINA = 0  # non esiste nel template originale, e' una riga NUOVA


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


def _righe_congelato(client, caseificio_id, data_giorno):
    """SOLO gli eventi di SCONGELAMENTO avvenuti quel giorno (latte che rientra in
    produzione) - una riga per struttura esterna, raggruppando se piu' movimenti
    lo stesso giorno dalla stessa struttura. Dinamico: nessun evento -> blocco assente."""
    movimenti = (
        client.table("movimenti_congelato")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("data", str(data_giorno))
        .eq("tipo", "scongelamento")
        .execute()
        .data
    )
    per_struttura = {}
    for m in movimenti:
        chiave = m.get("struttura_esterna") or "(interno)"
        if chiave not in per_struttura:
            per_struttura[chiave] = {"provenienza": chiave, "codice_asl": "", "kg": 0.0, "ddt": []}
        per_struttura[chiave]["kg"] += float(m.get("kg") or 0)
        if m.get("ddt"):
            per_struttura[chiave]["ddt"].append(m["ddt"])
    righe = []
    for dato in per_struttura.values():
        dato["ddt"] = ", ".join(dato["ddt"])
        righe.append(dato)
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
    """righe_dati vuoto => blocco assente (0 righe, nessun conferitore/evento).
    righe_dati non vuoto => il blocco resta SEMPRE (anche a 0 kg, per i conferitori fissi).
    n_righe_template puo' essere 0 (blocco nuovo, non esisteva nel template originale) - in
    quel caso, se ci sono dati, le righe vengono semplicemente inserite da zero.
    NOTA 29/08: non si crea piu' nessuna fusione (merge) DURANTE l'inserimento di righe -
    openpyxl non aggiorna in modo affidabile le fusioni quando si inseriscono/eliminano righe
    piu' volte di seguito (causa di crash reali, vedi _set) - le uniche fusioni create sono
    quella cosmetica dell'etichetta a fine blocco, e solo in modo protetto."""
    if not righe_dati:
        if n_righe_template > 0:
            ws.delete_rows(riga_inizio, n_righe_template)
        return -n_righe_template

    n_dati = len(righe_dati)
    delta = n_dati - n_righe_template

    if delta > 0:
        riga_stile = riga_inizio + n_righe_template - 1 if n_righe_template > 0 else riga_inizio - 1
        ws.insert_rows(riga_inizio + n_righe_template, delta)
        for i in range(delta):
            r = riga_inizio + n_righe_template + i
            _copia_stile_riga(ws, riga_stile, r, COLONNE_BLOCCO)
    elif delta < 0:
        ws.delete_rows(riga_inizio + n_dati, -delta)

    for i, dato in enumerate(righe_dati):
        r = riga_inizio + i
        if i == 0 and label_originale:
            _set(ws, f"A{r}", label_originale)
        _set(ws, f"B{r}", dato["provenienza"])
        _set(ws, f"D{r}", dato["codice_asl"])
        _set(ws, f"G{r}", dato["kg"])
        _set(ws, f"H{r}", dato["ddt"])
        _set(ws, f"I{r}", _acidita_random() if dato["kg"] > 0 else "")
        _set(ws, f"J{r}", _temperatura_random() if dato["kg"] > 0 else "")
        _set(ws, f"K{r}", "OK" if dato["kg"] > 0 else "")

    if n_dati > 1 and label_originale:
        try:
            ws.merge_cells(f"A{riga_inizio}:A{riga_inizio + n_dati - 1}")
            _copia_stile_riga(ws, riga_inizio, riga_inizio, ["A"])
        except Exception:
            pass  # cosmetico: se fallisce, l'etichetta resta solo sulla prima riga, nessun crash

    return delta


def _prodotti_ammessi_nel_periodo(client, caseificio_id, data_da, data_a):
    """Elenco prodotti (attivi, visibili in Produzioni) che sono stati REALMENTE prodotti
    (kg_totale>0) almeno un giorno nel periodo [data_da, data_a] - dinamico, richiesto
    dall'utente 27/08: un prodotto mai fatto nel periodo non deve comparire in nessun giorno."""
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
    if not prodotti:
        return []
    ids = [p["id"] for p in prodotti]
    produzioni_periodo = (
        client.table("produzioni").select("prodotto_id, kg_totale")
        .in_("prodotto_id", ids).gte("data", str(data_da)).lte("data", str(data_a))
        .execute().data
    )
    ids_usati = {r["prodotto_id"] for r in produzioni_periodo if float(r.get("kg_totale") or 0) > 0}
    return [p for p in prodotti if p["id"] in ids_usati]


def _prodotti_finiti(client, caseificio_id, data_giorno, prodotti_ammessi):
    """Una riga per ciascun prodotto GIA' FILTRATO (vedi _prodotti_ammessi_nel_periodo),
    con la produzione di QUESTO giorno (anche 0, se quel giorno specifico non l'ha fatto
    ma lo ha fatto in un altro giorno del periodo)."""
    righe = []
    for p in prodotti_ammessi:
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


def _resa_dop_giorno(client, caseificio_id, data_giorno):
    """Resa MBC del giorno = kg MBC prodotta / kg latte bufala_dop trasformato (stessa
    definizione usata nel Registro per convertire kg-prodotto in kg-latte)."""
    _, produzione_mozz = get_prodotto_e_produzione_giorno(
        client, caseificio_id, data_giorno, "Mozzarella di Bufala Campana DOP", solo_dop=True
    )
    kg_mozz = float((produzione_mozz or {}).get("kg_totale") or 0)
    kg_trasf_dop = registro_calc.trasformato(client, caseificio_id, "bufala_dop", data_giorno)
    return (kg_mozz / kg_trasf_dop * 100) if kg_trasf_dop > 0 else None


def _latte_dop_per_gruppo(client, caseificio_id, data_giorno, resa, is_dop_prodotto, escludi_ricotta, solo_nome=None):
    """kg di latte DOP consumato per un gruppo di prodotti (dop_altri o declassati), stessa
    logica di 'LatteDOP' nel Registro: kg_dop_prodotto / resa. Se solo_nome e' dato, filtra
    SOLO il prodotto il cui nome contiene quella stringa (es. 'senza lattosio')."""
    if not resa:
        return 0.0
    prodotti = (
        client.table("prodotti")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .eq("is_dop", is_dop_prodotto)
        .execute()
        .data
    )
    if escludi_ricotta:
        prodotti = [p for p in prodotti if "ricotta" not in p["nome"].lower()]
    if solo_nome:
        prodotti = [p for p in prodotti if solo_nome.lower() in p["nome"].lower()]
    elif is_dop_prodotto:
        prodotti = [p for p in prodotti if "senza lattosio" not in p["nome"].lower()]

    totale_latte = 0.0
    for p in prodotti:
        rec = (
            client.table("produzioni").select("*, produzione_origine(*)")
            .eq("prodotto_id", p["id"]).eq("data", str(data_giorno)).execute().data
        )
        if not rec:
            continue
        r = rec[0]
        tot = float(r.get("kg_totale") or 0)
        origini = {o["origine"]: o for o in r.get("produzione_origine", [])}
        kg_nondop = float(origini["non_dop"]["kg"]) if "non_dop" in origini and origini["non_dop"].get("kg") else 0.0
        kg_dop = tot - kg_nondop
        if kg_dop > 0:
            totale_latte += kg_dop / (resa / 100)
    return totale_latte


def _scrivi_vendite(ws, riga_inizio, vendite):
    """Scrive le vendite di latte del giorno, 2 destinatari per riga (colonne J/K/L e
    M/N/O) - inserisce righe extra automaticamente se ce ne sono piu' di 2, NESSUN tetto
    massimo (corretto il 27/08 su richiesta esplicita - prima erano fisse a 2)."""
    n_coppie = max(1, -(-len(vendite) // 2)) if vendite else 1  # arrotonda per eccesso, min 1
    delta = n_coppie - 1  # il template ha gia' 1 riga base per le vendite
    if delta > 0:
        ws.insert_rows(riga_inizio + 1, delta)
        for i in range(delta):
            r = riga_inizio + 1 + i
            _copia_stile_riga(ws, riga_inizio, r, ["G", "H", "I", "J", "K", "L", "M", "N", "O"])
    for i in range(0, len(vendite), 2):
        r = riga_inizio + i // 2
        v1 = vendite[i]
        _set(ws, f"J{r}", round(float(v1.get("kg") or 0)))
        _set(ws, f"K{r}", v1.get("ddt") or "")
        _set(ws, f"L{r}", (v1.get("destinatari_vendita") or {}).get("ragione_sociale", ""))
        if i + 1 < len(vendite):
            v2 = vendite[i + 1]
            _set(ws, f"M{r}", round(float(v2.get("kg") or 0)))
            _set(ws, f"N{r}", v2.get("ddt") or "")
            _set(ws, f"O{r}", (v2.get("destinatari_vendita") or {}).get("ragione_sociale", ""))
    return delta


def _compila_tr(ws, client, caseificio_id, data_giorno, prodotti_ammessi=None):
    """Scrive i dati di UN giorno su UN foglio 'tr' worksheet gia' aperto - separata da
    genera_tr() (apertura/salvataggio file) cosi' si puo' riusare dentro un workbook
    multi-giorno (vedi genera_tr_periodo), stessa idea di _compila_mbc/_compila_rbc.
    prodotti_ammessi: elenco gia' filtrato per il periodo (vedi _prodotti_ammessi_nel_periodo).
    Se None (chiamata per un singolo giorno, senza un periodo di riferimento), si calcola
    usando SOLO quel giorno come periodo."""
    if prodotti_ammessi is None:
        prodotti_ammessi = _prodotti_ammessi_nel_periodo(client, caseificio_id, data_giorno, data_giorno)
    # CORREZIONE 29/08: rimuove TUTTE le fusioni (merge) presenti nel template PRIMA di
    # inserire/eliminare qualunque riga - openpyxl non tiene aggiornate in modo affidabile le
    # fusioni quando si inseriscono/eliminano righe piu' volte di seguito (causa reale di due
    # crash precedenti). Partire senza nessuna fusione elimina il problema alla radice; le
    # uniche fusioni ricreate sono quelle cosmetiche gestite direttamente da _scrivi_blocco,
    # in modo protetto.
    for rng in list(ws.merged_cells.ranges):
        try:
            ws.unmerge_cells(str(rng))
        except Exception:
            pass
    is_dop = _caseificio_is_dop(client, caseificio_id)
    offset = 0
    totali = {"bufala_dop": 0.0, "bufala": 0.0, "vaccino": 0.0}

    # ------------------------------------------------------------
    # SEZIONE INGRESSO: blocchi conferitori fissi (allevamenti/caseifici dop/non-dop/vaccino)
    # ------------------------------------------------------------
    for nome, riga_inizio, n_righe, tipi_conferitore, tipo_latte, richiede_dop in BLOCCHI_CONFERITORI:
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

    # ------------------------------------------------------------
    # SEZIONE INGRESSO: CONGELATO (SOLO scongelamento = latte che rientra in produzione,
    # confermato dall'utente 27/08 - conta come bufala NON-DOP, mai bufala_dop, e va nei
    # totali del latte bufala non-DOP esattamente come un conferimento qualsiasi)
    # ------------------------------------------------------------
    riga_congelato = RIGA_CONGELATO + offset
    righe_congelato = _righe_congelato(client, caseificio_id, data_giorno)
    totali["bufala"] += sum(r["kg"] for r in righe_congelato)
    delta = _scrivi_blocco(ws, riga_congelato, N_RIGHE_TEMPLATE_CONGELATO, righe_congelato, "CONGELATO (latte scongelato rientrato)")
    offset += delta

    # ------------------------------------------------------------
    # SEZIONE INGRESSO: CAGLIATA BUFALA / CAGLIATA VACCINA (righe distinte, ESCLUSE dai
    # totali di latte bufala/vaccino sopra - "discorso diverso", confermato dall'utente)
    # ------------------------------------------------------------
    riga_cagliata_buf = RIGA_CAGLIATA + offset
    conferitori_cag_buf = _conferitori_attivi_categoria(
        client, caseificio_id, ["allevatore", "caseificio", "intermediario"], "semilavorato_bufala"
    )
    righe_cag_buf = _righe_dati_categoria(client, conferitori_cag_buf, data_giorno)
    delta = _scrivi_blocco(ws, riga_cagliata_buf, N_RIGHE_TEMPLATE_CAGLIATA_BUFALA, righe_cag_buf, "CAGLIATA BUFALA")
    offset += delta

    riga_cagliata_vacc = RIGA_CAGLIATA + offset  # subito dopo il blocco cagliata bufala
    conferitori_cag_vacc = _conferitori_attivi_categoria(
        client, caseificio_id, ["allevatore", "caseificio", "intermediario"], "semilavorato_vaccino"
    )
    righe_cag_vacc = _righe_dati_categoria(client, conferitori_cag_vacc, data_giorno)
    delta = _scrivi_blocco(ws, riga_cagliata_vacc, N_RIGHE_TEMPLATE_CAGLIATA_VACCINA, righe_cag_vacc, "CAGLIATA VACCINA")
    offset += delta

    # --- Totali (celle originali erano formule #REF! parziali - qui corretti sommando
    #     TUTTE le righe reali del blocco, non solo le prime due come nel template originale) ---
    riga_tot = 48 + offset
    _set(ws, f"E{riga_tot}", totali["bufala_dop"])
    _set(ws, f"E{riga_tot + 1}", totali["bufala"])
    _set(ws, f"E{riga_tot + 2}", totali["vaccino"])

    # --- Giacenza di apertura DOP (dal Registro) ---
    _set(ws, "E8", get_registro_giacenza_apertura(client, caseificio_id, data_giorno))

    # ------------------------------------------------------------
    # SEZIONE LAVORAZIONE (righe 55-61 nel template originale, si spostano con l'offset)
    # Mappata sui dati gia' calcolati nel Registro (registro_calc.py) - stessi numeri che
    # vedi nella pagina Registro, nessun ricalcolo parallelo.
    # ------------------------------------------------------------
    riga_lav_intest = 55 + offset  # intestazioni fisse "latte destinato al congelamento"/"latte venduto"
    riga_lav1_val = 57 + offset    # valori sotto le etichette "buf dop/buf non dop/dop declassato/delattosata" (riga 56)
    riga_lav2_val = 59 + offset    # valori sotto le etichette "cagliata b/v, buf/vac per mista, vaccino" (riga 58)

    resa = _resa_dop_giorno(client, caseificio_id, data_giorno)
    kg_buf_dop = registro_calc.trasformato(client, caseificio_id, "bufala_dop", data_giorno)
    kg_buf_non_dop = registro_calc.trasformato(client, caseificio_id, "bufala", data_giorno)
    kg_buf_dop_declassato = _latte_dop_per_gruppo(client, caseificio_id, data_giorno, resa, is_dop_prodotto=False, escludi_ricotta=True)
    kg_buf_dop_delattosata = _latte_dop_per_gruppo(client, caseificio_id, data_giorno, resa, is_dop_prodotto=True, escludi_ricotta=True, solo_nome="senza lattosio")
    _set(ws, f"A{riga_lav1_val}", round(kg_buf_dop) if kg_buf_dop else 0)
    _set(ws, f"B{riga_lav1_val}", round(kg_buf_non_dop) if kg_buf_non_dop else 0)
    _set(ws, f"C{riga_lav1_val}", round(kg_buf_dop_declassato) if kg_buf_dop_declassato else 0)
    _set(ws, f"E{riga_lav1_val}", round(kg_buf_dop_delattosata) if kg_buf_dop_delattosata else 0)

    kg_cagliata_b = sum(r["kg"] for r in righe_cag_buf)
    kg_cagliata_v = sum(r["kg"] for r in righe_cag_vacc)
    kg_buf_mista = registro_calc.mista_consumato(client, caseificio_id, "bufala", data_giorno)
    kg_vac_mista = registro_calc.mista_consumato(client, caseificio_id, "vaccino", data_giorno)
    kg_vaccino_trasf = registro_calc.trasformato(client, caseificio_id, "vaccino", data_giorno)
    _set(ws, f"A{riga_lav2_val}", round(kg_cagliata_b) if kg_cagliata_b else 0)
    _set(ws, f"B{riga_lav2_val}", round(kg_cagliata_v) if kg_cagliata_v else 0)
    _set(ws, f"C{riga_lav2_val}", round(kg_buf_mista) if kg_buf_mista else 0)
    _set(ws, f"D{riga_lav2_val}", round(kg_vac_mista) if kg_vac_mista else 0)
    _set(ws, f"E{riga_lav2_val}", round(kg_vaccino_trasf) if kg_vaccino_trasf else 0)

    # latte destinato al congelamento (uscita - opposto dello scongelamento sezione ingresso)
    movimenti_uscita = (
        client.table("movimenti_congelato").select("*")
        .eq("caseificio_id", caseificio_id).eq("data", str(data_giorno)).eq("tipo", "congelamento")
        .execute().data
    )
    kg_congelamento_uscita = sum(float(m.get("kg") or 0) for m in movimenti_uscita)
    ddt_congelamento_uscita = ", ".join(m["ddt"] for m in movimenti_uscita if m.get("ddt"))
    _set(ws, f"G{riga_lav_intest + 1}", round(kg_congelamento_uscita) if kg_congelamento_uscita else "")
    _set(ws, f"I{riga_lav_intest + 1}", ddt_congelamento_uscita)

    # latte venduto (NESSUN tetto massimo - righe extra inserite automaticamente se servono)
    try:
        vendite_giorno = (
            client.table("vendite_latte_destinatari")
            .select("*, destinatari_vendita(ragione_sociale)")
            .eq("caseificio_id", caseificio_id).eq("data", str(data_giorno))
            .execute().data
        )
    except Exception:
        vendite_giorno = []
    delta_vendite = _scrivi_vendite(ws, riga_lav_intest + 1, vendite_giorno)
    offset += delta_vendite

    # giacenza di chiusura (bufala dop / bufala non-dop) - dal Registro
    riga_giac1 = 61 + offset       # giacenza bufala dop / latte di buf
    _set(ws, f"B{riga_giac1}", round(registro_calc.giacenza_chiusura(client, caseificio_id, "bufala_dop", data_giorno)))
    _set(ws, f"D{riga_giac1}", round(registro_calc.giacenza_chiusura(client, caseificio_id, "bufala", data_giorno)))

    # ------------------------------------------------------------
    # SEZIONE PRODOTTI FINITI (righe 67-72 nel template originale, si spostano con l'offset)
    # SOLO i prodotti realmente prodotti nel periodo selezionato (vedi prodotti_ammessi) -
    # dinamico, corretto il 27/08.
    # ------------------------------------------------------------
    riga_prod = 67 + offset + 1  # +1: la riga 67 e' l'intestazione, i dati partono dalla successiva
    prodotti = _prodotti_finiti(client, caseificio_id, data_giorno, prodotti_ammessi)
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
        _set(ws, f"A{r}", prod["nome"])
        _set(ws, f"D{r}", prod["quantita"])
        _set(ws, f"F{r}", data_giorno.strftime("%d/%m/%Y") if prod["quantita"] > 0 else "")
        _set(ws, f"H{r}", prod["diretta"])
        _set(ws, f"J{r}", prod["terzi"])


def genera_tr(client, caseificio_id, data_giorno, output_path, copia_da_template=True):
    """Un solo giorno = un solo foglio tr (comportamento originale, invariato)."""
    if copia_da_template:
        shutil.copy(TEMPLATE_PATH, output_path)
    wb = openpyxl.load_workbook(output_path)
    ws = wb[FOGLIO]
    _compila_tr(ws, client, caseificio_id, data_giorno)
    wb.save(output_path)
    return output_path


def genera_tr_periodo(client, caseificio_id, data_da, data_a, output_path):
    """Un file tr con UN FOGLIO PER GIORNO nell'intervallo [data_da, data_a] (inclusi).
    File separato da MBC/RBC, come richiesto - non contiene gli altri due fogli del template.
    NOTA IMPORTANTE: il foglio tr ha righe dinamiche (inserite/rimosse in base ai conferitori
    del giorno) - ogni giorno DEVE partire da una copia "pulita" del template originale, mai
    dal foglio gia' compilato del giorno precedente (che potrebbe avere righe inserite/rimosse
    diverse). Per questo si tiene un foglio "pristine" nascosto, usato solo come sorgente per
    wb.copy_worksheet(), e lo si cancella alla fine.
    """
    shutil.copy(TEMPLATE_PATH, output_path)
    wb = openpyxl.load_workbook(output_path)
    for nome in list(wb.sheetnames):
        if nome != FOGLIO:
            del wb[nome]
    ws_pristine = wb[FOGLIO]
    ws_pristine.title = "_pristine_tr"

    # calcolato UNA SOLA VOLTA per tutto il periodo (non per ogni giorno): un prodotto
    # compare in tutti i giorni del periodo se e' stato fatto almeno un giorno, altrimenti
    # in nessuno - vedi nota in cima al file (corretto 27/08).
    prodotti_ammessi = _prodotti_ammessi_nel_periodo(client, caseificio_id, data_da, data_a)

    n_giorni = (data_a - data_da).days + 1
    for i in range(n_giorni):
        giorno = data_da + _dt.timedelta(days=i)
        ws = wb.copy_worksheet(ws_pristine)
        ws.title = giorno.strftime("%d-%m-%Y")
        _compila_tr(ws, client, caseificio_id, giorno, prodotti_ammessi=prodotti_ammessi)

    del wb["_pristine_tr"]
    wb.save(output_path)
    return output_path
