"""Literal tables and masks shared by the monster ROM routine families."""

from __future__ import annotations

from ..constants import MazeObjIds

# =============================================================================
# Constants and tables
# =============================================================================

# hpos flag bits (§ coords / 04 §3.3): bit 5 moving, bit 4 attacking.
_HPOS_FLAG_MOVING = 0x20
_HPOS_FLAG_ATTACK = 0x10

# ``mazeobj_hsize_tier_tbl`` (0x5864C) rows for the ten creature types -- the
# full-strength health nibble each family spawns with.  Read by
# monster_playerhit at 0x495F4.
_MAZEOBJ_HSIZE_TIER_TBL = {
    int(MazeObjIds.MONST_GHOST): 0x4,
    int(MazeObjIds.MONST_GRUNT): 0x4,
    int(MazeObjIds.MONST_DEMON): 0x8,
    int(MazeObjIds.MONST_LOBBER): 0xB,
    int(MazeObjIds.MONST_SORC): 0xB,
    int(MazeObjIds.MONST_AUX_GRUNT): 0x4,
    int(MazeObjIds.MONST_DEATH): 0x0,
    int(MazeObjIds.MONST_ACID): 0x1,
    int(MazeObjIds.MONST_SUPERSORC): 0xB,
    int(MazeObjIds.MONST_IT): 0x8,
}

# monster_oddangle_table (0x40E1E) -- ten rows of four bytes, indexed by
# monster index.  Byte 1 is the per-family action mask ANDed with the frame
# word (0x413FA/0x41460); bytes 0, 2 and 3 are animation-counter deltas added
# to the state word's high byte by the movement/animation state machine
# (0x411C4/0x41428/0x4149A).
_MONSTER_ODDANGLE_TABLE = (
    (0x0E, 0x06, 0x80, 0x00),   # 0 ghost
    (0x00, 0x06, 0x40, 0x40),   # 1 grunt
    (0x00, 0x06, 0x00, 0x40),   # 2 demon
    (0x00, 0x02, 0x20, 0x00),   # 3 lobber
    (0xFF, 0x06, 0xFF, 0x00),   # 4 sorcerer
    (0x00, 0x06, 0x40, 0x40),   # 5 aux grunt
    (0x00, 0x06, 0x40, 0xE0),   # 6 Death
    (0x00, 0x02, 0x00, 0x00),   # 7 acid
    (0xFF, 0x06, 0xFF, 0x00),   # 8 super sorcerer
    (0x01, 0x02, 0x00, 0x00),   # 9 IT
)

# Direction -> (dx, dy) unit step.  Same 0-7 compass players use
# (players.py: 0=right, 2=down, 4=left, 6=up, odds are the diagonals).
_DIR_DELTAS = {
    0: (1, 0),
    1: (1, 1),
    2: (0, 1),
    3: (-1, 1),
    4: (-1, 0),
    5: (-1, -1),
    6: (0, -1),
    7: (1, -1),
}
#: 0x410FA/0x4148A -- the blank sprite a sorcerer wears while blinked out.
_BLANK_PICTURE = 0x1709


# =============================================================================
# Movement engine (0x4126A) and the ray marches (0x5E10C/0x5E1D8/0x5E2A2/0x5E35E)
# =============================================================================
# The original does not "step and test": it probes each *axis component* of its
# heading with a ray march, keeps the components that came back clear, and only
# then works out which cell the resulting position belongs to.  That is what
# makes a diagonal walker slide along a wall -- one component is refused, the
# other still moves.
#
# Coordinates are the hardware's: the V axis grows *up* the screen, so probe 1
# (towards row 0) adds to the V word and probe 2 subtracts, exactly as the ROM
# writes them.

#: 0x4126E -- two MOBs overlap when both axis separations are inside this.
_OVERLAP = 0x7C0
#: 0x5E1BC etc -- software MOBs (picture bit 15) carry a shifted origin.
_SOFTWARE_MOB_BIAS = 0x200
