"""Tests for the ROM/asset bridge (WP-1).

Two skip conditions, mirroring the pattern gex's own test suite uses
(``python-gex/tests/test_golden_images.py``, ``test_integration_roms.py``):
ROMs must be present (checked the same way gex checks it -- resolved
``GEX_ROM_DIR``/``./ROMs`` directory containing the first tile ROM file) and,
for the golden-image comparisons, gex's reference-image corpus must exist.
Every test in this module skips cleanly rather than erroring when either is
missing -- there is exactly one exception, ``TestMissingRoms``, which tests
the *failure* path itself and therefore must not depend on ROMs being
present.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gauntpy.assets import (
    EFFECT_PICTURES,
    HERO_NAMES,
    MAX_BLOCK_TILES,
    PICTURE_TILE_MASK,
    TPORT_TRANSITION_PICTURES,
    AssetError,
    AssetStore,
    SpriteFrame,
    TileBlock,
    _projectile_palette_bank,
    _title_logo_palette_words,
)

# ---------------------------------------------------------------------------
# Paths & skip conditions (same approach as python-gex/tests/test_golden_images.py)
# ---------------------------------------------------------------------------

from gex.roms import _rom_dir, TILE_ROMS  # noqa: E402  (after skip-condition imports, matches gex's own tests)

_ROM_PATH = _rom_dir()
_ROMS_EXIST = _ROM_PATH.is_dir() and (_ROM_PATH / TILE_ROMS[0][0]).is_file()

_REF_DIR = Path(__file__).resolve().parents[2] / "python-gex" / "tests" / "reference_images"
_MANIFEST_PATH = _REF_DIR / "manifest.json"
_REFS_EXIST = _MANIFEST_PATH.is_file()

# Applied per-class (not as a module-level ``pytestmark``) because
# TestMissingRoms below tests the no-ROMs failure path itself and must run
# regardless of whether this environment happens to have ROMs configured.
requires_roms_and_refs = pytest.mark.skipif(
    not (_ROMS_EXIST and _REFS_EXIST),
    reason=f"ROM files ({_ROM_PATH}) or gex reference images ({_REF_DIR}) not available",
)

requires_roms = pytest.mark.skipif(
    not _ROMS_EXIST, reason=f"ROM files not available at {_ROM_PATH}"
)


@pytest.mark.parametrize(("kind", "palette", "expected"), (
    (None, 1, ("base", 1)),
    ("warrior", 0x0C, ("warrior", 0)),
    ("elf", 0x0D, ("elf", 1)),
    ("wizard", 0x0E, ("wizard", 2)),
))
def test_projectile_palette_mapping_does_not_require_rom_pixels(
    kind, palette, expected,
):
    assert _projectile_palette_bank(kind, palette) == expected


def test_title_logo_palette_shift_moves_the_rom_color_chain():
    from gex.palettes import GAUNTLET_PALETTES

    initial = _title_logo_palette_words(0)
    shifted = _title_logo_palette_words(1)
    assert initial[0][2] == GAUNTLET_PALETTES["base"][0][2].irgb
    assert shifted[0][2] == initial[0][3]
    assert shifted[0][9] == initial[1][2]
    assert _title_logo_palette_words(3)[9][9] == 0x1077


@pytest.fixture(scope="module")
def manifest() -> dict:
    with open(_MANIFEST_PATH) as f:
        return json.load(f)


def _pixel_sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _render_stamp(store: AssetStore, stamp) -> "object":
    """Render an AssetStore-built Stamp to a PIL image the same way gex's
    own golden tests do (``gex.render.blank_image`` / ``write_stamp_to_image``).
    This is test-support tooling for generic stamps.
    """
    from gex.render import blank_image, write_stamp_to_image

    height = len(stamp.data) // stamp.width
    img = blank_image(stamp.width * 8, height * 8)
    write_stamp_to_image(img, stamp, 0, 0)
    return img


def _assert_matches_reference(name: str, img, manifest: dict) -> None:
    ref_path = _REF_DIR / f"{name}.png"
    assert ref_path.is_file(), f"reference image missing: {ref_path}"
    entry = manifest[name]
    assert list(img.size) == entry["size"], (
        f"{name}: size mismatch: got {list(img.size)}, expected {entry['size']}"
    )
    rendered_sha = _pixel_sha256_bytes(img.tobytes())
    assert rendered_sha == entry["pixel_sha256"], (
        f"{name}: pixel data mismatch (rendered {rendered_sha} != reference "
        f"{entry['pixel_sha256']})"
    )


def _lit_pixels(stamp) -> int:
    """How many of a stamp's pixels are not palette index 0.

    Index 0 is the transparent one (``gex.render.write_tile_to_image``'s
    ``trans0``, and ``render.framebuffer.blit_indexed_tile``'s), so this is
    "how much of this sprite is actually visible" -- the measure a dissolve or
    a sparkle animates.
    """
    return sum(1 for tile in stamp.data for row in tile for px in row if px != 0)


# ---------------------------------------------------------------------------
# tile() round-trips a known tile against gex's reference image, byte-for-byte
# ---------------------------------------------------------------------------

@requires_roms_and_refs
class TestTileRoundTrip:
    @pytest.mark.parametrize("tilenum", [0x11, 0x100, 0x1C1])
    def test_single_tile_matches_gex_reference(self, tilenum, manifest):
        store = AssetStore()
        pixels = store.tile(tilenum)
        assert len(pixels) == 8
        assert all(len(row) == 8 for row in pixels)

        # tile() returns raw palette-index data; build a 1x1 stamp (via the
        # same AssetStore) to get something paletted/renderable, and compare
        # against gex's own "tile_0x0011"-style golden image.
        stamp = store.stamp([tilenum], 1, "base", 0)
        img = _render_stamp(store, stamp)
        _assert_matches_reference(f"tile_{tilenum:#06x}", img, manifest)

    def test_tile_decode_is_cached(self):
        store = AssetStore()
        a = store.tile(0x100)
        b = store.tile(0x100)
        assert a is b, "decoding the same tile twice must reuse the cached pixels"


@requires_roms
class TestTitleLogo:
    def test_native_logo_is_rom_decoded_and_mutation_isolated(self):
        store = AssetStore()
        first = store.title_logo()
        second = store.title_logo()
        assert first is not second
        assert first.size == (328, 48)
        assert hashlib.sha256(first.tobytes()).hexdigest() == (
            "ffa64aab833688660ee15dcc8c8277cea5708c23355e688466ddf2c771e1e733"
        )
        first.putpixel((0, 0), (255, 0, 255, 255))
        assert second.getpixel((0, 0)) != (255, 0, 255, 255)

    def test_live_title_palette_changes_the_rendered_wordmark(self):
        store = AssetStore()
        assert (
            store.title_logo_for_frame(1).tobytes()
            != store.title_logo_for_frame(24).tobytes()
        )


# ---------------------------------------------------------------------------
# stamp() multi-tile sprites, and its own caching
# ---------------------------------------------------------------------------

@requires_roms_and_refs
class TestStamp:
    def test_stamp_is_cached_by_arguments(self):
        store = AssetStore()
        s1 = store.stamp([0x100, 0x101, 0x102, 0x103], 2, "base", 0)
        s2 = store.stamp([0x100, 0x101, 0x102, 0x103], 2, "base", 0)
        assert s1 is s2, "identical stamp() calls must return the cached Stamp"

    def test_stamp_trans0_not_shared_with_opaque_variant(self):
        store = AssetStore()
        opaque = store.stamp([0x100], 1, "base", 0, trans0=False)
        transparent = store.stamp([0x100], 1, "base", 0, trans0=True)
        assert opaque is not transparent
        assert opaque.trans0 is False
        assert transparent.trans0 is True


# ---------------------------------------------------------------------------
# palette()
# ---------------------------------------------------------------------------

@requires_roms_and_refs
class TestPalette:
    def test_known_kind_and_index(self):
        from gex.palettes import BASE_PALETTES

        store = AssetStore()
        assert store.palette("base", 0) is BASE_PALETTES[0]

    def test_unknown_kind_raises_asset_error(self):
        store = AssetStore()
        with pytest.raises(AssetError, match="Unknown palette kind"):
            store.palette("not-a-real-kind", 0)

    def test_index_out_of_range_raises_asset_error(self):
        store = AssetStore()
        with pytest.raises(AssetError, match="out of range"):
            store.palette("base", 9999)


# ---------------------------------------------------------------------------
# Sprite lookup by MOB picture number
# ---------------------------------------------------------------------------

@requires_roms_and_refs
class TestSpriteByPictureNumber:
    def test_ghost_walk_up_frame0_matches_gex_reference(self, manifest):
        """mob_picture 2192 is the base tile of the Ghost walk-up, frame 0
        stamp per doc/05_data_reference.md §7.4 (also gex.monsters.MONSTERS
        ["ghost"].anims["walk"]["up"][0]). AssetStore.sprite() must resolve
        it to the same pixels gex's own name-based domonster("ghost-walk-up")
        produces.
        """
        store = AssetStore()
        frame = store.sprite_frame(2192)
        assert frame == SpriteFrame("ghost", "walk", "up", 0)

        stamp = store.sprite(2192)
        img = _render_stamp(store, stamp)
        _assert_matches_reference("ghost_walk_up", img, manifest)

    def test_software_flag_bit_is_masked_off(self):
        """Bit 15 of mob_picture is a software flag, not part of the tile
        number (gauntpy/src/gauntpy/mob.py docstring) -- a picture value
        with that bit set must resolve to the same sprite.
        """
        store = AssetStore()
        assert store.sprite_frame(2192) == store.sprite_frame(2192 | 0x8000)
        assert PICTURE_TILE_MASK == 0x7FFF

    def test_all_four_ghost_directions_resolve(self, manifest):
        directions = {
            "up": 2192, "upright": 2156, "right": 2120, "downright": 2084,
            "down": 2048, "downleft": 2304, "left": 2264, "upleft": 2228,
        }
        store = AssetStore()
        for direction, picture in directions.items():
            frame = store.sprite_frame(picture)
            assert frame.monster_type == "ghost"
            assert frame.direction == direction
            assert frame.frame_index == 0

    def test_unknown_picture_number_raises_clear_error(self):
        store = AssetStore()
        with pytest.raises(AssetError, match="No known sprite"):
            store.sprite_frame(0x0001)  # not any monster's animation tile

    def test_tier_selects_palette_like_gex_domonster(self):
        """gex's own CLI computes pal_num = mon.pnum + (monster_level + 1)
        for a name like "ghost2-walk-up" (python-gex/src/gex/monsters.py
        domonster()). AssetStore.sprite(tier=2) must match that exactly for
        the equivalent picture number.
        """
        store = AssetStore()
        default_stamp = store.sprite(2192)          # tier=1 default
        tier2_stamp = store.sprite(2192, tier=2)
        assert default_stamp.pnum == 0 + (1 + 1)
        assert tier2_stamp.pnum == 0 + (2 + 1)

    def test_palette_argument_overrides_the_tier_guess(self):
        """``mob_hpos`` bits 3-0 *are* the MOB palette number (doc/08), placed
        from ``mazeobj_hsize_tier_tbl`` and decremented as a monster is
        wounded. A caller holding the live word should not have to reverse it
        into a tier first."""
        store = AssetStore()
        assert store.sprite(2192, palette=3).pnum == 3
        assert store.sprite(2192, palette=2, tier=7).pnum == 2, "palette wins"
        assert store.sprite(2192, palette=0x14).pnum == 4, "masked to a nibble"


@requires_roms_and_refs
class TestSpriteDispatch:
    """``sprite()`` routes a picture word across four families; every one of
    them must resolve rather than fall through to the error path.
    """

    def test_a_projectile_picture_builds_a_2x2_base_stamp(self):
        from gex.projectiles import PROJECTILE_TILES

        store = AssetStore()
        tile = min(PROJECTILE_TILES)
        stamp = store.sprite(tile)
        assert stamp.width == 2
        assert len(stamp.numbers) == 4
        assert stamp.ptype == "base"

    def test_projectile_uses_its_live_base_palette_nibble(self):
        from gex.projectiles import PROJECTILE_TILES

        stamp = AssetStore().sprite(min(PROJECTILE_TILES), palette=1)

        assert (stamp.ptype, stamp.pnum) == ("base", 1)

    @pytest.mark.parametrize(("kind", "palette", "expected"), (
        ("warrior", 0x0C, ("warrior", 0)),
        ("elf", 0x0D, ("elf", 1)),
        ("wizard", 0x0E, ("wizard", 2)),
    ))
    def test_projectile_player_banks_follow_palette_12_to_15(
        self, kind, palette, expected,
    ):
        from gex.projectiles import PROJECTILE_TILES

        stamp = AssetStore().sprite(
            min(PROJECTILE_TILES), kind=kind, palette=palette,
        )

        assert (stamp.ptype, stamp.pnum) == expected

    def test_a_dragon_segment_picture_builds_a_4x4_base_stamp(self):
        from gex.dragon import DRAGON_SEGMENT_TILES

        store = AssetStore()
        stamp = store.sprite(min(DRAGON_SEGMENT_TILES))
        assert stamp.width == 4
        assert len(stamp.numbers) == 16

    def test_projectile_and_dragon_stamps_are_cached_like_every_other(self):
        """They used to be rebuilt (and re-decoded) on every call, which for a
        shot means once per frame per shot."""
        from gex.projectiles import PROJECTILE_TILES

        store = AssetStore()
        tile = min(PROJECTILE_TILES)
        assert store.sprite(tile) is store.sprite(tile)

    def test_a_placed_pickup_picture_resolves_to_its_item_stamp(self):
        from gex.objparams import base_picture

        store = AssetStore()
        key_picture = base_picture(53)      # MazeObjIds.KEY
        assert store.sprite(key_picture) is not None

    def test_the_software_flag_never_changes_the_dispatch(self):
        from gex.projectiles import PROJECTILE_TILES

        store = AssetStore()
        tile = min(PROJECTILE_TILES)
        assert store.sprite(tile) is store.sprite(tile | 0x8000)

    def test_an_unknown_picture_raises_instead_of_returning_none(self):
        """The fall-through used to end in a bare call whose exception was the
        only thing standing between a caller and a silent ``None``."""
        store = AssetStore()
        with pytest.raises(AssetError):
            store.sprite(0x0001)

    @pytest.mark.parametrize("marker", [0x8000, 0x8001, 0x8003])
    def test_marker_words_report_that_they_have_no_sprite(self, marker):
        """Walls and floor tiles carry marker pictures and are drawn by the
        playfield layer; asking for a sprite is a caller bug worth naming.
        0x8000 in particular masks to tile 0, which gex's item table holds as
        its "blank" entry -- so without the guard this returned blank pixels.
        """
        store = AssetStore()
        with pytest.raises(AssetError, match="Marker words"):
            store.sprite(marker)
        with pytest.raises(AssetError, match="Marker words"):
            store.sprite_frame(marker)


# ---------------------------------------------------------------------------
# Effects: the transient MOBs the game spawns for score popups, floating score
# stars, shot impacts and transporter sparkles.
#
# gex has carried these picture tables all along (``gex.effects``), but
# ``sprite()`` never consulted them, so every one of them fell through to the
# error path and the MOB layer silently dropped it. They are the most
# frequently spawned MOBs in a live frame after shots.
# ---------------------------------------------------------------------------

from gex.effects import EFFECT_TABLES, STAR_TILES, star_stamp  # noqa: E402


def _effect_pictures() -> list[int]:
    """Every distinct masked picture word in gex's effect tables."""
    return sorted(
        {word & PICTURE_TILE_MASK for words in EFFECT_TABLES.values() for word in words}
    )


class TestEffectPictureIndex:
    """ROM-free: the index itself, built from gex's bundled jsonc at import."""

    def test_every_word_gex_carries_has_a_block(self):
        for name, words in EFFECT_TABLES.items():
            for word in words:
                masked = word & PICTURE_TILE_MASK
                assert masked in EFFECT_PICTURES, (name, hex(word))

    def test_there_are_exactly_twenty_eight_distinct_effect_pictures(self):
        """15 score popups + 7 stars + 3 + 3 fx frames. Pinned so a change in
        gex's tables is reported here rather than as art that quietly stopped
        being drawn."""
        assert len(_effect_pictures()) == 28

    def test_the_index_also_covers_the_transporter_transition_cycle(self):
        """The one effect family gex has no metadata for at all -- six real
        3x3 ROM blocks from the table at 0x578F2."""
        for picture in TPORT_TRANSITION_PICTURES:
            assert EFFECT_PICTURES[picture] == TileBlock(3, 3, "base", 1)
        assert min(TPORT_TRANSITION_PICTURES) == 0x1DCF
        assert max(TPORT_TRANSITION_PICTURES) == 0x1E00

    def test_the_transition_cycle_matches_the_subsystem_transcription(self):
        """``subsystems/score.py`` transcribes the same ROM table (as the full
        symmetric twelve-word cycle) and ``players.handle_tport`` installs its
        first frame. Two transcriptions of one table must not drift."""
        from gauntpy.subsystems.players import _TPORT_ARRIVAL_PICTURE
        from gauntpy.subsystems.score import _TPORT_TRANSITION_PICTURES

        assert set(TPORT_TRANSITION_PICTURES) == set(_TPORT_TRANSITION_PICTURES)
        assert len(_TPORT_TRANSITION_PICTURES) == 12, "the ROM cycle is symmetric"
        assert _TPORT_ARRIVAL_PICTURE in TPORT_TRANSITION_PICTURES

    def test_star_blocks_are_gexs_own_3x3_geometry(self):
        from gex.effects import STAR_PNUM, STAR_PTYPE, STAR_XSIZE, STAR_YSIZE

        assert STAR_TILES
        for tile in STAR_TILES:
            assert EFFECT_PICTURES[tile] == TileBlock(
                STAR_XSIZE, STAR_YSIZE, STAR_PTYPE, STAR_PNUM
            )

    def test_popup_widths_match_the_two_halves_of_the_rom_table(self):
        """``playfield_showscore`` branches on ``popup < 0x0A``: three tiles
        wide in palette 5 for the score-value popups, two wide in palette 1 for
        the bonus ones -- which is also the stride of each half of the table.
        """
        popups = EFFECT_TABLES["score_popup"]
        for index, word in enumerate(popups):
            block = EFFECT_PICTURES[word & PICTURE_TILE_MASK]
            expected = TileBlock(3, 1, "base", 5) if index < 0x0A else TileBlock(2, 1, "base", 1)
            assert block == expected, (index, hex(word))
        assert popups[2] - popups[1] == 3, "the value half strides three tiles"
        assert popups[11] - popups[10] == 2, "the bonus half strides two"

    def test_the_popup_table_matches_the_shot_subsystems_transcription(self):
        from gauntpy.subsystems.shots import _SCORE_POPUP_PICTURE

        assert tuple(EFFECT_TABLES["score_popup"]) == _SCORE_POPUP_PICTURE

    def test_the_fx_tables_match_the_score_subsystems_transcription(self):
        """``score._advance_effect`` steps these same cycles; they are the two
        impact bursts (player-fired and monster-fired) and are 2x2."""
        from gauntpy.subsystems.score import (
            _MONSTER_IMPACT_PICTURES,
            _PLAYER_IMPACT_PICTURES,
            _TPORT_EFFECT_PICTURES,
        )

        assert tuple(EFFECT_TABLES["score_fx_a"]) == _PLAYER_IMPACT_PICTURES
        assert tuple(EFFECT_TABLES["score_fx_b"]) == _MONSTER_IMPACT_PICTURES
        assert tuple(EFFECT_TABLES["score_star"]) == _TPORT_EFFECT_PICTURES
        for word in _PLAYER_IMPACT_PICTURES + _MONSTER_IMPACT_PICTURES:
            assert EFFECT_PICTURES[word] == TileBlock(2, 2, "base", 1)


@requires_roms
class TestEveryEffectPictureRenders:
    """The finding itself, exhaustively: all 28 effect pictures gex knows
    about, plus the six transporter transition frames it does not.
    """

    @pytest.mark.parametrize("picture", _effect_pictures())
    def test_a_gex_effect_picture_builds_its_rom_block(self, picture):
        store = AssetStore()
        block = EFFECT_PICTURES[picture]
        stamp = store.sprite(picture)

        assert stamp.width == block.xsize
        assert len(stamp.numbers) == block.xsize * block.ysize
        assert list(stamp.numbers) == list(
            range(picture, picture + block.xsize * block.ysize)
        ), "the hardware stamps consecutive tiles from the picture word"
        assert (stamp.ptype, stamp.pnum) == (block.ptype, block.pnum)
        img = _render_stamp(store, stamp)
        assert img.size == (block.xsize * 8, block.ysize * 8)
        assert _lit_pixels(stamp) > 0, "an effect frame that is entirely blank"

    def test_all_twenty_eight_resolve_and_none_raise(self):
        store = AssetStore()
        assert len(_effect_pictures()) == 28
        assert all(store.sprite(p) is not None for p in _effect_pictures())

    def test_a_star_is_exactly_gexs_own_star_stamp(self):
        """gex already builds these (``gex.effects.star_stamp``); the bridge
        must not invent a different answer, only a cached one."""
        store = AssetStore()
        for tile in sorted(STAR_TILES):
            ours = store.sprite(tile)
            theirs = star_stamp(tile)
            assert (ours.width, ours.ptype, ours.pnum) == (
                theirs.width, theirs.ptype, theirs.pnum,
            )
            assert list(ours.numbers) == list(theirs.numbers)
            assert ours.data == theirs.data

    def test_the_software_flag_never_changes_the_effect_dispatch(self):
        store = AssetStore()
        for picture in _effect_pictures():
            assert store.sprite(picture) is store.sprite(picture | 0x8000)

    def test_effect_stamps_are_cached_like_every_other(self):
        """A popup or an impact burst is rebuilt every frame it is alive."""
        store = AssetStore()
        picture = _effect_pictures()[0]
        assert store.sprite(picture) is store.sprite(picture)

    def test_the_live_palette_nibble_still_picks_the_entry(self):
        """The game places an effect MOB with a palette nibble of its own
        (``shots._place_effect``'s ``hpos + 1``); the MOB layer passes the live
        word and it must win over the table's default, exactly as for a
        creature."""
        store = AssetStore()
        picture = sorted(STAR_TILES)[0]
        assert store.sprite(picture).pnum == 0, "gex's own star default"
        assert store.sprite(picture, palette=1).pnum == 1
        assert store.sprite(picture, palette=0x1B).pnum == 0xB, "masked to a nibble"


@requires_roms
class TestTransporterTransitionFrames:
    """0x1DCF..0x1E00 -- ROM 0x578F2's sparkle. Real 3x3 tile blocks that no
    gex table lists, driven by ``score._advance_player_transition`` /
    ``_advance_thief_transition`` on the five transporter animation slots.
    """

    def test_every_frame_is_a_3x3_block_of_consecutive_tiles(self):
        store = AssetStore()
        for picture in TPORT_TRANSITION_PICTURES:
            stamp = store.sprite(picture)
            assert stamp.width == 3
            assert len(stamp.numbers) == 9
            assert list(stamp.numbers) == list(range(picture, picture + 9))
            assert (stamp.ptype, stamp.pnum) == ("base", 1)
            assert _render_stamp(store, stamp).size == (24, 24)

    def test_the_sparkle_grows_and_then_fades(self):
        """The cycle is an expanding then collapsing burst: the ROM's twelve
        word table runs these six frames forward and then back. Lit-pixel
        counts must therefore rise to a peak and fall away -- if a frame
        decoded from the wrong base tile this shape would not hold.
        """
        store = AssetStore()
        lit = [_lit_pixels(store.sprite(p)) for p in TPORT_TRANSITION_PICTURES]
        assert all(count > 0 for count in lit), lit
        peak = lit.index(max(lit))
        assert 0 < peak < len(lit) - 1, lit
        assert lit[:peak + 1] == sorted(lit[:peak + 1]), lit
        assert lit[peak:] == sorted(lit[peak:], reverse=True), lit
        assert lit[0] < lit[peak] / 2, "the first frame is a faint spark"

    def test_both_range_endpoints_render(self):
        store = AssetStore()
        for picture in (0x1DCF, 0x1E00):
            assert len(store.sprite(picture).numbers) == 9

    def test_the_frames_are_all_different_artwork(self):
        store = AssetStore()
        rendered = {
            _render_stamp(store, store.sprite(p)).tobytes()
            for p in TPORT_TRANSITION_PICTURES
        }
        assert len(rendered) == len(TPORT_TRANSITION_PICTURES)


# ---------------------------------------------------------------------------
# The size-driven raw block fallback: artwork that is in no table at all.
# ---------------------------------------------------------------------------

_HERO_DISSOLVE_SIZE = (3, 3)


def _exit_pictures() -> list[list[int]]:
    """``players._PLAYER_EXIT_PICTURE`` as four rows of eight."""
    from gauntpy.subsystems.players import _PLAYER_EXIT_PICTURE

    return [list(_PLAYER_EXIT_PICTURE[c * 8:c * 8 + 8]) for c in range(4)]


def _dissolve_frames() -> list[tuple[str, int, int]]:
    """``(hero name, frame index 1-7, picture)`` for all 28 dissolve frames.

    Frame 0 of each class is the hero's own idle/standing picture and is in
    gex's animation table; 1-7 are the dissolve proper and are in nothing.
    """
    return [
        (HERO_NAMES[character], index, picture)
        for character, row in enumerate(_exit_pictures())
        for index, picture in enumerate(row)
        if index
    ]


#: The single dissolve frame that *is* in a table: 0x1087 is also one of the
#: Warrior's shooting frames, so it resolves through the animation index and
#: never reaches the size fallback at all. Tests that are about the fallback's
#: own behaviour have to use one of the other 27.
_TABLED_DISSOLVE_PICTURE = 0x1087


def _unnamed_dissolve_frames() -> list[tuple[str, int, int]]:
    return [row for row in _dissolve_frames() if row[2] != _TABLED_DISSOLVE_PICTURE]


@requires_roms
class TestHeroDissolveFallback:
    """``players._PLAYER_EXIT_PICTURE`` entries 1-7 per class: the 32-frame
    dissolve a hero plays in the exit (and the same table the death path
    steps). Seven 3x3 blocks per class, in no gex animation record -- so
    before the size fallback the MOB layer dropped the hero part-way through
    dying and the player just vanished.
    """

    @pytest.mark.parametrize("name,index,picture", _dissolve_frames())
    def test_a_dissolve_frame_renders_3x3_in_its_own_class_bank(
        self, name, index, picture
    ):
        store = AssetStore()
        stamp = store.sprite(
            picture, kind=name, palette=0, size=_HERO_DISSOLVE_SIZE
        )
        assert stamp.width == 3
        assert len(stamp.numbers) == 9
        assert list(stamp.numbers) == list(range(picture, picture + 9))
        assert (stamp.ptype, stamp.pnum) == (name, 0), (name, index)
        assert _render_stamp(store, stamp).size == (24, 24)
        assert _lit_pixels(stamp) > 0

    def test_all_four_classes_have_seven_frames_each(self):
        assert len(_dissolve_frames()) == 4 * 7

    def test_each_class_dissolves_in_its_own_colours(self):
        """The whole point of threading ``kind`` through the fallback: the same
        3x3 block drawn through four different banks is four different heroes.
        """
        store = AssetStore()
        for name, _index, picture in _unnamed_dissolve_frames():
            for other in HERO_NAMES:
                stamp = store.sprite(
                    picture, kind=other, palette=0, size=_HERO_DISSOLVE_SIZE
                )
                assert stamp.ptype == other
            assert store.sprite(
                picture, kind=name, palette=0, size=_HERO_DISSOLVE_SIZE
            ).ptype == name

    def test_the_dissolve_actually_dissolves(self):
        """Real ROM artwork, so it has to look like a dissolve: after the first
        couple of frames each one is strictly fainter than the last, and the
        final frame is a handful of pixels. A block decoded from the wrong base
        would not fade at all.
        """
        store = AssetStore()
        for character, row in enumerate(_exit_pictures()):
            name = HERO_NAMES[character]
            lit = [
                _lit_pixels(store.sprite(p, kind=name, size=_HERO_DISSOLVE_SIZE))
                for p in row[1:]
            ]
            assert all(count > 0 for count in lit), (name, lit)
            tail = lit[2:]
            assert tail == sorted(tail, reverse=True), (name, lit)
            assert len(set(tail)) == len(tail), (name, lit)
            assert lit[-1] * 5 < lit[0], (name, lit)

    def test_without_a_size_almost_every_dissolve_frame_still_raises(self):
        """The fallback is opt-in, and this is the measurement of the gap it
        fills: 27 of the 28 dissolve frames are in no table gex has. The
        exception is the Warrior's first, 0x1087, which happens to also be one
        of his shooting frames.
        """
        store = AssetStore()
        unresolved = []
        for name, _index, picture in _dissolve_frames():
            try:
                store.sprite(picture, kind=name)
            except AssetError:
                unresolved.append(picture)
        assert len(unresolved) == 27
        assert 0x1087 not in unresolved
        assert store.sprite(0x1087, kind="warrior").ptype == "warrior"

    def test_a_named_picture_ignores_the_size_it_is_given(self):
        """The fallback is last, so it can never override a table: a Ghost
        walk frame stays the Ghost's own 3x3 base-bank sprite even when a
        caller passes a size that disagrees."""
        from gex.monsters import MONSTERS

        store = AssetStore()
        ghost = MONSTERS["ghost"].anims["walk"]["up"][0]
        assert store.sprite(ghost, size=(1, 1)) is store.sprite(ghost)


@requires_roms
class TestSizedBlockContract:
    """What the fallback must *not* do: swallow the failures that mean
    something is genuinely wrong.
    """

    def test_an_unknown_picture_without_a_size_still_errors(self):
        store = AssetStore()
        with pytest.raises(AssetError, match="No known sprite"):
            store.sprite(0x0001)
        with pytest.raises(AssetError, match="No known sprite"):
            store.sprite(0x0001, kind="wizard")

    def test_a_marker_word_still_errors_even_with_a_size(self):
        """Markers are checked first: a wall is drawn by the playfield layer,
        and a size does not turn one into a sprite."""
        store = AssetStore()
        for marker in (0x8000, 0x8001, 0x8003):
            with pytest.raises(AssetError, match="Marker words"):
                store.sprite(marker, size=(2, 2))

    def test_a_block_the_tile_roms_do_not_hold_still_errors(self):
        """"No art here" and "art we had no table for" are different failures
        and the second must not hide the first. The tile ROMs end at 0x2800,
        so a block that runs off the end has to say so."""
        from gex.roms import TILE_ROM_SETS

        last_tile = 0x800 * len(TILE_ROM_SETS)
        store = AssetStore()
        with pytest.raises(AssetError, match="tile ROMs do not hold"):
            store.sprite(last_tile - 2, size=(3, 3))

    @pytest.mark.parametrize("size", [(0, 3), (3, 0), (9, 3), (3, 9), (-1, 1)])
    def test_a_size_mob_vpos_cannot_encode_is_reported_as_a_caller_bug(self, size):
        store = AssetStore()
        with pytest.raises(AssetError, match="mob_vpos cannot encode"):
            store.sprite(0x0001, size=size)
        assert MAX_BLOCK_TILES == 8

    def test_the_blank_flash_picture_decodes_to_nothing_visible(self):
        """0x1709 is the ROM's blank picture -- ``tport_player_flash``
        (0x50616), the invisibility flicker (``invisibility_flash_masks``) and
        ``monsters._BLANK_PICTURE`` all park it in a live MOB slot. The
        fallback now decodes it instead of skipping it, so it had better be
        genuinely empty artwork rather than garbage.
        """
        from gauntpy.subsystems.monsters import _BLANK_PICTURE
        from gauntpy.subsystems.players import _PLAYER_INVISIBLE_PICTURE

        assert _BLANK_PICTURE == _PLAYER_INVISIBLE_PICTURE == 0x1709
        store = AssetStore()
        for kind in (None, *HERO_NAMES):
            stamp = store.sprite(0x1709, kind=kind, palette=0, size=(3, 3))
            assert len(stamp.numbers) == 9
            assert _lit_pixels(stamp) == 0, "the blank flash must draw nothing"
            assert _render_stamp(store, stamp).size == (24, 24)

    def test_without_a_kind_a_raw_block_uses_the_base_mob_bank(self):
        store = AssetStore()
        picture = _unnamed_dissolve_frames()[0][2]
        stamp = store.sprite(picture, size=_HERO_DISSOLVE_SIZE)
        assert (stamp.ptype, stamp.pnum) == ("base", 0)

    def test_the_live_palette_nibble_picks_the_entry_inside_that_bank(self):
        from gex.palettes import GAUNTLET_PALETTES

        store = AssetStore()
        picture = _unnamed_dissolve_frames()[0][2]
        for index in range(len(GAUNTLET_PALETTES["warrior"])):
            stamp = store.sprite(
                picture, kind="warrior", palette=index, size=_HERO_DISSOLVE_SIZE
            )
            assert (stamp.ptype, stamp.pnum) == ("warrior", index)

    def test_a_nibble_the_bank_has_no_entry_for_falls_back_to_the_default(self):
        from gex.palettes import GAUNTLET_PALETTES

        store = AssetStore()
        picture = _unnamed_dissolve_frames()[0][2]
        out_of_bank = len(GAUNTLET_PALETTES["warrior"])
        stamp = store.sprite(
            picture, kind="warrior", palette=out_of_bank, size=_HERO_DISSOLVE_SIZE
        )
        assert (stamp.ptype, stamp.pnum) == ("warrior", 0)

    def test_a_raw_block_is_cached_like_every_other_stamp(self):
        store = AssetStore()
        picture = _unnamed_dissolve_frames()[0][2]
        first = store.sprite(picture, kind="warrior", palette=0, size=(3, 3))
        assert first is store.sprite(picture, kind="warrior", palette=0, size=(3, 3))

    def test_arbitrary_block_shapes_decode_row_major_from_the_picture(self):
        """"Contiguous tile block" is the whole contract, and it is not only
        square: a score popup is 3x1 and a shot is 2x2. Every shape the size
        word can name must lay its tiles out row-major from the picture, the
        way ``gex.render.gen_image`` does.
        """
        from gex.render import gen_image

        store = AssetStore()
        base = 0x0400
        for xsize, ysize in ((1, 1), (3, 1), (1, 3), (2, 2), (4, 2), (8, 8)):
            stamp = store.sprite(base, size=(xsize, ysize))
            assert stamp.width == xsize
            assert list(stamp.numbers) == list(range(base, base + xsize * ysize))
            ours = _render_stamp(store, stamp)
            assert ours.size == (xsize * 8, ysize * 8)
            assert ours.tobytes() == gen_image(base, xsize, ysize, "base", 0).tobytes()


# ---------------------------------------------------------------------------
# Entity kinds: which creature a shared picture number belongs to.
#
# ROM-free. Everything in the first two classes reads gex's bundled animation
# data (jsonc) through the picture index, which is built at import time with no
# ROM I/O -- so they run even where the graphics ROMs aren't configured, which
# is exactly where a data regression would otherwise go unnoticed.
# ``AssetStore._frame_for`` is a static method for the same reason: identifying
# a picture never needed a constructed store, only building pixels does.
# ---------------------------------------------------------------------------

from gex.heroes import HEROES  # noqa: E402
from gex.monsters import MONSTERS  # noqa: E402
from gex.npcs import NPCS  # noqa: E402

from gauntpy.constants import Character  # noqa: E402

_ENTITY_GROUPS = (("hero", HEROES), ("monster", MONSTERS), ("npc", NPCS))


def _all_frames(entity):
    """(action, direction, frame_index, tile) for every frame of one entity."""
    for action, dirs in entity.anims.items():
        for direction, frames in dirs.items():
            for index, tile in enumerate(frames):
                yield action, direction, index, tile


class TestPictureNumbersAreNotUnique:
    """The premise the ``kind`` argument exists for, pinned so a change in
    gex's data (a new family, a retabulated animation) is reported here rather
    than as a mysteriously recoloured sprite.
    """

    @staticmethod
    def _owners() -> dict[int, set[str]]:
        owners: dict[int, set[str]] = {}
        for _family, group in _ENTITY_GROUPS:
            for name, entity in group.items():
                for _action, _direction, _index, tile in _all_frames(entity):
                    owners.setdefault(tile, set()).add(name)
        return owners

    def test_the_wizard_shares_forty_tiles_with_the_two_sorcerers(self):
        """The Sorcerer and Super Sorcerer are drawn from the Wizard's own
        artwork -- the collision is real ROM data, not a gex transcription
        slip, and it is the whole reason a picture number cannot name an
        entity by itself.
        """
        shared = {tile: names for tile, names in self._owners().items() if len(names) > 1}
        assert len(shared) == 40
        assert {frozenset(names) for names in shared.values()} == {
            frozenset({"wizard", "sorcerer", "supersorc"}),
            frozenset({"wizard", "sorcerer"}),
        }

    def test_no_other_entity_pair_is_ambiguous(self):
        """If gex ever gains data that makes some *other* pair share tiles,
        ``render.mobs.sprite_kind`` needs a rule for that pair too."""
        shared = {tile: names for tile, names in self._owners().items() if len(names) > 1}
        assert set().union(*shared.values()) == {"wizard", "sorcerer", "supersorc"}

    def test_without_a_kind_the_wizard_still_answers_sorcerer(self):
        """The flat index keeps its monsters-first answer: a placed maze
        object's picture is a monster far more often than a hero, and callers
        that know better now say so instead of the map guessing for them.
        """
        wizard_walk_down = HEROES["wizard"].anims["walk"]["down"][0]
        assert AssetStore._frame_for(wizard_walk_down, None).monster_type == "sorcerer"


class TestKindAttributesEveryFrame:
    """Exhaustive: every frame of every entity gex knows about, resolved with
    that entity named, must come back as that entity -- and as a frame the
    entity really has at that tile.

    The reported ``(action, direction, frame_index)`` is deliberately not
    asserted field by field: entities genuinely reuse one tile across actions
    and directions (Acid's single sprite fills all eight compass entries; the
    Warrior's shoot and fight cycles overlap), so the index picks one triple by
    a fixed precedence. What must hold is that the triple it picks names *this*
    tile in *this* entity's own table -- the property a renderer depends on.
    """

    def test_every_entity_frame_resolves_to_that_entity(self):
        checked = 0
        for _family, group in _ENTITY_GROUPS:
            for name, entity in group.items():
                for action, direction, index, tile in _all_frames(entity):
                    frame = AssetStore._frame_for(tile, name)
                    where = (name, action, direction, index, tile)
                    assert frame is not None, where
                    assert frame.monster_type == name, (where, frame)
                    assert (
                        entity.anims[frame.action][frame.direction][frame.frame_index] == tile
                    ), (where, frame)
                    checked += 1
        assert checked == 1520, "gex's animation data changed size -- re-read this test"

    def test_every_frame_also_resolves_within_its_family(self):
        """The coarse kinds work too, for a caller that knows it is holding a
        hero but not which class."""
        for family, group in _ENTITY_GROUPS:
            for name, entity in group.items():
                for action, direction, index, tile in _all_frames(entity):
                    frame = AssetStore._frame_for(tile, family)
                    assert frame is not None and frame.monster_type in group, (
                        family, name, action, direction, index, tile,
                    )

    def test_every_wizard_frame_is_a_wizard_frame(self):
        """The finding itself: 112 of the Wizard's 136 frame entries -- every
        walk and idle frame, half of fight and shoot -- resolve to a Sorcerer
        without a kind, and to the Wizard with one."""
        wizard = HEROES["wizard"]
        misattributed = [
            (action, direction, index, tile)
            for action, direction, index, tile in _all_frames(wizard)
            if AssetStore._frame_for(tile, None).monster_type != "wizard"
        ]
        assert len(misattributed) == 112
        for action, direction, index, tile in misattributed:
            assert AssetStore._frame_for(tile, "wizard").monster_type == "wizard"
            assert AssetStore._frame_for(tile, "hero").monster_type == "wizard"

    def test_the_two_sorcerers_stay_separable_from_each_other(self):
        """They share 24 tiles with each other as well as with the Wizard, so
        the family kind is not enough for them -- the entity kind is."""
        shared = set(MONSTERS["sorcerer"].anims["walk"]["down"]) & set(
            MONSTERS["supersorc"].anims["walk"]["down"]
        )
        assert shared
        for tile in shared:
            assert AssetStore._frame_for(tile, "sorcerer").monster_type == "sorcerer"
            assert AssetStore._frame_for(tile, "supersorc").monster_type == "supersorc"

    def test_a_kind_is_a_preference_not_a_filter(self):
        """A hero slot does not hold hero artwork every frame -- the death
        animation (``players._PLAYER_DEATH_PICTURE``) and the bonus-screen icon
        both live in the player's own MOB slot. Naming the hero must not stop
        those resolving.
        """
        ghost_walk_up = MONSTERS["ghost"].anims["walk"]["up"][0]
        assert AssetStore._frame_for(ghost_walk_up, "wizard").monster_type == "ghost"
        assert AssetStore._frame_for(ghost_walk_up, "hero").monster_type == "ghost"

    def test_an_unknown_kind_is_a_loud_error_not_a_silent_fallback(self):
        """A typo'd kind that quietly fell through to the flat map would render
        the wrong palette exactly as before the fix, invisibly."""
        with pytest.raises(AssetError, match="Unknown sprite kind"):
            AssetStore._frame_for(2192, "wizzard")

    def test_the_hero_name_table_matches_gex_and_the_rom_class_order(self):
        assert set(HERO_NAMES) == set(HEROES)
        assert HERO_NAMES[int(Character.WIZARD)] == "wizard"
        assert HERO_NAMES == ("warrior", "valkyrie", "wizard", "elf")


@requires_roms
class TestKindSelectsThePaletteBank:
    """What the disambiguation is *for*: the entity a picture resolves to
    decides the sprite's palette bank, so getting it wrong paints a hero in a
    monster's colours.
    """

    @staticmethod
    def _wizard_tile() -> int:
        return HEROES["wizard"].anims["walk"]["down"][0]

    def test_a_wizard_renders_in_the_wizard_bank_not_the_sorcerers(self):
        store = AssetStore()
        tile = self._wizard_tile()
        assert store.sprite(tile).ptype == "base", "unchanged without a kind"
        wizard = store.sprite(tile, kind="wizard")
        assert (wizard.ptype, wizard.pnum) == ("wizard", HEROES["wizard"].pnum)

    def test_the_wizards_pixels_are_gexs_own_wizard_rendering(self):
        """End to end against gex's reference path for a hero frame -- the same
        ``gen_image(tile, xsize, ysize, hero.ptype, hero.pnum)`` call
        ``gex.heroes.dohero`` makes for ``wizard-walk-down``.
        """
        from gex.render import gen_image

        store = AssetStore()
        tile = self._wizard_tile()
        hero = HEROES["wizard"]

        ours = _render_stamp(store, store.sprite(tile, kind="wizard"))
        reference = gen_image(tile, hero.xsize, hero.ysize, hero.ptype, hero.pnum)
        assert ours.size == reference.size == (24, 24)
        assert ours.tobytes() == reference.tobytes()

        # And it is genuinely different from what the picture number alone
        # gave -- otherwise this test would pass on a broken fix.
        assert _render_stamp(store, store.sprite(tile)).tobytes() != reference.tobytes()

    def test_the_raw_palette_nibble_still_selects_inside_the_right_bank(self):
        """``mob_hpos`` bits 3-0 keep choosing the entry; ``kind`` only chooses
        the bank it indexes."""
        from gex.palettes import GAUNTLET_PALETTES

        store = AssetStore()
        tile = self._wizard_tile()
        for index in range(len(GAUNTLET_PALETTES["wizard"])):
            stamp = store.sprite(tile, palette=index, kind="wizard")
            assert (stamp.ptype, stamp.pnum) == ("wizard", index)

    def test_hardware_player_palette_nibble_selects_player_identity(self):
        store = AssetStore()
        elf_tile = HEROES["elf"].anims["walk"]["down"][0]

        stamp = store.sprite(elf_tile, palette=0x0D, kind="elf")

        assert (stamp.ptype, stamp.pnum) == ("elf", 1)

    def test_a_nibble_the_bank_has_no_entry_for_falls_back_to_the_default(self):
        """Banks are not all the same depth -- ``base`` has 12 entries, a
        hero's own bank 4. A hero MOB is placed with nibble 0
        (``mazeobj_hsize_tier_tbl``'s PLAYERSTART entry) and ``player_move``
        preserves it, but nothing stops a caller passing a wider one, and a
        hero who vanishes for a frame is a worse answer than a hero in his
        standing colour.
        """
        from gex.palettes import GAUNTLET_PALETTES

        store = AssetStore()
        tile = self._wizard_tile()
        out_of_bank = len(GAUNTLET_PALETTES["wizard"])
        stamp = store.sprite(tile, palette=out_of_bank, kind="wizard")
        assert (stamp.ptype, stamp.pnum) == ("wizard", HEROES["wizard"].pnum)

        # A monster's bank is deep enough for every nibble the game places, so
        # nothing about the wounded-monster colour walk changes.
        ghost = MONSTERS["ghost"].anims["walk"]["up"][0]
        assert store.sprite(ghost, palette=0xB).pnum == 0xB

    def test_a_monster_is_unaffected_by_the_new_argument(self):
        """Naming a kind that already agreed with the flat map must not disturb
        the answer -- the fix is additive."""
        store = AssetStore()
        ghost = MONSTERS["ghost"].anims["walk"]["up"][0]
        assert store.sprite(ghost, palette=4) is store.sprite(ghost, palette=4, kind="ghost")

    def test_the_thief_keeps_its_npc_bank(self):
        store = AssetStore()
        thief = NPCS["thief"].anims["walk"]["down"][0]
        stamp = store.sprite(thief, kind="thief")
        assert (stamp.ptype, stamp.pnum) == (NPCS["thief"].ptype, NPCS["thief"].pnum)



# ---------------------------------------------------------------------------
# Missing-ROM failure path -- must NOT depend on ROMs being present, so it is
# deliberately outside the module-level skip.
# ---------------------------------------------------------------------------

class TestMissingRoms:
    # Deliberately avoids the ``tmp_path`` fixture: this suite runs in a
    # shared tree alongside other concurrent work, and pytest's basetemp
    # creation under a shared TEMP root is not reliably writable here. A
    # plain nonexistent relative path is enough to exercise the failure path.
    _BOGUS_DIR = "gauntpy-test-assets-nonexistent-rom-dir"

    def test_clear_actionable_error_when_roms_missing(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", self._BOGUS_DIR)
        with pytest.raises(AssetError) as excinfo:
            AssetStore()
        message = str(excinfo.value)
        assert "GEX_ROM_DIR" in message
        assert "python-gex/README.md" in message

    def test_clear_actionable_error_when_env_unset(self, monkeypatch):
        # cwd while running "pytest tests" from gauntpy/ has no ./ROMs
        # subdirectory of its own, so the unset-env fallback path is already
        # exercised without needing to chdir anywhere.
        monkeypatch.delenv("GEX_ROM_DIR", raising=False)
        with pytest.raises(AssetError) as excinfo:
            AssetStore()
        assert "GEX_ROM_DIR" in str(excinfo.value)
