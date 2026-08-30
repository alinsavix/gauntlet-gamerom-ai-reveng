"""WP-8: monsters and generators.

Acceptance criteria from PLAN.md §6 WP-8:
1. 60+ monsters simulate without crashing.
2. Generators respect the probability table for every difficulty x player-count
   combination (frame_overflow forces probability to zero).
3. Slow-motion halves the monster update rate without touching players.
4. Each of the four special cases (Sorcerer, Acid, IT, Lobber) follows its
   documented branch.

Four ROM facts shape every test below:

* the pass runs on a *cadence word* that is ``frame_counter`` doubled unless
  slow-motion is running (0x40EEC), so a stagger of ``N`` is reached at
  ``frame_counter = N // 2``;
* ``main_move_monsters`` walks only the arc of the depth chain between two
  camera-derived SLIP buckets, and the culling rectangle trims what is left
  (0x49076/0x40FF6), so a test that wants a monster to act has to point the
  camera at it;
* the *idle* state is the normal one -- the mover runs from it every frame.
  The moving flag marks a creature that is animating a step or recovering from
  a blow, and the mover clears it again (0x41348);
* movement is by ray-marched *axis components* (0x4126A), so a diagonal walker
  slides along a wall instead of stopping dead.
"""

from __future__ import annotations

from gauntpy.constants import (
    Character,
    GENERATOR_TYPES,
    SLOT_DEMON_SHOTS,
    SLOT_LOBBER_SHOTS,
    GameMode,
    MazeObjIds,
    PlayerPower,
    PlayerStatus,
)
from gauntpy.coords import (
    decode_hpos,
    decode_vpos_at_y,
    encode_hpos,
    encode_vpos_at_y,
    hpos_x,
    native_v,
    pack_slot,
    vpos_y,
)
from gauntpy.state import GameState
from gauntpy.subsystems.exits import (
    TRICK_NOUSEINVUL,
    secret_check_winner,
    secret_trick_check,
)
from gauntpy.subsystems.monsters import (
    _DEMON_SHOT_HPOS_LOW,
    _GEN_ATTRACT_GHOST_FAMILIES,
    _GEN_ATTRACT_START_GHOST,
    _GEN_ATTRACT_START_OTHER,
    _GENERATOR_CELL_DX,
    _GENERATOR_SPAWN_DIRECTION,
    _GENERATOR_CELL_DY,
    _GENERATOR_SPAWN,
    _GENERATOR_TIER_PENALTY,
    _HPOS_FLAG_ATTACK,
    _HPOS_FLAG_MOVING,
    _LOBBER_SHOT_HPOS_LOW,
    _LOBBER_SHOT_SPAWN_H,
    _LOBBER_SHOT_SPAWN_V,
    _MAZEOBJ_VSIZE,
    _MONSTER_ODDANGLE_TABLE,
    _MONSTER_SHOT_SPAWN_H,
    _MONSTER_SHOT_SPAWN_V,
    _MONSTER_SPEED_BASE,
    _MONSTER_SPEED_FAST,
    _MONSTER_WALK_PICTURES,
    _MONSTER_IDLE_ANIMS,
    _MONSTER_MOVING_ANIMS,
    _SPAWN_CANDIDATE_COLUMN_DELTA,
    _SPAWN_CANDIDATE_ROW_DELTA,
    _MONSTER_SHOOT_AXIS_THRESHOLDS,
    _SHOT_COOLDOWN,
    _SHOT_VPOS_LOW,
    _MONSTER_SPAWN_PROBABILITY_TABLE,
    _aim_direction,
    _destination_cell,
    _dispatch_monster,
    _handle_generator,
    _in_cull_rect,
    _lobber_lead,
    _monster_move_engine,
    _monster_animation_index,
    _monster_speed,
    _oddangle_override,
    _probe_phase,
    monster_update_anim_tile,
    monster_shooter_in_view,
    _spawn_probability,
    _supersorc_dispatch,
    supersorc_place,
    tile_on_screen_d4,
    _update_cull_rect,
    _walk_band_head,
    GENERATOR_RETRY_RELOAD,
    generator_candidate_slot,
    handle_generate,
    main_move_monsters,
    monster_create_shot,
    monster_find_and_shoot,
    player_hurt_speech_timer,
    monster_playerhit,
    monster_walk_picture,
    monsters_everything,
    tile_occupancy_test,
)
from gauntpy.subsystems.shots import (
    _MONSTER_PROJECTILE_PICTURE_TBL,
    _PROJECTILE_PICTURE_TBL,
    _SHOT_COUNTER_RELOAD,
    main_handle_shots,
    shot_picture,
)

# Same skip condition test_assets.py uses: only the ROM byte-match and the
# renderer-resolvability checks need the real ROMs.
from gex.roms import _rom_dir, TILE_ROMS  # noqa: E402

import pytest  # noqa: E402

_ROM_PATH = _rom_dir()
requires_roms = pytest.mark.skipif(
    not (_ROM_PATH.is_dir() and (_ROM_PATH / TILE_ROMS[0][0]).is_file()),
    reason=f"ROM files not available at {_ROM_PATH}",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FixedRNG:
    """Replacement for GameRandom returning a preset sequence (then a default)."""

    def __init__(self, *values: int, default: int = 0) -> None:
        self._queue = list(values)
        self._default = default
        self.calls = 0

    def getrandom(self, bound: int) -> int:  # noqa: ARG002
        self.calls += 1
        return self._queue.pop(0) if self._queue else self._default

    random_word = getrandom


def _place_monster(state: GameState, slot: int, obj_type: int,
                   direction: int = 0, health: int = 4,
                   moving: bool = False) -> None:
    """Create a monster MOB at a maze slot, centred in its cell."""
    row, col = slot >> 5, slot & 0x1F
    x, y = col * 16, row * 16
    flags = _HPOS_FLAG_MOVING if moving else 0
    state.mobs.create(
        slot,
        tile=1,
        hpos=encode_hpos(x, palette=health, flags=flags),
        vpos=encode_vpos_at_y(y),
        obj_type=obj_type,
        state=direction & 0x07,
    )


def _place_wall(state: GameState, slot: int) -> None:
    row, col = slot >> 5, slot & 0x1F
    state.mobs.create(slot, tile=1, hpos=encode_hpos(col * 16),
                      vpos=encode_vpos_at_y(row * 16),
                      obj_type=int(MazeObjIds.WALL_REGULAR), state=0)


def _place_player(state: GameState, index: int, slot: int) -> None:
    """A hero MOB: a real record with a picture and a hero palette nibble."""
    p = state.players[index]
    p.status = PlayerStatus.ALIVE_HERE
    p.mob_slot = slot
    row, col = slot >> 5, slot & 0x1F
    state.mobs.create(slot, tile=0x100,
                      hpos=encode_hpos(col * 16, palette=0x0C + index),
                      vpos=encode_vpos_at_y(row * 16),
                      obj_type=int(MazeObjIds.PLAYERSTART), state=0)
    state.level_players_active = max(state.level_players_active, index + 1)
    state.player_in_maze[index] = 1


def _camera_on(state: GameState, slot: int) -> None:
    """Point the camera at ``slot`` the way ``camera.snap_camera`` would, so the
    culling rectangle (255 x 263 px around the midpoint) contains it and the
    chain walk covers its band."""
    x, y = (slot & 0x1F) * 16, (slot >> 5) * 16
    state.scroll_x = x - 0x68            # midX = scroll_x + 0x68
    state.scroll_y = y - 0x74            # midY = scroll_y + 0x74


def _arena(state: GameState, focus_slot: int, players: int = 1) -> None:
    """The minimum a monster needs to run: players on the level and a camera."""
    state.game_mode = 0                  # GameMode.NORMAL
    state.level_players_active = max(state.level_players_active, players)
    _camera_on(state, focus_slot)
    _update_cull_rect(state)


def _stagger_frame(slot: int) -> int:
    """``frame_counter`` at which ``slot``'s idle/generator stagger fires.

    The ROM compares ``((slot*2 | 2) ^ frame_word) & 0x1E`` against zero, and
    ``frame_word`` is ``frame_counter * 2`` outside slow-motion.
    """
    return ((((slot * 2) | 2) & 0x1E) // 2) & 0xF


def _walk_frames(state: GameState, count: int) -> None:
    for _ in range(count):
        state.frame_counter = (state.frame_counter + 1) & 0xFFFF
        main_move_monsters(state)


def _monster_slot(state: GameState, obj_type: int) -> int | None:
    for slot in range(1024):
        if state.mobs.obj_type(slot) == int(obj_type):
            return slot
    return None


# ---------------------------------------------------------------------------
# Speed (I-15)
# ---------------------------------------------------------------------------

class TestMonsterSpeedPerFamily:
    """Each LFLAG2 fast bit speeds up only its own family (I-15)."""

    @pytest.mark.parametrize(("bit", "family"), (
        (0x01, MazeObjIds.MONST_GHOST),
        (0x02, MazeObjIds.MONST_GRUNT),
        (0x04, MazeObjIds.MONST_DEMON),
        (0x08, MazeObjIds.MONST_LOBBER),
        (0x10, MazeObjIds.MONST_SORC),
        (0x20, MazeObjIds.MONST_AUX_GRUNT),
        (0x40, MazeObjIds.MONST_DEATH),
    ))
    def test_every_fast_bit_selects_exactly_its_family(self, bit, family):
        state = GameState(level_flags_2=bit)

        for candidate in (
            MazeObjIds.MONST_GHOST,
            MazeObjIds.MONST_GRUNT,
            MazeObjIds.MONST_DEMON,
            MazeObjIds.MONST_LOBBER,
            MazeObjIds.MONST_SORC,
            MazeObjIds.MONST_AUX_GRUNT,
            MazeObjIds.MONST_DEATH,
        ):
            expected = (
                _MONSTER_SPEED_FAST
                if candidate == family
                else _MONSTER_SPEED_BASE
            )
            assert _monster_speed(state, int(candidate), 2) == expected

    def test_fast_bit_speeds_only_its_family(self):
        state = GameState()
        state.level_flags_2 = 0x01                    # FAST_GHOSTS only
        assert _monster_speed(state, int(MazeObjIds.MONST_GHOST), 2) == _MONSTER_SPEED_FAST
        assert _monster_speed(state, int(MazeObjIds.MONST_GRUNT), 2) == _MONSTER_SPEED_BASE

    def test_needs_cadence_bit_one(self):
        state = GameState()
        state.level_flags_2 = 0x01
        assert _monster_speed(state, int(MazeObjIds.MONST_GHOST), 0) == _MONSTER_SPEED_BASE

    def test_family_without_a_fast_flag_stays_base(self):
        state = GameState()
        state.level_flags_2 = 0xFF                     # every fast bit set
        assert _monster_speed(state, int(MazeObjIds.MONST_ACID), 2) == _MONSTER_SPEED_BASE

    def test_cadence_word_is_the_doubled_frame_counter(self):
        """Without slow-motion the fast frame is an *odd* frame_counter, because
        monsters_everything doubles the word before testing bit 1 (0x40EEC)."""
        state = GameState()
        state.level_flags_2 = 0x02                     # FAST_GRUNTS
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)
        state.frame_counter = 1                        # doubled -> bit 1 set
        x0 = decode_hpos(state.mobs.hpos[slot])[0]
        main_move_monsters(state)
        moved = _monster_slot(state, MazeObjIds.MONST_GRUNT)
        assert decode_hpos(state.mobs.hpos[moved])[0] - x0 == _MONSTER_SPEED_FAST


# ---------------------------------------------------------------------------
# Slow-motion gate (acceptance criterion 3)
# ---------------------------------------------------------------------------

class TestSlowMotion:
    def test_even_frame_skips_walk(self):
        """With slow-mo active, an even frame does not advance any monster."""
        state = GameState()
        state.monster_slowmo_timer = 100
        state.frame_counter = 4          # even
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GHOST, direction=0)
        hpos_before = state.mobs.hpos[slot]
        main_move_monsters(state)
        assert state.mobs.hpos[slot] == hpos_before, "monster moved on even frame"
        assert state.monster_slowmo_timer == 99, "timer still decrements"

    def test_odd_frame_still_moves(self):
        """On an odd frame the monster walk runs even under slow-mo."""
        state = GameState()
        state.monster_slowmo_timer = 100
        state.frame_counter = 5          # odd
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GHOST, direction=0)
        x_before = decode_hpos(state.mobs.hpos[slot])[0]
        main_move_monsters(state)
        moved = _monster_slot(state, MazeObjIds.MONST_GHOST)
        assert decode_hpos(state.mobs.hpos[moved])[0] > x_before

    def test_silencer_sound_at_0x1e(self):
        state = GameState()
        state.monster_slowmo_timer = 0x1F
        state.frame_counter = 5
        _arena(state, pack_slot(5, 5))
        main_move_monsters(state)
        assert 0x38 in state.sound_log

    def test_end_sound_at_zero(self):
        state = GameState()
        state.monster_slowmo_timer = 1
        state.frame_counter = 5
        _arena(state, pack_slot(5, 5))
        main_move_monsters(state)
        assert 0x39 in state.sound_log

    def test_players_untouched_by_slowmo(self):
        """Slow-mo is a monster effect: player health does not change."""
        state = GameState()
        state.monster_slowmo_timer = 100
        state.frame_counter = 4
        _place_player(state, 0, pack_slot(10, 10))
        _camera_on(state, pack_slot(10, 10))
        state.players[0].health = 1000
        main_move_monsters(state)
        assert state.players[0].health == 1000


# ---------------------------------------------------------------------------
# Culling rectangle and the walked arc (0x49052 / 0x40FF6 / 0x41B52 / 0x49076)
# ---------------------------------------------------------------------------

class TestCullingRectangle:
    def test_origins_follow_the_camera(self):
        state = GameState()
        state.scroll_x = 0x100
        state.scroll_y = 0x80
        _update_cull_rect(state)
        assert state.monster_cull_h_origin == ((0x100 - 0x17) << 7)
        assert state.monster_cull_v_origin == ((0xF9 - 0x80) << 7)

    def test_wrapped_left_camera_keeps_right_seam_monsters_live(self):
        """Level 7 wraps horizontally; scroll 0 must include column 31."""
        state = GameState(wrap_h=True)
        slot = pack_slot(10, 31)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT)
        state.scroll_x = 0
        state.scroll_y = 10 * 16 - 0x74

        _update_cull_rect(state)

        assert state.monster_cull_h_origin == ((-0x17 << 7) & 0xFFFF)
        assert _in_cull_rect(state, slot)

    def test_the_cull_window_wraps_on_the_16_bit_word_itself(self):
        """``512 << 7`` is 0x10000, so one maze *is* one 16-bit word and the
        ROM's unsigned subtraction wraps at the seam with no extra masking.
        Column 31 sits 0x10 px left of a camera anchored at column 0."""
        state = GameState(wrap_h=True)
        state.scroll_x = 0
        state.scroll_y = 10 * 16 - 0x74
        _update_cull_rect(state)
        seam = pack_slot(10, 31)
        _place_monster(state, seam, MazeObjIds.MONST_GRUNT)
        delta = (state.mobs.hpos[seam] - state.monster_cull_h_origin) & 0xFFFF
        assert delta < 0x7F80, "inside the ROM's 255 px window across the seam"
        assert _in_cull_rect(state, seam)

    def test_the_vertical_cull_origin_is_the_roms_upward_one(self):
        """0x49052: ``(0xF9 - pf_vscroll_lo) << 7``, subtracted straight from
        the MOB's own upward V word -- no flip on either side."""
        state = GameState()
        state.scroll_y = 10 * 16 - 0x74
        state.scroll_x = 0x100
        _update_cull_rect(state)
        slot = pack_slot(10, 10)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT)
        assert state.monster_cull_v_origin == ((0xF9 - state.scroll_y) << 7) & 0xFFFF
        assert ((state.mobs.vpos[slot] - state.monster_cull_v_origin) & 0xFFFF) < 0x8380

    def test_level_seven_seam_lobber_is_processed_and_throws(self):
        state = GameState(
            game_mode=GameMode.NORMAL,
            level_players_active=1,
            wrap_h=True,
            scroll_x=504,
            scroll_y=22 * 16 - 0x74,
        )
        lobber = pack_slot(22, 3)
        player = pack_slot(22, 6)
        _place_monster(
            state, lobber, MazeObjIds.MONST_LOBBER, health=0x0B,
        )
        _place_player(state, 0, player)
        state.frame_counter = _stagger_frame(lobber)

        main_move_monsters(state)

        assert any(state.mobs.picture[slot] for slot in SLOT_LOBBER_SHOTS)

    def test_tile_visibility_wraps_across_the_level_seven_seam(self):
        state = GameState(scroll_x=480, scroll_y=10 * 16)

        assert tile_on_screen_d4(state, pack_slot(10, 2))
        assert not tile_on_screen_d4(state, pack_slot(10, 20))

    @requires_roms
    def test_level_seven_left_seam_keeps_its_visible_generator_active(self):
        from gauntpy import maze

        state = GameState(game_mode=GameMode.NORMAL)
        maze.load_level(state, 7, maze_number=6)
        generator = pack_slot(16, 2)
        assert state.mobs.obj_type(generator) in GENERATOR_TYPES
        state.scroll_x = 504
        state.scroll_y = 16 * 16 - 0x74

        _update_cull_rect(state)

        assert _in_cull_rect(state, generator)

    def test_monster_inside_the_box_is_processed(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GHOST, direction=0)
        x0 = decode_hpos(state.mobs.hpos[slot])[0]
        main_move_monsters(state)
        moved = _monster_slot(state, MazeObjIds.MONST_GHOST)
        assert decode_hpos(state.mobs.hpos[moved])[0] > x0

    def test_monster_outside_the_box_is_frozen(self):
        """A creature past the rectangle is skipped before any dispatch."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GHOST, direction=0)
        _camera_on(state, pack_slot(10, 30))     # look away, same band
        _update_cull_rect(state)
        assert not _in_cull_rect(state, slot)
        before = state.mobs.hpos[slot]
        main_move_monsters(state)
        assert state.mobs.hpos[slot] == before

    def test_walk_skips_bands_off_the_screen(self):
        """0x49076: the walk only covers the chain arc near the camera."""
        state = GameState()
        near = pack_slot(10, 10)
        far = pack_slot(30, 10)
        _arena(state, near)
        _place_monster(state, near, MazeObjIds.MONST_GHOST, direction=0)
        _place_monster(state, far, MazeObjIds.MONST_GRUNT, direction=0)
        before_far = state.mobs.hpos[far]
        main_move_monsters(state)
        assert state.mobs.hpos[far] == before_far, "off-screen band was walked"

    def test_walk_wraps_its_slip_arc_across_the_vertical_seam(self):
        """0x49076/0x490AC mask both SLIP indices into the 512-pixel maze."""
        state = GameState(scroll_x=323, scroll_y=492)
        monster = pack_slot(1, 27)
        player = pack_slot(6, 27)
        _place_monster(state, monster, MazeObjIds.MONST_GHOST, direction=4)
        _place_player(state, 0, player)
        state.mobs.create(
            pack_slot(31, 1), 1, encode_hpos(16),
            encode_vpos_at_y(31 * 16), MazeObjIds.TREASURE,
        )
        state.frame_counter = _stagger_frame(monster)
        before = state.mobs.state_link[monster]

        assert _in_cull_rect(state, monster) is False
        _update_cull_rect(state)
        assert _in_cull_rect(state, monster)
        assert _walk_band_head(state, -0x90) == state.mobs.slip_heads[60]
        assert _walk_band_head(state, 0x90) == state.mobs.slip_heads[32]

        main_move_monsters(state)

        assert state.mobs.state_link[monster] != before

    def test_no_players_freezes_everything(self):
        """0x4904E: with nobody on the level the whole pass returns early."""
        state = GameState()
        slot = pack_slot(10, 10)
        _camera_on(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GHOST, direction=0)
        state.level_players_active = 0
        before = state.mobs.hpos[slot]
        main_move_monsters(state)
        assert state.mobs.hpos[slot] == before

    def test_shooter_box_is_inset_from_the_cull_box(self):
        """monster_shooter_in_view rejects the outer margin the mover allows."""
        state = GameState()
        slot = pack_slot(10, 10)
        _camera_on(state, slot)
        _update_cull_rect(state)
        _place_monster(state, slot, MazeObjIds.MONST_DEMON)
        assert monster_shooter_in_view(state, slot)
        edge_x = (state.monster_cull_h_origin >> 7) + 8
        state.mobs.hpos[slot] = encode_hpos(edge_x)
        assert _in_cull_rect(state, slot)
        assert not monster_shooter_in_view(state, slot)

    def test_out_of_view_demon_holds_fire(self):
        """In the cull box but inside the shooter margin: it never fires."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_DEMON, direction=0)
        _place_player(state, 0, pack_slot(10, 16))
        x, y = (slot & 0x1F) * 16, (slot >> 5) * 16
        state.scroll_x = x - 8 + 0x17            # 8 px inside the left edge
        state.scroll_y = y - 0x74
        _update_cull_rect(state)
        assert _in_cull_rect(state, slot)
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_DEMON))
        assert all(state.mobs.picture[s] == 0 for s in range(5, 9))


# ---------------------------------------------------------------------------
# Movement engine (0x4126A) and the ray marches
# ---------------------------------------------------------------------------

class TestMovementEngine:
    def test_clear_step_advances_one_speed(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)
        h, v, d6, clear, blocker = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert clear and blocker is None
        assert hpos_x(h) - 160 == _MONSTER_SPEED_BASE
        assert vpos_y(v) == 160
        assert ((d6 >> 10) - 2) & 7 == 0, "heading unchanged when nothing blocks"

    def test_diagonal_slides_along_a_wall(self):
        """One component refused, the other still taken -- the ROM's slide."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=1)  # down-right
        _place_wall(state, pack_slot(10, 11))
        _place_wall(state, pack_slot(11, 11))
        h, v, _d6, clear, _b = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert clear
        assert hpos_x(h) == 160, "horizontal component blocked"
        assert vpos_y(v) == 160 + _MONSTER_SPEED_BASE, "vertical component taken"

    def test_wall_dead_ahead_refuses_the_step(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)
        _place_wall(state, pack_slot(10, 11))
        h, v, _d6, clear, blocker = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert not clear and blocker is None
        assert hpos_x(h) == 160 and vpos_y(v) == 160

    def test_flanking_cells_block_too(self):
        """A march checks the cell ahead *and* both of its neighbours, so a
        creature that is drifting towards a corner clips it."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)   # down
        state.mobs.hpos[slot] = encode_hpos(160 + 8, palette=4)  # drifted right
        _place_wall(state, pack_slot(11, 11))          # only the flank
        _, _, _d6, clear, _b = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert not clear

    def test_flank_out_of_reach_does_not_block(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_wall(state, pack_slot(11, 11))          # a full cell away
        _, _, _d6, clear, _b = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert clear

    def test_top_edge_guard(self):
        """0x5E112: a creature may not walk out of the top of the maze."""
        state = GameState()
        slot = pack_slot(0, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=6)   # up
        _, _, _d6, clear, _b = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert not clear

    def test_bottom_edge_guard(self):
        """0x5E1DE: nor out of the bottom."""
        state = GameState()
        slot = pack_slot(31, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)   # down
        _, _, _d6, clear, _b = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert not clear

    def test_maze_seam_is_toroidal(self):
        """The ROM's position words wrap once per maze, so column 31 sees
        column 0 as its neighbour (0x5E2C0)."""
        state = GameState()
        slot = pack_slot(10, 31)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)   # right
        _place_wall(state, pack_slot(10, 0))
        _, _, _d6, clear, _b = _probe_phase(state, slot, _MONSTER_SPEED_BASE << 7)
        assert not clear, "the wrapped column should block"

    def test_destination_cell_uses_the_sprite_bias(self):
        """0x41358: the cell a position belongs to is read with a +12 px
        horizontal and +8 px vertical sprite-origin bias."""
        assert _destination_cell(encode_hpos(160), encode_vpos_at_y(160)) == pack_slot(10, 10)
        assert _destination_cell(encode_hpos(164), encode_vpos_at_y(160)) == pack_slot(10, 11)
        assert _destination_cell(encode_hpos(160), encode_vpos_at_y(168)) == pack_slot(10, 10)
        assert _destination_cell(encode_hpos(160), encode_vpos_at_y(172)) == pack_slot(11, 10)

    def test_relocation_follows_the_position(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)
        _walk_frames(state, 4)
        assert _monster_slot(state, MazeObjIds.MONST_GRUNT) == pack_slot(10, 11)

    def test_relocation_writes_the_new_slots_live_animation_frame(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)
        state.mobs.hpos[slot] = encode_hpos(163, palette=4)
        state.mobs.picture[slot] = 1

        _monster_move_engine(
            state, slot, int(MazeObjIds.MONST_GRUNT), 1, 0,
        )

        moved = pack_slot(10, 11)
        assert state.mobs.obj_type(moved) == int(MazeObjIds.MONST_GRUNT)
        assert state.mobs.picture[moved] == _MONSTER_IDLE_ANIMS[
            int(MazeObjIds.MONST_GRUNT)
        ][_monster_animation_index(state, moved)]

    def test_engine_clears_the_moving_flag(self):
        """0x41348 -- a creature drops out of its walk state once it commits."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0,
                       moving=True)
        _monster_move_engine(state, slot, int(MazeObjIds.MONST_GRUNT), 1, 0)
        moved = _monster_slot(state, MazeObjIds.MONST_GRUNT)
        assert not state.mobs.hpos[moved] & _HPOS_FLAG_MOVING


# ---------------------------------------------------------------------------
# Animation counter (0x40E1E bytes 0/2/3)
# ---------------------------------------------------------------------------

class TestAnimationState:
    def test_moving_state_animates_before_it_steps(self):
        """0x4119A: while walking, the mover only runs when the counter wraps."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0,
                       moving=True)
        _dispatch_monster(state, slot, int(MazeObjIds.MONST_GRUNT), 0)
        assert state.mobs.hpos[slot] & _HPOS_FLAG_MOVING, "still animating"
        assert state.mobs.state_link[slot] & 0xE000 == 0x2000
        # Seven more gated frames wrap the counter and release the step.
        for _ in range(7):
            _dispatch_monster(state, slot, int(MazeObjIds.MONST_GRUNT), 0)
        moved = _monster_slot(state, MazeObjIds.MONST_GRUNT)
        assert not state.mobs.hpos[moved] & _HPOS_FLAG_MOVING
        assert decode_hpos(state.mobs.hpos[moved])[0] == 160 + _MONSTER_SPEED_BASE

    def test_moving_state_is_gated_by_the_frame(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0,
                       moving=True)
        _dispatch_monster(state, slot, int(MazeObjIds.MONST_GRUNT), 2)
        assert state.mobs.state_link[slot] & 0xE000 == 0, "off-gate frame"

    def test_attack_state_fires_when_the_windup_completes(self):
        """0x411F6: the attack animation ends by clearing the flag and firing."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_DEMON, direction=0)
        _place_player(state, 0, pack_slot(10, 16))
        state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK
        state.mobs.state_link[slot] |= 0xE000          # one step from the wrap
        _dispatch_monster(state, slot, int(MazeObjIds.MONST_DEMON), 0)
        assert not state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK or \
            any(state.mobs.picture[s] for s in range(5, 9))

    def test_sorcerer_blinks_out_when_its_counter_wraps(self):
        """Byte 2 bit 0 (0xFF) puts the two sorcerers into the blank state."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_SORC, direction=0)
        state.mobs.state_link[slot] |= 0xE000
        _monster_move_engine(state, slot, int(MazeObjIds.MONST_SORC), 4, 0)
        moved = _monster_slot(state, MazeObjIds.MONST_SORC)
        assert state.mobs.hpos[moved] & _HPOS_FLAG_ATTACK
        assert state.mobs.picture[moved] == 0x1709

    def test_refused_step_uses_byte_0_as_its_gate(self):
        """0x4142E: a grunt (byte 0 = 0) does nothing when its step is refused."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)
        _place_wall(state, pack_slot(10, 11))
        before = state.mobs.state_link[slot]
        _monster_move_engine(state, slot, int(MazeObjIds.MONST_GRUNT), 1, 0)
        assert state.mobs.state_link[slot] & 0xE000 == before & 0xE000

    def test_oddangle_table_bytes(self):
        """monster_oddangle_table (0x40E1E), transcribed byte for byte."""
        assert len(_MONSTER_ODDANGLE_TABLE) == 10
        assert _MONSTER_ODDANGLE_TABLE[0] == (0x0E, 0x06, 0x80, 0x00)   # ghost
        assert _MONSTER_ODDANGLE_TABLE[4] == (0xFF, 0x06, 0xFF, 0x00)   # sorcerer
        assert _MONSTER_ODDANGLE_TABLE[6] == (0x00, 0x06, 0x40, 0xE0)   # Death
        assert _MONSTER_ODDANGLE_TABLE[9] == (0x01, 0x02, 0x00, 0x00)   # IT


# ---------------------------------------------------------------------------
# Generators (acceptance criterion 2)
# ---------------------------------------------------------------------------

class TestGenerators:
    def test_probability_table_is_the_rom_table(self):
        """0x40E46: 32 entries, difficulty x player count."""
        assert len(_MONSTER_SPAWN_PROBABILITY_TABLE) == 32
        assert _MONSTER_SPAWN_PROBABILITY_TABLE[:4] == [0x04, 0x0B, 0x0F, 0x12]
        assert _MONSTER_SPAWN_PROBABILITY_TABLE[-4:] == [0x12, 0x19, 0x1D, 0x20]

    def test_probability_index_uses_difficulty_and_players(self):
        state = GameState()
        state.levelnum_current = 1               # no level cap
        state.game_settings = 0x60               # difficulty 3 -> index 12
        state.level_players_active = 2           # +1
        assert _spawn_probability(state) == _MONSTER_SPAWN_PROBABILITY_TABLE[13]

    def test_level_caps_probability(self):
        state = GameState()
        state.game_settings = 0xE0               # difficulty 7
        state.level_players_active = 4           # index 31 -> 0x20
        state.levelnum_current = 3               # cap 6
        assert _spawn_probability(state) == 6

    def test_frame_overflow_forces_no_spawn(self):
        """frame_overflow zeroes the probability, so no draw is even taken."""
        state = GameState()
        rng = _FixedRNG(0, 0, 0)                 # smallest possible draws
        state.rng = rng
        state.frame_overflow = 8
        state.level_players_active = 1
        state.levelnum_current = 5
        gen_slot = pack_slot(8, 8)
        _arena(state, gen_slot)
        _place_monster(state, gen_slot, MazeObjIds.GEN_GHOST1)
        state.frame_counter = _stagger_frame(gen_slot)
        main_move_monsters(state)
        for d in (pack_slot(7, 8), pack_slot(9, 8),
                  pack_slot(8, 7), pack_slot(8, 9)):
            assert state.mobs.obj_type(d) != int(MazeObjIds.MONST_GHOST)
        assert rng.calls == 0, "a throttled generator must not disturb the RNG"

    def test_turn_stagger_blocks_off_frames(self):
        """A generator acts only when its doubled-slot low bits match the frame."""
        state = GameState()
        state.rng = _FixedRNG(0)         # would spawn if it acted
        state.level_players_active = 1
        state.levelnum_current = 5
        gen_slot = pack_slot(8, 8)
        _arena(state, gen_slot)
        _place_monster(state, gen_slot, MazeObjIds.GEN_GHOST1)
        state.frame_counter = (_stagger_frame(gen_slot) + 1) & 0xF
        main_move_monsters(state)
        spawned = any(
            state.mobs.obj_type(pack_slot(r, c)) == int(MazeObjIds.MONST_GHOST)
            for r, c in ((7, 8), (9, 8), (8, 7), (8, 9))
        )
        assert not spawned, "generator acted on a non-staggered frame"

    def test_generator_acts_on_its_stagger_frame(self):
        state = GameState()
        state.rng = _FixedRNG(0, 0)
        state.levelnum_current = 5
        gen_slot = pack_slot(8, 8)
        _arena(state, gen_slot)
        _place_monster(state, gen_slot, MazeObjIds.GEN_GHOST1)
        state.frame_counter = _stagger_frame(gen_slot)
        main_move_monsters(state)
        assert any(
            state.mobs.obj_type(pack_slot(r, c)) == int(MazeObjIds.MONST_GHOST)
            for r, c in ((7, 8), (9, 8), (8, 7), (8, 9))
        )

    def test_spawn_when_probability_wins(self):
        """handle_generate places a ghost when the draw beats the probability."""
        state = GameState()
        state.game_mode = 0              # gameplay: the probability path
        state.rng = _FixedRNG(0, 0)      # draw 0 for the gate, 0 for direction
        gen_slot = pack_slot(8, 8)
        _place_monster(state, gen_slot, MazeObjIds.GEN_GHOST1)
        handle_generate(state, gen_slot, int(MazeObjIds.GEN_GHOST1), probability=32)
        neighbours = [pack_slot(7, 8), pack_slot(9, 8),
                      pack_slot(8, 7), pack_slot(8, 9)]
        assert any(
            state.mobs.obj_type(n) == int(MazeObjIds.MONST_GHOST)
            for n in neighbours
        )

    def test_no_spawn_when_random_wins(self):
        state = GameState()
        state.game_mode = 0              # gameplay: the probability path
        state.rng = _FixedRNG(31)        # draw 31 >= probability -> no spawn
        gen_slot = pack_slot(8, 8)
        _place_monster(state, gen_slot, MazeObjIds.GEN_GHOST1)
        handle_generate(state, gen_slot, int(MazeObjIds.GEN_GHOST1), probability=10)
        neighbours = [pack_slot(7, 8), pack_slot(9, 8),
                      pack_slot(8, 7), pack_slot(8, 9)]
        assert all(
            state.mobs.obj_type(n) != int(MazeObjIds.MONST_GHOST)
            for n in neighbours
        )


# ---------------------------------------------------------------------------
# Odd-angle override (I-15, 0x40E02 + 0x41810)
# ---------------------------------------------------------------------------

class TestOddAngleOverride:
    @pytest.mark.parametrize(("bit", "family", "override"), (
        (0x01, MazeObjIds.MONST_GHOST, 0x80),
        (0x02, MazeObjIds.MONST_GRUNT, 0xC0),
        (0x10, MazeObjIds.MONST_SORC, 0xA0),
        (0x20, MazeObjIds.MONST_AUX_GRUNT, 0xA0),
        (0x40, MazeObjIds.MONST_DEATH, 0x80),
    ))
    def test_every_live_oddangle_bit_selects_its_family(
        self, bit, family, override,
    ):
        state = GameState(level_flags=bit)
        assert _oddangle_override(state, int(family)) == override

    def test_flag_gates_the_override_byte(self):
        state = GameState()
        assert _oddangle_override(state, int(MazeObjIds.MONST_GRUNT)) == 0
        state.level_flags = 0x02                       # ODDANGLE_GRUNTS
        assert _oddangle_override(state, int(MazeObjIds.MONST_GRUNT)) == 0xC0
        assert _oddangle_override(state, int(MazeObjIds.MONST_GHOST)) == 0

    def test_per_family_bytes(self):
        state = GameState()
        state.level_flags = 0xFF
        assert _oddangle_override(state, int(MazeObjIds.MONST_GHOST)) == 0x80
        assert _oddangle_override(state, int(MazeObjIds.MONST_GRUNT)) == 0xC0
        assert _oddangle_override(state, int(MazeObjIds.MONST_SORC)) == 0xA0
        assert _oddangle_override(state, int(MazeObjIds.MONST_AUX_GRUNT)) == 0xA0
        assert _oddangle_override(state, int(MazeObjIds.MONST_DEATH)) == 0x80

    def test_mask_excludes_demons_and_lobbers(self):
        """0x73 leaves bits 2-3 out, and their table entries are zero anyway."""
        state = GameState()
        state.level_flags = 0xFF
        assert _oddangle_override(state, int(MazeObjIds.MONST_DEMON)) == 0
        assert _oddangle_override(state, int(MazeObjIds.MONST_LOBBER)) == 0

    def test_axis_thresholds_table(self):
        """monster_shoot_axis_thresholds (0x40D8A)."""
        assert len(_MONSTER_SHOOT_AXIS_THRESHOLDS) == 10
        assert _MONSTER_SHOOT_AXIS_THRESHOLDS[0] == (8, 1)                    # ghost
        assert _MONSTER_SHOOT_AXIS_THRESHOLDS[7] == (0, 0)                    # acid

    def test_default_picker_uses_cardinals(self):
        # (u, v) are hardware-axis deltas: v positive means the target is above.
        assert _aim_direction(40, 0, 0, 2) == 0
        assert _aim_direction(0, -40, 0, 2) == 2
        assert _aim_direction(-40, 40, 0, 2) == 5

    def test_odd_angle_never_returns_a_cardinal(self):
        for override, threshold in ((0x80, 8), (0xA0, 4), (0xC0, 4)):
            for dx in (-40, -8, 0, 8, 40):
                for dy in (-40, -8, 0, 8, 40):
                    d = _aim_direction(dx, dy, override, threshold)
                    assert d & 1, (override, dx, dy, d)

    def test_odd_angle_rotation_direction(self):
        assert _aim_direction(40, 0, 0xC0, 4) == 7      # counter-clockwise
        assert _aim_direction(40, 0, 0xA0, 4) == 1      # clockwise

    def test_odd_angled_grunt_walks_diagonally(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=0)
        _place_player(state, 0, pack_slot(10, 15))     # dead right
        state.level_flags = 0x02                       # ODDANGLE_GRUNTS
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 7, "should face up-right, not right"

    def test_plain_grunt_faces_the_player(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_player(state, 0, pack_slot(10, 15))
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 0, "should face right"


# ---------------------------------------------------------------------------
# Targeting (0x41750)
# ---------------------------------------------------------------------------

class TestTargeting:
    def test_invisible_player_is_not_targeted(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_player(state, 0, pack_slot(10, 15))     # right, invisible
        _place_player(state, 1, pack_slot(10, 4))      # left, visible
        state.players[0].powers = PlayerPower.INVIS
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 4, "should face the visible player"

    def test_repulsive_player_is_fled_from(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_player(state, 0, pack_slot(10, 15))     # dead right
        state.players[0].powers = PlayerPower.REPULSE
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 4, "faces away from the target"

    def test_power_masks_are_the_rom_bits(self):
        """0x4176C/0x4185C test the high byte's bits 0 and 1 -- word bits 8/9,
        which ``powerup_bit_masks`` (0x59B64) assigns to these two powers."""
        from gauntpy.subsystems.monsters import (
            _POWER_ARMOR,
            _POWER_INVIS,
            _POWER_REPULSE,
        )
        assert int(_POWER_INVIS) == 0x0100
        assert int(_POWER_REPULSE) == 0x0200
        assert int(_POWER_ARMOR) == 0x0002

    def test_a_bit_6_power_no_longer_hides_a_player(self):
        """Regression for the corrected numbering: the old 0x40 mask is a stat
        power now (nothing there), so it must not affect targeting."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_player(state, 0, pack_slot(10, 15))     # right
        _place_player(state, 1, pack_slot(10, 4))      # left
        state.players[0].powers = 0x0040               # not INVIS any more
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 0, "still targets the nearer player"

    def test_it_player_is_preferred(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_player(state, 0, pack_slot(10, 15))     # near, right
        _place_player(state, 1, pack_slot(2, 10))      # far, above
        state.player_it = 1
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 6, "should face IT, above"

    def test_equal_distance_favours_the_higher_slot(self):
        """0x417B8 walks the players backwards and only takes a strictly closer
        one, so a tie goes to the higher-numbered hero."""
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_player(state, 0, pack_slot(10, 14))     # right, 4 cells
        _place_player(state, 1, pack_slot(10, 6))      # left, 4 cells
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 4, "player 1 wins the tie"

    def test_an_invisible_player_loses_the_tie(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GRUNT, direction=2)
        _place_player(state, 0, pack_slot(10, 14))
        _place_player(state, 1, pack_slot(10, 6))
        state.players[1].powers = PlayerPower.INVIS
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_GRUNT))
        assert state.mobs.state(slot) & 7 == 0, "falls back to player 0"


# ---------------------------------------------------------------------------
# Special cases (acceptance criterion 4)
# ---------------------------------------------------------------------------

class TestSpecialCases:
    def test_acid_rolls_a_new_direction_on_its_turn(self):
        """0x4123A: the puddle picks a random heading on its stagger frame."""
        state = GameState()
        state.rng = _FixedRNG(3)
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_ACID, direction=0)
        state.frame_counter = _stagger_frame(slot)
        main_move_monsters(state)
        moved = _monster_slot(state, MazeObjIds.MONST_ACID)
        assert state.mobs.state(moved) & 7 == 3

    def test_acid_keeps_its_heading_off_turn(self):
        state = GameState()
        state.rng = _FixedRNG(3)
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_ACID, direction=0)
        state.frame_counter = (_stagger_frame(slot) + 1) & 0xF
        main_move_monsters(state)
        moved = _monster_slot(state, MazeObjIds.MONST_ACID)
        assert state.mobs.state(moved) & 7 == 0

    def test_acid_attack_state_is_gated_by_0x1e(self):
        """0x413E6: the splash animation only advances every 32nd frame."""
        state = GameState()
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_ACID, direction=0)
        state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK
        _dispatch_monster(state, slot, int(MazeObjIds.MONST_ACID), 2)
        assert state.mobs.state_link[slot] & 0xE000 == 0, "off-gate"
        _dispatch_monster(state, slot, int(MazeObjIds.MONST_ACID), 0)
        assert state.mobs.state_link[slot] & 0xE000 == 0x2000

    def test_sorcerer_does_not_shoot(self):
        """Sorcerer skips the shooting path -- no demon/lobber shot created."""
        state = GameState()
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_SORC, direction=0)
        _place_player(state, 0, pack_slot(5, 10))
        _walk_frames(state, 8)
        assert all(state.mobs.picture[s] == 0 for s in range(5, 13))

    def test_demon_can_shoot(self):
        """A demon facing a player on an idle turn-stagger frame fires a shot."""
        state = GameState()
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_DEMON, direction=0)
        _place_player(state, 0, pack_slot(5, 10))      # 80 px right
        state.frame_counter = _stagger_frame(slot)
        main_move_monsters(state)
        assert any(state.mobs.picture[s] != 0 for s in range(5, 9)), \
            "demon should have created a shot in slots 5-8"

    def test_demon_holds_fire_at_point_blank(self):
        """0x41AB6: the axis delta must reach 0x10 units (32 px)."""
        state = GameState()
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_DEMON, direction=0)
        _place_player(state, 0, pack_slot(5, 6))       # 16 px right
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_DEMON))
        assert all(state.mobs.picture[s] == 0 for s in range(5, 9))

    def test_demon_muzzle_must_be_clear(self):
        state = GameState()
        slot = pack_slot(5, 5)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_DEMON, direction=0)
        _place_player(state, 0, pack_slot(5, 10))
        _place_monster(state, pack_slot(5, 6), MazeObjIds.MONST_GRUNT)
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_DEMON))
        assert all(state.mobs.picture[s] == 0 for s in range(5, 9)), \
            "a blocked muzzle cell cancels the shot"

    def test_lobber_throws_in_its_band(self):
        state = GameState()
        slot = pack_slot(10, 4)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_LOBBER, direction=0)
        _place_player(state, 0, pack_slot(10, 8))      # 64 px right: in band
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_LOBBER))
        assert any(state.mobs.picture[s] != 0 for s in range(9, 13))
        assert 0x49 in state.sound_log

    def test_lobber_backs_away_when_too_close(self):
        state = GameState()
        slot = pack_slot(10, 4)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_LOBBER, direction=0)
        _place_player(state, 0, pack_slot(10, 5))      # 16 px right: too close
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_LOBBER))
        assert all(state.mobs.picture[s] == 0 for s in range(9, 13))
        assert state.mobs.state(slot) & 7 == 4, "turns away from the player"

    def test_lobber_out_of_range_holds(self):
        state = GameState()
        slot = pack_slot(10, 2)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_LOBBER, direction=0)
        _place_player(state, 0, pack_slot(10, 10))     # 128 px: past 88 px
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_LOBBER))
        assert all(state.mobs.picture[s] == 0 for s in range(9, 13))
        assert state.mobs.state(slot) & 7 == 0, "still faces the player"


# ---------------------------------------------------------------------------
# Shot channels (0x490DC)
# ---------------------------------------------------------------------------

class TestShotChannels:
    def _fire_demon(self) -> tuple[GameState, int]:
        state = GameState()
        slot = pack_slot(10, 4)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_DEMON, direction=0)
        _place_player(state, 0, pack_slot(10, 9))
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_DEMON))
        return state, slot

    def test_creation_loads_the_channel_cooldown(self):
        """0x49104 -- 0x3C frames written at ``shot_timer_next[slot - 5]``."""
        state, _ = self._fire_demon()
        assert state.shot_timer_next[0] == _SHOT_COOLDOWN

    def test_gate_word_is_read_three_channels_up(self):
        """0x41B22 -- ``find_unused_shot`` indexes from 0x904926, so the word
        that gates channel 5 is the timer written for channel 8."""
        state, slot = self._fire_demon()
        for s in range(5, 9):
            state.mobs.picture[s] = 0          # channels look free again
        state.shot_timer_next[:] = [0] * 8
        state.shot_timer_next[3] = _SHOT_COOLDOWN      # slot 5's gate word
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_DEMON))
        assert state.mobs.picture[5] == 0, "slot 5 is gated"
        assert state.mobs.picture[6] != 0, "slot 6 takes the shot"

    def test_all_demon_gates_busy_holds_fire(self):
        state, slot = self._fire_demon()
        for s in range(5, 9):
            state.mobs.picture[s] = 0
        state.shot_timer_next[:] = [0] * 8
        for s in range(5, 9):
            state.shot_timer_next[s - 2] = _SHOT_COOLDOWN
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_DEMON))
        assert all(state.mobs.picture[s] == 0 for s in range(5, 9))

    def test_top_lobber_channels_are_gated_by_score_popups(self):
        """The same index walks past ``shot_timer_next`` into the popup timers
        (0x90493A), so a floating score really does hold channel 10 shut."""
        state = GameState()
        slot = pack_slot(10, 4)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_LOBBER, direction=0)
        _place_player(state, 0, pack_slot(10, 8))
        state.shot_timer_next[7] = _SHOT_COOLDOWN      # slot 9's gate word
        state.score_display_timer[0] = 60              # slot 10's gate word
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_LOBBER))
        assert state.mobs.picture[9] == 0 and state.mobs.picture[10] == 0
        assert state.mobs.picture[11] != 0, "the first ungated channel throws"

    def test_creation_seeds_owner_direction_and_lifetime(self):
        """0x4915C stores the *ROM* compass, which is what WP-7 indexes its
        velocity and projectile-picture tables with; a demon firing right is 2,
        not gauntpy's 0."""
        state, slot = self._fire_demon()
        channel = next(s for s in range(5, 9) if state.mobs.picture[s]) - 1
        assert state.shot_owner_mob[channel] == slot
        assert state.shot_direction[channel] == 2
        assert state.shot_anim_lifetime_counter[channel] == 1

    def test_firing_puts_the_shooter_into_its_attack_state(self):
        """0x4910E -- ``ori.w #0x10`` on the shooter's hpos."""
        state, slot = self._fire_demon()
        assert state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK


class TestShotSpawnPicture:
    """0x491D2 (demon) / 0x49238 (lobber) -- the frame a channel is armed with.

    ``main_handle_shots`` (0x474F6) runs *before* ``main_move_monsters``
    (0x49034) in the frame, so a projectile created here is drawn from this
    picture for the rest of the frame and is not touched by the animation until
    the next one.  It therefore has to be real artwork, and it has to be the
    frame that next animation tick would land on, or the shot visibly jumps.
    """

    @staticmethod
    def _armed(shot_slot: int, direction: int,
               lead: tuple[int, int] | None = None) -> GameState:
        state = GameState()
        shooter = pack_slot(10, 10)
        _arena(state, shooter)
        _place_monster(state, shooter, MazeObjIds.MONST_DEMON,
                       direction=direction)
        monster_create_shot(state, shooter, direction, shot_slot, lead)
        return state

    def test_a_demon_shot_takes_its_rom_direction_frame(self):
        """``projectile_picture_table[0x20 + 2*direction]`` -- 0x491D8's index
        arithmetic with the counter at zero."""
        for direction in range(8):
            state = self._armed(5, direction)
            rom_dir = (direction + 2) & 0x07
            assert state.mobs.picture[5] == \
                _PROJECTILE_PICTURE_TBL[0x20 + 2 * rom_dir], direction

    def test_every_demon_channel_gets_the_same_frame(self):
        for shot_slot in SLOT_DEMON_SHOTS:
            state = self._armed(shot_slot, 0)
            assert state.mobs.picture[shot_slot] == \
                _PROJECTILE_PICTURE_TBL[0x20 + 2 * 2]

    def test_a_lobber_rock_takes_its_reload_counter_frame(self):
        """0x49240 indexes ``monster_projectile_picture_table`` with the reload
        it stored two instructions earlier -- 0x20 for every lobber channel."""
        for shot_slot in SLOT_LOBBER_SHOTS:
            channel = shot_slot - 1
            state = self._armed(shot_slot, 0, lead=(0x100, 0x100))
            counter = _SHOT_COUNTER_RELOAD[channel]
            assert state.mobs.picture[shot_slot] == \
                _MONSTER_PROJECTILE_PICTURE_TBL[counter]

    def test_the_rock_frame_does_not_depend_on_direction(self):
        """The lobber branch never reads the direction tables at all."""
        pictures = {self._armed(9, d, lead=(0x100, 0x100)).mobs.picture[9]
                    for d in range(8)}
        assert len(pictures) == 1

    def test_no_channel_is_ever_armed_with_a_placeholder(self):
        for shot_slot in list(SLOT_DEMON_SHOTS) + list(SLOT_LOBBER_SHOTS):
            lead = (0x100, 0x100) if shot_slot in SLOT_LOBBER_SHOTS else None
            for direction in range(8):
                state = self._armed(shot_slot, direction, lead)
                picture = state.mobs.picture[shot_slot]
                assert picture not in (0, 1), (shot_slot, direction)

    def test_the_armed_frame_is_what_the_next_animation_tick_computes(self):
        """The frame-order guarantee: nothing between creation and the next
        ``main_handle_shots`` repaints the channel, so the two must agree."""
        for shot_slot in list(SLOT_DEMON_SHOTS) + list(SLOT_LOBBER_SHOTS):
            channel = shot_slot - 1
            lead = (0x100, 0x100) if shot_slot in SLOT_LOBBER_SHOTS else None
            for direction in range(8):
                state = self._armed(shot_slot, direction, lead)
                armed = state.mobs.picture[shot_slot]

                # _advance_counter pre-decrements, then _advance_picture paints.
                counter = state.shot_anim_lifetime_counter[channel] - 1
                if counter < 0:
                    counter = _SHOT_COUNTER_RELOAD[channel]
                assert shot_picture(state, channel, counter) == armed, \
                    (shot_slot, direction)

    def test_a_real_frame_leaves_the_armed_picture_alone(self):
        """Driven through ``main_handle_shots`` itself, on a frame where the
        channel's animation is due (``(frame_counter ^ channel) & 1 == 0``)."""
        for shot_slot in (5, 9):
            channel = shot_slot - 1
            lead = (0x100, 0x100) if shot_slot in SLOT_LOBBER_SHOTS else None
            state = self._armed(shot_slot, 0, lead)
            armed = state.mobs.picture[shot_slot]
            state.frame_counter = channel & 1

            main_handle_shots(state)

            assert state.mobs.picture[shot_slot] == armed, shot_slot

    @requires_roms
    def test_the_armed_frames_are_the_rom_words(self):
        from gex.roms import coderom_get_bytes

        def word(addr: int) -> int:
            return int.from_bytes(coderom_get_bytes(addr, 2), "big")

        for direction in range(8):
            rom_dir = (direction + 2) & 0x07
            state = self._armed(5, direction)
            # 0x58B8A + (dir*2 + 0x20) * 2
            assert state.mobs.picture[5] == word(0x58B8A + (rom_dir * 2 + 0x20) * 2)

        state = self._armed(9, 0, lead=(0x100, 0x100))
        # 0x58EDE + shot_counter_reload[8] * 2
        assert state.mobs.picture[9] == word(0x58EDE + 0x20 * 2)

    @requires_roms
    def test_every_armed_frame_renders(self):
        """Renderer resolvability: the old ``1`` placeholder does not resolve at
        all, and every real frame does."""
        from gauntpy.assets import AssetError, AssetStore

        store = AssetStore()
        for shot_slot in list(SLOT_DEMON_SHOTS) + list(SLOT_LOBBER_SHOTS):
            lead = (0x100, 0x100) if shot_slot in SLOT_LOBBER_SHOTS else None
            for direction in range(8):
                state = self._armed(shot_slot, direction, lead)
                store.sprite(state.mobs.picture[shot_slot])

        with pytest.raises(AssetError):
            store.sprite(1)

    def test_lobber_leads_a_running_target(self):
        """0x419E4: the arc adds the target's own velocity to the aim."""
        state = GameState()
        slot = pack_slot(10, 4)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_LOBBER, direction=0)
        _place_player(state, 0, pack_slot(10, 8))
        state.players[0].direction = 2                 # the hero runs downward
        state.player_joystick[0] = 0xB0              # achieved DOWN movement
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_LOBBER))
        channel = next(s for s in range(9, 13) if state.mobs.picture[s])
        assert state.lobber_shot_vec_h[channel - 9] != 0
        assert state.shot_dy[channel] < 0, "the rock is thrown ahead of the hero"

    def test_lobber_lead_is_converted_from_rom_words(self):
        state = GameState()
        state.players[0].character = 0
        state.players[0].direction = 0
        state.player_joystick[0] = 0xE0              # achieved RIGHT movement

        # Raw 0x41978 arithmetic yields (0x138, -0x28) and both components are
        # stored as the ROM computes them.
        assert _lobber_lead(state, 0, 0, 0, 30, -10) == (0x138, -0x28)

    def test_stationary_target_has_no_velocity_lead(self):
        state = GameState()
        state.players[0].character = 0
        state.players[0].direction = 0
        state.player_joystick[0] = 0xF0

        assert _lobber_lead(state, 0, 0, 0, 30, -10) == (0x78, -0x28)

    def test_lobber_arc_accumulators_start_at_the_rock(self):
        """0x49216/0x4922A seeds the *masked* spawn position, palette-free."""
        from gauntpy.coords import POS_FIELD_MASK

        state = GameState()
        slot = pack_slot(10, 4)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_LOBBER, direction=0)
        _place_player(state, 0, pack_slot(10, 8))
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_LOBBER))
        channel = next(s for s in range(9, 13) if state.mobs.picture[s])
        assert state.lobber_shot_h_accum[channel - 9] == (
            state.mobs.hpos[channel] & POS_FIELD_MASK
        )
        assert state.lobber_shot_v_accum[channel - 9] == (
            state.mobs.vpos[channel] & POS_FIELD_MASK
        )

    def test_a_thrown_rock_flies_on_its_accumulator_not_the_velocity_table(self):
        """End to end: 0x419FA's vector, 0x49216's seed, 0x479C2's mover."""
        from gauntpy.coords import POS_FIELD_MASK

        state = GameState()
        slot = pack_slot(10, 4)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_LOBBER, direction=0)
        _place_player(state, 0, pack_slot(10, 8))
        monster_find_and_shoot(state, slot, int(MazeObjIds.MONST_LOBBER))
        channel = next(s for s in range(9, 13) if state.mobs.picture[s])
        shooter = channel - 1
        vec_h = state.lobber_shot_vec_h[channel - 9]
        vec_v = state.lobber_shot_vec_v[channel - 9]
        assert vec_h != 0, "the lead has a horizontal component to check"
        accum_h = state.lobber_shot_h_accum[channel - 9]
        accum_v = state.lobber_shot_v_accum[channel - 9]
        low_h = state.mobs.hpos[channel] & ~POS_FIELD_MASK & 0xFFFF
        low_v = state.mobs.vpos[channel] & ~POS_FIELD_MASK & 0xFFFF

        for step in range(1, 4):
            main_handle_shots(state)
            state.frame_counter += 1
            expect_h = (accum_h + step * vec_h) & 0xFFFF
            expect_v = (accum_v + step * vec_v) & 0xFFFF
            assert state.lobber_shot_h_accum[channel - 9] == expect_h
            assert state.lobber_shot_v_accum[channel - 9] == expect_v
            assert state.mobs.hpos[channel] == (expect_h & POS_FIELD_MASK) + low_h
            assert state.mobs.vpos[channel] == (expect_v & POS_FIELD_MASK) + low_v
        # A straight channel would have taken shot_velocity_x[0x20 + dir].
        from gauntpy.subsystems.shots import _SHOT_VELOCITY_X
        straight = _SHOT_VELOCITY_X[0x20 + state.shot_direction[shooter]]
        assert state.mobs.hpos[channel] != (
            (accum_h + 3 * straight) & POS_FIELD_MASK
        ) + low_h


# ---------------------------------------------------------------------------
# Shot spawn geometry: 0x49192-0x49270
# ---------------------------------------------------------------------------

class TestShotSpawnGeometry:
    """The ROM masks the shooter's words with 0xFF80 and adds its own low byte.

    ``+0xD`` (0x491BA), ``+1`` (0x49258) and ``+9`` (0x4926E) all land under
    the position field: they are the projectile's palette and packed sprite
    size, not pixel offsets.
    """

    SHOOTER = pack_slot(10, 10)     # pixel (160, 160)

    def _fire(self, direction: int, shot_slot: int = 5,
              lead: tuple[int, int] | None = None) -> GameState:
        state = GameState()
        _arena(state, self.SHOOTER)
        _place_monster(state, self.SHOOTER, MazeObjIds.MONST_DEMON,
                       direction=direction, health=4)
        state.mobs.vpos[self.SHOOTER] = encode_vpos_at_y(160, 3, 3)   # a 3x3 body
        monster_create_shot(state, self.SHOOTER, direction, shot_slot, lead)
        return state

    def test_a_demon_shot_rebuilds_the_exact_rom_words(self):
        for direction in range(8):
            state = self._fire(direction)
            rom_dir = (direction + 2) & 0x07
            off_h = _MONSTER_SHOT_SPAWN_H[rom_dir]
            off_v = _MONSTER_SHOT_SPAWN_V[rom_dir]
            base_v = native_v(160) << 7
            assert state.mobs.hpos[5] == ((160 << 7) + off_h + 0x0E) & 0xFFFF, direction
            assert state.mobs.vpos[5] == (base_v + off_v + 0x09) & 0xFFFF, direction

    def test_a_lobbed_rock_rebuilds_the_exact_rom_words(self):
        for direction in range(8):
            state = self._fire(direction, shot_slot=9, lead=(0x100, 0x100))
            rom_dir = (direction + 2) & 0x07
            off_h = _LOBBER_SHOT_SPAWN_H[rom_dir]
            off_v = _LOBBER_SHOT_SPAWN_V[rom_dir]
            base_v = native_v(160) << 7
            assert state.mobs.hpos[9] == ((160 << 7) + off_h + 0x01) & 0xFFFF, direction
            assert state.mobs.vpos[9] == (base_v + off_v + 0x09) & 0xFFFF, direction

    def test_the_palette_is_the_class_constant_not_the_shooters_health(self):
        assert self._fire(0).mobs.hpos[5] & 0x0F == 0x0E
        assert self._fire(0, 9, lead=(0, 0)).mobs.hpos[9] & 0x0F == 0x01
        # the shooter kept its own health nibble of 4
        assert self._fire(0).mobs.hpos[self.SHOOTER] & 0x0F == 4

    def test_a_projectile_carries_no_strength_bits(self):
        for direction in range(8):
            assert self._fire(direction).mobs.hpos[5] & 0x30 == 0
            assert self._fire(direction, 9, lead=(0, 0)).mobs.hpos[9] & 0x30 == 0

    def test_every_projectile_is_two_tiles_square(self):
        """0x4926E's +9: width-1 = height-1 = 1, whatever the shooter was."""
        for shot_slot, lead in ((5, None), (9, (0, 0))):
            state = self._fire(0, shot_slot, lead)
            assert decode_vpos_at_y(state.mobs.vpos[self.SHOOTER])[1:] == (3, 3)
            assert decode_vpos_at_y(state.mobs.vpos[shot_slot])[1:] == (2, 2)

    def test_the_muzzle_offsets_stay_per_direction(self):
        """The removed +13/+9 bias used to swamp them; they must still differ."""
        spots = {d: (decode_hpos(self._fire(d).mobs.hpos[5])[0],
                     decode_vpos_at_y(self._fire(d).mobs.vpos[5])[0])
                 for d in range(8)}
        assert len(set(spots.values())) > 1
        # ROM compass 2 (right) is the largest rightward muzzle, 0x600 = 12 px.
        assert spots[0] == (172, 160)
        # ROM compass 6 (left) pulls the muzzle back, 0xFE00 = -4 px.
        assert spots[4] == (156, 160)

    def test_the_shot_is_depth_keyed_where_the_next_frame_will_re_key_it(self):
        from gauntpy.subsystems.shots import shot_cell

        for direction in range(8):
            state = self._fire(direction)
            assert state.mobs.depth_key[5] == shot_cell(state, 5)

    @requires_roms
    def test_the_spawn_words_and_constants_are_the_rom_bytes(self):
        from gex.roms import coderom_get_bytes

        def word(addr: int) -> int:
            raw = int.from_bytes(coderom_get_bytes(addr, 2), "big")
            return raw - 0x10000 if raw >= 0x8000 else raw

        for index in range(8):
            assert _MONSTER_SHOT_SPAWN_H[index] == word(0x57B98 + index * 2)
            assert _MONSTER_SHOT_SPAWN_V[index] == word(0x57BA8 + index * 2)
            assert _LOBBER_SHOT_SPAWN_H[index] == word(0x57BB8 + index * 2)
            assert _LOBBER_SHOT_SPAWN_V[index] == word(0x57BC8 + index * 2)
            # every entry is a whole ROM pixel, so it cannot reach the low field
            assert _MONSTER_SHOT_SPAWN_H[index] % 0x80 == 0
            assert _MONSTER_SHOT_SPAWN_V[index] % 0x80 == 0
            assert _LOBBER_SHOT_SPAWN_H[index] % 0x80 == 0
            assert _LOBBER_SHOT_SPAWN_V[index] % 0x80 == 0

        # The three immediates, read straight out of the instruction stream.
        assert word(0x491BA) & 0xFFFF == 0x0640    # addi.w #imm, d0
        assert word(0x491BC) == 0x000D
        assert word(0x49258) & 0xFFFF == 0x5280    # addq.l #1, d0
        assert word(0x4926C) & 0xFFFF == 0x7209    # moveq #9, d1
        assert _DEMON_SHOT_HPOS_LOW == 0x0D + 1
        assert _LOBBER_SHOT_HPOS_LOW == 1
        assert _SHOT_VPOS_LOW == 9


# ---------------------------------------------------------------------------
# Chain walk + contact
# ---------------------------------------------------------------------------

class TestIterationAndContact:
    def test_hurt_speech_timer_reloads_and_selects_character_voice(self):
        state = GameState(level_players_active=2)
        state.rng = _FixedRNG(3, 2)
        state.players[0].character = Character.WARRIOR

        player_hurt_speech_timer(state, 0)

        assert state.hurt_speech_timer[0] == 15
        assert state.sound_log == [0x85]
        assert state.rng.calls == 2

    def test_hurt_speech_waits_for_negative_countdown(self):
        state = GameState(level_players_active=1)
        state.rng = _FixedRNG(0)
        state.hurt_speech_timer[0] = 1

        player_hurt_speech_timer(state, 0)

        assert state.hurt_speech_timer[0] == 0
        assert state.sound_log == []
        assert state.rng.calls == 0

    def test_acid_suppresses_voice_after_reloading_timer(self):
        state = GameState(level_players_active=4)
        state.rng = _FixedRNG(7, 3)
        state.players[0].acid_timer = 1

        player_hurt_speech_timer(state, 0)

        assert state.hurt_speech_timer[0] == 27
        assert state.sound_log == []
        assert state.rng.calls == 1

    def test_walk_marker_follows_the_camera(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _arena(state, slot)
        _place_monster(state, slot, MazeObjIds.MONST_GHOST)
        main_move_monsters(state)
        assert state.monster_iter_ptr != 0

    def test_iter_ptr_resets_with_no_monsters(self):
        state = GameState()
        state.monster_iter_ptr = 5
        monsters_everything(state)
        assert state.monster_iter_ptr == 0

    def test_contact_damages_player(self):
        """A monster walking into a player hurts it once its wind-up is done."""
        state = GameState()
        player_slot = pack_slot(5, 8)
        monster_slot = pack_slot(5, 5)
        _place_player(state, 0, player_slot)
        _arena(state, monster_slot)
        state.players[0].health = 1000
        _place_monster(state, monster_slot, MazeObjIds.MONST_GRUNT, direction=0)
        _walk_frames(state, 60)
        assert state.players[0].health < 1000, "player should take contact damage"

    def test_many_monsters_do_not_crash(self):
        """60+ monsters simulate in one frame without error (criterion 1)."""
        state = GameState()
        _arena(state, pack_slot(6, 5))
        n = 0
        for row in range(2, 12):
            for col in range(2, 9):
                _place_monster(state, pack_slot(row, col),
                               MazeObjIds.MONST_GHOST, direction=2)
                n += 1
        assert n >= 60
        _walk_frames(state, 4)   # must not raise

    def test_contact_uses_current_cell_not_spawn_slot(self):
        """A moved player is hit at the cell its record migrated into.

        Identity is location for a hero exactly as it is for a monster
        (``players.migrate_player_record``), so a creature stepping into the
        cell the hero now owns finds it there -- no pixel overlay involved.
        """
        state = GameState()
        spawn_slot = pack_slot(2, 2)          # where the hero came in
        current_slot = pack_slot(5, 6)        # where the record now is
        p = state.players[0]
        p.status = PlayerStatus.ALIVE_HERE
        p.mob_slot = current_slot
        p.health = 1000
        state.level_players_active = 1
        assert state.mobs.picture[spawn_slot] == 0, "the spawn cell is vacated"
        state.mobs.create(current_slot, tile=0x100,
                          hpos=encode_hpos(6 * 16 - 4, palette=0x0C),
                          vpos=encode_vpos_at_y(5 * 16),
                          obj_type=int(MazeObjIds.PLAYERSTART), state=0)

        monster_slot = pack_slot(5, 5)        # directly left of the current cell
        _arena(state, monster_slot)
        _place_monster(state, monster_slot, MazeObjIds.MONST_GRUNT, direction=0,
                       moving=True)
        x = (monster_slot & 0x1F) * 16 + 12
        state.mobs.hpos[monster_slot] = encode_hpos(x, palette=4,
                                                    flags=_HPOS_FLAG_MOVING)
        _monster_move_engine(state, monster_slot, int(MazeObjIds.MONST_GRUNT), 1, 0)
        assert state.players[0].health < 1000, \
            "contact must key off the cell the player's record occupies"

    def test_surrounding_grunts_damage_a_spawn_aligned_player(self):
        state = GameState()
        player_slot = pack_slot(10, 10)
        _place_player(state, 0, player_slot)
        state.mobs.hpos[player_slot] = encode_hpos(
            10 * 16 - 4, palette=0x0C,
        )
        state.mobs.vpos[player_slot] = encode_vpos_at_y(10 * 16, 3, 3)
        state.players[0].health = 1000

        placements = (
            (pack_slot(10, 9), 0),
            (pack_slot(10, 11), 4),
            (pack_slot(9, 10), 2),
            (pack_slot(11, 10), 6),
        )
        for slot, direction in placements:
            _place_monster(
                state, slot, MazeObjIds.MONST_GRUNT,
                direction=direction, health=4, moving=True,
            )
            x = (slot & 0x1F) * 16 - 4
            y = (slot >> 5) * 16
            state.mobs.hpos[slot] = encode_hpos(
                x, palette=4, flags=_HPOS_FLAG_MOVING,
            )
            state.mobs.vpos[slot] = encode_vpos_at_y(y, 3, 3)
            _monster_move_engine(
                state, slot, int(MazeObjIds.MONST_GRUNT), 1, 0,
            )

        assert state.players[0].health == 1000 - 4 * 8


class TestSuperSorcerer:
    """0x4106A -- fade out, teleport, fade in, fire."""

    def _blinked_out(self, state: GameState, slot: int) -> None:
        state.mobs.hpos[slot] |= _HPOS_FLAG_MOVING | _HPOS_FLAG_ATTACK
        state.mobs.picture[slot] = 0x1709

    def test_relocates_behind_player(self):
        """Blinked out and on its turn, it reappears behind a player."""
        state = GameState()
        state.rng = _FixedRNG(0)              # start at player 0
        # Player at (10,10) facing right (direction 0) -> behind is left.
        _place_player(state, 0, pack_slot(10, 10))
        state.players[0].direction = 0
        origin = pack_slot(9, 9)
        _arena(state, pack_slot(10, 8))
        _place_monster(state, origin, MazeObjIds.MONST_SUPERSORC)
        self._blinked_out(state, origin)
        state.frame_counter = _stagger_frame(origin)
        main_move_monsters(state)
        found = [s for s in range(1024)
                 if state.mobs.obj_type(s) == int(MazeObjIds.MONST_SUPERSORC)]
        assert len(found) == 1
        r, c = found[0] >> 5, found[0] & 0x1F
        assert (r, c) != (9, 9), "should have teleported"
        assert r == 10 and c < 10, "should be relocated to the player's left"
        assert state.mobs.state(found[0]) & 7 == 0, "faces back at the player"
        assert not state.mobs.hpos[found[0]] & (_HPOS_FLAG_MOVING | _HPOS_FLAG_ATTACK), \
            "0x410BE: it arrives solid again"
        assert state.mobs.picture[found[0]] != 0x1709

    def test_relocation_uses_player_slot_and_rom_corrected_hpos(self):
        state = GameState()
        state.rng = _FixedRNG(0)
        player_slot = pack_slot(10, 10)
        _place_player(state, 0, player_slot)
        state.players[0].direction = 0
        state.mobs.hpos[player_slot] = encode_hpos(10 * 16 - 4, palette=0x0C)
        origin = pack_slot(9, 9)
        _arena(state, pack_slot(10, 8))
        _place_monster(state, origin, MazeObjIds.MONST_SUPERSORC)
        self._blinked_out(state, origin)

        destination = supersorc_place(state, origin)

        assert destination == pack_slot(10, 6)
        assert decode_hpos(state.mobs.hpos[destination])[0] == 6 * 16 - 4
        assert decode_vpos_at_y(state.mobs.vpos[destination])[0] == 10 * 16
        assert state.mobs.state(destination) & 7 == 0

    def test_diagonal_relocation_faces_exactly_back_toward_player_slot(self):
        state = GameState()
        state.rng = _FixedRNG(0)
        player_slot = pack_slot(10, 10)
        _place_player(state, 0, player_slot)
        state.players[0].direction = 1
        state.mobs.hpos[player_slot] = encode_hpos(10 * 16 - 4, palette=0x0C)
        origin = pack_slot(9, 9)
        _arena(state, pack_slot(8, 8))
        _place_monster(state, origin, MazeObjIds.MONST_SUPERSORC)
        self._blinked_out(state, origin)

        destination = supersorc_place(state, origin)

        assert destination == pack_slot(6, 6)
        assert state.mobs.state(destination) & 7 == 1

    def test_teleport_is_turn_staggered(self):
        """0x41078: the teleport only runs on the creature's stagger frame."""
        state = GameState()
        state.rng = _FixedRNG(0)
        _place_player(state, 0, pack_slot(10, 10))
        state.players[0].direction = 0
        origin = pack_slot(9, 9)
        _arena(state, pack_slot(10, 8))
        _place_monster(state, origin, MazeObjIds.MONST_SUPERSORC)
        self._blinked_out(state, origin)
        state.frame_counter = (_stagger_frame(origin) + 1) & 0xF
        main_move_monsters(state)
        assert state.mobs.obj_type(origin) == int(MazeObjIds.MONST_SUPERSORC)

    def test_fade_out_blanks_the_sprite(self):
        """0x410D4: the walking phase ends by blinking out."""
        state = GameState()
        slot = pack_slot(9, 9)
        _arena(state, slot)
        _place_player(state, 0, pack_slot(10, 10))
        _place_monster(state, slot, MazeObjIds.MONST_SUPERSORC, moving=True)
        state.mobs.state_link[slot] |= 0xE000          # one step from the wrap
        _supersorc_dispatch(state, slot, 0)
        assert state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK
        assert not state.mobs.hpos[slot] & _HPOS_FLAG_MOVING
        assert state.mobs.picture[slot] == 0x1709

    def test_fade_in_restores_the_walking_state(self):
        """0x41104: the fade-in phase hands back to walking."""
        state = GameState()
        slot = pack_slot(9, 9)
        _arena(state, slot)
        _place_player(state, 0, pack_slot(10, 10))
        _place_monster(state, slot, MazeObjIds.MONST_SUPERSORC)
        state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK
        state.mobs.state_link[slot] |= 0xE000
        _supersorc_dispatch(state, slot, 0)
        assert state.mobs.hpos[slot] & _HPOS_FLAG_MOVING

    def test_idle_phase_fires_down_a_demon_channel(self):
        """0x41142: the Super Sorcerer's bolt borrows slots 5-8."""
        state = GameState()
        slot = pack_slot(9, 9)
        _arena(state, slot)
        _place_player(state, 0, pack_slot(9, 14))
        _place_monster(state, slot, MazeObjIds.MONST_SUPERSORC, direction=0)
        state.mobs.state_link[slot] |= 0xE000
        _supersorc_dispatch(state, slot, 0)
        assert any(state.mobs.picture[s] for s in range(5, 9))
        assert state.mobs.hpos[slot] & _HPOS_FLAG_MOVING


# ---------------------------------------------------------------------------
# Contact damage (I-13)
# ---------------------------------------------------------------------------

class TestContactDamageExact:
    """Exact tier-scaled contact damage (I-13): row = nibble - base + 2 + offset,
    damage = table[row*4 + character (+0x20 armored)]."""

    def _hit(self, obj_type, nibble, character=0, powers=0, moving=True,
             health=1000):
        state = GameState()
        state.game_mode = 0                      # GameMode.NORMAL
        mslot = pack_slot(5, 5)
        _place_monster(state, mslot, obj_type, health=nibble, moving=moving)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].character = character
        state.players[0].powers = powers
        state.players[0].health = health
        monster_playerhit(state, 0, mslot)
        return state, mslot

    def test_grunt_base_tier_warrior(self):
        # grunt base 4, offset 3; nibble 4 -> row 5 -> [8,7,10,9]; warrior=8.
        state, _ = self._hit(MazeObjIds.MONST_GRUNT, nibble=4, character=0)
        assert state.players[0].health == 1000 - 8

    def test_grunt_damage_scales_with_tier(self):
        # A weakened grunt (lower nibble) hits softer: nibble 3 -> row 4 -> 6.
        state, _ = self._hit(MazeObjIds.MONST_GRUNT, nibble=3, character=0)
        assert state.players[0].health == 1000 - 6

    def test_armor_uses_powered_half(self):
        # nibble 4 grunt -> row 5; armored warrior reads row 5 powered = 7.
        state, _ = self._hit(MazeObjIds.MONST_GRUNT, nibble=4, character=0,
                             powers=PlayerPower.ARMOR)
        assert state.players[0].health == 1000 - 7

    def test_windup_gate_costs_the_first_frame(self):
        """0x498EE: a creature not yet in its moving state only enters it."""
        state, mslot = self._hit(MazeObjIds.MONST_GRUNT, nibble=4, moving=False)
        assert state.players[0].health == 1000, "windup frame deals nothing"
        assert state.mobs.hpos[mslot] & _HPOS_FLAG_MOVING, "attack state entered"
        monster_playerhit(state, 0, mslot)           # now it is committed
        assert state.players[0].health == 1000 - 8

    def test_monster_hit_sound(self):
        state, _ = self._hit(MazeObjIds.MONST_GRUNT, nibble=4)
        assert 0x1E in state.sound_log

    def test_ghost_explodes_scores_and_hits_hard(self):
        # ghost base 4, offset 0; nibble 4 -> row 2 -> [24,21,30,27]; score 30.
        state, mslot = self._hit(MazeObjIds.MONST_GHOST, nibble=4, moving=False)
        assert state.mobs.obj_type(mslot) == 0, "ghost removed on contact"
        assert state.players[0].health == 1000 - 24, "ghosts ignore the windup"
        assert state.players[0].score == 30
        assert 0x1F in state.sound_log

    def test_lobber_deals_no_contact_damage(self):
        state, _ = self._hit(MazeObjIds.MONST_LOBBER, nibble=11)
        assert state.players[0].health == 1000, "a lobber's touch does nothing"

    def test_acid_tier_and_payout(self):
        # acid base 1, offset 5; nibble 1 -> row 7 -> [48,42,60,54]; +30 points.
        state, mslot = self._hit(MazeObjIds.MONST_ACID, nibble=1)
        assert state.players[0].health == 1000 - 48
        assert state.mobs.obj_type(mslot) == 0, "the puddle is used up"
        assert state.players[0].score == 30

    def test_acid_windup_stuns_and_slimes(self):
        state, mslot = self._hit(MazeObjIds.MONST_ACID, nibble=1, moving=False)
        assert state.players[0].health == 1000
        assert state.players[0].stundelay == 0x20
        assert 0x36 in state.sound_log

    def test_acid_windup_splashes_at_once_in_attract(self):
        """0x499BC: with a negative game_mode the puddle resolves immediately."""
        state = GameState()
        mslot = pack_slot(5, 5)
        _place_monster(state, mslot, MazeObjIds.MONST_ACID, health=1)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].health = 1000
        state.game_mode = -3                      # GameMode.DEMO
        monster_playerhit(state, 0, mslot)
        assert state.mobs.obj_type(mslot) == 0
        assert state.players[0].health == 1000 - 48

    def test_acid_timer_blocks_damage_but_not_the_payout(self):
        state = GameState()
        mslot = pack_slot(5, 5)
        _place_monster(state, mslot, MazeObjIds.MONST_ACID, health=1, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].health = 1000
        state.players[0].acid_timer = 30
        monster_playerhit(state, 0, mslot)
        assert state.players[0].health == 1000, "acid_timer grants immunity"
        assert state.players[0].score == 30

    def test_super_sorcerer_tier(self):
        # supersorc base 0xB, offset 4; nibble 0xB -> row 6 -> [4,4,4,4].
        state, _ = self._hit(MazeObjIds.MONST_SUPERSORC, nibble=0xB)
        assert state.players[0].health == 1000 - 4

    def test_super_sorcerer_arms_the_death_touch_timer(self):
        state, _ = self._hit(MazeObjIds.MONST_SUPERSORC, nibble=0xB)
        assert state.death_touch_timer[0] == -0x10

    def test_death_deals_table_damage_too(self):
        # death base 0, offset 4; nibble 0 -> row 6 -> 4 damage.
        state, _ = self._hit(MazeObjIds.MONST_DEATH, nibble=0)
        assert state.players[0].health == 1000 - 4

    def test_contact_resets_escape_and_idle_timers(self):
        state = GameState()
        mslot = pack_slot(5, 5)
        _place_monster(state, mslot, MazeObjIds.MONST_GRUNT, health=4, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].health = 1000
        state.escape_timer = 5000
        state.idle_timer = 900
        monster_playerhit(state, 0, mslot)
        assert state.escape_timer == 0
        assert state.idle_timer == 0


class TestFirstEncounterDialog:
    """0x4986A/0x496F4 -- the once-per-game "you have met a ..." box."""

    def _hit(self, obj_type, nibble, acid_timer=0):
        state = GameState()
        state.game_mode = 0
        mslot = pack_slot(5, 5)
        _place_monster(state, mslot, obj_type, health=nibble, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].health = 1000
        state.players[0].acid_timer = acid_timer
        monster_playerhit(state, 0, mslot)
        return state

    def test_masks_match_the_jump_table(self):
        cases = {
            MazeObjIds.MONST_GHOST: (4, 0x00000100),
            MazeObjIds.MONST_GRUNT: (4, 0x00000200),
            MazeObjIds.MONST_AUX_GRUNT: (4, 0x00000200),
            MazeObjIds.MONST_DEMON: (8, 0x00000400),
            MazeObjIds.MONST_SORC: (0xB, 0x00001000),
            MazeObjIds.MONST_ACID: (1, 0x00008000),
            MazeObjIds.MONST_DEATH: (0, 0x00020000),
            MazeObjIds.MONST_SUPERSORC: (0xB, 0x00020000),
        }
        for obj_type, (nibble, mask) in cases.items():
            state = self._hit(obj_type, nibble)
            assert state.dialog_first_encounter_flags & mask == mask, obj_type

    def test_lobber_never_reaches_the_dialog(self):
        state = self._hit(MazeObjIds.MONST_LOBBER, 0xB)
        assert state.dialog_first_encounter_flags == 0

    def test_it_uses_its_own_mask(self):
        state = self._hit(MazeObjIds.MONST_IT, 8)
        assert state.dialog_first_encounter_flags & 0x10000000

    def test_acid_immunity_skips_the_dialog(self):
        """The call sits inside the acid_timer guard (0x497F8)."""
        state = self._hit(MazeObjIds.MONST_GRUNT, 4, acid_timer=30)
        assert state.dialog_first_encounter_flags == 0

    def test_second_encounter_is_silent(self):
        state = self._hit(MazeObjIds.MONST_GRUNT, 4)
        state.dialog_timer = 0
        before = state.dialog_first_encounter_flags
        mslot = pack_slot(5, 7)
        _place_monster(state, mslot, MazeObjIds.MONST_GRUNT, health=4, moving=True)
        monster_playerhit(state, 0, mslot)
        assert state.dialog_first_encounter_flags == before


class TestPlayerHit:
    def test_death_arms_touch_timer(self):
        state = GameState()
        monster_slot = pack_slot(5, 5)
        _place_monster(state, monster_slot, MazeObjIds.MONST_DEATH, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        monster_playerhit(state, 0, monster_slot)
        assert state.death_touch_timer[0] == -0x10

    def test_death_touch_timer_refreshes_to_0x10(self):
        state = GameState()
        monster_slot = pack_slot(5, 5)
        _place_monster(state, monster_slot, MazeObjIds.MONST_DEATH, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        state.death_touch_timer[0] = 4
        monster_playerhit(state, 0, monster_slot)
        assert state.death_touch_timer[0] == 0x10

    def test_death_contact_accumulates_and_dismisses(self):
        """Walking into Death adds 4/contact; over 200 dismisses the MOB (I-22)."""
        state = GameState()
        monster_slot = pack_slot(5, 5)
        _place_monster(state, monster_slot, MazeObjIds.MONST_DEATH, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].death_damage_counter = 200   # one hit from dismissal
        monster_playerhit(state, 0, monster_slot)      # +4 -> 204 > 200
        assert state.mobs.obj_type(monster_slot) == 0, "Death should be dismissed"
        assert state.players[0].death_damage_counter == 0

    def test_death_contact_armor_adds_three(self):
        state = GameState()
        monster_slot = pack_slot(5, 5)
        _place_monster(state, monster_slot, MazeObjIds.MONST_DEATH, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].powers = PlayerPower.ARMOR
        monster_playerhit(state, 0, monster_slot)
        assert state.players[0].death_damage_counter == 3, "armor -> 3 per contact"

    def test_it_tag_transfers_the_curse(self):
        """0x4967A: IT is consumed, the toucher becomes IT, +10 points."""
        state = GameState()
        monster_slot = pack_slot(5, 5)
        _place_monster(state, monster_slot, MazeObjIds.MONST_IT, moving=True)
        _place_player(state, 0, pack_slot(5, 6))
        state.players[0].health = 1000
        monster_playerhit(state, 0, monster_slot)
        assert state.player_it == 0
        assert state.mobs.obj_type(monster_slot) == 0
        assert state.players[0].stundelay == 0x10
        assert state.players[0].score == 10
        assert state.players[0].health == 1000, "IT tags, it does not hurt"
        assert 0x35 in state.sound_log


class TestSecretRoomProgress:
    """0x496AC and 0x49892 -- the only two secret-trick hooks in monster code.

    A ROM-wide search for ``secret_trick_id`` (0x904065) and
    ``secret_tricks_flags`` (0x904872) finds no other reference anywhere in the
    dispatcher, the movement engine or the shooting code.
    """

    def _hit(self, obj_type, nibble, *, task, acid_timer=0, progress=0,
             player=0, it=-1):
        state = GameState()
        state.game_mode = 0
        state.secret_trick_id = task
        state.secret_tricks_flags[player] = progress
        state.player_it = it
        mslot = pack_slot(5, 5)
        _place_monster(state, mslot, obj_type, health=nibble, moving=True)
        _place_player(state, player, pack_slot(5, 6))
        state.players[player].health = 1000
        state.players[player].acid_timer = acid_timer
        monster_playerhit(state, player, mslot)
        return state

    # -- 0x496AC: "be IT" -----------------------------------------------------

    def test_being_tagged_scores_the_while_it_task(self):
        state = self._hit(MazeObjIds.MONST_IT, 8, task=0x5C)
        assert state.secret_tricks_flags[0] == 1
        assert state.player_it == 0

    def test_the_bump_is_an_increment_not_a_set(self):
        """``addq.b #1,(a2,d0.w)`` at 0x496BE."""
        state = self._hit(MazeObjIds.MONST_IT, 8, task=0x5C, progress=4)
        assert state.secret_tricks_flags[0] == 5

    def test_another_task_leaves_the_counter_alone(self):
        for task in (0, 8, 0x5B, 0x5D):
            state = self._hit(MazeObjIds.MONST_IT, 8, task=task, progress=3)
            assert state.secret_tricks_flags[0] == 3, hex(task)

    def test_the_new_holder_is_credited_not_the_old_one(self):
        """The bump at 0x496AC runs before ``it_player`` is reassigned at
        0x496C2, and it indexes D4 -- the player being tagged."""
        state = self._hit(MazeObjIds.MONST_IT, 8, task=0x5C, player=1, it=0)
        assert state.secret_tricks_flags[1] == 1
        assert state.secret_tricks_flags[0] == 0
        assert state.player_it == 1

    def test_the_counter_satisfies_the_exit_check(self):
        state = self._hit(MazeObjIds.MONST_IT, 8, task=0x5C)
        state.secret_player = 0
        assert secret_check_winner(state) is True

    def test_an_untagged_player_fails_the_exit_check(self):
        state = self._hit(MazeObjIds.MONST_IT, 8, task=0x5B, progress=0)
        state.secret_trick_id = 0x5C
        state.secret_player = 0
        assert secret_check_winner(state) is False

    def test_ordinary_contact_never_bumps_the_it_task(self):
        state = self._hit(MazeObjIds.MONST_GRUNT, 4, task=0x5C)
        assert state.secret_tricks_flags[0] == 0

    # -- 0x49892: "don't use invulnerability" ---------------------------------

    def test_a_hit_while_immune_clears_the_no_invul_progress(self):
        state = self._hit(MazeObjIds.MONST_GRUNT, 4, task=TRICK_NOUSEINVUL,
                          acid_timer=30, progress=1)
        assert state.secret_tricks_flags[0] == 0
        assert state.players[0].health == 1000, "immune, so no damage either"

    def test_a_hit_that_lands_leaves_the_progress_alone(self):
        """0x49890 jumps over the test, so only the immune branch clears it."""
        state = self._hit(MazeObjIds.MONST_GRUNT, 4, task=TRICK_NOUSEINVUL,
                          acid_timer=0, progress=1)
        assert state.secret_tricks_flags[0] == 1
        assert state.players[0].health < 1000

    def test_another_task_survives_an_immune_hit(self):
        for task in (0, 7, 9, 0x5C):
            state = self._hit(MazeObjIds.MONST_GRUNT, 4, task=task,
                              acid_timer=30, progress=1)
            assert state.secret_tricks_flags[0] == 1, hex(task)

    def test_every_family_clears_it_on_the_immune_path(self):
        families = (
            (MazeObjIds.MONST_GHOST, 4), (MazeObjIds.MONST_GRUNT, 4),
            (MazeObjIds.MONST_DEMON, 8), (MazeObjIds.MONST_SORC, 0xB),
            (MazeObjIds.MONST_ACID, 1), (MazeObjIds.MONST_DEATH, 0),
            (MazeObjIds.MONST_SUPERSORC, 0xB),
        )
        for obj_type, nibble in families:
            state = self._hit(obj_type, nibble, task=TRICK_NOUSEINVUL,
                              acid_timer=30, progress=1)
            assert state.secret_tricks_flags[0] == 0, obj_type

    def test_the_it_tag_path_does_not_reach_the_clear(self):
        """IT branches away at 0x4967A, long before 0x49892."""
        state = self._hit(MazeObjIds.MONST_IT, 8, task=TRICK_NOUSEINVUL,
                          acid_timer=30, progress=1)
        assert state.secret_tricks_flags[0] == 1

    def test_a_lobber_never_reaches_the_clear(self):
        state = self._hit(MazeObjIds.MONST_LOBBER, 0xB, task=TRICK_NOUSEINVUL,
                          acid_timer=30, progress=1)
        assert state.secret_tricks_flags[0] == 1

    def test_a_cleared_counter_loses_the_exit_check(self):
        state = self._hit(MazeObjIds.MONST_GRUNT, 4, task=TRICK_NOUSEINVUL,
                          acid_timer=30, progress=1)
        secret_trick_check(state, 0)
        assert state.secret_player < 0


# ---------------------------------------------------------------------------
# Generator spawn placement (0x492C0) and tile_occupancy_test (0x48F12)
# ---------------------------------------------------------------------------

class _RecordingRNG:
    """Records the bound of every draw so the ROM's draw *order* can be pinned."""

    def __init__(self, *values: int, default: int = 0) -> None:
        self._queue = list(values)
        self._default = default
        self.bounds: list[int] = []

    def getrandom(self, bound: int) -> int:
        self.bounds.append(bound)
        return self._queue.pop(0) if self._queue else self._default

    random_word = getrandom


#: ROM 0x57B50 / 0x57B68 / 0x57B80, entries 0-7: (column delta, row delta,
#: ROM-compass code).  Up, right, down, left, then the four diagonals.
_ROM_GEN_CANDIDATES = (
    (0, -0x20, 0),      # up
    (1, 0, 2),          # right
    (0, 0x20, 4),       # down
    (-1, 0, 6),         # left
    (1, -0x20, 1),      # up-right
    (1, 0x20, 3),       # down-right
    (-1, 0x20, 5),      # down-left
    (-1, -0x20, 7),     # up-left
)


def _place_generator(state: GameState, slot: int,
                     obj_type: int = int(MazeObjIds.GEN_GHOST1)) -> None:
    """A generator placed exactly as ``maze.placement_geometry`` places one.

    The 4 px sprite-centering correction is the point: ``tile_occupancy_test``
    measures candidate cells from that same biased origin (the ROM's
    ``(slot << 11) - 0x200``), so a generator dropped in without it sits 4 px
    off and starts refusing its own candidate cells.
    """
    row, col = slot >> 5, slot & 0x1F
    state.mobs.create(
        slot, tile=1,
        hpos=encode_hpos(col * 16 - 4, palette=5),   # mazeobj_hsize_tier[28..45]
        vpos=encode_vpos_at_y(row * 16, 3, 3),            # mazeobj_vpos_offset 0x12
        obj_type=obj_type, state=0,
    )


def _gameplay(state: GameState) -> None:
    """A gameplay frame.  ``GameState`` starts in the TITLE attract mode, where
    ``handle_generate`` takes its retry-timer path (0x492E2) and never draws."""
    state.game_mode = 0                              # GameMode.NORMAL


def _attract(state: GameState) -> None:
    """An attract/demo frame, with the demo's own retry-timer reload (0x44A76)."""
    state.game_mode = int(GameMode.DEMO)
    state.monster_generation_retry_timer = GENERATOR_RETRY_RELOAD


def _place_wall_marker(state: GameState, slot: int) -> None:
    """A wall as ``maze._write_marker`` stamps it: 0x8000, uncorrected, unlinked."""
    row, col = slot >> 5, slot & 0x1F
    state.mobs.picture[slot] = 0x8000
    state.mobs.hpos[slot] = encode_hpos(col * 16)
    state.mobs.vpos[slot] = encode_vpos_at_y(row * 16)
    state.mobs.set_obj_type(slot, int(MazeObjIds.WALL_REGULAR))


def _spawned_slot(state: GameState) -> int | None:
    for slot in range(len(state.mobs.picture)):
        if state.mobs.obj_type(slot) == int(MazeObjIds.MONST_GHOST):
            return slot
    return None


def _spawned_slot_of(state: GameState, gen_type: int) -> int | None:
    """The cell holding the creature ``gen_type``'s family generates."""
    wanted = _GENERATOR_SPAWN[gen_type]
    for slot in range(len(state.mobs.picture)):
        if state.mobs.obj_type(slot) == wanted:
            return slot
    return None


class TestGeneratorCandidateOrder:
    """0x49320-0x49438 -- eight candidates, rotated by ``getrandom(4)``."""

    def test_the_first_eight_offsets_are_the_rom_tables(self):
        gen = pack_slot(10, 10)
        for index, (dcol, drow, _) in enumerate(_ROM_GEN_CANDIDATES):
            assert generator_candidate_slot(gen, index) == \
                gen + drow + dcol, index

    def test_the_direction_codes_are_the_rom_table(self):
        assert _GENERATOR_SPAWN_DIRECTION[:8] == tuple(
            code for _, _, code in _ROM_GEN_CANDIDATES
        )

    def test_entries_eight_to_eleven_repeat_the_cardinals(self):
        """The tail is what turns ``start .. start+7`` into a rotation."""
        assert _GENERATOR_CELL_DX[8:12] == _GENERATOR_CELL_DX[:4]
        assert _GENERATOR_CELL_DY[8:12] == _GENERATOR_CELL_DY[:4]
        assert _GENERATOR_SPAWN_DIRECTION[8:12] == _GENERATOR_SPAWN_DIRECTION[:4]

    def test_every_start_tries_all_four_cardinals_before_any_diagonal(self):
        gen = pack_slot(10, 10)
        cardinals = {gen - 0x20, gen + 1, gen + 0x20, gen - 1}
        for start in range(4):
            order = [generator_candidate_slot(gen, start + i) for i in range(8)]
            assert len(set(order)) == 8, start
            assert set(order[:4 - start]) <= cardinals
            assert set(order) >= cardinals
            # The diagonals occupy exactly the four slots after the cardinals
            # the start did not skip.
            assert set(order[4 - start:8 - start]) == set(order) - cardinals

    def test_a_start_of_three_leaves_up_right_and_down_until_last(self):
        """start=3: left, the four diagonals, then up, right, down."""
        gen = pack_slot(10, 10)
        order = [generator_candidate_slot(gen, 3 + i) for i in range(8)]
        assert order[0] == gen - 1                       # left
        assert order[5:] == [gen - 0x20, gen + 1, gen + 0x20]


class TestGeneratorSeamWrap:
    """Both axes are masked at 0x4933C / 0x49350, so candidates wrap."""

    def test_the_column_wraps_at_the_right_edge(self):
        gen = pack_slot(10, 31)
        assert generator_candidate_slot(gen, 1) == pack_slot(10, 0)
        assert generator_candidate_slot(gen, 4) == pack_slot(9, 0)

    def test_the_column_wraps_at_the_left_edge(self):
        gen = pack_slot(10, 0)
        assert generator_candidate_slot(gen, 3) == pack_slot(10, 31)

    def test_the_row_wraps_at_the_top_edge(self):
        gen = pack_slot(0, 10)
        assert generator_candidate_slot(gen, 0) == pack_slot(31, 10)

    def test_the_row_wraps_at_the_bottom_edge(self):
        gen = pack_slot(31, 10)
        assert generator_candidate_slot(gen, 2) == pack_slot(0, 10)

    def test_a_wrapped_column_really_is_used(self):
        state = GameState()
        _gameplay(state)
        state.rng = _FixedRNG(0, 1)          # spawn, start at "right"
        gen = pack_slot(10, 31)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        assert _spawned_slot(state) == pack_slot(10, 0)

    def test_a_wrapped_row_zero_candidate_is_refused_as_out_of_range(self):
        """Row 0 packs below 0x20, which 0x48F24 rejects outright."""
        state = GameState()
        _gameplay(state)
        state.rng = _FixedRNG(0, 2)          # spawn, start at "down"
        gen = pack_slot(31, 10)
        _place_generator(state, gen)

        assert not tile_occupancy_test(state, pack_slot(0, 10))
        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        assert _spawned_slot(state) == pack_slot(31, 9), \
            "the rotation moves on to left"


class TestGeneratorSpawnChoice:
    def test_the_draw_order_is_the_probability_then_the_rotation_start(self):
        state = GameState()
        _gameplay(state)
        state.rng = _RecordingRNG(0, 0)
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        assert state.rng.bounds == [32, 4]

    def test_a_lost_probability_draw_never_reaches_the_rotation_draw(self):
        state = GameState()
        _gameplay(state)
        state.rng = _RecordingRNG(31)
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=10)

        assert state.rng.bounds == [32], "the rotation draw must not happen"
        assert _spawned_slot(state) is None

    def test_each_start_picks_its_own_cardinal(self):
        gen = pack_slot(10, 10)
        for start, expected in enumerate((gen - 0x20, gen + 1,
                                          gen + 0x20, gen - 1)):
            state = GameState()
            _gameplay(state)
            state.rng = _FixedRNG(0, start)
            _place_generator(state, gen)

            handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1),
                            probability=32)

            assert _spawned_slot(state) == expected, start

    def test_a_blocked_cardinal_rotates_on_to_the_next_one(self):
        state = GameState()
        _gameplay(state)
        state.rng = _FixedRNG(0, 0)          # start "up"
        gen = pack_slot(10, 10)
        _place_generator(state, gen)
        _place_wall_marker(state, gen - 0x20)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        assert _spawned_slot(state) == gen + 1, "right is next in the rotation"

    def test_all_four_cardinals_blocked_falls_through_to_a_diagonal(self):
        state = GameState()
        _gameplay(state)
        state.rng = _FixedRNG(0, 0)
        gen = pack_slot(10, 10)
        _place_generator(state, gen)
        for cardinal in (gen - 0x20, gen + 1, gen + 0x20, gen - 1):
            _place_wall_marker(state, cardinal)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        spawned = _spawned_slot(state)
        assert spawned == pack_slot(9, 11), "up-right, the first diagonal"
        assert state.mobs.state(spawned) & 0x07 == (1 - 2) & 0x07

    def test_a_ringed_generator_spawns_nothing_and_stays_put(self):
        state = GameState()
        _gameplay(state)
        state.rng = _FixedRNG(0, 0)
        gen = pack_slot(10, 10)
        _place_generator(state, gen)
        for index in range(8):
            _place_wall_marker(state, generator_candidate_slot(gen, index))

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        assert _spawned_slot(state) is None
        assert state.mobs.obj_type(gen) == int(MazeObjIds.GEN_GHOST1)


class TestGeneratorSpawnRecord:
    def test_the_creature_faces_the_way_it_was_pushed(self):
        """0x49388 pushes ``generator_spawn_direction``; gauntpy's compass is
        the ROM's minus two, so ROM north (0) is gauntpy 6."""
        gen = pack_slot(10, 10)
        for start, rom_code in enumerate((0, 2, 4, 6)):
            state = GameState()
            _gameplay(state)
            state.rng = _FixedRNG(0, start)
            _place_generator(state, gen)

            handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1),
                            probability=32)

            spawned = _spawned_slot(state)
            assert state.mobs.state(spawned) & 0x07 == (rom_code - 2) & 0x07

    def test_the_spawn_carries_the_rom_position_size_and_tier(self):
        state = GameState()
        _gameplay(state)
        state.rng = _FixedRNG(0, 1)          # right
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        spawned = _spawned_slot(state)
        assert spawned == pack_slot(10, 11)
        x, _flags, tier = decode_hpos(state.mobs.hpos[spawned])
        assert x == 11 * 16 - 4, "the 0x200 sprite correction of 0x493CE"
        assert tier == 4 - _GENERATOR_TIER_PENALTY[0]
        _y, width, height = decode_vpos_at_y(state.mobs.vpos[spawned])
        size = _MAZEOBJ_VSIZE[int(MazeObjIds.MONST_GHOST)]
        assert (width, height) == (((size >> 3) & 7) + 1, (size & 7) + 1)

    def test_the_generator_tier_sets_the_creatures_starting_health(self):
        """0x579AE: tier 1 spawns two notches below full, tier 3 spawns full."""
        gen = pack_slot(10, 10)
        for gen_type, penalty in (
            (MazeObjIds.GEN_GHOST1, 2),
            (MazeObjIds.GEN_GHOST2, 1),
            (MazeObjIds.GEN_GHOST3, 0),
        ):
            state = GameState()
            _gameplay(state)
            state.rng = _FixedRNG(0, 0)
            _place_generator(state, gen, int(gen_type))

            handle_generate(state, gen, int(gen_type), probability=32)

            spawned = _spawned_slot(state)
            assert state.mobs.hpos[spawned] & 0x0F == 4 - penalty, gen_type

    def test_a_fresh_spawn_does_not_block_the_next_one(self):
        """The spawn geometry and the clearance test have to agree, or a
        generator walls itself in after one creature."""
        state = GameState()
        _gameplay(state)
        state.rng = _FixedRNG(0, 0, 0, 1)
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)
        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        assert state.mobs.obj_type(pack_slot(9, 10)) == int(MazeObjIds.MONST_GHOST)
        assert state.mobs.obj_type(pack_slot(10, 11)) == int(MazeObjIds.MONST_GHOST)

    def test_the_spawn_picture_is_the_familys_walk_frame_for_its_heading(self):
        """0x4940E-0x49412 -- no creature is ever drawn as a placeholder."""
        gen = pack_slot(10, 10)
        for start, rom_code in enumerate((0, 2, 4, 6)):
            state = GameState()
            _gameplay(state)
            state.rng = _FixedRNG(0, start)
            _place_generator(state, gen)

            handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1),
                            probability=32)

            spawned = _spawned_slot(state)
            expected = _MONSTER_WALK_PICTURES[int(MazeObjIds.MONST_GHOST)][rom_code]
            assert state.mobs.picture[spawned] == expected, rom_code

    def test_the_picture_and_the_state_word_always_agree(self):
        """Both come off the same direction, so the shared per-frame picture
        writer at 0x414A4 would reproduce the very frame the spawn wrote."""
        gen = pack_slot(10, 10)
        for gen_type in (MazeObjIds.GEN_GHOST1, MazeObjIds.GEN_GRUNT2,
                         MazeObjIds.GEN_DEMON3, MazeObjIds.GEN_LOBBER1,
                         MazeObjIds.GEN_SORC2, MazeObjIds.GEN_AUX_GRUNT3):
            for start in range(4):
                state = GameState()
                _gameplay(state)
                state.rng = _FixedRNG(0, start)
                _place_generator(state, gen, int(gen_type))

                handle_generate(state, gen, int(gen_type), probability=32)

                spawned = _spawned_slot_of(state, int(gen_type))
                direction = state.mobs.state(spawned) & 0x07
                assert state.mobs.picture[spawned] == monster_walk_picture(
                    state.mobs.obj_type(spawned), direction
                ), (gen_type, start)


class TestTileOccupancyTest:
    """0x48F12: in range, empty, and clear of anything nearby."""

    def test_the_range_guards(self):
        state = GameState()
        assert not tile_occupancy_test(state, 0x20)
        assert tile_occupancy_test(state, 0x21)
        assert tile_occupancy_test(state, 0x3FF)
        assert not tile_occupancy_test(state, 0x400)

    def test_a_cell_with_a_picture_is_refused(self):
        state = GameState()
        slot = pack_slot(10, 10)
        assert tile_occupancy_test(state, slot)
        _place_wall_marker(state, slot)
        assert not tile_occupancy_test(state, slot)

    def test_a_creature_squarely_in_the_next_cell_does_not_block(self):
        """0x7C0 is a hair under one cell, so a settled neighbour is clear."""
        candidate = pack_slot(10, 10)
        for neighbour in (pack_slot(9, 10), pack_slot(11, 10),
                          pack_slot(10, 9), pack_slot(10, 11)):
            state = GameState()
            _place_monster_corrected(state, neighbour)
            assert tile_occupancy_test(state, candidate), neighbour

    def test_a_creature_halfway_out_of_the_cell_above_blocks(self):
        state = GameState()
        candidate = pack_slot(10, 10)
        _place_monster_corrected(state, pack_slot(9, 10), dy=8)

        assert not tile_occupancy_test(state, candidate)

    def test_a_creature_halfway_out_of_the_cell_to_the_left_blocks(self):
        state = GameState()
        candidate = pack_slot(10, 10)
        _place_monster_corrected(state, pack_slot(10, 9), dx=8)

        assert not tile_occupancy_test(state, candidate)

    def test_the_vertical_window_is_exactly_0x7c0(self):
        """``|vpos - candidate_v| <= 0x7C0`` in native position units.  A
        creature settled in the cell above clears it by 0x40 units (0x800 apart
        against a 0x7C0 window); one pixel of travel towards the candidate is
        enough to fail it."""
        candidate = pack_slot(10, 10)
        for dy in range(0, 17):
            state = GameState()
            _place_monster_corrected(state, pack_slot(9, 10), dy=dy)
            clear = tile_occupancy_test(state, candidate)
            assert clear == (dy == 0), dy

    def test_a_diagonal_neighbour_never_blocks_from_its_own_cell(self):
        candidate = pack_slot(10, 10)
        for neighbour in (pack_slot(9, 9), pack_slot(9, 11),
                          pack_slot(11, 9), pack_slot(11, 11)):
            state = GameState()
            _place_monster_corrected(state, neighbour)
            assert tile_occupancy_test(state, candidate), neighbour

    def test_a_wall_marker_next_door_does_not_block(self):
        """A wall is a software MOB, and 0x48FD8 takes its 0x200 back off."""
        candidate = pack_slot(10, 10)
        for index in range(8):
            state = GameState()
            row = ((candidate & 0x3E0) + _SPAWN_CANDIDATE_ROW_DELTA[index])
            col = (candidate + _SPAWN_CANDIDATE_COLUMN_DELTA[index]) & 0x1F
            _place_wall_marker(state, row + col)
            assert tile_occupancy_test(state, candidate), index

    def test_a_hero_standing_in_the_cell_refuses_it(self):
        state = GameState()
        candidate = pack_slot(10, 10)
        _place_player(state, 0, candidate)

        assert not tile_occupancy_test(state, candidate)

    def test_a_hero_walking_through_the_cell_refuses_it(self):
        """A hero half way out of the neighbouring cell is still in range.

        The record migrates with the hero, so the eight-neighbour proximity
        scan is all ``tile_occupancy_test`` needs: a hero whose record has just
        handed over to (10,9) but whose body still overhangs (10,10) keeps the
        cell reserved.
        """
        state = GameState()
        candidate, record = pack_slot(10, 10), pack_slot(10, 9)
        _place_player(state, 0, record)
        state.mobs.hpos[record] = encode_hpos(10 * 16 - 12, palette=0x0C)
        state.mobs.vpos[record] = encode_vpos_at_y(10 * 16)

        assert not tile_occupancy_test(state, candidate)

    def test_the_separation_wraps_across_the_column_seam(self):
        """The ROM's position words span one maze in 16 bits, so column 31 and
        column 0 are neighbours; gauntpy's are half that and wrap explicitly."""
        candidate = pack_slot(10, 0)

        settled = GameState()
        _place_monster_corrected(settled, pack_slot(10, 31))
        assert tile_occupancy_test(settled, candidate), "one cell away is clear"

        stepping = GameState()
        _place_monster_corrected(stepping, pack_slot(10, 31), dx=8)
        assert not tile_occupancy_test(stepping, candidate), \
            "half a cell across the seam still blocks"


def _place_monster_corrected(state: GameState, slot: int,
                             dx: int = 0, dy: int = 0) -> None:
    """A creature with the ROM's own placement geometry, optionally mid-step."""
    row, col = slot >> 5, slot & 0x1F
    state.mobs.create(
        slot, tile=1,
        hpos=encode_hpos(col * 16 - 4 + dx, palette=4),
        vpos=encode_vpos_at_y(row * 16 + dy, 3, 3),
        obj_type=int(MazeObjIds.MONST_GHOST), state=0,
    )


# ---------------------------------------------------------------------------
# Spawn artwork: monster_anim_walk_tbl (0x40DB2) frame 0
# ---------------------------------------------------------------------------

#: ROM 0x40DB2's ten pointers, and the eight animation-frame-0 words each names.
#: Transcribed independently of ``monsters._MONSTER_WALK_PICTURES`` so the two
#: have to agree, and byte-checked against the ROM itself below.
_ROM_WALK_TABLE_POINTERS = (
    0x058F26, 0x058FA6, 0x0590A6, 0x0591A6, 0x058C0A,
    0x058FA6, 0x0592A6, 0x059336, 0x058C0A, 0x059436,
)
#: 0x40DDA, the sibling attack table.  Zero for the four families with no attack
#: cycle; only listed here to pin which pointer table the spawn actually uses.
_ROM_ATTACK_TABLE_POINTERS = (
    0x000000, 0x059026, 0x059126, 0x000000, 0x059226,
    0x059026, 0x0592B6, 0x0593B6, 0x000000, 0x000000,
)
#: gex entity name per creature type -- what ``render.mobs.sprite_kind`` hands
#: ``AssetStore.sprite()`` -- and the direction name gex uses for each ROM
#: compass code.
_ROM_DIRECTION_NAMES = ("up", "upright", "right", "downright",
                        "down", "downleft", "left", "upleft")


class TestSpawnPictures:
    def test_every_family_has_all_eight_directions(self):
        for index in range(10):
            monster_type = int(MazeObjIds.MONST_GHOST) + index
            assert len(_MONSTER_WALK_PICTURES[monster_type]) == 8, monster_type

    def test_full_idle_and_moving_banks_have_all_eight_frames(self):
        assert all(len(table) == 64 for table in _MONSTER_IDLE_ANIMS.values())
        assert all(len(table) == 64 for table in _MONSTER_MOVING_ANIMS.values())

    def test_picture_refresh_uses_live_facing_and_animation_frame(self):
        state = GameState()
        slot = pack_slot(8, 8)
        _place_monster(
            state, slot, MazeObjIds.MONST_GRUNT, direction=4, moving=True,
        )
        state.mobs.set_state(slot, (3 << 3) | 4)

        monster_update_anim_tile(
            state, slot, int(MazeObjIds.MONST_GRUNT),
        )

        # gauntpy left (4) is ROM direction 6; frame 3 starts at word 24.
        assert state.mobs.picture[slot] == _MONSTER_MOVING_ANIMS[
            int(MazeObjIds.MONST_GRUNT)
        ][24 + 6]

    def test_main_loop_replaces_the_spawn_pose_while_moving(self):
        state = GameState()
        slot = pack_slot(8, 8)
        _arena(state, slot)
        _place_monster(
            state, slot, MazeObjIds.MONST_GRUNT, direction=0, moving=True,
        )
        state.mobs.picture[slot] = 1
        state.frame_counter = 1

        main_move_monsters(state)

        moved = _monster_slot(state, MazeObjIds.MONST_GRUNT)
        assert state.mobs.picture[moved] != 1

    def test_the_aliased_families_share_their_tables(self):
        """0x40DB2[5] is the grunt's pointer again and [8] the sorcerer's."""
        assert (_MONSTER_WALK_PICTURES[int(MazeObjIds.MONST_AUX_GRUNT)]
                == _MONSTER_WALK_PICTURES[int(MazeObjIds.MONST_GRUNT)])
        assert (_MONSTER_WALK_PICTURES[int(MazeObjIds.MONST_SUPERSORC)]
                == _MONSTER_WALK_PICTURES[int(MazeObjIds.MONST_SORC)])
        assert _ROM_WALK_TABLE_POINTERS[5] == _ROM_WALK_TABLE_POINTERS[1]
        assert _ROM_WALK_TABLE_POINTERS[8] == _ROM_WALK_TABLE_POINTERS[4]

    def test_the_compass_conversion_round_trips(self):
        """``monster_walk_picture`` takes gauntpy's compass; the table is the
        ROM's, two steps round."""
        for index in range(10):
            monster_type = int(MazeObjIds.MONST_GHOST) + index
            row = _MONSTER_WALK_PICTURES[monster_type]
            for rom_code in range(8):
                gauntpy_dir = (rom_code - 2) & 0x07
                assert monster_walk_picture(monster_type, gauntpy_dir) == \
                    row[rom_code], (monster_type, rom_code)

    @requires_roms
    def test_the_pointer_tables_are_the_rom_longwords(self):
        from gex.roms import coderom_get_bytes

        raw = coderom_get_bytes(0x40DB2, 4 * 20)
        longs = [int.from_bytes(raw[i * 4:i * 4 + 4], "big") for i in range(20)]
        assert tuple(longs[:10]) == _ROM_WALK_TABLE_POINTERS
        assert tuple(longs[10:]) == _ROM_ATTACK_TABLE_POINTERS

    @requires_roms
    def test_every_picture_is_the_rom_word(self):
        """All ten families x eight directions, straight off the ROM."""
        from gex.roms import coderom_get_bytes

        for index, pointer in enumerate(_ROM_WALK_TABLE_POINTERS):
            monster_type = int(MazeObjIds.MONST_GHOST) + index
            raw = coderom_get_bytes(pointer, 16)
            words = tuple(int.from_bytes(raw[i * 2:i * 2 + 2], "big")
                          for i in range(8))
            assert _MONSTER_WALK_PICTURES[monster_type] == words, monster_type

    @requires_roms
    def test_full_animation_banks_are_literal_rom_words(self):
        from gex.roms import coderom_get_bytes
        from gauntpy.subsystems.monsters import (
            _ANIM_ACID_IDLE,
            _ANIM_DEATH_IDLE,
            _ANIM_DEATH_MOVING,
            _ANIM_DEMON_IDLE,
            _ANIM_DEMON_MOVING,
            _ANIM_DEMON_SPECIAL,
            _ANIM_GHOST_IDLE,
            _ANIM_GRUNT_IDLE,
            _ANIM_GRUNT_MOVING,
            _ANIM_IT_IDLE,
            _ANIM_IT_SPECIAL,
            _ANIM_LOBBER_IDLE,
            _ANIM_LOBBER_THROW,
            _ANIM_SORC_IDLE,
            _ANIM_SORC_MOVING,
        )

        tables = (
            (0x58C0A, _ANIM_SORC_IDLE),
            (0x58F26, _ANIM_GHOST_IDLE),
            (0x58FA6, _ANIM_GRUNT_IDLE),
            (0x59026, _ANIM_GRUNT_MOVING),
            (0x590A6, _ANIM_DEMON_IDLE),
            (0x59126, _ANIM_DEMON_MOVING),
            (0x591A6, _ANIM_LOBBER_IDLE),
            (0x59226, _ANIM_SORC_MOVING),
            (0x592A6, _ANIM_DEATH_IDLE),
            (0x592B6, _ANIM_DEATH_MOVING),
            (0x59336, _ANIM_ACID_IDLE),
            (0x59436, _ANIM_IT_IDLE),
            (0x594B6, _ANIM_IT_SPECIAL),
            (0x59536, _ANIM_DEMON_SPECIAL),
            (0x595B6, _ANIM_LOBBER_THROW),
        )
        for address, table in tables:
            raw = coderom_get_bytes(address, 128)
            words = tuple(
                int.from_bytes(raw[i:i + 2], "big")
                for i in range(0, len(raw), 2)
            )
            assert table == words, hex(address)

    @requires_roms
    def test_every_picture_resolves_to_that_familys_own_sprite(self):
        """Renderer resolvability: ``AssetStore`` names an entity, action and
        direction for every one of the eighty words, and the direction it names
        is an independent confirmation of the ROM compass."""
        from gauntpy.assets import AssetStore
        from gauntpy.render.mobs import _MONSTER_ENTITY

        store = AssetStore()
        for index in range(10):
            monster_type = int(MazeObjIds.MONST_GHOST) + index
            kind = _MONSTER_ENTITY[monster_type]
            row = _MONSTER_WALK_PICTURES[monster_type]
            for rom_code, picture in enumerate(row):
                frame = store.sprite_frame(picture, kind=kind)
                assert frame.monster_type == kind, (monster_type, rom_code)
                if len(set(row)) == 1:
                    continue          # acid and IT are one frame for all eight
                assert frame.direction == _ROM_DIRECTION_NAMES[rom_code], \
                    (monster_type, rom_code, frame)

    @requires_roms
    def test_a_generated_creature_draws_without_a_placeholder(self):
        from gauntpy.assets import AssetStore
        from gauntpy.render.mobs import sprite_kind

        store = AssetStore()
        gen = pack_slot(10, 10)
        for gen_type in sorted(_GENERATOR_SPAWN):
            state = GameState()
            _gameplay(state)
            state.rng = _FixedRNG(0, 0)
            _place_generator(state, gen, gen_type)

            handle_generate(state, gen, gen_type, probability=32)

            spawned = _spawned_slot_of(state, gen_type)
            picture = state.mobs.picture[spawned]
            assert picture not in (0, 1), (gen_type, picture)
            store.sprite_frame(picture, kind=sprite_kind(state, spawned))

    @requires_roms
    def test_every_live_animation_frame_resolves_in_the_asset_store(self):
        from gauntpy.assets import AssetStore
        from gauntpy.render.mobs import _MONSTER_ENTITY
        from gauntpy.subsystems.monsters import (
            _ANIM_DEMON_SPECIAL,
            _ANIM_IT_SPECIAL,
            _ANIM_LOBBER_THROW,
        )

        store = AssetStore()
        for monster_type, table in _MONSTER_IDLE_ANIMS.items():
            kind = _MONSTER_ENTITY[monster_type]
            for picture in table:
                store.sprite_frame(picture, kind=kind)
        for monster_type, table in _MONSTER_MOVING_ANIMS.items():
            kind = _MONSTER_ENTITY[monster_type]
            for picture in table:
                store.sprite_frame(picture, kind=kind)
        for monster_type, table in (
            (int(MazeObjIds.MONST_DEMON), _ANIM_DEMON_SPECIAL),
            (int(MazeObjIds.MONST_LOBBER), _ANIM_LOBBER_THROW),
            (int(MazeObjIds.MONST_IT), _ANIM_IT_SPECIAL),
        ):
            kind = _MONSTER_ENTITY[monster_type]
            for picture in table:
                store.sprite_frame(picture, kind=kind)


# ---------------------------------------------------------------------------
# Attract-mode generation (0x492E2) and the tables it reads past
# ---------------------------------------------------------------------------

class TestAttractModeGeneration:
    """A negative ``game_mode`` replaces both draws with a countdown.

    ``attract_demo_init`` (0x44A76) loads ``monster_generation_retry_timer``
    with 4; ``handle_generate`` decrements it every generator turn and only a
    turn that drives it negative attempts a spawn, after which it is clamped to
    zero so every later turn attempts one.  The rotation start is then fixed --
    7 for the ghost families, 2 for the rest -- and no RNG is touched at all,
    which is what keeps the recorded demo reproducible.
    """

    def test_the_demo_start_loads_the_rom_reload_value(self):
        from gauntpy.subsystems.attract import attract_demo_init

        state = GameState()
        state.monster_generation_retry_timer = 0
        attract_demo_init(state)
        assert state.monster_generation_retry_timer == GENERATOR_RETRY_RELOAD

    def test_the_timer_throttles_four_turns_then_frees_every_turn(self):
        state = GameState()
        _attract(state)
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        seen = []
        for _turn in range(6):
            for slot in list(state.mobs.iter_chain()):
                if state.mobs.obj_type(slot) == int(MazeObjIds.MONST_GHOST):
                    state.mobs.unlink_and_clear(slot)
            handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1),
                            probability=0)
            seen.append(_spawned_slot(state) is not None)

        assert seen == [False, False, False, False, True, True]
        assert state.monster_generation_retry_timer == 0

    def test_no_random_draw_is_taken_in_attract_mode(self):
        state = GameState()
        _attract(state)
        state.rng = _RecordingRNG()
        state.monster_generation_retry_timer = 0
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=0)

        assert state.rng.bounds == [], "the demo must not disturb the RNG"
        assert _spawned_slot(state) is not None

    def test_the_probability_argument_is_ignored(self):
        state = GameState()
        _attract(state)
        state.monster_generation_retry_timer = 0
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=0)

        assert _spawned_slot(state) is not None

    def test_ghost_families_seed_the_rotation_at_seven(self):
        """0x492F8: family index 0-2 only, i.e. the three ghost generators."""
        gen = pack_slot(10, 10)
        state = GameState()
        _attract(state)
        state.monster_generation_retry_timer = 0
        _place_generator(state, gen, int(MazeObjIds.GEN_GHOST3))

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST3), probability=0)

        # Index 7 is up-left, the first candidate a seed of 7 reaches.
        assert _spawned_slot(state) == pack_slot(9, 9)
        assert _GEN_ATTRACT_START_GHOST == 7

    def test_other_families_seed_the_rotation_at_two(self):
        gen = pack_slot(10, 10)
        state = GameState()
        _attract(state)
        state.monster_generation_retry_timer = 0
        _place_generator(state, gen, int(MazeObjIds.GEN_GRUNT1))

        handle_generate(state, gen, int(MazeObjIds.GEN_GRUNT1), probability=0)

        # Index 2 is "down".
        assert _spawned_slot_of(state, int(MazeObjIds.GEN_GRUNT1)) == \
            pack_slot(11, 10)
        assert _GEN_ATTRACT_START_OTHER == 2

    def test_the_seven_seed_runs_the_counter_to_fourteen(self):
        """Indices 12-14 exist only because 0x4942C-0x49438 never masks."""
        assert _GEN_ATTRACT_START_GHOST + 7 == 14
        assert len(_GENERATOR_CELL_DX) == 15
        assert len(_GENERATOR_CELL_DY) == 15
        assert len(_GENERATOR_SPAWN_DIRECTION) == 15

    @requires_roms
    def test_indices_twelve_to_fourteen_are_the_next_tables_first_words(self):
        """Each table reads three words past its end into the head of the next:
        column into ``generator_spawn_row_delta`` (0x57B68), row into
        ``generator_spawn_direction`` (0x57B80), direction into
        ``monster_shot_spawn_h_offset`` (0x57B98)."""
        from gex.roms import coderom_get_bytes

        def words(addr: int, count: int) -> tuple[int, ...]:
            raw = coderom_get_bytes(addr, count * 2)
            return tuple(int.from_bytes(raw[i * 2:i * 2 + 2], "big")
                         for i in range(count))

        def signed(value: int) -> int:
            return value - 0x10000 if value & 0x8000 else value

        assert tuple(_GENERATOR_CELL_DX[12:]) == \
            tuple(signed(w) for w in words(0x57B68, 3))
        assert tuple(_GENERATOR_CELL_DY[12:]) == \
            tuple(signed(w) for w in words(0x57B80, 3))
        assert tuple(_GENERATOR_SPAWN_DIRECTION[12:]) == words(0x57B98, 3)

    def test_the_read_past_candidates_are_always_the_generators_own_cell(self):
        """Every aliased column delta is a multiple of 32 and every aliased row
        delta is under 32, so 0x49350's ``andi #0x1F`` and 0x4933C's
        ``andi #0x3E0`` annihilate all six -- the candidate cannot be anything
        but the generator itself, anywhere in the maze."""
        for index in (12, 13, 14):
            assert _GENERATOR_CELL_DX[index] % 0x20 == 0, index
            assert 0 <= _GENERATOR_CELL_DY[index] < 0x20, index
            for row in range(32):
                for col in range(32):
                    gen = pack_slot(row, col)
                    assert generator_candidate_slot(gen, index) == gen

    def test_the_read_past_candidates_can_never_be_taken(self):
        """And a generator's own cell always holds the generator, so the three
        nonsense direction words behind them are unreachable."""
        for index in (12, 13, 14):
            state = GameState()
            gen = pack_slot(10, 10)
            _place_generator(state, gen)
            assert not tile_occupancy_test(
                state, generator_candidate_slot(gen, index)
            ), index

    def test_a_ghost_generator_ringed_in_spawns_nothing_in_attract_mode(self):
        """The seed-7 sweep ends on the three read-past indices, so this is the
        exact path that would consume them -- and it still spawns nothing."""
        state = GameState()
        _attract(state)
        state.monster_generation_retry_timer = 0
        state.rng = _RecordingRNG()
        gen = pack_slot(10, 10)
        _place_generator(state, gen)
        for index in range(8):
            _place_wall_marker(state, generator_candidate_slot(gen, index))

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=0)

        assert _spawned_slot(state) is None
        assert state.mobs.obj_type(gen) == int(MazeObjIds.GEN_GHOST1)
        assert state.rng.bounds == []

    def test_gameplay_never_takes_the_attract_path(self):
        state = GameState()
        _gameplay(state)
        state.monster_generation_retry_timer = GENERATOR_RETRY_RELOAD
        state.rng = _RecordingRNG(0, 0)
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        handle_generate(state, gen, int(MazeObjIds.GEN_GHOST1), probability=32)

        assert state.rng.bounds == [32, 4]
        assert state.monster_generation_retry_timer == GENERATOR_RETRY_RELOAD


class TestAttractModeReachability:
    """Where the seed-7 sweep actually sits in the shipped attract loop."""

    def test_a_zero_probability_gates_the_whole_routine(self):
        """0x4103E short-circuits *before* the call, so a level whose spawn
        probability is zero never even ticks the retry timer.  A cold-booted
        cabinet is exactly that case: ``attract_demo_init`` (0x449D4-0x44A80)
        writes no ``levelnum_current``, so the first demo after power-on runs at
        level 0 and 0x40F9E's ``level x 2`` cap forces the probability to zero.
        """
        state = GameState()
        _attract(state)
        state.levelnum_current = 0
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        assert _spawn_probability(state) == 0
        _handle_generator(state, gen, int(MazeObjIds.GEN_GHOST1),
                          _stagger_frame(gen) * 2)

        assert state.monster_generation_retry_timer == GENERATOR_RETRY_RELOAD
        assert _spawned_slot(state) is None

    def test_a_played_cabinet_reaches_the_attract_path(self):
        """Any demo entered after a game has been played carries that game's
        level number, and the probability is then nonzero."""
        state = GameState()
        _attract(state)
        state.monster_generation_retry_timer = 0
        state.levelnum_current = 5
        state.level_players_active = 1
        gen = pack_slot(10, 10)
        _place_generator(state, gen)

        assert _spawn_probability(state) > 0
        _handle_generator(state, gen, int(MazeObjIds.GEN_GHOST1),
                          _stagger_frame(gen) * 2)

        assert _spawned_slot(state) is not None

    @requires_roms
    def test_the_shipped_demo_maze_carries_a_seed_seven_generator(self):
        """Demo maze 102 holds a GEN_GHOST2, whose family index (1) is inside
        0x492F6's 0-2 window -- so the seed-7 sweep, and with it the three
        read-past indices, is a live path and not dead code."""
        from gauntpy.subsystems.attract import attract_demo_init

        state = GameState()
        state.game_mode = int(GameMode.DEMO)
        attract_demo_init(state)

        first, last = int(MazeObjIds.GEN_GHOST1), int(MazeObjIds.GEN_AUX_GRUNT3)
        families = {state.mobs.obj_type(slot) - first
                    for slot in range(len(state.mobs.picture))
                    if first <= state.mobs.obj_type(slot) <= last}

        assert families, "the demo maze has generators at all"
        assert families & set(_GEN_ATTRACT_GHOST_FAMILIES), \
            "and at least one of them takes the seed of 7"
