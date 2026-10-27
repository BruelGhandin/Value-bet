"""Télécharge les données (GitHub) et prépare data/europe_matches.csv.

Source : xgabora/Club-Football-Match-Data-2000-2025 (résultats + cotes, domaine public/ouvert,
issu de football-data.co.uk). Usage : python download_data.py
"""
import os

import requests

from src.config import DATA_START, EUROPE
from src.data_loader import load_raw

URL = ("https://raw.githubusercontent.com/xgabora/"
       "Club-Football-Match-Data-2000-2025/main/data/Matches.csv")
RAW_PATH = "data/raw/Matches_all.csv"
OUT_PATH = "data/europe_matches.csv"


def main():
    os.makedirs("data/raw", exist_ok=True)
    if not os.path.exists(RAW_PATH):
        print("Téléchargement…")
        r = requests.get(URL, timeout=300)
        r.raise_for_status()
        with open(RAW_PATH, "wb") as f:
            f.write(r.content)
    df = load_raw(RAW_PATH)
    df = df[df["league"].isin(EUROPE) & (df["date"] >= DATA_START)]
    df.to_csv(OUT_PATH, index=False)
    print(f"{len(df)} matchs, {df['league'].nunique()} championnats -> {OUT_PATH}")
    print(df.groupby("league").agg(matchs=("home", "size"), dernier=("date", "max")).to_string())


if __name__ == "__main__":
    main()
