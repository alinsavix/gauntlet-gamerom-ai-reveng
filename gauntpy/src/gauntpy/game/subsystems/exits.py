"""Exit scanning/movement and shared level predicates -- WP-15.

Transition, treasure-room, and secret-room routines have separate owners;
explicit imports retain their established entry points.

Reference: ``doc/04_game_subsystems.md`` §12, §16, §10.6;
``doc/06_maze_catalog.md`` §3.2-§3.5; ``doc/05_data_reference.md`` §5.5.
"""

from __future__ import annotations

from .. import romtext
from ..constants import (
    FIRST_PLAYABLE_SLOT,
    SLOT_EXIT_ANIMS,
    GameMode,
    MazeObjIds,
    PlayerStatus,
)
from ..coords import position_field, unpack_slot
from ..playfield_vram import (
    EXIT_ANIM_FRAMES,
    EXIT_SETTLED_DESC,
    exit_descriptor,
    write_tile_descriptor,
)
from ..state import NUM_PLAYERS, GameState
from .display import (
    alpha_word,
    fill_alpha_rect,
    write_alpha_decimal,
    write_alpha_large_text,
    write_alpha_text,
)
from .sound import sound_play, sound_speech_play


# Compatibility exports; each routine and table has a single game-side owner.
from .level_data import (
    _LFLAG3_EXIT_MOVES as _LFLAG3_EXIT_MOVES,
    _SECRET_MAZE_FIRST as _SECRET_MAZE_FIRST,
    _TREASURE_MAZE_FIRST as _TREASURE_MAZE_FIRST,
)
from .level_transitions import (
    _LFLAG1_INVIS_TRAPWALLS as _LFLAG1_INVIS_TRAPWALLS,
    _LFLAG2_INVIS_ALLWALLS as _LFLAG2_INVIS_ALLWALLS,
    _LFLAG4_PLAYER_OFFSCREEN as _LFLAG4_PLAYER_OFFSCREEN,
    _LFLAG4_SHOTS_HURT as _LFLAG4_SHOTS_HURT,
    _LFLAG4_SHOTS_STUN as _LFLAG4_SHOTS_STUN,
    _MAZE_ROTATION_HINGE as _MAZE_ROTATION_HINGE,
    _MAZE_ROTATION_TOP as _MAZE_ROTATION_TOP,
    _TREASURE_MAZE_LAST as _TREASURE_MAZE_LAST,
    _TREASURE_ROOM_DURATION as _TREASURE_ROOM_DURATION,
    _finish_level_end as _finish_level_end,
    _load_next_level as _load_next_level,
    _players_exiting as _players_exiting,
    _players_still_here as _players_still_here,
    _spawn_level_players as _spawn_level_players,
    _write_level_flag_hint as _write_level_flag_hint,
    _write_level_splash_details as _write_level_splash_details,
    advance_level_countdowns as advance_level_countdowns,
    compute_next_level as compute_next_level,
    maze_checknum as maze_checknum,
    player_exit_sequence as player_exit_sequence,
    show_level_start_screen as show_level_start_screen,
    update_monster_spawn_bonus_from_score_per_coin as update_monster_spawn_bonus_from_score_per_coin,
)
from .secret_rooms import (
    CHALLENGE_COUNT as CHALLENGE_COUNT,
    CHALLENGE_FIRST as CHALLENGE_FIRST,
    TRICK_BEPUSHY as TRICK_BEPUSHY,
    TRICK_DIET as TRICK_DIET,
    TRICK_IT as TRICK_IT,
    TRICK_NOFOOLED as TRICK_NOFOOLED,
    TRICK_NOGETHIT as TRICK_NOGETHIT,
    TRICK_NOGREEDY1 as TRICK_NOGREEDY1,
    TRICK_NOGREEDY2 as TRICK_NOGREEDY2,
    TRICK_NOHURTFRIENDS as TRICK_NOHURTFRIENDS,
    TRICK_NONE as TRICK_NONE,
    TRICK_NOUSEINVUL as TRICK_NOUSEINVUL,
    TRICK_NO_TREASURE as TRICK_NO_TREASURE,
    TRICK_SAVESUPERSHOTS as TRICK_SAVESUPERSHOTS,
    TRICK_WATCHSHOOT1 as TRICK_WATCHSHOOT1,
    TRICK_WATCHSHOOT2 as TRICK_WATCHSHOOT2,
    _CHALLENGE_ALWAYS as _CHALLENGE_ALWAYS,
    _CHALLENGE_CLEAR_MONSTERS as _CHALLENGE_CLEAR_MONSTERS,
    _CHALLENGE_MAZE_SPLIT as _CHALLENGE_MAZE_SPLIT,
    _CHALLENGE_POTIONS as _CHALLENGE_POTIONS,
    _CHALLENGE_POTIONS_TARGET as _CHALLENGE_POTIONS_TARGET,
    _CHALLENGE_REMOVE_TREASURE as _CHALLENGE_REMOVE_TREASURE,
    _CHALLENGE_REMOVE_TREASURE_TARGET as _CHALLENGE_REMOVE_TREASURE_TARGET,
    _CHALLENGE_TIMER_BASE as _CHALLENGE_TIMER_BASE,
    _CHALLENGE_TIMER_RANDOM_MINUTES as _CHALLENGE_TIMER_RANDOM_MINUTES,
    _CHALLENGE_TRANSPORTERS as _CHALLENGE_TRANSPORTERS,
    _CHALLENGE_TRANSPORTERS_TARGET as _CHALLENGE_TRANSPORTERS_TARGET,
    _CHALLENGE_TREASURES as _CHALLENGE_TREASURES,
    _CHALLENGE_TREASURES_TARGET as _CHALLENGE_TREASURES_TARGET,
    _CHALLENGE_WALLS as _CHALLENGE_WALLS,
    _CHALLENGE_WALLS_TARGET as _CHALLENGE_WALLS_TARGET,
    _CHALLENGE_WHILE_IT as _CHALLENGE_WHILE_IT,
    _SAVESUPERSHOTS_TARGET as _SAVESUPERSHOTS_TARGET,
    _SECRET_ROOM_BONUS as _SECRET_ROOM_BONUS,
    _SECRET_START_MAX as _SECRET_START_MAX,
    _SECRET_START_MIN as _SECRET_START_MIN,
    _SECRET_START_MISS_PENALTY as _SECRET_START_MISS_PENALTY,
    _SECRET_START_WIN_BONUS as _SECRET_START_WIN_BONUS,
    _TRICK_NOGETHIT_MIN_LEVEL as _TRICK_NOGETHIT_MIN_LEVEL,
    _enter_secret_room as _enter_secret_room,
    _maze_secret_for_hint as _maze_secret_for_hint,
    _secret_room_payout as _secret_room_payout,
    _write_secret_hint as _write_secret_hint,
    _write_secret_room_start as _write_secret_room_start,
    secret_check as secret_check,
    secret_check_winner as secret_check_winner,
    secret_new_level_setup as secret_new_level_setup,
    secret_room_spawn as secret_room_spawn,
    secret_trick_check as secret_trick_check,
    secret_trick_progress as secret_trick_progress,
    secret_trick_set as secret_trick_set,
    treasure_collected as treasure_collected,
)
from .treasure_rooms import (
    _BONUS_DISPLAY_FRAMES as _BONUS_DISPLAY_FRAMES,
    _FAKE_COUNTDOWN_MIN_LEVEL as _FAKE_COUNTDOWN_MIN_LEVEL,
    _FAKE_COUNTDOWN_ODDS as _FAKE_COUNTDOWN_ODDS,
    _GSETTING_SPEECH_DISABLE as _GSETTING_SPEECH_DISABLE,
    _TREASURE_FAKEOUT_SPEECH as _TREASURE_FAKEOUT_SPEECH,
    _TREASURE_FAKE_COUNTDOWN_SEQUENCES as _TREASURE_FAKE_COUNTDOWN_SEQUENCES,
    _TREASURE_SECONDS_SPEECH as _TREASURE_SECONDS_SPEECH,
    _TREASURE_TIMEOUT_SPEECH as _TREASURE_TIMEOUT_SPEECH,
    _TREASURE_WARNING_DELAY as _TREASURE_WARNING_DELAY,
    _TREASURE_WARNING_SPEECH as _TREASURE_WARNING_SPEECH,
    _WARNING_ODDS as _WARNING_ODDS,
    _bonus_recipients as _bonus_recipients,
    _countdown_speech as _countdown_speech,
    _exiting_or_here as _exiting_or_here,
    _treasure_shares as _treasure_shares,
    _write_bonus_alpha as _write_bonus_alpha,
    main_treasure_timer as main_treasure_timer,
    show_level_end_bonus_screen as show_level_end_bonus_screen,
)

# LFLAG3_EXIT_CHOOSEONE = 1 << 15 in the longword, i.e. bit 7 of the LFLAG3
# byte: "Exit1of", only one of several exits is real.  maze_new_level_setup
# tests the pair with ``andi.l #0xC000`` at 0x43B6A and only then calls
# maze_pick_one_exit, so a maze with neither flag keeps every exit it decoded.
_LFLAG3_EXIT_CHOOSEONE = 0x80
_LFLAG3_EXIT_PICK_MASK = _LFLAG3_EXIT_MOVES | _LFLAG3_EXIT_CHOOSEONE

# LFLAG4_EXIT_FAKE = 1 << 6 in the 32-bit longword.
# LFLAG4 is the fourth byte (bits 7-0 of the longword), so bit 6 in the
# longword = bit 6 of the LFLAG4 byte.
# Reference: gex.constants.LFLAG4_EXIT_FAKE; doc/04_game_subsystems.md §12
_LFLAG4_EXIT_FAKE = 0x40    # bit 6 of level_flags_4 byte

# Moving-exit timer reload = 0x12C (300 frames, 5 s).  Verified by disassembly:
# the game's exit_move_timer (0x904A08) is loaded with #0x12C both at level setup
# (0x43B90) and on reload inside main_exit_move (move.w #0x12c,(a0) at 0x52A74).
# Reference: doc/04_game_subsystems.md §12.2; main_exit_move (0x5287C).
_EXIT_MOVE_TIMER_RELOAD = 0x12C  # 300 frames

# The open/close stamp animation runs while exit_move_timer is negative: one step
# every fourth frame (``exit_move_timer & 3`` at 0x52A62), settling once the timer
# reaches -0x20 (0x52A6E), where it reloads.  So the real period between moves
# is 0x12C + 0x20 = 332 frames, not 300.
_EXIT_ANIM_SETTLE = -0x20        # 0x52A6E cmpi.w #$ffe0
_EXIT_ANIM_STEP_MASK = 3         # 0x52A66 moveq #3
# Marker the ROM ORs into a losing exit's hpos word when the FakeExit flag is
# set (0x43EAC); the exit tile stays but reads as a decoy.
_EXIT_FAKE_MARK = 0x10

# exit_move_stride, ROM 0x5B7FC (row76.bin offset 0x1B7FC) -- 33 bytes indexed
# by exit_count.  main_exit_move adds the selected entry to the open exit's
# index in exit_slot_list to pick the next one (0x528D8-0x528EA).
_EXIT_ROTATION_OFFSET_BY_COUNT = [
    0, 1, 1, 2, 3, 3, 5, 3, 3, 5, 7, 5, 5, 5, 5, 7,
    7, 7, 7, 7, 7, 5, 7, 7, 7, 11, 11, 11, 11, 11, 11, 0, 0,
]
# maze_new_level_setup stops recording exits at 32 (0x43A3A).
_MAX_EXIT_SLOTS = 0x20
TRICK_TRANSPORT1 = 1        # try transportability (land beside acid)
TRICK_TRANSPORT2 = 2        # ... onto death
TRICK_TRANSPORT3 = 3        # ... into the exit
TRICK_TRANSPORT4 = 4        # ... corner-transport through a secret wall
TRICK_PUSHWALL = 10

#: What each progress hook should name, so a caller never has to remember which
#: way round §3.17's two "greedy" entries go.
TRICK_NO_FOOD = TRICK_DIET              # 0x0D, bumped by eating
# Tricks 0x0F-0x11 need somebody else on the level; main_start_game cancels them
# in solo play (0x48294-0x482B2).
_TRICK_MULTIPLAYER_FIRST = 0x0F
_TRICK_MULTIPLAYER_LAST = 0x11


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def player_activecount(state: GameState) -> int:
    """0x4D900 ``player_activecount`` -- players with status 1, 2, 8 or 0x10.

    Reference: doc/04_game_subsystems.md §16; PlayerStatus values 1/2/8/0x10
    = ALIVE_HERE / ALIVE_NEXT / RESPAWN_WAIT / SELECTING.
    """
    active_statuses = (
        int(PlayerStatus.ALIVE_HERE),
        int(PlayerStatus.ALIVE_NEXT),
        int(PlayerStatus.RESPAWN_WAIT),
        int(PlayerStatus.SELECTING),
    )
    return sum(1 for p in state.players if p.status in active_statuses)


def in_bonus_room(state: GameState) -> bool:
    """True in any bonus room -- treasure (104-114) or secret (115/116).

    This is the ROM's own test, ``cmpi.w #0x68,mazenum_current`` followed by a
    carry-clear branch, used at 0x4D2D0, 0x4A756, 0x52DBA and 0x52E56.
    """
    return state.mazenum_current >= _TREASURE_MAZE_FIRST


def in_secret_room(state: GameState) -> bool:
    """True in a secret room (maze 115 or 116) -- ``cmpi.w #0x73`` at 0x48232,
    0x43916, 0x4D496, 0x4D544 and 0x4D8CA."""
    return state.mazenum_current >= _SECRET_MAZE_FIRST


# ---------------------------------------------------------------------------
# main_exit_move (0x5287C) -- the moving exit
# ---------------------------------------------------------------------------

def exit_scan_level(state: GameState) -> None:
    """Rebuild the level's exit table -- ``maze_new_level_setup``'s exit work.

    Three ROM steps, in order:

      * the decode pass records every ``MAZEOBJ_EXIT`` tile into
        ``exit_slot_list`` (0x910740), capping the list at 32 (0x43A34-0x43A5A);
      * when the level carries ExitMoves or Exit1of (``andi.l #0xC000`` at
        0x43B6A), ``maze_pick_one_exit`` (0x43D8C, called with 0 at 0x43B76)
        chooses which of them is real;
      * the ExitMoves flag then either arms ``exit_move_timer`` with 0x12C or clears
        ``exit_open_id`` (0x43B7E-0x43B9A).

    WP-3's ``load_level`` does not build the list, so WP-15 recovers it from the
    MOB table -- a slot number *is* its cell address, so the scan is exact. It
    starts at ``FIRST_PLAYABLE_SLOT`` because the ROM's own scan starts at slot
    0x20 (``moveq #$20,d3`` at 0x43DA6) and row 0 is the reserved wall fill.

    Safe to call twice for the same maze, which matters while the common
    level-load path and this module's own transition path may both call it: the
    pick *removes* the losing exits, so a naive re-scan would see a single exit
    and disarm the level. The guard below recognises an already-picked table --
    the fresh scan is explained by the previous ``exit_slots`` and the open exit
    is still one of them -- and leaves it alone.
    """
    slots = [
        slot for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link))
        if state.mobs.obj_type(slot) == int(MazeObjIds.EXIT)
    ][:_MAX_EXIT_SLOTS]

    if (
        state.exit_slots
        and state.exit_open_id in slots
        and set(slots) <= set(state.exit_slots)
    ):
        return                                            # already scanned

    state.exit_slots = slots
    state.exit_close_id = 0
    state.exit_open_id = 0
    state.exit_anim_frame = 0

    maze_pick_one_exit(state)                             # 0x43B62-0x43B76

    if state.level_flags_3 & _LFLAG3_EXIT_MOVES:
        state.exit_move_timer = _EXIT_MOVE_TIMER_RELOAD   # 0x43B90
    else:
        state.exit_open_id = 0                            # 0x43B9A


def maze_pick_one_exit(state: GameState) -> None:
    """0x43D8C called with 0 -- pick the one real exit out of the level's exits.

    Gated at 0x43B62-0x43B72 on ExitMoves or Exit1of (LFLAG longword bits 14-15),
    so an ordinary maze keeps every exit it decoded. When it does run it counts
    the exit tiles (0x43DA6-0x43DD8) and then:

      * **no exits** -- nothing to do (0x43DFE);
      * **exactly one exit** -- clear the ExitMoves flag (0x43ED4-0x43EE8), which
        is why a single-exit maze can never have a moving exit no matter what its
        header says, and why ``exit_open_id`` is left alone there;
      * **more than one** -- ``getrandom(count)`` picks the real one, whose slot
        becomes ``exit_open_id`` (0x43E28-0x43E8C). Every other exit is either
        marked as a decoy, when the FakeExit flag (LFLAG4 bit 6) is set -- the
        ROM ORs 0x10 into its hpos word at 0x43EAC and the exit-collision path
        reads it back -- or removed outright (``mob_remove`` at 0x43EBC), which
        is the Exit1of behaviour.
    """
    if not state.level_flags_3 & _LFLAG3_EXIT_PICK_MASK:  # 0x43B6A
        return

    count = len(state.exit_slots)
    if count == 0:                                        # 0x43DFA-0x43DFE
        return
    if count == 1:                                        # 0x43ED4-0x43EE8
        state.level_flags_3 &= ~_LFLAG3_EXIT_MOVES
        return

    chosen = state.getrandom(count)                       # 0x43E2E
    state.exit_open_id = state.exit_slots[chosen]         # 0x43E8C
    fake_exits = state.level_flags_4 & _LFLAG4_EXIT_FAKE  # 0x43E98
    for index, slot in enumerate(state.exit_slots):
        if index == chosen:
            continue
        if fake_exits:
            state.mobs.hpos[slot] |= _EXIT_FAKE_MARK      # 0x43EAC
        else:
            from ..maze import clear_cell_descriptor
            clear_cell_descriptor(state, slot)
            state.mobs.unlink_and_clear(slot)             # 0x43EBC mob_remove


def exit_get_id(state: GameState, slot: int) -> int:
    """0x52B06 ``exit_get_id`` -- index of *slot* in ``exit_slots``.

    Returns ``exit_count`` when the slot is not in the list, exactly as the
    ROM's loop falls out at 0x52B2C.
    """
    for index, candidate in enumerate(state.exit_slots):
        if candidate == slot:
            return index
    return len(state.exit_slots)


def main_exit_move(state: GameState) -> None:
    """0x5287C -- relocate the open exit while the ExitMoves flag is set.

    The ROM does not teleport a tile to a random cell (``maze_randomplace``,
    0x42E9A, is the *pickup* placer and is never called from here -- its only
    reference in the whole game ROM is ``maze_addrandompickups``' A3 at
    0x43F7C).  Every exit the maze decoded is already in ``exit_slot_list``, and
    this call walks that list with the stride from 0x5B7FC, destroying the exit
    MOB at the old slot and creating it at the new one (0x528C2-0x52A58).

    Gate (0x52890-0x528B6): ``exit_open_id`` must be nonzero, and either the
    timer has already run out or the ExitMoves flag is set with players on the
    level.  Then:

      * timer reaches **0** -- the swap happens and sound 0x31 plays
        (0x528BC-0x52A58);
      * timer **negative** -- the open/close stamp animation advances one step
        every fourth frame (``_exit_move_animate``, 0x52A5C-0x52AF8);
      * timer reaches **-0x20** -- the exit settles and the timer reloads to
        0x12C (0x52A74), so the true period between moves is 332 frames.

    Reference: doc/04_game_subsystems.md §12.2.
    """
    if not state.exit_open_id:                  # 0x52890
        return
    if state.exit_move_timer > 0 and not (
        state.level_flags_3 & _LFLAG3_EXIT_MOVES and state.level_players_active
    ):
        return                                  # 0x5289A-0x528B6

    state.exit_move_timer -= 1                  # 0x528BA
    if state.exit_move_timer == 0:              # 0x528BC ``bne`` -- swap frame
        _exit_relocate(state)
        return
    if state.exit_move_timer > 0:
        return

    _exit_move_animate(state)                   # 0x52A5C


def _exit_move_animate(state: GameState) -> None:
    """0x52A5C-0x52AF8 -- the 32-frame open/close animation, then the reload.

    While ``exit_move_timer`` is negative the ROM stamps one frame of the closing
    script over ``exit_close_id`` and one frame of the opening script over
    ``exit_open_id`` every fourth frame, indexed by ``(-exit_move_timer) >> 2``.  The
    scripts themselves are playfield stamp descriptors reached through
    ``ptr_exit_openclose_anim`` (0x90489C, set from 0x5B81C + floorpattern*0x40
    at 0x44BAA) and drawn by ``pf_stamp_update`` (0x5E536) -- pixels, owned by
    WP-2 -- so what is modelled here is the step counter and the cadence it
    gates, which is what makes an exit take 332 frames rather than 300 to move
    again.

    At -0x20 the exit settles: the timer reloads to 0x12C, the open exit gets its
    resting stamp (0x5C8A0) and the vacated cell's floor is repainted by
    ``pf_floor_update`` (0x5E892) -- the MOB there was already cleared when the
    swap happened, so nothing more is owed to the simulation.
    """
    if state.exit_move_timer & _EXIT_ANIM_STEP_MASK:      # 0x52A62-0x52A6A
        return

    if state.exit_move_timer <= _EXIT_ANIM_SETTLE:        # 0x52A6E
        state.exit_move_timer = _EXIT_MOVE_TIMER_RELOAD   # 0x52A74
        state.exit_anim_frame = 0                         # settled stamp 0x5C8A0
        write_tile_descriptor(state, state.exit_open_id, EXIT_SETTLED_DESC)
        if state.exit_close_id:
            from ..maze import write_floor_descriptor
            write_floor_descriptor(state, state.exit_close_id)
        state.exit_close_id = 0                           # vacated cell repainted
        return

    state.exit_anim_frame = (-state.exit_move_timer) >> 2  # 0x52AAC-0x52AB4
    floorpattern = int(getattr(state.maze, "floorpattern", 0) or 0)
    write_tile_descriptor(
        state, state.exit_open_id,
        exit_descriptor(floorpattern, EXIT_ANIM_FRAMES + state.exit_anim_frame),
    )
    if state.exit_close_id:
        write_tile_descriptor(
            state, state.exit_close_id,
            exit_descriptor(floorpattern, state.exit_anim_frame),
        )


def _exit_relocate(state: GameState) -> None:
    """Move the open exit one stride along ``exit_slots`` (0x528C2-0x52A58)."""
    old_slot = state.exit_open_id
    state.exit_close_id = old_slot              # 0x528C8
    state.exit_anim_frame = 0                   # opening/closing scripts frame 0

    count = len(state.exit_slots)
    if count == 0:
        return
    index = exit_get_id(state, old_slot) + _EXIT_ROTATION_OFFSET_BY_COUNT[count]  # 0x528D8
    if index >= count:                          # 0x528EC-0x528F4
        index -= count
    new_slot = state.exit_slots[index]
    state.exit_open_id = new_slot               # 0x52908
    data = getattr(state.maze, "data", None)
    if data is not None and new_slot != old_slot:
        old_row, old_col = unpack_slot(old_slot)
        new_row, new_col = unpack_slot(new_slot)
        data[(old_col, old_row)] = int(MazeObjIds.TILE_FLOOR)
        data[(new_col, new_row)] = int(MazeObjIds.EXIT)
    floorpattern = int(getattr(state.maze, "floorpattern", 0) or 0)
    write_tile_descriptor(
        state, old_slot, exit_descriptor(floorpattern, 0),
    )
    write_tile_descriptor(
        state, new_slot, exit_descriptor(floorpattern, EXIT_ANIM_FRAMES),
    )

    sound_play(state, 0x31)                     # "exit moves", 0x52A4C
    if new_slot == old_slot:
        # Single-exit maze: the stride wraps straight back. maze_pick_one_exit
        # clears the ExitMoves flag in that case (0x43EDE) so the ROM never gets
        # here; guarded because nothing has actually moved.
        return

    # A player standing on the destination exits through it (0x5293C-0x52958);
    # anything else in the way is removed (0x5296E).
    if state.mobs.is_occupied(new_slot):        # 0x52918
        for index_, player in enumerate(state.players):
            if player.mob_slot == new_slot and player.status == int(PlayerStatus.ALIVE_HERE):
                state.movement_type = 1         # 0x5293C
                player_exit_sequence(state, index_, new_slot, int(MazeObjIds.EXIT))
                break
        if state.mobs.is_occupied(new_slot):
            state.mobs.unlink_and_clear(new_slot)

    if state.mobs.is_occupied(old_slot):
        state.mobs.unlink_and_clear(old_slot)

    # 0x52984-0x52A32 rebuilds the tile marker from the destination slot. Moving
    # the old record would preserve its old H/V words, making a later exit
    # dissolve appear where the exit used to be.
    from ..maze import placement_geometry

    hpos, vpos = placement_geometry(int(MazeObjIds.EXIT), new_slot)
    state.mobs.picture[new_slot] = 0x8001
    state.mobs.hpos[new_slot] = hpos
    state.mobs.vpos[new_slot] = vpos
    state.mobs.set_obj_type(new_slot, int(MazeObjIds.EXIT))
    state.mobs.set_state(new_slot, 0)
