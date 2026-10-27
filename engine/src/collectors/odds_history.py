"""Cotes et résultats historiques (xgabora/Club-Football-Match-Data-2000-2025) -> table `odds`."""
import io

import pandas as pd

from ..config import DATA_START, EUROPE
from ..data_loader import RAW_RENAME, clean

URL = "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv"


def run(store, **_):
    content = store.http_get(URL, source="odds_history", ttl_hours=24)
    if content is None:
        raise RuntimeError("fichier introuvable")
    df = pd.read_csv(io.BytesIO(content), usecols=list(RAW_RENAME), low_memory=False).rename(columns=RAW_RENAME)
    df = clean(df)
    df = df[df["league"].isin(EUROPE) & (df["date"] >= DATA_START)].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    rows = list(df[["league", "date", "home", "away", "home_goals", "away_goals",
                    "odds_home", "odds_draw", "odds_away"]].itertuples(index=False, name=None))
    rows = [tuple(None if (isinstance(v, float) and v != v) else v for v in r) for r in rows]
    store.executemany("INSERT OR REPLACE INTO odds VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return f"{len(rows)} matchs avec cotes ({df['league'].nunique()} championnats)"
