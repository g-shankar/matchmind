"""Command line: matchmind-autoevent benchmark | score | frames | svg | clip."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.script import parse_clock

from .benchmark import HELD_OUT_SEEDS, held_out_match, run_benchmark
from .detect import detect_events
from .score import BENCHMARK_NAME, LABEL, PIXEL_LABEL, AutoEventingReport, score
from .svg import render_svg
from .tracking import DEFAULT_HZ, render_tracking


def _positive(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return value


def _pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def _row(r: AutoEventingReport) -> str:
    return (
        f"{r.match_id:<12} passes P {_pct(r.passes.precision)} R {_pct(r.passes.recall)}"
        f" | shots {r.shots.matched}/{r.shots.truth} P {_pct(r.shots.precision)} R {_pct(r.shots.recall)}"
        f" | receiver {_pct(r.receiver_accuracy or 0)} | kick speed error {r.speed_mae_kmh or 0:.1f} km/h"
    )


def cmd_score(args: argparse.Namespace) -> None:
    print(LABEL, file=sys.stderr)
    reports = []
    for path in args.matches:
        events = read_jsonl(path)
        feed = render_tracking(events, hz=args.hz)
        r = score(events, detect_events(feed), hz=args.hz, frames=len(feed.frames))
        reports.append(r)
        print(_row(r))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([r.model_dump() for r in reports], indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)


def cmd_frames(args: argparse.Namespace) -> None:
    feed = render_tracking(read_jsonl(args.match), hz=args.hz)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if out.suffix == ".gz" else open
    with opener(out, "wt", encoding="utf-8") as fh:
        header = {
            "match_id": feed.match_id,
            "source": feed.source,
            "label": LABEL,
            "hz": feed.hz,
            "player_ids": feed.player_ids,
            "player_teams": feed.player_teams,
            "attacks_right": feed.attacks_right,
        }
        fh.write(json.dumps(header) + "\n")
        for f in feed.frames:
            xy = [None if v != v else round(v, 2) for v in f.xy]
            ball = None if f.ball is None else [round(f.ball[0], 2), round(f.ball[1], 2)]
            fh.write(
                json.dumps({"p": f.period, "t": f.clock_s, "alive": f.alive, "ball": ball, "xy": xy}) + "\n"
            )
    print(f"{len(feed.frames)} frames at {feed.hz:g} Hz -> {out}", file=sys.stderr)


def cmd_svg(args: argparse.Namespace) -> None:
    events = read_jsonl(args.match)
    feed = render_tracking(events, hz=args.hz)
    found = detect_events(feed)
    r = score(events, found, hz=args.hz, frames=len(feed.frames))
    period, start_s = parse_clock(args.at)
    svg = render_svg(
        feed,
        events,
        found,
        period=period,
        start_s=start_s,
        end_s=start_s + args.seconds,
        title=f"Tracking-to-event, {feed.match_id}, from {args.at} for {args.seconds:g} s",
        subtitle=(
            f"Whole match: passes found {_pct(r.passes.recall).strip()}"
            f" (precision {_pct(r.passes.precision).strip()}),"
            f" shots {r.shots.matched}/{r.shots.truth}, kick speed error {r.speed_mae_kmh or 0:.1f} km/h"
        ),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)


def _seeds(text: str) -> list[int]:
    """'900-909' or '900,903,907'."""
    try:
        if "-" in text:
            a, b = (int(x) for x in text.split("-", 1))
            seeds = list(range(a, b + 1))
        else:
            seeds = [int(x) for x in text.split(",") if x.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds look like 900-909 or 900,903") from exc
    if not seeds or len(seeds) > 200 or any(s < 0 for s in seeds):
        raise argparse.ArgumentTypeError("give between 1 and 200 non-negative seeds")
    return seeds


def _non_negative(text: str) -> float:
    value = float(text)
    if not value >= 0:
        raise argparse.ArgumentTypeError("must be zero or more")
    return value


def cmd_benchmark(args: argparse.Namespace) -> None:
    from .report_md import to_markdown

    print(f"{BENCHMARK_NAME}. {LABEL}. Pixel path: {PIXEL_LABEL}.", file=sys.stderr)
    seeds = args.held_out
    if args.quick:
        seeds = seeds[:2]
    result = run_benchmark(
        args.data,
        held_out_seeds=seeds,
        robustness_matches=1 if args.quick else args.robustness_matches,
        pixel_matches=1 if args.quick else args.pixel_matches,
        pixel_seconds=min(args.pixel_seconds, 30.0) if args.quick else args.pixel_seconds,
        images_dir=args.images,
        progress=lambda msg: print(f"  {msg}", file=sys.stderr),
    )
    held = {c.kind: c for c in result.held_out.classes}
    for kind, c in held.items():
        print(f"held-out {kind:<13} P {_pct(c.precision)} R {_pct(c.recall)} F1 {c.f1:.3f} (n={c.support})")
    p = result.held_out.pressure
    print(f"held-out {'pressure':<13} P {_pct(p.precision)} R {_pct(p.recall)} F1 {p.f1:.3f} (n={p.support})")
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    if args.md:
        out = Path(args.md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_markdown(result), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    print(f"done in {result.runtime_s:g} s", file=sys.stderr)


def cmd_clip(args: argparse.Namespace) -> None:
    from .clip import write_clip

    events = held_out_match(args.seed) if args.match is None else read_jsonl(args.match)
    feed = render_tracking(events, hz=args.hz)
    period, start_s = parse_clock(args.at)
    lo = next((k for k, f in enumerate(feed.frames) if f.period == period and f.clock_s >= start_s), None)
    if lo is None:
        raise SystemExit("That clock is not in the match.")
    result = write_clip(feed, lo, args.seconds, args.out, still=args.still)
    print(
        f"{PIXEL_LABEL}. {result['frames']} frames -> {result['clip']} ({result['format']})", file=sys.stderr
    )
    if result["still"]:
        print(f"still -> {result['still']}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matchmind-autoevent", description=f"{BENCHMARK_NAME}. {LABEL}.")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("benchmark", help="the full benchmark: splits, intervals, baseline, sweep, pixel path")
    b.add_argument("--data", default="data/matches", help="folder of tuning matches (published dataset)")
    b.add_argument(
        "--held-out",
        type=_seeds,
        default=list(HELD_OUT_SEEDS),
        help="held-out seeds, e.g. 900-909 (never used for tuning)",
    )
    b.add_argument("--robustness-matches", type=int, default=3)
    b.add_argument("--pixel-matches", type=int, default=3)
    b.add_argument("--pixel-seconds", type=_non_negative, default=180.0, help="0 skips the pixel path")
    b.add_argument("--images", help="write failure-example SVGs to this folder")
    b.add_argument("--json", help="write the full result as JSON")
    b.add_argument("--md", help="write a markdown report")
    b.add_argument("--quick", action="store_true", help="2 held-out matches, short pixel window (smoke run)")
    b.set_defaults(func=cmd_benchmark)

    c = sub.add_parser("clip", help="write a short pixel-path clip (MP4 via ffmpeg, else a PNG strip)")
    c.add_argument("--match", help="match JSONL; default: a held-out match from --seed")
    c.add_argument("--seed", type=int, default=HELD_OUT_SEEDS[0])
    c.add_argument("--at", default="05:00", help="match clock, e.g. 05:00")
    c.add_argument("--seconds", type=_positive, default=10.0)
    c.add_argument("--out", default="data/local/pixel-path.mp4")
    c.add_argument("--still", help="also write the middle frame as a PNG")
    c.add_argument("--hz", type=_positive, default=DEFAULT_HZ)
    c.set_defaults(func=cmd_clip)

    s = sub.add_parser("score", help="detect events from tracking and score them against the simulator")
    s.add_argument("matches", nargs="+", help="match JSONL files")
    s.add_argument("--hz", type=_positive, default=DEFAULT_HZ)
    s.add_argument("--json", help="also write the full reports to this file")
    s.set_defaults(func=cmd_score)

    f = sub.add_parser("frames", help="write the synthetic tracking feed (JSONL, .gz to compress)")
    f.add_argument("match")
    f.add_argument("--out", default="data/local/tracking.jsonl.gz")
    f.add_argument("--hz", type=_positive, default=DEFAULT_HZ)
    f.set_defaults(func=cmd_frames)

    v = sub.add_parser("svg", help="draw true against detected events for a passage of play")
    v.add_argument("match")
    v.add_argument("--at", default="33:40", help="match clock, e.g. 33:40 or 90+2:15")
    v.add_argument("--seconds", type=_positive, default=25.0)
    v.add_argument("--out", default="data/local/autoevent.svg")
    v.add_argument("--hz", type=_positive, default=DEFAULT_HZ)
    v.set_defaults(func=cmd_svg)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
