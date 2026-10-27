"""The Odds API -> table ref_odds : cotes 1X2 des prochains matchs, bookmaker par bookmaker (dont Pinnacle).

Clé gratuite : https://the-odds-api.com (500 crédits par mois). Une requête = 1 crédit (une région, un marché).
ATTENTION : non testé dans l'environnement de construction (site inaccessible) ; le format suit la documentation v4.
"""
import datetime as dt
import json

from ..settings import get_key
from ..store import BudgetExceeded

BASE = "https://api.the-odds-api.com/v4/sports"
MONTHLY_LIMIT = 500
# clé The Odds API -> code interne ; l'ordre donne la priorité quand le budget est limité
SPORTS = {"soccer_epl": "E0", "soccer_spain_la_liga": "SP1", "soccer_germany_bundesliga": "D1",
          "soccer_italy_serie_a": "I1", "soccer_france_ligue_one": "F1", "soccer_efl_champ": "E1",
          "soccer_netherlands_eredivisie": "N1", "soccer_portugal_primeira_liga": "P1",
          "soccer_japan_j_league": "JPN1", "soccer_korea_kleague1": "KOR1", "soccer_china_superleague": "CHN1"}


def _used_this_month(store) -> int:
    r = store.query("SELECT COALESCE(SUM(n),0) FROM request_log WHERE source='odds_api' AND day LIKE ?",
                    (dt.date.today().strftime("%Y-%m") + "%",))
    return r[0][0]


def run(store, max_sports: int = 6, **_):
    key = get_key("ODDS_API_KEY")
    if not key:
        raise RuntimeError("ODDS_API_KEY manquante")
    now = dt.datetime.now().isoformat(timespec="seconds")
    n_events = n_rows = 0
    try:
        for sport, code in list(SPORTS.items())[:max_sports]:
            if _used_this_month(store) >= MONTHLY_LIMIT - 20:
                raise BudgetExceeded("budget mensuel presque épuisé (500 crédits)")
            raw = store.http_get(f"{BASE}/{sport}/odds/", source="odds_api", ttl_hours=6,
                                 params={"apiKey": key, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"})
            if raw is None:
                continue
            for ev in json.loads(raw):
                n_events += 1
                for bm in ev.get("bookmakers", []):
                    for mk in bm.get("markets", []):
                        if mk.get("key") != "h2h":
                            continue
                        price = {o["name"]: o["price"] for o in mk["outcomes"]}
                        h, a, d = price.get(ev["home_team"]), price.get(ev["away_team"]), price.get("Draw")
                        if not (h and a and d):
                            continue
                        store.execute("INSERT OR REPLACE INTO ref_odds VALUES (?,?,?,?,?,?,?,?,?,?)",
                                      ("odds_api", now, code, ev["commence_time"], ev["home_team"], ev["away_team"],
                                       bm["key"], h, d, a))
                        n_rows += 1
    except BudgetExceeded as e:
        return f"{n_events} matchs, {n_rows} cotes enregistrées ; arrêt : {e}"
    return f"{n_events} matchs, {n_rows} cotes enregistrées. Crédits utilisés ce mois-ci : {_used_this_month(store)} / {MONTHLY_LIMIT}"
