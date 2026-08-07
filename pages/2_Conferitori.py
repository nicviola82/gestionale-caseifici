# ============================================================
# PAGINA: CONFERITORI DI LATTE
# Elenco, attivazione/disattivazione, ordine, dati specifici
# per allevatori / caseifici-intermediari / congelatori.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Conferitori", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Conferitori di latte")

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

TIPI_LATTE = ["bufala_dop", "bufala", "vaccino", "cagliata_bufala",
              "cagliata_vaccino", "bufala_congelato", "vaccino_congelato", "altro"]

# ------------------------------------------------------------
# BLOCCO: NUOVO CONFERITORE
# ------------------------------------------------------------
if is_owner():
    with st.expander("➕ Nuovo conferitore"):
        with st.form("nuovo_conferitore"):
            tipo = st.selectbox("Tipo di conferitore", ["allevatore", "caseificio", "intermediario", "congelatore"])
            ragione_sociale = st.text_input("Ragione sociale")
            sede_legale = st.text_input("Sede legale")
            sede_operativa = st.text_input("Sede operativa")
            piva = st.text_input("P.IVA")
            tipi_latte = st.multiselect("Tipi di latte conferiti", TIPI_LATTE)
            ordine = st.number_input("Ordine di visualizzazione", min_value=1, step=1)

            if st.form_submit_button("Salva conferitore"):
                nuovo = client.table("conferitori").insert({
                    "caseificio_id": caseificio_id,
                    "tipo": tipo,
                    "ragione_sociale": ragione_sociale,
                    "sede_legale": sede_legale,
                    "sede_operativa": sede_operativa,
                    "piva": piva,
                    "ordine": int(ordine),
                }).execute().data[0]

                for tl in tipi_latte:
                    client.table("conferitori_tipi_latte").insert({
                        "conferitore_id": nuovo["id"], "tipo_latte": tl
                    }).execute()

                st.success("Conferitore salvato. Apri 'Modifica' per aggiungere dati sanitari/documenti.")
                st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: ELENCO CONFERITORI
# ------------------------------------------------------------
st.subheader("Elenco conferitori")

conferitori = (
    client.table("conferitori")
    .select("*, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .order("ordine")
    .execute()
    .data
)

if not conferitori:
    st.info("Nessun conferitore inserito.")
else:
    for c in conferitori:
        tipi = ", ".join([t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]) or "-"
        col1, col2, col3 = st.columns([1, 4, 2])
        with col1:
            nuovo_stato = st.checkbox("Attivo", value=c["attivo"], key=f"att_{c['id']}")
            if nuovo_stato != c["attivo"] and is_owner():
                client.table("conferitori").update({"attivo": nuovo_stato}).eq("id", c["id"]).execute()
                st.rerun()
        with col2:
            st.write(f"**#{c['ordine']} - {c['ragione_sociale']}** ({c['tipo']}) — latte: {tipi}")
        with col3:
            if is_owner():
                with st.popover("Modifica"):
                    st.write("**Dati sanitari / documenti**")
                    if c["tipo"] == "allevatore":
                        with st.form(f"sanitario_{c['id']}"):
                            tipo_es = st.selectbox("Tipo esame", ["brucellosi", "tubercolosi", "leucosi",
                                                                    "carica_batterica", "cellule_somatiche"],
                                                     key=f"tipoes_{c['id']}")
                            valore = st.number_input("Valore (se applicabile)", value=0.0, key=f"val_{c['id']}")
                            rilascio = st.date_input("Data rilascio", value=_dt.date.today(), key=f"ril_{c['id']}")
                            scadenza = st.date_input("Data scadenza", value=_dt.date.today(), key=f"sca_{c['id']}")
                            if st.form_submit_button("Aggiungi esame"):
                                client.table("stati_sanitari").insert({
                                    "conferitore_id": c["id"], "tipo": tipo_es,
                                    "valore": valore, "data_rilascio": str(rilascio),
                                    "data_scadenza": str(scadenza),
                                }).execute()
                                st.success("Salvato.")
                                st.rerun()
                    else:
                        doc_tipo = "autocertificazione" if c["tipo"] in ("caseificio", "intermediario") else "contratto"
                        with st.form(f"doc_{c['id']}"):
                            scadenza = st.date_input(f"Scadenza {doc_tipo}", value=_dt.date.today(), key=f"docsca_{c['id']}")
                            if st.form_submit_button(f"Salva {doc_tipo}"):
                                client.table("documenti_conferitori").insert({
                                    "conferitore_id": c["id"], "tipo": doc_tipo,
                                    "data_scadenza": str(scadenza),
                                }).execute()
                                st.success("Salvato.")
                                st.rerun()

# ------------------------------------------------------------
# BLOCCO: AVVISI SCADENZE
# ------------------------------------------------------------
st.divider()
st.subheader("⚠️ Avvisi scadenze")
oggi = _dt.date.today()
sanitari = client.table("stati_sanitari").select("*, conferitori(ragione_sociale, caseificio_id)").execute().data
docs = client.table("documenti_conferitori").select("*, conferitori(ragione_sociale, caseificio_id)").execute().data

avvisi = []
for s in sanitari:
    conf = s.get("conferitori") or {}
    if conf.get("caseificio_id") != caseificio_id or not s.get("data_scadenza"):
        continue
    sc = _dt.date.fromisoformat(s["data_scadenza"])
    if sc < oggi:
        avvisi.append(f"🔴 {conf.get('ragione_sociale')}: {s['tipo']} SCADUTO il {sc.strftime('%d/%m/%Y')}")
    elif (sc - oggi).days <= 15:
        avvisi.append(f"🟠 {conf.get('ragione_sociale')}: {s['tipo']} in scadenza il {sc.strftime('%d/%m/%Y')}")
for d in docs:
    conf = d.get("conferitori") or {}
    if conf.get("caseificio_id") != caseificio_id or not d.get("data_scadenza"):
        continue
    sc = _dt.date.fromisoformat(d["data_scadenza"])
    if sc < oggi:
        avvisi.append(f"🔴 {conf.get('ragione_sociale')}: {d['tipo']} SCADUTO il {sc.strftime('%d/%m/%Y')}")
    elif (sc - oggi).days <= 15:
        avvisi.append(f"🟠 {conf.get('ragione_sociale')}: {d['tipo']} in scadenza il {sc.strftime('%d/%m/%Y')}")

if avvisi:
    for a in avvisi:
        st.write(a)
else:
    st.write("Nessuna scadenza imminente.")
    st.divider()

# ------------------------------------------------------------
# BLOCCO: VENDITA / CESSIONE LATTE
# ------------------------------------------------------------
st.subheader("A chi vendo/cedo il latte")

if is_owner():
    with st.expander("➕ Nuovo destinatario vendita"):
        with st.form("nuovo_destinatario"):
            v_tipo = st.selectbox("Tipo destinatario", ["caseificio", "intermediario", "congelatore_conto"],
                                    format_func=lambda x: {"caseificio": "Caseificio", "intermediario": "Intermediario",
                                                            "congelatore_conto": "Congelatore (conto congelamento)"}[x])
            v_ragione_sociale = st.text_input("Ragione sociale", key="v_rs_new")
            v_sede_legale = st.text_input("Sede legale", key="v_sl_new")
            v_sede_operativa = st.text_input("Sede operativa", key="v_so_new")
            v_piva = st.text_input("P.IVA", key="v_piva_new")
            if st.form_submit_button("Salva destinatario"):
                client.table("destinatari_vendita").insert({
                    "caseificio_id": caseificio_id, "tipo": v_tipo,
                    "ragione_sociale": v_ragione_sociale, "sede_legale": v_sede_legale,
                    "sede_operativa": v_sede_operativa, "piva": v_piva,
                }).execute()
                st.success("Destinatario salvato.")
                st.rerun()

destinatari = (
    client.table("destinatari_vendita")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .order("ragione_sociale")
    .execute()
    .data
)

TIPO_DEST_LABEL = {"caseificio": "Caseificio", "intermediario": "Intermediario", "congelatore_conto": "Congelatore (conto congelamento)"}

if not destinatari:
    st.info("Nessun destinatario di vendita inserito.")
else:
    for v in destinatari:
        vcol1, vcol2, vcol3 = st.columns([1, 4, 2])
        with vcol1:
            v_attivo = st.checkbox("Attivo", value=v["attivo"], key=f"vatt_{v['id']}")
            if v_attivo != v["attivo"] and is_owner():
                client.table("destinatari_vendita").update({"attivo": v_attivo}).eq("id", v["id"]).execute()
                st.rerun()
        with vcol2:
            st.write(f"**{v['ragione_sociale']}** ({TIPO_DEST_LABEL.get(v['tipo'], v['tipo'])})")
        with vcol3:
            if is_owner():
                with st.popover("✏️ Gestisci"):
                    with st.form(f"modifica_destinatario_{v['id']}"):
                        vm_ragione_sociale = st.text_input("Ragione sociale", value=v["ragione_sociale"], key=f"vm_rs_{v['id']}")
                        vm_sede_legale = st.text_input("Sede legale", value=v.get("sede_legale") or "", key=f"vm_sl_{v['id']}")
                        vm_sede_operativa = st.text_input("Sede operativa", value=v.get("sede_operativa") or "", key=f"vm_so_{v['id']}")
                        vm_piva = st.text_input("P.IVA", value=v.get("piva") or "", key=f"vm_piva_{v['id']}")
                        if st.form_submit_button("Salva modifiche"):
                            client.table("destinatari_vendita").update({
                                "ragione_sociale": vm_ragione_sociale, "sede_legale": vm_sede_legale,
                                "sede_operativa": vm_sede_operativa, "piva": vm_piva,
                            }).eq("id", v["id"]).execute()
                            st.success("Aggiornato.")
                            st.rerun()
                    st.divider()
                    if st.button("🗑️ Elimina destinatario", key=f"vdel_{v['id']}"):
                        client.table("destinatari_vendita").delete().eq("id", v["id"]).execute()
                        st.success("Eliminato.")
                        st.rerun()
