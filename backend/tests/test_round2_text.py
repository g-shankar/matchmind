"""First-time-user testing, round 2: the jump list speaks the viewer's language (R2-08)
and a replay's chance values read with the same decimals as its evidence (R2-14)."""

from __future__ import annotations

import pytest

from matchmind.api import view
from matchmind.api.session import MatchSession
from matchmind.crew.contracts import ViewerProfile
from matchmind.crew.fact_checker import check


@pytest.fixture(scope="module")
def demo() -> MatchSession:
    from matchmind.mcp.__main__ import load

    return load(70 * 60, 2)


def test_jump_list_titles_follow_the_viewer_language(demo):
    en = view.snapshot_payload(demo, ViewerProfile(language="en"))["bookmarks"]
    es = view.snapshot_payload(demo, ViewerProfile(language="es"))["bookmarks"]
    assert [b["moment_id"] for b in en] == [b["moment_id"] for b in es]
    assert en[0]["title"] != es[0]["title"]  # "Kick-off: ..." is Spanish now
    big_en = next(b for b in en if b["kind"] == "big_chance")
    big_es = next(b for b in es if b["moment_id"] == big_en["moment_id"])
    assert big_en["title"] != big_es["title"]
    # Each title is the template crew's own Spanish headline for that moment.
    card = demo.card_for_moment(big_en["moment_id"], ViewerProfile(language="es"))
    assert card is not None and big_es["title"] == card.headline


def test_world_languages_keep_the_english_title(demo):
    en = view.snapshot_payload(demo, ViewerProfile(language="en"))["bookmarks"]
    pt = view.snapshot_payload(demo, ViewerProfile(language="pt"))["bookmarks"]
    assert [b["title"] for b in en] == [b["title"] for b in pt]


def test_rest_bookmarks_stay_english(demo):
    from matchmind.api import reads

    class Hub:
        session = demo

    titles = {b["moment_id"]: b["title"] for b in reads.bookmarks(Hub())}  # type: ignore[arg-type]
    assert titles == {b.moment_id: b.title for b in demo.bookmarks}


def _better_card(demo, language="en"):
    b = next(b for b in demo.bookmarks if b.kind == "better_option")
    card = demo.card_for_moment(b.moment_id, ViewerProfile(language=language))
    assert card is not None
    return card


@pytest.mark.parametrize("language", ["en", "es", "fr"])
def test_replay_chance_values_use_two_decimals_like_the_evidence(demo, language):
    card = _better_card(demo, language)
    ev = {e.label_key: e for e in card.evidence}
    assert ev["alt_value"].unit == "xG"  # shown with the other chance values
    alt = ev["alt_value"].value
    sep = "," if language in ("es", "fr") else "."
    two = f"{alt:.2f}".replace(".", sep)
    text = " ".join(filter(None, [card.body, card.why]))
    assert two in text, text
    bundle = demo.bundle(card.moment_id)
    assert bundle is not None
    assert check(text, bundle.moment.facts, language, "text").ok


def test_a_language_change_resends_the_jump_list_in_that_language(demo, tmp_path):
    from fastapi.testclient import TestClient

    from matchmind.api.app import create_app

    app = create_app(
        session=demo,
        tick_interval=None,
        allowed_origins=["http://localhost:3000"],
        static_dir=tmp_path / "none",
    )

    def snapshot(ws) -> dict:
        msg = ws.receive_json()
        while msg["type"] != "INITIAL_SNAPSHOT":
            msg = ws.receive_json()
        return msg["data"]

    with TestClient(app) as client, client.websocket_connect("/ws/match") as ws:
        first = snapshot(ws)["bookmarks"][0]
        ws.send_json({"action": "set_view", "language": "es"})
        again = snapshot(ws)["bookmarks"][0]
    assert first["moment_id"] == again["moment_id"]
    assert first["title"] != again["title"]


@pytest.mark.parametrize("language", ["en", "es", "fr", "ar", "ja"])
def test_catch_up_jump_titles_in_every_language_carry_no_score(demo, language):
    import re

    snap = view.snapshot_payload(demo, ViewerProfile(language=language, spoilers=False))
    assert snap["home_score"] is None
    for b in snap["bookmarks"]:
        assert not re.search(r"\d\s?[-–]\s?\d", b["title"]), (language, b)


def test_a_language_change_in_catch_up_still_sends_a_scrubbed_snapshot(demo, tmp_path):
    from fastapi.testclient import TestClient

    from matchmind.api.app import create_app

    app = create_app(
        session=demo,
        tick_interval=None,
        allowed_origins=["http://localhost:3000"],
        static_dir=tmp_path / "none",
    )
    with TestClient(app) as client, client.websocket_connect("/ws/match?spoilers=0") as ws:
        msg = ws.receive_json()
        while msg["type"] != "INITIAL_SNAPSHOT":
            msg = ws.receive_json()
        before = msg["data"]
        ws.send_json({"action": "set_view", "language": "es"})
        msg = ws.receive_json()
        while msg["type"] != "INITIAL_SNAPSHOT":
            msg = ws.receive_json()
        snap = msg["data"]
    assert before["home_score"] is None and snap["home_score"] is None
    assert snap["profile"]["spoilers"] is False and snap["profile"]["language"] == "es"
    assert {b["moment_id"] for b in snap["bookmarks"]} == {b["moment_id"] for b in before["bookmarks"]}
    assert all(e.get("seq") is None for e in snap["recent_events"])
