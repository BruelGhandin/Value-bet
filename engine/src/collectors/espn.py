"""ESPN (API publique non documentée) -> table `upcoming` : matchs récents/à venir, formations et compositions.

ATTENTION : non testé dans l'environnement de construction (site inaccessible) et API non officielle :
le format peut changer. Le collecteur est défensif (une erreur sur un match n'arrête pas le reste).
Ligues configurables dans ESPN_LEAGUES (codes ESPN : eng.1, esp.1, ger.1, ita.1, fra.1, jpn.1, chn.1,
eng.w.1 pour la WSL, etc.).
"""
import datetime as dt
import json

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_LEAGUES = {"eng.1": "E0", "esp.1": "SP1", "ger.1": "D1", "ita.1": "I1", "fra.1": "F1",
                "eng.w.1": "WSL", "jpn.1": "JPN1", "chn.1": "CHN1"}


def _get_json(store, url, ttl):
    raw = store.http_get(url, source="espn", ttl_hours=ttl, min_interval=0.5)
    return None if raw is None else json.loads(raw)


def run(store, days_back: int = 2, days_ahead: int = 7, **_):
    now = dt.datetime.now().isoformat(timespec="seconds")
    d0 = (dt.date.today() - dt.timedelta(days=days_back)).strftime("%Y%m%d")
    d1 = (dt.date.today() + dt.timedelta(days=days_ahead)).strftime("%Y%m%d")
    n_events = n_xi = n_fail = 0
    for slug, code in ESPN_LEAGUES.items():
        try:
            sb = _get_json(store, f"{BASE}/{slug}/scoreboard?dates={d0}-{d1}", ttl=1)
        except Exception:
            n_fail += 1
            continue
        for ev in (sb or {}).get("events", []):
            try:
                comp = ev["competitions"][0]
                home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
                away = next(c for c in comp["competitors"] if c["homeAway"] == "away")
                formations, xis = {}, {}
                summ = _get_json(store, f"{BASE}/{slug}/summary?event={ev['id']}", ttl=1)
                for r in (summ or {}).get("rosters", []):
                    side = r.get("homeAway")
                    formations[side] = r.get("formation")
                    xis[side] = json.dumps([
                        {"player": p["athlete"]["displayName"], "pos": p.get("position", {}).get("abbreviation")}
                        for p in r.get("roster", []) if p.get("starter")], ensure_ascii=False)
                if xis:
                    n_xi += 1
                store.execute("INSERT OR REPLACE INTO upcoming VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              ("espn", now, code, str(ev["id"]), ev.get("date"),
                               home["team"]["displayName"], away["team"]["displayName"],
                               formations.get("home"), formations.get("away"), xis.get("home"), xis.get("away")))
                n_events += 1
            except Exception:
                continue
    if n_events == 0 and n_fail == len(ESPN_LEAGUES):
        raise RuntimeError("ESPN injoignable (réseau bloqué ?)")
    return f"{n_events} matchs ESPN enregistrés, dont {n_xi} avec composition"
