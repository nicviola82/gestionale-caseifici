# ============================================================
# MODULO: HELPER INTERFACCIA CONDIVISI
# Piccole funzioni riusate da più pagine, per evitare di
# ripetere lo stesso codice ovunque.
# ============================================================
import streamlit as st


def mostra_header_caseificio():
    """Mostra in alto alla pagina il caseificio e il periodo attualmente selezionati
    (presi da app.py/Seleziona_Caseificio.py), se già scelti. Va chiamata subito dopo
    st.title(...) in ogni pagina che lavora su un caseificio specifico."""
    nome = st.session_state.get("caseificio_nome")
    periodo_label = st.session_state.get("periodo_label")
    if nome and periodo_label:
        st.caption(f"📍 Caseificio: **{nome}** — Periodo: **{periodo_label}**")
    elif nome:
        st.caption(f"📍 Caseificio: **{nome}** — nessun periodo confermato")
