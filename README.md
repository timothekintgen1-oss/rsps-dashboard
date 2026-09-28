# RSPS Bot — moteur de régime autonome + dashboard live

Recalcule chaque jour le **MTPI / régime / rotation ETHBTC / trash OTHERS.D / allocation**
sur données réelles, vérifie la **réciprocité** avec tes relevés TradingView, publie un
**dashboard live** (GitHub Pages) et te notifie. Tourne tout seul une fois déployé.

---

## Deux voies (complémentaires)

| | Voie A — Pine + webhook | Voie B — bot Python (ce dossier) |
|---|---|---|
| Indicateurs | **tes vrais** (TradingView) — exacts | mes ports (8–9/10 fidèles) |
| Données | CRYPTOCAP natif | seed TradingView + Binance/Stooq/CoinGecko |
| Exécution | serveur TradingView 24/7 | GitHub Actions (cron quotidien) |
| Rôle | **source de vérité des signaux** | log + dashboard live + automatisation |

### ⚠ Fidélité (Voie B)
DEGA exact (1 date sur le fil) · WonderTrend PSAR approché · Z-Score proxy ·
TOTAL/OTHERS.D CoinGecko ≠ exactement CRYPTOCAP · LTPI on-chain (5/14) non inclus.
→ **Pour décider, la Voie A fait foi.** La réciprocité (ci-dessous) chiffre l'écart en continu.

---

## Les 3 séries à fournir (seed)

Sur TradingView, exporte en 1D *Exporter les données du graphe* (CSV `time,open,high,low,close`) :

| Fichier | Symbole TradingView | Bloc | Obligatoire |
|---|---|---|---|
| `seed/total.csv`    | `CRYPTOCAP:TOTAL`   | MTPI     | **oui** |
| `seed/others_d.csv` | `CRYPTOCAP:OTHERS.D`| Trash    | pour activer le Trash |
| `seed/ethbtc.csv`   | `BINANCE:ETHBTC` (ou ton ratio)| Rotation | optionnel (sinon Binance auto) |

BTC / ETH / or se téléchargent seuls. Chaque jour, le bot **append** la valeur du jour
à ces séries (CoinGecko pour TOTAL/OTHERS.D, Binance pour ETHBTC).

---

## Réciprocité (vérifier la cohérence avec ton système)

Reporte tes relevés TradingView dans **`seed/parity.csv`** :
```
date,block,label,state
2024-11-10,MTPI,EWO (5 32),1
2024-07-25,MTPI,DEGA (21..),-1
2024-07-25,MTPI,TrendChange (11 35),0
```
- `block` ∈ MTPI / ROT / TRASH · `label` = libellé exact (voir `strategy.py`) · `state` ∈ -1/0/1.
- À chaque run, le bot recalcule ces états et publie le **% de concordance** + la liste des
  écarts dans `state.json` → affichés dans le dashboard (panneau « Réciprocité »).
- Plus tu ajoutes de relevés (surtout en range), plus la validation est solide.

---

## Déploiement (≈ 10 min)

1. **Seed** : dépose au moins `seed/total.csv` (+ `others_d.csv`, `ethbtc.csv`, `parity.csv`).
2. **Repo GitHub privé** : pousse ce dossier.
3. **Dashboard live (Pages)** : *Settings → Pages → Source = Deploy from a branch →
   branche `main`, dossier `/docs`*. Le bot écrit `docs/state.json` à chaque run ;
   la page le lit et affiche le régime réel. URL : `https://<user>.github.io/<repo>/`.
4. **Telegram** (option) : `TG_TOKEN` + `TG_CHAT` dans *Settings → Secrets → Actions*.
5. **Actions** : onglet *Actions* → activer. Cron 00:15 UTC ; *Run workflow* pour tester.

### Local
```bash
pip install -r requirements.txt
python runner.py     # calcule, écrit state/state.json + docs/state.json
```

---

## Voie A — Webhook Pine
Mets `RSPS_TPI_Dashboard.pine` sur le graphe, connecte tes indicateurs (champ *Source*),
crée une alerte **« Any alert() function call »** + Webhook URL. Payload :
```json
{"ticker":"CRYPTOCAP:TOTAL","tf":"2D","regime":"LONG","mtpi":0.6,"rotation":0.2,
 "majeur":"ETH","alloc":"LONG · ETH 80 / BTC 20","time":1717977600000}
```
Une alerte par TF/symbole (TOTAL 2D, TOTAL 3D, ETHBTC 2D, OTHERS.D 3D…).

---

## Fichiers
```
indicators.py     moteur (14 indicateurs)
strategy.py       spec calibrée MTPI/ROT/TRASH + régime + réciprocité
data_sources.py   seed + Binance/Stooq/CoinGecko
runner.py         boucle quotidienne + notif + publication docs/state.json
docs/index.html   dashboard LIVE (GitHub Pages)
seed/             total.csv, others_d.csv, ethbtc.csv, parity.csv
state/            state.json + history.csv (générés)
.github/workflows/rsps.yml   planificateur
```
