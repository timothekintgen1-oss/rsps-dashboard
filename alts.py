"""
alts.py — Page 5 du classeur : table de sélection du trash (alts), automatisée.

Pour chaque token de seed/alts.json, 5 filtres valant 0 ou 1 (colonnes du classeur) :
  MCAP<Median   market cap sous la médiane de la liste (CoinGecko)
  Beta          bêta vs BTC (rendements 2D, 1 an) au-dessus de la médiane de la liste
  vs BTC (2D)   TOKEN/BTC en tendance haussière   (= BTCUSD/TOKEN baissier)
  vs ETH (2D)   TOKEN/ETH en tendance haussière   (= ETHUSD/TOKEN baissier)
  USD (2D)      TOKEN/USD en tendance haussière
Score = somme ; sélection si score >= seuil (4), poids égaux (page 1 du classeur).
Tendance = mini-TPI des 5 indicateurs de la page ETHBTC (DEGA, Sebastine, TrendChange,
Z-Score, WonderTrend) calculé sur la série en 2D : haussier si moyenne > 0.
"""
import json, os
import numpy as np, pandas as pd
import data_sources as ds, indicators as I, strategy as st

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "seed", "alts.json")
START = "2024-01-01"


def _ratio(a, b):
    """Bougies d'un ratio A/B, composante par composante (comme un spread TradingView)."""
    j = a.join(b, how="inner", lsuffix="_a", rsuffix="_b")
    r = pd.DataFrame({k: j[f"{k}_a"] / j[f"{k}_b"] for k in ("open", "high", "low", "close")})
    r["high"] = r.max(axis=1); r["low"] = r.min(axis=1)
    return r


def _trend(df):
    if df is None or len(df) < 120:
        return None
    score, _, mat = I.build_tpi(df, st.ROT_SPEC, entry=0.0, exit=0.0)
    return float(score.iloc[-1])


def _beta(tok, btc, days=365):
    j = pd.concat([tok["close"], btc["close"]], axis=1, keys=["t", "b"]).dropna()
    j = j.iloc[::2].pct_change().dropna().iloc[-days // 2:]       # rendements 2D sur ~1 an
    return float(np.cov(j["t"], j["b"])[0, 1] / np.var(j["b"], ddof=1)) if len(j) > 30 else None


def _mcaps(tokens):
    """{ticker: market cap USD} — CoinGecko, sinon CoinPaprika (gratuit, sans clé)."""
    try:
        rows = ds._cg("coins/markets", vs_currency="usd", ids=",".join(t["coingecko"] for t in tokens), per_page=250)
        by_id = {r["id"]: r.get("market_cap") for r in rows}
        return {t["ticker"]: by_id.get(t["coingecko"]) for t in tokens}
    except Exception as e:
        print(f"[alts] CoinGecko indispo ({e}) -> CoinPaprika")
    try:
        import requests
        rows = requests.get("https://api.coinpaprika.com/v1/tickers", params={"quotes": "USD"},
                            headers=ds.UA, timeout=60).json()
        best = {}
        for r in rows:                                   # symbole ambigu : on garde le mieux classé
            sym, rank = r.get("symbol"), r.get("rank") or 10**9
            if sym and (sym not in best or rank < best[sym][0]):
                best[sym] = (rank, r["quotes"]["USD"].get("market_cap"))
        return {t["ticker"]: best.get(t["ticker"], (0, None))[1] for t in tokens}
    except Exception as e:
        print(f"[alts] market caps indispo : {e}")
        return {}


def run(btc=None, eth=None):
    cfg = json.load(open(CFG))
    btc = btc if btc is not None else ds.binance_daily("BTCUSDT", start=START)
    eth = eth if eth is not None else ds.binance_daily("ETHUSDT", start=START)
    btc, eth = btc.loc[START:], eth.loc[START:]
    mc = _mcaps(cfg["tokens"])
    rows = []
    for t in cfg["tokens"]:
        try:
            tok = ds.token_daily(t["binance"], start=START)
        except Exception as e:
            print(f"[alts] {t['ticker']} indispo : {e}"); continue
        rows.append({"ticker": t["ticker"], "mcap": mc.get(t["ticker"]),
                     "beta": _beta(tok, btc),
                     "vs_btc": _trend(_ratio(tok, btc)), "vs_eth": _trend(_ratio(tok, eth)),
                     "usd": _trend(tok), "price": float(tok["close"].iloc[-1])})
    df = pd.DataFrame(rows)
    med_mc = df["mcap"].dropna().median() if df["mcap"].notna().any() else None
    med_beta = df["beta"].dropna().median()
    out = []
    for _, r in df.iterrows():
        f = {"mcap": int(med_mc is not None and r["mcap"] is not None and r["mcap"] < med_mc),
             "beta": int(r["beta"] is not None and r["beta"] >= med_beta),
             "vs_btc": int((r["vs_btc"] or 0) > 0),
             "vs_eth": int((r["vs_eth"] or 0) > 0),
             "usd": int((r["usd"] or 0) > 0)}
        out.append({"ticker": r["ticker"], "filters": f, "score": sum(f.values()),
                    "mcap": None if pd.isna(r["mcap"]) else float(r["mcap"]),
                    "beta": None if r["beta"] is None else round(r["beta"], 2),
                    "tpi": {k: None if r[k] is None else round(r[k], 2) for k in ("vs_btc", "vs_eth", "usd")},
                    "price": r["price"]})
    out.sort(key=lambda x: (-x["score"], -(x["tpi"]["vs_btc"] or -9)))
    sel = [x["ticker"] for x in out if x["score"] >= cfg["threshold"]]
    return {"date": str(btc.index[-1].date()), "threshold": cfg["threshold"],
            "selected": sel, "tokens": out}


if __name__ == "__main__":
    r = run()
    print(f"{r['date']}  seuil {r['threshold']}  -> sélection : {', '.join(r['selected']) or 'aucune'}")
    for x in r["tokens"]:
        f = x["filters"]
        print(f"  {x['ticker']:7} score {x['score']}  mcap<med {f['mcap']} beta {f['beta']} ({x['beta']}) "
              f"vsBTC {f['vs_btc']} ({x['tpi']['vs_btc']}) vsETH {f['vs_eth']} ({x['tpi']['vs_eth']}) USD {f['usd']} ({x['tpi']['usd']})")
