"""Registre des sources de données.

Chaque source indique : type d'accès, ce qu'elle apporte, si une clé est nécessaire, ses limites gratuites,
les liens pour obtenir une clé, et si elle a été VÉRIFIÉE (téléchargement réussi) dans l'environnement où
le logiciel a été construit. Les sources marquées verifiee=False sont codées mais n'ont pas pu être testées
(réseau restreint ou clé absente) : testez-les chez vous avec « Tester la connexion » ou
`python update.py --only <id>`.

Pour ajouter une source : ajoutez une entrée ici et un collecteur src/collectors/<id>.py (fonction run(store, **kw)).
"""
import os

# type : "fichier_github" | "fichier_web" (statique, gratuit) | "api_gratuite" (sans clé) | "api_cle" | "non_implemente"
SOURCES = [
    {
        "id": "odds_history", "nom": "Résultats + cotes Bet365 historiques (xgabora)",
        "type": "fichier_github", "url": "https://github.com/xgabora/Club-Football-Match-Data-2000-2025",
        "apporte": "résultats et cotes 1X2 de Bet365 (et meilleure cote de ~17 bookmakers), 29 championnats masculins",
        "gratuit": "Gratuit, sans clé", "cle": None, "verifiee": True,
        "mise_a_jour": "re-téléchargé toutes les 24 h",
    },
    {
        "id": "fpl_history", "nom": "Fantasy Premier League : historique par joueur (vaastav)",
        "type": "fichier_github", "url": "https://github.com/vaastav/Fantasy-Premier-League",
        "apporte": "Premier League : joueurs, poste, minutes, titulaire, buts, passes, buts encaissés par match (depuis 2019-20)",
        "gratuit": "Gratuit, sans clé", "cle": None, "verifiee": True,
        "mise_a_jour": "saison en cours re-téléchargée toutes les 6 h",
    },
    {
        "id": "statsbomb", "nom": "StatsBomb Open Data",
        "type": "fichier_github", "url": "https://github.com/statsbomb/open-data",
        "apporte": "formations et compositions avec postes, dont championnats féminins (WSL, Liga F, NWSL, Frauen-Bundesliga, Serie A Women)",
        "gratuit": "Gratuit, sans clé", "cle": None, "verifiee": True,
        "mise_a_jour": "incrémentale : N nouveaux matchs par exécution",
    },
    {
        "id": "fd_pinnacle", "nom": "football-data.co.uk : cotes Pinnacle historiques",
        "type": "fichier_web", "url": "https://www.football-data.co.uk/data.php",
        "doc": "https://www.football-data.co.uk/notes.txt",
        "apporte": "résultats et cotes Pinnacle (ouverture et clôture) des principales divisions européennes : la référence pour juger un bookmaker",
        "gratuit": "Gratuit, sans clé. Les colonnes Pinnacle peuvent manquer pour les saisons récentes : à vérifier", "cle": None, "verifiee": False,
        "mise_a_jour": "saison en cours re-téléchargée toutes les 12 h",
    },
    {
        "id": "odds_api", "nom": "The Odds API : cotes en direct de nombreux bookmakers (dont Pinnacle)",
        "type": "api_cle", "url": "https://api.the-odds-api.com/v4/",
        "inscription": "https://the-odds-api.com", "doc": "https://the-odds-api.com/liveapi/guides/v4/",
        "apporte": "cotes 1X2 des prochains matchs de plus de 100 championnats ; sert de référence pour le comparateur de cotes",
        "gratuit": "500 crédits par mois gratuits (1 championnat = 1 crédit par mise à jour)", "cle": "ODDS_API_KEY", "verifiee": False,
        "mise_a_jour": "6 championnats par mise à jour au maximum ; le budget mensuel est compté",
    },
    {
        "id": "api_football", "nom": "API-Football (api-sports.io)",
        "type": "api_cle", "url": "https://v3.football.api-sports.io/",
        "inscription": "https://dashboard.api-football.com/register", "doc": "https://www.api-football.com/documentation-v3",
        "apporte": "compositions, formations, blessures ; 1 200+ championnats (couverture inégale hors Europe)",
        "gratuit": "100 requêtes par jour, 10 par minute, tous les services", "cle": "API_FOOTBALL_KEY", "verifiee": False,
        "mise_a_jour": "le logiciel compte le budget quotidien",
    },
    {
        "id": "football_data_org", "nom": "football-data.org : calendriers",
        "type": "api_cle", "url": "https://api.football-data.org/v4/",
        "inscription": "https://www.football-data.org/client/register", "doc": "https://www.football-data.org/documentation/quickstart",
        "apporte": "calendrier des 10 prochains jours de 12 compétitions européennes (Premier League, Bundesliga, Serie A, Liga, Ligue 1…)",
        "gratuit": "12 compétitions, 10 appels par minute", "cle": "FOOTBALL_DATA_ORG_KEY", "verifiee": False,
        "mise_a_jour": "à chaque exécution",
    },
    {
        "id": "fpl_live", "nom": "API officielle Fantasy Premier League",
        "type": "api_gratuite", "url": "https://fantasy.premierleague.com/api/bootstrap-static/",
        "apporte": "blessures, suspensions, probabilité de jouer, prochains matchs (Premier League)",
        "gratuit": "Gratuit, sans clé (API non documentée officiellement)", "cle": None, "verifiee": False,
        "mise_a_jour": "toutes les heures au plus",
    },
    {
        "id": "espn", "nom": "ESPN (API publique non documentée)",
        "type": "api_gratuite", "url": "https://site.api.espn.com/apis/site/v2/sports/soccer/",
        "apporte": "calendrier, scores, compositions et formations de nombreux championnats (dont féminins, japonais, chinois)",
        "gratuit": "Gratuit, sans clé ; le format peut changer sans préavis", "cle": None, "verifiee": False,
        "mise_a_jour": "à chaque exécution",
    },
    {
        "id": "thesportsdb", "nom": "TheSportsDB : calendriers",
        "type": "api_gratuite", "url": "https://www.thesportsdb.com/api/v1/json/3/",
        "doc": "https://www.thesportsdb.com/free_sports_api",
        "apporte": "prochains matchs de 5 grands championnats (clé publique de test, volume limité)",
        "gratuit": "Gratuit avec la clé publique « 3 », 30 requêtes par minute", "cle": None, "verifiee": False,
        "mise_a_jour": "à chaque exécution",
    },
    {
        "id": "oddspapi", "nom": "OddsPapi : historique horodaté des cotes (dont Pinnacle)",
        "type": "non_implemente", "url": "https://oddspapi.io",
        "inscription": "https://oddspapi.io",
        "apporte": "évolution des cotes de 381 bookmakers dans le temps : permet de tester la vitesse des cotes",
        "gratuit": "Historique gratuit (3 bookmakers par requête). Pas encore codé : format à confirmer avec une vraie clé", "cle": None, "verifiee": False,
        "mise_a_jour": "non codé",
    },
    {
        "id": "betfair_historic", "nom": "Betfair : données historiques de la bourse de paris",
        "type": "non_implemente", "url": "https://historicdata.betfair.com",
        "inscription": "https://historicdata.betfair.com",
        "apporte": "prix et volumes de la bourse de paris, très précis. L'offre de base est gratuite, les offres avancées sont payantes",
        "gratuit": "Offre de base gratuite, prix des autres offres non confirmé", "cle": None, "verifiee": False,
        "mise_a_jour": "non codé",
    },
]

IMPLEMENTED = {"odds_history", "fpl_history", "statsbomb", "fd_pinnacle", "odds_api", "api_football",
               "football_data_org", "fpl_live", "espn", "thesportsdb"}


def get_key(source: dict) -> str | None:
    env = source.get("cle")
    if not env:
        return None
    from .settings import get_key as _get
    return _get(env)


def is_enabled(source: dict) -> bool:
    if source["id"] not in IMPLEMENTED:
        return False
    return source["cle"] is None or bool(get_key(source))


def describe() -> str:
    lines = []
    for s in SOURCES:
        etat = "actif" if is_enabled(s) else ("clé manquante (" + s["cle"] + ")" if s["cle"] and s["id"] in IMPLEMENTED else "non implémenté")
        verif = "vérifiée" if s["verifiee"] else "NON testée ici"
        lines.append(f"- {s['id']:<18} [{s['type']}] {etat} / {verif}\n    {s['nom']}\n    {s['apporte']}\n"
                     f"    {s.get('gratuit', '')}\n    {s['url']}" + (f"\n    clé : {s['inscription']}" if s.get("inscription") else ""))
    return "\n".join(lines)
