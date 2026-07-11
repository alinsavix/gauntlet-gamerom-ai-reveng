# Gauntlet II — Function Index

*Consolidated index of documented functions and callable entry points. Addresses are in the game ROM (0x040000–0x05FFFF) unless noted. Coverage includes conventional functions, callable leaves, shared-body entries, tail entries, and register/stack wrappers.*

## Callable-entry coverage audit

The completed audit did not rely on prologue bytes. The analyzed cross-reference set was reconciled target-by-target: every direct `BSR`/`JSR` CALL target and every direct JMP/CODE target in the game ROM resolves to a named entry below (or to a documented OS vector). The computed-PC jump tables are cataloged with exact entry counts in `03_game_rom_structure.md`; their destinations were checked as executable branches rather than inferred from table-shaped bytes.

An independent exhaustive opcode search for register-indirect `jsr` sites found no game-ROM calls through A1, A5, or A6. The actual game-ROM cases are:

- **A0:** the callback argument of `thief_probe_axis` (0x4EE2A), whose callers pass a verified tile-probe routine, plus the deliberate `jsr (0)` assertion at 0x43A18 when more than 32 transporters are discovered;
- **A2/A3:** fixed addresses hoisted into a saved register for repeated calls, including OS text/drawing vectors and already named game helpers such as `getrandom`, `maze_randomplace`, and the tile-visibility predicates; and
- **A4:** the fixed `dragon_player_proximity` address loaded by `mob_collision_test` and reused by its object handlers.

The null assertion is not a callable entry. All other indirect destinations are the same named entries reached directly elsewhere; no additional anonymous wrapper or shared body is implied by the register call itself. The leaf/BSR-only sweep is represented by the explicitly indexed non-`LINK` entries below (including the path-grid helpers, transporter pair helpers, collision-preserving wrappers, playfield register entries, and placement tails).

*Note: Corrections from FIXME.md are applied inline with `> **Correction:**` callouts.*

---

## 1. Main Loop Functions (all DONE)

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x42A66 | `m2mainloop` | Main game loop entry point; VBLANK-synchronized frame dispatch |
| 0x4017E | `game_vblank` | Game-ROM VBLANK interrupt handler: acknowledge watchdog/VBLANK, publish scroll registers, increment the semaphore, update palette effects/timers, and run the per-frame interrupt-side hooks before restoring registers |
| 0x44562 | `main_attract` | Attract mode state machine (SCORES→TITLE→DEMO→LEGEND) |
| 0x457C0 | `main_score_display` | Displays player scores on alpha layer |
| 0x45C00 | `main_open_doors` | Manages up to 8 concurrent door-opening animations |
| 0x4664C | `main_handle_death` | Handles Death monster behavior |
| 0x466F6 | `main_health_countdown` | Automatic per-frame health drain; advances the low-health heartbeat/HUD-pulse timer and schedules heartbeat sounds using mask table 0x576A8 |
| 0x46CAA | `main_scroll_playfield` | Updates playfield scroll based on player positions |
| 0x46FEA | `main_handle_potions` | Per-frame potion usage processing for all 4 players |
| 0x4715E | `main_score_update` | Updates score accumulation and display |
| 0x474F6 | `main_handle_shots` | Per-frame processing for exactly 12 projectile slots (0–3 player, 4–7 ordinary monster, 8–11 special/dragon): decrements each slot's animation/lifetime counter, reloads it from the character/slot-indexed table at 0x578C2 when appropriate, advances the class-specific picture sequence, performs MOB/tile collision and visibility handling, and removes or explodes expired shots |
| 0x4800C | `main_start_game` | Handles new game initialization |
| 0x49034 | `main_move_monsters` | Per-frame monster movement/AI dispatch |
| 0x4A53A | `main_move_players` | Per-frame player input, movement, animation |
| 0x4AE20 | `main_update_sound` | Processes sound queue and sends to sound CPU |
| 0x4CCBC | `main_msgbox_countdown` | Manages dialog box display timer |
| 0x4D29E | `main_treasure_timer` | Handles treasure room countdown timer |
| 0x4DCBA | `main_logo_updcolors` | Logo/title screen color cycling animation |
| 0x4DEB8 | `main_start_thief` | Countdown to thief deployment; spawns thief when timer expires |
| 0x4E8DC | `main_thief_anim` | Per-frame thief movement/animation state machine |
| 0x5287C | `main_exit_move` | Handles periodically relocating exits (ExitMoves flag) |
| 0x54454 | `main_handle_dragon` | Dragon state machine (sleeping/awake/stunned/turning) |
| 0x5E41A | `main_walls_random_move` | Handles random wall movement animation |
| 0x5E62A | `main_walls_cyclic_move` | Handles cyclic wall animation |

---

## 2. Initialization Functions

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x4014C | `game_start` | Game entry point; called from OS ROM at boot |
| 0x4327A | `one_time_init` | One-time initialization before first frame loop |
| 0x42F86 | `eeprom_load_config` | Read the game's EEPROM configuration block through OS service 0x24E, install defaults on failure, validate maze/difficulty/version fields, and load persistent settings/statistics into RAM |
| 0x43486 | `init_display` | Initialize main and special playfield palettes from two palette-selector arguments; does not set scroll coordinates |
| 0x44204 | `start_attract_to_game` | Transitions from attract mode to gameplay |
| 0x44414 | `start_attract_screen` | Sets up individual attract mode screens |
| 0x4438E | `load_attract_display_tilemap` | Expand the palette/run control stream at 0x5850E over the 1000 tile words at 0x5CB28 and write a 40×25 playfield display, then initialize scroll to (16,16) |
| 0x49BD0 | `highscore_table_init` | Load settings/high-score state through the OS EEPROM APIs; when the high-score banks are empty, copy the four class-specific ten-entry factory lists from ROM 0x57EBA, then initialize the four initials work buffers |
| 0x40644 | `input_debounce` | Sample the four player input ports into 0x904920–0x904926 and rotate each port's first two serial button bits into the eight debounce shift registers at 0x905F58–0x905F66 |
| 0x431EE | `eeprom_timer` | 10-minute periodic EEPROM write timer |
| 0x42D0A | `sound_response` | Processes responses from sound CPU via OS API |
| 0x42DF4 | `pick_character` | Select an unused character class for a joining player, honoring the requested cabinet/player mapping and already-active classes |
| 0x44A82 | `game_playfield_init` | OS-called playfield-init hook reached through fixed jump-table slot 0x40030: load the attract display tilemap, write words 0x5000–0x500F at 0x901480, and clear OS words reached through vectors 0x1D8/0x1DC |

---

## 3. Monster System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x40E6A | `monsters_everything` | Entry point: per-frame monster AI, movement, shots, generators |
| 0x41750 | `monster_find_and_shoot` | Find nearest player, set direction, maybe shoot |
| 0x41B16 | `find_unused_shot` | Find empty shot MOB slot |
| 0x490DC | `monster_create_shot` | Create a monster shot MOB at monster's position |
| 0x492C0 | `handle_generate` | Generator spawn routine called by `monster_loop_core`: probability/retry gate, scan eight neighboring cells through the padded 12-word direction tables at 0x57B50/68/80, require a traversable empty cell, then create the selected tiered monster |
| 0x49446 | `death_potion` | Handles Death being killed by a potion; AOE damage |
| 0x49498 | `playfield_showscore` | Displays floating score popup over dying monster |
| 0x495A6 | `monster_playerhit` | Monster overlapping player: apply damage, play sounds |
| 0x49A3C | `death_damagetrack` | AOE damage system; accumulates hit damage |
| 0x49A98 | `player_hurt_speech_timer` | Decrement one player's randomized hurt-speech cooldown; on expiry choose a class-specific hurt voice, unless acid-slowed, then reload from the active-player-count timing table |
| 0x5FDE0 | `supersorc_place` | Find empty spot behind player, place Super Sorcerer |
| 0x5FDB8 | `supersorc_place_helper` | Thin wrapper that loads MOB array base pointers then calls supersorc_place |

---

## 4. Player System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x43360 | `player_resetcounters` | Reset one player's counters (health, score unchanged, power-ups cleared) |
| 0x4341E | `player_resetall` | Reset all four player slots |
| 0x45866 | `player_it_set` | Set player as IT (verified): draws "IT" chars (0x49/0x54) in the player's HUD column, plays per-character "you're IT" speech (table 0x596F6) + sound 0xD4/0xD3; IT player tracked at 0x9049DC |
| 0x4590E | `player_it_unset` | Clear the IT label (verified): writes two blank tiles over "IT" in the HUD |
| 0x45ACA | `player_inv_update` | Draw the 12-slot inventory icon row in the player HUD (verified): key icons × `player_keysnum`, potion icons × `player_potionsnum`, blanks for the rest; VRAM row from pointer table [0x5FC12][p] |
| 0x48754 | `speech_welcome` | Play "welcome <character>" speech for joining player |
| 0x487CA | `player_lowhealth` | Play a one-shot contextual low-health voice warning for one player; gated by `player_lowhealth_spoken` and the signed respawn/speech timer, then loads that timer with 0x0708 frames |
| 0x488CA | `player_coindrop` / `player_init_for_coin` | Initialize player slot when a coin is inserted |
| 0x48A36 | `player_join2` | Handle player joining: pick character, init MOB, set state, speech |
| 0x48BB6 | `player_join` / `player_start_in_maze` | Outer join wrapper: validate slot, play join sound, call player_join2 |
| 0x49D0E | `highscore_check` | Check if player's score ranks in top 10; load `player_state_timer` with 2700 frames for initials entry or 600 frames for GAME OVER |
| 0x4D900 | `player_activecount` | Count players with state ≠ 0 (active gameplay) |
| 0x50224 | `player_tport` | Entry point when player touches a transporter tile |
| 0x50616 | `tport_player_flash` | Save MOB picture, set flash frame (0x1709) for transport visual |
| 0x50662 | `tport_player_move` | Full teleport state machine: find destination, animate, move |
| 0x50B88 | `tport_restore_player_picture` | Stack-argument leaf: map player index through `active_mob_ids` and restore the player's MOB picture from `tport_saved_picture[player]` when transporter movement completes |
| 0x5214C | `player_add_score_with_mult` | Add score × bonus multiplier to player's score |
| 0x41BF0 | `player_try_move` | Core collision-checked movement function |
| 0x42648 | `tile_lookup_core` | Read mob_picture[d1], compute distance, set carry flag if occupied |
| 0x4260C | `probe_down` | Boundary check + (Y−0x40) neighbor via tile_lookup_core |
| 0x425D0 | `probe_up` | Boundary check + (Y+0x40) neighbor via tile_lookup_core |
| 0x4270C | `probe_right` | Check tile at (X+2) via tile_lookup_core |
| 0x426D4 | `probe_left` | Check tile at (X−2) via tile_lookup_core |
| 0x42744 | `squeeze_through_check` | Test pass-through flag, tile type, and corner geometry |
| 0x406B6 | `mob_probe_up` | Register-preserving leaf probe: test the cell one row above and its two horizontal neighbors; return the first blocking MOB slot or -1 |
| 0x40732 | `mob_probe_down` | Mirrored leaf probe for the row below and its two horizontal neighbors |
| 0x4083A | `mob_probe_left` | Leaf probe for the cell to the left plus its two vertical neighbors |
| 0x408A0 | `mob_probe_right` | Mirrored leaf probe for the cell to the right plus its two vertical neighbors |
| 0x407A6 | `mob_probe_candidate` | Shared BSR-only helper for the four directional probes: reject an empty candidate, compute wrapped horizontal/vertical separation for an occupied cell, store signed/absolute deltas at 0x904024–0x90402A, and return the distance comparison in condition codes |
| 0x4FEB2 | `corner_squeeze_geometry` | Test wall corner shape for diagonal squeeze-through |
| 0x4280E | `door_traverse_right` | Ray-march rightward via ray_march_right; spawn passage marker |
| 0x428A4 | `door_traverse_left` | Ray-march leftward via ray_march_left |
| 0x4293A | `door_traverse_up` | Ray-march upward via ray_march_up |
| 0x429D0 | `door_traverse_down` | Ray-march downward via ray_march_down |
| 0x5E35E | `ray_march_right` | Scan rightward: 3 neighbors, distance test in X/Y |
| 0x5E2A2 | `ray_march_left` | Mirror of ray_march_right but column-- |
| 0x5E1D8 | `ray_march_up` | Scan upward: 3 neighbors (center/left/right) |
| 0x5E10C | `ray_march_down` | Mirror of ray_march_up but row-- |
| 0x414A4 | `monster_update_anim_tile` | Inline sub-function in `monsters_everything`: reads direction from high byte of `mob_anim[mob]`, masks to 6-bit counter+direction index, looks up tile from per-type animation table (via pointer at `0x40DB2`), writes to `mob_picture`. Called after every monster move. |
| 0x427B4 | `failed_door_post` | Compute tile position and update MOB display after failed door traversal |
| 0x5DE44 | `update_mob_backlinks` | Patch prev/next pointers; fix bucket chain; update `0x9049DE` |
| 0x5DED4 | `moblist_unlink_regs` | Register-state unlink entry used by `moblist_remove`: repair forward/back links and list heads, then preserve the removed slot's upper object-state bits rather than clearing its five array words |
| 0x49DE6 | `player_death_sequence` | Per-frame death/name-entry handler; decrements the reused `player_state_timer` countdown |
| 0x54FE8 | `player_enter_animation` | Per-frame entry animation (player swirling in) |
| 0x50E34 | `player_check_pickups` | Detect player standing on items (food, keys, etc.) |
| 0x47FAC | `award_walk_bonus` | Award bonus score for walking distance milestone |

---

## 5. Maze / Level System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x40C78 | `find_maze` | Look up maze data pointer and slapstic bank by maze number |
| 0x44AC2 | `maze_setupnew` | Full maze initialization: decode + place MOBs |
| 0x4C1BC | `maze_decode` | Decompress RLE-encoded maze data into playfield RAM |
| 0x45E40 | `maze_place_object` | Dispatch function: create all maze objects (walls, monsters, items) |
| 0x43F68 | `maze_addrandompickups` | Add random pickups based on maze header and difficulty |
| 0x42E9A | `maze_randomplace` | Place a tile-type object at a random empty floor tile |
| 0x4526A | `maze_show` | Clear alpha layer to reveal the level |
| 0x4529A | `maze_hide` | Fill alpha layer to hide the level |
| 0x452D0 | `setup_infopanel` | Set up right-side info panel (names, health bars, inventory) |
| 0x462AE | `dragon_reserve_footprint_cell` | Mark one of the dragon's three secondary 2×2 maze cells with hidden picture 0x8002, computed H/V coordinates, and link word 0xF000 |
| 0x4631C | `maze_tile_write_at` | Register/position wrapper used by maze placement to write or update the selected tile cell |
| 0x52ECA | `maze_checknum` | Validate/wrap maze number; handle end-of-game wraparound |
| 0x4BE24 | `level_splash` | Display new-level splash screen |
| 0x438AE | `maze_new_level_setup` | New level initialization hub (reset thief, switch slapstic bank, setup maze, etc.) |
| 0x436FE | `maze_load_pickup_config` | Read pickup-config bytes, assemble into `maze_pickup_config`, apply random flags |
| 0x436CC | `get_random_maze_flags` | Select random entry from 13-entry ROM table (0x57012) for level randomization |
| 0x43D8C | `maze_scan_objects` | Multi-mode maze object scanner (formerly `maze_food_mob_consume`): counts exits / player starts / food, implements EXIT_CHOOSEONE + fake-exit marking, clears EXIT_MOVES when one exit remains |
| 0x43826 | `slapstic_cmd_bitwise` | Issue bank-switch command sequence to Slapstic chip |
| 0x56E58 | `slapstic_cmd_bank0` | Switch to slapstic bank 0 |
| 0x56E6E | `slapstic_cmd_bank3` | Switch to slapstic bank 3 |
| 0x56E84 | `slapstic_cmd_bankX` | Switch to slapstic bank based on input |
| 0x56E90 | `slapstic_cmd_maze_init` | Register-argument Slapstic sequence used only by `maze_init`: reset at 0x38000, then copy the word at A0 to A1 through the shared 0x56E54 tail |
| 0x56E98 | `slapstic_cmd_bankX_special` | Register-argument Slapstic sequence used by `maze_select_bank_special`: accesses 0x38000, 0x3FB4A, then 0x38010 plus the selected bank offset |
| 0x56EAA | `slapstic_verify` | Verify slapstic is responding; returns 0x1FFFE if good |
| 0x46C5E | `scroll_to_slot` | Convert MOB slot to scroll coords; center viewport on that tile |
| 0x46F56 | `set_scroll_pos` | Set playfield H/V scroll registers |

---

## 6. Transporter / Forcefield System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x47CFE | `handle_tport` | Player touching transporter: create explosion anim, hide player |
| 0x47C0E | `tport_cycle_start` / `spawn_passage_marker` | Initialize transporter animation MOB at frame 0x924 |
| 0x47DAE | `shot_impact_spawn` | Spawns a shot-impact/explosion effect at the target's position using effect MOB slots 0xD–0xF (free slot found via 0x90201A/1C/1E). Called throughout `resolve_shot_hit`. (Formerly listed as `tport_cycle_update`/`spawn_explosion`.) |
| 0x4E7C0 | `tport_find_id` | Search tport_pos_table for entry matching given maze position |
| 0x50ADE | `tport_check_dest` | Validate potential transport destination |
| 0x5DF8E | `tport_create_splodey` | Create sparkle/explosion animation at teleport destination |
| 0x5FC5E | `pf_isff` | Check if given maze coordinate has a forcefield tile |
| 0x40528 | `main_cycle_tport_and_ffield` | Per-frame forcefield/transporter palette cycling |
| 0x53398 | `forcefield_segments_setup` | Scan FORCEFIELDHUB (type 0x3F) tiles, encode segment/graphic state in `mob_state_link`, and build the forcefield segment table at 0x910780 |
| 0x53346 | `check_forcefield_collision` | Test whether player is touching a forcefield |
| 0x52F26 | `maze_forcefield_setup` | Pack groups of four maze object types 7–9 into the spare-color byte table; clear the corresponding hidden marker MOBs and disable the level feature if none were present |
| 0x52FBE | `consume_forcefield_code` | Return code 1–3 for maze object types 7–9 and clear that marker's picture/position/link fields; return 0 for every other type |

---

## 7. Dragon System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x54454 | `main_handle_dragon` | Dragon state machine (sleeping/awake/stunned/turning/fire) |
| 0x549EA | `dragon_player_proximity` | Check if any player is in aggro range; start wake animation |
| 0x5496E | `dragon_setup_segments` | Derive and store all four 2×2 dragon segment MOB IDs from the primary cell and initialize dragon state/facing/movement/hit counters |
| 0x54748 | `dragon_fire_setup` | Fires one dragon fireball: sets fire cooldown (0x90487C) = 8, picks the origin segment MOB via table 0x5D4B8[pose+facing*2] from `dragon_seg_mob_ids` (0x904894), stores shot direction = facing |
| 0x53E4A | `dragon_choose_move_direction` | Compare the dragon with active players, test candidate maze cells, and update packed movement state/facing toward the best unobstructed direction |
| 0x53D10 | `dragon_update_segments` | Use the current path-program pose and facing to update the four dragon segment MOB positions/pictures |
| 0x540E8 | `dragon_find_free_shot_slot` | Scan dragon fireball slots 5 down to 1 and return the first whose `mob_picture` is zero (0 if none) |

---

## 8. Thief / Mugger System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x4DFF6 | `thief_target_calc` | Calculate player "wealth"; select wealthiest as thief target |
| 0x4E432 | `thief_setup` | Initialize thief MOB for the level |
| 0x4E4D8 | `thief_timer_set` | Calculate next thief appearance timer based on wealth and level |
| 0x4E1FE | `thief_steal_from_player` | Resolve contact with a player: choose and remove an inventory item/bonus multiplier (or inflict 100 health damage in mugger mode), update the HUD/dialog, and record the carried item |
| 0x4E684 | `tport_route_connect` | Add a directed transporter/pathfinding connection between two maze positions in the paired route tables at 0x905C54/0x905D54 |
| 0x4E73A | `tport_route_connect_if_empty` | Conditional form of `tport_route_connect`; adds the route only when the selected route-table entry has no existing high-nibble connection |
| 0x50FD2 | `path_grid_set_low_direction` | Leaf helper: address a 44-cell/0x80-byte padded row in the overlapping grid at 0x905054 and replace its low nibble with direction+1 |
| 0x51000 | `path_grid_set_high_direction_if_empty` | Leaf helper used by score/thief/movement paths: unless thief-mode bit 1 is set, install direction+1 in an empty high nibble while preserving the low nibble |
| 0x5103E | `path_grid_get_direction` | Leaf helper: read the high or low packed direction nibble selected by thief-mode bit 1; return direction 0–7 or invalid/unset value 8 |
| 0x5107A | `tport_route_write_pair` | Leaf helper: write forward and reverse 22-cell/0x80-byte padded route-table entries for two nonzero transporter IDs |
| 0x510BC | `tport_route_read_pair` | Leaf helper: read the selected forward/reverse route entries; with both IDs present the reverse entry supersedes the forward result, matching its route-building callers |
| 0x4E7FC | `thief_test_move_tile` | Validate the thief's next tile, including transporter entry, blocked-direction tests, and corner-squeeze handling |
| 0x4EE0A | `thief_probe_axis` | Invoke a directional tile-probe callback, reject blocked/colliding results, and apply the supplied coordinate delta to the thief MOB |
| 0x4F5C8 | `thief_remove_and_drop_loot` | Remove the thief/effect MOBs, award 500 points when appropriate, restore route state, and respawn carried loot at the departure tile |
| 0x4F742 | `thief_handle_tile_collision` | Handle thief contact with players, shots, obstacles, and transporter tiles; applies contact damage and returns whether movement is blocked |
| 0x4FAD4 | `thief_enter_tport` | Select the linked transporter destination and route direction for the thief, then start the transporter transition when the destination is usable |
| 0x4FBFC | `thief_start_tport_anim` | Hide/remove the thief at a transporter, create its transition MOB, record source/destination state, and start the teleport sound/animation |
| 0x4E122 | `thief_exit` | Thief departure: animate exit, remove MOB, schedule next appearance |

---

## 9. Exit System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x52B06 | `exit_get_id` | Look up exit's MOB slot from exit position table |
| 0x52B40 | `player_exit_sequence` | Player exiting state machine; advance to next level when all done |
| 0x5DF80 | `exit_create_player_anim` | Create player exit animation MOB |

---

## 10. Scoring / Coin / Dialog System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x42B6A | `coincheck` | Per-frame coin detection; handle player joining/coining |
| 0x40628 | `calc_score_per_coin` | Divide 32-bit value by 16-bit divisor for score-per-coin display |
| 0x49498 | `playfield_showscore` | Floating score popup over killed monster |
| 0x49D0E | `highscore_check` | Check if score ranks in top 10; set name-entry state |
| 0x4C440 | `dialog_first_encounter` / `player_hurt_flash` | First-encounter dialogs (bitmasked per encounter type) |
| 0x4C70A | `dialog_clear_message` / `fill_buffer_spaces` | Fill dialog message buffer with spaces then null terminator |
| 0x4C72A | `player_give_item_with_message` | Give power-up item; display associated dialog message |
| 0x4CB50 | `dialog_position_box` / `compute_screen_coords` | Position dialog box near player or at center |
| 0x4D476 | `show_continue_screen` | "PRESS START WITHIN X SECONDS TO CONTINUE" — shown when all players die (verified: clears alpha screen, coin-eligibility check 0x4D1A4, calls `player_activecount`, `secret_getname`; epilogue at 0x4D8DC calls `secret_check` and advances maze/level). GAME_ROM_KNOWN.md's "treasure room exit" description was wrong |
| 0x4A124 | `attract_highscores` | Shows 4-way-split high-score-per-coin attract screen |
| 0x44C7E | `update_maze_player_count` | Decrement active player count (0x904928); trigger all-dead state; called from `player_death_sequence` (0x49DE6). **Not** `show_continue_screen` (that is 0x4D476) |

---

## 11. Secret Room System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x486FE | `secret_check` **(RESOLVED)** | Level-transition secret-room bookkeeping: if a player entered the secret room, `secret_prev_maze` = maze# and interval 0x90487A += 15 (max 40); if nobody did, −2 (min 4); countdown 0x904878 reloaded. Called from `main_start_game` (0x480EC) and the `show_continue_screen` epilogue (0x4D8DC). `update_bgm_volume` refuted (no sound state touched) |
| 0x54EC6 | `secret_getname` **(RESOLVED)** | Secret-room winner name-entry setup, gated by EEPROM settings bit 13: name buffer 0x904AA4 = 'A'+spaces, `player_status` = 0x20, draws "ENTER YOUR" / "'LAST-NAME FIRST-NAME'"; bit clear → status 2, short delay. `reset_attract_player` refuted |
| 0x54BE0 | `secret_code_build` | Build the six-character `XXX-XXX` secret code in `dialog_msg_buf`: CRC-CCITT-hash the entered name while skipping spaces, interleave three hash symbols with three symbols encoding the previous maze/trick/challenge tuple, and map 5-bit groups through the alphabet at 0x54CA6 |

---

## 12. MOB (Sprite) Management

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x5DC58 | `mob_create` | Install a MOB into hardware VRAM arrays; link into priority chain |
| 0x5DCBC | `moblist_insert` | Insert new item into MOB linked lists |
| 0x5DD72 | `moblist_replace` | Replace destination MOB with source; unlink original |
| 0x5DDA8 | `moblist_remove` | Remove MOB from linked lists |
| 0x5DDDA | `moblist_remove_and_clear` / `mob_unlink` | Remove MOB from all 5 arrays; zero the slot |
| 0x5E064 | `mob_remove` | Unlink MOB from doubly-linked lists; update camera/priority |
| 0x5DF9C | `mob_place_explosion` | Common depth-list placement entry for explosion/effect slots; biases the supplied logical slot by 1 before entering the shared sorter at 0x5DFA6 |
| 0x5DFA6 | `insert_mob_depth_sorted` | Shared body used by the 0x5DF5A–0x5DF9C placement entries; insert the selected MOB into the Y-bucket/depth-sorted display chain and repair forward/back links |
| 0x5E57E | `tile_on_screen_d4` | Register-argument entry to the tile visibility test: packed maze position is already in D4; shares the body at 0x5E58C |
| 0x5E584 | `tile_on_screen_test` | Stack-argument entry to the same visibility test; loads packed maze position into D4 before the shared body |
| 0x5E5D2 | `tile_near_screen_d4` | Register-argument entry to the second, wider playfield visibility predicate used by cyclic walls; packed maze position is already in D4 |
| 0x5E5D8 | `tile_near_screen_test` | Stack-argument entry to the wider predicate. `dragon_any_segment_near_screen` loads this address into A2 and calls it indirectly for all four dragon segments. |
| 0x5E7A6 | `maze_place_object_types` | Stack-argument leaf: scan MOB slots for the supplied maze-object type or type−3, optionally require proximity to the screen, stamp every match into the playfield, and return whether any match existed |
| 0x5E80C | `maze_convert_walls_to_exits` | No-argument leaf called at the escape timeout: convert eligible wall markers (excluding forcefields) to exit type 0x10 and return whether anything changed |
| 0x5E542 | `pf_stamp_update_regs` | Register-argument entry to the 2×2 descriptor stamper: D0=packed maze position, A0=four-word descriptor, A1=palette/base addend; shared body of `pf_stamp_update` |
| 0x5EA66 | `pf_is_connectable_floor_xy` | Register-argument neighbor predicate used while choosing floor connectivity: returns 0xFF for an empty/connectable cell and 0 otherwise, accounting for forcefields and level flags |
| 0x5FC56 | `pf_isff_d0` | Register-argument forcefield query entry with packed maze position already in D0; shares the body of stack-argument `pf_isff` at 0x5FC5E |
| 0x5DE0A | `copy_mob_slot` | Copy 5 VRAM arrays from source slot to destination |
| 0x5DE44 | `update_mob_backlinks` | Patch prev/next pointers; fix bucket chain |
| 0x5DED4 | `moblist_unlink_regs` | Non-clearing register entry used by `moblist_remove`; shares the unlink algorithm but leaves the slot data intact apart from clearing link indices |
| 0x5DF5A | `mob_place_tport_anim` | Common depth-list placement entry for transporter animation slots; biases the supplied logical slot by 0x0D |
| 0x5DF68 | `mob_place_shot` | Common depth-list placement entry for shot MOB slots; uses the supplied slot without a bias (also used for dragon fireballs) |
| 0x5DF72 | `mob_place_anim` | Common depth-list placement entry for general animation slots; biases the logical slot by 0x11 |

---

## 13. Playfield (Tile) System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x5F31E | `pf_replace` | Replace tile at given slot with new type; handle MOB/graphics update |
| 0x5E892 | `pf_floor_update` | Update floor/wall tile graphics at given position |
| 0x5E536 | `pf_stamp_update` | Update a 2×2 stamp on playfield (e.g., exit open/close animation) |
| 0x5F77A | `pf_isdoor` | Returns door class from picture word: 1 = connectable segment (pics 0x9D18–0x9D3B), 2 = pics 0x9D3C–0x9D7B, 3 = pics 0x9D7C–0x9DAC, 0 = not a door (column x=0 always 0) |
| 0x5F772 | `pf_isdoor_stack` | Stack-argument wrapper used by the vertical/horizontal door-endpoint scanners; loads X/Y into D0/D1 and falls through to `pf_isdoor` |
| 0x5F7FA | `pf_door_update_surrounding` | Redraws the 4 neighbors of a changed tile if they are doors (register-args entry at 0x5F7F0 = `pf_door_update_surrounding_xy`) |
| 0x5F5A0 | `refresh_tile_visual` | Dispatch on tile type → select descriptor → write to VRAM (fully traced — see `05_data_reference.md` §5 descriptor tables; floors offset tile codes by floorpattern×0x30, walls use per-pattern blocks + 8-neighbor connectivity) |
| 0x5E542 | `write_tile_descriptor` / `pf_stamp_update` | Write 4-word 2×2 tile descriptor to playfield VRAM |
| 0x5F876 | `pf_door_draw_xy` | Register-args entry (a0=x, a1=y, d0=door type) into `pf_door_draw` |
| 0x5F880 | `pf_door_draw` | Door tile graphic updater (860 B, was `fcn_5F880`): adjacent-door mask → picture table 0x5F9CE; isolated type-2/3 doors oriented by surrounding floor; stores mask in bits 10–13 of `0x904066[tile]` |
| 0x5EA2E | `pf_isblankfloor` | Returns 0 iff tile picture == 0x8000 AND link type == 0x3F (plain floor) |
| 0x5E888 | `pf_floor_draw_xy` | Register-args entry into `pf_floor_update` (0x5E892); floor descriptor from 0x5BAE0, tile code += floorpattern×0x30 |
| 0x5E868 | `maze_special_floor` | No-argument setup leaf used only for wall patterns 6 and 11: scans all 1024 playfield/MOB picture words and converts every special-floor marker 0x8003 to ordinary floor 0x8000; returns with no result |
| 0x5EA00 | `maze_floor_decor` | No-argument 32×32 initialization pass: calls the register-entry `pf_floor_draw_xy(x,y)` for every maze cell, preserving D2–D3 and returning after exactly 1024 draws |
| 0x5EA26 | `pf_isblankfloor_stack` | Unreferenced stack-argument wrapper retained in the shipped code: loads `(x,y)` words from 6(A7)/10(A7) and falls through to register-entry `pf_isblankfloor` at 0x5EA2E |
| 0x5F2C0 | `maze_init_walls` | No-argument 32×32 wall-render pass. Unless level-flags byte 2 bit 7 suppresses it (except level 9999), draws cells whose picture is 0x8000 or 0x8003 through `pf_wall_draw_xy`; preserves D2–D3/A2 |
| 0x5F7C0 | `maze_doors_setup` | No-argument initial door-render pass over x=1..31 and y=0..31. Calls `pf_isdoor`; for each nonzero door type, passes x/y in A0/A1 and the type in D0 to `pf_door_draw_xy` |
| 0x5F024 | `wall_place_playfield_update` | Place wall tile; compute 2×2 descriptor; propagate to neighbors |
| 0x5F310 | `mob_place_tile` | Place tile; remove old MOB; update visuals |

---

## 14. Utility Functions

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x5FC4E | `getrandom` / `rand_n` | LCG random: returns value in [0, N). Stack-based. Seed at 0x904BFC |
| 0x5FC46 | `random_word` / `getrandom_r` | Register-based variant of getrandom |
| 0x5FD58 | `memclear` | Clear `count+1` longwords at ptr using DBRA loop |
| 0x5FD6A | `memcpy` / `copy_longwords` | Copy `count+1` longwords from src to dst |
| 0x5FD80 | `palette_fade_copy` | Copy word array from src to dst, subtracting delta; handles 12-bit color overflow |
| 0x5FD14 | `display_state_clear` | Clear MOB-list bucket state, reset scroll and first MOB fields, then clear alpha/playfield VRAM through the register-count memory-clear core |
| 0x5FD64 | `memclear_core` | Register-argument DBRA core used by display clearing: A0=destination and D0=count, clearing `count+1` longwords |
| 0x45BE8 | `stridx` / `strlen` | Pointer to string → offset of next null byte (string length) |
| 0x510FC | `calc_direction` | Compute direction (0–7) from source to destination position |
| 0x511AC | `player_tile_interact` / `tile_occupant_interact` | Dispatch by tile type: food/key/enemy/portal/chest handlers |
| 0x49B44 | `ascii_to_alpha_glyph` | Convert name-entry ASCII/control characters to the alpha-layer font code: A–Z→0x0A–0x23, digits→0–9, selected punctuation→0x24/0x27–0x2C, backspace→0x32, default→0x25 |
| 0x4D12E | `alpha_clear_rect` | Clear a rectangular region of alpha VRAM; arguments are column, width, row, and height |
| 0x5554E | `name_entry_step_char` | Increment/decrement and wrap a name-entry character through space, A–Z, and optional backspace |
| 0x555C4 | `name_entry_draw_char` | Draw one name-entry character with OS 0x218, translating backspace to glyph 0x3B and conditionally hiding spaces during the cursor-flash palette phase |

---

## 15. Sound Functions

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x4AD76 | `sound_play` / `play_sound` | Enqueue sound ID into 8-slot circular ring buffer |
| 0x4AD4E | `sound_speech_play` / `play_sound_mute_guarded` | Like play_sound but check mute flag first |

---

## 16. Shot / Combat Functions

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x41B16 | `find_unused_shot` | Scan shot MOB array for slot with mob_picture == 0 |
| 0x490DC | `monster_create_shot` | Create a monster shot MOB; link into shot list |
| 0x53666 | `player_create_shot` | Create a player shot MOB |
| 0x4AF50 | `resolve_shot_hit` | Full combat resolution for all target types (~0xED4 B, fully analyzed — see `04_game_subsystems.md` §30): `(target, shooter) → 0` shot survives / `-1` shot consumed; computed JMP 0x4B336 with table 0x4B338–0x4BB3; damage tables 0x596B6/0x596C2/0x596CE; monster tier system, generator degradation, secret-wall prizes, supershot/reflect |
| 0x40906 | `shot_mob_collision` | Bounding-box collision test for shot projectiles |
| 0x52192 | `mob_collision_test` | Bounding-box overlap + type dispatch for combat/pickup/warp |
| 0x47DAE | `shot_impact_spawn` | Spawns impact/explosion effect at target position in effect MOB slots 0xD–0xF |
| 0x4AEA0 | `shot_onscreen_check` | Range/visibility check vs scroll registers 0x904026/28; gates door reactions to shots |
| 0x53818 | `shot_reflect_calc` | Computes the reflected direction when a reflect-power shot hits a wall (result → `0x9049C4[player]`) |
| 0x5303A | `wall_crumble` | Applies shot damage to a destructible wall (called from `resolve_shot_hit` with (target, damage)) |
| 0x54112 | `dragon_shot_hit` | Dragon damage handler: hit counts only while breathing fire and not sleeping/turning; 9th hit kills; on hit picks a new random path program with pose-matched fast-forward |

---

## 17. OS ROM API Calls (address < 0x10000)

See `02_os_rom.md` for full descriptions. Summary table:

| API Address | Name | Args | Return |
|-------------|------|------|--------|
| 0x100 | `start_scroll_text` | (text_desc_ptr, speed, color) | d0 = 1 if started |
| 0x106 | `format_decimal` | (value, buf_ptr, width, leading_zeros) | void |
| 0x10C | `format_hex` | (value, buf_ptr, width, uppercase) | void |
| 0x112 | `format_number` | (buf_ptr, format_char, ...) | void |
| 0x14E | `init_alpha_display` | () | void |
| 0x154 | `wait_vblanks` | (count: word) | void |
| 0x15A | `process_sound` | () | void |
| 0x160 | `calc_health_per_coin` | (player_index: long) | d0 = health value |
| 0x166 | `check_and_deduct_coin` | (player_index: long) | d0 = 1 if success |
| 0x16C | `process_coins` | (coin_byte1, coin_byte2) | void |
| 0x172 | `send_sound_command` | (cmd: word, callback, param: byte) | d0 = 1 if sent |
| 0x17E | `send_sound_immediate` | () | void |
| 0x184 | `eeprom_check_busy` | () | d0 = 1 if busy |
| 0x18A | `eeprom_process` | () | void (called every VBLANK) |
| 0x190 | `eeprom_init` | () | void |
| 0x196 | `eeprom_request_write` | (region_index: long) | void |
| 0x19C | `process_coin_stats` | (player_index: word, stat: word) | void |
| 0x1A2 | `read_eeprom_setting` | (category: long, index: long) | d0 = byte |
| 0x1A8 | `read_game_config` | (item_index: long) | d0 = long |
| 0x1AE | `read_high_score_entry` | (class: word, rank: word) | d0 = ptr |
| 0x1B4 | `write_high_score_entry` | (class, rank, data_ptr) | void |
| 0x1BA | `get_eeprom_base` | () | d0 = ptr |
| 0x1C0 | `write_eeprom_setting` | (category, value) | void |
| 0x1C6 | `read_eeprom_config` | () | d0 = ptr |
| 0x1CC | `write_eeprom_config` | () | void |
| 0x1D2 | `run_self_test` | () | void |
| 0x200 | `display_large_text` | (text_desc_ptr) | d0 = pixel width |
| 0x218 | `write_alpha_char` | (row, col, char, color) | void |
| 0x224 | `calc_alpha_address` | (row, col) | d0 = address |
| 0x230 | `check_credits` | (required: long, player: long) | d0 = 1 if sufficient |
| 0x236 | `get_coin_multiplier` | () | d0 = multiplier |
| 0x23C | `disable_interrupts` | () | void |
| 0x242 | `enable_interrupts` | () | void |
| 0x24E | `eeprom_read_block` | (dest_buf, block_index, mode) | void |
| 0x254 | `reset_sound_cpu` | () | void |
| 0x25A | `draw_string` | (row, col, string_ptr, color) | d0 = chars written |
| 0x260 | `display_decimal_value` | (desc_ptr, color) | void |
| 0x266 | `display_hex_value` | (desc_ptr, color) | void |

---

## 18. Shared Functions Registry (cross-subsystem)

These functions are called from multiple top-level subsystems:

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x42DC8 | `sound_system_reset` | Flush sound ring buffer, reset speech counter, send HW reset |
| 0x4C9A2 | `demo_speech_cmd` | Process 0xFF speech command in demo input stream |
| 0x48BEC | `player_start_inner` | Find tile, set up sprite, link MOB (called from player_start_in_maze) |
| 0x48F12 | `tile_occupancy_test` / `check_tile_passable` | Check candidate tile for other players within 0x7C0 px; bounds + occupancy + proximity |
| 0x55440 | `next_anim_frame` | Animation state machine for player enter/death sequences |
| 0x4A44A | `update_sprite_tile` | Compute final tile index; write to display list entry |
| 0x554B6 | `schedule_sprite_update` | Look up tile attributes; call OS 0x218 to write sprite tile |
| 0x4E630 | `erase_mob_old_pos` | Compute tile-map index; write blank at old position |
| 0x4DE76 | `score_screen_color_cycle` | Every 16th frame: saves 4 words from 0x910140 area, shifts 11 color RAM entries one slot, writes saved words back to start — creates scrolling rainbow on high-score text |
| 0x4D956 | `scroll_apply` | Apply scroll delta for title-screen animation. Both deltas zero → writes 0x75 to 5 scroll anchor slots at 0x9038DE (stride 0x24). Non-zero → walks MOB list for scroll anchor tiles (picture in range 0x2700–0x2728) |
| 0x4DA3E | `title_logo_init` | No-argument TITLE initializer: build the multi-row logo MOBs, initialize brightness/color and full/short motion-program state, then start the logo off-screen with `scroll_apply(-128, 0)` |
| 0x449D4 | `attract_demo_init` / `demo_setup` | Initialize demo level for DEMO attract screen; sets up Elf player 1 |
| 0x40D24 | `load_level_tileset` | Load level tile data into VRAM |
| 0x4CD1C | `load_demo_level` | Load demo level for attract mode |
| 0x44DB4 | `show_level_start_screen` | Build the between-level/start display; after a secret-room win, replace the maze trick ID with a random 0x50–0x5D challenge task, set its timer, and show its qualifier |
| 0x40CF2 | `maze_init` | Maze initialization (called from main_start_game) |
| 0x4FCF0 | `find_richest_player` | Find player with highest item value (for thief targeting) |
| 0x4EE7A | `thief_move_engine` | Core thief movement/direction computation |
| 0x4F912 | `thief_compute_path` | Compute the thief's next maze position/direction, including diagonal alternatives and passability tests |
| 0x4E1B8 | `mark_item_stolen` | Mark item stolen in theft tracking |
| 0x4E172 | `abort_theft` | Abort current theft sequence |
| 0x43192 | `eeprom_write` | Copy 6 monitored values to write buffer; flush via OS 0x24E |
| 0x4ADAE | `sound_queue_reset` | Fill ring buffer with 0xFF; zero read/write heads |
| 0x45940 | `draw_player_score` | Draw the player's 7-digit SCORE (`player_score` 0x904990[p]) via OS `display_decimal_value` (0x260) at row p*5+9, using the flash attribute at 0x57350[p], then clear `player_redraw` bit 0. The former `draw_player_name`/`flash_score_display` names were misleading. |
| 0x459A2 | `draw_player_health` | Draw bonus multiplier “×N” when greater than one and the player's 5-digit HEALTH value; apply low-health/acid palette dimming and clear `player_redraw` bit 1. This is numeric HUD rendering, not a health bar or lives display. |
| 0x4A2CA | `draw_player_game_over` | Renders "GAME OVER" banner with class graphic; called from `player_cleanup_slot` |
| 0x54AF8 | `dragon_any_segment_near_screen` | Test the dragon's four segment positions with the indirect stack entry at 0x5E5D8; returns -1 when any segment is within the wider playfield window and 0 otherwise. Used by the potion handler's dragon-effect path. |
| 0x4D1A4 | `check_coin_eligibility` | Check DIP switches and player state to determine if player can continue; called from `show_continue_screen` |
| 0x489B8 | `remove_dying_player_sprites` | Remove sprite slots for dying player; called from `show_continue_screen` |
| 0x50B88 | *(score animation phase)* | Score animation phase handler |
| 0x4119A | `monster_special_handler` | Sorcerer teleport/acid spread/IT chase logic |
| 0x40FAE | *(monster walk loop body)* | Per-MOB iteration body within monster_loop_core |
| 0x46F56 | `scroll_set_position` | Apply scroll X/Y to hardware registers with clamping |
| 0x41B7E | `apply_direction_from_delta` | Compute direction code from dx/dy between MOBs |
| 0x40A78 | `shot_collision_candidate_core` | BSR-only candidate evaluator used by `shot_mob_collision`: reject empty/self/out-of-range slots, handle wrapped MOB coordinates, update signed/absolute separation scratch words, and return the candidate type/result in D2 |
| 0x41B52 | `monster_shooter_in_view` | BSR-only viewport gate before a monster fires: compare its byte-scale H/V coordinates with the culling origins; return D4=-1 when inside the allowed rectangle and zero otherwise |
| 0x41C30 | `player_try_move_core` | Internal register-state reentry for `player_try_move`; initializes the active player's MOB slot/coordinates and runs the directional collision/door/squeeze logic. Several branches BSR here to retry movement. |
| 0x42598 | `mob_collision_test_preserve_d1_a` | First of two byte-identical leaf wrappers: convert doubled MOB offsets D1/D5 back to slot IDs, call `mob_collision_test`, restore D1, and return its boolean in condition codes |
| 0x425B4 | `mob_collision_test_preserve_d1_b` | Second byte-identical copy of the D1-preserving `mob_collision_test` wrapper, reached by the alternate movement branches |
| 0x5E888 | `wall_remove_playfield_update` / `refresh_floor_visual` | Refresh floor visual after wall removal |
| 0x5EAB8 | `pf_wall_draw` (aka `refresh_wall_visual`) | Draws a wall tile: 8-neighbor connectivity mask → variant table 0x5EE24 (0x5EF24 for patterns 6/0xB); descriptor base by `wallpattern` (0–5: 0x5BBE0 + offsets 0x5EDD4; 6: 0x5D2F8; destructible ≥6: 0x5D3D0; 7+: random of 6 sets at 0x5EDF4); register entry 0x5EAB8, stack entry 0x5EAC2 |
| 0x4ADD6 | `enqueue_sound` | Low-level sound ID enqueue into ring buffer at 0x90404B; called by play_sound |
| 0x40CC4 | `maze_select_alt_bank` | Call `find_maze`, switch the Slapstic through the alternate bank-selection path, and store the resulting command offset at 0x904B8C. It does not clear maze state. |
| 0x40D4E | `maze_select_bank_special` | No-prologue callable bank-selection path used by `show_level_start_screen` and `main_start_game`; calls `find_maze`, executes the 0x38000/0x3FB4A/selected-bank Slapstic sequence through 0x56E98, and stores D1 at 0x904B8C |
| 0x54B68 | `dragon_shot_hitbox_adjust` | Register-argument leaf called only from `shot_mob_collision` after the candidate type is 0x3C: reset dragon escape/idle timers, test the moving head hitbox using the five-word padded offsets at 0x54BD6, and add 0x1000 to D0 when the shot overlaps the head |
| 0x449CC | `attract_noop_hook` | Deliberate empty routine called once at the end of the attract-screen timer/display update path |
| 0x48B58 | `update_monster_bonus_from_score_per_coin` | Sum active players' scores and inserted-coin counts, then add `(total_score >> 14) / total_coins` to the signed monster-cap bonus byte at 0x90405F |
| 0x4CDB8 | `draw_legend_monsters_page` | Render legend sub-page 1: “MONSTERS”, monster names, and their Fight/Shoot/Magic attributes |
| 0x4CFAE | `draw_legend_overview_page` | Render legend sub-page 0 from the two formatted text records at 0x5A99C and 0x5AB0E |
| 0x4CFDA | `draw_legend_rules_page` | Render legend sub-page 2: adjust its decorative MOBs, clear label rectangles, and draw the formatted rule/item text records |
| 0x50BB8 | `scan_move_path_interactions` | Repeatedly call a directional neighbor probe and resolve each encountered interior MOB/tile until the probe fails or the path is blocked |
| 0x50C7A | `resolve_move_tile_interaction` | Resolve a traversed tile; recurse through player-start markers, remove disposable markers, and invoke thief/exit cleanup for exit tiles |
| 0x50D14 | `nearby_mob_clearance_test` | Scan the eight neighboring maze cells and reject candidates with a live, sufficiently aligned MOB within the requested edge clearance |
| 0x51E80 | `door_record_endpoints` | Classify a door picture and populate one two-ended door record in 0x904A76 (positions) and 0x904A86 (endpoint direction codes) |
| 0x51FAE | `door_scan_vertical_endpoints` | Extend a door record through matching doors immediately above/below the starting cell; returns the next free endpoint index |
| 0x5207C | `door_scan_horizontal_endpoints` | Horizontal mirror of `door_scan_vertical_endpoints`, scanning left/right |

---

## 19. Detailed Shared Function Behaviors

### `start_attract_screen` — 0x44414

Sets `game_mode` (0x904918) to arg value. Calls OS 0x14E (hardware init). If dialog timer > 0: sets to 1 and calls `speech_countdown_flush`. Plays sounds 0x1 (silence) + 0x3C (music fade-out). Clears level counter (0x904000=0, 0x904004=1). Calls `pf_palette_clear` (0x5FCCE) and `player_resetall` (0x4341E).

Dispatch by mode:
- **TITLE (-2):** timer = 0x5DD (25 sec). Calls `load_attract_display_tilemap` (0x4438E) and 0x4DA3E. Every 13th title cycle: refreshes EEPROM settings via OS 0x1BA/0x236/0x1A8. If bit 14 of settings set and music counter zero: plays music 0x3B.
- **SCORES (-1):** timer = 0x258 (10 sec). Calls `attract_highscores` (0x4A124).
- **DEMO (-3):** timer = 0x1C20 (119 sec). Calls `demo_setup` (0x449D4), clears frame counter.
- **LEGEND (-4):** timer = 0x258. Calls `maze_hide` (0x4529A), draws legend art via `setup_infopanel` (0x452D0(-1)), loads demo level via 0x4CD1C.

### `start_attract_to_game` — 0x44204

Transitions from attract to gameplay. Clears level (0x904000=0). Flushes speech, clears damage flags (0x90487E=0, 0x9049E4=0). If DEMO mode: clears display. Plays sound 0x3C (music fade). Sets `game_mode=0` (NORMAL), level=1.

Initializes continue system: `0x904BB4/0x904BAC = 0x7D30` (default pointers), `0x904BB0/0x904BA8 = 0`. Calls OS 0x14E. Plays sound 0x2 ("Noisy"). Clears playfield via `maze_hide`, builds the level-start/challenge display via `show_level_start_screen` (0x44DB4), and sets up the maze via 0x438AE.

Loops 4 players: draws character tiles to HUD via OS 0x25A using ROM tables at 0x57340, 0x570B8, 0x570B4, 0x570CC, 0x570BC, 0x570DC, 0x570C4. Loads main tilemap via OS 0x200 from ROM 0x5709A (0x8C00 bytes). Initializes palettes via `init_display` (0x43486) with the main/special palette selectors at `0x904B58`/`0x904B5A`. Sets attract timer to -1.

### `init_display` — 0x43486

Args: `(main_palette_index: word, special_palette_variant: word)`. Initializes color palettes; it does not consume scroll coordinates. The normal values are the high and low nibbles of maze header byte 6. A main index of 0x10 selects the fixed palette block at 0x5AC5E instead of the normal 16-entry bank.

Waits for VBLANK by testing bit 3 of hardware port `0x803009`, then spinning on VBLANK semaphore at `0x904002`. Copies two overlapping 33-longword ROM views at `0x5AD1E` and `0x5AD9E` to color RAM at `0x910000` (alpha palette) and `0x910100` (MOB palette) via `copy_longwords` (0x5FD6A). The count argument is 0x20, and the DBRA helper copies count+1 elements.

Level-dependent palette: if `0x904B5E < 6`, uses biased base `0x5D7E8`; otherwise it uses `0x5D7C8`. In both cases the second argument in D3 selects a 32-byte entry, so the effective source is `base + D3×32`. This is one four-entry bank with overlapping views, not fixed “palette A/B” objects at 0x5D7E8/0x5D828. Sets `0x904A4E` (countdown timer) and `0x904B7C` (attract timer). Clears `0x90486E` and `0x904AC6`.

### `eeprom_load_config` — 0x42F86

Spins on OS 0x184 until resource is available. Calls OS 0x24E to read EEPROM block into buffer at `0x904B8E`.

On first boot (result == 0xFFFE): initializes defaults — writes header bytes (0x05, 0x00, 0x68, 0x00), clears remaining fields, stores game_settings word (0x904A24), writes back.

Parses buffer: byte 0 → `0x904010` (level number, validated against slapstic ROM pointer table at 0x38000), byte 1 → `0x90400E` (difficulty bits & 7), byte 2 → `0x904018` (clamped to 0x68–0x72 range), byte 3 → `0x904016` (& 3), words 4–5 → `0x904B86` (stats, clamped to 0x7D0) and `0x904B94` (settings). Sets EEPROM write timer to 0x8CA0 (≈10 minutes).

### `palette_fade_copy` — 0x5FD80

Args: `(count, src, dst, delta)`. Copies a word array from src to dst, subtracting `delta` from each word. If result underflows, wraps around using 12-bit channel math: `result = (result & 0xFFF) | 0x1000`. This preserves the overflow/borrow bit used in the game's 12-bit-per-channel IRGB color encoding.

### `pf_replace` — 0x5F31E

Args: `(slot_index, new_tile_type)`. Replaces tile at given MOB slot with new type. Handles MOB list cleanup (calls `moblist_remove_and_clear` for old MOB), updates `vram.mob_picture` and `vram.mob_link`. **Special handling for tile types 2, 4–9** (walls and special objects): uses different code paths to preserve wall connectivity. Calls graphics update functions to redraw the affected tile.

### `pf_floor_update` — 0x5E892

Updates floor/wall tile graphics at a given row/column position. Reads current tile type from `vram.mob_link`, dispatches:
- Types 0x10/0x11: animated floor tiles → tables at `0x5C8A0` / `0x5C8A8`
- Type 0x3E: special floor → table at `0x5CAA8`
- Type 0x3F: floor with player-specific animation → state from `0x904066`, pointer table at `0x5BA70`
- Types 0xA–0xC: door tiles → flag value `0x1000`

Calls `pf_stamp_update` (0x5E542) to write tile data to VRAM.

### `write_tile_descriptor` — 0x5E542

Args: d0.w = packed tile position (bits 9:5 = column, bits 4:0 = row); a0 = pointer to 4-word sprite descriptor; a1.w = palette base. Computes VRAM address at 0x900000 for a 2×2 tile block. The sprite table at 0x900000 is **128 columns × 256 rows** of 2-byte entries. Writes 4 words from template at: `[slot+0]`, `[slot+0x80]`, `[slot+2]`, `[slot+0x82]`.

### `maze_scan_objects` — 0x43D8C *(formerly `maze_food_mob_consume` — corrected)*

Multi-mode maze object scanner over all 0x400 `mob_link` tiles. Modes by argument (object types are the §3.14 Maze Object IDs, not the old "food" readings):
- **arg=0:** count **EXIT** tiles (type 0x10). Implements EXIT_CHOOSEONE: keeps one randomly chosen exit (slot → 0x904A0A); the others become fake exits (hpos |= 0x10) when LFLAG4 bit 6 (EXIT_FAKE) is set, otherwise are replaced with floor via `pf_replace`. When only one exit exists, clears LFLAG3 bit 6 (EXIT_MOVES, long bit 14 of 0x90491C).
- **arg=0xFFFF:** count **PLAYERSTART** tiles (type 0xF).
- **arg=N (N≥1):** count **food** (types 0x31 FOOD_DESTRUCTABLE / 0x32 FOOD_INVULN) — used by the has-food logic. (This food-counting mode is what led to the original misnaming.)
