"""Backtesting walk-forward par championnat : chaque match est prédit uniquement avec le passé."""
import numpy as np
import pandas as pd

from .model import PoissonModel
from .value import best_value_bet, devig, kelly_fraction


def _result(hg: int, ag: int) -> str:
    return "home" if hg > ag else ("away" if hg < ag else "draw")


def predict_league(df: pd.DataFrame, eval_start: str, refit_every: int = 30,
                   train_days: int = 1095, half_life: float = 365, min_train: int = 150) -> pd.DataFrame:
    """Prédit tous les matchs à partir de eval_start. Le modèle est ré-ajusté tous les `refit_every` matchs."""
    df = df.sort_values("date").reset_index(drop=True)
    ev = df.index[df["date"] >= pd.Timestamp(eval_start)].tolist()
    rows = []
    for s in range(0, len(ev), refit_every):
        block = df.loc[ev[s:s + refit_every]]
        t0 = block["date"].min()
        train = df[(df["date"] < t0) & (df["date"] >= t0 - pd.Timedelta(days=train_days))]
        if len(train) < min_train:
            continue
        model = PoissonModel(half_life_days=half_life).fit(train, ref_date=t0)
        for _, m in block.iterrows():
            p = model.predict(m["home"], m["away"])
            if not p or m[["odds_home", "odds_draw", "odds_away"]].isna().any():
                continue
            mh, md, ma = devig(m["odds_home"], m["odds_draw"], m["odds_away"])
            rows.append({
                "league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"],
                "p_home": p["p_home"], "p_draw": p["p_draw"], "p_away": p["p_away"],
                "lam_h": p["lam_h"], "lam_a": p["lam_a"],
                "home_goals": m["home_goals"], "away_goals": m["away_goals"],
                "m_home": mh, "m_draw": md, "m_away": ma,
                "odds_home": m["odds_home"], "odds_draw": m["odds_draw"], "odds_away": m["odds_away"],
                "result": _result(m["home_goals"], m["away_goals"]),
            })
    return pd.DataFrame(rows)


def probability_metrics(preds: pd.DataFrame) -> dict:
    """Log loss et Brier du modèle vs marché (plus bas = meilleur)."""
    idx = preds["result"].map({"home": 0, "draw": 1, "away": 2}).to_numpy()
    n = np.arange(len(preds))
    P = preds[["p_home", "p_draw", "p_away"]].to_numpy()
    M = preds[["m_home", "m_draw", "m_away"]].to_numpy()
    Y = np.eye(3)[idx]
    return {
        "logloss_modele": float(-np.log(np.clip(P[n, idx], 1e-9, 1)).mean()),
        "logloss_marche": float(-np.log(np.clip(M[n, idx], 1e-9, 1)).mean()),
        "brier_modele": float(((P - Y) ** 2).sum(axis=1).mean()),
        "brier_marche": float(((M - Y) ** 2).sum(axis=1).mean()),
    }


def simulate_bets(preds: pd.DataFrame, min_edge: float = 0.05, max_edge: float = 0.30,
                  start_bankroll: float = 1000.0, kelly: float = 0.25, max_stake_pct: float = 0.03) -> pd.DataFrame:
    """Un seul pari au maximum par match (le meilleur avantage). Mise fixe de 1 et mise Kelly en parallèle."""
    bankroll = start_bankroll
    out = []
    for _, r in preds.sort_values("date").iterrows():
        bet = best_value_bet(
            {"home": r["p_home"], "draw": r["p_draw"], "away": r["p_away"]},
            {"home": r["odds_home"], "draw": r["odds_draw"], "away": r["odds_away"]},
            min_edge, max_edge)
        if not bet:
            continue
        win = bet["outcome"] == r["result"]
        flat_profit = (bet["odds"] - 1) if win else -1.0
        stake = bankroll * min(kelly_fraction(bet["p"], bet["odds"], kelly), max_stake_pct)
        k_profit = stake * (bet["odds"] - 1) if win else -stake
        bankroll += k_profit
        out.append({"league": r["league"], "date": r["date"], "match": f'{r["home"]} - {r["away"]}',
                    "bet": bet["outcome"], "odds": bet["odds"], "p_model": bet["p"], "edge": bet["edge"],
                    "win": win, "flat_profit": flat_profit, "kelly_stake": stake,
                    "kelly_profit": k_profit, "bankroll": bankroll})
    return pd.DataFrame(out)


def summarize(preds: pd.DataFrame, bets: pd.DataFrame) -> dict:
    s = {"matchs": len(preds)}
    s.update({k: round(v, 4) for k, v in probability_metrics(preds).items()}) if len(preds) else None
    if bets.empty:
        s.update({"paris": 0})
        return s
    s.update({
        "paris": len(bets),
        "taux_reussite_%": round(100 * bets["win"].mean(), 1),
        "roi_flat_%": round(100 * bets["flat_profit"].sum() / len(bets), 2),
        "bankroll_finale": round(bets["bankroll"].iloc[-1], 2),
    })
    return s
