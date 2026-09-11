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

from gauntpy.game import coords
from gauntpy.game.constants import NULL_SLOT, NUM_MOB_SLOTS, GameMode, MazeObjIds
from gauntpy.game.mob import MobTable
from gauntpy.game.state import GameState, Player
from gauntpy.game.subsystems.session import coincheck

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


# --- health writers preserve the documented longword width -------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_coin_health_writer_preserves_signed_longword_wraparound(seed):
    """0x42C2C adds the configured coin health using the signed RAM convention."""
    rng = random.Random(seed)
    values = [1, 100, 0x7FFFFFFF - 99, 0x7FFFFFFF]
    values.extend(rng.randint(1, 0x7FFFFFFF) for _ in range(200))
    state = GameState(game_mode=GameMode.NORMAL, game_settings=0)
    player = state.players[0]
    for value in values:
        player.health = value
        player.coin_count = 2
        state.last_coin_state = 0
        state.coin_counters = 1
        state.health_dirty[0] = 0
        coincheck(state)
        # Config index zero is the literal 100-health word at ROM 0x57862.
        expected = ((value + 100 + (1 << 31)) % (1 << 32)) - (1 << 31)
        assert player.health == expected
        assert state.health_dirty[0] == 1


def test_default_player_health_and_score_are_in_bounds():
    """The one thing directly checkable against real code today: the
    dataclass defaults never violate the 32-bit contract."""
    player = Player(index=0)
    assert 0 <= player.health <= 0xFFFFFFFF
    assert 0 <= player.score <= 0xFFFFFFFF
