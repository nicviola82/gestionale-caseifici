# ============================================================
# MODULO: REGISTRO_CALC
# Logica di calcolo condivisa del Registro (giacenza, trasformato,
# consumo extra DOP) - estratta da 6_Registro.py cosi' sia la
# pagina Registro sia i fogli stampabili (MBC/RBC/tr) e il Siero
# usano SEMPRE la stessa funzione, senza doppioni che rischiano
# di disallinearsi.
#
# CORREZIONE BUG STORICO: il consumo extra DOP (quota dei prodotti
# derivati - es. Mozzarella di latte di Bufala, senza lattosio -
# fatta con latte DOP) va calcolato su TUTTA LA STORIA del
# caseificio, non solo sul periodo attualmente visualizzato in
# pagina - altrimenti la giacenza di apertura di un nuovo periodo
# risulta sbagliata. Nella versione precedente del Registro questo
# calcolo era limitato a "date_periodo" (il bug segnalato).
#
# NOTA PRESTAZIONI: calcola_stato_completo() ricostruisce tutta la
# storia (raccolto/trasformato/venduto/congelato/consumo extra) ad
# ogni chiamata - stesso limite gia' segnalato per la giacenza del
# Siero. Da ottimizzare in seguito (es. salvando un saldo
# giornaliero) quando la mole di dati storici crescerà.
# ============================================================

TIPI_GIAC = ["bufala_dop", "bufala", "vaccino", "semilavorato_bufala", "semilavorato_vaccino"]


def _tipo_per_conferitore(client, caseificio_id):
    conferitori = (
        client.table("conferitori")
        .select("id, conferitori_tipi_latte(tipo_latte)")
        .eq("caseificio_id", caseificio_id)
        .execute()
        .data
    )
    return {c["id"]: [t["tipo_latte"] for t in c.get("conferitori_tipi_latte", [])] for c in conferitori}


def _prodotti_e_primario_dop(client, caseificio_id):
    prodotti = (
        client.table("prodotti")
        .select("*")
        .eq("caseificio_id", caseificio_id)
        .eq("attivo", True)
        .eq("mostra_in_produzioni", True)
        .execute()
        .data
    )
    primario = next((p for p in prodotti if p["is_dop"] and p.get("stabilisce_resa")), None)
    return prodotti, primario


def _prodotti_dop_altri_e_declassati(prodotti, prodotto_primario_dop):
    def e_mista(p): return "mista" in p["nome"].lower()
    def e_vaccina(p): return "vaccin" in p["nome"].lower() and "mista" not in p["nome"].lower()
    def e_congelato(p): return "congelat" in p["nome"].lower()
    def e_cagliata(p): return "cagliata" in p["nome"].lower() or "semilav" in p["nome"].lower()
    def e_declassata(p):
        return (not p["is_dop"] and not e_mista(p) and not e_vaccina(p)
                and not e_congelato(p) and not e_cagliata(p) and p is not prodotto_primario_dop)
    dop_altri = [p for p in prodotti if p["is_dop"] and p is not prodotto_primario_dop]
    declassati = [p for p in prodotti if e_declassata(p)]
    mista = [p for p in prodotti if e_mista(p)]
    return dop_altri, declassati, mista


def calcola_stato_completo(client, caseificio_id, fino_a_data):
    """Ricalcola raccolto/trasformato/venduto/congelato/consumo_extra_dop/giacenza
    su TUTTA LA STORIA fino a fino_a_data (inclusa)."""

    tipo_per_conferitore = _tipo_per_conferitore(client, caseificio_id)
    conferitore_ids = list(tipo_per_conferitore.keys())

    conferimenti = (
        client.table("conferimenti").select("*").in_("conferitore_id", conferitore_ids)
        .lte("data", str(fino_a_data)).execute().data
    ) if conferitore_ids else []

    movimenti = (
        client.table("movimenti_congelato").select("*").eq("caseificio_id", caseificio_id)
        .lte("data", str(fino_a_data)).execute().data
    )

    trasformato_storia = (
        client.table("trasformato").select("*").eq("caseificio_id", caseificio_id)
        .lte("data", str(fino_a_data)).execute().data
    )
    trasformato_map = {(t["tipo_latte"], t["data"]): float(t["kg"] or 0) for t in trasformato_storia}

    venduto_storia = (
        client.table("latte_venduto").select("*").eq("caseificio_id", caseificio_id)
        .lte("data", str(fino_a_data)).execute().data
    )
    venduto_map = {}
    for v in venduto_storia:
        venduto_map[(v["tipo_latte"], v["data"])] = venduto_map.get((v["tipo_latte"], v["data"]), 0) + float(v["kg"] or 0)

    raccolto = {}
    congelato_map = {}
    for cf in conferimenti:
        tipi = tipo_per_conferitore.get(cf["conferitore_id"], [])
        kg = float(cf.get("kg") or 0)
        if kg <= 0:
            continue
        for t in tipi:
            if t in TIPI_GIAC:
                raccolto[(t, cf["data"])] = raccolto.get((t, cf["data"]), 0) + kg
    for m in movimenti:
        if m["tipo"] == "scongelamento":
            raccolto[("bufala", m["data"])] = raccolto.get(("bufala", m["data"]), 0) + float(m["kg"])
        elif m["tipo"] == "congelamento":
            orig = m.get("origine") or "bufala"
            congelato_map[(orig, m["data"])] = congelato_map.get((orig, m["data"]), 0) + float(m["kg"])

    prodotti, prodotto_primario_dop = _prodotti_e_primario_dop(client, caseificio_id)
    prodotti_dop_altri, prodotti_declassati, prodotti_mista = _prodotti_dop_altri_e_declassati(prodotti, prodotto_primario_dop)
    prodotto_ids = [p["id"] for p in prodotti]

    produzioni_storia = (
        client.table("produzioni").select("*").in_("prodotto_id", prodotto_ids)
        .lte("data", str(fino_a_data)).execute().data
    ) if prodotto_ids else []
    prod_map = {(e["prodotto_id"], e["data"]): e for e in produzioni_storia}

    origini_m = {}
    ids_produzioni = [r["id"] for r in produzioni_storia]
    if ids_produzioni:
        for o in client.table("produzione_origine").select("*").in_("produzione_id", ids_produzioni).execute().data:
            origini_m.setdefault(o["produzione_id"], {})[o["origine"]] = o

    def resa_dop_giorno(ds):
        if not prodotto_primario_dop:
            return None
        rec = prod_map.get((prodotto_primario_dop["id"], ds))
        prod = float(rec["kg_totale"]) if rec else 0
        trasf = trasformato_map.get(("bufala_dop", ds), 0)
        return (prod / trasf) if trasf > 0 else None

    # CORREZIONE: su tutta la storia disponibile in prod_map, non solo sul periodo aperto in pagina
    # ATTENZIONE: la Ricotta DOP va esclusa - si fa dal siero, non consuma latte
    # bufala_dop secondo la resa MBC (vedi stessa nota in pages/6_Registro.py)
    consumo_extra_dop = {}
    prodotti_dop_altri_no_ricotta = [p for p in prodotti_dop_altri if "ricotta" not in p["nome"].lower()]
    for p in prodotti_dop_altri_no_ricotta + prodotti_declassati:
        for (prodotto_id, ds), rec in prod_map.items():
            if prodotto_id != p["id"]:
                continue
            tot = float(rec.get("kg_totale") or 0)
            if tot <= 0:
                continue
            ov = origini_m.get(rec["id"], {}).get("non_dop")
            kg_nondop = float(ov["kg"]) if ov and ov.get("kg") else 0.0
            kg_dop = tot - kg_nondop
            if kg_dop > 0:
                r = resa_dop_giorno(ds)
                if r and r > 0:
                    consumo_extra_dop[("bufala_dop", ds)] = consumo_extra_dop.get(("bufala_dop", ds), 0) + kg_dop / r

    # MOZZARELLA MISTA -> consumo latte bufala/vaccino (aggiunto 27/08, per
    # allineare questo modulo condiviso a pages/6_Registro.py - stessa logica:
    # il kg di ciascun tipo di latte usato nella mista si legge dalle righe
    # produzione_origine con origine 'bufala'/'vaccino' della produzione mista
    # di quel giorno, editate dall'utente nel Registro).
    consumo_mista_buf = {}
    consumo_mista_vacc = {}
    for p in prodotti_mista:
        for (prodotto_id, ds), rec in prod_map.items():
            if prodotto_id != p["id"]:
                continue
            ov_b = origini_m.get(rec["id"], {}).get("bufala")
            kg_b = float(ov_b["kg"]) if ov_b and ov_b.get("kg") else 0.0
            if kg_b > 0:
                consumo_mista_buf[ds] = consumo_mista_buf.get(ds, 0) + kg_b
            ov_v = origini_m.get(rec["id"], {}).get("vaccino")
            kg_v = float(ov_v["kg"]) if ov_v and ov_v.get("kg") else 0.0
            if kg_v > 0:
                consumo_mista_vacc[ds] = consumo_mista_vacc.get(ds, 0) + kg_v

    # RICOTTA (DOP e NON-DOP) -> consumo latte bufala (solo se impostata una
    # percentuale in Impostazioni Fisse) - aggiunto 27/08, stessa logica di
    # pages/6_Registro.py: di regola la Ricotta si fa dal siero e non consuma
    # latte; se è impostata una % di latte di bufala aggiunto, quella quota va
    # scalata dal bucket "bufala" non-DOP (mai da bufala_dop).
    def _storico_percentuale(campo):
        return (
            client.table("impostazioni_registro")
            .select("data_da, valore")
            .eq("caseificio_id", caseificio_id)
            .eq("campo", campo)
            .order("data_da")
            .execute()
            .data
        )

    def _percentuale_alla_data(storico, data_str):
        valore = 0.0
        for r in storico:
            if r["data_da"] <= data_str:
                try:
                    valore = float(r["valore"])
                except (TypeError, ValueError):
                    valore = 0.0
            else:
                break
        return valore

    perc_bufala_rbc_storico = _storico_percentuale("perc_latte_bufala_rbc")
    perc_bufala_ricotta_nondop_storico = _storico_percentuale("perc_latte_bufala_ricotta_nondop")

    ricotta_dop_prodotti = [p for p in prodotti if p["is_dop"] and "ricotta di bufala campana dop" in p["nome"].lower()]
    ricotta_nondop_prodotti = [p for p in prodotti if not p["is_dop"] and "ricotta" in p["nome"].lower()]

    def _kg_prodotto_per_giorno(prodotti_list):
        out = {}
        for p in prodotti_list:
            for (prodotto_id, ds), rec in prod_map.items():
                if prodotto_id != p["id"]:
                    continue
                out[ds] = out.get(ds, 0) + float(rec.get("kg_totale") or 0)
        return out

    def _resa_media(prodotti_list):
        rese = [float(p["resa_automatica_percent"]) for p in prodotti_list if p.get("resa_automatica_percent")]
        return (sum(rese) / len(rese)) if rese else None

    ricotta_dop_per_giorno = _kg_prodotto_per_giorno(ricotta_dop_prodotti)
    ricotta_nondop_per_giorno = _kg_prodotto_per_giorno(ricotta_nondop_prodotti)
    resa_ricotta_dop = _resa_media(ricotta_dop_prodotti)
    resa_ricotta_nondop = _resa_media(ricotta_nondop_prodotti)

    ricotta_bufala_map = {}
    date_ricotta = sorted(set(list(ricotta_dop_per_giorno.keys()) + list(ricotta_nondop_per_giorno.keys())))
    for ds in date_ricotta:
        tot_oggi = 0.0
        if resa_ricotta_dop:
            perc = _percentuale_alla_data(perc_bufala_rbc_storico, ds)
            kg_oggi = ricotta_dop_per_giorno.get(ds, 0)
            if perc > 0 and kg_oggi > 0:
                tot_oggi += perc / 100 * (kg_oggi / (resa_ricotta_dop / 100))
        if resa_ricotta_nondop:
            perc = _percentuale_alla_data(perc_bufala_ricotta_nondop_storico, ds)
            kg_oggi = ricotta_nondop_per_giorno.get(ds, 0)
            if perc > 0 and kg_oggi > 0:
                tot_oggi += perc / 100 * (kg_oggi / (resa_ricotta_nondop / 100))
        if tot_oggi > 0:
            ricotta_bufala_map[ds] = round(tot_oggi)

    tutte_le_date = sorted(set(
        [d for (_, d) in raccolto.keys()] + [d for (_, d) in trasformato_map.keys()]
        + [d for (_, d) in venduto_map.keys()] + [d for (_, d) in consumo_extra_dop.keys()]
        + list(consumo_mista_buf.keys()) + list(consumo_mista_vacc.keys()) + list(ricotta_bufala_map.keys())
    ))

    giacenza_per_tipo = {t: 0.0 for t in TIPI_GIAC}
    giacenza_apertura_per_giorno = {}
    for d in tutte_le_date:
        for t in TIPI_GIAC:
            giacenza_apertura_per_giorno[(t, d)] = giacenza_per_tipo[t]
            entrata = raccolto.get((t, d), 0)
            uscita = (trasformato_map.get((t, d), 0)
                      + consumo_extra_dop.get((t, d), 0)
                      + venduto_map.get((t, d), 0)
                      + congelato_map.get((t if t in ("bufala_dop", "bufala") else "bufala", d), 0)
                      * (1 if t in ("bufala_dop", "bufala") else 0)
                      + (ricotta_bufala_map.get(d, 0) if t == "bufala" else 0)
                      + (consumo_mista_buf.get(d, 0) if t == "bufala" else 0)
                      + (consumo_mista_vacc.get(d, 0) if t == "vaccino" else 0))
            giacenza_per_tipo[t] = giacenza_per_tipo[t] + entrata - uscita

    return {
        "raccolto": raccolto,
        "trasformato_map": trasformato_map,
        "venduto_map": venduto_map,
        "congelato_map": congelato_map,
        "consumo_extra_dop": consumo_extra_dop,
        "consumo_mista_buf": consumo_mista_buf,
        "consumo_mista_vacc": consumo_mista_vacc,
        "ricotta_bufala_map": ricotta_bufala_map,
        "giacenza_apertura_per_giorno": giacenza_apertura_per_giorno,
        "prodotto_primario_dop": prodotto_primario_dop,
        "prod_map": prod_map,
    }


def giacenza_apertura(client, caseificio_id, tipo_latte, data):
    stato = calcola_stato_completo(client, caseificio_id, data)
    return stato["giacenza_apertura_per_giorno"].get((tipo_latte, str(data)), 0.0)


def giacenza_chiusura(client, caseificio_id, tipo_latte, data):
    stato = calcola_stato_completo(client, caseificio_id, data)
    ds = str(data)
    apertura_val = stato["giacenza_apertura_per_giorno"].get((tipo_latte, ds), 0.0)
    entrata = stato["raccolto"].get((tipo_latte, ds), 0)
    uscita = (stato["trasformato_map"].get((tipo_latte, ds), 0)
              + stato["consumo_extra_dop"].get((tipo_latte, ds), 0)
              + stato["venduto_map"].get((tipo_latte, ds), 0)
              + stato["congelato_map"].get((tipo_latte if tipo_latte in ("bufala_dop", "bufala") else "bufala", ds), 0)
              * (1 if tipo_latte in ("bufala_dop", "bufala") else 0)
              + (stato["ricotta_bufala_map"].get(ds, 0) if tipo_latte == "bufala" else 0)
              + (stato["consumo_mista_buf"].get(ds, 0) if tipo_latte == "bufala" else 0)
              + (stato["consumo_mista_vacc"].get(ds, 0) if tipo_latte == "vaccino" else 0))
    return apertura_val + entrata - uscita


def trasformato(client, caseificio_id, tipo_latte, data):
    rec = (
        client.table("trasformato")
        .select("kg")
        .eq("caseificio_id", caseificio_id)
        .eq("tipo_latte", tipo_latte)
        .eq("data", str(data))
        .execute()
        .data
    )
    return float(rec[0]["kg"]) if rec else 0.0


def trasformato_totale(client, caseificio_id, data):
    return sum(trasformato(client, caseificio_id, t, data) for t in TIPI_GIAC)


def extra_dop_consumato(client, caseificio_id, data):
    stato = calcola_stato_completo(client, caseificio_id, data)
    return stato["consumo_extra_dop"].get(("bufala_dop", str(data)), 0.0)


def mista_consumato(client, caseificio_id, tipo, data):
    """kg di latte bufala/vaccino usati nella Mozzarella Mista quel giorno
    (colonne Buf/Vac editabili in Registro). tipo: 'bufala' o 'vaccino'."""
    stato = calcola_stato_completo(client, caseificio_id, data)
    ds = str(data)
    chiave = "consumo_mista_buf" if tipo == "bufala" else "consumo_mista_vacc"
    return stato[chiave].get(ds, 0.0)


def ricotta_bufala_consumato(client, caseificio_id, data):
    """kg di latte bufala (non-DOP) usati per la Ricotta (DOP+non-DOP) quel giorno,
    solo se e' impostata una percentuale in Impostazioni Fisse."""
    stato = calcola_stato_completo(client, caseificio_id, data)
    return stato["ricotta_bufala_map"].get(str(data), 0.0)
