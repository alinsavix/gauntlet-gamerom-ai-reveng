"""Tests for the maze and level system (WP-3).

Split the same way ``test_assets.py`` is: pure-Python behavior (level
selection, ``maze_place_object``, the row-0 fill) needs no ROMs and always
runs; everything that decodes a real maze record needs the Slapstic ROM
files and skips cleanly (not errors) when ``GEX_ROM_DIR`` is unset, mirroring
``test_assets.py``'s ``requires_roms_and_refs`` pattern.
"""

from __future__ import annotations

import pytest

from gauntpy import maze as gm
from gauntpy.constants import FIRST_PLAYABLE_SLOT, GameMode, MazeObjIds
from gauntpy.coords import pack_slot
from gauntpy.state import GameState

from gex.constants import MAX_MAZE_NUM
from gex.roms import SLAPSTIC_ROMS, _rom_dir

# ---------------------------------------------------------------------------
# ROM availability (same approach as test_assets.py, but the Slapstic ROM
# pair specifically -- that is what maze decoding actually reads).
# ---------------------------------------------------------------------------

_ROM_PATH = _rom_dir()
_ROMS_EXIST = _ROM_PATH.is_dir() and (_ROM_PATH / SLAPSTIC_ROMS[0]).is_file()

requires_roms = pytest.mark.skipif(
    not _ROMS_EXIST,
    reason=f"Slapstic ROM files ({_ROM_PATH}) not available",
)


# ---------------------------------------------------------------------------
# maze_for_level -- the one fixed level->maze rule (doc/06 §3.1)
# ---------------------------------------------------------------------------

class TestMazeForLevel:
    def test_opening_act_levels_map_to_mazes_0_through_4_in_order(self):
        assert [gm.maze_for_level(n) for n in range(1, 6)] == [0, 1, 2, 3, 4]

    def test_level_six_and_beyond_has_no_fixed_mapping(self):
        """doc/06 §3.2: "the level -> maze mapping is cabinet state, not a
        formula" past the opening act."""
        for level in (6, 7, 999, 1000):
            assert gm.maze_for_level(level) is None

    def test_level_zero_has_no_fixed_mapping(self):
        assert gm.maze_for_level(0) is None


# ---------------------------------------------------------------------------
# maze_place_object -- pure arithmetic, needs no ROMs
# ---------------------------------------------------------------------------

class TestMazePlaceObject:
    def test_returns_next_slot(self):
        state = GameState()
        next_slot = gm.maze_place_object(state, 100, MazeObjIds.WALL_REGULAR, 5)
        assert next_slot == 105

    def test_places_the_requested_type_at_every_slot(self):
        state = GameState()
        gm.maze_place_object(state, 50, MazeObjIds.KEY, 3)
        for slot in (50, 51, 52):
            assert state.mobs.obj_type(slot) == MazeObjIds.KEY
        assert not state.mobs.is_occupied(53)

    def test_row_zero_fill_writes_wall_markers_in_slots_0_to_31(self):
        """SOL-02, MAME write-watch verified (doc/04 §5.3): maze_setupnew
        calls maze_place_object(0, 2, 0x20) immediately after decode to
        stamp the reserved row-0 block as solid walls.
        """
        state = GameState()
        next_slot = gm.maze_place_object(state, 0, MazeObjIds.WALL_REGULAR, FIRST_PLAYABLE_SLOT)

        assert next_slot == FIRST_PLAYABLE_SLOT == 0x20
        for slot in range(FIRST_PLAYABLE_SLOT):
            assert state.mobs.obj_type(slot) == MazeObjIds.WALL_REGULAR, f"slot {slot} not a wall marker"
        assert not state.mobs.is_occupied(FIRST_PLAYABLE_SLOT), "fill must not spill past slot 31"


# ---------------------------------------------------------------------------
# find_maze / decode_maze -- need the Slapstic ROMs
# ---------------------------------------------------------------------------

@requires_roms
class TestFindMaze:
    def test_all_117_mazes_resolve_to_a_valid_bank(self):
        for n in range(MAX_MAZE_NUM + 1):
            loc = gm.find_maze(n)
            assert loc.bank in (0, 1, 2, 3)
            assert loc.addr >= 0x38000

    def test_bank_layout_matches_doc_06_table(self):
        """doc/06 §2: mazes 0-32 bank 0, 33-62 bank 1, 63-88 bank 2, 89-116 bank 3."""
        assert gm.find_maze(0).bank == 0
        assert gm.find_maze(32).bank == 0
        assert gm.find_maze(33).bank == 1
        assert gm.find_maze(62).bank == 1
        assert gm.find_maze(63).bank == 2
        assert gm.find_maze(88).bank == 2
        assert gm.find_maze(89).bank == 3
        assert gm.find_maze(116).bank == 3

    def test_out_of_range_raises_maze_error(self):
        with pytest.raises(gm.MazeError):
            gm.find_maze(-1)
        with pytest.raises(gm.MazeError):
            gm.find_maze(MAX_MAZE_NUM + 1)


@requires_roms
class TestDecodeMaze:
    def test_all_117_mazes_decode_without_error(self):
        for n in range(MAX_MAZE_NUM + 1):
            maze = gm.decode_maze(n)
            assert maze.data, f"maze {n} decoded with no placed objects"

    def test_out_of_range_raises_maze_error(self):
        with pytest.raises(gm.MazeError):
            gm.decode_maze(MAX_MAZE_NUM + 1)


# ---------------------------------------------------------------------------
# place_decoded_objects -- MobTable must agree with gex's own decoder
# ---------------------------------------------------------------------------

@requires_roms
class TestPlaceDecodedObjectsMatchesGex:
    @pytest.mark.parametrize("maze_number", [0, 1, 4, 5, 50, 101, 104, 115, 116])
    def test_every_decoded_cell_lands_at_its_packed_slot(self, maze_number):
        """Acceptance: "decoded cell contents match gex's decoder exactly
        for every maze." Row 0 is placed separately (``maze_place_object``'s
        row-0 fill, matching maze_setupnew's own two-step order -- see
        ``place_decoded_objects``'s docstring), so both steps run here to
        cover every entry in gex's ``Maze.data``, row 0 included. A fresh
        GameState defaults game_mode to TITLE (not NORMAL), so the
        dragon-suppression special case in ``_place_decoded`` never fires
        here -- this checks raw placement fidelity against gex, independent
        of that gameplay rule.
        """
        state = GameState()
        maze = gm.decode_maze(maze_number)
        gm.place_decoded_objects(state, maze)
        gm.maze_place_object(state, 0, MazeObjIds.WALL_REGULAR, FIRST_PLAYABLE_SLOT)

        assert len(maze.data) > 0
        for (col, row), object_type in maze.data.items():
            slot = pack_slot(row, col)
            assert state.mobs.obj_type(slot) == object_type, (
                f"maze {maze_number} cell (col={col}, row={row}) slot {slot}: "
                f"expected type {object_type}, got {state.mobs.obj_type(slot)}"
            )

    def test_all_117_mazes_place_without_error(self):
        for n in range(MAX_MAZE_NUM + 1):
            state = GameState()
            maze = gm.decode_maze(n)
            gm.place_decoded_objects(state, maze)
            gm.maze_place_object(state, 0, MazeObjIds.WALL_REGULAR, FIRST_PLAYABLE_SLOT)

            # place_decoded_objects skips row 0 (gex bakes it into Maze.data
            # as a decode convenience -- see its docstring) and slot 0 is
            # never chain-linked (NULL_SLOT sentinel -- _create_generic), so
            # the chain length is every non-row-0 entry, plus slots 1-31
            # from the row-0 fill.
            non_row_zero = sum(1 for (_, row) in maze.data if row != 0)
            assert len(state.mobs) == non_row_zero + (FIRST_PLAYABLE_SLOT - 1)


@requires_roms
class TestDragonSuppression:
    """Maze 6 is the earliest rotation maze with a dragon token (doc/04 §5.4)."""

    def test_dragon_suppressed_before_level_12_in_normal_mode(self):
        state = GameState(game_mode=GameMode.NORMAL, levelnum_current=6)
        maze = gm.decode_maze(6)
        gm.place_decoded_objects(state, maze)

        for (col, row), object_type in maze.data.items():
            if object_type == MazeObjIds.MONST_DRAGON:
                slot = pack_slot(row, col)
                assert not state.mobs.is_occupied(slot), "dragon must be suppressed before level 12"

    def test_dragon_not_suppressed_at_or_after_level_12(self):
        state = GameState(game_mode=GameMode.NORMAL, levelnum_current=12)
        maze = gm.decode_maze(6)
        gm.place_decoded_objects(state, maze)

        dragon_slots = [
            pack_slot(row, col) for (col, row), t in maze.data.items() if t == MazeObjIds.MONST_DRAGON
        ]
        assert dragon_slots
        assert any(state.mobs.obj_type(s) == MazeObjIds.MONST_DRAGON for s in dragon_slots)

    def test_dragon_not_suppressed_outside_normal_game_mode(self):
        """Suppression is specifically gated on game_mode == NORMAL (doc/04 §5.4)."""
        state = GameState(game_mode=GameMode.DEMO, levelnum_current=1)
        maze = gm.decode_maze(6)
        gm.place_decoded_objects(state, maze)

        dragon_slots = [
            pack_slot(row, col) for (col, row), t in maze.data.items() if t == MazeObjIds.MONST_DRAGON
        ]
        assert any(state.mobs.obj_type(s) == MazeObjIds.MONST_DRAGON for s in dragon_slots)


# ---------------------------------------------------------------------------
# load_level -- the public entry point
# ---------------------------------------------------------------------------

@requires_roms
class TestLoadLevel:
    def test_levels_1_through_5_load_mazes_0_through_4(self):
        for level, expected_maze in zip(range(1, 6), range(0, 5)):
            state = GameState()
            gm.load_level(state, level)
            assert state.levelnum_current == level
            assert state.mazenum_current == expected_maze
            assert state.maze is not None

    def test_row_zero_is_wall_markers_after_load(self):
        state = GameState()
        gm.load_level(state, 1)
        for slot in range(FIRST_PLAYABLE_SLOT):
            assert state.mobs.obj_type(slot) == MazeObjIds.WALL_REGULAR

    def test_decoded_objects_present_after_load(self):
        """Every decoded cell is occupied after load_level, whether or not
        it is chain-linked -- slot 0 specifically never joins the depth
        chain (NULL_SLOT sentinel, see maze.py's _create_generic), so this
        checks occupancy (``is_occupied``) rather than chain length.
        """
        state = GameState()
        gm.load_level(state, 2)  # maze 1
        maze = gm.decode_maze(1)
        for col, row in maze.data:
            slot = pack_slot(row, col)
            assert state.mobs.is_occupied(slot), f"slot {slot} (col={col}, row={row}) not occupied"

    def test_level_past_opening_act_reuses_existing_mazenum_current(self):
        """No fixed rule past level 5 (doc/06 §3.2) -- load_level trusts
        state.mazenum_current, which the caller (not WP-3) is responsible
        for advancing. Here nothing advances it, so it stays put.
        """
        state = GameState(mazenum_current=42)
        gm.load_level(state, 6)
        assert state.mazenum_current == 42
        assert state.levelnum_current == 6

    def test_wrap_flags_follow_level_flags_4(self):
        state = GameState()
        gm.load_level(state, 1)
        from gex.constants import LFLAG4_WRAP_H, LFLAG4_WRAP_V

        assert state.wrap_h == bool(state.level_flags_4 & LFLAG4_WRAP_H)
        assert state.wrap_v == bool(state.level_flags_4 & LFLAG4_WRAP_V)


# ---------------------------------------------------------------------------
# maze_load_pickup_config / get_random_maze_flags
# ---------------------------------------------------------------------------

@requires_roms
class TestMazeLoadPickupConfig:
    def test_assembles_base_flags_from_maze_header(self):
        """With no randomization inputs consumed yet (levelnum 0, maze
        outside 5-114 so no hazard branch fires), the assembled flags must
        equal the maze header's own flags modulo the documented LFLAG1
        bits-2-3 XOR randomization.
        """
        state = GameState(mazenum_current=0, levelnum_current=0)
        maze = gm.decode_maze(0)
        gm.maze_load_pickup_config(state, maze)

        b1, b2, b3, b4 = gm._split_flags(maze.flags)
        assert state.level_flags_2 == b2
        assert state.level_flags_3 == b3
        assert state.level_flags_4 == b4
        # Only bits 2-3 of the LFLAG1 byte may differ (the documented XOR).
        assert (state.level_flags ^ b1) & ~0x0C == 0

    def test_random_maze_flags_table_reads_13_plausible_entries(self):
        table = gm._random_maze_flags_table_read()
        assert len(table) == 13
        assert table[0] == 0  # doc/04 §5.5's "no hazard" entry
        assert all(0 <= v <= 0xFFFFFFFF for v in table)

    def test_get_random_maze_flags_stays_in_range(self):
        state = GameState()
        for _ in range(50):
            result = gm.get_random_maze_flags(state)
            assert result in gm._random_maze_flags_table_read() or result == 0x2


class TestPickupConfigHazardBranches:
    """The hazard branches that OR only constants (the treasure-maze tiers,
    the mazes-5-101 >103 wrap tier, and the attract/9999 skip guard) never
    touch the ROM flags table, so a bare ``Maze(flags=...)`` exercises them
    with no ROMs. All expectations are verified against disassembly at ROM
    0x4374C-0x4381A (capstone, row76.bin); see maze.py's citations.
    """

    def _run(self, *, mazenum, levelnum, game_mode=GameMode.NORMAL, flags=0):
        from gex.mazedecode import Maze
        state = GameState(
            mazenum_current=mazenum, levelnum_current=levelnum, game_mode=game_mode
        )
        gm.maze_load_pickup_config(state, Maze(flags=flags))
        return state

    # --- attract / level==9999 skip guard (ROM 0x4374C-0x43760) ---

    def test_randomization_skipped_in_attract_mode(self):
        """DEMO is attract (game_mode < 0): base flags survive untouched --
        no LFLAG1 bits-2-3 XOR and no treasure hazard OR."""
        state = self._run(mazenum=110, levelnum=200, game_mode=GameMode.DEMO)
        assert (state.level_flags, state.level_flags_2,
                state.level_flags_3, state.level_flags_4) == (0, 0, 0, 0)

    def test_randomization_skipped_on_level_9999(self):
        state = self._run(mazenum=110, levelnum=9999)
        assert state.level_flags_4 == 0  # no treasure hazard applied

    # --- treasure mazes 104-114: graduated 3-tier on level%160 ---
    # (ROM 0x437D6-0x4381A). Regression guard for the corrected unconditional
    # -0xB0 bug: only the top tier gets 0xB0.

    def test_treasure_tier_top(self):
        assert self._run(mazenum=104, levelnum=130).level_flags_4 == 0xB0   # %160=130 > 120

    def test_treasure_tier_offscreen_only(self):
        assert self._run(mazenum=114, levelnum=100).level_flags_4 == 0x80   # > 80

    def test_treasure_tier_wraps_only(self):
        assert self._run(mazenum=110, levelnum=50).level_flags_4 == 0x30    # > 40

    def test_treasure_tier_none_at_boundary(self):
        assert self._run(mazenum=110, levelnum=40).level_flags_4 == 0x00    # not > 40

    def test_treasure_threshold_is_not_unconditional(self):
        """A low level%160 must NOT receive 0xB0 -- the exact bug the
        disassembly corrected."""
        assert self._run(mazenum=110, levelnum=10).level_flags_4 == 0x00

    # --- mazes 5-101, >103 tier: 0x30 wraps gated by TrapsLocal ---
    # (ROM 0x437C6-0x437D2). level%400 = 150 is in (103, 200].

    def test_wraps_added_on_103_tier_without_trapslocal(self):
        assert self._run(mazenum=50, levelnum=150).level_flags_4 & 0x30 == 0x30

    def test_wraps_gated_by_trapslocal_on_103_tier(self):
        state = self._run(mazenum=50, levelnum=150, flags=0x04)  # LFLAG4 bit 2 = TrapsLocal
        assert state.level_flags_4 & 0x30 == 0x00
        assert state.level_flags_4 & 0x04  # TrapsLocal itself preserved
