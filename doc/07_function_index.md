# Gauntlet II — Complete Function Index

*Consolidated index of all ~170 documented functions. Addresses are in the game ROM (0x040000–0x05FFFF) unless noted.*

*Note: Corrections from FIXME.md are applied inline with `> **Correction:**` callouts.*

---

## 1. Main Loop Functions (all DONE)

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x42A66 | `m2mainloop` | Main game loop entry point; VBLANK-synchronized frame dispatch |
| 0x44562 | `main_attract` | Attract mode state machine (SCORES→TITLE→DEMO→LEGEND) |
| 0x457C0 | `main_score_display` | Displays player scores on alpha layer |
| 0x45C00 | `main_open_doors` | Manages up to 8 concurrent door-opening animations |
| 0x4664C | `main_handle_death` | Handles Death monster behavior |
| 0x466F6 | `main_health_countdown` | Automatic per-frame health drain |
| 0x46CAA | `main_scroll_playfield` | Updates playfield scroll based on player positions |
| 0x46FEA | `main_handle_potions` | Per-frame potion usage processing for all 4 players |
| 0x4715E | `main_score_update` | Updates score accumulation and display |
| 0x474F6 | `main_handle_shots` | Per-frame shot projectile processing (12 slots) |
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
| 0x42F86 | `init_display_list` | Reads EEPROM, initializes display system/MOB list |
| 0x43486 | `init_display` | Sets playfield scroll + initializes color palettes |
| 0x44204 | `start_attract_to_game` | Transitions from attract mode to gameplay |
| 0x44414 | `start_attract_screen` | Sets up individual attract mode screens |
| 0x49BD0 | `init_monster_system` | Initializes monster/entity subsystem at startup |
| 0x431EE | `eeprom_timer` | 10-minute periodic EEPROM write timer |
| 0x42D0A | `sound_response` | Processes responses from sound CPU via OS API |

---

## 3. Monster System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x40E6A | `monsters_everything` | Entry point: per-frame monster AI, movement, shots, generators |
| 0x41750 | `monster_find_and_shoot` | Find nearest player, set direction, maybe shoot |
| 0x41B16 | `find_unused_shot` | Find empty shot MOB slot |
| 0x490DC | `monster_create_shot` | Create a monster shot MOB at monster's position |
| 0x492C0 | `monster_generic_handler` | Core AI/movement handler for standard monster types (ghosts, grunts, demons, lobbers, death). **Not** `handle_generate` — see `08_known_issues.md` item 1.1 |
| 0x49446 | `death_potion` | Handles Death being killed by a potion; AOE damage |
| 0x49498 | `playfield_showscore` | Displays floating score popup over dying monster |
| 0x495A6 | `monster_playerhit` | Monster overlapping player: apply damage, play sounds |
| 0x49A3C | `death_damagetrack` | AOE damage system; accumulates hit damage |
| 0x49A98 | `sound_player_hurt` | Plays appropriate hurt speech for player's character class |
| 0x5FDE0 | `supersorc_place` | Find empty spot behind player, place Super Sorcerer |
| 0x5FDB8 | `supersorc_place_helper` | Thin wrapper that loads MOB array base pointers then calls supersorc_place |

---

## 4. Player System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x43360 | `player_resetcounters` | Reset one player's counters (health, score unchanged, power-ups cleared) |
| 0x4341E | `player_resetall` | Reset all four player slots |
| 0x45866 | `player_it_set` | Set player as IT; copy IT punishment from ROM table |
| 0x4590E | `player_it_unset` | Clear IT status and restore normal attack params |
| 0x45ACA | `player_inv_update` | Update right-side inventory panel for all active players |
| 0x48754 | `speech_welcome` | Play "welcome <character>" speech for joining player |
| 0x487CA | `player_lowhealth` / `player_sound_sprite_update` | Plays heartbeat sound below health threshold; manages animation state |
| 0x488CA | `player_coindrop` / `player_init_for_coin` | Initialize player slot when a coin is inserted |
| 0x48A36 | `player_join2` | Handle player joining: pick character, init MOB, set state, speech |
| 0x48BB6 | `player_join` / `player_start_in_maze` | Outer join wrapper: validate slot, play join sound, call player_join2 |
| 0x49D0E | `highscore_check` | Check if player's score ranks in top 10 |
| 0x4D900 | `player_activecount` | Count players with state ≠ 0 (active gameplay) |
| 0x50224 | `player_tport` | Entry point when player touches a transporter tile |
| 0x50616 | `tport_player_flash` | Save MOB picture, set flash frame (0x1709) for transport visual |
| 0x50662 | `tport_player_move` | Full teleport state machine: find destination, animate, move |
| 0x5214C | `player_add_score_with_mult` | Add score × bonus multiplier to player's score |
| 0x41BF0 | `player_try_move` | Core collision-checked movement function |
| 0x42648 | `tile_lookup_core` | Read mob_picture[d1], compute distance, set carry flag if occupied |
| 0x4260C | `probe_down` | Boundary check + (Y−0x40) neighbor via tile_lookup_core |
| 0x425D0 | `probe_up` | Boundary check + (Y+0x40) neighbor via tile_lookup_core |
| 0x4270C | `probe_right` | Check tile at (X+2) via tile_lookup_core |
| 0x426D4 | `probe_left` | Check tile at (X−2) via tile_lookup_core |
| 0x42744 | `squeeze_through_check` | Test pass-through flag, tile type, and corner geometry |
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
| 0x49DE6 | `player_death_sequence` | Per-frame death/despawn animation handler |
| 0x54FE8 | `player_enter_animation` | Per-frame entry animation (player swirling in) |
| 0x50E34 | `player_check_pickups` | Detect player standing on items (food, keys, etc.) |
| 0x452D0 | `player_cleanup_slot` | Refresh HUD display for one player |
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
| 0x52ECA | `maze_checknum` | Validate/wrap maze number; handle end-of-game wraparound |
| 0x4BE24 | `level_splash` | Display new-level splash screen |
| 0x438AE | `maze_new_level_setup` | New level initialization hub (reset thief, switch slapstic bank, setup maze, etc.) |
| 0x436FE | `maze_load_pickup_config` | Read pickup-config bytes, assemble into `maze_pickup_config`, apply random flags |
| 0x436CC | `get_random_maze_flags` | Select random entry from 13-entry ROM table (0x57012) for level randomization |
| 0x43D8C | `maze_food_mob_consume` | Remove random food/treasure mob from active list |
| 0x43826 | `slapstic_cmd_bitwise` | Issue bank-switch command sequence to Slapstic chip |
| 0x56E58 | `slapstic_cmd_bank0` | Switch to slapstic bank 0 |
| 0x56E6E | `slapstic_cmd_bank3` | Switch to slapstic bank 3 |
| 0x56E84 | `slapstic_cmd_bankX` | Switch to slapstic bank based on input |
| 0x56EAA | `slapstic_verify` | Verify slapstic is responding; returns 0x1FFFE if good |
| 0x46C5E | `scroll_to_slot` | Convert MOB slot to scroll coords; center viewport on that tile |
| 0x46F56 | `set_scroll_pos` | Set playfield H/V scroll registers |

---

## 6. Transporter / Forcefield System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x47CFE | `handle_tport` | Player touching transporter: create explosion anim, hide player |
| 0x47C0E | `tport_cycle_start` / `spawn_passage_marker` | Initialize transporter animation MOB at frame 0x924 |
| 0x47DAE | `tport_cycle_update` / `spawn_explosion` | Per-frame transporter animation cycling (frames 0x924–0x95A); also used to spawn explosion animations |
| 0x4E7C0 | `tport_find_id` | Search tport_pos_table for entry matching given maze position |
| 0x50ADE | `tport_check_dest` | Validate potential transport destination |
| 0x5DF8E | `tport_create_splodey` | Create sparkle/explosion animation at teleport destination |
| 0x5FC5E | `pf_isff` | Check if given maze coordinate has a forcefield tile |
| 0x40528 | `main_cycle_tport_and_ffield` | Per-frame forcefield/transporter palette cycling |
| 0x53398 | *(unnamed)* | Build forcefield segment table from FORCEFIELDHUB objects |
| 0x53346 | `check_forcefield_collision` | Test whether player is touching a forcefield |

---

## 7. Dragon System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x54454 | `main_handle_dragon` | Dragon state machine (sleeping/awake/stunned/turning/fire) |
| 0x549EA | `dragon_player_proximity` | Check if any player is in aggro range; start wake animation |
| 0x54748 | `dragon_fire_attack` | Execute fire breath attack; create fire MOBs along attack vector |
| 0x53E4A | `dragon_move_update` | Update dragon position per frame; call `dragon_change_dir` if blocked |
| 0x53D10 | `dragon_change_dir` | Pick new dragon movement direction |
| 0x540E8 | `dragon_attack_check` | Decide whether dragon should fire this frame |

---

## 8. Thief / Mugger System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x4DFF6 | `thief_target_calc` | Calculate player "wealth"; select wealthiest as thief target |
| 0x4E432 | `thief_setup` | Initialize thief MOB for the level |
| 0x4E4D8 | `thief_timer_set` | Calculate next thief appearance timer based on wealth and level |
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
| 0x4D476 | `show_continue_screen` | "PRESS START WITHIN X SECONDS TO CONTINUE" — shown when all players die. **Correction:** Not `fcn_4d476` or "treasure room" — see `08_known_issues.md` item 1.3 |
| 0x4A124 | `attract_highscores` | Shows 4-way-split high-score-per-coin attract screen |
| 0x44C7E | `update_maze_player_count` | Decrement active player count; trigger all-dead state. **Not** `show_continue_screen` — see `08_known_issues.md` item 1.2 |

---

## 11. Secret Room System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x486FE | `secret_check` **(CONFLICT)** | **GAME_ROM_KNOWN.md:** Check if we should enter secret room. **FUNCTIONS_PLAN.md:** `update_bgm_volume`. See `08_known_issues.md` item 2.1. |
| 0x54EC6 | `secret_getname` **(CONFLICT)** | **GAME_ROM_KNOWN.md:** Set up name entry for secret room winner. **FUNCTIONS_PLAN.md:** `reset_attract_player`. See `08_known_issues.md` item 2.2. |

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
| 0x5DF9C | `insert_mob_depth_sorted` | Insert MOB into Y-depth-sorted display chain |
| 0x5E584 | `tile_on_screen_test` | Returns 0xFF if tile is within visible scroll window |
| 0x5DE0A | `copy_mob_slot` | Copy 5 VRAM arrays from source slot to destination |
| 0x5DE44 | `update_mob_backlinks` | Patch prev/next pointers; fix bucket chain |

---

## 13. Playfield (Tile) System

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x5F31E | `pf_replace` | Replace tile at given slot with new type; handle MOB/graphics update |
| 0x5E892 | `pf_floor_update` | Update floor/wall tile graphics at given position |
| 0x5E536 | `pf_stamp_update` | Update a 2×2 stamp on playfield (e.g., exit open/close animation) |
| 0x5F77A | `pf_isdoor` | Returns 0=not door, 1=intersection, 2=horiz door, 3=vert door |
| 0x5F7FA | `pf_door_update_surrounding` | Check surrounding positions for doors; update door graphics |
| 0x5F5A0 | `refresh_tile_visual` | Dispatch on tile type → select descriptor → write to VRAM |
| 0x5E542 | `write_tile_descriptor` / `pf_stamp_update` | Write 4-word 2×2 tile descriptor to playfield VRAM |
| 0x5F7F0 | `update_neighbor_tiles` | Iterate 4 neighbors; call `update_wall_connection` for each wall |
| 0x5F876 | `update_wall_connection` | 4-bit connectivity bitmask → lookup tables → wall graphic |
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
| 0x45BE8 | `stridx` / `strlen` | Pointer to string → offset of next null byte (string length) |
| 0x510FC | `calc_direction` | Compute direction (0–7) from source to destination position |
| 0x511AC | `player_tile_interact` / `tile_occupant_interact` | Dispatch by tile type: food/key/enemy/portal/chest handlers |

---

## 15. Sound Functions

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x4AD76 | `sound_play` / `play_sound` | Enqueue sound ID into 8-slot circular ring buffer |
| 0x4AD4E | `sound_speech_play` / `play_sound_mute_guarded` | Like play_sound but check mute flag first |
| 0x5DF5A | *(unnamed)* | Something to do with shot graphics |
| 0x5DF68 | *(unnamed)* | Something to do with shot graphics |
| 0x5DF72 | *(unnamed)* | Something to do with shots |

---

## 16. Shot / Combat Functions

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x41B16 | `find_unused_shot` | Scan shot MOB array for slot with mob_picture == 0 |
| 0x490DC | `monster_create_shot` | Create a monster shot MOB; link into shot list |
| 0x53666 | `player_create_shot` | Create a player shot MOB |
| 0x4AF50 | `resolve_shot_hit` | Large dispatcher (~500 B): handle combat resolution for all target types |
| 0x40906 | `shot_mob_collision` | Bounding-box collision test for shot projectiles |
| 0x52192 | `mob_collision_test` | Bounding-box overlap + type dispatch for combat/pickup/warp |

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
| 0x4DA3E | *(in attract setup)* | Initialize display config for TITLE attract screen |
| 0x449D4 | `attract_demo_init` / `demo_setup` | Initialize demo level for DEMO attract screen; sets up Elf player 1 |
| 0x40D24 | `load_level_tileset` | Load level tile data into VRAM |
| 0x4CD1C | `load_demo_level` | Load demo level for attract mode |
| 0x44DB4 | `spawn_enemies_attract` | Spawn attract-mode thief animation |
| 0x40CF2 | `maze_init` | Maze initialization (called from main_start_game) |
| 0x4FCF0 | `find_richest_player` | Find player with highest item value (for thief targeting) |
| 0x4EE7A | `thief_move_engine` | Core thief movement/direction computation |
| 0x4F912 | `compute_path` | Path computation for thief and other entities |
| 0x4E1B8 | `mark_item_stolen` | Mark item stolen in theft tracking |
| 0x4E172 | `abort_theft` | Abort current theft sequence |
| 0x43192 | `eeprom_write` | Copy 6 monitored values to write buffer; flush via OS 0x24E |
| 0x4ADAE | `sound_queue_reset` | Fill ring buffer with 0xFF; zero read/write heads |
| 0x45940 | `flash_score_display` / `draw_player_name` | **Conflict:** Phase 24 analysis calls this `flash_score_display` (draws score digits with flash attribute via OS 0x260); Phase 8 sub-call tree calls it `draw_player_name` (draws character name tile in HUD). Same address, different described behaviors — see `08_known_issues.md`. |
| 0x459A2 | `update_health_bar` / `draw_player_lives` | **Conflict:** Phase 24 calls this `update_health_bar` (draws health bar MOBs); Phase 8 sub-call tree calls it `draw_player_lives` (draws life-counter icons). See `08_known_issues.md`. |
| 0x4A2CA | `draw_player_game_over` | Renders "GAME OVER" banner with class graphic; called from `player_cleanup_slot` |
| 0x54AF8 | `check_player_proximity` | Check if a player is nearby; used by `main_handle_potions` for proximity-based invulnerability |
| 0x4D1A4 | `check_coin_eligibility` | Check DIP switches and player state to determine if player can continue; called from `show_continue_screen` |
| 0x489B8 | `remove_dying_player_sprites` | Remove sprite slots for dying player; called from `show_continue_screen` |
| 0x50B88 | *(score animation phase)* | Score animation phase handler |
| 0x4119A | `monster_special_handler` | Sorcerer teleport/acid spread/IT chase logic |
| 0x40E6A | `monster_loop_core` | Monster processing loop body; handles speed tables, type dispatch, animation |
| 0x40FAE | *(monster walk loop body)* | Per-MOB iteration body within monster_loop_core |
| 0x46F56 | `scroll_set_position` | Apply scroll X/Y to hardware registers with clamping |
| 0x41B7E | `apply_direction_from_delta` | Compute direction code from dx/dy between MOBs |
| 0x495A6 | `monster_move_speed_execute` | Core monster movement: type dispatch, momentum, damage apply |
| 0x49A98 | `monster_despawn_timer` | Per-mob countdown; random respawn on expiry |
| 0x540E8 | `find_player_in_fire_arc` | Find player in dragon fire arc for targeting |
| 0x53D10 | `dragon_death` | Dragon death sequence |
| 0x5DF68 | `spawn_fireball_projectile` | Spawn dragon fireball projectile MOB |
| 0x5E888 | `wall_remove_playfield_update` / `refresh_floor_visual` | Refresh floor visual after wall removal |
| 0x5EAB8 | `refresh_wall_visual` | Refresh wall visual (called from refresh_tile_visual for wall-type tiles) |
| 0x4ADD6 | `enqueue_sound` | Low-level sound ID enqueue into ring buffer at 0x90404B; called by play_sound |
| 0x40CC4 | *(maze cleanup)* | Called from start_attract_to_game with arg 0; clears maze state |

---

## 19. Detailed Shared Function Behaviors

### `start_attract_screen` — 0x44414

Sets `game_mode` (0x904918) to arg value. Calls OS 0x14E (hardware init). If dialog timer > 0: sets to 1 and calls `speech_countdown_flush`. Plays sounds 0x1 (silence) + 0x3C (music fade-out). Clears level counter (0x904000=0, 0x904004=1). Calls `pf_palette_clear` (0x5FCCE) and `player_resetall` (0x4341E).

Dispatch by mode:
- **TITLE (-2):** timer = 0x5DD (25 sec). Calls 0x4438E (init display config) and 0x4DA3E. Every 13th title cycle: refreshes EEPROM settings via OS 0x1BA/0x236/0x1A8. If bit 14 of settings set and music counter zero: plays music 0x3B.
- **SCORES (-1):** timer = 0x258 (10 sec). Calls `attract_highscores` (0x4A124).
- **DEMO (-3):** timer = 0x1C20 (119 sec). Calls `demo_setup` (0x449D4), clears frame counter.
- **LEGEND (-4):** timer = 0x258. Calls `maze_hide` (0x4529A), draws legend art via `setup_infopanel` (0x452D0(-1)), loads demo level via 0x4CD1C.

### `start_attract_to_game` — 0x44204

Transitions from attract to gameplay. Clears level (0x904000=0). Flushes speech, clears damage flags (0x90487E=0, 0x9049E4=0). If DEMO mode: clears display. Plays sound 0x3C (music fade). Sets `game_mode=0` (NORMAL), level=1.

Initializes continue system: `0x904BB4/0x904BAC = 0x7D30` (default pointers), `0x904BB0/0x904BA8 = 0`. Calls OS 0x14E. Plays sound 0x2 ("Noisy"). Clears playfield via `maze_hide`, spawns enemies via 0x44DB4, sets up scores via 0x438AE.

Loops 4 players: draws character tiles to HUD via OS 0x25A using ROM tables at 0x57340, 0x570B8, 0x570B4, 0x570CC, 0x570BC, 0x570DC, 0x570C4. Loads main tilemap via OS 0x200 from ROM 0x5709A (0x8C00 bytes). Places players via `init_display` (0x43486) with start coords from `0x904B58`/`0x904B5A`. Sets attract timer to -1.

### `init_display` — 0x43486

Args: `(scroll_x: word, scroll_y: word)`. Sets up playfield scroll and initializes color palettes.

Waits for VBLANK by testing bit 3 of hardware port `0x803009`, then spinning on VBLANK semaphore at `0x904002`. Copies two blocks of 32 longwords from ROM palette data at `0x5AD1E` to color RAM at `0x910000` (alpha palette) and `0x910100` (MOB palette) via `copy_longwords` (0x5FD6A).

Level-dependent palette: if `0x904B5E < 6`, uses playfield palette from ROM `0x5D7E8`; otherwise uses `0x5D828`. Sets `0x904A4E` (countdown timer) and `0x904B7C` (attract timer). Clears `0x90486E` and `0x904AC6`.

### `init_display_list` — 0x42F86

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

### `maze_food_mob_consume` — 0x43D8C

Three calling modes based on argument:
- **arg=0:** Scan for tile type 0x10 (food), call `pf_replace(slot, 0)` and `moblist_remove_and_clear`
- **arg=0xFFFF:** Scan for tile type 0xF (food variant), remove it, store its slot index in `ram.level_start_slot` (0x9049E0)
- **arg=N (N≥1):** Remove N random treasure mobs (types 0x31/0x32), iterating until N consumed
