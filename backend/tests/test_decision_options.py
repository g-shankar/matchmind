"""The ranked option list behind the "Should he have passed?" replay."""

import json
from pathlib import Path

from matchmind.schema import EventType
from matchmind.stats.better_option import OPTION_METHOD, OPTION_METHOD_VERSION, analyse_shot
from test_stats import load, scripted_shot

HOME = "NBR"
FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo" / "demo-match.json"


def _bo(team: str):
    demo = load("MM-DEMO-001")
    shot = scripted_shot(demo, team)
    return shot, analyse_shot(shot, HOME)


def test_every_teammate_is_ranked_with_the_shot_marked_taken():
    shot, bo = _bo("NBR")
    assert bo is not None
    mates = {p.player_id for p in shot.freeze_frame if p.teammate and not p.actor and not p.keeper}
    passes = [o for o in bo.options if o.kind == "pass"]
    assert {o.player_id for o in passes} == mates
    assert [o.rank for o in bo.options] == list(range(1, len(bo.options) + 1))
    taken = [o for o in bo.options if o.taken]
    assert len(taken) == 1 and taken[0].kind == "shot" and taken[0].player_id == shot.player_id
    assert taken[0].score == bo.shot_chance_quality
    assert bo.method == OPTION_METHOD and bo.method_version == OPTION_METHOD_VERSION


def test_ranking_agrees_with_the_trigger_and_uses_engine_numbers():
    for team in ("NBR", "HCY"):
        _shot, bo = _bo(team)
        best = next(o for o in bo.options if o.kind == "pass")
        assert best.player_id == bo.teammate_id
        assert best.score == bo.alt_value and best.pass_success == bo.pass_success
        assert best.chance_quality == bo.alt_chance_quality
        eligible = [o for o in bo.options if o.eligible]
        assert bo.options[: len(eligible)] == eligible  # eligible first
        assert [o.score for o in eligible] == sorted((o.score for o in eligible), reverse=True)
        for o in bo.options:
            assert o.eligible == (o.onside and o.open)
            if o.kind == "pass":
                assert o.score == round(o.pass_success * o.chance_quality, 3)


def test_ranking_is_deterministic():
    assert _bo("NBR")[1].options == _bo("NBR")[1].options


def test_demo_fixture_carries_the_same_ranking_as_the_engine():
    data = json.loads(FIXTURE.read_text())
    demo = load("MM-DEMO-001")
    by_id = {e.event_id: e for e in demo if e.type == EventType.SHOT}
    moments = [m for m in data["moments"] if m["kind"] == "better_option"]
    assert moments
    for m in moments:
        r = m["replay"]
        assert r["method"] == OPTION_METHOD and r["method_version"] == OPTION_METHOD_VERSION
        bo = analyse_shot(by_id[r["shot_event_id"]], HOME)
        assert [(o["kind"], o["player_id"], o["score"]) for o in r["options"]] == [
            (o.kind, o.player_id, o.score) for o in bo.options
        ]
