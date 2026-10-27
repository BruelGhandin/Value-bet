"""Réglages locaux (clés API, paramètres de mise). Stockés dans data/settings.json sur votre machine uniquement."""
import json
import os

PATH = "data/settings.json"
DEFAULTS = {
    "keys": {"API_FOOTBALL_KEY": "", "FOOTBALL_DATA_ORG_KEY": "", "ODDS_API_KEY": ""},
    "bankroll": 1000.0,       # capital de départ du suivi à blanc
    "kelly_fraction": 0.25,   # part du critère de Kelly utilisée
    "max_stake_pct": 3.0,     # mise maximale, en % du capital
    "min_edge_pct": 5.0,      # avantage minimal pour signaler un pari, en %
}


def load() -> dict:
    s = json.loads(json.dumps(DEFAULTS))
    try:
        with open(PATH, encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(s.get(k), dict):
                s[k].update(v)
            else:
                s[k] = v
    except (OSError, ValueError):
        pass
    return s


def save(s: dict):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def get_key(env_name: str) -> str | None:
    """La variable d'environnement a priorité sur le fichier de réglages."""
    return os.environ.get(env_name) or load()["keys"].get(env_name) or None
