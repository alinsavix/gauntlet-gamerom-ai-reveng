"""Potions and magic -- WP-12.

The ``potion_effect_matrix`` (0x5DA98) is 28 records x 16 bytes for object types
0x12-0x2D, indexed ``(object_type << 4) + character + trigger_flags``, where bit
2 marks a shot-triggered potion and bit 3 the Magic-power variant.

**A zero entry destroys the target outright.** There is no "no effect" encoding
for monsters at all -- read the 0x5DA98 entry in the data reference in full
before implementing.

Reference: ``doc/05_data_reference.md`` (0x5DA98); ``doc/04_game_subsystems.md``
§4.6.

The 448-byte matrix is transcribed from ROM 0x5DA98 (``_POTION_EFFECT_MATRIX_ROM``
below). Its per-character damage values are nuanced: e.g. a Warrior drink does
2 to a Ghost (which survives as a weaker tier), while a Wizard or Elf drink,
and any Magic-power potion, destroy it outright. The documented invariants
hold in the data -- Death/Acid/Super-Sorcerer rows are all-zero (any potion
kills them), the Wizard column is zero everywhere, and the Elf column is zero
for monster rows.
"""

from __future__ import annotations

from ..constants import GameMode, MazeObjIds
from ..state import GameState
from .display import ALPHA_PALETTE_INIT
from .monsters import (
    _ANIM_ACID_IDLE,
    _HPOS_FLAG_ATTACK,
    _HPOS_FLAG_MOVING,
    _in_cull_rect,
    _refresh_monster_picture,
    _update_cull_rect,
)
from .sound import sound_play as _sound_play


# =============================================================================
# Constants
# =============================================================================

# Magic-press edge: the same (reg & 0x1F) == 0x1C pattern main_start_game
# matches, tested for potions at 0x47020 (§ potions docstring, §6.4).
_MAGIC_EDGE_MASK = 0x1F
_MAGIC_EDGE_VALUE = 0x1C

# Potion-use and unavailable-maze sounds, from 0x470A8 / 0x4705C.
_SOUND_POTION = 0x1D
_SOUND_POTION_UNAVAILABLE = 0x44
_SOUND_DRAGON_POTION = 0xD5

# ``dialog_first_encounter`` masks pushed at 0x470C0 / 0x4712A.  The latter is
# record 4 ("COLLECT MAGIC POTION BEFORE PRESSING MAGIC"); the former records a
# successful potion use in the full 32-record dialog bitset.
_DIALOG_POTION_BEFORE_MAGIC = 0x00000010
_DIALOG_POTION_USED = 0x00080000

# Magic power is player_powers' low-byte bit 5 (ROM 0x4159C / 0x498F2).
_POWER_MAGIC = 0x0020

# Matrix covers object types 0x12..0x2D (§data ref 0x5DA98).
_MATRIX_FIRST_TYPE = 0x12
_MATRIX_LAST_TYPE = 0x2D

# IT (0x1B) is filtered out before the lookup -- its row is unreachable filler.
_IT_TYPE = int(MazeObjIds.MONST_IT)   # 0x1B / 27

# Object-class split tested at 0x41670: generators are type >= 0x1C.
_GENERATOR_SPLIT = 0x1C

# 0x579D2 / 0x579E2, indexed by death_hits & 7.
_DEATH_POTION_SCORE = (1000, 4000, 2000, 6000, 1000, 8000, 1000, 2000)
_DEATH_POTION_POPUP = (2, 5, 3, 7, 2, 9, 2, 3)

# The blast is not global.  0x41560-0x41584 subtracts the two camera-derived
# monster culling origins from the target's H/V words and rejects it with an
# *unsigned* compare against 0x7F80 / 0x8380 -- the same screen-sized box
# ``monsters._in_cull_rect`` already implements in the same native words.
# In the ROM the potion pass is a branch *instead of* the ordinary body of
# ``monsters_everything`` (0x40EA6 -> 0x41532), reached from
# ``main_move_monsters`` (0x49034) right after it recomputes those origins at
# 0x49052-0x49072. Gauntpy uses the same alternate pass; direct test callers
# also re-anchor here.

# Per-type tier bases from ``mazeobj_hsize_tier_tbl`` (0x5864C), used to decide
# whether tier-nibble damage kills a monster (§26 / §4.6).
_TIER_BASE = {
    int(MazeObjIds.MONST_GHOST): 4,
    int(MazeObjIds.MONST_GRUNT): 4,
    int(MazeObjIds.MONST_AUX_GRUNT): 4,
    int(MazeObjIds.MONST_DEMON): 8,
    int(MazeObjIds.MONST_LOBBER): 0xB,
    int(MazeObjIds.MONST_SORC): 0xB,
}

# ``mazeobj_base_picture_tbl`` at 0x5868C, entries 0x1C--0x2D.  A nonzero
# generator matrix entry replaces both its type and its exact base picture.
_GENERATOR_BASE_PICTURES = (
    0x09AB, 0x09B4, 0x09BD,
    0x09C6, 0x09CF, 0x09D8,
    0x09C6, 0x09CF, 0x09D8,
    0x09C6, 0x09CF, 0x09D8,
    0x09C6, 0x09CF, 0x09D8,
    0x09C6, 0x09CF, 0x09D8,
)


# ``potion_effect_matrix`` -- transcribed from ROM 0x5DA98 (row76.bin offset
# 0x1DA98), 28 records × 16 bytes for object types 0x12-0x2D.  Each record is
# indexed by ``character + trigger_flags`` (cols 0-3 drink, 4-7 shot-triggered,
# 8-11 Magic-power, 12-15 shot+Magic-power).  A zero entry destroys the target;
# for monsters a non-zero entry is tier-nibble damage (so a Warrior potion does
# 2 to a Ghost, which survives), for generators it replaces the type field.
# The data confirms the documented invariants: Death/Acid/Super-Sorcerer rows
# (0x18-0x1A) are all-zero, IT (0x1B) is an unreachable all-0x1B filler row, the
# Wizard column is zero everywhere, and the Elf column is zero for monster rows.
_POTION_EFFECT_MATRIX_ROM: dict[int, list[int]] = {
    0x12: [2, 2, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_GHOST
    0x13: [2, 0, 0, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_GRUNT
    0x14: [2, 0, 0, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_DEMON
    0x15: [2, 0, 0, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_LOBBER
    0x16: [2, 0, 0, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_SORC
    0x17: [2, 0, 0, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_AUX_GRUNT
    0x18: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_DEATH
    0x19: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_ACID
    0x1A: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # MONST_SUPERSORC
    0x1B: [27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27],  # IT filler
    0x1C: [28, 28, 0, 0, 28, 28, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # GEN_GHOST1
    0x1D: [29, 29, 0, 0, 29, 29, 0, 28, 28, 28, 0, 0, 28, 28, 0, 0],  # GEN_GHOST2
    0x1E: [30, 30, 0, 28, 30, 30, 28, 29, 29, 29, 0, 0, 29, 29, 0, 28],  # GEN_GHOST3
    0x1F: [31, 0, 0, 0, 31, 31, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # GEN_GRUNT1
    0x20: [32, 31, 0, 0, 32, 32, 0, 31, 31, 0, 0, 0, 31, 31, 0, 0],  # GEN_GRUNT2
    0x21: [33, 32, 0, 31, 33, 33, 31, 32, 32, 31, 0, 0, 32, 32, 0, 31],  # GEN_GRUNT3
    0x22: [34, 0, 0, 0, 34, 34, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # GEN_DEMON1
    0x23: [35, 34, 0, 0, 35, 35, 0, 34, 34, 0, 0, 0, 34, 34, 0, 0],  # GEN_DEMON2
    0x24: [36, 35, 0, 34, 36, 36, 34, 35, 35, 34, 0, 0, 35, 35, 0, 34],  # GEN_DEMON3
    0x25: [37, 0, 0, 0, 37, 37, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # GEN_LOBBER1
    0x26: [38, 37, 0, 0, 38, 38, 0, 37, 37, 0, 0, 0, 37, 37, 0, 0],  # GEN_LOBBER2
    0x27: [39, 38, 0, 37, 39, 39, 37, 38, 38, 37, 0, 0, 38, 38, 0, 37],  # GEN_LOBBER3
    0x28: [40, 0, 0, 0, 40, 40, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # GEN_SORC1
    0x29: [41, 40, 0, 0, 41, 41, 0, 40, 40, 0, 0, 0, 40, 40, 0, 0],  # GEN_SORC2
    0x2A: [42, 41, 0, 40, 42, 42, 40, 41, 41, 40, 0, 0, 41, 41, 0, 40],  # GEN_SORC3
    0x2B: [43, 0, 0, 0, 43, 43, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],   # GEN_AUX_GRUNT1
    0x2C: [44, 43, 0, 0, 44, 44, 0, 43, 43, 0, 0, 0, 43, 43, 0, 0],  # GEN_AUX_GRUNT2
    0x2D: [45, 44, 0, 43, 45, 45, 43, 44, 44, 43, 0, 0, 44, 44, 0, 43],  # GEN_AUX_GRUNT3
}

# =============================================================================
# Top-level main-loop call
# =============================================================================

def main_handle_potions(state: GameState) -> None:
    """0x46FEA -- potion use and blast resolution.

    Gated on the debounced Magic press (the ``== 0x1C`` pattern) for any active
    player carrying a potion.  A press consumes one potion and triggers the
    screen-clearing blast.
    """
    for p in state.players:
        if not p.active:
            continue
        if not _magic_press_edge(state, p.index):
            continue
        if state.mazenum_current >= 0x73:
            _sound_play(state, _SOUND_POTION_UNAVAILABLE)
            continue
        if p.potionsnum <= 0:
            _dialog_first_encounter(
                state, p.index, _DIALOG_POTION_BEFORE_MAGIC
            )
            _sound_play(state, _SOUND_POTION_UNAVAILABLE)
            continue

        # 0x4707E stores the bare player index before inventory, dialog, and
        # effect handling; potion_blast will retain that provenance while it
        # adds its per-target Magic-power selector.
        state.potion_player = p.index
        # 0x47084-0x47098 selects color 3 of the triggering player's alpha
        # palette. VBLANK copies this latch into playfield color 0/8.
        state.playfield_color_latch = ALPHA_PALETTE_INIT[p.index * 4 + 7]
        p.potionsnum -= 1
        _sound_play(state, _SOUND_POTION)
        from .players import player_inv_update

        player_inv_update(state, p.index)                 # 0x470BA
        _dialog_first_encounter(state, p.index, _DIALOG_POTION_USED)
        _apply_dragon_potion(state)


def _dialog_first_encounter(
    state: GameState, player_index: int, encounter_mask: int
) -> int:
    """Use WP-14's dialog owner without creating an import-time dependency."""
    from .score import dialog_first_encounter

    return dialog_first_encounter(state, player_index, encounter_mask)


def _magic_press_edge(state: GameState, player_index: int) -> bool:
    if state.game_mode != GameMode.NORMAL:
        # 0x4702E-0x47048 reads bit 0 directly from the current demo record.
        # The hardware debounce register is only consulted in normal play.
        from .players import demo_record_word

        return not (demo_record_word(state, player_index) & 0x01)
    reg = state.debounce_shift_magic[player_index]
    return (reg & _MAGIC_EDGE_MASK) == _MAGIC_EDGE_VALUE


def _apply_dragon_potion(state: GameState) -> None:
    """0x470D2-0x47128 -- apply the dragon's private potion transition."""
    from .dragon import (
        _ST_STUNNED,
        _ST_WAKING,
        dragon_any_segment_near_screen,
    )

    if not dragon_any_segment_near_screen(state):
        return
    if state.dragon_state & _ST_WAKING:
        if state.dragon_anim_ctr == 0:
            state.dragon_anim_ctr = 0x31
        elif state.dragon_anim_ctr < 0:
            state.dragon_anim_ctr = -state.dragon_anim_ctr
        _sound_play(state, _SOUND_DRAGON_POTION)
        return
    if state.dragon_state & _ST_STUNNED:
        state.dragon_state &= ~_ST_STUNNED
        state.dragon_state |= _ST_WAKING
        state.dragon_anim_ctr = -0x31
        return
    state.dragon_state |= _ST_STUNNED


# =============================================================================
# Blast resolution (the 0x4153E-0x41728 MOB scan)
# =============================================================================

def potion_blast(state: GameState, player_index: int, *,
                 shot_triggered: bool = False) -> None:
    """Scan every on-screen monster/generator MOB and apply the effect (§4.6).

    ``shot_triggered`` sets bit 2 of the trigger flags for a potion detonated
    by a shot rather than drunk.

    A potion clears the *screen*, not the level: 0x41560-0x41584 culls each
    candidate against the camera-derived monster culling rectangle before the
    matrix lookup, so a generator or creature outside it is left completely
    untouched -- not damaged, not demoted, not destroyed.
    """
    state.potion_player = player_index | (0x04 if shot_triggered else 0)
    character = state.players[player_index].character & 0x03
    magic_powered = bool(state.players[player_index].powers & _POWER_MAGIC)
    trigger = character
    if shot_triggered:
        trigger |= 0x04
    if magic_powered:
        trigger |= 0x08

    _update_cull_rect(state)

    # Snapshot the chain: removal mutates it.
    for slot in list(state.mobs.iter_chain()):
        obj_type = state.mobs.obj_type(slot)
        if obj_type < _MATRIX_FIRST_TYPE or obj_type > _MATRIX_LAST_TYPE:
            continue
        if obj_type == _IT_TYPE:
            continue   # IT is immune -- filtered before the lookup
        if not _in_cull_rect(state, slot):
            continue   # off screen: 0x41570 / 0x41584 skip it entirely
        _apply_potion_effect(
            state, slot, obj_type, trigger, player_index,
        )


def _apply_potion_effect(state: GameState, slot: int, obj_type: int,
                         trigger: int, player_index: int) -> None:
    if obj_type == int(MazeObjIds.MONST_SUPERSORC):
        if state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK:
            state.mobs.state_link[slot] &= 0x1FFF
            state.mobs.hpos[slot] &= ~(_HPOS_FLAG_MOVING | _HPOS_FLAG_ATTACK)
            _refresh_monster_picture(state, slot, obj_type)
            return
    elif obj_type == int(MazeObjIds.MONST_ACID):
        if not state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK:
            state.mobs.picture[slot] = _ANIM_ACID_IDLE[0]
            state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK
            state.mobs.state_link[slot] &= 0x1FFF
            return

    entry = _POTION_EFFECT_MATRIX_ROM[obj_type][trigger & 0x0F]

    if entry == 0:
        if obj_type == int(MazeObjIds.MONST_DEATH):
            from .shots import playfield_showscore

            index = state.death_hits & 7
            playfield_showscore(
                state, slot, _DEATH_POTION_POPUP[index],
            )
            state.players[player_index].score += _DEATH_POTION_SCORE[index]
            state.score_dirty[player_index] = 1
        state.mobs.unlink_and_clear(slot)        # zero destroys outright
        return

    if obj_type >= _GENERATOR_SPLIT:
        # Non-zero byte replaces the generator's type field and base picture.
        state.mobs.set_obj_type(slot, entry & 0x3F)
        state.mobs.picture[slot] = _GENERATOR_BASE_PICTURES[
            entry - _GENERATOR_SPLIT
        ]
        return

    # Monster: subtract from the hpos tier nibble; destroy if it leaves the
    # exact three-value [base-2, base] window.
    hpos = state.mobs.hpos[slot]
    tier = hpos & 0x0F
    base = _TIER_BASE.get(obj_type, 4)
    new_tier = tier - entry
    if not base - 2 <= new_tier <= base:
        state.mobs.unlink_and_clear(slot)
    else:
        state.mobs.hpos[slot] = (hpos & ~0x0F) | (new_tier & 0x0F)
