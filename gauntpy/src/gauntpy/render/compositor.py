"""Assembles the four layers into one framebuffer. PLAN.md §6 WP-2, "keep
the compositor a pure function of GameState + AssetStore -> framebuffer."

**The 336x240 screen split, resolved from the ROM.** This used to be a flagged
guess (240x240 playfield + a 96px strip) because no document gave a pixel
boundary. It does not have to be guessed: the info panel is a block of *opaque
alpha cells* (``doc/01_hardware.md`` §4.2 -- opaque alpha is the top display
layer; §9 -- 8px cells, 42 displayed columns), and ``setup_infopanel``
(0x452D0) says exactly which cells. Its clear loop walks one alpha row as
``a0 += 0x3A`` (29 words), 13 words of blank tile 0x8000, ``a0 += 0x2C`` (22
words) = 64 words, so the panel is **alpha columns 29-41** -- framebuffer
x 232-335, 104px wide. ``draw_player_score`` (0x45940) confirms it from the
other end: its 7-digit field starts at column 0x1D = 29 and
``draw_player_health``'s 5-digit field at column 0x25 = 37 ends on column 41,
the last displayed one. The playfield therefore gets x 0-231 and the panel
x 232-335; ``subsystems/score.py`` holds the alpha-grid constants and
``render/hud.py`` maps them into this rectangle.

**Layer order implements the priority table by construction.** Draw
playfield, then MOBs (transparent/shadow-aware), then HUD (opaque-aware) --
that is exactly ``doc/01_hardware.md`` §4.2's priority list read bottom to
top, so no separate "resolve priority" pass is needed; later draws already
win.
"""

from __future__ import annotations

import dataclasses

from ..constants import GameMode
from ..state import GameState
from ..subsystems import score
from ..subsystems.camera import viewport_scroll
from .framebuffer import Framebuffer
from .hud import draw_debug_frame_counter, draw_hud, draw_message_box
from .mobs import SpriteSource, draw_mob_layer
from .playfield import (
    PlayfieldCache, draw_animated_floor_tiles, draw_exit_animation, draw_playfield,
    draw_transporter_tiles, draw_wall_crumble, playfield_cache_for,
    shadow_source_for,
)
from .screens import draw_front_end_overlay

__all__ = [
    "LOGICAL_WIDTH", "LOGICAL_HEIGHT", "PLAYFIELD_VIEWPORT", "HUD_PANEL",
    "HUD_PANEL_X", "RenderCache", "render_frame",
]

#: doc/01_hardware.md §4, Confidence: Verified.
LOGICAL_WIDTH = 336
LOGICAL_HEIGHT = 240

#: The info panel's first alpha column (``subsystems/score.PANEL_COLUMN``, 29)
#: in framebuffer pixels -- 8px cells, so 232. See the module docstring.
HUD_PANEL_X = score.PANEL_COLUMN * 8

#: (dest_x, dest_y, width, height) in framebuffer pixels -- see the "screen
#: split" derivation above.
PLAYFIELD_VIEWPORT: tuple[int, int, int, int] = (0, 0, HUD_PANEL_X, LOGICAL_HEIGHT)
_HARDWARE_VIEWPORT: tuple[int, int, int, int] = (
    0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT,
)
HUD_PANEL: tuple[int, int, int, int] = (
    HUD_PANEL_X, 0, LOGICAL_WIDTH - HUD_PANEL_X, LOGICAL_HEIGHT,
)


@dataclasses.dataclass
class RenderCache:
    """Cross-frame caches a host loop should hold and pass back in --
    keeping this outside ``GameState`` is what PLAN.md §3 rule 7 requires
    ("rendering reads state; it is never read by state"). Building this
    fresh every call still works (``render_frame`` does that when no cache
    is supplied); passing one back in just avoids re-decoding the maze into
    a fresh 512x512 raster on every one of 60 frames a second.
    """

    playfield: PlayfieldCache | None = None


def render_frame(
    state: GameState,
    assets: SpriteSource,
    *,
    cache: RenderCache | None = None,
    width: int = LOGICAL_WIDTH,
    height: int = LOGICAL_HEIGHT,
    paused: bool = False,
) -> tuple[Framebuffer, RenderCache]:
    """Composite one frame: playfield, then MOBs, then HUD.

    Pure with respect to ``state``/``assets``: for the same state, the same
    assets, and no reused cache, the output is the same framebuffer every
    time. ``cache`` is purely a performance seam (a rebuilt-from-nothing
    cache produces identical output to a reused, up-to-date one) -- see
    ``RenderCache``.

    Returns ``(framebuffer, cache)`` so a caller can hold the returned cache
    and pass it back on the next call.
    """
    cache = cache or RenderCache()
    fb = Framebuffer(width, height)

    # The camera stores the ROM's hardware scroll registers; the renderer wants
    # a plain viewport top-left. Convert once, here (I-23), so every layer sees
    # the same world-pixel corner.
    scroll_x, scroll_y = viewport_scroll(
        state, PLAYFIELD_VIEWPORT[2], PLAYFIELD_VIEWPORT[3],
    )

    shadow_src = None
    if state.maze is not None:
        cache.playfield = playfield_cache_for(state.maze, cache.playfield)
        draw_playfield(fb, cache.playfield, scroll_x, scroll_y, _HARDWARE_VIEWPORT)
        draw_animated_floor_tiles(
            fb, cache.playfield, state, scroll_x, scroll_y, _HARDWARE_VIEWPORT
        )
        # The moving exit is a playfield stamp (main_exit_move -> pf_stamp_update),
        # not a MOB, and it changes every fourth frame -- so it goes on top of the
        # cached raster rather than into it. Crumbling walls are the same shape of
        # problem: wall_crumble restamps them as they take damage.
        draw_exit_animation(
            fb, cache.playfield, state, scroll_x, scroll_y, _HARDWARE_VIEWPORT
        )
        draw_transporter_tiles(
            fb, cache.playfield, state, scroll_x, scroll_y, _HARDWARE_VIEWPORT
        )
        draw_wall_crumble(
            fb, cache.playfield, state, scroll_x, scroll_y, _HARDWARE_VIEWPORT
        )
        # Exact MOB shadows: the shadow-palette twin of the playfield the MOB
        # layer draws over (see playfield.build_playfield_images). Without a
        # maze there is nothing to shadow, so the MOB layer falls back to its
        # in-place darkening.
        shadow_src = shadow_source_for(
            cache.playfield, scroll_x, scroll_y, _HARDWARE_VIEWPORT,
        )

    draw_mob_layer(
        fb, state, assets, scroll_x, scroll_y, _HARDWARE_VIEWPORT,
        shadow_src=shadow_src,
    )

    if int(state.game_mode) != int(GameMode.SCORES):
        draw_hud(fb, state, HUD_PANEL)

    # Front-end screens use the cabinet's full 336x240 raster. This is required
    # by the native 328px title wordmark and also covers the gameplay HUD during
    # attract/select screens. The function remains a no-op during gameplay.
    draw_front_end_overlay(fb, state, (0, 0, width, height), assets)

    # The message box is the alpha layer's topmost element: it sits over the
    # playfield (dialog_position_box, 0x4CB50) and over anything an attract
    # screen drew, so it goes last.
    draw_message_box(fb, state, PLAYFIELD_VIEWPORT)
    draw_debug_frame_counter(fb, state, HUD_PANEL, paused=paused)

    return fb, cache
