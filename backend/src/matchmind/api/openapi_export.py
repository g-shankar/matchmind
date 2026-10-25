"""Export the API's OpenAPI contract to docs/openapi.json.

    python -m matchmind.api.openapi_export          # rewrite docs/openapi.json
    python -m matchmind.api.openapi_export --check  # exit 1 when the file is stale

`tests/test_openapi_contract.py` runs the same comparison, so a route or model
change that is not reflected in the committed file fails the suite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .app import create_app

SPEC_PATH = Path(__file__).resolve().parents[4] / "docs" / "openapi.json"


def build_spec() -> dict:
    """The live schema, independent of environment settings (docs on, no static
    frontend, no MCP mount, which is not part of the schema)."""
    app = create_app(
        tick_interval=None,
        allowed_origins=[],
        static_dir="/nonexistent-static",
        mcp_enabled=False,
        api_docs=True,
    )
    return app.openapi()


def render(spec: dict) -> str:
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the committed file is stale")
    args = parser.parse_args(argv)
    text = render(build_spec())
    if args.check:
        if not SPEC_PATH.is_file() or SPEC_PATH.read_text(encoding="utf-8") != text:
            print("docs/openapi.json is stale: run `make openapi`", file=sys.stderr)
            return 1
        return 0
    SPEC_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {SPEC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
