"""Alpha/HUD layer -- the info panel the cabinet draws on its text layer:
level, per-player name, score, health, bonus multiplier and inventory.
PLAN.md §6 WP-2 step 3.

**Layout is the ROM's, not ours.** Every row and column below comes from
``subsystems/score.py``'s panel constants, which were read off the drawing
coordinates in ``setup_infopanel`` (0x452D0), ``draw_player_score`` (0x45940),
``draw_player_health`` (0x459A2) and ``player_inv_update`` (0x45ACA) -- see
that module's docstring. The alpha grid is 8px cells, 42 displayed columns
(``doc/01_hardware.md`` §9), so an alpha (column, row) maps to framebuffer
pixels by multiplying by 8. The panel is columns 29-41: pixels 232-335.

**Content is the ROM's too.** Text comes from ``render/romtext.py``
(transcribed ROM strings and pre-baked HUD word glyph runs) and the *values*
come from the ``InfoPanel`` latch that ``main_score_display`` writes -- so the
HUD shows what the game last drew, on the ROM's one-player-per-four-frames
cadence, rather than sampling live player fields behind the simulation's back.

**The message box is real text now.** ``dialog_first_encounter`` (0x4C440,
implemented in ``subsystems/score.py``) puts the ROM's own message lines on
``state.dialog_message`` and its box geometry on ``dialog_box_width`` /
``dialog_box_rows``; this module draws them, in the owning player's text
palette, for as long as ``dialog_timer`` runs.
"""

from __future__ import annotations

from ..constants import PlayerStatus
from ..state import GameState
from ..subsystems import score
from ..subsystems.display import alpha_color_rgba, alpha_palette_rgba
from . import romtext
from .text import GLYPH_W, draw_glyph_run, draw_text

__all__ = [
    "draw_hud", "draw_message_box", "draw_debug_frame_counter",
    "CELL", "cell_xy",
]

#: One alpha character cell is 8x8 pixels (doc/01_hardware.md §9, §5).
CELL = GLYPH_W

_TEXT_RGBA = (255, 255, 255, 255)
_DIM_RGBA = (128, 128, 136, 255)
_BOX_RGBA = (200, 200, 200, 255)
_PANEL_BG = (0, 0, 0, 255)
def cell_xy(panel: tuple[int, int, int, int], column: int, row: int) -> tuple[int, int]:
    """Framebuffer pixel of alpha cell ``(column, row)``.

    ``panel`` anchors the panel's own first column (``score.PANEL_COLUMN``) at
    ``panel[0]``, so the ROM's absolute alpha columns can be used verbatim even
    if a caller places the panel somewhere else.
    """
    px, py, _pw, _ph = panel
    return px + (column - score.PANEL_COLUMN) * CELL, py + row * CELL


def _player_rgba(
    state: GameState, index: int, attribute: int | None = None,
) -> tuple[int, int, int, int]:
    """Player text color 3 resolved through live alpha color RAM."""
    attr = (
        score.PLAYER_TEXT_PALETTE_WORDS[index & 3]
        if attribute is None else attribute
    )
    return alpha_color_rgba(state, attr, 3)


def _draw_level_header(fb, state: GameState, panel) -> None:
    """``setup_infopanel``'s whole-panel pass: "LEVEL " at row 6 column 0x1F
    and the 3-digit level number at column 0x25."""
    x, y = cell_xy(panel, score.LEVEL_LABEL_COLUMN, score.LEVEL_ROW)
    draw_text(fb.image, x, y, romtext.TEXT_LEVEL, _TEXT_RGBA)
    x, y = cell_xy(panel, score.LEVEL_VALUE_COLUMN, score.LEVEL_ROW)
    draw_text(
        fb.image, x, y,
        score.format_field(state.levelnum_current, score.LEVEL_DIGITS),
        _TEXT_RGBA,
    )


def _draw_inventory(
    fb, state: GameState, panel, index: int, keys: int, potions: int, colour,
) -> None:
    """``player_inv_update`` (0x45ACA): fill up to ``INVENTORY_CELLS`` cells
    with key glyphs, blanks, then potion glyphs -- keys left-aligned, potions
    right-aligned, both clamped to the row."""
    cells = score.INVENTORY_CELLS
    row = index * score.PLAYER_BLOCK_STRIDE + score.PLAYER_INV_ROW
    used = min(max(0, keys), cells)
    x, y = cell_xy(panel, score.INVENTORY_COLUMN, row)
    for i in range(used):
        draw_glyph_run(
            fb.image, x + i * CELL, y, (romtext.GLYPH_KEY,),
            alpha_color_rgba(state, score.KEY_PALETTE_WORDS[index], 3),
            fallback="K",
            palette=alpha_palette_rgba(state, score.KEY_PALETTE_WORDS[index]),
        )

    first_potion = max(used, cells - max(0, potions))
    for i in range(first_potion, cells):
        draw_glyph_run(
            fb.image, x + i * CELL, y, (romtext.GLYPH_POTION,),
            alpha_color_rgba(state, score.POTION_PALETTE_WORDS[index], 3),
            fallback="P",
            palette=alpha_palette_rgba(
                state, score.POTION_PALETTE_WORDS[index],
            ),
        )


def _draw_player_block(fb, state: GameState, panel, index: int) -> None:
    """One player's four-row block, in the ROM's own order: name run, the
    SCORE/HEALTH label run plus the bonus multiplier, the two numeric fields,
    then the inventory row."""
    player = state.players[index]
    field = score.info_panel(state).players[index]
    base = index * score.PLAYER_BLOCK_STRIDE
    player_attr = score.PLAYER_TEXT_PALETTE_WORDS[index]
    player_palette = alpha_palette_rgba(state, player_attr)
    colour = _player_rgba(state, index)

    # Row p*5+7, column 0x23: the pre-baked character-name glyph run.
    klass = int(player.character) & 3
    x, y = cell_xy(panel, score.PLAYER_NAME_COLUMN, base + score.PLAYER_NAME_ROW)
    draw_glyph_run(
        fb.image, x, y, romtext.CHARACTER_HUD_GLYPHS[klass], colour,
        fallback=romtext.CHARACTER_NAMES[klass], palette=player_palette,
    )

    # Row p*5+8, column 0x21: "SCORE" then two blank cells then "HEALTH".
    x, y = cell_xy(panel, score.PLAYER_LABEL_COLUMN, base + score.PLAYER_LABEL_ROW)
    advance = draw_glyph_run(
        fb.image, x, y, romtext.LABEL_SCORE_GLYPHS, _DIM_RGBA, fallback="SCORE",
    )
    draw_glyph_run(
        fb.image, x + advance + 2 * CELL, y, romtext.LABEL_HEALTH_GLYPHS,
        _DIM_RGBA, fallback="HEALTH",
    )
    if state.player_it == index:
        x, y = cell_xy(
            panel, score.IT_LABEL_COLUMN, base + score.PLAYER_LABEL_ROW,
        )
        draw_glyph_run(
            fb.image, x, y, romtext.LABEL_IT_GLYPHS, colour, fallback="IT",
            palette=player_palette,
        )

    # Same row, columns 31-32: the bonus multiplier, only above one.
    if field.bonusmult > 1:
        x, y = cell_xy(panel, score.BONUSMULT_COLUMN, base + score.PLAYER_LABEL_ROW)
        draw_text(
            fb.image, x, y, f"{min(field.bonusmult, 9)}x", colour,
            palette=player_palette,
        )

    # Row p*5+9: the two latched numeric fields.
    x, y = cell_xy(panel, score.SCORE_COLUMN, base + score.PLAYER_VALUE_ROW)
    draw_text(
        fb.image, x, y, score.format_field(field.score, score.SCORE_DIGITS), colour,
        palette=alpha_palette_rgba(state, field.score_attr),
    )
    x, y = cell_xy(panel, score.HEALTH_COLUMN, base + score.PLAYER_VALUE_ROW)
    draw_text(
        fb.image, x, y, score.format_field(field.health, score.HEALTH_DIGITS),
        _player_rgba(state, index, field.health_attr),
        palette=alpha_palette_rgba(state, field.health_attr),
    )

    # Row p*5+10: keys from the left, potions from the right, 12 cells.
    _draw_inventory(
        fb, state, panel, index, player.keysnum, player.potionsnum, colour,
    )


def _draw_player_background(
    fb, state: GameState, panel, index: int,
) -> None:
    """Render setup_infopanel's opaque alpha-RAM space cells."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(fb.image)
    base = index * score.PLAYER_BLOCK_STRIDE
    cells = [
        *(
            (column, base + score.PLAYER_NAME_ROW)
            for column in range(
                score.PLAYER_NAME_COLUMN - 1, score.PLAYER_NAME_COLUMN + 5,
            )
        ),
        *(
            (column, row)
            for row in range(
                base + score.PLAYER_LABEL_ROW,
                base + score.PLAYER_INV_ROW + 1,
            )
            for column in range(
                score.PANEL_COLUMN, score.PANEL_COLUMN + score.PANEL_WIDTH,
            )
        ),
    ]
    for column, row in cells:
        word = state.alpha_ram[row * score.ALPHA_ROW_STRIDE + column]
        if not word & 0x8000:
            continue
        x, y = cell_xy(panel, column, row)
        draw.rectangle(
            [x, y, x + CELL - 1, y + CELL - 1],
            fill=alpha_color_rgba(state, word, 0),
        )


def draw_message_box(fb, state: GameState, viewport: tuple[int, int, int, int]) -> None:
    """Draw the message box over ``viewport`` while ``dialog_timer`` runs.

    ``dialog_position_box`` (0x4CB50) places the real box near its owning
    player or centres it when there is none; without the player's screen
    position available to this layer, the box is centred in the viewport --
    the ROM's own no-owner placement. Everything else is the game's: the lines
    are ``state.dialog_message`` (ROM message records), the box is
    ``dialog_box_rows`` alpha rows tall and ``dialog_box_width`` columns wide,
    and the text uses the owning player's palette word shifted by -0x1000
    exactly as ``dialog_first_encounter`` does (0x4C5B4).
    """
    from PIL import ImageDraw

    if not state.dialog_timer or not state.dialog_message:
        return

    vx, vy, vw, vh = viewport
    rows = max(state.dialog_box_rows, len(state.dialog_message) + 2)
    cols = max(state.dialog_box_width, 1) + 2
    box_w, box_h = cols * CELL, rows * CELL
    if state.dialog_box_column >= 0 and state.dialog_box_row >= 0:
        box_x = vx + state.dialog_box_column * CELL
        box_y = vy + state.dialog_box_row * CELL
    else:
        box_x = vx + max(0, (vw - box_w) // 2)
        box_y = vy + max(0, (vh - box_h) // 2)

    draw = ImageDraw.Draw(fb.image)
    draw.rectangle(
        [box_x, box_y, box_x + box_w - 1, box_y + box_h - 1],
        outline=_BOX_RGBA, fill=_PANEL_BG,
    )

    # -0x1000 on the attribute word is the dim shade; the owning player's
    # colour identifies whose message it is (-1 = nobody, so plain white).
    if 0 <= state.dialog_player < 4:
        attribute = (
            score.PLAYER_TEXT_PALETTE_WORDS[state.dialog_player] - 0x1000
        )
        colour = _player_rgba(state, state.dialog_player, attribute)
    else:
        colour = _DIM_RGBA
    for i, line in enumerate(state.dialog_message):
        draw_text(
            fb.image, box_x + CELL, box_y + (i + 1) * CELL, line, colour,
            palette=(
                alpha_palette_rgba(state, attribute)
                if 0 <= state.dialog_player < 4 else None
            ),
            opaque=0 <= state.dialog_player < 4,
        )


def draw_hud(fb, state: GameState, panel: tuple[int, int, int, int]) -> None:
    """Draw the info panel into ``fb``.

    ``panel`` is ``(x, y, width, height)`` in framebuffer pixels -- where the
    ROM's alpha columns 29-41 land on screen (``compositor.HUD_PANEL``). The
    message box is a separate call (``draw_message_box``) because the real one
    is positioned over the playfield, not inside the panel.
    """
    from PIL import ImageDraw

    px, py, pw, ph = panel
    draw = ImageDraw.Draw(fb.image)
    # setup_infopanel clears the panel block to opaque blanks (tile 0x8000)
    # before drawing; opaque alpha cells are the top display layer
    # (doc/01_hardware.md §4.2), which is what makes the panel a solid strip.
    draw.rectangle([px, py, px + pw - 1, py + ph - 1], fill=_PANEL_BG)

    _draw_level_header(fb, state, panel)

    rows_available = ph // CELL
    for index, player in enumerate(state.players):
        last_row = index * score.PLAYER_BLOCK_STRIDE + score.PLAYER_INV_ROW
        if last_row >= rows_available:
            break
        _draw_player_background(fb, state, panel, index)
        if player.status == PlayerStatus.REMOVED:
            continue
        _draw_player_block(fb, state, panel, index)


def draw_debug_frame_counter(
    fb, state: GameState, panel: tuple[int, int, int, int], *,
    paused: bool = False,
) -> None:
    """Host-only decimal frame counter in the panel's lower-right corner."""
    from PIL import ImageDraw, ImageFont

    px, py, pw, ph = panel
    text = str(state.frame_counter & 0xFFFF)
    draw = ImageDraw.Draw(fb.image)
    font = ImageFont.load_default()
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width, height = right - left, bottom - top
    draw.text(
        (px + pw - width - 2, py + ph - height - 2),
        text, fill=(255, 255, 0, 255), font=font,
    )
    if paused:
        pause_text = "PAUSED"
        left, top, right, bottom = draw.textbbox(
            (0, 0), pause_text, font=font,
        )
        pause_width = right - left
        draw.text(
            (px + pw - pause_width - 2, py + ph - 2 * height - 4),
            pause_text, fill=(255, 80, 80, 255), font=font,
        )
