"""Generic renderer for the cabinet's 42×30 visible alpha layer."""

from __future__ import annotations

from ..state import GameState
from ..subsystems.display import (
    ALPHA_ATTRIBUTE_MASK,
    ALPHA_COLUMNS,
    ALPHA_GLYPH_MASK,
    ALPHA_ROWS,
    ALPHA_VISIBLE_COLUMNS,
    alpha_palette_rgba,
)
from .text import GLYPH_H, GLYPH_W, draw_alpha_glyph

__all__ = ["draw_alpha_layer"]


def draw_alpha_layer(
    fb,
    state: GameState,
    *,
    clip: tuple[int, int, int, int] | None = None,
) -> None:
    """Composite every visible VRAM cell using its live color-RAM palette."""
    image = fb.image
    clip = clip or (0, 0, image.width, image.height)
    clip_x, clip_y, clip_w, clip_h = clip
    clip_right, clip_bottom = clip_x + clip_w, clip_y + clip_h
    palettes: dict[int, tuple[tuple[int, int, int, int], ...]] = {}

    for row in range(min(ALPHA_ROWS, image.height // GLYPH_H)):
        y = row * GLYPH_H
        if y + GLYPH_H <= clip_y or y >= clip_bottom:
            continue
        base = row * ALPHA_COLUMNS
        for column in range(min(ALPHA_VISIBLE_COLUMNS, image.width // GLYPH_W)):
            x = column * GLYPH_W
            if x + GLYPH_W <= clip_x or x >= clip_right:
                continue
            word = state.alpha_ram[base + column] & 0xFFFF
            opaque = bool(word & 0x8000)
            code = word & ALPHA_GLYPH_MASK
            if not opaque and code == 0:
                continue
            attribute = word & ALPHA_ATTRIBUTE_MASK
            palette = palettes.get(attribute)
            if palette is None:
                palette = alpha_palette_rgba(state, attribute)
                palettes[attribute] = palette
            draw_alpha_glyph(image, x, y, code, palette, opaque=opaque)
