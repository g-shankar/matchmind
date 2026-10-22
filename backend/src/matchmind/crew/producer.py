"""Producer: turns voiced moments into timed overlay cards for one viewer.

Deterministic rules:
- slot by kind (speed and distance tags go on the pitch, replays to the side
  panel, goals full screen, the rest as lower thirds);
- persona filter (each audience sees the kinds it cares about);
- the favourite club's moments get +15 priority and `favourite_side`;
- moments about the focus player are always kept and boosted;
- de-duplicated by moment id per viewer;
- at most one lower third per 8 s of match clock (extra ones move to the
  side panel, or are dropped when minor);
- corrections: a card that rules earlier moments out (`retracts`) is always
  kept, and a card for a moment already ruled out is never shown, even if it
  arrives late or twice (out-of-order or repeated delivery).
Per-viewer memory lives in `ViewerState`, one per connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from matchmind.crew.contracts import (
    RTL_LANGUAGES,
    Evidence,
    MomentBundle,
    MomentKind,
    Narrative,
    OverlayCard,
    Slot,
    ViewerProfile,
)
from matchmind.crew.i18n import pack

if TYPE_CHECKING:
    from matchmind.crew.cues import Cue, CueCompiler

LOWER_THIRD_GAP_S = 8.0
FAVOURITE_BOOST = 15
FOCUS_BOOST = 20
MINOR_PRIORITY = 50
SEEN_LIMIT = 5000

SLOT_BY_KIND: dict[MomentKind, Slot] = {
    MomentKind.GOAL: "full_screen",
    MomentKind.CORRECTION: "full_screen",
    MomentKind.BETTER_OPTION: "side_panel",
    MomentKind.UNFOUND_RUN: "side_panel",
    MomentKind.SPEED_BURST: "pitch_tag",
    MomentKind.DISTANCE_MILESTONE: "pitch_tag",
    MomentKind.ROCKET_SHOT: "pitch_tag",
}
DURATION_S: dict[str, float] = {
    "full_screen": 8.0,
    "lower_third": 7.0,
    "side_panel": 12.0,
    "pitch_tag": 4.0,
    "metric_alert": 5.0,
}

ALL_KINDS = frozenset(MomentKind)
PERSONA_KINDS: dict[str, frozenset[MomentKind]] = {
    "casual": ALL_KINDS - {MomentKind.HARD_PASS, MomentKind.PRESSURE_SPELL},
    "tactical": ALL_KINDS - {MomentKind.DISTANCE_MILESTONE},
    "fantasy": frozenset(
        {
            MomentKind.GOAL,
            MomentKind.CARD,
            MomentKind.BIG_CHANCE,
            MomentKind.BETTER_OPTION,
            MomentKind.UNFOUND_RUN,
            MomentKind.ROCKET_SHOT,
            MomentKind.MILESTONE,
            MomentKind.CORRECTION,
        }
    ),
    "player_spotlight": frozenset({MomentKind.GOAL, MomentKind.MILESTONE, MomentKind.CORRECTION}),
}
ALWAYS_SHOW_PRIORITY = 80  # big moments reach every audience


@dataclass
class ViewerState:
    """What the producer remembers for one viewer (one WebSocket)."""

    last_lower_third_s: float | None = None
    seen: dict[str, None] = field(default_factory=dict)
    metric_baseline: dict[str, float] = field(default_factory=dict)
    last_metric_alert: dict[str, tuple[int, float]] = field(default_factory=dict)
    ruled_out: dict[str, None] = field(default_factory=dict)  # moment ids a correction retracted
    cues: CueCompiler | None = None  # this viewer's cue sheet, from where they joined
    cue_active: list[Cue] | None = None  # what was on air when the sheet was (re)started, sent once

    def fork(self) -> ViewerState:
        """An independent copy (a new viewer joining at a compiled position)."""
        return ViewerState(
            last_lower_third_s=self.last_lower_third_s,
            seen=dict(self.seen),
            metric_baseline=dict(self.metric_baseline),
            last_metric_alert=dict(self.last_metric_alert),
            ruled_out=dict(self.ruled_out),
            cues=self.cues.fork() if self.cues is not None else None,
            cue_active=list(self.cue_active) if self.cue_active is not None else None,
        )

    def remember(self, moment_id: str) -> None:
        self.seen[moment_id] = None
        while len(self.seen) > SEEN_LIMIT:
            self.seen.pop(next(iter(self.seen)))

    def rule_out(self, moment_ids: list[str]) -> None:
        for mid in moment_ids:
            self.ruled_out[mid] = None
        while len(self.ruled_out) > SEEN_LIMIT:
            self.ruled_out.pop(next(iter(self.ruled_out)))

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]


def favourite_side(team: str | None, profile: ViewerProfile) -> bool | None:
    if not profile.favourite_team or team is None:
        return None
    return team == profile.favourite_team


def localise_evidence(items: list[Evidence], language: str) -> list[Evidence]:
    """Copies of the evidence with labels in the card's language (English, then
    the existing label, when a pack has no entry)."""
    out: list[Evidence] = []
    for item in items:
        key = item.label_key
        label = item.label
        if key:
            label = (
                pack(language).get("labels", {}).get(key) or pack("en").get("labels", {}).get(key) or label
            )
        out.append(item.model_copy(update={"label": label}))
    return out


def build_card(
    bundle: MomentBundle,
    narrative: Narrative,
    why: str,
    profile: ViewerProfile,
    slot: Slot | None = None,
    evidence: list[Evidence] | None = None,
) -> OverlayCard:
    m = bundle.moment
    chosen: Slot = slot or SLOT_BY_KIND.get(m.kind, "lower_third")
    priority = m.priority
    fav = favourite_side(m.team, profile)
    if fav:
        priority += FAVOURITE_BOOST
    if profile.focus_player_id and profile.focus_player_id in m.player_ids:
        priority += FOCUS_BOOST
    produced_by = (
        "ai" if narrative.produced_by == "ai" and bundle.explanation.produced_by == "ai" else "template"
    )
    reason = narrative.fallback_reason or bundle.explanation.fallback_reason
    return OverlayCard(
        card_id=f"{m.moment_id}:{profile.persona}:{profile.language}",
        moment_id=m.moment_id,
        kind=m.kind,
        slot=chosen,
        priority=min(100, priority),
        show_at_s=m.clock_s,
        duration_s=DURATION_S[chosen],
        persona=profile.persona,
        language=profile.language,
        rtl=profile.language in RTL_LANGUAGES,
        headline=narrative.headline,
        body=narrative.body,
        why=why,
        tactical_tag=bundle.explanation.tactical_tag,
        evidence=localise_evidence(
            evidence if evidence is not None else bundle.explanation.evidence, profile.language
        ),
        player_ids=list(m.player_ids),
        team=m.team,
        favourite_side=fav,
        produced_by=produced_by,
        fallback_reason=reason,
        replay=bundle.replay,
        retracts=list(m.retracts),
    )


def wanted(card: OverlayCard, profile: ViewerProfile) -> bool:
    if profile.focus_player_id and profile.focus_player_id in card.player_ids:
        return True
    if card.slot == "metric_alert":
        return True
    persona = profile.persona
    if persona == "player_spotlight" and not profile.focus_player_id:
        persona = "casual"
    if card.kind in PERSONA_KINDS[persona]:
        return True
    return card.priority >= ALWAYS_SHOW_PRIORITY and persona != "fantasy"


def select(cards: list[OverlayCard], profile: ViewerProfile, state: ViewerState) -> list[OverlayCard]:
    """Filter, de-duplicate and time cards for one viewer; highest priority first."""
    out: list[OverlayCard] = []
    batch: set[str] = set()
    for card in cards:
        if card.retracts:
            state.rule_out(card.retracts)
    for card in sorted(cards, key=lambda c: (-c.priority, c.show_at_s, c.card_id)):
        key = card.moment_id
        if key in state.seen or key in batch or key in state.ruled_out:
            continue
        if not card.retracts and not wanted(card, profile):
            continue
        if card.slot == "lower_third":
            last = state.last_lower_third_s
            # A clock that jumps backwards (second half restarts at 2700 s, or
            # a seek) starts a fresh gap instead of blocking lower thirds.
            if last is not None and 0 <= card.show_at_s - last < LOWER_THIRD_GAP_S:
                focus = bool(profile.focus_player_id and profile.focus_player_id in card.player_ids)
                if card.priority < MINOR_PRIORITY and not focus:
                    continue
                card = card.model_copy(update={"slot": "side_panel", "duration_s": DURATION_S["side_panel"]})
            else:
                state.last_lower_third_s = card.show_at_s
        batch.add(key)
        state.remember(key)
        out.append(card)
    return out
