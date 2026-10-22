"""Evaluation dataset and free local evaluators for the studio crew.

`build_dataset` replays every match through the stats engine and a crew that
is pinned to `TemplateLLM()` (no paid calls, ever), then voices every moment
for every persona x language and writes one JSON line per card, plus one per
full-time recap. Each line has the Azure AI Evaluation columns:

- `query`: what the agent was asked (moment kind, audience, language),
- `context`: the moment's facts as JSON (the only numbers it may use),
- `response`: the text a viewer sees,
- `ground_truth`: the fact-checked Analyst explanation in the same language,

plus the raw fields (`headline`, `body`, `facts`, ...) the local evaluators
read. The same file runs through Foundry's built-in Groundedness and Relevance
evaluators (docs/EVALUATION.md); those are model-graded and paid.

The local evaluators are deterministic and free:
- groundedness_numbers: every number is a fact (the fact-checker);
- groundedness_numbers_strict: also spelled-out numbers (the bar model text meets);
- length: headline and body length rules;
- persona_vocab: plain words for casual, numbers for tactical, no chalkboard
  acronyms for fantasy, the focus player named for player spotlight;
- language: the text is in the requested language (script and stop words).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from matchmind.crew import commentator
from matchmind.crew.contracts import PERSONAS, STUDIO_LANGUAGES, MomentBundle, ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.fact_checker import check, extract_numbers, length_problems
from matchmind.crew.llm import ModelBudget, TemplateLLM
from matchmind.crew.spotter import surname
from matchmind.crew.translator import OffTranslator
from matchmind.schema import Event
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import get_team
from matchmind.stats.state import StatsEngine

BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_MATCHES = BACKEND_DIR / "data" / "matches"

# --------------------------------------------------------------- dataset


def match_files(path: str | Path = DEFAULT_MATCHES) -> list[Path]:
    p = Path(path)
    return sorted(p.glob("*.jsonl")) if p.is_dir() else [p]


def _query(kind: str, persona: str, language: str) -> str:
    return (
        f"Write a PitchPulse overlay card (headline and body) about this {kind.replace('_', ' ')} moment. "
        f"Audience: {commentator.PERSONA_BRIEFS[persona]} Language: {commentator.LANGUAGE_NAMES[language]}."
    )


def _context(facts: dict[str, Any]) -> str:
    return json.dumps(facts, ensure_ascii=False, sort_keys=True)


def _replay(events: list[Event]) -> tuple[Crew, StatsEngine, list[MomentBundle]]:
    start = events[0]
    home, away = str(start.details["home"]), str(start.details["away"])
    teams = {home: get_team(home), away: get_team(away)}
    stats = StatsEngine(start.match_id, home, away)
    # Pinned to templates and no translation: an evaluation run never spends on paid AI.
    crew = Crew(
        teams, llm=TemplateLLM(), budget=ModelBudget(total=0, per_minute=0), translator=OffTranslator()
    )
    bundles: list[MomentBundle] = []
    for event in events:
        metrics = stats.process(event)
        bundles += crew.process(event, metrics, stats.snapshot(), stats.players())
    return crew, stats, bundles


def match_records(events: list[Event], tally: dict[str, int] | None = None) -> Iterator[dict[str, Any]]:
    """One record per voiced card and per recap. `tally["dropped"]` counts cards
    the crew refused to show (no template fits, or the fact-checker rejected it)."""
    tally = tally if tally is not None else {}
    tally.setdefault("dropped", 0)
    crew, stats, bundles = _replay(events)
    match_id = events[0].match_id
    names = crew.names
    for bundle in bundles:
        m = bundle.moment
        for persona in PERSONAS:
            focus = m.player_ids[0] if persona == "player_spotlight" and m.player_ids else None
            for language in STUDIO_LANGUAGES:
                profile = ViewerProfile(persona=persona, language=language, focus_player_id=focus)
                card = crew.render(bundle, profile)
                if card is None:
                    tally["dropped"] += 1
                    continue
                yield {
                    "id": f"{m.moment_id}:{persona}:{language}",
                    "type": "card",
                    "match_id": match_id,
                    "moment_id": m.moment_id,
                    "kind": m.kind.value,
                    "persona": persona,
                    "language": language,
                    "focus_player": names.get(focus) if focus else None,
                    "produced_by": card.produced_by,
                    "fallback_reason": card.fallback_reason,
                    "query": _query(m.kind.value, persona, language),
                    "context": _context(m.facts),
                    "response": f"{card.headline}\n{card.body}",
                    "ground_truth": card.why,
                    "headline": card.headline,
                    "body": card.body,
                    "facts": dict(m.facts),
                }
    snapshot, players = stats.snapshot(), stats.players()
    for persona in PERSONAS:
        for language in STUDIO_LANGUAGES:
            recap = crew.recap(snapshot, players, ViewerProfile(persona=persona, language=language))
            yield {
                "id": f"{match_id}:recap:{persona}:{language}",
                "type": "recap",
                "match_id": match_id,
                "moment_id": None,
                "kind": "recap",
                "persona": persona,
                "language": language,
                "focus_player": None,
                "produced_by": recap.produced_by,
                "fallback_reason": None,
                "query": (
                    f"Write the PitchPulse match recap. Audience: {commentator.PERSONA_BRIEFS[persona]} "
                    f"Language: {commentator.LANGUAGE_NAMES[language]}."
                ),
                "context": _context(recap.stats),
                "response": "\n".join([recap.title, recap.headline, *recap.summary_paragraphs]),
                "ground_truth": recap.headline,
                "headline": recap.headline,
                "title": recap.title,
                "paragraphs": list(recap.summary_paragraphs),
                "body": "",
                "facts": dict(recap.stats),
            }


def build_dataset(matches: Iterable[Path], out: str | Path) -> dict[str, dict[str, int]]:
    """Write the JSONL; returns {match_id: {"records": n, "dropped": n}}."""
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, dict[str, int]] = {}
    with out_path.open("w", encoding="utf-8") as fh:
        for path in matches:
            events = read_jsonl(path)
            n, tally = 0, {"dropped": 0}
            for record in match_records(events, tally):
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")
                n += 1
            counts[events[0].match_id] = {"records": n, "dropped": tally["dropped"]}
    return counts


def read_dataset(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ------------------------------------------------------------ evaluators

JARGON = re.compile(r"\b(?:xG|xA|xT|PDR)\b")
CHALKBOARD = re.compile(r"\b(?:xT|PDR)\b")
_ARABIC = re.compile(r"[؀-ۿ]")
_KANA = re.compile(r"[぀-ヿ]")
_CJK = re.compile(r"[぀-ヿ一-鿿]")


# Common function words plus everyday football words per language. A text is
# scored by how many of its words appear in each list, plus spelling cues.
def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


STOP_WORDS: dict[str, frozenset[str]] = {
    "en": _words(
        "the and of to in is for with his her on at from by it that was but has he out after into their "
        "its this goes scores shot shots pass passes chance goal goals today minutes keeps finds through "
        "over past behind back line run runs still now just half time from who what yet off top speed "
        "estimated so far club appearance assist assists clear team ball box",
    ),
    "es": _words(
        "el la los las del y en un una con por para que su al se es sin pero más lo como sus desde hasta "
        "tiro tiros pase pases gol goles ocasión minutos lleva suma ya hoy esta este no entró sobre "
        "dificultad descanso esperados recorrido según nuestra estimación correr vuela mete directa "
        "esprint esprints aprieta encerrando algo puede romperse filtra supera ha tu equipo partido "
        "velocidad remate disparo asistencia asistencias balón área revisa tus puntos",
    ),
    "fr": _words(
        "le la les des du et en un une avec pour que sur au aux est il sa son mais dans à ses pas plus "
        "tir tirs passe passes but buts occasion cumule depuis cette valait quelque chose va finir par "
        "céder enferme met pression trouve difficulté qui ajoute décisive mi-temps ton équipe vitesse "
        "frappe ballon surface aujourd'hui sprint sprints parcouru estimé",
    ),
}
_ES_SPELLING = re.compile(r"[ñ¿¡]")
_FR_SPELLING = re.compile(r"[çœèêùû]|\b[ldjnqu]'|\s[:;!?]")
_DECIMAL_COMMA = re.compile(r"\d,\d")


def _texts(record: dict[str, Any]) -> list[tuple[str, str]]:
    if record["type"] == "recap":
        return [("text", record["title"]), ("headline", record["headline"])] + [
            ("paragraph", p) for p in record["paragraphs"]
        ]
    return [("headline", record["headline"]), ("body", record["body"])]


def eval_groundedness(record: dict[str, Any], strict: bool = False) -> tuple[bool, str | None]:
    reasons: list[str] = []
    for field, text in _texts(record):
        reasons += check(text, record["facts"], record["language"], field, strict_words=strict).reasons
    return (not reasons, reasons[0] if reasons else None)


def eval_length(record: dict[str, Any]) -> tuple[bool, str | None]:
    reasons = [r for field, text in _texts(record) for r in length_problems(text, field)]
    return (not reasons, reasons[0] if reasons else None)


def eval_persona(record: dict[str, Any]) -> tuple[bool, str | None]:
    text = record["response"]
    persona = record["persona"]
    if persona == "casual" and (found := JARGON.search(text)):
        return False, f"casual text uses jargon {found.group(0)}"
    has_numbers = any(
        isinstance(v, int | float) and not isinstance(v, bool) for v in record["facts"].values()
    )
    if persona == "tactical" and has_numbers and not extract_numbers(text, record["language"]):
        return False, "tactical text has no numbers"
    if persona == "fantasy" and (found := CHALKBOARD.search(text)):
        return False, f"fantasy text uses chalkboard term {found.group(0)}"
    focus = record.get("focus_player")
    if persona == "player_spotlight" and focus and surname(focus) not in text:
        return False, "spotlight text does not name the focus player"
    return True, None


def detect_language(text: str) -> str | None:
    """Rough script and stop-word guess among the five product languages."""
    if _ARABIC.search(text):
        return "ar"
    if _KANA.search(text) or len(_CJK.findall(text)) >= 2:
        return "ja"
    words = [w.lower() for w in re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text)]
    scores = {lang: float(sum(w in stops for w in words)) for lang, stops in STOP_WORDS.items()}
    scores["es"] += 2 * len(_ES_SPELLING.findall(text))
    scores["fr"] += 2 * len(_FR_SPELLING.findall(text))
    if _DECIMAL_COMMA.search(text):  # English prints 0.18, Spanish and French 0,18
        scores["en"] = 0.0
    best = max(scores.values())
    leaders = [lang for lang, score in scores.items() if score == best]
    return leaders[0] if best > 0 and len(leaders) == 1 else None


def eval_language(record: dict[str, Any]) -> tuple[bool, str | None]:
    text = record["response"]
    # Names are fictional and Latin-script in every language: take them out first.
    for value in record["facts"].values():
        if isinstance(value, str) and value:
            text = text.replace(value, " ")
    found = detect_language(text)
    if found == record["language"]:
        return True, None
    return False, f"looks like {found or 'undetermined'}"


EVALUATORS = {
    "groundedness_numbers": eval_groundedness,
    "groundedness_numbers_strict": lambda r: eval_groundedness(r, strict=True),
    "length": eval_length,
    "persona_vocab": eval_persona,
    "language": eval_language,
}


def evaluate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Pass counts per evaluator, overall and by type, persona and language,
    plus up to five example failures per evaluator (ids and reasons only)."""
    totals: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    failures: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in records:
        groups = (
            "all",
            f"type:{record['type']}",
            f"persona:{record['persona']}",
            f"language:{record['language']}",
        )
        for name, fn in EVALUATORS.items():
            ok, reason = fn(record)
            for group in groups:
                cell = totals[name][group]
                cell[0] += ok
                cell[1] += 1
            if not ok and len(failures[name]) < 5:
                failures[name].append({"id": record["id"], "reason": reason or ""})
    produced = defaultdict(int)
    for record in records:
        produced[record["produced_by"]] += 1
    return {
        "records": len(records),
        "matches": len({r["match_id"] for r in records}),
        "produced_by": dict(produced),
        "scores": {
            name: {
                group: {"passed": p, "total": t, "rate": round(p / t, 4) if t else None}
                for group, (p, t) in groups.items()
            }
            for name, groups in totals.items()
        },
        "failures": dict(failures),
    }


def scorecard(result: dict[str, Any]) -> str:
    """A plain-text table for the terminal and the docs."""
    groups = ["all", "type:card", "type:recap"]
    groups += [f"persona:{p}" for p in PERSONAS] + [f"language:{lang}" for lang in STUDIO_LANGUAGES]
    lines = [
        f"PitchPulse crew evaluation: {result['records']} records from {result['matches']} matches "
        f"(produced_by: {', '.join(f'{k}={v}' for k, v in sorted(result['produced_by'].items()))})",
        "",
        f"{'evaluator':<30}" + "".join(f"{g.split(':')[-1][:9]:>10}" for g in groups),
    ]
    for name, by_group in result["scores"].items():
        row = f"{name:<30}"
        for g in groups:
            cell = by_group.get(g)
            row += f"{cell['rate'] * 100:>9.1f}%" if cell and cell["rate"] is not None else f"{'-':>10}"
        lines.append(row)
    for name, items in result["failures"].items():
        lines.append("")
        lines.append(f"{name} examples:")
        lines += [f"  {f['id']}: {f['reason']}" for f in items]
    return "\n".join(lines)


def check_record_fields(record: dict[str, Any]) -> list[str]:
    """Columns Azure AI Evaluation reads; empty means the line is usable."""
    return [k for k in ("query", "context", "response") if not str(record.get(k, "")).strip()]
