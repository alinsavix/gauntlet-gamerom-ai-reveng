"""Host-only complete modeled-state dumps for troubleshooting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any

from ..mob import MobTable
from ..rng import GameRandom
from ..state import GameState

STATE_DUMP_SCHEMA = 1
DEFAULT_STATE_DUMP_DIR = Path(__file__).resolve().parents[3] / "traces" / "state-dumps"


def _json_value(value: object, seen: set[int]) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"encoding": "hex", "data": value.hex()}

    identity = id(value)
    if identity in seen:
        return {"cycle": type(value).__name__}
    seen.add(identity)
    try:
        if isinstance(value, MobTable):
            return {
                name: _json_value(getattr(value, name), seen)
                for name in value.__slots__
            }
        if isinstance(value, GameRandom):
            return {"seed": value.seed}
        if is_dataclass(value):
            return {
                field.name: _json_value(getattr(value, field.name), seen)
                for field in fields(value)
            }
        if isinstance(value, Mapping):
            if all(isinstance(key, str) for key in value):
                return {
                    key: _json_value(item, seen)
                    for key, item in value.items()
                }
            return [
                {
                    "key": _json_value(key, seen),
                    "value": _json_value(item, seen),
                }
                for key, item in value.items()
            ]
        if isinstance(value, (list, tuple)):
            return [_json_value(item, seen) for item in value]
        if isinstance(value, (set, frozenset)):
            return [_json_value(item, seen) for item in sorted(value, key=repr)]
        slots = getattr(value, "__slots__", ())
        if slots:
            if isinstance(slots, str):
                slots = (slots,)
            return {
                name: _json_value(getattr(value, name), seen)
                for name in slots
                if hasattr(value, name)
            }
        attributes = getattr(value, "__dict__", None)
        if attributes is not None:
            return {
                name: _json_value(item, seen)
                for name, item in sorted(attributes.items())
                if not callable(item)
            }
        return {"type": type(value).__name__, "repr": repr(value)}
    finally:
        seen.remove(identity)


def state_dump_payload(state: GameState) -> dict[str, object]:
    """Return every modeled GameState field in a complete JSON-safe shape."""
    return {
        "schema": STATE_DUMP_SCHEMA,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "frame": state.frame_counter,
        "state": _json_value(state, set()),
    }


def dump_game_state(
    state: GameState, output_dir: str | Path = DEFAULT_STATE_DUMP_DIR,
) -> Path:
    """Atomically write a complete host-side state dump and return its path."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"state-frame-{state.frame_counter:05d}-{stamp}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state_dump_payload(state), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path
