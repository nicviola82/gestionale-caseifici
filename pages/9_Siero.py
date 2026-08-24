# ============================================================
# PAGINA: SIERO
# Riepilogo del PERIODO selezionato (non più del solo giorno):
# siero DOP/totale, giacenza cumulativa, consumo per Ricotta di
# Bufala Campana DOP, smaltimento.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner
from siero import (
    siero_dop_prodotto_periodo, siero_totale_prodotto_periodo,
    siero_utilizzato_ricotta_dop_periodo, giacenza_siero_dop, giacenza_siero_totale,
    get_smaltimenti_periodo,
)
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Siero", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Siero")
mostra_header_caseificio()
st.caption("Il siero è per differenza tra latte trasformato e prodotto ottenuto. Giacenza calcolata su tutta la storia.")

caseificio_id = st.session_state.get("caseificio_id")
periodo_inizio = st.session_state.get("periodo_inizio")
periodo_fine = st.session_state.get("periodo_fine")

if not caseificio_id or not periodo_inizio:
    st.info("Seleziona caseificio e periodo dalla pagina principale prima di continuare.")
    st.stop()

st.caption(f"Periodo: {st.session_state.get('periodo_label')}")

st.warning(
    "⚠️ Il calcolo del siero DOP/totale dipende dal 'latte trasformato' che oggi arriva dal Registro attuale, "
    "non ancora ricollegato a questo modulo - i valori sotto risultano 0 finché non verrà completato."
)

st.divider()

# ------------------------------------------------------------
# BLOCCO: SIERO DOP DEL PERIODO
# ------------------------------------------------------------
st.subheader("Siero DOP (per la Ricotta di Bufala Campana DOP)")

siero_dop_periodo = siero_dop_prodotto_periodo(client, caseificio_id, periodo_inizio, periodo_fine)
ricotta_dop_periodo, utilizzato_periodo, errore_resa = siero_utilizzato_ricotta_dop_periodo(
    client, caseificio_id, periodo_inizio, periodo_fine
)
apertura = giacenza_siero_dop(client, caseificio_id, periodo_inizio, includi_giorno=False)
disponibile = apertura + siero_dop_periodo
chiusura = disponibile - utilizzato_periodo

col1, col2, col3, col4 = st.columns(4)
col1.metric("Giacenza apertura periodo", f"{apertura:.1f} kg")
col2.metric("Siero DOP prodotto nel periodo", f"{siero_dop_periodo:.1f} kg")
col3.metric("Ricotta DOP dichiarata nel periodo", f"{ricotta_dop_periodo:.1f} kg")
col4.metric("Giacenza chiusura periodo", f"{chiusura:.1f} kg")

if errore_resa:
    st.error(f"⚠️ {errore_resa}")
elif utilizzato_periodo > disponibile:
    st.warning(
        f"⚠️ La Ricotta DOP dichiarata nel periodo richiede {utilizzato_periodo:.1f} kg di siero, "
        f"ma la giacenza disponibile (apertura + prodotto nel periodo) è {disponibile:.1f} kg. "
        f"Il programma NON blocca: puoi comunque procedere attingendo alla giacenza storica."
    )

st.divider()

# ------------------------------------------------------------
# BLOCCO: SIERO TOTALE E SMALTIMENTO (PERIODO)
# ------------------------------------------------------------
st.subheader("Siero totale e smaltimento")

siero_totale_periodo = siero_totale_prodotto_periodo(client, caseificio_id, periodo_inizio, periodo_fine)
giacenza_totale = giacenza_siero_totale(client, caseificio_id, periodo_fine, includi_giorno=True)

col1, col2 = st.columns(2)
col1.metric("Siero totale prodotto nel periodo (tutto il latte)", f"{siero_totale_periodo:.1f} kg")
col2.metric("Giacenza totale disponibile per lo smaltimento", f"{giacenza_totale:.1f} kg")

smaltimenti_periodo = get_smaltimenti_periodo(client, caseificio_id, periodo_inizio, periodo_fine)
if smaltimenti_periodo:
    st.table([{
        "Data": _dt.date.fromisoformat(s["data"]).strftime("%d/%m/%Y"),
        "Azienda": s["azienda"], "Categoria": s.get("categoria") or "-", "KG": s["kg"],
    } for s in smaltimenti_periodo])
    tot_smaltito_periodo = sum(float(s["kg"]) for s in smaltimenti_periodo)
    st.caption(f"Totale smaltito nel periodo: {tot_smaltito_periodo:.1f} kg su {len(smaltimenti_periodo)} conferimento/i.")
else:
    st.write("Nessuno smaltimento registrato in questo periodo.")

if is_owner():
    with st.form("nuovo_smaltimento"):
        st.write("➕ Registra smaltimento")
        data_smalt = st.date_input(
            "Data", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine, format="DD/MM/YYYY"
        )
        azienda = st.text_input("Azienda di smaltimento")
        categoria = st.text_input("Categoria (es. 'categoria 3')", value="categoria 3")
        kg = st.number_input("KG smaltiti", min_value=0.0, step=1.0)
        if st.form_submit_button("Salva smaltimento"):
            if azienda and kg > 0:
                client.table("smaltimento_siero").insert({
                    "caseificio_id": caseificio_id, "data": str(data_smalt),
                    "azienda": azienda, "categoria": categoria or None, "kg": kg,
                }).execute()
                st.success("Smaltimento registrato.")
                st.rerun()
            else:
                st.warning("Inserisci azienda e kg.")
