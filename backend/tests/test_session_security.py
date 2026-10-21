"""Session fixes from the security review: no paid calls at load, recap after a
jump, checkpointed seeks and the bookmark list."""

from __future__ import annotations

import pytest

from conftest import FakeClock, FakeCrew, FakeStats
from matchmind.api import session as session_mod
from matchmind.api.session import Engines, MatchSession, build_session, load_events
from matchmind.crew.contracts import ViewerProfile


def play_until(session: MatchSession, clock: FakeClock, seconds: float):
    clock.t += seconds
    return session.advance()


class CountingLLM:
    """A paid model stand-in that only counts calls."""

    enabled = True
    model = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, system, user, schema, timeout_s):
        from matchmind.crew.llm import LLMError

        self.calls += 1
        raise LLMError("counting only")


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "Yes"])
def test_one_ai_switch_accepts_true_1_yes(monkeypatch, value):
    from matchmind.crew import llm as llm_mod

    monkeypatch.setenv("MATCHMIND_AI_ENABLED", value)
    assert session_mod.ai_enabled is llm_mod.ai_enabled
    assert llm_mod.ai_enabled() and isinstance(llm_mod.make_llm(), llm_mod.AzureOpenAILLM)
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "no")
    assert not llm_mod.ai_enabled()


def test_loading_the_match_never_calls_the_paid_model(monkeypatch):
    from matchmind.crew import crew as crew_mod
    from matchmind.crew import llm as llm_mod

    counting = CountingLLM()
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "true")
    monkeypatch.setattr(llm_mod, "AzureOpenAILLM", lambda *a, **k: counting)
    monkeypatch.setattr(crew_mod, "make_llm", lambda: counting)
    s = build_session()
    assert s.crew.llm is counting  # the live crew is the paid one...
    assert counting.calls == 0  # ...but the whole-match pre-pass ran on templates
    assert s.bookmarks


def real_session(clock: FakeClock) -> MatchSession:
    return MatchSession(load_events(), engines=session_mod.real_engines(), clock=clock)


def test_recap_after_seek_or_reset_matches_a_straight_run(monkeypatch):
    monkeypatch.delenv("MATCHMIND_AI_ENABLED", raising=False)
    profile = ViewerProfile(persona="tactical", language="fr", favourite_team="HCY")
    straight_clock = FakeClock()
    straight = real_session(straight_clock)
    play_until(straight, straight_clock, 10_000)
    expected = straight.recap(profile).model_dump()
    assert expected["key_moments"]

    clock = FakeClock()
    s = real_session(clock)
    play_until(s, clock, 30)
    s.recap(profile)  # cached mid-match; must not leak past the jump
    s.seek(4000, period=2)
    play_until(s, clock, 10_000)
    assert s.ended
    assert s.recap(profile).model_dump() == expected

    s.reset()
    play_until(s, clock, 10_000)
    assert s.recap(profile).model_dump() == expected


def test_seek_clears_the_recap_cache_and_restores_crew_moments(session: MatchSession):
    profile = ViewerProfile()
    session.seek(2800, period=2)
    first = session.recap(profile)
    assert [m.moment_id for m in session.crew.recap_moments] == ["goal-MM-TEST-001-00003"]
    assert [b.moment.moment_id for b in session.crew.restored] == ["goal-MM-TEST-001-00003"]
    session.seek(2800, period=2)
    assert session.recap(profile) is not first  # rebuilt, not served from before the jump
    session.reset()
    assert session.crew.restored == []


def test_seek_replays_from_the_nearest_checkpoint():
    calls = {"n": 0}

    class CountingStats(FakeStats):
        def process(self, event):
            calls["n"] += 1
            return super().process(event)

    s = MatchSession(load_events(), engines=Engines(stats=CountingStats, crew=FakeCrew), clock=FakeClock())
    calls["n"] = 0
    s.seek(5000, period=2)
    assert 0 < calls["n"] <= session_mod.CHECKPOINT_EVERY
    assert s.next_index > 1000


def test_checkpointed_seek_matches_a_full_replay():
    from matchmind.stats.state import StatsEngine

    events = load_events()
    s = MatchSession(events, engines=Engines(stats=StatsEngine, crew=FakeCrew), clock=FakeClock())
    for clock_s, period in ((4000, 2), (600, 1), (4000, 2), (2700, 2)):
        s.seek(clock_s, period=period)
        full = StatsEngine(s.match_id, s.home_id, s.away_id)
        for e in events[: s.next_index]:
            full.process(e)
        assert s.snapshot.model_dump() == full.snapshot().model_dump()
        live = {k: v.model_dump() for k, v in s._live.stats.players().items()}
        assert live == {k: v.model_dump() for k, v in full.players().items()}


def test_bookmarks_leave_out_pitch_tags_and_pass_ratings(monkeypatch):
    monkeypatch.delenv("MATCHMIND_AI_ENABLED", raising=False)
    s = real_session(FakeClock())
    hidden = session_mod.NO_BOOKMARK_KINDS
    assert hidden == {"speed_burst", "rocket_shot", "distance_milestone", "hard_pass"}
    assert {str(b.moment.kind) for _, b in s._bundle_index} & hidden  # the demo has them...
    assert not {b.kind for b in s.bookmarks} & hidden  # ...but they are not bookmarks
    assert any(b.kind == "goal" for b in s.bookmarks)
