"""MOB slot table, packed fields, and the shared depth chain."""

from __future__ import annotations

from gauntpy import coords
from gauntpy.constants import NULL_SLOT, MazeObjIds
from gauntpy.mob import MobTable


def place(mobs: MobTable, row: int, col: int, obj_type=MazeObjIds.MONST_GHOST) -> int:
    """Create an object at a maze cell, at that cell's own slot number."""
    slot = coords.pack_slot(row, col)
    x, y = coords.slot_to_pixels(slot)
    return mobs.create(
        slot,
        tile=0x100,
        hpos=coords.encode_hpos(x, palette=3),
        vpos=coords.encode_vpos(y, width=3, height=3),
        obj_type=obj_type,
    )


def test_packed_fields_roundtrip():
    mobs = MobTable()
    slot = place(mobs, 12, 20, MazeObjIds.MONST_GRUNT)

    assert slot == 404, "slot number is the packed cell address"
    assert mobs.obj_type(slot) == MazeObjIds.MONST_GRUNT
    assert mobs.position(slot) == (320, 192)
    assert coords.decode_hpos(mobs.hpos[slot])[2] == 3     # palette
    assert coords.decode_vpos(mobs.vpos[slot])[1:] == (3, 3)  # width, height


def test_type_and_link_share_one_word():
    """Object type lives in the top six bits of the link word."""
    mobs = MobTable()
    slot = place(mobs, 5, 5, MazeObjIds.MONST_DEMON)

    mobs.set_next(slot, 0x3FF)
    assert mobs.obj_type(slot) == MazeObjIds.MONST_DEMON, "type survived a link write"
    assert mobs.next_slot(slot) == 0x3FF

    mobs.set_obj_type(slot, MazeObjIds.KEY)
    assert mobs.next_slot(slot) == 0x3FF, "link survived a type write"


def test_state_and_backlink_share_one_word():
    mobs = MobTable()
    slot = place(mobs, 6, 6)

    mobs.set_state(slot, 0x2A)
    mobs.set_prev(slot, 300)
    assert mobs.state(slot) == 0x2A
    assert mobs.prev_slot(slot) == 300


def test_chain_is_depth_sorted():
    """Insertion order must not matter; vertical band decides."""
    mobs = MobTable()
    bottom = place(mobs, 20, 4)
    top = place(mobs, 2, 4)
    middle = place(mobs, 11, 4)

    assert list(mobs.iter_chain()) == [top, middle, bottom]


def test_chain_is_doubly_linked():
    mobs = MobTable()
    slots = [place(mobs, r, 3) for r in (4, 9, 14)]

    walked = list(mobs.iter_chain())
    assert mobs.prev_slot(walked[0]) == NULL_SLOT
    for earlier, later in zip(walked, walked[1:]):
        assert mobs.next_slot(earlier) == later
        assert mobs.prev_slot(later) == earlier
    assert mobs.next_slot(walked[-1]) == NULL_SLOT
    assert set(walked) == set(slots)


def test_unlink_preserves_the_record():
    """moblist_remove repairs links but leaves picture/H/V and type alone."""
    mobs = MobTable()
    a, b, c = (place(mobs, r, 7) for r in (3, 8, 13))

    picture, hpos = mobs.picture[b], mobs.hpos[b]
    mobs.unlink(b)

    assert list(mobs.iter_chain()) == [a, c]
    assert mobs.picture[b] == picture
    assert mobs.hpos[b] == hpos
    assert mobs.obj_type(b) == MazeObjIds.MONST_GHOST


def test_unlink_and_clear_zeroes_everything():
    mobs = MobTable()
    a = place(mobs, 3, 7)
    b = place(mobs, 8, 7)

    mobs.unlink_and_clear(b)

    assert list(mobs.iter_chain()) == [a]
    assert mobs.picture[b] == 0
    assert mobs.hpos[b] == 0
    assert mobs.vpos[b] == 0
    assert mobs.link[b] == 0
    assert mobs.state_link[b] == 0
    assert not mobs.is_occupied(b)


def test_unlink_head_updates_global_head():
    mobs = MobTable()
    head = place(mobs, 2, 2)
    second = place(mobs, 12, 2)

    mobs.unlink(head)
    assert mobs.depth_list_head == second


def test_move_slot_relocates_the_record():
    """A monster 'moving' means its record moves to the destination slot."""
    mobs = MobTable()
    src = place(mobs, 10, 10, MazeObjIds.MONST_LOBBER)
    mobs.set_state(src, 0x15)
    dst = coords.pack_slot(10, 11)

    mobs.move_slot(src, dst)

    assert not mobs.is_occupied(src), "source cell is vacated"
    assert mobs.obj_type(dst) == MazeObjIds.MONST_LOBBER
    assert mobs.state(dst) == 0x15
    assert dst in list(mobs.iter_chain())
    assert src not in list(mobs.iter_chain())


def test_slot_occupancy_is_arithmetic_not_search():
    """The most common query in the game: what is in that cell?"""
    mobs = MobTable()
    place(mobs, 9, 9, MazeObjIds.KEY)

    assert mobs.is_occupied(coords.pack_slot(9, 9))
    assert mobs.obj_type(coords.pack_slot(9, 9)) == MazeObjIds.KEY
    assert not mobs.is_occupied(coords.pack_slot(9, 10))


def test_slips_enter_the_one_chain():
    """SLIPs are cumulative bookmarks into a single list, not 64 lists."""
    mobs = MobTable()
    near_top = place(mobs, 1, 5)     # y=16  -> band 2
    lower = place(mobs, 10, 5)       # y=160 -> band 20

    assert mobs.band_of(near_top) == 2
    assert mobs.band_of(lower) == 20

    # Every band at or before the first object enters at that object.
    assert mobs.slip_heads[0] == near_top
    assert mobs.slip_heads[2] == near_top
    # Bands after it, up to the next object, still enter at the later one.
    assert mobs.slip_heads[20] == lower
    # Walking from a band yields that object and everything behind it.
    assert list(mobs.iter_from_band(20)) == [lower]
    assert list(mobs.iter_from_band(0)) == [near_top, lower]


def test_slip_bands_follow_the_playfield_not_the_screen():
    """A sprite's band must not change when the camera scrolls."""
    mobs = MobTable()
    slot = place(mobs, 16, 16)
    assert mobs.band_of(slot) == (16 * 16) // 8
