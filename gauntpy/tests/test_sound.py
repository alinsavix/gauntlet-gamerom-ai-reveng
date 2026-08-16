"""Sound queue -- WP-18. sound.py implements the queue, not the audio.

These tests pin down the parts other packages will lean on as a test oracle:
sound_play/sound_speech_play append to the live queue, main_update_sound
drains it into a permanent log, and sound_response handles the (largely
trivial, since there is no real sound board) reply side.
"""

from __future__ import annotations

from gauntpy.constants import GameMode
from gauntpy.mainloop import tick
from gauntpy.state import GameState
from gauntpy.subsystems import sound


def test_sound_play_appends_to_the_queue():
    state = GameState()
    sound.sound_play(state, 0x37)
    assert state.sound_queue == [0x37]
    assert state.sound_log == [], "appending must not touch the log directly"


def test_sound_play_preserves_order():
    state = GameState()
    sound.sound_play(state, 0x0D)
    sound.sound_play(state, 0x13)
    assert state.sound_queue == [0x0D, 0x13]


def test_sound_play_masks_to_a_byte():
    state = GameState()
    sound.sound_play(state, 0x137)
    assert state.sound_queue == [0x37]


def test_sound_play_drops_silently_when_the_ring_is_full():
    """Usable capacity is 7 (one slot reserved to distinguish full/empty)."""
    state = GameState()
    for i in range(sound.SOUND_QUEUE_CAPACITY):
        sound.sound_play(state, i)
    assert len(state.sound_queue) == sound.SOUND_QUEUE_CAPACITY

    sound.sound_play(state, 0xAA)  # the eighth attempt

    assert len(state.sound_queue) == sound.SOUND_QUEUE_CAPACITY, "still 7, not 8"
    assert 0xAA not in state.sound_queue, "the overflowing command was dropped"


def test_sound_speech_play_appends_when_speech_is_enabled():
    state = GameState()
    assert state.game_settings & sound.GAME_SETTINGS_SPEECH_DISABLED == 0

    sound.sound_speech_play(state, 0xC4)

    assert state.sound_queue == [0xC4]


def test_sound_speech_play_is_silenced_by_the_operator_bit():
    """game_settings bit 11 is the 'Disable Speech' setting (0x904A24)."""
    state = GameState(game_settings=sound.GAME_SETTINGS_SPEECH_DISABLED)

    sound.sound_speech_play(state, 0xC4)

    assert state.sound_queue == [], "speech must not reach the queue at all"


def test_sound_speech_play_unaffected_by_unrelated_bits():
    state = GameState(game_settings=0x3)  # some other, unrelated setting bits
    sound.sound_speech_play(state, 0x5A)
    assert state.sound_queue == [0x5A]


def test_main_update_sound_drains_the_queue_into_the_log():
    state = GameState()
    sound.sound_play(state, 0x0D)
    sound.sound_play(state, 0x13)

    sound.main_update_sound(state)

    assert state.sound_queue == [], "drain empties the live queue"
    assert state.sound_log == [0x0D, 0x13], "drained commands land in the log, in order"


def test_the_log_is_a_persistent_oracle_not_a_transient_queue():
    """Acceptance: other packages assert 'this event played sound 0x37'."""
    state = GameState()

    sound.sound_play(state, 0x26)  # treasure pickup, §11.5
    sound.main_update_sound(state)

    sound.sound_play(state, 0x13)  # key pickup, §11.5
    sound.main_update_sound(state)

    assert state.sound_log == [0x26, 0x13], "the log accumulates across frames"
    assert 0x26 in state.sound_log, "an earlier event is still provable later"


def test_main_update_sound_stops_at_eight_attempts_per_frame():
    """§11.2: at most eight attempts, whether or not the ring would allow more.

    Bypasses sound_play's own 7-entry cap to exercise main_update_sound's
    independent attempt limit directly.
    """
    state = GameState()
    state.sound_queue = list(range(10))

    sound.main_update_sound(state)

    assert state.sound_log == list(range(sound.SOUND_DRAIN_MAX_ATTEMPTS))
    assert state.sound_queue == [8, 9], "the two leftover entries wait for next frame"


def test_main_update_sound_skips_entirely_on_frame_overflow():
    state = GameState()
    sound.sound_play(state, 0x28)
    state.frame_overflow = 8

    sound.main_update_sound(state)

    assert state.sound_queue == [0x28], "nothing drained while the frame ran long"
    assert state.sound_log == []


def test_main_update_sound_skips_entirely_during_the_recovery_holdoff():
    state = GameState()
    sound.sound_play(state, 0x28)
    state.sound_holdoff = 5

    sound.main_update_sound(state)

    assert state.sound_queue == [0x28]
    assert state.sound_log == []


def test_sound_response_idles_when_nothing_arrives():
    """No byte, no fault bits, no holdoff: only the idle timer moves."""
    state = GameState()
    state.sound_idle_timer = 5

    sound.sound_response(state)

    assert state.sound_idle_timer == 4
    assert state.sound_holdoff == 0
    assert state.sound_queue_state == 0


def test_sound_response_sends_the_status_query_when_idle_timer_expires():
    state = GameState()
    state.sound_idle_timer = 0  # this frame's decrement makes it go negative
    state.sound_retry_count = 9

    sound.sound_response(state)

    assert state.sound_idle_timer == sound.SOUND_IDLE_RELOAD, "reloads to 240 frames"
    assert state.sound_retry_count == 0, "a send always succeeds with no real hardware"
    assert state.sound_queue_state == 0


def test_sound_response_0xff_during_holdoff_clears_it():
    """The board announcing itself alive during the recovery grace period."""
    state = GameState()
    state.sound_holdoff = 42
    state.sound_incoming = [0xFF]

    sound.sound_response(state)

    assert state.sound_holdoff == 0
    assert state.sound_incoming == [], "the byte was consumed"


def test_sound_response_unexpected_byte_during_holdoff_forces_reset():
    state = GameState()
    state.sound_holdoff = 42
    state.sound_queue = [0x11, 0x22]
    state.sound_incoming = [0x03]  # anything but 0xFF

    sound.sound_response(state)

    assert state.sound_holdoff == sound.SOUND_RESET_HOLDOFF, "reset reloads to 180"
    assert state.sound_queue == [], "reset clears the outgoing ring too"


def test_sound_response_unexpected_byte_with_no_holdoff_forces_reset():
    """A byte arriving when the game was not expecting one at all."""
    state = GameState()
    state.sound_holdoff = 0
    state.sound_incoming = [0x07]

    sound.sound_response(state)

    assert state.sound_holdoff == sound.SOUND_RESET_HOLDOFF


def test_sound_response_fault_bits_force_reset():
    """Nonzero low three bits of sound_queue_state are the board's own fault report."""
    state = GameState()
    state.sound_queue_state = 0x02

    sound.sound_response(state)

    assert state.sound_holdoff == sound.SOUND_RESET_HOLDOFF
    assert state.sound_queue_state == 0, "reset clears the fault word"


def test_sound_response_fault_bits_ignore_unrelated_high_bits():
    state = GameState()
    state.sound_queue_state = 0x08  # bit 3 set, low 3 bits clear
    state.sound_idle_timer = 5

    sound.sound_response(state)

    assert state.sound_holdoff == 0, "no reset -- the low 3 bits were clear"
    assert state.sound_idle_timer == 4, "idle countdown still ran"


def test_sound_response_holdoff_decrements_without_reset():
    state = GameState()
    state.sound_holdoff = 5

    sound.sound_response(state)

    assert state.sound_holdoff == 4


def test_sound_response_holdoff_expiring_without_ack_resets_again():
    state = GameState()
    state.sound_holdoff = 1  # this frame's decrement reaches zero

    sound.sound_response(state)

    assert state.sound_holdoff == sound.SOUND_RESET_HOLDOFF, "re-armed, still waiting"


def test_sound_system_reset_clears_queue_holdoff_state_and_retries():
    state = GameState()
    state.sound_queue = [0x01, 0x02]
    state.sound_queue_state = 0x5
    state.sound_retry_count = 99

    sound.sound_system_reset(state)

    assert state.sound_queue == []
    assert state.sound_holdoff == sound.SOUND_RESET_HOLDOFF
    assert state.sound_queue_state == 0
    assert state.sound_retry_count == 0


def test_the_main_loop_actually_calls_sound_response():
    """sound_response runs every frame -- prove it moves the idle timer."""
    state = GameState(game_mode=GameMode.NORMAL)
    state.sound_idle_timer = 5

    tick(state)

    assert state.sound_idle_timer == 4


def test_the_main_loop_actually_calls_main_update_sound():
    state = GameState(game_mode=GameMode.NORMAL)
    state.sound_queue = [0x37]

    tick(state)

    assert state.sound_queue == [], "drained during the frame"
    assert state.sound_log == [0x37], "and logged where a test can find it"
