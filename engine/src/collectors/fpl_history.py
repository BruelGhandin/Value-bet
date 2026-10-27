"""Fantasy Premier League, historique par joueur et par match (vaastav/Fantasy-Premier-League)
-> table `player_match` : minutes, titulaire, poste, buts, passes, buts encaissés.
"""
import datetime as dt
import io

import pandas as pd

BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
FIRST_SEASON = 2019


def seasons() -> list[str]:
    last = dt.date.today().year
    return [f"{y}-{str(y + 1)[2:]}" for y in range(FIRST_SEASON, last + 1)]


def _season_rows(store, season: str, ttl):
    gw = store.http_get(f"{BASE}/{season}/gws/merged_gw.csv", source="fpl_history", ttl_hours=ttl)
    tm = store.http_get(f"{BASE}/{season}/teams.csv", source="fpl_history", ttl_hours=ttl)
    if gw is None or tm is None:
        return None
    d = pd.read_csv(io.BytesIO(gw), encoding="utf-8", encoding_errors="replace", on_bad_lines="skip", low_memory=False)
    teams = pd.read_csv(io.BytesIO(tm)).set_index("id")["name"].to_dict()
    d["opponent"] = d["opponent_team"].map(teams)
    if "team" not in d.columns:  # saison 2019-20 : pas de colonne équipe, on la déduit du calendrier
        fx = store.http_get(f"{BASE}/{season}/fixtures.csv", source="fpl_history", ttl_hours=ttl)
        if fx is None:
            return None
        f = pd.read_csv(io.BytesIO(fx)).set_index("id")
        d["_h"] = d["fixture"].map(f["team_h"]).map(teams)
        d["_a"] = d["fixture"].map(f["team_a"]).map(teams)
        home = d["was_home"].astype(str).str.lower().isin(["true", "1"])
        d["team"] = d["_h"].where(home, d["_a"])
    if "position" not in d.columns:  # 2019-20 : le poste vient de players_raw.csv (element_type)
        pr = store.http_get(f"{BASE}/{season}/players_raw.csv", source="fpl_history", ttl_hours=ttl)
        if pr is None:
            return None
        et = pd.read_csv(io.BytesIO(pr)).set_index("id")["element_type"].map({1: "GK", 2: "DEF", 3: "MID", 4: "FWD"})
        d["position"] = d["element"].map(et)
    d = d[d["opponent"].notna()].copy()
    d["date"] = pd.to_datetime(d["kickoff_time"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
    d["is_home"] = d["was_home"].astype(str).str.lower().isin(["true", "1"]).astype(int)
    d["team_goals"] = d.apply(lambda r: r["team_h_score"] if r["is_home"] else r["team_a_score"], axis=1)
    d["opp_goals"] = d.apply(lambda r: r["team_a_score"] if r["is_home"] else r["team_h_score"], axis=1)
    d = d.dropna(subset=["date", "team_goals", "opp_goals"])
    # "starts" n'existe pas dans les saisons anciennes : on prend les 11 joueurs les plus utilisés
    d["minutes"] = pd.to_numeric(d["minutes"], errors="coerce").fillna(0).astype(int)
    d["match_key"] = d["fixture"].astype(str)
    # titulaire : colonne "starts" si elle est cohérente (11 par équipe et par match), sinon les 11 joueurs les plus utilisés
    d["rank"] = d.groupby(["match_key", "team"])["minutes"].rank(method="first", ascending=False)
    d["started"] = ((d["rank"] <= 11) & (d["minutes"] > 0)).astype(int)
    if "starts" in d.columns:
        st = pd.to_numeric(d["starts"], errors="coerce")
        ok = st.fillna(0).groupby([d["match_key"], d["team"]]).transform("sum") == 11
        d["started"] = st.where(ok, d["started"]).fillna(0).astype(int)
    d["position"] = d["position"].replace({"GKP": "GK", "AM": "MID"})  # libellés incohérents selon les saisons
    d["season"] = season
    out = d[["season", "match_key", "date", "team", "opponent", "is_home", "element", "name", "position", "minutes",
             "started", "goals_scored", "assists", "goals_conceded", "saves", "team_goals", "opp_goals"]].copy()
    out.columns = ["season", "match_key", "date", "team", "opponent", "is_home", "player_id", "player", "pos",
                   "minutes", "started", "goals", "assists", "conceded", "saves", "team_goals", "opp_goals"]
    for c in ("goals", "assists", "conceded", "saves", "team_goals", "opp_goals", "player_id"):
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)
    return out.drop_duplicates(["season", "match_key", "player_id"])


def run(store, **_):
    cur = seasons()[-1]
    total, done = 0, []
    for s in seasons():
        ttl = 6 if s == cur else None  # saisons terminées : cache sans expiration
        rows = _season_rows(store, s, ttl)
        if rows is None:
            continue
        store.execute("DELETE FROM player_match WHERE season=?", (s,))
        store.executemany("INSERT OR REPLACE INTO player_match VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          list(rows.itertuples(index=False, name=None)))
        total += len(rows)
        done.append(s)
    return f"{total} lignes joueur-match, saisons {', '.join(done)}"
