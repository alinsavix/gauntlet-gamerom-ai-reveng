"""Recorded demo input, cursor advancement, and per-consumer input selection."""

from __future__ import annotations

from ..constants import GameMode
from ..state import NUM_PLAYERS, GameState
from .input import direction_bits, fire_held
from .player_lifecycle import player_join


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
# Playback advances ``demo_timer`` and ``demo_ptr`` and dispatches caption/join
# records; it never overwrites the hardware joystick sample. Consumers reach the
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

_DEMO_RECORD_MESSAGE = 0xFF          # 0x4A59E
_DEMO_RECORD_JOIN = 0xFE            # 0x4A5A2 falls through to the join branch
_DEMO_RECORD_MAX_ORDINARY = 0xFD    # 0x4A58E: ``cmpi.b #$fd`` / ``bls``
_DEMO_JOIN_KICKOFF_TIMER = 1        # 0x4A5CC: the joined slot expires next frame

#: All bits high = nothing pressed, matching ``input.JOY_IDLE``.
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
    other mode it *is* the hardware sample. Other button/direction consumers
    select the same source independently, without overwriting hardware input.
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
    a join record starts someone else. ``_demo_playback`` uses this to arm the
    slot selected by attract setup.
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
    # 0x44A38-0x44A48: attract_demo_init arms one slot. Attract setup installs the
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
            if code == _DEMO_RECORD_MESSAGE:
                from .score import demo_message_show

                demo_message_show(state, player_index, payload)
                continue
            _demo_join_record(state, payload)
