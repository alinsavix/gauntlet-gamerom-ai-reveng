"""Player frame orchestration, projectile creation, and compatibility entry points.

Movement/collision, lifecycle/health, pickups, and transport live in the
corresponding ``player_*`` families. Public generic probes belong to
``mob_probes``; recorded input, picture selection, and names have separate owners.
Public reexports preserve function identity. The legacy exit adapter additionally
retains optional arguments; game callers use the actual transition routine.

Reference: ``doc/04_game_subsystems.md`` §4 (all), §7.2, §10.5, §10.6, §13,
§14.1, §21; ``doc/generated/player_collision_contracts.csv``,
``player_runtime_contracts.csv``, ``player_lifecycle_contracts.csv``,
``tport_forcefield_contracts.csv``, ``playfield_floor_contracts.csv``;
``book/03_four_players.md`` and ``book/02_one_arrow.md``.
Tables and gates transcribed from ``row76.bin`` carry
their ROM address in a comment; where the ROM and the prose docs disagree the
ROM wins and the disagreement is written down at the point of use.
"""

from __future__ import annotations

from ..constants import (
    FIRST_PLAYABLE_SLOT,
    SLOT_PLAYER_SHOTS,
    GameMode,
    MazeObjIds,
    PlayerPower,
    PlayerStatus,
)
from ..coords import POS_SHIFT, position_field
from ..state import NUM_PLAYERS, GameState
from .input import fire_held
from .score import player_add_score_with_mult as player_add_score_with_mult
# Explicit compatibility imports; implementations live with their ROM families.
from .player_animation import (
    _PORT_DIR_TO_ROM_DIR,
    _ANIM_TABLE_IDLE,
    _PLAYER_EXIT_PICTURE,
    _FIGHTING_ANIM_END,
    update_player_sprite as update_player_sprite,
    update_player_sprites as update_player_sprites,
)
from .player_names import (
    secret_code_for as secret_code_for,
    secret_code_build as secret_code_build,
    secret_getname as secret_getname,
    secret_name_entry_update as secret_name_entry_update,
    highscore_check as highscore_check,
    name_entry_step_char as name_entry_step_char,
    player_death_sequence as player_death_sequence,
)
from .sound import sound_play as _sound_play


# Compatibility exports; each routine and table has a single game-side owner.
from .mob_probes import (
    mob_probe_down as mob_probe_down,
    mob_probe_left as mob_probe_left,
    mob_probe_right as mob_probe_right,
    mob_probe_up as mob_probe_up,
)
from .player_data import _NO_MOVE, _SHOT_PALETTE_BASE
from .player_items import (
    _dialog,
    door_open_start as door_open_start,
    initialize_player_temporary_power as initialize_player_temporary_power,
    maze_convert_walls_to_exits as maze_convert_walls_to_exits,
    open_timed_doors as open_timed_doors,
    player_tile_interact as player_tile_interact,
)
from .player_lifecycle import (
    _play_random_character_voice,
    calc_score_per_coin as calc_score_per_coin,
    main_handle_death as main_handle_death,
    main_health_countdown as main_health_countdown,
    player_damage_sample_update as player_damage_sample_update,
    player_hurt_palette_vblank as player_hurt_palette_vblank,
    player_inv_update as player_inv_update,
    player_join as player_join,
    player_join_finalize as player_join_finalize,
    player_lowhealth as player_lowhealth,
    player_resetall as player_resetall,
    player_resetcounters as player_resetcounters,
    player_start_inner as player_start_inner,
    setup_infopanel as setup_infopanel,
    show_continue_prompt as show_continue_prompt,
    speech_welcome as speech_welcome,
)
from .player_movement import (
    _PLAYER_SPEED_NORMAL,
    _direction_from_input,
    _player_record_cell,
    _track_thief_victim_move,
    migrate_player_record as migrate_player_record,
    player_try_move as player_try_move,
)
from .player_transport import (
    corner_squeeze_geometry as corner_squeeze_geometry,
    handle_tport as handle_tport,
    nearby_mob_clearance_test as nearby_mob_clearance_test,
    player_tport as player_tport,
    scan_move_path_interactions as scan_move_path_interactions,
    squeeze_through_check as squeeze_through_check,
    tile_on_screen_test as tile_on_screen_test,
    tport_check_dest as tport_check_dest,
    tport_player_move as tport_player_move,
    tport_transition_arm as tport_transition_arm,
)
from .player_input import (
    _JOY_DIRECTIONS,
    _demo_playback,
    _joystick_direction_bits,
    _joystick_fire_held,
    demo_playback_start as demo_playback_start,
    demo_record_word as demo_record_word,
    player_joystick_word as player_joystick_word,
)


# =============================================================================
# Tables
# =============================================================================

# ``forcefield_damage_table`` (0x5813C).  §4.3 TRAP 4.
# Index = character + 4 × armor_power_bit (bit 1 of player.powers).
# Warrior=0, Valkyrie=1, Wizard=2, Elf=3.
_FORCEFIELD_DAMAGE_TABLE = [
    2, 2, 6, 4,   # armor_power_bit=0 (no extra armor)
    1, 1, 5, 3,   # armor_power_bit=1 (extra armor, powers & 0x02)
]

# RESPAWN_WAIT counter limit; transition when reached (main_move_players
# 0x4A6A0: ``cmpi.w #$20, player_anim_counter``).
_RESPAWN_WAIT_LIMIT = 0x20

# Death/exit animation: the frame counter counts down to 4 (0x4A666), one step
# per four frames (0x4A652 ``andi.w #$3``).
_DEATH_ANIM_LAST_FRAME = 4
_DEATH_ANIM_STEP_MASK = 0x03

# escape_timer value that fires maze_convert_walls_to_exits (0x5208, §4.1).
_ESCAPE_TIMER_LIMIT = 0x5208
# Sound played when the escape timeout actually converted something (0x4AD20).
_SOUND_ESCAPE_WALLS = 0x27
# level_flags_3 (0x90491E) bits cleared after the conversion (0x4AD34/0x4AD3C).
_ESCAPE_CLEARS_LEVEL_FLAGS_3 = 0x08 | 0x40

# Forcefield hurt-timer initial countdown value loaded on first contact
# (0x4AACE); continuing contact refreshes a positive value below this threshold.
_FORCEFIELD_HURT_TIMEOUT = 0x10

# Door-idle thresholds, main_move_players 0x4ACEC/0x4ACF2: 0xA8C frames while
# any player is carrying a key, 0x4B0 otherwise.  The counter is the ROM's own
# ``idle_timer`` word at 0x90490C, advanced by the post-loop below.
_DOOR_IDLE_THRESHOLD_WITH_KEYS = 0xA8C
_DOOR_IDLE_THRESHOLD_NO_KEYS = 0x4B0

_POWER_SHOTSPEED = int(PlayerPower.SHOTSPEED)   # bit 3, POWERUP_BIT_MASKS[3]
# shot_reflect_sound_tbl -- ROM 0x5BAD0, indexed by character.
_SHOT_REFLECT_SOUND_TBL = [0x45, 0x47, 0x46, 0x48]
# Character-specific death SFX, refs/soundcmds.csv 0x14-0x17; ROM 0x57932
# (four longwords), played by the death path of main_health_countdown (0x46B2A).
_PLAYER_DEATH_SOUND_BASE = 0x14

# Shot spawn offsets, ROM shot_spawn_hpos_tbl (0x5BAB0) and shot_spawn_vpos_tbl
# (0x5BAC0), read by player_create_shot at 0x536FA/0x53746 and added to the
# firing player's masked hpos/vpos.  Both are native position words, so they
# are added to the MOB word as they stand and the vertical column keeps the
# hardware's upward sense.  Indexed by ROM facing direction.
_SHOT_REFLECT_HDELTA = [0x0200, 0x0500, 0x0600, 0x0300, 0x0200, -0x0080, -0x0200, -0x0100]
_SHOT_REFLECT_VDELTA = [0x0700, 0x0300, 0x0180, -0x0080, -0x0100, -0x0280, 0x0180, 0x0380]
_SHOT_TILE_WIDTH = 2
_SHOT_TILE_HEIGHT = 2

# player_shot_picture_tbl -- ROM 0x58B8A, 32 records of two words (frame A,
# frame B) indexed ``character * 8 + rom_direction``; player_create_shot uses
# frame A (0x536EA).  Transcribed from row76.bin offset 0x18B8A.
_PLAYER_SHOT_PICTURE = [
    # Warrior
    0x1C9F, 0x1CA7, 0x1CAF, 0x1CB7, 0x1CBF, 0x1CC7, 0x1CCF, 0x1C97,
    # Valkyrie
    0x17FC, 0x18FC, 0x19FC, 0x1AFC, 0x1BC3, 0x1C68, 0x1C6C, 0x1C70,
    # Wizard
    0x1CD7, 0x1CDF, 0x1CE7, 0x1CEF, 0x1CF7, 0x1D00, 0x1D08, 0x1D10,
    # Elf
    0x1C74, 0x1C78, 0x1C7C, 0x1C80, 0x1C84, 0x1C8B, 0x1C8F, 0x1C93,
]

def _player_shooting_input_update_one(state: GameState,
                                      player_index: int) -> None:
    """Arm one held-Fire action; the call is idempotent during its throw."""
    player = state.players[player_index]
    if (not player.active or not player.mob_slot
            or state.player_tport_phase[player_index] >= 0
            or player.stundelay
            or not _joystick_fire_held(state, player_index)):
        return
    # 0x474FE/0x477D0: the input arm is the ``else`` branch of the live-shot
    # handler. A player cannot restart the throw while their fixed channel is
    # still occupied.
    if state.mobs.picture[player_index + SLOT_PLAYER_SHOTS.start]:
        return
    if (state.player_shooting[player_index]
            and (player.anim_counter & 0xFFFF)
            <= _FIGHTING_ANIM_END[player_index]):
        return
    state.reflect_count[player_index] = 4
    player.anim_counter = 0
    state.player_shooting[player_index] = -1
    state.player_fighting_dir[player_index] = 0
    state.player_walking[player_index] = 0


def player_shooting_input_update(state: GameState) -> None:
    """0x47B72-0x47BF6 -- arm held-Fire shooting actions for all players.

    The ROM places this input gate in ``main_handle_shots`` before the player
    loop.  ``main_move_players`` also calls it when driven standalone, making
    headless/direct ticks observe the same action state.  The operation is
    idempotent while the current four-count throw is still underway.
    """
    for player_index in range(NUM_PLAYERS):
        _player_shooting_input_update_one(state, player_index)


def _advance_player_sprite(state: GameState, player_index: int, *,
                           walking: bool, fire_held: bool) -> None:
    """Run the counter/action half of 0x4AB08-0x4AC0E for one hero."""
    player = state.players[player_index]
    if (not player.active or not player.mob_slot
            or state.player_tport_phase[player_index] >= 0):
        return

    state.player_walking[player_index] = int(walking)
    update_player_sprite(state, player_index, walking=walking)

    if state.player_fighting_dir[player_index] or walking:
        player.anim_counter = (player.anim_counter + 1) & 0xFFFF
        return
    if not state.player_shooting[player_index]:
        return

    previous_counter = player.anim_counter & 0xFFFF
    player.anim_counter = (previous_counter + 1) & 0xFFFF
    if previous_counter == _FIGHTING_ANIM_END[player_index]:
        player_create_shot(state, player_index)

    # 0x4ABF4-0x4AC0C: held Fire repeats after the four-count throw; on release
    # the animation is allowed through count 8, and cannot exceed count 15.
    if previous_counter > 0x0F or (
            not fire_held and previous_counter > 8):
        state.player_shooting[player_index] = 0

#: ``player_tport_phase`` value at which the transition's move milestone lands.
#: WP-14's loop 2 counts the phase up one per frame and acts on ``phase >> 1``
#: when the phase is even, so step 0x0B -- ``tport_player_move`` at 0x47324 --
#: is phase 0x16.  Its idle sentinel is negative (the ROM stores 0xFFFF).
_TRANSITION_MOVE_PHASE = 0x0B * 2
_TRANSITION_IDLE_PHASE = -1
_DIALOG_FORCEFIELD = 0x80000000     # 0x4AAEE, inside the contact block
# FOOD000, retained as the ordinary-food fixture constant used by tests.
_WHOLESOME_FOOD_PICTURE = 0x0963
# 0x4A4FA, four frame-counter phase rows by active-low joystick nibble.
_DIZZY_DIRECTION_REMAP = (
    0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0x70, 0xE0, 0x60,
    0xF0, 0xD0, 0xB0, 0x90, 0xF0, 0x50, 0xA0, 0xF0,
    0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0x50, 0x60, 0x70,
    0xF0, 0x90, 0xA0, 0xB0, 0xF0, 0xD0, 0xE0, 0xF0,
    0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0xD0, 0x70, 0x50,
    0xF0, 0xB0, 0xE0, 0xA0, 0xF0, 0x90, 0x60, 0xF0,
    0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0x50, 0x60, 0x70,
    0xF0, 0x90, 0xA0, 0xB0, 0xF0, 0xD0, 0xE0, 0xF0,
)


def player_exit_sequence(state: GameState, player_index: int,
                         exit_mob_slot: int = 0,
                         exit_type: int = int(MazeObjIds.EXIT)) -> None:
    """Legacy default-argument adapter for the exit routine (0x52B40).

    Game callers import ``level_transitions.player_exit_sequence`` directly;
    this adapter retains the older optional exit-slot/type arguments.
    """
    from .level_transitions import player_exit_sequence as _exit_sequence
    _exit_sequence(state, player_index, exit_mob_slot, exit_type)


def player_create_shot(state: GameState, player_index: int) -> None:
    """0x53666 -- spawn a player shot in the player's fixed channel (§26, N-02).

    Each player owns one shot channel (slot ``player_index + 1``, in
    ``SLOT_PLAYER_SHOTS`` = slots 1-4). A new shot is created only while that
    channel is free (``picture == 0``), so a held Fire button produces one shot
    at a time -- the channel is re-armed when the live shot expires or hits
    (``main_handle_shots``, WP-7).

    Spawn picture and position are the ROM's, not placeholders:

      * ``mob_picture`` = ``player_shot_picture_tbl[character * 8 + facing]``
        (0x58B8A, read at 0x536EA);
      * ``mob_hpos`` = firing player's X + ``shot_spawn_hpos_tbl[facing]``
        (0x5BAB0) with palette ``0x0C + player`` (0x5371C);
      * ``mob_vpos`` = firing player's Y + ``shot_spawn_vpos_tbl[facing]``
        (0x5BAC0) with the 2x2-tile size field the ROM writes as 9 (0x53768).

    Facing indexes those tables through ``_PORT_DIR_TO_ROM_DIR``.  Motion,
    lifetime and hit resolution stay WP-7's.
    """
    player = state.players[player_index]
    shot_slot = player_index + SLOT_PLAYER_SHOTS.start   # slots 1-4
    if shot_slot not in SLOT_PLAYER_SHOTS:
        return
    if state.mobs.picture[shot_slot] != 0:               # channel busy: one at a time
        return

    base_h = position_field(state.mobs.hpos[player.mob_slot])
    base_v = position_field(state.mobs.vpos[player.mob_slot])
    port_dir = player.direction & 0x07
    rom_dir = _PORT_DIR_TO_ROM_DIR[port_dir]
    character = player.character & 0x03

    state.mobs.picture[shot_slot] = _PLAYER_SHOT_PICTURE[character * 8 + rom_dir]
    state.mobs.hpos[shot_slot] = (
        base_h + _SHOT_REFLECT_HDELTA[rom_dir]
        + _SHOT_PALETTE_BASE + player_index
    ) & 0xFFFF
    state.mobs.vpos[shot_slot] = (
        base_v + _SHOT_REFLECT_VDELTA[rom_dir]
        + (((_SHOT_TILE_WIDTH - 1) & 0x07) << 3)
        + ((_SHOT_TILE_HEIGHT - 1) & 0x07)
    ) & 0xFFFF
    state.shot_direction[player_index] = rom_dir
    from .shot_state import shot_velocity

    vx, vv = shot_velocity(state, player_index, rom_dir)
    state.shot_dx[shot_slot] = vx >> POS_SHIFT
    state.shot_dy[shot_slot] = vv >> POS_SHIFT
    state.shot_lifetime[shot_slot] = 0
    _sound_play(state, _SHOT_REFLECT_SOUND_TBL[character])
    if player.supershot > 0:
        player.supershot = (player.supershot - 1) & 0xFF


# =============================================================================
# Player frame helpers and main-loop routine
# =============================================================================

def _check_forcefield_collision(state: GameState, player_index: int) -> bool:
    """0x4AA68 -- True when the player overlaps a live forcefield beam.

    The ROM call site converts the player's MOB position to a packed cell and
    hands it to ``check_forcefield_collision`` (0x53346), which walks the packed
    segment table at 0x910780 through ``pf_isff`` (0x5FC5E).  Both of those --
    the table build (``forcefield_segments_setup``, 0x53398) and the query --
    belong to the living-maze subsystem and now exist there, so this is a thin
    adapter over them rather than the second, independent hub scan it used to
    carry.  That scan approximated the segment table from the MOB grid every
    frame and could not see the wrap and length fields the packed words encode.

    ``main_cycle_tport_and_ffield`` builds the table earlier in the same frame;
    the guard here only matters when ``main_move_players`` is driven on its own,
    and mirrors that routine's own lazy build.
    """
    from .maze_objects import check_forcefield_collision, forcefield_segments_setup

    if not state.forcefield_segments_ready:
        forcefield_segments_setup(state)

    # 0x4AA5E-0x4AA68 hands ``check_forcefield_collision`` the player's own MOB
    # id out of ``active_mob_ids`` -- which is the cell the hero stands in,
    # because the record migrates with it.
    return check_forcefield_collision(
        state, state.players[player_index].mob_slot,
    )


def _power_timers_tick(state: GameState, player_index: int) -> None:
    """0x4A7FE-0x4A890 -- run down the three timed powers.

    Each countdown is paired with the ``player_powers`` bit it keeps alive, and
    the pairing is where the bit numbers were confirmed from the far side: the
    ROM clears each one with a ``bclr`` on the *high byte* of the word, so
    ``bclr #0`` is bit 8, ``bclr #1`` is bit 9 and ``bclr #5`` is bit 13.

      * ``invis_timer`` (0x905F50) -> PlayerPower.INVIS   (bit 8,  0x4A80E)
      * the repulsiveness countdown (0x905F38) -> PlayerPower.REPULSE
        (bit 9, 0x4A826) -- doc/05 calls that word ``reflect_timer``, but bit 9
        is the one 0x4185C tests to make monsters flee, and reflection is bit 10
      * the 0x905F40 countdown -> PlayerPower.ACID_AFFLICTION (bit 13, 0x4A880)

    That last one also charges damage while it runs: one point every eighth
    frame, two when frame-counter bit 3 is clear (0x4A838-0x4A85E), floored at
    zero, raising the health redraw bit.  It is the same word the acid puddle
    arms, which is why this port calls it ``acid_timer``.
    """
    player = state.players[player_index]

    if state.player_invis_timer[player_index]:                       # 0x4A804
        state.player_invis_timer[player_index] -= 1
        if state.player_invis_timer[player_index] == 0:
            player.powers &= ~int(PlayerPower.INVIS) & 0xFFFF        # 0x4A80E
            player_inv_update(state, player_index)

    if state.player_repulse_timer[player_index]:                     # 0x4A81A
        state.player_repulse_timer[player_index] -= 1
        if state.player_repulse_timer[player_index] == 0:
            player.powers &= ~int(PlayerPower.REPULSE) & 0xFFFF      # 0x4A826
            player_inv_update(state, player_index)

    if player.acid_timer:                                            # 0x4A832
        if (state.frame_counter & 0x07) == 0:                        # 0x4A840
            damage = 1 if (state.frame_counter & 0x08) else 2        # 0x4A852
            player.health = max(0, player.health - damage)           # 0x4A85E
            state.health_dirty[player_index] = 1                     # 0x4A868
        player.acid_timer -= 1                                       # 0x4A87A
        if player.acid_timer == 0:
            player.powers &= ~int(PlayerPower.ACID_AFFLICTION) & 0xFFFF       # 0x4A880
            state.health_dirty[player_index] = 1                     # 0x4A88C
            player_inv_update(state, player_index)

    if state.player_dizzy_timer[player_index]:                       # 0x4A898
        state.player_dizzy_timer[player_index] -= 1                  # 0x4A89E


def _player_movement_direction_bits(
    state: GameState, player_index: int,
) -> int:
    """Return the ROM-remapped movement nibble for a dizzy live player."""
    if (
        state.game_mode != int(GameMode.NORMAL)
        or not state.player_dizzy_timer[player_index]
    ):
        return _joystick_direction_bits(state, player_index)
    raw = player_joystick_word(state, player_index)
    index = (state.frame_counter & 0x30) + ((raw >> 4) & 0x0F)
    return (~_DIZZY_DIRECTION_REMAP[index]) & _JOY_DIRECTIONS


def _status8_complete(state: GameState, player_index: int) -> None:
    """0x4A6AA-0x4A6E6 -- the status-0x08 animation has finished.

    The ROM's only writer of status 8 is ``player_exit_sequence``, so its tail
    is the *exit* tail: status 2 (0x4A6B2), the exit-animation MOB released
    (0x4A6C0, mob id 0x14 + player), ``active_mob_ids`` cleared (0x4A6D2), the
    IT label dropped if this was the IT player (0x4A6DE) and
    ``level_players_active`` decremented (0x4A6E6).  When that count reaches
    zero the level is over: the countdowns at 0x4A748-0x4A788 tick and the tally
    screen runs (0x4A78C).

    This port also parks a *dying* hero in status 8 for its own death
    animation, which the ROM has no equivalent for -- ``Player.exit_pending``
    tells them apart.  That arm keeps the port's own tail: REMOVED, and the
    continue prompt once nobody is left.
    """
    player = state.players[player_index]

    if player.exit_pending:
        player.status = int(PlayerStatus.ALIVE_NEXT)         # 0x4A6B2
        player.exit_pending = 0
        if player.mob_slot:                                  # 0x4A6C0/0x4A6D2
            state.mobs.unlink_and_clear(player.mob_slot)
        player.mob_slot = 0
        state.player_in_maze[player_index] = 0
        if state.player_it == player_index:                  # 0x4A6D6
            state.player_it = 0xFFFF
            from .score import write_it_labels
            write_it_labels(state)
        state.level_players_active = max(0, state.level_players_active - 1)
        setup_infopanel(state, player_index)
        if state.level_players_active == 0:                  # 0x4A6E6
            from .level_transitions import _finish_level_end, advance_level_countdowns
            from .treasure_rooms import show_level_end_bonus_screen

            if advance_level_countdowns(state):              # 0x4A748-0x4A788
                show_level_end_bonus_screen(state)           # 0x4A78C
            else:
                # DEMO completion is owned by main_start_game at
                # 0x480B6-0x480E2. The countdown bookkeeping above still runs,
                # but level 2 is never committed for the recorded actors.
                if state.game_mode == int(GameMode.DEMO):
                    return
                from .secret_rooms import secret_check

                secret_check(state)                          # 0x480EC
                state.levelnum_current = state.level_next
                state.mazenum_current = state.maze_next
                _finish_level_end(state)
        return

    # The port's death animation: the hero leaves the level for good.
    player.status = int(PlayerStatus.REMOVED)
    setup_infopanel(state, player_index)
    if state.player_it == player_index:                      # 0x4A6D6
        state.player_it = 0xFFFF
        from .score import write_it_labels
        write_it_labels(state)
    if not any(p.active for p in state.players):
        show_continue_prompt(state)


def main_move_players(state: GameState) -> None:
    """0x4A53A -- per-frame processing for all four player slots (§4.1).

    Four sections:
    1. Game-mode gate: skip demo in normal play; skip entirely for
       TITLE/SCORES/LEGEND; use demo stream for DEMO mode.
    2. Demo playback: reads [timer, joystick] pairs from per-player streams.
    3. Per-player status dispatch: SECRET_NAME_ENTRY, DYING, RESPAWN_WAIT,
       active gameplay (damage sample, power-ups, forcefield contact, movement,
       tile interaction, shooting, animation).
    4. Post-loop (gated at ROM 0x4ACD4 on the 0x4A8B4 counter, which only
       normal play writes): the door-idle threshold comparison and the escape
       timeout, so neither runs during the attract DEMO.
    """
    # Secret-name entry runs during the TREAS_EXIT display hold (0x54FE8).
    if 0 <= state.secret_player < NUM_PLAYERS and state.players[
        state.secret_player
    ].status == int(PlayerStatus.SECRET_NAME_ENTRY):
        secret_name_entry_update(state)
        return

    # ── Section 1: game-mode gate ─────────────────────────────────────────────
    if state.game_mode < 0:
        # Attract family: only DEMO runs the player loop.
        if state.game_mode != int(GameMode.DEMO):
            return  # TITLE / SCORES / LEGEND -- skip entirely
        # DEMO: fall through to demo section.
    elif state.game_mode == int(GameMode.TREAS_EXIT):
        return  # level-end bonus screen: the world is frozen (WP-15/§16)
    # game_mode >= 0 (normal): skip demo section, proceed to per-player loop.

    # A dynamic picture with no object identity and either no complete position
    # or no depth-list membership is not a record any ROM MOB writer can produce.
    # Clear this Python-only remnant before collision probes can treat it as an
    # invisible obstacle.
    for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.picture)):
        if (
            state.mobs.picture[slot]
            and state.mobs.obj_type(slot) == 0
            and state.mobs.state(slot) == 0
            and (
                state.mobs.hpos[slot] == 0
                or state.mobs.vpos[slot] == 0
                or not state.mobs.is_linked(slot)
            )
        ):
            state.mobs.unlink_and_clear(slot)

    # ── Section 2: demo playback ──────────────────────────────────────────────
    if state.game_mode == int(GameMode.DEMO):
        _demo_playback(state)

    # ── Section 3: per-player loop ────────────────────────────────────────────
    # The ROM keeps two frame locals across the loop, and *where* each one is
    # written matters: -4(a6) is bumped at 0x4A8B4, which sits inside the
    # ``game_mode == 0`` arm of the branch at 0x4A8A2, and it gates the whole
    # post-loop at 0x4ACD4; -2(a6) accumulates key counts at 0x4AC8C, on the
    # active tail, and picks the door-idle threshold.
    active_processed = 0
    keys_held = 0
    for player_index in range(NUM_PLAYERS):
        player = state.players[player_index]
        state.player_joystick[player_index] = _NO_MOVE

        # Status 0x20: secret winner name entry.
        if player.status == int(PlayerStatus.SECRET_NAME_ENTRY):
            secret_name_entry_update(state)
            continue

        # Status 0x04: initials entry / GAME OVER dwell -- countdown (0x49DE6).
        if player.status == int(PlayerStatus.DYING):
            player_death_sequence(state, player_index)
            continue

        # Status 0x08: the exit animation (0x4A646-0x4A6E6), which this port
        # also runs for a dying hero.  ROM cadence: player_anim_counter
        # (0x9049BC) advances every frame but the branch only acts when its low
        # two bits are clear (0x4A652).  Phase 1 -- while player_facing_dir has
        # not reached 4 -- resets the counter and steps the facing down one
        # notch per four frames, drawing anim_table_idle (0x58A4A): the hero
        # spins on the spot.  Phase 2 lets the counter accumulate and steps
        # player_exit_picture_tbl (0x5870A) with ``counter >> 2`` (0x4A796), the
        # 32-frame dissolve.  Only at 0x20 does the player leave the level.
        if player.status == int(PlayerStatus.RESPAWN_WAIT):
            player.anim_counter = (player.anim_counter + 1) & 0xFFFF
            if player.anim_counter & _DEATH_ANIM_STEP_MASK:
                continue
            frame = state.player_death_anim_frame[player_index]
            if frame != _DEATH_ANIM_LAST_FRAME:
                player.anim_counter = 0
                frame = (frame - 1) & 0x07
                state.player_death_anim_frame[player_index] = frame
                if player.mob_slot:
                    state.mobs.picture[player.mob_slot] = _ANIM_TABLE_IDLE[
                        (player.character & 0x03) * 8 + frame
                    ]
                continue
            if player.anim_counter < _RESPAWN_WAIT_LIMIT:       # 0x4A6A0/0x4A796
                if player.mob_slot:
                    state.mobs.picture[player.mob_slot] = _PLAYER_EXIT_PICTURE[
                        (player.character & 0x03) * 8
                        + (player.anim_counter >> 2)
                    ]
                continue
            _status8_complete(state, player_index)
            continue

        # All other inactive statuses (REMOVED 0x00, ALIVE_NEXT 0x02, etc.).
        if not player.active:
            continue

        # ── Active gameplay ───────────────────────────────────────────────────
        # Neither frame local is written here: the ROM counts a processed player
        # at 0x4A8B4 (after the transport and power-timer work, and only in
        # normal play) and its keys at 0x4AC8C, on the tail below.

        # Death: a player whose health has reached zero (from the flat drain,
        # forcefield/monster contact, or shots) leaves the level (§4.1 / §4.3).
        # Without this the player would keep playing with negative health.
        #
        # This is the ROM's own death block from main_health_countdown
        # (0x467E0-0x46B7E), reached from here because this port detects the
        # zero crossing in the player loop: player_resetcounters (0x4699A)
        # wipes the slot, the IT label is dropped (0x469C4),
        # level_players_active is decremented (0x469DA), score-per-coin is
        # computed (0x46A18) and highscore_check (0x46AC4) decides between
        # initials entry and the GAME OVER dwell before the panel is rebuilt
        # (0x46AD0) and the character's death SFX plays (0x46B2A).
        if player.health <= 0:
            player.health = 0
            character = player.character
            dead_slot = player.mob_slot
            player.death_damage_counter = 0
            # The ROM's animation frame *is* player_facing_dir (0x9049A4), so
            # the death sequence starts from whatever way the hero was facing
            # and counts down to 4 (0x4A672).
            state.player_death_anim_frame[player_index] = _PORT_DIR_TO_ROM_DIR[
                player.direction & 0x07
            ]
            state.player_lowhealth_spoken[player_index] = 0       # 0x46944-ish
            state.player_respawn_speech_timer[player_index] = -1
            if state.player_it == player_index:                   # 0x469C4
                state.player_it = 0xFFFF
                from .score import write_it_labels
                write_it_labels(state)
            state.level_players_active = max(0, state.level_players_active - 1)
            calc_score_per_coin(state, player_index)              # 0x46A18
            # player_resetcounters clears the inventory, the powers, every
            # timer and the status; the character and the score survive it, so
            # the ladder and the panel still have something to show.
            if dead_slot:
                state.mobs.unlink_and_clear(dead_slot)
            player_resetcounters(state, player_index)             # 0x4699A
            player.character = character
            player.anim_counter = 0
            highscore_check(state, player_index)                  # 0x46AC4
            # highscore_check alone owns the result: a ranked player enters
            # status 4 for initials; an unranked player remains cleared.
            setup_infopanel(state, player_index)                  # 0x46AD0
            _play_random_character_voice(state, character)        # 0x46B16
            _sound_play(
                state, _PLAYER_DEATH_SOUND_BASE + (character & 0x03),
            )                                                     # 0x46B2A
            if state.level_players_active == 0:                   # 0x46B30
                if state.dialog_timer:
                    from .score import main_msgbox_countdown
                    state.dialog_timer = 1
                    main_msgbox_countdown(state)                   # 0x46B48
                if state.levelnum_current == 1:
                    state.attract_timer = 0x0258                   # 0x46B58
                else:
                    state.attract_timer = 0x05DD                   # 0x46B62
                    show_continue_prompt(state)                    # 0x46B6A
            if state.thief_victim == player_index:                # 0x46B70
                from .thief import thief_exit
                thief_exit(state)
            continue

        # 60-frame damage sample window (§4.3 / 0x50E34).
        player_damage_sample_update(state, player_index)

        # 0x4A7E2-0x4A7EC: a non-negative transport phase means WP-14's loop 2
        # is running this player's dissolve/move/re-form, so everything below --
        # power timers, forcefield, movement, pickups, shooting, animation --
        # is skipped until the transition retires and the phase goes negative
        # again. Loop 2 calls ``tport_player_move`` at the move milestone.
        if state.player_tport_phase[player_index] >= 0:
            continue

        _power_timers_tick(state, player_index)

        # 0x4A8A2-0x4A8B4: the branch that decides where this frame's joystick
        # word comes from is also the one that counts the player.  ``game_mode``
        # non-zero takes the demo arm at 0x4A8F2 -- it reads the recorded word
        # through ``demo_ptr`` and jumps straight to the stun gate, never
        # touching -4(a6).  Only normal play (``game_mode == 0``) reads
        # ``player_input_raw`` and does the ``addq.w #1,-4(a6)`` at 0x4A8B4, so a
        # DEMO frame always leaves the counter at zero and the post-loop's
        # timed-door sweep and escape-timeout conversion (gated at 0x4ACD4)
        # never run while the attract demo is playing.  The demo's own hero
        # still moves, fights and picks things up: everything below this point
        # is common to both arms.
        if state.game_mode == int(GameMode.NORMAL):               # 0x4A8A8
            active_processed += 1                                 # 0x4A8B4

        fire_held = _joystick_fire_held(state, player_index)
        walking = False
        movement_origin: tuple[int, int, int] | None = None
        movement_destination: int | None = None

        # Stun (0x4A908-0x4A91C).  ``player_stundelay`` (0x904A54) counts down
        # one per frame and, while it is still non-zero afterwards, the ROM
        # branches straight to the forcefield check: the speed lookup, the
        # facing update, the shot test and player_try_move are all skipped, so
        # a stunned hero neither moves nor acts on its joystick -- but is still
        # charged for standing in a forcefield.
        if player.stundelay:                                     # 0x4A90E
            player.stundelay -= 1
        stunned = player.stundelay != 0                          # 0x4A918
        dirn = _player_movement_direction_bits(state, player_index)
        if (not stunned and dirn
                and (not state.player_shooting[player_index]
                     or player.anim_counter
                     > _FIGHTING_ANIM_END[player_index])):
            rom_direction = _direction_from_input(dirn)
            if rom_direction < 8:
                player.direction = (rom_direction - 2) & 0x07
        # ``main_handle_shots`` normally performs this input pass earlier in a
        # complete frame. Repeating the idempotent gate here supports direct
        # subsystem ticks; it must follow the facing update for a newly loaded
        # demo SHOOT record.
        _player_shooting_input_update_one(state, player_index)

        # 0x4A9C0 keeps a just-armed throw still through its four-count wind-up;
        # a held Fire line otherwise bypasses the movement call at 0x4A9DE.
        shooting_windup = (
            state.player_shooting[player_index]
            and (player.anim_counter & 0xFFFF)
            <= _FIGHTING_ANIM_END[player_index]
        )
        fight_ready = (
            not state.player_fighting_dir[player_index]
            or (player.anim_counter & 0x0F) == 0x07
        )
        if not stunned and not fire_held and not shooting_windup and fight_ready:
            # Movement: delegate fully to WP-5 (§4.2 / 0x41BF0).  The joystick
            # comes from the demo record in DEMO and the hardware sample
            # otherwise -- chosen at the read, per 0x50690, never by writing
            # one into the other.
            if dirn:
                state.movement_type = 2
                movement_origin = (
                    player.mob_slot,
                    state.mobs.hpos[player.mob_slot],
                    state.mobs.vpos[player.mob_slot],
                )
                moved_dirs = player_try_move(
                    state, player_index, dirn, 0, track_thief=False,
                )
                state.player_joystick[player_index] = moved_dirs
                walking = moved_dirs != _NO_MOVE
                movement_destination = (
                    _player_record_cell(state, player_index) if walking else None
                )
            else:
                state.player_fighting_dir[player_index] = 0

        # Forcefield contact damage (0x4AA42-0x4AAB8; §4.3 TRAP 5).  It sits
        # *after* the move, which is why walking into a live segment is charged
        # on the frame the hero arrives.  Charged only when the field colour is
        # lit (not blinked off), the player is not acid-slowed, AND the player
        # is actually overlapping a forcefield -- the last gate
        # (check_forcefield_collision, 0x4AA68) was missing, which drained every
        # player on every lit frame regardless of position.
        if (state.forcefield_color != 0
                and player.acid_timer == 0
                and _check_forcefield_collision(state, player_index)):
            armor_bit = 1 if (player.powers & 0x02) else 0
            dmg = _FORCEFIELD_DAMAGE_TABLE[player.character + 4 * armor_bit]
            player.health = max(0, player.health - dmg)          # 0x4AAA8-0x4AAAE
            player.pending_damage += dmg
            state.health_dirty[player_index] = 1     # player_redraw bit 1
            # Signal a new-contact event to main_handle_death (§21): set to
            # negative only when the countdown is not already running.
            if state.forcefield_hurt_timer[player_index] == 0:
                state.forcefield_hurt_timer[player_index] = -_FORCEFIELD_HURT_TIMEOUT
            elif 0 < state.forcefield_hurt_timer[player_index] < _FORCEFIELD_HURT_TIMEOUT:
                state.forcefield_hurt_timer[player_index] = _FORCEFIELD_HURT_TIMEOUT
            _dialog(state, player_index, _DIALOG_FORCEFIELD)   # 0x4AAEE
            player.hurt_cooldown = 0x12                        # 0x4AAFC-0x4AB06

        # 0x4A91C jumps past the tile work but still lands on the shared
        # picture-table tail: a stunned hero keeps its sprite updated and still
        # contributes its keys, it simply does not consult this frame's
        # joystick.  ``walking`` is already False on that arm.
        if not stunned:
            # Tile interaction (§4.6): the cell the player's record now names,
            # taken from its H/V words with the ROM's own sprite bias
            # (``coords.mob_cell_of``).  This is where food/keys/potions/
            # treasure and power-ups are picked up, doors are opened, and exits
            # are taken (which drives the level transition, WP-20).
            #
            # 0x424EC-0x4254C is the shape: an *empty* entered cell needs no
            # interaction, because ``player_try_move`` has already migrated the
            # record into it and ``mob_slot`` is that cell. Only an occupied
            # one is offered to ``player_tile_interact`` -- and if the tile is
            # consumed the record follows the hero into the cell it just
            # cleared, on the same frame.
            #
            # ``player_tile_or_tport_dest`` still holds last frame's cell, so an
            # unchanged cell means "already interacted here"; without that edge
            # gate a non-consumed tile (an acid puddle, another hero's record)
            # would re-trigger every frame.
            current_tile_slot = _player_record_cell(state, player_index)
            if (current_tile_slot != player.mob_slot
                    and current_tile_slot != state.player_tile_or_tport_dest[player_index]):
                handled = player_tile_interact(
                    state, current_tile_slot, player_index,
                )
                if handled:
                    migrated = migrate_player_record(
                        state, player_index,
                    )                                       # 0x42588 -> 0x424F2
                    if (
                        not migrated
                        and state.player_tport_phase[player_index] < 0
                        and movement_origin is not None
                    ):
                        source, old_h, old_v = movement_origin
                        if player.mob_slot == source:
                            state.mobs.hpos[source] = old_h
                            state.mobs.vpos[source] = old_v
                            state.player_joystick[player_index] = _NO_MOVE
                            walking = False
                            movement_destination = source
                elif movement_origin is not None:
                    source, old_h, old_v = movement_origin
                    if player.mob_slot == source:
                        state.mobs.hpos[source] = old_h
                        state.mobs.vpos[source] = old_v
                        state.player_joystick[player_index] = _NO_MOVE
                        walking = False
                        movement_destination = source
            if movement_destination is not None:
                _track_thief_victim_move(
                    state, player_index, movement_destination,
                )

        _advance_player_sprite(
            state, player_index, walking=walking, fire_held=fire_held,
        )
        keys_held += player.keysnum                  # 0x4AC8C: add.w -2(a6),d2

    # Maintain the camera-tracking arrays (0x904BD8 / 0x904BCE) from live
    # player state -- the player subsystem owns these; the camera only reads
    # them (§17).  A player's current cell is the cell its migrating record now
    # occupies, which is ``mob_slot`` itself except on the rare frame where an
    # occupied destination held the record back.
    for i, player in enumerate(state.players):
        if player.active:
            if state.player_tport_phase[i] >= 0:
                # Mid-transition: player_tile_or_tport_dest already holds the
                # destination cell and main_scroll_playfield is panning towards
                # it, so recomputing it from the hero's (still unmoved) pixels
                # would drag the camera back.
                state.player_in_maze[i] = 1
                continue
            state.player_tile_or_tport_dest[i] = _player_record_cell(state, i)
            state.player_in_maze[i] = 1
        else:
            state.player_in_maze[i] = 0

    # ── Section 4: post-loop ──────────────────────────────────────────────────
    # 0x4ACD4 (``tst.w -4(a6)`` / ``beq 0x4AD44``) gates the whole block -- both
    # the door-idle sweep and the escape timeout -- on at least one player
    # having been counted at 0x4A8B4.  That counter is only written in normal
    # play, so during the attract DEMO the demo hero moves, fights and picks
    # things up while ``idle_timer`` and ``escape_timer`` stand completely
    # still: no timed doors open and no wall is ever converted into an exit on
    # the attract screen.
    if active_processed == 0:
        return

    # Door idle timeout (0x4ACDA-0x4AD02).  ``idle_timer`` is the ROM's own
    # 0x90490C word: main_move_players advances it right here, and a negative
    # value disables the check (``tst.w``/``blt`` at 0x4ACE0).  The threshold is
    # 0xA8C frames while any player is carrying a key and 0x4B0 otherwise
    # (0x4ACEC/0x4ACF2) -- not the 3600-frame game_settings guess this used to
    # carry.  After the sweep the ROM stores 0xFFFF (0x4AD02), i.e. -1 as a
    # signed word, so the timed doors open exactly once per level.
    if state.idle_timer >= 0:
        state.idle_timer = (state.idle_timer + 1) & 0xFFFF
        threshold = (_DOOR_IDLE_THRESHOLD_WITH_KEYS if keys_held
                     else _DOOR_IDLE_THRESHOLD_NO_KEYS)
        if state.idle_timer > threshold:
            open_timed_doors(state)
            state.idle_timer = -1        # ROM writes 0xFFFF at 0x4AD02

    # Escape timeout (0x4AD06-0x4AD3C): at 0x5208 steps every wall becomes an
    # exit.  Sound 0x27 plays only when the conversion actually changed
    # something, and the level's cyclic-wall/trap flags are cleared afterwards
    # so the freshly-made exits are not cycled away again.
    state.escape_timer = (state.escape_timer + 1) & 0xFFFF
    if state.escape_timer >= _ESCAPE_TIMER_LIMIT:
        if maze_convert_walls_to_exits(state):
            _sound_play(state, _SOUND_ESCAPE_WALLS)
        state.escape_timer = 0
        state.level_flags_3 &= ~_ESCAPE_CLEARS_LEVEL_FLAGS_3 & 0xFF
# Fallback used only when player context is unavailable (Warrior base).
_PLAYER_SPEED = _PLAYER_SPEED_NORMAL[0] >> POS_SHIFT   # 1 px
_WORLD_PIXELS = 512   # 32 cells × 16 px/cell
