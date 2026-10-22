"""Command line: matchmind-ingest validate | play <file>.

    matchmind-ingest validate feed.jsonl
    matchmind-ingest validate feed.csv --mapping mapping.yaml --roster roster.yaml
    matchmind-ingest play feed.csv --mapping mapping.yaml --roster roster.yaml
    matchmind-ingest play feed.jsonl --serve        # the full app on this feed

`play` runs the feed through the same session pipeline as the app (stats engine,
crew in template mode, bookmarks, recap) and prints what came out. It never
calls a paid model. `--serve` starts the API on the feed instead, exactly as
`MATCHMIND_MATCH_FILE=... matchmind-api` would.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from .errors import IngestError
from .feed import Feed, load_feed


def _load(args: argparse.Namespace) -> Feed:
    return load_feed(args.file, roster=args.roster, mapping=args.mapping)


def _summary(feed: Feed) -> dict:
    start, end = feed.events[0], feed.events[-1]
    home, away = str(start.details["home"]), str(start.details["away"])
    return {
        "match_id": feed.match_id,
        "format": feed.source,
        "home": {"team_id": home, "name": feed.teams[home].name},
        "away": {"team_id": away, "name": feed.teams[away].name},
        "events": len(feed.events),
        "final_score": f"{end.details.get('score_home', '?')}-{end.details.get('score_away', '?')}",
        "event_types": dict(sorted(Counter(e.type.value for e in feed.events).items())),
    }


def cmd_validate(args: argparse.Namespace) -> None:
    summary = _summary(_load(args))
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(
        f"OK {summary['match_id']} ({summary['format']}): {summary['home']['name']} "
        f"{summary['final_score']} {summary['away']['name']}, {summary['events']} events"
    )
    for name, count in summary["event_types"].items():
        print(f"  {name:<14}{count:>6}")


def play_feed(feed: Feed) -> dict:
    """Play a feed straight through the session pipeline with the template crew."""
    from matchmind.api.session import Engines, MatchSession
    from matchmind.crew.contracts import ViewerProfile
    from matchmind.crew.crew import Crew
    from matchmind.crew.llm import TemplateLLM
    from matchmind.crew.translator import OffTranslator
    from matchmind.stats.state import StatsEngine

    def template_crew(teams):
        return Crew(teams, llm=TemplateLLM(), translator=OffTranslator())

    clock = [0.0]
    engines = Engines(stats=StatsEngine, crew=template_crew, bookmark_crew=template_crew)
    session = MatchSession(feed.events, teams=feed.teams, engines=engines, clock=lambda: clock[0])
    session.set_speed(60)
    moments = 0
    while not session.ended:
        clock[0] += 60.0
        moments += sum(len(t.bundles) for t in session.advance())
    recap = session.recap(ViewerProfile())
    home, away = session.score
    return {
        "match_id": session.match_id,
        "score": f"{home}-{away}",
        "events_played": session.next_index,
        "moments": moments,
        "bookmarks": [f"{b.match_clock} {b.title}" for b in session.bookmarks],
        "recap_headline": recap.headline,
        "recap_fact_check": recap.fact_check.model_dump(mode="json"),
    }


def cmd_play(args: argparse.Namespace) -> None:
    feed = _load(args)
    if args.serve:
        os.environ["MATCHMIND_MATCH_FILE"] = str(Path(args.file).resolve())
        for env, value in (("MATCHMIND_ROSTER_FILE", args.roster), ("MATCHMIND_FEED_MAPPING", args.mapping)):
            if value:
                os.environ[env] = str(Path(value).resolve())
        os.environ["MATCHMIND_SOURCE"] = "file"
        from matchmind.api.__main__ import main as serve

        print(f"serving {feed.match_id} ...", file=sys.stderr)
        serve()
        return
    result = play_feed(feed)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(
        f"played {result['match_id']}: {result['score']}, {result['events_played']} events, "
        f"{result['moments']} moments"
    )
    for line in result["bookmarks"][:20]:
        print(f"  {line}")
    print(f"recap: {result['recap_headline']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="matchmind-ingest", description="Check and play an external synthetic event feed"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, help_text in (
        ("validate", cmd_validate, "check a feed strictly and summarise it"),
        ("play", cmd_play, "play a feed through the session pipeline (template crew)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("file", help="a .jsonl feed in our event schema, or a .csv with --mapping")
        p.add_argument("--roster", help="roster file (YAML/JSON) for clubs other than the bundled two")
        p.add_argument("--mapping", help="mapping file (YAML/JSON) for a generic CSV feed")
        p.add_argument("--json", action="store_true", help="print JSON")
        if name == "play":
            p.add_argument("--serve", action="store_true", help="start the API on this feed instead")
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except IngestError as exc:
        print(f"REJECTED: {exc.summary}", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
