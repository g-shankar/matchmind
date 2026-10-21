from __future__ import annotations

import sys

import pytest

from conftest import FAKE_ENGINES, FakeClock, make_events
from matchmind.api import session as session_mod
from matchmind.api.session import MatchSession, SessionError, _timeline, build_session, load_events
from matchmind.crew.contracts import ViewerProfile


def play_until(session: MatchSession, clock: FakeClock, seconds: float):
    clock.t += seconds
    return session.advance()


def test_timeline_glues_periods_and_stays_monotonic():
    tl = _timeline(make_events())
    assert tl == sorted(tl)
    # Second half starts where first-half stoppage ended, not back at 2700.
    assert tl[6] == tl[5] == 2760
    assert tl[7] == 2860


def test_bookmarks_cover_whole_match_at_load(session: MatchSession):
    kinds = [(b.kind, b.match_clock, b.period) for b in session.bookmarks]
    assert kinds == [("goal", "01:00", 1), ("goal", "46:40", 2)]
    assert session.bookmarks[0].title == "Goal for NBR"
    assert session.next_index == 0  # nothing played yet


def test_ticks_play_in_order_on_the_match_clock(session: MatchSession, clock: FakeClock):
    ticks = session.advance()  # kick-off events are due at once
    assert [t.event.seq for t in ticks] == [0, 1]
    assert play_until(session, clock, 0.05) == []  # 5 match seconds: pass at 10 s not due
    ticks = play_until(session, clock, 0.05)
    assert [t.event.seq for t in ticks] == [2]
    ticks = play_until(session, clock, 0.5)
    assert [t.event.seq for t in ticks] == [3]
    assert ticks[0].score_home == 1 and session.score == (1, 0)
    assert [b.moment.kind for b in ticks[0].bundles] == ["goal"]


def test_speed_scales_playback(session: MatchSession, clock: FakeClock):
    session.set_speed(1)  # 10 match seconds per real second
    session.advance()
    assert [t.event.seq for t in play_until(session, clock, 1.0)] == [2]
    session.set_speed(60)  # 600 match seconds per real second
    assert [t.event.seq for t in play_until(session, clock, 0.1)] == [3]
    with pytest.raises(SessionError, match="1, 10 or 60"):
        session.set_speed(2)


def test_pause_holds_the_clock(session: MatchSession, clock: FakeClock):
    session.advance()
    session.toggle_pause()
    assert play_until(session, clock, 100) == []
    session.toggle_pause()
    assert [t.event.seq for t in play_until(session, clock, 0.1)] == [2]


def test_full_match_ends_and_stops(session: MatchSession, clock: FakeClock):
    ticks = play_until(session, clock, 100)
    assert len(ticks) == 9 and ticks[-1].is_last
    assert session.ended and not session.is_running
    assert session.score == (1, 1)
    assert session.playback()["ended"] is True
    with pytest.raises(SessionError, match="finished"):
        session.toggle_pause()


def test_seek_replays_stats_without_cards(session: MatchSession, clock: FakeClock):
    calls_before = session.crew.process_calls
    session.seek(2800, period=2)
    assert session.crew.process_calls == calls_before  # no crew work on the way
    assert session.crew.resets == 1
    assert session.score == (1, 0)
    assert session.last_event.seq == 6 and session.period == 2
    # Moments before the seek point are available as recent cards.
    assert [b.moment.moment_id for b in session.recent_bundles()] == ["goal-MM-TEST-001-00003"]
    ticks = session.advance()  # the goal at 2800 is due straight away
    assert [t.event.seq for t in ticks] == [7]
    assert session.score == (1, 1)


def test_seek_infers_the_half_and_lands_on_the_clock(session: MatchSession, clock: FakeClock):
    session.seek(30)
    assert session.last_event.seq == 2 and session.advance() == []
    assert [t.event.seq for t in play_until(session, clock, 0.3)] == [3]
    session.seek(2750, period=1)
    assert session.last_event.seq == 3
    assert [t.event.seq for t in session.advance()] == [4]
    session.seek(2750)  # no half given: 2750 is in the second half
    assert session.last_event.seq == 6


def test_seek_rejects_bad_times(session: MatchSession):
    with pytest.raises(SessionError):
        session.seek(-1)
    with pytest.raises(SessionError, match="after full time"):
        session.seek(9000, period=2)


def test_seek_back_after_full_time_reopens(session: MatchSession, clock: FakeClock):
    play_until(session, clock, 100)
    session.seek(0)
    assert not session.ended and session.score == (0, 0)


def test_reset_goes_back_to_kick_off_and_plays(session: MatchSession, clock: FakeClock):
    play_until(session, clock, 1)
    session.toggle_pause()
    session.reset()
    assert session.is_running and not session.ended
    assert session.next_index == 2 and session.score == (0, 0)
    assert session.recent_bundles() == []


def test_cards_follow_the_profile(session: MatchSession, clock: FakeClock):
    ticks = play_until(session, clock, 1)
    bundles = [b for t in ticks for b in t.bundles]
    cards = session.cards_for(bundles, ViewerProfile(persona="tactical", language="ar", favourite_team="HCY"))
    assert cards[0].persona == "tactical" and cards[0].rtl and cards[0].favourite_side is False


def test_recap_is_cached_per_profile_and_position(session: MatchSession, clock: FakeClock):
    profile = ViewerProfile(persona="fantasy")
    first = session.recap(profile)
    assert session.recap(profile) is first
    assert session.crew.recap_calls == 1
    play_until(session, clock, 1)
    assert session.recap(profile).headline == "1-0"


def test_moment_card_and_unknown_moment(session: MatchSession):
    card = session.card_for_moment("goal-MM-TEST-001-00007", ViewerProfile(language="ja"))
    assert card is not None and card.language == "ja"
    assert session.card_for_moment("nope", ViewerProfile()) is None


def test_players_in_line_up_order(session: MatchSession, clock: FakeClock):
    play_until(session, clock, 100)
    assert [p.player_id for p in session.players()] == ["NBR-9", "HCY-6", "HCY-9"]


def test_demo_match_loads_and_plays_with_fakes(clock: FakeClock):
    events = load_events()
    assert events[0].match_id == "MM-DEMO-001"
    s = MatchSession(events, engines=FAKE_ENGINES, clock=clock)
    assert len(s.bookmarks) == 5  # the five goals in the 2-3 demo match
    play_until(s, clock, 10_000)
    assert s.ended and s.score == (2, 3)


def test_match_file_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MATCHMIND_MATCH_FILE", str(tmp_path / "missing.jsonl"))
    with pytest.raises(RuntimeError, match="not found"):
        load_events()


def test_build_session_says_what_is_missing(monkeypatch):
    def broken():
        raise RuntimeError(
            "The stats engine (matchmind.stats.state.StatsEngine) is not available in this build."
        )

    monkeypatch.setattr(session_mod, "real_engines", broken)
    with pytest.raises(RuntimeError, match="stats engine"):
        build_session()


def test_build_session_with_injected_engines():
    s = build_session(engines=FAKE_ENGINES)
    assert s.match_id == "MM-DEMO-001" and s.auto_eventing is None


def test_paid_ai_stays_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("MATCHMIND_AI_ENABLED", raising=False)
    assert session_mod.ai_enabled() is False and session_mod.live_llm() is None
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "true")
    assert session_mod.ai_enabled() is True
    # No model client in this build: the crew falls back to templates instead of failing.
    monkeypatch.setitem(sys.modules, "matchmind.crew.llm", None)
    assert session_mod.live_llm() is None
