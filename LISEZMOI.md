# Value Bet : application Android (PWA) avec mise à jour automatique

## Ce que fait le site tout seul (GitHub Actions, gratuit)
- **Chaque jour à 06:00 (Brazzaville)** : retélécharge l'historique de résultats et cotes, recalcule les modèles, charge les cotes de référence si la clé The Odds API est enregistrée.
- **Toutes les 20 minutes (09:00 à 23:00 Brazzaville)** : lit les matchs (ESPN), enregistre la composition et la formation dès qu'elles sont publiées (environ 1 h avant le match), fait la prédiction, enregistre les scores et mesure la fiabilité.
- Le résultat est écrit dans `data/snapshot.json` : l'application l'affiche dans « Matchs du jour ». Les compositions et prédictions sont gardées dans `engine/data/live.db`, qui grossit chaque jour.

## Mise en route (une seule fois)
1. Fusionnez la demande de modification, puis ouvrez l'onglet **Actions** du dépôt. Si GitHub demande d'activer les workflows, acceptez.
2. Choisissez « Value Bet - mise à jour automatique » > **Run workflow** > mode `full` > Run. C'est le premier essai réel : ouvrez l'exécution pour voir si chaque étape est verte.
3. Facultatif : Settings > Secrets and variables > Actions > New repository secret, nom `ODDS_API_KEY`, valeur votre clé gratuite The Odds API (500 crédits par mois).

## Limites à connaître
- L'API d'ESPN n'est pas officielle : le format ou les codes de championnat peuvent changer. Rien n'a pu être testé avec le vrai service avant la mise en ligne.
- GitHub peut décaler un horaire de plusieurs minutes, et désactive les tâches planifiées d'un dépôt resté 60 jours sans activité.
- La formation est enregistrée et affichée, mais ne modifie pas encore les probabilités : les tests n'ont montré aucun gain. La section « Fiabilité mesurée » dira avec le temps si les prédictions battent le marché.

## Essai sur l'ordinateur
    cd engine && python daily.py --full --pwa-dir ..
