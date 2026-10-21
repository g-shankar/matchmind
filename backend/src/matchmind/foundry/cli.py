"""Command line: matchmind-foundry export | eval-dataset | eval.

Every command is free and offline: the crew runs pinned to templates and no
Azure service is called.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from matchmind.foundry import evaluation, manifests

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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
