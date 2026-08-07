# ============================================================
# PAGINA: REGISTRO
# Il "motore": latte messo in lavorazione per prodotto/giorno,
# resa calcolata automaticamente, integrazioni tra prodotti
# (es. non-DOP completata con latte DOP), giacenze latte per
# tipo lungo tutta la storia del caseificio (non solo il periodo),
# avviso 60 ore per il latte DOP.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button, is_owner

st.set_page_config(page_title="Registro", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Registro")

caseificio_id = st.session_state.get("caseificio_id")
periodo_inizio = st.session_state.get("periodo_inizio")
periodo_fine = st.session_state.get("periodo_fine")

if not caseificio_id or not periodo_inizio:
    st.info("Seleziona caseificio e periodo dalla pagina principale prima di continuare.")
    st.stop()

st.caption(f"Periodo: {st.session_state.get('periodo_label')}")

TIPI_LATTE_LABEL = {"bufala_dop": "Bufala DOP", "bufala": "Bufala", "vaccino": "Vaccino"}

# ------------------------------------------------------------
# BLOCCO: SCELTA GIORNO DA LAVORARE (dentro il periodo)
# ------------------------------------------------------------
st.subheader("Giorno da lavorare")
n_giorni = (periodo_fine - periodo_inizio).days + 1
date_periodo = [periodo_inizio + _dt.timedelta(days=i) for i in range(n_giorni)]
giorno = st.selectbox("Data", date_periodo, format_func=lambda d: d.strftime("%A %d/%m/%Y"), key="registro_giorno")

# ------------------------------------------------------------
# BLOCCO: PRODOTTI ATTIVI
# ------------------------------------------------------------
prodotti = (
    client.table("prodotti")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .eq("attivo", True)
    .order("nome")
    .execute()
    .data
)
if not prodotti:
    st.info("Nessun prodotto attivo. Vai su 'Prodotti' per attivarne uno.")
    st.stop()

prodotti_by_id = {p["id"]: p for p in prodotti}

# ------------------------------------------------------------
# BLOCCO: RIGHE REGISTRO GIA' SALVATE PER QUESTO GIORNO
# ------------------------------------------------------------
righe_oggi = (
    client.table("registro")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .eq("data", str(giorno))
    .execute()
    .data
)
righe_oggi_by_prodotto = {r["prodotto_id"]: r for r in righe_oggi}

def resa_di(prodotto_id):
    r = righe_oggi_by_prodotto.get(prodotto_id)
    if r and r.get("latte_kg") and float(r["latte_kg"]) > 0:
        return float(r["produzione_kg"]) / float(r["latte_kg"])
    return None

# ------------------------------------------------------------
# BLOCCO: INSERIMENTO/MODIFICA PER OGNI PRODOTTO
# ------------------------------------------------------------
st.subheader(f"Lavorazione del {giorno.strftime('%d/%m/%Y')}")

if is_owner():
    for p in prodotti:
        esistente = righe_oggi_by_prodotto.get(p["id"])
        with st.expander(f"{p['nome']}" + (" — già inserito" if esistente else "")):
            with st.form(f"registro_{p['id']}_{giorno}"):
                default_tipo = "bufala_dop" if p["is_dop"] else "bufala"
                tipo_primario = st.selectbox(
                    "Tipo di latte primario messo in lavorazione", list(TIPI_LATTE_LABEL.keys()),
                    format_func=lambda x: TIPI_LATTE_LABEL[x],
                    index=list(TIPI_LATTE_LABEL.keys()).index(esistente["tipo_latte_primario"] if esistente else default_tipo),
                    key=f"tipo_{p['id']}",
                )
                latte_kg = st.number_input(
                    "KG di latte messo in lavorazione", min_value=0.0, step=1.0,
                    value=float(esistente["latte_kg"]) if esistente else 0.0, key=f"latte_{p['id']}",
                )
                produzione_kg = st.number_input(
                    f"KG di {p['nome']} prodotti con questo latte", min_value=0.0, step=1.0,
                    value=float(esistente["produzione_kg"]) if esistente else 0.0, key=f"prod_{p['id']}",
                )
                if latte_kg > 0 and produzione_kg > 0:
                    st.caption(f"Resa calcolata: {produzione_kg / latte_kg * 100:.1f}%")

                st.markdown("**Produzione extra di questo prodotto fatta con latte 'in prestito' da un altro prodotto/resa**")
                altri_prodotti = [pp for pp in prodotti if pp["id"] != p["id"]]
                opzioni_integrazione = ["(nessuna)"] + [pp["nome"] for pp in altri_prodotti]
                default_idx = 0
                if esistente and esistente.get("integrazione_da_prodotto_id"):
                    riferimento_nome = prodotti_by_id.get(esistente["integrazione_da_prodotto_id"], {}).get("nome")
                    if riferimento_nome in opzioni_integrazione:
                        default_idx = opzioni_integrazione.index(riferimento_nome)
                riferimento_nome = st.selectbox(
                    "Prendi la resa da (prodotto dello stesso giorno)", opzioni_integrazione,
                    index=default_idx, key=f"rif_{p['id']}",
                )
                produzione_integrazione = st.number_input(
                    f"KG di {p['nome']} prodotti con quel latte 'in prestito'", min_value=0.0, step=1.0,
                    value=float(esistente["produzione_integrazione_kg"]) if esistente and esistente.get("produzione_integrazione_kg") else 0.0,
                    key=f"integr_{p['id']}",
                )
                if riferimento_nome != "(nessuna)":
                    rif_prodotto = next(pp for pp in altri_prodotti if pp["nome"] == riferimento_nome)
                    resa_rif = resa_di(rif_prodotto["id"])
                    if resa_rif:
                        st.caption(f"Resa di '{riferimento_nome}' oggi: {resa_rif*100:.1f}% -> latte necessario per l'integrazione: {produzione_integrazione / resa_rif:.1f} kg")
                    else:
                        st.caption(f"⚠️ '{riferimento_nome}' non ha ancora una resa calcolata per oggi (inseriscilo prima).")

                note = st.text_input("Note (facoltativo)", value=esistente.get("note") or "" if esistente else "", key=f"note_{p['id']}")

                if st.form_submit_button("Salva"):
                    rif_id = None
                    if riferimento_nome != "(nessuna)":
                        rif_id = next(pp["id"] for pp in altri_prodotti if pp["nome"] == riferimento_nome)
                    client.table("registro").upsert({
                        "caseificio_id": caseificio_id,
                        "prodotto_id": p["id"],
                        "data": str(giorno),
                        "tipo_latte_primario": tipo_primario,
                        "latte_kg": latte_kg,
                        "produzione_kg": produzione_kg,
                        "produzione_integrazione_kg": produzione_integrazione if produzione_integrazione > 0 else None,
                        "integrazione_da_prodotto_id": rif_id,
                        "note": note or None,
                    }, on_conflict="prodotto_id,data").execute()
                    st.success("Salvato.")
                    st.rerun()

st.divider()

# ------------------------------------------------------------
# BLOCCO: RIEPILOGO LAVORAZIONE DEL GIORNO
# ------------------------------------------------------------
st.subheader("Riepilogo lavorazione del giorno")
if righe_oggi:
    riepilogo = []
    for r in righe_oggi:
        nome = prodotti_by_id.get(r["prodotto_id"], {}).get("nome", "?")
        resa = (float(r["produzione_kg"]) / float(r["latte_kg"]) * 100) if r.get("latte_kg") else 0
        riga = {
            "Prodotto": nome, "Latte primario": TIPI_LATTE_LABEL.get(r["tipo_latte_primario"], r["tipo_latte_primario"]),
            "KG latte": r["latte_kg"], "KG prodotti": r["produzione_kg"], "Resa %": round(resa, 1),
        }
        if r.get("produzione_integrazione_kg"):
            rif_nome = prodotti_by_id.get(r.get("integrazione_da_prodotto_id"), {}).get("nome", "?")
            riga["Integrazione"] = f"{r['produzione_integrazione_kg']} kg da resa di '{rif_nome}'"
        riepilogo.append(riga)
    st.table(riepilogo)
else:
    st.write("Nessuna lavorazione ancora registrata per questo giorno.")

st.divider()

# ------------------------------------------------------------
# BLOCCO: GIACENZE LATTE (STORICO COMPLETO, NON SOLO IL PERIODO)
# ------------------------------------------------------------
st.subheader("❄️ Giacenze latte refrigerato")
st.caption("Calcolate su tutta la storia del caseificio: giacenza = giacenza precedente + raccolto - lavorato. L'avviso 60 ore per il DOP è una stima approssimata (non conosciamo l'orario esatto di ogni consegna).")

conferitori_tutti = (
    client.table("conferitori")
    .select("id, conferitori_tipi_latte(tipo_latte)")
    .eq("caseificio_id", caseificio_id)
    .execute()
    .data
)
tipo_per_conferitore = {}
for c in conferitori_tutti:
    tipi = [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])]
    tipo_per_conferitore[c["id"]] = tipi

conferimenti_tutti = (
    client.table("conferimenti")
    .select("*")
    .in_("conferitore_id", [c["id"] for c in conferitori_tutti])
    .lte("data", str(periodo_fine))
    .execute()
    .data
) if conferitori_tutti else []

movimenti_tutti = (
    client.table("movimenti_congelato")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)

registro_tutti = (
    client.table("registro")
    .select("*")
    .eq("caseificio_id", caseificio_id)
    .lte("data", str(periodo_fine))
    .execute()
    .data
)

raccolto = {}
for cf in conferimenti_tutti:
    tipi = tipo_per_conferitore.get(cf["conferitore_id"], [])
    kg = float(cf.get("kg") or 0)
    if kg <= 0:
        continue
    for t in tipi:
        if t in ("bufala_dop", "bufala", "vaccino"):
            raccolto[(t, cf["data"])] = raccolto.get((t, cf["data"]), 0) + kg

for m in movimenti_tutti:
    if m["tipo"] == "scongelamento":
        raccolto[("bufala", m["data"])] = raccolto.get(("bufala", m["data"]), 0) + float(m["kg"])

lavorato = {}
registro_by_prodotto_data = {(r["prodotto_id"], r["data"]): r for r in registro_tutti}
for r in registro_tutti:
    lavorato[(r["tipo_latte_primario"], r["data"])] = lavorato.get((r["tipo_latte_primario"], r["data"]), 0) + float(r["latte_kg"] or 0)
    if r.get("produzione_integrazione_kg") and r.get("integrazione_da_prodotto_id"):
        rif = registro_by_prodotto_data.get((r["integrazione_da_prodotto_id"], r["data"]))
        if rif and float(rif.get("latte_kg") or 0) > 0:
            resa_rif = float(rif["produzione_kg"]) / float(rif["latte_kg"])
            if resa_rif > 0:
                latte_integr = float(r["produzione_integrazione_kg"]) / resa_rif
                lavorato[(rif["tipo_latte_primario"], r["data"])] = lavorato.get((rif["tipo_latte_primario"], r["data"]), 0) + latte_integr

tutte_le_date = sorted(set([d for (_, d) in raccolto.keys()] + [d for (_, d) in lavorato.keys()] + [str(d) for d in date_periodo]))

giacenza_per_tipo = {"bufala_dop": 0.0, "bufala": 0.0, "vaccino": 0.0}
eta_giacenza_dop = None
storico_giacenza = []

for d in tutte_le_date:
    for tipo in giacenza_per_tipo:
        entrata = raccolto.get((tipo, d), 0)
        uscita = lavorato.get((tipo, d), 0)
        if tipo == "bufala_dop":
            if giacenza_per_tipo[tipo] <= 0 and entrata > 0:
                eta_giacenza_dop = d
            if uscita >= giacenza_per_tipo[tipo] + entrata:
                eta_giacenza_dop = None
        giacenza_per_tipo[tipo] = giacenza_per_tipo[tipo] + entrata - uscita
    if d >= str(periodo_inizio):
        storico_giacenza.append({
            "Data": _dt.date.fromisoformat(d).strftime("%d/%m/%Y"),
            "Bufala DOP": round(giacenza_per_tipo["bufala_dop"], 1),
            "Bufala": round(giacenza_per_tipo["bufala"], 1),
            "Vaccino": round(giacenza_per_tipo["vaccino"], 1),
        })

if storico_giacenza:
    st.table(storico_giacenza)

for tipo in ["bufala_dop", "bufala", "vaccino"]:
    if giacenza_per_tipo[tipo] < 0:
        st.error(f"⚠️ Giacenza {TIPI_LATTE_LABEL[tipo]} NEGATIVA: {round(giacenza_per_tipo[tipo],1)} kg — hai lavorato più latte di quanto disponibile.")

if eta_giacenza_dop:
    ore_trascorse = (giorno - _dt.date.fromisoformat(eta_giacenza_dop)).days * 24
    if ore_trascorse > 60:
        st.error(f"⚠️ Il latte DOP più vecchio in giacenza risulta raccolto/conferito il {eta_giacenza_dop} — sono passate più di 60 ore (stima)!")
    elif ore_trascorse > 48:
        st.warning(f"⏰ Il latte DOP più vecchio in giacenza è del {eta_giacenza_dop} — attenzione al limite delle 60 ore (stima).")
