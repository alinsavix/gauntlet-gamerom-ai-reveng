"""ROM-faithful text rendering using the alpha character ROM.

The alpha layer's 8x8 glyphs (``gex.alphafont``, decoded from
``136043-1104.6p``) replace the PIL placeholder font the HUD and front-end
screens used to draw with. Glyphs 32-127 are ASCII, so any ASCII string
renders; the font is a fixed 8px monospace, which also makes centering exact.

The same ROM also holds the pre-baked HUD word glyphs the info panel is built
from (``draw_glyph_run`` below, fed by ``render/romtext.py``'s transcribed
runs), which is why this module exposes raw glyph indices as well as ASCII.

**Graceful fallback.** When the ROM is unavailable (no ``GEX_ROM_DIR``, e.g. a
headless CI box) the glyph lookup fails once and this module falls back to
PIL's bundled font, so text still appears -- the same "degrade, don't crash"
posture the rest of ``render/`` takes toward missing ROMs. A glyph run has no
PIL equivalent, so ``draw_glyph_run`` takes the ASCII spelling of the same word
and draws that instead.

Pixels are 2-bit intensities (0 = transparent, 1-3 = increasing brightness);
each lit pixel is written as the requested colour scaled by intensity/3, which
reads correctly over the black backgrounds the HUD and screens paint.
"""

from __future__ import annotations

GLYPH_W = 8
GLYPH_H = 8

_glyph_fn = None
_raw_glyph_fn = None
_glyph_checked = False


def _rom_glyphs():
    """The gex ``ascii_glyph`` callable, or ``None`` if the ROM is absent.

    Resolved once and cached (the answer cannot change within a run).
    """
    global _glyph_fn, _raw_glyph_fn, _glyph_checked
    if not _glyph_checked:
        _glyph_checked = True
        try:
            from gex.alphafont import ascii_glyph, glyph
            ascii_glyph("A")            # force the ROM read; raises without ROMs
            _glyph_fn = ascii_glyph
            _raw_glyph_fn = glyph
        except Exception:
            _glyph_fn = None
            _raw_glyph_fn = None
    return _glyph_fn


def rom_font_available() -> bool:
    """True when the ROM alpha font is in use (False = PIL fallback)."""
    return _rom_glyphs() is not None


def text_width(text: str, *, scale: int = 1) -> int:
    """Rendered width in pixels of ``text`` at ``scale`` (monospace 8px cells)."""
    return len(text) * GLYPH_W * scale


def draw_text(image, x, y, text: str, rgba, *, scale: int = 1) -> int:
    """Draw ASCII ``text`` with its top-left at ``(x, y)`` onto a PIL RGBA
    ``image``. Returns the advance width. Uses the ROM font when available,
    else PIL.
    """
    glyphs = _rom_glyphs()
    if glyphs is None:
        _draw_text_pil(image, x, y, text, rgba, scale)
        return text_width(text, scale=scale)

    cx = int(x)
    top = int(y)
    for ch in text:
        if ch == " ":
            # ASCII 32 in the ROM is an *opaque* block (the "black screen" fill,
            # doc/01 §9); as a word separator a space is a blank gap.
            cx += GLYPH_W * scale
            continue
        _blit_glyph(image, glyphs(ch), cx, top, rgba, scale)
        cx += GLYPH_W * scale
    return cx - int(x)


def draw_glyph_run(
    image, x, y, codes, rgba, *, fallback: str = "", scale: int = 1,
    palette=None,
) -> int:
    """Draw raw alpha-ROM glyph indices -- the pre-baked HUD words the info
    panel is made of (``render/romtext.py``). Returns the advance width.

    ``fallback`` is the ASCII spelling of the same word, drawn instead when the
    ROM font is unavailable (a raw glyph index has no PIL equivalent).
    """
    if _rom_glyphs() is None:
        if not fallback:
            return 0
        return draw_text(image, x, y, fallback, rgba, scale=scale)

    cx = int(x)
    top = int(y)
    for code in codes:
        _blit_glyph(
            image, _raw_glyph_fn(int(code)), cx, top, rgba, scale,
            palette=palette,
        )
        cx += GLYPH_W * scale
    return cx - int(x)


def glyph_run_width(codes, *, scale: int = 1) -> int:
    """Rendered width in pixels of a glyph run (one 8px cell per code)."""
    return len(tuple(codes)) * GLYPH_W * scale


def _blit_glyph(image, gl, x: int, y: int, rgba, scale: int, *,
                palette=None) -> None:
    """Blit one decoded 8x8 2-bit glyph, clipped to ``image``."""
    px = image.load()
    width, height = image.size
    r, g, b, a = rgba
    for gy in range(GLYPH_H):
        row = gl[gy]
        for gx in range(GLYPH_W):
            v = row[gx]
            if not v:
                continue
            if palette is None:
                f = v / 3.0
                col = (int(r * f), int(g * f), int(b * f), a)
            else:
                col = palette[v]
            bx = x + gx * scale
            by = y + gy * scale
            for sy in range(scale):
                yy = by + sy
                if not (0 <= yy < height):
                    continue
                for sx in range(scale):
                    xx = bx + sx
                    if 0 <= xx < width:
                        px[xx, yy] = col


def draw_text_centered(image, cx, y, text: str, rgba, *, scale: int = 1) -> None:
    """Draw ``text`` horizontally centred on ``cx``."""
    x = cx - text_width(text, scale=scale) / 2
    draw_text(image, x, y, text, rgba, scale=scale)


def _draw_text_pil(image, x, y, text: str, rgba, scale: int) -> None:
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=GLYPH_H * scale)
    except TypeError:                    # very old Pillow
        font = ImageFont.load_default()
    draw.text((x, y), text, fill=rgba, font=font)
