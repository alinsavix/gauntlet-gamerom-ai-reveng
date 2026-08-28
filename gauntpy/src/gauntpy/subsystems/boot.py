"""Boot and one-time initialization -- WP-20.

Reference: ``doc/03_game_rom_structure.md`` §5, §2.2; ``book/05_boot_and_os.md``.

``one_time_init`` runs exactly once, before the first VBLANK wait, from
``g2mainloop``. It is not part of the per-frame band, so it is not tracked in
``test_mainloop``'s implemented-calls roster.

Scope note. The ROM's ``one_time_init`` also drives display setup, the DIP/EEPROM
reads through OS services, and the "restore factory defaults" request in settings
bit 12 (0x432D8-0x432FA). Alpha VRAM/color RAM are now modeled; unrelated
hardware and OS-service concerns remain host boundaries. Everything the simulation can observe is
done: sound reset (0x42DC8), RAM/timer clearing, the persisted configuration
(0x42F86), the high-score banks (0x49BD0), the default character assignment
{0,1,2,3} (0x4332C-0x43342), and the hand-off into TITLE attract (0x43350).
"""

from __future__ import annotations

from ..constants import Character, GameMode
from ..state import NUM_PLAYERS, GameState
from .attract import start_attract_screen
from .eeprom import eeprom_load_settings
from .display import init_alpha_color_ram
from .score import highscore_table_init

# Sound-board reset holdoff, loaded by sound_system_reset (0xB4 = 180 frames,
# §11.3).
_SOUND_RESET_HOLDOFF = 0xB4


def one_time_init(state: GameState) -> None:
    """0x4327A -- full game initialization before the first frame (§5).

    Order follows the ROM: reset the sound system, clear game state, load the
    persisted EEPROM configuration (§5 step 6, 0x42F86), seed the high-score
    banks from the factory lists for any bank the EEPROM did not supply
    (0x43306), initialise RAM variables and default characters, then hand off to
    the TITLE attract screen.
    """
    _sound_system_reset(state)
    _clear_game_state(state)
    init_alpha_color_ram(state)             # init_display 0x434C2-0x434EC
    eeprom_load_settings(state)          # 0x43300 -- config load (WP-19)
    highscore_table_init(state)          # 0x43306 -- factory ladders (WP-14)
    _init_ram_variables(state)
    _start_attract_title(state)


def _sound_system_reset(state: GameState) -> None:
    """Flush the sound ring and arm the recovery holdoff (§5 step 1, §11.3)."""
    state.soundqueue.clear()
    state.speech_counter = _SOUND_RESET_HOLDOFF
    state.sound_idle_timer = 0xF0
    state.sound_cpu_retry_count = 0


def _clear_game_state(state: GameState) -> None:
    """Zero the frame/overflow bookkeeping (§5 step 2)."""
    state.frame_counter = 0
    state.frame_overflow = 0
    state.vblank_semaphore = 0
    state.dialog_timer = 0


def _init_ram_variables(state: GameState) -> None:
    """Timers, cleared state, and default character types {0,1,2,3} (§5 step 7)."""
    for i in range(NUM_PLAYERS):
        p = state.players[i]
        p.character = Character(i)      # default WARRIOR/VALKYRIE/WIZARD/ELF
        p.status = 0                    # PlayerStatus.REMOVED
        state.pending_character[i] = int(Character(i))

    state.level_players_active = 0
    state.monster_iter_ptr = 0
    state.monster_slowmo_timer = 0
    state.title_intro_state = 0
    state.title_logo_full_program = False
    # Secret-room pacing counters both start at 20 (§10.6, game init 0x43312).
    state.secret_possible_counter = 20
    state.secret_possible_start = 20
    # level_next_potion (0x904B7E) is cleared at 0x43320; level_next_treasure
    # (0x904B80) is not touched here -- it is armed the first time the cabinet
    # reaches level 6 (maze_new_level_setup 0x438E4, ported in exits.py).
    state.level_next_potion = 0


def _start_attract_title(state: GameState) -> None:
    """Hand off to TITLE attract (§5 step 8: start_attract_screen(-2)).

    Calls WP-17's real ``start_attract_screen``; ``main_attract`` takes over
    from the first frame.
    """
    start_attract_screen(state, int(GameMode.TITLE))
