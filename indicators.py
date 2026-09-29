"""
Ports Python des indicateurs Pine de la stratégie (chacun renvoie un état {-1,+1}).
Convention : +1 = bullish, -1 = bearish, 0 = neutre/non initialisé.
Entrée attendue : DataFrame `df` avec colonnes minuscules open/high/low/close (index = dates).
Réglages par défaut = ceux relevés dans l'Excel (page MTPI/TOTAL sauf mention).

⚠️ Validation de PARITÉ encore à faire : il faut l'OHLC réel (exports TradingView) +
1-2 dates de relevé pour vérifier que l'état calculé == ton +1/-1 du classeur.
Plusieurs indicateurs ont des subtilités (repainting, noyau de lissage) signalées en commentaire.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
#  Helpers façon Pine (ta.*)
# --------------------------------------------------------------------------- #
def ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def sma(s, n):  return s.rolling(n).mean()
def wma(s, n):
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)
def rma(s, n):  return s.ewm(alpha=1.0 / n, adjust=False).mean()   # Wilder

def true_range(df):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    return tr
def atr(df, n): return rma(true_range(df), n)

def _persist(events):
    """events: array de {1,-1,0} ; propage la dernière valeur non nulle (logique `var` Pine)."""
    out = np.zeros(len(events)); cur = 0
    for i, e in enumerate(events):
        if e != 0: cur = e
        out[i] = cur
    return out

# --------------------------------------------------------------------------- #
#  1. Elliott Wave Oscillator (© Koryu)      Excel: close 5 32
# --------------------------------------------------------------------------- #
def ewo_state(df, fast=5, slow=32, use_percent=True, src="close"):
    s = df[src]
    diff = (sma(s, fast) - sma(s, slow))
    if use_percent: diff = diff / s * 100
    return np.where(diff > 0, 1, -1)          # vert si >0, rouge sinon

# --------------------------------------------------------------------------- #
#  2. Sebastine Trend Catcher (© sebastinecc)   défaut len=len2=5
# --------------------------------------------------------------------------- #
def sebastine_state(df, len1=5, len2=5):
    o, h, l, c = (ema(df[x], len1) for x in ["open", "high", "low", "close"])
    haclose = (o + h + l + c) / 4
    haopen = pd.Series(index=df.index, dtype=float)
    haopen.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2
    for i in range(1, len(df)):
        haopen.iloc[i] = (haopen.iloc[i - 1] + haclose.iloc[i - 1]) / 2
    hahigh = pd.concat([h, haopen, haclose], axis=1).max(axis=1)
    halow = pd.concat([l, haopen, haclose], axis=1).min(axis=1)
    o2, c2 = ema(haopen, len2), ema(haclose, len2)
    seb = (c2 / o2 - 1) * 100
    return np.where(seb >= 0, 1, -1)

# --------------------------------------------------------------------------- #
#  3. DFT Overlay (© wbburgin)   N=20, smoothing=10
#     dft = |composante DC| ≈ moyenne mobile N ; dfts = lissage noyau rationnel.
#     bull si dft > dfts (zone lime). Noyau rationnel = approximation causale.
# --------------------------------------------------------------------------- #
def _rational_quadratic(s, lookback=25, rel_weight=1.0, start=10):
    W = lookback + start + 5
    w = np.array([(1 + (i ** 2) / (lookback ** 2 * 2 * rel_weight)) ** (-rel_weight)
                  for i in range(W)])
    def f(x):  # x ordonné ancien->récent ; on pondère du plus récent au plus ancien
        xr = x[::-1]
        return np.dot(xr, w[:len(xr)]) / w[:len(xr)].sum()
    return s.rolling(W).apply(f, raw=True)

def dft_state(df, N=20, smoothing=10):
    dft = sma(df["close"], N).abs()           # |DC| = |moyenne des N dernières closes|
    dfts = _rational_quadratic(dft, 25, 1.0, smoothing)
    return np.where(dft > dfts, 1, -1)

# --------------------------------------------------------------------------- #
#  4. Trend Change Indicator (© QuantitativeAlpha)   Excel MTPI: 11 35 50 0.3 125
#     Signal tracé : diff = ma(fast)-ma(slow) vs trend_margin*ATR. persist sur neutre.
# --------------------------------------------------------------------------- #
def tci_state(df, fast=11, slow=35, atr_len=60, trend_margin=0.3, ma="ema"):
    f = {"ema": ema, "sma": sma, "wma": wma, "rma": rma}[ma]
    diff = f(df["close"], fast) - f(df["close"], slow)
    band = trend_margin * atr(df, atr_len)
    # neutre = 0 (vert / rouge / blanc sur TradingView) : le classeur note bien 0 dans ce cas
    return np.where(diff > band, 1, np.where(diff < -band, -1, 0))

# --------------------------------------------------------------------------- #
#  5. DEGA RMA (© QuantEdgeB)   Excel MTPI: 21 4 2 12 40 1.7 1.7
# --------------------------------------------------------------------------- #
def _dema(s, n): e1 = ema(s, n); return 2 * e1 - ema(e1, n)
def _gaussian(s, n, sigma):
    w = np.array([np.exp(-0.5 * ((i - (n - 1) / 2) / sigma) ** 2) for i in range(n)])
    w = w[::-1]                                # i=0 = barre courante dans Pine
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)

def dega_state(df, len_dema=21, len_fg=4, sigma=2.0, len_rma=12,
               len_atr=40, mult_up=1.7, mult_dn=1.7):
    dema = _dema(df["close"], len_dema)
    rma_line = rma(_gaussian(dema, len_fg, sigma), len_rma)
    custom_atr = (len_atr / 100) * _dema(true_range(df), len_dema * 2)
    longR = rma_line + custom_atr * mult_up
    shortR = rma_line - custom_atr * mult_dn
    ev = np.where(df["close"] > longR, 1, np.where(df["close"] < shortR, -1, 0))
    return _persist(ev)

# --------------------------------------------------------------------------- #
#  6. LNL Trend System (© L&L Capital)   Excel MTPI: "Tight Normal 60"
#     État principal = Stop Line T : close vs EMA13 ± ATR. (TrendMode Tight -> 60)
# --------------------------------------------------------------------------- #
def lnl_state(df, trend_mode="Tight"):
    atr_len = {"Tight": 60, "Normal": 80, "Loose": 100, "FOMC": 120, "Net": 140}[trend_mode]
    trend = ema(df["close"], 13)
    a = (atr_len / 100) * ema(true_range(df), 8)
    ev = np.where(df["close"] > trend + a, 1, np.where(df["close"] < trend - a, -1, 0))
    return _persist(ev)

# --------------------------------------------------------------------------- #
#  7. Trend Strength Gauge / HSMA (© VanHe1sing)   length=20
#     (bug d'origine : a = 3*wma-2*wma = wma) -> état = signe(wma - sma)
# --------------------------------------------------------------------------- #
def tsg_state(df, length=20):
    return np.where(wma(df["close"], length) - sma(df["close"], length) > 0, 1, -1)

# --------------------------------------------------------------------------- #
#  8. Kalman Hull Supertrend (© BackQuant)   Excel Trash: 3 0.01 12 1.08
# --------------------------------------------------------------------------- #
def _kalman(arr, meas_noise, proc_noise=0.01):
    n = len(arr); out = np.empty(n)
    x = arr[0]; P = 1.0
    for i in range(n):
        P = P + proc_noise
        K = P / (P + meas_noise)
        x = x + K * (arr[i] - x)
        P = (1 - K) * P
        out[i] = x
    return out

def kalman_hull_st_state(df, meas_noise=3.0, proc_noise=0.01, atr_period=12, factor=1.08):
    c = df["close"].to_numpy()
    def kf(a, mn): return _kalman(a, mn, proc_noise)
    khma = kf(2 * kf(c, meas_noise / 2) - kf(c, meas_noise), max(1, round(np.sqrt(meas_noise))))
    src = pd.Series(khma, index=df.index)
    a = atr(df, atr_period).to_numpy()
    close = c
    up = src.to_numpy() + factor * a
    dn = src.to_numpy() - factor * a
    lower = np.copy(dn); upper = np.copy(up); direction = np.zeros(len(df))
    st = np.full(len(df), np.nan)
    for i in range(len(df)):
        pl = lower[i - 1] if i else dn[i]
        pu = upper[i - 1] if i else up[i]
        lower[i] = dn[i] if (dn[i] > pl or (i and close[i - 1] < pl)) else pl
        upper[i] = up[i] if (up[i] < pu or (i and close[i - 1] > pu)) else pu
        if i == 0 or np.isnan(a[i - 1]):
            direction[i] = 1
        elif st[i - 1] == pu:
            direction[i] = -1 if close[i] > upper[i] else 1
        else:
            direction[i] = 1 if close[i] < lower[i] else -1
        st[i] = lower[i] if direction[i] == -1 else upper[i]
    # Trend : +1 quand direction passe < 0 (uptrend), -1 quand direction passe > 0
    long_ev = (direction < 0) & (np.roll(direction, 1) >= 0)
    short_ev = (direction > 0) & (np.roll(direction, 1) <= 0)
    ev = np.where(long_ev, 1, np.where(short_ev, -1, 0)); ev[0] = 0
    return _persist(ev)

# --------------------------------------------------------------------------- #
#  9. Normalized KAMA Oscillator (© IkkeOmar)   fast=7 slow=19 er=8 norm=50
# --------------------------------------------------------------------------- #
def kama_state(df, fast=7, slow=19, er_period=8, norm_period=50, use_norm=True):
    c = df["close"]
    change = (c - c.shift(er_period)).abs()
    vol = (c - c.shift(1)).abs().rolling(er_period).sum()
    er = change / vol
    sc = er * (2 / (fast + 1) - 2 / (slow + 1)) + 2 / (slow + 1)
    kama = ema(c, fast) + sc * (c - ema(c, fast))
    if not use_norm:
        return np.where(kama > 0, 1, -1)
    lo, hi = kama.rolling(norm_period).min(), kama.rolling(norm_period).max()
    normd = (kama - lo) / (hi - lo) - 0.5
    return np.where(normd > 0, 1, -1)

# --------------------------------------------------------------------------- #
#  10. MA Band Distance Monitor (© HasanRifat)   Excel MTPI: 20 5 close close EMA SMA
#      Signal = croisement fastMA / slowMA (alertes crossover/under). bull si fast>slow.
# --------------------------------------------------------------------------- #
def _ma(s, n, t):
    return {"SMA": sma, "EMA": ema, "SMMA (RMA)": rma, "RMA": rma, "WMA": wma}[t](s, n)

def ma_band_distance_state(df, slowlen=20, fastlen=5, slow_type="EMA", fast_type="SMA"):
    fast = _ma(df["close"], fastlen, fast_type)
    slow = _ma(df["close"], slowlen, slow_type)
    return np.where(fast > slow, 1, -1)

# --------------------------------------------------------------------------- #
#  11. 4-Colored EMA Diff & Stochastic Traffic Light (MTF)   Excel MTPI: 7 19 14 3 3
#      État principal = signe(EMA_fast − EMA_slow). Option : feu stochastique k>d.
# --------------------------------------------------------------------------- #
def mtf_ema_stoch_state(df, ema_fast=7, ema_slow=19, use_stoch=False,
                        k_len=14, d_len=3, smooth_k=3):
    diff = ema(df["close"], ema_fast) - ema(df["close"], ema_slow)
    if not use_stoch:
        return np.where(diff >= 0, 1, -1)
    ll, hh = df["low"].rolling(k_len).min(), df["high"].rolling(k_len).max()
    stoch = 100 * (df["close"] - ll) / (hh - ll)
    k = sma(stoch, smooth_k); d = sma(k, d_len)
    return np.where(k > d, 1, -1)

# --------------------------------------------------------------------------- #
#  12. WonderTrend (PSAR + Keltner state machine)   Excel MTPI: 20 0.02 0.02 0.2
#      État = ptrend (dernier état directionnel non nul de la machine).
# --------------------------------------------------------------------------- #
def _psar(high, low, af0, step, maxv):
    n = len(high); sar = np.empty(n)
    up = True; af = af0; ep = high[0]; s = low[0]; sar[0] = s
    for i in range(1, n):
        s = s + af * (ep - s)
        if up:
            s = min(s, low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
            if high[i] > ep: ep = high[i]; af = min(af + step, maxv)
            if low[i] < s: up = False; s = ep; ep = low[i]; af = af0
        else:
            s = max(s, high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
            if low[i] < ep: ep = low[i]; af = min(af + step, maxv)
            if high[i] > s: up = True; s = ep; ep = high[i]; af = af0
        sar[i] = s
    return sar

def wondertrend_state(df, length=20, psar_start=0.02, psar_inc=0.02, psar_max=0.2):
    high = df["high"].to_numpy(); low = df["low"].to_numpy(); close = df["close"].to_numpy()
    out = _psar(high, low, psar_start, psar_inc, psar_max)
    kc = ema(df["close"], length).to_numpy()           # Keltner basis = EMA(close,length)
    n = len(df)
    psar = np.where(out < close, 1, -1)
    save = np.empty(n); save[0] = out[0]
    for i in range(1, n):
        save[i] = out[i - 1] if psar[i] != psar[i - 1] else save[i - 1]
    trend = np.zeros(n); trend[0] = 1; ptrend = np.ones(n)
    for i in range(1, n):
        t = trend[i - 1]
        l2 = low[i - 2] if i >= 2 else low[i]; h2 = high[i - 2] if i >= 2 else high[i]
        up_c = psar[i] == 1 and low[i] > max(kc[i], l2) and low[i - 1] > save[i] and l2 > max(kc[i], save[i])
        dn_c = psar[i] == -1 and high[i] < min(kc[i], h2) and high[i - 1] < save[i] and h2 < min(kc[i], save[i])
        wave = 3 if (up_c or dn_c) else 0
        if t <= 0 and wave >= 3 and psar[i] == 1: t = 1
        elif t >= 0 and wave >= 3 and psar[i] == -1: t = -1
        if (t == -1 and save[i] > save[i - 1]) or (t == 1 and save[i] < save[i - 1]): t = 0
        trend[i] = t
        ptrend[i] = t if t != 0 else ptrend[i - 1]
    return ptrend.astype(int)

# --------------------------------------------------------------------------- #
#  13. Z-Score Deviation — PROXY OUVERT   Excel MTPI: close 22 15 / ETHBTC: 27 18
#      ⚠️ L'original "Z-Score Deviation Fusion" est PROTÉGÉ sur TradingView (non
#      reproductible). Ceci est un z-score de déviation standard : z = (close − MA) / σ.
#      bull si z > 0 (prix au-dessus de sa moyenne). À VALIDER/AJUSTER contre ta lecture.
# --------------------------------------------------------------------------- #
def z_score_deviation_state(df, len_dev=22, len_sig=15, mode="zero"):
    s = df["close"]
    mean = sma(s, len_dev)
    std = s.rolling(len_dev).std(ddof=0)
    z = (s - mean) / std
    if mode == "signal":                  # variante : z vs sa ligne de signal lissée
        return np.where(z > sma(z, len_sig), 1, -1)
    return np.where(z > 0, 1, -1)          # défaut : signe de la déviation

# --------------------------------------------------------------------------- #
#  14. Adaptive Gaussian Moving Average (© LeafAlgo)   Excel LTPI: 23 20 1
#      MA gaussienne à sigma adaptatif (= stdev du close). bull si close >= AGMA.
# --------------------------------------------------------------------------- #
def agma_state(df, length=23, vol_period=20, adaptive=True, sigma_fixed=1.0):
    close = df["close"]
    sigma = (close.rolling(vol_period).std(ddof=0) if adaptive
             else pd.Series(sigma_fixed, index=close.index)).to_numpy()
    H = np.array([close.rolling(i + 1).max().to_numpy() for i in range(length)])
    L = np.array([close.rolling(i + 1).min().to_numpy() for i in range(length)])
    val = H + L                                   # value = highest(close,i+1)+lowest(close,i+1)
    idx = np.arange(length) - (length - 1)
    gma = np.full(len(close), np.nan)
    for t in range(len(close)):
        s = sigma[t]
        if np.isnan(s) or s == 0:
            continue
        w = np.exp(-((idx / (2 * s)) ** 2) / 2)
        gma[t] = (np.dot(val[:, t], w) / w.sum()) / 2
    return np.where(close.to_numpy() >= gma, 1, -1)

# --------------------------------------------------------------------------- #
#  BLOC ON-CHAIN / MACRO (LTPI) — nécessite des données NON-PRIX
# --------------------------------------------------------------------------- #
def valuation_state(z, mode="roc", thresh=0.0, roc_period=1):
    """
    Proxy du bloc on-chain/macro via TON BTC Valuation Index (Z-score composite).
    mode='roc'   -> tendance : bull si la valorisation monte (RoC > 0)   [défaut, façon LTPI trend]
    mode='level' -> niveau  : bull si Z < seuil (zone bon marché)        [façon SDCA/accumulation]
    """
    z = pd.Series(z)
    if mode == "level":
        return np.where(z < thresh, 1, -1)
    return np.where(z.diff(roc_period) > 0, 1, -1)

def _zs(s, mean, std): return (s - mean) / std

def onchain_zscore_state(mc, realized_mc, sopr, nupl_len=126, sopr_len=111,
                         mvrv_len=111, sopr_ema=14, l_th=0.73, s_th=-0.44):
    """Port fidèle de On-chain Zscore (QuantumResearch). NÉCESSITE mc, realized_mc, sopr (Glassnode/Coinmetrics)."""
    nupl = (mc - realized_mc) / mc * 100
    nuplz = _zs(nupl, sma(nupl, nupl_len), nupl.rolling(nupl_len).std(ddof=0))
    soprz = ema(_zs(sopr, sma(sopr, sopr_len), sopr.rolling(sopr_len).std(ddof=0)), sopr_ema)
    mvrv = mc / realized_mc
    mvrvz = _zs(mvrv, ema(mvrv, mvrv_len), mvrv.rolling(mvrv_len).std(ddof=0))
    z = (nuplz + soprz + mvrvz) / 3
    ev = np.where(z > l_th, 1, np.where(z < s_th, -1, 0))
    return _persist(ev)

def sopr_loop_state(sopr, ma_len=30, a=1, b=60, long_s=40, short_s=8, ma="ema"):
    """Port du SOPR Smoothed MA For-Loop (CHIPA). NÉCESSITE la série SOPR (Glassnode)."""
    f = {"ema": ema, "sma": sma, "rma": rma, "wma": wma}[ma]
    arr = f(sopr, ma_len).to_numpy()
    out = np.zeros(len(arr))
    for t in range(len(arr)):
        s2 = 0
        for i in range(a, b + 1):
            if t - i >= 0:
                s2 += 1 if arr[t] > arr[t - i] else -1
        out[t] = s2
    ev = np.where(out > long_s, 1, np.where(out < short_s, -1, 0))
    return _persist(ev)

# --------------------------------------------------------------------------- #
#  Ré-échantillonnage multi-timeframe (2D / 3D façon TradingView)
#  ⚠️ TV ancre les barres multi-jours à une date de référence : l'`origin` ci-dessous
#     est à CALIBRER contre ton classeur (sinon décalage d'une barre).
# --------------------------------------------------------------------------- #
def resample_tf(df, tf="2D", origin="2018-01-01"):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    cols = {k: v for k, v in agg.items() if k in df.columns}
    if tf.upper() in ("W", "1W", "WEEK"):
        return df.resample("W-MON").agg(cols).dropna()
    n = int(tf[:-1]) if tf[-1].upper() == "D" else int(tf)   # "2D" -> 2, "3D" -> 3
    anchor = pd.Timestamp(origin)
    bar_id = (df.index - anchor).days // n                    # barre N-jours ancrée sur `origin`
    g = df.groupby(bar_id).agg(cols)
    g.index = df.index.to_series().groupby(bar_id).last().values  # étiquette = dernier jour de la barre
    return g.dropna()

def state_to_daily(state_series, daily_index):
    """Reprojette un état calculé en TF lente sur l'index quotidien (forward-fill)."""
    return state_series.reindex(daily_index, method="ffill")

# --------------------------------------------------------------------------- #
#  Registre + assemblage TPI
# --------------------------------------------------------------------------- #
INDICATORS = {
    "elliott_wave_osc": ewo_state,
    "sebastine_trend_catcher": sebastine_state,
    "dft_overlay": dft_state,
    "trend_change_indicator": tci_state,
    "lnl_trend_system": lnl_state,
    "dega_rma": dega_state,
    "trend_strength_gauge": tsg_state,
    "kalman_hull_st": kalman_hull_st_state,
    "kama_osc": kama_state,
    "ma_band_distance": ma_band_distance_state,
    "mtf_ema_stoch": mtf_ema_stoch_state,
    "wondertrend": wondertrend_state,
    "z_score_deviation": z_score_deviation_state,
    "agma": agma_state,
}

def tpi(df, members, entry=0.1, exit=0.1):
    """Moyenne des états des indicateurs `members` -> score, état régime LONG/CASH."""
    scores = pd.DataFrame({m: INDICATORS[m](df) for m in members}, index=df.index)
    score = scores.mean(axis=1)
    regime = np.where(score > entry, 1, np.where(score < -exit, -1, np.nan))
    regime = pd.Series(regime, index=df.index).ffill().fillna(0)
    return score, regime, scores

def build_tpi(daily_df, spec, entry=0.1, exit=0.1, origin="2018-01-01"):
    """
    Assembleur piloté par spec. `spec` = liste de dicts :
        {"label": str, "name": clé INDICATORS, "tf": "2D"/"3D"/"W"/"1D", "params": {...}}
    Chaque indicateur est calculé sur SA timeframe (ré-échantillonnée depuis le daily),
    puis reprojeté en quotidien (ffill) avant la moyenne. Bornes d'hystérésis entry/exit.
    """
    states = {}
    for s in spec:
        tf = s.get("tf", "1D")
        d = daily_df if tf in ("1D", "D") else resample_tf(daily_df, tf, origin)
        st = INDICATORS[s["name"]](d, **s.get("params", {}))
        st = pd.Series(np.asarray(st), index=d.index)
        states[s["label"]] = state_to_daily(st, daily_df.index)
    mat = pd.DataFrame(states, index=daily_df.index)
    score = mat.mean(axis=1)
    regime = np.where(score > entry, 1, np.where(score < -exit, -1, np.nan))
    regime = pd.Series(regime, index=daily_df.index).ffill().fillna(0)
    return score, regime, mat


if __name__ == "__main__":
    # Test : OHLC synthétique pour vérifier que tout tourne sans erreur
    idx = pd.date_range("2017-01-01", periods=800, freq="D")
    rng = np.random.default_rng(0)
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.03, len(idx))))
    df = pd.DataFrame({"close": close}, index=idx)
    df["open"] = df["close"].shift(1).fillna(df["close"])
    df["high"] = df[["open", "close"]].max(axis=1) * (1 + rng.uniform(0, .02, len(idx)))
    df["low"] = df[["open", "close"]].min(axis=1) * (1 - rng.uniform(0, .02, len(idx)))
    print("Dernier état de chaque indicateur (données synthétiques) :")
    for name, fn in INDICATORS.items():
        st = fn(df)
        print(f"  {name:26s} {int(st[-1]):+d}")
    members = ["elliott_wave_osc", "mtf_ema_stoch", "sebastine_trend_catcher",
               "dft_overlay", "wondertrend", "trend_change_indicator",
               "ma_band_distance", "lnl_trend_system", "dega_rma", "z_score_deviation"]  # MTPI complet 10/10 (Z-Score = proxy)
    score, regime, _ = tpi(df, members)
    print(f"\nMTPI (10/10, Z-Score proxy) dernier = {score.iloc[-1]:+.2f}  régime = {int(regime.iloc[-1]):+d}")
