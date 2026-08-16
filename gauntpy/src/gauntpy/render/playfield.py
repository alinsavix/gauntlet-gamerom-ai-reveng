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
exits, the transporter pad). Those are drawn from the live ``MobTable`` by
``render/mobs.py`` once a maze's objects are placed into it (WP-3). Until
WP-3 lands, ``state.mobs`` is simply empty and nothing is drawn there --
this module does not depend on WP-3 to produce a correct terrain-only
playfield.

This split is also why the acceptance test (``tests/test_render.py``)
cannot byte-for-byte match a full ``genpfimage`` PNG: gex's reference draws
strictly more (the baked-in starting objects). The test instead restricts
its pixel comparison to cells whose content is terrain in both renderers --
see the test module's docstring for the exact method.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from gex.adjacency import (
    checkdooradj4,
    checkffadj4,
    checkwalladj3,
    checkwalladj8,
    copyedges,
    ff_make_map,
    isdoor,
    whatis,
)
from gex.door import DOOR_HORIZ, DOOR_VERT, door_get_stamp
from gex.floor import floor_get_stamp
from gex.items import item_get_stamp
from gex.palettes import GAUNTLET_PALETTES, IRGB, palette_make_special
from gex.render import Stamp, blank_image, write_stamp_to_image
from gex.wall import ff_get_stamp, wall_get_destructable_stamp, wall_get_stamp

from ..constants import MazeObjIds
from ..coords import PF_COLS, PF_ROWS, WORLD_PIXELS

__all__ = [
    "MAZE_CELLS", "TERRAIN_TYPES", "PlayfieldCache", "ShadowSource",
    "build_playfield_image", "build_playfield_images", "draw_playfield",
    "irgb_to_shadow", "shadow_source_for",
]

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
    {MazeObjIds.TILE_FLOOR, MazeObjIds.WALL_MOVABLE, MazeObjIds.WALL_SECRET,
     MazeObjIds.WALL_DESTRUCTABLE, MazeObjIds.DOOR_HORIZ, MazeObjIds.DOOR_VERT,
     MazeObjIds.FORCEFIELDHUB}
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


def _terrain_stamp(maze: MazeLike, x: int, y: int, obj: int) -> tuple[Stamp | None, int]:
    """Terrain-only equivalent of ``gex.pfrender._get_stamp_for_obj``: same
    dispatch, restricted to ``TERRAIN_TYPES``. Returns (stamp, dot count).
    """
    if obj in _FLOOR_TILE_INFO:
        ptype_override, dots = _FLOOR_TILE_INFO[obj]
        adj = checkwalladj3(maze, x, y) + maze.rand.intn(4)
        return dataclasses.replace(
            floor_get_stamp(maze.floorpattern, adj, maze.floorcolor),
            ptype=ptype_override, pnum=0,
        ), dots

    if obj == MazeObjIds.WALL_DESTRUCTABLE:
        adj = checkwalladj8(maze, x, y)
        return wall_get_destructable_stamp(maze.wallpattern, adj, maze.wallcolor, maze.rand), 0

    if obj == MazeObjIds.WALL_SECRET:
        adj = checkwalladj8(maze, x, y)
        return dataclasses.replace(
            wall_get_stamp(maze.wallpattern, adj, maze.wallcolor, maze.rand),
            ptype="secret", pnum=0,
        ), 0

    if obj in _WALL_TILE_DOTS:
        adj = checkwalladj8(maze, x, y)
        return wall_get_stamp(maze.wallpattern, adj, maze.wallcolor, maze.rand), _WALL_TILE_DOTS[obj]

    if obj == MazeObjIds.WALL_MOVABLE:
        # Rendered as a single named stamp, not adjacency-shaped -- a
        # pushwall doesn't blend into the wall run around it. Matches
        # gex.pfrender's own _ITEM_STAMP_NAMES["pushwall"] entry; kept here
        # (rather than dropped into the "not terrain" bucket) because a
        # movable wall's *position changes* happen through the same
        # tile-descriptor rewrite path as any other wall
        # (doc/04_game_subsystems.md §13; WP-11 owns the actual movement),
        # not through the MOB table.
        return item_get_stamp("pushwall"), 0

    if isdoor(obj):
        adj = checkdooradj4(maze, x, y)
        return door_get_stamp(DOOR_HORIZ if obj == MazeObjIds.DOOR_HORIZ else DOOR_VERT, adj), 0

    if obj == MazeObjIds.FORCEFIELDHUB:
        adj = checkffadj4(maze, x, y)
        return ff_get_stamp(adj), 0

    if obj == MazeObjIds.FOOD_INVULN:
        # Not terrain (it's a floor item, drawn by the MOB layer once
        # placed) -- but gex.pfrender's own dispatch for this one object
        # type draws from ``maze.rand`` (picking which of the three "food"
        # sprites to preview: ``FOODS[maze.rand.intn(3)]``), the only
        # non-terrain branch in gex's whole dispatch table that does. Since
        # every terrain cell's floor-texture variety also comes from this
        # same ``maze.rand`` stream (see ``_floor_stamp`` below), silently
        # skipping this draw would desync every *subsequent* cell's floor
        # texture from gex's reference rendering -- not just this cell's.
        # Consuming (and discarding) the same draw keeps the two streams
        # aligned. This is a real coupling to a gex implementation detail;
        # if gex's dispatch ever gains another rand-consuming non-terrain
        # branch, ``tests/test_render.py``'s golden-image comparison will
        # start failing with mismatches spread past that object's cell, and
        # this is the fix to look for.
        maze.rand.intn(3)
        return None, 0

    return None, 0


def _floor_stamp(maze: MazeLike, x: int, y: int, ffmap) -> Stamp:
    adj = checkwalladj3(maze, x, y) if maze.wallpattern < 11 else 0
    stamp = floor_get_stamp(maze.floorpattern, adj + maze.rand.intn(4), maze.floorcolor)
    if (x, y) in ffmap:
        stamp = dataclasses.replace(stamp, ptype="forcefield", pnum=0)
    return stamp


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

    **Open question, flagged rather than silently resolved:** wall/door
    connectivity at the boundary cells (column/row 31) is computed after
    calling ``gex.adjacency.copyedges``, which mirrors column/row 0 into a
    phantom column/row 32 *whenever the level does not wrap on that axis*.
    That is gex's own convention for giving a maze-preview PNG a
    non-truncated-looking border; nothing in the disassembly documents what
    the real hardware's wall-connectivity scan does when it looks one cell
    past the edge of a non-wrapping level (out-of-range playfield RAM read,
    or a level-authoring guarantee that a border wall's connectivity never
    needs it -- every stock maze has a full wall ring at row/column 0 and a
    matching one is implied at 31, per the decoder's own "fill row 0 with
    walls" step in ``gex.mazedecode.maze_decompress``). We call
    ``copyedges`` here purely so this module's boundary wall shapes match
    ``gex``'s reference images pixel-for-pixel (the acceptance test in
    ``tests/test_render.py`` depends on it) -- not because it is confirmed
    hardware-accurate.
    """
    return build_playfield_images(maze)[0]


#: White floor-dot color and its shadow-palette equivalent, precomputed.
_DOT_RGBA = IRGB(0xFFFF).to_rgba()
_DOT_RGBA_SHADOW = IRGB(irgb_to_shadow(0xFFFF)).to_rgba()


def build_playfield_images(maze: MazeLike):
    """Build both the normal world raster and its **shadow-palette twin** in a
    single decode pass, returning ``(normal, shadow)``.

    The shadow raster is the same terrain rendered through the half-intensity
    shadow palette (``irgb_to_shadow`` on every color) -- it *is* the hardware
    shadow-palette bank's contribution, precomputed for the whole world. The
    MOB layer samples it wherever a sprite pixel has index 1 (shadow), so the
    shadow shows the true (I−7)-intensity playfield color rather than an
    approximation. Both rasters are produced from one ``maze.rand`` stream
    (the stamps are chosen once and drawn to both images), so the shadow
    raster is guaranteed pixel-aligned with the normal one and the floor
    texture randomization can't desync between them.

    ``build_playfield_image`` returns just the normal raster (unchanged output
    -- the golden-image test still holds), for callers that don't need shadow.
    """
    normal = blank_image(WORLD_PIXELS, WORLD_PIXELS)
    shadow = blank_image(WORLD_PIXELS, WORLD_PIXELS)
    ffmap = ff_make_map(maze)
    copyedges(maze)  # see "Open question" above
    palette_make_special(maze.floorpattern, maze.floorcolor, maze.wallpattern, maze.wallcolor)

    shadow_pal_cache: dict[tuple[str, int], list] = {}

    def shadow_pal(ptype: str, pnum: int):
        key = (ptype, pnum)
        pal = shadow_pal_cache.get(key)
        if pal is None:
            pal = _shadow_palette(GAUNTLET_PALETTES[ptype][pnum])
            shadow_pal_cache[key] = pal
        return pal

    for y in range(MAZE_CELLS):
        for x in range(MAZE_CELLS):
            stamp = _floor_stamp(maze, x, y, ffmap)
            write_stamp_to_image(normal, stamp, x * 16, y * 16)
            _write_stamp(shadow, stamp, x * 16, y * 16, shadow_pal(stamp.ptype, stamp.pnum))

    for y in range(MAZE_CELLS):
        for x in range(MAZE_CELLS):
            obj = whatis(maze, x, y)
            stamp, dots = _terrain_stamp(maze, x, y, obj)
            if stamp is not None:
                write_stamp_to_image(normal, stamp, x * 16 + stamp.nudgex, y * 16 + stamp.nudgey)
                _write_stamp(shadow, stamp, x * 16 + stamp.nudgex, y * 16 + stamp.nudgey,
                             shadow_pal(stamp.ptype, stamp.pnum))
            if dots:
                _render_dots(normal, x * 16, y * 16, dots, _DOT_RGBA)
                _render_dots(shadow, x * 16, y * 16, dots, _DOT_RGBA_SHADOW)

    return normal, shadow


@dataclasses.dataclass
class PlayfieldCache:
    """The cached world rasters plus the maze identity they were built from,
    so the compositor can tell when it needs rebuilding (a new level) versus
    reusing what it has (every other frame). Owned by whichever host loop
    calls ``render_frame`` -- never stored on ``GameState`` (PLAN.md §3 rule
    7: rendering reads state, it is never read *by* state).

    ``image`` is the normal world raster; ``shadow_image`` is its
    half-intensity shadow-palette twin (``build_playfield_images``), sampled
    by the MOB layer for shadow pixels.
    """

    maze_id: int
    image: object         # PIL.Image.Image (untyped to avoid a hard PIL import at type-check time)
    shadow_image: object  # PIL.Image.Image -- the shadow-palette twin


def playfield_cache_for(maze: MazeLike, cache: PlayfieldCache | None) -> PlayfieldCache:
    """Return a cache valid for ``maze``, rebuilding only if ``cache`` is
    stale or absent. ``id(maze)`` is enough to detect "new level": WP-3
    replaces ``state.maze`` wholesale on a level transition rather than
    mutating one Maze object's terrain in place (terrain mutation in place
    is WP-11's job and will need its own invalidation -- flagged, not
    implemented here, since no work package currently mutates ``maze.data``
    after decode).
    """
    if cache is not None and cache.maze_id == id(maze):
        return cache
    normal, shadow = build_playfield_images(maze)
    return PlayfieldCache(maze_id=id(maze), image=normal, shadow_image=shadow)


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
        (fx, fy), or ``None`` if that world position is off the raster
        (e.g. a wraparound seam) -- the caller falls back to scaling there."""
        wx = fx + self._ox
        wy = fy + self._oy
        if 0 <= wx < self._w and 0 <= wy < self._h:
            return self._px[wx, wy]
        return None


def shadow_source_for(
    cache: PlayfieldCache, scroll_x: int, scroll_y: int, viewport: tuple[int, int, int, int]
) -> ShadowSource:
    """A ``ShadowSource`` over ``cache``'s shadow raster, aligned to the same
    scroll/viewport ``draw_playfield`` used for the normal raster."""
    dest_x, dest_y, _w, _h = viewport
    return ShadowSource(cache.shadow_image, scroll_x, scroll_y, dest_x, dest_y)


def draw_playfield(fb, cache: PlayfieldCache, scroll_x: int, scroll_y: int, viewport: tuple[int, int, int, int]) -> None:
    """Blit the scrolled window of the cached world raster into ``fb``.

    ``viewport`` is ``(dest_x, dest_y, width, height)`` in framebuffer
    pixels -- where on screen the playfield goes and how big it is. Camera
    scroll is applied here, at blit time, per PLAN.md §6 WP-2 step 1: a
    plain crop of the 512x512 cache, no tile recomputation.
    """
    dest_x, dest_y, width, height = viewport
    box = (scroll_x, scroll_y, scroll_x + width, scroll_y + height)
    fb.paste_region(cache.image, box, (dest_x, dest_y))
