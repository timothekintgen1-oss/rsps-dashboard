"""
backtest.py — Recalcule les courbes d'équité à chaque run et écrit docs/backtest.json.
Courbes : RSPS Raw (cash hors-marché) · RSPS + Gold (or si tendance, hors-marché) · BTC hodl.
Référence prof = chiffres rapportés (statiques) sur sa fenêtre.
"""
import numpy as np, pandas as pd, indicators as I, strategy as st

FEE = 0.00045                       # taker Hyperliquid
WINDOW = ("2025-01-01", "2026-05-07")
PROF = {
    "raw":  {"perf": 29.8, "sharpe": 0.78, "dd": -28.8},
    "gold": {"perf": 87.3, "sharpe": 1.52, "dd": -21.8},
    "btc":  {"perf": -12.0, "sharpe": None, "dd": -50.0},
}


def _metrics(r, sub=None):
    rr = r if sub is None else r.loc[sub[0]:sub[1]]
    if len(rr) < 5:
        return None
    nav = (1 + rr).cumprod()
    dd = float((nav / nav.cummax() - 1).min())
    yrs = max((rr.index[-1] - rr.index[0]).days / 365, 1e-9)
    cagr = float(nav.iloc[-1] ** (1 / yrs) - 1)
    dt = rr.index.to_series().diff().dt.days.median()          # espacement médian des barres
    ppy = 365.0 / dt if dt and dt > 0 else 365.0               # périodes par an
    vol = rr.std() * np.sqrt(ppy)
    sh = float((rr.mean() * ppy) / vol) if vol > 0 else 0.0
    return {"perf": round((float(nav.iloc[-1]) - 1) * 100, 1),
            "cagr": round(cagr * 100, 1), "sharpe": round(sh, 2),
            "dd": round(dd * 100, 1), "x": round(float(nav.iloc[-1]), 2)}


def run(series):
    total, btc, eth, ethbtc = series["total"], series["btc"], series["eth"], series["ethbtc"]
    gold = series.get("gold")
    idx = total.index

    _, regime, _ = I.build_tpi(total, st.MTPI_SPEC, entry=st.ENTRY, exit=st.EXIT)
    long = (regime.reindex(idx).ffill() > 0).astype(float)
    es, _, _ = I.build_tpi(ethbtc, st.ROT_SPEC, entry=0.0, exit=0.0)
    es = es.reindex(idx, method="ffill").fillna(0)
    w_eth = pd.Series(np.where(es > 0, 0.8, 0.2), index=idx)
    w_btc = 1 - w_eth
    ret_btc = btc["close"].reindex(idx, method="ffill").pct_change().fillna(0)
    ret_eth = eth["close"].reindex(idx, method="ffill").pct_change().fillna(0)
    _dt = pd.Series(idx).diff().dt.days.median() or 1          # pas de temps (1 j, 2 j…)
    _maw = max(2, int(round(50 / _dt)))                        # MA ≈ 50 jours quel que soit le pas

    def build(gold_on):
        we, wb, lg = w_eth.shift(1).fillna(0), w_btc.shift(1).fillna(0), long.shift(1).fillna(0)
        cryp = lg * (we * ret_eth + wb * ret_btc)
        gld = pd.Series(0.0, index=idx); gw = pd.Series(0.0, index=idx)
        if gold_on and gold is not None:
            gc = gold["close"].reindex(idx, method="ffill")
            rg = gc.pct_change().fillna(0)
            gup = (gc > gc.rolling(_maw).mean()).astype(float)
            gw = (1 - lg) * gup.shift(1).fillna(0)
            gld = gw * rg
        turn = (lg * we).diff().abs().fillna(0) + (lg * wb).diff().abs().fillna(0) + gw.diff().abs().fillna(0)
        return cryp + gld - turn * FEE

    raw, goldv = build(False), build(True)
    curves = {"raw": raw, "gold": goldv, "btc": ret_btc}

    # equity normalisée à 100, sous-échantillonnée (~180 pts) pour le JSON
    step = max(1, len(idx) // 180)
    sidx = idx[::step]
    out_curves = {}
    for k, r in curves.items():
        nav = (1 + r).cumprod() * 100
        out_curves[k] = [round(float(v), 2) for v in nav.reindex(sidx).values]

    return {
        "dates": [str(d.date()) for d in sidx],
        "curves": out_curves,
        "metrics_full": {k: _metrics(r) for k, r in curves.items()},
        "metrics_window": {k: _metrics(r, WINDOW) for k, r in curves.items()},
        "prof": PROF, "window": list(WINDOW),
        "as_of": str(idx[-1].date()),
    }
