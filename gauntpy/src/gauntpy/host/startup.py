"""Explicit cabinet power-on and direct-play construction.

Synthetic fixtures have their own game-writer setup in ``custom_scenario``.
Resume reconstructs a snapshot in ``state_dump`` and never enters either
initializer here.
"""

from __future__ import annotations

from ..constants import GameMode, MazeObjIds, PlayerStatus
from ..coords import encode_hpos, encode_vpos_at_y, pack_slot, slot_to_pixels
from ..rng import GameRandom
from ..state import GameState
from ..subsystems.camera import snap_camera
from ..subsystems.player_animation import update_player_sprite
from ..subsystems.players import player_join
from ..subsystems.session import configured_start_health
from .eeprom import PersistencePolicy, bind_eeprom_storage


def build_cold_boot_state(
    rng_seed: int = 0, *,
    persistence_policy: PersistencePolicy = PersistencePolicy.READ_WRITE,
) -> GameState:
    """Seed one power-on and let the cabinet boot routine enter TITLE attract."""
    from ..subsystems.boot import one_time_init

    state = GameState(rng=GameRandom(rng_seed))
    bind_eeprom_storage(state, policy=persistence_policy)
    one_time_init(state)
    return state


def spawn_player(state: GameState, character: int) -> int:
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
        from ..subsystems.display import init_player_mob_palette

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
    from .. import maze

    from ..subsystems.eeprom import GAME_DEFAULT_SETTINGS
    from ..subsystems.display import init_alpha_color_ram

    state = GameState(
        game_mode=GameMode.NORMAL,
        game_settings=GAME_DEFAULT_SETTINGS,
        rng=GameRandom(rng_seed),
    )
    init_alpha_color_ram(state)
    if maze_number is None and level > 5:
        from ..subsystems.exits import compute_next_level

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
    spawn_player(state, character)
    from ..subsystems.exits import update_monster_spawn_bonus_from_score_per_coin

    update_monster_spawn_bonus_from_score_per_coin(state)
    maze.maze_addrandompickups(state, True)
    from ..subsystems.players import (
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
