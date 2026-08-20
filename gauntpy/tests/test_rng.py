"""The game's LCG, ported from random_core (0x5FC2C)."""

from __future__ import annotations

import pytest

from gauntpy.rng import INCREMENT, MAX_SAFE_BOUND, MULTIPLIER, SEED_BIAS, GameRandom


# ---------------------------------------------------------------------------
# A literal model of the 68010 routine, one Python statement per instruction.
# gauntpy's own implementation is the *simplified* form; this is the thing it
# has to agree with, so the two are checked against each other exhaustively
# below rather than both being checked against a hand-picked constant.
# ---------------------------------------------------------------------------

def _s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _swap(value: int) -> int:
    """68k SWAP: exchange the two halves of a longword."""
    return ((value & 0xFFFF) << 16) | ((value >> 16) & 0xFFFF)


def rom_random_core(seed: int, bound: int) -> tuple[int, int]:
    """``(result, new_seed)`` exactly as ROM 0x5FC26-0x5FC44 computes them."""
    d0 = bound & 0xFFFF                                  # moveq #0,d0 / move.w 6(a7),d0
    d1 = seed & 0xFFFF                                   # move.w (a0),d1
    d1 = (_s16(d1) * MULTIPLIER) & 0xFFFFFFFF            # muls.w #$3619,d1
    d1 = (d1 & 0xFFFF0000) | ((d1 + INCREMENT) & 0xFFFF)  # addi.w #$5D35,d1
    new_seed = d1 & 0xFFFF                               # move.w d1,(a0)
    d1 = (_s16(d1) * _s16(d0)) & 0xFFFFFFFF              # muls.w d0,d1
    d0 = _swap(d0)                                       # swap d0
    d0 = (_s32(d0) >> 1) & 0xFFFFFFFF                    # asr.l #1,d0
    d0 = (d0 + d1) & 0xFFFFFFFF                          # add.l d1,d0
    d0 = _swap(d0)                                       # swap d0
    return _s16(d0), new_seed                            # ext.l d0 / rts


# ---------------------------------------------------------------------------
# The recurrence
# ---------------------------------------------------------------------------

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


def test_constructor_masks_a_wide_seed():
    assert GameRandom(seed=0x1234_5678).seed == 0x5678
    assert GameRandom(seed=-1).seed == 0xFFFF


def test_the_lcg_has_the_full_16_bit_period():
    """Hull-Dobell: multiplier % 4 == 1 and an odd increment give every one of
    the 65536 seeds exactly once, so the stream never falls into a short cycle
    however long a session runs."""
    assert MULTIPLIER % 4 == 1
    assert INCREMENT % 2 == 1

    rng = GameRandom(seed=0)
    seen = {0}
    for _ in range(0xFFFF):
        rng.getrandom(2)
        seen.add(rng.seed)
    assert len(seen) == 0x10000
    rng.getrandom(2)
    assert rng.seed == 0, "the period must close back onto the starting seed"


# ---------------------------------------------------------------------------
# Agreement with the instruction-level model
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bound", [0, 1, 2, 3, 4, 13, 32, 0x100, 0x7FFF, 0x8000, 0xFFFF])
def test_matches_the_instruction_model_over_every_seed(bound):
    """Exhaustive over all 65536 seeds, for the bounds the game actually uses
    plus the two signed ones -- there is no sampling to argue about."""
    rng = GameRandom()
    for seed in range(0x10000):
        rng.seed = seed
        got = rng.getrandom(bound)
        expected, expected_seed = rom_random_core(seed, bound)
        assert (got, rng.seed) == (expected, expected_seed), (
            f"seed {seed:#06x} bound {bound:#06x}"
        )


def test_the_seed_bias_is_the_documented_one():
    assert SEED_BIAS == 0x8000
    rng = GameRandom(seed=0x1111)
    seed_after = (0x1111 * MULTIPLIER + INCREMENT) & 0xFFFF
    assert rng.getrandom(100) == (100 * ((seed_after + SEED_BIAS) & 0xFFFF)) >> 16


# ---------------------------------------------------------------------------
# Range, width and sign
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bound", [1, 2, 3, 8, 32, 0x100, 0x7FFF])
def test_results_stay_in_range(bound):
    rng = GameRandom(seed=0x1234)
    for _ in range(2000):
        assert 0 <= rng.getrandom(bound) < bound


def test_bound_zero_is_safe_and_still_advances_the_seed():
    """A zero-bound draw yields 0 but must not be shortcut: the ROM stores the
    advanced seed at 0x5FC36, before it has looked at the bound at all, so
    skipping the advance would desynchronise the shared stream."""
    rng = GameRandom(seed=1)
    assert rng.getrandom(0) == 0
    assert rng.seed == (1 * MULTIPLIER + INCREMENT) & 0xFFFF


def test_bit15_bounds_follow_muls_w_instead_of_raising():
    """``MULS.W`` reads a bound with bit 15 set as negative, so the result is
    <= 0 and the [0, bound) guarantee is gone (doc/07 §14.1). The ROM returns
    it anyway; so do we, rather than inventing an exception the hardware does
    not have."""
    assert MAX_SAFE_BOUND == 0x7FFF
    for bound in (0x8000, 0xC000, 0xFFFF):
        rng = GameRandom(seed=0x2222)
        for _ in range(200):
            result = rng.getrandom(bound)
            assert -0x8000 <= result <= 0
            assert result == rom_random_core(
                (rng.seed - INCREMENT) * pow(MULTIPLIER, -1, 0x10000) & 0xFFFF, bound
            )[0]


def test_bound_is_a_hardware_word():
    """Only the low 16 bits of the bound reach ``MULS.W``, so anything wider is
    truncated exactly as pushing it as a word would be."""
    a = GameRandom(seed=99).getrandom(32)
    b = GameRandom(seed=99).getrandom(0x1_0020)
    assert a == b


# ---------------------------------------------------------------------------
# The veneers
# ---------------------------------------------------------------------------

def test_random_word_is_the_same_body():
    """0x5FC46 is a two-instruction veneer onto the same core (§14.1)."""
    assert GameRandom(seed=5).random_word(64) == GameRandom(seed=5).getrandom(64)


def test_random_seeded_does_not_touch_the_global_stream():
    """0x5FC22 takes its own seed pointer, so a draw through it leaves
    0x904BFC -- the stream every other caller shares -- exactly where it was."""
    rng = GameRandom(seed=0xABCD)
    result, new_seed = rng.random_seeded(50, seed=0x1234)
    assert rng.seed == 0xABCD
    assert (result, new_seed) == rom_random_core(0x1234, 50)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

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
