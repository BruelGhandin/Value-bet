"""Chargement des données de matchs.

Format standard (CSV) : league, date, home, away, home_goals, away_goals,
odds_home, odds_draw, odds_away (cotes optionnelles pour la prédiction,
nécessaires pour le backtest).
"""
import pandas as pd

RAW_RENAME = {
    "Division": "league",
    "MatchDate": "date",
    "HomeTeam": "home",
    "AwayTeam": "away",
    "FTHome": "home_goals",
    "FTAway": "away_goals",
    "OddHome": "odds_home",
    "OddDraw": "odds_draw",
    "OddAway": "odds_away",
}
STD_COLS = ["league", "date", "home", "away", "home_goals", "away_goals",
            "odds_home", "odds_draw", "odds_away"]


def load_raw(path: str) -> pd.DataFrame:
    """Charge le gros fichier Matches.csv (xgabora/Club-Football-Match-Data-2000-2025)."""
    df = pd.read_csv(path, usecols=list(RAW_RENAME), low_memory=False).rename(columns=RAW_RENAME)
    return clean(df)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "home", "away", "home_goals", "away_goals"])
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)
    for c in ("odds_home", "odds_draw", "odds_away"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[STD_COLS].sort_values("date").reset_index(drop=True)


def load_matches(path: str, leagues: list[str] | None = None) -> pd.DataFrame:
    """Charge un CSV au format standard (par ex. data/europe_matches.csv)."""
    df = clean(pd.read_csv(path))
    if leagues:
        df = df[df["league"].isin(leagues)].reset_index(drop=True)
    return df
