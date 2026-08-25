"""A minimum playable runner: walk a hero around a real Gauntlet II maze.

    uv run gauntpy-play            # level 1, Elf
    uv run gauntpy-play --level 2 --character elf --scale 3

By default it loads a maze and drops a player directly into gameplay; ``--attract``
boots through the complete cabinet front end. Both paths drive the real
``game_frame`` at 60 Hz with a pygame window and keyboard input.

Requires the ROM-graphics and display extras::

    uv run --extra rom --extra display gauntpy-play
    # or: uv run --all-extras gauntpy-play
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .constants import Character, GameMode, MazeObjIds, PlayerStatus
from .coords import encode_hpos, encode_vpos_at_y, pack_slot, slot_to_pixels
from .mainloop import tick
from .state import GameState
from .subsystems.camera import snap_camera
from .subsystems.players import player_join, update_player_sprite
from .subsystems.session import configured_start_health

#: Highest maze number the Slapstic image holds (gex's own bound, restated so
#: ``--level`` can be clamped without importing gex at module import time --
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


def _ensure_rom_dir() -> None:
    """Point gex at the repo's ROMs/ directory unless the user set GEX_ROM_DIR."""
    if os.environ.get("GEX_ROM_DIR"):
        return
    repo_roms = Path(__file__).resolve().parents[3] / "ROMs"
    if repo_roms.is_dir():
        os.environ["GEX_ROM_DIR"] = str(repo_roms)


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
        state.player_tile_pos[0] = start

    update_player_sprite(state, 0)
    snap_camera(state)                      # frame the hero immediately
    return p.mob_slot


def build_state(
    level: int,
    character: int,
    *,
    keys: int = 0,
    potions: int = 0,
    powers: tuple[int, ...] = (),
) -> GameState:
    """Load ``level`` and spawn a hero directly (the mid-level drop)."""
    from . import maze

    from .subsystems.eeprom import GAME_DEFAULT_SETTINGS
    from .subsystems.display import init_alpha_color_ram

    state = GameState(
        game_mode=GameMode.NORMAL,
        game_settings=GAME_DEFAULT_SETTINGS,
    )
    init_alpha_color_ram(state)
    if level > 5:
        # Past the opening act there is no fixed level -> maze rule (doc/06
        # §3.2), so ``load_level`` reads ``mazenum_current``. Seed it with the
        # cabinet's own opening rotation position rather than leaving it at
        # maze 0, which would silently replay level 1's maze.
        state.mazenum_current = min(level - 1, MAX_MAZE_NUM)
    maze.load_level(state, level)           # places objects with their pictures
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


def run(level: int = 1, character: int = Character.ELF, scale: int = 4,
        from_attract: bool = False,
        suppress_first_encounter_messages: bool = False,
        keys: int = 0, potions: int = 0,
        powers: tuple[int, ...] = ()) -> None:
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

    try:
        from .render.host import HostShell, PygameUnavailable
    except Exception as exc:  # pragma: no cover - import guard
        raise SystemExit(f"could not import the host shell: {exc}")

    try:
        host = HostShell(scale=scale, title="gauntpy")
    except PygameUnavailable as exc:
        raise SystemExit(
            f"{exc}\n\nRun it with the display extra, e.g.:\n"
            "    uv run --all-extras gauntpy-play"
        )

    if from_attract:
        from .subsystems.boot import one_time_init
        state = GameState()
        one_time_init(state)                # boots into TITLE attract
    else:
        from .maze import MazeError
        try:
            state = build_state(
                level, character, keys=keys, potions=potions, powers=powers,
            )
        except MazeError as exc:
            host.close()
            raise SystemExit(
                f"could not load level {level}: {exc}\n"
                "Check that GEX_ROM_DIR points at a complete Gauntlet II ROM "
                "dump (file list in python-gex/README.md)."
            )

    state.suppress_first_encounter_messages = suppress_first_encounter_messages

    # mainloop.g2mainloop's body: pump input, run a frame, present. The camera
    # (main_scroll_playfield) runs inside tick() and the compositor converts its
    # scroll to the viewport (I-23), so no runner-side camera fix-up is needed.
    try:
        while True:
            host.wait_for_vblank(state)     # pump events + sample keyboard + coins
            if not host.paused:
                tick(state)                 # one full 60 Hz game frame
            host.present(state)             # composite + flip
    except SystemExit:
        pass
    finally:
        host.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="gauntpy-play", description="Walk a hero around a Gauntlet II maze."
    )
    parser.add_argument(
        "--level", type=_positive_level, default=1,
        help="level number; 1-5 are the fixed opening mazes 0-4, higher levels "
             "start at the matching rotation maze and advance from there",
    )
    parser.add_argument(
        "--character", choices=sorted(_CHARACTERS), default="elf",
        help="hero class (default: elf)",
    )
    parser.add_argument("--scale", type=_positive_scale, default=4,
                        help="window pixel scale (default: 4)")
    parser.add_argument(
        "--attract", action="store_true",
        help="boot into attract and start via the real front end "
             "(press 5 to insert a coin, arrows to pick a class, Enter to start)",
    )
    parser.add_argument(
        "--no-first-encounter-messages", action="store_true",
        help="suppress first-encounter pop-up boxes without changing gameplay",
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
    if args.attract and (args.keys or args.potions or args.power):
        parser.error("--keys, --potions, and --power require direct play (no --attract)")

    _ensure_rom_dir()
    if not os.environ.get("GEX_ROM_DIR"):
        print(
            "No ROMs found. Set GEX_ROM_DIR to your Gauntlet II ROM directory, "
            "or put the files in ./ROMs.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    run(level=args.level, character=_CHARACTERS[args.character], scale=args.scale,
        from_attract=args.attract,
        suppress_first_encounter_messages=args.no_first_encounter_messages,
        keys=args.keys, potions=args.potions,
        powers=tuple(int(_TEMPORARY_POWERS[name]) for name in args.power))



if __name__ == "__main__":
    main()
