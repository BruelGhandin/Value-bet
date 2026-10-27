"""StatsBomb Open Data -> tables sb_matches / sb_lineups (formation + poste de chaque titulaire).

Les fichiers d'événements sont lourds ; la composition de départ est dans les premiers octets,
on ne télécharge donc que le début de chaque fichier (requête Range).
Mise à jour incrémentale : au plus `max_new` nouveaux matchs par exécution.
"""
import json
from concurrent.futures import ThreadPoolExecutor

RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# (nom de compétition StatsBomb, genre) -> priorité : on traite d'abord le féminin et les ligues demandées
WANTED = [
    ("FA Women's Super League", "female"), ("Liga F", "female"), ("NWSL", "female"),
    ("Frauen Bundesliga", "female"), ("Serie A Women", "female"),
    ("Premier League", "male"), ("La Liga", "male"), ("1. Bundesliga", "male"),
    ("Serie A", "male"), ("Ligue 1", "male"), ("Major League Soccer", "male"),
    ("Indian Super league", "male"),
]


def _json(store, url, ttl=24):
    c = store.http_get(url, source="statsbomb", ttl_hours=ttl)
    return None if c is None else json.loads(c)


def _starting_xi(store, match_id: int):
    """Lit les 2 premiers événements « Starting XI » dans le début du fichier d'événements."""
    raw = store.http_get(f"{RAW}/events/{match_id}.json", source="statsbomb", ttl_hours=None, byte_range=(0, 24000))
    if raw is None:
        return []
    text = raw.decode("utf-8", errors="ignore")
    dec, pos, out = json.JSONDecoder(), text.find("{"), []
    while pos != -1 and len(out) < 2:
        try:
            obj, end = dec.raw_decode(text, pos)
        except ValueError:
            break
        if obj.get("type", {}).get("name") == "Starting XI":
            out.append(obj)
        pos = text.find("{", end)
    return out


def run(store, max_new: int = 400, workers: int = 8, **_):
    comps = _json(store, f"{RAW}/competitions.json")
    if comps is None:
        raise RuntimeError("competitions.json introuvable")
    targets = []
    for name, gender in WANTED:
        for c in comps:
            if c["competition_name"] == name and c["competition_gender"] == gender:
                targets.append(c)
    for c in targets:
        ms = _json(store, f"{RAW}/matches/{c['competition_id']}/{c['season_id']}.json")
        if not ms:
            continue
        rows = [(m["match_id"], c["competition_name"], c["season_name"], c["competition_gender"], m["match_date"],
                 m["home_team"]["home_team_name"], m["away_team"]["away_team_name"], m["home_score"], m["away_score"])
                for m in ms]
        store.executemany("INSERT OR REPLACE INTO sb_matches VALUES (?,?,?,?,?,?,?,?,?)", rows)

    todo = [r[0] for r in store.query(
        """SELECT m.match_id FROM sb_matches m LEFT JOIN sb_lineup_done d ON d.match_id=m.match_id
           WHERE d.match_id IS NULL ORDER BY m.gender DESC, m.date DESC""")][:max_new]

    def work(mid):
        try:
            return mid, _starting_xi(store, mid)
        except Exception as e:  # un match en erreur ne bloque pas les autres
            return mid, None

    ok = 0
    with ThreadPoolExecutor(workers) as ex:
        for mid, xis in ex.map(work, todo):
            if not xis:
                store.execute("INSERT OR REPLACE INTO sb_lineup_done VALUES (?,0)", (mid,))
                continue
            rows = []
            for ev in xis:
                t = ev["tactics"]
                for p in t["lineup"]:
                    rows.append((mid, ev["team"]["name"], str(t["formation"]), p["player"]["id"],
                                 p["player"]["name"], p["position"]["name"]))
            store.executemany("INSERT OR REPLACE INTO sb_lineups VALUES (?,?,?,?,?,?)", rows)
            store.execute("INSERT OR REPLACE INTO sb_lineup_done VALUES (?,1)", (mid,))
            ok += 1
    left = store.query("SELECT COUNT(*) FROM sb_matches m LEFT JOIN sb_lineup_done d ON d.match_id=m.match_id WHERE d.match_id IS NULL")[0][0]
    return f"{ok} nouvelles compositions lues ; {left} matchs restent à traiter (relancer pour continuer)"
