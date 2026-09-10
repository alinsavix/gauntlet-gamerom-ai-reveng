"""Projectile hit dispatch, victim-specific damage, and shared award calls."""

from __future__ import annotations

from ..constants import MazeObjIds
from ..state import GameState
from ..playfield import pf_replace as pf_replace
from .shot_data import (
    CONSUMED as CONSUMED,
)

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
_SOUND_SECRET_WALL = 0x30
_SOUND_SLOWMO = 0x37
_SOUND_POTION_BREAK = 0x1D

# Slow-motion trigger pictures (identified by picture, not by type).  §26.
_PIC_SLOWMO_FOOD = 0x25ED
_PIC_SLOWMO_POTION = 0x20FC
_SLOWMO_FOOD_FRAMES = 0x258
_SLOWMO_POTION_FRAMES = 0x4B0

# Doors only react to a shot inside this box (0x4B416 passes 0x2C0 twice).
_DOOR_LIMIT = 0x02C0

# Secret-wall prize roll (0x4B56A-0x4B5D2).
_PRIZE_HIDDENPOT_BASE = 0xA728
_GAME_MODE_SECRET = -3           # 0xFFFD, the secret-room game mode


def _hurt_latch(state: GameState, victim_index: int) -> None:
    """``ori.b #2, player_redraw[victim]`` -- WP-14's ``health_dirty`` latch.

    The ROM raises it at 0x4B102/0x4B152 (player-versus-player) and 0x4B282
    (monster shot); the stun-only path deliberately does not, because it
    changes no health.
    """
    state.health_dirty[victim_index] = 1


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


def death_damage_accumulate(state: GameState, player_index: int,
                            death_slot: int, damage: int) -> None:
    """0x49A3C -- add damage to per-player Death-damage counter; dismiss when > 200.

    §3.6 / §26: supershot adds 25; monster/player Death *contact* adds 4 (or 3
    with the armor power, called from ``monster_playerhit``).  Ordinary player
    shots do NOT call this -- they only increment death_hits.  The counter
    belongs to the player and persists across multiple Death MOBs within a
    level; player_start_inner resets it on join/transition.
    """
    from .shots import (
        tport_cycle_start as tport_cycle_start,
    )

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
    from .shots import (
        _shot_tier as _shot_tier,
    )

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
    from .shots import (
        _shot_slot as _shot_slot,
    )

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
    from .shots import (
        _is_maxtier as _is_maxtier,
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        _sound as _sound,
        dragon_player_proximity as dragon_player_proximity,
    )

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
    from .shots import (
        _sound as _sound,
    )

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
    from .shots import (
        _u16 as _u16,
    )

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
    from .shots import (
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        dragon_player_proximity as dragon_player_proximity,
    )
    from .score import player_add_score_with_mult

    if shooter_id >= 4:
        return _finish(state, slot, shooter_id)

    dragon_player_proximity(state, slot)
    # 0x4BD7E: MULS.W prepares the base; 0x52158 consumes its low word.
    player_add_score_with_mult(state, shooter_id, damage * multiplier)
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
    from .shots import (
        playfield_showscore as playfield_showscore,
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        _u16 as _u16,
    )

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
    from .shots import (
        _u16 as _u16,
    )

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
    from .shots import (
        _u16 as _u16,
    )

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
    from .shots import (
        _u16 as _u16,
        tport_cycle_start as tport_cycle_start,
    )

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
    from .shot_collision import (
        shot_reflect_calc as shot_reflect_calc,
    )
    from .shots import (
        _is_maxtier as _is_maxtier,
        shot_impact_spawn as shot_impact_spawn,
    )

    if shooter_id < 4 and (state.players[shooter_id].powers & _POWER_REFLECT):
        state.shot_direction[shooter_id] = shot_reflect_calc(
            state, raw_target, shooter_id,
        )
        if state.reflect_count[shooter_id] != 0:
            return SURVIVES

    shot_impact_spawn(state, raw_target, shooter_id)
    if _is_maxtier(state, shooter_id):
        return SURVIVES     # 0x4B51E: max-tier shots bore through walls
    return _consume(state, shooter_id)


def _handle_secret_wall(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B528 -- reveal the wall, roll a prize, credit the trick."""
    from .shots import (
        _sound as _sound,
        _spawn_maze_object as _spawn_maze_object,
        _u16 as _u16,
        dragon_player_proximity as dragon_player_proximity,
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        dragon_player_proximity as dragon_player_proximity,
        shot_impact_spawn as shot_impact_spawn,
        wall_crumble as wall_crumble,
    )

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
    from .shots import (
        _is_maxtier as _is_maxtier,
    )

    if _is_maxtier(state, shooter_id):
        return SURVIVES
    return _consume(state, shooter_id)


def _handle_door(state: GameState, slot: int, shooter_id: int) -> int:
    """0x4B416 -- doors only notice a shot inside the 0x2C0 box."""
    from .shot_collision import (
        shot_onscreen_check as shot_onscreen_check,
    )
    from .shots import (
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        _u16 as _u16,
        dragon_player_proximity as dragon_player_proximity,
    )

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
    from .shots import (
        dragon_player_proximity as dragon_player_proximity,
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        _sound as _sound,
        _speech as _speech,
        dragon_player_proximity as dragon_player_proximity,
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        _potion_blast as _potion_blast,
        _sound as _sound,
        _speech as _speech,
        _u16 as _u16,
        dragon_player_proximity as dragon_player_proximity,
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        dragon_player_proximity as dragon_player_proximity,
        shot_impact_spawn as shot_impact_spawn,
    )

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
    from .shots import (
        _u16 as _u16,
    )

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
