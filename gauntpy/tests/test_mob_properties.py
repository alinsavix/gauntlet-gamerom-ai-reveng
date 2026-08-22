"""WP-21 sub-deliverable 4 -- property tests over ``MobTable`` and health.

Hand-rolled, not ``hypothesis``-based: ``hypothesis`` is not a project
dependency (``pyproject.toml``'s ``dev`` group lists only ``pytest``), so
these use plain ``random`` with fixed seeds instead. That is fine here
specifically because this is *test* code generating *test* inputs -- PLAN.md
§9's "RNG divergence" risk and the "route every random draw through
``state.getrandom()``" rule are about the simulation itself, not about how a
test builds its fixtures.

Covers PLAN.md §6 WP-21.4's four invariants: the depth chain is never
cyclic, a slot is never in the chain twice, SLIP band heads always point
into the chain, and health stays within its documented bounds.
"""

from __future__ import annotations

import random

import pytest

from gauntpy import coords
from gauntpy.constants import NULL_SLOT, NUM_MOB_SLOTS, MazeObjIds
from gauntpy.mob import MobTable
from gauntpy.state import Player

SEEDS = [1, 2, 3, 17, 12345]


def _random_table(seed: int, num_ops: int = 300) -> tuple[MobTable, set[int]]:
    """Build a ``MobTable`` via a random sequence of create/unlink/move ops.

    Returns the table alongside ``active``, an independent tally of which
    slots should currently be occupied, kept by this function rather than
    read back from the table -- so the properties below check the table
    against ground truth, not against itself.
    """
    rng = random.Random(seed)
    table = MobTable()
    active: set[int] = set()

    for _ in range(num_ops):
        op = rng.choice(("create", "unlink", "move")) if active else "create"

        if op == "create":
            slot = rng.randint(1, NUM_MOB_SLOTS - 1)  # slot 0 is the chain terminator
            if slot in active:
                continue
            y = rng.randint(0, 1023)
            table.create(
                slot,
                tile=0x100,
                hpos=coords.encode_hpos(0),
                vpos=coords.encode_vpos_at_y(y),
                obj_type=MazeObjIds.MONST_GHOST,
            )
            active.add(slot)

        elif op == "unlink":
            slot = rng.choice(sorted(active))
            table.unlink_and_clear(slot)
            active.discard(slot)

        else:  # move
            src = rng.choice(sorted(active))
            dst = rng.randint(1, NUM_MOB_SLOTS - 1)
            if dst in active or dst == src:
                continue
            table.move_slot(src, dst)
            active.discard(src)
            active.add(dst)

    return table, active


# --- the chain is never cyclic; a slot is never in it twice ------------------
#
# iter_chain() already raises RuntimeError on a cycle (mob.py's own guard).
# If the random operations above ever produced one, these tests would fail
# with that exception before reaching any assertion below.

@pytest.mark.parametrize("seed", SEEDS)
def test_chain_matches_the_active_set_exactly(seed):
    """The chain never drops, duplicates, or invents a slot."""
    table, active = _random_table(seed)
    walked = list(table.iter_chain())

    assert set(walked) == active, "chain contents diverged from the operations performed"


@pytest.mark.parametrize("seed", SEEDS)
def test_a_slot_is_never_in_the_chain_twice(seed):
    table, _active = _random_table(seed)
    walked = list(table.iter_chain())
    assert len(walked) == len(set(walked))


def test_chain_survives_dense_churn_without_a_cycle():
    """A longer, denser run than the parametrized ones above, to bias toward
    the create/unlink/move collisions a short random walk is less likely to
    hit (e.g. moving a slot onto a value about to be reused)."""
    table, active = _random_table(seed=99, num_ops=2000)
    walked = list(table.iter_chain())
    assert set(walked) == active
    assert len(walked) == len(set(walked))


# --- SLIP band heads always point into the chain -----------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_slip_heads_always_point_into_the_chain_or_null(seed):
    """Every SLIP band head either terminates (``NULL_SLOT``) or names a slot
    that is actually in the depth chain (mob.py: "the 64 SLIP band heads
    enter that *same* chain at different positions -- they are not 64
    independent lists")."""
    table, _active = _random_table(seed)
    chain = set(table.iter_chain())

    for band, head in enumerate(table.slip_heads):
        assert head == NULL_SLOT or head in chain, (
            f"slip_heads[{band}] = {head} is not in the depth chain"
        )


@pytest.mark.parametrize("seed", SEEDS)
def test_depth_list_head_is_null_or_currently_active(seed):
    table, active = _random_table(seed)
    if not active:
        assert table.depth_list_head == NULL_SLOT
    else:
        assert table.depth_list_head in active


# --- health never exceeds its documented bounds ------------------------------
#
# PLAN.md §3 ground rule 6: "Health and score are 32-bit [longwords] ...
# Mask on write where width is observable." No WP-6 writer exists yet --
# state.py's ``Player.health`` has no setter of its own, so there is no
# production code path to exercise here. What *is* checkable today: the
# masking rule itself, against an independent reference, and the dataclass
# defaults. Once WP-6 lands a real health-write function, swap ``_mask_u32``
# below for it and this test starts checking the genuine article.

def _mask_u32(value: int) -> int:
    return value & 0xFFFFFFFF


@pytest.mark.parametrize("seed", SEEDS)
def test_health_mask_matches_32bit_unsigned_wraparound(seed):
    rng = random.Random(seed)
    for _ in range(200):
        # Both a plausible in-range accumulation and values far outside 32
        # bits in either sign, mirroring what an unmasked write -- or an
        # underflowing `subq.l` -- could produce on real hardware.
        value = rng.randint(-(1 << 40), 1 << 40)
        masked = _mask_u32(value)
        assert 0 <= masked <= 0xFFFFFFFF
        assert masked == value % (1 << 32), "must match 32-bit unsigned wraparound exactly"


def test_default_player_health_and_score_are_in_bounds():
    """The one thing directly checkable against real code today: the
    dataclass defaults never violate the 32-bit contract."""
    player = Player(index=0)
    assert 0 <= player.health <= 0xFFFFFFFF
    assert 0 <= player.score <= 0xFFFFFFFF
