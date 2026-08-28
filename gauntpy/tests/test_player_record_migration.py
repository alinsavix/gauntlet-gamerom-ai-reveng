"""Live player MOB records migrate by maze cell, exactly as a monster's does.

``player_try_move_core``'s tail (0x424CA-0x42526) computes the cell the hero's
new H/V words name, and when it differs from ``active_mob_ids[player]`` and the
cell is free it calls ``move_mob_slot`` (0x5DE0A) to relocate the record.
"identity is location" therefore holds for heroes too, and every consumer that
used to need a port-only overlay -- shot probes, monster contact, the renderer's
band window -- simply reads the cell.
"""

from __future__ import annotations

from gauntpy.constants import (
    FIRST_PLAYABLE_SLOT,
    SLOT_EXIT_ANIMS,
    GameMode,
    MazeObjIds,
    PlayerStatus,
)
from gauntpy.coords import (
    encode_hpos,
    encode_vpos_at_y,
    hpos_x,
    mob_cell_of,
    native_v,
    pack_slot,
    vpos_y,
)
from gauntpy.render import mobs as render_mobs
from gauntpy.state import GameState
from gauntpy.subsystems import players as gp
from gauntpy.subsystems.input import JOY_DOWN, JOY_IDLE, JOY_RIGHT
from gauntpy.subsystems.players import migrate_player_record, player_try_move

_HERO_PICTURE = 0x1E0D


def _spawn(state: GameState, index: int, slot: int) -> object:
    """A live hero record in ``slot``, built exactly as player_start_inner does."""
    player = state.players[index]
    player.status = int(PlayerStatus.ALIVE_HERE)
    player.health = 1000
    player.mob_slot = slot
    row, col = slot >> 5, slot & 0x1F
    state.mobs.create(
        slot,
        tile=_HERO_PICTURE,
        hpos=encode_hpos(col * 16 - 4, (index + 0x0C) & 0x0F),
        vpos=encode_vpos_at_y(row * 16, 3, 3),
        obj_type=int(MazeObjIds.PLAYERSTART),
        state=index,
    )
    state.player_tile_or_tport_dest[index] = slot
    state.player_in_maze[index] = 1
    # These tests are about the record, not the independent offscreen gate.
    state.level_flags_4 |= 0x80
    return player


def _walk(state: GameState, index: int, delta: int, frames: int = 24) -> None:
    """Step the hero until its record leaves the cell it started in."""
    start = state.players[index].mob_slot
    for _ in range(frames):
        state.movement_type = 2
        player_try_move(state, index, delta, 0)
        if state.players[index].mob_slot != start:
            return


# ---------------------------------------------------------------------------
# The move itself
# ---------------------------------------------------------------------------

class TestCrossingACellMovesTheRecord:
    def test_walking_right_lands_in_the_next_packed_slot(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)

        _walk(state, 0, JOY_RIGHT)

        assert player.mob_slot == start + 1
        assert state.mobs.picture[start + 1] == _HERO_PICTURE
        assert state.mobs.obj_type(start + 1) == int(MazeObjIds.PLAYERSTART)

    def test_walking_down_lands_one_row_on(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)

        _walk(state, 0, JOY_DOWN)

        assert player.mob_slot == start + 0x20
        assert state.mobs.picture[start + 0x20] == _HERO_PICTURE

    def test_the_vacated_cell_is_cleared(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)

        _walk(state, 0, JOY_RIGHT)

        assert player.mob_slot != start
        assert state.mobs.picture[start] == 0
        assert state.mobs.hpos[start] == 0
        assert state.mobs.vpos[start] == 0
        assert state.mobs.link[start] == 0
        assert state.mobs.state_link[start] == 0
        assert not state.mobs.is_occupied(start)

    def test_the_handover_row_is_the_roms_own_bias(self):
        """0x424CA adds 0x400 to V *upward*: the row changes at ``y % 16 == 9``."""
        for offset, expected_row in ((8, 10), (9, 11)):
            hpos = encode_hpos(10 * 16 - 4)
            vpos = encode_vpos_at_y(10 * 16 + offset, 3, 3)
            assert mob_cell_of(hpos, vpos) >> 5 == expected_row


class TestTheRecordSurvivesTheMove:
    def test_the_live_low_fields_are_carried_over(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 1, start)
        state.mobs.hpos[start] |= 0x30          # both software flag bits
        low_h = state.mobs.hpos[start] & 0x7F
        low_v = state.mobs.vpos[start] & 0x7F

        _walk(state, 1, JOY_RIGHT)

        assert player.mob_slot != start
        assert state.mobs.hpos[player.mob_slot] & 0x7F == low_h
        assert state.mobs.vpos[player.mob_slot] & 0x7F == low_v
        assert low_v == 0x12, "a 3x3 hero's packed size"

    def test_the_state_word_still_names_the_player(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 2, start)

        _walk(state, 2, JOY_RIGHT)

        assert player.mob_slot != start
        assert state.mobs.state(player.mob_slot) == 2
        assert state.mobs.hpos[player.mob_slot] & 0x0F == 0x0C + 2

    def test_the_position_is_the_one_the_move_produced(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)

        _walk(state, 0, JOY_RIGHT, frames=10)

        x = hpos_x(state.mobs.hpos[player.mob_slot])
        assert x > 10 * 16 - 4, "the record carried the live pixels with it"
        assert mob_cell_of(
            state.mobs.hpos[player.mob_slot],
            state.mobs.vpos[player.mob_slot],
        ) == player.mob_slot


class TestTheDepthChainStaysValid:
    def test_the_chain_is_repaired_and_stays_sorted(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)
        for slot in (pack_slot(4, 4), pack_slot(20, 20)):
            state.mobs.create(slot, tile=0x100, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.MONST_GRUNT))

        _walk(state, 0, JOY_DOWN)

        chain = list(state.mobs.iter_chain())
        assert player.mob_slot in chain
        assert start not in chain
        assert chain == sorted(chain), "packed slot order is depth order"
        assert len(set(chain)) == len(chain)
        assert state.mobs.is_linked(player.mob_slot)
        assert not state.mobs.is_linked(start)

    def test_the_slip_band_follows_the_record(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)

        _walk(state, 0, JOY_DOWN)

        band = state.mobs.band_of(player.mob_slot)
        assert band == (player.mob_slot >> 5) * 2
        assert state.mobs.slip_heads[band] == player.mob_slot


class TestMigrationRefusesTheCellsItMust:
    def test_an_occupied_destination_holds_the_record_back(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)
        blocker = start + 1
        state.mobs.create(blocker, tile=0x2222, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.MONST_DEATH))

        state.mobs.hpos[start] = encode_hpos(11 * 16 - 4, 0x0C)
        assert not migrate_player_record(state, 0)
        assert player.mob_slot == start
        assert state.mobs.picture[blocker] == 0x2222

    def test_the_managed_low_slots_are_never_a_destination(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(1, 4)
        player = _spawn(state, 0, start)
        # Row 0 shares the MOB table with the reserved shot/effect slots.
        state.mobs.vpos[start] = encode_vpos_at_y(0, 3, 3)
        assert mob_cell_of(
            state.mobs.hpos[start], state.mobs.vpos[start],
        ) < FIRST_PLAYABLE_SLOT

        assert not migrate_player_record(state, 0)
        assert player.mob_slot == start

    def test_an_exit_animation_slot_is_left_alone(self):
        state = GameState(game_mode=GameMode.NORMAL)
        player = state.players[0]
        player.status = int(PlayerStatus.EXITING)
        player.mob_slot = SLOT_EXIT_ANIMS[0]
        state.mobs.picture[player.mob_slot] = _HERO_PICTURE
        state.mobs.hpos[player.mob_slot] = encode_hpos(10 * 16 - 4, 0x0C)
        state.mobs.vpos[player.mob_slot] = encode_vpos_at_y(10 * 16, 3, 3)

        assert not migrate_player_record(state, 0)
        assert player.mob_slot == SLOT_EXIT_ANIMS[0]


class TestTwoPlayersDoNotOverwriteOneAnother:
    def test_a_hero_cannot_migrate_onto_another_heros_record(self):
        state = GameState(game_mode=GameMode.NORMAL)
        first = pack_slot(10, 11)
        second = pack_slot(10, 10)
        held = _spawn(state, 0, first)
        mover = _spawn(state, 1, second)

        _walk(state, 1, JOY_RIGHT)

        assert held.mob_slot == first
        assert state.mobs.state(first) == 0
        assert mover.mob_slot == second
        assert state.mobs.state(second) == 1
        assert state.mobs.picture[first] == _HERO_PICTURE
        assert state.mobs.picture[second] == _HERO_PICTURE

    def test_both_records_keep_their_own_palette_and_identity(self):
        state = GameState(game_mode=GameMode.NORMAL)
        one = _spawn(state, 0, pack_slot(6, 6))
        two = _spawn(state, 1, pack_slot(12, 12))

        _walk(state, 0, JOY_RIGHT)
        _walk(state, 1, JOY_DOWN)

        assert one.mob_slot == pack_slot(6, 7)
        assert two.mob_slot == pack_slot(13, 12)
        assert state.mobs.state(one.mob_slot) == 0
        assert state.mobs.state(two.mob_slot) == 1
        assert state.mobs.hpos[one.mob_slot] & 0x0F == 0x0C
        assert state.mobs.hpos[two.mob_slot] & 0x0F == 0x0D


# ---------------------------------------------------------------------------
# The consumers that used to need an overlay
# ---------------------------------------------------------------------------

class TestShotsFindTheMigratedRecord:
    def test_a_monster_shot_hits_the_hero_in_its_new_cell(self):
        from gauntpy.subsystems.shots import resolve_shot_hit, shot_mob_collision

        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 1, start)
        _walk(state, 1, JOY_RIGHT)
        cell = player.mob_slot
        assert cell != start

        shot = 5                                   # demon channel 4
        state.mobs.picture[shot] = 1
        state.mobs.hpos[shot] = state.mobs.hpos[cell] & 0xFF80
        state.mobs.vpos[shot] = state.mobs.vpos[cell] & 0xFF80
        state.shot_direction[4] = 2

        assert shot_mob_collision(state, cell, 4) == cell
        before = player.health
        resolve_shot_hit(state, cell, 4)
        assert player.health < before, "damage is charged to the record's owner"

    def test_the_probe_needs_no_player_overlay(self):
        from gauntpy.subsystems import shots

        state = GameState(game_mode=GameMode.NORMAL)
        record_slot = pack_slot(10, 10)
        empty_slot = pack_slot(10, 11)
        _spawn(state, 0, record_slot)
        # Recreate the obsolete fixed-record shape: metadata remains in one slot
        # while its pixels name another. The candidate probe must inspect only
        # the candidate's physical record, not synthesize a player overlay.
        state.mobs.hpos[record_slot] = encode_hpos(11 * 16 - 4, 0x0C)

        assert shots.shot_collision_candidate_core(
            state, empty_slot * 2, 4, 1, 1, 0, 0, -1, False,
        ) is None


class TestMonsterContactFindsTheMigratedRecord:
    def test_a_creature_cannot_step_into_the_cell_the_hero_owns(self):
        from gauntpy.subsystems.monsters import _cell_player_index

        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)
        _walk(state, 0, JOY_DOWN)

        assert _cell_player_index(state, player.mob_slot) == 0
        assert _cell_player_index(state, start) is None
        assert state.mobs.is_occupied(player.mob_slot)

    def test_the_fixed_record_fallback_is_gone(self):
        from gauntpy.subsystems import monsters

        assert not hasattr(monsters, "_player_in_cell")


class TestTheRendererUsesTheCurrentBand:
    def test_the_hero_is_found_through_its_own_band(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(2, 8)
        player = _spawn(state, 0, start)
        state.mobs.vpos[start] = encode_vpos_at_y(320, 3, 3)
        migrate_player_record(state, 0)
        assert player.mob_slot == pack_slot(20, 8)

        visible = [
            info.slot for info in render_mobs.iter_visible_mobs(
                state, 0, 272, 336, 240,
            )
        ]
        assert player.mob_slot in visible

        first, last = render_mobs._chain_band_window(state, 272, 240)
        assert first <= state.mobs.band_of(player.mob_slot) <= last

    def test_the_untracked_band_workaround_is_gone(self):
        assert not hasattr(render_mobs, "_untracked_bands")


class TestCameraAndTilePositionAgree:
    def test_the_tracking_arrays_name_the_record(self):
        from gauntpy.subsystems.camera import _camera_target

        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)
        state.level_players_active = 1
        state.player_input_raw[0] = 0xFFFF & ~JOY_RIGHT

        for _ in range(24):
            gp.main_move_players(state)
            if player.mob_slot != start:
                break

        assert player.mob_slot != start
        assert state.player_tile_or_tport_dest[0] == player.mob_slot
        assert state.player_in_maze[0] == 1

        target = _camera_target(state, include_camera=False)
        assert target == (
            hpos_x(state.mobs.hpos[player.mob_slot]) - 0x68,
            vpos_y(state.mobs.vpos[player.mob_slot]) - 0x74,
        )


class TestTheTransporterStillRelocatesTheRecord:
    def test_the_move_milestone_migrates_the_record(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        landing = pack_slot(20, 20)
        player = _spawn(state, 0, start)
        state.player_tile_or_tport_dest[0] = landing

        gp.tport_player_move(state, 0)

        assert player.mob_slot == landing
        assert state.mobs.picture[landing] == _HERO_PICTURE
        assert state.mobs.state(landing) == 0
        assert state.mobs.picture[start] == 0
        assert hpos_x(state.mobs.hpos[landing]) == 20 * 16 - 4
        assert vpos_y(state.mobs.vpos[landing]) == 20 * 16
        assert landing in list(state.mobs.iter_chain())

    def test_a_treasure_at_the_landing_is_collected_and_replaced(self):
        state = GameState(game_mode=GameMode.NORMAL, level_players_active=1)
        start = pack_slot(10, 10)
        landing = pack_slot(20, 20)
        player = _spawn(state, 0, start)
        player.bonusmult = 1
        state.mobs.create(landing, tile=0x3333, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        state.player_tile_or_tport_dest[0] = landing

        gp.tport_player_move(state, 0)

        assert player.mob_slot == landing
        assert state.mobs.obj_type(landing) == int(MazeObjIds.PLAYERSTART)
        assert state.mobs.picture[landing] == _HERO_PICTURE
        assert state.player_treascount[0] == 1
        assert player.score == 100

    def test_a_monster_at_the_landing_is_replaced(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        landing = pack_slot(20, 20)
        player = _spawn(state, 0, start)
        state.mobs.create(
            landing, tile=0x3333, hpos=encode_hpos(20 * 16),
            vpos=encode_vpos_at_y(20 * 16, 3, 3),
            obj_type=int(MazeObjIds.MONST_DEMON),
        )
        state.player_tile_or_tport_dest[0] = landing

        gp.tport_player_move(state, 0)

        assert player.mob_slot == landing
        assert state.mobs.obj_type(landing) == int(MazeObjIds.PLAYERSTART)
        assert state.mobs.picture[landing] == _HERO_PICTURE
        assert state.mobs.picture[start] == 0

    def test_a_thief_at_the_landing_is_removed_and_drops_its_loot(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        landing = pack_slot(20, 20)
        player = _spawn(state, 0, start)
        state.thief_mob_slot = landing
        state.thief_current_pos = landing
        state.thief_victim = 0
        state.thief_item_carried = int(MazeObjIds.KEY)
        state.mobs.create(
            landing, tile=0x0E63, hpos=encode_hpos(20 * 16),
            vpos=encode_vpos_at_y(20 * 16, 3, 3),
            obj_type=int(MazeObjIds.PLAYERSTART),
        )
        state.player_tile_or_tport_dest[0] = landing

        gp.tport_player_move(state, 0)

        assert state.thief_mob_slot == 0
        assert player.keysnum == 1
        assert player.mob_slot == landing
        assert state.mobs.obj_type(landing) == int(MazeObjIds.PLAYERSTART)

    def test_a_newly_blocked_landing_keeps_the_player_at_the_source(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        landing = pack_slot(20, 20)
        player = _spawn(state, 0, start)
        state.mobs.create(
            landing, tile=0x8000, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.WALL_REGULAR),
        )
        state.player_tile_or_tport_dest[0] = landing

        gp.tport_player_move(state, 0)

        assert player.mob_slot == start
        assert state.mobs.picture[landing] == 0x8000
        assert state.player_tile_or_tport_dest[0] == start

    def test_aborted_transport_entry_restores_the_player_move(self):
        state = GameState(game_mode=GameMode.NORMAL, level_players_active=1)
        start = pack_slot(5, 4)
        source = pack_slot(5, 5)
        destination = pack_slot(5, 9)
        player = _spawn(state, 0, start)
        state.mobs.hpos[start] = encode_hpos(67, 0x0C)
        state.mobs.create(
            source, tile=1, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.TRANSPORTER),
        )
        state.mobs.create(
            destination, tile=1, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.TRANSPORTER),
        )
        for row in range(4, 7):
            for col in range(8, 11):
                slot = pack_slot(row, col)
                if slot == destination:
                    continue
                state.mobs.create(
                    slot, tile=0x8000, hpos=0, vpos=0,
                    obj_type=int(MazeObjIds.WALL_REGULAR),
                )
        before = (state.mobs.hpos[start], state.mobs.vpos[start])
        state.thief_victim = 0
        state.thief_victim_pos = start
        route_before = list(state.path_direction_grid)
        state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT

        gp.main_move_players(state)

        assert state.player_tport_phase[0] < 0
        assert player.mob_slot == start
        assert (state.mobs.hpos[start], state.mobs.vpos[start]) == before
        assert state.player_tile_or_tport_dest[0] == start
        assert state.thief_victim_pos == start
        assert state.path_direction_grid == bytearray(route_before)


class TestTheExitStillTakesTheRecordOutOfTheMaze:
    def test_reaching_an_exit_vacates_the_cell_and_claims_the_anim_slot(self):
        from gauntpy.subsystems.exits import player_exit_sequence

        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)
        state.level_players_active = 1
        exit_slot = pack_slot(10, 11)
        state.mobs.create(
            exit_slot, tile=0x4444,
            hpos=encode_hpos(11 * 16), vpos=encode_vpos_at_y(10 * 16),
            obj_type=int(MazeObjIds.EXIT),
        )

        player_exit_sequence(state, 0, exit_slot, int(MazeObjIds.EXIT))

        assert player.mob_slot == SLOT_EXIT_ANIMS[0]
        assert state.mobs.picture[start] == 0
        assert start not in list(state.mobs.iter_chain())
        assert state.mobs.picture[SLOT_EXIT_ANIMS[0]] == _HERO_PICTURE


class TestTilePickupsStillFireOnTheEntryEdge:
    def test_a_consumed_tile_lets_the_record_follow_the_hero_in(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(10, 10)
        player = _spawn(state, 0, start)
        food = start + 1
        state.mobs.create(
            food, tile=gp._WHOLESOME_FOOD_PICTURE,
            hpos=encode_hpos(11 * 16), vpos=encode_vpos_at_y(10 * 16),
            obj_type=int(MazeObjIds.FOOD_DESTRUCTABLE),
        )
        state.player_input_raw[0] = 0xFFFF & ~JOY_RIGHT
        before = player.health

        for _ in range(24):
            gp.main_move_players(state)
            if player.mob_slot != start:
                break

        assert player.health > before, "the food was eaten"
        assert player.mob_slot == food, "and the record moved in behind it"
        assert state.mobs.state(food) == 0
        assert state.mobs.picture[start] == 0


class TestForcefieldContactUsesTheRecordCell:
    def test_the_beam_is_queried_at_the_cell_the_record_occupies(self):
        state = GameState(game_mode=GameMode.NORMAL)
        start = pack_slot(5, 4)
        player = _spawn(state, 0, start)
        state.forcefield_color = 1
        # horizontal, length 4, hub at (5,3) -- doc/04 §7.3.
        state.ff_segment_table = [0x8000 | (3 << 10) | pack_slot(5, 3)]
        state.forcefield_segments_ready = True

        assert gp._check_forcefield_collision(state, 0)

        state.mobs.hpos[start] = encode_hpos(20 * 16 - 4, 0x0C)
        migrate_player_record(state, 0)
        assert player.mob_slot == pack_slot(5, 20)
        assert not gp._check_forcefield_collision(state, 0)


class TestSpawnPlacesTheRecordInItsOwnCell:
    def test_a_later_join_takes_an_empty_cell_beside_the_first_hero(self):
        state = GameState(game_mode=GameMode.NORMAL)
        state.maze = object()
        first = pack_slot(10, 10)
        _spawn(state, 0, first)
        state.level_players_active = 1

        assert gp.player_start_inner(state, 1) == -1
        joined = state.players[1].mob_slot
        assert joined in (first - 1, first + 1, first - 0x20, first + 0x20)
        assert state.mobs.state(joined) == 1
        assert state.mobs.obj_type(joined) == int(MazeObjIds.PLAYERSTART)
        assert state.player_tile_or_tport_dest[1] == joined
        assert mob_cell_of(
            state.mobs.hpos[joined], state.mobs.vpos[joined],
        ) == joined


def test_a_record_that_never_leaves_its_cell_is_not_touched():
    state = GameState(game_mode=GameMode.NORMAL)
    start = pack_slot(10, 10)
    player = _spawn(state, 0, start)
    before = (
        state.mobs.picture[start], state.mobs.hpos[start],
        state.mobs.vpos[start], state.mobs.link[start],
        state.mobs.state_link[start],
    )

    assert not migrate_player_record(state, 0)
    assert player.mob_slot == start
    assert (
        state.mobs.picture[start], state.mobs.hpos[start],
        state.mobs.vpos[start], state.mobs.link[start],
        state.mobs.state_link[start],
    ) == before


def test_the_record_cell_matches_the_creature_rule():
    """One rule serves both movers -- 0x41358 for a monster, 0x424CA for a hero."""
    from gauntpy.subsystems.monsters import _destination_cell

    for row in (0, 7, 31):
        for col in (0, 13, 31):
            for dy in (0, 8, 9, 15):
                hpos = encode_hpos(col * 16 - 4)
                vpos = encode_vpos_at_y(row * 16 + dy, 3, 3)
                assert mob_cell_of(hpos, vpos) == _destination_cell(hpos, vpos)


def test_native_v_round_trip_is_what_the_bias_is_measured_against():
    assert native_v(0) == 496
    assert vpos_y(encode_vpos_at_y(160, 3, 3)) == 160
