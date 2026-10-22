"""Lakehouse export: schema, row counts, determinism, CSV fallback, Fabric assets."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

from matchmind.analytics import sources, writers
from matchmind.analytics.build import build_tables, process_match
from matchmind.analytics.cli import main as cli_main
from matchmind.analytics.labels import split_for
from matchmind.analytics.schema import ALL_TABLES, BY_NAME, EVENTS, STAR_TABLES
from matchmind.schema import Event, EventType, Outcome, Point
from matchmind.simulator.publisher import read_jsonl, write_jsonl
from matchmind.stats.better_option import analyse_shot, shot_alternative
from matchmind.stats.metrics import to_attacking
from matchmind.stats.state import StatsEngine

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
DATA = BACKEND / "data" / "matches"
FABRIC = REPO / "analytics" / "fabric"
SEED = 1234


@pytest.fixture(scope="module")
def bundled_events() -> list[list[Event]]:
    return sources.load_matches([DATA])


@pytest.fixture(scope="module")
def bundled(bundled_events) -> dict[str, list[dict]]:
    return build_tables(bundled_events)


@pytest.fixture(scope="module")
def one_match() -> list[Event]:
    return sources.generate_match(SEED)


# ------------------------------------------------------------------ schema


def test_table_definitions_are_consistent():
    assert [t.name for t in ALL_TABLES] == list(BY_NAME)
    for t in ALL_TABLES:
        for ref in t.references.values():
            table, col = ref.split(".")
            assert col in BY_NAME[table].names, f"{t.name} references {ref}"
        assert set(t.references) <= set(t.names)


def test_rows_match_the_schema_exactly(bundled):
    assert set(bundled) == set(BY_NAME)
    for name, rows in bundled.items():
        cols = set(BY_NAME[name].names)
        assert all(set(row) == cols for row in rows), name


def test_keys_are_unique(bundled):
    for table in ALL_TABLES:
        keys = [tuple(r[k] for k in table.key) for r in bundled[table.name]]
        assert len(keys) == len(set(keys)), f"{table.name} has duplicate keys"


def test_foreign_keys_resolve(bundled):
    for table in ALL_TABLES:
        for col, ref in table.references.items():
            ref_table, ref_col = ref.split(".")
            known = {r[ref_col] for r in bundled[ref_table]}
            used = {r[col] for r in bundled[table.name] if r.get(col) is not None}
            assert used <= known, f"{table.name}.{col} has values missing from {ref}"


# -------------------------------------------------------------- row counts


def test_row_counts_follow_the_source(bundled, bundled_events):
    assert len(bundled["matches"]) == len(bundled_events) == 5
    assert len(bundled["events"]) == sum(len(m) for m in bundled_events)
    assert len(bundled["teams"]) == 2 and len(bundled["players"]) == 22
    assert len(bundled["team_match"]) == 2 * len(bundled_events)
    assert len(bundled["player_match"]) == 22 * len(bundled_events)
    assert len(bundled["moments"]) == sum(r["moments"] for r in bundled["matches"])
    assert len(bundled["moment_facts"]) == sum(len(json.loads(r["facts_json"])) for r in bundled["moments"])
    flagged = [r for r in bundled["events"] if r["has_better_option"] or r["has_unfound_run"]]
    assert len(bundled["better_options"]) == len(flagged)
    manifest = json.loads((DATA / "manifest.json").read_text())
    counts = {m["match_id"]: m["events"] for m in manifest}
    assert {r["match_id"]: r["events"] for r in bundled["matches"]} == counts


def test_aggregates_agree_with_the_events(bundled, bundled_events):
    by_match = {r["match_id"]: r for r in bundled["matches"]}
    # A goal a VAR review overturned is still a shot but not a goal (docs/METRICS.md).
    ruled_out = {
        e.reviewed_event_id
        for m in bundled_events
        for e in m
        if e.type == EventType.VAR_REVIEW and e.outcome == Outcome.OVERTURNED
    }
    assert ruled_out, "the demo match has a goal ruled out by VAR"
    for tm in bundled["team_match"]:
        match = by_match[tm["match_id"]]
        side = "home" if tm["is_home"] else "away"
        assert tm["goals"] == match[f"score_{side}"]
        shots = [
            r for r in bundled["events"] if r["match_id"] == tm["match_id"] and r["team_id"] == tm["team_id"]
        ]
        assert tm["shots"] == sum(r["type"] == "shot" for r in shots)
        goals = sum(
            r["type"] == "shot" and r["outcome"] == "goal" and r["event_id"] not in ruled_out for r in shots
        )
        assert tm["goals"] == goals
        cards = [r for r in shots if r["type"] == "card"]
        assert tm["yellow_cards"] + tm["red_cards"] == len(cards)
        assert tm["points"] == (
            3 if tm["goals"] > tm["goals_against"] else 1 if tm["goals"] == tm["goals_against"] else 0
        )
    players = {(r["match_id"], r["player_id"]): r for r in bundled["player_match"]}
    for match in bundled["matches"]:
        total = sum(r["goals"] for (m, _), r in players.items() if m == match["match_id"])
        assert total == match["score_home"] + match["score_away"]


def test_possession_adds_up(bundled):
    totals: dict[str, float] = {}
    for tm in bundled["team_match"]:
        totals[tm["match_id"]] = totals.get(tm["match_id"], 0.0) + tm["possession_pct"]
    assert all(abs(v - 100.0) < 0.2 for v in totals.values())


def test_enriched_numbers_come_from_the_stats_engine(one_match):
    rows = process_match(one_match).tables["events"]
    final = StatsEngine.replay(one_match).snapshot()
    assert rows[-1]["xg_home"] == final.xg_home and rows[-1]["xg_away"] == final.xg_away
    assert (rows[-1]["score_home"], rows[-1]["score_away"]) == (final.score_home, final.score_away)
    shots = [r for r in rows if r["type"] == "shot"]
    assert shots and all(r["xg"] is not None and 0 < r["xg"] <= 0.95 for r in shots)
    assert all(r["xg"] is None for r in rows if r["type"] != "shot")


def test_ground_truth_labels_stay_out_of_the_stats(one_match):
    """The stats engine ignores labels, so stripping them cannot change any number."""
    stripped = [e.model_copy(update={"labels": []}) for e in one_match]
    with_labels = process_match(one_match).tables
    without = process_match(stripped).tables
    for name in ("player_match", "team_match", "moments", "better_options"):
        assert with_labels[name] == without[name], name
    drop = lambda row: {k: v for k, v in row.items() if k != "scripted"}  # noqa: E731 (only column read from labels)
    assert [drop(r) for r in with_labels["matches"]] == [drop(r) for r in without["matches"]]
    assert [r["xg"] for r in with_labels["events"]] == [r["xg"] for r in without["events"]]


# ------------------------------------------------------------- determinism


def _read_tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_same_seed_gives_identical_csv_bytes(tmp_path):
    for name in ("a", "b"):
        tables = build_tables([sources.generate_match(SEED)])
        writers.write_tables(tables, tmp_path / name, "csv", matches=[tables["matches"][0]["match_id"]])
    a, b = _read_tree(tmp_path / "a"), _read_tree(tmp_path / "b")
    assert a.keys() == b.keys() and a == b
    assert any(k.endswith("part-0.csv") for k in a)


def test_different_seed_changes_the_data(tmp_path, one_match):
    other = build_tables([sources.generate_match(SEED + 1)])
    assert other["events"] != process_match(one_match).tables["events"]


def test_generated_match_does_not_depend_on_how_many_are_requested():
    one = sources.load_matches(seeds=1, seed_start=500)
    three = sources.load_matches(seeds=3, seed_start=500)
    assert [e.to_json() for e in one[0]] == [e.to_json() for e in three[0]]
    assert [m[0].match_id for m in three] == sorted(m[0].match_id for m in three)


def test_generated_matches_carry_the_requested_decision_beats(one_match):
    labels = {label for e in one_match for label in e.labels}
    assert {"scripted:missed_option", "scripted:run_not_found"} <= labels
    rows = process_match(one_match).tables
    assert rows["matches"][0]["scripted"] is True
    assert len(rows["better_options"]) >= 3  # every beat is picked up by the stats engine, not by the script
    plain = sources.generate_match(SEED, beats=0)
    assert not any(label.startswith("scripted:") for e in plain for label in e.labels)
    assert process_match(plain).tables["matches"][0]["scripted"] is False


def test_beat_scripts_are_valid_for_any_seed():
    for seed in range(300):
        script = sources.generated_script(seed)
        assert len(script.beats) == sources.DEFAULT_BEATS
        assert [b.at_s for b in script.beats] == sorted(b.at_s for b in script.beats)
        assert all(480 <= b.at_s <= 5200 and not 2640 < b.at_s < 2790 for b in script.beats)
    with pytest.raises(ValueError, match="beats"):
        sources.load_matches(seeds=1, beats=9)


def test_input_order_does_not_change_the_output(bundled_events):
    files = sorted(DATA.glob("*.jsonl"))
    forward = sources.load_matches(files)
    backward = sources.load_matches(reversed(files))
    assert [m[0].match_id for m in forward] == [m[0].match_id for m in backward]


def test_parquet_is_deterministic_and_matches_csv(tmp_path, one_match):
    pytest.importorskip("pyarrow")
    tables = build_tables([one_match])
    for fmt in ("parquet", "parquet2", "csv"):
        writers.write_tables(tables, tmp_path / fmt, "csv" if fmt == "csv" else "parquet")
    assert _read_tree(tmp_path / "parquet") == _read_tree(tmp_path / "parquet2")
    for name in tables:
        assert writers.read_table(tmp_path / "parquet", name) == writers.read_table(tmp_path / "csv", name), (
            name
        )


# ------------------------------------------------------------- file layout


def test_parquet_layout_and_types(tmp_path, one_match):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    tables = build_tables([one_match])
    manifest = writers.write_tables(tables, tmp_path, "parquet", matches=["x"])
    assert manifest["format"] == "parquet" and set(manifest["tables"]) == set(BY_NAME)
    for table in ALL_TABLES:
        folder = tmp_path / "Tables" / table.name
        assert sorted(p.name for p in folder.iterdir()) == ["_schema.json", "part-0.parquet"]
        doc = json.loads((folder / "_schema.json").read_text())
        assert doc["row_count"] == len(tables[table.name]) == manifest["tables"][table.name]["rows"]
        assert [c["name"] for c in doc["columns"]] == table.names
        schema = pq.read_schema(folder / "part-0.parquet")
        assert schema.names == table.names
    schema = pq.read_schema(tmp_path / "Tables" / "events" / "part-0.parquet")
    assert schema.field("ts").type == pa.timestamp("us", tz="UTC")
    assert schema.field("seq").type == pa.int64() and schema.field("xg").type == pa.float64()
    assert schema.field("sprint").type == pa.bool_()


def test_csv_fallback_without_pyarrow(tmp_path, one_match, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyarrow", None)  # makes `import pyarrow` raise ImportError
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    assert writers.have_pyarrow() is False
    assert writers.resolve_format("auto") == "csv"
    with pytest.raises(RuntimeError, match="pyarrow"):
        writers.resolve_format("parquet")
    tables = build_tables([one_match])
    manifest = writers.write_tables(tables, tmp_path, "auto")
    assert manifest["format"] == "csv"
    for name, rows in tables.items():
        folder = tmp_path / "Tables" / name
        assert sorted(p.name for p in folder.iterdir()) == ["_schema.json", "part-0.csv"]
        assert writers.read_table(tmp_path, name) == [
            {c: r.get(c) for c in BY_NAME[name].names} for r in rows
        ], name
    text = (tmp_path / "Tables" / "events" / "part-0.csv").read_text(encoding="utf-8")
    assert "\r" not in text and text.splitlines()[0] == ",".join(EVENTS.names)
    assert "true" in text and re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", text)


def test_re_export_in_another_format_leaves_no_stale_part_file(tmp_path, one_match):
    pytest.importorskip("pyarrow")
    tables = build_tables([one_match])
    writers.write_tables(tables, tmp_path, "parquet")
    writers.write_tables(tables, tmp_path, "csv")
    for name in tables:
        files = sorted(p.name for p in (tmp_path / "Tables" / name).iterdir())
        assert files == ["_schema.json", "part-0.csv"], name
    again = writers.write_tables(tables, tmp_path, "csv")
    assert again["tables"]["events"]["rows"] == len(tables["events"])  # overwritten, not appended


def test_empty_table_still_gets_a_file(tmp_path):
    writers.write_tables({"better_options": []}, tmp_path, "csv")
    rows = writers.read_table(tmp_path, "better_options")
    assert rows == []
    assert json.loads((tmp_path / "Tables" / "better_options" / "_schema.json").read_text())["row_count"] == 0


# ------------------------------------------------------------------ labels


def test_decision_labels(bundled):
    rows = bundled["decision_labels"]
    events = bundled["events"]
    assert len(rows) == sum(r["type"] in ("shot", "pass") for r in events)
    assert {r["decision"] for r in rows} == {"shot", "pass"}
    shots = [r for r in rows if r["decision"] == "shot"]
    flagged = {r["event_id"] for r in events if r["has_better_option"]}
    assert {r["event_id"] for r in shots if r["label_better_option"]} == flagged
    assert all(r["label_xg_gain"] >= 0 for r in shots)
    assert all(r["label_xg_gain"] > 0 for r in shots if r["label_better_option"])
    goals = {r["event_id"] for r in events if r["type"] == "shot" and r["outcome"] == "goal"}
    assert {r["event_id"] for r in shots if r["label_goal"]} == goals
    passes = [r for r in rows if r["decision"] == "pass"]
    assert all(r["label_completed"] is not None for r in passes)
    assert all(r["label_next_shot_xg"] > 0 for r in passes if r["label_leads_to_shot"])
    assert not any("truth" in c for c in BY_NAME["decision_labels"].names)


def test_split_is_per_match_and_covers_the_bundled_set(bundled):
    per_match: dict[str, set[str]] = {}
    for r in bundled["decision_labels"]:
        per_match.setdefault(r["match_id"], set()).add(r["split"])
    assert all(len(v) == 1 for v in per_match.values())
    assert {next(iter(v)) for v in per_match.values()} == {"train", "val", "test"}
    assert split_for("MM-SYN-004") == split_for("MM-SYN-004")


def test_pass_that_leads_to_a_shot_is_labelled(one_match):
    rows = process_match(one_match).tables["decision_labels"]
    leads = [r for r in rows if r["label_leads_to_shot"]]
    assert leads, "a full match has passes that lead to shots"
    shots = {r["event_id"]: r for r in rows if r["decision"] == "shot"}
    assert len(shots) > 0
    by_id = {e.event_id: e for e in one_match}
    for r in leads[:20]:
        e = by_id[r["event_id"]]
        later = [
            s
            for s in one_match
            if s.type == EventType.SHOT
            and s.team == e.team
            and s.possession_id == e.possession_id
            and s.period == e.period
            and 0 <= s.clock_s - e.clock_s <= 15
        ]
        assert later


def test_shot_alternative_agrees_with_the_better_option_trigger(bundled_events):
    checked = 0
    for events in bundled_events:
        engine = StatsEngine.replay(events)
        for e in events:
            if e.type != EventType.SHOT:
                continue
            bo = analyse_shot(e, engine.home_id)
            alt = shot_alternative(e, engine.home_id)
            if bo is not None:
                assert alt is not None
                assert (alt.teammate_id, alt.alt_value) == (bo.teammate_id, bo.alt_value)
                checked += 1
    assert checked >= 3


# ------------------------------------------------------------------- CLI


def test_cli_export_from_files_and_seeds(tmp_path, one_match, capsys):
    src = tmp_path / "in"
    write_jsonl(one_match, src / "m.jsonl")
    out = tmp_path / "out"
    cli_main(
        [
            "export",
            "--out",
            str(out),
            "--input",
            str(src),
            "--seeds",
            "1",
            "--seed-start",
            "7",
            "--format",
            "csv",
        ]
    )
    manifest = json.loads((out / "_manifest.json").read_text())
    assert manifest["matches"] == sorted([one_match[0].match_id, "MM-GEN-00007"])
    assert manifest["tables"]["matches"]["rows"] == 2
    assert "decision_labels" not in manifest["tables"]
    cli_main(["export", "--out", str(out), "--input", str(src), "--format", "csv", "--with-labels"])
    assert "decision_labels" in json.loads((out / "_manifest.json").read_text())["tables"]
    assert "rows" in capsys.readouterr().err


def test_cli_labels_and_enrich(tmp_path, one_match):
    src = tmp_path / "m.jsonl"
    write_jsonl(one_match, src)
    cli_main(["labels", "--out", str(tmp_path / "lab"), "--input", str(src), "--format", "csv"])
    assert (tmp_path / "lab" / "Tables" / "decision_labels" / "part-0.csv").exists()
    assert not (tmp_path / "lab" / "Tables" / "events").exists()
    cli_main(["enrich", "--out", str(tmp_path / "e.jsonl"), "--input", str(src)])
    lines = (tmp_path / "e.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(one_match)
    first = json.loads(lines[0])
    assert set(first) <= set(EVENTS.names) and first["ts"].endswith("Z")
    assert "labels" not in first


def test_cli_refuses_a_repeated_match_instead_of_double_counting(tmp_path, one_match):
    write_jsonl(one_match, tmp_path / "a.jsonl")
    write_jsonl(one_match, tmp_path / "b.jsonl")
    with pytest.raises(SystemExit, match="twice"):
        cli_main(["export", "--out", str(tmp_path / "o"), "--input", str(tmp_path), "--format", "csv"])


def test_cli_errors_are_plain(tmp_path):
    with pytest.raises(SystemExit, match="does not exist"):
        cli_main(
            ["export", "--out", str(tmp_path / "o"), "--input", str(tmp_path / "nope"), "--format", "csv"]
        )
    with pytest.raises(SystemExit, match="No matches"):
        cli_main(["export", "--out", str(tmp_path / "o"), "--input", str(tmp_path), "--format", "csv"])


def test_match_without_a_start_event_is_refused():
    e = Event(
        event_id="X-1",
        match_id="X",
        seq=0,
        ts="2026-10-24T15:00:00Z",
        period=1,
        clock_s=1.0,
        match_clock="00:01",
        type=EventType.PASS,
        team="NBR",
        player_id="NBR-9",
        start=Point(x=1, y=1),
    )
    with pytest.raises(ValueError, match="match_start"):
        process_match([e])


def test_lakehouse_flips_the_away_team_to_attack_the_same_way(bundled):
    away = next(r for r in bundled["events"] if r["is_home"] is False and r["start_x"] is not None)
    assert away["att_start_x"] == round(to_attacking((away["start_x"], away["start_y"]), "HCY", "NBR")[0], 2)


# ------------------------------------------------------- Fabric assets


def _kql_blocks() -> str:
    return (FABRIC / "eventhouse.kql").read_text(encoding="utf-8")


def _kql_table(text: str, table: str) -> dict[str, str]:
    m = re.search(rf"\.create-merge table {table} \((.*?)\n\)", text, re.S)
    assert m, f"no .create-merge for {table}"
    cols = dict(re.findall(r"^\s*(\w+):\s*(\w+),?$", m.group(1), re.M))
    assert cols
    return cols


def _kql_mapping(text: str, table: str) -> list[dict]:
    m = re.search(
        rf'\.create-or-alter table {table} ingestion json mapping "\w+"\n```\n(.*?)\n```', text, re.S
    )
    assert m, f"no mapping for {table}"
    return json.loads(m.group(1))


def test_kql_raw_mapping_matches_the_event_schema():
    text = _kql_blocks()
    cols, mapping = _kql_table(text, "MatchEvents"), _kql_mapping(text, "MatchEvents")
    assert {e["column"]: e["datatype"] for e in mapping} == cols
    assert len({e["column"] for e in mapping}) == len(mapping)
    fields = Event.model_fields
    roots: dict[str, set[str]] = {}
    for entry in mapping:
        path = entry["Properties"]["Path"]
        assert path.startswith("$.")
        root, *rest = path[2:].split(".")
        assert root in fields, f"{path} is not a field of the event schema"
        roots.setdefault(root, set()).update(rest)
    # every field is ingested, except the simulator's ground-truth labels
    assert set(fields) - set(roots) == {"labels"}
    # nested paths are the Point fields
    assert roots["start"] == roots["end"] == set(Point.model_fields)
    # column types follow the pydantic field types
    for entry in mapping:
        root, *rest = entry["Properties"]["Path"][2:].split(".")
        ann = str((Point.model_fields[rest[0]] if rest else fields[root]).annotation)
        if "dict" in ann or "list" in ann:
            want = "dynamic"
        elif "datetime" in ann:
            want = "datetime"
        elif "bool" in ann:
            want = "bool"
        elif "float" in ann:
            want = "real"
        elif "int" in ann:
            want = "long"
        else:
            want = "string"
        assert entry["datatype"] == want, (entry, ann)


def test_kql_enriched_table_matches_the_events_table():
    text = _kql_blocks()
    cols, mapping = _kql_table(text, "MatchEventsEnriched"), _kql_mapping(text, "MatchEventsEnriched")
    kql_type = {
        "string": "string",
        "int64": "long",
        "float64": "real",
        "bool": "bool",
        "timestamp": "datetime",
    }
    assert cols == {c.name: kql_type[c.dtype] for c in EVENTS.cols}
    assert list(cols) == EVENTS.names
    assert [(e["column"], e["Properties"]["Path"]) for e in mapping] == [(c, f"$.{c}") for c in EVENTS.names]


KQL_WORDS = {
    "let", "toscalar", "top", "by", "project", "where", "summarize", "arg_max", "round", "avg", "max",
    "count", "countif", "order", "asc", "desc", "render", "linechart", "with", "title", "and", "true",
    "false", "matchid",
}  # fmt: skip


def test_kql_queries_only_use_known_columns():
    text = _kql_blocks()
    queries = text.split("2. real-time queries", 1)[1]
    blocks = [b for b in queries.split("\n\n") if "let matchId" in b]
    assert len(blocks) == 5
    for block in blocks:
        code = re.sub(r'"[^"]*"', "", re.sub(r"//.*", "", block))
        table = (
            "MatchEventsEnriched"
            if "from_enriched" in code or "MatchEventsEnriched" in code
            else "MatchEvents"
        )
        known = (
            set(EVENTS.names)
            if table == "MatchEventsEnriched"
            else {e["column"] for e in _kql_mapping(text, "MatchEvents")}
        )
        aliases = set(re.findall(r"\b(\w+)\s*=(?!=)", code))
        idents = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", code))
        unknown = idents - known - aliases - KQL_WORDS
        assert not unknown, f"{table} query uses unknown names {sorted(unknown)}"
    assert text.count("render ") == 1
    assert "Not connected yet" in text


def test_notebook_is_valid_and_consistent():
    nb = json.loads((FABRIC / "pitchpulse_lakehouse.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and nb["cells"]
    ids = [c["id"] for c in nb["cells"]]
    assert len(set(ids)) == len(ids)
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code and all(c["outputs"] == [] and c["execution_count"] is None for c in code)
    for c in code:
        ast.parse("".join(c["source"]))  # every code cell is valid Python
    source = "\n".join("".join(c["source"]) for c in nb["cells"])
    tables = {m for m in re.findall(r"\bpp_([a-z_]+)\b", source) if not m.startswith("vw_")}
    assert tables <= {t.name for t in STAR_TABLES}
    assert "Status: not run yet" in "".join(nb["cells"][0]["source"]).replace("**", "")


# ------------------------------------------------------------------- docs


def test_docs_row_counts_are_the_real_ones(bundled):
    text = (REPO / "docs" / "ANALYTICS.md").read_text(encoding="utf-8")
    found = {
        name: int(rows.replace(",", ""))
        for name, rows in re.findall(r"^\|\s*`?(\w+)`?\s*\|\s*(?:fact|dim)\s*\|\s*([\d,]+)\s*\|", text, re.M)
    }
    assert found == {name: len(rows) for name, rows in bundled.items() if name != "decision_labels"} | {
        "decision_labels": len(bundled["decision_labels"])
    }


def test_read_jsonl_roundtrip_is_what_the_export_reads(tmp_path, one_match):
    write_jsonl(one_match, tmp_path / "m.jsonl")
    again = read_jsonl(tmp_path / "m.jsonl")
    assert process_match(again).tables["matches"] == process_match(one_match).tables["matches"]
