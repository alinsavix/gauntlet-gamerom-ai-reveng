"""MOB layer -- every dynamic thing: players, monsters, shots, items lying
on the floor, animations. PLAN.md §6 WP-2 step 2.

The depth chain (``mob.py``, ``doc/04_game_subsystems.md`` §24) is walked in
chain order, entering at the first on-screen SLIP band exactly as the
hardware does (``doc/01_hardware.md`` §8.4) -- both for speed (skip
everything below the visible strip without a search) and because **chain
order is draw priority**: MOBs later in the chain paint over MOBs earlier in
it. Insertion order is by vertical band (``MobTable.insert``'s sort key), so
this reproduces the pseudo-depth effect of things lower on screen drawing in
front of things higher up.

``iter_visible_mobs`` is deliberately pure -- ``GameState`` in, an ordered
list of what-to-draw-where out, no ``AssetStore`` involved. That is what lets
``tests/test_render.py`` assert draw order (a PLAN.md §6 WP-2 acceptance
criterion) without any ROMs: build a MobTable, call this function, check the
slot order. ``draw_mob_layer`` is the thin, ROM-needing layer on top that
turns each entry into actual pixels.
"""

from __future__ import annotations

from typing import Iterator, NamedTuple, Protocol

from ..assets import AssetError
from ..constants import NUM_SLIP_BANDS, SLIP_BAND_PIXELS
from ..coords import decode_hpos, decode_vpos
from ..state import GameState

__all__ = ["MobDrawInfo", "SpriteSource", "iter_visible_mobs", "draw_mob_layer"]


class MobDrawInfo(NamedTuple):
    """One MOB's draw-relevant state, already decoded out of the packed
    words -- everything ``draw_mob_layer`` needs except the actual pixels.
    """

    slot: int
    x: int          # world pixel, top-left corner (coords.decode_hpos)
    y: int          # world pixel, top-left corner (coords.decode_vpos)
    width_px: int
    height_px: int
    picture: int     # raw mob_picture, bit 15 (software flag) not yet masked
    palette: int     # mob_hpos bits 3-0 -- see draw_mob_layer's tier note


class SpriteSource(Protocol):
    """Whatever the MOB layer needs from an asset provider. Matches
    ``AssetStore.sprite()``'s signature exactly (structurally, not by
    inheritance) so tests can supply a ROM-free fake -- see
    ``tests/test_render.py``'s ``_FakeAssets``.
    """

    def sprite(self, picture: int, *, tier: int = 1): ...  # -> gex.render.Stamp
    def palette(self, kind: str, index: int): ...           # -> gex.palettes.Palette


def _visible_band_range(scroll_y: int, viewport_h: int) -> tuple[int, int]:
    """SLIP bands overlapping ``[scroll_y, scroll_y + viewport_h)``, per
    ``doc/01_hardware.md`` §8.4 (one band per 8 playfield scanlines,
    ``constants.SLIP_BAND_PIXELS`` = 8, ``NUM_SLIP_BANDS`` = 64 covering the
    512px world).
    """
    first = max(0, scroll_y // SLIP_BAND_PIXELS)
    last_y = scroll_y + viewport_h - 1
    last = min(NUM_SLIP_BANDS - 1, max(first, last_y // SLIP_BAND_PIXELS))
    return first, last


def iter_visible_mobs(
    state: GameState, scroll_x: int, scroll_y: int, viewport_w: int, viewport_h: int
) -> Iterator[MobDrawInfo]:
    """Depth-chain order, entering at the first visible SLIP band and
    stopping once the chain passes the last one -- "Use the SLIP band heads
    to skip MOBs outside the visible bands" (PLAN.md §6 WP-2 step 2). Bands
    are monotonic non-decreasing along the chain (``MobTable.insert``'s sort
    key), so both the entry point and the early stop are safe.

    Yields only MOBs that are occupied, have a nonzero picture (picture 0 is
    "nothing to draw" -- also what the fixed-slot placeholders and the
    chain's own null terminator use), and whose bounding box intersects the
    viewport. Horizontally off-screen MOBs are skipped but the walk
    continues (the chain is band-sorted, not x-sorted, so an out-of-band-y
    MOB can still be anywhere in x).
    """
    mobs = state.mobs
    first_band, last_band = _visible_band_range(scroll_y, viewport_h)
    viewport_bottom = scroll_y + viewport_h
    viewport_right = scroll_x + viewport_w

    for slot in mobs.iter_from_band(first_band):
        band = mobs.band_of(slot)
        if band > last_band:
            break
        if not mobs.is_occupied(slot):
            continue
        picture = mobs.picture[slot]
        if picture & 0x7FFF == 0:
            continue

        x, _, palette = decode_hpos(mobs.hpos[slot])
        y, width_tiles, height_tiles = decode_vpos(mobs.vpos[slot])
        width_px, height_px = width_tiles * 8, height_tiles * 8

        if x + width_px <= scroll_x or x >= viewport_right:
            continue
        if y + height_px <= scroll_y or y >= viewport_bottom:
            continue

        yield MobDrawInfo(slot, x, y, width_px, height_px, picture, palette)


def draw_mob_layer(
    fb,
    state: GameState,
    assets: SpriteSource,
    scroll_x: int,
    scroll_y: int,
    viewport: tuple[int, int, int, int],
    *,
    tier_for=None,
) -> None:
    """Draw every visible MOB, in chain order, onto ``fb``.

    ``tier_for(state, slot) -> int`` selects the monster-strength palette
    tier per ``AssetStore.sprite``'s ``tier`` argument. **Flagged design
    decision:** no landed work package currently records a live monster's
    strength tier anywhere ``render/`` can read it (WP-1's own docstring
    notes the picture number alone doesn't encode it -- it's meant to live
    in MOB-specific state such as the hpos low-nibble hit-point tier WP-7's
    ``resolve_shot_hit`` will maintain, per PLAN.md's WP-7 entry). Until that
    lands, the default here is a constant ``tier=1`` ("standard" strength)
    for every MOB. Callers that already have tier information (tests, or a
    future package) can pass their own ``tier_for``.

    Sprites for object types gex's bundled animation data doesn't cover yet
    (``AssetStore``'s own documented gap -- every monster family except
    "ghost" as of WP-1) raise ``AssetError``; this layer catches that per
    MOB and skips it rather than failing the whole frame, so the renderer
    degrades gracefully as gex's data grows instead of being all-or-nothing.
    """
    dest_x, dest_y, vw, vh = viewport
    clip = (dest_x, dest_y, dest_x + vw, dest_y + vh)
    tier_for = tier_for or (lambda _state, _slot: 1)
    palette_cache: dict[tuple[str, int], list] = {}

    for info in iter_visible_mobs(state, scroll_x, scroll_y, viewport[2], viewport[3]):
        try:
            stamp = assets.sprite(info.picture, tier=tier_for(state, info.slot))
        except AssetError:
            continue

        pal_key = (stamp.ptype, stamp.pnum)
        palette_rgba = palette_cache.get(pal_key)
        if palette_rgba is None:
            palette_rgba = [c.to_rgba() for c in assets.palette(stamp.ptype, stamp.pnum)]
            palette_cache[pal_key] = palette_rgba

        screen_x = dest_x + (info.x - scroll_x)
        screen_y = dest_y + (info.y - scroll_y)
        for idx, tile in enumerate(stamp.data):
            row, col = divmod(idx, stamp.width)
            # Pixel special cases (doc/01_hardware.md §4/§6, Confidence:
            # Verified): 0 = transparent (trans0=True), 1 = shadow. Shadow
            # darkens whatever this layer already painted at that pixel --
            # i.e. the playfield color, since the playfield layer runs first
            # (PLAN.md §6 WP-2 build order) -- rather than looking up a color.
            #
            # The real hardware shows the underlying playfield pixel through
            # the half-intensity *shadow palette* bank (color RAM 0x910400),
            # which the game builds from the playfield palette (0x910500) in
            # the copy routine at 0x5FD80 (called from 0x436B8): for each
            # 16-bit IRGB entry, shadow = color - 0x7000 (subtract 7 from the
            # I nibble, bits 15-12), and if that borrows (I <= 6) the RGB is
            # kept and I is forced to 1. Verified by disassembly (capstone,
            # row76.bin). We approximate that palette-space operation as a
            # per-pixel RGB *0.5 here: the compositor only has the flattened
            # underlying RGB (= I*channel), not the source I nibble, so the
            # exact (I-7)*channel result is not recoverable per-pixel; *0.5 is
            # close for the common full-intensity (I=15 -> 8/15) playfield
            # colors. An exact implementation would build a shadow-palette
            # raster in the playfield layer -- see Framebuffer.blit_indexed_tile.
            fb.blit_indexed_tile(
                tile, palette_rgba,
                screen_x + col * 8, screen_y + row * 8,
                trans0=True, shadow_index=1, clip=clip,
            )
