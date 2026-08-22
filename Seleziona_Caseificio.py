# ============================================================
# PAGINA: ANAGRAFICA CASEIFICIO
# Crea, modifica caseificio; gestisce l'elenco refrigeranti.
# ============================================================
import streamlit as st
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Anagrafica Caseificio", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Anagrafica Caseificio")
mostra_header_caseificio()

if not is_owner():
    st.warning("Solo l'amministratore puo' modificare l'anagrafica.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: NUOVO CASEIFICIO
# ------------------------------------------------------------
with st.expander("➕ Nuovo caseificio"):
    with st.form("nuovo_caseificio"):
        ragione_sociale = st.text_input("Denominazione sociale")
        sede_legale = st.text_input("Sede legale")
        sede_operativa = st.text_input("Sede operativa")
        piva = st.text_input("P.IVA")
        is_dop = st.checkbox("Caseificio linea DOP")

        col1, col2 = st.columns(2)
        with col1:
            aut_852_numero = st.text_input("Autorizzazione 852 - numero")
            aut_852_rilascio = st.date_input("852 - data rilascio", value=None)
            aut_852_scadenza = st.date_input("852 - data scadenza", value=None)
        with col2:
            aut_853_numero = st.text_input("Autorizzazione 853 - numero")
            aut_853_rilascio = st.date_input("853 - data rilascio", value=None)
            aut_853_scadenza = st.date_input("853 - data scadenza", value=None)

        if st.form_submit_button("Salva caseificio"):
            client.table("caseifici").insert({
                "ragione_sociale": ragione_sociale,
                "sede_legale": sede_legale,
                "sede_operativa": sede_operativa,
                "piva": piva,
                "is_dop": is_dop,
                "aut_852_numero": aut_852_numero,
                "aut_852_rilascio": str(aut_852_rilascio) if aut_852_rilascio else None,
                "aut_852_scadenza": str(aut_852_scadenza) if aut_852_scadenza else None,
                "aut_853_numero": aut_853_numero,
                "aut_853_rilascio": str(aut_853_rilascio) if aut_853_rilascio else None,
                "aut_853_scadenza": str(aut_853_scadenza) if aut_853_scadenza else None,
            }).execute()
            st.success("Caseificio creato.")
            st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: DETTAGLIO CASEIFICIO SELEZIONATO
# ------------------------------------------------------------
caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

caseificio = client.table("caseifici").select("*").eq("id", caseificio_id).single().execute().data
st.subheader(f"Dettaglio: {caseificio['ragione_sociale']}")

import datetime as _dt
from ui_helpers import mostra_header_caseificio
oggi = _dt.date.today()
for campo, etichetta in [("aut_852_scadenza", "Autorizzazione 852"), ("aut_853_scadenza", "Autorizzazione 853")]:
    val = caseificio.get(campo)
    if val:
        scadenza = _dt.date.fromisoformat(val)
        if scadenza < oggi:
            st.error(f"⚠️ {etichetta} SCADUTA il {scadenza.strftime('%d/%m/%Y')}")
        elif (scadenza - oggi).days <= 30:
            st.warning(f"⚠️ {etichetta} in scadenza il {scadenza.strftime('%d/%m/%Y')}")

st.write(f"**Sede legale:** {caseificio.get('sede_legale') or '-'}")
st.write(f"**Sede operativa:** {caseificio.get('sede_operativa') or '-'}")
st.write(f"**P.IVA:** {caseificio.get('piva') or '-'}")

st.divider()

# ------------------------------------------------------------
# BLOCCO: REFRIGERANTI
# ------------------------------------------------------------
st.subheader("Refrigeranti (tank di stoccaggio)")

refrigeranti = (
    client.table("refrigeranti")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .order("codice")
    .execute()
    .data
)
if refrigeranti:
    st.table([{"Codice": r["codice"], "Nome": r.get("nome") or "-", "Capienza (kg)": r.get("capienza_kg"), "Attivo": "Sì" if r["attivo"] else "No"} for r in refrigeranti])

with st.expander("➕ Aggiungi refrigerante"):
    with st.form("nuovo_refrigerante"):
        codice = st.text_input("Codice / lettera identificativa")
        nome = st.text_input("Nome refrigerante")
        capienza = st.number_input("Capienza (kg)", min_value=0.0, step=100.0)
        if st.form_submit_button("Salva refrigerante"):
            client.table("refrigeranti").insert({
                "caseificio_id": caseificio_id,
                "codice": codice,
                "nome": nome,
                "capienza_kg": capienza,
            }).execute()
            st.success("Refrigerante aggiunto.")
            st.rerun()
