"""Unit tests for Poisson surprise scoring.

We assert *properties* (monotonicity, ordering, finiteness), not magic numbers,
so the tests survive scipy version bumps that shift a rounding digit.
"""

import math

from loglens.scoring import poisson_surprise


def test_score_is_non_negative():
    # -ln(P), P <= 1  =>  score >= 0, always.
    for base, win in [(0, 1), (100, 100), (135, 176), (0, 50), (100, 0)]:
        assert poisson_surprise(base, win) >= 0.0


def test_monotonic_in_window_count():
    # For a fixed baseline, seeing more is never less surprising.
    assert (
        poisson_surprise(0, 5)
        < poisson_surprise(0, 25)
        < poisson_surprise(0, 50)
    )


def test_surprise_beats_volume():
    # The core thesis: a rare-but-new event outranks a common one wobbling.
    assert poisson_surprise(0, 25) > poisson_surprise(135, 176)


def test_lambda_zero_is_finite():
    # NEW templates have base=0; smoothing (alpha) must keep the score finite.
    assert math.isfinite(poisson_surprise(0, 1))


def test_normal_is_quieter_than_anomaly():
    # A window matching the baseline expectation should score low...
    assert poisson_surprise(100, 100) < poisson_surprise(0, 25)
    assert poisson_surprise(100, 100) < 2.0
    # ...but a real DROP is now surprising too (two-sided scoring, Q2b fix):
    # 100 -> 50 falls in the lower tail and must outscore the quiet case.
    assert poisson_surprise(100, 50) > poisson_surprise(100, 100)


def test_vanished_is_now_surprising():
    # Q2b FIXED: two-sided surprise. A template that fired ~100x in the baseline
    # but vanished (window=0) is highly improbable under the lower tail, so it
    # scores high and can rank — previously this returned 0 and sank.
    assert poisson_surprise(100, 0) > 50.0
