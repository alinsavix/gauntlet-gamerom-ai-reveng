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

    def read(self) -> EepromImage | None: ...

    def write(self, image: EepromImage) -> None: ...


@dataclass
class MemoryEepromStorage:
    """An isolated cabinet device with no external reads or writes."""

    image: EepromImage | None = None

    def read(self) -> EepromImage | None:
        return self.image

    def write(self, image: EepromImage) -> None:
        self.image = image
