"""The ingest adapter: external feeds (our JSON lines, the generic CSV) checked strictly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from conftest import FAKE_ENGINES, FakeClock
from matchmind.api import session as session_mod
from matchmind.ingest import IngestError, Limits, load_feed, validate_events
from matchmind.ingest.cli import main as ingest_main
from matchmind.ingest.cli import play_feed
from matchmind.ingest.csv_feed import read_csv_feed
from matchmind.ingest.roster import load_roster, roster_from_data
from matchmind.schema import Event, EventType, LineupPlayer
from matchmind.simulator.publisher import read_jsonl, write_jsonl

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "data" / "matches"
EXAMPLES = BACKEND / "data" / "examples"
DEMO = DATA / "MM-DEMO-001.jsonl"


@pytest.fixture(scope="module")
def demo() -> list[Event]:
    return read_jsonl(DEMO)


def _roster_dict() -> dict:
    return yaml.safe_load((EXAMPLES / "roster.yaml").read_text(encoding="utf-8"))


def _write_mapping(tmp_path: Path, **changes) -> Path:
    mapping = yaml.safe_load((EXAMPLES / "mapping.yaml").read_text(encoding="utf-8"))
    mapping.update(changes)
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(mapping, default=str), encoding="utf-8")
    return path


def _write_csv(tmp_path: Path, rows: list[str], header: str | None = None) -> Path:
    lines = (EXAMPLES / "feed.csv").read_text(encoding="utf-8").splitlines()
    path = tmp_path / "feed.csv"
    path.write_text("\n".join([header or lines[0], *rows]) + "\n", encoding="utf-8")
    return path


def _reject(events: list[Event], match: str, roster=None) -> None:
    with pytest.raises(IngestError, match=match):
        validate_events(events, roster)


# --- the bundled data passes untouched ---------------------------------------------------------


@pytest.mark.parametrize("path", sorted(DATA.glob("*.jsonl")), ids=lambda p: p.stem)
def test_bundled_matches_pass_and_normalising_changes_nothing(path: Path):
    feed = load_feed(path)
    assert feed.events == read_jsonl(path)
    assert set(feed.teams) == {"NBR", "HCY"}


# --- rejections: every rule has a failing case ---------------------------------------------------


def test_feed_must_start_with_match_start_and_end_with_match_end(demo):
    _reject(demo[1:], "must begin with a match_start")
    _reject(demo[:-1], "must end with a match_end")
    _reject([], "empty")


def test_unknown_club_needs_a_roster(demo):
    start = demo[0].model_copy(update={"details": {**demo[0].details, "home": "XYZ"}})
    _reject([start, *demo[1:]], "not one of the bundled clubs")


def test_player_not_in_the_line_up_is_refused(demo):
    i = next(i for i, e in enumerate(demo) if e.type == EventType.PASS)
    bad = demo[i].model_copy(update={"player_id": "NBR-99"})
    _reject([*demo[:i], bad, *demo[i + 1 :]], "not in the line-ups")


def test_player_in_the_wrong_team_is_refused(demo):
    i = next(i for i, e in enumerate(demo) if e.type == EventType.PASS and e.team == "NBR")
    bad = demo[i].model_copy(update={"team": "HCY"})
    _reject([*demo[:i], bad, *demo[i + 1 :]], "does not play for")


def test_receiver_and_details_ids_are_checked(demo):
    i = next(i for i, e in enumerate(demo) if e.type == EventType.FOUL)
    bad = demo[i].model_copy(update={"details": {"fouled_id": "ZZZ-4"}})
    _reject([*demo[:i], bad, *demo[i + 1 :]], "details.fouled_id")


def test_clock_running_backwards_is_refused(demo):
    i = 500
    bad = demo[i].model_copy(update={"clock_s": demo[i - 1].clock_s - 30})
    _reject([*demo[:i], bad, *demo[i + 1 :]], "runs backwards")


def test_same_second_events_are_fine(demo):
    i = 500
    same = demo[i].model_copy(update={"clock_s": demo[i - 1].clock_s, "ts": demo[i - 1].ts})
    events, _ = validate_events([*demo[:i], same, *demo[i + 1 :]])
    assert events[i].clock_s == events[i - 1].clock_s


def test_seq_must_strictly_increase_and_ids_be_unique(demo):
    _reject([*demo[:10], demo[9].model_copy(update={"event_id": "x-1"}), *demo[10:]], "seq")
    dup = demo[11].model_copy(update={"event_id": demo[10].event_id})
    _reject([*demo[:11], dup, *demo[12:]], "appears twice")


def test_only_one_match_start(demo):
    again = demo[0].model_copy(
        update={"seq": demo[5].seq, "event_id": "again", "clock_s": demo[5].clock_s, "ts": demo[5].ts}
    )
    _reject([*demo[:5], again, *demo[6:]], "exactly one match_start")


def test_clock_outside_its_half_is_refused(demo):
    i = 100
    bad = demo[i].model_copy(update={"clock_s": 4600.0})  # period 1 cannot reach 76:40
    _reject([*demo[:i], bad, *demo[i + 1 :]], "outside period 1")


def test_naive_timestamps_are_refused(tmp_path, demo):
    path = tmp_path / "feed.jsonl"
    write_jsonl(demo, path)
    text = path.read_text(encoding="utf-8").replace(
        '"ts":"2026-10-24T15:00:00Z"', '"ts":"2026-10-24T15:00:00"', 1
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(IngestError, match="time zone"):
        load_feed(path)


def test_infinite_speed_is_refused(demo):
    i = next(i for i, e in enumerate(demo) if e.ball_speed_mps)
    bad = demo[i].model_copy(update={"ball_speed_mps": float("inf")})
    _reject([*demo[:i], bad, *demo[i + 1 :]], "ball_speed_mps")


@pytest.mark.parametrize(
    "details, match",
    [
        ({"label": "Kane scores again"}, "real name"),
        ({"label": "bad\x00text"}, "control characters"),
        ({"label": "x" * 200}, "longer than"),
        ({"Bad-Key": 1}, "lower_snake_case"),
        ({f"k{i}": i for i in range(20)}, "more than 16 keys"),
    ],
)
def test_details_are_untrusted_text(demo, details, match):
    i = next(i for i, e in enumerate(demo) if e.type == EventType.MILESTONE)
    bad = demo[i].model_copy(update={"details": details})
    _reject([*demo[:i], bad, *demo[i + 1 :]], match)


def test_labels_are_capped(demo):
    bad = demo[3].model_copy(update={"labels": ["<script>"]})
    _reject([*demo[:3], bad, *demo[4:]], "labels")


def test_line_up_names_must_match_the_roster(demo):
    lineups = list(demo[0].lineups or [])
    lineups[0] = lineups[0].model_copy(update={"name": "Somebody Else"})
    _reject([demo[0].model_copy(update={"lineups": lineups}), *demo[1:]], "does not match the roster")


def test_size_caps(tmp_path, demo):
    path = tmp_path / "feed.jsonl"
    write_jsonl(demo, path)
    with pytest.raises(IngestError, match="larger than"):
        load_feed(path, limits=Limits(max_bytes=1024))
    with pytest.raises(IngestError, match="longer than"):
        load_feed(path, limits=Limits(max_line_bytes=2048))  # match_start with line-ups is bigger
    with pytest.raises(IngestError, match="more than 100 events"):
        load_feed(path, limits=Limits(max_events=100))


def test_bad_json_line_names_the_line(tmp_path, demo):
    path = tmp_path / "feed.jsonl"
    write_jsonl(demo[:5], path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"not": "an event"}\n')
    with pytest.raises(IngestError) as info:
        load_feed(path)
    assert any(p.startswith("line 6") for p in info.value.problems)


def test_unknown_suffix_and_csv_without_mapping(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(IngestError, match=r"\.jsonl"):
        load_feed(tmp_path / "a.txt")
    with pytest.raises(IngestError, match="mapping file"):
        load_feed(EXAMPLES / "feed.csv", roster=EXAMPLES / "roster.yaml")


# --- rosters --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, value, match",
    [
        (("teams", 0, "name"), "Chelsea Rovers", "real name"),
        (("teams", 0, "players", 9, "name"), "Erling Haaland", "real name"),
        (("teams", 0, "players", 9, "name"), "R0bot 9000", "letters"),
        (("teams", 0, "team_id"), "rvt1", "capital letters"),
        (("teams", 0, "primary_color"), "red", "#rrggbb"),
        (("teams", 0, "style"), "Plays like Arsenal", "real name"),
    ],
)
def test_roster_rejects_real_or_odd_names(path, value, match):
    data = _roster_dict()
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(IngestError, match=match):
        roster_from_data(data)


def test_roster_needs_unique_numbers_and_a_keeper():
    data = _roster_dict()
    data["teams"][0]["players"][1]["number"] = 1
    with pytest.raises(IngestError, match="same shirt number"):
        roster_from_data(data)
    data = _roster_dict()
    data["teams"][0]["players"][0]["position"] = "CB"
    with pytest.raises(IngestError, match="goalkeeper"):
        roster_from_data(data)


def test_roster_file_size_cap(tmp_path):
    path = tmp_path / "roster.yaml"
    path.write_text("#" * (70 * 1024), encoding="utf-8")
    with pytest.raises(IngestError, match="larger than"):
        load_roster(path)


def test_external_ids_are_normalised_to_team_and_number(demo):
    """A feed with its own player ids and lower-case clubs comes out canonical."""
    ids = {lp.player_id: f"p{n}" for n, lp in enumerate(demo[0].lineups or [])}
    lineups = [
        LineupPlayer(**{**lp.model_dump(), "player_id": ids[lp.player_id], "team": lp.team.lower()})
        for lp in demo[0].lineups or []
    ]
    start = demo[0].model_copy(update={"lineups": lineups, "match_id": "mm-demo-001"})

    def rename(e: Event) -> Event:
        upd: dict = {}
        if e.player_id:
            upd["player_id"] = ids[e.player_id]
        if e.team:
            upd["team"] = e.team.lower()
        return e.model_copy(update=upd)

    events, _ = validate_events([start, *[rename(e) for e in demo[1:]]])
    i = next(i for i, e in enumerate(demo) if e.player_id)
    assert events[i].player_id == demo[i].player_id and events[i].team == demo[i].team
    assert events[0].match_id == "MM-DEMO-001"
    assert events[0].lineups == demo[0].lineups


# --- the generic CSV ----------------------------------------------------------------------------


def test_example_csv_feed_builds_a_full_match():
    feed = load_feed(
        EXAMPLES / "feed.csv", roster=EXAMPLES / "roster.yaml", mapping=EXAMPLES / "mapping.yaml"
    )
    types = [e.type for e in feed.events]
    assert types[0] == EventType.MATCH_START and types[-1] == EventType.MATCH_END
    assert types.count(EventType.PERIOD_START) == 2 and types.count(EventType.PERIOD_END) == 2
    assert feed.events[-1].details == {"score_home": 2, "score_away": 1}
    assert feed.teams["RVT"].name == "Riverton Athletic"
    # Scaled from a 100 x 100 top-left pitch: the first pass starts on the centre spot.
    first = next(e for e in feed.events if e.type == EventType.PASS)
    assert (first.start.x, first.start.y) == (52.5, 34.0)
    assert first.receiver_id == "RVT-6"  # the next actor, a teammate
    assert len({e.possession_id for e in feed.events if e.possession_id}) > 5


def test_example_csv_feed_plays_through_the_session_pipeline():
    feed = load_feed(
        EXAMPLES / "feed.csv", roster=EXAMPLES / "roster.yaml", mapping=EXAMPLES / "mapping.yaml"
    )
    result = play_feed(feed)
    assert result["score"] == "2-1"
    assert result["events_played"] == len(feed.events)
    assert any("GOAL" in b for b in result["bookmarks"])
    assert result["recap_fact_check"]["ok"] is True


@pytest.mark.parametrize(
    "rows, match",
    [
        (["Pass,0,1,RVT,10,50,50,40,45,,1"], "needs an outcome"),
        (["Teleport,0,1,RVT,10,50,50,40,45,Complete,1"], "not a supported action"),
        (["Pass,0,1,RVT,10,150,50,40,45,Complete,1"], "off a 100 x 100 pitch"),
        (["Pass,0,1,XXX,10,50,50,40,45,Complete,1"], "not playing"),
        (["Pass,0,1,RVT,42,50,50,40,45,Complete,1"], "no player 42"),
        (["Pass,0,1,RVT,10,50,50,40,45,Complete,1", "Pass,0,0,RVT,6,50,50,40,45,Complete,1"], "time order"),
        (["Pass,0,75,RVT,10,50,50,40,45,Complete,1"], "second 0-59"),
        (["Pass,0,1,RVT,10,50,,40,45,Complete,1"], "go together"),
        (["Pass,0,1,RVT,10,50,50,40,45,Complete,3"], "period must be 1 or 2"),
        (["Pass,0,1,RVT," + "9" * 80 + ",50,50,40,45,Complete,1"], "longer than"),
    ],
)
def test_csv_rows_are_checked(tmp_path, rows, match):
    csv_path = _write_csv(tmp_path, rows)
    with pytest.raises(IngestError, match=match) as info:
        load_feed(csv_path, roster=EXAMPLES / "roster.yaml", mapping=EXAMPLES / "mapping.yaml")
    assert "Row 2" in str(info.value) or "Row 3" in str(info.value)


def test_csv_missing_column_and_bad_mapping(tmp_path):
    csv_path = _write_csv(tmp_path, ["Pass,0,1,RVT,10"], header="action,minute,second,player")
    with pytest.raises(IngestError, match="missing the column"):
        load_feed(csv_path, roster=EXAMPLES / "roster.yaml", mapping=EXAMPLES / "mapping.yaml")
    with pytest.raises(IngestError, match="mapping file"):
        read_csv_feed(
            EXAMPLES / "feed.csv",
            _write_mapping(tmp_path, colour="blue"),
            load_roster(EXAMPLES / "roster.yaml"),
        )
    with pytest.raises(IngestError, match="time zone"):
        read_csv_feed(
            EXAMPLES / "feed.csv",
            _write_mapping(tmp_path, kickoff="2026-10-24T15:00:00"),
            load_roster(EXAMPLES / "roster.yaml"),
        )


def test_csv_without_period_column_infers_halves(tmp_path):
    lines = (EXAMPLES / "feed.csv").read_text(encoding="utf-8").splitlines()
    header = lines[0].rsplit(",", 1)[0]
    # Drop the period column and the rows at minute 45 (ambiguous without it).
    rows = [r.rsplit(",", 1)[0] for r in lines[1:] if r.split(",")[1] != "45"]
    path = _write_csv(tmp_path, rows, header=header)
    feed = load_feed(path, roster=EXAMPLES / "roster.yaml", mapping=EXAMPLES / "mapping.yaml")
    assert {e.period for e in feed.events} == {1, 2}


# --- the CLI and the app's file path ------------------------------------------------------------


def test_cli_validate_ok_and_rejected(tmp_path, capsys, demo):
    ingest_main(["validate", str(DEMO)])
    assert "OK MM-DEMO-001" in capsys.readouterr().out
    bad = tmp_path / "bad.jsonl"
    write_jsonl([demo[0].model_copy(update={"details": {"home": "NBR", "away": "NBR"}}), *demo[1:]], bad)
    with pytest.raises(SystemExit) as info:
        ingest_main(["validate", str(bad)])
    assert info.value.code == 1
    assert "REJECTED" in capsys.readouterr().err


def test_cli_play_json(capsys):
    ingest_main(
        [
            "play",
            str(EXAMPLES / "feed.csv"),
            "--roster",
            str(EXAMPLES / "roster.yaml"),
            "--mapping",
            str(EXAMPLES / "mapping.yaml"),
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["match_id"] == "EXT-DEMO-001" and out["score"] == "2-1"


def test_app_plays_a_csv_feed_from_the_env(monkeypatch):
    monkeypatch.setenv("MATCHMIND_MATCH_FILE", str(EXAMPLES / "feed.csv"))
    monkeypatch.setenv("MATCHMIND_FEED_MAPPING", str(EXAMPLES / "mapping.yaml"))
    monkeypatch.setenv("MATCHMIND_ROSTER_FILE", str(EXAMPLES / "roster.yaml"))
    monkeypatch.delenv("MATCHMIND_SOURCE", raising=False)
    s = session_mod.build_session(engines=FAKE_ENGINES)
    assert s.match_id == "EXT-DEMO-001"
    assert s.teams["GLD"].name == "Glenmoor Dynamo"
    assert s.auto_eventing is None  # synthetic tracking only exists for the bundled clubs
    assert s.source_status()["format"] == "csv"


def test_app_refuses_a_bad_feed_with_plain_words(monkeypatch, tmp_path, demo):
    bad = tmp_path / "bad.jsonl"
    write_jsonl(demo[:-1], bad)
    monkeypatch.setenv("MATCHMIND_MATCH_FILE", str(bad))
    with pytest.raises(RuntimeError, match="cannot be played: The feed must end with a match_end"):
        session_mod.load_events()


def test_ingested_session_plays_to_the_end(monkeypatch):
    feed = load_feed(
        EXAMPLES / "feed.csv", roster=EXAMPLES / "roster.yaml", mapping=EXAMPLES / "mapping.yaml"
    )
    clock = FakeClock()
    s = session_mod.MatchSession(feed.events, teams=feed.teams, engines=FAKE_ENGINES, clock=clock)
    while not s.ended:
        clock.t += 100
        s.advance()
    assert s.score == (2, 1)
