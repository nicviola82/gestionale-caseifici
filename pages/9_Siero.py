# ============================================================
# PAGINA: SIERO
# Riepilogo giornaliero siero DOP/totale, giacenza cumulativa,
# consumo per Ricotta di Bufala Campana DOP, smaltimento.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner
from siero import (
    siero_dop_prodotto_giorno, siero_totale_prodotto_giorno,
    siero_utilizzato_ricotta_dop_giorno, giacenza_siero_dop, giacenza_siero_totale,
    get_ricotta_dop_giorno, get_smaltimenti_giorno,
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
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

st.warning(
    "⚠️ Il calcolo del siero DOP/totale dipende dal 'latte trasformato' che oggi arriva dal Registro attuale, "
    "non ancora ricollegato a questo modulo - i valori sotto risultano 0 finché non verrà completato."
)

data_giorno = st.date_input("Giorno", value=_dt.date.today())

st.divider()

# ------------------------------------------------------------
# BLOCCO: SIERO DOP DEL GIORNO
# ------------------------------------------------------------
st.subheader("Siero DOP (per la Ricotta di Bufala Campana DOP)")

siero_dop_oggi = siero_dop_prodotto_giorno(client, caseificio_id, data_giorno)
utilizzato_oggi, errore_resa = siero_utilizzato_ricotta_dop_giorno(client, caseificio_id, data_giorno)
ricotta_dop_oggi, _ = get_ricotta_dop_giorno(client, caseificio_id, data_giorno)
apertura = giacenza_siero_dop(client, caseificio_id, data_giorno, includi_giorno=False)
disponibile = apertura + siero_dop_oggi
chiusura = disponibile - utilizzato_oggi

col1, col2, col3, col4 = st.columns(4)
col1.metric("Giacenza apertura", f"{apertura:.1f} kg")
col2.metric("Siero DOP prodotto oggi", f"{siero_dop_oggi:.1f} kg")
col3.metric("Ricotta DOP dichiarata", f"{ricotta_dop_oggi:.1f} kg")
col4.metric("Giacenza chiusura", f"{chiusura:.1f} kg")

if errore_resa:
    st.error(f"⚠️ {errore_resa}")
elif utilizzato_oggi > disponibile:
    st.warning(
        f"⚠️ La Ricotta DOP dichiarata oggi richiede {utilizzato_oggi:.1f} kg di siero, "
        f"ma la giacenza disponibile (apertura + prodotto oggi) è {disponibile:.1f} kg. "
        f"Il programma NON blocca: puoi comunque procedere attingendo alla giacenza storica."
    )

st.divider()

# ------------------------------------------------------------
# BLOCCO: SIERO TOTALE E SMALTIMENTO
# ------------------------------------------------------------
st.subheader("Siero totale e smaltimento")

siero_totale_oggi = siero_totale_prodotto_giorno(client, caseificio_id, data_giorno)
giacenza_totale = giacenza_siero_totale(client, caseificio_id, data_giorno, includi_giorno=True)

col1, col2 = st.columns(2)
col1.metric("Siero totale prodotto oggi (tutto il latte)", f"{siero_totale_oggi:.1f} kg")
col2.metric("Giacenza totale disponibile per lo smaltimento", f"{giacenza_totale:.1f} kg")

smaltimenti_oggi = get_smaltimenti_giorno(client, caseificio_id, data_giorno)
if smaltimenti_oggi:
    st.table([{"Azienda": s["azienda"], "Categoria": s.get("categoria") or "-", "KG": s["kg"]} for s in smaltimenti_oggi])
    tot_smaltito_oggi = sum(float(s["kg"]) for s in smaltimenti_oggi)
    st.caption(f"Totale smaltito oggi: {tot_smaltito_oggi:.1f} kg su {len(smaltimenti_oggi)} conferimento/i.")

if is_owner():
    with st.form("nuovo_smaltimento"):
        st.write("➕ Registra smaltimento (puoi aggiungerne più di uno per lo stesso giorno)")
        azienda = st.text_input("Azienda di smaltimento")
        categoria = st.text_input("Categoria (es. 'categoria 3')", value="categoria 3")
        kg = st.number_input("KG smaltiti", min_value=0.0, step=1.0)
        if st.form_submit_button("Salva smaltimento"):
            if azienda and kg > 0:
                client.table("smaltimento_siero").insert({
                    "caseificio_id": caseificio_id, "data": str(data_giorno),
                    "azienda": azienda, "categoria": categoria or None, "kg": kg,
                }).execute()
                st.success("Smaltimento registrato.")
                st.rerun()
            else:
                st.warning("Inserisci azienda e kg.")
