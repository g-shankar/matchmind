from pathlib import Path

import pytest

from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator import pitch
from matchmind.simulator.publisher import read_jsonl
from matchmind.stats import metrics
from matchmind.stats.better_option import analyse_run, analyse_shot, shot_chance_quality
from matchmind.stats.state import StatsEngine, pressure_index, tempo_label

DATA = Path(__file__).resolve().parents[1] / "data" / "matches"
UNSCRIPTED = ["MM-SYN-001", "MM-SYN-002", "MM-SYN-003", "MM-SYN-004"]
TEMPOS = {"Furious Chaos", "High-Tempo Transition", "Methodical Control", "Total Positional Control"}


def load(match_id: str) -> list[Event]:
    return read_jsonl(DATA / f"{match_id}.jsonl")


@pytest.fixture(scope="module")
def demo() -> list[Event]:
    return load("MM-DEMO-001")


@pytest.fixture(scope="module")
def demo_run(demo):
    """The demo played through one engine: per-event metrics and snapshots."""
    engine = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    out = []
    for e in demo:
        m = engine.process(e)
        out.append((e, m, engine.snapshot()))
    return engine, out


def scripted_shot(events: list[Event], team: str) -> Event:
    return next(
        e
        for e in events
        if e.type == EventType.SHOT and "scripted:missed_option" in e.labels and e.team == team
    )


# ------------------------------------------------------------- metrics


def test_xt_grows_towards_goal_and_is_symmetric():
    assert metrics.xt(5, 34) < metrics.xt(50, 34) < metrics.xt(80, 34) < metrics.xt(100, 34)
    assert metrics.xt(100, 30) == metrics.xt(100, 68 - 30)
    assert metrics.xt(100, 34) > metrics.xt(100, 5)  # central beats wide
    assert metrics.xt(-1, -1) == metrics.XT_GRID[0][0] and metrics.xt(200, 200) == metrics.XT_GRID[7][11]


def test_xt_delta_sign_is_sensible():
    into_box = metrics.xt_delta((70, 34), (96, 34), completed=True)
    backwards = metrics.xt_delta((70, 34), (45, 34), completed=True)
    failed = metrics.xt_delta((70, 34), (96, 34), completed=False)
    assert into_box > 0.1
    assert backwards < 0
    assert failed == -metrics.xt(70, 34)


def test_pass_difficulty_scale_and_terms():
    easy = metrics.pass_difficulty(8, 0, -2, 40, "ground", lane_opponents=0, angle_deg=170)
    hard = metrics.pass_difficulty(45, 2, 35, 90, "through_ball", lane_opponents=3, angle_deg=90)
    assert 0 <= easy < 15 and hard == 100
    # Each new term raises difficulty, and unknown terms keep the 0-100 scale.
    base = metrics.pass_difficulty(20, 1, 10, 60, "ground")
    assert metrics.pass_difficulty(20, 1, 10, 60, "ground", lane_opponents=3) > base
    assert metrics.pass_difficulty(30, 0, 0, 60, "ground", angle_deg=90) > metrics.pass_difficulty(
        30, 0, 0, 60, "ground", angle_deg=0
    )
    assert metrics.pass_difficulty(45, 2, 35, 90, "cross") == 100
    assert metrics.pass_difficulty(20, 2, 10, 60, "ground") > metrics.pass_difficulty(20, 0, 10, 60, "ground")


def test_pass_angle_and_lane_helpers():
    assert metrics.pass_angle_deg((50, 34), (60, 34)) == 0
    assert metrics.pass_angle_deg((50, 34), (50, 44)) == 90
    assert metrics.pass_angle_deg((50, 34), (40, 34)) == 180
    opps = [(55, 34.5), (52, 40), (49, 34)]  # in the lane, wide, behind the passer
    assert metrics.opponents_in_lane((50, 34), (70, 34), opps) == 1


def test_broadcast_thresholds():
    assert metrics.SPEED_BURST_KMH == 30.0
    assert metrics.ROCKET_SHOT_KMH == 100.0
    assert metrics.DISTANCE_MILESTONES_KM == (5.0, 8.0, 10.0)


def test_pressure_index_and_tempo():
    assert pressure_index(0, 0, 0, 0.0) == 0
    assert pressure_index(10, 2, 2, 0.4) > pressure_index(10, 0, 0, 0.0) > 0
    assert pressure_index(500, 50, 50, 5.0) == 100
    assert [tempo_label(x) for x in (-0.9, 0.0, 0.3, 0.9)] == [
        "Furious Chaos",
        "High-Tempo Transition",
        "Methodical Control",
        "Total Positional Control",
    ]


# --------------------------------------------- "Should he have passed?"


@pytest.mark.parametrize("team", ["NBR", "HCY"])
def test_missed_square_ball_is_flagged(demo, team):
    shot = scripted_shot(demo, team)
    open_id = next(lbl.split(":")[1] for lbl in shot.labels if lbl.startswith("better_option:"))
    found = analyse_shot(shot, "NBR")
    assert found is not None
    assert found.teammate_id == open_id and found.shooter_id == shot.player_id
    assert found.times_better >= 2
    assert found.alt_value == pytest.approx(found.pass_success * found.alt_chance_quality, abs=0.002)
    # Output positions are absolute, straight from the freeze frame.
    mate = next(p for p in shot.freeze_frame if p.player_id == open_id)
    assert (found.teammate_pos.x, found.teammate_pos.y) == (mate.x, mate.y)
    assert (found.shooter_pos.x, found.shooter_pos.y) == (shot.start.x, shot.start.y)
    assert found.keeper is not None and found.nearest_marker_m >= 7


def test_demo_shots_flag_only_the_scripted_moments(demo):
    flagged = {e.match_clock[:2] for e in demo if e.type == EventType.SHOT and analyse_shot(e, "NBR")}
    assert flagged == {"34", "78"}


def test_goals_are_never_flagged(demo):
    goals = [e for e in demo if e.type == EventType.SHOT and e.outcome == Outcome.GOAL]
    assert goals and all(analyse_shot(g, "NBR") is None for g in goals)


def test_unfound_run_is_flagged(demo):
    run = next(e for e in demo if e.type == EventType.RUN and "scripted:run_not_found" in e.labels)
    found = analyse_run(run, "NBR")
    assert found is not None
    assert found.runner_id == "HCY-9" and found.carrier_id == "HCY-10" and not found.found
    assert found.pass_on_at_s <= 1.5
    assert found.one_on_one
    assert found.projected_chance_quality >= 0.2
    assert found.clear_of_line_m >= 1.5
    assert found.pass_on_clock.startswith("61:")
    assert len(found.runner_path) == len(run.tracking)
    assert (found.runner_path[0].x, found.runner_path[0].y) == (run.start.x, run.start.y)


def test_found_runs_and_other_events_are_not_flagged(demo):
    for e in demo:
        if e.type == EventType.RUN and e.outcome == Outcome.FOUND:
            assert analyse_run(e, "NBR") is None
    pass_event = next(e for e in demo if e.type == EventType.PASS)
    assert analyse_run(pass_event, "NBR") is None and analyse_shot(pass_event, "NBR") is None


@pytest.mark.parametrize("match_id", UNSCRIPTED)
def test_few_false_flags_in_unscripted_matches(match_id):
    events = load(match_id)
    home = events[0].details["home"]
    flags = sum(1 for e in events if e.type == EventType.SHOT and analyse_shot(e, home))
    flags += sum(1 for e in events if e.type == EventType.RUN and analyse_run(e, home))
    assert flags < 4


# --------------------------------------------------------- stats engine


def test_same_input_same_output(demo, demo_run):
    _, first = demo_run
    again = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    for e, m, snap in first:
        assert again.process(e) == m
        assert again.snapshot() == snap
    assert again.players() == demo_run[0].players()


def test_score_xg_and_shots_match_a_recount(demo, demo_run):
    engine, out = demo_run
    snap = engine.snapshot()
    end = demo[-1].details
    assert (snap.score_home, snap.score_away) == (end["score_home"], end["score_away"]) == (2, 3)
    for team, xg, shots in (("NBR", snap.xg_home, snap.shots_home), ("HCY", snap.xg_away, snap.shots_away)):
        team_shots = [e for e in demo if e.type == EventType.SHOT and e.team == team]
        assert shots == len(team_shots)
        assert xg == pytest.approx(sum(shot_chance_quality(e, "NBR") for e in team_shots), abs=0.01)
    players = engine.players()
    assert sum(p.goals for p in players.values()) == 5
    assert sum(p.xg for p in players.values()) == pytest.approx(snap.xg_home + snap.xg_away, abs=0.02)


def test_hcy_pressure_rises_during_the_spell(demo_run):
    _, out = demo_run

    def mean_hcy_pressure(lo: float, hi: float) -> float:
        values = [s.away.pressure_index for e, _, s in out if e.period == 2 and lo <= e.clock_s < hi]
        return sum(values) / len(values)

    assert mean_hcy_pressure(3600, 4500) > mean_hcy_pressure(2700, 3600)


def test_pass_accuracy_matches_a_recount(demo, demo_run):
    engine, _ = demo_run
    players = engine.players()
    for pid in ("NBR-6", "HCY-8"):
        passes = [e for e in demo if e.type == EventType.PASS and e.player_id == pid]
        done = sum(e.outcome == Outcome.COMPLETE for e in passes)
        p = players[pid]
        assert (p.passes, p.passes_completed) == (len(passes), done)
        assert p.pass_accuracy == round(100 * done / len(passes), 1)
        assert p.model_dump()["pass_accuracy"] == p.pass_accuracy  # serialised for the API


def test_scripted_assists_are_credited(demo, demo_run):
    engine, _ = demo_run
    players = engine.players()
    for goal in (e for e in demo if e.type == EventType.SHOT and e.outcome == Outcome.GOAL):
        assister = goal.details["assist_id"]
        assert players[assister].assists >= 1 and players[assister].key_passes >= 1
    assert sum(p.assists for p in players.values()) <= 5
    assert all(p.xa >= 0 and p.key_passes >= p.assists for p in players.values())


def test_player_counting_stats(demo, demo_run):
    engine, _ = demo_run
    players = engine.players()
    assert len(players) == 22
    for pid, p in players.items():
        mine = [e for e in demo if e.player_id == pid]
        assert p.tackles_won == sum(e.type == EventType.TACKLE for e in mine)
        assert p.interceptions == sum(e.type == EventType.INTERCEPTION for e in mine)
        assert p.shots == sum(e.type == EventType.SHOT for e in mine)
        speeds = [e.player_speed_mps for e in mine if e.player_speed_mps is not None]
        assert p.top_speed_kmh == (round(max(speeds) * 3.6, 1) if speeds else 0.0)
        assert p.sprints == sum(s > metrics.SPRINT_MS for s in speeds)
        assert p.touches >= p.passes + p.shots
    assert players["NBR-4"].distance_km > 0  # sent off, but played 52 minutes
    assert max(p.top_speed_kmh for p in players.values()) > metrics.SPEED_BURST_KMH


def test_distance_is_an_increasing_estimate(demo_run):
    engine, out = demo_run
    seen: dict[str, float] = {}
    replay = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    for e, _, _ in out:
        replay.process(e)
        for p in replay.changed_players():
            assert p.distance_km >= seen.get(p.player_id, 0.0)
            seen[p.player_id] = p.distance_km
    assert all(0 < p.distance_km < 15 for p in engine.players().values())


def test_carry_distance(demo, demo_run):
    engine, _ = demo_run
    pid = "NBR-6"
    expected = sum(
        pitch.dist((e.start.x, e.start.y), (e.end.x, e.end.y))
        for e in demo
        if e.player_id == pid
        and e.type in (EventType.CARRY, EventType.DRIBBLE)
        and e.outcome != Outcome.INCOMPLETE
    )
    assert engine.players()[pid].carry_distance_m == pytest.approx(expected, abs=0.5)


def test_event_metrics_fill_the_right_fields(demo, demo_run):
    _, out = demo_run
    by_id = {e.event_id: m for e, m, _ in out}
    for e, m, _ in out:
        if e.type in (EventType.PASS, EventType.CARRY):
            assert m.xt_delta is not None
        if e.type == EventType.PASS:
            assert m.pass_distance_m is not None and 0 <= m.pass_difficulty <= 100
        if e.type == EventType.SHOT:
            assert 0 < m.chance_quality <= 0.95 and m.distance_to_goal_m is not None
            assert m.fast_shot == (m.ball_speed_kmh >= metrics.ROCKET_SHOT_KMH)
            assert m.xt_delta is None
    assert by_id[scripted_shot(demo, "NBR").event_id].better_option.teammate_id == "NBR-9"
    assert by_id[scripted_shot(demo, "HCY").event_id].better_option.teammate_id == "HCY-9"
    run = next(e for e in demo if e.type == EventType.RUN and "scripted:run_not_found" in e.labels)
    assert by_id[run.event_id].unfound_run.one_on_one
    assert sum(m.better_option is not None for m in by_id.values()) == 2
    assert sum(m.unfound_run is not None for m in by_id.values()) == 1
    # The demo's goal passes into the box add threat.
    goal_pass = next(
        e
        for e in demo
        if e.type == EventType.PASS
        and "scripted:goal" in e.labels
        and e.details["pass_type"] == "through_ball"
    )
    assert by_id[goal_pass.event_id].xt_delta > 0


def test_through_ball_after_a_run_uses_the_tracked_lane(demo, demo_run):
    _, out = demo_run
    seq = {e.seq: e for e in demo}
    found = [e for e in demo if e.type == EventType.RUN and e.outcome == Outcome.FOUND]
    passes = [seq[r.seq + 1] for r in found if seq[r.seq + 1].details.get("pass_type") == "through_ball"]
    assert passes
    engine = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    for e in demo:
        if e.seq == passes[0].seq:
            assert engine._lane_from_run(e) is not None
        engine.process(e)


def test_snapshot_ranges(demo_run):
    _, out = demo_run
    for _, _, s in out:
        assert -100 <= s.momentum <= 100 and -1 <= s.control_chaos <= 1
        assert s.tempo in TEMPOS
        assert s.home.possession_pct + s.away.possession_pct == pytest.approx(100, abs=0.2)
        assert s.events_per_min < 60
    controls = [s.control_chaos for _, _, s in out]
    assert min(controls) < -0.3 and max(controls) > 0.3  # the gauge actually moves
    momenta = [s.momentum for _, _, s in out]
    assert min(momenta) < -20 and max(momenta) > 20


def test_window_is_rolling(demo_run):
    _, out = demo_run
    final = out[-1][2]
    assert final.home.shots + final.away.shots < final.shots_home + final.shots_away


def test_labels_never_change_the_numbers(demo):
    a = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    b = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    for e in demo[:400]:
        assert a.process(e) == b.process(e.model_copy(update={"labels": []}))
    assert a.snapshot() == b.snapshot()


def test_duplicate_delivery_is_not_double_counted(demo):
    engine = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    for e in demo[:300]:
        engine.process(e)
    before = (engine.snapshot(), engine.players())
    again = engine.process(demo[299])
    assert engine.changed_players() == []
    assert (engine.snapshot(), engine.players()) == before
    assert again.event_id == demo[299].event_id
    with pytest.raises(ValueError, match="different content"):
        engine.process(demo[299].model_copy(update={"outcome": Outcome.INCOMPLETE}))
    with pytest.raises(ValueError, match="arrived after"):
        engine.process(demo[100].model_copy(update={"event_id": "MM-DEMO-001-x"}))
    with pytest.raises(ValueError, match="another match"):
        engine.process(demo[300].model_copy(update={"match_id": "OTHER"}))


def test_returned_stats_are_copies(demo):
    engine = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    for e in demo[:200]:
        engine.process(e)
    pid = next(iter(engine.players()))
    engine.players()[pid].goals = 99
    assert engine.players()[pid].goals != 99


def test_changed_players_are_exactly_the_ones_whose_stats_moved(demo):
    engine = StatsEngine("MM-DEMO-001", "NBR", "HCY")
    before = engine.players()
    for e in demo:
        engine.process(e)
        after = engine.players()
        moved = {pid for pid, p in after.items() if before.get(pid) != p}
        changed = engine.changed_players()
        assert moved <= {p.player_id for p in changed}
        assert all(after[p.player_id] == p for p in changed)
        if e.player_id:
            assert e.player_id in {p.player_id for p in changed}
        if e.type == EventType.MATCH_START:
            assert len(changed) == 22
        before = after


def test_replay_helper(demo, demo_run):
    engine = StatsEngine.replay(demo)
    assert engine.snapshot() == demo_run[0].snapshot()
    with pytest.raises(ValueError):
        StatsEngine.replay([])
