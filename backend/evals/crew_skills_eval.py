"""Crew-shape eval: does folding a crew agent into a "skill" of another agent help?

Ten fixed examples on the demo match, each with a few pass/fail checks. A
scripted model stands in for the paid one (paid AI stays off), so the eval is
free, offline and repeatable; it scores the crew's wiring (who answers, what
the fact-checker lets through, what still works when one step fails), not the
model's prose.

    python -I evals/crew_skills_eval.py            # every variant
    python -I evals/crew_skills_eval.py baseline   # one variant

Variants are applied one at a time, in order; the run stops at the first one
that makes any example score worse than the baseline.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matchmind.crew import analyst, commentator  # noqa: E402
from matchmind.crew.analyst import AnalystOut, TacticalTag  # noqa: E402
from matchmind.crew.commentator import CommentatorOut  # noqa: E402
from matchmind.crew.contracts import ViewerProfile  # noqa: E402
from matchmind.crew.crew import AnalystDraft, CommentatorDraft, Crew  # noqa: E402
from matchmind.crew.fact_checker import check  # noqa: E402
from matchmind.crew.llm import LLMError, LLMSchemaError, ModelBudget  # noqa: E402
from matchmind.crew.translator import OffTranslator  # noqa: E402
from matchmind.simulator.publisher import read_jsonl  # noqa: E402
from matchmind.simulator.teams import TEAMS  # noqa: E402
from matchmind.stats.state import StatsEngine  # noqa: E402

DEMO = ROOT / "data" / "matches" / "MM-DEMO-001.jsonl"
WHY_MARK = "That decision changed the attack."
WHY_MARK_PLAIN = "That moment changed the game."


# ------------------------------------------------------------ scripted model


class StudioOut(BaseModel):
    """Folded Analyst + Commentator answer: one call writes the why and the card."""

    why: str = Field(max_length=320)
    tactical_tag: TacticalTag
    headline: str
    body: str


class SimModel:
    """Behaves like a well-behaved model: uses only given facts and states the
    verdict. `faults` maps a role (analyst, commentator) to timeout, schema or
    invent (writes a number that is not a fact)."""

    enabled = True
    model = "sim-model"
    provider = "azure_openai"

    def __init__(self, faults: dict[str, str] | None = None) -> None:
        self.faults = faults or {}
        self.calls: dict[str, int] = {}
        self.log: list[tuple] = []

    def complete_json(self, system, user, schema, timeout_s):
        role = {AnalystOut: "analyst", CommentatorOut: "commentator", StudioOut: "commentator"}.get(
            schema, "other"
        )
        self.calls[role] = self.calls.get(role, 0) + 1
        self.log.append((role, user.get("kind"), user.get("match_clock")))
        fault = self.faults.get(role)
        if fault == "timeout":
            raise LLMError("timeout")
        if fault == "schema":
            raise LLMSchemaError("not json")
        verdict = user.get("verdict")
        why = WHY_MARK if verdict else WHY_MARK_PLAIN
        if fault == "invent":
            why = "He had 97 options there."
        tag = user.get("allowed_tactical_tags", ["decision quality"])[0]
        audience = str(user.get("audience", ""))
        tactical = "tactic" in audience.lower() or "analyst" in audience.lower()
        headline = "Decision under the microscope" if tactical else "What a moment"
        body = verdict or (user.get("why_it_matters") or why)
        if not tactical:
            body = "Big call. " + body
        if fault == "invent" and schema is not AnalystOut:
            body = "He had 97 options there."
        if schema is AnalystOut:
            return AnalystOut(why=why, tactical_tag=tag)
        if schema is CommentatorOut:
            return CommentatorOut(headline=headline, body=body)
        if schema is StudioOut:
            return StudioOut(why=why, tactical_tag=_tag_for(user), headline=headline, body=body)
        raise LLMError("unknown schema")


def _tag_for(user: dict) -> str:
    return user.get("allowed_tactical_tags", list(analyst.TAGS.values()))[0]


# ------------------------------------------------------------ variants


STUDIO_SYSTEM = (
    "You are the PitchPulse studio. Skill 1 (analyst): explain WHY the moment matters in one or two "
    "English sentences. Skill 2 (commentator): write the overlay card for the audience and language.\n"
    + analyst.ANALYST_SYSTEM.split("Rules:", 1)[1]
)


class FoldedAnalystCrew(Crew):
    """Variant 1: the Analyst becomes a skill of the Commentator. One model call
    per card writes the why and the card; the process step makes no model call."""

    def analyst_step(self, moment):
        return AnalystDraft(None, None, 0.0)

    def commentator_step(self, bundle, profile) -> CommentatorDraft | None:
        draft = super().commentator_step(bundle, profile)  # template + (unused) payload
        if draft is None or not self.llm.enabled:
            return draft
        m = bundle.moment
        fav = self.team_name(profile.favourite_team)
        payload = commentator.ai_payload(
            m, "", profile.persona, profile.language, fav, profile.focus_player_id
        )
        payload["allowed_tactical_tags"] = list(analyst.TAGS.values())
        result, reason = self._ai("commentator", STUDIO_SYSTEM, payload, StudioOut)
        why = draft.why
        if result is not None and profile.language == "en":
            ok = check(result.why, m.facts, "en", "why", strict_words=True, roster=self.protected_names).ok
            if ok:
                why = result.why
        draft.why, draft.result, draft.reason = why, result, reason
        return draft


class SelfCheckCrew(Crew):
    """Variant 2: the Fact-checker becomes a prompt skill (the model is told to
    check its own numbers) instead of deterministic code. Model text is trusted."""

    def fact_check_explanation(self, moment, draft):
        if draft.result is not None:
            from matchmind.crew.contracts import Explanation

            return Explanation(
                moment_id=moment.moment_id,
                why=draft.result.why,
                tactical_tag=draft.result.tactical_tag,
                evidence=analyst.evidence(moment),
                produced_by="ai",
            )
        return super().fact_check_explanation(moment, draft)


VARIANTS: dict[str, Callable[..., Crew]] = {
    "baseline": Crew,
    "fold_analyst_into_commentator": FoldedAnalystCrew,
    "fact_checker_as_skill": SelfCheckCrew,
}


# ------------------------------------------------------------ examples


def run_match(crew: Crew, limit: int = 2142):
    events = read_jsonl(DEMO)[:limit]
    stats = StatsEngine(events[0].match_id, "NBR", "HCY")
    bundles = []
    for e in events:
        bundles += crew.process(e, stats.process(e), stats.snapshot(), stats.players())
    return bundles


def first(bundles, kind: str):
    return next(b for b in bundles if b.moment.kind.value == kind)


def numbers_backed(card, bundle) -> bool:
    texts = {"headline": card.headline, "body": card.body}
    for field, text in texts.items():
        if not check(text, bundle.moment.facts, card.language, field).ok:
            return False
    return not card.why or check(card.why, bundle.moment.facts, card.language, "why").ok


def example(name: str, faults: dict[str, str] | None, kind: str, profile: ViewerProfile, checks):
    return {"name": name, "faults": faults or {}, "kind": kind, "profile": profile, "checks": checks}


def ai_card(card) -> bool:
    return card.headline in ("Decision under the microscope", "What a moment")


def ai_why(card) -> bool:
    return card.why in (WHY_MARK, WHY_MARK_PLAIN)


EXAMPLES = [
    example(
        "1 should-he-have-passed, analyst, en",
        None,
        "better_option",
        ViewerProfile(persona="tactical", language="en"),
        {
            "card is model text": lambda c, b, s: ai_card(c),
            "verdict stated": lambda c, b, s: "should have passed" in c.body,
            "why is model text": lambda c, b, s: ai_why(c),
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
            "pass geometry drawn": lambda c, b, s: c.replay is not None,
        },
    ),
    example(
        "2 should-he-have-passed, fan, en",
        None,
        "better_option",
        ViewerProfile(persona="casual", language="en"),
        {
            "card is model text": lambda c, b, s: ai_card(c),
            "fan voice differs from analyst": lambda c, b, s: c.headline != "Decision under the microscope",
            "verdict stated": lambda c, b, s: "should have passed" in c.body,
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
        },
    ),
    example(
        "3 goal, fan, es",
        None,
        "goal",
        ViewerProfile(persona="casual", language="es"),
        {
            "card renders": lambda c, b, s: bool(c.headline),
            "language es": lambda c, b, s: c.language == "es",
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
        },
    ),
    example(
        "4 goal, analyst, ar (rtl)",
        None,
        "goal",
        ViewerProfile(persona="tactical", language="ar"),
        {
            "card renders": lambda c, b, s: bool(c.headline),
            "rtl": lambda c, b, s: c.rtl,
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
        },
    ),
    example(
        "5 commentator invents a number",
        {"commentator": "invent"},
        "better_option",
        ViewerProfile(persona="tactical", language="en"),
        {
            "invented number blocked": lambda c, b, s: "97" not in c.body,
            "fallback visible": lambda c, b, s: bool(c.fallback_reason),
            "why still model text": lambda c, b, s: ai_why(c),
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
        },
    ),
    example(
        "6 analyst invents a number",
        {"analyst": "invent"},
        "better_option",
        ViewerProfile(persona="tactical", language="en"),
        {
            "invented number blocked": lambda c, b, s: "97" not in c.why,
            "card still model text": lambda c, b, s: ai_card(c),
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
        },
    ),
    example(
        "7 commentator model down",
        {"commentator": "timeout"},
        "better_option",
        ViewerProfile(persona="tactical", language="en"),
        {
            "card still shown": lambda c, b, s: bool(c.headline),
            "fallback visible": lambda c, b, s: bool(c.fallback_reason),
            "why still model text": lambda c, b, s: ai_why(c),
            "verdict still stated": lambda c, b, s: (
                "should have passed" in (c.body + c.why).lower() or bool(c.replay)
            ),
        },
    ),
    example(
        "8 analyst model returns bad JSON",
        {"analyst": "schema"},
        "better_option",
        ViewerProfile(persona="tactical", language="en"),
        {
            "card still model text": lambda c, b, s: ai_card(c),
            "why shown": lambda c, b, s: bool(c.why),
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
        },
    ),
    example(
        "9 player focus card",
        None,
        "better_option",
        None,  # filled in from the moment's player
        {
            "card is model text": lambda c, b, s: ai_card(c),
            "focus player tagged": lambda c, b, s: bool(c.player_ids),
            "numbers backed": lambda c, b, s: numbers_backed(c, b),
        },
    ),
    example(
        "10 model cost per moment",
        None,
        "better_option",
        ViewerProfile(persona="tactical", language="en"),
        {
            "<= 2 model calls for one card": lambda c, b, s: sum(s.calls.values()) <= 2,
            "trace shows each agent": lambda c, b, s: (
                {"spotter", "analyst", "commentator", "fact_checker"} <= {st.agent for st in s.trace.steps}
            ),
        },
    ),
]


def score(variant: str) -> dict[str, tuple[int, int, list[str]]]:
    factory = VARIANTS[variant]
    out: dict[str, tuple[int, int, list[str]]] = {}
    for ex in EXAMPLES:
        sim = SimModel(ex["faults"])
        crew = factory(
            TEAMS,
            llm=sim,
            translator=OffTranslator(),
            orchestrator="in_process",
            budget=ModelBudget(total=100_000, per_minute=100_000),
        )
        bundles = run_match(crew, limit=900)
        bundle = first(bundles, ex["kind"])
        profile = ex["profile"] or ViewerProfile(
            persona="player_spotlight", language="en", focus_player_id=bundle.moment.player_ids[0]
        )
        card = crew.render(bundle, profile)
        mine = [r for r in sim.log if r[1:] == (bundle.moment.kind.value, bundle.moment.match_clock)]
        sim.calls = {"this_moment": len(mine)}
        sim.trace = crew.trace_for(bundle.moment.moment_id)
        failed = []
        for label, fn in ex["checks"].items():
            try:
                ok = card is not None and fn(card, bundle, sim)
            except Exception as exc:  # a check that crashes is a fail
                ok = False
                label = f"{label} ({type(exc).__name__})"
            if not ok:
                failed.append(label)
        n = len(ex["checks"])
        out[ex["name"]] = (n - len(failed), n, failed)
        crew._pool.shutdown(wait=False)
    return out


def total(result) -> tuple[int, int]:
    return sum(r[0] for r in result.values()), sum(r[1] for r in result.values())


def main(argv: list[str]) -> int:
    names = argv or list(VARIANTS)
    base = score("baseline")
    report = {"baseline": base}
    p, n = total(base)
    print(f"baseline: {p}/{n}")
    for name, (got, of, failed) in base.items():
        print(f"  {got}/{of}  {name}" + (f"   FAILED: {', '.join(failed)}" if failed else ""))
    for variant in names:
        if variant == "baseline":
            continue
        res = score(variant)
        report[variant] = res
        p, n = total(res)
        worse = [k for k in res if res[k][0] < base[k][0]]
        print(f"\n{variant}: {p}/{n}" + ("   WORSE ON: " + "; ".join(worse) if worse else ""))
        for name, (got, of, failed) in res.items():
            delta = got - base[name][0]
            mark = f" ({delta:+d})" if delta else ""
            print(f"  {got}/{of}{mark}  {name}" + (f"   FAILED: {', '.join(failed)}" if failed else ""))
        if worse:
            print(f"\nSTOP: {variant} made {len(worse)} example(s) worse; later variants not applied.")
            break
    (ROOT / "evals" / "last_run.json").write_text(
        json.dumps({v: {k: list(r) for k, r in res.items()} for v, res in report.items()}, indent=1)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
