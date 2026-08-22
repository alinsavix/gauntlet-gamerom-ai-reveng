"""MOB layer -- every dynamic thing: players, monsters, shots, items lying
on the floor, animations. PLAN.md §6 WP-2 step 2.

The depth chain (``mob.py``, ``doc/04_game_subsystems.md`` §24) is walked in
chain order, entering near the first on-screen SLIP band as the hardware does
(``doc/01_hardware.md`` §8.4) -- both for speed (skip everything below the
visible strip without a search) and because **chain order is draw priority**:
MOBs later in the chain paint over MOBs earlier in it. Insertion order is by
vertical band (``MobTable.insert``'s sort key), so this reproduces the
pseudo-depth effect of things lower on screen drawing in front of things
higher up.

"Near", not "at": a band records where a MOB's *cell* is, and a sprite is up to
eight tiles tall and can straddle the edge of the viewport (or, for a hero,
sit rows away from the record slot it never leaves). ``_chain_band_window``
widens the walk by exactly that much so the bounding-box test is the only thing
that decides what is on screen.

``iter_visible_mobs`` is deliberately pure -- ``GameState`` in, an ordered
list of what-to-draw-where out, no ``AssetStore`` involved. That is what lets
``tests/test_render.py`` assert draw order (a PLAN.md §6 WP-2 acceptance
criterion) without any ROMs: build a MobTable, call this function, check the
slot order. ``draw_mob_layer`` is the thin, ROM-needing layer on top that
turns each entry into actual pixels.
"""

from __future__ import annotations

from typing import Iterator, NamedTuple, Protocol

from ..assets import HERO_NAMES, AssetError
from ..constants import (
    NUM_SLIP_BANDS, SLIP_BAND_PIXELS, SLOT_DEMON_SHOTS,
    SLOT_PLAYER_SHOTS, MazeObjIds,
)
from ..coords import CELL_PIXELS, decode_hpos, decode_vpos, sprite_top_y
from ..state import GameState

__all__ = [
    "MobDrawInfo", "SpriteSource", "iter_visible_mobs", "draw_mob_layer",
    "strength_tier", "sprite_kind", "MAX_MOB_TILES", "MAX_MOB_PIXELS",
    "BAND_SLACK_PIXELS",
]

#: Per-creature ``(full-strength hpos nibble, the sprite tier that nibble
#: means)``. The nibbles are ``mazeobj_hsize_tier_tbl`` (ROM 0x5864C, the same
#: rows ``subsystems/shots.py`` and ``subsystems/monsters.py`` transcribe);
#: the tier is which of gex's ``<family><N>`` palette variants that
#: full-strength form is. Acid and Death have a single strength, so their
#: table entry *is* tier 1; the eight-family three-step creatures top out at
#: tier 3 and step down one tier per point of damage
#: (``doc/04_game_subsystems.md`` §26: a monster lives while its nibble stays
#: in ``[base-2, base]``).
_TIER_TABLE: dict[int, tuple[int, int]] = {
    int(MazeObjIds.MONST_GHOST):     (0x4, 3),
    int(MazeObjIds.MONST_GRUNT):     (0x4, 3),
    int(MazeObjIds.MONST_AUX_GRUNT): (0x4, 3),
    int(MazeObjIds.MONST_DEMON):     (0x8, 3),
    int(MazeObjIds.MONST_IT):        (0x8, 3),
    int(MazeObjIds.MONST_LOBBER):    (0xB, 3),
    int(MazeObjIds.MONST_SORC):      (0xB, 3),
    int(MazeObjIds.MONST_SUPERSORC): (0xB, 3),
    int(MazeObjIds.MONST_ACID):      (0x1, 1),
    int(MazeObjIds.MONST_DEATH):     (0x0, 1),
}

_MIN_TIER, _MAX_TIER = 1, 3

#: MOB object type -> the ``gex`` entity whose animation table its pictures come
#: from -- the ``kind`` ``AssetStore.sprite()`` disambiguates with.
#:
#: This exists because the picture number alone is *not* enough. The Sorcerer
#: and Super Sorcerer are drawn from the Wizard's own artwork, so 40 tile
#: numbers belong to three entities at once and the asset store's flat index has
#: to pick one of them (see ``assets._build_picture_index``). The MOB layer does
#: not have to guess: ``mob_link`` bits 15-10 carry the object type, and for a
#: hero ``Player.character`` names the class outright.
_MONSTER_ENTITY: dict[int, str] = {
    int(MazeObjIds.MONST_GHOST):     "ghost",
    int(MazeObjIds.MONST_GRUNT):     "grunt",
    int(MazeObjIds.MONST_AUX_GRUNT): "grunt",
    int(MazeObjIds.MONST_DEMON):     "demon",
    int(MazeObjIds.MONST_LOBBER):    "lobber",
    int(MazeObjIds.MONST_SORC):      "sorcerer",
    int(MazeObjIds.MONST_SUPERSORC): "supersorc",
    int(MazeObjIds.MONST_DEATH):     "death",
    int(MazeObjIds.MONST_ACID):      "acid",
    int(MazeObjIds.MONST_IT):        "it",
}

#: The tallest a MOB can legally be. ``mob_vpos`` bits 2-0 hold *height - 1* in
#: 8px tiles (``coords.decode_vpos``), so eight tiles / 64 px is the ceiling the
#: hardware word itself imposes -- nothing in the game can be taller.
MAX_MOB_TILES = 8
MAX_MOB_PIXELS = MAX_MOB_TILES * 8

#: How far a sprite's top edge may sit from the world row its SLIP band names.
#: ``MobTable.band_of`` derives the band from the record's *cell row* (the ROM's
#: own rule, 0x5DCD6-0x5DCE6), while the sprite is drawn from ``mob_vpos``; a
#: creature's pixels lead its cell by up to half a cell in either direction
#: (``monsters._destination_cell``'s +8px bias), and maze placement can nudge a
#: sprite wider than its cell. One whole cell is the bound on that gap.
BAND_SLACK_PIXELS = MAX_MOB_PIXELS - CELL_PIXELS

# palette_hurt_{warrior,valkyrie,wizard,elf} (0x404AE/0x404D0/0x404F8/
# 0x4051A) copy white from the 0x5B20E hurt-cycle tables into these class-local
# palette entries while 0x905F30 is nonzero.
_PLAYER_HURT_PALETTE_INDICES = (
    (5, 12),
    (6, 8, 9),
    (6, 8, 10),
    (11, 12),
)
_HURT_WHITE_RGBA = (225, 225, 225, 255)  # IRGB 0xFFFF


def _player_hurt_palette(
    state: GameState, slot: int, palette_rgba: list,
) -> list:
    """Apply the live hurt-palette RAM overlay for a hero MOB."""
    player = next(
        (
            player for player in state.players
            if player.mob_slot == slot and player.status
        ),
        None,
    )
    if player is None or player.hurt_cooldown == 0:
        return palette_rgba
    flashed = list(palette_rgba)
    for index in _PLAYER_HURT_PALETTE_INDICES[player.character & 0x03]:
        flashed[index] = _HURT_WHITE_RGBA
    return flashed


def strength_tier(state: GameState, slot: int) -> int:
    """The sprite/palette tier of the creature in ``slot`` -- the default
    ``tier_for`` (see ``draw_mob_layer``).

    This is not a guess any more. ``doc/01_hardware.md`` §8.2 says
    ``mob_hpos`` bits 3-0 **are** the hardware MOB palette number, and
    ``doc/04_game_subsystems.md`` §26 says the game keeps a monster's live
    health tier in exactly those bits ("health/tier = the target's own hpos low
    nibble ... otherwise it survives as a weaker tier"). A hit that drops the
    nibble therefore changes the hardware palette: that *is* how a weakened
    monster visibly changes colour. Mapping the nibble back through
    ``_TIER_TABLE`` reproduces it, and lands on exactly the palette index the
    hardware would have used (asserted in ``tests/test_render.py``).

    Non-creature slots -- items, shots, dragon segments, the player -- keep
    tier 1: their sprites are not tiered and their stamps carry their own
    palette.
    """
    entry = _TIER_TABLE.get(state.mobs.obj_type(slot))
    if entry is None:
        return _MIN_TIER
    base, full_tier = entry
    nibble = state.mobs.hpos[slot] & 0x0F
    return max(_MIN_TIER, min(_MAX_TIER, full_tier - (base - nibble)))


class MobDrawInfo(NamedTuple):
    """One MOB's draw-relevant state, already decoded out of the packed
    words -- everything ``draw_mob_layer`` needs except the actual pixels.
    """

    slot: int
    x: int          # world pixel, top-left corner (coords.decode_hpos)
    y: int          # world pixel, top-left corner (coords.sprite_top_y)
    width_px: int
    height_px: int
    picture: int     # raw mob_picture, bit 15 (software flag) not yet masked
    palette: int     # mob_hpos bits 3-0 -- see draw_mob_layer's tier note
    kind: str | None = None   # gex entity name -- see sprite_kind()

    @property
    def size_tiles(self) -> tuple[int, int]:
        """``(width, height)`` in 8x8 tiles -- the MOB's own ``mob_vpos`` size
        field, back in the units the hardware states it in
        (``coords.decode_vpos``).

        This is ``AssetStore.sprite()``'s ``size``: a picture word plus this
        pair is all the MOB hardware ever gets, so together they can draw
        artwork that is in no animation, effect or item table -- the hero
        exit/death dissolve frames above all. See ``AssetStore._sized_block``.
        """
        return self.width_px // 8, self.height_px // 8


class SpriteSource(Protocol):
    """Whatever the MOB layer needs from an asset provider. Matches
    ``AssetStore.sprite()``'s signature exactly (structurally, not by
    inheritance) so tests can supply a ROM-free fake -- see
    ``tests/test_render.py``'s ``_FakeAssets``.
    """

    def sprite(
        self,
        picture: int,
        *,
        tier: int = 1,
        palette: int | None = None,
        kind: str | None = None,
        size: tuple[int, int] | None = None,
    ): ...
    def palette(self, kind: str, index: int): ...           # -> gex.palettes.Palette


def sprite_kind(state: GameState, slot: int) -> str | None:
    """Which ``gex`` entity the MOB in ``slot`` is -- ``AssetStore.sprite()``'s
    ``kind``, or ``None`` when the slot is not a creature the layer can name.

    Picture numbers are not unique across entities: the Sorcerer and Super
    Sorcerer use the Wizard's artwork, so a Wizard walk frame is *also* a
    Sorcerer walk frame. Resolved from the picture alone, a playing Wizard
    comes back as a Sorcerer and is drawn through the Sorcerer's ``base``
    palette bank instead of his own -- visibly the wrong hero. The MOB table
    already knows better, from two independent places:

    * a player's hero class is ``Player.character`` and its record slot is
      ``Player.mob_slot`` (``players.player_start_inner``), and
    * every other creature's family is ``mob_link`` bits 15-10, the object type.

    Players are checked first because a hero's record keeps the PLAYERSTART
    object type it was spawned from, which the thief's MOB also uses
    (``thief._thief_spawn``) -- so the type alone cannot tell a hero from an
    NPC, but the slot can.
    """
    for player in state.players:
        if player.mob_slot == slot and player.status:
            return HERO_NAMES[int(player.character) & 0x03]
    palette = state.mobs.hpos[slot] & 0x0F
    if slot in (*SLOT_PLAYER_SHOTS, *SLOT_DEMON_SHOTS) and palette >= 0x0C:
        player_index = palette - 0x0C
        return HERO_NAMES[int(state.players[player_index].character) & 0x03]
    return _MONSTER_ENTITY.get(state.mobs.obj_type(slot))


def _untracked_bands(state: GameState) -> Iterator[int]:
    """SLIP bands the chain walk must cover regardless of where the camera is.

    A MOB's band comes from its record slot's cell row, which is only a
    statement about where it *is* because the simulation moves a creature's
    record as it walks (``MobTable.move_slot`` -- "identity is location"). One
    family breaks that rule: a hero's record stays in the PLAYERSTART slot it
    was spawned into for the whole level (``players.player_start_inner``, and
    ``player_move`` only rewrites H/V), so a player who walks away from their
    spawn row keeps that row's band forever. Culling on it makes the hero
    vanish the moment the camera scrolls past their spawn row -- which is
    exactly what happens once you walk more than half a screen from it.

    Yielding their bands here widens the window instead of adding a second,
    out-of-order pass, so chain order (= draw priority) is untouched.
    """
    for player in state.players:
        if player.mob_slot and player.status:
            yield state.mobs.band_of(player.mob_slot)


def _chain_band_window(state: GameState, scroll_y: int, viewport_h: int) -> tuple[int, int]:
    """The SLIP band range the chain walk has to cover for a viewport at
    ``scroll_y``, per ``doc/01_hardware.md`` §8.4 (one band per 8 playfield
    scanlines, ``constants.SLIP_BAND_PIXELS`` = 8, ``NUM_SLIP_BANDS`` = 64
    covering the 512px world).

    Not simply the bands the viewport overlaps. A band names where a MOB's
    *cell* is; the sprite drawn from that record can extend up to
    ``MAX_MOB_PIXELS`` below its top edge and sit up to ``BAND_SLACK_PIXELS``
    away from the cell row itself, so a MOB anchored above the viewport can
    still have its body across the top of it -- a row-1 treasure (a 3x3-tile,
    24px sprite at world y 16, in band 2) is still on screen at ``scroll_y``
    24, where entering at ``scroll_y // 8`` would have started a band too late
    and walked straight past it. Widening the window by that geometry at both
    ends is what makes the bounding-box test the only thing that decides
    visibility; the walk still stops early, it just stops at the right band.
    """
    first_y = scroll_y - (MAX_MOB_PIXELS + BAND_SLACK_PIXELS)
    last_y = scroll_y + viewport_h - 1 + BAND_SLACK_PIXELS
    first = max(0, first_y // SLIP_BAND_PIXELS)
    last = min(NUM_SLIP_BANDS - 1, last_y // SLIP_BAND_PIXELS)
    for band in _untracked_bands(state):
        first = min(first, band)
        last = max(last, band)
    return first, max(first, last)


def iter_visible_mobs(
    state: GameState, scroll_x: int, scroll_y: int, viewport_w: int, viewport_h: int
) -> Iterator[MobDrawInfo]:
    """Depth-chain order, entering at the first band that can hold a visible
    MOB and stopping once the chain passes the last one -- "Use the SLIP band
    heads to skip MOBs outside the visible bands" (PLAN.md §6 WP-2 step 2).
    Bands are monotonic non-decreasing along the chain (``MobTable.insert``'s
    sort key), so both the entry point and the early stop are safe.

    The window is ``_chain_band_window``'s, not the viewport's own band range:
    a band says where a MOB's *cell* is, and a sprite can hang below or beside
    that cell, so the walk has to start (and stop) far enough out that no
    partly-visible MOB is skipped before the bounding box gets to judge it.

    Yields only MOBs that are occupied, have a nonzero picture (picture 0 is
    "nothing to draw" -- also what the fixed-slot placeholders and the
    chain's own null terminator use), and whose bounding box intersects the
    viewport. Horizontally off-screen MOBs are skipped but the walk
    continues (the chain is band-sorted, not x-sorted, so an out-of-band-y
    MOB can still be anywhere in x).
    """
    mobs = state.mobs
    first_band, last_band = _chain_band_window(state, scroll_y, viewport_h)
    viewport_bottom = scroll_y + viewport_h
    viewport_right = scroll_x + viewport_w

    wrapped_y = (
        scroll_y + viewport_h > 512
        or scroll_y < MAX_MOB_PIXELS + BAND_SLACK_PIXELS
    )
    iterator = mobs.iter_chain() if wrapped_y else mobs.iter_from_band(first_band)
    for slot in iterator:
        band = mobs.band_of(slot)
        if not wrapped_y and band > last_band:
            break
        if not mobs.is_occupied(slot):
            continue
        picture = mobs.picture[slot]
        if picture & 0x7FFF == 0:
            continue

        x, _, palette = decode_hpos(mobs.hpos[slot])
        v_anchor, width_tiles, height_tiles = decode_vpos(mobs.vpos[slot])
        width_px, height_px = width_tiles * 8, height_tiles * 8
        # The V word counts *up* from the playfield floor to the bottom of the
        # MOB's 16-pixel maze cell, and hardware draws the sprite upward from
        # there: a 3x3 hero/monster begins eight pixels above the cell, a 4x4
        # dragon sixteen. ``coords.sprite_top_y`` is that one conversion, and
        # this is the only place the renderer needs it.
        y = sprite_top_y(v_anchor, height_px)

        draw_x = next(
            (
                candidate for candidate in (x - 512, x, x + 512)
                if candidate + width_px > scroll_x and candidate < viewport_right
            ),
            None,
        )
        if draw_x is None:
            continue
        draw_y = next(
            (
                candidate for candidate in (y - 512, y, y + 512)
                if candidate + height_px > scroll_y and candidate < viewport_bottom
            ),
            None,
        )
        if draw_y is None:
            continue

        yield MobDrawInfo(
            slot, draw_x, draw_y, width_px, height_px, picture, palette,
            sprite_kind(state, slot),
        )


def draw_mob_layer(
    fb,
    state: GameState,
    assets: SpriteSource,
    scroll_x: int,
    scroll_y: int,
    viewport: tuple[int, int, int, int],
    *,
    tier_for=None,
    shadow_src=None,
) -> None:
    """Draw every visible MOB, in chain order, onto ``fb``.

    **The palette comes from the MOB itself.** ``mob_hpos`` bits 3-0 *are* the
    hardware MOB palette number (``doc/01_hardware.md`` §8.2), and the game
    keeps a creature's live health tier in those same bits
    (``doc/04_game_subsystems.md`` §26) -- so the word ``iter_visible_mobs``
    already decoded is passed straight to ``AssetStore.sprite(palette=...)``.
    That is what makes a wounded monster change colour the way the original
    does, without this layer having to infer anything.

    ``tier_for(state, slot) -> int`` remains as the ``tier`` fallback for an
    asset provider that cannot honour a raw palette number; it defaults to
    ``strength_tier``, which derives the same value from that nibble the long
    way round. An asset store that supports ``palette`` ignores it.

    **Which creature, not just which picture.** ``sprite_kind`` resolves each
    slot to a gex entity from the MOB table itself (the player slots by
    ``Player.character``, everything else by object type) and that goes to the
    asset store as ``kind``. Without it a playing Wizard renders as a Sorcerer
    -- they share 40 tile numbers -- in the Sorcerer's palette bank.

    **How big it is.** ``mob_vpos`` bits 5-0 are the sprite's tile size, and
    that word plus the picture is the whole of what the MOB hardware draws --
    so it goes to the asset store as ``size`` (``MobDrawInfo.size_tiles``).
    That is what renders the artwork no table names: a hero's exit/death
    dissolve is seven 3x3 blocks per class that no gex animation record
    covers, so before this the hero simply stopped being drawn part-way
    through dying. ``kind`` still picks the bank, so a dissolving Warrior
    dissolves in the Warrior's colours.

    Sprites the asset store still cannot resolve -- a picture in no table,
    from a caller that has no size either -- raise ``AssetError``; this layer
    catches that per MOB and skips it rather than failing the whole frame, so
    the renderer degrades gracefully as gex's data grows instead of being
    all-or-nothing. The palette fetch is inside the same guard because a
    resolved sprite still names a bank/index pair the provider may not have.
    """
    dest_x, dest_y, vw, vh = viewport
    clip = (dest_x, dest_y, dest_x + vw, dest_y + vh)
    tier_for = tier_for or strength_tier
    palette_cache: dict[tuple[str, int], list] = {}

    for info in iter_visible_mobs(state, scroll_x, scroll_y, viewport[2], viewport[3]):
        try:
            stamp = assets.sprite(
                info.picture,
                tier=tier_for(state, info.slot),
                palette=info.palette,
                kind=info.kind,
                size=info.size_tiles,
            )
            pal_key = (stamp.ptype, stamp.pnum)
            palette_rgba = palette_cache.get(pal_key)
            if palette_rgba is None:
                palette_rgba = [c.to_rgba() for c in assets.palette(stamp.ptype, stamp.pnum)]
                palette_cache[pal_key] = palette_rgba
            palette_rgba = _player_hurt_palette(
                state, info.slot, palette_rgba,
            )
        except AssetError:
            continue

        screen_x = dest_x + (info.x - scroll_x)
        screen_y = dest_y + (info.y - scroll_y)
        max_cols, max_rows = info.size_tiles
        for idx, tile in enumerate(stamp.data):
            row, col = divmod(idx, stamp.width)
            if row >= max_rows or col >= max_cols:
                continue
            # Pixel special cases (doc/01_hardware.md §4/§6, Confidence:
            # Verified): 0 = transparent (trans0=True), 1 = shadow. A shadow
            # pixel shows the underlying playfield through the half-intensity
            # shadow palette (built by playfield.irgb_to_shadow, ROM 0x5FD80).
            # ``shadow_src`` (the compositor's ShadowSource over the cached
            # shadow raster) supplies that exact color; without it the blit
            # falls back to darkening in place. Verified by disassembly
            # (capstone, row76.bin) -- see playfield.irgb_to_shadow.
            fb.blit_indexed_tile(
                tile, palette_rgba,
                screen_x + col * 8, screen_y + row * 8,
                trans0=True, shadow_index=1, shadow_src=shadow_src, clip=clip,
            )
