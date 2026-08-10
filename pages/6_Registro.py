# ============================================================
# PAGINA: REGISTRO
# Un'unica tabella: Refrigerato/Ritirato (calcolati) + Trasformato
# (editabile) per ogni tipo di latte, Prodotto (editabile,
# condiviso con Produzioni) per ogni prodotto, Resa (calcolata,
# solo dal prodotto che la "stabilisce"). Si salva da sola ad
# ogni modifica, senza bisogno di premere un tasto.
# La mozzarella vaccina/mista ha una sezione dedicata sotto,
# per via della formula di resa combinata (vaccino a meta' peso).
# ============================================================
import streamlit as st
import pandas as pd
import datetime as _dt
import hashlib
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
# BLOCCO: PRODOTTI ATTIVI E CLASSIFICAZIONE
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
    base = f"{p['nome']} (DOP)" if p["is_dop"] else p["nome"]
    return f"⭐{base}" if p.get("stabilisce_resa") else base

def e_mista_o_vaccina(p):
    n = p["nome"].lower()
    return ("mista" in n) or ("vaccin" in n)

prodotti_bufala_famiglia = [p for p in prodotti if not e_mista_o_vaccina(p)]
prodotti_mista_vaccina = [p for p in prodotti if e_mista_o_vaccina(p)]
prodotto_primario_dop = next((p for p in prodotti if p["is_dop"] and p.get("stabilisce_resa")), None)
prodotto_primario_nondop = next((p for p in prodotti if not p["is_dop"] and p.get("stabilisce_resa") and not e_mista_o_vaccina(p)), None)

if not prodotto_primario_dop and "bufala_dop" in tipi_in_uso:
    st.warning("⚠️ Nessun prodotto e' impostato come 'stabilisce la resa' per la Bufala DOP. Vai su Prodotti e spunta questa opzione sulla Mozzarella di Bufala Campana DOP, altrimenti la resa DOP non puo' essere calcolata.")

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
trasformato_map_storico = {(t["tipo_latte"], t["data"]): float(t["kg"] or 0) for t in trasformato_tutti}

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
produzioni_map_storico = {(e["prodotto_id"], e["data"]): e for e in produzioni_esistenti}

origini_tutte = (
    client.table("produzione_origine")
    .select("*")
    .in_("produzione_id", [r["id"] for r in produzioni_esistenti])
    .execute()
    .data
) if produzioni_esistenti else []
origini_map = {}
for o in origini_tutte:
    origini_map.setdefault(o["produzione_id"], {})[o["origine"]] = float(o["kg"] or 0)

mista_vaccina_tutti = (
    client.table("mista_vaccina")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
mv_map = {m["data"]: m for m in mista_vaccina_tutti}

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE TABELLA UNICA (dati correnti, prima delle modifiche)
# ------------------------------------------------------------
righe = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for t in tipi_in_uso:
        riga[f"{t}_trasf"] = trasformato_map_storico.get((t, ds), 0.0)
        riga[f"{t}_venduto"] = venduto_map.get((t, ds), 0.0)
    for p in prodotti_bufala_famiglia:
        rec = produzioni_map_storico.get((p["id"], ds))
        riga[f"p{p['id']}_prod"] = float(rec["kg_totale"]) if rec and rec.get("kg_totale") is not None else 0.0
    righe.append(riga)

df_base = pd.DataFrame(righe)

# ------------------------------------------------------------
# BLOCCO: TABELLA EDITABILE (Trasformato, Venduto, Prodotto)
# ------------------------------------------------------------
st.subheader("Registro")
st.caption("⭐ = prodotto che stabilisce la resa del giorno per la sua categoria di latte. Refrigerato/Ritirato/Resa (sotto) sono calcolati. Modifica le celle: si salva tutto da solo.")

column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for t in tipi_in_uso:
    label = TIPI_LATTE_LABEL[t]
    column_config[f"{t}_trasf"] = st.column_config.NumberColumn(f"{label} - Trasformato", min_value=0.0, step=1.0)
    column_config[f"{t}_venduto"] = st.column_config.NumberColumn(f"{label} - Venduto", min_value=0.0, step=1.0)
for p in prodotti_bufala_famiglia:
    column_config[f"p{p['id']}_prod"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)} - Prodotto", min_value=0.0, step=1.0)

df_modificato = st.data_editor(df_base, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_registro")

# ------------------------------------------------------------
# BLOCCO: AUTO-SALVATAGGIO (nessun tasto, salva quando qualcosa cambia)
# ------------------------------------------------------------
hash_attuale = hashlib.md5(df_modificato.round(3).to_csv().encode()).hexdigest()
if is_owner() and st.session_state.get("registro_ultimo_hash") != hash_attuale:
    record_trasformato, record_venduto, record_produzioni = [], [], []
    for i, d in enumerate(date_periodo):
        ds = str(d)
        for t in tipi_in_uso:
            kg_t = df_modificato.loc[i, f"{t}_trasf"]
            record_trasformato.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(kg_t or 0)})
            kg_v = df_modificato.loc[i, f"{t}_venduto"]
            if kg_v and float(kg_v) > 0:
                record_venduto.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(kg_v)})
        for p in prodotti_bufala_famiglia:
            kg_p = df_modificato.loc[i, f"p{p['id']}_prod"]
            esistente = produzioni_map_storico.get((p["id"], ds))
            record_produzioni.append({
                "caseificio_id": caseificio_id, "prodotto_id": p["id"], "data": ds,
                "kg_totale": float(kg_p or 0),
                "kg_diretta": float(esistente["kg_diretta"]) if esistente and esistente.get("kg_diretta") else 0.0,
                "kg_terzi": float(esistente["kg_terzi"]) if esistente and esistente.get("kg_terzi") else 0.0,
            })
    if record_trasformato:
        client.table("trasformato").upsert(record_trasformato, on_conflict="caseificio_id,tipo_latte,data").execute()
    client.table("latte_venduto").delete().eq("caseificio_id", caseificio_id).gte("data", str(periodo_inizio)).lte("data", str(periodo_fine)).execute()
    if record_venduto:
        client.table("latte_venduto").insert(record_venduto).execute()
    if record_produzioni:
        client.table("produzioni").upsert(record_produzioni, on_conflict="prodotto_id,data").execute()
    st.session_state["registro_ultimo_hash"] = hash_attuale
    st.rerun()

st.session_state["registro_ultimo_hash"] = hash_attuale

st.divider()

# ------------------------------------------------------------
# BLOCCO: RESA DOP E CONSUMO AUTOMATICO PER I PRODOTTI DERIVATI
# ------------------------------------------------------------
trasformato_map = {(t, str(d)): float(df_modificato.loc[i, f"{t}_trasf"] or 0) for i, d in enumerate(date_periodo) for t in tipi_in_uso}
produzioni_map = {}
for i, d in enumerate(date_periodo):
    for p in prodotti_bufala_famiglia:
        produzioni_map[(p["id"], str(d))] = float(df_modificato.loc[i, f"p{p['id']}_prod"] or 0)

def resa_dop(ds):
    if not prodotto_primario_dop:
        return None
    prod = produzioni_map.get((prodotto_primario_dop["id"], ds), 0)
    trasf = trasformato_map.get(("bufala_dop", ds), 0)
    return (prod / trasf) if trasf > 0 else None

def resa_nondop(ds):
    if not prodotto_primario_nondop:
        return None
    prod = produzioni_map.get((prodotto_primario_nondop["id"], ds), 0)
    trasf = trasformato_map.get(("bufala", ds), 0)
    return (prod / trasf) if trasf > 0 else None

consumo_extra = {}
for p in prodotti_bufala_famiglia:
    if p is prodotto_primario_dop:
        continue
    for d in date_periodo:
        ds = str(d)
        prod_kg = produzioni_map.get((p["id"], ds), 0)
        if prod_kg <= 0:
            continue
        rec = produzioni_map_storico.get((p["id"], ds))
        override = origini_map.get(rec["id"]) if rec else None
        if override:
            kg_dop, kg_nondop, kg_semi = override.get("dop", 0), override.get("non_dop", 0), override.get("semilavorato_bufala", 0)
        else:
            # default: tutto attinge alla resa DOP (o non-DOP se e' il prodotto primario non-DOP e non fa parte del DOP)
            kg_dop, kg_nondop, kg_semi = prod_kg, 0, 0
        if kg_dop > 0:
            r = resa_dop(ds)
            if r and r > 0:
                consumo_extra[("bufala_dop", ds)] = consumo_extra.get(("bufala_dop", ds), 0) + kg_dop / r
        if kg_nondop > 0 and p is not prodotto_primario_nondop:
            r = resa_nondop(ds)
            if r and r > 0:
                consumo_extra[("bufala", ds)] = consumo_extra.get(("bufala", ds), 0) + kg_nondop / r
        if kg_semi > 0:
            consumo_extra[("semilavorato_bufala", ds)] = consumo_extra.get(("semilavorato_bufala", ds), 0) + kg_semi

for ds, m in mv_map.items():
    trasf_vacc = float(m["trasformato_vaccino_kg"] or 0)
    trasf_buf_mista = float(m["trasformato_bufala_mista_kg"] or 0)
    prod_vacc = float(m["produzione_vaccina_kg"] or 0)
    prod_mista = float(m["produzione_mista_kg"] or 0)
    denom = (trasf_vacc / 2) + trasf_buf_mista
    if denom > 0:
        resa_c = (prod_vacc + prod_mista) / denom
        if resa_c > 0:
            latte_vacc_per_vaccina = prod_vacc / (resa_c / 2)
            consumo_extra[("vaccino", ds)] = consumo_extra.get(("vaccino", ds), 0) + latte_vacc_per_vaccina + max(trasf_vacc - latte_vacc_per_vaccina, 0)
            consumo_extra[("bufala", ds)] = consumo_extra.get(("bufala", ds), 0) + trasf_buf_mista

# ------------------------------------------------------------
# BLOCCO: CALCOLO GIACENZE (apertura giorno = chiusura giorno precedente)
# ------------------------------------------------------------
tutte_le_date = sorted(set(
    [d for (_, d) in raccolto.keys()] + [str(d) for d in date_periodo]
    + [k[1] for k in venduto_map.keys()] + [k[1] for k in congelato_map.keys()]
))

giacenza_per_tipo = {t: 0.0 for t in tipi_in_uso}
giacenza_per_giorno = {}
for d in tutte_le_date:
    for t in tipi_in_uso:
        giacenza_per_giorno[(t, d)] = giacenza_per_tipo[t]
        entrata = raccolto.get((t, d), 0)
        uscita = trasformato_map.get((t, d), 0) + consumo_extra.get((t, d), 0) + venduto_map.get((t, d), 0)
        if t in ("bufala_dop", "bufala"):
            uscita += congelato_map.get(("bufala_dop" if t == "bufala_dop" else "bufala", d), 0)
        giacenza_per_tipo[t] = giacenza_per_tipo[t] + entrata - uscita

# ------------------------------------------------------------
# BLOCCO: RIEPILOGO REFRIGERATO / RITIRATO / RESA
# ------------------------------------------------------------
st.subheader("Refrigerato, Ritirato e Resa")
riepilogo = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for t in tipi_in_uso:
        label = TIPI_LATTE_LABEL[t]
        riga[f"{label} Refrigerato"] = round(giacenza_per_giorno.get((t, ds), 0.0), 1)
        riga[f"{label} Ritirato"] = round(raccolto.get((t, ds), 0.0), 1)
    r_dop = resa_dop(ds)
    if prodotto_primario_dop:
        riga["Resa DOP"] = f"{r_dop*100:.2f}%" if r_dop else "-"
    r_nondop = resa_nondop(ds)
    if prodotto_primario_nondop:
        riga["Resa non-DOP"] = f"{r_nondop*100:.2f}%" if r_nondop else "-"
    m = mv_map.get(ds, {})
    denom_mv = (float(m.get("trasformato_vaccino_kg", 0) or 0) / 2) + float(m.get("trasformato_bufala_mista_kg", 0) or 0)
    if denom_mv > 0:
        resa_mv = (float(m.get("produzione_vaccina_kg", 0) or 0) + float(m.get("produzione_mista_kg", 0) or 0)) / denom_mv
        riga["Resa mista/vaccina"] = f"{resa_mv*100:.2f}%"
    riepilogo.append(riga)

st.dataframe(riepilogo, use_container_width=True, hide_index=True)

st.divider()

# ------------------------------------------------------------
# BLOCCO: ORIGINE PRODUZIONE - SOLO PER SPOSTAMENTI MANUALI (ECCEZIONE)
# ------------------------------------------------------------
with st.expander("🔧 Sposta manualmente l'origine di un prodotto (eccezione, di default non serve)"):
    st.caption("Per default TUTTA la produzione dei prodotti famiglia bufala (diversi dal prodotto che stabilisce la resa) attinge automaticamente alla resa DOP. Usa questo solo se vuoi spostare una parte su latte non-DOP o semilavorato.")
    prodotti_spostabili = [p for p in prodotti_bufala_famiglia if p is not prodotto_primario_dop]
    righe_con_totale = [(p, d) for p in prodotti_spostabili for d in date_periodo if produzioni_map.get((p["id"], str(d)), 0) > 0]
    if righe_con_totale:
        prod_nome = st.selectbox("Prodotto", sorted({etichetta_prodotto(p) for p, _ in righe_con_totale}), key="orig_prodotto")
        prod_sel = next(p for p, _ in righe_con_totale if etichetta_prodotto(p) == prod_nome)
        date_disp = sorted({d for p, d in righe_con_totale if p["id"] == prod_sel["id"]})
        data_sel = st.selectbox("Data", date_disp, format_func=lambda d: d.strftime("%d/%m/%Y"), key="orig_data")
        rec = produzioni_map_storico.get((prod_sel["id"], str(data_sel)))
        if rec:
            totale_giorno = produzioni_map.get((prod_sel["id"], str(data_sel)), 0)
            origini_attuali = origini_map.get(rec["id"], {})
            st.caption(f"Totale prodotto quel giorno: {totale_giorno} kg")
            if is_owner():
                with st.form("form_origine"):
                    kg_dop = st.number_input("Fatta con latte DOP (kg)", min_value=0.0, step=1.0, value=origini_attuali.get("dop", 0.0))
                    kg_nondop = st.number_input("Fatta con latte non-DOP (kg)", min_value=0.0, step=1.0, value=origini_attuali.get("non_dop", 0.0))
                    kg_semi = st.number_input("Fatta con semilavorato (kg)", min_value=0.0, step=1.0, value=origini_attuali.get("semilavorato_bufala", 0.0))
                    if st.form_submit_button("Salva origine"):
                        for origine, kg in [("dop", kg_dop), ("non_dop", kg_nondop), ("semilavorato_bufala", kg_semi)]:
                            client.table("produzione_origine").upsert({"produzione_id": rec["id"], "origine": origine, "kg": kg}, on_conflict="produzione_id,origine").execute()
                        st.success("Salvato.")
                        st.rerun()
    else:
        st.write("Nessun prodotto con produzione da spostare nel periodo.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: MOZZARELLA VACCINA E MISTA
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
            st.caption(f"Resa combinata: {resa_c*100:.2f}%")
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
