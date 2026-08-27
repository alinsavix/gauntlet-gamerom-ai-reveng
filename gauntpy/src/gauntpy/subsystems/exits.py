"""Exits, treasure rooms, and secret rooms -- WP-15.

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

# ---------------------------------------------------------------------------
# Level-flag bit masks (byte-level, as stored in GameState)
# ---------------------------------------------------------------------------

# LFLAG3_EXIT_MOVES = 1 << 14 in the 32-bit longword at 0x90491C.
# LFLAG3 is the third byte (bits 15-8 of the longword), so bit 14 in the
# longword = bit 6 of the LFLAG3 byte.
# Reference: gex.constants.LFLAG3_EXIT_MOVES; doc/04_game_subsystems.md §12.2
_LFLAG3_EXIT_MOVES = 0x40   # bit 6 of level_flags_3 byte

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
# the game's exit_timer (0x904A08) is loaded with #0x12C both at level setup
# (0x43B90) and on reload inside main_exit_move (move.w #0x12c,(a0) at 0x52A74).
# Reference: doc/04_game_subsystems.md §12.2; main_exit_move (0x5287C).
_EXIT_MOVE_TIMER_RELOAD = 0x12C  # 300 frames

# The open/close stamp animation runs while exit_timer is negative: one step
# every fourth frame (``exit_timer & 3`` at 0x52A62), settling once the timer
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
_EXIT_MOVE_STRIDE = [
    0, 1, 1, 2, 3, 3, 5, 3, 3, 5, 7, 5, 5, 5, 5, 7,
    7, 7, 7, 7, 7, 5, 7, 7, 7, 11, 11, 11, 11, 11, 11, 0, 0,
]
# maze_new_level_setup stops recording exits at 32 (0x43A3A).
_MAX_EXIT_SLOTS = 0x20

# Maze-number bands (doc/06 §3.5, §6).  Everything >= 104 is a bonus room; the
# treasure rooms are 104-114 and the two secret rooms are 115/116.
_TREASURE_MAZE_FIRST = 0x68   # 104
_TREASURE_MAZE_LAST = 0x72    # 114
_SECRET_MAZE_FIRST = 0x73     # 115

# treasure_room_duration, ROM 0x57358 -- four words indexed by
# player_activecount() - 1; show_level_start_screen stores value + 1 into
# treasure_timer (0x44F1A-0x44F32).  doc/05_data_reference.md §5.4.
_TREASURE_ROOM_DURATION = [0x04B0, 0x05A0, 0x05DC, 0x0618]  # 1200/1440/1500/1560

# game_settings (0x904A24) bit 11, "Disable Speech".  main_treasure_timer forces
# the timeout announcement to element 0 (ZERO) when it is set (0x4D41A-0x4D426).
_GSETTING_SPEECH_DISABLE = 0x800


# ---------------------------------------------------------------------------
# Secret rooms -- §10.6, doc/05_data_reference.md §3.17
# ---------------------------------------------------------------------------

# Maze-header trick IDs (the byte at maze header offset 0, gex ``Maze.secret``).
#
# **Corrected against the ROM.** doc/05_data_reference.md §3.17 lists
# ``TRICK_NOGREEDY2 = 13 (no treasure)`` and ``TRICK_DIET = 14 (no food)``, but
# ``player_tile_interact`` compares the other way round: the *treasure* arm tests
# 0x0E at 0x519C2 -- immediately above the ``player_treascount`` bump at
# 0x519F8 -- while both *food* arms test 0x0D at 0x51C0C and 0x51CEE,
# immediately above a ``player_health`` add (``add.l #100,0x904980[p]`` at
# 0x51CCC). The names below follow the ROM, so 13 is the food trick and 14 the
# treasure trick. Prefer the behaviour-named aliases in progress hooks.
TRICK_NONE = 0
TRICK_TRANSPORT1 = 1        # try transportability (land beside acid)
TRICK_TRANSPORT2 = 2        # ... onto death
TRICK_TRANSPORT3 = 3        # ... into the exit
TRICK_TRANSPORT4 = 4        # ... corner-transport through a secret wall
TRICK_WATCHSHOOT1 = 5       # watch what you shoot (foods)
TRICK_WATCHSHOOT2 = 6       # watch what you shoot (secret walls)
TRICK_SAVESUPERSHOTS = 7
TRICK_NOUSEINVUL = 8
TRICK_NOGETHIT = 9          # dragon progress byte must have low two bits clear
TRICK_PUSHWALL = 10
TRICK_NOFOOLED = 11
TRICK_NOGREEDY1 = 12        # 0x0C, no keys or potions (0x514D4, 0x5179C)
TRICK_DIET = 13             # 0x0D, no food (0x51C0C, 0x51CEE)
TRICK_NOGREEDY2 = 14        # 0x0E, no treasure (0x519C2)
TRICK_BEPUSHY = 15
TRICK_IT = 16
TRICK_NOHURTFRIENDS = 17

#: What each progress hook should name, so a caller never has to remember which
#: way round §3.17's two "greedy" entries go.
TRICK_NO_FOOD = TRICK_DIET              # 0x0D, bumped by eating
TRICK_NO_TREASURE = TRICK_NOGREEDY2     # 0x0E, bumped by collecting treasure

# "Save Super Shots" wants eleven banked (0x52BAA).
_SAVESUPERSHOTS_TARGET = 0x0B
# Trick 9 needs a dragon, which the rotation only produces from level 12
# (maze_new_level_setup 0x4394E).
_TRICK_NOGETHIT_MIN_LEVEL = 0x0C
# Tricks 0x0F-0x11 need somebody else on the level; main_start_game cancels them
# in solo play (0x48294-0x482B2).
_TRICK_MULTIPLAYER_FIRST = 0x0F
_TRICK_MULTIPLAYER_LAST = 0x11

# Challenge task codes: show_level_start_screen replaces the maze trick with
# ``0x50 + getrandom(14)`` (0x44E0C), a second namespace evaluated against the
# same per-player progress bytes.
CHALLENGE_FIRST = 0x50
CHALLENGE_COUNT = 0x0E
# Tasks 0x50-0x56 play in maze 115, 0x57-0x5D in maze 116 (0x44E1E-0x44E32).
_CHALLENGE_MAZE_SPLIT = 0x57

# challenge_timer_base, ROM 0x57360 -- 14 words, the secret room's base duration
# in frames, indexed by task code - 0x50 (doc/05_data_reference.md §5.4).
_CHALLENGE_TIMER_BASE = [
    1200, 1140, 1200, 1080, 900, 840, 1020,
    960, 1320, 660, 1080, 1140, 960, 1260,
]
# challenge_timer_random_minutes, ROM 0x5737C -- ``getrandom(value) * 60`` is
# added to the base above (0x44E5C-0x44E7E).
_CHALLENGE_TIMER_RANDOM = [6, 4, 6, 4, 6, 4, 6, 4, 6, 5, 5, 9, 4, 5]

# Qualification thresholds read by secret_check_winner (0x4D1A4).
_CHALLENGE_WALLS = (0x52, 0x5B)      # shoot 3 secret walls -> progress > 2
_CHALLENGE_WHILE_IT = 0x5C           # while you are IT     -> progress > 0
_CHALLENGE_POTIONS = (0x51, 0x5D)    # collect all potions  -> progress == 6
_CHALLENGE_TRANSPORTERS = 0x56       # use 5 transporters   -> progress == 0x3E
_CHALLENGE_TREASURES = 0x50          # collect 6 treasures  -> progress == 6
_CHALLENGE_REMOVE_TREASURE = 0x5A    # remove all treasure  -> progress == 0x13
_CHALLENGE_ALWAYS = (0x54, 0x55, 0x57, 0x58, 0x59)   # no extra condition
_CHALLENGE_CLEAR_MONSTERS = 0x53     # no monster or generator may remain
_CHALLENGE_WALLS_TARGET = 2
_CHALLENGE_POTIONS_TARGET = 6
_CHALLENGE_TRANSPORTERS_TARGET = 0x3E
_CHALLENGE_TREASURES_TARGET = 6
_CHALLENGE_REMOVE_TREASURE_TARGET = 0x13

# secret_check's adaptive pacing (0x4872C-0x48746).
_SECRET_START_WIN_BONUS = 0x0F
_SECRET_START_MAX = 0x28
_SECRET_START_MISS_PENALTY = 2
_SECRET_START_MIN = 4

# Completing the challenge pays 5000 per coin (0x4D778).
_SECRET_ROOM_BONUS = 0x1388


# ---------------------------------------------------------------------------
# Speech tables -- doc/05_data_reference.md §5.5, transcribed from row76.bin
# ---------------------------------------------------------------------------

# treasure_seconds_speech, ROM 0x5AB64 (row76.bin 0x1AB64) -- 11 longwords
# indexed *directly by the seconds remaining*, 0..10: ZERO, ONE, ... TEN
# (0x4D442-0x4D44C).  Element 0 is bypassed by the timeout branch but keeps the
# numeric table direct-indexed.
_TREASURE_SECONDS_SPEECH = [
    0x54,                          # 0     ZERO
    0x4A, 0x4B, 0x4C, 0x4D, 0x4E,  # 1-5   ONE..FIVE
    0x4F, 0x50, 0x51, 0x52, 0x53,  # 6-10  SIX..TEN
]

# treasure_fake_countdown_sequences, ROM 0x5AB90, reached through the four
# pointers at 0x5ABE0 (0x5AB90/0x5ABA4/0x5ABB8/0x5ABCC).  Each row is five
# speech IDs for displayed seconds 10 down to 6 -- deliberately scrambled, so
# the machine lies about how much time is left (0x4D382-0x4D3A0).
_TREASURE_FAKE_COUNTDOWN = [
    [0x4D, 0x50, 0x52, 0x4F, 0x51],  # FOUR SEVEN NINE SIX EIGHT
    [0x4C, 0x4D, 0x4E, 0x4F, 0x50],  # THREE FOUR FIVE SIX SEVEN
    [0x4B, 0x4C, 0x4D, 0x51, 0x52],  # TWO THREE FOUR EIGHT NINE
    [0x51, 0x50, 0x4F, 0x4E, 0x4D],  # EIGHT SEVEN SIX FIVE FOUR
]
# treasure_fakeout_speech, ROM 0x5ABF0 -- played once the fake countdown reaches
# displayed second 6 (0x4D3AA-0x4D3C0).
_TREASURE_FAKEOUT_SPEECH = [0xA5, 0xA6]          # JUST KIDDING / FOOLED YOU
# treasure_timeout_speech, ROM 0x5ABF8 (0x4D418-0x4D44C).
_TREASURE_TIMEOUT_SPEECH = [0x54, 0xA0, 0x54, 0xA7]
# treasure_warning_speech / treasure_warning_delay, ROM 0x5AC08 / 0x5AC18 --
# the six-second warning and how many countdown seconds it silences
# (0x4D3E4-0x4D40A).
_TREASURE_WARNING_SPEECH = [0xA1, 0xA2, 0xA3, 0xA4]
_TREASURE_WARNING_DELAY = [1, 2, 2, 2]
# The fake countdown is only armed above level 30 and only in a treasure (not
# secret) room, on a 1-in-16 roll at the ten-second mark (0x4D33E-0x4D364).
_FAKE_COUNTDOWN_ODDS = 0x10
_FAKE_COUNTDOWN_MIN_LEVEL = 0x1E     # 30
# The six-second warning fires on a 1-in-4 roll (0x4D3DA-0x4D3E2).
_WARNING_ODDS = 4


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _count_active_players(state: GameState) -> int:
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
# Secret rooms (§10.6): the level's trick, who wins it, and the challenge room
# ---------------------------------------------------------------------------

def secret_new_level_setup(state: GameState) -> None:
    """0x43916-0x4395C -- give the freshly loaded maze its secret objective.

    A secret room keeps the challenge it was entered with; an ordinary maze
    clears the objective and the winner, and then takes the maze header's trick
    byte (gex ``Maze.secret``) only when ``secret_possible_counter`` has run
    out. Trick 9 wants a dragon to survive, so it is cancelled below level 12.
    """
    if in_secret_room(state):                    # 0x43916
        return
    state.secret_trick_id = TRICK_NONE           # 0x43922
    state.secret_winner = -1                     # 0x43928, 0xFF = nobody
    if state.secret_possible_counter:            # 0x43930
        return
    state.secret_trick_id = getattr(state.maze, "secret", TRICK_NONE)   # 0x4393E
    if (state.secret_trick_id == TRICK_NOGETHIT                          # 0x43944
            and state.levelnum_current < _TRICK_NOGETHIT_MIN_LEVEL):
        state.secret_trick_id = TRICK_NONE       # 0x43958


def secret_trick_progress(state: GameState, player_index: int, trick_id: int,
                          amount: int = 1) -> None:
    """The ``addq.b #1,secret_tricks_flags[player]`` hook shape (§10.6).

    Every progress site in the ROM is the same two instructions guarded by the
    level's active objective -- ``cmpi.b #<trick>,trick_tasknum`` then bump the
    player's byte -- so the whole family reduces to this call. WP-15 owns the
    counter; the hooks that call it live with whatever subsystem notices the
    event (see ``secret_trick_set`` for the two assignment-shaped sites).
    """
    if state.secret_trick_id != trick_id:
        return
    flags = state.secret_tricks_flags
    flags[player_index] = (flags[player_index] + amount) & 0xFF


def secret_trick_set(state: GameState, player_index: int, trick_id: int,
                     value: int) -> None:
    """The ``move.b #n``/``clr.b`` progress sites (0x518C2, 0x498A4)."""
    if state.secret_trick_id != trick_id:
        return
    state.secret_tricks_flags[player_index] = value & 0xFF


def secret_trick_check(state: GameState, player_index: int) -> None:
    """0x52B60-0x52C4E -- did this exiting player satisfy the level's trick?

    Each trick reads the player's progress byte, or a counter another subsystem
    keeps, and a pass writes the player into ``secret_winner`` (0x52C46 copies
    ``current_player``, which inside ``player_exit_sequence`` is this player).
    ``TRICK_IT`` is the odd one out: it decides on the spot whether the exiting
    player is IT and then marks every player, so nobody else can claim it.
    """
    trick = state.secret_trick_id
    flags = state.secret_tricks_flags

    if trick == TRICK_IT:                                        # 0x52B60
        if (state.secret_winner < 0                              # 0x52B66
                and state.player_it == player_index              # 0x52B70
                and flags[player_index] != 1):                   # 0x52B7A
            state.secret_winner = player_index                   # 0x52B82
        for i in range(NUM_PLAYERS):                             # 0x52B88
            flags[i] = 1
        return

    progress = flags[player_index]
    if trick == TRICK_SAVESUPERSHOTS:                            # 0x52B9C
        won = state.players[player_index].supershot >= _SAVESUPERSHOTS_TARGET
    elif trick in (TRICK_WATCHSHOOT1, TRICK_WATCHSHOOT2):        # 0x52BB4
        won = progress > 1
    elif trick == TRICK_NOUSEINVUL:                              # 0x52BCE
        won = progress == 1
    elif trick in (TRICK_NOGETHIT, TRICK_DIET):                  # 0x52BE0: 9, 0x0D
        won = (progress & 3) == 0
    elif trick in (TRICK_NOFOOLED, TRICK_NOHURTFRIENDS):         # 0x52C00
        won = progress == 0
    elif trick in (TRICK_NOGREEDY1, TRICK_NOGREEDY2):            # 0x52C18: 0x0C, 0x0E
        won = (progress & 7) == 0
    elif trick == TRICK_BEPUSHY:                                 # 0x52C38
        won = state.movement_type == 0
    else:
        # Tricks 1-4 and 10 are decided by the transporter/wall paths, not by
        # reaching the exit, so they never resolve here.
        won = False

    if won:
        state.secret_winner = player_index                       # 0x52C46


def secret_check(state: GameState) -> None:
    """0x486FE -- adapt how often a secret room is offered.

    Runs at the end of a level that had an objective: a win records the maze in
    ``secret_prev_maze`` and pushes the reload value up by 15 (capped at 40), a
    miss pulls it down by 2 (floored at 4). ``secret_possible_counter`` then
    reloads, and ``advance_level_countdowns`` walks it down one level at a time.
    """
    if state.secret_trick_id == TRICK_NONE:                      # 0x48708
        return
    if 0 <= state.secret_winner < NUM_PLAYERS:                   # 0x48710/0x48718
        state.secret_prev_maze = state.mazenum_current           # 0x48722
        state.secret_possible_start = min(                       # 0x4872C
            state.secret_possible_start + _SECRET_START_WIN_BONUS,
            _SECRET_START_MAX,
        )
    else:
        state.secret_possible_start = max(                       # 0x4873E
            state.secret_possible_start - _SECRET_START_MISS_PENALTY,
            _SECRET_START_MIN,
        )
    state.secret_possible_counter = state.secret_possible_start  # 0x4874A


def secret_check_winner(state: GameState) -> bool:
    """0x4D1A4 -- was the secret room's challenge task completed?

    Reads the winner's progress byte against the task's target. Task 0x53 is the
    exception: it sweeps the MOB table and passes only when no monster or
    generator (object types 0x12-0x2D) is left standing (0x4D26C-0x4D290).
    """
    player = state.secret_winner
    if not 0 <= player < NUM_PLAYERS:
        return False
    task = state.secret_trick_id
    progress = state.secret_tricks_flags[player]

    if task in _CHALLENGE_WALLS:                                 # 0x4D1C0
        return progress > _CHALLENGE_WALLS_TARGET
    if task == _CHALLENGE_WHILE_IT:                              # 0x4D1DA
        return progress > 0
    if task in _CHALLENGE_POTIONS:                               # 0x4D1EA
        return progress == _CHALLENGE_POTIONS_TARGET
    if task == _CHALLENGE_TRANSPORTERS:                          # 0x4D204
        return progress == _CHALLENGE_TRANSPORTERS_TARGET
    if task == _CHALLENGE_TREASURES:                             # 0x4D216
        return progress == _CHALLENGE_TREASURES_TARGET
    if task == _CHALLENGE_REMOVE_TREASURE:                       # 0x4D228
        return progress == _CHALLENGE_REMOVE_TREASURE_TARGET
    if task in _CHALLENGE_ALWAYS:                                # 0x4D238-0x4D25C
        return True
    if task == _CHALLENGE_CLEAR_MONSTERS:                        # 0x4D262
        first, last = int(MazeObjIds.MONST_GHOST), int(MazeObjIds.GEN_AUX_GRUNT3)
        return not any(
            first <= state.mobs.obj_type(slot) <= last
            for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link))
        )
    return False


def _enter_secret_room(state: GameState) -> bool:
    """0x44DD6-0x44E8E -- swap the level for the winner's challenge room.

    Fires when a player won the level's trick and is standing in the exit. The
    maze trick is filed in ``secret_trick_last``, a random challenge task takes
    its place, and the room is maze 115 or 116 depending on the task. The time
    limit is the task's base duration plus ``getrandom(minutes) * 60``.
    """
    winner = state.secret_winner
    if not 0 <= winner < NUM_PLAYERS:                            # 0x44DD6/0x44DE0
        return False
    if state.players[winner].status != int(PlayerStatus.ALIVE_NEXT):   # 0x44DFA
        return False

    state.secret_trick_last = state.secret_trick_id              # 0x44E06
    task = CHALLENGE_FIRST + state.getrandom(CHALLENGE_COUNT)    # 0x44E0C
    state.secret_trick_id = task

    state.mazenum_current = _SECRET_MAZE_FIRST                   # 0x44E1E
    if task >= _CHALLENGE_MAZE_SPLIT:                            # 0x44E26
        state.mazenum_current += 1

    index = task - CHALLENGE_FIRST
    duration = _CHALLENGE_TIMER_BASE[index]                      # 0x44E44
    duration += state.getrandom(_CHALLENGE_TIMER_RANDOM[index]) * 60   # 0x44E5C
    state.treasure_timer = duration                              # 0x44E80
    state.secret_need_hint = 0                                   # 0x44E86
    state.treasure_announcement_delay = 0
    state.treasure_voice_set = 0
    return True


def _maze_secret_for_hint(state: GameState) -> int:
    """Read the selected maze header byte that level_splash sees at 0x4C084."""
    from ..maze import MazeError, decode_maze

    try:
        return int(decode_maze(state.mazenum_current).secret)
    except MazeError:
        return int(getattr(state.maze, "secret", TRICK_NONE) or TRICK_NONE)


def _write_secret_hint(state: GameState) -> None:
    """0x4C04E-0x4C108 -- consume secret_need_hint into alpha RAM."""
    if not state.secret_need_hint:
        return

    row = 4 if state.levelnum_current == 1 else 15
    if in_bonus_room(state):
        row += 2
    write_alpha_text(state, 4, row, romtext.SECRET_HINT_HEADER, 0x8000)
    row += 1

    trick = _maze_secret_for_hint(state)
    eligible = (
        TRICK_NONE < trick <= TRICK_NOHURTFRIENDS
        and state.secret_possible_counter == 0
        and (trick != TRICK_NOGETHIT or state.levelnum_current >= 12)
    )
    if not eligible:
        trick = state.getrandom(len(romtext.SECRET_OBJECTIVE_HINTS)) + 1
    text = romtext.SECRET_OBJECTIVE_HINTS[trick - 1]
    write_alpha_text(state, 14 - len(text) // 2, row, text, 0x8000)
    state.secret_need_hint = 0


def _write_secret_room_start(state: GameState) -> None:
    """0x44F7E-0x450F8 -- write the complete secret challenge invitation."""
    winner = state.secret_winner
    if not 0 <= winner < NUM_PLAYERS:
        return

    write_alpha_large_text(state, 4, 3, romtext.SECRET_ROOM_TITLE, 0x8000)
    attribute = 0x8400 + (winner << 10)
    write_alpha_large_text(
        state, 0, 7, romtext.PLAYER_COLOR_NAMES[winner], attribute,
    )
    character = state.players[winner].character & 3
    write_alpha_large_text(
        state, 13, 7, romtext.SECRET_CHARACTER_NAMES[character], attribute,
    )
    for text, column, row, text_attribute in romtext.SECRET_ROOM_LINES:
        write_alpha_text(state, column, row, text, text_attribute)

    seconds = state.treasure_timer // 60
    write_alpha_decimal(state, 10, 13, seconds, 2, 0x8000)
    qualifier = romtext.SECRET_CHALLENGE_QUALIFIERS[
        state.secret_trick_id - CHALLENGE_FIRST
    ]
    if qualifier is not None:
        text, column, row = qualifier
        write_alpha_text(state, column, row, text, 0x8400)
        if state.secret_trick_id == _CHALLENGE_WHILE_IT:
            write_alpha_text(state, 20, row, "IT", 0x8000)
    write_alpha_large_text(state, 34, 2, f"{seconds:>2}", 0x8000)


def secret_room_spawn(state: GameState) -> None:
    """0x482BC-0x4834E -- only the winner goes in, and they go in empty-handed.

    ``main_start_game`` spawns just ``secret_winner`` when the loaded maze is a
    secret room, stashes their keys, potions and super-shots, and zeroes them,
    so the challenge starts from nothing. ``show_level_end_bonus_screen`` adds
    the stash back on the way out.
    """
    from .players import player_start_inner

    winner = state.secret_winner
    if not 0 <= winner < NUM_PLAYERS:
        return
    player = state.players[winner]
    player_start_inner(state, winner)                            # 0x482CA
    player.status = int(PlayerStatus.ALIVE_HERE)                 # 0x482D8
    state.secret_saved_keys = player.keysnum                     # 0x482E6
    state.secret_saved_potions = player.potionsnum               # 0x482F6
    state.secret_saved_supershot = player.supershot              # 0x48306
    player.keysnum = 0                                           # 0x4831E
    player.potionsnum = 0
    player.supershot = 0
    state.secret_tricks_flags[winner] = 0    # player_start_inner 0x48ED6
    from .players import setup_infopanel

    setup_infopanel(state, winner)


def _secret_room_payout(state: GameState, completed: bool) -> bool:
    """0x4D720-0x4D8A0 -- pay the winner, hand their inventory back, stand down.

    Only ``secret_winner`` is considered; a completed task pays
    ``5000 x player_coincount``. Either way the stash is returned, the player is
    put back in the exiting state, and ``secret_winner`` is cleared so the next
    level does not walk straight back into another secret room.
    """
    winner = state.secret_winner
    state.bonus_amount = 0
    open_name_entry = False
    if 0 <= winner < NUM_PLAYERS:
        player = state.players[winner]
        if (completed                                            # 0x4D748
                and player.status in (int(PlayerStatus.ALIVE_NEXT),
                                      int(PlayerStatus.RESPAWN_WAIT))):
            open_name_entry = True
            bonus = _SECRET_ROOM_BONUS * max(1, player.coin_count)   # 0x4D778
            player.score += bonus                                # 0x4D788
            state.score_dirty[winner] = 1
            state.bonus_amount = bonus
        player.status = int(PlayerStatus.ALIVE_NEXT)             # 0x4D85C
        player.keysnum = (player.keysnum + state.secret_saved_keys) & 0xFF
        player.potionsnum = (player.potionsnum + state.secret_saved_potions) & 0xFF
        player.supershot = (player.supershot + state.secret_saved_supershot) & 0xFF
        from .players import player_inv_update

        player_inv_update(state, winner)
    state.secret_saved_keys = 0
    state.secret_saved_potions = 0
    state.secret_saved_supershot = 0
    if not open_name_entry:
        state.secret_winner = -1                                 # 0x4D866
    return open_name_entry


# ---------------------------------------------------------------------------
# main_treasure_timer (0x4D29E) -- countdown, speech, timeout
# ---------------------------------------------------------------------------

def _countdown_speech(state: GameState, seconds_remaining: int) -> None:
    """The once-per-second announcement block, 0x4D2FC-0x4D456 (§16).

    Ten seconds out the machine decides whether to lie: above level 30, in a
    treasure (not secret) room, a 1-in-16 roll arms one of the four scrambled
    sequences at 0x5AB90, which counts 10-6 with the wrong numbers and then owns
    up with JUST KIDDING / FOOLED YOU.  Otherwise the true number is spoken from
    0x5AB64, with a 1-in-4 taunt at six seconds and a parting shot at zero.
    """
    if seconds_remaining == 10:                          # 0x4D330
        state.treasure_announcement_delay = 0
        state.treasure_voice_set = 0
        if (
            state.mazenum_current < _SECRET_MAZE_FIRST
            and state.getrandom(_FAKE_COUNTDOWN_ODDS) == 0
            and state.levelnum_current > _FAKE_COUNTDOWN_MIN_LEVEL
        ):
            state.treasure_voice_set = state.getrandom(4) + 1

    if state.treasure_announcement_delay != 0:           # 0x4D366
        state.treasure_announcement_delay -= 1
        return

    if state.treasure_voice_set != 0 and seconds_remaining >= 6:   # 0x4D378
        sequence = _TREASURE_FAKE_COUNTDOWN[state.treasure_voice_set - 1]
        sound_play(state, sequence[seconds_remaining - 6])
        if seconds_remaining == 6:                       # 0x4D3A6: own up
            sound_play(state, _TREASURE_FAKEOUT_SPEECH[state.getrandom(2)])
            state.treasure_announcement_delay = 1
            state.treasure_voice_set = 0
        return

    if seconds_remaining == 6 and state.getrandom(_WARNING_ODDS) == 0:  # 0x4D3D4
        pick = state.getrandom(4)
        sound_speech_play(state, _TREASURE_WARNING_SPEECH[pick])
        state.treasure_announcement_delay = _TREASURE_WARNING_DELAY[pick]
        return

    if seconds_remaining == 0:                           # 0x4D414
        pick = 0 if state.game_settings & _GSETTING_SPEECH_DISABLE else state.getrandom(4)
        sound_play(state, _TREASURE_TIMEOUT_SPEECH[pick])
        return

    if seconds_remaining <= 10:                          # 0x4D43C
        sound_play(state, _TREASURE_SECONDS_SPEECH[seconds_remaining])


def main_treasure_timer(state: GameState) -> None:
    """0x4D29E -- treasure-room countdown, speech, and timeout.

    Four gates, in the ROM's order (0x4D2B2-0x4D2D8):

      * ``global_ui_delay_timer`` (0x904A4E) must be zero -- while a bonus tally
        or level splash is up, ``main_start_game`` runs down that shared timer
        and this routine leaves the treasure countdown frozen;
      * ``treasure_timer`` (0x9049E8) must be nonzero;
      * ``game_mode`` must be NORMAL (0);
      * ``mazenum_current`` must be >= 104 -- a treasure or secret room.

    The timer then decrements once per frame and every 60th frame speaks the
    remaining seconds (``_countdown_speech``).  When it reaches zero with at
    least one player still counted by ``player_activecount``, the level ends via
    ``show_level_end_bonus_screen`` (0x4D456-0x4D466).

    Reference: doc/04_game_subsystems.md §16.
    """
    # main_treasure_timer only tests this shared timer. main_start_game owns its
    # decrement and transition actions at 0x4817C-0x481E8.
    if state.bonus_timer > 0:
        return

    if state.treasure_timer <= 0:              # 0x4D2BC (also guards negatives)
        return
    if state.game_mode != int(GameMode.NORMAL):   # 0x4D2C6
        return
    if not in_bonus_room(state):               # 0x4D2D0
        return

    state.treasure_timer -= 1                  # 0x4D2DC

    # Every full second (60 frames), including the final zero.
    if state.treasure_timer % 60 == 0:         # 0x4D2EA divu #0x3C, remainder
        seconds_remaining = state.treasure_timer // 60
        write_alpha_large_text(
            state, 34, 2, f"{seconds_remaining:>2}", 0x8000,
        )                                       # 0x4D2FC-0x4D32A
        _countdown_speech(state, seconds_remaining)

    # Timer just expired: end the level if anyone is still present.
    if state.treasure_timer == 0:              # 0x4D456
        if _count_active_players(state) > 0:   # 0x4D45E level_players_active
            show_level_end_bonus_screen(state)


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
      * the ExitMoves flag then either arms ``exit_timer`` with 0x12C or clears
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

    While ``exit_timer`` is negative the ROM stamps one frame of the closing
    script over ``exit_close_id`` and one frame of the opening script over
    ``exit_open_id`` every fourth frame, indexed by ``(-exit_timer) >> 2``.  The
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
    index = exit_get_id(state, old_slot) + _EXIT_MOVE_STRIDE[count]  # 0x528D8
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


# ---------------------------------------------------------------------------
# Level-transition orchestration (WP-20) -- player_exit_sequence (0x52B40),
# maze_checknum (0x52ECA), show_level_start_screen (0x44DB4),
# show_level_end_bonus_screen (0x4D476).
# ---------------------------------------------------------------------------

# Highest live maze number in the rotation (mazes 5-101; doc/06 §3.2).
_MAZE_ROTATION_TOP = 101
# The catalog hinge: candidate maze 5 is replaced by the resume position
# (doc/06 §3.2, maze_checknum 0x52ED8).
_MAZE_RESUME_HINGE = 5


def maze_checknum(state: GameState) -> None:
    """0x52ECA -- validate/wrap the candidate ``maze_next`` (doc/06 §3.2).

    Two rules, in order:

      * on entry, candidate 5 is substituted with the cabinet's resume
        position (``maze_resume``) -- this is the hinge that makes level 6 land
        "wherever the rotation stands";
      * any candidate past the live range (> 101) wraps back to 5 and forces an
        EEPROM save (``eeprom_write_timer`` = 1); since 5 ≤ 101 the loop then
        settles. All 117 pointer-table entries are live, so only the > 101 wrap
        ever fires in practice.
    """
    if state.maze_next == _MAZE_RESUME_HINGE:
        state.maze_next = state.maze_resume
    while state.maze_next > _MAZE_ROTATION_TOP:
        state.maze_next = _MAZE_RESUME_HINGE
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

    if state.maze_next == _MAZE_RESUME_HINGE:
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
    from .players import _PORT_DIR_TO_ROM_DIR

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
    from .players import player_inv_update

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
    after this call; WP-3's ``load_level`` does not model it, so it is applied
    here in the same order the ROM performs it.
    """
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

            players = min(4, max(1, _count_active_players(state)))       # 0x44F1A
            state.treasure_timer = _TREASURE_ROOM_DURATION[players - 1] + 1
            state.treasure_announcement_delay = 0
            state.treasure_voice_set = 0

    # maze_new_level_setup 0x438E4: the countdown is armed the first time the
    # cabinet reaches level 6.
    if state.levelnum_current == 6:
        state.level_next_treasure = state.getrandom(3) + 3

    from .players import setup_infopanel

    setup_infopanel(state, -1)                               # 0x44F38-0x44F3E
    fill_alpha_rect(state, 0, 0, 29, 30, alpha_word(0x8000)) # 0x44F44-0x44F66
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
    _write_secret_hint(state)

    # 0x45228-0x45260: normal/reduced-text/secret-room display holds.
    state.bonus_timer = (
        0x258 if in_secret_room(state)
        else (0x96 if state.game_settings & 0x400 else 0xB4)
    )


# Bonus-screen hold before the next level loads: global_ui_delay_timer = 0x12C
# (300 frames, 5 s) at show_level_end_bonus_screen 0x4D50E.
_BONUS_DISPLAY_FRAMES = 0x12C


def _write_bonus_alpha(
    state: GameState, *,
    ordinary_rows: dict[int, tuple[int, int, int, int]],
    secret_player: int,
) -> None:
    """Write show_level_end_bonus_screen's exact small-alpha tally."""
    fill_alpha_rect(state, 0, 0, 29, 30, alpha_word(0x8000))
    if secret_player >= 0:
        attribute = 0x8400 + (secret_player << 10)
        row = 9 + secret_player * 5
        if state.bonus_amount:
            write_alpha_text(state, 4, row, romtext.BONUS_SECRET_5000, attribute)
            write_alpha_decimal(
                state, 19, row, state.bonus_amount, 7, attribute,
            )
        else:
            write_alpha_text(state, 4, row, romtext.BONUS_NONE, attribute)
        return

    for player_index, player in enumerate(state.players):
        attribute = 0x8400 + (player_index << 10)
        row = 8 + player_index * 5
        values = ordinary_rows.get(player_index)
        if values is None:
            if player.status == int(PlayerStatus.ALIVE_HERE):
                write_alpha_text(state, 4, row + 1, romtext.BONUS_NONE, attribute)
            continue
        player_factor, coin_factor, treasures, bonus = values
        write_alpha_text(state, 7, row, romtext.BONUS_100_X_COINS, attribute)
        write_alpha_decimal(state, 7, row, player_factor, 3, attribute)
        write_alpha_decimal(state, 22, row, coin_factor, 5, attribute)
        write_alpha_text(state, 9, row + 1, romtext.BONUS_TREASURES_X, attribute)
        write_alpha_decimal(state, 23, row + 1, treasures, 4, attribute)
        write_alpha_text(state, 13, row + 2, romtext.BONUS_EQUALS, attribute)
        write_alpha_decimal(state, 21, row + 2, bonus, 6, attribute)


def _exiting_or_here(state: GameState) -> list[int]:
    """Players who go on to the next level: still on it, or in the exit."""
    return [
        i for i, p in enumerate(state.players)
        if p.status in (int(PlayerStatus.ALIVE_NEXT), int(PlayerStatus.ALIVE_HERE))
    ]


def _bonus_recipients(state: GameState) -> list[int]:
    """Players the tally pays -- status 2 or 8 exactly (0x4D552/0x4D55E).

    Narrower than ``_exiting_or_here``: somebody still standing in a bonus room
    when its clock runs out never reached the exit, and the ROM pays them
    nothing.
    """
    return [
        i for i, p in enumerate(state.players)
        if p.status in (int(PlayerStatus.ALIVE_NEXT), int(PlayerStatus.RESPAWN_WAIT))
    ]


def treasure_collected(state: GameState, player_index: int) -> None:
    """A treasure pickup, with everything the ROM's treasure arm counts.

    ``player_tile_interact``'s treasure arm (0x519C2-0x519F8) is one block, so
    doing all of it here is what keeps the counters consistent:

      * the secret progress byte is bumped once at 0x519E4 when the level's
        objective is the *treasure* trick 0x0E (0x519C2), or the challenge task
        0x50 "after collecting 6 treasures" (0x519CE), or 0x5A "after removing
        all treasure" (0x519DA) -- three compares, one shared ``addq.b #1``, and
        since ``secret_trick_id`` holds exactly one code at a time the calls
        below likewise bump at most once;
      * ``player_treascount`` (0x904A50) is bumped at 0x519F8 -- the treasure
        factor of the level-end bonus (0x4D57E);
      * ``level_treasures`` stays as the level total the bonus screen displays.

    The *food* arms are a different block reporting 0x0D (0x51C0C, 0x51CEE);
    WP-6 owns those, so eating never advances a treasure objective and vice
    versa.
    """
    counts = state.player_treascount
    counts[player_index] = (counts[player_index] + 1) & 0xFF
    state.level_treasures += 1
    secret_trick_progress(state, player_index, TRICK_NO_TREASURE)          # 0x519C2
    secret_trick_progress(state, player_index, _CHALLENGE_TREASURES)       # 0x519CE
    secret_trick_progress(state, player_index, _CHALLENGE_REMOVE_TREASURE)  # 0x519DA


def _treasure_shares(state: GameState, recipients: list[int]) -> dict[int, int]:
    """Per-player treasure counts for the tally, with unattributed pickups.

    ``player_treascount`` is authoritative. Any treasure counted in
    ``level_treasures`` that no player claimed -- a pickup routed through the
    level total instead of ``treasure_collected`` -- is credited to the first
    recipient, which is what the level-wide tally did before the counter
    existed. The remainder is zero as soon as every pickup site attributes.
    """
    shares = {i: state.player_treascount[i] for i in recipients}
    unattributed = state.level_treasures - sum(state.player_treascount)
    if unattributed > 0 and recipients:
        shares[recipients[0]] += unattributed
    return shares


def show_level_end_bonus_screen(state: GameState) -> None:
    """0x4D476 -- end the level: award the treasure bonus, show the tally, then
    (after the hold) load the saved next maze.

    Commits the computed ``level_next``/``maze_next`` and pays every player who
    reached the exit their own bonus -- ``100 x player_activecount x
    player_coincount[p] x player_treascount[p]`` (0x4D516-0x4D5AA, doc/04 §16) --
    then enters the display phase: ``game_mode = TREAS_EXIT`` with ``bonus_timer``
    (the ROM's ``global_ui_delay_timer``, 0x904A4E) counting 300 frames down
    instead of cutting straight to the next level. ``main_treasure_timer`` runs
    the countdown and fires the deferred load (``_finish_level_end``) when it
    expires. This routine writes the settled tally into alpha VRAM before it
    returns; the generic alpha pass displays those words during the hold.

    ``player_coincount`` floors at 1 because every player who joins through the
    real path is credited one coin (``player_coindrop`` 0x48962) whether the
    cabinet is on free play or not; the floor only matters for a hero placed
    directly by a test or the dev runner. ``bonus_amount`` is the total shown on
    the screen; 0 treasures yields 0 (a "NO BONUS" screen).

    Robust to a ROM-less environment -- the deferred load leaves the old maze
    intact if the next one cannot be decoded.

    Leaving a treasure room plays the treasure-music fade (0x41) rather than the
    theme fade, matching the ``mazenum_current >= 115`` split at 0x4D496.

    Leaving a **secret** room takes the other tally entirely (0x4D720-0x4D8A0):
    ``secret_check_winner`` decides whether the challenge task was completed,
    only ``secret_winner`` is paid -- ``5000 x player_coincount`` -- and the
    inventory stashed on the way in is handed back. The position is committed
    last (0x4D8E2/0x4D8EC), so every branch above still sees the maze that was
    just played, and ``secret_check`` (0x4D8DC) adapts how soon the next secret
    room may be offered.
    """
    from .players import setup_infopanel

    was_secret_room = in_secret_room(state)          # 0x4D496, before the commit
    secret_player = state.secret_winner if was_secret_room else -1
    ordinary_rows: dict[int, tuple[int, int, int, int]] = {}
    challenge_completed = secret_check_winner(state) if was_secret_room else False  # 0x4D4B0

    sound_play(state, 0x39)                          # 0x4D48A slow-motion silencer
    if not was_secret_room:
        sound_play(state, 0x41)                      # 0x4D4A2 treasure-music fade
    else:
        sound_play(state, 0x3C)                      # 0x4D4BA theme fade

    state.treasure_timer = 0
    state.treasure_voice_set = 0
    # 0x4D4D6 parks the announcement delay on -1: no countdown speech can fire
    # while the tally is up. Entering the next treasure room re-zeroes it.
    state.treasure_announcement_delay = 0xFFFF
    setup_infopanel(state, -1)                       # 0x4D4DE-0x4D4E4
    state.bonus_timer = _BONUS_DISPLAY_FRAMES        # 0x4D50E
    state.game_mode = GameMode.TREAS_EXIT            # display phase (world frozen)

    open_name_entry = False
    if was_secret_room:                              # 0x4D544 -> 0x4D720
        open_name_entry = _secret_room_payout(state, challenge_completed)
        state.secret_need_hint = 0                   # 0x4D8D4
    else:
        players = max(1, _count_active_players(state))   # 0x4D516 player_activecount
        recipients = _bonus_recipients(state)        # 0x4D552/0x4D55E status 2 / 8
        shares = _treasure_shares(state, recipients)

        state.bonus_amount = 0
        for i in recipients:
            player = state.players[i]
            coins = max(1, player.coin_count)        # 0x4D574 player_coincount
            bonus = 100 * players * coins * shares[i]   # 0x4D522/0x4D578/0x4D58E
            ordinary_rows[i] = (100 * players, 100 * players * coins, shares[i], bonus)
            if not bonus:
                continue
            player.score += bonus                    # 0x4D59E
            state.score_dirty[i] = 1                 # 0x4D5AA ori.b #1
            state.bonus_amount += bonus

        secret_check(state)                          # 0x4D8DC

    _write_bonus_alpha(
        state, ordinary_rows=ordinary_rows, secret_player=secret_player,
    )
    if open_name_entry:
        from .players import secret_getname

        secret_getname(state)                        # 0x4D7E0, after tally writes

    # Commit the next position last, exactly as 0x4D8E2/0x4D8EC do (default to
    # level+1 if compute_next_level was not run, e.g. a direct caller).
    state.levelnum_current = state.level_next or (state.levelnum_current + 1)
    if state.maze_next:
        state.mazenum_current = state.maze_next


def _finish_level_end(state: GameState) -> None:
    """Prepare the next maze and level splash when the prior display ends.

    This is the ``main_start_game`` transition tail (0x480F2-0x48156): the
    position is already committed, so run ``show_level_start_screen`` -- which
    may replace the maze with a treasure room -- and load it without placing
    players until the splash's shared UI timer expires.
    """
    from .display import clear_alpha_visible

    clear_alpha_visible(state)
    show_level_start_screen(state)                   # 0x4813A
    state.level_start_pending = _load_next_level(
        state, state.levelnum_current, _exiting_or_here(state),
        spawn_players=False,
    )
    if not state.level_start_pending:
        state.bonus_timer = 0
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
    state.spawn_probability_bonus = (
        state.spawn_probability_bonus + delta
    ) & 0xFF                                                   # 0x48BA6


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

    exit_scan_level(state)                           # maze_new_level_setup exit table
    # player_start_inner clears player_treascount on every spawn (0x48E86); the
    # level total is cleared by load_level.
    state.player_treascount = [0] * len(state.players)
    if not spawn_players:
        return True

    _spawn_level_players(state, survivors)
    return True


def _spawn_level_players(state: GameState, survivors: list[int]) -> None:
    """Run main_start_game's post-splash player placement on the loaded maze."""
    from .players import player_join_finalize, player_start_inner

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
        state.players[i].status = int(PlayerStatus.ALIVE_HERE)
        if player_start_inner(state, i) == -1:       # world spawn (I-08)
            state.secret_tricks_flags[i] = 0         # next-level survivor, 0x48280
            player_join_finalize(state, i)

    # 0x4834E: both handoff arms converge here, with the heroes already back to
    # status 1, so the bonus is computed from the party that is about to play.
    update_monster_spawn_bonus_from_score_per_coin(state)
    from ..maze import maze_addrandompickups
    maze_addrandompickups(state, True)                # 0x48358
    from .thief import thief_setup

    thief_setup(state)                               # 0x4835E
    state.idle_timer = 0                             # 0x4836A
