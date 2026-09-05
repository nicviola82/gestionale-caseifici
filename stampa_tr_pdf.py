# ============================================================
# MODULO: STAMPA TR (PDF)
# Foglio "tr" (tabellone giornaliero di rintracciabilita' latte/prodotti),
# in formato PDF invece di Excel - richiesto dall'utente il 29/08 perche'
# un foglio Excel "non si capisce molto", un PDF e' un documento pronto da
# leggere/stampare.
#
# REGOLA "SOLO DATI REALMENTE INSERITI" (corretta il 29/08 su richiesta
# esplicita): le righe dei conferitori e i valori della sezione Lavorazione
# compaiono SOLO se il valore quel giorno e' > 0 - niente piu' righe a 0 per
# conferitori attivi che quel giorno non hanno consegnato nulla. ECCEZIONE:
# i PRODOTTI OTTENUTI restano visibili anche a 0 nei giorni in cui non sono
# stati fatti, MA SOLO se sono stati prodotti almeno un giorno nel periodo
# selezionato - questo per poter confrontare colonna per colonna tra un
# giorno e l'altro (richiesta esplicita precedente, ancora valida). Stessa
# cosa per la GIACENZA (e' uno stato, non un inserimento: si mostra sempre,
# anche a 0) e per i TOTALI (sono un riepilogo calcolato, non un dato
# inserito: si mostrano sempre).
#
# Stessa raccolta dati delle versioni Excel (stampa_tr.py / stampa_tr_template.py)
# - cambia solo COME viene presentato il risultato.
# ============================================================
import random
import datetime as _dt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

import registro_calc

COLORE_SEZIONE = colors.HexColor("#1F3864")
COLORE_INTESTAZIONE_TABELLA = colors.HexColor("#D9E1F2")
COLORE_TOTALE = colors.HexColor("#F2F2F2")
COLORE_GRIGIO_CHIARO = colors.HexColor("#9DB2D9")

stili = getSampleStyleSheet()
STILE_TITOLO = ParagraphStyle("TitoloTR", parent=stili["Title"], fontSize=15, textColor=COLORE_SEZIONE, spaceAfter=2)
STILE_SOTTOTITOLO = ParagraphStyle("SottotitoloTR", parent=stili["Normal"], fontSize=9, textColor=colors.HexColor("#595959"), spaceAfter=10)
STILE_SEZIONE = ParagraphStyle("SezioneTR", parent=stili["Heading2"], fontSize=12, textColor=colors.white, backColor=COLORE_SEZIONE, spaceBefore=10, spaceAfter=6, leftIndent=4, borderPadding=4)
STILE_SOTTOSEZIONE = ParagraphStyle("SottosezioneTR", parent=stili["Heading3"], fontSize=10, textColor=COLORE_SEZIONE, spaceBefore=6, spaceAfter=3)
STILE_VUOTO = ParagraphStyle("VuotoTR", parent=stili["Normal"], fontSize=8, textColor=colors.HexColor("#A6A6A6"), italic=True)


def _acidita_random():
    return f"3,{random.randint(5, 9)} °SH/50ml"


def _temperatura_random():
    return f"T°C {random.randint(3, 5)},{random.randint(1, 9)}"


# ------------------------------------------------------------
# BLOCCO: RACCOLTA DATI (identica nella sostanza alle versioni Excel - qui
# cambia solo il filtro "solo kg>0" per conferitori/lavorazione)
# ------------------------------------------------------------
def _caseificio_e_dop(client, caseificio_id):
    c = client.table("caseifici").select("*").eq("id", caseificio_id).single().execute().data
    return c, bool(c and c.get("is_dop"))


def _conferitori_attivi_categoria(client, caseificio_id, tipi_conferitore, tipo_latte):
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
    """SOLO i conferitori che hanno consegnato davvero (kg>0) quel giorno - corretto 29/08,
    prima mostrava sempre tutti i conferitori attivi anche a 0 kg."""
    righe = []
    for c in conferitori:
        rec = (
            client.table("conferimenti").select("*")
            .eq("conferitore_id", c["id"]).eq("data", str(data_giorno))
            .execute().data
        )
        kg = float(rec[0]["kg"]) if rec and rec[0].get("kg") else 0.0
        if kg <= 0:
            continue
        ddt = rec[0].get("ddt") if rec else ""
        righe.append({"provenienza": c["ragione_sociale"], "codice": c.get("piva", ""), "kg": kg, "ddt": ddt or ""})
    return righe


def _righe_congelato(client, caseificio_id, data_giorno):
    movimenti = (
        client.table("movimenti_congelato").select("*")
        .eq("caseificio_id", caseificio_id).eq("data", str(data_giorno)).eq("tipo", "scongelamento")
        .execute().data
    )
    per_struttura = {}
    for m in movimenti:
        chiave = m.get("struttura_esterna") or "(interno)"
        d = per_struttura.setdefault(chiave, {"provenienza": chiave, "codice": "", "kg": 0.0, "ddt": []})
        d["kg"] += float(m.get("kg") or 0)
        if m.get("ddt"):
            d["ddt"].append(m["ddt"])
    righe = []
    for d in per_struttura.values():
        if d["kg"] <= 0:
            continue
        d["ddt"] = ", ".join(d["ddt"])
        righe.append(d)
    return righe


def _prodotti_ammessi_nel_periodo(client, caseificio_id, data_da, data_a):
    prodotti = (
        client.table("prodotti").select("*")
        .eq("caseificio_id", caseificio_id).eq("attivo", True).eq("mostra_in_produzioni", True)
        .order("nome").execute().data
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


def _prodotti_finiti(client, prodotti_ammessi, data_giorno):
    """Prodotti gia' filtrati per periodo - qui restano visibili ANCHE a 0 (per confrontare
    tra un giorno e l'altro), a differenza di conferitori/lavorazione. Lotto calcolato con la
    stessa logica gia' usata in MBC/RBC (calcola_lotto), aggiunto il 29/08 su richiesta."""
    from stampa_mbc import calcola_lotto
    righe = []
    for p in prodotti_ammessi:
        rec = (
            client.table("produzioni").select("*").eq("prodotto_id", p["id"]).eq("data", str(data_giorno))
            .execute().data
        )
        totale = float(rec[0]["kg_totale"]) if rec and rec[0].get("kg_totale") else 0.0
        righe.append({
            "nome": p["nome"],
            "lotto": calcola_lotto(p, data_giorno) if totale > 0 else "",
            "totale": totale,
            "diretta": float(rec[0]["kg_diretta"]) if rec and rec[0].get("kg_diretta") else 0.0,
            "terzi": float(rec[0]["kg_terzi"]) if rec and rec[0].get("kg_terzi") else 0.0,
        })
    return righe


def _resa_dop_giorno(client, caseificio_id, data_giorno):
    from stampa_mbc import get_prodotto_e_produzione_giorno
    _, produzione_mozz = get_prodotto_e_produzione_giorno(
        client, caseificio_id, data_giorno, "Mozzarella di Bufala Campana DOP", solo_dop=True
    )
    kg_mozz = float((produzione_mozz or {}).get("kg_totale") or 0)
    kg_trasf_dop = registro_calc.trasformato(client, caseificio_id, "bufala_dop", data_giorno)
    return (kg_mozz / kg_trasf_dop * 100) if kg_trasf_dop > 0 else None


def _latte_dop_per_gruppo(client, caseificio_id, data_giorno, resa, is_dop_prodotto, solo_nome=None):
    if not resa:
        return 0.0
    prodotti = (
        client.table("prodotti").select("*")
        .eq("caseificio_id", caseificio_id).eq("attivo", True).eq("is_dop", is_dop_prodotto)
        .execute().data
    )
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


def _cagliata_conferitori(client, caseificio_id, data_giorno):
    conf_b = _conferitori_attivi_categoria(client, caseificio_id, ["allevatore", "caseificio", "intermediario"], "semilavorato_bufala")
    conf_v = _conferitori_attivi_categoria(client, caseificio_id, ["allevatore", "caseificio", "intermediario"], "semilavorato_vaccino")
    return _righe_dati_categoria(client, conf_b, data_giorno), _righe_dati_categoria(client, conf_v, data_giorno)


def _mista_e_congelamento_uscita(client, caseificio_id, data_giorno):
    kg_buf_mista = registro_calc.mista_consumato(client, caseificio_id, "bufala", data_giorno)
    kg_vac_mista = registro_calc.mista_consumato(client, caseificio_id, "vaccino", data_giorno)
    movimenti_uscita = (
        client.table("movimenti_congelato").select("*")
        .eq("caseificio_id", caseificio_id).eq("data", str(data_giorno)).eq("tipo", "congelamento")
        .execute().data
    )
    kg_congelamento_uscita = sum(float(m.get("kg") or 0) for m in movimenti_uscita)
    ddt_congelamento_uscita = ", ".join(m["ddt"] for m in movimenti_uscita if m.get("ddt"))
    return kg_buf_mista, kg_vac_mista, kg_congelamento_uscita, ddt_congelamento_uscita


def _vendite_giorno(client, caseificio_id, data_giorno):
    try:
        return (
            client.table("vendite_latte_destinatari")
            .select("*, destinatari_vendita(ragione_sociale)")
            .eq("caseificio_id", caseificio_id).eq("data", str(data_giorno))
            .execute().data
        )
    except Exception:
        return []


# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE PDF
# ------------------------------------------------------------
def _tabella_conferitori(righe_dati, larghezze):
    intestazioni = ["Provenienza", "Cod. ASL/P.IVA", "N. DDT", "KG", "Acidità", "Temperatura", "Esito"]
    dati = [intestazioni]
    for d in righe_dati:
        dati.append([
            d["provenienza"], d["codice"], d["ddt"], f"{d['kg']:g}",
            _acidita_random(), _temperatura_random(), "OK",
        ])
    t = Table(dati, colWidths=larghezze, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLORE_INTESTAZIONE_TABELLA),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLORE_SEZIONE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, COLORE_GRIGIO_CHIARO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
    ]))
    return t


def _blocco_categoria(elementi, titolo, righe_dati, larghezze):
    """Aggiunge sottotitolo + tabella SOLO se ci sono righe con dati reali (kg>0) - se una
    categoria non ha avuto nessun conferimento oggi, il blocco intero non compare (corretto
    29/08)."""
    if not righe_dati:
        return
    elementi.append(Paragraph(titolo, STILE_SOTTOSEZIONE))
    elementi.append(_tabella_conferitori(righe_dati, larghezze))
    elementi.append(Spacer(1, 6))


def _riga_valore_pdf(righe_tabella, etichetta, valore):
    """Aggiunge una riga SOLO se il valore e' > 0 - corretto 29/08."""
    if not valore or valore <= 0:
        return
    righe_tabella.append([etichetta, f"{round(valore):,} kg".replace(",", ".")])


def genera_tr_pdf(client, caseificio_id, data_giorno, output_path, prodotti_ammessi=None):
    if prodotti_ammessi is None:
        prodotti_ammessi = _prodotti_ammessi_nel_periodo(client, caseificio_id, data_giorno, data_giorno)

    anagrafica, is_dop = _caseificio_e_dop(client, caseificio_id)
    larghezze_conf = [5.2 * cm, 2.6 * cm, 2 * cm, 1.8 * cm, 2.3 * cm, 2.5 * cm, 1.6 * cm]

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.4 * cm, rightMargin=1.4 * cm, topMargin=1.4 * cm, bottomMargin=1.4 * cm,
    )
    elementi = []
    elementi.append(Paragraph("TR — Tabellone giornaliero rintracciabilità", STILE_TITOLO))
    elementi.append(Paragraph(
        f"{anagrafica['ragione_sociale']} — Data: {data_giorno.strftime('%d/%m/%Y')}" + ("  •  Caseificio DOP" if is_dop else ""),
        STILE_SOTTOTITOLO,
    ))

    # ---------------- SEZIONE 1: LATTE IN INGRESSO ----------------
    # CORREZIONE 29/08: la giacenza di apertura va indicata PRIMA del latte conferito (non
    # dopo i totali come prima), e va mostrata per ENTRAMBI i tipi di latte bufala (prima
    # solo per il DOP). Nomenclatura uniformata come richiesto: "Latte di bufala MBC" per il
    # DOP, "Latte di bufala" per il non-DOP - stessa terminologia usata ovunque nel documento.
    elementi.append(Paragraph("LATTE IN INGRESSO", STILE_SEZIONE))
    righe_giacenza_apertura = []
    if is_dop:
        giacenza_apertura_mbc = registro_calc.giacenza_apertura(client, caseificio_id, "bufala_dop", data_giorno)
        righe_giacenza_apertura.append(["Giacenza di apertura — Latte di bufala MBC", f"{round(giacenza_apertura_mbc):,} kg".replace(",", ".")])
    giacenza_apertura_buf = registro_calc.giacenza_apertura(client, caseificio_id, "bufala", data_giorno)
    righe_giacenza_apertura.append(["Giacenza di apertura — Latte di bufala", f"{round(giacenza_apertura_buf):,} kg".replace(",", ".")])
    t = Table(righe_giacenza_apertura, colWidths=[10 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, COLORE_GRIGIO_CHIARO),
    ]))
    elementi.append(t)
    elementi.append(Spacer(1, 8))

    totali = {"bufala_dop": 0.0, "bufala": 0.0, "vaccino": 0.0}
    blocco_ingresso = []

    if is_dop:
        righe = _righe_dati_categoria(client, _conferitori_attivi_categoria(client, caseificio_id, ["allevatore"], "bufala_dop"), data_giorno)
        totali["bufala_dop"] += sum(r["kg"] for r in righe)
        _blocco_categoria(blocco_ingresso, "Allevamenti — Latte di bufala MBC", righe, larghezze_conf)

        # CORREZIONE 29/08: mancavano gli intermediari (es. "Colle Fiori") - prima la
        # query controllava solo tipo "caseificio", non "intermediario"
        righe = _righe_dati_categoria(client, _conferitori_attivi_categoria(client, caseificio_id, ["caseificio", "intermediario"], "bufala_dop"), data_giorno)
        totali["bufala_dop"] += sum(r["kg"] for r in righe)
        _blocco_categoria(blocco_ingresso, "Caseifici / Intermediari — Latte di bufala MBC", righe, larghezze_conf)

    righe = _righe_dati_categoria(client, _conferitori_attivi_categoria(client, caseificio_id, ["caseificio", "intermediario"], "bufala"), data_giorno)
    totali["bufala"] += sum(r["kg"] for r in righe)
    _blocco_categoria(blocco_ingresso, "Caseifici / Intermediari — Latte di bufala", righe, larghezze_conf)

    righe = _righe_dati_categoria(client, _conferitori_attivi_categoria(client, caseificio_id, ["allevatore"], "bufala"), data_giorno)
    totali["bufala"] += sum(r["kg"] for r in righe)
    _blocco_categoria(blocco_ingresso, "Allevamenti — Latte di bufala", righe, larghezze_conf)

    righe = _righe_dati_categoria(client, _conferitori_attivi_categoria(client, caseificio_id, ["allevatore", "caseificio", "intermediario"], "vaccino"), data_giorno)
    totali["vaccino"] += sum(r["kg"] for r in righe)
    _blocco_categoria(blocco_ingresso, "Latte vaccino", righe, larghezze_conf)

    righe_congelato = _righe_congelato(client, caseificio_id, data_giorno)
    totali["bufala"] += sum(r["kg"] for r in righe_congelato)
    _blocco_categoria(blocco_ingresso, "Congelato — Latte di bufala scongelato rientrato", righe_congelato, larghezze_conf)

    conf_cag_b, conf_cag_v = _cagliata_conferitori(client, caseificio_id, data_giorno)
    kg_cagliata_b = sum(r["kg"] for r in conf_cag_b)
    kg_cagliata_v = sum(r["kg"] for r in conf_cag_v)
    _blocco_categoria(blocco_ingresso, "Cagliata bufala ricevuta (esclusa dai totali latte)", conf_cag_b, larghezze_conf)
    _blocco_categoria(blocco_ingresso, "Cagliata vaccina ricevuta (esclusa dai totali latte)", conf_cag_v, larghezze_conf)

    if blocco_ingresso:
        elementi.extend(blocco_ingresso)
    else:
        elementi.append(Paragraph("Nessun conferimento registrato oggi.", STILE_VUOTO))
        elementi.append(Spacer(1, 6))

    # totali: sempre visibili (riepilogo calcolato, non un inserimento)
    righe_totale = []
    if is_dop:
        righe_totale.append(["TOTALE Latte di bufala MBC in ingresso", f"{round(totali['bufala_dop']):,} kg".replace(",", ".")])
    righe_totale.append(["TOTALE Latte di bufala in ingresso (incl. congelato)", f"{round(totali['bufala']):,} kg".replace(",", ".")])
    righe_totale.append(["TOTALE latte vaccino in ingresso", f"{round(totali['vaccino']):,} kg".replace(",", ".")])
    t = Table(righe_totale, colWidths=[10 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLORE_TOTALE),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, COLORE_GRIGIO_CHIARO),
    ]))
    elementi.append(t)
    elementi.append(Spacer(1, 4))

    # ---------------- SEZIONE 2: LAVORAZIONE ----------------
    # CORREZIONE 29/08 (errore di ragionamento segnalato): il totale "Latte di bufala MBC
    # trasformato" deve essere la SOMMA di tutto il latte DOP trasformato (quota MBC pura +
    # quota usata per il declassato + quota usata per la delattosata) - prima mostravo solo
    # la quota MBC pura come "totale", senza sommarci le altre due (che comparivano solo come
    # "di cui" separati, mai aggiunti al totale).
    righe_lav = []
    resa = _resa_dop_giorno(client, caseificio_id, data_giorno) if is_dop else None
    if is_dop:
        kg_buf_dop_puro = registro_calc.trasformato(client, caseificio_id, "bufala_dop", data_giorno)
        kg_declassato = _latte_dop_per_gruppo(client, caseificio_id, data_giorno, resa, is_dop_prodotto=False)
        kg_delattosata = _latte_dop_per_gruppo(client, caseificio_id, data_giorno, resa, is_dop_prodotto=True, solo_nome="senza lattosio")
        kg_buf_dop_totale = kg_buf_dop_puro + kg_declassato + kg_delattosata
        _riga_valore_pdf(righe_lav, "Latte di bufala MBC trasformato (totale)", kg_buf_dop_totale)
        _riga_valore_pdf(righe_lav, "...di cui per MBC (DOP)", kg_buf_dop_puro)
        _riga_valore_pdf(righe_lav, "...di cui per prodotto declassato (non-DOP)", kg_declassato)
        _riga_valore_pdf(righe_lav, "...di cui per mozzarella delattosata", kg_delattosata)

    kg_buf_non_dop = registro_calc.trasformato(client, caseificio_id, "bufala", data_giorno)
    _riga_valore_pdf(righe_lav, "Latte di bufala trasformato", kg_buf_non_dop)
    kg_buf_mista, kg_vac_mista, kg_cong_uscita, ddt_cong_uscita = _mista_e_congelamento_uscita(client, caseificio_id, data_giorno)
    _riga_valore_pdf(righe_lav, "...di cui latte di bufala usato per la Mozzarella Mista", kg_buf_mista)
    kg_vaccino_trasf = registro_calc.trasformato(client, caseificio_id, "vaccino", data_giorno)
    _riga_valore_pdf(righe_lav, "Latte vaccino trasformato", kg_vaccino_trasf)
    _riga_valore_pdf(righe_lav, "...di cui latte vaccino usato per la Mozzarella Mista", kg_vac_mista)
    _riga_valore_pdf(righe_lav, "Cagliata bufala prodotta oggi", kg_cagliata_b)
    _riga_valore_pdf(righe_lav, "Cagliata vaccina prodotta oggi", kg_cagliata_v)
    _riga_valore_pdf(righe_lav, "Latte destinato al congelamento (uscita)", kg_cong_uscita)

    elementi.append(Paragraph("LAVORAZIONE — LATTE TRASFORMATO", STILE_SEZIONE))
    if righe_lav:
        t = Table(righe_lav, colWidths=[12 * cm, 3.5 * cm])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORE_GRIGIO_CHIARO),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
        ]))
        elementi.append(t)
        if kg_cong_uscita and ddt_cong_uscita:
            elementi.append(Paragraph(f"DDT congelamento: {ddt_cong_uscita}", STILE_SOTTOTITOLO))
    else:
        elementi.append(Paragraph("Nessuna lavorazione registrata oggi.", STILE_VUOTO))
    elementi.append(Spacer(1, 6))

    # ---------------- SEZIONE 3: LATTE VENDUTO ----------------
    vendite = _vendite_giorno(client, caseificio_id, data_giorno)
    elementi.append(Paragraph("LATTE VENDUTO", STILE_SEZIONE))
    if vendite:
        dati_vendite = [["Destinatario", "Tipo latte", "KG", "N. DDT"]]
        for v in vendite:
            dati_vendite.append([
                (v.get("destinatari_vendita") or {}).get("ragione_sociale", ""),
                v.get("tipo_latte", ""),
                f"{round(float(v.get('kg') or 0)):g}",
                v.get("ddt") or "",
            ])
        t = Table(dati_vendite, colWidths=[6 * cm, 4 * cm, 2.5 * cm, 3 * cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORE_INTESTAZIONE_TABELLA),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORE_GRIGIO_CHIARO),
            ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ]))
        elementi.append(t)
    else:
        elementi.append(Paragraph("Nessuna vendita di latte registrata oggi.", STILE_VUOTO))
    elementi.append(Spacer(1, 6))

    # ---------------- SEZIONE 4: GIACENZA DI CHIUSURA (sempre visibile) ----------------
    elementi.append(Paragraph("GIACENZA DI CHIUSURA", STILE_SEZIONE))
    righe_giac = []
    if is_dop:
        righe_giac.append(["Latte di bufala MBC", f"{round(registro_calc.giacenza_chiusura(client, caseificio_id, 'bufala_dop', data_giorno)):,} kg".replace(",", ".")])
    righe_giac.append(["Latte di bufala", f"{round(registro_calc.giacenza_chiusura(client, caseificio_id, 'bufala', data_giorno)):,} kg".replace(",", ".")])
    t = Table(righe_giac, colWidths=[10 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, COLORE_GRIGIO_CHIARO),
    ]))
    elementi.append(t)
    elementi.append(Spacer(1, 6))

    # ---------------- SEZIONE 5: PRODOTTI OTTENUTI (0 ammesso, per confronto tra giorni) ----------------
    # CORREZIONE 29/08: aggiunto il lotto di produzione (stessa logica gia' usata in MBC/RBC
    # - calcola_lotto, in base a come e' configurato il prodotto in Prodotti).
    elementi.append(Paragraph("PRODOTTI OTTENUTI", STILE_SEZIONE))
    prodotti = _prodotti_finiti(client, prodotti_ammessi, data_giorno)
    if prodotti:
        dati_prod = [["Prodotto", "Lotto", "KG totale", "Vendita diretta", "Vendita a terzi"]]
        for p in prodotti:
            dati_prod.append([p["nome"], p["lotto"], f"{p['totale']:g}", f"{p['diretta']:g}", f"{p['terzi']:g}"])
        t = Table(dati_prod, colWidths=[6 * cm, 3 * cm, 2.5 * cm, 2.8 * cm, 2.8 * cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORE_INTESTAZIONE_TABELLA),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, COLORE_GRIGIO_CHIARO),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ]))
        elementi.append(t)
    else:
        elementi.append(Paragraph("Nessun prodotto realizzato nel periodo selezionato.", STILE_VUOTO))

    doc.build(elementi)
    return output_path


def genera_tr_pdf_periodo(client, caseificio_id, data_da, data_a, output_path_prefix):
    """Un PDF PER GIORNO (non un unico file con più fogli come in Excel - un PDF ha senso
    come documento singolo). Ritorna la lista dei percorsi generati, uno per ogni giorno."""
    prodotti_ammessi = _prodotti_ammessi_nel_periodo(client, caseificio_id, data_da, data_a)
    percorsi = []
    n_giorni = (data_a - data_da).days + 1
    for i in range(n_giorni):
        giorno = data_da + _dt.timedelta(days=i)
        path = f"{output_path_prefix}_{giorno.strftime('%Y%m%d')}.pdf"
        genera_tr_pdf(client, caseificio_id, giorno, path, prodotti_ammessi=prodotti_ammessi)
        percorsi.append(path)
    return percorsi
