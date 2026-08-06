# ============================================================
# BLOCCO: CONNESSIONE DATABASE
# Si collega a Supabase usando le chiavi salvate nei "Secrets"
# di Streamlit Cloud (non scritte qui nel codice).
# ============================================================
import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)
