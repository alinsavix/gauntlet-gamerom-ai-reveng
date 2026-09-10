"""Monsters and generators -- WP-8.

Traversal, dispatch, and contact logic stay here. Movement, shooting, and
spawning families are imported from their own modules without wrapper calls.

Reference: ``doc/04_game_subsystems.md`` §3 (all of it);
``doc/generated/monster_combat_contracts.csv``; ``book/04_the_horde.md``.

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
from .score import player_add_score_with_mult
from .score import dialog_first_encounter
from .shots import death_damage_accumulate
from .sound import sound_play as _sound_play


# Compatibility exports; each routine and table has a single game-side owner.
from .monster_data import (
    _BLANK_PICTURE as _BLANK_PICTURE,
    _DIR_DELTAS as _DIR_DELTAS,
    _HPOS_FLAG_ATTACK as _HPOS_FLAG_ATTACK,
    _HPOS_FLAG_MOVING as _HPOS_FLAG_MOVING,
    _MAZEOBJ_HSIZE_TIER_TBL as _MAZEOBJ_HSIZE_TIER_TBL,
    _MONSTER_ODDANGLE_TABLE as _MONSTER_ODDANGLE_TABLE,
    _OVERLAP as _OVERLAP,
    _SOFTWARE_MOB_BIAS as _SOFTWARE_MOB_BIAS,
)
from .monster_movement import (
    _BLINK_ANIM_BUMP as _BLINK_ANIM_BUMP,
    _EDGE_TOP_LIMIT as _EDGE_TOP_LIMIT,
    _PROBE_DOWN as _PROBE_DOWN,
    _PROBE_LEFT as _PROBE_LEFT,
    _PROBE_RIGHT as _PROBE_RIGHT,
    _PROBE_UP as _PROBE_UP,
    _cell_at as _cell_at,
    _cell_player_index as _cell_player_index,
    _commit_move as _commit_move,
    _destination_cell as _destination_cell,
    _is_player_cell as _is_player_cell,
    _march_cell_blocks as _march_cell_blocks,
    _march_hit_player as _march_hit_player,
    _monster_move_engine as _monster_move_engine,
    _move_tail as _move_tail,
    _probe_phase as _probe_phase,
    _ray_march as _ray_march,
    _s16 as _s16,
    _write_direction as _write_direction,
    apply_direction_from_delta as apply_direction_from_delta,
)
from .monster_shooting import (
    _DEMON_DIAG_SKEW as _DEMON_DIAG_SKEW,
    _DEMON_MIN_RANGE as _DEMON_MIN_RANGE,
    _DEMON_SHOT_HPOS_LOW as _DEMON_SHOT_HPOS_LOW,
    _DEMON_SHOT_PASSABLE as _DEMON_SHOT_PASSABLE,
    _JOYSTICK_NIBBLE_TO_DIRECTION as _JOYSTICK_NIBBLE_TO_DIRECTION,
    _LEAD_COS as _LEAD_COS,
    _LEAD_DELTA_SCALE as _LEAD_DELTA_SCALE,
    _LEAD_PLAYER_SPEED as _LEAD_PLAYER_SPEED,
    _LEAD_SIN as _LEAD_SIN,
    _LEAD_SPAWN_SCALE as _LEAD_SPAWN_SCALE,
    _LOBBER_MAX_RANGE as _LOBBER_MAX_RANGE,
    _LOBBER_MIN_RANGE as _LOBBER_MIN_RANGE,
    _LOBBER_SHOT_HPOS_LOW as _LOBBER_SHOT_HPOS_LOW,
    _LOBBER_SHOT_SPAWN_H as _LOBBER_SHOT_SPAWN_H,
    _LOBBER_SHOT_SPAWN_V as _LOBBER_SHOT_SPAWN_V,
    _MONSTER_SHOOT_AXIS_THRESHOLDS as _MONSTER_SHOOT_AXIS_THRESHOLDS,
    _MONSTER_SHOT_SPAWN_H as _MONSTER_SHOT_SPAWN_H,
    _MONSTER_SHOT_SPAWN_V as _MONSTER_SHOT_SPAWN_V,
    _POWER_INVIS as _POWER_INVIS,
    _POWER_REPULSE as _POWER_REPULSE,
    _SHOT_COOLDOWN as _SHOT_COOLDOWN,
    _SHOT_COUNTER_RELOAD as _SHOT_COUNTER_RELOAD,
    _SHOT_VPOS_LOW as _SHOT_VPOS_LOW,
    _SOUND_LOBBER_THROW as _SOUND_LOBBER_THROW,
    _demon_muzzle_clear as _demon_muzzle_clear,
    _demon_shoot as _demon_shoot,
    _depth_place_shot as _depth_place_shot,
    _find_target_player as _find_target_player,
    _lobber_lead as _lobber_lead,
    _lobber_throw as _lobber_throw,
    _neighbor_slot as _neighbor_slot,
    _round_div as _round_div,
    _shot_gate_word as _shot_gate_word,
    _spawn_shot_picture as _spawn_shot_picture,
    find_unused_shot as find_unused_shot,
    monster_create_shot as monster_create_shot,
    monster_find_and_shoot as monster_find_and_shoot,
)
from .monster_spawning import (
    _GENERATOR_CELL_DX as _GENERATOR_CELL_DX,
    _GENERATOR_CELL_DY as _GENERATOR_CELL_DY,
    _GENERATOR_SPAWN as _GENERATOR_SPAWN,
    _GENERATOR_SPAWN_DIRECTION as _GENERATOR_SPAWN_DIRECTION,
    _GENERATOR_TIER_PENALTY as _GENERATOR_TIER_PENALTY,
    _GEN_ATTRACT_GHOST_FAMILIES as _GEN_ATTRACT_GHOST_FAMILIES,
    _GEN_ATTRACT_START_GHOST as _GEN_ATTRACT_START_GHOST,
    _GEN_ATTRACT_START_OTHER as _GEN_ATTRACT_START_OTHER,
    _GEN_CANDIDATE_COUNT as _GEN_CANDIDATE_COUNT,
    _GEN_START_BOUND as _GEN_START_BOUND,
    _MAZEOBJ_VSIZE as _MAZEOBJ_VSIZE,
    _MONSTER_SPAWN_PROBABILITY_TABLE as _MONSTER_SPAWN_PROBABILITY_TABLE,
    _MONSTER_WALK_PICTURES as _MONSTER_WALK_PICTURES,
    _OCCUPANCY_MAX_SLOT as _OCCUPANCY_MAX_SLOT,
    _OCCUPANCY_MIN_SLOT as _OCCUPANCY_MIN_SLOT,
    _ONSCREEN_H_SPAN as _ONSCREEN_H_SPAN,
    _ONSCREEN_V_SPAN as _ONSCREEN_V_SPAN,
    _SPAWN_CANDIDATE_COLUMN_DELTA as _SPAWN_CANDIDATE_COLUMN_DELTA,
    _SPAWN_CANDIDATE_ROW_DELTA as _SPAWN_CANDIDATE_ROW_DELTA,
    _SPAWN_HEALTH as _SPAWN_HEALTH,
    _SPAWN_HPOS_CORRECTION as _SPAWN_HPOS_CORRECTION,
    _SUPERSORC_DIRECTION_BIAS as _SUPERSORC_DIRECTION_BIAS,
    _SUPERSORC_PROBE_STEPS as _SUPERSORC_PROBE_STEPS,
    _SUPERSORC_PROXIMITY as _SUPERSORC_PROXIMITY,
    _handle_generator as _handle_generator,
    _rendered_occupant as _rendered_occupant,
    _spawn_monster as _spawn_monster,
    _spawn_probability as _spawn_probability,
    _supersorc_candidate as _supersorc_candidate,
    _supersorc_dispatch as _supersorc_dispatch,
    _supersorc_relocate as _supersorc_relocate,
    _supersorc_shoot as _supersorc_shoot,
    _supersorc_too_crowded as _supersorc_too_crowded,
    generator_candidate_slot as generator_candidate_slot,
    handle_generate as handle_generate,
    monster_walk_picture as monster_walk_picture,
    supersorc_place as supersorc_place,
    tile_occupancy_test as tile_occupancy_test,
    tile_on_screen_d4 as tile_on_screen_d4,
)

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

# Contact-hurt feedback, from monster_playerhit (0x49876-0x4988A / 0x4967A).
_SOUND_MONSTER_HIT = 0x1E       # "Monster Hits Player"
_SOUND_GHOST_HIT = 0x1F         # "Ghost Hits Player" (type 18 only)
_SOUND_IT_TAG = 0x35            # "Player Touches IT"
_SOUND_ACID_SLIME = 0x36        # "Acid Puddle Slimes Player"
_HURT_COOLDOWN = 0x12           # hurt_cooldown reload (0x49788)

# player_hurt_speech_timer, ROM 0x49A98. The four longword sound-ID banks at
# 0x57AAE are selected by player_character; 0x57B4C gives their exact lengths.
_CHARACTER_HURT_SOUND_BANKS = (
    (0x83, 0x84, 0x85, 0x86),
    (0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB2, 0xB3, 0xB4),
    (0x6D, 0x6E, 0x70, 0x72, 0x73, 0x74, 0x75, 0x95, 0x96, 0x97),
    (0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x79, 0x7E, 0x7F, 0x80),
)
# hurt_speech_cooldown_base, ROM 0x57B32, indexed by active player count.
_HURT_SPEECH_COOLDOWN_BASE = (0, 8, 12, 14, 20)

# Acid acts once every 32 frames: (frame_word & 0x1E) == 0 (0x413E6).
_ACID_RATE_MASK = 0x1E
_POWER_ARMOR = PlayerPower.ARMOR        # selects the powered half of a table

# monster_contact_damage_table -- transcribed from ROM 0x57A2E (row76.bin
# offset 0x17A2E), 64 words = 16 rows × 4 character columns (Warrior, Valkyrie,
# Wizard, Elf).  Rows 0-7 are the eight unpowered contact classes; rows 8-15 are
# the powered-player half (lower damage).  Valkyrie (col 1) always takes the
# least, Wizard (col 2) the most.  §3.7.
_MONSTER_CONTACT_DAMAGE_TABLE = [
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

# Secret-room progress (§10.6).  ``secret_trick_id`` (gex ``secret_trick_id``,
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
#: 0x44A76 -- ``attract_demo_init`` loads ``monster_generation_retry_timer``.
GENERATOR_RETRY_RELOAD = 4


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


def monster_update_anim_tile(
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
    state.monster_cull_h_origin = ((state.scroll_x - _CULL_H_BIAS) << POS_SHIFT) & 0xFFFF
    state.monster_cull_v_origin = ((_CULL_V_BIAS - state.scroll_y) << POS_SHIFT) & 0xFFFF


def _in_cull_rect(state: GameState, slot: int) -> bool:
    """0x40FF6-0x4101A -- whether a creature is processed at all this frame."""
    if ((state.mobs.hpos[slot] - state.monster_cull_h_origin) & 0xFFFF) >= _CULL_WIDTH:
        return False
    return ((state.mobs.vpos[slot] - state.monster_cull_v_origin) & 0xFFFF) < _CULL_HEIGHT


def monster_shooter_in_view(state: GameState, slot: int) -> bool:
    """``monster_shooter_in_view`` (0x41B52) -- the tighter shooting box.

    Byte comparisons against the same origins, so the units are 2 pixels and
    the arithmetic wraps once per 512-pixel maze.
    """
    du = ((state.mobs.hpos[slot] >> 8) - (state.monster_cull_h_origin >> 8)) & 0xFF
    if du <= _VIEW_H_MIN or du >= _VIEW_H_MAX:
        return False
    dv = ((state.mobs.vpos[slot] >> 8) - (state.monster_cull_v_origin >> 8)) & 0xFF
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

    # monsters_everything 0x40E9A branches to the potion scan instead of its
    # ordinary walk while the one-field color latch differs from the level
    # floor color. This keeps surviving/revealed targets from acting afterward.
    if state.playfield_color_latch != state.playfield_color_base:
        from .potions import potion_blast

        owner = state.potion_player & 0x03
        potion_blast(
            state, owner, shot_triggered=bool(state.potion_player & 0x04),
        )
        return

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
            monster_update_anim_tile(state, slot, obj_type)
    else:
        _dispatch_monster(state, slot, obj_type, frame_word)
        if state.mobs.obj_type(slot) == obj_type:
            monster_update_anim_tile(state, slot, obj_type)


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
    # 0x49076/0x490AC mask the scroll-relative coordinate with 0x1F0 before
    # indexing the word table at 0x905F82.  The mask wraps the scan window at
    # the vertical maze seam.  MobTable's band indices are already shifted one
    # entry earlier than the ROM's biased tail view (see mob.py).
    band = ((mid_y + offset) & 0x1F0) // _SLIP_BAND_PIXELS
    heads = state.mobs.slip_heads
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
        _anim_add_high(state, slot, _MONSTER_ODDANGLE_TABLE[index][3])
        _monster_move_engine(state, slot, obj_type, index, frame_word)
        return

    if hpos & _HPOS_FLAG_ATTACK:
        # 0x411CC -- winding up.  IT and acid have their own gates, the
        # sorcerer skips straight to the mover, everyone else fires when the
        # wind-up animation completes.
        if obj_type == int(MazeObjIds.MONST_IT):                   # 0x413F0
            _anim_finish_attack(state, slot, index,
                                _MONSTER_ODDANGLE_TABLE[index][1], frame_word)
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
    _anim_add_high(state, slot, _MONSTER_ODDANGLE_TABLE[index][2])


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
    return _MONSTER_CONTACT_DAMAGE_TABLE[row * 4 + (p.character & 0x03) + armored]


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
    row = tier - _MAZEOBJ_HSIZE_TIER_TBL.get(obj_type, 0) + 2

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
                                _MONSTER_CONTACT_DAMAGE_TABLE[index])

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

    player_hurt_speech_timer(state, player_index)         # 0x498D0

    # 0x498D6: any contact resets the trap-wall escape timer and wakes the
    # idle timer that opens timed doors.
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0


def player_hurt_speech_timer(state: GameState, player_index: int) -> None:
    """0x49A98 -- tick and, on expiry, announce one hurt voice.

    The cooldown is reloaded before the acid-affliction test, so an acid-slowed
    player consumes only the first random draw and remains silent. Ordinary
    expiry then draws once more from the selected character's literal sound
    bank and submits that command through the normal sound path.
    """
    timer = (state.hurt_speech_timer[player_index] - 1) & 0xFFFF
    state.hurt_speech_timer[player_index] = timer
    if not timer & 0x8000:
        return

    active = max(0, min(int(state.level_players_active), 4))
    state.hurt_speech_timer[player_index] = (
        state.getrandom(8) + _HURT_SPEECH_COOLDOWN_BASE[active]
    ) & 0xFFFF

    if state.players[player_index].acid_timer:
        return

    character = int(state.players[player_index].character) & 0x03
    sounds = _CHARACTER_HURT_SOUND_BANKS[character]
    _sound_play(state, sounds[state.getrandom(len(sounds))])


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
            damage = _MONSTER_CONTACT_DAMAGE_TABLE[row * 4 + (p.character & 0x03)]
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
