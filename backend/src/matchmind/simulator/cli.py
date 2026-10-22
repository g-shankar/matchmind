"""Command line: matchmind-sim generate | live | dataset | schema | export | dictionary."""

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


def _tracking_window(spec: str | None):
    """'1:600-630' -> TrackingWindow(period 1, 600 s to 630 s)."""
    if not spec:
        return None
    from matchmind.dataset.export import TrackingWindow

    try:
        period, span = spec.split(":", 1)
        start, end = span.split("-", 1)
        return TrackingWindow(int(period), float(start), float(end))
    except ValueError as exc:
        raise SystemExit(f"--tracking: {exc} (use PERIOD:FROM-TO in seconds, e.g. 1:600-630)") from None


def cmd_export(args: argparse.Namespace) -> None:
    from matchmind.dataset import catalog
    from matchmind.dataset.dictionary import render_dictionary
    from matchmind.dataset.export import FORMATS, export_parts

    data_dir = Path(args.data) if args.data else None
    ids = list(args.match or [])
    ids += [catalog.seeded_id(seed) for seed in args.seed or []]
    if args.all:
        ids += [e.match_id for e in catalog.bundled_entries(data_dir)]
    if not ids:
        raise SystemExit("Pick matches: --match ID, --seed N or --all")
    entries = []
    for match_id in dict.fromkeys(ids):
        entry = catalog.find(match_id, data_dir, any_seed=True)
        if entry is None:
            raise SystemExit(
                f"Unknown match '{match_id}'. Bundled: --all; seeded: --seed 0-{catalog.CLI_MAX_SEED}"
            )
        entries.append(entry)
    window = _tracking_window(args.tracking)
    formats = list(FORMATS) if args.format == "all" else [args.format]
    if window is not None and "zip" not in formats:
        raise SystemExit("--tracking needs --format zip (or all)")
    dictionary = render_dictionary(data_dir)
    schema = Event.model_json_schema()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    matches = []
    for entry in entries:
        events = catalog.load_match(entry, data_dir)
        matches.append(events)
        for fmt in formats:
            name, _, chunks = export_parts(
                entry, events, fmt, dictionary, schema, window if fmt == "zip" else None
            )
            with (out / name).open("wb") as fh:
                for chunk in chunks:
                    fh.write(chunk)
            print(f"{entry.match_id}: {fmt} -> {out / name}", file=sys.stderr)
    if args.lakehouse:
        from matchmind.analytics.build import build_tables
        from matchmind.analytics.schema import STAR_TABLES
        from matchmind.analytics.writers import resolve_format, write_tables

        tables = build_tables(sorted(matches, key=lambda m: m[0].match_id))
        keep = {t.name for t in STAR_TABLES}
        write_tables(
            {k: v for k, v in tables.items() if k in keep},
            out / "lakehouse",
            resolve_format("auto"),
            matches=[r["match_id"] for r in tables["matches"]],
        )
        print(f"lakehouse star schema -> {out / 'lakehouse'}", file=sys.stderr)


def cmd_dictionary(args: argparse.Namespace) -> None:
    from matchmind.dataset.dictionary import render_dictionary

    text = render_dictionary(Path(args.data) if args.data else None)
    path = Path(args.out)
    if args.check:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{path} is out of date: run `matchmind-sim dictionary`")
        print(f"{path} is up to date", file=sys.stderr)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
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

    x = sub.add_parser("export", help="export matches with metadata, rosters and the data dictionary")
    x.add_argument("--match", action="append", help="match id, bundled or MM-GEN-nnnnn (repeatable)")
    x.add_argument("--seed", type=int, action="append", help="seeded match MM-GEN-<seed> (repeatable)")
    x.add_argument("--all", action="store_true", help="every bundled match")
    x.add_argument("--format", choices=["jsonl", "csv", "zip", "all"], default="zip")
    x.add_argument(
        "--tracking", metavar="PERIOD:FROM-TO", help="add 25 Hz tracking, e.g. 1:600-630 (<= 60 s)"
    )
    x.add_argument("--lakehouse", action="store_true", help="also write the Lakehouse star schema")
    x.add_argument("--data", help="bundled dataset folder (default data/matches)")
    x.add_argument("--out", default="data/export")
    x.set_defaults(func=cmd_export)

    dd = sub.add_parser("dictionary", help="write docs/DATA-DICTIONARY.md from the schema and the dataset")
    dd.add_argument("--out", default="../docs/DATA-DICTIONARY.md")
    dd.add_argument("--data", help="bundled dataset folder (default data/matches)")
    dd.add_argument("--check", action="store_true", help="exit 1 if the file is out of date")
    dd.set_defaults(func=cmd_dictionary)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from None


if __name__ == "__main__":
    main()
