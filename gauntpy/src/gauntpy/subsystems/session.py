"""Coins, credits, character select, and session start -- WP-16.

Reference: ``doc/04_game_subsystems.md`` §10.1, §22, §6.4;
``book/07_session_lifecycle.md``.
"""

from __future__ import annotations

from .. import romtext
from ..constants import Character, GameMode, PlayerStatus
from ..state import NUM_PLAYERS, GameState
from .display import (
    clear_alpha_visible, write_alpha_glyphs, write_alpha_large_text,
)
from .players import player_join_finalize, player_start_inner, setup_infopanel

# ---------------------------------------------------------------------------
# Health added per coin for an active player, indexed by game_settings & 0x1F.
# ROM table at 0x57862, 32 words.
# Reference: doc/04_game_subsystems.md §10.1.
# ---------------------------------------------------------------------------
_COIN_HEALTH_TABLE: list[int] = [
    100, 125, 150, 175, 200, 225, 250, 300,
    350, 400, 450, 500, 550, 600, 650, 700,
    750, 800, 850, 900, 950, 1000, 1100, 1200,
    1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000,
]

# Per-player coin-slot sound, ROM longword table at 0x57002: red/blue/yellow/
# green (0x22-0x25 in refs/soundcmds.csv).  Played by player_init_for_coin
# (0x488FE) and by coincheck when an active player re-coins (0x42CB6); both
# index it by *player slot*, not by character, which is what
# doc/05_data_reference.md's "character announcement speech IDs" label misses.
_COIN_SLOT_SOUND: list[int] = [0x22, 0x23, 0x24, 0x25]


def _write_character_select_alpha(state: GameState) -> None:
    """start_attract_to_game's portrait names and ROM instruction chain."""
    clear_alpha_visible(state)
    setup_infopanel(state, -1)
    positions = ((12, 24), (5, 26), (12, 29), (18, 26))  # ROM 0x570B4/0x570B8
    for klass, (column, row) in enumerate(positions):
        write_alpha_glyphs(
            state, column, row, romtext.CHARACTER_HUD_GLYPHS[klass], 0x8000,
        )
    for text, column, row in romtext.CHARACTER_SELECT_LINES:
        write_alpha_large_text(state, column, row, text, 0x8C00)

# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _signed_byte(value: int) -> int:
    """``monster_spawn_probability_bonus`` (0x90405F) is a signed byte."""
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def _signed_long(value: int) -> int:
    """Store a wrapped 68000 longword in the port's signed-health convention."""
    value &= 0xFFFF_FFFF
    return value - 0x1_0000_0000 if value & 0x8000_0000 else value


def _magic_press_edge(state: GameState, player_index: int) -> bool:
    """Return True on a settled Magic press edge.

    0x1C = 0b11100: bits 4-2 are three released frames (1s), bits 1-0 are
    two held frames (0s).  Active low: 1 = not pressed, 0 = pressed.  Matches
    the pattern ``main_start_game`` tests at 0x48402-0x48416 over
    ``debounce_shift_magic`` (0x905F58).
    Reference: doc/04_game_subsystems.md §6.4.
    """
    return (state.debounce_shift_magic[player_index] & 0x1F) == 0x1C


def start_attract_to_game(state: GameState) -> None:
    """0x44204 -- begin a new session, leaving attract for gameplay (§6.4).

    Three callers reach this every frame regardless of the attract lockout: a
    coin arriving during attract (``coincheck`` 0x42BE2), a free-play Magic
    press (``main_start_game`` 0x484B8), and the attract timer expiring in mode
    0 with a player still holding health (``main_attract`` 0x448CE).

    Sets NORMAL and starts a fresh game: score reset and **level 1 (maze 0)
    loaded**, so a player who then commits a character (``main_start_game`` ->
    ``player_start_inner``, I-08) spawns into a real maze. Guarded via
    ``reset_and_load_level`` so a ROM-less environment still makes the mode
    transition (it just has no maze to spawn into).

    ``player_resetall`` (0x4341E) runs here only when the cabinet is leaving
    **DEMO** (0x4424A-0x44254): every other attract screen already reset the
    four slots on the way in (``start_attract_screen`` 0x4446E), and DEMO is the
    one screen that then builds a live hero of its own. That is the ROM's own
    split, and it is what stops a demo Elf's health, inventory and MOB from
    following the coin into the session.

    Also clears the transition machinery the ROM resets here: the theme fade and
    session-start sounds (0x4425A/0x4429A), the bonus/treasure hold
    (``global_ui_delay_timer`` = 0 at 0x44366) and the attract countdown, which
    is parked on its 0xFFFF disabled sentinel at 0x4436C so ``main_attract``
    stops running until a screen loads a timer again.
    """
    from .players import player_resetall
    from .sound import sound_play

    state.dialog_first_encounter_flags = 0   # 0x44244
    if state.game_mode == GameMode.DEMO:     # 0x4424A
        player_resetall(state)               # 0x44254
    sound_play(state, 0x3C)             # 0x4425A theme fade-out
    state.game_mode = GameMode.NORMAL   # 0x44266
    state.levelnum_current = 1          # 0x4426C
    state.mazenum_current = 0           # 0x4420E
    sound_play(state, 0x02)             # 0x4429A session-start sting
    state.bonus_timer = 0               # 0x44366 global_ui_delay_timer
    state.bonus_amount = 0
    state.treasure_timer = 0
    state.level_treasures = 0
    state.player_treascount = [0] * NUM_PLAYERS
    state.welcome_elapsed_frames = 0       # fresh session setup, 0x48692
    state.attract_timer = 0xFFFF        # 0x4436C: the attract machine stands down
    from .. import maze
    from .exits import exit_scan_level
    if maze.reset_and_load_level(state, 1):   # level 1 = maze 0 (I-08 spawn target)
        exit_scan_level(state)                # maze_new_level_setup exit table
    _write_character_select_alpha(state)      # 0x442BC-0x44346


# Free-play / demo starting health, ROM word at 0x578A0 (player_init_for_coin
# 0x488EC and 0x4891C).  With paid pricing the health comes from
# _COIN_HEALTH_TABLE instead.
_FREE_PLAY_START_HEALTH = 0x7D0     # 2000


def configured_start_health(state: GameState) -> int:
    """The full health assigned when a player starts or continues."""
    if not state.two_player_mode:
        return _FREE_PLAY_START_HEALTH
    return _COIN_HEALTH_TABLE[state.game_settings & 0x1F]


def player_init_for_coin(state: GameState, player_index: int) -> None:
    """0x488CA + ``player_coindrop`` (0x4895C) -- credit a player into select.

    Plays that slot's coin-slot sound (0x488FE), sets the starting health --
    the free-play/demo word at 0x578A0, or the coin-health table at 0x57862 under
    paid pricing (0x4890E-0x48946) -- zeroes the score (0x48954), sets
    ``player_coincount`` to **1** (0x48962), which is why the level-end bonus has
    a nonzero coin factor even on free play, resets the low-health cadence word
    (0x4896C), puts the player into SELECTING (0x4899C) and rebuilds its info
    panel (0x489A8).

    The DEMO branch at 0x488E4 takes the free-play health and skips the sound,
    because the demo's joins are scripted rather than paid for.
    """
    from .sound import sound_play

    player = state.players[player_index]
    if state.game_mode == GameMode.DEMO:                        # 0x488DC
        player.health = _FREE_PLAY_START_HEALTH                 # 0x488EC
    else:
        sound_play(state, _COIN_SLOT_SOUND[player_index & 3])   # 0x488FE
        player.health = configured_start_health(state)          # 0x4890E-0x4891C
    player.score = 0                                            # 0x48954
    # A valid ROM lifecycle already ran player_resetcounters before a dead slot
    # can be credited again. Reassert its 1x baseline here so a host-driven
    # fresh session cannot expose stale multiplier state.
    player.bonusmult = 1
    player.coin_count = 1                                       # 0x48962
    player.state_timer = 0xFFFF                                 # 0x4896C
    player.status = PlayerStatus.SELECTING                      # 0x4899C
    state.pending_character[player_index] = int(player.character)
    setup_infopanel(state, player_index)                        # 0x489A8


# ---------------------------------------------------------------------------
# Main-loop calls (WP-16)
# ---------------------------------------------------------------------------

def coincheck(state: GameState) -> None:
    """0x42B6A -- coin detection, credit accounting, and coin-for-health.

    Coins inserted for an already-active player add health from the table at
    0x57862 indexed by ``game_settings & 0x1F``. A coin arriving during attract
    can begin a session at any point -- it consults no lockout threshold.

    Change-detection pattern: compare ``coin_counters`` (0x904FEC) against
    ``last_coin_state`` (0x9049EA).  If they differ, process all 4 player slots.
    Reference: doc/04_game_subsystems.md §10.1.
    """
    if state.coin_counters == state.last_coin_state:
        return

    # Capture the old value before overwriting it, so per-channel deltas are
    # computed correctly (doc §10.1: operand order corrected to new+4-old).
    old = state.last_coin_state
    state.last_coin_state = state.coin_counters

    # 0x42BA4: free play ignores coin effects, but the shadow still tracks the
    # hardware counters so switching pricing modes cannot replay old events.
    if state.two_player_mode == 0:
        return

    from .sound import sound_play

    for i in range(NUM_PLAYERS):
        # Each player channel occupies 2 bits at offset i*2 (0x904FEC layout).
        new_count = (state.coin_counters >> (i * 2)) & 3
        old_count = (old >> (i * 2)) & 3
        if new_count == old_count:
            continue

        # Global attract check (doc §10.1 / §6.4).  The extra DEMO branch
        # exists because demo heroes hold health while the cabinet is idle.
        all_zero_health = all(p.health == 0 for p in state.players)
        if (all_zero_health or state.game_mode == GameMode.DEMO) and state.game_mode < 0:
            # Leave attract and start a fresh game (level 1 loaded). Then fall
            # through so this same coin credits the triggering player below --
            # one coin both begins the session and enters that player into
            # character select, rather than needing a second coin. (game_mode is
            # now NORMAL and every player's health was just reset to 0.)
            start_attract_to_game(state)

        player = state.players[i]
        if player.health > 0:
            # Active player re-coining: top up health from 0x57862 table.
            table_index = state.game_settings & 0x1F
            health_add = _COIN_HEALTH_TABLE[table_index]
            player.health = _signed_long(player.health + health_add)  # 0x42C2C
            player.coin_count += 1                       # 0x42C04
            # 0x42C30: a positive monster_spawn_probability_bonus is walked back
            # one step per extra coin, so paying to stay alive also buys a
            # slightly calmer level -- the counterweight to the bonus
            # update_monster_spawn_bonus_from_score_per_coin adds each level.
            if _signed_byte(state.spawn_probability_bonus) > 0:
                state.spawn_probability_bonus = (
                    state.spawn_probability_bonus - 1
                ) & 0xFF                                 # 0x42C38
            state.player_lowhealth_spoken[i] = 0         # 0x42C46
            state.player_respawn_speech_timer[i] = -1    # 0x42C54
            player.state_timer = 0xFFFF                  # 0x42C64
            state.health_dirty[i] = 1                    # 0x42C72 player_redraw bit 1
            # The whole panel is rebuilt only while the player is still inside
            # their "coins to start" allowance (0x42C88-0x42CA4).
            coins_to_start = ((state.game_settings & 0x300) >> 8) + 1
            if player.coin_count <= coins_to_start:
                setup_infopanel(state, i)                # 0x42CA4
            sound_play(state, _COIN_SLOT_SOUND[i & 3])   # 0x42CB6
        else:
            # New player joining: player_init_for_coin (0x488CA) sets the
            # starting health, credits one coin, and enters character select.
            if state.credits > 0:
                state.credits -= 1
            player_init_for_coin(state, i)


def character_select_input_update(state: GameState) -> None:
    """0x42DF4 -- character selection input. See §22.

    Per-frame handler.  For each player slot with status == SELECTING, reads
    the joystick and updates the tentative character.  Directional bits are
    tested active-low (bit clear = pressed) in priority order:

      bit 7 (0x80) clear → Warrior
      bit 5 (0x20) clear → Valkyrie
      bit 6 (0x40) clear → Wizard
      bit 4 (0x10) clear → Elf

    If the selection changes, ``pending_character`` and ``player.character``
    are updated and the info panel is redrawn.
    Reference: doc/04_game_subsystems.md §22.
    """
    for i in range(NUM_PLAYERS):
        player = state.players[i]
        if player.status != PlayerStatus.SELECTING:
            continue

        # Read joystick from 0x904920[player*2]+1 (low byte of the input word).
        # Switches are active low: a bit that is 0 means the direction is held.
        joy = state.player_input_raw[i]

        # Priority order matches the ROM: bit 7 → up, bit 5 → left,
        # bit 6 → down, bit 4 → right (doc §22).
        if not (joy & 0x80):
            new_char = Character.WARRIOR
        elif not (joy & 0x20):
            new_char = Character.VALKYRIE
        elif not (joy & 0x40):
            new_char = Character.WIZARD
        elif not (joy & 0x10):
            new_char = Character.ELF
        else:
            new_char = state.pending_character[i]  # no direction held: keep current

        if new_char != state.pending_character[i]:
            state.pending_character[i] = new_char
            player.character = new_char
            setup_infopanel(state, i)                    # 0x42E7E


def _cancel_solo_only_trick(state: GameState) -> None:
    """0x48294-0x482B2 -- drop a multiplayer-only secret trick in solo play.

    Tricks 0x0F ("Be Pushy"), 0x10 ("IT Could Be Nice") and 0x11 ("Don't Hurt
    Friends") all need a second hero on the level, so with exactly one player
    active the objective is cleared rather than left unwinnable.
    """
    from .exits import _TRICK_MULTIPLAYER_FIRST, _TRICK_MULTIPLAYER_LAST, TRICK_NONE

    if not _TRICK_MULTIPLAYER_FIRST <= state.secret_trick_id <= _TRICK_MULTIPLAYER_LAST:
        return
    if state.level_players_active == 1:
        state.secret_trick_id = TRICK_NONE


def main_start_game(state: GameState) -> None:
    """0x4800C -- turn a credited player into a hero in the maze.

    The start/join/character-commit press is on the **Magic** line, matching
    ``(debounce_shift_magic & 0x1F) == 0x1C`` at 0x48402-0x48416. It is not
    Fire; that was a documented correction. Use ``input.magic_press_edge``.

    For each player with SELECTING status and a settled Magic press:
      - Commits the pending character.
      - Awards a starting health of 800.
      - Spawns the hero through ``player_start_inner`` (0x48BEC) and finalizes
        the join through ``player_join_finalize`` (0x48A36), so the panel,
        welcome speech and ``level_players_active`` all follow the ROM's path.
      - ``player_start_inner`` applies the first-player class byte at 0x40E66
        to ``monster_spawn_probability_bonus``; it is not a score multiplier.

    In free play (``two_player_mode == 0``) a Magic press while in attract mode
    starts the session (``start_attract_to_game``, 0x484B8) and credits the
    pressing player into character select (``player_init_for_coin``, 0x484BE).
    Reference: doc/04_game_subsystems.md §6.4; PLAN.md §6 WP-16.
    """
    state.welcome_elapsed_frames = (
        state.welcome_elapsed_frames + 1
    ) & 0xFFFF_FFFF                                               # 0x48020

    for i in range(NUM_PLAYERS):
        if not _magic_press_edge(state, i):
            continue

        player = state.players[i]

        if player.status == PlayerStatus.SELECTING:
            from .display import clear_alpha_visible

            initial_selection = not any(
                other.status == PlayerStatus.ALIVE_HERE
                for index, other in enumerate(state.players)
                if index != i
            )
            # Commit character selection and starting health.
            player.character = state.pending_character[i]

            # Full join (I-08): place the hero MOB into the maze when one is
            # loaded, then finalize (ALIVE_HERE + join speech / HUD redraw).
            # player_start_inner returns -1 and counts the player itself when it
            # finds a spawn tile; when there is no maze (attract/character
            # select) it returns 0 without counting, so the join is still
            # finalized here and counted once. Either way the count advances by
            # exactly one -- unifying the two former increment sites (I-R5).
            placed = player_start_inner(state, i)
            player_join_finalize(state, i)
            if placed != -1:
                state.level_players_active += 1
            if initial_selection:
                clear_alpha_visible(state)
                setup_infopanel(state, -1)

            # Tricks 0x0F-0x11 need somebody else to be pushy with, to be IT
            # against, or to avoid hurting, so a solo cabinet cancels them
            # (0x48294-0x482B2).
            _cancel_solo_only_trick(state)

        elif state.game_mode < 0 and state.two_player_mode == 0:
            # Free-play path: Magic press in attract starts the session and
            # credits the pressing player straight into character select
            # (0x484B8 start_attract_to_game, then 0x484BE player_init_for_coin).
            start_attract_to_game(state)
            player_init_for_coin(state, i)
