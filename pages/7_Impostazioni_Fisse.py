# ============================================================
# PAGINA: IMPOSTAZIONI FISSE
# Valori che restano fissi (orari, acidita'/temperatura, dati di
# lavorazione, caglio provvisorio) finche' non vengono modificati:
# ogni modifica vale "da" una data in poi, senza cancellare lo
# storico dei valori precedenti.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Impostazioni Fisse", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Impostazioni Fisse")
st.caption("Ogni valore che imposti resta valido da quella data in poi, finche' non lo modifichi di nuovo. Serve per i fogli stampabili (orari, parametri di lavorazione, caglio).")

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

CAMPI = {
    "ora_ricevimento_latte": "Ora ricevimento latte",
    "ora_inizio_lavorazione": "Ora inizio lavorazione",
    "ora_fine_lavorazione": "Ora fine lavorazione",
    "ora_rottura_cagliata": "Ora rottura cagliata",
    "acidita_primo_siero": "Acidità primo siero (°SH/50ml)",
    "temperatura_latte": "Temperatura latte (°C)",
    "temperatura_attivazione": "Temperatura attivazione (°C)",
    "tipo_siero_innesto": "Tipo siero innesto",
    "temperatura_acqua_filatura": "Temperatura acqua di filatura (°C)",
    "caglio_fornitore": "Caglio - fornitore",
    "caglio_lotto": "Caglio - lotto",
}

def valore_attuale(campo, alla_data=None):
    alla_data = alla_data or _dt.date.today()
    righe = (
        client.table("impostazioni_registro")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("campo", campo)
        .lte("data_da", str(alla_data))
        .order("data_da", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return righe[0] if righe else None

st.subheader("Valori attuali")
righe_attuali = []
for campo, label in CAMPI.items():
    v = valore_attuale(campo)
    righe_attuali.append({
        "Campo": label,
        "Valore attuale": v["valore"] if v else "(non impostato)",
        "In vigore da": v["data_da"] if v else "-",
    })
st.table(righe_attuali)

st.divider()

st.subheader("➕ Imposta / modifica un valore")
if is_owner():
    with st.form("nuova_impostazione"):
        campo_sel = st.selectbox("Campo", list(CAMPI.keys()), format_func=lambda c: CAMPI[c])
        nuovo_valore = st.text_input("Nuovo valore")
        data_da = st.date_input("In vigore da", value=_dt.date.today())
        if st.form_submit_button("Salva"):
            if nuovo_valore.strip():
                client.table("impostazioni_registro").insert({
                    "caseificio_id": caseificio_id, "campo": campo_sel,
                    "valore": nuovo_valore.strip(), "data_da": str(data_da),
                }).execute()
                st.success("Salvato.")
                st.rerun()
            else:
                st.warning("Inserisci un valore.")

st.divider()

st.subheader("Storico modifiche")
storico = (
    client.table("impostazioni_registro")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .order("campo")
    .order("data_da", desc=True)
    .execute()
    .data
)
if storico:
    st.table([{
        "Campo": CAMPI.get(s["campo"], s["campo"]),
        "Valore": s["valore"],
        "In vigore da": s["data_da"],
    } for s in storico])
else:
    st.write("Nessuna impostazione salvata ancora.")
