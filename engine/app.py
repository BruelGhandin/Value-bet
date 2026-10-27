"""Interface locale : python app.py  (ouvre http://127.0.0.1:8765 dans votre navigateur).

Tout reste sur votre machine : base data/store.db, réglages et clés API data/settings.json.
"""
import csv
import datetime as dt
import json
import math
import os
import sys
import threading
import webbrowser

import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, request, send_from_directory
from scipy.stats import poisson

from src import settings
from src.config import EUROPE
from src.model import PoissonModel
from src.sources import SOURCES, get_key, is_enabled
from src.store import Store
from src.updater import run_update
from src.value import devig, edge, kelly_fraction

app = Flask(__name__, static_folder="ui", static_url_path="")
store = Store()
JOB = {"running": False, "lines": [], "started": None}
_models: dict = {}


def clean(o):
    """JSON sans NaN."""
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return clean(float(o))
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def ok(data=None, **kw):
    return jsonify(clean({"ok": True, **(data or {}), **kw}))


def fail(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def read_csv(path):
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


# ---------------------------------------------------------------- pages
@app.get("/")
def index():
    return send_from_directory("ui", "index.html")


# ---------------------------------------------------------------- accueil
@app.get("/api/status")
def status():
    counts = {t: store.query(f"SELECT COUNT(*) FROM {t}")[0][0]
              for t in ("odds", "player_match", "sb_matches", "sb_lineups", "injuries", "upcoming", "journal")}
    last = store.query("SELECT ts, source, ok, message FROM update_log ORDER BY ts DESC LIMIT 8")
    newest = store.query("SELECT MAX(date) FROM odds")[0][0]
    up = store.query("""SELECT league, kickoff, home, away, home_formation, away_formation, source FROM upcoming
                        ORDER BY kickoff LIMIT 12""")
    lineup = {}
    try:
        with open("results/lineup_summary.json", encoding="utf-8") as f:
            lineup = json.load(f)
    except OSError:
        pass
    return ok(counts=counts, newest=newest, last=[dict(zip(("ts", "source", "ok", "message"), r)) for r in last],
              upcoming=[dict(zip(("league", "kickoff", "home", "away", "hf", "af", "source"), r)) for r in up],
              lineup=lineup)


# ---------------------------------------------------------------- prédiction
def _league_df(code):
    return pd.read_sql_query("SELECT date, home, away, home_goals, away_goals FROM odds WHERE league=? ORDER BY date",
                             store.db, params=(code,), parse_dates=["date"])


def get_model(code):
    n = store.query("SELECT COUNT(*), MAX(date) FROM odds WHERE league=?", (code,))[0]
    cached = _models.get(code)
    if cached and cached[0] == n:
        return cached[1], cached[2]
    df = _league_df(code)
    if df.empty:
        return None, []
    last = df["date"].max()
    train = df[df["date"] >= last - pd.Timedelta(days=1095)]
    model = PoissonModel(half_life_days=365).fit(train, ref_date=last)
    teams = sorted(set(df[df["date"] >= last - pd.Timedelta(days=400)][["home", "away"]].to_numpy().ravel()))
    teams = [t for t in teams if t in model.attack]
    _models[code] = (n, model, teams)
    return model, teams


@app.get("/api/leagues")
def leagues():
    rows = store.query("SELECT league, COUNT(*), MAX(date) FROM odds GROUP BY league")
    out = []
    for code, n, last in rows:
        name, country, tier = EUROPE.get(code, (code, "", 0))
        out.append({"code": code, "name": name, "country": country, "tier": tier, "matches": n, "last": last})
    out.sort(key=lambda r: (r["country"], r["tier"]))
    return ok(leagues=out)


@app.get("/api/teams/<code>")
def teams(code):
    _, t = get_model(code)
    return ok(teams=t)


@app.post("/api/predict")
def predict():
    b = request.get_json(force=True)
    code, home, away = b.get("league"), b.get("home"), b.get("away")
    model, teams_ = get_model(code)
    if model is None:
        return fail("Aucune donnée pour ce championnat. Lancez une mise à jour dans « Sources & API ».")
    if home == away:
        return fail("Choisissez deux équipes différentes.")
    p = model.predict(home, away)
    if not p:
        return fail("Équipe inconnue du modèle pour ce championnat.")
    g = np.arange(11)
    grid = np.outer(poisson.pmf(g, p["lam_h"]), poisson.pmf(g, p["lam_a"]))
    grid /= grid.sum()
    scores = sorted(((int(i), int(j), float(grid[i, j])) for i in range(6) for j in range(6)), key=lambda x: -x[2])[:5]
    over25 = float(sum(grid[i, j] for i in range(11) for j in range(11) if i + j > 2))
    btts = float(grid[1:, 1:].sum())
    res = {"p": {"home": p["p_home"], "draw": p["p_draw"], "away": p["p_away"]},
           "lam": [p["lam_h"], p["lam_a"]], "scores": scores, "over25": over25, "btts": btts}

    st = settings.load()
    odds = [b.get("odds_home"), b.get("odds_draw"), b.get("odds_away")]
    try:
        odds = [float(o) if o not in (None, "") else None for o in odds]
    except ValueError:
        return fail("Les cotes doivent être des nombres (par exemple 2.10).")
    if all(o and o > 1 for o in odds):
        mk = devig(*odds)
        bankroll = float(b.get("bankroll") or st["bankroll"])
        rows, best = [], None
        for key, pm, m, o in zip(("home", "draw", "away"), (p["p_home"], p["p_draw"], p["p_away"]), mk, odds):
            e = edge(pm, o)
            rows.append({"outcome": key, "odds": o, "market": m, "model": pm, "edge": e})
            if e >= st["min_edge_pct"] / 100 and (best is None or e > best["edge"]):
                best = {"outcome": key, "odds": o, "edge": e, "p": pm}
        if best:
            frac = min(kelly_fraction(best["p"], best["odds"], st["kelly_fraction"]), st["max_stake_pct"] / 100)
            best["stake"] = round(bankroll * frac, 2)
        res["market"] = {"rows": rows, "margin": sum(1 / o for o in odds) - 1, "best": best, "bankroll": bankroll}
    return ok(res)


# ---------------------------------------------------------------- comparateur de cotes
@app.get("/api/ref_matches")
def ref_matches():
    rows = store.query("""SELECT league, commence, home, away, bookmaker, odds_home, odds_draw, odds_away, fetched_at
                          FROM ref_odds WHERE commence >= date('now','-1 day') ORDER BY commence""")
    groups: dict = {}
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
                    "odds": [oh, od, oa], "fetched_at": ft})
    return ok(matches=out)


@app.post("/api/compare")
def compare():
    b = request.get_json(force=True)
    try:
        book = [float(str(x).replace(",", ".")) for x in b["book"]]
        ref = [float(str(x).replace(",", ".")) for x in b["ref"]]
    except (KeyError, ValueError, TypeError):
        return fail("Saisissez six cotes sous forme de nombres (par exemple 2.10).")
    if len(book) != 3 or len(ref) != 3 or any(o <= 1 for o in book + ref):
        return fail("Chaque cote doit être supérieure à 1.")
    st = settings.load()
    fair = devig(*ref)
    rows, best = [], None
    for k, p, ob, orf in zip(("home", "draw", "away"), fair, book, ref):
        e = edge(p, ob)
        rows.append({"outcome": k, "book": ob, "ref": orf, "fair_prob": p, "fair_odds": 1 / p, "edge": e,
                     "min_odds": (1 / p) * (1 + st["min_edge_pct"] / 100)})
        if e >= st["min_edge_pct"] / 100 and (best is None or e > best["edge"]):
            best = {"outcome": k, "odds": ob, "edge": e, "p": p}
    bankroll = float(b.get("bankroll") or st["bankroll"])
    if best:
        frac = min(kelly_fraction(best["p"], best["odds"], st["kelly_fraction"]), st["max_stake_pct"] / 100)
        best["stake"] = round(bankroll * frac, 2)
    bm, rm = sum(1 / o for o in book) - 1, sum(1 / o for o in ref) - 1
    return ok(rows=rows, book_margin=bm, ref_margin=rm, extra_margin=bm - rm, best=best, bankroll=bankroll,
              min_edge=st["min_edge_pct"], ref_weak=rm > 0.05)


# ---------------------------------------------------------------- formations / résultats
@app.get("/api/formations")
def formations():
    return ok(globales=read_csv("results/formations_globales.csv"), duels=read_csv("results/formations_duels.csv"),
              equipes=read_csv("results/formations_par_equipe.csv"))


@app.get("/api/results")
def results():
    rows = read_csv("results/summary.csv")
    lineup = {}
    try:
        with open("results/lineup_summary.json", encoding="utf-8") as f:
            lineup = json.load(f)
    except OSError:
        pass
    return ok(leagues=rows, lineup=lineup)


# ---------------------------------------------------------------- suivi à blanc
@app.get("/api/journal")
def journal_list():
    rows = store.query("SELECT id, ts, league, home, away, pick, odds, stake, p_model, result, note FROM journal ORDER BY id DESC")
    keys = ("id", "ts", "league", "home", "away", "pick", "odds", "stake", "p_model", "result", "note")
    items = [dict(zip(keys, r)) for r in rows]
    st = settings.load()
    start = float(st["bankroll"])
    profit = 0.0
    staked = settled = won = 0
    for it in items:
        if it["result"] == "won":
            profit += it["stake"] * (it["odds"] - 1); staked += it["stake"]; settled += 1; won += 1
        elif it["result"] == "lost":
            profit -= it["stake"]; staked += it["stake"]; settled += 1
    summary = {"start": start, "current": start + profit, "profit": profit, "staked": staked, "settled": settled,
               "won": won, "pending": sum(1 for i in items if i["result"] == "pending"),
               "roi": (profit / staked) if staked else None}
    return ok(items=items, summary=summary)


@app.post("/api/journal")
def journal_add():
    b = request.get_json(force=True)
    try:
        odds, stake = float(b["odds"]), float(b["stake"])
    except (KeyError, ValueError):
        return fail("Cote et mise sont obligatoires.")
    if odds <= 1 or stake <= 0:
        return fail("La cote doit être supérieure à 1 et la mise positive.")
    store.execute("INSERT INTO journal (ts, league, home, away, pick, odds, stake, p_model, note) VALUES (?,?,?,?,?,?,?,?,?)",
                  (dt.datetime.now().isoformat(timespec="minutes"), b.get("league"), b.get("home"), b.get("away"),
                   b.get("pick"), odds, stake, b.get("p_model"), b.get("note") or ""))
    return ok()


@app.post("/api/journal/<int:jid>")
def journal_settle(jid):
    r = request.get_json(force=True).get("result")
    if r not in ("won", "lost", "pending"):
        return fail("Résultat invalide.")
    store.execute("UPDATE journal SET result=? WHERE id=?", (r, jid))
    return ok()


@app.delete("/api/journal/<int:jid>")
def journal_delete(jid):
    store.execute("DELETE FROM journal WHERE id=?", (jid,))
    return ok()


# ---------------------------------------------------------------- sources, clés, réglages
def _mask(k):
    return "" if not k else ("•" * 8 + k[-4:] if len(k) > 4 else "•" * len(k))


@app.get("/api/sources")
def sources():
    out = []
    for s in SOURCES:
        key = get_key(s) if s["cle"] else None
        last = store.query("SELECT ts, ok, message FROM update_log WHERE source=? ORDER BY ts DESC LIMIT 1", (s["id"],))
        out.append({**{k: s.get(k) for k in ("id", "nom", "type", "url", "apporte", "cle", "verifiee", "mise_a_jour", "gratuit", "inscription", "doc")},
                    "active": is_enabled(s), "key_set": bool(key), "key_masked": _mask(key),
                    "last": dict(zip(("ts", "ok", "message"), last[0])) if last else None})
    return ok(sources=out, settings={k: v for k, v in settings.load().items() if k != "keys"})


@app.post("/api/settings")
def save_settings():
    b = request.get_json(force=True)
    st = settings.load()
    for name, val in (b.get("keys") or {}).items():
        if name in st["keys"] and val is not None and "•" not in val:
            st["keys"][name] = val.strip()
    for k, lo, hi in (("bankroll", 1, 1e9), ("kelly_fraction", 0.01, 1), ("max_stake_pct", 0.1, 25), ("min_edge_pct", 0, 50)):
        if k in b:
            try:
                v = float(b[k])
            except (TypeError, ValueError):
                return fail(f"Valeur invalide pour {k}.")
            st[k] = min(max(v, lo), hi)
    settings.save(st)
    return ok()


@app.post("/api/test/<sid>")
def test_source(sid):
    """Vérifie la connexion à une source (sans consommer de budget significatif)."""
    try:
        if sid == "api_football":
            key = get_key(next(s for s in SOURCES if s["id"] == sid))
            if not key:
                return fail("Aucune clé enregistrée. Collez votre clé API-Football puis enregistrez.")
            r = requests.get("https://v3.football.api-sports.io/status", headers={"x-apisports-key": key}, timeout=20)
            j = r.json()
            if j.get("errors"):
                return fail("Clé refusée : " + json.dumps(j["errors"], ensure_ascii=False))
            req = (j.get("response") or {}).get("requests", {})
            return ok(message=f"Connexion réussie. Requêtes aujourd'hui : {req.get('current', '?')} / {req.get('limit_day', '?')}.")
        if sid == "odds_api":
            key = get_key(next(s for s in SOURCES if s["id"] == sid))
            if not key:
                return fail("Aucune clé enregistrée. Collez votre clé The Odds API puis enregistrez.")
            r = requests.get("https://api.the-odds-api.com/v4/sports/", params={"apiKey": key}, timeout=20)
            if r.status_code in (401, 403):
                return fail("Clé refusée par The Odds API.")
            r.raise_for_status()
            left = r.headers.get("x-requests-remaining", "?")
            return ok(message=f"Connexion réussie. Crédits restants ce mois-ci : {left}.")
        urls = {"fd_pinnacle": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
                "thesportsdb": "https://www.thesportsdb.com/api/v1/json/3/eventsnextleague.php?id=4328",
                "fpl_live": "https://fantasy.premierleague.com/api/bootstrap-static/",
                "espn": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
                "odds_history": "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/README.md",
                "fpl_history": "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/README.md",
                "statsbomb": "https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json",
                "football_data_org": "https://api.football-data.org/v4/competitions/PL"}
        if sid not in urls:
            return fail("Cette source n'a pas de test de connexion.")
        h = {}
        if sid == "football_data_org":
            key = get_key(next(s for s in SOURCES if s["id"] == sid))
            if not key:
                return fail("Aucune clé enregistrée.")
            h["X-Auth-Token"] = key
        r = requests.get(urls[sid], headers={"User-Agent": "Mozilla/5.0", **h}, timeout=20)
        if r.status_code >= 400:
            return fail(f"La source répond avec l'erreur HTTP {r.status_code}.")
        return ok(message=f"Connexion réussie (HTTP {r.status_code}).")
    except requests.RequestException as e:
        return fail("Connexion impossible : " + str(e)[:160])


@app.post("/api/update")
def update():
    if JOB["running"]:
        return fail("Une mise à jour est déjà en cours.")
    only = (request.get_json(silent=True) or {}).get("only") or None
    JOB.update(running=True, lines=[], started=dt.datetime.now().isoformat(timespec="seconds"))

    def work():
        try:
            run_update(Store(), only, 400, log=lambda m: JOB["lines"].append(m))
        except Exception as e:
            JOB["lines"].append(f"ERREUR {e}")
        finally:
            JOB["running"] = False
            _models.clear()

    threading.Thread(target=work, daemon=True).start()
    return ok()


@app.get("/api/update")
def update_state():
    return ok(running=JOB["running"], lines=JOB["lines"], started=JOB["started"])


if __name__ == "__main__":
    port = 8765
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
