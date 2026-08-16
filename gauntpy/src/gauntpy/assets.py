"""ROM and asset bridge: wraps ``gex`` behind an interface the renderer and
subsystems can use, so gex's CLI-oriented API (string verbs like
``"ghost-walk-up"``, argparse namespaces, PNG files) never leaks into game
code.

Everything pixel-shaped in gauntpy comes from the user's own ROMs, read and
decoded at runtime by the sibling ``../python-gex`` project (see its
``README.md``). This module owns exactly three things gex does not provide
directly:

1. A small, game-shaped surface -- ``tile``/``stamp``/``palette`` -- instead
   of gex's CLI verbs and file-writing entry points.
2. Sprite lookup **by MOB picture number** (what the simulation actually
   stores in ``mob_picture`` / ``MobTable.picture``) rather than by gex's
   name-based lookup (``"ghost-walk-up"``). See ``sprite()`` below.
3. A construction-time check that fails loudly, with fix-it instructions,
   when the ROMs aren't set up -- this is the first thing anyone who clones
   the repo and tries to run gauntpy will hit.

Reference: ``PLAN.md`` §6 WP-1; ``python-gex/README.md``;
``python-gex/src/gex/{roms,render,palettes,monsters}.py``;
``doc/05_data_reference.md`` §7 (monster animation pointer tables).

No ROM images, ROM-derived tables, or copyrighted assets are committed here
(PLAN.md §1) -- everything below reads the user's own ROM dump at runtime.
"""

from __future__ import annotations

import os
from typing import NamedTuple, Sequence

from gex.monsters import MONSTERS
from gex.palettes import GAUNTLET_PALETTES, Palette
from gex.render import Stamp, TileData, gen_stamp_from_array, get_parsed_tile
from gex.roms import GexError, TILE_ROMS, _rom_dir

__all__ = ["AssetError", "AssetStore", "SpriteFrame"]


class AssetError(Exception):
    """Something the asset bridge could not satisfy: missing ROMs, an
    unknown tile/palette/picture number, or a gex-level decode failure.

    Callers of this module never need to catch gex's own exception types
    (``GexError`` and friends) -- everything gex-shaped that can go wrong is
    translated into this one.
    """


# ---------------------------------------------------------------------------
# ROM availability check
# ---------------------------------------------------------------------------

def _roms_available() -> bool:
    """Mirrors the check gex's own test suite uses (e.g.
    ``python-gex/tests/test_golden_images.py``): the resolved ROM directory
    must exist and contain at least the first tile ROM. gex re-reads
    ``GEX_ROM_DIR`` on every call (``gex.roms._rom_dir``), so this is cheap
    and always current.
    """
    rom_dir = _rom_dir()
    return rom_dir.is_dir() and (rom_dir / TILE_ROMS[0][0]).is_file()


def _require_roms() -> None:
    if _roms_available():
        return
    rom_dir = _rom_dir()
    env_val = os.environ.get("GEX_ROM_DIR")
    raise AssetError(
        "gauntpy needs the Gauntlet II arcade ROM files to decode any "
        "graphics, and none were found.\n"
        f"  GEX_ROM_DIR = {env_val!r} "
        f"({'unset -- gex falls back to a ./ROMs directory in the cwd' if env_val is None else 'set'})\n"
        f"  Resolved ROM directory: {rom_dir}\n"
        f"  {'That directory does not exist.' if not rom_dir.is_dir() else 'That directory exists but is missing ' + TILE_ROMS[0][0] + ' (and likely the rest of the ROM set).'}\n"
        "\n"
        "Fix: set GEX_ROM_DIR to a directory containing your own Gauntlet II "
        "ROM dump (file list and checksums in python-gex/README.md), e.g.\n"
        "\n"
        "    export GEX_ROM_DIR=/path/to/your/ROMs\n"
        "\n"
        "gauntpy does not ship ROM images or ROM-derived data -- see "
        "PLAN.md §1."
    )


# ---------------------------------------------------------------------------
# Picture number -> sprite frame
# ---------------------------------------------------------------------------

class SpriteFrame(NamedTuple):
    """Identifies which named/directed/framed sprite a raw MOB picture
    number refers to. Purely descriptive -- ``AssetStore.sprite()`` uses it
    internally to find the tile block's width/height/palette-type, but
    callers may also want it (logging, tests) without building a ``Stamp``.
    """

    monster_type: str   # key into gex.monsters.MONSTERS, e.g. "ghost"
    action: str          # e.g. "walk"
    direction: str        # e.g. "up"
    frame_index: int      # index into that direction's frame list


def _build_picture_index() -> dict[int, SpriteFrame]:
    """Build the picture-number -> sprite-frame map from gex's own monster
    animation data (``gex.monsters.MONSTERS``, loaded from
    ``python-gex/src/gex/data/monsters.jsonc``).

    Those per-frame tile numbers *are* the doc/05_data_reference.md §7
    animation tables -- e.g. gex's "ghost" entry is exactly the verified
    table in §7.4 (same 32 tile numbers, same counter-group-of-5-then-1-2-3
    pattern), and gex's own docstring for the data file says as much.
    Building the reverse map from gex's data instead of re-transcribing the
    doc keeps the two from drifting apart, and (this is the important part)
    it means the map grows automatically if gex ever gains data for more
    monster families.

    KNOWN GAP (flagging per PLAN.md's "stop and report rather than guess"):
    as of this writing gex's monsters.jsonc defines only "ghost". The other
    eight monster families (grunt, demon, lobber, sorcerer/supersorc, death,
    acid, it) have ROM *table addresses* in doc/05_data_reference.md
    §7.1-7.3, and §7.5 gives exactly one verified Grunt tile number (DOWN
    frame 0 = 2529) plus a counter pattern description -- not a full 64-word
    listing. That is not enough to build a correct reverse map for those
    families without reading the ROM directly, which is out of scope for
    WP-1 (told to read §7 only) and arguably belongs in gex itself (whoever
    extends monsters.jsonc gets this mapping for free, with no gauntpy
    change needed). ``AssetStore.sprite()`` raises a clear ``AssetError``
    naming the families it *does* know about rather than silently returning
    a wrong or blank sprite for the rest.
    """
    index: dict[int, SpriteFrame] = {}
    for monster_type, mon in MONSTERS.items():
        for action, by_direction in mon.anims.items():
            for direction, frames in by_direction.items():
                for frame_index, tile_number in enumerate(frames):
                    index[tile_number] = SpriteFrame(monster_type, action, direction, frame_index)
    return index


# Built once at import time: pure Python data from gex's bundled jsonc, no
# ROM I/O, so this is safe to compute even when no ROMs are configured.
_PICTURE_INDEX: dict[int, SpriteFrame] = _build_picture_index()

#: mob_picture bits 14-0 are the tile number; bit 15 is a separate software
#: flag (gauntpy/src/gauntpy/mob.py's MobTable docstring; consistent with
#: every "N | tile | picture+flag" row in doc/05_data_reference.md's fixed
#: object picture table, e.g. "Potion (destr) | ... | 2300+flag | bit 15").
PICTURE_TILE_MASK = 0x7FFF


# ---------------------------------------------------------------------------
# AssetStore
# ---------------------------------------------------------------------------

class AssetStore:
    """The one door between gauntpy and gex.

    Construction fails fast with an actionable ``AssetError`` if the ROMs
    aren't configured -- see ``_require_roms()``. After that, every method
    is a pure decode: same inputs always produce the same (cached) output,
    with no dependency on ``GameState``.
    """

    def __init__(self) -> None:
        _require_roms()
        # gex's own get_parsed_tile() is already process-wide cached
        # (functools.lru_cache) by raw tile number, so decoding the same
        # tile twice -- from two different stamps, or two different
        # AssetStore instances -- never re-reads the ROM. This cache is the
        # one extra layer worth adding on top: it avoids rebuilding the
        # same Stamp object (and its tile-list) every frame for an
        # animation that keeps requesting the same tile block.
        self._stamp_cache: dict[tuple, Stamp] = {}

    # -- tiles ---------------------------------------------------------

    def tile(self, number: int) -> TileData:
        """Decoded 8x8 tile: 8 rows of 8 palette-index pixels (0-15). Combine
        with ``palette()`` to get colors. The returned list is shared with
        gex's internal cache -- treat it as read-only.
        """
        try:
            return get_parsed_tile(number)
        except GexError as exc:
            raise AssetError(f"Could not decode tile {number:#06x}: {exc}") from exc

    # -- multi-tile sprites ---------------------------------------------

    def stamp(
        self,
        numbers: Sequence[int],
        width: int,
        ptype: str = "base",
        pnum: int = 0,
        trans0: bool = False,
    ) -> Stamp:
        """A multi-tile sprite: ``numbers`` laid out ``width`` tiles wide,
        row-major, using palette ``GAUNTLET_PALETTES[ptype][pnum]`` at draw
        time. ``trans0`` makes palette index 0 transparent instead of opaque
        black (gex's convention for items/keys/etc., see
        ``gex.render.write_tile_to_image``).
        """
        key = (tuple(numbers), width, ptype, pnum, trans0)
        cached = self._stamp_cache.get(key)
        if cached is not None:
            return cached
        try:
            built = gen_stamp_from_array(list(numbers), width, ptype, pnum)
        except GexError as exc:
            raise AssetError(f"Could not build stamp for tiles {list(numbers)}: {exc}") from exc
        built.trans0 = trans0
        self._stamp_cache[key] = built
        return built

    # -- palettes --------------------------------------------------------

    def palette(self, kind: str, index: int) -> Palette:
        """A 16-entry ``Palette`` (list of ``IRGB``) by kind
        (``"base"``/``"floor"``/``"wall"``/character names/etc. -- see
        ``gex.palettes.GAUNTLET_PALETTES``) and index within that kind.
        """
        try:
            table = GAUNTLET_PALETTES[kind]
        except KeyError:
            raise AssetError(
                f"Unknown palette kind {kind!r}; valid kinds: {sorted(GAUNTLET_PALETTES)}"
            ) from None
        try:
            return table[index]
        except IndexError:
            raise AssetError(
                f"Palette index {index} out of range for kind {kind!r} "
                f"(0..{len(table) - 1})"
            ) from None

    # -- sprite lookup by MOB picture number ------------------------------

    def sprite_frame(self, picture: int) -> SpriteFrame:
        """Identify which sprite frame a raw MOB picture number names,
        without building a Stamp. Raises ``AssetError`` if the picture
        number isn't in any animation table gex currently knows about (see
        ``_build_picture_index``'s docstring for the known gap).
        """
        masked = picture & PICTURE_TILE_MASK
        frame = _PICTURE_INDEX.get(masked)
        if frame is None:
            raise AssetError(
                f"No known sprite for MOB picture number {picture:#06x} "
                f"(tile {masked:#06x} after masking off bit 15, the "
                "software flag -- doc/05_data_reference.md mob_picture "
                "entry). This tile isn't in any animation table gex "
                "currently has data for. Monster families gex knows about: "
                f"{sorted(MONSTERS)}. See doc/05_data_reference.md §7 and "
                "the WP-1 report for the rest."
            )
        return frame

    def sprite(self, picture: int, *, tier: int = 1) -> Stamp:
        """The multi-tile ``Stamp`` for a raw MOB picture number
        (``mob_picture`` / ``MobTable.picture``).

        ``tier`` selects the palette variant the way gex's own CLI does for
        a name like ``"ghost2-walk-up"``: ``pal_num = mon.pnum + (tier +
        1)`` (see ``python-gex/src/gex/monsters.py`` ``domonster()``, which
        calls this ``monster_level``). Renamed here to avoid clashing with
        gauntpy's ``levelnum_current`` (the *dungeon* level) -- this is the
        monster-strength tier from ``MazeObjIds.GEN_GHOST1/2/3`` and
        friends, a different axis entirely. The picture number alone does
        not encode which tier a live monster is (that lives in the MOB's
        own state, e.g. the hpos low-nibble tier used by shot-hit
        resolution -- doc/04_game_subsystems.md §26); the caller supplies
        it.
        """
        masked = picture & PICTURE_TILE_MASK
        frame = self.sprite_frame(picture)
        mon = MONSTERS[frame.monster_type]
        pal_num = mon.pnum + (tier + 1)
        tiles = tuple(range(masked, masked + mon.xsize * mon.ysize))
        return self.stamp(tiles, mon.xsize, mon.ptype, pal_num)
