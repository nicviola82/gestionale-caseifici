# ============================================================
# PAGINA: PRODOTTI
# Elenco prodotti del caseificio, attivazione, tipo lotto,
# giorni di scadenza, resa automatica (solo ricotta).
# ============================================================
import streamlit as st
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Prodotti", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Prodotti")

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

PRODOTTI_BASE = [
    "Mozzarella di Bufala Campana DOP", "Mozzarella di latte di Bufala", "Ricotta di Bufala DOP",
    "Ricotta di Bufala", "Mozzarella mista (bufala/vaccino)", "Semilavorato",
    "Caciocavallo di bufala", "Caciocavallo misto", "Caciocavallo vaccino",
    "Figliata di bufala", "Burrata di bufala",
    "Mozzarella di latte di Bufala senza lattosio", "Mozzarella DOP senza lattosio",
]

# ------------------------------------------------------------
# BLOCCO: NUOVO PRODOTTO
# ------------------------------------------------------------
if is_owner():
    with st.expander("➕ Nuovo prodotto"):
        with st.form("nuovo_prodotto"):
            nome = st.selectbox("Prodotto", PRODOTTI_BASE + ["Altro..."])
            if nome == "Altro...":
                nome = st.text_input("Nome prodotto personalizzato")
            is_dop = st.checkbox("Prodotto DOP")
            tipo_lotto = st.radio("Tipo di lotto", ["data_produzione", "giuliano"], horizontal=True)
            giorni_scadenza = st.number_input("Giorni di scadenza dalla produzione (es. 12)", min_value=0, step=1)
            resa = None
            if "ricotta" in nome.lower():
                resa = st.number_input("Resa automatica (% del latte lavorato)", min_value=0.0, max_value=100.0, value=3.5)

            if st.form_submit_button("Salva prodotto"):
                client.table("prodotti").insert({
                    "caseificio_id": caseificio_id,
                    "nome": nome,
                    "is_dop": is_dop,
                    "tipo_lotto": tipo_lotto,
                    "giorni_scadenza": int(giorni_scadenza),
                    "resa_automatica_percent": resa,
                }).execute()
                st.success("Prodotto salvato.")
                st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: ELENCO PRODOTTI
# ------------------------------------------------------------
st.subheader("Elenco prodotti")

prodotti = (
    client.table("prodotti")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .order("nome")
    .execute()
    .data
)

if not prodotti:
    st.info("Nessun prodotto inserito.")
else:
    for p in prodotti:
        col1, col2 = st.columns([1, 5])
        with col1:
            nuovo_stato = st.checkbox("Attivo", value=p["attivo"], key=f"prod_att_{p['id']}")
            if nuovo_stato != p["attivo"] and is_owner():
                client.table("prodotti").update({"attivo": nuovo_stato}).eq("id", p["id"]).execute()
                st.rerun()
        with col2:
            dop_lbl = " (DOP)" if p["is_dop"] else ""
            lotto_lbl = "gg giuliano" if p["tipo_lotto"] == "giuliano" else "data produzione"
            st.write(f"**{p['nome']}{dop_lbl}** — lotto: {lotto_lbl}, scadenza: +{p.get('giorni_scadenza') or 0} giorni"
                     + (f", resa automatica {p['resa_automatica_percent']}%" if p.get("resa_automatica_percent") else ""))
