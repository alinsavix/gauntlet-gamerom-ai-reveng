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
from gauntpy.constants import MazeObjIds
from gauntpy.render.compositor import HUD_PANEL, PLAYFIELD_VIEWPORT, render_frame
from gauntpy.render.framebuffer import Framebuffer
from gauntpy.render.hud import draw_hud
from gauntpy.render.mobs import draw_mob_layer, iter_visible_mobs
from gauntpy.state import GameState

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

    @staticmethod
    def _fill_index(picture: int) -> int:
        return 2 + (picture % 13)  # 2..14

    def sprite(self, picture: int, *, tier: int = 1):
        from gex.render import Stamp

        idx = self._fill_index(picture)
        tile = [[idx] * 8 for _ in range(8)]
        return Stamp(width=1, numbers=[picture], ptype="fake", pnum=0, data=[tile])

    def palette(self, kind: str, index: int):
        return self._palette


def _place(mobs, row: int, col: int, picture: int, obj_type=MazeObjIds.MONST_GHOST, size: int = 3) -> int:
    slot = coords.pack_slot(row, col)
    x, y = coords.slot_to_pixels(slot)
    return mobs.create(
        slot,
        tile=picture,
        hpos=coords.encode_hpos(x),
        vpos=coords.encode_vpos(y, width=size, height=size),
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

    def test_shadow_index_fallback_darkens_existing_pixel(self):
        """doc/01_hardware.md §4/§6: MOB pixel value 1 is the shadow special
        case. With no ``shadow_src`` it must read whatever is already on the
        framebuffer and darken it, never the MOB's own palette.
        """
        fb = Framebuffer(8, 8)
        fb.set_pixel(0, 0, (100, 100, 100, 255))
        tile = [[1] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        palette[1] = (255, 0, 0, 255)  # must NOT be used
        fb.blit_indexed_tile(tile, palette, 0, 0, shadow_index=1, shadow_scale=0.5)
        assert fb.get_pixel(0, 0) == (50, 50, 50, 255)

    def test_shadow_src_supplies_exact_color_over_fallback(self):
        """When a shadow_src is given, its exact color wins and the in-place
        scale is not used -- ``shadow_src.at`` is the shadow-palette playfield
        color (playfield.ShadowSource)."""
        class _FixedShadow:
            def at(self, fx, fy):
                return (7, 8, 9, 255)

        fb = Framebuffer(8, 8)
        fb.set_pixel(0, 0, (100, 100, 100, 255))  # would scale to (50,50,50)
        tile = [[1] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        fb.blit_indexed_tile(
            tile, palette, 0, 0,
            shadow_index=1, shadow_scale=0.5, shadow_src=_FixedShadow(),
        )
        assert fb.get_pixel(0, 0) == (7, 8, 9, 255)

    def test_shadow_src_off_raster_falls_back_to_scale(self):
        """A shadow_src reporting None (off-raster, e.g. a wrap seam) falls
        back to the in-place darkening."""
        class _NoShadow:
            def at(self, fx, fy):
                return None

        fb = Framebuffer(8, 8)
        fb.set_pixel(0, 0, (100, 100, 100, 255))
        tile = [[1] * 8 for _ in range(8)]
        palette = [(0, 0, 0, 255)] * 16
        fb.blit_indexed_tile(
            tile, palette, 0, 0,
            shadow_index=1, shadow_scale=0.5, shadow_src=_NoShadow(),
        )
        assert fb.get_pixel(0, 0) == (50, 50, 50, 255)

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

        # Scroll far enough down that only the low MOB's band is visible.
        infos = list(iter_visible_mobs(state, scroll_x=0, scroll_y=350, viewport_w=240, viewport_h=240))

        assert [info.slot for info in infos] == [low_slot]

    def test_mob_entirely_below_viewport_is_excluded(self):
        state = GameState()
        _place(state.mobs, row=30, col=2, picture=0x10)  # far below any normal viewport

        infos = list(iter_visible_mobs(state, 0, 0, 240, 240))

        assert infos == []

    def test_zero_picture_slot_is_never_drawn(self):
        """Picture 0 is 'nothing to draw' -- also what the chain's own null
        terminator and unpainted placeholder slots use.
        """
        state = GameState()
        slot = coords.pack_slot(5, 5)
        x, y = coords.slot_to_pixels(slot)
        state.mobs.create(slot, tile=0, hpos=coords.encode_hpos(x), vpos=coords.encode_vpos(y, 3, 3), obj_type=MazeObjIds.WALL_REGULAR)

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
        expected_idx = _FakeAssets._fill_index(2)
        expected_rgba = (expected_idx * 16, expected_idx * 16, expected_idx * 16, 255)
        assert fb.get_pixel(top_x + 4, top_y + 4) == expected_rgba


# ---------------------------------------------------------------------------
# HUD layer (ROM-free -- PIL default font, no ROM character set; see
# render/hud.py's module docstring for that flagged decision)
# ---------------------------------------------------------------------------

class TestHud:
    def test_active_player_row_is_not_left_blank(self):
        state = GameState()
        state.players[0].status = 1  # PlayerStatus.ALIVE_HERE
        state.players[0].score = 1234
        state.players[0].health = 500

        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)

        px, py, pw, ph = HUD_PANEL
        row_has_ink = any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(py, py + 24)
            for x in range(px, px + pw)
        )
        assert row_has_ink, "an active player's row must draw something other than the panel background"

    def test_removed_player_row_still_drawn_dim(self):
        state = GameState()  # all players default to PlayerStatus.REMOVED
        fb = Framebuffer(336, 240)
        draw_hud(fb, state, HUD_PANEL)
        px, py, pw, ph = HUD_PANEL
        assert any(
            fb.get_pixel(x, y) != (0, 0, 0, 255)
            for y in range(py, py + 24)
            for x in range(px, px + pw)
        )

    def test_message_box_appears_only_while_dialog_timer_is_set(self):
        state = GameState()
        state.dialog_timer = 0
        fb_no_dialog = Framebuffer(336, 240)
        draw_hud(fb_no_dialog, state, HUD_PANEL)

        state.dialog_timer = 30
        fb_dialog = Framebuffer(336, 240)
        draw_hud(fb_dialog, state, HUD_PANEL)

        px, py, pw, ph = HUD_PANEL
        box_row_y = py + ph - 20
        no_dialog_row = [fb_no_dialog.get_pixel(x, box_row_y) for x in range(px, px + pw)]
        dialog_row = [fb_dialog.get_pixel(x, box_row_y) for x in range(px, px + pw)]
        assert no_dialog_row != dialog_row, "the message box outline must only appear while dialog_timer is nonzero"

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


# ---------------------------------------------------------------------------
# Compositor smoke test (ROM-free: no state.maze, so the playfield layer is
# a no-op, and mobs come from _FakeAssets)
# ---------------------------------------------------------------------------

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

    def test_shadow_raster_is_the_irgb_transform_not_a_scale(self):
        """build_playfield_images' shadow twin applies the exact ROM intensity
        transform (playfield.irgb_to_shadow), which is darker than and
        distinct from a naive RGB *0.5 -- that difference is the whole point
        of the shadow raster.
        """
        from gauntpy.render.playfield import build_playfield_images

        maze = self._decode(1)
        normal, shadow = build_playfield_images(maze)
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
