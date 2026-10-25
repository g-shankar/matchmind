from matchmind.crew.analyst import verdict
from matchmind.crew.fact_checker import check


def test_model_text_may_use_first_and_second():
    r = check(
        "A first touch and a second ball keep the move alive.", {"score": "1-0"}, "en", strict_words=True
    )
    assert r.ok, r.reasons


def test_other_ordinals_still_need_facts():
    assert not check("His third shot of the night.", {"score": "1-0"}, "en", strict_words=True).ok


def test_raw_fact_keys_are_rejected():
    r = check(
        "High involvement (p_key_passes 3) lifts the tempo.", {"p_key_passes": 3}, "en", strict_words=True
    )
    assert any("field name p_key_passes" in x for x in r.reasons)


def test_better_option_payload_carries_the_verdict():
    from types import SimpleNamespace

    from matchmind.crew.contracts import MomentKind

    m = SimpleNamespace(
        kind=MomentKind.BETTER_OPTION, facts={"player": "K. Asante", "teammate": "A. Kerrigan"}
    )
    assert verdict(m) == {"verdict": "K. Asante should have passed to A. Kerrigan."}
    assert verdict(SimpleNamespace(kind=MomentKind.GOAL, facts={})) == {}
