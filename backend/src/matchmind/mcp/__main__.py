"""`matchmind-mcp` / `python -m matchmind.mcp`: the PitchPulse MCP tools over stdio.

Loads the demo match (or MATCHMIND_MATCH_FILE) in its own process and parks it
at full time, or at `--clock-s` (and `--period`). The crew runs in template
mode here whatever MATCHMIND_AI_ENABLED says, so a local client can never spend
on paid AI. Logs go to stderr; stdout carries the protocol only.
"""

from __future__ import annotations

import argparse
import logging
import sys

from matchmind.api.session import Engines, MatchSession, build_session


def template_engines() -> Engines:
    from matchmind.crew.crew import Crew
    from matchmind.crew.llm import TemplateLLM
    from matchmind.crew.translator import OffTranslator
    from matchmind.stats.state import StatsEngine

    def crew(teams):
        return Crew(teams, llm=TemplateLLM(), translator=OffTranslator())

    return Engines(stats=StatsEngine, crew=crew, bookmark_crew=crew)


def load(clock_s: float | None, period: int | None, match_file: str | None = None) -> MatchSession:
    session = build_session(match_file, engines=template_engines())
    session.is_running = False  # nothing plays in this process; the tools read a fixed position
    if clock_s is None:
        session.play_to_end()
    else:
        session.seek(clock_s, period)
        session.is_running = False
    return session


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="matchmind-mcp", description="PitchPulse MCP tools over stdio")
    p.add_argument("--clock-s", type=float, default=None, help="match clock in seconds (default: full time)")
    p.add_argument("--period", type=int, choices=(1, 2), default=None, help="half for --clock-s")
    p.add_argument("--match-file", default=None, help="JSONL match (default: the bundled demo match)")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    import anyio

    from matchmind.api.app import Hub

    from .server import build_server

    hub = Hub(load(args.clock_s, args.period, args.match_file))
    anyio.run(build_server(hub).run_stdio_async)


if __name__ == "__main__":
    main()
