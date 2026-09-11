"""Exit commitment, maze rotation, level splashes, and post-spawn common tails."""

from __future__ import annotations

from .. import romtext
from ..constants import SLOT_EXIT_ANIMS, GameMode, MazeObjIds, PlayerStatus
from ..coords import position_field
from ..state import GameState
from .display import alpha_word, fill_alpha_rect, write_alpha_decimal, write_alpha_large_text, write_alpha_text
from .sound import sound_play, sound_speech_play
from .level_data import (
    _LFLAG3_EXIT_MOVES as _LFLAG3_EXIT_MOVES,
    _SECRET_MAZE_FIRST as _SECRET_MAZE_FIRST,
    _TREASURE_MAZE_FIRST as _TREASURE_MAZE_FIRST,
)

_LFLAG1_INVIS_TRAPWALLS = 0x80
_LFLAG2_INVIS_ALLWALLS = 0x80
_LFLAG4_SHOTS_STUN = 0x01
_LFLAG4_SHOTS_HURT = 0x02
_LFLAG4_PLAYER_OFFSCREEN = 0x80
_TREASURE_MAZE_LAST = 0x72    # 114

# treasure_room_duration, ROM 0x57358 -- four words indexed by
# player_activecount() - 1; show_level_start_screen stores value + 1 into
# treasure_timer (0x44F1A-0x44F32).  doc/05_data_reference.md §5.4.
_TREASURE_ROOM_DURATION = [0x04B0, 0x05A0, 0x05DC, 0x0618]  # 1200/1440/1500/1560


def _write_level_flag_hint(state: GameState, key: str) -> None:
    text, column, row, attribute = romtext.LEVEL_FLAG_HINTS[key]
    write_alpha_text(state, column, row, text, attribute)


def _write_level_splash_details(state: GameState) -> None:
    """0x4BE24-0x4C1B2 -- write flag notices and the lower gameplay hint."""
    from .level_state import in_bonus_room
    from .secret_rooms import (
        _write_secret_hint as _write_secret_hint,
    )

    speech_used = False
    if (
        state.level_next_potion == 0
        and state.levelnum_current >= 6
        and state.mazenum_current < _SECRET_MAZE_FIRST
    ):
        _write_level_flag_hint(state, "hidden_potion")
        if state.getrandom(4) == 0:
            sound_speech_play(state, 0x9B)
            speech_used = True

    if state.level_flags_4 & _LFLAG4_SHOTS_STUN:
        _write_level_flag_hint(state, "shots_stun")
        if not speech_used:
            sound_speech_play(state, 0x8C)
            speech_used = True
    if state.level_flags_4 & _LFLAG4_SHOTS_HURT:
        _write_level_flag_hint(state, "shots_hurt")
        if not speech_used:
            sound_speech_play(state, 0x99)
            speech_used = True
    if state.level_flags_4 & _LFLAG4_PLAYER_OFFSCREEN:
        _write_level_flag_hint(state, "player_offscreen")

    if state.level_flags_2 & _LFLAG2_INVIS_ALLWALLS:
        _write_level_flag_hint(state, "all_walls_invisible")
    elif state.level_flags & _LFLAG1_INVIS_TRAPWALLS:
        _write_level_flag_hint(state, "trap_walls_invisible")
        if not speech_used and state.getrandom(4) == 0:
            sound_speech_play(state, 0xCD)
            speech_used = True

    if state.level_flags_3 & _LFLAG3_EXIT_MOVES:
        _write_level_flag_hint(state, "exit_moves")
        if not speech_used and state.getrandom(4) == 0:
            sound_speech_play(state, 0xCE)

    row = 4 if state.levelnum_current == 1 else 15
    if state.levelnum_current == 1:
        text = romtext.GAMEPLAY_TIPS[-1][0]
        write_alpha_text(state, (29 - len(text)) // 2, row, text, 0x8000)
        return
    if state.secret_need_hint:
        _write_secret_hint(state)
        return
    if in_bonus_room(state) or state.game_settings & 0x0400:
        return

    first, second = romtext.GAMEPLAY_TIPS[state.getrandom(9)]
    if first:
        write_alpha_text(
            state, (29 - len(first)) // 2, row, first, 0x8000,
        )
        row += 1
    if second:
        write_alpha_text(
            state, (29 - len(second)) // 2, row, second, 0x8000,
        )


# ---------------------------------------------------------------------------
# Level-transition orchestration (WP-20) -- player_exit_sequence (0x52B40),
# maze_checknum (0x52ECA), show_level_start_screen (0x44DB4),
# show_level_end_bonus_screen (0x4D476).
# ---------------------------------------------------------------------------

# Highest live maze number in the rotation (mazes 5-101; doc/06 §3.2).
_MAZE_ROTATION_TOP = 101
# The catalog hinge: candidate maze 5 is replaced by the resume position
# (doc/06 §3.2, maze_checknum 0x52ED8).
_MAZE_ROTATION_HINGE = 5


def maze_checknum(state: GameState) -> None:
    """0x52ECA -- validate/wrap the candidate ``maze_next`` (doc/06 §3.2).

    Two rules, in order:

      * on entry, candidate 5 is substituted with the cabinet's resume
        position (``maze_number``) -- this is the hinge that makes level 6 land
        "wherever the rotation stands";
      * any candidate past the live range (> 101) wraps back to 5 and forces an
        EEPROM save (``eeprom_write_timer`` = 1); since 5 ≤ 101 the loop then
        settles. All 117 pointer-table entries are live, so only the > 101 wrap
        ever fires in practice.
    """
    if state.maze_next == _MAZE_ROTATION_HINGE:
        state.maze_next = state.maze_number
    while state.maze_next > _MAZE_ROTATION_TOP:
        state.maze_next = _MAZE_ROTATION_HINGE
        state.eeprom_write_timer = 1        # force a save next tick (0x904012)


def compute_next_level(state: GameState, exit_type: int) -> None:
    """The ``player_exit_sequence`` tail (0x52DB2-0x52E56): pick the next level
    and maze from the current position, ``exit_type``, and cabinet rotation
    (doc/06 §3.2/§3.4). Writes ``level_next`` and ``maze_next``; advances the
    stride when a step sequence lands back on maze 5.

    Deliberately a no-op inside a bonus room: the ROM's
    ``cmpi.w #0x68,mazenum_current`` at 0x52DBA skips the whole computation
    there, so a treasure room returns to the ``maze_next``/``level_next`` saved
    before it was interleaved -- the rotation maze it displaced is played next,
    at the same level number (doc/06 §3.5).
    """
    from .level_state import in_bonus_room

    if exit_type == int(MazeObjIds.EXITTO6):
        # EXITTO6 (maze 0 only): jump straight to level 6 at the resume
        # position, skipping the rest of the opening act (doc/06 §3.4). Does
        # not consult or bump the stride.
        state.level_next = 6
        state.maze_next = 6 - 1             # = 5, then substituted by resume
        maze_checknum(state)
        return

    if in_bonus_room(state):                # 0x52DBA -- keep the saved position
        return

    # Ordinary exit (doc/06 §3.2).
    level_next = state.levelnum_current + 1
    if level_next > 999:
        level_next -= 994                  # level 1000 wraps to 6

    state.maze_next = state.mazenum_current
    steps = 1
    if state.mazenum_current >= 5:
        steps += state.maze_stride         # coarser strides deeper in a lap
    for _ in range(steps):
        state.maze_next += 1
        maze_checknum(state)

    if state.maze_next == _MAZE_ROTATION_HINGE:
        state.maze_stride = (state.maze_stride + 1) & 7

    state.level_next = level_next


def _players_still_here(state: GameState) -> bool:
    """True while any player is still ALIVE_HERE (has not yet reached the exit)."""
    return any(p.status == int(PlayerStatus.ALIVE_HERE) for p in state.players)


def _players_exiting(state: GameState) -> bool:
    """True once at least one player has left the level through an exit.

    Status 8 is the animation still running (0x52C66), status 2 the hero that
    finished it (0x4A6B2); both are "on their way to the next level".
    """
    return any(
        p.status in (int(PlayerStatus.ALIVE_NEXT), int(PlayerStatus.EXITING))
        for p in state.players
    )


def player_exit_sequence(state: GameState, player_index: int,
                         exit_mob_slot: int, exit_type: int) -> None:
    """0x52B40 -- one player reaches an exit and starts the exit animation.

    Contract ``player_exit_sequence(player_index, exit_mob_slot, exit_type)``
    (doc/04 §12.1). Steps: play the per-player exit sound (0x0E-0x11), park the
    player in **status 0x08** (0x52C66), stand the exit-animation MOB up over
    the exit (0x52C6C-0x52D26, ``exit_create_player_anim`` 0x5DF80, slots
    0x15+player = ``SLOT_EXIT_ANIMS``), take the hero's own sprite out of the
    maze (0x52D76), drop the transport/reflect power bits (0x52D82), point
    ``active_mob_ids`` at the animation MOB (0x52DA0), zero the animation
    counter (0x52DAE), compute the next level/maze (``compute_next_level``),
    stop the treasure timer once the room is empty (0x52E56-0x52E88) and drop
    the ExitMoves flag (0x52EB4).

    **The level does not end here.**  The ROM leaves the hero in status 8 for
    the ~32-frame dissolve that ``main_move_players`` runs (0x4A646-0x4A6E6),
    and only when the *last* one finishes -- ``level_players_active`` reaching
    zero at 0x4A6E6 -- do the end-of-level countdowns and the tally screen run
    (0x4A748-0x4A78C).  ``players._status8_complete`` is that tail.
    """
    from .level_state import in_bonus_room
    from .secret_rooms import (
        secret_trick_check as secret_trick_check,
    )

    from .player_animation import _PORT_DIR_TO_ROM_DIR

    secret_trick_check(state, player_index)        # 0x52B60-0x52C4E

    sound_play(state, 0x0E + (player_index & 3))    # §12.1

    player = state.players[player_index]
    player.status = int(PlayerStatus.EXITING)      # 0x52C66
    player.exit_pending = 1
    state.player_in_maze[player_index] = 0

    # 0x52C6C-0x52D26: the animation MOB stands in the exit, one reserved slot
    # per player, wearing whatever picture the hero was wearing.  The ROM's
    # exit_create_player_anim (0x5DF80) is one of the managed low-slot placement
    # wrappers, so the slot is depth-keyed by the exit's own cell.
    anim_slot = SLOT_EXIT_ANIMS[player_index & 3]
    hero_slot = player.mob_slot
    picture = state.mobs.picture[hero_slot] if hero_slot else 0
    if state.mobs.picture[anim_slot]:
        state.mobs.unlink_and_clear(anim_slot)
    state.mobs.picture[anim_slot] = picture
    state.mobs.hpos[anim_slot] = (
        position_field(state.mobs.hpos[exit_mob_slot] - 0x200)
        + 0x0C + player_index
    ) & 0xFFFF                                     # 0x52C88-0x52CA2
    state.mobs.vpos[anim_slot] = (
        position_field(state.mobs.vpos[exit_mob_slot]) + 0x12
    ) & 0xFFFF                                     # 0x52CC6-0x52CD0
    state.mobs.insert(anim_slot, depth_key=exit_mob_slot)

    if hero_slot:                                  # 0x52D76: the hero leaves
        state.mobs.unlink_and_clear(hero_slot)
    player.powers &= 0xF3FF                        # 0x52D88
    from .player_lifecycle import player_inv_update

    player_inv_update(state, player_index)
    player.mob_slot = anim_slot                    # 0x52DA0
    player.anim_counter = 0                        # 0x52DAE
    # The dissolve starts by spinning the hero's facing down to 4 (0x4A672).
    state.player_death_anim_frame[player_index] = _PORT_DIR_TO_ROM_DIR[
        player.direction & 0x07
    ]

    compute_next_level(state, exit_type)           # 0x52DB2 tail

    # A bonus room's countdown stops as soon as the last player is out (0x52E88).
    if in_bonus_room(state) and not _players_still_here(state):
        state.treasure_timer = 0

    state.level_flags_3 &= ~_LFLAG3_EXIT_MOVES     # 0x52EB4 clears LFLAG bit 14


def advance_level_countdowns(state: GameState) -> bool:
    """The end-of-level bookkeeping at main_move_players 0x4A748-0x4A788.

    Runs once when the last player has left. The secret-room availability
    counter ticks down, and -- outside a bonus room, past level 6 -- so do the
    hidden-potion and treasure-room countdowns. A live 1 -> 0 transition proceeds
    directly to ``show_level_start_screen``, which interleaves the treasure room;
    only leaving a bonus room requests the visible tally.

    Lives here rather than in WP-6's ``main_move_players`` because the whole
    block exists to feed WP-15's treasure scheduling, and this reimplementation
    reaches the end of the level through ``player_exit_sequence``.
    """
    from .level_state import in_bonus_room

    if state.secret_possible_counter:                    # 0x4A748
        state.secret_possible_counter -= 1

    if in_bonus_room(state):                             # 0x4A756
        return True
    if state.level_next <= 6:                            # 0x4A760
        return False
    if state.level_next_potion:                          # 0x4A76C
        state.level_next_potion -= 1
    if not state.level_next_treasure:
        # The live schedule enters the room on the transition that decrements
        # 1 -> 0. Direct starts and historical snapshots can expose an
        # already-zero ordinary state; preserve the reachable arcade outcome
        # rather than showing an otherwise unreachable pre-room tally.
        return False
    state.level_next_treasure -= 1
    return False


def show_level_start_screen(state: GameState) -> None:
    """0x44DB4 -- interleave a secret room or a treasure room into the level.

    Called on every level transition, after ``levelnum_current``/
    ``mazenum_current`` have been committed and before the maze is loaded
    (main_start_game 0x480F2-0x48156). Past level 6 it takes one of two arms:

      * the **secret** arm (0x44DD6-0x44E8E, ``_enter_secret_room``) when a
        player won the level's trick and is standing in the exit -- the maze
        becomes 115 or 116 and the trick is replaced by a challenge task;
      * otherwise the **treasure** arm (0x44E92-0x44F32), when the countdown
        maintained by ``advance_level_countdowns`` has reached zero:
        ``mazenum_current`` becomes ``treas_mazerand_num``, the treasure rotation
        steps on by ``treas_mazerand_adder + 1`` (wrapping 114 back into 104-114
        and bumping the adder whenever a lap lands exactly on 104), and
        ``treasure_timer`` is loaded from ``treasure_room_duration`` (0x57358)
        plus one (doc/06 §3.5).

    ``maze_next``/``level_next`` are deliberately left alone by both: a bonus
    room borrows the level number, and the rotation maze it displaced is played
    next (``compute_next_level`` skips its computation from a bonus room).

    The level-6 seed of ``level_next_treasure`` belongs to
    ``maze_new_level_setup`` (0x438E4-0x438FC), which the ROM runs immediately
    after this call. The port applies the seed here, before the subsequent
    maze load, rather than inside ``load_level``.
    """
    from .level_state import in_bonus_room, in_secret_room, player_activecount
    from .secret_rooms import (
        _enter_secret_room as _enter_secret_room,
        _write_secret_room_start as _write_secret_room_start,
    )

    if state.levelnum_current > 6:                               # 0x44DCA
        entered_secret = _enter_secret_room(state)               # 0x44DD6
        if not entered_secret and state.level_next_treasure == 0:   # 0x44E92
            state.level_next_treasure = state.getrandom(3) + 3   # 0x44E9C-0x44EAC
            state.mazenum_current = state.treas_mazerand_num     # 0x44EB2-0x44EB8

            state.treas_mazerand_num += state.treas_mazerand_adder + 1   # 0x44ECA
            if state.treas_mazerand_num > _TREASURE_MAZE_LAST:           # 0x44ED8
                state.treas_mazerand_num -= 11                           # 0x44EE4
                if state.treas_mazerand_num == _TREASURE_MAZE_FIRST:     # 0x44EFC
                    state.treas_mazerand_adder = (state.treas_mazerand_adder + 1) & 3

            players = min(4, max(1, player_activecount(state)))       # 0x44F1A
            state.treasure_timer = _TREASURE_ROOM_DURATION[players - 1] + 1
            state.treasure_announcement_delay = 0
            state.treasure_voice_set = 0

    # maze_new_level_setup 0x438E4: the countdown is armed the first time the
    # cabinet reaches level 6.
    if state.levelnum_current == 6:
        state.level_next_treasure = state.getrandom(3) + 3

    from .player_lifecycle import setup_infopanel

    setup_infopanel(state, -1)                               # 0x44F38-0x44F3E
    fill_alpha_rect(state, 0, 0, 29, 30, alpha_word(0x8000)) # 0x44F44-0x44F66
    sound_play(state, 0xD7)                                  # 0x44F68-0x44F6E
    if in_secret_room(state):
        _write_secret_room_start(state)
    elif _TREASURE_MAZE_FIRST <= state.mazenum_current <= _TREASURE_MAZE_LAST:
        write_alpha_large_text(
            state, 1, 5, romtext.TREASURE_ROOM_TITLE, 0x8000,
        )
        for text, column, row, attribute in romtext.TREASURE_ROOM_LINES:
            write_alpha_text(state, column, row, text, attribute)
        seconds = state.treasure_timer // 60
        write_alpha_decimal(state, 14, 11, seconds, 2, 0x8000)
        write_alpha_large_text(state, 34, 2, f"{seconds:>2}", 0x8000)
    elif not in_bonus_room(state):
        write_alpha_large_text(
            state, 4, 9, romtext.TEXT_LEVEL_SPLASH, 0x8000,
        )
        write_alpha_large_text(
            state, 16, 9, f"{state.levelnum_current:>3}", 0x8000,
        )
    _write_level_splash_details(state)

    # 0x45228-0x45260: normal/reduced-text/secret-room display holds.
    state.global_delay_timer = (
        0x258 if in_secret_room(state)
        else (0x96 if state.game_settings & 0x400 else 0xB4)
    )


def _finish_level_end(state: GameState) -> None:
    """Prepare the next maze and level splash when the prior display ends.

    This is the ``main_start_game`` transition tail (0x480F2-0x48156): the
    position is already committed, so run ``show_level_start_screen`` -- which
    may replace the maze with a treasure room -- and load it without placing
    players until the splash's shared UI timer expires.
    """
    from .treasure_rooms import (
        _exiting_or_here as _exiting_or_here,
    )

    from .display import clear_alpha_visible

    clear_alpha_visible(state)
    sound_play(state, 0x39)                          # 0x4812E-0x48134
    show_level_start_screen(state)                   # 0x4813A
    if state.mazenum_current < _TREASURE_MAZE_FIRST:
        sound_play(state, 0x42)                      # 0x48140-0x4814E
    state.level_start_pending = _load_next_level(
        state, state.levelnum_current, _exiting_or_here(state),
        spawn_players=False,
    )
    if not state.level_start_pending:
        state.global_delay_timer = 0
    state.bonus_amount = 0
    state.game_mode = GameMode.NORMAL


def update_monster_spawn_bonus_from_score_per_coin(state: GameState) -> None:
    """0x48B58 -- make the generators harder for a rich party.

    Loops the four slots (0x48B6A-0x48B9A) and, for each player whose status is
    exactly 1 (ALIVE_HERE), accumulates ``player_coincount`` (0x904B2A) and
    ``player_score`` (0x904990).  Then ``monster_spawn_probability_bonus``
    (0x90405F) gains ``(total_score >> 14) / total_coins`` as a **signed byte
    add** (0x48B9C-0x48BA6), so the counter wraps the way the ROM's ``add.b``
    does and ``main_move_monsters`` keeps reading it as a signed byte.

    ``main_start_game`` calls it at the level handoff (0x4834E), where both the
    ordinary per-player placement loop and the secret-room arm converge -- once
    per level, on the frame the heroes are put into the new maze.  The ROM's
    ``divs.w`` would trap on a coinless party; every joined player carries at
    least one coin (0x48962), so the zero case simply does nothing here.
    """
    from .level_state import in_secret_room

    total_coins = 0
    total_score = 0
    for player in state.players:
        if player.status != int(PlayerStatus.ALIVE_HERE):      # 0x48B72
            continue
        total_coins += player.coin_count                       # 0x48B84
        total_score += player.score                            # 0x48B92
    if total_coins <= 0:
        return
    # 0x48B9C: asr.l #14, then a signed word divide, then a byte add.
    delta = (total_score >> 14) // total_coins
    state.monster_spawn_probability_bonus = (
        state.monster_spawn_probability_bonus + delta
    ) & 0xFF                                                   # 0x48BA6
    if in_secret_room(state):
        state.secret_saved_keys = state.monster_spawn_probability_bonus


def _load_next_level(
    state: GameState, level: int, survivors: list[int], *,
    spawn_players: bool = True,
) -> bool:
    """Swap in the committed maze and re-place ``survivors`` at its PLAYERSTARTs.

    A secret room takes the other spawn path (main_start_game 0x48232 ->
    0x482BC): only the winner goes in, and their inventory is stashed at the
    door. Every other maze runs ``secret_new_level_setup`` first, so the level's
    trick and the winner slot are refreshed before anybody is placed.

    Reloading needs the ROMs; if the maze cannot be decoded (no ROMs) the old
    maze is left intact and only the level counters have moved.
    """
    from .. import maze                              # bridge module (imports gex)
    # mazenum_current is already the maze to play -- the rotation's maze_next, or
    # the bonus room show_level_start_screen substituted for it.
    if not maze.reset_and_load_level(state, level, maze_number=state.mazenum_current):
        return False                                  # no ROMs: nothing to respawn into

    # player_start_inner clears player_treascount on every spawn (0x48E86); the
    # level total is cleared by load_level.
    state.player_treascount = [0] * len(state.players)
    if not spawn_players:
        return True

    _spawn_level_players(state, survivors)
    return True


def _spawn_level_players(state: GameState, survivors: list[int]) -> None:
    """Run main_start_game's post-splash player placement on the loaded maze."""
    from .level_state import in_secret_room, player_activecount
    from .secret_rooms import (
        secret_new_level_setup as secret_new_level_setup,
        secret_room_spawn as secret_room_spawn,
    )

    from .player_lifecycle import player_start_inner, setup_infopanel

    if in_secret_room(state):                        # 0x48232
        secret_room_spawn(state)
        update_monster_spawn_bonus_from_score_per_coin(state)   # 0x4834E
        from ..maze import maze_addrandompickups
        maze_addrandompickups(state, True)            # 0x48358
        from .thief import thief_setup

        thief_setup(state)                           # 0x4835E
        state.idle_timer = 0                         # 0x4836A
        return

    secret_new_level_setup(state)                    # 0x43916-0x4395C

    for i in survivors:
        if player_start_inner(state, i) == -1:       # world spawn (I-08)
            # 0x4825E-0x4828A is the survivor arm, not player_join_finalize:
            # restore status, redraw the panel, and clear this level's progress.
            # Join sounds, WELCOME speech, and join-time field resets belong only
            # to the actual join path through 0x48A36.
            state.players[i].status = int(PlayerStatus.ALIVE_HERE)
            setup_infopanel(state, state.secret_player)
            state.secret_tricks_flags[i] = 0         # next-level survivor, 0x48280

    # 0x4834E: both handoff arms converge here, with the heroes already back to
    # status 1, so the bonus is computed from the party that is about to play.
    update_monster_spawn_bonus_from_score_per_coin(state)
    from ..maze import maze_addrandompickups
    maze_addrandompickups(state, True)                # 0x48358
    from .thief import thief_setup

    thief_setup(state)                               # 0x4835E
    state.idle_timer = 0                             # 0x4836A
    if _TREASURE_MAZE_FIRST <= state.mazenum_current < 0x73:
        active = min(4, max(1, player_activecount(state)))
        sound_play(state, (0x40, 0x3F, 0x3E, 0x3D)[active - 1])  # 0x5790A
        sound_speech_play(
            state, (0x55, 0x56, 0x57)[state.getrandom(3)],
        )                                                   # 0x57962
    elif state.levelnum_current >= 6 and state.mazenum_current < 0x73:
        if state.getrandom(16) > 13:                        # 0x483CA-0x483DA
            sound_speech_play(
                state, (0x55, 0x58, 0x5E)[state.getrandom(3)],
            )                                               # 0x5796E
