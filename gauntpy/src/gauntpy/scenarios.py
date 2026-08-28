"""Deterministic headless gameplay scenarios and compact state traces.

Run ``gauntpy-scenario list`` or, with ROMs configured,
``gauntpy-scenario run level7-seam --frames 240 --every 4``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .constants import (
    SLOT_DEMON_SHOTS,
    SLOT_LOBBER_SHOTS,
    SLOT_PLAYER_SHOTS,
    Character,
    GameMode,
    MazeObjIds,
    PlayerStatus,
)
from .coords import (
    encode_hpos,
    encode_vpos_at_y,
    hpos_x,
    pack_slot,
    vpos_y,
)
from .mainloop import tick
from .state import GameState
from .subsystems.input import JOY_DOWN, JOY_IDLE, JOY_LEFT, JOY_RIGHT


Step = Callable[[GameState, int], None]
Build = Callable[[], GameState]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    default_frames: int
    build: Build
    step: Step


def _tick_with_input(script: Callable[[int], int]) -> Step:
    def step(state: GameState, frame: int) -> None:
        state.player_input_raw[0] = script(frame) & 0xFFFF
        tick(state)

    return step


def _idle(_frame: int) -> int:
    return JOY_IDLE


def _level1_state() -> GameState:
    from .play import build_state

    return build_state(1, Character.WARRIOR)


def _level1_input(frame: int) -> int:
    if frame < 60:
        return JOY_IDLE & ~JOY_RIGHT
    if frame < 100:
        return JOY_IDLE & ~JOY_DOWN
    return JOY_IDLE


def _level7_state() -> GameState:
    from .play import build_state

    return build_state(7, Character.WARRIOR)


def _level7_input(frame: int) -> int:
    return JOY_IDLE & ~JOY_LEFT if frame < 220 else JOY_IDLE


def _forcefield_state() -> GameState:
    from .maze import maze_place_object

    state = GameState(game_mode=GameMode.NORMAL, level_players_active=1)
    left, right = pack_slot(5, 5), pack_slot(5, 9)
    maze_place_object(state, left, MazeObjIds.FORCEFIELDHUB, 1)
    maze_place_object(state, right, MazeObjIds.FORCEFIELDHUB, 1)
    player = state.players[0]
    player.status = PlayerStatus.ALIVE_HERE
    player.health = 2000
    player.mob_slot = pack_slot(5, 7)
    state.mobs.create(
        player.mob_slot,
        tile=0x1E0D,
        hpos=encode_hpos(7 * 16 - 4, palette=0x0C),
        vpos=encode_vpos_at_y(5 * 16, 3, 3),
        obj_type=MazeObjIds.PLAYERSTART,
        state=0,
    )
    state.player_in_maze[0] = 1
    state.player_tile_or_tport_dest[0] = player.mob_slot
    return state


def _dragon_state() -> GameState:
    from .subsystems.dragon import dragon_setup_segments

    state = GameState(game_mode=GameMode.NORMAL, level_players_active=1)
    primary = pack_slot(10, 10)
    segments = (
        primary,
        primary - 0x20,
        primary + 1,
        primary - 0x1F,
    )
    for index, slot in enumerate(segments):
        state.mobs.create(
            slot,
            tile=0xA000 + index,
            hpos=encode_hpos((slot & 0x1F) * 16),
            vpos=encode_vpos_at_y((slot >> 5) * 16, 4, 4),
            obj_type=MazeObjIds.MONST_DRAGON,
        )
    dragon_setup_segments(state, primary)
    player = state.players[0]
    player.status = PlayerStatus.ALIVE_HERE
    player.health = 2000
    player.mob_slot = pack_slot(13, 10)
    state.mobs.create(
        player.mob_slot,
        tile=0x1E0D,
        hpos=encode_hpos(10 * 16 - 4, palette=0x0C),
        vpos=encode_vpos_at_y(13 * 16, 3, 3),
        obj_type=MazeObjIds.PLAYERSTART,
    )
    state.player_in_maze[0] = 1
    state.player_tile_or_tport_dest[0] = player.mob_slot
    return state


def _dragon_step(state: GameState, _frame: int) -> None:
    from .subsystems.dragon import main_handle_dragon

    main_handle_dragon(state)
    state.frame_counter = (state.frame_counter + 1) & 0xFFFF


def _demo_state() -> GameState:
    from .subsystems.attract import start_attract_screen

    state = GameState()
    start_attract_screen(state, int(GameMode.DEMO))
    return state


def _close_combat_state() -> GameState:
    from .subsystems.players import player_create_shot

    state = GameState(game_mode=GameMode.NORMAL, level_players_active=1)
    player = state.players[0]
    player.status = PlayerStatus.ALIVE_HERE
    player.health = 2000
    player.mob_slot = pack_slot(10, 10)
    state.mobs.create(
        player.mob_slot,
        tile=0x1E0D,
        hpos=encode_hpos(160, palette=0x0C),
        vpos=encode_vpos_at_y(160, 3, 3),
        obj_type=MazeObjIds.PLAYERSTART,
    )
    monster = pack_slot(10, 11)
    state.mobs.create(
        monster,
        tile=0x1234,
        hpos=encode_hpos(172, palette=0x09),
        vpos=encode_vpos_at_y(157, 3, 3),
        obj_type=MazeObjIds.MONST_SORC,
    )
    player.direction = 0
    player_create_shot(state, 0)
    return state


def _shots_step(state: GameState, _frame: int) -> None:
    from .subsystems.shots import resolve_shot_hit, shot_mob_collision

    target = shot_mob_collision(state, pack_slot(10, 10), 0)
    if target >= 0:
        resolve_shot_hit(state, target, 0)
    state.frame_counter = (state.frame_counter + 1) & 0xFFFF


SCENARIOS: dict[str, Scenario] = {
    scenario.name: scenario
    for scenario in (
        Scenario(
            "level1",
            "Opening maze movement, pickup, collision, and camera smoke run.",
            180,
            _level1_state,
            _tick_with_input(_level1_input),
        ),
        Scenario(
            "level7-seam",
            "Walk left across level 7's horizontal seam while monsters track.",
            300,
            _level7_state,
            _tick_with_input(_level7_input),
        ),
        Scenario(
            "forcefields",
            "Two marker hubs, a player in the beam, and repeated random phases.",
            700,
            _forcefield_state,
            _tick_with_input(_idle),
        ),
        Scenario(
            "dragon-range",
            "A player near a dragon, tracing target packing and fire mode.",
            160,
            _dragon_state,
            _dragon_step,
        ),
        Scenario(
            "demo-playback",
            "The full recorded attract-mode Elf demonstration.",
            7000,
            _demo_state,
            _tick_with_input(_idle),
        ),
        Scenario(
            "close-combat",
            "A point-blank player projectile and Sorcerer collision.",
            12,
            _close_combat_state,
            _shots_step,
        ),
    )
}


def digest_state(state: GameState) -> dict:
    """Compact JSON-safe trace row for the recurring fidelity scenarios."""
    creature_counts = Counter(
        state.mobs.obj_type(slot)
        for slot in state.mobs.iter_chain()
        if 18 <= state.mobs.obj_type(slot) <= 45
    )
    players = []
    for player in state.players:
        if not player.mob_slot and not player.status:
            continue
        slot = player.mob_slot
        players.append(
            {
                "i": player.index,
                "slot": slot,
                "x": hpos_x(state.mobs.hpos[slot]) if slot else None,
                "y": vpos_y(state.mobs.vpos[slot]) if slot else None,
                "status": int(player.status),
                "health": player.health,
                "score": player.score,
                "cell": state.player_tile_or_tport_dest[player.index],
            }
        )
    shots = []
    for slot in (
        *SLOT_PLAYER_SHOTS,
        *SLOT_DEMON_SHOTS,
        *SLOT_LOBBER_SHOTS,
    ):
        if not state.mobs.picture[slot]:
            continue
        shots.append(
            {
                "slot": slot,
                "picture": state.mobs.picture[slot],
                "x": hpos_x(state.mobs.hpos[slot]),
                "y": vpos_y(state.mobs.vpos[slot]),
                "dir": state.shot_direction[slot - 1],
            }
        )
    return {
        "frame": state.frame_counter,
        "mode": int(state.game_mode),
        "level": state.levelnum_current,
        "maze": state.mazenum_current,
        "rng": state.rng.seed,
        "scroll": [state.scroll_x, state.scroll_y],
        "players": players,
        "creatures": dict(sorted(creature_counts.items())),
        "shots": shots,
        "forcefield": {
            "step": state.forcefield_step,
            "timer": state.forcefield_step_timer,
            "color": state.forcefield_color,
            "segments": list(state.forcefield_segment_table),
        },
        "dragon": {
            "slot": state.dragon_mob_slot,
            "state": state.dragon_state,
            "target": state.dragon_move_state,
            "facing": state.dragon_facing,
            "cooldown": state.dragon_fire_cooldown,
        },
        "demo_pos": list(state.demo_stream_pos),
    }


def run_scenario(name: str, frames: int | None = None, every: int = 1) -> list[dict]:
    scenario = SCENARIOS[name]
    frame_count = scenario.default_frames if frames is None else frames
    if frame_count < 0:
        raise ValueError("frames must be non-negative")
    if every < 1:
        raise ValueError("every must be at least one")
    state = scenario.build()
    trace = [digest_state(state)]
    for frame in range(frame_count):
        scenario.step(state, frame)
        if (frame + 1) % every == 0:
            trace.append(digest_state(state))
    return trace


def run_synthetic_scenario(
    path: str | Path, frames: int | None = None, every: int = 1,
) -> tuple[object, list[dict]]:
    """Run a declarative synthetic fixture through the ordinary frame loop."""
    from .custom_scenario import (
        apply_synthetic_events,
        build_synthetic_state,
        load_synthetic_scenario,
    )

    scenario = load_synthetic_scenario(path)
    frame_count = scenario.default_frames if frames is None else frames
    if frame_count < 0:
        raise ValueError("frames must be non-negative")
    if every < 1:
        raise ValueError("every must be at least one")
    state = build_synthetic_state(scenario)
    trace = [digest_state(state)]
    for frame in range(frame_count):
        apply_synthetic_events(state)
        tick(state)
        if (frame + 1) % every == 0:
            trace.append(digest_state(state))
    return scenario, trace


def _write_trace(payload: object, output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gauntpy-scenario")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list deterministic scenarios")
    run = subparsers.add_parser("run", help="run and trace one scenario")
    run.add_argument("scenario", help="built-in scenario name or synthetic .gsc path")
    run.add_argument("--frames", type=int)
    run.add_argument("--every", type=int, default=1)
    run.add_argument("--output")
    args = parser.parse_args(argv)

    if args.command == "list":
        _write_trace(
            [
                {
                    "name": item.name,
                    "description": item.description,
                    "default_frames": item.default_frames,
                }
                for item in SCENARIOS.values()
            ],
            None,
        )
        return

    if args.scenario in SCENARIOS:
        trace = run_scenario(args.scenario, args.frames, args.every)
        scenario_name = args.scenario
        default_frames = SCENARIOS[args.scenario].default_frames
        synthetic = False
    else:
        scenario, trace = run_synthetic_scenario(
            args.scenario, args.frames, args.every,
        )
        scenario_name = scenario.name
        default_frames = scenario.default_frames
        synthetic = True
    _write_trace(
        {
            "scenario": scenario_name,
            "synthetic": synthetic,
            "frames": args.frames
            if args.frames is not None
            else default_frames,
            "every": args.every,
            "trace": trace,
        },
        args.output,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
