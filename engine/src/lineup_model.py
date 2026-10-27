"""Modèle basé sur les compositions (Premier League, données FPL).

Idée : on note chaque joueur à son poste d'après ses matchs passés, puis on mesure la force de la composition
alignée (les 11 titulaires réels) et on la compare à la composition habituelle de l'équipe.
Un titulaire clé absent baisse la force du onze ; un remplaçant qui joue à sa place la fait varier.

Notes de joueur (calculées uniquement avec les matchs AVANT la rencontre, pondérées par la récence) :
  attaque  = buts + 0,6 x passes décisives, par 90 minutes
  défense  = buts encaissés quand le joueur est sur le terrain, par 90 minutes
Ces taux sont ramenés vers la moyenne du poste (shrinkage) pour les joueurs avec peu de minutes.
"""
import numpy as np
import pandas as pd

K_MIN = 900          # minutes « fictives » du shrinkage
HALF_LIFE = 365.0    # jours
HISTORY = 10         # nb de matchs pour la composition « habituelle » de l'équipe


def lineup_features(pm: pd.DataFrame) -> pd.DataFrame:
    """pm : table player_match (une ligne par joueur et par match). Retourne une ligne par équipe et par match."""
    pm = pm.copy()
    pm["date"] = pd.to_datetime(pm["date"])
    pm["att"] = pm["goals"] + 0.6 * pm["assists"]
    state = {}                                   # joueur -> [minutes, att, conc, dernière date] (valeurs pondérées)
    pos_cum = {p: [1e-9, 0.0, 0.0] for p in ("GK", "DEF", "MID", "FWD")}
    recent = {}                                  # équipe -> liste (xi_att, xi_def) des derniers matchs
    out = []
    default = {"GK": (0.0, 1.3), "DEF": (0.08, 1.3), "MID": (0.2, 1.3), "FWD": (0.45, 1.3)}

    for (date, mkey), g in pm.sort_values(["date", "match_key"]).groupby(["date", "match_key"], sort=False):
        per_team = {}
        for team, t in g.groupby("team"):
            starters = t[t["started"] == 1]
            att_sum, conc_vals = 0.0, []
            for _, r in starters.iterrows():
                st = state.get(r["player_id"])
                mins, att, conc = 0.0, 0.0, 0.0
                if st:
                    f = 0.5 ** ((date - st[3]).days / HALF_LIFE)
                    mins, att, conc = st[0] * f, st[1] * f, st[2] * f
                pc = pos_cum[r["pos"]]
                pa = pc[1] / pc[0] * 90 if pc[0] > 5000 else default[r["pos"]][0]
                pcn = pc[2] / pc[0] * 90 if pc[0] > 5000 else default[r["pos"]][1]
                att90 = (att + pa * K_MIN / 90) / (mins + K_MIN) * 90
                conc90 = (conc + pcn * K_MIN / 90) / (mins + K_MIN) * 90
                if r["pos"] != "GK":
                    att_sum += att90
                if r["pos"] != "FWD":
                    conc_vals.append(conc90)
            xi_att = att_sum
            xi_def = float(np.mean(conc_vals)) if conc_vals else np.nan
            hist = recent.get(team, [])
            base_att = np.mean([h[0] for h in hist]) if hist else np.nan
            base_def = np.mean([h[1] for h in hist]) if hist else np.nan
            per_team[team] = (xi_att, xi_def, base_att, base_def, int(t["is_home"].iloc[0]),
                              str(t["opponent"].iloc[0]), len(starters))
        for team, (xa, xd, ba, bd, home, opp, n) in per_team.items():
            out.append({"match_key": mkey, "date": date, "team": team, "opponent": opp, "is_home": home,
                        "xi_att": xa, "xi_def": xd, "d_att": xa - ba, "d_def": xd - bd, "n_starters": n})
        # mise à jour des états APRÈS le calcul (pas de fuite d'information)
        for team, (xa, xd, *_r) in per_team.items():
            recent.setdefault(team, []).append((xa, xd))
            recent[team] = recent[team][-HISTORY:]
        for _, r in g[g["minutes"] > 0].iterrows():
            st = state.get(r["player_id"])
            if st:
                f = 0.5 ** ((date - st[3]).days / HALF_LIFE)
                st[0], st[1], st[2] = st[0] * f, st[1] * f, st[2] * f
            else:
                st = state[r["player_id"]] = [0.0, 0.0, 0.0, date]
            st[0] += r["minutes"]; st[1] += r["att"]; st[2] += r["conceded"]; st[3] = date
            pc = pos_cum[r["pos"]]
            pc[0] += r["minutes"]; pc[1] += r["att"]; pc[2] += r["conceded"]
    return pd.DataFrame(out)
