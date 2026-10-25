"""The committed OpenAPI contract (docs/openapi.json) matches the live app."""

import json

from matchmind.api.openapi_export import SPEC_PATH, build_spec, render


def test_committed_openapi_matches_live_schema():
    assert SPEC_PATH.is_file(), "docs/openapi.json missing: run `make openapi`"
    committed = SPEC_PATH.read_text(encoding="utf-8")
    assert committed == render(build_spec()), (
        "API schema drifted: run `make openapi` and commit docs/openapi.json"
    )


def test_spec_is_openapi_3_with_paths():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "PitchPulse match API"
    assert "/api/metrics" in spec["paths"]
