"""football-data.org -> table upcoming : calendrier des 10 prochains jours (palier gratuit : 12 compétitions).

Clé gratuite : https://www.football-data.org/client/register
ATTENTION : non testé dans l'environnement de construction (site inaccessible).
"""
import datetime as dt
import json

from ..settings import get_key

URL = "https://api.football-data.org/v4/matches"
CODES = {"PL": "E0", "ELC": "E1", "BL1": "D1", "SA": "I1", "PD": "SP1", "FL1": "F1", "DED": "N1", "PPL": "P1"}


def run(store, **_):
    key = get_key("FOOTBALL_DATA_ORG_KEY")
    if not key:
        raise RuntimeError("FOOTBALL_DATA_ORG_KEY manquante")
    today = dt.date.today()
    raw = store.http_get(URL, source="football_data_org", ttl_hours=1, min_interval=6.5,
                         headers={"X-Auth-Token": key},
                         params={"dateFrom": today.isoformat(), "dateTo": (today + dt.timedelta(days=9)).isoformat()})
    now = dt.datetime.now().isoformat(timespec="seconds")
    n = 0
    for m in json.loads(raw).get("matches", []):
        code = CODES.get(m.get("competition", {}).get("code"))
        if not code:
            continue
        store.execute("INSERT OR REPLACE INTO upcoming VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      ("football_data_org", now, code, str(m["id"]), m.get("utcDate"),
                       m["homeTeam"].get("name"), m["awayTeam"].get("name"), None, None, None, None))
        n += 1
    return f"{n} matchs à venir enregistrés"
