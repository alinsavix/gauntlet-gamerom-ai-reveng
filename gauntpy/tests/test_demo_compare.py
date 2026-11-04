"""tools/demo_compare.py: the trace reader, the pokes, and poked runs pinned to MAME."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from gauntpy.game.constants import MazeObjIds
from gauntpy.game.mainloop import tick
from gauntpy.game.state import GameState
from gex.roms import SLAPSTIC_ROMS, _rom_dir

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "demo_compare.py"
_SPEC = importlib.util.spec_from_file_location("gauntpy_demo_compare", _TOOL)
demo_compare = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = demo_compare
_SPEC.loader.exec_module(demo_compare)

requires_roms = pytest.mark.skipif(
    not (_rom_dir() / SLAPSTIC_ROMS[0]).is_file(), reason="Slapstic ROMs not available",
)


def _frame(frame: int, iteration: int, seed: int) -> str:
    fields = ["F", frame, f"{iteration:x}", "0", f"{seed:x}"] + ["0"] * 11
    return ",".join(str(field) for field in fields) + "\n"


def test_a_trace_keeps_the_last_sample_of_each_iteration(tmp_path):
    trace = tmp_path / "trace.txt"
    trace.write_text(
        "MAME's start-up chatter\n"
        + _frame(27, 0, 0x1111) + "M,40,100,0,0,0,0\n"   # setup, before the demo's first iteration
        + _frame(28, 1, 0x2222)                          # a lag frame: mid-iteration
        + _frame(29, 1, 0x3333) + "M,40,200,400,8000,1012,312\n"
        + _frame(30, 2, 0x4444),
        encoding="utf-8",
    )
    iterations = demo_compare.load_trace(trace)
    assert sorted(iterations) == [1, 2]
    assert iterations[1][0]["seed"] == 0x3333
    assert iterations[1][1][40] == (0x200, 0x400, 0x8000, 0x1012, 0x312)
    assert iterations[2][1][40] == (0x200, 0x400, 0x8000, 0x1012, 0x312), "a slot keeps its last dump"


def test_the_families_poke_moves_monsters_and_their_generators():
    state = GameState()
    mobs = state.mobs
    for slot, obj_type in ((33, MazeObjIds.MONST_GHOST), (34, MazeObjIds.MONST_GRUNT),
                           (35, MazeObjIds.MONST_AUX_GRUNT), (36, MazeObjIds.GEN_GHOST1),
                           (37, MazeObjIds.GEN_GRUNT3), (38, MazeObjIds.GEN_AUX_GRUNT2),
                           (39, MazeObjIds.MONST_ACID)):
        mobs.create(slot, tile=0x2300, hpos=0x4005, vpos=0x8012, obj_type=int(obj_type))
    demo_compare.POKES["families"][1](state)
    assert [mobs.obj_type(slot) for slot in range(33, 40)] == [
        MazeObjIds.MONST_DEMON, MazeObjIds.MONST_LOBBER, MazeObjIds.MONST_SORC,
        MazeObjIds.GEN_DEMON1, MazeObjIds.GEN_LOBBER3, MazeObjIds.GEN_SORC2,
        MazeObjIds.MONST_ACID,
    ]
    assert mobs.hpos[33] & 0xF == 8, "a demon's health nibble"
    assert mobs.hpos[34] & 0xF == 0xB
    assert mobs.hpos[39] == 0x4005, "other records are left alone"


def _run_demo(poke: str):
    """Yield (iteration, state) through the poked demo, poking as the capture did."""
    state = demo_compare.new_demo()
    poke_at, poke_fn = demo_compare.POKES[poke]
    iteration = 0
    while True:
        tick(state)
        iteration += 1
        yield iteration, state
        if iteration == poke_at:
            poke_fn(state)


#: traces/mame/poked/families.txt, MAME 0.289: slot 850 is a demon, and at 5315 it fires
#: on frame 6 of its walk.  iteration: (seed, picture, H, V, state word >> 10).
_FAMILIES_SLOT_850 = {
    5314: (0xC264, 0x192D, 0x8B07, 0x2492, 0x37),
    5315: (0xEF88, 0x19D8, 0x8B17, 0x2492, 0x00),
    5352: (0x94A6, 0x1A63, 0x8B17, 0x2492, 0x10),
}


@requires_roms
def test_a_poked_demon_fires_from_frame_zero_as_on_mame():
    """S-199.  With the demo's ghosts and grunts poked into other families, the whole run
    matched the capture; these are the samples around the first shot that used to split
    the two, and the run's end."""
    for iteration, state in _run_demo("families"):
        if iteration in _FAMILIES_SLOT_850:
            mobs = state.mobs
            ours = mobs.state(850) & 0x3F
            assert (
                state.rng.seed, mobs.picture[850], mobs.hpos[850] & 0xFFFF,
                mobs.vpos[850] & 0xFFFF, (ours & 0x38) | (((ours & 7) + 2) & 7),
            ) == _FAMILIES_SLOT_850[iteration], iteration
        if iteration == 7200:
            elf = state.players[1].mob_slot
            assert (state.rng.seed, elf, state.mobs.hpos[elf] & 0xFFFF, state.mobs.vpos[elf] & 0xFFFF) == (
                0xDE1F, 0x91, 0x840D, 0xDA12,
            )
            break


@requires_roms
def test_a_poked_lobber_run_matches_mame():
    """S-203, from traces/mame/poked/lobbers.txt, MAME 0.289.

    At 5400 a rock lands and its impact effect (slot 14) takes the ROM's odd depth key,
    so a passing rock (slot 11) sorts behind it.  At 5496 the Elf turns from its fight,
    which ends it and starts another, so the lobber survives the blow gauntpy used to
    land at 5500 and the two runs stay together to the end.
    """
    for iteration, state in _run_demo("lobbers"):
        mobs = state.mobs
        if iteration == 5400:
            assert (mobs.next_slot(11), mobs.prev_slot(11)) == (850, 14)
            assert (mobs.next_slot(14), mobs.prev_slot(14)) == (11, 685)
        elif iteration == 5496:
            assert mobs.picture[state.players[1].mob_slot] == 0x16B4
        elif iteration == 5500:
            assert state.rng.seed == 0xFF77
            assert (mobs.picture[914], mobs.hpos[914] & 0xFFFF) == (0x1BC7, 0x8C99)
            assert mobs.vpos[state.players[1].mob_slot] & 0xFFFF == 0x1012
        elif iteration == 7200:
            elf = state.players[1].mob_slot
            assert (state.rng.seed, elf, mobs.hpos[elf] & 0xFFFF, mobs.vpos[elf] & 0xFFFF) == (
                0x6D00, 0x248, 0x3F0D, 0x6812,
            )
            break
