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

    # indices : seed + append CoinGecko (avec comblement du trou)
    total_seed, others_seed = _load_seed("total.csv"), _load_seed("others_d.csv")
    try:
        total_v, others_dom = coingecko_total_dominance()
        out["total"]    = _bridge(total_seed,  today, total_v)
        out["others_d"] = _bridge(others_seed, today, others_dom)
        _persist("total.csv", today, total_v)
        _persist("others_d.csv", today, others_dom)
    except Exception as e:
        print(f"[warn] CoinGecko indispo ({e}) — seed seul.")
        out["total"], out["others_d"] = _fill_gaps(total_seed), _fill_gaps(others_seed)

    if out["total"] is None:
        raise SystemExit("Seed manquant : exporte CRYPTOCAP:TOTAL -> seed/total.csv "
                         "(time,open,high,low,close).")
    return out
