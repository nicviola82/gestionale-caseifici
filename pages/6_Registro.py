# ============================================================
# PAGINA: REGISTRO
# Fedele alla struttura del foglio Excel di riferimento:
# per ogni tipo di latte in uso (bufala DOP, bufala, vaccino,
# semilavorato) -> Refrigerato (giacenza calcolata) | Ritirato
# (raccolto quel giorno, da Dati Inseriti, sola lettura) |
# Trasformato (editabile). Per ogni prodotto attivo -> Prodotto
# (editabile, condiviso con la pagina Produzioni).
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

TIPI_LATTE_LABEL = {"bufala_dop": "Bufala DOP", "bufala": "Bufala", "vaccino": "Vaccino", "semilavorato": "Semilavorato"}

# ------------------------------------------------------------
# BLOCCO: LISTA DATE DEL PERIODO
# ------------------------------------------------------------
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
    st.info("Nessun conferitore con un tipo di latte tra Bufala DOP / Bufala / Vaccino / Semilavorato. Vai su 'Conferitori' per impostarli.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: PRODOTTI ATTIVI E VISIBILI
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

# ------------------------------------------------------------
# BLOCCO: DATI STORICI (per calcolare correttamente la giacenza)
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

raccolto = {}
for cf in conferimenti_tutti:
    tipi = tipo_per_conferitore.get(cf["conferitore_id"], [])
    kg = float(cf.get("kg") or 0)
    if kg <= 0:
        continue
    for t in tipi:
        if t in TIPI_LATTE_LABEL:
            raccolto[(t, cf["data"])] = raccolto.get((t, cf["data"]), 0) + kg
for m in movimenti_tutti:
    if m["tipo"] == "scongelamento":
        raccolto[("bufala", m["data"])] = raccolto.get(("bufala", m["data"]), 0) + float(m["kg"])

tutte_le_date = sorted(set([d for (_, d) in raccolto.keys()] + [k[1] for k in trasformato_map.keys()] + [str(d) for d in date_periodo]))

giacenza_per_tipo = {t: 0.0 for t in tipi_in_uso}
giacenza_per_giorno = {}
for d in tutte_le_date:
    for t in tipi_in_uso:
        entrata = raccolto.get((t, d), 0)
        uscita = trasformato_map.get((t, d), 0)
        giacenza_per_tipo[t] = giacenza_per_tipo[t] + entrata - uscita
        giacenza_per_giorno[(t, d)] = giacenza_per_tipo[t]

# ------------------------------------------------------------
# BLOCCO: PRODUZIONI GIA' SALVATE (condivise con la pagina Produzioni)
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
produzioni_map = {(e["prodotto_id"], e["data"]): e for e in produzioni_esistenti}

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE GRIGLIA
# ------------------------------------------------------------
st.subheader("Griglia Registro")
st.caption("Refrigerato e Ritirato sono calcolati (non modificabili). Trasformato = quanto latte metti in lavorazione. Prodotto = quanto hai ottenuto (condiviso con Produzioni). Ricorda 'Salva registro' in fondo.")

righe = []
for d in date_periodo:
    ds = str(d)
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for t in tipi_in_uso:
        riga[f"{t} - Refrigerato"] = round(giacenza_per_giorno.get((t, ds), 0.0), 1)
        riga[f"{t} - Ritirato"] = round(raccolto.get((t, ds), 0.0), 1)
        riga[f"{t} - Trasformato"] = trasformato_map.get((t, ds), 0.0)
    for p in prodotti:
        rec = produzioni_map.get((p["id"], ds))
        riga[f"p{p['id']} - Prodotto"] = float(rec["kg_totale"]) if rec and rec.get("kg_totale") is not None else 0.0
    righe.append(riga)

df = pd.DataFrame(righe)

column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for t in tipi_in_uso:
    label = TIPI_LATTE_LABEL[t]
    column_config[f"{t} - Refrigerato"] = st.column_config.NumberColumn(f"{label}\nRefrigerato", disabled=True)
    column_config[f"{t} - Ritirato"] = st.column_config.NumberColumn(f"{label}\nRitirato", disabled=True)
    column_config[f"{t} - Trasformato"] = st.column_config.NumberColumn(f"{label}\nTrasformato", min_value=0.0, step=1.0)
for p in prodotti:
    column_config[f"p{p['id']} - Prodotto"] = st.column_config.NumberColumn(f"{etichetta_prodotto(p)}\nProdotto", min_value=0.0, step=1.0)

df_modificato = st.data_editor(
    df, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_registro"
)

if is_owner():
    if st.button("💾 Salva registro"):
        record_trasformato = []
        record_produzioni = []
        for i, d in enumerate(date_periodo):
            ds = str(d)
            for t in tipi_in_uso:
                kg = df_modificato.loc[i, f"{t} - Trasformato"]
                if kg and float(kg) > 0:
                    record_trasformato.append({
                        "caseificio_id": caseificio_id, "tipo_latte": t, "data": ds, "kg": float(kg),
                    })
            for p in prodotti:
                kg = df_modificato.loc[i, f"p{p['id']} - Prodotto"]
                if kg and float(kg) > 0:
                    esistente = produzioni_map.get((p["id"], ds))
                    record_produzioni.append({
                        "caseificio_id": caseificio_id,
                        "prodotto_id": p["id"],
                        "data": ds,
                        "kg_totale": float(kg),
                        "kg_diretta": float(esistente["kg_diretta"]) if esistente and esistente.get("kg_diretta") else 0.0,
                        "kg_terzi": float(esistente["kg_terzi"]) if esistente and esistente.get("kg_terzi") else 0.0,
                    })
        if record_trasformato:
            client.table("trasformato").upsert(record_trasformato, on_conflict="caseificio_id,tipo_latte,data").execute()
        if record_produzioni:
            client.table("produzioni").upsert(record_produzioni, on_conflict="prodotto_id,data").execute()
        st.success("Registro salvato.")
        st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: AVVISI
# ------------------------------------------------------------
for t in tipi_in_uso:
    if giacenza_per_tipo[t] < 0:
        st.error(f"⚠️ Giacenza {TIPI_LATTE_LABEL[t]} NEGATIVA: {round(giacenza_per_tipo[t],1)} kg — hai lavorato più latte di quanto disponibile.")

if "bufala_dop" in tipi_in_uso:
    eta_giacenza_dop = None
    giac = 0.0
    for d in tutte_le_date:
        entrata = raccolto.get(("bufala_dop", d), 0)
        uscita = trasformato_map.get(("bufala_dop", d), 0)
        if giac <= 0 and entrata > 0:
            eta_giacenza_dop = d
        if uscita >= giac + entrata:
            eta_giacenza_dop = None
        giac = giac + entrata - uscita
    if eta_giacenza_dop:
        ore_trascorse = (periodo_fine - _dt.date.fromisoformat(eta_giacenza_dop)).days * 24
        if ore_trascorse > 60:
            st.error(f"⚠️ Il latte DOP più vecchio in giacenza risulta del {eta_giacenza_dop} — sono passate più di 60 ore (stima)!")
        elif ore_trascorse > 48:
            st.warning(f"⏰ Il latte DOP più vecchio in giacenza è del {eta_giacenza_dop} — attenzione al limite delle 60 ore (stima).")
