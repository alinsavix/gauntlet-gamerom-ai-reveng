"""Monsters and generators -- WP-8.

Reference: ``doc/04_game_subsystems.md`` §3 (all of it);
``doc/generated/monster_combat_contracts.csv``; ``book/11_monsters.md``.

Key facts for whoever implements this, all of which are easy to get backwards:

- ``monsters_everything`` walks the chain from ``monster_iter_ptr`` (0x904A60),
  which rotates the entry point each frame so no creature is permanently first.
  The walk runs to completion; it never leaves monsters unprocessed.
- There is **no jump table**. One shared handler (0x4119A) with branches.
- ``D6`` in the original is ``monster_index * 4``, **not** an object type.
  Here it is just ``monster_index = obj_type - MONST_GHOST`` (0-9).
- ``monster_slowmo_timer`` skips the entire pass on even frames -- it is a
  global effect on monsters, not a player debuff.
- Generators are throttled by ``frame_overflow``, which zeroes their spawn
  probability; it does not cap how many monsters are processed.
- The cadence word the whole pass runs on is **not** ``frame_counter`` itself.
  ``monsters_everything`` loads ``d6`` from ``frame_counter`` (0x904006) and
  *doubles* it (0x40EEC) when slow-motion is off; under slow-motion it keeps
  the undoubled value and only runs on odd frames (0x40EE0).  Every ``& 6`` /
  ``& 0x1E`` stagger below is therefore against that derived word, which keeps
  a creature's real-time cadence identical with and without slow-motion.
- A monster or generator outside the **culling rectangle** (0x40FF6-0x4101A) is
  skipped entirely for the frame, and shooters additionally need to be inside
  the smaller ``monster_shooter_in_view`` box (0x41B52).  Both are anchored on
  the origins ``main_move_monsters`` derives from the camera (0x49052).
- The LFLAG1 "odd angle" flags do not change speed: they swap the *aiming*
  routine for a family so it can only face diagonals (0x40E02 + 0x41810).

Design note (movement model). The original moves a monster by relocating its
record to a new cell (``move_mob_slot`` -- "identity is location"), tracking a
pixel position inside ``mob_hpos``/``mob_vpos``. This module keeps that dual
representation and now runs the ROM's own mover: each axis component of the
heading is probed with a ray march (0x5E10C and friends), the components that
came back clear are kept -- which is what makes a diagonal walker slide along a
wall -- and the record is relocated when the resulting position lands in a new
cell. The animation counter in the state word's top three bits drives the
whole thing: creatures hold a pose for eight gated frames, and the *wrap* is
what releases the next step, shot or blink.  A generated creature is created
with the exact walk frame its heading names (``monster_anim_walk_tbl``, 0x40DB2),
so it has real artwork from the frame it appears; choosing the *later* frames of
that cycle, and the palette bank they are drawn through, is the renderer's
(WP-2).
"""

from __future__ import annotations

from ..constants import (
    GENERATOR_TYPES,
    MONSTER_TYPES,
    SLOT_DEMON_SHOTS,
    SLOT_LOBBER_SHOTS,
    MazeObjIds,
    PlayerPower,
)
from ..coords import (
    POS_SHIFT,
    encode_hpos,
    encode_vpos_at_y,
    hpos_x,
    low_field,
    mob_cell_of,
    native_v,
    position_field,
    replace_position,
    vpos_y,
)
from ..state import GameState
from .exits import TRICK_NOUSEINVUL, secret_trick_progress, secret_trick_set
from .players import player_add_score_with_mult
from .score import dialog_first_encounter
from .shots import death_damage_accumulate
from .sound import sound_play as _sound_play


# =============================================================================
# Constants and tables
# =============================================================================

# hpos flag bits (§ coords / 04 §3.3): bit 5 moving, bit 4 attacking.
_HPOS_FLAG_MOVING = 0x20
_HPOS_FLAG_ATTACK = 0x10

# Base per-step movement in pixels; the ROM's 0x80/0x100 words are one and two
# native position pixels.
_MONSTER_SPEED_BASE = 1
_MONSTER_SPEED_FAST = 2

# Slow-motion looping-sound cues (§3.3, refs/soundcmds.csv).  The ROM plays
# 0x38 as the timer passes 0x1E and 0x39 as it reaches 0 (0x40EC0/0x40ED2);
# refs/soundcmds.csv labels 0x38 "End of Slow Motion" and 0x39 "Slow Motion
# Silencer", i.e. the *names* in the CSV are the other way round.  Behaviour
# below follows the ROM.
_SOUND_SLOWMO_SILENCER = 0x38   # fires as the timer passes 0x1E
_SOUND_SLOWMO_END = 0x39        # fires as the timer reaches 0

# Lobber-throw sound (§3.5).
_SOUND_LOBBER_THROW = 0x49

# Contact-hurt feedback, from monster_playerhit (0x49876-0x4988A / 0x4967A).
_SOUND_MONSTER_HIT = 0x1E       # "Monster Hits Player"
_SOUND_GHOST_HIT = 0x1F         # "Ghost Hits Player" (type 18 only)
_SOUND_IT_TAG = 0x35            # "Player Touches IT"
_SOUND_ACID_SLIME = 0x36        # "Acid Puddle Slimes Player"
_HURT_COOLDOWN = 0x12           # hurt_cooldown reload (0x49788)

# Acid acts once every 32 frames: (frame_word & 0x1E) == 0 (0x413E6).
_ACID_RATE_MASK = 0x1E

# Player power bits monster_find_and_shoot reads out of ``player_powers``
# (0x9048E0).  The ROM tests the *high byte* bits 0 and 1 -- word bits 8 and 9
# -- which ``powerup_bit_masks`` (0x59B64) assigns to Invisibility and
# Repulsiveness; ``PlayerPower`` is the ROM-authoritative transcription.
_POWER_INVIS = PlayerPower.INVIS        # not targeted at all (0x4176C/0x417C0)
_POWER_REPULSE = PlayerPower.REPULSE    # fled from instead (0x4185C)
_POWER_ARMOR = PlayerPower.ARMOR        # selects the powered half of a table

# Spawn probability out of 32 (§3.4).  ``monster_spawn_probability_table``
# lives at **0x40E46** (32 bytes, transcribed literally below), not 0x57A08:
# monsters_everything indexes it with ``((game_settings & 0xE0) >> 3) +
# level_players_active - 1`` (0x40F5C-0x40F7E), which spans 0-31 -- eight
# difficulty steps x four player counts.
_SPAWN_PROB_TABLE = [
    0x04, 0x0B, 0x0F, 0x12,   # difficulty 0, 1-4 players
    0x06, 0x0D, 0x11, 0x14,   # difficulty 1
    0x08, 0x0F, 0x13, 0x16,   # difficulty 2
    0x0A, 0x11, 0x15, 0x18,   # difficulty 3
    0x0C, 0x13, 0x17, 0x1A,   # difficulty 4
    0x0E, 0x15, 0x19, 0x1C,   # difficulty 5
    0x10, 0x17, 0x1B, 0x1E,   # difficulty 6
    0x12, 0x19, 0x1D, 0x20,   # difficulty 7
]

# monster_contact_damage_table -- transcribed from ROM 0x57A2E (row76.bin
# offset 0x17A2E), 64 words = 16 rows × 4 character columns (Warrior, Valkyrie,
# Wizard, Elf).  Rows 0-7 are the eight unpowered contact classes; rows 8-15 are
# the powered-player half (lower damage).  Valkyrie (col 1) always takes the
# least, Wizard (col 2) the most.  §3.7.
_MONSTER_CONTACT_DAMAGE_TBL = [
    8, 7, 10, 9,      # class 0
    16, 14, 20, 18,   # class 1
    24, 21, 30, 27,   # class 2
    4, 4, 5, 4,       # class 3
    6, 5, 7, 6,       # class 4
    8, 7, 10, 9,      # class 5
    4, 4, 4, 4,       # class 6
    48, 42, 60, 54,   # class 7
    7, 6, 9, 8,       # class 0 powered
    14, 12, 18, 16,   # class 1 powered
    21, 18, 27, 24,   # class 2 powered
    4, 3, 4, 4,       # class 3 powered
    6, 5, 6, 6,       # class 4 powered
    7, 6, 9, 8,       # class 5 powered
    3, 3, 3, 3,       # class 6 powered
    42, 36, 54, 48,   # class 7 powered
]

# ``mazeobj_hsize_tier_tbl`` (0x5864C) rows for the ten creature types -- the
# full-strength health nibble each family spawns with.  Read by
# monster_playerhit at 0x495F4.
_MAZEOBJ_HSIZE_TIER = {
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

# Per-type damage-row offset, from the 10-way jump table at 0x49620.  The row
# is ``(hpos & 0xF) - mazeobj_hsize_tier_tbl[type] + 2 + offset`` (0x495E8) and
# the damage is ``table[row*4 + character (+0x20 when armored)]`` (0x497CE).
# Lobber (0x49A32, the empty epilogue) and IT (the tagging path) are absent:
# neither deals table damage.
_CONTACT_ROW_OFFSET = {
    int(MazeObjIds.MONST_GHOST): 0,       # 0x49634, and explodes on contact
    int(MazeObjIds.MONST_GRUNT): 3,       # 0x4964C
    int(MazeObjIds.MONST_DEMON): 3,       # 0x49654
    int(MazeObjIds.MONST_SORC): 3,        # 0x4965C
    int(MazeObjIds.MONST_AUX_GRUNT): 3,   # 0x4964C (shares the grunt entry)
    int(MazeObjIds.MONST_DEATH): 4,       # 0x4970A
    int(MazeObjIds.MONST_SUPERSORC): 4,   # 0x4970A (shares Death's entry)
    int(MazeObjIds.MONST_ACID): 5,        # 0x4966E
}

#: Score awarded when the Acid puddle is consumed (0x498BA).
_ACID_CONTACT_SCORE = 0x1E
#: Score awarded for touching IT (0x496E4), plus the stun it applies (0x496DE).
_IT_TAG_SCORE = 0x0A
_IT_TAG_STUN = 0x10
#: death_touch_timer reload values (0x49730/0x49746/0x49752).  Negative means
#: "new contact" to WP-6, which negates it into a countdown.
_DEATH_TOUCH_NEW = -0x10        # 0xFFF0
_DEATH_TOUCH_REFRESH = 0x10
_DEATH_TOUCH_WHILE_ACID = 1
#: Death-damage accumulator rows (0x497A6/0x497AA): row 6 col 0 unarmored, row
#: 14 col 0 armored -- 4 and 3.
_DEATH_DAMAGE_ROW = 0x18
_DEATH_DAMAGE_ROW_ARMORED = 0x38

# ``dialog_first_encounter`` masks -- the "you have now met a ..." box, shown
# once per game.  The value is loaded into A4 alongside the damage row by each
# arm of the 0x49620 jump table (0x49644 ghost, 0x4964E grunt and aux grunt,
# 0x49656 demon, 0x4965E sorcerer, 0x49670 acid, 0x4970C Death and the Super
# Sorcerer) and handed to the dialog at 0x4986A; IT passes its own literal at
# 0x496F4.  A lobber never reaches the call.
_FIRST_ENCOUNTER_MASK = {
    int(MazeObjIds.MONST_GHOST): 0x00000100,
    int(MazeObjIds.MONST_GRUNT): 0x00000200,
    int(MazeObjIds.MONST_AUX_GRUNT): 0x00000200,
    int(MazeObjIds.MONST_DEMON): 0x00000400,
    int(MazeObjIds.MONST_SORC): 0x00001000,
    int(MazeObjIds.MONST_ACID): 0x00008000,
    int(MazeObjIds.MONST_DEATH): 0x00020000,
    int(MazeObjIds.MONST_SUPERSORC): 0x00020000,
}
_IT_ENCOUNTER_MASK = 0x10000000

# Secret-room progress (§10.6).  ``secret_trick_id`` (gex ``trick_tasknum``,
# 0x904065) holds the maze's trick outside a secret room and the challenge
# task inside one, and the per-player progress bytes live at 0x904872.  A
# search of the whole ROM for either address finds exactly two sites inside the
# monster code: the IT tag at 0x496AC and the immune contact path at 0x49892 --
# the dispatcher and the movement engine never touch them.
_TRICK_TASK_WHILE_IT = 0x5C     # exits._CHALLENGE_WHILE_IT; passes on any bump

# =============================================================================
# Culling rectangle (0x49052 origins, 0x40FF6 test, 0x41B52 shooter box)
# =============================================================================
# main_move_monsters derives two origins from the camera:
#     monster_cull_h_origin = (pf_hscroll - 0x17) << 7
#     monster_cull_v_origin = (0xF9 - pf_vscroll_lo) << 7
# and both are stored, and compared against, as native position words.
_CULL_H_BIAS = 0x17
_CULL_V_BIAS = 0xF9
_CULL_WIDTH = 0x7F80        # 255 px across
_CULL_HEIGHT = 0x8380       # 263 px down: a screen-sized box on the camera
# monster_shooter_in_view compares the *high bytes*, i.e. 2-pixel units, and
# rejects the outer margin of that same box.
_VIEW_H_MIN, _VIEW_H_MAX = 0x06, 0x79
_VIEW_V_MIN, _VIEW_V_MAX = 0x08, 0x7F

# monster_level_flag_overrides (0x40E02) -- seven longwords, one per family
# slot, of which only the high byte is used: monsters_everything copies it over
# the high byte of that family's speed longword for every set bit of
# ``level_flags & 0x73`` (0x40F34-0x40F58).  The byte is *not* a speed; it
# selects the aiming routine at 0x41810, which is why the LFLAG1 bits are named
# ODDANGLE_* -- every non-zero value restricts the creature to diagonals.
#   0x80  quadrant-with-threshold picker (0x418EA)
#   0xA0  round the cardinal clockwise to a diagonal (0x418B8)
#   0xC0  round the cardinal counter-clockwise to a diagonal (0x41882)
# Demons (bit 2) and lobbers (bit 3) are masked out of 0x73 and their table
# entries are zero, so they can never be odd-angled.
_ODDANGLE_LEVEL_FLAG_MASK = 0x73
_ODDANGLE_OVERRIDE = {
    int(MazeObjIds.MONST_GHOST): (0x01, 0x80),        # 0x40E02
    int(MazeObjIds.MONST_GRUNT): (0x02, 0xC0),        # 0x40E06
    int(MazeObjIds.MONST_DEMON): (0x04, 0x00),        # 0x40E0A (masked out)
    int(MazeObjIds.MONST_LOBBER): (0x08, 0x00),       # 0x40E0E (masked out)
    int(MazeObjIds.MONST_SORC): (0x10, 0xA0),         # 0x40E12
    int(MazeObjIds.MONST_AUX_GRUNT): (0x20, 0xA0),    # 0x40E16
    int(MazeObjIds.MONST_DEATH): (0x40, 0x80),        # 0x40E1A
}

# monster_shoot_axis_thresholds (0x40D8A) -- ten rows of two words, indexed by
# monster index.  Word 0 feeds the 0x80 odd-angle picker (0x418F2), word 1 the
# default cardinal/diagonal picker (0x41822).  Both are in 2-pixel units.
_SHOOT_AXIS_THRESHOLDS = (
    (8, 1),   # 0 ghost
    (4, 2),   # 1 grunt
    (4, 4),   # 2 demon
    (4, 4),   # 3 lobber
    (4, 2),   # 4 sorcerer
    (4, 2),   # 5 aux grunt
    (4, 1),   # 6 Death
    (0, 0),   # 7 acid
    (4, 2),   # 8 super sorcerer
    (4, 1),   # 9 IT
)

# monster_oddangle_table (0x40E1E) -- ten rows of four bytes, indexed by
# monster index.  Byte 1 is the per-family action mask ANDed with the frame
# word (0x413FA/0x41460); bytes 0, 2 and 3 are animation-counter deltas added
# to the state word's high byte by the movement/animation state machine
# (0x411C4/0x41428/0x4149A).
_MONSTER_ODDANGLE_TBL = (
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

# Shooter range gates, in the 2-pixel units monster_find_and_shoot works in.
_LOBBER_MIN_RANGE = 0x14        # closer than this on both axes: back away (0x41946)
_LOBBER_MAX_RANGE = 0x2C        # further than this on either axis: no throw
_DEMON_MIN_RANGE = 0x10         # 0x41AB6/0x41AD0/0x41AE8
_DEMON_DIAG_SKEW = 0x08         # diagonal shots need |dx|-|dy| under this
# Cells a demon shot may be launched *into* (0x41A72-0x41AAE); anything else
# blocks the shot.  An empty cell always passes.
_DEMON_SHOT_PASSABLE = frozenset({
    int(MazeObjIds.TILE_STUN), int(MazeObjIds.TILE_TRAP1),
    int(MazeObjIds.TILE_TRAP2), int(MazeObjIds.TILE_TRAP3),
    int(MazeObjIds.EXIT), int(MazeObjIds.MONST_ACID),
    int(MazeObjIds.KEY), int(MazeObjIds.POWER_INVIS),
    int(MazeObjIds.POWER_REPULSE), int(MazeObjIds.POWER_REFLECT),
    int(MazeObjIds.POWER_TRANSPORT), int(MazeObjIds.TRANSPORTER),
})

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
_SPAWN_HEALTH = _MAZEOBJ_HSIZE_TIER

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

# Full 64-word animation banks consumed by monster_update_anim_tile (0x414A4).
# The state field supplies ``frame * 8 + ROM direction``.  These are literal
# transcriptions from row76.bin; aliases below mirror the pointer tables at
# 0x40DB2/0x40DDA rather than duplicating shared banks.
_ANIM_GHOST_IDLE = (                                               # 0x58F26
    0x0890, 0x086C, 0x0848, 0x0824, 0x0800, 0x0900, 0x08D8, 0x08B4,
    0x0890, 0x086C, 0x0848, 0x0824, 0x0800, 0x0900, 0x08D8, 0x08B4,
    0x0890, 0x086C, 0x0848, 0x0824, 0x0800, 0x0900, 0x08D8, 0x08B4,
    0x0890, 0x086C, 0x0848, 0x0824, 0x0800, 0x0900, 0x08D8, 0x08B4,
    0x0890, 0x086C, 0x0848, 0x0824, 0x0800, 0x0900, 0x08D8, 0x08B4,
    0x0899, 0x0875, 0x0851, 0x082D, 0x0809, 0x0909, 0x08E1, 0x08BD,
    0x08A2, 0x087E, 0x085A, 0x0836, 0x0812, 0x0912, 0x08EA, 0x08C6,
    0x08AB, 0x0887, 0x0863, 0x083F, 0x081B, 0x091B, 0x08F3, 0x08CF,
)

_ANIM_GRUNT_IDLE = (                                               # 0x58FA6
    0x0A5A, 0x0A3F, 0x0A1B, 0x0A00, 0x09E1, 0x0AB4, 0x0A90, 0x0A75,
    0x0A5A, 0x0A3F, 0x0A1B, 0x0A00, 0x09E1, 0x0AB4, 0x0A90, 0x0A75,
    0x0A5A, 0x0A3F, 0x0A1B, 0x0A00, 0x09E1, 0x0AB4, 0x0A90, 0x0A75,
    0x0A63, 0x0A48, 0x0A24, 0x0A09, 0x09EA, 0x0ABD, 0x0A99, 0x0A7E,
    0x0A6C, 0x0A51, 0x0A2D, 0x0A12, 0x09F3, 0x0AC6, 0x0AA2, 0x0A87,
    0x0A6C, 0x0A51, 0x0A2D, 0x0A12, 0x09F3, 0x0AC6, 0x0AA2, 0x0A87,
    0x0A63, 0x0A48, 0x0A24, 0x0A09, 0x09EA, 0x0ABD, 0x0AAB, 0x0A7E,
    0x0A5A, 0x0A3F, 0x0A1B, 0x0A00, 0x09E1, 0x0AB4, 0x0A90, 0x0A75,
)

_ANIM_DEMON_IDLE = (                                               # 0x590A6
    0x1990, 0x1963, 0x1909, 0x18AB, 0x1851, 0x187E, 0x18D8, 0x1936,
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
    0x1975, 0x1948, 0x18EA, 0x1890, 0x1836, 0x1863, 0x18BD, 0x191B,
    0x196C, 0x193F, 0x18E1, 0x1887, 0x182D, 0x185A, 0x18B4, 0x1912,
    0x196C, 0x193F, 0x18E1, 0x1887, 0x182D, 0x185A, 0x18B4, 0x1912,
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
    0x1987, 0x195A, 0x1900, 0x18A2, 0x1848, 0x1875, 0x18CF, 0x192D,
    0x1990, 0x1963, 0x1909, 0x18AB, 0x1851, 0x187E, 0x18D8, 0x1936,
)

_ANIM_LOBBER_IDLE = (                                              # 0x591A6
    0x1BCD, 0x1BAB, 0x1B8D, 0x1B6F, 0x1B51, 0x1C2A, 0x1C0C, 0x1BEB,
    0x1BCD, 0x1BAB, 0x1B8D, 0x1B6F, 0x1B51, 0x1C2A, 0x1C0C, 0x1BEB,
    0x1BCD, 0x1BAB, 0x1B8D, 0x1B6F, 0x1B51, 0x1C2A, 0x1C0C, 0x1BEB,
    0x1BD3, 0x1BB1, 0x1B93, 0x1B75, 0x1B57, 0x1C30, 0x1C12, 0x1BF1,
    0x1BD3, 0x1BB1, 0x1B93, 0x1B75, 0x1B57, 0x1C30, 0x1C12, 0x1BF1,
    0x1BD9, 0x1BB7, 0x1B99, 0x1B7B, 0x1B5D, 0x1C36, 0x1C18, 0x1BF7,
    0x1BD9, 0x1BB7, 0x1B99, 0x1B7B, 0x1B5D, 0x1C36, 0x1C18, 0x1BF7,
    0x1BD3, 0x1BB1, 0x1B93, 0x1B75, 0x1B57, 0x1C30, 0x1C12, 0x1BF1,
)

_ANIM_SORC_IDLE = (                                                # 0x58C0A
    0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3,
    0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3,
    0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3,
    0x141B, 0x1436, 0x1451, 0x146C, 0x13AB, 0x13C6, 0x13E1, 0x1400,
    0x1424, 0x143F, 0x145A, 0x1475, 0x13B4, 0x13CF, 0x13EA, 0x1409,
    0x1424, 0x143F, 0x145A, 0x1475, 0x13B4, 0x13CF, 0x13EA, 0x1409,
    0x141B, 0x1436, 0x1451, 0x146C, 0x13AB, 0x13C6, 0x13E1, 0x1400,
    0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3,
)

_ANIM_DEATH_IDLE = (                                               # 0x592A6
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
    0x1ACF, 0x1B24, 0x1B09, 0x1AEA, 0x1A7E, 0x1A99, 0x1AB4, 0x1B3F,
    0x1AD8, 0x1B2D, 0x1B12, 0x1AF3, 0x1A87, 0x1AA2, 0x1ABD, 0x1B48,
    0x1AD8, 0x1B2D, 0x1B12, 0x1AF3, 0x1A87, 0x1AA2, 0x1ABD, 0x1B48,
    0x1ACF, 0x1B24, 0x1B09, 0x1AEA, 0x1A7E, 0x1A99, 0x1AB4, 0x1B3F,
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
)

_ANIM_ACID_IDLE = (                                                # 0x59336
    0x2300, 0x2300, 0x2300, 0x2300, 0x2300, 0x2300, 0x2300, 0x2300,
    0x2309, 0x2387, 0x2348, 0x23C6, 0x233F, 0x23BD, 0x237E, 0x25DB,
    0x2312, 0x2390, 0x2351, 0x23CF, 0x2336, 0x23B4, 0x2375, 0x23F3,
    0x231B, 0x2399, 0x235A, 0x23D8, 0x232D, 0x23AB, 0x236C, 0x23EA,
    0x2324, 0x23A2, 0x2363, 0x23E1, 0x2324, 0x23A2, 0x2363, 0x23E1,
    0x232D, 0x23AB, 0x236C, 0x23EA, 0x231B, 0x2399, 0x235A, 0x23D8,
    0x2336, 0x23B4, 0x2375, 0x23F3, 0x2312, 0x2390, 0x2351, 0x23CF,
    0x233F, 0x23BD, 0x237E, 0x25DB, 0x2309, 0x2387, 0x2348, 0x23C6,
)

_ANIM_IT_IDLE = (                                                  # 0x59436
    0x2600, 0x2600, 0x2600, 0x2600, 0x2600, 0x2600, 0x2600, 0x2600,
    0x2609, 0x2609, 0x2609, 0x2609, 0x2609, 0x2609, 0x2609, 0x2609,
    0x2612, 0x2612, 0x2612, 0x2612, 0x2612, 0x2612, 0x2612, 0x2612,
    0x261B, 0x261B, 0x261B, 0x261B, 0x261B, 0x261B, 0x261B, 0x261B,
    0x2624, 0x2624, 0x2624, 0x2624, 0x2624, 0x2624, 0x2624, 0x2624,
    0x262D, 0x262D, 0x262D, 0x262D, 0x262D, 0x262D, 0x262D, 0x262D,
    0x2636, 0x2636, 0x2636, 0x2636, 0x2636, 0x2636, 0x2636, 0x2636,
    0x263F, 0x263F, 0x263F, 0x263F, 0x263F, 0x263F, 0x263F, 0x263F,
)

_ANIM_GRUNT_MOVING = (                                             # 0x59026
    0x0B24, 0x0B12, 0x0B00, 0x0AEA, 0x0AD8, 0x0B5A, 0x0B48, 0x0B36,
    0x0B24, 0x0B12, 0x0B00, 0x0AEA, 0x0AD8, 0x0B5A, 0x0B48, 0x0B36,
    0x0B24, 0x0B12, 0x0B00, 0x0AEA, 0x0AD8, 0x0B5A, 0x0B48, 0x0B36,
    0x0A63, 0x0A48, 0x0A2D, 0x0A09, 0x09EA, 0x0ABD, 0x0A90, 0x0A7E,
    0x0B1B, 0x0B09, 0x0AF3, 0x0AE1, 0x0ACF, 0x0B51, 0x0B3F, 0x0B2D,
    0x0B1B, 0x0B09, 0x0AF3, 0x0AE1, 0x0ACF, 0x0B51, 0x0B3F, 0x0B2D,
    0x0A63, 0x0A48, 0x0A2D, 0x0A09, 0x09EA, 0x0ABD, 0x0A90, 0x0A7E,
    0x0B24, 0x0B12, 0x0B00, 0x0AEA, 0x0AD8, 0x0B5A, 0x0B48, 0x0B36,
)

_ANIM_DEMON_MOVING = (                                             # 0x59126
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
    0x19D8, 0x19CF, 0x19BD, 0x19AB, 0x1999, 0x19A2, 0x19B4, 0x19C6,
    0x19D8, 0x19CF, 0x19BD, 0x19AB, 0x1999, 0x19A2, 0x19B4, 0x19C6,
    0x19D8, 0x19CF, 0x19BD, 0x19AB, 0x1999, 0x19A2, 0x19B4, 0x19C6,
    0x19D8, 0x19CF, 0x19BD, 0x19AB, 0x1999, 0x19A2, 0x19B4, 0x19C6,
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
)

_ANIM_SORC_MOVING = (                                              # 0x59226
    0x14CF, 0x14E1, 0x14F3, 0x1509, 0x1487, 0x1499, 0x14AB, 0x14BD,
    0x14CF, 0x14E1, 0x14F3, 0x1509, 0x1487, 0x1499, 0x14AB, 0x14BD,
    0x14C6, 0x14D8, 0x14EA, 0x1500, 0x147E, 0x1490, 0x14A2, 0x14B4,
    0x14C6, 0x14D8, 0x14EA, 0x1500, 0x147E, 0x1490, 0x14A2, 0x14B4,
    0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3,
    0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3,
    0x14C6, 0x14D8, 0x14EA, 0x1500, 0x147E, 0x1490, 0x14A2, 0x14B4,
    0x14C6, 0x14D8, 0x14EA, 0x1500, 0x147E, 0x1490, 0x14A2, 0x14B4,
)

_ANIM_DEATH_MOVING = (                                             # 0x592B6
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
    0x1ACF, 0x1B24, 0x1B09, 0x1AEA, 0x1A7E, 0x1A99, 0x1AB4, 0x1B3F,
    0x1AD8, 0x1B2D, 0x1B12, 0x1AF3, 0x1A87, 0x1AA2, 0x1ABD, 0x1B48,
    0x1AD8, 0x1B2D, 0x1B12, 0x1AF3, 0x1A87, 0x1AA2, 0x1ABD, 0x1B48,
    0x1ACF, 0x1B24, 0x1B09, 0x1AEA, 0x1A7E, 0x1A99, 0x1AB4, 0x1B3F,
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
    0x1AC6, 0x1B1B, 0x1B00, 0x1AE1, 0x1A75, 0x1A90, 0x1AAB, 0x1B36,
)

# 0x593B6 is byte-identical to 0x59336.
_ANIM_ACID_MOVING = _ANIM_ACID_IDLE

_ANIM_IT_SPECIAL = (                                               # 0x594B6
    0x2648, 0x2651, 0x265A, 0x2663, 0x266C, 0x2675, 0x267E, 0x2687,
    0x2600, 0x2609, 0x2612, 0x261B, 0x2624, 0x262D, 0x2636, 0x263F,
    0x2648, 0x2651, 0x265A, 0x2663, 0x266C, 0x2675, 0x267E, 0x2687,
    0x2600, 0x2609, 0x2612, 0x261B, 0x2624, 0x262D, 0x2636, 0x263F,
    0x2648, 0x2651, 0x265A, 0x2663, 0x266C, 0x2675, 0x267E, 0x2687,
    0x2600, 0x2609, 0x2612, 0x261B, 0x2624, 0x262D, 0x2636, 0x263F,
    0x2648, 0x2651, 0x265A, 0x2663, 0x266C, 0x2675, 0x267E, 0x2687,
    0x2600, 0x2609, 0x2612, 0x261B, 0x2624, 0x262D, 0x2636, 0x263F,
)

_ANIM_DEMON_SPECIAL = (                                            # 0x59536
    0x19D8, 0x19CF, 0x19BD, 0x19AB, 0x1999, 0x19A2, 0x19B4, 0x19C6,
    0x1A6C, 0x1A5A, 0x1A24, 0x1A12, 0x19EA, 0x1A00, 0x1A36, 0x1A48,
    0x1A63, 0x1A51, 0x1A1B, 0x1A09, 0x19E1, 0x19F3, 0x1A2D, 0x1A3F,
    0x1A6C, 0x1A5A, 0x1A24, 0x1A12, 0x19EA, 0x1A00, 0x1A36, 0x1A48,
    0x1A63, 0x1A51, 0x1A1B, 0x1A09, 0x19E1, 0x19F3, 0x1A2D, 0x1A3F,
    0x19D8, 0x19CF, 0x19BD, 0x19AB, 0x1999, 0x19A2, 0x19B4, 0x19C6,
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
    0x197E, 0x1951, 0x18F3, 0x1899, 0x183F, 0x186C, 0x18C6, 0x1924,
)

_ANIM_LOBBER_THROW = (                                             # 0x595B6
    0x1BDF, 0x1BBD, 0x1B9F, 0x1B81, 0x1B63, 0x1C3C, 0x1C1E, 0x1C00,
    0x1BE5, 0x1BC7, 0x1BA5, 0x1B87, 0x1B69, 0x1C42, 0x1C24, 0x1C06,
    0x1BE5, 0x1BC7, 0x1BA5, 0x1B87, 0x1B69, 0x1C42, 0x1C24, 0x1C06,
    0x1BE5, 0x1BC7, 0x1BA5, 0x1B87, 0x1B69, 0x1C42, 0x1C24, 0x1C06,
    0x1BD3, 0x1BB1, 0x1B93, 0x1B75, 0x1B57, 0x1C30, 0x1C12, 0x1BF1,
    0x1BD3, 0x1BB1, 0x1B93, 0x1B75, 0x1B57, 0x1C30, 0x1C12, 0x1BF1,
    0x1BD3, 0x1BB1, 0x1B93, 0x1B75, 0x1B57, 0x1C30, 0x1C12, 0x1BF1,
    0x1BD3, 0x1BB1, 0x1B93, 0x1B75, 0x1B57, 0x1C30, 0x1C12, 0x1BF1,
)

_MONSTER_IDLE_ANIMS = {
    int(MazeObjIds.MONST_GHOST): _ANIM_GHOST_IDLE,
    int(MazeObjIds.MONST_GRUNT): _ANIM_GRUNT_IDLE,
    int(MazeObjIds.MONST_DEMON): _ANIM_DEMON_IDLE,
    int(MazeObjIds.MONST_LOBBER): _ANIM_LOBBER_IDLE,
    int(MazeObjIds.MONST_SORC): _ANIM_SORC_IDLE,
    int(MazeObjIds.MONST_AUX_GRUNT): _ANIM_GRUNT_IDLE,
    int(MazeObjIds.MONST_DEATH): _ANIM_DEATH_IDLE,
    int(MazeObjIds.MONST_ACID): _ANIM_ACID_IDLE,
    int(MazeObjIds.MONST_SUPERSORC): _ANIM_SORC_IDLE,
    int(MazeObjIds.MONST_IT): _ANIM_IT_IDLE,
}

_MONSTER_MOVING_ANIMS = {
    int(MazeObjIds.MONST_GRUNT): _ANIM_GRUNT_MOVING,
    int(MazeObjIds.MONST_DEMON): _ANIM_DEMON_MOVING,
    int(MazeObjIds.MONST_SORC): _ANIM_SORC_MOVING,
    int(MazeObjIds.MONST_AUX_GRUNT): _ANIM_GRUNT_MOVING,
    int(MazeObjIds.MONST_DEATH): _ANIM_DEATH_MOVING,
    int(MazeObjIds.MONST_ACID): _ANIM_ACID_MOVING,
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
_GEN_CANDIDATE_COL = (0, 1, 0, -1, 1, 1, -1, -1, 0, 1, 0, -1, -0x20, 0, 0x20)
_GEN_CANDIDATE_ROW = (-0x20, 0, 0x20, 0, -0x20, 0x20, 0x20, -0x20,
                      -0x20, 0, 0x20, 0, 0, 2, 4)
#: The ROM-compass code (0=north) written into the spawned creature's state
#: word.  gauntpy's compass is the ROM's minus two -- see ``_write_direction``.
_GEN_CANDIDATE_DIR = (0, 2, 4, 6, 1, 3, 5, 7, 0, 2, 4, 6, 0x200, 0x500, 0x600)
#: 0x49312's ``getrandom`` bound, and the eight tries of 0x49434.
_GEN_START_BOUND = 4
_GEN_CANDIDATE_COUNT = 8
#: 0x492F8/0x492FC -- attract mode does not draw for the rotation start at all.
#: The three ghost-generator families seed it at 7, every other family at 2.
_GEN_ATTRACT_START_GHOST = 7
_GEN_ATTRACT_START_OTHER = 2
#: 0x492EE-0x492F6 -- the family indices that take the 7 seed.
_GEN_ATTRACT_GHOST_FAMILIES = range(0, 3)
#: 0x44A76 -- ``attract_demo_init`` loads ``monster_generation_retry_timer``.
GENERATOR_RETRY_RELOAD = 4

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
_OCCUPANCY_NEIGHBOUR_COL = (-1, 1, 0, 0, 1, 1, -1, -1)
_OCCUPANCY_NEIGHBOUR_ROW = (0, 0, -0x20, 0x20, -0x20, 0x20, 0x20, -0x20)

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


# =============================================================================
# Small helpers on the MOB record
# =============================================================================

def _get_direction(state: GameState, slot: int) -> int:
    """Monster facing, stored in the low 3 bits of the MOB state field."""
    return state.mobs.state(slot) & 0x07


def _set_direction(state: GameState, slot: int, direction: int) -> None:
    upper = state.mobs.state(slot) & ~0x07
    state.mobs.set_state(slot, upper | (direction & 0x07))


def _monster_animation_index(state: GameState, slot: int) -> int:
    """Translate gauntpy's compass in the six-bit state to a ROM table index."""
    packed = state.mobs.state(slot) & 0x3F
    return (packed & 0x38) | (((packed & 0x07) + 2) & 0x07)


def _refresh_monster_picture(
    state: GameState, slot: int, obj_type: int,
) -> None:
    """``monster_update_anim_tile`` (0x414A4) and its bank selectors.

    The previous port advanced the animation counter and facing field but never
    copied the selected ROM word into ``mob_picture``. Creatures therefore kept
    their spawn frame forever even while turning and walking.
    """
    if state.mobs.picture[slot] == 0:
        return

    flags = state.mobs.hpos[slot]
    if (
        state.mobs.picture[slot] == _BLANK_PICTURE
        and flags & (_HPOS_FLAG_MOVING | _HPOS_FLAG_ATTACK)
    ):
        return
    table = _MONSTER_IDLE_ANIMS[obj_type]
    if flags & _HPOS_FLAG_MOVING:
        table = _MONSTER_MOVING_ANIMS.get(obj_type, table)
    elif flags & _HPOS_FLAG_ATTACK:
        if obj_type == int(MazeObjIds.MONST_LOBBER):
            table = _ANIM_LOBBER_THROW
        elif obj_type == int(MazeObjIds.MONST_IT):
            table = _ANIM_IT_SPECIAL
        elif obj_type == int(MazeObjIds.MONST_DEMON):
            table = _ANIM_DEMON_SPECIAL
        elif obj_type == int(MazeObjIds.MONST_SORC):
            table = _ANIM_SORC_MOVING

    state.mobs.picture[slot] = table[_monster_animation_index(state, slot)]


def _signed_byte(value: int) -> int:
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def _monster_index(obj_type: int) -> int:
    """``D6 / 4`` in the original: 0-9 for the ten creature types."""
    return obj_type - int(MazeObjIds.MONST_GHOST)


def _delta_units(target_word: int, source_word: int) -> int:
    """Signed axis delta in 2-pixel units, exactly as ``monster_find_and_shoot``
    computes it (0x4177A-0x41796): high byte of each position word, subtracted
    as bytes and then sign-extended, so the delta wraps to the shorter way
    round a 512-pixel maze.
    """
    return _signed_byte((target_word >> 8) - (source_word >> 8))


def _aim_direction(u: int, v: int, override: int = 0, threshold: int = 0) -> int:
    """Direction to face along (``u``, ``v``), 0x41810-0x4192C.

    ``u``/``v`` are deltas in the hardware's own axes, so ``v`` positive means
    the target is *above*.  The ROM's compass is ``0=up, 1=up-right, 2=right
    ...`` (``player_facing_dir``); gauntpy's is ``0=right, 1=down-right, ...``,
    i.e. ROM = gauntpy + 2.

    ``override`` is the family's ``monster_level_flag_overrides`` byte, zero
    unless that ODDANGLE level flag is set.  Every non-zero value yields an odd
    (diagonal) direction:

    * ``0xC0`` rounds the cardinal direction counter-clockwise (0x41882),
    * ``0xA0`` rounds it clockwise (0x418B8),
    * ``0x80`` picks by |u|/|v| against ``threshold`` (0x418EA).

    With no override the picker is the cardinal/diagonal one at 0x4181A:
    diagonal unless one axis is inside ``threshold``.
    """
    if override & 0x40:                     # 0xC0
        if v < u:
            rom = 1 if v >= -u else 3
        else:
            rom = 5 if v < -u else 7
        return (rom - 2) & 0x07
    if override & 0x20:                     # 0xA0
        if v < u:
            rom = 3 if v >= -u else 5
        else:
            rom = 7 if v < -u else 1
        return (rom - 2) & 0x07

    au, av = abs(u), abs(v)
    if override:                            # 0x80
        # 0x418EA-0x4190C.  The |dx| test only selects which of two identical
        # tails runs: the ``moveq #7`` at 0x41906 falls straight through into
        # the |dy| test that overwrites it, so the vertical delta alone
        # decides -- 1 (up-right) when the target is at least ``threshold``
        # away vertically, 3 (down-right) when it is level with the creature.
        rom = 1 if av >= threshold else 3
    else:                                   # no override
        rom = 1
        if au < threshold:
            rom = 0
        if av < threshold:
            rom = 2
    if u < 0:
        rom = (8 - rom) & 0x07
    if v < 0:
        rom = (12 - rom) & 0x07
    return (rom - 2) & 0x07


def _oddangle_override(state: GameState, obj_type: int) -> int:
    """The family's override byte, or 0 when its ODDANGLE flag is clear.

    ``monsters_everything`` copies ``monster_level_flag_overrides[family]`` over
    the family's speed longword for every set bit of ``level_flags & 0x73``
    (0x40F34-0x40F58); ``monster_find_and_shoot`` then reads it back at 0x41814.
    """
    entry = _ODDANGLE_OVERRIDE.get(obj_type)
    if entry is None:
        return 0
    bit, value = entry
    if not (state.level_flags & _ODDANGLE_LEVEL_FLAG_MASK & bit):
        return 0
    return value


# =============================================================================
# Culling rectangle
# =============================================================================

def _update_cull_rect(state: GameState) -> None:
    """0x49052-0x49076 -- re-anchor the culling rectangle on the camera."""
    state.cull_rect_x = ((state.scroll_x - _CULL_H_BIAS) << POS_SHIFT) & 0xFFFF
    state.cull_rect_y = ((_CULL_V_BIAS - state.scroll_y) << POS_SHIFT) & 0xFFFF


def _in_cull_rect(state: GameState, slot: int) -> bool:
    """0x40FF6-0x4101A -- whether a creature is processed at all this frame."""
    if ((state.mobs.hpos[slot] - state.cull_rect_x) & 0xFFFF) >= _CULL_WIDTH:
        return False
    return ((state.mobs.vpos[slot] - state.cull_rect_y) & 0xFFFF) < _CULL_HEIGHT


def _shooter_in_view(state: GameState, slot: int) -> bool:
    """``monster_shooter_in_view`` (0x41B52) -- the tighter shooting box.

    Byte comparisons against the same origins, so the units are 2 pixels and
    the arithmetic wraps once per 512-pixel maze.
    """
    du = ((state.mobs.hpos[slot] >> 8) - (state.cull_rect_x >> 8)) & 0xFF
    if du <= _VIEW_H_MIN or du >= _VIEW_H_MAX:
        return False
    dv = ((state.mobs.vpos[slot] >> 8) - (state.cull_rect_y >> 8)) & 0xFF
    return not (dv <= _VIEW_V_MIN or dv >= _VIEW_V_MAX)


def _cell_blocked(state: GameState, slot: int) -> bool:
    """True when a cell already holds a wall, object, or another MOB."""
    return state.mobs.is_occupied(slot)


# =============================================================================
# Top-level main-loop call
# =============================================================================

def main_move_monsters(state: GameState) -> None:
    """0x49034 -- advance every monster and generator by one frame.

    Re-anchors the culling rectangle on the camera, picks the arc of the depth
    chain the walk will cover, applies the global slow-motion gate (which
    halves the monster update rate without touching players), and then walks
    that arc.

    With no player on the level the ROM returns before touching any of it
    (0x4904E), so an empty maze freezes its monsters.
    """
    if state.level_players_active <= 0:
        return
    _update_cull_rect(state)

    # 0x49076-0x490CC: two SLIP bucket heads bracket the on-screen band of the
    # chain -- the walk starts at one and stops at the other.
    start_slot = _walk_band_head(state, -_WALK_HALF_SPAN)
    state.monster_iter_ptr = (_walk_band_head(state, _WALK_HALF_SPAN)
                              or state.mobs.depth_list_head)

    slowmo = state.monster_slowmo_timer > 0
    if slowmo:
        state.monster_slowmo_timer -= 1
        if state.monster_slowmo_timer == _ACID_RATE_MASK:   # 0x1E
            _sound_play(state, _SOUND_SLOWMO_SILENCER)       # 0x38
        elif state.monster_slowmo_timer == 0:
            _sound_play(state, _SOUND_SLOWMO_END)            # 0x39
        # While slow-motion is active the whole walk is dropped on even frames.
        if (state.frame_counter & 1) == 0:
            return

    monsters_everything(state, _frame_word(state, slowmo), start_slot)


def _frame_word(state: GameState, slowmo: bool) -> int:
    """``d6`` -- the cadence word every stagger in the pass is taken against.

    ``frame_counter`` doubled (0x40EEC) unless slow-motion is running, in which
    case the raw value is used and only odd frames run at all (0x40EE0).  The
    doubling keeps a creature's real-time cadence the same either way.
    """
    if slowmo:
        return state.frame_counter & 0xFFFF
    return (state.frame_counter * 2) & 0xFFFF


def monsters_everything(state: GameState, frame_word: int | None = None,
                        start_slot: int | None = None) -> None:
    """0x40E6A -- walk the on-screen arc of the depth chain.

    The walk enters at ``start_slot`` and runs forward -- wrapping from the end
    of the chain back to its head, exactly as the ROM wraps to
    ``priority_bucket_heads`` -- until it reaches ``monster_iter_ptr``, the
    bucket head that marks the far edge of the visible band.  Because the chain
    is sorted top-to-bottom, that arc *is* the band of creatures near the
    screen; the culling rectangle then trims the corners.
    """
    if frame_word is None:
        frame_word = _frame_word(state, state.monster_slowmo_timer > 0)

    if state.mobs.depth_list_head == 0:
        state.monster_iter_ptr = 0
        return
    if start_slot is None:
        start_slot = _walk_band_head(state, -_WALK_HALF_SPAN)

    slot = start_slot or state.mobs.depth_list_head
    for _ in range(len(state.mobs.picture) + 1):        # cycle guard
        if slot == 0:
            return
        # 0x414C8 re-reads the chain head every lap, so a creature that
        # relocated (and re-headed the list) cannot strand the walk.
        head = state.mobs.depth_list_head
        if head == 0:
            return
        nxt = state.mobs.next_slot(slot) or head
        _dispatch_chain_entry(state, slot, frame_word)
        # 0x414D0 compares *after* processing, so the entry the walk starts on
        # is always handled even when it is the marker itself.
        slot = nxt
        if slot == state.monster_iter_ptr:
            return
    raise RuntimeError("cycle detected in the monster walk")


def _dispatch_chain_entry(state: GameState, slot: int, frame_word: int) -> None:
    """0x40FB4-0x4105E -- type decode, culling, then the family dispatch."""
    obj_type = state.mobs.obj_type(slot)
    if obj_type not in GENERATOR_TYPES and obj_type not in MONSTER_TYPES:
        return
    if not _in_cull_rect(state, slot):
        return
    if obj_type in GENERATOR_TYPES:
        _handle_generator(state, slot, obj_type, frame_word)
    elif obj_type == int(MazeObjIds.MONST_SUPERSORC):
        _supersorc_dispatch(state, slot, frame_word)
        if state.mobs.obj_type(slot) == obj_type:
            _refresh_monster_picture(state, slot, obj_type)
    else:
        _dispatch_monster(state, slot, obj_type, frame_word)
        if state.mobs.obj_type(slot) == obj_type:
            _refresh_monster_picture(state, slot, obj_type)


# 0x49076/0x490AC -- the walk covers the arc of the chain between two SLIP
# bucket heads, 8 px above the visible band and 56 px below it: 288 px in all,
# comfortably wider than the 263 px culling rectangle so nothing on screen can
# be skipped by the arc alone.  The ROM's buckets are *screen*-relative (the
# hardware SLIP list); gauntpy's ``MobTable.slip_heads`` are playfield-relative
# by design (see mob.py), so the same window is re-derived from the camera
# midpoint instead of from ``pf_vscroll_lo`` directly.
_WALK_HALF_SPAN = 144
_CAM_MID_OFFSET = 0x88          # midpoint of ROM's scroll-8 .. scroll+280 arc
_SLIP_BAND_PIXELS = 8


def _walk_band_head(state: GameState, offset: int) -> int:
    """The chain entry ``offset`` pixels from the camera midpoint."""
    mid_y = state.scroll_y + _CAM_MID_OFFSET
    band = (mid_y + offset) // _SLIP_BAND_PIXELS
    heads = state.mobs.slip_heads
    if band < 0:
        return state.mobs.depth_list_head
    if band >= len(heads):
        # Past the last band: the ROM falls back to ``priority_bucket_heads``,
        # so the walk wraps once and stops at the chain head.
        return state.mobs.depth_list_head
    return heads[band] or state.mobs.depth_list_head


def _iter_ptr_forget(state: GameState, slot: int) -> None:
    """0x414FE -- a creature that removed itself hands the marker back."""
    if state.monster_iter_ptr != slot:
        return
    state.monster_iter_ptr = (state.mobs.prev_slot(slot)
                              or state.mobs.depth_list_head)


# =============================================================================
# Shared monster handler (0x4119A) and the animation counter
# =============================================================================
# The state word's top three bits (0xE000) are an animation counter.  Every
# branch below advances it with ``addi.w #0x2000`` and acts on the *carry*: the
# creature holds a pose for eight gated frames and then does something -- take a
# step, finish an attack, blink out.  ``monster_oddangle_table`` supplies the
# per-family knobs: byte 1 is the frame mask while walking or after a step, byte
# 0 the mask when the step was refused, byte 2 the counter delta (or, with bit 0
# set, "enter the blink state") and byte 3 the delta on the moving path.

_ANIM_STEP = 0x2000
#: 0x410FA/0x4148A -- the blank sprite a sorcerer wears while blinked out.
_BLANK_PICTURE = 0x1709
#: 0x41484 -- extra counter bump applied when entering the blink state.
_BLINK_ANIM_BUMP = 0x60


def _anim_advance(state: GameState, slot: int) -> bool:
    """``addi.w #0x2000,(a6,d2.w)`` -- True when the counter wraps (carry)."""
    value = state.mobs.state_link[slot] + _ANIM_STEP
    state.mobs.state_link[slot] = value & 0xFFFF
    return value > 0xFFFF


def _anim_add_high(state: GameState, slot: int, delta: int) -> None:
    """``add.b d0,(a6,d2.w)`` -- byte add into the state word's high byte."""
    if not delta:
        return
    word = state.mobs.state_link[slot]
    state.mobs.state_link[slot] = ((((word >> 8) + delta) & 0xFF) << 8) | (word & 0xFF)


def _dispatch_monster(state: GameState, slot: int, obj_type: int,
                      frame_word: int) -> None:
    """One shared handler with per-state and per-family branches (§3.3)."""
    index = _monster_index(obj_type)
    hpos = state.mobs.hpos[slot]

    if hpos & _HPOS_FLAG_MOVING:
        # 0x4119A -- walking.  One animation step every fourth frame; the step
        # itself only happens on the frame the counter wraps.
        if frame_word & 6:
            return
        if not _anim_advance(state, slot):
            return
        _anim_add_high(state, slot, _MONSTER_ODDANGLE_TBL[index][3])
        _monster_move_engine(state, slot, obj_type, index, frame_word)
        return

    if hpos & _HPOS_FLAG_ATTACK:
        # 0x411CC -- winding up.  IT and acid have their own gates, the
        # sorcerer skips straight to the mover, everyone else fires when the
        # wind-up animation completes.
        if obj_type == int(MazeObjIds.MONST_IT):                   # 0x413F0
            _anim_finish_attack(state, slot, index,
                                _MONSTER_ODDANGLE_TBL[index][1], frame_word)
            return
        if obj_type == int(MazeObjIds.MONST_ACID):                 # 0x413E6
            _anim_finish_attack(state, slot, index, _ACID_RATE_MASK, frame_word)
            return
        if obj_type == int(MazeObjIds.MONST_SORC):                 # 0x411E2
            _monster_move_engine(state, slot, obj_type, index, frame_word)
            return
        if frame_word & 6:
            return
        if not _anim_advance(state, slot):
            return                       # still in the wind-up frames
        state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK                # 0x411FE
        monster_find_and_shoot(state, slot, obj_type)              # 0x41252
        _post_action(state, slot, obj_type, index, frame_word)
        return

    # 0x41222 -- idle: on its turn the creature re-aims (or, for acid, rolls a
    # new direction), otherwise it just keeps walking.
    if (((slot * 2) | 2) ^ frame_word) & 0x1E:
        _monster_move_engine(state, slot, obj_type, index, frame_word)
        return
    if obj_type == int(MazeObjIds.MONST_ACID):                     # 0x4123A
        _set_direction(state, slot, state.getrandom(8))
    else:
        monster_find_and_shoot(state, slot, obj_type)
    _post_action(state, slot, obj_type, index, frame_word)


def _anim_finish_attack(state: GameState, slot: int, index: int, mask: int,
                        frame_word: int) -> None:
    """0x413E6/0x413F0/0x4141C -- gated wind-up that ends by dropping the
    attack flag and nudging the animation counter by the family's byte 2."""
    if mask & (frame_word & 0xFF):
        return
    if not _anim_advance(state, slot):
        return
    state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK
    _anim_add_high(state, slot, _MONSTER_ODDANGLE_TBL[index][2])


def _post_action(state: GameState, slot: int, obj_type: int, index: int,
                 frame_word: int) -> None:
    """0x41256 -- a creature that just acted animates its attack or walks."""
    if state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK:
        return
    _monster_move_engine(state, slot, obj_type, index, frame_word, acted=True)


# obj_type -> its per-family LFLAG2 "fast" bit in the ``level_flags_2`` byte.
# Each fast flag speeds up exactly one family (gex.constants LFLAG2_FAST_*:
# longword bits 16-22 = level_flags_2 byte bits 0-6). Acid, Super Sorcerer, and
# IT have no fast flag. §3.3.
_FAST_FAMILY_BIT = {
    int(MazeObjIds.MONST_GHOST): 0x01,       # LFLAG2_FAST_GHOSTS
    int(MazeObjIds.MONST_GRUNT): 0x02,       # LFLAG2_FAST_GRUNTS
    int(MazeObjIds.MONST_DEMON): 0x04,       # LFLAG2_FAST_DEMONS
    int(MazeObjIds.MONST_LOBBER): 0x08,      # LFLAG2_FAST_LOBBERS
    int(MazeObjIds.MONST_SORC): 0x10,        # LFLAG2_FAST_SORCERERS
    int(MazeObjIds.MONST_AUX_GRUNT): 0x20,   # LFLAG2_FAST_AUX_GRUNTS
    int(MazeObjIds.MONST_DEATH): 0x40,       # LFLAG2_FAST_DEATHS
}


def _monster_speed(state: GameState, obj_type: int, frame_word: int) -> int:
    """Base 0x80 (2 px); a family raised to 0x100 (4 px) on frames where bit 1 of
    the frame word is set, averaging ~1.5x (§3.3).

    Verified by disassembly of monsters_everything (0x40EEE-0x40F34): the config
    pushes 0x80 for every family, and only when ``level_flags_2`` has *that
    family's* fast bit set **and** bit 1 of the cadence word is set is it raised
    to 0x100.  That word is ``frame_counter`` doubled outside slow-motion, so
    without slow-motion the test lands on ``frame_counter`` bit 0.

    The ``level_flags`` ODDANGLE override at 0x40E02 rides in the *high* byte of
    the same longword and is not a speed at all -- see ``_oddangle_override``.
    """
    bit = _FAST_FAMILY_BIT.get(obj_type)
    if bit and (state.level_flags_2 & bit) and (frame_word & 2):
        return _MONSTER_SPEED_FAST
    return _MONSTER_SPEED_BASE


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
#: 0x5E112 / 0x5E1DE -- the vertical edge guards, on the V word itself: a march
#: towards row 0 stops unless the word is at or below 0xF080, and a march
#: towards row 31 stops once the word has gone negative through the floor.
_EDGE_TOP_LIMIT = 0xF080

# Probe descriptors: (row step, column step) of the cell straight ahead, and
# the axis the two flanking cells are taken along.
_PROBE_UP = (-1, 0)
_PROBE_DOWN = (1, 0)
_PROBE_LEFT = (0, -1)
_PROBE_RIGHT = (0, 1)


def _cell_at(row: int, col: int) -> int:
    """Slot of a maze cell; the column wraps inside its row (``andi #0x3E``)."""
    return ((row & 0x1F) << 5) | (col & 0x1F)


def _march_cell_blocks(state: GameState, cell: int, h: int, v: int) -> bool:
    """One cell of a ray march: does its occupant overlap the probe position?

    ``tst.w (a2,d1.w)`` empty -> no; picture bit 15 (a software MOB) shifts the
    stored H by 0x200 first; otherwise both axis separations have to be inside
    ``_OVERLAP`` for the cell to block.

    The separations are taken *modulo the maze*: the position words span
    exactly one maze in 16 bits, so the subtraction wraps at the seam on its
    own and a creature on column 31 sees column 0 as its neighbour.

    A hero needs no special case: its record migrates into the cell it stands
    in, so a walking player is simply that cell's occupant.
    """
    picture = state.mobs.picture[cell]
    if picture == 0:
        return False
    cell_h = state.mobs.hpos[cell]
    if picture & 0x8000:
        cell_h = (cell_h - _SOFTWARE_MOB_BIAS) & 0xFFFF
    if abs(_s16(cell_h - h)) >= _OVERLAP:
        return False
    return abs(_s16(v - state.mobs.vpos[cell])) < _OVERLAP


def _s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _ray_march(state: GameState, slot: int, probe: tuple[int, int],
               h: int, v: int) -> int | None:
    """The four ray marches -- returns the blocking cell, or None when clear.

    Each march looks at the cell straight ahead and the two cells flanking it
    on the perpendicular axis, because a 16-pixel creature clips its
    neighbours.  The ROM signals "clear" by returning with N set and a -1 cell,
    and records it by setting bit 31 of D2; here that is simply ``None``.
    """
    row, col = slot >> 5, slot & 0x1F
    d_row, d_col = probe

    if d_row:                                   # vertical march
        if d_row < 0:                           # 0x5E10C: towards row 0
            if row < 2:                         # cmpi.w #0x80,d2
                return None if (v & 0xFFFF) <= _EDGE_TOP_LIMIT else slot
        elif row >= 31:                         # 0x5E1D8: cmpi.w #0x7C0,d2
            return None if _s16(v) >= 0 else slot
        ahead_row = row + d_row
        cells = (_cell_at(ahead_row, col),
                 _cell_at(ahead_row, col - 1),
                 _cell_at(ahead_row, col + 1))
    else:                                       # horizontal march
        ahead_col = col + d_col
        cells = [_cell_at(row, ahead_col)]
        if row >= 2:                            # 0x5E2DE: skip near the top
            cells.append(_cell_at(row - 1, ahead_col))
        if row < 31:                            # 0x5E308: skip on the last row
            cells.append(_cell_at(row + 1, ahead_col))

    for cell in cells:
        if cell != slot and _march_cell_blocks(state, cell, h, v):
            return cell
    return None


def _probe_phase(state: GameState, slot: int, step: int,
                 ) -> tuple[int, int, int, bool, int | None]:
    """0x41272-0x41336 -- the four axis probes.

    Returns ``(hpos, vpos, d6, any_clear, blocking_cell)``.  ``d6`` is the
    ROM's rotating direction counter *after* the final ``+0x400`` and mask, so
    it is the heading to store; ``blocking_cell`` is set only when a probe ran
    into something the caller has to resolve as contact.
    """
    h = state.mobs.hpos[slot]
    v = state.mobs.vpos[slot]
    rom_dir = (_get_direction(state, slot) + 2) & 0x07
    d6 = ((rom_dir << 10) + 0x400) & 0x1C00
    clear = False

    # --- probe 1 (0x41288): the "up the screen" component -------------------
    if d6 < 0xC00:
        v = (v + step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_UP, h, v)
        if blocker is None:
            clear = True
        else:
            v = (v - step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 - 0x1000) & 0xFFFF

    # --- probe 2 (0x412B4): the "down the screen" component -----------------
    if d6 < 0xC00:
        v = (v - step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_DOWN, h, v)
        if blocker is None:
            clear = True
        else:
            v = (v + step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 - 0x800) & 0x1C00

    # --- probe 3 (0x412E4): the leftward component --------------------------
    if d6 < 0xC00:
        h = (h - step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_LEFT, h, v)
        if blocker is None:
            clear = True
        else:
            h = (h + step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 + 0x1000) & 0x1C00

    # --- probe 4 (0x41314): the rightward component -------------------------
    if d6 < 0xC00:
        h = (h + step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_RIGHT, h, v)
        if blocker is None:
            clear = True
        else:
            h = (h - step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 + 0x400) & 0x1C00
    return h, v, d6, clear, None


def _is_player_cell(state: GameState, cell: int) -> bool:
    """0x4129E -- the palette nibble the ROM reads a hero sprite by."""
    return _cell_player_index(state, cell) is not None


def _monster_move_engine(state: GameState, slot: int, obj_type: int, index: int,
                         frame_word: int, acted: bool = False) -> None:
    """0x4126A -- probe, slide, relocate, and animate.

    ``D6`` walks a rotating direction counter: it starts one step clockwise of
    the creature's heading and each probe block moves it on, so a run with
    nothing blocked lands back exactly where it started.  A probe that *is*
    blocked doubles it first (``add.w d6,d6; subi #0x400``), which is how the
    creature turns away from what it hit.
    """
    speed = _monster_speed(state, obj_type, frame_word)
    h, v, d6, clear, blocker = _probe_phase(state, slot, speed << POS_SHIFT)
    if blocker is not None:
        _march_hit_player(state, slot, blocker)
        return
    _commit_move(state, slot, index, d6, h, v, clear, frame_word, acted)


def _march_hit_player(state: GameState, slot: int, blocker: int) -> None:
    """0x4129A/0x413B0 -- a blocked probe that ran into a player is contact.

    The ROM branches out of the probe loop *before* it commits the heading or
    drops the moving flag (0x41348), so the creature neither moves nor leaves
    its attack state: this is the frame it lands a blow.  Afterwards it turns
    to face what it hit (0x413CC), unless the contact removed it -- a ghost
    exploding on the player.
    """
    victim = _cell_player_index(state, blocker)
    if victim is None:
        return
    monster_playerhit(state, victim, slot)
    if state.mobs.picture[slot] == 0:
        _iter_ptr_forget(state, slot)          # 0x413C4: it removed itself
        return
    _face_after_contact(state, slot, blocker)  # 0x413CC


def _cell_player_index(state: GameState, cell: int) -> int | None:
    """Which player, if any, the given cell counts as.

    The ROM tests the cell's palette nibble (>= 0xC, the four hero palettes)
    and then charges the hit to that player.  This port asks the authoritative
    question instead -- which live record *is* this cell -- because
    ``active_mob_ids`` is the identity and a nibble is only its colour
    (``FIDELITY.md`` rule 6).  Both answers are the same cell now that a hero's
    record migrates with it.
    """
    for p in state.players:
        if p.active and p.mob_slot == cell:
            return p.index
    return None


def _face_after_contact(state: GameState, slot: int, victim_cell: int) -> None:
    """``apply_direction_from_delta`` (0x41B7E) -- turn towards what was hit.

    Same picker as the idle aim with the fixed 0x400-position-unit threshold,
    which is 8 pixels, i.e. 4 of the 2-pixel units the picker counts in.
    """
    victim = _cell_player_index(state, victim_cell)
    target_slot = (
        state.players[victim].mob_slot if victim is not None else victim_cell
    )
    dx = _delta_units(state.mobs.hpos[target_slot], state.mobs.hpos[slot])
    dv = _delta_units(state.mobs.vpos[target_slot], state.mobs.vpos[slot])
    _set_direction(state, slot, _aim_direction(dx, dv, 0, 4))


def _write_direction(state: GameState, slot: int, d6: int) -> None:
    """0x4133E -- store the ROM-compass direction field back into the state."""
    _set_direction(state, slot, ((d6 >> 10) - 2) & 0x07)


def _destination_cell(h: int, v: int) -> int:
    """0x41358-0x41374 -- which cell a position belongs to, sprite bias and all.

    The ROM adds 0x400 to V and 0x600 to H before slicing out the row and
    column, and its rows run the other way -- which is exactly what the stored
    words do too, so this is the ROM's own arithmetic. ``coords.mob_cell_of``
    owns it, because ``player_try_move_core`` (0x424CA) applies the identical
    sequence to relocate a hero's record.
    """
    return mob_cell_of(h, v)


def _commit_move(state: GameState, slot: int, index: int, d6: int, h: int,
                 v: int, clear: bool, frame_word: int, acted: bool) -> None:
    """0x4133E-0x413AE -- store the heading, then relocate if a probe was clear."""
    _write_direction(state, slot, d6)
    h &= ~_HPOS_FLAG_MOVING                    # 0x41348: bclr #5
    state.mobs.hpos[slot] = h

    if not clear:
        _move_tail(state, slot, index, frame_word, moved=False, acted=acted)
        return

    dest = _destination_cell(h, v)
    if dest == slot:                            # 0x4144C: same cell
        state.mobs.vpos[slot] = v
        _move_tail(state, slot, index, frame_word, moved=True, acted=acted)
        return

    if state.mobs.picture[dest] == 0:           # 0x41380: the cell is free
        if state.monster_iter_ptr == slot:
            state.monster_iter_ptr = dest
        state.mobs.hpos[slot] = h
        state.mobs.vpos[slot] = v
        state.mobs.move_slot(slot, dest)
        _move_tail(state, dest, index, frame_word, moved=True, acted=acted)
        _refresh_monster_picture(
            state, dest, int(MazeObjIds.MONST_GHOST) + index,
        )
        return

    victim = _cell_player_index(state, dest)    # 0x413A2
    if victim is None:
        _move_tail(state, slot, index, frame_word, moved=False, acted=acted)
        return
    monster_playerhit(state, victim, slot)
    if state.mobs.picture[slot] == 0:
        _iter_ptr_forget(state, slot)
        return
    _face_after_contact(state, slot, dest)
    if not (state.mobs.hpos[slot] & _HPOS_FLAG_MOVING):
        _move_tail(state, slot, index, frame_word, moved=False, acted=acted)


def _move_tail(state: GameState, slot: int, index: int, frame_word: int,
               moved: bool, acted: bool) -> None:
    """0x41454 (moved) and 0x4142E (refused) -- the shared animation tail.

    The frame mask comes from ``monster_oddangle_table``: byte 1 after a step,
    byte 0 when the step was refused.  A zero mask on the refused path means
    "do nothing at all"; a negative one (the two sorcerers) drops the attack
    flag instead.  When the counter wraps, byte 2 either bumps it further or --
    with bit 0 set -- flips the creature into its blink state.
    """
    row = _MONSTER_ODDANGLE_TBL[index]
    if moved:
        mask = row[1]
    else:
        if acted:                               # 0x41430: btst #30
            return
        mask = row[0]
        if mask == 0:
            return
        if mask & 0x80:                         # 0x41442: bmi
            if state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK:
                state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK
            return

    if mask & (frame_word & 0xFF):              # 0x41460
        return
    if not _anim_advance(state, slot):          # 0x41466
        return

    delta = row[2]
    if delta & 0x01:                            # 0x41472: the blink families
        if state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK:
            state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK
            return
        state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK
        _anim_add_high(state, slot, _BLINK_ANIM_BUMP)
        state.mobs.picture[slot] = _BLANK_PICTURE
        return
    _anim_add_high(state, slot, delta)


# =============================================================================
# Find and shoot (0x41750)
# =============================================================================

def monster_find_and_shoot(state: GameState, slot: int, obj_type: int) -> None:
    """0x41750 -- face a player and, for shooter classes, launch a shot.

    The IT player (``player_it``) is evaluated first, biasing selection toward
    the cursed hero; otherwise the nearest player by summed absolute axis delta
    wins (§3.5).  Invisible players are invisible to this too (0x4176C/0x417C0).

    Which direction "facing" means is the family's business: an ODDANGLE level
    flag swaps in a diagonal-only picker (``_aim_direction``).  A *repulsive*
    target is fled from instead -- the direction is flipped 180 degrees
    (``eori #4`` at 0x41876/0x41AE2) -- except that demons and lobbers still
    take their shot first.
    """
    index = _monster_index(obj_type)
    target = _find_target_player(state, slot)
    if target < 0:
        return
    p = state.players[target]
    dx = _delta_units(state.mobs.hpos[p.mob_slot], state.mobs.hpos[slot])
    dv = _delta_units(state.mobs.vpos[p.mob_slot], state.mobs.vpos[slot])

    override = _oddangle_override(state, obj_type)
    thresholds = _SHOOT_AXIS_THRESHOLDS[index]
    threshold = thresholds[0] if override == 0x80 else thresholds[1]
    direction = _aim_direction(dx, dv, override, threshold)
    repulsive = bool(p.powers & _POWER_REPULSE)

    if obj_type == int(MazeObjIds.MONST_LOBBER):
        direction = _lobber_throw(state, slot, direction, dx, dv, target)
    elif obj_type == int(MazeObjIds.MONST_DEMON):
        if not _demon_shoot(state, slot, direction, dx, dv) and repulsive:
            direction ^= 4
    elif repulsive:
        direction ^= 4

    _set_direction(state, slot, direction)


def _lobber_throw(state: GameState, slot: int, direction: int,
                  dx: int, dv: int, target: int) -> int:
    """0x41946 -- range-gated rock throw; returns the direction to face.

    Inside 0x14 units (40 px) on *both* axes the lobber backs away instead of
    throwing; past 0x2C (88 px) on either axis, and from outside the shooter
    box, it just stands and faces.  A thrown rock is given the lead arc of
    0x419E4, not a straight direction step.
    """
    adx, adv = abs(dx), abs(dv)
    if adx < _LOBBER_MIN_RANGE and adv < _LOBBER_MIN_RANGE:
        return direction ^ 4            # too close: turn away (0x41876)
    if adx >= _LOBBER_MAX_RANGE or adv >= _LOBBER_MAX_RANGE:
        return direction
    if not _shooter_in_view(state, slot):
        return direction
    shot_slot = _find_free_shot_slot(state, SLOT_LOBBER_SHOTS)
    if shot_slot is None:
        return direction
    lead = _lobber_lead(state, slot, direction, target, dx, dv)
    monster_create_shot(state, slot, direction, shot_slot, lead=lead)
    _sound_play(state, _SOUND_LOBBER_THROW)
    return direction


def _demon_shoot(state: GameState, slot: int, direction: int,
                 dx: int, dv: int) -> bool:
    """0x41A2E -- fireball if in view, in range, and the muzzle cell is clear.

    The axis gate depends on the facing: a diagonal shot also needs the two
    deltas within ``_DEMON_DIAG_SKEW`` of each other, so the demon only fires
    down a real 45-degree line.
    """
    if not _shooter_in_view(state, slot):
        return False
    shot_slot = _find_free_shot_slot(state, SLOT_DEMON_SHOTS)
    if shot_slot is None:
        return False
    if not _demon_muzzle_clear(state, slot, direction):
        return False

    adx, adv = abs(dx), abs(dv)
    if direction & 1:                                   # diagonal
        if adx < _DEMON_MIN_RANGE or abs(adx - adv) >= _DEMON_DIAG_SKEW:
            return False
    elif direction in (0, 4):                           # left/right
        if adx < _DEMON_MIN_RANGE:
            return False
    elif adv < _DEMON_MIN_RANGE:                        # up/down
        return False

    monster_create_shot(state, slot, direction, shot_slot)
    return True


def _neighbor_slot(slot: int, direction: int, wrap: bool = False) -> int | None:
    """The neighbouring cell one step along ``direction``.

    ``wrap`` reproduces the masked arithmetic of 0x41A5A (``andi #0x1F`` on the
    column and ``andi #0x3E0`` on the row), which the demon shot path uses;
    everywhere else an off-grid step is simply rejected.
    """
    row, col = slot >> 5, slot & 0x1F
    step_x, step_y = _DIR_DELTAS[direction]
    nr, nc = row + step_y, col + step_x
    if wrap:
        return ((nr & 0x1F) << 5) | (nc & 0x1F)
    if not (0 <= nr < 32 and 0 <= nc < 32):
        return None
    return (nr << 5) | nc


def _demon_muzzle_clear(state: GameState, slot: int, direction: int) -> bool:
    """0x41A42-0x41AAE -- the cell the shot is launched into must be passable."""
    dest = _neighbor_slot(slot, direction, wrap=True)
    if dest is None or dest < 0x20:
        return False
    if state.mobs.picture[dest] == 0:
        return True
    return state.mobs.obj_type(dest) in _DEMON_SHOT_PASSABLE


def _find_target_player(state: GameState, slot: int) -> int:
    """Nearest active player by |dH| + |dV|, IT evaluated first.

    Distances are the byte deltas of 0x417C8-0x417EA, so they wrap the shorter
    way round the maze.  An invisible player is skipped entirely, IT included.
    The ROM walks the four slots *backwards* (D3 = 6, 4, 2, 0) and only takes a
    strictly closer one, so an exact tie is won by the **higher** player index;
    scanning forwards with ``<=`` is the same rule.
    """
    it = state.player_it
    if (it != 0xFFFF and 0 <= it < len(state.players)
            and state.players[it].active
            and not (state.players[it].powers & _POWER_INVIS)):
        return it

    best = -1
    best_dist = None
    for p in state.players:
        if not p.active or (p.powers & _POWER_INVIS):
            continue
        dx = _delta_units(state.mobs.hpos[p.mob_slot], state.mobs.hpos[slot])
        dv = _delta_units(state.mobs.vpos[p.mob_slot], state.mobs.vpos[slot])
        dist = abs(dx) + abs(dv)
        if best_dist is None or dist <= best_dist:
            best_dist = dist
            best = p.index
    return best


def _find_free_shot_slot(state: GameState, shot_slots: range) -> int | None:
    """``find_unused_shot`` (0x41B16) -- a channel is free when its picture is
    clear *and* the word beside it reads zero.

    That second word is **not** the channel's own cadence timer.  The ROM
    indexes it from 0x904926 with ``slot*2``, three words below
    ``shot_timer_next``'s own base, so channel *n* is gated by the timer
    ``monster_create_shot`` wrote for channel *n+3*, and the top three lobber
    channels index past the end of that array into ``score_display_timer``
    (0x90493A) -- a floating score popup really does hold a lobber channel
    shut.  Reproduced as-is; ``_shot_gate_word`` is where the aliasing lives.
    """
    for s in shot_slots:
        if state.mobs.picture[s] == 0 and _shot_gate_word(state, s) == 0:
            return s
    return None


def _shot_gate_word(state: GameState, slot: int) -> int:
    """The 0x904926-based word ``find_unused_shot`` tests for ``slot``."""
    index = slot - 2                    # (0x904926 + slot*2 - 0x90492A) // 2
    timers = state.shot_timer_next
    if index < len(timers):
        return timers[index]
    popups = state.score_display_timer
    index -= len(timers)
    return popups[index] if index < len(popups) else 0


# Per-direction muzzle offsets, raw ROM position words indexed by the ROM
# compass.  ``monster_shot_spawn_h_offset`` (0x57B98) / ``..._v_offset``
# (0x57BA8) are the demon pair, ``lobber_shot_spawn_h/v_offset`` (0x57BB8/
# 0x57BC8) the lobber pair.  Every entry is a multiple of 0x100 -- a whole
# pixel is 0x80 -- so none of them can disturb the low field of the word they
# are added to, and they are added exactly as the ROM writes them.
_MONSTER_SHOT_SPAWN_H = (0x200, 0x500, 0x600, 0x200, 0x200, 0x000, -0x200, -0x100)
_MONSTER_SHOT_SPAWN_V = (0x500, 0x400, 0x000, 0x000, -0x200, -0x100, 0x000, 0x400)
_LOBBER_SHOT_SPAWN_H = (0x500, 0x300, 0x200, 0x000, 0x000, 0x000, 0x200, 0x300)
_LOBBER_SHOT_SPAWN_V = (0x100, 0x000, 0x000, 0x000, 0x000, 0x300, 0x200, 0x200)

# The constants the ROM adds *underneath* the position field.  0x49192/0x491A2
# mask the shooter's own words with 0xFF80 first, so these are not offsets at
# all -- they are the new projectile's low field.  A demon shot collects
# ``+0xD`` (0x491BA) and then the shared ``+1`` (0x49258), giving H low byte
# 0xE: palette 0xE with no strength bits.  A lobber gets only the ``+1``,
# palette 1.  Both get ``+9`` vertically (0x4926E), which is the packed sprite
# size -- width-1 = height-1 = 1, a 2x2-tile 16x16 px projectile.  gauntpy
# numbers both fields exactly as the ROM does, so the values carry over.
_DEMON_SHOT_HPOS_LOW = 0x0D + 0x01
_LOBBER_SHOT_HPOS_LOW = 0x01
_SHOT_VPOS_LOW = 0x09

#: ``shot_counter_reload`` (0x578C2), one word per shot channel 0-11.
_SHOT_COUNTER_RELOAD = (
    0x000F, 0x0001, 0x0001, 0x0000,      # player channels
    0x0001, 0x0001, 0x0001, 0x0001,      # demon channels
    0x0020, 0x0020, 0x0020, 0x0020,      # lobber channels
)
#: 0x49104 -- frames before that channel may fire again.
_SHOT_COOLDOWN = 0x3C
#: The lobber's flight is a lead: the target's own velocity plus four times the
#: separation.  ``player_speed_normal`` (0x580C8) and the per-direction
#: components at 0x580D8/0x580EA build the first term.
_LEAD_PLAYER_SPEED = (0x60, 0x70, 0x60, 0x80, 0x80, 0x80, 0x80, 0xA0)
_LEAD_COS = (0, 2, 2, 2, 0, -2, -2, -2, 0)  # 0x580D8, index 8 = still
_LEAD_SIN = (2, 2, 0, -2, -2, -2, 0, 2, 0)  # 0x580EA, index 8 = still
# ``joystick_nibble_to_direction`` (0x580FC), indexed by the achieved-movement
# word at 0x9048F0. A neutral 0xF nibble selects 8, the zero-padded table row.
_WALK_NIBBLE_TO_DIRECTION = (
    8, 8, 8, 8, 8, 7, 1, 0, 8, 5, 3, 4, 8, 6, 2, 8,
)
_LEAD_DELTA_SCALE = 4                        # 0x419BC/0x419C6
_LEAD_SPAWN_SCALE = 4                        # 0x419F4/0x41A0C


def monster_create_shot(state: GameState, slot: int, direction: int,
                        shot_slot: int, lead: tuple[int, int] | None = None) -> None:
    """0x490DC -- arm a projectile in one of the fixed monster channels.

    Seeds everything WP-7's mover reads: the channel cadence timer, the
    animation/lifetime counter, the owner cell, the ROM-compass direction, the
    spawn position with its per-direction muzzle offset, the projectile's
    opening frame and its place in the depth chain.  ``lead`` carries the
    lobber's computed arc vector (0x419E4-0x41A10); without it the projectile
    flies straight down its direction, which is what every other family does.

    The spawn position is rebuilt in whole ROM words rather than decoded and
    re-encoded, because the ROM's ``+0xD``/``+1``/``+9`` tails land in the low
    field, not the position field: they are the projectile's palette and its
    packed sprite size, not a pixel offset.  The muzzle offsets are position
    words in the hardware's own axes, so they simply add.
    """
    from .shots import lobber_accumulator_seed, shot_velocity

    channel = shot_slot - 1                    # shooter id, ROM's shot slot - 1
    rom_dir = (direction + 2) & 0x07

    state.shot_timer_next[shot_slot - 5] = _SHOT_COOLDOWN
    state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK          # 0x4910E
    state.shot_anim_lifetime_counter[channel] = _SHOT_COUNTER_RELOAD[channel]
    state.shot_lifetime[shot_slot] = _SHOT_COUNTER_RELOAD[channel]
    # 0x4915C stores the direction WP-7 reads back out of ``shot_direction``,
    # and everything that module indexes with it -- ``shot_velocity_x/y``
    # (0x576E2/0x57792), the projectile picture tables and ``_direction_of``'s
    # own recovery -- is on the ROM compass, not gauntpy's.
    state.shot_direction[channel] = rom_dir
    state.shot_owner_mob[channel] = slot                # active_mob_ids[shot-1]

    # 0x49192/0x491A2: the projectile inherits only the shooter's *position*
    # field -- the shooter's palette (its health nibble) and its 3x3 sprite
    # size are masked off, and the class constants below replace them.
    base_h = position_field(state.mobs.hpos[slot])
    base_v = position_field(state.mobs.vpos[slot])
    if lead is None:
        off_h = _MONSTER_SHOT_SPAWN_H[rom_dir]
        off_v = _MONSTER_SHOT_SPAWN_V[rom_dir]
        hpos_low = _DEMON_SHOT_HPOS_LOW
    else:
        off_h = _LOBBER_SHOT_SPAWN_H[rom_dir]
        off_v = _LOBBER_SHOT_SPAWN_V[rom_dir]
        hpos_low = _LOBBER_SHOT_HPOS_LOW
    state.mobs.hpos[shot_slot] = (base_h + off_h + hpos_low) & 0xFFFF
    state.mobs.vpos[shot_slot] = (base_v + off_v + _SHOT_VPOS_LOW) & 0xFFFF
    state.mobs.picture[shot_slot] = _spawn_shot_picture(state, channel)
    _depth_place_shot(state, shot_slot)

    if lead is None:
        vec_h, vec_v = shot_velocity(state, channel, rom_dir)
        state.shot_dx[shot_slot] = vec_h >> POS_SHIFT
        state.shot_dy[shot_slot] = vec_v >> POS_SHIFT
    else:
        vec_h, vec_v = lead
        state.lobber_shot_vec_h[shot_slot - 9] = vec_h
        state.lobber_shot_vec_v[shot_slot - 9] = vec_v
        # 0x49216/0x4922A -- WP-7 owns the accumulator/MOB-word relationship.
        lobber_accumulator_seed(state, channel)
        # WP-7 moves shots by whole pixels, so round rather than truncate: a
        # lob that leads by 1.5 px/frame otherwise degenerates to 1.
        state.shot_dx[shot_slot] = _round_div(vec_h, 128)
        state.shot_dy[shot_slot] = _round_div(vec_v, 128)


def _depth_place_shot(state: GameState, shot_slot: int) -> None:
    """0x49274-0x492B6 -- key the new channel into the depth chain at its cell.

    The ROM derives the cell from the H/V words it has just written, with the
    same +12/+8 px sprite biases the per-frame re-key uses, and hands both to
    ``insert_mob_depth_sorted``.  Without it the channel's ``mob_depth_key``
    stays zero, and the very next ``main_handle_shots`` probes for collisions
    from cell 0 -- the top-left corner of the maze -- and destroys the shot on
    the frame after it was fired.
    """
    from .shots import shot_cell     # WP-7 owns the shot cell geometry

    state.mobs.unlink(shot_slot)
    state.mobs.insert(shot_slot, depth_key=shot_cell(state, shot_slot))


def _spawn_shot_picture(state: GameState, channel: int) -> int:
    """The frame 0x491D2 (demon) / 0x49238 (lobber) arms a channel with.

    Both are the ordinary projectile animation evaluated at the counter the
    channel was just seeded with, so the projectile is drawn as real artwork
    for the rest of the frame it is created in.  That matters because
    ``main_handle_shots`` (0x474F6) has already run by the time
    ``main_move_monsters`` (0x49034) fires: the picture written here is the one
    the renderer shows until the *next* frame's animation tick.

    The two creation sites read their tables at different counters -- 0x491D8
    hardcodes index 0 for a demon shot (which is where the reload of 1
    pre-decrements to on that next tick), while 0x49240 uses the lobber's
    freshly stored reload -- and neither consults the shot's strength tier,
    which the H word written just above has in any case cleared.
    """
    from .shots import shot_picture   # WP-7 owns the three ROM picture tables

    counter = (_SHOT_COUNTER_RELOAD[channel]
               if channel + 1 in SLOT_LOBBER_SHOTS else 0)
    return shot_picture(state, channel, counter)


def _round_div(value: int, divisor: int) -> int:
    return -((-value + divisor // 2) // divisor) if value < 0 else (value + divisor // 2) // divisor


def _lobber_lead(state: GameState, slot: int, direction: int, target: int,
                 dx: int, dv: int) -> tuple[int, int]:
    """0x41978-0x41A10 -- where the rock is thrown, not where the player is.

    The arc vector is the target's *current* walking velocity plus four times
    the separation, less the muzzle offset -- so a lobber leads a running hero
    and drops the rock where they are heading.
    """
    p = state.players[target]
    speed_row = ((p.character & 0x03)
                 + (4 if p.powers & PlayerPower.SPEED else 0))
    speed = _LEAD_PLAYER_SPEED[speed_row]
    move_nibble = (state.player_walk_dirs[target] >> 4) & 0x0F
    rom_move = _WALK_NIBBLE_TO_DIRECTION[move_nibble]
    vec_h = speed * _LEAD_COS[rom_move]
    vec_v = speed * _LEAD_SIN[rom_move]

    # The separation terms: the ROM adds 2 to the horizontal delta first
    # (0x419BA); both deltas are already in its own axes.
    vec_h += (dx + 2) * _LEAD_DELTA_SCALE
    vec_v += dv * _LEAD_DELTA_SCALE

    rom_dir = (direction + 2) & 0x07
    vec_h -= (_LOBBER_SHOT_SPAWN_H[rom_dir] >> 8) * _LEAD_SPAWN_SCALE
    vec_v -= (_LOBBER_SHOT_SPAWN_V[rom_dir] >> 8) * _LEAD_SPAWN_SCALE
    return _s16(vec_h), _s16(vec_v)


# =============================================================================
# Player contact (0x495A6)
# =============================================================================

def _contact_damage(p, row: int) -> int:  # noqa: ANN001
    """``monster_contact_damage_table[row*4 + character (+0x20 armored)]``.

    The powered half of the 64-word table is the +0x20 (eight-row) block
    (0x497D4-0x49824).  Every live tier of every family lands inside rows 0-7,
    so a row outside that window means the caller was handed a corrupt tier;
    the ROM would read neighbouring data, we deal nothing.
    """
    if not 0 <= row <= 7:
        return 0
    armored = 0x20 if (p.powers & _POWER_ARMOR) else 0
    return _MONSTER_CONTACT_DAMAGE_TBL[row * 4 + (p.character & 0x03) + armored]


def monster_playerhit(state: GameState, player_index: int,
                      monster_slot: int) -> None:
    """0x495A6 -- resolve a monster walking into a player (§3.7).

    The damage row scales with the creature's *live* strength tier:
    ``row = (hpos & 0xF) - mazeobj_hsize_tier_tbl[type] + 2 + offset``, where
    the offset comes from the ten-way jump table at 0x49620.  Four families are
    not on the damage path at all: a lobber's handler is the empty epilogue
    (0x49A32), IT tags instead of hurting (0x4967A), and ghosts and acid are
    consumed by the contact and pay out score.
    """
    obj_type = state.mobs.obj_type(monster_slot)
    if obj_type not in MONSTER_TYPES:
        return

    tier = state.mobs.hpos[monster_slot] & 0x0F
    row = tier - _MAZEOBJ_HSIZE_TIER.get(obj_type, 0) + 2

    if obj_type == int(MazeObjIds.MONST_IT):
        _it_tag(state, player_index, monster_slot)
        return

    offset = _CONTACT_ROW_OFFSET.get(obj_type)
    if offset is None:
        return          # lobber: no contact damage, only its thrown rocks hurt
    row += offset

    if obj_type == int(MazeObjIds.MONST_GHOST):
        # 0x49634: the ghost explodes on contact, pays (row+1)*10, and only
        # then applies its damage -- no attack-state windup for ghosts.
        state.mobs.unlink_and_clear(monster_slot)
        player_add_score_with_mult(state, player_index, (row + 1) * 10)
        _contact_apply(state, player_index, monster_slot, obj_type, row)
        return

    if obj_type in (int(MazeObjIds.MONST_DEATH),
                    int(MazeObjIds.MONST_SUPERSORC)):
        # 0x4970A -- Death and the Super Sorcerer share one handler; both bump
        # the looping death-touch timer before the damage gate.
        _death_touch_update(state, player_index)

    # Attack-state windup (0x498EE): a creature that is not yet in its moving
    # state only *enters* it on this contact and deals nothing this frame.
    if not (state.mobs.hpos[monster_slot] & _HPOS_FLAG_MOVING):
        state.mobs.hpos[monster_slot] |= _HPOS_FLAG_MOVING
        if obj_type == int(MazeObjIds.MONST_ACID):
            _acid_windup(state, player_index, monster_slot, row)
        return

    if (obj_type == int(MazeObjIds.MONST_ACID)
            and (state.mobs.state_link[monster_slot] & 0xE000)):
        return          # 0x49904: the puddle is mid-animation, no damage yet

    _contact_apply(state, player_index, monster_slot, obj_type, row)


def _contact_apply(state: GameState, player_index: int, monster_slot: int,
                   obj_type: int, row: int) -> None:
    """0x4977E-0x498EA -- charge the hit and run its side effects."""
    p = state.players[player_index]
    p.hurt_cooldown = _HURT_COOLDOWN

    if obj_type == int(MazeObjIds.MONST_DEATH):
        # 0x4979E: Death also feeds the per-player Death-damage counter, which
        # dismisses the MOB past 200 (§3.6 / §26).  The amount is read from the
        # same contact table: row 6 column 0, or row 14 when armored -- 4 / 3.
        index = (_DEATH_DAMAGE_ROW_ARMORED if (p.powers & _POWER_ARMOR)
                 else _DEATH_DAMAGE_ROW)
        death_damage_accumulate(state, player_index, monster_slot,
                                _MONSTER_CONTACT_DAMAGE_TBL[index])

    if p.acid_timer == 0:                       # 0x497EE: acid grants immunity
        damage = _contact_damage(p, row)
        p.health = max(0, p.health - damage)
        p.pending_damage += damage
        state.health_dirty[player_index] = 1    # player_redraw |= 2
        # 0x4986A: the once-per-game "you have met a ..." box, keyed by the
        # family mask the jump table loaded into A4, with the damage as its
        # numeric field.
        mask = _FIRST_ENCOUNTER_MASK.get(obj_type)
        if mask is not None:
            dialog_first_encounter(state, player_index, mask, damage)
        if obj_type == int(MazeObjIds.MONST_GHOST):
            _sound_play(state, _SOUND_GHOST_HIT)            # 0x1F
        elif obj_type != int(MazeObjIds.MONST_DEATH):
            _sound_play(state, _SOUND_MONSTER_HIT)          # 0x1E
    else:
        # 0x49892: the branch taken at 0x497F8 lands past the damage, the
        # dialog and the sound and runs one extra test -- being touched while
        # the invulnerability/affliction timer is up fails "don't use
        # invulnerability", so the level's progress byte is cleared.  The
        # damage path never reaches this (0x49890 jumps over it).
        secret_trick_set(state, player_index, TRICK_NOUSEINVUL, 0)

    if obj_type == int(MazeObjIds.MONST_ACID):
        # 0x498AE: the puddle is used up by the splash and pays 30 points.
        state.mobs.unlink_and_clear(monster_slot)
        player_add_score_with_mult(state, player_index, _ACID_CONTACT_SCORE)

    # 0x498D6: any contact resets the trap-wall escape timer and wakes the
    # idle timer that opens timed doors.
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0


def _acid_windup(state: GameState, player_index: int, monster_slot: int,
                 row: int) -> None:
    """0x49922 -- the frame a puddle latches onto a player.

    In attract mode (``game_mode`` negative) the splash resolves immediately:
    the puddle is removed and its damage charged without the armor bias
    (0x499BC).  In play it stuns for 0x20 frames, turns to face the victim and
    starts its splash animation with sound 0x36 (0x4993E).

    The ROM also seeds the state word's animation counter here, which is what
    the ``& 0xE000`` gate above waits on; the puddle's own attack branch
    (0x413E6) advances it every 32nd frame, so the splash resolves a beat after
    the latch rather than on the same frame.
    """
    p = state.players[player_index]
    if state.game_mode < 0:
        state.mobs.unlink_and_clear(monster_slot)
        if 0 <= row <= 7:
            damage = _MONSTER_CONTACT_DAMAGE_TBL[row * 4 + (p.character & 0x03)]
            p.health = max(0, p.health - damage)
            state.health_dirty[player_index] = 1
            dialog_first_encounter(
                state, player_index,
                _FIRST_ENCOUNTER_MASK[int(MazeObjIds.MONST_ACID)],
                damage,
            )
        return

    p.stundelay = 0x20
    dx = _delta_units(state.mobs.hpos[p.mob_slot], state.mobs.hpos[monster_slot])
    dv = _delta_units(state.mobs.vpos[p.mob_slot], state.mobs.vpos[monster_slot])
    _set_direction(state, monster_slot, _aim_direction(dx, dv, 0, 4))
    if p.acid_timer == 0:
        _sound_play(state, _SOUND_ACID_SLIME)   # 0x36


def _death_touch_update(state: GameState, player_index: int) -> None:
    """0x49712-0x49752 -- arm/refresh the looping death-touch sound timer."""
    p = state.players[player_index]
    timer = state.death_touch_timer[player_index]
    if p.acid_timer != 0:
        state.death_touch_timer[player_index] = _DEATH_TOUCH_WHILE_ACID
    elif timer == 0:
        state.death_touch_timer[player_index] = _DEATH_TOUCH_NEW   # 0xFFF0
    elif 0 < timer < _DEATH_TOUCH_REFRESH:
        state.death_touch_timer[player_index] = _DEATH_TOUCH_REFRESH


def _it_tag(state: GameState, player_index: int, monster_slot: int) -> None:
    """0x4967A -- touching IT transfers the curse instead of dealing damage.

    The ROM also swaps the on-screen IT name label here (0x4590E clears the old
    holder's, 0x45866 sets the new one); synchronize those two alpha cells here.
    """
    p = state.players[player_index]
    _sound_play(state, _SOUND_IT_TAG)           # 0x35
    # 0x496AC: the "be IT" challenge only needs one tag, and the bump lands
    # before player_it is reassigned, so the *new* holder is credited.
    secret_trick_progress(state, player_index, _TRICK_TASK_WHILE_IT)
    state.player_it = player_index
    from .score import write_it_labels
    write_it_labels(state)
    state.mobs.unlink_and_clear(monster_slot)
    p.stundelay = _IT_TAG_STUN
    player_add_score_with_mult(state, player_index, _IT_TAG_SCORE)
    dialog_first_encounter(state, player_index, _IT_ENCOUNTER_MASK)   # 0x496F4
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0


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
    idx = max(0, min(idx, len(_SPAWN_PROB_TABLE) - 1))
    prob = _SPAWN_PROB_TABLE[idx] + _signed_byte(state.spawn_probability_bonus)
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
                       _GEN_CANDIDATE_DIR[index])
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
    row = ((gen_slot & 0x3E0) + _GEN_CANDIDATE_ROW[index]) & 0x3E0
    col = (gen_slot + _GEN_CANDIDATE_COL[index]) & 0x1F
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
        neighbour = ((slot & 0x3E0) + _OCCUPANCY_NEIGHBOUR_ROW[index]
                     + ((slot + _OCCUPANCY_NEIGHBOUR_COL[index]) & 0x1F))
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
_SUPERSORC_BIAS = (0, -1, 1)
_SUPERSORC_RUN = (4, 3, 3)
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


def _tile_on_screen(state: GameState, slot: int) -> bool:
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
        dest = _supersorc_place(state, slot)
        if dest is None:
            return
        _anim_add_high(state, dest, 0xE0)       # 0x410B8
        state.mobs.hpos[dest] &= ~(_HPOS_FLAG_MOVING | _HPOS_FLAG_ATTACK)
        _refresh_monster_picture(
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
    shot_slot = _find_free_shot_slot(state, SLOT_DEMON_SHOTS)
    if shot_slot is None:
        _anim_add_high(state, slot, 0x80)       # 0x4114C: try again sooner
        return
    monster_create_shot(state, slot, _get_direction(state, slot), shot_slot)
    state.mobs.hpos[shot_slot] |= _HPOS_FLAG_ATTACK      # 0x41178
    _anim_add_high(state, slot, 0x40)                     # 0x4117E
    state.mobs.hpos[slot] |= _HPOS_FLAG_MOVING
    state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK


def _supersorc_place(state: GameState, slot: int) -> int | None:
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

        px = hpos_x(state.mobs.hpos[p.mob_slot])
        py = vpos_y(state.mobs.vpos[p.mob_slot])
        prow, pcol = py >> 4, px >> 4
        behind = (p.direction + 4) & 0x07

        for bias, run in zip(_SUPERSORC_BIAS, _SUPERSORC_RUN):
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
        if not _tile_on_screen(state, cell):
            return None
    dest = (r << 5) | c
    if _supersorc_too_crowded(state, dest, slot):
        return None
    return dest


def _supersorc_too_crowded(state: GameState, dest: int, self_slot: int) -> bool:
    """True if another MOB sits within the proximity box of ``dest``.

    The ROM walks the eight neighbouring cells (``spawn_candidate_*_delta``,
    0x578A2/0x578B2) and tests whichever of them hold a picture; every MOB
    close enough to matter is in one of those cells, so the depth-chain scan
    here reaches the same set.
    """
    dest_h = ((dest & 0x1F) * 16) << POS_SHIFT
    dest_v = native_v((dest >> 5) * 16) << POS_SHIFT
    for s in state.mobs.iter_chain():
        if s == self_slot or state.mobs.picture[s] == 0:
            continue
        if (abs(position_field(state.mobs.hpos[s]) - dest_h) <= _SUPERSORC_PROXIMITY
                and abs(position_field(state.mobs.vpos[s]) - dest_v)
                <= _SUPERSORC_PROXIMITY):
            return True
    return False


def _supersorc_relocate(state: GameState, slot: int, dest: int,
                        direction: int) -> None:
    """Move the Super Sorcerer's record to ``dest`` and face ``direction``.

    0x5FF2C keeps the low seven bits of both position words -- the flags and
    the palette/tier nibble -- and only rewrites the cell part.
    """
    if dest == slot:
        _set_direction(state, slot, direction)
        return
    if state.mobs.is_occupied(dest):
        return
    if state.monster_iter_ptr == slot:      # 0x410A6: keep the walk marker live
        state.monster_iter_ptr = dest
    low_h = low_field(state.mobs.hpos[slot])
    low_v = low_field(state.mobs.vpos[slot])
    x = (dest & 0x1F) * 16
    y = (dest >> 5) * 16
    state.mobs.move_slot(slot, dest)
    state.mobs.hpos[dest] = replace_position(low_h, encode_hpos(x))
    state.mobs.vpos[dest] = replace_position(
        low_v, encode_vpos_at_y(y),
    )
    _set_direction(state, dest, direction)
