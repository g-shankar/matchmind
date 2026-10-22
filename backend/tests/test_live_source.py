"""Event Hubs consumer mode: the session plays the live stream through the same checks.

No Azure here: a fake consumer delivers the simulator's messages (with the delivery
problems a real stream has: redeliveries, reordering, late joins, other matches)."""

from __future__ import annotations

import random
import threading
import time
from pathlib import Path

import pytest

from conftest import FAKE_ENGINES, FakeClock, FakeStats
from matchmind.api import session as session_mod
from matchmind.api.session import MatchSession, SessionError, build_live_session
from matchmind.ingest.eventhubs import EventHubsSource
from matchmind.ingest.live import LiveFeed
from matchmind.ingest.stream import StreamValidator
from matchmind.schema import Event, EventType
from matchmind.simulator.publisher import read_jsonl

DEMO = Path(__file__).resolve().parents[1] / "data" / "matches" / "MM-DEMO-001.jsonl"
OTHER = DEMO.with_name("MM-SYN-001.jsonl")


@pytest.fixture(scope="module")
def demo() -> list[Event]:
    return read_jsonl(DEMO)


class TickClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _raw(events: list[Event]) -> list[str]:
    return [e.to_json() for e in events]


def _offer_all(v: StreamValidator, raws: list[str]) -> list[Event]:
    out: list[Event] = []
    for raw in raws:
        out += v.offer(raw)
    return out


# --- StreamValidator -----------------------------------------------------------------------------


def test_an_in_order_stream_gives_the_same_events_as_the_file(demo):
    v = StreamValidator()
    assert _offer_all(v, _raw(demo)) == demo
    assert v.state == "ended" and v.stats.accepted == len(demo)


def test_redeliveries_are_dropped_and_counted(demo):
    v = StreamValidator()
    raws = _raw(demo[:50])
    out = _offer_all(v, raws + raws[10:30])  # a reconnect replays 20 messages
    assert out == demo[:50]
    assert v.stats.duplicates == 20


def test_same_seq_with_changed_content_is_refused_and_the_first_stands(demo):
    v = StreamValidator()
    _offer_all(v, _raw(demo[:20]))
    changed = demo[10].model_copy(update={"player_id": "NBR-7" if demo[10].player_id != "NBR-7" else "NBR-8"})
    assert v.offer(changed.to_json()) == []
    assert v.stats.conflicts == 1 and v.stats.duplicates == 0
    # The waiting case too: a changed copy of an event still in the reorder buffer.
    v.offer(demo[25].to_json())
    v.offer(demo[25].model_copy(update={"clock_s": demo[25].clock_s + 1}).to_json())
    assert v.stats.conflicts == 2
    out = _offer_all(v, _raw(demo[20:25]))
    assert out == demo[20:26]


def test_out_of_order_events_are_released_in_seq_order(demo):
    rng = random.Random(4)
    body = demo[1:400]
    shuffled = []
    for i in range(0, len(body), 8):  # shuffle within small windows, as partitions interleave
        chunk = body[i : i + 8]
        rng.shuffle(chunk)
        shuffled += chunk
    v = StreamValidator()
    out = _offer_all(v, _raw([demo[0], *shuffled]))
    assert out == demo[:400]
    assert v.stats.reordered > 0 and v.stats.skipped == 0


def test_same_second_events_keep_their_seq_order(demo):
    i = next(i for i in range(5, len(demo)) if int(demo[i].clock_s) == int(demo[i - 1].clock_s))
    v = StreamValidator()
    _offer_all(v, _raw(demo[: i - 1]))
    out = v.offer(demo[i].to_json()) + v.offer(demo[i - 1].to_json())
    assert [e.seq for e in out] == [i - 1, i]


def test_a_gap_that_never_fills_is_skipped_after_the_timeout(demo):
    clock = TickClock()
    v = StreamValidator(gap_timeout_s=5.0, clock=clock)
    _offer_all(v, _raw(demo[:10]))
    assert v.offer(demo[11].to_json()) == []  # 10 is missing
    clock.t = 3.0
    assert v.flush() == []
    clock.t = 6.0
    assert v.flush() == [demo[11]]
    assert v.stats.skipped == 1
    assert v.offer(demo[10].to_json()) == []  # too late now: refused, never applied out of order
    assert v.stats.rejected == 1


def test_a_full_reorder_buffer_skips_ahead(demo):
    v = StreamValidator(reorder_window=5, gap_timeout_s=1e9)
    _offer_all(v, _raw(demo[:10]))
    out = _offer_all(v, _raw(demo[11:18]))
    assert out and out[0] == demo[11]
    assert v.stats.skipped == 1


def test_joining_late_waits_for_the_next_match_start(demo):
    other = read_jsonl(OTHER)
    v = StreamValidator()
    out = _offer_all(v, _raw(other[500:520]))  # mid-match: no match_start seen
    assert out == [] and v.state == "waiting_for_match_start"
    out = _offer_all(v, _raw(demo[:30]))
    assert out == demo[:30]
    assert v.stats.before_start == 20  # the other match's events, counted once we know


def test_events_that_overtake_their_match_start_are_kept(demo):
    v = StreamValidator()
    out = _offer_all(v, _raw([demo[2], demo[1], demo[0], demo[3]]))
    assert out == demo[:4] and v.stats.before_start == 0


def test_other_matches_on_the_hub_are_ignored(demo):
    other = read_jsonl(OTHER)
    v = StreamValidator(match_id="MM-DEMO-001")
    out = []
    for a, b in zip(_raw(other[:100]), _raw(demo[:100]), strict=True):
        out += v.offer(a) + v.offer(b)
    assert out == demo[:100]
    assert v.stats.before_start == 1 and v.stats.other_match == 99


def test_nothing_is_accepted_after_match_end(demo):
    v = StreamValidator()
    _offer_all(v, _raw(demo))
    assert v.offer(demo[0].to_json()) == []
    assert v.stats.after_end == 1


def test_a_bad_event_is_refused_and_the_stream_goes_on(demo):
    v = StreamValidator()
    _offer_all(v, _raw(demo[:20]))
    bad = demo[20].model_copy(update={"player_id": "NBR-99"})
    assert v.offer(bad.to_json()) == []
    assert v.stats.rejected == 1 and "not in the line-ups" in (v.stats.last_problem or "")
    assert v.offer("{not json") == []
    assert v.offer("x" * (300 * 1024)) == []
    assert v.stats.too_big == 1
    assert _offer_all(v, _raw(demo[21:25])) == demo[21:25]


def test_a_match_start_with_real_names_is_refused(demo):
    lineups = list(demo[0].lineups or [])
    lineups[0] = lineups[0].model_copy(update={"name": "Mohamed Salah"})
    v = StreamValidator()
    assert v.offer(demo[0].model_copy(update={"lineups": lineups}).to_json()) == []
    assert v.state == "waiting_for_match_start" and v.stats.rejected == 1


# --- LiveFeed backpressure -------------------------------------------------------------------------


def test_put_blocks_while_the_session_is_behind(demo):
    feed = LiveFeed(StreamValidator(), max_ready=5)
    for raw in _raw(demo[:5]):
        assert feed.put(raw)
    assert feed.put(demo[5].to_json(), timeout=0.05) is False  # full: the consumer waits
    done = threading.Event()

    def consumer():
        feed.put(demo[5].to_json())
        done.set()

    t = threading.Thread(target=consumer)
    t.start()
    time.sleep(0.05)
    assert not done.is_set()
    assert len(feed.drain(limit=2)) == 2
    t.join(timeout=2)
    assert done.is_set() and feed.status()["backpressure_waits"] >= 2
    assert [e.seq for e in feed.drain()] == [2, 3, 4, 5]


def test_closing_releases_a_blocked_consumer(demo):
    feed = LiveFeed(StreamValidator(), max_ready=1)
    feed.put(demo[0].to_json())
    result = []
    t = threading.Thread(target=lambda: result.append(feed.put(demo[1].to_json())))
    t.start()
    feed.close("stopping")
    t.join(timeout=2)
    assert result == [False] and feed.exhausted is False  # one event still waiting
    feed.drain()
    assert feed.exhausted


# --- fake Event Hubs consumer --------------------------------------------------------------------


class FakeEventData:
    def __init__(self, body: str) -> None:
        self._body = body
        self.partition_key = None

    def body_as_str(self, encoding: str = "UTF-8") -> str:
        return self._body


class FakeConsumer:
    """Delivers messages like EventHubConsumerClient.receive: None ticks included."""

    def __init__(self, messages: list[str], fail_after: int | None = None) -> None:
        self.messages = messages
        self.fail_after = fail_after
        self.kwargs: dict = {}
        self.closed = False

    def receive(self, on_event, **kwargs) -> None:
        self.kwargs = kwargs
        for n, body in enumerate(self.messages):
            if self.closed:
                return
            if self.fail_after is not None and n == self.fail_after:
                raise ConnectionError("link detached")
            on_event(None, None if n % 50 == 7 else FakeEventData(body))
            if n % 50 == 7:
                on_event(None, FakeEventData(body))
        while not self.closed:
            time.sleep(0.01)

    def close(self) -> None:
        self.closed = True


def _messy_stream(demo: list[Event]) -> list[str]:
    """Another match's tail first (we joined late), then the demo with redeliveries and swaps."""
    other = read_jsonl(OTHER)
    msgs = _raw(other[-30:])
    raws = _raw(demo)
    rng = random.Random(9)
    for i in range(0, len(raws), 6):
        chunk = raws[i : i + 6]
        rng.shuffle(chunk)
        msgs += chunk
        if i % 120 == 0:
            msgs += chunk[:3]  # redelivered
    return msgs


def _play_to_end(s: MatchSession, clock: FakeClock, limit_s: float = 60.0) -> None:
    deadline = time.monotonic() + limit_s
    while not s.ended and time.monotonic() < deadline:
        clock.t += 100
        s.advance()
        time.sleep(0.001)


def test_live_session_plays_the_stream_like_the_file(demo, monkeypatch):
    monkeypatch.delenv("MATCHMIND_EVENTHUBS_MATCH_ID", raising=False)
    consumer = FakeConsumer(_messy_stream(demo))
    s = build_live_session(FAKE_ENGINES, consumer_factory=lambda: consumer, wait_s=10)
    assert s is not None and s.is_live and s.match_id == "MM-DEMO-001"
    assert consumer.kwargs["starting_position"] == "@latest"
    clock = FakeClock()
    s._clock = clock
    _play_to_end(s, clock)
    assert s.ended and s.score == (2, 3)
    file_session = MatchSession(demo, engines=FAKE_ENGINES)
    assert [b.moment_id for b in s.bookmarks] == [b.moment_id for b in file_session.bookmarks]
    assert s.events == demo
    status = s.source_status()
    assert status["source"] == "eventhubs" and status["complete"] is True
    stream = status["stream"]
    assert stream["duplicates"] > 0 and stream["reordered"] > 0 and stream["before_start"] == 30
    assert stream["skipped"] == 0 and stream["conflicts"] == 0
    s.consumer.close()


def test_a_live_match_is_not_over_until_match_end(demo):
    feed = LiveFeed(StreamValidator())
    for raw in _raw(demo[:300]):
        feed.put(raw)
    start = feed.wait_for_start(1)
    assert start is not None
    clock = FakeClock()
    s = MatchSession([start], engines=FAKE_ENGINES, clock=clock, live_feed=feed)
    for _ in range(200):
        clock.t += 100
        s.advance()
    assert s.next_index == 300 and not s.ended
    with pytest.raises(SessionError, match="not been played yet"):
        s.seek(5000)
    s.seek(600)  # inside what has arrived: fine
    for raw in _raw(demo[300:]):
        feed.put(raw)
    _play_to_end(s, clock)
    assert s.ended and s.score == (2, 3)
    with pytest.raises(ValueError, match="complete"):
        s.append([demo[-1]])


def test_a_stream_that_stops_ends_the_match_at_the_last_event(demo):
    consumer = FakeConsumer(_raw(demo[:400]), fail_after=399)
    s = build_live_session(FAKE_ENGINES, consumer_factory=lambda: consumer, wait_s=10)
    assert s is not None
    clock = FakeClock()
    s._clock = clock
    _play_to_end(s, clock, limit_s=10)
    assert s.ended and s.next_index == 399
    assert s.source_status()["stream"]["state"] == "stopped"
    assert "stopped" in s.source_status()["stream"]["error"]


def test_no_live_match_means_none(demo):
    consumer = FakeConsumer(_raw(demo[100:110]))  # mid-match only: no match_start
    assert build_live_session(FAKE_ENGINES, consumer_factory=lambda: consumer, wait_s=0.2) is None
    assert consumer.closed


def test_source_switch(monkeypatch):
    monkeypatch.setattr(session_mod, "_auto_eventing", lambda events: None)  # not under test here
    monkeypatch.setenv("MATCHMIND_SOURCE", "kafka")
    with pytest.raises(RuntimeError, match="MATCHMIND_SOURCE"):
        session_mod.build_session(engines=FAKE_ENGINES)
    monkeypatch.delenv("MATCHMIND_SOURCE")
    assert session_mod.build_session(engines=FAKE_ENGINES).source_status()["source"] == "file"


def test_eventhubs_mode_starts_at_once_and_switches_when_a_live_match_starts(monkeypatch):
    """Start-up never waits on the stream (the container's startup probe): the file match
    plays first and the session switches when the live match_start arrives."""
    monkeypatch.setattr(session_mod, "_auto_eventing", lambda events: None)
    monkeypatch.setenv("MATCHMIND_SOURCE", "eventhubs")
    other = read_jsonl(OTHER)
    gate = threading.Event()

    class GatedConsumer(FakeConsumer):
        def receive(self, on_event, **kwargs):
            gate.wait(5)
            super().receive(on_event, **kwargs)

    consumer = GatedConsumer(_raw(other))
    real_start = session_mod.start_live_source
    monkeypatch.setattr(session_mod, "start_live_source", lambda: real_start(lambda: consumer))
    started = time.monotonic()
    s = session_mod.build_session(engines=FAKE_ENGINES)
    assert time.monotonic() - started < 5
    assert s.match_id == "MM-DEMO-001" and not s.is_live
    status = s.source_status()
    assert status["requested"] == "eventhubs" and "Waiting for a live match" in status["note"]
    assert status["stream"]["state"] == "waiting_for_match_start"
    assert s.poll_live() is False
    gate.set()
    deadline = time.monotonic() + 5
    while not s.poll_live():
        assert time.monotonic() < deadline, "never switched to the live match"
        time.sleep(0.01)
    assert s.is_live and s.match_id == "MM-SYN-001" and s.poll_live() is False
    clock = FakeClock()
    s._clock = clock
    _play_to_end(s, clock)
    assert s.ended and len(s.events) == len(other)
    assert s.source_status()["source"] == "eventhubs"
    s.consumer.close()


def test_eventhubs_mode_without_settings_says_what_is_missing(monkeypatch):
    from matchmind.ingest import eventhubs

    monkeypatch.delenv("EVENTHUB_FULLY_QUALIFIED_NAMESPACE", raising=False)
    try:
        import azure.eventhub  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="Azure extras"):
            eventhubs.default_consumer()
    else:  # pragma: no cover - only with the azure extra installed
        with pytest.raises(RuntimeError, match="EVENTHUB_FULLY_QUALIFIED_NAMESPACE"):
            eventhubs.default_consumer()


def test_source_reads_its_starting_position_from_the_env(monkeypatch):
    monkeypatch.setenv("MATCHMIND_EVENTHUBS_START", "-1")
    src = EventHubsSource(LiveFeed(StreamValidator()), consumer_factory=lambda: FakeConsumer([]))
    assert src.starting_position == "-1"


def test_the_live_session_never_sees_labels_stripped_differently(demo):
    """Events from the stream are the same objects the file gives, labels included; the
    stats engine strips them as it does for files (no separate path)."""
    v = StreamValidator()
    out = _offer_all(v, _raw(demo[:200]))
    assert [e.labels for e in out] == [e.labels for e in demo[:200]]
    assert any(e.type == EventType.PERIOD_START for e in out)


# --- security review fixes: typed details, all-or-nothing append, engine scores ----------------


def test_a_bad_score_in_the_stream_is_rejected_and_the_match_stays_whole(demo):
    i = next(i for i, e in enumerate(demo) if e.type == EventType.PERIOD_END)
    bad = demo[i].model_copy(update={"details": {"score_home": "not-a-number", "score_away": 0}})
    consumer = FakeConsumer(_raw([*demo[:i], bad, *demo[i + 1 :]]))
    s = build_live_session(FAKE_ENGINES, consumer_factory=lambda: consumer, wait_s=10)
    assert s is not None
    clock = FakeClock()
    s._clock = clock
    _play_to_end(s, clock)
    assert s.ended
    assert s.source_status()["stream"]["rejected"] == 1
    assert len(s.events) == len(s._event_metrics) == len(demo) - 1
    recent = s.recent_events(10)
    assert len(recent) == 10 and recent[-1][0].type == EventType.MATCH_END
    s.consumer.close()


class ExplodingStats(FakeStats):
    """A stats engine that cannot process one particular event."""

    BAD_SEQ = 250

    def process(self, event):
        if event.seq == self.BAD_SEQ:
            raise ValueError("cannot process this event")
        return super().process(event)


def test_append_is_all_or_nothing_per_event(demo):
    feed = LiveFeed(StreamValidator(), max_ready=len(demo))
    for raw in _raw(demo):
        feed.put(raw)
    start = feed.wait_for_start(1)
    engines = session_mod.Engines(stats=ExplodingStats, crew=FAKE_ENGINES.crew)
    clock = FakeClock()
    s = MatchSession([start], engines=engines, clock=clock, live_feed=feed)
    _play_to_end(s, clock)
    assert s.ended and s.live_dropped == 1
    assert ExplodingStats.BAD_SEQ not in [e.seq for e in s.events]
    assert len(s.events) == len(s._event_metrics) == len(s._tl) == len(demo) - 1
    assert s.score == (2, 3)
    assert len(s.recent_events(20)) == 20
    assert s.source_status()["events_dropped"] == 1
    s.seek(600)  # checkpoints still line up with the events
    assert s.next_index > 0


def test_a_feed_supplied_score_never_becomes_a_fact():
    """Scores on goal and milestone moments come from the stats engine, never the feed."""
    from matchmind.crew.crew import Crew
    from matchmind.crew.llm import TemplateLLM
    from matchmind.crew.translator import OffTranslator
    from matchmind.ingest import validate_events
    from matchmind.stats.state import StatsEngine

    events = read_jsonl(DEMO)
    first_goal = next(i for i, e in enumerate(events) if e.type == EventType.SHOT and e.outcome == "goal")
    half = next(i for i, e in enumerate(events) if e.type == EventType.PERIOD_END)
    lying = {"score_home": 7, "score_away": 9}
    events = [
        e.model_copy(update={"details": {**e.details, **lying}}) if i in (first_goal, half) else e
        for i, e in enumerate(events[: half + 1])
    ]
    events, _ = validate_events(events, require_end=False)  # well-formed numbers: accepted

    def crew(teams):
        return Crew(teams, llm=TemplateLLM(), translator=OffTranslator())

    s = MatchSession(events, engines=session_mod.Engines(stats=StatsEngine, crew=crew), clock=FakeClock())
    facts = [
        b.moment.facts
        for _, b in s._bundle_index
        if "score_home" in b.moment.facts
        and b.moment.source_event_ids[0] in (events[first_goal].event_id, events[half].event_id)
    ]
    assert len(facts) >= 2
    for f in facts:
        assert (f["score_home"], f["score_away"]) != (7, 9)
    assert (facts[-1]["score_home"], facts[-1]["score_away"]) == (2, 0)  # the demo's half-time score
