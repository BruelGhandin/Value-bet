"""Exécution d'une mise à jour des sources (utilisée par update.py et par l'interface)."""
import importlib

from .sources import SOURCES, is_enabled


def run_update(store, only=None, max_new: int = 400, log=print):
    for s in SOURCES:
        if only and s["id"] not in only:
            continue
        if not is_enabled(s):
            if only:
                log(f"[{s['id']}] inactive (clé manquante ou non implémentée)")
            continue
        log(f"[{s['id']}] en cours…")
        try:
            mod = importlib.import_module(f"src.collectors.{s['id']}")
            msg = mod.run(store, max_new=max_new)
            store.log(s["id"], True, msg)
            log(f"[{s['id']}] OK  {msg}")
        except Exception as e:  # une source en panne ne bloque pas les autres
            store.log(s["id"], False, repr(e))
            log(f"[{s['id']}] ERREUR  {str(e)[:300]}")
    log("Terminé.")
