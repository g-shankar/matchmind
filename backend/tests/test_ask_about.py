"""Ask the studio: questions about PitchPulse itself, and the "should he have passed?"
answer before the first such moment (first-time-user testing, round 2: R2-01, R2-04)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from matchmind.api import reads
from matchmind.api.session import MatchSession
from matchmind.ask import ask
from matchmind.ask.i18n import PACKS
from matchmind.crew.fact_checker import check

LANGS = ("en", "es", "fr", "ar", "ja")


@pytest.fixture(scope="module")
def demo() -> MatchSession:
    from matchmind.mcp.__main__ import load

    return load(70 * 60, 2)


@pytest.fixture
def ctx70(demo):
    demo.seek(70 * 60, 2)
    return reads.ask_context(demo)


@pytest.fixture
def ctx_kickoff(demo):
    demo.seek(35, 1)
    return reads.ask_context(demo)


PROVENANCE = [
    ("en", "Is this real data?"),
    ("en", "Is this real Premier League data and who built you?"),
    ("en", "Is this AI?"),
    ("en", "Who made PitchPulse?"),
    ("es", "¿Son datos reales?"),
    ("es", "¿Quién te hizo?"),
    ("fr", "Est-ce que ce sont des données réelles ?"),
    ("fr", "Es-tu une IA ?"),
    ("ar", "من صنعك؟"),
    ("ar", "هل أنت ذكاء اصطناعي؟"),
    ("ja", "これは本物のデータですか？"),
    ("ja", "誰が作ったの？"),
]


@pytest.mark.parametrize(("lang", "question"), PROVENANCE)
def test_provenance_questions_get_the_fixed_about_answer(ctx70, lang, question):
    a = ask(ctx70, question=question, language=lang)
    assert a.status == "answered", (question, a.reason)
    assert a.intent is not None and a.intent.kind == "about"
    pack = PACKS[lang]
    sep = "" if lang == "ja" else " "
    expected = sep.join(pack[k] for k in ("about_data", "about_numbers", "about_template", "about_team"))
    assert a.answer == expected  # fixed text, the same every time: nothing from the question
    assert not a.evidence and not a.moment_ids and not a.source_event_ids
    assert check(a.answer, a.facts, lang, "text").ok


def test_the_about_answer_never_repeats_a_real_name(ctx70):
    a = ask(ctx70, question="Is this real Premier League data?")
    assert a.intent is not None and a.intent.kind == "about"
    assert "Premier" not in a.answer and "League" not in a.answer
    assert "synthetic" in a.answer and "hackathon" in a.answer


def test_the_about_answer_says_when_paid_ai_is_on(ctx70):
    a = ask(replace(ctx70, ai_crew=True), question="Is this AI?")
    assert a.answer.count(PACKS["en"]["about_ai"]) == 1
    assert PACKS["en"]["about_template"] not in a.answer


def test_about_answers_have_no_numbers():
    for lang in LANGS:
        for key in ("about_data", "about_numbers", "about_template", "about_ai", "about_team"):
            assert not any(ch.isdigit() for ch in PACKS[lang][key]), (lang, key)


@pytest.mark.parametrize(
    "question",
    [
        "who made this pass?",  # a match question that happens to read "who made this"
        "Who made the most tackles?",
    ],
)
def test_match_questions_still_win_over_about(ctx70, question):
    a = ask(ctx70, question=question)
    assert a.intent is not None and a.intent.kind == "top_player"


def test_a_real_name_without_a_provenance_question_is_still_refused(ctx70):
    a = ask(ctx70, question="Who scored for Arsenal?")
    assert a.status == "refused" and a.reason == "real_name"


def test_better_option_before_the_first_one_points_to_the_moments_list(ctx_kickoff):
    for lang in LANGS:
        a = ask(ctx_kickoff, chip="better_option", language=lang)
        assert a.status == "answered"
        assert a.answer == PACKS[lang]["better_none"].replace("{clock}", ctx_kickoff.clock)
        assert check(a.answer, a.facts, lang, "text").ok
    en = ask(ctx_kickoff, chip="better_option").answer
    assert "moments list" in en and "jump" in en
    # Never reads ahead: the moment's clock is not in the answer.
    assert "34:16" not in en
