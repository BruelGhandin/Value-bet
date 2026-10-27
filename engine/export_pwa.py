"""Exporte les paramètres des modèles et les résultats vers pwa/data/snapshot.json.

La PWA (application Android installable) ne peut pas exécuter Python : elle fait ses calculs en JavaScript à partir
de ce fichier. Les équipes sont décrites par 2 nombres (attaque, défense) : c'est tout ce dont le modèle de Poisson a
besoin pour prédire un match.

    python update.py            # met à jour la base locale
    python export_pwa.py        # régénère pwa/data/snapshot.json (et incrémente la version du cache hors-ligne)
    # puis publiez le dossier pwa/ (voir pwa/LISEZMOI.md)
"""
import csv
import datetime as dt
import json
import os
import re

import numpy as np
import pandas as pd

from src.config import EUROPE
from src.model import PoissonModel
from src.sources import IMPLEMENTED, SOURCES
from src.store import Store
from src.value import devig

OUT = "pwa/data/snapshot.json"
TRAIN_DAYS, ACTIVE_DAYS, HALF_LIFE = 1095, 400, 365  # mêmes valeurs que app.get_model


def r5(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 5)


def read_csv(path):
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def build_models(store):
    leagues, models = [], {}
    for code, n, last in store.query("SELECT league, COUNT(*), MAX(date) FROM odds GROUP BY league"):
        df = pd.read_sql_query("SELECT date, home, away, home_goals, away_goals FROM odds WHERE league=? ORDER BY date",
                               store.db, params=(code,), parse_dates=["date"])
        if df.empty:
            continue
        end = df["date"].max()
        m = PoissonModel(half_life_days=HALF_LIFE).fit(df[df["date"] >= end - pd.Timedelta(days=TRAIN_DAYS)], ref_date=end)
        teams = sorted(set(df[df["date"] >= end - pd.Timedelta(days=ACTIVE_DAYS)][["home", "away"]].to_numpy().ravel()))
        teams = [t for t in teams if t in m.attack]
        name, country, tier = EUROPE.get(code, (code, "", 0))
        leagues.append({"code": code, "name": name, "country": country, "tier": tier, "matches": n, "last": last})
        models[code] = {"avg_home": r5(m.avg_home), "avg_away": r5(m.avg_away),
                        "teams": {t: [r5(m.attack[t]), r5(m.defense[t])] for t in teams}}
    leagues.sort(key=lambda r: (r["country"], r["tier"]))
    return leagues, models


def ref_matches(store):
    rows = store.query("""SELECT league, commence, home, away, bookmaker, odds_home, odds_draw, odds_away, fetched_at
                          FROM ref_odds WHERE commence >= date('now','-1 day') ORDER BY commence""")
    groups = {}
    for lg, com, h, a, bm, oh, od, oa, ft in rows:
        groups.setdefault((lg, com, h, a), {})[bm] = (oh, od, oa, ft)
    out = []
    for (lg, com, h, a), books in groups.items():
        if "pinnacle" in books:
            oh, od, oa, ft = books["pinnacle"]
            label = "Pinnacle"
        else:
            probs = np.mean([devig(*v[:3]) for v in books.values()], axis=0)
            oh, od, oa = [float(1 / p) for p in probs]
            ft = max(v[3] for v in books.values())
            label = f"Moyenne de {len(books)} bookmakers (cotes sans marge)"
        out.append({"league": lg, "commence": com, "home": h, "away": a, "source": label,
                    "odds": [r5(oh), r5(od), r5(oa)], "fetched_at": ft})
    return out


def build_snapshot(store, ref_store=None, prev=None):
    """Instantané complet. `prev` : instantané précédent, dont on garde les parties que la base actuelle ne sait pas refaire
    (par exemple en automatique, où seules les cotes sont retéléchargées : pas de données joueurs ni de formations)."""
    prev = prev or {}
    leagues, models = build_models(store)
    if not models:
        raise SystemExit("Base vide : lancez d'abord  python update.py")
    counts = {t: store.query(f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("odds", "player_match", "sb_matches", "sb_lineups")}
    counts = {k: max(v, (prev.get("counts") or {}).get(k, 0)) for k, v in counts.items()}
    fm = {"globales": read_csv("results/formations_globales.csv"), "duels": read_csv("results/formations_duels.csv"),
          "equipes": read_csv("results/formations_par_equipe.csv")}
    return {
        "generated": dt.datetime.now().isoformat(timespec="minutes"),
        "newest": store.query("SELECT MAX(date) FROM odds")[0][0],
        "counts": counts,
        "leagues": leagues,
        "models": models,
        "upcoming": [],
        "ref_matches": ref_matches(ref_store or store),
        "sources": [{**{k: x.get(k) for k in ("id", "nom", "type", "apporte", "gratuit", "inscription", "doc", "url", "verifiee")},
                     "codee": x["id"] in IMPLEMENTED} for x in SOURCES],
        "lineup": read_json("results/lineup_summary.json") or prev.get("lineup", {}),
        "results_leagues": read_csv("results/summary.csv") or prev.get("results_leagues", []),
        "formations": fm if fm["globales"] else prev.get("formations", fm),
        "live": prev.get("live", {}),
    }


def write_snapshot(snap, pwa_dir="pwa", bump_sw=True):
    out = os.path.join(pwa_dir, "data", "snapshot.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
    sw = os.path.join(pwa_dir, "sw.js")
    if bump_sw and os.path.exists(sw):  # nouvelle version du cache hors-ligne
        s = open(sw, encoding="utf-8").read()
        s = re.sub(r'const VERSION = "[^"]*";', f'const VERSION = "{dt.datetime.now():%Y%m%d-%H%M%S}";', s)
        open(sw, "w", encoding="utf-8").write(s)
    return out


def load_snapshot(pwa_dir="pwa"):
    return read_json(os.path.join(pwa_dir, "data", "snapshot.json"))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwa-dir", default="pwa")
    a = ap.parse_args()
    snap = build_snapshot(Store(), prev=load_snapshot(a.pwa_dir))
    out = write_snapshot(snap, a.pwa_dir)
    n_teams = sum(len(m["teams"]) for m in snap["models"].values())
    print(f"{out} : {len(snap['models'])} championnats, {n_teams} équipes, {os.path.getsize(out) / 1024:.0f} Ko. Données jusqu'au {snap['newest']}.")


if __name__ == "__main__":
    main()
