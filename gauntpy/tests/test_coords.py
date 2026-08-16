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
    """X in bits 15-6, flags in 5-4, palette in 3-0."""
    word = coords.encode_hpos(320, palette=0xB, flags=coords.HPOS_FLAG_MOVING)
    x, flags, palette = coords.decode_hpos(word)
    assert (x, palette) == (320, 0xB)
    assert flags == coords.HPOS_FLAG_MOVING
    assert word >> 6 == 320


def test_vpos_word_layout():
    """Y in bits 15-6, width-1 in 5-3, height-1 in 2-0."""
    word = coords.encode_vpos(192, width=4, height=2)
    assert coords.decode_vpos(word) == (192, 4, 2)
    assert word >> 6 == 192


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
