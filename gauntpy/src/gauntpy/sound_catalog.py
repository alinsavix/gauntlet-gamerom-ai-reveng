"""Sound-command names shared by diagnostics and host audio playback."""

from __future__ import annotations

import csv
from importlib.resources import files
from types import MappingProxyType
from typing import Mapping

__all__ = ["SOUND_COMMAND_DESCRIPTIONS"]


def _load_command_descriptions() -> Mapping[int, str]:
    catalog = files("gauntpy").joinpath("data/soundcmds.csv")
    with catalog.open("r", encoding="utf-8", newline="") as source:
        rows = csv.DictReader(source)
        descriptions = {
            int(row["Sound Id"], 16): row["description"]
            for row in rows
            if row.get("Sound Id")
        }
    return MappingProxyType(descriptions)


SOUND_COMMAND_DESCRIPTIONS = _load_command_descriptions()
