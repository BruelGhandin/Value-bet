"""Normalisation des noms d'équipes (les sources écrivent les noms différemment)."""
ALIASES = {
    "man utd": "man united", "man united": "man united", "manchester united": "man united",
    "spurs": "tottenham", "tottenham": "tottenham", "tottenham hotspur": "tottenham",
    "nottm forest": "nott'm forest", "nott'm forest": "nott'm forest", "nottingham forest": "nott'm forest",
    "sheffield utd": "sheffield united", "sheffield united": "sheffield united",
    "coventry city": "coventry", "hull city": "hull", "ipswich town": "ipswich",
    "wolves": "wolves", "wolverhampton wanderers": "wolves",
    "newcastle": "newcastle", "newcastle united": "newcastle",
    "west brom": "west brom", "west bromwich albion": "west brom",
    "leeds": "leeds", "leeds united": "leeds", "leicester": "leicester", "leicester city": "leicester",
    "norwich": "norwich", "norwich city": "norwich", "brighton": "brighton", "brighton & hove albion": "brighton",
    "west ham": "west ham", "west ham united": "west ham", "luton": "luton", "luton town": "luton",
    "man city": "man city", "manchester city": "man city",
}


def canon(name: str) -> str:
    n = str(name).strip().lower().replace(".", "")
    return ALIASES.get(n, n)
