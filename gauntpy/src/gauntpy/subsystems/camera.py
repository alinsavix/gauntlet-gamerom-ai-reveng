"""The camera -- WP-13.

Reference: ``doc/04_game_subsystems.md`` §17; ``book/08_world_in_memory.md``.
"""

from __future__ import annotations

from ..constants import GameMode
from ..coords import WORLD_PIXELS
from ..state import GameState


#: The camera writes the ROM's *hardware* scroll registers. Horizontal is a
#: viewport offset shifted by the hardware centering (0x68); vertical is the
#: *inverted* register ``scroll_y = 0x1E8 - midY - 0x6C``. ``render`` wants a
#: plain viewport-top-left in world pixels -- ``render.compositor`` converts
#: these back with ``_CAM_X_SHIFT`` / ``_CAM_Y_BASE`` (see I-23).
CAM_X_SHIFT = 0x68              # 104: midX = scroll_x + CAM_X_SHIFT
CAM_Y_BASE = 0x1E8 - 0x6C       # 380: midY = CAM_Y_BASE - scroll_y

# ``scroll_set_position`` (0x46F56) has asymmetric, display-geometry-specific
# limits.  They are register limits, not generic 512px world limits.
_SCROLL_X_MIN = 0x005
_SCROLL_X_MAX = 0x124
_SCROLL_Y_MIN = 0x001
_SCROLL_Y_MAX = 0x118


def _camera_target(state: GameState) -> tuple[int, int] | None:
    """The scroll target (hardware-register form) the party wants this frame,
    or ``None`` when there is nothing to track. Steps 1-2 of §17 (extent with
    wrap + rubber band, then the offset/inverted target); the smoothing and
    clamp are the caller's.
    """
    # --- Step 1: compute player extent with wrap and rubber-band ---
    # Collect pixel positions, adjusting for horizontal seam wraparound.
    # On a toroidal level player positions may exceed 511 (the 10-bit MOB
    # field allows 0-1023); when one player is near x=0 and another is near
    # x=512 their raw difference can exceed 0x200 (the world width), so we
    # fold the far one back to compare correctly across the seam.  §17.
    px_list: list[int] = []
    py_list: list[int] = []
    ref_x: int | None = None

    for i, player in enumerate(state.players):
        if state.player_in_maze[i] == 0:
            continue

        px = state.mobs.hpos[player.mob_slot] >> 6   # pixel_x = hpos / 64
        py = state.mobs.vpos[player.mob_slot] >> 6   # pixel_y = vpos / 64

        if ref_x is None:
            ref_x = px
        elif state.wrap_h:
            # Fold across the seam so all positions are comparable (§17).
            if px - ref_x > 0x200:       # player is >512 px right of reference
                px -= 0x200
            elif ref_x - px > 0x200:     # player is >512 px left of reference
                px += 0x200

        px_list.append(px)
        py_list.append(py)

    if not px_list:
        return  # no players tracked -- nothing to scroll toward

    min_x = min(px_list)
    max_x = max(px_list)
    min_y = min(py_list)
    max_y = max(py_list)

    # Rubber band: clamp extent to at most 0xC8 (200 px) per axis.
    # Past this limit the far player is held at the screen edge instead of
    # dragging the camera further (§17; book §08 "One camera, four players").
    if max_x - min_x > 0xC8:   # 0xC8 = 200 px rubber-band limit
        max_x = min_x + 0xC8
    if max_y - min_y > 0xC8:
        max_y = min_y + 0xC8

    # --- Step 2: compute target scroll position ---
    # Midpoint of the (clamped) extent, offset so the maze viewport centres
    # rather than the full 336x240 screen.  Y is inverted: scroll_y increases
    # as the view moves up.  §17.
    target_x = (min_x + max_x) // 2 - 0x68   # 0x68 = 104 px half-viewport offset
    target_y = 0x1E8 - (min_y + max_y) // 2 - 0x6C  # 0x1E8 = 488; 0x6C = 108
    return target_x, target_y


def main_scroll_playfield(state: GameState) -> None:
    """0x46CAA -- move the shared camera toward the party.

    Bounding extent of the active players (honouring wraparound), the +/-0xC8
    rubber band so one adventurous player cannot yank the camera away from
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
    target = _camera_target(state)
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
    """Convert the hardware scroll registers the camera writes into the
    **renderer's viewport top-left** in world pixels (I-23).

    The camera keeps the ROM's hardware registers -- X shifted by the hardware
    centering, Y *inverted* -- because that is what the original writes. The
    software renderer instead wants the world-pixel corner of its
    ``viewport_w x viewport_h`` window, centred on the party. Recover the
    midpoint the camera encoded (``CAM_X_SHIFT`` / ``CAM_Y_BASE``), re-centre
    for this viewport, and clamp to the 512px maze. This is the single place the
    two conventions meet, so the camera stays ROM-faithful and the renderer
    stays a plain viewport consumer.
    """
    mid_x = state.scroll_x + CAM_X_SHIFT
    mid_y = CAM_Y_BASE - state.scroll_y
    view_x = mid_x - viewport_w // 2
    view_y = mid_y - viewport_h // 2
    max_x = max(0, WORLD_PIXELS - viewport_w)
    max_y = max(0, WORLD_PIXELS - viewport_h)
    return max(0, min(view_x, max_x)), max(0, min(view_y, max_y))
