"""Offline "under the hood" data for the PitchPulse web app's demo mode.

Writes `frontend/public/demo/demo-insights.json` next to the demo match. The
web app loads it only when a viewer opens a trust panel in the offline demo
(the claim audit, the crew panel or the #lab view), so the match fixture
itself stays the same size.

What it holds, and where each part comes from:

- `audits`: one claim audit per demo moment, in the `MomentAudit` shape of
  `GET /api/match/moment/{id}/audit`. The sentences are the demo's own card
  texts (3 personas x en/es/ar); the claims, bindings, fact checks and
  cross-language parity are worked out by the server's own code
  (`matchmind.crew.claims`, `matchmind.crew.fact_checker`) against the
  moment's evidence. There is no crew trace: nothing ran a crew in the
  recording, so `trace` is empty and the app says so.
- `metrics`: the metric registry (`GET /api/metrics`), static.
- `auto_eventing`: the synthetic tracking-to-event benchmark for the demo
  match (`GET /api/auto-eventing`): detected from synthetic tracking, not video.
- `dataset`: the dataset index (`GET /api/dataset`). Downloads need the server.

Everything is deterministic: same input, byte-identical output.
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from typing import Any

from matchmind.crew import claims as claims_mod
from matchmind.crew.contracts import Moment, OverlayCard
from matchmind.crew.fact_checker import check_all

INSIGHTS_VERSION = 1
PERSONAS = ("casual", "tactical", "fantasy")
LANGS = ("en", "es", "ar")

# Demo evidence labels that carry a moment's key fact, under the server's fact keys
# (crew.claims.KEY_FACTS), so parity compares the same facts the server would.
KEY_LABELS: dict[str, str] = {
    "Scorer": "player",
    "Shooter": "player",
    "Player": "player",
    "Runner": "runner",
    "Free teammate": "teammate",
    "Assist": "assist",
    "Ball carrier": "carrier",
    # A card colour is a word, printed differently in each language ("yellow", "amarilla"):
    # it is kept as a fact but not compared across languages by value.
    "Card": "card_colour",
    "Times better": "times_better",
    "Chance quality": "xg",
    "Projected chance quality": "projected_xg",
    "Player speed": "speed_kmh",
    "Ball speed": "shot_speed_kmh",
    "Distance milestone": "milestone_km",
    "Momentum change (5 min)": "momentum_change",
    "Goal ruled out (scored at)": "ruled_out_clock",
    "Milestone": "milestone",
}
UNIT_SUFFIX = {"m": "_m", "km/h": "_kmh", "km": "_km", "xG": "_xg", "xA": "_xa", "%": "_pct", "s": "_s"}
# Server template keys (crew.wording) by demo kind.
TEMPLATE_KEY = {"milestone": "milestone.player"}


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _fact_key(label: str, unit: str | None) -> str:
    if label in KEY_LABELS:
        return KEY_LABELS[label]
    key = _slug(label.replace("(match)", "match").replace("(last 5 min)", "last5"))
    suffix = UNIT_SUFFIX.get(unit or "")
    if suffix and not key.endswith(suffix) and suffix.strip("_") not in key.split("_"):
        key += suffix
    return key


def moment_facts(m: dict, teams: dict) -> tuple[dict[str, Any], dict[str, str]]:
    """The moment's facts (from its evidence, under stable keys), and name -> squad id."""
    home, away = teams["home"], teams["away"]
    facts: dict[str, Any] = {"home": home["short_name"], "away": away["short_name"]}
    roster: dict[str, str] = {home["short_name"]: home["team_id"], away["short_name"]: away["team_id"]}
    for side in (home, away):
        for p in side["players"]:
            roster[p["name"]] = p["player_id"]
            roster[p["name"].split()[-1]] = p["player_id"]
    if m.get("team"):
        facts["team"] = home["short_name"] if m["team"] == home["team_id"] else away["short_name"]
    for ev in m["evidence"]:
        label, value = ev["label"], ev["value"]
        if label.endswith(" goals") and label.split()[0] in (home["team_id"], away["team_id"]):
            key = "score_home" if label.split()[0] == home["team_id"] else "score_away"
        else:
            key = _fact_key(label, ev.get("unit"))
        while key in facts and facts[key] != value:
            key += "_2"
        # "100th club appearance": the appearance number is the fact, printed as "100th" or "100".
        if isinstance(value, str) and key == "milestone" and (digits := re.search(r"\d+", value)):
            facts["appearance_n"] = int(digits.group(0))
            continue
        facts[key] = value
        # A full name is printed by surname in the cards: keep both, the surname as `<key>_short`.
        if isinstance(value, str) and value in roster and " " in value:
            facts[f"{key}_short"] = value.split()[-1]
    # Players the card is about, when no evidence row names them (a rocket shot, a speed burst).
    named = {v for v in facts.values() if isinstance(v, str)}
    for p in m.get("players") or []:
        if p["name"] in named:
            continue
        key = "player" if "player" not in facts else f"player_{len(named)}"
        facts[key] = p["name"]
        facts[f"{key}_short"] = p["name"].split()[-1]
        named.add(p["name"])
    return facts, roster


def _card(persona: str, lang: str, claims: list) -> OverlayCard:
    return OverlayCard.model_construct(persona=persona, language=lang, claims=claims)


def moment_audit(m: dict, teams: dict) -> dict[str, Any]:
    facts, roster = moment_facts(m, teams)
    moment = Moment(
        moment_id=m["moment_id"],
        kind=m["kind"],
        clock_s=m["show_at_s"],
        match_clock=m["match_clock"],
        period=m.get("period", 1),
        team=m.get("team"),
        player_ids=list(m["player_ids"]),
        facts=facts,
        source_event_ids=[m["event_id"]],
        priority=m["priority"],
        retracts=list(m.get("retracts") or []),
    )
    names = tuple(sorted(roster, key=len, reverse=True))
    renderings: list[dict[str, Any]] = []
    cards: list[OverlayCard] = []
    for persona in PERSONAS:
        for lang in LANGS:
            text = m["texts"].get(persona, {}).get(lang)
            if not text:
                continue
            claims = claims_mod.card_claims(
                moment, text["headline"], text["body"], text["why"], lang, roster=roster
            )
            parts = {"headline": text["headline"], "body": text["body"]}
            if text["why"]:
                parts["why"] = text["why"]
            check = check_all(parts, facts, lang, roster=names)
            cards.append(_card(persona, lang, claims))
            renderings.append(
                {
                    "persona": persona,
                    "language": lang,
                    "text_language": lang,
                    "source": "template_sweep",
                    "produced_by": "template",
                    "fallback_reason": None,
                    "translated_by": None,
                    "headline": text["headline"],
                    "body": text["body"],
                    "why": text["why"],
                    "fact_check": check.model_dump(),
                    "claims": [c.model_dump(exclude_none=False) for c in claims],
                }
            )
    kind = m["kind"]
    tkey = TEMPLATE_KEY.get(kind, kind)
    parity = claims_mod.fact_parity(moment, cards, 0, template_key=tkey)
    en = m["texts"].get("tactical", {}).get("en") or m["texts"].get("casual", {}).get("en") or {}
    return {
        "moment_id": m["moment_id"],
        "kind": kind,
        "match_clock": m["match_clock"],
        "period": m.get("period", 1),
        "team": m.get("team"),
        "player_ids": list(m["player_ids"]),
        "facts": facts,
        "source_event_ids": [m["event_id"]],
        "explanation": {
            "moment_id": m["moment_id"],
            "why": en.get("why", ""),
            "tactical_tag": m["tactical_tag"],
            "evidence": m["evidence"],
            "produced_by": "template",
            "fallback_reason": None,
        },
        "renderings": renderings,
        "parity": parity.model_dump(),
        "trace": [],
        "not_checked": list(claims_mod.NOT_CHECKED),
        "retracts": list(m.get("retracts") or []),
        "ruled_out_by": None,
    }


def build_insights(fixture: dict, events: list) -> dict[str, Any]:
    """`events`: the match as `matchmind.schema.Event` objects (for the benchmark)."""
    from matchmind import autoevent
    from matchmind.api.app import dataset_index
    from matchmind.stats.registry import registry_payload

    audits = {m["moment_id"]: moment_audit(m, fixture["teams"]) for m in fixture["moments"]}
    for m in fixture["moments"]:
        for target in m.get("retracts") or []:
            if target in audits:
                audits[target]["ruled_out_by"] = m["moment_id"]
    auto = autoevent.evaluate(events)
    if hasattr(auto, "model_dump"):
        auto = auto.model_dump()
    return {
        "insights_version": INSIGHTS_VERSION,
        "match_id": fixture["match_id"],
        "note": (
            "Recorded for the offline demo. Claims, fact checks and parity were worked out by the "
            "server's own checker against each demo card; no crew ran, so there is no trace."
        ),
        "audits": audits,
        "metrics": registry_payload(),
        "auto_eventing": auto,
        "dataset": dataset_index(),
    }


def insights_problems(insights: dict) -> list[str]:
    """Self-check: every rendering passed the fact-checker, and parity holds."""
    problems: list[str] = []
    for mid, a in insights["audits"].items():
        for r in a["renderings"]:
            if not r["fact_check"]["ok"]:
                problems.append(f"{mid} {r['persona']}/{r['language']}: {r['fact_check']['reasons'][:2]}")
        if not a["parity"]["ok"]:
            problems.append(f"{mid} parity: {a['parity']['problems'][:2]}")
    return problems
