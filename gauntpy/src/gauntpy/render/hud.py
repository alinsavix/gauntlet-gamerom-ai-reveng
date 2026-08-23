"""Alpha-layer compatibility entry points and host-only HUD overlays."""

from __future__ import annotations

from ..state import GameState
from ..subsystems import score
from .alpha import draw_alpha_layer
from .text import GLYPH_W

__all__ = [
    "draw_hud", "draw_message_box", "draw_debug_frame_counter",
    "CELL", "cell_xy",
]

CELL = GLYPH_W


def cell_xy(panel: tuple[int, int, int, int], column: int, row: int) -> tuple[int, int]:
    """Framebuffer pixel for an absolute alpha cell inside the panel clip."""
    px, py, _pw, _ph = panel
    return px + (column - score.PANEL_COLUMN) * CELL, py + row * CELL


def draw_hud(fb, state: GameState, panel: tuple[int, int, int, int]) -> None:
    """Compatibility wrapper: render the panel cells from alpha VRAM."""
    draw_alpha_layer(fb, state, clip=panel)


def draw_message_box(fb, state: GameState, viewport: tuple[int, int, int, int]) -> None:
    """Compatibility wrapper: render playfield alpha cells from alpha VRAM."""
    draw_alpha_layer(fb, state, clip=viewport)


def draw_debug_frame_counter(
    fb, state: GameState, panel: tuple[int, int, int, int], *,
    paused: bool = False,
) -> None:
    """Draw host-only diagnostics; these deliberately do not enter alpha VRAM."""
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
