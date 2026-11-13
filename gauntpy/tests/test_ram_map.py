"""tools/ram_map.py: the game RAM the lockstep harness compares with gauntpy's state."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from gauntpy.game.state import GameState

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "ram_map.py"
_SPEC = importlib.util.spec_from_file_location("gauntpy_ram_map", _TOOL)
ram_map = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ram_map)


def _fields():
    return [(*field, 0, "same") for field in ram_map.FIELDS] + list(ram_map.CONVERTED)


def _spans():
    state = GameState()
    for owner, field, address, size, stride, first, _ in _fields():
        if owner == "player":
            count = len(state.players)
        else:
            value = getattr(state, field)
            count = min(len(value), 64) if isinstance(value, list) else 1
        for index in range(first, count):
            yield field, address + index * stride, size


def test_every_field_is_real_state():
    state = GameState()
    for owner, field, _, _, _, _, encoding in _fields():
        assert encoding in ("same", "x2"), field
        holder = state.players[0] if owner == "player" else state
        assert hasattr(holder, field), field


def test_every_field_lies_in_game_ram_and_none_overlap():
    taken: dict[int, str] = {}
    for field, address, size in _spans():
        assert 0x904000 <= address and address + size <= 0x906000, field
        for byte in range(address, address + size):
            assert byte not in taken, f"{field} overlaps {taken[byte]} at {byte:#x}"
            taken[byte] = field


def test_compared_and_excluded_fields_are_apart():
    compared = {field[1] for field in _fields()}
    assert len(compared) == len(_fields()), "a field is listed twice"
    assert not compared & set(ram_map.UNCOMPARED)
