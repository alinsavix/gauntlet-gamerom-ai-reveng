"""Render the authoritative playfield descriptor and color RAM.

Game logic owns the 64x64 column-first descriptor table and the two live
128-word color banks. Rendering decodes descriptors into a host-side indexed
raster, then resolves that raster through the color banks; it never reconstructs
terrain from logical maze objects or overlays a second live playfield effect.
"""

from __future__ import annotations

import dataclasses

from PIL import Image

from ..coords import PF_COLS, PF_ROWS, WORLD_PIXELS
from ..playfield_vram import PF_PALETTE_MASK, PF_TILE_MASK
from ..subsystems.display import _irgb_rgba

__all__ = [
    "PlayfieldCache",
    "ShadowSource",
    "draw_playfield",
    "irgb_to_shadow",
    "playfield_cache_for_state",
    "shadow_source_for",
]


def irgb_to_shadow(irgb: int) -> int:
    """Apply ``palette_fade_copy(..., 0x7000)`` to one IRGB word."""
    if irgb >= 0x7000:
        return irgb - 0x7000
    return (irgb & 0x0FFF) | 0x1000


@dataclasses.dataclass
class PlayfieldCache:
    """Derived normal and shadow rasters keyed by authoritative RAM state."""

    image: object
    shadow_image: object
    vram_generation: int = -1
    color_generation: int = -1
    descriptor_signature: tuple[int, ...] = ()
    indexed_image: object | None = None
    decoded_tiles: dict[int, object] = dataclasses.field(default_factory=dict)
    state: object | None = None


def _vram_palette(state, number: int, *, shadow: bool = False):  # noqa: ANN001
    ram = (
        state.playfield_shadow_color_ram
        if shadow else state.playfield_color_ram
    )
    base = (number & 7) * 16
    return [_irgb_rgba(word) for word in ram[base:base + 16]]


def _build_vram_indices(
    state, decoded_tiles: dict[int, object] | None = None,  # noqa: ANN001
):
    """Decode descriptor RAM into palette-bank/color indices once per change."""
    from gex.render import get_parsed_tile
    from gex.roms import GexError

    decoded_tiles = {} if decoded_tiles is None else decoded_tiles
    pixels = bytearray(WORLD_PIXELS * WORLD_PIXELS)
    for column in range(PF_COLS):
        base = column * PF_ROWS
        for row in range(PF_ROWS):
            word = int(state.playfield_ram[base + row]) & 0xFFFF
            tile_number = word & PF_TILE_MASK
            tile = decoded_tiles.get(tile_number)
            if tile is None:
                try:
                    tile = get_parsed_tile(tile_number)
                except GexError:
                    tile = [[0] * 8 for _ in range(8)]
                decoded_tiles[tile_number] = tile
            palette_base = (word & PF_PALETTE_MASK) >> 8
            x = column * 8
            y = row * 8
            for line, tile_line in enumerate(tile):
                offset = (y + line) * WORLD_PIXELS + x
                pixels[offset:offset + 8] = bytes(
                    palette_base | (int(color) & 0x0F) for color in tile_line
                )
    indexed = Image.frombytes(
        "P", (WORLD_PIXELS, WORLD_PIXELS), bytes(pixels),
    )
    return indexed, decoded_tiles


def _update_vram_indices(
    state, indexed, decoded_tiles: dict[int, object],  # noqa: ANN001
    previous: tuple[int, ...], current: tuple[int, ...],
):
    """Restamp only descriptor words changed since the previous host raster."""
    from PIL import Image
    from gex.render import get_parsed_tile
    from gex.roms import GexError

    updated = indexed.copy()
    for index, (old_word, word) in enumerate(zip(previous, current, strict=True)):
        if old_word == word:
            continue
        tile_number = word & PF_TILE_MASK
        tile = decoded_tiles.get(tile_number)
        if tile is None:
            try:
                tile = get_parsed_tile(tile_number)
            except GexError:
                tile = [[0] * 8 for _ in range(8)]
            decoded_tiles[tile_number] = tile
        palette_base = (word & PF_PALETTE_MASK) >> 8
        pixels = bytes(
            palette_base | (int(color) & 0x0F)
            for tile_line in tile
            for color in tile_line
        )
        column, row = divmod(index, PF_ROWS)
        updated.paste(
            Image.frombytes("P", (8, 8), pixels),
            (column * 8, row * 8),
        )
    return updated


def _colorize_indexed(indexed, state, *, shadow: bool = False):  # noqa: ANN001
    """Resolve one indexed world through live color RAM without tile decoding."""
    palette = []
    for number in range(8):
        for color in _vram_palette(state, number, shadow=shadow):
            palette.extend(color[:3])
    palette.extend([0] * (768 - len(palette)))
    colored = indexed.copy()
    colored.putpalette(palette)
    return colored.convert("RGBA")


def playfield_cache_for_state(
    state, cache: PlayfieldCache | None,  # noqa: ANN001
) -> PlayfieldCache:
    """Return a cache derived exclusively from descriptor and color RAM."""
    same_state = cache is not None and cache.state is state
    vram_unchanged = (
        same_state and cache.vram_generation == state.playfield_generation
    )
    color_unchanged = (
        same_state
        and cache.color_generation == state.playfield_color_generation
    )
    if vram_unchanged and color_unchanged:
        return cache

    if vram_unchanged:
        descriptor_signature = cache.descriptor_signature
        indexed = cache.indexed_image
        decoded_tiles = cache.decoded_tiles
    else:
        descriptor_signature = tuple(
            int(word) & 0xFFFF for word in state.playfield_ram
        )
        if (
            cache is not None
            and cache.indexed_image is not None
            and len(cache.descriptor_signature) == len(descriptor_signature)
        ):
            decoded_tiles = cache.decoded_tiles
            indexed = _update_vram_indices(
                state,
                cache.indexed_image,
                decoded_tiles,
                cache.descriptor_signature,
                descriptor_signature,
            )
        else:
            indexed, decoded_tiles = _build_vram_indices(
                state, cache.decoded_tiles if cache is not None else None,
            )
    normal = _colorize_indexed(indexed, state)
    shadow = _colorize_indexed(indexed, state, shadow=True)
    return PlayfieldCache(
        image=normal,
        shadow_image=shadow,
        vram_generation=state.playfield_generation,
        color_generation=state.playfield_color_generation,
        descriptor_signature=descriptor_signature,
        indexed_image=indexed,
        decoded_tiles=decoded_tiles,
        state=state,
    )


class ShadowSource:
    """Sample the cached shadow raster by framebuffer coordinate."""

    __slots__ = ("image", "_px", "_w", "_h", "_ox", "_oy")

    def __init__(
        self, shadow_image, scroll_x: int, scroll_y: int,
        dest_x: int, dest_y: int,
    ) -> None:
        self.image = shadow_image
        self._px = shadow_image.load()
        self._w, self._h = shadow_image.size
        self._ox = scroll_x - dest_x
        self._oy = scroll_y - dest_y

    def at(self, fx: int, fy: int):
        wx, wy = self.source_xy(fx, fy)
        return self._px[wx, wy]

    def source_xy(self, fx: int, fy: int) -> tuple[int, int]:
        return (fx + self._ox) % self._w, (fy + self._oy) % self._h


def shadow_source_for(
    cache: PlayfieldCache,
    scroll_x: int,
    scroll_y: int,
    viewport: tuple[int, int, int, int],
) -> ShadowSource:
    dest_x, dest_y, _width, _height = viewport
    return ShadowSource(
        cache.shadow_image, scroll_x, scroll_y, dest_x, dest_y,
    )


def draw_playfield(
    fb,
    cache: PlayfieldCache,
    scroll_x: int,
    scroll_y: int,
    viewport: tuple[int, int, int, int],
) -> None:
    """Blit a wrapped, scrolled playfield window from the derived cache."""
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
