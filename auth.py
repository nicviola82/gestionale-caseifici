# ============================================================
# BLOCCO: LOGIN E RUOLI
# Gestisce l'accesso: email + password (creati da te in Supabase).
# Ruolo "owner": accesso completo a tutto.
# Ruolo "caseificio": solo visualizzazione + stampa, limitato ai
#   caseifici a cui è stato abilitato.
# ============================================================
import streamlit as st
from db import get_client


def login_form():
    """Mostra il form di login. Ritorna True se l'utente e' autenticato."""
    if "user" in st.session_state:
        return True

    st.title("Accesso al gestionale")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Entra")

    if submitted:
        client = get_client()
        try:
            res = client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            st.session_state["user"] = res.user
            st.session_state["access_token"] = res.session.access_token

            # carica il profilo (ruolo + caseifici abilitati)
            profile = (
                client.table("profiles")
                .select("*")
                .eq("id", res.user.id)
                .single()
                .execute()
            )
            st.session_state["profile"] = profile.data

            if profile.data["ruolo"] == "caseificio":
                accessi = (
                    client.table("accessi_caseificio")
                    .select("caseificio_id")
                    .eq("profile_id", res.user.id)
                    .execute()
                )
                st.session_state["caseifici_abilitati"] = [
                    r["caseificio_id"] for r in accessi.data
                ]
            else:
                st.session_state["caseifici_abilitati"] = None  # owner: tutti

            st.rerun()
        except Exception as e:
            st.error("Email o password non corretti.")
    return "user" in st.session_state


def is_owner() -> bool:
    return st.session_state.get("profile", {}).get("ruolo") == "owner"


def logout_button():
    if st.sidebar.button("Esci"):
        for k in ["user", "access_token", "profile", "caseifici_abilitati"]:
            st.session_state.pop(k, None)
        st.rerun()
