"""Camera-bounded monster/generator traversal and shared monster dispatch.

Movement, shooting, spawning, contact, and MOB-state operations live in their
own modules. Public routine aliases below preserve the existing entry points
without wrapper calls.

Reference: ``doc/04_game_subsystems.md`` §3 (all of it);
``doc/generated/monster_combat_contracts.csv``; ``book/04_the_horde.md``.

Traversal and dispatch invariants:

- ``main_move_monsters`` selects a camera-bounded arc between two SLIP bucket
  heads. ``monsters_everything`` walks from the near head, wrapping as needed,
  until the next entry reaches ``monster_iter_ptr`` (0x904A60), the far-edge
  marker. It does not process the entire depth chain every frame.
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

Movement model. The original moves a monster by relocating its
record to a new cell (``move_mob_slot`` -- "identity is location"), tracking a
pixel position inside ``mob_hpos``/``mob_vpos``. The monster mover keeps that dual
representation: each axis component of the heading is probed with a ray march
(0x5E10C and friends), the components that
came back clear are kept -- which is what makes a diagonal walker slide along a
wall -- and the record is relocated when the resulting position lands in a new
cell. The animation counter in the state word's top three bits drives the
whole thing: creatures hold a pose for eight gated frames, and the *wrap* is
what releases the next step, shot or blink.  A generated creature is created
with the exact walk frame its heading names (``monster_anim_walk_tbl``, 0x40DB2),
so it has real artwork from the frame it appears. The game selects later
animation frames through ``monster_update_anim_tile`` and owns the live MOB
picture and palette/tier words; the renderer consumes those words.
"""

from __future__ import annotations

from ..constants import (
    GENERATOR_TYPES,
    MONSTER_TYPES,
    MazeObjIds,
)
from ..coords import POS_SHIFT
from ..state import GameState
from .sound import sound_play as _sound_play


# Internal dependencies come directly from their implementation owners.
from .monster_data import (
    _HPOS_FLAG_ATTACK,
    _HPOS_FLAG_MOVING,
    _MONSTER_ODDANGLE_TABLE,
)
from .monster_movement import _monster_move_engine
from .monster_spawning import _handle_generator, _supersorc_dispatch
from .monster_state import (
    _anim_add_high,
    _anim_advance,
    _monster_index,
    _set_direction,
)

# Limited compatibility exports: public routines and the generator retry value.
from .score import player_add_score_with_mult as player_add_score_with_mult
from .monster_contact import (
    monster_playerhit as monster_playerhit,
    player_hurt_speech_timer as player_hurt_speech_timer,
)
from .monster_movement import (
    apply_direction_from_delta as apply_direction_from_delta,
)
from .monster_shooting import (
    find_unused_shot as find_unused_shot,
    monster_create_shot as monster_create_shot,
    monster_find_and_shoot as monster_find_and_shoot,
    monster_shooter_in_view as monster_shooter_in_view,
)
from .monster_spawning import (
    GENERATOR_RETRY_RELOAD as GENERATOR_RETRY_RELOAD,
    generator_candidate_slot as generator_candidate_slot,
    handle_generate as handle_generate,
    monster_walk_picture as monster_walk_picture,
    supersorc_place as supersorc_place,
    tile_occupancy_test as tile_occupancy_test,
    tile_on_screen_d4 as tile_on_screen_d4,
)
from .monster_state import monster_update_anim_tile as monster_update_anim_tile

# Slow-motion looping-sound cues (§3.3, refs/soundcmds.csv).  The ROM plays
# 0x38 as the timer passes 0x1E and 0x39 as it reaches 0 (0x40EC0/0x40ED2);
# refs/soundcmds.csv labels 0x38 "End of Slow Motion" and 0x39 "Slow Motion
# Silencer", i.e. the *names* in the CSV are the other way round.  Behaviour
# below follows the ROM.
_SOUND_SLOWMO_SILENCER = 0x38   # fires as the timer passes 0x1E
_SOUND_SLOWMO_END = 0x39        # fires as the timer reaches 0

# Acid acts once every 32 frames: (frame_word & 0x1E) == 0 (0x413E6).
_ACID_RATE_MASK = 0x1E

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


def _update_cull_rect(state: GameState) -> None:
    """0x49052-0x49076 -- re-anchor the culling rectangle on the camera."""
    state.monster_cull_h_origin = ((state.scroll_x - _CULL_H_BIAS) << POS_SHIFT) & 0xFFFF
    state.monster_cull_v_origin = ((_CULL_V_BIAS - state.scroll_y) << POS_SHIFT) & 0xFFFF


def _in_cull_rect(state: GameState, slot: int) -> bool:
    """0x40FF6-0x4101A -- whether a creature is processed at all this frame."""
    if ((state.mobs.hpos[slot] - state.monster_cull_h_origin) & 0xFFFF) >= _CULL_WIDTH:
        return False
    return ((state.mobs.vpos[slot] - state.monster_cull_v_origin) & 0xFFFF) < _CULL_HEIGHT


# =============================================================================
# Top-level main-loop call
# =============================================================================

def main_move_monsters(state: GameState) -> None:
    """0x49034 -- advance monsters and generators in the camera-bounded arc.

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
