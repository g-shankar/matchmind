"""World languages through Azure AI Translator: request shape, protection of
numbers and names, the fact-checker on translated text, off mode, spend rails
and the cache. No network: every request goes to an injected httpx transport."""

from __future__ import annotations

import json
import re
import threading
import time
from collections import namedtuple

import httpx
import pytest

from matchmind.crew.breaker import BREAKER_OPEN_S
from matchmind.crew.contracts import PERSONAS, STUDIO_LANGUAGES, WORLD_LANGUAGES, MomentKind, ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.fact_checker import extract_numbers
from matchmind.crew.languages import language_list
from matchmind.crew.llm import TemplateLLM
from matchmind.crew.producer import ViewerState
from matchmind.crew.translator import (
    TOKEN_SCOPE,
    AzureTranslator,
    CharacterBudget,
    OffTranslator,
    ProtectionError,
    TranslationCache,
    TranslationService,
    TranslatorError,
    make_translator,
    protect,
    protection_pattern,
    translator_enabled,
    unprotect,
)
from matchmind.schema import EventType
from matchmind.simulator.teams import TEAMS
from matchmind.stats.models import EventMetrics
from test_crew import bundles_from, ev, moments, players, snap, window  # noqa: F401

ENDPOINT = "https://trl-pitchpulse-test.cognitiveservices.azure.com/"
Token = namedtuple("Token", "token expires_on")
SPAN = re.compile(r'(<span class="notranslate">.*?</span>)')


class FakeCredential:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    def get_token(self, *scopes: str) -> Token:
        self.scopes.extend(scopes)
        return Token(f"tok-{len(self.scopes)}", time.time() + 3600)


def fake_translate(text: str, to: str) -> str:
    """A stand-in for Translator: changes the words, never the protected spans."""
    parts = SPAN.split(text)
    return "".join(p if SPAN.fullmatch(p) else (f"«{to}» {p}" if p.strip() else p) for p in parts)


class FakeAzure:
    """Records every request and answers like Translator v3."""

    def __init__(self, tamper=None, status: int = 200, delay: float = 0.0, body: bytes | None = None):
        self.requests: list[httpx.Request] = []
        self.tamper = tamper
        self.status = status
        self.delay = delay
        self.body = body
        self._lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.requests.append(request)
        if self.delay:
            time.sleep(self.delay)
        if self.status != 200:
            return httpx.Response(
                self.status, content=self.body or b'{"error":{"message":"provider secret"}}'
            )
        to = request.url.params["to"]
        items = json.loads(request.content)
        out = []
        for item in items:
            text = fake_translate(item["Text"], to)
            if self.tamper:
                text = self.tamper(text)
            out.append({"translations": [{"text": text, "to": to}]})
        return httpx.Response(200, json=out)


def azure(fake: FakeAzure, credential: FakeCredential | None = None) -> AzureTranslator:
    return AzureTranslator(
        endpoint=ENDPOINT,
        region="uksouth",
        credential=credential or FakeCredential(),
        transport=httpx.MockTransport(fake),
    )


def service(fake: FakeAzure, **kw) -> TranslationService:
    kw.setdefault("budget", CharacterBudget(total=1_000_000, per_minute=1_000_000))
    kw.setdefault("cache", TranslationCache())
    return TranslationService(azure(fake), **kw)


NAMES = ("Adam Kerrigan", "Kerrigan", "Northbridge FC")


# ------------------------------------------------------------------ request shape


def test_one_batched_request_with_bearer_token_and_no_keys():
    fake, cred = FakeAzure(), FakeCredential()
    svc = TranslationService(
        azure(fake, cred), budget=CharacterBudget(10_000, 10_000), cache=TranslationCache()
    )
    out = svc.translate(["Kerrigan scores for Northbridge FC", "Chance quality 0.42 xG", ""], "de", NAMES)
    assert out.texts is not None and out.reason is None
    assert len(fake.requests) == 1  # every string of the card in ONE request
    req = fake.requests[0]
    assert req.method == "POST"
    assert req.url.host == "trl-pitchpulse-test.cognitiveservices.azure.com"
    assert req.url.path == "/translator/text/v3.0/translate"
    assert dict(req.url.params) == {"api-version": "3.0", "from": "en", "to": "de", "textType": "html"}
    assert req.headers["authorization"] == "Bearer tok-1"
    assert req.headers["content-type"].startswith("application/json")
    assert "x-clienttraceid" in req.headers
    for header in ("ocp-apim-subscription-key", "ocp-apim-resourceid", "ocp-apim-subscription-region"):
        assert header not in req.headers  # keyless, custom subdomain: the token is enough
    assert cred.scopes == [TOKEN_SCOPE]
    body = json.loads(req.content)
    assert len(body) == 2  # the empty string is not sent (or billed)
    assert '<span class="notranslate">Kerrigan</span>' in body[0]["Text"]
    assert '<span class="notranslate">Northbridge FC</span>' in body[0]["Text"]
    assert '<span class="notranslate">0.42</span>' in body[1]["Text"]
    assert '<span class="notranslate">xG</span>' in body[1]["Text"]
    assert out.texts[2] == ""
    assert "Kerrigan" in out.texts[0] and "0.42" in out.texts[1] and "<" not in out.texts[1]


def test_token_is_reused_until_close_to_expiry():
    fake, cred = FakeAzure(), FakeCredential()
    svc = TranslationService(
        azure(fake, cred), budget=CharacterBudget(10_000, 10_000), cache=TranslationCache()
    )
    svc.translate(["One"], "pt")
    svc.translate(["Two"], "pt")
    assert len(fake.requests) == 2 and len(cred.scopes) == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.cognitive.microsofttranslator.com/",  # global endpoint needs keys or resource ids
        "http://trl-x.cognitiveservices.azure.com/",
        "https://trl-x.cognitiveservices.azure.com.evil.example/",
        "",
    ],
)
def test_only_a_custom_subdomain_endpoint_is_used(endpoint):
    t = AzureTranslator(
        endpoint=endpoint, credential=FakeCredential(), transport=httpx.MockTransport(FakeAzure())
    )
    with pytest.raises(TranslatorError, match="endpoint_not_configured"):
        t.translate(["Hi"], "de", 1.0)


def test_provider_error_text_never_leaks():
    fake = FakeAzure(status=401, body=b"provider secret: key abc123")
    svc = service(fake)
    out = svc.translate(["Goal"], "ko")
    assert out.texts is None and out.reason == "translator_error"
    with pytest.raises(TranslatorError) as exc:
        azure(fake).translate(["Goal"], "ko", 1.0)
    assert str(exc.value) == "http_401"
    assert "secret" not in svc.status().model_dump_json()


def test_malformed_answer_is_an_error():
    t = AzureTranslator(
        endpoint=ENDPOINT,
        credential=FakeCredential(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{"translations": []}])),
    )
    with pytest.raises(TranslatorError, match="schema"):
        t.translate(["a", "b"], "tr", 1.0)


# ------------------------------------------------------------------ protection


def test_protect_and_unprotect_round_trip_numbers_names_and_markup():
    pattern = protection_pattern(NAMES)
    text = "Kerrigan's 3.1x better pass & 34.2 km/h <run> at 67:28 for Northbridge FC (12th, 55%)"
    p = protect(text, pattern)
    assert "<run>" not in p.html and "&lt;run&gt;" in p.html and "&amp;" in p.html
    assert p.tokens == ("Kerrigan", "3.1x", "34.2", "km/h", "67:28", "Northbridge FC", "12th", "55%")
    # Translator may move the protected pieces around; they only have to come back unchanged.
    spans = SPAN.findall(p.html)
    moved = "Pase " + " y ".join(reversed(spans)) + " &lt;carrera&gt; &amp;"
    back = unprotect(moved, p.tokens)
    for token in p.tokens:
        assert token in back
    assert "<carrera> &" in back and "<span" not in back


@pytest.mark.parametrize(
    "tamper",
    [
        lambda h: h.replace('<span class="notranslate">0.42</span>', '<span class="notranslate">0,42</span>'),
        lambda h: h.replace('<span class="notranslate">0.42</span>', "0.42"),  # tag dropped
        lambda h: h.replace(
            '<span class="notranslate">Kerrigan</span>', '<span class="notranslate">Kerri</span>'
        ),
        lambda h: h + '<span class="notranslate">9</span>',  # piece added
        lambda h: h + "<b>bold</b>",  # other markup
    ],
)
def test_unprotect_refuses_any_change_to_protected_pieces(tamper):
    p = protect("Kerrigan had 0.42 xG", protection_pattern(NAMES))
    with pytest.raises(ProtectionError):
        unprotect(tamper(p.html), p.tokens)


# ------------------------------------------------------------------ crew: cards


def world_crew(fake: FakeAzure, **kw) -> Crew:
    return Crew(TEAMS, llm=TemplateLLM(), translator=service(fake, **kw))


def test_world_language_card_is_translated_and_fact_checked(moments):  # noqa: F811
    fake = FakeAzure()
    crew = world_crew(fake)
    bundle = next(b for b in bundles_from(crew, moments) if b.moment.kind == MomentKind.BETTER_OPTION)
    english = crew.render(bundle, ViewerProfile(language="en"))
    card = crew.render(bundle, ViewerProfile(language="de"))
    assert card is not None and english is not None
    assert len(fake.requests) == 1  # headline, body, why and every evidence label in one request
    assert len(json.loads(fake.requests[0].content)) == 3 + len(english.evidence)
    assert card.language == "de" and card.text_language == "de"
    assert card.translated_by == "azure_ai_translator" and card.fallback_reason is None
    assert card.card_id.endswith(":de") and card.rtl is False
    assert card.headline.startswith("«de»") and card.body != english.body
    # Every number survives exactly: the translated card prints the same numbers as the English one.
    for field in ("headline", "body", "why"):
        assert sorted(extract_numbers(getattr(card, field))) == sorted(
            extract_numbers(getattr(english, field))
        )
    assert [e.value for e in card.evidence] == [e.value for e in english.evidence]
    assert all(e.label.startswith("«de»") for e in card.evidence)
    steps = {(s.agent, s.status) for t in crew.traces(50) for s in t.steps}
    assert ("translator", "ok") in steps


@pytest.mark.parametrize("persona", PERSONAS)
def test_every_kind_survives_translation_for_every_persona(moments, persona):  # noqa: F811
    # No false rejections: a faithful translation of any studio card passes the checks.
    crew = world_crew(FakeAzure())
    for bundle in bundles_from(crew, moments):
        for fav in (None, "NBR"):
            card = crew.render(bundle, ViewerProfile(persona=persona, language="tr", favourite_team=fav))
            assert card is not None, bundle.moment.kind
            assert card.translated_by == "azure_ai_translator", (bundle.moment.kind, card.fallback_reason)
    assert crew.status().translator.rejections == 0


def test_studio_languages_never_go_through_the_translator(moments):  # noqa: F811
    fake = FakeAzure()
    crew = world_crew(fake)
    bundle = bundles_from(crew, moments)[0]
    for lang in STUDIO_LANGUAGES:
        card = crew.render(bundle, ViewerProfile(language=lang))
        assert card is not None and card.translated_by is None and card.text_language == lang
    assert fake.requests == []


def test_tampered_translation_is_rejected_by_the_fact_checker(moments):  # noqa: F811
    # A number slipped in outside the protected spans: the protection check passes,
    # the fact-checker must not.
    fake = FakeAzure(tamper=lambda h: h + " 99")
    crew = world_crew(fake)
    bundle = next(b for b in bundles_from(crew, moments) if b.moment.kind == MomentKind.GOAL)
    english = crew.render(bundle, ViewerProfile(language="en"))
    card = crew.render(bundle, ViewerProfile(language="pt"))
    assert card is not None and english is not None
    assert card.fallback_reason == "translation_rejected"
    assert card.language == "pt" and card.text_language == "en" and card.translated_by is None
    assert (card.headline, card.body, card.why) == (english.headline, english.body, english.why)
    assert crew.status().translator.rejections == 1
    rejected = [
        s for t in crew.traces(50) for s in t.steps if s.agent == "fact_checker" and s.status == "rejected"
    ]
    assert rejected and "99" in (rejected[0].detail or "")


def test_changed_protected_number_is_rejected(moments):  # noqa: F811
    def change(h: str) -> str:
        return re.sub(
            r'(<span class="notranslate">)(\d+)(\.\d+)?', lambda m: m.group(1) + "7" + (m.group(3) or ""), h
        )

    crew = world_crew(FakeAzure(tamper=change))
    bundle = next(b for b in bundles_from(crew, moments) if b.moment.kind == MomentKind.BETTER_OPTION)
    card = crew.render(bundle, ViewerProfile(language="hi"))
    assert card is not None and card.fallback_reason == "translation_rejected" and card.text_language == "en"


def test_translator_off_shows_english_and_says_so(moments):  # noqa: F811
    crew = Crew(TEAMS, llm=TemplateLLM())  # no translator given: follows the switches, which are off
    assert crew.translation.enabled is False
    bundle = bundles_from(crew, moments)[0]
    english = crew.render(bundle, ViewerProfile(language="en"))
    for lang in WORLD_LANGUAGES:
        card = crew.render(bundle, ViewerProfile(language=lang))
        assert card is not None and english is not None
        assert card.language == lang and card.text_language == "en"
        assert card.fallback_reason == "translator_off" and card.translated_by is None
        assert card.headline == english.headline
    status = crew.status().translator
    assert status.mode == "off" and status.available is False and status.requests == 0


def test_switch_needs_both_flags(monkeypatch):
    assert translator_enabled() is False and isinstance(make_translator(), OffTranslator)
    monkeypatch.setenv("MATCHMIND_TRANSLATOR_ENABLED", "true")
    assert translator_enabled() is False  # paid AI still off
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "yes")
    assert translator_enabled() is True and isinstance(make_translator(), AzureTranslator)


def test_metric_alert_in_a_world_language_is_translated():
    fake = FakeAzure()
    crew = world_crew(fake)
    state = ViewerState()
    profile = ViewerProfile(focus_metric="pressure", favourite_team="HCY", language="sw")
    for i, (t, pressure) in enumerate(((100.0, 20.0), (160.0, 37.0))):
        alerts = crew.metric_alerts(
            ev(i + 1, EventType.PASS, t),
            EventMetrics(event_id=f"e{i}"),
            snap(t, away=window(pressure_index=pressure)),
            players(),
            profile,
            state,
        )
    assert len(alerts) == 1 and len(fake.requests) == 1
    alert = alerts[0]
    assert alert.slot == "metric_alert" and alert.language == "sw" and alert.text_language == "sw"
    assert alert.translated_by == "azure_ai_translator" and "37" in alert.headline


# ------------------------------------------------------------------ crew: recap


def test_recap_in_a_world_language_is_one_request_and_checked(moments):  # noqa: F811
    fake = FakeAzure()
    crew = world_crew(fake)
    crew._bundles = {b.moment.moment_id: b for b in bundles_from(crew, moments)}
    profile = ViewerProfile(language="zh-Hans", favourite_team="NBR")
    english = crew.recap(snap(5500.0, period=2), players(), profile.model_copy(update={"language": "en"}))
    recap = crew.recap(snap(5500.0, period=2), players(), profile)
    assert len(fake.requests) == 1
    assert recap.translated_by == "azure_ai_translator" and recap.text_language == "zh-Hans"
    assert recap.language == "zh-Hans" and recap.fact_check.ok
    assert len(recap.key_moments) == len(english.key_moments)
    assert all("«zh-Hans»" in k.headline for k in recap.key_moments)
    assert recap.stats == english.stats  # numbers come from the engine, untouched


def test_tampered_recap_falls_back_to_english(moments):  # noqa: F811
    crew = world_crew(FakeAzure(tamper=lambda h: h + " 42"))
    crew._bundles = {b.moment.moment_id: b for b in bundles_from(crew, moments)}
    recap = crew.recap(snap(5500.0, period=2), players(), ViewerProfile(language="id"))
    assert recap.fallback_reason == "translation_rejected" and recap.text_language == "en"
    assert recap.language == "id" and recap.translated_by is None
    assert recap.fact_check.ok  # the English text that is shown passed


# ------------------------------------------------------------------ rails


def test_cache_hit_sends_no_second_request():
    fake = FakeAzure()
    svc = service(fake)
    a = svc.translate(["Big chance for Kerrigan, 0.42 xG"], "tr", NAMES)
    b = svc.translate(["Big chance for Kerrigan, 0.42 xG"], "tr", NAMES)
    assert a.texts == b.texts and not a.cached and b.cached
    assert len(fake.requests) == 1 and svc.status().cache_hits == 1
    svc.translate(["Big chance for Kerrigan, 0.42 xG"], "ko", NAMES)  # another language is another entry
    assert len(fake.requests) == 2


def test_cache_is_bounded():
    cache = TranslationCache(limit=2)
    for i in range(5):
        cache.put(cache.key([str(i)], "de"), [str(i)])
    assert len(cache) == 2 and cache.get(cache.key(["0"], "de")) is None


def test_cached_translation_is_still_fact_checked(moments):  # noqa: F811
    # A cached translation is re-checked on every use, against the facts of the moment asking.
    fake = FakeAzure(tamper=lambda h: h + " 99")
    crew = world_crew(fake)
    bundle = bundles_from(crew, moments)[0]
    for persona in ("casual", "casual"):
        crew._cards.clear()
        card = crew.render(bundle, ViewerProfile(language="pt", persona=persona))
        assert card is not None and card.fallback_reason == "translation_rejected"
    assert len(fake.requests) == 1  # the refused text is not bought twice


def test_concurrent_viewers_buy_one_translation():
    fake = FakeAzure(delay=0.2)
    svc = service(fake)
    results = []

    def go():
        results.append(svc.translate(["Northbridge FC press high"], "de", NAMES))

    threads = [threading.Thread(target=go) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(fake.requests) == 1
    assert all(r.texts == results[0].texts and r.texts for r in results)


def test_character_budget_and_rate_stop_requests():
    fake = FakeAzure()
    svc = service(fake, budget=CharacterBudget(total=60, per_minute=10_000))
    assert svc.translate(["Short"], "de").texts is not None
    out = svc.translate(["A much longer sentence that would go over the budget set above"], "de")
    assert out.reason == "translator_budget" and len(fake.requests) == 1

    now = [0.0]
    rate = CharacterBudget(total=10_000, per_minute=100, clock=lambda: now[0])
    assert rate.take(80) and not rate.take(30)
    now[0] += 61
    assert rate.take(30)


def test_circuit_breaker_opens_after_three_failures_then_recovers():
    fake = FakeAzure(status=503)
    now = [0.0]
    svc = service(fake, clock=lambda: now[0])
    for i in range(3):
        assert svc.translate([f"Text {i}"], "de").reason == "translator_error"
    assert svc.translate(["Text 4"], "de").reason == "translator_circuit_open"
    assert len(fake.requests) == 3 and svc.status().breaker_open
    now[0] += BREAKER_OPEN_S + 1
    fake.status = 200
    assert svc.translate(["Text 5"], "de").texts is not None
    assert not svc.status().breaker_open


def test_timeout_is_short_and_falls_back():
    fake = FakeAzure(delay=0.5)
    svc = service(fake, timeout_s=0.05)
    t0 = time.perf_counter()
    out = svc.translate(["Slow"], "de")
    assert out.reason == "translator_timeout" and time.perf_counter() - t0 < 0.4


def test_passing_failure_is_not_cached_so_the_next_render_tries_again(moments):  # noqa: F811
    fake = FakeAzure(status=503)
    crew = world_crew(fake)
    bundle = bundles_from(crew, moments)[0]
    first_try = crew.render(bundle, ViewerProfile(language="de"))
    assert first_try is not None and first_try.fallback_reason == "translator_error"
    fake.status = 200
    second = crew.render(bundle, ViewerProfile(language="de"))
    assert second is not None and second.translated_by == "azure_ai_translator"


def test_language_list_marks_world_languages_off_until_switched_on():
    off = {lang.code: lang for lang in language_list(False)}
    assert len(off) == len(STUDIO_LANGUAGES) + len(WORLD_LANGUAGES) == 13
    assert all(off[c].available and off[c].source == "studio" for c in STUDIO_LANGUAGES)
    assert all(not off[c].available and off[c].reason == "translator_off" for c in WORLD_LANGUAGES)
    assert off["ar"].rtl and off["pt"].name == "Português"
    on = language_list(True)
    assert all(lang.available and lang.reason is None for lang in on)


# ------------------------------------------------------------------ session wiring


def test_bookmark_pass_never_translates_even_when_switched_on(monkeypatch):
    from matchmind.api.session import real_engines

    monkeypatch.setenv("MATCHMIND_TRANSLATOR_ENABLED", "true")
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "true")
    monkeypatch.setenv("AZURE_TRANSLATOR_ENDPOINT", ENDPOINT)
    monkeypatch.setattr("matchmind.api.session.live_llm", lambda: TemplateLLM())  # no model client here
    engines = real_engines()
    assert engines.crew(TEAMS).translation.enabled is True
    assert engines.bookmark_crew(TEAMS).translation.enabled is False


def test_session_does_not_keep_a_recap_left_in_english_by_a_passing_problem(clock):
    from conftest import FakeCrew, FakeStats, make_events
    from matchmind.api.session import Engines, MatchSession

    class FlakyCrew(FakeCrew):
        reason = "translator_timeout"

        def recap(self, *args, **kwargs):
            out = super().recap(*args, **kwargs)
            return out.model_copy(update={"fallback_reason": FlakyCrew.reason, "text_language": "en"})

    session = MatchSession(make_events(), engines=Engines(stats=FakeStats, crew=FlakyCrew), clock=clock)
    profile = ViewerProfile(language="de")
    session.recap(profile)
    session.recap(profile)
    assert session.crew.recap_calls == 2  # tried again
    FlakyCrew.reason = "translator_off"  # the same answer every time: kept
    session.recap(profile)
    session.recap(profile)
    assert session.crew.recap_calls == 3
