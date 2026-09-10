"""Literal tables and masks shared by the player ROM routine families."""

from __future__ import annotations

from ..constants import MazeObjIds, PlayerPower

# speech_charname_tbl, ROM 0x596F6 (16 longwords), indexed
# ``character + player * 4``.  Used by speech_welcome (0x487B0) and
# player_lowhealth (0x48884).
_SPEECH_CHARNAME_TBL = [
    0xBD, 0xBE, 0xBF, 0xC0,
    0xC1, 0xC2, 0xC3, 0xC4,
    0xC5, 0xC6, 0xC7, 0xC8,
    0xC9, 0xCA, 0xCB, 0xCC,
]

# Health threshold below which the warning cadence activates (§4.3).
_LOW_HEALTH_THRESHOLD = 200

# state_timer sentinel meaning "disabled".  Written by player_resetcounters
# (0x433B4), coincheck (0x42C64) and the food branch of player_tile_interact
# (0x51D24) -- *not* by main_health_countdown, which simply stops advancing the
# timer once health is back at 200 (§4.3 says "reset"; the ROM does not).
_STATE_TIMER_DISABLED = 0xFFFF

# The shot MOB's palette nibble is 0x0C + player (player_create_shot 0x5371C),
# which is also what nearby_mob_clearance_test keys off to recognise a player's
# own sprites.  Its size field is 9 = width 2, height 2 tiles (0x53768).
_SHOT_PALETTE_BASE = 0x0C

# Wall picture marker: mob_picture == 0x8000 means a solid wall occupies
# the slot (§18).
_WALL_PICTURE = 0x8000

# Vertical boundary sentinel returned by mob_probe_up/down when the player
# is in the top or bottom maze row (§4.2, player_collision_contracts.csv).
# Callers must NOT treat this as a valid MOB slot.
_VERTICAL_BOUNDARY = 0x0400

# No movement return value for player_try_move (§4.2, contracts CSV).
_NO_MOVE = 0x00F0
# The corner-squeeze and transporter gates both test ``btst #3`` of the
# player_powers *high* byte -- 0x42744 and 0x50252 -- which is word bit 11, the
# bit ``MazeObjIds.POWER_TRANSPORT`` grants.  The value 0x0800 was right; the
# old ``_POWER_INVULN`` name was not, and a "transportability" power gating the
# transporter and the squeeze-through is what the ROM is actually doing.
_POWER_TRANSPORT = int(PlayerPower.TRANSPORT)

# Maze geometry (mirrors coords.py, kept inline to avoid the import).
_MAZE_ROWS = 32
_FIGHT_PASS_TYPES = frozenset((
    int(MazeObjIds.TILE_STUN),
    int(MazeObjIds.TILE_TRAP1),
    int(MazeObjIds.TILE_TRAP2),
    int(MazeObjIds.TILE_TRAP3),
    int(MazeObjIds.EXIT),
    int(MazeObjIds.EXITTO6),
    int(MazeObjIds.TREASURE),
    int(MazeObjIds.FOOD_DESTRUCTABLE),
    int(MazeObjIds.FOOD_INVULN),
    int(MazeObjIds.POT_DESTRUCTABLE),
    int(MazeObjIds.POT_INVULN),
    int(MazeObjIds.KEY),
    int(MazeObjIds.POWER_INVIS),
    int(MazeObjIds.POWER_REPULSE),
    int(MazeObjIds.POWER_REFLECT),
    int(MazeObjIds.POWER_TRANSPORT),
    int(MazeObjIds.POWER_SUPERSHOT),
    int(MazeObjIds.POWER_INVULN),
    int(MazeObjIds.HIDDENPOT),
    int(MazeObjIds.TRANSPORTER),
))

# ``mob_probe_candidate`` (0x407A6) accepts an occupied cell only when its
# rendered anchors are less than 0x7C0 native position units apart on both
# axes.
_PROBE_OVERLAP = 0x7C0
# ``probe_up`` 0x425D0 bypasses row-zero MOB slots while the live record is in
# row one. Those slots are fixed shot/effect channels during play, so the ROM
# compares the proposed V word against this boundary instead of reading them.
_TOP_PLAYER_BOUNDARY_V = 0xF080

# Player-offscreen gate in level_flags_4. With it clear, player_try_move_core
# compares proposed H/V anchors with scroll_hpos_origin / scroll_vpos_origin
# against 0x7000 / 0x7400 (0x41C52-0x41C6A and 0x42092-0x420AA).
_PLAYER_OFFSCREEN = 0x80
