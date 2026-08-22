"""Coordinate conversions between the three systems."""

from __future__ import annotations

import pytest

from gauntpy import coords


def test_the_worked_example_from_the_book():
    """book/08_world_in_memory.md traces row 12, column 20 through all three."""
    slot = coords.pack_slot(12, 20)
    assert slot == 0x194
    assert slot == 404
    assert coords.unpack_slot(slot) == (12, 20)
    assert coords.slot_to_pixels(slot) == (320, 192)
    assert coords.slot_to_pf_index(slot) == (20 * 2) * 64 + (12 * 2)


@pytest.mark.parametrize("row", [0, 1, 15, 31])
@pytest.mark.parametrize("col", [0, 1, 15, 31])
def test_slot_roundtrip(row, col):
    assert coords.unpack_slot(coords.pack_slot(row, col)) == (row, col)


def test_slot_covers_the_whole_range():
    seen = {coords.pack_slot(r, c) for r in range(32) for c in range(32)}
    assert seen == set(range(1024)), "32x32 cells map onto 1024 slots exactly"


def test_pixels_to_slot_truncates_into_the_containing_cell():
    slot = coords.pack_slot(12, 20)
    for dx in range(0, 16, 5):
        for dy in range(0, 16, 5):
            assert coords.pixels_to_slot(320 + dx, 192 + dy) == slot


def test_hpos_word_layout():
    """X in bits 15-7, flags in 6-4, palette in 3-0."""
    word = coords.encode_hpos(320, palette=0xB, flags=coords.HPOS_FLAG_MOVING)
    x, flags, palette = coords.decode_hpos(word)
    assert (x, palette) == (320, 0xB)
    assert flags == coords.HPOS_FLAG_MOVING
    assert word >> 7 == 320


def test_vpos_word_layout():
    """V in bits 15-7, width-1 in 5-3, height-1 in 2-0."""
    word = coords.encode_vpos(192, width=4, height=2)
    assert coords.decode_vpos(word) == (192, 4, 2)
    assert word >> 7 == 192


def test_flags_and_palette_do_not_collide():
    plain = coords.encode_hpos(64, palette=0xF, flags=0)
    moving = coords.encode_hpos(64, palette=0xF, flags=coords.HPOS_FLAG_MOVING)
    assert coords.decode_hpos(plain)[0] == coords.decode_hpos(moving)[0]
    assert coords.decode_hpos(plain)[2] == coords.decode_hpos(moving)[2]
    assert plain != moving


def test_playfield_block_is_column_first_2x2():
    slot = coords.pack_slot(3, 5)
    tl, bl, tr, br = coords.pf_quad_indices(slot)
    assert tl == (5 * 2) * 64 + (3 * 2)
    assert bl == tl + 1, "next word down the column"
    assert tr == tl + 64, "one playfield column across"
    assert br == tl + 65


# ---------------------------------------------------------------------------
# Field widths and wrapping
# ---------------------------------------------------------------------------

def test_position_fields_are_nine_bits_and_wrap_like_the_hardware():
    """A sprite-origin correction can push an object at column 0 negative; the
    hardware word has nine position bits and wraps, and so must the encoder
    rather than producing a Python negative that silently poisons later
    arithmetic."""
    assert coords.decode_hpos(coords.encode_hpos(-4))[0] == 0x1FC
    assert coords.decode_vpos(coords.encode_vpos(-8))[0] == 0x1F8
    assert coords.decode_hpos(coords.encode_hpos(512))[0] == 0


def test_size_fields_are_three_bits_each():
    """Width-1 in bits 5-3 and height-1 in 2-0, so 1-8 tiles per axis: the
    dragon's 4x4 and a monster's 3x3 both fit, and nothing bleeds into V."""
    for width in range(1, 9):
        for height in range(1, 9):
            word = coords.encode_vpos(160, width=width, height=height)
            assert coords.decode_vpos(word) == (160, width, height)


def test_encoding_never_disturbs_a_neighbouring_field():
    word = coords.encode_hpos(0x1FF, palette=0xF, flags=0x30)
    x, flags, palette = coords.decode_hpos(word)
    assert (x, flags, palette) == (0x1FF, 0x30, 0xF)
    assert word == 0xFFBF

    word = coords.encode_vpos(0x1FF, width=8, height=8)
    assert word == 0xFFBF


def test_slot_to_pixels_is_the_cell_origin_without_corrections():
    """Per-object corrections belong to the object constructor (``maze.py``),
    not here -- otherwise every caller would have to know which of the four
    master parameter tables applied."""
    for row, col in ((0, 0), (5, 7), (31, 31)):
        assert coords.slot_to_pixels(coords.pack_slot(row, col)) == (col * 16, row * 16)


def test_pixels_to_slot_is_the_inverse_of_slot_to_pixels():
    for slot in range(0, 1024, 37):
        x, y = coords.slot_to_pixels(slot)
        assert coords.pixels_to_slot(x, y) == slot


# ---------------------------------------------------------------------------
# The native ROM encoding
# ---------------------------------------------------------------------------

def test_one_screen_pixel_is_0x80_field_units():
    """The position field starts at bit 7, so ``x`` pixels is ``x << 7``."""
    assert coords.POS_SHIFT == 7
    assert coords.POS_UNIT == 0x80
    for x in (0, 1, 4, 16, 200, 511):
        assert coords.encode_hpos(x) == x << 7
        assert coords.hpos_x(x << 7) == x


def test_the_native_masks_are_the_roms_own():
    """Every ROM site that rebuilds a position word uses this exact pair."""
    assert coords.POS_FIELD_MASK == 0xFF80
    assert coords.POS_LOW_MASK == 0x007F
    assert coords.POS_FIELD_MASK | coords.POS_LOW_MASK == 0xFFFF


def test_one_512_pixel_maze_wraps_at_0x10000():
    """``512 << 7`` is exactly the 16-bit word, so position arithmetic wraps at
    the maze seam by being 16-bit -- no extra masking anywhere."""
    assert coords.POS_MODULUS == 0x10000
    assert coords.encode_hpos(511) + coords.POS_UNIT == 0x10000
    assert (coords.encode_hpos(511) + coords.POS_UNIT) & 0xFFFF == coords.encode_hpos(0)


def test_maze_placement_is_the_roms_slot_shifted_eleven():
    """``maze_place_object`` (0x46192) builds a cell's words as ``slot << 11``:
    ``column * 16`` horizontally and ``(31 - row) * 16`` vertically."""
    for row, col in ((0, 0), (5, 7), (12, 20), (31, 31)):
        slot = coords.pack_slot(row, col)
        x, y = coords.slot_to_pixels(slot)
        assert coords.encode_hpos(x) == (col << 11)
        assert coords.encode_vpos_at_y(y) == ((31 - row) << 11)


def test_the_vertical_axis_counts_up_from_the_playfield_floor():
    """V is the distance up to the *bottom* edge of the object's maze cell, so
    the last row sits at 0 and row 0 at 496."""
    assert coords.V_ANCHOR_BIAS == 496
    assert coords.native_v(0) == 496
    assert coords.native_v(31 * 16) == 0
    for y in range(0, 512, 7):
        assert coords.screen_y(coords.native_v(y)) == y
        assert coords.native_v(coords.screen_y(y)) == y


def test_a_taller_sprite_hangs_upward_from_its_anchor():
    """Hardware draws upward from the V anchor: a 24 px creature in a 16 px
    cell begins eight pixels above it, a 4x4 dragon sixteen."""
    v = coords.native_v(10 * 16)
    assert coords.sprite_top_y(v, 16) == 10 * 16
    assert coords.sprite_top_y(v, 24) == 10 * 16 - 8
    assert coords.sprite_top_y(v, 32) == 10 * 16 - 16


def test_the_low_field_survives_every_screen_conversion():
    """A palette nibble, software flags or a packed sprite size must ride
    through unchanged -- the conversions only touch bits 15-7."""
    word = coords.encode_hpos(200, palette=0xB, flags=coords.HPOS_FLAG_ATTACK)
    assert word & coords.POS_LOW_MASK == 0x1B
    assert coords.hpos_x(word) == 200

    word = coords.encode_vpos_at_y(10 * 16, width=3, height=3)
    assert word & coords.POS_LOW_MASK == 0x12
    assert coords.vpos_y(word) == 10 * 16
    assert coords.decode_vpos_at_y(word) == (10 * 16, 3, 3)
