# ============================================================
# PAGINA: FOGLI STAMPABILI
# Genera i documenti ufficiali RINA (MBC, RBC, tr) compilati,
# sia per un singolo giorno sia per un intero periodo.
# ============================================================
import streamlit as st
import datetime as _dt
from db import get_client
from auth import login_form, logout_button
from stampa_mbc import genera_mbc, genera_mbc_periodo
from stampa_rbc import genera_rbc, genera_rbc_periodo
from stampa_tr import genera_tr, genera_tr_periodo
from stampa_tr_template import genera_tr_template, genera_tr_template_periodo
from ui_helpers import mostra_header_caseificio

st.set_page_config(page_title="Fogli Stampabili", layout="wide")
if not login_form():
    st.stop()
logout_button()
client = get_client()

st.title("Fogli Stampabili")
mostra_header_caseificio()
st.caption("Genera i documenti ufficiali (MBC, RBC, tr) compilati con i dati del giorno o del periodo scelto.")

caseificio_id = st.session_state.get("caseificio_id")
if not caseificio_id:
    st.info("Seleziona un caseificio dalla pagina principale.")
    st.stop()

modalita = st.radio("Genera per:", ["Un singolo giorno", "Un periodo (più giorni)"], horizontal=True)

st.divider()

# ============================================================
# MODALITA': SINGOLO GIORNO (comportamento originale, invariato)
# ============================================================
if modalita == "Un singolo giorno":
    data_giorno = st.date_input("Giorno da stampare", value=_dt.date.today(), format="DD/MM/YYYY")

    st.divider()

    # ------------------------------------------------------------
    # MBC + RBC nello stesso file (comportamento storico per un singolo giorno)
    # ------------------------------------------------------------
    st.subheader("MBC + RBC insieme - Registri Mozzarella e Ricotta")
    if st.button("📄 Genera MBC + RBC del giorno"):
        output_path = f"Scheda_{data_giorno.strftime('%Y%m%d')}.xlsx"
        genera_mbc(client, caseificio_id, data_giorno, output_path)
        _, avvisi = genera_rbc(client, caseificio_id, data_giorno, output_path)
        for a in avvisi:
            st.warning(f"⚠️ {a}")
        with open(output_path, "rb") as f:
            st.download_button(
                "⬇️ Scarica scheda compilata (MBC + RBC)",
                data=f.read(),
                file_name=output_path,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_mbc_rbc_giorno",
            )
        st.success("MBC e RBC generati.")

    st.divider()

    # ------------------------------------------------------------
    # SOLO MBC o SOLO RBC per un singolo giorno (richiesto: poter stampare un
    # tipo alla volta anche per un giorno solo, non solo per periodo) - riusa
    # le stesse funzioni "periodo" passando lo stesso giorno come inizio e
    # fine: producono un file con UN SOLO tipo di foglio, senza gli altri 2.
    # ------------------------------------------------------------
    col_solo1, col_solo2 = st.columns(2)
    with col_solo1:
        st.subheader("Solo MBC")
        if st.button("📄 Genera solo MBC del giorno"):
            output_path_mbc = f"MBC_{data_giorno.strftime('%Y%m%d')}.xlsx"
            genera_mbc_periodo(client, caseificio_id, data_giorno, data_giorno, output_path_mbc)
            with open(output_path_mbc, "rb") as f:
                st.download_button(
                    "⬇️ Scarica solo MBC",
                    data=f.read(),
                    file_name=output_path_mbc,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_solo_mbc_giorno",
                )
            st.success("MBC generato (solo questo foglio).")
    with col_solo2:
        st.subheader("Solo RBC")
        if st.button("📄 Genera solo RBC del giorno"):
            output_path_rbc = f"RBC_{data_giorno.strftime('%Y%m%d')}.xlsx"
            _, avvisi = genera_rbc_periodo(client, caseificio_id, data_giorno, data_giorno, output_path_rbc)
            for a in avvisi:
                st.warning(f"⚠️ {a}")
            with open(output_path_rbc, "rb") as f:
                st.download_button(
                    "⬇️ Scarica solo RBC",
                    data=f.read(),
                    file_name=output_path_rbc,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_solo_rbc_giorno",
                )
            st.success("RBC generato (solo questo foglio).")

    st.divider()

    # ------------------------------------------------------------
    # tr (righe dinamiche in base ai conferitori attivi) - DUE VERSIONI in prova (29/08):
    # "nuovo metodo" = foglio costruito da zero (nessun template Excel copiato);
    # "vecchio metodo" = basato sul template originale, con le correzioni sui merge fatte
    # finora. Tenute entrambe finche' non si capisce quale funziona meglio in pratica.
    # ------------------------------------------------------------
    st.subheader("tr - Tabellone giornaliero")
    st.caption("Righe: un conferitore attivo compare sempre (anche a 0 kg quel giorno); il blocco CONGELATO compare solo nei giorni con un vero scongelamento; i prodotti finiti mostrano solo quelli realmente fatti nel periodo selezionato.")
    col_nuovo, col_vecchio = st.columns(2)
    with col_nuovo:
        st.caption("🆕 Nuovo metodo (foglio costruito da zero)")
        if st.button("📄 Genera tr - nuovo metodo"):
            output_path_tr = f"tr_nuovo_{data_giorno.strftime('%Y%m%d')}.xlsx"
            genera_tr(client, caseificio_id, data_giorno, output_path_tr)
            with open(output_path_tr, "rb") as f:
                st.download_button(
                    "⬇️ Scarica tr (nuovo metodo)",
                    data=f.read(),
                    file_name=output_path_tr,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_tr_nuovo_giorno",
                )
            st.success("tr (nuovo metodo) generato.")
    with col_vecchio:
        st.caption("📄 Vecchio metodo (basato sul template originale)")
        if st.button("📄 Genera tr - vecchio metodo"):
            output_path_tr2 = f"tr_template_{data_giorno.strftime('%Y%m%d')}.xlsx"
            genera_tr_template(client, caseificio_id, data_giorno, output_path_tr2)
            with open(output_path_tr2, "rb") as f:
                st.download_button(
                    "⬇️ Scarica tr (vecchio metodo)",
                    data=f.read(),
                    file_name=output_path_tr2,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_tr_vecchio_giorno",
                )
            st.success("tr (vecchio metodo) generato.")

# ============================================================
# MODALITA': PERIODO (3 file separati - uno per MBC, uno per RBC, uno per tr,
# ciascuno con un foglio per ogni giorno del periodo)
# ============================================================
else:
    col1, col2 = st.columns(2)
    with col1:
        data_da = st.date_input("Dal giorno", value=_dt.date.today() - _dt.timedelta(days=6), format="DD/MM/YYYY")
    with col2:
        data_a = st.date_input("Al giorno", value=_dt.date.today(), format="DD/MM/YYYY")

    if data_a < data_da:
        st.error("Il giorno finale deve essere uguale o successivo al giorno iniziale.")
        st.stop()

    n_giorni = (data_a - data_da).days + 1
    st.caption(f"Periodo di {n_giorni} giorni. Vengono generati 3 file separati (MBC, RBC, tr), "
               f"ciascuno con un foglio per ogni giorno del periodo.")

    st.divider()

    st.subheader("MBC - Registro Mozzarella")
    if st.button("📄 Genera MBC del periodo"):
        output_path = f"MBC_{data_da.strftime('%Y%m%d')}_{data_a.strftime('%Y%m%d')}.xlsx"
        genera_mbc_periodo(client, caseificio_id, data_da, data_a, output_path)
        with open(output_path, "rb") as f:
            st.download_button(
                "⬇️ Scarica MBC del periodo",
                data=f.read(),
                file_name=output_path,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_mbc_periodo",
            )
        st.success(f"MBC generato: {n_giorni} fogli, uno per giorno.")

    st.divider()

    st.subheader("RBC - Registro Ricotta")
    if st.button("📄 Genera RBC del periodo"):
        output_path = f"RBC_{data_da.strftime('%Y%m%d')}_{data_a.strftime('%Y%m%d')}.xlsx"
        _, avvisi = genera_rbc_periodo(client, caseificio_id, data_da, data_a, output_path)
        for a in avvisi:
            st.warning(f"⚠️ {a}")
        with open(output_path, "rb") as f:
            st.download_button(
                "⬇️ Scarica RBC del periodo",
                data=f.read(),
                file_name=output_path,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_rbc_periodo",
            )
        st.success(f"RBC generato: {n_giorni} fogli, uno per giorno.")

    st.divider()

    st.subheader("tr - Tabellone giornaliero")
    st.caption("Righe: un conferitore attivo compare sempre (anche a 0 kg quel giorno); il blocco CONGELATO compare solo nei giorni con un vero scongelamento; i prodotti finiti mostrano solo quelli realmente fatti nel periodo selezionato.")
    col_nuovo_p, col_vecchio_p = st.columns(2)
    with col_nuovo_p:
        st.caption("🆕 Nuovo metodo (foglio costruito da zero)")
        if st.button("📄 Genera tr del periodo - nuovo metodo"):
            output_path_tr = f"tr_nuovo_{data_da.strftime('%Y%m%d')}_{data_a.strftime('%Y%m%d')}.xlsx"
            genera_tr_periodo(client, caseificio_id, data_da, data_a, output_path_tr)
            with open(output_path_tr, "rb") as f:
                st.download_button(
                    "⬇️ Scarica tr del periodo (nuovo metodo)",
                    data=f.read(),
                    file_name=output_path_tr,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_tr_nuovo_periodo",
                )
            st.success(f"tr (nuovo metodo) generato: {n_giorni} fogli, uno per giorno.")
    with col_vecchio_p:
        st.caption("📄 Vecchio metodo (basato sul template originale)")
        if st.button("📄 Genera tr del periodo - vecchio metodo"):
            output_path_tr2 = f"tr_template_{data_da.strftime('%Y%m%d')}_{data_a.strftime('%Y%m%d')}.xlsx"
            genera_tr_template_periodo(client, caseificio_id, data_da, data_a, output_path_tr2)
            with open(output_path_tr2, "rb") as f:
                st.download_button(
                    "⬇️ Scarica tr del periodo (vecchio metodo)",
                    data=f.read(),
                    file_name=output_path_tr2,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_tr_vecchio_periodo",
                )
            st.success(f"tr (vecchio metodo) generato: {n_giorni} fogli, uno per giorno.")
