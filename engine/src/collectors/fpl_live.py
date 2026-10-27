"""API officielle Fantasy Premier League -> table `injuries` (blessures/suspensions) et `upcoming` (prochains matchs).

ATTENTION : non testé dans l'environnement de construction (site inaccessible). À vérifier chez vous.
"""
import datetime as dt
import json

URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIX = "https://fantasy.premierleague.com/api/fixtures/?future=1"
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def run(store, **_):
    raw = store.http_get(URL, source="fpl_live", ttl_hours=1, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(raw)
    teams = {t["id"]: t["name"] for t in d["teams"]}
    now = dt.datetime.now().isoformat(timespec="seconds")
    rows = []
    for p in d["elements"]:
        if p.get("status") in ("i", "s", "d", "u") or (p.get("chance_of_playing_next_round") not in (None, 100)):
            rows.append(("fpl_live", now, "E0", teams[p["team"]], p["web_name"], POS.get(p["element_type"]),
                         p["status"], p.get("chance_of_playing_next_round"), p.get("news") or ""))
    store.execute("DELETE FROM injuries WHERE source='fpl_live'")
    store.executemany("INSERT OR REPLACE INTO injuries VALUES (?,?,?,?,?,?,?,?,?)", rows)

    fx = json.loads(store.http_get(FIX, source="fpl_live", ttl_hours=1, headers={"User-Agent": "Mozilla/5.0"}))
    up = [("fpl_live", now, "E0", str(f["id"]), f.get("kickoff_time"), teams[f["team_h"]], teams[f["team_a"]],
           None, None, None, None) for f in fx if f.get("kickoff_time")]
    store.execute("DELETE FROM upcoming WHERE source='fpl_live'")
    store.executemany("INSERT OR REPLACE INTO upcoming VALUES (?,?,?,?,?,?,?,?,?,?,?)", up)
    return f"{len(rows)} joueurs signalés blessés/incertains, {len(up)} matchs à venir"
