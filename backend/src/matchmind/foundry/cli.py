"""Command line: matchmind-foundry export | eval-dataset | eval | register | trace-demo.

`export`, `eval-dataset`, `eval` and `register --dry-run` are free and offline:
the crew runs pinned to templates and no Azure service is called.

`register` and `trace-demo` are owner steps against a Microsoft Foundry project
(setup/owner-todo.md). They sign in with Microsoft Entra ID (`az login`), never
a key, and refuse to run in CI. `trace-demo` makes a few paid model calls, so
it also needs `--yes`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

from matchmind.foundry import agent_service, evaluation, manifests

TRACE_DEMO_MAX_MOMENTS = 10

REPO_DIR = evaluation.BACKEND_DIR.parent
DEFAULT_AGENTS_DIR = REPO_DIR / "foundry" / "agents"
DEFAULT_DATASET = evaluation.BACKEND_DIR / "data" / "local" / "pitchpulse-evaluation.jsonl"


def cmd_export(args: argparse.Namespace) -> int:
    for path in manifests.export(args.out):
        print(path)
    return 0


def cmd_eval_dataset(args: argparse.Namespace) -> int:
    files = [f for spec in args.matches for f in evaluation.match_files(spec)]
    if not files:
        print("No match files found.", file=sys.stderr)
        return 2
    counts = evaluation.build_dataset(files, args.out)
    for match_id, c in counts.items():
        print(
            f"{match_id}: {c['records']} records, {c['dropped']} cards withheld by the crew", file=sys.stderr
        )
    print(f"{sum(c['records'] for c in counts.values())} records -> {args.out}", file=sys.stderr)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    path = Path(args.data)
    if not path.is_file():
        print(f"Dataset not found: {path}. Run `matchmind-foundry eval-dataset` first.", file=sys.stderr)
        return 2
    records = evaluation.read_dataset(path)
    result = evaluation.evaluate(records)
    print(evaluation.scorecard(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.min_rate is not None:
        low = {
            name: by["all"]["rate"]
            for name, by in result["scores"].items()
            if name in args.gate and by["all"]["rate"] < args.min_rate
        }
        if low:
            print(f"\nBelow {args.min_rate:.0%}: {low}", file=sys.stderr)
            return 1
    return 0


def _owner_only(command: str) -> str | None:
    """Why this owner step cannot run here, or None."""
    if os.environ.get("CI", "").strip().lower() not in ("", "0", "false"):
        return f"`{command}` changes a Foundry project and is run by the owner, never in CI."
    return None


def _endpoint(args: argparse.Namespace) -> str | None:
    endpoint = (args.endpoint or agent_service.project_endpoint()).strip()
    if not endpoint.startswith("https://"):
        print(
            "Set MATCHMIND_FOUNDRY_PROJECT_ENDPOINT (or pass --endpoint) to the Foundry project endpoint, "
            "https://<resource>.services.ai.azure.com/api/projects/<project>.",
            file=sys.stderr,
        )
        return None
    return endpoint


def service_for(endpoint: str) -> agent_service.AgentServiceClient:
    """The Agent Service client the owner commands use (tests swap in a fake)."""
    return agent_service.AzureAgentService(endpoint)


def cmd_register(args: argparse.Namespace) -> int:
    specs = agent_service.agent_specs(args.model)
    if args.dry_run:
        payloads = [{"agent_name": spec.name, "body": spec.body()} for spec in specs]
        print(json.dumps(payloads, indent=2, ensure_ascii=False))
        return 0
    refusal = _owner_only("register")
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    endpoint = _endpoint(args)
    if endpoint is None:
        return 2
    service = service_for(endpoint)
    try:
        results = agent_service.register(service, specs)
    except Exception as exc:  # noqa: BLE001 - one plain line, never provider text
        print(
            f"Registration stopped ({type(exc).__name__}). Check `az login` and that you have the "
            "Azure AI User role on the project.",
            file=sys.stderr,
        )
        return 1
    for action, record in results:
        print(f"{action:<9} {record.name} (version {record.version})")
    return 0


def cmd_trace_demo(args: argparse.Namespace) -> int:
    refusal = _owner_only("trace-demo")
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    if not args.yes:
        print(
            f"trace-demo makes up to {4 * args.moments} paid model calls through Foundry Agent Service. "
            "Run it again with --yes to go ahead.",
            file=sys.stderr,
        )
        return 2
    endpoint = _endpoint(args)
    if endpoint is None:
        return 2
    service = service_for(endpoint)
    _tracing_from_project(service)
    try:
        lines = run_trace_demo(service, args.moments, args.model)
    except Exception as exc:  # noqa: BLE001
        print(f"trace-demo stopped ({type(exc).__name__}).", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    _flush_tracing()
    print(
        "Traces: Foundry portal > your project > Tracing (spans arrive within a few minutes). "
        "Agent runs: Foundry portal > Agents > pitchpulse-analyst / pitchpulse-commentator.",
        file=sys.stderr,
    )
    return 0


def run_trace_demo(
    service: agent_service.AgentServiceClient, moments: int, model: str | None = None
) -> list[str]:
    """The first `moments` moments of the demo match through the Foundry path:
    Analyst and Commentator agents, fact-checked, chained by Agent Framework when
    it is installed. The model budget caps the calls at 4 per moment."""
    from matchmind.crew.contracts import ViewerProfile
    from matchmind.crew.crew import Crew
    from matchmind.crew.llm import ModelBudget
    from matchmind.crew.translator import OffTranslator
    from matchmind.simulator.publisher import read_jsonl
    from matchmind.simulator.teams import get_team
    from matchmind.stats.state import StatsEngine

    events = list(read_jsonl(evaluation.DEFAULT_MATCHES / "MM-DEMO-001.jsonl"))
    home, away = str(events[0].details["home"]), str(events[0].details["away"])
    stats = StatsEngine(events[0].match_id, home, away)
    orchestrator = "agent_framework" if importlib.util.find_spec("agent_framework") else "in_process"
    crew = Crew(
        {home: get_team(home), away: get_team(away)},
        llm=agent_service.FoundryAgentsLLM(service, model=model),
        budget=ModelBudget(total=4 * moments, per_minute=30),
        translator=OffTranslator(),
        orchestrator=orchestrator,
    )
    lines = [f"orchestrator: {crew.orchestrator}, provider: {crew.status().provider}"]
    done = 0
    for event in events:
        if done >= moments:
            break
        metrics = stats.process(event)
        for bundle in crew.process(event, metrics, stats.snapshot(), stats.players()):
            if done >= moments:
                break
            card = crew.render(bundle, ViewerProfile())
            explanation = bundle.explanation
            lines.append(
                f"{bundle.moment.match_clock} {bundle.moment.kind.value}: analyst={explanation.produced_by}"
                f"{'/' + explanation.fallback_reason if explanation.fallback_reason else ''} "
                f"commentator={card.produced_by if card else 'none'}"
                f"{'/' + card.fallback_reason if card and card.fallback_reason else ''}"
            )
            done += 1
    status = crew.status()
    lines.append(f"fallbacks: {status.fallbacks}, rejections: {status.rejections}")
    return lines


def _tracing_from_project(service: agent_service.AgentServiceClient) -> None:
    """Send the crew's spans to the project's Application Insights, signed in with
    Entra ID, unless the environment already says where they go."""
    from matchmind.crew import telemetry

    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        project = getattr(service, "project_client", None)
        try:
            conn = project().telemetry.get_application_insights_connection_string() if project else None
        except Exception as exc:  # noqa: BLE001 - tracing is optional
            print(
                f"Tracing is off: no Application Insights on the project ({type(exc).__name__}).",
                file=sys.stderr,
            )
            return
        if not conn:
            return
        os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = conn
        os.environ.setdefault("APPLICATIONINSIGHTS_AUTHENTICATION_STRING", "Authorization=AAD")
    os.environ.setdefault("OTEL_SERVICE_NAME", "pitchpulse-crew")
    telemetry.reset()


def _flush_tracing() -> None:
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except Exception:  # noqa: BLE001 - tracing is optional
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matchmind-foundry", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("export", help="write the five agent manifests from the code")
    p.add_argument("--out", default=str(DEFAULT_AGENTS_DIR), help="output folder (default: foundry/agents)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("eval-dataset", help="voice every moment of every match into an evaluation JSONL")
    p.add_argument(
        "--matches",
        nargs="+",
        default=[str(evaluation.DEFAULT_MATCHES)],
        help="match JSONL files or folders (default: backend/data/matches)",
    )
    p.add_argument("--out", default=str(DEFAULT_DATASET), help="output JSONL")
    p.set_defaults(func=cmd_eval_dataset)

    p = sub.add_parser("eval", help="run the free local evaluators and print a scorecard")
    p.add_argument("--data", default=str(DEFAULT_DATASET), help="dataset JSONL from eval-dataset")
    p.add_argument("--json", help="also write the full result as JSON")
    p.add_argument("--min-rate", type=float, help="exit 1 if a gated evaluator's overall rate is lower")
    p.add_argument(
        "--gate",
        nargs="+",
        default=["groundedness_numbers", "length"],
        help="evaluators --min-rate applies to",
    )
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser(
        "register", help="create or update the Foundry Agent Service agents from the agent cards (owner step)"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the exact request payloads; no sign-in, no calls"
    )
    p.add_argument(
        "--endpoint", help="Foundry project endpoint (default: MATCHMIND_FOUNDRY_PROJECT_ENDPOINT)"
    )
    p.add_argument("--model", help="model deployment name (default: MATCHMIND_FOUNDRY_MODEL or gpt-4o-mini)")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser(
        "trace-demo", help="run a few demo moments through the Foundry agents, for portal traces (owner step)"
    )
    p.add_argument(
        "--moments",
        type=int,
        default=3,
        choices=range(1, TRACE_DEMO_MAX_MOMENTS + 1),
        metavar="N",
        help=f"moments to voice, 1-{TRACE_DEMO_MAX_MOMENTS} (default 3)",
    )
    p.add_argument("--yes", action="store_true", help="confirm the paid model calls")
    p.add_argument(
        "--endpoint", help="Foundry project endpoint (default: MATCHMIND_FOUNDRY_PROJECT_ENDPOINT)"
    )
    p.add_argument("--model", help="model deployment name (default: MATCHMIND_FOUNDRY_MODEL or gpt-4o-mini)")
    p.set_defaults(func=cmd_trace_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
