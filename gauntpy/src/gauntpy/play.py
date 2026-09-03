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

from .constants import Character, GameMode, MazeObjIds, PlayerStatus
from .coords import encode_hpos, encode_vpos_at_y, pack_slot, slot_to_pixels
from .mainloop import tick
from .rng import GameRandom
from .state import GameState
from .subsystems.camera import snap_camera
from .subsystems.players import player_join, update_player_sprite
from .subsystems.session import configured_start_health

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
    repo_roms = Path(__file__).resolve().parents[3] / "ROMs"
    if repo_roms.is_dir():
        os.environ["GEX_ROM_DIR"] = str(repo_roms)


def _sound_dir() -> Path:
    configured = os.environ.get("GAUNTPY_SOUND_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "sounds"


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
        from .subsystems.score import GAME_SETTINGS_REDUCE_TEXT

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


def _spawn_player(state: GameState, character: int) -> int:
    """Drop player 0 into the loaded maze at a PLAYERSTART and return its slot.

    Uses the real join path (``player_join`` -> ``player_start_inner`` +
    ``player_join_finalize``, I-08): the PLAYERSTART marker MOB, already placed
    by ``maze.load_level`` with the hero base picture, becomes the hero. Only
    the character and starting health are runner concerns. If the maze has no
    PLAYERSTART, a hero MOB is dropped in the centre as a fallback.
    """
    p = state.players[0]
    p.character = character
    p.health = configured_start_health(state)

    player_join(state, 0)                   # positioned spawn + finalize

    if not p.active:                        # no PLAYERSTART: centre fallback
        from .subsystems.display import init_player_mob_palette

        start = pack_slot(16, 16)
        px, py = slot_to_pixels(start)
        state.mobs.unlink_and_clear(start)
        state.mobs.create(
            start, tile=0, hpos=encode_hpos(px, palette=0x0C),
            vpos=encode_vpos_at_y(py),
            obj_type=MazeObjIds.PLAYERSTART, state=0,
        )
        init_player_mob_palette(state, 0, character)
        p.status = PlayerStatus.ALIVE_HERE
        p.mob_slot = start
        p.direction = 2
        state.level_players_active = 1
        state.player_in_maze[0] = 1
        state.player_tile_or_tport_dest[0] = start

    update_player_sprite(state, 0)
    snap_camera(state)                      # frame the hero immediately
    return p.mob_slot


def build_state(
    level: int,
    character: int,
    *,
    maze_number: int | None = None,
    keys: int = 0,
    potions: int = 0,
    powers: tuple[int, ...] = (),
    rng_seed: int = 0,
) -> GameState:
    """Load ``level`` and spawn a hero directly (the mid-level drop).

    ``level`` owns level-gated behavior.  ``maze_number`` optionally pins the
    stored maze record; without it, levels 1-5 use mazes 0-4 and level 6+
    advances the cabinet rotation from its current resume position.
    """
    from . import maze

    from .subsystems.eeprom import GAME_DEFAULT_SETTINGS
    from .subsystems.display import init_alpha_color_ram

    state = GameState(
        game_mode=GameMode.NORMAL,
        game_settings=GAME_DEFAULT_SETTINGS,
        rng=GameRandom(rng_seed),
    )
    init_alpha_color_ram(state)
    if maze_number is None and level > 5:
        from .subsystems.exits import compute_next_level

        state.levelnum_current = 5
        state.mazenum_current = 4
        while state.levelnum_current < level:
            compute_next_level(state, int(MazeObjIds.EXIT))
            state.levelnum_current = state.level_next
            state.mazenum_current = state.maze_next
        maze_number = state.mazenum_current
    maze.load_level(
        state, level, maze_number=maze_number,
    )                                       # places objects with their pictures
    _spawn_player(state, character)
    from .subsystems.exits import update_monster_spawn_bonus_from_score_per_coin

    update_monster_spawn_bonus_from_score_per_coin(state)
    maze.maze_addrandompickups(state, True)
    from .subsystems.players import (
        initialize_player_temporary_power,
        setup_infopanel,
    )
    player = state.players[0]
    player.keysnum = keys
    player.potionsnum = potions
    for power in powers:
        initialize_player_temporary_power(state, 0, power)
    setup_infopanel(state, -1)
    return state


_STRESS_PHASES = (
    ("TITLE attract", int(GameMode.TITLE), None),
    ("DEMO gameplay", int(GameMode.DEMO), None),
    ("level 12 dragon maze", None, (12, 11)),
    ("level 16 moving/fake exits", None, (16, 15)),
    ("SCORES over maze 103", int(GameMode.SCORES), None),
    ("LEGEND over maze 103", int(GameMode.LEGEND), None),
)


def _build_stress_state(phase_index: int, rng_seed: int) -> GameState:
    """Construct one ROM-backed workload through its normal setup routine."""
    name, attract_mode, level_maze = _STRESS_PHASES[phase_index]
    if attract_mode is not None:
        from .subsystems.attract import start_attract_screen
        from .subsystems.eeprom import GAME_DEFAULT_SETTINGS

        state = GameState(
            game_settings=GAME_DEFAULT_SETTINGS,
            rng=GameRandom(rng_seed),
            eeprom_persistence_enabled=False,
        )
        start_attract_screen(state, attract_mode)
    else:
        level, maze_number = level_maze
        state = build_state(
            level, int(Character.ELF), maze_number=maze_number, rng_seed=rng_seed,
        )
        state.eeprom_persistence_enabled = False
    print(f"gauntpy stress phase: {name}")
    return state


def run(level: int = 1, character: int = Character.ELF, scale: int = 4,
        from_attract: bool = False,
        reduce_text: bool = False,
        sound_enabled: bool = False,
        uncapped: bool = False,
        keys: int = 0, potions: int = 0,
        powers: tuple[int, ...] = (),
        load_state_path: str | Path | None = None,
        scenario_path: str | Path | None = None,
        rng_seed: int = 0, maze_number: int | None = None,
        benchmark_frames: int | None = None,
        stress_seconds: float | None = None) -> None:
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

    if stress_seconds is not None:
        state = _build_stress_state(0, rng_seed)
    elif load_state_path is not None:
        from .render.state_dump import StateDumpError, load_game_state
        try:
            state = load_game_state(load_state_path)
        except StateDumpError as exc:
            raise SystemExit(f"could not load saved state: {exc}") from exc
    elif scenario_path is not None:
        from .custom_scenario import (
            SyntheticScenarioError,
            build_synthetic_state,
            load_synthetic_scenario,
        )
        try:
            state = build_synthetic_state(load_synthetic_scenario(scenario_path))
        except SyntheticScenarioError as exc:
            raise SystemExit(f"could not load synthetic scenario: {exc}") from exc
    elif from_attract:
        from .subsystems.boot import one_time_init
        state = GameState(rng=GameRandom(rng_seed))
        one_time_init(state)                # boots into TITLE attract
    else:
        from .maze import MazeError
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

    if benchmark_frames is not None:
        state.eeprom_persistence_enabled = False

    try:
        from .render.host import HostShell, PygameUnavailable
    except Exception as exc:  # pragma: no cover - import guard
        raise SystemExit(f"could not import the host shell: {exc}")

    try:
        host = HostShell(
            scale=scale,
            title="gauntpy",
            sound_dir=_enabled_sound_dir(
                sound_enabled
                and not uncapped
                and benchmark_frames is None
                and stress_seconds is None
            ),
            uncapped=uncapped or benchmark_frames is not None or stress_seconds is not None,
        )
    except PygameUnavailable as exc:
        raise SystemExit(
            f"{exc}\n\nRun it with the display extra, e.g.:\n"
            "    uv run --all-extras gauntpy-play"
        )
    if load_state_path is not None:
        host.skip_existing_audio(state)

    _apply_operator_overrides(state, reduce_text=reduce_text)

    # mainloop.g2mainloop's body: pump input, run a frame, present. The camera
    # (main_scroll_playfield) runs inside tick() and the compositor converts its
    # scroll to the viewport (I-23), so no runner-side camera fix-up is needed.
    benchmark = None
    warmup_remaining = 0
    if benchmark_frames is not None:
        from .performance import BenchmarkRecorder

        benchmark = BenchmarkRecorder()
        warmup_remaining = min(30, benchmark_frames)

    stress_started = perf_counter() if stress_seconds is not None else None
    stress_phase = 0
    stress_phase_seconds = (
        min(2.0, stress_seconds / len(_STRESS_PHASES))
        if stress_seconds is not None else None
    )
    next_stress_phase_at = stress_phase_seconds
    stress_frames = 0
    try:
        while True:
            loop_started = perf_counter()
            if stress_started is not None:
                elapsed = loop_started - stress_started
                if elapsed >= stress_seconds:
                    print(
                        f"gauntpy stress test complete: {stress_frames} frames "
                        f"in {elapsed:.3f} seconds"
                    )
                    break
                if elapsed >= next_stress_phase_at:
                    stress_phase = (stress_phase + 1) % len(_STRESS_PHASES)
                    next_stress_phase_at += stress_phase_seconds
                    state = _build_stress_state(stress_phase, rng_seed)

            input_started = perf_counter()
            host.wait_for_vblank(state)     # pump events + sample keyboard + coins
            input_finished = perf_counter()
            frame_updated = not host.paused
            if not host.paused:
                from .custom_scenario import apply_synthetic_events

                update_started = perf_counter()
                apply_synthetic_events(state)
                tick(
                    state,
                    treasure_timer_paused=host.treasure_timer_paused,
                )                           # one full 60 Hz game frame
                update_finished = perf_counter()
            else:
                update_started = update_finished = perf_counter()
            present_started = perf_counter()
            host.present(state)             # composite + flip
            loop_finished = perf_counter()
            stress_frames += stress_started is not None

            if benchmark is not None:
                if not frame_updated:
                    continue
                if warmup_remaining:
                    warmup_remaining -= 1
                    continue
                benchmark.add(
                    host_input_ms=(input_finished - input_started) * 1000.0,
                    game_update_ms=(update_finished - update_started) * 1000.0,
                    game_raster_ms=host.last_render_time_ms,
                    presentation_ms=(loop_finished - present_started) * 1000.0,
                    complete_loop_ms=(loop_finished - loop_started) * 1000.0,
                )
                if benchmark.frames >= benchmark_frames:
                    from .performance import format_benchmark_report

                    print(format_benchmark_report(benchmark, scale=scale))
                    break
    except SystemExit:
        pass
    finally:
        host.close()


def main(argv: list[str] | None = None) -> None:
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
    parser.add_argument("--scale", type=_positive_scale, default=4,
                        help="window pixel scale (default: 4)")
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
        help="benchmark host input, game update, raster, presentation, and the "
             "complete uncapped loop (default: 600 measured frames)",
    )
    modes.add_argument(
        "--stresstest", type=_positive_seconds, metavar="SECONDS",
        help="run an uncapped timed workload cycling ROM-backed gameplay and "
             "attract screens",
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
    run(level=args.level or 1,
        character=_CHARACTERS[args.character or "elf"], scale=args.scale,
        from_attract=args.attract,
        reduce_text=args.reduce_text,
        sound_enabled=args.sound and not args.uncapped,
        uncapped=args.uncapped,
        keys=args.keys, potions=args.potions,
        powers=tuple(int(_TEMPORARY_POWERS[name]) for name in args.power),
        load_state_path=args.load_state, scenario_path=args.scenario,
        rng_seed=rng_seed, maze_number=args.maze,
        benchmark_frames=args.benchmark, stress_seconds=args.stresstest)



if __name__ == "__main__":
    main()
