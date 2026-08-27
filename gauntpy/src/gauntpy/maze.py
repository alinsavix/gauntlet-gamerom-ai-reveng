"""Maze and level system -- WP-3.

The public entry point is ``load_level(state, level_number)``, called at
level transitions: WP-20's boot/front-end path (``session.main_start_game``
via ``reset_and_load_level``), WP-15's exit sequence, WP-17's attract demo,
and the ``gauntpy-play`` runner all reach the maze through it.

Like ``assets.py``, this is a bridge module: it is allowed to import ``gex``
(the sibling ``../python-gex`` project) but must not import any gauntpy
subsystem module. gex already implements the Slapstic ROM reader and the
maze bytecode decompressor -- this module *reuses* both rather than porting
them (PLAN.md WP-3), and adds the game-specific layer gex has no reason to
know about: level selection, level-flag randomization and the maze mirroring
it drives, row-0 wall fill, and turning decoded tokens into ``MobTable``
records.

Reference: ``doc/04_game_subsystems.md`` section 5; ``doc/06_maze_catalog.md``;
``book/09_mazes_and_slapstic.md``; ``../python-gex/src/gex/{roms,mazedecode}.py``.

Scope note -- find_maze vs. level selection
--------------------------------------------
``doc/04_game_subsystems.md`` section 5.1 is explicit that ``find_maze``
(0x40C78) "Maps maze number -> data pointer + slapstic bank" -- it takes a
*maze number*, not a level number, and the 117-maze table in
``doc/06_maze_catalog.md`` has no level column (there is no fixed
level -> maze relationship past level 5; "the level -> maze mapping is
cabinet state, not a formula", doc/06 section 3). The much larger,
EEPROM-backed rotation algorithm that actually picks *which* maze number
plays as level 6 and beyond lives in ``player_exit_sequence`` (0x52B40) and
``maze_checknum`` (0x52ECA) -- both explicitly assigned to WP-15 in
``PLAN.md`` section 6 ("Exits, treasure rooms, secret rooms"), not WP-3, and
the resume-position write lives in ``main_health_countdown`` (WP-6).

So ``find_maze`` here is deliberately the narrow thing the doc describes:
maze number -> (bank, address). ``maze_for_level`` below implements only the
one *fixed* rule doc/06 section 3.1 documents (levels 1-5 -> mazes 0-4);
for level 6 and up, ``load_level`` trusts ``state.mazenum_current`` to have
already been set by whichever package computes the rotation. This is a
deliberate scope decision, not an oversight -- flagged here rather than
silently porting a level->maze formula the doc says does not exist.
"""

from __future__ import annotations

import struct
from dataclasses import replace
from typing import NamedTuple

from gex.adjacency import (
    checkffadj4,
    ff_make_map,
    whatis,
)
from gex.constants import (
    LFLAG4_TRAPS_LOCAL,
    LFLAG4_WRAP_H,
    LFLAG4_WRAP_V,
    MAX_MAZE_NUM,
)
from gex.floor import floor_get_stamp
from gex.palettes import (
    FLOOR_PALETTES,
    SHRUB_FLOOR_COLOR_NUMS,
    SHRUB_PALETTE_DEFAULT,
    WALL_PALETTES,
)
from gex.mazedecode import Maze, maze_decompress
from gex.objparams import (
    PICTURE_MARKER,
    base_picture,
    hpos_correction,
    hsize_tier,
    vpos_offset,
)
from gex.roms import (
    GexError,
    coderom_get_bytes,
    slapstic_maze_get_bank,
    slapstic_maze_get_real_addr,
    slapstic_read_maze,
)
from gex.wall import ff_get_stamp, wall_get_destructable_stamp, wall_get_stamp

from . import coords
from .constants import FIRST_PLAYABLE_SLOT, GameMode, MazeObjIds
from .mob import MobTable
from .playfield_vram import (
    EXIT_SETTLED_DESC,
    EXITTO6_SETTLED_DESC,
    TRANSPORTER_DESC,
    playfield_index,
    read_tile_descriptor,
    write_tile_descriptor,
)
from .state import GameState

__all__ = [
    "MazeError",
    "MazeLocation",
    "find_maze",
    "decode_maze",
    "maze_for_level",
    "level_flags_long",
    "mirror_slot",
    "mirror_maze",
    "maze_place_object",
    "place_decoded_objects",
    "get_random_maze_flags",
    "maze_load_pickup_config",
    "load_level",
    "reset_and_load_level",
    "set_cell_descriptor",
    "clear_cell_descriptor",
    "write_floor_descriptor",
    "postdecode_level_setup",
    "initialize_playfield_ram",
    "initialize_maze_color_ram",
    "load_attract_display_tilemap",
]

_ATTRACT_TILE_STREAM_ADDR = 0x5CB28
_ATTRACT_RUN_CONTROL_ADDR = 0x5850E
_ATTRACT_TILE_COLUMNS = 40
_ATTRACT_TILE_ROWS = 25
_ATTRACT_TILE_LEFT = 1
_ATTRACT_TILE_TOP = 5
_ATTRACT_RUN_CONTROL_SIZE = 125
_ATTRACT_FIXED_PALETTE_ADDR = 0x5AC5E


def load_attract_display_tilemap(state: GameState) -> None:
    """Port ``load_attract_display_tilemap`` 0x4438E into playfield VRAM."""
    count = _ATTRACT_TILE_COLUMNS * _ATTRACT_TILE_ROWS
    try:
        raw_words = coderom_get_bytes(_ATTRACT_TILE_STREAM_ADDR, count * 2)
        controls = coderom_get_bytes(
            _ATTRACT_RUN_CONTROL_ADDR, _ATTRACT_RUN_CONTROL_SIZE,
        )
    except GexError:
        return
    words = struct.unpack(f">{count}H", raw_words)
    word_index = 0
    control_index = 0
    remaining = 0
    palette = 0
    for row in range(_ATTRACT_TILE_TOP, _ATTRACT_TILE_TOP + _ATTRACT_TILE_ROWS):
        for column in range(
            _ATTRACT_TILE_LEFT, _ATTRACT_TILE_LEFT + _ATTRACT_TILE_COLUMNS,
        ):
            if remaining == 0:
                control = controls[control_index]
                control_index += 1
                palette = (control & 0xE0) << 7
                remaining = control & 0x1F
            state.playfield_ram[playfield_index(column, row)] = (
                words[word_index] & 0x0FFF
            ) | palette
            word_index += 1
            remaining -= 1
    state.playfield_generation += 1


def load_attract_fixed_palette() -> tuple[int, ...] | None:
    """Read init_display's fixed 128-word TITLE palette at ROM 0x5AC5E."""
    try:
        raw = coderom_get_bytes(_ATTRACT_FIXED_PALETTE_ADDR, 128 * 2)
    except GexError:
        return None
    return struct.unpack(">128H", raw)



class MazeError(Exception):
    """Something WP-3 could not satisfy: an out-of-range maze/level number
    or a gex-level decode failure. Mirrors ``assets.py``'s ``AssetError``
    pattern -- callers of this module never need to catch gex's own
    ``GexError``.
    """


def set_cell_descriptor(state: GameState, slot: int, object_type: int) -> None:
    """Update a logical cell and perform the ROM-equivalent local restamps."""
    slot &= 0x3FF
    data = getattr(state.maze, "data", None)
    if data is not None and slot >= FIRST_PLAYABLE_SLOT:
        row, col = coords.unpack_slot(slot)
        data[(col, row)] = int(object_type)

    if state.playfield_floor_catalog and data is not None:
        row, col = coords.unpack_slot(slot)
        write_tile_descriptor(
            state, slot, _descriptor_for_cell(state, slot, int(object_type)),
        )

        from .subsystems.maze_objects import refresh_surrounding_door_graphics

        refresh_surrounding_door_graphics(state, slot)

        # refresh_tile_visual 0x5F66E-0x5F76C visits these cells in this exact
        # order. Only north, north-east, and east have a floor fallback because
        # those are the three checkwalladj3 textures whose input includes the
        # changed center cell.
        refreshes = (
            (-1, -1, False), (0, -1, True), (1, -1, True),
            (-1, 0, False), (1, 0, True),
            (-1, 1, False), (0, 1, False), (1, 1, False),
        )
        for dx, dy, refresh_floor in refreshes:
            neighbour = coords.pack_slot(row + dy, col + dx)
            neighbour_type = _logical_cell_type(
                state, col + dx, row + dy,
            )
            wall_refreshed = _wall_needs_refresh(
                state, neighbour, neighbour_type,
            )
            if wall_refreshed:
                write_tile_descriptor(
                    state, neighbour,
                    _descriptor_for_cell(state, neighbour, neighbour_type),
                )
            elif refresh_floor and neighbour_type not in _WALL_TYPES:
                write_tile_descriptor(
                    state, neighbour,
                    _descriptor_for_cell(state, neighbour, neighbour_type),
                )

            if (
                (dx, dy) in ((0, -1), (1, 0))
                or wall_refreshed and (dx, dy) in ((-1, 0), (0, 1))
            ):
                refresh_surrounding_door_graphics(state, neighbour)
        return

    write_tile_descriptor(
        state, slot, _descriptor_for_cell(state, slot, int(object_type)),
    )


def clear_cell_descriptor(state: GameState, slot: int) -> None:
    """Replace one living-maze descriptor with floor."""
    set_cell_descriptor(state, slot, int(MazeObjIds.TILE_FLOOR))


def write_floor_descriptor(state: GameState, slot: int) -> None:
    """Run one centre-only ``pf_floor_update`` ordinary-floor write."""
    write_tile_descriptor(state, slot, _fresh_floor_descriptor(state, slot))


_SPECIAL_FLOORS = frozenset((
    int(MazeObjIds.TILE_STUN),
    int(MazeObjIds.TILE_TRAP1),
    int(MazeObjIds.TILE_TRAP2),
    int(MazeObjIds.TILE_TRAP3),
))
_WALL_TYPES = frozenset((
    int(MazeObjIds.WALL_REGULAR),
    int(MazeObjIds.WALL_SECRET),
    int(MazeObjIds.WALL_DESTRUCTABLE),
    int(MazeObjIds.WALL_RANDOM),
    int(MazeObjIds.WALL_TRAPCYC1),
    int(MazeObjIds.WALL_TRAPCYC2),
    int(MazeObjIds.WALL_TRAPCYC3),
))
_TRAP_WALL_TYPES = frozenset((
    int(MazeObjIds.WALL_TRAPCYC1),
    int(MazeObjIds.WALL_TRAPCYC2),
    int(MazeObjIds.WALL_TRAPCYC3),
))

_WALL_ADJ8 = (
    (-1, -1, 0x01), (0, -1, 0x02), (1, -1, 0x04),
    (-1, 0, 0x08), (1, 0, 0x10),
    (-1, 1, 0x20), (0, 1, 0x40), (1, 1, 0x80),
)
_FLOOR_ADJ3 = ((-1, 0, 4), (0, 1, 16), (-1, 1, 8))


def _logical_cell_type(state: GameState, col: int, row: int) -> int:
    data = getattr(state.maze, "data", None)
    if data is None:
        return int(MazeObjIds.TILE_FLOOR)
    return int(data.get((col & 0x1F, row & 0x1F), MazeObjIds.TILE_FLOOR))


def _wall_needs_refresh(
    state: GameState, slot: int, object_type: int,
) -> bool:
    """Match refresh_tile_visual's connectable-wall probe for live records."""
    if object_type not in _WALL_TYPES:
        return False
    if (
        object_type == int(MazeObjIds.WALL_DESTRUCTABLE)
        and slot in state.destructible_wall_stage
    ):
        return False
    if (
        object_type == int(MazeObjIds.WALL_RANDOM)
        and state.mobs.picture[slot] == 0
    ):
        return False
    return True


def _wall_is_visible(state: GameState, object_type: int) -> bool:
    """Apply maze_init_walls/pf_wall_draw's two invisibility gates."""
    if state.levelnum_current == LEVEL_SENTINEL:
        return True
    if state.level_flags_2 & 0x80:
        return False
    return not (
        object_type in _TRAP_WALL_TYPES and state.level_flags & 0x80
    )


def _wall_adjacency(state: GameState, slot: int) -> int:
    row, col = coords.unpack_slot(slot)
    return sum(
        bit for dx, dy, bit in _WALL_ADJ8
        if (
            (neighbor := coords.pack_slot(
                (row + dy) & 0x1F, (col + dx) & 0x1F,
            )) < FIRST_PLAYABLE_SLOT
            or (
                state.mobs.picture[neighbor] == 0x8000
                and _logical_cell_type(state, col + dx, row + dy) in _WALL_TYPES
            )
        )
    )


def _floor_adjacency(state: GameState, slot: int) -> int:
    if state.playfield_wallpattern >= 11:
        return 0
    row, col = coords.unpack_slot(slot)
    return sum(
        bit for dx, dy, bit in _FLOOR_ADJ3
        if (
            (object_type := _logical_cell_type(
                state, col + dx, row + dy,
            )) in _WALL_TYPES
            and _wall_is_visible(state, object_type)
            and not (
                object_type in _TRAP_WALL_TYPES
                and (
                    state.level_flags & 0x80
                    or state.level_flags_3 & 0x08
                )
            )
            and state.mobs.picture[
                coords.pack_slot((row + dy) & 0x1F, (col + dx) & 0x1F)
            ] == 0x8000
        )
    )


def write_cyclic_wall_descriptor(
    state: GameState, slot: int, object_type: int,
) -> None:
    """Center-only wall_place_playfield_update for cyclic wall types 7-9."""
    row, col = coords.unpack_slot(slot)
    maze = state.maze
    data = getattr(maze, "data", None)
    if data is not None:
        data[(col, row)] = int(object_type)
    if not _wall_is_visible(state, object_type):
        return
    adjacency = sum(
        bit for dx, dy, bit in _WALL_ADJ8
        if (
            (neighbor := coords.pack_slot(
                (row + dy) & 0x1F, (col + dx) & 0x1F,
            )) >= FIRST_PLAYABLE_SLOT
            and state.mobs.picture[neighbor] == 0x8000
            and state.mobs.obj_type(neighbor) in _TRAP_WALL_TYPES
        )
    )
    if maze is None:
        return
    try:
        stamp = wall_get_stamp(
            int(getattr(maze, "wallpattern", 0)), adjacency,
            int(getattr(maze, "wallcolor", 0)), _StateRandom(state),
        )
    except GexError:
        return
    write_tile_descriptor(state, slot, _descriptor_words(stamp, 7))


def _forcefield_adjacency(state: GameState, slot: int) -> int:
    result = 0
    for segment in state.forcefield_segments:
        hub = segment & 0x3FF
        row, col = coords.unpack_slot(hub)
        length = ((segment >> 10) & 0x0F) + 1
        horizontal = bool(segment & 0x8000)
        endpoint = (
            (row << 5) | ((col + length) & 0x1F)
            if horizontal
            else (((row + length) & 0x1F) << 5) | col
        )
        if slot == hub:
            result |= 2 if horizontal else 4
        elif slot == endpoint:
            result |= 8 if horizontal else 1
    return result


def _descriptor_for_cell(
    state: GameState, slot: int, object_type: int,
) -> tuple[int, int, int, int]:
    slot &= 0x3FF
    object_type = int(object_type)
    if object_type == int(MazeObjIds.TILE_FLOOR):
        return _fresh_floor_descriptor(state, slot)
    if object_type in _SPECIAL_FLOORS:
        palette = 2 if object_type == int(MazeObjIds.TILE_STUN) else 1
        return _fresh_floor_descriptor(state, slot, palette=palette)
    if object_type == int(MazeObjIds.EXIT):
        return EXIT_SETTLED_DESC
    if object_type == int(MazeObjIds.EXITTO6):
        return EXITTO6_SETTLED_DESC
    if object_type == int(MazeObjIds.TRANSPORTER):
        return TRANSPORTER_DESC
    if object_type == int(MazeObjIds.WALL_DESTRUCTABLE):
        if not _wall_is_visible(state, object_type):
            return read_tile_descriptor(state, slot)
        descriptor = state.playfield_destruct_catalog.get(
            _wall_adjacency(state, slot)
        )
        if descriptor is not None:
            return descriptor
        maze = state.maze
        if maze is None or not hasattr(maze, "wallpattern"):
            return read_tile_descriptor(state, slot)
        if maze is not None:
            try:
                stamp = wall_get_destructable_stamp(
                    int(getattr(maze, "wallpattern", 0)),
                    _wall_adjacency(state, slot),
                    int(getattr(maze, "wallcolor", 0)),
                    _StateRandom(state),
                )
            except GexError:
                return read_tile_descriptor(state, slot)
            return _descriptor_words(stamp, 7)
    if object_type in _WALL_TYPES:
        if not _wall_is_visible(state, object_type):
            return read_tile_descriptor(state, slot)
        descriptor = state.playfield_wall_catalog.get(
            _wall_adjacency(state, slot)
        )
        if descriptor is not None:
            return descriptor
        maze = state.maze
        if maze is None or not hasattr(maze, "wallpattern"):
            return read_tile_descriptor(state, slot)
        if maze is not None:
            try:
                stamp = wall_get_stamp(
                    int(getattr(maze, "wallpattern", 0)),
                    _wall_adjacency(state, slot),
                    int(getattr(maze, "wallcolor", 0)),
                    _StateRandom(state),
                )
            except GexError:
                return read_tile_descriptor(state, slot)
            return _descriptor_words(stamp, 7)
    if object_type == int(MazeObjIds.FORCEFIELDHUB):
        adjacency = _forcefield_adjacency(state, slot)
        descriptor = state.playfield_forcefield_catalog.get(
            adjacency
        )
        if descriptor is not None:
            return descriptor
        return _descriptor_words(ff_get_stamp(adjacency), 4)
    if object_type in _WALL_TYPES:
        return read_tile_descriptor(state, slot)
    return _fresh_floor_descriptor(state, slot)


def _initial_floor_descriptor(
    state: GameState, slot: int, object_type: int,
) -> tuple[int, int, int, int]:
    """Make the one descriptor decision made by ``maze_floor_decor``.

    The ROM checks the four descriptor-owned object types before reaching its
    random-floor branch.  Everything else receives one floor draw here; walls
    are replaced by the separate wall pass afterwards.
    """
    object_type = int(object_type)
    if object_type in (
        int(MazeObjIds.EXIT),
        int(MazeObjIds.EXITTO6),
        int(MazeObjIds.TRANSPORTER),
        int(MazeObjIds.FORCEFIELDHUB),
    ):
        return _descriptor_for_cell(state, slot, object_type)
    if object_type in _SPECIAL_FLOORS:
        palette = 2 if object_type == int(MazeObjIds.TILE_STUN) else 1
        return _fresh_floor_descriptor(state, slot, palette=palette)
    return _fresh_floor_descriptor(state, slot)


def _initial_object_type(
    state: GameState, maze: Maze, slot: int, col: int, row: int,
) -> int:
    """Read the post-setup MOB type, falling back to decoded floor-only data."""
    if state.mobs.is_occupied(slot):
        return state.mobs.obj_type(slot)
    decoded = int(whatis(maze, col, row))
    if state.cyclic_wall_setup_ready and decoded in _TRAP_WALL_TYPES:
        return int(MazeObjIds.TILE_FLOOR)
    return decoded


class _StateRandom:
    """gex stamp-provider adapter over the game's single live RNG stream."""

    def __init__(self, state: GameState) -> None:
        self.state = state

    def intn(self, bound: int) -> int:
        return self.state.getrandom(bound)


def _fresh_floor_descriptor(
    state: GameState, slot: int, *, palette: int | None = None,
) -> tuple[int, int, int, int]:
    """Draw the texture variant at the descriptor write point, as the ROM does."""
    variation = state.getrandom(4)
    adjacency = _floor_adjacency(state, slot)
    descriptor = state.playfield_floor_catalog.get((adjacency, variation))
    if descriptor is None:
        if not state.playfield_floor_catalog:
            descriptor = state.playfield_floor_descriptors[slot]
        else:
            maze = state.maze
            if maze is None:
                descriptor = state.playfield_floor_descriptors[slot]
            else:
                descriptor = _descriptor_words(
                    floor_get_stamp(
                        int(getattr(maze, "floorpattern", 0)),
                        adjacency + variation,
                        int(getattr(maze, "floorcolor", 0)),
                    ),
                    0,
                )
    if palette is None:
        palette = 3 if slot in state.playfield_forcefield_cells else 0
    descriptor = tuple(
        (word & 0x8FFF) | ((palette & 7) << 12) for word in descriptor
    )
    state.playfield_floor_descriptors[slot] = descriptor
    return descriptor


def _descriptor_words(stamp, palette: int) -> tuple[int, int, int, int]:  # noqa: ANN001
    return tuple(
        (int(word) & 0x0FFF) | ((palette & 7) << 12)
        for word in stamp.numbers[:4]
    )


def _palette_words(palette) -> list[int]:  # noqa: ANN001
    return [int(color.irgb) & 0xFFFF for color in palette]


def initialize_maze_color_ram(
    state: GameState, maze: Maze, *, floorcolor: int | None = None,
) -> None:
    """Run the palette half of init_display for a decoded maze."""
    from .subsystems.display import init_playfield_color_ram

    selected_floorcolor = maze.floorcolor if floorcolor is None else floorcolor
    palette7_substitutions: tuple[tuple[int, int], ...] = ()
    if maze.wallpattern >= 6:
        raw_special = (
            WALL_PALETTES[maze.wallcolor - 1]
            if maze.wallcolor else SHRUB_PALETTE_DEFAULT
        )
        first = 3 if maze.wallpattern >= 11 else 0
        floor_indices = SHRUB_FLOOR_COLOR_NUMS[maze.floorpattern][first:first + 3]
        palette7_substitutions = tuple(
            (13 + offset, FLOOR_PALETTES[selected_floorcolor][source].irgb)
            for offset, source in enumerate(floor_indices)
        )
    else:
        raw_special = WALL_PALETTES[maze.wallcolor]
    init_playfield_color_ram(
        state,
        _palette_words(FLOOR_PALETTES[selected_floorcolor]),
        _palette_words(raw_special),
        palette7_substitutions=palette7_substitutions,
    )


def initialize_playfield_ram(state: GameState, maze: Maze) -> None:
    """Commit one level's randomly selected 64x64 descriptor table.

    This is the gex-using level bridge corresponding to ``maze_floor_decor`` and
    the initial ``refresh_tile_visual`` sweep. Every random descriptor choice is
    drawn from ``state.getrandom`` at the point where its four words are written.
    """
    initialize_maze_color_ram(state, maze)

    state.playfield_ram[:] = [0] * len(state.playfield_ram)
    state.playfield_floor_descriptors[:] = [(0, 0, 0, 0)] * 1024
    state.playfield_floor_catalog.clear()
    state.playfield_wall_catalog.clear()
    state.playfield_destruct_catalog.clear()
    state.playfield_forcefield_catalog.clear()
    state.playfield_wallpattern = int(maze.wallpattern)
    state.playfield_forcefield_cells = set()
    for segment in state.forcefield_segments:
        hub = segment & 0x3FF
        row, col = coords.unpack_slot(hub)
        length = ((segment >> 10) & 0x0F) + 1
        horizontal = bool(segment & 0x8000)
        for distance in range(1, length):
            state.playfield_forcefield_cells.add(
                (row << 5) | ((col + distance) & 0x1F)
                if horizontal
                else (((row + distance) & 0x1F) << 5) | col
            )
    for adjacency in (0, 4, 8, 12, 16, 20, 24, 28):
        for variation in range(4):
            state.playfield_floor_catalog[(adjacency, variation)] = (
                _descriptor_words(
                    floor_get_stamp(
                        maze.floorpattern, adjacency + variation,
                        maze.floorcolor,
                    ),
                    0,
                )
            )

    from gex.rand import SeededRandom
    if maze.wallpattern in (0, 1, 2, 3, 4, 5, 6, 11):
        for adjacency in range(256):
            state.playfield_wall_catalog[adjacency] = _descriptor_words(
                wall_get_stamp(
                    maze.wallpattern, adjacency, maze.wallcolor,
                    SeededRandom(5),
                ),
                7,
            )
    for adjacency in range(256):
        state.playfield_destruct_catalog[adjacency] = _descriptor_words(
            wall_get_destructable_stamp(
                maze.wallpattern, adjacency, maze.wallcolor, SeededRandom(5),
            ),
            7,
        )
    for adjacency in range(16):
        state.playfield_forcefield_catalog[adjacency] = _descriptor_words(
            ff_get_stamp(adjacency), 4,
        )

    # maze_floor_decor calls pf_floor_update once per cell. Fixed descriptor
    # types return before the RNG branch; ordinary floors and object underlays
    # draw exactly one variation. Wall graphics are a later, separate pass.
    for col in range(32):
        for row in range(32):
            slot = coords.pack_slot(row, col)
            obj = _initial_object_type(state, maze, slot, col, row)
            descriptor = _initial_floor_descriptor(state, slot, obj)
            write_tile_descriptor(state, slot, descriptor)

    # maze_init_walls owns wall descriptor selection and its pattern-specific
    # random draws. No floor decision is repeated in this pass.
    for row in range(32):
        for col in range(32):
            slot = coords.pack_slot(row, col)
            obj = _initial_object_type(state, maze, slot, col, row)
            if obj in _WALL_TYPES and _wall_is_visible(state, obj):
                descriptor = _descriptor_for_cell(state, slot, obj)
                write_tile_descriptor(state, slot, descriptor)


# ---------------------------------------------------------------------------
# find_maze (0x40C78) and maze decode -- thin wrappers over gex
# ---------------------------------------------------------------------------

class MazeLocation(NamedTuple):
    """``find_maze``'s result: which Slapstic bank holds the record, and its
    normalized address within the 32 KiB image (doc/06 sections 1-2).
    """

    bank: int
    addr: int


def find_maze(maze_number: int) -> MazeLocation:
    """``find_maze`` (0x40C78): maze number -> Slapstic bank + data pointer
    (doc/04 section 5.1). See the module docstring's "Scope note" -- this
    maps a *maze number*, not a level.

    Delegates entirely to gex, which already implements the 2-bit bank
    lookup table (0x39FE0) and the 117-entry pointer table (0x3800C),
    normalized into the interleaved 32 KiB image (doc/06 sections 1-2).
    """
    if not (0 <= maze_number <= MAX_MAZE_NUM):
        raise MazeError(f"maze number {maze_number} out of range 0..{MAX_MAZE_NUM}")
    try:
        bank = slapstic_maze_get_bank(maze_number)
        addr = slapstic_maze_get_real_addr(maze_number)
    except GexError as exc:
        raise MazeError(f"could not resolve maze {maze_number}: {exc}") from exc
    return MazeLocation(bank, addr)


def decode_maze(maze_number: int) -> Maze:
    """Read and decompress one maze record: ``find_maze``'s pointer feeds
    ``maze_decode`` (0x4C1BC) in the original; here both steps are gex calls
    (``slapstic_read_maze`` + ``maze_decompress``), never ported.

    Maze 116 has no trailing zero delimiter -- its stream runs into the bank
    lookup table at the end of the 32 KiB image (doc/06 section 8) -- so it
    is decoded with ``allow_missing_delimiter``, matching gex's own CLI
    (``gex/maze.py`` ``domaze``).
    """
    if not (0 <= maze_number <= MAX_MAZE_NUM):
        raise MazeError(f"maze number {maze_number} out of range 0..{MAX_MAZE_NUM}")
    try:
        compressed = slapstic_read_maze(maze_number)
        return maze_decompress(compressed, allow_missing_delimiter=maze_number == MAX_MAZE_NUM)
    except GexError as exc:
        raise MazeError(f"could not decode maze {maze_number}: {exc}") from exc


# ---------------------------------------------------------------------------
# Level -> maze selection -- the opening act only (see "Scope note" above)
# ---------------------------------------------------------------------------

def maze_for_level(level_number: int) -> int | None:
    """The one *fixed* level -> maze rule: levels 1-5 always play mazes 0-4,
    in that order (doc/06 section 3.1; ``book/09`` "Choosing the next
    maze"). Returns ``None`` for any other level number -- from level 6 on,
    the maze number is cabinet-rotation state, not a function of the level
    number alone (see module docstring "Scope note").
    """
    if 1 <= level_number <= 5:
        return level_number - 1
    return None


# ---------------------------------------------------------------------------
# Level-flag mirroring (maze_place_object 0x45E9A-0x45FD0)
# ---------------------------------------------------------------------------
#
# Two of the level-flags longword's bits flip the whole maze as it is placed,
# and they are exactly the two bits ``maze_load_pickup_config`` re-randomizes
# on every level (doc/04 sec 5.5: "LFLAG1 bits 2-3 (long bits 26-27) are XOR'd
# with getrandom(4) every level"). That is why the same maze number never
# quite plays the same way twice, and why ``doc/07_function_index.md``'s
# ``maze_tile_write_at`` entry speaks of "the level_flags (0x90491C) mirror
# bits" without naming them: verified by disassembly at ROM 0x45E9E-0x45FBC
# and 0x45F42-0x45FBC, bit 26 mirrors horizontally and bit 27 vertically.
#
# gex names the same two bits ``LFLAG1_ODDANGLE_DEMONS`` / ``_LOBBERS`` and
# doc/05 sec 3.12 lists them the same way; the odd-angle override table
# (0x40E02) covers ghosts/grunts/sorcerers/aux-grunts/Death, not demons and
# lobbers, so the placement use is the one with evidence behind it. Named
# here for what the code does with them, cross-referenced rather than
# renamed in gex.

MIRROR_H_FLAG = 1 << 26   # LFLAG1 bit 2
MIRROR_V_FLAG = 1 << 27   # LFLAG1 bit 3

#: ``levelnum_current`` sentinel (0x270F) used by the secret/treasure rooms:
#: with it set, placement is never mirrored and the flags are never
#: randomized (ROM 0x45FC4-0x45FCC, 0x4374C).
LEVEL_SENTINEL = 9999


def level_flags_long(state: GameState) -> int:
    """The four level-flags bytes as the one longword at 0x90491C."""
    return _join_flags(
        state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4
    )


def mirror_slot(state: GameState, slot: int) -> int:
    """Apply the level's mirror flags to a packed slot (ROM 0x45F3E-0x45FD0).

    Horizontal first, then vertical -- the ROM's order, though each preserves
    the other's axis so it does not matter:

      * horizontal: ``col -> (base - col) & 0x1F`` with ``base`` 0x1F when
        LFLAG4 WrapH is set and 0x20 otherwise, so a wrapping level mirrors
        about the seam and a non-wrapping one keeps column 0 (its border wall)
        in place;
      * vertical: ``row -> 32 - row``, which is why row 0 -- the reserved
        block the decoder never emits -- has no mirror image.

    Slots below ``FIRST_PLAYABLE_SLOT`` (the row-0 wall fill) and the
    ``levelnum_current == 9999`` sentinel bypass mirroring entirely
    (0x45FBC-0x45FCC).
    """
    if slot < FIRST_PLAYABLE_SLOT or state.levelnum_current == LEVEL_SENTINEL:
        return slot

    flags = level_flags_long(state)
    if flags & MIRROR_H_FLAG:
        base = 0x1F if state.level_flags_4 & LFLAG4_WRAP_H else 0x20
        slot = (slot & 0x3E0) | ((base - slot) & 0x1F)
    if flags & MIRROR_V_FLAG:
        slot = (slot & 0x1F) + (0x400 - (slot & 0x3E0))
    return slot


def _placement_slot(state: GameState, slot: int, object_type: int) -> int:
    """Mirror one placement and correct a dragon's 2x2 anchor."""
    slot = mirror_slot(state, slot)
    if object_type != int(MazeObjIds.MONST_DRAGON):
        return slot
    flags = level_flags_long(state)
    if flags & MIRROR_H_FLAG:
        slot = (slot & 0x3E0) | ((slot - 1) & 0x1F)
    if flags & MIRROR_V_FLAG:
        slot = (slot + 0x20) & 0x3FF
    return slot


def mirror_maze(state: GameState, maze: Maze) -> Maze:
    """A copy of ``maze`` with ``data`` moved through ``mirror_slot``.

    ``maze_place_object`` mirrors each cell as it places it, so the MobTable
    is already correct without this. The *terrain* is a second consumer:
    ``render/playfield.py`` builds its tile image straight from
    ``state.maze.data``, and the original mirrors that too (the same flags are
    applied by ``maze_tile_write``/``maze_tile_write_at`` inside
    ``maze_decode``, ``doc/07_function_index.md`` 0x4631C). Storing the
    mirrored view keeps the drawn walls and the walls you collide with the
    same walls.
    """
    mirrored = {}
    for (col, row), object_type in maze.data.items():
        slot = _placement_slot(
            state, coords.pack_slot(row, col), int(object_type),
        )
        new_row, new_col = coords.unpack_slot(slot)
        mirrored[(new_col, new_row)] = object_type
    return replace(maze, data=mirrored)


# ---------------------------------------------------------------------------
# maze_place_object (0x45E40) and MobTable population
# ---------------------------------------------------------------------------
#
# The dispatcher splits its 64 object types three ways (doc/04 sec 5.4,
# verified at ROM 0x45FD2-0x4610A):
#
#   * solid-wall markers write ``mob_picture`` 0x8000 straight into the five
#     arrays -- no ``mob_create``, and so never a member of the depth chain;
#   * tile markers do the same with 0x8001;
#   * everything else is a real sprite built by ``mob_create`` from the master
#     parameter tables.

#: Types whose marker word is 0x8000 (ROM 0x45FD2-0x4600E). Forcefield hubs
#: are solid endpoints; contact damage comes from the beam segment cells between
#: hubs, not by walking through a hub.
_SOLID_WALL_MARKERS = frozenset((
    int(MazeObjIds.WALL_REGULAR),
    int(MazeObjIds.WALL_SECRET),
    int(MazeObjIds.WALL_DESTRUCTABLE),
    int(MazeObjIds.WALL_RANDOM),
    int(MazeObjIds.WALL_TRAPCYC1),
    int(MazeObjIds.WALL_TRAPCYC2),
    int(MazeObjIds.WALL_TRAPCYC3),
    int(MazeObjIds.FORCEFIELDHUB),
))

#: Types whose marker word is 0x8001 (ROM 0x460B8-0x46100) -- floor-level
#: things drawn by the playfield layer or by their own animated MOB in a fixed
#: slot, never by a base sprite. Marker records never enter the MOB depth chain,
#: so the sprite renderer does not see these words.
_TILE_MARKERS = frozenset((
    int(MazeObjIds.TILE_STUN),
    int(MazeObjIds.TILE_TRAP1),
    int(MazeObjIds.TILE_TRAP2),
    int(MazeObjIds.TILE_TRAP3),
    int(MazeObjIds.EXIT),
    int(MazeObjIds.EXITTO6),
    int(MazeObjIds.TRANSPORTER),
))

#: Every type the ROM stamps as a marker. Their
#: ``mazeobj_hpos_correction_tbl`` entries are dead data (the marker branch
#: uses a fixed word instead), which matters because entry 0x3F holds 8000 --
#: 62 px of "correction" that would fling the hub across the maze.
_ROM_MARKER_TYPES = _SOLID_WALL_MARKERS | _TILE_MARKERS

#: The solid-wall marker word (doc/04 sec 5.4; ``players._slot_is_blocking``).
WALL_MARKER_PICTURE = 0x8000
#: Floor/animated marker word (ROM 0x460B8-0x46100).
TILE_MARKER_PICTURE = 0x8001

# ``getrandom(3)`` picks the invulnerable-food picture from a three-word ROM
# table at 0x58F20 (doc/04 sec 5.4; ROM 0x46150-0x46168). Read through gex's
# generic code-ROM reader and cached, like the level-flags table below --
# never transcribed by hand.
_FOOD_INVULN_PICTURES_ADDR = 0x58F20
_FOOD_INVULN_PICTURES_COUNT = 3
_food_invuln_pictures: tuple[int, ...] | None = None

# challenge_target_object_types, ROM 0x57056 -- one generator type selected by
# each challenge code 0x50-0x5D. maze_new_level_setup 0x43C20-0x43D10 turns
# every matching generator into an exit and removes the other eligible ones.
_CHALLENGE_TARGET_OBJECT_TYPES = (
    0x2C, 0x2A, 0x2A, 0x29, 0x2D, 0x28, 0x2B,
    0x2D, 0x28, 0x2C, 0x29, 0x2A, 0x2A, 0x2B,
)
_CHALLENGE_FIRST = 0x50
_CHALLENGE_LAST = 0x5D
_SECRET_MAZE_FIRST = 0x73
_CHALLENGE_MONSTER_FIRST = 0x13
_CHALLENGE_MONSTER_LAST = 0x18
_CHALLENGE_GENERATOR_FIRST = 0x28
_CHALLENGE_GENERATOR_LAST = 0x2D
_CHALLENGE_HIDDEN_POTION_BASE = 0xA728
_LFLAG4_TRAPS_RANDOM = 0x08
_TRAP_TYPE_FIRST = int(MazeObjIds.TILE_TRAP1)
_TRAP_TYPE_COUNT = 3
_ADAPTIVE_FOOD_PICTURE = 0x277B


def _food_invuln_pictures_read() -> tuple[int, ...]:
    global _food_invuln_pictures
    if _food_invuln_pictures is None:
        raw = coderom_get_bytes(
            _FOOD_INVULN_PICTURES_ADDR, _FOOD_INVULN_PICTURES_COUNT * 2
        )
        _food_invuln_pictures = struct.unpack(f">{_FOOD_INVULN_PICTURES_COUNT}H", raw)
    return _food_invuln_pictures


def _dragon_suppressed(state: GameState, object_type: int) -> bool:
    """Dragons never spawn from maze data before level 12 of a normal game.

    ROM 0x45E6A-0x45E8A: type 0x3C with ``game_mode == 0``,
    ``levelnum_current < 12`` and the level not the 9999 sentinel is written
    as empty -- ``maze_place_object`` returns ``start_slot + count`` without
    touching a single array.
    """
    return (
        object_type == MazeObjIds.MONST_DRAGON
        and state.game_mode == GameMode.NORMAL
        and state.levelnum_current < 12
        and state.levelnum_current != LEVEL_SENTINEL
    )


def maze_place_object(state: GameState, start_slot: int, object_type: int, count: int) -> int:
    """``maze_place_object`` (0x45E40): create ``count`` MOBs of
    ``object_type`` at consecutive slots starting at ``start_slot``,
    returning the next slot (doc/04 section 5.4;
    ``doc/generated/maze_contracts.csv`` row for 0x45E40: "uint16 next slot
    in D0.l"). The original returns this in D0.l; here it is a normal
    Python return.

    Two whole-call escapes come first (ROM 0x45E64-0x45E96): ``TILE_FLOOR``
    places nothing, and a suppressed dragon places nothing -- both still
    return ``start_slot + count``, so a decoder run keeps its cursor.

    Each slot is then run through ``mirror_slot`` before anything is written.
    The returned cursor is always the *unmirrored* one, which is what makes
    the mirror invisible to callers.

    Used both for individual decoded tokens (``count`` always 1 -- gex's
    decoder has already expanded runs into individual cells, see
    ``place_decoded_objects``) and, critically, for ``maze_setupnew``'s
    row-0 fill (``load_level`` below calls this with
    ``count=FIRST_PLAYABLE_SLOT`` to stamp slots 0-31 as solid walls).
    """
    object_type = int(object_type)
    if object_type == MazeObjIds.TILE_FLOOR or _dragon_suppressed(state, object_type):
        return start_slot + count

    for slot in range(start_slot, start_slot + count):
        _place_one(state, _placement_slot(state, slot, object_type), object_type)
    return start_slot + count


def _place_one(state: GameState, slot: int, object_type: int) -> None:
    """Write one object at an already-mirrored slot."""
    if object_type in _SOLID_WALL_MARKERS:
        _write_marker(state, slot, object_type, WALL_MARKER_PICTURE)
    elif object_type in _TILE_MARKERS:
        _write_marker(state, slot, object_type, TILE_MARKER_PICTURE)
    else:
        _create_generic(state, slot, object_type)


def maze_randomplace(state: GameState, object_type: int) -> int:
    """0x42E9A -- place one pickup in the ROM's deterministic empty-cell walk."""
    object_type = int(object_type)
    slot = state.getrandom(0x3E0) + FIRST_PLAYABLE_SLOT
    while slot < FIRST_PLAYABLE_SLOT or state.mobs.picture[slot]:
        slot = (slot + 0x51) & 0x3FF
    picture = placement_base_picture(object_type)
    if object_type == int(MazeObjIds.HIDDENPOT):
        picture = 0xA728 + (state.getrandom(6) << 2)
    hpos, vpos = placement_geometry(object_type, slot)
    state.mobs.create(slot, picture, hpos, vpos, object_type, 0)
    return slot


def place_deferred_thief_pickups(state: GameState) -> list[int]:
    """0x44166-0x441A6 -- restore loot carried off on the previous level."""
    placed: list[int] = []
    if state.mazenum_current >= 0x73:
        return placed
    state.special_bonus_score = 100
    if state.mugger_item_nextlevel:
        placed.append(maze_randomplace(state, MazeObjIds.FOOD_INVULN))
    if state.thief_item_nextlevel != 0x7D30:
        state.special_bonus_score = state.thief_item_nextlevel >> 6
        placed.append(maze_randomplace(
            state, state.thief_item_nextlevel & 0x3F,
        ))
    return placed


def _remove_random_food(state: GameState, count: int) -> list[int]:
    """maze_scan_objects(count), 0x43D8C -- remove up to count food MOBs."""
    removed: list[int] = []
    food_types = {
        int(MazeObjIds.FOOD_DESTRUCTABLE),
        int(MazeObjIds.FOOD_INVULN),
    }
    foods = [
        slot for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.picture))
        if state.mobs.obj_type(slot) in food_types
    ]
    count = min(max(0, count), len(foods))
    remaining_ahead = len(foods)
    cursor = 0
    while count:
        choice_window = remaining_ahead // count
        choice = state.getrandom(choice_window)
        selected = cursor + choice
        slot = foods[selected]
        state.mobs.unlink_and_clear(slot)
        removed.append(slot)
        # maze_scan_objects keeps its A2 sweep pointer after the selected food.
        # Foods passed over cannot be selected by a later iteration.
        remaining_ahead -= choice + 1
        cursor = selected + 1
        count -= 1
    return removed


def maze_addrandompickups(
    state: GameState, enable_random_pickups: bool,
) -> list[int]:
    """0x43F68 -- add/remove the level's complete random pickup set."""
    if state.mazenum_current >= 0x73:
        state.random_pickups_setup_done = True
        return []

    placed: list[int] = []

    # The guaranteed hidden-potion cadence begins at level 6 and reloads its
    # next-level countdown to three after placement.
    if state.level_next_potion == 0 and state.levelnum_current >= 6:
        placed.append(maze_randomplace(state, MazeObjIds.HIDDENPOT))
        state.level_next_potion = 3

    pickup_delta = state.level_flags_3 & 0x07
    active = max(0, min(int(state.level_players_active), 4))
    difficulty = (state.game_settings & 0xE0) >> 5
    character_index = 1

    if state.mazenum_current < 0x68 and enable_random_pickups:
        if active == 1:
            player_index = next(
                (
                    index for index in range(len(state.players) - 1, -1, -1)
                    if state.players[index].mob_slot
                ),
                0,
            )
            character_index = int(state.players[player_index].character) & 0x03

            if character_index == 2:  # Wizard
                draw = state.getrandom(4)
                if difficulty > 4:
                    pickup_delta -= 2 if draw <= 8 - difficulty else 3
                else:
                    pickup_delta -= 1 if draw <= 4 - difficulty else 2
            elif character_index == 0:  # Warrior
                draw = state.getrandom(4)
                if difficulty >= 4:
                    pickup_delta -= 1 if draw <= 7 - difficulty else 2
                elif draw > 3 - difficulty:
                    pickup_delta -= 1
            elif character_index == 3 and difficulty >= 4:  # Elf
                if state.getrandom(4) > 6 - difficulty:
                    pickup_delta -= 1
        else:
            character_index = 1
            if active == 2:
                if state.getrandom(4) > 7 - difficulty:
                    pickup_delta -= 1
            elif active == 3:
                pickup_delta += 1
            elif active == 4:
                pickup_delta += 2

        class_bonus = (3, 0, 4, 0)[character_index]
        spawn_bonus = state.spawn_probability_bonus & 0xFF
        if spawn_bonus & 0x80:
            spawn_bonus -= 0x100
        excess = spawn_bonus - class_bonus
        if excess > 0:
            pickup_delta -= excess >> 2
            if state.getrandom(4) < (excess & 3):
                pickup_delta -= 1

    if pickup_delta < 0:
        _remove_random_food(state, -pickup_delta)
    else:
        for _ in range(pickup_delta):
            placed.append(maze_randomplace(state, MazeObjIds.FOOD_DESTRUCTABLE))

    placed.extend(place_deferred_thief_pickups(state))

    # From level 3 onward, a pair of independent draws can add one authored
    # special pickup. The second draw selects slow food versus a potion.
    if state.levelnum_current >= 3 and state.getrandom(0x40) < 0x18:
        if state.getrandom(0x40) < 0x20:
            slot = maze_randomplace(state, MazeObjIds.POT_DESTRUCTABLE)
            state.mobs.picture[slot] = 0x20FC
        else:
            slot = maze_randomplace(state, MazeObjIds.FOOD_DESTRUCTABLE)
            state.mobs.picture[slot] = 0x25ED
        placed.append(slot)

    state.random_pickups_setup_done = True
    return placed


def _write_marker(state: GameState, slot: int, object_type: int, picture: int) -> None:
    """Stamp a marker straight into the five arrays (ROM 0x46012-0x460B4).

    No ``mob_create``, so no depth-chain membership: walls and floor markers
    are drawn by the playfield layer, and a maze's several hundred of them
    would otherwise swamp the one list every per-frame chain walk traverses.
    Any previous occupant is unlinked first, exactly as
    ``mob_place_tile`` (0x5F310) does.
    """
    mobs = state.mobs
    mobs.unlink(slot)
    x, y = coords.slot_to_pixels(slot)
    mobs.picture[slot] = picture
    mobs.hpos[slot] = coords.encode_hpos(x)
    mobs.vpos[slot] = coords.encode_vpos_at_y(y)
    mobs.set_obj_type(slot, object_type)
    mobs.set_state(slot, 0)


def placement_picture(state: GameState, object_type: int) -> int:
    """The ``mob_picture`` a decoded object of ``object_type`` is created with.

    From the master ``mazeobj_base_picture_tbl`` (0x5868C, doc/05 §5.2) via
    gex's ``objparams.base_picture``, except for invulnerable food, whose
    picture is one of three drawn with ``getrandom(3)`` (ROM 0x46150).

    ``PICTURE_MARKER`` (0x8001) entries reaching here belong to types the ROM
    would have stamped as markers; they are left at picture 0 for the reason
    given on ``_TILE_MARKERS``.
    """
    if object_type == MazeObjIds.FOOD_INVULN:
        # The draw happens even when the table cannot be read, so the shared
        # RNG stream stays in step with the real game either way (PLAN.md's
        # "route randomness through state.getrandom()" rule).
        variant = state.getrandom(_FOOD_INVULN_PICTURES_COUNT)
        try:
            return _food_invuln_pictures_read()[variant]
        except GexError:
            return base_picture(object_type)

    pic = base_picture(object_type)
    return 0 if pic == PICTURE_MARKER else pic


def placement_base_picture(object_type: int) -> int:
    """The literal mazeobj_base_picture_tbl entry, without placement RNG."""
    return base_picture(object_type)


def placement_geometry(object_type: int, slot: int) -> tuple[int, int]:
    """``(hpos, vpos)`` words for a decoded object -- ROM 0x4617C-0x461CC.

    Three of the four master parameter tables meet here:

      * ``mazeobj_hsize_tier_tbl`` (0x5864C) is the low nibble OR'd into hpos.
        doc/08 corrects its name: that nibble is the **MOB palette number**,
        and for a monster it is simultaneously its health tier -- which is why
        ``shots``, ``monsters`` and ``potions`` all read the hpos nibble as
        remaining health. Placing monsters without it left every maze-placed
        creature at tier 0.
      * ``mazeobj_vpos_offset_tbl`` (0x5860C) is the packed size: bits 5-3
        width-1, bits 2-0 height-1. Monsters are 3x3 tiles, pickups 2x2, the
        dragon 4x4.
      * ``mazeobj_hpos_correction_tbl`` (0x5858C) centers a sprite wider than
        its cell. Its entries are native hpos field units -- the same units
        gauntpy stores -- so a correction is subtracted from the word
        directly; the one value that occurs, 512, is 4 px, exactly half the
        overhang of a 24 px sprite in a 16 px cell. Marker types skip it: the
        ROM's marker branch uses a fixed word instead, so their table entries
        are dead data.

    Vertically the ROM stores ``(31 - row) * 16`` px with no per-type addend at
    all -- its V field counts up from the playfield floor, which makes the
    stored value the cell's *bottom* edge, and gauntpy stores exactly that
    word. Whether a taller sprite then hangs upward from that edge is the
    display hardware's business, and ``coords.sprite_top_y`` is where the
    renderer settles it. Only the packed size travels from
    ``mazeobj_vpos_offset_tbl``; its position bits are zero for every one of
    the 64 types, so nothing is being dropped.
    """
    size = vpos_offset(object_type) & 0x3F
    width = ((size >> 3) & 0x07) + 1
    height = (size & 0x07) + 1

    x, y = coords.slot_to_pixels(slot)
    hpos = coords.encode_hpos(x, hsize_tier(object_type) & 0x0F)
    if object_type not in _ROM_MARKER_TYPES:
        hpos = (hpos - hpos_correction(object_type)) & 0xFFFF

    return hpos, coords.encode_vpos_at_y(y, width, height)


def _create_generic(state: GameState, slot: int, object_type: int) -> None:
    """``mob_create`` one decoded object: picture, geometry, type (ROM 0x46260).

    Slot 0 is never linked into the depth chain: ``constants.NULL_SLOT`` is
    0, the chain's own terminator/"empty" sentinel (``mob.py``'s
    ``depth_list_head`` and every ``next``/``prev`` pointer use 0 to mean
    "nothing here"), so inserting a real record *at* slot 0 makes the chain
    unable to tell "list is empty" from "slot 0 is the head" and corrupts
    traversal. Slot 0 is inside the row-0 wall fill, which the original
    stamps as a marker anyway, so nothing reaches here with slot 0 in
    practice -- the guard is belt and braces.

    Dragons also reserve the other three cells of their 2x2 footprint exactly
    as 0x46206-0x4625C does before creating the primary record.
    """
    hpos, vpos = placement_geometry(object_type, slot)
    picture = placement_picture(state, object_type)
    # objects.c seeds ordinary monsters with ROM direction 4 (down). The
    # monster subsystem's internal compass is rotated by two, so that is 2.
    mob_state = 2 if (
        int(MazeObjIds.MONST_GHOST)
        <= object_type
        <= int(MazeObjIds.MONST_IT)
    ) else 0
    if (object_type == int(MazeObjIds.MONST_SUPERSORC)
            and state.levelnum_current != LEVEL_SENTINEL
            and state.game_mode != int(GameMode.LEGEND)):
        hpos |= 0x10
        picture = 0x1709
    if object_type == int(MazeObjIds.MONST_DRAGON):
        row = slot & 0x3E0
        right = row | ((slot + 1) & 0x1F)
        for reserved in ((slot - 0x20) & 0x3FF, right,
                         (right - 0x20) & 0x3FF):
            state.mobs.unlink_and_clear(reserved)
            x, y = coords.slot_to_pixels(reserved)
            state.mobs.picture[reserved] = 0x8002
            state.mobs.hpos[reserved] = coords.encode_hpos(x)
            state.mobs.vpos[reserved] = coords.encode_vpos_at_y(y, 2, 2)
            state.mobs.set_obj_type(reserved, object_type)
            state.mobs.set_state(reserved, 0)
    state.mobs.create(
        slot,
        picture,
        hpos=hpos,
        vpos=vpos,
        obj_type=object_type,
        state=mob_state,
        link_into_chain=slot != 0,
    )
    if object_type == int(MazeObjIds.MONST_DRAGON):
        from .subsystems.dragon import setup_dragon_segments

        setup_dragon_segments(state, slot)


def _prepare_secret_challenge(state: GameState) -> None:
    """0x43C20-0x43D10 -- replace secret-maze actors and create its exits."""
    if state.mazenum_current < _SECRET_MAZE_FIRST:
        return
    task = int(state.secret_trick_id)
    if not _CHALLENGE_FIRST <= task <= _CHALLENGE_LAST:
        return

    target_type = _CHALLENGE_TARGET_OBJECT_TYPES[task - _CHALLENGE_FIRST]
    for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link)):
        object_type = state.mobs.obj_type(slot)
        if _CHALLENGE_MONSTER_FIRST <= object_type <= _CHALLENGE_MONSTER_LAST:
            picture = (
                _CHALLENGE_HIDDEN_POTION_BASE
                + (object_type - _CHALLENGE_MONSTER_FIRST) * 4
            )
            state.mobs.unlink_and_clear(slot)
            hpos, vpos = placement_geometry(int(MazeObjIds.HIDDENPOT), slot)
            state.mobs.create(
                slot, picture, hpos, vpos, int(MazeObjIds.HIDDENPOT), 0,
            )
            set_cell_descriptor(state, slot, int(MazeObjIds.HIDDENPOT))
            continue
        if not _CHALLENGE_GENERATOR_FIRST <= object_type <= _CHALLENGE_GENERATOR_LAST:
            continue

        state.mobs.unlink_and_clear(slot)
        replacement = (
            int(MazeObjIds.EXIT)
            if object_type == target_type
            else int(MazeObjIds.TILE_FLOOR)
        )
        if replacement == int(MazeObjIds.EXIT):
            _place_one(state, slot, replacement)
        set_cell_descriptor(state, slot, replacement)


def _randomize_trap_types(state: GameState) -> None:
    """0x439B0-0x43A8E -- rotate type-10/11/12 trap identities together."""
    if not state.level_flags_4 & _LFLAG4_TRAPS_RANDOM:
        return
    rotation = state.getrandom(_TRAP_TYPE_COUNT)
    for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link)):
        object_type = state.mobs.obj_type(slot)
        if not _TRAP_TYPE_FIRST <= object_type < _TRAP_TYPE_FIRST + _TRAP_TYPE_COUNT:
            continue
        randomized = _TRAP_TYPE_FIRST + (
            object_type - _TRAP_TYPE_FIRST + rotation
        ) % _TRAP_TYPE_COUNT
        state.mobs.set_obj_type(slot, randomized)
        data = getattr(state.maze, "data", None)
        if data is not None:
            row, col = coords.unpack_slot(slot)
            data[(col, row)] = randomized


def _mark_adaptive_food(state: GameState) -> None:
    """0x43AF0-0x43B5A -- choose one authored food for adaptive healing."""
    if state.mazenum_current >= _SECRET_MAZE_FIRST or state.levelnum_current <= 6:
        return
    food_types = {
        int(MazeObjIds.FOOD_DESTRUCTABLE),
        int(MazeObjIds.FOOD_INVULN),
    }
    foods = [
        slot for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link))
        if state.mobs.obj_type(slot) in food_types
    ]
    if not foods:
        return
    slot = foods[state.getrandom(len(foods))]
    state.mobs.picture[slot] = _ADAPTIVE_FOOD_PICTURE
    state.mobs.set_obj_type(slot, int(MazeObjIds.FOOD_DESTRUCTABLE))
    data = getattr(state.maze, "data", None)
    if data is not None:
        row, col = coords.unpack_slot(slot)
        data[(col, row)] = int(MazeObjIds.FOOD_DESTRUCTABLE)


def postdecode_level_setup(state: GameState) -> None:
    """Apply the shared post-playfield portion of maze_new_level_setup."""
    _randomize_trap_types(state)
    from .subsystems.maze_objects import setup_random_walls

    setup_random_walls(state)
    _mark_adaptive_food(state)


def place_decoded_objects(state: GameState, maze: Maze) -> None:
    """Populate ``MobTable`` from gex's decoded ``Maze.data``: slot number
    is the packed cell address, so placement is arithmetic, not a search
    (task brief; doc/04 sections 5.3-5.4).

    gex keys ``Maze.data`` by ``(x, y)`` = ``(col, row)`` -- see
    ``gex.mazedecode.index2xy``. gex's own linear decode cursor is already
    ``row * 32 + col``, which is exactly ``coords.pack_slot(row, col)``, so
    no coordinate translation beyond a swap is needed. Cells are placed in
    ascending slot order so that the depth chain is built the way the
    original's decoder builds it, front to back.

    Row 0 (``row == 0``, i.e. slots 0-31) is skipped: gex's
    ``maze_decompress`` bakes a row-0 wall border directly into
    ``Maze.data`` as a decode-completeness convenience
    (``mazedecode.py``: ``maze.data.update({(i, 0): WALL_REGULAR ...})``
    before its token loop even starts), but the *real* ``maze_decode``
    (0x4C1BC) never emits row 0 at all -- "the tile cursor starts at slot
    0x20 (row 0 is not emitted by this function)", doc/04 section 5.3. That
    row is instead filled by a separate, later call
    (``maze_place_object(0, 2, 0x20)``, doc/04 sections 5.2-5.3), which
    ``load_level`` issues itself below. Placing it here too would
    double-create slots 0-31 -- and row 0 has no mirror image, so it must not
    go through the mirroring path either.
    """
    cells = sorted(
        ((coords.pack_slot(row, col), object_type)
         for (col, row), object_type in maze.data.items()
         if row != 0),
    )
    for slot, object_type in cells:
        maze_place_object(state, slot, object_type, 1)


def select_player_start_slot(state: GameState) -> None:
    """Port maze_scan_objects(-1): select a start and process every loser."""
    starts = [
        slot for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link))
        if state.mobs.obj_type(slot) == int(MazeObjIds.PLAYERSTART)
    ]
    state.maze_player_start_slot = 0
    if not starts:
        return
    selected = starts[state.getrandom(len(starts))]
    state.maze_player_start_slot = selected
    data = getattr(state.maze, "data", None)
    for slot in starts:
        if slot != selected and state.level_flags_4 & 0x40:
            state.mobs.hpos[slot] |= 0x10
            continue
        state.mobs.unlink_and_clear(slot)
        if data is not None:
            row, col = coords.unpack_slot(slot)
            data.pop((col, row), None)


# ---------------------------------------------------------------------------
# maze_load_pickup_config (0x436FE) -- level flags load & randomization
# ---------------------------------------------------------------------------

def _split_flags(longword: int) -> tuple[int, int, int, int]:
    """32-bit level-flags longword -> its 4 big-endian bytes (LFLAG1..4)."""
    longword &= 0xFFFFFFFF
    return (
        (longword >> 24) & 0xFF,
        (longword >> 16) & 0xFF,
        (longword >> 8) & 0xFF,
        longword & 0xFF,
    )


def _join_flags(b1: int, b2: int, b3: int, b4: int) -> int:
    """Inverse of ``_split_flags``."""
    return ((b1 & 0xFF) << 24) | ((b2 & 0xFF) << 16) | ((b3 & 0xFF) << 8) | (b4 & 0xFF)


# get_random_maze_flags (0x436CC): a 13-entry, 4-byte-per-entry ROM table at
# 0x57012 (doc/04 sec 5.5; doc/05_data_reference.md sec 5.2 names the size
# "13 x 4B" but -- out of WP-3's doc-read scope -- does not transcribe the
# values). Per PLAN.md sec 8 ("when the docs and the ROM disagree, the ROM
# wins") and the standing instruction to verify rather than invent, the
# table is read directly from the game ROM via gex's existing generic code
# -ROM reader (never re-derived or hand-copied). Read once and cached --
# it is fixed ROM content, not per-maze state.
_RANDOM_MAZE_FLAGS_ADDR = 0x57012
_RANDOM_MAZE_FLAGS_COUNT = 13
_random_maze_flags_table: tuple[int, ...] | None = None


def _random_maze_flags_table_read() -> tuple[int, ...]:
    global _random_maze_flags_table
    if _random_maze_flags_table is None:
        raw = coderom_get_bytes(_RANDOM_MAZE_FLAGS_ADDR, _RANDOM_MAZE_FLAGS_COUNT * 4)
        _random_maze_flags_table = struct.unpack(f">{_RANDOM_MAZE_FLAGS_COUNT}I", raw)
    return _random_maze_flags_table


def get_random_maze_flags(state: GameState) -> int:
    """``get_random_maze_flags`` (0x436CC): selects a random entry from the
    13-entry ROM table at 0x57012 via ``getrandom(13)``. If LFLAG4 bit 2
    (TrapsLocal) is set and the selected entry is 0x80, overrides to 0x2
    (doc/04 sec 5.5) -- verified directly against the game ROM: entry 1 is
    0x80 (``LFLAG4_PLAYER_OFFSCREEN``) and entry 3 is 0x2
    (``LFLAG4_SHOTS_HURT``), consistent with every other populated entry
    being a single set bit somewhere across LFLAG1/2/4 (e.g. 0x1000000 =
    ``LFLAG1_ODDANGLE_GHOSTS``, 0x10000 = ``LFLAG2_FAST_GHOSTS``).
    """
    table = _random_maze_flags_table_read()
    result = table[state.getrandom(_RANDOM_MAZE_FLAGS_COUNT)]
    if state.level_flags_4 & LFLAG4_TRAPS_LOCAL and result == 0x80:
        result = 0x2
    return result


def maze_load_pickup_config(state: GameState, maze: Maze) -> None:
    """``maze_load_pickup_config`` (0x436FE): assemble the maze header's
    four level-flags bytes into the level-flags longword, then randomize
    (doc/04 sec 5.5; doc/06 sec 4/8).

    gex has already assembled header bytes 1-4 into ``maze.flags``
    (``mazedecode.maze_decompress``: ``struct.unpack(">I", compressed[1:5])``)
    -- this function stores that (as 4 separate bytes, matching the RAM
    layout at 0x90491C-0x90491F: ``wrap_h``/``wrap_v`` below read
    ``level_flags_4`` as a standalone byte exactly like the pre-existing
    field comments in state.py do) and applies the documented
    randomization on top.
    """
    b1, b2, b3, b4 = _split_flags(maze.flags)
    state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4 = b1, b2, b3, b4

    # The whole randomization block is skipped on the level==9999 sentinel and
    # in attract mode (game_mode < 0). ROM 0x4374C-0x43760: cmpi.w #0x270F on
    # levelnum, then tst.w/bge on game_mode -- verified by disassembly. In
    # those cases the base header flags stored above are the final value.
    if state.levelnum_current != LEVEL_SENTINEL and state.game_mode >= 0:
        # LFLAG1 bits 2-3 (longword bits 26-27) XOR'd with getrandom(4), every
        # level (doc/04 sec 5.5; ROM 0x43764-0x43772). These are the two
        # placement mirror bits -- see MIRROR_H_FLAG/MIRROR_V_FLAG -- so this
        # single draw is what re-flips the maze on each new level.
        state.level_flags ^= (state.getrandom(4) << 2) & 0x0C

        longword = _join_flags(
            state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4
        )

        mazenum = state.mazenum_current
        levelnum = state.levelnum_current

        if 5 <= mazenum <= 101:
            # doc/04 sec 5.5, verified by disassembly at ROM 0x43774-0x437D4:
            # level%400 > 297 -> get_random_maze_flags() then +0x30
            # (WrapV|WrapH) unless LFLAG4 bit 2 (TrapsLocal); > 200 -> random
            # flags only; > 103 -> +0x30 unless TrapsLocal. The >103 TrapsLocal
            # gate (ROM 0x437C8: btst #2,$3(a3); bne) was missing from the
            # earlier reading -- it is the same gate as the >297 tier.
            depth = levelnum % 400
            if depth > 297:
                extra = get_random_maze_flags(state)
                if not (state.level_flags_4 & LFLAG4_TRAPS_LOCAL):
                    extra |= LFLAG4_WRAP_V | LFLAG4_WRAP_H
                longword |= extra
            elif depth > 200:
                longword |= get_random_maze_flags(state)
            elif depth > 103:
                if not (state.level_flags_4 & LFLAG4_TRAPS_LOCAL):
                    longword |= LFLAG4_WRAP_V | LFLAG4_WRAP_H
        elif 104 <= mazenum <= 114:
            # Treasure mazes: a graduated 3-tier threshold on level%160,
            # exactly parallel to the mazes-5-101 rule -- verified by
            # disassembly at ROM 0x437D6-0x4381A. The doc/04 sec 5.5 summary
            # ("level%160 with 0xB0") named only the top tier; the full rule:
            #   > 120 -> 0xB0 (LFLAG4 offscreen + both wraps)
            #   >  80 -> 0x80 (offscreen only)
            #   >  40 -> 0x30 (both wraps)
            #   <= 40 -> nothing
            depth = levelnum % 160
            if depth > 120:
                longword |= 0x80 | LFLAG4_WRAP_V | LFLAG4_WRAP_H  # 0xB0; 0x80 = PLAYER_OFFSCREEN
            elif depth > 80:
                longword |= 0x80  # LFLAG4_PLAYER_OFFSCREEN
            elif depth > 40:
                longword |= LFLAG4_WRAP_V | LFLAG4_WRAP_H  # 0x30

        state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4 = _split_flags(longword)

    # 0x90491F bits 5/4 -- see the pre-existing field comments in state.py.
    state.wrap_h = bool(state.level_flags_4 & LFLAG4_WRAP_H)
    state.wrap_v = bool(state.level_flags_4 & LFLAG4_WRAP_V)


# ---------------------------------------------------------------------------
# load_level -- the public entry point
# ---------------------------------------------------------------------------

def load_level(state: GameState, level_number: int, maze_number: int | None = None) -> None:
    """Load and set up the maze for ``level_number`` (PLAN.md sec 6 WP-3).

    Owns no main-loop call; it is called at level transitions -- WP-20 boot
    and the front end (``session.main_start_game``), WP-15's exit sequence,
    WP-17's attract demo, and the ``gauntpy-play`` runner all arrive here,
    usually through ``reset_and_load_level`` below.

    Consolidates ``maze_new_level_setup``'s (0x438AE) game-side setup:
    decode and mirrored placement, row-zero fill, start selection, camera snap,
    playfield construction, trap/random-wall/food post-processing, exit-table
    scan, and the secret-challenge transformation.

    (The original calls ``maze_load_pickup_config`` from ``maze_setupnew``
    only for the 9999 sentinel and attract -- ROM 0x44B30-0x44B4E -- and from
    the game-start and level-splash paths otherwise, 0x4521C/0x48556/0x48636.
    Calling it unconditionally here is the same net effect for a single
    consolidated entry point, and it is the only way the flags are set at all
    in normal play.)

    The common post-spawn tail in ``exits._spawn_level_players`` owns thief
    scheduling and party-dependent random pickups. Transporter position-table
    reads are represented by ordered live-MOB scans because packed slot is
    already the stored table value.
    """
    state.levelnum_current = level_number
    state.dialog_once_flags &= ~1                       # 0x438DC
    state.thief_level_setup_done = False
    from .subsystems.maze_objects import select_forcefield_delay_profile
    select_forcefield_delay_profile(state)
    state.level_treasures = 0            # fresh level: reset the bonus tally count
    state.special_bonus_score = 100      # 0x44166, ordinary score-bag value
    state.random_pickups_setup_done = False

    if maze_number is not None:
        # Caller pins a specific maze (attract demo/legend, treasure rooms) that
        # is not the level's fixed maze.
        mazenum = maze_number
    else:
        mazenum = maze_for_level(level_number)
        if mazenum is None:
            # No fixed rule past the opening act (doc/06 sec 3.2) -- trust that
            # the caller (eventually WP-15's exit sequence via WP-20 boot) has
            # already advanced state.mazenum_current. See module docstring
            # "Scope note".
            mazenum = state.mazenum_current
    state.mazenum_current = mazenum

    maze = decode_maze(mazenum)

    maze_load_pickup_config(state, maze)

    # Decode cursor never emits row 0 (doc/04 sec 5.3) -- populate the
    # decoded tokens first, then stamp the reserved row separately, exactly
    # as the original orders it ("Immediately after the decoder returns,
    # maze_setupnew calls maze_place_object(0, 2, 0x20)").
    place_decoded_objects(state, maze)
    maze_place_object(state, 0, MazeObjIds.WALL_REGULAR, FIRST_PLAYABLE_SLOT)
    # Logical maze data remains useful to gameplay/catalog code. The display
    # bridge commits its random texture decisions once into hardware-shaped
    # descriptor RAM; rendering never treats this dictionary as pixels.
    state.maze = mirror_maze(state, maze)
    select_player_start_slot(state)              # maze_scan_objects(-1), 0x4395E
    from .subsystems.camera import scroll_to_slot
    scroll_to_slot(state, state.maze_player_start_slot)  # 0x43974
    from .subsystems.maze_objects import (
        forcefield_segments_setup, maze_forcefield_setup,
    )
    forcefield_segments_setup(state)
    if state.level_flags_3 & 0x08:
        maze_forcefield_setup(state)
    initialize_playfield_ram(state, state.maze)
    from .subsystems.maze_objects import setup_door_graphics
    setup_door_graphics(state)
    postdecode_level_setup(state)                        # 0x439B0-0x43B5A
    # The ROM scans existing exits before its secret-maze transformation, so
    # generated challenge exits are deliberately absent from the position table.
    # Player collision still sees their live marker records.
    from .subsystems.exits import exit_scan_level
    exit_scan_level(state)
    _prepare_secret_challenge(state)

    # maze_new_level_setup step 10: rebuild the exit table from the MOBs just
    # placed (0x43B3A-0x43B9A). It has to live on the common load path, not in
    # each caller: the runner's mid-level drop went straight to load_level, so
    # exit_slots stayed empty, exit_open_id stayed zero, and main_exit_move
    # returned at its first gate -- moving exits never moved. WP-15 owns the
    # scan; this is the call site the ROM puts it at. Function-local because
    # exits.py reaches back into this module for its own reload, and it must
    # run last: the scan reads the placed EXIT MOBs and the level flags.


def reset_and_load_level(
    state: GameState, level_number: int, maze_number: int | None = None
) -> bool:
    """Start a fresh level: drop the old maze's MOBs, reset the active-player
    count, and load ``level_number`` (the ``maze_new_level_setup`` framing --
    the ROM rebuilds the whole MOB table on a level change). Pass
    ``maze_number`` to pin a specific maze (attract demo/legend, treasure rooms)
    instead of the level's fixed maze.

    Returns ``True`` on success. On a decode failure -- most commonly no ROMs
    configured -- the previous MOB table is restored and ``False`` is returned,
    so callers (the attract->game start, the exit sequence) advance their level
    counters but do not crash a ROM-less environment. Players are re-placed by
    the caller after a successful load.
    """
    old_mobs = state.mobs
    state.mobs = MobTable()
    state.level_players_active = 0
    try:
        load_level(state, level_number, maze_number)
    except MazeError:
        state.mobs = old_mobs
        return False
    return True
