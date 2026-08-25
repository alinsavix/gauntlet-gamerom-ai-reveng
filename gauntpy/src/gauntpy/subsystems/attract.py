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

from .. import romtext
from ..constants import GameMode, PlayerStatus
from ..state import GameState
from .display import (
    alpha_word,
    fill_alpha_rect,
    write_alpha_decimal,
    write_alpha_text,
)
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

# logo_motion_program_full/short, ROM 0x5AC2E/0x5AC4E. Each record is
# (duration, ordinary-logo V delta, "II" V delta, playfield V-scroll delta).
_TITLE_MOTION_FULL = (
    (0x90, 2, 0, 0),
    (0x03, -2, 0, 2),
    (0x06, 1, 0, -1),
    (0x01, 0, 0, 0),
    (0xB3, 0, 2, 0),
    (0x03, 0, -2, 2),
    (0x06, 0, 1, -1),
    (0x00, 0, 0, 0),
)
_TITLE_MOTION_SHORT = (
    (0x90, 2, 0, 0),
    (0x01, 0, 0, 0),
    (0xB3, 0, 2, 0),
    (0x00, 0, 0, 0),
)
_TITLE_MOB_FIRST = 0x20
_TITLE_MOB_LAST = 0xBE


def _title_mob_record(
    state: GameState, slot: int, picture: int, hpos: int, vpos: int,
) -> None:
    state.mobs.create(slot, tile=picture, hpos=hpos, vpos=vpos, obj_type=0)


def _init_title_logo_mobs(state: GameState) -> None:
    """Port title_logo_init 0x4DA9A-0x4DCB8 into the four MOB arrays."""
    slot = _TITLE_MOB_FIRST
    picture = 0x2000
    main_vpos = 0x6400
    ii_picture = 0x2700
    ii_vpos = 0x4000

    for row in range(9):
        if row == 6:
            picture = 0x2560
        hpos = 0x0200 + row
        for _ in range(3):
            _title_mob_record(state, slot, picture, hpos, main_vpos + 0x38)
            slot += 1
            picture += 8
            hpos += 0x2000

        if row < 5:
            _title_mob_record(state, slot, picture, hpos, main_vpos + 0x20)
            slot += 1
            picture += 5
            hpos += 0x1400
            for _ in range(12):
                _title_mob_record(state, slot, picture, hpos, main_vpos)
                slot += 1
                picture += 1
                hpos += 0x0400
        else:
            _title_mob_record(state, slot, picture, hpos, main_vpos + 0x10)
            slot += 1
            picture += 3
            hpos += 0x0C00
            _title_mob_record(state, slot, picture, hpos, main_vpos)
            slot += 1

            ii_hpos = 0x6E00 + row
            _title_mob_record(state, slot, ii_picture, ii_hpos, ii_vpos + 0x08)
            slot += 1
            ii_picture += 2
            ii_hpos += 0x0800
            for _ in range(6):
                _title_mob_record(state, slot, ii_picture, ii_hpos, ii_vpos)
                slot += 1
                ii_picture += 1
                ii_hpos += 0x0400

            hpos += 0x2000
            picture += 8
            for _ in range(6):
                _title_mob_record(state, slot, picture, hpos, main_vpos)
                slot += 1
                picture += 1
                hpos += 0x0400

        main_vpos -= 0x0400
        ii_vpos -= 0x0400

    ii_hpos = 0x6E09
    _title_mob_record(state, slot, ii_picture, ii_hpos, ii_vpos + 0x08)
    slot += 1
    ii_picture += 2
    ii_hpos += 0x0800
    for _ in range(6):
        _title_mob_record(state, slot, ii_picture, ii_hpos, ii_vpos)
        slot += 1
        ii_picture += 1
        ii_hpos += 0x0400

    assert slot - 1 == _TITLE_MOB_LAST
    _scroll_title_mobs(state, -1, 0)
    state.logo_motion_index = -1
    state.logo_scroll_timer = 0


def _scroll_title_mobs(
    state: GameState, body_delta: int, ii_delta: int,
) -> bool:
    """Port scroll_apply 0x4D956 for the title's two MOB groups."""
    if body_delta == 0 and ii_delta == 0:
        return False
    for slot in range(_TITLE_MOB_FIRST, _TITLE_MOB_LAST + 1):
        picture = state.mobs.picture[slot] & 0x7FFF
        delta = ii_delta if 0x2700 <= picture < 0x2728 else body_delta
        state.mobs.vpos[slot] = (
            state.mobs.vpos[slot] + (delta << 7)
        ) & 0xFFFF
    return True


def _update_title_logo_motion(state: GameState) -> None:
    program = _TITLE_MOTION_FULL if state.title_logo_full_program else _TITLE_MOTION_SHORT
    while True:
        if state.logo_scroll_timer == 0:
            state.logo_motion_index += 1
            duration, body_delta, ii_delta, scroll_delta = program[
                state.logo_motion_index
            ]
            state.logo_scroll_timer = duration
            if duration == 0:
                state.logo_scroll_timer = -1
            elif scroll_delta:
                state.scroll_y = (state.scroll_y + scroll_delta) & 0x1FF

        if state.logo_scroll_timer <= 0:
            return
        state.logo_scroll_timer -= 1
        duration, body_delta, ii_delta, scroll_delta = program[
            state.logo_motion_index
        ]
        if state.logo_scroll_timer > 0 and scroll_delta:
            state.scroll_y = (state.scroll_y + scroll_delta) & 0x1FF
        if _scroll_title_mobs(state, body_delta, ii_delta):
            return


def _write_legend_alpha(state: GameState) -> None:
    """load_legend_page's opaque 29-column curtain and ROM text page."""
    fill_alpha_rect(state, 0, 0, 29, 30, alpha_word(0x8000))
    page = int(state.attract_legend)
    if page == 1:
        fill_alpha_rect(state, 16, 3, 10, 14, 0)
    if page == 2:
        # draw_legend_rules_page 0x4D088-0x4D0EC reveal windows precede text.
        for column, width, row, height in (
            (0, 5, 2, 5), (0, 5, 10, 9), (0, 5, 22, 7),
            (22, 7, 2, 5), (24, 5, 11, 6), (24, 5, 20, 9),
        ):
            fill_alpha_rect(state, column, row, width, height, 0)
    if page == 2:
        write_alpha_text(state, 8, 0, "LEGEND", 0x8000)
        for text, column, row, attribute in romtext.LEGEND_RULES_TEXT:
            write_alpha_text(state, column, row, text, attribute)
        return
    elif page == 1:
        write_alpha_text(state, 6, 0, "MONSTERS", 0x8000)
        for text, column in (
            ("Type", 1), ("Fight", 12), ("Shoot", 18), ("Magic", 24),
        ):
            write_alpha_text(state, column, 18, text, 0x8000)
        write_alpha_text(state, 1, 3, "Type", 0x8000)
        for index, (name, fight, shoot, magic) in enumerate(
            romtext.LEGEND_MONSTER_ROWS
        ):
            art_row = 4 + index + (1 if index == 9 else 0)
            table_row = 19 + index
            write_alpha_text(state, 0, art_row, name, 0x9000)
            write_alpha_text(state, 0, table_row, name, 0x9000)
            for text, column in ((fight, 15), (shoot, 20), (magic, 25)):
                attribute = romtext.LEGEND_MONSTER_VALUE_ATTRIBUTES[text]
                write_alpha_text(state, column, table_row, text, attribute)
        return
    else:
        records = romtext.LEGEND_CREDITS_TEXT
    for text, column, row in records:
        attribute = 0x8800 if page == 0 and column == 4 else 0x8000
        write_alpha_text(state, column, row, text, attribute)


def _adjust_legend_rules_mobs(state: GameState) -> None:
    """Port draw_legend_rules_page's decorative MOB writes at 0x4CFF8."""
    for slot, picture in (
        (0x24F, 0x09A2), (0x2CF, 0x2728), (0x2D0, 0x272C),
        (0x2EF, 0x2730), (0x2F0, 0x2734), (0x30F, 0x2738),
        (0x310, 0x273C),
    ):
        state.mobs.picture[slot] = picture
    for slot, delta in (
        (0x2C3, 0x0100), (0x2C4, -0x0100), (0x2E3, 0x0200),
        (0x303, 0x0200), (0x323, -0x0100), (0x324, 0x0600),
    ):
        state.mobs.vpos[slot] = (state.mobs.vpos[slot] + delta) & 0xFFFF


def _adjust_legend_monster_mobs(state: GameState) -> None:
    """Port draw_legend_monsters_page's fourteen position adjustments."""
    for array, slot, delta in (
        (state.mobs.hpos, 0x257, -0x0400),
        (state.mobs.vpos, 0x258, -0x0400),
        (state.mobs.hpos, 0x279, 0x0400),
        (state.mobs.hpos, 0x277, -0x0400),
        (state.mobs.vpos, 0x277, -0x0200),
        (state.mobs.vpos, 0x278, -0x0600),
        (state.mobs.hpos, 0x299, 0x0400),
        (state.mobs.vpos, 0x299, -0x0200),
        (state.mobs.hpos, 0x2B7, -0x0400),
        (state.mobs.vpos, 0x2B8, -0x0400),
        (state.mobs.hpos, 0x2D9, 0x0400),
        (state.mobs.vpos, 0x2D9, 0x0100),
        (state.mobs.hpos, 0x2F7, -0x0600),
        (state.mobs.vpos, 0x2F7, -0x0300),
    ):
        array[slot] = (array[slot] + delta) & 0xFFFF


def _load_legend_page(state: GameState) -> None:
    """Port load_legend_page 0x4CD1C, including its maze/palette reload."""
    from .. import maze
    from .players import setup_infopanel

    maze.reset_and_load_level(
        state, state.levelnum_current, maze_number=_LEGEND_MAZE,
    )
    if state.attract_legend == 1 and state.maze is not None:
        maze.initialize_maze_color_ram(state, state.maze, floorcolor=7)
    setup_infopanel(state, -1)
    if state.attract_legend == 2:
        state.scroll_x = 0x2C
        state.scroll_y = 0x108
        _adjust_legend_rules_mobs(state)
    elif state.attract_legend == 1:
        state.scroll_x = 0xE0
        state.scroll_y = 0x100
        _adjust_legend_monster_mobs(state)
    _write_legend_alpha(state)

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

    TITLE delegates the exact nested timer and 0x910204/0x910332 writes to the
    game-owned color-RAM model. ``logo_color_timer`` remains only a diagnostic
    frame count for callers that observed the earlier migration.
    """
    state.logo_color_timer = (state.logo_color_timer + 1) & 0xFFFF
    if int(state.game_mode) == int(GameMode.SCORES):
        if (state.frame_counter & 0x0F) == 0:
            # 0x4DE8C-0x4DEAC preserves the last four words, shifts the
            # preceding twelve, and restores the saved group at the front.
            block = state.alpha_color_ram[144:160]
            state.alpha_color_ram[144:160] = block[-4:] + block[:-4]
    elif int(state.game_mode) == int(GameMode.TITLE):
        from .display import update_title_logo_colors

        update_title_logo_colors(state)
        _update_title_logo_motion(state)


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

    # 0x44984-0x449B6: NORMAL with no live players is the continue screen.
    # The prompt itself contains a four-space hole; once per full second this
    # tail writes the two-digit seconds value into that modeled alpha RAM.
    if (
        mode == int(GameMode.NORMAL)
        and state.levelnum_current != 1
        and state.attract_timer >= 0
        and state.attract_timer % 60 == 0
    ):
        write_alpha_decimal(
            state, 13, 14, state.attract_timer // 60, 2, 0x8000,
        )

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
    state.logo_cycle_timer = 0

    if mode == int(GameMode.LEGEND):               # 0x4486E
        if state.attract_legend == 0:
            state.game_mode = int(GameMode.SCORES)  # 0x4487C
        else:
            # Page on to the next legend screen without restarting the screen
            # (0x44882-0x4489C, and the attract_legend != 2 skip at 0x44904).
            state.attract_legend -= 1
            state.attract_timer = _LOADED_TIMER[int(GameMode.LEGEND)]
            from .players import player_resetall

            player_resetall(state)
            _load_legend_page(state)                # 0x4488C-0x4489C
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
    from .display import clear_attract_display_memory, restore_alpha_color_ram

    clear_attract_display_memory(state)              # 0x44468 / 0x44474
    restore_alpha_color_ram(state)                   # init_display common prefix
    player_resetall(state)                         # 0x4446E
    _sound_play(state, _SOUND_THEME_FADE)          # 0x4447A
    state.attract_timer = _LOADED_TIMER.get(mode, 0x258)

    if mode == int(GameMode.TITLE):
        from .display import (
            init_alpha_color_ram,
            init_fixed_playfield_color_ram,
            init_title_logo_colors,
        )
        from ..maze import (
            load_attract_display_tilemap, load_attract_fixed_palette,
        )

        # attract_display (0x4438E) finishes with init_display(0x10, 0x10),
        # which restores alpha colors but deliberately skips playfield/MOB
        # palettes. The title routine then builds its own MOB display list.
        load_attract_display_tilemap(state)
        init_alpha_color_ram(state, initialize_mobs=False)
        fixed_palette = load_attract_fixed_palette()
        if fixed_palette is not None:
            init_fixed_playfield_color_ram(state, fixed_palette)
        state.attract_count = (state.attract_count + 1) & 0xFFFF   # 0x4448E
        if state.attract_count >= _TITLE_SETTINGS_REFRESH_CYCLE:   # 0x44498
            state.attract_count = 0
            _refresh_operator_settings(state)          # 0x444A4-0x444C2
        state.title_logo_full_program = state.title_intro_state == 0
        init_title_logo_colors(state)               # title_logo_init 0x444D2
        _init_title_logo_mobs(state)
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
        state.attract_legend = 2
        _load_legend_page(state)                    # 0x44536-0x44552
    elif mode == int(GameMode.SCORES):
        from .. import maze
        from .score import write_high_score_screen

        maze.reset_and_load_level(
            state, state.levelnum_current, maze_number=_LEGEND_MAZE,
        )
        state.scroll_x = 9
        state.scroll_y = 5
        write_high_score_screen(state)              # attract_highscores 0x4450C


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
        from .exits import update_monster_spawn_bonus_from_score_per_coin

        update_monster_spawn_bonus_from_score_per_coin(state)
        maze.maze_addrandompickups(state, False)         # 0x48590


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
            from .players import player_resetall

            player_resetall(state)
            _load_legend_page(state)
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
