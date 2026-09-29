#!/usr/bin/env python3
"""runner.py — Boucle quotidienne du bot RSPS (régime + rotation + trash + réciprocité)."""
import os, json
import pandas as pd
import data_sources as ds
import strategy as st

HERE = os.path.dirname(__file__)
STATE_DIR = os.path.join(HERE, "state")
STATE_JSON = os.path.join(STATE_DIR, "state.json")
HISTORY = os.path.join(STATE_DIR, "history.csv")
DOCS_JSON = os.path.join(HERE, "docs", "state.json")   # copie pour GitHub Pages
PARITY = os.path.join(HERE, "seed", "parity.csv")
CONFIG = os.path.join(HERE, "docs", "config.json")     # {"relay": "https://…workers.dev"}


def notify(msg):
    tok, chat = os.getenv("TG_TOKEN"), os.getenv("TG_CHAT")
    if not (tok and chat):
        print("[notify] (Telegram non configuré)\n" + msg); return
    import requests
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data={"chat_id": chat, "text": msg, "parse_mode": "HTML"}, timeout=20)
    except Exception as e:
        print(f"[notify] échec : {e}")


def sync_tradingview():
    """Récupère les signaux TradingView (relais Cloudflare) : archive docs/tv_state.json
    et ajoute chaque état reçu à seed/parity.csv -> la réciprocité s'alimente seule."""
    try:
        relay = json.load(open(CONFIG)).get("relay", "").rstrip("/")
    except Exception:
        relay = ""
    if not relay:
        return
    import requests
    try:
        tv = requests.get(relay + "/state", timeout=30).json()
    except Exception as e:
        print(f"[tv] relais injoignable : {e}"); return
    if not tv.get("date"):
        print("[tv] aucun signal TradingView reçu pour l'instant"); return
    json.dump(tv, open(os.path.join(HERE, "docs", "tv_state.json"), "w"), indent=2, ensure_ascii=False)
    rows = [{"date": v["date"], "block": sys, "label": lab, "state": st}
            for sys, info in tv.get("systems", {}).items()
            for v in info.get("tfs", {}).values()
            for lab, st in v.get("states", {}).items()]
    if rows:
        old = pd.read_csv(PARITY) if os.path.exists(PARITY) else pd.DataFrame(columns=["date","block","label","state"])
        allp = pd.concat([old, pd.DataFrame(rows)]).drop_duplicates(["date","block","label"], keep="last")
        allp.sort_values(["date","block","label"]).to_csv(PARITY, index=False)
    print(f"[tv] {tv['date']}  {tv.get('regime')}  MTPI={tv.get('mtpi')}  ({len(rows)} états archivés)")


def exposure(res, alts_res):
    """Exposition cible par actif (fractions du portefeuille), pages 1 à 5 du classeur."""
    if res["regime"] != "LONG":
        return {"CASH": 1.0}
    sel = (alts_res or {}).get("selected") or []
    trash = res.get("trash_pct", 0.0) if sel else 0.0     # aucun token retenu : reste en majeurs
    cons = 1.0 - trash
    maj, mino = ("ETH", "BTC") if res["majeur"] == "ETH" else ("BTC", "ETH")
    out = {maj: round(0.8 * cons, 4), mino: round(0.2 * cons, 4)}
    for t in sel:
        out[t] = round(trash / len(sel), 4)
    return out


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    sync_tradingview()
    series = ds.get_series()
    res = st.evaluate(series["total"], series.get("ethbtc"), series.get("others_d"))
    try:
        import alts
        alts_res = alts.run(series["btc"], series["eth"])
        json.dump(alts_res, open(os.path.join(HERE, "docs", "alts.json"), "w"), indent=2, ensure_ascii=False)
        print(f"  alts retenus : {', '.join(alts_res['selected']) or 'aucun'}")
    except Exception as e:
        print(f"[alts] {e}"); alts_res = None
    res["exposure"] = exposure(res, alts_res)
    res["reconstructed"] = series.get("reconstructed") or {}

    # réciprocité avec tes relevés TradingView (seed/parity.csv), si fourni
    if os.path.exists(PARITY):
        try:
            res["reciprocity"] = st.reciprocity(pd.read_csv(PARITY), series)
        except Exception as e:
            print(f"[recip] {e}")

    prev = json.load(open(STATE_JSON)) if os.path.exists(STATE_JSON) else {}
    if prev.get("date") and res["date"] < prev["date"]:
        # CoinGecko indispo -> calcul sur le seed seul, plus ancien que l'état publié :
        # on ne l'écrase pas (sinon faux changement de régime + fausse alerte).
        print(f"[skip] état calculé au {res['date']} plus ancien que le publié "
              f"({prev['date']}) — rien n'est mis à jour.")
        return
    changed = prev.get("regime") != res["regime"]

    json.dump(res, open(STATE_JSON, "w"), indent=2, ensure_ascii=False)
    json.dump(res, open(DOCS_JSON, "w"), indent=2, ensure_ascii=False)   # pour le dashboard live

    # comparatif backtest auto-actualisé -> docs/backtest.json
    try:
        import backtest as bt
        bt_res = bt.run(series)
        json.dump(bt_res, open(os.path.join(HERE, "docs", "backtest.json"), "w"), indent=2, ensure_ascii=False)
        mw = bt_res["metrics_window"]
        if mw.get("raw"):
            print(f"  backtest fenêtre prof : Raw {mw['raw']['perf']:+}% / DD {mw['raw']['dd']}% | "
                  f"Gold {mw['gold']['perf']:+}% / DD {mw['gold']['dd']}%")
    except Exception as e:
        print(f"[backtest] {e}")
    pd.DataFrame([{k: res[k] for k in ("date","mtpi","regime","rotation","majeur","trash","alloc")}]) \
        .to_csv(HISTORY, mode="a", header=not os.path.exists(HISTORY), index=False)

    arrow = "🟢" if res["regime"] == "LONG" else "🔴"
    print(f"{res['date']}  {arrow} {res['regime']}  MTPI={res['mtpi']:+.3f}  "
          f"rot={res['rotation']}  trash={res['trash']}  -> {res['alloc']}")
    if res.get("reciprocity", {}).get("pct") is not None:
        print(f"  réciprocité : {res['reciprocity']['pct']}% "
              f"({res['reciprocity']['ok']}/{res['reciprocity']['n']})")

    bars = [tf for tf in ("2D","3D","W") if res["new_bars"][tf]]
    if os.getenv("NOTIFY","change") == "always" or changed or bars:
        head = "♻️ <b>RÉGIME CHANGE</b>" if changed else "🕯️ Nouvelle bougie"
        lines = [f"{head} — {res['date']}",
                 f"{arrow} <b>{res['regime']}</b>  ·  MTPI {res['mtpi']:+.3f}",
                 f"Allocation : <b>{res['alloc']}</b>"]
        if res["rotation"] is not None:
            lines.append(f"Rotation {res['rotation']:+.2f} → {res['majeur']}")
        if res["trash"] is not None:
            lines.append(f"Trash {res['trash']:+.2f} → {res.get('trash_pct', 0):.0%} en alts")
        lines.append("Exposition : " + " · ".join(f"{k} {v:.0%}" for k, v in res["exposure"].items()))
        if bars:
            lines.append("Ouverture TF : " + ", ".join(bars))
        notify("\n".join(lines))


if __name__ == "__main__":
    main()
