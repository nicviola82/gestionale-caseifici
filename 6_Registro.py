# ============================================================
# PAGINA: REGISTRO
# Solo tabelle, niente moduli. Tabella 1 (editabile): Trasformato
# e Venduto per tipo di latte, Totale prodotto per ogni prodotto
# famiglia bufala (con eventuale quota "fatta con non-DOP" e il
# latte usato per quella quota), e per mista/vaccina il latte
# vaccino/bufala usato. Tabella 2 (sola lettura): Refrigerato,
# Ritirato, Resa, e il latte DOP calcolato automaticamente per
# le quote non spostate.
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
tipi_da_conferitori = {t for tipi in tipo_per_conferitore.values() for t in tipi if t in TIPI_LATTE_LABEL}

movimenti_tutti = (
    client.table("movimenti_congelato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
if any(m["tipo"] == "scongelamento" for m in movimenti_tutti):
    tipi_da_conferitori.add("bufala")

tipi_in_uso = [t for t in TIPI_LATTE_LABEL if t in tipi_da_conferitori]
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
if not prodotti:
    st.info("Nessun prodotto attivo/visibile in Produzioni. Vai su 'Prodotti' per attivarne uno.")
    st.stop()

def etichetta_prodotto(p):
    base = f"{p['nome']} (DOP)" if p["is_dop"] else p["nome"]
    return f"⭐{base}" if p.get("stabilisce_resa") else base

def e_mista_o_vaccina(p):
    n = p["nome"].lower()
    return ("mista" in n) or ("vaccin" in n)

prodotti_bufala_famiglia = [p for p in prodotti if not e_mista_o_vaccina(p)]
prodotti_mista_vaccina = [p for p in prodotti if e_mista_o_vaccina(p) and (("vaccino" in tipi_in_uso))]
prodotto_primario_dop = next((p for p in prodotti if p["is_dop"] and p.get("stabilisce_resa")), None)
prodotti_derivati = [p for p in prodotti_bufala_famiglia if p is not prodotto_primario_dop]

if not prodotto_primario_dop and "bufala_dop" in tipi_in_uso:
    st.warning("⚠️ Nessun prodotto e' impostato come 'stabilisce la resa' per la Bufala DOP. Vai su Prodotti e spuntalo sulla Mozzarella di Bufala Campana DOP.")

# ------------------------------------------------------------
# BLOCCO: DATI ESISTENTI DEL PERIODO (per popolare la tabella)
# ------------------------------------------------------------
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
    origini_map.setdefault(o["produzione_id"], {})[o["origine"]] = o

trasformato_tutti = (
    client.table("trasformato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
trasformato_map_storico = {(t["tipo_latte"], t["data"]): float(t["kg"] or 0) for t in trasformato_tutti}

venduto_tutti_periodo = (
    client.table("latte_venduto")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
venduto_map_storico = {}
for v in venduto_tutti_periodo:
    venduto_map_storico[(v["tipo_latte"], v["data"])] = venduto_map_storico.get((v["tipo_latte"], v["data"]), 0) + float(v["kg"] or 0)

# ------------------------------------------------------------
# BLOCCO: TABELLA 1 - INSERIMENTO (editabile)
# ------------------------------------------------------------
st.subheader("Tabella lavorazione (scrivi direttamente nelle celle)")
st.caption("⭐ = prodotto che stabilisce la resa DOP. Per i prodotti derivati: 'conNonDOP' = quanti kg di quel prodotto sono fatti con latte non-DOP invece che DOP; 'LatteNonDOP' = quanto latte non-DOP hai messo in lavorazione per quella quota (lo decidi tu). Il resto resta automaticamente attribuito al DOP.")

righe = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for t in tipi_in_uso:
        riga[f"t_{t}_trasf"] = trasformato_map_storico.get((t, ds), 0.0)
        riga[f"t_{t}_vend"] = venduto_map_storico.get((t, ds), 0.0)
    for p in prodotti_bufala_famiglia:
        rec = produzioni_map_storico.get((p["id"], ds))
        riga[f"p_{p['id']}_tot"] = float(rec["kg_totale"]) if rec and rec.get("kg_totale") is not None else 0.0
        if p is not prodotto_primario_dop:
            ov = origini_map.get(rec["id"], {}).get("non_dop") if rec else None
            riga[f"p_{p['id']}_connondop"] = float(ov["kg"]) if ov and ov.get("kg") else 0.0
            riga[f"p_{p['id']}_lattenondop"] = float(ov["kg_latte"]) if ov and ov.get("kg_latte") else 0.0
    for p in prodotti_mista_vaccina:
        rec = produzioni_map_storico.get((p["id"], ds))
        riga[f"p_{p['id']}_tot"] = float(rec["kg_totale"]) if rec and rec.get("kg_totale") is not None else 0.0
        ov_map = origini_map.get(rec["id"], {}) if rec else {}
        riga[f"p_{p['id']}_lattevacc"] = float(ov_map.get("vaccino", {}).get("kg_latte") or 0) if ov_map.get("vaccino") else 0.0
        riga[f"p_{p['id']}_lattebuf"] = float(ov_map.get("bufala", {}).get("kg_latte") or 0) if ov_map.get("bufala") else 0.0
    righe.append(riga)

df = pd.DataFrame(righe)
column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for t in tipi_in_uso:
    label = TIPI_LATTE_LABEL[t]
    column_config[f"t_{t}_trasf"] = st.column_config.NumberColumn(f"{label} Trasf.", min_value=0.0, step=1.0)
    column_config[f"t_{t}_vend"] = st.column_config.NumberColumn(f"{label} Venduto", min_value=0.0, step=1.0)
for p in prodotti_bufala_famiglia:
    column_config[f"p_{p['id']}_tot"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)} Tot.", min_value=0.0, step=1.0)
    if p is not prodotto_primario_dop:
        column_config[f"p_{p['id']}_connondop"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)} conNonDOP", min_value=0.0, step=1.0)
        column_config[f"p_{p['id']}_lattenondop"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)} LatteNonDOP", min_value=0.0, step=1.0)
for p in prodotti_mista_vaccina:
    column_config[f"p_{p['id']}_tot"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)} Tot.", min_value=0.0, step=1.0)
    column_config[f"p_{p['id']}_lattevacc"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)} LatteVaccino", min_value=0.0, step=1.0)
    column_config[f"p_{p['id']}_lattebuf"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)} LatteBufala", min_value=0.0, step=1.0)

df_mod = st.data_editor(df, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_registro")

if is_owner():
    if st.button("💾 Salva registro"):
        record_trasf, record_vend, record_prod = [], [], []
        for i, d in enumerate(date_periodo):
            ds = str(d)
            for t in tipi_in_uso:
                record_trasf.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(df_mod.loc[i, f"t_{t}_trasf"] or 0)})
                kg_v = df_mod.loc[i, f"t_{t}_vend"]
                if kg_v and float(kg_v) > 0:
                    record_vend.append({"caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(kg_v)})
            for p in prodotti_bufala_famiglia + prodotti_mista_vaccina:
                esistente = produzioni_map_storico.get((p["id"], ds))
                kg_tot = float(df_mod.loc[i, f"p_{p['id']}_tot"] or 0)
                record_prod.append({
                    "caseificio_id": caseificio_id, "prodotto_id": p["id"], "data": ds, "kg_totale": kg_tot,
                    "kg_diretta": float(esistente["kg_diretta"]) if esistente and esistente.get("kg_diretta") else 0.0,
                    "kg_terzi": float(esistente["kg_terzi"]) if esistente and esistente.get("kg_terzi") else 0.0,
                })
        if record_trasf:
            client.table("trasformato").upsert(record_trasf, on_conflict="caseificio_id,tipo_latte,data").execute()
        client.table("latte_venduto").delete().eq("caseificio_id", caseificio_id).gte("data", str(periodo_inizio)).lte("data", str(periodo_fine)).execute()
        if record_vend:
            client.table("latte_venduto").insert(record_vend).execute()
        if record_prod:
            risultati = client.table("produzioni").upsert(record_prod, on_conflict="prodotto_id,data").execute()
            id_per_prodotto_data = {(r["prodotto_id"], r["data"]): r["id"] for r in risultati.data}
            for i, d in enumerate(date_periodo):
                ds = str(d)
                for p in prodotti_derivati:
                    prod_id = id_per_prodotto_data.get((p["id"], ds))
                    if not prod_id:
                        continue
                    kg_connondop = float(df_mod.loc[i, f"p_{p['id']}_connondop"] or 0)
                    kg_lattenondop = float(df_mod.loc[i, f"p_{p['id']}_lattenondop"] or 0)
                    client.table("produzione_origine").upsert({
                        "produzione_id": prod_id, "origine": "non_dop", "kg": kg_connondop, "kg_latte": kg_lattenondop,
                    }, on_conflict="produzione_id,origine").execute()
                for p in prodotti_mista_vaccina:
                    prod_id = id_per_prodotto_data.get((p["id"], ds))
                    if not prod_id:
                        continue
                    kg_lattevacc = float(df_mod.loc[i, f"p_{p['id']}_lattevacc"] or 0)
                    kg_lattebuf = float(df_mod.loc[i, f"p_{p['id']}_lattebuf"] or 0)
                    if kg_lattevacc > 0:
                        client.table("produzione_origine").upsert({"produzione_id": prod_id, "origine": "vaccino", "kg": 0, "kg_latte": kg_lattevacc}, on_conflict="produzione_id,origine").execute()
                    if kg_lattebuf > 0:
                        client.table("produzione_origine").upsert({"produzione_id": prod_id, "origine": "bufala", "kg": 0, "kg_latte": kg_lattebuf}, on_conflict="produzione_id,origine").execute()
        st.success("Registro salvato.")
        st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: RICALCOLO CON I DATI SALVATI (per Refrigerato/Ritirato/Resa)
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

produzioni_periodo = (
    client.table("produzioni")
    .select("*")
    .in_("prodotto_id", prodotto_ids)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .execute()
    .data
) if prodotto_ids else []
produzioni_map = {(e["prodotto_id"], e["data"]): e for e in produzioni_periodo}

origini_map2 = {}
for o in (client.table("produzione_origine").select("*").in_("produzione_id", [r["id"] for r in produzioni_periodo]).execute().data if produzioni_periodo else []):
    origini_map2.setdefault(o["produzione_id"], {})[o["origine"]] = o

def resa_dop(ds):
    if not prodotto_primario_dop:
        return None
    rec = produzioni_map.get((prodotto_primario_dop["id"], ds))
    prod = float(rec["kg_totale"]) if rec else 0
    trasf = trasformato_map.get(("bufala_dop", ds), 0)
    return (prod / trasf) if trasf > 0 else None

consumo_extra = {}
for p in prodotti_derivati:
    for d in date_periodo:
        ds = str(d)
        rec = produzioni_map.get((p["id"], ds))
        if not rec:
            continue
        tot = float(rec["kg_totale"] or 0)
        if tot <= 0:
            continue
        ov = origini_map2.get(rec["id"], {}).get("non_dop")
        kg_nondop = float(ov["kg"]) if ov and ov.get("kg") else 0.0
        kg_latte_nondop = float(ov["kg_latte"]) if ov and ov.get("kg_latte") else 0.0
        kg_dop = tot - kg_nondop
        if kg_nondop > 0:
            trasformato_map[("bufala", ds)] = trasformato_map.get(("bufala", ds), 0) + kg_latte_nondop
        if kg_dop > 0:
            r = resa_dop(ds)
            if r and r > 0:
                consumo_extra[("bufala_dop", ds)] = consumo_extra.get(("bufala_dop", ds), 0) + kg_dop / r

for p in prodotti_mista_vaccina:
    for d in date_periodo:
        ds = str(d)
        rec = produzioni_map.get((p["id"], ds))
        if not rec:
            continue
        ov_map = origini_map2.get(rec["id"], {})
        kg_vacc = float(ov_map.get("vaccino", {}).get("kg_latte") or 0) if ov_map.get("vaccino") else 0.0
        kg_buf = float(ov_map.get("bufala", {}).get("kg_latte") or 0) if ov_map.get("bufala") else 0.0
        if kg_vacc > 0:
            trasformato_map[("vaccino", ds)] = trasformato_map.get(("vaccino", ds), 0) + kg_vacc
        if kg_buf > 0:
            trasformato_map[("bufala", ds)] = trasformato_map.get(("bufala", ds), 0) + kg_buf

tutte_le_date = sorted(set(
    [d for (_, d) in raccolto.keys()] + [d for (_, d) in trasformato_map.keys()]
    + [d for (_, d) in venduto_map.keys()] + [d for (_, d) in congelato_map.keys()]
    + [d for (_, d) in consumo_extra.keys()] + [str(d) for d in date_periodo]
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
# BLOCCO: TABELLA 2 - RIEPILOGO (sola lettura)
# ------------------------------------------------------------
st.subheader("Riepilogo (calcolato)")
riepilogo = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for t in tipi_in_uso:
        label = TIPI_LATTE_LABEL[t]
        riga[f"{label} Refr."] = round(giacenza_per_giorno.get((t, ds), 0.0), 1)
        riga[f"{label} Rit."] = round(raccolto.get((t, ds), 0.0), 1)
    r_dop = resa_dop(ds)
    if prodotto_primario_dop:
        riga["Resa DOP"] = f"{r_dop*100:.2f}%" if r_dop else "-"
    for p in prodotti_derivati:
        rec = produzioni_map.get((p["id"], ds))
        if rec and float(rec.get("kg_totale") or 0) > 0:
            ov = origini_map2.get(rec["id"], {}).get("non_dop")
            kg_nondop = float(ov["kg"]) if ov and ov.get("kg") else 0.0
            kg_dop_prod = float(rec["kg_totale"]) - kg_nondop
            r = resa_dop(ds)
            latte_dop_calc = (kg_dop_prod / r) if r and r > 0 else None
            riga[f"{p['nome']} LatteDOP calc."] = round(latte_dop_calc, 1) if latte_dop_calc is not None else "-"
    riepilogo.append(riga)
st.dataframe(riepilogo, use_container_width=True, hide_index=True)

st.divider()

# ------------------------------------------------------------
# BLOCCO: AVVISI
# ------------------------------------------------------------
for t in tipi_in_uso:
    if giacenza_per_tipo[t] < 0:
        st.error(f"⚠️ Giacenza {TIPI_LATTE_LABEL[t]} NEGATIVA: {round(giacenza_per_tipo[t],1)} kg.")

if "bufala_dop" in tipi_in_uso:
    eta, giac = None, 0.0
    for d in tutte_le_date:
        entrata = raccolto.get(("bufala_dop", d), 0)
        uscita = trasformato_map.get(("bufala_dop", d), 0) + consumo_extra.get(("bufala_dop", d), 0) + venduto_map.get(("bufala_dop", d), 0) + congelato_map.get(("bufala_dop", d), 0)
        if giac <= 0 and entrata > 0:
            eta = d
        if uscita >= giac + entrata:
            eta = None
        giac = giac + entrata - uscita
    if eta:
        ore = (periodo_fine - _dt.date.fromisoformat(eta)).days * 24
        if ore > 60:
            st.error(f"⚠️ Il latte DOP più vecchio in giacenza risulta del {eta} — più di 60 ore (stima)!")
        elif ore > 48:
            st.warning(f"⏰ Il latte DOP più vecchio in giacenza è del {eta} — attenzione alle 60 ore (stima).")
