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
from . import romtext
from .text import GLYPH_W, draw_glyph_run, draw_text

__all__ = ["draw_hud", "draw_message_box", "CELL", "cell_xy"]

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


def _player_rgba(index: int, *, dim: bool = False) -> tuple[int, int, int, int]:
    """The player's RED/BLUE/YELLOW/GREEN identity colour (romtext), dimmed
    when ``draw_player_health`` shifted the attribute word for the low-health
    pulse or an acid slow."""
    r, g, b, a = romtext.PLAYER_COLOR_RGBA[index & 3]
    if dim:
        return (r // 2, g // 2, b // 2, a)
    return (r, g, b, a)


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


def _draw_inventory(fb, panel, index: int, keys: int, potions: int, colour) -> None:
    """``player_inv_update`` (0x45ACA): fill up to ``INVENTORY_CELLS`` cells
    with key glyphs, blanks, then potion glyphs -- keys left-aligned, potions
    right-aligned, both clamped to the row."""
    cells = score.INVENTORY_CELLS
    row = index * score.PLAYER_BLOCK_STRIDE + score.PLAYER_INV_ROW
    used = min(max(0, keys), cells)
    x, y = cell_xy(panel, score.INVENTORY_COLUMN, row)
    for i in range(used):
        draw_glyph_run(fb.image, x + i * CELL, y, (romtext.GLYPH_KEY,), colour, fallback="K")

    first_potion = max(used, cells - max(0, potions))
    for i in range(first_potion, cells):
        draw_glyph_run(fb.image, x + i * CELL, y, (romtext.GLYPH_POTION,), colour, fallback="P")


def _draw_player_block(fb, state: GameState, panel, index: int) -> None:
    """One player's four-row block, in the ROM's own order: name run, the
    SCORE/HEALTH label run plus the bonus multiplier, the two numeric fields,
    then the inventory row."""
    player = state.players[index]
    field = score.info_panel(state).players[index]
    base = index * score.PLAYER_BLOCK_STRIDE
    colour = _player_rgba(index)

    # Row p*5+7, column 0x23: the pre-baked character-name glyph run.
    klass = int(player.character) & 3
    x, y = cell_xy(panel, score.PLAYER_NAME_COLUMN, base + score.PLAYER_NAME_ROW)
    draw_glyph_run(
        fb.image, x, y, romtext.CHARACTER_HUD_GLYPHS[klass], colour,
        fallback=romtext.CHARACTER_NAMES[klass],
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

    # Same row, columns 31-32: the bonus multiplier, only above one.
    if field.bonusmult > 1:
        x, y = cell_xy(panel, score.BONUSMULT_COLUMN, base + score.PLAYER_LABEL_ROW)
        draw_text(fb.image, x, y, f"{min(field.bonusmult, 9)}x", colour)

    # Row p*5+9: the two latched numeric fields.
    x, y = cell_xy(panel, score.SCORE_COLUMN, base + score.PLAYER_VALUE_ROW)
    draw_text(
        fb.image, x, y, score.format_field(field.score, score.SCORE_DIGITS), colour,
    )
    dim = field.health_attr != score.PLAYER_TEXT_PALETTE_WORDS[index]
    x, y = cell_xy(panel, score.HEALTH_COLUMN, base + score.PLAYER_VALUE_ROW)
    draw_text(
        fb.image, x, y, score.format_field(field.health, score.HEALTH_DIGITS),
        _player_rgba(index, dim=dim),
    )

    # Row p*5+10: keys from the left, potions from the right, 12 cells.
    _draw_inventory(fb, panel, index, player.keysnum, player.potionsnum, colour)


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
        colour = _player_rgba(state.dialog_player, dim=True)
    else:
        colour = _DIM_RGBA
    for i, line in enumerate(state.dialog_message):
        draw_text(fb.image, box_x + CELL, box_y + (i + 1) * CELL, line, colour)


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
        if player.status == PlayerStatus.REMOVED:
            continue
        _draw_player_block(fb, state, panel, index)
