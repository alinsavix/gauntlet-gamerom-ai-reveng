"""Public MOB probe family (0x406B6-0x408A0), distinct from private player probes."""

from __future__ import annotations

from ..coords import POS_SHIFT, native_v
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


# ROM: helper | Python deferral of pass-through objects that ordinary movement resolves after the probe.
def _probe_candidate_deferred(
    state: GameState, mover_slot: int, candidate: int, *,
    self_slot: int | None,
) -> bool:
    """Whether an overlapping candidate lets ordinary movement through.

    The ROM's probe reports any overlapping record; ``mob_collision_test``
    then passes the hero through pickups and similar objects, which the cell
    tail interacts with after the move. This predicate is that pass result.
    """
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
# Each probe checks three candidates: the cell in the target direction plus
# its two flanking neighbours (§4.2), and returns the first one whose record
# overlaps the mover, whatever it is. Callers decide what that record means.
# Flank columns always wrap within their row (``andi.w #$3E``); flank rows are
# skipped at the top (slot < 0x40) and bottom (slot >= 0x3E0) instead.

# ROM: helper | Ordered first-overlap walk shared by the four public probes (the bcs exits after each bsr 0x407A6).
def _first_public_overlap(
    state: GameState, mob_slot: int, candidates: list[int], *,
    hpos: int | None, vpos: int | None, self_slot: int | None,
) -> int:
    for candidate in candidates:
        if _probe_candidate_overlaps(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot,
        ):
            return candidate
    return -1


# ROM: helper | Candidate order of the column-major probes 0x406B6/0x40732: target, column-1, column+1, each wrapped in the row.
def _row_triplet(row: int, col: int) -> list[int]:
    return [(row << 5) | ((col + dc) & 0x1F) for dc in (0, -1, 1)]


# ROM: helper | Candidate order of the row-major probes 0x4083A/0x408A0: target row, row above when slot >= 0x40, row below when slot < 0x3E0.
def _column_triplet(mob_slot: int, col: int) -> list[int]:
    row = mob_slot >> 5
    rows = [row]
    if mob_slot >= 0x40:                       # 0x4086E / 0x408D4
        rows.append(row - 1)
    if mob_slot < 0x3E0:                       # 0x40880 / 0x408E6
        rows.append(row + 1)
    return [(r << 5) | (col & 0x1F) for r in rows]


# ROM: direct game:0x406B6 | Public three-candidate upward probe boundary, including its vertical sentinel; distinct from private probe_up.
def mob_probe_up(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
) -> int:
    """0x406B6 -- the first record overlapping the mover from the row above.

    Returns that slot, -1 when nothing overlaps, or 0x0400 when the live V
    word of a mover in the top two slot rows is above the top boundary.
    Callers must not treat every non-negative return as a valid slot.
    """
    if mob_slot < 0x40:                                    # 0x406C2
        live_vpos = state.mobs.vpos[mob_slot] if vpos is None else vpos
        if (live_vpos & 0xFFFF) > _TOP_PLAYER_BOUNDARY_V:  # 0x406C8
            return _VERTICAL_BOUNDARY
        return -1
    return _first_public_overlap(
        state, mob_slot, _row_triplet((mob_slot >> 5) - 1, mob_slot & 0x1F),
        hpos=hpos, vpos=vpos, self_slot=self_slot,
    )


# ROM: direct game:0x40732 | Public three-candidate downward probe boundary, including its vertical sentinel; distinct from private probe_down.
def mob_probe_down(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
) -> int:
    """0x40732 -- the first record overlapping the mover from the row below.

    Returns that slot, -1, or 0x0400 when a row-31 mover's live V word is
    negative.
    """
    if mob_slot >= 0x3E0:                                  # 0x4073E
        live_vpos = state.mobs.vpos[mob_slot] if vpos is None else vpos
        return _VERTICAL_BOUNDARY if live_vpos & 0x8000 else -1
    return _first_public_overlap(
        state, mob_slot, _row_triplet((mob_slot >> 5) + 1, mob_slot & 0x1F),
        hpos=hpos, vpos=vpos, self_slot=self_slot,
    )


# ROM: direct game:0x4083A | Public left-and-flanks probe boundary.
def mob_probe_left(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
) -> int:
    """0x4083A -- the first record overlapping the mover from the column to
    the left (wrapped within the row), then its upper and lower flanks.

    Left/right probes have no boundary sentinel.
    """
    return _first_public_overlap(
        state, mob_slot, _column_triplet(mob_slot, (mob_slot & 0x1F) - 1),
        hpos=hpos, vpos=vpos, self_slot=self_slot,
    )


# ROM: direct game:0x408A0 | Public right-and-flanks probe boundary.
def mob_probe_right(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
) -> int:
    """0x408A0 -- the first record overlapping the mover from the column to
    the right (wrapped within the row), then its upper and lower flanks."""
    return _first_public_overlap(
        state, mob_slot, _column_triplet(mob_slot, (mob_slot & 0x1F) + 1),
        hpos=hpos, vpos=vpos, self_slot=self_slot,
    )
