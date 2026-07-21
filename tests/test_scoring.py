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
    # Window matching the baseline expectation should score low.
    assert poisson_surprise(100, 100) < poisson_surprise(0, 25)
    # Below expectation => essentially no surprise.
    assert poisson_surprise(100, 50) < 1.0


def test_vanished_scores_zero():
    # KNOWN LIMITATION (design doc Q2b): surprise is one-sided (upper tail),
    # so a vanished template (window=0) always scores 0. This test documents
    # that on purpose — if lower-tail scoring is added, update it deliberately.
    assert poisson_surprise(100, 0) == 0.0
