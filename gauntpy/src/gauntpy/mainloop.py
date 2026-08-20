"""The main loop -- ``g2mainloop`` (0x42A66).

One trip through this loop advances every system in the game by exactly one
frame, sixty times a second. The body is a straight line of 28 calls in a fixed
order, plus ``one_time_init`` before the first frame.

``game_frame`` below is that straight line, written as a straight line. The
order is load-bearing -- money and controls are read before anything can be
skipped, the world simulates, presentation reports on the result, and
persistence and sound flush last -- so it is expressed as ordinary sequential
calls rather than a table something walks. ROM addresses are comments, for
cross-referencing the disassembly.

``tests/test_mainloop.py`` parses this module and checks the call order against
``doc/generated/main_loop_contracts.csv``, so the sequence cannot drift from the
ROM's without a test failing.

Reference: ``doc/03_game_rom_structure.md`` §2.1-2.5; ``book/06_main_loop.md``.
"""

from __future__ import annotations

from .constants import FRAME_OVERFLOW_SET
from .state import GameState
from .subsystems.attract import main_attract, main_logo_updcolors
from .subsystems.boot import one_time_init
from .subsystems.camera import main_scroll_playfield
from .subsystems.dragon import main_handle_dragon
from .subsystems.eeprom import eeprom_periodic_write
from .subsystems.exits import main_exit_move, main_treasure_timer
from .subsystems.input import input_debounce
from .subsystems.maze_objects import (
    main_cycle_tport_and_ffield,
    main_open_doors,
    main_walls_cyclic_move,
    main_walls_random_move,
)
from .subsystems.monsters import main_move_monsters
from .subsystems.players import (
    main_handle_death,
    main_health_countdown,
    main_move_players,
    player_hurt_palette_vblank,
)
from .subsystems.potions import main_handle_potions
from .subsystems.score import (
    main_msgbox_countdown,
    main_score_display,
    main_score_update,
)
from .subsystems.session import (
    character_select_input_update,
    coincheck,
    main_start_game,
)
from .subsystems.shots import main_handle_shots
from .subsystems.sound import main_update_sound, sound_response
from .subsystems.thief import main_start_thief, main_thief_anim


def game_frame(state: GameState) -> None:
    """Advance the entire world by one frame -- the body of ``g2mainloop``."""

    # Three services that run no matter what: money and controls are sampled
    # before anything can be skipped.
    main_logo_updcolors(state)              # 0x4DCBA
    input_debounce(state)                   # 0x40644
    coincheck(state)                        # 0x42B6A

    # The dialog gate. One word in RAM freezes the entire gameplay band as a
    # block: monsters halt, shots hang in the air, health stops draining. Not a
    # slow-down -- the code that would advance any of them simply does not run.
    if state.dialog_timer == 0:
        main_cycle_tport_and_ffield(state)  # 0x40528
        main_handle_potions(state)          # 0x46FEA
        main_open_doors(state)              # 0x45C00
        main_handle_shots(state)            # 0x474F6
        main_move_players(state)            # 0x4A53A
        main_scroll_playfield(state)        # 0x46CAA
        main_move_monsters(state)           # 0x49034
        main_handle_dragon(state)           # 0x54454
        main_thief_anim(state)              # 0x4E8DC
        main_start_thief(state)             # 0x4DEB8
        main_health_countdown(state)        # 0x466F6
        main_treasure_timer(state)          # 0x4D29E
        main_handle_death(state)            # 0x4664C
        main_exit_move(state)               # 0x5287C
        main_walls_cyclic_move(state)       # 0x5E62A
        main_walls_random_move(state)       # 0x5E41A

    # Presentation and housekeeping, which also always run. The message box
    # counts itself down, coins are still accepted, and sound still drains,
    # even while the world above is frozen.
    main_msgbox_countdown(state)            # 0x4CCBC
    character_select_input_update(state)    # 0x42DF4
    main_start_game(state)                  # 0x4800C
    main_score_update(state)                # 0x4715E
    main_score_display(state)               # 0x457C0
    main_attract(state)                     # 0x44562
    eeprom_periodic_write(state)            # 0x431EE
    sound_response(state)                   # 0x42D0A
    main_update_sound(state)                # 0x4AE20


def check_frame_overflow(state: GameState) -> None:
    """The loop's most self-aware moment.

    If the VBLANK flag is already set again, the display finished another field
    while we were still working: the frame ran long. Set ``frame_overflow`` to
    8. Otherwise halve it, so the signal decays to zero after a few good frames.

    This is more than a diagnostic. While it is nonzero the generator spawn
    probability is forced to zero, so an overloaded machine stops *adding* to
    the crowd instead of stuttering its display. It does not bound how many
    monsters are processed -- the chain walk still visits every one.
    """
    if state.vblank_flag:
        state.frame_overflow = FRAME_OVERFLOW_SET
    else:
        state.frame_overflow >>= 1


def tick(state: GameState) -> None:
    """Consume one VBLANK and run one frame.

    Deliberately not tied to a clock: the host decides whether this happens on
    a 60 Hz timer, as fast as possible in a headless test, or one keypress at a
    time in a debugger. Determinism lives here -- same state, same inputs, same
    RNG seed produces the same frame, always.
    """
    state.frame_counter = (state.frame_counter + 1) & 0xFFFF
    state.vblank_flag = 0
    player_hurt_palette_vblank(state)

    game_frame(state)

    check_frame_overflow(state)


def g2mainloop(state: GameState, host) -> None:  # noqa: ANN001
    """Run forever, locked to the beam. Never returns; the original never does.

    The loop does not free-run. It spins until the VBLANK interrupt raises the
    semaphore, consumes it, performs one full update, and goes back to waiting.
    Every quantity in the game that involves time is therefore denominated in
    frames.

    ``host`` supplies ``wait_for_vblank()`` and ``present(state)``. Most callers
    want ``tick()`` directly instead of this.
    """
    one_time_init(state)

    while True:
        host.wait_for_vblank(state)
        tick(state)
        host.present(state)
