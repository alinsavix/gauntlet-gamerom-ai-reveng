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

from gauntpy.assets import AssetError, AssetStore, PICTURE_TILE_MASK, SpriteFrame

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


@pytest.fixture(scope="module")
def manifest() -> dict:
    with open(_MANIFEST_PATH) as f:
        return json.load(f)


def _pixel_sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _render_stamp(store: AssetStore, stamp) -> "object":
    """Render an AssetStore-built Stamp to a PIL image the same way gex's
    own golden tests do (``gex.render.blank_image`` / ``write_stamp_to_image``).
    This is test-support tooling only -- assets.py itself never touches PIL.
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
