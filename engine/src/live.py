"""Pipeline « en direct » : calendrier + compositions (ESPN, gratuit, sans clé) -> prédictions automatiques -> suivi des résultats.

Étapes d'un cycle (voir daily.py) :
  1. lire les matchs récents et à venir de chaque championnat (scoreboard ESPN) ;
  2. pour les matchs qui approchent, lire la composition et la formation (summary ESPN) dès qu'elles sont publiées ;
  3. faire une prédiction dès que le match est dans la fenêtre (version 0), puis une seconde quand la composition est connue (version 1) ;
  4. quand le match est fini, enregistrer le score ;
  5. mesurer honnêtement la qualité des prédictions (erreur du modèle contre erreur du marché, résultat des paris signalés).

ATTENTION : l'API ESPN n'est pas documentée officiellement et n'a pas pu être testée dans l'environnement de construction
(site inaccessible) ; le code suit le format observé d'habitude et reste défensif. Les codes de ligue ESPN sont à vérifier.
"""
import datetime as dt
import difflib
import json
import math
import re
import unicodedata

from .config import EUROPE
from .names import canon
from .value import devig, edge

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
# code ESPN -> code interne (ceux de config.EUROPE). Un code erroné est simplement ignoré (404).
ESPN_LEAGUES = {
    "eng.1": "E0", "eng.2": "E1", "eng.3": "E2", "eng.4": "E3", "sco.1": "SC0", "sco.2": "SC1",
    "ger.1": "D1", "ger.2": "D2", "ita.1": "I1", "ita.2": "I2", "esp.1": "SP1", "esp.2": "SP2",
    "fra.1": "F1", "fra.2": "F2", "ned.1": "N1", "bel.1": "B1", "por.1": "P1", "tur.1": "T1", "gre.1": "G1",
    "aut.1": "AUT", "sui.1": "SUI", "den.1": "DEN", "nor.1": "NOR", "swe.1": "SWE", "pol.1": "POL",
    "rou.1": "ROM", "rus.1": "RUS", "fin.1": "FIN", "irl.1": "IRL",
    "eng.w.1": "WSL", "jpn.1": "JPN1", "chn.1": "CHN1",
}
LEAGUE_NAMES = {**{k: v[0] for k, v in EUROPE.items()}, "WSL": "Women's Super League", "JPN1": "J1 League", "CHN1": "Super League chinoise"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_matches (league TEXT, match_id TEXT, kickoff TEXT, home TEXT, away TEXT, status TEXT,
    home_goals INTEGER, away_goals INTEGER, hf TEXT, af TEXT, hxi TEXT, axi TEXT, lineup_at TEXT, updated_at TEXT,
    PRIMARY KEY (league, match_id));
CREATE TABLE IF NOT EXISTS live_predictions (league TEXT, match_id TEXT, version INTEGER, created_at TEXT, lineup_known INTEGER,
    home_m TEXT, away_m TEXT, lam_h REAL, lam_a REAL, p_h REAL, p_d REAL, p_a REAL,
    ref_h REAL, ref_d REAL, ref_a REAL, ref_src TEXT, flag TEXT, flag_edge REAL, flag_odds REAL,
    PRIMARY KEY (league, match_id, version));
"""
MIN_EDGE, MAX_EDGE = 0.05, 0.30
MAX_GOALS = 10


# ------------------------------------------------------------------ noms d'équipes
_STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "fk", "sk", "bk", "if", "ik", "sv", "vfl", "vfb", "tsg", "rb", "us",
         "ud", "cd", "rc", "rcd", "ca", "club", "de", "calcio", "1", "04", "05", "09", "1899", "1846", "1860", "fsv", "ogc", "stade"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    toks = [t for t in s.split() if t not in _STOP]
    return " ".join(toks) or s.strip()


class TeamMatcher:
    """Associe un nom d'équipe d'une source (ESPN, Odds API) au nom utilisé par le modèle."""

    def __init__(self, teams):
        self.teams = list(teams)
        self.by_norm = {norm(t): t for t in self.teams}
        self.by_canon = {canon(t): t for t in self.teams}
        self.cache = {}

    def find(self, name):
        if name in self.cache:
            return self.cache[name]
        r = self._find(name)
        self.cache[name] = r
        return r

    def _find(self, name):
        if name in self.teams:
            return name
        n = norm(name)
        if n in self.by_norm:
            return self.by_norm[n]
        if canon(name) in self.by_canon:
            return self.by_canon[canon(name)]
        tn = set(n.split())
        cands = [t for nt, t in self.by_norm.items() if nt and len(nt) >= 4 and (set(nt.split()) <= tn or tn <= set(nt.split()))]
        if len(cands) == 1:
            return cands[0]
        close = difflib.get_close_matches(n, list(self.by_norm), n=1, cutoff=0.8)
        return self.by_norm[close[0]] if close else None


# ------------------------------------------------------------------ ESPN
def _json(store, url, ttl):
    raw = store.http_get(url, source="espn", ttl_hours=ttl, min_interval=0.3, headers={"User-Agent": "Mozilla/5.0"})
    return None if raw is None else json.loads(raw)


def _utc(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def fetch_matches(store, now, days_back=1, days_ahead=2, ttl=0.05, leagues=None, summary_window_h=3.0):
    """Met à jour live_matches : calendrier, score, formation et composition. Retourne un petit bilan."""
    d0 = (now - dt.timedelta(days=days_back)).strftime("%Y%m%d")
    d1 = (now + dt.timedelta(days=days_ahead)).strftime("%Y%m%d")
    stamp = now.isoformat(timespec="minutes")
    n_ev = n_lineup = n_fail = n_ok = 0
    for slug, code in ESPN_LEAGUES.items():
        if leagues and code not in leagues:
            continue
        try:
            sb = _json(store, f"{ESPN_BASE}/{slug}/scoreboard?dates={d0}-{d1}", ttl)
        except Exception:
            n_fail += 1
            continue
        if sb is None:
            continue
        n_ok += 1
        for ev in sb.get("events", []):
            try:
                comp = ev["competitions"][0]
                h = next(c for c in comp["competitors"] if c["homeAway"] == "home")
                a = next(c for c in comp["competitors"] if c["homeAway"] == "away")
                state = ev.get("status", {}).get("type", {}).get("state", "pre")  # pre / in / post
                status = {"pre": "scheduled", "in": "live", "post": "finished"}.get(state, state)
                if ev.get("status", {}).get("type", {}).get("completed"):
                    status = "finished"
                ko = _utc(ev.get("date"))
                mid = str(ev["id"])
                old = store.query("SELECT hf, af, hxi, axi, lineup_at FROM live_matches WHERE league=? AND match_id=?", (code, mid))
                hf, af, hxi, axi, lineup_at = old[0] if old else (None, None, None, None, None)
                hg = ag = None
                if status in ("live", "finished"):
                    try:
                        hg, ag = int(h.get("score")), int(a.get("score"))
                    except (TypeError, ValueError):
                        pass
                near = ko is not None and abs((ko - now).total_seconds()) <= summary_window_h * 3600
                if lineup_at is None and (near or status != "scheduled"):
                    summ = _json(store, f"{ESPN_BASE}/{slug}/summary?event={mid}", ttl)
                    fm, xi = {}, {}
                    for r in (summ or {}).get("rosters", []):
                        side = r.get("homeAway")
                        starters = [{"player": p["athlete"]["displayName"], "pos": (p.get("position") or {}).get("abbreviation")}
                                    for p in r.get("roster", []) if p.get("starter")]
                        if len(starters) == 11:
                            fm[side] = r.get("formation")
                            xi[side] = json.dumps(starters, ensure_ascii=False)
                    if len(xi) == 2:
                        hf, af, hxi, axi, lineup_at = fm.get("home"), fm.get("away"), xi["home"], xi["away"], stamp
                        n_lineup += 1
                store.execute("INSERT OR REPLACE INTO live_matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (code, mid, ko.isoformat(timespec="minutes") if ko else ev.get("date"), h["team"]["displayName"],
                               a["team"]["displayName"], status, hg, ag, hf, af, hxi, axi, lineup_at, stamp))
                n_ev += 1
            except Exception:
                continue
    if n_ok == 0 and n_fail:
        raise RuntimeError("ESPN injoignable (réseau bloqué ?)")
    return f"{n_ev} matchs lus, {n_lineup} nouvelles compositions"


# ------------------------------------------------------------------ prédiction
def _pmf(lam, n=MAX_GOALS):
    out = [math.exp(-lam)]
    for k in range(1, n + 1):
        out.append(out[-1] * lam / k)
    return out


def poisson_1x2(lh, la):
    ph, pa = _pmf(lh), _pmf(la)
    tot = ph_ = pd_ = pa_ = 0.0
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            v = x * y
            tot += v
            if i > j:
                ph_ += v
            elif i == j:
                pd_ += v
            else:
                pa_ += v
    return ph_ / tot, pd_ / tot, pa_ / tot


def model_prob(models, league, home, away):
    m = models.get(league)
    if not m:
        return None
    th, ta = m["teams"].get(home), m["teams"].get(away)
    if not th or not ta:
        return None
    lh, la = th[0] * ta[1] * m["avg_home"], ta[0] * th[1] * m["avg_away"]
    return lh, la, poisson_1x2(lh, la)


def _ref_for(store, league, home_m, away_m, ko, matcher):
    """Cotes de référence (Pinnacle sinon consensus) pour ce match, depuis la table ref_odds."""
    try:
        rows = store.query("SELECT commence, home, away, bookmaker, odds_home, odds_draw, odds_away FROM ref_odds WHERE league=?", (league,))
    except Exception:
        return None
    books = {}
    for com, h, a, bm, oh, od, oa in rows:
        c = _utc(com)
        if c is None or ko is None or abs((c - ko).total_seconds()) > 36 * 3600:
            continue
        if matcher.find(h) == home_m and matcher.find(a) == away_m:
            books[bm] = (oh, od, oa)
    if not books:
        return None
    if "pinnacle" in books:
        return "Pinnacle", books["pinnacle"]
    acc = [0.0, 0.0, 0.0]
    for v in books.values():
        for i, p in enumerate(devig(*v)):
            acc[i] += p / len(books)
    return f"Moyenne de {len(books)} bookmakers", tuple(1 / p for p in acc)


def predict_upcoming(store, models, now, horizon_h=36.0):
    """Crée/maintient les prédictions des matchs à venir. Retourne (nouvelles prédictions, équipes sans correspondance)."""
    matchers, unmatched, made = {}, set(), 0
    stamp = now.isoformat(timespec="minutes")
    rows = store.query("SELECT league, match_id, kickoff, home, away, status, lineup_at FROM live_matches WHERE status!='finished'")
    for league, mid, kickoff, home, away, status, lineup_at in rows:
        ko = _utc(kickoff)
        if ko is None or ko > now + dt.timedelta(hours=horizon_h):
            continue
        if league not in models:
            continue
        mt = matchers.setdefault(league, TeamMatcher(models[league]["teams"]))
        hm, am = mt.find(home), mt.find(away)
        if not hm or not am:
            unmatched.update(n for n, m in ((home, hm), (away, am)) if not m)
            continue
        want = 1 if lineup_at else 0
        have = {r[0] for r in store.query("SELECT version FROM live_predictions WHERE league=? AND match_id=?", (league, mid))}
        if want in have or (status == "live"):  # pas de nouvelle prédiction une fois le match commencé
            continue
        res = model_prob(models, league, hm, am)
        if res is None:
            continue
        lh, la, p = res
        ref = _ref_for(store, league, hm, am, ko, mt)
        ref_h = ref_d = ref_a = None
        src = flag = None
        fe = fo = None
        if ref:
            src, (ref_h, ref_d, ref_a) = ref
            for k, pm, o in zip(("home", "draw", "away"), p, (ref_h, ref_d, ref_a)):
                e = edge(pm, o)
                if MIN_EDGE <= e <= MAX_EDGE and (fe is None or e > fe):
                    flag, fe, fo = k, e, o
        store.execute("INSERT OR REPLACE INTO live_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (league, mid, want, stamp, int(bool(lineup_at)), hm, am, lh, la, p[0], p[1], p[2],
                       ref_h, ref_d, ref_a, src, flag, fe, fo))
        made += 1
    return made, sorted(unmatched)


# ------------------------------------------------------------------ suivi honnête
def track_record(store):
    """Erreur du modèle contre celle du marché, et résultat des paris signalés, sur les matchs terminés."""
    rows = store.query("""SELECT m.home_goals, m.away_goals, p.p_h, p.p_d, p.p_a, p.ref_h, p.ref_d, p.ref_a, p.flag, p.flag_odds
                          FROM live_matches m JOIN live_predictions p ON p.league=m.league AND p.match_id=m.match_id
                          WHERE m.status='finished' AND m.home_goals IS NOT NULL
                            AND p.version=(SELECT MAX(version) FROM live_predictions q WHERE q.league=p.league AND q.match_id=p.match_id)""")
    n = len(rows)
    ll_m = ll_k = 0.0
    n_k = hit = n_flag = 0
    profit = 0.0
    for hg, ag, ph, pd_, pa, rh, rd, ra, flag, fo in rows:
        y = 0 if hg > ag else (1 if hg == ag else 2)
        ll_m += -math.log(max((ph, pd_, pa)[y], 1e-9))
        if rh:
            mk = devig(rh, rd, ra)
            ll_k += -math.log(max(mk[y], 1e-9))
            n_k += 1
        if flag:
            n_flag += 1
            won = ("home", "draw", "away")[y] == flag
            hit += won
            profit += (fo - 1) if won else -1
    # erreur du modèle sur les mêmes matchs que le marché, pour comparer à armes égales
    ll_same = 0.0
    for hg, ag, ph, pd_, pa, rh, *_ in rows:
        if rh:
            y = 0 if hg > ag else (1 if hg == ag else 2)
            ll_same += -math.log(max((ph, pd_, pa)[y], 1e-9))
    return {"matchs": n, "matchs_avec_marche": n_k,
            "logloss_modele": round(ll_m / n, 4) if n else None,
            "logloss_modele_memes_matchs": round(ll_same / n_k, 4) if n_k else None,
            "logloss_marche": round(ll_k / n_k, 4) if n_k else None,
            "paris_signales": n_flag, "reussite": round(hit / n_flag, 4) if n_flag else None,
            "roi_signales": round(profit / n_flag, 4) if n_flag else None}


def live_snapshot(store, now, back_h=8.0, ahead_h=36.0):
    """Section « live » du snapshot lu par l'application."""
    lo = (now - dt.timedelta(hours=back_h)).isoformat(timespec="minutes")
    hi = (now + dt.timedelta(hours=ahead_h)).isoformat(timespec="minutes")
    rows = store.query("""SELECT m.league, m.match_id, m.kickoff, m.home, m.away, m.status, m.home_goals, m.away_goals,
                                 m.hf, m.af, m.hxi, m.axi, m.lineup_at,
                                 p.home_m, p.away_m, p.lam_h, p.lam_a, p.p_h, p.p_d, p.p_a, p.ref_h, p.ref_d, p.ref_a, p.ref_src, p.flag, p.flag_edge, p.flag_odds
                          FROM live_matches m LEFT JOIN live_predictions p ON p.league=m.league AND p.match_id=m.match_id
                            AND p.version=(SELECT MAX(version) FROM live_predictions q WHERE q.league=m.league AND q.match_id=m.match_id)
                          WHERE m.kickoff BETWEEN ? AND ? ORDER BY m.kickoff, m.league""", (lo, hi))
    out = []
    for (lg, mid, ko, h, a, st, hg, ag, hf, af, hxi, axi, lat, hm, am, lh, la, ph, pd_, pa, rh, rd, ra, rs, fl, fe, fo) in rows:
        item = {"league": lg, "league_name": LEAGUE_NAMES.get(lg, lg), "kickoff": ko, "home": h, "away": a, "status": st,
                "score": [hg, ag] if hg is not None else None, "hf": hf, "af": af, "lineup": bool(lat), "lineup_at": lat,
                "hxi": json.loads(hxi) if hxi else None, "axi": json.loads(axi) if axi else None,
                "p": [round(ph, 4), round(pd_, 4), round(pa, 4)] if ph is not None else None,
                "lam": [round(lh, 3), round(la, 3)] if lh is not None else None}
        if rh:
            fair = devig(rh, rd, ra)
            item["ref"] = {"src": rs, "odds": [round(rh, 3), round(rd, 3), round(ra, 3)], "fair": [round(x, 4) for x in fair]}
        if fl:
            item["flag"] = {"outcome": fl, "edge": round(fe, 4), "odds": round(fo, 3)}
        out.append(item)
    return out
