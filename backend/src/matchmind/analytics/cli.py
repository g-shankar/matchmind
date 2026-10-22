"""Command line: matchmind-lakehouse export | labels | enrich."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .build import build_tables
from .schema import STAR_TABLES
from .sources import DEFAULT_BEATS, DEFAULT_SEED_START, load_matches
from .writers import FORMATS, resolve_format, write_tables

DEFAULT_INPUT = "data/matches"


def _add_sources(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--input",
        nargs="+",
        default=None,
        metavar="PATH",
        help=f"match JSONL files or folders (default {DEFAULT_INPUT} when --seeds is not given)",
    )
    p.add_argument("--seeds", type=int, default=0, help="also simulate N new matches, deterministically")
    p.add_argument("--seed-start", type=int, default=DEFAULT_SEED_START, help="first seed of the new matches")
    p.add_argument(
        "--beats",
        type=int,
        default=DEFAULT_BEATS,
        help="story beats per new match: 'should he have passed' shots and unfound runs (0 = none)",
    )


def _matches(args: argparse.Namespace):
    inputs = args.input if args.input is not None else ([] if args.seeds else [DEFAULT_INPUT])
    matches = load_matches(inputs, args.seeds, args.seed_start, args.beats)
    if not matches:
        raise SystemExit("No matches found. Pass --input PATH or --seeds N.")
    return matches


def _report(manifest: dict, out: Path) -> None:
    print(f"wrote {len(manifest['matches'])} match(es) as {manifest['format']} -> {out}", file=sys.stderr)
    for name, info in manifest["tables"].items():
        print(f"  {name:<16}{info['rows']:>9} rows", file=sys.stderr)


def cmd_export(args: argparse.Namespace) -> None:
    fmt = resolve_format(args.format)
    tables = build_tables(_matches(args))
    keep = {t.name for t in STAR_TABLES} | ({"decision_labels"} if args.with_labels else set())
    manifest = write_tables(
        {k: v for k, v in tables.items() if k in keep},
        args.out,
        fmt,
        matches=[r["match_id"] for r in tables["matches"]],
    )
    _report(manifest, Path(args.out))


def cmd_labels(args: argparse.Namespace) -> None:
    fmt = resolve_format(args.format)
    tables = build_tables(_matches(args))
    manifest = write_tables(
        {"decision_labels": tables["decision_labels"]},
        args.out,
        fmt,
        matches=[r["match_id"] for r in tables["matches"]],
    )
    _report(manifest, Path(args.out))


def cmd_enrich(args: argparse.Namespace) -> None:
    """Enriched events as JSON lines: the `events` table, one object per line.

    This is the file shape the Eventhouse table `MatchEventsEnriched` ingests
    (see analytics/fabric/eventhouse.kql)."""
    rows = build_tables(_matches(args))["events"]
    out = sys.stdout if args.out == "-" else Path(args.out).open("w", encoding="utf-8")
    try:
        for row in rows:
            clean = {k: v for k, v in row.items() if v is not None}
            clean["ts"] = row["ts"].isoformat().replace("+00:00", "Z")
            out.write(json.dumps(clean, separators=(",", ":"), ensure_ascii=False) + "\n")
    finally:
        if out is not sys.stdout:
            out.close()
    print(f"wrote {len(rows)} enriched events", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="matchmind-lakehouse", description="Fabric Lakehouse export of the synthetic match data"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    e = sub.add_parser("export", help="write the star schema (Tables/<table>/part-0.parquet or .csv)")
    _add_sources(e)
    e.add_argument("--out", default="data/lakehouse")
    e.add_argument("--format", choices=FORMATS, default="auto", help="auto = Parquet if pyarrow is installed")
    e.add_argument("--with-labels", action="store_true", help="also write the decision_labels table")
    e.set_defaults(func=cmd_export)

    lab = sub.add_parser("labels", help="write the ML decision dataset (one row per shot or pass)")
    _add_sources(lab)
    lab.add_argument("--out", default="data/lakehouse-labels")
    lab.add_argument("--format", choices=FORMATS, default="auto")
    lab.set_defaults(func=cmd_labels)

    en = sub.add_parser("enrich", help="write enriched events as JSON lines for the Eventhouse table")
    _add_sources(en)
    en.add_argument("--out", default="-", help="file, or - for stdout")
    en.set_defaults(func=cmd_enrich)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()
