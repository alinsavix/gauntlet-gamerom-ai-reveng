"""Projectiles and hit resolution -- WP-7.

Twelve fixed channels: player shots in MOB slots 1-4, ordinary monster shots
5-8, lobbed rocks 9-12.  Fixed slots mean no allocation and no search
-- that is the design, not an optimization to add later.  A channel's
*shooter id* is ``slot - 1``, which is how every ROM table below is indexed.
The dragon has no channels of its own: ``dragon_find_free_shot_slot``
(0x540E8) hands its fire one of the monster channels 5-8.

Reference: ``doc/04_game_subsystems.md`` §26, §3.6, §23;
``doc/generated/monster_combat_contracts.csv``; ``book/11_monsters.md``.
Every table here is transcribed from ``row76.bin`` (game address ``A`` at file
offset ``A - 0x40000``, big-endian) and every routine follows the
corresponding disassembly rather than the prose.

**Units.**  The MOB position field is the hardware's own ``pixel << 7``, so
every ROM constant that is added to or compared against a position word --
velocity vectors included -- is used here exactly as the ROM writes it.

**Follow-ups owned elsewhere.**  The ROM's shot creators seed three words this
module then owns; ``main_handle_shots`` still latches them on the frame a
channel goes live for anything that arms a channel by hand.  When WP-8/WP-9
next touch them:

  * ``monsters.monster_create_shot`` writes ``state.shot_direction[ch]``
    (0x9049C4), ``state.shot_anim_lifetime_counter[ch]`` from
    ``shot_counter_reload`` (ROM 0x490FE), ``state.shot_owner_mob[ch]`` with
    the firing monster's MOB slot (``active_mob_ids``, 0x9048C8), reloads
    ``state.shot_timer_next[ch]``, and for a lobber seeds
    ``lobber_shot_vec_h/v`` plus the two accumulators (0x49216/0x4922A);
  * ``dragon.dragon_fire_setup`` does the same for its own channels
    (ROM 0x5480E/0x548A4) -- note the dragon fires into the *demon* channels
    4-7, not 8-11: ``dragon_find_free_shot_slot`` (0x540E8) scans MOB slots
    8 down to 5;
  * the playfield renderer should draw a damaged destructible wall from
    ``state.destructible_wall_stage``: on a shrub level (``wallpattern >= 6``)
    ``wall_crumble_descriptor`` gives the stamp record, elsewhere
    ``wall_crumble_palette`` gives the tile's palette nibble.
"""

from __future__ import annotations

from ..constants import MazeObjIds
from ..coords import (
    POS_FIELD_MASK, POS_SHIFT,
    hpos_x, position_field, replace_position, vpos_y,
)
from ..state import GameState

CONSUMED = -1      # resolve_shot_hit: mob_unlink(shooter) + picture cleared
SURVIVES = 0       # resolve_shot_hit: pierce / reflect / no effect


# =============================================================================
# Tables (ROM literals)
# =============================================================================

# shot_damage_base_tbl -- ROM 0x596B6, 12 bytes.  Index = shot class =
# player_character (0-3), +8 with the shot-power upgrade.  §26.
_SHOT_DAMAGE_BASE_TBL = [
    2, 1, 1, 1,   # 0-3:  Warrior, Valkyrie, Wizard, Elf (base)
    1, 1, 1, 1,   # 4-7:  monster shot classes reach here with class = shooter
    2, 2, 2, 2,   # 8-11: upgraded (Warrior+, Valkyrie+, Wizard+, Elf+)
]

# shot_damage_rand_tbl -- ROM 0x596C2, 12 bytes.  A non-zero entry means the
# class adds getrandom(2): classes 2 (Wizard) and 8 (Warrior + shot power).
_SHOT_DAMAGE_RAND_TBL = [
    0, 0, 1, 0,
    0, 0, 0, 0,
    1, 0, 0, 0,
]

# player_powers bit 4 = shot-power upgrade (0x4AFCE tests byte 1 bit 4).  §26.
_POWER_SHOTPOWER = 0x10
# player_powers bit 1 = armour (0x4B1B6), bit 10 = reflect (0x4B4B0).
_POWER_ARMOR = 0x02
_POWER_REFLECT = 0x400

# Supershot forces damage 3 regardless of class (0x4B00E).  §26.
_SUPERSHOT_DAMAGE = 3

# monstshot_damage_tbl -- ROM 0x596CE, 40 bytes = 10 rows x 4 character
# columns (Warrior, Valkyrie, Wizard, Elf).  The row index the ROM builds at
# 0x4B1AC-0x4B238 is exactly
#     character + 4*armour + tier
# with ``tier`` selected from the *shot's* hpos bits 4-5 (0x30 -> 0x20,
# 0x20 -> 0x18, 0x10 -> 0x10) and, when those bits are clear, 8 for a
# special/dragon channel (shooter >= 8) or 0 otherwise.
_MONSTSHOT_DAMAGE_TBL = [
    4, 3, 5, 4,       # 0x00  ordinary monster shot
    3, 2, 4, 3,       # 0x04  ... armoured
    3, 3, 3, 3,       # 0x08  special/dragon channel
    2, 2, 2, 2,       # 0x0C  ... armoured
    12, 10, 15, 13,   # 0x10  shot tier 1
    9, 7, 12, 10,     # 0x14  ... armoured
    8, 7, 10, 9,      # 0x18  shot tier 2
    7, 6, 9, 8,       # 0x1C  ... armoured
    8, 7, 10, 9,      # 0x20  shot tier 3
    7, 6, 9, 8,       # 0x24  ... armoured
]

# mazeobj_hsize_tier_tbl -- ROM 0x5864C, 64 bytes indexed by object type.  The
# low nibble of hpos is the MOB palette; for monsters it doubles as the
# three-step health/tier value, live while it stays in ``[base-2, base]``.
_MAZEOBJ_HSIZE_TIER_TBL = [
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x04, 0x04, 0x08, 0x0B, 0x0B, 0x04,
    0x00, 0x01, 0x0B, 0x08, 0x05, 0x05, 0x05, 0x05,
    0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05,
    0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x08, 0x01, 0x00, 0x00,
]

# mazeobj_base_picture_tbl -- ROM 0x5868C, 64 words.  Generator degradation
# (0x4BD5A) and the secret-wall prize (0x4B5D8) both read it.
_MAZEOBJ_BASE_PICTURE_TBL = [
    0x0000, 0x8001, 0x8000, 0x20F6, 0x8000, 0x8000, 0x0000, 0x8000,
    0x8000, 0x8000, 0x8001, 0x8001, 0x8001, 0x9D3C, 0x9D7C, 0x1E0D,
    0x8001, 0x8001, 0x0800, 0x09E1, 0x183F, 0x1B57, 0x13A2, 0x09E1,
    0x1A75, 0x2300, 0x13A2, 0x2600, 0x09AB, 0x09B4, 0x09BD, 0x09C6,
    0x09CF, 0x09D8, 0x09C6, 0x09CF, 0x09D8, 0x09C6, 0x09CF, 0x09D8,
    0x09C6, 0x09CF, 0x09D8, 0x09C6, 0x09CF, 0x09D8, 0x0987, 0x25E4,
    0x09A2, 0x0963, 0x096C, 0x88FC, 0x89FC, 0x8AFC, 0x1700, 0x26FC,
    0x24FC, 0x23FC, 0x2788, 0x2784, 0xA740, 0x0BFC, 0x8001, 0x0C3F,
]

# shot_counter_reload -- ROM 0x578C2, 12 words.  Player channels index it by
# character; channels 4-11 index it by channel.
_SHOT_COUNTER_RELOAD = [
    0x0F, 0x01, 0x01, 0x00, 0x01, 0x01,
    0x01, 0x01, 0x20, 0x20, 0x20, 0x20,
]

# shot_velocity_x / shot_velocity_y -- ROM 0x576E2 / 0x57792, 88 signed words
# each, 11 rows of 8 directions.  Rows 0-3 are the four characters, row 4 the
# ordinary monster shot (+0x20), rows 5-8 the shot-speed set (+0x28), row 9
# the tier-2 monster shot (+0x48) and row 10 the max-tier shot (+0x50).
#
# The ROM stores positions and velocities in native ``<< 7`` words, and so do
# we, so both tables are the literal ROM data.  The V axis grows up the screen
# in both, so ``shot_velocity`` returns entry Y unchanged.
_SHOT_VELOCITY_X = [
    0, 256, 384, 256, 0, -256, -384, -256,
    0, 384, 512, 384, 0, -384, -512, -384,
    0, 384, 512, 384, 0, -384, -512, -384,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 256, 384, 256, 0, -256, -384, -256,
    0, 384, 512, 384, 0, -384, -512, -384,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 640, 896, 640, 0, -640, -896, -640,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 128, 256, 128, 0, -128, -256, -128,
]
_SHOT_VELOCITY_Y = [
    384, 256, 0, -256, -384, -256, 0, 256,
    512, 384, 0, -384, -512, -384, 0, 384,
    512, 384, 0, -384, -512, -384, 0, 384,
    640, 512, 0, -512, -640, -512, 0, 512,
    384, 256, 0, -256, -384, -256, 0, 256,
    512, 384, 0, -384, -512, -384, 0, 384,
    640, 512, 0, -512, -640, -512, 0, 512,
    640, 512, 0, -512, -640, -512, 0, 512,
    896, 640, 0, -640, -896, -640, 0, 640,
    640, 512, 0, -512, -640, -512, 0, 512,
    256, 128, 0, -128, -256, -128, 0, 128,
]
_VEL_MONSTER_BASE = 0x20     # ordinary monster shot rows
_VEL_SHOTSPEED = 0x28        # player shot-speed rows
_VEL_MONSTER_TIER2 = 0x48    # monster shot with hpos bit 5
_VEL_MONSTER_MAXTIER = 0x50  # monster shot with hpos bits 4+5

# projectile_picture_table (0x58B8A, 64 words), special_projectile_picture_table
# (0x58E3E, 80 words) and monster_projectile_picture_table (0x58EDE, 33 words).
_PROJECTILE_PICTURE_TBL = [
    0x1C9F, 0x1CA3, 0x1CA7, 0x1CAB, 0x1CAF, 0x1CB3, 0x1CB7, 0x1CBB,
    0x1CBF, 0x1CC3, 0x1CC7, 0x1CCB, 0x1CCF, 0x1CD3, 0x1C97, 0x1C9B,
    0x17FC, 0x17FC, 0x18FC, 0x18FC, 0x19FC, 0x19FC, 0x1AFC, 0x1AFC,
    0x1BC3, 0x1BC3, 0x1C68, 0x1C68, 0x1C6C, 0x1C6C, 0x1C70, 0x1C70,
    0x1CD7, 0x1CDB, 0x1CDF, 0x1CE3, 0x1CE7, 0x1CEB, 0x1CEF, 0x1CF3,
    0x1CF7, 0x1CFB, 0x1D00, 0x1D04, 0x1D08, 0x1D0C, 0x1D10, 0x1D14,
    0x1C74, 0x1C74, 0x1C78, 0x1C78, 0x1C7C, 0x1C7C, 0x1C80, 0x1C80,
    0x1C84, 0x1C84, 0x1C8B, 0x1C8B, 0x1C8F, 0x1C8F, 0x1C93, 0x1C93,
]
_SPECIAL_PROJECTILE_PICTURE_TBL = [
    0x27B0, 0x27B0, 0x27B0, 0x27A7, 0x27A7, 0x279E, 0x279E, 0x2795,
    0x2795, 0x278C, 0x278C, 0x07BC, 0x07BC, 0x07BC, 0x07B3, 0x07B3,
    0x07B3, 0x27EF, 0x27EF, 0x27EF, 0x27B0, 0x27B0, 0x27B0, 0x27A7,
    0x27A7, 0x279E, 0x279E, 0x2795, 0x2795, 0x278C, 0x278C, 0x27E6,
    0x27E6, 0x27E6, 0x27DD, 0x27DD, 0x27DD, 0x27D4, 0x27D4, 0x27D4,
    0x27B0, 0x27B0, 0x27B0, 0x27A7, 0x27A7, 0x279E, 0x279E, 0x2795,
    0x2795, 0x278C, 0x278C, 0x07D7, 0x07D7, 0x07D7, 0x07CE, 0x07CE,
    0x07CE, 0x07C5, 0x07C5, 0x07C5, 0x27B0, 0x27B0, 0x27B0, 0x27A7,
    0x27A7, 0x279E, 0x279E, 0x2795, 0x2795, 0x278C, 0x278C, 0x27CB,
    0x27CB, 0x27CB, 0x27C2, 0x27C2, 0x27C2, 0x27B9, 0x27B9, 0x27B9,
]
_MONSTER_PROJECTILE_PICTURE_TBL = [
    0x1C48, 0x1C48, 0x1C48, 0x1C48, 0x1C4C, 0x1C4C, 0x1C4C, 0x1C4C,
    0x1C50, 0x1C50, 0x1C50, 0x1C54, 0x1C54, 0x1C54, 0x1C58, 0x1C58,
    0x1C58, 0x1C58, 0x1C54, 0x1C54, 0x1C54, 0x1C50, 0x1C50, 0x1C50,
    0x1C4C, 0x1C4C, 0x1C4C, 0x1C4C, 0x1C48, 0x1C48, 0x1C48, 0x1C48,
    0x1C48,
]

# shot_collision_width (0x40B98) and its companion span table (0x40BB0),
# twelve words each, in native position units.  Player shots index by
# character, other channels by channel.
_SHOT_HITBOX_WIDTH = [
    0x0580, 0x0400, 0x0480, 0x0400, 0x0480, 0x0480,
    0x0480, 0x0480, 0x0480, 0x0480, 0x0480, 0x0480,
]
_SHOT_HITBOX_SPAN = [
    0x0800, 0x0600, 0x0700, 0x0600, 0x0600, 0x0600,
    0x0600, 0x0600, 0x0600, 0x0600, 0x0600, 0x0600,
]
# dragon_shot_collision_width (0x40BC8) plus its span half (0x40BD0).
_DRAGON_HITBOX_WIDTH = [0x0300, 0x0200, 0x0280, 0x0200]
_DRAGON_HITBOX_SPAN = [0x0500, 0x0300, 0x0400, 0x0300]
# A max-tier monster shot swaps in a fixed, much larger box (0x4094C).
_MAXTIER_HITBOX_WIDTH = 0x0880
_MAXTIER_HITBOX_SPAN = 0x0E80
_MAXTIER_H_BIAS = 0x0200          # 0x40990: nudge before masking

# shot_collision_probe_offsets -- ROM 0x40BD8, eight direction records of five
# (horizontal, vertical) signed word pairs.  The values are *word* indices
# into the MOB arrays: 2 per cell horizontally, 0x40 per maze row.  Each probe
# takes the previous probe's index, adds the horizontal delta, keeps only the
# column (``& 0x3E``), adds the vertical delta and re-adds the shot's own row.
_PROBE_OFFSETS = [
    [(-64, -64), (62, 0), (4, 0), (-68, -64), (4, -64)],
    [(-62, -64), (-2, -64), (66, 0), (62, 64), (-66, 0)],
    [(2, 0), (-66, -64), (128, 64), (-126, -64), (128, 64)],
    [(66, 64), (-64, 0), (62, 64), (-66, 0), (-62, -64)],
    [(64, 64), (-66, 0), (4, 0), (64, 64), (-4, 64)],
    [(62, 64), (-64, 0), (66, 64), (-128, -64), (66, 0)],
    [(-2, 0), (-62, -64), (128, 64), (-2, 64), (-128, -64)],
    [(-66, -64), (64, 0), (-62, -64), (66, 0), (62, 64)],
]

# ``wall_desc_destructible`` -- ROM 0x5BA5C points at the three stage records
# 0x5D3D0/0x5D3D8/0x5D3E0, each four playfield stamp words.  wall_crumble reads
# the stamped first word back to recover the stage and writes the next record.
# Byte-identical to gex's ``wall.SHRUB_DESTRUCT_STAMPS``, whose entry 0 is the
# untouched destructible wall.
_WALL_CRUMBLE_DESCS = (
    (0x07A7, 0x07A8, 0x07A9, 0x07AA),
    (0x07AB, 0x07AC, 0x07AD, 0x07AE),
    (0x07AF, 0x07B0, 0x07B1, 0x07B2),
)

# 0x40B58, 64 bytes: 0 = a max-tier shot collides with this object type,
# 0xFF = it passes straight through.
_MAXTIER_PASS_TBL = [
    0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00,
    0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0xFF, 0xFF, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF,
    0xFF, 0x00, 0xFF, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0xFF,
]

# Movable wall: 0x400 per player-shot hit into the object-state field,
# dissolve at 0x6400 (25 hits).  0x400 is exactly one step of that field.
_WALL_MOVE_HIT_UNIT = 0x400
_WALL_MOVE_DISSOLVE = 0x6400

# Generator families run in triplets from GEN_GHOST1.
_GEN_BASE = int(MazeObjIds.GEN_GHOST1)      # 28
_GEN_TOP = int(MazeObjIds.GEN_AUX_GRUNT3)   # 45

# Player MOB palette threshold: hpos & 0xF >= this identifies a player sprite.
_PLAYER_PALETTE_MIN = 0xC
# Monster "blinking / phased out" flag, hpos bit 4 (0x4BB92, 0x4BC70).
_MONST_PHASED = 0x10
# Shot strength/tier lives in hpos bits 4-5 of the *shot's* MOB word.
_SHOT_TIER_MASK = 0x30

# Player-hit parameters (LFLAG4 bits 0-1).  §26 / 0x4B058-0x4B172.
_SHOT_STUN_ADD = 0x28
_SHOT_STUN_MAX = 0x5A
_SHOT_HURT_COOLDOWN = 0x12
_SHOT_HP_HIT = 2
_SUPERSHOT_HP_HIT = 10
_LFLAG4_SHOTSTUN = 0x01
_LFLAG4_SHOTHURT = 0x02

# Score multipliers the ROM loads into D5 before the 0x4BD66 tail.
_SCORE_MULT_GHOST = 10
_SCORE_MULT_GRUNT = 5
_SCORE_MULT_GENERATOR = 10
_SCORE_MULT_DEATH_IT = 1
_SCORE_MULT_SUPERSORC = 100

# Sounds.
_SOUND_PLAYER_HIT = 0x1E
_SOUND_REFLECT = 0x2C
_SOUND_SECRET_WALL = 0x30
_SOUND_SLOWMO = 0x37
_SOUND_POTION_BREAK = 0x1D

# Slow-motion trigger pictures (identified by picture, not by type).  §26.
_PIC_SLOWMO_FOOD = 0x25ED
_PIC_SLOWMO_POTION = 0x20FC
_SLOWMO_FOOD_FRAMES = 0x258
_SLOWMO_POTION_FRAMES = 0x4B0

# Effect pool (0x0D-0x10) and its two pictures.
_EFFECT_SLOTS = range(0x0D, 0x11)
_TPORT_EFFECT_FIRST = 0x0924
_TPORT_EFFECT_LAST = 0x095A
_PLAYER_IMPACT_PICTURE = 0x0EFC
_MONSTER_IMPACT_PICTURE = 0x1C5C

# Off-screen disposal window (0x47716-0x477B8), in native position units.
_SCREEN_H_BIAS = 0x08            # ROM scroll_hpos_origin = (pf_hscroll - 8)<<7
_SCREEN_V_REF = 0x108            # ROM scroll_vpos_origin = (0x108 - pf_vscroll)<<7
_SCREEN_W = 0x7400
_SCREEN_W_TOL = 0x8400
_SCREEN_H = 0x7800
_SCREEN_H_TOL = 0x8800
_SCREEN_MARGIN = 0x0800
_SCREEN_NEG = 0xC000

# Doors only react to a shot inside this box (0x4B416 passes 0x2C0 twice).
_DOOR_LIMIT = 0x02C0

# Secret-wall prize roll (0x4B56A-0x4B5D2).
_PRIZE_HIDDENPOT_BASE = 0xA728
_GAME_MODE_SECRET = -3           # 0xFFFD, the secret-room game mode

# =============================================================================
# Small shared helpers
# =============================================================================

def _u16(value: int) -> int:
    return value & 0xFFFF


def _maze_position(value: int) -> int:
    """Unsigned position arithmetic: one 512 px maze is exactly one 16-bit word."""
    return value & 0xFFFF


def _s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def _shot_slot(shooter_id: int) -> int:
    """The MOB slot a shooter id owns.  The ROM writes ``shooter + 1``."""
    return shooter_id + 1


def _shot_tier(state: GameState, shooter_id: int) -> int:
    """hpos bits 4-5 of the shot MOB: its strength band."""
    return state.mobs.hpos[_shot_slot(shooter_id)] & _SHOT_TIER_MASK


def _is_maxtier(state: GameState, shooter_id: int) -> bool:
    return _shot_tier(state, shooter_id) == _SHOT_TIER_MASK


def _sound(state: GameState, sound_id: int) -> None:
    from .sound import sound_play
    sound_play(state, sound_id)


def _speech(state: GameState, speech_id: int) -> None:
    from .sound import sound_speech_play
    sound_speech_play(state, speech_id)


def _cell_of(px: int, py: int) -> int:
    """Packed maze cell of a world pixel position (0x47A5A-0x47A7C).

    The ROM rounds each axis to the nearest cell centre (``+8``) before
    truncating; ``py`` arrives already un-inverted into downward screen pixels
    by ``coords.vpos_y``, which is that routine's vertical half.
    """
    col = ((px + 8) >> 4) & 0x1F
    row = ((py + 8) >> 4) & 0x1F
    return (row << 5) | col


def shot_cell(state: GameState, slot: int) -> int:
    """The maze cell a projectile MOB's pixel position belongs to.

    ``monster_create_shot`` (0x49280-0x492A2) and this module's own re-key use
    the same +12/+8 px sprite biases, so a channel is depth-placed at creation
    exactly where the next frame would re-key it.
    """
    mobs = state.mobs
    return _cell_of(hpos_x(mobs.hpos[slot]), vpos_y(mobs.vpos[slot]))


def _shot_cell(state: GameState, slot: int) -> int:
    return shot_cell(state, slot)


def _direction_of(dx: int, dv: int) -> int:
    """Shot direction code from a per-frame pixel delta.

    ``dv`` is a native V delta -- positive walks up the screen -- matching the
    hardware axes ``state.shot_dy`` is stored in.  Matches ``thief.py``'s
    identical derivation: 0 is up, then clockwise.
    """
    if dx == 0:
        return 0 if dv > 0 else 4 if dv < 0 else 8
    if dv == 0:
        return 2 if dx > 0 else 6
    if dx > 0:
        return 1 if dv > 0 else 3
    return 7 if dv > 0 else 5


def _live_direction(state: GameState, shooter_id: int) -> int:
    """``shot_direction[shooter]`` (0x9049C4), recovered when unset.

    ``player_create_shot``/``monster_create_shot`` seed only ``shot_dx/dy``, so
    a channel that has never been through this module carries the sentinel 8.
    """
    direction = state.shot_direction[shooter_id]
    if 0 <= direction <= 7:
        return direction
    slot = _shot_slot(shooter_id)
    direction = _direction_of(state.shot_dx[slot], state.shot_dy[slot])
    if direction > 7:
        direction = 0
    state.shot_direction[shooter_id] = direction
    return direction


def player_add_score_with_mult(state: GameState, player_index: int, damage: int,
               multiplier: int) -> None:
    """``player_add_score_with_mult`` (0x5214C), inlined.

    Cross-subsystem rule: shots.py cannot import players.py.  Score is 32-bit;
    mask on write (PLAN §3 rule 6).  0x5217C then does ``ori.b #1`` into
    ``player_redraw`` -- WP-14's ``score_dirty`` latch -- so the info panel
    picks the new total up on this player's turn in the four-frame rotation.
    """
    player = state.players[player_index]
    player.score = _u32(player.score + damage * multiplier * player.bonusmult)
    state.score_dirty[player_index] = 1


def _hurt_latch(state: GameState, victim_index: int) -> None:
    """``ori.b #2, player_redraw[victim]`` -- WP-14's ``health_dirty`` latch.

    The ROM raises it at 0x4B102/0x4B152 (player-versus-player) and 0x4B282
    (monster shot); the stun-only path deliberately does not, because it
    changes no health.
    """
    state.health_dirty[victim_index] = 1


def _u32(value: int) -> int:
    return value & 0xFFFF_FFFF


def _trick_bump(state: GameState, player_index: int, trick_id: int) -> None:
    """0x4B694 / 0x4B852 / 0x4B90E -- the signed-byte secret-room progress bump.

    WP-15 owns ``secret_tricks_flags``; these sites only notice the event.  The
    ROM's shape is ``tst.b`` then ``blt`` to ``move.b #1``, otherwise
    ``addq.b #1``, so a byte that has already gone negative restarts at one
    instead of wrapping.  Both halves go through the WP-15 entry points, which
    carry the ``cmpi.b #<trick>,secret_trick_id`` guard themselves.
    """
    from .exits import secret_trick_progress, secret_trick_set
    if state.secret_tricks_flags[player_index] & 0x80:
        secret_trick_set(state, player_index, trick_id, 1)
    else:
        secret_trick_progress(state, player_index, trick_id)


def _trick_set(state: GameState, player_index: int, trick_id: int,
               value: int) -> None:
    """0x4B052 / 0x4B312 -- the ``move.b #n`` and ``clr.b`` progress sites."""
    from .exits import secret_trick_set
    secret_trick_set(state, player_index, trick_id, value)


# 0x4B67E / 0x4B68A: two secret-room tasks with no WP-15 name of their own ride
# the same "watch what you shoot" bump as TRICK_WATCHSHOOT2 (0x4B672).
_TASK_SHOOT_SECRET_A = 0x52
_TASK_SHOOT_SECRET_B = 0x5B
# 0x4B826: the supershot-treasure task, likewise unnamed.
_TASK_SHOOT_TREASURE = 0x5A


def _kill_bookkeeping(state: GameState) -> None:
    """0x4B754/0x4BB24: a destroyed object resets the escape and idle timers."""
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0


# dialog_first_encounter records (0x4C440).  resolve_shot_hit is the only shot
# function that raises them, at exactly seven ``jsr $4C440`` sites, and the
# record number is the bit number of the mask it pushes (``1 << record``).
# score.py owns the message and speech tables behind them.
_DIALOG_FOOD_SHOT = 1          # 0x4B930 "SOME FOOD DESTROYED BY SHOTS"
_DIALOG_POTION_SHOT = 6        # 0x4BA46 "SHOOTING A POTION HAS A LESSER EFFECT"
_DIALOG_POISON_SHOT = 7        # 0x4B8F0/0x4BA40 "SHOOTING POISON SLOWS MONSTERS"
_DIALOG_DEMON_SHOT = 10        # 0x4B2D8 ordinary monster shot (channels 4-7)
_DIALOG_LOBBER_SHOT = 11       # 0x4B2CE special channel (>= 8), no tier bits
_DIALOG_DRAGON_SHOT = 14       # 0x4B292 shot tier 2/3 -- "SHOOT DRAGON'S HEAD"
_DIALOG_STRONG_SHOT = 16       # 0x4B2BE shot tier 1
_DIALOG_PLAYER_SHOT = 18       # 0x4B178 shot by another player
_DIALOG_WALL_SHOT = 22         # 0x4B6F8 destructible wall


def _dialog(state: GameState, player_index: int, record: int,
            value: int = 0) -> int:
    """``dialog_first_encounter`` (0x4C440) -- WP-14 owns the dialog records.

    Returns 1 when the selected record carries speech, which is the value the
    ROM's food and potion paths test before speaking for themselves.  A record
    whose message slot is empty returns 0, exactly as the ROM's NULL-record
    path does.

    Ghost/grunt/sorcerer (records 8, 9 and 12) are deliberately *not* raised
    here: those three never fire projectiles, so their encounter records come
    from ``monster_playerhit`` (0x495A6, the computed-mask calls at 0x4986A
    and 0x49A2C) -- WP-8's contact path, not this one.
    """
    from .score import dialog_first_encounter
    return dialog_first_encounter(state, player_index, 1 << record, value)


# =============================================================================
# Effect pool (0x47C0E / 0x47DAE)
# =============================================================================

def _claim_effect_slot(state: GameState, fallback_channel: int,
                       preserve_tport: bool) -> int | None:
    """Claim one of the four shared effect MOBs used by ROM 0x47C0E/0x47DAE."""
    for slot in _EFFECT_SLOTS:
        if state.mobs.picture[slot] == 0:
            return slot

    slot = 0x0D + (fallback_channel & 3)
    picture = state.mobs.picture[slot]
    if preserve_tport and _TPORT_EFFECT_FIRST <= picture <= _TPORT_EFFECT_LAST:
        return None
    state.mobs.unlink_and_clear(slot)
    return slot


def _place_effect(state: GameState, effect_slot: int, source_slot: int,
                  picture: int, vpos_add: int, counter: int) -> None:
    """Install a temporary effect MOB at a tile-aligned source position."""
    state.mobs.picture[effect_slot] = picture
    state.mobs.hpos[effect_slot] = (
        position_field(state.mobs.hpos[source_slot]) + 1
    ) & 0xFFFF
    state.mobs.vpos[effect_slot] = (
        position_field(state.mobs.vpos[source_slot]) + vpos_add
    ) & 0xFFFF
    state.mobs.insert(effect_slot, depth_key=source_slot)
    state.mob_effect_anim_counter[effect_slot - 0x0D] = counter & 0xFF


def shot_impact_spawn(state: GameState, target: int, shooter: int) -> None:
    """0x47DAE -- spawn a sparkle explosion at the target.

    The first free slot in 0x0D-0x10 wins. With a full pool, the shooter selects
    a fallback channel, but an active transporter dissolve in that channel is
    preserved rather than overwritten.
    """
    effect_slot = _claim_effect_slot(
        state, shooter, preserve_tport=True,
    )
    if effect_slot is None:
        return
    picture = (
        _PLAYER_IMPACT_PICTURE if shooter < 8 else _MONSTER_IMPACT_PICTURE
    )
    _place_effect(state, effect_slot, target, picture, 9, 0)


def tport_cycle_start(state: GameState, slot: int,
                      animation_channel: int = 0) -> None:
    """0x47C0E -- start a transporter-cycle dissolve effect on ``slot``.

    The ROM always claims a channel, replacing ``animation_channel`` when all
    four are occupied, then seeds the counter with 0xFF so loop 3 of
    ``main_score_update`` begins at frame zero on its next tick.
    """
    effect_slot = _claim_effect_slot(
        state, animation_channel, preserve_tport=False,
    )
    assert effect_slot is not None
    _place_effect(
        state, effect_slot, slot, _TPORT_EFFECT_FIRST, 0x12, 0xFF,
    )


def death_damage_accumulate(state: GameState, player_index: int,
                            death_slot: int, damage: int) -> None:
    """0x49A3C -- add damage to per-player Death-damage counter; dismiss when > 200.

    §3.6 / §26: supershot adds 25; monster/player Death *contact* adds 4 (or 3
    with the armor power, called from ``monster_playerhit``).  Ordinary player
    shots do NOT call this -- they only increment death_hits.  The counter
    belongs to the player and persists across multiple Death MOBs within a
    level; player_start_inner resets it on join/transition.
    """
    player = state.players[player_index]
    player.death_damage_counter += damage
    if player.death_damage_counter > 200:
        # Ninth supershot (200 + 25 = 225 > 200): dismiss Death.
        player.death_damage_counter = 0
        tport_cycle_start(state, death_slot, player_index)
        state.mobs.unlink_and_clear(death_slot)


# =============================================================================
# Damage
# =============================================================================

def _shot_damage(state: GameState, shooter_id: int) -> int:
    """0x4AFA6-0x4B00E -- the damage this shot carries.

    The ROM runs this for *every* shot, monster channels included: those index
    the class tables with the raw shooter id, which is why the middle band of
    ``shot_damage_base_tbl`` exists.  ``getrandom(2)`` is drawn here, so the
    order matters even on paths that ignore the result.
    """
    if shooter_id < 4:
        shot_class = state.players[shooter_id].character & 0xFFFF
    else:
        shot_class = shooter_id
    if shot_class < 4 and (state.players[shooter_id].powers & _POWER_SHOTPOWER):
        shot_class += 8
    shot_class = min(shot_class, len(_SHOT_DAMAGE_BASE_TBL) - 1)

    damage = _SHOT_DAMAGE_BASE_TBL[shot_class]
    if _SHOT_DAMAGE_RAND_TBL[shot_class]:
        damage += state.getrandom(2)
    if shooter_id < 4 and state.players[shooter_id].supershot:
        damage = _SUPERSHOT_DAMAGE
    return damage


def _monstshot_damage_index(state: GameState, victim, shooter_id: int) -> int:  # noqa: ANN001
    """Exact ``monstshot_damage_tbl`` index (0x4B1AC-0x4B238).

    ``character + 4*armour + tier``, where the tier addend comes from the
    *shot's* own hpos bits 4-5 and falls back to 8 for a special/dragon
    channel when those bits are clear.
    """
    index = (victim.character & 0x03)
    if victim.powers & _POWER_ARMOR:
        index += 4
    tier = _shot_tier(state, shooter_id)
    if tier == 0x30:
        index += 0x20
    elif tier == 0x20:
        index += 0x18
    elif tier == 0x10:
        index += 0x10
    elif shooter_id >= 8:
        index += 8
    return index


def _supershot(state: GameState, shooter_id: int) -> bool:
    return shooter_id < 4 and bool(state.players[shooter_id].supershot)


# =============================================================================
# resolve_shot_hit tails
# =============================================================================

def _channel_clear(state: GameState, shooter_id: int) -> None:
    """``mob_depth_remove(shooter)`` + ``mob_picture[shooter+1] = 0``.

    The ROM leaves H/V alone here; only the off-screen path clears them.
    """
    slot = _shot_slot(shooter_id)
    state.mobs.depth_remove(shooter_id)
    state.mobs.picture[slot] = 0
    state.shot_dx[slot] = 0
    state.shot_dy[slot] = 0
    state.shot_direction[shooter_id] = 8
    state.shot_owner_mob[shooter_id] = -1


def _consume(state: GameState, shooter_id: int) -> int:
    """0x4B6CE -- unconditional "shot used up" tail."""
    _channel_clear(state, shooter_id)
    return CONSUMED


def _finish(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4BDB4 -- the shared tail: a max-tier shot bores straight through.

    Otherwise it sparkles on a still-present target and is consumed.
    """
    if _is_maxtier(state, shooter_id):
        return SURVIVES
    if state.mobs.picture[slot] != 0:
        shot_impact_spawn(state, slot, shooter_id)
    return _consume(state, shooter_id)


# =============================================================================
# resolve_shot_hit -- object handlers
# =============================================================================

def _handle_player_victim(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B02C-0x4B316 -- the target MOB is a player."""
    mobs = state.mobs
    victim_index = mobs.state(slot) & 0x3F
    if victim_index >= len(state.players):
        return _finish(state, slot, shooter_id)     # guard: corrupted slot
    victim = state.players[victim_index]

    if shooter_id >= 4:
        return _monster_shot_on_player(state, slot, shooter_id, victim_index, victim)

    # ---- player versus player (0x4B046) ----
    from .exits import TRICK_NOHURTFRIENDS
    _trick_set(state, shooter_id, TRICK_NOHURTFRIENDS, 1)

    hurt = False
    if not victim.acid_timer and (state.level_flags_4 & _LFLAG4_SHOTSTUN):
        victim.stundelay = min(victim.stundelay + _SHOT_STUN_ADD, _SHOT_STUN_MAX)
        state.player_fighting_dir[victim_index] = 0
        victim.hurt_cooldown = _SHOT_HURT_COOLDOWN
        hurt = True
    elif not victim.acid_timer and (state.level_flags_4 & _LFLAG4_SHOTHURT):
        victim.health = max(0, victim.health - _SHOT_HP_HIT)
        _hurt_latch(state, victim_index)
        victim.hurt_cooldown = _SHOT_HURT_COOLDOWN
        hurt = True
    elif state.players[shooter_id].supershot and not victim.acid_timer:
        victim.health = max(0, victim.health - _SUPERSHOT_HP_HIT)
        _hurt_latch(state, victim_index)
        victim.hurt_cooldown = _SHOT_HURT_COOLDOWN
        hurt = True
    elif shooter_id != victim_index:
        _dialog(state, shooter_id, _DIALOG_PLAYER_SHOT)

    if hurt:
        dragon_player_proximity(state, slot)
        _sound(state, _SOUND_PLAYER_HIT)
    return _finish(state, slot, shooter_id)


def _monster_shot_on_player(state: GameState, slot: int, shooter_id: int,
                            victim_index: int, victim) -> int:  # noqa: ANN001
    """0x4B1AC -- a monster/dragon shot landing on a player."""
    index = _monstshot_damage_index(state, victim, shooter_id)

    if victim.acid_timer:
        # 0x4B306: an acid-slowed player is immune, and loses trick 8.
        from .exits import TRICK_NOUSEINVUL
        _trick_set(state, victim_index, TRICK_NOUSEINVUL, 0)
        return _finish(state, slot, shooter_id)

    damage = _MONSTSHOT_DAMAGE_TBL[index]
    victim.health = max(0, victim.health - damage)
    _hurt_latch(state, victim_index)

    if index >= 0x18:
        _dialog(state, victim_index, _DIALOG_DRAGON_SHOT, damage)
        # 0x4B2A2: only the dragon's own fire counts against "don't get hit".
        from .exits import TRICK_NOGETHIT, secret_trick_progress
        secret_trick_progress(state, victim_index, TRICK_NOGETHIT)
    elif index >= 0x10:
        _dialog(state, victim_index, _DIALOG_STRONG_SHOT, damage)
    elif index >= 8:
        _dialog(state, victim_index, _DIALOG_LOBBER_SHOT, damage)
    else:
        _dialog(state, victim_index, _DIALOG_DEMON_SHOT, damage)

    victim.hurt_cooldown = _SHOT_HURT_COOLDOWN
    _sound(state, _SOUND_PLAYER_HIT)
    return _finish(state, slot, shooter_id)


def _handle_monster(state: GameState, slot: int, shooter_id: int, damage: int,
                    obj_type: int, multiplier: int) -> int:
    """0x4BB36 -- subtract the damage from the target's own hpos tier nibble."""
    mobs = state.mobs
    mobs.hpos[slot] = _u16(mobs.hpos[slot] - damage)
    tier = mobs.hpos[slot] & 0x0F
    base = _MAZEOBJ_HSIZE_TIER_TBL[obj_type & 0x3F]
    # The ROM tests ``(tier - base + 2) < 3`` unsigned, i.e. the live window.
    if 0 <= (tier - base + 2) <= 2:
        return _score_tail(state, slot, shooter_id, damage, obj_type, multiplier)
    return _destroy_target(state, slot, shooter_id, damage, obj_type, multiplier)


def _destroy_target(state: GameState, slot: int, shooter_id: int, damage: int,
                    obj_type: int, multiplier: int) -> int:
    """0x4BCB8 -- sparkle, then remove when this shooter is allowed to."""
    shot_impact_spawn(state, slot, shooter_id)
    remove = (
        shooter_id < 4
        or 0x1C <= obj_type <= 0x1E
        or 0x12 <= obj_type <= 0x1B
    )
    if remove:
        state.mobs.unlink_and_clear(slot)
    return _score_tail(state, slot, shooter_id, damage, obj_type, multiplier)


def _score_tail(state: GameState, slot: int, shooter_id: int, damage: int,
                obj_type: int, multiplier: int) -> int:
    """0x4BD66 -- award the score, then pierce unless the target is Death/IT."""
    if shooter_id >= 4:
        return _finish(state, slot, shooter_id)

    dragon_player_proximity(state, slot)
    player_add_score_with_mult(state, shooter_id, damage, multiplier)
    if state.idle_timer > 0:
        state.idle_timer = 0

    if state.players[shooter_id].supershot:
        if obj_type not in (int(MazeObjIds.MONST_IT), int(MazeObjIds.MONST_DEATH)):
            return SURVIVES
    return _finish(state, slot, shooter_id)


def _handle_sorcerer(state: GameState, slot: int, shooter_id: int,
                     damage: int, obj_type: int) -> int:
    """0x4BB70 -- a Sorcerer phased out (hpos bit 4) is untouchable."""
    if _supershot(state, shooter_id):
        return _destroy_target(
            state, slot, shooter_id, damage, obj_type, _SCORE_MULT_GRUNT,
        )
    if state.mobs.hpos[slot] & _MONST_PHASED:
        return SURVIVES
    return _handle_monster(
        state, slot, shooter_id, damage, obj_type, _SCORE_MULT_GRUNT,
    )


def _handle_supersorc(state: GameState, slot: int, shooter_id: int,
                      damage: int, obj_type: int) -> int:
    """0x4BBA2 -- the Super Sorcerer dies to one ordinary player shot.

    A supershot takes the shared destroy path instead, where D5 is still the
    zeroed victim register -- so it scores nothing.  That is the ROM.
    """
    if _supershot(state, shooter_id):
        return _destroy_target(state, slot, shooter_id, damage, obj_type, 0)
    if state.mobs.hpos[slot] & _MONST_PHASED:
        return SURVIVES
    if shooter_id >= 4:
        return _finish(state, slot, shooter_id)

    state.escape_timer = 0
    playfield_showscore(state, slot, 0)
    shot_impact_spawn(state, slot, shooter_id)
    state.mobs.unlink_and_clear(slot)
    return _score_tail(
        state, slot, shooter_id, damage, obj_type, _SCORE_MULT_SUPERSORC,
    )


def _handle_death(state: GameState, slot: int, shooter_id: int,
                  damage: int, obj_type: int) -> int:
    """0x4BC12 -- Death: count the hit, and only a supershot really hurts."""
    if shooter_id < 4:
        state.death_hits = _u16(state.death_hits + 1)
        if state.players[shooter_id].supershot:
            death_damage_accumulate(state, shooter_id, slot, 25)
    return _score_tail(
        state, slot, shooter_id, damage, obj_type, _SCORE_MULT_DEATH_IT,
    )


def _handle_it(state: GameState, slot: int, shooter_id: int,
               damage: int, obj_type: int) -> int:
    """0x4BC48 -- shooting IT folds its state field down and phases it out."""
    mobs = state.mobs
    previous = mobs.state_link[slot]
    mobs.state_link[slot] = previous & 0x1FFF
    if not (mobs.hpos[slot] & _MONST_PHASED):
        mobs.state_link[slot] = _u16(
            (mobs.state_link[slot] & 0x3FF) + ((previous >> 3) & 0x1C00)
        )
        mobs.hpos[slot] = _u16(mobs.hpos[slot] | _MONST_PHASED)
    return _score_tail(
        state, slot, shooter_id, damage, obj_type, _SCORE_MULT_DEATH_IT,
    )


def _handle_generator(state: GameState, slot: int, shooter_id: int,
                      damage: int, obj_type: int) -> int:
    """0x4BCB0/0x4BD04/0x4BD14 -- tier 1 always dies, 2 and 3 need the damage."""
    state.escape_timer = 0
    tier = ((obj_type - _GEN_BASE) % 3) + 1
    if tier == 1 or damage >= tier:
        return _destroy_target(
            state, slot, shooter_id, damage, obj_type, _SCORE_MULT_GENERATOR,
        )

    # 0x4BD22: step the type field down and refresh the picture.
    mobs = state.mobs
    mobs.link[slot] = _u16(mobs.link[slot] - (damage << 10))
    mobs.picture[slot] = _MAZEOBJ_BASE_PICTURE_TBL[(mobs.link[slot] >> 10) & 0x3F]
    return _score_tail(
        state, slot, shooter_id, damage, obj_type, _SCORE_MULT_GENERATOR,
    )


def _handle_wall(state: GameState, raw_target: int, slot: int,
                 shooter_id: int, obj_type: int) -> int:
    """0x4B448 -- movable walls first, then the shared wall/tile path."""
    mobs = state.mobs
    if shooter_id < 4 and obj_type == int(MazeObjIds.WALL_MOVABLE):
        # The ROM accumulates 0x400 -- one step of the object-state field --
        # directly in mob_state_link and dissolves at 0x6400 (25 hits).
        mobs.state_link[slot] = _u16(mobs.state_link[slot] + _WALL_MOVE_HIT_UNIT)
        count = mobs.state_link[slot]
        state.movable_wall_hits[slot] = count & ~0x3FF
        if count >= _WALL_MOVE_DISSOLVE:
            from ..maze import clear_cell_descriptor

            state.movable_wall_hits.pop(slot, None)
            tport_cycle_start(state, slot, shooter_id)
            mobs.unlink_and_clear(slot)
            clear_cell_descriptor(state, slot)
            return _consume(state, shooter_id)
    return _handle_generic_wall(state, raw_target, shooter_id)


def _handle_generic_wall(state: GameState, raw_target: int,
                         shooter_id: int) -> int:
    """0x4B49A -- reflect if the shooter can, else sparkle and stop.

    Also the entry point for a bare playfield tile code (0x400-0x7FF), which
    has no MOB of its own.
    """
    if shooter_id < 4 and (state.players[shooter_id].powers & _POWER_REFLECT):
        state.shot_direction[shooter_id] = shot_reflect_calc(
            state, raw_target, shooter_id,
        )
        if state.reflect_count[shooter_id] != 0:
            return SURVIVES

    shot_impact_spawn(state, raw_target & 0x3FF, shooter_id)
    if _is_maxtier(state, shooter_id):
        return SURVIVES     # 0x4B51E: max-tier shots bore through walls
    return _consume(state, shooter_id)


def _handle_secret_wall(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B528 -- reveal the wall, roll a prize, credit the trick."""
    mobs = state.mobs
    _sound(state, _SOUND_SECRET_WALL)
    # 0x4B53C then 0x4B55A: stamp floor over the tile, spawn the burst at the
    # position that stamp deliberately leaves behind, then free the MOB.
    pf_replace(state, slot, int(MazeObjIds.TILE_FLOOR))
    shot_impact_spawn(state, slot, shooter_id)
    mobs.unlink_and_clear(slot)

    roll = state.getrandom(0x10)
    spawn = True
    if state.game_mode != _GAME_MODE_SECRET:
        if roll >= state.level_players_active * 2 + 2:
            spawn = False

    if spawn:
        if state.game_mode == _GAME_MODE_SECRET:
            prize = int(MazeObjIds.POT_INVULN)
        elif roll < 2:
            prize = int(MazeObjIds.MONST_DEATH)
        elif roll < 4:
            prize = int(MazeObjIds.TREASURE_BAG)
        elif roll in (4, 8):
            prize = int(MazeObjIds.POT_INVULN)
        elif roll in (5, 7):
            prize = int(MazeObjIds.FOOD_INVULN)
        else:
            prize = int(MazeObjIds.HIDDENPOT)

        picture = _MAZEOBJ_BASE_PICTURE_TBL[prize]
        if prize == int(MazeObjIds.HIDDENPOT):
            picture = _u16(_PRIZE_HIDDENPOT_BASE + (state.getrandom(6) << 2))
        _spawn_maze_object(state, slot, prize, picture)

    if shooter_id >= 4:
        return _consume(state, shooter_id)

    # 0x4B672/0x4B67E/0x4B68A: three secret-room tasks watch what you shoot.
    from .exits import TRICK_WATCHSHOOT2
    for trick in (TRICK_WATCHSHOOT2, _TASK_SHOOT_SECRET_A, _TASK_SHOOT_SECRET_B):
        _trick_bump(state, shooter_id, trick)
    state.secret_need_hint = 1
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0
    dragon_player_proximity(state, slot)
    return _consume(state, shooter_id)


def _handle_destructible_wall(state: GameState, raw_target: int, slot: int,
                              shooter_id: int, damage: int) -> int:
    """0x4B6F2 -- crumble it, and let a supershot carry on through."""
    if shooter_id < 4:
        _dialog(state, shooter_id, _DIALOG_WALL_SHOT)

    if wall_crumble(state, slot, damage):
        shot_impact_spawn(state, slot, shooter_id)

    if shooter_id >= 4:
        return _handle_wall_tail(state, shooter_id)

    if state.players[shooter_id].supershot:
        dragon_player_proximity(state, slot)
        _kill_bookkeeping(state)
        return SURVIVES

    _kill_bookkeeping(state)
    dragon_player_proximity(state, slot)
    return _handle_wall_tail(state, shooter_id)


def _handle_wall_tail(state: GameState, shooter_id: int) -> int:
    """0x4B502 -- the wall paths' shared close: max-tier keeps going."""
    if _is_maxtier(state, shooter_id):
        return SURVIVES
    return _consume(state, shooter_id)


def _handle_door(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B416 -- doors only notice a shot inside the 0x2C0 box."""
    if shot_onscreen_check(state, slot, _DOOR_LIMIT, _DOOR_LIMIT) == 0:
        return SURVIVES
    shot_impact_spawn(state, slot, shooter_id)
    return _consume(state, shooter_id)


def _handle_playerstart(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B784 -- shooting the thief either slows it or kills it.

    The thief MOB carries ``PLAYERSTART`` as its object type, so this is the
    thief's own dispatch case.  A shot that finds the mugger already up to
    speed only drags it back (0x4B7F0); everything else is a kill.
    """
    if shooter_id >= 4:
        return _finish(state, slot, shooter_id)

    if (state.thief_speed != 0x200 and (state.thief_mode & 0x80)
            and not state.players[shooter_id].supershot):
        state.thief_speed = _u16(state.thief_speed + 0x80)
    else:
        # 0x4B7E8: WP-10 owns the whole removal transaction -- the 500-point
        # bounty, the dissolve, the carried-item handover and the dropped
        # pickup.
        from .thief import thief_remove_and_drop_loot
        thief_remove_and_drop_loot(state, shooter_id, slot)

    dragon_player_proximity(state, slot)
    return _consume(state, shooter_id)


def _handle_treasure(state: GameState, slot: int, shooter_id: int,
                     obj_type: int) -> int:
    """0x4B80E -- treasure and the invulnerable food/potion: supershot only."""
    if shooter_id >= 4 or not state.players[shooter_id].supershot:
        return _finish(state, slot, shooter_id)

    from .exits import TRICK_WATCHSHOOT1, secret_trick_progress
    if obj_type == int(MazeObjIds.TREASURE):
        # 0x4B826: this task counts plainly, with no negative-byte restart.
        secret_trick_progress(state, shooter_id, _TASK_SHOOT_TREASURE)
    elif obj_type == int(MazeObjIds.FOOD_INVULN):
        _trick_bump(state, shooter_id, TRICK_WATCHSHOOT1)    # 0x4B840

    shot_impact_spawn(state, slot, shooter_id)
    state.mobs.unlink_and_clear(slot)
    dragon_player_proximity(state, slot)
    _kill_bookkeeping(state)
    return SURVIVES     # 0x4B746: a supershot always carries on


def _handle_food(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B894 -- destructible food, with the slow-motion picture special case."""
    mobs = state.mobs
    picture = 0
    if shooter_id < 4:
        picture = mobs.picture[slot]
        if picture == _PIC_SLOWMO_FOOD:
            state.monster_slowmo_timer = _SLOWMO_FOOD_FRAMES
            _sound(state, _SOUND_SLOWMO)

    shot_impact_spawn(state, slot, shooter_id)
    mobs.unlink_and_clear(slot)
    if shooter_id >= 4:
        return _finish(state, slot, shooter_id)

    if picture == _PIC_SLOWMO_FOOD:
        _dialog(state, shooter_id, _DIALOG_POISON_SHOT)
        spoke = 1
    else:
        # 0x4B904: shooting ordinary food is what TRICK_WATCHSHOOT1 counts.
        from .exits import TRICK_WATCHSHOOT1
        _trick_bump(state, shooter_id, TRICK_WATCHSHOOT1)
        spoke = _dialog(state, shooter_id, _DIALOG_FOOD_SHOT)

    if state.players[shooter_id].supershot:
        dragon_player_proximity(state, slot)
        _kill_bookkeeping(state)
        return SURVIVES

    dragon_player_proximity(state, slot)
    _kill_bookkeeping(state)

    if not spoke and state.getrandom(3) == 0:
        if state.getrandom(5) == 0:
            _speech(state, 0x61)
        else:
            character = state.players[shooter_id].character & 0x03
            _speech(state, _SHOT_FOOD_SPEECH[shooter_id * 4 + character])
            _speech(state, 0x9A)
    return _finish(state, slot, shooter_id)


def _handle_potion(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B9CE -- a shot potion detonates; some pictures start slow motion."""
    mobs = state.mobs
    picture = 0
    if shooter_id < 4:
        picture = mobs.picture[slot]
        if picture == _PIC_SLOWMO_POTION:
            state.monster_slowmo_timer = _SLOWMO_POTION_FRAMES
            _sound(state, _SOUND_SLOWMO)

    shot_impact_spawn(state, slot, shooter_id)
    mobs.unlink_and_clear(slot)
    if state.mazenum_current < 0x73:
        _sound(state, _SOUND_POTION_BREAK)
    if shooter_id >= 4:
        return _finish(state, slot, shooter_id)

    spoke = _dialog(
        state, shooter_id,
        _DIALOG_POISON_SHOT if picture == _PIC_SLOWMO_POTION
        else _DIALOG_POTION_SHOT,
    )

    if picture != _PIC_SLOWMO_POTION and state.mazenum_current < 0x73:
        # 0x4BA6A: the shot potion blasts as if the shooter had drunk it.
        # The ROM only stamps ``potion_player`` here and lets the blast scan
        # inside monsters_everything pick it up; the port's WP-12 entry does
        # the scan directly, so drive it and then restore the ROM's own
        # ``shooter + 4`` encoding of that word.
        _potion_blast(state, shooter_id)
        state.potion_player = _u16(shooter_id + 4)
        if not spoke and state.getrandom(4) == 0 and \
                state.players[shooter_id].supershot:
            if state.getrandom(4) == 0:
                _speech(state, 0x8B)
            else:
                character = state.players[shooter_id].character & 0x03
                _speech(state, _SHOT_FOOD_SPEECH[shooter_id * 4 + character])
                _speech(state, 0x9C)

    if state.players[shooter_id].supershot:
        dragon_player_proximity(state, slot)
        _kill_bookkeeping(state)
        return SURVIVES

    dragon_player_proximity(state, slot)
    _kill_bookkeeping(state)
    return _finish(state, slot, shooter_id)


def _handle_dragon(state: GameState, raw_target: int, slot: int,
                   shooter_id: int) -> int:
    """0x4B3B4 -- player shots go to the dragon handler, monster shots die."""
    if shooter_id >= 4:
        shot_impact_spawn(state, slot, shooter_id)
        return _consume(state, shooter_id)

    dragon_player_proximity(state, slot)
    from .dragon import dragon_shot_hit
    dragon_shot_hit(state, raw_target, shooter_id)
    return _consume(state, shooter_id)


# =============================================================================
# resolve_shot_hit -- the computed dispatch at 0x4B336
# =============================================================================

# The 62-entry displacement table at 0x4B338 collapses into these groups.
_TYPES_NO_EFFECT = frozenset((
    1, 10, 11, 12, 16, 17, 25, 53, 54, 55, 56, 57, 58, 59, 62,
))
_TYPES_WALL = frozenset((2, 3, 7, 8, 9))
_TYPES_GRUNT_CLASS = frozenset((19, 20, 21, 23))
_TYPES_TREASURE = frozenset((46, 47, 48, 50, 52))

# shot_food_speech_tbl (0x596F6): sixteen longwords indexed by
# ``character + shooter*4``, spoken as "<name> ... shot the food" with the
# 0x9A ("shot the food") or 0x9C ("shot the potion") suffix.
_SHOT_FOOD_SPEECH = [
    0xBD, 0xBE, 0xBF, 0xC0,
    0xC1, 0xC2, 0xC3, 0xC4,
    0xC5, 0xC6, 0xC7, 0xC8,
    0xC9, 0xCA, 0xCB, 0xCC,
]


def resolve_shot_hit(state: GameState, target: int, shooter_id: int) -> int:
    """0x4AF50 -- shot to target hit resolution.

    Returns 0 when the shot survives (pierce/reflect/no effect); -1 when the
    shot is consumed (``mob_unlink(shooter)`` and its picture cleared).

    ``target`` is a MOB slot (0-0x3FF), or 0x400-0x7FF for a generic playfield
    tile with no MOB of its own.  ``shooter_id`` is 0-3 for player shots and
    >= 4 for the monster/dragon channels.
    """
    mobs = state.mobs
    raw_target = _u16(target)
    slot = raw_target & 0x3FF
    obj_type = mobs.obj_type(slot)

    if 0x400 <= raw_target < 0x800:
        # 0x4AFA0: a bare playfield tile enters the generic wall path, so a
        # reflecting shot still bounces off it.
        return _handle_generic_wall(state, raw_target, shooter_id)

    # The ROM computes the damage (and draws getrandom) before dispatching.
    damage = _shot_damage(state, shooter_id)

    if (mobs.hpos[slot] & 0x0F) >= _PLAYER_PALETTE_MIN:
        return _handle_player_victim(state, slot, shooter_id)

    if not 1 <= obj_type <= 0x3E:
        return _finish(state, slot, shooter_id)     # bounds check at 0x4B31E

    if obj_type in _TYPES_NO_EFFECT:
        return SURVIVES                              # 0x4B890
    if obj_type in _TYPES_WALL:
        return _handle_wall(state, raw_target, slot, shooter_id, obj_type)
    if obj_type == int(MazeObjIds.WALL_SECRET):
        return _handle_secret_wall(state, slot, shooter_id)
    if obj_type == int(MazeObjIds.WALL_DESTRUCTABLE):
        return _handle_destructible_wall(state, raw_target, slot, shooter_id, damage)
    if obj_type == int(MazeObjIds.WALL_RANDOM):
        return _finish(state, slot, shooter_id)      # 0x4BDB4 directly
    if obj_type in (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT)):
        return _handle_door(state, slot, shooter_id)
    if obj_type == int(MazeObjIds.PLAYERSTART):
        return _handle_playerstart(state, slot, shooter_id)
    if obj_type == int(MazeObjIds.MONST_GHOST):
        return _handle_monster(
            state, slot, shooter_id, damage, obj_type, _SCORE_MULT_GHOST,
        )
    if obj_type in _TYPES_GRUNT_CLASS:
        return _handle_monster(
            state, slot, shooter_id, damage, obj_type, _SCORE_MULT_GRUNT,
        )
    if obj_type == int(MazeObjIds.MONST_SORC):
        return _handle_sorcerer(state, slot, shooter_id, damage, obj_type)
    if obj_type == int(MazeObjIds.MONST_DEATH):
        return _handle_death(state, slot, shooter_id, damage, obj_type)
    if obj_type == int(MazeObjIds.MONST_SUPERSORC):
        return _handle_supersorc(state, slot, shooter_id, damage, obj_type)
    if obj_type == int(MazeObjIds.MONST_IT):
        return _handle_it(state, slot, shooter_id, damage, obj_type)
    if _GEN_BASE <= obj_type <= _GEN_TOP:
        return _handle_generator(state, slot, shooter_id, damage, obj_type)
    if obj_type in _TYPES_TREASURE:
        return _handle_treasure(state, slot, shooter_id, obj_type)
    if obj_type == int(MazeObjIds.FOOD_DESTRUCTABLE):
        return _handle_food(state, slot, shooter_id)
    if obj_type in (int(MazeObjIds.POT_DESTRUCTABLE), int(MazeObjIds.HIDDENPOT)):
        return _handle_potion(state, slot, shooter_id)
    if obj_type == int(MazeObjIds.MONST_DRAGON):
        return _handle_dragon(state, raw_target, slot, shooter_id)

    return _finish(state, slot, shooter_id)


# =============================================================================
# Shared routines the ROM calls from resolve_shot_hit
# =============================================================================

_DRAGON_WAKE_FRAMES = 0x31       # 0x54ABC, the wake animation the ROM starts
_DRAGON_BOX_WIDTH = 10           # inclusive offsets -4..+5
_DRAGON_BOX_HEIGHT = 10          # inclusive offsets -5..+4


def dragon_player_proximity(
    state: GameState, cell: int, previous_cell: int = 0,
) -> None:
    """``dragon_player_proximity`` (0x549EA) -- react to entry into its box.

    The current cell must be inside the wrapped 10x10 rectangle around the
    primary segment, while a nonzero previous cell must be outside it. Sleeping
    dragons start/reverse their wake transition; stunned dragons clear stun.
    """
    head = state.dragon_seg_mob_ids[0]
    if not head:
        return

    start_col = ((head & 0x1F) - 4) & 0x1F
    start_row = (((head >> 5) & 0x1F) - 5) & 0x1F

    def inside(value: int) -> bool:
        col = value & 0x1F
        row = (value >> 5) & 0x1F
        return (
            ((col - start_col) & 0x1F) < _DRAGON_BOX_WIDTH
            and ((row - start_row) & 0x1F) < _DRAGON_BOX_HEIGHT
        )

    if not inside(cell) or (previous_cell and inside(previous_cell)):
        return

    from .dragon import _ST_STUNNED, _ST_WAKING

    if state.dragon_state & _ST_WAKING:
        if state.dragon_anim_ctr > 0:
            return
        if state.dragon_anim_ctr == 0:
            state.dragon_anim_ctr = _DRAGON_WAKE_FRAMES
        else:
            state.dragon_anim_ctr = -state.dragon_anim_ctr
        _sound(state, 0xD5)
    elif state.dragon_state & _ST_STUNNED:
        state.dragon_state &= ~_ST_STUNNED
        _sound(state, 0xD5)


# 0x579F2, the second word of each ``score_popup_tbl`` record: the picture the
# floating score sprite shows.  Entry 0 is the plain "points" burst the shot
# code raises; 1-9 and 10-14 are the score-value and bonus popups.
_SCORE_POPUP_PICTURE_TABLE = (
    0x1C88, 0x1DB4, 0x1DB7, 0x1DBA, 0x1DBD, 0x1DC0, 0x1DC3, 0x1DC6,
    0x1DC9, 0x1DCC, 0x25F6, 0x25F8, 0x25FA, 0x25FC, 0x25FE,
)
_SCORE_POPUP_SLOT = 0x11         # 0x494DC, the first popup MOB slot
_SCORE_POPUP_FRAMES = 0x3C       # 0x494D2


def playfield_showscore(state: GameState, slot: int, popup: int) -> None:
    """``playfield_showscore`` (0x49498) -- float a score sprite over ``slot``.

    Takes the first of the four popup channels whose ``score_display_timer``
    has run out; ``score.main_score_update`` ages the timer and clears the MOB
    again.  The sprite is snapped to the source's cell, lifted one row, then
    nudged by the palette/size bias the ROM picks per popup family.
    """
    mobs = state.mobs
    for channel in range(4):
        if state.score_display_timer[channel]:
            continue
        state.score_display_timer[channel] = _SCORE_POPUP_FRAMES
        popup_slot = _SCORE_POPUP_SLOT + channel
        mobs.picture[popup_slot] = _SCORE_POPUP_PICTURE_TABLE[
            popup % len(_SCORE_POPUP_PICTURE_TABLE)
        ]
        hpos = position_field(mobs.hpos[slot])
        vpos = _u16(position_field(mobs.vpos[slot]) + 0x400)
        if popup < 0x0A:
            hpos += 5           # 0x4954A: palette 5, three tiles wide
            vpos = _u16(vpos + 0x10)
        else:
            hpos += 1           # 0x4956A: palette 1, two tiles wide
            vpos = _u16(vpos + 8)
        mobs.hpos[popup_slot] = _u16(hpos)
        mobs.vpos[popup_slot] = vpos
        mobs.unlink(popup_slot)
        mobs.insert(popup_slot, depth_key=slot)
        return


_playfield_showscore = playfield_showscore


def _potion_blast(state: GameState, shooter_id: int) -> None:
    """Arm the shot-triggered potion state consumed by the monster pass."""
    from .display import ALPHA_PALETTE_INIT

    # resolve_shot_hit 0x4BA6A-0x4BA82 arms the same one-field playfield flash
    # as a drunk potion before storing shooter+4 in potion_player.
    state.playfield_color_latch = ALPHA_PALETTE_INIT[shooter_id * 4 + 7]


def pf_replace(state: GameState, slot: int, obj_type: int) -> None:
    """``pf_replace`` (0x5F31E) -- retile a maze cell in place.

    Replacing with floor takes the ROM's three-way branch at 0x5F352: a static
    tile marker (picture 0x8000/0x8001) only loses its picture and type, so the
    cell keeps the H/V words a following ``shot_impact_spawn`` reads back; a
    real MOB goes through ``mob_free``; an empty cell is left alone.  Stamping
    a new type uses ``maze._place_one``, the port's single reviewed copy of the
    ROM's tile write, which unlinks the previous occupant exactly as
    ``mob_place_tile`` (0x5F310) does.
    """
    if obj_type != int(MazeObjIds.TILE_FLOOR):
        from ..maze import _place_one, set_cell_descriptor

        _place_one(state, slot, obj_type)
        set_cell_descriptor(state, slot, obj_type)
        return

    from ..maze import clear_cell_descriptor

    clear_cell_descriptor(state, slot)
    picture = state.mobs.picture[slot]
    if picture in (0x8000, 0x8001):
        hpos = state.mobs.hpos[slot]
        vpos = state.mobs.vpos[slot]
        state.mobs.unlink_and_clear(slot)
        state.mobs.hpos[slot] = hpos
        state.mobs.vpos[slot] = vpos
    elif picture:
        state.mobs.unlink_and_clear(slot)


def _spawn_maze_object(state: GameState, slot: int, obj_type: int,
                       picture: int) -> None:
    """``mob_create`` (0x5DC58) at the revealed cell (0x4B5FC-0x4B664).

    The ROM rebuilds the H/V words from the master parameter tables inline.
    ``maze.placement_geometry`` is the port's single reviewed copy of exactly
    that arithmetic -- including the fact that 0x5860C carries the packed
    sprite *size*, not a vertical offset -- so reuse it rather than duplicate
    the corrections.  The picture comes from the caller because the secret-wall
    prize randomizes it for a hidden potion, and because this path must not
    gain the extra ``getrandom`` that ``maze.placement_picture`` draws.
    """
    from ..maze import placement_geometry
    hpos, vpos = placement_geometry(obj_type, slot)
    state.mobs.create(slot, picture, hpos, vpos, obj_type, 0)


def wall_crumble(state: GameState, slot: int, damage: int) -> int:
    """0x5303A -- apply shot damage to a destructible wall.

    Returns -1 when the wall is gone and 0 when it only crumbles a step.

    Three ROM branches.  With ``level_flags`` bit 23 (LFLAG2 bit 7) the wall
    vanishes on the first hit (0x53046).  On a shrub level -- ``wallpattern``
    (0x904B5E) >= 6 -- the stage is the tile's own graphic: the ROM matches the
    low 12 bits of the stamped descriptor against ``wall_desc_destructible``
    and destroys the wall outright when nothing matches (0x53084-0x530C6).
    Everywhere else it is a palette crumble (0x530E0-0x53136): the tile starts
    at palette 7 and each hit subtracts ``damage`` from all four quadrant words,
    destroying the wall once the drop would pass the ``(p - 5) & 7`` headroom.
    Both ladders are three steps wide, so the stored stage drives either one.
    """
    if state.level_flags_2 & 0x80:
        # 0x5305C: this branch clears the four MOB words itself and stamps no
        # replacement tile, so it is not the shared destroy tail.
        state.destructible_wall_stage.pop(slot, None)
        state.mobs.link[slot] = 0
        state.mobs.vpos[slot] = 0
        state.mobs.hpos[slot] = 0
        state.mobs.picture[slot] = 0
        from ..maze import clear_cell_descriptor

        clear_cell_descriptor(state, slot)
        return CONSUMED

    stage = state.destructible_wall_stage.get(slot, 0)
    if _wallpattern(state) >= 6:
        # 0x53096: an unrecognised descriptor reads back as a huge stage, so a
        # tile that was never a destructible shrub crumbles away in one hit.
        if not 0 <= stage < len(_WALL_CRUMBLE_DESCS):
            _wall_destroy(state, slot)
            return CONSUMED
        if stage + damage >= len(_WALL_CRUMBLE_DESCS):
            _wall_destroy(state, slot)
            return CONSUMED
    else:
        # 0x530E8: headroom left in the tile's palette nibble, p = 7 - stage.
        if damage > ((7 - stage) - 5) & 7:
            _wall_destroy(state, slot)
            return CONSUMED

    state.destructible_wall_stage[slot] = stage + damage
    from ..playfield_vram import read_tile_descriptor, write_tile_descriptor

    descriptor = wall_crumble_descriptor(state, slot)
    if descriptor is not None:
        write_tile_descriptor(state, slot, descriptor, 0x7000)
    else:
        palette = wall_crumble_palette(state, slot) & 7
        write_tile_descriptor(
            state,
            slot,
            tuple((word & 0x8FFF) | (palette << 12)
                  for word in read_tile_descriptor(state, slot)),
        )
    return 0


def _wall_destroy(state: GameState, slot: int) -> None:
    """0x530FE -- the crumble ladders' shared "wall is gone" tail."""
    state.destructible_wall_stage.pop(slot, None)
    pf_replace(state, slot, int(MazeObjIds.TILE_FLOOR))


def wall_crumble_descriptor(state: GameState, slot: int) -> tuple[int, ...] | None:
    """The tile graphic a crumbling wall should now draw with.

    Shrub levels return the four-stamp ``wall_desc_destructible`` record the
    ROM stamps into the playfield; everywhere else the crumble is a palette
    walk and there is no replacement descriptor.  ``None`` also means "not
    damaged", which is the untouched wall.
    """
    stage = state.destructible_wall_stage.get(slot)
    if stage is None or _wallpattern(state) < 6:
        return None
    return _WALL_CRUMBLE_DESCS[min(stage, len(_WALL_CRUMBLE_DESCS) - 1)]


def wall_crumble_palette(state: GameState, slot: int) -> int:
    """The palette nibble a crumbling wall should now draw with (0x53120)."""
    return 7 - state.destructible_wall_stage.get(slot, 0)


def _wallpattern(state: GameState) -> int:
    """``wallpattern`` (0x904B5E) -- the level's wall tile set."""
    return int(getattr(state.maze, "wallpattern", 0) or 0)


def shot_onscreen_check(state: GameState, target: int,
                        h_limit: int, v_limit: int) -> int:
    """0x4AEA0 -- does the door at ``target`` face the shot that just hit it?

    Reads the separations ``shot_collision_candidate_core`` recorded for the
    accepted candidate and compares them against the door's own open-direction
    bits in ``mob_state_link``.  -1 = react, 0 = ignore.
    """
    door = state.mobs.state_link[target]

    if v_limit > state.collision_dist_V:
        if (door & 0x2000) and _s16(state.shothit_dist_H) > -h_limit:
            return CONSUMED
        if (door & 0x0800) and h_limit > _s16(state.shothit_dist_H):
            return CONSUMED
    if h_limit > state.collision_dist_H:
        if (door & 0x1000) and _s16(state.shothit_dist_V) > -v_limit:
            return CONSUMED
        if (door & 0x0400) and v_limit > _s16(state.shothit_dist_V):
            return CONSUMED
    return 0


# =============================================================================
# shot_mob_collision (0x40906) and its candidate core (0x40A78)
# =============================================================================

def shot_collision_candidate_core(state: GameState, index: int, shooter_id: int,
                    width: int, span: int, shot_h: int, shot_v: int,
                    self_index: int, maxtier: bool) -> int | None:
    """0x40A78 -- accept or reject one probed cell.

    ``index`` is the ROM's word index (``slot * 2``).  Returns the accepted
    MOB slot, or ``None``.  Also publishes the signed and folded separations
    the door check reads back.
    """
    mobs = state.mobs

    if index >= 0x800:
        # 0x40A84: the probe left the maze.  As a u16 this covers both a probe
        # that ran off the top (the index went negative) and one that ran off
        # the bottom.  The ROM wraps by a whole 0x800-word maze and returns the
        # cell as an immediate hit, without any separation test.  It only does
        # so for a non-max-tier shot (0x40A90 tests the sign bit set on the
        # biased hpos) whose own V word is negative and no greater than
        # 0xF3FF -- see ``_wrap_allowed``.  ``_test_probe_wrap`` proves the
        # bottom case cannot occur, so the wrap always lands on row 31.
        if maxtier or not _wrap_allowed(state, shooter_id):
            return None
        index = _u16(index + 0x800)
        assert 0x40 <= index < 0x800, "probe wrapped outside the maze"
        return index >> 1

    if index < 0x40:
        # 0x40A9A-0x40AA0: row 0 shares the reserved MOB band, so an upward
        # shot in the top half of that row returns a 0x400-tagged playfield
        # target instead of reading a MOB record. resolve_shot_hit routes that
        # tag through the ordinary wall/reflect path.
        shot_v = state.mobs.vpos[_shot_slot(shooter_id)] & 0xFFFF
        if maxtier or shot_v <= 0xF3FF:
            return None
        return (index + 0x800) >> 1

    slot = index >> 1
    if mobs.picture[slot] == 0 or index == self_index:
        # 0x40AA6/0x40AAE: an empty cell, or the shooter's own record, is not a
        # candidate. A live hero *is* one -- its record migrates into the cell
        # it stands in, so the probe finds it here like any other occupant.
        return None

    picture = mobs.picture[slot]
    if picture & 0x8000:
        # 0x40B02: a static playfield tile is snapped to its cell first.
        sep_h = _u16(((mobs.hpos[slot] + 0x280) & 0xF800) - shot_h)
        sep_v = _u16(((mobs.vpos[slot] + 0x100) & 0xF800) - shot_v)
    else:
        sep_h = _u16(
            position_field(mobs.hpos[slot]) - shot_h + 0x200
        )
        sep_v = _u16(
            position_field(mobs.vpos[slot]) - shot_v
        )

    state.shothit_dist_H = sep_h
    folded_h = sep_h ^ POS_FIELD_MASK if sep_h & 0x8000 else sep_h
    if folded_h >= width:
        return None
    state.collision_dist_H = folded_h

    state.shothit_dist_V = sep_v
    folded_v = sep_v ^ POS_FIELD_MASK if sep_v & 0x8000 else sep_v
    if folded_v >= width:
        return None
    state.collision_dist_V = folded_v

    if span < _u16(folded_v + folded_h):
        return None

    if maxtier and _MAXTIER_PASS_TBL[mobs.obj_type(slot)] != 0:
        return None      # 0x40B3A: this type ignores a max-tier shot
    return slot


def _wrap_allowed(state: GameState, shooter_id: int) -> bool:
    """The vertical window at 0x40A88/0x40A8A gates the probe's maze wrap.

    Straight off the ROM now that the V word is the hardware's own: "negative
    and no greater than 0xF3FF", i.e. the shot has to be level with the bottom
    half of row 0 (9 <= screen y <= 240) before a probe may wrap to row 31.

    The companion window at 0x40A9A, ``V > 0xF3FF``, guards the row-0 case
    ``shot_collision_candidate_core`` refuses outright.
    """
    vpos = state.mobs.vpos[_shot_slot(shooter_id)] & 0xFFFF
    return 0x8000 <= vpos <= 0xF3FF


def shot_mob_collision(state: GameState, cell: int, shooter_id: int) -> int:
    """0x40906 -- the first MOB this shot overlaps, or -1.

    ``cell`` is the shot's own packed maze cell (the ROM passes
    ``mob_depth_key[shot]``).  The shot's own cell is probed first, then the
    five direction-dependent offsets from ``shot_collision_probe_offsets``.
    """
    mobs = state.mobs
    slot = _shot_slot(shooter_id)
    maxtier = _is_maxtier(state, shooter_id)

    if shooter_id >= 4:
        if maxtier:
            width, span = _MAXTIER_HITBOX_WIDTH, _MAXTIER_HITBOX_SPAN
        else:
            width = _SHOT_HITBOX_WIDTH[shooter_id]
            span = _SHOT_HITBOX_SPAN[shooter_id]
    else:
        character = state.players[shooter_id].character & 0x03
        width = _SHOT_HITBOX_WIDTH[character]
        span = _SHOT_HITBOX_SPAN[character]

    shot_h = mobs.hpos[slot]
    shot_v = mobs.vpos[slot]
    if maxtier:
        shot_h = _u16(shot_h + _MAXTIER_H_BIAS)
    shot_h = position_field(shot_h)
    shot_v = position_field(shot_v)

    self_index = _u16(_shot_owner(state, shooter_id) * 2)
    if shooter_id < 4 and state.reflect_count[shooter_id] != 4:
        self_index |= 0x8000    # 0x409BA: a reflected shot may hit its owner

    index = _u16(cell * 2)
    hit = shot_collision_candidate_core(
        state, index, shooter_id, width, span, shot_h, shot_v,
        self_index, maxtier,
    )
    if hit is not None:
        return _dragon_hitbox_retry(state, hit, shooter_id, shot_h, shot_v,
                                    self_index, maxtier)

    row_base = index & 0x7C0
    for h_delta, v_delta in _PROBE_OFFSETS[_live_direction(state, shooter_id) & 7]:
        index = _u16(_u16(index + h_delta) & 0x3E)
        index = _u16(index + v_delta + row_base)
        hit = shot_collision_candidate_core(
            state, index, shooter_id, width, span, shot_h, shot_v,
            self_index, maxtier,
        )
        if hit is not None:
            return _dragon_hitbox_retry(state, hit, shooter_id, shot_h,
                                        shot_v, self_index, maxtier)
    return -1


def _dragon_hitbox_retry(state: GameState, slot: int, shooter_id: int,
                         shot_h: int, shot_v: int, self_index: int,
                         maxtier: bool) -> int:
    """0x40A3E -- the dragon gets a second, tighter pass over the same cell."""
    if slot >= 0x400:
        return slot
    if state.mobs.obj_type(slot) != int(MazeObjIds.MONST_DRAGON):
        return slot
    character = (
        state.players[shooter_id].character & 0x03 if shooter_id < 4 else 0
    )
    facing = state.dragon_facing & 0x06
    # dragon_head_hitbox_offsets, ROM 0x54BD6. Facing indexes these as byte
    # offsets: V reads table[facing/2], H reads the following word.
    offsets = (0x0400, 0, 0x0400, 0, 0x0400)
    hsep = _u16(state.dragon_head_hpos - shot_h)
    if hsep & 0x8000:
        hsep ^= POS_FIELD_MASK
    hsep = _s16(hsep - offsets[(facing >> 1) + 1])
    width = _DRAGON_HITBOX_WIDTH[character]
    if hsep >= width:
        return slot

    vsep = _u16(state.dragon_head_vpos - shot_v)
    if vsep & 0x8000:
        vsep ^= POS_FIELD_MASK
    vsep = _s16(vsep - offsets[facing >> 1])
    if vsep >= width or hsep + vsep >= _DRAGON_HITBOX_SPAN[character]:
        return slot

    # The ROM adds 0x1000 to the doubled MOB index and then shifts right once,
    # so the public packed-cell result carries 0x0800 on a moving-head hit.
    return slot | 0x0800


def _shot_owner(state: GameState, shooter_id: int) -> int:
    """``active_mob_ids[shooter]`` (0x9048C8) -- the MOB that fired."""
    if shooter_id < 4:
        return state.players[shooter_id].mob_slot
    owner = state.shot_owner_mob[shooter_id]
    return owner if owner >= 0 else 0


# =============================================================================
# shot_reflect_calc (0x53818)
# =============================================================================

_REFLECT_NONE = 0        # 0x53CAE: unchanged, and no counter/cell update
_REFLECT_KEEP = 1        # 0x53CB4: finish with the direction as computed
_REFLECT_XOR2 = 2        # 0x53CB6
_REFLECT_XOR6 = 3        # 0x53CB0

# 0x538FE / 0x53924 / 0x53948 / 0x5396A / 0x53992: the five signed-delta
# bands, each five entries wide, that pick the corner handler.
_REFLECT_BANDS = {
    -2: "A_", -1: "A_", 0: None, 1: "B_", 2: "B_",
    -66: "UL", -65: "UL", -64: None, -63: "UR", -62: "UR",
    -34: "UL", -33: "UL", -32: "U_", -31: "UR", -30: "UR",
    30: "DL", 31: "DL", 32: "D_", 33: "DR", 34: "DR",
    62: "DL", 63: "DL", 64: None, 65: "DR", 66: "DR",
}


def shot_reflect_calc(state: GameState, target: int, shooter_id: int) -> int:
    """0x53818 -- the direction a reflected shot leaves the wall with.

    Cardinal shots simply reverse.  A diagonal picks its bounce from the
    signed cell delta between this wall and the last one, then confirms it
    against the two neighbouring wall pictures, exactly as 0x5399C-0x53C98 do.
    """
    mobs = state.mobs
    direction = state.shot_direction[shooter_id] & 0xFFFF
    if 0 <= direction <= 7 and not direction & 1:
        return _reflect_finish(state, target, shooter_id, direction ^ 4,
                               _REFLECT_KEEP)
    if not 0 <= direction <= 7:
        direction = _live_direction(state, shooter_id)
        if not direction & 1:
            return _reflect_finish(state, target, shooter_id, direction ^ 4,
                                   _REFLECT_KEEP)

    if target >= 0x400:
        # 0x53850: with no MOB to inspect, the shot's own vertical position
        # decides.  The ROM's ``vpos > 0xF7FF`` is "within 8 pixels of the top
        # of the maze" in the hardware's upward V word.
        near_top = (mobs.vpos[_shot_slot(shooter_id)] & 0xFFFF) > 0xF7FF
        if direction in (1, 7):
            outcome = _REFLECT_NONE if near_top else _REFLECT_XOR2
        else:
            outcome = _REFLECT_XOR2 if near_top else _REFLECT_NONE
        return _reflect_finish(state, target, shooter_id, direction, outcome)

    delta = _s16(target - state.player_shot_last_wall_pos[shooter_id])
    if delta > 0x200:
        delta -= 0x400
    if (state.player_shot_last_wall_pos[shooter_id] & 0x3E0) == (target & 0x3E0):
        if delta > 2:
            delta -= 0x20
        elif delta < -2:
            delta += 0x20

    band = _REFLECT_BANDS.get(delta)
    if band is None:
        return _reflect_finish(state, target, shooter_id, direction,
                               _REFLECT_NONE)

    direction, outcome = _reflect_corner(state, target, shooter_id,
                                         direction, band)
    return _reflect_finish(state, target, shooter_id, direction, outcome)


# Each corner handler owns one diagonal; anything else snaps to its partner.
# (expected direction, fallback direction, column step, row step, negate H)
_REFLECT_CORNERS = {
    "UL": (7, 3, +1, +1, True),    # 0x5399C
    "UR": (1, 5, -1, +1, False),   # 0x53A50
    "DL": (5, 1, +1, -1, False),   # 0x53AFC
    "DR": (3, 7, -1, -1, True),    # 0x53BA6
}


def _reflect_corner(state: GameState, target: int, shooter_id: int,
                    direction: int, band: str) -> tuple[int, int]:
    """0x5399C / 0x53A50 / 0x53AFC / 0x53BA6 and their three dispatchers."""
    if band == "A_":       # 0x53C84, same row, wall to the left
        if direction == 5:
            band = "DL"
        elif direction == 7:
            band = "UL"
        else:
            return direction, _REFLECT_NONE
    elif band == "B_":     # 0x53C98, same row, wall to the right
        if direction == 1:
            band = "UR"
        elif direction == 3:
            band = "DR"
        else:
            return direction, _REFLECT_NONE
    elif band == "U_":     # 0x53C58, one row up
        if direction == 1:
            band = "UR"
        elif direction == 7:
            band = "UL"
        else:
            return direction, _REFLECT_NONE
    elif band == "D_":     # 0x53C6E, one row down
        if direction == 3:
            band = "DR"
        elif direction == 5:
            band = "DL"
        else:
            return direction, _REFLECT_NONE

    expected, fallback, col_step, row_step, negate_h = _REFLECT_CORNERS[band]
    if direction != expected:
        return fallback, _REFLECT_KEEP

    mobs = state.mobs
    side = (target & 0xFFE0) | ((target + col_step) & 0x1F)
    if mobs.picture[side] == 0x8000:
        direction ^= 2
    above = target + (row_step << 5)
    if not 0 <= above < 0x400 or mobs.picture[above] == 0x8000:
        direction ^= 6

    if direction != state.shot_direction[shooter_id]:
        return direction, _REFLECT_KEEP

    shot = _shot_slot(shooter_id)
    sep_h = mobs.hpos[target] - mobs.hpos[shot]
    if negate_h:
        sep_h = -sep_h
    sep_v = _s16(mobs.vpos[target] - mobs.vpos[shot])
    nearer = _s16(sep_h) < sep_v
    if band in ("UL", "UR"):
        return direction, _REFLECT_XOR2 if nearer else _REFLECT_XOR6
    return direction, _REFLECT_XOR6 if nearer else _REFLECT_XOR2


def _reflect_finish(state: GameState, target: int, shooter_id: int,
                    direction: int, outcome: int) -> int:
    """0x53CB0-0x53D02 -- apply the outcome, spend a bounce, remember the wall."""
    if outcome == _REFLECT_NONE:
        return direction
    if outcome == _REFLECT_XOR2:
        direction ^= 2
    elif outcome == _REFLECT_XOR6:
        direction ^= 6

    state.reflect_count[shooter_id] = _u16(state.reflect_count[shooter_id] - 1)
    if state.reflect_count[shooter_id] != 0:
        _sound(state, _SOUND_REFLECT)

    if target >= 0x190:
        slot = _shot_slot(shooter_id)
        key = state.mobs.depth_key[slot] if slot < len(state.mobs.depth_key) else 0
        state.player_shot_last_wall_pos[shooter_id] = key
    else:
        state.player_shot_last_wall_pos[shooter_id] = target
    return direction & 7


# =============================================================================
# main_handle_shots (0x474F6)
# =============================================================================

def _screen_origins(state: GameState) -> tuple[int, int]:
    """The ROM's ``scroll_hpos_origin``/``scroll_vpos_origin`` (0x904AC2/4).

    ``(pf_hscroll - 8) << 7`` and ``(0x108 - pf_vscroll_lo) << 7``, verbatim:
    ``state.scroll_y`` *is* the ROM's vertical scroll register.
    """
    origin_h = _u16((state.scroll_x - _SCREEN_H_BIAS) << POS_SHIFT)
    origin_v = _u16((_SCREEN_V_REF - state.scroll_y) << POS_SHIFT)
    return origin_h, origin_v


def _heads_back(direction: int, axis: str, negative: bool) -> bool:
    """0x47748-0x477B6 -- is the shot travelling back toward the window?"""
    if axis == "h":
        return direction in ((1, 2, 3) if negative else (5, 6, 7))
    return direction in ((7, 0, 1) if negative else (3, 4, 5))


def _offscreen(state: GameState, shooter_id: int, direction: int) -> bool:
    """0x47716-0x477B6 -- whether this shot has left the playfield window."""
    slot = _shot_slot(shooter_id)
    origin_h, origin_v = _screen_origins(state)
    delta_h = _maze_position(state.mobs.hpos[slot] - origin_h)
    delta_v = _maze_position(state.mobs.vpos[slot] - origin_v)

    if delta_h > _SCREEN_W:
        if _maze_position(delta_h + _SCREEN_MARGIN) > _SCREEN_W_TOL:
            return True
        if not _heads_back(direction, "h", delta_h >= _SCREEN_NEG):
            return True
    if delta_v > _SCREEN_H:
        if _maze_position(delta_v + _SCREEN_MARGIN) > _SCREEN_H_TOL:
            return True
        if not _heads_back(direction, "v", delta_v >= _SCREEN_NEG):
            return True
    return False


def _remove_shot(state: GameState, shooter_id: int) -> None:
    """0x477B8 -- drop the shot channel, clearing H/V as well."""
    slot = _shot_slot(shooter_id)
    _channel_clear(state, shooter_id)
    state.mobs.hpos[slot] = 0
    state.mobs.vpos[slot] = 0
    state.shot_lifetime[slot] = 0


def _advance_counter(state: GameState, shooter_id: int) -> int:
    """0x475D0-0x47620 -- predecrement, reload from ``shot_counter_reload``."""
    counter = _s16(state.shot_anim_lifetime_counter[shooter_id] - 1)
    if counter < 0:
        if shooter_id < 4:
            counter = _SHOT_COUNTER_RELOAD[
                state.players[shooter_id].character & 0x03
            ]
        else:
            counter = _SHOT_COUNTER_RELOAD[shooter_id]
    state.shot_anim_lifetime_counter[shooter_id] = counter
    return counter


def shot_picture(state: GameState, shooter_id: int, counter: int) -> int:
    """The projectile picture channel ``shooter_id`` shows at ``counter``.

    The three ROM tables and the index arithmetic of 0x47622-0x47716, factored
    out so the two places that need an exact projectile frame agree by
    construction: this module's per-frame animation, and
    ``monsters.monster_create_shot`` (0x490DC), which arms a channel with the
    very frame the next animation tick would land on.

    * player channels 0-3 index ``projectile_picture_table`` by
      ``(direction*2 + counter) & 0x0F`` inside the character's 16-word block;
    * demon channels 4-7 by ``direction*2 + counter + 0x20``, unless the shot
      is max tier, which swaps in ``special_projectile_picture_table``;
    * lobber channels 8-11 ignore direction entirely -- the rock's spin is the
      counter alone, in ``monster_projectile_picture_table``.
    """
    direction = _live_direction(state, shooter_id) & 7

    if shooter_id < 4:
        index = (direction * 2 + counter) & 0x0F
        index += (state.players[shooter_id].character & 0x03) << 4
        return _PROJECTILE_PICTURE_TBL[index & 0x3F]
    if shooter_id < 8:
        if _is_maxtier(state, shooter_id):
            index = (direction & 6) * 10 + counter
            table = _SPECIAL_PROJECTILE_PICTURE_TBL
        else:
            index = direction * 2 + counter + 0x20
            table = _PROJECTILE_PICTURE_TBL
        return table[index % len(table)]
    table = _MONSTER_PROJECTILE_PICTURE_TBL
    return table[counter % len(table)]


def _advance_picture(state: GameState, shooter_id: int, counter: int) -> None:
    """0x47622-0x47716 -- the class-specific projectile animation."""
    state.mobs.picture[_shot_slot(shooter_id)] = shot_picture(
        state, shooter_id, counter
    )


def _velocity_row(state: GameState, shooter_id: int, direction: int) -> int:
    """0x47846 / 0x478B8 -- which velocity row this channel uses.

    Only channels 0-7 reach here: the lobbed-rock channels 8-11 branch
    away at 0x478B4 before any table is read (see ``_advance_lobber``).
    """
    if shooter_id < 4:
        row = ((state.players[shooter_id].character & 0x03) << 3) + direction
        if state.players[shooter_id].powers & 0x08:      # shot-speed upgrade
            row += _VEL_SHOTSPEED
        return row
    tier = _shot_tier(state, shooter_id)
    if tier == _SHOT_TIER_MASK:
        return direction + _VEL_MONSTER_MAXTIER
    if tier & 0x20:
        return direction + _VEL_MONSTER_TIER2
    return direction + _VEL_MONSTER_BASE


def shot_velocity(state: GameState, shooter_id: int,
                  direction: int) -> tuple[int, int]:
    """This frame's signed H/V word delta for a straight channel (0-7).

    Public so a shot creator can seed ``shot_dx/dy`` with the very step its
    channel will take, instead of guessing one.  Both components are in the
    hardware's own axes, so the V delta is positive up the screen.
    """
    row = _velocity_row(state, shooter_id, direction)
    return _SHOT_VELOCITY_X[row], _SHOT_VELOCITY_Y[row]


def lobber_accumulator_seed(state: GameState, shooter_id: int) -> None:
    """0x49216/0x4922A -- point a lobber channel's accumulators at its MOB.

    ``monster_create_shot`` seeds the pair from the masked spawn position, one
    instruction before it writes the same value plus the palette (0x4925A) and
    the sprite size (0x49270) into the MOB words -- so the accumulator's low
    bits start at zero and the first ``_advance_lobber`` reproduces the spawn
    position exactly, plus one vector step.  Exposed so the creators and
    ``main_handle_shots``' go-live latch agree by construction.
    """
    lobber = shooter_id - 8
    slot = _shot_slot(shooter_id)
    state.lobber_shot_h_accum[lobber] = position_field(state.mobs.hpos[slot])
    state.lobber_shot_v_accum[lobber] = position_field(state.mobs.vpos[slot])


def _advance_lobber(state: GameState, shooter_id: int) -> None:
    """0x479C2-0x47A58 -- the lobbed-rock channels 8-11.

    Only a lobber's thrown rock lands here.  The dragon's fire does *not*:
    ``dragon_find_free_shot_slot`` (0x540E8) puts it in the demon channels
    4-7, so it moves off ``shot_velocity_x/y`` like any other monster shot.

    These four never touch ``shot_velocity_x/y``: they carry their own signed
    per-shot vector (``lobber_shot_vec_h/v``, 0x9048F8/0x904900, written once
    by ``monster_find_and_shoot``'s lead calculation at 0x419FA/0x41A10) and a
    private 16-bit accumulator per channel (``lobber_shot_h_accum/v_accum``,
    0x904A66/0x904A6E).  The accumulator *is* the shot's fine position: each
    frame the vector is added to it, the top bits are copied into the MOB word
    and the low bits stay as the sub-pixel remainder.  That remainder is the
    whole point -- a lead of, say, 0xC0 per frame is 1.5 px, and only the
    accumulator can carry the half.

    The ROM writes ``hpos = (accum & 0xFF80) + (hpos & 0x7F)``, i.e. it keeps
    the channel's palette/flags (and, vertically, its sprite size) untouched
    and replaces only the position field. ``coords.replace_position`` performs
    that split, and the creators store the ROM's own vector.

    ``shot_dx/dy`` are deliberately left alone: the vector never changes
    during a rock's flight, so ``monster_create_shot``'s rounded seed still
    describes the motion and ``thief.py``'s dodge scan keeps reading it.
    """
    slot = _shot_slot(shooter_id)
    lobber = shooter_id - 8

    accum_h = _u16(state.lobber_shot_h_accum[lobber]
                   + state.lobber_shot_vec_h[lobber])
    accum_v = _u16(state.lobber_shot_v_accum[lobber]
                   + state.lobber_shot_vec_v[lobber])
    state.lobber_shot_h_accum[lobber] = accum_h
    state.lobber_shot_v_accum[lobber] = accum_v

    state.mobs.hpos[slot] = replace_position(state.mobs.hpos[slot], accum_h)
    state.mobs.vpos[slot] = replace_position(state.mobs.vpos[slot], accum_v)


def _advance_position(state: GameState, shooter_id: int, direction: int) -> None:
    """0x47830-0x47A58 -- apply this frame's velocity to the shot MOB.

    Three class branches, exactly as the ROM dispatches them: player channels
    at 0x47846, monster channels at 0x478B8 (where a max-tier shot only moves
    on even frames, 0x478CE), and the lobbed-rock channels at 0x479C2.
    The velocity tables are the ROM's own native words.
    """
    if shooter_id >= 8:
        _advance_lobber(state, shooter_id)
        return

    slot = _shot_slot(shooter_id)
    if shooter_id >= 4 and _is_maxtier(state, shooter_id) \
            and (state.frame_counter & 1):
        return

    dx, dv = shot_velocity(state, shooter_id, direction)
    state.mobs.hpos[slot] = _u16(state.mobs.hpos[slot] + dx)
    state.mobs.vpos[slot] = _u16(state.mobs.vpos[slot] + dv)
    state.shot_dx[slot] = dx >> POS_SHIFT
    state.shot_dy[slot] = dv >> POS_SHIFT


def _reposition_in_chain(state: GameState, shooter_id: int, cell: int) -> None:
    """0x47A7E-0x47B12 -- re-key the shot when it changes maze cell."""
    slot = _shot_slot(shooter_id)
    previous = state.mobs.depth_key[slot] if slot < len(state.mobs.depth_key) else 0
    if cell == previous:
        return

    if shooter_id < 4:
        # 0x47A98: forget the last wall once the shot is two cells clear of
        # it, so a bounce cannot immediately re-trigger on the same wall.
        gap = abs(_s16(state.player_shot_last_wall_pos[shooter_id] - cell))
        if gap > 0x21 or (
            (state.player_shot_last_wall_pos[shooter_id] ^ cell) & 0x21
        ) == 0x21:
            state.player_shot_last_wall_pos[shooter_id] = previous

    state.mobs.unlink(slot)
    state.mobs.insert(slot, depth_key=cell)


def main_handle_shots(state: GameState) -> None:
    """0x474F6 -- advance the twelve projectile channels.

    Per channel: the collision probe, the animation/lifetime counter and its
    picture, the off-screen window, the class-specific motion, and the depth
    re-key when the shot crosses into a new maze cell.  Its player-channel
    input gate first arms the throw animation in ``players.py``; free channels
    re-arm ``reflect_count`` (0x47BC2).
    """
    # 0x47B72-0x47BF6 runs in this ROM routine, before main_move_players selects
    # that throw's picture.  Keep the state/picture policy in players.py.
    from .players import player_shooting_input_update

    player_shooting_input_update(state)

    # 0x4750C: the demon/lobber shot cadence timers tick here.
    for i in range(8):
        if state.shot_timer_next[i]:
            state.shot_timer_next[i] -= 1

    for shooter_id in range(12):
        slot = _shot_slot(shooter_id)
        if state.mobs.picture[slot] == 0:
            if shooter_id < 4:
                state.reflect_count[shooter_id] = 4
                state.shot_owner_mob[shooter_id] = -1
            continue

        cell = state.mobs.depth_key[slot]
        if state.shot_owner_mob[shooter_id] < 0:
            # Identity is location: a fresh shot still sits on its shooter.
            state.shot_owner_mob[shooter_id] = _shot_cell(state, slot)
            if not cell:
                cell = state.shot_owner_mob[shooter_id]
                state.mobs.depth_key[slot] = cell
            if shooter_id >= 4:
                # The ROM seeds the counter in monster_create_shot (0x490FE)
                # and dragon_fire_setup (0x5480E/0x548A4).  Both of the port's
                # creators do so too, but a channel armed by anything else
                # would otherwise start at zero -- and for 8-11 this word *is*
                # the shot's lifetime, so that would kill it immediately.
                state.shot_anim_lifetime_counter[shooter_id] = (
                    _SHOT_COUNTER_RELOAD[shooter_id]
                )
            if shooter_id >= 8:
                # Same reasoning for the arc accumulators (0x49216/0x4922A):
                # a channel that reached here without ``monster_create_shot``
                # has none, and an unseeded pair would teleport the rock to
                # the top-left corner on its first step.
                lobber_accumulator_seed(state, shooter_id)

        # ---- collision (0x4755C) ----
        probe = True
        if shooter_id >= 8:
            counter = state.shot_anim_lifetime_counter[shooter_id]
            probe = 0 <= counter < 6
        if probe:
            target = shot_mob_collision(state, cell, shooter_id)
            if target >= 0 and resolve_shot_hit(state, target, shooter_id) != 0:
                continue

        # ---- animation / lifetime (0x475BA) ----
        if ((state.frame_counter ^ shooter_id) & 1) == 0:
            counter = _advance_counter(state, shooter_id)
            _advance_picture(state, shooter_id, counter)

        direction = _live_direction(state, shooter_id) & 7

        # ---- off-screen disposal (0x47716) ----
        if _offscreen(state, shooter_id, direction):
            _remove_shot(state, shooter_id)
            continue

        # ---- lifetime expiry (0x477E8) ----
        if state.shot_anim_lifetime_counter[shooter_id] == 0 and (
            shooter_id >= 8 or _is_maxtier(state, shooter_id)
        ):
            if shooter_id >= 8:
                shot_impact_spawn(state, slot, shooter_id)
            _remove_shot(state, shooter_id)
            continue

        # ---- motion (0x47830) ----
        _advance_position(state, shooter_id, direction)
        state.shot_lifetime[slot] += 1
        _reposition_in_chain(state, shooter_id, _shot_cell(state, slot))
