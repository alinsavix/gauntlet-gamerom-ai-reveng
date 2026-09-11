"""A minimum playable runner: walk a hero around a real Gauntlet II maze.

    uv run gauntpy-play            # level 1, Elf; muted, 60 Hz
    uv run gauntpy-play --sound --level 2 --character elf --scale 3
    uv run gauntpy-play --uncapped # no host frame limiter
    uv run gauntpy-play --level 115 --maze 3

By default it loads a maze and drops a player directly into gameplay; ``--attract``
boots through the complete cabinet front end. Both paths drive the real
``game_frame`` in a pygame window with keyboard input. The host defaults to a
60 Hz limit and muted playback; command-line switches can remove the limit or
play the accepted command stream without changing modeled game state.

Requires the ROM-graphics and display extras::

    uv run --extra rom --extra display gauntpy-play
    # or: uv run --all-extras gauntpy-play
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from ..game.constants import Character, MazeObjIds
from ..game.mainloop import tick
from ..performance_workloads import (
    WORKLOADS,
    build_workload_state as _build_workload_state,
    selected_workloads,
    validate_runtime_invariants,
)
from ..game.state import GameState
from .eeprom import PersistencePolicy, bind_eeprom_storage
from .run_policy import BenchmarkRun, RunPolicy, StressRun
from .session import HostSession
from .startup import build_cold_boot_state, build_state

if TYPE_CHECKING:
    from .shell import HostShell

#: Highest maze number the Slapstic image holds (gex's own bound, restated so
#: ``--maze`` can be checked without importing gex at module import time --
#: ``play`` must stay importable with no ROMs configured).
MAX_MAZE_NUM = 116

_CHARACTERS = {
    "warrior": Character.WARRIOR,
    "valkyrie": Character.VALKYRIE,
    "wizard": Character.WIZARD,
    "elf": Character.ELF,
}

_TEMPORARY_POWERS = {
    "invisibility": MazeObjIds.POWER_INVIS,
    "repulsiveness": MazeObjIds.POWER_REPULSE,
    "reflective-shots": MazeObjIds.POWER_REFLECT,
    "transportability": MazeObjIds.POWER_TRANSPORT,
    "super-shots": MazeObjIds.POWER_SUPERSHOT,
    "invulnerability": MazeObjIds.POWER_INVULN,
}


def _positive_level(value: str) -> int:
    level = int(value)
    if level < 1:
        raise argparse.ArgumentTypeError("level must be 1 or greater")
    return level


def _maze_number(value: str) -> int:
    maze_number = int(value)
    if not 0 <= maze_number <= MAX_MAZE_NUM:
        raise argparse.ArgumentTypeError(
            f"maze must be between 0 and {MAX_MAZE_NUM}"
        )
    return maze_number


def _positive_scale(value: str) -> int:
    scale = int(value)
    if scale < 1:
        raise argparse.ArgumentTypeError("scale must be 1 or greater")
    return scale


def _inventory_count(value: str) -> int:
    count = int(value)
    if not 0 <= count <= 255:
        raise argparse.ArgumentTypeError("inventory count must be between 0 and 255")
    return count


def _positive_frame_count(value: str) -> int:
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError("frame count must be 1 or greater")
    return count


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be greater than zero")
    return seconds


def _ensure_rom_dir() -> None:
    """Point gex at the repo's ROMs/ directory unless the user set GEX_ROM_DIR."""
    if os.environ.get("GEX_ROM_DIR"):
        return
    repo_roms = Path(__file__).resolve().parents[4] / "ROMs"
    if repo_roms.is_dir():
        os.environ["GEX_ROM_DIR"] = str(repo_roms)


def _sound_dir() -> Path:
    configured = os.environ.get("GAUNTPY_SOUND_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "sounds"


def _enabled_sound_dir(enabled: bool) -> Path | None:
    """Resolve the local recording library only when playback was requested."""
    if not enabled:
        return None
    sound_dir = _sound_dir()
    if sound_dir.is_dir():
        return sound_dir
    print(
        f"gauntpy sound library not found at {sound_dir}; "
        "running without audio (set GAUNTPY_SOUND_DIR to override)",
        file=sys.stderr,
    )
    return None


def _apply_operator_overrides(state: GameState, *, reduce_text: bool) -> None:
    if reduce_text:
        from ..game.subsystems.score import GAME_SETTINGS_REDUCE_TEXT

        state.game_settings |= GAME_SETTINGS_REDUCE_TEXT


def _seed_value(value: str) -> int | str:
    """Parse an explicit 16-bit seed or the host-random sentinel."""
    if value.lower() == "random":
        return "random"
    try:
        seed = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "seed must be a 16-bit integer or 'random'"
        ) from exc
    if not 0 <= seed <= 0xFFFF:
        raise argparse.ArgumentTypeError(
            "seed must be between 0 and 65535"
        )
    return seed


_STRESS_PHASES = WORKLOADS


def _build_stress_state(phase_index: int, rng_seed: int) -> GameState:
    """Construct one named workload through its ordinary setup routine."""
    workload = _STRESS_PHASES[phase_index]
    state = _build_workload_state(workload, rng_seed)
    state.eeprom_persistence_enabled = False
    print(f"gauntpy stress workload: {workload.name} ({workload.description})")
    return state


def run(level: int = 1, character: int = Character.ELF, scale: int = 4,
        from_attract: bool = False,
        reduce_text: bool = False,
        full_playfield: bool = False,
        sound_enabled: bool = False,
        uncapped: bool = False,
        keys: int = 0, potions: int = 0,
        powers: tuple[int, ...] = (),
        load_state_path: str | Path | None = None,
        scenario_path: str | Path | None = None,
        rng_seed: int = 0, maze_number: int | None = None,
        benchmark_frames: int | None = None,
        stress_seconds: float | None = None,
        workload_name: str | None = None) -> None:
    """Open a window and run the game loop until the player closes it.

    Two entries: the default mid-level drop (``build_state``), or -- with
    ``from_attract`` -- boot through the real front end (``one_time_init`` ->
    TITLE attract), where you insert a coin (the ``5`` key), pick a class on the
    joystick, and press Magic (Enter) to start, exactly as the cabinet does. The
    attract, high-score, legend, and character-select routines populate alpha
    VRAM; the generic alpha renderer displays it with the ROM font. The title
    screen uses the ROM's fixed playfield and procedurally built MOB records.
    """
    _ensure_rom_dir()
    policy = RunPolicy(
        benchmark_frames=benchmark_frames, stress_seconds=stress_seconds,
        uncapped=uncapped, sound_enabled=sound_enabled,
    )

    benchmark_workloads = (
        selected_workloads(workload_name)
        if benchmark_frames is not None and workload_name is not None
        else ()
    )
    stress_workloads = (
        selected_workloads(workload_name) if stress_seconds is not None else ()
    )
    stress_phase_indices = tuple(
        WORKLOADS.index(workload) for workload in stress_workloads
    )

    if stress_seconds is not None:
        state = _build_stress_state(stress_phase_indices[0], rng_seed)
    elif benchmark_workloads:
        state = _build_workload_state(benchmark_workloads[0], rng_seed)
    elif load_state_path is not None:
        from .state_dump import StateDumpError, load_game_state
        try:
            state = load_game_state(load_state_path)
        except StateDumpError as exc:
            raise SystemExit(f"could not load saved state: {exc}") from exc
    elif scenario_path is not None:
        from ..custom_scenario import (
            SyntheticScenarioError,
            build_synthetic_state,
            load_synthetic_scenario,
        )
        try:
            state = build_synthetic_state(load_synthetic_scenario(scenario_path))
        except SyntheticScenarioError as exc:
            raise SystemExit(f"could not load synthetic scenario: {exc}") from exc
    elif from_attract:
        state = build_cold_boot_state(
            rng_seed,
            persistence_policy=(
                PersistencePolicy.READ_ONLY
                if benchmark_frames is not None else PersistencePolicy.READ_WRITE
            ),
        )
    else:
        from ..maze_rom import MazeError
        try:
            state = build_state(
                level, character, keys=keys, potions=potions, powers=powers,
                rng_seed=rng_seed, maze_number=maze_number,
            )
        except MazeError as exc:
            raise SystemExit(
                f"could not load level {level}"
                f"{'' if maze_number is None else f' / maze {maze_number}'}: {exc}\n"
                "Check that GEX_ROM_DIR points at a complete Gauntlet II ROM "
                "dump (file list in python-gex/README.md)."
            ) from exc

    if policy.performance_mode:
        state.eeprom_persistence_enabled = False
        if load_state_path is None:
            bind_eeprom_storage(state, policy=PersistencePolicy.ISOLATED)
    elif scenario_path is not None:
        state.eeprom_persistence_enabled = False
        bind_eeprom_storage(state, policy=PersistencePolicy.ISOLATED)
    elif load_state_path is None and not from_attract:
        bind_eeprom_storage(state)

    session = HostSession(
        state, resumed=load_state_path is not None,
        restart_enabled=not policy.performance_mode,
    )

    try:
        from .shell import HostShell, PygameUnavailable
    except Exception as exc:  # pragma: no cover - import guard
        raise SystemExit(f"could not import the host shell: {exc}")

    try:
        host = HostShell(
            scale=scale,
            title="gauntpy",
            full_playfield=full_playfield,
            sound_dir=_enabled_sound_dir(policy.playback_enabled),
            uncapped=policy.accelerated,
        )
    except PygameUnavailable as exc:
        raise SystemExit(
            f"{exc}\n\nRun it with the display extra, e.g.:\n"
            "    uv run --all-extras gauntpy-play"
        )
    if load_state_path is not None:
        host.skip_existing_audio(state)

    _apply_operator_overrides(state, reduce_text=reduce_text)
    session.capture_level_start()

    benchmark = (
        BenchmarkRun(benchmark_frames, benchmark_workloads)
        if benchmark_frames is not None else None
    )
    stress = (
        StressRun(
            stress_seconds, stress_workloads, stress_phase_indices,
            started=perf_counter(),
        )
        if stress_seconds is not None else None
    )
    _run_loop(
        host, session, benchmark=benchmark, stress=stress,
        rng_seed=rng_seed, reduce_text=reduce_text, scale=scale,
    )


def _restore_requested_level(host: HostShell, session: HostSession) -> bool:
    """Consume F11 before a tick; presentation remains the loop's responsibility."""
    if not getattr(host, "restart_level_requested", False):
        return False
    host.restart_level_requested = False
    if not session.restart_level():
        print("gauntpy level restart unavailable until a new playable level starts")
        return False
    state = session.state
    host.state_restored(state)
    print(
        "gauntpy restored level start: "
        f"level {state.levelnum_current} / maze {state.mazenum_current}; "
        "external EEPROM writes disabled"
    )
    return True


def _run_loop(
    host: HostShell,
    session: HostSession,
    *,
    benchmark: BenchmarkRun | None,
    stress: StressRun | None,
    rng_seed: int,
    reduce_text: bool,
    scale: int,
) -> None:
    """Pump input, update once, and present; all clocks remain host observations."""
    state = session.state
    try:
        while True:
            loop_started = perf_counter()
            if stress is not None:
                elapsed = loop_started - stress.started
                if elapsed >= stress.seconds:
                    print(stress.completion_report(elapsed))
                    break
                if stress.advance_if_due(elapsed):
                    state = _build_stress_state(stress.phase_index, rng_seed)
                    bind_eeprom_storage(state, policy=PersistencePolicy.ISOLATED)
                    session = HostSession(state, restart_enabled=False)
                    _apply_operator_overrides(state, reduce_text=reduce_text)

            input_started = perf_counter()
            host.wait_for_vblank(state)     # pump events + sample keyboard + coins
            input_finished = perf_counter()
            if _restore_requested_level(host, session):
                state = session.state
                host.present(state)
                continue
            frame_updated = not host.paused
            invariant_seconds = 0.0
            if not host.paused:
                update_started = perf_counter()
                session.apply_events()
                tick(
                    state,
                    treasure_timer_paused=host.treasure_timer_paused,
                )                           # one full 60 Hz game frame
                update_finished = perf_counter()
                session.capture_level_start()
                if benchmark is not None or stress is not None:
                    invariant_workload = (
                        stress.label if stress is not None else benchmark.label
                    )
                    invariant_started = perf_counter()
                    validate_runtime_invariants(
                        state,
                        workload=invariant_workload,
                        frame=state.frame_counter,
                    )
                    invariant_seconds = perf_counter() - invariant_started
            else:
                update_started = update_finished = perf_counter()
            host.present(state)             # composite + flip
            loop_finished = perf_counter()
            if stress is not None:
                stress.frames += 1

            if benchmark is not None and benchmark.should_record(
                frame_updated=frame_updated,
            ):
                benchmark.recorder.add(
                    host_input_ms=(input_finished - input_started) * 1000.0,
                    game_update_ms=(update_finished - update_started) * 1000.0,
                    game_raster_ms=host.last_render_time_ms,
                    display_flip_ms=host.last_display_flip_time_ms,
                    complete_loop_ms=(
                        loop_finished - loop_started - invariant_seconds
                    ) * 1000.0,
                )
                if benchmark.complete:
                    print(benchmark.report(scale=scale))
                    workload = benchmark.advance_workload()
                    if workload is None:
                        break
                    state = _build_workload_state(workload, rng_seed)
                    session = HostSession(state, restart_enabled=False)
                    state.eeprom_persistence_enabled = False
                    bind_eeprom_storage(state, policy=PersistencePolicy.ISOLATED)
                    _apply_operator_overrides(state, reduce_text=reduce_text)
                    benchmark.reset_recording()
    except SystemExit:
        pass
    finally:
        host.close()


def _main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="gauntpy-play", description="Walk a hero around a Gauntlet II maze."
    )
    parser.add_argument(
        "--level", type=_positive_level,
        help="game level number; controls level-gated behavior and, unless "
             "--maze is given, selects through the cabinet maze rotation",
    )
    parser.add_argument(
        "--maze", type=_maze_number,
        help="stored maze record 0-116; does not change the game level "
             "(default level: 1)",
    )
    parser.add_argument(
        "--character", choices=sorted(_CHARACTERS),
        help="hero class (default: elf)",
    )
    parser.add_argument(
        "--scale", type=_positive_scale,
        help="window pixel scale (default: 4, or 1 with --full-playfield)",
    )
    parser.add_argument(
        "--full-playfield", action="store_true",
        help="show the entire playfield with the current camera view outlined",
    )
    parser.add_argument(
        "--seed", type=_seed_value,
        help="initial RNG seed (default: 0); use 'random' for host entropy",
    )
    parser.add_argument(
        "--attract", action="store_true",
        help="boot into attract and start via the real front end "
             "(press 5 to insert a coin, arrows to pick a class, Enter to start)",
    )
    parser.add_argument(
        "--load-state", type=Path,
        help="resume from a complete JSON state saved with F4",
    )
    parser.add_argument(
        "--scenario", type=Path,
        help="load a declarative synthetic 32x32 maze fixture",
    )
    parser.add_argument(
        "--workload", choices=("all", *(workload.name for workload in WORKLOADS)),
        help="named benchmark/stress workload; 'all' runs the complete suite",
    )
    parser.add_argument(
        "--list-workloads", action="store_true",
        help="list deterministic benchmark/stress workloads and exit",
    )
    parser.add_argument(
        "--reduce-text", action="store_true",
        help="enable the ROM's Reduce Text operator setting",
    )
    parser.add_argument(
        "--sound", action="store_true",
        help="play local command-named WAV recordings (default: off)",
    )
    parser.add_argument(
        "--uncapped", action="store_true",
        help="run without the host's 60 Hz frame-rate limit; disables sound",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--benchmark", nargs="?", const=600, type=_positive_frame_count,
        metavar="FRAMES",
        help="benchmark host input, game update, raster, display flip, and the "
             "complete uncapped loop (default: 600 measured frames)",
    )
    modes.add_argument(
        "--stresstest", type=_positive_seconds, metavar="SECONDS",
        help="run an uncapped timed workload cycling ROM-backed and synthetic "
             "scenarios",
    )
    parser.add_argument(
        "--keys", type=_inventory_count, default=0,
        help="start direct play with this many keys (0-255)",
    )
    parser.add_argument(
        "--potions", type=_inventory_count, default=0,
        help="start direct play with this many potions (0-255)",
    )
    parser.add_argument(
        "--power", action="append", choices=sorted(_TEMPORARY_POWERS), default=[],
        help="start direct play with a temporary power; may be repeated",
    )
    args = parser.parse_args(argv)
    if args.list_workloads:
        from ..performance_workloads import format_workload_catalog

        print(format_workload_catalog())
        return
    if args.workload and args.benchmark is None and args.stresstest is None:
        parser.error("--workload requires --benchmark or --stresstest")
    if args.level is not None and args.level > 999 and args.maze is None:
        parser.error(
            "--level above 999 requires --maze; ordinary level progression "
            "wraps level 1000 to level 6"
        )
    if args.attract and (args.keys or args.potions or args.power):
        parser.error("--keys, --potions, and --power require direct play (no --attract)")
    if args.load_state and (
        args.attract or args.level is not None or args.maze is not None
        or args.character is not None
        or args.keys or args.potions or args.power or args.seed is not None
    ):
        parser.error(
            "--load-state cannot be combined with --attract, --level, --maze, --character, "
            "--keys, --potions, --power, or --seed"
        )
    if args.scenario and (
        args.load_state or args.attract or args.level is not None
        or args.maze is not None
        or args.character is not None or args.keys or args.potions
        or args.power or args.seed is not None
    ):
        parser.error(
            "--scenario cannot be combined with --load-state, --attract, --level, --maze, "
            "--character, --keys, --potions, --power, or --seed"
        )
    if args.stresstest is not None and (
        args.load_state or args.scenario or args.attract or args.level is not None
        or args.maze is not None or args.character is not None
        or args.keys or args.potions or args.power
    ):
        parser.error(
            "--stresstest controls its own screens and cannot be combined with "
            "--load-state, --scenario, --attract, --level, --maze, --character, --keys, "
            "--potions, or --power"
        )
    if args.benchmark is not None and args.workload and (
        args.load_state or args.scenario or args.attract or args.level is not None
        or args.maze is not None or args.character is not None
        or args.keys or args.potions or args.power
    ):
        parser.error(
            "--benchmark with --workload controls its own state and cannot be "
            "combined with --load-state, --scenario, --attract, --level, --maze, "
            "--character, --keys, --potions, or --power"
        )
    if (args.benchmark is not None or args.stresstest is not None) and args.sound:
        parser.error("--benchmark and --stresstest disable host sound playback")

    _ensure_rom_dir()
    if not os.environ.get("GEX_ROM_DIR"):
        print(
            "No ROMs found. Set GEX_ROM_DIR to your Gauntlet II ROM directory, "
            "or put the files in ./ROMs.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    rng_seed = (
        int.from_bytes(os.urandom(2), "big")
        if args.seed == "random"
        else 0 if args.seed is None
        else args.seed
    )
    scale = args.scale if args.scale is not None else (1 if args.full_playfield else 4)
    run(level=args.level or 1,
        character=_CHARACTERS[args.character or "elf"], scale=scale,
        from_attract=args.attract,
        reduce_text=args.reduce_text,
        full_playfield=args.full_playfield,
        sound_enabled=args.sound and not args.uncapped,
        uncapped=args.uncapped,
        keys=args.keys, potions=args.potions,
        powers=tuple(int(_TEMPORARY_POWERS[name]) for name in args.power),
        load_state_path=args.load_state, scenario_path=args.scenario,
        rng_seed=rng_seed, maze_number=args.maze,
        benchmark_frames=args.benchmark, stress_seconds=args.stresstest,
        workload_name=args.workload)


def main(argv: list[str] | None = None) -> None:
    """Run the graphical CLI, translating Ctrl-C into a quiet shell exit."""
    try:
        _main(argv)
    except KeyboardInterrupt:
        print("\ngauntpy interrupted", file=sys.stderr)
        raise SystemExit(130) from None



if __name__ == "__main__":
    main()
