"""The camera -- WP-13.

Reference: ``doc/04_game_subsystems.md`` §17; ``book/03_four_players.md``.
"""

from __future__ import annotations

from ..constants import GameMode
from ..coords import POS_SHIFT, WORLD_PIXELS
from ..state import GameState


#: The camera writes the ROM's hardware scroll registers. The party extent is
#: taken in MOB coordinates, whose V pixels count up from the playfield floor;
#: the vertical target is ``0x1E8 - midV - 0x6C``.
CAM_X_SHIFT = 0x68              # 104: midX = scroll_x + CAM_X_SHIFT

# ``scroll_set_position`` (0x46F56) has asymmetric, display-geometry-specific
# limits.  They are register limits, not generic 512px world limits.
_SCROLL_X_MIN = 0x005
_SCROLL_X_MAX = 0x124
_SCROLL_Y_MIN = 0x001
_SCROLL_Y_MAX = 0x118


# ROM: part game:0x46CAA | Party extent/wrap/outlier target calculation extracted from main_scroll_playfield; include_camera=False is a Python extension.
def _camera_target(
    state: GameState, *, include_camera: bool = True,
) -> tuple[int, int] | None:
    """The scroll target (hardware-register form) the party wants this frame,
    or ``None`` when there is nothing to track.

    0x46CDE-0x46EF8 work in MOB coordinates: H pixels, and V pixels that grow
    up the screen. The extent starts at the current camera centre, so the
    camera approaches the party at half rate. Each player then contributes in
    two passes:

    * 0x46D2A: while ``player_tport_phase`` is not negative, the cell in
      ``player_tile_or_tport_dest`` -- the transporter destination -- widens
      the extent directly;
    * 0x46DC6: the live MOB position widens it subject to the 0x140 rubber
      band, which pulls an outlier 0xC8 pixels back toward the party.

    The midpoint is averaged before the V axis is inverted (0x46EE8), which
    fixes the rounding of an odd extent.
    """
    left = state.scroll_x - 0x98                     # 0x46CDE
    v_top = 0x27C - state.scroll_y                   # 0x46CEE
    if include_camera:
        min_x = max_x = state.scroll_x + CAM_X_SHIFT    # 0x46D0A
        min_v = max_v = 0x17C - state.scroll_y          # 0x46D16
    else:
        min_x = max_x = min_v = max_v = None
    tracked = False

    # ROM: part game:0x46CAA | Shared one-maze wrap fold of each extent point against the window at 0x46D84-0x46DAC/0x46E16-0x46E3E.
    def fold(x: int, v: int) -> tuple[int, int]:
        if include_camera or state.wrap_h:
            if x < left:
                x += WORLD_PIXELS
            elif x >= left + WORLD_PIXELS:
                x -= WORLD_PIXELS
        if include_camera or state.wrap_v:
            if v < v_top - WORLD_PIXELS:
                v += WORLD_PIXELS
            elif v >= v_top:
                v -= WORLD_PIXELS
        return x, v

    for i, player in enumerate(state.players):
        slot = player.mob_slot
        if not slot:
            continue
        tracked = True

        if state.player_tport_phase[i] >= 0:         # 0x46D36
            cell = state.player_tile_or_tport_dest[i]
            x, v = fold(((cell & 0x1F) << 4) - 4,
                        ((cell & 0x3E0) ^ 0x3E0) >> 1)
            if min_x is None:
                min_x = max_x = x
                min_v = max_v = v
            else:
                max_x = max(max_x, x)
                max_v = max(max_v, v)
                min_x = min(min_x, x)
                min_v = min(min_v, v)

        x, v = fold((state.mobs.hpos[slot] & 0xFFFF) >> POS_SHIFT,
                    (state.mobs.vpos[slot] & 0xFFFF) >> POS_SHIFT)
        if min_x is None:
            min_x = max_x = x
            min_v = max_v = v
            continue
        if x > max_x:                                # 0x46E40
            if x - min_x > 0x140:
                x -= 0xC8
            else:
                max_x = x
        if v > max_v:                                # 0x46E5E
            if v - min_v > 0x140:
                v -= 0xC8
            else:
                max_v = v
        if x < min_x:                                # 0x46E7C
            if max_x - x > 0x140:
                x += 0xC8
                max_x = max(max_x, x)
            else:
                min_x = x
        if v < min_v:                                # 0x46EA0
            if max_v - v > 0x140:
                v += 0xC8
                max_v = max(max_v, v)
            else:
                min_v = v

    if not tracked:
        return None
    assert min_x is not None and max_x is not None
    assert min_v is not None and max_v is not None

    target_x = ((min_x + max_x) >> 1) - CAM_X_SHIFT           # 0x46ED2/0x46EFC
    target_y = 0x1E8 - ((min_v + max_v) >> 1) - 0x6C          # 0x46EE0-0x46F1A
    return target_x, target_y


# ROM: direct game:0x46CAA | Shared camera update boundary with extracted target calculation and delegated scroll clamp.
def main_scroll_playfield(state: GameState) -> None:
    """0x46CAA -- move the shared camera toward the party.

    Bounding extent of the active players (honouring wraparound), the 0x140
    outlier threshold so one adventurous player cannot yank the camera away from
    three cooperating ones, a target at the midpoint offset so the maze
    viewport centres rather than the full screen, 2 px per axis per frame with
    a snap when close, then ``scroll_set_position`` clamps.
    """
    # Guard: only runs during GAMEMODE_NORMAL or GAMEMODE_DEMO (§17).
    if state.game_mode not in (GameMode.NORMAL, GameMode.DEMO):
        return
    if state.level_players_active <= 0:
        return

    # ``player_tport_phase`` / ``player_tile_or_tport_dest`` (0x904BCE /
    # 0x904BD8) are maintained by ``main_move_players`` (WP-5/6), which runs
    # earlier in the frame; the camera only reads them here (§17).
    target = _camera_target(state)
    if target is None:
        return
    target_x, target_y = target

    # --- Step 3: smooth scroll toward target (2 px per frame, snap when close) ---
    # §17: if |delta| >= 3 step by 2; otherwise snap.
    delta_x = target_x - state.scroll_x
    if delta_x >= 3:
        state.scroll_x += 2
    elif delta_x <= -3:
        state.scroll_x -= 2
    else:
        state.scroll_x = target_x

    delta_y = target_y - state.scroll_y
    if delta_y >= 3:
        state.scroll_y += 2
    elif delta_y <= -3:
        state.scroll_y -= 2
    else:
        state.scroll_y = target_y

    # --- Step 4: clamp to legal scroll range ---
    set_scroll_pos(state)


# ROM: helper | Python level-start framing policy reusing the ROM-derived target without smoothing; no separate ROM snap-camera callable identified.
def snap_camera(state: GameState) -> None:
    """Jump the camera straight to its target, no smoothing -- for framing the
    party immediately at level start (so the view does not pan in from 0,0).
    Writes the same hardware-register scroll the smoothed path converges to.
    """
    target = _camera_target(state, include_camera=False)
    if target is None:
        return
    state.scroll_x, state.scroll_y = target
    set_scroll_pos(state)


# ROM: direct game:0x46C5E | Packed-maze-cell camera centering boundary followed by the shared clamp.
def scroll_to_slot(state: GameState, packed_slot: int) -> None:
    """0x46C5E -- center the hardware scroll on one packed maze cell."""
    packed_slot &= 0x03FF
    row_bits = packed_slot & 0x03E0
    state.scroll_y = 0x01E8 - ((row_bits ^ 0x03E0) >> 1) - 0x6C
    state.scroll_x = ((packed_slot & 0x1F) << 4) - 4 - CAM_X_SHIFT
    set_scroll_pos(state)


# ROM: direct game:0x46F56 | Scroll clamp/mask boundary; Python reads and writes state fields instead of receiving two register-value arguments.
def set_scroll_pos(state: GameState) -> None:
    """0x46F56 -- clamp scroll registers to the legal playfield range.

    When a wrap flag is clear the axis is bounded.  When set, the scroll
    register may wrap freely (hardware handles it).  §17.
    """
    if not state.wrap_h:
        state.scroll_x = max(_SCROLL_X_MIN, min(state.scroll_x, _SCROLL_X_MAX))
    if not state.wrap_v:
        state.scroll_y = max(_SCROLL_Y_MIN, min(state.scroll_y, _SCROLL_Y_MAX))

    # The ROM masks both signed input words down to their 9-bit register form
    # after clamping (or directly on wrapped axes).
    state.scroll_x &= 0x1FF
    state.scroll_y &= 0x1FF


# ROM: infrastructure | Host-renderer interpretation of modeled scroll registers, with compatibility viewport arguments ignored.
def viewport_scroll(state: GameState, viewport_w: int, viewport_h: int) -> tuple[int, int]:
    """Return the world origin represented by the hardware scroll registers.

    MAME 0.289 pixel comparison pins the visible playfield directly to
    ``pf_hscroll``. The older host-side ``-8`` conversion shifted the whole maze
    five pixels too far right at the ROM's left clamp.
    """
    del viewport_w, viewport_h
    return state.scroll_x & 0x1FF, state.scroll_y & 0x1FF
