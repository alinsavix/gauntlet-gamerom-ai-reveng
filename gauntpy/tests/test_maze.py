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
from gauntpy.coords import POS_SHIFT, decode_hpos, decode_vpos_at_y, pack_slot
from gauntpy.state import GameState

from gex.constants import LFLAG3_EXIT_MOVES, MAX_MAZE_NUM
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

@requires_roms
def test_first_level_ordinary_food_heals_and_is_not_poison():
    from gauntpy.constants import GameMode, PlayerStatus
    from gauntpy.state import GameState
    from gauntpy.subsystems.players import (
        _POISONED_FOOD_PICTURE, player_tile_interact,
    )

    state = GameState(game_mode=GameMode.NORMAL, levelnum_current=1)
    assert gm.reset_and_load_level(state, 1, maze_number=0)
    slot = next(
        slot for slot in range(32, 1024)
        if state.mobs.obj_type(slot) == int(MazeObjIds.FOOD_INVULN)
    )
    assert state.mobs.picture[slot] != _POISONED_FOOD_PICTURE
    player = state.players[0]
    player.status = PlayerStatus.ALIVE_HERE
    player.health = 500

    assert player_tile_interact(state, slot, 0) == -1
    assert player.health == 600
    assert state.mobs.picture[slot] == 0


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


class _FixedRNG:
    def __init__(self, *values: int) -> None:
        self.values = list(values)

    def getrandom(self, bound: int) -> int:  # noqa: ARG002
        return self.values.pop(0)


class TestDeferredThiefPickups:
    def test_mugger_food_and_encoded_thief_loot_return_on_the_next_level(self):
        state = GameState()
        state.rng = _FixedRNG(0, 1)
        state.mugger_item_nextlevel = int(MazeObjIds.FOOD_INVULN)
        state.thief_item_nextlevel = (
            (4 * 500 << 6) | int(MazeObjIds.TREASURE_BAG)
        )

        slots = gm.place_deferred_thief_pickups(state)

        assert slots == [FIRST_PLAYABLE_SLOT, FIRST_PLAYABLE_SLOT + 1]
        assert state.mobs.obj_type(slots[0]) == int(MazeObjIds.FOOD_INVULN)
        assert state.mobs.obj_type(slots[1]) == int(MazeObjIds.TREASURE_BAG)
        assert state.special_bonus_score == 2000

    def test_secret_rooms_do_not_receive_deferred_loot(self):
        state = GameState(mazenum_current=0x73)
        state.rng = _FixedRNG(0)
        state.mugger_item_nextlevel = int(MazeObjIds.FOOD_INVULN)

        assert gm.place_deferred_thief_pickups(state) == []
        assert not any(state.mobs.picture)


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

    def test_floor_places_nothing_but_still_advances_the_cursor(self):
        """ROM 0x45E64: type 0 falls straight to the ``start + count`` exit."""
        state = GameState()
        assert gm.maze_place_object(state, 200, MazeObjIds.TILE_FLOOR, 4) == 204
        for slot in range(200, 204):
            assert not state.mobs.is_occupied(slot)

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


class TestMarkerPlacement:
    """Walls and floor markers are stamped straight into the five arrays --
    no ``mob_create``, so never members of the depth chain (doc/04 §5.4;
    ROM 0x46012-0x460B4 and 0x460EE-0x46100, neither of which calls 0x5DC58).
    """

    WALLS = [
        MazeObjIds.WALL_REGULAR, MazeObjIds.WALL_SECRET,
        MazeObjIds.WALL_DESTRUCTABLE, MazeObjIds.WALL_RANDOM,
        MazeObjIds.WALL_TRAPCYC1, MazeObjIds.WALL_TRAPCYC2, MazeObjIds.WALL_TRAPCYC3,
    ]

    @pytest.mark.parametrize("object_type", WALLS)
    def test_every_solid_wall_type_gets_the_0x8000_marker(self, object_type):
        """``players._slot_is_blocking`` recognises a wall by picture 0x8000
        alone, so a wall placed without it does not block. WALL_RANDOM is the
        one this catches: its ``mazeobj_base_picture_tbl`` entry is 0, and the
        ROM's marker branch is where the 0x8000 comes from.
        """
        state = GameState()
        slot = pack_slot(9, 9)
        gm.maze_place_object(state, slot, object_type, 1)

        assert state.mobs.picture[slot] == gm.WALL_MARKER_PICTURE
        assert state.mobs.obj_type(slot) == object_type

    @pytest.mark.parametrize("object_type", WALLS + [
        MazeObjIds.TILE_STUN, MazeObjIds.TILE_TRAP1, MazeObjIds.TILE_TRAP2,
        MazeObjIds.TILE_TRAP3, MazeObjIds.EXIT, MazeObjIds.EXITTO6,
        MazeObjIds.TRANSPORTER,
    ])
    def test_markers_never_join_the_depth_chain(self, object_type):
        state = GameState()
        slot = pack_slot(9, 9)
        gm.maze_place_object(state, slot, object_type, 1)

        assert state.mobs.is_occupied(slot), "the record is still written"
        assert not state.mobs.is_linked(slot)
        assert list(state.mobs.iter_chain()) == []

    def test_a_marker_unlinks_whatever_it_replaces(self):
        state = GameState()
        slot = pack_slot(9, 9)
        gm.maze_place_object(state, slot, MazeObjIds.MONST_GHOST, 1)
        assert state.mobs.is_linked(slot)

        gm.maze_place_object(state, slot, MazeObjIds.WALL_REGULAR, 1)
        assert not state.mobs.is_linked(slot)
        assert list(state.mobs.iter_chain()) == []

    def test_real_sprites_do_join_the_chain(self):
        state = GameState()
        slot = pack_slot(4, 4)
        gm.maze_place_object(state, slot, MazeObjIds.MONST_GRUNT, 1)
        assert list(state.mobs.iter_chain()) == [slot]


class TestPlacementGeometry:
    """The three geometry columns of the master parameter tables
    (0x5858C/0x5860C/0x5864C, doc/05 §5.2) reach the created MOB.
    """

    def test_monster_gets_its_palette_health_nibble(self):
        """doc/08: that low nibble is the MOB palette number *and*, for a
        monster, its health tier -- which is what ``shots``, ``monsters`` and
        ``potions`` all read back as remaining health. Placed at 0 they would
        every one of them start below their own kill threshold.
        """
        from gex.objparams import hsize_tier

        state = GameState()
        for object_type, expected in (
            (MazeObjIds.MONST_GHOST, 4), (MazeObjIds.MONST_DEMON, 8),
            (MazeObjIds.MONST_LOBBER, 11), (MazeObjIds.GEN_GHOST1, 5),
        ):
            slot = pack_slot(3, int(object_type) % 30 + 1)
            gm.maze_place_object(state, slot, object_type, 1)
            assert state.mobs.hpos[slot] & 0x0F == expected == hsize_tier(object_type)

    def test_monster_is_three_tiles_square_and_centred_in_its_cell(self):
        state = GameState()
        slot = pack_slot(5, 7)
        gm.maze_place_object(state, slot, MazeObjIds.MONST_GHOST, 1)

        x, _, palette = decode_hpos(state.mobs.hpos[slot])
        y, width, height = decode_vpos_at_y(state.mobs.vpos[slot])
        assert (width, height) == (3, 3)
        # 24 px sprite in a 16 px cell: half the overhang each side, which is
        # exactly the table's 512-unit hpos correction.
        assert x == 7 * 16 - 4
        assert y == 5 * 16
        assert palette == 4

    def test_pickup_is_two_tiles_square_and_fills_its_cell(self):
        state = GameState()
        slot = pack_slot(6, 7)
        gm.maze_place_object(state, slot, MazeObjIds.KEY, 1)

        x, _, _ = decode_hpos(state.mobs.hpos[slot])
        y, width, height = decode_vpos_at_y(state.mobs.vpos[slot])
        assert (width, height) == (2, 2)
        assert (x, y) == (7 * 16, 6 * 16)   # 16 px sprite, 16 px cell: no correction

    def test_the_correction_is_exactly_half_the_overhang(self):
        """Which is what pins the hpos units at whole pixels: the only nonzero
        correction in the table, 512, is 4 px, and every type carrying it is
        3 tiles (24 px) wide -- half the overhang in a 16 px cell."""
        from gex.objparams import hpos_correction, vpos_offset

        for object_type in range(64):
            correction = hpos_correction(object_type)
            width = ((vpos_offset(object_type) >> 3) & 0x07) + 1
            if correction and object_type not in gm._ROM_MARKER_TYPES:
                assert correction >> POS_SHIFT == (width * 8 - 16) // 2

    def test_markers_keep_the_plain_cell_origin(self):
        """Marker types never reach the correction table -- entry 0x3F holds
        8000, which would move a forcefield hub 62 px.
        """
        state = GameState()
        slot = pack_slot(8, 8)
        gm.maze_place_object(state, slot, MazeObjIds.WALL_REGULAR, 1)
        assert state.mobs.picture[slot] == gm.WALL_MARKER_PICTURE
        assert decode_hpos(state.mobs.hpos[slot])[0] == 8 * 16
        assert decode_vpos_at_y(state.mobs.vpos[slot])[0] == 8 * 16

        gm.maze_place_object(state, slot + 1, MazeObjIds.FORCEFIELDHUB, 1)
        assert state.mobs.picture[slot + 1] == gm.WALL_MARKER_PICTURE
        assert decode_hpos(state.mobs.hpos[slot + 1])[0] == 9 * 16

        gm.maze_place_object(state, slot + 2, MazeObjIds.TRANSPORTER, 1)
        assert state.mobs.picture[slot + 2] == gm.TILE_MARKER_PICTURE

    def test_a_marker_stores_the_roms_own_slot_shifted_eleven(self):
        """``maze_tile_write_at`` builds both words from ``slot << 11``: the H
        word is ``column * 16 << 7`` and the V word ``(31 - row) * 16 << 7``,
        counting up from the playfield floor."""
        state = GameState()
        for row, col in ((1, 0), (8, 8), (31, 31)):
            slot = pack_slot(row, col)
            gm.maze_place_object(state, slot, MazeObjIds.WALL_REGULAR, 1)
            assert state.mobs.hpos[slot] == col << 11
            assert state.mobs.vpos[slot] == (31 - row) << 11

    def test_a_placed_creature_keeps_the_native_low_fields(self):
        """The H correction lands in the position field and the packed size in
        the low field, so the two never disturb each other."""
        state = GameState()
        slot = pack_slot(5, 7)
        gm.maze_place_object(state, slot, MazeObjIds.MONST_GHOST, 1)
        hpos, vpos = state.mobs.hpos[slot], state.mobs.vpos[slot]
        assert hpos == ((7 * 16 - 4) << 7) | 4          # 0x200 correction, tier 4
        assert vpos == ((31 - 5) << 11) | 0x12          # 3x3 tiles, no V addend


class TestMazeMirroring:
    """LFLAG1 bits 2-3 (level-flags long bits 26-27) mirror placement, and
    ``maze_load_pickup_config`` re-randomizes them every level -- ROM
    0x45E9E-0x45FBC. Pure arithmetic; needs no ROMs.
    """

    def _state(self, *, flags1=0, flags4=0, levelnum=1):
        return GameState(
            game_mode=GameMode.NORMAL, levelnum_current=levelnum,
            level_flags=flags1, level_flags_4=flags4,
        )

    def test_no_flags_means_no_mirror(self):
        state = self._state()
        slot = pack_slot(5, 7)
        assert gm.mirror_slot(state, slot) == slot

    def test_horizontal_mirror_without_wrap_pins_column_zero(self):
        """base 0x20: ``col -> (-col) & 0x1F``, so the border column stays put."""
        state = self._state(flags1=0x04)
        assert gm.mirror_slot(state, pack_slot(5, 0)) == pack_slot(5, 0)
        assert gm.mirror_slot(state, pack_slot(5, 1)) == pack_slot(5, 31)
        assert gm.mirror_slot(state, pack_slot(5, 7)) == pack_slot(5, 25)

    def test_horizontal_mirror_with_wrap_flag_uses_base_0x1f(self):
        from gex.constants import LFLAG4_WRAP_H

        state = self._state(flags1=0x04, flags4=LFLAG4_WRAP_H)
        assert gm.mirror_slot(state, pack_slot(5, 0)) == pack_slot(5, 31)
        assert gm.mirror_slot(state, pack_slot(5, 31)) == pack_slot(5, 0)

    def test_vertical_mirror_reflects_rows_1_to_31(self):
        state = self._state(flags1=0x08)
        assert gm.mirror_slot(state, pack_slot(1, 7)) == pack_slot(31, 7)
        assert gm.mirror_slot(state, pack_slot(31, 7)) == pack_slot(1, 7)
        assert gm.mirror_slot(state, pack_slot(16, 7)) == pack_slot(16, 7)

    def test_both_mirrors_compose(self):
        state = self._state(flags1=0x0C)
        assert gm.mirror_slot(state, pack_slot(4, 3)) == pack_slot(28, 29)

    def test_every_mirror_is_an_involution_over_the_playable_grid(self):
        for flags1 in (0x04, 0x08, 0x0C):
            state = self._state(flags1=flags1)
            seen = set()
            for slot in range(FIRST_PLAYABLE_SLOT, 1024):
                image = gm.mirror_slot(state, slot)
                assert FIRST_PLAYABLE_SLOT <= image < 1024
                assert gm.mirror_slot(state, image) == slot
                seen.add(image)
            assert len(seen) == 1024 - FIRST_PLAYABLE_SLOT, "mirroring must be a bijection"

    def test_row_zero_fill_is_never_mirrored(self):
        """ROM 0x45FBC: slots below 0x20 bypass the mirror, so the reserved
        wall row cannot be flipped into the playfield."""
        state = self._state(flags1=0x0C)
        for slot in range(FIRST_PLAYABLE_SLOT):
            assert gm.mirror_slot(state, slot) == slot

    def test_level_9999_sentinel_bypasses_mirroring(self):
        state = self._state(flags1=0x0C, levelnum=gm.LEVEL_SENTINEL)
        assert gm.mirror_slot(state, pack_slot(5, 7)) == pack_slot(5, 7)

    def test_placement_lands_at_the_mirrored_slot(self):
        state = self._state(flags1=0x04)
        cursor = gm.maze_place_object(state, pack_slot(5, 7), MazeObjIds.KEY, 1)

        assert state.mobs.obj_type(pack_slot(5, 25)) == MazeObjIds.KEY
        assert not state.mobs.is_occupied(pack_slot(5, 7))
        assert cursor == pack_slot(5, 7) + 1, "the cursor is the unmirrored one"

    def test_mirrored_dragon_corrects_its_two_by_two_anchor(self):
        horizontal = self._state(flags1=0x04, levelnum=12)
        gm.maze_place_object(
            horizontal, pack_slot(5, 7), MazeObjIds.MONST_DRAGON, 1,
        )
        assert horizontal.mobs.obj_type(pack_slot(5, 24)) == int(
            MazeObjIds.MONST_DRAGON
        )

        vertical = self._state(flags1=0x08, levelnum=12)
        gm.maze_place_object(
            vertical, pack_slot(5, 7), MazeObjIds.MONST_DRAGON, 1,
        )
        assert vertical.mobs.obj_type(pack_slot(28, 7)) == int(
            MazeObjIds.MONST_DRAGON
        )

    def test_mirrored_object_is_positioned_at_its_new_cell(self):
        state = self._state(flags1=0x08)
        gm.maze_place_object(state, pack_slot(2, 9), MazeObjIds.KEY, 1)
        destination = pack_slot(30, 9)
        assert decode_hpos(state.mobs.hpos[destination])[0] == 9 * 16
        assert decode_vpos_at_y(state.mobs.vpos[destination])[0] == 30 * 16

    def test_mirror_maze_matches_what_placement_did(self):
        """``state.maze`` feeds the terrain renderer while the MobTable feeds
        collision -- if the two disagreed you would walk through drawn walls.
        """
        from gex.mazedecode import Maze

        state = self._state(flags1=0x0C)
        source = Maze(data={
            (7, 5): int(MazeObjIds.KEY),
            (3, 9): int(MazeObjIds.WALL_REGULAR),
            (20, 30): int(MazeObjIds.MONST_GHOST),
        })
        gm.place_decoded_objects(state, source)
        mirrored = gm.mirror_maze(state, source)

        assert len(mirrored.data) == len(source.data)
        for (col, row), object_type in mirrored.data.items():
            assert state.mobs.obj_type(pack_slot(row, col)) == object_type

    def test_mirror_maze_preserves_the_header_fields(self):
        from gex.mazedecode import Maze

        state = self._state(flags1=0x04)
        source = Maze(data={(7, 5): int(MazeObjIds.KEY)}, flags=0x1234_5678,
                      secret=3, wallpattern=6, floorpattern=2)
        mirrored = gm.mirror_maze(state, source)
        assert (mirrored.flags, mirrored.secret, mirrored.wallpattern,
                mirrored.floorpattern) == (0x1234_5678, 3, 6, 2)
        assert source.data == {(7, 5): int(MazeObjIds.KEY)}, "the source is not mutated"



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
        marker_types = gm._SOLID_WALL_MARKERS | gm._TILE_MARKERS
        for n in range(MAX_MAZE_NUM + 1):
            state = GameState()
            maze = gm.decode_maze(n)
            gm.place_decoded_objects(state, maze)
            gm.maze_place_object(state, 0, MazeObjIds.WALL_REGULAR, FIRST_PLAYABLE_SLOT)

            # place_decoded_objects skips row 0 (gex bakes it into Maze.data
            # as a decode convenience -- see its docstring) and the row-0 fill
            # is all markers, so the chain holds exactly the non-row-0 cells
            # that are real MOBs: walls and floor markers are stamped into the
            # arrays without ever being linked (doc/04 §5.4).
            expected = {
                pack_slot(row, col)
                for (col, row), object_type in maze.data.items()
                if row != 0 and object_type not in marker_types
            }
            assert set(state.mobs.iter_chain()) == expected, f"maze {n}"

    def test_the_chain_comes_out_in_ascending_slot_order(self):
        """``moblist_insert`` (0x5DCFE) orders by packed slot, so a freshly
        decoded maze walks front-to-back, row by row, column by column."""
        state = GameState()
        gm.place_decoded_objects(state, gm.decode_maze(0))
        chain = list(state.mobs.iter_chain())
        assert chain == sorted(chain)

    def test_placed_monsters_start_at_full_health(self):
        """Their health tier *is* the hpos palette nibble (doc/08), and
        ``shots``/``monsters``/``potions`` read it back as remaining health.
        """
        from gex.objparams import hsize_tier

        state = GameState()
        maze = gm.decode_maze(0)
        gm.place_decoded_objects(state, maze)

        monsters = [
            (pack_slot(row, col), t)
            for (col, row), t in maze.data.items()
            if row != 0 and 18 <= t <= 27
        ]
        assert monsters, "maze 0 should contain monsters"
        for slot, object_type in monsters:
            slot = gm.mirror_slot(state, slot)
            assert state.mobs.hpos[slot] & 0x0F == hsize_tier(object_type)

    def test_placed_monsters_start_facing_down(self):
        state = GameState()
        maze = gm.decode_maze(0)
        gm.place_decoded_objects(state, maze)

        monsters = [
            pack_slot(row, col)
            for (col, row), object_type in maze.data.items()
            if row != 0 and 18 <= object_type <= 27
        ]
        assert monsters
        assert all(state.mobs.state(slot) == 2 for slot in monsters)

    def test_super_sorcerer_starts_invisible_during_play(self):
        state = GameState(game_mode=GameMode.NORMAL)
        slot = pack_slot(8, 8)

        gm.maze_place_object(
            state, slot, int(MazeObjIds.MONST_SUPERSORC), 1,
        )

        assert state.mobs.picture[slot] == 0x1709
        assert state.mobs.hpos[slot] & 0x10

    def test_dragon_reserves_its_full_footprint_during_placement(self):
        state = GameState(game_mode=GameMode.NORMAL)
        state.levelnum_current = 12
        slot = pack_slot(10, 10)

        gm.maze_place_object(
            state, slot, int(MazeObjIds.MONST_DRAGON), 1,
        )

        expected = [slot, slot - 0x20, slot + 1, slot - 0x1F]
        assert state.dragon_seg_mob_ids == expected
        assert state.mobs.picture[slot] != 0x8002
        assert all(state.mobs.picture[cell] == 0x8002 for cell in expected[1:])
        assert all(
            state.mobs.obj_type(cell) == int(MazeObjIds.MONST_DRAGON)
            for cell in expected
        )

    def test_invulnerable_food_picture_is_one_of_the_three_rom_variants(self):
        """getrandom(3) into the three-word table at 0x58F20 (ROM 0x46150)."""
        variants = set(gm._food_invuln_pictures_read())
        assert len(variants) == 3

        state = GameState()
        seen = set()
        for i in range(60):
            slot = pack_slot(1 + i // 30, 1 + i % 30)
            gm.maze_place_object(state, slot, MazeObjIds.FOOD_INVULN, 1)
            seen.add(state.mobs.picture[slot])
        assert seen <= variants
        assert len(seen) > 1, "the variant must actually vary"



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
        """Every cell of the maze ``load_level`` stored is occupied.

        ``state.maze`` is the *mirrored* view -- the one the terrain renderer
        draws -- so checking against it also checks that placement and
        rendering agree about where the level is (see ``mirror_maze``). EXIT
        cells are skipped: ``exit_scan_level`` may remove the losing ones after
        placement (see ``test_mob_table_and_stored_maze_agree_cell_for_cell``).
        """
        state = GameState()
        gm.load_level(state, 2)  # maze 1
        for (col, row), object_type in state.maze.data.items():
            if object_type == MazeObjIds.EXIT:
                continue
            slot = pack_slot(row, col)
            assert state.mobs.is_occupied(slot), f"slot {slot} (col={col}, row={row}) not occupied"

    def test_mob_table_and_stored_maze_agree_cell_for_cell(self):
        """Placement and the stored (mirrored) maze describe the same level.

        ``exit_scan_level`` now routes losing exits through the shared floor
        replacement, so logical maze data, MOB state, and playfield VRAM remain
        synchronized after the Exit1of/ExitMoves pass.
        """
        for level in range(1, 6):
            state = GameState(game_mode=GameMode.NORMAL)
            gm.load_level(state, level)
            for (col, row), object_type in state.maze.data.items():
                if row == 0:
                    continue
                slot = pack_slot(row, col)
                assert state.mobs.obj_type(slot) == object_type, (
                    f"level {level} cell (col={col}, row={row})"
                )

    def test_a_normal_game_level_actually_gets_mirrored_sometimes(self):
        """The LFLAG1 bits-2-3 XOR is a getrandom(4) draw per level, so over a
        run of seeds every one of the four mirror combinations shows up. If
        placement ever stopped consulting them this would collapse to one.
        """
        from gauntpy.rng import GameRandom

        combinations = set()
        for seed in range(40):
            state = GameState(game_mode=GameMode.NORMAL, rng=GameRandom(seed=seed))
            gm.load_level(state, 3)
            flags = gm.level_flags_long(state)
            combinations.add(
                (bool(flags & gm.MIRROR_H_FLAG), bool(flags & gm.MIRROR_V_FLAG))
            )
        assert len(combinations) == 4

    def test_attract_mode_leaves_the_flags_exactly_as_authored(self):
        """game_mode < 0 skips the whole randomization block (ROM 0x4374C), so
        the demo plays a maze with the header's own flags -- mirror bits
        included -- and never re-rolls them."""
        state = GameState(game_mode=GameMode.DEMO)
        gm.load_level(state, 1)
        assert gm.level_flags_long(state) == gm.decode_maze(0).flags


@requires_roms
class TestLoadLevelExitScan:
    """``maze_new_level_setup`` step 10 rebuilds the exit table from the MOBs
    the decode pass just placed (ROM 0x43B3A-0x43B9A). It belongs on the common
    load path, not in each caller: every entry point that skipped it -- the
    runner's mid-level drop, most of all -- got a level whose ``exit_slots``
    were empty and whose ``exit_open_id`` was zero, which is precisely
    ``main_exit_move``'s first bail-out gate, so moving exits never moved.
    """

    #: LFLAG3 bit 6 within the standalone ``level_flags_3`` byte.
    EXIT_MOVES = LFLAG3_EXIT_MOVES >> 8

    def _first_maze_with_moving_exits(self) -> int:
        for number in range(MAX_MAZE_NUM + 1):
            maze = gm.decode_maze(number)
            if not ((maze.flags >> 8) & 0xFF) & self.EXIT_MOVES:
                continue
            if sum(1 for t in maze.data.values() if t == MazeObjIds.EXIT) > 1:
                return number
        raise AssertionError("no shipped maze has a multi-exit moving level")

    def test_load_level_fills_the_exit_table(self):
        state = GameState(game_mode=GameMode.NORMAL)
        gm.load_level(state, 1)

        assert state.exit_slots, "maze 0 has an exit; the scan must find it"
        for slot in state.exit_slots:
            assert state.mobs.obj_type(slot) == MazeObjIds.EXIT
            assert slot >= FIRST_PLAYABLE_SLOT, "the ROM's scan starts at slot 0x20"

    def test_exit_slots_are_the_mirrored_ones(self):
        """The scan reads the MobTable, so it picks up wherever mirroring put
        the exits -- a scan against the unmirrored decode would name cells that
        hold something else entirely."""
        state = GameState(game_mode=GameMode.NORMAL)
        gm.load_level(state, 1)
        decoded = {
            pack_slot(row, col)
            for (col, row), t in state.maze.data.items() if t == MazeObjIds.EXIT
        }
        assert set(state.exit_slots) <= decoded

    def test_a_moving_exit_level_comes_out_armed(self):
        number = self._first_maze_with_moving_exits()
        state = GameState(game_mode=GameMode.NORMAL)
        gm.load_level(state, 1, maze_number=number)

        assert state.level_flags_3 & self.EXIT_MOVES
        assert state.exit_open_id in state.exit_slots, (
            "one exit must be picked, or main_exit_move returns at its first gate"
        )
        assert state.exit_move_timer == 0x12C

    def test_the_open_exit_actually_moves_once_the_timer_runs_out(self):
        """The whole point of the scan: drive ``main_exit_move`` past its
        332-frame period and the open exit is somewhere else."""
        from gauntpy.subsystems.exits import main_exit_move

        number = self._first_maze_with_moving_exits()
        state = GameState(game_mode=GameMode.NORMAL)
        gm.load_level(state, 1, maze_number=number)
        state.level_players_active = 1

        start = state.exit_open_id
        for _ in range(400):
            main_exit_move(state)

        assert state.exit_open_id != start
        assert state.exit_open_id in state.exit_slots

    def test_a_second_scan_does_not_disturb_the_pick(self):
        """WP-15's own transition path still calls ``exit_scan_level`` right
        after reloading, so the two calls now meet. The scan's guard has to
        recognise an already-picked table -- otherwise the re-scan would see
        only the surviving exits and disarm the level."""
        from gauntpy.subsystems.exits import exit_scan_level

        number = self._first_maze_with_moving_exits()
        state = GameState(game_mode=GameMode.NORMAL)
        gm.load_level(state, 1, maze_number=number)
        before = (list(state.exit_slots), state.exit_open_id, state.exit_move_timer)

        exit_scan_level(state)

        assert (list(state.exit_slots), state.exit_open_id, state.exit_move_timer) == before

    def test_a_reload_rescans_for_the_new_level(self):
        """A level change must not leave the previous maze's exits behind."""
        state = GameState(game_mode=GameMode.NORMAL)
        assert gm.reset_and_load_level(state, 1)
        first = list(state.exit_slots)

        assert gm.reset_and_load_level(state, 2)
        for slot in state.exit_slots:
            assert state.mobs.obj_type(slot) == MazeObjIds.EXIT
        assert state.exit_slots != first or first == []


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
