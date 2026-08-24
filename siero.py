# ============================================================
# MODULO: SIERO (calcoli)
# Principio: niente si crea e nulla si distrugge, tutto si
# trasforma -> siero prodotto = latte trasformato - prodotto
# ottenuto, calcolato sui valori REALMENTE dichiarati (non su
# una percentuale fissa).
#
# Due pool separati e indipendenti:
#   - Siero DOP: usato per la Ricotta di Bufala Campana DOP
#     (consumo = ricotta DOP prodotta / % resa, sempre inserita
#     a mano). Giacenza cumulativa nel tempo, storia completa.
#   - Siero TOTALE (tutto il latte, non solo DOP): usato per lo
#     smaltimento, un unico numero, poi ripartito manualmente
#     dall'utente tra una o piu' aziende.
#
# IMPORTANTE SULLE PRESTAZIONI: la giacenza cumulativa NON cicla
# giorno per giorno interrogando il database ad ogni iterazione
# (avrebbe fatto migliaia di chiamate di rete e mandato in errore
# Supabase/httpx) - fa UNA query in blocco per tutta la storia
# disponibile, poi somma i risultati in memoria.
# ============================================================
import datetime as _dt

import registro_calc


# ------------------------------------------------------------
# BLOCCO: DATI DAL REGISTRO (per il "giorno" mostrato in pagina)
# ------------------------------------------------------------
def get_trasformato_dop_giorno(client, caseificio_id, data_giorno):
    return registro_calc.trasformato(client, caseificio_id, "bufala_dop", data_giorno)


def get_trasformato_totale_giorno(client, caseificio_id, data_giorno):
    return registro_calc.trasformato_totale(client, caseificio_id, data_giorno)


# ------------------------------------------------------------
# BLOCCO: DATI DA PRODUZIONI - query singola (per il "giorno")
# ------------------------------------------------------------
def _kg_prodotto_giorno(client, prodotto_id, data_giorno):
    rec = (
        client.table("produzioni")
        .select("*")
        .eq("prodotto_id", prodotto_id)
        .eq("data", str(data_giorno))
        .execute()
        .data
    )
    return float(rec[0]["kg_totale"]) if rec and rec[0].get("kg_totale") else 0.0


def _trova_prodotto(client, caseificio_id, nome_contiene, solo_dop=None):
    prodotti = (
        client.table("prodotti").select("*").eq("caseificio_id", caseificio_id).eq("attivo", True).execute().data
    )
    match = [p for p in prodotti if nome_contiene.lower() in p["nome"].lower()]
    if solo_dop is not None:
        match = [p for p in match if p["is_dop"] == solo_dop]
    return match[0] if match else None


def get_mozzarella_dop_giorno(client, caseificio_id, data_giorno):
    prodotto = _trova_prodotto(client, caseificio_id, "Mozzarella di Bufala Campana DOP", solo_dop=True)
    if not prodotto:
        return 0.0
    return _kg_prodotto_giorno(client, prodotto["id"], data_giorno)


def get_ricotta_dop_giorno(client, caseificio_id, data_giorno):
    prodotto = _trova_prodotto(client, caseificio_id, "Ricotta di Bufala Campana DOP", solo_dop=True)
    if not prodotto:
        return 0.0, None
    return _kg_prodotto_giorno(client, prodotto["id"], data_giorno), prodotto


def get_resa_ricotta_dop(client, caseificio_id):
    prodotto = _trova_prodotto(client, caseificio_id, "Ricotta di Bufala Campana DOP", solo_dop=True)
    if not prodotto or not prodotto.get("resa_automatica_percent"):
        return None
    return float(prodotto["resa_automatica_percent"])


# ------------------------------------------------------------
# BLOCCO: SIERO PRODOTTO NEL GIORNO SELEZIONATO (mass balance reale)
# ------------------------------------------------------------
def siero_dop_prodotto_giorno(client, caseificio_id, data_giorno):
    trasformato_dop = get_trasformato_dop_giorno(client, caseificio_id, data_giorno)
    mozzarella_dop = get_mozzarella_dop_giorno(client, caseificio_id, data_giorno)
    return max(0.0, trasformato_dop - mozzarella_dop)


def siero_totale_prodotto_giorno(client, caseificio_id, data_giorno):
    trasformato_tot = get_trasformato_totale_giorno(client, caseificio_id, data_giorno)
    # TODO: sottrarre tutti i prodotti (non solo mozzarella DOP) ottenuti da tutto il latte,
    # quando la mappatura prodotto->tipo di latte sara' definita nel Registro riscritto.
    return max(0.0, trasformato_tot)


def siero_utilizzato_ricotta_dop_giorno(client, caseificio_id, data_giorno):
    ricotta_dop, prodotto = get_ricotta_dop_giorno(client, caseificio_id, data_giorno)
    if ricotta_dop <= 0:
        return 0.0, None
    resa = get_resa_ricotta_dop(client, caseificio_id)
    if not resa:
        return 0.0, "Resa % non impostata per la Ricotta di Bufala Campana DOP (vai su Prodotti)"
    return ricotta_dop / (resa / 100), None


# ------------------------------------------------------------
# BLOCCO: VERSIONI "PERIODO" (sommano più giorni con SOLO query in blocco -
# mai una query ripetuta per ogni singolo giorno del periodo, stesso
# principio della giacenza cumulativa sotto). Usate dalla pagina Siero per
# mostrare un riepilogo del periodo selezionato invece del solo giorno.
# ------------------------------------------------------------
def _date_nel_periodo(periodo_inizio, periodo_fine):
    d = periodo_inizio
    while d <= periodo_fine:
        yield d
        d += _dt.timedelta(days=1)


def siero_dop_prodotto_periodo(client, caseificio_id, periodo_inizio, periodo_fine):
    trasf_dop = _bulk_trasformato(client, caseificio_id, periodo_fine, tipo_latte="bufala_dop")
    mozz_map, _ = _bulk_produzione(client, caseificio_id, "Mozzarella di Bufala Campana DOP", True, periodo_fine)
    tot = 0.0
    for d in _date_nel_periodo(periodo_inizio, periodo_fine):
        ds = str(d)
        tot += max(0.0, trasf_dop.get(ds, 0.0) - mozz_map.get(ds, 0.0))
    return tot


def siero_totale_prodotto_periodo(client, caseificio_id, periodo_inizio, periodo_fine):
    trasf_tot = _bulk_trasformato(client, caseificio_id, periodo_fine)
    tot = 0.0
    for d in _date_nel_periodo(periodo_inizio, periodo_fine):
        tot += max(0.0, trasf_tot.get(str(d), 0.0))
    return tot


def siero_utilizzato_ricotta_dop_periodo(client, caseificio_id, periodo_inizio, periodo_fine):
    ricotta_map, prodotto = _bulk_produzione(client, caseificio_id, "Ricotta di Bufala Campana DOP", True, periodo_fine)
    if not prodotto:
        return 0.0, 0.0, None
    resa = get_resa_ricotta_dop(client, caseificio_id)
    ricotta_tot = sum(ricotta_map.get(str(d), 0.0) for d in _date_nel_periodo(periodo_inizio, periodo_fine))
    if ricotta_tot <= 0:
        return 0.0, 0.0, None
    if not resa:
        return ricotta_tot, 0.0, "Resa % non impostata per la Ricotta di Bufala Campana DOP (vai su Prodotti)"
    return ricotta_tot, ricotta_tot / (resa / 100), None


def get_smaltimenti_periodo(client, caseificio_id, periodo_inizio, periodo_fine):
    return (
        client.table("smaltimento_siero")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .gte("data", str(periodo_inizio))
        .lte("data", str(periodo_fine))
        .order("data")
        .execute()
        .data
    )


# ------------------------------------------------------------
# BLOCCO: DATI IN BLOCCO (una query sola per tutta la storia,
# non una per giorno) - usati SOLO per calcolare la giacenza
# cumulativa, mai in un ciclo che rifa' la stessa query ogni volta.
# ------------------------------------------------------------
def _bulk_trasformato(client, caseificio_id, fino_a_data, tipo_latte=None):
    q = (
        client.table("trasformato")
        .select("tipo_latte, data, kg")
        .eq("caseificio_id", caseificio_id)
        .lte("data", str(fino_a_data))
    )
    if tipo_latte:
        q = q.eq("tipo_latte", tipo_latte)
    righe = q.execute().data
    m = {}
    for r in righe:
        m[r["data"]] = m.get(r["data"], 0.0) + float(r["kg"] or 0)
    return m


def _bulk_produzione(client, caseificio_id, nome_contiene, solo_dop, fino_a_data):
    prodotto = _trova_prodotto(client, caseificio_id, nome_contiene, solo_dop)
    if not prodotto:
        return {}, None
    righe = (
        client.table("produzioni")
        .select("data, kg_totale")
        .eq("prodotto_id", prodotto["id"])
        .lte("data", str(fino_a_data))
        .execute()
        .data
    )
    return {r["data"]: float(r["kg_totale"] or 0) for r in righe}, prodotto


# ------------------------------------------------------------
# BLOCCO: GIACENZA SIERO DOP (storia completa, query in blocco)
# ------------------------------------------------------------
def giacenza_siero_dop(client, caseificio_id, alla_data, includi_giorno=False):
    limite = alla_data if includi_giorno else alla_data - _dt.timedelta(days=1)

    trasf_map = _bulk_trasformato(client, caseificio_id, limite, tipo_latte="bufala_dop")
    mozz_map, _ = _bulk_produzione(client, caseificio_id, "Mozzarella di Bufala Campana DOP", True, limite)
    ricotta_map, _ = _bulk_produzione(client, caseificio_id, "Ricotta di Bufala Campana DOP", True, limite)
    resa = get_resa_ricotta_dop(client, caseificio_id)

    date_rilevanti = set(trasf_map) | set(mozz_map) | set(ricotta_map)

    prodotto_tot = 0.0
    utilizzato_tot = 0.0
    for ds in date_rilevanti:
        trasf = trasf_map.get(ds, 0.0)
        mozz = mozz_map.get(ds, 0.0)
        prodotto_tot += max(0.0, trasf - mozz)

        ricotta = ricotta_map.get(ds, 0.0)
        if ricotta > 0 and resa:
            utilizzato_tot += ricotta / (resa / 100)

    return prodotto_tot - utilizzato_tot


# ------------------------------------------------------------
# BLOCCO: SMALTIMENTO (tabella smaltimento_siero - vedi
# migrazione_smaltimento_siero.sql da eseguire su Supabase se non
# ancora fatto - QUESTA TABELLA MANCANTE era la causa dell'errore
# segnalato dall'utente sul foglio Siero, 24/08)
#
# create table smaltimento_siero (
#   id uuid primary key default gen_random_uuid(),
#   caseificio_id uuid references caseifici(id),
#   data date not null,
#   azienda text not null,
#   kg numeric not null,
#   categoria text
# );
# ------------------------------------------------------------
def get_smaltimenti_giorno(client, caseificio_id, data_giorno):
    return (
        client.table("smaltimento_siero")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("data", str(data_giorno))
        .execute()
        .data
    )


def giacenza_siero_totale(client, caseificio_id, alla_data, includi_giorno=False):
    limite = alla_data if includi_giorno else alla_data - _dt.timedelta(days=1)

    trasf_map = _bulk_trasformato(client, caseificio_id, limite)  # tutti i tipi di latte

    smaltimenti = (
        client.table("smaltimento_siero")
        .select("data, kg")
        .eq("caseificio_id", caseificio_id)
        .lte("data", str(limite))
        .execute()
        .data
    )
    smaltito_tot = sum(float(s["kg"] or 0) for s in smaltimenti)
    prodotto_tot = sum(max(0.0, kg) for kg in trasf_map.values())

    return prodotto_tot - smaltito_tot
