# value_bet_europe (v2 : collecte automatique + compositions)

Outil d'apprentissage : estimer les probabilités 1X2 de matchs de football avec un modèle de Poisson,
les comparer aux cotes (marge retirée), détecter des « value bets » et tester le tout en backtest walk-forward
(chaque match est prédit uniquement avec le passé).

**Aucun gain n'est garanti.** Sur les données testées, le modèle perd contre le marché (voir Résultats).

## Utilisation
```
pip install -r requirements.txt
python download_data.py      # télécharge les données (GitHub) -> data/europe_matches.csv
python main.py               # backtest de tous les championnats -> results/
python main.py E0 SP1 F1     # certains championnats seulement
```

## Contenu
- `src/config.py` : 29 championnats (D1/D2 d'Angleterre, Écosse, Allemagne, Italie, Espagne, France, + Pays-Bas, Belgique, Portugal, Turquie, Grèce, pays nordiques, etc.).
- `src/model.py` : Poisson avec pondération des matchs récents et rétrécissement des équipes à peu de matchs.
- `src/value.py` : retrait de la marge (devig), avantage espéré, Kelly fractionné, plafond d'avantage anti-erreurs de modèle.
- `src/backtest.py` : backtest walk-forward, log loss / Brier modèle vs marché, simulation de paris (mise fixe et Kelly plafonné à 3 % de la bankroll).
- `results/` : `summary.csv` (par championnat), `predictions.csv`, `bets.csv`.

## Données
Source : dépôt GitHub xgabora/Club-Football-Match-Data-2000-2025 (résultats + cotes, issu de football-data.co.uk).
- Divisions 1 et 2 (et plus bas en Angleterre) de 2019 à début septembre 2026 ; les pays hors grandes ligues s'arrêtent fin 2024.
- Évaluation sur les matchs depuis juillet 2021 (la période avant sert d'entraînement).
- **Championnats féminins : non inclus**, aucune source gratuite avec cotes n'a été trouvée.
- Les cotes sont celles de la colonne `OddHome/OddDraw/OddAway` du jeu de données (pas de cotes Congobet).

## Résultats (backtest, 21 534 paris)
- Le marché prédit mieux que le modèle dans les 29 championnats (log loss et Brier plus bas).
- ROI à mise fixe : -12,7 % au total ; de -0,2 % (Norvège) à -26,7 % (Turquie).
- Mélanger le modèle avec le marché n'améliore pas la précision : tout poids donné au modèle dégrade le log loss.

## Pistes
1. Ajouter Elo, xG, repos/calendrier, blessures (le modèle actuel n'utilise que les buts).
2. Chercher des marchés moins efficaces (divisions basses, cotes tôt dans la semaine) avec de vraies cotes datées.
3. Suivi à blanc (sans argent) avant toute mise réelle.


---
## v2 : collecte automatique, stockage local, modèle basé sur les compositions

```
python update.py --list      # sources déclarées (actives / clé manquante / non testées)
python update.py             # met à jour la base locale data/store.db (incrémental, avec cache)
python update.py --status    # contenu de la base et derniers journaux
python main_lineup.py        # backtest Premier League : buts seuls vs buts + compositions vs marché
python formation_report.py   # formations qui gagnent, duels, joueurs par poste (StatsBomb, dont féminin)
```
- Les sources sont listées dans `src/sources.py` ; un collecteur par source dans `src/collectors/`.
- Chaque téléchargement est mis en cache (`data/cache/`), les erreurs sont journalisées, une source en panne ne bloque pas les autres, et le budget quotidien des API limitées (API-Football : 100/jour) est compté.
- Pour une mise à jour automatique, planifiez `python update.py` (cron / Planificateur de tâches).
- **Vérifiées** (téléchargement réussi) : xgabora (cotes), vaastav/FPL (joueurs, Premier League), StatsBomb Open Data.
- **Codées mais NON testées** (réseau bloqué là où le logiciel a été construit) : API FPL officielle (blessures), ESPN (compositions), API-Football (clé `API_FOOTBALL_KEY`). Testez-les chez vous avec `python update.py --only fpl_live espn`.
- Championnats féminins : formations et compositions via StatsBomb uniquement (pas de cotes, donc pas de backtest de paris).

### Résultats (backtest Premier League, 1 896 matchs, saisons 2021-22 à 2026-27)
| Modèle | log loss | Brier |
|---|---|---|
| Marché (cotes sans marge) | 0,9606 | 0,5706 |
| Buts seuls | 0,9815 | 0,5842 |
| Buts + compositions | 0,9840 | 0,5857 |

Ajouter la force de la composition alignée n'améliore pas la précision et ne bat pas le marché.
Rapport formations : l'avantage apparent du 4-3-3 vient surtout du niveau des équipes qui l'utilisent ;
une fois ce niveau retiré, l'effet propre des formations est faible (de l'ordre de ±0,1 but par match).


---
## Interface graphique (v3)
```
pip install -r requirements.txt
python app.py        # ouvre http://127.0.0.1:8765  (ou lancer.bat sous Windows, lancer.sh sous Linux/Mac)
```
Six pages : Accueil, Prédire un match (probabilités, scores, cotes, mise suggérée), Formations, Résultats des tests,
Suivi à blanc (paris virtuels), Sources & API (clés, test de connexion, mise à jour, paramètres de mise).
Les clés API sont enregistrées dans `data/settings.json` (sur votre ordinateur uniquement). Ne partagez pas ce fichier.

---
## Recherche d'un avantage (research.py)
`python research.py` teste, saison par saison et avec intervalle de confiance, si Elo, forme, tirs, corners, modèle de buts
ou meilleures cotes entre bookmakers améliorent les probabilités du marché. Résultat (voir `results/research.txt`) :
gain de précision d'environ 0,001 de log loss au mieux, très inférieur à la marge des bookmakers ; aucun pari simulé n'est rentable.

---
## v4 : comparateur de cotes et catalogue d'API gratuites
- Page **Comparer des cotes** : saisissez les cotes de votre bookmaker et celles d'une référence (Pinnacle). L'application retire la marge de la référence, calcule la cote juste, la marge en plus du bookmaker, l'avantage de chaque issue et la cote minimale à accepter. Les cotes de référence se chargent automatiquement avec une clé The Odds API (gratuite).
- Page **Sources & API** : chaque source affiche son offre gratuite et le lien pour obtenir une clé. Nouvelles sources codées (NON testées, sites inaccessibles là où le logiciel a été construit, mais vérifiées avec des réponses simulées) : `odds_api` (The Odds API), `football_data_org`, `thesportsdb`, `fd_pinnacle` (cotes Pinnacle historiques de football-data.co.uk).
- Les cotes historiques actuellement utilisées pour les tests sont celles de **Bet365** (pas Pinnacle). Lancez `python update.py --only fd_pinnacle` chez vous pour récupérer l'historique Pinnacle (table `ref_hist`), puis refaites les tests de précision avec Pinnacle comme référence.
