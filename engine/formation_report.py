"""Rapport formations (StatsBomb) : quelles formations gagnent, contre quelles formations, quels joueurs à quel poste.

    python update.py --only statsbomb      # remplit les compositions (incrémental)
    python formation_report.py

Attention aux petits échantillons : une combinaison équipe/formation/joueur apparaît rarement.
Les colonnes `n` (matchs) sont données pour juger la fiabilité ; les seuils minimaux sont réglables.
"""
import numpy as np
import pandas as pd

from src.store import Store

MIN_TEAM_FORMATION = 8     # matchs minimum pour une équipe avec une formation
MIN_MATCHUP = 30           # matchs minimum pour un duel formation contre formation
MIN_PLAYER_COMBO = 8       # matchs minimum pour joueur + poste + formation


def load(store: Store) -> pd.DataFrame:
    """Une ligne par équipe et par match : formation, adversaire, formation adverse, points, différence de buts."""
    m = pd.read_sql_query("SELECT * FROM sb_matches", store.db)
    f = pd.read_sql_query("SELECT DISTINCT match_id, team, formation FROM sb_lineups", store.db)
    h = m.rename(columns={"home": "team", "away": "opp", "home_goals": "gf", "away_goals": "ga"})[
        ["match_id", "competition", "season", "gender", "date", "team", "opp", "gf", "ga"]]
    a = m.rename(columns={"away": "team", "home": "opp", "away_goals": "gf", "home_goals": "ga"})[
        ["match_id", "competition", "season", "gender", "date", "team", "opp", "gf", "ga"]]
    t = pd.concat([h, a])
    t = t.merge(f, on=["match_id", "team"]).merge(
        f.rename(columns={"team": "opp", "formation": "opp_formation"}), on=["match_id", "opp"])
    t["pts"] = np.where(t["gf"] > t["ga"], 3, np.where(t["gf"] == t["ga"], 1, 0))
    t["gd"] = t["gf"] - t["ga"]
    t["win"] = (t["gf"] > t["ga"]).astype(int)
    return t


def main():
    store = Store()
    t = load(store)
    print(f"{t['match_id'].nunique()} matchs avec formations des deux équipes\n")

    # Ajustement : on retire le niveau moyen de l'équipe (sinon une formation « gagne » surtout parce que les
    # meilleures équipes l'utilisent). Effet = différence de buts du match moins la moyenne de l'équipe, adversaire compris.
    t["gd_vs_team"] = t["gd"] - t.groupby("team")["gd"].transform("mean") + t.groupby("opp")["gd"].transform("mean") * 0
    by_f = t.groupby("formation").agg(n=("pts", "size"), pts_par_match=("pts", "mean"),
                                       diff_buts=("gd", "mean"), diff_buts_ajustee=("gd_vs_team", "mean"),
                                       victoires=("win", "mean")).round(2)
    by_f = by_f[by_f["n"] >= 30].sort_values("pts_par_match", ascending=False)
    print("== Formations (toutes équipes), au moins 30 matchs ==\n(diff_buts_ajustee = après retrait du niveau habituel de l'équipe : l'effet propre de la formation)")
    print(by_f.to_string(), "\n")

    tf = t.groupby(["team", "formation"]).agg(n=("pts", "size"), pts_par_match=("pts", "mean"),
                                               diff_buts=("gd", "mean")).round(2).reset_index()
    tf = tf[tf["n"] >= MIN_TEAM_FORMATION].sort_values("pts_par_match", ascending=False)
    print(f"== Meilleures formations par équipe (>= {MIN_TEAM_FORMATION} matchs) ==")
    print(tf.head(15).to_string(index=False), "\n")

    mu = t.groupby(["formation", "opp_formation"]).agg(n=("pts", "size"), pts_par_match=("pts", "mean"),
                                                        diff_buts=("gd", "mean")).round(2).reset_index()
    mu = mu[(mu["n"] >= MIN_MATCHUP) & (mu["formation"] != mu["opp_formation"])].sort_values("pts_par_match", ascending=False)
    print(f"== Duels de formations (>= {MIN_MATCHUP} matchs) ==")
    print(mu.head(10).to_string(index=False), "\n...\n", mu.tail(5).to_string(index=False), "\n")

    lu = pd.read_sql_query("SELECT match_id, team, formation, player, position FROM sb_lineups", store.db)
    pc = lu.merge(t[["match_id", "team", "pts", "gd"]], on=["match_id", "team"])
    pc = pc.groupby(["team", "formation", "position", "player"]).agg(
        n=("pts", "size"), pts_par_match=("pts", "mean"), diff_buts=("gd", "mean")).round(2).reset_index()
    pc = pc[pc["n"] >= MIN_PLAYER_COMBO].sort_values(["pts_par_match", "n"], ascending=False)
    print(f"== Joueur + poste + formation (>= {MIN_PLAYER_COMBO} matchs) : indicatif, petits échantillons ==")
    print(pc.head(15).to_string(index=False))

    by_f.to_csv("results/formations_globales.csv")
    tf.to_csv("results/formations_par_equipe.csv", index=False)
    mu.to_csv("results/formations_duels.csv", index=False)
    pc.to_csv("results/joueur_poste_formation.csv", index=False)


if __name__ == "__main__":
    main()
