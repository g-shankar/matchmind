"""The one-command deploy: preview by default, and one switch for the live AI crew.

deployment/deploy.sh runs against a fake `az` that records every call, so no
Azure account is touched.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deployment" / "deploy.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"

FAKE_AZ = """#!/usr/bin/env bash
echo "$*" >> "$AZ_LOG"
case "$1 $2" in
  "group exists") echo "${GROUP_EXISTS:-true}" ;;
  "deployment group")
    case "$*" in
      *registryName*) echo crpitchpulse ;;
      *appUrl*) echo https://ca-pitchpulse.example.test ;;
    esac ;;
  "acr show") echo crpitchpulse.example.test ;;
esac
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
exit 0
"""


def run(tmp_path: Path, *args: str, stdin: str = "", **env: str) -> list[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("az", FAKE_AZ), ("curl", FAKE_CURL)):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    log = tmp_path / "az.log"
    log.write_text("")
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("MATCHMIND_", "DEPLOY_"))}
    clean.update(env, PATH=f"{bin_dir}:{clean['PATH']}", AZ_LOG=str(log))
    subprocess.run(
        ["bash", str(SCRIPT), *args], env=clean, input=stdin, check=True, capture_output=True, text=True
    )
    return log.read_text().splitlines()


def params(calls: list[str]) -> str:
    return next(c for c in calls if "what-if" in c or "deployment group create" in c)


def test_default_is_a_preview_that_creates_nothing(tmp_path):
    calls = run(tmp_path)
    assert any("deployment group what-if" in c for c in calls)
    assert not any("create" in c or "acr build" in c for c in calls)


def test_paid_ai_is_off_unless_switched_on(tmp_path):
    p = params(run(tmp_path))
    assert "aiEnabled=false" in p and "deployOpenAi=false" in p and "deployTranslator=false" in p


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
def test_one_switch_turns_on_the_live_crew_and_its_model(tmp_path, value):
    p = params(run(tmp_path, MATCHMIND_AI_ENABLED=value))
    assert "aiEnabled=true" in p and "deployOpenAi=true" in p
    assert "deployTranslator=false" in p  # Translator keeps its own switch


def test_the_model_deployment_can_still_be_held_back(tmp_path):
    p = params(run(tmp_path, MATCHMIND_AI_ENABLED="true", DEPLOY_OPENAI="false"))
    assert "aiEnabled=true" in p and "deployOpenAi=false" in p


def test_apply_builds_in_the_registry_and_rolls_out_that_image(tmp_path):
    calls = run(tmp_path, "--apply")
    base = next(i for i, c in enumerate(calls) if "deployApps=false" in c)
    build = next(i for i, c in enumerate(calls) if c.startswith("acr build"))
    apps = next(i for i, c in enumerate(calls) if "deployApps=true" in c)
    assert base < build < apps
    assert "containerImage=crpitchpulse.example.test/pitchpulse:" in calls[apps]


def test_paid_ai_deploy_stops_without_a_typed_yes(tmp_path):
    log = tmp_path / "az.log"
    for answer in ("", "no\n"):
        with pytest.raises(subprocess.CalledProcessError):
            run(tmp_path, "--apply", stdin=answer, MATCHMIND_AI_ENABLED="true")
        assert not any("create" in c or "acr build" in c for c in log.read_text().splitlines())


@pytest.mark.parametrize("how", [{"stdin": "yes\n"}, {"CONFIRM_PAID_AI": "yes"}])
def test_paid_ai_deploy_goes_ahead_once_confirmed(tmp_path, how):
    calls = run(tmp_path, "--apply", MATCHMIND_AI_ENABLED="true", **how)
    assert any("deployApps=true" in c and "aiEnabled=true" in c for c in calls)


def test_unknown_options_are_refused(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        run(tmp_path, "--yes")


def test_the_workflow_uses_the_same_one_switch():
    text = WORKFLOW.read_text()
    assert "deployOpenAi=${{ vars.DEPLOY_OPENAI || vars.MATCHMIND_AI_ENABLED || 'false' }}" in text
    assert "aiEnabled=${{ vars.MATCHMIND_AI_ENABLED || 'false' }}" in text
