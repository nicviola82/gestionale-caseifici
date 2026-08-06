# ============================================================
# PAGINA PRINCIPALE
# Login, poi tendina per scegliere con quale caseificio lavorare.
# ============================================================
import streamlit as st
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Gestionale Caseifici", layout="wide")

if not login_form():
    st.stop()

logout_button()
client = get_client()

st.title("Gestionale Caseifici")

# ------------------------------------------------------------
# BLOCCO: TENDINA SELEZIONE CASEIFICIO
# ------------------------------------------------------------
query = client.table("caseifici").select("id, ragione_sociale, is_dop")

if not is_owner():
    abilitati = st.session_state.get("caseifici_abilitati") or []
    if not abilitati:
        st.warning("Non sei abilitato a nessun caseificio. Contatta l'amministratore.")
        st.stop()
    query = query.in_("id", abilitati)

caseifici = query.order("ragione_sociale").execute().data

if not caseifici:
    st.info("Nessun caseificio presente. Usa 'Anagrafica Caseificio' nel menu a sinistra per crearne uno.")
else:
    opzioni = {f"{c['ragione_sociale']} {'(DOP)' if c['is_dop'] else ''}": c["id"] for c in caseifici}
    scelta = st.selectbox("Seleziona il caseificio con cui vuoi lavorare", list(opzioni.keys()))
    st.session_state["caseificio_id"] = opzioni[scelta]
    st.session_state["caseificio_nome"] = scelta
    st.success(f"Stai lavorando su: {scelta}")

st.caption("Usa il menu a sinistra per Anagrafica, Conferitori e Prodotti.")
