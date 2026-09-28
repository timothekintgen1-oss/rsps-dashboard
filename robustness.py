#!/usr/bin/env python3
"""
robustness.py — La stratégie tient-elle quand on la bouscule ?

Uniquement sur l'historique réel (exports TradingView du seed, sans comblement),
stratégie « RSPS cash » (MTPI -> LONG/CASH, rotation ETH/BTC 80/20).

  1. Par période       : la perf vient-elle d'une seule année ?
  2. Paramètres ±25 %  : 60 tirages aléatoires des réglages de chaque indicateur.
                         Si la spec actuelle est tout en haut de la distribution -> sur-ajustement.
  3. Indicateurs       : on retire chaque indicateur un par un ; puis 60 sous-ensembles
                         aléatoires de 5 indicateurs sur 10.
  4. Seuils            : entrée/sortie de 0 à 0,4.
  5. Exécution         : 1 à 3 barres de retard, frais x1 à x5.

Écrit docs/robustness.json (lu par le dashboard) et imprime un résumé.
"""
import json, os, random
import numpy as np, pandas as pd
import data_sources as ds, indicators as I, strategy as st
from backtest import _metrics, FEE

HERE = os.path.dirname(os.path.abspath(__file__))
rng = random.Random(42)


def load():
    total, ethbtc = ds._load_seed("total.csv"), ds._load_seed("ethbtc.csv")
    def contiguous_end(df):                          # s'arrête au premier trou > 3 j
        gaps = df.index.to_series().diff().dt.days
        big = gaps[(gaps > 3) & (df.index > "2019-12-31")]
        return big.index[0] - pd.Timedelta(days=1) if len(big) else df.index.max()
    end = min(contiguous_end(total), contiguous_end(ethbtc))
    return {"total": total.loc[:end], "ethbtc": ethbtc.loc[:end],
            "btc": ds.binance_daily("BTCUSDT").loc[:end], "eth": ds.binance_daily("ETHUSDT").loc[:end]}


_ROT_CACHE = {}
def rotation_weights(S, rot_spec):
    key = json.dumps(rot_spec, sort_keys=True)
    if key not in _ROT_CACHE:
        es, _, _ = I.build_tpi(S["ethbtc"], rot_spec, entry=0.0, exit=0.0)
        _ROT_CACHE[key] = es
    return _ROT_CACHE[key]


def simulate(S, mtpi_spec=st.MTPI_SPEC, rot_spec=st.ROT_SPEC, entry=st.ENTRY, exit=st.EXIT, lag=1, fee=FEE):
    total = S["total"]; idx = total.index
    _, regime, _ = I.build_tpi(total, mtpi_spec, entry=entry, exit=exit)
    long = (regime.reindex(idx).ffill() > 0).astype(float)
    es = rotation_weights(S, rot_spec).reindex(idx, method="ffill").fillna(0)
    we = pd.Series(np.where(es > 0, 0.8, 0.2), index=idx); wb = 1 - we
    rb = S["btc"]["close"].reindex(idx, method="ffill").pct_change().fillna(0)
    re = S["eth"]["close"].reindex(idx, method="ffill").pct_change().fillna(0)
    lg, we, wb = long.shift(lag).fillna(0), we.shift(lag).fillna(0), wb.shift(lag).fillna(0)
    turn = (lg * we).diff().abs().fillna(0) + (lg * wb).diff().abs().fillna(0)
    r = lg * (we * re + wb * rb) - turn * fee
    start = S["btc"].index.min()                     # BTC Binance dispo -> départ commun
    return r.loc[start:], rb.loc[start:]


def perturb(spec, pct=0.25):
    out = []
    for s in spec:
        p = dict(s.get("params", {}))
        for k, v in p.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            f = 1 + rng.uniform(-pct, pct)
            p[k] = max(2, int(round(v * f))) if isinstance(v, int) else v * f
        out.append({**s, "params": p})
    return out


def pctile(x, arr):
    arr = [a for a in arr if a is not None]
    return round(100 * sum(a <= x for a in arr) / len(arr)) if arr else None


def main():
    S = load()
    base, btc = simulate(S)
    mb = _metrics(base); mbtc = _metrics(btc)
    print(f"Base    : CAGR {mb['cagr']}%  Sharpe {mb['sharpe']}  DD {mb['dd']}%  ×{mb['x']}   (BTC : CAGR {mbtc['cagr']}%, DD {mbtc['dd']}%)")

    # 1. périodes
    periods = []
    for y in sorted(set(base.index.year)):
        m, mbt = _metrics(base, (f"{y}-01-01", f"{y}-12-31")), _metrics(btc, (f"{y}-01-01", f"{y}-12-31"))
        if m: periods.append({"period": str(y), "rsps": m["perf"], "btc": mbt["perf"], "dd": m["dd"]})
    halves = [("2018-01-01", "2021-12-31"), ("2022-01-01", "2026-12-31")]
    for a, b in halves:
        m = _metrics(base, (a, b)); periods.append({"period": f"{a[:4]}–{b[:4]}", "rsps": m["perf"], "sharpe": m["sharpe"], "dd": m["dd"],
                                                     "btc": _metrics(btc, (a, b))["perf"]})
    print("Périodes:", ", ".join(f"{p['period']} {p['rsps']:+}% (BTC {p['btc']:+}%)" for p in periods))

    # 2. paramètres ±25 %
    params = []
    for i in range(60):
        r, _ = simulate(S, mtpi_spec=perturb(st.MTPI_SPEC), rot_spec=perturb(st.ROT_SPEC))
        params.append(_metrics(r))
    sh = [m["sharpe"] for m in params]; cg = [m["cagr"] for m in params]; dd = [m["dd"] for m in params]
    print(f"Params  : Sharpe médian {np.median(sh):.2f} [p10 {np.percentile(sh,10):.2f} – p90 {np.percentile(sh,90):.2f}]"
          f"  -> la spec actuelle est au {pctile(mb['sharpe'], sh)}e centile")

    # 3a. retrait d'un indicateur
    loo = []
    for s in st.MTPI_SPEC:
        r, _ = simulate(S, mtpi_spec=[x for x in st.MTPI_SPEC if x is not s])
        m = _metrics(r); loo.append({"label": s["label"], "sharpe": m["sharpe"], "cagr": m["cagr"], "dd": m["dd"],
                                      "delta_sharpe": round(m["sharpe"] - mb["sharpe"], 2)})
    loo.sort(key=lambda d: d["delta_sharpe"])
    print("Retrait :", ", ".join(f"{d['label']} {d['delta_sharpe']:+}" for d in loo))
    # 3b. sous-ensembles de 5
    subs = []
    for i in range(60):
        r, _ = simulate(S, mtpi_spec=rng.sample(st.MTPI_SPEC, 5)); subs.append(_metrics(r))
    ssh = [m["sharpe"] for m in subs]
    print(f"5 sur 10: Sharpe médian {np.median(ssh):.2f} [p10 {np.percentile(ssh,10):.2f} – p90 {np.percentile(ssh,90):.2f}]")

    # 4. seuils
    thr = []
    for t in (0.0, 0.1, 0.2, 0.3, 0.4):
        r, _ = simulate(S, entry=t, exit=t); m = _metrics(r)
        thr.append({"thr": t, "sharpe": m["sharpe"], "cagr": m["cagr"], "dd": m["dd"]})
    print("Seuils  :", ", ".join(f"{d['thr']}: Sh {d['sharpe']}" for d in thr))

    # 5. exécution
    exe = []
    for lag in (1, 2, 3):
        for fm in (1, 3, 5):
            r, _ = simulate(S, lag=lag, fee=FEE * fm); m = _metrics(r)
            exe.append({"lag": lag, "fee_x": fm, "sharpe": m["sharpe"], "cagr": m["cagr"], "dd": m["dd"]})
    print("Exéc.   :", ", ".join(f"lag{d['lag']}/fx{d['fee_x']}: Sh {d['sharpe']}" for d in exe))

    out = {"as_of": str(base.index[-1].date()), "start": str(base.index[0].date()),
           "base": mb, "btc": mbtc, "periods": periods,
           "params": {"n": len(params), "sharpe": sorted(sh), "cagr": sorted(cg), "dd": sorted(dd),
                      "base_pctile": pctile(mb["sharpe"], sh)},
           "leave_one_out": loo,
           "subsets5": {"n": len(subs), "sharpe": sorted(ssh), "base_pctile": pctile(mb["sharpe"], ssh)},
           "thresholds": thr, "execution": exe}
    json.dump(out, open(os.path.join(HERE, "docs", "robustness.json"), "w"), indent=1, ensure_ascii=False)
    print("-> docs/robustness.json")


if __name__ == "__main__":
    main()
