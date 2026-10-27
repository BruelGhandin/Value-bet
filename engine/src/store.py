"""Stockage local (SQLite) + téléchargement avec cache, limites de requêtes et reprises."""
import datetime as dt
import hashlib
import os
import sqlite3
import threading
import time

import requests

DB_PATH = "data/store.db"
CACHE_DIR = "data/cache"

SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (key TEXT PRIMARY KEY, url TEXT, path TEXT, fetched_at REAL);
CREATE TABLE IF NOT EXISTS request_log (source TEXT, day TEXT, n INTEGER, PRIMARY KEY (source, day));
CREATE TABLE IF NOT EXISTS update_log (ts TEXT, source TEXT, ok INTEGER, message TEXT);

-- Premier League (FPL) : une ligne par joueur et par match
CREATE TABLE IF NOT EXISTS player_match (
    season TEXT, match_key TEXT, date TEXT, team TEXT, opponent TEXT, is_home INTEGER,
    player_id INTEGER, player TEXT, pos TEXT, minutes INTEGER, started INTEGER,
    goals INTEGER, assists INTEGER, conceded INTEGER, saves INTEGER, team_goals INTEGER, opp_goals INTEGER,
    PRIMARY KEY (season, match_key, player_id));

-- StatsBomb : matchs et compositions (formation + poste de chaque titulaire)
CREATE TABLE IF NOT EXISTS sb_matches (match_id INTEGER PRIMARY KEY, competition TEXT, season TEXT, gender TEXT,
    date TEXT, home TEXT, away TEXT, home_goals INTEGER, away_goals INTEGER);
CREATE TABLE IF NOT EXISTS sb_lineups (match_id INTEGER, team TEXT, formation TEXT, player_id INTEGER, player TEXT,
    position TEXT, PRIMARY KEY (match_id, team, player_id));
CREATE TABLE IF NOT EXISTS sb_lineup_done (match_id INTEGER PRIMARY KEY, ok INTEGER);

-- Cotes / résultats historiques
CREATE TABLE IF NOT EXISTS odds (league TEXT, date TEXT, home TEXT, away TEXT, home_goals INTEGER, away_goals INTEGER,
    odds_home REAL, odds_draw REAL, odds_away REAL, PRIMARY KEY (league, date, home, away));

-- Cotes de référence : bookmakers en direct (The Odds API) et Pinnacle historique (football-data.co.uk)
CREATE TABLE IF NOT EXISTS ref_odds (source TEXT, fetched_at TEXT, league TEXT, commence TEXT, home TEXT, away TEXT,
    bookmaker TEXT, odds_home REAL, odds_draw REAL, odds_away REAL, PRIMARY KEY (source, league, commence, home, away, bookmaker));
CREATE TABLE IF NOT EXISTS ref_hist (league TEXT, date TEXT, home TEXT, away TEXT, home_goals INTEGER, away_goals INTEGER,
    ps_h REAL, ps_d REAL, ps_a REAL, psc_h REAL, psc_d REAL, psc_a REAL, b365_h REAL, b365_d REAL, b365_a REAL,
    PRIMARY KEY (league, date, home, away));

-- Suivi à blanc (paris virtuels)
CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, league TEXT, home TEXT, away TEXT,
    pick TEXT, odds REAL, stake REAL, p_model REAL, result TEXT DEFAULT 'pending', note TEXT);

-- Sources « en direct » : blessures et prochains matchs
CREATE TABLE IF NOT EXISTS injuries (source TEXT, fetched_at TEXT, league TEXT, team TEXT, player TEXT, pos TEXT,
    status TEXT, chance_playing REAL, news TEXT, PRIMARY KEY (source, league, team, player));
CREATE TABLE IF NOT EXISTS upcoming (source TEXT, fetched_at TEXT, league TEXT, match_id TEXT, kickoff TEXT,
    home TEXT, away TEXT, home_formation TEXT, away_formation TEXT, home_xi TEXT, away_xi TEXT,
    PRIMARY KEY (source, league, match_id));
"""


class BudgetExceeded(Exception):
    pass


class Store:
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self._last = {}

    # ---- utilitaires SQL ----
    def execute(self, sql, params=()):
        with self.lock:
            cur = self.db.execute(sql, params)
            self.db.commit()
            return cur

    def executemany(self, sql, rows):
        with self.lock:
            self.db.executemany(sql, rows)
            self.db.commit()

    def query(self, sql, params=()):
        with self.lock:
            return self.db.execute(sql, params).fetchall()

    def log(self, source: str, ok: bool, message: str):
        self.execute("INSERT INTO update_log VALUES (?,?,?,?)",
                     (dt.datetime.now().isoformat(timespec="seconds"), source, int(ok), message[:500]))

    # ---- téléchargement ----
    def _budget_used(self, source: str) -> int:
        r = self.query("SELECT n FROM request_log WHERE source=? AND day=?", (source, dt.date.today().isoformat()))
        return r[0][0] if r else 0

    def _count(self, source: str):
        day = dt.date.today().isoformat()
        self.execute("INSERT INTO request_log VALUES (?,?,1) ON CONFLICT(source,day) DO UPDATE SET n=n+1", (source, day))

    def http_get(self, url: str, *, source: str, ttl_hours: float | None = None, headers: dict | None = None,
                 params: dict | None = None, byte_range: tuple[int, int] | None = None,
                 daily_limit: int | None = None, min_interval: float = 0.0, retries: int = 3):
        """Retourne le contenu (bytes) ou None si 404. ttl_hours=None : cache sans expiration."""
        key = hashlib.sha1(f"{url}|{sorted((params or {}).items())}|{byte_range}".encode()).hexdigest()
        row = self.query("SELECT path, fetched_at FROM http_cache WHERE key=?", (key,))
        if row and os.path.exists(row[0][0]):
            age_h = (time.time() - row[0][1]) / 3600
            if ttl_hours is None or age_h < ttl_hours:
                with open(row[0][0], "rb") as f:
                    return f.read()
        if daily_limit is not None and self._budget_used(source) >= daily_limit:
            raise BudgetExceeded(f"{source} : budget de {daily_limit} requêtes/jour atteint")
        h = dict(headers or {})
        if byte_range:
            h["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
        last_err = None
        for attempt in range(retries):
            if min_interval:
                with self.lock:
                    wait = self._last.get(source, 0) + min_interval - time.time()
                    self._last[source] = max(time.time(), self._last.get(source, 0) + min_interval)
                if wait > 0:
                    time.sleep(wait)
            try:
                r = requests.get(url, headers=h, params=params, timeout=60)
                self._count(source)
                if r.status_code == 404:
                    return None
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(min(float(r.headers.get("Retry-After", 2 ** attempt * 2)), 60))
                    last_err = f"HTTP {r.status_code}"
                    continue
                r.raise_for_status()
                path = os.path.join(CACHE_DIR, key + ".bin")
                with open(path, "wb") as f:
                    f.write(r.content)
                self.execute("INSERT OR REPLACE INTO http_cache VALUES (?,?,?,?)", (key, url, path, time.time()))
                return r.content
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Échec du téléchargement {url} : {last_err}")
