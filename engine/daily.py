"""Mise à jour automatique : matchs, compositions, prédictions et suivi des résultats.

    python daily.py --full   # une fois par jour : données historiques + modèles + cotes de référence + cycle en direct
    python daily.py --live   # toutes les 20 minutes : calendrier, compositions publiées, prédictions, scores (rapide)

Planification gratuite : le workflow GitHub Actions fourni (.github/workflows/value-bet.yml) lance les deux modes.
Sur votre ordinateur : cron (Linux/Mac) ou Planificateur de tâches (Windows) avec la même commande.
Les clés (ODDS_API_KEY facultative) se lisent dans l'environnement ou dans data/settings.json.
"""
import argparse
import datetime as dt
import importlib

import export_pwa as ex
from src import live
from src.settings import get_key
from src.store import Store
from src.updater import run_update


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--full", action="store_true")
    g.add_argument("--live", action="store_true")
    ap.add_argument("--pwa-dir", default="pwa", help="dossier de l'application (contient data/snapshot.json et sw.js)")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    lv = Store("data/live.db")           # petite base conservée entre les exécutions (matchs, compositions, prédictions)
    lv.db.executescript(live.SCHEMA)
    prev = ex.load_snapshot(a.pwa_dir)
    notes = []

    if a.full:
        base = Store("data/store.db")    # historique de résultats et cotes, retéléchargé à chaque exécution complète
        run_update(base, ["odds_history"])
        if get_key("ODDS_API_KEY"):
            try:
                msg = importlib.import_module("src.collectors.odds_api").run(lv)
                lv.log("odds_api", True, msg); notes.append("odds_api: " + msg)
            except Exception as e:
                lv.log("odds_api", False, repr(e)); notes.append("odds_api ERREUR: " + str(e)[:200])
        snap = ex.build_snapshot(base, ref_store=lv, prev=prev)
    else:
        if not prev or not prev.get("models"):
            raise SystemExit("Pas de snapshot : lancez d'abord  python daily.py --full")
        snap = prev

    try:
        msg = live.fetch_matches(lv, now, ttl=1.0 if a.full else 0.05)
        lv.log("espn", True, msg); notes.append("espn: " + msg)
    except Exception as e:
        lv.log("espn", False, repr(e)); notes.append("espn ERREUR: " + str(e)[:200])
    made, unmatched = live.predict_upcoming(lv, snap["models"], now)
    notes.append(f"{made} nouvelles prédictions")
    if unmatched:
        notes.append("équipes sans correspondance : " + ", ".join(unmatched[:12]))

    snap["live"] = {"updated": now.isoformat(timespec="minutes"), "mode": "full" if a.full else "live",
                    "matches": live.live_snapshot(lv, now), "track": live.track_record(lv),
                    "unmatched": unmatched[:30], "notes": notes}
    snap["generated"] = now.isoformat(timespec="minutes") if not a.full else snap["generated"]
    out = ex.write_snapshot(snap, a.pwa_dir, bump_sw=a.full)
    print(out, "|", " | ".join(notes))


if __name__ == "__main__":
    main()
