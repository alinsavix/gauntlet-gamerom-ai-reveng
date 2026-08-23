"""The camera -- WP-13.

Reference: ``doc/04_game_subsystems.md`` §17; ``book/08_world_in_memory.md``.
"""

from __future__ import annotations

from ..constants import GameMode
from ..coords import WORLD_PIXELS, hpos_x, vpos_y
from ..state import GameState


#: The camera writes the ROM's hardware scroll registers. MOB V words count up
#: from the playfield floor, so the party extent is taken in ordinary downward
#: screen pixels (``coords.vpos_y``). Applying that conversion to
#: ``0x1E8 - rom_midY - 0x6C`` yields ``world_midY - 0x74``.
#: The renderer's exact world origin is therefore ``(scroll_x - 8, scroll_y)``.
CAM_X_SHIFT = 0x68              # 104: midX = scroll_x + CAM_X_SHIFT
CAM_Y_SHIFT = 0x74              # 116: midY = scroll_y + CAM_Y_SHIFT

# ``scroll_set_position`` (0x46F56) has asymmetric, display-geometry-specific
# limits.  They are register limits, not generic 512px world limits.
_SCROLL_X_MIN = 0x005
_SCROLL_X_MAX = 0x124
_SCROLL_Y_MIN = 0x001
_SCROLL_Y_MAX = 0x118


def _camera_target(
    state: GameState, *, include_camera: bool = True,
) -> tuple[int, int] | None:
    """The scroll target (hardware-register form) the party wants this frame,
    or ``None`` when there is nothing to track. Steps 1-2 of §17 (extent with
    wrap + rubber band, then the offset/inverted target); the smoothing and
    clamp are the caller's.
    """
    # The current camera centre participates in the extent. Besides giving the
    # original's half-rate approach, this is the reference frame that makes
    # seam folding stable when the 9-bit scroll register is near 0/511.
    min_x = max_x = state.scroll_x + CAM_X_SHIFT
    min_y = max_y = state.scroll_y + CAM_Y_SHIFT
    if not include_camera:
        min_x = max_x = None
        min_y = max_y = None
    tracked = False
    window_left = state.scroll_x - 0x98
    window_top = state.scroll_y - 0x8C

    for i, player in enumerate(state.players):
        if state.player_in_maze[i] == 0:
            continue
        tracked = True

        px = hpos_x(state.mobs.hpos[player.mob_slot])
        py = vpos_y(state.mobs.vpos[player.mob_slot])

        if include_camera or state.wrap_h:
            if px < window_left:
                px += WORLD_PIXELS
            elif px >= window_left + WORLD_PIXELS:
                px -= WORLD_PIXELS
        if include_camera or state.wrap_v:
            if py < window_top:
                py += WORLD_PIXELS
            elif py >= window_top + WORLD_PIXELS:
                py -= WORLD_PIXELS

        if min_x is None:
            min_x = max_x = px
            min_y = max_y = py
            continue

        if px > max_x:
            if px - min_x > 0x140:
                px -= 200
            else:
                max_x = px
        if py > max_y:
            if py - min_y > 0x140:
                py -= 200
            else:
                max_y = py
        if px < min_x:
            if max_x - px > 0x140:
                px += 200
                max_x = max(max_x, px)
            else:
                min_x = px
        if py < min_y:
            if max_y - py > 0x140:
                py += 200
                max_y = max(max_y, py)
            else:
                min_y = py

    if not tracked:
        return  # no players tracked -- nothing to scroll toward
    assert min_x is not None and max_x is not None
    assert min_y is not None and max_y is not None

    # --- Step 2: compute target scroll position ---
    # Midpoint of the adjusted extent, offset so the maze viewport centres
    # rather than the full 336x240 screen. The upward MOB V word has already
    # been converted to downward screen Y, leaving a simple offset.
    target_x = (min_x + max_x) // 2 - 0x68
    target_y = (min_y + max_y) // 2 - CAM_Y_SHIFT
    return target_x, target_y


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

    # ``player_in_maze`` / ``player_tile_pos`` (0x904BCE / 0x904BD8) are
    # maintained by ``main_move_players`` (WP-5/6), which runs earlier in the
    # frame; the camera only reads them here (§17).
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
    _scroll_set_position(state)


def snap_camera(state: GameState) -> None:
    """Jump the camera straight to its target, no smoothing -- for framing the
    party immediately at level start (so the view does not pan in from 0,0).
    Writes the same hardware-register scroll the smoothed path converges to.
    """
    target = _camera_target(state, include_camera=False)
    if target is None:
        return
    state.scroll_x, state.scroll_y = target
    _scroll_set_position(state)


def _scroll_set_position(state: GameState) -> None:
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


def viewport_scroll(state: GameState, viewport_w: int, viewport_h: int) -> tuple[int, int]:
    """Return the world origin represented by the hardware scroll registers.

    MAME 0.289 pixel comparison pins the visible playfield directly to
    ``pf_hscroll``. The older host-side ``-8`` conversion shifted the whole maze
    five pixels too far right at the ROM's left clamp.
    """
    del viewport_w, viewport_h
    return state.scroll_x & 0x1FF, state.scroll_y & 0x1FF
