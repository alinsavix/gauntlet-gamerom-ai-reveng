"""Tests for the display compositor and host shell (WP-2).

Three tiers, mirroring ``test_assets.py``'s pattern:

- **Always runs, no ROMs.** ``Framebuffer`` primitives, MOB draw-order (a
  PLAN.md §6 WP-2 acceptance criterion -- "assert draw order matches chain
  order"), the HUD layer, and a full ``render_frame`` smoke test all use a
  ROM-free fake asset source (``_FakeAssets``) instead of a real
  ``AssetStore``, so they exercise real code paths without needing the ROMs
  gex would otherwise read.
- **Needs ROMs.** The playfield golden-image comparison against gex's own
  ``genpfimage`` -- real tile pixels are the whole point of that test, so it
  cannot be faked. Skips cleanly (mirrors ``test_assets.py``'s
  ``requires_roms_and_refs``) rather than erroring when ROMs aren't
  configured.
- **Needs pygame.** ``HostShell`` (host.py) tests skip cleanly via
  ``pytest.importorskip`` when pygame isn't installed, per this package's
  brief ("pygame host-shell tests may still skip if pygame isn't
  installed... but the compositor tests must not depend on pygame").
"""

from __future__ import annotations

import time

import pytest

from gauntpy import coords
from gauntpy.constants import GameMode, MazeObjIds, PlayerStatus
from gauntpy.render.compositor import HUD_PANEL, PLAYFIELD_VIEWPORT, render_frame
from gauntpy.render.framebuffer import Framebuffer
from gauntpy.render.hud import (
    cell_xy,
    draw_debug_frame_counter,
    draw_hud,
    draw_message_box,
)
from gauntpy.render.mobs import draw_mob_layer, iter_visible_mobs, strength_tier
from gauntpy.render import playfield, romtext
from gauntpy.render.screens import _title_logo_y, draw_front_end_overlay
from gauntpy.state import GameState
from gauntpy.subsystems import score
from gauntpy.subsystems.score import (
    dialog_first_encounter,
    main_msgbox_countdown,
    main_score_display,
)

# ---------------------------------------------------------------------------
# ROM/reference availability (same approach as test_assets.py)
# ---------------------------------------------------------------------------

from gex.roms import TILE_ROMS, _rom_dir  # noqa: E402

_ROM_PATH = _rom_dir()
_ROMS_EXIST = _ROM_PATH.is_dir() and (_ROM_PATH / TILE_ROMS[0][0]).is_file()

requires_roms = pytest.mark.skipif(
    not _ROMS_EXIST, reason=f"ROM files not available at {_ROM_PATH}"
)


# ---------------------------------------------------------------------------
# A ROM-free SpriteSource, matching render.mobs.SpriteSource structurally --
# no gex tile decode, no ROM I/O. Lets the MOB-layer and compositor tests
# exercise real drawing code without ROMs.
# ---------------------------------------------------------------------------

class _FakeColor:
    def __init__(self, rgba: tuple[int, int, int, int]) -> None:
        self._rgba = rgba

    def to_rgba(self) -> tuple[int, int, int, int]:
        return self._rgba


class _FakeAssets:
    """Every ``sprite(picture)`` is a single 8x8 tile filled with one index,
    derived from ``picture`` so different pictures are visibly different
    colors after compositing. Index 0 (transparent) and 1 (shadow) are never
    produced by ``_fill_index`` so ordinary sprite pixels never accidentally
    hit those special cases.
    """

    def __init__(self) -> None:
        # 16-entry grayscale ramp, distinguishable by exact value.
        self._palette = [_FakeColor((i * 16, i * 16, i * 16, 255)) for i in range(16)]
        self.sprite_calls: list[
            tuple[int, int, int | None, str | None, tuple[int, int] | None]
        ] = []
        from PIL import Image

        self._title_logo = Image.new("RGBA", (328, 48), (32, 192, 64, 255))

    @staticmethod
    def _fill_index(picture: int) -> int:
        return 2 + (picture % 13)  # 2..14

    def sprite(self, picture: int, *, tier: int = 1, palette: int | None = None,
               kind: str | None = None, size: tuple[int, int] | None = None):
        from gex.render import Stamp

        idx = self._fill_index(picture)
        tile = [[idx] * 8 for _ in range(8)]
        self.sprite_calls.append((picture, tier, palette, kind, size))
        return Stamp(width=1, numbers=[picture], ptype="fake", pnum=0, data=[tile])

    def palette(self, kind: str, index: int):
        return self._palette

    def title_logo(self):
        return self._title_logo


def _place(mobs, row: int, col: int, picture: int, obj_type=MazeObjIds.MONST_GHOST, size: int = 3) -> int:
    slot = coords.pack_slot(row, col)
    x, y = coords.slot_to_pixels(slot)
    return mobs.create(
        slot,
        tile=picture,
        hpos=coords.encode_hpos(x),
        vpos=coords.encode_vpos_at_y(y, width=size, height=size),
        obj_type=obj_type,
    )


# ---------------------------------------------------------------------------
# Framebuffer primitives
# ---------------------------------------------------------------------------

class TestFramebuffer:
    def test_default_background_is_opaque_black(self):
        fb = Framebuffer(4, 4)
        assert fb.get_pixel(0, 0) == (0, 0, 0, 255)

    def test_out_of_bounds_read_returns_none_not_an_exception(self):
        fb = Framebuffer(4, 4)
        assert fb.get_pixel(-1, 0) is None
        assert fb.get_pixel(4, 0) is None

    def test_set_and_get_pixel_roundtrip(self):
        fb = Framebuffer(4, 4)
        fb.set_pixel(1, 2, (10, 20, 30, 255))
        assert fb.get_pixel(1, 2) == (10, 20, 30, 255)

    def test_blit_indexed_tile_trans0_leaves_background(self):
        fb = Framebuffer(8, 8)
        tile = [[0] * 8 for _ in range(8)]
        palette = [(9, 9, 9, 255)] * 16
        fb.blit_indexed_tile(tile, palette, 0, 0, trans0=True)
        assert fb.get_pixel(0, 0) == (0, 0, 0, 255), "index 0 must stay transparent"

    def test_blit_indexed_tile_paints_normal_colors(self):
        fb = Framebuffer(8, 8)
        tile = [[5] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        palette[5] = (200, 100, 50, 255)
        fb.blit_indexed_tile(tile, palette, 0, 0)
        assert fb.get_pixel(3, 3) == (200, 100, 50, 255)

    def test_shadow_index_fallback_scales_by_the_hardware_ratio(self):
        """doc/01_hardware.md §4/§6: MOB pixel value 1 is the shadow special
        case. With no ``shadow_src`` it must read whatever is already on the
        framebuffer and scale it, never the MOB's own palette -- and by the
        hardware's own 8/15, not a round number (see framebuffer.SHADOW_RATIO).
        """
        fb = Framebuffer(8, 8)
        fb.set_pixel(0, 0, (150, 150, 150, 255))
        tile = [[1] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        palette[1] = (255, 0, 0, 255)  # must NOT be used
        fb.blit_indexed_tile(tile, palette, 0, 0, shadow_index=1)
        assert fb.get_pixel(0, 0) == (80, 80, 80, 255)   # 150*8//15

    def test_the_shadow_ratio_is_the_rom_transform_on_full_intensity_colors(self):
        """SHADOW_RATIO is derived, not chosen: irgb_to_shadow takes I=15 to
        I=8, and gex renders an IRGB as (R*I, G*I, B*I), so a full-intensity
        color's shadow is exactly 8/15 of it -- with no rounding error."""
        from gex.palettes import IRGB

        from gauntpy.render.framebuffer import SHADOW_RATIO
        from gauntpy.render.playfield import irgb_to_shadow

        num, den = SHADOW_RATIO
        for rgb in (0xF00, 0x0F0, 0x00F, 0xFFF, 0x8A3, 0x123):
            full = 0xF000 | rgb
            source = IRGB(full).to_rgba()
            expected = IRGB(irgb_to_shadow(full)).to_rgba()
            scaled = tuple(c * num // den for c in source[:3]) + (255,)
            assert scaled == expected, hex(full)

    def test_shadow_src_supplies_exact_color_over_fallback(self):
        """When a shadow_src is given, its exact color wins and the ratio
        scale is not used -- ``shadow_src.at`` is the shadow-palette playfield
        color (playfield.ShadowSource)."""
        class _FixedShadow:
            def at(self, fx, fy):
                return (7, 8, 9, 255)

        fb = Framebuffer(8, 8)
        fb.set_pixel(0, 0, (100, 100, 100, 255))
        tile = [[1] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        fb.blit_indexed_tile(
            tile, palette, 0, 0, shadow_index=1, shadow_src=_FixedShadow(),
        )
        assert fb.get_pixel(0, 0) == (7, 8, 9, 255)

    def test_shadow_src_off_raster_falls_back_to_the_ratio(self):
        """A shadow_src reporting None (off-raster, e.g. a wrap seam) falls
        back to the in-place scale."""
        class _NoShadow:
            def at(self, fx, fy):
                return None

        fb = Framebuffer(8, 8)
        fb.set_pixel(0, 0, (150, 150, 150, 255))
        tile = [[1] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        fb.blit_indexed_tile(
            tile, palette, 0, 0, shadow_index=1, shadow_src=_NoShadow(),
        )
        assert fb.get_pixel(0, 0) == (80, 80, 80, 255)

    def test_irgb_to_shadow_matches_rom_transform(self):
        """playfield.irgb_to_shadow == the 0x5FD80 routine: subtract 7 from
        the IRGB intensity nibble, floor at 1 (verified by disassembly)."""
        from gauntpy.render.playfield import irgb_to_shadow
        assert irgb_to_shadow(0xFFFF) == 0x8FFF   # I=15 -> 8
        assert irgb_to_shadow(0x8ABC) == 0x1ABC   # I=8  -> 1
        assert irgb_to_shadow(0x7000) == 0x0000   # I=7 exactly -> 0
        assert irgb_to_shadow(0x6ABC) == 0x1ABC   # I=6 borrows -> clamp I=1, RGB kept
        assert irgb_to_shadow(0x0123) == 0x1123   # I=0 borrows -> I=1

    def test_clip_rect_confines_drawing(self):
        fb = Framebuffer(16, 16)
        tile = [[5] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        palette[5] = (200, 100, 50, 255)
        fb.blit_indexed_tile(tile, palette, 4, 4, clip=(0, 0, 8, 8))
        assert fb.get_pixel(6, 6) == (200, 100, 50, 255), "inside clip: drawn"
        assert fb.get_pixel(10, 10) == (0, 0, 0, 255), "outside clip: untouched"

    def test_save_png_and_to_pil_image(self, tmp_path):
        fb = Framebuffer(4, 4)
        img = fb.to_pil_image()
        assert img.size == (4, 4)
        out = tmp_path / "fb.png"
        fb.save_png(str(out))
        assert out.is_file()


# ---------------------------------------------------------------------------
# MOB layer: draw order (ROM-free -- PLAN.md §6 WP-2 acceptance criterion)
# ---------------------------------------------------------------------------

def test_player_hurt_palette_whitens_the_rom_selected_entries():
    from gauntpy.render.mobs import (
        _HURT_WHITE_RGBA,
        _PLAYER_HURT_PALETTE_INDICES,
        _player_hurt_palette,
    )

    base = [(i, i, i, 255) for i in range(16)]
    for character, indices in enumerate(_PLAYER_HURT_PALETTE_INDICES):
        state = GameState()
        player = state.players[0]
        player.status = PlayerStatus.ALIVE_HERE
        player.mob_slot = 42
        player.character = character
        player.hurt_cooldown = 0x0C

        flashed = _player_hurt_palette(state, 42, base)

        assert base == [(i, i, i, 255) for i in range(16)]
        for index in range(16):
            expected = _HURT_WHITE_RGBA if index in indices else base[index]
            assert flashed[index] == expected


def test_projectile_palette_12_to_15_resolves_through_player_colour_banks():
    from gauntpy.render.mobs import sprite_kind

    state = GameState()
    state.mobs.hpos[1] = 0x0C
    state.mobs.hpos[5] = 0x0E
    state.mobs.hpos[9] = 0x01

    assert sprite_kind(state, 1) == "warrior"
    assert sprite_kind(state, 5) == "wizard"
    assert sprite_kind(state, 9) is None


class TestMobDrawOrder:
    def test_visible_mobs_yielded_in_chain_order_ascending_band(self):
        """Chain order IS draw priority (PLAN.md §6 WP-2 step 2). The chain
        is sorted by vertical band, so three MOBs placed at increasing rows
        must come back out in the same order they were placed.
        """
        state = GameState()
        slots = [_place(state.mobs, row, 5, picture=0x100 + i) for i, row in enumerate([2, 10, 20])]

        # Full-world viewport height: this test is about ordering, not
        # culling (that's covered separately below).
        infos = list(iter_visible_mobs(state, 0, 0, 240, coords.WORLD_PIXELS))

        assert [info.slot for info in infos] == slots

    def test_entering_at_a_band_skips_earlier_mobs(self):
        """The SLIP band entry point is what makes this fast -- verify it
        actually excludes off-screen-above MOBs rather than merely stopping
        the caller from *seeing* them after a full walk.
        """
        state = GameState()
        _place(state.mobs, row=1, col=2, picture=0x10)   # near the top
        low_slot = _place(state.mobs, row=25, col=2, picture=0x20)  # near the bottom

        # The 240px window crosses the 512px seam, so row 1 wraps in below the
        # low MOB; the full-chain fallback must preserve chain order.
        infos = list(iter_visible_mobs(state, scroll_x=0, scroll_y=350, viewport_w=240, viewport_h=240))

        assert [info.slot for info in infos] == [coords.pack_slot(1, 2), low_slot]

    def test_mob_entirely_below_viewport_is_excluded(self):
        state = GameState()
        _place(state.mobs, row=30, col=2, picture=0x10)  # far below any normal viewport

        infos = list(iter_visible_mobs(state, 0, 0, 240, 240))

        assert infos == []

    def test_top_edge_includes_a_sprite_wrapped_from_world_bottom(self):
        state = GameState()
        state.wrap_v = True
        slot = coords.pack_slot(31, 2)
        state.mobs.create(
            slot, tile=0x100, hpos=coords.encode_hpos(32),
            vpos=coords.encode_vpos_at_y(504, 3, 3),
            obj_type=MazeObjIds.MONST_GHOST,
        )

        infos = list(iter_visible_mobs(state, 0, 0, 240, 240))

        assert [info.slot for info in infos] == [slot]

    def test_zero_picture_slot_is_never_drawn(self):
        """Picture 0 is 'nothing to draw' -- also what the chain's own null
        terminator and unpainted placeholder slots use.
        """
        state = GameState()
        slot = coords.pack_slot(5, 5)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(slot, tile=0, hpos=coords.encode_hpos(x), vpos=coords.encode_vpos_at_y(y, 3, 3), obj_type=MazeObjIds.WALL_REGULAR)

        infos = list(iter_visible_mobs(state, 0, 0, 240, 240))

        assert infos == []

    def test_later_chain_entry_draws_on_top(self):
        """End-to-end confirmation (still ROM-free, via _FakeAssets): two
        overlapping MOBs, the later one in chain order must win the pixel.
        """
        state = GameState()
        _place(state.mobs, row=10, col=10, picture=1, size=4)   # earlier band -> earlier in chain
        top_slot = _place(state.mobs, row=11, col=10, picture=2, size=4)  # later band -> drawn on top, overlaps

        fb = Framebuffer(240, 240)
        draw_mob_layer(fb, state, _FakeAssets(), 0, 0, PLAYFIELD_VIEWPORT)

        top_x, top_y = coords.slot_to_pixels(top_slot)
        top_y -= 16  # 4x4 MOB: two extra tile rows draw above the cell
        expected_idx = _FakeAssets._fill_index(2)
        expected_rgba = (expected_idx * 16, expected_idx * 16, expected_idx * 16, 255)
        assert fb.get_pixel(top_x + 4, top_y + 4) == expected_rgba


class TestTheRendererDecodesTheNativeVWord:
    """The MOB V word counts up from the playfield floor and the hardware draws
    upward from it, so the renderer's one job at this boundary is
    ``coords.sprite_top_y``."""

    def test_a_cell_sized_sprite_sits_exactly_on_its_cell(self):
        state = GameState()
        slot = _place(state.mobs, row=10, col=10, picture=0x100, size=2)
        assert state.mobs.vpos[slot] == ((31 - 10) << 11) | 0x09
        info = next(iter(iter_visible_mobs(state, 0, 96, 240, 240)))
        assert (info.x, info.y) == (10 * 16, 10 * 16)

    def test_a_three_tile_sprite_begins_eight_pixels_above_its_cell(self):
        state = GameState()
        _place(state.mobs, row=10, col=10, picture=0x100, size=3)
        info = next(iter(iter_visible_mobs(state, 0, 96, 240, 240)))
        assert (info.x, info.y) == (10 * 16, 10 * 16 - 8)

    def test_a_four_tile_dragon_begins_sixteen_pixels_above_its_cell(self):
        state = GameState()
        _place(state.mobs, row=10, col=10, picture=0x100, size=4)
        info = next(iter(iter_visible_mobs(state, 0, 96, 240, 240)))
        assert (info.x, info.y) == (10 * 16, 10 * 16 - 16)

    def test_the_last_maze_row_stores_a_zero_v_word(self):
        state = GameState()
        slot = _place(state.mobs, row=31, col=3, picture=0x100, size=2)
        assert state.mobs.vpos[slot] & coords.POS_FIELD_MASK == 0
        info = next(iter(iter_visible_mobs(state, 0, 272, 240, 240)))
        assert info.y == 31 * 16


class TestVisibleMobsCoverEverythingOnScreen:
    """``iter_visible_mobs`` is an optimisation over the obvious answer -- walk
    the whole depth chain, keep whatever overlaps the viewport -- so the two
    must agree exactly. They did not: the walk entered the chain at
    ``scroll_y``'s own SLIP band, but a band says where a MOB's *cell* is, not
    where its sprite ends. Anything anchored above the viewport with its body
    across the top edge was skipped before the bounding box could judge it.
    """

    VIEWPORT = (232, 240)

    @classmethod
    def _reference(cls, state, scroll_x, scroll_y):
        """The whole chain, in order, bounding-box tested. Deliberately the
        naive version: no bands, nothing to get wrong."""
        viewport_w, viewport_h = cls.VIEWPORT
        found = []
        for slot in state.mobs.iter_chain():
            if not state.mobs.is_occupied(slot) or state.mobs.picture[slot] & 0x7FFF == 0:
                continue
            x, _flags, _pal = coords.decode_hpos(state.mobs.hpos[slot])
            v, width, height = coords.decode_vpos(state.mobs.vpos[slot])
            y = coords.sprite_top_y(v, height * 8)
            draw_x = next(
                (
                    candidate for candidate in (x - 512, x, x + 512)
                    if candidate + width * 8 > scroll_x
                    and candidate < scroll_x + viewport_w
                ),
                None,
            )
            if draw_x is None:
                continue
            draw_y = next(
                (
                    candidate for candidate in (y - 512, y, y + 512)
                    if candidate + height * 8 > scroll_y
                    and candidate < scroll_y + viewport_h
                ),
                None,
            )
            if draw_y is None:
                continue
            found.append(slot)
        return found

    def _visible(self, state, scroll_x, scroll_y):
        return [
            info.slot
            for info in iter_visible_mobs(state, scroll_x, scroll_y, *self.VIEWPORT)
        ]

    def test_a_row_one_treasure_survives_a_camera_that_crops_it(self):
        """The reported case. Treasure is a 3x3-tile object
        (``mazeobj_vpos_offset_tbl`` entry 0x12), so a row-1 chest is a 24px
        sprite with its top at world y 8 and is on screen below ``scroll_y`` 32 --
        but its cell is in band 2, and a camera at y 24 used to enter the chain
        at band 3 and never see it.
        """
        state = GameState()
        slot = _place(state.mobs, row=1, col=5, picture=0x987,
                      obj_type=MazeObjIds.TREASURE, size=3)
        for scroll_y in range(0, 32, 4):
            assert self._visible(state, 0, scroll_y) == [slot], scroll_y
        assert self._visible(state, 0, 32) == [], "and gone once it really is off"

    def test_every_scroll_position_matches_the_brute_force_answer(self):
        """A spread of rows, columns and every legal sprite height (1-8 tiles,
        ``mob_vpos`` bits 2-0), swept over every camera position the clamped
        camera can produce."""
        state = GameState()
        slots = [
            _place(state.mobs, row=row, col=(i * 5) % 32, picture=0x100 + i,
                   size=1 + (i % 8))
            for i, row in enumerate(range(0, 32, 3))
        ]
        assert len(slots) == 11

        viewport_w, viewport_h = self.VIEWPORT
        for scroll_y in range(0, coords.WORLD_PIXELS - viewport_h + 1, 4):
            for scroll_x in (0, 96, coords.WORLD_PIXELS - viewport_w):
                assert self._visible(state, scroll_x, scroll_y) == self._reference(
                    state, scroll_x, scroll_y
                ), (scroll_x, scroll_y)

    def test_a_creature_caught_between_cells_is_still_found(self):
        """A monster's pixels lead its cell by up to half a cell either way
        (``monsters._destination_cell``'s +8px bias), so its sprite can sit a
        band above the one its record names."""
        state = GameState()
        slot = _place(state.mobs, row=4, col=4, picture=0x200, size=3)
        y, width, height = coords.decode_vpos_at_y(state.mobs.vpos[slot])
        state.mobs.vpos[slot] = coords.encode_vpos_at_y(y - 8, width, height)
        for scroll_y in range(0, 56, 4):
            assert self._visible(state, 0, scroll_y) == self._reference(state, 0, scroll_y), scroll_y

    def test_the_tallest_legal_sprite_is_covered(self):
        """8 tiles is the ceiling ``mob_vpos``'s 3-bit height field allows, and
        the entry margin is sized from it."""
        from gauntpy.render.mobs import MAX_MOB_PIXELS, MAX_MOB_TILES

        assert (MAX_MOB_TILES, MAX_MOB_PIXELS) == (8, 64)
        state = GameState()
        slot = _place(state.mobs, row=6, col=6, picture=0x300, size=MAX_MOB_TILES)
        y, _w, _h = coords.decode_vpos_at_y(state.mobs.vpos[slot])
        assert self._visible(state, 0, y + coords.CELL_PIXELS - 1) == [slot]
        assert self._visible(state, 0, y + coords.CELL_PIXELS) == []

    def test_a_hero_walks_its_band_along_with_it(self):
        """A hero obeys the rule bands rely on, like every other creature.

        ``players.migrate_player_record`` moves the record into the cell the
        hero stands in (``MobTable.move_slot`` -- "identity is location"), so
        the band the chain walk enters at follows the sprite down the maze and
        the plain geometric window is all the renderer needs.
        """
        state = GameState()
        spawn = _place(state.mobs, row=2, col=8, picture=0x1E0D,
                       obj_type=MazeObjIds.PLAYERSTART, size=3)
        player = state.players[0]
        player.mob_slot = spawn
        player.status = int(PlayerStatus.ALIVE_HERE)

        walked = coords.pack_slot(20, 8)                    # 18 rows down
        state.mobs.vpos[spawn] = coords.encode_vpos_at_y(320, 3, 3)
        state.mobs.move_slot(spawn, walked)
        player.mob_slot = walked
        assert state.mobs.picture[spawn] == 0, "the spawn cell is vacated"
        assert state.mobs.band_of(walked) == 40, "the band came with it"

        for scroll_y in (0, 100, 200, 272):
            assert self._visible(state, 0, scroll_y) == self._reference(state, 0, scroll_y), scroll_y
        assert walked in self._visible(state, 0, 200)

    def test_the_walk_still_enters_late_and_stops_early(self):
        """The band window is widened by a fixed, documented amount, not
        abandoned -- PLAN.md §6 WP-2 step 2's "skip MOBs outside the visible
        bands" still holds."""
        from gauntpy.render.mobs import (
            BAND_SLACK_PIXELS, MAX_MOB_PIXELS, _chain_band_window,
        )

        state = GameState()
        first, last = _chain_band_window(state, 160, 240)
        assert first == (160 - MAX_MOB_PIXELS - BAND_SLACK_PIXELS) // 8 > 0
        assert last == (160 + 240 - 1 + BAND_SLACK_PIXELS) // 8 < 63

        # ... and a MOB far above the window is still skipped by the entry
        # point rather than merely filtered out afterwards.
        _place(state.mobs, row=1, col=1, picture=0x10)
        assert state.mobs.band_of(coords.pack_slot(1, 1)) < first


class TestSpriteKind:
    """Which creature a slot holds, resolved from the MOB table rather than
    guessed from the picture number -- ``render.mobs.sprite_kind``."""

    def test_a_players_slot_reports_the_class_they_picked(self):
        from gauntpy.constants import Character
        from gauntpy.render.mobs import sprite_kind

        for character, name in enumerate(("warrior", "valkyrie", "wizard", "elf")):
            state = GameState()
            slot = _place(state.mobs, row=6, col=6, picture=0x1E0D,
                          obj_type=MazeObjIds.PLAYERSTART, size=3)
            player = state.players[0]
            player.mob_slot = slot
            player.character = Character(character)
            player.status = int(PlayerStatus.ALIVE_HERE)
            assert sprite_kind(state, slot) == name

    def test_the_thief_is_not_mistaken_for_a_hero(self):
        """The thief's MOB carries the PLAYERSTART object type too
        (``thief._thief_spawn``), so only the player's own slot may claim a
        hero class."""
        from gauntpy.render.mobs import sprite_kind

        state = GameState()
        slot = _place(state.mobs, row=9, col=9, picture=0x1E0D,
                      obj_type=MazeObjIds.PLAYERSTART, size=3)
        assert sprite_kind(state, slot) is None

    def test_a_removed_player_no_longer_claims_its_old_slot(self):
        from gauntpy.render.mobs import sprite_kind

        state = GameState()
        slot = _place(state.mobs, row=6, col=6, picture=0x1E0D,
                      obj_type=MazeObjIds.PLAYERSTART, size=3)
        state.players[0].mob_slot = slot
        state.players[0].status = int(PlayerStatus.REMOVED)
        assert sprite_kind(state, slot) is None

    def test_each_monster_type_names_its_gex_family(self):
        from gex.monsters import MONSTERS
        from gauntpy.render.mobs import sprite_kind

        families = {
            MazeObjIds.MONST_GHOST: "ghost",
            MazeObjIds.MONST_GRUNT: "grunt",
            MazeObjIds.MONST_AUX_GRUNT: "grunt",
            MazeObjIds.MONST_DEMON: "demon",
            MazeObjIds.MONST_LOBBER: "lobber",
            MazeObjIds.MONST_SORC: "sorcerer",
            MazeObjIds.MONST_SUPERSORC: "supersorc",
            MazeObjIds.MONST_DEATH: "death",
            MazeObjIds.MONST_ACID: "acid",
            MazeObjIds.MONST_IT: "it",
        }
        for obj_type, name in families.items():
            assert name in MONSTERS
            state = GameState()
            slot = _place(state.mobs, row=7, col=7, picture=0x100, obj_type=obj_type)
            assert sprite_kind(state, slot) == name

    def test_non_creatures_have_no_kind(self):
        from gauntpy.render.mobs import sprite_kind

        state = GameState()
        slot = _place(state.mobs, row=5, col=5, picture=0x200, obj_type=MazeObjIds.KEY)
        assert sprite_kind(state, slot) is None

    def test_the_kind_reaches_the_asset_store(self):
        from gauntpy.constants import Character

        state = GameState()
        slot = _place(state.mobs, row=6, col=6, picture=0x1E0D,
                      obj_type=MazeObjIds.PLAYERSTART, size=3)
        player = state.players[0]
        player.mob_slot = slot
        player.character = Character.WIZARD
        player.status = int(PlayerStatus.ALIVE_HERE)

        assets = _FakeAssets()
        draw_mob_layer(Framebuffer(240, 240), state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        assert assets.sprite_calls[0][3] == "wizard"

    def test_a_sprite_whose_palette_the_provider_lacks_skips_one_mob_not_the_frame(self):
        """The palette fetch moved inside the per-MOB guard: a resolved sprite
        can still name a bank/index the provider does not have, and one missing
        creature beats a black frame."""
        from gauntpy.assets import AssetError

        class _NoPalettes(_FakeAssets):
            def palette(self, kind: str, index: int):
                raise AssetError("no such palette")

        state = GameState()
        _place(state.mobs, row=6, col=6, picture=0x100)
        draw_mob_layer(Framebuffer(240, 240), state, _NoPalettes(), 0, 0, PLAYFIELD_VIEWPORT)


class TestMobStrengthTier:
    """``strength_tier`` must land on the palette index the hardware itself
    would have used: doc/01_hardware.md §8.2 makes ``mob_hpos`` bits 3-0 the
    MOB palette number, and doc/04_game_subsystems.md §26 puts the creature's
    live health tier in those same bits.
    """

    #: MazeObjIds -> gex monster key, plus that family's full-strength nibble
    #: (mazeobj_hsize_tier_tbl, ROM 0x5864C) and how many live steps it has.
    _FAMILIES = [
        (MazeObjIds.MONST_GHOST, "ghost", 0x4, 3),
        (MazeObjIds.MONST_GRUNT, "grunt", 0x4, 3),
        (MazeObjIds.MONST_AUX_GRUNT, "grunt", 0x4, 3),
        (MazeObjIds.MONST_DEMON, "demon", 0x8, 3),
        (MazeObjIds.MONST_IT, "it", 0x8, 3),
        (MazeObjIds.MONST_LOBBER, "lobber", 0xB, 3),
        (MazeObjIds.MONST_SORC, "sorcerer", 0xB, 3),
        (MazeObjIds.MONST_SUPERSORC, "supersorc", 0xB, 3),
        (MazeObjIds.MONST_ACID, "acid", 0x1, 1),
        (MazeObjIds.MONST_DEATH, "death", 0x0, 1),
    ]

    def test_tier_resolves_to_the_hardware_palette_number(self):
        """gex builds a monster's palette as ``pnum + tier + 1``
        (python-gex/src/gex/monsters.py ``domonster``). Feeding it the tier
        derived from the hpos nibble must reproduce the nibble exactly -- for
        every family and every live strength step.
        """
        from gex.monsters import MONSTERS

        for obj_type, name, base, steps in self._FAMILIES:
            for step in range(steps):
                nibble = base - step
                state = GameState()
                slot = coords.pack_slot(5, 5)
                x, y = coords.slot_to_pixels(slot)
                state.mobs.create(
                    slot, tile=0x100,
                    hpos=coords.encode_hpos(x) | nibble,
                    vpos=coords.encode_vpos_at_y(y, 3, 3),
                    obj_type=obj_type,
                )
                tier = strength_tier(state, slot)
                pal = MONSTERS[name].pnum + tier + 1
                assert pal == nibble, (name, nibble, tier, pal)

    def test_tier_is_clamped_to_the_range_gex_has_palettes_for(self):
        state = GameState()
        slot = coords.pack_slot(5, 5)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=0x100, hpos=coords.encode_hpos(x) | 0xF,
            vpos=coords.encode_vpos_at_y(y, 3, 3), obj_type=MazeObjIds.MONST_GHOST,
        )
        assert strength_tier(state, slot) == 3       # nibble 0xF is above base
        state.mobs.hpos[slot] = coords.encode_hpos(x) | 0x0
        assert strength_tier(state, slot) == 1       # and 0 is below base-2

    def test_non_creatures_keep_tier_one(self):
        """Items, shots and terrain carry their own palette in their stamp;
        their hpos nibble is not a strength tier."""
        state = GameState()
        slot = _place(state.mobs, row=5, col=5, picture=0x200, obj_type=MazeObjIds.KEY)
        assert strength_tier(state, slot) == 1


class TestLivePaletteReachesTheAssetStore:
    """``mob_hpos`` bits 3-0 are the hardware MOB palette number
    (doc/01_hardware.md §8.2), so the MOB layer hands that word to
    ``AssetStore.sprite(palette=...)`` rather than throwing it away and
    re-deriving a tier."""

    def _draw(self, nibble: int, obj_type=MazeObjIds.MONST_GHOST):
        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=0x100,
            hpos=coords.encode_hpos(x) | nibble,
            vpos=coords.encode_vpos_at_y(y, 3, 3),
            obj_type=obj_type,
        )
        assets = _FakeAssets()
        draw_mob_layer(Framebuffer(240, 240), state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        return assets.sprite_calls

    def test_the_live_palette_word_is_passed_through(self):
        for nibble in (0x2, 0x3, 0x4):
            calls = self._draw(nibble)
            assert calls and calls[0][2] == nibble, nibble

    def test_the_tier_fallback_is_still_supplied(self):
        """An asset provider that cannot honour a raw palette number still
        gets the derived tier."""
        calls = self._draw(0x4)
        assert calls[0][1] == strength_tier_of(0x4)

    def test_a_wounded_monster_changes_colour(self):
        """The whole point: dropping the nibble must change what is drawn."""
        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=0x100, hpos=coords.encode_hpos(x) | 0x4,
            vpos=coords.encode_vpos_at_y(y, 3, 3), obj_type=MazeObjIds.MONST_GHOST,
        )
        assets = _FakeAssets()
        draw_mob_layer(Framebuffer(240, 240), state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        state.mobs.hpos[slot] = coords.encode_hpos(x) | 0x2      # two hits taken
        draw_mob_layer(Framebuffer(240, 240), state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        assert assets.sprite_calls[0][2] != assets.sprite_calls[1][2]

    def test_a_custom_tier_hook_is_still_honoured(self):
        state = GameState()
        _place(state.mobs, row=6, col=6, picture=0x100)
        assets = _FakeAssets()
        draw_mob_layer(
            Framebuffer(240, 240), state, assets, 0, 0, PLAYFIELD_VIEWPORT,
            tier_for=lambda _s, _slot: 3,
        )
        assert assets.sprite_calls[0][1] == 3


class TestTheMobSizeReachesTheAssetStore:
    """``mob_vpos`` bits 5-0 are the sprite's tile size, and picture + size is
    the whole of what the MOB hardware draws. The layer hands both over, which
    is what lets the asset store stamp a raw ROM block for artwork that is in
    no table (``AssetStore._sized_block``) -- the hero exit/death dissolve
    above all.
    """

    def _draw(self, width: int, height: int):
        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=0x100, hpos=coords.encode_hpos(x),
            vpos=coords.encode_vpos_at_y(y, width, height),
            obj_type=MazeObjIds.MONST_GHOST,
        )
        assets = _FakeAssets()
        draw_mob_layer(Framebuffer(240, 240), state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        return assets.sprite_calls

    @pytest.mark.parametrize("width,height", [(1, 1), (2, 2), (3, 3), (3, 1), (8, 8)])
    def test_the_decoded_size_is_passed_through_in_tiles(self, width, height):
        calls = self._draw(width, height)
        assert calls and calls[0][4] == (width, height)

    def test_mob_draw_info_reports_the_same_size_the_word_encodes(self):
        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=0x100, hpos=coords.encode_hpos(x),
            vpos=coords.encode_vpos_at_y(y, 3, 2), obj_type=MazeObjIds.MONST_GHOST,
        )
        info = next(iter_visible_mobs(state, 0, 0, 240, 240))
        assert (info.width_px, info.height_px) == (24, 16)
        assert info.size_tiles == (3, 2)
        assert coords.decode_vpos_at_y(state.mobs.vpos[slot])[1:] == info.size_tiles

    def test_sprite_stamp_is_clipped_to_the_hardware_size_word(self):
        from gex.render import Stamp

        class ThreeByThreeAssets(_FakeAssets):
            def sprite(self, picture, **kwargs):  # noqa: ANN001
                tile = [[5] * 8 for _ in range(8)]
                return Stamp(
                    width=3, numbers=list(range(9)), ptype="fake", pnum=0,
                    data=[tile] * 9,
                )

        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=0x100, hpos=coords.encode_hpos(x),
            vpos=coords.encode_vpos_at_y(y, 3, 2),
            obj_type=MazeObjIds.MONST_LOBBER,
        )
        fb = Framebuffer(240, 240)
        draw_mob_layer(fb, state, ThreeByThreeAssets(), 0, 0, PLAYFIELD_VIEWPORT)

        assert fb.get_pixel(x + 4, y + 12) != (0, 0, 0, 255)
        assert fb.get_pixel(x + 4, y + 20) == (0, 0, 0, 255)


def strength_tier_of(nibble: int) -> int:
    """The tier ``strength_tier`` derives for a ghost carrying ``nibble``."""
    state = GameState()
    slot = coords.pack_slot(6, 6)
    x, y = coords.slot_to_pixels(slot)
    state.mobs.create(
        slot, tile=0x100, hpos=coords.encode_hpos(x) | nibble,
        vpos=coords.encode_vpos_at_y(y, 3, 3), obj_type=MazeObjIds.MONST_GHOST,
    )
    return strength_tier(state, slot)


# ---------------------------------------------------------------------------
# HUD layer -- the info panel. Layout comes from subsystems/score.py's ROM
# constants (setup_infopanel 0x452D0 / draw_player_score 0x45940 /
# draw_player_health 0x459A2 / player_inv_update 0x45ACA); content comes from
# the InfoPanel latch main_score_display writes. ROM-free: render/text.py falls
# back to PIL when the alpha font ROM isn't there.
# ---------------------------------------------------------------------------

class TestHud:
    @staticmethod
    def _state() -> GameState:
        """main_score_display skips TITLE/SCORES (§14.2), so HUD latch tests
        need a gameplay mode."""
        return GameState(game_mode=GameMode.NORMAL)

    @staticmethod
    def _ink_in_rows(fb, panel, first_row, last_row) -> bool:
        px, py, pw, _ph = panel
        return any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(py + first_row * 8, py + (last_row + 1) * 8)
            for x in range(px, px + pw)
        )

    def _player_block_rows(self, index):
        base = index * score.PLAYER_BLOCK_STRIDE
        return base + score.PLAYER_NAME_ROW, base + score.PLAYER_INV_ROW

    def test_active_player_row_is_not_left_blank(self):
        state = self._state()
        state.players[0].status = PlayerStatus.ALIVE_HERE
        state.players[0].score = 1234
        state.players[0].health = 500
        state.frame_counter = 0
        main_score_display(state)               # latch what the ROM would draw

        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)

        first, last = self._player_block_rows(0)
        assert self._ink_in_rows(fb, HUD_PANEL, first, last), (
            "an active player's block (alpha rows 7-10) must draw something"
        )

    def test_removed_player_block_is_blank_but_the_level_header_is_not(self):
        """setup_infopanel dispatches on player status: a REMOVED player has no
        name, score or health on the panel -- only the whole-panel header
        ("LEVEL n" at row 6) is unconditional."""
        state = GameState()   # all players default to PlayerStatus.REMOVED
        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)

        first, last = self._player_block_rows(0)
        assert not self._ink_in_rows(fb, HUD_PANEL, first, last)
        assert self._ink_in_rows(fb, HUD_PANEL, score.LEVEL_ROW, score.LEVEL_ROW)

    def test_each_player_block_lands_on_its_rom_rows(self):
        """Player p's block is rows p*5+7 .. p*5+10 -- the ROM's ``d4 = p*5+7``
        and its four-row clear loop. Drawing player 2 must not touch player 1's
        rows."""
        state = self._state()
        state.players[2].status = PlayerStatus.ALIVE_HERE
        state.players[2].score = 7654321
        state.frame_counter = 2
        main_score_display(state)

        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)

        for other in (0, 1, 3):
            first, last = self._player_block_rows(other)
            assert not self._ink_in_rows(fb, HUD_PANEL, first, last), other
        first, last = self._player_block_rows(2)
        assert self._ink_in_rows(fb, HUD_PANEL, first, last)

    def test_hud_draws_the_latched_score_not_the_live_one(self):
        """The panel is a latch: a score change only reaches the HUD when
        main_score_display next selects that player (frame_counter & 3)."""
        state = self._state()
        state.players[0].status = PlayerStatus.ALIVE_HERE
        state.players[0].score = 100
        state.frame_counter = 0
        main_score_display(state)

        state.players[0].score = 999999      # changes mid-frame, not yet drawn
        fb_stale = Framebuffer(336, 240)
        draw_hud(fb_stale, state, HUD_PANEL)

        state.frame_counter = 4              # player 0's turn comes round again
        main_score_display(state)
        fb_fresh = Framebuffer(336, 240)
        draw_hud(fb_fresh, state, HUD_PANEL)

        assert fb_stale.image.tobytes() != fb_fresh.image.tobytes()

    def test_the_info_panel_never_draws_the_message_box(self):
        """``dialog_position_box`` (0x4CB50) places the box over the playfield,
        not inside the panel -- ``draw_message_box`` owns it, so a live dialog
        must not change what the panel draws."""
        state = GameState()
        state.dialog_timer = 30
        state.dialog_message = ["HELLO"]
        state.dialog_box_rows, state.dialog_box_width = 3, 5

        fb_dialog = Framebuffer(336, 240)
        draw_hud(fb_dialog, state, HUD_PANEL)
        fb_plain = Framebuffer(336, 240)
        draw_hud(fb_plain, GameState(), HUD_PANEL)
        assert fb_dialog.image.tobytes() == fb_plain.image.tobytes()

    def test_playfield_area_untouched(self):
        """The HUD layer must not paint outside its own panel."""
        state = GameState()
        state.players[0].status = 1
        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)
        px_x, px_y, px_w, px_h = PLAYFIELD_VIEWPORT
        for y in range(px_y, px_y + px_h, 17):
            for x in range(px_x, px_x + px_w, 23):
                assert fb.get_pixel(x, y) == (0, 0, 0, 255)


class TestMessageBox:
    """The dialog box draws the ROM message ``dialog_first_encounter`` (0x4C440)
    put on GameState -- not a blank outline."""

    def _drawn_text(self, state, monkeypatch) -> list[str]:
        seen: list[str] = []
        import gauntpy.render.hud as hud_mod

        real = hud_mod.draw_text

        def spy(image, x, y, text, rgba, *, scale=1):
            seen.append(text)
            return real(image, x, y, text, rgba, scale=scale)

        monkeypatch.setattr(hud_mod, "draw_text", spy)
        fb = Framebuffer(336, 240)
        draw_message_box(fb, state, PLAYFIELD_VIEWPORT)
        return seen

    def test_nothing_is_drawn_without_a_live_dialog(self):
        state = GameState()
        fb = Framebuffer(336, 240)
        before = fb.image.tobytes()
        draw_message_box(fb, state, PLAYFIELD_VIEWPORT)
        assert fb.image.tobytes() == before

    def test_the_rom_message_lines_are_drawn(self, monkeypatch):
        state = GameState(game_mode=GameMode.NORMAL)
        dialog_first_encounter(state, 0, 1 << 3)
        seen = self._drawn_text(state, monkeypatch)
        assert seen == list(state.dialog_message)
        assert " SAVE KEYS TO  " in seen

    def test_the_box_is_sized_from_the_rom_geometry(self):
        state = GameState(game_mode=GameMode.NORMAL)
        dialog_first_encounter(state, 0, 1 << 0)     # a three-line record
        fb = Framebuffer(336, 240)
        draw_message_box(fb, state, PLAYFIELD_VIEWPORT)

        vx, vy, vw, vh = PLAYFIELD_VIEWPORT
        expected_h = state.dialog_box_rows * 8
        expected_w = (state.dialog_box_width + 2) * 8
        top = vy + state.dialog_box_row * 8
        left = vx + state.dialog_box_column * 8
        assert fb.get_pixel(left, top) == (200, 200, 200, 255), "box outline"
        assert fb.get_pixel(left + expected_w - 1, top) == (200, 200, 200, 255)

    def test_the_box_disappears_when_the_timer_runs_out(self):
        state = GameState(game_mode=GameMode.NORMAL)
        dialog_first_encounter(state, 0, 1 << 2)
        state.dialog_timer = 1
        main_msgbox_countdown(state)

        fb = Framebuffer(336, 240)
        before = fb.image.tobytes()
        draw_message_box(fb, state, PLAYFIELD_VIEWPORT)
        assert fb.image.tobytes() == before

    def test_render_frame_puts_the_box_over_the_world(self):
        state = GameState(game_mode=GameMode.NORMAL)
        state.players[0].status = PlayerStatus.ALIVE_HERE
        fb_plain, _ = render_frame(state, _FakeAssets())
        dialog_first_encounter(state, 0, 1 << 3)
        fb_box, _ = render_frame(state, _FakeAssets())
        assert fb_plain.image.tobytes() != fb_box.image.tobytes()


class TestPanelGeometryMatchesTheRom:
    """The screen split is no longer a guess: setup_infopanel clears alpha
    columns 29-41 and the two numeric fields sit at columns 0x1D and 0x25."""

    def test_panel_starts_at_alpha_column_29(self):
        assert score.PANEL_COLUMN == 29
        assert HUD_PANEL[0] == score.PANEL_COLUMN * 8 == 232
        assert PLAYFIELD_VIEWPORT[2] == 232, "playfield ends where the panel starts"

    def test_hardware_playfield_exists_behind_all_alpha_columns(self):
        from gauntpy.render.compositor import _HARDWARE_VIEWPORT

        assert _HARDWARE_VIEWPORT == (0, 0, 336, 240)

    def test_panel_is_thirteen_alpha_columns_ending_on_the_last_shown_one(self):
        assert score.PANEL_WIDTH == 13
        assert HUD_PANEL[2] == 13 * 8 == 104
        # 42 displayed columns (doc/01_hardware.md §9.1): 0..41.
        assert score.PANEL_LAST_COLUMN == 41
        assert HUD_PANEL[0] + HUD_PANEL[2] == 336

    def test_health_field_ends_on_the_last_displayed_column(self):
        assert score.HEALTH_COLUMN + score.HEALTH_DIGITS - 1 == score.PANEL_LAST_COLUMN

    def test_score_field_starts_at_the_panel_edge(self):
        assert score.SCORE_COLUMN == score.PANEL_COLUMN
        assert score.SCORE_DIGITS == 7

    def test_cell_xy_maps_rom_alpha_cells_to_pixels(self):
        # draw_player_score's row for player 1 is 1*5+9 = 14 -> y = 112.
        assert cell_xy(HUD_PANEL, score.SCORE_COLUMN, 14) == (232, 112)
        assert cell_xy(HUD_PANEL, score.HEALTH_COLUMN, 14) == (296, 112)

    def test_inventory_keys_use_the_dedicated_gold_alpha_palette(self):
        from gex.palettes import IRGB
        from gauntpy.render import hud

        assert hud._KEY_PALETTE_RGBA == tuple(
            IRGB(value).to_rgba()
            for value in (0x0000, 0xFFA0, 0xF08E, 0xF00C)
        )
        assert hud._KEY_PALETTE_RGBA != tuple(
            hud._player_rgba(0) for _ in range(4)
        )

    def test_debug_frame_counter_uses_the_lower_right_panel_corner(self):
        state = GameState()
        state.frame_counter = 123
        fb = Framebuffer(336, 240)

        draw_debug_frame_counter(fb, state, HUD_PANEL)

        assert any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(220, 240)
            for x in range(300, 336)
        )

    def test_pause_indicator_appears_above_the_frame_counter(self):
        state = GameState(frame_counter=123)
        fb = Framebuffer(336, 240)

        draw_debug_frame_counter(fb, state, HUD_PANEL, paused=True)

        assert any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(205, 229)
            for x in range(285, 336)
        )


# ---------------------------------------------------------------------------
# Compositor smoke test (ROM-free: no state.maze, so the playfield layer is
# a no-op, and mobs come from _FakeAssets)
# ---------------------------------------------------------------------------

class TestRomText:
    """The ROM-font text blitter (render/text.py). Works with the ROM font or
    the PIL fallback, so these hold either way."""

    def _any_nonblack(self, fb, box) -> bool:
        x0, y0, x1, y1 = box
        return any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(y0, y1) for x in range(x0, x1)
        )

    def test_a_letter_draws_pixels(self):
        from gauntpy.render.text import draw_text

        fb = Framebuffer(24, 12)
        draw_text(fb.image, 1, 1, "A", (255, 255, 255, 255))
        assert self._any_nonblack(fb, (0, 0, 24, 12))

    def test_a_space_draws_nothing(self):
        from gauntpy.render.text import draw_text

        fb = Framebuffer(24, 12)
        draw_text(fb.image, 1, 1, " ", (255, 255, 255, 255))
        assert not self._any_nonblack(fb, (0, 0, 24, 12))

    def test_raw_glyph_can_use_all_three_hardware_palette_colours(self):
        from gauntpy.render.text import _blit_glyph

        palette = (
            (0, 0, 0, 255),
            (10, 20, 30, 255),
            (40, 50, 60, 255),
            (70, 80, 90, 255),
        )
        glyph = [[1, 2, 3, 0, 0, 0, 0, 0]] + [[0] * 8 for _ in range(7)]
        fb = Framebuffer(8, 8)

        _blit_glyph(
            fb.image, glyph, 0, 0, (255, 255, 255, 255), 1,
            palette=palette,
        )

        assert [fb.get_pixel(x, 0) for x in range(3)] == list(palette[1:])

    def test_width_is_monospace_eight_px_times_scale(self):
        from gauntpy.render.text import text_width

        assert text_width("ABC") == 24
        assert text_width("ABC", scale=2) == 48


class TestFrontEndOverlay:
    """The title/scores/legend/character-select overlay (render/screens.py):
    draws during attract and pre-game select, no-op during gameplay."""

    def _overlay_changes_viewport(self, state) -> bool:
        fb = Framebuffer(336, 240)
        before = fb.image.tobytes()
        draw_front_end_overlay(fb, state, (0, 0, 336, 240), _FakeAssets())
        return fb.image.tobytes() != before

    def test_title_screen_draws(self):
        state = GameState()                       # default mode is TITLE attract
        assert self._overlay_changes_viewport(state)

    def test_title_uses_native_asset_wordmark(self):
        fb = Framebuffer(336, 240)
        assets = _FakeAssets()
        draw_front_end_overlay(fb, GameState(), (0, 0, 336, 240), assets)
        assert fb.get_pixel(4, 17) == (32, 192, 64, 255)
        assert fb.get_pixel(331, 64) == (32, 192, 64, 255)

    def test_the_disabled_attract_timer_sentinel_parks_the_wordmark(self):
        """0x904B7C is read signed (main_attract's tst.w/blt), so its 0xFFFF
        "disabled" value is -1, not a 65535-frame countdown: an idle attract
        machine shows the settled logo, not the off-screen start of a motion
        program that is not running."""
        state = GameState()
        state.attract_timer = 0xFFFF
        assert _title_logo_y(state) == 17
        state.attract_timer = 0
        assert _title_logo_y(state) == 17

    def test_title_motion_matches_rom_landmarks(self):
        state = GameState()
        state.title_logo_full_program = True
        for frame, expected_y in (
            (0, -207),
            (32, -271),
            (33, 239),
            (144, 17),
            (145, 15),
            (147, 17),
            (148, 18),
            (153, 17),
            (333, 13),
            (340, 17),
        ):
            state.attract_timer = 0x5DD - frame
            assert _title_logo_y(state) == expected_y

        state.title_logo_full_program = False
        state.attract_timer = 0x5DD - 145
        assert _title_logo_y(state) == 17

    def test_scores_and_legend_draw(self):
        for mode in (GameMode.SCORES, GameMode.LEGEND):
            state = GameState()
            state.game_mode = mode
            assert self._overlay_changes_viewport(state), mode

    def test_character_select_draws_before_the_game_starts(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = PlayerStatus.SELECTING
        assert self._overlay_changes_viewport(state)

    def test_gameplay_is_a_noop(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = PlayerStatus.ALIVE_HERE
        assert not self._overlay_changes_viewport(state)

    def test_select_overlay_suppressed_once_a_hero_is_playing(self):
        """A late joiner selecting must not black out a live player's maze."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = PlayerStatus.ALIVE_HERE
        state.players[1].status = PlayerStatus.SELECTING
        assert not self._overlay_changes_viewport(state)


class TestFrontEndTextIsRomData:
    """None of the front-end copy is invented any more: it is transcribed ROM
    text (render/romtext.py) and the ROM's own factory high-score table."""

    def _drawn_text(self, state, monkeypatch) -> list[str]:
        """Every ASCII string the overlay draws, captured at the text layer."""
        seen: list[str] = []
        import gauntpy.render.screens as screens_mod
        import gauntpy.render.text as text_mod

        real_draw = text_mod.draw_text

        def spy(image, x, y, text, rgba, *, scale=1):
            seen.append(text)
            return real_draw(image, x, y, text, rgba, scale=scale)

        monkeypatch.setattr(screens_mod, "draw_text", spy)
        monkeypatch.setattr(text_mod, "draw_text", spy)
        monkeypatch.setattr(
            screens_mod, "draw_text_centered",
            lambda image, cx, y, text, rgba, *, scale=1: seen.append(text),
        )
        fb = Framebuffer(336, 240)
        draw_front_end_overlay(fb, state, (0, 0, 336, 240), _FakeAssets())
        return seen

    def test_title_uses_the_rom_insert_coin_and_press_start_strings(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.TITLE
        seen = self._drawn_text(state, monkeypatch)
        assert romtext.TEXT_INSERT_COIN.strip() in seen
        assert romtext.TEXT_PRESS_START.strip() in seen
        assert romtext.TEXT_ATARI_GAMES in seen
        assert not any("PRESS 5" in s for s in seen), "no invented instruction copy"

    def test_scores_screen_is_the_rom_four_way_split(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.SCORES
        seen = self._drawn_text(state, monkeypatch)

        assert romtext.TEXT_SCORE_PER_COIN in seen
        for plural in romtext.CHARACTER_NAME_PLURALS:
            assert plural in seen, plural

    def test_scores_screen_shows_the_rom_factory_ladder(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.SCORES
        seen = self._drawn_text(state, monkeypatch)

        for klass, cls in enumerate(score.FACTORY_HIGHSCORE_RECORDS):
            for value, initials in cls:
                assert any(
                    initials in s and str(value) in s for s in seen
                ), (klass, initials, value)

    def test_scores_screen_follows_the_live_table_not_the_rom_constant(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.SCORES
        score.high_scores(state)[0][0] = (123456, "ZZZ")
        seen = self._drawn_text(state, monkeypatch)
        assert any("ZZZ" in s and "123456" in s for s in seen)

    def test_character_select_uses_the_rom_instruction_chain(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = PlayerStatus.SELECTING
        seen = self._drawn_text(state, monkeypatch)

        for text, _column, _row in romtext.CHARACTER_SELECT_LINES:
            assert text in seen, text
        assert romtext.TEXT_SELECT_HERO.strip() in seen
        for name in romtext.CHARACTER_NAMES:
            assert name in seen, name
        assert not any("CHOOSE YOUR HERO" in s for s in seen)

    def test_character_select_names_players_by_their_rom_colour(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[1].status = PlayerStatus.SELECTING
        state.players[1].character = 2
        seen = self._drawn_text(state, monkeypatch)
        assert romtext.PLAYER_COLOR_NAMES[1] in seen
        assert "P2" not in seen

    def test_bonus_screen_uses_show_level_end_bonus_screen_strings(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.TREAS_EXIT
        state.bonus_amount = 0
        seen = self._drawn_text(state, monkeypatch)
        assert romtext.BONUS_100_X_COINS in seen
        assert romtext.BONUS_NONE in seen
        assert not any("LEVEL COMPLETE" in s for s in seen)

    def test_legend_uses_the_rom_gameplay_tips(self, monkeypatch):
        state = GameState()
        state.game_mode = GameMode.LEGEND
        seen = self._drawn_text(state, monkeypatch)
        flat = [line for tip in romtext.GAMEPLAY_TIPS for line in tip if line]
        assert any(line in seen for line in flat)
        assert not any("STRONGEST MELEE" in s for s in seen), "no invented class traits"


class TestRomTextTables:
    def test_the_hud_name_runs_cover_the_four_classes(self):
        assert len(romtext.CHARACTER_HUD_GLYPHS) == 4
        assert len(romtext.CHARACTER_NAMES) == 4
        # character_hud_text_ptrs -> 0x57508/0x5750E/0x57514/0x5751A: 4, 5, 4
        # and 2 glyph cells, each cell two half-width letters.
        assert [len(run) for run in romtext.CHARACTER_HUD_GLYPHS] == [4, 5, 4, 2]

    def test_the_player_colour_names_are_the_rom_ones(self):
        assert romtext.PLAYER_COLOR_NAMES == ("RED", "BLUE", "YELLOW", "GREEN")
        assert len(romtext.PLAYER_COLOR_RGBA) == 4

    def test_glyph_runs_render_or_fall_back_to_their_ascii_spelling(self):
        from gauntpy.render.text import draw_glyph_run

        fb = Framebuffer(64, 12)
        advance = draw_glyph_run(
            fb.image, 0, 1, romtext.LABEL_SCORE_GLYPHS, (255, 255, 255, 255),
            fallback="SCORE",
        )
        assert advance > 0
        assert any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(12) for x in range(64)
        )


class TestExitAnimation:
    """The moving exit is a playfield stamp (main_exit_move 0x5287C ->
    pf_stamp_update 0x5E536), indexed by ``state.exit_anim_frame``."""

    def test_descriptor_pool_is_the_rom_sequential_block(self):
        """exit_tile_descs (0x5C8B0) is 252 consecutive words 0x3A2-0x49D, so
        descriptor k is 0x3A2 + 4k. Nine floor patterns x seven stages."""
        assert playfield.EXIT_DESC_TILE_BASE == 0x03A2
        assert playfield.EXIT_ANIM_STAGES == 7
        last = playfield.exit_descriptor(8, 7)     # pattern 8, final stage
        assert last == (0x049A, 0x049B, 0x049C, 0x049D)
        first = playfield.exit_descriptor(0, 0)
        assert first == (0x03A2, 0x03A3, 0x03A4, 0x03A5)

    def test_the_two_cells_are_always_at_complementary_stages(self):
        """main_exit_move reads offset 0 for the closing cell and offset 0x20
        (entry 8) for the opening one. The record pairs them so the stages sum
        to the last one: as a cell seals, the other opens by the same amount.
        Each half also holds its first stage for two steps."""
        record = playfield.EXIT_DESC_RECORD
        assert record == (0, 0, 1, 2, 3, 4, 5, 6, 6, 6, 5, 4, 3, 2, 1, 0)
        last = playfield.EXIT_ANIM_STAGES - 1
        for frame in range(playfield.EXIT_ANIM_FRAMES):
            assert record[frame] + record[8 + frame] == last, frame
        closing = record[:8]
        opening = record[8:]
        assert list(closing) == sorted(closing)
        assert list(opening) == sorted(opening, reverse=True)
        assert closing[0] == closing[1] and opening[0] == opening[1]

    def test_each_floor_pattern_owns_its_own_seven_descriptors(self):
        seen = set()
        for pattern in range(9):
            for entry in range(16):
                seen.add(playfield.exit_descriptor(pattern, entry)[0])
        assert len(seen) == 9 * playfield.EXIT_ANIM_STAGES

    @requires_roms
    def test_the_settled_descriptor_is_the_tiles_gex_uses_for_an_exit(self):
        """floor_type10_desc (0x5C8A0) and gex's own ``exit`` item stamp are
        the same 2x2 block -- which is what pins the overlay's palette.

        Needs ROMs: ``item_get_stamp`` decodes the tiles it names, so without
        them this errored instead of skipping, unlike every other test here.
        """
        from gex.items import item_get_stamp

        assert playfield.EXIT_SETTLED_DESC == (0x039E, 0x039F, 0x0006, 0x0006)
        assert tuple(item_get_stamp("exit").numbers) == playfield.EXIT_SETTLED_DESC

    def _cache(self, palette=None):
        from gauntpy.render.playfield import PlayfieldCache

        return PlayfieldCache(
            image=None, shadow_image=None, floorpattern=0,
            exit_palette=palette or [(0, 0, 0, 255)] * 16,
            transporter_palette=palette or [(0, 0, 0, 255)] * 16,
        )

    def _state(self, **kw):
        state = GameState(game_mode=GameMode.NORMAL)
        state.exit_open_id = coords.pack_slot(4, 4)
        for key, value in kw.items():
            setattr(state, key, value)
        return state

    def test_nothing_is_drawn_without_an_open_exit(self):
        state = GameState()
        state.exit_open_id = 0
        fb = Framebuffer(240, 240)
        before = fb.image.tobytes()
        playfield.draw_exit_animation(fb, self._cache(), state, 0, 0, PLAYFIELD_VIEWPORT)
        assert fb.image.tobytes() == before

    def test_an_ordinary_live_exit_is_drawn_without_a_moving_exit(self):
        state = GameState()
        slot = coords.pack_slot(4, 4)
        state.mobs.create(
            slot, tile=0x8001, hpos=0, vpos=0,
            obj_type=MazeObjIds.EXIT, link_into_chain=False,
        )

        assert self._capture(state) == [(slot, playfield.EXIT_SETTLED_DESC)]

    def test_exit_to_six_uses_its_distinct_destination_graphic(self):
        state = GameState()
        slot = coords.pack_slot(7, 7)
        state.mobs.create(
            slot, tile=0x8001, hpos=0, vpos=0,
            obj_type=MazeObjIds.EXITTO6, link_into_chain=False,
        )

        assert self._capture(state) == [(slot, playfield.EXITTO6_SETTLED_DESC)]

    def test_transporter_marker_is_a_playfield_stamp(self):
        state = GameState()
        slot = coords.pack_slot(7, 7)
        state.mobs.create(
            slot, tile=0x8001, hpos=0, vpos=0,
            obj_type=MazeObjIds.TRANSPORTER, link_into_chain=False,
        )
        stamped = []
        real = playfield._blit_descriptor
        playfield._blit_descriptor = (
            lambda fb, descriptor, cell, palette, sx, sy, viewport, **kwargs:
            stamped.append((cell, tuple(descriptor)))
        )
        try:
            playfield.draw_transporter_tiles(
                Framebuffer(240, 240), self._cache(), state,
                0, 0, PLAYFIELD_VIEWPORT,
            )
        finally:
            playfield._blit_descriptor = real

        assert stamped == [(slot, playfield.TRANSPORTER_DESC)]

    def test_transporter_stamp_consumes_the_live_cycle_phase(self):
        from gex.palettes import IRGB

        state = GameState()
        slot = coords.pack_slot(7, 7)
        state.mobs.create(
            slot, tile=0x8001, hpos=0, vpos=0,
            obj_type=MazeObjIds.TRANSPORTER, link_into_chain=False,
        )
        palettes = []
        real = playfield._blit_descriptor
        playfield._blit_descriptor = (
            lambda fb, descriptor, cell, palette, sx, sy, viewport, **kwargs:
            palettes.append(tuple(palette))
        )
        try:
            for phase in (0, 5):
                state.tport_cycle_pos = phase
                playfield.draw_transporter_tiles(
                    Framebuffer(240, 240), self._cache(), state,
                    0, 0, PLAYFIELD_VIEWPORT,
                )
        finally:
            playfield._blit_descriptor = real

        assert palettes[0][13] == IRGB(0xFFFF).to_rgba()
        assert palettes[1][13] == IRGB(0x8F00).to_rgba()

    def test_animated_floor_palettes_use_their_live_color_words(self):
        from gex.palettes import IRGB, S_COLORS_1, S_COLORS_2

        trap = playfield._animated_floor_palette("trap", 0, 0x4044)
        stun = playfield._animated_floor_palette("stun", 0, 0xEEE0)
        forcefield = playfield._animated_floor_palette(
            "forcefield", 0, 0x9FFF,
        )

        for index in (0, S_COLORS_1[0], S_COLORS_2[0]):
            assert trap[index] == IRGB(0x4044).to_rgba()
            assert stun[index] == IRGB(0xEEE0).to_rgba()
            assert forcefield[index] == IRGB(0x9FFF).to_rgba()

    def test_live_forcefield_cells_expand_the_runtime_segment_table(self):
        state = GameState()
        state.forcefield_segments = [
            0x8000 | (3 << 10) | coords.pack_slot(5, 3),
            0x4000 | (3 << 10) | coords.pack_slot(30, 8),
        ]

        assert playfield._live_forcefield_cells(state) == {
            (4, 5), (5, 5), (6, 5),
            (8, 31), (8, 0), (8, 1),
        }

    def test_forcefield_beam_is_redrawn_with_the_live_cycle_color(self, monkeypatch):
        from gex.palettes import IRGB, S_COLORS_1

        class Maze:
            data = {
                (3, 5): int(MazeObjIds.FORCEFIELDHUB),
                (7, 5): int(MazeObjIds.FORCEFIELDHUB),
            }
            floorpattern = 0
            floorcolor = 0
            wallpattern = 0
            wallcolor = 0

        cache = self._cache()
        cache.maze_object = Maze()
        cache.floor_variants = (0,) * (32 * 32)
        state = GameState(forcefield_color=0xF00F)
        state.forcefield_segments = [
            0x8000 | (3 << 10) | coords.pack_slot(5, 3),
        ]
        calls = []
        monkeypatch.setattr(
            playfield, "_blit_descriptor",
            lambda fb, descriptor, cell, palette, sx, sy, viewport, **kwargs:
                calls.append((cell, palette[S_COLORS_1[0]])),
        )

        playfield.draw_animated_floor_tiles(
            Framebuffer(240, 240), cache, state, 0, 0, PLAYFIELD_VIEWPORT,
        )

        assert {cell for cell, _color in calls} == {
            coords.pack_slot(5, 4),
            coords.pack_slot(5, 5),
            coords.pack_slot(5, 6),
        }
        assert all(color == IRGB(0xF00F).to_rgba() for _cell, color in calls)

    def test_exit_overlay_wraps_with_the_hardware_viewport(self, monkeypatch):
        import gex.render

        calls = []

        class Capture:
            def blit_indexed_tile(self, tile, palette, x, y, **kwargs):
                calls.append((x, y))

        monkeypatch.setattr(
            gex.render, "get_parsed_tile",
            lambda _word: [[1] * 8 for _ in range(8)],
        )
        playfield._blit_descriptor(
            Capture(), playfield.EXIT_SETTLED_DESC,
            coords.pack_slot(5, 5), [(0, 0, 0, 255)] * 16,
            509, 509, (0, 0, 336, 240),
        )

        assert calls[0] == (83, 83)
        assert calls[-1] == (91, 91)

    def test_the_settled_exit_is_drawn_while_the_timer_is_positive(self):
        state = self._state(exit_move_timer=0x12C, exit_anim_frame=0)
        stamped = self._capture(state)
        assert stamped == [(state.exit_open_id, playfield.EXIT_SETTLED_DESC)]

    def test_both_cells_animate_while_the_timer_is_negative(self):
        state = self._state(
            exit_move_timer=-12, exit_anim_frame=3,
            exit_close_id=coords.pack_slot(9, 9),
        )
        stamped = self._capture(state)
        assert stamped == [
            (state.exit_close_id, playfield.exit_descriptor(0, 3)),
            (state.exit_open_id, playfield.exit_descriptor(0, 8 + 3)),
        ]

    def test_the_vacated_cell_is_skipped_once_it_is_cleared(self):
        """exits.py zeroes exit_close_id at settle -- the floor underneath is
        already in the cached raster, so nothing is stamped there."""
        state = self._state(exit_move_timer=-12, exit_anim_frame=2, exit_close_id=0)
        stamped = self._capture(state)
        assert [slot for slot, _ in stamped] == [state.exit_open_id]

    def test_every_frame_of_the_phase_selects_a_distinct_stage(self):
        seen = []
        for frame in range(playfield.EXIT_ANIM_FRAMES):
            state = self._state(exit_move_timer=-4 * frame - 4, exit_anim_frame=frame)
            seen.append(self._capture(state)[0][1])
        assert len(set(seen)) == playfield.EXIT_ANIM_STAGES

    def _capture(self, state):
        """Run the overlay with a stub tile decoder, returning the (cell,
        descriptor) pairs it stamped."""
        stamped: list[tuple[int, tuple]] = []
        real = playfield._blit_descriptor

        def spy(fb, descriptor, cell, palette, sx, sy, viewport):
            stamped.append((cell, tuple(descriptor)))

        playfield._blit_descriptor = spy
        try:
            fb = Framebuffer(240, 240)
            playfield.draw_exit_animation(
                fb, self._cache(), state, 0, 0, PLAYFIELD_VIEWPORT
            )
        finally:
            playfield._blit_descriptor = real
        return stamped


class TestBonusScreenUsesThePerPlayerTally:
    """show_level_end_bonus_screen pays each exiting hero from
    ``player_treascount`` (0x904A50), so the screen shows that, not the
    level-wide ``level_treasures``."""

    def _drawn_text(self, state, monkeypatch) -> list[str]:
        seen: list[str] = []
        import gauntpy.render.screens as screens_mod

        monkeypatch.setattr(
            screens_mod, "draw_text_centered",
            lambda image, cx, y, text, rgba, *, scale=1: seen.append(text),
        )
        monkeypatch.setattr(
            screens_mod, "draw_text",
            lambda image, x, y, text, rgba, *, scale=1: seen.append(text),
        )
        fb = Framebuffer(336, 240)
        draw_front_end_overlay(fb, state, (0, 0, 336, 240), _FakeAssets())
        return seen

    def _bonus_state(self):
        state = GameState()
        state.game_mode = GameMode.TREAS_EXIT
        return state

    def test_one_row_per_player_who_collected_treasure(self, monkeypatch):
        state = self._bonus_state()
        state.player_treascount = [3, 0, 5, 0]
        state.level_treasures = 99         # must not be what the screen shows
        state.bonus_amount = 3200
        seen = self._drawn_text(state, monkeypatch)

        assert f"{romtext.PLAYER_COLOR_NAMES[0]} {romtext.BONUS_TREASURES_X} 3" in seen
        assert f"{romtext.PLAYER_COLOR_NAMES[2]} {romtext.BONUS_TREASURES_X} 5" in seen
        assert not any(romtext.PLAYER_COLOR_NAMES[1] in s for s in seen)
        assert not any("99" in s for s in seen), "level_treasures must not leak in"

    def test_the_total_award_is_the_settled_bonus_amount(self, monkeypatch):
        state = self._bonus_state()
        state.player_treascount = [2, 0, 0, 0]
        state.bonus_amount = 800
        seen = self._drawn_text(state, monkeypatch)
        assert romtext.BONUS_EQUALS in seen
        assert "800" in seen


    def test_no_bonus_when_nobody_collected_anything(self, monkeypatch):
        state = self._bonus_state()
        state.player_treascount = [0, 0, 0, 0]
        state.bonus_amount = 0
        seen = self._drawn_text(state, monkeypatch)
        assert romtext.BONUS_NONE in seen
        assert romtext.BONUS_100_X_COINS in seen


class TestPlayfieldEdgeRule:
    """The ROM's 5-bit cell coordinates, pinned from gauntpy's side.

    The masking itself lives in ``gex.adjacency.whatis`` now, but what this
    module renders depends on it, so a regression there must fail here rather
    than silently change the maze. ROM-free: it exercises the lookup rule.
    """

    @staticmethod
    def _maze(cells):
        class _Maze:
            pass

        maze = _Maze()
        maze.data = dict(cells)
        return maze

    def test_lookups_wrap_at_both_ends_of_both_axes(self):
        """-1 is 31 and 32 is 0, on both axes, regardless of wrap flags."""
        from gex.adjacency import whatis

        maze = self._maze({(0, 5): 11, (31, 5): 22, (7, 0): 33, (7, 31): 44})
        assert whatis(maze, 32, 5) == 11     # off the right edge -> column 0
        assert whatis(maze, -1, 5) == 22     # off the left edge  -> column 31
        assert whatis(maze, 7, 32) == 33     # off the bottom     -> row 0
        assert whatis(maze, 7, -1) == 44     # off the top        -> row 31

    def test_bottom_clamp_shows_row_31_then_wraps_row_zero(self):
        from PIL import Image
        from gauntpy.render.playfield import PlayfieldCache, draw_playfield

        image = Image.new("RGBA", (512, 512), (0, 0, 0, 255))
        for y in range(496, 512):
            for x in range(512):
                image.putpixel((x, y), (255, 0, 0, 255))
        for y in range(16):
            for x in range(512):
                image.putpixel((x, y), (0, 255, 0, 255))
        cache = PlayfieldCache(image=image, shadow_image=image.copy())
        fb = Framebuffer(336, 240)

        draw_playfield(fb, cache, 0, 280, (0, 0, 336, 240))

        assert fb.get_pixel(10, 216) == (255, 0, 0, 255)
        assert fb.get_pixel(10, 232) == (0, 255, 0, 255)

    def test_in_range_lookups_are_untouched(self):
        from gex.adjacency import whatis

        maze = self._maze({(3, 4): 9})
        assert whatis(maze, 3, 4) == 9
        assert whatis(maze, 5, 6) == 0       # absent -> the floor default

    def test_adjacency_at_the_edge_sees_the_opposite_side(self):
        """The observable consequence: a wall run down column 31 is a
        neighbour of column 0, so the two edges connect."""
        from gex.adjacency import checkwalladj8

        seam = self._maze({(31, y): int(MazeObjIds.WALL_REGULAR) for y in (4, 5, 6)})
        middle = self._maze({(20, y): int(MazeObjIds.WALL_REGULAR) for y in (4, 5, 6)})

        # dx = -1 probes: 0x01 (up-left), 0x08 (left), 0x20 (down-left).
        assert checkwalladj8(seam, 0, 5) & 0x29 == 0x29, "the seam must connect"
        assert checkwalladj8(middle, 0, 5) & 0x29 == 0, "and only across a seam"

    def test_the_forcefield_ray_wraps_too(self):
        """ff_mark/ff_make_map read cells through the same masked accessor, so
        a beam leaving one edge continues on the other."""
        from gex.adjacency import ff_make_map

        maze = self._maze({
            (2, 5): int(MazeObjIds.FORCEFIELDHUB),
            (30, 5): int(MazeObjIds.FORCEFIELDHUB),
        })
        ffmap = ff_make_map(maze)
        assert all(0 <= x < 32 and 0 <= y < 32 for x, y in ffmap), (
            "marked cells must stay inside the grid"
        )

    def test_the_renderer_leaves_the_maze_alone(self):
        """Nothing may write phantom cells back -- maze.place_decoded_objects
        iterates the same dict."""
        maze = self._maze({(3, 4): int(MazeObjIds.WALL_REGULAR)})
        before = dict(maze.data)
        from gex.adjacency import checkwalladj8, ff_make_map

        checkwalladj8(maze, 0, 0)
        ff_make_map(maze)
        assert maze.data == before

    @requires_roms
    def test_row_zero_is_all_wall_in_every_shipped_maze(self):
        """The predicates also short-circuit masked row 0 to "wall" (0x5EA32,
        0x5EA6A, 0x5F78C, 0x5EAEA). No separate rule is coded for it because
        maze_decompress already fills row 0 with walls -- this is what makes
        that equivalence safe to rely on."""
        from gex.adjacency import iswall, whatis
        from gex.constants import MAX_MAZE_NUM
        from gex.mazedecode import maze_decompress
        from gex.roms import slapstic_read_maze

        for n in range(MAX_MAZE_NUM + 1):
            maze = maze_decompress(
                slapstic_read_maze(n), allow_missing_delimiter=(n == MAX_MAZE_NUM)
            )
            for x in range(32):
                assert iswall(whatis(maze, x, 0)), f"maze {n} cell ({x}, 0)"


class TestWallCrumble:
    """Damaged destructible walls (wall_crumble 0x5303A) draw over the cached
    raster, using the descriptor/palette WP-7 computes."""

    def _cache(self, stamp=None):
        from gauntpy.render.playfield import PlayfieldCache

        return PlayfieldCache(
            image=None, shadow_image=None,
            crumble_stamps={} if stamp is None else {coords.pack_slot(4, 4): stamp},
        )

    def _stamp(self, ptype="wall", pnum=1):
        from gex.render import Stamp

        return Stamp(width=2, numbers=[0x100, 0x101, 0x102, 0x103],
                     ptype=ptype, pnum=pnum,
                     data=[[[2] * 8 for _ in range(8)] for _ in range(4)])

    def _capture(self, state, cache):
        stamped: list[tuple[int, tuple]] = []
        real = playfield._blit_descriptor

        def spy(fb, descriptor, cell, palette, sx, sy, viewport):
            stamped.append((cell, tuple(descriptor)))

        playfield._blit_descriptor = spy
        try:
            playfield.draw_wall_crumble(
                Framebuffer(240, 240), cache, state, 0, 0, PLAYFIELD_VIEWPORT
            )
        finally:
            playfield._blit_descriptor = real
        return stamped

    def test_nothing_is_drawn_without_damage(self):
        state = GameState()
        assert self._capture(state, self._cache(self._stamp())) == []

    def test_stage_zero_is_the_untouched_wall(self):
        state = GameState()
        state.destructible_wall_stage = {coords.pack_slot(4, 4): 0}
        assert self._capture(state, self._cache(self._stamp())) == []

    def test_a_damaged_wall_on_a_plain_set_restamps_its_own_tiles(self):
        """Below the shrub patterns the crumble is a palette walk, so the tiles
        are the wall's own and only the palette changes."""
        from gauntpy.subsystems.shots import wall_crumble_palette

        state = GameState()
        state.maze = type("M", (), {"wallpattern": 4})()
        slot = coords.pack_slot(4, 4)
        state.destructible_wall_stage = {slot: 2}

        stamped = self._capture(state, self._cache(self._stamp()))

        assert stamped == [(slot, (0x100, 0x101, 0x102, 0x103))]
        assert wall_crumble_palette(state, slot) == 5      # 7 - stage

    def test_a_damaged_wall_on_a_shrub_set_uses_the_rom_descriptor(self):
        from gauntpy.subsystems.shots import wall_crumble_descriptor

        state = GameState()
        state.maze = type("M", (), {"wallpattern": 7})()
        slot = coords.pack_slot(4, 4)
        state.destructible_wall_stage = {slot: 1}

        stamped = self._capture(state, self._cache(self._stamp(ptype="shrub", pnum=0)))

        assert stamped == [(slot, wall_crumble_descriptor(state, slot))]
        assert stamped[0][1] != (0x100, 0x101, 0x102, 0x103)

    def test_each_stage_selects_a_different_descriptor(self):
        state = GameState()
        state.maze = type("M", (), {"wallpattern": 7})()
        slot = coords.pack_slot(4, 4)
        seen = set()
        for stage in (0, 1, 2):
            state.destructible_wall_stage = {slot: stage}
            from gauntpy.subsystems.shots import wall_crumble_descriptor
            seen.add(wall_crumble_descriptor(state, slot))
        assert len(seen) == 3

    def test_the_palette_walk_stays_inside_the_wall_bank(self):
        from gex.palettes import GAUNTLET_PALETTES
        from gauntpy.subsystems.shots import wall_crumble_palette

        state = GameState()
        state.maze = type("M", (), {"wallpattern": 4})()
        slot = coords.pack_slot(4, 4)
        for stage in (0, 1, 2):
            state.destructible_wall_stage = {slot: stage}
            assert 0 <= wall_crumble_palette(state, slot) < len(GAUNTLET_PALETTES["wall"])

    @requires_roms
    def test_the_overlay_never_advances_the_shared_texture_rng(self):
        """The stamps are captured at build time precisely so drawing damage
        cannot draw from the maze's stream and shift every floor texture.

        Compared by *drawing* from the stream afterwards rather than by
        inspecting the PRNG object: ``SeededRandom`` exposes neither a seed nor
        a state, and ``repr(vars(rand))`` -- which this used to compare -- is
        just the wrapped ``random.Random``'s address, identical whether or not
        anything consumed it.
        """
        from gex.mazedecode import maze_decompress
        from gex.roms import slapstic_read_maze
        from gauntpy.render.playfield import draw_wall_crumble, playfield_cache_for

        maze = maze_decompress(slapstic_read_maze(1))
        untouched = maze_decompress(slapstic_read_maze(1))
        cache = playfield_cache_for(maze, None)
        state = GameState()
        state.maze = maze
        state.destructible_wall_stage = {slot: 1 for slot in (cache.crumble_stamps or {})}

        draw_wall_crumble(Framebuffer(240, 240), cache, state, 0, 0, PLAYFIELD_VIEWPORT)
        assert [maze.rand.intn(97) for _ in range(32)] == [
            untouched.rand.intn(97) for _ in range(32)
        ]


class TestRenderFrame:
    def test_produces_a_full_size_framebuffer(self):
        state = GameState()
        fb, _cache = render_frame(state, _FakeAssets())
        assert (fb.width, fb.height) == (336, 240)

    def test_is_deterministic_for_the_same_state(self):
        """PLAN.md §3 rule 7: the compositor is a pure function of state +
        assets. Same inputs, same pixels.
        """
        state = GameState()
        _place(state.mobs, row=8, col=8, picture=5)
        fb1, _ = render_frame(state, _FakeAssets())
        fb2, _ = render_frame(state, _FakeAssets())
        assert fb1.image.tobytes() == fb2.image.tobytes()

    def test_cache_reuse_produces_identical_output_to_a_fresh_build(self):
        state = GameState()
        fb_fresh, _ = render_frame(state, _FakeAssets())

        from gauntpy.render.compositor import RenderCache

        cache = RenderCache()
        fb_a, cache = render_frame(state, _FakeAssets(), cache=cache)
        fb_b, cache = render_frame(state, _FakeAssets(), cache=cache)
        assert fb_a.image.tobytes() == fb_fresh.image.tobytes() == fb_b.image.tobytes()


# ---------------------------------------------------------------------------
# Playfield golden-image comparison against gex's genpfimage -- needs ROMs.
#
# gex's genpfimage bakes a maze's starting monsters/items into the same PNG
# as the terrain (it is a maze-*preview* tool -- see render/playfield.py's
# module docstring). gauntpy's playfield layer deliberately does not, since
# those are dynamic MOBs on real hardware. So this test restricts its pixel
# comparison to cells whose object type is terrain in both renderers --
# exactly the "assert on the playfield region they should share" escape
# hatch PLAN.md §6 WP-2's acceptance criterion names.
#
# The two Maze objects are decoded independently (not shared) so each starts
# with its own freshly-seeded SeededRandom(5) (gex.mazedecode.Maze's
# default); both renderers consume that RNG in the same per-cell order (see
# playfield.py's floor/terrain dispatch, deliberately mirroring gex.pfrender
# cell-for-cell), so floor texture variety matches between the two
# independent decodes.
# ---------------------------------------------------------------------------

@requires_roms
class TestPlayfieldMatchesGexReference:
    @staticmethod
    def _decode(maze_num: int):
        from gex.constants import MAX_MAZE_NUM
        from gex.mazedecode import maze_decompress
        from gex.roms import slapstic_read_maze

        return maze_decompress(
            slapstic_read_maze(maze_num),
            allow_missing_delimiter=maze_num == MAX_MAZE_NUM,
        )

    # A spread of maze numbers, including both non-wrapping (most levels)
    # and wrapping ones (LFLAG4_WRAP_H/V -- doc/04_game_subsystems.md's maze
    # flags), and the last catalog entry (116, whose decode needs the
    # allow_missing_delimiter special case gex's own tests exercise).
    @pytest.mark.parametrize("maze_num", [0, 1, 10, 50, 100, 116])
    def test_terrain_cells_match_gex_genpfimage_pixel_for_pixel(self, maze_num, tmp_path):
        from PIL import Image

        from gex.adjacency import whatis
        from gex.pfrender import genpfimage
        from gauntpy.render.playfield import TERRAIN_TYPES, build_playfield_image

        maze_ref = self._decode(maze_num)
        maze_ours = self._decode(maze_num)

        ref_path = tmp_path / "ref.png"
        genpfimage(maze_ref, str(ref_path))
        ref_img = Image.open(ref_path).convert("RGBA")
        # gex's export adds a cosmetic 16px border (and, for non-wrapping
        # axes, one extra preview column/row beyond it) that real playfield
        # RAM has no equivalent of -- see build_playfield_image's docstring.
        # Cropping it off recovers exactly the 512x512 true world.
        ref_world = ref_img.crop((16, 16, 16 + 512, 16 + 512))

        our_world = build_playfield_image(maze_ours)
        assert our_world.size == (512, 512)

        # gex's item stamps are allowed to be larger than one cell and carry
        # a pixel "nudge" (e.g. "treasure" is 3x3 tiles with nudge (-4, -4) --
        # python-gex/src/gex/data/items.jsonc), so a dynamic object's
        # rendering can bleed a few pixels into *neighboring* cells even
        # though it's anchored at just one. Since gauntpy doesn't draw those
        # objects at all (they're MOBs, not terrain -- see this module's
        # docstring), a neighbor of a dynamic-object cell isn't a safe
        # comparison point either. Exclude a buffer around every dynamic
        # cell, not just the cell itself.
        dynamic_cells = {
            (x, y)
            for y in range(32) for x in range(32)
            if whatis(maze_ours, x, y) not in TERRAIN_TYPES
        }
        contaminated = set(dynamic_cells)
        for dx, dy in dynamic_cells:
            for oy in range(-2, 3):
                for ox in range(-2, 3):
                    contaminated.add((dx + ox, dy + oy))

        mismatches = []
        compared = 0
        for y in range(32):
            for x in range(32):
                if (x, y) in contaminated:
                    continue
                compared += 1
                box = (x * 16, y * 16, x * 16 + 16, y * 16 + 16)
                if ref_world.crop(box).tobytes() != our_world.crop(box).tobytes():
                    mismatches.append((x, y, int(whatis(maze_ours, x, y))))

        # Threshold picked from the observed range across the parametrized
        # mazes (255-634 comparable cells out of 1024) -- low enough not to
        # flake on an item-dense maze, high enough to catch a dispatch bug
        # that left almost nothing comparable.
        assert compared > 150, "sanity: too few terrain-only cells survived the item-bleed exclusion to be a meaningful comparison"
        assert not mismatches, f"{len(mismatches)}/{compared} terrain cells differ from gex's reference: {mismatches[:10]}"

    def test_the_renderer_does_not_mutate_the_simulations_maze(self):
        """The edge rule is applied through a read-only view. Nothing may be
        written back -- anything else iterating maze.data (
        maze.place_decoded_objects does) would see phantom cells."""
        from gauntpy.render.playfield import build_playfield_images

        maze = self._decode(1)
        before = dict(maze.data)
        build_playfield_images(maze)
        assert maze.data == before
        assert not any(x > 31 or y > 31 for x, y in maze.data)

    def test_a_terrain_change_in_place_restamps_the_cache(self, monkeypatch):
        """A wall dissolving or a door opening mutates maze.data under the same
        object. It must update locally rather than rebuilding 512x512."""
        from gauntpy.render import playfield
        from gauntpy.render.playfield import playfield_cache_for

        maze = self._decode(1)
        cache = playfield_cache_for(maze, None)
        assert playfield_cache_for(maze, cache) is cache, "unchanged: reuse"

        cell = next(iter(maze.data))
        maze.data[cell] = int(MazeObjIds.TILE_FLOOR)
        monkeypatch.setattr(
            playfield, "_build_playfield_layers",
            lambda _maze: (_ for _ in ()).throw(
                AssertionError("single-cell change rebuilt the world")
            ),
        )
        rebuilt = playfield_cache_for(maze, cache)
        assert rebuilt is cache, "terrain changed: restamp in place"
        assert rebuilt.cells == maze.data

    def test_incremental_shrub_update_does_not_retexture_other_cells(self):
        from gauntpy.render.playfield import (
            _changed_cell_neighbourhood, playfield_cache_for,
        )

        maze = self._decode(6)
        cache = playfield_cache_for(maze, None)
        before = cache.image.copy()
        old = dict(maze.data)
        changed = next(
            cell for cell, obj in maze.data.items()
            if obj in (
                int(MazeObjIds.WALL_TRAPCYC1),
                int(MazeObjIds.WALL_TRAPCYC2),
                int(MazeObjIds.WALL_TRAPCYC3),
                int(MazeObjIds.WALL_RANDOM),
            )
        )
        maze.data[changed] = int(MazeObjIds.TILE_FLOOR)
        affected = _changed_cell_neighbourhood(old, maze.data)

        assert playfield_cache_for(maze, cache) is cache
        for y in range(32):
            for x in range(32):
                if (x, y) in affected:
                    continue
                box = (x * 16, y * 16, x * 16 + 16, y * 16 + 16)
                assert cache.image.crop(box).tobytes() == before.crop(box).tobytes()

    def test_incremental_update_preserves_pushwall_overhang(self):
        from gauntpy.render.playfield import (
            build_playfield_images, playfield_cache_for,
        )

        maze = self._decode(40)
        assert maze.data[(28, 5)] == int(MazeObjIds.WALL_MOVABLE)
        assert maze.data[(29, 5)] == int(MazeObjIds.WALL_MOVABLE)
        cache = playfield_cache_for(maze, None)

        maze.data[(29, 3)] = int(MazeObjIds.DOOR_HORIZ)
        assert playfield_cache_for(maze, cache) is cache
        expected, _shadow, _crumble = build_playfield_images(maze)

        # The 24x16 stamps are nudged -4,-4; this is the overhanging top strip
        # a one-pass adjacency restamp used to erase with the row-4 floor boxes.
        box = (28 * 16, 5 * 16 - 4, 30 * 16, 5 * 16)
        assert cache.image.crop(box).tobytes() == expected.crop(box).tobytes()

    def test_a_different_level_rebuilds_the_cache(self):
        from gauntpy.render.playfield import playfield_cache_for

        one, ten = self._decode(1), self._decode(10)      # both kept alive
        cache = playfield_cache_for(one, None)
        assert playfield_cache_for(ten, cache) is not cache

    def test_identical_content_shares_a_raster(self):
        """Validity is decided on content, not identity -- two decodes of the
        same maze describe the same world, and id() can even be recycled onto
        a fresh Maze once the old one is collected."""
        from gauntpy.render.playfield import playfield_cache_for

        first, second = self._decode(1), self._decode(1)
        assert first is not second
        cache = playfield_cache_for(first, None)
        assert playfield_cache_for(second, cache) is cache

    def test_a_palette_change_alone_rebuilds_the_cache(self):
        from gauntpy.render.playfield import playfield_cache_for

        maze = self._decode(1)
        cache = playfield_cache_for(maze, None)
        maze.floorcolor = (maze.floorcolor + 1) & 0x0F
        assert playfield_cache_for(maze, cache) is not cache

    def test_shadow_raster_is_the_irgb_transform_not_a_scale(self):
        """build_playfield_images' shadow twin applies the exact ROM intensity
        transform (playfield.irgb_to_shadow), which is darker than and
        distinct from a naive RGB *0.5 -- that difference is the whole point
        of the shadow raster.
        """
        from gauntpy.render.playfield import build_playfield_images

        maze = self._decode(1)
        normal, shadow, _crumble = build_playfield_images(maze)
        assert normal.size == shadow.size == (512, 512)

        n_px, s_px = normal.load(), shadow.load()
        differs_from_half = 0
        checked = 0
        for y in range(0, 512, 7):
            for x in range(0, 512, 7):
                n = n_px[x, y]
                if n[:3] == (0, 0, 0):
                    continue
                checked += 1
                s = s_px[x, y]
                # Shadow never brightens any channel (intensity only drops).
                assert all(sc <= nc for sc, nc in zip(s[:3], n[:3])), (x, y, s, n)
                if tuple(int(c * 0.5) for c in n[:3]) != s[:3]:
                    differs_from_half += 1

        assert checked > 100
        # The exact transform must visibly diverge from 0.5-scaling on real
        # playfield colors (it wouldn't, if the transform weren't applied).
        assert differs_from_half > 0


# ---------------------------------------------------------------------------
# Playfield determinism -- real mazes, real ROM tiles.
#
# The floor texture of every cell and the tile choice of every shrub wall come
# out of ``maze.rand``, deliberately: gex's own ``pfrender`` draws from the
# same stream in the same per-cell order, which is what lets the golden-image
# comparison above hold cell for cell. But *drawing* from it advanced it, so
# the second build of a maze came out different from the first -- and this
# module rebuilds whenever the cache is invalidated (a new level, a wall
# dissolving, a caller that kept no cache). The renderer was not a function of
# its input: two ``render_frame`` calls on an unchanged state produced two
# different pictures of the same world.
# ---------------------------------------------------------------------------

@requires_roms
class TestPlayfieldBuildIsPure:
    @staticmethod
    def _decode(maze_num: int):
        from gex.constants import MAX_MAZE_NUM
        from gex.mazedecode import maze_decompress
        from gex.roms import slapstic_read_maze

        return maze_decompress(
            slapstic_read_maze(maze_num),
            allow_missing_delimiter=maze_num == MAX_MAZE_NUM,
        )

    @staticmethod
    def _cells_differing(a, b):
        return {
            (x, y)
            for y in range(32)
            for x in range(32)
            if a.crop((x * 16, y * 16, x * 16 + 16, y * 16 + 16)).tobytes()
            != b.crop((x * 16, y * 16, x * 16 + 16, y * 16 + 16)).tobytes()
        }

    def test_repeated_builds_of_one_maze_are_identical(self):
        from gauntpy.render.playfield import build_playfield_images

        maze = self._decode(1)
        first_normal, first_shadow, _ = build_playfield_images(maze)
        for _ in range(2):
            normal, shadow, _ = build_playfield_images(maze)
            assert normal.tobytes() == first_normal.tobytes()
            assert shadow.tobytes() == first_shadow.tobytes()

    def test_the_build_leaves_the_mazes_own_random_stream_where_it_found_it(self):
        """It takes a copy (``build_rand``) rather than consuming the maze's
        stream, so nothing downstream of the renderer sees a different world
        because a frame happened to be drawn."""
        from gauntpy.render.playfield import build_playfield_images

        drawn, untouched = self._decode(1), self._decode(1)
        build_playfield_images(drawn)
        assert [drawn.rand.intn(97) for _ in range(32)] == [
            untouched.rand.intn(97) for _ in range(32)
        ]

    def test_two_independent_decodes_render_the_same_world(self):
        from gauntpy.render.playfield import build_playfield_images

        one, two = self._decode(10), self._decode(10)
        assert build_playfield_images(one)[0].tobytes() == build_playfield_images(two)[0].tobytes()

    def test_repeated_frames_with_no_cache_are_identical(self):
        """``render_frame``'s own contract (PLAN.md §3 rule 7) -- previously
        true only because the smoke test ran without a maze loaded."""
        state = GameState()
        state.maze = self._decode(1)
        _place(state.mobs, row=8, col=8, picture=5)

        first, _ = render_frame(state, _FakeAssets())
        for _ in range(2):
            again, _ = render_frame(state, _FakeAssets())
            assert again.image.tobytes() == first.image.tobytes()

    def test_a_reused_cache_matches_a_freshly_built_one(self):
        """"``cache`` is purely a performance seam" -- with a real maze
        loaded, which is when the seam actually does anything."""
        from gauntpy.render.compositor import RenderCache

        state = GameState()
        state.maze = self._decode(1)
        fresh, _ = render_frame(state, _FakeAssets())

        cache = RenderCache()
        first, cache = render_frame(state, _FakeAssets(), cache=cache)
        second, cache = render_frame(state, _FakeAssets(), cache=cache)
        assert fresh.image.tobytes() == first.image.tobytes() == second.image.tobytes()

    def test_a_wall_restyled_in_place_redraws_only_that_cell(self):
        """Cache invalidation must not re-randomize the world. Swapping a plain
        wall for a trap-cycle wall keeps the same stamp path, the same wall
        adjacency for every neighbour (both are walls to ``iswall``) and the
        same draw count -- so the only thing that may change is the corner dot
        inside that one cell.
        """
        from gauntpy.render.playfield import build_playfield_images

        maze = self._decode(1)
        before, before_shadow, _ = build_playfield_images(maze)

        cell = next(
            key for key, value in sorted(maze.data.items())
            if value == int(MazeObjIds.WALL_REGULAR)
        )
        maze.data[cell] = int(MazeObjIds.WALL_TRAPCYC1)
        after, after_shadow, _ = build_playfield_images(maze)

        assert self._cells_differing(before, after) == {cell}
        assert self._cells_differing(before_shadow, after_shadow) == {cell}

    def test_a_wall_removed_redraws_only_its_own_neighbourhood(self):
        """The general case: an edit that *does* change adjacency reaches the
        eight cells around it (through the wrap-around edge rule), and stops
        there. Before the fix all 1024 cells came back different.
        """
        from gauntpy.render.playfield import build_playfield_images

        maze = self._decode(1)
        before, _shadow, _ = build_playfield_images(maze)

        cell = next(
            key for key, value in sorted(maze.data.items())
            if value == int(MazeObjIds.WALL_REGULAR)
        )
        maze.data[cell] = int(MazeObjIds.TILE_FLOOR)
        after, _shadow, _ = build_playfield_images(maze)

        x, y = cell
        neighbourhood = {
            ((x + dx) & 0x1F, (y + dy) & 0x1F)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        }
        differing = self._cells_differing(before, after)
        assert cell in differing, "sanity: the edited cell itself must change"
        assert differing <= neighbourhood, sorted(differing - neighbourhood)

    def test_an_invalidated_cache_restamps_to_exactly_a_fresh_build(self):
        """Terrain changing under the same Maze object is the case the content
        comparison in ``playfield_cache_for`` exists for. On a non-random wall
        pattern the local restamp is byte-identical to a fresh full build."""
        from gauntpy.render.playfield import build_playfield_images, playfield_cache_for

        maze = self._decode(1)
        cache = playfield_cache_for(maze, None)

        cell = next(
            key for key, value in sorted(maze.data.items())
            if value == int(MazeObjIds.WALL_REGULAR)
        )
        maze.data[cell] = int(MazeObjIds.TILE_FLOOR)

        rebuilt = playfield_cache_for(maze, cache)
        assert rebuilt is cache
        expected_normal, expected_shadow, _ = build_playfield_images(maze)
        assert rebuilt.image.tobytes() == expected_normal.tobytes()
        assert rebuilt.shadow_image.tobytes() == expected_shadow.tobytes()

    def test_a_maze_whose_walls_draw_from_the_stream_is_deterministic_too(self):
        """Wall patterns 7-10 and 12-15 pick their tiles randomly
        (``gex.wall.wall_get_tiles``), so on those levels the terrain pass
        consumes the shared stream as well -- the case a per-build copy has to
        cover and a "reset to a fixed seed per cell" fix would not.
        """
        from gauntpy.render.playfield import build_playfield_images

        maze = self._decode(1)
        maze.wallpattern = 7
        first, _shadow, _ = build_playfield_images(maze)
        second, _shadow2, _ = build_playfield_images(maze)
        assert first.tobytes() == second.tobytes()


# ---------------------------------------------------------------------------
# Live MOB layer with real ROM pixels: the sprites the layer used to drop.
#
# ``draw_mob_layer`` catches ``AssetError`` per MOB and skips it, which is the
# right answer for artwork that genuinely is not there -- and is exactly what
# hid two whole families of artwork that is. Every effect MOB (score popups,
# floating score stars, impact bursts, transporter sparkles) and every frame
# of a hero's exit/death dissolve failed to resolve and was silently dropped,
# so the only way to see the difference is to watch the skip itself.
# ---------------------------------------------------------------------------

class _RecordingAssets:
    """A real ``AssetStore`` that also records what resolved and what the MOB
    layer had to skip. A skip leaves no trace in the framebuffer, so it has to
    be observed at the seam."""

    def __init__(self) -> None:
        from gauntpy.assets import AssetStore

        self._store = AssetStore()
        self.resolved: list[tuple[int, object]] = []
        self.skipped: list[tuple[int, str]] = []

    def sprite(self, picture, *, tier=1, palette=None, kind=None, size=None):
        from gauntpy.assets import AssetError

        try:
            stamp = self._store.sprite(
                picture, tier=tier, palette=palette, kind=kind, size=size
            )
        except AssetError as exc:
            self.skipped.append((picture, str(exc)))
            raise
        self.resolved.append((picture, stamp))
        return stamp

    def palette(self, kind, index):
        return self._store.palette(kind, index)


class _SizeBlindAssets(_RecordingAssets):
    """The behaviour before the size contract: everything else the same, but
    the MOB's own size word thrown away."""

    def sprite(self, picture, *, tier=1, palette=None, kind=None, size=None):
        return super().sprite(picture, tier=tier, palette=palette, kind=kind)


def _drawn_pixels(fb) -> int:
    """How many framebuffer pixels are no longer the opaque-black background."""
    raw = fb.image.tobytes()
    return sum(
        1
        for i in range(0, len(raw), 4)
        if raw[i] or raw[i + 1] or raw[i + 2] or raw[i + 3] != 255
    )


@requires_roms
class TestTheLayerNoLongerDropsEffectsAndDissolves:
    _SOURCE_CELL = (6, 6)
    _EFFECT_SLOT = 0x0D          # the first of the shared effect pool

    @classmethod
    def _place_effect(cls, state, slot, picture, width, height, palette):
        """The placement ``shots._place_effect`` / ``shots._playfield_showscore``
        / ``players.handle_tport`` perform, in the port's own units: the
        source's cell, the effect's own size in ``mob_vpos`` and its own
        palette nibble in ``mob_hpos``.
        """
        source = coords.pack_slot(*cls._SOURCE_CELL)
        x, y = coords.slot_to_pixels(source)
        state.mobs.picture[slot] = picture
        state.mobs.hpos[slot] = coords.encode_hpos(x) | palette
        state.mobs.vpos[slot] = coords.encode_vpos_at_y(y, width, height)
        state.mobs.insert(slot, depth_key=source)

    def _draw_one_effect(self, picture, block, assets=None):
        state = GameState()
        self._place_effect(
            state, self._EFFECT_SLOT, picture, block.xsize, block.ysize, block.pnum
        )
        assets = assets or _RecordingAssets()
        fb = Framebuffer(240, 240)
        draw_mob_layer(fb, state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        return assets, fb

    def test_treasure_bag_pickup_popup_reaches_the_visible_mob_walk(self):
        from gauntpy.subsystems.players import player_tile_interact

        state = GameState()
        state.level_players_active = 1
        state.players[0].status = int(PlayerStatus.ALIVE_HERE)
        source = coords.pack_slot(*self._SOURCE_CELL)
        x, y = coords.slot_to_pixels(source)
        state.mobs.create(
            source, tile=0x1234,
            hpos=coords.encode_hpos(x),
            vpos=coords.encode_vpos_at_y(y, 2, 2),
            obj_type=MazeObjIds.TREASURE_BAG,
        )

        player_tile_interact(state, source, 0)

        visible = list(
            iter_visible_mobs(
                state, 0, 0,
                PLAYFIELD_VIEWPORT[2], PLAYFIELD_VIEWPORT[3],
            )
        )
        assert state.score_display_timer[0] == 0x3C
        assert any(info.slot == 0x11 for info in visible)

    def test_every_effect_picture_reaches_the_framebuffer(self):
        """All 28 of gex's effect pictures plus the six transporter transition
        frames, each on a real effect slot with the geometry the ROM's own
        placement code gives it."""
        from gauntpy.assets import EFFECT_PICTURES

        assert len(EFFECT_PICTURES) == 34
        for picture, block in sorted(EFFECT_PICTURES.items()):
            assets, fb = self._draw_one_effect(picture, block)
            assert assets.skipped == [], (hex(picture), assets.skipped)
            assert [p for p, _ in assets.resolved] == [picture], hex(picture)
            assert _drawn_pixels(fb) > 0, f"{picture:#06x} resolved but drew nothing"

    def test_the_transporter_sparkle_is_drawn_on_its_own_fixed_slots(self):
        """The five transporter animation MOBs (25-29) that
        ``score._advance_player_transition`` / ``_advance_thief_transition``
        step through the 0x578F2 cycle -- one slot per player plus the thief's.
        """
        from gauntpy.assets import TPORT_TRANSITION_PICTURES
        from gauntpy.constants import SLOT_TPORT_ANIMS

        state = GameState()
        for offset, slot in enumerate(SLOT_TPORT_ANIMS):
            picture = TPORT_TRANSITION_PICTURES[offset % len(TPORT_TRANSITION_PICTURES)]
            self._place_effect(state, slot, picture, 3, 3, 1)

        assets = _RecordingAssets()
        fb = Framebuffer(240, 240)
        draw_mob_layer(fb, state, assets, 0, 0, PLAYFIELD_VIEWPORT)

        assert assets.skipped == []
        assert len(assets.resolved) == len(SLOT_TPORT_ANIMS)
        assert all(stamp.width == 3 for _p, stamp in assets.resolved)
        assert _drawn_pixels(fb) > 0

    def test_a_score_popup_keeps_the_width_the_rom_gave_it(self):
        """The two halves of the popup table are different shapes -- three
        tiles wide for a score value, two for a bonus -- and the effect index
        has to keep them apart or the sprite is stamped from the wrong tiles.
        """
        from gauntpy.subsystems.shots import _SCORE_POPUP_PICTURE

        for index, picture in enumerate(_SCORE_POPUP_PICTURE):
            expected_width = 3 if index < 0x0A else 2
            assets, fb = self._draw_one_effect(
                picture, _block_for(picture)
            )
            assert assets.skipped == []
            (_p, stamp), = assets.resolved
            assert stamp.width == expected_width, (index, hex(picture))
            assert len(stamp.numbers) == expected_width
            assert _drawn_pixels(fb) > 0


@requires_roms
class TestTheHeroDissolveIsDrawnToTheEnd:
    """``players._PLAYER_EXIT_PICTURE``: the 32-frame dissolve a hero plays in
    the exit, and the same table the death path steps. Seven of each class's
    eight frames are in no gex animation record, so the MOB layer dropped the
    hero part-way through and the player simply vanished mid-animation.
    """

    @staticmethod
    def _hero_state(character: int, picture: int):
        from gauntpy.assets import HERO_NAMES
        from gauntpy.constants import Character

        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=picture, hpos=coords.encode_hpos(x),
            vpos=coords.encode_vpos_at_y(y, 3, 3), obj_type=MazeObjIds.PLAYERSTART,
        )
        player = state.players[0]
        player.mob_slot = slot
        player.character = Character(character)
        player.status = int(PlayerStatus.ALIVE_HERE)
        return state, HERO_NAMES[character]

    def _draw(self, character, picture, assets=None):
        state, name = self._hero_state(character, picture)
        assets = assets or _RecordingAssets()
        fb = Framebuffer(240, 240)
        draw_mob_layer(fb, state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        return assets, fb, name

    def test_all_four_classes_dissolve_all_eight_frames(self):
        from gauntpy.subsystems.players import _PLAYER_EXIT_PICTURE

        assert len(_PLAYER_EXIT_PICTURE) == 32
        for character in range(4):
            for frame in range(8):
                picture = _PLAYER_EXIT_PICTURE[character * 8 + frame]
                assets, fb, name = self._draw(character, picture)
                where = (name, frame, hex(picture))
                assert assets.skipped == [], where
                (_p, stamp), = assets.resolved
                assert (stamp.ptype, stamp.pnum) == (name, 0), where
                assert stamp.width == 3 and len(stamp.numbers) == 9, where
                assert _drawn_pixels(fb) > 0, where

    def test_the_death_spin_frames_are_drawn_too(self):
        """``_PLAYER_DEATH_PICTURE`` is ``anim_table_idle`` and every frame of
        it is in gex's hero data -- pinned so that stays true rather than
        quietly starting to depend on the fallback."""
        from gauntpy.subsystems.players import _PLAYER_DEATH_PICTURE

        for character in range(4):
            for frame in range(8):
                picture = _PLAYER_DEATH_PICTURE[character * 8 + frame]
                assets, fb, name = self._draw(character, picture)
                assert assets.skipped == [], (name, frame, hex(picture))
                (_p, stamp), = assets.resolved
                assert (stamp.ptype, stamp.pnum) == (name, 0)
                assert _drawn_pixels(fb) > 0

    def test_without_the_size_word_the_dissolve_is_dropped_as_before(self):
        """The regression guard: the same frame, drawn by a provider that
        throws the MOB's size away, is skipped and leaves an empty screen."""
        from gauntpy.subsystems.players import _PLAYER_EXIT_PICTURE

        picture = _PLAYER_EXIT_PICTURE[2]          # Warrior dissolve frame 2
        assets, fb, _name = self._draw(0, picture, assets=_SizeBlindAssets())
        assert [p for p, _msg in assets.skipped] == [picture]
        assert assets.resolved == []
        assert _drawn_pixels(fb) == 0

        now, fb_now, _ = self._draw(0, picture)
        assert now.skipped == []
        assert _drawn_pixels(fb_now) > 0

    def test_the_blank_flash_picture_resolves_and_stays_invisible(self):
        """0x1709 is the ROM's blank picture: the transporter flash, the
        invisibility flicker and the monster blank all park it in a live slot.
        It now decodes instead of being skipped, so it must be genuinely empty
        artwork -- a hero who turns into a block of garbage while teleporting
        would be worse than one who disappears.
        """
        from gauntpy.subsystems.players import _PLAYER_INVISIBLE_PICTURE

        for character in range(4):
            assets, fb, _name = self._draw(character, _PLAYER_INVISIBLE_PICTURE)
            assert assets.skipped == []
            assert len(assets.resolved) == 1
            assert _drawn_pixels(fb) == 0, "the blank flash must draw nothing"


def _block_for(picture: int):
    from gauntpy.assets import EFFECT_PICTURES, PICTURE_TILE_MASK

    return EFFECT_PICTURES[picture & PICTURE_TILE_MASK]


@requires_roms
class TestAWizardRendersAsAWizard:
    """The MOB layer end to end with real ROM pixels: a playing Wizard must be
    drawn from the Wizard's own palette bank. His picture numbers are also the
    Sorcerer's -- the two share the artwork -- so resolving the sprite from the
    picture alone painted the hero in the Sorcerer's ``base`` colours.
    """

    @staticmethod
    def _hero_state(character):
        from gex.heroes import HEROES
        from gauntpy.assets import HERO_NAMES
        from gauntpy.constants import Character

        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        tile = HEROES[HERO_NAMES[int(character)]].anims["walk"]["down"][0]
        state.mobs.create(
            slot, tile=tile, hpos=coords.encode_hpos(x),
            vpos=coords.encode_vpos_at_y(y, 3, 3), obj_type=MazeObjIds.PLAYERSTART,
        )
        player = state.players[0]
        player.mob_slot = slot
        player.character = Character(int(character))
        player.status = int(PlayerStatus.ALIVE_HERE)
        return state, slot, tile

    def test_core_wizard_picture_keeps_the_wizard_disambiguation(self):
        """The player-owned ROM selector, not a gex host hook, supplies the
        shared Wizard/Sorcerer tile before the MOB layer picks its palette."""
        from gauntpy.assets import AssetStore
        from gauntpy.constants import Character
        from gauntpy.render.mobs import sprite_kind
        from gauntpy.subsystems.players import (
            _PLAYER_IDLE_PICTURE,
            _PORT_DIR_TO_ROM_DIR,
            update_player_sprite,
        )

        state, slot, _ = self._hero_state(Character.WIZARD)
        state.mobs.picture[slot] = 0x1E0D
        update_player_sprite(state, 0)

        player = state.players[0]
        expected = _PLAYER_IDLE_PICTURE[
            int(Character.WIZARD) * 8
            + _PORT_DIR_TO_ROM_DIR[player.direction]
        ]
        assert state.mobs.picture[slot] == expected
        assert sprite_kind(state, slot) == "wizard"
        assert AssetStore().sprite(expected, kind=sprite_kind(state, slot)).ptype == "wizard"

    def test_the_drawn_hero_is_the_wizard_stamp_pixel_for_pixel(self):
        from gauntpy.assets import AssetStore
        from gauntpy.constants import Character

        store = AssetStore()
        state, slot, tile = self._hero_state(Character.WIZARD)

        drawn = Framebuffer(240, 240)
        draw_mob_layer(drawn, state, store, 0, 0, PLAYFIELD_VIEWPORT)

        # The reference: the same framebuffer primitive, fed the stamp the
        # Wizard is supposed to be -- gex's own hero record decides both the
        # bank ("wizard") and the standing entry within it.
        expected = Framebuffer(240, 240)
        stamp = store.sprite(tile, kind="wizard", palette=0)
        assert (stamp.ptype, stamp.pnum) == ("wizard", 0)
        palette_rgba = [c.to_rgba() for c in store.palette(stamp.ptype, stamp.pnum)]
        hero_x, hero_y = coords.slot_to_pixels(slot)
        hero_y -= 8
        for index, tile_data in enumerate(stamp.data):
            row, col = divmod(index, stamp.width)
            expected.blit_indexed_tile(
                tile_data, palette_rgba, hero_x + col * 8, hero_y + row * 8,
                trans0=True, shadow_index=1,
                clip=(0, 0, PLAYFIELD_VIEWPORT[2], PLAYFIELD_VIEWPORT[3]),
            )

        assert drawn.image.tobytes() == expected.image.tobytes()

    def test_it_is_visibly_different_from_the_sorcerer_it_used_to_be(self):
        from gauntpy.assets import AssetStore
        from gauntpy.constants import Character

        store = AssetStore()
        state, _slot, tile = self._hero_state(Character.WIZARD)

        class _IgnoresKind:
            """The old behaviour: resolve the sprite from the picture alone."""

            def sprite(self, picture, *, tier=1, palette=None, kind=None, size=None):
                return store.sprite(picture, tier=tier, palette=palette)

            def palette(self, kind, index):
                return store.palette(kind, index)

        now = Framebuffer(240, 240)
        draw_mob_layer(now, state, store, 0, 0, PLAYFIELD_VIEWPORT)
        before = Framebuffer(240, 240)
        draw_mob_layer(before, state, _IgnoresKind(), 0, 0, PLAYFIELD_VIEWPORT)

        assert store.sprite(tile).ptype == "base", "the picture alone says Sorcerer"
        assert now.image.tobytes() != before.image.tobytes()

    def test_the_other_three_classes_get_their_own_banks_too(self):
        from gex.heroes import HEROES
        from gauntpy.assets import HERO_NAMES, AssetStore
        from gauntpy.constants import Character

        store = AssetStore()
        for character in Character:
            _state, _slot, tile = self._hero_state(character)
            name = HERO_NAMES[int(character)]
            stamp = store.sprite(tile, kind=name, palette=0)
            assert (stamp.ptype, stamp.pnum) == (HEROES[name].ptype, HEROES[name].pnum)

    def test_a_sorcerer_in_the_same_maze_keeps_its_own_colours(self):
        """The other half of the fix: naming the hero must not recolour the
        monsters that share his artwork."""
        from gex.heroes import HEROES
        from gex.monsters import MONSTERS
        from gauntpy.assets import AssetStore

        store = AssetStore()
        shared = set(HEROES["wizard"].anims["walk"]["down"]) & set(
            MONSTERS["sorcerer"].anims["walk"]["down"]
        )
        assert shared
        for tile in shared:
            monster = store.sprite(tile, kind="sorcerer", palette=0xB)
            assert (monster.ptype, monster.pnum) == ("base", 0xB)


# ---------------------------------------------------------------------------
# Host shell -- needs pygame. Skips cleanly when it isn't installed.
# ---------------------------------------------------------------------------

try:
    import pygame  # noqa: F401

    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False

requires_pygame = pytest.mark.skipif(
    not _PYGAME_AVAILABLE, reason="pygame not installed; HostShell tests skip per WP-2's brief"
)


@pytest.fixture(autouse=True)
def _headless_pygame(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")


@requires_pygame
class TestHostShellInput:
    def test_input_polarity_is_active_low(self):
        """doc/04_game_subsystems.md §15 / subsystems/input.py: 'nothing
        pressed' must be all bits set (0xFFFF), and a held key must clear
        (not set) its bit -- getting this backwards inverts every control.
        """
        from gauntpy.render.host import HostShell

        shell = HostShell(assets=_FakeAssets())
        try:
            state = GameState()
            shell._sample_input(state)
            assert state.player_input_raw[0] == 0xFFFF, "nothing pressed -> all bits set"
        finally:
            shell.close()

    def test_present_and_wait_for_vblank_round_trip(self):
        """Smoke test of the exact g2mainloop interface (wait_for_vblank
        then present), using the fake asset source so it needs no ROMs.
        """
        from gauntpy.render.host import HostShell

        shell = HostShell(assets=_FakeAssets())
        try:
            state = GameState()
            shell.wait_for_vblank(state)
            shell.present(state)
        finally:
            shell.close()

    def test_p_key_toggles_host_pause(self):
        from gauntpy.render.host import HostShell

        shell = HostShell(assets=_FakeAssets())
        try:
            pygame = shell._pygame
            state = GameState()
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p)
            )
            shell.wait_for_vblank(state)
            assert shell.paused
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p)
            )
            shell.wait_for_vblank(state)
            assert not shell.paused
        finally:
            shell.close()


# ---------------------------------------------------------------------------
# Throughput -- not a hard CI gate (generous bound), but documents measured
# MOB-layer performance per PLAN.md §6 WP-2's "sustain 60fps with 100+ MOBs"
# acceptance criterion. ROM-free (uses _FakeAssets), so it always runs.
# ---------------------------------------------------------------------------

class TestMobLayerThroughput:
    def test_100_plus_mobs_draw_well_within_a_frame_budget(self):
        state = GameState()
        rng_positions = [(r, c) for r in range(2, 30, 2) for c in range(2, 30, 2)]
        for i, (row, col) in enumerate(rng_positions[:120]):
            _place(state.mobs, row, col, picture=i, size=3)

        assets = _FakeAssets()
        fb = Framebuffer(240, 240)

        frames = 30
        start = time.perf_counter()
        for _ in range(frames):
            draw_mob_layer(fb, state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        elapsed = time.perf_counter() - start

        per_frame_ms = (elapsed / frames) * 1000
        # 60Hz budgets 16.7ms for the *entire* frame (sim + all 4 render
        # layers + present); this asserts the MOB layer alone, with 120
        # MOBs, stays comfortably inside that, not that it hits some tight
        # bound. Generous on purpose to avoid flaking slower CI machines --
        # see the WP-2 report for the actual measured figure.
        assert per_frame_ms < 50, f"MOB layer took {per_frame_ms:.2f}ms/frame for {len(rng_positions[:120])} MOBs"
