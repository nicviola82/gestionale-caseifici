# ============================================================
# PAGINA: REGISTRO
# Elenco di LAVORAZIONI: ogni riga = un prodotto, una data, il
# latte usato (con eventuale seconda fonte per la mista) e il
# prodotto ottenuto. La resa si calcola riga per riga, libera.
# Sotto: Refrigerato/Ritirato/Venduto/Congelato per tipo di
# latte, calcolati su tutta la storia (non solo il periodo).
# ============================================================
import streamlit as st
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
# (da conferitori diretti oppure da scongelamento -> bufala)
# ------------------------------------------------------------
conferitori_tutti = (
    client.table("conferitori")
    .select("id, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .execute()
    .data
)
tipo_per_conferitore = {c["id"]: [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])] for c in conferitori_tutti}
tipi_da_conferitori = {t for tipi in tipo_per_conferitore.values() for t in tipi if t in TIPI_LATTE_LABEL}

movimenti_tutti = (
    client.table("movimenti_congelato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
ha_scongelamento = any(m["tipo"] == "scongelamento" for m in movimenti_tutti)
if ha_scongelamento:
    tipi_da_conferitori.add("bufala")

tipi_in_uso = [t for t in TIPI_LATTE_LABEL if t in tipi_da_conferitori]

if not tipi_in_uso:
    st.info("Nessun conferitore con un tipo di latte riconosciuto. Vai su 'Conferitori' per impostarli.")
    st.stop()

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
prodotti_by_id = {p["id"]: p for p in prodotti}

def etichetta_prodotto(p):
    return f"{p['nome']} (DOP)" if p["is_dop"] else p["nome"]

if not prodotti:
    st.info("Nessun prodotto attivo/visibile in Produzioni. Vai su 'Prodotti' per attivarne uno.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: NUOVA LAVORAZIONE
# ------------------------------------------------------------
st.subheader("➕ Nuova lavorazione")
if is_owner():
    with st.form("nuova_lavorazione"):
        col1, col2 = st.columns(2)
        with col1:
            data_lav = st.date_input("Data", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine)
            prod_nome = st.selectbox("Prodotto", [etichetta_prodotto(p) for p in prodotti])
        with col2:
            fonte1 = st.selectbox("Fonte di latte", tipi_in_uso, format_func=lambda t: TIPI_LATTE_LABEL[t])
            kg1 = st.number_input("KG di latte usati (fonte 1)", min_value=0.0, step=1.0)

        usa_seconda_fonte = st.checkbox("Usa anche una seconda fonte di latte (es. per la mista: bufala + vaccino)")
        fonte2, kg2 = None, 0.0
        if usa_seconda_fonte:
            c1, c2 = st.columns(2)
            with c1:
                fonte2 = st.selectbox("Fonte di latte 2", [t for t in tipi_in_uso if t != fonte1], format_func=lambda t: TIPI_LATTE_LABEL[t], key="fonte2")
            with c2:
                kg2 = st.number_input("KG di latte usati (fonte 2)", min_value=0.0, step=1.0, key="kg2")

        kg_prodotto = st.number_input("KG di prodotto ottenuti", min_value=0.0, step=1.0)

        if kg1 > 0 and kg_prodotto > 0:
            tot_latte = kg1 + (kg2 or 0)
            st.caption(f"Resa di questa lavorazione: {kg_prodotto/tot_latte*100:.2f}%")

        if st.form_submit_button("Salva lavorazione"):
            prod_sel = next(p for p in prodotti if etichetta_prodotto(p) == prod_nome)
            client.table("lavorazioni").insert({
                "caseificio_id": caseificio_id, "prodotto_id": prod_sel["id"], "data": str(data_lav),
                "fonte1": fonte1, "kg_latte1": kg1,
                "fonte2": fonte2, "kg_latte2": kg2 if usa_seconda_fonte else None,
                "kg_prodotto": kg_prodotto,
            }).execute()
            st.success("Lavorazione salvata.")
            st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: ELENCO LAVORAZIONI DEL PERIODO
# ------------------------------------------------------------
st.subheader("Lavorazioni del periodo")

lavorazioni_periodo = (
    client.table("lavorazioni")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .order("data")
    .execute()
    .data
)

if not lavorazioni_periodo:
    st.write("Nessuna lavorazione ancora registrata in questo periodo.")
else:
    for lav in lavorazioni_periodo:
        prod = prodotti_by_id.get(lav["prodotto_id"])
        nome_prod = etichetta_prodotto(prod) if prod else "(prodotto eliminato)"
        tot_latte = float(lav["kg_latte1"] or 0) + float(lav["kg_latte2"] or 0)
        resa = (float(lav["kg_prodotto"]) / tot_latte * 100) if tot_latte > 0 else 0
        fonte_txt = TIPI_LATTE_LABEL.get(lav["fonte1"], lav["fonte1"]) + f" {lav['kg_latte1']} kg"
        if lav.get("fonte2"):
            fonte_txt += f" + {TIPI_LATTE_LABEL.get(lav['fonte2'], lav['fonte2'])} {lav['kg_latte2']} kg"
        col1, col2 = st.columns([6, 1])
        with col1:
            st.write(f"**{_dt.date.fromisoformat(lav['data']).strftime('%d/%m/%Y')}** — {nome_prod}: {fonte_txt} → **{lav['kg_prodotto']} kg** prodotti (resa {resa:.2f}%)")
        with col2:
            if is_owner() and st.button("🗑️", key=f"del_lav_{lav['id']}"):
                client.table("lavorazioni").delete().eq("id", lav["id"]).execute()
                st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: VENDITA LATTE
# ------------------------------------------------------------
st.subheader("Vendita latte")
if is_owner():
    with st.expander("➕ Registra vendita di latte"):
        with st.form("nuova_vendita_latte"):
            data_v = st.date_input("Data ", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine, key="data_vendita_latte")
            tipo_v = st.selectbox("Tipo di latte venduto", tipi_in_uso, format_func=lambda t: TIPI_LATTE_LABEL[t], key="tipo_vendita_latte")
            kg_v = st.number_input("KG venduti", min_value=0.0, step=1.0, key="kg_vendita_latte")
            if st.form_submit_button("Salva vendita"):
                client.table("latte_venduto").insert({
                    "caseificio_id": caseificio_id, "tipo_latte": tipo_v, "data": str(data_v), "kg": kg_v,
                }).execute()
                st.success("Registrata.")
                st.rerun()

venduto_periodo = (
    client.table("latte_venduto")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .order("data")
    .execute()
    .data
)
if venduto_periodo:
    st.table([{
        "Data": _dt.date.fromisoformat(v["data"]).strftime("%d/%m/%Y"),
        "Tipo": TIPI_LATTE_LABEL.get(v["tipo_latte"], v["tipo_latte"]),
        "KG": v["kg"],
    } for v in venduto_periodo])

st.divider()

# ------------------------------------------------------------
# BLOCCO: DATI STORICI COMPLETI (per calcolare correttamente la giacenza)
# ------------------------------------------------------------
conferimenti_tutti = (
    client.table("conferimenti")
    .select("*")
    .in_("conferitore_id", list(tipo_per_conferitore.keys()))
    .lte("data", str(periodo_fine))
    .execute()
    .data
) if tipo_per_conferitore else []

lavorazioni_tutte = (
    client.table("lavorazioni")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)

venduto_tutti = (
    client.table("latte_venduto")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)

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

trasformato = {}  # (tipo, data) -> kg consumati (da tutte le lavorazioni)
for lav in lavorazioni_tutte:
    trasformato[(lav["fonte1"], lav["data"])] = trasformato.get((lav["fonte1"], lav["data"]), 0) + float(lav["kg_latte1"] or 0)
    if lav.get("fonte2"):
        trasformato[(lav["fonte2"], lav["data"])] = trasformato.get((lav["fonte2"], lav["data"]), 0) + float(lav["kg_latte2"] or 0)

venduto_map = {}
for v in venduto_tutti:
    venduto_map[(v["tipo_latte"], v["data"])] = venduto_map.get((v["tipo_latte"], v["data"]), 0) + float(v["kg"] or 0)

tutte_le_date = sorted(set(
    [d for (_, d) in raccolto.keys()] + [d for (_, d) in trasformato.keys()]
    + [d for (_, d) in venduto_map.keys()] + [d for (_, d) in congelato_map.keys()]
    + [str(d) for d in date_periodo]
))

giacenza_per_tipo = {t: 0.0 for t in tipi_in_uso}
giacenza_per_giorno = {}
for d in tutte_le_date:
    for t in tipi_in_uso:
        # apertura del giorno = chiusura del giorno precedente
        giacenza_per_giorno[(t, d)] = giacenza_per_tipo[t]
        entrata = raccolto.get((t, d), 0)
        uscita = trasformato.get((t, d), 0) + venduto_map.get((t, d), 0)
        if t in ("bufala_dop", "bufala"):
            uscita += congelato_map.get(("bufala_dop" if t == "bufala_dop" else "bufala", d), 0)
        giacenza_per_tipo[t] = giacenza_per_tipo[t] + entrata - uscita

# ------------------------------------------------------------
# BLOCCO: RIEPILOGO REFRIGERATO / RITIRATO / TRASFORMATO / CONGELATO
# ------------------------------------------------------------
st.subheader("Refrigerato, Ritirato, Trasformato e Congelato")
riepilogo = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for t in tipi_in_uso:
        label = TIPI_LATTE_LABEL[t]
        riga[f"{label} Refr."] = round(giacenza_per_giorno.get((t, ds), 0.0), 1)
        riga[f"{label} Rit."] = round(raccolto.get((t, ds), 0.0), 1)
        riga[f"{label} Trasf."] = round(trasformato.get((t, ds), 0.0), 1)
        if t in ("bufala_dop", "bufala"):
            cong = congelato_map.get((t, ds), 0.0)
            if cong:
                riga[f"{label} Cong."] = round(cong, 1)
    riepilogo.append(riga)
st.dataframe(riepilogo, use_container_width=True, hide_index=True)

st.divider()

# ------------------------------------------------------------
# BLOCCO: RESE PER PRODOTTO NEL PERIODO
# ------------------------------------------------------------
st.subheader("Rese per prodotto")
rese_per_prodotto = {}
for lav in lavorazioni_periodo:
    tot_latte = float(lav["kg_latte1"] or 0) + float(lav["kg_latte2"] or 0)
    if tot_latte <= 0:
        continue
    pid = lav["prodotto_id"]
    rese_per_prodotto.setdefault(pid, {"latte": 0.0, "prodotto": 0.0})
    rese_per_prodotto[pid]["latte"] += tot_latte
    rese_per_prodotto[pid]["prodotto"] += float(lav["kg_prodotto"])

if rese_per_prodotto:
    righe_rese = []
    for pid, v in rese_per_prodotto.items():
        prod = prodotti_by_id.get(pid)
        if not prod:
            continue
        resa = v["prodotto"] / v["latte"] * 100 if v["latte"] > 0 else 0
        righe_rese.append({
            "Prodotto": etichetta_prodotto(prod), "Latte totale KG": round(v["latte"], 1),
            "Prodotto totale KG": round(v["prodotto"], 1), "Resa media %": round(resa, 2),
        })
    st.table(righe_rese)
else:
    st.write("Nessuna lavorazione con dati sufficienti per calcolare la resa.")

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
        uscita = trasformato.get(("bufala_dop", d), 0) + venduto_map.get(("bufala_dop", d), 0) + congelato_map.get(("bufala_dop", d), 0)
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
