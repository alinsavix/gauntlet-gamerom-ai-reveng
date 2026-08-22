"""MOB slot table and the shared depth chain.

A "thing in the maze" is one index into five parallel arrays of 16-bit words.
Four of them are the VRAM tables the display hardware reads; the fifth lives in
working RAM and completes the record.

Reference: ``doc/04_game_subsystems.md`` §1.1, §2.1, §24;
``book/08_world_in_memory.md``.

    array           hw?  contents
    picture         yes  tile number (bits 14-0), software flag (bit 15)
    hpos            yes  X (15-7), flags (6-4), palette (3-0)
    vpos            yes  Y (15-7), spare (6), width-1 (5-3), height-1 (2-0)
    link            yes  object type (15-10), next slot (9-0)
    state_link      no   object state (15-10), previous slot (9-0)

The low ten bits of ``link``/``state_link`` make one doubly linked chain,
sorted by depth. The 64 SLIP band heads (0x905F80) are cumulative bookmarks
*into that same chain* -- they are not 64 independent lists -- so band ``b``
names the first MOB belonging to band ``b`` or any later one.

Ordering (``moblist_insert`` 0x5DCBC, ``insert_mob_depth_sorted`` 0x5DFA6,
both read off ``row76.bin``) is by **packed slot number**, not by pixel Y: a
maze object's slot *is* its cell address, so ascending slot is exactly
row-major depth order, with the column as a free tie-breaker. The managed low
slots 0-0x1F have no cell of their own, so they sort by the explicit
``mob_depth_key`` word (0x904940) the placement wrappers hand them -- a shot's
key is the slot it was fired from, and that is how it lands at the right depth.
``MobTable.sort_key`` is that one rule.

Two ROM details that are easy to miss and that the tests pin down:

* ``mob_create`` links the slot *before* writing the new picture, and
  ``moblist_insert`` returns immediately unless the picture already there is 0
  or 0x8000 (0x5DCC0-0x5DCC6). Creating over a live object therefore rewrites
  its five words but does **not** link it a second time.
* ``mob_depth_list_head`` (0x9049DE) is written only when an insert runs off
  the end of the chain and is restored to the removed node's predecessor on
  unlink -- it is the ROM's *tail* cache, used to append in O(1); real
  traversal enters through the SLIP table. gauntpy stores the head instead,
  because every consumer here walks forward from it; the resulting chain order
  is identical.
"""

from __future__ import annotations

from collections.abc import Iterator

from . import coords
from .constants import (
    NULL_SLOT,
    NUM_DEPTH_KEYS,
    NUM_MOB_SLOTS,
    NUM_SLIP_BANDS,
    SLIP_BAND_PIXELS,
    MazeObjIds,
)

LINK_MASK = 0x03FF   # bits 9-0: slot pointer
UPPER_SHIFT = 10     # bits 15-10: type (link) or state (state_link)
UPPER_MASK = 0x3F

#: A maze row is 16 px and a SLIP band 8 px, so each row spans two bands
#: (``moblist_insert`` 0x5DCD8-0x5DCDC derives the band from the slot's row,
#: doubled). The ROM's index is ``2 * (row + 1)``, one band further on, because
#: its vertical coordinates measure the *bottom* edge of a cell counting up
#: from the playfield floor while its band table is read top-down; ``2 * row``
#: is the same band sequence, in the same order, one band earlier.
BANDS_PER_ROW = coords.CELL_PIXELS // SLIP_BAND_PIXELS

#: Pictures a slot may already hold and still be linkable: empty, or the solid
#: wall marker (``moblist_insert``'s guard at 0x5DCC0-0x5DCC6).
LINKABLE_PICTURES = (0, 0x8000)


class MobTable:
    """The 1024 MOB slots plus the depth chain that orders them."""

    __slots__ = (
        "picture", "hpos", "vpos", "link", "state_link",
        "depth_list_head", "slip_heads", "depth_key",
    )

    def __init__(self) -> None:
        n = NUM_MOB_SLOTS
        self.picture = [0] * n
        self.hpos = [0] * n
        self.vpos = [0] * n
        self.link = [0] * n
        self.state_link = [0] * n

        self.depth_list_head = NULL_SLOT
        # Cumulative band entry points into the one chain (0x905F80).
        self.slip_heads = [NULL_SLOT] * NUM_SLIP_BANDS
        # Ordering keys for the managed low slots (0x904940). These are *not*
        # a second backward-link table: they stand in for the slot number when
        # a fixed slot has to sort as if it lived at some maze cell.
        self.depth_key = [0] * NUM_DEPTH_KEYS

    # --- packed field accessors -------------------------------------------------

    def obj_type(self, slot: int) -> int:
        return (self.link[slot] >> UPPER_SHIFT) & UPPER_MASK

    def set_obj_type(self, slot: int, obj_type: int) -> None:
        self.link[slot] = (self.link[slot] & LINK_MASK) | ((obj_type & UPPER_MASK) << UPPER_SHIFT)

    def next_slot(self, slot: int) -> int:
        return self.link[slot] & LINK_MASK

    def set_next(self, slot: int, nxt: int) -> None:
        self.link[slot] = (self.link[slot] & ~LINK_MASK) | (nxt & LINK_MASK)

    def state(self, slot: int) -> int:
        return (self.state_link[slot] >> UPPER_SHIFT) & UPPER_MASK

    def set_state(self, slot: int, value: int) -> None:
        self.state_link[slot] = (
            (self.state_link[slot] & LINK_MASK) | ((value & UPPER_MASK) << UPPER_SHIFT)
        )

    def prev_slot(self, slot: int) -> int:
        return self.state_link[slot] & LINK_MASK

    def set_prev(self, slot: int, prev: int) -> None:
        self.state_link[slot] = (self.state_link[slot] & ~LINK_MASK) | (prev & LINK_MASK)

    # --- geometry ----------------------------------------------------------------

    def position(self, slot: int) -> tuple[int, int]:
        """World pixel (x, y) of a slot, converted to downward screen Y."""
        return coords.hpos_x(self.hpos[slot]), coords.vpos_y(self.vpos[slot])

    def sort_key(self, slot: int) -> int:
        """The chain's ordering key for ``slot`` (0x5DCFE / 0x5DFE6).

        A dynamic slot *is* a packed cell address, so it orders itself. The
        managed low slots (0-0x1F: shots, explosions, popups, exit and
        transporter animations) have no cell, so they order by the explicit
        ``mob_depth_key`` word the placement wrappers stored for them --
        typically the packed slot of whatever spawned the effect.
        """
        if slot < NUM_DEPTH_KEYS:
            return self.depth_key[slot]
        return slot

    def band_of(self, slot: int) -> int:
        """SLIP band index for a slot.

        Derived from the ordering key's *row*, not from the live pixel Y
        (0x5DCD6-0x5DCE6): bands measure the playfield, so a sprite's band
        neither changes when the camera scrolls nor drifts as it walks between
        cells, and the chain's band sequence stays monotonic by construction.
        """
        band = (self.sort_key(slot) >> 5) * BANDS_PER_ROW
        return min(band, NUM_SLIP_BANDS - 1)

    def is_occupied(self, slot: int) -> bool:
        """Whether a slot currently holds an object.

        Because slot number equals cell address, this is the whole of
        "what is in that cell?" -- arithmetic, not a search.
        """
        return self.link[slot] != 0 or self.picture[slot] != 0

    def is_linked(self, slot: int) -> bool:
        """Whether ``slot`` is currently a member of the depth chain.

        Marker objects (walls, floor tiles) live in the five arrays without
        ever joining the chain, so "occupied" and "linked" are different
        questions and both get asked.
        """
        return (
            self.depth_list_head == slot
            or self.next_slot(slot) != NULL_SLOT
            or self.prev_slot(slot) != NULL_SLOT
        )

    # --- chain traversal ----------------------------------------------------------

    def iter_chain(self, start: int | None = None) -> Iterator[int]:
        """Walk the depth chain from ``start`` (default: the global head).

        Slot 0 terminates. Guarded against cycles so a corrupt chain fails
        loudly in tests instead of hanging the frame.
        """
        slot = self.depth_list_head if start is None else start
        seen = 0
        while slot != NULL_SLOT:
            yield slot
            slot = self.next_slot(slot)
            seen += 1
            if seen > NUM_MOB_SLOTS:
                raise RuntimeError("cycle detected in MOB depth chain")

    def iter_from_band(self, band: int) -> Iterator[int]:
        """Enter the chain at a SLIP band -- the hardware's traversal."""
        return self.iter_chain(self.slip_heads[band])

    # --- chain mutation -----------------------------------------------------------

    def insert(self, slot: int, depth_key: int | None = None) -> None:
        """Insert ``slot`` into the depth chain -- ``moblist_insert`` (0x5DCBC).

        ``depth_key`` is the explicit ordering key the managed low-slot
        placement wrappers (0x5DF5A-0x5DF9C) supply and
        ``insert_mob_depth_sorted`` (0x5DFA6) stores at 0x904940; it is what
        makes a fixed effect slot sort as if it lived at a maze cell.

        The walk is the ROM's, comparison for comparison: stop at the first
        node whose *raw slot* is greater than our key, and -- for the managed
        low slots, whose raw number is meaninglessly small -- at the first one
        whose own depth key is greater than or equal to it. Equal keys
        therefore go *before* a managed slot and *after* a dynamic one, which
        is exactly what 0x5DFE6-0x5E016 does.
        """
        if depth_key is not None and slot < NUM_DEPTH_KEYS:
            self.depth_key[slot] = depth_key

        key = self.sort_key(slot)
        prev = NULL_SLOT
        cur = self.depth_list_head
        seen = 0
        while cur != NULL_SLOT:
            if cur > key:
                break
            if cur < NUM_DEPTH_KEYS and key <= self.depth_key[cur]:
                break
            prev = cur
            cur = self.next_slot(cur)
            seen += 1
            if seen > NUM_MOB_SLOTS:
                raise RuntimeError("cycle detected in MOB depth chain")

        self.set_next(slot, cur)
        self.set_prev(slot, prev)
        if cur != NULL_SLOT:
            self.set_prev(cur, slot)
        if prev == NULL_SLOT:
            self.depth_list_head = slot
        else:
            self.set_next(prev, slot)

        self.rebuild_slips()

    def moblist_insert(self, slot: int) -> bool:
        """``moblist_insert`` (0x5DCBC) proper: insert unless the slot is live.

        The guard is the first thing the routine does (0x5DCC0-0x5DCC6) and it
        reads the picture that is *already* in the slot: anything other than
        empty or the 0x8000 wall marker means a real object is there and
        already in the chain, so it returns without touching the links. Both
        callers -- ``mob_create`` and ``move_mob_slot`` -- run before the new
        record is written, which is what makes the test meaningful.

        Returns whether the slot was linked. The depth-placed wrappers use
        ``insert`` directly instead; ``insert_mob_depth_sorted`` (0x5DFA6) has
        no such guard, because a fixed effect slot's picture is its *own*
        previous frame.
        """
        if self.picture[slot] not in LINKABLE_PICTURES:
            return False
        self.insert(slot)
        return True

    def unlink(self, slot: int) -> None:
        """``moblist_remove`` (0x5DDA8): repair links and heads, preserve the record.

        Picture/H/V and the upper type/state bits survive -- callers rely on
        this when temporarily lifting an object out of the chain (the thief
        transition in §25 does exactly that).

        A slot that is not in the chain returns untouched. The ROM has no such
        check (it would patch whatever its stale pointers named); here it makes
        "unlink whatever might be there" -- how marker placement and every
        ``unlink_and_clear`` caller uses it -- both safe and cheap.
        """
        if not self.is_linked(slot):
            return

        prev = self.prev_slot(slot)
        nxt = self.next_slot(slot)

        if prev == NULL_SLOT:
            if self.depth_list_head == slot:
                self.depth_list_head = nxt
        else:
            self.set_next(prev, nxt)
        if nxt != NULL_SLOT:
            self.set_prev(nxt, prev)

        self.set_next(slot, NULL_SLOT)
        self.set_prev(slot, NULL_SLOT)
        self.rebuild_slips()

    def unlink_and_clear(self, slot: int) -> None:
        """``moblist_remove_and_clear``: unlink, then zero all five words."""
        self.unlink(slot)
        self.picture[slot] = 0
        self.hpos[slot] = 0
        self.vpos[slot] = 0
        self.link[slot] = 0
        self.state_link[slot] = 0

    def depth_remove(self, physical_slot_minus_one: int) -> None:
        """``mob_depth_remove`` (0x5E064) for temporary depth-placed MOBs.

        The ROM argument names ``physical slot - 1``. It unlinks that slot,
        clears its depth key and both link/state words, and deliberately leaves
        picture/H/V for the caller to clear or replace.
        """
        slot = (physical_slot_minus_one + 1) & LINK_MASK
        self.unlink(slot)
        if slot < len(self.depth_key):
            self.depth_key[slot] = 0
        self.link[slot] = 0
        self.state_link[slot] = 0

    def move_slot(self, src: int, dst: int) -> None:
        """``move_mob_slot`` (0x5DE0A): relocate a record to a new cell.

        Order matters and is the ROM's: link the destination **first**, while
        its picture still says whether anything already lives there (the
        ``moblist_insert`` guard), then copy the five words, then unlink and
        clear the source. This is how anything in the maze "moves" -- a
        monster (``monster_loop_core`` 0x410B0), a pushed movable wall
        (``failed_door_post`` 0x42802) and a live hero
        (``player_try_move_core`` 0x42520) all end here: identity is location,
        so moving means changing which slot holds the record.
        """
        self.moblist_insert(dst)

        self.picture[dst] = self.picture[src]
        self.hpos[dst] = self.hpos[src]
        self.vpos[dst] = self.vpos[src]
        self.set_obj_type(dst, self.obj_type(src))
        self.set_state(dst, self.state(src))

        self.unlink_and_clear(src)

    # --- SLIP maintenance ----------------------------------------------------------

    def rebuild_slips(self) -> None:
        """Recompute the 64 cumulative band entry points from the chain.

        Each SLIP points at the first MOB belonging to its band *or a later
        one*, so the hardware can start reading partway down one ordered list.

        The original updates only the affected SLIPs on each insertion or
        removal, walking down from the changed node's band while the entry is
        still empty or still names the displaced node (0x5DD5E-0x5DD6E,
        0x5E03E-0x5E04E). Rebuilding wholesale is O(chain), obviously correct,
        and -- unlike the ROM -- immune to its own quirk of computing the
        removal band from the raw slot rather than the depth key. WP-2 may
        replace it with incremental updates once the renderer is real, but only
        behind this same interface.
        """
        heads = [NULL_SLOT] * NUM_SLIP_BANDS
        marked = 0
        for slot in self.iter_chain():
            band = self.band_of(slot)
            while marked <= band:
                heads[marked] = slot
                marked += 1
            if marked >= NUM_SLIP_BANDS:
                break
        self.slip_heads = heads

    # --- construction ---------------------------------------------------------------

    def create(
        self,
        slot: int,
        tile: int,
        hpos: int,
        vpos: int,
        obj_type: int | MazeObjIds,
        state: int = 0,
        link_into_chain: bool = True,
    ) -> int:
        """``mob_create`` (0x5DC58), argument order per §23.5.

        The chain link happens *before* the picture is written, and
        ``moblist_insert`` bails out unless what is already there is empty or
        the solid-wall marker (0x5DCC0-0x5DCC6). So creating over a live object
        overwrites its record but leaves the chain alone -- the ROM's guard
        against linking one slot twice, and the reason a re-created cell never
        corrupts the list.

        ``link_into_chain=False`` is the marker path: walls, traps and
        forcefield hubs are stamped straight into the five arrays by
        ``maze_place_object`` without ever going through ``mob_create``
        (doc/04 §5.4), so they are never chain members at all.
        """
        linkable = link_into_chain and self.picture[slot] in LINKABLE_PICTURES

        self.picture[slot] = tile
        self.hpos[slot] = hpos
        self.vpos[slot] = vpos
        # 0x5DC94/0x5DCA6 preserve the low ten-bit next/previous links when a
        # live slot is rewritten without being reinserted.
        self.set_obj_type(slot, int(obj_type))
        self.set_state(slot, state)
        if linkable:
            self.insert(slot)
        return slot

    # --- internals -------------------------------------------------------------------

    def __len__(self) -> int:
        return sum(1 for _ in self.iter_chain())
