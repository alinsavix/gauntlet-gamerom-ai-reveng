"""Host-only complete modeled-state dumps for troubleshooting."""

from __future__ import annotations

from collections.abc import Mapping
import ast
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
_SCHEMA_1_RETIRED_FIELDS = {"suppress_first_encounter_messages"}
DEFAULT_STATE_DUMP_DIR = Path(__file__).resolve().parents[3] / "traces" / "state-dumps"
_SCHEMA_1_ADDED_FIELDS = {
    "hurt_speech_timer",
    "random_pickups_setup_done",
    "playfield_color_latch",
    "playfield_color_base",
    "eeprom_persistence_enabled",
    "dialog_once_flags",
}


class StateDumpError(ValueError):
    """A saved-state file cannot be reconstructed safely."""


def _json_value(value: object, seen: set[int]) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
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
    payload = {
        "schema": STATE_DUMP_SCHEMA,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "frame": state.frame_counter,
        "state": _json_value(state, set()),
    }
    from ..custom_scenario import synthetic_runtime_payload

    synthetic = synthetic_runtime_payload(state)
    if synthetic is not None:
        payload["synthetic_scenario"] = synthetic
    return payload


def _mapping_key(value: object) -> object:
    if isinstance(value, list):
        return tuple(_mapping_key(item) for item in value)
    return value


def _mapping(value: object, *, tuple_values: bool = False) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, list):
        raise StateDumpError("expected a serialized mapping")
    result = {}
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"key", "value"}:
            raise StateDumpError("invalid serialized mapping entry")
        item = entry["value"]
        if tuple_values and isinstance(item, list):
            item = tuple(item)
        result[_mapping_key(entry["key"])] = item
    return result


def _restore_bytearray(value: object) -> bytearray:
    if (
        isinstance(value, dict)
        and value.get("encoding") == "hex"
        and isinstance(value.get("data"), str)
    ):
        try:
            return bytearray.fromhex(value["data"])
        except ValueError as exc:
            raise StateDumpError("invalid hexadecimal bytearray data") from exc

    # Schema-1 dumps made before resumable states represented bytearray through
    # repr(). Parse only its bytes literal, never evaluate the surrounding call.
    if isinstance(value, dict) and value.get("type") == "bytearray":
        representation = value.get("repr")
        if (
            isinstance(representation, str)
            and representation.startswith("bytearray(")
            and representation.endswith(")")
        ):
            try:
                raw = ast.literal_eval(representation[10:-1])
            except (SyntaxError, ValueError) as exc:
                raise StateDumpError("invalid legacy bytearray state") from exc
            if isinstance(raw, bytes):
                return bytearray(raw)
    raise StateDumpError("invalid path_direction_grid")


def _restore_dataclass(target: object, payload: object) -> None:
    if not isinstance(payload, dict):
        raise StateDumpError(f"expected an object for {type(target).__name__}")
    expected = {field.name for field in fields(target)}
    if set(payload) != expected:
        missing = sorted(expected - set(payload))
        extra = sorted(set(payload) - expected)
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if extra:
            details.append(f"unknown fields: {', '.join(extra)}")
        raise StateDumpError(f"{type(target).__name__} shape mismatch ({'; '.join(details)})")

    for field in fields(target):
        current = getattr(target, field.name)
        value = payload[field.name]
        if is_dataclass(current):
            _restore_dataclass(current, value)
        elif isinstance(current, list) and current and is_dataclass(current[0]):
            if not isinstance(value, list) or len(value) != len(current):
                raise StateDumpError(f"invalid {field.name} record list")
            for item, item_payload in zip(current, value):
                _restore_dataclass(item, item_payload)
        else:
            setattr(target, field.name, value)


def _restore_mobs(payload: object) -> MobTable:
    if not isinstance(payload, dict):
        raise StateDumpError("expected an object for MobTable")
    mobs = MobTable()
    expected = set(mobs.__slots__)
    if set(payload) != expected:
        raise StateDumpError("MobTable shape does not match this gauntpy version")
    for name in mobs.__slots__:
        value = payload[name]
        current = getattr(mobs, name)
        if isinstance(current, list):
            if not isinstance(value, list) or len(value) != len(current):
                raise StateDumpError(f"invalid MobTable.{name} array")
            setattr(mobs, name, value)
        elif not isinstance(value, int):
            raise StateDumpError(f"invalid MobTable.{name} value")
        else:
            setattr(mobs, name, value)
    return mobs


def _restore_maze(payload: object) -> object | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise StateDumpError("expected an object for maze")

    try:
        from gex.mazedecode import Maze
    except ImportError as exc:
        raise StateDumpError("loading a maze state requires the local gex package") from exc

    maze = Maze()
    expected = {field.name for field in fields(maze)}
    if set(payload) != expected:
        raise StateDumpError("saved maze shape does not match this gex version")
    maze.data = _mapping(payload["data"])
    for name in expected - {"data", "rand"}:
        setattr(maze, name, payload[name])
    # Maze.rand is used only while constructing descriptor catalogs. Those
    # catalogs are already in GameState, and loading a later level replaces it.
    return maze


def game_state_from_payload(payload: object) -> GameState:
    """Reconstruct a runnable ``GameState`` from a schema-1 dump payload."""
    if not isinstance(payload, dict):
        raise StateDumpError("saved state root must be a JSON object")
    if payload.get("schema") != STATE_DUMP_SCHEMA:
        raise StateDumpError(
            f"unsupported saved-state schema {payload.get('schema')!r}; "
            f"expected {STATE_DUMP_SCHEMA}"
        )
    serialized = payload.get("state")
    if not isinstance(serialized, dict):
        raise StateDumpError("saved state has no GameState object")
    state = GameState()
    expected = {field.name for field in fields(state)}
    for name in _SCHEMA_1_RETIRED_FIELDS:
        serialized.pop(name, None)
    missing_fields = expected - set(serialized)
    if set(serialized) - expected or missing_fields - _SCHEMA_1_ADDED_FIELDS:
        missing = sorted(missing_fields)
        extra = sorted(set(serialized) - expected)
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if extra:
            details.append(f"unknown fields: {', '.join(extra)}")
        raise StateDumpError(f"GameState shape mismatch ({'; '.join(details)})")

    if "hurt_speech_timer" not in serialized:
        serialized["hurt_speech_timer"] = [0] * len(state.players)
    if "random_pickups_setup_done" not in serialized:
        serialized["random_pickups_setup_done"] = bool(
            serialized.get("maze") is not None
            and serialized.get("level_players_active", 0)
        )
    if "playfield_color_base" not in serialized:
        colors = serialized.get("playfield_color_ram")
        base = colors[8] if isinstance(colors, list) and len(colors) > 8 else 0
        serialized["playfield_color_base"] = base
    if "playfield_color_latch" not in serialized:
        serialized["playfield_color_latch"] = serialized["playfield_color_base"]
    if "eeprom_persistence_enabled" not in serialized:
        serialized["eeprom_persistence_enabled"] = True
    if "dialog_once_flags" not in serialized:
        serialized["dialog_once_flags"] = 0
    players = serialized.get("players")
    if isinstance(players, list):
        for player in players:
            if isinstance(player, dict):
                if "damage_sample_count" not in player:
                    player["damage_sample_count"] = 0
                    player["cumulative_damage"] = 0

    for field in fields(state):
        name = field.name
        value = serialized[name]
        if name == "mobs":
            state.mobs = _restore_mobs(value)
        elif name == "rng":
            if not isinstance(value, dict) or set(value) != {"seed"}:
                raise StateDumpError("invalid RNG state")
            state.rng = GameRandom(value["seed"])
        elif name == "maze":
            state.maze = _restore_maze(value)
        elif name == "players":
            if not isinstance(value, list) or len(value) != len(state.players):
                raise StateDumpError("invalid players record list")
            for player, player_payload in zip(state.players, value):
                _restore_dataclass(player, player_payload)
        elif name == "info_panel":
            _restore_dataclass(state.info_panel, value)
        elif name == "path_direction_grid":
            state.path_direction_grid = _restore_bytearray(value)
        elif name == "playfield_forcefield_cells":
            if not isinstance(value, list):
                raise StateDumpError("invalid playfield_forcefield_cells")
            state.playfield_forcefield_cells = set(value)
        elif name == "playfield_floor_descriptors":
            state.playfield_floor_descriptors = [tuple(item) for item in value]
        elif name == "high_scores":
            state.high_scores = [
                [tuple(record) for record in ladder] for ladder in value
            ]
        elif name == "playfield_floor_catalog":
            state.playfield_floor_catalog = _mapping(value, tuple_values=True)
        elif name in {
            "playfield_wall_catalog",
            "playfield_destruct_catalog",
            "playfield_forcefield_catalog",
        }:
            state.__dict__[name] = _mapping(value, tuple_values=True)
        elif isinstance(getattr(state, name), dict):
            state.__dict__[name] = _mapping(value)
        else:
            setattr(state, name, value)
    # A historical snapshot must not roll current operator/high-score/rotation
    # persistence backward when its captured timer next expires.
    state.eeprom_persistence_enabled = False
    if "synthetic_scenario" in payload:
        from ..custom_scenario import (
            SyntheticScenarioError,
            restore_synthetic_runtime,
        )

        try:
            restore_synthetic_runtime(state, payload["synthetic_scenario"])
        except SyntheticScenarioError as exc:
            raise StateDumpError(f"invalid synthetic scenario metadata: {exc}") from exc
    return state


def load_game_state(path: str | Path) -> GameState:
    """Load a complete state dump without running boot or level setup."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StateDumpError(f"could not read saved state {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise StateDumpError(f"saved state is not valid JSON: {exc}") from exc
    try:
        return game_state_from_payload(payload)
    except StateDumpError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise StateDumpError(f"invalid saved-state value: {exc}") from exc


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
