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
   name-based lookup (``"ghost-walk-up"``). See ``sprite()`` below -- including
   the two things no gex table names: the block geometry of the effect
   pictures (``EFFECT_PICTURES``) and the raw size-driven fallback that draws
   artwork no metadata covers at all (``AssetStore._sized_block``).
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
from typing import TYPE_CHECKING, NamedTuple, Sequence

from gex.dragon import (
    DRAGON_SEGMENT_TILES,
    SEGMENT_PNUM,
    SEGMENT_PTYPE,
    SEGMENT_XSIZE,
    SEGMENT_YSIZE,
)
from gex.effects import (
    EFFECT_TABLES,
    STAR_PNUM,
    STAR_PTYPE,
    STAR_TILES,
    STAR_XSIZE,
    STAR_YSIZE,
)
from gex.heroes import HEROES
from gex.items import item_stamp_for_picture
from gex.monsters import MONSTERS
from gex.npcs import NPCS
from gex.palettes import GAUNTLET_PALETTES, Palette
from gex.projectiles import (
    PROJECTILE_TILES,
    SHOT_PNUM,
    SHOT_PTYPE,
    SHOT_XSIZE,
    SHOT_YSIZE,
)
from gex.render import Stamp, TileData, gen_stamp_from_array, get_parsed_tile
from gex.roms import GexError, TILE_ROMS, _rom_dir
from gex.title_logo import title_logo_image

if TYPE_CHECKING:
    from PIL import Image

__all__ = [
    "AssetError", "AssetStore", "SpriteFrame", "TileBlock", "HERO_NAMES",
    "EFFECT_PICTURES", "TPORT_TRANSITION_PICTURES", "MAX_BLOCK_TILES",
]


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


def _index_entities(entities: dict) -> dict[int, SpriteFrame]:
    """Reverse ``{name: entity}`` into a picture-number -> frame map.

    Within one entity, actions can *share* base tiles: for the NULL-moving
    families "idle" is literally "walk", and a hero's actions overlap too. So
    a tile can be claimed by more than one action, and the winner must be
    deterministic (not "whichever JSON key happened to come last"). Resolve
    by a fixed precedence -- "walk" is the canonical identity of a placed
    object's picture -- and let the first (highest-precedence) action keep the
    tile via setdefault. Across entities the same rule applies to whichever
    entity ``entities`` iterates first, which is why the *scoped* maps below
    exist: they are how a caller says which entity it meant.
    """
    index: dict[int, SpriteFrame] = {}
    for name, entity in entities.items():
        for action in sorted(entity.anims, key=_action_rank):
            for direction, frames in entity.anims[action].items():
                for frame_index, tile_number in enumerate(frames):
                    index.setdefault(
                        tile_number, SpriteFrame(name, action, direction, frame_index)
                    )
    return index


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

    Coverage: gex's ``monsters.jsonc`` carries all ten monster families
    (ghost, grunt, demon, lobber, sorcerer, supersorc, death, acid, it, plus
    the aux-grunt sharing grunt's table), ``heroes.jsonc`` the four player
    classes, and ``npcs.jsonc`` the thief (which the mugger reuses). What
    this index deliberately does not cover is the two entity families that
    are not 8-direction animation records at all -- projectiles and dragon
    segments -- because their picture words come from flat ROM tables rather
    than a per-direction animation; ``AssetStore.sprite()`` dispatches those
    through ``gex.projectiles``/``gex.dragon`` before it consults this map,
    and placed pickups through ``gex.items``. Between the four paths, every
    maze object type 0-63 that has a static sprite resolves.

    **This map cannot be right for every caller, and that is the point of
    ``kind``.** Monsters and heroes do *not* have disjoint tile ranges: the
    Sorcerer and the Super Sorcerer are drawn from the Wizard's own artwork,
    so 40 tile numbers -- every Wizard walk/idle frame plus half his fight and
    shoot cycles -- belong to three entities at once. A single flat map has to
    pick one, and whichever it picks is wrong for the other two: monsters-first
    renders the Wizard through the Sorcerer's ``base`` palette bank, and
    heroes-first would recolour both Sorcerers. The flat map keeps the
    monsters-first answer (a placed maze object's picture is a monster far more
    often than not), and callers that know what they are holding -- the MOB
    layer knows the player slots and every creature's object type -- say so
    with ``kind`` and get the scoped map instead.
    """
    return _index_entities({**MONSTERS, **HEROES, **NPCS})


# Action precedence for the picture-number map: the canonical action that owns
# a shared tile wins. "walk" is what a placed maze object's base picture means;
# "idle"/others only fill tiles no higher-precedence action already claimed.
_ACTION_PRECEDENCE = ("walk", "fight", "shoot", "idle")


def _action_rank(action: str) -> int:
    """Sort key: known actions by precedence, unknown actions last (stable)."""
    try:
        return _ACTION_PRECEDENCE.index(action)
    except ValueError:
        return len(_ACTION_PRECEDENCE)


# Built once at import time: pure Python data from gex's bundled jsonc, no
# ROM I/O, so this is safe to compute even when no ROMs are configured.
_PICTURE_INDEX: dict[int, SpriteFrame] = _build_picture_index()

#: The three entity *families* gex carries 8-direction animation records for.
#: These are the coarse ``kind`` values ``sprite()``/``sprite_frame()`` accept
#: (an individual entity name -- "wizard", "ghost", "thief" -- is accepted too,
#: and is what the MOB layer actually passes, since it always knows exactly
#: which creature a slot holds).
MONSTER_KIND = "monster"
HERO_KIND = "hero"
NPC_KIND = "npc"

#: ``constants.Character`` order -> gex hero name. The ROM indexes every
#: per-class table by the same 0-3 class number (doc/05_data_reference.md §8's
#: player animation tables, ``char * (8 * frames) + ...``), and gex's
#: ``heroes.jsonc`` keys are those four classes -- so this tuple is the whole
#: translation between ``Player.character`` and ``AssetStore.sprite(kind=...)``.
HERO_NAMES: tuple[str, ...] = ("warrior", "valkyrie", "wizard", "elf")

_FAMILIES: dict[str, dict] = {
    MONSTER_KIND: MONSTERS,
    HERO_KIND: HEROES,
    NPC_KIND: NPCS,
}

#: ``kind`` -> the picture map scoped to it. A family key indexes just that
#: family; an entity key indexes just that one entity, which is the only way to
#: separate the Sorcerer from the Super Sorcerer (they share 24 tiles with each
#: other as well as with the Wizard). Lookup order in ``_frame_for`` is scoped
#: map first, flat map second, so ``kind`` never *loses* a picture -- a hero
#: slot momentarily holding a non-hero picture (the death-animation frames of
#: ``players._PLAYER_DEATH_PICTURE``, the bonus-screen icon ``score`` parks in
#: the player's slot) still resolves exactly as it did before.
def _build_scoped_indexes() -> dict[str, dict[int, SpriteFrame]]:
    scoped: dict[str, dict[int, SpriteFrame]] = {}
    for family, members in _FAMILIES.items():
        scoped[family] = _index_entities(members)
    for members in _FAMILIES.values():
        for name, entity in members.items():
            if name in scoped:
                # One namespace, so a gex entity named after a family would
                # silently shadow it and quietly change what every caller
                # passing that family gets back. Refuse to load instead.
                raise AssetError(
                    f"gex entity {name!r} collides with a sprite family name; "
                    f"kind would be ambiguous (families: {sorted(_FAMILIES)})"
                )
            scoped[name] = _index_entities({name: entity})
    return scoped


_PICTURE_INDEX_BY_KIND: dict[str, dict[int, SpriteFrame]] = _build_scoped_indexes()

if set(HERO_NAMES) != set(HEROES):        # pragma: no cover - guards a data change
    raise AssetError(
        f"HERO_NAMES {HERO_NAMES} no longer matches gex's hero classes "
        f"{sorted(HEROES)}; render.mobs.sprite_kind indexes it by "
        "Player.character"
    )

# Name -> entity record (monster, hero, or NPC).  Heroes and NPCs use their
# palette index directly; monsters offset it by the strength tier.
_ENTITIES = {**MONSTERS, **HEROES, **NPCS}
_DIRECT_PNUM_NAMES = frozenset(HEROES) | frozenset(NPCS)

#: mob_picture bits 14-0 are the tile number; bit 15 is a separate software
#: flag (gauntpy/src/gauntpy/mob.py's MobTable docstring; consistent with
#: every "N | tile | picture+flag" row in doc/05_data_reference.md's fixed
#: object picture table, e.g. "Potion (destr) | ... | 2300+flag | bit 15").
PICTURE_TILE_MASK = 0x7FFF

#: The three words maze placement stamps *instead of* a sprite (doc/04 §5.4):
#: 0x8000 a solid wall, 0x8001 a floor-level marker (stun tile, trap, exit,
#: transporter), 0x8003 the alternate wall style used when the maze's wall
#: pattern is 6 or 0xB. The playfield layer draws all three from the tile
#: descriptors, so asking the sprite bridge for one is a caller bug -- and one
#: worth naming, because 0x8000 masks to tile 0, which gex's item table happens
#: to hold as its "blank" entry. Without this it would quietly return blank
#: pixels instead of saying what went wrong.
MARKER_PICTURES = frozenset((0x8000, 0x8001, 0x8003))


# ---------------------------------------------------------------------------
# Raw tile blocks: effects, and anything whose size the MOB word carries
# ---------------------------------------------------------------------------

class TileBlock(NamedTuple):
    """A rectangle of consecutive tile numbers plus the palette bank it is
    drawn through -- the whole of what the MOB hardware stamps for a picture
    word.

    An animation record (``gex.monsters``/``heroes``/``npcs``) states the same
    four things per entity; this is the shape for everything that has a size
    without having an animation table, which is every transient effect and
    every raw-block fallback below.
    """

    xsize: int
    ysize: int
    ptype: str
    pnum: int


#: The bank a raw tile block falls back to when nothing names a better one:
#: the shared ``base`` MOB palette, entry 0. Every effect the game spawns is
#: drawn through ``base`` -- only creatures have private banks.
DEFAULT_BLOCK_PTYPE = "base"
DEFAULT_BLOCK_PNUM = 0

#: ``mob_vpos`` holds *width - 1* in bits 5-3 and *height - 1* in bits 2-0
#: (``coords.decode_vpos``), so 8 tiles / 64 px on a side is the largest sprite
#: the hardware word can describe and 1 the smallest. A ``size`` outside that
#: did not come from a MOB record and is a caller bug, not missing art.
MAX_BLOCK_TILES = 8

# The block geometry the ROM's own placement code gives each effect family.
# gex's effects.jsonc carries the picture *words* (the tables at 0x579F2 /
# 0x576B6 / 0x576D2 / 0x576DA) but not the size or palette nibble, because
# those live at the call sites that spawn the MOB rather than in the tables --
# and gauntpy already transcribes every one of them:
#
#   score popups   ``shots._playfield_showscore`` (0x49498): the size and
#                  palette go into the popup MOB's own H/V words, three tiles
#                  wide + palette 5 for the score-value popups at 0x4954A, two
#                  wide + palette 1 for the bonus popups at 0x4956A -- which is
#                  also exactly the spacing of the two halves of the table
#                  (0x1DB4, 0x1DB7, ... three apart; 0x25F6, 0x25F8, ... two).
#   floating stars ``shots.tport_cycle_start`` -> ``_place_effect`` with
#                  ``vpos + 0x12`` = 3x3 tiles, ``hpos + 1`` = palette 1. gex
#                  states the same 3x3 geometry itself (``STAR_XSIZE``/
#                  ``STAR_YSIZE``/``star_stamp``), so its constants are used
#                  and this port's placement is the cross-check.
#   impact bursts  ``shots.shot_impact_spawn`` -> ``_place_effect`` with
#                  ``vpos + 9`` = 2x2 tiles, ``hpos + 1`` = palette 1; again
#                  the table's own stride (0x1C5C, 0x1C60, 0x1C64).
#
# The palette nibble here is only the *default*: a caller holding the live
# ``mob_hpos`` word passes it as ``palette`` and that wins, exactly as it does
# for creatures.
_SCORE_POPUP_VALUE = TileBlock(3, 1, DEFAULT_BLOCK_PTYPE, 5)
_SCORE_POPUP_BONUS = TileBlock(2, 1, DEFAULT_BLOCK_PTYPE, 1)
#: First index of the bonus half of ``score_popup`` -- ``playfield_showscore``
#: branches on ``popup < 0x0A`` (0x49542).
_SCORE_POPUP_BONUS_FIRST = 0x0A
_SCORE_STAR = TileBlock(STAR_XSIZE, STAR_YSIZE, STAR_PTYPE, STAR_PNUM)
_SCORE_FX = TileBlock(2, 2, DEFAULT_BLOCK_PTYPE, 1)

#: ``tport_transition_pictures`` -- ROM 0x578F2, the sparkle both transporter
#: transition loops step their animation MOB through (the twelve-word table is
#: symmetric, so these six words are all of its distinct frames; the same
#: transcription lives in ``subsystems/score.py`` as
#: ``_TPORT_TRANSITION_PICTURES``, and ``subsystems/players.handle_tport``
#: installs the first of them). They are real ROM tile blocks that gex's
#: effects metadata does not list, so the dispatch below would otherwise skip
#: every transporter arrival and level transition in the game.
TPORT_TRANSITION_PICTURES: tuple[int, ...] = (
    0x1DCF, 0x1DD8, 0x1DE1, 0x1DEA, 0x1DF3, 0x1E00,
)
#: ``handle_tport`` (0x47CFE) places that MOB with ``vpos + 0x12`` (3x3 tiles)
#: and ``hpos + 1`` (palette 1), the same nudges the shared effect pool uses.
_TPORT_TRANSITION = TileBlock(3, 3, DEFAULT_BLOCK_PTYPE, 1)

#: Every table name ``_build_effect_blocks`` knows how to size. gex growing a
#: new effect table must not silently mean "still no sprite for those".
_KNOWN_EFFECT_TABLES = frozenset(
    ("score_popup", "score_star", "score_fx_a", "score_fx_b")
)


def _build_effect_blocks() -> dict[int, TileBlock]:
    """Masked picture number -> tile block, for every effect picture gex's
    ``effects.jsonc`` carries plus the transporter transition cycle.

    Keyed by the *masked* tile number so the bit-15 software flag never
    changes the dispatch, and built with ``setdefault`` so the first family to
    claim a word keeps it (the tables repeat words to hold a frame for two
    ticks, and nothing across families collides today).
    """
    unknown = sorted(set(EFFECT_TABLES) - _KNOWN_EFFECT_TABLES)
    if unknown:        # pragma: no cover - guards a gex data change
        raise AssetError(
            f"gex.effects gained table(s) {unknown} that gauntpy has no block "
            f"geometry for; AssetStore.sprite() would skip every picture in "
            f"them (known tables: {sorted(_KNOWN_EFFECT_TABLES)})"
        )

    blocks: dict[int, TileBlock] = {}

    def claim(word: int, block: TileBlock) -> None:
        blocks.setdefault(word & PICTURE_TILE_MASK, block)

    # gex states the star geometry itself, and STAR_TILES is already the
    # masked, de-duplicated set of them.
    for tile in STAR_TILES:
        claim(tile, _SCORE_STAR)
    for index, word in enumerate(EFFECT_TABLES["score_popup"]):
        claim(
            word,
            _SCORE_POPUP_VALUE
            if index < _SCORE_POPUP_BONUS_FIRST
            else _SCORE_POPUP_BONUS,
        )
    for family in ("score_fx_a", "score_fx_b"):
        for word in EFFECT_TABLES[family]:
            claim(word, _SCORE_FX)
    for word in TPORT_TRANSITION_PICTURES:
        claim(word, _TPORT_TRANSITION)
    return blocks


#: Built at import time from gex's bundled data -- pure Python, no ROM I/O.
EFFECT_PICTURES: dict[int, TileBlock] = _build_effect_blocks()


def _entity_default_pnum(name: str, entity, tier: int) -> int:
    """The palette entry an entity is drawn through when the caller has no
    live ``mob_hpos`` nibble. Heroes and NPCs use their own index directly;
    monsters offset it by the strength tier the way gex's ``domonster`` does.
    """
    if name in _DIRECT_PNUM_NAMES:
        return entity.pnum
    return entity.pnum + (tier + 1)



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

    def title_logo(self) -> Image.Image:
        """The native 328x48 title wordmark decoded from the graphics ROMs.

        gex caches the decode process-wide and returns an independent image.
        The bundled data contains only the reverse-engineered tile layout; the
        artwork itself always comes from the user's ROM dump.
        """
        try:
            return title_logo_image()
        except GexError as exc:
            raise AssetError(f"Could not decode the title logo: {exc}") from exc

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

    @staticmethod
    def _frame_for(masked: int, kind: str | None) -> SpriteFrame | None:
        """The sprite frame for an already-masked tile number, preferring the
        entity (or family) named by ``kind``.

        ``kind`` disambiguates the 40 tile numbers the Wizard shares with the
        Sorcerer and Super Sorcerer -- see ``_build_picture_index``. It is a
        *preference*, not a filter: a picture the named entity does not own
        falls through to the flat map, so a hero slot holding a death frame or
        an item icon still resolves.
        """
        if kind is not None:
            scoped = _PICTURE_INDEX_BY_KIND.get(kind)
            if scoped is None:
                raise AssetError(
                    f"Unknown sprite kind {kind!r}; valid kinds: the families "
                    f"{sorted(_FAMILIES)} and the entity names "
                    f"{sorted(_ENTITIES)}"
                )
            frame = scoped.get(masked)
            if frame is not None:
                return frame
        return _PICTURE_INDEX.get(masked)

    def sprite_frame(self, picture: int, *, kind: str | None = None) -> SpriteFrame:
        """Identify which sprite frame a raw MOB picture number names,
        without building a Stamp. Raises ``AssetError`` if the picture
        number isn't in any animation table gex currently knows about (see
        ``_build_picture_index``'s docstring for what that map covers).

        ``kind`` names the entity (``"wizard"``) or family (``"hero"``) the
        caller knows the picture belongs to, and settles the tiles more than
        one entity claims. Without it the answer is the flat map's
        monsters-first one.

        Projectiles, dragon segments and placed pickups are *not* animation
        records and never appear here even though ``sprite()`` renders them --
        the error message says so, because "no sprite frame" and "no sprite"
        are different failures and the second one is what a caller usually
        wants to hear about.
        """
        masked = picture & PICTURE_TILE_MASK
        frame = self._frame_for(masked, kind)
        if frame is None:
            raise AssetError(self._no_sprite_message(picture, masked))
        return frame

    @staticmethod
    def _no_sprite_message(picture: int, masked: int) -> str:
        if picture in MARKER_PICTURES:
            return (
                f"Marker words like {picture:#06x} have no sprite: maze "
                "placement writes 0x8000 (solid wall), 0x8001 (floor marker) "
                "or 0x8003 (alternate wall style) instead of a picture, and "
                "the playfield tile layer draws them (doc/04 §5.4)."
            )
        return (
            f"No known sprite frame for MOB picture number {picture:#06x} "
            f"(tile {masked:#06x} after masking off bit 15, the "
            "software flag -- doc/05_data_reference.md mob_picture "
            "entry). This tile is in no 8-direction animation table: gex "
            f"knows monsters {sorted(MONSTERS)}, heroes {sorted(HEROES)} "
            f"and NPCs {sorted(NPCS)}. Projectiles, dragon segments, effects "
            "and pickups are not animation records -- ask sprite() for those, "
            "and pass sprite(size=...) for artwork no table names at all."
        )

    def sprite(
        self,
        picture: int,
        *,
        tier: int = 1,
        palette: int | None = None,
        kind: str | None = None,
        size: tuple[int, int] | None = None,
    ) -> Stamp:
        """The multi-tile ``Stamp`` for a raw MOB picture number
        (``mob_picture`` / ``MobTable.picture``).

        Six dispatch paths, tried in the order that makes each one's test
        conclusive: projectiles, dragon segments and effects are recognised by
        membership in their flat ROM picture tables, creatures by the
        animation-table index, placed pickups by the item picture index, and
        anything still unnamed by ``size`` -- the MOB's own word (below).

        ``kind`` says which entity (``"wizard"``) or family (``"hero"``) the
        caller knows it is holding, and is what makes a Wizard render as a
        Wizard: he shares 40 tile numbers with the Sorcerer and Super
        Sorcerer, and the flat index has to hand those to one of the three
        (see ``_build_picture_index``). The entity chosen this way decides the
        sprite's *size* and *palette bank* -- so ``kind`` picks the bank,
        ``palette`` still picks the entry within it.

        ``palette`` names the MOB palette directly and wins when given -- that
        is ``mob_hpos`` bits 3-0, which the maze places from
        ``mazeobj_hsize_tier_tbl`` and combat then decrements, so passing it
        makes a wounded monster change colour the way the original does
        (doc/08 known issues, "that nibble is the MOB palette number"). Banks
        are not all the same depth (``base`` has 12 entries, a hero's own bank
        4), so a nibble that names nothing in the resolved entity's bank falls
        back to that entity's default rather than raising -- the sprite is
        still the right sprite, and the alternative is a hero who vanishes for
        a frame.

        ``tier`` is the fallback for callers that do not have the live word:
        it selects the palette variant the way gex's own CLI does for a name
        like ``"ghost2-walk-up"``, ``pal_num = mon.pnum + (tier + 1)`` (see
        ``python-gex/src/gex/monsters.py`` ``domonster()``, which calls this
        ``monster_level``). Renamed here to avoid clashing with gauntpy's
        ``levelnum_current`` (the *dungeon* level) -- this is the
        monster-strength tier from ``MazeObjIds.GEN_GHOST1/2/3`` and friends,
        a different axis entirely.

        ``size`` is ``(width, height)`` in 8x8 tiles, straight out of the
        MOB's own ``mob_vpos`` word (``coords.decode_vpos``), and is what makes
        the artwork that is in *no* table render anyway -- see
        ``_sized_block``. It is consulted last, so it never changes what a
        named picture resolves to, and it is only consulted at all when the
        caller supplies it: a bare ``sprite(0x0001)`` still raises.
        """
        masked = picture & PICTURE_TILE_MASK
        if picture in MARKER_PICTURES:
            raise AssetError(self._no_sprite_message(picture, masked))
        # Projectiles are 2x2 base-palette shots, not 8-direction creatures.
        # gex's own projectile_stamp/segment_stamp rebuild (and re-fill) a
        # Stamp on every call; going through self.stamp() with the identical
        # gex constants keeps every shot and dragon segment on the shared
        # cache instead of allocating one per frame.
        if masked in PROJECTILE_TILES:
            return self._block_stamp(masked, SHOT_XSIZE, SHOT_YSIZE, SHOT_PTYPE, SHOT_PNUM)
        # Dragon head/body segments are 4x4 base-palette sprites.
        if masked in DRAGON_SEGMENT_TILES:
            return self._block_stamp(
                masked, SEGMENT_XSIZE, SEGMENT_YSIZE, SEGMENT_PTYPE, SEGMENT_PNUM
            )
        # Effects: score popups, the floating score star, the two impact
        # bursts and the transporter sparkle. Flat ROM picture tables like the
        # two above rather than animation records, and every one of them is a
        # transient MOB the game spawns constantly -- without this they were
        # the most frequently *skipped* sprites in a live frame.
        effect = EFFECT_PICTURES.get(masked)
        if effect is not None:
            return self._block_stamp(
                masked, effect.xsize, effect.ysize, effect.ptype,
                self._bank_index(effect.ptype, effect.pnum, palette),
            )
        # Creatures: monsters / heroes / NPCs (8-direction animation entities).
        frame = self._frame_for(masked, kind)
        if frame is not None:
            entity = _ENTITIES[frame.monster_type]
            default_pnum = _entity_default_pnum(frame.monster_type, entity, tier)
            pal_num = self._bank_index(entity.ptype, default_pnum, palette)
            tiles = tuple(range(masked, masked + entity.xsize * entity.ysize))
            return self.stamp(tiles, entity.xsize, entity.ptype, pal_num)
        # Placed maze objects: treasure, keys, potions, food, power-ups, etc.
        item = item_stamp_for_picture(picture)
        if item is not None:
            return item
        # Named by nothing -- but a caller holding the MOB record still knows
        # how big it is, and that is the hardware's own answer.
        block = self._sized_block(picture, masked, size, tier, palette, kind)
        if block is not None:
            return block
        # Nothing matched -- sprite_frame() raises the descriptive AssetError.
        raise self._no_sprite_error(picture)

    @staticmethod
    def _bank_index(ptype: str, default_pnum: int, palette: int | None) -> int:
        """The palette entry to use inside bank ``ptype``: the live
        ``mob_hpos`` nibble when the caller has it, the bank's own default
        when it does not -- or when the bank has no such entry, since banks
        are not all the same depth and a sprite in its standing colour beats a
        sprite that vanished.
        """
        if palette is None:
            return default_pnum
        pal_num = palette & 0x0F
        if 0 <= pal_num < len(GAUNTLET_PALETTES.get(ptype, ())):
            return pal_num
        return default_pnum

    def _sized_block(
        self,
        picture: int,
        masked: int,
        size: tuple[int, int] | None,
        tier: int,
        palette: int | None,
        kind: str | None,
    ) -> Stamp | None:
        """The last dispatch path: stamp ``size`` tiles of raw ROM straight
        from ``masked``, or ``None`` when the caller gave no size.

        **Why this exists.** A picture word plus a size word is all the MOB
        hardware ever gets: it stamps ``width * height`` consecutive tiles
        starting at the picture and colours them with the ``mob_hpos`` nibble.
        Every table above is *metadata* about which picture means what -- and
        that metadata is not complete, because the game plays real artwork
        that is in no animation table at all. The hero exit/death dissolve of
        ``players._PLAYER_EXIT_PICTURE`` is the clearest case: seven 3x3
        blocks per class, 27 of the 28 in no gex record (the odd one out is
        also one of the Warrior's shooting frames), so every hero that reached
        an exit or died simply stopped being drawn mid-animation.

        **Why it does not hide real errors.** It only runs when the caller
        passes a size it actually has -- the MOB layer reads it out of
        ``mob_vpos``; a caller who is merely guessing at a picture number
        passes nothing and still gets the descriptive ``AssetError``. A size
        the hardware word cannot even encode is reported as the caller bug it
        is, and tiles that are not in the ROM still fail: ``stamp()`` turns
        gex's ``TileError`` into an ``AssetError`` naming the block, so
        "picture points at nothing" stays distinguishable from "picture points
        at art we had no table for".

        The bank comes from ``kind`` when it names an entity -- that is what
        keeps a dissolving Warrior in the Warrior's own colours instead of the
        shared ``base`` bank -- then the live ``palette`` nibble picks the
        entry inside it, exactly as for a named creature.
        """
        if size is None:
            return None
        xsize, ysize = size
        if not (1 <= xsize <= MAX_BLOCK_TILES and 1 <= ysize <= MAX_BLOCK_TILES):
            raise AssetError(
                f"MOB picture {picture:#06x} was given size {xsize}x{ysize}, "
                f"which mob_vpos cannot encode: bits 5-3 and 2-0 hold "
                f"width-1/height-1, so both must be 1..{MAX_BLOCK_TILES} "
                "(coords.decode_vpos)."
            )
        entity = _ENTITIES.get(kind) if kind is not None else None
        if entity is None:
            ptype, default_pnum = DEFAULT_BLOCK_PTYPE, DEFAULT_BLOCK_PNUM
        else:
            ptype = entity.ptype
            default_pnum = _entity_default_pnum(kind, entity, tier)
        pnum = self._bank_index(ptype, default_pnum, palette)
        tiles = tuple(range(masked, masked + xsize * ysize))
        try:
            return self.stamp(tiles, xsize, ptype, pnum)
        except AssetError as exc:
            raise AssetError(
                f"MOB picture {picture:#06x} names a {xsize}x{ysize} block of "
                f"tiles {tiles[0]:#06x}-{tiles[-1]:#06x}, which the tile ROMs "
                f"do not hold: {exc}"
            ) from exc

    def _block_stamp(
        self, tile: int, xsize: int, ysize: int, ptype: str, pnum: int
    ) -> Stamp:
        """A cached ``xsize x ysize`` block of consecutive tiles from ``tile``."""
        return self.stamp(tuple(range(tile, tile + xsize * ysize)), xsize, ptype, pnum)

    def _no_sprite_error(self, picture: int) -> AssetError:
        try:
            self.sprite_frame(picture)
        except AssetError as exc:
            return exc
        # Unreachable: sprite() only gets here when the index lookup missed.
        return AssetError(f"No sprite for MOB picture number {picture:#06x}")
