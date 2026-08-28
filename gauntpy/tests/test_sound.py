"""Sound -- WP-18. sound.py implements the command engine, not the audio.

These tests pin down the parts other packages will lean on as a test oracle.
The central fact is §11.1's fast path: with the recovery holdoff clear,
``sound_play`` hands the byte straight to the board and does **not** queue it,
so ``sound_log`` -- not ``soundqueue`` -- is the record of what was emitted.
The ring is the fallback for a busy latch or a nonzero holdoff, and
``main_update_sound`` drains it into that same log.
"""

from __future__ import annotations

from gauntpy.constants import GameMode
from gauntpy.mainloop import tick
from gauntpy.state import GameState
from gauntpy.subsystems import sound


def _busy_latch(monkeypatch):
    """Make the board latch report busy, so sound_play takes the ring path."""
    monkeypatch.setattr(sound, "try_send_sound_command", lambda _s, _c: False)


def _queue_through_the_busy_fallback(state, *sound_ids):
    """Fill the ring the way the game does when the latch is busy (§11.1)."""
    original = sound.try_send_sound_command
    sound.try_send_sound_command = lambda _s, _c: False
    try:
        for sound_id in sound_ids:
            sound.sound_play(state, sound_id)
    finally:
        sound.try_send_sound_command = original


# ---------------------------------------------------------------------------
# sound_play, §11.1: immediate send when the holdoff is clear, ring otherwise.
# ---------------------------------------------------------------------------

def test_sound_play_sends_immediately_when_the_latch_accepts():
    """§11.1: "an immediately accepted command is not queued"."""
    state = GameState()
    assert state.speech_counter == 0, "the fast path needs a clear holdoff"

    sound.sound_play(state, 0x37)

    assert state.sound_log == [0x37], "the board got the byte this instant"
    assert state.soundqueue == [], "and it never touched the ring"


def test_an_accepted_command_is_logged_exactly_once():
    """The immediate send is the delivery; the drain must not repeat it."""
    state = GameState()

    sound.sound_play(state, 0x37)
    sound.main_update_sound(state)

    assert state.sound_log == [0x37]
    assert state.sound_log.count(0x37) == 1, "logged by exactly one path"


def test_sound_play_offers_the_masked_byte_to_the_latch(monkeypatch):
    """The latch is one byte wide, so the offer is the masked value."""
    state = GameState()
    seen = []

    def recording(_state, command):
        seen.append(command)
        return True

    monkeypatch.setattr(sound, "try_send_sound_command", recording)

    sound.sound_play(state, 0x137)

    assert seen == [0x37], "the send got the masked byte, not 0x137"
    assert state.sound_log == [0x37]


def test_sound_play_preserves_order_on_the_fast_path():
    state = GameState()
    sound.sound_play(state, 0x0D)
    sound.sound_play(state, 0x13)
    assert state.sound_log == [0x0D, 0x13]
    assert state.soundqueue == []


def test_sound_play_masks_to_a_byte():
    state = GameState()
    sound.sound_play(state, 0x137)
    assert state.sound_log == [0x37]


def test_sound_play_masks_to_a_byte_on_the_ring_path_too(monkeypatch):
    state = GameState()
    _busy_latch(monkeypatch)

    sound.sound_play(state, 0x137)

    assert state.soundqueue == [0x37]


def test_a_busy_latch_falls_back_to_the_ring(monkeypatch):
    """§11.1: "a busy result falls back to the ring"."""
    state = GameState()
    _busy_latch(monkeypatch)

    sound.sound_play(state, 0x37)

    assert state.soundqueue == [0x37], "parked on the ring for the drain"
    assert state.sound_log == [], "nothing reached the board yet"


def test_a_busy_fallback_reaches_the_log_only_when_the_drain_gets_it(monkeypatch):
    state = GameState()
    _busy_latch(monkeypatch)
    sound.sound_play(state, 0x37)
    monkeypatch.setattr(sound, "try_send_sound_command", lambda _s, _c: True)

    sound.main_update_sound(state)

    assert state.soundqueue == []
    assert state.sound_log == [0x37], "delivered once, by the drain"


def test_a_nonzero_holdoff_queues_directly_without_offering_the_byte(monkeypatch):
    """§11.1: "While speech traffic is active it skips the immediate attempt
    and queues directly" -- 0x9049EE is read at 0x4AD7E before the send."""
    state = GameState()
    state.speech_counter = 5
    calls = {"n": 0}

    def counting(_state, _command):
        calls["n"] += 1
        return True

    monkeypatch.setattr(sound, "try_send_sound_command", counting)

    sound.sound_play(state, 0x37)

    assert calls["n"] == 0, "the holdoff skips the immediate attempt entirely"
    assert state.soundqueue == [0x37]
    assert state.sound_log == []


def test_the_holdoff_gate_reopens_the_fast_path_when_it_clears():
    state = GameState()
    state.speech_counter = 1
    sound.sound_play(state, 0x11)
    assert state.soundqueue == [0x11]

    state.speech_counter = 0
    sound.sound_play(state, 0x22)

    assert state.sound_log == [0x22], "the second command went straight out"
    assert state.soundqueue == [0x11], "the first is still parked on the ring"


def test_sound_play_drops_silently_when_the_ring_is_full():
    """Usable capacity is 7 (one slot reserved to distinguish full/empty).

    Only the ring path can overflow, so the holdoff is armed to keep every
    command on it.
    """
    state = GameState()
    state.speech_counter = 10
    for i in range(sound.SOUND_QUEUE_CAPACITY):
        sound.sound_play(state, i)
    assert len(state.soundqueue) == sound.SOUND_QUEUE_CAPACITY

    sound.sound_play(state, 0xAA)  # the eighth attempt

    assert len(state.soundqueue) == sound.SOUND_QUEUE_CAPACITY, "still 7, not 8"
    assert 0xAA not in state.soundqueue, "the overflowing command was dropped"
    assert state.sound_log == [], "and it was never emitted either"


def test_the_busy_fallback_drops_on_a_full_ring_as_well(monkeypatch):
    state = GameState()
    _busy_latch(monkeypatch)

    for i in range(sound.SOUND_QUEUE_CAPACITY + 1):
        sound.sound_play(state, 0x50 + i)

    assert state.soundqueue == [0x50 + i for i in range(sound.SOUND_QUEUE_CAPACITY)]
    assert (0x50 + sound.SOUND_QUEUE_CAPACITY) not in state.soundqueue


def test_enqueue_sound_is_the_ring_primitive_sound_play_falls_back_to():
    """0x4ADD6: append if there is room, drop silently otherwise."""
    state = GameState()
    for i in range(sound.SOUND_QUEUE_CAPACITY):
        sound.enqueue_sound(state, i)
    sound.enqueue_sound(state, 0x1AA)

    assert state.soundqueue == list(range(sound.SOUND_QUEUE_CAPACITY))
    assert state.sound_log == [], "the ring is not the board"


def test_an_immediate_send_jumps_ahead_of_anything_still_on_the_ring():
    """The ring only holds what the latch refused, so a command accepted now
    genuinely reaches the board before bytes still waiting for the drain."""
    state = GameState()
    state.speech_counter = 3
    sound.sound_play(state, 0xA1)
    sound.sound_play(state, 0xA2)

    state.speech_counter = 0
    sound.sound_play(state, 0xB0)          # accepted immediately
    assert state.sound_log == [0xB0]

    sound.main_update_sound(state)         # now the ring drains, in order

    assert state.sound_log == [0xB0, 0xA1, 0xA2]
    assert state.soundqueue == []


def test_sound_speech_play_emits_when_speech_is_enabled():
    state = GameState()
    assert state.game_settings & sound.GAME_SETTINGS_SPEECH_DISABLED == 0

    sound.sound_speech_play(state, 0xC4)

    assert state.sound_log == [0xC4], "speech takes sound_play's fast path"
    assert state.soundqueue == []


def test_sound_speech_play_is_silenced_by_the_operator_bit():
    """game_settings bit 11 is the 'Disable Speech' setting (0x904A24)."""
    state = GameState(game_settings=sound.GAME_SETTINGS_SPEECH_DISABLED)

    sound.sound_speech_play(state, 0xC4)

    assert state.sound_log == [], "speech must not reach the board"
    assert state.soundqueue == [], "nor the ring"


def test_sound_speech_play_is_silenced_on_the_ring_path_too():
    """The gate is in front of sound_play, so the holdoff cannot leak it."""
    state = GameState(game_settings=sound.GAME_SETTINGS_SPEECH_DISABLED)
    state.speech_counter = 5

    sound.sound_speech_play(state, 0xC4)

    assert state.soundqueue == []
    assert state.sound_log == []


def test_sound_speech_play_queues_behind_a_holdoff_when_enabled():
    state = GameState()
    state.speech_counter = 5

    sound.sound_speech_play(state, 0xC4)

    assert state.soundqueue == [0xC4]
    assert state.sound_log == []


def test_sound_speech_play_unaffected_by_unrelated_bits():
    state = GameState(game_settings=0x3)  # some other, unrelated setting bits
    sound.sound_speech_play(state, 0x5A)
    assert state.sound_log == [0x5A]


def test_main_update_sound_drains_the_queue_into_the_log():
    state = GameState()
    _queue_through_the_busy_fallback(state, 0x0D, 0x13)
    assert state.soundqueue == [0x0D, 0x13]

    sound.main_update_sound(state)

    assert state.soundqueue == [], "drain empties the live queue"
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


def test_both_paths_land_in_one_ordered_log():
    """Whichever way a command went out, the oracle records it once."""
    state = GameState()

    sound.sound_play(state, 0x01)                 # immediate
    _queue_through_the_busy_fallback(state, 0x02)  # ring
    sound.sound_play(state, 0x03)                 # immediate again
    sound.main_update_sound(state)                # ring drains last

    assert state.sound_log == [0x01, 0x03, 0x02]
    assert state.soundqueue == []


def test_main_update_sound_stops_at_eight_attempts_per_frame():
    """§11.2: at most eight attempts, whether or not the ring would allow more.

    Bypasses sound_play's own 7-entry cap to exercise main_update_sound's
    independent attempt limit directly.
    """
    state = GameState()
    state.soundqueue = list(range(10))

    sound.main_update_sound(state)

    assert state.sound_log == list(range(sound.SOUND_DRAIN_MAX_ATTEMPTS))
    assert state.soundqueue == [8, 9], "the two leftover entries wait for next frame"


def test_main_update_sound_skips_entirely_on_frame_overflow():
    state = GameState()
    _queue_through_the_busy_fallback(state, 0x28)
    state.frame_overflow = 8

    sound.main_update_sound(state)

    assert state.soundqueue == [0x28], "nothing drained while the frame ran long"
    assert state.sound_log == []


def test_main_update_sound_skips_entirely_during_the_recovery_holdoff():
    state = GameState()
    state.speech_counter = 5
    sound.sound_play(state, 0x28)       # holdoff sends it to the ring (§11.1)

    sound.main_update_sound(state)

    assert state.soundqueue == [0x28]
    assert state.sound_log == []


# ---------------------------------------------------------------------------
# The busy-latch ladder (§11.2, "Contradicted and corrected"). No real board
# ever reports busy, so the send is a substitutable seam -- that is what makes
# the documented behaviour testable instead of merely commented.
# ---------------------------------------------------------------------------

def test_a_busy_latch_costs_an_attempt_but_leaves_the_read_head_alone(monkeypatch):
    """§11.2: the failure branch falls through to the attempt counter and
    re-offers the same byte; it does not advance the read head or end the
    drain."""
    state = GameState()
    state.soundqueue = [0x37, 0x38]
    monkeypatch.setattr(sound, "try_send_sound_command", lambda _s, _c: False)

    sound.main_update_sound(state)

    assert state.soundqueue == [0x37, 0x38], "nothing consumed while the latch was busy"
    assert state.sound_log == []


def test_a_latch_that_frees_up_mid_frame_still_drains_within_the_eight_attempts():
    state = GameState()
    state.soundqueue = [0x37, 0x38]
    busy = {"left": 3}

    def flaky(_state, _command):
        if busy["left"]:
            busy["left"] -= 1
            return False
        return True

    original = sound.try_send_sound_command
    sound.try_send_sound_command = flaky
    try:
        sound.main_update_sound(state)
    finally:
        sound.try_send_sound_command = original

    # Three busy attempts + two accepted = five of the eight.
    assert state.sound_log == [0x37, 0x38]
    assert state.soundqueue == []


def test_busy_attempts_are_capped_at_eight_per_frame(monkeypatch):
    calls = {"n": 0}

    def counting(_state, _command):
        calls["n"] += 1
        return False

    state = GameState()
    state.soundqueue = [0x01]
    monkeypatch.setattr(sound, "try_send_sound_command", counting)

    sound.main_update_sound(state)

    assert calls["n"] == sound.SOUND_DRAIN_MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# The status-query retry ladder (§11.3).
# ---------------------------------------------------------------------------

def test_a_failed_status_send_retries_next_frame_and_counts_the_attempt(monkeypatch):
    """§11.3: "A failed send clears the timer so the next frame retries
    immediately and increments the retry count"."""
    state = GameState()
    state.sound_idle_timer = 0
    monkeypatch.setattr(sound, "send_status_query", lambda _s: False)

    sound.sound_response(state)

    assert state.sound_idle_timer == 0, "cleared, so the next frame retries at once"
    assert state.sound_cpu_retry_count == 1
    assert state.speech_counter == 0, "one failure is not yet a reset"


def test_the_retry_count_forces_a_full_reset_above_the_threshold(monkeypatch):
    """§11.3: "above 0xB4 (180) it performs a full reset" -- strictly above."""
    state = GameState()
    state.sound_idle_timer = 0
    state.sound_cpu_retry_count = sound.SOUND_RETRY_LIMIT - 1
    state.soundqueue = [0x11]
    monkeypatch.setattr(sound, "send_status_query", lambda _s: False)

    sound.sound_response(state)          # count reaches exactly 0xB4
    assert state.sound_cpu_retry_count == sound.SOUND_RETRY_LIMIT
    assert state.speech_counter == 0, "0xB4 itself is not above 0xB4"

    state.sound_idle_timer = 0
    sound.sound_response(state)          # count passes 0xB4
    assert state.speech_counter == sound.SOUND_RESET_HOLDOFF
    assert state.sound_cpu_retry_count == 0, "the reset clears the count"
    assert state.soundqueue == [], "and the ring"


def test_the_status_query_clears_the_fault_word_before_polling(monkeypatch):
    """The reply's low three bits must be this poll's fault report, so the word
    is cleared before the send regardless of whether the send works."""
    state = GameState()
    state.sound_idle_timer = 0
    state.sound_queue_state = 0x08       # bit 3: not a fault bit, survives the gate
    monkeypatch.setattr(sound, "send_status_query", lambda _s: False)

    sound.sound_response(state)

    assert state.sound_queue_state == 0


def test_a_successful_send_reloads_and_clears_any_accumulated_retries():
    state = GameState()
    state.sound_idle_timer = 0
    state.sound_cpu_retry_count = 42

    sound.sound_response(state)

    assert state.sound_idle_timer == sound.SOUND_IDLE_RELOAD
    assert state.sound_cpu_retry_count == 0


def test_the_documented_command_ids_are_the_ones_the_catalog_gives():
    """§11.3: 0x00 reinitialize/stop-all, 0x06 the command-count query
    (replies 0xDB, the exclusive upper bound of the 219 IDs), 0x07 the
    diagnostic fault query."""
    assert sound.SOUND_REINITIALIZE == 0x00
    assert sound.SOUND_COMMAND_COUNT_QUERY == 0x06
    assert sound.SOUND_DIAGNOSTIC_QUERY == 0x07


def test_reinitialize_takes_the_ordinary_path():
    """§11.3: "Command 0x00 follows the ordinary queue path but dispatches to a
    full engine reinitialization" -- it is not special-cased, so it uses
    whichever of §11.1's two paths is open, like any other command."""
    state = GameState()
    sound.sound_play(state, sound.SOUND_REINITIALIZE)
    assert state.sound_log == [0x00], "sent immediately, like anything else"
    assert state.soundqueue == []

    held = GameState()
    held.speech_counter = 4
    sound.sound_play(held, sound.SOUND_REINITIALIZE)
    assert held.soundqueue == [0x00], "and rings up behind a holdoff, like anything else"

    held.speech_counter = 0
    sound.main_update_sound(held)
    assert held.sound_log == [0x00]


def test_sound_response_idles_when_nothing_arrives():
    """No byte, no fault bits, no holdoff: only the idle timer moves."""
    state = GameState()
    state.sound_idle_timer = 5

    sound.sound_response(state)

    assert state.sound_idle_timer == 4
    assert state.speech_counter == 0
    assert state.sound_queue_state == 0


def test_sound_response_sends_the_status_query_when_idle_timer_expires():
    state = GameState()
    state.sound_idle_timer = 0  # this frame's decrement makes it go negative
    state.sound_cpu_retry_count = 9

    sound.sound_response(state)

    assert state.sound_idle_timer == sound.SOUND_IDLE_RELOAD, "reloads to 240 frames"
    assert state.sound_cpu_retry_count == 0, "a send always succeeds with no real hardware"
    assert state.sound_queue_state == 0


def test_sound_response_0xff_during_holdoff_clears_it():
    """The board announcing itself alive during the recovery grace period."""
    state = GameState()
    state.speech_counter = 42
    state.sound_incoming = [0xFF]

    sound.sound_response(state)

    assert state.speech_counter == 0
    assert state.sound_incoming == [], "the byte was consumed"


def test_sound_response_unexpected_byte_during_holdoff_forces_reset():
    state = GameState()
    state.speech_counter = 42
    state.soundqueue = [0x11, 0x22]
    state.sound_incoming = [0x03]  # anything but 0xFF

    sound.sound_response(state)

    assert state.speech_counter == sound.SOUND_RESET_HOLDOFF, "reset reloads to 180"
    assert state.soundqueue == [], "reset clears the outgoing ring too"


def test_sound_response_unexpected_byte_with_no_holdoff_forces_reset():
    """A byte arriving when the game was not expecting one at all."""
    state = GameState()
    state.speech_counter = 0
    state.sound_incoming = [0x07]

    sound.sound_response(state)

    assert state.speech_counter == sound.SOUND_RESET_HOLDOFF


def test_sound_response_fault_bits_force_reset():
    """Nonzero low three bits of sound_queue_state are the board's own fault report."""
    state = GameState()
    state.sound_queue_state = 0x02

    sound.sound_response(state)

    assert state.speech_counter == sound.SOUND_RESET_HOLDOFF
    assert state.sound_queue_state == 0, "reset clears the fault word"


def test_sound_response_fault_bits_ignore_unrelated_high_bits():
    state = GameState()
    state.sound_queue_state = 0x08  # bit 3 set, low 3 bits clear
    state.sound_idle_timer = 5

    sound.sound_response(state)

    assert state.speech_counter == 0, "no reset -- the low 3 bits were clear"
    assert state.sound_idle_timer == 4, "idle countdown still ran"


def test_sound_response_holdoff_decrements_without_reset():
    state = GameState()
    state.speech_counter = 5

    sound.sound_response(state)

    assert state.speech_counter == 4


def test_sound_response_holdoff_expiring_without_ack_resets_again():
    state = GameState()
    state.speech_counter = 1  # this frame's decrement reaches zero

    sound.sound_response(state)

    assert state.speech_counter == sound.SOUND_RESET_HOLDOFF, "re-armed, still waiting"


def test_sound_system_reset_clears_queue_holdoff_state_and_retries():
    state = GameState()
    state.soundqueue = [0x01, 0x02]
    state.sound_queue_state = 0x5
    state.sound_cpu_retry_count = 99

    sound.sound_system_reset(state)

    assert state.soundqueue == []
    assert state.speech_counter == sound.SOUND_RESET_HOLDOFF
    assert state.sound_queue_state == 0
    assert state.sound_cpu_retry_count == 0


def test_the_main_loop_actually_calls_sound_response():
    """sound_response runs every frame -- prove it moves the idle timer."""
    state = GameState(game_mode=GameMode.NORMAL)
    state.sound_idle_timer = 5

    tick(state)

    assert state.sound_idle_timer == 4


def test_the_main_loop_actually_calls_main_update_sound():
    state = GameState(game_mode=GameMode.NORMAL)
    state.soundqueue = [0x37]

    tick(state)

    assert state.soundqueue == [], "drained during the frame"
    assert state.sound_log == [0x37], "and logged where a test can find it"
