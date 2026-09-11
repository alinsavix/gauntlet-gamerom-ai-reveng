"""Generator placement and the Super Sorcerer's specialized placement family."""

from __future__ import annotations

from ..constants import SLOT_DEMON_SHOTS, MazeObjIds
from ..coords import POS_SHIFT, encode_hpos, encode_vpos_at_y, native_v, replace_position
from ..state import GameState
from .monster_data import (
    _BLANK_PICTURE,
    _DIR_DELTAS,
    _HPOS_FLAG_ATTACK,
    _HPOS_FLAG_MOVING,
    _MAZEOBJ_HSIZE_TIER_TBL,
    _OVERLAP,
    _SOFTWARE_MOB_BIAS,
)
from .monster_shooting import (
    _find_target_player,
    find_unused_shot,
    monster_create_shot,
)
from .monster_state import (
    _aim_direction,
    _anim_add_high,
    _anim_advance,
    _delta_units,
    _get_direction,
    _s16,
    _set_direction,
    _signed_byte,
    monster_update_anim_tile,
)

# Spawn probability out of 32 (§3.4).  ``monster_spawn_probability_table``
# lives at **0x40E46** (32 bytes, transcribed literally below), not 0x57A08:
# monsters_everything indexes it with ``((game_settings & 0xE0) >> 3) +
# level_players_active - 1`` (0x40F5C-0x40F7E), which spans 0-31 -- eight
# difficulty steps x four player counts.
_MONSTER_SPAWN_PROBABILITY_TABLE = [
    0x04, 0x0B, 0x0F, 0x12,   # difficulty 0, 1-4 players
    0x06, 0x0D, 0x11, 0x14,   # difficulty 1
    0x08, 0x0F, 0x13, 0x16,   # difficulty 2
    0x0A, 0x11, 0x15, 0x18,   # difficulty 3
    0x0C, 0x13, 0x17, 0x1A,   # difficulty 4
    0x0E, 0x15, 0x19, 0x1C,   # difficulty 5
    0x10, 0x17, 0x1B, 0x1E,   # difficulty 6
    0x12, 0x19, 0x1D, 0x20,   # difficulty 7
]

# Which generator type spawns which creature.  Generators come in three tiers
# each (28-45); the spawned creature is fixed by family.
_GENERATOR_SPAWN = {
    int(MazeObjIds.GEN_GHOST1): int(MazeObjIds.MONST_GHOST),
    int(MazeObjIds.GEN_GHOST2): int(MazeObjIds.MONST_GHOST),
    int(MazeObjIds.GEN_GHOST3): int(MazeObjIds.MONST_GHOST),
    int(MazeObjIds.GEN_GRUNT1): int(MazeObjIds.MONST_GRUNT),
    int(MazeObjIds.GEN_GRUNT2): int(MazeObjIds.MONST_GRUNT),
    int(MazeObjIds.GEN_GRUNT3): int(MazeObjIds.MONST_GRUNT),
    int(MazeObjIds.GEN_DEMON1): int(MazeObjIds.MONST_DEMON),
    int(MazeObjIds.GEN_DEMON2): int(MazeObjIds.MONST_DEMON),
    int(MazeObjIds.GEN_DEMON3): int(MazeObjIds.MONST_DEMON),
    int(MazeObjIds.GEN_LOBBER1): int(MazeObjIds.MONST_LOBBER),
    int(MazeObjIds.GEN_LOBBER2): int(MazeObjIds.MONST_LOBBER),
    int(MazeObjIds.GEN_LOBBER3): int(MazeObjIds.MONST_LOBBER),
    int(MazeObjIds.GEN_SORC1): int(MazeObjIds.MONST_SORC),
    int(MazeObjIds.GEN_SORC2): int(MazeObjIds.MONST_SORC),
    int(MazeObjIds.GEN_SORC3): int(MazeObjIds.MONST_SORC),
    int(MazeObjIds.GEN_AUX_GRUNT1): int(MazeObjIds.MONST_AUX_GRUNT),
    int(MazeObjIds.GEN_AUX_GRUNT2): int(MazeObjIds.MONST_AUX_GRUNT),
    int(MazeObjIds.GEN_AUX_GRUNT3): int(MazeObjIds.MONST_AUX_GRUNT),
}

# Starting health nibble per spawned creature -- the same
# ``mazeobj_hsize_tier_tbl`` (0x5864C) rows the contact path reads, which is
# also what WP-7's kill maths uses (ghost/grunt/aux 4, demon 8).
_SPAWN_HEALTH = _MAZEOBJ_HSIZE_TIER_TBL

# ``mazeobj_vpos_offset_tbl`` (0x5860C) rows for the creature types, added
# straight to the new MOB's V word at 0x493B2: bits 5-3 width-1, bits 2-0
# height-1.  Every family is 3x3 tiles bar the lobber, which is 3x2.
_MAZEOBJ_VSIZE = {
    int(MazeObjIds.MONST_GHOST): 0x12,
    int(MazeObjIds.MONST_GRUNT): 0x12,
    int(MazeObjIds.MONST_DEMON): 0x12,
    int(MazeObjIds.MONST_LOBBER): 0x11,
    int(MazeObjIds.MONST_SORC): 0x12,
    int(MazeObjIds.MONST_AUX_GRUNT): 0x12,
    int(MazeObjIds.MONST_DEATH): 0x12,
    int(MazeObjIds.MONST_ACID): 0x12,
    int(MazeObjIds.MONST_SUPERSORC): 0x12,
    int(MazeObjIds.MONST_IT): 0x12,
}

# ``generator_spawn_hpos_correction`` (0x579AE), indexed by the generator's
# family index (``gen_type - GEN_GHOST1``) and *subtracted* from the new
# creature's H word at 0x493E4.  The word lands in the palette nibble, which is
# the creature's health tier, so the three tiers of every generator family spawn
# progressively healthier creatures: -2, -1, 0.
_GENERATOR_TIER_PENALTY = (2, 1, 0)

# ``mazeobj_hpos_correction_tbl`` (0x5858C) is 0x200 for every creature type,
# and 0x493CE bakes it straight into the spawn position: the H word is
# ``(column << 11) - 0x200``, i.e. the 24 px sprite centred in its 16 px cell.
# That is 4 px, exactly what ``maze.placement_geometry`` subtracts for a
# maze-placed creature -- and the clearance test below compares against the
# same biased origin, so the two have to agree or a generator starts blocking
# its own candidate cells.
_SPAWN_HPOS_CORRECTION = 4

# ``monster_anim_walk_tbl`` (0x40DB2) -- ten longword pointers, one per creature
# type 0x12-0x1B, each naming a 64-word animation table laid out as eight
# animation frames of eight directions.  Its sibling ``monster_anim_attack_tbl``
# (0x40DDA) holds the attack cycles and is zero for the four families that have
# none (ghost, lobber, super sorcerer, IT).  The shared per-frame picture writer
# at 0x414A4-0x414B8 indexes the selected table with ``(state_byte & 0xFC) >> 1``
# -- which is the MOB state word itself, animation counter in bits 5-3 and
# direction in bits 2-0.
#
# A generator's spawn takes the same table but reaches it the short way
# (0x493E8-0x49412): the new creature's state word is the direction alone, so
# its picture is animation frame 0 of that direction.  Those are the eighty
# words below, transcribed from the tables the pointers name -- the reason a
# freshly generated creature has real artwork from the very first frame it is
# drawn.  gex resolves every one of them, and the entity/direction it names for
# each is an independent check on the ROM compass: entry 0 is "up", 2 "right",
# 4 "down", 6 "left".
_MONSTER_WALK_PICTURES = {
    int(MazeObjIds.MONST_GHOST):                                     # 0x58F26
        (0x0890, 0x086C, 0x0848, 0x0824, 0x0800, 0x0900, 0x08D8, 0x08B4),
    int(MazeObjIds.MONST_GRUNT):                                     # 0x58FA6
        (0x0A5A, 0x0A3F, 0x0A1B, 0x0A00, 0x09E1, 0x0AB4, 0x0A90, 0x0A75),
    int(MazeObjIds.MONST_DEMON):                                     # 0x590A6
        (0x1990, 0x1963, 0x1909, 0x18AB, 0x1851, 0x187E, 0x18D8, 0x1936),
    int(MazeObjIds.MONST_LOBBER):                                    # 0x591A6
        (0x1BCD, 0x1BAB, 0x1B8D, 0x1B6F, 0x1B51, 0x1C2A, 0x1C0C, 0x1BEB),
    int(MazeObjIds.MONST_SORC):                                      # 0x58C0A
        (0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3),
    int(MazeObjIds.MONST_AUX_GRUNT):                                 # 0x58FA6
        (0x0A5A, 0x0A3F, 0x0A1B, 0x0A00, 0x09E1, 0x0AB4, 0x0A90, 0x0A75),
    int(MazeObjIds.MONST_DEATH):                                     # 0x592A6
        (0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36),
    int(MazeObjIds.MONST_ACID):                                      # 0x59336
        (0x2300, 0x2300, 0x2300, 0x2300, 0x2300, 0x2300, 0x2300, 0x2300),
    int(MazeObjIds.MONST_SUPERSORC):                                 # 0x58C0A
        (0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3),
    int(MazeObjIds.MONST_IT):                                        # 0x59436
        (0x2600, 0x2600, 0x2600, 0x2600, 0x2600, 0x2600, 0x2600, 0x2600),
}

# ``generator_spawn_col_delta`` (0x57B50), ``generator_spawn_row_delta``
# (0x57B68) and ``generator_spawn_direction`` (0x57B80): three parallel word
# tables of *twelve* entries each.  Entries 0-7 are the eight candidate cells in
# the ROM's order -- up, right, down, left, then the four diagonals -- and 8-11
# repeat 0-3.  That tail is what makes the scan a rotation: 0x49320 seeds the
# counter with ``getrandom(4)`` and 0x4942C-0x49438 runs it to ``start + 7``
# with no masking at all, so the four cardinals are always tried first,
# cyclically from a random one, then the four diagonals, and any cardinal the
# random start skipped comes back round at the very end.
#
# Entries 12-14 are *not* table data: the attract-mode seed of 7 (see
# ``handle_generate``) runs the counter to 14 and each table reads three words
# past its own end, into the head of the next one -- the column table into
# ``generator_spawn_row_delta``, the row table into ``generator_spawn_direction``
# and the direction table into ``monster_shot_spawn_h_offset`` (0x57B98).  They
# are transcribed here as the ROM's real bytes rather than elided, because that
# is what makes the outcome provable: every one of the three column values is a
# multiple of 32 and every one of the row values is under 32, so
# ``generator_candidate_slot``'s masks annihilate all six and the candidate is
# the generator's own cell, which can never be free.  The direction words are
# consequently unreachable; ``monster_walk_picture`` masks them to three bits so
# a hypothetical caller gets a defined answer instead of an exception.
_GENERATOR_CELL_DX = (0, 1, 0, -1, 1, 1, -1, -1, 0, 1, 0, -1, -0x20, 0, 0x20)
_GENERATOR_CELL_DY = (-0x20, 0, 0x20, 0, -0x20, 0x20, 0x20, -0x20,
                      -0x20, 0, 0x20, 0, 0, 2, 4)
#: The ROM-compass code (0=north) written into the spawned creature's state
#: word.  gauntpy's compass is the ROM's minus two -- see ``_write_direction``.
_GENERATOR_SPAWN_DIRECTION = (0, 2, 4, 6, 1, 3, 5, 7, 0, 2, 4, 6, 0x200, 0x500, 0x600)
#: 0x49312's ``getrandom`` bound, and the eight tries of 0x49434.
_GEN_START_BOUND = 4
_GEN_CANDIDATE_COUNT = 8
#: 0x492F8/0x492FC -- attract mode does not draw for the rotation start at all.
#: The three ghost-generator families seed it at 7, every other family at 2.
_GEN_ATTRACT_START_GHOST = 7
_GEN_ATTRACT_START_OTHER = 2
#: 0x492EE-0x492F6 -- the family indices that take the 7 seed.
_GEN_ATTRACT_GHOST_FAMILIES = range(0, 3)

# ``tile_occupancy_test`` (0x48F12).  A candidate cell has to sit strictly
# inside the maze proper (0x48F24/0x48F30), and so does each neighbour it
# probes (0x48F94/0x48F9C).
_OCCUPANCY_MIN_SLOT = 0x20
_OCCUPANCY_MAX_SLOT = 0x400

# ``tile_neighbour_col_delta`` (0x578A2) / ``tile_neighbour_row_delta``
# (0x578B2) -- the eight cells around a candidate, left/right first.  Unlike the
# generator's own offsets the row term is *not* masked (0x48F76-0x48F92 adds it
# straight onto ``slot & 0x3E0``), so a neighbour that would fall off the top or
# bottom of the maze fails the range check instead of wrapping.
_SPAWN_CANDIDATE_COLUMN_DELTA = (-1, 1, 0, 0, 1, 1, -1, -1)
_SPAWN_CANDIDATE_ROW_DELTA = (0, 0, -0x20, 0x20, -0x20, 0x20, 0x20, -0x20)


# =============================================================================
# Generators (§3.4)
# =============================================================================

def _handle_generator(state: GameState, slot: int, obj_type: int,
                      frame_word: int) -> None:
    """0x41026 -- turn-staggered generator: one spawn attempt per 16 frames.

    The stagger is ``((slot*2 | 2) ^ frame_word) & 0x1E`` and a zero
    probability short-circuits before the random draw (0x4103E), so a throttled
    generator does not disturb the RNG sequence.
    """
    if ((((slot * 2) | 2) ^ frame_word) & 0x1E) != 0:
        return
    probability = _spawn_probability(state)
    if probability == 0:
        return
    handle_generate(state, slot, obj_type, probability)


def _spawn_probability(state: GameState) -> int:
    """Spawn probability out of 32 (§3.4); zero while frame_overflow is set.

    ``monster_spawn_probability_table`` (0x40E46) is indexed by
    ``((game_settings & 0xE0) >> 3) + level_players_active - 1``, then biased by
    the signed ``monster_spawn_probability_bonus`` byte and capped at twice the
    level number on every level but 1 (0x40F82-0x40F9E).
    """
    if state.frame_overflow:
        return 0
    idx = ((state.game_settings & 0xE0) >> 3) + state.level_players_active - 1
    idx = max(0, min(idx, len(_MONSTER_SPAWN_PROBABILITY_TABLE) - 1))
    prob = _MONSTER_SPAWN_PROBABILITY_TABLE[idx] + _signed_byte(state.monster_spawn_probability_bonus)
    level = state.levelnum_current
    if level != 1:
        prob = min(prob, level * 2)
    return max(0, prob)


def handle_generate(state: GameState, gen_slot: int, gen_type: int,
                    probability: int) -> None:
    """0x492C0 -- one generator spawn attempt.

    Two ways in.  In gameplay (0x49300) the probability draw comes first:
    ``getrandom(0x20)`` loses to the level's spawn probability or nothing
    happens, and the winner then draws ``getrandom(4)`` for the rotation start.
    In attract mode (0x492E2, taken on a negative ``game_mode``) there is no
    randomness at all: ``monster_generation_retry_timer`` counts down and only a
    turn that drives it negative attempts anything, after which it is clamped to
    zero so every later turn does.  The start is then fixed -- 7 for the three
    ghost-generator families, 2 for everything else -- which is how the demo
    stays reproducible frame for frame.

    Either way the scan walks eight candidate cells (0x49320-0x49438): the four
    cardinals cyclically from the start, then the four diagonals, then any
    cardinal the start skipped.  Each is offered to ``tile_occupancy_test``,
    which wants it empty *and* clear of nearby creatures; the first that passes
    takes the creature, facing the direction it was reached from.
    """
    family = gen_type - int(MazeObjIds.GEN_GHOST1)

    if state.game_mode < 0:
        state.monster_generation_retry_timer -= 1
        if state.monster_generation_retry_timer >= 0:
            return
        state.monster_generation_retry_timer = 0
        start = (_GEN_ATTRACT_START_GHOST if family in _GEN_ATTRACT_GHOST_FAMILIES
                 else _GEN_ATTRACT_START_OTHER)
    else:
        if state.getrandom(32) >= probability:
            return   # the random draw wins: no spawn this turn
        start = state.getrandom(_GEN_START_BOUND)

    monster_type = _GENERATOR_SPAWN.get(gen_type)
    if monster_type is None:
        return

    for index in range(start, start + _GEN_CANDIDATE_COUNT):
        dest = generator_candidate_slot(gen_slot, index)
        if not tile_occupancy_test(state, dest):
            continue
        _spawn_monster(state, dest, monster_type, gen_type,
                       _GENERATOR_SPAWN_DIRECTION[index])
        return


def monster_walk_picture(monster_type: int, direction: int) -> int:
    """The walk-table frame a creature of ``monster_type`` faces ``direction``
    with -- 0x414A4-0x414B8's lookup at animation frame 0.

    ``direction`` is the gauntpy compass stored in the MOB state word
    (0=right); the ROM's tables are indexed by its own compass, which is two
    steps round (0=up), so the conversion is ``_write_direction``'s in reverse.
    """
    row = _MONSTER_WALK_PICTURES[monster_type]
    return row[(direction + 2) & 0x07]


def generator_candidate_slot(gen_slot: int, index: int) -> int:
    """0x49326-0x49354 -- the ``index``-th candidate cell around a generator.

    Both axes are masked (``andi #0x3E0`` on the row, ``andi #0x1F`` on the
    column), so this step wraps at *both* maze seams: a generator on row 0
    offers row 31 as its "up" candidate, and one on column 31 offers column 0
    as its "right" candidate.  The clearance test that follows is what then
    decides whether the wrapped cell is actually usable.
    """
    row = ((gen_slot & 0x3E0) + _GENERATOR_CELL_DY[index]) & 0x3E0
    col = (gen_slot + _GENERATOR_CELL_DX[index]) & 0x1F
    return row + col


def _rendered_occupant(state: GameState, cell: int) -> tuple[int, int]:
    """``(record slot, picture)`` of whatever is drawn in ``cell``."""
    return cell, state.mobs.picture[cell]


def tile_occupancy_test(state: GameState, slot: int) -> bool:
    """``tile_occupancy_test`` (0x48F12) -- may something be placed in ``slot``?

    Three conditions, in the ROM's order:

    * the cell is strictly inside the maze -- ``> 0x20`` and ``< 0x400``, so
      the top wall row and anything past the last row are refused outright;
    * nothing is drawn in it (``tst.w mob_picture[slot]``, 0x48F38);
    * none of the eight surrounding cells holds a *rendered* MOB within 0x7C0
      position units on **both** axes (0x48F68-0x49024).

    That last test is a pixel-proximity test, not cell occupancy: the eight
    neighbours are merely the cells whose records could be close enough.  A
    creature that has walked most of the way out of the cell above is still
    within range and still blocks, while one sitting squarely in it is not --
    0x7C0 is a hair under one 16 px cell.  The candidate's own origin carries
    the 0x200 sprite-centering correction every creature is placed with, and a
    software MOB neighbour (picture bit 15) has its own 0x200 taken back off
    (0x48FD8) so both sides are measured from the same edge.

    In the hardware's own words all of those distances are the ROM's literal
    constants, exactly as ``_OVERLAP``/``_SOFTWARE_MOB_BIAS`` already are for
    the ray march, and the separations are taken modulo the maze: the position
    words span exactly one maze in 16 bits, so the subtraction wraps at the
    seam on its own.
    """
    if not _OCCUPANCY_MIN_SLOT < slot < _OCCUPANCY_MAX_SLOT:
        return False
    if _rendered_occupant(state, slot)[1]:
        return False

    candidate_h = (((slot & 0x1F) << 11) - _SOFTWARE_MOB_BIAS) & 0xFFFF
    candidate_v = (native_v(((slot >> 5) & 0x1F) * 16) << POS_SHIFT) & 0xFFFF

    for index in range(8):
        neighbour = ((slot & 0x3E0) + _SPAWN_CANDIDATE_ROW_DELTA[index]
                     + ((slot + _SPAWN_CANDIDATE_COLUMN_DELTA[index]) & 0x1F))
        if not _OCCUPANCY_MIN_SLOT < neighbour < _OCCUPANCY_MAX_SLOT:
            continue
        occupant, picture = _rendered_occupant(state, neighbour)
        if not picture:
            continue
        delta_h = _s16(state.mobs.hpos[occupant] - candidate_h)
        if picture & 0x8000:
            delta_h -= _SOFTWARE_MOB_BIAS
        if abs(delta_h) > _OVERLAP:
            continue
        if abs(_s16(state.mobs.vpos[occupant] - candidate_v)) <= _OVERLAP:
            return False
    return True


def _spawn_monster(state: GameState, slot: int, monster_type: int,
                   gen_type: int, rom_direction: int) -> None:
    """0x4936A-0x49424 -- ``mob_create`` the new creature.

    Picture, position, size, health tier and heading all come out of the ROM's
    own argument build: the picture is the family's walk frame for the chosen
    direction (0x40DB2 via 0x4940E); the H word is the cell's origin less the
    0x200 sprite correction, with ``mazeobj_hsize_tier_tbl`` in the palette
    nibble and the generator's tier penalty (0x579AE) taken back off it, so a
    tier-1 generator's creature starts two notches below full health; the V word
    carries ``mazeobj_vpos_offset_tbl``'s packed size; and the state word carries
    the direction the candidate was reached from, which is what makes a new
    creature walk *away* from its generator -- and is the same field the
    per-frame picture writer reads, so art and heading cannot disagree.
    """
    direction = (rom_direction - 2) & 0x07
    x = (slot & 0x1F) * 16 - _SPAWN_HPOS_CORRECTION
    y = ((slot >> 5) & 0x1F) * 16
    penalty = _GENERATOR_TIER_PENALTY[
        (gen_type - int(MazeObjIds.GEN_GHOST1)) % len(_GENERATOR_TIER_PENALTY)
    ]
    health = max(0, _SPAWN_HEALTH.get(monster_type, 4) - penalty)
    size = _MAZEOBJ_VSIZE.get(monster_type, 0x12)
    state.mobs.create(
        slot,
        tile=monster_walk_picture(monster_type, direction),
        hpos=encode_hpos(x, palette=health, flags=0),
        vpos=encode_vpos_at_y(y, ((size >> 3) & 0x07) + 1, (size & 0x07) + 1),
        obj_type=monster_type,
        state=direction,
    )


# =============================================================================
# Super Sorcerer placement (0x5FDE0)
# =============================================================================

# Direction biases and required clear runs behind a player, from the parallel
# tables ``supersorc_direction_bias`` (0x5FDAC) and ``supersorc_probe_steps``
# (0x5FDB2) -- {0, -1, +1} and {4, 3, 3} (§3.3).
_SUPERSORC_DIRECTION_BIAS = (0, -1, 1)
_SUPERSORC_PROBE_STEPS = (4, 3, 3)
# Proximity rejection (0x5FF06/0x5FF1C): a destination is refused when another
# MOB sits within 0x7C0 *position units* of it on both axes -- a hair under one
# 16-pixel cell.
_SUPERSORC_PROXIMITY = 0x7C0
# ``tile_on_screen_d4`` (0x5E57E): every probed cell has to be on screen.
# 0x6C00 and 0x7000 position units are 216 and 224 pixels; the vertical test is
# against ``scroll_vpos_origin = (0x108 - pf_vscroll_lo) << 7`` (0x46FCE).
# In downward world Y, a cell is visible at ``scroll <= y <= scroll+224``.
_ONSCREEN_H_SPAN = 0x6C00 >> POS_SHIFT
_ONSCREEN_V_SPAN = 0x7000 >> POS_SHIFT


def tile_on_screen_d4(state: GameState, slot: int) -> bool:
    """``tile_on_screen_d4`` (0x5E57E) -- is this cell inside the viewport?"""
    dx = ((slot & 0x1F) * 16 - state.scroll_x) & 0x1FF
    if dx > _ONSCREEN_H_SPAN:
        return False
    dy = ((slot >> 5) * 16 - state.scroll_y) & 0x1FF
    return dy <= _ONSCREEN_V_SPAN


def _supersorc_dispatch(state: GameState, slot: int, frame_word: int) -> None:
    """0x4106A -- the Super Sorcerer's four-phase cycle.

    It fades out, teleports behind a hero, fades back in and throws a fireball
    down a demon shot channel, each phase released by a wrap of the same
    animation counter every other family uses.
    """
    hpos = state.mobs.hpos[slot]
    moving = hpos & _HPOS_FLAG_MOVING
    attack = hpos & _HPOS_FLAG_ATTACK

    if moving and attack:                       # 0x41078: blinked out -- jump
        if (((slot * 2) | 2) ^ frame_word) & 0x1E:
            return
        dest = supersorc_place(state, slot)
        if dest is None:
            return
        _anim_add_high(state, dest, 0xE0)       # 0x410B8
        state.mobs.hpos[dest] &= ~(_HPOS_FLAG_MOVING | _HPOS_FLAG_ATTACK)
        monster_update_anim_tile(
            state, dest, int(MazeObjIds.MONST_SUPERSORC),
        )
        return

    if moving:                                  # 0x410D4: fade out
        if frame_word & 6:
            return
        if not _anim_advance(state, slot):
            return
        state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK
        state.mobs.hpos[slot] &= ~_HPOS_FLAG_MOVING
        state.mobs.picture[slot] = _BLANK_PICTURE
        return

    if attack:                                  # 0x41104: fade back in
        if frame_word & 0xE:
            return
        if not _anim_advance(state, slot):
            return
        state.mobs.hpos[slot] |= _HPOS_FLAG_MOVING
        return

    if frame_word & 0x1E:                       # 0x4112C: idle, then fire
        return
    if not _anim_advance(state, slot):
        return
    _supersorc_shoot(state, slot)


def _supersorc_shoot(state: GameState, slot: int) -> None:
    """0x41142 -- the Super Sorcerer borrows a demon channel for its bolt."""
    shot_slot = find_unused_shot(state, SLOT_DEMON_SHOTS)
    if shot_slot is None:
        _anim_add_high(state, slot, 0x80)       # 0x4114C: try again sooner
        return
    monster_create_shot(state, slot, _get_direction(state, slot), shot_slot)
    state.mobs.hpos[shot_slot] |= _HPOS_FLAG_ATTACK      # 0x41178
    _anim_add_high(state, slot, 0x40)                     # 0x4117E
    state.mobs.hpos[slot] |= _HPOS_FLAG_MOVING
    state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK


def supersorc_place(state: GameState, slot: int) -> int | None:
    """Relocate the Super Sorcerer behind a player (§3.3, 0x5FDE0).

    Tries all four players cyclically from a random start, skipping inactive
    ones.  For each it tests three directions behind that player's facing
    (biases {0,-1,+1}) requiring clear runs of {4,3,3} on-screen empty cells,
    staying within rows 1-31, and rejects a destination crowded by another MOB.
    On the first success it relocates the creature and turns it back towards
    the player and returns its new slot; otherwise it stays put and returns
    None.
    """
    start = state.getrandom(4)
    for i in range(4):
        pi = (start + i) & 3
        p = state.players[pi]
        if not p.active:
            continue

        # 0x5FE1A reads active_mob_ids directly. A hero's corrected sprite
        # origin is four pixels left of that slot and must not be quantized back.
        prow, pcol = p.mob_slot >> 5, p.mob_slot & 0x1F
        behind = (p.direction + 4) & 0x07

        for bias, run in zip(_SUPERSORC_DIRECTION_BIAS, _SUPERSORC_PROBE_STEPS):
            direction = (behind + bias) & 0x07
            dest = _supersorc_candidate(state, slot, prow, pcol, direction, run)
            if dest is not None:
                # 0x5FF48: it arrives facing back down the probe line, i.e. at
                # the player it just materialised behind.
                _supersorc_relocate(state, slot, dest, (direction + 4) & 0x07)
                return dest if state.mobs.picture[dest] else slot
    # No valid destination: re-aim at the nearest player and stay put.  The
    # Super Sorcerer's own aim uses ``apply_direction_from_delta`` (0x41B7E),
    # whose threshold is a fixed 0x400 position units -- 8 pixels, i.e. 4 of
    # the 2-pixel units the picker works in.
    target = _find_target_player(state, slot)
    if target >= 0:
        tp = state.players[target]
        dx = _delta_units(state.mobs.hpos[tp.mob_slot], state.mobs.hpos[slot])
        dv = _delta_units(state.mobs.vpos[tp.mob_slot], state.mobs.vpos[slot])
        _set_direction(state, slot, _aim_direction(dx, dv, 0, 4))
    return None                              # 0x5FF8C: nowhere to go


def _supersorc_candidate(state: GameState, slot: int, prow: int, pcol: int,
                         direction: int, run: int) -> int | None:
    """The cell ``run`` steps from (prow, pcol) along ``direction`` if the whole
    run is clear, on screen, inside rows 1-31, and uncrowded; else None.

    The column wraps (``andi #0x1F`` at 0x5FE60) while the row is a hard bound:
    the slot has to stay in [0x20, 0x400).
    """
    step_x, step_y = _DIR_DELTAS[direction]
    r, c = prow, pcol
    for _ in range(run):
        r += step_y
        c = (c + step_x) & 0x1F
        if not 1 <= r <= 31:
            return None
        cell = (r << 5) | c
        if cell != slot and _cell_blocked(state, cell):
            return None
        if not tile_on_screen_d4(state, cell):
            return None
    dest = (r << 5) | c
    if _supersorc_too_crowded(state, dest, slot):
        return None
    return dest


def _supersorc_too_crowded(state: GameState, dest: int, self_slot: int) -> bool:
    """True if another MOB sits within the proximity box of ``dest``.

    Walk the eight neighbouring cells (``spawn_candidate_*_delta``,
    0x578A2/0x578B2) and test whichever of them hold a picture, excluding the
    relocating creature's own record.
    """
    dest_h = (((dest & 0x1F) * 16 - 4) << POS_SHIFT) & 0xFFFF
    dest_v = native_v((dest >> 5) * 16) << POS_SHIFT
    row_base = dest & 0x3E0
    for dc, dr in zip(_SPAWN_CANDIDATE_COLUMN_DELTA, _SPAWN_CANDIDATE_ROW_DELTA):
        s = row_base + dr + ((dest + dc) & 0x1F)
        if not 0x20 <= s < 0x400 or s == self_slot:
            continue
        picture = state.mobs.picture[s]
        if picture == 0:
            continue
        delta_h = state.mobs.hpos[s] - dest_h
        if picture & 0x8000:
            delta_h -= 0x200
        if (
            abs(delta_h) <= _SUPERSORC_PROXIMITY
            and abs(state.mobs.vpos[s] - dest_v) <= _SUPERSORC_PROXIMITY
        ):
            return True
    return False


def _supersorc_relocate(state: GameState, slot: int, dest: int,
                        direction: int) -> None:
    """Move the Super Sorcerer's record to ``dest`` and face ``direction``.

    0x5FF2C keeps the low six bits of both position words -- the flags and
    palette/tier or size fields -- and only rewrites the cell part.
    """
    if dest == slot:
        _set_direction(state, slot, direction)
        return
    if state.mobs.is_occupied(dest):
        return
    if state.monster_iter_ptr == slot:      # 0x410A6: keep the walk marker live
        state.monster_iter_ptr = dest
    # 0x5FF2C masks with 0x3F, deliberately clearing low-field bit 6.
    low_h = state.mobs.hpos[slot] & 0x3F
    low_v = state.mobs.vpos[slot] & 0x3F
    x = (dest & 0x1F) * 16 - 4
    y = (dest >> 5) * 16
    state.mobs.move_slot(slot, dest)
    state.mobs.hpos[dest] = replace_position(low_h, encode_hpos(x))
    state.mobs.vpos[dest] = replace_position(
        low_v, encode_vpos_at_y(y),
    )
    _set_direction(state, dest, direction)


#: 0x44A76 -- ``attract_demo_init`` loads ``monster_generation_retry_timer``.
GENERATOR_RETRY_RELOAD = 4


def _cell_blocked(state: GameState, slot: int) -> bool:
    """True when a cell already holds a wall, object, or another MOB."""
    return state.mobs.is_occupied(slot)
