"""
data_sources.py — Données réelles, avec amorçage (seed) TradingView par série.

Principe : pour chaque série, si un fichier seed/<nom>.csv existe (export
TradingView : time,open,high,low,close), il sert d'HISTORIQUE de base, et le bot
APPEND une valeur par jour à chaque run. Sans seed, on rapatrie depuis l'API.

  TOTAL     -> seed (CRYPTOCAP:TOTAL) + append CoinGecko (total market cap)
  OTHERS.D  -> seed (CRYPTOCAP:OTHERS.D) + append CoinGecko (dominance % hors top 10)
  ETHBTC    -> seed (optionnel) + append Binance ; sinon Binance complet
  BTC/ETH   -> Binance complet
  OR        -> Stooq complet

⚠ La market cap CoinGecko n'a pas exactement le même univers que CRYPTOCAP de
  TradingView : de légers écarts sont attendus. Source de vérité = alerte Pine.
"""
import io, os, time, requests, pandas as pd

SEED = os.path.join(os.path.dirname(__file__), "seed")
UA = {"User-Agent": "rsps-bot/1.0"}


def binance_daily(symbol, start="2018-01-01"):
    # miroir public de Binance : api.binance.com renvoie 451 depuis les runners US de GitHub
    url = "https://data-api.binance.vision/api/v3/klines"
    ms = int(pd.Timestamp(start).timestamp() * 1000); rows = []
    while True:
        r = requests.get(url, params={"symbol": symbol, "interval": "1d",
                         "startTime": ms, "limit": 1000}, headers=UA, timeout=30)
        r.raise_for_status(); data = r.json()
        if not data: break
        rows += data; ms = data[-1][0] + 86_400_000
        if len(data) < 1000: break
        time.sleep(0.2)
    df = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c", *range(7)])
    df["time"] = pd.to_datetime(df["t"], unit="ms").dt.normalize()
    for a, b in [("o","open"),("h","high"),("l","low"),("c","close")]:
        df[b] = df[a].astype(float)
    return df[["time","open","high","low","close"]].drop_duplicates("time").set_index("time")


def bybit_daily(symbol, start="2024-01-01"):
    """Bougies 1D spot Bybit (repli pour les tokens listés récemment sur Binance, ex. HYPE)."""
    end = int(pd.Timestamp.utcnow().timestamp() * 1000); t0 = int(pd.Timestamp(start).timestamp() * 1000)
    rows = []
    while end > t0:
        r = requests.get("https://api.bybit.com/v5/market/kline", params={"category": "spot", "symbol": symbol,
                         "interval": "D", "end": end, "limit": 1000}, headers=UA, timeout=30).json()
        lst = (r.get("result") or {}).get("list") or []
        if not lst: break
        rows += lst; end = int(lst[-1][0]) - 1                     # Bybit renvoie du plus récent au plus ancien
        if len(lst) < 1000: break
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "v", "q"]).astype(float)
    df["time"] = pd.to_datetime(df["t"], unit="ms").dt.normalize()
    df = df[df["time"] >= pd.Timestamp(start)]
    return df[["time", "open", "high", "low", "close"]].drop_duplicates("time").set_index("time").sort_index()


def kucoin_daily(symbol, start="2024-01-01"):
    """Bougies 1D KuCoin (accessible depuis les serveurs US de GitHub, contrairement à Bybit)."""
    pair = symbol.replace("USDT", "-USDT")
    end = int(pd.Timestamp.utcnow().timestamp()); t0 = int(pd.Timestamp(start).timestamp())
    rows = []
    while end > t0:
        r = requests.get("https://api.kucoin.com/api/v1/market/candles", params={"type": "1day", "symbol": pair,
                         "startAt": t0, "endAt": end}, headers=UA, timeout=30).json()
        lst = r.get("data") or []
        if not lst: break
        rows += lst; end = int(lst[-1][0]) - 1                     # du plus récent au plus ancien
        if len(lst) < 1500: break
    df = pd.DataFrame([[x[0], x[1], x[3], x[4], x[2]] for x in rows], columns=["t", "open", "high", "low", "close"]).astype(float)
    df["time"] = pd.to_datetime(df["t"], unit="s").dt.normalize()
    return df[["time", "open", "high", "low", "close"]].drop_duplicates("time").set_index("time").sort_index()


def token_daily(symbol, start="2024-01-01"):
    """Binance ; si l'historique est court (listing récent), KuCoin puis Bybit."""
    best = binance_daily(symbol, start=start)
    if len(best) >= 400:
        return best
    for fn in (kucoin_daily, bybit_daily):
        try:
            alt = fn(symbol, start=start)
            if len(alt) > len(best):
                best = alt
        except Exception:
            pass
    return best


def yahoo_gold():
    """Or (future COMEX GC=F) via Yahoo Finance — historique depuis 2000."""
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
                     params={"range": "max", "interval": "1d"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status(); res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open","high","low","close")},
                      index=pd.to_datetime(res["timestamp"], unit="s").normalize())
    df.index.name = "time"
    df = df.dropna(subset=["close"])
    return df[~df.index.duplicated(keep="last")]


def get_gold():
    """Yahoo, puis Binance PAXG (or tokenisé, depuis 2020) ; None si tout échoue.
    (Stooq, l'ancienne source, renvoie désormais une page anti-bot au lieu du CSV.)"""
    for name, fn in (("Yahoo", yahoo_gold), ("Binance PAXG", lambda: binance_daily("PAXGUSDT"))):
        try:
            return fn()
        except Exception as e:
            print(f"[warn] or via {name} indispo ({e})")
    return None


def _cg(path, **params):
    """GET CoinGecko avec retries : l'API gratuite renvoie souvent 429 (surtout
    depuis les IP partagées de GitHub Actions)."""
    for i in range(4):
        r = requests.get(f"https://api.coingecko.com/api/v3/{path}", params=params, headers=UA, timeout=30)
        if r.status_code != 429:
            r.raise_for_status(); return r.json()
        time.sleep(15 * (i + 1))
    r.raise_for_status()


def paprika_total_dominance():
    """Repli CoinPaprika (gratuit, sans clé) : (market cap totale, dominance % hors top 10)."""
    g = requests.get("https://api.coinpaprika.com/v1/global", headers=UA, timeout=30).json()
    total = float(g["market_cap_usd"])
    rows = requests.get("https://api.coinpaprika.com/v1/tickers", params={"quotes": "USD"},
                        headers=UA, timeout=60).json()
    top10 = sum(sorted((r["quotes"]["USD"].get("market_cap") or 0 for r in rows), reverse=True)[:10])
    return total, (total - top10) / total * 100.0


def total_dominance():
    """CoinGecko (source d'origine), sinon CoinPaprika — CoinGecko renvoie 403 sans clé depuis 09/2026."""
    try:
        return coingecko_total_dominance()
    except Exception as e:
        print(f"[warn] CoinGecko indispo ({e}) -> CoinPaprika")
        return paprika_total_dominance()


def coingecko_total_dominance():
    """(total market cap USD, dominance % des 'others' hors top 10)."""
    g = _cg("global")["data"]
    total = float(g["total_market_cap"]["usd"])
    mk = _cg("coins/markets", vs_currency="usd", order="market_cap_desc", per_page=10, page=1)
    top10 = sum(c["market_cap"] for c in mk if c.get("market_cap"))
    others_dom = (total - top10) / total * 100.0
    return total, others_dom


def _load_seed(name):
    p = os.path.join(SEED, name)
    if not os.path.exists(p): return None
    df = pd.read_csv(p, parse_dates=["time"]).set_index("time")
    df.index = df.index.normalize()
    return df[["open","high","low","close"]]


def _append(df, day, value):
    day = pd.Timestamp(day).normalize()
    row = pd.DataFrame({"open":value,"high":value,"low":value,"close":value}, index=[day])
    if df is None: return row
    return pd.concat([df[~df.index.isin([day])], row]).sort_index()


def _persist(name, day, value):
    """Écrit le point live du jour dans seed/<name> pour que l'historique s'accumule
    d'un run à l'autre (le workflow committe seed/). Seuls les vrais points sont
    persistés — le comblement de _bridge reste en mémoire."""
    p = os.path.join(SEED, name)
    if not os.path.exists(p): return
    d = pd.Timestamp(day).strftime("%Y-%m-%d")
    with open(p, newline="") as f:
        lines = f.read().splitlines()
    nl = "\r\n" if lines and open(p, "rb").read().endswith(b"\r\n") else "\n"
    if lines and lines[-1].startswith(d + ","):     # relance le même jour : on remplace
        lines.pop()
    elif lines and lines[-1][:10] > d:              # seed plus récent que le jour : rien
        return
    lines.append(f"{d},{value},{value},{value},{value}")
    with open(p, "w", newline="") as f:
        f.write(nl.join(lines) + nl)


def _bridge(df, day, value):
    """Comble le trou entre la fin du seed et 'day' (forward-fill de la dernière
    valeur connue), puis écrit la valeur live du jour. Évite tout hole/saut de
    calendrier qui fausserait les indicateurs au premier run après un export."""
    return _fill_gaps(_append(df, day, value))


def _fill_gaps(df):
    if df is None: return None
    # comble TOUS les trous > 3 j (fin du seed -> points persistés par _persist),
    # pas seulement le dernier : sinon le résultat change dès le 2e run.
    fills = []
    for a, b in zip(df.index[:-1], df.index[1:]):
        if (b - a).days > 3:
            gap = pd.date_range(a + pd.Timedelta(days=1), b - pd.Timedelta(days=1), freq="D")
            lc = float(df.loc[a, "close"])
            fills.append(pd.DataFrame({"open":lc,"high":lc,"low":lc,"close":lc}, index=gap))
    return pd.concat([df, *fills]).sort_index() if fills else df


REF = os.path.join(SEED, "live_ref.json")

# Paniers pour reconstituer un trou dans les exports TradingView (en attendant les alertes TV) :
# TOTAL ~ panier des plus grosses capitalisations ; OTHERS ~ panier d'alts hors top 10.
TOTAL_BASKET = {"BTCUSDT": .62, "ETHUSDT": .13, "XRPUSDT": .05, "BNBUSDT": .04, "SOLUSDT": .03,
                "DOGEUSDT": .01, "ADAUSDT": .01, "TRXUSDT": .01, "LINKUSDT": .005, "AVAXUSDT": .005}
OTHERS_BASKET = ["SUIUSDT", "AVAXUSDT", "TONUSDT", "NEARUSDT", "ONDOUSDT", "AAVEUSDT", "RENDERUSDT",
                 "FETUSDT", "UNIUSDT", "TAOUSDT", "LTCUSDT", "DOTUSDT", "HBARUSDT", "XLMUSDT"]


def _basket(weights, start):
    """Indice buy-and-hold d'un panier (base 1 au premier jour commun)."""
    px = {}
    for sym in weights:
        try:
            px[sym] = binance_daily(sym, start=str(start.date()))["close"]
        except Exception:
            pass
    df = pd.DataFrame(px).dropna(axis=1, how="all").ffill().dropna()
    w = pd.Series({k: weights[k] for k in df.columns}); w = w / w.sum()
    return (df / df.iloc[0]).mul(w, axis=1).sum(axis=1)


def reconstruct_gaps(total, others, max_gap=5):
    """Comble les trous > max_gap jours du seed TradingView en chaînant les variations des
    paniers Binance au dernier niveau TradingView connu. Renvoie (total, others, info)."""
    info = {}
    def gaps(df):
        d = df.index.to_series().diff().dt.days
        return [(df.index[i - 1], df.index[i]) for i in range(1, len(df)) if d.iloc[i] > max_gap]
    for a, b in gaps(total):
        tb = _basket(TOTAL_BASKET, a)
        ob = _basket({k: 1 for k in OTHERS_BASKET}, a)
        days = tb.index[(tb.index > a) & (tb.index < b)]
        if not len(days):
            continue
        t0, o0 = float(total.loc[a, "close"]), float(others.loc[a, "close"]) if a in others.index else None
        tl = t0 * tb.loc[days]
        rows = pd.DataFrame({"open": tl, "high": tl, "low": tl, "close": tl})
        total = pd.concat([total, rows]).sort_index()
        if o0 is not None:
            ol = o0 * (ob.reindex(days).ffill() / tb.loc[days])
            others = pd.concat([others, pd.DataFrame({"open": ol, "high": ol, "low": ol, "close": ol})]).sort_index()
        info[f"{a.date()} -> {b.date()}"] = len(days)
    return total, others, info


def _chain(name, seed_df, day, raw):
    """Niveau à ajouter au seed TradingView à partir d'une source d'un autre univers
    (CoinGecko / CoinPaprika) : on n'en garde que la VARIATION depuis le dernier point,
    appliquée au dernier niveau TradingView. Évite le saut d'échelle (ex. OTHERS.D 8 % vs 13 %)."""
    import json
    ref = json.load(open(REF)) if os.path.exists(REF) else {}
    d = str(pd.Timestamp(day).date())
    r = ref.get(name)
    last_level = float(seed_df["close"].iloc[-1])
    if r and r["date"] == d:                       # relance le même jour : même base
        base_raw, base_level = r["prev_raw"], r["prev_level"]
    elif r:                                        # nouveau jour : la veille devient la base
        base_raw, base_level = r["raw"], r["level"]
    else:                                          # premier passage : on s'ancre sans saut
        base_raw, base_level = raw, last_level
    level = base_level * raw / base_raw
    ref[name] = {"date": d, "raw": raw, "level": level, "prev_raw": base_raw, "prev_level": base_level}
    json.dump(ref, open(REF, "w"), indent=1)
    return level


def get_series(today=None):
    today = pd.Timestamp(today or pd.Timestamp.utcnow().date()).normalize()
    out = {"btc": binance_daily("BTCUSDT"), "eth": binance_daily("ETHUSDT"),
           "gold": get_gold()}

    # ETHBTC : seed TradingView si fourni (fidélité), sinon Binance complet ; append du jour
    eth_seed = _load_seed("ethbtc.csv")
    if eth_seed is not None:
        last_close = float(binance_daily("ETHBTC", start=str(today - pd.Timedelta(days=3))).iloc[-1]["close"])
        out["ethbtc"] = _bridge(eth_seed, today, last_close)
        _persist("ethbtc.csv", today, last_close)
    else:
        out["ethbtc"] = binance_daily("ETHBTC")

    # indices : seed TradingView + trous reconstitués (paniers Binance) + variation du jour
    total_seed, others_seed = _load_seed("total.csv"), _load_seed("others_d.csv")
    if total_seed is not None and others_seed is not None:
        # le dernier jour du seed peut être aujourd'hui (point déjà persisté) : on reconstitue jusqu'à hier
        tt = total_seed if total_seed.index.max() >= today else _append(total_seed, today, float(total_seed["close"].iloc[-1]))
        total_seed, others_seed, out["reconstructed"] = reconstruct_gaps(tt, others_seed)
        if total_seed.index.max() == today and not (_load_seed("total.csv").index.max() >= today):
            total_seed = total_seed.iloc[:-1]                 # retire le point technique ajouté
        if out["reconstructed"]:
            print(f"[info] trous du seed reconstitués (paniers Binance) : {out['reconstructed']}")
    try:
        total_raw, others_raw = total_dominance()
        total_v = _chain("total", total_seed, today, total_raw)
        others_dom = _chain("others_d", others_seed, today, others_raw)
        out["total"]    = _bridge(total_seed,  today, total_v)
        out["others_d"] = _bridge(others_seed, today, others_dom)
        _persist("total.csv", today, total_v)
        _persist("others_d.csv", today, others_dom)
    except Exception as e:
        print(f"[warn] market cap globale indispo ({e}) — seed seul.")
        out["total"], out["others_d"] = _fill_gaps(total_seed), _fill_gaps(others_seed)

    if out["total"] is None:
        raise SystemExit("Seed manquant : exporte CRYPTOCAP:TOTAL -> seed/total.csv "
                         "(time,open,high,low,close).")
    return out
