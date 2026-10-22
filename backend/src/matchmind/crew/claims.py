"""Claims: every sentence a viewer sees, tied to the facts and events behind it.

A card's headline, body and explanation (and a recap's title, headline,
paragraphs and key-moment lines) are split into sentences (Latin, Arabic and
Japanese punctuation). Each sentence becomes a `Claim`:

- every number is bound to the fact key it prints ("3.1x" -> `times_better`),
  every squad name to its player or club id;
- template text knows its fact keys exactly, from the template's placeholders;
  model and machine-translated text gets them by matching values to facts
  (and the unit printed next to a number picks between equal values);
- `check` says what the machine verified: `verified_numeric` (all numbers are
  facts), `verified_name` (no numbers; the names are facts) or
  `unverified_text` (nothing checkable, or a check failed, see `reason`).

Never claimed as verified: tone, causal wording ("so they have to adjust"),
negation and comparisons beyond the bounded rules in the fact-checker. The
reason on every claim says so.

`fact_parity` checks one moment across audiences: every rendering may use only
the moment's facts, states the moment's anchor (who or what it is about), and
for each persona every language states the same key facts as English.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from matchmind.crew.contracts import (
    Claim,
    ClaimBinding,
    FactParity,
    FactValue,
    Moment,
    OverlayCard,
)
from matchmind.crew.fact_checker import (
    key_unit,
    matching_keys,
    number_spans,
    sanity_problems,
    string_fact_spans,
)
from matchmind.crew.i18n import pack, placeholder_keys
from matchmind.crew.wording import template_key as key_of

MAX_CLAIMS = 40
MAX_SOURCE_IDS = 12
MAX_PROBLEMS = 40
MAX_STATED = 64

# Template variables that are words derived from a fact, not the fact itself.
DERIVED_KEYS: dict[str, str] = {
    "zone": "pitch_zone",
    "outcome_phrase": "outcome",
    "card_name": "card",
    "card_name_cap": "card",
    "card_action": "card",
    "appearance_nth": "appearance_n",
}
# Two keys for one entity (full name and surname).
ENTITY_ALIASES: dict[str, str] = {
    "player_short": "player",
    "teammate_short": "teammate",
    "runner_short": "runner",
    "receiver_short": "receiver",
    "assist_short": "assist",
    "potm_short": "potm",
}

# A sentence ends at . ! ? (Latin), ؟ (Arabic), । (Devanagari) when a space or the
# end follows, or at 。！？ (Japanese, Chinese) anywhere. Decimal points ("0.31")
# and the abbreviations below never end a sentence.
_END = re.compile(r"[。！？]+[」』”’)）»]*|[.!?؟।]+[\"'”’)）»]*(?=\s|$)")
_ABBREVIATION = re.compile(r"(?:\b(?:est|approx|vs|etc|env|aprox)\.)$", re.IGNORECASE)

NOT_CHECKED = (
    "Tone, wording and causal claims (why something happened) are not machine-verified.",
    "Negation is not checked: 'did not score' and 'scored' read the same to the checker.",
    "Comparisons are checked only for 'more/less than' and multipliers in English, Spanish and French.",
    "Attribution is checked for per-club numbers (score, xG, shots) printed right after a club name, "
    "and for 'A 2-1 B' scorelines; a player's number next to another player's name is not.",
    "Number words ('three') are checked only in model text; templates use words such as 'first half'.",
)


def split_sentences(text: str) -> list[str]:
    """Script-aware sentence split; keeps the punctuation, drops empty parts."""
    out: list[str] = []
    start = 0
    for m in _END.finditer(text):
        piece = text[start : m.end()]
        if _ABBREVIATION.search(piece.rstrip("\"'”’)）»")):
            continue
        out.append(piece.strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def template_fact_keys(template: str, facts: Mapping[str, FactValue]) -> list[str]:
    """The fact keys a template sentence prints (derived words map to their fact)."""
    keys: list[str] = []
    for key in placeholder_keys(template):
        key = DERIVED_KEYS.get(key, key)
        if key in facts and key not in keys:
            keys.append(key)
    return keys


def _entity(name: str, roster: Mapping[str, str] | None) -> str | None:
    return roster.get(name) if roster else None


def _pick(
    token: str, facts: Mapping[str, FactValue], unit: str | None, preferred: Sequence[str]
) -> str | None:
    """The fact key a number is bound to: the template's own keys first, then the
    closest value ("0" is score 0 before xG 0.13), then the unit printed."""
    candidates = matching_keys(token, facts)
    if not candidates:
        return None
    pool = [k for k in candidates if k in preferred] or candidates
    n = float(token)
    pool.sort(key=lambda k: abs(abs(float(facts[k])) - n))  # type: ignore[arg-type]
    if unit:
        pool = [k for k in pool if key_unit(k) == unit] or pool
    return pool[0]


def sentence_claim(
    sentence: str,
    field: str,
    facts: Mapping[str, FactValue],
    language: str,
    *,
    template: str | None = None,
    source_event_ids: Sequence[str] = (),
    key_sources: Mapping[str, Sequence[str]] | None = None,
    roster: Mapping[str, str] | None = None,
    favourite: tuple[str, str] | None = None,
) -> Claim:
    """One sentence, its bindings and what was verified about it. `favourite` is
    (the language's "your team" phrase, the viewer's club name): a framed template
    that writes "your team" states that club."""
    template_keys = template_fact_keys(template, facts) if template is not None else []
    bindings: list[ClaimBinding] = []
    names: list[str] = []
    for span, keys in string_fact_spans(sentence, facts):
        chosen = [k for k in keys if k in template_keys] or keys
        entity = _entity(span.text, roster)
        bindings.append(
            ClaimBinding(
                text=span.text,
                kind="name" if entity else "text",
                fact_key=chosen[0],
                value=facts[chosen[0]],
                entity_id=entity,
            )
        )
        if entity:
            names.append(span.text)
    if favourite and favourite[0]:
        phrase, club = favourite
        at = sentence.casefold().find(phrase.casefold())
        keys = [k for k, v in facts.items() if v == club]
        if at != -1 and keys:
            chosen = [k for k in keys if k in template_keys] or keys
            printed = sentence[at : at + len(phrase)]
            bindings.append(
                ClaimBinding(
                    text=printed,
                    kind="name",
                    fact_key=chosen[0],
                    value=club,
                    entity_id=_entity(club, roster),
                )
            )
            names.append(printed)
    unbound: list[str] = []
    numbers: list[str] = []
    for n in number_spans(sentence, language, facts):
        numbers.append(n.text)
        key = _pick(n.token, facts, n.unit, template_keys)
        if key is None:
            unbound.append(n.text)
        bindings.append(
            ClaimBinding(
                text=n.text,
                kind="number",
                fact_key=key,
                value=facts[key] if key else None,
                unit=n.unit,
            )
        )
    bindings.sort(key=lambda b: sentence.find(b.text))

    if template is not None:
        fact_keys = list(template_keys)
        fact_keys += [b.fact_key for b in bindings if b.fact_key and b.fact_key not in fact_keys]
    else:
        fact_keys = list(dict.fromkeys(b.fact_key for b in bindings if b.fact_key))

    origin = "template filled from facts" if template is not None else "matched to facts"
    problems = [f"number {t} is not in the facts" for t in unbound]
    problems += sanity_problems(sentence, facts, language)
    if problems:
        check, reason = "unverified_text", "; ".join(problems[:3])
    elif numbers:
        bound = ", ".join(dict.fromkeys(b.fact_key for b in bindings if b.kind == "number" and b.fact_key))
        check = "verified_numeric"
        reason = f"{len(numbers)} of {len(numbers)} numbers {origin} ({bound}); wording not machine-checked"
    elif names:
        check = "verified_name"
        reason = f"names {origin} ({', '.join(dict.fromkeys(names))}); wording not machine-checked"
    else:
        check = "unverified_text"
        reason = "no number or squad name to check; tone and wording are not machine-verified"

    sources = list(source_event_ids)
    for key in fact_keys:
        sources += list((key_sources or {}).get(key, ()))
    return Claim(
        sentence=sentence,
        field=field,  # type: ignore[arg-type]
        fact_keys=fact_keys,
        numbers=numbers,
        source_event_ids=list(dict.fromkeys(sources))[:MAX_SOURCE_IDS],
        check=check,  # type: ignore[arg-type]
        reason=reason,
        origin="template" if template is not None else "matched",
        bindings=bindings,
    )


def text_claims(
    text: str,
    field: str,
    facts: Mapping[str, FactValue],
    language: str,
    *,
    template: str | None = None,
    source_event_ids: Sequence[str] = (),
    key_sources: Mapping[str, Sequence[str]] | None = None,
    roster: Mapping[str, str] | None = None,
    favourite: tuple[str, str] | None = None,
) -> list[Claim]:
    """Claims for every sentence of one field. With the template, each sentence
    takes the placeholders of the matching template sentence (or, when the
    sentence counts differ, of the whole template)."""
    sentences = split_sentences(text)
    templates: list[str | None] = [None] * len(sentences)
    if template is not None:
        parts = split_sentences(template)
        templates = parts if len(parts) == len(sentences) else [template] * len(sentences)
    return [
        sentence_claim(
            s,
            field,
            facts,
            language,
            template=t,
            source_event_ids=source_event_ids,
            key_sources=key_sources,
            roster=roster,
            favourite=favourite,
        )
        for s, t in zip(sentences, templates, strict=True)
    ]


def card_claims(
    moment: Moment,
    headline: str,
    body: str,
    why: str,
    language: str,
    *,
    templates: Mapping[str, str | None] | None = None,
    roster: Mapping[str, str] | None = None,
    favourite_name: str | None = None,
) -> list[Claim]:
    """Claims for a card's headline, body and why, all tied to the moment's events.
    With the viewer's club, "your team" in the card's language counts as that club."""
    favourite = (pack(language)["your_team"], favourite_name) if favourite_name else None
    templates = templates or {}
    out: list[Claim] = []
    for field, text in (("headline", headline), ("body", body), ("why", why)):
        if text:
            out += text_claims(
                text,
                field,
                moment.facts,
                language,
                template=templates.get(field),
                source_event_ids=moment.source_event_ids,
                roster=roster,
                favourite=favourite,
            )
    return out[:MAX_CLAIMS]


# ------------------------------------------------------------------ parity

# Per moment kind (template key): the facts every rendering must agree on, and
# the anchor groups (who or what the moment is about) every rendering must state.
KEY_FACTS: dict[str, tuple[str, ...]] = {
    "goal": ("player", "team", "score_home", "score_away"),
    "correction": ("player", "score_home", "score_away", "ruled_out_clock"),
    "card": ("player", "card"),
    "big_chance": ("player", "xg"),
    "better_option": ("player", "teammate", "times_better"),
    "unfound_run": ("runner", "projected_xg"),
    "momentum_swing": ("team", "momentum_change"),
    "pressure_spell": ("team", "pressure_index"),
    "speed_burst": ("player", "speed_kmh"),
    "rocket_shot": ("player", "shot_speed_kmh"),
    "distance_milestone": ("player", "milestone_km"),
    "hard_pass": ("player", "pass_difficulty"),
    "key_tackle": ("player", "own_goal_distance_m"),
    "milestone.kick_off": ("home", "away"),
    "milestone.half_time": ("home", "away", "score_home", "score_away"),
    "milestone.full_time": ("home", "away", "score_home", "score_away"),
    "milestone.player": ("player", "appearance_n"),
}
ANCHORS: dict[str, tuple[tuple[str, ...], ...]] = {
    "goal": (("player", "team"),),
    "correction": (("player",),),
    "card": (("player",),),
    "big_chance": (("player", "team"),),
    "better_option": (("player", "teammate"),),
    "unfound_run": (("runner", "player"),),
    "momentum_swing": (("team",),),
    "pressure_spell": (("team",),),
    "speed_burst": (("player",),),
    "rocket_shot": (("player",),),
    "distance_milestone": (("player",),),
    "hard_pass": (("player",),),
    "key_tackle": (("player",),),
    "milestone.kick_off": (("home",), ("away",)),
    "milestone.half_time": (("score_home",), ("score_away",)),
    "milestone.full_time": (("score_home",), ("score_away",)),
    "milestone.player": (("player",),),
}
_SIDES = ("home", "away", "winner", "loser", "opp")


def _entity_key(key: str) -> str:
    return ENTITY_ALIASES.get(key, key)


def stated_facts(
    claims: Iterable[Claim], moment: Moment, fields: Sequence[str] = ("headline", "body")
) -> set[str]:
    """Fact keys (surnames folded into the full-name key) the given fields state.
    A club printed as "your team" counts as the club (its template key is kept)."""
    stated: set[str] = set()
    for c in claims:
        if c.field in fields:
            stated.update(_entity_key(k) for k in c.fact_keys)
    # A name printed once is every key that holds it: "team" and "home" are often the same club.
    for key in list(stated):
        value = moment.facts.get(key)
        if isinstance(value, str):
            stated.update(_entity_key(k) for k, v in moment.facts.items() if v == value)
    return stated


def _matched(card: OverlayCard, moment: Moment) -> set[str]:
    """Facts the headline and body state, by printed value only (no template keys)."""
    stated: set[str] = set()
    for c in card.claims:
        if c.field not in ("headline", "body"):
            continue
        for n in number_spans(c.sentence, card.language, moment.facts):
            stated.update(_entity_key(k) for k in matching_keys(n.token, moment.facts))
        for _, keys in string_fact_spans(c.sentence, moment.facts):
            stated.update(_entity_key(k) for k in keys)
    return stated


def fact_parity(
    moment: Moment,
    cards: Sequence[OverlayCard],
    withheld: int = 0,
    template_key: str | None = None,
    sources: Sequence[str] | None = None,
) -> FactParity:
    """Cross-persona and cross-language parity for one moment's renderings.

    1. Every rendering uses only the moment's facts (no claim failed a check, no
       unbound number).
    2. Every rendering states each anchor group (who or what the moment is about).
    3. For each persona, every language states the same key facts as English from
       the same source (template text compared by template keys, model or
       translated text by printed values); `sources` (parallel to `cards`, e.g.
       "template_sweep" or "live") keeps live cards apart from the sweep, and a
       live card with no live English card is compared with the sweep's.
    """
    tkey = template_key or key_of(moment)
    key_facts = tuple(k for k in KEY_FACTS.get(tkey, ()) if k in moment.facts)
    keyset = set(key_facts)
    anchors = tuple(
        g for g in (tuple(k for k in group if k in moment.facts) for group in ANCHORS.get(tkey, ())) if g
    )
    srcs = list(sources) if sources is not None else ["template_sweep"] * len(cards)
    first = srcs[0] if srcs else "template_sweep"
    problems: list[str] = []
    stated_map: dict[str, list[str]] = {}
    seen: dict[tuple[str, str, str], tuple[set[str], set[str], bool]] = {}
    for card, source in zip(cards, srcs, strict=True):
        label = f"{card.persona}/{card.language}" + ("" if source == first else f" ({source})")
        for c in [c for c in card.claims if c.check == "unverified_text" and _failed(c)][:2]:
            problems.append(f"{label}: {c.field} '{c.sentence[:60]}': {c.reason}")
        exact_all = stated_facts(card.claims, moment)
        value_all = _matched(card, moment)
        is_template = templated(card)
        stated = (exact_all if is_template else value_all) & keyset
        stated_map[label] = sorted(stated, key=key_facts.index)
        for group in anchors:
            if not set(group) & (exact_all | value_all):
                problems.append(f"{label}: does not say who or what it is about ({' or '.join(group)})")
        seen[(card.persona, card.language, source)] = (exact_all & keyset, value_all & keyset, is_template)
    for (persona, language, source), (exact, by_value, is_template) in seen.items():
        if language == "en":
            continue
        english = seen.get((persona, "en", source)) or seen.get((persona, "en", first))
        if english is None:
            continue
        en_exact, en_value, en_template = english
        want, got = (en_exact, exact) if is_template and en_template else (en_value, by_value)
        if want != got:
            parts = []
            if want - got:
                parts.append(f"missing {', '.join(sorted(want - got))}")
            if got - want:
                parts.append(f"extra {', '.join(sorted(got - want))}")
            label = f"{persona}/{language}" + ("" if source == first else f" ({source})")
            problems.append(f"{label}: key facts differ from {persona}/en ({'; '.join(parts)})")
    return FactParity(
        ok=not problems,
        key_facts=list(key_facts),
        anchors=[list(g) for g in anchors],
        renderings=len(cards),
        withheld=withheld,
        stated=dict(list(stated_map.items())[:MAX_STATED]),
        problems=problems[:MAX_PROBLEMS],
    )


def templated(card: OverlayCard) -> bool:
    """True when the headline and body were filled from templates (their claims say so).
    `produced_by` alone cannot tell: a model headline over a template explanation
    is still marked "template" on the card."""
    shown = [c for c in card.claims if c.field in ("headline", "body")]
    return bool(shown) and all(c.origin == "template" for c in shown)


def _failed(claim: Claim) -> bool:
    """An unverified claim that failed a check (not one with nothing to check)."""
    return not claim.reason.startswith("no number or squad name")
