# ============================================================
# PAGINA: PRODUZIONI
# Griglia stile Excel: prodotti attivi e visibili in colonna
# (Totale / Diretta / Terzi), giorni del periodo in riga.
# Per i prodotti "multi-terzi" e' possibile suddividere il
# venduto a terzi tra piu' destinatari.
# ============================================================
import streamlit as st
import pandas as pd
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Produzioni", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Produzioni")

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

# ------------------------------------------------------------
# BLOCCO: COSTRUZIONE GRIGLIA
# ------------------------------------------------------------
st.subheader("Griglia produzioni")
st.caption("Per ogni prodotto: KG Totale, KG Diretta, KG Terzi. Ricorda di premere 'Salva produzioni' in fondo.")

righe = []
for d in date_periodo:
    riga = {"Data": d.strftime("%d/%m/%Y")}
    for p in prodotti:
        rec = mappa_esistenti.get((p["id"], str(d)))
        riga[f"{p['nome']} - Totale"] = float(rec["kg_totale"]) if rec and rec.get("kg_totale") is not None else 0.0
        riga[f"{p['nome']} - Diretta"] = float(rec["kg_diretta"]) if rec and rec.get("kg_diretta") is not None else 0.0
        riga[f"{p['nome']} - Terzi"] = float(rec["kg_terzi"]) if rec and rec.get("kg_terzi") is not None else 0.0
    righe.append(riga)

df = pd.DataFrame(righe)

column_config = {"Data": st.column_config.TextColumn("Data", disabled=True)}
for p in prodotti:
    column_config[f"{p['nome']} - Totale"] = st.column_config.NumberColumn(f"{p['nome']}\nTotale KG", min_value=0.0, step=1.0)
    column_config[f"{p['nome']} - Diretta"] = st.column_config.NumberColumn(f"{p['nome']}\nDiretta KG", min_value=0.0, step=1.0)
    column_config[f"{p['nome']} - Terzi"] = st.column_config.NumberColumn(f"{p['nome']}\nTerzi KG", min_value=0.0, step=1.0)

df_modificato = st.data_editor(
    df, column_config=column_config, hide_index=True, use_container_width=True, key="griglia_produzioni"
)

if is_owner():
    if st.button("💾 Salva produzioni"):
        records = []
        for i, d in enumerate(date_periodo):
            for p in prodotti:
                tot = df_modificato.loc[i, f"{p['nome']} - Totale"]
                dir_ = df_modificato.loc[i, f"{p['nome']} - Diretta"]
                terzi = df_modificato.loc[i, f"{p['nome']} - Terzi"]
                if (tot and float(tot) > 0) or (dir_ and float(dir_) > 0) or (terzi and float(terzi) > 0):
                    records.append({
                        "caseificio_id": caseificio_id,
                        "prodotto_id": p["id"],
                        "data": str(d),
                        "kg_totale": float(tot) if tot else 0.0,
                        "kg_diretta": float(dir_) if dir_ else 0.0,
                        "kg_terzi": float(terzi) if terzi else 0.0,
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
    st.caption("Solo per i prodotti abilitati in Prodotti ('Consenti piu' destinatari'). Il totale delle righe qui sotto dovrebbe corrispondere al KG Terzi inserito nella griglia sopra per quel giorno/prodotto.")

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
        st.info("Nessun destinatario di vendita attivo. Aggiungine uno nella pagina Conferitori, sezione 'A chi vendo/cedo il latte' (i destinatari vengono riusati anche qui per i prodotti finiti).")
    else:
        prodotto_scelto_nome = st.selectbox("Prodotto", [p["nome"] for p in prodotti_multi], key="prod_multi_scelto")
        prodotto_scelto = next(p for p in prodotti_multi if p["nome"] == prodotto_scelto_nome)
        data_scelta = st.date_input("Data", value=periodo_inizio, min_value=periodo_inizio, max_value=periodo_fine, key="data_multi_scelta")

        produzione_giorno = mappa_esistenti.get((prodotto_scelto["id"], str(data_scelta)))
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
                st.caption(f"Totale già assegnato: {tot_assegnato} kg su {produzione_giorno.get('kg_terzi') or 0} kg Terzi inseriti nella griglia.")

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
        totali_prodotto.append({"Prodotto": p["nome"], "Totale KG": tot, "Diretta KG": dir_tot, "Terzi KG": terzi_tot})
if totali_prodotto:
    st.table(totali_prodotto)
else:
    st.write("Nessuna produzione ancora registrata in questo periodo.")
