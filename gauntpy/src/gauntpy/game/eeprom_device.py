"""Typed EEPROM image boundary, independent of host persistence and game rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

HighScoreImage = tuple[tuple[tuple[int, str], ...], ...]


@dataclass(frozen=True)
class EepromRotation:
    maze_number: int
    maze_stride: int
    treas_mazerand_num: int
    treas_mazerand_adder: int


@dataclass(frozen=True)
class EepromImage:
    game_settings: int
    two_player_mode: int | None = None
    high_scores: HighScoreImage | None = None
    rotation: EepromRotation | None = None


class EepromStorage(Protocol):
    """Read the current device image; ``None`` denotes an unprogrammed part."""

    # ROM: infrastructure | Abstract typed device-image protocol; not OS eeprom_read_block, which uses redundant blocks, syndromes and queue semantics.
    def read(self) -> EepromImage | None: ...

    # ROM: infrastructure | Abstract typed device-image protocol; not OS queued EEPROM request/process bodies.
    def write(self, image: EepromImage) -> None: ...


@dataclass
class MemoryEepromStorage:
    """An isolated cabinet device with no external reads or writes."""

    image: EepromImage | None = None

    # ROM: infrastructure | Reads the isolated Python device image; no OS block decoding, hardware access or asynchronous read implementation.
    def read(self) -> EepromImage | None:
        return self.image

    # ROM: infrastructure | Replaces the isolated Python device image; no OS byte-write state machine, unlock register or EEPROM queue implementation.
    def write(self, image: EepromImage) -> None:
        self.image = image
