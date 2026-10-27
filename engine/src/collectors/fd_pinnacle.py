"""football-data.co.uk -> table ref_hist : cotes Pinnacle (ouverture PSH/PSD/PSA, clôture PSCH/PSCD/PSCA) et Bet365.

Pinnacle est un bookmaker très précis : ses cotes de clôture servent de référence pour juger les autres.
ATTENTION : non testé dans l'environnement de construction (site inaccessible). Si les colonnes Pinnacle sont
absentes pour une saison, elle est ignorée sans erreur.
"""
import datetime as dt
import io

import pandas as pd

LEAGUES = ["E0", "E1", "E2", "E3", "SC0", "SC1", "D1", "D2", "I1", "I2", "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1"]
FIRST = 2019
COLS = {"PSH": "ps_h", "PSD": "ps_d", "PSA": "ps_a", "PSCH": "psc_h", "PSCD": "psc_d", "PSCA": "psc_a",
        "B365H": "b365_h", "B365D": "b365_d", "B365A": "b365_a"}


def parse(content: bytes, league: str) -> pd.DataFrame:
    d = pd.read_csv(io.BytesIO(content), encoding="latin-1", on_bad_lines="skip")
    need = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not need.issubset(d.columns) or not ({"PSCH", "PSH"} & set(d.columns)):
        return pd.DataFrame()
    d = d.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]).copy()
    d["date"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    d = d.dropna(subset=["date"])
    out = pd.DataFrame({"league": league, "date": d["date"], "home": d["HomeTeam"], "away": d["AwayTeam"],
                        "home_goals": d["FTHG"].astype(int), "away_goals": d["FTAG"].astype(int)})
    for src, dst in COLS.items():
        out[dst] = pd.to_numeric(d[src], errors="coerce") if src in d.columns else None
    return out.dropna(subset=["ps_h", "psc_h"], how="all")


def run(store, **_):
    cur = dt.date.today().year - (0 if dt.date.today().month >= 7 else 1)
    n = 0
    seasons_ok = set()
    for y in range(FIRST, cur + 1):
        code = f"{y % 100:02d}{(y + 1) % 100:02d}"
        for lg in LEAGUES:
            url = f"https://www.football-data.co.uk/mmz4281/{code}/{lg}.csv"
            raw = store.http_get(url, source="fd_pinnacle", ttl_hours=12 if y == cur else None, min_interval=0.4)
            if raw is None:
                continue
            df = parse(raw, lg)
            if df.empty:
                continue
            rows = [tuple(None if (isinstance(v, float) and v != v) else v for v in r)
                    for r in df.itertuples(index=False, name=None)]
            store.executemany("INSERT OR REPLACE INTO ref_hist VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            n += len(rows)
            seasons_ok.add(code)
    return f"{n} matchs avec cotes Pinnacle, saisons {', '.join(sorted(seasons_ok)) or 'aucune'}"
