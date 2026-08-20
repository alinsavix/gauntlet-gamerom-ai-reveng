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


# ---------------------------------------------------------------------------
# Bit assignments and the shift itself, against the ROM
# ---------------------------------------------------------------------------

def test_bit_assignments_match_the_data_reference():
    """doc/05_data_reference.md §3.11, Verified for bits 0, 1 and 4-7 --
    ``joystick_nibble_to_direction`` (0x580FC) decoding all eight compass
    directions is what fixes RIGHT=4, LEFT=5, DOWN=6, UP=7. An earlier reading
    put the directions at bits 2-5, which read the two unconnected spare lines
    for UP/DOWN and swapped LEFT/RIGHT.
    """
    assert (gin.JOY_MAGIC_BIT, gin.JOY_FIRE_BIT) == (0x01, 0x02)
    assert (gin.JOY_RIGHT, gin.JOY_LEFT, gin.JOY_DOWN, gin.JOY_UP) == (
        0x10, 0x20, 0x40, 0x80
    )
    assert gin.JOY_DIRECTIONS == 0xF0
    # Bits 2-3 are JOY_SPARE1/2 and no consumer tests either one.
    assert gin.JOY_DIRECTIONS & 0x0C == 0


def test_the_shift_matches_the_lsr_roxl_pair():
    """ROM 0x40650-0x4065A per player: ``lsr.w #1,d0`` drops raw bit 0 into X
    and ``roxl.w`` rotates it into bit 0 of the magic register; the second
    pair does the same with raw bit 1 and the fire register. Modelled here
    instruction for instruction so the *order* of the two pairs is pinned --
    swapping them would put Fire on the start button.
    """
    state = GameState()
    # Both registers boot released (all ones), because the switches are active
    # low and nothing is pressed.
    magic = state.debounce_shift_magic[0]
    fire = state.debounce_shift_fire[0]
    assert (magic, fire) == (gin.JOY_IDLE, gin.JOY_IDLE)

    words = [0xFFFF, 0xFFFE, 0xFFFD, 0xFFFC, 0xFFFF, 0xAAAA, 0x5555]
    for word in words:
        state.player_input_raw[0] = word
        gin.input_debounce(state)

        d0 = word
        x = d0 & 1            # lsr.w #1,d0
        d0 >>= 1
        magic = ((magic << 1) | x) & 0xFFFF    # roxl.w magic
        x = d0 & 1            # lsr.w #1,d0
        fire = ((fire << 1) | x) & 0xFFFF      # roxl.w fire

        assert state.debounce_shift_magic[0] == magic, hex(word)
        assert state.debounce_shift_fire[0] == fire, hex(word)



def test_the_raw_word_is_truncated_to_a_hardware_word():
    """0x803000 is a word port and 0x904920 a word of RAM; a host that writes
    something wider must not smuggle extra bits into the shift registers."""
    state = GameState()
    state.player_input_raw[0] = 0x1_FFFE
    gin.input_debounce(state)
    assert state.player_input_raw[0] == 0xFFFE
    assert state.debounce_shift_magic[0] & 1 == 0


def test_read_ports_is_the_host_facing_indirection():
    """Demo playback works precisely because recorded input arrives through
    the same array the hardware read would land in (§6.2)."""
    state = GameState()
    assert gin.read_ports(state) is state.player_input_raw


def test_all_four_players_have_their_own_registers():
    state = GameState()
    for player in range(4):
        state.player_input_raw[player] = press(gin.JOY_MAGIC_BIT) if player == 3 else gin.JOY_IDLE
    gin.input_debounce(state)
    assert [state.debounce_shift_magic[p] & 1 for p in range(4)] == [1, 1, 1, 0]
