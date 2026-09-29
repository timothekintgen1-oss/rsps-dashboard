"""
backtest_alts.py — Backtest de la poche « trash » (pages 4 et 5 du classeur), sans regard vers le futur.

À chaque date, la table de sélection est recalculée avec les seules données disponibles ce jour-là :
  univers   tokens de seed/alts.json ayant au moins 180 jours d'historique à cette date
  MCap      pas d'historique gratuit de market cap -> proxy : volume moyen 30 j sous la médiane
  Bêta      bêta 1 an (rendements 2 j) vs BTC au-dessus de la médiane de l'univers du jour
  Tendances mini-TPI ETHBTC (5 ind.) en 2D sur TOKEN/BTC, TOKEN/ETH, TOKEN/USD
  Sélection score >= seuil, poids égaux ; part trash = 20 % x force OTHERS.D si LONG et OTHERS.D > 0
Limite : la liste de tokens est celle d'aujourd'hui (biais du survivant) — résultat optimiste.
"""
import json, os
import numpy as np, pandas as pd
import data_sources as ds, indicators as I, strategy as st
from alts import _ratio, CFG

START = "2019-01-01"
MIN_HISTORY = 180


def _tpi(df):
    if df is None or len(df) < MIN_HISTORY:
        return None
    score, _, _ = I.build_tpi(df, st.ROT_SPEC, entry=0.0, exit=0.0)
    return score


def panel(btc, eth):
    """DataFrames quotidiens (dates x tokens) : clôture, volume, bêta, tendances."""
    cfg = json.load(open(CFG))
    close, vol, tb, te, tu = {}, {}, {}, {}, {}
    for t in cfg["tokens"]:
        try:
            tok = ds.binance_daily(t["binance"], start=START, volume=True)
            if len(tok) < 400:                                   # listing récent : KuCoin / Bybit
                alt = ds.token_daily(t["binance"], start=START)
                if len(alt) > len(tok):
                    tok = alt.assign(qvol=np.nan)
        except Exception as e:
            print(f"[bt-alts] {t['ticker']} indispo : {e}"); continue
        if len(tok) < MIN_HISTORY:
            continue
        k = t["ticker"]
        close[k], vol[k] = tok["close"], tok["qvol"]
        tu[k], tb[k], te[k] = _tpi(tok[["open","high","low","close"]]), _tpi(_ratio(tok, btc)), _tpi(_ratio(tok, eth))
    days = btc.index
    C = pd.DataFrame(close).reindex(days)
    V = pd.DataFrame(vol).reindex(days).rolling(30, min_periods=10).mean()
    avail = C.notna() & (C.notna().cumsum() >= MIN_HISTORY)
    r2, b2 = C.pct_change(2, fill_method=None), btc["close"].pct_change(2)
    beta = r2.rolling(365, min_periods=180).cov(b2).div(b2.rolling(365, min_periods=180).var(), axis=0)
    T = {n: pd.DataFrame({k: v for k, v in d.items() if v is not None}).reindex(days).ffill()
         for n, d in (("vs_btc", tb), ("vs_eth", te), ("usd", tu))}
    return C, V, beta, T, avail, cfg["threshold"]


def selection(C, V, beta, T, avail, threshold):
    """Masque (dates x tokens) des tokens retenus, calculé date par date."""
    Vm, Bm = V.where(avail), beta.where(avail)
    f_mcap = Vm.lt(Vm.median(axis=1), axis=0)
    f_beta = Bm.ge(Bm.median(axis=1), axis=0)
    score = f_mcap.astype(int) + f_beta.astype(int)
    for n in ("vs_btc", "vs_eth", "usd"):
        score += (T[n].reindex(columns=C.columns) > 0).astype(int)
    return (score >= threshold) & avail, score


def sleeve(series, idx, long, w_eth, fee):
    """Rendements du portefeuille complet (majeurs + trash) sur l'index du backtest."""
    btc, eth = series["btc"], series["eth"]
    C, V, beta, T, avail, thr = panel(btc, eth)
    sel, _ = selection(C, V, beta, T, avail, thr)
    trash_s, _, _ = I.build_tpi(series["others_d"], st.TRASH_SPEC, entry=0.0, exit=0.0)
    trash_s = trash_s.reindex(idx, method="ffill").fillna(0)
    sel = sel.reindex(idx, method="ffill").fillna(False).astype(bool)
    n = sel.sum(axis=1)
    trash_pct = np.where((long > 0) & (trash_s > 0) & (n > 0), st.TRASH_MAX * trash_s, 0.0)
    trash_pct = pd.Series(trash_pct, index=idx)
    w_alt = sel.astype(float).div(n.replace(0, np.nan), axis=0).fillna(0).mul(trash_pct, axis=0)
    cons = long * (1 - trash_pct)
    W = pd.concat([w_alt, (cons * w_eth).rename("ETH"), (cons * (1 - w_eth)).rename("BTC")], axis=1)
    px = pd.concat([C.reindex(idx, method="ffill"), eth["close"].reindex(idx, method="ffill").rename("ETH"),
                    btc["close"].reindex(idx, method="ffill").rename("BTC")], axis=1)
    R = px.pct_change(fill_method=None).fillna(0)
    Ws = W.shift(1).fillna(0)
    turn = W.diff().abs().sum(axis=1).fillna(0)
    ret = (Ws * R).sum(axis=1) - turn * fee
    active = trash_pct > 0
    stats = {"since": str(idx[idx >= pd.Timestamp(START)][0].date()),
             "pct_time_alts": round(100 * float(active[idx >= pd.Timestamp("2020-01-01")].mean()), 1),
             "avg_n_alts": round(float(n[active].mean()), 1) if active.any() else 0,
             "last_selection": [c for c in sel.columns if sel.iloc[-1][c]],
             "universe_now": int(avail.iloc[-1].sum())}
    return ret, stats
