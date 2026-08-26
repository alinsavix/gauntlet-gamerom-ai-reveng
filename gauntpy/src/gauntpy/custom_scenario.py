"""Declarative synthetic mazes for deterministic host-side reproductions.

These files are test fixtures, not decoded game content. They use normal
game-side maze/MOB/playfield writers, but they cannot establish ROM fidelity.
"""

from __future__ import annotations

import hashlib
import shlex
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .constants import Character, GameMode, MazeObjIds
from .rng import GameRandom
from .state import GameState
from .subsystems.input import (
    JOY_DOWN,
    JOY_IDLE,
    JOY_LEFT,
    JOY_RIGHT,
    JOY_UP,
)

SYNTHETIC_SCENARIO_FORMAT = "gauntpy-synthetic-maze-v1"
_RUNTIME_ATTRIBUTE = "_gauntpy_synthetic_scenario"

_DEFAULT_LEGEND = {
    ".": MazeObjIds.TILE_FLOOR,
    " ": MazeObjIds.TILE_FLOOR,
    "#": MazeObjIds.WALL_REGULAR,
    "m": MazeObjIds.WALL_MOVABLE,
    "s": MazeObjIds.WALL_SECRET,
    "w": MazeObjIds.WALL_DESTRUCTABLE,
    "?": MazeObjIds.WALL_RANDOM,
    "@": MazeObjIds.PLAYERSTART,
    "E": MazeObjIds.EXIT,
    "G": MazeObjIds.MONST_GHOST,
    "g": MazeObjIds.MONST_GRUNT,
    "d": MazeObjIds.MONST_DEMON,
    "l": MazeObjIds.MONST_LOBBER,
    "z": MazeObjIds.MONST_SORC,
    "a": MazeObjIds.MONST_ACID,
    "T": MazeObjIds.TREASURE,
    "C": MazeObjIds.TREASURE_LOCKED,
    "f": MazeObjIds.FOOD_DESTRUCTABLE,
    "p": MazeObjIds.POT_DESTRUCTABLE,
    "k": MazeObjIds.KEY,
    "O": MazeObjIds.TRANSPORTER,
    "F": MazeObjIds.FORCEFIELDHUB,
}

_CHARACTERS = {
    "warrior": Character.WARRIOR,
    "valkyrie": Character.VALKYRIE,
    "wizard": Character.WIZARD,
    "elf": Character.ELF,
}

_DIRECTIONS = {
    "idle": JOY_IDLE,
    "up": JOY_IDLE & ~JOY_UP,
    "down": JOY_IDLE & ~JOY_DOWN,
    "left": JOY_IDLE & ~JOY_LEFT,
    "right": JOY_IDLE & ~JOY_RIGHT,
    "up-left": JOY_IDLE & ~(JOY_UP | JOY_LEFT),
    "up-right": JOY_IDLE & ~(JOY_UP | JOY_RIGHT),
    "down-left": JOY_IDLE & ~(JOY_DOWN | JOY_LEFT),
    "down-right": JOY_IDLE & ~(JOY_DOWN | JOY_RIGHT),
}


class SyntheticScenarioError(ValueError):
    """A synthetic scenario file is malformed or unsafe to execute."""


@dataclass(frozen=True)
class SyntheticEvent:
    frame: int
    action: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyntheticScenario:
    name: str
    description: str
    default_frames: int
    level: int
    maze_number: int
    flags: int
    seed: int
    character: int
    health: int
    wallpattern: int
    wallcolor: int
    floorpattern: int
    floorcolor: int
    initial_input: int | None
    grid: tuple[str, ...]
    legend: tuple[tuple[str, int], ...]
    events: tuple[SyntheticEvent, ...]
    canonical_content: str
    sha256: str
    source_name: str | None = None


@dataclass
class SyntheticScenarioRuntime:
    scenario: SyntheticScenario
    fired_events: set[int] = field(default_factory=set)
    current_input: int | None = None

    def __post_init__(self) -> None:
        if self.current_input is None:
            self.current_input = self.scenario.initial_input


def _integer(value: str, name: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value, 0)
    except ValueError as exc:
        raise SyntheticScenarioError(f"{name} must be an integer") from exc
    if not minimum <= result <= maximum:
        raise SyntheticScenarioError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return result


def _object_type(value: str) -> int:
    try:
        return int(MazeObjIds[value.upper()])
    except KeyError:
        return _integer(value, "legend object", 0, 63)


def _input_word(value: str) -> int | None:
    normalized = value.lower()
    if normalized == "live":
        return None
    try:
        return _DIRECTIONS[normalized]
    except KeyError as exc:
        raise SyntheticScenarioError(
            f"unknown input direction {value!r}"
        ) from exc


def parse_synthetic_scenario(
    text: str, *, source_name: str | None = None,
) -> SyntheticScenario:
    """Parse one versioned manifest and its exact 32x32 ASCII maze."""
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    if not canonical.endswith("\n"):
        canonical += "\n"

    headers: dict[str, str] = {}
    legend = dict(_DEFAULT_LEGEND)
    events: list[SyntheticEvent] = []
    grid: list[str] = []
    section = "header"
    for line_number, line in enumerate(canonical.splitlines(), 1):
        marker = line.strip().lower()
        if marker in {"[maze]", "[legend]", "[events]"}:
            section = marker[1:-1]
            continue
        if section == "maze":
            grid.append(line)
            continue
        if not marker or marker.startswith(";"):
            continue
        if section == "events":
            try:
                parts = shlex.split(line)
            except ValueError as exc:
                raise SyntheticScenarioError(
                    f"line {line_number}: invalid event syntax"
                ) from exc
            if len(parts) < 2:
                raise SyntheticScenarioError(
                    f"line {line_number}: event needs a frame and action"
                )
            frame = _integer(parts[0], "event frame", 0, 0xFFFF)
            events.append(SyntheticEvent(frame, parts[1].lower(), tuple(parts[2:])))
            continue
        if "=" not in line:
            raise SyntheticScenarioError(
                f"line {line_number}: expected key = value"
            )
        key, value = (part.strip() for part in line.split("=", 1))
        if section == "legend":
            if len(key) != 1:
                raise SyntheticScenarioError(
                    f"line {line_number}: legend keys must be one character"
                )
            legend[key] = MazeObjIds(_object_type(value))
        else:
            headers[key.lower()] = value

    if headers.get("format") != SYNTHETIC_SCENARIO_FORMAT:
        raise SyntheticScenarioError(
            f"format must be {SYNTHETIC_SCENARIO_FORMAT!r}"
        )
    if len(grid) != 32 or any(len(row) != 32 for row in grid):
        raise SyntheticScenarioError("maze must contain exactly 32 rows of 32 characters")
    unknown = sorted({symbol for row in grid for symbol in row if symbol not in legend})
    if unknown:
        raise SyntheticScenarioError(
            "maze uses undefined symbols: " + ", ".join(repr(item) for item in unknown)
        )
    if any(legend[symbol] != MazeObjIds.WALL_REGULAR for symbol in grid[0]):
        raise SyntheticScenarioError("maze row 0 must be entirely regular walls")
    starts = sum(
        legend[symbol] == MazeObjIds.PLAYERSTART
        for row in grid for symbol in row
    )
    if starts < 1:
        raise SyntheticScenarioError("maze needs at least one player start")

    character_name = headers.get("character", "elf").lower()
    if character_name not in _CHARACTERS:
        raise SyntheticScenarioError(f"unknown character {character_name!r}")
    initial_input = _input_word(headers.get("input", "live"))
    for index, event in enumerate(events):
        if event.action == "input":
            if len(event.args) != 1:
                raise SyntheticScenarioError("input event needs one direction")
            _input_word(event.args[0])
        elif event.action == "activate_thief":
            if len(event.args) not in (2, 3):
                raise SyntheticScenarioError(
                    "activate_thief needs row column [thief|mugger]"
                )
            _integer(event.args[0], "thief row", 1, 31)
            _integer(event.args[1], "thief column", 0, 31)
            if len(event.args) == 3 and event.args[2].lower() not in {"thief", "mugger"}:
                raise SyntheticScenarioError(
                    "activate_thief variant must be thief or mugger"
                )
        else:
            raise SyntheticScenarioError(
                f"event {index}: unsupported action {event.action!r}"
            )
    if sum(event.action == "activate_thief" for event in events) > 1:
        raise SyntheticScenarioError(
            "a synthetic scenario may schedule only one activate_thief event"
        )

    return SyntheticScenario(
        name=headers.get("name", Path(source_name).stem if source_name else "synthetic"),
        description=headers.get("description", "Synthetic gauntpy reproduction."),
        default_frames=_integer(headers.get("frames", "600"), "frames", 0, 0x7FFFFFFF),
        level=_integer(headers.get("level", "1"), "level", 1, 9999),
        maze_number=_integer(headers.get("maze_number", "0"), "maze_number", 0, 116),
        flags=_integer(headers.get("flags", "0"), "flags", 0, 0xFFFFFFFF),
        seed=_integer(headers.get("seed", "0"), "seed", 0, 0xFFFF),
        character=int(_CHARACTERS[character_name]),
        health=_integer(headers.get("health", "2000"), "health", 1, 0x7FFFFFFF),
        wallpattern=_integer(headers.get("wallpattern", "0"), "wallpattern", 0, 11),
        wallcolor=_integer(headers.get("wallcolor", "0"), "wallcolor", 0, 15),
        floorpattern=_integer(headers.get("floorpattern", "0"), "floorpattern", 0, 15),
        floorcolor=_integer(headers.get("floorcolor", "0"), "floorcolor", 0, 15),
        initial_input=initial_input,
        grid=tuple(grid),
        legend=tuple(sorted((symbol, int(obj)) for symbol, obj in legend.items())),
        events=tuple(sorted(events, key=lambda item: item.frame)),
        canonical_content=canonical,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_name=Path(source_name).name if source_name else None,
    )


def load_synthetic_scenario(path: str | Path) -> SyntheticScenario:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise SyntheticScenarioError(
            f"could not read synthetic scenario {source}: {exc}"
        ) from exc
    return parse_synthetic_scenario(text, source_name=source.name)


def attach_synthetic_runtime(
    state: GameState, runtime: SyntheticScenarioRuntime,
) -> None:
    setattr(state, _RUNTIME_ATTRIBUTE, runtime)


def synthetic_runtime_for(state: GameState) -> SyntheticScenarioRuntime | None:
    runtime = getattr(state, _RUNTIME_ATTRIBUTE, None)
    return runtime if isinstance(runtime, SyntheticScenarioRuntime) else None


def build_synthetic_state(scenario: SyntheticScenario) -> GameState:
    """Build a playable state through the ordinary game-side memory writers."""
    from gex.mazedecode import Maze

    from . import maze as maze_module
    from .play import _spawn_player
    from .subsystems.display import init_alpha_color_ram
    from .subsystems.exits import exit_scan_level
    from .subsystems.maze_objects import (
        forcefield_segments_setup,
        maze_forcefield_setup,
        select_forcefield_delay_profile,
        setup_door_graphics,
    )
    from .subsystems.players import setup_infopanel
    from .subsystems.eeprom import GAME_DEFAULT_SETTINGS

    state = GameState(
        game_mode=GameMode.NORMAL,
        game_settings=GAME_DEFAULT_SETTINGS,
        rng=GameRandom(scenario.seed),
    )
    init_alpha_color_ram(state)
    state.levelnum_current = scenario.level
    state.mazenum_current = scenario.maze_number
    (
        state.level_flags,
        state.level_flags_2,
        state.level_flags_3,
        state.level_flags_4,
    ) = maze_module._split_flags(scenario.flags)
    state.wrap_h = bool(state.level_flags_4 & 0x20)
    state.wrap_v = bool(state.level_flags_4 & 0x10)
    state.thief_level_setup_done = True
    state.random_pickups_setup_done = True
    select_forcefield_delay_profile(state)

    legend = dict(scenario.legend)
    data = {
        (column, row): int(legend[symbol])
        for row, line in enumerate(scenario.grid)
        for column, symbol in enumerate(line)
        if legend[symbol] != int(MazeObjIds.TILE_FLOOR)
    }
    decoded = Maze(
        data=data,
        flags=scenario.flags,
        wallpattern=scenario.wallpattern,
        wallcolor=scenario.wallcolor,
        floorpattern=scenario.floorpattern,
        floorcolor=scenario.floorcolor,
    )
    maze_module.place_decoded_objects(state, decoded)
    maze_module.maze_place_object(
        state, 0, MazeObjIds.WALL_REGULAR, 32,
    )
    state.maze = maze_module.mirror_maze(state, decoded)
    maze_module.select_player_start_slot(state)
    forcefield_segments_setup(state)
    if state.level_flags_3 & 0x08:
        maze_forcefield_setup(state)
    maze_module.initialize_playfield_ram(state, state.maze)
    setup_door_graphics(state)
    exit_scan_level(state)
    _spawn_player(state, scenario.character)
    state.players[0].health = scenario.health
    setup_infopanel(state, -1)

    runtime = SyntheticScenarioRuntime(scenario)
    for event in scenario.events:
        if event.action == "activate_thief":
            _prepare_thief(state, event.frame, *event.args)
    attach_synthetic_runtime(state, runtime)
    return state


def _prepare_thief(
    state: GameState, target_frame: int, row_text: str, column_text: str,
    variant: str = "thief",
) -> None:
    from .coords import pack_slot
    from .subsystems import thief

    row = _integer(row_text, "thief row", 1, 31)
    column = _integer(column_text, "thief column", 0, 31)
    slot = pack_slot(row, column)
    if state.mobs.picture[slot]:
        raise SyntheticScenarioError(
            f"activate_thief destination {row},{column} is occupied"
        )
    player = state.players[0]
    if not player.active or not player.mob_slot:
        raise SyntheticScenarioError("activate_thief needs an active player 1")
    state.thief_victim = 0
    state.thief_start_location = slot
    state.thief_victim_pos = player.mob_slot
    state.thief_item_carried = thief._THIEF_CARRIED_EMPTY
    state.thief_mode = thief.THIEF_PURSUE
    if variant.lower() == "mugger":
        state.thief_mode |= thief.THIEF_IS_MUGGER
        state.thief_speed = thief._SPEED_MUGGER
    else:
        state.thief_speed = thief._SPEED_THIEF
    _seed_synthetic_thief_route(state, slot, player.mob_slot)
    state.thief_enter_time = (target_frame - state.frame_counter) & 0xFFFF
    state.thief_level_setup_done = True


def _seed_synthetic_thief_route(
    state: GameState, start: int, target: int,
) -> None:
    """Create the victim breadcrumbs a delayed normal deployment would inherit."""
    from .subsystems import thief

    directions = ((0, -1, 0), (2, 0, 1), (4, 1, 0), (6, 0, -1))
    queue = deque([start])
    previous: dict[int, tuple[int, int]] = {}
    visited = {start}
    while queue:
        current = queue.popleft()
        if current == target:
            break
        row, column = current >> 5, current & 0x1F
        for direction, row_delta, column_delta in directions:
            next_row = row + row_delta
            next_column = column + column_delta
            if state.wrap_v:
                next_row &= 0x1F
            elif not 1 <= next_row < 32:
                continue
            if state.wrap_h:
                next_column &= 0x1F
            elif not 0 <= next_column < 32:
                continue
            candidate = (next_row << 5) | next_column
            if candidate in visited:
                continue
            if (
                candidate != target
                and not thief._route_cell_is_traversable(state, candidate)
            ):
                continue
            visited.add(candidate)
            previous[candidate] = (current, direction)
            queue.append(candidate)
    if target not in visited:
        raise SyntheticScenarioError(
            "activate_thief has no traversable route to player 1"
        )

    route: list[tuple[int, int]] = []
    current = target
    while current != start:
        parent, direction = previous[current]
        route.append((parent, direction))
        current = parent
    for cell, direction in reversed(route):
        thief.path_grid_set_low_direction(state, cell, direction)


def apply_synthetic_events(state: GameState) -> None:
    """Apply this frame's bounded host events before the ordinary game tick."""
    runtime = synthetic_runtime_for(state)
    if runtime is None:
        return
    for index, event in enumerate(runtime.scenario.events):
        if index in runtime.fired_events or event.frame != state.frame_counter:
            continue
        if event.action == "input":
            runtime.current_input = _input_word(event.args[0])
        elif event.action == "activate_thief":
            # The victim and countdown were armed at scenario construction so
            # ordinary player movement could extend the pursuit breadcrumbs.
            pass
        runtime.fired_events.add(index)
    if runtime.current_input is not None:
        state.player_input_raw[0] = runtime.current_input


def synthetic_runtime_payload(state: GameState) -> dict[str, object] | None:
    runtime = synthetic_runtime_for(state)
    if runtime is None:
        return None
    scenario = runtime.scenario
    return {
        "format": SYNTHETIC_SCENARIO_FORMAT,
        "synthetic": True,
        "source_name": scenario.source_name,
        "sha256": scenario.sha256,
        "content": scenario.canonical_content,
        "fired_events": sorted(runtime.fired_events),
        "current_input": runtime.current_input,
    }


def restore_synthetic_runtime(
    state: GameState, payload: object,
) -> None:
    if payload is None:
        return
    if not isinstance(payload, dict) or payload.get("synthetic") is not True:
        raise SyntheticScenarioError("invalid synthetic scenario dump metadata")
    content = payload.get("content")
    if not isinstance(content, str):
        raise SyntheticScenarioError("synthetic scenario dump has no content")
    canonical = content.replace("\r\n", "\n").replace("\r", "\n")
    if not canonical.endswith("\n"):
        canonical += "\n"
    expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if payload.get("sha256") != expected_hash:
        raise SyntheticScenarioError("synthetic scenario dump hash mismatch")
    source_name = payload.get("source_name")
    if source_name is not None and not isinstance(source_name, str):
        raise SyntheticScenarioError("invalid synthetic scenario source name")
    scenario = parse_synthetic_scenario(canonical, source_name=source_name)
    fired = payload.get("fired_events", [])
    if not isinstance(fired, list) or not all(isinstance(item, int) for item in fired):
        raise SyntheticScenarioError("invalid synthetic fired-event list")
    current_input = payload.get("current_input")
    if current_input is not None and not isinstance(current_input, int):
        raise SyntheticScenarioError("invalid synthetic current input")
    runtime = SyntheticScenarioRuntime(scenario, fired_events=set(fired))
    runtime.current_input = current_input
    attach_synthetic_runtime(state, runtime)
