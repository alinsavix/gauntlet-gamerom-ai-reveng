"""Coordinate systems.

Gauntlet II locates things in three coordinate systems. All conversions here
are pure integer arithmetic, exactly as in the original.

Reference: ``doc/04_game_subsystems.md`` §1.3, §23.1-23.3.

  maze cell   row 0-31, column 0-31
  packed slot (row << 5) | column, range 0-1023 -- also the MOB id for
              dynamic objects (§1.2), which is why "identity is location"
  pixels      world pixel coordinates on the 512x512 playfield, 16 px/cell
  playfield   64x64 grid of 8x8 tiles, column-first; one maze cell owns a
              2x2 block

This module owns the **hardware MOB word encoding**, and gauntpy stores the
arcade's own words: a position field in bits 15-7 over a seven-bit low field,
one screen pixel per 0x80 field units.  ``maze_place_object`` (0x46192,
``maze_tile_write_at``) builds a cell's words as ``slot << 11``, which is
``column * 16`` and ``(31 - row) * 16`` pixels -- whole pixels, because the
field starts at bit 7.  The per-type corrections in
``mazeobj_hpos_correction_tbl`` are in those same field units (its only nonzero
value, 512, is 4 px, half the overhang of a 24 px sprite in a 16 px cell),
which is what pins the scale down.

Two conventions come with the hardware and are kept:

* **Vertical measures up.**  A V word is the distance from the playfield floor
  up to the *bottom* edge of the object's 16 px maze cell, so an object one row
  further down the screen has a *smaller* V.  ``V_ANCHOR_BIAS`` (496) converts:
  ``screen_y(v) == 496 - v`` and ``native_v(y) == 496 - y``, one involution,
  used at the rendering/UI boundary and wherever a subsystem needs a maze row.
  ``sprite_top_y`` adds the sprite's own height, which is what the display
  hardware does when it draws upward from that anchor.
* **One maze fills the word.**  ``512 << 7`` is 0x10000, so position arithmetic
  wraps at the seam by being 16-bit, with no extra masking -- exactly like the
  ROM's own ``add.w``/``sub.w`` on these words.
"""

from __future__ import annotations

MAZE_ROWS = 32
MAZE_COLS = 32
CELL_PIXELS = 16

PF_COLS = 64
PF_ROWS = 64
PF_ROW_STRIDE = 64  # words, column-first indexing

WORLD_PIXELS = 512


# --- packed slot <-> maze cell ------------------------------------------------

def pack_slot(row: int, col: int) -> int:
    """(row, col) -> packed slot. Bits 9-5 row, bits 4-0 column."""
    return ((row & 0x1F) << 5) | (col & 0x1F)


def unpack_slot(slot: int) -> tuple[int, int]:
    """packed slot -> (row, col)."""
    return (slot >> 5) & 0x1F, slot & 0x1F


# --- packed slot <-> world pixels ---------------------------------------------

def slot_to_pixels(slot: int) -> tuple[int, int]:
    """packed slot -> (pixel_x, pixel_y), the cell's unadjusted origin.

    ``pixel_y`` is the ordinary downward screen coordinate of the cell's top
    edge; ``native_v`` turns it into the hardware's upward V.

    Per-object sprite-origin corrections (``mazeobj_hpos_correction_tbl``,
    0x5858C, §5.4) are applied by object constructors, not here.
    """
    row, col = unpack_slot(slot)
    return col * CELL_PIXELS, row * CELL_PIXELS


def pixels_to_slot(x: int, y: int) -> int:
    """(pixel_x, pixel_y) -> packed slot, truncating to the containing cell."""
    return pack_slot(y // CELL_PIXELS, x // CELL_PIXELS)


# --- MOB hardware word encoding ------------------------------------------------
#
# mob_hpos: bits 15-7 X position, bits 6-4 software flags, bits 3-0 palette
# mob_vpos: bits 15-7 Y position, bit 6 spare, bits 5-3 width-1, bits 2-0 height-1
#
# Every ROM site that rebuilds a position word masks with 0xFF80 and keeps 0x7F
# of the old one; those are the two constants below, and a ROM constant that
# lands in either field carries over unchanged.

#: Field units per screen pixel, and the shift that produces them.
POS_SHIFT = 7
POS_UNIT = 1 << POS_SHIFT           # 0x80

POS_FIELD_MASK = 0xFF80
POS_LOW_MASK = 0x007F

#: A nine-bit position field holds one 512-pixel maze, so the whole word is one
#: maze: position arithmetic is plain 16-bit arithmetic and wraps at the seam.
POS_MODULUS = WORLD_PIXELS << POS_SHIFT     # 0x10000
POS_VALUE_MASK = WORLD_PIXELS - 1           # 0x1FF, the pixel value's own width

HPOS_FLAG_MOVING = 0x20   # bit 5
HPOS_FLAG_ATTACK = 0x10   # bit 4

#: ``native_v(y) == V_ANCHOR_BIAS - y``: the V word names the *bottom* edge of a
#: 16 px maze cell, counted up from the playfield floor, so the last row (31)
#: sits at 0 and row 0 at 496.
V_ANCHOR_BIAS = WORLD_PIXELS - CELL_PIXELS  # 496


def native_v(y: int) -> int:
    """Downward screen pixel Y -> the hardware's upward V pixel."""
    return (V_ANCHOR_BIAS - y) % WORLD_PIXELS


def screen_y(v: int) -> int:
    """Hardware upward V pixel -> downward screen pixel Y. Its own inverse."""
    return (V_ANCHOR_BIAS - v) % WORLD_PIXELS


def sprite_top_y(v: int, height_px: int) -> int:
    """Downward screen Y of the *top* row a sprite of ``height_px`` covers.

    The hardware draws upward from the V anchor, so a 24 px creature in a 16 px
    cell begins eight pixels above the cell and a 4x4 dragon sixteen.
    """
    return (WORLD_PIXELS - v - height_px) % WORLD_PIXELS


def encode_hpos(x: int, palette: int = 0, flags: int = 0) -> int:
    """Build an H word from a screen pixel X plus its low field."""
    return ((x & POS_VALUE_MASK) << POS_SHIFT) | (flags & 0x30) | (palette & 0x0F)


def decode_hpos(word: int) -> tuple[int, int, int]:
    """-> (x, flags, palette). ``x`` is a screen pixel."""
    return (word >> POS_SHIFT) & POS_VALUE_MASK, word & 0x30, word & 0x0F


def encode_vpos(v: int, width: int = 1, height: int = 1) -> int:
    """Build a V word from a **native upward** V pixel plus the packed size."""
    return (
        ((v & POS_VALUE_MASK) << POS_SHIFT)
        | (((width - 1) & 0x07) << 3)
        | ((height - 1) & 0x07)
    )


def decode_vpos(word: int) -> tuple[int, int, int]:
    """-> (v, width, height). ``v`` is the **native upward** V pixel."""
    return (
        (word >> POS_SHIFT) & POS_VALUE_MASK,
        ((word >> 3) & 0x07) + 1,
        (word & 0x07) + 1,
    )


def encode_vpos_at_y(y: int, width: int = 1, height: int = 1) -> int:
    """``encode_vpos`` for callers holding a downward screen Y."""
    return encode_vpos(native_v(y), width, height)


def decode_vpos_at_y(word: int) -> tuple[int, int, int]:
    """``decode_vpos`` with the position converted to a downward screen Y."""
    v, width, height = decode_vpos(word)
    return screen_y(v), width, height


def hpos_x(word: int) -> int:
    """Screen pixel X of an H word."""
    return (word >> POS_SHIFT) & POS_VALUE_MASK


def vpos_v(word: int) -> int:
    """Native upward V pixel of a V word."""
    return (word >> POS_SHIFT) & POS_VALUE_MASK


def vpos_y(word: int) -> int:
    """Downward screen Y of a V word -- the rendering/UI boundary conversion."""
    return screen_y((word >> POS_SHIFT) & POS_VALUE_MASK)


# --- packed slot -> playfield tile RAM ------------------------------------------

def slot_to_pf_index(slot: int) -> int:
    """packed slot -> word index of the top-left 8x8 tile of its 2x2 block.

    Playfield RAM is column-first: ``(col * 2) * 64 + (row * 2)``. The other
    three descriptors of the block sit at the +0x080/+0x002/+0x082 byte offsets
    documented in §23.3.
    """
    row, col = unpack_slot(slot)
    return (col * 2) * PF_ROW_STRIDE + (row * 2)


def pf_quad_indices(slot: int) -> tuple[int, int, int, int]:
    """The four word indices covering one maze cell's 2x2 tile block."""
    base = slot_to_pf_index(slot)
    return base, base + 1, base + PF_ROW_STRIDE, base + PF_ROW_STRIDE + 1
