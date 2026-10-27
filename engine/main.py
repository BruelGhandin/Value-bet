"""Backtest multi-championnats.

Usage :
    python download_data.py          # une fois
    python main.py                   # tous les championnats
    python main.py E0 SP1 F1         # certains championnats seulement
"""
import os
import sys

import pandas as pd

from src.backtest import predict_league, simulate_bets, summarize
from src.config import EUROPE, EVAL_START
from src.data_loader import load_matches

DATA = "data/europe_matches.csv"


def main(leagues: list[str]):
    df = load_matches(DATA, leagues or None)
    os.makedirs("results", exist_ok=True)
    rows, all_preds, all_bets = [], [], []
    for code in sorted(df["league"].unique()):
        d = df[df["league"] == code]
        preds = predict_league(d, EVAL_START)
        if preds.empty:
            continue
        bets = simulate_bets(preds)
        name, country, tier = EUROPE.get(code, (code, "", 0))
        rows.append({"code": code, "championnat": f"{country} - {name}", **summarize(preds, bets)})
        all_preds.append(preds)
        all_bets.append(bets)
        print(f"{code}: {len(preds)} matchs, {len(bets)} paris", flush=True)

    summary = pd.DataFrame(rows)
    summary.to_csv("results/summary.csv", index=False)
    pd.concat(all_preds).to_csv("results/predictions.csv", index=False)
    bets_all = pd.concat(all_bets)
    bets_all.to_csv("results/bets.csv", index=False)

    print("\n=== Résumé par championnat ===")
    print(summary.to_string(index=False))
    if len(bets_all):
        print(f"\nTOTAL : {len(bets_all)} paris, ROI à mise fixe = "
              f"{100 * bets_all['flat_profit'].sum() / len(bets_all):.2f} %")


if __name__ == "__main__":
    main(sys.argv[1:])
