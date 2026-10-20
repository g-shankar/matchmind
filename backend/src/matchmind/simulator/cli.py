"""Command line: matchmind-sim generate | live | dataset | schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from matchmind.schema import Event, EventType

from .engine import MatchEngine
from .publisher import EventHubSink, read_jsonl, replay, stdout_sink, write_jsonl
from .script import load_script, random_script


def _summary(events: list[Event]) -> str:
    end = events[-1]
    start = events[0]
    home, away = start.details["home"], start.details["away"]
    shots = sum(e.type == EventType.SHOT for e in events)
    return (
        f"{events[0].match_id}: {home} {end.details['score_home']}-{end.details['score_away']} {away}"
        f" | {len(events)} events, {shots} shots"
    )


def _simulate(script_spec: str, seed: int) -> list[Event]:
    engine = MatchEngine(load_script(script_spec), seed)
    events = engine.run()
    for warning in engine.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return events


def cmd_generate(args: argparse.Namespace) -> None:
    events = _simulate(args.script, args.seed)
    path = write_jsonl(events, args.out)
    print(f"{_summary(events)} -> {path}", file=sys.stderr)


def cmd_live(args: argparse.Namespace) -> None:
    events = read_jsonl(args.from_file) if args.from_file else _simulate(args.script, args.seed)
    sink = EventHubSink() if args.sink == "eventhub" else stdout_sink
    try:
        sent = replay(events, sink, speed=args.speed)
    finally:
        if isinstance(sink, EventHubSink):
            sink.close()
    print(f"sent {sent} events at {args.speed}x", file=sys.stderr)


def cmd_dataset(args: argparse.Namespace) -> None:
    out = Path(args.out)
    manifest = []
    for i in range(args.count):
        seed = args.seed + i
        if i == 0:
            script = load_script("demo")
        else:
            home, away = ("NBR", "HCY") if i % 2 else ("HCY", "NBR")
            script = random_script(f"MM-SYN-{i:03d}", home=home, away=away)
        events = MatchEngine(script, seed).run()
        path = write_jsonl(events, out / f"{script.match_id}.jsonl")
        end = events[-1].details
        manifest.append(
            {
                "match_id": script.match_id,
                "file": path.name,
                "seed": seed,
                "home": script.home,
                "away": script.away,
                "score": f"{end['score_home']}-{end['score_away']}",
                "events": len(events),
                "scripted": not script.random_goals,
            }
        )
        print(_summary(events), file=sys.stderr)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def cmd_schema(args: argparse.Namespace) -> None:
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(Event.model_json_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matchmind-sim", description="Synthetic match simulator")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="simulate a match to a JSONL file")
    g.add_argument("--script", default="demo", help="bundled script name or path to a .yaml")
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--out", default="data/local/demo.jsonl")
    g.set_defaults(func=cmd_generate)

    live = sub.add_parser("live", help="stream a match in (scaled) real time")
    live.add_argument("--script", default="demo")
    live.add_argument("--seed", type=int, default=7)
    live.add_argument("--from-file", help="replay an existing JSONL file instead")
    live.add_argument("--speed", type=float, default=60.0, help="1, 10 or 60 for the demo")
    live.add_argument("--sink", choices=["stdout", "eventhub"], default="stdout")
    live.set_defaults(func=cmd_live)

    d = sub.add_parser("dataset", help="publish N matches plus a manifest")
    d.add_argument("--out", default="data/matches")
    d.add_argument("--count", type=int, default=5)
    d.add_argument("--seed", type=int, default=100)
    d.set_defaults(func=cmd_dataset)

    s = sub.add_parser("schema", help="export the event JSON Schema")
    s.add_argument("--out", default="schema/event.schema.json")
    s.set_defaults(func=cmd_schema)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
