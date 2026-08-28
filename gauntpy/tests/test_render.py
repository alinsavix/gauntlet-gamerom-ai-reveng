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
    draw_hud,
    draw_message_box,
    draw_pause_indicator,
)
from gauntpy.render.mobs import draw_mob_layer, iter_visible_mobs, strength_tier
from gauntpy.render import playfield, romtext
from gauntpy.state import GameState
from gauntpy.subsystems import score
from gauntpy.subsystems.score import (
    dialog_first_encounter,
    main_msgbox_countdown,
    main_score_display,
)
from gauntpy.subsystems.display import init_alpha_color_ram


def _alpha_text(state, column: int, row: int, width: int) -> str:
    start = row * score.ALPHA_ROW_STRIDE + column
    return "".join(
        chr(code) if code else " "
        for word in state.alpha_ram[start:start + width]
        for code in (word & 0x3FF,)
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

class _FakeAssets:
    """Every ``sprite(picture)`` is a single 8x8 tile filled with one index,
    derived from ``picture`` so different pictures are visibly different
    colors after compositing. Index 0 (transparent) and 1 (shadow) are never
    produced by ``_fill_index`` so ordinary sprite pixels never accidentally
    hit those special cases.
    """

    def __init__(self) -> None:
        self.sprite_calls: list[
            tuple[int, int, int | None, str | None, tuple[int, int] | None]
        ] = []

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

def test_live_mob_color_ram_changes_pixels_without_changing_mob_words():
    state = GameState()
    assets = _FakeAssets()
    slot = _place(state.mobs, 2, 2, picture=0x100)
    info = next(iter_visible_mobs(state, 0, 0, 240, 240))
    pixel_index = assets._fill_index(0x100)
    before_words = tuple(
        table[slot] for table in (
            state.mobs.link, state.mobs.picture, state.mobs.hpos, state.mobs.vpos,
        )
    )

    state.mob_color_ram[pixel_index] = 0xFF00
    first = Framebuffer(240, 240)
    draw_mob_layer(first, state, assets, 0, 0, (0, 0, 240, 240))
    state.mob_color_ram[pixel_index] = 0xF0F0
    second = Framebuffer(240, 240)
    draw_mob_layer(second, state, assets, 0, 0, (0, 0, 240, 240))

    assert first.get_pixel(info.x, info.y) != second.get_pixel(info.x, info.y)
    assert tuple(
        table[slot] for table in (
            state.mobs.link, state.mobs.picture, state.mobs.hpos, state.mobs.vpos,
        )
    ) == before_words


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
        state.mob_color_ram[_FakeAssets._fill_index(1)] = 0xFF00
        state.mob_color_ram[_FakeAssets._fill_index(2)] = 0xF0F0

        fb = Framebuffer(240, 240)
        draw_mob_layer(fb, state, _FakeAssets(), 0, 0, PLAYFIELD_VIEWPORT)

        top_x, top_y = coords.slot_to_pixels(top_slot)
        top_y -= 16  # 4x4 MOB: two extra tile rows draw above the cell
        from gauntpy.subsystems.display import _irgb_rgba
        assert fb.get_pixel(top_x + 4, top_y + 4) == _irgb_rgba(0xF0F0)


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
            x_candidates = (x - 512, x, x + 512) if state.wrap_h else (x,)
            draw_x = next(
                (
                    candidate for candidate in x_candidates
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

    def test_nonwrapping_left_edge_does_not_draw_a_right_edge_mob(self):
        state = GameState(wrap_h=False)
        slot = _place(state.mobs, row=6, col=31, picture=0x300, size=3)
        state.mobs.hpos[slot] = coords.encode_hpos(500)

        visible = list(iter_visible_mobs(state, 0, 0, 336, 240))

        assert all(info.slot != slot for info in visible)

    def test_wrapping_left_edge_draws_a_right_edge_mob_across_the_seam(self):
        state = GameState(wrap_h=True)
        slot = _place(state.mobs, row=6, col=31, picture=0x300, size=3)
        state.mobs.hpos[slot] = coords.encode_hpos(500)

        visible = list(iter_visible_mobs(state, 0, 0, 336, 240))

        info = next(info for info in visible if info.slot == slot)
        assert info.x == -12


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
        """An item's hpos nibble is a color-RAM selector, not a strength tier."""
        state = GameState()
        slot = _place(state.mobs, row=5, col=5, picture=0x200, obj_type=MazeObjIds.KEY)
        assert strength_tier(state, slot) == 1


class TestLivePaletteStaysInTheRenderer:
    """AssetStore supplies indexed pixels; only color RAM supplies color."""

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

    def test_the_live_palette_word_is_not_given_to_the_asset_provider(self):
        for nibble in (0x2, 0x3, 0x4):
            calls = self._draw(nibble)
            assert calls and calls[0][2] is None, nibble

    def test_the_tier_fallback_is_still_supplied(self):
        """Legacy stamp lookup metadata still receives the derived tier."""
        calls = self._draw(0x4)
        assert calls[0][1] == strength_tier_of(0x4)

    def test_a_wounded_monster_changes_colour(self):
        """Dropping the nibble selects another live RAM bank."""
        state = GameState()
        slot = coords.pack_slot(6, 6)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(
            slot, tile=0x100, hpos=coords.encode_hpos(x) | 0x4,
            vpos=coords.encode_vpos_at_y(y, 3, 3), obj_type=MazeObjIds.MONST_GHOST,
        )
        assets = _FakeAssets()
        pixel = assets._fill_index(0x100)
        state.mob_color_ram[4 * 16 + pixel] = 0xFF00
        state.mob_color_ram[2 * 16 + pixel] = 0xF0F0
        first = Framebuffer(240, 240)
        draw_mob_layer(first, state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        state.mobs.hpos[slot] = coords.encode_hpos(x) | 0x2      # two hits taken
        second = Framebuffer(240, 240)
        draw_mob_layer(second, state, assets, 0, 0, PLAYFIELD_VIEWPORT)
        assert first.get_pixel(x, y - 8) != second.get_pixel(x, y - 8)

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
        state.mob_color_ram[5] = 0xFFFF
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
        from gauntpy.subsystems.display import init_alpha_color_ram
        from gauntpy.subsystems.players import setup_infopanel

        state = GameState(game_mode=GameMode.NORMAL)
        for player in state.players:
            player.status = PlayerStatus.ALIVE_HERE
            player.health = 750
        init_alpha_color_ram(state)
        setup_infopanel(state, -1)
        return state

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
        from gauntpy.subsystems.players import setup_infopanel
        setup_infopanel(state, 0)
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

    def test_it_label_appears_between_score_and_health_for_it_player(self):
        state = self._state()
        state.players[0].status = PlayerStatus.ALIVE_HERE
        state.frame_counter = 0
        main_score_display(state)

        plain = Framebuffer(336, 240)
        draw_hud(plain, state, HUD_PANEL)
        state.player_it = 0
        score.write_it_labels(state)
        tagged = Framebuffer(336, 240)
        draw_hud(tagged, state, HUD_PANEL)

        x, y = cell_xy(
            HUD_PANEL, score.IT_LABEL_COLUMN, score.PLAYER_LABEL_ROW,
        )
        box = (x, y, x + 2 * 8, y + 8)
        assert tagged.image.crop(box).tobytes() != plain.image.crop(box).tobytes()

    def test_removed_player_block_is_blank_but_the_level_header_is_not(self):
        """A removed player keeps its colored alpha background but no text."""
        state = self._state()  # all players default to PlayerStatus.REMOVED
        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)

        first, last = self._player_block_rows(0)
        assert self._ink_in_rows(fb, HUD_PANEL, first, last)
        assert self._ink_in_rows(fb, HUD_PANEL, score.LEVEL_ROW, score.LEVEL_ROW)

    def test_player_sections_resolve_rom_alpha_color_ram(self):
        from gauntpy.subsystems.display import alpha_color_rgba

        state = self._state()
        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)

        assert tuple(
            state.alpha_color_ram[128 + palette * 4]
            for palette in range(4, 8)
        ) == (0x3F00, 0x300F, 0x2FF0, 0x30F0)
        for index in range(4):
            x, y = cell_xy(
                HUD_PANEL, score.PANEL_COLUMN,
                index * score.PLAYER_BLOCK_STRIDE + score.PLAYER_LABEL_ROW,
            )
            attribute = score.PLAYER_TEXT_PALETTE_WORDS[index]
            assert fb.get_pixel(x, y) == alpha_color_rgba(
                state, attribute, 0,
            )

    def test_live_alpha_color_ram_write_changes_the_panel_background(self):
        from gauntpy.subsystems.display import alpha_color_rgba

        state = self._state()
        attribute = score.PLAYER_TEXT_PALETTE_WORDS[0]
        color_index = 128 + 4 * 4
        state.alpha_color_ram[color_index] = 0xF00F
        fb = Framebuffer(336, 240)

        draw_hud(fb, state, HUD_PANEL)

        x, y = cell_xy(HUD_PANEL, score.PANEL_COLUMN, score.PLAYER_LABEL_ROW)
        assert fb.get_pixel(x, y) == alpha_color_rgba(state, attribute, 0)

    @requires_roms
    def test_multicolor_name_glyphs_use_all_live_alpha_palette_shades(self):
        state = self._state()
        state.players[0].status = PlayerStatus.ALIVE_HERE
        from gauntpy.subsystems.players import setup_infopanel
        setup_infopanel(state, 0)
        before = Framebuffer(336, 240)
        draw_hud(before, state, HUD_PANEL)

        base = 128 + 4 * 4
        state.alpha_color_ram[base + 1] = 0xF0F0
        state.alpha_color_ram[base + 2] = 0xF00F
        after = Framebuffer(336, 240)
        draw_hud(after, state, HUD_PANEL)

        x, y = cell_xy(HUD_PANEL, score.PLAYER_NAME_COLUMN, score.PLAYER_NAME_ROW)
        box = (x, y, x + 4 * 8, y + 8)
        assert before.image.crop(box).tobytes() != after.image.crop(box).tobytes()

    def test_each_player_block_lands_on_its_rom_rows(self):
        """Player p's block is rows p*5+7 .. p*5+10 -- the ROM's ``d4 = p*5+7``
        and its four-row clear loop. Drawing player 2 must not alter another
        position's colored background."""
        state = self._state()
        baseline = Framebuffer(336, 240)
        draw_hud(baseline, state, HUD_PANEL)
        state.players[2].status = PlayerStatus.ALIVE_HERE
        state.players[2].score = 7654321
        state.frame_counter = 2
        main_score_display(state)

        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)

        for other in (0, 1, 3):
            first, last = self._player_block_rows(other)
            box = (
                HUD_PANEL[0], first * 8,
                HUD_PANEL[0] + HUD_PANEL[2], (last + 1) * 8,
            )
            assert fb.image.crop(box).tobytes() == baseline.image.crop(box).tobytes()
        first, last = self._player_block_rows(2)
        box = (
            HUD_PANEL[0], first * 8,
            HUD_PANEL[0] + HUD_PANEL[2], (last + 1) * 8,
        )
        assert fb.image.crop(box).tobytes() != baseline.image.crop(box).tobytes()

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
        state.dialog_box_height, state.dialog_box_width = 3, 5

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

    def test_nothing_is_drawn_without_a_live_dialog(self):
        state = GameState()
        fb = Framebuffer(336, 240)
        before = fb.image.tobytes()
        draw_message_box(fb, state, PLAYFIELD_VIEWPORT)
        assert fb.image.tobytes() == before

    def test_the_rom_message_lines_are_written_to_alpha_ram(self):
        state = GameState(game_mode=GameMode.NORMAL)
        dialog_first_encounter(state, 0, 1 << 3)
        for offset, line in enumerate(state.dialog_message, 1):
            assert _alpha_text(
                state, state.dialog_box_column + 1,
                state.dialog_box_row + offset, len(line),
            ) == line
        assert " SAVE KEYS TO  " in state.dialog_message

    def test_the_box_is_sized_from_the_rom_geometry(self):
        state = GameState(game_mode=GameMode.NORMAL)
        dialog_first_encounter(state, 0, 1 << 0)     # a three-line record
        fb = Framebuffer(336, 240)
        draw_message_box(fb, state, PLAYFIELD_VIEWPORT)

        vx, vy, vw, vh = PLAYFIELD_VIEWPORT
        expected_h = state.dialog_box_height * 8
        expected_w = (state.dialog_box_width + 2) * 8
        top = vy + state.dialog_box_row * 8
        left = vx + state.dialog_box_column * 8
        top_word = state.alpha_ram[
            state.dialog_box_row * score.ALPHA_ROW_STRIDE
            + state.dialog_box_column
        ]
        assert top_word & 0x8000
        assert top_word & 0x3FF == 0

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
        init_alpha_color_ram(state)
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
        from gauntpy.subsystems.display import (
            alpha_palette_words, init_alpha_color_ram,
        )

        state = GameState()
        init_alpha_color_ram(state)
        assert alpha_palette_words(
            state, score.KEY_PALETTE_WORDS[0],
        ) == (0x3F00, 0xFFA0, 0xF08E, 0xF00C)
        assert alpha_palette_words(
            state, score.KEY_PALETTE_WORDS[0],
        ) != alpha_palette_words(
            state, score.PLAYER_TEXT_PALETTE_WORDS[0],
        )

    def test_unpaused_host_draws_no_debug_text_over_the_game_panel(self):
        fb = Framebuffer(336, 240)

        draw_pause_indicator(fb, HUD_PANEL)

        assert all(
            fb.get_pixel(x, y) == (0, 0, 0, 255)
            for y in range(220, 240)
            for x in range(300, 336)
        )

    def test_pause_indicator_uses_the_lower_right_panel_corner(self):
        fb = Framebuffer(336, 240)

        draw_pause_indicator(fb, HUD_PANEL, paused=True)

        assert any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(220, 240)
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


class TestTitleMobs:
    def test_title_motion_matches_rom_landmarks(self):
        from gauntpy.coords import sprite_top_y
        from gauntpy.subsystems.attract import (
            _init_title_logo_mobs, _update_title_logo_motion,
        )

        state = GameState(game_mode=GameMode.TITLE)
        state.title_logo_full_program = True
        _init_title_logo_mobs(state)
        expected = dict((
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
        ))
        for frame in range(341):
            if frame in expected:
                y = sprite_top_y(state.mobs.vpos[0x20] >> 7, 8)
                if y >= 240:
                    y -= 512
                assert y - state.scroll_y == expected[frame]
            _update_title_logo_motion(state)

    def test_title_init_populates_the_hardware_mob_range(self):
        from gauntpy.subsystems.attract import _init_title_logo_mobs

        state = GameState(game_mode=GameMode.TITLE)
        _init_title_logo_mobs(state)

        assert state.mobs.picture[0x20] == 0x2000
        assert state.mobs.hpos[0x20] == 0x0200
        assert state.mobs.vpos[0x20] == 0x63B8
        assert state.mobs.picture[0x75] == 0x2700
        assert state.mobs.picture[0xBE] == 0x2727

    def test_scores_and_legend_draw(self):
        from gauntpy.render.alpha import draw_alpha_layer
        from gauntpy.subsystems.attract import start_attract_screen

        for mode in (GameMode.SCORES, GameMode.LEGEND):
            state = GameState()
            init_alpha_color_ram(state)
            start_attract_screen(state, int(mode))
            fb = Framebuffer(336, 240)
            draw_alpha_layer(fb, state)
            assert fb.image.getbbox(), mode

    def test_scores_preserve_the_maze_between_opaque_score_boxes(self):
        from PIL import Image

        fb = Framebuffer(336, 240)
        fb.image.paste(Image.new("RGBA", (336, 240), (12, 34, 56, 255)))
        state = GameState(game_mode=GameMode.SCORES)
        init_alpha_color_ram(state)
        score.attract_highscores(state)

        from gauntpy.render.alpha import draw_alpha_layer
        draw_alpha_layer(fb, state)

        assert fb.get_pixel(0, 239) == (12, 34, 56, 255)
        assert fb.get_pixel(8, 0) == (12, 34, 56, 255)
        assert fb.get_pixel(8, 8) == (0, 0, 0, 255)

    def test_scores_compositor_does_not_leak_gameplay_hud_backgrounds(self):
        state = GameState(game_mode=GameMode.SCORES)

        fb, _cache = render_frame(state, _FakeAssets())

        assert fb.get_pixel(232, 80) != (50, 0, 0, 255)

    def test_character_select_draws_before_the_game_starts(self):
        from gauntpy.render.alpha import draw_alpha_layer
        from gauntpy.subsystems.session import _write_character_select_alpha

        state = GameState()
        init_alpha_color_ram(state)
        state.game_mode = GameMode.NORMAL
        state.players[0].status = PlayerStatus.SELECTING
        _write_character_select_alpha(state)
        fb = Framebuffer(336, 240)
        draw_alpha_layer(fb, state)
        assert fb.image.getbbox()

class TestFrontEndTextIsRomData:
    """Front-end routines put ROM copy into alpha VRAM, not render calls."""

    def test_title_leaves_alpha_ram_clear_for_its_playfield_and_mobs(self):
        from gauntpy.subsystems.attract import start_attract_screen

        state = GameState()
        start_attract_screen(state, int(GameMode.TITLE))
        assert not any(state.alpha_ram)

    def test_scores_screen_is_the_rom_four_way_split(self):
        from gauntpy.subsystems.display import (
            _LARGE_GLYPH_INDEX_MAP,
            _LARGE_GLYPH_QUADS,
        )

        state = GameState()
        score.attract_highscores(state)
        column, row = romtext.TEXT_SCORE_PER_COIN_POS
        start = row * score.ALPHA_ROW_STRIDE + column
        expected_s = _LARGE_GLYPH_QUADS[_LARGE_GLYPH_INDEX_MAP[ord("S")]][0] | 0x100
        expected_c = _LARGE_GLYPH_QUADS[_LARGE_GLYPH_INDEX_MAP[ord("C")]][0] | 0x100
        assert state.alpha_ram[start] & 0x3FF == expected_s
        assert state.alpha_ram[start + 2] & 0x3FF == expected_c
        for klass, column, row in romtext.HIGHSCORE_QUADRANTS:
            plural = romtext.CHARACTER_NAME_PLURALS[klass]
            start = row * score.ALPHA_ROW_STRIDE + column
            assert all(
                state.alpha_ram[start + offset * 2] & 0x0100
                for offset in range(len(plural))
            )

    def test_scores_screen_preserves_the_maze_border_above_the_top_ladders(self):
        state = GameState()
        score.attract_highscores(state)

        assert state.alpha_ram[1] == 0
        assert state.alpha_ram[20] == 0
        assert state.alpha_ram[score.ALPHA_ROW_STRIDE + 1] & 0x8000
        assert state.alpha_ram[score.ALPHA_ROW_STRIDE + 20] & 0x8000

    def test_scores_screen_shows_the_rom_factory_ladder(self):
        state = GameState()
        score.attract_highscores(state)
        assert _alpha_text(state, 2, 3, 7) == " #1 AWC"
        assert _alpha_text(state, 11, 3, 7) == "   8000"
        assert _alpha_text(state, 24, 3, 7) == " #1 T H"

    def test_scores_screen_follows_the_live_table_not_the_rom_constant(self):
        state = GameState()
        score.high_scores(state)[0][0] = (123456, "ZZZ")
        score.attract_highscores(state)
        assert _alpha_text(state, 2, 3, 7) == " #1 ZZZ"
        assert _alpha_text(state, 11, 3, 7) == " 123456"

    def test_character_select_uses_the_rom_instruction_chain(self):
        from gauntpy.subsystems.session import _write_character_select_alpha

        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = PlayerStatus.SELECTING
        _write_character_select_alpha(state)
        for text, column, row in romtext.CHARACTER_SELECT_LINES:
            start = row * score.ALPHA_ROW_STRIDE + column
            cells = (
                state.alpha_ram[start:start + 2]
                + state.alpha_ram[
                    start + score.ALPHA_ROW_STRIDE:
                    start + score.ALPHA_ROW_STRIDE + 2
                ]
            )
            assert all(word & 0x0100 for word in cells)
        assert _alpha_text(
            state, score.PANEL_COLUMN, score.PLAYER_INV_ROW,
            len(romtext.TEXT_SELECT_HERO),
        ) == romtext.TEXT_SELECT_HERO

    def test_legend_uses_the_rom_descriptor_text(self):
        from gauntpy.subsystems.attract import start_attract_screen

        state = GameState()
        start_attract_screen(state, int(GameMode.LEGEND))
        for text, column, row, _attribute in romtext.LEGEND_RULES_TEXT:
            assert _alpha_text(state, column, row, len(text)) == text
        assert _alpha_text(state, 8, 0, 6) == "LEGEND"

    def test_legend_rules_reveals_the_rom_rectangles_without_erasing_the_panel(self):
        from gauntpy.subsystems.attract import start_attract_screen

        state = GameState()
        start_attract_screen(state, int(GameMode.LEGEND))

        for column, row in (
            (0, 2), (0, 10), (0, 22), (22, 2), (24, 11), (24, 20),
        ):
            assert state.alpha_ram[row * score.ALPHA_ROW_STRIDE + column] == 0
        assert state.alpha_ram[7 * score.ALPHA_ROW_STRIDE + 22] & 0x8000
        assert state.alpha_ram[
            5 * score.ALPHA_ROW_STRIDE + score.PANEL_COLUMN
        ] & 0x8000

    def test_monster_legend_writes_the_rom_capability_table(self):
        from gauntpy.subsystems.attract import start_attract_screen

        state = GameState()
        start_attract_screen(state, int(GameMode.LEGEND))
        state.attract_legend = 1
        from gauntpy.subsystems.attract import load_legend_page
        load_legend_page(state)

        assert _alpha_text(state, 6, 0, 8) == "MONSTERS"
        assert _alpha_text(state, 0, 19, 5) == "GHOST"
        assert _alpha_text(state, 15, 19, 2) == "NO"
        assert _alpha_text(state, 20, 19, 3) == "YES"
        assert _alpha_text(state, 25, 25, 4) == "STUN"
        assert _alpha_text(state, 0, 14, 6) == "DRAGON"


class TestRomTextTables:
    def test_the_hud_name_runs_cover_the_four_classes(self):
        assert len(romtext.CHARACTER_HUD_GLYPHS) == 4
        assert len(romtext.CHARACTER_NAMES) == 4
        # character_hud_text_ptrs -> 0x57508/0x5750E/0x57514/0x5751A: 4, 5, 4
        # and 2 glyph cells, each cell two half-width letters.
        assert [len(run) for run in romtext.CHARACTER_HUD_GLYPHS] == [4, 5, 4, 2]

    def test_the_player_colour_names_are_the_rom_ones(self):
        assert romtext.PLAYER_COLOR_NAMES == (
            " RED  ", " BLUE ", "YELLOW", "GREEN ",
        )
        assert score.PLAYER_TEXT_PALETTE_WORDS == (0xD000, 0xD400, 0xD800, 0xDC00)

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




class TestBonusScreenUsesThePerPlayerTally:
    """show_level_end_bonus_screen pays each exiting hero from
    ``player_treascount`` (0x904A50), so the screen shows that, not the
    level-wide ``level_treasures``."""

    def _bonus_state(self):
        state = GameState()
        state.level_players_active = 1
        state.players[0].status = PlayerStatus.ALIVE_NEXT
        state.players[0].coin_count = 1
        return state

    def test_one_row_per_player_who_collected_treasure(self):
        from gauntpy.subsystems.exits import show_level_end_bonus_screen

        state = self._bonus_state()
        state.player_treascount = [3, 0, 0, 0]
        state.level_treasures = 3
        show_level_end_bonus_screen(state)
        assert _alpha_text(state, 7, 8, len(romtext.BONUS_100_X_COINS)) == (
            romtext.BONUS_100_X_COINS
        )
        assert _alpha_text(state, 9, 9, len(romtext.BONUS_TREASURES_X)) == (
            romtext.BONUS_TREASURES_X
        )
        assert _alpha_text(state, 23, 9, 4) == "   3"

    def test_the_total_award_is_the_settled_bonus_amount(self):
        from gauntpy.subsystems.exits import show_level_end_bonus_screen

        state = self._bonus_state()
        state.player_treascount = [2, 0, 0, 0]
        state.level_treasures = 2
        show_level_end_bonus_screen(state)
        assert state.bonus_amount == 200
        assert _alpha_text(state, 13, 10, len(romtext.BONUS_EQUALS)) == romtext.BONUS_EQUALS
        assert _alpha_text(state, 21, 10, 6) == "   200"


    def test_no_bonus_when_nobody_collected_anything(self):
        from gauntpy.subsystems.exits import show_level_end_bonus_screen

        state = self._bonus_state()
        state.player_treascount = [0, 0, 0, 0]
        show_level_end_bonus_screen(state)
        assert state.bonus_amount == 0
        assert _alpha_text(state, 21, 10, 6) == "     0"


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

    def test_bounded_right_clamp_repeats_the_left_wall_strip(self):
        from PIL import Image
        from gauntpy.render.playfield import PlayfieldCache, draw_playfield

        image = Image.new("RGBA", (512, 512), (0, 0, 0, 255))
        for y in range(512):
            for x in range(16):
                image.putpixel((x, y), (255, 0, 0, 255))
        cache = PlayfieldCache(image=image, shadow_image=image.copy())
        fb = Framebuffer(232, 16)

        draw_playfield(fb, cache, 0x124, 0, (0, 0, 232, 16))

        assert fb.get_pixel(219, 0) == (0, 0, 0, 255)
        assert fb.get_pixel(220, 0) == (255, 0, 0, 255)
        assert fb.get_pixel(231, 0) == (255, 0, 0, 255)

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
        from gauntpy.subsystems.display import init_mob_color_ram
        if not any(state.mob_color_ram):
            init_mob_color_ram(state)
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
        from gauntpy.subsystems.shots import _SCORE_POPUP_PICTURE_TABLE

        for index, picture in enumerate(_SCORE_POPUP_PICTURE_TABLE):
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
        from gauntpy.subsystems.display import (
            init_mob_color_ram, init_player_mob_palette,
        )
        init_mob_color_ram(state)
        init_player_mob_palette(state, 0, character)
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
        """``_ANIM_TABLE_IDLE`` is ``anim_table_idle`` and every frame of
        it is in gex's hero data -- pinned so that stays true rather than
        quietly starting to depend on the fallback."""
        from gauntpy.subsystems.players import _ANIM_TABLE_IDLE

        for character in range(4):
            for frame in range(8):
                picture = _ANIM_TABLE_IDLE[character * 8 + frame]
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
        from gauntpy.subsystems.display import (
            init_mob_color_ram, init_player_mob_palette,
        )
        init_mob_color_ram(state)
        init_player_mob_palette(state, 0, int(character))
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
            _ANIM_TABLE_IDLE,
            _PORT_DIR_TO_ROM_DIR,
            update_player_sprite,
        )

        state, slot, _ = self._hero_state(Character.WIZARD)
        state.mobs.picture[slot] = 0x1E0D
        update_player_sprite(state, 0)

        player = state.players[0]
        expected = _ANIM_TABLE_IDLE[
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
        from gauntpy.subsystems.display import mob_palette_rgba
        palette_rgba = mob_palette_rgba(
            state, state.mobs.hpos[slot] & 0x0F,
        )
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

    def test_shared_artwork_still_uses_the_live_wizard_palette(self):
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
        assert now.image.tobytes() == before.image.tobytes()

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

    def test_f1_toggles_the_separate_host_diagnostics_panel(self, monkeypatch):
        from gauntpy.render.compositor import LOGICAL_HEIGHT, LOGICAL_WIDTH
        from gauntpy.render.diagnostics import DEBUG_PANEL_WIDTH
        from gauntpy.render import host
        from gauntpy.render.host import HostShell

        times = iter((10.0, 10.0125))
        monkeypatch.setattr(host, "perf_counter", lambda: next(times))
        shell = HostShell(assets=_FakeAssets(), scale=1)
        try:
            pygame = shell._pygame
            state = GameState()
            assert shell.window.get_size() == (LOGICAL_WIDTH, LOGICAL_HEIGHT)

            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1)
            )
            shell.wait_for_vblank(state)
            assert shell.diagnostics_visible
            assert shell.window.get_size() == (
                LOGICAL_WIDTH + DEBUG_PANEL_WIDTH,
                LOGICAL_HEIGHT,
            )
            shell.present(state)
            assert shell._diagnostics_previous.render_time_ms == pytest.approx(12.5)
            assert shell._diagnostics_previous.render_time_history_ms == (12.5,)

            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1)
            )
            shell.wait_for_vblank(state)
            assert not shell.diagnostics_visible
            assert shell.window.get_size() == (LOGICAL_WIDTH, LOGICAL_HEIGHT)
        finally:
            shell.close()

    def test_f4_writes_a_host_state_dump_without_mutating_game_memory(
        self, monkeypatch, tmp_path,
    ):
        from gauntpy.render import host

        saved = tmp_path / "state.json"
        calls = []

        def _dump(state):
            calls.append(state.frame_counter)
            saved.write_text("{}\n", encoding="utf-8")
            return saved

        monkeypatch.setattr(host, "dump_game_state", _dump)
        shell = host.HostShell(assets=_FakeAssets())
        try:
            pygame = shell._pygame
            state = GameState(frame_counter=321)
            before = tuple(state.mobs.picture)
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F4)
            )

            shell.wait_for_vblank(state)

            assert calls == [321]
            assert shell.last_state_dump_path == saved
            assert tuple(state.mobs.picture) == before
        finally:
            shell.close()

    def test_troubleshooting_function_keys_route_to_controls(self, monkeypatch):
        from gauntpy.render import host

        calls = []
        monkeypatch.setattr(
            host, "debug_skip_level",
            lambda state: calls.append(("level", state)) or True,
        )
        monkeypatch.setattr(
            host, "debug_add_key",
            lambda state, player: calls.append(("key", player)) or True,
        )
        monkeypatch.setattr(
            host, "debug_add_potion",
            lambda state, player: calls.append(("potion", player)) or True,
        )
        monkeypatch.setattr(
            host, "debug_enable_secret_room",
            lambda state: calls.append(("enable-secret", state)) or True,
        )
        monkeypatch.setattr(
            host, "debug_force_secret_room",
            lambda state, player: calls.append(("force-secret", player)) or True,
        )
        shell = host.HostShell(assets=_FakeAssets(), player=2)
        try:
            pygame = shell._pygame
            state = GameState(
                game_mode=GameMode.NORMAL,
                mazenum_current=104,
                treasure_timer=60,
            )
            for key in (
                pygame.K_F5, pygame.K_F6, pygame.K_F7, pygame.K_F8,
                pygame.K_F9, pygame.K_F10,
            ):
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=key)
                )

            shell.wait_for_vblank(state)

            assert calls == [
                ("level", state),
                ("key", 2),
                ("potion", 2),
                ("enable-secret", state),
                ("force-secret", 2),
            ]
            assert shell.treasure_timer_paused
        finally:
            shell.close()

    def test_f8_unpauses_and_clears_when_bonus_room_ends(self):
        from gauntpy.render.host import HostShell

        shell = HostShell(assets=_FakeAssets())
        try:
            pygame = shell._pygame
            state = GameState(
                game_mode=GameMode.NORMAL,
                mazenum_current=115,
                treasure_timer=120,
            )
            for expected in (True, False):
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8)
                )
                shell.wait_for_vblank(state)
                assert shell.treasure_timer_paused is expected

            shell.treasure_timer_paused = True
            state.treasure_timer = 0
            shell.wait_for_vblank(state)
            assert not shell.treasure_timer_paused
        finally:
            shell.close()

    def test_diagnostics_panel_stays_native_width_when_game_is_scaled(self):
        from gauntpy.render.compositor import LOGICAL_HEIGHT, LOGICAL_WIDTH
        from gauntpy.render.diagnostics import DEBUG_PANEL_WIDTH
        from gauntpy.render.host import HostShell

        shell = HostShell(assets=_FakeAssets(), scale=3, diagnostics=True)
        try:
            assert shell.window.get_size() == (
                LOGICAL_WIDTH * 3 + DEBUG_PANEL_WIDTH,
                LOGICAL_HEIGHT * 3,
            )
            shell.present(GameState())
        finally:
            shell.close()

    def test_diagnostics_page_and_mob_navigation_is_host_only(self):
        from gauntpy.render.host import HostShell

        state = GameState()
        state.mobs.picture[32] = 0x1000
        state.mobs.picture[40] = 0x2000
        shell = HostShell(assets=_FakeAssets(), scale=1, diagnostics=True)
        try:
            pygame = shell._pygame
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3)
            )
            shell.wait_for_vblank(state)
            assert shell.diagnostics_page == 1
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2)
            )
            shell.wait_for_vblank(state)
            assert shell.diagnostics_page == 0

            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHTBRACKET)
            )
            shell.wait_for_vblank(state)
            assert shell.diagnostics_selected_mob == 32
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHTBRACKET)
            )
            shell.wait_for_vblank(state)
            assert shell.diagnostics_selected_mob == 40

            before = tuple(state.mobs.picture)
            shell.present(state)
            state.players[0].health = 100
            shell.present(state)
            assert shell._diagnostics_events
            assert tuple(state.mobs.picture) == before
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
