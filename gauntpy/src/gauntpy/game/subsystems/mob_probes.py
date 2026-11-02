"""Public MOB probe family (0x406B6-0x408A0), distinct from private player probes."""

from __future__ import annotations

from ..coords import POS_SHIFT, hpos_x, native_v, vpos_y
from ..state import GameState
from .player_data import (
    _FIGHT_PASS_TYPES as _FIGHT_PASS_TYPES,
    _MAZE_ROWS as _MAZE_ROWS,
    _POWER_TRANSPORT as _POWER_TRANSPORT,
    _PROBE_OVERLAP as _PROBE_OVERLAP,
    _TOP_PLAYER_BOUNDARY_V as _TOP_PLAYER_BOUNDARY_V,
    _VERTICAL_BOUNDARY as _VERTICAL_BOUNDARY,
)

_MAZE_COLS = 32


# ROM: helper | Python signed-16-bit distance utility shared by collision readers; no independent ROM callable.
def _wrapped_position_delta(a: int, b: int) -> int:
    """Absolute signed distance in the one-maze 16-bit position word space."""
    value = (a - b) & 0xFFFF
    if value & 0x8000:
        value -= 0x10000
    return abs(value)


# ROM: part game:0x407A6,game:0x42648 | Extracts both candidate routines' high-picture-bit H/V rounding arms; the zero-position synthetic-record fallback is Python-only.
def _probe_candidate_anchor(state: GameState, candidate: int) -> tuple[int, int]:
    """Return tile_lookup_core's live/rounded collision anchor."""
    candidate_h = state.mobs.hpos[candidate]
    candidate_v = state.mobs.vpos[candidate]

    if candidate_h == 0 and candidate_v == 0:
        # Synthetic records in isolated tests may omit placement geometry.
        candidate_h = ((candidate & 0x1F) * 16 << POS_SHIFT) & 0xFFFF
        candidate_v = (native_v((candidate >> 5) * 16) << POS_SHIFT) & 0xFFFF

    if state.mobs.picture[candidate] & 0x8000:
        candidate_h = (((candidate_h + 0x280) & 0xF800) - 0x200) & 0xFFFF
        candidate_v = (candidate_v + 0x100) & 0xF800
    return candidate_h, candidate_v


# ROM: merged game:0x407A6,game:0x42648 | Common implementation of public mob_probe_candidate and private tile_lookup_core: optional proposed coordinates replace register inputs; Python self/interaction guards are additional.
def _probe_candidate_blocks(
    state: GameState,
    mover_slot: int,
    candidate: int,
    *,
    hpos: int | None = None,
    vpos: int | None = None,
    self_slot: int | None = None,
    defer_interactions: bool = True,
) -> bool:
    """Position-aware ``mob_probe_candidate`` (0x407A6).

    The directional probes name three possible cells, but a cell blocks only
    when its rendered anchor actually overlaps the player's proposed position.
    Treating every named cell as an immediate collision made a wall one row
    away stop a hero anywhere in the current row.

    ``self_slot`` is the mover's own record. The ROM never needs it -- it
    probes from ``active_mob_ids`` itself, so the record can never be one of
    the three cells ahead -- but this port probes from the cell under the
    hero's feet, and a record hands over to the next row half a cell earlier
    than that (``coords.mob_cell_of`` versus ``_pixel_to_slot``). For those few
    pixels the mover's own migrated record *is* one of the named cells, and a
    hero is not an obstacle to itself.
    """
    from .player_movement import (
        _pixel_to_slot as _pixel_to_slot,
    )

    if not defer_interactions:
        return _probe_candidate_overlaps(
            state, mover_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot,
        )
    return (
        _probe_candidate_overlaps(
            state, mover_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot,
        )
        and not _probe_candidate_deferred(
            state, mover_slot, candidate, self_slot=self_slot,
        )
    )


# ROM: helper | Python deferral of pass-through objects and hero-sharing cells that ordinary movement resolves after the probe.
def _probe_candidate_deferred(
    state: GameState, mover_slot: int, candidate: int, *,
    self_slot: int | None,
) -> bool:
    """Whether an overlapping candidate lets ordinary movement through.

    The ROM's probe reports any overlapping record; ``mob_collision_test``
    then passes the hero through pickups and similar objects, which the cell
    tail interacts with after the move. This predicate is that pass result.
    """
    from .player_movement import (
        _pixel_to_slot as _pixel_to_slot,
    )

    if state.mobs.obj_type(candidate) in _FIGHT_PASS_TYPES:
        transporting = any(
            player.active
            and player.mob_slot == self_slot
            and player.powers & _POWER_TRANSPORT
            for player in state.players
        )
        if not transporting:
            # Ordinary movement resolves these after entering their cell. With
            # transportability, squeeze_through_check runs first and teleports
            # past them instead (0x42744 precedes mob_collision_test).
            return True
    for player in state.players:
        if not player.active or candidate != player.mob_slot:
            continue
        player_x = hpos_x(state.mobs.hpos[player.mob_slot])
        player_y = vpos_y(state.mobs.vpos[player.mob_slot])
        if _pixel_to_slot(player_x, player_y) == mover_slot:
            # Two heroes sharing one cell do not block each other out of it.
            return True
    return False


# ROM: part game:0x407A6,game:0x42648 | Shared nonzero-picture and anchor-overlap test of mob_probe_candidate/tile_lookup_core.
def _probe_candidate_overlaps(
    state: GameState,
    mover_slot: int,
    candidate: int,
    *,
    hpos: int | None = None,
    vpos: int | None = None,
    self_slot: int | None = None,
) -> bool:
    """Whether ``candidate`` holds a record overlapping the mover.

    Like 0x407B6-0x407DE and 0x42656-0x4267C, every examined record leaves
    its signed separations in 0x904028/0x90402A and their magnitudes in
    0x904024/0x904026; the vertical pair is only reached once the horizontal
    magnitude is under 0x7C0. ``shot_onscreen_check`` reads them back for a
    door that ``mob_collision_test`` receives.
    """
    if candidate == mover_slot or state.mobs.picture[candidate] == 0:
        return False
    if candidate == self_slot:
        return False
    mover_h = state.mobs.hpos[mover_slot] if hpos is None else hpos
    mover_v = state.mobs.vpos[mover_slot] if vpos is None else vpos
    candidate_h, candidate_v = _probe_candidate_anchor(state, candidate)

    state.shothit_dist_H = (candidate_h - mover_h) & 0xFFFF
    distance_h = _wrapped_position_delta(candidate_h, mover_h)
    if distance_h >= _PROBE_OVERLAP:
        return False
    state.collision_dist_H = distance_h
    state.shothit_dist_V = (candidate_v - mover_v) & 0xFFFF
    distance_v = _wrapped_position_delta(candidate_v, mover_v)
    state.collision_dist_V = distance_v
    return distance_v < _PROBE_OVERLAP


# ---------------------------------------------------------------------------
# The four directional probes (§4.2, contracts CSV)
# ---------------------------------------------------------------------------
# Each probe checks three candidates: the cell in the target direction,
# plus its two flanking neighbours (§4.2: "exactly three times: the cell
# ahead plus its two flanking neighbours, which covers everything a 24-pixel
# body can overlap while crossing a 16-pixel cell").

# ROM: direct game:0x406B6 | Public three-candidate upward probe boundary, including its vertical sentinel; distinct from private probe_up.
def mob_probe_up(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
    defer_interactions: bool = True,
) -> int:
    """0x406B6 -- probe the cell above for a blocking wall (§4.2).

    Returns the first blocking slot, -1 when clear, or 0x0400 when the proposed
    live V word crosses the top boundary in the top two slot rows.
    Callers must not treat every non-negative return as a valid slot.
    """
    row = mob_slot >> 5
    col = mob_slot & 0x1F
    if row <= 1:
        live_vpos = state.mobs.vpos[mob_slot] if vpos is None else vpos
        if (live_vpos & 0xFFFF) > _TOP_PLAYER_BOUNDARY_V:
            return _VERTICAL_BOUNDARY
        return -1
    target_row = row - 1
    for dc in (0, -1, 1):            # centre, left flank, right flank (§4.2)
        c = col + dc
        if state.wrap_h:
            c &= 0x1F
        elif not (0 <= c < _MAZE_COLS):
            continue
        candidate = (target_row << 5) | c
        if _probe_candidate_blocks(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot, defer_interactions=defer_interactions,
        ):
            return candidate
    return -1


# ROM: direct game:0x40732 | Public three-candidate downward probe boundary, including its vertical sentinel; distinct from private probe_down.
def mob_probe_down(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
    defer_interactions: bool = True,
) -> int:
    """0x40732 -- probe the cell below for a blocking wall (§4.2).

    Returns first blocking slot, -1 when clear, or 0x0400 when a row-31
    proposed live V word becomes negative.
    """
    row = mob_slot >> 5
    col = mob_slot & 0x1F
    if row >= _MAZE_ROWS - 1:
        live_vpos = state.mobs.vpos[mob_slot] if vpos is None else vpos
        return _VERTICAL_BOUNDARY if live_vpos & 0x8000 else -1
    target_row = row + 1
    for dc in (0, -1, 1):
        c = col + dc
        if state.wrap_h:
            c &= 0x1F
        elif not (0 <= c < _MAZE_COLS):
            continue
        candidate = (target_row << 5) | c
        if _probe_candidate_blocks(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot, defer_interactions=defer_interactions,
        ):
            return candidate
    return -1


# ROM: direct game:0x4083A | Public left-and-flanks probe boundary.
def mob_probe_left(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
    defer_interactions: bool = True,
) -> int:
    """0x4083A -- probe the cell to the left for a blocking wall (§4.2).

    Returns first blocking slot or -1.  Left/right probes have no horizontal
    boundary sentinel (only up/down do; §4.2, contracts CSV).
    """
    row = mob_slot >> 5
    col = mob_slot & 0x1F
    if col == 0:
        if not state.wrap_h:
            return -1
        target_col = _MAZE_COLS - 1
    else:
        target_col = col - 1
    flank_rows = [0]
    if row >= 2:                     # 0x4086E: doubled slot >= 0x80
        flank_rows.append(-1)
    if row < _MAZE_ROWS - 1:         # 0x40880: doubled slot < 0x7C0
        flank_rows.append(1)
    for dr in flank_rows:            # centre, optional upper/lower flanks
        r = row + dr
        if state.wrap_v:
            r &= 0x1F
        elif not (0 <= r < _MAZE_ROWS):
            continue
        candidate = (r << 5) | target_col
        if _probe_candidate_blocks(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot, defer_interactions=defer_interactions,
        ):
            return candidate
    return -1


# ROM: direct game:0x408A0 | Public right-and-flanks probe boundary.
def mob_probe_right(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
    defer_interactions: bool = True,
) -> int:
    """0x408A0 -- probe the cell to the right for a blocking wall (§4.2).

    Returns first blocking slot or -1.
    """
    row = mob_slot >> 5
    col = mob_slot & 0x1F
    if col >= _MAZE_COLS - 1:
        if not state.wrap_h:
            return -1
        target_col = 0
    else:
        target_col = col + 1
    flank_rows = [0]
    if row >= 2:                     # 0x408D4: doubled slot >= 0x80
        flank_rows.append(-1)
    if row < _MAZE_ROWS - 1:         # 0x408E6: doubled slot < 0x7C0
        flank_rows.append(1)
    for dr in flank_rows:
        r = row + dr
        if state.wrap_v:
            r &= 0x1F
        elif not (0 <= r < _MAZE_ROWS):
            continue
        candidate = (r << 5) | target_col
        if _probe_candidate_blocks(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot, defer_interactions=defer_interactions,
        ):
            return candidate
    return -1
