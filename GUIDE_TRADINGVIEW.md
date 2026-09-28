# Brancher TradingView sur le dashboard

Le script `tradingview/RSPS_TPI_AllInOne.pine` calcule **les 29 indicateurs** de tes 4 systèmes
directement dans TradingView, à partir du code original des scripts publics, et envoie chaque
système au relais à la clôture de sa bougie. Le dashboard les affiche (badge **TV**).

```
TradingView (1 script, 1 alerte) ──webhook──▶ relais Cloudflare ──▶ dashboard
                                                     │
                               robot GitHub quotidien ┘ archive + compare au moteur Python
```

## 1. Ajouter le script (une fois)

1. Ouvre un graphique **`CRYPTOCAP:TOTAL`** en **1D** (bougie journalière).
2. **Éditeur Pine** → *Nouvel indicateur* → **Cmd + A**, **Supprimer** (l'éditeur doit être vide),
   puis colle tout `RSPS_TPI_AllInOne.pine` → **Enregistrer** → **Ajouter au graphique**.
3. Le panneau affiche le score MTPI et un tableau : régime, MTPI, LTPI, Rotation, Small-caps.
   Compare avec ton système habituel.

Le script va lui-même chercher ETHBTC, OTHERS.D et les timeframes 2D / 3D / hebdo : rien à
brancher. Pourquoi 1D : les bougies 2D, 3D et hebdo se clôturent toutes un jour donné, le script
envoie chaque système le jour même de sa clôture (le délai d'exécution compte beaucoup, cf. test
de robustesse).

## 2. Créer l'alerte (une seule)

1. **Alerte** (en haut) → **Condition** : `RSPS TPI` → **`Any alert() function call`**.
2. **Expiration** : *Illimitée*.
3. **Notifications** → coche **Webhook URL** → colle l'adresse du fichier `SECRET.txt`.
4. **Créer**.

Au premier passage (à la clôture journalière suivante), le script envoie les 4 systèmes ;
ensuite, chacun à la clôture de sa propre bougie. Les cartes du dashboard passent de **Py** à **TV**.

## Limite : Z-Score Deviation Fusion

Cet indicateur (RAKIQUANT) est **protégé** : son code n'est pas public. Il est remplacé par un
z-score standard (MTPI 30 20 et Rotation 27 18), soit 2 indicateurs sur 29.
Pour le MTPI, tu peux utiliser le vrai : graphique TOTAL en **2D**, ajoute Z-Score Deviation
Fusion (30 20), puis dans les paramètres de RSPS TPI coche « utiliser le vrai Z-Score » et choisis
sa sortie dans **Source Z-Score**.

## Vérifier

- `https://rsps-relay.timothekintgen1.workers.dev/state` : état combiné reçu de TradingView.
- `https://rsps-relay.timothekintgen1.workers.dev/log` : dernières alertes reçues.
- Chaque nuit, le robot GitHub ajoute les états TradingView à `seed/parity.csv` : le score de
  fiabilité du moteur Python se remplit tout seul.

`tradingview/RSPS_Relais.pine` (branchement manuel indicateur par indicateur) reste disponible
si tu préfères utiliser tes propres instances d'indicateurs.
