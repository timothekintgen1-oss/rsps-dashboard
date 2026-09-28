# Brancher TradingView sur le dashboard

TradingView devient la source des signaux : tes vrais indicateurs, sur les vraies
données CRYPTOCAP. Le script `tradingview/RSPS_Relais.pine` lit leurs états et les
envoie au relais à chaque clôture de bougie ; le dashboard les affiche (badge **TV**).

```
TradingView (tes indicateurs) ──alerte webhook──▶ relais Cloudflare ──▶ dashboard
                                                        │
                                  robot GitHub quotidien ┘ archive + compare au moteur Python
```

## 1. Ajouter le script relais (une fois)

1. TradingView → **Éditeur Pine** → *Ouvrir* → *Nouvel indicateur*.
2. Colle tout le contenu de `tradingview/RSPS_Relais.pine`, **Enregistrer** sous « RSPS Relais ».

## 2. Un graphique par système

| Graphique | Timeframe | Système (réglage du script) | Indicateurs à brancher (nom exact) |
|---|---|---|---|
| `CRYPTOCAP:TOTAL` | 2D | MTPI | EWO (5 32) · MTF-EMA (7 19) · Z-Score (30 20) · DFT (6 29) · WonderTrend (20) · MA Band (20 5) · LNL (Tight) · DEGA (21..) |
| `CRYPTOCAP:TOTAL` | 3D | MTPI | Sebastine (9 6) · TrendChange (11 35) |
| `CRYPTOCAP:TOTAL` | 1W | LTPI | LNL (Normal) · Sebastine (9 10) · EWO (4 26) · DFT (3 20) · AGMA (23 20) · TrendChange (40 60) · Kalman Hull (4..) · Trend Strength (17) · MTF-EMA (12 6) |
| `BINANCE:ETHBTC` | 2D | ROT | DEGA (23..) · Sebastine (16 15) · TrendChange (16 40) · Z-Score (27 18) · WonderTrend (def) |
| `CRYPTOCAP:OTHERS.D` | 3D | TRASH | DFT (14 14) · EWO (7 26) · MTF-EMA (12 13) · Trend Strength (21) · Kalman Hull (3..) |

Les deux instances MTPI (2D et 3D) sont fusionnées par le relais : le score MTPI est la
moyenne des 10 indicateurs, exactement comme dans `strategy.py`.

Sur chaque graphique :

1. Ajoute tes indicateurs habituels, avec leurs réglages.
2. Ajoute **RSPS Relais**, puis ouvre ses paramètres :
   - **Système** : celui du tableau.
   - Pour chaque indicateur : coche la case, écris le **nom exact** du tableau (il sert à
     comparer avec le moteur Python), choisis dans **Source** la sortie de l'indicateur
     (la ligne ou l'histogramme qui porte son signal), et la **Lecture** :
     - `Valeur > 0` : oscillateur / histogramme, positif = haussier ;
     - `Prix > ligne` : ligne de tendance (supertrend, bande…), prix au-dessus = haussier ;
     - `État ±1` : l'indicateur sort déjà 1 / -1.
     - `Inverser` si le sens est à l'envers.
3. Vérifie le petit tableau en haut à droite : chaque indicateur doit afficher le même
   état (+1 / -1) que sa couleur sur le graphique. **C'est l'étape la plus importante.**

> Si un indicateur ne sort qu'une couleur (aucune valeur exploitable dans *Source*), il
> faut ajouter un `plot()` de son état dans son code, ou le signaler pour qu'on l'adapte.

## 3. Créer l'alerte (une par graphique)

1. Clic droit sur le graphique → **Ajouter une alerte**.
2. **Condition** : `RSPS Relais` → **`Any alert() function call`**.
3. **Expiration** : *Illimitée* (sinon l'alerte s'arrête sans prévenir).
4. Onglet **Notifications** → coche **Webhook URL** et colle l'adresse du relais
   (fichier `relay/SECRET.txt` sur ton Mac, de la forme `https://rsps-relay…workers.dev/hook/…`).
5. Le message est généré par le script : ne le modifie pas.

À la clôture de bougie suivante, la carte correspondante du dashboard passe de **Py** à **TV**.

## Vérifier

- `https://<relais>/state` : état combiné reçu de TradingView.
- `https://<relais>/log` : dernières alertes reçues.
- Chaque nuit, le robot GitHub ajoute les états TradingView à `seed/parity.csv` :
  le score de fiabilité du moteur Python se remplit tout seul.
