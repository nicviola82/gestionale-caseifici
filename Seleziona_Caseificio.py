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

# ------------------------------------------------------------
# BLOCCO: NUOVO CASEIFICIO
# Spostato PRIMA del controllo "nessun caseificio" qui sotto: altrimenti,
# alla primissima volta (zero caseifici), la pagina si fermava subito e non
# c'era alcun modo di crearne uno (bug introdotto togliendo la vecchia
# pagina Anagrafica, che era raggiungibile anche a lista vuota - 27/08).
# ------------------------------------------------------------
if is_owner():
    with st.popover("➕ Nuovo caseificio"):
        with st.form("nuovo_caseificio"):
            n_ragione_sociale = st.text_input("Denominazione sociale")
            n_sede_legale = st.text_input("Sede legale")
            n_sede_operativa = st.text_input("Sede operativa")
            n_piva = st.text_input("P.IVA")
            n_is_dop = st.checkbox("Caseificio linea DOP")

            col1, col2 = st.columns(2)
            with col1:
                n_aut_852_numero = st.text_input("Autorizzazione 852 - numero")
                n_aut_852_rilascio = st.date_input("852 - data rilascio", value=None, key="n852r")
                n_aut_852_scadenza = st.date_input("852 - data scadenza", value=None, key="n852s")
            with col2:
                n_aut_853_numero = st.text_input("Autorizzazione 853 - numero")
                n_aut_853_rilascio = st.date_input("853 - data rilascio", value=None, key="n853r")
                n_aut_853_scadenza = st.date_input("853 - data scadenza", value=None, key="n853s")

            if st.form_submit_button("Salva nuovo caseificio"):
                client.table("caseifici").insert({
                    "ragione_sociale": n_ragione_sociale,
                    "sede_legale": n_sede_legale,
                    "sede_operativa": n_sede_operativa,
                    "piva": n_piva,
                    "is_dop": n_is_dop,
                    "aut_852_numero": n_aut_852_numero,
                    "aut_852_rilascio": str(n_aut_852_rilascio) if n_aut_852_rilascio else None,
                    "aut_852_scadenza": str(n_aut_852_scadenza) if n_aut_852_scadenza else None,
                    "aut_853_numero": n_aut_853_numero,
                    "aut_853_rilascio": str(n_aut_853_rilascio) if n_aut_853_rilascio else None,
                    "aut_853_scadenza": str(n_aut_853_scadenza) if n_aut_853_scadenza else None,
                }).execute()
                st.success("Caseificio creato. Selezionalo dalla tendina qui sotto.")
                st.rerun()

if not caseifici:
    st.info("Nessun caseificio presente. Usa il tasto '➕ Nuovo caseificio' qui sopra per crearne uno.")
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
# BLOCCO: MODIFICA DATI ANAGRAFICI DEL CASEIFICIO SELEZIONATO
# CORREZIONE 27/08: prima il tasto "Modifica" mandava alla pagina Anagrafica
# Caseificio, che pero' NON aveva nessun modulo di modifica dei dati (solo
# creazione nuovo caseificio + una scheda di sola lettura) - da qui il "non
# funziona" segnalato. La pagina Anagrafica Caseificio viene eliminata: tutto
# (nuovo caseificio, modifica caseificio) vive qui. I refrigeranti si spostano
# in Impostazioni Fisse (vedi punto 8).
# ------------------------------------------------------------
if is_owner():
    caseificio_corrente = client.table("caseifici").select("*").eq("id", nuovo_caseificio_id).single().execute().data
    with st.popover("✏️ Modifica dati anagrafici di questo caseificio"):
        with st.form("modifica_caseificio"):
            m_ragione_sociale = st.text_input("Denominazione sociale", value=caseificio_corrente.get("ragione_sociale") or "")
            m_sede_legale = st.text_input("Sede legale", value=caseificio_corrente.get("sede_legale") or "")
            m_sede_operativa = st.text_input("Sede operativa", value=caseificio_corrente.get("sede_operativa") or "")
            m_piva = st.text_input("P.IVA", value=caseificio_corrente.get("piva") or "")
            m_is_dop = st.checkbox("Caseificio linea DOP", value=caseificio_corrente.get("is_dop", False))

            col1, col2 = st.columns(2)
            with col1:
                m_aut_852_numero = st.text_input("Autorizzazione 852 - numero", value=caseificio_corrente.get("aut_852_numero") or "")
                m_aut_852_rilascio = st.date_input(
                    "852 - data rilascio",
                    value=_dt.date.fromisoformat(caseificio_corrente["aut_852_rilascio"]) if caseificio_corrente.get("aut_852_rilascio") else None,
                )
                m_aut_852_scadenza = st.date_input(
                    "852 - data scadenza",
                    value=_dt.date.fromisoformat(caseificio_corrente["aut_852_scadenza"]) if caseificio_corrente.get("aut_852_scadenza") else None,
                )
            with col2:
                m_aut_853_numero = st.text_input("Autorizzazione 853 - numero", value=caseificio_corrente.get("aut_853_numero") or "")
                m_aut_853_rilascio = st.date_input(
                    "853 - data rilascio",
                    value=_dt.date.fromisoformat(caseificio_corrente["aut_853_rilascio"]) if caseificio_corrente.get("aut_853_rilascio") else None,
                )
                m_aut_853_scadenza = st.date_input(
                    "853 - data scadenza",
                    value=_dt.date.fromisoformat(caseificio_corrente["aut_853_scadenza"]) if caseificio_corrente.get("aut_853_scadenza") else None,
                )

            if st.form_submit_button("Salva modifiche"):
                client.table("caseifici").update({
                    "ragione_sociale": m_ragione_sociale,
                    "sede_legale": m_sede_legale,
                    "sede_operativa": m_sede_operativa,
                    "piva": m_piva,
                    "is_dop": m_is_dop,
                    "aut_852_numero": m_aut_852_numero,
                    "aut_852_rilascio": str(m_aut_852_rilascio) if m_aut_852_rilascio else None,
                    "aut_852_scadenza": str(m_aut_852_scadenza) if m_aut_852_scadenza else None,
                    "aut_853_numero": m_aut_853_numero,
                    "aut_853_rilascio": str(m_aut_853_rilascio) if m_aut_853_rilascio else None,
                    "aut_853_scadenza": str(m_aut_853_scadenza) if m_aut_853_scadenza else None,
                }).eq("id", nuovo_caseificio_id).execute()
                st.success("Dati anagrafici aggiornati.")
                st.session_state["caseificio_nome"] = f"{m_ragione_sociale} {'(DOP)' if m_is_dop else ''}"
                st.rerun()

    # avviso scadenze autorizzazioni, sempre visibile (non solo dentro il popover)
    for campo, etichetta in [("aut_852_scadenza", "Autorizzazione 852"), ("aut_853_scadenza", "Autorizzazione 853")]:
        val = caseificio_corrente.get(campo)
        if val:
            scadenza = _dt.date.fromisoformat(val)
            oggi_check = _dt.date.today()
            if scadenza < oggi_check:
                st.error(f"⚠️ {etichetta} SCADUTA il {scadenza.strftime('%d/%m/%Y')}")
            elif (scadenza - oggi_check).days <= 30:
                st.warning(f"⚠️ {etichetta} in scadenza il {scadenza.strftime('%d/%m/%Y')}")

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
