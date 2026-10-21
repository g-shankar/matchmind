"""Command line: matchmind-autoevent score | frames | svg."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.script import parse_clock

from .detect import detect_events
from .score import LABEL, AutoEventingReport, score
from .svg import render_svg
from .tracking import DEFAULT_HZ, render_tracking


def _pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def _row(r: AutoEventingReport) -> str:
    return (
        f"{r.match_id:<12} passes P {_pct(r.passes.precision)} R {_pct(r.passes.recall)}"
        f" | shots {r.shots.matched}/{r.shots.truth} P {_pct(r.shots.precision)} R {_pct(r.shots.recall)}"
        f" | receiver {_pct(r.receiver_accuracy or 0)} | kick speed error {r.speed_mae_kmh:.1f} km/h"
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
        title=f"Auto-eventing, {feed.match_id}, from {args.at} for {args.seconds:g} s",
        subtitle=(
            f"Whole match: passes found {_pct(r.passes.recall).strip()}"
            f" (precision {_pct(r.passes.precision).strip()}),"
            f" shots {r.shots.matched}/{r.shots.truth}, kick speed error {r.speed_mae_kmh:.1f} km/h"
        ),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="matchmind-autoevent", description=f"Auto-eventing from synthetic tracking. {LABEL}."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("score", help="detect events from tracking and score them against the simulator")
    s.add_argument("matches", nargs="+", help="match JSONL files")
    s.add_argument("--hz", type=float, default=DEFAULT_HZ)
    s.add_argument("--json", help="also write the full reports to this file")
    s.set_defaults(func=cmd_score)

    f = sub.add_parser("frames", help="write the synthetic tracking feed (JSONL, .gz to compress)")
    f.add_argument("match")
    f.add_argument("--out", default="data/local/tracking.jsonl.gz")
    f.add_argument("--hz", type=float, default=DEFAULT_HZ)
    f.set_defaults(func=cmd_frames)

    v = sub.add_parser("svg", help="draw true against detected events for a passage of play")
    v.add_argument("match")
    v.add_argument("--at", default="33:40", help="match clock, e.g. 33:40 or 90+2:15")
    v.add_argument("--seconds", type=float, default=25.0)
    v.add_argument("--out", default="data/local/autoevent.svg")
    v.add_argument("--hz", type=float, default=DEFAULT_HZ)
    v.set_defaults(func=cmd_svg)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
