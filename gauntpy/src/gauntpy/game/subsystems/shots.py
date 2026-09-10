"""Projectiles and hit resolution -- WP-7.

Projectile ticks and effects stay here; collision and damage routines belong
to ``shot_collision`` and ``shot_damage`` with identity-preserving reexports.

Twelve fixed channels: player shots in MOB slots 1-4, ordinary monster shots
5-8, lobbed rocks 9-12.  Fixed slots mean no allocation and no search
-- that is the design, not an optimization to add later.  A channel's
*shooter id* is ``slot - 1``, which is how every ROM table below is indexed.
The dragon has no channels of its own: ``dragon_find_free_shot_slot``
(0x540E8) hands its fire one of the monster channels 5-8.

Reference: ``doc/04_game_subsystems.md`` §26, §3.6, §23;
``doc/generated/monster_combat_contracts.csv``; ``book/02_one_arrow.md``.
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
    hpos_x, mob_words_to_slot, position_field, replace_position, vpos_y,
)
from ..state import GameState
from ..playfield import pf_replace as pf_replace
from .score import player_add_score_with_mult as player_add_score_with_mult


# Compatibility exports; each routine and table has a single game-side owner.
from .shot_collision import (
    _DRAGON_HITBOX_SPAN as _DRAGON_HITBOX_SPAN,
    _DRAGON_HITBOX_WIDTH as _DRAGON_HITBOX_WIDTH,
    _MAXTIER_HITBOX_SPAN as _MAXTIER_HITBOX_SPAN,
    _MAXTIER_HITBOX_WIDTH as _MAXTIER_HITBOX_WIDTH,
    _MAXTIER_H_BIAS as _MAXTIER_H_BIAS,
    _MAXTIER_PASS_TBL as _MAXTIER_PASS_TBL,
    _PROBE_OFFSETS as _PROBE_OFFSETS,
    _REFLECT_BANDS as _REFLECT_BANDS,
    _REFLECT_CORNERS as _REFLECT_CORNERS,
    _REFLECT_KEEP as _REFLECT_KEEP,
    _REFLECT_NONE as _REFLECT_NONE,
    _REFLECT_XOR2 as _REFLECT_XOR2,
    _REFLECT_XOR6 as _REFLECT_XOR6,
    _SHOT_HITBOX_SPAN as _SHOT_HITBOX_SPAN,
    _SHOT_HITBOX_WIDTH as _SHOT_HITBOX_WIDTH,
    _SOUND_REFLECT as _SOUND_REFLECT,
    _dragon_hitbox_retry as _dragon_hitbox_retry,
    _reflect_corner as _reflect_corner,
    _reflect_finish as _reflect_finish,
    _shot_owner as _shot_owner,
    _wrap_allowed as _wrap_allowed,
    shot_collision_candidate_core as shot_collision_candidate_core,
    shot_mob_collision as shot_mob_collision,
    shot_onscreen_check as shot_onscreen_check,
    shot_reflect_calc as shot_reflect_calc,
)
from .shot_damage import (
    SURVIVES as SURVIVES,
    _DIALOG_DEMON_SHOT as _DIALOG_DEMON_SHOT,
    _DIALOG_DRAGON_SHOT as _DIALOG_DRAGON_SHOT,
    _DIALOG_FOOD_SHOT as _DIALOG_FOOD_SHOT,
    _DIALOG_LOBBER_SHOT as _DIALOG_LOBBER_SHOT,
    _DIALOG_PLAYER_SHOT as _DIALOG_PLAYER_SHOT,
    _DIALOG_POISON_SHOT as _DIALOG_POISON_SHOT,
    _DIALOG_POTION_SHOT as _DIALOG_POTION_SHOT,
    _DIALOG_STRONG_SHOT as _DIALOG_STRONG_SHOT,
    _DIALOG_WALL_SHOT as _DIALOG_WALL_SHOT,
    _DOOR_LIMIT as _DOOR_LIMIT,
    _GAME_MODE_SECRET as _GAME_MODE_SECRET,
    _GEN_BASE as _GEN_BASE,
    _GEN_TOP as _GEN_TOP,
    _LFLAG4_SHOTHURT as _LFLAG4_SHOTHURT,
    _LFLAG4_SHOTSTUN as _LFLAG4_SHOTSTUN,
    _MAZEOBJ_BASE_PICTURE_TBL as _MAZEOBJ_BASE_PICTURE_TBL,
    _MAZEOBJ_HSIZE_TIER_TBL as _MAZEOBJ_HSIZE_TIER_TBL,
    _MONSTSHOT_DAMAGE_TBL as _MONSTSHOT_DAMAGE_TBL,
    _MONST_PHASED as _MONST_PHASED,
    _PIC_SLOWMO_FOOD as _PIC_SLOWMO_FOOD,
    _PIC_SLOWMO_POTION as _PIC_SLOWMO_POTION,
    _PLAYER_PALETTE_MIN as _PLAYER_PALETTE_MIN,
    _POWER_ARMOR as _POWER_ARMOR,
    _POWER_REFLECT as _POWER_REFLECT,
    _POWER_SHOTPOWER as _POWER_SHOTPOWER,
    _PRIZE_HIDDENPOT_BASE as _PRIZE_HIDDENPOT_BASE,
    _SCORE_MULT_DEATH_IT as _SCORE_MULT_DEATH_IT,
    _SCORE_MULT_GENERATOR as _SCORE_MULT_GENERATOR,
    _SCORE_MULT_GHOST as _SCORE_MULT_GHOST,
    _SCORE_MULT_GRUNT as _SCORE_MULT_GRUNT,
    _SCORE_MULT_SUPERSORC as _SCORE_MULT_SUPERSORC,
    _SHOT_DAMAGE_BASE_TBL as _SHOT_DAMAGE_BASE_TBL,
    _SHOT_DAMAGE_RAND_TBL as _SHOT_DAMAGE_RAND_TBL,
    _SHOT_FOOD_SPEECH as _SHOT_FOOD_SPEECH,
    _SHOT_HP_HIT as _SHOT_HP_HIT,
    _SHOT_HURT_COOLDOWN as _SHOT_HURT_COOLDOWN,
    _SHOT_STUN_ADD as _SHOT_STUN_ADD,
    _SHOT_STUN_MAX as _SHOT_STUN_MAX,
    _SLOWMO_FOOD_FRAMES as _SLOWMO_FOOD_FRAMES,
    _SLOWMO_POTION_FRAMES as _SLOWMO_POTION_FRAMES,
    _SOUND_PLAYER_HIT as _SOUND_PLAYER_HIT,
    _SOUND_POTION_BREAK as _SOUND_POTION_BREAK,
    _SOUND_SECRET_WALL as _SOUND_SECRET_WALL,
    _SOUND_SLOWMO as _SOUND_SLOWMO,
    _SUPERSHOT_DAMAGE as _SUPERSHOT_DAMAGE,
    _SUPERSHOT_HP_HIT as _SUPERSHOT_HP_HIT,
    _TASK_SHOOT_SECRET_A as _TASK_SHOOT_SECRET_A,
    _TASK_SHOOT_SECRET_B as _TASK_SHOOT_SECRET_B,
    _TASK_SHOOT_TREASURE as _TASK_SHOOT_TREASURE,
    _TYPES_GRUNT_CLASS as _TYPES_GRUNT_CLASS,
    _TYPES_NO_EFFECT as _TYPES_NO_EFFECT,
    _TYPES_TREASURE as _TYPES_TREASURE,
    _TYPES_WALL as _TYPES_WALL,
    _WALL_MOVE_DISSOLVE as _WALL_MOVE_DISSOLVE,
    _WALL_MOVE_HIT_UNIT as _WALL_MOVE_HIT_UNIT,
    _channel_clear as _channel_clear,
    _consume as _consume,
    _destroy_target as _destroy_target,
    _dialog as _dialog,
    _finish as _finish,
    _handle_death as _handle_death,
    _handle_destructible_wall as _handle_destructible_wall,
    _handle_door as _handle_door,
    _handle_dragon as _handle_dragon,
    _handle_food as _handle_food,
    _handle_generator as _handle_generator,
    _handle_generic_wall as _handle_generic_wall,
    _handle_it as _handle_it,
    _handle_monster as _handle_monster,
    _handle_player_victim as _handle_player_victim,
    _handle_playerstart as _handle_playerstart,
    _handle_potion as _handle_potion,
    _handle_secret_wall as _handle_secret_wall,
    _handle_sorcerer as _handle_sorcerer,
    _handle_supersorc as _handle_supersorc,
    _handle_treasure as _handle_treasure,
    _handle_wall as _handle_wall,
    _handle_wall_tail as _handle_wall_tail,
    _hurt_latch as _hurt_latch,
    _kill_bookkeeping as _kill_bookkeeping,
    _monster_shot_on_player as _monster_shot_on_player,
    _monstshot_damage_index as _monstshot_damage_index,
    _score_tail as _score_tail,
    _shot_damage as _shot_damage,
    _supershot as _supershot,
    _trick_bump as _trick_bump,
    _trick_set as _trick_set,
    death_damage_accumulate as death_damage_accumulate,
    resolve_shot_hit as resolve_shot_hit,
)
from .shot_data import (
    CONSUMED as CONSUMED,
)

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
# Shot strength/tier lives in hpos bits 4-5 of the *shot's* MOB word.
_SHOT_TIER_MASK = 0x30

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


def _u32(value: int) -> int:
    return value & 0xFFFF_FFFF


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
                  picture: int, vpos_add: int, counter: int, *,
                  hpos_add: int = 0, depth_key: int | None = None) -> None:
    """Install a temporary effect MOB at a tile-aligned source position."""
    state.mobs.picture[effect_slot] = picture
    state.mobs.hpos[effect_slot] = (
        position_field(state.mobs.hpos[source_slot]) + hpos_add + 1
    ) & 0xFFFF
    state.mobs.vpos[effect_slot] = (
        position_field(state.mobs.vpos[source_slot]) + vpos_add
    ) & 0xFFFF
    if depth_key is None:
        depth_key = source_slot
    state.mobs.insert(effect_slot, depth_key=depth_key)
    state.mob_effect_anim_counter[effect_slot - 0x0D] = counter & 0xFF


def _impact_geometry(
    state: GameState, target: int, shooter: int,
) -> tuple[int, int, int]:
    """Return ``(source_slot, hpos_add, depth_key)`` from 0x47E6A-0x47F7E."""
    if target >= 0x400:
        depth_key = target - 0x400
        if depth_key < 0x20:
            depth_key += 0x20
        elif depth_key > 0x400:
            depth_key -= 0x20
        return _shot_slot(shooter), 0, depth_key

    if target & 0x1F or state.level_flags_4 & 0x20:
        hpos_add = 0 if state.mobs.hpos[target] & 0x38 <= 8 else 0x200
        source_slot = target
    else:
        hpos_add = 0
        source_slot = _shot_slot(shooter)

    if target < 0x20:
        hpos = position_field(state.mobs.hpos[source_slot]) + hpos_add + 1
        vpos = position_field(state.mobs.vpos[source_slot]) + 9
        target = mob_words_to_slot(hpos, vpos, x_bias=8)
    return source_slot, hpos_add, target


def shot_impact_spawn(state: GameState, target: int, shooter: int) -> None:
    """0x47DAE -- spawn a sparkle explosion for a MOB or tagged tile hit.

    The first free slot in 0x0D-0x10 wins. With a full pool, the shooter selects
    a fallback channel, but an active transporter dissolve in that channel is
    preserved rather than overwritten. Tagged playfield hits position the effect
    from the live projectile; their normalized cell is only the depth-list key.
    """
    effect_slot = _claim_effect_slot(
        state, shooter, preserve_tport=True,
    )
    if effect_slot is None:
        return
    picture = (
        _PLAYER_IMPACT_PICTURE if shooter < 8 else _MONSTER_IMPACT_PICTURE
    )
    source_slot, hpos_add, depth_key = _impact_geometry(state, target, shooter)
    _place_effect(
        state, effect_slot, source_slot, picture, 9, 0,
        hpos_add=hpos_add, depth_key=depth_key,
    )


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
