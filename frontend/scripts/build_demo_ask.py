"""Record the offline demo's "Ask the studio" answers and spoiler-free stories.

The offline demo (no server) cannot run the question parser, so it can only
offer the suggested questions (chips). This script answers every chip, in the
demo's three languages, at checkpoints through the recorded match, and writes
the spoiler-free "story so far" for catch-up mode at the same checkpoints.

Every answer is built by the same code the live server runs (`matchmind.ask`
and `matchmind.crew.recap`) from the numbers already in
`frontend/public/demo/demo-match.json`, so the demo's answers agree with what
the demo shows on screen. Nothing later than a checkpoint is read for it. The
output is deterministic and fact-checked; the script fails on any problem.

Run from the repository root, after `build_demo_fixture.py`:

    PYTHONPATH=backend/src python frontend/scripts/build_demo_ask.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from matchmind.ask import CHIPS, AskContext, ask
from matchmind.ask.i18n import ask_pack
from matchmind.ask.service import MetricInfo
from matchmind.crew import recap as recap_mod
from matchmind.crew.contracts import Moment, MomentKind
from matchmind.crew.spoilers import SPOILER_FACT_KEYS, spoiler_free_moments
from matchmind.simulator.teams import get_team
from matchmind.stats.models import MatchStateSnapshot, PlayerStats
from matchmind.stats.registry import registry_payload

REPO = Path(__file__).resolve().parents[2]
DEFAULT_IN = REPO / "frontend" / "public" / "demo" / "demo-match.json"
DEFAULT_OUT = REPO / "frontend" / "public" / "demo" / "demo-ask.json"
LANGUAGES = ("en", "es", "ar")
CHECKPOINT_S = 300  # one checkpoint every 5 minutes of play
# The demo client needs the answer and what backs it; the full claim list stays on the live server.
KEEP = (
    "status",
    "reason",
    "intent",
    "understood_by",
    "answer",
    "language",
    "text_language",
    "rtl",
    "as_of",
    "spoilers",
    "evidence",
    "moment_ids",
    "metric",
    "produced_by",
    "fact_check",
)


def moment_from_fixture(m: dict[str, Any]) -> Moment:
    """The fixture moment as the answer code sees it. Facts are the moment's own evidence."""
    facts: dict[str, Any] = {}
    replay = m.get("replay") or {}
    if m["kind"] == "better_option" and replay:
        names = {p["player_id"]: p["name"] for p in m.get("players", [])}
        facts = {
            "player": names.get(replay["shooter_id"], replay["shooter_id"]),
            "teammate": names.get(replay["teammate_id"], replay["teammate_id"]),
            "times_better": replay["times_better"],
        }
    return Moment(
        moment_id=m["moment_id"],
        kind=MomentKind(m["kind"]),
        clock_s=m["show_at_s"],
        match_clock=m["match_clock"],
        period=m.get("period", 1),
        team=m.get("team"),
        player_ids=list(m.get("player_ids", [])),
        facts=facts,
        source_event_ids=[m["event_id"]],
        priority=m.get("priority", 50),
        retracts=list(m.get("retracts", [])),
    )


def checkpoints(ticks: list[dict]) -> list[int]:
    """Tick indexes (inclusive) where a checkpoint falls: kick-off, every CHECKPOINT_S of play, the end."""
    out: list[int] = [0]  # kick-off, so a question asked straight away has an answer
    played = 0.0
    next_at = CHECKPOINT_S
    for i in range(1, len(ticks)):
        a, b = ticks[i - 1]["event"], ticks[i]["event"]
        if a["period"] == b["period"]:
            played += max(0.0, b["clock_s"] - a["clock_s"])
        if played >= next_at:
            out.append(i)
            next_at += CHECKPOINT_S
    if not out or out[-1] != len(ticks) - 1:
        out.append(len(ticks) - 1)
    return out


def build(fixture: dict) -> tuple[dict, list[str]]:
    ticks = fixture["ticks"]
    teams = {t["team_id"]: get_team(t["team_id"]) for t in fixture["teams"].values()}
    home_id, away_id = fixture["teams"]["home"]["team_id"], fixture["teams"]["away"]["team_id"]
    event_index = {t["event"]["event_id"]: i for i, t in enumerate(ticks)}
    moments = sorted(
        (m for m in fixture["moments"] if m["event_id"] in event_index),
        key=lambda m: (event_index[m["event_id"]], m["moment_id"]),
    )
    metric_info = {
        m["id"]: MetricInfo(id=m["id"], name=m["name"], formula=m["formula"], quality=m["quality"])
        for m in registry_payload()["metrics"]
    }
    protected = tuple(
        sorted({p.name for t in teams.values() for p in t.players} | {t.name for t in teams.values()})
    )
    problems: list[str] = []
    players: dict[str, dict] = {}
    applied = 0
    points: list[dict] = []
    for idx in checkpoints(ticks):
        while applied <= idx:
            for p in ticks[applied]["players_changed"]:
                players[p["player_id"]] = p
            applied += 1
        tick = ticks[idx]
        so_far = [moment_from_fixture(m) for m in moments if event_index[m["event_id"]] <= idx]
        snapshot = MatchStateSnapshot.model_validate(tick["state"])
        ctx = AskContext(
            match_id=fixture["match_id"],
            clock=tick["clock"],
            clock_s=tick["event"]["clock_s"],
            period=tick["period"],
            ended=idx == len(ticks) - 1,
            home_id=home_id,
            away_id=away_id,
            teams=teams,
            snapshot=snapshot,
            players=[PlayerStats.model_validate(p) for p in players.values()],
            moments=so_far,
            physical_source=next(iter(players.values()), {}).get("physical_source", "event_estimate"),
        )
        answers: dict[str, dict[str, dict]] = {}
        for lang in LANGUAGES:
            answers[lang] = {}
            for chip in CHIPS:
                a = ask(ctx, chip=chip, language=lang, spoilers=True, metric_info=metric_info)
                if a.status != "answered" or not a.fact_check.ok:
                    problems.append(f"{tick['clock']} {lang} {chip}: {a.status} {a.fact_check.reasons}")
                answers[lang][chip] = a.model_dump(mode="json", include=set(KEEP))
            hidden = ask(ctx, chip="score", language=lang, spoilers=False, metric_info=metric_info)
            if hidden.status != "hidden":
                problems.append(f"{tick['clock']} {lang}: score chip not hidden in catch-up mode")
        stories: dict[str, dict] = {}
        for lang in LANGUAGES:
            facts = recap_mod.story_facts(so_far, snapshot, teams)
            title, headline, paragraphs, _ = recap_mod.story_texts_with_templates(facts, lang)
            verdict = recap_mod.check_texts(title, headline, paragraphs, facts, lang, roster=protected)
            if not verdict.ok:
                problems.append(f"story {tick['clock']} {lang}: {verdict.reasons}")
            if set(facts) & SPOILER_FACT_KEYS:
                problems.append(f"story {tick['clock']} {lang}: result facts in the story")
            stories[lang] = {
                "title": title,
                "headline": headline,
                "summary_paragraphs": paragraphs,
                "stats": facts,
                "fact_check": {"ok": verdict.ok, "reasons": list(verdict.reasons)},
                "key_moment_ids": [m.moment_id for m in spoiler_free_moments(so_far)][-6:],
            }
        points.append(
            {
                "tick_index": idx,
                "clock": tick["clock"],
                "period": tick["period"],
                "clock_s": tick["event"]["clock_s"],
                "answers": answers,
                "stories": stories,
            }
        )
    out = {
        "match_id": fixture["match_id"],
        "checkpoint_s": CHECKPOINT_S,
        "chips": list(CHIPS),
        "hidden": {lang: ask_pack(lang)["hidden"] for lang in LANGUAGES},
        "checkpoints": points,
    }
    return out, problems


def serialise(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", type=Path, default=DEFAULT_IN)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    fixture = json.loads(args.input.read_text(encoding="utf-8"))
    data, problems = build(fixture)
    again, _ = build(fixture)
    if serialise(again) != serialise(data):
        problems.append("output is not deterministic")
    if problems:
        print("Self-check failed:", file=sys.stderr)
        for p in problems[:50]:
            print(f"  - {p}", file=sys.stderr)
        return 1
    blob = serialise(data)
    args.output.write_bytes(blob)
    print(f"Wrote {args.output} ({len(blob) / 1e3:.0f} kB): {len(data['checkpoints'])} checkpoints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
