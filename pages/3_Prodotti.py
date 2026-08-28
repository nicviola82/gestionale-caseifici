# ============================================================
# PAGINA: PRODOTTI
# Elenco prodotti del caseificio, attivazione, modifica, eliminazione,
# tipo lotto, giorni di scadenza, resa automatica (solo ricotta),
# visibilita' nello schema Produzioni, vendita a piu' terzi.
# ============================================================
import streamlit as st
from db import get_client
from auth import login_form, logout_button, is_owner
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Prodotti", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Prodotti")
mostra_header_caseificio()

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

PRODOTTI_BASE = [
    "Mozzarella di Bufala Campana DOP", "Mozzarella di Bufala Campana DOP Affumicata",
    "Mozzarella di latte di Bufala", "Ricotta di Bufala DOP",
    "Ricotta di Bufala", "Mozzarella mista (bufala/vaccino)", "Semilavorato",
    "Caciocavallo di bufala", "Caciocavallo misto", "Caciocavallo vaccino",
    "Figliata di bufala", "Burrata di bufala",
    "Mozzarella di latte di Bufala senza lattosio", "Mozzarella DOP senza lattosio",
    "Mozzarella (latte vaccino)", "Nero di Bufala",
]

TIPI_LOTTO = ["data_produzione", "data_scadenza", "giuliano"]
TIPI_LOTTO_LABEL = {
    "data_produzione": "Data di produzione",
    "data_scadenza": "Data di scadenza",
    "giuliano": "Calendario giuliano (1-366)",
}

TIPI_VENDITA = ["diretta", "terzi", "entrambe"]
TIPI_VENDITA_LABEL = {
    "diretta": "Solo vendita diretta",
    "terzi": "Solo vendita a terzi",
    "entrambe": "Entrambe (diretta + terzi)",
}

# ------------------------------------------------------------
# BLOCCO: NUOVO PRODOTTO
# ------------------------------------------------------------
if is_owner():
    with st.expander("➕ Nuovo prodotto"):
        with st.form("nuovo_prodotto"):
            nome = st.selectbox("Prodotto", PRODOTTI_BASE + ["Altro..."])
            if nome == "Altro...":
                nome = st.text_input("Nome prodotto personalizzato")
            abbreviazione = st.text_input("Abbreviazione (usata come intestazione nella griglia di Produzioni, es. \"MBC\")", max_chars=15)
            is_dop = st.checkbox("Prodotto DOP")
            tipo_lotto = st.radio("Tipo di lotto", TIPI_LOTTO, format_func=lambda x: TIPI_LOTTO_LABEL[x], horizontal=True)
            giorni_scadenza = st.number_input("Giorni di scadenza dalla produzione (es. 12)", min_value=0, step=1)
            resa = None
            if "ricotta" in nome.lower():
                resa = st.number_input("Resa automatica (% del latte lavorato)", min_value=0.0, max_value=100.0, value=3.5)
            mostra_produzioni = st.checkbox("Mostra questo prodotto nello schema Produzioni", value=True)
            tipo_vendita = st.radio(
                "Tipo di vendita", TIPI_VENDITA, format_func=lambda x: TIPI_VENDITA_LABEL[x],
                index=2, horizontal=True,
                help="Se 'Solo diretta' o 'Solo terzi', in Produzioni non verrà più chiesto di suddividere - il totale va tutto lì.",
            )
            consente_piu_terzi = st.checkbox("Consenti piu' destinatari per la vendita a terzi (es. mozzarella)")
            stabilisce_resa = st.checkbox("Questo prodotto STABILISCE LA RESA del giorno per la sua categoria di latte (es. la Mozzarella di Bufala Campana DOP)")

            if st.form_submit_button("Salva prodotto"):
                client.table("prodotti").insert({
                    "caseificio_id": caseificio_id,
                    "nome": nome,
                    "abbreviazione": abbreviazione or None,
                    "is_dop": is_dop,
                    "attivo": True,
                    "tipo_lotto": tipo_lotto,
                    "giorni_scadenza": int(giorni_scadenza),
                    "resa_automatica_percent": resa,
                    "mostra_in_produzioni": mostra_produzioni,
                    "tipo_vendita": tipo_vendita,
                    "consente_piu_terzi": consente_piu_terzi,
                    "stabilisce_resa": stabilisce_resa,
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
        col1, col2, col3, col4 = st.columns([1, 4, 1, 1])
        with col1:
            nuovo_stato = st.checkbox("Attivo", value=p["attivo"], key=f"prod_att_{p['id']}")
            if nuovo_stato != p["attivo"] and is_owner():
                client.table("prodotti").update({"attivo": nuovo_stato}).eq("id", p["id"]).execute()
                st.rerun()
        with col2:
            dop_lbl = " (DOP)" if p["is_dop"] else ""
            lotto_lbl = TIPI_LOTTO_LABEL.get(p["tipo_lotto"], p["tipo_lotto"])
            extra = []
            if p.get("abbreviazione"):
                extra.append(f"abbr. \"{p['abbreviazione']}\"")
            if not p.get("mostra_in_produzioni", True):
                extra.append("nascosto da Produzioni")
            if p.get("consente_piu_terzi"):
                extra.append("multi-terzi")
            extra.append(TIPI_VENDITA_LABEL.get(p.get("tipo_vendita") or "entrambe", "Entrambe"))
            extra_txt = f" [{', '.join(extra)}]" if extra else ""
            st.write(f"**{p['nome']}{dop_lbl}** — lotto: {lotto_lbl}, scadenza: +{p.get('giorni_scadenza') or 0} giorni"
                     + (f", resa automatica {p['resa_automatica_percent']}%" if p.get("resa_automatica_percent") else "")
                     + extra_txt)
        with col3:
            if is_owner():
                with st.popover("✏️ Modifica"):
                    with st.form(f"modifica_prodotto_{p['id']}"):
                        m_nome = st.text_input("Nome prodotto", value=p["nome"], key=f"m_nome_{p['id']}")
                        m_abbreviazione = st.text_input(
                            "Abbreviazione (griglia Produzioni)", value=p.get("abbreviazione") or "",
                            max_chars=15, key=f"m_abbr_{p['id']}",
                        )
                        m_is_dop = st.checkbox("Prodotto DOP", value=p["is_dop"], key=f"m_dop_{p['id']}")
                        m_tipo_lotto = st.radio(
                            "Tipo di lotto", TIPI_LOTTO, format_func=lambda x: TIPI_LOTTO_LABEL[x],
                            index=TIPI_LOTTO.index(p["tipo_lotto"]), key=f"m_lotto_{p['id']}",
                        )
                        m_giorni_scadenza = st.number_input(
                            "Giorni di scadenza dalla produzione", min_value=0, step=1,
                            value=p.get("giorni_scadenza") or 0, key=f"m_giorni_{p['id']}",
                        )
                        m_resa = st.number_input(
                            "Resa automatica % (0 = nessuna)", min_value=0.0, max_value=100.0,
                            value=float(p.get("resa_automatica_percent") or 0.0), key=f"m_resa_{p['id']}",
                        )
                        m_mostra_produzioni = st.checkbox(
                            "Mostra nello schema Produzioni", value=p.get("mostra_in_produzioni", True), key=f"m_mostra_{p['id']}",
                        )
                        m_tipo_vendita = st.radio(
                            "Tipo di vendita", TIPI_VENDITA, format_func=lambda x: TIPI_VENDITA_LABEL[x],
                            index=TIPI_VENDITA.index(p.get("tipo_vendita") or "entrambe"), key=f"m_venditatipo_{p['id']}", horizontal=True,
                        )
                        m_consente_piu_terzi = st.checkbox(
                            "Consenti piu' destinatari per la vendita a terzi", value=p.get("consente_piu_terzi", False), key=f"m_multi_{p['id']}",
                        )
                        m_stabilisce_resa = st.checkbox(
                            "Questo prodotto STABILISCE LA RESA del giorno", value=p.get("stabilisce_resa", False), key=f"m_resa_flag_{p['id']}",
                        )
                        if st.form_submit_button("Salva modifiche"):
                            client.table("prodotti").update({
                                "nome": m_nome,
                                "abbreviazione": m_abbreviazione or None,
                                "is_dop": m_is_dop,
                                "tipo_lotto": m_tipo_lotto,
                                "giorni_scadenza": int(m_giorni_scadenza),
                                "resa_automatica_percent": m_resa if m_resa > 0 else None,
                                "mostra_in_produzioni": m_mostra_produzioni,
                                "tipo_vendita": m_tipo_vendita,
                                "consente_piu_terzi": m_consente_piu_terzi,
                                "stabilisce_resa": m_stabilisce_resa,
                            }).eq("id", p["id"]).execute()
                            st.success("Prodotto aggiornato.")
                            st.rerun()

                    # ------------------------------------------------------------
                    # BLOCCO: COLONNE VENDITA A TERZI (nomi scelti dall'utente)
                    # Fuori dal form sopra perche' deve reagire SUBITO quando cambi
                    # il numero di colonne (nei form di Streamlit i widget si
                    # aggiornano solo al submit, qui invece serve la reattivita'
                    # immediata). Visibile solo se "consenti piu' destinatari" e'
                    # gia' salvato True per questo prodotto (aggiunto 27/08).
                    # ------------------------------------------------------------
                    if p.get("consente_piu_terzi"):
                        st.divider()
                        st.caption("Colonne per la vendita a terzi in Produzioni: quante sono e come si chiamano")
                        colonne_esistenti = (
                            client.table("prodotto_colonne_terzi").select("*")
                            .eq("prodotto_id", p["id"]).order("ordine").execute().data
                        )
                        n_colonne = st.number_input(
                            "Quante colonne per vendita a terzi?", min_value=1, max_value=10,
                            value=len(colonne_esistenti) or 1, step=1, key=f"ncol_terzi_{p['id']}",
                        )
                        nomi_colonne = []
                        for i in range(int(n_colonne)):
                            valore_default = colonne_esistenti[i]["nome"] if i < len(colonne_esistenti) else ""
                            nomi_colonne.append(st.text_input(
                                f"Nome colonna {i + 1}", value=valore_default, key=f"nome_col_terzi_{p['id']}_{i}",
                            ))
                        if st.button("Salva colonne vendita a terzi", key=f"salva_col_terzi_{p['id']}"):
                            for i, nome_col in enumerate(nomi_colonne):
                                nome_col = nome_col.strip() or f"Terzo {i + 1}"
                                if i < len(colonne_esistenti):
                                    if colonne_esistenti[i]["nome"] != nome_col:
                                        client.table("prodotto_colonne_terzi").update(
                                            {"nome": nome_col}
                                        ).eq("id", colonne_esistenti[i]["id"]).execute()
                                else:
                                    client.table("prodotto_colonne_terzi").insert({
                                        "prodotto_id": p["id"], "nome": nome_col, "ordine": i,
                                    }).execute()
                            if len(colonne_esistenti) > len(nomi_colonne):
                                for extra in colonne_esistenti[len(nomi_colonne):]:
                                    client.table("prodotto_colonne_terzi").delete().eq("id", extra["id"]).execute()
                                st.warning("Attenzione: le colonne rimosse eliminano anche i dati di produzione già salvati per quelle colonne.")
                            st.success("Colonne aggiornate.")
                            st.rerun()
        with col4:
            if is_owner():
                if st.button("🗑️", key=f"prod_del_{p['id']}", help="Elimina prodotto"):
                    st.session_state[f"prod_conferma_del_{p['id']}"] = True
                if st.session_state.get(f"prod_conferma_del_{p['id']}"):
                    if st.button("Conferma eliminazione", key=f"prod_del_conferma_{p['id']}"):
                        client.table("prodotti").delete().eq("id", p["id"]).execute()
                        st.session_state.pop(f"prod_conferma_del_{p['id']}", None)
                        st.success("Prodotto eliminato.")
                        st.rerun()
