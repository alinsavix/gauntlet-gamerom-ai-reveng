"""Front-end screen overlays: title, high scores, legend, and character
select. PLAN.md §6 WP-2 (the attract/select presentation).

Text is drawn with the **ROM alpha font** (``render/text.py`` over
``gex.alphafont``, the real ``136043-1104.6p`` glyphs), the same 8px characters
the cabinet's text layer uses; the module falls back to PIL only when the ROM
is absent. The 328x48 title wordmark is likewise reconstructed at runtime from
the user's graphics ROMs via ``AssetStore.title_logo``.

**The copy is the ROM's.** Every string on these screens comes from
``render/romtext.py``'s transcriptions -- " INSERT COIN " (0x57556),
" PRESS START " (0x5752C), the ``character_select_instruction_chain``
(0x57072), "SCORE PER COIN" and the WARRIORS/VALKYRIES/WIZARDS/ELVES quadrant
headers (0x57FFA-0x58053), the bonus-screen strings (0x5AB1A) and the gameplay
tips (0x5999C) -- and the high-score ladder comes from
``subsystems/score.high_scores``, which seeds itself from the ROM's own
``factory_highscore_records`` (0x57EBA) exactly as ``highscore_table_init``
(0x49BD0) does on a cabinet whose high-score banks are empty. Where the ROM
also gives a screen position (the descriptor blocks), the position is used.

The overlay draws only during a **front-end phase** -- an attract screen
(``game_mode < 0``) or the pre-game character select (a player is SELECTING and
none is ALIVE_HERE yet). During ordinary gameplay it is a no-op, so the world
renders untouched.
"""

from __future__ import annotations

from typing import Protocol

from PIL import Image

from ..constants import GameMode, PlayerStatus
from ..state import GameState
from ..subsystems import score
from . import romtext
from .text import GLYPH_H, GLYPH_W, draw_text, draw_text_centered

__all__ = ["TitleLogoSource", "draw_front_end_overlay"]

_WHITE = (255, 255, 255, 255)
_DIM = (150, 150, 160, 255)
_GOLD = (240, 205, 90, 255)
_ACCENT = (120, 180, 255, 255)
_BLACK = (0, 0, 0, 255)

# ROM records at 0x5AC2E and 0x5AC4E. Their signed deltas all act on the
# hardware's vertical axis; the second delta moves only the separate 0x2700
# anchor group, retained here because it controls same-frame record advances.
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
_TITLE_TIMER_START = 0x5DD


class TitleLogoSource(Protocol):
    def title_logo(self) -> Image.Image: ...


def _cell(viewport, column: int, row: int) -> tuple[int, int]:
    """Framebuffer pixel of alpha cell ``(column, row)`` inside ``viewport``.

    The front-end screens use the cabinet's whole 42x30 alpha grid (8px cells,
    doc/01_hardware.md §9), so ROM descriptor coordinates map straight through.
    """
    vx, vy, _vw, _vh = viewport
    return vx + column * GLYPH_W, vy + row * GLYPH_H


def _fill(fb, viewport: tuple[int, int, int, int]) -> None:
    from PIL import ImageDraw

    vx, vy, vw, vh = viewport
    ImageDraw.Draw(fb.image).rectangle(
        [vx, vy, vx + vw - 1, vy + vh - 1], fill=_BLACK
    )


def draw_front_end_overlay(
    fb,
    state: GameState,
    viewport: tuple[int, int, int, int],
    assets: TitleLogoSource,
) -> None:
    """Draw the front-end screen for the current mode over ``viewport``.

    A no-op during ordinary gameplay. ``viewport`` is ``(x, y, w, h)`` in
    framebuffer pixels.
    """
    mode = int(state.game_mode)
    selecting = any(p.status == int(PlayerStatus.SELECTING) for p in state.players)
    playing = any(p.status == int(PlayerStatus.ALIVE_HERE) for p in state.players)
    is_bonus = mode == int(GameMode.TREAS_EXIT)

    # The bonus screen (TREAS_EXIT) and pre-game character select run in a
    # non-negative mode; every other overlay is an attract screen. Ordinary
    # gameplay draws nothing.
    if mode >= 0 and not is_bonus and not (selecting and not playing):
        return

    vx, vy, vw, vh = viewport
    cx = vx + vw / 2

    if selecting and not playing:
        _draw_char_select(fb, state, viewport, cx)
    elif is_bonus:
        _fill(fb, viewport)
        _draw_bonus(fb, state, viewport, cx)
    elif mode == int(GameMode.TITLE):
        _fill(fb, viewport)
        _draw_title(fb, state, assets, viewport, cx)
    elif mode == int(GameMode.SCORES):
        _fill(fb, viewport)
        _draw_scores(fb, state, viewport, cx)
    elif mode == int(GameMode.LEGEND):
        _fill(fb, viewport)
        _draw_legend(fb, state, viewport, cx)
    elif mode == int(GameMode.DEMO):
        # The DEMO screen is the live maze and info panel. Its 0xFF stream
        # records are rendered through the ordinary message-box layer.
        return


def _title_logo_y(state: GameState) -> int:
    """Interpret the ROM motion records and return the wordmark's screen Y.

    ``attract_timer`` (0x904B7C) is a **signed** word everywhere the game
    tests it -- ``main_attract`` gates on ``tst.w``/``blt``, which is why
    0xFFFF is its "disabled" sentinel rather than a 65535-frame countdown. Read
    it the same way here, so an idle attract machine parks the wordmark at its
    settled position instead of rewinding it to the off-screen start of a
    motion program that is not running.
    """
    timer_signed = state.attract_timer & 0xFFFF
    if timer_signed >= 0x8000:
        timer_signed -= 0x10000
    if timer_signed <= 0:
        return 17

    frame = max(0, _TITLE_TIMER_START - timer_signed)
    program = (
        _TITLE_MOTION_FULL
        if state.title_logo_full_program
        else _TITLE_MOTION_SHORT
    )
    record_index = -1
    timer = 0
    body_delta_sum = 0
    scroll_delta_sum = 0

    for _ in range(frame):
        while True:
            if timer == 0:
                record_index += 1
                timer, body_delta, anchor_delta, scroll_delta = program[
                    record_index
                ]
                if timer == 0:
                    return 17
                scroll_delta_sum += scroll_delta

            timer -= 1
            if timer > 0:
                scroll_delta_sum += scroll_delta
            body_delta_sum += body_delta

            # scroll_apply returns -1 for a zero/zero object delta, which makes
            # the updater load the next record during this same display frame.
            if body_delta != 0 or anchor_delta != 0:
                break

    raw_y = (-207 - body_delta_sum - scroll_delta_sum) & 0x1FF
    return raw_y - 512 if raw_y >= 240 else raw_y


def _draw_title(
    fb, state: GameState, assets: TitleLogoSource, viewport, cx
) -> None:
    vx, vy, vw, vh = viewport
    animated_logo = getattr(assets, "title_logo_for_frame", None)
    logo = (
        animated_logo(state.logo_color_timer)
        if animated_logo is not None
        else assets.title_logo()
    )
    logo_x = round(cx - logo.width / 2)
    fb.image.paste(logo, (logo_x, vy + _title_logo_y(state)), logo)
    # ROM strings 0x57556 / 0x5752C (their padding is for the cabinet's own
    # fixed-width fields; this screen centres them itself).
    draw_text_centered(
        fb.image, cx, vy + 124, romtext.TEXT_INSERT_COIN.strip(), _WHITE
    )
    draw_text_centered(
        fb.image, cx, vy + 142, romtext.TEXT_PRESS_START.strip(), _DIM
    )
    draw_text_centered(fb.image, cx, vy + vh - 26, romtext.TEXT_ATARI_GAMES, _DIM)
    draw_text_centered(fb.image, cx, vy + vh - 14, romtext.TEXT_COPYRIGHT, _DIM)


def _draw_scores(fb, state: GameState, viewport, cx) -> None:
    """``attract_highscores`` (0x4A124) -- the four-way-split score-per-coin
    screen, at the ROM's own descriptor coordinates (0x57FFA)."""
    ladders = score.high_scores(state)

    col, row = romtext.TEXT_SCORE_PER_COIN_POS
    x, y = _cell(viewport, col, row)
    draw_text(fb.image, x, y, romtext.TEXT_SCORE_PER_COIN, _ACCENT)

    for klass, column, header_row in romtext.HIGHSCORE_QUADRANTS:
        x, y = _cell(viewport, column, header_row)
        draw_text(fb.image, x, y, romtext.CHARACTER_NAME_PLURALS[klass], _GOLD)
        for rank, (value, initials) in enumerate(ladders[klass][:score.HIGHSCORE_RANKS]):
            ex, ey = _cell(viewport, column, header_row + 1 + rank)
            draw_text(fb.image, ex, ey, f"{initials} {value:>6d}", _WHITE)


def _draw_legend(fb, state: GameState, viewport, cx) -> None:
    """``load_legend_page`` (0x4CD1C) draws one of three explanatory pages over
    maze 103. gauntpy has no legend artwork pipeline, so it draws the page's
    *text*: the four ROM character names plus a page of the ROM's own gameplay
    tips (0x5999C), selected by ``attract_legend`` -- the same sub-screen
    counter the ROM dispatches on (§6.4).
    """
    vx, vy, vw, vh = viewport
    for i, label in enumerate(romtext.CHARACTER_NAMES):
        draw_text_centered(fb.image, cx, vy + 20 + i * (GLYPH_H + 4), label, _ACCENT)

    tips = romtext.GAMEPLAY_TIPS
    page = max(0, int(state.attract_legend)) % len(tips)
    y = vy + 20 + 4 * (GLYPH_H + 4) + 12
    for offset in range(3):
        for line in tips[(page + offset) % len(tips)]:
            if line:
                draw_text_centered(fb.image, cx, y, line, _WHITE)
                y += GLYPH_H + 2
        y += 4


def _draw_bonus(fb, state, viewport, cx) -> None:
    """``show_level_end_bonus_screen`` (0x4D476) -- the treasure tally, using
    that routine's own strings (ROM 0x5AB1A-0x5AB63).

    The tally is **per player**: the ROM pays each exiting hero
    ``100 x player_activecount x player_coincount[p] x player_treascount[p]``
    (0x4D516-0x4D5AA), so the screen shows one "TREASURES x N" line per
    recipient, named by that player's ROM colour, over the shared
    "100 x COINS" heading. ``player_treascount`` (0x904A50) is the settled
    per-player count ``exits.py`` awarded from -- not ``level_treasures``,
    which is the level-wide pickup count and includes treasure no player
    claimed.
    """
    vx, vy, vw, vh = viewport
    draw_text_centered(fb.image, cx, vy + 32, romtext.BONUS_100_X_COINS, _GOLD)

    y = vy + 56
    rows = 0
    for index, count in enumerate(state.player_treascount):
        if not count:
            continue
        label = romtext.PLAYER_COLOR_NAMES[index]
        draw_text_centered(
            fb.image, cx, y, f"{label} {romtext.BONUS_TREASURES_X} {count}", _WHITE,
        )
        y += GLYPH_H + 4
        rows += 1
    if not rows:
        draw_text_centered(
            fb.image, cx, y, f"{romtext.BONUS_TREASURES_X} 0", _DIM,
        )
        y += GLYPH_H + 4

    if state.bonus_amount:
        draw_text_centered(fb.image, cx, y + 12, romtext.BONUS_EQUALS, _ACCENT)
        draw_text_centered(fb.image, cx, y + 30, f"{state.bonus_amount}", _WHITE, scale=2)
    else:
        draw_text_centered(fb.image, cx, y + 20, romtext.BONUS_NONE, _DIM)


def _draw_char_select(fb, state, viewport, cx) -> None:
    vx, vy, vw, vh = viewport
    _fill(fb, viewport)
    draw_text_centered(
        fb.image, cx, vy + 14, romtext.TEXT_SELECT_HERO.strip(), _GOLD
    )

    # Which SELECTING players are currently on which class.
    on_class: dict[int, list[int]] = {c: [] for c in range(4)}
    for i, p in enumerate(state.players):
        if p.status == int(PlayerStatus.SELECTING):
            on_class[int(p.character) & 0x03].append(i)

    y = vy + 44
    for c, label in enumerate(romtext.CHARACTER_NAMES):
        picked = on_class[c]
        draw_text_centered(fb.image, cx, y, label, _WHITE if picked else _DIM)
        if picked:
            # The ROM names players by colour (player_color_name_strings,
            # 0x57222), not by "P1".
            tag = " ".join(romtext.PLAYER_COLOR_NAMES[i] for i in picked)
            draw_text_centered(fb.image, cx, y + GLYPH_H + 1, tag, _ACCENT)
        y += 26

    # character_select_instruction_chain (0x57072), at its own ROM cells.
    for text, column, row in romtext.CHARACTER_SELECT_LINES:
        x, ly = _cell(viewport, column, row)
        draw_text(fb.image, x, ly, text, _DIM)
    draw_text_centered(
        fb.image, cx, vy + vh - GLYPH_H - 4, romtext.TEXT_PRESS_START.strip(), _DIM
    )
