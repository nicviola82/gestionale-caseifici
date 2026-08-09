# ============================================================
# PAGINA: REGISTRO
# 5 pool di latte (Bufala DOP, Bufala, Vaccino, Semilavorato
# bufalino, Semilavorato vaccino): Refrigerato/Ritirato/
# Trasformato/Venduto in griglia. Sezione "Origine produzione"
# per lo spostamento tra caselle (DOP/non-DOP/semilavorato) sui
# prodotti famiglia bufala. Sezione dedicata Mista/Vaccina con
# resa combinata (vaccino a meta' peso).
# ============================================================
import streamlit as st
import pandas as pd
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Registro", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Registro")

caseificio_id = st.session_state.get("caseificio_id")
periodo_inizio = st.session_state.get("periodo_inizio")
periodo_fine = st.session_state.get("periodo_fine")

if not caseificio_id or not periodo_inizio:
    st.info("Seleziona caseificio e periodo dalla pagina principale prima di continuare.")
    st.stop()

st.caption(f"Periodo: {st.session_state.get('periodo_label')}")

TIPI_LATTE_LABEL = {
    "bufala_dop": "Bufala DOP", "bufala": "Bufala", "vaccino": "Vaccino",
    "semilavorato_bufala": "Semilav. bufalino", "semilavorato_vaccino": "Semilav. vaccino",
}

n_giorni = (periodo_fine - periodo_inizio).days + 1
date_periodo = [periodo_inizio + _dt.timedelta(days=i) for i in range(n_giorni)]

# ------------------------------------------------------------
# BLOCCO: TIPI DI LATTE REALMENTE IN USO
# ------------------------------------------------------------
conferitori_tutti = (
    client.table("conferitori")
    .select("id, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .execute()
    .data
)
tipo_per_conferitore = {c["id"]: [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])] for c in conferitori_tutti}
tipi_in_uso = [t for t in TIPI_LATTE_LABEL if any(t in tipi for tipi in tipo_per_conferitore.values())]

if not tipi_in_uso:
    st.info("Nessun conferitore con un tipo di latte riconosciuto. Vai su 'Conferitori' per impostarli.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: DATI STORICI (raccolto, venduto, congelato, trasformato)
# ------------------------------------------------------------
conferimenti_tutti = (
    client.table("conferimenti")
    .select("*")
    .in_("conferitore_id", list(tipo_per_conferitore.keys()))
    .lte("data", str(periodo_fine))
    .execute()
    .data
) if tipo_per_conferitore else []

movimenti_tutti = (
    client.table("movimenti_congelato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)

trasformato_tutti = (
    client.table("trasformato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
trasformato_map = {(t["tipo_latte"], t["data"]): float(t["kg"] or 0) for t in trasformato_tutti}

venduto_tutti = (
    client.table("latte_venduto")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
venduto_map = {}
for v in venduto_tutti:
    venduto_map[(v["tipo_latte"], v["data"])] = venduto_map.get((v["tipo_latte"], v["data"]), 0) + float(v["kg"] or 0)

raccolto = {}
for cf in conferimenti_tutti:
    tipi = tipo_per_conferitore.get(cf["conferitore_id"], [])
    kg = float(cf.get("kg") or 0)
    if kg <= 0:
        continue
    for t in tipi:
        if t in TIPI_LATTE_LABEL:
            raccolto[(t, cf["data"])] = raccolto.get((t, cf["data"]), 0) + kg

congelato_map = {}
for m in movimenti_tutti:
    if m["tipo"] == "scongelamento":
        raccolto[("bufala", m["data"])] = raccolto.get(("bufala", m["data"]), 0) + float(m["kg"])
    elif m["tipo"] == "congelamento":
        origine = m.get("origine") or "bufala"
        congelato_map[(origine, m["data"])] = congelato_map.get((origine, m["data"]), 0) + float(m["kg"])

# ------------------------------------------------------------
# BLOCCO: PRODOTTI ATTIVI E CLASSIFICAZIONE (famiglia bufala vs mista/vaccina)
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

def etichetta_prodotto(p):
    return f"{p['nome']} (DOP)" if p["is_dop"] else p["nome"]

def e_mista_o_vaccina(p):
    n = p["nome"].lower()
    return ("mista" in n) or ("vaccin" in n)

prodotti_dop = [p for p in prodotti if p["is_dop"]]
prodotti_bufala_famiglia = [p for p in prodotti if not p["is_dop"] and not e_mista_o_vaccina(p)]

prodotto_ids = [p["id"] for p in prodotti]
produzioni_esistenti = (
    client.table("produzioni")
    .select("*")
    .in_("prodotto_id", prodotto_ids)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .execute()
    .data
) if prodotto_ids else []
produzioni_map = {(e["prodotto_id"], e["data"]): e for e in produzioni_esistenti}

# ------------------------------------------------------------
# BLOCCO: ORIGINE PRODUZIONE (spostamento DOP/non-DOP/semilavorato)
# ------------------------------------------------------------
produzione_ids_bufala = [produzioni_map[k]["id"] for k in produzioni_map if produzioni_map[k]["prodotto_id"] in [p["id"] for p in prodotti_bufala_famiglia]]
origini_tutte = (
    client.table("produzione_origine")
    .select("*")
    .in_("produzione_id", produzione_ids_bufala)
    .execute()
    .data
) if produzione_ids_bufala else []
origini_map = {}
for o in origini_tutte:
    origini_map.setdefault(o["produzione_id"], {})[o["origine"]] = float(o["kg"] or 0)

# ------------------------------------------------------------
# BLOCCO: RESA DOP DEL GIORNO (produzione DOP totale / trasformato DOP)
# ------------------------------------------------------------
def resa_dop(ds):
    prod_dop = sum(float(produzioni_map[(p["id"], ds)]["kg_totale"] or 0) for p in prodotti_dop if (p["id"], ds) in produzioni_map)
    trasf_dop = trasformato_map.get(("bufala_dop", ds), 0)
    return (prod_dop / trasf_dop) if trasf_dop > 0 else None

# ------------------------------------------------------------
# BLOCCO: CONSUMO EXTRA per DOP/semilavorato_bufala dovuto a integrazioni
# (kg fatti con DOP / resa_dop; kg fatti con semilavorato = 1:1)
# ------------------------------------------------------------
consumo_extra = {}  # (tipo, data) -> kg
for (prod_id, ds), rec in produzioni_map.items():
    if rec["prodotto_id"] not in [p["id"] for p in prodotti_bufala_famiglia]:
        continue
    origini = origini_map.get(rec["id"], {})
    kg_dop = origini.get("dop", 0)
    kg_semi = origini.get("semilavorato_bufala", 0)
    if kg_dop > 0:
        r = resa_dop(ds)
        if r and r > 0:
            consumo_extra[("bufala_dop", ds)] = consumo_extra.get(("bufala_dop", ds), 0) + kg_dop / r
    if kg_semi > 0:
        consumo_extra[("semilavorato_bufala", ds)] = consumo_extra.get(("semilavorato_bufala", ds), 0) + kg_semi  # 1:1

# ------------------------------------------------------------
# BLOCCO: SEZIONE MISTA/VACCINA (consumo vaccino/bufala dedicato)
# ------------------------------------------------------------
mista_vaccina_tutti = (
    client.table("mista_vaccina")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
mv_map = {m["data"]: m for m in mista_vaccina_tutti}

for ds, m in mv_map.items():
    trasf_vacc = float(m["trasformato_vaccino_kg"] or 0)
    trasf_buf_mista = float(m["trasformato_bufala_mista_kg"] or 0)
    prod_vacc = float(m["produzione_vaccina_kg"] or 0)
    prod_mista = float(m["produzione_mista_kg"] or 0)
    denom = (trasf_vacc / 2) + trasf_buf_mista
    if denom > 0:
        resa_combinata = (prod_vacc + prod_mista) / denom
        if resa_combinata > 0:
            latte_vacc_per_vaccina = prod_vacc / (resa_combinata / 2)
            consumo_extra[("vaccino", ds)] = consumo_extra.get(("vaccino", ds), 0) + latte_vacc_per_vaccina
            consumo_extra[("bufala", ds)] = consumo_extra.get(("bufala", ds), 0) + trasf_buf_mista
            residuo_vaccino = trasf_vacc - latte_vacc_per_vaccina
            consumo_extra[("vaccino", ds)] = consumo_extra.get(("vaccino", ds), 0) + max(residuo_vaccino, 0)

# ------------------------------------------------------------
# BLOCCO: CALCOLO GIACENZE (con vendite, congelamento, integrazioni)
# ------------------------------------------------------------
tutte_le_date = sorted(set(
    [d for (_, d) in raccolto.keys()] + [k[1] for k in trasformato_map.keys()]
    + [k[1] for k in venduto_map.keys()] + [k[1] for k in congelato_map.keys()]
    + [k[1] for k in consumo_extra.keys()] + [str(d) for d in date_periodo]
))

giacenza_per_tipo = {t: 0.0 for t in tipi_in_uso}
giacenza_per_giorno = {}
for d in tutte_le_date:
    for t in tipi_in_uso:
        # la giacenza mostrata per il giorno "d" e' quella DISPONIBILE ALL'APERTURA
        # di quel giorno, cioe' la chiusura del giorno precedente (come nel foglio Excel)
        giacenza_per_giorno[(t, d)] = giacenza_per_tipo[t]
        entrata = raccolto.get((t, d), 0)
        uscita = trasformato_map.get((t, d), 0) + consumo_extra.get((t, d), 0) + venduto_map.get((t, d), 0)
        if t in ("bufala_dop", "bufala"):
            uscita += congelato_map.get(("bufala_dop" if t == "bufala_dop" else "bufala", d), 0)
        giacenza_per_tipo[t] = giacenza_per_tipo[t] + entrata - uscita

# ------------------------------------------------------------
# BLOCCO: GRIGLIA PRINCIPALE
# ------------------------------------------------------------
st.subheader("Griglia Registro")
st.caption("Refrigerato/Ritirato = calcolati. Trasformato e Venduto = li scrivi tu. Il consumo per le integrazioni (DOP->non-DOP, semilavorato, mista/vaccina) si aggiunge automaticamente, lo vedi nel riepilogo sotto.")

righe = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for t in tipi_in_uso:
        riga[f"{t} - Refrigerato"] = round(giacenza_per_giorno.get((t, ds), 0.0), 1)
        riga[f"{t} - Ritirato"] = round(raccolto.get((t, ds), 0.0), 1)
        riga[f"{t} - Trasformato"] = trasformato_map.get((t, ds), 0.0)
        riga[f"{t} - Venduto"] = venduto_map.get((t, ds), 0.0)
    righe.append(riga)

df = pd.DataFrame(righe)
column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for t in tipi_in_uso:
    label = TIPI_LATTE_LABEL[t]
    column_config[f"{t} - Refrigerato"] = st.column_config.NumberColumn(f"{label}\nRefrigerato", disabled=True)
    column_config[f"{t} - Ritirato"] = st.column_config.NumberColumn(f"{label}\nRitirato", disabled=True)
    column_config[f"{t} - Trasformato"] = st.column_config.NumberColumn(f"{label}\nTrasformato", min_value=0.0, step=1.0)
    column_config[f"{t} - Venduto"] = st.column_config.NumberColumn(f"{label}\nVenduto", min_value=0.0, step=1.0)

df_modificato = st.data_editor(df, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_registro")

if is_owner():
    if st.button("💾 Salva griglia Registro"):
        record_trasformato, record_venduto = [], []
        for i, d in enumerate(date_periodo):
            ds = str(d)
            for t in tipi_in_uso:
                kg_t = df_modificato.loc[i, f"{t} - Trasformato"]
                if kg_t and float(kg_t) > 0:
                    record_trasformato.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(kg_t)})
                kg_v = df_modificato.loc[i, f"{t} - Venduto"]
                if kg_v and float(kg_v) > 0:
                    record_venduto.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(kg_v)})
        if record_trasformato:
            client.table("trasformato").upsert(record_trasformato, on_conflict="caseificio_id,tipo_latte,data").execute()
        if record_venduto:
            # cancella e reinserisce le vendite del periodo per evitare duplicati/somme errate
            client.table("latte_venduto").delete().eq("caseificio_id", caseificio_id).gte("data", str(periodo_inizio)).lte("data", str(periodo_fine)).execute()
            client.table("latte_venduto").insert(record_venduto).execute()
        st.success("Registro salvato.")
        st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: ORIGINE PRODUZIONE FAMIGLIA BUFALA (spostamento tra caselle)
# ------------------------------------------------------------
st.subheader("Origine produzione — famiglia bufala (DOP / non-DOP / semilavorato)")
st.caption("Per i prodotti non-DOP famiglia bufala: indica quanta produzione di quel giorno e' fatta con latte DOP, quanta con latte non-DOP, quanta con semilavorato. Il programma calcola da solo il latte DOP/semilavorato consumato in piu'.")

righe_bufala_con_totale = [(p, d) for p in prodotti_bufala_famiglia for d in date_periodo if (p["id"], str(d)) in produzioni_map and float(produzioni_map[(p["id"], str(d))].get("kg_totale") or 0) > 0]

if not righe_bufala_con_totale:
    st.info("Nessuna produzione famiglia bufala non-DOP trovata nel periodo (vai su Produzioni per inserirla).")
else:
    prod_nome = st.selectbox("Prodotto", sorted({etichetta_prodotto(p) for p, _ in righe_bufala_con_totale}), key="orig_prodotto")
    prod_sel = next(p for p, _ in righe_bufala_con_totale if etichetta_prodotto(p) == prod_nome)
    date_disp = sorted({d for p, d in righe_bufala_con_totale if p["id"] == prod_sel["id"]})
    data_sel = st.selectbox("Data", date_disp, format_func=lambda d: d.strftime("%d/%m/%Y"), key="orig_data")

    rec = produzioni_map[(prod_sel["id"], str(data_sel))]
    totale_giorno = float(rec["kg_totale"])
    origini_attuali = origini_map.get(rec["id"], {})
    st.caption(f"Totale prodotto quel giorno: {totale_giorno} kg")

    if is_owner():
        with st.form("form_origine"):
            kg_dop = st.number_input("Fatta con latte DOP (kg)", min_value=0.0, step=1.0, value=origini_attuali.get("dop", 0.0))
            kg_nondop = st.number_input("Fatta con latte non-DOP (kg)", min_value=0.0, step=1.0, value=origini_attuali.get("non_dop", 0.0))
            kg_semi = st.number_input("Fatta con semilavorato (kg)", min_value=0.0, step=1.0, value=origini_attuali.get("semilavorato_bufala", 0.0))
            somma = kg_dop + kg_nondop + kg_semi
            st.caption(f"Somma inserita: {somma} kg (totale prodotto: {totale_giorno} kg)" + (" ⚠️ non coincide" if abs(somma - totale_giorno) > 0.01 else " ✅"))
            r_dop = resa_dop(str(data_sel))
            if kg_dop > 0:
                if r_dop:
                    st.caption(f"Resa DOP di oggi: {r_dop*100:.1f}% -> latte DOP consumato in piu': {kg_dop/r_dop:.1f} kg")
                else:
                    st.caption("⚠️ Nessuna resa DOP disponibile per oggi (serve trasformato+produzione DOP quel giorno).")
            if st.form_submit_button("Salva origine"):
                for origine, kg in [("dop", kg_dop), ("non_dop", kg_nondop), ("semilavorato_bufala", kg_semi)]:
                    client.table("produzione_origine").upsert({
                        "produzione_id": rec["id"], "origine": origine, "kg": kg,
                    }, on_conflict="produzione_id,origine").execute()
                st.success("Salvato.")
                st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: MOZZARELLA VACCINA E MISTA (resa combinata)
# ------------------------------------------------------------
st.subheader("Mozzarella vaccina e mista")
st.caption("Il vaccino vale meta' della bufala in resa. Resa combinata = (produzione vaccina + mista) / (trasformato vaccino/2 + trasformato bufala per mista).")

data_mv = st.selectbox("Data", date_periodo, format_func=lambda d: d.strftime("%d/%m/%Y"), key="mv_data")
mv_esistente = mv_map.get(str(data_mv), {})

if is_owner():
    with st.form("form_mista_vaccina"):
        tv = st.number_input("Trasformato vaccino (kg)", min_value=0.0, step=1.0, value=float(mv_esistente.get("trasformato_vaccino_kg", 0) or 0))
        tb = st.number_input("Trasformato bufala per mista (kg)", min_value=0.0, step=1.0, value=float(mv_esistente.get("trasformato_bufala_mista_kg", 0) or 0))
        pv = st.number_input("Produzione mozzarella vaccina (kg)", min_value=0.0, step=1.0, value=float(mv_esistente.get("produzione_vaccina_kg", 0) or 0))
        pm = st.number_input("Produzione mozzarella mista (kg)", min_value=0.0, step=1.0, value=float(mv_esistente.get("produzione_mista_kg", 0) or 0))

        denom = (tv / 2) + tb
        if denom > 0:
            resa_c = (pv + pm) / denom
            st.caption(f"Resa combinata: {resa_c*100:.1f}%")
            if resa_c > 0:
                latte_vacc_vaccina = pv / (resa_c / 2)
                st.caption(f"Latte vaccino per la vaccina: {latte_vacc_vaccina:.1f} kg — residuo vaccino per la mista: {max(tv - latte_vacc_vaccina, 0):.1f} kg")

        if st.form_submit_button("Salva mista/vaccina"):
            client.table("mista_vaccina").upsert({
                "caseificio_id": caseificio_id, "data": str(data_mv),
                "trasformato_vaccino_kg": tv, "trasformato_bufala_mista_kg": tb,
                "produzione_vaccina_kg": pv, "produzione_mista_kg": pm,
            }, on_conflict="caseificio_id,data").execute()
            st.success("Salvato.")
            st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: RESE DEL PERIODO (riepilogo)
# ------------------------------------------------------------
st.subheader("Rese del periodo")
rese_righe = []
for d in date_periodo:
    ds = str(d)
    r_dop = resa_dop(ds)
    m = mv_map.get(ds, {})
    denom_mv = (float(m.get("trasformato_vaccino_kg", 0) or 0) / 2) + float(m.get("trasformato_bufala_mista_kg", 0) or 0)
    resa_mv = ((float(m.get("produzione_vaccina_kg", 0) or 0) + float(m.get("produzione_mista_kg", 0) or 0)) / denom_mv) if denom_mv > 0 else None
    if r_dop or resa_mv:
        rese_righe.append({
            "Data": d.strftime("%d/%m/%Y"),
            "Resa DOP": f"{r_dop*100:.1f}%" if r_dop else "-",
            "Resa mista/vaccina": f"{resa_mv*100:.1f}%" if resa_mv else "-",
        })
if rese_righe:
    st.table(rese_righe)
else:
    st.write("Nessuna resa calcolabile ancora per questo periodo.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: AVVISI
# ------------------------------------------------------------
for t in tipi_in_uso:
    if giacenza_per_tipo[t] < 0:
        st.error(f"⚠️ Giacenza {TIPI_LATTE_LABEL[t]} NEGATIVA: {round(giacenza_per_tipo[t],1)} kg.")

if "bufala_dop" in tipi_in_uso:
    eta_giacenza_dop, giac = None, 0.0
    for d in tutte_le_date:
        entrata = raccolto.get(("bufala_dop", d), 0)
        uscita = trasformato_map.get(("bufala_dop", d), 0) + consumo_extra.get(("bufala_dop", d), 0) + venduto_map.get(("bufala_dop", d), 0) + congelato_map.get(("bufala_dop", d), 0)
        if giac <= 0 and entrata > 0:
            eta_giacenza_dop = d
        if uscita >= giac + entrata:
            eta_giacenza_dop = None
        giac = giac + entrata - uscita
    if eta_giacenza_dop:
        ore_trascorse = (periodo_fine - _dt.date.fromisoformat(eta_giacenza_dop)).days * 24
        if ore_trascorse > 60:
            st.error(f"⚠️ Il latte DOP più vecchio in giacenza risulta del {eta_giacenza_dop} — più di 60 ore (stima)!")
        elif ore_trascorse > 48:
            st.warning(f"⏰ Il latte DOP più vecchio in giacenza è del {eta_giacenza_dop} — attenzione alle 60 ore (stima).")
