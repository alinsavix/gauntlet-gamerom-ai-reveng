"""Display compositor and host shell. PLAN.md §6 WP-2.

Owns no main-loop calls -- rendering happens after ``tick()`` returns, not
inside it (``mainloop.py`` is untouched by this package). The compositor
(``compositor.py``, ``playfield.py``, ``mobs.py``, ``hud.py``,
``framebuffer.py``) is a pure function of ``GameState`` + an asset provider
-> ``Framebuffer`` and never imports pygame, per PLAN.md §3 rule 7 ("the
simulation core imports nothing... Rendering reads state; it is never read
*by* state") and this package's own brief ("make pygame an OPTIONAL
import"). Only ``host.py`` (the pygame window/input/pump) touches pygame,
and only when a ``HostShell`` is actually constructed.

Quick tour:

- ``framebuffer.Framebuffer`` -- the output type: an RGBA raster wrapping a
  ``PIL.Image``, inspectable without pygame, dumpable to PNG for golden
  comparisons.
- ``playfield`` -- layer 1, the maze (floor/walls/doors/forcefields).
- ``mobs`` -- layer 2, every dynamic thing (players, monsters, shots,
  floor items), walked in depth-chain order.
- ``hud`` -- layer 3, the cabinet's info panel (level, per-player name,
  score, health, bonus multiplier, inventory) on the ROM's own alpha-grid
  coordinates, drawing the values ``subsystems/score.py`` latched.
- ``alpha`` -- layer 3, the generic alpha-RAM renderer used by both gameplay
  HUD and front-end screens.
- ``text`` -- alpha character-ROM decoding plus the host-only debug fallback.
- ``compositor.render_frame(state, assets)`` -- assembles all three into one
  ``Framebuffer``; layer 4 (priority/shadowing) falls out of the draw order
  itself (see that module's docstring).
- ``diagnostics`` -- immutable state snapshots and a separate host-only panel;
  never writes modeled game or video memory.
- ``host.HostShell`` -- the pygame window + input + 60Hz pump; supplies
  ``wait_for_vblank``/``present`` so ``mainloop.g2mainloop(state, host)`` can
  drive it directly.
"""

from __future__ import annotations

from .compositor import HUD_PANEL, HUD_PANEL_X, LOGICAL_HEIGHT, LOGICAL_WIDTH, PLAYFIELD_VIEWPORT, RenderCache, render_frame
from .diagnostics import DebugSnapshot, capture_debug_snapshot, render_debug_panel
from .framebuffer import Framebuffer

__all__ = [
    "Framebuffer",
    "RenderCache",
    "render_frame",
    "LOGICAL_WIDTH",
    "LOGICAL_HEIGHT",
    "PLAYFIELD_VIEWPORT",
    "HUD_PANEL",
    "HUD_PANEL_X",
    "DebugSnapshot",
    "capture_debug_snapshot",
    "render_debug_panel",
]
