"""Playfield descriptor RAM and the ROM-shaped 2x2 stamp helpers.

This module intentionally has no gex dependency.  Simulation code writes the
same numeric descriptor words as the ROM; only the maze bridge chooses the
initial words and only the renderer decodes their graphics.
"""

from __future__ import annotations

from collections.abc import Iterable

PF_TILE_COLS = 64
PF_TILE_ROWS = 64
PF_WORD_COUNT = PF_TILE_COLS * PF_TILE_ROWS
PF_TILE_MASK = 0x0FFF
PF_PALETTE_MASK = 0x7000

EXIT_SETTLED_DESC = (0x039E, 0x039F, 0x0006, 0x0006)
EXITTO6_SETTLED_DESC = (0x039E, 0x039F, 0x03A0, 0x03A1)
TRANSPORTER_DESC = (0x449E, 0x449F, 0x44A0, 0x44A1)

# tport_palette_cycle_blocks, ROM 0x5AFAE: six 16-byte records.  VBLANK copies
# each record's first six words to palette 4 entries 8-13 (0x910590).
TRANSPORTER_COLOR_CYCLE = (
    (0x8F00, 0xCF21, 0xFF76, 0xFF98, 0xFFDD, 0xFFFF),
    (0x8F00, 0x8F00, 0xCF21, 0xFF76, 0xFF98, 0xFFDD),
    (0x8F00, 0x8F00, 0x8F00, 0xCF21, 0xFF76, 0xFF98),
    (0x8F00, 0x8F00, 0x8F00, 0x8F00, 0xCF21, 0xFF76),
    (0x8F00, 0x8F00, 0x8F00, 0x8F00, 0x8F00, 0xCF21),
    (0x8F00, 0x8F00, 0x8F00, 0x8F00, 0x8F00, 0x8F00),
)

# palette_offset1/2_by_floorpattern, ROM 0x405C8/0x405D8.  The ROM stores
# byte offsets from palette 1; color-RAM APIs use their corresponding indices.
SPECIAL_COLOR_INDEX_1 = (10, 10, 10, 10, 10, 1, 9, 9, 9)
SPECIAL_COLOR_INDEX_2 = (12, 12, 12, 12, 12, 2, 11, 1, 2)

EXIT_ANIM_STAGES = 7
EXIT_ANIM_FRAMES = 8
EXIT_DESC_TILE_BASE = 0x03A2
EXIT_DESC_RECORD = (0, 0, 1, 2, 3, 4, 5, 6, 6, 6, 5, 4, 3, 2, 1, 0)


def playfield_index(column: int, row: int) -> int:
    """Index one 8x8 tile in the hardware's column-first 64x64 table."""
    return (column & 0x3F) * PF_TILE_ROWS + (row & 0x3F)


def descriptor_indices(slot: int) -> tuple[int, int, int, int]:
    """VRAM indices for a maze cell's TL, TR, BL and BR descriptor words."""
    row = (slot >> 5) & 0x1F
    column = slot & 0x1F
    left = column << 1
    top = row << 1
    return (
        playfield_index(left, top),
        playfield_index(left + 1, top),
        playfield_index(left, top + 1),
        playfield_index(left + 1, top + 1),
    )


def read_tile_descriptor(state, slot: int) -> tuple[int, int, int, int]:  # noqa: ANN001
    return tuple(state.playfield_ram[index] for index in descriptor_indices(slot))


def write_tile_descriptor(
    state, slot: int, descriptor: Iterable[int], addend: int = 0,  # noqa: ANN001
) -> bool:
    """``pf_stamp_update`` (0x5E536): write one four-word 2x2 descriptor.

    Returns whether any word changed.  The generation is a host cache key, not
    arcade RAM, and advances only for a visible change.
    """
    words = tuple(descriptor)
    if len(words) != 4:
        raise ValueError("a playfield descriptor must contain four words")
    changed = False
    for index, word in zip(descriptor_indices(slot), words, strict=True):
        value = (int(word) + int(addend)) & 0xFFFF
        if state.playfield_ram[index] != value:
            state.playfield_ram[index] = value
            changed = True
    if changed:
        state.playfield_generation += 1
    return changed


def write_playfield_color(state, index: int, word: int) -> bool:  # noqa: ANN001
    """Write one word of normal playfield color RAM (0x910500)."""
    if not 0 <= index < 128:
        raise IndexError("playfield color index must be in 0..127")
    value = int(word) & 0xFFFF
    if state.playfield_color_ram[index] == value:
        return False
    state.playfield_color_ram[index] = value
    state.playfield_color_generation += 1
    return True


def write_playfield_colors(
    state, first: int, words: Iterable[int],  # noqa: ANN001
) -> bool:
    """Write a contiguous normal-color run and invalidate once."""
    values = tuple(int(word) & 0xFFFF for word in words)
    if first < 0 or first + len(values) > 128:
        raise IndexError("playfield color run exceeds 0x910500-0x9105FF")
    changed = False
    for offset, value in enumerate(values):
        index = first + offset
        if state.playfield_color_ram[index] != value:
            state.playfield_color_ram[index] = value
            changed = True
    if changed:
        state.playfield_color_generation += 1
    return changed


def exit_descriptor(floorpattern: int, record_entry: int) -> tuple[int, int, int, int]:
    stage = EXIT_DESC_RECORD[record_entry & 0x0F]
    first = EXIT_DESC_TILE_BASE + 4 * (
        (floorpattern % 9) * EXIT_ANIM_STAGES + stage
    )
    return first, first + 1, first + 2, first + 3
