# ============================================================
# PAGINA: PRODUZIONI
# Griglia stile Excel: per ogni prodotto, colonne SEMPRE VISIBILI
# in base al suo tipo di vendita (impostato in Prodotti):
#   - "diretta"  -> una sola colonna (100% diretta)
#   - "terzi"    -> una sola colonna (100% terzi)
#   - "entrambe" -> DUE colonne sempre visibili: "v.dir" e "v.ind"
# Il Totale (kg_diretta + kg_terzi) lo calcola sempre il programma,
# non è mai inserito a mano.
# ============================================================
import streamlit as st
import pandas as pd
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Produzioni", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Produzioni")
mostra_header_caseificio()

caseificio_id = st.session_state.get("caseificio_id")
periodo_inizio = st.session_state.get("periodo_inizio")
periodo_fine = st.session_state.get("periodo_fine")

if not caseificio_id or not periodo_inizio:
    st.info("Seleziona caseificio e periodo dalla pagina principale prima di continuare.")
    st.stop()

st.caption(f"Periodo: {st.session_state.get('periodo_label')}")

# ------------------------------------------------------------
# BLOCCO: LISTA DATE DEL PERIODO
# ------------------------------------------------------------
n_giorni = (periodo_fine - periodo_inizio).days + 1
date_periodo = [periodo_inizio + _dt.timedelta(days=i) for i in range(n_giorni)]

# ------------------------------------------------------------
# BLOCCO: PRODOTTI ATTIVI E VISIBILI IN PRODUZIONI
# ------------------------------------------------------------
prodotti = (
    client.table("prodotti")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .eq("attivo", True)
    .eq("mostra_in_produzioni", True)
    .order("nome")
    .execute()
    .data
)

if not prodotti:
    st.info("Nessun prodotto attivo/visibile in Produzioni. Vai su 'Prodotti' per attivarne uno.")
    st.stop()

# ------------------------------------------------------------
# BLOCCO: CARICA PRODUZIONI ESISTENTI DEL PERIODO
# ------------------------------------------------------------
prodotto_ids = [p["id"] for p in prodotti]
esistenti = (
    client.table("produzioni")
    .select("*")
    .in_("prodotto_id", prodotto_ids)
    .gte("data", str(periodo_inizio))
    .lte("data", str(periodo_fine))
    .execute()
    .data
)
mappa_esistenti = {(e["prodotto_id"], e["data"]): e for e in esistenti}

def etichetta_prodotto(p):
    return f"{p.get('abbreviazione') or p['nome']}{' (DOP)' if p['is_dop'] else ''}"

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE GRIGLIA
# Colonne per prodotto in base al tipo_vendita (impostato in Prodotti):
#   diretta  -> 1 colonna "<etichetta> v.dir"
#   terzi    -> 1 colonna "<etichetta> v.ind"
#   entrambe -> 2 colonne "<etichetta> v.dir" + "<etichetta> v.ind", SEMPRE
#               visibili insieme (non più una tendina facoltativa)
# Il Totale non è mai una colonna editabile: si calcola sempre come somma.
# ------------------------------------------------------------
st.subheader("Griglia produzioni")
st.caption("Inserisci direttamente i KG per vendita diretta e/o a terzi. Il Totale lo calcola sempre il programma. Ricorda di premere 'Salva produzioni' in fondo.")

righe = []
for d in date_periodo:
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for p in prodotti:
        rec = mappa_esistenti.get((p["id"], str(d)))
        tipo_vendita = p.get("tipo_vendita") or "entrambe"
        kg_dir = float(rec["kg_diretta"]) if rec and rec.get("kg_diretta") is not None else 0.0
        kg_terzi = float(rec["kg_terzi"]) if rec and rec.get("kg_terzi") is not None else 0.0
        if tipo_vendita in ("diretta", "entrambe"):
            riga[f"p{p['id']}_dir"] = kg_dir
        if tipo_vendita in ("terzi", "entrambe"):
            riga[f"p{p['id']}_terzi"] = kg_terzi
    righe.append(riga)

df = pd.DataFrame(righe)

column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for p in prodotti:
    etichetta = etichetta_prodotto(p)
    tipo_vendita = p.get("tipo_vendita") or "entrambe"
    if f"p{p['id']}_dir" in df.columns:
        lbl = f"{etichetta}\nv.dir" if tipo_vendita == "entrambe" else f"{etichetta}\nTotale (diretta)"
        column_config[f"p{p['id']}_dir"] = st.column_config.NumberColumn(lbl, min_value=0.0, step=1.0)
    if f"p{p['id']}_terzi" in df.columns:
        lbl = f"{etichetta}\nv.ind" if tipo_vendita == "entrambe" else f"{etichetta}\nTotale (terzi)"
        column_config[f"p{p['id']}_terzi"] = st.column_config.NumberColumn(lbl, min_value=0.0, step=1.0)

df_modificato = st.data_editor(
    df, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_produzioni"
)

if is_owner():
    if st.button("💾 Salva produzioni"):
        records = []
        for i, d in enumerate(date_periodo):
            for p in prodotti:
                kg_dir = float(df_modificato.loc[i, f"p{p['id']}_dir"]) if f"p{p['id']}_dir" in df_modificato.columns else 0.0
                kg_terzi = float(df_modificato.loc[i, f"p{p['id']}_terzi"]) if f"p{p['id']}_terzi" in df_modificato.columns else 0.0
                tot = kg_dir + kg_terzi
                if tot > 0:
                    records.append({
                        "caseificio_id": caseificio_id,
                        "prodotto_id": p["id"],
                        "data": str(d),
                        "kg_totale": tot,
                        "kg_diretta": kg_dir,
                        "kg_terzi": kg_terzi,
                    })
        if records:
            client.table("produzioni").upsert(records, on_conflict="prodotto_id,data").execute()
            st.success(f"Salvate {len(records)} produzioni.")
            st.rerun()
        else:
            st.info("Nessun dato da salvare.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: SUDDIVISIONE VENDITA A TERZI (PRODOTTI MULTI-TERZI)
# ------------------------------------------------------------
prodotti_multi = [p for p in prodotti if p.get("consente_piu_terzi")]

if prodotti_multi:
    st.subheader("🔀 Suddivisione vendita a terzi tra più destinatari")
    st.caption("Solo per i prodotti abilitati in Prodotti ('Consenti piu' destinatari'). Il totale delle righe qui sotto dovrebbe corrispondere al KG v.ind (terzi) calcolato per quel giorno/prodotto.")

    destinatari = (
        client.table("destinatari_vendita")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .order("ragione_sociale")
        .execute()
        .data
    )

    if not destinatari:
        st.info("Nessun destinatario di vendita attivo. Aggiungine uno nella pagina Conferitori, sezione 'A chi vendo/cedo il latte'.")
    else:
        prodotto_scelto_nome2 = st.selectbox("Prodotto", [p["nome"] for p in prodotti_multi], key="prod_multi_scelto")
        prodotto_scelto2 = next(p for p in prodotti_multi if p["nome"] == prodotto_scelto_nome2)
        data_scelta2 = st.date_input("Data", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine, key="data_multi_scelta", format="DD/MM/YYYY")

        produzione_giorno = mappa_esistenti.get((prodotto_scelto2["id"], str(data_scelta2)))
        if not produzione_giorno:
            st.warning("Nessuna produzione salvata per questo prodotto in questa data. Salva prima la griglia sopra.")
        else:
            produzione_id = produzione_giorno["id"]
            righe_terzi = (
                client.table("produzioni_terzi")
                .select("*, destinatari_vendita(ragione_sociale)")
                .eq("produzione_id", produzione_id)
                .execute()
                .data
            )
            if righe_terzi:
                st.table([{
                    "Destinatario": r["destinatari_vendita"]["ragione_sociale"],
                    "KG": r["kg"],
                } for r in righe_terzi])
                tot_assegnato = sum(float(r["kg"]) for r in righe_terzi)
                st.caption(f"Totale già assegnato: {tot_assegnato} kg su {produzione_giorno.get('kg_terzi') or 0} kg v.ind (terzi).")

            with st.form("nuovo_terzo"):
                dest_nome = st.selectbox("Destinatario", [d["ragione_sociale"] for d in destinatari])
                kg_dest = st.number_input("KG per questo destinatario", min_value=0.0, step=1.0)
                if st.form_submit_button("Aggiungi assegnazione"):
                    dest_id = next(d["id"] for d in destinatari if d["ragione_sociale"] == dest_nome)
                    client.table("produzioni_terzi").insert({
                        "produzione_id": produzione_id, "destinatario_id": dest_id, "kg": kg_dest,
                    }).execute()
                    st.success("Assegnato.")
                    st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: TOTALE PER PRODOTTO NEL PERIODO
# ------------------------------------------------------------
st.subheader("Totale per prodotto nel periodo")
totali_prodotto = []
for p in prodotti:
    tot = sum(
        float(mappa_esistenti[(p["id"], str(d))]["kg_totale"] or 0)
        for d in date_periodo if (p["id"], str(d)) in mappa_esistenti
    )
    dir_tot = sum(
        float(mappa_esistenti[(p["id"], str(d))]["kg_diretta"] or 0)
        for d in date_periodo if (p["id"], str(d)) in mappa_esistenti
    )
    terzi_tot = sum(
        float(mappa_esistenti[(p["id"], str(d))]["kg_terzi"] or 0)
        for d in date_periodo if (p["id"], str(d)) in mappa_esistenti
    )
    if tot > 0:
        totali_prodotto.append({"Prodotto": etichetta_prodotto(p), "Totale KG": tot, "v.dir KG": dir_tot, "v.ind KG": terzi_tot})
if totali_prodotto:
    st.table(totali_prodotto)
else:
    st.write("Nessuna produzione ancora registrata in questo periodo.")
