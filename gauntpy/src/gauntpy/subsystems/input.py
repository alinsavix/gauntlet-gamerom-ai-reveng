"""Input sampling and debouncing -- ``input_debounce`` (0x40644).

This module is the worked example of a completed work package: one main-loop
call, ported from the documented behaviour, with the ROM's own names kept and
every non-obvious constant cited.

A joystick switch is springy metal, and metal bounces. The original keeps a
16-frame history of each of the two button bits per player, built with a
hand-written ``lsr.w #1,d0`` / ``roxl.w`` pair -- one of the game ROM's few
pieces of hand-written assembly, because no C compiler of the era would emit a
rotate-through-carry.

**The switches are active low**: a raw bit of 0 means pressed. ``roxl.w``
shifts the newest sample into bit 0, so a shift register reads newest-first and
a run of 1s means "released". Getting this backwards inverts every button in
the game, so the polarity is asserted in the tests.

Reference: ``doc/04_game_subsystems.md`` §15 and §6.4;
``doc/08_known_issues.md`` (the 0x1C correction); ``book/06_main_loop.md``.
"""

from __future__ import annotations

from ..state import NUM_PLAYERS, GameState

#: Raw input bit assignments (``05_data_reference.md`` §3.11). The
#: start/join/character-commit press is on the *Magic* line, not Fire --
#: corrected at 0x48402-0x48416 against 0x905F58.
JOY_MAGIC_BIT = 0x01  # bit 0 -> shift register A (0x905F58)
JOY_FIRE_BIT = 0x02   # bit 1 -> shift register B (0x905F60)

JOY_UP = 0x04
JOY_DOWN = 0x08
JOY_LEFT = 0x10
JOY_RIGHT = 0x20
JOY_DIRECTIONS = JOY_UP | JOY_DOWN | JOY_LEFT | JOY_RIGHT

#: All bits high = nothing pressed, because the switches are active low.
JOY_IDLE = 0xFFFF

#: The debounced press edge: ``(debounce_shift_magic & 0x1F) == 0x1C``.
#: 0b11100 is three frames released (older, bits 4-2) followed by two frames
#: held (newest, bits 1-0). Matched by ``main_start_game`` (0x48402) and
#: ``main_handle_potions`` (0x47020).
PRESS_PATTERN = 0x1C
PRESS_MASK = 0x1F


def read_ports(state: GameState) -> list[int]:
    """Sample the four hardware input words (0x803000 + player*2).

    The host writes into ``state.player_input_raw`` before the frame. That
    indirection is the whole reason demo playback works: recorded inputs feed
    through the identical path the hardware would drive (§6.2).
    """
    return state.player_input_raw


def input_debounce(state: GameState) -> None:
    """Sample all four players' controls and update their shift registers."""
    raw_words = read_ports(state)

    for player in range(NUM_PLAYERS):
        raw = raw_words[player] & 0xFFFF
        state.player_input_raw[player] = raw

        # lsr.w #1,d0 ; roxl.w (magic)  -- raw bit 0 into shift register A
        magic_bit = raw & 1
        state.debounce_shift_magic[player] = (
            (state.debounce_shift_magic[player] << 1) | magic_bit
        ) & 0xFFFF

        # lsr.w #1,d0 ; roxl.w (fire)   -- raw bit 1 into shift register B
        fire_bit = (raw >> 1) & 1
        state.debounce_shift_fire[player] = (
            (state.debounce_shift_fire[player] << 1) | fire_bit
        ) & 0xFFFF


# --- readers ------------------------------------------------------------------
#
# Note the deliberate asymmetry, which is in the original: the start/join press
# is debounced, but shooting and steering read the raw word. Atari debounced
# the input that must fire exactly once and left the held inputs raw.

def magic_press_edge(state: GameState, player: int) -> bool:
    """A settled Magic press edge, exactly as ``main_start_game`` tests it."""
    return (state.debounce_shift_magic[player] & PRESS_MASK) == PRESS_PATTERN


def magic_held(state: GameState, player: int) -> bool:
    """Magic held right now (active low: bit clear means pressed)."""
    return not (state.player_input_raw[player] & JOY_MAGIC_BIT)


def fire_held(state: GameState, player: int) -> bool:
    """Fire is gated on the raw bit, not the settled pattern (0x4A9DE)."""
    return not (state.player_input_raw[player] & JOY_FIRE_BIT)


def direction_bits(state: GameState, player: int) -> int:
    """Pressed direction bits, normalized to active *high* for our callers.

    Movement code downstream is far easier to read with 1 = pressed, so the
    inversion happens once, here, rather than in every consumer.
    """
    return ~state.player_input_raw[player] & JOY_DIRECTIONS


def any_direction(state: GameState, player: int) -> bool:
    return bool(direction_bits(state, player))
