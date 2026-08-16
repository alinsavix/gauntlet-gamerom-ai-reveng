"""Maze and level system -- WP-3.

The public entry point is ``load_level(state, level_number)``, called at
level transitions. This package owns no main-loop call -- WP-20 boot will
call ``load_level`` once it exists; nothing calls it today.

Like ``assets.py``, this is a bridge module: it is allowed to import ``gex``
(the sibling ``../python-gex`` project) but must not import any gauntpy
subsystem module. gex already implements the Slapstic ROM reader and the
maze bytecode decompressor -- this module *reuses* both rather than porting
them (PLAN.md WP-3), and adds the game-specific layer gex has no reason to
know about: level selection, level-flag randomization, row-0 wall fill, and
turning decoded tokens into ``MobTable`` records.

Reference: ``doc/04_game_subsystems.md`` section 5; ``doc/06_maze_catalog.md``;
``book/09_mazes_and_slapstic.md``; ``../python-gex/src/gex/{roms,mazedecode}.py``.

Scope note -- find_maze vs. level selection
--------------------------------------------
``doc/04_game_subsystems.md`` section 5.1 is explicit that ``find_maze``
(0x40C78) "Maps maze number -> data pointer + slapstic bank" -- it takes a
*maze number*, not a level number, and the 117-maze table in
``doc/06_maze_catalog.md`` has no level column (there is no fixed
level -> maze relationship past level 5; "the level -> maze mapping is
cabinet state, not a formula", doc/06 section 3). The much larger,
EEPROM-backed rotation algorithm that actually picks *which* maze number
plays as level 6 and beyond lives in ``player_exit_sequence`` (0x52B40) and
``maze_checknum`` (0x52ECA) -- both explicitly assigned to WP-15 in
``PLAN.md`` section 6 ("Exits, treasure rooms, secret rooms"), not WP-3, and
the resume-position write lives in ``main_health_countdown`` (WP-6).

So ``find_maze`` here is deliberately the narrow thing the doc describes:
maze number -> (bank, address). ``maze_for_level`` below implements only the
one *fixed* rule doc/06 section 3.1 documents (levels 1-5 -> mazes 0-4);
for level 6 and up, ``load_level`` trusts ``state.mazenum_current`` to have
already been set by whichever package computes the rotation. This is a
deliberate scope decision, not an oversight -- flagged here rather than
silently porting a level->maze formula the doc says does not exist.
"""

from __future__ import annotations

import struct
from typing import NamedTuple

from gex.constants import (
    LFLAG4_TRAPS_LOCAL,
    LFLAG4_WRAP_H,
    LFLAG4_WRAP_V,
    MAX_MAZE_NUM,
)
from gex.mazedecode import Maze, maze_decompress
from gex.roms import (
    GexError,
    coderom_get_bytes,
    slapstic_maze_get_bank,
    slapstic_maze_get_real_addr,
    slapstic_read_maze,
)

from . import coords
from .constants import FIRST_PLAYABLE_SLOT, GameMode, MazeObjIds
from .state import GameState

__all__ = [
    "MazeError",
    "MazeLocation",
    "find_maze",
    "decode_maze",
    "maze_for_level",
    "maze_place_object",
    "place_decoded_objects",
    "get_random_maze_flags",
    "maze_load_pickup_config",
    "load_level",
]


class MazeError(Exception):
    """Something WP-3 could not satisfy: an out-of-range maze/level number
    or a gex-level decode failure. Mirrors ``assets.py``'s ``AssetError``
    pattern -- callers of this module never need to catch gex's own
    ``GexError``.
    """


# ---------------------------------------------------------------------------
# find_maze (0x40C78) and maze decode -- thin wrappers over gex
# ---------------------------------------------------------------------------

class MazeLocation(NamedTuple):
    """``find_maze``'s result: which Slapstic bank holds the record, and its
    normalized address within the 32 KiB image (doc/06 sections 1-2).
    """

    bank: int
    addr: int


def find_maze(maze_number: int) -> MazeLocation:
    """``find_maze`` (0x40C78): maze number -> Slapstic bank + data pointer
    (doc/04 section 5.1). See the module docstring's "Scope note" -- this
    maps a *maze number*, not a level.

    Delegates entirely to gex, which already implements the 2-bit bank
    lookup table (0x39FE0) and the 117-entry pointer table (0x3800C),
    normalized into the interleaved 32 KiB image (doc/06 sections 1-2).
    """
    if not (0 <= maze_number <= MAX_MAZE_NUM):
        raise MazeError(f"maze number {maze_number} out of range 0..{MAX_MAZE_NUM}")
    try:
        bank = slapstic_maze_get_bank(maze_number)
        addr = slapstic_maze_get_real_addr(maze_number)
    except GexError as exc:
        raise MazeError(f"could not resolve maze {maze_number}: {exc}") from exc
    return MazeLocation(bank, addr)


def decode_maze(maze_number: int) -> Maze:
    """Read and decompress one maze record: ``find_maze``'s pointer feeds
    ``maze_decode`` (0x4C1BC) in the original; here both steps are gex calls
    (``slapstic_read_maze`` + ``maze_decompress``), never ported.

    Maze 116 has no trailing zero delimiter -- its stream runs into the bank
    lookup table at the end of the 32 KiB image (doc/06 section 8) -- so it
    is decoded with ``allow_missing_delimiter``, matching gex's own CLI
    (``gex/maze.py`` ``domaze``).
    """
    if not (0 <= maze_number <= MAX_MAZE_NUM):
        raise MazeError(f"maze number {maze_number} out of range 0..{MAX_MAZE_NUM}")
    try:
        compressed = slapstic_read_maze(maze_number)
        return maze_decompress(compressed, allow_missing_delimiter=maze_number == MAX_MAZE_NUM)
    except GexError as exc:
        raise MazeError(f"could not decode maze {maze_number}: {exc}") from exc


# ---------------------------------------------------------------------------
# Level -> maze selection -- the opening act only (see "Scope note" above)
# ---------------------------------------------------------------------------

def maze_for_level(level_number: int) -> int | None:
    """The one *fixed* level -> maze rule: levels 1-5 always play mazes 0-4,
    in that order (doc/06 section 3.1; ``book/09`` "Choosing the next
    maze"). Returns ``None`` for any other level number -- from level 6 on,
    the maze number is cabinet-rotation state, not a function of the level
    number alone (see module docstring "Scope note").
    """
    if 1 <= level_number <= 5:
        return level_number - 1
    return None


# ---------------------------------------------------------------------------
# maze_place_object (0x45E40) and MobTable population
# ---------------------------------------------------------------------------

def maze_place_object(state: GameState, start_slot: int, object_type: int, count: int) -> int:
    """``maze_place_object`` (0x45E40): create ``count`` MOBs of
    ``object_type`` at consecutive slots starting at ``start_slot``,
    returning the next slot (doc/04 section 5.4;
    ``doc/generated/maze_contracts.csv`` row for 0x45E40: "uint16 next slot
    in D0.l"). The original returns this in D0.l; here it is a normal
    Python return.

    Used both for individual decoded tokens (``count`` always 1 -- gex's
    decoder has already expanded runs into individual cells, see
    ``place_decoded_objects``) and, critically, for ``maze_setupnew``'s
    row-0 fill (``load_level`` below calls this with
    ``count=FIRST_PLAYABLE_SLOT`` to stamp slots 0-31 as solid walls).
    """
    for slot in range(start_slot, start_slot + count):
        _create_generic(state, slot, object_type)
    return start_slot + count


def _create_generic(state: GameState, slot: int, object_type: int) -> None:
    """Create one MOB at ``slot`` with geometry only -- no ROM picture
    lookup. See KNOWN GAP below.

    Slot 0 is never linked into the depth chain: ``constants.NULL_SLOT`` is
    0, the chain's own terminator/"empty" sentinel (``mob.py``'s
    ``depth_list_head`` and every ``next``/``prev`` pointer use 0 to mean
    "nothing here"), so inserting a real record *at* slot 0 makes the chain
    unable to tell "list is empty" from "slot 0 is the head" and corrupts
    traversal (confirmed: ``MobTable.insert`` raises "cycle detected"
    immediately). This is exactly the row-0 wall fill's slot range, and it
    lines up with doc/04 section 5.4's own observation that wall/trap/
    forcefield "marker types" write ``mob_picture`` directly rather than
    going through ``mob_create`` -- i.e. the original never chain-links
    slot 0 either, it just gets there by a different, un-ported code path.
    """
    x, y = coords.slot_to_pixels(slot)
    state.mobs.create(
        slot,
        # KNOWN GAP (flagged, not guessed): the real placement picture comes
        # from the master parameter tables at 0x5858C-0x5870B
        # (mazeobj_base_picture_tbl / mazeobj_hsize_tier_tbl /
        # mazeobj_hpos_correction_tbl / mazeobj_vpos_offset_tbl,
        # doc/05_data_reference.md section 5.2), which is out of WP-3's
        # doc-read scope (limited to doc/04 section 5 and doc/06). Object
        # *type* and *position* (this function's actual job, per the task
        # brief) are exact; the *tile*/*picture* number is left 0 until a
        # follow-up work package wires the parameter tables through
        # AssetStore -- see PLAN.md WP-1/WP-2.
        0,
        hpos=coords.encode_hpos(x),
        vpos=coords.encode_vpos(y),
        obj_type=object_type,
        link_into_chain=slot != 0,
    )


def _place_decoded(state: GameState, slot: int, object_type: int) -> None:
    """Apply ``maze_place_object``'s two token-specific special cases
    (doc/04 section 5.4) before falling through to the shared placement
    primitive.
    """
    if object_type == MazeObjIds.MONST_DRAGON:
        # Suppressed (written as empty) when game_mode == 0 and
        # levelnum_current < 12 (and level != 9999) -- dragons never spawn
        # from maze data before level 12 of a normal game (doc/04 sec 5.4).
        suppressed = (
            state.game_mode == GameMode.NORMAL
            and state.levelnum_current < 12
            and state.levelnum_current != 9999
        )
        if suppressed:
            return
    elif object_type == MazeObjIds.FOOD_INVULN:
        # Random variant selection via getrandom(3) from the three-word
        # table at 0x58F20 (doc/04 sec 5.4). The variant only changes the
        # *picture*, which is the KNOWN GAP in _create_generic above -- the
        # draw is still made so the shared RNG stream stays in step with
        # the real game, per PLAN.md's "route randomness through
        # state.getrandom()" rule.
        state.getrandom(3)

    maze_place_object(state, slot, object_type, 1)


def place_decoded_objects(state: GameState, maze: Maze) -> None:
    """Populate ``MobTable`` from gex's decoded ``Maze.data``: slot number
    is the packed cell address, so placement is arithmetic, not a search
    (task brief; doc/04 sections 5.3-5.4).

    gex keys ``Maze.data`` by ``(x, y)`` = ``(col, row)`` -- see
    ``gex.mazedecode.index2xy``. gex's own linear decode cursor is already
    ``row * 32 + col``, which is exactly ``coords.pack_slot(row, col)``, so
    no coordinate translation beyond a swap is needed.

    Row 0 (``row == 0``, i.e. slots 0-31) is skipped: gex's
    ``maze_decompress`` bakes a row-0 wall border directly into
    ``Maze.data`` as a decode-completeness convenience
    (``mazedecode.py``: ``maze.data.update({(i, 0): WALL_REGULAR ...})``
    before its token loop even starts), but the *real* ``maze_decode``
    (0x4C1BC) never emits row 0 at all -- "the tile cursor starts at slot
    0x20 (row 0 is not emitted by this function)", doc/04 section 5.3. That
    row is instead filled by a separate, later call
    (``maze_place_object(0, 2, 0x20)``, doc/04 sections 5.2-5.3), which
    ``load_level`` issues itself below. Placing it here too would
    double-create slots 0-31 -- and for slot 0 specifically, corrupt the
    depth chain, since ``constants.NULL_SLOT`` is 0 and a slot can only be
    chain-linked once (see ``_create_generic``).
    """
    for (col, row), object_type in maze.data.items():
        if row == 0:
            continue
        slot = coords.pack_slot(row, col)
        _place_decoded(state, slot, object_type)


# ---------------------------------------------------------------------------
# maze_load_pickup_config (0x436FE) -- level flags load & randomization
# ---------------------------------------------------------------------------

def _split_flags(longword: int) -> tuple[int, int, int, int]:
    """32-bit level-flags longword -> its 4 big-endian bytes (LFLAG1..4)."""
    longword &= 0xFFFFFFFF
    return (
        (longword >> 24) & 0xFF,
        (longword >> 16) & 0xFF,
        (longword >> 8) & 0xFF,
        longword & 0xFF,
    )


def _join_flags(b1: int, b2: int, b3: int, b4: int) -> int:
    """Inverse of ``_split_flags``."""
    return ((b1 & 0xFF) << 24) | ((b2 & 0xFF) << 16) | ((b3 & 0xFF) << 8) | (b4 & 0xFF)


# get_random_maze_flags (0x436CC): a 13-entry, 4-byte-per-entry ROM table at
# 0x57012 (doc/04 sec 5.5; doc/05_data_reference.md sec 5.2 names the size
# "13 x 4B" but -- out of WP-3's doc-read scope -- does not transcribe the
# values). Per PLAN.md sec 8 ("when the docs and the ROM disagree, the ROM
# wins") and the standing instruction to verify rather than invent, the
# table is read directly from the game ROM via gex's existing generic code
# -ROM reader (never re-derived or hand-copied). Read once and cached --
# it is fixed ROM content, not per-maze state.
_RANDOM_MAZE_FLAGS_ADDR = 0x57012
_RANDOM_MAZE_FLAGS_COUNT = 13
_random_maze_flags_table: tuple[int, ...] | None = None


def _random_maze_flags_table_read() -> tuple[int, ...]:
    global _random_maze_flags_table
    if _random_maze_flags_table is None:
        raw = coderom_get_bytes(_RANDOM_MAZE_FLAGS_ADDR, _RANDOM_MAZE_FLAGS_COUNT * 4)
        _random_maze_flags_table = struct.unpack(f">{_RANDOM_MAZE_FLAGS_COUNT}I", raw)
    return _random_maze_flags_table


def get_random_maze_flags(state: GameState) -> int:
    """``get_random_maze_flags`` (0x436CC): selects a random entry from the
    13-entry ROM table at 0x57012 via ``getrandom(13)``. If LFLAG4 bit 2
    (TrapsLocal) is set and the selected entry is 0x80, overrides to 0x2
    (doc/04 sec 5.5) -- verified directly against the game ROM: entry 1 is
    0x80 (``LFLAG4_PLAYER_OFFSCREEN``) and entry 3 is 0x2
    (``LFLAG4_SHOTS_HURT``), consistent with every other populated entry
    being a single set bit somewhere across LFLAG1/2/4 (e.g. 0x1000000 =
    ``LFLAG1_ODDANGLE_GHOSTS``, 0x10000 = ``LFLAG2_FAST_GHOSTS``).
    """
    table = _random_maze_flags_table_read()
    result = table[state.getrandom(_RANDOM_MAZE_FLAGS_COUNT)]
    if state.level_flags_4 & LFLAG4_TRAPS_LOCAL and result == 0x80:
        result = 0x2
    return result


def maze_load_pickup_config(state: GameState, maze: Maze) -> None:
    """``maze_load_pickup_config`` (0x436FE): assemble the maze header's
    four level-flags bytes into the level-flags longword, then randomize
    (doc/04 sec 5.5; doc/06 sec 4/8).

    gex has already assembled header bytes 1-4 into ``maze.flags``
    (``mazedecode.maze_decompress``: ``struct.unpack(">I", compressed[1:5])``)
    -- this function stores that (as 4 separate bytes, matching the RAM
    layout at 0x90491C-0x90491F: ``wrap_h``/``wrap_v`` below read
    ``level_flags_4`` as a standalone byte exactly like the pre-existing
    field comments in state.py do) and applies the documented
    randomization on top.
    """
    b1, b2, b3, b4 = _split_flags(maze.flags)
    state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4 = b1, b2, b3, b4

    # The whole randomization block is skipped on the level==9999 sentinel and
    # in attract mode (game_mode < 0). ROM 0x4374C-0x43760: cmpi.w #0x270F on
    # levelnum, then tst.w/bge on game_mode -- verified by disassembly. In
    # those cases the base header flags stored above are the final value.
    if state.levelnum_current != 9999 and state.game_mode >= 0:
        # LFLAG1 bits 2-3 (longword bits 26-27) XOR'd with getrandom(4), every
        # level (doc/04 sec 5.5; ROM 0x43764-0x43772).
        state.level_flags ^= (state.getrandom(4) << 2) & 0x0C

        longword = _join_flags(
            state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4
        )

        mazenum = state.mazenum_current
        levelnum = state.levelnum_current

        if 5 <= mazenum <= 101:
            # doc/04 sec 5.5, verified by disassembly at ROM 0x43774-0x437D4:
            # level%400 > 297 -> get_random_maze_flags() then +0x30
            # (WrapV|WrapH) unless LFLAG4 bit 2 (TrapsLocal); > 200 -> random
            # flags only; > 103 -> +0x30 unless TrapsLocal. The >103 TrapsLocal
            # gate (ROM 0x437C8: btst #2,$3(a3); bne) was missing from the
            # earlier reading -- it is the same gate as the >297 tier.
            depth = levelnum % 400
            if depth > 297:
                extra = get_random_maze_flags(state)
                if not (state.level_flags_4 & LFLAG4_TRAPS_LOCAL):
                    extra |= LFLAG4_WRAP_V | LFLAG4_WRAP_H
                longword |= extra
            elif depth > 200:
                longword |= get_random_maze_flags(state)
            elif depth > 103:
                if not (state.level_flags_4 & LFLAG4_TRAPS_LOCAL):
                    longword |= LFLAG4_WRAP_V | LFLAG4_WRAP_H
        elif 104 <= mazenum <= 114:
            # Treasure mazes: a graduated 3-tier threshold on level%160,
            # exactly parallel to the mazes-5-101 rule -- verified by
            # disassembly at ROM 0x437D6-0x4381A. The doc/04 sec 5.5 summary
            # ("level%160 with 0xB0") named only the top tier; the full rule:
            #   > 120 -> 0xB0 (LFLAG4 offscreen + both wraps)
            #   >  80 -> 0x80 (offscreen only)
            #   >  40 -> 0x30 (both wraps)
            #   <= 40 -> nothing
            depth = levelnum % 160
            if depth > 120:
                longword |= 0x80 | LFLAG4_WRAP_V | LFLAG4_WRAP_H  # 0xB0; 0x80 = PLAYER_OFFSCREEN
            elif depth > 80:
                longword |= 0x80  # LFLAG4_PLAYER_OFFSCREEN
            elif depth > 40:
                longword |= LFLAG4_WRAP_V | LFLAG4_WRAP_H  # 0x30

        state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4 = _split_flags(longword)

    # 0x90491F bits 5/4 -- see the pre-existing field comments in state.py.
    state.wrap_h = bool(state.level_flags_4 & LFLAG4_WRAP_H)
    state.wrap_v = bool(state.level_flags_4 & LFLAG4_WRAP_V)


# ---------------------------------------------------------------------------
# load_level -- the public entry point
# ---------------------------------------------------------------------------

def load_level(state: GameState, level_number: int) -> None:
    """Load and set up the maze for ``level_number`` (PLAN.md sec 6 WP-3).
    Owns no main-loop call; called at level transitions -- WP-20 boot will
    wire this in once it exists. Nothing calls this function today.

    Ports ``maze_new_level_setup``'s (0x438AE) decode+setup order (doc/04
    sec 5.2) for the steps that are WP-3's own job:

        4. slapstic_cmd_bitwise bank switch + maze_setupnew(cur_maze_ptr)
           -- here, decode via gex (``decode_maze``).
        5. (folded into the same pass) maze_load_pickup_config.
        6. Populate MobTable from the decoded tokens.
        7. Row-0 fill: maze_place_object(0, 2, 0x20).

    Steps 1-3 and 8-10 of the documented order (thief timer/target reset,
    dragon-encounter flag clear, random treasure-level timer, scroll-to-slot
    camera centering, transporter/exit table scans) touch state that
    belongs to other work packages (WP-9, WP-10, WP-11, WP-13, WP-15, WP-16)
    and does not exist under their GameState headings yet. Ground rule 1
    forbids adding fields to another package's block, so those steps are
    left for those packages to wire in when they land, rather than guessed
    at here.
    """
    state.levelnum_current = level_number

    mazenum = maze_for_level(level_number)
    if mazenum is None:
        # No fixed rule past the opening act (doc/06 sec 3.2) -- trust that
        # the caller (eventually WP-15's exit sequence via WP-20 boot) has
        # already advanced state.mazenum_current. See module docstring
        # "Scope note".
        mazenum = state.mazenum_current
    state.mazenum_current = mazenum

    maze = decode_maze(mazenum)
    state.maze = maze

    maze_load_pickup_config(state, maze)

    # Decode cursor never emits row 0 (doc/04 sec 5.3) -- populate the
    # decoded tokens first, then stamp the reserved row separately, exactly
    # as the original orders it ("Immediately after the decoder returns,
    # maze_setupnew calls maze_place_object(0, 2, 0x20)").
    place_decoded_objects(state, maze)
    maze_place_object(state, 0, MazeObjIds.WALL_REGULAR, FIRST_PLAYABLE_SLOT)
