"""Static-WAV playback for the pygame host.

The game simulation ends at ``GameState.sound_log``: it contains the bytes
accepted by the modeled main-CPU sound latch.  This module consumes that stream
and reproduces the sound board's command-level playback policy without
emulating its 6502, YM2151, POKEY, or TMS5220.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
import re
from typing import Sequence

__all__ = ["SoundLibraryError", "StaticSoundPlayer"]


class SoundLibraryError(RuntimeError):
    """The host's static sound library cannot satisfy a command."""


_SOUND_FILENAME = re.compile(r"^0x([0-9a-fA-F]{2})_.*\.wav$")
_SPEECH_COMMANDS = frozenset((0x08, *range(0x4A, 0xD6)))
_HIGH_PRIORITY_SPEECH = frozenset(range(0xA1, 0xA7))
_FILTER_SURVIVORS = frozenset((0x22, 0x23, 0x24, 0x25, 0x3B))
_LOOPING_COMMANDS = frozenset((0x20, 0x2E, 0x37))
_STOP_TARGETS = {0x21: 0x20, 0x2F: 0x2E, 0x39: 0x37}
_TREASURE_MUSIC = frozenset(range(0x3D, 0x41))
_MUSIC_COMMANDS = frozenset((0x04, 0x3B, 0x42)) | _TREASURE_MUSIC
_CONTROL_COMMANDS = frozenset((
    0x00, 0x01, 0x02, 0x03, 0x06, 0x07,
    0x21, 0x2F, 0x39, 0x3C, 0x41,
    0xD6, 0xD7, 0xD8, 0xD9, 0xDA,
))
_SPEECH_QUEUE_CAPACITY = 7
_FADE_MILLISECONDS = 1000
_MIXER_EFFECT_LEVEL = {
    0xD6: 0.0,
    0xD7: 1.0 / 3.0,
    0xD8: 2.0 / 3.0,
    0xD9: 1.0,
}


def _speech_priority(command: int) -> int:
    if command in _HIGH_PRIORITY_SPEECH:
        return 0x40
    if command == 0xBC:
        return 4
    return 0


class StaticSoundPlayer:
    """Consume accepted sound commands and play command-named WAV files.

    ``mixer`` is ``pygame.mixer`` in production and a small compatible fake in
    tests.  Channel zero is reserved for serialized speech; the remaining
    channels represent the sound board's concurrent sequence slots.
    """

    def __init__(self, mixer, sound_dir: str | Path) -> None:
        self._mixer = mixer
        self._sound_dir = Path(sound_dir)
        if not self._sound_dir.is_dir():
            raise SoundLibraryError(
                f"sound directory does not exist: {self._sound_dir}"
            )
        self._paths = self._index_library()
        self._sounds: dict[int, object] = {}
        self._playing: dict[int, list[object]] = {}
        self._speech_queue: deque[tuple[int, int]] = deque()
        self._speech_channel = mixer.Channel(0)
        self._current_speech_priority = 0
        self._filter_high = False
        self._effect_volume = 1.0
        self._consumed_count = 0

    def _index_library(self) -> dict[int, Path]:
        paths: dict[int, Path] = {}
        for path in self._sound_dir.glob("*.wav"):
            match = _SOUND_FILENAME.match(path.name)
            if match is None:
                continue
            command = int(match.group(1), 16)
            if command in paths:
                raise SoundLibraryError(
                    f"duplicate WAV files for command 0x{command:02X}"
                )
            paths[command] = path
        return paths

    def skip_existing(self, commands: Sequence[int]) -> None:
        """Begin after an existing persistent log, as when loading a snapshot."""
        self._consumed_count = len(commands)

    def consume(self, commands: Sequence[int]) -> None:
        """Play every command appended since the previous host update."""
        if self._consumed_count > len(commands):
            self._consumed_count = 0
        self._retire_finished_channels()
        self._advance_speech()
        pending = commands[self._consumed_count:]
        self._consumed_count = len(commands)
        for command in pending:
            self._dispatch(command & 0xFF)
        self._advance_speech()

    def close(self) -> None:
        self._mixer.stop()
        self._speech_queue.clear()
        self._playing.clear()

    def _dispatch(self, command: int) -> None:
        if command == 0x00:
            self.close()
            self._filter_high = False
            self._effect_volume = 1.0
            self._current_speech_priority = 0
            return
        if command == 0x01:
            self._filter_high = True
            self._refresh_volumes()
            return
        if command == 0x02:
            self._filter_high = False
            self._refresh_volumes()
            return
        if command in _STOP_TARGETS:
            self._stop_command(_STOP_TARGETS[command])
            return
        if command == 0x3C:
            self._fade_commands((0x3B,))
            return
        if command == 0x41:
            self._fade_commands(_TREASURE_MUSIC)
            return
        if command in _MIXER_EFFECT_LEVEL:
            self._effect_volume = _MIXER_EFFECT_LEVEL[command]
            self._refresh_volumes()
            return
        if command in _SPEECH_COMMANDS:
            self._queue_speech(command)
            return
        if command in _CONTROL_COMMANDS:
            return
        self._play_effect(command)

    def _sound(self, command: int):
        sound = self._sounds.get(command)
        if sound is not None:
            return sound
        try:
            path = self._paths[command]
        except KeyError as exc:
            raise SoundLibraryError(
                f"no WAV file for playable command 0x{command:02X}"
            ) from exc
        sound = self._mixer.Sound(str(path))
        self._sounds[command] = sound
        return sound

    def _play_effect(self, command: int) -> None:
        channel = self._mixer.find_channel(True)
        self._detach_channel(channel)
        channel.set_volume(self._volume_for(command))
        channel.play(
            self._sound(command),
            loops=-1 if command in _LOOPING_COMMANDS else 0,
        )
        self._playing.setdefault(command, []).append(channel)

    def _detach_channel(self, channel) -> None:
        for command, channels in tuple(self._playing.items()):
            remaining = [active for active in channels if active != channel]
            if remaining:
                self._playing[command] = remaining
            else:
                del self._playing[command]

    def _queue_speech(self, command: int) -> None:
        if self._filter_high:
            return
        priority = _speech_priority(command)
        if not self._speech_channel.get_busy() and not self._speech_queue:
            self._start_speech(command, priority)
            return
        if len(self._speech_queue) >= _SPEECH_QUEUE_CAPACITY:
            return
        if priority < self._current_speech_priority:
            return
        if priority > self._current_speech_priority:
            self._speech_queue.clear()
        self._speech_queue.append((command, priority))

    def _advance_speech(self) -> None:
        if self._speech_channel.get_busy():
            return
        self._current_speech_priority = 0
        if self._speech_queue:
            self._start_speech(*self._speech_queue.popleft())

    def _start_speech(self, command: int, priority: int) -> None:
        self._current_speech_priority = priority
        self._speech_channel.set_volume(0.0 if self._filter_high else 1.0)
        self._speech_channel.play(self._sound(command))

    def _stop_command(self, command: int) -> None:
        for channel in self._playing.pop(command, ()):
            channel.stop()

    def _fade_commands(self, commands) -> None:
        for command in commands:
            for channel in self._playing.pop(command, ()):
                channel.fadeout(_FADE_MILLISECONDS)

    def _retire_finished_channels(self) -> None:
        for command, channels in tuple(self._playing.items()):
            active = [channel for channel in channels if channel.get_busy()]
            if active:
                self._playing[command] = active
            else:
                del self._playing[command]

    def _volume_for(self, command: int) -> float:
        if self._filter_high and command not in _FILTER_SURVIVORS:
            return 0.0
        return 1.0 if command in _MUSIC_COMMANDS else self._effect_volume

    def _refresh_volumes(self) -> None:
        for command, channels in self._playing.items():
            volume = self._volume_for(command)
            for channel in channels:
                channel.set_volume(volume)
        if self._speech_channel.get_busy():
            self._speech_channel.set_volume(0.0 if self._filter_high else 1.0)
