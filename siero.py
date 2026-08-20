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
# NOTA: "latte trasformato" per tipo di latte dipende dal
# Registro, che non e' ancora stato ricollegato (verra' rifatto
# in seguito) - le funzioni get_trasformato_* sono placeholder
# TODO, stesso schema usato in stampa_mbc.py.
# ============================================================
import datetime as _dt


# ------------------------------------------------------------
# BLOCCO: DATI DAL REGISTRO (ora collegati a registro_calc.py)
# ------------------------------------------------------------
import registro_calc


def get_trasformato_dop_giorno(client, caseificio_id, data_giorno):
    return registro_calc.trasformato(client, caseificio_id, "bufala_dop", data_giorno)


def get_trasformato_totale_giorno(client, caseificio_id, data_giorno):
    return registro_calc.trasformato_totale(client, caseificio_id, data_giorno)


# ------------------------------------------------------------
# BLOCCO: DATI DA PRODUZIONI (gia' collegabili oggi)
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
    q = client.table("prodotti").select("*").eq("caseificio_id", caseificio_id).eq("attivo", True)
    prodotti = q.execute().data
    match = [p for p in prodotti if nome_contiene.lower() in p["nome"].lower()]
    if solo_dop is not None:
        match = [p for p in match if p["is_dop"] == solo_dop]
    return match[0] if match else None


def get_mozzarella_dop_giorno(client, caseificio_id, data_giorno):
    """Kg di Mozzarella di Bufala Campana DOP prodotti quel giorno (prodotto 'principale')."""
    prodotto = _trova_prodotto(client, caseificio_id, "Mozzarella di Bufala Campana DOP", solo_dop=True)
    if not prodotto:
        return 0.0
    return _kg_prodotto_giorno(client, prodotto["id"], data_giorno)


def get_ricotta_dop_giorno(client, caseificio_id, data_giorno):
    """Kg di Ricotta di Bufala Campana DOP dichiarati quel giorno (sempre inseriti a mano)."""
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
# BLOCCO: SIERO PRODOTTO (mass balance reale)
# ------------------------------------------------------------
def siero_dop_prodotto_giorno(client, caseificio_id, data_giorno):
    trasformato_dop = get_trasformato_dop_giorno(client, caseificio_id, data_giorno)  # TODO Registro
    mozzarella_dop = get_mozzarella_dop_giorno(client, caseificio_id, data_giorno)
    return max(0.0, trasformato_dop - mozzarella_dop)


def siero_totale_prodotto_giorno(client, caseificio_id, data_giorno):
    trasformato_totale = get_trasformato_totale_giorno(client, caseificio_id, data_giorno)  # TODO Registro
    # TODO: sottrarre tutti i prodotti (non solo mozzarella DOP) ottenuti da tutto il latte,
    # quando la mappatura prodotto->tipo di latte sara' definita nel Registro riscritto.
    # Per ora, in assenza del Registro, ritorna 0 come le altre funzioni TODO.
    return max(0.0, trasformato_totale)


# ------------------------------------------------------------
# BLOCCO: SIERO UTILIZZATO PER RICOTTA DOP
# ------------------------------------------------------------
def siero_utilizzato_ricotta_dop_giorno(client, caseificio_id, data_giorno):
    ricotta_dop, prodotto = get_ricotta_dop_giorno(client, caseificio_id, data_giorno)
    if ricotta_dop <= 0:
        return 0.0, None
    resa = get_resa_ricotta_dop(client, caseificio_id)
    if not resa:
        return 0.0, "Resa % non impostata per la Ricotta di Bufala Campana DOP (vai su Prodotti)"
    return ricotta_dop / (resa / 100), None


# ------------------------------------------------------------
# BLOCCO: GIACENZA SIERO DOP (cumulativa su tutta la storia,
# come da lezione imparata col bug del Registro - MAI solo sul
# periodo corrente)
# ------------------------------------------------------------
def giacenza_siero_dop(client, caseificio_id, alla_data, includi_giorno=False):
    """Giacenza siero DOP calcolata su tutta la storia fino a 'alla_data'
    (esclusa, salvo includi_giorno=True)."""
    data_inizio = _dt.date(2000, 1, 1)  # inizio storia: da adattare se serve un limite piu' realistico
    giorni = []
    d = data_inizio
    limite = alla_data if includi_giorno else alla_data - _dt.timedelta(days=1)
    while d <= limite:
        giorni.append(d)
        d += _dt.timedelta(days=1)

    prodotto_tot = sum(siero_dop_prodotto_giorno(client, caseificio_id, g) for g in giorni)
    utilizzato_tot = sum(siero_utilizzato_ricotta_dop_giorno(client, caseificio_id, g)[0] for g in giorni)
    return prodotto_tot - utilizzato_tot


# ------------------------------------------------------------
# BLOCCO: SMALTIMENTO (tabella smaltimento_siero - NUOVA,
# da creare su Supabase)
#
# SQL per crearla:
# create table smaltimento_siero (
#   id bigint generated always as identity primary key,
#   caseificio_id bigint references caseifici(id),
#   data date not null,
#   azienda text not null,
#   kg numeric not null,
#   categoria text  -- es. "categoria 3"
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
    data_inizio = _dt.date(2000, 1, 1)
    giorni = []
    d = data_inizio
    limite = alla_data if includi_giorno else alla_data - _dt.timedelta(days=1)
    while d <= limite:
        giorni.append(d)
        d += _dt.timedelta(days=1)

    prodotto_tot = sum(siero_totale_prodotto_giorno(client, caseificio_id, g) for g in giorni)
    smaltiti = 0.0
    for g in giorni:
        for s in get_smaltimenti_giorno(client, caseificio_id, g):
            smaltiti += float(s["kg"] or 0)
    return prodotto_tot - smaltiti
