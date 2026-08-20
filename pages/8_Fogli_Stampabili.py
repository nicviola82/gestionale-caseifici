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
from stampa_rbc import genera_rbc
from stampa_tr import genera_tr

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
# BLOCCO: GENERAZIONE MBC + RBC
# RBC va compilato sullo stesso file di MBC: sul foglio RBC,
# Scheda N. e Data sono formule che puntano a MBC dello stesso
# workbook (=MBC!C3 / =MBC!H3), quindi le due generazioni non
# possono essere separate in due file diversi.
# ------------------------------------------------------------
st.subheader("MBC + RBC - Registri Mozzarella e Ricotta")
if st.button("📄 Genera MBC + RBC del giorno"):
    output_path = f"Scheda_{data_giorno.strftime('%Y%m%d')}.xlsx"
    genera_mbc(client, caseificio_id, data_giorno, output_path)
    genera_rbc(client, caseificio_id, data_giorno, output_path)
    with open(output_path, "rb") as f:
        st.download_button(
            "⬇️ Scarica scheda compilata (MBC + RBC)",
            data=f.read(),
            file_name=output_path,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.success("MBC e RBC generati.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: TR (righe dinamiche in base ai conferitori attivi)
# ------------------------------------------------------------
st.subheader("tr - Tabellone giornaliero")
st.caption("Le righe dei conferitori vengono generate solo per chi ha effettivamente conferito quel giorno.")
if st.button("📄 Genera tr del giorno"):
    output_path_tr = f"tr_{data_giorno.strftime('%Y%m%d')}.xlsx"
    genera_tr(client, caseificio_id, data_giorno, output_path_tr)
    with open(output_path_tr, "rb") as f:
        st.download_button(
            "⬇️ Scarica tr compilato",
            data=f.read(),
            file_name=output_path_tr,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.success("tr generato.")
