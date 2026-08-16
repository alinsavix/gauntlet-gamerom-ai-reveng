"""The compositor's output type.

**Representation chosen:** an RGBA raster wrapping a ``PIL.Image`` (mode
``"RGBA"``). Rationale (a WP-2 design decision -- the docs don't pin an
implementation, only the logical 336x240 resolution, ``doc/01_hardware.md``
§4):

- PIL is already a hard dependency of ``gex`` (``assets.py`` pulls it in
  transitively, and ``python-gex/src/gex/render.py`` -- the module WP-1 names
  as the reference for ``Stamp``/``TileData`` shapes -- is built entirely on
  ``PIL.Image``). Using it here means tile/stamp blitting can reuse gex's own
  ``write_tile_to_image``-style pixel loops instead of reinventing them, and
  the playfield layer's golden-image tests compare like for like against
  gex's own ``genpfimage`` PNGs.
- It is inspectable without pygame: ``get_pixel``/``to_pil_image`` work in
  any headless test, which is the hard requirement from PLAN.md §6 WP-2
  ("must be inspectable by tests without pygame").
- PNG export for golden-image comparisons falls out for free
  (``Image.save``), rather than hand-rolling a PNG encoder.

The one thing this type deliberately does NOT do is talk to pygame. The host
shell (``render/host.py``) converts a ``Framebuffer`` to a pygame surface at
presentation time; nothing in this module imports pygame.
"""

from __future__ import annotations

from PIL import Image

__all__ = ["Framebuffer"]


class Framebuffer:
    """An RGBA raster of a fixed size, plus the handful of blit primitives
    the compositor layers need.

    Row 0 is the top of the screen, column 0 is the left, matching every
    other coordinate system in this codebase (``coords.py``).
    """

    __slots__ = ("width", "height", "image", "_pixels")

    def __init__(self, width: int, height: int, background: tuple[int, int, int, int] = (0, 0, 0, 255)) -> None:
        self.width = width
        self.height = height
        self.image = Image.new("RGBA", (width, height), background)
        self._pixels = self.image.load()

    # -- inspection ----------------------------------------------------------

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int] | None:
        """RGBA at (x, y), or ``None`` if out of bounds (never raises --
        callers doing boundary-adjacent assertions don't need a try/except).
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[x, y]
        return None

    def set_pixel(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[x, y] = rgba

    def to_pil_image(self) -> Image.Image:
        """A copy of the current raster (mutating the copy never affects
        this framebuffer)."""
        return self.image.copy()

    def save_png(self, path: str) -> None:
        """Golden-image export, per PLAN.md §6 WP-2's request for a PNG dump
        path."""
        self.image.save(path, "PNG")

    # -- clearing --------------------------------------------------------------

    def clear(self, rgba: tuple[int, int, int, int] = (0, 0, 0, 255)) -> None:
        self.image.paste(rgba, (0, 0, self.width, self.height))
        self._pixels = self.image.load()

    # -- blit primitives ---------------------------------------------------

    def paste_region(self, source: Image.Image, box: tuple[int, int, int, int], dest_xy: tuple[int, int]) -> None:
        """Copy ``source.crop(box)`` to ``dest_xy``. Used by the playfield
        layer to blit the scrolled window out of the cached world raster --
        this is what makes "camera scroll applied at blit time" (PLAN.md §6
        WP-2 step 1) a plain crop-and-paste rather than a per-tile
        recomputation every frame.
        """
        region = source.crop(box)
        self.image.paste(region, dest_xy)
        self._pixels = self.image.load()

    def blit_indexed_tile(
        self,
        tile: list[list[int]],
        palette_rgba: list[tuple[int, int, int, int]],
        x: int,
        y: int,
        *,
        trans0: bool = True,
        shadow_index: int | None = None,
        shadow_scale: float = 0.5,
        shadow_src=None,
        clip: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Blit one 8x8 palette-index tile (gex's ``TileData`` shape: 8 rows
        of 8 values 0-15) at raster position (x, y), consulting
        ``palette_rgba`` (16 entries) for color.

        ``shadow_index``, when given, makes that one index a special case
        instead of an ordinary color lookup: pixel value 1 is the hardware's
        shadow (``doc/01_hardware.md`` §4/§6), which shows the underlying
        playfield pixel through the half-intensity *shadow palette*.

        When ``shadow_src`` is given (a ``playfield.ShadowSource``), the exact
        hardware result is used: the shadow-palette color of the playfield
        pixel at this position is copied straight in -- and, matching the
        hardware, it reveals the *playfield*, not any MOB drawn earlier at the
        same pixel. When ``shadow_src`` is absent (no maze, or a ROM-free
        test), it falls back to darkening whatever is already there by
        ``shadow_scale`` -- a close approximation for the common full-intensity
        playfield colors, but the only option once the source intensity nibble
        is gone. The exact shadow palette is built by ``playfield.irgb_to_shadow``
        (ROM 0x5FD80). ``shadow_src`` also falls back to ``shadow_scale`` for
        any pixel it reports off-raster (e.g. a wraparound seam).

        ``clip``, when given, is ``(x0, y0, x1, y1)`` (``x1``/``y1``
        exclusive) restricting drawing to that sub-rectangle of the
        framebuffer in addition to the framebuffer's own bounds. The MOB
        layer passes its viewport here so a sprite straddling the edge of
        the playfield area doesn't bleed into the HUD panel -- real hardware
        has no such leak because the HUD is a separate physical layer, not a
        screen region a sprite could overdraw (``doc/01_hardware.md`` §4.1).
        """
        px = self._pixels
        w, h = self.width, self.height
        cx0, cy0, cx1, cy1 = clip if clip is not None else (0, 0, w, h)
        # Always clamp to the framebuffer's own bounds too, even if a caller
        # passes a clip rectangle that overshoots them -- PIL's pixel access
        # has no bounds checking of its own and would raise.
        x0, y0, x1, y1 = max(0, cx0), max(0, cy0), min(w, cx1), min(h, cy1)
        for j in range(8):
            row = tile[j]
            py = y + j
            if py < y0 or py >= y1:
                continue
            for i in range(8):
                pxx = x + i
                if pxx < x0 or pxx >= x1:
                    continue
                idx = row[i]
                if idx == 0:
                    if trans0:
                        continue
                    px[pxx, py] = palette_rgba[0]
                    continue
                if shadow_index is not None and idx == shadow_index:
                    exact = shadow_src.at(pxx, py) if shadow_src is not None else None
                    if exact is not None:
                        px[pxx, py] = exact
                    else:
                        under = px[pxx, py]
                        px[pxx, py] = (
                            int(under[0] * shadow_scale),
                            int(under[1] * shadow_scale),
                            int(under[2] * shadow_scale),
                            under[3],
                        )
                    continue
                px[pxx, py] = palette_rgba[idx]
