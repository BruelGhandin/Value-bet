"""Modèle de Poisson avec pondération des matchs récents et rétrécissement (shrinkage)."""
import numpy as np
import pandas as pd
from scipy.stats import poisson

MAX_GOALS = 10


class PoissonModel:
    def __init__(self, half_life_days: float = 365, shrink: float = 6.0):
        self.half_life = half_life_days
        self.shrink = shrink  # nb de "matchs fictifs moyens" ajoutés à chaque équipe
        self.attack: dict = {}
        self.defense: dict = {}
        self.avg_home = 1.4
        self.avg_away = 1.1

    def fit(self, df: pd.DataFrame, ref_date=None) -> "PoissonModel":
        ref = pd.Timestamp(ref_date) if ref_date is not None else df["date"].max()
        w = 0.5 ** ((ref - df["date"]).dt.days.clip(lower=0) / self.half_life)
        self.avg_home = float(np.average(df["home_goals"], weights=w))
        self.avg_away = float(np.average(df["away_goals"], weights=w))
        base = (self.avg_home + self.avg_away) / 2

        long = pd.concat([
            pd.DataFrame({"team": df["home"], "scored": df["home_goals"], "conceded": df["away_goals"], "w": w}),
            pd.DataFrame({"team": df["away"], "scored": df["away_goals"], "conceded": df["home_goals"], "w": w}),
        ])
        long["ws"] = long["scored"] * long["w"]
        long["wc"] = long["conceded"] * long["w"]
        g = long.groupby("team")[["ws", "wc", "w"]].sum()
        k = self.shrink
        self.attack = ((g["ws"] + k * base) / (g["w"] + k) / base).to_dict()
        self.defense = ((g["wc"] + k * base) / (g["w"] + k) / base).to_dict()
        return self

    def predict(self, home: str, away: str) -> dict:
        """Probabilités 1X2 estimées (dict vide si une équipe est inconnue)."""
        if home not in self.attack or away not in self.attack:
            return {}
        lam_h = self.attack[home] * self.defense[away] * self.avg_home
        lam_a = self.attack[away] * self.defense[home] * self.avg_away
        g = np.arange(MAX_GOALS + 1)
        grid = np.outer(poisson.pmf(g, lam_h), poisson.pmf(g, lam_a))
        grid /= grid.sum()
        return {
            "lam_h": float(lam_h), "lam_a": float(lam_a),
            "p_home": float(np.tril(grid, -1).sum()),
            "p_draw": float(np.trace(grid)),
            "p_away": float(np.triu(grid, 1).sum()),
        }
