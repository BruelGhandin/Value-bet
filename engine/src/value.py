"""Value bets, retrait de la marge du bookmaker et gestion de mise."""


def devig(odds_h: float, odds_d: float, odds_a: float) -> tuple[float, float, float]:
    """Probabilités implicites du marché, normalisées (marge retirée)."""
    inv = (1 / odds_h, 1 / odds_d, 1 / odds_a)
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def edge(p_model: float, odds: float) -> float:
    """Avantage espéré par unité misée : p * cote - 1."""
    return p_model * odds - 1.0


def kelly_fraction(p_model: float, odds: float, fraction: float = 0.25) -> float:
    """Kelly fractionné (prudent). Retourne la part de la bankroll à miser."""
    b = odds - 1.0
    if b <= 0:
        return 0.0
    k = (p_model * b - (1 - p_model)) / b
    return max(0.0, k) * fraction


def best_value_bet(preds: dict, odds: dict, min_edge: float = 0.05, max_edge: float = 0.30):
    """preds/odds : clés 'home','draw','away'. Retourne le meilleur pari (ou None).

    max_edge écarte les « avantages » énormes, presque toujours des erreurs du modèle.
    """
    best = None
    for k, p in preds.items():
        o = odds.get(k)
        if not o or o != o:  # None ou NaN
            continue
        e = edge(p, o)
        if min_edge <= e <= max_edge and (best is None or e > best["edge"]):
            best = {"outcome": k, "p": p, "odds": o, "edge": e}
    return best
