# ============================================================
# PAGINA PRINCIPALE: SELEZIONA CASEIFICIO
# Login, poi tendina per scegliere il caseificio, poi scelta
# del periodo di lavoro (settimana o mese). Solo l'owner puo'
# anche eliminare un caseificio dalla tendina.
#
# NOTA: questo file sostituisce il precedente "app.py" (rinominato
# per mostrare "Seleziona Caseificio" nel menu laterale invece di
# "app") - va impostato come "Main file path" nelle impostazioni
# dell'app su Streamlit Cloud al posto di app.py.
# ============================================================
import streamlit as st
import datetime as _dt
import calendar
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
    st.stop()

opzioni = {f"{c['ragione_sociale']} {'(DOP)' if c['is_dop'] else ''}": c["id"] for c in caseifici}
scelta = st.selectbox("Seleziona il caseificio con cui vuoi lavorare", list(opzioni.keys()))
nuovo_caseificio_id = opzioni[scelta]

if st.session_state.get("caseificio_id") != nuovo_caseificio_id:
    for k in ["periodo_inizio", "periodo_fine", "periodo_label"]:
        st.session_state.pop(k, None)

st.session_state["caseificio_id"] = nuovo_caseificio_id
st.session_state["caseificio_nome"] = scelta

# ------------------------------------------------------------
# BLOCCO: ELIMINA CASEIFICIO (solo owner)
# Richiede conferma esplicita (scrivere la ragione sociale) prima
# di procedere, essendo un'operazione distruttiva e irreversibile.
# ------------------------------------------------------------
if is_owner():
    with st.expander("🗑️ Elimina questo caseificio"):
        st.warning(
            f"Stai per eliminare **{scelta}** in modo definitivo. "
            "Se ci sono dati collegati (conferitori, prodotti, produzioni, ecc.) "
            "l'eliminazione potrebbe non essere completa o essere rifiutata dal database."
        )
        conferma_testo = st.text_input(
            "Per confermare, scrivi esattamente la ragione sociale qui sotto:",
            key="conferma_elimina_caseificio",
        )
        if st.button("Elimina definitivamente", type="primary", key="btn_elimina_caseificio"):
            ragione_sociale_attesa = scelta.replace(" (DOP)", "").strip()
            if conferma_testo.strip() != ragione_sociale_attesa:
                st.error("Il testo scritto non corrisponde esattamente alla ragione sociale. Eliminazione annullata.")
            else:
                try:
                    client.table("caseifici").delete().eq("id", nuovo_caseificio_id).execute()
                    st.session_state.pop("caseificio_id", None)
                    st.session_state.pop("caseificio_nome", None)
                    for k in ["periodo_inizio", "periodo_fine", "periodo_label"]:
                        st.session_state.pop(k, None)
                    st.success("Caseificio eliminato.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Impossibile eliminare: probabilmente ci sono ancora dati collegati (conferitori, prodotti, ecc.). Dettaglio: {e}")

st.divider()

# ------------------------------------------------------------
# BLOCCO: SCELTA PERIODO DI LAVORO (SETTIMANA O MESE)
# ------------------------------------------------------------
st.subheader("Periodo di lavoro")

oggi = _dt.date.today()
tipo_periodo = st.radio("Vuoi lavorare a settimana o a mese?", ["Settimana", "Mese"], horizontal=True)

col1, col2 = st.columns(2)
with col1:
    anno = st.number_input("Anno", min_value=2020, max_value=2100, value=oggi.year, step=1)

if tipo_periodo == "Mese":
    mesi_nomi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    with col2:
        mese = st.selectbox("Mese", list(range(1, 13)), format_func=lambda m: mesi_nomi[m - 1], index=oggi.month - 1)
    periodo_inizio = _dt.date(int(anno), mese, 1)
    periodo_fine = _dt.date(int(anno), mese, calendar.monthrange(int(anno), mese)[1])
    periodo_label = f"{mesi_nomi[mese - 1]} {anno}"
else:
    settimana_default = oggi.isocalendar()[1]
    with col2:
        settimana = st.number_input("Numero settimana (1-53)", min_value=1, max_value=53, value=settimana_default, step=1)
    periodo_inizio = _dt.date.fromisocalendar(int(anno), int(settimana), 1)
    periodo_fine = _dt.date.fromisocalendar(int(anno), int(settimana), 7)
    periodo_label = f"Settimana {settimana} del {anno} ({periodo_inizio.strftime('%d/%m')} - {periodo_fine.strftime('%d/%m')})"

if st.button("Conferma periodo"):
    st.session_state["periodo_inizio"] = periodo_inizio
    st.session_state["periodo_fine"] = periodo_fine
    st.session_state["periodo_label"] = periodo_label
    st.rerun()

if "periodo_label" in st.session_state:
    st.success(f"✅ Stai lavorando su **{st.session_state['caseificio_nome']}** — periodo: **{st.session_state['periodo_label']}**")
    st.caption("Usa il menu a sinistra per Anagrafica, Conferitori, Prodotti e Dati Inseriti.")
else:
    st.info("Conferma il periodo per poter usare le altre pagine (Dati Inseriti, ecc.).")
