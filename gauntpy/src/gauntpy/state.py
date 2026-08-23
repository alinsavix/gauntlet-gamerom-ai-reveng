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
    mob_slot: int = 0                           # active_mob_ids: the live cell
    direction: int = 0                          # facing, 0-7
    anim_counter: int = 0
    state_timer: int = 0xFFFF                   # 0x904A26, low-health cadence
    stundelay: int = 0                          # player_stundelay
    hurt_cooldown: int = 0                       # 0x905F30, hurt-palette timer
    acid_timer: int = 0
    supershot: int = 0                          # 0x905F68
    death_damage_counter: int = 0               # 0x904B3A
    damage_sample_timer: int = 60               # 60-frame window, §4.3
    pending_damage: int = 0
    cumulative_damage: int = 0                  # saturation accumulator, §4.3
    coin_count: int = 0                         # 0x904B2A, player_coincount

    # --- death / high-score name entry (§10.3, 0x49D0E and 0x49DE6) ----------
    score_per_coin: int = 0                     # 0x904B1A, longword
    #: 0x904A4A. ``rank_high_score`` returns 0-9 to qualify; 10 (and anything
    #: else outside 0-9) means "did not rank", which is what skips initials
    #: entry at 0x49D50/0x49D60.
    highscore_rank: int = 10
    initials_cursor: int = 0                    # 0x904A3A byte 0
    #: 0x904A3B-0x904A3D, the three editable character codes ('A' by default).
    initials: list[int] = field(default_factory=lambda: [0x41, 0x41, 0x41])
    name_entry_velocity: int = 0                # 0x904A2E, signed word +-0xA0
    name_entry_repeat_delay: int = 0            # 0x904A36, byte
    #: Set by ``player_exit_sequence`` so the shared 0x08 status can tell the
    #: exit animation apart from this port's death animation (see PlayerStatus).
    exit_pending: int = 0

    @property
    def active(self) -> bool:
        """On the level right now and taking input."""
        return bool(self.status & PlayerStatus.ALIVE_HERE)


# =============================================================================
# WP-14 · info-panel record types.
#
# These live here, next to ``Player``, for the same reason ``Player`` does:
# ``GameState`` needs the type to declare a typed, default-constructed field,
# and anything defined in ``subsystems/`` would make ``state`` import a
# subsystem that already imports ``state``. They carry no behaviour -- WP-14's
# ``subsystems/score.py`` owns every write.
# =============================================================================


@dataclass
class PanelField:
    """One player's **latched** info-panel fields: what the last
    ``draw_player_score`` (0x45940) / ``draw_player_health`` (0x459A2) actually
    put on the alpha layer at VRAM 0x905000. It is a diagnostic shadow of
    ``alpha_ram`` (the renderer consumes VRAM directly), and confirms the ROM's
    one-player-per-four-frames redraw cadence.
    """

    score_drawn: bool = False       # has draw_player_score run for this player
    health_drawn: bool = False      # has draw_player_health run for this player
    score: int = 0                  # 0x904990[p] as drawn
    score_attr: int = 0             # player_text_palette_words[p] (ROM 0x57350)
    health: int = 0                 # 0x904980[p] as drawn
    health_attr: int = 0            # the same word, less the pulse/acid shift
    bonusmult: int = 1              # 0x90490E[p], drawn only when > 1


@dataclass
class InfoPanel:
    """The alpha-RAM info panel's shadow (VRAM 0x905000, columns 29-41) --
    ``setup_infopanel`` (0x452D0) rebuilds it, ``main_score_display`` (0x457C0)
    keeps it current one player at a time."""

    players: list[PanelField] = field(
        default_factory=lambda: [PanelField() for _ in range(NUM_PLAYERS)]
    )


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
        default_factory=lambda: [
            Player(index=i, character=Character(i))
            for i in range(NUM_PLAYERS)
        ]
    )

    vblank_flag: int = 0             # 0x904002, the VBLANK semaphore
    frame_counter: int = 0           # 0x904006
    frame_overflow: int = 0          # 0x904916, generator spawn throttle
    game_mode: int = GameMode.TITLE  # 0x904918
    dialog_timer: int = 0            # 0x904A9E, gates the 16-call world band
    # Host testing option: keep first-encounter flags/speech semantics but do
    # not create the alpha message box or stall the gameplay band.
    suppress_first_encounter_messages: bool = False

    # =========================================================================
    # WP-3 · maze and level
    # =========================================================================
    mazenum_current: int = 0        # 0x904000
    levelnum_current: int = 0       # 0x904004
    # The level-flags longword at 0x90491C (doc/04_game_subsystems.md §5.5),
    # stored as its 4 big-endian bytes rather than one 32-bit field because
    # the pre-existing wrap_h/wrap_v comments below already read
    # level_flags_4 as a standalone byte at 0x90491F. gex.constants'
    # LFLAG1_*/LFLAG2_*/LFLAG3_*/LFLAG4_* masks are longword-relative
    # (bits 24-31/16-23/8-15/0-7); only LFLAG4 tests directly against its
    # byte here without shifting -- see gauntpy.maze._split_flags/_join_flags
    # for the reassembly WP-3 needs internally.
    level_flags: int = 0            # 0x90491C, LFLAG1 byte
    level_flags_2: int = 0          # 0x90491D, LFLAG2 byte
    level_flags_3: int = 0          # 0x90491E, LFLAG3 byte
    level_flags_4: int = 0          # 0x90491F, LFLAG4 byte
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
    movement_type: int = 0            # 0x904BF2
    # 0x9048F0: active-low directions actually moved this frame; 0xF0 = still.
    player_walk_dirs: list[int] = field(
        default_factory=lambda: [0x00F0] * NUM_PLAYERS
    )

    # =========================================================================
    # WP-6 · player lifecycle, health, powers, tile interaction
    # =========================================================================
    player_it: int = 0xFFFF         # 0x9049DC, 0xFFFF = nobody is IT
    # Per-player looping-sound timer arrays (§21).
    # Negative = new contact (main_handle_death plays start sound and negates).
    # Positive = countdown; when reaches 0, stop sound plays.
    forcefield_hurt_timer: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )  # 0x904B4A[player*2]
    death_touch_timer: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )  # 0x904B42[player*2]
    # 0x9048C6 escape_timer: trap-wall conversion fires when this reaches
    # 0x5208 (21000) -- main_move_players 0x4AD06-0x4AD16 (§4.1 post-loop).
    escape_timer: int = 0           # counts up each frame during gameplay
    # 0x90490C ``idle_timer``: counts up once per frame inside main_move_players
    # (0x4ACE4) while the post-loop activity gate is set, and is compared there
    # against 0x4B0/0xA8C to fire open_timed_doors.  The sweep then stores
    # 0xFFFF (0x4AD02) -- negative, so the ``tst.w``/``blt`` at 0x4ACE0 stops
    # any further increment and the timed doors open once per level.
    idle_timer: int = 0
    # 0x904ACA, 1 B × 4 ``player_lowhealth_spoken``: one-shot latch for the
    # low-health voice warning.  player_lowhealth (0x487CA) returns immediately
    # when set, sets it after speaking; death/join setup and a food pickup that
    # lifts health back to 200 clear it (§4.3, 05_data_reference §4).
    player_lowhealth_spoken: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # 0x904ACE, 2 B × 4 ``player_respawn_speech_timer``: signed countdown.
    # player_lowhealth speaks only while this is negative and reloads it with
    # 0x708; main_health_countdown decrements it while it is >= 0 (0x467C2).
    player_respawn_speech_timer: list[int] = field(
        default_factory=lambda: [-1] * NUM_PLAYERS
    )
    # 0x904AC6, longword ``welcome_elapsed_frames``: frames elapsed in the
    # current start-game loop, incremented by main_start_game (0x48020).
    # speech_welcome (0x48754) uses 600 as both its gate and its reload.
    welcome_elapsed_frames: int = 0
    # 0x9049A4 ``player_facing_dir``, as reused by the status-0x08 branch of
    # main_move_players (0x4A672) for the death/exit animation frame, which
    # counts 7 -> 4 one step per four frames.  Kept separate from
    # ``Player.direction`` because that field carries the port's own facing
    # encoding (0 = right), not the ROM's (0 = up).
    player_death_anim_frame: list[int] = field(
        default_factory=lambda: [7] * NUM_PLAYERS
    )
    # 0x905F48 ``dizzy_timer``, 2 B x 4: the "you are dizzy" countdown a
    # poisoned food or potion arms with 0x4B0 frames (0x51C68/0x5166E).
    # Wholesome food and potions clear it (0x51BF8/0x51CDA) and
    # main_move_players runs it down (0x4A892-0x4A89E).
    player_dizzy_timer: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # 0x905F50 ``invis_timer``, 2 B x 4: countdown for the POWER_INVIS pickup
    # (loaded 0x4B0 at 0x517D4).  main_move_players decrements it and clears
    # PlayerPower.INVIS when it reaches zero (0x4A808-0x4A80E).
    player_invis_timer: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # 0x905F38 ``repulse_timer``, 2 B x 4: countdown for the POWER_REPULSE
    # pickup, loaded per character from the table at 0x5B72C at 0x5181A.  Its
    # expiry clears PlayerPower.REPULSE (0x4A820-0x4A826) -- bit 9, the bit
    # 0x4185C tests to make monsters flee -- so this is the *repulsiveness*
    # countdown.  05_data_reference.md calls it ``reflect_timer``; reflection is
    # bit 10 (type 0x38), read at 0x4B4B0, and has no timer at all.
    player_repulse_timer: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # 0x904BCE, 2 B × 4 ``player_tport_phase``: per-player transport phase.
    # Negative = not teleporting; 0..0x10 = an in-flight teleport.  WP-13's
    # ``player_in_maze`` is main_scroll_playfield's reading of the same ROM
    # word; the port keeps them apart because ``player_in_maze`` uses 1 = in
    # maze rather than the ROM's negative-means-in-maze polarity.
    player_tport_phase: list[int] = field(
        default_factory=lambda: [-1] * NUM_PLAYERS
    )
    # 0x904BE2, 2 B × 4 ``player_tport_type``: destination transporter slot of
    # the player's current teleport (0 = none in flight).
    player_tport_type: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # 0x904BEA, 2 B × 4 ``player_tport_route_state``: source transporter slot,
    # recorded by player_tport on entry (0x5023E).
    player_tport_route_state: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # Demo playback state (§4.1 section 2).  WP-17 populates demo_streams.
    demo_active_player: int = 0     # current player slot being driven by demo
    demo_streams: list[list[int]] = field(
        default_factory=lambda: [[] for _ in range(NUM_PLAYERS)]
    )  # per-player recorded [timer, joystick] byte pairs
    demo_stream_pos: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    demo_timers: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )

    # =========================================================================
    # WP-7 · shots and hit resolution
    # =========================================================================
    death_hits: int = 0             # 0x904A5C, global Death hit counter

    # Port-side whole-pixel projection of the ROM velocity tables/accumulators;
    # indices 1-12 correspond to the fixed projectile MOB slots.  Both are in
    # the hardware's own axes, so ``shot_dy`` is a *native* V delta: positive
    # walks the projectile up the screen (``coords``).
    shot_dx: list[int] = field(default_factory=lambda: [0] * 13)
    shot_dy: list[int] = field(default_factory=lambda: [0] * 13)
    # Port-side elapsed frames, parallel to the exact ROM countdown below.
    shot_lifetime: list[int] = field(default_factory=lambda: [0] * 13)
    # Movable wall hit accumulators: slot → cumulative hit value in units of
    # 0x400 per player-shot hit.  At 0x6400 (25 hits) the wall dissolves.
    # Stored here rather than in mob_state_link because state_link lower bits
    # are the depth-chain prev pointer and must not be corrupted.  §26.
    movable_wall_hits: dict = field(default_factory=dict)  # slot(int) → int
    # 0x904B02, ``shot_anim_lifetime_counter``: one word per projectile
    # channel 0-11.  main_handle_shots predecrements it on its eligible frames
    # and reloads from ``shot_counter_reload`` (0x578C2) when it goes negative;
    # for channels 8-11 the reload value doubles as the shot's lifetime and
    # zero triggers impact/removal.  Shot creation seeds it.
    shot_anim_lifetime_counter: list[int] = field(
        default_factory=lambda: [0] * 12
    )
    # 0x90492A, ``shot_timer_next``: eight words counting down to the next
    # demon/lobber shot.  main_handle_shots (0x47510) decrements them; WP-8's
    # monster_create_shot (0x490FE) is the ROM's writer.
    shot_timer_next: list[int] = field(default_factory=lambda: [0] * 8)
    # 0x9048BE, ``reflect_count``: reflections left on each player's live shot.
    # Armed to 4 while the channel is free (0x47BC2) and predecremented by
    # shot_reflect_calc (0x53CC4); a shot bounces only while it is non-zero.
    reflect_count: list[int] = field(default_factory=lambda: [4] * NUM_PLAYERS)
    # 0x9048A8, ``player_shot_last_wall_pos``: packed cell of each player
    # shot's most recent wall contact, used by shot_reflect_calc to pick the
    # bounce and by main_handle_shots (0x47ADE) to suppress a repeat.
    player_shot_last_wall_pos: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # 0x904028 / 0x904024 / 0x90402A / 0x904026: signed and folded-absolute
    # separations recorded by shot_collision_candidate_core (0x40A78) for the
    # candidate it accepted.  shot_onscreen_check (0x4AEA0) reads them back.
    shot_sep_h: int = 0
    shot_sep_h_abs: int = 0
    shot_sep_v: int = 0
    shot_sep_v_abs: int = 0
    # 0x9048C8 ``active_mob_ids`` entries 4-11: the MOB slot that fired each
    # monster/dragon shot channel, so a shot cannot hit its own shooter.
    # Entries 0-3 come from ``Player.mob_slot`` and are refreshed each frame.
    # -1 = unknown; main_handle_shots latches the spawn cell (identity is
    # location) the frame a channel goes live.  See the WP-8 follow-up note in
    # ``shots.py``: monster_create_shot should write this directly.
    shot_owner_mob: list[int] = field(default_factory=lambda: [-1] * 12)
    # Destructible-wall crumble stage, one entry per damaged wall slot.
    # wall_crumble (0x5303A) keeps the stage in the playfield tile itself: on a
    # shrub level (``wallpattern >= 6``) it is which of the three
    # ``wall_desc_destructible`` descriptors is stamped, elsewhere it is how far
    # the tile's palette nibble has been walked down from 7.  The port's terrain
    # raster is a cache built from ``maze``, so the stage lives here and the
    # renderer reads it back: shrub levels pick ``SHRUB_DESTRUCT_STAMPS[stage]``,
    # the rest draw the wall with palette ``7 - stage``.
    destructible_wall_stage: dict = field(default_factory=dict)  # slot → 0-2
    # 0x90486E ``secret_need_hint``: set when a secret wall is shot open, so
    # the next level start screen offers the hint.  WP-7 writes, WP-15 reads.
    secret_need_hint: int = 0
    # 0x9049AC ``player_fighting_dir``: per-player fighting direction
    # (1=up, 2=up-right, ..., 8=up-left).  resolve_shot_hit clears it when a
    # shot stuns its victim (0x4B0B0); WP-5/WP-6 otherwise own it.
    player_fighting_dir: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # 0x9049B4 ``player_shooting``: 0xFFFF while the four-frame firing action
    # is armed, zero otherwise.  ``main_handle_shots`` starts it and
    # ``main_move_players`` consumes its animation/cadence.
    player_shooting: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    # Port-side projection of main_move_players' frame-local movement result.
    # The ROM keeps this in a stack local only; retaining it lets the public
    # sprite updater select the correct walking-vs-idle action outside the core.
    player_walking: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )

    # =========================================================================
    # WP-8 · monsters and generators
    # =========================================================================
    monster_slowmo_timer: int = 0   # 0x9048B2, global monster slow motion
    # 0x904A60, ``monster_iter_ptr``: the MOB **slot** the chain walk stops at.
    # main_move_monsters recomputes it from the camera every frame (0x4909A):
    # together with the bucket head the walk starts from it brackets the
    # on-screen arc of the depth chain, so off-screen creatures are never even
    # visited.  It is not a rotating cursor, despite the name.
    monster_iter_ptr: int = 0
    spawn_probability_bonus: int = 0  # 0x90405F, signed byte
    # 0x904B7A ``monster_generation_retry_timer``: the attract/demo replacement
    # for the probability draw.  ``attract_demo_init`` (0x44A76) loads it with 4;
    # ``handle_generate`` counts it down once per generator turn and only forces
    # a spawn attempt once it goes negative, then clamps it back to zero (0x492E2
    # -0x492EC) so every later turn attempts one.
    monster_generation_retry_timer: int = 4
    # Monster culling rectangle (0x904A62/0x904A64): a creature outside it is
    # skipped for the whole frame; shooters need the tighter box as well (§3.3).
    cull_rect_x: int = 0            # 0x904A62
    cull_rect_y: int = 0            # 0x904A64
    # 0x9048F8/0x904900 ``lobber_shot_vec_h/v`` and 0x904A66/0x904A6E
    # ``lobber_shot_h_accum/v_accum``: one entry per lobber channel (MOB slots
    # 9-12).  monster_create_shot seeds all four when a rock is thrown; WP-7's
    # ``_advance_lobber`` (0x479C2) then adds the vector to the accumulator
    # every frame and copies only its top bits into the MOB word, so the low
    # bits carry the sub-pixel remainder.  That remainder is what makes a
    # lobbed rock arc instead of stepping in whole pixels; ``shot_dx/dy`` stay
    # as the rounded description ``thief.py``'s dodge scan reads.
    lobber_shot_vec_h: list[int] = field(default_factory=lambda: [0] * 4)
    lobber_shot_vec_v: list[int] = field(default_factory=lambda: [0] * 4)
    lobber_shot_h_accum: list[int] = field(default_factory=lambda: [0] * 4)
    lobber_shot_v_accum: list[int] = field(default_factory=lambda: [0] * 4)

    # =========================================================================
    # WP-9 · dragon
    # =========================================================================
    # 0x904890, dragon transition/state bitmask. Bit 0 is the sleeping/wake
    # transition, bit 1 is stun, bit 2 is turn, and bit 3 holds sustained fire.
    dragon_state: int = 0
    # 0x904880, cumulative hits; the 9th kills the dragon (§8.3).
    dragon_hits: int = 0
    # 0x904882/0x904884, rendered head position after its pose/facing offsets.
    dragon_head_hpos: int = 0
    dragon_head_vpos: int = 0
    # 0x904892, animation counter. Path byte index is (dragon_anim_ctr >> 3),
    # so the path phase advances every 8 frames and wraps at 128 (§8.3).
    dragon_anim_ctr: int = 0
    # 0x904886, current path program 0-4 (§8.3).
    dragon_path_num: int = 0
    # 0x90488C, packed movement state; its low nibble gates dragon fire.
    dragon_move_state: int = 0
    # 0x90488E, cardinal facing (0, 2, 4, or 6); feeds the head pose index.
    dragon_facing: int = 0
    # 0x90487C, fire cooldown; the same word serves as the stun countdown while
    # the dragon is stunned (the dragon cannot fire and be stunned at once) --
    # §8.1/§8.2.
    dragon_fire_cooldown: int = 0
    # 0x904894–0x90489A, head plus three body segment MOB slots.
    dragon_seg_mob_ids: list[int] = field(default_factory=lambda: [0] * 4)
    # Compatibility alias for the primary entry above. Set by level setup/tests.
    dragon_mob_slot: int = 0

    # =========================================================================
    # WP-10 · thief and mugger
    # =========================================================================
    thief_mode: int = 0             # 0x904BA0
    thief_victim: int = -1          # 0x904B9A, wealthiest-player target index
    thief_victim_pos: int = 0       # 0x904B98, target's prior packed maze cell
    thief_path_direction: int = 0   # 0x90404A, byte; selected route direction
    thief_direction: int = 0        # 0x904B9C, movement/animation direction
    # 0x904060-0x904062, shot-dodge latches.  Direction -1 means that a
    # dodge has begun but has not yet selected its first movement direction.
    thief_pursuit_direction: int = -1
    thief_pursuit_player: int = -1
    thief_pursuit_shot_direction: int = -1
    # 0x9048B0, route cell which constrains a mid-dodge direction change.
    thief_direction_change_pos: int = 0
    thief_previous_pos: int = 0     # 0x904BA2, prior route cell
    thief_current_pos: int = 0      # 0x904BA4, current thief maze/MOB cell
    thief_next_pos: int = 0         # 0x904BA6, next route cell
    thief_start_location: int = 0   # 0x904BBA, victim cell when scheduled
    # 0x904BA8-0x904BB6, carried and deferred thief/mugger loot.
    mugger_item_nextlevel: int = 0
    thief_item_nextlevel: int = 0
    mugger_item_carried: int = 0
    thief_item_carried: int = 0x7D30
    # 0x904B56, value carried by the special score-bag pickup.
    special_bonus_score: int = 100
    # 0x904BB8-0x904BBE, collision and transporter state.
    thief_collision_direction_code: int = 0
    thief_stolen_item: int = 0
    thief_tport_active: int = 0
    path_direction_grid: bytearray = field(
        default_factory=lambda: bytearray(0xC00)
    )  # 0x905054, 24 rows × 0x80 bytes; overlaps the HUD workspace
    thief_enter_time: int = -1      # 0x904B9E, frames until entry, -1 = idle
    # 0x9048BC, thief per-frame movement units (0x180 mugger / 0x200 thief; §9.1)
    thief_speed: int = 0
    # MOB slot of the thief while deployed (0 = not on the level)
    thief_mob_slot: int = 0
    # 0x9049C4, one direction/state word per projectile channel.  Player
    # channels are 1-4, and their directions occupy indices 0-3.
    # Eight is the invalid/no-live-shot sentinel used by the dodge scan.
    shot_direction: list[int] = field(default_factory=lambda: [8] * 12)

    # =========================================================================
    # WP-11 · living maze (walls, doors, transporters, forcefields)
    # =========================================================================
    # 0x904030, transporter colour animation position (bounces 0-5)
    tport_cycle_pos: int = 0
    # 0x904032, transporter direction of bounce (+1 or -1)
    tport_cycle_dir: int = 1
    # 0x904034, 2-bit sub-frame divider for transporter animation (ticks every 4th frame)
    tport_cycle_divider: int = 0
    # 0x90402E / 0x90402C: directions for colors held in live playfield RAM.
    palette_pulse_dir_a: int = 0
    palette_pulse_dir_b: int = 0
    # Host-side latches for the two transporter secret-objective write sites.
    # The ROM writes source/destination pad bits synchronously at 0x5025C and
    # 0x509E4; gauntpy observes the armed transition on its next world frame.
    tport_secret_pad_masks: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    tport_secret_event_keys: list[int] = field(
        default_factory=lambda: [-1] * NUM_PLAYERS
    )
    # 0x904046, live forcefield colour word (0 = blinked off, harmless to main_move_players)
    forcefield_color: int = 0
    # 0x904049, forcefield step counter 0-7.
    forcefield_step: int = 0
    # 0x904048, byte countdown. The ROM predecrements it, so zero wraps to 255.
    forcefield_step_timer: int = 0
    # forcefield_cycle_delay_profiles[0] at ROM 0x571DA (§7.4). Level setup
    # replaces this with profile ``levelnum_current & 3``.
    forcefield_step_durations: list[int] = field(
        default_factory=lambda: [0x10, 0x20, 0x10, 0x20, 0x10, 0x20, 0x20, 0x40]
    )
    # forcefield_color_steps -- ROM 0x405C0.
    forcefield_colors_table: list[int] = field(
        default_factory=lambda: [0xFF00, 0xF0F0, 0x9FFF, 0xF00F]
    )
    # 0x910780, zero-terminated packed forcefield segment words.
    forcefield_segments: list[int] = field(default_factory=list)
    # Host-side setup latches: ROM level setup builds these before the main
    # loop; gauntpy's lazy bridge performs that same work on its first frame.
    forcefield_segments_ready: bool = False
    # 0x90401A, cyclic-wall timer. Setup clears it; an expired predecrement
    # reloads 0x78 (120 frames).
    cyclic_wall_timer: int = 0
    # 0x90401C, current cyclic-wall phase (0 initially, then 1, 2, 3).
    cyclic_wall_phase: int = 0
    # Color RAM Spare 0x910600: one byte per 4-tile group, 2 bits per tile.
    # phase_bits = (cyclic_wall_assign[slot >> 2] >> ((slot & 3) << 1)) & 3.
    # Zero = not a cyclic wall; 1-3 = phase assignment. Populated by level setup (WP-3).
    cyclic_wall_assign: list[int] = field(default_factory=lambda: [0] * 256)
    cyclic_wall_setup_ready: bool = False
    # 0x9048A6, random wall timer (negative = disabled, 0 = process, positive = countdown; §19)
    random_wall_timer: int = -1
    # 0x9048A0, random wall low water mark (first WALL_RANDOM slot; set by level setup WP-3)
    random_wall_low_mark: int = 0
    # 0x9048A2, random wall target index
    random_wall_target: int = 0
    # 0x9048A4, random wall current index
    random_wall_current: int = 0
    random_wall_setup_ready: bool = False
    # 0x904A76/0x904A86, eight independently advancing door-opening fronts.
    door_endpoint_pos: list[int] = field(default_factory=lambda: [0] * 8)
    door_endpoint_dir: list[int] = field(default_factory=lambda: [0] * 8)

    # =========================================================================
    # WP-12 · potions and magic
    # =========================================================================
    # 0x904022, player index plus trigger bits for the current potion blast.
    potion_player: int = 0

    # =========================================================================
    # WP-13 · camera
    # =========================================================================
    scroll_x: int = 0
    scroll_y: int = 0
    # 0x904BD8: per-player tile position for camera extent calculation.
    # Each entry is the packed slot (row<<5|col) of that player's cell, which
    # is ``Player.mob_slot`` itself except on the rare frame where an occupied
    # destination held the migrating record back (players.migrate_player_record).
    player_tile_pos: list[int] = field(default_factory=lambda: [0] * 4)
    # 0x904BCE: per-player "in maze" flag (nonzero = camera should track this player)
    player_in_maze: list[int] = field(default_factory=lambda: [0] * 4)

    # =========================================================================
    # WP-14 · scoring, HUD, dialogs
    # =========================================================================
    # 0x90493A: 4-slot popup timers (one per floating score channel, slots 17-20)
    score_display_timer: list[int] = field(default_factory=lambda: [0] * 4)
    # Per-player dirty flags for score/health redraw (no documented address — WP-14 internal).
    # Start dirty so the first real frame redraws everything.
    score_dirty: list[int] = field(default_factory=lambda: [1] * 4)
    health_dirty: list[int] = field(default_factory=lambda: [1] * 4)
    # 0x90497C: 4 effect animation counters (shared documentation name
    # ``mob_effect_anim_counter``; WP-8 did not add this field so WP-14 owns it).
    mob_effect_anim_counter: list[int] = field(default_factory=lambda: [0] * 4)
    # 0x904007 bit 2: master score-display gate (1 = enabled).
    score_display_enabled: int = 1
    # Diagnostic shadow of what draw_player_score / draw_player_health last
    # wrote. Rendering reads alpha_ram itself, not this convenience latch.
    info_panel: InfoPanel = field(default_factory=InfoPanel)
    # Per-character-class high-score ladders, ten entries of (score, initials)
    # best first -- the shape OS ``read_high_score_entry`` (0x1AE) exposes from
    # the EEPROM image (doc/02_os_rom.md §8.11). Empty lists are the ROM's
    # "high-score banks are empty" condition, which ``highscore_table_init``
    # (0x49BD0) fills from ``factory_highscore_records`` (ROM 0x57EBA).
    high_scores: list[list[tuple[int, str]]] = field(
        default_factory=lambda: [[] for _ in range(4)]
    )
    # 0x9049E4 ``dialog_first_encounter_flags``: 32-bit "already shown" bitmask,
    # one bit per first-encounter dialog (§10.4).
    dialog_first_encounter_flags: int = 0
    # 0x904AA4 message buffer: the lines of the message box currently on screen
    # (empty when no box is up). ``dialog_timer`` is its countdown.
    dialog_message: list[str] = field(default_factory=list)
    # 0x904A9A / 0x904A9C: the box's width in alpha columns and height in rows,
    # as dialog_first_encounter computed them.
    dialog_box_width: int = 0
    dialog_box_rows: int = 0
    # Which player the box belongs to (-1 = centred/no owner), the argument
    # ``dialog_position_box`` (0x4CB50) takes; also selects its text palette.
    dialog_player: int = -1
    # 0x904AA0/0x904AA2: alpha-cell origin chosen when the box is created.
    dialog_box_column: int = -1
    dialog_box_row: int = -1
    # 0x904BD6 ``thief_tport_timer``: the shared thief/effect transition
    # counter main_score_update's loop 1b advances. 0xFFFF/-1 = idle. Its two
    # companions are 0x904BCC (the thief picture saved across the dissolve) and
    # 0x904BE0 (the slot the thief re-emerges in). WP-14 owns them because
    # loop 1b is their only reader; WP-10 arms them when a thief teleports.
    thief_tport_timer: int = -1
    thief_tport_saved_picture: int = 0
    thief_tport_dest: int = 0
    thief_level_setup_done: bool = False
    # 0x905C54/0x905D54: one-based transporter route records. Bits 15-8 name
    # the linked transporter ID; low nibble is direction+1.
    tport_route_forward: list[int] = field(default_factory=lambda: [0] * 33)
    tport_route_reverse: list[int] = field(default_factory=lambda: [0] * 33)
    # 0x904BC4 ``tport_saved_picture``: one word per player, the hero's MOB
    # picture parked across a transporter transition by loop 2's save milestone
    # and put back by ``tport_restore_player_picture`` (0x50B88).
    player_tport_saved_picture: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )

    # =========================================================================
    # WP-15 · exits, treasure rooms, secret rooms
    # =========================================================================
    # 0x9049E8: treasure room countdown in frames (0 = not in treasure room)
    treasure_timer: int = 0
    # 0x904A08 exit_timer: moving-exit relocation countdown; reloads to 0x12C
    # (300 frames), verified by disassembly of main_exit_move (0x52A74).
    exit_move_timer: int = 0x12C
    # 0x904878: secret room availability counter (counts down once per level)
    secret_possible_counter: int = 20
    # 0x90487A: secret room start value (for counter reload)
    secret_possible_start: int = 20
    # 0x904063: current secret room winner player index (-1 = none)
    secret_winner: int = -1
    # 0x904AA4 dialog/name buffer reused by the secret-room contest flow.
    secret_name_buffer: list[int] = field(
        default_factory=lambda: [ord("A")] + [ord(" ")] * 28
    )
    secret_code: str = ""
    # 0x904870: maze number of previous secret room
    secret_prev_maze: int = 0
    # 0x904065: trick/challenge ID active in current level (0 = none)
    secret_trick_id: int = 0
    # 0x904064 ``trick_last``: the maze trick a player won, saved when
    # show_level_start_screen replaces it with a challenge code (0x44E06).
    secret_trick_last: int = 0
    # The winner's inventory, stashed on the way into the secret room and added
    # back on the way out. The ROM parks them in spare array slots --
    # 0x90405F (keys), 0x90405A reused as scratch (potions) and 0x905F6D
    # ``secret_saved_supershot`` -- at main_start_game 0x482E6-0x48306, and adds
    # them back at show_level_end_bonus_screen 0x4D86E-0x4D8A0. Named fields
    # here because the ROM's slot reuse aliases player 0's keys.
    secret_saved_keys: int = 0
    secret_saved_potions: int = 0
    secret_saved_supershot: int = 0
    # 0x904872: per-player trick progress/violation flags (WP-15 tracks, WP-7 writes)
    secret_tricks_flags: list[int] = field(default_factory=lambda: [0] * 4)
    # Treasures picked up on the current level -- feeds the level-end bonus
    # tally (doc/04 §16 "100 x players x coins x treasures"). Reset by level
    # setup, incremented by player_tile_interact on a treasure pickup. (No single
    # ROM address; the original derives the count during the bonus screen.)
    level_treasures: int = 0
    # 0x904A50 player_treascount: per-player treasure pickups on this level, the
    # bonus tally's treasure factor (show_level_end_bonus_screen 0x4D57E/0x4D638).
    # The ROM bumps it in player_tile_interact's treasure arm (0x519F8) and
    # clears it in player_start_inner (0x48E86); WP-15 owns the counter and
    # exposes ``exits.treasure_collected()`` as that write site.
    player_treascount: list[int] = field(default_factory=lambda: [0] * NUM_PLAYERS)
    # 0x904A4E global_ui_delay_timer: holds the bonus tally and then the level
    # splash before player placement. bonus_amount is the computed award shown
    # on the treasure/secret-room exit screen.
    bonus_timer: int = 0
    bonus_amount: int = 0
    # Host-side phase marker for the shared 0x904A4E timer. True after the next
    # maze and its level splash are prepared, while hero placement is deferred.
    level_start_pending: bool = False
    # 0x904B80: levels left before the next treasure room. Seeded with
    # getrandom(3)+3 the first time levelnum_current reaches 6
    # (maze_new_level_setup 0x438E4-0x438FC), decremented once per level on the
    # end-of-level path, and re-seeded by show_level_start_screen (doc/06 §3.5).
    level_next_treasure: int = 0
    # 0x904B7E: levels left before the next guaranteed hidden potion
    # (maze_addrandompickups 0x43F8E-0x43FA6). Decremented on the same
    # end-of-level path as level_next_treasure (main_move_players 0x4A76C).
    level_next_potion: int = 0
    # 0x904BC0: treasure-room inter-announcement delay. Counted down inside the
    # once-per-second path, so its unit is countdown seconds, not frames (§16).
    treasure_announcement_delay: int = 0
    # 0x904BC2: treasure-countdown voice set. 0 = speak the true numbers;
    # 1-4 select one of the four scrambled fake countdowns at ROM 0x5AB90.
    treasure_voice_set: int = 0
    # 0x910740 exit_slot_list / 0x904A06 exit_count: every EXIT tile the current
    # maze decoded to, in slot order. The ROM fills this in maze_new_level_setup
    # (0x43A34-0x43A5A); exits.py rebuilds it from the MOB table because WP-3's
    # level setup does not (see exits.exit_scan_level).
    exit_slots: list[int] = field(default_factory=list)
    # 0x904A0A: slot of the exit that is currently open. Zero disables
    # main_exit_move entirely (maze_new_level_setup clears it at 0x43B9A when
    # the level has no ExitMoves flag).
    exit_open_id: int = 0
    # 0x904A0C: slot the open exit is moving away from, latched at 0x528C8.
    exit_close_id: int = 0
    # Open/close animation step, 0-7, while exit_move_timer is negative. No RAM
    # address of its own: the ROM keeps it in D4 as ``(-exit_timer) >> 2``
    # (main_exit_move 0x52AAC-0x52AB4) and uses it to index the stamp scripts at
    # ``ptr_exit_openclose_anim`` (0x90489C). Zero means "settled".
    exit_anim_frame: int = 0

    # =========================================================================
    # WP-16 · coins, credits, session lifecycle
    # =========================================================================
    credits: int = 0
    # 0x904FEC: coin insertion counters (4 × 2-bit per-channel values, packed
    # word).  coincheck compares this against last_coin_state to detect new
    # insertions.
    coin_counters: int = 0
    # 0x9049EA: shadow of coin_counters from the previous frame.
    last_coin_state: int = 0
    # 0x9049E2: pricing mode flag; nonzero = paid (coins required), 0 = free play.
    # 0x9049E2, hardware pricing/two-player DIP word. The host defaults to paid
    # play; tests/operators can set zero for free play.
    two_player_mode: int = 1
    # Character currently displayed during selection (per player, before commit).
    # 0x9048E8: same address as player.character, but used as the tentative value
    # during SELECTING status before the player commits.
    pending_character: list[int] = field(default_factory=lambda: [0] * NUM_PLAYERS)

    # =========================================================================
    # WP-17 · attract mode and demo playback
    # =========================================================================
    # 0x904B7C, shared attract/display countdown for the current attract screen.
    # Reloaded by start_attract_screen; 0xFFFF is the disabled sentinel (§10.5)
    # that start_attract_to_game writes at 0x4436C, and the value main_attract
    # reads as -1 through its ``tst.w``/``blt`` gate, so the machine is idle
    # until a screen actually loads a timer.
    attract_timer: int = 0xFFFF
    # 0x904B60, attract_count: TITLE screens seen since the last EEPROM re-read;
    # start_attract_screen wraps it at 13 (0x4448E-0x4449E).
    attract_count: int = 0
    # 0x90491A, LEGEND sub-screen counter (initially 2, counting down; §6.4).
    attract_legend: int = 2
    # 16-bit title intro selector/counter sampled before each TITLE setup (§14.3).
    title_intro_state: int = 0
    # Latched when TITLE starts, before title_intro_state advances. True selects
    # the ROM's 8-record first-intro motion; later cycles use the 4-record script.
    title_logo_full_program: bool = False
    # main_logo_updcolors cadence counter (palette cycling proper is WP-2).
    logo_color_timer: int = 0
    logo_color_dir: int = 1          # 0x904A16
    logo_cycle_timer: int = 0        # 0x904A18
    logo_bright_timer: int = 0       # 0x904A1A
    logo_bright_accum: int = 0       # 0x904A1C
    logo_color_cur: int = 0          # 0x904A1E
    logo_color_index: int = 0        # host index for ROM pointer 0x904A20
    logo_motion_index: int = -1      # host index for ROM pointer 0x904A10
    logo_scroll_timer: int = 0       # 0x904A14

    # =========================================================================
    # WP-18 · sound
    #
    # The command queue, the recovery/retry machine and the speech gate are all
    # implemented (subsystems/sound.py). What the port deliberately does not do
    # is synthesise audio: the accepted command stream is the output, recorded
    # in ``sound_log``. That is a host boundary, not an unfinished subsystem.
    # =========================================================================
    # Outgoing command ring: 8 physical slots at 0x90404B (write head 0x904053,
    # read head 0x904054), one slot reserved to distinguish full from empty, so
    # usable capacity is 7 -- doc/04_game_subsystems.md §11.1-11.2.
    sound_queue: list[int] = field(default_factory=list)
    # Permanent history of every command accepted by the immediate fast path or
    # by main_update_sound's queue drain. Never cleared automatically -- this is
    # the WP-18 test oracle.
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
    # No sound board is emulated, so no reply byte ever arrives from OS 0x178
    # on its own -- the board is the one piece of hardware the port replaces
    # with a command log rather than reimplementing. Tests (and any future
    # board model) push bytes here (FIFO) to drive sound_response's
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
    # Display memory · playfield/alpha VRAM and color RAM
    # =========================================================================
    # 0x900000-0x901FFF: 64 x 64 16-bit playfield descriptors, column-first.
    playfield_ram: list[int] = field(default_factory=lambda: [0] * (64 * 64))
    # Host-side invalidation key for the derived RGBA playfield raster.
    playfield_generation: int = 0
    # Descriptor-construction tables used only at ROM-equivalent stamp sites.
    # The renderer never reads them; the committed words above remain canonical.
    playfield_floor_descriptors: list[tuple[int, int, int, int]] = field(
        default_factory=lambda: [(0, 0, 0, 0)] * (32 * 32)
    )
    playfield_floor_catalog: dict[
        tuple[int, int], tuple[int, int, int, int]
    ] = field(default_factory=dict)
    playfield_wall_catalog: dict[int, tuple[int, int, int, int]] = field(
        default_factory=dict
    )
    playfield_destruct_catalog: dict[int, tuple[int, int, int, int]] = field(
        default_factory=dict
    )
    playfield_forcefield_catalog: dict[int, tuple[int, int, int, int]] = field(
        default_factory=dict
    )
    playfield_forcefield_cells: set[int] = field(default_factory=set)
    playfield_wallpattern: int = 0
    # 0x910500-0x9105FF: 128 16-bit IRGB playfield color entries.
    playfield_color_ram: list[int] = field(default_factory=lambda: [0] * 128)
    # 0x910400-0x9104FF: the corresponding 128-entry shadow bank.
    playfield_shadow_color_ram: list[int] = field(default_factory=lambda: [0] * 128)
    # Host-side invalidation key for writes to either playfield color bank.
    playfield_color_generation: int = 0
    # 0x905000-0x905EFF: 64 columns x 30 visible alpha rows.
    alpha_ram: list[int] = field(default_factory=lambda: [0] * (64 * 30))
    # 0x910000-0x9101FF: 256 16-bit IRGB alpha color entries.
    alpha_color_ram: list[int] = field(default_factory=lambda: [0] * 256)
    # 0x910200-0x9103FF: 256 16-bit IRGB motion-object color entries.
    mob_color_ram: list[int] = field(default_factory=lambda: [0] * 256)
    # 0x9049F6 / 0x9049FE: byte offsets into each player's ROM color cycles.
    player_hurt_palette_offset: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )
    player_power_palette_offset: list[int] = field(
        default_factory=lambda: [0] * NUM_PLAYERS
    )

    # =========================================================================
    # WP-20 · boot and orchestration
    # =========================================================================
    # Level-transition scratch, written by player_exit_sequence / maze_checknum
    # (subsystems/exits.py) and consumed by show_level_end_bonus_screen.
    maze_next: int = 0              # 0x904B54, next maze number
    level_next: int = 0            # next level number (transient, ROM 0x52DC6 tail)
    # Cabinet rotation state, EEPROM-backed (doc/06 §3.2). Nominally owned by
    # WP-19's config load; kept here with the rest of the transition machinery
    # that reads and advances it. Fresh-EEPROM defaults per doc/06 §3.2 table.
    maze_resume: int = 5           # 0x904010 mazerand_num, rotation resume position
    maze_stride: int = 0           # 0x90400E mazerand_adder, extra mazes per level (0-7)
    # Treasure-room rotation -- the second EEPROM-backed pair (doc/06 §3.5).
    # eeprom_load_config forces treas_mazerand_num back to 104 when it is outside
    # 104-114 (0x4303E-0x43054) and masks the adder to 0-3 (0x43062); those are
    # also the fresh-cabinet defaults.
    treas_mazerand_num: int = 104  # 0x904018, next treasure maze
    treas_mazerand_adder: int = 0  # 0x904016, treasure stride (0-3)

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
