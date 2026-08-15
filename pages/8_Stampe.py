# ============================================================
# PAGINA: STAMPE
# Genera PDF con un foglio per ogni giorno lavorato nel periodo
# scelto. Si parte dal foglio "tr" (tracciabilita' latte in
# ingresso) - MBC1 e RBC1 (moduli RINA) arriveranno dopo.
# ============================================================
import streamlit as st
import datetime as _dt
import io
from db import get_client
from auth import login_form, logout_button

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors

st.set_page_config(page_title="Stampe", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Stampe")

caseificio_id = st.session_state.get("caseificio_id")
caseificio_nome = st.session_state.get("caseificio_nome")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

TIPI_LATTE_LABEL = {
    "bufala_dop": "Bufala DOP", "bufala": "Bufala", "vaccino": "Vaccino",
    "semilavorato_bufala": "Semilav. bufalino", "semilavorato_vaccino": "Semilav. vaccino",
}

# ------------------------------------------------------------
# BLOCCO: SCELTA INTERVALLO DA STAMPARE
# ------------------------------------------------------------
st.subheader("Foglio Tracciabilità (tr) — latte in ingresso")
col1, col2 = st.columns(2)
with col1:
    data_dal = st.date_input("Dal", value=_dt.date.today())
with col2:
    data_al = st.date_input("Al", value=_dt.date.today())

if data_al < data_dal:
    st.error("La data 'Al' deve essere successiva o uguale a 'Dal'.")
    st.stop()

n_giorni = (data_al - data_dal).days + 1
if n_giorni > 31:
    st.warning("Hai selezionato più di 31 giorni: il PDF potrebbe essere lungo da generare.")

# ------------------------------------------------------------
# BLOCCO: FUNZIONE PER OTTENERE UN VALORE FISSO (Impostazioni Fisse)
# ------------------------------------------------------------
def valore_fisso(campo, alla_data):
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
    return righe[0]["valore"] if righe else "-"

# ------------------------------------------------------------
# BLOCCO: DATI CASEIFICIO E CONFERITORI
# ------------------------------------------------------------
caseificio = client.table("caseifici").select("*").eq("id", caseificio_id).single().execute().data

conferitori = (
    client.table("conferitori")
    .select("*, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .eq("attivo", True)
    .order("ordine")
    .execute()
    .data
)

LABEL_TIPO_CONFERITORE = {
    "allevatore": "Allevamento", "caseificio": "Caseificio",
    "intermediario": "Intermediario", "congelatore": "Congelatore",
}

# ------------------------------------------------------------
# BLOCCO: GENERAZIONE PDF (un foglio per giorno)
# ------------------------------------------------------------
def disegna_foglio_giorno(c, giorno, ds):
    width, height = A4
    y = height - 20*mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(15*mm, y, "MANUALE DI AUTOCONTROLLO")
    y -= 6*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(15*mm, y, "M.R.15 - RINTRACCIABILITA' DEI PRODOTTI A BASE DI LATTE")
    y -= 8*mm
    c.setFont("Helvetica", 9)
    c.drawString(15*mm, y, f"Caseificio: {caseificio.get('ragione_sociale','-')}")
    c.drawString(120*mm, y, f"Data: {giorno.strftime('%d/%m/%Y')}")
    y -= 10*mm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(15*mm, y, "Latte in ingresso nella struttura")
    y -= 6*mm

    # intestazione tabella
    colonne = [("Conferitore", 55*mm), ("Tipo", 30*mm), ("Tipo latte", 30*mm), ("N.DDT", 20*mm), ("KG", 20*mm), ("Esito", 20*mm)]
    x = 15*mm
    c.setFont("Helvetica-Bold", 8)
    for label, w in colonne:
        c.drawString(x, y, label)
        x += w
    y -= 2*mm
    c.line(15*mm, y, 195*mm, y)
    y -= 5*mm

    conferimenti_giorno = (
        client.table("conferimenti")
        .select("*")
        .in_("conferitore_id", [cf["id"] for cf in conferitori])
        .eq("data", ds)
        .execute()
        .data
    ) if conferitori else []
    mappa_conf_id = {cf["id"]: cf for cf in conferitori}

    c.setFont("Helvetica", 8)
    totale_kg = {}
    for cf_data in conferimenti_giorno:
        conf = mappa_conf_id.get(cf_data["conferitore_id"])
        if not conf or not float(cf_data.get("kg") or 0) > 0:
            continue
        tipi = ", ".join(TIPI_LATTE_LABEL.get(t["tipo_latte"], t["tipo_latte"]) for t in conf.get("conferitori_tipi_latte", []))
        x = 15*mm
        c.drawString(x, y, conf["ragione_sociale"][:32]); x += 55*mm
        c.drawString(x, y, LABEL_TIPO_CONFERITORE.get(conf["tipo"], conf["tipo"])); x += 30*mm
        c.drawString(x, y, tipi[:20]); x += 30*mm
        c.drawString(x, y, str(cf_data.get("ddt") or "-")); x += 20*mm
        c.drawString(x, y, f"{float(cf_data['kg']):.1f}"); x += 20*mm
        c.drawString(x, y, "OK")
        for t in conf.get("conferitori_tipi_latte", []):
            tt = t["tipo_latte"]
            totale_kg[tt] = totale_kg.get(tt, 0) + float(cf_data["kg"])
        y -= 5*mm
        if y < 40*mm:
            c.showPage()
            y = height - 20*mm
            c.setFont("Helvetica", 8)

    if not conferimenti_giorno:
        c.drawString(15*mm, y, "Nessun conferimento registrato in questa data.")
        y -= 5*mm

    y -= 5*mm
    c.line(15*mm, y, 195*mm, y)
    y -= 7*mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(15*mm, y, "Totali per tipo di latte")
    y -= 5*mm
    c.setFont("Helvetica", 8)
    for t, tot in totale_kg.items():
        c.drawString(15*mm, y, f"{TIPI_LATTE_LABEL.get(t, t)}: {tot:.1f} kg")
        y -= 5*mm

    y -= 5*mm
    c.line(15*mm, y, 195*mm, y)
    y -= 7*mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(15*mm, y, "Parametri (valori fissi impostati)")
    y -= 5*mm
    c.setFont("Helvetica", 8)
    c.drawString(15*mm, y, f"Ora ricevimento latte: {valore_fisso('ora_ricevimento_latte', ds)}")
    y -= 5*mm
    c.drawString(15*mm, y, f"Acidità primo siero: {valore_fisso('acidita_primo_siero', ds)}")
    y -= 5*mm
    c.drawString(15*mm, y, f"Temperatura latte: {valore_fisso('temperatura_latte', ds)}")
    y -= 10*mm

    c.setFont("Helvetica", 7)
    c.drawString(15*mm, 15*mm, f"Documento generato dal gestionale caseifici - {_dt.date.today().strftime('%d/%m/%Y')}")

if st.button("📄 Crea PDF"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    giorno = data_dal
    primo = True
    while giorno <= data_al:
        if not primo:
            c.showPage()
        disegna_foglio_giorno(c, giorno, str(giorno))
        primo = False
        giorno += _dt.timedelta(days=1)
    c.save()
    buffer.seek(0)

    st.download_button(
        "⬇️ Scarica PDF",
        data=buffer,
        file_name=f"tr_{data_dal}_{data_al}.pdf",
        mime="application/pdf",
    )
    st.success(f"PDF creato con {n_giorni} foglio/i (uno per giorno).")
