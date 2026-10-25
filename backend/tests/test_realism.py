"""Football realism: seeded unscripted matches produce believable per-match averages."""

import pytest

from matchmind.simulator import realism


@pytest.fixture(scope="module")
def lines():
    return realism.measure_all()


def test_twenty_seeded_matches(lines):
    assert len(lines) == 20
    assert [x.seed for x in lines] == list(realism.SEEDS)


@pytest.mark.parametrize("metric", list(realism.RANGES))
def test_average_in_realistic_range(lines, metric):
    lo, hi = realism.RANGES[metric]
    avg = realism.averages(lines)[metric]
    assert lo <= avg <= hi, f"{metric} average {avg} outside {lo}-{hi}"


def test_possession_splits_sum_to_100(lines):
    for x in lines:
        assert x.possession_home + x.possession_away == pytest.approx(100.0)
        assert 30.0 <= x.possession_home <= 70.0


def test_per_match_sanity(lines):
    for x in lines:
        assert x.shots_on_target <= x.shots
        assert x.goals <= x.shots_on_target
        assert 60.0 <= x.pass_accuracy <= 95.0


def test_deterministic():
    assert realism.measure(1000) == realism.measure(1000)


def test_table_prints(lines):
    text = realism.table(lines)
    assert "| 1000 |" in text and "pass_accuracy" in text
