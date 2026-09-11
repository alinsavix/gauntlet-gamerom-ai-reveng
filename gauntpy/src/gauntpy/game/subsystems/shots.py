"""Projectile channel ticks and public routine exports -- WP-7.

Shared channel geometry and state live in ``shot_state``; hit effect writers
live in ``shot_effects``. Collision and damage belong to ``shot_collision`` and
``shot_damage``. Public routine reexports below preserve function identity.

Twelve fixed channels: player shots in MOB slots 1-4, ordinary monster shots
5-8, lobbed rocks 9-12.  Fixed slots mean no allocation and no search
-- that is the design, not an optimization to add later.  A channel's
*shooter id* is ``slot - 1``; channel-indexed tables use that id.
The dragon has no channels of its own: ``dragon_find_free_shot_slot``
(0x540E8) hands its fire one of the monster channels 5-8.

Reference: ``doc/04_game_subsystems.md`` §26, §3.6, §23;
``doc/generated/monster_combat_contracts.csv``; ``book/02_one_arrow.md``.
The projectile tables are transcribed from ``row76.bin`` (game address ``A`` at
file offset ``A - 0x40000``, big-endian) and the routines follow the corresponding
disassembly rather than the prose.

**Units.**  The MOB position field is the hardware's own ``pixel << 7``, so
every ROM constant that is added to or compared against a position word --
velocity vectors included -- is used here exactly as the ROM writes it.

**Current port wiring.** ``monster_shooting.monster_create_shot`` and
``dragon.dragon_fire_setup`` seed direction, animation/lifetime counter and
owner; the monster creator also reloads its cadence timer and seeds lobber
accumulators. ``main_handle_shots`` retains its owner/counter/accumulator
fallback for channels armed by hand. Player creation seeds direction too;
``shot_state._live_direction`` recovers it from ``shot_dx/dy`` only when unset.

``shot_effects.wall_crumble`` tracks crumble progress in
``state.destructible_wall_stage`` and writes the resulting descriptor or palette
to playfield VRAM. Rendering reads that VRAM, not the stage dictionary.
"""

from __future__ import annotations

from ..coords import POS_SHIFT, replace_position
from ..state import GameState
from ..playfield import pf_replace as pf_replace
from .score import player_add_score_with_mult as player_add_score_with_mult


# Public compatibility exports; private imports support this module's own tick.
from .shot_collision import (
    shot_collision_candidate_core as shot_collision_candidate_core,
    shot_mob_collision as shot_mob_collision,
    shot_onscreen_check as shot_onscreen_check,
    shot_reflect_calc as shot_reflect_calc,
)
from .shot_damage import (
    SURVIVES as SURVIVES,
    death_damage_accumulate as death_damage_accumulate,
    dragon_player_proximity as dragon_player_proximity,
    resolve_shot_hit as resolve_shot_hit,
)
from .shot_data import CONSUMED as CONSUMED
from .shot_effects import (
    playfield_showscore as playfield_showscore,
    shot_impact_spawn as shot_impact_spawn,
    tport_cycle_start as tport_cycle_start,
    wall_crumble as wall_crumble,
    wall_crumble_descriptor as wall_crumble_descriptor,
    wall_crumble_palette as wall_crumble_palette,
)
from .shot_state import (
    _SHOT_COUNTER_RELOAD,
    _channel_clear,
    _is_maxtier,
    _live_direction,
    _maze_position,
    _s16,
    _shot_cell,
    _shot_slot,
    _u16,
    lobber_accumulator_seed as lobber_accumulator_seed,
    shot_cell as shot_cell,
    shot_picture as shot_picture,
    shot_velocity as shot_velocity,
)

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


def _advance_picture(state: GameState, shooter_id: int, counter: int) -> None:
    """0x47622-0x47716 -- the class-specific projectile animation."""
    state.mobs.picture[_shot_slot(shooter_id)] = shot_picture(
        state, shooter_id, counter
    )


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
