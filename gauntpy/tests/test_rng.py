"""The game's LCG, ported from random_core (0x5FC2C)."""

from __future__ import annotations

import pytest

from gauntpy.rng import INCREMENT, MULTIPLIER, GameRandom


def test_seed_advance_matches_the_documented_lcg():
    rng = GameRandom(seed=0)
    rng.getrandom(32)
    assert rng.seed == (0 * MULTIPLIER + INCREMENT) & 0xFFFF == 0x5D35


def test_known_value():
    """seed 0 -> 0x5D35; (32 * ((0x5D35 + 0x8000) & 0xFFFF)) >> 16 == 27."""
    assert GameRandom(seed=0).getrandom(32) == 27


def test_seed_stays_sixteen_bit():
    rng = GameRandom(seed=0xFFFF)
    for _ in range(500):
        rng.getrandom(16)
        assert 0 <= rng.seed <= 0xFFFF


@pytest.mark.parametrize("bound", [1, 2, 3, 8, 32, 0x100, 0x7FFF])
def test_results_stay_in_range(bound):
    rng = GameRandom(seed=0x1234)
    for _ in range(2000):
        assert 0 <= rng.getrandom(bound) < bound


def test_bound_zero_is_safe():
    assert GameRandom(seed=1).getrandom(0) == 0


def test_signed_bounds_are_refused():
    """MULS.W loses the [0, bound) guarantee above 0x7FFF; fail loudly."""
    with pytest.raises(ValueError, match="0x7FFF"):
        GameRandom().getrandom(0x8000)


def test_same_seed_reproduces_the_sequence():
    """The original's seed free-runs and is never initialized, so nothing in
    the real machine repeats. Ours does -- that is what makes tests possible."""
    a = [GameRandom(seed=42).getrandom(100) for _ in range(1)]
    first = GameRandom(seed=42)
    second = GameRandom(seed=42)
    assert [first.getrandom(100) for _ in range(50)] == [
        second.getrandom(100) for _ in range(50)
    ]
    assert a[0] == GameRandom(seed=42).getrandom(100)


def test_distribution_is_roughly_uniform():
    rng = GameRandom(seed=7)
    counts = [0] * 4
    for _ in range(8000):
        counts[rng.getrandom(4)] += 1
    assert all(1600 < c < 2400 for c in counts), counts
