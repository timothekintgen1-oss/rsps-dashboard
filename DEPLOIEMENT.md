# Déploiement du dashboard RSPS — pas à pas

Ce dossier contient **tout** ce qu'il faut : le dashboard (`docs/`), le bot quotidien (`runner.py`, `data_sources.py`, `strategy.py`, `indicators.py`, `backtest.py`), les données de départ (`seed/`) et l'automatisation (`.github/workflows/rsps.yml`).

Une fois déployé, tu obtiens :
- une page web publique (ou privée) avec tes boussoles + le comparatif, à jour ;
- un robot qui **chaque jour** récupère la donnée, recalcule tout, et met la page à jour **sans toi** ;
- (option) une alerte Telegram à chaque changement de régime.

Compte ~10 minutes. Aucune compétence technique requise si tu suis l'**Option A** (glisser-déposer).

---

## Étape 0 — Ce que tu as déjà

Tu as créé un repo vide sur GitHub (par ex. `rsps-dashboard`). Garde son onglet ouvert. Note son adresse, du type :
`https://github.com/TON_PSEUDO/rsps-dashboard`

> Repo **privé** = parfait (le dashboard restera accessible via son lien Pages même en privé). Repo **public** = ça marche aussi.

---

## Étape 1 — Mettre les fichiers dans le repo

### Option A — Glisser-déposer (le plus simple, sans installer quoi que ce soit)

1. Sur la page de ton repo vide, clique sur le lien **« uploading an existing file »** (ou bouton **Add file → Upload files**).
2. Ouvre le dossier `rsps_bot` sur ton ordinateur. **Sélectionne tout ce qu'il contient** (les fichiers `.py`, les dossiers `docs`, `seed`, `state`, `.github`, le `requirements.txt`, etc.) et **glisse-les** dans la zone d'upload de GitHub.
   - ⚠️ Le dossier `.github` commence par un point : il est parfois masqué. Sur Mac, dans le Finder, fais `Cmd + Maj + .` pour afficher les fichiers cachés, puis glisse-le aussi. **Il est indispensable** (c'est lui qui contient l'automatisation).
3. En bas, dans **Commit changes**, laisse le message par défaut et clique **Commit changes**.
4. Rafraîchis : tu dois voir `docs/`, `seed/`, `runner.py`, `.github/`, etc. dans le repo.

### Option B — En ligne de commande (si tu préfères)

Depuis le dossier `rsps_bot` sur ton ordinateur, remplace `TON_PSEUDO` puis colle :

```bash
git init
git add .
git commit -m "RSPS dashboard"
git branch -M main
git remote add origin https://github.com/TON_PSEUDO/rsps-dashboard.git
git push -u origin main
```

---

## Étape 2 — Activer la page web (GitHub Pages)

1. Dans ton repo : onglet **Settings** (en haut à droite).
2. Menu de gauche : **Pages**.
3. Section **Build and deployment → Source** : choisis **Deploy from a branch**.
4. Juste en dessous, **Branch** : sélectionne **`main`**, et dans le second menu choisis le dossier **`/docs`**. Clique **Save**.
5. Attends ~1 minute, rafraîchis la page : GitHub affiche en haut un encadré vert avec l'adresse de ton site :
   `https://TON_PSEUDO.github.io/rsps-dashboard/`

Ouvre ce lien → **ton dashboard s'affiche**, figé à la dernière donnée fournie (30 juin). L'étape suivante le rend vivant.

---

## Étape 3 — Activer le robot quotidien (GitHub Actions)

1. Dans ton repo : onglet **Actions**.
2. Si GitHub demande une confirmation, clique **« I understand my workflows, go ahead and enable them »**.
3. Dans la liste à gauche, clique sur le workflow **« RSPS daily »**.
4. Bouton **Run workflow** (à droite) → **Run workflow** : ça lance un premier passage **tout de suite** (sinon il attendrait 00 h 15 UTC).
5. Au bout d'une minute, une ligne verte ✅ apparaît. Clique dessus pour voir le journal : tu dois lire le régime du jour, le backtest, etc.
6. Reviens sur ton lien Pages et rafraîchis : la **date en haut à droite** doit maintenant correspondre à **aujourd'hui**, et le pastille indiquer « actualisé en direct ».

> À partir de là, c'est automatique : chaque jour à **00 h 15 UTC** (~02 h 15 heure de Paris l'été), le robot tourne seul et met la page à jour. Tu n'as plus rien à faire.

---

## Étape 4 — (Optionnel) Alertes Telegram

Pour recevoir un message à chaque changement de régime :

1. Sur Telegram, parle à **@BotFather** → `/newbot` → suis les instructions → il te donne un **token** (une longue chaîne).
2. Récupère ton **chat ID** : parle à **@userinfobot**, il te renvoie ton `Id` (un nombre).
3. Dans ton repo : **Settings → Secrets and variables → Actions → New repository secret**. Crée deux secrets :
   - Nom `TG_TOKEN`, valeur = le token de BotFather.
   - Nom `TG_CHAT`, valeur = ton chat ID.
4. C'est tout. Le prochain run t'enverra un message si le régime bouge (ou à chaque bougie).

> Sans ces secrets, le bot fonctionne quand même : il écrit juste les alertes dans le journal des Actions au lieu de Telegram.

---

## Ce que fait le robot chaque jour (mode autonome)

- **Prix BTC / ETH / ETHBTC** : récupérés sur **Binance** (fiable, identique à ta grille).
- **TOTAL & OTHERS.D** : reconstitués via **CoinGecko** (capi globale + dominance hors top 10).
- **Or** : via **Stooq**.
- Il repart de tes exports TradingView (`seed/`) comme historique de base, ajoute le point du jour, recalcule les 4 systèmes + le backtest, et pousse `docs/state.json` + `docs/backtest.json` que lit la page.

⚠️ **Petit écart de source assumé** : la capi CoinGecko n'a pas exactement le même univers que `CRYPTOCAP` de TradingView. Sur les nouveaux points quotidiens, de légères différences sont possibles (surtout sur OTHERS.D). Ton historique reste tes vraies données TradingView ; c'est uniquement le flux quotidien qui a cette approximation. Si un jour tu veux tout re-caler exactement, il suffit de remplacer les fichiers de `seed/` par un nouvel export TradingView à jour (glisser-déposer, comme à l'étape 1).

---

## Dépannage rapide

| Symptôme | Cause probable | Solution |
|---|---|---|
| La page Pages affiche 404 | Pages pas encore prêt, ou mauvais dossier | Attends 1-2 min ; vérifie Settings → Pages = branche `main`, dossier `/docs` |
| Le dashboard s'affiche mais la date ne bouge pas | Aucun run d'Action n'a encore eu lieu | Onglet Actions → Run workflow (étape 3) |
| L'onglet Actions est vide | Le dossier `.github` n'a pas été uploadé | Ré-uploade le dossier `.github` (fichiers cachés, voir étape 1) |
| Le run échoue en rouge | API momentanément indisponible | Relance « Run workflow » ; le bot retombe sur le seed si CoinGecko est down |
| Réciprocité à 4/6 | Échantillon de test par défaut | Remplace `seed/parity.csv` par tes vrais relevés (une ligne par indicateur : `date,block,indicator,value`) |

---

## Structure du dossier (pour référence)

```
rsps_bot/
├── docs/                ← la page web (Pages sert ce dossier)
│   ├── index.html          le dashboard (boussoles + comparatif)
│   ├── state.json          état du jour (régime, jauges) — écrit par le bot
│   └── backtest.json       courbes + métriques — écrit par le bot
├── seed/                ← historique de base (tes exports TradingView) + parity.csv
├── state/               ← journal (history.csv) + dernier état
├── indicators.py        moteur des 14 indicateurs
├── strategy.py          MTPI · LTPI · Rotation · Trash + allocation
├── backtest.py          courbes d'équité + métriques (annualisation robuste au pas de temps)
├── data_sources.py      récupération autonome des données (Binance / CoinGecko / Stooq)
├── runner.py            boucle quotidienne (appelée par l'Action)
├── requirements.txt     dépendances Python
└── .github/workflows/rsps.yml   planification quotidienne
```
