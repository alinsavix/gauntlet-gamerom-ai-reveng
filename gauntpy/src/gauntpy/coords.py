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

One deliberate divergence, recorded here because this is the module that owns
the encoding. The hardware's own H/V words are not in whole pixels: the ROM
builds them as ``slot << 11`` (``maze_place_object`` 0x46192, ``maze_tile_write_at``),
which puts ``column * 32`` in the position field -- **half-pixels**, two units
per screen pixel -- and stores Y as ``(31 - row) * 32``, the *bottom* edge of
the cell counting **up** from the playfield floor. The per-type corrections in
``mazeobj_hpos_correction_tbl`` are in those same half-pixel units (its only
nonzero value, 512, is 8 field units = 4 px = half the overhang of a 24 px
sprite in a 16 px cell), which is what pins the scale down.

gauntpy keeps whole pixels with Y increasing downward, matching
``doc/04_game_subsystems.md`` §23.2's own ``pixel_x = column x 16`` /
``pixel_y = row x 16`` and every subsystem and renderer built on it. The two
representations are related by ``field = 2 * pixels`` horizontally and
``field = 2 * (512 - pixels - height)`` vertically, so nothing is lost -- but a
raw H/V word lifted straight out of a MAME trace will not compare equal to one
of ours, and ``maze.py`` converts the correction tables on the way in.
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
# mob_hpos: bits 15-6 X position, bits 5-4 software flags, bits 3-0 palette
# mob_vpos: bits 15-6 Y position, bits 5-3 width-1,        bits 2-0 height-1
#
# The ROM splits the same words one bit higher -- position in bits 15-7 over a
# seven-bit low field -- so every ROM site that rebuilds a position word masks
# with 0xFF80 and keeps 0x7F of the old one.  These are that pair, restated at
# gauntpy's shift; the low field keeps the ROM's own bit numbers, so a ROM
# constant that lands *in* it (a palette nibble, a packed sprite size) carries
# over unchanged while a constant that lands in the position field is >> 7 into
# whole pixels.

POS_FIELD_MASK = 0xFFC0
POS_LOW_MASK = 0x003F

HPOS_FLAG_MOVING = 0x20   # bit 5
HPOS_FLAG_ATTACK = 0x10   # bit 4


def encode_hpos(x: int, palette: int = 0, flags: int = 0) -> int:
    return ((x & 0x3FF) << 6) | (flags & 0x30) | (palette & 0x0F)


def decode_hpos(word: int) -> tuple[int, int, int]:
    """-> (x, flags, palette)."""
    return (word >> 6) & 0x3FF, word & 0x30, word & 0x0F


def encode_vpos(y: int, width: int = 1, height: int = 1) -> int:
    return ((y & 0x3FF) << 6) | (((width - 1) & 0x07) << 3) | ((height - 1) & 0x07)


def decode_vpos(word: int) -> tuple[int, int, int]:
    """-> (y, width, height) in 8x8 tiles."""
    return (word >> 6) & 0x3FF, ((word >> 3) & 0x07) + 1, (word & 0x07) + 1


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
