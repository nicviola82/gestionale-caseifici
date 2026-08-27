# ============================================================
# PAGINA: REGISTRO
# Struttura identica al foglio Excel di riferimento:
# LATTE REFRIGERATO | LATTE RITIRATO | LATTE TRASFORMATO |
# MOZZARELLA PRODOTTA | RESA | LATTE CONGELATO E VENDUTO
# Colonne abbreviate per stare a schermo. Solo tabelle.
# ============================================================
import streamlit as st
import pandas as pd
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Registro", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Registro")
mostra_header_caseificio()

caseificio_id = st.session_state.get("caseificio_id")
periodo_inizio = st.session_state.get("periodo_inizio")
periodo_fine = st.session_state.get("periodo_fine")

if not caseificio_id or not periodo_inizio:
    st.info("Seleziona caseificio e periodo dalla pagina principale prima di continuare.")
    st.stop()

st.caption(f"Periodo: {st.session_state.get('periodo_label')}")

n_giorni = (periodo_fine - periodo_inizio).days + 1
date_periodo = [periodo_inizio + _dt.timedelta(days=i) for i in range(n_giorni)]

# ------------------------------------------------------------
# BLOCCO: DATI CASEIFICIO (quali tipi di latte usa)
# ------------------------------------------------------------
conferitori_tutti = (
    client.table("conferitori")
    .select("id, tipo, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .execute()
    .data
)
tipo_per_conferitore = {
    c["id"]: [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]
    for c in conferitori_tutti
}
# conferitori di tipo "congelatore": il RITIRO del latte da questi conta come Ritirato
# Bufala normale (stesso bucket, niente categoria a parte) - serve pero' tenerne traccia
# a parte per sapere quanto della giacenza bufala "di ritorno dal congelatore".
congelatore_ids = {c["id"] for c in conferitori_tutti if c["tipo"] == "congelatore"}
tutti_tipi = {t for tipi in tipo_per_conferitore.values() for t in tipi}

usa_dop = "bufala_dop" in tutti_tipi
usa_buf = "bufala" in tutti_tipi or "bufala_congelato" in tutti_tipi
usa_vacc = "vaccino" in tutti_tipi or "vaccino_congelato" in tutti_tipi
usa_sem_buf = "semilavorato_bufala" in tutti_tipi
usa_sem_vacc = "semilavorato_vaccino" in tutti_tipi

movimenti_tutti = (
    client.table("movimenti_congelato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
if any(m["tipo"] == "scongelamento" for m in movimenti_tutti):
    usa_buf = True

# ------------------------------------------------------------
# BLOCCO: PRODOTTI ATTIVI
# ------------------------------------------------------------
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
prodotto_primario_dop = next((p for p in prodotti if p["is_dop"] and p.get("stabilisce_resa")), None)

# mozzarella declassata = prodotti non-DOP famiglia bufala (no mista/vaccina)
def e_mista(p): return "mista" in p["nome"].lower()
def e_vaccina(p): return "vaccin" in p["nome"].lower() and "mista" not in p["nome"].lower()
def e_congelato(p): return "congelat" in p["nome"].lower()
def e_cagliata(p): return "cagliata" in p["nome"].lower() or "semilav" in p["nome"].lower()
def e_cagliata_bufala(p): return e_cagliata(p) and "vaccin" not in p["nome"].lower()
def e_cagliata_vaccina(p): return e_cagliata(p) and "vaccin" in p["nome"].lower()
def e_declassata(p):
    return (not p["is_dop"] and not e_mista(p) and not e_vaccina(p)
            and not e_congelato(p) and not e_cagliata(p)
            and p is not prodotto_primario_dop)

prodotti_dop_altri = [p for p in prodotti if p["is_dop"] and p is not prodotto_primario_dop]
prodotti_declassati = [p for p in prodotti if e_declassata(p)]
prodotti_mista = [p for p in prodotti if e_mista(p)]
prodotti_vaccina = [p for p in prodotti if e_vaccina(p)]
prodotti_cong = [p for p in prodotti if e_congelato(p)]
prodotti_cagliata = [p for p in prodotti if e_cagliata(p)]

prodotto_ids = [p["id"] for p in prodotti]

# ------------------------------------------------------------
# BLOCCO: CARICA DATI STORICI (per giacenza corretta)
# ------------------------------------------------------------
conferimenti_tutti = (
    client.table("conferimenti")
    .select("*")
    .in_("conferitore_id", list(tipo_per_conferitore.keys()))
    .lte("data", str(periodo_fine))
    .execute()
    .data
) if tipo_per_conferitore else []

trasformato_storia = (
    client.table("trasformato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
trasformato_map = {(t["tipo_latte"], t["data"]): float(t["kg"] or 0) for t in trasformato_storia}

venduto_storia = (
    client.table("latte_venduto")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
venduto_map = {}
for v in venduto_storia:
    venduto_map[(v["tipo_latte"], v["data"])] = venduto_map.get((v["tipo_latte"], v["data"]), 0) + float(v["kg"] or 0)

congelato_map = {}
raccolto = {}
raccolto_da_congelatore_buf = {}  # sotto-quota di raccolto[("bufala", data)] che viene da un
                                    # conferitore di tipo "congelatore" (ritiro di latte tornato
                                    # dal congelamento) - usata per il calcolo proporzionale sotto
for cf in conferimenti_tutti:
    tipi = tipo_per_conferitore.get(cf["conferitore_id"], [])
    kg = float(cf.get("kg") or 0)
    if kg <= 0: continue
    for t in tipi:
        if t in ("bufala_dop", "bufala", "vaccino", "semilavorato_bufala", "semilavorato_vaccino"):
            raccolto[(t, cf["data"])] = raccolto.get((t, cf["data"]), 0) + kg
            if t == "bufala" and cf["conferitore_id"] in congelatore_ids:
                raccolto_da_congelatore_buf[cf["data"]] = raccolto_da_congelatore_buf.get(cf["data"], 0) + kg
for m in movimenti_tutti:
    if m["tipo"] == "scongelamento":
        # NOTA: dati storici da prima della correzione (22/08) - il ritiro dal congelatore ora si
        # inserisce nella normale griglia conferimenti di Dati Inseriti, non più qui - questo blocco
        # resta solo per non perdere/rompere eventuali movimenti già registrati in passato.
        raccolto[("bufala", m["data"])] = raccolto.get(("bufala", m["data"]), 0) + float(m["kg"])
        raccolto_da_congelatore_buf[m["data"]] = raccolto_da_congelatore_buf.get(m["data"], 0) + float(m["kg"])
    elif m["tipo"] == "congelamento":
        orig = m.get("origine") or "bufala"
        congelato_map[(orig, m["data"])] = congelato_map.get((orig, m["data"]), 0) + float(m["kg"])

produzioni_storia = (
    client.table("produzioni")
    .select("*")
    .in_("prodotto_id", prodotto_ids)
    .lte("data", str(periodo_fine))
    .execute()
    .data
) if prodotto_ids else []
prod_map = {(e["prodotto_id"], e["data"]): e for e in produzioni_storia}

# extra consumo DOP per i prodotti derivati (inclusi altri DOP es. senza lattosio)
# calcolato su TUTTA LA STORIA (non solo il periodo aperto), altrimenti la giacenza
# di apertura di un nuovo periodo risulterebbe sbagliata
origini_m = {}
for o in (client.table("produzione_origine").select("*").in_("produzione_id", [r["id"] for r in produzioni_storia]).execute().data if produzioni_storia else []):
    origini_m.setdefault(o["produzione_id"], {})[o["origine"]] = o

def resa_dop_giorno(ds):
    if not prodotto_primario_dop: return None
    rec = prod_map.get((prodotto_primario_dop["id"], ds))
    prod = float(rec["kg_totale"]) if rec else 0
    trasf = trasformato_map.get(("bufala_dop", ds), 0)
    return (prod / trasf) if trasf > 0 else None

consumo_extra_dop = {}
# ATTENZIONE: la Ricotta DOP va ESCLUSA da questo calcolo generico - ha una
# logica di consumo latte a parte (blocco RICOTTA piu' sotto, che scala dal
# bucket bufala NON-DOP solo se impostata una percentuale in Impostazioni
# Fisse). Includerla anche qui la conterebbe due volte e scalerebbe latte
# bufala_dop che la Ricotta normalmente non consuma (si fa dal siero).
prodotti_dop_altri_no_ricotta = [p for p in prodotti_dop_altri if "ricotta" not in p["nome"].lower()]
for p in prodotti_dop_altri_no_ricotta + prodotti_declassati:
    for (prodotto_id, ds), rec in prod_map.items():
        if prodotto_id != p["id"]: continue
        tot = float(rec["kg_totale"] or 0)
        if tot <= 0: continue
        ov = origini_m.get(rec["id"], {}).get("non_dop")
        kg_nondop = float(ov["kg"]) if ov and ov.get("kg") else 0.0
        kg_dop = tot - kg_nondop
        if kg_dop > 0:
            r = resa_dop_giorno(ds)
            if r and r > 0:
                consumo_extra_dop[("bufala_dop", ds)] = consumo_extra_dop.get(("bufala_dop", ds), 0) + kg_dop / r

# ------------------------------------------------------------
# BLOCCO: MOZZARELLA MISTA -> CONSUMO LATTE BUFALA E VACCINO
# La Mozzarella Mista si fa mescolando latte di bufala E latte vaccino nella
# stessa lavorazione. L'utente inserisce ogni giorno quanto latte di CIASCUN
# tipo è entrato in quella lavorazione (colonne Mis.<nome>Buf / Mis.<nome>Vac
# nella tabella) e quella quota va sottratta dal refrigerato del tipo
# corrispondente (aggiunto 27/08 su richiesta utente - prima il latte per la
# mista non veniva scalato da nessuna giacenza).
# RICHIEDE la migrazione che aggiunge 'bufala'/'vaccino' ai valori ammessi
# della colonna produzione_origine.origine (vedi messaggio di consegna).
# Calcolato su TUTTA LA STORIA, stesso motivo del consumo extra DOP sopra.
# ------------------------------------------------------------
consumo_mista_buf = {}
consumo_mista_vacc = {}
for p in prodotti_mista:
    for (prodotto_id, ds), rec in prod_map.items():
        if prodotto_id != p["id"]: continue
        ov_b = origini_m.get(rec["id"], {}).get("bufala")
        kg_b = float(ov_b["kg"]) if ov_b and ov_b.get("kg") else 0.0
        if kg_b > 0:
            consumo_mista_buf[ds] = consumo_mista_buf.get(ds, 0) + kg_b
        ov_v = origini_m.get(rec["id"], {}).get("vaccino")
        kg_v = float(ov_v["kg"]) if ov_v and ov_v.get("kg") else 0.0
        if kg_v > 0:
            consumo_mista_vacc[ds] = consumo_mista_vacc.get(ds, 0) + kg_v

# ------------------------------------------------------------
# BLOCCO: RICOTTA (DOP e NON-DOP) -> CONSUMO LATTE BUFALA (SOLO SE IMPOSTATO)
# Di regola la Ricotta (DOP o non-DOP) NON entra nel conteggio latte (si fa
# con il siero, un sottoprodotto già contato altrove tramite il foglio Siero).
# ECCEZIONE: se in Impostazioni Fisse è indicata una percentuale di latte di
# bufala aggiunto alla ricotta, quella quota è latte VERO consumato e va
# scalata dalla giacenza bufala come un'uscita, esattamente come un
# trasformato. Due impostazioni distinte, stesso bucket di destinazione:
#   - perc_latte_bufala_rbc            -> per la Ricotta di Bufala Campana DOP
#   - perc_latte_bufala_ricotta_nondop -> per la Ricotta di bufala NON-DOP
#     (aggiunta 27/08 su richiesta utente: prima esisteva solo per la DOP)
# NOTA: entrambe scalano dal bucket "bufala" non-DOP (non bufala_dop), perché
# il latte aggiunto è genericamente "latte di bufala" fresco, non DOP.
# NOTA PRESTAZIONI: poche query TOTALI per l'intero periodo (mai una query per
# ogni singolo giorno, che su un periodo lungo renderebbe la pagina lentissima
# - stesso principio già seguito in siero.py).
# ------------------------------------------------------------
tipi_giac = ["bufala_dop", "bufala", "vaccino", "semilavorato_bufala", "semilavorato_vaccino"]
tutte_le_date = sorted(set(
    [d for (_, d) in raccolto.keys()] + [d for (_, d) in trasformato_map.keys()]
    + [d for (_, d) in venduto_map.keys()] + [str(d) for d in date_periodo]
))

def carica_perc_storico(campo):
    return (
        client.table("impostazioni_registro")
        .select("data_da, valore")
        .eq("caseificio_id", caseificio_id)
        .eq("campo", campo)
        .order("data_da")
        .execute()
        .data
    )

def perc_alla_data(storico, data_str):
    valore = 0.0
    for r in storico:
        if r["data_da"] <= data_str:
            try:
                valore = float(r["valore"])
            except (TypeError, ValueError):
                valore = 0.0
        else:
            break
    return valore

perc_bufala_rbc_storico = carica_perc_storico("perc_latte_bufala_rbc")
perc_bufala_ricotta_nondop_storico = carica_perc_storico("perc_latte_bufala_ricotta_nondop")

ricotta_dop_prodotti = (
    client.table("prodotti")
    .select("id, resa_automatica_percent")
    .eq("caseificio_id", caseificio_id)
    .eq("is_dop", True)
    .ilike("nome", "%Ricotta di Bufala Campana DOP%")
    .execute()
    .data
)
ricotta_nondop_prodotti = (
    client.table("prodotti")
    .select("id, resa_automatica_percent")
    .eq("caseificio_id", caseificio_id)
    .eq("is_dop", False)
    .ilike("nome", "%ricotta%")
    .execute()
    .data
)

def kg_prodotto_per_giorno(prodotti_list):
    if not prodotti_list:
        return {}
    ids = [p["id"] for p in prodotti_list]
    out = {}
    for r in (
        client.table("produzioni").select("data, kg_totale").in_("prodotto_id", ids)
        .gte("data", str(periodo_inizio)).lte("data", str(periodo_fine)).execute().data
    ):
        out[r["data"]] = out.get(r["data"], 0) + float(r["kg_totale"] or 0)
    return out

def resa_media(prodotti_list):
    rese = [float(p["resa_automatica_percent"]) for p in prodotti_list if p.get("resa_automatica_percent")]
    return (sum(rese) / len(rese)) if rese else None

ricotta_dop_per_giorno = kg_prodotto_per_giorno(ricotta_dop_prodotti)
ricotta_nondop_per_giorno = kg_prodotto_per_giorno(ricotta_nondop_prodotti)
resa_ricotta_dop = resa_media(ricotta_dop_prodotti)
resa_ricotta_nondop = resa_media(ricotta_nondop_prodotti)

ricotta_bufala_map = {}
for d in tutte_le_date:
    tot_oggi = 0.0
    if resa_ricotta_dop:
        perc = perc_alla_data(perc_bufala_rbc_storico, d)
        kg_oggi = ricotta_dop_per_giorno.get(d, 0)
        if perc > 0 and kg_oggi > 0:
            tot_oggi += perc / 100 * (kg_oggi / (resa_ricotta_dop / 100))
    if resa_ricotta_nondop:
        perc = perc_alla_data(perc_bufala_ricotta_nondop_storico, d)
        kg_oggi = ricotta_nondop_per_giorno.get(d, 0)
        if perc > 0 and kg_oggi > 0:
            tot_oggi += perc / 100 * (kg_oggi / (resa_ricotta_nondop / 100))
    if tot_oggi > 0:
        ricotta_bufala_map[d] = round(tot_oggi)

# giacenza (apertura giorno = chiusura giorno precedente)
# REGOLA ARROTONDAMENTO: ogni componente (entrata/uscita) va arrotondato a intero
# PRIMA di essere sommato o sottratto, e la giacenza cumulativa risultante resta
# sempre un intero passo dopo passo - non si accumula in decimali per poi
# arrotondare solo in visualizzazione, altrimenti gli arrotondamenti si sommano
# in modo scorretto lungo il periodo.
giacenza_per_tipo = {t: 0 for t in tipi_giac}
giacenza_per_giorno = {}
for d in tutte_le_date:
    for t in tipi_giac:
        giacenza_per_giorno[(t, d)] = giacenza_per_tipo[t]
        entrata = round(raccolto.get((t, d), 0))
        uscita = round(
            trasformato_map.get((t, d), 0)
            + consumo_extra_dop.get((t, d), 0)
            + venduto_map.get((t, d), 0)
            + congelato_map.get((t if t in ("bufala_dop", "bufala") else "bufala", d), 0) * (1 if t in ("bufala_dop", "bufala") else 0)
            + (ricotta_bufala_map.get(d, 0) if t == "bufala" else 0)
            + (consumo_mista_buf.get(d, 0) if t == "bufala" else 0)
            + (consumo_mista_vacc.get(d, 0) if t == "vaccino" else 0)
        )
        giacenza_per_tipo[t] = giacenza_per_tipo[t] + entrata - uscita

# chiusura dell'ultimo giorno del periodo selezionato (richiesta utente 27/08:
# la tabella mostra l'APERTURA di ogni giorno - serve anche vedere la
# CHIUSURA dell'ultimo giorno, cioè la giacenza "a fine periodo")
giacenza_chiusura_periodo = dict(giacenza_per_tipo)

# ------------------------------------------------------------
# BLOCCO: QUOTA "EX-CONGELATO" DENTRO LA GIACENZA BUFALA
# Non teniamo lotti separati (un'unica giacenza cumulativa di bufala), quindi la
# quota di provenienza congelata si segue con una sotto-giacenza PROPORZIONALE:
# entra quando c'è un ritiro dal congelatore, esce nella stessa proporzione in cui
# esce il resto della giacenza bufala quel giorno (trasformato + venduto + congelato).
# Serve per rispondere a "quanto del Trasformato Bufala di oggi viene dal congelato".
# Stessa regola di arrotondamento: intero ad ogni passaggio, non solo alla fine.
# ------------------------------------------------------------
giacenza_congelata_buf = 0
giacenza_congelata_apertura = {}
for d in tutte_le_date:
    giacenza_congelata_apertura[d] = giacenza_congelata_buf
    entrata_c = round(raccolto_da_congelatore_buf.get(d, 0))
    giac_tot_apertura = giacenza_per_giorno.get(("bufala", d), 0)
    uscita_tot = round(
        trasformato_map.get(("bufala", d), 0)
        + venduto_map.get(("bufala", d), 0)
        + congelato_map.get(("bufala", d), 0)
    )
    quota = (giacenza_congelata_buf / giac_tot_apertura) if giac_tot_apertura > 0 else 0.0
    uscita_c = round(uscita_tot * quota)
    giacenza_congelata_buf = giacenza_congelata_buf + entrata_c - uscita_c

# ------------------------------------------------------------
# BLOCCO: CARICA DATI PERIODO PER TABELLA EDITABILE
# ------------------------------------------------------------
trasf_periodo = {(t["tipo_latte"], t["data"]): float(t["kg"] or 0) for t in (
    client.table("trasformato").select("*").eq("caseificio_id", caseificio_id)
    .gte("data", str(periodo_inizio)).lte("data", str(periodo_fine)).execute().data
)}
vend_periodo = {}
for v in (client.table("latte_venduto").select("*").eq("caseificio_id", caseificio_id)
          .gte("data", str(periodo_inizio)).lte("data", str(periodo_fine)).execute().data):
    vend_periodo[(v["tipo_latte"], v["data"])] = vend_periodo.get((v["tipo_latte"], v["data"]), 0) + float(v["kg"] or 0)
cong_periodo = {}
for m in movimenti_tutti:
    if m["data"] < str(periodo_inizio) or m["data"] > str(periodo_fine): continue
    if m["tipo"] == "congelamento":
        orig = m.get("origine") or "bufala"
        cong_periodo[(orig, m["data"])] = cong_periodo.get((orig, m["data"]), 0) + float(m["kg"])

def kg_prod(p, ds): 
    r = prod_map.get((p["id"], ds))
    return float(r["kg_totale"]) if r and r.get("kg_totale") else 0.0

def kg_nondop(p, ds):
    r = prod_map.get((p["id"], ds))
    if not r: return 0.0
    ov = origini_m.get(r["id"], {}).get("non_dop")
    return float(ov["kg"]) if ov and ov.get("kg") else 0.0

def kg_latte_nondop(p, ds):
    r = prod_map.get((p["id"], ds))
    if not r: return 0.0
    ov = origini_m.get(r["id"], {}).get("non_dop")
    return float(ov["kg_latte"]) if ov and ov.get("kg_latte") else 0.0

def latte_dop_prodotto(p, ds):
    """kg di latte bufala DOP consumato per la quota DOP di un prodotto D./Dec.
    (tot - nD, convertito in latte con la resa MBC del giorno) - lo stesso
    valore già usato in consumo_extra_dop per scalare Ref.MBC, reso visibile."""
    kg_dop = kg_prod(p, ds) - kg_nondop(p, ds)
    if kg_dop <= 0:
        return 0
    r = resa_dop_giorno(ds)
    return round(kg_dop / r) if r and r > 0 else 0

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE TABELLA UNICA
# ------------------------------------------------------------
righe = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m")}

    # REFRIGERATO (sola lettura)
    if usa_dop:  riga["Ref.MBC"]  = round(giacenza_per_giorno.get(("bufala_dop", ds), 0))
    if usa_buf:  riga["Ref.Buf"]  = round(giacenza_per_giorno.get(("bufala", ds), 0))
    if usa_vacc: riga["Ref.Vacc"] = round(giacenza_per_giorno.get(("vaccino", ds), 0))
    if usa_sem_buf:  riga["Ref.SemB"] = round(giacenza_per_giorno.get(("semilavorato_bufala", ds), 0))
    if usa_sem_vacc: riga["Ref.SemV"] = round(giacenza_per_giorno.get(("semilavorato_vaccino", ds), 0))

    # RITIRATO (da Dati Inseriti, sola lettura)
    if usa_dop:  riga["Rit.MBC"]  = round(raccolto.get(("bufala_dop", ds), 0))
    if usa_buf:  riga["Rit.Buf"]  = round(raccolto.get(("bufala", ds), 0))
    if usa_vacc: riga["Rit.Vacc"] = round(raccolto.get(("vaccino", ds), 0))
    if usa_sem_buf:  riga["Rit.SemB"] = round(raccolto.get(("semilavorato_bufala", ds), 0))
    if usa_sem_vacc: riga["Rit.SemV"] = round(raccolto.get(("semilavorato_vaccino", ds), 0))

    # TRASFORMATO (editabile — solo DOP per MBC, no latte non-DOP per prodotti DOP)
    if usa_dop:  riga["Tr.MBC"]   = trasf_periodo.get(("bufala_dop", ds), 0.0)
    if usa_buf:
        tr_buf_oggi = trasf_periodo.get(("bufala", ds), 0.0)
        riga["Tr.Buf"]   = tr_buf_oggi
        # quota "di cui da latte congelato" (calcolo proporzionale sulla giacenza di apertura
        # del giorno, come da conferma dell'utente - non teniamo lotti separati per FIFO)
        giac_tot_ap = giacenza_per_giorno.get(("bufala", ds), 0)
        quota_cong = (giacenza_congelata_apertura.get(ds, 0) / giac_tot_ap) if giac_tot_ap > 0 else 0.0
        riga["Tr.BufCong"] = round(round(tr_buf_oggi) * quota_cong)
        # latte bufala consumato dalla Ricotta quel giorno (solo se impostato in
        # Impostazioni Fisse - vedi blocco RICOTTA -> CONSUMO LATTE BUFALA sopra)
        riga["RBC.Buf"] = ricotta_bufala_map.get(ds, 0)
    if usa_vacc: riga["Tr.Vacc"]  = trasf_periodo.get(("vaccino", ds), 0.0)
    if usa_sem_buf:  riga["Tr.SemB"]  = trasf_periodo.get(("semilavorato_bufala", ds), 0.0)
    if usa_sem_vacc: riga["Tr.SemV"]  = trasf_periodo.get(("semilavorato_vaccino", ds), 0.0)

    # MOZZARELLA PRODOTTA (sola lettura, sincronizzata da Produzioni)
    if prodotto_primario_dop: riga["Mozz.MBC"]  = kg_prod(prodotto_primario_dop, ds)
    for p in prodotti_dop_altri:
        tot = kg_prod(p, ds)
        riga[f"D.{p['nome'][:6]}Tot"] = tot
        riga[f"D.{p['nome'][:6]}nD"] = kg_nondop(p, ds)  # editabile: quota fatta con non-DOP
        riga[f"D.{p['nome'][:6]}dop"] = round(tot - kg_nondop(p, ds), 1)  # resta col DOP (calcolato)
        # kg di LATTE bufala DOP effettivamente consumato per la quota DOP di
        # questo prodotto (tot-nD convertito in latte con la resa del giorno) -
        # sola lettura, mostra il numero già usato per scalare Ref.MBC, prima
        # invisibile in tabella (richiesta utente 27/08)
        riga[f"D.{p['nome'][:6]}LatteDOP"] = latte_dop_prodotto(p, ds)
    for p in prodotti_declassati:
        tot = kg_prod(p, ds)
        riga[f"Dec.{p['nome'][:6]}Tot"] = tot
        riga[f"Dec.{p['nome'][:6]}nD"] = kg_nondop(p, ds)  # editabile: quota fatta con non-DOP
        riga[f"Dec.{p['nome'][:6]}dop"] = round(tot - kg_nondop(p, ds), 1)  # resta col DOP (calcolato)
        riga[f"Dec.{p['nome'][:6]}LatteDOP"] = latte_dop_prodotto(p, ds)
    for p in prodotti_mista:
        base = f"Mis.{p['nome'][:6]}"
        rec = prod_map.get((p["id"], ds))
        riga[f"{base}Tot"] = kg_prod(p, ds)
        ov_b = origini_m.get(rec["id"], {}).get("bufala") if rec else None
        ov_v = origini_m.get(rec["id"], {}).get("vaccino") if rec else None
        riga[f"{base}Buf"] = float(ov_b["kg"]) if ov_b and ov_b.get("kg") else 0.0  # editabile: kg latte bufala usato
        riga[f"{base}Vac"] = float(ov_v["kg"]) if ov_v and ov_v.get("kg") else 0.0  # editabile: kg latte vaccino usato
    for p in prodotti_vaccina:     riga[f"Vac.{p['nome'][:6]}"] = kg_prod(p, ds)
    for p in prodotti_cong:        riga[f"Con.{p['nome'][:6]}"] = kg_prod(p, ds)
    for p in prodotti_cagliata:    riga[f"Cag.{p['nome'][:6]}"] = kg_prod(p, ds)

    # RESA (calcolata, sola lettura)
    r_dop = resa_dop_giorno(ds)
    if usa_dop: riga["R.MBC"] = f"{r_dop*100:.2f}%" if r_dop else "-"
    # BUFALA: mozzarella bufala (declassata) + caciocavallo bufala + cagliata bufala.
    # VACCINO: mozzarella/caciocavallo vaccina + cagliata vaccina.
    # (prima usavano lo stesso identico numeratore per entrambe le rese - bug corretto)
    prodotti_cagliata_buf = [p for p in prodotti_cagliata if e_cagliata_bufala(p)]
    prodotti_cagliata_vacc = [p for p in prodotti_cagliata if e_cagliata_vaccina(p)]
    for label, t, prods in [
        ("R.Buf", "bufala", prodotti_declassati + prodotti_cagliata_buf),
        ("R.Vacc", "vaccino", prodotti_vaccina + prodotti_cagliata_vacc),
    ]:
        if (label == "R.Buf" and usa_buf) or (label == "R.Vacc" and usa_vacc):
            tot_p = sum(kg_prod(p, ds) for p in prods)
            tot_l = trasf_periodo.get((t, ds), 0)
            riga[label] = f"{tot_p/tot_l*100:.2f}%" if tot_l > 0 else "-"

    # LATTE CONGELATO E VENDUTO (editabile)
    if usa_dop:
        riga["MBC.vMBC"]   = vend_periodo.get(("bufala_dop_mbc", ds), 0.0)
        riga["MBC.vBuf"]   = vend_periodo.get(("bufala_dop_nondop", ds), 0.0)
        riga["MBC.Cong"]   = cong_periodo.get(("bufala_dop", ds), 0.0)
    if usa_buf:
        riga["Buf.Cong"]   = cong_periodo.get(("bufala", ds), 0.0)
    riga["CongVend"]       = vend_periodo.get(("bufala_congelato", ds), 0.0)
    if usa_vacc: riga["VaccVend"] = vend_periodo.get(("vaccino", ds), 0.0)

    righe.append(riga)

df = pd.DataFrame(righe)

# ------------------------------------------------------------
# BLOCCO: NASCONDI COLONNE/FAMIGLIE A ZERO NEL PERIODO
# Se un'intera famiglia di colonne (es. tutto il vaccino, o un singolo prodotto)
# risulta a zero in TUTTO il periodo selezionato, non ha senso mostrarla: si
# nasconde solo per QUESTA vista, i dati restano intatti nel database e
# riappaiono da soli se in quel periodo torna a esserci attività.
# ------------------------------------------------------------
def famiglia_azzerata(cols):
    numeriche = [c for c in cols if c in df.columns and not c.startswith("R.")]
    if not numeriche:
        return False
    return all(pd.to_numeric(df[c], errors="coerce").fillna(0).abs().sum() == 0 for c in numeriche)

famiglie = {
    "MBC": [c for c in df.columns if c.startswith("Ref.MBC") or c.startswith("Rit.MBC") or c.startswith("Tr.MBC")
            or c == "Mozz.MBC" or c == "R.MBC" or c.startswith("MBC.")],
    "Buf": [c for c in df.columns if c in ("Ref.Buf", "Rit.Buf", "Tr.Buf", "R.Buf", "Buf.Cong", "Tr.BufCong", "RBC.Buf")],
    "Vacc": [c for c in df.columns if c in ("Ref.Vacc", "Rit.Vacc", "Tr.Vacc", "R.Vacc", "VaccVend")],
    "SemB": [c for c in df.columns if c in ("Ref.SemB", "Rit.SemB", "Tr.SemB")],
    "SemV": [c for c in df.columns if c in ("Ref.SemV", "Rit.SemV", "Tr.SemV")],
    "CongVend": [c for c in df.columns if c == "CongVend"],
}
colonne_da_nascondere = set()
for nome_fam, cols in famiglie.items():
    if cols and famiglia_azzerata(cols):
        colonne_da_nascondere |= set(cols)

# prodotti singoli: stesso principio, un prodotto alla volta (gruppo Tot/nD/dop o colonna unica)
prodotti_gruppi = {}
for p in prodotti_dop_altri:
    base = f"D.{p['nome'][:6]}"
    prodotti_gruppi[base] = [f"{base}Tot", f"{base}nD", f"{base}dop", f"{base}LatteDOP"]
for p in prodotti_declassati:
    base = f"Dec.{p['nome'][:6]}"
    prodotti_gruppi[base] = [f"{base}Tot", f"{base}nD", f"{base}dop", f"{base}LatteDOP"]
for p in prodotti_mista:
    base = f"Mis.{p['nome'][:6]}"
    prodotti_gruppi[base] = [f"{base}Tot", f"{base}Buf", f"{base}Vac"]
for p in prodotti_vaccina:  prodotti_gruppi[f"Vac.{p['nome'][:6]}"] = [f"Vac.{p['nome'][:6]}"]
for p in prodotti_cong:     prodotti_gruppi[f"Con.{p['nome'][:6]}"] = [f"Con.{p['nome'][:6]}"]
for p in prodotti_cagliata: prodotti_gruppi[f"Cag.{p['nome'][:6]}"] = [f"Cag.{p['nome'][:6]}"]

for base, cols in prodotti_gruppi.items():
    cols_presenti = [c for c in cols if c in df.columns]
    if cols_presenti and famiglia_azzerata(cols_presenti):
        colonne_da_nascondere |= set(cols_presenti)

df_completo = df  # tenuto per l'esportazione CSV (che include SEMPRE tutte le colonne, anche quelle nascoste qui)
if colonne_da_nascondere:
    df = df.drop(columns=list(colonne_da_nascondere))
    st.caption(f"({len(colonne_da_nascondere)} colonne nascoste perché a zero in tutto il periodo selezionato — i dati non sono persi, riappaiono da sole se tornano ad esserci valori)")

# colonne editabili (tutto tranne Refrigerato, Ritirato, Resa)
col_readonly = {"Data"}
col_readonly |= {c for c in df.columns if c.startswith("Ref.") or c.startswith("Rit.") or c in ("R.MBC","R.Buf","R.Vacc")}
col_readonly |= {c for c in df.columns if c == "Mozz.MBC" or c.startswith("Vac.") or c.startswith("Con.") or c.startswith("Cag.")}
col_readonly |= {c for c in df.columns if c.startswith("Mis.") and c.endswith("Tot")}
col_readonly |= {c for c in df.columns if c.endswith("Tot") or c.endswith("dop") or c.endswith("LatteDOP")}
col_readonly |= {c for c in df.columns if c == "Tr.BufCong"}
col_readonly |= {c for c in df.columns if c == "RBC.Buf"}

column_config = {"Data": st.column_config.TextColumn("Data", disabled=True, width=60)}
for col in df.columns:
    if col == "Data": continue
    disabled = col in col_readonly
    etichetta = "Tr.Buf\n(di cui congelato)" if col == "Tr.BufCong" else ("Bufala\nusata per RBC" if col == "RBC.Buf" else col)
    column_config[col] = st.column_config.NumberColumn(etichetta, disabled=disabled, min_value=0.0 if not disabled else None, step=1.0 if not disabled else None, width=70) if not col.startswith("R.") else st.column_config.TextColumn(col, disabled=True, width=65)

df_mod = st.data_editor(df, column_config=column_config, hide_index=True, width="stretch", key="griglia_registro")

# ------------------------------------------------------------
# BLOCCO: GIACENZA DI CHIUSURA A FINE PERIODO
# La tabella sopra mostra sempre l'APERTURA di ogni giorno (= chiusura del
# giorno prima). Su richiesta dell'utente (27/08) mostriamo qui SEPARATAMENTE
# anche la CHIUSURA dell'ultimo giorno del periodo selezionato, cioè la
# giacenza reale "a fine periodo" (apertura dell'ultimo giorno + movimenti di
# quel giorno).
# ------------------------------------------------------------
etichette_chiusura = [
    (usa_dop, "MBC", "bufala_dop"), (usa_buf, "Buf", "bufala"), (usa_vacc, "Vacc", "vaccino"),
    (usa_sem_buf, "SemB", "semilavorato_bufala"), (usa_sem_vacc, "SemV", "semilavorato_vaccino"),
]
n_metriche = sum(1 for attivo, _, _ in etichette_chiusura if attivo) or 1
cols_chiusura = st.columns(n_metriche)
i_col = 0
for attivo, etichetta, tipo in etichette_chiusura:
    if not attivo:
        continue
    with cols_chiusura[i_col]:
        st.metric(f"Chiusura {etichetta} al {periodo_fine.strftime('%d/%m/%Y')}", f"{round(giacenza_chiusura_periodo.get(tipo, 0))} kg")
    i_col += 1

# ------------------------------------------------------------
# BLOCCO: SALVATAGGIO
# ------------------------------------------------------------
if is_owner():
    st.caption("Nota: la produzione (Mozzarella Prodotta) si modifica SOLO nella pagina Produzioni. Qui puoi solo spostare una quota dei prodotti derivati (senza lattosio, mozzarella di bufala, ecc.) su latte non-DOP con le colonne 'nD', e indicare quanto latte bufala/vaccino è entrato nella Mozzarella Mista con le colonne 'Buf'/'Vac'.")
    if st.button("💾 Salva registro"):
        record_trasf, record_vend = [], []
        for i, d in enumerate(date_periodo):
            ds = str(d)
            for t, col in [("bufala_dop","Tr.MBC"),("bufala","Tr.Buf"),("vaccino","Tr.Vacc"),
                           ("semilavorato_bufala","Tr.SemB"),("semilavorato_vaccino","Tr.SemV")]:
                if col in df.columns:
                    record_trasf.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(df_mod.loc[i, col] or 0)})

            # quota "fatta con non-DOP" per i prodotti derivati (l'unica cosa scrivibile sulla produzione qui)
            for p in prodotti_dop_altri + prodotti_declassati:
                prefisso = "D." if p in prodotti_dop_altri else "Dec."
                col_nd = f"{prefisso}{p['nome'][:6]}nD"
                if col_nd not in df.columns: continue
                rec = prod_map.get((p["id"], ds))
                if not rec: continue
                kg_nd = float(df_mod.loc[i, col_nd] or 0)
                client.table("produzione_origine").upsert({
                    "produzione_id": rec["id"], "origine": "non_dop", "kg": kg_nd,
                }, on_conflict="produzione_id,origine").execute()

            # latte bufala/vaccino usato per la Mozzarella Mista (aggiunto 27/08)
            for p in prodotti_mista:
                base = f"Mis.{p['nome'][:6]}"
                rec = prod_map.get((p["id"], ds))
                if not rec: continue
                for origine, col in [("bufala", f"{base}Buf"), ("vaccino", f"{base}Vac")]:
                    if col not in df.columns: continue
                    kg_o = float(df_mod.loc[i, col] or 0)
                    client.table("produzione_origine").upsert({
                        "produzione_id": rec["id"], "origine": origine, "kg": kg_o,
                    }, on_conflict="produzione_id,origine").execute()

            for t, col in [("bufala_congelato","CongVend"),("vaccino","VaccVend")]:
                if col in df.columns:
                    kg_v = float(df_mod.loc[i, col] or 0)
                    if kg_v > 0: record_vend.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": kg_v})

        if record_trasf:
            client.table("trasformato").upsert(record_trasf, on_conflict="caseificio_id,tipo_latte,data").execute()
        client.table("latte_venduto").delete().eq("caseificio_id", caseificio_id).gte("data", str(periodo_inizio)).lte("data", str(periodo_fine)).execute()
        if record_vend:
            client.table("latte_venduto").insert(record_vend).execute()
        st.success("Registro salvato.")
        st.rerun()

# ------------------------------------------------------------
# BLOCCO: IMPORTA / ESPORTA
# CORREZIONE: il CSV va generato con separatore ";" e codifica UTF-8 con BOM
# (utf-8-sig), altrimenti Excel in italiano lo apre male (tutto in una sola
# colonna, sembra "non funzionare" anche se il file è tecnicamente valido).
# ------------------------------------------------------------
col_exp1, col_exp2 = st.columns(2)
with col_exp1:
    try:
        csv_bytes = df_completo.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        st.download_button(
            "⬇️ Esporta CSV (compatibile Excel)", data=csv_bytes,
            file_name=f"registro_{periodo_inizio}_{periodo_fine}.csv", mime="text/csv",
        )
    except Exception as e:
        st.error(f"Errore nella generazione del CSV: {e}")
with col_exp2:
    file_import = st.file_uploader("⬆️ Importa CSV", type=["csv"], key="import_registro")
    if file_import is not None and is_owner():
        try:
            df_import = pd.read_csv(file_import, sep=";", decimal=",")
            st.dataframe(df_import, width="stretch")
            if st.button("Conferma importazione"):
                st.warning("L'importazione sovrascrive i valori Trasformato/Venduto per le date corrispondenti presenti nel file. Assicurati che le colonne coincidano con quelle della tabella sopra.")
                for i in range(len(df_import)):
                    ds_match = None
                    for d in date_periodo:
                        if d.strftime("%d/%m") == str(df_import.iloc[i]["Data"]):
                            ds_match = str(d)
                            break
                    if not ds_match: continue
                    for t, col in [("bufala_dop","Tr.MBC"),("bufala","Tr.Buf"),("vaccino","Tr.Vacc"),
                                   ("semilavorato_bufala","Tr.SemB"),("semilavorato_vaccino","Tr.SemV")]:
                        if col in df_import.columns:
                            client.table("trasformato").upsert({
                                "caseificio_id": caseificio_id, "tipo_latte": t, "data": ds_match,
                                "kg": float(df_import.iloc[i][col] or 0),
                            }, on_conflict="caseificio_id,tipo_latte,data").execute()
                st.success("Importazione completata.")
                st.rerun()
        except Exception as e:
            st.error(f"Errore nella lettura del file: {e}")

st.divider()

# ------------------------------------------------------------
# BLOCCO: AVVISI
# ------------------------------------------------------------
for t, label in [("bufala_dop","Bufala DOP"),("bufala","Bufala"),("vaccino","Vaccino")]:
    if giacenza_per_tipo.get(t, 0) < 0:
        st.error(f"⚠️ Giacenza {label} NEGATIVA: {round(giacenza_per_tipo[t],1)} kg.")

if usa_dop:
    eta, giac = None, 0.0
    for d in tutte_le_date:
        entrata = raccolto.get(("bufala_dop", d), 0)
        uscita = (trasformato_map.get(("bufala_dop", d), 0)
                  + consumo_extra_dop.get(("bufala_dop", d), 0)
                  + venduto_map.get(("bufala_dop", d), 0)
                  + congelato_map.get(("bufala_dop", d), 0))
        if giac <= 0 and entrata > 0: eta = d
        if uscita >= giac + entrata: eta = None
        giac = giac + entrata - uscita
    if eta:
        ore = (periodo_fine - _dt.date.fromisoformat(eta)).days * 24
        if ore > 60:
            st.error(f"⚠️ Il latte DOP più vecchio in giacenza risulta del {eta} — più di 60 ore (stima)!")
        elif ore > 48:
            st.warning(f"⏰ Il latte DOP più vecchio in giacenza è del {eta} — attenzione alle 60 ore.")
