"""Structural contract for decoded maze data, independent of the ROM decoder."""

from __future__ import annotations

from typing import Protocol


class MazeData(Protocol):
    data: dict[tuple[int, int], int]
    encodedbytes: int
    secret: int
    flags: int
    wallpattern: int
    wallcolor: int
    floorpattern: int
    floorcolor: int
