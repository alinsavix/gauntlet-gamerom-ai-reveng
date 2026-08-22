"""Attract mode, demo playback, and logo colour cycling -- WP-17.

Demo playback is the engine running on recorded inputs: the same
``main_move_players`` path, fed from per-player streams of ``[timer, joystick]``
pairs, with ``0xFF`` = speech and ``0xFE`` = a join record (hi nibble =
character class, lo nibble = slot; §6.2 -- it is *not* an end-of-sequence
marker: a stream ends with an ordinary record whose duration byte is 0).
Demo joystick bytes are active low, like the hardware.

Reference: ``doc/04_game_subsystems.md`` §6 (all), §14.3;
``doc/generated/startup_attract_contracts.csv``; ``book/15_attract_and_demo.md``.

Scope note. The four attract screens' *content* (high-score render, title logo,
legend art) and the palette colour cycling in ``main_logo_updcolors`` are
rendering, owned by WP-2. This module owns the state machine: the real recorded
byte streams (transcribed from ROM 0x5818C+), screen rotation on the documented
timers, the one-second input lockout that gates screen switching, the five
interruption test blocks, and the three expiry outcomes at 0x44860-0x4491A
(legend paging, the ``start_attract_to_game`` hand-off at 0x448CE, and the
``game_mode -= 1`` rotation). Consuming a stream's 0xFE join record is WP-6's
``players._demo_playback``.
"""

from __future__ import annotations

from ..constants import GameMode, PlayerStatus
from ..state import GameState
from .sound import sound_play as _sound_play

# =============================================================================
# Screen timing tables (§6.1, §6.4)
# =============================================================================

# Loaded countdown per attract screen.
_LOADED_TIMER = {
    int(GameMode.SCORES): 0x258,    # ~10 s
    int(GameMode.TITLE): 0x5DD,     # ~25 s
    int(GameMode.DEMO): 0x1C20,     # ~119 s
    int(GameMode.LEGEND): 0x258,    # ~10 s
}

# Input-lockout threshold: exactly 60 frames below the loaded timer.  While the
# timer is above this, screen-switching input is ignored (§6.4).
_INPUT_THRESHOLD = {
    int(GameMode.SCORES): 0x21C,
    int(GameMode.TITLE): 0x5A1,
    int(GameMode.DEMO): 0x1BE4,
    int(GameMode.LEGEND): 0x21C,
}

# Natural rotation order when a screen's timer expires (§6.1).
_NEXT_SCREEN = {
    int(GameMode.SCORES): int(GameMode.TITLE),
    int(GameMode.TITLE): int(GameMode.DEMO),
    int(GameMode.DEMO): int(GameMode.LEGEND),
    int(GameMode.LEGEND): int(GameMode.SCORES),
}

# Sound theme played on the title screen when attract sounds are enabled (§6.1).
_SOUND_TITLE_THEME = 0x3B
# Screen-change sounds every start_attract_screen plays before its per-mode
# setup: 0x01 at 0x4444E and the theme fade-out 0x3C at 0x4447A.
_SOUND_SCREEN_CHANGE = 0x01
_SOUND_THEME_FADE = 0x3C
# game_settings bit 14 -- the operator "Music/attract sound enable" option
# (doc/05_data_reference.md §1.10).  start_attract_screen masks it with
# ``andi.l #0x4000,d0`` at 0x444DA-0x444E6 and only then plays the title theme.
_SETTINGS_ATTRACT_SOUND = 0x4000
# Every 13th TITLE setup re-reads the operator settings from EEPROM
# (0x4448E-0x444C2); ``attract_count`` (0x904B60) is that cycle counter.
_TITLE_SETTINGS_REFRESH_CYCLE = 0xD

# start_attract_screen resets the level/maze counters before its per-mode setup
# so every attract screen starts from a known position (0x4445A-0x44462).
_ATTRACT_LEVEL = 1
_ATTRACT_MAZE = 0

# Demo level maze numbers (§6.1).
_DEMO_MAZE = 102
_LEGEND_MAZE = 103

# Recorded demo input streams, transcribed from ROM (row76.bin).  Each is a
# flat list of bytes read as [timer, joystick] pairs, with 0xFF = speech marker
# and 0xFE = join record (hi nibble = character class, lo nibble = slot).  The
# initial pointer table at 0x58098 is {0x5818C, 0x581C4, 0x5825A, 0x5825C}.
# Player 1's stream (0x581C4) is the active Elf run in standard attract (§6.2).
_DEMO_STREAM_P0 = [  # ROM 0x5818C, 56 bytes
    1, 243, 11, 115, 11, 227, 41, 243, 44, 227, 90, 243, 88, 227, 44, 115,
    22, 227, 255, 8, 139, 243, 44, 179, 47, 243, 112, 227, 58, 115, 22, 211,
    6, 179, 255, 11, 22, 211, 14, 179, 12, 243, 180, 243, 139, 115, 224, 243,
    22, 211, 44, 83, 55, 115, 0, 243,
]
_DEMO_STREAM_P1 = [  # ROM 0x581C4, 150 bytes -- active Elf stream
    1, 243, 255, 0, 8, 179, 255, 1, 144, 179, 40, 227, 16, 211, 8, 179,
    14, 147, 255, 2, 3, 147, 45, 243, 8, 147, 16, 227, 255, 3, 8, 227,
    8, 115, 16, 227, 8, 163, 16, 227, 48, 115, 6, 209, 30, 243, 12, 209,
    255, 4, 24, 211, 24, 115, 20, 211, 20, 115, 1, 227, 255, 5, 6, 225,
    30, 243, 63, 227, 24, 179, 60, 243, 88, 179, 50, 211, 20, 179, 60, 243,
    9, 179, 240, 243, 44, 243, 255, 6, 67, 179, 66, 243, 6, 113, 78, 243,
    6, 177, 86, 243, 6, 113, 30, 243, 16, 179, 1, 211, 1, 227, 255, 7,
    254, 32, 254, 3, 65, 243, 131, 243, 96, 227, 244, 243, 80, 227, 8, 115,
    24, 227, 32, 115, 16, 211, 121, 243, 212, 243, 104, 115, 255, 10, 240, 243,
    1, 242, 72, 83, 0, 243,
]
_DEMO_STREAM_P2 = [0, 243]  # ROM 0x5825A, 2 bytes (parking record)
_DEMO_STREAM_P3 = [  # ROM 0x5825C, 48 bytes
    1, 243, 11, 179, 22, 227, 30, 243, 44, 227, 90, 243, 99, 227, 11, 179,
    59, 227, 116, 243, 52, 113, 120, 243, 33, 115, 34, 243, 64, 227, 42, 115,
    255, 9, 180, 243, 139, 115, 253, 243, 3, 243, 88, 83, 33, 211, 0, 243,
]
_DEMO_STREAMS = [_DEMO_STREAM_P0, _DEMO_STREAM_P1, _DEMO_STREAM_P2, _DEMO_STREAM_P3]
# Standard attract runs player 1 (the Elf); character class 3 = Elf.
_DEMO_ACTIVE_PLAYER = 1
_DEMO_ELF_CLASS = 3

# Raw-input bit masks (active low; §6.2, §6.4).
_FIRE_BIT = 0x02
_MAGIC_BIT = 0x01
_DIRECTION_BITS = 0xF0


# =============================================================================
# main_logo_updcolors (0x4DCBA)
# =============================================================================

def main_logo_updcolors(state: GameState) -> None:
    """0x4DCBA -- palette-driven colour animation and title logo effects.

    The palette RAM writes themselves are rendering (WP-2); here the cadence
    counter advances so timing-dependent callers stay in step.  On the SCORES
    screen the rainbow shifts every 16th frame; on TITLE the logo pulse runs on
    its own inner/outer timers (§14.3).
    """
    state.logo_color_timer = (state.logo_color_timer + 1) & 0xFFFF
    # Colour-cycle work (palette RAM) is deferred to WP-2; nothing the
    # simulation reads changes here.


# =============================================================================
# main_attract (0x44562)
# =============================================================================

def _signed_word(value: int) -> int:
    """Read a GameState counter the way the ROM reads its 16-bit RAM word.

    ``attract_timer`` (0x904B7C) is tested with ``tst.w``/``blt``, so the
    disabled sentinel ``0xFFFF`` that ``start_attract_to_game`` writes at
    0x4436C has to compare as -1, not 65535.
    """
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _select_phase_idle(state: GameState) -> bool:
    """0x4457C-0x445CE -- in NORMAL, is every player either out or selecting?

    The attract machine keeps running in ``game_mode`` 0 while the cabinet sits
    on the character-select screen: each player's status must be REMOVED (0) or
    SELECTING (0x10), otherwise somebody is actually playing and the machine is
    idle.
    """
    return all(
        p.status in (int(PlayerStatus.REMOVED), int(PlayerStatus.SELECTING))
        for p in state.players
    )


def main_attract(state: GameState) -> None:
    """0x44562 -- the attract state machine (§6).

    Runs in the four attract screens and, per 0x4457C-0x445CE, in NORMAL while
    every player is still out or selecting.  It decrements the current screen
    timer (unless the 0xFFFF "disabled" sentinel is loaded), honours the
    one-second input lockout, restarts a screen on any interruption test, and on
    expiry either pages the legend, starts a session, or rotates to the next
    screen.
    """
    if state.game_mode > 0:
        return   # gameplay proper: the attract machine is idle (0x44576)

    mode = int(state.game_mode)
    if mode != int(GameMode.NORMAL) and mode not in _LOADED_TIMER:
        return
    if mode == int(GameMode.NORMAL) and not _select_phase_idle(state):
        return   # somebody is playing (0x445D0)

    if _signed_word(state.attract_timer) < 0:
        return   # disabled sentinel, e.g. straight after start_attract_to_game

    state.attract_timer -= 1                       # 0x445DA

    if mode != int(GameMode.NORMAL):
        threshold = _INPUT_THRESHOLD[mode]
        # The one-second lockout gates screen switching only: interruption tests
        # are armed once the timer drops to the threshold.
        if state.attract_timer <= threshold:
            if _check_attract_interrupt(state, mode):
                return

    if state.attract_timer >= 0:
        return                     # 0x44860 ``tst.w (a0); bge`` -- not expired yet

    _attract_timer_expired(state, mode)


def _attract_timer_expired(state: GameState, mode: int) -> None:
    """0x44860-0x4491A -- what happens when the screen timer runs out."""
    state.logo_color_timer = 0                     # 0x44866 logo_cycle_timer

    if mode == int(GameMode.LEGEND):               # 0x4486E
        if state.attract_legend == 0:
            state.game_mode = int(GameMode.SCORES)  # 0x4487C
        else:
            # Page on to the next legend screen without restarting the screen
            # (0x44882-0x4489C, and the attract_legend != 2 skip at 0x44904).
            state.attract_legend -= 1
            state.attract_timer = _LOADED_TIMER[int(GameMode.LEGEND)]
            return
    elif mode == int(GameMode.NORMAL):             # 0x448A4
        # The character-select screen timed out. A player still holding health
        # means the cabinet owes them a game, so restart the session rather than
        # falling back into attract (0x448A8-0x448CE).
        if any(p.health for p in state.players):
            from .session import start_attract_to_game
            start_attract_to_game(state)           # 0x448CE
            return
        state.game_mode = int(GameMode.SCORES)     # 0x448D6: game_mode -= 1
    else:
        # Rotation is literally ``subq.w #1,game_mode`` (0x448D6):
        # SCORES -> TITLE -> DEMO -> LEGEND.
        state.game_mode = _NEXT_SCREEN[mode]
        if state.game_mode == int(GameMode.LEGEND):
            from .players import setup_infopanel

            state.attract_legend = 2               # 0x448DE
            setup_infopanel(state, -1)             # 0x448EC-0x448F2

    start_attract_screen(state, int(state.game_mode))   # 0x4490E


def _refresh_operator_settings(state: GameState) -> None:
    """0x444A4-0x444C2 -- re-read the operator configuration every 13th TITLE.

    The ROM calls OS ``read_pricing`` (0x236) into ``two_player_mode`` and OS
    ``read_config_word(0xC)`` (0x1A8) into ``game_settings``, so a change made in
    the operator menu takes effect without a reboot.  ``eeprom_load_settings``
    is the same restore on this side; a missing file leaves the live values
    alone, which is the factory-default case.
    """
    from .eeprom import eeprom_load_settings

    eeprom_load_settings(state)


def start_attract_screen(state: GameState, mode: int) -> None:
    """0x44414 -- switch to an attract screen and load its timer (§6.1).

    Every screen change plays the change sound 0x01 and the theme fade 0x3C,
    resets the position counters to level 1 / maze 0 (0x4444E-0x4447A), and runs
    ``player_resetall`` (0x4446E) so a session that ended deep in the rotation
    cannot leak its heroes' inventory, powers, timers or status into the attract
    screens.  TITLE additionally counts screens: every 13th one would re-read the
    operator settings from EEPROM (0x4448E-0x444C2, WP-19's job) and, when
    settings bit 14 (attract sound) is set, plays the Gauntlet II theme.

    Per-screen *rendering* (high-score page, title logo, legend art) is WP-2's.
    """
    state.game_mode = mode
    _sound_play(state, _SOUND_SCREEN_CHANGE)       # 0x4444E
    state.levelnum_current = _ATTRACT_LEVEL        # 0x4445A
    state.mazenum_current = _ATTRACT_MAZE          # 0x44462

    from .players import player_resetall

    player_resetall(state)                         # 0x4446E
    _sound_play(state, _SOUND_THEME_FADE)          # 0x4447A
    state.attract_timer = _LOADED_TIMER.get(mode, 0x258)

    if mode == int(GameMode.TITLE):
        state.attract_count = (state.attract_count + 1) & 0xFFFF   # 0x4448E
        if state.attract_count >= _TITLE_SETTINGS_REFRESH_CYCLE:   # 0x44498
            state.attract_count = 0
            _refresh_operator_settings(state)          # 0x444A4-0x444C2
        state.title_logo_full_program = state.title_intro_state == 0
        if (
            state.game_settings & _SETTINGS_ATTRACT_SOUND
            and state.title_intro_state == 0
        ):
            _sound_play(state, _SOUND_TITLE_THEME)
            state.title_intro_state = 2
        else:
            state.title_intro_state = (state.title_intro_state - 1) & 0xFFFF
    elif mode == int(GameMode.DEMO):
        attract_demo_init(state)
    elif mode == int(GameMode.LEGEND):
        from .players import setup_infopanel

        state.attract_legend = 2
        setup_infopanel(state, -1)                 # 0x4453C-0x44542


def attract_demo_init(state: GameState) -> None:
    """0x449D4 -- set up demo playback on the demo level (§6.3).

    Loads the demo maze (its walls, monsters, generators, and items), resets the
    frame counter, installs the recorded input streams (transcribed from ROM
    0x5818C+), and drops the scripted player 1 Elf in at the maze's PLAYERSTART.
    ``main_move_players`` then drives the demo through the identical input path
    the hardware would use, so the DEMO attract screen shows a real world with a
    hero moving through it.

    The 0xFE join records inside the streams (``FE 20`` = slot 0 as Wizard,
    ``FE 03`` = slot 3 as Warrior, both at ROM 0x58234/0x58236) are consumed by
    ``players._demo_playback``; acting on them -- writing ``player_character``,
    calling ``player_join``, and reloading that slot's pointer from the table at
    0x58098 (0x4A5B2-0x4A5DE) -- is WP-6's side of §6.2.
    """
    state.frame_counter = 0
    state.demo_active_player = _DEMO_ACTIVE_PLAYER
    for i in range(len(state.demo_streams)):
        state.demo_streams[i] = list(_DEMO_STREAMS[i])
        state.demo_stream_pos[i] = 0
        state.demo_timers[i] = 0
    # 0x44A76 -- the demo has no random spawn draw; its generators run off this
    # countdown instead (``monsters.handle_generate``'s negative-game_mode path).
    from .monsters import GENERATOR_RETRY_RELOAD

    state.monster_generation_retry_timer = GENERATOR_RETRY_RELOAD

    from .. import maze
    from .exits import exit_scan_level
    from .players import player_join, setup_infopanel
    from .session import player_init_for_coin

    setup_infopanel(state, -1)                     # 0x449DE-0x449E4
    state.dialog_first_encounter_flags = 0         # 0x449F6

    # Player 1 is the Elf hero driving the standard demo (§6.3).
    elf = state.players[_DEMO_ACTIVE_PLAYER]
    elf.character = _DEMO_ELF_CLASS
    player_init_for_coin(state, _DEMO_ACTIVE_PLAYER)

    # Load the demo maze and place the Elf, so the recorded inputs have a world
    # to move through. Guarded so a ROM-less environment still sets up the demo
    # state (it just has no maze). maze.reset_and_load_level resets the MOB table.
    if maze.reset_and_load_level(state, state.levelnum_current, maze_number=_DEMO_MAZE):
        exit_scan_level(state)
        player_join(state, _DEMO_ACTIVE_PLAYER)


# =============================================================================
# Interruption test blocks (§6.4)
# =============================================================================

def _check_attract_interrupt(state: GameState, mode: int) -> bool:
    """Run the five interruption tests; restart a screen on the first match.

    Each block restarts an *attract screen* -- it does not start a session.
    Entering gameplay is a separate path (``coincheck`` / ``main_start_game``)
    that runs every frame regardless of this lockout (§6.4).
    """
    # Block 1 (positions 1, 2 -- blue/yellow): FIRE/MAGIC -> SCORES.
    if _button_pressed(state, 1) or _button_pressed(state, 2):
        start_attract_screen(state, int(GameMode.SCORES))
        return True

    # Block 2 (positions 0, 3 -- red/green): FIRE/MAGIC -> TITLE.
    if _button_pressed(state, 0) or _button_pressed(state, 3):
        start_attract_screen(state, int(GameMode.TITLE))
        return True

    # Block 3 (positions 0, 3): joystick direction -> DEMO.
    if _direction_pressed(state, 0):
        # A single-player host can only drive position 0. Once DEMO is already
        # selected, treat the same cabinet shortcut as "next" so it reaches the
        # LEGEND screen instead of reinitializing maze 102 forever.
        destination = (
            int(GameMode.LEGEND)
            if mode == int(GameMode.DEMO)
            else int(GameMode.DEMO)
        )
        start_attract_screen(state, destination)
        return True
    if _direction_pressed(state, 3):
        start_attract_screen(state, int(GameMode.DEMO))
        return True

    # Block 5 (positions 1, 2, LEGEND only): joystick direction -> next legend
    # page, or SCORES when the last page has shown.  Checked before block 4 so
    # a direction on the LEGEND screen pages rather than restarting it.
    if mode == int(GameMode.LEGEND) and (
        _direction_pressed(state, 1) or _direction_pressed(state, 2)
    ):
        if state.attract_legend > 0:
            state.attract_legend -= 1
            state.attract_timer = _LOADED_TIMER[int(GameMode.LEGEND)]
        else:
            start_attract_screen(state, int(GameMode.SCORES))
        return True

    # Block 4 (positions 1, 2): joystick direction -> LEGEND, reset counter.
    if _direction_pressed(state, 1) or _direction_pressed(state, 2):
        start_attract_screen(state, int(GameMode.LEGEND))
        return True

    return False


def _button_pressed(state: GameState, position: int) -> bool:
    """FIRE (paid: or MAGIC) held at a raw-input position (active low; §6.4)."""
    raw = state.player_input_raw[position]
    mask = (_FIRE_BIT | _MAGIC_BIT) if state.two_player_mode else _FIRE_BIT
    return (raw & mask) != mask


def _direction_pressed(state: GameState, position: int) -> bool:
    """Any joystick direction held at a raw-input position (active low)."""
    raw = state.player_input_raw[position]
    return (raw & _DIRECTION_BITS) != _DIRECTION_BITS
