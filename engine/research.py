"""Recherche d'un avantage face au marché.

Question : existe-t-il une information (Elo, forme, tirs, corners, modèle de buts, meilleures cotes entre
bookmakers) qui rend les probabilités MEILLEURES que celles des cotes ? Chaque test est fait en walk-forward
(entraînement sur les saisons passées, évaluation sur la saison suivante) et comparé au marché, avec un
intervalle d'incertitude à 95 %.

    python research.py
"""
import io

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.collectors.odds_history import URL
from src.store import Store

TOP5 = {"E0", "SP1", "D1", "I1", "F1"}
SECOND = {"E1", "E2", "E3", "SP2", "D2", "I2", "F2", "SC1", "SC2", "SC3"}
ROLL = 8


def group_of(code):
    return "Top 5" if code in TOP5 else ("Divisions inférieures" if code in SECOND else "Autres championnats")


def load(store: Store) -> pd.DataFrame:
    raw = store.http_get(URL, source="odds_history", ttl_hours=None)
    d = pd.read_csv(io.BytesIO(raw), low_memory=False)
    d["date"] = pd.to_datetime(d["MatchDate"])
    d = d[d["date"] >= "2019-07-01"].rename(columns={"Division": "league", "HomeTeam": "home", "AwayTeam": "away"})
    d = d.dropna(subset=["OddHome", "OddDraw", "OddAway", "FTHome", "FTAway"]).sort_values("date").reset_index(drop=True)
    d["res"] = np.where(d["FTHome"] > d["FTAway"], 0, np.where(d["FTHome"] == d["FTAway"], 1, 2))
    inv = 1 / d[["OddHome", "OddDraw", "OddAway"]].to_numpy()
    p = inv / inv.sum(axis=1, keepdims=True)
    d[["m_h", "m_d", "m_a"]] = p
    d["season"] = d["date"].apply(lambda x: x.year if x.month >= 7 else x.year - 1)
    return d


def rolling_stats(d: pd.DataFrame) -> pd.DataFrame:
    """Moyenne glissante (ROLL derniers matchs, hors match courant) de tirs cadrés, tirs et corners pour/contre."""
    d = d.copy()
    d["mid"] = np.arange(len(d))
    stats = {"sot": ("HomeTarget", "AwayTarget"), "sh": ("HomeShots", "AwayShots"), "co": ("HomeCorners", "AwayCorners")}
    long = []
    for side, other in (("home", "away"), ("away", "home")):
        t = pd.DataFrame({"mid": d["mid"], "league": d["league"], "date": d["date"], "team": d[side]})
        for k, (h, a) in stats.items():
            f, ag = (h, a) if side == "home" else (a, h)
            t[k] = d[f] - d[ag]  # solde pour - contre
        long.append(t)
    long = pd.concat(long).sort_values(["league", "team", "date", "mid"])
    for k in stats:
        long[k + "_r"] = long.groupby(["league", "team"])[k].transform(lambda s: s.shift(1).rolling(ROLL, min_periods=4).mean())
    for side in ("home", "away"):
        pass
    r = long.set_index(["mid", "team"])
    for k in stats:
        d[f"{k}_h"] = [r[k + "_r"].get((m, t), np.nan) for m, t in zip(d["mid"], d["home"])]
        d[f"{k}_a"] = [r[k + "_r"].get((m, t), np.nan) for m, t in zip(d["mid"], d["away"])]
        d[f"{k}_diff"] = d[f"{k}_h"] - d[f"{k}_a"]
    return d


def logloss(p, y):
    return -np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1))


def features(d, kind):
    ph, pd_, pa = d["m_h"], d["m_d"], d["m_a"]
    X = pd.DataFrame({"lhd": np.log(ph / pd_), "lad": np.log(pa / pd_)})
    if kind in ("elo", "elo+stats", "all"):
        X["elo"] = (d["HomeElo"] - d["AwayElo"]) / 100
        X["f3"] = d["Form3Home"] - d["Form3Away"]
        X["f5"] = d["Form5Home"] - d["Form5Away"]
    if kind in ("elo+stats", "all"):
        for k in ("sot", "sh", "co"):
            X[k] = d[f"{k}_diff"]
    if kind == "all":
        X["pm_h"] = np.log(d["pm_home"] / d["pm_draw"])
        X["pm_a"] = np.log(d["pm_away"] / d["pm_draw"])
    return X


def walk_forward(d, kind, first_test=2023):
    """Retourne, pour chaque match de test, les probabilités du modèle (recalibrage du marché + informations ajoutées)."""
    out = pd.DataFrame(index=d.index, columns=["p_h", "p_d", "p_a"], dtype=float)
    X = features(d, kind)
    ok = X.notna().all(axis=1)
    for s in sorted(d["season"].unique()):
        if s < first_test:
            continue
        tr = ok & (d["season"] < s)
        te = ok & (d["season"] == s)
        if tr.sum() < 2000 or te.sum() == 0:
            continue
        sc = StandardScaler().fit(X[tr])
        lr = LogisticRegression(C=0.5, max_iter=600).fit(sc.transform(X[tr]), d.loc[tr, "res"])
        out.loc[te, :] = lr.predict_proba(sc.transform(X[te]))
    return out


def paired(delta):
    delta = delta[~np.isnan(delta)]
    m, se = delta.mean(), delta.std(ddof=1) / np.sqrt(len(delta))
    return m, 1.96 * se, len(delta)


def roi_ci(profits):
    m, se = profits.mean(), profits.std(ddof=1) / np.sqrt(len(profits))
    return 100 * m, 196 * se, len(profits)


def main():
    store = Store()
    d = load(store)
    pm = pd.read_csv("results/predictions.csv", parse_dates=["date"])[
        ["league", "date", "home", "away", "p_home", "p_draw", "p_away"]].rename(
        columns={"p_home": "pm_home", "p_draw": "pm_draw", "p_away": "pm_away"})
    d = d.merge(pm, on=["league", "date", "home", "away"], how="inner").sort_values("date").reset_index(drop=True)
    d = rolling_stats(d)
    d["group"] = d["league"].map(group_of)
    y = d["res"].to_numpy()
    base = logloss(d[["m_h", "m_d", "m_a"]].to_numpy(), y)
    print(f"{len(d)} matchs (2021-22 à 2026-27), évaluation sur les saisons 2023-24 et suivantes\n")

    print("=== 1. Une information supplémentaire améliore-t-elle les probabilités du marché ? ===")
    print("Écart de log loss par rapport au marché (négatif = meilleur que le marché), avec marge d'erreur à 95 %\n")
    rows = []
    for kind, label in (("market", "Marché recalibré seul"), ("elo", "+ Elo et forme"),
                        ("elo+stats", "+ tirs cadrés, tirs, corners"), ("all", "+ modèle de buts")):
        p = walk_forward(d, kind)
        ll = logloss(p.to_numpy(dtype=float), y)
        delta = ll - base
        row = {"modèle": label}
        for g in ("Top 5", "Divisions inférieures", "Autres championnats", "Tous"):
            mask = (d["group"] == g) if g != "Tous" else np.ones(len(d), bool)
            m, ci, n = paired(delta[mask])
            row[g] = f"{m:+.4f} ± {ci:.4f}" if n else "–"
        rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n=== 2. Meilleures cotes entre bookmakers (valeur par rapport au consensus) ===")
    print("Pari sur l'issue dont la MEILLEURE cote du marché dépasse la cote juste du consensus, mise fixe 1.\n")
    mx = d[["MaxHome", "MaxDraw", "MaxAway"]].to_numpy()
    ok = np.isfinite(mx).all(axis=1) & (mx / d[["OddHome", "OddDraw", "OddAway"]].to_numpy() < 1.6).all(axis=1)
    P = d[["m_h", "m_d", "m_a"]].to_numpy()
    E = np.where(ok[:, None], P * mx - 1, -9)
    rows = []
    for thr in (0.0, 0.03, 0.05, 0.08):
        k = E.argmax(1)
        sel = E.max(1) >= thr
        prof = np.where(k == y, mx[np.arange(len(y)), k] - 1, -1.0)
        row = {"avantage minimal": f"{int(thr * 100)} %"}
        for g in ("Top 5", "Divisions inférieures", "Autres championnats", "Tous"):
            mask = sel & ((d["group"] == g) if g != "Tous" else True)
            if mask.sum() > 30:
                r, ci, n = roi_ci(prof[mask])
                row[g] = f"{r:+.1f} % ± {ci:.1f} ({n})"
            else:
                row[g] = "–"
        rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))

    base_prof = np.where(np.arange(3)[None, :] == y[:, None], mx - 1, -1.0)[ok]
    print(f"\nRepère : miser 1 sur CHAQUE issue à la meilleure cote = {100 * base_prof.mean():+.2f} % par pari "
          f"(coût du jeu quand on choisit toujours la meilleure cote).")
    # robustesse par saison, seuil 3 %
    sel = E.max(1) >= 0.03
    k = E.argmax(1)
    prof = np.where(k == y, mx[np.arange(len(y)), k] - 1, -1.0)
    print("\nSeuil 3 %, par saison (tous championnats) :")
    for s in sorted(d["season"].unique()):
        mask = sel & (d["season"] == s)
        if mask.sum() > 50:
            r, ci, n = roi_ci(prof[mask])
            print(f"  {s}-{str(s + 1)[2:]} : {r:+.1f} % ± {ci:.1f} ({n} paris)")


if __name__ == "__main__":
    main()
