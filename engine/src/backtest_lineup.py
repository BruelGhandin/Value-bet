"""Backtest du modèle « compositions » sur la Premier League.

Compare trois prédictions sur les mêmes matchs : marché (cotes sans marge), modèle de buts seul (Poisson),
et modèle de buts + force de la composition alignée. Walk-forward : pour chaque saison, entraînement sur les
saisons précédentes uniquement.

    python update.py                 # (une fois) remplit la base locale
    python main_lineup.py
"""
import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor

from .backtest import predict_league, probability_metrics, simulate_bets
from .lineup_model import lineup_features
from .names import canon
from .store import Store

TRAIN_FROM = "2020-08-01"   # début des prédictions de base utilisées pour entraîner la correction
FEATS = ["log_lam", "d_att_own", "d_def_opp"]


def _grid_probs(lh: float, la: float, n: int = 10):
    g = np.arange(n + 1)
    grid = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    grid /= grid.sum()
    return float(np.tril(grid, -1).sum()), float(np.trace(grid)), float(np.triu(grid, 1).sum())


def build_dataset(store: Store) -> pd.DataFrame:
    odds = pd.read_sql_query("SELECT * FROM odds WHERE league='E0'", store.db, parse_dates=["date"])
    base = predict_league(odds, TRAIN_FROM)
    pm = pd.read_sql_query("SELECT * FROM player_match", store.db)
    feat = lineup_features(pm)
    feat["ck"] = feat["team"].map(canon)
    feat["co"] = feat["opponent"].map(canon)
    idx = {}
    for r in feat.itertuples():
        for dd in (0, -1, 1):  # tolérance d'un jour (fuseaux horaires)
            idx.setdefault((r.ck, r.co, (r.date + pd.Timedelta(days=dd)).strftime("%Y-%m-%d")), r)
    rows, miss = [], 0
    for b in base.itertuples():
        d = b.date.strftime("%Y-%m-%d")
        h = idx.get((canon(b.home), canon(b.away), d))
        a = idx.get((canon(b.away), canon(b.home), d))
        if h is None or a is None or h.is_home != 1 or a.is_home != 0:
            miss += 1
            continue
        rows.append({**b._asdict(), "h_d_att": h.d_att, "h_d_def": h.d_def, "a_d_att": a.d_att, "a_d_def": a.d_def})
    df = pd.DataFrame(rows).drop(columns="Index").dropna(subset=["h_d_att", "h_d_def", "a_d_att", "a_d_def"])
    print(f"{len(df)} matchs avec composition et cotes ({miss} sans correspondance)")
    return df


def stack(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par équipe et par match : buts marqués, attendu de base, delta d'attaque, delta défensif adverse."""
    h = pd.DataFrame({"y": df["home_goals"], "log_lam": np.log(df["lam_h"]), "d_att_own": df["h_d_att"], "d_def_opp": df["a_d_def"]})
    a = pd.DataFrame({"y": df["away_goals"], "log_lam": np.log(df["lam_a"]), "d_att_own": df["a_d_att"], "d_def_opp": df["h_d_def"]})
    return pd.concat([h, a], keys=["h", "a"], names=["side", "i"]).reset_index()


def walk_forward(df: pd.DataFrame, alpha: float = 1e-3) -> tuple[pd.DataFrame, list]:
    df = df.sort_values("date").reset_index(drop=True)
    season = df["date"].apply(lambda d: d.year if d.month >= 7 else d.year - 1)
    out, coefs = [], []
    for s in sorted(season.unique()):
        tr, te = df[season < s], df[season == s]
        if len(tr) < 300 or te.empty:
            continue
        sd = stack(tr)
        mdl = PoissonRegressor(alpha=alpha, max_iter=500).fit(sd[FEATS], sd["y"])
        coefs.append({"saison": f"{s}-{str(s + 1)[2:]}", "entrainement": len(tr), **dict(zip(FEATS, mdl.coef_.round(3))),
                      "const": round(float(mdl.intercept_), 3)})
        ts = stack(te)
        lam = mdl.predict(ts[FEATS])
        n = len(te)
        lh, la = lam[:n], lam[n:]
        te = te.copy()
        probs = [_grid_probs(x, y) for x, y in zip(lh, la)]
        te["p_home"], te["p_draw"], te["p_away"] = zip(*probs)
        out.append(te)
    return pd.concat(out), coefs


def main():
    store = Store()
    df = build_dataset(store)
    res, coefs = walk_forward(df)
    print("\nCoefficients du modèle par saison d'entraînement :")
    print(pd.DataFrame(coefs).to_string(index=False))

    base_cols = ["p_home", "p_draw", "p_away"]
    base_only = res.copy()
    # probabilités du modèle de buts seul sur les mêmes matchs (colonnes d'origine du backtest de base)
    base_probs = df.loc[res.index.map(lambda _: True)] if False else None
    ref = df.set_index(["date", "home", "away"])
    key = list(zip(res["date"], res["home"], res["away"]))
    base_only[base_cols] = ref.loc[key, base_cols].to_numpy()

    print("\n=== Comparaison sur les mêmes matchs (plus bas = mieux) ===")
    rows = []
    for name, d in (("Marché (cotes sans marge)", None), ("Modèle de buts seul", base_only), ("Buts + compositions", res)):
        if d is None:
            m = probability_metrics(res)
            rows.append({"modèle": name, "logloss": m["logloss_marche"], "brier": m["brier_marche"]})
        else:
            m = probability_metrics(d)
            rows.append({"modèle": name, "logloss": m["logloss_modele"], "brier": m["brier_modele"]})
    print(pd.DataFrame(rows).round(4).to_string(index=False), f"\n({len(res)} matchs)")
    import json
    with open("results/lineup_summary.json", "w", encoding="utf-8") as fh:
        json.dump({"matchs": len(res), "modeles": rows, "coefficients": coefs}, fh, ensure_ascii=False, indent=1)

    for name, d in (("Modèle de buts seul", base_only), ("Buts + compositions", res)):
        bets = simulate_bets(d)
        if len(bets):
            print(f"{name}: {len(bets)} paris, taux de réussite {100 * bets['win'].mean():.1f} %, "
                  f"ROI à mise fixe {100 * bets['flat_profit'].sum() / len(bets):.2f} %")
    res.to_csv("results/lineup_predictions.csv", index=False)
    pd.DataFrame(coefs).to_csv("results/lineup_coefficients.csv", index=False)


if __name__ == "__main__":
    main()
