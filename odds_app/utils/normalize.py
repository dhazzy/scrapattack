import re
import unicodedata


TEAM_STOP_WORDS = {
    "fc",
    "cf",
    "sc",
    "fk",
    "u19",
    "u21",
    "u23",
    "women",
    "w",
    "reserves",
    "ii",
}


def normalize_team_name(raw_name: str) -> str:
    value = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode()
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    tokens = [tok for tok in value.split() if tok and tok not in TEAM_STOP_WORDS]
    return " ".join(tokens)


def canonical_match_key(home_team: str, away_team: str) -> tuple[str, str]:
    home = normalize_team_name(home_team)
    away = normalize_team_name(away_team)
    return home, away
