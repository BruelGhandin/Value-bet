"""Championnats pris en charge (codes de la colonne Division du jeu de données)."""

# code: (nom, pays, niveau)
EUROPE = {
    "E0": ("Premier League", "Angleterre", 1),
    "E1": ("Championship", "Angleterre", 2),
    "E2": ("League One", "Angleterre", 3),
    "E3": ("League Two", "Angleterre", 4),
    "SC0": ("Premiership", "Écosse", 1),
    "SC1": ("Championship", "Écosse", 2),
    "D1": ("Bundesliga", "Allemagne", 1),
    "D2": ("2. Bundesliga", "Allemagne", 2),
    "I1": ("Serie A", "Italie", 1),
    "I2": ("Serie B", "Italie", 2),
    "SP1": ("La Liga", "Espagne", 1),
    "SP2": ("La Liga 2", "Espagne", 2),
    "F1": ("Ligue 1", "France", 1),
    "F2": ("Ligue 2", "France", 2),
    "N1": ("Eredivisie", "Pays-Bas", 1),
    "B1": ("Pro League", "Belgique", 1),
    "P1": ("Primeira Liga", "Portugal", 1),
    "T1": ("Süper Lig", "Turquie", 1),
    "G1": ("Super League", "Grèce", 1),
    # Données disponibles jusqu'à fin 2024 seulement :
    "AUT": ("Bundesliga", "Autriche", 1),
    "SUI": ("Super League", "Suisse", 1),
    "DEN": ("Superliga", "Danemark", 1),
    "NOR": ("Eliteserien", "Norvège", 1),
    "SWE": ("Allsvenskan", "Suède", 1),
    "POL": ("Ekstraklasa", "Pologne", 1),
    "ROM": ("Liga I", "Roumanie", 1),
    "RUS": ("Premier Liga", "Russie", 1),
    "FIN": ("Veikkausliiga", "Finlande", 1),
    "IRL": ("Premier Division", "Irlande", 1),
}

# Date de début des données conservées (warmup) et de l'évaluation (backtest)
DATA_START = "2019-07-01"
EVAL_START = "2021-07-01"

# Championnats féminins : aucune source gratuite avec cotes n'a été trouvée.
WOMEN_LEAGUES_AVAILABLE = False
