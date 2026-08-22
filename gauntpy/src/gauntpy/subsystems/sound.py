"""Sound -- WP-18. The command engine is real; the audio output is a log.

The command engine, the eight-attempt drain with its busy-latch retry, the
board recovery/holdoff machine, the status-query retry ladder and the operator
speech gate are all implemented against §11. What the port does not do is
*synthesise* audio: the emitted command stream is the output, recorded in
``state.sound_log``. That is the one hardware boundary this package replaces
rather than reimplements -- the sound board is a separate 6502 with its own
ROMs -- and it doubles as a **test oracle** for the rest of the game ("this
event plays sound 0x37").

219 command IDs (0x00-0xDA); command 0x00 is reinitialize/stop-all, 0x06 the
command-count query (replies 0xDB), 0x07 the diagnostic fault query.

``sound_play`` (§11.1) is ROM-faithful, fast path included: when the recovery
holdoff is zero it offers the byte straight to the board and an accepted
command is *never* queued; only a busy latch (or a nonzero holdoff) falls back
to the seven-entry ring. So ``sound_log`` -- not ``sound_queue`` -- is what
"the board was told", and it is where every emitted command shows up exactly
once, whether it went out immediately or was drained later. Capacity and
drop-when-full behaviour on the ring path are preserved exactly.

**The two board-facing sends are seams.** Everything the documented
queue/retry logic branches on is a *send result*. ``try_send_sound_command``
(OS 0x242) and ``send_status_query`` (OS 0x172) return ``True`` for the log
backend and can be substituted by a real board model -- or a test -- to
exercise the busy and failed-send ladders. The gates themselves (the
eight-attempt budget, the read head staying put on a busy result, the retry
count, the 0xB4 reset threshold, the speech-disable bit) are all implemented.

Reference: ``doc/04_game_subsystems.md`` §11; ``refs/soundcmds.csv``;
``book/16_sound.md``.
"""

from __future__ import annotations

from ..state import GameState

__all__ = [
    "SOUND_REINITIALIZE", "SOUND_COMMAND_COUNT_QUERY", "SOUND_DIAGNOSTIC_QUERY",
    "SOUND_QUEUE_CAPACITY", "SOUND_DRAIN_MAX_ATTEMPTS", "SOUND_RESET_HOLDOFF",
    "SOUND_IDLE_RELOAD", "SOUND_RETRY_LIMIT", "GAME_SETTINGS_SPEECH_DISABLED",
    "SOUND_NO_RESPONSE",
    "try_send_sound_command", "send_status_query",
    "enqueue_sound", "sound_play", "sound_speech_play", "sound_system_reset",
    "sound_response", "main_update_sound",
]

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

#: Consecutive failed-send retry threshold before a full reset. §11.3: "above
#: 0xB4 (180) it performs a full reset".
SOUND_RETRY_LIMIT = 0xB4

#: game_settings (0x904A24) bit 11 -- the operator "Disable Speech" setting.
#: sound_speech_play calls sound_play only when this bit is clear. §11.4.
GAME_SETTINGS_SPEECH_DISABLED = 1 << 11

#: The "no response this poll" sentinel OS 0x178 (read_sound_data) returns.
#: §11.3.
SOUND_NO_RESPONSE = 0xFFFF


# ---------------------------------------------------------------------------
# The board-facing sends. See the module docstring: these exist so the
# documented busy/failure ladders are real code rather than commentary.
# ---------------------------------------------------------------------------

def try_send_sound_command(state: GameState, command: int) -> bool:
    """OS ``try_send_sound_command`` (0x242) -- offer one byte to the sound
    board's command latch. ``True`` = accepted, ``False`` = the latch is busy.

    Nothing in this simulation owns a latch, so the offer always succeeds.
    """
    return True


def send_status_query(state: GameState) -> bool:
    """OS 0x172 -- send the diagnostic status query (command
    ``SOUND_DIAGNOSTIC_QUERY``) with a one-byte reply directed at 0x9049F1.
    ``True`` = sent, ``False`` = the send failed. §11.3.

    Always succeeds here for the same reason ``try_send_sound_command`` does.
    """
    return True


def enqueue_sound(state: GameState, sound_id: int) -> None:
    """0x4ADD6 -- the ring fallback: append if there is room, otherwise drop
    the byte silently. Usable capacity is 7 (§11.1-11.2).
    """
    if len(state.sound_queue) < SOUND_QUEUE_CAPACITY:
        state.sound_queue.append(sound_id & 0xFF)
    # else: ring full, command dropped without complaint (§11.2)


def sound_play(state: GameState, sound_id: int) -> None:
    """0x4AD76 -- play a sound command. Called from all over the game.

    §11.1: with the recovery holdoff (0x9049EE, tested at 0x4AD7E) clear, the
    byte is offered straight to the board through ``try_send_sound_command``
    and an accepted command is **not** queued. A busy latch falls back to the
    ring (``enqueue_sound``, 0x4ADD6); a nonzero holdoff skips the immediate
    attempt and queues directly.

    An accepted immediate send *is* the board receiving the byte, so for the
    log backend it is recorded in ``sound_log`` here and exactly once --
    ``main_update_sound`` only logs the commands it drains out of the ring.
    """
    sound_id &= 0xFF
    if not state.sound_holdoff and try_send_sound_command(state, sound_id):
        state.sound_log.append(sound_id)
        return
    enqueue_sound(state, sound_id)


def sound_speech_play(state: GameState, speech_id: int) -> None:
    """0x4AD4E -- play a speech command. See §11.4.

    Calls ``sound_play`` -- immediate send or ring, whichever §11.1 selects --
    only when the "Disable Speech" operator setting (game_settings bit 11) is
    clear. A disabled setting emits nothing at all.
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
    if state.sound_idle_timer >= 0:
        return

    # Time for the periodic diagnostic poll. The word is cleared first so the
    # reply's low three fault bits are the board's, not last poll's (§11.3).
    state.sound_queue_state = 0
    if send_status_query(state):
        state.sound_idle_timer = SOUND_IDLE_RELOAD
        state.sound_retry_count = 0
        return

    # Failed send: clear the timer so the next frame retries immediately, count
    # the attempt, and reset the whole engine once the count passes 0xB4.
    state.sound_idle_timer = 0
    state.sound_retry_count += 1
    if state.sound_retry_count > SOUND_RETRY_LIMIT:
        sound_system_reset(state)


def main_update_sound(state: GameState) -> None:
    """0x4AE20 -- drain the outgoing sound command queue. See §11.2.

    Skips entirely when ``frame_overflow`` or the recovery holdoff is
    nonzero. Otherwise makes at most eight attempts, stopping early if the
    ring empties first. Every command the board accepts here is appended to
    ``sound_log``, the permanent oracle other packages assert against -- which
    is also where ``sound_play``'s immediately-accepted commands go, so the log
    holds every emitted command exactly once regardless of the path it took.

    §11.2's "Contradicted and corrected": a busy result from
    ``try_send_sound_command`` does **not** end the drain. It costs one of the
    eight attempts and leaves the read head alone, so the same byte is offered
    again on the next attempt (and, if the eight run out, next frame).
    """
    if state.frame_overflow or state.sound_holdoff:
        return

    attempts = 0
    while state.sound_queue and attempts < SOUND_DRAIN_MAX_ATTEMPTS:
        attempts += 1
        command = state.sound_queue[0]
        if not try_send_sound_command(state, command):
            continue        # busy: the byte stays at the head of the ring
        state.sound_queue.pop(0)
        state.sound_log.append(command)
