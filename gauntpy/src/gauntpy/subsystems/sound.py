"""Sound -- WP-18. Stubbed: the queue is real, the audio is not.

Implement the command queue, not the synthesis. Every emitted command gets
logged, which turns sound into a **test oracle** for the other packages ("this
event plays sound 0x37") rather than dead weight.

219 command IDs (0x00-0xDA); command 0x00 is reinitialize/stop-all, 0x06 the
command-count query (replies 0xDB), 0x07 the diagnostic fault query.

The original's ``sound_play`` (§11.1) has a hardware fast path: when the
sound-board latch is free it sends the command immediately instead of queuing
it. There is no real latch in this simulation -- no code ever reports
"busy" -- so that optimization has nothing to bypass. Per the WP-18 brief
("``sound_play(id)`` appends, the drain call consumes"), every command here
always takes the ring path; capacity and drop-when-full behaviour are
preserved exactly.

Reference: ``doc/04_game_subsystems.md`` §11; ``refs/soundcmds.csv``;
``book/16_sound.md``.
"""

from __future__ import annotations

from ..state import GameState

# --- catalog (refs/soundcmds.csv; doc §11.3, §11.5) -------------------------
#
# ``refs/soundcmds.csv`` is authoritative for these three: it carries the
# corrected CONTROL labels, while ``doc/generated/soundcmds.csv`` still shows
# them as "UNK ... (Used in self-test)" -- the machine-generated table predates
# the MAME/6502 tracing that pinned these down (§11.3).
SOUND_REINITIALIZE = 0x00     # full sound-engine reinit / stop-all (§11.3, §11.5)
SOUND_COMMAND_COUNT_QUERY = 0x06  # replies 0xDB, exclusive upper bound of IDs (§11.3)
SOUND_DIAGNOSTIC_QUERY = 0x07     # fault-bitmap query; arms liveness sentinels (§11.3)

#: Physical ring has 8 slots (0x90404B) but reserves one to distinguish full
#: from empty, so usable capacity is 7. A full ring drops the new byte
#: silently. §11.1-11.2.
SOUND_QUEUE_CAPACITY = 7

#: main_update_sound makes at most eight attempts per frame before giving up,
#: whether or not the ring is empty. §11.2.
SOUND_DRAIN_MAX_ATTEMPTS = 8

#: sound_system_reset's holdoff reload -- 180 frames (0x42DDA). §11.3.
SOUND_RESET_HOLDOFF = 0xB4

#: Idle-timer reload after a successful status-query send -- 240 frames. §11.3.
SOUND_IDLE_RELOAD = 0xF0

#: Consecutive failed-send retry threshold before a full reset. §11.3.
SOUND_RETRY_LIMIT = 0xB4

#: game_settings (0x904A24) bit 11 -- the operator "Disable Speech" setting.
#: sound_speech_play calls sound_play only when this bit is clear. §11.4.
GAME_SETTINGS_SPEECH_DISABLED = 1 << 11

#: The "no response this poll" sentinel OS 0x178 (read_sound_data) returns.
#: §11.3.
SOUND_NO_RESPONSE = 0xFFFF


def sound_play(state: GameState, sound_id: int) -> None:
    """0x4AD76 -- queue a sound command. Called from all over the game.

    Corresponds to the ring fallback path (``enqueue_sound``, 0x4ADD6): append
    if there is room, otherwise drop silently. See the module docstring for
    why the immediate-dispatch fast path is not modelled.
    """
    sound_id &= 0xFF
    if len(state.sound_queue) < SOUND_QUEUE_CAPACITY:
        state.sound_queue.append(sound_id)
    # else: ring full, command dropped without complaint (§11.2)


def sound_speech_play(state: GameState, speech_id: int) -> None:
    """0x4AD4E -- queue a speech command. See §11.4.

    Calls ``sound_play`` only when the "Disable Speech" operator setting
    (game_settings bit 11) is clear.
    """
    if not (state.game_settings & GAME_SETTINGS_SPEECH_DISABLED):
        sound_play(state, speech_id)


def sound_system_reset(state: GameState) -> None:
    """0x42DC8 -- reset the sound engine after a dead or unexpected board.

    Calls OS 0x254 with (0, 0) on real hardware (nothing to simulate here),
    sets the 180-frame recovery holdoff, clears the fault-report word and the
    retry count, and resets the outgoing ring (``sound_queue_reset``,
    0x4ADAE: fills the physical ring with 0xFF and zeroes both indices --
    equivalent here to emptying the Python queue). §11.3.
    """
    state.sound_queue.clear()
    state.sound_holdoff = SOUND_RESET_HOLDOFF
    state.sound_queue_state = 0
    state.sound_retry_count = 0


def sound_response(state: GameState) -> None:
    """0x42D0A -- process replies from the sound board. See §11.3.

    Polls OS 0x178 for one byte; no response is reported as 0xFFFF. There is
    no real sound board in this simulation, so a byte only "arrives" when a
    test pushes one onto ``state.sound_incoming`` -- in ordinary play this
    routine only ever walks the idle-countdown branch, which is why the
    WP-18 brief calls this side "largely trivial".
    """
    if state.sound_incoming:
        byte = state.sound_incoming.pop(0) & 0xFF
    else:
        byte = SOUND_NO_RESPONSE

    if byte != SOUND_NO_RESPONSE:
        if state.sound_holdoff:
            if byte == 0xFF:
                state.sound_holdoff = 0  # the board is back (§11.3)
            else:
                sound_system_reset(state)
        else:
            sound_system_reset(state)  # unexpected traffic
        return

    # Idle handling -- no byte arrived this frame.
    if state.sound_queue_state & 0x7:
        sound_system_reset(state)  # the board's own fault report
        return

    if state.sound_holdoff:
        state.sound_holdoff -= 1
        if state.sound_holdoff == 0:
            sound_system_reset(state)  # holdoff expired with no 0xFF ack
        return

    state.sound_idle_timer -= 1
    if state.sound_idle_timer < 0:
        state.sound_queue_state = 0
        # Status query (command 0x07) sent through OS 0x172. No real sound
        # board exists in this simulation, so the send always succeeds --
        # the documented failed-send/retry-count path (§11.3) has nothing to
        # trigger it here and is not modelled.
        state.sound_idle_timer = SOUND_IDLE_RELOAD
        state.sound_retry_count = 0


def main_update_sound(state: GameState) -> None:
    """0x4AE20 -- drain the outgoing sound command queue. See §11.2.

    Skips entirely when ``frame_overflow`` or the recovery holdoff is
    nonzero. Otherwise makes at most eight attempts, stopping early if the
    ring empties first. Every drained command is appended to ``sound_log``,
    the permanent oracle other packages assert against.

    The documented busy-latch retry (§11.2, "Contradicted and corrected":
    a busy result costs an attempt but leaves the read head alone) has no
    counterpart here -- there is no real latch to report busy, so every
    attempt succeeds and consumes one queue entry.
    """
    if state.frame_overflow or state.sound_holdoff:
        return

    attempts = 0
    while state.sound_queue and attempts < SOUND_DRAIN_MAX_ATTEMPTS:
        command = state.sound_queue.pop(0)
        state.sound_log.append(command)
        attempts += 1
