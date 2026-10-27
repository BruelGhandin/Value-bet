"""Met à jour la base locale en allant chercher les données dans les sources déclarées (src/sources.py).

    python update.py --list                 # affiche les sources (actives, clés manquantes, non testées)
    python update.py                        # met à jour toutes les sources actives
    python update.py --only statsbomb --max-new 1000
    python update.py --status               # contenu de la base + derniers journaux
Planifiez-le (cron, Planificateur de tâches Windows) pour une mise à jour automatique.
"""
import argparse
from src.sources import describe
from src.store import Store
from src.updater import run_update


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--max-new", type=int, default=400, help="StatsBomb : nombre max de nouveaux matchs par exécution")
    a = ap.parse_args()
    if a.list:
        print(describe())
        return
    store = Store()
    if a.status:
        for t in ("odds", "player_match", "sb_matches", "sb_lineups", "injuries", "upcoming"):
            print(f"{t:<14} {store.query(f'SELECT COUNT(*) FROM {t}')[0][0]} lignes")
        print("\nDerniers journaux :")
        for r in store.query("SELECT ts, source, ok, message FROM update_log ORDER BY ts DESC LIMIT 12"):
            print(f"  {r[0]}  {r[1]:<14} {'OK ' if r[2] else 'ERR'}  {r[3]}")
        return
    run_update(store, a.only, a.max_new)


if __name__ == "__main__":
    main()
