"""TheSportsDB (clé publique de test « 3 ») -> table upcoming : prochains matchs de 5 grands championnats.

ATTENTION : non testé dans l'environnement de construction (site inaccessible). Volume limité par la clé gratuite.
"""
import datetime as dt
import json

BASE = "https://www.thesportsdb.com/api/v1/json/3/eventsnextleague.php"
LEAGUES = {4328: "E0", 4335: "SP1", 4331: "D1", 4332: "I1", 4334: "F1"}


def run(store, **_):
    now = dt.datetime.now().isoformat(timespec="seconds")
    n = 0
    for lid, code in LEAGUES.items():
        raw = store.http_get(BASE, source="thesportsdb", ttl_hours=3, params={"id": lid}, min_interval=2.1)
        for ev in (json.loads(raw).get("events") or []) if raw else []:
            kickoff = f"{ev.get('dateEvent')}T{(ev.get('strTime') or '00:00:00')[:8]}"
            store.execute("INSERT OR REPLACE INTO upcoming VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          ("thesportsdb", now, code, str(ev["idEvent"]), kickoff, ev.get("strHomeTeam"),
                           ev.get("strAwayTeam"), None, None, None, None))
            n += 1
    return f"{n} matchs à venir enregistrés"
