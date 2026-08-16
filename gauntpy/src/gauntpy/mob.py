"""MOB slot table and the shared depth chain.

A "thing in the maze" is one index into five parallel arrays of 16-bit words.
Four of them are the VRAM tables the display hardware reads; the fifth lives in
working RAM and completes the record.

Reference: ``doc/04_game_subsystems.md`` §1.1, §2.1, §24;
``book/08_world_in_memory.md``.

    array           hw?  contents
    picture         yes  tile number (bits 14-0), software flag (bit 15)
    hpos            yes  X (15-6), flags (5-4), palette (3-0)
    vpos            yes  Y (15-6), width-1 (5-3), height-1 (2-0)
    link            yes  object type (15-10), next slot (9-0)
    state_link      no   object state (15-10), previous slot (9-0)

The low ten bits of ``link``/``state_link`` make one doubly linked chain,
sorted by depth. ``depth_list_head`` is the global head (0x9049DE); the 64 SLIP
band heads (0x905F80) enter that *same* chain at different positions -- they
are not 64 independent lists.
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
        # Ordering tie-breakers for the managed low slots (0x904940).
        # These are *not* a second backward-link table.
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
        """World pixel (x, y) of a slot."""
        return coords.decode_hpos(self.hpos[slot])[0], coords.decode_vpos(self.vpos[slot])[0]

    def band_of(self, slot: int) -> int:
        """SLIP band index for a slot.

        Bands measure the *playfield*, not the screen, so a sprite's band does
        not change when the camera scrolls past it.
        """
        y = coords.decode_vpos(self.vpos[slot])[0]
        band = y // SLIP_BAND_PIXELS
        return min(band, NUM_SLIP_BANDS - 1)

    def is_occupied(self, slot: int) -> bool:
        """Whether a slot currently holds an object.

        Because slot number equals cell address, this is the whole of
        "what is in that cell?" -- arithmetic, not a search.
        """
        return self.link[slot] != 0 or self.picture[slot] != 0

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
        """Insert ``slot`` into the depth chain, ordered by vertical band.

        ``depth_key`` records the explicit ordering key supplied by the managed
        low-slot placement wrappers (0x5DF5A-0x5DF9C) and breaks ties among
        them.
        """
        if depth_key is not None and slot < NUM_DEPTH_KEYS:
            self.depth_key[slot] = depth_key

        key = self._sort_key(slot)
        prev = NULL_SLOT
        cur = self.depth_list_head
        while cur != NULL_SLOT and self._sort_key(cur) <= key:
            prev = cur
            cur = self.next_slot(cur)

        self.set_next(slot, cur)
        self.set_prev(slot, prev)
        if cur != NULL_SLOT:
            self.set_prev(cur, slot)
        if prev == NULL_SLOT:
            self.depth_list_head = slot
        else:
            self.set_next(prev, slot)

        self.rebuild_slips()

    def unlink(self, slot: int) -> None:
        """``moblist_remove``: repair links and heads, preserve the record.

        Picture/H/V and the upper type/state bits survive -- callers rely on
        this when temporarily lifting an object out of the chain (the thief
        transition in §25 does exactly that).
        """
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

    def move_slot(self, src: int, dst: int) -> None:
        """``move_mob_slot``: relocate a record to a new cell.

        Inserts the destination, copies the five words, then unlinks and clears
        the source. This is how a monster "moves": identity is location, so
        moving means changing which slot holds the record.
        """
        self.picture[dst] = self.picture[src]
        self.hpos[dst] = self.hpos[src]
        self.vpos[dst] = self.vpos[src]
        self.set_obj_type(dst, self.obj_type(src))
        self.set_state(dst, self.state(src))

        self.insert(dst)
        self.unlink_and_clear(src)

    # --- SLIP maintenance ----------------------------------------------------------

    def rebuild_slips(self) -> None:
        """Recompute the 64 cumulative band entry points from the chain.

        Each SLIP points at the first MOB belonging to its band *or a later
        one*, so the hardware can start reading partway down one ordered list.

        The original updates only the affected SLIPs on each insertion or
        removal. Rebuilding wholesale is O(chain) and obviously correct; WP-2
        may replace it with incremental updates once the renderer is real, but
        only behind this same interface.
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
        """``mob_create`` (0x5DC58), argument order per §23.5."""
        self.picture[slot] = tile
        self.hpos[slot] = hpos
        self.vpos[slot] = vpos
        self.link[slot] = (int(obj_type) & UPPER_MASK) << UPPER_SHIFT
        self.state_link[slot] = (state & UPPER_MASK) << UPPER_SHIFT
        if link_into_chain:
            self.insert(slot)
        return slot

    # --- internals -------------------------------------------------------------------

    def _sort_key(self, slot: int) -> tuple[int, int]:
        band = self.band_of(slot)
        tie = self.depth_key[slot] if slot < NUM_DEPTH_KEYS else 0
        return band, tie

    def __len__(self) -> int:
        return sum(1 for _ in self.iter_chain())
