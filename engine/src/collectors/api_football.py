"""API-Football (api-sports.io) -> compositions, formations et blessures. Nécessite la variable d'environnement
API_FOOTBALL_KEY. Palier gratuit : 100 requêtes/jour, le budget est compté dans la base locale.

ATTENTION : non testé (pas de clé dans l'environnement de construction). Les chemins JSON suivent la
documentation publique de l'API (fixtures, fixtures/lineups, injuries).
"""
import datetime as dt
import json

from ..sources import SOURCES, get_key
from ..store import BudgetExceeded

BASE = "https://v3.football.api-sports.io"
# ID de ligue API-Football -> code interne (39 = Premier League, 140 = La Liga, 78 = Bundesliga, 135 = Serie A, 61 = Ligue 1)
LEAGUES = {39: "E0", 140: "SP1", 78: "D1", 135: "I1", 61: "F1"}
LIMIT = 100


def _call(store, key, path, params):
    raw = store.http_get(f"{BASE}/{path}", source="api_football", ttl_hours=1, params=params,
                         headers={"x-apisports-key": key}, daily_limit=LIMIT, min_interval=6.5)
    return json.loads(raw)["response"] if raw else []


def run(store, season: int | None = None, **_):
    src = next(s for s in SOURCES if s["id"] == "api_football")
    key = get_key(src)
    if not key:
        raise RuntimeError("API_FOOTBALL_KEY manquante")
    today = dt.date.today()
    season = season or (today.year if today.month >= 7 else today.year - 1)
    now = dt.datetime.now().isoformat(timespec="seconds")
    n = 0
    try:
        for lid, code in LEAGUES.items():
            fixtures = _call(store, key, "fixtures",
                             {"league": lid, "season": season, "from": today.isoformat(),
                              "to": (today + dt.timedelta(days=4)).isoformat()})
            for f in fixtures:
                fid = f["fixture"]["id"]
                lineups = _call(store, key, "fixtures/lineups", {"fixture": fid})  # vide tant que la compo n'est pas publiée
                form, xi = {}, {}
                for t in lineups:
                    side = "home" if t["team"]["id"] == f["teams"]["home"]["id"] else "away"
                    form[side] = t.get("formation")
                    xi[side] = json.dumps([{"player": p["player"]["name"], "pos": p["player"].get("pos")}
                                           for p in t.get("startXI", [])], ensure_ascii=False)
                store.execute("INSERT OR REPLACE INTO upcoming VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              ("api_football", now, code, str(fid), f["fixture"]["date"], f["teams"]["home"]["name"],
                               f["teams"]["away"]["name"], form.get("home"), form.get("away"), xi.get("home"), xi.get("away")))
                n += 1
            inj = _call(store, key, "injuries", {"league": lid, "season": season, "date": today.isoformat()})
            rows = [("api_football", now, code, i["team"]["name"], i["player"]["name"], None,
                     i["player"].get("type"), None, i["player"].get("reason") or "") for i in inj]
            store.executemany("INSERT OR REPLACE INTO injuries VALUES (?,?,?,?,?,?,?,?,?)", rows)
    except BudgetExceeded as e:
        return f"{n} matchs traités ; arrêt : {e}"
    return f"{n} matchs API-Football enregistrés"
