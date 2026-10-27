# Value Bet : application Android (PWA)

Application installable sur l'écran d'accueil d'Android. Elle fait tous ses calculs dans le téléphone et marche sans connexion.

## Ce qu'elle contient
Prédire un match, Comparer des cotes (Pinnacle comme référence), Suivi à blanc, Formations, Résultats des tests, Sources & réglages.
Le suivi et les réglages sont gardés dans le navigateur du téléphone (pensez à « Exporter le suivi »).

## Publier gratuitement (GitHub Pages)
L'installation demande une adresse **https** : GitHub Pages en fournit une gratuitement.
1. Dans votre dépôt GitHub, mettez le contenu du dossier `pwa/` (à la racine du dépôt, ou dans un dossier `docs/`).
2. Réglages du dépôt > Pages > choisissez la branche et le dossier (`/` ou `/docs`).
3. Sur Android, ouvrez `https://VOTRE-NOM.github.io/VOTRE-DEPOT/` dans Chrome.
4. Menu ⋮ > « Installer l'application » (ou le bouton « Installer » dans Sources & réglages).

## Mettre à jour les données
Sur l'ordinateur :

    python update.py          # télécharge les nouvelles données
    python export_pwa.py      # régénère pwa/data/snapshot.json

Puis republiez le dossier `pwa/` sur GitHub. Sur le téléphone, ouvrez l'application en ligne : les nouvelles données arrivent seules,
ou touchez « Rechercher de nouvelles données ».

## Cotes en direct (facultatif)
Collez votre clé gratuite The Odds API dans Sources & réglages. Dans « Comparer », choisissez un championnat puis « Charger les cotes en direct »
(1 crédit sur 500 par mois). Cette fonction n'a pas pu être testée en vrai : si le navigateur la bloque, saisissez les cotes à la main.

## Essai rapide sur l'ordinateur

    cd pwa && python -m http.server 8790     # puis http://localhost:8790
