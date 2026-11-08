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
from gex import mazedecode
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


# ROM: adapter game:0x40C78 | Delegates bank/address lookup to gex and returns MazeLocation; no Slapstic bus switching, shared-stack ABI or ptr_maze_data write.
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


class _WriteLog(dict):
    """A maze's cells, also remembering each write in decode order."""

    # ROM: helper | Starts an empty log of a maze's object writes.
    def __init__(self) -> None:
        super().__init__()
        self.order: list[tuple[int, int]] = []

    # ROM: helper | Records one object write as gex's token routines make it.
    def __setitem__(self, cell: tuple[int, int], object_type: int) -> None:
        super().__setitem__(cell, object_type)
        self.order.append((cell[1] << 5 | cell[0], int(object_type)))


# ROM: part game:0x4C1BC | The token walk again through gex's own token routines, keeping the order of the object writes that gex's final map loses.
def maze_write_order(compressed: list[int]) -> list[tuple[int, int]] | None:
    """Every (packed slot, object type) the decoder writes, in order, floors excepted."""
    if len(compressed) < 11:
        return None
    maze = Maze()
    log = _WriteLog()
    maze.data = log
    htype1, htype2, vtype1, vtype2 = compressed[7:11]
    prev = htype2
    location = 32
    pos = 11
    while location < 1024 and pos < len(compressed):
        token = compressed[pos]
        pos += 1
        top2 = token & mazedecode._TOP2_MASK
        if top2 == mazedecode._TOK_LITERAL:
            location, prev = mazedecode._token_literal(maze, location, token)
        elif top2 == mazedecode._TOK_REPEAT:
            location, prev = mazedecode._token_repeat(
                maze, location, token, prev, htype1, htype2, vtype1, vtype2,
            )
        elif top2 == mazedecode._TOK_WALL_OR_PREV:
            location = mazedecode._token_wall_or_prev(maze, location, token, prev)
        elif top2 == mazedecode._TOK_FLOOR:
            location = mazedecode._token_floor(maze, location, token)
    return log.order


# ROM: adapter game:0x4C1BC | ROM acquisition and delegated maze-decode adapter returning a gex Maze; not the complete maze_setupnew body at 0x44AC2, which additionally places MOBs and initializes game state.
def decode_maze(maze_number: int) -> Maze:
    """Acquire and decode a record; maze 116 has no trailing delimiter."""
    if not (0 <= maze_number <= MAX_MAZE_NUM):
        raise MazeError(f"maze number {maze_number} out of range 0..{MAX_MAZE_NUM}")
    try:
        compressed = slapstic_read_maze(maze_number)
        maze = maze_decompress(compressed, allow_missing_delimiter=maze_number == MAX_MAZE_NUM)
        maze.write_order = maze_write_order(compressed)
        return maze
    except GexError as exc:
        raise MazeError(f"could not decode maze {maze_number}: {exc}") from exc


_FOOD_INVULN_PICTURES_ADDR = 0x58F20
_FOOD_INVULN_PICTURES_COUNT = 3
_food_invuln_pictures: tuple[int, ...] | None = None
_RANDOM_MAZE_FLAGS_ADDR = 0x57012
_RANDOM_MAZE_FLAGS_COUNT = 13
_random_maze_flags_table: tuple[int, ...] | None = None


# ROM: infrastructure | Cached acquisition of the literal invulnerable-food picture table; 0x58F20 is data, not an entry.
def food_invuln_pictures_read() -> tuple[int, ...]:
    """Read the literal three-word invulnerable-food picture table (0x58F20)."""
    global _food_invuln_pictures
    if _food_invuln_pictures is None:
        raw = coderom_get_bytes(
            _FOOD_INVULN_PICTURES_ADDR, _FOOD_INVULN_PICTURES_COUNT * 2,
        )
        _food_invuln_pictures = struct.unpack(f">{_FOOD_INVULN_PICTURES_COUNT}H", raw)
    return _food_invuln_pictures


# ROM: infrastructure | Cached acquisition of all random-maze flag records; does not perform get_random_maze_flags selection or RNG work.
def random_maze_flags_table_read() -> tuple[int, ...]:
    """Read all thirteen flag records (0x57012), without selecting one."""
    global _random_maze_flags_table
    if _random_maze_flags_table is None:
        raw = coderom_get_bytes(_RANDOM_MAZE_FLAGS_ADDR, _RANDOM_MAZE_FLAGS_COUNT * 4)
        _random_maze_flags_table = struct.unpack(f">{_RANDOM_MAZE_FLAGS_COUNT}I", raw)
    return _random_maze_flags_table
