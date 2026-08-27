# ============================================================
# PAGINA: IMPOSTAZIONI FISSE
# Valori che restano fissi (orari, acidita'/temperatura, dati di
# lavorazione, caglio provvisorio, parametri RBC) finche' non
# vengono modificati: ogni modifica vale "da" una data in poi,
# senza cancellare lo storico dei valori precedenti.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Impostazioni Fisse", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Impostazioni Fisse")
mostra_header_caseificio()
st.caption("Ogni valore che imposti resta valido da quella data in poi, finche' non lo modifichi di nuovo. Serve per i fogli stampabili (MBC, RBC, tr).")

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: DEFINIZIONE CAMPI
# tipo determina il widget mostrato nel form e come il valore
# viene serializzato in stringa nella colonna "valore":
#   testo         -> stringa libera
#   numero        -> stringa numerica (es. "4.20")
#   ora           -> stringa "HH:MM"
#   select        -> una delle stringhe in "opzioni"
#   stabilizzato / trattamento -> "SI|Opzione1,Opzione2" oppure "NO"
# ------------------------------------------------------------
CAMPI = {
    # --- Esistenti (MBC / generali) ---
    "ora_ricevimento_latte": {"label": "Ora ricevimento latte", "tipo": "ora", "gruppo": "Generale / MBC"},
    "ora_inizio_lavorazione": {"label": "Ora inizio lavorazione", "tipo": "ora", "gruppo": "Generale / MBC"},
    "ora_fine_lavorazione": {"label": "Ora fine lavorazione", "tipo": "ora", "gruppo": "Generale / MBC"},
    "ora_rottura_cagliata": {"label": "Ora rottura cagliata", "tipo": "ora", "gruppo": "Generale / MBC"},
    "acidita_primo_siero": {"label": "Acidità primo siero (°SH/50ml)", "tipo": "numero", "gruppo": "Generale / MBC"},
    "temperatura_latte": {"label": "Temperatura latte (°C)", "tipo": "numero", "gruppo": "Generale / MBC"},
    "tempo_maturazione_minuti": {"label": "Tempo di maturazione (minuti)", "tipo": "numero", "gruppo": "Generale / MBC"},
    "temperatura_attivazione": {"label": "Temperatura attivazione (°C)", "tipo": "numero", "gruppo": "Generale / MBC"},
    "tipo_siero_innesto": {"label": "Tipo siero innesto", "tipo": "testo", "gruppo": "Generale / MBC"},
    "temperatura_acqua_filatura": {"label": "Temperatura acqua di filatura (°C)", "tipo": "numero", "gruppo": "Generale / MBC"},
    "caglio_fornitore": {"label": "Caglio - fornitore", "tipo": "testo", "gruppo": "Generale / MBC"},
    "caglio_lotto": {"label": "Caglio - lotto", "tipo": "testo", "gruppo": "Generale / MBC"},
    "cicli_lavorazione": {"label": "Cicli di lavorazione n° (MBC)", "tipo": "numero", "gruppo": "Generale / MBC"},

    # --- Nuovi campi MBC ---
    "separazione_produzioni": {
        "label": "Separazione produzioni DOP / non-DOP (MBC D28)", "tipo": "select",
        "opzioni": ["Spaziale", "Tem.le", "Spaziale/Tem.le"], "gruppo": "MBC",
    },
    "composizione_liquido_governo": {
        "label": "Composizione liquido di governo (MBC U23-W23)", "tipo": "testo", "gruppo": "MBC",
    },
    "ora_termine_confezionamento": {
        "label": "Ora termine confezionamento (MBC)", "tipo": "ora", "gruppo": "MBC",
    },

    # --- Nuovi campi RBC ---
    "ora_siero_autoprodotto_rbc": {
        "label": "Ora produzione siero autoprodotto (RBC P27)", "tipo": "ora", "gruppo": "RBC",
    },
    "siero_stabilizzato": {
        "label": "Il siero DOP viene stabilizzato (RBC H37/H38/H39)", "tipo": "stabilizzato",
        "opzioni": ["Pastorizzato", "Termizzato", "Refrigerato"], "gruppo": "RBC",
    },
    "agente_acidificante_rbc": {
        "label": "Agente acidificante (RBC)", "tipo": "select",
        "opzioni": ["Cizza di Mozzarella di Bufala Campana DOP", "Acido Lattico", "Acido Citrico"], "gruppo": "RBC",
    },
    "perc_latte_bufala_rbc": {
        "label": "% aggiunta latte di bufala (RBC, max 6%)", "tipo": "numero", "gruppo": "RBC",
    },
    "perc_latte_bufala_ricotta_nondop": {
        "label": "% aggiunta latte di bufala (Ricotta NON-DOP)", "tipo": "numero", "gruppo": "RBC",
    },
    "perc_panna_fresca_rbc": {
        "label": "% aggiunta panna fresca (RBC, max 5%)", "tipo": "numero", "gruppo": "RBC",
    },
    "kg_sale_rbc": {
        "label": "Sale (kg per 100 kg primo siero, max 1 kg)", "tipo": "numero", "gruppo": "RBC",
    },
    "temperatura_finale_ricotta": {
        "label": "Temperatura finale ricotta (°C, max 96)", "tipo": "numero", "gruppo": "RBC",
    },
    "temperatura_raffreddamento_ricotta": {
        "label": "Temperatura raffreddamento ricotta (°C, 1-4)", "tipo": "numero", "gruppo": "RBC",
    },
    "trattamento_termico_ricotta": {
        "label": "Trattamento termico ricotta", "tipo": "trattamento",
        "opzioni": ["Lisciatura", "Omogeneizzazione"], "gruppo": "RBC",
    },
}


# ------------------------------------------------------------
# BLOCCO: SERIALIZZAZIONE VALORI "SPECIALI" (SI/NO + scelte multiple)
# Usato per siero_stabilizzato e trattamento_termico_ricotta.
# ------------------------------------------------------------
def serializza_speciale(si_no, scelte):
    if not si_no:
        return "NO"
    return "SI|" + ",".join(scelte)


def parse_speciale(valore):
    if not valore or valore == "NO":
        return False, []
    if valore.startswith("SI|"):
        parte = valore[3:]
        return True, [s for s in parte.split(",") if s]
    return False, []


def display_valore(campo, valore):
    if valore is None:
        return "(non impostato)"
    tipo = CAMPI[campo]["tipo"]
    if tipo in ("stabilizzato", "trattamento"):
        si_no, scelte = parse_speciale(valore)
        if not si_no:
            return "No"
        return "Sì (" + ", ".join(scelte) + ")" if scelte else "Sì"
    return valore


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


# ------------------------------------------------------------
# BLOCCO: VALORI ATTUALI (raggruppati per sezione)
# ------------------------------------------------------------
st.subheader("Valori attuali")
gruppi = ["Generale / MBC", "MBC", "RBC"]
for gruppo in gruppi:
    campi_gruppo = [c for c, info in CAMPI.items() if info["gruppo"] == gruppo]
    if not campi_gruppo:
        continue
    st.markdown(f"**{gruppo}**")
    righe_attuali = []
    for campo in campi_gruppo:
        v = valore_attuale(campo)
        righe_attuali.append({
            "Campo": CAMPI[campo]["label"],
            "Valore attuale": display_valore(campo, v["valore"] if v else None),
            "In vigore da": v["data_da"] if v else "-",
        })
    st.table(righe_attuali)

st.divider()

# ------------------------------------------------------------
# BLOCCO: IMPOSTA / MODIFICA UN VALORE
# Fuori da un st.form perche' il widget da mostrare cambia in
# base al tipo del campo selezionato (serve un rerun immediato).
# ------------------------------------------------------------
st.subheader("➕ Imposta / modifica un valore")
if is_owner():
    campo_sel = st.selectbox(
        "Campo", list(CAMPI.keys()),
        format_func=lambda c: f"[{CAMPI[c]['gruppo']}] {CAMPI[c]['label']}",
        key="if_campo_sel",
    )
    info = CAMPI[campo_sel]
    tipo = info["tipo"]

    nuovo_valore = None
    valido = True

    if tipo == "testo":
        nuovo_valore = st.text_input("Nuovo valore", key=f"if_input_{campo_sel}")
        valido = bool(nuovo_valore.strip())
    elif tipo == "numero":
        num = st.number_input("Nuovo valore", step=0.1, format="%.2f", key=f"if_input_{campo_sel}")
        nuovo_valore = str(num)
    elif tipo == "ora":
        ora = st.time_input("Nuovo valore", key=f"if_input_{campo_sel}")
        nuovo_valore = ora.strftime("%H:%M")
    elif tipo == "select":
        nuovo_valore = st.selectbox("Nuovo valore", info["opzioni"], key=f"if_input_{campo_sel}")
    elif tipo in ("stabilizzato", "trattamento"):
        si_no = st.checkbox("Sì", key=f"if_input_sino_{campo_sel}")
        scelte = []
        if si_no:
            scelte = st.multiselect("Tipo", info["opzioni"], key=f"if_input_scelte_{campo_sel}")
        nuovo_valore = serializza_speciale(si_no, scelte)

    data_da = st.date_input("In vigore da", value=_dt.date.today(), key="if_input_data")

    if st.button("Salva", key="if_salva"):
        if not valido:
            st.warning("Inserisci un valore.")
        else:
            client.table("impostazioni_registro").insert({
                "caseificio_id": caseificio_id, "campo": campo_sel,
                "valore": nuovo_valore, "data_da": str(data_da),
            }).execute()
            st.success("Salvato.")
            st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: STORICO MODIFICHE
# ------------------------------------------------------------
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
        "Campo": CAMPI[s["campo"]]["label"] if s["campo"] in CAMPI else s["campo"],
        "Valore": display_valore(s["campo"], s["valore"]) if s["campo"] in CAMPI else s["valore"],
        "In vigore da": s["data_da"],
    } for s in storico])
else:
    st.write("Nessuna impostazione salvata ancora.")
