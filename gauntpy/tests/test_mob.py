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


# ---------------------------------------------------------------------------
# Ordering: the ROM sorts by packed slot, not by pixel Y (0x5DCFE / 0x5DFE6)
# ---------------------------------------------------------------------------

def test_the_chain_is_ordered_by_slot_number():
    """Within one row, ascending column is ascending slot -- the tie-break a
    band-only sort throws away. Insertion order must not survive."""
    mobs = MobTable()
    for col in (20, 4, 11, 31, 0):
        place(mobs, 6, col)
    assert list(mobs.iter_chain()) == [
        coords.pack_slot(6, col) for col in (0, 4, 11, 20, 31)
    ]


def test_ordering_ignores_a_pixel_position_that_disagrees_with_the_slot():
    """A monster mid-step has a pixel Y between two rows; its depth is still
    its cell's. Sorting on the live vpos would let two MOBs swap places
    mid-stride and make the band sequence non-monotonic."""
    mobs = MobTable()
    early = place(mobs, 4, 4)
    late = place(mobs, 5, 4)
    mobs.vpos[early] = coords.encode_vpos(500)     # dragged far down the screen

    assert list(mobs.iter_chain()) == [early, late]
    assert mobs.band_of(early) == 8


def test_sort_key_is_the_slot_for_dynamic_slots():
    mobs = MobTable()
    assert mobs.sort_key(500) == 500
    assert mobs.band_of(500) == (500 >> 5) * 2


def test_a_managed_low_slot_sorts_by_its_depth_key():
    """Slots 0-0x1F are shots, popups and effect animations: they have no cell
    of their own, so ``mob_depth_key`` (0x904940) says where in the chain they
    belong -- typically the slot they were spawned from."""
    mobs = MobTable()
    near = place(mobs, 2, 2)
    far = place(mobs, 20, 2)

    shot = 3
    mobs.picture[shot] = 0x0900
    mobs.insert(shot, depth_key=coords.pack_slot(10, 2))

    assert mobs.sort_key(shot) == coords.pack_slot(10, 2)
    assert mobs.depth_key[shot] == coords.pack_slot(10, 2)
    assert list(mobs.iter_chain()) == [near, shot, far]
    assert mobs.band_of(shot) == 20


def test_a_low_slot_without_a_depth_key_sorts_to_the_front():
    """Key 0 is what an uninitialised 0x904940 word holds, and the chain is
    ascending, so the effect lands at the head -- not at slot 3's own row."""
    mobs = MobTable()
    body = place(mobs, 8, 8)
    mobs.picture[3] = 0x0900
    mobs.insert(3)
    assert list(mobs.iter_chain()) == [3, body]


def test_slips_stay_monotonic_with_a_depth_keyed_effect_present():
    mobs = MobTable()
    place(mobs, 2, 2)
    place(mobs, 20, 2)
    mobs.picture[5] = 0x0900
    mobs.insert(5, depth_key=coords.pack_slot(10, 2))

    bands = [mobs.band_of(s) for s in mobs.iter_chain()]
    assert bands == sorted(bands)
    for band, head in enumerate(mobs.slip_heads):
        if head:
            assert mobs.band_of(head) >= band


# ---------------------------------------------------------------------------
# mob_create's own insertion guard (0x5DCC0-0x5DCC6)
# ---------------------------------------------------------------------------

def test_creating_over_a_live_object_rewrites_it_without_relinking():
    """``moblist_insert`` runs *before* the new picture is written and bails
    out unless what is there is empty or the 0x8000 wall marker. Linking twice
    would splice the slot into the chain at two places at once."""
    mobs = MobTable()
    slot = place(mobs, 7, 7, MazeObjIds.MONST_GHOST)
    assert list(mobs.iter_chain()) == [slot]

    place(mobs, 7, 7, MazeObjIds.MONST_DEMON)

    assert list(mobs.iter_chain()) == [slot], "still linked exactly once"
    assert mobs.obj_type(slot) == MazeObjIds.MONST_DEMON, "the record is replaced"


def test_recreating_middle_live_object_preserves_both_chain_links():
    mobs = MobTable()
    first = place(mobs, 6, 7, MazeObjIds.MONST_GHOST)
    middle = place(mobs, 7, 7, MazeObjIds.MONST_GHOST)
    last = place(mobs, 8, 7, MazeObjIds.MONST_GHOST)
    assert list(mobs.iter_chain()) == [first, middle, last]

    place(mobs, 7, 7, MazeObjIds.MONST_DEMON)

    assert list(mobs.iter_chain()) == [first, middle, last]
    assert mobs.prev_slot(middle) == first
    assert mobs.next_slot(middle) == last


def test_creating_over_a_wall_marker_does_link():
    mobs = MobTable()
    slot = coords.pack_slot(7, 7)
    mobs.picture[slot] = 0x8000          # a solid-wall marker, not chain-linked
    assert not mobs.is_linked(slot)

    place(mobs, 7, 7, MazeObjIds.MONST_GHOST)
    assert list(mobs.iter_chain()) == [slot]


def test_move_slot_will_not_link_a_destination_that_is_already_live():
    """``move_mob_slot`` links the destination before copying, so the guard
    sees the destination's *previous* picture (0x5DE0A)."""
    mobs = MobTable()
    src = place(mobs, 3, 3, MazeObjIds.MONST_GHOST)
    dst = place(mobs, 9, 9, MazeObjIds.MONST_GRUNT)

    mobs.move_slot(src, dst)

    chain = list(mobs.iter_chain())
    assert chain == [dst], "destination linked once, source gone"
    assert mobs.obj_type(dst) == MazeObjIds.MONST_GHOST


def test_is_linked_distinguishes_occupancy_from_membership():
    mobs = MobTable()
    slot = coords.pack_slot(5, 5)
    mobs.picture[slot] = 0x8000
    mobs.set_obj_type(slot, MazeObjIds.WALL_REGULAR)

    assert mobs.is_occupied(slot)
    assert not mobs.is_linked(slot)
    assert list(mobs.iter_chain()) == []


def test_unlinking_something_that_is_not_in_the_chain_is_a_no_op():
    mobs = MobTable()
    a = place(mobs, 4, 4)
    b = coords.pack_slot(9, 9)

    mobs.unlink(b)
    assert list(mobs.iter_chain()) == [a]
    assert mobs.depth_list_head == a


def test_unlink_and_clear_still_zeroes_an_unlinked_marker():
    mobs = MobTable()
    slot = coords.pack_slot(5, 5)
    mobs.picture[slot] = 0x8000
    mobs.set_obj_type(slot, MazeObjIds.WALL_REGULAR)

    mobs.unlink_and_clear(slot)
    assert not mobs.is_occupied(slot)


def test_a_marker_never_lengthens_the_chain():
    """Hundreds of walls per maze would otherwise be walked by every
    per-frame chain scan in the game."""
    mobs = MobTable()
    for col in range(32):
        slot = coords.pack_slot(3, col)
        mobs.picture[slot] = 0x8000
        mobs.set_obj_type(slot, MazeObjIds.WALL_REGULAR)
    monster = place(mobs, 4, 4)
    assert list(mobs.iter_chain()) == [monster]
