"""ROM acquisition and gex adapters; no game-state changes or game RNG draws.

Stamp providers retain their explicit random-source argument. The game owns
when that source is consumed, including during live wall descriptor writes.
"""

from __future__ import annotations

import struct
from typing import NamedTuple

from gex.adjacency import checkffadj4, ff_make_map, whatis
from gex.constants import (
    LFLAG4_TRAPS_LOCAL, LFLAG4_WRAP_H, LFLAG4_WRAP_V, MAX_MAZE_NUM,
)
from gex.floor import floor_get_stamp
from gex.mazedecode import Maze, maze_decompress
from gex.objparams import (
    PICTURE_MARKER, base_picture, hpos_correction, hsize_tier, vpos_offset,
)
from gex.palettes import (
    FLOOR_PALETTES, SHRUB_FLOOR_COLOR_NUMS, SHRUB_PALETTE_DEFAULT, WALL_PALETTES,
)
from gex.rand import SeededRandom
from gex.roms import (
    GexError, coderom_get_bytes, slapstic_maze_get_bank,
    slapstic_maze_get_real_addr, slapstic_read_maze,
)
from gex.wall import ff_get_stamp, wall_get_destructable_stamp, wall_get_stamp


class MazeError(Exception):
    """An invalid maze number or a failure to acquire/decode its ROM record."""


class MazeLocation(NamedTuple):
    """Slapstic bank and normalized address returned by find_maze (0x40C78)."""

    bank: int
    addr: int


def find_maze(maze_number: int) -> MazeLocation:
    """Resolve the ROM's maze identity, not its dungeon level."""
    if not (0 <= maze_number <= MAX_MAZE_NUM):
        raise MazeError(f"maze number {maze_number} out of range 0..{MAX_MAZE_NUM}")
    try:
        bank = slapstic_maze_get_bank(maze_number)
        addr = slapstic_maze_get_real_addr(maze_number)
    except GexError as exc:
        raise MazeError(f"could not resolve maze {maze_number}: {exc}") from exc
    return MazeLocation(bank, addr)


def decode_maze(maze_number: int) -> Maze:
    """Acquire and decode a record; maze 116 has no trailing delimiter."""
    if not (0 <= maze_number <= MAX_MAZE_NUM):
        raise MazeError(f"maze number {maze_number} out of range 0..{MAX_MAZE_NUM}")
    try:
        compressed = slapstic_read_maze(maze_number)
        return maze_decompress(compressed, allow_missing_delimiter=maze_number == MAX_MAZE_NUM)
    except GexError as exc:
        raise MazeError(f"could not decode maze {maze_number}: {exc}") from exc


_FOOD_INVULN_PICTURES_ADDR = 0x58F20
_FOOD_INVULN_PICTURES_COUNT = 3
_food_invuln_pictures: tuple[int, ...] | None = None
_RANDOM_MAZE_FLAGS_ADDR = 0x57012
_RANDOM_MAZE_FLAGS_COUNT = 13
_random_maze_flags_table: tuple[int, ...] | None = None


def food_invuln_pictures_read() -> tuple[int, ...]:
    """Read the literal three-word invulnerable-food picture table (0x58F20)."""
    global _food_invuln_pictures
    if _food_invuln_pictures is None:
        raw = coderom_get_bytes(
            _FOOD_INVULN_PICTURES_ADDR, _FOOD_INVULN_PICTURES_COUNT * 2,
        )
        _food_invuln_pictures = struct.unpack(f">{_FOOD_INVULN_PICTURES_COUNT}H", raw)
    return _food_invuln_pictures


def random_maze_flags_table_read() -> tuple[int, ...]:
    """Read all thirteen flag records (0x57012), without selecting one."""
    global _random_maze_flags_table
    if _random_maze_flags_table is None:
        raw = coderom_get_bytes(_RANDOM_MAZE_FLAGS_ADDR, _RANDOM_MAZE_FLAGS_COUNT * 4)
        _random_maze_flags_table = struct.unpack(f">{_RANDOM_MAZE_FLAGS_COUNT}I", raw)
    return _random_maze_flags_table
