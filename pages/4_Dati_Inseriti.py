# ============================================================
# PAGINA: DATI INSERITI
# Griglia stile Excel: conferitori attivi (in ordine) in colonna
# con DDT/KG, date del periodo scelto in riga. Totali per
# conferitore e per tipo di latte. Movimenti congelato.
# ============================================================
import streamlit as st
import pandas as pd
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Dati Inseriti", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Dati Inseriti")
mostra_header_caseificio()

caseificio_id = st.session_state.get("caseificio_id")
periodo_inizio = st.session_state.get("periodo_inizio")
periodo_fine = st.session_state.get("periodo_fine")

if not caseificio_id or not periodo_inizio:
    st.info("Seleziona caseificio e periodo dalla pagina principale prima di continuare.")
    st.stop()

st.caption(f"Periodo: {st.session_state.get('periodo_label')}")

TIPI_LATTE_LABEL = {
    "bufala_dop": "Bufala DOP", "bufala": "Bufala", "vaccino": "Vaccino",
    "semilavorato_bufala": "Semilavorato bufala", "semilavorato_vaccino": "Semilavorato vaccino",
    "bufala_congelato": "Bufala congelato", "vaccino_congelato": "Vaccino congelato", "altro": "Altro",
}

# ------------------------------------------------------------
# BLOCCO: LISTA DATE DEL PERIODO
# ------------------------------------------------------------
n_giorni = (periodo_fine - periodo_inizio).days + 1
date_periodo = [periodo_inizio + _dt.timedelta(days=i) for i in range(n_giorni)]

# ------------------------------------------------------------
# BLOCCO: CONFERITORI ATTIVI IN ORDINE
# ------------------------------------------------------------
conferitori = (
    client.table("conferitori")
    .select("*, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .eq("attivo", True)
    .order("ordine")
    .execute()
    .data
)

if not conferitori:
    st.info("Nessun conferitore attivo. Vai su 'Conferitori' per aggiungerne o attivarne uno.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: CARICA CONFERIMENTI ESISTENTI DEL PERIODO
# ------------------------------------------------------------
conferitore_ids = [c["id"] for c in conferitori]
esistenti = (
    client.table("conferimenti")
    .select("*")
    .in_("conferitore_id", conferitore_ids)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
mappa_esistenti = {(e["conferitore_id"], e["data"]): e for e in esistenti}

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE GRIGLIA
# ------------------------------------------------------------
st.subheader("Griglia conferimenti")
st.caption("Modifica le celle direttamente. Puoi copiare/incollare piu' valori insieme (anche da Excel). Ricorda di premere 'Salva conferimenti' in fondo.")

righe = []
for d in date_periodo:
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for c in conferitori:
        rec = mappa_esistenti.get((c["id"], str(d)))
        riga[f"{c['ragione_sociale']} - DDT"] = rec["ddt"] if rec else ""
        riga[f"{c['ragione_sociale']} - KG"] = float(rec["kg"]) if rec and rec.get("kg") is not None else 0.0
    righe.append(riga)

df = pd.DataFrame(righe)

column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for c in conferitori:
    column_config[f"{c['ragione_sociale']} - DDT"] = st.column_config.TextColumn(f"{c['ragione_sociale']}\nDDT")
    column_config[f"{c['ragione_sociale']} - KG"] = st.column_config.NumberColumn(f"{c['ragione_sociale']}\nKG", min_value=0.0, step=1.0)

df_modificato = st.data_editor(
    df, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_conferimenti"
)

if is_owner():
    if st.button("💾 Salva conferimenti"):
        records = []
        for i, d in enumerate(date_periodo):
            for c in conferitori:
                ddt = df_modificato.loc[i, f"{c['ragione_sociale']} - DDT"]
                kg = df_modificato.loc[i, f"{c['ragione_sociale']} - KG"]
                if (ddt and str(ddt).strip()) or (kg and float(kg) > 0):
                    records.append({
                        "caseificio_id": caseificio_id,
                        "conferitore_id": c["id"],
                        "data": str(d),
                        "ddt": str(ddt) if ddt else None,
                        "kg": float(kg) if kg else 0.0,
                    })
        if records:
            client.table("conferimenti").upsert(records, on_conflict="conferitore_id,data").execute()
            st.success(f"Salvati {len(records)} conferimenti.")
            st.rerun()
        else:
            st.info("Nessun dato da salvare.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: MOVIMENTI LATTE CONGELATO
# ------------------------------------------------------------
st.subheader("❄️ Movimenti latte congelato")
st.caption("DDT e struttura esterna sono facoltativi: lasciali vuoti se il latte resta nel tuo stabilimento (semplice prelievo interno); compilali se il latte e' tenuto presso una struttura terza.")
mcol1, mcol2 = st.columns(2)
with mcol1:
    with st.expander("➕ Registra scongelamento (si somma alla Bufala non-DOP)"):
        with st.form("nuovo_scongelamento"):
            data_sc = st.date_input("Data", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine)
            kg_sc = st.number_input("KG scongelati", min_value=0.0, step=1.0)
            ddt_sc = st.text_input("N. DDT (facoltativo, solo se struttura esterna)")
            struttura_sc = st.text_input("Struttura esterna (facoltativo)")
            if st.form_submit_button("Salva scongelamento"):
                client.table("movimenti_congelato").insert({
                    "caseificio_id": caseificio_id, "data": str(data_sc),
                    "tipo": "scongelamento", "kg": kg_sc,
                    "ddt": ddt_sc or None, "struttura_esterna": struttura_sc or None,
                }).execute()
                st.success("Registrato.")
                st.rerun()
with mcol2:
    with st.expander("➕ Registra congelamento (bufala DOP o non-DOP)"):
        with st.form("nuovo_congelamento"):
            data_cg = st.date_input("Data ", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine)
            origine_cg = st.radio("Origine", ["bufala_dop", "bufala"], format_func=lambda x: "Bufala DOP" if x == "bufala_dop" else "Bufala")
            kg_cg = st.number_input("KG messi in congelamento", min_value=0.0, step=1.0)
            ddt_cg = st.text_input("N. DDT (facoltativo, solo se struttura esterna)")
            struttura_cg = st.text_input("Struttura esterna (facoltativo) ")
            if st.form_submit_button("Salva congelamento"):
                client.table("movimenti_congelato").insert({
                    "caseificio_id": caseificio_id, "data": str(data_cg),
                    "tipo": "congelamento", "origine": origine_cg, "kg": kg_cg,
                    "ddt": ddt_cg or None, "struttura_esterna": struttura_cg or None,
                }).execute()
                st.success("Registrato.")
                st.rerun()

movimenti = (
    client.table("movimenti_congelato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .order("data")
    .execute()
    .data
)
if movimenti:
    st.table([{
        "Data": _dt.date.fromisoformat(m["data"]).strftime("%d/%m/%Y"),
        "Tipo": "Scongelamento" if m["tipo"] == "scongelamento" else "Congelamento",
        "Origine": ("Bufala DOP" if m.get("origine") == "bufala_dop" else "Bufala") if m.get("origine") else "-",
        "KG": m["kg"],
        "DDT": m.get("ddt") or "-",
        "Struttura esterna": m.get("struttura_esterna") or "(prelievo interno)",
    } for m in movimenti])
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

# ------------------------------------------------------------
# BLOCCO: TOTALE PER CONFERITORE NEL PERIODO
# ------------------------------------------------------------
st.subheader("Totale per conferitore nel periodo")
totali_conferitore = []
for c in conferitori:
    tot = sum(
        float(mappa_esistenti[(c["id"], str(d))]["kg"] or 0)
        for d in date_periodo if (c["id"], str(d)) in mappa_esistenti
    )
    if tot > 0:
        totali_conferitore.append({"Conferitore": c["ragione_sociale"], "Totale KG periodo": tot})
if totali_conferitore:
    st.table(totali_conferitore)
else:
    st.write("Nessun conferimento ancora registrato in questo periodo.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: TOTALE GIORNALIERO PER TIPO DI LATTE
# ------------------------------------------------------------
st.subheader("Totale giornaliero per tipo di latte")

tipi_presenti = set()
for c in conferitori:
    for t in c.get("conferitori_tipi_latte", []):
        tipi_presenti.add(t["tipo_latte"])

if not tipi_presenti:
    st.write("Nessun tipo di latte associato ai conferitori attivi.")
else:
    scongelamenti_per_giorno = {}
    for m in movimenti:
        if m["tipo"] == "scongelamento":
            scongelamenti_per_giorno[m["data"]] = scongelamenti_per_giorno.get(m["data"], 0) + float(m["kg"])

    righe_tipo = []
    for tipo in sorted(tipi_presenti):
        riga = {"Tipo di latte": TIPI_LATTE_LABEL.get(tipo, tipo)}
        totale_periodo = 0.0
        ha_almeno_un_valore = False
        for d in date_periodo:
            tot_giorno = 0.0
            for c in conferitori:
                tipi_conferitore = [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]
                if tipo in tipi_conferitore:
                    rec = mappa_esistenti.get((c["id"], str(d)))
                    if rec and rec.get("kg"):
                        tot_giorno += float(rec["kg"])
            if tipo == "bufala":
                tot_giorno += scongelamenti_per_giorno.get(str(d), 0.0)
            if tot_giorno > 0:
                ha_almeno_un_valore = True
                riga[d.strftime("%d/%m")] = tot_giorno
            else:
                riga[d.strftime("%d/%m")] = "-"
            totale_periodo += tot_giorno
        riga["Totale periodo"] = totale_periodo
        if ha_almeno_un_valore:
            righe_tipo.append(riga)

    if righe_tipo:
        st.table(righe_tipo)
    else:
        st.write("Nessun conferimento ancora registrato in questo periodo.")
