"""Shared treasure/secret-room boundaries and objective constants."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Level-flag bit masks (byte-level, as stored in GameState)
# ---------------------------------------------------------------------------

# LFLAG3_EXIT_MOVES = 1 << 14 in the 32-bit longword at 0x90491C.
# LFLAG3 is the third byte (bits 15-8 of the longword), so bit 14 in the
# longword = bit 6 of the LFLAG3 byte.
# Reference: gex.constants.LFLAG3_EXIT_MOVES; doc/04_game_subsystems.md §12.2
_LFLAG3_EXIT_MOVES = 0x40   # bit 6 of level_flags_3 byte

# Maze-number bands (doc/06 §3.5, §6).  Everything >= 104 is a bonus room; the
# treasure rooms are 104-114 and the two secret rooms are 115/116.
_TREASURE_MAZE_FIRST = 0x68   # 104
_SECRET_MAZE_FIRST = 0x73     # 115
