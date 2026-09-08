"""Game-side player picture selection and its literal ROM animation banks.

These routines write native MOB pictures; host rendering only reads them.
Input, counter advancement, shot creation, and status-8 transitions remain
in players, at their original points in the movement transaction.
"""

from __future__ import annotations

from ..constants import PlayerPower
from ..state import NUM_PLAYERS, GameState


# ``player.direction`` -> the ROM's own ``player_facing_dir`` (0x9049A4)
# encoding, which 05_data_reference documents as 0=up, 1=up-right, 2=right,
# 3=down-right, 4=down, 5=down-left, 6=left, 7=up-left.  Every ROM table keyed
# by facing (shot picture, shot spawn offset) is indexed through this map.  The
# port keeps its own encoding in ``Player.direction`` because ``play.py`` and
# the level-transition tests already render from it.
_PORT_DIR_TO_ROM_DIR = [2, 3, 4, 5, 6, 7, 0, 1]
# anim_table_idle -- ROM 0x58A4A, 4 characters x 8 facing directions, indexed
# ``character * 8 + frame`` by the first half of
# the status-0x08 branch at 0x4A696: the hero spins from its facing direction
# down to 4, one step per four frames.
_ANIM_TABLE_IDLE = [
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
_ANIM_TABLE_WALKING = _rom_picture_table("""
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
_ANIM_TABLE_FIGHTING = _rom_picture_table("""
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
_ANIM_TABLE_SHOOTING = _rom_picture_table("""
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

# Freeze the literal list as the tuple used by both idle and death-spin readers.
_ANIM_TABLE_IDLE = tuple(_ANIM_TABLE_IDLE)

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
        picture = _ANIM_TABLE_FIGHTING[
            character * 64 + rom_direction * 8 + ((counter >> 1) & 0x07)
        ]
    elif action == "walk":
        picture = _ANIM_TABLE_WALKING[
            character * 32 + rom_direction * 4 + ((counter >> 2) & 0x03)
        ]
    elif action == "shoot":
        picture = _ANIM_TABLE_SHOOTING[
            character * 32 + rom_direction * 4 + ((counter >> 2) & 0x03)
        ]
    else:
        picture = _ANIM_TABLE_IDLE[character * 8 + rom_direction]

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
