# Gauntlet II ROM Reverse Engineering Report

*Analysis of row76.bin (Game ROM, 0x040000–0x07FFFF) and row10.bin (Slapstic/level data ROM, 0x038000–0x03FFFF).*

---

## Summary

This report covers a full reverse engineering pass of the Gauntlet II game ROM across all major subsystems. All functions listed in PLAN.md phases 2–10 were analyzed; findings are documented below by subsystem. All names and comments have been persisted in `gauntlet.r2`.

---

## 1. Main Loop & Game Initialization

### Jump Table (0x40000–0x40054)
Ten JMP entries confirmed as documented in GAME_ROM_KNOWN.md. Targets match entries listed in section 2.2.

### `game_start` (0x4014c)
Initializes all major RAM subsystems: clears player state arrays, sets up MOB lists, loads initial palettes, configures sound hardware, and calls `game_init_settings` before handing off to the main loop.

### `m2mainloop` (0x42a66)
Per-frame dispatch confirmed. Key per-frame call sequence (GAMEMODE_NORMAL):
1. `coincheck` — coin insertion check
2. `main_move_monsters` / `monsters_everything` — monster AI
3. `main_move_players` — player input and movement
4. `main_handle_shots` — shot movement and tport cycling
5. `main_scroll_playfield` — scroll update
6. `main_health_countdown` — health drain
7. `main_handle_death` — death/respawn
8. `main_score_update` / `main_score_display` — score display
9. `main_open_doors` — door-open logic
10. `main_handle_potions` — potion effects
11. `main_handle_dragon` — dragon state machine
12. `main_start_thief` / `main_thief_move` — thief AI
13. `main_exit_move` — moving exit
14. `main_cycle_tport_and_ffield` — transporter/forcefield cycling
15. `main_update_sound` — sound queue
16. `main_walls_random_move` / `main_walls_cyclic_move` — wall animations

Game mode dispatch uses `ram.os_flag` (word) as the level/mode selector; values below 0x5 are pre-game, 0x5–0x72 are normal gameplay, ≥0x73 are special/attract modes.

---

## 2. Monster System

### `monsters_everything` (0x40e6a)
Entry point called once per frame. Iterates all MOB slots, dispatching to per-monster-type handlers. Manages monster health, shot generation, and generator spawning.

### `monster_find_and_shoot` (0x41750)
Finds the nearest player within range. Sets monster facing direction. Calls `find_unused_shot` and `monster_create_shot` if attack conditions are met. Target player selection accounts for IT status.

### `monster_create_shot` (0x490dc)
Creates a shot MOB at the monster's current position. Shot tile type encodes direction (bits in mob_link). Calls `mob_place_shot` then links into the shot list.

### `handle_generate` (0x492c0)
Generator (spawn point) logic. Checks `ram.monster_count` against the level cap. Spawns a new monster MOB at the generator position using the maze-encoded monster type. Respects the max-monsters-per-type cap.

### `main_move_monsters` (0x49034)
Per-frame dispatch. Iterates all active monster MOBs. Calls movement, collision, and attack functions for each. Monster type (from mob_link high bits) selects the movement handler.

### `death_potion` (0x49446)
Handles DEATH being killed by a potion. Calls `death_damagetrack` to apply AOE damage to all monsters on-screen, removes the Death MOB, plays death sound, awards score.

### `death_damagetrack` (0x49a3c)
AOE damage system. Scans all active monster MOBs within screen bounds. Reduces each monster's health by a potion-damage amount. Monsters reduced to ≤0 are killed (score added). Also damages player health by a small amount.

### `find_unused_shot` (0x41b16)
Scans the shot MOB array (dedicated region) for a slot with mob_picture == 0. Returns the slot index or -1 if full.

### `monster_playerhit` (0x495a6)
Called when a monster occupies the same tile as a player. Applies monster-type damage to player health. Checks `ram.player_invincible` flags. Triggers `sound_player_hurt` and heartbeat sounds at low health.

---

## 3. Player System

### `main_move_players` (0x4a53a)
Per-frame player movement. Reads debounced joystick input for each active player, computes new position via collision checks (`mob_check_up/down/left/right`), updates `mob_hpos`/`mob_vpos`. Calls `player_tile_interact` when player enters a new tile.

### `player_resetcounters` (0x43360)
Clears all counters for one player: health reset to starting value, score unchanged, all power-up flags cleared, shot-speed/damage to defaults, IT flag cleared.

### `player_resetall` (0x4341e)
Calls `player_resetcounters` for all four player slots, then resets the shared player state arrays.

### `player_it_set` (0x45866) / `player_it_unset` (0x4590e)
IT mechanic: `player_it_set` copies a random "IT punishment" from a ROM table to the target player, plays the IT sound (0x35), updates the IT display. `player_it_unset` clears IT status and restores normal attack parameters.

### `player_inv_update` (0x45aca)
Updates the right-side inventory panel for all active players. Reads power-up flags from RAM and writes icon tile IDs to the alpha layer at fixed column positions.

### `player_add_score_with_mult` (0x5214c)
Adds score to a player accounting for the bonus multiplier (`ram.score_multiplier`). Updates the 32-bit score accumulator. Calls `highscore_check` to test for a new high score.

### `player_lowhealth` (0x487ca)
Called each frame per player. Plays heartbeat sound (0x18–0x1b by player index) when health < threshold. Sets the dying flag when health reaches 0; triggers player death sequence.

### `player_coindrop` (0x488ca)
Handles a coin insertion matched to an active player. Adds health from a table at 0x57862 based on `ram.game_pricing_config`. Updates coin-count display.

### `player_join` (0x48bb6) / `player_join2` (0x48a36)
`player_join2` handles a player pressing START from attract: picks character class (from `pick_character`), initializes MOB, sets state to active. `player_join` is the outer wrapper that validates slot availability, plays join sound (0x9–0xc), calls `speech_welcome`.

### `sound_player_hurt` (0x49a98)
Plays the appropriate hurt speech sample for the player's character class (warrior/valkyrie/wizard/elf hurt sounds). Throttled by a per-player cooldown to avoid rapid-fire speech.

### `player_activecount` (0x4d900)
Counts players with state != 0 (active gameplay). Returns count in d0. Used by many systems to gate behavior when no players remain.

### `player_tport` (0x50224)
Entry point when a player touches a transporter tile. Validates the transporter, calls `tport_player_flash` (flash effect), then `tport_player_move` (teleport state machine).

### `player_tile_interact` (0x511ac)
Large dispatch by tile type (from `mob_link >> 10`). Handles: food pickup (adds health, plays sound 0xd), key pickup (0x13), treasure (0x26, calls `player_add_score_with_mult`), doors (check key), transporter (calls `player_tport`), exit (calls `player_exit_sequence`), stun tiles (0x32–0x34), IT tile (0x35), acid (0x36), slow-motion (0x37). Central hub for all tile-based player interactions.

### RAM — Player Arrays (base near 0x904908)
From analysis of `player_resetcounters` and related functions, the per-player arrays are word-sized with stride 2 (4 players × 2 bytes):
- `ram.player_state` (0x904908..0x90490e) — 0=inactive, 1=active, 2=winning secret room, 3=exiting, 4=entering name
- `ram.player_health` — 16-bit health (0 = dead)
- `ram.player_shot_power` — shot damage value
- `ram.player_shot_speed` — shot speed tier
- `ram.player_invincible` — extra armor flag
- `ram.player_score_lo` / `ram.player_score_hi` — 32-bit score (two words)

---

## 4. Level/Maze System

### `find_maze` (0x40c78)
Looks up maze entry from the slapstic ROM table by maze number. Returns pointer in `ram.cur_maze_ptr`. Sets the slapstic bank in d1.

### `maze_setupnew` (0x44ac2)
Full maze initialization from the current maze data pointer. Calls `maze_decode` to decompress tile data into playfield RAM, then `maze_objects_setup` to place all MOBs (monsters, generators, items, exits, transporters). Sets `ram.maze_pickup_config`.

### `maze_decode` (0x4c1bc)
Decompresses maze data from the slapstic ROM into playfield RAM. Run-length encoded format: each run specifies tile type and count. Also decodes the maze header (dimensions, type flags, monster table).

**Maze data structure** (from decoding analysis, offsets from maze base pointer):
- Byte 0: secret room type (0 = none, other = secret room monster type)
- Bytes 1–3: maze feature flags (assembled into `ram.maze_pickup_config` by `maze_load_pickup_config`)
- Byte 4: additional config byte
- Byte 5+: compressed tile data (RLE)

### `maze_addrandompickups` (0x43f68)
Adds random pickups to the maze after setup. Checks `ram.maze_pickup_placed` and `ram.vblank_occurred` before placing a type-0x3d item via `maze_randomplace`. Uses `ram.maze_pickup_config` bits 10:8 to determine quantity. Gated by `ram.os_flag` (game mode).

### `maze_randomplace` (0x42e9a)
Places a tile-type object at a random empty floor tile. Scans mob_link for open floor slots, picks one randomly via `getrandom`, calls `mob_create` with the given tile type.

### `maze_show` (0x4526a) / `maze_hide` (0x4529a)
Shows/hides the alpha overlay layer by writing to the alpha layer control register. Used for level transitions and splash screens.

### `maze_checknum` (0x52eca)
Validates and wraps the maze number. Handles end-of-game wraparound and loops to level 1 after the last level.

### `level_splash` (0x4be24)
Displays the new-level splash screen ("LEVEL X" etc.) via alpha layer writes. Waits for a fixed duration, then clears.

### `setup_infopanel` (0x452d0)
Sets up the right-side info panel: player name tags, health bars, and inventory icons. Writes to a fixed column of alpha RAM.

### `maze_new_level_setup` (0x438ae, renamed from fcn_438ae)
New level initialization hub. Called when transitioning to a new level:
1. Resets thief timer and target to 0xFF
2. Clears dragon encounter flag
3. Optionally sets a random level timer (0x904b80)
4. Calls `slapstic_cmd_bitwise` to switch ROM banks
5. Calls `maze_setupnew` with `ram.cur_maze_ptr`
6. Sets up secret room state from maze byte 0
7. Calls `maze_food_mob_consume` (arg=0xffff) to find a food tile and mark it as the level start slot (`ram.level_start_slot`)
8. Calls `scroll_to_slot` to center the view there
9. Clears tport/exit position tables (0x910700 / `ram.exit_pos_table`)
10. Scans all mob_link slots to repopulate tport and exit tables

### `maze_load_pickup_config` (0x436fe, renamed from fcn_436fe)
Reads 4 pickup-config bytes from maze data, assembles into a 32-bit value, stores to `ram.maze_pickup_config`. Then randomly XORs and ORs feature flags based on current game level (`ram.os_flag`) and frame count (`ram.vblank_occurred`). Calls `get_random_maze_flags` for randomized bits. Higher levels get more aggressive random modifications.

### `get_random_maze_flags` (0x436cc, renamed from fcn_436cc)
Selects a random entry from a 13-entry ROM table at 0x57012 using `getrandom(0xd)`. If maze config bit 2 is set and the result is 0x80, overrides to 0x2. Returns a maze feature flags longword.

### `maze_food_mob_consume` (0x43d8c, renamed from fcn_43d8c)
Removes a random food or treasure mob from the active mob_link list. Called during level setup:
- arg=0: scan for tile type 0x10 (food), call `pf_replace(slot, 0)` and `moblist_remove_and_clear`
- arg=0xffff: scan for tile type 0xf (food variant), remove it, store its slot index in `ram.level_start_slot` (0x9049e0)
- arg=N (N≥1): remove N random treasure mobs (types 0x31/0x32), iterating until N consumed

### `slapstic_cmd_bitwise` (0x43826)
Issues the bank-switch command sequence to the Slapstic chip (row10.bin). Reads current bank from `0x904b8c`, uses ROM tables at 0x57046 and 0x5704e to compute the access addresses, performs the required read-write sequence to latch the bank.

### Slapstic utility functions
- `slapstic_cmd_bank0` (0x56e58), `slapstic_cmd_bank3` (0x56e6e), `slapstic_cmd_bankX` (0x56e84): switch to specific banks
- `slapstic_verify` (0x56eaa): verifies slapstic is responding correctly

---

## 5. Thief, Mugger & Exit Systems

### `thief_target_calc` (0x4dff6)
Calculates player "wealth" (score × multiplier + items). Selects the wealthiest active player as the thief's target. Stores target player index in `ram.thief_target_player`.

### `thief_setup` (0x4e432)
Initializes thief MOB for the level: picks spawn position near an edge of the maze, sets initial facing direction, links MOB into the active list. Reads thief speed from maze flags.

### `thief_timer_set` (0x4e4d8)
Calculates next thief appearance timer based on target player wealth and current level. Lower wealth → longer delay. Stores result in `ram.thief_timer`.

### `main_start_thief` (0x4deb8)
Decrements `ram.thief_timer` each frame. When it reaches zero (and a player is active), calls `thief_target_calc` then `thief_setup` to deploy the thief.

### `main_thief_move` (0x4e8dc)
Per-frame thief movement state machine. States: idle → approaching target → stealing (overlapping player) → fleeing. When overlapping: steals item (calls `thief_steal_effect`), plays "thief" speech (0x62–0x65). Exit when thief reaches maze edge calls `thief_exit`. Also handles mugger variant behavior.

### `thief_exit` (0x4e122)
Thief departure: plays exit animation, removes thief MOB, resets `ram.thief_mob_id` to 0. Optionally schedules next thief appearance.

### `main_exit_move` (0x5287c)
Manages the moving exit feature. When the maze has a moving exit (maze flag bit), periodically relocates the exit tile to a new random empty position using `maze_randomplace`. Plays sound 0x31 ("Exit Moving").

### `exit_get_id` (0x52b06)
Looks up the exit's MOB slot from the exit position table. Returns the slot index for the exit at a given maze position.

### `exit_create_player_anim` (0x5df80)
Creates the player exit animation MOB (the player character "walking into" the exit portal). Sets animation frame sequence from a ROM table.

### `player_exit_sequence` (0x52b40)
Player exiting state machine. Plays exit sound (0xe–0x11 by player), runs `exit_create_player_anim`, sets player state to 3 (exiting), calls `maze_checknum` and advances to next level when all exiting players are done.

### RAM — Thief
- `ram.thief_timer` (0x904b9c): countdown to next thief deployment
- `ram.thief_target_player` (0x904ba0): player index being targeted (0–3 or 0xFF=none)
- `ram.thief_mob_id` (0x904ba2): thief's MOB slot ID
- `ram.thief_steal_count` (0x904ba4): number of items stolen this level
- `ram.thief_approach_dir` (0x904ba6): current movement direction
- `ram.thief_stolen_item` (0x904bbc): tile type of last stolen item

---

## 6. Transporter & Forcefield Systems

### `handle_tport` (0x47cfe)
Handles a player touching a transporter tile. Copies player MOB position to the transporter animation slot, creates a `tport_create_splodey` explosion animation, and triggers the transport sequence. Player MOB is hidden during transport (picture set to 0x1709 flash frame).

### `tport_cycle_start` (0x47c0e, renamed from fcn_47c0e)
Initializes a transporter animation MOB at the first animation frame (0x924). Sets `ram.tport_active_flags[slot]` = 0xFF to mark this transporter as cycling.

### `tport_cycle_update` (0x47dae)
Per-frame transporter animation cycling. Advances frames in the 0x924–0x95a range. Called from `main_handle_shots` for each active transporter MOB.

### `tport_player_flash` (0x50616)
Saves the player's current MOB picture to the `ram.ptr_tport_pic_save` buffer and sets the player's picture to a flash frame (0x1709). Used as a visual indicator when entering a transporter.

### `tport_player_move` (0x50662)
Full teleport state machine. Finds a valid destination transporter (calls `tport_check_dest`), handles IT/thief handoff, plays transport sound (0x28), calls `handle_tport` at the destination, then restores the player MOB. Manages multi-frame transition animation.

### `tport_find_id` (0x4e7c0)
Searches `tport_pos_table` (0x910700, count = `ram.num_tports`) for an entry matching the given maze position. Returns slot index + 1, or 0 if not found.

### `tport_check_dest` (0x50ade)
Validates a potential transport destination. Returns failure if the destination has an empty MOB slot, a locked door (tile types 0xd or 0xe), or a wall tile (0x2f, 0x3c, 0x3e).

### `tport_create_splodey` (0x5df8e)
Creates the transporter explosion/sparkle animation MOB at the teleport destination. Short animation sequence, then MOB is removed.

### `pf_isff` (0x5fc5e)
Checks if a given maze coordinate has a forcefield tile. Reads `ff_segment_table` (0x910780) which is a terminated list of forcefield segments, each encoding position, length, and direction flags.

### `main_cycle_tport_and_ffield` (0x40528)
Per-frame forcefield and transporter color cycling. For forcefields: reads color index from `ram.ff_cycle_index` (0x904049), advances `ram.ff_cycle_timer` (0x904048), updates color RAM entry at `0x904042`. For transporters: cycles through palette entries.

### RAM — Transporter (dense pointer region 0x904bc4–0x904bea)
- `ram.ptr_tport_pic_save` (0x904bc4): longword pointer to per-slot saved picture array
- `ram.tport_saved_mob_state` (0x904bcc): word — saved MOB state during transport
- `ram.ptr_tport_phase` (0x904bce): longword pointer to per-slot transport phase array
- `ram.ptr_tport_frame_ctr` (0x904bd6): longword pointer to per-slot frame counter array
- `ram.ptr_tport_dest` (0x904bd8): longword pointer to per-slot destination slot array
- `ram.tport_transition_mob` (0x904be0): word — MOB slot used for transition effect
- `ram.ptr_tport_type` (0x904be2): longword pointer to per-slot transport type array
- `ram.tport_active_flags` (0x90497c): byte array[N] — 0xFF = transporter cycling
- `ram.num_tports` (0x904b84): word — number of active transporters on current level
- `tport_pos_table` (0x910700): word array[32] — maze slot index for each transporter

### RAM — Forcefield
- `ram.ptr_ff_color` (0x904042): longword pointer to forcefield color entry in color RAM
- `ram.ff_cycle_timer` (0x904048): byte — countdown to next color cycle step
- `ram.ff_cycle_index` (0x904049): byte — current index into forcefield color table
- `ff_segment_table` (0x910780): forcefield segment list (terminated by 0)

---

## 7. Dragon System

### `main_handle_dragon` (0x54454)
Full dragon state machine. Dragon states encoded in `ram.dragon_state` (0x904890) as a bitmask:
- Bit 0: awake (1) / sleeping (0)
- Bit 1: locked (door-blocking behavior)
- Bit 2: stunned
- Bit 3: turning

Dragon wakeup: triggered by `dragon_player_proximity`; runs wake animation (negative `ram.dragon_anim_ctr` counter). Active dragon: calls `dragon_attack_check` and `dragon_move_update` each frame. Stun: decrements `ram.dragon_stun_timer`, returns to active when 0.

### `dragon_player_proximity` (0x549ea, renamed from fcn_549ea)
Checks if any player is within the dragon's aggro range (col ±9, row ±5). If so, starts the wake animation sequence and sets the awake bit in `ram.dragon_state`.

### `dragon_fire_attack` (0x54748)
Executes a fire breath attack toward the targeted player. Creates fire MOBs at intervals along the attack vector. Uses `ram.dragon_target_hpos`/`ram.dragon_target_vpos` as the aim point.

### `dragon_move_update` (0x53e4a)
Updates dragon position each frame based on `ram.dragon_facing`. Calls collision detection. Calls `dragon_change_dir` if blocked. Updates animation frame from ROM direction tables.

### `dragon_change_dir` (0x53d10)
Picks a new movement direction for the dragon. Uses `ram.dragon_rand_dir` for randomization (set by `getrandom`). Prefers directions that keep the dragon facing the targeted player.

### `dragon_attack_check` (0x540e8)
Determines whether the dragon should fire. Checks player distance and `ram.dragon_anim_ctr` timing. Calls `dragon_fire_attack` if conditions are met.

### `secret_check` (0x486fe)
Checks whether the current level should have a secret room. Reads the secret room monster type from maze data byte 0. Tracks the player score in the secret room using `ram.secret_score_ctr` (max 0x28, min 4). Only active when `ram.secret_room_active` (0x904065) is non-zero.

### `secret_getname` (0x54ec6)
Sets up the name entry screen for a player who won the secret room challenge. Sets `ram.player_state` = 2 for the winning player and initializes the name entry UI.

### RAM — Dragon
- `ram.dragon_stun_timer` (0x90487c): countdown while stunned
- `ram.dragon_encounter_flag` (0x90487e): bit 0 = encounter triggered this level
- `ram.dragon_target_hpos` (0x904882): horizontal position of current target player
- `ram.dragon_target_vpos` (0x904884): vertical position of current target player
- `ram.dragon_rand_dir` (0x904886): random direction preference
- `ram.dragon_move_state` (0x90488c): movement sub-state
- `ram.dragon_facing` (0x90488e): current facing direction (0–3 or 8 directions)
- `ram.dragon_state` (0x904890): state bitmask (awake/locked/stunned/turning)
- `ram.dragon_anim_ctr` (0x904892): animation counter (negative = waking, positive = active)
- `ram.dragon_mob_id` (0x904894): dragon's MOB slot ID

### RAM — Secret Room
- `ram.secret_entry_frame` (0x904870): frame when player entered secret room
- `ram.secret_score_ctr` (0x90487a): score accumulated in secret room
- `ram.secret_score_thresh` (0x904878): score threshold to win
- `ram.secret_room_player` (0x904063): player index in secret room (0xFF=none)
- `ram.secret_room_active` (0x904065): byte — non-zero if secret room is active this level

---

## 8. Scoring, Coin & Dialog Systems

### `coincheck` (0x42b6a)
Called every frame. Detects new coin insertions by comparing `ram.coin_counters` to `ram.last_coin_state` (0x9049ea). On match, reads `ram.game_pricing_config` (0x9049e2) for health-per-coin table offset, adds health from table at 0x57862. Updates per-player coin count at `ram.player_coin_count` (0x904b2a array).

### `calc_score_per_coin` (0x40628)
Utility: divides a 32-bit value by a 16-bit divisor using two DIVU instructions (handles 32-bit / 16-bit = 32-bit result). Used for score-per-coin calculations in the attract screen.

### `playfield_showscore` (0x49498)
Displays a floating score popup when a player kills a monster or picks up an item. Scans `ram.score_display_timer` (0x90493a, 4 slots) for a free slot. Places a score MOB at the player position + vertical offset, active for 60 frames.

### `highscore_check` (0x49d0e)
Calls OS `read_high_score` (0x1c6) with the player's current score. If the score ranks in the top 10, stores the rank in `ram.player_highscore_rank` (0x904a4a) and sets `ram.player_state` = 4 (name entry mode).

### `dialog_first_encounter` (0x4c440)
Handles first-encounter dialogs for monsters/objects. Uses `ram.encounter_seen_flags` (0x9049e4) as a 32-bit bitmask. On first encounter (bit not set), looks up the message string from tables at 0x5a200 (message index table) and 0x5a300 (message strings). Plays sound 0x1c ("Message Appears on Screen").

### `dialog_clear_message` (0x4c70a, renamed from unknown)
Fills the dialog message buffer (`ram.ptr_dialog_msg` 0x904aa4) with N spaces then a null terminator. Used to blank the dialog text area before writing new content.

### `player_give_item_with_message` (0x4c72a)
Gives a player a power-up item and displays the associated dialog message. Sets the power-up flag in the player's inventory, calls `dialog_position_box` and writes the message string, plays the encounter sound.

### `dialog_position_box` (0x4cb50, renamed from unknown)
Positions the dialog box on-screen. If a player is visible, places the box near their position; otherwise places it at the center or near a transporter destination.

### `show_continue_screen` (0x44c7e, renamed from fcn_44c7e)
Displays the "PRESS START WITHIN X SECONDS TO CONTINUE GAME AT THIS LEVEL" screen. Triggered when all 4 player states are 0 or 0x10 (inactive/attract). Plays Gauntlet II Theme Song (sound 0x3b = "Gauntlet II Theme Song / Secret Room"). Sets `ram.continue_screen_active` (0x904b82) = 1. Gated by `0x904b7c` != 0xffff (purpose unclear; prevents showing during certain sequences).

Text is drawn via OS `draw_string` (0x25a) in 6 rows at fixed column positions.

### RAM — Scoring/Coin/Dialog
- `ram.last_coin_state` (0x9049ea): last-seen coin counter state (for edge detection)
- `ram.game_pricing_config` (0x9049e2): pricing table index / health-per-coin config
- `ram.player_coin_count` (0x904b2a): word array[4] — coins inserted per player this session
- `ram.score_display_timer` (0x90493a): word array[4] — countdown frames for score popups
- `ram.encounter_seen_flags` (0x9049e4): 32-bit bitmask — which first-encounter dialogs have been shown
- `ram.dialog_active` (0x904a9e): word — non-zero if a dialog box is currently displayed
- `ram.ptr_dialog_box_x` (0x904aa0): longword pointer to dialog X position
- `ram.ptr_dialog_box_y` (0x904aa2): longword pointer to dialog Y position
- `ram.ptr_dialog_msg` (0x904aa4): longword pointer to dialog message string buffer
- `ram.player_highscore_rank` (0x904a4a): word array[4] — high-score rank achieved (10+ = none)
- `ram.continue_screen_active` (0x904b82): word — 1 when continue screen is showing

---

## 9. Remaining Unknown Functions Resolved (Phase 10)

### `scroll_to_slot` (0x46c5e, newly named)
Converts a MOB slot index to playfield scroll coordinates. Extracts row (bits 9:5) and column (bits 4:0) from the slot, computes pixel offsets, and calls `set_scroll_pos` (0x46f56) to center the viewport on that tile. Called from `maze_new_level_setup` to center the view at the level start position.

### `set_scroll_pos` (0x46f56, newly named)
Sets the playfield horizontal and vertical scroll registers from the given (x, y) pixel arguments. Internal utility used by `scroll_to_slot` and `main_scroll_playfield`.

### `palette_fade_copy` (0x5fd80, newly named)
Copies a word array from src to dst, subtracting a delta value from each word. If the result underflows, wraps around: `result = (result & 0xFFF) | 0x1000`. This preserves the "overflow/borrow" bit used in the game's 12-bit-per-channel color encoding. Args: `(count, src, dst, delta)`.

### `supersorc_place_helper` (0x5fdb8, newly named)
Thin wrapper: loads mob array base pointers (mob_picture, mob_hpos, mob_vpos) then calls `supersorc_place` (0x5fde0). Places the Super Sorcerer mob.

---

## 10. Utility Functions Confirmed

### `getrandom` (0x5fc4e) / `getrandom_r` (0x5fc46)
Linear congruential RNG. `getrandom(n)` returns a random value 0..n-1. Seed at `ram.random_seed` (0x904bfc). `getrandom_r` is the full 32-bit variant. Both use the standard LCG formula: `seed = seed * A + B`.

### `memclear` (0x5fd58)
Clears `count+1` longwords starting at `ptr` using DBRA loop. Args: `(count, ptr)` on stack (word, longword).

### `memcpy` (0x5fd6a)
Copies `count+1` longwords from src to dst using DBRA loop. Args: `(count, src, dst)` on stack.

### `pf_replace` (0x5f31e)
Replaces a tile at a given MOB slot with a new tile type. Handles MOB list cleanup (`moblist_remove_and_clear` for old mob), updates both `vram.mob_picture` and `vram.mob_link`, then calls graphics update functions to redraw the affected tile. Special handling for tile types 2, 4–9 (doors, walls, special objects). Args: `(slot_index, new_tile_type)`.

### `pf_floor_update` (0x5e892)
Updates floor/wall tile graphics at a given (row, col) position. Reads the current tile type from `vram.mob_link`, dispatches to the appropriate tile animation table:
- Type 0x10/0x11: animated floor tiles (tables at 0x5c8a0, 0x5c8a8)
- Type 0x3e: special floor (table at 0x5caa8)
- Type 0x3f: floor with player-specific animation (state from 0x904066, table at 0x5ba70)
- Types 0xa–0xc: door tiles (flag value 0x1000)
Calls `pf_stamp_update` (0x5e542) to write the tile data to VRAM.

---

## 11. Data Structure Clarifications

### MOB (Motion Object) Arrays
4096 slots (0x000–0xFFF), 4 parallel arrays:
- `vram.mob_picture` (0x902000): word — tile/frame index; 0=unused, 0x8000/0x8001=special
- `vram.mob_hpos` (0x902800): word — horizontal position in pixels (bits 3:0 = sub-pixel flags)
- `vram.mob_vpos` (0x903000): word — vertical position in pixels
- `vram.mob_link` (0x903800): word — linked list + tile type: bits 15:10 = tile type, bits 9:0 = next-slot link

The tile type in `mob_link >> 10` is the primary dispatch key for `player_tile_interact` and `monsters_everything`.

### Maze Data Format (from `maze_decode` analysis)
Stored in slapstic ROM (row10.bin), bank-switched. Format at each maze entry:
- Byte 0: secret room type (0=none; 1–8 = secret room type/monster)
- Bytes 1–4: pickup configuration word (read by `maze_load_pickup_config`, stored as `ram.maze_pickup_config`)
- Bytes 5+: RLE-compressed playfield tile data

### `ram.maze_pickup_config` Bit Layout (from `maze_load_pickup_config` and `maze_addrandompickups`)
- Bits 10:8 (0x700): pickup quantity selector used by `maze_addrandompickups`
- Bit 14 (0x4000): "has food" flag — cleared by `maze_food_mob_consume` when only 1 food remains
- Bit 2 of byte 3: checked by `get_random_maze_flags` to restrict certain random flags
- Remaining bits: various maze feature flags (invisible walls, reflective shots, etc.)

---

## 12. Corrections to GAME_ROM_KNOWN.md

### `getrandom` address
PLAN.md Phase 10 listed `getrandom` at 0x5fc5e, but that address is `pf_isff`. The correct address for `getrandom` is **0x5fc4e** (with `getrandom_r` at 0x5fc46).

### `movea.l` immediate mode ambiguity
Several r2 disassembly listings display `movea.l 0x9XXXXX, an` which appears to be a memory dereference but is actually IMMEDIATE mode (loading the address literal into the register). Confirmed via raw byte inspection:
- Bytes `247c` = `MOVEA.L #imm.l, a2` (load address of target into a2)
- Bytes `267c` = `MOVEA.L #imm.l, a3`
- Bytes `207c` = `MOVEA.L #imm.l, a0`

This affects any analysis that assumed these instructions were dereferencing pointers. Dragon RAM locations at 0x904890–0x904894 are **direct word values** (not pointers), confirmed by raw byte checks.

### `ram.dragon_mob_id` (0x904894)
Previously uncertain whether this was a pointer or a direct value. Confirmed to be the direct word-sized MOB slot ID for the dragon's MOB entry.

---

## 13. Remaining Unknowns

### Functions not fully resolved
- `0x46f56` (`set_scroll_pos`): Named based on call context; internal implementation not fully read but purpose is clear from call sites
- `0x904b7c`: Word checked by `show_continue_screen` (must be != 0xffff to show). Likely a flag that prevents the continue screen during transitions or other special states. Best guess: `ram.continue_screen_inhibit`.
- `0x9048a0`–`0x9048a6`, `0x904a06`, `0x9048b2`, `0x904b80`: Named from `maze_new_level_setup` context. Type-0x6 tile in mob_link (stored in 0x9048a0/0x9048a2) is not definitively identified — possibly a player start marker or trapped area.
- `0x904066`: byte array indexed by slot×2, read by `pf_floor_update` for type-0x3f floor animation state. Likely `ram.floor_anim_state[slot]`.
- `fcn_5f880` (0x5f880): Not analyzed. Located near `pf_isdoor`/`pf_door_update_surrounding`, likely a door-adjacent tile helper.
- `fcn_4d476` (0x4d476): Not analyzed.

### ROM tables not fully decoded
- 0x57012: 13-entry table of maze feature flag longwords (used by `get_random_maze_flags`)
- 0x57862: Health-per-coin table (indexed by `ram.game_pricing_config`)
- 0x5a200, 0x5a300: First-encounter dialog index and message tables
- 0x5ba70: Floor animation pointer table (4+ entries, indexed by floor animation index)
- 0x5c8a0, 0x5c8a8, 0x5caa8: Tile animation data for floor types 0x10, 0x11, 0x3e

---

*Report generated from multi-session radare2 analysis. All findings reflected in gauntlet.r2 project file.*
