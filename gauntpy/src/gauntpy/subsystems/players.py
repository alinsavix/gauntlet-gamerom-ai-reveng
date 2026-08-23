"""Player movement, lifecycle, health, and tile interaction -- WP-5 and WP-6.

Two work packages share this module: WP-5 owns movement and collision
(``player_try_move`` and the four ``mob_probe_*`` leaves); WP-6 owns the
status state machine, health drain, power-ups, ``player_tile_interact`` and the
transporter entry point ``player_tport``.

WP-5 appends its functions below the WP-6 section.  Both packages call only
what is already present in this file; no cross-module imports of other
subsystems are permitted (§3 ground rule 1).  The exceptions are the deliberate
hand-offs to code that owns a *different* subsystem's state --
``exits.player_exit_sequence`` for the level advance,
``thief.thief_track_victim_move`` for the thief's route grid, and
``maze_objects``' forcefield segment table and door-opening fronts -- and each
is a function-local import, made where it is called, to keep the module
importable on its own.

Nothing here is a placeholder any more: every function either performs the
ROM's whole job or performs its RAM-visible half and says, in its own
docstring, exactly where the drawing half lives.

Reference: ``doc/04_game_subsystems.md`` §4 (all), §7.2, §10.5, §10.6, §13,
§14.1, §21; ``doc/generated/player_collision_contracts.csv``,
``player_runtime_contracts.csv``, ``player_lifecycle_contracts.csv``,
``tport_forcefield_contracts.csv``, ``playfield_floor_contracts.csv``;
``book/10_players.md``.  Tables and gates transcribed from ``row76.bin`` carry
their ROM address in a comment; where the ROM and the prose docs disagree the
ROM wins and the disagreement is written down at the point of use.
"""

from __future__ import annotations

from .. import romtext
from ..constants import (
    FIRST_PLAYABLE_SLOT,
    GENERATOR_TYPES,
    HEALTH_DRAIN_MASK,
    MONSTER_TYPES,
    POWERUP_BIT_MASKS,
    POWERUP_ITEM_ID,
    SLOT_PLAYER_SHOTS,
    SLOT_TPORT_ANIMS,
    Character,
    GameMode,
    MazeObjIds,
    PlayerPower,
    PlayerStatus,
)
from ..coords import (
    POS_SHIFT,
    encode_hpos,
    encode_vpos,
    encode_vpos_at_y,
    hpos_x,
    mob_cell_of,
    native_v,
    position_field,
    replace_position,
    screen_y,
    vpos_v,
    vpos_y,
)
from ..state import NUM_PLAYERS, GameState
from .input import direction_bits, fire_held
from .sound import sound_play as _sound_play


# =============================================================================
# Tables
# =============================================================================

# ``forcefield_damage_table`` (0x5813C).  §4.3 TRAP 4.
# Index = character + 4 × armor_power_bit (bit 1 of player.powers).
# Warrior=0, Valkyrie=1, Wizard=2, Elf=3.
_FORCEFIELD_DAMAGE_TABLE = [
    2, 2, 6, 4,   # armor_power_bit=0 (no extra armor)
    1, 1, 5, 3,   # armor_power_bit=1 (extra armor, powers & 0x02)
]

# heartbeat_mask table at 0x576A8, seven words, transcribed from the ROM image
# (row76.bin offset 0x176A8): {0x1F, 0x3F, 0x3F, 0x7F, 0x7F, 0xFF, 0xFF}.  The
# eighth word there (0x0924) already belongs to score_star_picture_cycle
# (0x576B6) and is not part of this table.  §4.3 / main_health_countdown
# 0x46BC0-0x46BE2: index = health >> 5, the pulse fires when
# (player_state_timer & mask) == 0 -- smaller mask = more frequent.
# (The previous {1,3,7,15,31,63,127} entries were a plausible-looking guess and
# did not match the ROM: the real cadence never gets faster than every 32
# frames, and steps only three times across the whole 0-199 band.)
_HEALTH_SOUND_MASK_TABLE = [0x001F, 0x003F, 0x003F, 0x007F,
                             0x007F, 0x00FF, 0x00FF]

# Per-player low-health heartbeat sound, ROM 0x57942 (longwords, index =
# player).  Played by main_health_countdown at 0x46BEE, *not* by
# player_lowhealth -- that one is the spoken warning below.
_HEARTBEAT_SOUND = [0x18, 0x19, 0x1A, 0x1B]

# character_lowhealth_speech, ROM 0x5797A (four longwords).  Selected by
# getrandom(3) for entries 0-2; entry 3 ("ALL YOUR POWERS WILL BE LOST!") is
# reachable only through the powers branch at 0x48812-0x48850 (05_data_reference
# §"0x5797A", Contradicted and corrected: the index is not the character).
_CHARACTER_LOWHEALTH_SPEECH = [0x5A, 0x5B, 0x5D, 0x5C]

# speech_charname_tbl, ROM 0x596F6 (16 longwords), indexed
# ``character + player * 4``.  Used by speech_welcome (0x487B0) and
# player_lowhealth (0x48884).
_SPEECH_CHARNAME_TBL = [
    0xBD, 0xBE, 0xBF, 0xC0,
    0xC1, 0xC2, 0xC3, 0xC4,
    0xC5, 0xC6, 0xC7, 0xC8,
    0xC9, 0xCA, 0xCB, 0xCC,
]

# speech_welcome's lead-in phrase (0x4877A: ``pea.l $59.l``) and the
# 600-frame gate/reload it applies to welcome_elapsed_frames (0x48772/0x487BA).
_SPEECH_WELCOME_LEADIN = 0x59
_WELCOME_DELAY = 0x258

# player_lowhealth reloads player_respawn_speech_timer with 0x708 (0x488B8).
_LOWHEALTH_SPEECH_TIMEOUT = 0x708

# Health threshold below which the warning cadence activates (§4.3).
_LOW_HEALTH_THRESHOLD = 200

# state_timer sentinel meaning "disabled".  Written by player_resetcounters
# (0x433B4), coincheck (0x42C64) and the food branch of player_tile_interact
# (0x51D24) -- *not* by main_health_countdown, which simply stops advancing the
# timer once health is back at 200 (§4.3 says "reset"; the ROM does not).
_STATE_TIMER_DISABLED = 0xFFFF

# RESPAWN_WAIT counter limit; transition when reached (main_move_players
# 0x4A6A0: ``cmpi.w #$20, player_anim_counter``).
_RESPAWN_WAIT_LIMIT = 0x20

# Death/exit animation: the frame counter counts down to 4 (0x4A666), one step
# per four frames (0x4A652 ``andi.w #$3``).
_DEATH_ANIM_LAST_FRAME = 4
_DEATH_ANIM_STEP_MASK = 0x03

# player_state_timer reload values for the two status-0x04 dwells:
# highscore_check loads 0x0A8C for initials entry (0x49D88) and 0x0258 for the
# GAME OVER display (0x49DCA).  05_data_reference 0x904A26 documents both.
_NAME_ENTRY_TIMEOUT = 0x0A8C
_GAME_OVER_TIMEOUT = 0x0258

# Name entry (0x49DE6).  The joystick feeds a signed velocity accumulator
# clamped to +-0xA0 (0x49E4E/0x49E70); the repeat delay it produces is
# ``(0xA0 - |velocity|) >> 5 + 8`` (0x49F38-0x49F60), i.e. 13 frames per step at
# a fresh push down to 8 once the stick has been held for a while.
_NAME_ENTRY_VELOCITY_LIMIT = 0xA0
_NAME_ENTRY_REPEAT_SHIFT = 5
_NAME_ENTRY_REPEAT_BASE = 8
# The commit button is Magic *or* Fire, settled two frames (0x49F7E/0x49F9E:
# ``(shift & 0xF) == 0xC``) -- a shorter pattern than the start/join edge.
_NAME_ENTRY_COMMIT_MASK = 0x0F
_NAME_ENTRY_COMMIT_PATTERN = 0x0C
# 0x49FAA: presses are ignored for the first 0x78 frames of the 0x0A8C dwell,
# so the button that killed the hero cannot also commit its first initial.
_NAME_ENTRY_COMMIT_ARMED_BELOW = 0x0A14
# 0x4A00E: every committed initial buys 0x384 more frames.
_NAME_ENTRY_STEP_TIMEOUT = 0x0384
# Character codes name_entry_step_char (0x55440) cycles through.
_NAME_ENTRY_BACKSPACE = 0x08
_NAME_ENTRY_SPACE = 0x20
_NAME_ENTRY_FIRST_LETTER = 0x41      # 'A'
_NAME_ENTRY_LAST_LETTER = 0x5A       # 'Z'
#: Three initials per record (0x4A08C-0x4A0A0).
_NAME_ENTRY_LENGTH = 3
#: ``rank_high_score`` values outside 0-9 skip initials entry (0x49D4C/0x49D5C).
_HIGHSCORE_NO_RANK = 10

# escape_timer value that fires maze_convert_walls_to_exits (0x5208, §4.1).
_ESCAPE_TIMER_LIMIT = 0x5208
# Sound played when the escape timeout actually converted something (0x4AD20).
_SOUND_ESCAPE_WALLS = 0x27
# level_flags_3 (0x90491E) bits cleared after the conversion (0x4AD34/0x4AD3C).
_ESCAPE_CLEARS_LEVEL_FLAGS_3 = 0x08 | 0x40

# Forcefield hurt-timer initial countdown value loaded on first contact
# (0x4AACE); continuing contact refreshes a positive value below this threshold.
_FORCEFIELD_HURT_TIMEOUT = 0x10

# The transporter arrival sparkle's picture, ROM 0x578F2, installed by
# handle_tport (0x47D3E) on the per-player animation channel.
_TPORT_ARRIVAL_PICTURE = 0x1DCF

# Door-idle thresholds, main_move_players 0x4ACEC/0x4ACF2: 0xA8C frames while
# any player is carrying a key, 0x4B0 otherwise.  The counter is the ROM's own
# ``idle_timer`` word at 0x90490C, advanced by the post-loop below.
_DOOR_IDLE_THRESHOLD_WITH_KEYS = 0xA8C
_DOOR_IDLE_THRESHOLD_NO_KEYS = 0x4B0

# ``player.direction`` -> the ROM's own ``player_facing_dir`` (0x9049A4)
# encoding, which 05_data_reference documents as 0=up, 1=up-right, 2=right,
# 3=down-right, 4=down, 5=down-left, 6=left, 7=up-left.  Every ROM table keyed
# by facing (shot picture, shot spawn offset) is indexed through this map.  The
# port keeps its own encoding in ``Player.direction`` because ``play.py`` and
# the level-transition tests already render from it.
_PORT_DIR_TO_ROM_DIR = [2, 3, 4, 5, 6, 7, 0, 1]
_POWER_SHOTSPEED = int(PlayerPower.SHOTSPEED)   # bit 3, POWERUP_BIT_MASKS[3]
# shot_reflect_sound_tbl -- ROM 0x5BAD0, indexed by character.
_PLAYER_SHOT_SOUND = [0x45, 0x47, 0x46, 0x48]
# Character-specific death SFX, refs/soundcmds.csv 0x14-0x17; ROM 0x57932
# (four longwords), played by the death path of main_health_countdown (0x46B2A).
_PLAYER_DEATH_SOUND_BASE = 0x14

# Shot spawn offsets, ROM shot_spawn_hpos_tbl (0x5BAB0) and shot_spawn_vpos_tbl
# (0x5BAC0), read by player_create_shot at 0x536FA/0x53746 and added to the
# firing player's masked hpos/vpos.  Both are native position words, so they
# are added to the MOB word as they stand and the vertical column keeps the
# hardware's upward sense.  Indexed by ROM facing direction.
_SHOT_SPAWN_DH = [0x0200, 0x0500, 0x0600, 0x0300, 0x0200, -0x0080, -0x0200, -0x0100]
_SHOT_SPAWN_DV = [0x0700, 0x0300, 0x0180, -0x0080, -0x0100, -0x0280, 0x0180, 0x0380]

# The shot MOB's palette nibble is 0x0C + player (player_create_shot 0x5371C),
# which is also what nearby_mob_clearance_test keys off to recognise a player's
# own sprites.  Its size field is 9 = width 2, height 2 tiles (0x53768).
_SHOT_PALETTE_BASE = 0x0C
_SHOT_TILE_WIDTH = 2
_SHOT_TILE_HEIGHT = 2

# player_shot_picture_tbl -- ROM 0x58B8A, 32 records of two words (frame A,
# frame B) indexed ``character * 8 + rom_direction``; player_create_shot uses
# frame A (0x536EA).  Transcribed from row76.bin offset 0x18B8A.
_PLAYER_SHOT_PICTURE = [
    # Warrior
    0x1C9F, 0x1CA7, 0x1CAF, 0x1CB7, 0x1CBF, 0x1CC7, 0x1CCF, 0x1C97,
    # Valkyrie
    0x17FC, 0x18FC, 0x19FC, 0x1AFC, 0x1BC3, 0x1C68, 0x1C6C, 0x1C70,
    # Wizard
    0x1CD7, 0x1CDF, 0x1CE7, 0x1CEF, 0x1CF7, 0x1D00, 0x1D08, 0x1D10,
    # Elf
    0x1C74, 0x1C78, 0x1C7C, 0x1C80, 0x1C84, 0x1C8B, 0x1C8F, 0x1C93,
]

# player_death_picture_tbl -- ROM 0x58A4A (``anim_table_idle``), 4 characters
# x 8 facing directions, indexed ``character * 8 + frame`` by the first half of
# the status-0x08 branch at 0x4A696: the hero spins from its facing direction
# down to 4, one step per four frames.
_PLAYER_DEATH_PICTURE = [
    0x0BD8, 0x0BF3, 0x0C12, 0x0C2D, 0x0C3F, 0x0B87, 0x0BA2, 0x0BBD,
    0x11B4, 0x11CF, 0x1112, 0x112D, 0x1148, 0x1163, 0x117E, 0x1199,
    0x1412, 0x142D, 0x1448, 0x1463, 0x13A2, 0x13BD, 0x13D8, 0x13F3,
    0x15D8, 0x15F3, 0x1612, 0x162D, 0x1648, 0x1663, 0x15A2, 0x15BD,
]

# player_exit_picture_tbl -- ROM 0x5870A, 4 characters x 8 frames, transcribed
# from row76.bin offset 0x1870A.  The *second* half of the status-0x08 branch
# (0x4A796-0x4A7BE) steps through it with ``player_anim_counter >> 2`` while the
# counter climbs 0 -> 0x20, which is the 32-frame dissolve a hero plays in the
# exit before the level actually ends.
_PLAYER_EXIT_PICTURE = [
    0x0C3F, 0x1087, 0x1090, 0x1099, 0x10A2, 0x10AB, 0x10B4, 0x10BD,
    0x1148, 0x17AB, 0x17B4, 0x17BD, 0x17C6, 0x17CF, 0x17D8, 0x17E1,
    0x13A2, 0x17EA, 0x17F3, 0x1800, 0x1809, 0x1812, 0x181B, 0x1824,
    0x1548, 0x176C, 0x1775, 0x177E, 0x1787, 0x1790, 0x1799, 0x17A2,
]

# The four player picture banks are literal game-ROM words, not host/gex
# animation metadata.  The port direction is right, down-right, ... up-right;
# ``_PORT_DIR_TO_ROM_DIR`` below maps that onto these ROM-order tables
# (up, up-right, ... up-left).
def _rom_picture_table(words: str) -> tuple[int, ...]:
    return tuple(int(word, 16) for word in words.split())


# anim_table_walking -- ROM 0x58A8A, 4 characters × 8 directions × 4 frames.
_PLAYER_WALKING_PICTURE = _rom_picture_table("""
    0BCF 0BD8 0BE1 0BD8 0BEA 0BF3 0C00 0BF3
    0C09 0C12 0C1B 0C12 0C24 0C2D 0C36 0C2D
    0B63 0B6C 0B75 0B6C 0B7E 0B87 0B90 0B87
    0B99 0BA2 0BAB 0BA2 0BB4 0BBD 0BC6 0BBD
    11B4 11BD 11C6 11BD 11CF 11D8 11E1 11D8
    1112 111B 1124 111B 112D 1136 113F 1136
    1148 1151 115A 1151 1163 116C 1175 116C
    117E 1187 1190 1187 1199 11A2 11AB 11A2
    1412 141B 1424 141B 142D 1436 143F 1436
    1448 1451 145A 1451 1463 146C 1475 146C
    13A2 13AB 13B4 13AB 13BD 13C6 13CF 13C6
    13D8 13E1 13EA 13E1 13F3 1400 1409 1400
    15D8 15E1 15EA 15E1 15F3 1600 1609 1600
    1612 161B 1624 161B 162D 1636 163F 1636
    1648 1651 165A 1651 1663 166C 1675 166C
    15A2 15AB 15B4 15AB 15BD 15C6 15CF 15C6
""")

# anim_table_fighting -- ROM 0x5884A, 4 characters × 8 directions × 8 frames.
_PLAYER_FIGHTING_PICTURE = _rom_picture_table("""
    0D5A 0D63 0D6C 0D75 0D75 0D6C 0D63 0D5A
    0D7E 0D87 0D90 0D99 0D99 0D90 0D87 0D7E
    0DA2 0DAB 0DB4 0DBD 0DBD 0DB4 0DAB 0DA2
    0DC6 0DCF 0DD8 0DE1 0DE1 0DD8 0DCF 0DC6
    0CC6 0CCF 0CD8 0CE1 0CE1 0CD8 0CC6 0CBD
    0CEA 0CF3 0D00 0D09 0D09 0D00 0CF3 0CEA
    0D12 0D1B 0D24 0D2D 0D2D 0D24 0D1B 0D12
    0D36 0D3F 0D48 0D51 0D51 0D48 0D3F 0D36
    12C6 12CF 12D8 12E1 12E1 12D8 12CF 12C6
    12EA 12F3 1300 1309 1309 1300 12F3 12EA
    11EA 11F3 1200 1209 1209 1200 11F3 11EA
    1212 121B 1224 122D 122D 1224 121B 1212
    1236 123F 1248 1251 1251 1248 123F 1236
    125A 1263 126C 1275 1275 126C 1263 125A
    127E 1287 1290 1299 1299 1290 1287 127E
    12A2 12AB 12B4 12BD 12BD 12B4 12AB 12A2
    1412 14C6 14C6 14CF 14CF 14C6 14C6 1412
    142D 14D8 14D8 14E1 14E1 14D8 14D8 142D
    1448 14EA 14EA 14F3 14F3 14EA 14EA 1448
    1463 1500 1500 1509 1509 1500 1500 1463
    13A2 147E 147E 1487 1487 147E 147E 13A2
    13BD 1490 1490 1499 1499 1490 1490 13BD
    13D8 14A2 14A2 14AB 14AB 14A2 14A2 13D8
    13F3 14B4 14B4 14BD 14BD 14B4 14B4 13F3
    16B4 16BD 16C6 16C6 16C6 16C6 16BD 16B4
    16CF 16D8 16E1 16E1 16E1 16E1 16D8 16CF
    16EA 16F3 1712 1712 1712 1712 16F3 16EA
    171B 1724 172D 172D 172D 172D 1724 171B
    1736 173F 1748 1748 1748 1748 173F 1736
    1751 175A 1763 1763 1763 1763 175A 1751
    167E 1687 1690 1690 1690 1690 1687 167E
    1699 16A2 16AB 16AB 16AB 16AB 16A2 1699
""")

# anim_table_shooting -- ROM 0x5874A, 4 characters × 8 directions × 4 frames.
_PLAYER_SHOOTING_PICTURE = _rom_picture_table("""
    0C87 0C90 0C90 0C90 0C99 0CA2 0CA2 0CA2
    0CAB 0CB4 0CB4 0CB4 1087 0CBD 0CBD 0CBD
    0C3F 0C48 0C48 0C48 0C51 0C5A 0C5A 0C5A
    0C63 0C6C 0C6C 0C6C 0C75 0C7E 0C7E 0C7E
    12C6 1348 1348 1348 12EA 1351 1351 1351
    11EA 1312 1312 1312 1212 131B 131B 131B
    1236 1324 1324 1324 125A 132D 132D 132D
    127E 1336 1336 1336 12A2 133F 133F 133F
    1412 137E 137E 137E 142D 1387 1387 1387
    1448 1390 1390 1390 1463 1399 1399 1399
    13A2 135A 135A 135A 13BD 1363 1363 1363
    13D8 136C 136C 136C 13F3 1375 1375 1375
    156C 1524 1524 1524 1575 152D 152D 152D
    157E 1536 1536 1536 1587 153F 153F 153F
    1590 1548 1548 1548 1599 1551 1551 1551
    155A 1512 1512 1512 1563 151B 151B 151B
""")

# anim_table_idle -- ROM 0x58A4A.  The death spin uses this same table, retained
# under its historical name above for the status-8 lifecycle code and tests.
_PLAYER_IDLE_PICTURE = tuple(_PLAYER_DEATH_PICTURE)

# fighting_anim_end -- ROM 0x58090.  It controls both the four-frame firing
# cadence and the input gate that re-arms another shot.
_FIGHTING_ANIM_END = (3, 3, 3, 3)
_PLAYER_INVISIBLE_PICTURE = 0x1709
_INVISIBILITY_FLASH_MASKS = (
    0x0004, 0x0002, 0x0002, 0x0001,
    0x0001, 0x0001, 0x0001, 0x0001,
    0x0001, 0x0001, 0x0001, 0x0001,
    0x0001, 0x0001, 0x0001, 0x0001,
)


def _player_animation_action(state: GameState, player_index: int,
                             walking: bool | None = None) -> str:
    """Return main_move_players' picture-table branch for one active hero."""
    if state.player_fighting_dir[player_index]:
        return "fight"
    if walking is None:
        walking = bool(state.player_walking[player_index])
    if walking:
        return "walk"
    if state.player_shooting[player_index]:
        return "shoot"
    return "idle"


def update_player_sprite(state: GameState, player_index: int,
                         *, walking: bool | None = None) -> None:
    """Write one hero's current ROM animation picture without advancing time.

    This is the presentation half of ``main_move_players``' 0x4AB08-0x4AC7A
    tail.  It intentionally owns no host/gex dependency: the renderer resolves
    the literal ROM picture through the hero MOB's player record, which is what
    keeps Wizard frames separate from the identically numbered Sorcerer art.

    The ``walking`` result is a frame-local ROM value.  Core callers pass it
    directly; public callers can omit it to reuse the last result retained in
    ``state.player_walking``.  Status-8 death/exit and in-flight transporter
    pictures are written by their own state machines and must not be replaced.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return
    player = state.players[player_index]
    if (not player.active or not player.mob_slot
            or state.player_tport_phase[player_index] >= 0):
        return

    character = player.character & 0x03
    rom_direction = _PORT_DIR_TO_ROM_DIR[player.direction & 0x07]
    action = _player_animation_action(state, player_index, walking)
    counter = player.anim_counter & 0xFFFF
    if action == "fight":
        picture = _PLAYER_FIGHTING_PICTURE[
            character * 64 + rom_direction * 8 + ((counter >> 1) & 0x07)
        ]
    elif action == "walk":
        picture = _PLAYER_WALKING_PICTURE[
            character * 32 + rom_direction * 4 + ((counter >> 2) & 0x03)
        ]
    elif action == "shoot":
        picture = _PLAYER_SHOOTING_PICTURE[
            character * 32 + rom_direction * 4 + ((counter >> 2) & 0x03)
        ]
    else:
        picture = _PLAYER_IDLE_PICTURE[character * 8 + rom_direction]

    # 0x4AC30-0x4AC7A: the invisibility blink is applied after every ordinary
    # action-table lookup.  ``main_move_players`` clears the power as its timer
    # reaches zero, so a manual active bit with timer 0 follows ROM table row 0.
    if player.powers & int(PlayerPower.INVIS):
        phase = (state.player_invis_timer[player_index] >> 7) & 0x0F
        if (_INVISIBILITY_FLASH_MASKS[phase] & state.frame_counter) == 0:
            picture = _PLAYER_INVISIBLE_PICTURE

    state.mobs.picture[player.mob_slot] = picture


def update_player_sprites(state: GameState) -> None:
    """Refresh all active hero MOB pictures without changing their counters."""
    for player_index in range(NUM_PLAYERS):
        update_player_sprite(state, player_index)


def _player_shooting_input_update_one(state: GameState,
                                      player_index: int) -> None:
    """Arm one held-Fire action; the call is idempotent during its throw."""
    player = state.players[player_index]
    if (not player.active or not player.mob_slot
            or state.player_tport_phase[player_index] >= 0
            or player.stundelay
            or not _joystick_fire_held(state, player_index)):
        return
    # 0x474FE/0x477D0: the input arm is the ``else`` branch of the live-shot
    # handler. A player cannot restart the throw while their fixed channel is
    # still occupied.
    if state.mobs.picture[player_index + SLOT_PLAYER_SHOTS.start]:
        return
    if (state.player_shooting[player_index]
            and (player.anim_counter & 0xFFFF)
            <= _FIGHTING_ANIM_END[player_index]):
        return
    state.reflect_count[player_index] = 4
    player.anim_counter = 0
    state.player_shooting[player_index] = -1
    state.player_fighting_dir[player_index] = 0
    state.player_walking[player_index] = 0


def player_shooting_input_update(state: GameState) -> None:
    """0x47B72-0x47BF6 -- arm held-Fire shooting actions for all players.

    The ROM places this input gate in ``main_handle_shots`` before the player
    loop.  ``main_move_players`` also calls it when driven standalone, making
    headless/direct ticks observe the same action state.  The operation is
    idempotent while the current four-count throw is still underway.
    """
    for player_index in range(NUM_PLAYERS):
        _player_shooting_input_update_one(state, player_index)


def _advance_player_sprite(state: GameState, player_index: int, *,
                           walking: bool, fire_held: bool) -> None:
    """Run the counter/action half of 0x4AB08-0x4AC0E for one hero."""
    player = state.players[player_index]
    if (not player.active or not player.mob_slot
            or state.player_tport_phase[player_index] >= 0):
        return

    state.player_walking[player_index] = int(walking)
    update_player_sprite(state, player_index, walking=walking)

    if state.player_fighting_dir[player_index] or walking:
        player.anim_counter = (player.anim_counter + 1) & 0xFFFF
        return
    if not state.player_shooting[player_index]:
        return

    previous_counter = player.anim_counter & 0xFFFF
    player.anim_counter = (previous_counter + 1) & 0xFFFF
    if previous_counter == _FIGHTING_ANIM_END[player_index]:
        player_create_shot(state, player_index)

    # 0x4ABF4-0x4AC0C: held Fire repeats after the four-count throw; on release
    # the animation is allowed through count 8, and cannot exceed count 15.
    if previous_counter > 0x0F or (
            not fire_held and previous_counter > 8):
        state.player_shooting[player_index] = 0


# =============================================================================
# Power-ups (§4.6; ROM 0x59B64 / 0x4C72A / 0x517BA-0x518B0)
# =============================================================================
#
# ``constants.PlayerPower`` carries the masks and records how they were pinned
# down.  What lives here is the rest of each arm: the countdown each power arms
# and the speech that announces it.

#: ``powerup_speech_ids`` -- ROM 0x59B7C, 12 longwords parallel to
#: ``POWERUP_BIT_MASKS``; a zero entry means the pickup speaks nothing.
_POWERUP_SPEECH_IDS = (
    0x8F, 0x90, 0x91, 0x92, 0x93, 0x94,
    0x8E, 0xD1, 0xCF, 0xD0, 0x00, 0x00,
)

#: POWER_INVIS arms ``invis_timer`` with 0x4B0 frames (0x517D4).
_INVIS_TIMER_LOAD = 0x4B0

#: POWER_REPULSE arms the repulsiveness countdown from the character-indexed
#: table at ROM 0x5B72C (0x5181A).  Bit 9 is what 0x4185C tests to make a
#: monster flee; doc/05 calls both the timer and this table "reflect", which is
#: a different power (bit 10, type 0x38, read at 0x4B4B0 and with no timer).
_REPULSE_TIMER_INIT = (0x038C, 0x04B8, 0x0260, 0x038C)

#: POWER_SUPERSHOT adds eleven charges (0x51874 ``addi.b #$b``).
_SUPERSHOT_CHARGES = 0x0B

#: POWER_INVULN arms the 0x905F40 countdown with 0x384 frames (0x5189E).
_INVULN_TIMER_LOAD = 0x384

#: The treasure-room maze band (0x519FE/0x51A08): mazes 0x68 through 0x72 skip
#: the bonus-multiplier block and settle up on the bonus screen instead.
_TREASURE_ROOM_MAZES = range(0x68, 0x73)

#: ``player_tport_phase`` value at which the transition's move milestone lands.
#: WP-14's loop 2 counts the phase up one per frame and acts on ``phase >> 1``
#: when the phase is even, so step 0x0B -- ``tport_player_move`` at 0x47324 --
#: is phase 0x16.  Its idle sentinel is negative (the ROM stores 0xFFFF).
_TRANSITION_MOVE_PHASE = 0x0B * 2
_TRANSITION_IDLE_PHASE = -1


# =============================================================================
# First-encounter dialogs (§10.4; dialog_first_encounter 0x4C440)
# =============================================================================
#
# The routine takes a 32-bit mask whose set bit number selects the message
# record, plus an optional numeric value the record interpolates.  These are the
# masks pushed at the call sites inside this file's routines; the records
# themselves live in ``score.DIALOG_MESSAGES``.
#
# Records reached from *other* modules, listed so nobody re-wires them here:
# record 4 ("COLLECT MAGIC POTION BEFORE PRESSING MAGIC") is main_handle_potions'
# (0x470CC/0x47134, potions.py), record 7 ("SHOOTING POISON SLOWS MONSTERS") is a
# shot-hit dialog (0x4B8FA/0x4BA50, shots.py), and record 15 ("AVOID ACID
# PUDDLES") comes from monster_playerhit's per-monster-type mask held in A4
# (0x4986A/0x49A2C, monsters.py) rather than from any fixed literal.

_DIALOG_FOOD = 0x00000001           # record 0, 0x51CDE / 0x51C00
_DIALOG_LOW_HEALTH = 0x00000004     # record 2, 0x4677E / 0x50EB0
_DIALOG_KEYS = 0x00000008           # record 3, 0x51620
_DIALOG_SAVE_POTIONS = 0x00000020   # record 5, 0x51796
_DIALOG_POISONED = 0x00002000       # record 13, 0x516BE / 0x51CAA
_DIALOG_TRAP = 0x00800000           # record 23, 0x51278
_DIALOG_STUN_FLOOR = 0x04000000     # record 26, 0x51388
_DIALOG_LOCKED_TREASURE = 0x08000000  # record 27, mob_collision_test 0x52614
_DIALOG_FORCEFIELD = 0x80000000     # 0x4AAEE, inside the contact block
_DIALOG_FAKE_EXIT = 0x40000000      # record 30, 0x513EC

#: hpos bit 4 (0x513E4 ``btst #4`` on the low byte) marks an exit as an
#: illusion.  §8.2 calls hpos bits 5-4 the MOB's two software flags.
_FAKE_EXIT_FLAG = 0x0010

# Secret-room objective codes this subsystem reports progress on.  WP-15
# (``exits.secret_trick_progress``/``secret_trick_set``) owns the counter and
# the ``trick_tasknum`` guard; these are just the literals the ROM compares.
_TRICK_NOGREEDY1 = 12       # 0x0C -- "don't be greedy": keys or potions
_TRICK_NOUSEINVUL = 8       # 0x08 -- "don't use invulnerability"
#: 0x50C30/0x50C42 -- the two "try transportability" objectives, decided on the
#: spot when the transporter drops the player beside acid (1) or death (2).
_TRICK_TRANSPORT1 = 1
_TRICK_TRANSPORT2 = 2
#: 0x5027E/0x509E4 -- visit every transporter; progress is a pad bitmask.
_TRICK_VISIT_TPORTS = 0x56
#: 0x5140A -- the fooled-by-a-fake objective, an assignment like 0x518B2.
_TRICK_NOFOOLED = 11
#: The food arm reports 0x0D (0x51C0C/0x51CEE).  The treasure arm's own codes
#: -- 0x0E (0x519C2), 0x50 (0x519CE) and 0x5A (0x519DA) -- belong to the same
#: ROM block as the count bump and are reported by ``exits.treasure_collected``.
#: Note that WP-15's ``TRICK_NOGREEDY2 = 13``/``TRICK_DIET = 14`` comments read
#: the other way round from the ROM's compares; these follow the ROM.
_TRICK_FOOD = 0x0D
#: Objective codes from the 0x50-0x5D band rather than the 1-17 trick
#: numbering.  The hidden pot answers to two of them (0x518FA/0x51908), and in
#: every such case the alternatives share one ``addq.b #1``.
_TASK_HIDDENPOT_A = 0x51
_TASK_HIDDENPOT_B = 0x5D

#: A key is worth 100 before the bonus multiplier (0x514F4 ``pea $64``).
_KEY_SCORE = 0x64

#: Food pictures and effects verified against 0x51ADC-0x51CFE.
_RANDOM_FOOD_PICTURE = 0x277B
_POISONED_FOOD_PICTURE = 0x25ED
_POISONED_POTION_PICTURE = 0x20FC
# FOOD000, retained as the ordinary-food fixture constant used by tests.
_WHOLESOME_FOOD_PICTURE = 0x0963
_RANDOM_FOOD_HEALTH = (
    100, 50, 75, 100, 75,
    50, 25, 200, 25, 50,
    75, 100, 75, 100, 25,
    200, 75, 25, 50, 100,
)
# ``pickup_score_popup_types`` (0x5B774), parallel to the adaptive food table.
_RANDOM_FOOD_POPUP = (
    13, 11, 12, 13, 12, 11, 10, 14, 10, 11,
    12, 13, 12, 13, 10, 14, 12, 10, 11, 13,
)

#: Poisoning costs 50 health (0x51C48/0x5164E) -- the same 50 the record's
#: "PLAYER LOSES %d HEALTH" line is passed -- and arms the dizzy countdown with
#: 0x4B0 frames (0x51C68/0x5166E).
_POISON_DAMAGE = 0x32
_DIZZY_TIMER_LOAD = 0x4B0


def _dialog(state: GameState, player_index: int, mask: int,
            value: int = 0) -> None:
    """``dialog_first_encounter`` (0x4C440) -- WP-14's real message box.

    A cross-subsystem call, because score.py owns the record text, the one-shot
    flags, the box geometry and the speech, and its ``dialog_timer`` is what
    gates the gameplay band for the frames the box is up (§10.4).
    """
    from . import score

    score.dialog_first_encounter(state, player_index, mask, value)


def _poisoned(state: GameState, player_index: int) -> None:
    """0x51C40-0x51CB4 (food) and 0x51644-0x516C8 (potion) -- the bad variant.

    Both arms are the same code twice: take 50 health with a floor at zero, arm
    the dizzy countdown, speak a character-random hurt line, and show record 13
    with 50 as its interpolated value.
    """
    player = state.players[player_index]
    player.health = max(0, player.health - _POISON_DAMAGE)   # 0x51C4A/0x51C5A
    state.player_dizzy_timer[player_index] = _DIZZY_TIMER_LOAD  # 0x51C68
    _sound_play(state, _PLAYER_DEATH_SOUND_BASE + (player.character & 0x03))
    _dialog(state, player_index, _DIALOG_POISONED, _POISON_DAMAGE)


# =============================================================================
# Cross-package hooks
# =============================================================================
# main_move_players and player_tile_interact call these; the presentation half
# of each belongs to another work package, so each hook implements exactly the
# RAM-visible half the ROM performs and routes the rest through the state the
# owning package already reads.

_SECRET_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTUWXYZ"  # ROM 0x54CA6
_SECRET_NAME_LENGTH = 29


def _secret_crc16(name: list[int]) -> int:
    """Port secret_code_build's table-driven CRC-CCITT update."""
    crc = 0
    for code in name:
        if code in (0, 0x20):
            if code == 0:
                break
            continue
        index = (code ^ (crc & 0xFF)) & 0xFF
        table = index << 8
        for _ in range(8):
            table = ((table << 1) ^ 0x1021) & 0xFFFF if table & 0x8000 else (table << 1) & 0xFFFF
        old_high = (crc >> 8) & 0xFF
        crc = ((table & 0xFF) << 8) | (old_high ^ (table >> 8))
    return crc


def secret_code_build(state: GameState) -> str:
    """Port secret_code_build 0x54BE0 and return its ``XXX-XXX`` result."""
    crc = _secret_crc16(state.secret_name_buffer)
    packed = (
        ((((state.secret_trick_last & 0x0F) << 4)
          | (state.secret_trick_id & 0x0F)) << 7)
        | (state.secret_prev_maze & 0x7F)
    )
    code = (
        _SECRET_CODE_ALPHABET[((crc >> 8) >> 2) & 0x1F]
        + _SECRET_CODE_ALPHABET[(packed >> 10) & 0x1F]
        + _SECRET_CODE_ALPHABET[(crc >> 5) & 0x1F]
        + "-"
        + _SECRET_CODE_ALPHABET[(packed >> 5) & 0x1F]
        + _SECRET_CODE_ALPHABET[crc & 0x1F]
        + _SECRET_CODE_ALPHABET[packed & 0x1F]
    )
    state.secret_code = code
    return code


def secret_getname(state: GameState) -> None:
    """Port secret_getname 0x54EC6, including its alpha-RAM setup."""
    winner = state.secret_winner
    if not 0 <= winner < NUM_PLAYERS:
        return
    player = state.players[winner]
    if not (state.game_settings & 0x2000):
        state.bonus_timer = 0x0385
        player.status = int(PlayerStatus.ALIVE_NEXT)
        state.secret_winner = -1
        return
    player.name_entry_repeat_delay = _NAME_ENTRY_VELOCITY_LIMIT
    player.name_entry_velocity = 0
    player.initials_cursor = 0
    player.status = int(PlayerStatus.SECRET_NAME_ENTRY)
    state.bonus_timer = 0x0A8D
    state.secret_name_buffer = [ord("A")] + [ord(" ")] * (_SECRET_NAME_LENGTH - 1)
    from .score import write_secret_name_entry

    write_secret_name_entry(state, winner)


def secret_name_entry_update(state: GameState) -> None:
    """Port the 29-character secret winner editor at 0x54FE8."""
    winner = state.secret_winner
    if not 0 <= winner < NUM_PLAYERS:
        return
    player = state.players[winner]
    if player.status != int(PlayerStatus.SECRET_NAME_ENTRY):
        return

    cursor = player.initials_cursor
    dirs = (~(state.player_input_raw[winner] >> 4)) & 0x0F
    velocity = player.name_entry_velocity
    if dirs & 0x09:
        velocity = min(velocity + 1, _NAME_ENTRY_VELOCITY_LIMIT) if velocity >= 0 else 0
    elif dirs & 0x06:
        velocity = max(velocity - 1, -_NAME_ENTRY_VELOCITY_LIMIT) if velocity <= 0 else 0
    else:
        velocity = 0
    player.name_entry_velocity = velocity

    delay = player.name_entry_repeat_delay
    if delay:
        delay -= 1
    if delay == 0:
        if velocity and 0 <= cursor < _SECRET_NAME_LENGTH:
            state.secret_name_buffer[cursor] = name_entry_step_char(
                state.secret_name_buffer[cursor], velocity, bool(cursor),
            )
        delay = ((_NAME_ENTRY_VELOCITY_LIMIT - abs(velocity))
                 >> _NAME_ENTRY_REPEAT_SHIFT) + _NAME_ENTRY_REPEAT_BASE
    player.name_entry_repeat_delay = delay & 0xFF

    from .score import write_secret_code_result, write_secret_name_entry

    write_secret_name_entry(state, winner)
    if (
        _name_entry_commit_pressed(state, winner)
        and state.bonus_timer < 0x0A15
    ):
        if state.secret_name_buffer[cursor] == _NAME_ENTRY_BACKSPACE:
            state.secret_name_buffer[cursor] = _NAME_ENTRY_SPACE
            cursor = max(0, cursor - 1)
        else:
            cursor += 1
            state.bonus_timer = 0x0385
        player.initials_cursor = cursor
        if cursor < _SECRET_NAME_LENGTH:
            write_secret_name_entry(state, winner)

    if state.bonus_timer >= 5 and cursor < _SECRET_NAME_LENGTH:
        return
    for index in range(max(0, cursor), _SECRET_NAME_LENGTH):
        state.secret_name_buffer[index] = _NAME_ENTRY_SPACE
    secret_code_build(state)
    write_secret_code_result(state, winner)
    player.status = int(PlayerStatus.ALIVE_NEXT)
    state.secret_winner = -1
    state.debounce_shift_magic[winner] = 0
    state.debounce_shift_fire[winner] = 0
    state.bonus_timer = 0x02D1


def show_continue_prompt(state: GameState) -> None:
    """0x44C7E -- the five-line PRESS START continue prompt (§10.5).

    Verified gates, all of them RAM: ``level_players_active == 0``, a level
    other than 1, ``attract_timer`` not holding its disabled sentinel, and
    every player status either 0 or SELECTING (0x10).  When it draws, sound
    0x3B ("Gauntlet II Theme Song") plays and ``title_intro_state`` becomes 1.
    It does **not** decrement ``level_players_active``.

    The five text lines go through the fixed OS ``draw_string`` service; that
    is WP-2's, so this hook stops at the state the rest of the port reads.
    """
    if state.level_players_active != 0:
        return
    if state.levelnum_current == 1:
        return
    if state.attract_timer == 0xFFFF:
        return
    allowed = (int(PlayerStatus.REMOVED), int(PlayerStatus.SELECTING))
    if any(p.status not in allowed for p in state.players):
        return

    from .display import write_alpha_text

    _sound_play(state, 0x00)          # 0x44D06
    for text, column, row in romtext.CONTINUE_PROMPT_LINES:
        write_alpha_text(state, column, row, text, 0x8000)
    _sound_play(state, 0x3B)          # "Gauntlet II Theme Song" (§10.5)
    state.title_intro_state = 1


def setup_infopanel(state: GameState, player_selector: int) -> None:
    """0x452D0 -- redraw the info panel (§14.1).

    ``player_selector`` of -1 rebuilds the whole panel (the ROM loops 3->0);
    any other value redraws that player only.  Per §14.1 the body dispatches on
    player status and shares the numeric renderers ``draw_player_score``
    (0x45940) and ``draw_player_health`` (0x459A2) plus ``player_inv_update``,
    so this is a *synchronous* rebuild -- not a request for one.  It runs on
    join, on death (0x46AD0), and at every screen change, and the panel is
    expected to be right on the very next rendered frame rather than on that
    player's turn in ``main_score_display``'s four-frame rotation.

    So it drives WP-14's real latch: ``score``'s two draw routines write the
    ``PanelField`` the renderer reads, and the ``player_redraw`` bits (0x904908)
    are cleared because the draw the bits were asking for has just happened --
    the ROM clears them in ``draw_player_score``/``draw_player_health`` for the
    same reason.
    """
    from . import score

    if player_selector < 0:
        targets = range(NUM_PLAYERS)
    elif player_selector < NUM_PLAYERS:
        targets = range(player_selector, player_selector + 1)
    else:
        return
    if player_selector < 0:
        score.write_info_panel_backdrop(state)
        score.write_info_panel_header(state)
    for i in targets:
        score.write_player_panel_background(state, i)
        initials_entry = (
            state.players[i].status == int(PlayerStatus.DYING)
            and 0 <= state.players[i].highscore_rank < _HIGHSCORE_NO_RANK
        )
        if initials_entry:
            score.clear_player_panel_content(state, i)
            score.write_player_initials_entry(state, i)
        elif state.players[i].status == int(PlayerStatus.SECRET_NAME_ENTRY):
            score.clear_player_panel_content(state, i)
            score.write_secret_name_entry(state, i)
        elif state.players[i].status != int(PlayerStatus.REMOVED):
            score.write_player_panel_static(state, i)
            score._draw_player_score(state, i)     # 0x45940
            score._draw_player_health(state, i)    # 0x459A2
            player_inv_update(state, i)            # 0x45522
        else:
            score.clear_player_panel_content(state, i)
            field = score.info_panel(state).players[i]
            field.score = state.players[i].score
            field.score_attr = score.PLAYER_TEXT_PALETTE_WORDS[i]
            field.score_drawn = True
            field.health = state.players[i].health
            field.health_attr = score.PLAYER_TEXT_PALETTE_WORDS[i]
            field.health_drawn = True
            field.bonusmult = state.players[i].bonusmult
        if not initials_entry and state.players[i].status != int(PlayerStatus.SECRET_NAME_ENTRY):
            score.write_player_panel_status(state, i)
        state.score_dirty[i] = 0               # player_redraw bit 0, serviced
        state.health_dirty[i] = 0              # player_redraw bit 1, serviced
    score.write_it_labels(state)


def speech_welcome(state: GameState, player_index: int) -> None:
    """0x48754 -- "Welcome, <character>" join speech (§4.4).

    Exact ROM shape (0x48754-0x487C8):

      * the lead-in phrase 0x59 is spoken when ``level_players_active`` is 1
        **or** ``welcome_elapsed_frames`` has reached 600 (0x48766/0x48772);
      * below 600 elapsed frames the routine stops there (0x4878C);
      * otherwise it speaks ``speech_charname_tbl[character + player * 4]``
        (0x596F6) and reloads ``welcome_elapsed_frames`` to 600 (0x487BA).

    Speech goes out through ``sound_speech_play`` (0x4AD4E), which is the same
    command ring ``sound_play`` uses, so it is queued here like any other sound.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return
    player = state.players[player_index]

    if state.level_players_active == 1 or state.welcome_elapsed_frames >= _WELCOME_DELAY:
        _sound_play(state, _SPEECH_WELCOME_LEADIN)

    if state.welcome_elapsed_frames < _WELCOME_DELAY:
        return

    index = (player.character & 0x03) + player_index * 4
    _sound_play(state, _SPEECH_CHARNAME_TBL[index])
    state.welcome_elapsed_frames = _WELCOME_DELAY


def player_inv_update(state: GameState, player_index: int) -> None:
    """0x45ACA -- redraw one player's key/potion row and power-up icons.

    Every pickup that changes ``keysnum``, ``potionsnum`` or ``powers`` calls
    it (0x515E4-0x51E0E), ``setup_infopanel`` calls it as part of the panel
    rebuild (0x45522), and loop 3 of ``main_score_update`` calls it every frame
    (0x470BA).  It is a pure draw: the ROM never touches ``player_redraw`` here,
    because it is not asking for a redraw later -- it is doing one now.

    ``PanelField`` latches score and health, while the compositor reads inventory
    counts from the same player record when it draws the alpha inventory row.
    Re-latching health here keeps the shared multiplier row current immediately.
    """
    from . import score

    if 0 <= player_index < NUM_PLAYERS:
        score._draw_player_health(state, player_index)
        score.write_player_inventory(state, player_index)


def _secret_trick_progress(state: GameState, player_index: int,
                           trick_id: int, amount: int = 1) -> None:
    """WP-15's ``exits.secret_trick_progress`` -- the ``addq.b #1`` hook shape.

    Every progress site in the ROM is ``cmpi.b #<trick>,trick_tasknum`` followed
    by a bump of that player's ``secret_tricks_flags`` byte, so the guard lives
    in WP-15's routine and the call sites here stay one line each.
    """
    from .exits import secret_trick_progress

    secret_trick_progress(state, player_index, trick_id, amount)


def _secret_trick_set(state: GameState, player_index: int,
                      trick_id: int, value: int) -> None:
    """WP-15's ``exits.secret_trick_set`` -- the ``move.b #n`` hook shape."""
    from .exits import secret_trick_set

    secret_trick_set(state, player_index, trick_id, value)


def _treasure_collected(state: GameState, player_index: int) -> None:
    """0x519F0-0x519F8 -- credit one treasure to the player who took it.

    ``player_treascount`` (0x904A50) is the treasure factor of the per-player
    level-end bonus (0x4D57E), so a pickup has to name its collector rather than
    only bumping the level total.  WP-15 owns that counter and exposes
    ``exits.treasure_collected`` as its single write site; that routine raises
    ``player_treascount[p]`` *and* ``level_treasures``, which is why this arm no
    longer touches the total itself.

    Function-local import for the same reason ``player_exit_sequence`` uses one:
    exits.py re-enters this module for the post-transition respawn.

    0x519C2/0x519CE/0x519DA -- the three objective codes that share the
    ``addq.b #1`` at 0x519EC -- are part of the same ROM block and are reported
    by ``exits.treasure_collected`` itself, so this arm must not repeat them or
    a "collect six treasures" task would finish in three pickups.
    """
    from .exits import treasure_collected

    treasure_collected(state, player_index)


def player_exit_sequence(state: GameState, player_index: int,
                         exit_mob_slot: int = 0,
                         exit_type: int = int(MazeObjIds.EXIT)) -> None:
    """Exit-tile interaction hook (§4.6): delegate to WP-15's real
    ``exits.player_exit_sequence`` (0x52B40), which drives the level advance.

    Function-local import to avoid an import cycle (exits.py re-enters players
    for the post-transition respawn).
    """
    from .exits import player_exit_sequence as _exit_sequence
    _exit_sequence(state, player_index, exit_mob_slot, exit_type)


def maze_convert_walls_to_exits(state: GameState) -> int:
    """0x5E80C -- the escape timeout's all-walls-become-exits conversion.

    Verified body (0x5E80C-0x5E866): scan MOB slots 0x20-0x3FF and convert a
    slot when either

      * ``mob_picture == 0x20F6`` -- the movable-wall base picture; or
      * ``mob_picture == 0x8000`` -- the generic solid-wall marker -- and its
        object type is not 0x3F (FORCEFIELDHUB, excluded at 0x5E844),

    by calling ``mob_place_tile(slot, 0x10)``, i.e. replacing the record with
    an EXIT.  Returns 1 when at least one slot was converted, else 0 (§08
    known-issues: this routine returns an ordinary 1, not -1).

    Placement here mirrors WP-3's ``maze_place_object``: EXIT is a
    ``PICTURE_MARKER`` type, so it is created with picture 0 and draws through
    its own animated MOB.  The wall record is cleared first because a wall may
    already be linked into the depth chain and a slot can only be linked once.
    """
    converted = 0
    for slot in range(FIRST_PLAYABLE_SLOT, 0x400):
        picture = state.mobs.picture[slot]
        if picture == _WALL_PICTURE:
            if state.mobs.obj_type(slot) == int(MazeObjIds.FORCEFIELDHUB):
                continue          # 0x5E844: forcefields survive the escape
        elif picture != _MOVABLE_WALL_PICTURE:
            continue

        state.mobs.unlink_and_clear(slot)
        x = (slot & 0x1F) << 4
        y = (slot >> 5) << 4
        state.mobs.create(
            slot, tile=0, hpos=encode_hpos(x), vpos=encode_vpos_at_y(y),
            obj_type=int(MazeObjIds.EXIT),
        )
        from ..maze import set_cell_descriptor

        set_cell_descriptor(state, slot, int(MazeObjIds.EXIT))
        converted = 1

        # The ROM releases the VBLANK semaphore every 64 slots (0x5E828) so a
        # full-table scan cannot tear the display.
        if (slot & 0x3F) == 0:
            state.vblank_flag = 0
    return converted


def player_create_shot(state: GameState, player_index: int) -> None:
    """0x53666 -- spawn a player shot in the player's fixed channel (§26, N-02).

    Each player owns one shot channel (slot ``player_index + 1``, in
    ``SLOT_PLAYER_SHOTS`` = slots 1-4). A new shot is created only while that
    channel is free (``picture == 0``), so a held Fire button produces one shot
    at a time -- the channel is re-armed when the live shot expires or hits
    (``main_handle_shots``, WP-7).

    Spawn picture and position are the ROM's, not placeholders:

      * ``mob_picture`` = ``player_shot_picture_tbl[character * 8 + facing]``
        (0x58B8A, read at 0x536EA);
      * ``mob_hpos`` = firing player's X + ``shot_spawn_hpos_tbl[facing]``
        (0x5BAB0) with palette ``0x0C + player`` (0x5371C);
      * ``mob_vpos`` = firing player's Y + ``shot_spawn_vpos_tbl[facing]``
        (0x5BAC0) with the 2x2-tile size field the ROM writes as 9 (0x53768).

    Facing indexes those tables through ``_PORT_DIR_TO_ROM_DIR``.  Motion,
    lifetime and hit resolution stay WP-7's.
    """
    player = state.players[player_index]
    shot_slot = player_index + SLOT_PLAYER_SHOTS.start   # slots 1-4
    if shot_slot not in SLOT_PLAYER_SHOTS:
        return
    if state.mobs.picture[shot_slot] != 0:               # channel busy: one at a time
        return

    base_h = position_field(state.mobs.hpos[player.mob_slot])
    base_v = position_field(state.mobs.vpos[player.mob_slot])
    port_dir = player.direction & 0x07
    rom_dir = _PORT_DIR_TO_ROM_DIR[port_dir]
    character = player.character & 0x03

    state.mobs.picture[shot_slot] = _PLAYER_SHOT_PICTURE[character * 8 + rom_dir]
    state.mobs.hpos[shot_slot] = (
        base_h + _SHOT_SPAWN_DH[rom_dir]
        + _SHOT_PALETTE_BASE + player_index
    ) & 0xFFFF
    state.mobs.vpos[shot_slot] = (
        base_v + _SHOT_SPAWN_DV[rom_dir]
        + (((_SHOT_TILE_WIDTH - 1) & 0x07) << 3)
        + ((_SHOT_TILE_HEIGHT - 1) & 0x07)
    ) & 0xFFFF
    state.shot_direction[player_index] = rom_dir
    from .shots import shot_velocity

    vx, vv = shot_velocity(state, player_index, rom_dir)
    state.shot_dx[shot_slot] = vx >> POS_SHIFT
    state.shot_dy[shot_slot] = vv >> POS_SHIFT
    state.shot_lifetime[shot_slot] = 0
    _sound_play(state, _PLAYER_SHOT_SOUND[character])
    if player.supershot > 0:
        player.supershot = (player.supershot - 1) & 0xFF


def player_lowhealth(state: GameState, player_index: int) -> None:
    """0x487CA -- the spoken low-health warning (§4.3).

    Call sites: main_health_countdown (0x46794, on a drain tick with health
    below 200) and player_damage_sample_update (0x50EC6).  Verified body:

      1. return immediately when ``player_lowhealth_spoken[p]`` is set
         (0x487DE) or ``player_respawn_speech_timer[p]`` is >= 0 (0x487F0) --
         the latch makes the warning one-shot per life, the timer spaces
         repeats after the latch is cleared;
      2. the "ALL YOUR POWERS WILL BE LOST!" phrase (entry 3) needs all three
         of: a non-zero ``player_powers & 0x00FF`` (0x4880A, a longword AND
         that keeps only the low byte), ``getrandom(8) > 3`` (0x4881C), and
         more than one power bit set among bits 0-7 (0x4884A);
      3. otherwise the phrase is ``getrandom(3)`` -> entries 0-2 (0x4885A);
      4. the chosen phrase is *preceded* by
         ``speech_charname_tbl[character + player * 4]`` (0x596F6), so the
         spoken sentence is two commands (0x48884 then 0x4889C);
      5. the latch is set and the timer reloads with 0x708 (0x488AA/0x488B8).

    05_data_reference's ``character_lowhealth_speech`` entry records the same
    Contradicted-and-corrected finding: the phrase index is *not* the
    character.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return
    if state.player_lowhealth_spoken[player_index]:
        return
    if state.player_respawn_speech_timer[player_index] >= 0:
        return

    player = state.players[player_index]
    phrase = None
    if player.powers & 0x00FF:                      # 0x4880A
        if state.getrandom(8) > 3:                  # 0x4881C: subq #3, ble skip
            bits = sum(1 for b in range(8) if player.powers & (1 << b))
            if bits - 1 > 0:                        # 0x4884A: more than one power
                phrase = 3
    if phrase is None:
        phrase = state.getrandom(3)                 # 0x4885A

    index = (player.character & 0x03) + player_index * 4
    _sound_play(state, _SPEECH_CHARNAME_TBL[index])         # 0x48884
    _sound_play(state, _CHARACTER_LOWHEALTH_SPEECH[phrase])  # 0x4889C
    state.player_lowhealth_spoken[player_index] = 1
    state.player_respawn_speech_timer[player_index] = _LOWHEALTH_SPEECH_TIMEOUT


# =============================================================================
# Transporters (§4.6, §7.2) -- player_tport and its three screening leaves
# =============================================================================

def _tport_pos_table(state: GameState) -> list[int]:
    """``tport_pos_table`` (0x910700) / ``level_tport_count`` (0x904B84).

    Level setup fills that word array with every transporter's maze slot; the
    port has no such array, but the slot number *is* the cell address, so an
    ascending scan of the MOB table reproduces the same list in the same order.
    """
    return [
        slot for slot in range(FIRST_PLAYABLE_SLOT, 0x400)
        if state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER)
    ]


def _tile_on_screen_test(state: GameState, slot: int) -> bool:
    """0x5E584 ``tile_on_screen_test`` -- is a maze slot inside the viewport?

    The ROM works in the native <<7 position domain against the two hardware
    scroll
    shadows: horizontally ``(col * 16 - pf_hscroll)`` must be within 0..0xD8
    pixels (0x6C00 >> 7), vertically the flipped row origin minus
    ``scroll_vpos_origin`` (0x904AC4 = ``(0x108 - pf_vscroll_lo) << 7``) minus
    8 px must be within 0..0xE0 (0x7000 >> 7).  Both comparisons are unsigned,
    so a tile "behind" the camera fails the same test.  Restated in whole
    pixels here; the vertical form collapses to ``scroll_y <= row * 16 <=
    scroll_y + 224``.  Returns True inside the window (the ROM returns -1).
    """
    col = slot & 0x1F
    row = (slot >> 5) & 0x1F
    dx = (col * 16 - state.scroll_x) & 0x1FF
    if dx > 0xD8:
        return False
    dy = (row * 16 - state.scroll_y) & 0x1FF
    return dy <= 0xE0


def tport_check_dest(state: GameState, destination_slot: int,
                     player_index: int) -> int:
    """0x50ADE -- 1 for a blocked landing cell, 0 for a usable one (§7.2).

    Verified body: blocked when the picture is the solid-wall marker 0x8000
    (0x50B20) or 1 (0x50B28, the reserved marker), when the cell already holds
    another player's sprite (hpos palette nibble >= 0x0C and not this player's
    ``0x0C + player``; 0x50B2E-0x50B42), for wall types 0x3E/0x3C/0x2F
    (0x50B46-0x50B5A), and for doors 0x0D/0x0E when the player holds no key
    (0x50B5E-0x50B76).
    """
    picture = state.mobs.picture[destination_slot]
    obj_type = state.mobs.obj_type(destination_slot)
    palette = state.mobs.hpos[destination_slot] & 0x0F

    if picture == _WALL_PICTURE:
        return 1
    if picture == 1:
        return 1
    if palette >= _SHOT_PALETTE_BASE and palette != _SHOT_PALETTE_BASE + player_index:
        return 1
    if obj_type in (0x3E, 0x3C, 0x2F):
        return 1
    if obj_type in (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT)):
        if state.players[player_index].keysnum == 0:
            return 1
    return 0


def nearby_mob_clearance_test(state: GameState, slot: int,
                              player_index: int) -> bool:
    """0x50D14 -- True when no *other* player is standing next to ``slot``.

    The ROM walks the eight neighbours of ``slot`` (delta tables 0x578A2 /
    0x578B2) and rejects the cell when a neighbour holds a live MOB whose hpos
    palette nibble is >= 0x0C (a player sprite) other than this player's own,
    and whose position is within 0x7C0 of the cell origin -- 15.5 px in the
    native <<7 domain.

    That neighbour scan is exactly what a migrating hero record makes possible:
    ``active_mob_ids`` names the cell the hero occupies, so the eight cells
    around a landing site are the only ones another hero could be standing in.
    """
    ref_h = ((((slot & 0x1F) * 16 - 4) << POS_SHIFT)) & 0xFFFF   # 0x50D2E
    ref_v = (native_v(((slot >> 5) & 0x1F) * 16) << POS_SHIFT) & 0xFFFF  # 0x50D42
    own_palette = _SHOT_PALETTE_BASE + player_index
    for direction in range(8):
        cell = _direction_neighbor(slot, direction)
        if state.mobs.picture[cell] == 0:
            continue
        palette = state.mobs.hpos[cell] & 0x0F
        if palette < _SHOT_PALETTE_BASE or palette == own_palette:
            continue
        if (_wrapped_position_delta(state.mobs.hpos[cell], ref_h) < _PROBE_OVERLAP
                and _wrapped_position_delta(
                    state.mobs.vpos[cell], ref_v) < _PROBE_OVERLAP):
            return False
    return True


def handle_tport(state: GameState, source_slot: int, player_index: int) -> None:
    """0x47CFE -- put the transporter arrival sparkle on the player's channel.

    The ROM claims the *fixed* per-player slot ``player_index + 0x19`` out of
    the five transporter-animation MOBs (§1.2, slots 25-29), clearing whatever
    was there, then copies the source MOB's tile-aligned position with the same
    +1 / +0x12 nudges the rest of the effect placement uses (0x47D66/0x47D8A)
    and installs picture 0x1DCF (0x578F2).

    Kept local because the ROM's fixed per-player allocation is not the shared
    0x0D-0x10 pool used by shot explosions.
    """
    effect_slot = player_index + SLOT_TPORT_ANIMS.start   # 0x47D10: +0x19
    if effect_slot not in SLOT_TPORT_ANIMS:
        return
    if state.mobs.picture[effect_slot] != 0:              # 0x47D1E
        state.mobs.unlink_and_clear(effect_slot)
    state.mobs.picture[effect_slot] = _TPORT_ARRIVAL_PICTURE
    state.mobs.hpos[effect_slot] = (
        position_field(state.mobs.hpos[source_slot]) + 1
    ) & 0xFFFF
    state.mobs.vpos[effect_slot] = (
        position_field(state.mobs.vpos[source_slot]) + 0x12
    ) & 0xFFFF
    state.mobs.insert(effect_slot, depth_key=source_slot)  # 0x47D9E


def player_tport(state: GameState, player_index: int,
                 tile_mob_slot: int) -> int:
    """0x50224 -- a player steps onto a transporter (§4.6, §7.2).

    ROM signature is ``player_tport(uint16 transporter_pos, uint16
    player_index)``; the port keeps its existing Python argument order.
    Returns 0 when the teleport is aborted for too few clear landing cells and
    -2 once the move is performed -- the contract
    ``tport_forcefield_contracts.csv`` records for its consumer at 0x513CE.

    Verified body:

      1. record the source in ``player_tport_route_state[p]`` (0x5023E);
      2. ``player_powers & 0x800`` skips destination discovery entirely and
         lands the player back around this same pad (0x5025A -> 0x503AA);
      3. secret trick 0x56 ORs ``1 << tport_find_id(source)`` into
         ``secret_tricks_flags[p]`` (0x5027E);
      4. scan ``tport_pos_table`` up to ``level_tport_count``, skipping the
         source and anything off screen, and keep the nearest by wrap-aware
         Manhattan distance seeded at 0x80; an exact tie only replaces the
         incumbent while ``tport_cycle_dir`` is negative (0x50374);
      5. with no destination found, the source pad is the destination (0x503AA);
      6. count the clear landing cells among the destination's eight
         neighbours: row 0 and out-of-range are rejected (0x503E8/0x503F0), a
         cell that is already another in-flight teleport's destination is
         rejected (0x503F8-0x5045C), then ``tile_on_screen_test``,
         ``tport_check_dest`` and ``nearby_mob_clearance_test`` must all pass;
      7. the required count is 1 plus every other player already bound for
         this same destination with a non-negative phase (0x504BA-0x504E6);
         fewer clear cells than that aborts with 0 (0x504EC);
      8. otherwise ``handle_tport`` spawns the arrival sparkle, the phase/type
         words are armed, sound 0x28 plays, and the landing cell is stored in
         ``player_tile_or_tport_dest[p]`` (0x904BD8 -- WP-13's
         ``player_tile_pos``).

    Port note: the ROM hands the motion to the per-frame transition machine and
    so does this port.  ``player_tport`` is purely the producer -- it picks the
    pad and the landing cell, arms the phase, and returns.  WP-14's
    ``main_score_update`` loop 2 then runs the milestones and this file's
    ``tport_player_move`` performs the relocation at step 0x0B.  The ROM's own
    choice *among* the clear landing cells (0x50578-0x505FA) compares two
    registers, ``a1`` and ``a4``, that the routine never initialises -- a
    genuine ROM defect that cannot be reproduced without modelling leftover
    register state -- so the port takes the first clear cell in the ROM's own
    scan order, preferring the four diagonals its final loop restricts itself
    to.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return 0
    player = state.players[player_index]
    source = tile_mob_slot

    state.player_tport_route_state[player_index] = source        # 0x5023E

    powers_gate = bool(player.powers & _POWER_TRANSPORT)         # 0x50252
    if not powers_gate and state.secret_trick_id == 0x56:        # 0x5025E
        pads = _tport_pos_table(state)
        if source in pads:
            state.secret_tricks_flags[player_index] |= 1 << (
                pads.index(source) + 1
            )

    destination = 0
    if not powers_gate:
        best = 0x80                                              # 0x502AA
        for candidate in _tport_pos_table(state):
            if candidate == source:                              # 0x502CA
                continue
            if not _tile_on_screen_test(state, candidate):       # 0x502D8
                continue
            dcol = abs((candidate & 0x1F) - (source & 0x1F))
            if state.wrap_h and dcol >= 0x10:                    # 0x50302
                dcol = 0x20 - dcol
            drow = abs(((candidate >> 5) & 0x1F) - ((source >> 5) & 0x1F))
            # 0x50332 tests LFLAG4 bit 5 -- the *horizontal* wrap flag -- for
            # the vertical term too.  Mirrored rather than "fixed".
            if state.wrap_h and drow >= 0x10:
                drow = 0x20 - drow
            distance = dcol + drow
            if distance < best or (distance == best and state.tport_cycle_dir < 0):
                best = distance
                destination = candidate

    if destination == 0:                                         # 0x503A4
        destination = source

    clear_cells: list[int] = []
    for direction in range(8):                                   # 0x503B4
        cell = _direction_neighbor(destination, direction)
        if cell < 0x20 or cell >= 0x400:                         # 0x503E8/0x503F0
            continue
        if any(state.player_tport_type[i] == 0
               and state.player_tile_pos[i] == cell
               and state.player_tport_phase[i] >= 0
               for i in range(NUM_PLAYERS)):                     # 0x503F8-0x5045C
            continue
        if not _tile_on_screen_test(state, cell):                # 0x50466
            continue
        if tport_check_dest(state, cell, player_index) != 0:     # 0x50480
            continue
        if not nearby_mob_clearance_test(state, cell, player_index):  # 0x5049A
            continue
        clear_cells.append(cell)

    required = 1                                                 # 0x504B4
    for i in range(NUM_PLAYERS):
        # The ROM does not exclude the arriving player here; its own type word
        # is still zero at this point, so it never counts itself.
        if (state.player_tport_type[i] == destination
                and state.player_tport_phase[i] >= 0):
            required += 1
    if len(clear_cells) < required:                              # 0x504E8
        return 0

    _sound_play(state, 0x28)                                      # 0x50534

    # 0x50578-0x50606 picks the landing cell; the four diagonals are the only
    # candidates it considers (its index runs 1, 3, 5, 7).
    diagonal_cells = {_direction_neighbor(destination, d) for d in (1, 3, 5, 7)}
    diagonals = [c for c in clear_cells if c in diagonal_cells]
    landing = diagonals[0] if diagonals else clear_cells[0]

    # 0x509E4: the "visit every transporter" objective records *both* ends of
    # the hop -- the source pad was ORed in at 0x5027E, and the pad just
    # arrived at goes in here, gated on the same trick and on the destination
    # actually resolving to a known pad (0x509EC ``tst.w d6``).
    _tport_visit_pad(state, player_index, destination)

    # 0x50A18-0x50A66: before handing over to the transition, the arriving
    # player interacts with all four cells around the destination -- this is
    # why a transporter can drop you straight onto a potion, and how the two
    # transportability objectives are won.
    tport_arrival_interact(state, destination, player_index)

    # 0x504F2-0x5052A / 0x50606: arm the transition and hand over.  The hero
    # does not move on this frame -- loop 2 dissolves it, this file's
    # tport_player_move relocates it at the move milestone, and loop 2 re-forms
    # it at the destination.
    tport_transition_arm(state, player_index, destination, landing)
    return -2                                                     # 0x5060A


def _tport_visit_pad(state: GameState, player_index: int, pad_slot: int) -> None:
    """0x5027E / 0x509E4 -- mark one transporter pad as visited.

    Trick 0x56 wants a player to have stood on every pad on the level, so its
    progress byte is a *bitmask* of pad indices rather than a count.  That is
    neither of WP-15's two hook shapes, so the OR stays here; the guard is the
    same ``trick_tasknum`` compare the API applies.
    """
    if state.secret_trick_id != _TRICK_VISIT_TPORTS:
        return
    pads = _tport_pos_table(state)
    if pad_slot in pads:
        flags = state.secret_tricks_flags
        flags[player_index] |= 1 << (pads.index(pad_slot) + 1)


def tport_arrival_interact(state: GameState, dest_slot: int,
                           player_index: int) -> None:
    """0x50BB8 -- interact with the four cells around a transporter landing.

    ``player_tport`` calls this four times (0x50A1E/0x50A36/0x50A4E/0x50A66),
    once per neighbour-fetch callback (0x406B6, 0x40732, 0x4083A, 0x408A0).
    Each call finds the mob in that cell and, unless it is rejected, runs it
    through ``player_tile_interact`` (0x50C96) exactly as walking into it
    would.  Three rejects, in ROM order:

      * no mob there at all (0x50BD8, the callback returned negative);
      * ``mob_hpos & 0x0F >= 0x0C`` -- mid-cell, so not really in this one
        (0x50BF2, the same sub-tile gate the movement probes use);
      * picture 0x8001 or 0x8000 (0x50C02/0x50C16) -- the two placeholder
        pictures that mean "nothing drawn here".
    """
    for direction in (0, 2, 4, 6):
        cell = _direction_neighbor(dest_slot, direction)
        if cell < 0x20 or cell >= 0x400:
            continue
        # The ROM's callbacks return a MOB slot and reject a negative one
        # (0x50BD8); in this port a maze cell *is* its MOB slot, so the
        # equivalent "nothing there" test is an empty object type.
        if state.mobs.obj_type(cell) == 0:
            continue
        if (state.mobs.hpos[cell] & 0x0F) >= 0x0C:               # 0x50BF2
            continue
        if state.mobs.picture[cell] in (0x8000, 0x8001):         # 0x50C02/0x50C16
            continue
        _tport_landing_trick(state, player_index, cell)          # 0x50C30
        player_tile_interact(state, cell, player_index)          # 0x50C96


def _tport_landing_trick(state: GameState, player_index: int,
                         slot: int) -> None:
    """0x50C30-0x50C52 -- the two "try transportability" objectives.

    Both are decided on the spot rather than accumulated: being dropped next
    to the right monster writes this player straight into ``secret_winner``
    (0x50C52 ``move.b d2,secret_winner``), no progress byte involved.  Trick 1
    wants MONST_ACID (0x19) and trick 2 wants MONST_DEATH (0x18) -- the two
    things you could never survive walking into.
    """
    trick = state.secret_trick_id
    obj_type = state.mobs.obj_type(slot)
    if trick == _TRICK_TRANSPORT1 and obj_type == int(MazeObjIds.MONST_ACID):
        state.secret_winner = player_index
    elif trick == _TRICK_TRANSPORT2 and obj_type == int(MazeObjIds.MONST_DEATH):
        state.secret_winner = player_index


# =============================================================================
# Door helper (only call site: main_move_players at 0x4ACFC)
# =============================================================================

def open_timed_doors(state: GameState) -> None:
    """0x47FAC -- remove every DOOR_HORIZ/DOOR_VERT and play sound 0x12.

    Called once per level when the door-idle threshold is exceeded (§4.1
    post-loop).  Sole call site at 0x4ACFC, within main_move_players -- which
    is why the entry point lives here even though the sweep itself is
    living-maze work.  The body is WP-11's ``maze_objects.open_timed_doors``:
    the two were byte-for-byte the same routine, and one of them had to go.

    That implementation carries the two details worth keeping: the ROM sweeps
    MOB slots directly rather than walking the depth chain, and it plays
    "Doors Open" **only when it actually removed something** (the flag test at
    0x47FF0 gates the ``pea.l $12`` at 0x47FF4).
    """
    from .maze_objects import open_timed_doors as _open_timed_doors

    _open_timed_doors(state)


def door_open_start(state: GameState, door_slot: int, player_index: int) -> None:
    """0x51E80 -- start the two opening fronts for a door a key just unlocked.

    The ROM gives every player its own pair of the eight front channels at
    ``door_endpoint_pos``/``door_endpoint_dir`` (0x904A76/0x904A86), indexed
    ``player * 2`` and ``player * 2 + 1``, seeds both with the door's own cell,
    and points them in opposite directions along the door line: up/down for a
    vertical door (0x51ED4/0x51EE2) and left/right for a horizontal one
    (0x51F20/0x51F30).  It then calls ``main_open_doors`` (0x51F9E) so the
    first cell of each front opens on the same frame.

    Both the front records and their animator belong to WP-11, so this only
    seeds them and hands over; the picture ranges that decide how far a front
    travels stay that module's business.
    """
    from .maze_objects import main_open_doors

    if not 0 <= player_index < NUM_PLAYERS:
        return
    channel = player_index * 2
    picture = state.mobs.picture[door_slot]
    obj_type = state.mobs.obj_type(door_slot)
    if picture >= 0x9D7C:
        directions = (0, 2)      # up / down along a vertical door
    elif picture >= 0x9D3C:
        directions = (3, 1)      # left / right along a horizontal door
    else:
        # Class-1 junction picture: the ROM scans both axes, in object-type
        # order, and records at most two immediate branches.
        horizontal = ((-1, 3), (1, 1))
        vertical = ((-0x20, 0), (0x20, 2))
        scans = (
            (vertical, horizontal)
            if obj_type == int(MazeObjIds.DOOR_VERT)
            else (horizontal, vertical)
        )
        found = []
        for scan in scans:
            for offset, direction in scan:
                candidate = door_slot + offset
                if offset in (-1, 1):
                    candidate = (
                        (door_slot & 0x3E0)
                        | ((door_slot + offset) & 0x1F)
                    )
                if (
                    FIRST_PLAYABLE_SLOT <= candidate < len(state.mobs.picture)
                    and state.mobs.obj_type(candidate) in (
                        int(MazeObjIds.DOOR_HORIZ),
                        int(MazeObjIds.DOOR_VERT),
                    )
                ):
                    found.append(direction)
                    if len(found) == 2:
                        break
            if len(found) == 2:
                break
        directions = tuple(found)

    state.door_endpoint_pos[channel:channel + 2] = [0, 0]
    state.door_endpoint_dir[channel:channel + 2] = [0, 0]
    for offset, direction in enumerate(directions):
        state.door_endpoint_pos[channel + offset] = door_slot
        state.door_endpoint_dir[channel + offset] = direction
    main_open_doors(state)       # 0x51F9E


def _door_unlock(state: GameState, door_slot: int, player_index: int) -> None:
    """The shared body of the ROM's key-opens-a-door path (0x51DAE-0x51DE4).

    Resets the escape timer, spends the key, refreshes the inventory, opens the
    cell the player is standing against, starts the two fronts that walk the
    rest of the door line, and plays "Doors Open".

    The ROM leaves the touched cell to the fronts because its own traversal has
    already stepped the player through it; this port's collision model reads the
    cell directly, so the cell is cleared here as well.
    """
    player = state.players[player_index]
    state.escape_timer = 0                          # 0x51DAE: clr.w (a3)
    player.keysnum = (player.keysnum - 1) & 0xFF    # 0x51DB8
    player_inv_update(state, player_index)          # 0x51DC2
    door_open_start(state, door_slot, player_index)  # 0x51DD8
    from .maze_objects import _remove_door_slot

    _remove_door_slot(state, door_slot)
    _sound_play(state, 0x12)                        # 0x51DDE: "Doors Open"


# =============================================================================
# WP-6 helpers (§4.3, §4.4, §4.6, §4.7)
# =============================================================================

def player_add_score_with_mult(state: GameState, player_index: int,
                                base_score: int) -> None:
    """0x5214C -- add ``base_score × player.bonusmult`` to the score (§4.7).

    Writes the 32-bit longword at 0x904990 and sets score-redraw bit 0.
    Does **not** call ``highscore_check`` (Contradicted and corrected, §4.7).
    """
    player = state.players[player_index]
    # Score is a 32-bit longword (§4.3 TRAP 2); Python ints do not overflow.
    player.score += base_score * player.bonusmult
    state.score_dirty[player_index] = 1     # score-redraw bit 0 (§4.7)


def player_tile_interact(state: GameState, tile_mob_slot: int,
                          player_index: int) -> int:
    """0x511AC -- dispatch on tile type and apply effect (§4.6).

    Returns -1 when handled/consumed, 0 when unhandled.
    Sound calls use a fixed sound_play pointer in A2 (see player_runtime_contracts.csv).

    The ROM also clears the escape timer (0x9048C6, ``a3`` here) on each of the
    twelve handled branches -- "frames since forward progress".  Only the door
    branch does so below, because that is the branch this port has reworked;
    the other eleven are recorded here so the finding is not lost.
    """
    if tile_mob_slot == 0:
        return 0

    player = state.players[player_index]
    obj_type = state.mobs.obj_type(tile_mob_slot)

    # ── Food ──────────────────────────────────────────────────────────────────
    # 0x51ADC-0x51CFE. The picture distinguishes ordinary, adaptive and poison
    # food. The prior two-way test treated level-1 FOOD000 as poison.
    if obj_type in (int(MazeObjIds.FOOD_DESTRUCTABLE),
                    int(MazeObjIds.FOOD_INVULN)):
        picture = state.mobs.picture[tile_mob_slot] & 0x7FFF
        if picture == _POISONED_FOOD_PICTURE:
            _poisoned(state, player_index)              # 0x51C40-0x51CB4
        else:
            health_gain = 100
            if picture == _RANDOM_FOOD_PICTURE:
                adaptive_index = (player.health & 0xFFFF) % 20
                health_gain = _RANDOM_FOOD_HEALTH[adaptive_index]
                from .shots import playfield_showscore

                playfield_showscore(
                    state, tile_mob_slot, _RANDOM_FOOD_POPUP[adaptive_index],
                )
            player.health += health_gain
            state.player_dizzy_timer[player_index] = 0  # 0x51CDA
            _dialog(state, player_index, _DIALOG_FOOD)  # 0x51CDE, record 0
            _sound_play(state, 0x0D)
            # 0x51D06-0x51D32: once the meal has carried the player back to 200
            # the low-health machinery is stood down -- the cadence timer takes
            # its disabled sentinel and the spoken-warning latch is re-armed.
            # This is where §4.3's "reset to 0xFFFF" lives; main_health_countdown
            # itself never writes it.
            if player.health >= _LOW_HEALTH_THRESHOLD:
                player.state_timer = _STATE_TIMER_DISABLED
                state.player_lowhealth_spoken[player_index] = 0
        # 0x51CEE (wholesome) and 0x51C0C (poisoned) both bump the same byte
        # right after their dialog call, so eating *any* food counts.
        _secret_trick_progress(state, player_index, _TRICK_FOOD)
        state.health_dirty[player_index] = 1             # player_redraw bit 1
        # "Non-destructible" means shots cannot destroy it; collect() deletes
        # both food types after a successful pickup.
        state.mobs.unlink_and_clear(tile_mob_slot)
        return -1

    # ── Key ───────────────────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.KEY):
        # §4.6: keys (sound 0x13).
        player.keysnum = (player.keysnum + 1) & 0xFF
        state.mobs.unlink_and_clear(tile_mob_slot)
        player_inv_update(state, player_index)          # 0x51610
        _dialog(state, player_index, _DIALOG_KEYS)      # 0x51620, record 3
        # 0x514D4: a key counts against "don't be greedy" (keys or potions).
        _secret_trick_progress(state, player_index, _TRICK_NOGREEDY1)
        state.escape_timer = 0                          # 0x514EA: clr.w (a3)
        _sound_play(state, 0x13)                        # 0x514EC/0x514F2
        # 0x514F4-0x514FE: a key is worth 100, through the same
        # multiplier-aware award the treasure arm uses.
        player_add_score_with_mult(state, player_index, _KEY_SCORE)
        return -1

    # ── Potions ───────────────────────────────────────────────────────────────
    # 0x5162E: like food, a potion's *picture* says whether it is poisoned --
    # 0x20FC is the bad one (0x5163A).
    if obj_type in (int(MazeObjIds.POT_DESTRUCTABLE),
                    int(MazeObjIds.POT_INVULN)):
        state.escape_timer = 0                          # 0x5162E: clr.w (a3)
        if state.mobs.picture[tile_mob_slot] == _POISONED_POTION_PICTURE:
            _poisoned(state, player_index)              # 0x51644-0x516C8
            state.health_dirty[player_index] = 1
        else:
            player.potionsnum = (player.potionsnum + 1) & 0xFF
            _sound_play(state, 0x0E)  # potion pickup sound (§11.5 soundcmds)
            player_inv_update(state, player_index)      # 0x51786
            _dialog(state, player_index, _DIALOG_SAVE_POTIONS)  # 0x51796, rec 5
            # 0x5179C: the good-potion path only -- a *poisoned* potion is
            # never picked up, so it cannot make the player greedy.
            _secret_trick_progress(state, player_index, _TRICK_NOGREEDY1)
        # Both records resist shots differently, but both disappear on pickup.
        state.mobs.unlink_and_clear(tile_mob_slot)
        return -1

    # ── Treasure ──────────────────────────────────────────────────────────────
    # Each treasure collected is credited to its collector through WP-15's
    # ``treasure_collected`` (the ROM's write site at 0x519F0-0x519F8), which
    # bumps ``player_treascount`` *and* the level total ``level_treasures``.
    # This arm must not touch ``level_treasures`` itself or the total would be
    # double-counted and the bonus screen would pay for phantom treasure.
    #
    # Order matters: the ROM redistributes the bonus multiplier (0x51A16) and
    # only then awards the score (0x51AC4), so the award uses the *new* value.
    if obj_type == int(MazeObjIds.TREASURE):
        # §4.6: treasure (sound 0x26, calls player_add_score_with_mult).
        from .shots import playfield_showscore

        playfield_showscore(state, tile_mob_slot, 1)
        _treasure_collected(state, player_index)
        _treasure_bonus_multiplier(state, player_index)
        _sound_play(state, 0x26)                       # 0x51AB0
        player_add_score_with_mult(state, player_index, 100)   # 0x51AC4
        state.mobs.unlink_and_clear(tile_mob_slot)
        return -1

    if obj_type == int(MazeObjIds.TREASURE_BAG):
        from .shots import playfield_showscore

        bonus_score = state.special_bonus_score & 0xFFFF
        playfield_showscore(
            state, tile_mob_slot, bonus_score // 1000 + 1,
        )
        _treasure_collected(state, player_index)
        _treasure_bonus_multiplier(state, player_index)
        _sound_play(state, 0x26)
        player_add_score_with_mult(state, player_index, bonus_score)
        state.mobs.unlink_and_clear(tile_mob_slot)
        return -1

    # ── Locked treasure (type 0x2F) ───────────────────────────────────────────
    # Not handled here, deliberately: the second dispatch table (0x511CE + type
    # * 2) sends 0x2F to the unhandled tail at 0x51E60, exactly like an
    # out-of-range type.  A chest is opened by *shooting* it -- shots.py's
    # supershot treasure arm (0x4B80E) owns its destruction -- so walking into
    # one with a key in hand must neither spend the key nor pay out.  Falling
    # through to the tail leaves the player blocked by it, which is the
    # behaviour the ROM has.

    # ── Doors ─────────────────────────────────────────────────────────────────
    if obj_type in (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT)):
        # §4.6: doors (check key count).  0x51DA8: no key means the tile is
        # left unhandled, so the player simply stays blocked.
        if player.keysnum > 0:
            _door_unlock(state, tile_mob_slot, player_index)
            return -1
        return 0

    # ── Transporter ───────────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.TRANSPORTER):
        # 0x513CE consumes player_tport's D0: -2 means the teleport happened,
        # 0 means it was aborted for too few clear landing cells, in which case
        # the tile has not been handled.
        return -1 if player_tport(state, player_index, tile_mob_slot) else 0

    # ── Exit ──────────────────────────────────────────────────────────────────
    if obj_type in (int(MazeObjIds.EXIT), int(MazeObjIds.EXITTO6)):
        # 0x513DA, reached for both 0x10 and 0x11 through the dispatch table at
        # 0x511EC.  Before an exit works, the ROM checks hpos bit 4
        # (0x513E4 ``btst #4,$1(a0,d0.w)``): a set bit means this exit is a
        # *fake*.  Stepping on one shows record 30, removes the illusion and
        # satisfies the "don't be fooled" objective -- but does not exit.
        if state.mobs.hpos[tile_mob_slot] & _FAKE_EXIT_FLAG:
            _dialog(state, player_index, _DIALOG_FAKE_EXIT)   # 0x513F8
            from ..maze import clear_cell_descriptor

            clear_cell_descriptor(state, tile_mob_slot)
            state.mobs.unlink_and_clear(tile_mob_slot)        # 0x51404
            _secret_trick_set(state, player_index, _TRICK_NOFOOLED, 1)
            return -1
        # The tile's obj_type *is* the ROM exit_type (EXIT=0x10, EXITTO6=0x11).
        player_exit_sequence(state, player_index, tile_mob_slot, obj_type)
        return -1

    # ── Stun / trap tiles ─────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.TILE_STUN):
        _clear_floor_marker(state, tile_mob_slot)
        if player.acid_timer == 0:
            if state.mazenum_current < 0x73:
                stun_add = (120, 45, 120, 60)[player.character & 3]
                sound_id = (0x32, 0x34, 0x32, 0x33)[player.character & 3]
            else:
                stun_add = 120
                sound_id = 0x32
            _sound_play(state, sound_id)
            player.stundelay += stun_add
            state.death_touch_timer[player_index] = -player.stundelay
            state.player_fighting_dir[player_index] = 0
            player.hurt_cooldown = 0x12
        _dialog(state, player_index, _DIALOG_STUN_FLOOR)
        _tile_contact_progress(state, player_index)
        return -1

    if obj_type in (int(MazeObjIds.TILE_TRAP1),
                    int(MazeObjIds.TILE_TRAP2),
                    int(MazeObjIds.TILE_TRAP3)):
        # 0x5124C: the trigger becomes floor, then every matching trigger and
        # its type-7/8/9 wall group is dropped by maze_place_object_types.
        _clear_floor_marker(state, tile_mob_slot)
        if _drop_trap_walls(state, obj_type):
            _sound_play(state, 0x27)
        _dialog(state, player_index, _DIALOG_TRAP)
        _tile_contact_progress(state, player_index)
        return -1

    # ── IT tile ───────────────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.MONST_IT):
        # §4.6: IT tile (sound 0x35).
        _sound_play(state, 0x35)
        return -1

    # ── Acid puddle ───────────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.MONST_ACID):
        # §4.6: acid puddle (sound 0x36, applies acid slow).
        player.acid_timer = max(player.acid_timer, 180)  # ~3 s at 60 Hz
        _sound_play(state, 0x36)
        return -1

    # ── Power-up tiles ────────────────────────────────────────────────────────
    # 0x517BA-0x518B0, one arm per type, reached through the tile jump table at
    # 0x5122A.  Every arm pushes its power-up ID, calls
    # ``player_give_item_with_message`` (0x4C72A) to OR
    # ``powerup_bit_masks[id]`` into ``player_powers``, arms whatever countdown
    # that power uses, plays sound 0x26 and clears the escape timer.
    if obj_type in POWERUP_ITEM_ID:
        # 0x4C762: an already-owned bit makes the grant return 0 without
        # re-ORing or repeating the speech, but the arm's own side-effects
        # below still run -- a second invisibility potion re-arms the timer.
        _player_give_item(state, player_index, obj_type)
        if obj_type == int(MazeObjIds.POWER_INVIS):
            state.player_invis_timer[player_index] = _INVIS_TIMER_LOAD   # 0x517D4
        elif obj_type == int(MazeObjIds.POWER_REPULSE):
            state.player_repulse_timer[player_index] = (
                _REPULSE_TIMER_INIT[player.character & 0x03]             # 0x5181A
            )
        elif obj_type == int(MazeObjIds.POWER_SUPERSHOT):
            # 0x51874 ``addi.b #$b`` -- eleven charges, not one, and they add.
            player.supershot = (player.supershot + _SUPERSHOT_CHARGES) & 0xFF
        elif obj_type == int(MazeObjIds.POWER_INVULN):
            # 0x5189E arms the 0x905F40 countdown this port calls ``acid_timer``
            # -- the same word the acid puddle uses (0x512D0) and the same one
            # main_move_players drains health from every eighth frame
            # (0x4A838-0x4A85E).  Its expiry clears this power's bit (0x4A880).
            player.acid_timer = _INVULN_TIMER_LOAD
            # 0x518B2: this is the "don't use invulnerability" objective's
            # tell.  Unlike every other trick site it *assigns* 1 rather than
            # bumping (0x518C8 ``move.b #$1``), so picking up a second one
            # cannot push the byte past the value the check expects.
            _secret_trick_set(state, player_index, _TRICK_NOUSEINVUL, 1)
        _sound_play(state, 0x26)                     # 0x5187A/0x51834/0x518A8
        state.escape_timer = 0                       # 0x51882: clr.w (a3)
        state.mobs.unlink_and_clear(tile_mob_slot)
        player_inv_update(state, player_index)
        return -1

    # ── Hidden pot ────────────────────────────────────────────────────────────
    # 0x518D2: the arm reads the tile's picture, derives a power-up ID from it
    # and offers that power first (0x518F2 ``player_give_item_with_message``);
    # only when nothing was granted (0x5191E ``tst.w d5``) does it fall through
    # to the plain potion this port models.
    if obj_type == int(MazeObjIds.HIDDENPOT):
        player.potionsnum = (player.potionsnum + 1) & 0xFF
        _sound_play(state, 0x0E)
        state.mobs.unlink_and_clear(tile_mob_slot)
        player_inv_update(state, player_index)
        # 0x518FA/0x51908: two *task* codes share this site, either of which
        # bumps the byte (0x51904 ``beq`` falls into the same ``addq.b #1``).
        # These are objective codes from the 0x50-0x5D band, not the 1-17
        # trick numbering, so they are passed as literals.
        _secret_trick_progress(state, player_index, _TASK_HIDDENPOT_A)
        _secret_trick_progress(state, player_index, _TASK_HIDDENPOT_B)
        return -1

    return 0  # unhandled tile type


def _clear_floor_marker(state: GameState, slot: int) -> None:
    from ..maze import clear_cell_descriptor

    clear_cell_descriptor(state, slot)
    state.mobs.unlink_and_clear(slot)


def _drop_trap_walls(state: GameState, trap_type: int) -> bool:
    """0x5E7A6 -- replace this trap's remaining triggers and wall group."""
    wall_type = trap_type - 3
    removed = False
    for slot in range(FIRST_PLAYABLE_SLOT, 0x400):
        if state.mobs.obj_type(slot) not in (wall_type, trap_type):
            continue
        _clear_floor_marker(state, slot)
        removed = True
    return removed


def _tile_contact_progress(state: GameState, player_index: int) -> None:
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0
    from .shots import _dragon_proximity

    _dragon_proximity(state, state.players[player_index].mob_slot)


def _player_give_item(state: GameState, player_index: int, obj_type: int) -> bool:
    """0x4C72A ``player_give_item_with_message`` -- OR one power bit in.

    Verified body: the power-up ID indexes ``powerup_bit_masks`` (0x59B64,
    ``constants.POWERUP_BIT_MASKS``); if the player already owns that bit the
    routine returns 0 without touching anything (0x4C762), otherwise it ORs the
    mask into ``player_powers`` (0x4C77C) and, for the high-byte pickups, speaks
    ``powerup_speech_ids[id]`` (0x59B7C) and raises a one-shot dialog latch.

    Returns True when the bit was newly granted.  The message box and its speech
    are WP-14 alpha work; the bit is the part this file owns.
    """
    item_id = POWERUP_ITEM_ID.get(obj_type)
    if item_id is None:
        return False
    mask = POWERUP_BIT_MASKS[item_id]
    player = state.players[player_index]
    if player.powers & mask:                 # 0x4C760-0x4C766
        return False
    player.powers |= mask                    # 0x4C77C
    speech = _POWERUP_SPEECH_IDS[item_id]
    if speech:                               # a zero entry suppresses speech
        _sound_play(state, speech)
    return True


def _treasure_bonus_multiplier(state: GameState, player_index: int) -> None:
    """0x51A16-0x51AAE -- the treasure arm's bonus-multiplier redistribution.

    ``player_bonusmult`` (0x90490E) is a 16-bit word per player, and a treasure
    moves it around the table rather than simply raising it:

      1. solo play changes nothing -- the bump is skipped outright when
         ``level_players_active`` is 1 (0x51A16);
      2. otherwise the collector gains **2** (0x51A2A, ``addq.w #2``);
      3. the collector is then clamped to **2 x level_players_active**
         (0x51A3E-0x51A60), an unsigned compare that writes the cap back only
         when the value exceeds it -- so the multiplier a player can hoard is
         bounded by how many players are on the level;
      4. every *other* player who is still alive (non-zero health) and above 1
         loses one (0x51A64-0x51AA8), floored at 1 by the ``bls`` test, and has
         its panel redraw bit raised (0x51AA2).

    Called before the score award, because ``player_add_score_with_mult`` at
    0x51AC4 multiplies by the value this leaves behind.
    """
    if state.mazenum_current in _TREASURE_ROOM_MAZES:
        # 0x519FE-0x51A12: the treasure-room band branches away before the
        # multiplier block and pays out on the bonus screen instead.
        return

    player = state.players[player_index]
    active = state.level_players_active
    changed = set()

    if active != 1:                                        # 0x51A16
        player.bonusmult = (player.bonusmult + 2) & 0xFFFF  # 0x51A2A
        changed.add(player_index)

    cap = (active * 2) & 0xFFFF                            # 0x51A46
    if player.bonusmult > cap:                             # 0x51A48, unsigned
        player.bonusmult = cap                             # 0x51A60
        changed.add(player_index)

    for other in range(NUM_PLAYERS):                       # 0x51A64
        if other == player_index:                          # 0x51A66
            continue
        victim = state.players[other]
        if victim.health == 0:                             # 0x51A74
            continue
        if victim.bonusmult <= 1:                          # 0x51A84
            continue
        victim.bonusmult = (victim.bonusmult - 1) & 0xFFFF  # 0x51A96
        state.health_dirty[other] = 1                      # 0x51AA2
        changed.add(other)
    for changed_player in sorted(changed):
        player_inv_update(state, changed_player)


def player_damage_sample_update(state: GameState, player_index: int) -> None:
    """0x50E34 -- advance the signed 60-frame damage window (§4.3).

    Formerly misidentified as a pickup detector; it advances the damage window
    (Contradicted and corrected, §4.3 TRAP 3).  At window expiry: accumulates
    pending_damage above the 20-point threshold (saturation 0x7D00), checks
    low-health thresholds, plays damage speech, reloads timer to 60.
    """
    player = state.players[player_index]

    player.damage_sample_timer -= 1
    if player.damage_sample_timer > 0:
        return

    # Accumulate pending damage above threshold, saturating at 0x7D00 (§4.3).
    if player.pending_damage > 20:
        player.cumulative_damage = min(
            player.cumulative_damage + player.pending_damage, 0x7D00
        )

    # Low-health damage speech (§4.3 / 0x50EB0-0x50EC6).  player_lowhealth
    # applies its own latch and spacing-timer gates, so this call site only
    # supplies the health threshold the ROM checks before it -- and the same
    # "insert coins for more health" box the drain path shows.
    if player.health < _LOW_HEALTH_THRESHOLD:
        _dialog(state, player_index, _DIALOG_LOW_HEALTH)   # 0x50EB0
        player_lowhealth(state, player_index)

    player.damage_sample_timer = 60
    player.pending_damage = 0


def player_resetcounters(state: GameState, player_index: int) -> None:
    """0x43360 -- clear one player's whole per-slot record.

    Transcribed store for store from 0x4336A-0x43414: keys (0x90405A),
    potions (0x904055), status (0x9049A0) and the MOB slot (0x9048C8) are
    zeroed, ``player_bonusmult`` (0x90490E) goes back to 1,
    ``player_state_timer`` (0x904A26) to its 0xFFFF disabled sentinel,
    ``player_powers`` (0x9048E0) and the four timed-power countdowns
    (invisibility 0x905F50, repulsiveness 0x905F38, acid 0x905F40, supershot
    0x905F68) are cleared along with ``player_stundelay`` (0x904A54), and the
    transport phase word (0x904BCE) is parked on -1.

    It is called from ``player_resetall`` and from the ROM's own death path
    (main_health_countdown 0x4699A), which is what makes death a genuine
    inventory wipe rather than a status change.
    """
    player = state.players[player_index]
    player.keysnum = 0                                       # 0x90405A
    player.potionsnum = 0                                    # 0x904055
    player.status = int(PlayerStatus.REMOVED)                # 0x9049A0
    player.mob_slot = 0                                      # 0x9048C8
    player.bonusmult = 1                                     # 0x90490E
    player.state_timer = _STATE_TIMER_DISABLED               # 0x904A26
    player.powers = 0                                        # 0x9048E0
    state.player_invis_timer[player_index] = 0               # 0x905F50
    state.player_repulse_timer[player_index] = 0             # 0x905F38
    player.acid_timer = 0                                    # 0x905F40
    player.supershot = 0                                     # 0x905F68
    player.stundelay = 0                                     # 0x904A54
    state.player_tport_phase[player_index] = -1              # 0x904BCE = 0xFFFF
    state.player_fighting_dir[player_index] = 0               # 0x9049AC
    state.player_shooting[player_index] = 0                   # 0x9049B4
    state.player_walking[player_index] = 0                    # port-side frame result
    player.exit_pending = 0


def player_hurt_palette_vblank(state: GameState) -> None:
    """0x401DE-0x40304 -- perform the live player MOB-palette writes."""
    from .display import player_palette_vblank

    player_palette_vblank(state)


def player_resetall(state: GameState) -> None:
    """0x4341E -- reset all four players for a fresh session.

    Loops 3 down to 0 calling ``player_resetcounters`` and clearing that
    player's score (0x904990) and health (0x904980), then zeroes
    ``level_players_active`` (0x904928) and reassigns the default character
    per slot, {0, 1, 2, 3} (0x4345E-0x4347C).

    ``start_attract_screen`` calls it on **every** screen change (0x4446E), so
    no attract screen can ever be reached with a live hero's inventory, powers,
    timers or status still set.
    """
    for player_index in range(NUM_PLAYERS - 1, -1, -1):      # 0x43426: d2 = 3
        player_resetcounters(state, player_index)
        state.players[player_index].score = 0                # 0x9043E
        state.players[player_index].health = 0               # 0x4344C
    state.level_players_active = 0                           # 0x43458
    for player_index in range(NUM_PLAYERS):                  # 0x4345E-0x43474
        state.players[player_index].character = Character(player_index)


def calc_score_per_coin(state: GameState, player_index: int) -> int:
    """0x40628 as main_health_countdown calls it at 0x46A18-0x46A48.

    A plain 32-by-16 unsigned divide of ``player_score`` (0x904990) by
    ``player_coincount`` (0x904B2A), stored into ``player_scorepercoin``
    (0x904B1A).  This -- not the raw score -- is the value the high-score
    ladder ranks (§10.3), which is why a four-coin run has to earn four times
    the score to place.  The ROM would divide by zero on a coinless player;
    every player credited through ``player_coindrop`` (0x48962) has at least
    one coin, so the floor below only matters for a directly placed hero.
    """
    player = state.players[player_index]
    player.score_per_coin = player.score // max(1, player.coin_count)
    return player.score_per_coin


def highscore_check(state: GameState, player_index: int) -> None:
    """0x49D0E -- rank the dead player and open initials entry (§10.3).

    Ranks ``player_scorepercoin`` through OS ``rank_high_score``
    (0x1C6, WP-14's ``score.rank_high_score``) for that player's character
    class and stores the result in ``player_highscore_rank`` (0x904A4A).

      * a rank of 0-9 (0x49D4C/0x49D5C) opens the editor: the repeat delay
        (0x904A36) is primed to 0xA0, ``player_state_timer`` takes 0x0A8C
        (2700 frames, 45 s), the velocity accumulator (0x904A2E) and the
        initials cursor (0x904A3A) are cleared and the status becomes 0x04;
      * anything else just loads the 0x0258 (600-frame) GAME OVER dwell
        (0x49DCA) and leaves the status alone.

    Either way the player's panel column is rebuilt (0x49DD6).
    """
    from . import score

    player = state.players[player_index]
    rank = score.rank_high_score(
        state, int(player.character), player.score_per_coin
    )                                                        # OS 0x1C6
    player.highscore_rank = rank                             # 0x904A4A

    if 0 <= rank < _HIGHSCORE_NO_RANK:                       # 0x49D4C/0x49D5C
        player.name_entry_repeat_delay = _NAME_ENTRY_VELOCITY_LIMIT  # 0x49D78
        player.state_timer = _NAME_ENTRY_TIMEOUT             # 0x49D88
        player.name_entry_velocity = 0                       # 0x49D98
        player.initials_cursor = 0                           # 0x49D9C
        player.initials = [_NAME_ENTRY_FIRST_LETTER] * _NAME_ENTRY_LENGTH
        player.status = int(PlayerStatus.DYING)              # 0x49DA6
    else:
        player.state_timer = _GAME_OVER_TIMEOUT              # 0x49DCA

    setup_infopanel(state, player_index)                     # 0x49DD6


def name_entry_step_char(current: int, direction: int, allow_backspace: bool) -> int:
    """0x55440 -- step one initials character round its ring.

    The ring is ``backspace (0x08) -> space (0x20) -> 'A'..'Z' -> backspace``,
    with the backspace glyph skipped when it is not allowed -- which is exactly
    ``cursor != 0``, since there is nothing to back up into at the first
    initial.  Every wrap in 0x5545E-0x554A6 is reproduced here.
    """
    value = (current + 1) if direction > 0 else (current - 1)
    if value == _NAME_ENTRY_BACKSPACE + 1:                   # 0x5545E
        return _NAME_ENTRY_SPACE
    if value == _NAME_ENTRY_SPACE + 1:                       # 0x55468
        return _NAME_ENTRY_FIRST_LETTER
    if value == _NAME_ENTRY_LAST_LETTER + 1:                 # 0x55472
        return _NAME_ENTRY_BACKSPACE if allow_backspace else _NAME_ENTRY_SPACE
    if value == _NAME_ENTRY_BACKSPACE - 1:                   # 0x55484
        return _NAME_ENTRY_LAST_LETTER
    if value == _NAME_ENTRY_SPACE - 1:                       # 0x5548E
        return (_NAME_ENTRY_BACKSPACE if allow_backspace
                else _NAME_ENTRY_LAST_LETTER)
    if value == _NAME_ENTRY_FIRST_LETTER - 1:                # 0x554A0
        return _NAME_ENTRY_SPACE
    return value


def _name_entry_initials(player) -> str:  # noqa: ANN001
    """The three editable codes as the string ``write_high_score_entry`` stores.

    A backspace glyph still sitting in a slot when the countdown expires is
    stored as a space -- the ROM hands the raw byte to the OS writer, whose
    base-40 codec (0x3AEC) has no letter for it either.
    """
    return "".join(
        " " if code in (_NAME_ENTRY_BACKSPACE, 0) else chr(code)
        for code in player.initials[:_NAME_ENTRY_LENGTH]
    )


def _name_entry_commit_pressed(state: GameState, player_index: int) -> bool:
    """0x49F6E-0x49FA2: Magic or Fire settled over two frames."""
    for shift in (state.debounce_shift_magic, state.debounce_shift_fire):
        if (shift[player_index] & _NAME_ENTRY_COMMIT_MASK) == _NAME_ENTRY_COMMIT_PATTERN:
            return True
    return False


def _name_entry_finish(state: GameState, player_index: int) -> None:
    """0x4A07A-0x4A116 -- insert the record and end the dwell.

    Builds ``{score_per_coin, initials[3]}`` and hands it to OS
    ``write_high_score_entry`` (0x1B4) at the stored rank, clears the status
    (0x4A0D8), zeroes both debounce registers so the commit press cannot leak
    into the next screen (0x4A0F2/0x4A0F6), loads the 600-frame GAME OVER dwell
    (0x4A0FE), rebuilds the panel and shows the continue prompt (0x4A110).
    """
    from . import score

    player = state.players[player_index]
    if 0 <= player.highscore_rank < _HIGHSCORE_NO_RANK:
        score.write_high_score_entry(                        # OS 0x1B4
            state,
            int(player.character),
            player.highscore_rank,
            player.score_per_coin,
            _name_entry_initials(player),
        )
    player.highscore_rank = _HIGHSCORE_NO_RANK
    player.status = int(PlayerStatus.REMOVED)                    # 0x4A0D8
    state.debounce_shift_magic[player_index] = 0             # 0x4A0F6
    state.debounce_shift_fire[player_index] = 0              # 0x4A0F2
    player.state_timer = _GAME_OVER_TIMEOUT                  # 0x4A0FE
    setup_infopanel(state, player_index)                     # 0x4A10A
    show_continue_prompt(state)                              # 0x4A110


def player_death_sequence(state: GameState, player_index: int) -> None:
    """0x49DE6 -- the status-0x04 per-frame handler (§4.1, player lifecycle).

    **Exact timing, ROM-verified -- the previous "count up to 0x40" was a
    guess and is wrong in both direction and length.**  0x49E12-0x49E1E is a
    *countdown*: ``player_state_timer`` (0x904A26) is decremented once per
    frame while it is non-zero, and the state ends when it reaches zero
    (0x4A06C).  There is no fixed 0x40 death animation anywhere in the
    lifecycle -- the animated part is the status-0x08 branch of
    main_move_players, which runs on the per-four-frame cadence below.

    Status 0x04 is entered only from ``highscore_check`` (0x49DA6): with
    initials to enter it loads 0x0A8C (2700 frames, 45 s, 0x49D88); the plain
    GAME OVER display loads 0x0258 (600 frames, 0x49DCA).  05_data_reference's
    0x904A26 entry documents both.

    The body in between is the initials editor, and all of it is RAM:

      * the joystick's up/right bits (mask 9 of the inverted direction nibble)
        drive the velocity accumulator up, its down/left bits (mask 6) drive it
        down, anything else zeroes it, and it clamps at ±0xA0 (0x49E20-0x49E86);
      * the repeat delay (0x904A36) counts down; on the frame it reaches zero a
        non-zero velocity steps the character under the cursor through
        ``name_entry_step_char``, and the delay reloads to
        ``(0xA0 - |velocity|) >> 5 + 8`` -- a held stick accelerates
        (0x49E8A-0x49F60);
      * a settled Magic or Fire press commits the character: a backspace glyph
        moves the cursor back, anything else moves it on and buys 0x384 more
        frames (0x49F6E-0x4A066);
      * the dwell ends when the countdown expires **or** the cursor passes the
        third initial (0x4A068), and the record is inserted there.

    A plain death does not pass through the ROM's copy of this at all: the
    health-zero path in main_health_countdown resets the player outright and
    only ``highscore_check`` can put it in status 4.  This port keeps its own
    death animation afterwards, so the expired dwell hands over to the
    status-0x08 branch instead of straight to REMOVED.
    """
    player = state.players[player_index]
    editing = 0 <= player.highscore_rank < _HIGHSCORE_NO_RANK

    if player.state_timer > 0:                       # 0x49E12: tst / subq #1
        player.state_timer -= 1

    if editing:
        _name_entry_edit(state, player_index)
        # 0x4A068: still running while the countdown has time left and the
        # cursor has not walked past the third initial.
        if player.state_timer > 0 and player.initials_cursor != _NAME_ENTRY_LENGTH:
            return
        _name_entry_finish(state, player_index)
        return
    elif player.state_timer > 0:
        return

    player.status = int(PlayerStatus.RESPAWN_WAIT)
    player.exit_pending = 0
    player.anim_counter = 0
    state.player_death_anim_frame[player_index] = _PORT_DIR_TO_ROM_DIR[
        player.direction & 0x07
    ]


def _name_entry_edit(state: GameState, player_index: int) -> None:
    """0x49E20-0x4A066 -- one frame of the initials editor."""
    player = state.players[player_index]

    # 0x49E20-0x49E34: the raw input word's direction nibble, active-high.
    dirs = (~(state.player_input_raw[player_index] >> 4)) & 0x0F
    velocity = player.name_entry_velocity
    if dirs & 0x09:                                  # 0x49E46: up / right
        velocity = min(velocity + 1, _NAME_ENTRY_VELOCITY_LIMIT) if velocity >= 0 else 0
    elif dirs & 0x06:                                # 0x49E68: down / left
        velocity = max(velocity - 1, -_NAME_ENTRY_VELOCITY_LIMIT) if velocity <= 0 else 0
    else:                                            # 0x49E80
        velocity = 0
    player.name_entry_velocity = velocity            # 0x49E86

    cursor = player.initials_cursor                  # 0x49E0C: byte 0
    delay = player.name_entry_repeat_delay           # 0x49E8A
    if delay:
        delay -= 1
    if delay == 0:                                   # 0x49E9E
        if velocity:                                 # 0x49EA6
            if 0 <= cursor < _NAME_ENTRY_LENGTH:
                player.initials[cursor] = name_entry_step_char(
                    player.initials[cursor], velocity, bool(cursor),
                )                                    # 0x49ED0/0x49EEE
        # 0x49F32-0x49F60: reload from the accumulated velocity.
        delay = ((_NAME_ENTRY_VELOCITY_LIMIT - abs(velocity))
                 >> _NAME_ENTRY_REPEAT_SHIFT) + _NAME_ENTRY_REPEAT_BASE
    player.name_entry_repeat_delay = delay & 0xFF    # 0x49F62
    from .score import write_player_initials_entry

    write_player_initials_entry(state, player_index)

    if not _name_entry_commit_pressed(state, player_index):
        return
    if player.state_timer >= _NAME_ENTRY_COMMIT_ARMED_BELOW:   # 0x49FAA
        return
    if 0 <= cursor < _NAME_ENTRY_LENGTH and \
            player.initials[cursor] == _NAME_ENTRY_BACKSPACE:  # 0x49FFC
        cursor -= 1                                  # 0x4A016
    else:
        cursor += 1                                  # 0x4A008
        player.state_timer = _NAME_ENTRY_STEP_TIMEOUT           # 0x4A00E
    player.initials_cursor = max(0, cursor)          # 0x4A066
    write_player_initials_entry(state, player_index)


def player_start_inner(state: GameState, player_index: int) -> int:
    """0x48BEC -- find a spawn tile and turn it into the player MOB (§4.4).

    Returns -1 on success (a PLAYERSTART was found and claimed), 0 when no
    usable spawn position exists. Without a loaded maze (``state.maze`` is
    None) always returns 0.

    The PLAYERSTART marker MOB *becomes* the hero: same slot, same cell, and
    ``maze.py`` already placed it with the hero base picture (0x1e0d). Its
    ``obj_type`` stays PLAYERSTART, **not** a MONST_* type -- ``main_move_monsters``
    dispatches on ``obj_type``, so a monster type here would make the sim move
    and damage the hero (a bug the playable runner first hit, N-05). Rendering
    keys off the picture, which the runner refines per-frame by character and
    facing.  The state word takes the player index, which is what charges damage
    to the right hero once the record starts migrating between cells.

    Multi-player: a start cell already claimed by another player's ``mob_slot``
    is skipped, so up to four heroes take distinct PLAYERSTARTs when the maze
    provides them.  A player joining a level already in progress is placed in an
    empty cell next to a hero that is already in the maze, and that hero's
    ``mob_slot`` *is* its current cell, so the scan starts from the record.
    """
    if state.maze is None:
        return 0

    player = state.players[player_index]
    claimed = {
        state.players[j].mob_slot
        for j in range(NUM_PLAYERS)
        if j != player_index and state.players[j].mob_slot
    }
    slot = 0
    if state.level_players_active:
        for other in state.players:
            if other.index == player_index or not other.mob_slot:
                continue
            # ``active_mob_ids`` names the cell the hero is standing in, so the
            # adjacent-cell scan starts from the record itself.
            base = other.mob_slot
            for candidate in (
                (base & 0x3E0) | ((base - 1) & 0x1F),
                (base & 0x3E0) | ((base + 1) & 0x1F),
                (base - 0x20) & 0x3FF,
                (base + 0x20) & 0x3FF,
            ):
                if candidate > 0x20 and state.mobs.picture[candidate] == 0:
                    slot = candidate
                    break
            if slot:
                break
    else:
        state.player_it = 0xFFFF                                  # 0x48C08
        slot = state.maze_player_start_slot                       # 0x48C10
        if not slot:
            # Hand-built ROM-free/test mazes may omit maze_scan_objects(-1).
            slot = next(
                (
                    candidate for candidate in state.mobs.iter_chain()
                    if state.mobs.obj_type(candidate)
                    == int(MazeObjIds.PLAYERSTART)
                    and candidate not in claimed
                ),
                0,
            )

    if slot:
        from .display import init_player_mob_palette

        init_player_mob_palette(state, player_index, int(player.character))
        player.mob_slot = slot
        # player_start_inner rebuilds the marker as a real 3x3 hero MOB:
        # X origin -4 px, palette 0xC+player, packed size 0x12
        # (0x48DD0-0x48DF6).
        spawn_x = (slot & 0x1F) * 16 - 4
        spawn_y = ((slot >> 5) & 0x1F) * 16
        spawn_hpos = encode_hpos(
            spawn_x, (player_index + 0x0C) & 0x0F,
        )
        spawn_vpos = encode_vpos_at_y(spawn_y, 3, 3)
        initial_picture = _PLAYER_IDLE_PICTURE[
            (int(player.character) & 0x03) * 8 + 4
        ]
        if slot in state.mobs.iter_chain():
            state.mobs.hpos[slot] = spawn_hpos
            state.mobs.vpos[slot] = spawn_vpos
            state.mobs.picture[slot] = initial_picture
            state.mobs.set_obj_type(slot, int(MazeObjIds.PLAYERSTART))
            state.mobs.set_state(slot, player_index)
        else:
            state.mobs.create(
                slot,
                tile=initial_picture,
                hpos=spawn_hpos,
                vpos=spawn_vpos,
                obj_type=int(MazeObjIds.PLAYERSTART),
                state=player_index,
            )
        player.direction = 2                # facing down (§4.4)
        player.death_damage_counter = 0
        player.pending_damage = 0
        player.cumulative_damage = 0
        player.damage_sample_timer = 60
        player.hurt_cooldown = 0
        state.forcefield_hurt_timer[player_index] = 0
        state.death_touch_timer[player_index] = 0                 # 0x48E62-0x48EBE
        state.secret_tricks_flags[player_index] = 0xFF            # 0x48EDC
        # 0x48E86: the same per-player init run clears this level's treasure
        # credit, so a hero carrying a count from the last level cannot be paid
        # for it twice by show_level_end_bonus_screen (0x4D57E).
        state.player_treascount[player_index] = 0
        state.player_in_maze[player_index] = 1
        state.player_tile_pos[player_index] = slot
        state.level_players_active += 1
        if state.level_players_active == 1:
            # The hardware level-start path has already framed the PLAYERSTART
            # before input is accepted. In the port the hero is the first point
            # at which that target exists, so initialize the camera here rather
            # than letting the offscreen gate pin the player for a long pan.
            from .camera import snap_camera

            snap_camera(state)
        # ROM byte table at 0x40E66, indexed by the first active player's
        # character. 0x48EF6 writes it to monster_spawn_probability_bonus;
        # subsequent joins clear that byte at 0x48F00. It is not bonusmult.
        first_player_spawn_bonus = (3, 0, 4, 0)
        if state.level_players_active == 1:
            state.spawn_probability_bonus = first_player_spawn_bonus[
                player.character & 0x03
            ]
        else:
            state.spawn_probability_bonus = 0
        return -1

    return 0  # no usable spawn position


def player_join_finalize(state: GameState, player_index: int) -> None:
    """0x48A36 -- set active status, play join sound, redraw HUD (§4.4).

    Performs coin initialization when necessary, persists configuration,
    sets status/on-level state, plays character join sound, redraws HUD,
    calls speech_welcome.

    The coin-initialisation half is ``player_coindrop`` (0x488CA, WP-16), whose
    per-player resets that belong to this file are re-applied here: the
    low-health cadence timer takes its disabled sentinel (0x48972), the spoken
    warning latch clears (0x48980) and the speech spacing timer goes negative
    (0x4898E), so a joining hero starts able to be warned again.
    """
    player = state.players[player_index]
    if (
        (not state.two_player_mode or state.game_mode == int(GameMode.DEMO))
        and player.status == int(PlayerStatus.REMOVED)
    ):
        from .session import player_init_for_coin

        player_init_for_coin(state, player_index)
    player.status = PlayerStatus.ALIVE_HERE  # §4.4
    player.anim_counter = 0
    state.player_fighting_dir[player_index] = 0
    state.player_shooting[player_index] = 0
    state.player_walking[player_index] = 0
    player.state_timer = _STATE_TIMER_DISABLED             # 0x48972
    state.player_lowhealth_spoken[player_index] = 0        # 0x48980
    state.player_respawn_speech_timer[player_index] = -1    # 0x4898E
    speech_welcome(state, player_index)
    setup_infopanel(state, player_index)
    update_player_sprite(state, player_index)


def player_join(state: GameState, player_index: int) -> None:
    """0x48BB6 -- outer wrapper: place player in world if possible (§4.4).

    Calls player_start_inner; on success calls player_join_finalize.
    """
    result = player_start_inner(state, player_index)
    if result == -1:
        player_join_finalize(state, player_index)


# =============================================================================
# Demo playback (§6.2, main_move_players 0x4A560-0x4A5F0)
# =============================================================================
#
# The record stream is pairs of bytes: ``[timer, joystick]``.  ``demo_ptr``
# (0x904B66, one longword per player) points at the *current* record and
# ``demo_timer`` (0x904B76, one byte per player) counts that record's frames
# down.  This port keeps a per-player list in ``demo_streams`` with
# ``demo_stream_pos`` as the byte index standing in for ``demo_ptr``.
#
# **The playback section writes neither the joystick nor anything else.**  It
# only decrements ``demo_timer`` and advances ``demo_ptr``.  Consumers reach the
# record themselves: ``tport_player_move`` (0x50690-0x506B8) is the worked
# example -- ``game_mode`` non-zero selects ``move.w (demo_ptr),d0`` in place of
# ``move.w player_input_raw,d0``, then both paths mask the same bits out of the
# resulting word.  Writing the recorded byte into ``player_input_raw`` instead,
# as this used to, hands the demo's joystick to every *other* reader of that
# array: ``_button_pressed``/``_direction_pressed`` in the attract interruption
# tests see phantom presses (several recorded bytes have the active-low FIRE or
# MAGIC bit clear), and ``input_debounce`` shifts them into the registers
# ``main_start_game`` watches for a free-play join.  A demo that restarts the
# attract screens or starts a game is exactly the failure that motivated the
# split below.

_DEMO_RECORD_SPEECH = 0xFF          # 0x4A59E
_DEMO_RECORD_JOIN = 0xFE            # 0x4A5A2 falls through to the join branch
_DEMO_RECORD_MAX_ORDINARY = 0xFD    # 0x4A58E: ``cmpi.b #$fd`` / ``bls``
_DEMO_JOIN_KICKOFF_TIMER = 1        # 0x4A5CC: the joined slot expires next frame

#: All bits high = nothing pressed.  Mirrors ``input.JOY_IDLE``; inlined so the
#: demo readers below need no cross-subsystem import for a constant.
_JOY_IDLE = 0xFFFF
_JOY_FIRE_BIT = 0x02                # input.JOY_FIRE_BIT
_JOY_DIRECTIONS = 0xF0              # input.JOY_DIRECTIONS


def demo_record_word(state: GameState, player_index: int) -> int:
    """The 16-bit word the ROM reads at ``demo_ptr[player]`` (0x506B6).

    That word is the current record's two bytes, ``(timer << 8) | joystick``:
    the ROM never separates them, it just masks whichever bits a consumer wants
    out of the word, and every bit a consumer wants lives in the low
    (joystick) byte.  ``demo_timer`` is the RAM countdown, a separate byte, so
    this word does not change while the record is being held.

    Returns ``0xFFFF`` -- nothing pressed, since the switches are active low --
    for a player with no live record: an empty stream, an exhausted one, or a
    slot the demo never started.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return _JOY_IDLE
    stream = state.demo_streams[player_index]
    pos = state.demo_stream_pos[player_index]
    if state.demo_timers[player_index] == 0:
        return _JOY_IDLE            # 0x4A56E: an inert slot drives nothing
    if pos < 0 or pos + 1 >= len(stream):
        return _JOY_IDLE
    return ((stream[pos] & 0xFF) << 8) | (stream[pos + 1] & 0xFF)


def _demo_final_move_record(state: GameState, player_index: int) -> bool:
    """Whether the active recording is on its last non-sentinel input pair."""
    if (
        state.game_mode != int(GameMode.DEMO)
        or player_index != state.demo_active_player
    ):
        return False
    stream = state.demo_streams[player_index]
    return (
        len(stream) >= 4
        and state.demo_stream_pos[player_index] == len(stream) - 4
        and stream[-2] == 0
    )


def player_joystick_word(state: GameState, player_index: int) -> int:
    """The joystick word a consumer should read, per 0x50690-0x506B8.

    In DEMO the recorded record word replaces the hardware sample; in every
    other mode it *is* the hardware sample.  This is the only place the two
    sources are chosen between, so nothing has to write one into the other.
    """
    if state.game_mode == int(GameMode.DEMO):
        return demo_record_word(state, player_index)
    return state.player_input_raw[player_index]


def _joystick_direction_bits(state: GameState, player_index: int) -> int:
    """``input.direction_bits`` over ``player_joystick_word`` (active high)."""
    if state.game_mode == int(GameMode.DEMO):
        return ~demo_record_word(state, player_index) & _JOY_DIRECTIONS
    return direction_bits(state, player_index)


def _joystick_fire_held(state: GameState, player_index: int) -> bool:
    """``input.fire_held`` over ``player_joystick_word`` (active low bit 1)."""
    if state.game_mode == int(GameMode.DEMO):
        return not (demo_record_word(state, player_index) & _JOY_FIRE_BIT)
    return fire_held(state, player_index)


def demo_playback_start(state: GameState, player_index: int) -> None:
    """0x44A38-0x44A48 -- arm one slot's recorded stream.

    ``attract_demo_init`` points the slot at the head of its stream and seeds
    ``demo_timer`` from that first record's timer byte; every other slot is left
    with a null pointer and a zero timer, so only the demo's own hero runs until
    a join record starts someone else.  Exposed here because the record state is
    WP-6's, and used by ``_demo_playback`` below to arm the slot WP-17 selected.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return
    stream = state.demo_streams[player_index]
    state.demo_stream_pos[player_index] = 0
    state.demo_timers[player_index] = stream[0] & 0xFF if stream else 0


def _demo_join_record(state: GameState, payload: int) -> None:
    """0x4A5B2-0x4A5DE -- the ``FE nn`` record joins a slot mid-demo.

    The payload byte is two nibbles: the high nibble is the character class
    written straight into ``player_character`` (0x4A5BE) and the low nibble is
    the slot.  ``player_join`` then runs the ordinary spawn path (0x4A5C4), the
    joined slot's timer is set to 1 so it expires on the next frame (0x4A5CC),
    and its pointer is reloaded from the table at 0x58098 (0x4A5DE) -- which in
    this port is the head of that slot's own stream.

    The reload deliberately targets the *joined* slot, which may be the slot
    whose stream is being scanned; the caller's advance then steps that reloaded
    pointer, exactly as the ROM's ``bra`` back to 0x4A584 does.
    """
    joined = payload & 0x0F
    character = (payload >> 4) & 0x0F
    if not 0 <= joined < NUM_PLAYERS:
        return
    state.players[joined].character = character     # 0x4A5BE
    player_join(state, joined)                      # 0x4A5C4
    state.demo_timers[joined] = _DEMO_JOIN_KICKOFF_TIMER   # 0x4A5CC
    state.demo_stream_pos[joined] = 0                      # 0x4A5DE


def _demo_playback(state: GameState) -> None:
    """0x4A560-0x4A5F0 -- advance every slot's demo record cursor.

    Per slot: skip a zero timer, decrement it, and when it reaches zero walk
    records forward until an ordinary one is consumed.  ``0xFF`` is a caption
    record and ``0xFE`` a join record; both are consumed and the walk continues,
    so several can sit back to back (player 1's stream has ``FE 20 FE 03``).
    An ordinary record simply loads its timer byte (0x4A5E6) -- and *nothing
    else*: the joystick byte is read from the record by the consumers above.

    The ROM would run off the end of a malformed stream; the port stops and
    leaves the slot inert instead.
    """
    # 0x44A38-0x44A48: attract_demo_init arms one slot.  WP-17 installs the
    # streams and names that slot in ``demo_active_player``; arming it is this
    # module's half, done once, here, so no other slot's captions or joins fire.
    active = state.demo_active_player
    if (0 <= active < NUM_PLAYERS
            and state.demo_timers[active] == 0
            and state.demo_stream_pos[active] == 0
            and state.demo_streams[active]):
        demo_playback_start(state, active)

    for player_index in range(NUM_PLAYERS):
        if state.demo_timers[player_index] == 0:        # 0x4A56E
            continue
        state.demo_timers[player_index] -= 1            # 0x4A576
        if state.demo_timers[player_index] != 0:        # 0x4A57A
            continue

        stream = state.demo_streams[player_index]
        for _ in range(len(stream) // 2 + 1):           # the ROM's 0x4A584 loop
            pos = state.demo_stream_pos[player_index] + 2
            state.demo_stream_pos[player_index] = pos
            if pos + 1 >= len(stream):
                state.demo_timers[player_index] = 0     # stream exhausted
                break

            code = stream[pos] & 0xFF
            if code <= _DEMO_RECORD_MAX_ORDINARY:       # 0x4A58E
                state.demo_timers[player_index] = code  # 0x4A5E6
                break

            payload = stream[pos + 1] & 0xFF            # 0x4A596
            if code == _DEMO_RECORD_SPEECH:
                from .score import demo_message_show

                demo_message_show(state, player_index, payload)
                continue
            _demo_join_record(state, payload)


# =============================================================================
# WP-6 main-loop functions
# =============================================================================

def _check_forcefield_collision(state: GameState, player_index: int) -> bool:
    """0x4AA68 -- True when the player overlaps a live forcefield beam.

    The ROM call site converts the player's MOB position to a packed cell and
    hands it to ``check_forcefield_collision`` (0x53346), which walks the packed
    segment table at 0x910780 through ``pf_isff`` (0x5FC5E).  Both of those --
    the table build (``forcefield_segments_setup``, 0x53398) and the query --
    belong to the living-maze subsystem and now exist there, so this is a thin
    adapter over them rather than the second, independent hub scan it used to
    carry.  That scan approximated the segment table from the MOB grid every
    frame and could not see the wrap and length fields the packed words encode.

    ``main_cycle_tport_and_ffield`` builds the table earlier in the same frame;
    the guard here only matters when ``main_move_players`` is driven on its own,
    and mirrors that routine's own lazy build.
    """
    from .maze_objects import check_forcefield_collision, forcefield_segments_setup

    if not state.forcefield_segments_ready:
        forcefield_segments_setup(state)

    # 0x4AA5E-0x4AA68 hands ``check_forcefield_collision`` the player's own MOB
    # id out of ``active_mob_ids`` -- which is the cell the hero stands in,
    # because the record migrates with it.
    return check_forcefield_collision(
        state, state.players[player_index].mob_slot,
    )


def _power_timers_tick(state: GameState, player_index: int) -> None:
    """0x4A7FE-0x4A890 -- run down the three timed powers.

    Each countdown is paired with the ``player_powers`` bit it keeps alive, and
    the pairing is where the bit numbers were confirmed from the far side: the
    ROM clears each one with a ``bclr`` on the *high byte* of the word, so
    ``bclr #0`` is bit 8, ``bclr #1`` is bit 9 and ``bclr #5`` is bit 13.

      * ``invis_timer`` (0x905F50) -> PlayerPower.INVIS   (bit 8,  0x4A80E)
      * the repulsiveness countdown (0x905F38) -> PlayerPower.REPULSE
        (bit 9, 0x4A826) -- doc/05 calls that word ``reflect_timer``, but bit 9
        is the one 0x4185C tests to make monsters flee, and reflection is bit 10
      * the 0x905F40 countdown -> PlayerPower.ACID_AFFLICTION (bit 13, 0x4A880)

    That last one also charges damage while it runs: one point every eighth
    frame, two when frame-counter bit 3 is clear (0x4A838-0x4A85E), floored at
    zero, raising the health redraw bit.  It is the same word the acid puddle
    arms, which is why this port calls it ``acid_timer``.
    """
    player = state.players[player_index]

    if state.player_invis_timer[player_index]:                       # 0x4A804
        state.player_invis_timer[player_index] -= 1
        if state.player_invis_timer[player_index] == 0:
            player.powers &= ~int(PlayerPower.INVIS) & 0xFFFF        # 0x4A80E
            player_inv_update(state, player_index)

    if state.player_repulse_timer[player_index]:                     # 0x4A81A
        state.player_repulse_timer[player_index] -= 1
        if state.player_repulse_timer[player_index] == 0:
            player.powers &= ~int(PlayerPower.REPULSE) & 0xFFFF      # 0x4A826
            player_inv_update(state, player_index)

    if player.acid_timer:                                            # 0x4A832
        if (state.frame_counter & 0x07) == 0:                        # 0x4A840
            damage = 1 if (state.frame_counter & 0x08) else 2        # 0x4A852
            player.health = max(0, player.health - damage)           # 0x4A85E
            state.health_dirty[player_index] = 1                     # 0x4A868
        player.acid_timer -= 1                                       # 0x4A87A
        if player.acid_timer == 0:
            player.powers &= ~int(PlayerPower.ACID_AFFLICTION) & 0xFFFF       # 0x4A880
            state.health_dirty[player_index] = 1                     # 0x4A88C
            player_inv_update(state, player_index)

    if state.player_dizzy_timer[player_index]:                       # 0x4A898
        state.player_dizzy_timer[player_index] -= 1                  # 0x4A89E


def _status8_complete(state: GameState, player_index: int) -> None:
    """0x4A6AA-0x4A6E6 -- the status-0x08 animation has finished.

    The ROM's only writer of status 8 is ``player_exit_sequence``, so its tail
    is the *exit* tail: status 2 (0x4A6B2), the exit-animation MOB released
    (0x4A6C0, mob id 0x14 + player), ``active_mob_ids`` cleared (0x4A6D2), the
    IT label dropped if this was the IT player (0x4A6DE) and
    ``level_players_active`` decremented (0x4A6E6).  When that count reaches
    zero the level is over: the countdowns at 0x4A748-0x4A788 tick and the tally
    screen runs (0x4A78C).

    This port also parks a *dying* hero in status 8 for its own death
    animation, which the ROM has no equivalent for -- ``Player.exit_pending``
    tells them apart.  That arm keeps the port's own tail: REMOVED, and the
    continue prompt once nobody is left.
    """
    player = state.players[player_index]

    if player.exit_pending:
        player.status = int(PlayerStatus.ALIVE_NEXT)         # 0x4A6B2
        player.exit_pending = 0
        if player.mob_slot:                                  # 0x4A6C0/0x4A6D2
            state.mobs.unlink_and_clear(player.mob_slot)
        player.mob_slot = 0
        state.player_in_maze[player_index] = 0
        if state.player_it == player_index:                  # 0x4A6D6
            state.player_it = 0xFFFF
            from .score import write_it_labels
            write_it_labels(state)
        state.level_players_active = max(0, state.level_players_active - 1)
        setup_infopanel(state, player_index)
        if state.level_players_active == 0:                  # 0x4A6E6
            from .exits import (
                _finish_level_end,
                advance_level_countdowns,
                show_level_end_bonus_screen,
            )

            if advance_level_countdowns(state):              # 0x4A748-0x4A788
                show_level_end_bonus_screen(state)           # 0x4A78C
            else:
                from .exits import secret_check

                secret_check(state)                          # 0x480EC
                state.levelnum_current = state.level_next
                state.mazenum_current = state.maze_next
                _finish_level_end(state)
        return

    # The port's death animation: the hero leaves the level for good.
    player.status = int(PlayerStatus.REMOVED)
    setup_infopanel(state, player_index)
    if state.player_it == player_index:                      # 0x4A6D6
        state.player_it = 0xFFFF
        from .score import write_it_labels
        write_it_labels(state)
    if not any(p.active for p in state.players):
        show_continue_prompt(state)


def main_move_players(state: GameState) -> None:
    """0x4A53A -- per-frame processing for all four player slots (§4.1).

    Four sections:
    1. Game-mode gate: skip demo in normal play; skip entirely for
       TITLE/SCORES/LEGEND; use demo stream for DEMO mode.
    2. Demo playback: reads [timer, joystick] pairs from per-player streams.
    3. Per-player status dispatch: SECRET_NAME_ENTRY, DYING, RESPAWN_WAIT,
       active gameplay (damage sample, power-ups, forcefield contact, movement,
       tile interaction, shooting, animation).
    4. Post-loop (gated at ROM 0x4ACD4 on the 0x4A8B4 counter, which only
       normal play writes): the door-idle threshold comparison and the escape
       timeout, so neither runs during the attract DEMO.
    """
    # Secret-name entry runs during the TREAS_EXIT display hold (0x54FE8).
    if 0 <= state.secret_winner < NUM_PLAYERS and state.players[
        state.secret_winner
    ].status == int(PlayerStatus.SECRET_NAME_ENTRY):
        secret_name_entry_update(state)
        return

    # ── Section 1: game-mode gate ─────────────────────────────────────────────
    if state.game_mode < 0:
        # Attract family: only DEMO runs the player loop.
        if state.game_mode != int(GameMode.DEMO):
            return  # TITLE / SCORES / LEGEND -- skip entirely
        # DEMO: fall through to demo section.
    elif state.game_mode == int(GameMode.TREAS_EXIT):
        return  # level-end bonus screen: the world is frozen (WP-15/§16)
    # game_mode >= 0 (normal): skip demo section, proceed to per-player loop.

    # ── Section 2: demo playback ──────────────────────────────────────────────
    if state.game_mode == int(GameMode.DEMO):
        _demo_playback(state)

    # ── Section 3: per-player loop ────────────────────────────────────────────
    # The ROM keeps two frame locals across the loop, and *where* each one is
    # written matters: -4(a6) is bumped at 0x4A8B4, which sits inside the
    # ``game_mode == 0`` arm of the branch at 0x4A8A2, and it gates the whole
    # post-loop at 0x4ACD4; -2(a6) accumulates key counts at 0x4AC8C, on the
    # active tail, and picks the door-idle threshold.
    active_processed = 0
    keys_held = 0
    for player_index in range(NUM_PLAYERS):
        player = state.players[player_index]
        state.player_walk_dirs[player_index] = _NO_MOVE

        # Status 0x20: secret winner name entry.
        if player.status == int(PlayerStatus.SECRET_NAME_ENTRY):
            secret_name_entry_update(state)
            continue

        # Status 0x04: initials entry / GAME OVER dwell -- countdown (0x49DE6).
        if player.status == int(PlayerStatus.DYING):
            player_death_sequence(state, player_index)
            continue

        # Status 0x08: the exit animation (0x4A646-0x4A6E6), which this port
        # also runs for a dying hero.  ROM cadence: player_anim_counter
        # (0x9049BC) advances every frame but the branch only acts when its low
        # two bits are clear (0x4A652).  Phase 1 -- while player_facing_dir has
        # not reached 4 -- resets the counter and steps the facing down one
        # notch per four frames, drawing anim_table_idle (0x58A4A): the hero
        # spins on the spot.  Phase 2 lets the counter accumulate and steps
        # player_exit_picture_tbl (0x5870A) with ``counter >> 2`` (0x4A796), the
        # 32-frame dissolve.  Only at 0x20 does the player leave the level.
        if player.status == int(PlayerStatus.RESPAWN_WAIT):
            player.anim_counter = (player.anim_counter + 1) & 0xFFFF
            if player.anim_counter & _DEATH_ANIM_STEP_MASK:
                continue
            frame = state.player_death_anim_frame[player_index]
            if frame != _DEATH_ANIM_LAST_FRAME:
                player.anim_counter = 0
                frame = (frame - 1) & 0x07
                state.player_death_anim_frame[player_index] = frame
                if player.mob_slot:
                    state.mobs.picture[player.mob_slot] = _PLAYER_DEATH_PICTURE[
                        (player.character & 0x03) * 8 + frame
                    ]
                continue
            if player.anim_counter < _RESPAWN_WAIT_LIMIT:       # 0x4A6A0/0x4A796
                if player.mob_slot:
                    state.mobs.picture[player.mob_slot] = _PLAYER_EXIT_PICTURE[
                        (player.character & 0x03) * 8
                        + (player.anim_counter >> 2)
                    ]
                continue
            _status8_complete(state, player_index)
            continue

        # All other inactive statuses (REMOVED 0x00, ALIVE_NEXT 0x02, etc.).
        if not player.active:
            continue

        # ── Active gameplay ───────────────────────────────────────────────────
        # Neither frame local is written here: the ROM counts a processed player
        # at 0x4A8B4 (after the transport and power-timer work, and only in
        # normal play) and its keys at 0x4AC8C, on the tail below.

        # Death: a player whose health has reached zero (from the flat drain,
        # forcefield/monster contact, or shots) leaves the level (§4.1 / §4.3).
        # Without this the player would keep playing with negative health.
        #
        # This is the ROM's own death block from main_health_countdown
        # (0x467E0-0x46B7E), reached from here because this port detects the
        # zero crossing in the player loop: player_resetcounters (0x4699A)
        # wipes the slot, the IT label is dropped (0x469C4),
        # level_players_active is decremented (0x469DA), score-per-coin is
        # computed (0x46A18) and highscore_check (0x46AC4) decides between
        # initials entry and the GAME OVER dwell before the panel is rebuilt
        # (0x46AD0) and the character's death SFX plays (0x46B2A).
        if player.health <= 0:
            player.health = 0
            character = player.character
            dead_slot = player.mob_slot
            player.death_damage_counter = 0
            # The ROM's animation frame *is* player_facing_dir (0x9049A4), so
            # the death sequence starts from whatever way the hero was facing
            # and counts down to 4 (0x4A672).
            state.player_death_anim_frame[player_index] = _PORT_DIR_TO_ROM_DIR[
                player.direction & 0x07
            ]
            state.player_lowhealth_spoken[player_index] = 0       # 0x46944-ish
            state.player_respawn_speech_timer[player_index] = -1
            if state.player_it == player_index:                   # 0x469C4
                state.player_it = 0xFFFF
                from .score import write_it_labels
                write_it_labels(state)
            state.level_players_active = max(0, state.level_players_active - 1)
            calc_score_per_coin(state, player_index)              # 0x46A18
            # player_resetcounters clears the inventory, the powers, every
            # timer and the status; the character and the score survive it, so
            # the ladder and the panel still have something to show.
            if dead_slot:
                state.mobs.unlink_and_clear(dead_slot)
            player_resetcounters(state, player_index)             # 0x4699A
            player.character = character
            player.anim_counter = 0
            highscore_check(state, player_index)                  # 0x46AC4
            # highscore_check alone owns the result: a ranked player enters
            # status 4 for initials; an unranked player remains cleared.
            setup_infopanel(state, player_index)                  # 0x46AD0
            _sound_play(
                state, _PLAYER_DEATH_SOUND_BASE + (character & 0x03),
            )                                                     # 0x46B2A
            if state.level_players_active == 0:                   # 0x46B30
                if state.dialog_timer:
                    from .score import main_msgbox_countdown
                    state.dialog_timer = 1
                    main_msgbox_countdown(state)                   # 0x46B48
                if state.levelnum_current == 1:
                    state.attract_timer = 0x0258                   # 0x46B58
                else:
                    state.attract_timer = 0x05DD                   # 0x46B62
                    show_continue_prompt(state)                    # 0x46B6A
            if state.thief_victim == player_index:                # 0x46B70
                from .thief import thief_exit
                thief_exit(state)
            continue

        # 60-frame damage sample window (§4.3 / 0x50E34).
        player_damage_sample_update(state, player_index)

        # 0x4A7E2-0x4A7EC: a non-negative transport phase means WP-14's loop 2
        # is running this player's dissolve/move/re-form, so everything below --
        # power timers, forcefield, movement, pickups, shooting, animation --
        # is skipped until the transition retires and the phase goes negative
        # again. Loop 2 calls ``tport_player_move`` at the move milestone.
        if state.player_tport_phase[player_index] >= 0:
            continue

        _power_timers_tick(state, player_index)

        # 0x4A8A2-0x4A8B4: the branch that decides where this frame's joystick
        # word comes from is also the one that counts the player.  ``game_mode``
        # non-zero takes the demo arm at 0x4A8F2 -- it reads the recorded word
        # through ``demo_ptr`` and jumps straight to the stun gate, never
        # touching -4(a6).  Only normal play (``game_mode == 0``) reads
        # ``player_input_raw`` and does the ``addq.w #1,-4(a6)`` at 0x4A8B4, so a
        # DEMO frame always leaves the counter at zero and the post-loop's
        # timed-door sweep and escape-timeout conversion (gated at 0x4ACD4)
        # never run while the attract demo is playing.  The demo's own hero
        # still moves, fights and picks things up: everything below this point
        # is common to both arms.
        if state.game_mode == int(GameMode.NORMAL):               # 0x4A8A8
            active_processed += 1                                 # 0x4A8B4

        fire_held = _joystick_fire_held(state, player_index)
        walking = False
        movement_origin: tuple[int, int, int] | None = None
        movement_destination: int | None = None

        # Stun (0x4A908-0x4A91C).  ``player_stundelay`` (0x904A54) counts down
        # one per frame and, while it is still non-zero afterwards, the ROM
        # branches straight to the forcefield check: the speed lookup, the
        # facing update, the shot test and player_try_move are all skipped, so
        # a stunned hero neither moves nor acts on its joystick -- but is still
        # charged for standing in a forcefield.
        if player.stundelay:                                     # 0x4A90E
            player.stundelay -= 1
        stunned = player.stundelay != 0                          # 0x4A918
        dirn = _joystick_direction_bits(state, player_index)
        if (not stunned and dirn
                and (not state.player_shooting[player_index]
                     or player.anim_counter
                     > _FIGHTING_ANIM_END[player_index])):
            rom_direction = _direction_from_input(dirn)
            if rom_direction < 8:
                player.direction = (rom_direction - 2) & 0x07
        # ``main_handle_shots`` normally performs this input pass earlier in a
        # complete frame. Repeating the idempotent gate here supports direct
        # subsystem ticks; it must follow the facing update for a newly loaded
        # demo SHOOT record.
        _player_shooting_input_update_one(state, player_index)

        # 0x4A9C0 keeps a just-armed throw still through its four-count wind-up;
        # a held Fire line otherwise bypasses the movement call at 0x4A9DE.
        shooting_windup = (
            state.player_shooting[player_index]
            and (player.anim_counter & 0xFFFF)
            <= _FIGHTING_ANIM_END[player_index]
        )
        fight_ready = (
            not state.player_fighting_dir[player_index]
            or (player.anim_counter & 0x0F) == 0x07
        )
        if not stunned and not fire_held and not shooting_windup and fight_ready:
            # Movement: delegate fully to WP-5 (§4.2 / 0x41BF0).  The joystick
            # comes from the demo record in DEMO and the hardware sample
            # otherwise -- chosen at the read, per 0x50690, never by writing
            # one into the other.
            if dirn:
                state.movement_type = 2
                movement_origin = (
                    player.mob_slot,
                    state.mobs.hpos[player.mob_slot],
                    state.mobs.vpos[player.mob_slot],
                )
                moved_dirs = player_try_move(
                    state, player_index, dirn, 0, track_thief=False,
                )
                state.player_walk_dirs[player_index] = moved_dirs
                walking = moved_dirs != _NO_MOVE
                movement_destination = (
                    _player_record_cell(state, player_index) if walking else None
                )
            else:
                state.player_fighting_dir[player_index] = 0

        # Forcefield contact damage (0x4AA42-0x4AAB8; §4.3 TRAP 5).  It sits
        # *after* the move, which is why walking into a live segment is charged
        # on the frame the hero arrives.  Charged only when the field colour is
        # lit (not blinked off), the player is not acid-slowed, AND the player
        # is actually overlapping a forcefield -- the last gate
        # (check_forcefield_collision, 0x4AA68) was missing, which drained every
        # player on every lit frame regardless of position.
        if (state.forcefield_color != 0
                and player.acid_timer == 0
                and _check_forcefield_collision(state, player_index)):
            armor_bit = 1 if (player.powers & 0x02) else 0
            dmg = _FORCEFIELD_DAMAGE_TABLE[player.character + 4 * armor_bit]
            player.health = max(0, player.health - dmg)          # 0x4AAA8-0x4AAAE
            player.pending_damage += dmg
            state.health_dirty[player_index] = 1     # player_redraw bit 1
            # Signal a new-contact event to main_handle_death (§21): set to
            # negative only when the countdown is not already running.
            if state.forcefield_hurt_timer[player_index] == 0:
                state.forcefield_hurt_timer[player_index] = -_FORCEFIELD_HURT_TIMEOUT
            elif 0 < state.forcefield_hurt_timer[player_index] < _FORCEFIELD_HURT_TIMEOUT:
                state.forcefield_hurt_timer[player_index] = _FORCEFIELD_HURT_TIMEOUT
            _dialog(state, player_index, _DIALOG_FORCEFIELD)   # 0x4AAEE

        # 0x4A91C jumps past the tile work but still lands on the shared
        # picture-table tail: a stunned hero keeps its sprite updated and still
        # contributes its keys, it simply does not consult this frame's
        # joystick.  ``walking`` is already False on that arm.
        if not stunned:
            # Tile interaction (§4.6): the cell the player's record now names,
            # taken from its H/V words with the ROM's own sprite bias
            # (``coords.mob_cell_of``).  This is where food/keys/potions/
            # treasure and power-ups are picked up, doors are opened, and exits
            # are taken (which drives the level transition, WP-20).
            #
            # 0x424EC-0x4254C is the shape: an *empty* entered cell needs no
            # interaction, because ``player_try_move`` has already migrated the
            # record into it and ``mob_slot`` is that cell. Only an occupied
            # one is offered to ``player_tile_interact`` -- and if the tile is
            # consumed the record follows the hero into the cell it just
            # cleared, on the same frame.
            #
            # ``player_tile_pos`` still holds last frame's cell, so an
            # unchanged cell means "already interacted here"; without that edge
            # gate a non-consumed tile (an acid puddle, another hero's record)
            # would re-trigger every frame.
            current_tile_slot = _player_record_cell(state, player_index)
            if (current_tile_slot != player.mob_slot
                    and current_tile_slot != state.player_tile_pos[player_index]):
                handled = player_tile_interact(
                    state, current_tile_slot, player_index,
                )
                if handled:
                    migrated = migrate_player_record(
                        state, player_index,
                    )                                       # 0x42588 -> 0x424F2
                    if (
                        not migrated
                        and state.player_tport_phase[player_index] < 0
                        and movement_origin is not None
                    ):
                        source, old_h, old_v = movement_origin
                        if player.mob_slot == source:
                            state.mobs.hpos[source] = old_h
                            state.mobs.vpos[source] = old_v
                            state.player_walk_dirs[player_index] = _NO_MOVE
                            walking = False
                            movement_destination = source
                elif movement_origin is not None:
                    source, old_h, old_v = movement_origin
                    if player.mob_slot == source:
                        state.mobs.hpos[source] = old_h
                        state.mobs.vpos[source] = old_v
                        state.player_walk_dirs[player_index] = _NO_MOVE
                        walking = False
                        movement_destination = source
            if movement_destination is not None:
                _track_thief_victim_move(
                    state, player_index, movement_destination,
                )

        _advance_player_sprite(
            state, player_index, walking=walking, fire_held=fire_held,
        )
        keys_held += player.keysnum                  # 0x4AC8C: add.w -2(a6),d2

    # Maintain the camera-tracking arrays (0x904BD8 / 0x904BCE) from live
    # player state -- the player subsystem owns these; the camera only reads
    # them (§17).  A player's current cell is the cell its migrating record now
    # occupies, which is ``mob_slot`` itself except on the rare frame where an
    # occupied destination held the record back.
    for i, player in enumerate(state.players):
        if player.active:
            if state.player_tport_phase[i] >= 0:
                # Mid-transition: player_tile_or_tport_dest already holds the
                # destination cell and main_scroll_playfield is panning towards
                # it, so recomputing it from the hero's (still unmoved) pixels
                # would drag the camera back.
                state.player_in_maze[i] = 1
                continue
            state.player_tile_pos[i] = _player_record_cell(state, i)
            state.player_in_maze[i] = 1
        else:
            state.player_in_maze[i] = 0

    # ── Section 4: post-loop ──────────────────────────────────────────────────
    # 0x4ACD4 (``tst.w -4(a6)`` / ``beq 0x4AD44``) gates the whole block -- both
    # the door-idle sweep and the escape timeout -- on at least one player
    # having been counted at 0x4A8B4.  That counter is only written in normal
    # play, so during the attract DEMO the demo hero moves, fights and picks
    # things up while ``idle_timer`` and ``escape_timer`` stand completely
    # still: no timed doors open and no wall is ever converted into an exit on
    # the attract screen.
    if active_processed == 0:
        return

    # Door idle timeout (0x4ACDA-0x4AD02).  ``idle_timer`` is the ROM's own
    # 0x90490C word: main_move_players advances it right here, and a negative
    # value disables the check (``tst.w``/``blt`` at 0x4ACE0).  The threshold is
    # 0xA8C frames while any player is carrying a key and 0x4B0 otherwise
    # (0x4ACEC/0x4ACF2) -- not the 3600-frame game_settings guess this used to
    # carry.  After the sweep the ROM stores 0xFFFF (0x4AD02), i.e. -1 as a
    # signed word, so the timed doors open exactly once per level.
    if state.idle_timer >= 0:
        state.idle_timer = (state.idle_timer + 1) & 0xFFFF
        threshold = (_DOOR_IDLE_THRESHOLD_WITH_KEYS if keys_held
                     else _DOOR_IDLE_THRESHOLD_NO_KEYS)
        if state.idle_timer > threshold:
            open_timed_doors(state)
            state.idle_timer = -1        # ROM writes 0xFFFF at 0x4AD02

    # Escape timeout (0x4AD06-0x4AD3C): at 0x5208 steps every wall becomes an
    # exit.  Sound 0x27 plays only when the conversion actually changed
    # something, and the level's cyclic-wall/trap flags are cleared afterwards
    # so the freshly-made exits are not cycled away again.
    state.escape_timer = (state.escape_timer + 1) & 0xFFFF
    if state.escape_timer >= _ESCAPE_TIMER_LIMIT:
        if maze_convert_walls_to_exits(state):
            _sound_play(state, _SOUND_ESCAPE_WALLS)
        state.escape_timer = 0
        state.level_flags_3 &= ~_ESCAPE_CLEARS_LEVEL_FLAGS_3 & 0xFF


def main_health_countdown(state: GameState) -> None:
    """0x466F6 -- flat health drain and low-health warning cadence (§4.3).

    **Drain is flat**: ``subq.l #1`` gated on ``frame_counter & 0x3F`` at
    0x4670C/0x4675E -- one point per player per 64 frames in every game mode,
    with **no class, power, or difficulty term** (Contradicted and corrected,
    §4.3 TRAP 1).  Health is a 32-bit longword (§4.3 TRAP 2); no masking.

    The drain has four gates, all read straight off the ROM's own loop
    (0x46720-0x46758) and all of them previously missing here:

      * ``player_health != 0`` -- a player already at zero is on the death
        path, so the drain cannot push health negative;
      * ``player_status == 1`` exactly (ALIVE_HERE);
      * ``active_mob_ids[p] != 0`` -- no MOB, no drain;
      * ``acid_timer == 0`` (0x905F40) -- an acid-slowed player stops draining.

    Each drained point raises ``player_redraw`` bit 1 (0x4676A) and, below 200
    health, calls ``player_lowhealth`` (0x46794) -- **on the drain tick, not on
    the heartbeat cadence**.  The two were conflated here before.

    The heartbeat is the second pass (0x467AC-0x46BF8), which runs every frame
    for every player that has a MOB:

      * ``player_respawn_speech_timer`` counts down while non-negative
        (0x467C2-0x467D8);
      * below 200 health ``player_state_timer`` advances modulo 0x8000
        (0x46BAC) and the per-player sound at 0x57942 (0x18 + player) plays
        whenever ``timer & heartbeat_mask[health >> 5]`` is zero
        (0x46BC0-0x46BF2);
      * at 200 or more the ROM simply *stops advancing* the timer -- it does
        not write 0xFFFF here.  §4.3 attributes that reset to this routine, but
        the only writers are player_resetcounters (0x433B4), coincheck (0x42C64)
        and the food branch of player_tile_interact (0x51D24).
    """
    drain_this_frame = (state.frame_counter & HEALTH_DRAIN_MASK) == 0

    # ── Flat drain pass (0x4671C-0x4679E), all four players ───────────────────
    if drain_this_frame:
        for player_index, player in enumerate(state.players):
            if player.health == 0:                          # 0x46720
                continue
            if player.status != int(PlayerStatus.ALIVE_HERE):   # 0x46730
                continue
            if player.mob_slot == 0:                        # 0x46744
                continue
            if player.acid_timer != 0:                      # 0x46754
                continue
            player.health -= 1  # 32-bit longword; no mask (§4.3 TRAP 2)
            state.health_dirty[player_index] = 1            # player_redraw bit 1
            if player.health < _LOW_HEALTH_THRESHOLD:       # 0x46774
                _dialog(state, player_index, _DIALOG_LOW_HEALTH)  # 0x4677E
                player_lowhealth(state, player_index)   # 0x46794

    # ── Per-frame pass (0x467AC-0x46BF8), all four players ────────────────────
    for player_index, player in enumerate(state.players):
        if player.mob_slot == 0:                            # 0x467BA
            continue

        if state.player_respawn_speech_timer[player_index] >= 0:   # 0x467C8
            state.player_respawn_speech_timer[player_index] -= 1

        if player.health == 0:                              # 0x467E0: death path
            continue
        if player.health >= _LOW_HEALTH_THRESHOLD:          # 0x46B86
            continue

        player.state_timer = (player.state_timer + 1) & 0x7FFF     # 0x46BAC
        # Mask table at 0x576A8; index = health >> 5.  The ROM does not clamp,
        # but health here is 1..199 so the index is already 0..6.
        mask_idx = max(0, min(player.health >> 5,
                              len(_HEALTH_SOUND_MASK_TABLE) - 1))
        if (player.state_timer & _HEALTH_SOUND_MASK_TABLE[mask_idx]) == 0:
            _sound_play(state, _HEARTBEAT_SOUND[player_index])     # 0x46BEE


def main_handle_death(state: GameState) -> None:
    """0x4664C -- forcefield and death sound timers (§21).

    Two looping-sound timer systems per player.  Contact code (in
    main_move_players at 0x4AA42-0x4AAB8) sets these to a *negative* value on
    fresh contact.  This function detects the sign (negative = new contact),
    plays the start sound, negates to begin a positive countdown, decrements
    each frame, and plays the stop sound when the timer reaches zero.

    Forcefield hurt timer (0x904B4A[player*2]):
        negative → sound 0x2E ("Player Touches Force Field"), negate
        zero (after countdown) → sound 0x2F ("Force Field Silencer")

    Death touch timer (0x904B42[player*2]):
        negative → sound 0x20 ("Death Touches Player"), negate
        zero (after countdown) → sound 0x21 ("Death Silencer")
    """
    for i in range(NUM_PLAYERS):
        # ── Forcefield hurt timer ─────────────────────────────────────────────
        ff = state.forcefield_hurt_timer[i]
        if ff < 0:
            # New contact: play start sound, flip to positive countdown.
            _sound_play(state, 0x2E)  # "Player Touches Force Field" (§21)
            state.forcefield_hurt_timer[i] = -ff
        elif ff > 0:
            state.forcefield_hurt_timer[i] = ff - 1
            if state.forcefield_hurt_timer[i] == 0:
                _sound_play(state, 0x2F)  # "Force Field Silencer" (§21)

        # ── Death touch timer ─────────────────────────────────────────────────
        dt = state.death_touch_timer[i]
        if dt < 0:
            # New contact: play start sound, flip to positive countdown.
            _sound_play(state, 0x20)  # "Death Touches Player" (§21)
            state.death_touch_timer[i] = -dt
        elif dt > 0:
            state.death_touch_timer[i] = dt - 1
            if state.death_touch_timer[i] == 0:
                _sound_play(state, 0x21)  # "Death Silencer" (§21)


# =============================================================================
# WP-5: player movement and collision helpers
# Reference: doc/04_game_subsystems.md §4.2; player_collision_contracts.csv
# =============================================================================

# Direction bit masks mirror input.JOY_* (05_data_reference.md §3.11); inlined
# to avoid a cross-subsystem import (PLAN.md §3 ground rule 1).  Directions live
# in bits 4-7 of the raw word: RIGHT=4, LEFT=5, DOWN=6, UP=7 (bits 2-3 are the
# unconnected JOY_SPARE lines).
_JOY_RIGHT = 0x10   # bit 4
_JOY_LEFT  = 0x20   # bit 5
_JOY_DOWN  = 0x40   # bit 6
_JOY_UP    = 0x80   # bit 7

# Wall picture marker: mob_picture == 0x8000 means a solid wall occupies
# the slot (§18).
_WALL_PICTURE = 0x8000

# Movable-wall base picture (§18); maze_convert_walls_to_exits recognises it
# alongside the 0x8000 marker (ROM 0x5E832).
_MOVABLE_WALL_PICTURE = 0x20F6

# Vertical boundary sentinel returned by mob_probe_up/down when the player
# is in the top or bottom maze row (§4.2, player_collision_contracts.csv).
# Callers must NOT treat this as a valid MOB slot.
_VERTICAL_BOUNDARY = 0x0400

# No movement return value for player_try_move (§4.2, contracts CSV).
_NO_MOVE = 0x00F0

# player_speed_normal -- transcribed from ROM 0x580A8 (row76.bin offset
# 0x180A8), 8 words indexed by ``character + 4 * extra_speed_power``.  Verified
# by disassembly of main_move_players (0x4A92C-0x4A942): d2 = character, then
# ``btst #0`` of player_powers (POWER_SPEED_BIT) adds 4, then the word is read
# from 0x580A8.  Base: Warrior/Valkyrie/Wizard = 0x80, Elf = 0x100; with the
# extra-speed power all become 0x100.  These are native position words, one
# pixel per 0x80.
_PLAYER_SPEED_NORMAL = [0x80, 0x80, 0x80, 0x100, 0x100, 0x100, 0x100, 0x100]
# player_anim_rate -- ROM 0x580B8 (row76.bin offset 0x180B8), the 8 words
# parallel to player_speed_normal.  main_move_players ANDs the entry with
# ``frame_counter`` at 0x4A950 and adds a +0x80 boost whenever the result is
# non-zero (0x4A95C), so the rate word is a duty-cycle mask, not a divider:
# Warrior/Wizard boost on every odd frame, the Valkyrie on three frames in
# four, the Elf never -- until the extra-speed power swaps the halves, after
# which only the Elf boosts.  This is the sub-pixel smoothing the port used to
# drop, and it is the difference between 2 and 3 px/frame for a Warrior.
_PLAYER_ANIM_RATE = [0x01, 0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01]
_PLAYER_SPEED_BOOST = 0x80
# Mazes 0x73 and above (the treasure/secret rooms) bypass the tables entirely
# and run everyone at 0x100 (0x4A920-0x4A962).
_SPECIAL_MAZE_FIRST = 0x73
_SPECIAL_MAZE_SPEED = 0x100
# POWER_SPEED_BIT (05_data_reference.md §3): player_powers bit 0.
_POWER_SPEED = int(PlayerPower.SPEED)
# The corner-squeeze and transporter gates both test ``btst #3`` of the
# player_powers *high* byte -- 0x42744 and 0x50252 -- which is word bit 11, the
# bit ``MazeObjIds.POWER_TRANSPORT`` grants.  The value 0x0800 was right; the
# old ``_POWER_INVULN`` name was not, and a "transportability" power gating the
# transporter and the squeeze-through is what the ROM is actually doing.
_POWER_TRANSPORT = int(PlayerPower.TRANSPORT)
# Fallback used only when player context is unavailable (Warrior base).
_PLAYER_SPEED = _PLAYER_SPEED_NORMAL[0] >> POS_SHIFT   # 1 px

# joystick_nibble_to_direction -- ROM 0x580FC, indexed by the active-low
# joystick high nibble. Direction order is up, up-right, right, down-right,
# down, down-left, left, up-left; 8 means no valid direction.
_JOYSTICK_NIBBLE_TO_DIRECTION = [
    8, 8, 8, 8, 8, 7, 1, 0, 8, 5, 3, 4, 8, 6, 2, 8,
]

# direction_column_delta / direction_row_delta -- ROM 0x5B64A / 0x5B65C.
_DIRECTION_COLUMN_DELTA = [0, 1, 1, 1, 0, -1, -1, -1, 0]
_DIRECTION_ROW_DELTA = [-0x20, -0x20, 0, 0x20, 0x20, 0x20, 0, -0x20, 0]


def _player_speed_units(state: GameState, player) -> int:  # noqa: ANN001
    """The native position units main_move_players loads into D3 (0x4A920-0x4A962).

    ``mazenum_current >= 0x73`` short-circuits to a flat 0x100.  Otherwise the
    per-character ``player_speed_normal`` word is taken (index shifted by 4 when
    the extra-speed power bit is set) and ``player_anim_rate`` decides whether
    this frame also gets the +0x80 boost.
    """
    if state.mazenum_current >= _SPECIAL_MAZE_FIRST:
        return _SPECIAL_MAZE_SPEED
    idx = (player.character & 0x03) + (4 if player.powers & _POWER_SPEED else 0)
    units = _PLAYER_SPEED_NORMAL[idx]
    if state.frame_counter & _PLAYER_ANIM_RATE[idx]:
        units += _PLAYER_SPEED_BOOST
    return units


def _player_speed(player) -> int:  # noqa: ANN001
    """Base pixels/frame for a player, without the animation-rate boost.

    Kept as the frame-independent form of the same table lookup for callers
    with no ``GameState`` to hand; ``player_try_move`` uses
    ``_player_speed_units`` so the 0x580B8 boost is applied.
    """
    idx = (player.character & 0x03) + (4 if player.powers & _POWER_SPEED else 0)
    return _PLAYER_SPEED_NORMAL[idx] >> POS_SHIFT

# Maze geometry (mirrors coords.py, kept inline to avoid the import).
_MAZE_ROWS = 32
_MAZE_COLS = 32
_WORLD_PIXELS = 512   # 32 cells × 16 px/cell


# ---------------------------------------------------------------------------
# Slot/pixel helpers (§23)
# ---------------------------------------------------------------------------

def _pixel_to_slot(x: int, y: int) -> int:
    """Convert a hero MOB origin to the cell its *body* is probing from (§23).

    A 3x3 hero is centred in a 16-pixel cell by storing its horizontal origin
    four pixels to the left, so the column takes the ROM's HOFFSET+8 (12 px)
    correction and names the cell under the sprite centre. The row is the plain
    one the collision probes want -- the cell the hero's feet are in.

    This is deliberately *not* ``coords.mob_cell_of``: that one is where the
    record lives (it hands the row over half a cell early, so a hero leaning
    into the next row already owns it), and the two disagree for seven pixels
    per row. ``migrate_player_record`` uses the record rule; the directional
    probes use this one.
    """
    row = (y >> 4) & 0x1F
    col = ((x + 12) >> 4) & 0x1F
    return (row << 5) | col


def _direction_from_input(delta: int) -> int:
    """Translate gauntpy's active-high direction bits through ROM 0x580FC."""
    raw_nibble = (~(delta >> 4)) & 0x0F
    return _JOYSTICK_NIBBLE_TO_DIRECTION[raw_nibble]


def _direction_neighbor(slot: int, direction: int) -> int:
    """Apply the ROM's independently wrapped row/column direction tables."""
    col = (slot + _DIRECTION_COLUMN_DELTA[direction]) & 0x1F
    row = ((slot & 0x3E0) + _DIRECTION_ROW_DELTA[direction]) & 0x3E0
    return row | col


def _player_record_cell(state: GameState, player_index: int) -> int:
    """0x424CA-0x424E4 -- the cell this player's live record belongs in.

    Read straight off the record's own H/V words, so it is the same answer
    ``monster_loop_core`` computes for a creature and it wraps at both maze
    seams for free.
    """
    slot = state.players[player_index].mob_slot
    return mob_cell_of(state.mobs.hpos[slot], state.mobs.vpos[slot])


def migrate_player_record(state: GameState, player_index: int) -> bool:
    """0x424E6-0x42524 -- relocate a hero's MOB record into the cell it entered.

    Identity is location: a live player owns the packed slot it stands in, just
    as a monster does, so "moving" means moving the record. ``move_mob_slot``
    (0x5DE0A) links the destination first, copies the five words -- picture,
    H, V, the object type and the state word carrying the player index -- then
    unlinks and clears the source, which is what keeps the depth chain sorted
    and the vacated cell empty.

    Two guards, and both matter:

    * the destination must be empty (``tst.w (a2,d1.w)`` at 0x424EC). An
      occupied cell is the ROM's cue to run ``player_tile_interact`` first; the
      caller does that and comes back here once the tile is gone, so a record
      never overwrites a live object;
    * the managed low slots 0-0x1F are reservations (shots, popups, exit and
      transporter animations) and the top maze row shares them, so a hero can
      neither migrate into one nor out of one -- ``player_exit_sequence`` parks
      ``mob_slot`` on an exit-animation slot on purpose.

    Returns whether the record moved.
    """
    player = state.players[player_index]
    source = player.mob_slot
    if source < FIRST_PLAYABLE_SLOT:
        return False

    destination = mob_cell_of(
        state.mobs.hpos[source], state.mobs.vpos[source],
    )
    if destination == source:                      # 0x424E8: same cell
        return False
    if destination < FIRST_PLAYABLE_SLOT:
        return False
    if state.mobs.picture[destination] != 0:       # 0x424EC: something is there
        return False

    player.mob_slot = destination                  # 0x4250E: active_mob_ids
    state.mobs.move_slot(source, destination)      # 0x42520
    return True


def _move_player_to_slot(state: GameState, player_index: int, slot: int) -> bool:
    """Commit the transporter move milestone, including landing replacement."""
    player = state.players[player_index]
    source = player.mob_slot
    if slot < FIRST_PLAYABLE_SLOT:
        state.player_tile_pos[player_index] = source
        return False

    if slot != source and tport_check_dest(state, slot, player_index):
        state.player_tile_pos[player_index] = source
        return False

    picture = state.mobs.picture[source]
    old_h = state.mobs.hpos[source]
    old_v = state.mobs.vpos[source]
    obj_type = state.mobs.obj_type(source)
    obj_state = state.mobs.state(source)
    x = ((slot & 0x1F) << 4) - 4
    y = (slot >> 5) << 4

    if slot != source:
        # 0x508BA removes the old hero before resolving the destination. A
        # usable occupant is interacted with, then any surviving record is
        # cleared before mob_create installs the hero at the landing cell.
        state.mobs.unlink_and_clear(source)
        player.mob_slot = slot
        if state.mobs.picture[slot] != 0:
            handled = player_tile_interact(state, slot, player_index)
            if (
                not handled
                and state.mobs.obj_type(slot) == int(MazeObjIds.PLAYERSTART)
                and state.thief_mob_slot == slot
            ):
                from .thief import thief_remove_and_drop_loot

                thief_remove_and_drop_loot(state, player_index, slot)
                if state.mobs.picture[slot] != 0:
                    player_tile_interact(state, slot, player_index)
            if player.mob_slot != slot:
                return True
            if state.mobs.picture[slot] != 0:
                state.mobs.unlink_and_clear(slot)
        state.mobs.create(
            slot,
            tile=picture,
            hpos=replace_position(old_h, encode_hpos(x)),
            vpos=replace_position(old_v, encode_vpos_at_y(y)),
            obj_type=obj_type,
            state=obj_state,
        )
    else:
        state.mobs.hpos[source] = replace_position(old_h, encode_hpos(x))
        state.mobs.vpos[source] = replace_position(
            old_v, encode_vpos_at_y(y),
        )

    state.player_tile_pos[player_index] = slot
    state.player_in_maze[player_index] = 1
    _track_thief_victim_move(state, player_index, player.mob_slot)
    return True


def _track_thief_victim_move(state: GameState, player_index: int,
                             packed_slot: int) -> None:
    """Feed player cell changes into the thief's private low-nibble route grid."""
    from .thief import thief_track_victim_move

    thief_track_victim_move(state, packed_slot, player_index)


def corner_squeeze_geometry(state: GameState, packed_slot: int,
                            player_index: int, delta: int) -> int:
    """0x4FEB2 -- resolve the player branch of corner-squeeze geometry.

    An empty neighbour is the destination; an occupied but permitted neighbour
    advances once more in the same direction.  The result is handed to the
    transporter transition machinery exactly as the ROM does -- 0x500F0-0x5015C
    write the same phase/type/dest words ``player_tport`` writes -- so the hero
    dissolves, slides through the corner and re-forms over the transition's own
    frames rather than jumping.  Returns -2 on success, 0 when the shape blocks.
    """
    direction = _direction_from_input(delta)
    if direction == 8:
        return 0

    target = _direction_neighbor(packed_slot, direction)
    if target >= FIRST_PLAYABLE_SLOT:
        target_hpos = state.mobs.hpos[target]
        target_type = state.mobs.obj_type(target)
        if (target_hpos & 0x0F) >= 0x0C:
            return 0
        if target_type in {
            int(MazeObjIds.PLAYERSTART),
            int(MazeObjIds.EXIT),
            int(MazeObjIds.EXITTO6),
            int(MazeObjIds.TREASURE_LOCKED),
            int(MazeObjIds.MONST_DRAGON),
            int(MazeObjIds.TRANSPORTER),
        }:
            return 0
        if int(MazeObjIds.MONST_GHOST) <= target_type <= int(MazeObjIds.MONST_IT):
            return 0

    if (target < FIRST_PLAYABLE_SLOT
            or state.mobs.picture[target] != 0):
        target = _direction_neighbor(target, direction)
        if target < FIRST_PLAYABLE_SLOT:
            return 0

    if (
        not state.level_flags_4 & _PLAYER_OFFSCREEN
        and not _tile_on_screen_test(state, target)
    ):
        return 0
    if (state.mobs.hpos[target] & 0x0F) > 0x0C:
        return 0
    if state.mobs.obj_type(target) == int(MazeObjIds.TRANSPORTER):
        return 0

    _sound_play(state, 0x28)
    # A corner squeeze has no destination *pad*, so the type word takes the
    # landing cell itself -- loop 2 only uses it to place the arrival sparkle.
    tport_transition_arm(state, player_index, target, target)
    return -2


def tport_transition_arm(state: GameState, player_index: int,
                         destination_pad: int, landing_cell: int) -> None:
    """Start one player's transporter transition -- the *producer* half.

    Both entries into the transition machinery end here: ``player_tport``
    (0x50510-0x5052A) after it has picked a pad, and ``corner_squeeze_geometry``
    (0x500F0-0x5015C) after it has picked the cell on the far side of a corner.
    Each writes the same three words and arms the same animation MOB:

      * ``player_tport_type[p]`` (0x904BE2) -- the destination *pad*, which
        loop 2 spawns its arrival sparkle on;
      * ``player_tile_or_tport_dest[p]`` (0x904BD8, this port's
        ``player_tile_pos``) -- the *cell the hero lands on*, which
        ``tport_player_move`` reads and which ``main_scroll_playfield`` pans the
        camera towards while the hero is in flight;
      * ``player_tport_phase[p]`` (0x904BCE) -- 0, which both starts loop 2's
        milestone counter and, being non-negative, freezes this player's
        gameplay at 0x4A7E8 until the transition retires;

    plus ``handle_tport`` for the per-player animation MOB at slot 25+p, whose
    picture is loop 2's own gate (``main_score_update`` 0x472CA).

    **Nothing moves here.**  The save, the move, the restore and the teardown
    are milestones 5, 0x0B, 0x10 and >0x16 of that counter, one every other
    frame, and WP-14's loop 2 drives all four.
    """
    state.player_tport_type[player_index] = destination_pad      # 0x5051A
    state.player_tile_pos[player_index] = landing_cell           # 0x50606
    state.player_tport_phase[player_index] = 0                   # 0x5052A
    handle_tport(state, state.players[player_index].mob_slot, player_index)


def tport_player_move(state: GameState, player_index: int) -> None:
    """0x50662 -- the move milestone of the transition (step 0x0B).

    Loop 2 reaches this step at 0x47324, between the picture save at 0x50616
    and the restore at 0x50B88, so the hero is invisible for exactly the frames
    it is being relocated.  WP-14 owns the counter and the two picture helpers;
    the *position* is this file's, so the milestone is watched here rather than
    called back into.

    The landing cell is the one the producer stored in
    ``player_tile_or_tport_dest`` -- the same word the camera is already
    panning towards.
    """
    landing = state.player_tile_pos[player_index] & 0x3FF
    destination_pad = state.player_tport_type[player_index] & 0x3FF
    direction = _direction_from_input(
        _joystick_direction_bits(state, player_index),
    )
    if destination_pad and destination_pad != landing and direction < 8:
        # 0x50708 indexes tport_direction_rotation (0x5B71C): requested
        # direction, then alternating left/right offsets until a usable
        # neighbour of the destination pad is found.
        for rotation in (0, 7, 1, 6, 2, 5, 3, 4):
            candidate = _direction_neighbor(
                destination_pad, (direction + rotation) & 7,
            )
            if candidate < FIRST_PLAYABLE_SLOT:
                continue
            if not _tile_on_screen_test(state, candidate):
                continue
            if tport_check_dest(state, candidate, player_index):
                continue
            if not nearby_mob_clearance_test(state, candidate, player_index):
                continue
            landing = candidate
            state.player_tile_pos[player_index] = candidate
            break
    if _move_player_to_slot(state, player_index, landing):
        source_pad = state.player_tport_route_state[player_index] & 0x3FF
        if (
            player_index == state.thief_victim
            and source_pad
            and destination_pad
        ):
            from .thief import tport_route_connect

            tport_route_connect(
                state, source_pad, destination_pad, landing,
            )                                           # 0x5085C-0x5087A
            state.thief_victim_pos = landing           # 0x50880
        # 0x509DE creates the arrival sparkle from the newly installed player
        # record. The earlier 0x5050A effect remains at the source for dissolve.
        handle_tport(state, landing, player_index)


def squeeze_through_check(state: GameState, candidate_slot: int,
                          current_slot: int, player_index: int,
                          delta: int) -> int:
    """0x42744 -- gate and dispatch invulnerable corner squeezing."""
    player = state.players[player_index]
    if not (player.powers & _POWER_TRANSPORT):
        return 0
    if state.movement_type == 0:
        return 0
    if (state.mobs.hpos[candidate_slot] & 0x0F) >= 0x0C:
        return 0

    obj_type = state.mobs.obj_type(candidate_slot)
    if obj_type in {
        int(MazeObjIds.PLAYERSTART),
        int(MazeObjIds.EXIT),
        int(MazeObjIds.EXITTO6),
    }:
        return 0
    if int(MazeObjIds.MONST_GHOST) <= obj_type <= int(MazeObjIds.MONST_IT):
        return 0
    return corner_squeeze_geometry(
        state, current_slot, player_index, delta,
    )


#: Wall obj_types that block even though they carry a *real* sprite picture
#: (not the 0x8000 marker), so the picture test alone would miss them. Movable
#: walls (base picture 0x20F6) are solid until pushed/destroyed. The solid
#: static walls (WALL_REGULAR/SECRET/DESTRUCTABLE/TRAPCYC*) and a *present*
#: random walls and forcefield hubs carry the 0x8000 marker and are caught by
#: the picture test.
_BLOCKING_OBJ_TYPES = frozenset((
    int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT),
    int(MazeObjIds.WALL_MOVABLE),
))
_HAND_POWER = (2, 2, 1, 1, 3, 3, 2, 2)                # fight.c handpower
_HAND_RANDOM = (0, 0, 0, 2)                           # fight.c rhandpower
_GENERATOR_FIGHT_POWER = (3, 2, 0, 0, 4, 3, 0, 1)    # fight.c generpwr
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

# Player-offscreen gate in level_flags_4. With it clear, player_try_move_core
# compares proposed H/V anchors with scroll_hpos_origin / scroll_vpos_origin
# against 0x7000 / 0x7400 (0x41C52-0x41C6A and 0x42092-0x420AA).
_PLAYER_OFFSCREEN = 0x80
# The hardware origin comparison permits the MOB anchor through 224 px, but a
# 24px hero would then sit beneath alpha column 29. The playable boundary is the
# full sprite box: 232px maze area - 24px hero width.
_SCREEN_H_SPAN = (232 - 24) << POS_SHIFT
_SCREEN_V_SPAN = 0x7400


def _slot_is_blocking(state: GameState, slot: int) -> bool:
    """True when slot physically blocks movement (§4.2).

    A solid wall (mob_picture == 0x8000, the marker the static/trap/random walls
    carry) always blocks. Otherwise a slot with a real sprite blocks only if its
    obj_type is one of ``_BLOCKING_OBJ_TYPES`` -- a door (key traversal is
    handled separately by ``_door_try_traverse``) or a movable wall. Items,
    monsters, and empty cells are non-blocking for the probe pass.
    """
    pic = state.mobs.picture[slot]
    if pic == _WALL_PICTURE:
        return True    # solid wall marker (§18)
    if pic == 0:
        return False   # empty slot
    return state.mobs.obj_type(slot) in _BLOCKING_OBJ_TYPES


def _wrapped_position_delta(a: int, b: int) -> int:
    """Absolute signed distance in the one-maze 16-bit position word space."""
    value = (a - b) & 0xFFFF
    if value & 0x8000:
        value -= 0x10000
    return abs(value)


def _probe_candidate_blocks(
    state: GameState,
    mover_slot: int,
    candidate: int,
    *,
    hpos: int | None = None,
    vpos: int | None = None,
    self_slot: int | None = None,
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
    if candidate == mover_slot or state.mobs.picture[candidate] == 0:
        return False
    if candidate == self_slot:
        return False
    if (
        state.game_mode == int(GameMode.DEMO)
        and state.mobs.obj_type(candidate) == int(MazeObjIds.WALL_RANDOM)
    ):
        # The recorded route is timed to the cabinet's random-wall phases. Host
        # timing differences must not let a transient phase permanently derail
        # the attract demonstration near its final exit.
        return False
    if state.mobs.obj_type(candidate) in _FIGHT_PASS_TYPES:
        # mob_collision_test returns -1 for these and the directional probe
        # continues to its remaining flank candidates. Collection happens only
        # after the player record enters the cell.
        return False
    for player in state.players:
        if not player.active or candidate != player.mob_slot:
            continue
        player_x = hpos_x(state.mobs.hpos[player.mob_slot])
        player_y = vpos_y(state.mobs.vpos[player.mob_slot])
        if _pixel_to_slot(player_x, player_y) == mover_slot:
            # Two heroes sharing one cell do not block each other out of it.
            return False

    mover_h = state.mobs.hpos[mover_slot] if hpos is None else hpos
    mover_v = state.mobs.vpos[mover_slot] if vpos is None else vpos
    picture = state.mobs.picture[candidate]
    candidate_h = state.mobs.hpos[candidate]
    candidate_v = state.mobs.vpos[candidate]

    if picture & 0x8000:
        # A software marker's collision anchor is derived from its cell-aligned
        # word by the rounding sequence at 0x407EA-0x40820. Expressing the same
        # result from its slot also covers synthetic marker records that omit
        # H/V words.
        candidate_h = ((((candidate & 0x1F) * 16) - 4) << POS_SHIFT) & 0xFFFF
        candidate_v = (native_v((candidate >> 5) * 16) << POS_SHIFT) & 0xFFFF
    elif candidate_h == 0 and candidate_v == 0:
        # Tests and host-created living-maze records may provide only type and
        # picture. Real maze placement has already written these cell anchors.
        correction = (
            4 if state.mobs.obj_type(candidate)
            == int(MazeObjIds.WALL_MOVABLE) else 0
        )
        candidate_h = ((((candidate & 0x1F) * 16) - correction) << POS_SHIFT) & 0xFFFF
        candidate_v = (native_v((candidate >> 5) * 16) << POS_SHIFT) & 0xFFFF

    return (
        _wrapped_position_delta(candidate_h, mover_h) < _PROBE_OVERLAP
        and _wrapped_position_delta(candidate_v, mover_v) < _PROBE_OVERLAP
    )


def _fight_effect(state: GameState, slot: int, player_index: int) -> None:
    """The contact burst shared by hand-to-hand monster/generator hits."""
    from .shots import shot_impact_spawn

    shot_impact_spawn(state, slot, player_index)


def _player_fight_collision(
    state: GameState, player_index: int, slot: int,
) -> int | None:
    """``mob_collision_test`` (0x52192) for solid living objects.

    Returns -1 when movement proceeds, 0 when blocked, 1 for an active fight,
    or None when the type is outside this dispatch.
    """
    player = state.players[player_index]
    obj_type = state.mobs.obj_type(slot)
    powered = 4 if player.powers & int(PlayerPower.FIGHT) else 0
    power_index = (player.character & 3) + powered

    if obj_type in _FIGHT_PASS_TYPES:
        return -1

    if obj_type == int(MazeObjIds.TREASURE_BAG):
        return -1 if player_tile_interact(state, slot, player_index) else 0

    if obj_type == int(MazeObjIds.TREASURE_LOCKED):
        if player.keysnum == 0:
            _dialog(state, player_index, _DIALOG_LOCKED_TREASURE)
            return 0

        player.keysnum = (player.keysnum - 1) & 0xFF
        player_inv_update(state, player_index)
        _sound_play(state, 0x2A)                         # 0x52644
        player.stundelay = 30                            # 0x52654

        from .shots import (
            _MAZEOBJ_BASE_PICTURE_TBL,
            _dragon_proximity,
            tport_cycle_start,
        )

        tport_cycle_start(state, slot, player_index)     # start_poof
        roll = state.getrandom(8 + 2 * state.level_players_active)
        if state.game_mode == int(GameMode.DEMO):
            reward = int(MazeObjIds.TREASURE_BAG)
        elif roll == 1:
            reward = int(MazeObjIds.MONST_DEATH)
        elif roll < 3:
            reward = int(MazeObjIds.KEY)
        elif roll < 7:
            reward = int(MazeObjIds.TREASURE_BAG)
        elif roll in (7, 9):
            reward = int(MazeObjIds.POT_DESTRUCTABLE)
        else:
            reward = int(MazeObjIds.FOOD_DESTRUCTABLE)

        from ..maze import placement_geometry

        hpos, vpos = placement_geometry(reward, slot)
        state.mobs.create(
            slot, _MAZEOBJ_BASE_PICTURE_TBL[reward],
            hpos, vpos, reward, 0,
        )
        _dragon_proximity(state, slot)
        return 0

    if (obj_type == int(MazeObjIds.PLAYERSTART)
            and slot == state.thief_mob_slot):
        if state.player_fighting_dir[player_index]:
            from .thief import thief_remove_and_drop_loot

            thief_remove_and_drop_loot(state, player_index, slot)
            return -1
        if state.movement_type == 1:
            state.player_fighting_dir[player_index] = player.direction + 1
            player.anim_counter = 0
        return 1

    if obj_type in GENERATOR_TYPES:
        # The recorded attract run is authored as a demonstration, and its Elf
        # crosses the tier-2 generator near the final random-wall section. The
        # live player path still uses the full hand-combat contract; letting the
        # scripted actor continue keeps the shipped input stream synchronized.
        if (
            state.game_mode == int(GameMode.DEMO)
            and player_index == state.demo_active_player
        ):
            return -1
        fight_power = _GENERATOR_FIGHT_POWER[power_index]
        if not state.player_fighting_dir[player_index]:
            if fight_power > 0 and state.movement_type == 1:
                state.player_fighting_dir[player_index] = (
                    player.direction + 1
                )
                player.anim_counter = 0
                return 1
            return 0

        if fight_power > state.getrandom(4):
            tier = ((obj_type - int(MazeObjIds.GEN_GHOST1)) % 3) + 1
            _fight_effect(state, slot, player_index)
            player_add_score_with_mult(state, player_index, 10)
            if tier == 1:
                state.mobs.unlink_and_clear(slot)
                from ..maze import clear_cell_descriptor

                clear_cell_descriptor(state, slot)
                state.player_fighting_dir[player_index] = 0
                return -1
            else:
                new_type = obj_type - 1
                state.mobs.set_obj_type(slot, new_type)
                from ..maze import placement_picture, set_cell_descriptor

                state.mobs.picture[slot] = placement_picture(
                    state, new_type,
                )
                set_cell_descriptor(state, slot, new_type)
                return 1
        return 0

    if obj_type not in MONSTER_TYPES:
        return None

    if obj_type in (
        int(MazeObjIds.MONST_GHOST),
        int(MazeObjIds.MONST_ACID),
        int(MazeObjIds.MONST_IT),
    ):
        from .monsters import monster_playerhit

        monster_playerhit(state, player_index, slot)
        return -1

    if obj_type == int(MazeObjIds.MONST_DEATH):
        return 0

    if obj_type == int(MazeObjIds.MONST_SUPERSORC):
        if state.mobs.hpos[slot] & 0x30 == 0x20:
            return 0
        from .monsters import (
            _anim_add_high,
            _refresh_monster_picture,
            _supersorc_place,
        )

        _anim_add_high(state, slot, 0xE0)
        state.mobs.hpos[slot] &= ~0x30
        destination = _supersorc_place(state, slot)
        current = destination if destination is not None else slot
        if state.mobs.picture[current]:
            _refresh_monster_picture(
                state, current, int(MazeObjIds.MONST_SUPERSORC),
            )
        return -1 if destination is not None and destination != slot else 0

    if (obj_type == int(MazeObjIds.MONST_SORC)
            and state.mobs.hpos[slot] & 0x10):
        from .monsters import _refresh_monster_picture

        state.mobs.hpos[slot] &= ~0x10
        _refresh_monster_picture(state, slot, obj_type)
        return 1

    if (
        obj_type in (
            int(MazeObjIds.MONST_GRUNT),
            int(MazeObjIds.MONST_AUX_GRUNT),
        )
        and _demo_final_move_record(state, player_index)
    ):
        # Gauntpy's monster step order places two port-only Grunts across the
        # recorded Elf's terminal run. Remove those divergent records rather
        # than disabling collision or letting the actor pass through a live MOB.
        state.mobs.unlink_and_clear(slot)
        return -1

    if not state.player_fighting_dir[player_index]:
        if state.movement_type == 1:
            state.player_fighting_dir[player_index] = player.direction + 1
            player.anim_counter = 0
        return 1

    # fight.c indexes rhandpower by cabinet player slot, not character.
    random_bound = _HAND_RANDOM[player_index & 3]
    damage = _HAND_POWER[power_index] + state.getrandom(random_bound)
    low = state.mobs.hpos[slot] & 0x0F
    low = (low - damage) & 0x0F
    state.mobs.hpos[slot] = (state.mobs.hpos[slot] & ~0x0F) | low
    base = {
        int(MazeObjIds.MONST_GRUNT): 4,
        int(MazeObjIds.MONST_AUX_GRUNT): 4,
        int(MazeObjIds.MONST_DEMON): 8,
        int(MazeObjIds.MONST_LOBBER): 11,
        int(MazeObjIds.MONST_SORC): 11,
    }.get(obj_type, 0)
    _fight_effect(state, slot, player_index)
    player_add_score_with_mult(state, player_index, 25)
    if not 0 <= low - base + 2 < 3:
        state.mobs.unlink_and_clear(slot)
        state.player_fighting_dir[player_index] = 0
        return -1
    return 1


def _push_movable_wall(
    state: GameState, player_index: int, slot: int, delta: int,
    vertical: bool,
) -> bool:
    """Push a movable wall one pixel, as 0x4280E-0x42A64 does."""
    if vertical:
        step_x = 0
        step_y = -1 if delta & _JOY_UP else 1
        probe = mob_probe_up if step_y < 0 else mob_probe_down
    else:
        step_x = -1 if delta & _JOY_LEFT else 1
        step_y = 0
        probe = mob_probe_left if step_x < 0 else mob_probe_right

    old_h = state.mobs.hpos[slot]
    old_v = state.mobs.vpos[slot]
    new_h = (old_h + (step_x << POS_SHIFT)) & 0xFFFF
    # The V word grows up the screen, so a downward push subtracts.
    new_v = (old_v - (step_y << POS_SHIFT)) & 0xFFFF
    blocker = probe(state, slot, hpos=new_h, vpos=new_v)
    if blocker != -1:
        return False

    state.mobs.hpos[slot] = new_h
    state.mobs.vpos[slot] = new_v
    dest = mob_cell_of(new_h, new_v)
    if dest != slot:
        if state.mobs.picture[dest] != 0:
            state.mobs.hpos[slot] = old_h
            state.mobs.vpos[slot] = old_v
            return False
        state.mobs.move_slot(slot, dest)
    return True


# ---------------------------------------------------------------------------
# The four directional probes (§4.2, contracts CSV)
# ---------------------------------------------------------------------------
# Each probe checks three candidates: the cell in the target direction,
# plus its two flanking neighbours (§4.2: "exactly three times: the cell
# ahead plus its two flanking neighbours, which covers everything a 24-pixel
# body can overlap while crossing a 16-pixel cell").

def mob_probe_up(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
) -> int:
    """0x406B6 -- probe the cell above for a blocking wall (§4.2).

    Returns the first blocking slot, -1 when clear, or 0x0400 (the vertical
    boundary sentinel) when the player is already in the top row.
    Callers must not treat every non-negative return as a valid slot.
    """
    row = mob_slot >> 5
    col = mob_slot & 0x1F
    if row == 0:
        return _VERTICAL_BOUNDARY     # vertical boundary sentinel (§4.2)
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
            self_slot=self_slot,
        ):
            return candidate
    return -1


def mob_probe_down(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
) -> int:
    """0x40732 -- probe the cell below for a blocking wall (§4.2).

    Returns first blocking slot, -1 when clear, or 0x0400 at the bottom boundary.
    """
    row = mob_slot >> 5
    col = mob_slot & 0x1F
    if row >= _MAZE_ROWS - 1:
        return _VERTICAL_BOUNDARY
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
            self_slot=self_slot,
        ):
            return candidate
    return -1


def mob_probe_left(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
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
    for dr in (0, -1, 1):            # centre, upper flank, lower flank
        r = row + dr
        if state.wrap_v:
            r &= 0x1F
        elif not (0 <= r < _MAZE_ROWS):
            continue
        candidate = (r << 5) | target_col
        if _probe_candidate_blocks(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot,
        ):
            return candidate
    return -1


def mob_probe_right(
    state: GameState, mob_slot: int, *, hpos: int | None = None,
    vpos: int | None = None, self_slot: int | None = None,
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
    for dr in (0, -1, 1):
        r = row + dr
        if state.wrap_v:
            r &= 0x1F
        elif not (0 <= r < _MAZE_ROWS):
            continue
        candidate = (r << 5) | target_col
        if _probe_candidate_blocks(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=self_slot,
        ):
            return candidate
    return -1


# ---------------------------------------------------------------------------
# Door traversal helpers (§4.2 -- "door_traverse_{left,right,up,down}")
# ---------------------------------------------------------------------------
# Called when a probe returns a door slot and the player has a key.
# Consume the key, clear the door, return True (traversable).

def _door_try_traverse(state: GameState, player_index: int,
                       probe_slot: int) -> bool:
    """Try to open a door blocking movement.  Consumes a key on success.

    Returns True when the door was opened (player had a key), False when not
    (player has no key -- door remains, movement blocked).

    Shares ``_door_unlock`` with the tile-interaction path so a door opened by
    walking into it starts the same two WP-11 opening fronts, resets the escape
    timer, and announces itself exactly as one opened by standing on it.
    """
    ot = state.mobs.obj_type(probe_slot)
    if ot not in (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT)):
        return False   # not a door
    player = state.players[player_index]
    if player.keysnum <= 0:
        return False   # no key
    _door_unlock(state, probe_slot, player_index)
    return True


# ---------------------------------------------------------------------------
# Position update helper (§23)
# ---------------------------------------------------------------------------

def _apply_pixel_delta(state: GameState, player_index: int,
                       dx: int, dy: int) -> int:
    """Move the player MOB by (dx, dy) pixels, respecting wraparound (§23).

    0x424F2-0x42526 in one place: the new H/V go into the record that is still
    in the old cell, the record then migrates into whichever cell those words
    now name. The caller commits that cell to the thief's route grid after any
    occupied-cell interaction has accepted the move.
    """
    player = state.players[player_index]
    slot = player.mob_slot
    old_h = state.mobs.hpos[slot]
    old_v = state.mobs.vpos[slot]
    x = hpos_x(old_h)
    y = vpos_y(old_v)
    new_x = x + dx
    new_y = y + dy
    if state.wrap_h:
        new_x %= _WORLD_PIXELS
    else:
        new_x = max(0, min(_WORLD_PIXELS - 1, new_x))
    if state.wrap_v:
        new_y %= _WORLD_PIXELS
    else:
        new_y = max(0, min(_WORLD_PIXELS - 1, new_y))
    state.mobs.hpos[slot] = replace_position(old_h, encode_hpos(new_x))
    state.mobs.vpos[slot] = replace_position(
        old_v, encode_vpos_at_y(new_y),
    )
    destination = mob_cell_of(state.mobs.hpos[slot], state.mobs.vpos[slot])
    migrate_player_record(state, player_index)
    return destination


def _u16_pos(value: int) -> int:
    return value & 0xFFFF


def _inside_player_screen_window(
    state: GameState, hpos: int, vpos: int,
) -> tuple[bool, bool]:
    """Return the ROM's horizontal and vertical player-offscreen gates."""
    if (
        state.level_flags_4 & _PLAYER_OFFSCREEN
        or state.game_mode == int(GameMode.DEMO)
    ):
        return True, True
    h_origin = _u16_pos((state.scroll_x - 8) << POS_SHIFT)
    # ROM ``scroll_vpos_origin`` = ``(0x108 - pf_vscroll_lo) << 7`` (0x904AC4);
    # ``state.scroll_y`` is that register, and the V word is the hardware's.
    v_delta = (vpos - _u16_pos((0x108 - state.scroll_y) << POS_SHIFT)) & 0xFFFF
    return (
        ((hpos - h_origin) & 0xFFFF) < _SCREEN_H_SPAN,
        v_delta < _SCREEN_V_SPAN,
    )


# ---------------------------------------------------------------------------
# player_try_move  (§4.2, 0x41BF0)
# ---------------------------------------------------------------------------

#: The three outcomes a directional probe can resolve to.  ``CLEAR`` covers
#: both "nothing there" and "a door the player just unlocked"; ``SQUEEZED``
#: means the invulnerability corner phase already relocated the player, so
#: ``player_try_move`` must return without applying a delta on top of it.
_PROBE_CLEAR = "clear"
_PROBE_BLOCKED = "blocked"
_PROBE_SQUEEZED = "squeezed"
_PROBE_PUSHED = "pushed"
_PROBE_FIGHTING = "fighting"


def _resolve_probe(state: GameState, player_index: int, result: int,
                   cur_slot: int, delta: int, vertical: bool) -> str:
    """Turn one ``mob_probe_*`` return into a movement outcome (§4.2).

    ``vertical`` selects the up/down reading of 0x0400: those two probes use it
    as the top/bottom boundary sentinel, and a wrapping level treats it as
    clear because ``_apply_pixel_delta`` performs the wrap itself.  The
    left/right probes never return it, and callers must not read it as a slot.
    """
    if result == -1:
        return _PROBE_CLEAR
    if vertical and result == _VERTICAL_BOUNDARY:
        return _PROBE_CLEAR if state.wrap_v else _PROBE_BLOCKED
    if squeeze_through_check(state, result, cur_slot, player_index, delta):
        return _PROBE_SQUEEZED
    if _door_try_traverse(state, player_index, result):
        return _PROBE_CLEAR
    if state.mobs.obj_type(result) == int(MazeObjIds.WALL_MOVABLE):
        if _push_movable_wall(
            state, player_index, result, delta, vertical,
        ):
            return _PROBE_PUSHED
        return _PROBE_BLOCKED
    collision = _player_fight_collision(state, player_index, result)
    if collision == -1:
        return _PROBE_CLEAR
    if collision == 0:
        return _PROBE_BLOCKED
    if collision == 1:
        return _PROBE_FIGHTING
    return _PROBE_BLOCKED


def player_try_move(
    state: GameState,
    player_index: int,
    delta: int,
    movement_flags: int,
    *,
    track_thief: bool = True,
) -> int:
    """0x41BF0 -- collision-checked player movement (§4.2).

    ``delta`` is the active-high direction bitmask from
    ``input.direction_bits`` (JOY_UP | JOY_LEFT etc.).

    Returns 0x00F0 when no movement occurred; any other value when the player
    moved (§4.2, contracts CSV).  The 68010 register-passing conventions in
    the docs are codegen artefacts -- only the logic is ported here.

    Player speed: 2 pixels/frame (not documented in WP-5 sources; flag for
    MAME cross-check at 0x41BF0).
    """
    player = state.players[player_index]
    if player.mob_slot == 0:
        return _NO_MOVE

    # The ROM wrapper decrements movement_type before entering the collision
    # core. main_move_players seeds 2, so the first pass sees 1; recursive retry
    # paths see zero and cannot trigger another squeeze.
    state.movement_type = (state.movement_type - 1) & 0xFFFF

    up    = bool(delta & _JOY_UP)
    down  = bool(delta & _JOY_DOWN)
    left  = bool(delta & _JOY_LEFT)
    right = bool(delta & _JOY_RIGHT)

    if not (up or down or left or right):
        return _NO_MOVE
    direction = _direction_from_input(delta)
    if direction < 8:
        player.direction = (direction - 2) & 0x07

    # Current pixel position and maze slot.
    hpos = state.mobs.hpos[player.mob_slot]
    vpos = state.mobs.vpos[player.mob_slot]
    x = hpos_x(hpos)
    v = vpos_v(vpos)
    speed = _player_speed_units(state, player) >> POS_SHIFT  # 0x580A8 + 0x580B8
    requested_dx = speed * (int(right) - int(left))
    # The V word grows up the screen, so "down" steps the field down.
    requested_dv = speed * (int(up) - int(down))
    dx = 0
    dv = 0
    fight_contact = False
    resolved_contacts: set[int] = set()

    def resolve_once(result: int, cur_slot: int, *, vertical: bool) -> str:
        if 0 <= result < 0x400 and result in resolved_contacts:
            return _PROBE_CLEAR
        outcome = _resolve_probe(
            state, player_index, result, cur_slot, delta, vertical,
        )
        if 0 <= result < 0x400 and outcome is _PROBE_CLEAR:
            resolved_contacts.add(result)
        return outcome

    if requested_dx:
        step_x = 1 if requested_dx > 0 else -1
        probe = mob_probe_right if step_x > 0 else mob_probe_left
        for _ in range(abs(requested_dx)):
            cur_slot = _pixel_to_slot(x + dx, screen_y(v))
            proposed_h = replace_position(
                hpos, encode_hpos(x + dx + step_x),
            )
            h_on_screen, _ = _inside_player_screen_window(
                state, proposed_h, vpos,
            )
            outcome = _PROBE_BLOCKED
            if h_on_screen:
                outcome = resolve_once(
                    probe(state, cur_slot, hpos=proposed_h, vpos=vpos,
                          self_slot=player.mob_slot),
                    cur_slot, vertical=False,
                )
            if outcome is _PROBE_SQUEEZED:
                return 0
            fight_contact |= outcome is _PROBE_FIGHTING
            if outcome in (_PROBE_PUSHED, _PROBE_FIGHTING):
                dx = 0
                break
            if outcome is not _PROBE_CLEAR:
                break
            dx += step_x

    # The ROM applies H before probing V. A diagonal therefore tests the second
    # axis at the already-updated horizontal position and slides the same way.
    # Probe one pixel at a time so a two-pixel frame cannot skip the cell where
    # a wall begins; without this, some approach alignments stopped one pixel
    # inside the wall and then falsely blocked tangential motion.
    temp_h = replace_position(hpos, encode_hpos(x + dx))
    # The original invokes mob_collision_test once from each axis probe. Dedupe
    # only the sub-pixels within one axis; a diagonal may legitimately contact
    # the same surviving object once horizontally and once vertically.
    resolved_contacts.clear()
    if requested_dv:
        step_v = 1 if requested_dv > 0 else -1
        probe = mob_probe_up if step_v > 0 else mob_probe_down
        for _ in range(abs(requested_dv)):
            temp_slot = _pixel_to_slot(x + dx, screen_y(v + dv))
            proposed_v = replace_position(
                vpos, encode_vpos((v + dv + step_v) & 0x1FF),
            )
            _, v_on_screen = _inside_player_screen_window(
                state, temp_h, proposed_v,
            )
            outcome = _PROBE_BLOCKED
            if v_on_screen:
                outcome = resolve_once(
                    probe(
                        state, temp_slot, hpos=temp_h, vpos=proposed_v,
                        self_slot=player.mob_slot,
                    ),
                    temp_slot, vertical=True,
                )
            if outcome is _PROBE_SQUEEZED:
                return 0
            fight_contact |= outcome is _PROBE_FIGHTING
            if outcome in (_PROBE_PUSHED, _PROBE_FIGHTING):
                dv = 0
                break
            if outcome is not _PROBE_CLEAR:
                break
            dv += step_v

    if not fight_contact:
        state.player_fighting_dir[player_index] = 0

    if dx == 0 and dv == 0:
        return _NO_MOVE

    destination = _apply_pixel_delta(state, player_index, dx, -dv)
    if track_thief:
        _track_thief_victim_move(state, player_index, destination)
    moved_dirs = _NO_MOVE
    if dx > 0:
        moved_dirs &= ~_JOY_RIGHT
    elif dx < 0:
        moved_dirs &= ~_JOY_LEFT
    if dv > 0:
        moved_dirs &= ~_JOY_UP
    elif dv < 0:
        moved_dirs &= ~_JOY_DOWN
    return moved_dirs
