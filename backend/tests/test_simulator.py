import json
from collections import Counter

import pytest

from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator import load_script, pitch, random_script, simulate
from matchmind.simulator.cli import main as cli_main
from matchmind.simulator.publisher import read_jsonl, replay, write_jsonl
from matchmind.simulator.script import format_clock, parse_clock

SEED = 7


@pytest.fixture(scope="module")
def demo() -> list[Event]:
    return simulate(load_script("demo"), SEED)


def attacking_frame(team: str, home: str, x: float, y: float) -> tuple[float, float]:
    return (x, y) if team == home else pitch.flip((x, y))


# ---------------------------------------------------------------- contract


def test_same_seed_is_byte_identical(demo):
    again = simulate(load_script("demo"), SEED)
    assert [e.to_json() for e in demo] == [e.to_json() for e in again]


def test_different_seed_changes_the_match(demo):
    other = simulate(load_script("demo"), SEED + 1)
    assert [e.to_json() for e in demo] != [e.to_json() for e in other]


def test_events_are_ordered_and_valid(demo):
    assert [e.seq for e in demo] == list(range(len(demo)))
    assert len({e.event_id for e in demo}) == len(demo)
    assert all(a.ts <= b.ts for a, b in zip(demo, demo[1:], strict=False))
    for a, b in zip(demo, demo[1:], strict=False):
        if a.period == b.period:
            assert a.clock_s <= b.clock_s
    assert demo[0].type == EventType.MATCH_START and demo[-1].type == EventType.MATCH_END
    assert len(demo[0].lineups) == 22


def test_jsonl_round_trip(demo, tmp_path):
    path = write_jsonl(demo, tmp_path / "m.jsonl")
    assert read_jsonl(path) == demo


def test_speeds_match_the_documented_ranges(demo):
    for e in demo:
        if e.type == EventType.PASS:
            assert 10 <= e.ball_speed_mps <= 25
        if e.type == EventType.SHOT:
            assert 20 <= e.ball_speed_mps <= 35
        if e.player_speed_mps is not None:
            assert e.player_speed_mps <= 10


# ------------------------------------------------------------- demo story


def test_demo_story_plays_out(demo):
    goals = [e for e in demo if e.type == EventType.SHOT and e.outcome == Outcome.GOAL]
    reviews = [e for e in demo if e.type == EventType.VAR_REVIEW]
    ruled_out = {r.reviewed_event_id for r in reviews if r.outcome == Outcome.OVERTURNED}
    counted = [g for g in goals if g.event_id not in ruled_out]
    assert [g.player_id for g in counted] == ["NBR-9", "NBR-10", "HCY-10", "HCY-9", "HCY-11"]
    assert demo[-1].details == {"score_home": 2, "score_away": 3}
    assert counted[-1].match_clock.startswith("90+")


def test_demo_goal_ruled_out_by_var_before_the_break(demo):
    """The correction beat: NBR-11 scores just before 40', VAR rules it out for
    offside about 70 s later, and the 41' goal still makes it 2-0."""
    (review,) = [e for e in demo if e.type == EventType.VAR_REVIEW]
    shot = next(e for e in demo if e.event_id == review.reviewed_event_id)
    assert shot.type == EventType.SHOT and shot.outcome == Outcome.GOAL and shot.player_id == "NBR-11"
    assert shot.details["score_home"] == 2 and shot.details["score_away"] == 0
    assert review.outcome == Outcome.OVERTURNED and review.review_reason == "offside"
    assert review.details == {"score_home": 1, "score_away": 0}
    assert review.period == 1 and 2340 <= shot.clock_s < review.clock_s < 2490  # 39:00 .. 41:30
    assert 60 <= review.clock_s - shot.clock_s <= 80
    nxt = demo[demo.index(review) + 1]
    assert nxt.team == "HCY"  # restart: free kick to the defending side
    second = next(e for e in demo if e.type == EventType.SHOT and e.outcome == "goal" and e.seq > review.seq)
    assert second.player_id == "NBR-10" and second.details["score_home"] == 2


def test_var_review_needs_a_target_and_a_verdict():
    base = {
        "event_id": "X-1",
        "match_id": "X",
        "seq": 1,
        "ts": "2026-10-24T15:00:00Z",
        "period": 1,
        "clock_s": 10.0,
        "match_clock": "00:10",
        "type": "var_review",
    }
    with pytest.raises(ValueError):
        Event.model_validate({**base, "outcome": "overturned"})
    with pytest.raises(ValueError):
        Event.model_validate({**base, "reviewed_event_id": "X-0", "outcome": "goal"})
    with pytest.raises(ValueError):
        Event.model_validate({**base, "type": "pass", "reviewed_event_id": "X-0"})
    ok = Event.model_validate(
        {**base, "reviewed_event_id": "X-0", "outcome": "stands", "review_reason": "foul"}
    )
    assert ok.review_reason == "foul"


def test_red_carded_player_disappears(demo):
    red = next(e for e in demo if e.type == EventType.CARD and e.details["card"] == "red")
    assert red.player_id == "NBR-4"
    after = [e for e in demo if e.seq > red.seq]
    assert not any(e.player_id == "NBR-4" for e in after)
    for e in after:
        for p in e.freeze_frame or []:
            assert p.player_id != "NBR-4"


def test_pressure_spell_tilts_possession(demo):
    def hcy_share(lo, hi):
        passes = [e for e in demo if e.type == EventType.PASS and lo <= e.clock_s < hi]
        return Counter(e.team for e in passes)["HCY"] / len(passes)

    assert hcy_share(3600, 4500) > hcy_share(2700, 3600) + 0.05
    spell = [e for e in demo if "pressure_spell:HCY" in e.labels]
    assert spell[0].clock_s >= 3600 and spell[-1].clock_s < 4500


# ------------------------------------------- "Should he have passed?" data


def test_every_shot_has_a_final_third_freeze_frame(demo):
    shots = [e for e in demo if e.type == EventType.SHOT]
    assert shots
    for shot in shots:
        frame = shot.freeze_frame
        assert sum(p.actor for p in frame) == 1
        assert next(p for p in frame if p.actor).player_id == shot.player_id
        for p in frame:
            if not p.actor:
                u, _ = attacking_frame(shot.team, "NBR", p.x, p.y)
                assert u >= 70, f"{p.player_id} outside final third in {shot.event_id}"
        assert any(p.keeper and not p.teammate for p in frame)


@pytest.mark.parametrize("team", ["NBR", "HCY"])
def test_missed_option_has_a_clearly_better_teammate(demo, team):
    shot = next(
        e
        for e in demo
        if e.type == EventType.SHOT and "scripted:missed_option" in e.labels and e.team == team
    )
    open_id = next(lbl.split(":")[1] for lbl in shot.labels if lbl.startswith("better_option:"))
    frame = {p.player_id: p for p in shot.freeze_frame}
    shooter = attacking_frame(team, "NBR", shot.start.x, shot.start.y)
    mate = attacking_frame(team, "NBR", frame[open_id].x, frame[open_id].y)
    opponents = [attacking_frame(team, "NBR", p.x, p.y) for p in frame.values() if not p.teammate]

    assert min(pitch.dist(mate, o) for o in opponents) >= 7.0  # unmarked
    assert pitch.goal_angle(mate) > 2 * pitch.goal_angle(shooter)  # far better angle
    assert pitch.distance_to_goal(mate) < pitch.distance_to_goal(shooter)
    assert min(pitch.dist(shooter, o) for o in opponents) < 3.5  # shooter under pressure


def test_run_not_found_is_clean_through_and_ignored(demo):
    run = next(e for e in demo if e.type == EventType.RUN and "scripted:run_not_found" in e.labels)
    assert run.outcome == Outcome.NOT_FOUND and run.player_id == "HCY-9"
    assert [f.t_offset_s for f in run.tracking] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

    def frame(t):
        f = next(f for f in run.tracking if f.t_offset_s == t)
        runner = next(p for p in f.players if p.actor)
        backs = [p for p in f.players if not p.teammate and not p.keeper]
        to_u = lambda p: attacking_frame("HCY", "NBR", p.x, p.y)[0]  # noqa: E731
        return to_u(runner), max(to_u(p) for p in backs)

    runner0, line0 = frame(0.0)
    runner15, line15 = frame(1.5)
    assert runner0 <= line0  # onside when the run starts
    assert runner15 > line15 + 2  # clear of the back line: the pass was on

    nxt = demo[run.seq + 1]
    assert nxt.type == EventType.PASS and nxt.player_id == "HCY-10"
    assert nxt.receiver_id != "HCY-9"
    assert nxt.clock_s >= run.clock_s + 3.0


def test_random_runs_carry_tracking(demo):
    runs = [e for e in demo if e.type == EventType.RUN]
    assert len(runs) >= 5
    assert {Outcome.FOUND, Outcome.NOT_FOUND} <= {r.outcome for r in runs}
    for r in runs:
        assert len(r.tracking) == 7
        assert sum(p.actor for p in r.tracking[0].players) == 1


# ------------------------------------------------------- random matches


def test_random_matches_look_like_football():
    totals = []
    for seed in range(8):
        events = simulate(random_script(f"R{seed}"), seed)
        shots = [e for e in events if e.type == EventType.SHOT]
        passes = [e for e in events if e.type == EventType.PASS]
        assert 12 <= len(shots) <= 45
        assert 0.7 <= sum(e.outcome == Outcome.COMPLETE for e in passes) / len(passes) <= 0.92
        end = events[-1].details
        totals.append(end["score_home"] + end["score_away"])
    assert 1.0 <= sum(totals) / len(totals) <= 4.5


# ---------------------------------------------------------------- plumbing


@pytest.mark.parametrize(
    ("text", "expected"),
    [("00:00", (1, 0.0)), ("67:20", (2, 4040.0)), ("45+1:30", (1, 2790.0)), ("90+2:15", (2, 5535.0))],
)
def test_parse_clock(text, expected):
    assert parse_clock(text) == expected
    assert format_clock(expected[1], expected[0]) == text


@pytest.mark.parametrize("bad", ["91:00", "60+1:00", "12:75", "abc"])
def test_parse_clock_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        parse_clock(bad)


def test_replay_paces_events_by_match_clock(demo):
    sleeps, sent = [], []
    count = replay(demo[:50], sent.append, speed=60, sleep=sleeps.append)
    assert count == 50 and sent == demo[:50]
    expected = (demo[49].clock_s - demo[0].clock_s) / 60
    assert sum(sleeps) == pytest.approx(expected, abs=1e-6)


def test_cli_generate_and_schema(tmp_path):
    out = tmp_path / "demo.jsonl"
    cli_main(["generate", "--seed", "3", "--out", str(out)])
    assert read_jsonl(out)[-1].type == EventType.MATCH_END
    schema_path = tmp_path / "event.schema.json"
    cli_main(["schema", "--out", str(schema_path)])
    assert "freeze_frame" in json.loads(schema_path.read_text())["properties"]
