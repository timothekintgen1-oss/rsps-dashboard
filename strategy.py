"""
strategy.py — Spec calibrée RSPS + calcul régime/rotation/trash + réciprocité.
Paramètres validés en parité vs relevés TradingView (8/10 exacts ; DEGA exact ;
WonderTrend = PSAR approché ; Z-Score = proxy 30/20). Voir README.
"""
import pandas as pd
import indicators as I

ENTRY = 0.10   # LONG si MTPI > ENTRY
EXIT  = 0.10   # CASH si MTPI < EXIT

# --- MTPI : CRYPTOCAP:TOTAL (2D / 3D) ---------------------------------------
MTPI_SPEC = [
    {"label": "EWO (5 32)",          "name": "elliott_wave_osc",       "tf": "2D", "params": {"fast": 5, "slow": 32}},
    {"label": "MTF-EMA (7 19)",      "name": "mtf_ema_stoch",          "tf": "2D", "params": {"ema_fast": 7, "ema_slow": 19}},
    {"label": "Sebastine (9 6)",     "name": "sebastine_trend_catcher","tf": "3D", "params": {"len1": 9, "len2": 6}},
    {"label": "Z-Score (30 20)",     "name": "z_score_deviation",      "tf": "2D", "params": {"len_dev": 30, "len_sig": 20}},
    {"label": "DFT (6 29)",          "name": "dft_overlay",            "tf": "2D", "params": {"N": 6, "smoothing": 29}},
    {"label": "WonderTrend (20)",    "name": "wondertrend",            "tf": "2D", "params": {"length": 20}},
    {"label": "TrendChange (11 35)", "name": "trend_change_indicator", "tf": "3D", "params": {"fast": 11, "slow": 35, "atr_len": 50, "trend_margin": 0.3}},
    {"label": "MA Band (20 5)",      "name": "ma_band_distance",       "tf": "2D", "params": {"slowlen": 20, "fastlen": 5, "slow_type": "EMA", "fast_type": "SMA"}},
    {"label": "LNL (Tight)",         "name": "lnl_trend_system",       "tf": "2D", "params": {"trend_mode": "Tight"}},
    {"label": "DEGA (21..)",         "name": "dega_rma",               "tf": "2D", "params": {}},
]

# --- Rotation : ETHBTC (2D) --------------------------------------------------
ROT_SPEC = [
    {"label": "DEGA (23..)",         "name": "dega_rma",               "tf": "2D", "params": {"len_dema": 23, "len_fg": 4, "sigma": 2, "len_rma": 21, "len_atr": 40, "mult_up": 1.7, "mult_dn": 1.7}},
    {"label": "Sebastine (16 15)",   "name": "sebastine_trend_catcher","tf": "2D", "params": {"len1": 16, "len2": 15}},
    {"label": "TrendChange (16 40)", "name": "trend_change_indicator", "tf": "2D", "params": {"fast": 16, "slow": 40, "atr_len": 50, "trend_margin": 0.3}},
    {"label": "Z-Score (27 18)",     "name": "z_score_deviation",      "tf": "2D", "params": {"len_dev": 27, "len_sig": 18}},
    {"label": "WonderTrend (def)",   "name": "wondertrend",            "tf": "2D", "params": {}},
]

# --- Trash : OTHERS.D (3D) ---------------------------------------------------
TRASH_SPEC = [
    {"label": "DFT (14 14)",         "name": "dft_overlay",            "tf": "3D", "params": {"N": 14, "smoothing": 14}},
    {"label": "EWO (7 26)",          "name": "elliott_wave_osc",       "tf": "3D", "params": {"fast": 7, "slow": 26}},
    {"label": "MTF-EMA (12 13)",     "name": "mtf_ema_stoch",          "tf": "3D", "params": {"ema_fast": 12, "ema_slow": 13}},
    {"label": "Trend Strength (21)", "name": "trend_strength_gauge",   "tf": "3D", "params": {"length": 21}},
    {"label": "Kalman Hull (3..)",   "name": "kalman_hull_st",         "tf": "3D", "params": {"meas_noise": 3, "proc_noise": 0.01, "atr_period": 12, "factor": 1.08}},
]


# --- LTPI : Weekly (9 techniques reproductibles ; 5 on-chain non inclus) -----
LTPI_SPEC = [
    {"label": "LNL (Normal)",        "name": "lnl_trend_system",       "tf": "W", "params": {"trend_mode": "Normal"}},
    {"label": "Sebastine (9 10)",    "name": "sebastine_trend_catcher","tf": "W", "params": {"len1": 9, "len2": 10}},
    {"label": "EWO (4 26)",          "name": "elliott_wave_osc",       "tf": "W", "params": {"fast": 4, "slow": 26}},
    {"label": "DFT (3 20)",          "name": "dft_overlay",            "tf": "W", "params": {"N": 3, "smoothing": 20}},
    {"label": "AGMA (23 20 1)",      "name": "agma",                   "tf": "W", "params": {"length": 23, "vol_period": 20, "sigma_fixed": 1.0}},
    {"label": "TrendChange (40 60)", "name": "trend_change_indicator", "tf": "W", "params": {"fast": 40, "slow": 60, "atr_len": 60, "trend_margin": 0.3}},
    {"label": "Kalman Hull (4..)",   "name": "kalman_hull_st",         "tf": "W", "params": {"meas_noise": 4, "proc_noise": 0.01, "atr_period": 4, "factor": 1.05}},
    {"label": "Trend Strength (17)", "name": "trend_strength_gauge",   "tf": "W", "params": {"length": 17}},
    {"label": "MTF-EMA (12 6)",      "name": "mtf_ema_stoch",          "tf": "W", "params": {"ema_fast": 12, "ema_slow": 6}},
]


# --- LTPI : TOTAL Weekly (proxy technique 9/14 — 5 on-chain non reproductibles) ---
LTPI_SPEC = [
    {"label": "LNL (Normal)",        "name": "lnl_trend_system",       "tf": "W", "params": {"trend_mode": "Normal"}},
    {"label": "Sebastine (9 10)",    "name": "sebastine_trend_catcher","tf": "W", "params": {"len1": 9, "len2": 10}},
    {"label": "EWO (4 26)",          "name": "elliott_wave_osc",       "tf": "W", "params": {"fast": 4, "slow": 26}},
    {"label": "DFT (3 20)",          "name": "dft_overlay",            "tf": "W", "params": {"N": 3, "smoothing": 20}},
    {"label": "AGMA (23 20)",        "name": "agma",                   "tf": "W", "params": {"length": 23, "vol_period": 20}},
    {"label": "TrendChange (40 60)", "name": "trend_change_indicator", "tf": "W", "params": {"fast": 40, "slow": 60, "atr_len": 60, "trend_margin": 0.3}},
    {"label": "Kalman Hull (4..)",   "name": "kalman_hull_st",         "tf": "W", "params": {"meas_noise": 4, "proc_noise": 0.01, "atr_period": 4, "factor": 1.05}},
    {"label": "Trend Strength (17)", "name": "trend_strength_gauge",   "tf": "W", "params": {"length": 17}},
    {"label": "MTF-EMA (12 6)",      "name": "mtf_ema_stoch",          "tf": "W", "params": {"ema_fast": 12, "ema_slow": 6}},
]


def _bar_open(idx, ndays, origin="2018-01-01"):
    return ((idx - pd.Timestamp(origin)).days % ndays) == 0


def _block_last(src, spec):
    """Renvoie (score, états_dernière_barre) pour un bloc, ou (nan, {}) si indispo."""
    if src is None or len(src) < 60:
        return float("nan"), {}
    score, _, mat = I.build_tpi(src, spec, entry=0.0, exit=0.0)
    last = src.index[-1]
    return float(score.loc[last]), {k: int(round(v)) for k, v in mat.loc[last].items()}


def evaluate(total, ethbtc, others_d=None):
    score, regime, mat = I.build_tpi(total, MTPI_SPEC, entry=ENTRY, exit=EXIT)
    last = total.index[-1]
    mtpi = float(score.loc[last]); reg = int(regime.loc[last])

    rot, rot_states = _block_last(ethbtc, ROT_SPEC)
    trash, trash_states = _block_last(others_d, TRASH_SPEC)
    ltpi, ltpi_states = _block_last(total, LTPI_SPEC)
    eth_over = (rot == rot and rot > 0)       # rot==rot : non-NaN
    small_ok = (trash == trash and trash > 0)

    if reg == 1:
        alloc = "LONG · ETH 80 / BTC 20" if eth_over else "LONG · BTC 80 / ETH 20"
    else:
        alloc = "CASH · Dominant Denominator"
    if reg == 1 and small_ok:
        alloc += "  + small-caps ≤20%"

    d = pd.DatetimeIndex([last])
    return {
        "date": str(last.date()),
        "mtpi": round(mtpi, 4),
        "regime": "LONG" if reg == 1 else "CASH",
        "rotation": None if rot != rot else round(rot, 4),
        "majeur": "ETH" if eth_over else "BTC",
        "trash": None if trash != trash else round(trash, 4),
        "small_caps": bool(reg == 1 and small_ok),
        "ltpi": None if ltpi != ltpi else round(ltpi, 4),
        "alloc": alloc,
        "states": {k: int(round(v)) for k, v in mat.loc[last].items()},
        "rot_states": rot_states,
        "trash_states": trash_states,
        "ltpi_states": ltpi_states,
        "new_bars": {"2D": bool(_bar_open(d, 2)[0]),
                     "3D": bool(_bar_open(d, 3)[0]),
                     "W":  last.weekday() == 0},
    }


# ---------------------------------------------------------------- réciprocité
SPEC_BY_BLOCK = {"MTPI": (MTPI_SPEC, "total"), "LTPI": (LTPI_SPEC, "total"), "ROT": (ROT_SPEC, "ethbtc"), "TRASH": (TRASH_SPEC, "others_d")}


def reciprocity(parity_df, series):
    """Compare les relevés TradingView (parity.csv) aux états calculés.
    parity.csv : colonnes date, block (MTPI/ROT/TRASH), label, state (-1/0/1)."""
    if parity_df is None or len(parity_df) == 0:
        return None
    out = {"by_block": {}, "mismatches": [], "n": 0, "ok": 0}
    cache = {}
    for blk, (spec, key) in SPEC_BY_BLOCK.items():
        src = series.get(key)
        if src is None:
            continue
        _, _, mat = I.build_tpi(src, spec, entry=0.0, exit=0.0)
        cache[blk] = mat
    for _, r in parity_df.iterrows():
        blk = str(r["block"]).upper()
        mat = cache.get(blk)
        if mat is None:
            continue
        day = pd.Timestamp(r["date"]).normalize()
        if r["label"] not in mat.columns or day not in mat.index:
            continue
        mine = int(round(mat.loc[day, r["label"]])); his = int(r["state"])
        ok = mine == his
        out["n"] += 1; out["ok"] += int(ok)
        b = out["by_block"].setdefault(blk, {"n": 0, "ok": 0})
        b["n"] += 1; b["ok"] += int(ok)
        if not ok:
            out["mismatches"].append({"date": str(day.date()), "block": blk,
                                      "label": r["label"], "mine": mine, "his": his})
    out["pct"] = round(100 * out["ok"] / out["n"], 1) if out["n"] else None
    return out
