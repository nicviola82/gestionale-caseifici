# ============================================================
# PAGINA: DATI INSERITI
# Griglia stile Excel: conferitori attivi (in ordine) in colonna
# con DDT/KG, date del periodo scelto in riga. Totali per
# conferitore e per tipo di latte. Movimenti congelato.
# ============================================================
import streamlit as st
import pandas as pd
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Dati Inseriti", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Dati Inseriti")

caseificio_id = st.session_state.get("caseificio_id")
periodo_inizio = st.session_state.get("periodo_inizio")
periodo_fine = st.session_state.get("periodo_fine")

if not caseificio_id or not periodo_inizio:
    st.info("Seleziona caseificio e periodo dalla pagina principale prima di continuare.")
    st.stop()

st.caption(f"Periodo: {st.session_state.get('periodo_label')}")

TIPI_LATTE_LABEL = {
    "bufala_dop": "Bufala DOP", "bufala": "Bufala", "vaccino": "Vaccino",
    "cagliata_bufala": "Cagliata bufala", "cagliata_vaccino": "Cagliata vaccino",
    "bufala_congelato": "Bufala congelato", "vaccino_congelato": "Vaccino congelato", "altro": "Altro",
}

# ------------------------------------------------------------
# BLOCCO: LISTA DATE DEL PERIODO
# ------------------------------------------------------------
n_giorni = (periodo_fine - periodo_inizio).days + 1
date_periodo = [periodo_inizio + _dt.timedelta(days=i) for i in range(n_giorni)]

# ------------------------------------------------------------
# BLOCCO: CONFERITORI ATTIVI IN ORDINE
# ------------------------------------------------------------
conferitori = (
    client.table("conferitori")
    .select("*, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .eq("attivo", True)
    .order("ordine")
    .execute()
    .data
)

if not conferitori:
    st.info("Nessun conferitore attivo. Vai su 'Conferitori' per aggiungerne o attivarne uno.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: CARICA CONFERIMENTI ESISTENTI DEL PERIODO
# ------------------------------------------------------------
conferitore_ids = [c["id"] for c in conferitori]
esistenti = (
    client.table("conferimenti")
    .select("*")
    .in_("conferitore_id", conferitore_ids)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
mappa_esistenti = {(e["conferitore_id"], e["data"]): e for e in esistenti}

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE GRIGLIA
# ------------------------------------------------------------
st.subheader("Griglia conferimenti")
st.caption("Modifica le celle direttamente. Puoi copiare/incollare piu' valori insieme (anche da Excel). Ricorda di premere 'Salva conferimenti' in fondo.")

righe = []
for d in date_periodo:
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for c in conferitori:
        rec = mappa_esistenti.get((c["id"], str(d)))
        riga[f"{c['ragione_sociale']} - DDT"] = rec["ddt"] if rec else ""
        riga[f"{c['ragione_sociale']} - KG"] = float(rec["kg"]) if rec and rec.get("kg") is not None else 0.0
    righe.append(riga)

df = pd.DataFrame(righe)

column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for c in conferitori:
    column_config[f"{c['ragione_sociale']} - DDT"] = st.column_config.TextColumn(f"{c['ragione_sociale']}\nDDT")
    column_config[f"{c['ragione_sociale']} - KG"] = st.column_config.NumberColumn(f"{c['ragione_sociale']}\nKG", min_value=0.0, step=1.0)

df_modificato = st.data_editor(
    df, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_conferimenti"
)

if is_owner():
    if st.button("💾 Salva conferimenti"):
        records = []
        for i, d in enumerate(date_periodo):
            for c in conferitori:
                ddt = df_modificato.loc[i, f"{c['ragione_sociale']} - DDT"]
                kg = df_modificato.loc[i, f"{c['ragione_sociale']} - KG"]
                if (ddt and str(ddt).strip()) or (kg and float(kg) > 0):
                    records.append({
                        "caseificio_id": caseificio_id,
                        "conferitore_id": c["id"],
                        "data": str(d),
                        "ddt": str(ddt) if ddt else None,
                        "kg": float(kg) if kg else 0.0,
                    })
        if records:
            client.table("conferimenti").upsert(records, on_conflict="conferitore_id,data").execute()
            st.success(f"Salvati {len(records)} conferimenti.")
            st.rerun()
        else:
            st.info("Nessun dato da salvare.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: MOVIMENTI LATTE CONGELATO
# ------------------------------------------------------------
st.subheader("❄️ Movimenti latte congelato")
mcol1, mcol2 = st.columns(2)
with mcol1:
    with st.expander("➕ Registra scongelamento (si somma alla Bufala non-DOP)"):
        with st.form("nuovo_scongelamento"):
            data_sc = st.date_input("Data", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine)
            kg_sc = st.number_input("KG scongelati", min_value=0.0, step=1.0)
            note_sc = st.text_input("Nota (facoltativa)")
            if st.form_submit_button("Salva scongelamento"):
                client.table("movimenti_congelato").insert({
                    "caseificio_id": caseificio_id, "data": str(data_sc),
                    "tipo": "scongelamento", "kg": kg_sc, "note": note_sc,
                }).execute()
                st.success("Registrato.")
                st.rerun()
with mcol2:
    with st.expander("➕ Registra congelamento (bufala DOP o non-DOP)"):
        with st.form("nuovo_congelamento"):
            data_cg = st.date_input("Data ", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine)
            origine_cg = st.radio("Origine", ["bufala_dop", "bufala"], format_func=lambda x: "Bufala DOP" if x == "bufala_dop" else "Bufala")
            kg_cg = st.number_input("KG messi in congelamento", min_value=0.0, step=1.0)
            note_cg = st.text_input("Nota (facoltativa) ")
            if st.form_submit_button("Salva congelamento"):
                client.table("movimenti_congelato").insert({
                    "caseificio_id": caseificio_id, "data": str(data_cg),
                    "tipo": "congelamento", "origine": origine_cg, "kg": kg_cg, "note": note_cg,
                }).execute()
                st.success("Registrato.")
                st.rerun()

movimenti = (
    client.table("movimenti_congelato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .order("data")
    .execute()
    .data
)
if movimenti:
    st.table([{
        "Data": _dt.date.fromisoformat(m["data"]).strftime("%d/%m/%Y"),
        "Tipo": "Scongelamento" if m["tipo"] == "scongelamento" else "Congelamento",
        "Origine": ("Bufala DOP" if m.get("origine") == "bufala_dop" else "Bufala") if m.get("origine") else "-",
        "KG": m["kg"],
        "Nota": m.get("note") or "-",
    } for m in movimenti])

st.divider()

# ------------------------------------------------------------
# BLOCCO: TOTALE PER CONFERITORE NEL PERIODO
# ------------------------------------------------------------
st.subheader("Totale per conferitore nel periodo")
totali_conferitore = []
for c in conferitori:
    tot = sum(
        float(mappa_esistenti[(c["id"], str(d))]["kg"] or 0)
        for d in date_periodo if (c["id"], str(d)) in mappa_esistenti
    )
    if tot > 0:
        totali_conferitore.append({"Conferitore": c["ragione_sociale"], "Totale KG periodo": tot})
if totali_conferitore:
    st.table(totali_conferitore)
else:
    st.write("Nessun conferimento ancora registrato in questo periodo.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: TOTALE GIORNALIERO PER TIPO DI LATTE
# ------------------------------------------------------------
st.subheader("Totale giornaliero per tipo di latte")

tipi_presenti = set()
for c in conferitori:
    for t in c.get("conferitori_tipi_latte", []):
        tipi_presenti.add(t["tipo_latte"])

if not tipi_presenti:
    st.write("Nessun tipo di latte associato ai conferitori attivi.")
else:
    scongelamenti_per_giorno = {}
    for m in movimenti:
        if m["tipo"] == "scongelamento":
            scongelamenti_per_giorno[m["data"]] = scongelamenti_per_giorno.get(m["data"], 0) + float(m["kg"])

    righe_tipo = []
    for tipo in sorted(tipi_presenti):
        riga = {"Tipo di latte": TIPI_LATTE_LABEL.get(tipo, tipo)}
        totale_periodo = 0.0
        ha_almeno_un_valore = False
        for d in date_periodo:
            tot_giorno = 0.0
            for c in conferitori:
                tipi_conferitore = [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]
                if tipo in tipi_conferitore:
                    rec = mappa_esistenti.get((c["id"], str(d)))
                    if rec and rec.get("kg"):
                        tot_giorno += float(rec["kg"])
            if tipo == "bufala":
                tot_giorno += scongelamenti_per_giorno.get(str(d), 0.0)
            if tot_giorno > 0:
                ha_almeno_un_valore = True
                riga[d.strftime("%d/%m")] = tot_giorno
            else:
                riga[d.strftime("%d/%m")] = "-"
            totale_periodo += tot_giorno
        riga["Totale periodo"] = totale_periodo
        if ha_almeno_un_valore:
            righe_tipo.append(riga)

    if righe_tipo:
        st.table(righe_tipo)
    else:
        st.write("Nessun conferimento ancora registrato in questo periodo.")
