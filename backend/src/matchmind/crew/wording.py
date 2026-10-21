"""Shared wording helpers: which template a moment uses and the variables a
template may print (the moment's facts plus localised words derived from them)."""

from __future__ import annotations

from typing import Any

from matchmind.crew.contracts import Moment, MomentKind
from matchmind.crew.i18n import ordinal_en, pack

TEAM_KEYS = ("team", "opp", "home", "away", "winner", "loser", "potm_team", "subject")


def template_key(moment: Moment) -> str:
    if moment.kind == MomentKind.MILESTONE:
        return f"milestone.{moment.facts.get('phase', 'kick_off')}"
    return moment.kind.value


def localise_teams(variables: dict[str, Any], language: str, favourite_name: str | None) -> dict[str, Any]:
    """Phrase it from the viewer's side: the favourite club becomes "your team"."""
    if not favourite_name:
        return variables
    mine = pack(language)["your_team"]
    for key in TEAM_KEYS:
        if variables.get(key) == favourite_name:
            variables[key] = mine
    return variables


def variables(moment: Moment, language: str, favourite_name: str | None = None) -> dict[str, Any]:
    p = pack(language)
    v: dict[str, Any] = dict(moment.facts)
    zone = moment.facts.get("pitch_zone", "")
    v["zone"] = p["zones"].get(zone, p["zones"][""])
    outcome = str(moment.facts.get("outcome", ""))
    v["outcome_phrase"] = p["outcomes"].get(outcome, p["outcomes"][""])
    card = str(moment.facts.get("card", "yellow"))
    v["card_name"] = p["card_name"].get(card, p["card_name"]["yellow"])
    v["card_name_cap"] = p["card_name_cap"].get(card, p["card_name_cap"]["yellow"])
    v["card_action"] = p["card_action"].get(card, p["card_action"]["yellow"])
    n = moment.facts.get("appearance_n")
    if isinstance(n, int) and not isinstance(n, bool):
        v["appearance_nth"] = ordinal_en(n)
    return localise_teams(v, language, favourite_name)
