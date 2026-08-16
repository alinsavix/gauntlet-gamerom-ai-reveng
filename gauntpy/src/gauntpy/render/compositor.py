"""Assembles the four layers into one framebuffer. PLAN.md §6 WP-2, "keep
the compositor a pure function of GameState + AssetStore -> framebuffer."

**Flagged design decision -- the 336x240 screen split.**
``doc/01_hardware.md`` §4 pins the overall resolution (336x240, Verified) and
``book/04_display_system.md`` describes the layout only loosely: "the maze
viewport gets a roughly 240x240 square, with the remaining strip along the
right given over to the score panel." No document gives an exact pixel
boundary. We fix it at playfield 240x240 in the top-left corner and a 96px
(336-240) HUD strip filling the rest of the width at full height -- chosen
because 240x240 divides evenly by both the 16px maze cell and the 8px tile,
and 96px is a plausible score-panel width for 8px-wide alpha characters (12
columns). If a later package finds the real boundary in the ROM (e.g. from
``setup_infopanel``'s drawing coordinates), update
``PLAYFIELD_VIEWPORT``/``HUD_PANEL`` here -- nothing else in this package
depends on the exact split.

**Layer order implements the priority table by construction.** Draw
playfield, then MOBs (transparent/shadow-aware), then HUD (opaque-aware) --
that is exactly ``doc/01_hardware.md`` §4.2's priority list read bottom to
top, so no separate "resolve priority" pass is needed; later draws already
win.
"""

from __future__ import annotations

import dataclasses

from ..state import GameState
from .framebuffer import Framebuffer
from .hud import draw_hud
from .mobs import SpriteSource, draw_mob_layer
from .playfield import PlayfieldCache, draw_playfield, playfield_cache_for, shadow_source_for

__all__ = [
    "LOGICAL_WIDTH", "LOGICAL_HEIGHT", "PLAYFIELD_VIEWPORT", "HUD_PANEL",
    "RenderCache", "render_frame",
]

#: doc/01_hardware.md §4, Confidence: Verified.
LOGICAL_WIDTH = 336
LOGICAL_HEIGHT = 240

#: (dest_x, dest_y, width, height) in framebuffer pixels -- see the "screen
#: split" decision above.
PLAYFIELD_VIEWPORT: tuple[int, int, int, int] = (0, 0, 240, 240)
HUD_PANEL: tuple[int, int, int, int] = (240, 0, LOGICAL_WIDTH - 240, LOGICAL_HEIGHT)


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

    shadow_src = None
    if state.maze is not None:
        cache.playfield = playfield_cache_for(state.maze, cache.playfield)
        draw_playfield(fb, cache.playfield, state.scroll_x, state.scroll_y, PLAYFIELD_VIEWPORT)
        # Exact MOB shadows: the shadow-palette twin of the playfield the MOB
        # layer draws over (see playfield.build_playfield_images). Without a
        # maze there is nothing to shadow, so the MOB layer falls back to its
        # in-place darkening.
        shadow_src = shadow_source_for(cache.playfield, state.scroll_x, state.scroll_y, PLAYFIELD_VIEWPORT)

    draw_mob_layer(
        fb, state, assets, state.scroll_x, state.scroll_y, PLAYFIELD_VIEWPORT,
        shadow_src=shadow_src,
    )

    draw_hud(fb, state, HUD_PANEL)

    return fb, cache
