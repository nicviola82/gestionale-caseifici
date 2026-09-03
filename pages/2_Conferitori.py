# ============================================================
# PAGINA: CONFERITORI DI LATTE
# Elenco, attivazione/disattivazione, ordine, dati specifici
# per allevatori / caseifici-intermediari / congelatori.
#
# Ogni conferitore ha 3 azioni separate: Elimina, Modifica
# (dati anagrafici), Stati sanitari/documenti - prima erano
# unite in un solo popover "Modifica".
# Nuovi campi: codice_stalla (solo allevatori), bollo_ce (per
# caseificio/intermediario/congelatore - riconoscimento 853),
# codice_abbreviativo (per tutti).
# ============================================================
import streamlit as st
import datetime as _dt
import pandas as pd
from db import get_client
from auth import login_form, logout_button, is_owner
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Conferitori", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Conferitori di latte")
mostra_header_caseificio()

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

TIPI_LATTE = ["bufala_dop", "bufala", "vaccino", "semilavorato_bufala", "semilavorato_vaccino",
              "bufala_congelato", "vaccino_congelato", "altro"]

# ------------------------------------------------------------
# BLOCCO: NUOVO CONFERITORE
# ------------------------------------------------------------
if is_owner():
    with st.expander("➕ Nuovo conferitore"):
        with st.form("nuovo_conferitore"):
            tipo = st.selectbox("Tipo di conferitore", ["allevatore", "caseificio", "intermediario", "congelatore"])
            ragione_sociale = st.text_input("Ragione sociale")
            codice_abbreviativo = st.text_input("Codice abbreviativo (usato nelle griglie al posto del nome)")
            sede_legale = st.text_input("Sede legale")
            sede_operativa = st.text_input("Sede operativa")
            piva = st.text_input("P.IVA")
            codice_stalla = st.text_input("Codice di stalla (solo allevatori)")
            bollo_ce = st.text_input("Numero bollo CE - riconoscimento 853 (caseificio/intermediario/congelatore)")
            tipi_latte = st.multiselect("Tipi di latte conferiti", TIPI_LATTE)
            ordine = st.number_input("Ordine di visualizzazione", min_value=1, step=1)

            if st.form_submit_button("Salva conferitore"):
                nuovo = client.table("conferitori").insert({
                    "caseificio_id": caseificio_id,
                    "tipo": tipo,
                    "ragione_sociale": ragione_sociale,
                    "codice_abbreviativo": codice_abbreviativo or None,
                    "sede_legale": sede_legale,
                    "sede_operativa": sede_operativa,
                    "piva": piva,
                    "codice_stalla": codice_stalla if tipo == "allevatore" else None,
                    "bollo_ce": bollo_ce if tipo != "allevatore" else None,
                    "ordine": int(ordine),
                }).execute().data[0]

                for tl in tipi_latte:
                    client.table("conferitori_tipi_latte").insert({
                        "conferitore_id": nuovo["id"], "tipo_latte": tl
                    }).execute()

                st.success("Conferitore salvato.")
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

# Stati sanitari e documenti di TUTTI i conferitori di questo caseificio, raggruppati per
# conferitore - usati sia per la lista dentro ogni popover "Stati sanitari" sia per il
# pallino di stato accanto al nome, sia per il riepilogo "Avvisi scadenze" più sotto
# (una sola query invece di ripeterla più volte).
oggi = _dt.date.today()

sanitari_grezzi = client.table("stati_sanitari").select("*, conferitori(ragione_sociale, caseificio_id)").execute().data
docs_grezzi = client.table("documenti_conferitori").select("*, conferitori(ragione_sociale, caseificio_id)").execute().data

sanitari_by_conf = {}
for s in sanitari_grezzi:
    conf = s.get("conferitori") or {}
    if conf.get("caseificio_id") == caseificio_id:
        sanitari_by_conf.setdefault(s["conferitore_id"], []).append(s)

docs_by_conf = {}
for d in docs_grezzi:
    conf = d.get("conferitori") or {}
    if conf.get("caseificio_id") == caseificio_id:
        docs_by_conf.setdefault(d["conferitore_id"], []).append(d)


def stato_scadenza_badge(record_list):
    """Ritorna un'emoji che riassume lo stato peggiore tra tutti i record di un conferitore:
    nessun dato caricato / tutto valido / in scadenza (entro 15 giorni) / scaduto."""
    if not record_list:
        return "⚪ nessun dato"
    peggiore = "ok"
    for r in record_list:
        if not r.get("data_scadenza"):
            continue
        sc = _dt.date.fromisoformat(r["data_scadenza"])
        if sc < oggi:
            peggiore = "scaduto"
            break
        elif (sc - oggi).days <= 15 and peggiore != "scaduto":
            peggiore = "in_scadenza"
    return {"ok": "🟢 in regola", "in_scadenza": "🟠 in scadenza", "scaduto": "🔴 scaduto"}[peggiore]


if not conferitori:
    st.info("Nessun conferitore inserito.")
else:
    for c in conferitori:
        tipi = ", ".join([t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]) or "-"
        col1, col2, col3, col4, col5 = st.columns([1, 4, 1, 1, 1])

        with col1:
            nuovo_stato = st.checkbox("Attivo", value=c["attivo"], key=f"att_{c['id']}")
            if nuovo_stato != c["attivo"] and is_owner():
                client.table("conferitori").update({"attivo": nuovo_stato}).eq("id", c["id"]).execute()
                st.rerun()

        with col2:
            sigla = f" [{c['codice_abbreviativo']}]" if c.get("codice_abbreviativo") else ""
            st.write(f"**#{c['ordine']} - {c['ragione_sociale']}**{sigla} ({c['tipo']}) — latte: {tipi}")
            extra = []
            if c.get("codice_stalla"):
                extra.append(f"Cod. stalla: {c['codice_stalla']}")
            if c.get("bollo_ce"):
                extra.append(f"Bollo CE: {c['bollo_ce']}")
            record_conferitore = sanitari_by_conf.get(c["id"], []) + docs_by_conf.get(c["id"], [])
            extra.append(stato_scadenza_badge(record_conferitore))
            if extra:
                st.caption(" · ".join(extra))

        with col3:
            if is_owner():
                with st.popover("✏️ Modifica"):
                    with st.form(f"modifica_conferitore_{c['id']}"):
                        m_ragione_sociale = st.text_input("Ragione sociale", value=c["ragione_sociale"], key=f"m_rs_{c['id']}")
                        m_codice_abbreviativo = st.text_input("Codice abbreviativo", value=c.get("codice_abbreviativo") or "", key=f"m_cod_{c['id']}")
                        m_sede_legale = st.text_input("Sede legale", value=c.get("sede_legale") or "", key=f"m_sl_{c['id']}")
                        m_sede_operativa = st.text_input("Sede operativa", value=c.get("sede_operativa") or "", key=f"m_so_{c['id']}")
                        m_piva = st.text_input("P.IVA", value=c.get("piva") or "", key=f"m_piva_{c['id']}")
                        if c["tipo"] == "allevatore":
                            m_codice_stalla = st.text_input("Codice di stalla", value=c.get("codice_stalla") or "", key=f"m_stalla_{c['id']}")
                            m_bollo_ce = None
                        else:
                            m_codice_stalla = None
                            m_bollo_ce = st.text_input("Numero bollo CE (853)", value=c.get("bollo_ce") or "", key=f"m_bce_{c['id']}")
                        m_ordine = st.number_input("Ordine di visualizzazione", min_value=1, step=1, value=c["ordine"], key=f"m_ord_{c['id']}")
                        if st.form_submit_button("Salva modifiche"):
                            client.table("conferitori").update({
                                "ragione_sociale": m_ragione_sociale,
                                "codice_abbreviativo": m_codice_abbreviativo or None,
                                "sede_legale": m_sede_legale,
                                "sede_operativa": m_sede_operativa,
                                "piva": m_piva,
                                "codice_stalla": m_codice_stalla,
                                "bollo_ce": m_bollo_ce,
                                "ordine": int(m_ordine),
                            }).eq("id", c["id"]).execute()
                            st.success("Aggiornato.")
                            st.rerun()

        with col4:
            if is_owner():
                with st.popover("🩺 Stati sanitari"):
                    # ---- Elenco di quanto già caricato per QUESTO conferitore ----
                    # (prima mancava del tutto: si poteva solo aggiungere, mai vedere cosa
                    # c'era già - motivo per cui sembrava che "non apparisse da nessuna parte")
                    esistenti = sanitari_by_conf.get(c["id"], []) if c["tipo"] == "allevatore" else docs_by_conf.get(c["id"], [])
                    if esistenti:
                        st.caption("Già caricati:")
                        for rec in sorted(esistenti, key=lambda r: r.get("data_scadenza") or "", reverse=True):
                            sc = rec.get("data_scadenza")
                            sc_fmt = _dt.date.fromisoformat(sc).strftime("%d/%m/%Y") if sc else "-"
                            etichetta_tipo = rec.get("tipo", "")
                            valore_txt = f" (valore: {rec['valore']})" if rec.get("valore") not in (None, 0, 0.0) else ""
                            riga_col1, riga_col2 = st.columns([5, 1])
                            with riga_col1:
                                badge = ""
                                if sc:
                                    sc_date = _dt.date.fromisoformat(sc)
                                    if sc_date < oggi:
                                        badge = "🔴 "
                                    elif (sc_date - oggi).days <= 15:
                                        badge = "🟠 "
                                st.write(f"{badge}{etichetta_tipo}{valore_txt} — scade {sc_fmt}")
                            with riga_col2:
                                tabella_rec = "stati_sanitari" if c["tipo"] == "allevatore" else "documenti_conferitori"
                                if st.button("🗑️", key=f"delrec_{tabella_rec}_{rec['id']}"):
                                    client.table(tabella_rec).delete().eq("id", rec["id"]).execute()
                                    st.rerun()
                        st.divider()
                    else:
                        st.caption("Nessun dato caricato ancora.")

                    if c["tipo"] == "allevatore":
                        with st.form(f"sanitario_{c['id']}"):
                            tipo_es = st.selectbox("Tipo esame", ["brucellosi", "tubercolosi", "leucosi",
                                                                    "carica_batterica", "cellule_somatiche"],
                                                     key=f"tipoes_{c['id']}")
                            valore = st.number_input("Valore (se applicabile)", value=0.0, key=f"val_{c['id']}")
                            laboratorio = st.text_input(
                                "Laboratorio (per carica batterica - chi rilascia le analisi)",
                                key=f"lab_{c['id']}",
                            )
                            rilascio = st.date_input("Data rilascio", value=_dt.date.today(), key=f"ril_{c['id']}", format="DD/MM/YYYY")
                            scadenza = st.date_input("Data scadenza", value=_dt.date.today(), key=f"sca_{c['id']}", format="DD/MM/YYYY")
                            if st.form_submit_button("Aggiungi esame"):
                                client.table("stati_sanitari").insert({
                                    "conferitore_id": c["id"], "tipo": tipo_es,
                                    "valore": valore, "laboratorio": laboratorio or None,
                                    "data_rilascio": str(rilascio),
                                    "data_scadenza": str(scadenza),
                                }).execute()
                                st.success("Salvato.")
                                st.rerun()
                    else:
                        doc_tipo = "autocertificazione" if c["tipo"] in ("caseificio", "intermediario") else "contratto"
                        with st.form(f"doc_{c['id']}"):
                            scadenza = st.date_input(f"Scadenza {doc_tipo}", value=_dt.date.today(), key=f"docsca_{c['id']}", format="DD/MM/YYYY")
                            if st.form_submit_button(f"Salva {doc_tipo}"):
                                client.table("documenti_conferitori").insert({
                                    "conferitore_id": c["id"], "tipo": doc_tipo,
                                    "data_scadenza": str(scadenza),
                                }).execute()
                                st.success("Salvato.")
                                st.rerun()

        with col5:
            if is_owner():
                if st.button("🗑️", key=f"del_{c['id']}", help="Elimina conferitore"):
                    st.session_state[f"conferma_del_{c['id']}"] = True
                if st.session_state.get(f"conferma_del_{c['id']}"):
                    if st.button("Conferma eliminazione", key=f"del_conferma_{c['id']}"):
                        client.table("conferitori").delete().eq("id", c["id"]).execute()
                        st.session_state.pop(f"conferma_del_{c['id']}", None)
                        st.success("Eliminato.")
                        st.rerun()

# ------------------------------------------------------------
# BLOCCO: AVVISI SCADENZE
# Riusa gli stessi dati già recuperati sopra (sanitari_by_conf/docs_by_conf),
# senza ripetere le stesse query due volte.
# ------------------------------------------------------------
st.divider()
st.subheader("⚠️ Avvisi scadenze")

avvisi = []
for lista in sanitari_by_conf.values():
    for s in lista:
        conf = s.get("conferitori") or {}
        if not s.get("data_scadenza"):
            continue
        sc = _dt.date.fromisoformat(s["data_scadenza"])
        if sc < oggi:
            avvisi.append(f"🔴 {conf.get('ragione_sociale')}: {s['tipo']} SCADUTO il {sc.strftime('%d/%m/%Y')}")
        elif (sc - oggi).days <= 15:
            avvisi.append(f"🟠 {conf.get('ragione_sociale')}: {s['tipo']} in scadenza il {sc.strftime('%d/%m/%Y')}")
for lista in docs_by_conf.values():
    for d in lista:
        conf = d.get("conferitori") or {}
        if not d.get("data_scadenza"):
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

st.divider()

# ------------------------------------------------------------
# BLOCCO: TABELLA STAMPABILE CONFERITORI
# Una riga per conferitore con: denominazione, codice di stalla O bollo CE
# (853), indirizzo, P.IVA, prodotto/i (tipo/i di latte) fornito/i, e stati
# sanitari - per Brucellosi/Tubercolosi/Leucosi solo la DATA DI SCADENZA più
# recente, per la Carica batterica il LABORATORIO che rilascia le analisi
# (non un valore numerico), come richiesto esplicitamente.
# ------------------------------------------------------------
st.subheader("📋 Tabella conferitori (stampabile)")


def _ultimo_per_tipo(lista, tipo):
    """Ritorna il record più recente (per data_scadenza) di un certo tipo, o None."""
    candidati = [r for r in lista if r.get("tipo") == tipo]
    if not candidati:
        return None
    return sorted(candidati, key=lambda r: r.get("data_scadenza") or "", reverse=True)[0]


righe_tabella = []
for c in conferitori:
    sanitari_c = sanitari_by_conf.get(c["id"], [])
    docs_c = docs_by_conf.get(c["id"], [])
    tipi_c = ", ".join([t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]) or "-"

    brucellosi = _ultimo_per_tipo(sanitari_c, "brucellosi")
    tubercolosi = _ultimo_per_tipo(sanitari_c, "tubercolosi")
    leucosi = _ultimo_per_tipo(sanitari_c, "leucosi")
    carica_batt = _ultimo_per_tipo(sanitari_c, "carica_batterica")
    doc_principale = docs_c[0] if docs_c else None

    def _data_fmt(rec):
        sc = rec.get("data_scadenza") if rec else None
        return _dt.date.fromisoformat(sc).strftime("%d/%m/%Y") if sc else "-"

    righe_tabella.append({
        "Denominazione": c["ragione_sociale"],
        "Codice stalla / Bollo CE": c.get("codice_stalla") or c.get("bollo_ce") or "-",
        "Indirizzo": c.get("sede_operativa") or c.get("sede_legale") or "-",
        "P.IVA": c.get("piva") or "-",
        "Prodotto/i fornito/i": tipi_c,
        "Scad. Brucellosi": _data_fmt(brucellosi),
        "Scad. Tubercolosi": _data_fmt(tubercolosi),
        "Scad. Leucosi": _data_fmt(leucosi),
        "Laboratorio (carica batterica)": (carica_batt or {}).get("laboratorio") or "-",
        "Scad. autocertificazione/contratto": _data_fmt(doc_principale),
    })

if righe_tabella:
    st.dataframe(righe_tabella, hide_index=True, width="stretch")
    try:
        df_conferitori = pd.DataFrame(righe_tabella)
        csv_bytes = df_conferitori.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        st.download_button(
            "🖨️ Esporta/Stampa tabella conferitori (CSV compatibile Excel)",
            data=csv_bytes, file_name="tabella_conferitori.csv", mime="text/csv",
        )
    except Exception as e:
        st.error(f"Errore nella generazione del CSV: {e}")
else:
    st.info("Nessun conferitore da mostrare.")
