"""Static-WAV playback for the pygame host.

The game simulation ends at ``GameState.sound_log``: it contains the bytes
accepted by the modeled main-CPU sound latch.  This module consumes that stream
and reproduces the sound board's command-level playback policy without
emulating its 6502, YM2151, POKEY, or TMS5220.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping, Sequence

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
_CONTROL_DESCRIPTIONS = {
    0x00: "Clear/reinitialize audio",
    0x01: "High sound filter",
    0x02: "Clear sound filter",
    0x03: "Input/status query",
    0x06: "Command-count query",
    0x07: "Diagnostic query",
    0x21: "Death silencer",
    0x2F: "Force field silencer",
    0x39: "Slow motion silencer",
    0x3C: "Theme song fade out",
    0x41: "Treasure room music fade out",
    0xD6: "Effects off",
    0xD7: "Low effects",
    0xD8: "Medium effects",
    0xD9: "Full effects",
    0xDA: "Queue status response",
}

# Sound-ROM type-7 chain records. Each tuple is (physical channel, priority);
# transcribed from the command parameter/chain tables catalogued by the
# companion sound-ROM project. Equal priority replaces the old member, while a
# higher-priority member suppresses lower members until it retires.
_TYPE7_CHANNEL_PRIORITIES = {
    0x04: ((4, 8), (5, 8), (6, 8), (7, 8), (8, 8), (9, 8), (10, 8), (11, 8)),
    0x05: ((0, 8), (1, 8), (2, 8), (3, 8)),
    0x09: ((4, 15), (5, 15), (8, 14)),
    0x0A: ((10, 15), (11, 15), (6, 14), (7, 14)),
    0x0B: ((10, 14), (11, 14), (6, 15), (7, 15), (4, 13), (5, 13), (8, 13), (9, 13)),
    0x0C: ((8, 15), (9, 15)),
    0x0D: ((8, 2), (9, 2)),
    0x0E: ((4, 3), (5, 3)),
    0x0F: ((6, 3), (7, 3)),
    0x10: ((8, 3), (9, 3)),
    0x11: ((10, 3), (11, 3)),
    0x12: ((4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (9, 2), (10, 2), (11, 2)),
    0x13: ((4, 2), (5, 2)),
    0x14: ((4, 32), (5, 32)),
    0x15: ((6, 32), (7, 32)),
    0x16: ((8, 32), (9, 32)),
    0x17: ((10, 32), (11, 32)),
    0x18: ((4, 30), (5, 30)),
    0x19: ((6, 30), (7, 30)),
    0x1A: ((8, 30), (9, 30)),
    0x1B: ((10, 30), (11, 30)),
    0x1C: ((6, 3), (7, 3)),
    0x1D: ((4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (9, 2), (10, 2), (11, 2)),
    0x1E: ((8, 2), (9, 2)),
    0x1F: ((10, 2), (11, 2)),
    0x20: ((4, 20), (5, 20)),
    0x22: ((4, 63), (5, 63)),
    0x23: ((6, 63), (7, 63)),
    0x24: ((8, 63), (9, 63)),
    0x25: ((10, 63), (11, 63)),
    0x26: ((4, 2), (5, 2)),
    0x27: ((4, 8), (5, 8), (6, 8), (7, 8), (8, 6), (9, 8), (10, 8), (11, 8)),
    0x28: ((4, 8), (5, 8), (6, 8), (7, 8), (8, 7), (9, 8), (10, 8), (11, 8)),
    0x29: ((4, 10), (5, 10), (6, 10), (7, 10), (8, 7), (9, 10), (10, 10), (11, 10)),
    0x2A: ((4, 8),),
    0x2B: ((5, 8),),
    0x2C: ((7, 8),),
    0x2D: ((9, 10),),
    0x2E: ((10, 8),),
    0x30: ((11, 8),),
    0x31: ((4, 8),),
    0x32: ((5, 8),),
    0x33: ((8, 7),),
    0x34: ((9, 8),),
    0x35: ((10, 8),),
    0x36: ((9, 8),),
    0x37: ((8, 8),),
    0x38: ((8, 9),),
    0x3A: ((9, 9),),
    0x3B: ((4, 61), (5, 61), (6, 61), (7, 61), (8, 61), (9, 61), (10, 61), (11, 61)),
    0x3D: ((4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (9, 2), (10, 2), (11, 2)),
    0x3E: ((4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (9, 2), (10, 2), (11, 2)),
    0x3F: ((4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (9, 2), (10, 2), (11, 2)),
    0x40: ((4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (9, 2), (10, 2), (11, 2)),
    0x42: ((4, 31), (5, 31), (6, 31), (7, 31), (8, 31)),
    0x43: ((0, 51),),
    0x44: ((1, 51),),
    0x45: ((0, 2),),
    0x46: ((1, 2),),
    0x47: ((2, 2),),
    0x48: ((3, 2),),
    0x49: ((3, 2),),
}


@dataclass(eq=False)
class _Type7Playback:
    command: int
    channel: object
    members: dict[int, int]


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
        self._type7_playbacks: list[_Type7Playback] = []
        self._speech_queue: deque[tuple[int, int]] = deque()
        self._speech_channel = mixer.Channel(0)
        self._next_effect_channel = 1
        self._current_speech_priority = 0
        self._filter_high = False
        self._effect_volume = 1.0
        self._consumed_count = 0

    @property
    def command_descriptions(self) -> Mapping[int, str]:
        descriptions = dict(_CONTROL_DESCRIPTIONS)
        descriptions.update(
            (command, self._description_from_path(path))
            for command, path in self._paths.items()
        )
        return descriptions

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

    @staticmethod
    def _description_from_path(path: Path) -> str:
        description = path.stem[5:].replace("__", " / ").replace("_", " ")
        return description.strip()

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
        self._type7_playbacks.clear()

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
        if command not in _TYPE7_CHANNEL_PRIORITIES:
            raise SoundLibraryError(
                f"no type-7 channel metadata for command 0x{command:02X}"
            )
        members = self._admit_type7_members(command)
        if not members:
            self._refresh_volumes()
            return

        channel = self._allocate_effect_channel()
        self._detach_channel(channel)
        channel.set_volume(0.0)
        channel.play(
            self._sound(command),
            loops=-1 if command in _LOOPING_COMMANDS else 0,
        )
        self._playing.setdefault(command, []).append(channel)
        self._type7_playbacks.append(
            _Type7Playback(command, channel, members),
        )
        self._refresh_volumes()

    def _admit_type7_members(self, command: int) -> dict[int, int]:
        accepted: dict[int, int] = {}
        for hardware_channel, priority in _TYPE7_CHANNEL_PRIORITIES[command]:
            equal = next(
                (
                    playback for playback in self._type7_playbacks
                    if playback.members.get(hardware_channel) == priority
                ),
                None,
            )
            if equal is not None:
                self._remove_logical_member(equal, hardware_channel)
            elif self._logical_member_count() + len(accepted) >= 30:
                candidates = [
                    (playback.members[hardware_channel], playback)
                    for playback in self._type7_playbacks
                    if hardware_channel in playback.members
                ]
                if not candidates:
                    break
                lowest_priority, victim = min(candidates, key=lambda item: item[0])
                if priority < lowest_priority:
                    break
                self._remove_logical_member(victim, hardware_channel)
            accepted[hardware_channel] = priority
        return accepted

    def _logical_member_count(self) -> int:
        return sum(
            len(playback.members) for playback in self._type7_playbacks
        )

    def _remove_logical_member(
        self, playback: _Type7Playback, hardware_channel: int,
    ) -> None:
        playback.members.pop(hardware_channel, None)
        if not playback.members:
            playback.channel.stop()
            self._remove_type7_playback(playback)

    def _allocate_effect_channel(self):
        for _ in range(31):
            index = self._next_effect_channel
            self._next_effect_channel = 1 + (index % 31)
            channel = self._mixer.Channel(index)
            if not channel.get_busy():
                return channel
        return self._mixer.Channel(self._next_effect_channel)

    def _detach_channel(self, channel) -> None:
        for playback in tuple(self._type7_playbacks):
            if playback.channel == channel:
                self._remove_type7_playback(playback)
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
        for playback in tuple(self._type7_playbacks):
            if playback.command == command:
                playback.channel.stop()
                self._remove_type7_playback(playback)
        for channel in self._playing.pop(command, ()):
            channel.stop()
        self._refresh_volumes()

    def _fade_commands(self, commands) -> None:
        for command in commands:
            for channel in self._playing.get(command, ()):
                channel.fadeout(_FADE_MILLISECONDS)

    def _retire_finished_channels(self) -> None:
        for playback in tuple(self._type7_playbacks):
            if not playback.channel.get_busy():
                self._remove_type7_playback(playback)
        for command, channels in tuple(self._playing.items()):
            active = [channel for channel in channels if channel.get_busy()]
            if active:
                self._playing[command] = active
            else:
                del self._playing[command]
        self._refresh_volumes()

    def _remove_type7_playback(self, playback: _Type7Playback) -> None:
        if playback in self._type7_playbacks:
            self._type7_playbacks.remove(playback)
        channels = self._playing.get(playback.command, [])
        remaining = [channel for channel in channels if channel != playback.channel]
        if remaining:
            self._playing[playback.command] = remaining
        else:
            self._playing.pop(playback.command, None)

    def _type7_playback_is_audible(self, playback: _Type7Playback) -> bool:
        for hardware_channel, priority in playback.members.items():
            winner = max(
                (
                    candidate.members.get(hardware_channel, -1)
                    for candidate in self._type7_playbacks
                ),
                default=-1,
            )
            if priority == winner:
                return True
        return False

    def _volume_for(self, command: int) -> float:
        if self._filter_high and command not in _FILTER_SURVIVORS:
            return 0.0
        return 1.0 if command in _MUSIC_COMMANDS else self._effect_volume

    def _refresh_volumes(self) -> None:
        type7_channels = {
            playback.channel for playback in self._type7_playbacks
        }
        for playback in self._type7_playbacks:
            volume = (
                self._volume_for(playback.command)
                if self._type7_playback_is_audible(playback)
                else 0.0
            )
            playback.channel.set_volume(volume)
        for command, channels in self._playing.items():
            for channel in channels:
                if channel not in type7_channels:
                    channel.set_volume(self._volume_for(command))
        if self._speech_channel.get_busy():
            self._speech_channel.set_volume(0.0 if self._filter_high else 1.0)
