"""Game state -- the reimplementation's stand-in for working RAM.

Field names match the documented RAM variable names so that any claim in
``doc/05_data_reference.md`` can be checked against the code by grep. The
original address is given in a comment on each field; it is documentation,
not an address we honour.

Types are Python ints, but widths matter: the original stores health and score
as 32-bit longwords and nearly everything else as 16-bit words. Subsystems must
mask on write where the original's wraparound is observable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import Character, GameMode, PlayerStatus
from .mob import MobTable
from .rng import GameRandom

NUM_PLAYERS = 4


@dataclass
class Player:
    """Per-player state, gathered from the parallel arrays the original used."""

    index: int
    status: int = PlayerStatus.REMOVED          # 0x9049A0, byte
    character: int = Character.WARRIOR          # 0x9048E8
    health: int = 0                             # 0x904980, longword, stride 4
    score: int = 0                              # 0x904990, longword
    powers: int = 0                             # 0x9048E0, word
    keysnum: int = 0                            # 0x90405A, byte
    potionsnum: int = 0                         # 0x904055, byte
    bonusmult: int = 1                          # player_bonusmult
    mob_slot: int = 0                           # active_mob_ids
    direction: int = 0                          # facing, 0-7
    anim_counter: int = 0
    state_timer: int = 0xFFFF                   # 0x904A26, low-health cadence
    stundelay: int = 0                          # player_stundelay
    hurt_cooldown: int = 0
    acid_timer: int = 0
    supershot: int = 0                          # 0x905F68
    death_damage_counter: int = 0               # 0x904B3A
    damage_sample_timer: int = 60               # 60-frame window, §4.3
    pending_damage: int = 0
    coin_count: int = 0

    @property
    def active(self) -> bool:
        """On the level right now and taking input."""
        return bool(self.status & PlayerStatus.ALIVE_HERE)


@dataclass
class GameState:
    """Everything the main loop's 28 per-frame calls read and write.

    **Adding fields: append under your own work package's heading below.**

    This is the one file every work package may touch, so it is partitioned by
    owner. Appending under your own heading means two agents working in
    parallel anchor on different text and cannot clobber each other. Do not
    reorder the blocks, and do not add fields to another package's block or to
    the shared core.

    Every field needs its documented name and its RAM address in a comment. If
    the docs give no name for it, say so in the comment.
    """

    # =========================================================================
    # Shared core -- owned by no work package. Do not append here.
    # =========================================================================
    mobs: MobTable = field(default_factory=MobTable)
    rng: GameRandom = field(default_factory=GameRandom)
    players: list[Player] = field(
        default_factory=lambda: [Player(index=i) for i in range(NUM_PLAYERS)]
    )

    vblank_flag: int = 0             # 0x904002, the VBLANK semaphore
    frame_counter: int = 0           # 0x904006
    frame_overflow: int = 0          # 0x904916, generator spawn throttle
    game_mode: int = GameMode.TITLE  # 0x904918
    dialog_timer: int = 0            # 0x904A9E, gates the 16-call world band

    # =========================================================================
    # WP-3 · maze and level
    # =========================================================================
    mazenum_current: int = 0        # 0x904000
    levelnum_current: int = 0       # 0x904004
    level_flags: int = 0            # LFLAG1/2 -- see gex.constants
    level_flags_2: int = 0
    level_flags_3: int = 0
    level_flags_4: int = 0
    level_players_active: int = 0
    maze: object | None = None      # gex.mazedecode.Maze once WP-3 lands
    wrap_h: bool = False            # 0x90491F bit 5, from LFLAG4_WRAP_H
    wrap_v: bool = False            # 0x90491F bit 4, from LFLAG4_WRAP_V

    # =========================================================================
    # WP-4 · input
    # =========================================================================
    # Switches are active low, so "nothing pressed" is all bits set. Defaulting
    # these to 0 would mean every button held on frame one.
    player_input_raw: list[int] = field(default_factory=lambda: [0xFFFF] * NUM_PLAYERS)  # 0x904920
    debounce_shift_magic: list[int] = field(default_factory=lambda: [0xFFFF] * NUM_PLAYERS)  # 0x905F58
    debounce_shift_fire: list[int] = field(default_factory=lambda: [0xFFFF] * NUM_PLAYERS)   # 0x905F60

    # =========================================================================
    # WP-5 · player movement and collision
    # =========================================================================
    # (per-player movement state that does not belong on Player goes here)

    # =========================================================================
    # WP-6 · player lifecycle, health, powers, tile interaction
    # =========================================================================
    player_it: int = 0xFFFF         # 0x9049DC, 0xFFFF = nobody is IT

    # =========================================================================
    # WP-7 · shots and hit resolution
    # =========================================================================
    death_hits: int = 0             # 0x904A5C, global Death hit counter

    # =========================================================================
    # WP-8 · monsters and generators
    # =========================================================================
    monster_slowmo_timer: int = 0   # 0x9048B2, global monster slow motion
    monster_iter_ptr: int = 0       # 0x904A60, rotating chain entry point
    spawn_probability_bonus: int = 0  # 0x90405F, signed byte

    # =========================================================================
    # WP-9 · dragon
    # =========================================================================

    # =========================================================================
    # WP-10 · thief and mugger
    # =========================================================================
    thief_mode: int = 0             # 0x904BA0
    thief_victim: int = -1
    thief_enter_time: int = -1      # frames until entry, -1 = not scheduled

    # =========================================================================
    # WP-11 · living maze (walls, doors, transporters, forcefields)
    # =========================================================================

    # =========================================================================
    # WP-12 · potions and magic
    # =========================================================================

    # =========================================================================
    # WP-13 · camera
    # =========================================================================
    scroll_x: int = 0
    scroll_y: int = 0

    # =========================================================================
    # WP-14 · scoring, HUD, dialogs
    # =========================================================================

    # =========================================================================
    # WP-15 · exits, treasure rooms, secret rooms
    # =========================================================================

    # =========================================================================
    # WP-16 · coins, credits, session lifecycle
    # =========================================================================
    credits: int = 0

    # =========================================================================
    # WP-17 · attract mode and demo playback
    # =========================================================================

    # =========================================================================
    # WP-18 · sound (stubbed)
    # =========================================================================
    # Outgoing command ring: 8 physical slots at 0x90404B (write head 0x904053,
    # read head 0x904054), one slot reserved to distinguish full from empty, so
    # usable capacity is 7 -- doc/04_game_subsystems.md §11.1-11.2.
    sound_queue: list[int] = field(default_factory=list)
    # Permanent history of every command main_update_sound has drained. Never
    # cleared automatically -- this is the WP-18 "test oracle": other packages
    # (and their tests) assert against it, e.g. "this event played sound 0x37".
    sound_log: list[int] = field(default_factory=list)
    # 0x9049EE, sound-board recovery holdoff. Named ``speech_counter`` in the
    # loader symbols, but corrected in §11.3: the only writer is
    # sound_system_reset, which loads 0xB4 (180 frames). Nonzero blocks both
    # sound_play's immediate-send attempt and main_update_sound's drain.
    sound_holdoff: int = 0
    # 0x9049F0, low 3 bits are the sound board's own fault report, delivered as
    # the reply to the diagnostic status query (command 0x07) -- §11.3.
    sound_queue_state: int = 0
    # 0x9049F2, idle timer counting down to the next status query (command
    # 0x07); reloads to 0xF0 (240 frames) on a successful send -- §11.3. Initial
    # value is not independently documented; matches the post-reset reload.
    sound_idle_timer: int = 0xF0
    # 0x9049F4, consecutive failed-status-send retry count; a full reset fires
    # above 0xB4 (180) -- §11.3.
    sound_retry_count: int = 0
    # No real sound board exists in this simulation (WP-18 is stubbed at the
    # queue boundary), so no reply byte ever arrives from OS 0x178 on its own.
    # Tests can push bytes here (FIFO) to exercise sound_response's
    # reply-handling branches -- §11.3.
    sound_incoming: list[int] = field(default_factory=list)

    # =========================================================================
    # WP-19 · EEPROM and configuration
    # =========================================================================
    game_settings: int = 0            # 0x904A24, EEPROM options word; bit layout in subsystems/eeprom.py
    eeprom_write_timer: int = 0x8CA0  # 0x904012 target; §20 periodic-write countdown, 36,000 frames (~10 min @ 60Hz)
    eeprom_settings_cache: int = 0    # 0x904B94, "last written" shadow of game_settings; §20 change detection
    eeprom_save_path: str = "gauntpy_eeprom.json"  # no ROM address -- local persistence target, see eeprom.py

    # =========================================================================
    # WP-20 · boot and orchestration
    # =========================================================================

    # --- convenience ----------------------------------------------------------

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self.players if p.active]

    @property
    def players_active_count(self) -> int:
        return len(self.active_players)

    def getrandom(self, bound: int) -> int:
        """Shorthand for the game's ``getrandom(bound)``."""
        return self.rng.getrandom(bound)
