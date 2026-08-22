"""Playfield layer -- the maze (floor, walls, doors, forcefields).

PLAN.md §6 WP-2 step 1: "64x64 grid of 8x8 tiles, column-first, from the
tile descriptors. Camera scroll applied at blit time." The word "tile
descriptors" is the game's own term (``doc/04_game_subsystems.md`` §13.2):
one maze cell is a 2x2 block of 8x8 playfield tiles, four tile-and-palette
words written together by ``write_tile_descriptor`` (0x5E542) whenever a
cell's logical contents change.

**Design decision -- caching, not a per-frame descriptor walk.** The real
hardware's playfield RAM is a persistent 64x64 word table that only changes
when game logic calls ``write_tile_descriptor`` (a wall opens, a door state
changes, a random wall dissolves); the *video* hardware just scans whatever
is currently there, every field, driven by the two scroll registers
(``doc/01_hardware.md`` §10). We reproduce that division of labour: this
module decodes the maze **once** into a cached 512x512 RGBA raster (the
"tile descriptors", rendered), and ``draw_playfield`` on every frame is a
plain crop-and-paste of the scrolled window out of that cache -- no
per-tile work in the hot path. A future package that lets terrain change at
runtime (WP-11, the living maze) invalidates and rebuilds the cache when it
does, exactly as ``refresh_tile_visual`` does for the real 64x64 table.

That only works if a rebuild is a *rebuild* and not a redraw of a different
world, so the decode is pure: it reads the maze and writes nothing back, the
random floor-texture stream included (``build_rand``). Rebuilding after a wall
dissolves re-textures nothing the wall did not touch, and two frames of an
unchanged state are the same frame whether or not a cache was kept.

**Design decision -- terrain only, not gex's whole-maze preview.**
``python-gex/src/gex/pfrender.py`` (``genpfimage``) is a maze-*preview*
tool: it bakes a maze's starting monsters, keys, potions, treasure, and
power-ups into one flat PNG, because that is what a human proofing 117
mazes wants to see. It is **not** how the hardware renders during play.
``doc/01_hardware.md`` §4.1 draws the layer line precisely: MOBs are
"players, monsters, shots, animations" -- the *dynamic* half. And §8.7
confirms it structurally: "Dynamic maze objects use slots 30-1023" of the
same MOB table the renderer's MOB layer (``render/mobs.py``) walks. A key
lying on the floor is a MOB, not a playfield tile, because it has to
disappear the instant a player walks over it, and playfield tiles don't
animate per-object like that.

So this module reuses gex's *terrain* stamp constructors (``wall_get_stamp``,
``door_get_stamp``, ``ff_get_stamp``, the floor/wall dot tables) -- the part
of ``gex.pfrender`` that computes wall connectivity and floor texture --
but filters out every object type gex's own dispatch would draw as an
"item" (monsters, generators, keys, potions, treasure, power-ups, the
transporter pad). Those are drawn from the live ``MobTable`` by
``render/mobs.py`` once a maze's objects are placed into it (WP-3).

**The exit is neither.** It is not baked into the world raster and it is not
drawn as a MOB: its marker identifies the live cell, while the visible 2x2
descriptor is stamped into playfield RAM. ``draw_exit_animation`` therefore
draws every live exit marker as the settled descriptor and overlays the moving
exit's open/close script when ``main_exit_move`` is active.

This split is also why the acceptance test (``tests/test_render.py``)
cannot byte-for-byte match a full ``genpfimage`` PNG: gex's reference draws
strictly more (the baked-in starting objects). The test instead restricts
its pixel comparison to cells whose content is terrain in both renderers --
see the test module's docstring for the exact method.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Protocol

from gex.adjacency import (
    checkffadj4,
    checkwalladj3,
    checkwalladj8,
    ff_make_map,
    whatis,
)
from gex.floor import floor_get_stamp
from gex.items import item_get_stamp
from gex.palettes import (
    GAUNTLET_PALETTES, IRGB, S_COLORS_1, S_COLORS_2,
    palette_make_special,
)
from gex.rand import SeededRandom
from gex.render import Stamp, blank_image, write_stamp_to_image
from gex.wall import ff_get_stamp, wall_get_destructable_stamp, wall_get_stamp

from ..constants import MazeObjIds
from ..coords import PF_COLS, PF_ROWS, WORLD_PIXELS, pack_slot

__all__ = [
    "MAZE_CELLS", "TERRAIN_TYPES", "PlayfieldCache", "ShadowSource",
    "build_playfield_image", "build_playfield_images", "build_rand",
    "draw_playfield", "irgb_to_shadow", "shadow_source_for",
    "EXIT_ANIM_STAGES", "EXIT_ANIM_FRAMES", "EXIT_DESC_TILE_BASE",
    "EXIT_DESC_RECORD", "EXIT_SETTLED_DESC", "EXITTO6_SETTLED_DESC",
    "TRANSPORTER_DESC", "exit_descriptor",
    "draw_animated_floor_tiles", "draw_exit_animation",
    "draw_transporter_tiles", "draw_wall_crumble",
]

#: ``gex.mazedecode.Maze``'s own default seed, restated for the one case where
#: a ``MazeLike`` has no ``rand`` at all (a hand-built test fake) -- see
#: ``build_rand``.
_DEFAULT_MAZE_SEED = 5

#: The maze is a 32x32 cell grid (``coords.py``), each cell a 2x2 block of
#: the 64x64 8x8-tile playfield (``PF_COLS``/``PF_ROWS`` = 64 = 32*2).
MAZE_CELLS = 32

#: Special-floor overlays that still count as "terrain" -- they are
#: hazards baked into the floor, not objects sitting on it.
#: ``gex.pfrender._FLOOR_TILE_INFO`` (same set, restated here since that
#: name is private to gex's module).
_FLOOR_TILE_INFO: dict[int, tuple[str, int]] = {
    MazeObjIds.TILE_STUN: ("stun", 0),
    MazeObjIds.TILE_TRAP1: ("trap", 1),
    MazeObjIds.TILE_TRAP2: ("trap", 2),
    MazeObjIds.TILE_TRAP3: ("trap", 3),
}

#: Wall types rendered through the adjacency-driven wall stamp, with their
#: corner-dot decoration count. Mirrors ``gex.pfrender._WALL_TILE_DOTS``.
_WALL_TILE_DOTS: dict[int, int] = {
    MazeObjIds.WALL_REGULAR: 0,
    MazeObjIds.WALL_TRAPCYC1: 1,
    MazeObjIds.WALL_TRAPCYC2: 2,
    MazeObjIds.WALL_TRAPCYC3: 3,
    MazeObjIds.WALL_RANDOM: 4,
}

#: Everything this module will draw as part of the maze itself. Anything
#: not in this set is a dynamic MOB and is left to ``render/mobs.py`` --
#: see the module docstring's "terrain only" decision.
TERRAIN_TYPES: frozenset[int] = frozenset(
    {MazeObjIds.TILE_FLOOR, MazeObjIds.WALL_SECRET,
     MazeObjIds.WALL_DESTRUCTABLE, MazeObjIds.FORCEFIELDHUB}
    | set(_FLOOR_TILE_INFO) | set(_WALL_TILE_DOTS)
)

_DOT_POSITIONS: dict[int, list[tuple[int, int]]] = {
    1: [(7, 7)],
    2: [(9, 5), (5, 9)],
    3: [(7, 7), (9, 5), (5, 9)],
    4: [(9, 5), (5, 9), (5, 5), (9, 9)],
}


class MazeLike(Protocol):
    """The subset of ``gex.mazedecode.Maze`` this module reads. Spelled out
    so tests can hand-build a minimal fake without a real decode."""

    data: dict
    flags: int
    wallpattern: int
    wallcolor: int
    floorpattern: int
    floorcolor: int
    rand: object


def irgb_to_shadow(irgb: int) -> int:
    """The hardware's playfield-shadow-palette transform, applied to one
    16-bit IRGB color word.

    Verified by disassembly (capstone, ``row76.bin``): the game builds the
    128-entry shadow palette bank (color RAM 0x910400) from the playfield
    bank (0x910500) in the copy routine at 0x5FD80 -- for each entry,
    ``shadow = color - 0x7000`` (subtract 7 from the intensity nibble, bits
    15-12, leaving R/G/B alone); if that borrows (source intensity <= 6) the
    RGB nibbles are kept and intensity is forced to 1. A MOB pixel of index 1
    shows the underlying playfield pixel through this palette
    (``doc/01_hardware.md`` §4/§6). See that doc's §6 note for the full
    derivation. Not an RGB halving and not a "subtract 128".
    """
    if irgb >= 0x7000:            # bcc: no borrow, subtract 7 from I nibble
        return irgb - 0x7000
    return (irgb & 0x0FFF) | 0x1000  # borrow: keep RGB, force intensity = 1


def _shadow_palette(pal):
    """Shadow-palette version of a gex ``Palette`` (list of ``IRGB``)."""
    from gex.palettes import IRGB
    return [IRGB(irgb_to_shadow(c.irgb)) for c in pal]


def _write_stamp(img, stamp, xloc: int, yloc: int, palette) -> None:
    """Blit a stamp with an explicit palette (gex's ``write_stamp_to_image``
    always reads the global ``GAUNTLET_PALETTES``; the shadow pass needs a
    per-stamp shadow palette instead, so it goes tile by tile through gex's
    palette-taking ``write_tile_to_image``)."""
    from gex.render import write_tile_to_image
    for idx, tile in enumerate(stamp.data):
        ty, tx = divmod(idx, stamp.width)
        write_tile_to_image(img, tile, palette, stamp.trans0, xloc + tx * 8, yloc + ty * 8)


def _dotat(img, xloc: int, yloc: int, rgba) -> None:
    pixels = img.load()
    w, h = img.size
    for y in range(2):
        for x in range(2):
            px, py = xloc + x, yloc + y
            if 0 <= px < w and 0 <= py < h:
                pixels[px, py] = rgba


def _render_dots(img, xloc: int, yloc: int, count: int, rgba) -> None:
    for dx, dy in _DOT_POSITIONS.get(count, []):
        _dotat(img, xloc + dx, yloc + dy, rgba)


def _terrain_stamp(maze: MazeLike, x: int, y: int, obj: int, rand) -> tuple[Stamp | None, int]:
    """Terrain-only equivalent of ``gex.pfrender._get_stamp_for_obj``: same
    dispatch, restricted to ``TERRAIN_TYPES``. Returns (stamp, dot count).

    ``rand`` is the build's own texture stream (``build_rand``), never
    ``maze.rand`` -- see ``build_playfield_images``.
    """
    if obj in _FLOOR_TILE_INFO:
        ptype_override, dots = _FLOOR_TILE_INFO[obj]
        adj = checkwalladj3(maze, x, y) + rand.intn(4)
        return dataclasses.replace(
            floor_get_stamp(maze.floorpattern, adj, maze.floorcolor),
            ptype=ptype_override, pnum=0,
        ), dots

    if obj == MazeObjIds.WALL_DESTRUCTABLE:
        adj = checkwalladj8(maze, x, y)
        return wall_get_destructable_stamp(maze.wallpattern, adj, maze.wallcolor, rand), 0

    if obj == MazeObjIds.WALL_SECRET:
        adj = checkwalladj8(maze, x, y)
        return wall_get_stamp(
            maze.wallpattern, adj, maze.wallcolor, rand,
        ), 0

    if obj in _WALL_TILE_DOTS:
        adj = checkwalladj8(maze, x, y)
        return wall_get_stamp(maze.wallpattern, adj, maze.wallcolor, rand), _WALL_TILE_DOTS[obj]

    if obj == MazeObjIds.WALL_MOVABLE:
        # A pushwall moves by sub-cell pixels and is therefore drawn from its
        # live MOB H/V record, not baked into the static terrain raster.
        return None, 0

    if obj == MazeObjIds.FORCEFIELDHUB:
        adj = checkffadj4(maze, x, y)
        return ff_get_stamp(adj), 0

    if obj == MazeObjIds.FOOD_INVULN:
        # Not terrain (it's a floor item, drawn by the MOB layer once
        # placed) -- but gex.pfrender's own dispatch for this one object
        # type draws from the maze's random stream (picking which of the
        # three "food" sprites to preview: ``FOODS[maze.rand.intn(3)]``), the
        # only non-terrain branch in gex's whole dispatch table that does.
        # Since every terrain cell's floor-texture variety also comes from
        # that same stream (see ``_floor_stamp`` below), silently
        # skipping this draw would desync every *subsequent* cell's floor
        # texture from gex's reference rendering -- not just this cell's.
        # Consuming (and discarding) the same draw keeps the two streams
        # aligned. This is a real coupling to a gex implementation detail;
        # if gex's dispatch ever gains another rand-consuming non-terrain
        # branch, ``tests/test_render.py``'s golden-image comparison will
        # start failing with mismatches spread past that object's cell, and
        # this is the fix to look for.
        rand.intn(3)
        return None, 0

    return None, 0


def _floor_stamp(
    maze: MazeLike, x: int, y: int, ffmap, rand=None,
    variation: int | None = None,
) -> Stamp:
    adj = checkwalladj3(maze, x, y) if maze.wallpattern < 11 else 0
    if variation is None:
        variation = rand.intn(4)
    stamp = floor_get_stamp(maze.floorpattern, adj + variation, maze.floorcolor)
    if (x, y) in ffmap:
        stamp = dataclasses.replace(stamp, ptype="forcefield", pnum=0)
    return stamp


class _RecordingRand:
    """Record per-cell terrain draws while preserving the shared ROM stream."""

    def __init__(self, source) -> None:  # noqa: ANN001
        self.source = source
        self.calls: list[int] = []

    def intn(self, bound: int) -> int:
        value = self.source.intn(bound)
        self.calls.append(value)
        return value


class _ReplayRand:
    """Replay a cell's original texture draws, with a stable new-cell fallback."""

    def __init__(self, values: tuple[int, ...], slot: int) -> None:
        self.values = list(values)
        self.slot = slot
        self.index = 0

    def intn(self, bound: int) -> int:
        if self.index < len(self.values):
            value = self.values[self.index] % bound
        else:
            # A wall that was inactive during the initial build has no recorded
            # terrain draw. Give it a deterministic slot-local choice without
            # advancing or reshuffling any other cell's texture.
            value = ((self.slot * 0x45D9F3B) ^ (self.index * 0x9E37)) % bound
            self.values.append(value)
        self.index += 1
        return value


def build_rand(maze: MazeLike):
    """The random stream one playfield build may consume: an independent copy
    of ``maze.rand``, taken at its current state and thrown away afterwards.

    **Why a copy.** The floor texture of every cell, and the tile choice of
    every shrub wall, comes from ``maze.rand`` -- gex's own ``pfrender`` does
    the same, which is why the two renderers agree cell for cell. But drawing
    from it *advances* it, and this module rebuilds the whole world raster
    whenever the cache is invalidated: a new level, a wall dissolving, a door
    opening, or simply a caller that did not keep the cache. Consuming the
    maze's own stream made every rebuild come out different from the one
    before it -- the same maze, redrawn, with all 1024 cells re-textured. That
    is not a cache subtlety, it is the renderer not being a function of its
    input: ``render_frame`` twice on an unchanged state produced two different
    pictures.

    Copying gives the build a private stream that starts wherever the maze's
    does and leaves it exactly there, so the raster is a pure function of the
    maze (a *fresh decode* -- ``gex.mazedecode.Maze``'s ``SeededRandom(5)``
    default -- still reproduces gex's reference rendering exactly, because the
    copy starts from that same untouched seed state).

    ``copy.deepcopy`` rather than reading gex's private ``SeededRandom._rng``
    state: gex's PRNG is a wrapper whose internals are its own business, and a
    deep copy is defined behaviour for anything it might hold.
    """
    rand = getattr(maze, "rand", None)
    if rand is None:
        # MazeLike is a protocol -- a hand-built fake in a test may not carry a
        # stream at all. gex's own default is what a fresh decode would have.
        return SeededRandom(_DEFAULT_MAZE_SEED)
    return copy.deepcopy(rand)


def build_playfield_image(maze: MazeLike):
    """Decode ``maze`` into a 512x512 RGBA raster of the whole world
    (``coords.WORLD_PIXELS``), cell (0, 0) at pixel (0, 0) -- no border, no
    wraparound preview column. Compare with
    ``python-gex/src/gex/pfrender.py``'s ``genpfimage``, which offsets
    everything by a cosmetic 16px border and (when a level doesn't wrap)
    draws one extra preview column/row beyond the real 32x32 grid; neither
    exists in playfield RAM on real hardware, so neither is reproduced here.

    Requires ROMs (tile pixel data comes from gex, which reads them
    lazily on first use) -- callers should expect ``gex.roms.GexError`` /
    ``AssetError``-shaped failures the same way any other tile decode does.

    **Boundary connectivity: settled from the ROM.** A neighbour probe that
    steps off one edge of the 32x32 grid lands on the opposite edge. Every
    playfield helper in the game ROM masks both cell coordinates with 0x1F
    before touching the tile table -- the wall/floor predicates
    ``pf_isblankfloor`` (``andi.w #$1f`` at 0x5EA2E/0x5EA34) and
    ``pf_is_connectable_floor_xy`` (0x5EA66/0x5EA6C), the wall renderer
    ``pf_wall_draw`` (0x5EAD4/0x5EADA), ``pf_isdoor`` (0x5F77A/0x5F77E) and
    its caller ``pf_door_update_surrounding_xy`` (0x5F806/0x5F80C), and the
    forcefield ray in ``forcefield_segments_setup`` (0x5340A-0x5340C) -- so the
    rule is uniform across walls, floor texture, doors and forcefields alike,
    and it does not depend on the level's wrap flags. Those predicates also
    short-circuit masked row 0 to "wall" (0x5EA32, 0x5EA6A, 0x5F78C, 0x5EAEA);
    no separate rule is needed because ``maze_decompress`` fills row 0 with
    walls, which ``tests/test_render.py`` verifies for all 117 shipped mazes.

    The rule now lives in ``gex.adjacency.whatis``, which masks both
    coordinates -- so this module gets it for free and there is nothing to
    correct here. It was not always so: gex previously resolved the edge with
    a ``copyedges`` pass that mirrored only the *high* edge and only on a
    non-wrapping axis, and did it by writing phantom column/row 32 cells into
    ``maze.data``. That was reported from here with the addresses above and
    fixed in gex; ``TestPlayfieldEdgeRule`` pins the behaviour from gauntpy's
    side so a regression there cannot silently change what this renders.
    """
    return build_playfield_images(maze)[0]


#: White floor-dot color and its shadow-palette equivalent, precomputed.
_DOT_RGBA = IRGB(0xFFFF).to_rgba()
_DOT_RGBA_SHADOW = IRGB(irgb_to_shadow(0xFFFF)).to_rgba()


def _build_playfield_layers(maze: MazeLike):
    """Build the normal world raster, its **shadow-palette twin** and the
    incremental-cache artifacts in a single decode pass.

    The shadow raster is the same terrain rendered through the half-intensity
    shadow palette (``irgb_to_shadow`` on every color) -- it *is* the hardware
    shadow-palette bank's contribution, precomputed for the whole world. The
    MOB layer samples it wherever a sprite pixel has index 1 (shadow), so the
    shadow shows the true (I−7)-intensity playfield color rather than an
    approximation. Both rasters are produced from one texture stream (the
    stamps are chosen once and drawn to both images), so the shadow raster is
    guaranteed pixel-aligned with the normal one and the floor texture
    randomization can't desync between them.

    **Pure.** The build reads ``maze`` and writes nothing back, including the
    random stream: ``build_rand`` hands it a private copy, so calling this
    twice on the same maze returns the same two rasters, and a rebuild after a
    terrain edit re-textures nothing that the edit did not touch. (The stream
    is shared across cells, in gex's own per-cell order, because that is what
    makes the two renderers agree -- so an edit that changes how many draws its
    own cell consumes still shifts the cells drawn after it. Editing a cell
    into another type of the same kind -- one wall style for another, one trap
    for another -- consumes the same draws and leaves the rest of the world
    pixel-identical.)

    ``build_playfield_images`` exposes the original three-artifact public
    result; ``playfield_cache_for`` retains the floor rasters and per-cell
    texture draws so living-maze changes can restamp only their adjacency ring.
    """
    normal = blank_image(WORLD_PIXELS, WORLD_PIXELS)
    shadow = blank_image(WORLD_PIXELS, WORLD_PIXELS)
    ffmap = ff_make_map(maze)
    rand = build_rand(maze)
    palette_make_special(maze.floorpattern, maze.floorcolor, maze.wallpattern, maze.wallcolor)

    shadow_pal_cache: dict[tuple[str, int], list] = {}

    def shadow_pal(ptype: str, pnum: int):
        key = (ptype, pnum)
        pal = shadow_pal_cache.get(key)
        if pal is None:
            pal = _shadow_palette(GAUNTLET_PALETTES[ptype][pnum])
            shadow_pal_cache[key] = pal
        return pal

    floor_variants = [0] * (MAZE_CELLS * MAZE_CELLS)
    for y in range(MAZE_CELLS):
        for x in range(MAZE_CELLS):
            slot = pack_slot(y, x)
            variation = rand.intn(4)
            floor_variants[slot] = variation
            stamp = _floor_stamp(
                maze, x, y, ffmap, variation=variation,
            )
            write_stamp_to_image(normal, stamp, x * 16, y * 16)
            _write_stamp(shadow, stamp, x * 16, y * 16, shadow_pal(stamp.ptype, stamp.pnum))

    floor_normal = normal.copy()
    floor_shadow = shadow.copy()
    crumble_stamps: dict[int, object] = {}
    terrain_rolls: dict[int, tuple[int, ...]] = {}
    recording_rand = _RecordingRand(rand)
    for y in range(MAZE_CELLS):
        for x in range(MAZE_CELLS):
            slot = pack_slot(y, x)
            recording_rand.calls.clear()
            obj = whatis(maze, x, y)
            stamp, dots = _terrain_stamp(
                maze, x, y, obj, recording_rand,
            )
            terrain_rolls[slot] = tuple(recording_rand.calls)
            if stamp is not None:
                write_stamp_to_image(normal, stamp, x * 16 + stamp.nudgex, y * 16 + stamp.nudgey)
                _write_stamp(shadow, stamp, x * 16 + stamp.nudgex, y * 16 + stamp.nudgey,
                             shadow_pal(stamp.ptype, stamp.pnum))
                if obj == MazeObjIds.WALL_DESTRUCTABLE:
                    # Keep the exact stamp so the crumble overlay can re-blit
                    # it through a damaged palette without calling
                    # wall_get_destructable_stamp again -- that would draw from
                    # the texture stream and shift every cell after it.
                    crumble_stamps[slot] = stamp
            if dots:
                _render_dots(normal, x * 16, y * 16, dots, _DOT_RGBA)
                _render_dots(shadow, x * 16, y * 16, dots, _DOT_RGBA_SHADOW)

    return (
        normal, shadow, crumble_stamps,
        floor_normal, floor_shadow, tuple(floor_variants), terrain_rolls,
    )


def build_playfield_images(maze: MazeLike):
    """Public three-artifact playfield build."""
    normal, shadow, crumble_stamps, *_ = _build_playfield_layers(maze)
    return normal, shadow, crumble_stamps


@dataclasses.dataclass
class PlayfieldCache:
    """The cached world rasters plus the maze identity they were built from,
    so the compositor can tell when it needs rebuilding (a new level) versus
    reusing what it has (every other frame). Owned by whichever host loop
    calls ``render_frame`` -- never stored on ``GameState`` (PLAN.md §3 rule
    7: rendering reads state, it is never read *by* state).

    ``image`` is the normal world raster; ``shadow_image`` is its
    half-intensity shadow-palette twin (``build_playfield_images``), sampled
    by the MOB layer for shadow pixels. ``floorpattern`` and ``exit_palette``
    are captured here for the same reason: the moving-exit overlay
    (``draw_exit_animation``) needs both every frame, and the palette is a
    snapshot of gex's ``palette_make_special`` result for *this* maze rather
    than a global read that a later level could have changed underneath it.

    ``signature`` and ``cells`` make the cache self-validating. The floor-only
    rasters and per-cell random choices support deterministic local restamps:
    opening a door or cycling a wall never redraws the other 1023 cells.
    Callers should retain this cache for the life of a level: deliberately
    dropping it performs a fresh shared-stream build, while the hardware-faithful
    live path preserves the choices already stamped into playfield RAM.
    """

    image: object         # PIL.Image.Image (untyped to avoid a hard PIL import at type-check time)
    shadow_image: object  # PIL.Image.Image -- the shadow-palette twin
    floorpattern: int = 0
    exit_palette: list | None = None
    transporter_palette: list | None = None
    signature: tuple = ()
    cells: dict | None = None
    crumble_stamps: dict | None = None
    floor_image: object | None = None
    floor_shadow_image: object | None = None
    floor_variants: tuple[int, ...] = ()
    terrain_rolls: dict[int, tuple[int, ...]] | None = None
    maze_object: object | None = None


def _maze_signature(maze: MazeLike) -> tuple:
    """Everything besides the cells that changes the rendered world."""
    return (
        int(getattr(maze, "floorpattern", 0)),
        int(getattr(maze, "floorcolor", 0)),
        int(getattr(maze, "wallpattern", 0)),
        int(getattr(maze, "wallcolor", 0)),
    )


def _changed_cell_neighbourhood(
    old: dict, new: dict,
) -> set[tuple[int, int]]:
    """Changed cells plus their wrapped 8-neighbour adjacency ring."""
    changed = {
        key for key in set(old) | set(new)
        if old.get(key, int(MazeObjIds.TILE_FLOOR))
        != new.get(key, int(MazeObjIds.TILE_FLOOR))
    }
    affected: set[tuple[int, int]] = set()
    for x, y in changed:
        if not 0 <= x < MAZE_CELLS or not 0 <= y < MAZE_CELLS:
            continue
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                affected.add(((x + dx) & 0x1F, (y + dy) & 0x1F))
    return affected


def _expand_cell_ring(
    cells: set[tuple[int, int]], radius: int = 1,
) -> set[tuple[int, int]]:
    """Wrapped square expansion around an existing cell set."""
    expanded: set[tuple[int, int]] = set()
    for x, y in cells:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                expanded.add(((x + dx) & 0x1F, (y + dy) & 0x1F))
    return expanded


def _restamp_changed_cells(maze: MazeLike, cache: PlayfieldCache) -> None:
    """Update changed terrain and its adjacency ring without a world rebuild."""
    old_cells = cache.cells or {}
    floor_cells = _changed_cell_neighbourhood(old_cells, maze.data)
    if not floor_cells:
        cache.cells = dict(maze.data)
        return
    # WALL_MOVABLE is a 24x16 stamp nudged -4,-4, so a floor box can erase art
    # belonging to a source cell one ring beyond the adjacency cells. Redraw
    # terrain from that extra ring after every floor box has been restored.
    terrain_cells = _expand_cell_ring(floor_cells)

    ffmap = ff_make_map(maze)
    shadow_pal_cache: dict[tuple[str, int], list] = {}

    def shadow_pal(ptype: str, pnum: int):
        key = (ptype, pnum)
        pal = shadow_pal_cache.get(key)
        if pal is None:
            pal = _shadow_palette(GAUNTLET_PALETTES[ptype][pnum])
            shadow_pal_cache[key] = pal
        return pal

    floor_variants = cache.floor_variants
    terrain_rolls = cache.terrain_rolls or {}
    crumble_stamps = cache.crumble_stamps or {}
    for x, y in sorted(floor_cells, key=lambda point: (point[1], point[0])):
        slot = pack_slot(y, x)
        variation = floor_variants[slot]
        floor_stamp = _floor_stamp(
            maze, x, y, ffmap, variation=variation,
        )
        px, py = x * 16, y * 16
        write_stamp_to_image(cache.floor_image, floor_stamp, px, py)
        _write_stamp(
            cache.floor_shadow_image, floor_stamp, px, py,
            shadow_pal(floor_stamp.ptype, floor_stamp.pnum),
        )

        box = (px, py, px + 16, py + 16)
        cache.image.paste(cache.floor_image.crop(box), box)
        cache.shadow_image.paste(cache.floor_shadow_image.crop(box), box)

    # Match the full builder's layer order: all floor writes first, then every
    # terrain write. Interleaving them lets a later floor box clip an earlier
    # stamp that overhangs its cell.
    for x, y in sorted(terrain_cells, key=lambda point: (point[1], point[0])):
        slot = pack_slot(y, x)
        px, py = x * 16, y * 16
        replay_rand = _ReplayRand(terrain_rolls.get(slot, ()), slot)
        obj = whatis(maze, x, y)
        stamp, dots = _terrain_stamp(
            maze, x, y, obj, replay_rand,
        )
        terrain_rolls[slot] = tuple(replay_rand.values)
        crumble_stamps.pop(slot, None)
        if stamp is not None:
            write_stamp_to_image(
                cache.image, stamp, px + stamp.nudgex, py + stamp.nudgey,
            )
            _write_stamp(
                cache.shadow_image, stamp,
                px + stamp.nudgex, py + stamp.nudgey,
                shadow_pal(stamp.ptype, stamp.pnum),
            )
            if obj == MazeObjIds.WALL_DESTRUCTABLE:
                crumble_stamps[slot] = stamp
        if dots:
            _render_dots(cache.image, px, py, dots, _DOT_RGBA)
            _render_dots(
                cache.shadow_image, px, py, dots, _DOT_RGBA_SHADOW,
            )

    cache.cells = dict(maze.data)
    cache.terrain_rolls = terrain_rolls
    cache.crumble_stamps = crumble_stamps


def playfield_cache_for(maze: MazeLike, cache: PlayfieldCache | None) -> PlayfieldCache:
    """Return a cache valid for ``maze``, rebuilding only when it is stale.

    Validity is decided on content plus the live maze object. An unchanged or
    content-identical maze reuses the raster. A replacement level with different
    content gets a full build. Changes under the same object -- door fronts,
    cyclic/random walls, destroyed walls -- diff ``cells`` and restamp only the
    changed cells plus their wrapped eight-neighbour adjacency ring.
    """
    signature = _maze_signature(maze)
    if cache is not None and cache.signature == signature:
        if cache.cells == maze.data:
            cache.maze_object = maze
            return cache
        if (
            cache.maze_object is maze
            and cache.floor_image is not None
            and cache.floor_shadow_image is not None
            and len(cache.floor_variants) == MAZE_CELLS * MAZE_CELLS
        ):
            _restamp_changed_cells(maze, cache)
            return cache

    (
        normal, shadow, crumble_stamps,
        floor_normal, floor_shadow, floor_variants, terrain_rolls,
    ) = _build_playfield_layers(maze)
    return PlayfieldCache(
        image=normal,
        shadow_image=shadow,
        floorpattern=signature[0],
        exit_palette=[c.to_rgba() for c in GAUNTLET_PALETTES["floor"][0]],
        transporter_palette=[
            c.to_rgba() for c in GAUNTLET_PALETTES["teleff"][0]
        ],
        signature=signature,
        cells=dict(maze.data),
        crumble_stamps=crumble_stamps,
        floor_image=floor_normal,
        floor_shadow_image=floor_shadow,
        floor_variants=floor_variants,
        terrain_rolls=terrain_rolls,
        maze_object=maze,
    )


class ShadowSource:
    """Samples the cached shadow raster by *framebuffer* coordinate, for the
    MOB layer's shadow pixels. Holds the full 512x512 shadow raster's pixel
    access plus the framebuffer->world offset implied by the current scroll
    and playfield viewport, so no per-frame crop is needed -- the same scroll
    arithmetic ``draw_playfield`` uses, inverted.
    """

    __slots__ = ("_px", "_w", "_h", "_ox", "_oy")

    def __init__(self, shadow_image, scroll_x: int, scroll_y: int, dest_x: int, dest_y: int) -> None:
        self._px = shadow_image.load()
        self._w, self._h = shadow_image.size
        # framebuffer (fx, fy) -> world (fx + ox, fy + oy): draw_playfield
        # pasted world pixel (scroll + (fx - dest)) at framebuffer fx.
        self._ox = scroll_x - dest_x
        self._oy = scroll_y - dest_y

    def at(self, fx: int, fy: int):
        """Shadow-palette RGBA of the playfield pixel under framebuffer
        (fx, fy), with the hardware's 9-bit playfield wrap."""
        wx = (fx + self._ox) % self._w
        wy = (fy + self._oy) % self._h
        return self._px[wx, wy]


def shadow_source_for(
    cache: PlayfieldCache, scroll_x: int, scroll_y: int, viewport: tuple[int, int, int, int]
) -> ShadowSource:
    """A ``ShadowSource`` over ``cache``'s shadow raster, aligned to the same
    scroll/viewport ``draw_playfield`` used for the normal raster."""
    dest_x, dest_y, _w, _h = viewport
    return ShadowSource(cache.shadow_image, scroll_x, scroll_y, dest_x, dest_y)


def draw_wall_crumble(fb, cache: PlayfieldCache, state, scroll_x: int, scroll_y: int,
                      viewport: tuple[int, int, int, int]) -> None:
    """Draw the damaged stages of destructible walls over the cached playfield.

    ``wall_crumble`` (0x5303A) takes a wall through three stages before
    ``pf_replace`` finally removes it, and the two ways it shows damage are
    both supplied by WP-7:

    * on a **shrub** wall set the ROM stamps a replacement 2x2 tile record --
      ``shots.wall_crumble_descriptor`` returns it (the
      ``wall_desc_destructible`` records at 0x53114's pointer table);
    * everywhere else the tiles stay put and the *palette* walks down,
      ``7 - stage`` (0x53120), which ``shots.wall_crumble_palette`` returns.

    Like the moving exit this is an overlay rather than part of the cached
    raster: the stage lives in ``state.destructible_wall_stage``, changes
    mid-level, and is not part of ``maze.data``, so a rebuild would not be
    triggered by it and would cost a whole 512x512 decode anyway.
    """
    from ..subsystems.shots import wall_crumble_descriptor, wall_crumble_palette

    stages = getattr(state, "destructible_wall_stage", None)
    if not stages or cache is None:
        return
    stamps = cache.crumble_stamps or {}

    for slot, stage in stages.items():
        if not stage:
            continue                      # stage 0 is the untouched wall
        descriptor = wall_crumble_descriptor(state, slot)
        stamp = stamps.get(slot)
        if descriptor is not None:
            # Shrub set: the ROM replaces the tiles. Palette is the wall
            # stamp's own -- the shrub bank has a single entry.
            palette = _stamp_palette_rgba(stamp, None)
            _blit_descriptor(fb, descriptor, slot, palette, scroll_x, scroll_y, viewport)
        elif stamp is not None:
            # The ROM's 7-stage nibble indexes live playfield color RAM, not
            # gex's static wall-color list. Using it as a gex palette index
            # turns the first hit pink/green. Keep the level wall palette; the
            # simulation still retains the exact crumble stage/nibble.
            palette = _stamp_palette_rgba(stamp, None)
            _blit_descriptor(
                fb, tuple(stamp.numbers[:4]), slot, palette, scroll_x, scroll_y, viewport,
            )


def _stamp_palette_rgba(stamp, pnum: int | None) -> list:
    """RGBA entries for ``stamp``'s palette bank, at ``pnum`` when that index
    exists in it -- the crumble walk only applies to the multi-entry wall bank,
    so an out-of-range index (or the single-entry shrub bank) falls back to the
    stamp's own palette."""
    if stamp is None:
        return [(0, 0, 0, 255)] * 16
    bank = GAUNTLET_PALETTES[stamp.ptype]
    index = stamp.pnum if pnum is None else pnum
    if not 0 <= index < len(bank):
        index = stamp.pnum
    return [c.to_rgba() for c in bank[index]]


def draw_playfield(fb, cache: PlayfieldCache, scroll_x: int, scroll_y: int, viewport: tuple[int, int, int, int]) -> None:
    """Blit the scrolled window of the cached world raster into ``fb``.

    ``viewport`` is ``(dest_x, dest_y, width, height)`` in framebuffer
    pixels -- where on screen the playfield goes and how big it is. Camera
    scroll is applied here, at blit time, per PLAN.md §6 WP-2 step 1: a
    toroidal crop of the 512x512 cache, no tile recomputation.
    """
    dest_x, dest_y, width, height = viewport
    world_w, world_h = cache.image.size
    remaining_h = height
    source_y = scroll_y % world_h
    out_y = dest_y
    while remaining_h:
        chunk_h = min(remaining_h, world_h - source_y)
        remaining_w = width
        source_x = scroll_x % world_w
        out_x = dest_x
        while remaining_w:
            chunk_w = min(remaining_w, world_w - source_x)
            fb.paste_region(
                cache.image,
                (
                    source_x, source_y,
                    source_x + chunk_w, source_y + chunk_h,
                ),
                (out_x, out_y),
            )
            remaining_w -= chunk_w
            out_x += chunk_w
            source_x = 0
        remaining_h -= chunk_h
        out_y += chunk_h
        source_y = 0


# ---------------------------------------------------------------------------
# The moving exit's open/close animation.
#
# This is a playfield-layer effect, not a MOB: ``main_exit_move`` (0x5287C)
# drives it through ``pf_stamp_update`` (0x5E536), which writes four descriptor
# words straight into the 2x2 block of playfield RAM for a cell
# (doc/04_game_subsystems.md §18's stamper note; ``pf_stamp_update`` contract in
# ``doc/generated/playfield_floor_contracts.csv``). That is why it lives here
# and not in ``render/mobs.py`` -- and why it has to be an overlay rather than
# something baked into the cached world raster, which is only rebuilt per level.
#
# Data, transcribed from row76.bin:
#
# * ``exit_desc_by_floorpattern`` (0x5B81C, doc/05_data_reference.md) -- nine
#   floor-pattern records of sixteen longword pointers into ``exit_tile_descs``.
#   Every record has the same shape, and record ``fp`` points at the seven
#   descriptors starting at pool index ``fp * 7``: entries 0-7 run that
#   seven-stage sequence forwards, entries 8-15 run it backwards.
#   ``main_exit_move`` reads offset 0 for the *closing* cell and offset 0x20
#   (entry 8) for the *opening* one (0x529E6-0x52A46), then steps both by
#   ``exit_anim_frame`` (0x52AAC-0x52AF6) -- so one cell seals as the other
#   opens, out of a single script.
# * ``exit_tile_descs`` (0x5C8B0) -- 63 eight-byte 2x2 descriptors holding the
#   252 *consecutive* words 0x3A2-0x49D, so descriptor ``k`` is simply
#   ``0x3A2 + 4*k`` and the following three tiles. Verified against the ROM.
# * ``floor_type10_desc`` (0x5C8A0) -- the settled exit, ``(0x39E, 0x39F, 6,
#   6)``. Those are exactly the tiles gex's own ``exit`` item stamp uses, which
#   is what pins the palette below.
# ---------------------------------------------------------------------------

#: Stages in the sequence a single floor pattern owns (pool indices fp*7 + 0..6).
EXIT_ANIM_STAGES = 7

#: Steps of ``exit_anim_frame``: one every fourth frame while ``exit_move_timer``
#: runs 0 down to -0x20, so eight of them (``subsystems/exits.py``).
EXIT_ANIM_FRAMES = 8

#: First word of ``exit_tile_descs``; descriptor k is base + 4*k .. +3.
EXIT_DESC_TILE_BASE = 0x03A2

#: The sixteen-entry record every floor pattern repeats, as pool offsets from
#: that pattern's own seven-descriptor block.
EXIT_DESC_RECORD = (0, 0, 1, 2, 3, 4, 5, 6, 6, 6, 5, 4, 3, 2, 1, 0)

#: ``floor_type10_desc`` (0x5C8A0) -- the resting exit's 2x2 block.
EXIT_SETTLED_DESC = (0x039E, 0x039F, 0x0006, 0x0006)

#: ``floor_type11_desc`` (0x5C8A8) -- the distinct EXIT TO LEVEL 6 block.
EXITTO6_SETTLED_DESC = (0x039E, 0x039F, 0x03A0, 0x03A1)

#: The transporter's playfield-stamped 2x2 block (gex ``tport`` ROM record).
TRANSPORTER_DESC = (0x049E, 0x049F, 0x04A0, 0x04A1)

# ``tport_palette_cycle_blocks`` (0x5AFAE), six 16-byte records. VBLANK copies
# the first six words of the selected record to playfield palette 4 entries 8-13.
_TRANSPORTER_PALETTE_CYCLE = (
    (0x8F00, 0xCF21, 0xFF76, 0xFF98, 0xFFDD, 0xFFFF),
    (0x8F00, 0x8F00, 0xCF21, 0xFF76, 0xFF98, 0xFFDD),
    (0x8F00, 0x8F00, 0x8F00, 0xCF21, 0xFF76, 0xFF98),
    (0x8F00, 0x8F00, 0x8F00, 0x8F00, 0xCF21, 0xFF76),
    (0x8F00, 0x8F00, 0x8F00, 0x8F00, 0x8F00, 0xCF21),
    (0x8F00, 0x8F00, 0x8F00, 0x8F00, 0x8F00, 0x8F00),
)

#: Playfield words are ``tile 11-0 | palette 14-12`` (doc/01_hardware.md §7).
#: Every exit descriptor word is below 0x1000, so its palette field is 0 -- the
#: same "floor" palette 0 gex's ``exit`` stamp declares.
_PF_TILE_MASK = 0x0FFF


def exit_descriptor(floorpattern: int, record_entry: int) -> tuple[int, int, int, int]:
    """The four playfield words for one entry of a floor pattern's exit record.

    ``record_entry`` is 0-7 for the closing cell's script and 8-15 for the
    opening cell's -- the two offsets ``main_exit_move`` reads.
    """
    stage = EXIT_DESC_RECORD[record_entry & 0x0F]
    index = (floorpattern % 9) * EXIT_ANIM_STAGES + stage
    first = EXIT_DESC_TILE_BASE + 4 * index
    return (first, first + 1, first + 2, first + 3)


def _blit_descriptor(
    fb, descriptor, cell: int, palette_rgba, scroll_x, scroll_y, viewport,
    *, trans0: bool = False,
) -> None:
    """Stamp one 2x2 descriptor over ``cell`` (a packed ``row<<5 | col`` slot).

    Mirrors ``pf_stamp_update``: word 0 is the top-left 8x8 tile, then
    top-right, bottom-left, bottom-right.
    """
    from gex.render import get_parsed_tile

    dest_x, dest_y, vw, vh = viewport
    clip = (dest_x, dest_y, dest_x + vw, dest_y + vh)
    world_x = (cell & 0x1F) * 16
    world_y = ((cell >> 5) & 0x1F) * 16

    def visible_delta(world: int, scroll: int, viewport_size: int) -> int | None:
        wrapped = (world - scroll) % WORLD_PIXELS
        for delta in (wrapped, wrapped - WORLD_PIXELS):
            if delta + 16 > 0 and delta < viewport_size:
                return delta
        return None

    delta_x = visible_delta(world_x, scroll_x, vw)
    delta_y = visible_delta(world_y, scroll_y, vh)
    if delta_x is None or delta_y is None:
        return
    screen_x = dest_x + delta_x
    screen_y = dest_y + delta_y

    for i, word in enumerate(descriptor):
        try:
            tile = get_parsed_tile(word & _PF_TILE_MASK)
        except Exception:
            continue        # a ROM-free run has no pixels to stamp
        row, col = divmod(i, 2)
        fb.blit_indexed_tile(
            tile, palette_rgba,
            screen_x + col * 8, screen_y + row * 8,
            trans0=trans0, clip=clip,
        )


def draw_exit_animation(fb, cache: PlayfieldCache, state, scroll_x: int, scroll_y: int,
                        viewport: tuple[int, int, int, int]) -> None:
    """Draw live settled exits and the moving exit animation over the cache.

    ``main_exit_move`` keeps two cells in play: ``exit_open_id``, which is
    becoming an exit, and ``exit_close_id``, the one it vacated. While
    ``exit_move_timer`` is negative both step through the shared script at
    ``exit_anim_frame`` (0-7); once it settles the opening cell holds
    ``floor_type10_desc`` and the vacated cell goes back to plain floor -- which
    here means simply not drawing over it, since the cached raster already has
    floor everywhere an exit is not baked in (EXIT is not in ``TERRAIN_TYPES``).
    """
    if cache is None:
        return

    palette_rgba = cache.exit_palette
    if palette_rgba is None:
        return

    moving_open = int(getattr(state, "exit_open_id", 0))
    for slot in range(0x20, len(state.mobs.picture)):
        if slot == moving_open or state.mobs.picture[slot] == 0:
            continue
        if state.mobs.obj_type(slot) not in (
            int(MazeObjIds.EXIT), int(MazeObjIds.EXITTO6),
        ):
            continue
        descriptor = (
            EXITTO6_SETTLED_DESC
            if state.mobs.obj_type(slot) == int(MazeObjIds.EXITTO6)
            else EXIT_SETTLED_DESC
        )
        _blit_descriptor(
            fb, descriptor, slot, palette_rgba,
            scroll_x, scroll_y, viewport,
        )

    if not moving_open:
        return

    frame = max(0, min(EXIT_ANIM_FRAMES - 1, int(state.exit_anim_frame)))
    animating = int(state.exit_move_timer) < 0

    if animating:
        opening = exit_descriptor(cache.floorpattern, EXIT_ANIM_FRAMES + frame)
        if state.exit_close_id:
            _blit_descriptor(
                fb, exit_descriptor(cache.floorpattern, frame),
                state.exit_close_id, palette_rgba, scroll_x, scroll_y, viewport,
            )
    else:
        opening = (
            EXITTO6_SETTLED_DESC
            if state.mobs.obj_type(moving_open) == int(MazeObjIds.EXITTO6)
            else EXIT_SETTLED_DESC
        )

    _blit_descriptor(
        fb, opening, moving_open, palette_rgba, scroll_x, scroll_y, viewport,
    )


def draw_transporter_tiles(
    fb, cache: PlayfieldCache, state, scroll_x: int, scroll_y: int,
    viewport: tuple[int, int, int, int],
) -> None:
    """Stamp every live transporter marker through playfield palette 4."""
    if cache is None or cache.transporter_palette is None:
        return
    phase = max(0, min(5, int(state.tport_cycle_pos)))
    palette = list(cache.transporter_palette)
    palette[8:14] = [
        IRGB(word).to_rgba() for word in _TRANSPORTER_PALETTE_CYCLE[phase]
    ]
    for slot in range(0x20, len(state.mobs.picture)):
        if (state.mobs.picture[slot]
                and state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER)):
            _blit_descriptor(
                fb, TRANSPORTER_DESC, slot, palette,
                scroll_x, scroll_y, viewport, trans0=True,
            )


def _live_forcefield_cells(state) -> set[tuple[int, int]]:  # noqa: ANN001
    """Expand the ROM's packed segment words to cells needing palette redraw."""
    cells: set[tuple[int, int]] = set()
    for segment in state.forcefield_segments:
        hub = segment & 0x3FF
        row, col = hub >> 5, hub & 0x1F
        length = ((segment >> 10) & 0x0F) + 1
        horizontal = bool(segment & 0x8000)
        for distance in range(1, length):
            cells.add((
                (col + distance) & 0x1F if horizontal else col,
                row if horizontal else (row + distance) & 0x1F,
            ))
    return cells


def draw_animated_floor_tiles(
    fb, cache: PlayfieldCache, state, scroll_x: int, scroll_y: int,
    viewport: tuple[int, int, int, int],
) -> None:
    """Re-stamp forcefield/trap/stun cells through their live palette words."""
    if cache is None or cache.maze_object is None:
        return

    floorpattern = cache.floorpattern % len(S_COLORS_1)
    ffmap = _live_forcefield_cells(state)
    for x, y in ffmap:
        slot = pack_slot(y, x)
        stamp = _floor_stamp(
            cache.maze_object, x, y, ffmap,
            variation=cache.floor_variants[slot],
        )
        _blit_descriptor(
            fb, tuple(stamp.numbers), slot,
            _animated_floor_palette(
                "forcefield", floorpattern, state.forcefield_color,
            ),
            scroll_x, scroll_y, viewport,
        )

    animated = {
        int(MazeObjIds.TILE_TRAP1): ("trap", state.palette_pulse_b),
        int(MazeObjIds.TILE_TRAP2): ("trap", state.palette_pulse_b),
        int(MazeObjIds.TILE_TRAP3): ("trap", state.palette_pulse_b),
        int(MazeObjIds.TILE_STUN): ("stun", state.palette_pulse_a),
    }
    for (x, y), obj in (cache.cells or {}).items():
        live = animated.get(int(obj))
        if live is None:
            continue
        ptype, color_word = live
        slot = pack_slot(y, x)
        replay_rand = _ReplayRand((cache.terrain_rolls or {}).get(slot, ()), slot)
        stamp, _dots = _terrain_stamp(
            cache.maze_object, x, y, int(obj), replay_rand,
        )
        if stamp is None:
            continue
        palette = _animated_floor_palette(
            ptype, floorpattern, color_word,
        )
        _blit_descriptor(
            fb, tuple(stamp.numbers), slot, palette,
            scroll_x, scroll_y, viewport,
        )


def _animated_floor_palette(
    ptype: str, floorpattern: int, color_word: int,
) -> list[tuple[int, int, int, int]]:
    palette = [color.to_rgba() for color in GAUNTLET_PALETTES[ptype][0]]
    live_rgba = IRGB(color_word).to_rgba()
    for color_index in (
        0, S_COLORS_1[floorpattern], S_COLORS_2[floorpattern],
    ):
        palette[color_index] = live_rgba
    return palette
