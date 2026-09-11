"""Secret-objective progress, winner selection, and secret-room entry/payout."""

from __future__ import annotations

from .. import romtext
from ..constants import FIRST_PLAYABLE_SLOT, MazeObjIds, PlayerStatus
from ..state import NUM_PLAYERS, GameState
from .display import write_alpha_decimal, write_alpha_large_text, write_alpha_text
from .level_data import (
    _SECRET_MAZE_FIRST as _SECRET_MAZE_FIRST,
)

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
TRICK_WATCHSHOOT1 = 5       # watch what you shoot (foods)
TRICK_WATCHSHOOT2 = 6       # watch what you shoot (secret walls)
TRICK_SAVESUPERSHOTS = 7
TRICK_NOUSEINVUL = 8
TRICK_NOGETHIT = 9          # dragon progress byte must have low two bits clear
TRICK_NOFOOLED = 11
TRICK_NOGREEDY1 = 12        # 0x0C, no keys or potions (0x514D4, 0x5179C)
TRICK_DIET = 13             # 0x0D, no food (0x51C0C, 0x51CEE)
TRICK_NOGREEDY2 = 14        # 0x0E, no treasure (0x519C2)
TRICK_BEPUSHY = 15
TRICK_IT = 16
TRICK_NOHURTFRIENDS = 17
TRICK_NO_TREASURE = TRICK_NOGREEDY2     # 0x0E, bumped by collecting treasure

# "Save Super Shots" wants eleven banked (0x52BAA).
_SAVESUPERSHOTS_TARGET = 0x0B
# Trick 9 needs a dragon, which the rotation only produces from level 12
# (maze_new_level_setup 0x4394E).
_TRICK_NOGETHIT_MIN_LEVEL = 0x0C

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
_CHALLENGE_TIMER_RANDOM_MINUTES = [6, 4, 6, 4, 6, 4, 6, 4, 6, 5, 5, 9, 4, 5]

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
# Secret rooms (§10.6): the level's trick, who wins it, and the challenge room
# ---------------------------------------------------------------------------

def secret_new_level_setup(state: GameState) -> None:
    """0x43916-0x4395C -- give the freshly loaded maze its secret objective.

    A secret room keeps the challenge it was entered with; an ordinary maze
    clears the objective and the winner, and then takes the maze header's trick
    byte (gex ``Maze.secret``) only when ``secret_possible_counter`` has run
    out. Trick 9 wants a dragon to survive, so it is cancelled below level 12.
    """
    from .level_state import in_secret_room

    if in_secret_room(state):                    # 0x43916
        return
    state.secret_trick_id = TRICK_NONE           # 0x43922
    state.secret_player = -1                     # 0x43928, 0xFF = nobody
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
    level's active objective -- ``cmpi.b #<trick>,secret_trick_id`` then bump the
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
    keeps, and a pass writes the player into ``secret_player`` (0x52C46 copies
    ``current_player``, which inside ``player_exit_sequence`` is this player).
    ``TRICK_IT`` is the odd one out: it decides on the spot whether the exiting
    player is IT and then marks every player, so nobody else can claim it.
    """
    trick = state.secret_trick_id
    flags = state.secret_tricks_flags

    if trick == TRICK_IT:                                        # 0x52B60
        if (state.secret_player < 0                              # 0x52B66
                and state.player_it == player_index              # 0x52B70
                and flags[player_index] != 1):                   # 0x52B7A
            state.secret_player = player_index                   # 0x52B82
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
        state.secret_player = player_index                       # 0x52C46


def secret_check(state: GameState) -> None:
    """0x486FE -- adapt how often a secret room is offered.

    Runs at the end of a level that had an objective: a win records the maze in
    ``secret_prev_maze`` and pushes the reload value up by 15 (capped at 40), a
    miss pulls it down by 2 (floored at 4). ``secret_possible_counter`` then
    reloads, and ``advance_level_countdowns`` walks it down one level at a time.
    """
    if state.secret_trick_id == TRICK_NONE:                      # 0x48708
        return
    if 0 <= state.secret_player < NUM_PLAYERS:                   # 0x48710/0x48718
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
    player = state.secret_player
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
    winner = state.secret_player
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
    duration += state.getrandom(_CHALLENGE_TIMER_RANDOM_MINUTES[index]) * 60   # 0x44E5C
    state.treasure_timer = duration                              # 0x44E80
    state.secret_need_hint = 0                                   # 0x44E86
    state.treasure_announcement_delay = 0
    state.treasure_voice_set = 0
    return True


def _maze_secret_for_hint(state: GameState) -> int:
    """Read the selected maze header byte that level_splash sees at 0x4C084."""
    from ...maze_rom import MazeError, decode_maze

    try:
        return int(decode_maze(state.mazenum_current).secret)
    except MazeError:
        return int(getattr(state.maze, "secret", TRICK_NONE) or TRICK_NONE)


def _write_secret_hint(state: GameState) -> None:
    """0x4C04E-0x4C108 -- consume secret_need_hint into alpha RAM."""
    from .level_state import in_bonus_room

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
    winner = state.secret_player
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

    ``main_start_game`` spawns just ``secret_player`` when the loaded maze is a
    secret room, stashes their keys, potions and super-shots, and zeroes them,
    so the challenge starts from nothing. ``show_level_end_bonus_screen`` adds
    the stash back on the way out.
    """
    from .player_lifecycle import player_start_inner

    winner = state.secret_player
    if not 0 <= winner < NUM_PLAYERS:
        return
    player = state.players[winner]
    player_start_inner(state, winner)                            # 0x482CA
    player.status = int(PlayerStatus.ALIVE_HERE)                 # 0x482D8
    state.monster_spawn_probability_bonus = player.keysnum       # 0x482E6
    state.players[0].keysnum = player.potionsnum                  # 0x482F6
    state.secret_saved_supershot = player.supershot              # 0x48306
    player.keysnum = 0                                           # 0x4831E
    player.potionsnum = 0
    player.supershot = 0
    state.secret_saved_keys = state.monster_spawn_probability_bonus
    state.secret_saved_potions = state.players[0].keysnum
    state.secret_tricks_flags[winner] = 0    # player_start_inner 0x48ED6
    from .player_lifecycle import setup_infopanel

    setup_infopanel(state, winner)


def _secret_room_payout(state: GameState, completed: bool) -> bool:
    """0x4D720-0x4D8A0 -- pay the winner, hand their inventory back, stand down.

    Only ``secret_player`` is considered; a completed task pays
    ``5000 x player_coincount``. Either way the stash is returned, the player is
    put back in the exiting state, and ``secret_player`` is cleared so the next
    level does not walk straight back into another secret room.
    """
    winner = state.secret_player
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
        player.keysnum = (
            player.keysnum + state.monster_spawn_probability_bonus
        ) & 0xFF
        player.potionsnum = (
            player.potionsnum + state.players[0].keysnum
        ) & 0xFF
        player.supershot = (player.supershot + state.secret_saved_supershot) & 0xFF
        from .player_lifecycle import player_inv_update

        player_inv_update(state, winner)
    state.secret_saved_keys = state.monster_spawn_probability_bonus
    state.secret_saved_potions = state.players[0].keysnum
    if not open_name_entry:
        state.secret_player = -1                                 # 0x4D866
    return open_name_entry


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
