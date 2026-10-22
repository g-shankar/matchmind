"""Dataset export: catalog allow-list, formats, tracking sample, data dictionary, API and CLI."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FAKE_ENGINES, FakeClock
from matchmind.analytics.sources import generate_match
from matchmind.api import app as app_mod
from matchmind.api.app import create_app
from matchmind.api.session import MatchSession, load_events
from matchmind.dataset import catalog
from matchmind.dataset.dictionary import ENUM_MEANINGS, UNDESCRIBED, _enum_table, render_dictionary
from matchmind.dataset.export import (
    EVENT_COLUMNS,
    TRACKING_COLUMNS,
    TrackingWindow,
    csv_lines,
    export_parts,
    tracking_rows,
)
from matchmind.schema import Event, EventType
from matchmind.simulator.cli import main as sim_main
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import TEAMS

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
DATA = BACKEND / "data" / "matches"
DEMO = DATA / "MM-DEMO-001.jsonl"


def _export(match_id: str, fmt: str, window: TrackingWindow | None = None) -> tuple[str, str, bytes]:
    entry = catalog.find(match_id)
    assert entry is not None
    name, media, chunks = export_parts(
        entry, catalog.load_match(entry), fmt, "dictionary text", Event.model_json_schema(), window
    )
    return name, media, b"".join(chunks)


# --- catalog ------------------------------------------------------------------------------------


def test_catalog_lists_the_bundled_matches_with_seeds():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    entries = catalog.bundled_entries()
    assert [(e.match_id, e.seed, e.score) for e in entries] == [
        (m["match_id"], m["seed"], m["score"]) for m in manifest
    ]
    assert entries[0].scenario == "demo_storyline"
    assert {e.scenario for e in entries[1:]} == {"chance_model"}


@pytest.mark.parametrize(
    "match_id",
    [
        "../matches/MM-DEMO-001",
        "MM-DEMO-001.jsonl",
        "manifest",
        "MM-GEN-00999",
        "MM-GEN-01020",
        "mm-demo-001",
        "",
    ],
)
def test_only_allow_listed_ids_are_found(match_id):
    assert catalog.find(match_id) is None


def test_the_cli_may_use_any_seed():
    assert catalog.find("MM-GEN-00042") is None
    entry = catalog.find("MM-GEN-00042", any_seed=True)
    assert entry is not None and entry.seed == 42 and entry.kind == "seeded"


def test_seeded_matches_are_deterministic_and_the_lakehouse_generator():
    entry = catalog.find("MM-GEN-01003")
    assert entry is not None
    assert catalog.load_match(entry) == generate_match(1003)
    assert _export("MM-GEN-01003", "jsonl") == _export("MM-GEN-01003", "jsonl")


# --- formats ------------------------------------------------------------------------------------


def test_jsonl_export_is_the_bundled_file_byte_for_byte():
    name, media, body = _export("MM-DEMO-001", "jsonl")
    assert name == "MM-DEMO-001.jsonl" and media == "application/x-ndjson"
    assert body == DEMO.read_bytes()


def test_csv_export_has_one_row_per_event_and_the_documented_columns():
    _, _, body = _export("MM-DEMO-001", "csv")
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    events = read_jsonl(DEMO)
    assert list(rows[0]) == [c.name for c in EVENT_COLUMNS]
    assert len(rows) == len(events)
    shot = next(i for i, e in enumerate(events) if e.type == EventType.SHOT)
    assert float(rows[shot]["start_x"]) == events[shot].start.x
    assert int(rows[shot]["freeze_frame_players"]) == len(events[shot].freeze_frame)
    assert json.loads(rows[0]["details"]) == events[0].details
    assert rows[0]["ts"] == "2026-10-24T15:00:00.000000Z"


def test_csv_text_cells_never_start_a_formula():
    out = "".join(csv_lines(EVENT_COLUMNS[:1], [{"event_id": "=HYPERLINK(1)"}, {"event_id": -3.5}]))
    assert out.splitlines()[1] == "'=HYPERLINK(1)"
    assert out.splitlines()[2] == "-3.5"  # numbers stay numbers


def test_zip_export_holds_everything_a_judge_needs():
    name, media, body = _export("MM-DEMO-001", "zip", TrackingWindow(1, 600, 610))
    assert name == "MM-DEMO-001.zip" and media == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(body))
    assert zf.testzip() is None
    names = [n.split("/", 1)[1] for n in zf.namelist()]
    assert names == [
        "README.txt",
        "match.json",
        "events.jsonl",
        "events.csv",
        "rosters.csv",
        "event.schema.json",
        "DATA-DICTIONARY.md",
        "tracking.csv",
    ]
    meta = json.loads(zf.read("MM-DEMO-001/match.json"))
    assert meta["synthetic"] is True and meta["seed"] == 100 and meta["final_score"] == {"home": 2, "away": 3}
    assert meta["pitch"] == {"length_m": 105.0, "width_m": 68.0, "home_attacks": "+x"}
    assert zf.read("MM-DEMO-001/events.jsonl") == DEMO.read_bytes()
    roster = list(csv.DictReader(io.StringIO(zf.read("MM-DEMO-001/rosters.csv").decode())))
    assert {r["name"] for r in roster} == {p.name for t in TEAMS.values() for p in t.players}
    assert "synthetic" in zf.read("MM-DEMO-001/README.txt").decode().lower()


def test_zip_is_deterministic():
    assert _export("MM-SYN-002", "zip") == _export("MM-SYN-002", "zip")


def test_tracking_needs_the_zip_format():
    with pytest.raises(ValueError, match="zip"):
        _export("MM-DEMO-001", "csv", TrackingWindow(1, 0, 10))


# --- tracking sample ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "window",
    [TrackingWindow(1, 600, 630), TrackingWindow(2, 3200, 3260), TrackingWindow(1, 0, 20)],
    ids=["open_play", "after_red_card", "kick_off"],
)
def test_tracking_sample_is_bounded_25hz_and_on_the_pitch(window):
    events = read_jsonl(DEMO)
    rows = list(tracking_rows(events, window))
    frames = sorted({r["clock_s"] for r in rows})
    assert frames and all(window.start_s <= t <= window.end_s for t in frames)
    assert len(frames) >= 0.9 * 25 * (window.end_s - window.start_s)
    assert len(rows) == len(frames) * 23  # the ball and 22 players per frame
    assert all(r["x"] is None or 0 <= r["x"] <= 105 for r in rows)
    assert all(r["y"] is None or 0 <= r["y"] <= 68 for r in rows)
    assert set(rows[0]) == {c.name for c in TRACKING_COLUMNS}
    assert rows == list(tracking_rows(events, window))  # reproducible


def test_sent_off_player_is_not_drawn_after_the_red_card():
    events = read_jsonl(DEMO)
    red = next(e for e in events if e.type == EventType.CARD and e.details.get("card") == "red")
    rows = list(tracking_rows(events, TrackingWindow(red.period, red.clock_s + 60, red.clock_s + 70)))
    assert {r["x"] for r in rows if r["object"] == red.player_id} == {None}


@pytest.mark.parametrize(
    "args, match",
    [((3, 0, 10), "period"), ((1, 50, 40), "before it ends"), ((1, 0, 61), "at most 60")],
)
def test_tracking_window_limits(args, match):
    with pytest.raises(ValueError, match=match):
        TrackingWindow(*args)


# --- data dictionary ------------------------------------------------------------------------------


def test_data_dictionary_doc_is_up_to_date():
    doc = (REPO / "docs" / "DATA-DICTIONARY.md").read_text(encoding="utf-8")
    assert doc == render_dictionary(), (
        "docs/DATA-DICTIONARY.md is stale: run `cd backend && matchmind-sim dictionary`"
    )


def test_bundled_json_schema_matches_the_model():
    on_disk = json.loads((BACKEND / "schema" / "event.schema.json").read_text(encoding="utf-8"))
    assert on_disk == Event.model_json_schema(), "run `matchmind-sim schema` to refresh event.schema.json"


def test_dictionary_covers_every_field_enum_and_match():
    doc = render_dictionary()
    schema = Event.model_json_schema()
    for field in schema["properties"]:
        assert f"| `{field}` |" in doc
    for value in EventType:
        assert f"| `{value.value}` |" in doc
        assert value.value in ENUM_MEANINGS["EventType"], f"add a meaning for {value.value}"
    for entry in catalog.bundled_entries():
        assert f"`{entry.match_id}`" in doc
    assert "105 x 68" in doc and "2700" in doc and UNDESCRIBED not in doc


def test_a_new_enum_value_is_listed_without_breaking_the_generator():
    table = "\n".join(_enum_table("EventType", ["pass", "brand_new_type"]))
    assert "| `brand_new_type` | not described yet |" in table


def test_cli_dictionary_check(tmp_path, capsys):
    out = tmp_path / "DD.md"
    with pytest.raises(SystemExit, match="out of date"):
        sim_main(["dictionary", "--out", str(out), "--check"])
    sim_main(["dictionary", "--out", str(out)])
    sim_main(["dictionary", "--out", str(out), "--check"])
    assert out.read_text(encoding="utf-8") == render_dictionary()


# --- CLI export ---------------------------------------------------------------------------------


def test_cli_export_writes_every_format_and_the_lakehouse(tmp_path):
    sim_main(
        [
            "export",
            "--match",
            "MM-DEMO-001",
            "--seed",
            "7",
            "--format",
            "all",
            "--tracking",
            "1:600-605",
            "--lakehouse",
            "--out",
            str(tmp_path),
        ]
    )
    for name in ("MM-DEMO-001", "MM-GEN-00007"):
        for ext in ("jsonl", "csv", "zip"):
            assert (tmp_path / f"{name}.{ext}").stat().st_size > 1000
    assert (tmp_path / "MM-DEMO-001.jsonl").read_bytes() == DEMO.read_bytes()
    zf = zipfile.ZipFile(tmp_path / "MM-DEMO-001.zip")
    assert "MM-DEMO-001/tracking.csv" in zf.namelist()
    manifest = json.loads((tmp_path / "lakehouse" / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["matches"] == ["MM-DEMO-001", "MM-GEN-00007"]


@pytest.mark.parametrize(
    "argv, match",
    [
        (["export"], "Pick matches"),
        (["export", "--match", "NOPE"], "Unknown match"),
        (["export", "--all", "--format", "csv", "--tracking", "1:0-5"], "needs --format zip"),
        (["export", "--all", "--tracking", "1:0-500"], "at most 60"),
        (["export", "--all", "--tracking", "nonsense"], "PERIOD:FROM-TO"),
    ],
)
def test_cli_export_errors(tmp_path, argv, match):
    with pytest.raises(SystemExit, match=match):
        sim_main([*argv, "--out", str(tmp_path)])


# --- API ------------------------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    app_mod.dataset_export_bytes.cache_clear()
    s = MatchSession(load_events(), engines=FAKE_ENGINES, clock=FakeClock())
    with TestClient(create_app(session=s, tick_interval=None)) as c:
        yield c


def test_api_lists_matches_scenarios_and_seeds(client):
    r = client.get("/api/dataset")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=3600"
    body = r.json()
    assert body["synthetic"] is True and body["formats"] == ["jsonl", "csv", "zip"]
    ids = [m["match_id"] for m in body["matches"]]
    assert ids[:5] == [e.match_id for e in catalog.bundled_entries()]
    assert ids[5] == "MM-GEN-01000" and ids[-1] == "MM-GEN-01019"
    assert all("file" not in m for m in body["matches"])  # no server paths leave the server
    assert body["seeded"] == {"seed_start": 1000, "seed_end": 1019, "match_id": "MM-GEN-<seed, 5 digits>"}


@pytest.mark.parametrize(
    "fmt, media", [("jsonl", "application/x-ndjson"), ("csv", "text/csv"), ("zip", "application/zip")]
)
def test_api_export_streams_a_download(client, fmt, media):
    r = client.get(f"/api/dataset/export?match_id=MM-DEMO-001&format={fmt}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(media)
    assert r.headers["content-disposition"] == f'attachment; filename="MM-DEMO-001.{fmt}"'
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert int(r.headers["content-length"]) == len(r.content)
    if fmt == "jsonl":
        assert r.content == DEMO.read_bytes()


def test_api_export_with_tracking_sample(client):
    r = client.get(
        "/api/dataset/export?match_id=MM-GEN-01000&format=zip&tracking_period=1&tracking_from=300&tracking_to=330"
    )
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    rows = list(csv.DictReader(io.StringIO(zf.read("MM-GEN-01000/tracking.csv").decode())))
    assert rows and all(300 <= float(x["clock_s"]) <= 330 for x in rows)
    assert "## Event fields" in zf.read("MM-GEN-01000/DATA-DICTIONARY.md").decode()


@pytest.mark.parametrize(
    "query, status, detail",
    [
        ("match_id=../../etc/passwd", 400, "match_id"),
        ("match_id=..%2F..%2Fetc", 400, "match_id"),
        ("match_id=MM-DEMO-001%00", 400, "match_id"),
        ("match_id=" + "A" * 40, 400, "match_id"),
        ("match_id=MM-GEN-01020", 404, "do not have that match"),
        ("match_id=MM-DEMO-001&format=parquet", 400, "format"),
        (
            "match_id=MM-DEMO-001&format=csv&tracking_period=1&tracking_from=0&tracking_to=10",
            400,
            "zip format",
        ),
        ("match_id=MM-DEMO-001&tracking_period=1&tracking_from=0", 400, "needs tracking_period"),
        ("match_id=MM-DEMO-001&tracking_period=1&tracking_from=0&tracking_to=100", 400, "at most 60"),
        ("match_id=MM-DEMO-001&tracking_period=3&tracking_from=0&tracking_to=10", 400, "tracking_period"),
        ("match_id=MM-DEMO-001&tracking_period=1&tracking_from=nan&tracking_to=10", 400, "tracking_from"),
    ],
)
def test_api_export_refuses_bad_requests_in_plain_words(client, query, status, detail):
    r = client.get(f"/api/dataset/export?{query}")
    assert r.status_code == status
    assert detail in r.json()["detail"]
    assert r.headers["cache-control"] == "no-store"  # errors are never cached publicly


def test_api_export_is_rate_limited_per_ip(client):
    codes = [client.get("/api/dataset/export?match_id=MM-SYN-001&format=jsonl").status_code for _ in range(8)]
    assert codes[:6] == [200] * 6 and codes[-1] == 429


def test_api_export_refuses_when_every_build_slot_is_busy(monkeypatch):
    monkeypatch.setattr(app_mod, "EXPORT_CONCURRENCY", 0)
    s = MatchSession(load_events(), engines=FAKE_ENGINES, clock=FakeClock())
    with TestClient(create_app(session=s, tick_interval=None)) as c:
        r = c.get("/api/dataset/export?match_id=MM-DEMO-001")
    assert r.status_code == 429 and "busy" in r.json()["detail"]


def test_api_other_routes_stay_no_store(client):
    assert client.get("/api/health").headers["cache-control"] == "no-store"
    r = client.get("/api/source")
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["source"] == "file" and r.json()["complete"] is True


def test_there_is_no_upload_route(client):
    """External feeds come in through the CLI or the env file path, never an HTTP upload."""
    routes = [(getattr(r, "path", ""), getattr(r, "methods", None) or set()) for r in client.app.routes]
    assert not any("upload" in p or "ingest" in p for p, _ in routes)
    assert not any(p.startswith(("/api/dataset", "/api/source")) and "POST" in m for p, m in routes)
    assert client.post("/api/dataset/export?match_id=MM-DEMO-001").status_code == 405
