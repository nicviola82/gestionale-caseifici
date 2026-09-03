# ============================================================
# PAGINA: PRODUZIONI
# Griglia stile Excel: per ogni prodotto, colonne SEMPRE VISIBILI
# in base al suo tipo di vendita (impostato in Prodotti):
#   - "diretta"  -> una sola colonna (100% diretta)
#   - "terzi", NO colonne multi-terzi configurate -> una sola colonna (100% terzi)
#   - "terzi"/"entrambe", CON colonne multi-terzi configurate in Prodotti ->
#     una colonna FISSA E NOMINATA DALL'UTENTE per ciascun destinatario
#     (sostituisce la vecchia sezione separata di assegnazione libera - 27/08)
#   - "entrambe" -> colonna/e diretta SEMPRE visibile insieme alle colonne terzi
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
# BLOCCO: COLONNE VENDITA A TERZI NOMINATE (per prodotto)
# Aggiunto 27/08: se un prodotto ha "consente_piu_terzi" e ha delle colonne
# configurate in Prodotti (nome + ordine), la griglia mostra QUELLE colonne
# fisse invece di un'unica colonna "v.ind". Se il flag e' attivo ma non e'
# stata configurata ancora nessuna colonna, avvisiamo e usiamo comunque una
# sola colonna generica di transizione.
# ------------------------------------------------------------
prodotti_multi_ids = [p["id"] for p in prodotti if p.get("consente_piu_terzi")]
colonne_per_prodotto = {}
if prodotti_multi_ids:
    tutte_colonne = (
        client.table("prodotto_colonne_terzi").select("*")
        .in_("prodotto_id", prodotti_multi_ids).order("ordine").execute().data
    )
    for c in tutte_colonne:
        colonne_per_prodotto.setdefault(c["prodotto_id"], []).append(c)

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

# valori già assegnati per colonna nominata (produzione_id, colonna_id) -> kg
terzi_dettaglio_map = {}
id_produzioni_esistenti = [e["id"] for e in esistenti]
if id_produzioni_esistenti and colonne_per_prodotto:
    for r in (
        client.table("produzioni_terzi").select("produzione_id, colonna_id, kg")
        .in_("produzione_id", id_produzioni_esistenti).not_.is_("colonna_id", "null")
        .execute().data
    ):
        terzi_dettaglio_map[(r["produzione_id"], r["colonna_id"])] = float(r["kg"] or 0)

def etichetta_prodotto(p):
    return f"{p.get('abbreviazione') or p['nome']}{' (DOP)' if p['is_dop'] else ''}"

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE GRIGLIA
# Colonne per prodotto in base al tipo_vendita (impostato in Prodotti):
#   diretta  -> 1 colonna "<etichetta> v.dir"
#   terzi    -> colonna/e terzi (nominate se configurate, altrimenti "v.ind")
#   entrambe -> colonna "v.dir" + colonna/e terzi, SEMPRE visibili insieme
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
            colonne = colonne_per_prodotto.get(p["id"])
            if colonne:
                for c in colonne:
                    valore = terzi_dettaglio_map.get((rec["id"], c["id"]), 0.0) if rec else 0.0
                    riga[f"p{p['id']}_terzi_c{c['id']}"] = valore
            else:
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
    colonne = colonne_per_prodotto.get(p["id"])
    if colonne:
        for c in colonne:
            key = f"p{p['id']}_terzi_c{c['id']}"
            if key in df.columns:
                column_config[key] = st.column_config.NumberColumn(f"{etichetta}\n{c['nome']}", min_value=0.0, step=1.0)
    elif f"p{p['id']}_terzi" in df.columns:
        lbl = f"{etichetta}\nv.ind" if tipo_vendita == "entrambe" else f"{etichetta}\nTotale (terzi)"
        column_config[f"p{p['id']}_terzi"] = st.column_config.NumberColumn(lbl, min_value=0.0, step=1.0)
        if p.get("consente_piu_terzi"):
            st.warning(f"'{p['nome']}' ha 'consenti piu' destinatari' attivo ma nessuna colonna configurata: vai su Prodotti > Modifica per nominarle. Per ora usa una sola colonna 'v.ind'.")

df_modificato = st.data_editor(
    df, column_config=column_config, hide_index=True, width="stretch", key="griglia_produzioni"
)

if is_owner():
    if st.button("💾 Salva produzioni"):
        records = []
        for i, d in enumerate(date_periodo):
            for p in prodotti:
                kg_dir = float(df_modificato.loc[i, f"p{p['id']}_dir"]) if f"p{p['id']}_dir" in df_modificato.columns else 0.0
                colonne = colonne_per_prodotto.get(p["id"])
                if colonne:
                    kg_terzi = sum(
                        float(df_modificato.loc[i, f"p{p['id']}_terzi_c{c['id']}"] or 0)
                        for c in colonne if f"p{p['id']}_terzi_c{c['id']}" in df_modificato.columns
                    )
                else:
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
            righe_salvate = (
                client.table("produzioni").upsert(records, on_conflict="prodotto_id,data").execute().data
            )
            id_per_chiave = {(r["prodotto_id"], r["data"]): r["id"] for r in righe_salvate}
            # dettaglio per colonna nominata (solo per prodotti con colonne configurate)
            dettagli_terzi = []
            for i, d in enumerate(date_periodo):
                for p in prodotti:
                    colonne = colonne_per_prodotto.get(p["id"])
                    if not colonne:
                        continue
                    produzione_id = id_per_chiave.get((p["id"], str(d)))
                    if not produzione_id:
                        continue
                    for c in colonne:
                        key = f"p{p['id']}_terzi_c{c['id']}"
                        if key not in df_modificato.columns:
                            continue
                        dettagli_terzi.append({
                            "produzione_id": produzione_id, "colonna_id": c["id"],
                            "kg": float(df_modificato.loc[i, key] or 0),
                        })
            if dettagli_terzi:
                client.table("produzioni_terzi").upsert(dettagli_terzi, on_conflict="produzione_id,colonna_id").execute()
            st.success(f"Salvate {len(records)} produzioni.")
            st.rerun()
        else:
            st.info("Nessun dato da salvare.")

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
