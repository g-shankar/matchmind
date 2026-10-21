"""Foundry tooling: agent manifests generated from the code, the evaluation
dataset (template mode only) and the free local evaluators."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from matchmind.crew import analyst, commentator, llm, recap
from matchmind.crew.contracts import LANGUAGES, PERSONAS, ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.llm import LLMSchemaError
from matchmind.foundry import cli, evaluation, manifests
from matchmind.foundry.contracts import AnalystIn, CommentatorIn, RecapIn
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import TEAMS
from matchmind.stats.state import StatsEngine

BACKEND = Path(__file__).resolve().parents[1]
AGENTS_DIR = BACKEND.parent / "foundry" / "agents"
DEMO = BACKEND / "data" / "matches" / "MM-DEMO-001.jsonl"


@pytest.fixture(scope="module")
def demo_records() -> list[dict]:
    return list(evaluation.match_records(read_jsonl(DEMO)))


# -------------------------------------------------------------- manifests


def test_committed_manifests_match_a_fresh_export(tmp_path):
    written = manifests.export(tmp_path)
    committed = sorted(p.name for p in AGENTS_DIR.glob("*.yaml"))
    assert sorted(p.name for p in written) == committed, "run `matchmind-foundry export`"
    for path in written:
        assert path.read_text("utf-8") == (AGENTS_DIR / path.name).read_text("utf-8"), (
            f"{path.name} is stale: run `matchmind-foundry export`"
        )


def test_manifests_carry_the_real_prompts_and_settings():
    by_name = {m["display_name"]: m for m in manifests.manifests()}
    assert list(by_name) == ["Spotter", "Analyst", "Commentator", "Fact-checker", "Producer"]
    prompts = {
        "Analyst": analyst.ANALYST_SYSTEM,
        "Commentator": commentator.COMMENTATOR_SYSTEM,
        "Producer": recap.RECAP_SYSTEM,
    }
    for name, manifest in by_name.items():
        assert manifest["tools"] == []
        steps = manifest["model_steps"]
        if name in prompts:
            (step,) = steps
            assert step["instructions"] == prompts[name].strip()
            assert step["deployment"] == llm.DEFAULT_DEPLOYMENT
            assert step["temperature"] == llm.TEMPERATURE and step["max_tokens"] == llm.MAX_TOKENS
        else:
            assert steps == [] and manifest["runtime"] == "deterministic"
    # The YAML parses back to the same data.
    for path in AGENTS_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text("utf-8"))
        assert data["schema"] == manifests.MANIFEST_SCHEMA


class RecordingLLM:
    """Records every request; answers with a schema error so the repair path runs too."""

    enabled = True
    model = "recording"

    def __init__(self) -> None:
        self.requests: list[tuple[type[BaseModel], dict]] = []

    def complete_json(self, system, user, schema, timeout_s):
        self.requests.append((schema, user))
        raise LLMSchemaError("not json")


def test_manifest_input_schemas_match_what_the_crew_really_sends():
    rec = RecordingLLM()
    crew = Crew(TEAMS, llm=rec, timeout_s=5.0)
    events = read_jsonl(DEMO)
    stats = StatsEngine(events[0].match_id, "NBR", "HCY")
    bundles = []
    for e in events:
        bundles += crew.process(e, stats.process(e), stats.snapshot(), stats.players())
        for agent in crew.breakers:
            crew.breakers[agent].success()  # keep the breaker shut so every step calls the model
    profile = ViewerProfile(persona="player_spotlight", language="es", favourite_team="NBR")
    for b in bundles[:20]:
        profile.focus_player_id = b.moment.player_ids[0] if b.moment.player_ids else None
        crew.render(b, profile)
    crew.recap(stats.snapshot(), stats.players(), profile)

    contracts = {
        analyst.AnalystOut: AnalystIn,
        commentator.CommentatorOut: CommentatorIn,
        recap.RecapOut: RecapIn,
    }
    seen = {schema for schema, _ in rec.requests}
    assert seen == set(contracts)
    assert any("repair" in user for _, user in rec.requests)
    assert any("favourite_team" in user and "focus_player_id" in user for _, user in rec.requests)
    for schema, user in rec.requests:
        contracts[schema].model_validate(user)  # extra="forbid": any new payload key fails here


# ---------------------------------------------------------------- dataset


def test_dataset_has_azure_evaluation_columns_for_every_persona_and_language(demo_records):
    cards = [r for r in demo_records if r["type"] == "card"]
    recaps = [r for r in demo_records if r["type"] == "recap"]
    assert len(recaps) == 20
    assert {(r["persona"], r["language"]) for r in cards} == {
        (p, lang) for p in PERSONAS for lang in LANGUAGES
    }
    for r in demo_records:
        assert evaluation.check_record_fields(r) == []
        assert json.loads(r["context"]) == r["facts"]
        assert r["produced_by"] == "template"
    assert len({r["id"] for r in demo_records}) == len(demo_records)


def test_dataset_never_calls_paid_ai_even_with_the_switch_on(monkeypatch):
    """Project lesson: pass TemplateLLM() explicitly; llm=None would follow the switch."""
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "true")

    def refuse(*a, **kw):
        raise AssertionError("evaluation must never build a paid model client")

    monkeypatch.setattr(llm.AzureOpenAILLM, "__init__", refuse)
    records = list(evaluation.match_records(read_jsonl(DEMO)[:300]))
    assert records and {r["produced_by"] for r in records} == {"template"}


def test_dataset_is_reproducible(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    evaluation.build_dataset([DEMO], a)
    evaluation.build_dataset([DEMO], b)  # a rerun writes the same file, nothing stale carried over
    assert a.read_bytes() == b.read_bytes()


# ------------------------------------------------------------- evaluators


def _card(**kw) -> dict:
    base = {
        "id": "x",
        "type": "card",
        "match_id": "M",
        "persona": "casual",
        "language": "en",
        "focus_player": None,
        "produced_by": "template",
        "headline": "Kerrigan scores",
        "body": "Kerrigan finds the corner from 12 m.",
        "facts": {"player": "Adam Kerrigan", "player_short": "Kerrigan", "distance_m": 12, "xg": 0.31},
    }
    base.update(kw)
    base["response"] = f"{base['headline']}\n{base['body']}"
    return base


def test_groundedness_catches_an_invented_number():
    assert evaluation.eval_groundedness(_card())[0]
    ok, reason = evaluation.eval_groundedness(_card(body="Kerrigan finds the corner from 14 m."))
    assert not ok and "14" in reason


def test_strict_groundedness_catches_number_words():
    assert evaluation.eval_groundedness(_card(body="Kerrigan scores his third of the day."))[0]
    assert not evaluation.eval_groundedness(_card(body="Kerrigan scores his third of the day."), strict=True)[
        0
    ]


def test_length_rule():
    assert evaluation.eval_length(_card())[0]
    assert not evaluation.eval_length(_card(headline="one two three four five six seven eight nine"))[0]


def test_persona_rules():
    assert not evaluation.eval_persona(_card(body="Kerrigan converts a 0.31 xG chance."))[0]  # casual jargon
    assert evaluation.eval_persona(_card(persona="tactical", body="A 0.31 xG chance from 12 m."))[0]
    assert not evaluation.eval_persona(_card(persona="tactical", body="Kerrigan finds the corner."))[0]
    assert not evaluation.eval_persona(_card(persona="fantasy", body="Adds 0.31 xT."))[0]
    spot = _card(persona="player_spotlight", focus_player="Rui Mallick")
    assert not evaluation.eval_persona(spot)[0]
    assert evaluation.eval_persona(_card(persona="player_spotlight", focus_player="Adam Kerrigan"))[0]


@pytest.mark.parametrize(
    ("language", "headline", "body", "ok"),
    [
        ("es", "Gol de Kerrigan", "Kerrigan define desde 12 m con una ocasión de 0,31 xG.", True),
        (
            "es",
            "Kerrigan scores",
            "Kerrigan finds the corner from 12 m.",
            False,
        ),  # English leaked into Spanish
        ("fr", "But de Kerrigan", "Kerrigan trouve le petit filet à 12 m.", True),
        ("fr", "Gol de Kerrigan", "Kerrigan define desde 12 m con una ocasión.", False),
        ("ar", "هدف Kerrigan", "Kerrigan يسجل من 12 م.", True),
        ("ja", "Kerriganのゴール", "Kerriganが12 mから決めました。", True),
        ("ja", "Kerrigan scores", "Kerrigan finds the corner from 12 m.", False),
    ],
)
def test_language_sanity(language, headline, body, ok):
    assert evaluation.eval_language(_card(language=language, headline=headline, body=body))[0] is ok


def test_demo_scorecard_meets_the_gates(demo_records):
    result = evaluation.evaluate(demo_records)
    scores = {name: by["all"]["rate"] for name, by in result["scores"].items()}
    assert scores["groundedness_numbers"] == 1.0  # the crew never shows an ungrounded number
    assert scores["length"] == 1.0
    assert scores["language"] >= 0.99
    text = evaluation.scorecard(result)
    assert "groundedness_numbers" in text and "language" in text


def test_cli_end_to_end(tmp_path, capsys):
    data = tmp_path / "set.jsonl"
    assert cli.main(["eval-dataset", "--matches", str(DEMO), "--out", str(data)]) == 0
    out_json = tmp_path / "result.json"
    assert cli.main(["eval", "--data", str(data), "--json", str(out_json), "--min-rate", "0.99"]) == 0
    assert "PitchPulse crew evaluation" in capsys.readouterr().out
    assert json.loads(out_json.read_text())["records"] == len(evaluation.read_dataset(data))
    assert cli.main(["eval", "--data", str(tmp_path / "missing.jsonl")]) == 2
    assert cli.main(["export", "--out", str(tmp_path / "agents")]) == 0
    assert len(list((tmp_path / "agents").glob("*.yaml"))) == 5
