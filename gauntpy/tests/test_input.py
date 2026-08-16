"""Input debouncing -- the worked-example subsystem.

The switches are active low, which is easy to get backwards and inverts every
button in the game when you do. These tests pin the polarity down.
"""

from __future__ import annotations

from gauntpy.constants import GameMode
from gauntpy.mainloop import tick
from gauntpy.state import GameState
from gauntpy.subsystems import input as gin


def press(*bits: int) -> int:
    """A raw input word with the given bits pressed (active low: cleared)."""
    word = gin.JOY_IDLE
    for bit in bits:
        word &= ~bit
    return word & 0xFFFF


def run_frames(state: GameState, frames: int) -> None:
    for _ in range(frames):
        gin.input_debounce(state)


def test_idle_shifts_in_ones():
    """Nothing pressed means the register fills with 1s, not 0s."""
    state = GameState()
    run_frames(state, 4)
    assert state.debounce_shift_magic[0] == 0xFFFF
    assert state.debounce_shift_fire[0] == 0xFFFF


def test_pressing_shifts_in_zeros():
    state = GameState()
    run_frames(state, 8)
    state.player_input_raw[0] = press(gin.JOY_MAGIC_BIT)
    run_frames(state, 3)

    assert state.debounce_shift_magic[0] & 0x7 == 0b000, "three held frames"
    assert state.debounce_shift_magic[0] & 0x8, "the frame before was released"


def test_bits_do_not_cross_registers():
    """Bit 0 is Magic, bit 1 is Fire."""
    state = GameState()
    state.player_input_raw[0] = press(gin.JOY_MAGIC_BIT)
    run_frames(state, 3)

    assert state.debounce_shift_magic[0] & 0x7 == 0
    assert state.debounce_shift_fire[0] & 0x7 == 0x7, "fire untouched"


def test_fire_bit_is_independent():
    state = GameState()
    state.player_input_raw[2] = press(gin.JOY_FIRE_BIT)
    run_frames(state, 4)

    assert state.debounce_shift_fire[2] & 0xF == 0
    assert state.debounce_shift_magic[2] & 0xF == 0xF


def test_registers_hold_sixteen_frames():
    state = GameState()
    state.player_input_raw[1] = press(gin.JOY_MAGIC_BIT)
    run_frames(state, 40)
    assert state.debounce_shift_magic[1] == 0, "saturates at 16 bits, no overflow"


def test_players_are_independent():
    state = GameState()
    state.player_input_raw = [
        press(gin.JOY_MAGIC_BIT), gin.JOY_IDLE, press(gin.JOY_FIRE_BIT), gin.JOY_IDLE
    ]
    run_frames(state, 2)

    assert state.debounce_shift_magic[0] & 0x3 == 0
    assert state.debounce_shift_magic[1] & 0x3 == 0x3
    assert state.debounce_shift_fire[2] & 0x3 == 0
    assert state.debounce_shift_fire[3] & 0x3 == 0x3


def test_the_settled_press_edge():
    """main_start_game matches 0x1C: three released frames then two held."""
    state = GameState()
    run_frames(state, 8)
    assert not gin.magic_press_edge(state, 0)

    state.player_input_raw[0] = press(gin.JOY_MAGIC_BIT)
    run_frames(state, 2)

    assert state.debounce_shift_magic[0] & gin.PRESS_MASK == gin.PRESS_PATTERN
    assert gin.magic_press_edge(state, 0)


def test_press_edge_fires_once_not_while_held():
    state = GameState()
    run_frames(state, 8)
    state.player_input_raw[0] = press(gin.JOY_MAGIC_BIT)

    edges = []
    for _ in range(10):
        gin.input_debounce(state)
        edges.append(gin.magic_press_edge(state, 0))

    assert edges.count(True) == 1, "a held button must not repeat the edge"
    assert edges[1] is True, "and it fires on the second held frame"


def test_bounce_never_registers_a_press():
    """A chattering contact must never produce the settled pattern."""
    state = GameState()
    for frame in range(20):
        state.player_input_raw[0] = gin.JOY_IDLE if frame % 2 else press(gin.JOY_MAGIC_BIT)
        gin.input_debounce(state)
        assert not gin.magic_press_edge(state, 0)


def test_held_readers_use_the_raw_word():
    state = GameState()
    assert not gin.fire_held(state, 0)
    assert not gin.magic_held(state, 0)

    state.player_input_raw[0] = press(gin.JOY_FIRE_BIT)
    assert gin.fire_held(state, 0)
    assert not gin.magic_held(state, 0)


def test_direction_bits_are_normalized_to_active_high():
    state = GameState()
    assert gin.direction_bits(state, 0) == 0
    assert not gin.any_direction(state, 0)

    state.player_input_raw[0] = press(gin.JOY_UP, gin.JOY_LEFT, gin.JOY_MAGIC_BIT)
    assert gin.direction_bits(state, 0) == gin.JOY_UP | gin.JOY_LEFT
    assert gin.any_direction(state, 0)


def test_the_main_loop_actually_calls_it():
    state = GameState(game_mode=GameMode.NORMAL)
    state.player_input_raw[0] = press(gin.JOY_MAGIC_BIT)
    tick(state)
    assert state.debounce_shift_magic[0] & 1 == 0
