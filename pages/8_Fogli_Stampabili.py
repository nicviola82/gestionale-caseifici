# ============================================================
# PAGINA: FOGLI STAMPABILI
# Genera i documenti ufficiali RINA (MBC, poi RBC/tr) compilati
# per una singola giornata, pronti da scaricare e stampare.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button
from stampa_mbc import genera_mbc

st.set_page_config(page_title="Fogli Stampabili", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Fogli Stampabili")
st.caption("Genera i documenti ufficiali (MBC, RBC, tr) compilati con i dati del giorno scelto.")

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

data_giorno = st.date_input("Giorno da stampare", value=_dt.date.today())

st.divider()

# ------------------------------------------------------------
# BLOCCO: GENERAZIONE MBC
# ------------------------------------------------------------
st.subheader("MBC - Registro Mozzarella")
if st.button("📄 Genera MBC"):
    output_path = f"MBC_{data_giorno.strftime('%Y%m%d')}.xlsx"
    genera_mbc(client, caseificio_id, data_giorno, output_path)
    with open(output_path, "rb") as f:
        st.download_button(
            "⬇️ Scarica MBC compilato",
            data=f.read(),
            file_name=output_path,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.success("MBC generato.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: RBC E TR (in arrivo)
# ------------------------------------------------------------
st.subheader("RBC - Registro Ricotta")
st.info("In lavorazione - non ancora disponibile.")

st.subheader("tr - Tabellone giornaliero")
st.info("In lavorazione - non ancora disponibile.")
