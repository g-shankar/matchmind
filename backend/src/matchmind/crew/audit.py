"""Moment audit: everything behind one moment, for `GET /api/match/moment/{id}/audit`.

The audit shows the moment's facts and source events, the Analyst's evidence,
every rendering's sentences with their claims and fact-check outcome, the
cross-persona and cross-language parity result, and the crew's trace steps.

Renderings come from two places, and the audit never spends on paid AI:
- `template_sweep`: every persona x studio language, voiced by the template-only
  crew the session already keeps for bookmarks (no model, no translator);
- `live`: cards the live crew has already rendered for this moment (model text or
  translations included), read from its cache, never rendered for the audit.
"""

from __future__ import annotations

from typing import Any

from matchmind.crew import claims as claims_mod
from matchmind.crew.contracts import (
    PERSONAS,
    STUDIO_LANGUAGES,
    FactCheck,
    MomentAudit,
    MomentBundle,
    OverlayCard,
    RenderingAudit,
    ViewerProfile,
)
from matchmind.crew.fact_checker import check_all

LIVE_LIMIT = 16


def _fact_check(card: OverlayCard, bundle: MomentBundle, roster: tuple[str, ...]) -> FactCheck:
    """The production check, run again on what the viewer saw (model text gets the
    strict number-word rule, translations the roomier length rule)."""
    parts: dict[str, Any] = {"headline": card.headline, "body": card.body}
    if card.why:
        parts["why"] = card.why
    language = card.text_language or card.language
    return check_all(
        parts,
        bundle.moment.facts,
        language,
        # Model text gets the strict number-word rule, as when the crew checked it.
        strict_words=card.translated_by is None and not claims_mod.templated(card),
        translated=card.translated_by is not None,
        roster=roster or None,
    )


def _with_claims(card: OverlayCard, bundle: MomentBundle, roster_ids: dict[str, str]) -> OverlayCard:
    """Cards made before claims existed (or by a stand-in crew) get them by matching."""
    if card.claims:
        return card
    language = card.text_language or card.language
    found = claims_mod.card_claims(
        bundle.moment, card.headline, card.body, card.why, language, roster=roster_ids or None
    )
    return card.model_copy(update={"claims": found})


def _rendering(
    card: OverlayCard, source: str, bundle: MomentBundle, roster: tuple[str, ...]
) -> RenderingAudit:
    return RenderingAudit(
        persona=card.persona,
        language=card.language,
        text_language=card.text_language,
        source=source,  # type: ignore[arg-type]
        produced_by=card.produced_by,
        fallback_reason=card.fallback_reason,
        translated_by=card.translated_by,
        headline=card.headline,
        body=card.body,
        why=card.why,
        fact_check=_fact_check(card, bundle, roster),
        claims=card.claims,
    )


def moment_audit(bundle: MomentBundle, sweep_crew: Any, live_crew: Any | None = None) -> MomentAudit:
    """`sweep_crew` must be template-only (it renders); `live_crew` is only read."""
    m = bundle.moment
    roster: tuple[str, ...] = tuple(getattr(sweep_crew, "protected_names", ()) or ())
    roster_ids: dict[str, str] = dict(getattr(sweep_crew, "roster_ids", {}) or {})
    sweep: list[OverlayCard] = []
    withheld = 0
    for persona in PERSONAS:
        focus = m.player_ids[0] if persona == "player_spotlight" and m.player_ids else None
        for language in STUDIO_LANGUAGES:
            card = sweep_crew.render(
                bundle, ViewerProfile(persona=persona, language=language, focus_player_id=focus)
            )
            if card is None:
                withheld += 1
            else:
                sweep.append(_with_claims(card, bundle, roster_ids))
    live: list[OverlayCard] = []
    cached = getattr(live_crew, "cached_cards", None) if live_crew is not None else None
    if callable(cached):
        live = [_with_claims(c, bundle, roster_ids) for c in cached(m.moment_id, LIVE_LIMIT)]

    cards = sweep + live
    sources = ["template_sweep"] * len(sweep) + ["live"] * len(live)
    parity = claims_mod.fact_parity(m, cards, withheld, sources=sources)

    trace = None
    for crew in (live_crew, sweep_crew):
        trace_for = getattr(crew, "trace_for", None) if crew is not None else None
        if callable(trace_for):
            trace = trace_for(m.moment_id)
            if trace is not None:
                break
    return MomentAudit(
        moment_id=m.moment_id,
        kind=m.kind,
        match_clock=m.match_clock,
        period=m.period,
        team=m.team,
        player_ids=list(m.player_ids),
        facts=dict(m.facts),
        source_event_ids=list(m.source_event_ids),
        explanation=bundle.explanation,
        renderings=[_rendering(c, s, bundle, roster) for c, s in zip(cards, sources, strict=True)],
        parity=parity,
        trace=list(trace.steps) if trace is not None else [],
        not_checked=list(claims_mod.NOT_CHECKED),
    )
