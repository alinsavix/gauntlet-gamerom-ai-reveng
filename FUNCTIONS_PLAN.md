# Gauntlet II — Complete Function Analysis Tracker

## Status Key

| Status | Meaning |
|--------|---------|
| `NOT_STARTED` | Function not yet analyzed |
| `IN_PROGRESS` | Analysis underway |
| `DONE` | Fully analyzed with args, return, description |
| `SHARED` | Analyzed in shared registry, referenced here |

## Progress Summary

| Phase | Function | Status |
|------:|:---------|:-------|
| 0 | one_time_init (0x4327a) | DONE |
| 1 | main_logo_updcolors (0x4dcba) | DONE |
| 2 | input_debounce (0x40644) | DONE |
| 3 | coincheck (0x42b6a) | DONE |
| 4 | main_cycle_tport_and_ffield (0x40528) | DONE |
| 5 | main_handle_potions (0x46fea) | DONE |
| 6 | main_open_doors (0x45c00) | DONE |
| 7 | main_handle_shots (0x474f6) | DONE |
| 8 | main_move_players (0x4a53a) | DONE |
| 9 | main_scroll_playfield (0x46caa) | DONE |
| 10 | main_move_monsters (0x49034) | DONE |
| 11 | main_handle_dragon (0x54454) | DONE |
| 12 | main_thief_anim (0x4e8dc) | DONE |
| 13 | main_start_thief (0x4deb8) | DONE |
| 14 | main_health_countdown (0x466f6) | DONE |
| 15 | main_treasure_timer (0x4d29e) | DONE |
| 16 | main_handle_death (0x4664c) | DONE |
| 17 | main_exit_move (0x5287c) | DONE |
| 18 | main_walls_cyclic_move (0x5e62a) | DONE |
| 19 | main_walls_random_move (0x5e41a) | DONE |
| 20 | main_msgbox_countdown (0x4ccbc) | DONE |
| 21 | pick_character (0x42df4) | DONE |
| 22 | main_start_game (0x4800c) | DONE |
| 23 | main_score_update (0x4715e) | DONE |
| 24 | main_score_display (0x457c0) | DONE |
| 25 | main_attract (0x44562) | DONE |
| 26 | eeprom_timer (0x431ee) | DONE |
| 27 | sound_response (0x42d0a) | DONE |
| 28 | main_update_sound (0x4ae20) | DONE |

---

## Shared Functions Registry

Functions called from multiple top-level trees. Analyzed once, referenced everywhere.

### OS ROM API Calls (address < 0x10000)

| Address | Name | Args | Description |
|---------|------|------|-------------|
| 0x184 | os_alloc_or_check | (arg: long) | Allocates/checks resource; returns 0 in d0 on success, non-zero on busy |
| 0x1B4 | os_remove_sprite_object | (sprite_ptr, class, char_class, base) | Removes a sprite object from display lists |
| 0x1CC | os_reset_controller | (player: long) | Resets player controller state |
| 0x218 | os_write_sprite_tile | (slot, frame, tile_base, tile_word) | Writes one sprite-tile entry to VRAM display list |
| 0x224 | os_alloc_display_entry | (index, base) | Allocates/gets display list entry pointer; returns ptr in d0 |
| 0x242 | os_sound_channel_active | (sound_id: long) | Returns non-zero in d0 if sound channel is already playing |
| 0x24E | os_alloc_display_list | (base, arg2, arg3) | Allocates display list; returns handle in d0.w |
| 0x25A | os_draw_text | (plane_base, write_slot, string_ptr, char_count) | Draws text string to display list |
| 0x260 | os_draw_number | (plane_base, write_slot, row, value, color) | Renders decimal number as tiles |

### Shared Game Functions `DONE`

#### `play_sound` — 0x4AD76
- **Args:** (sound_id: long) — low byte is the 8-bit sound ID
- **Return:** void
- **Description:** Checks if sound system is enabled (0x9049EE == 0). If enabled, calls OS 0x242 to check if channel already playing this sound; if so, skips. Otherwise enqueues the sound ID byte into an 8-slot circular ring buffer at 0x90404B (write head at 0x904053, read head at 0x904054). Drops silently if queue is full.
- **Sub-calls:** OS 0x242, `enqueue_sound` (0x4ADD6)
- **Callers:** main_move_players, main_handle_shots, main_move_monsters, and many others

#### `mob_remove` — 0x5E064
- **Args:** (mob_id: long) — MOB slot index
- **Return:** void
- **Description:** Unlinks MOB `mob_id` from two doubly-linked lists in 0x903800 (forward links, low 10 bits) and 0x904066 (backward links, low 10 bits). Patches predecessor/successor pointers to skip the removed MOB. Updates camera target at 0x9049DE if this MOB was the focus. Removes from priority bucket table at 0x905F80. Zeros all array entries for the slot (0x904940, 0x903800, 0x904066).
- **Sub-calls:** none
- **Callers:** player_death_sequence, show_continue_screen, player_start_in_maze, and others

#### `mob_unlink` — 0x5DDDA
- **Args:** mob_id in d2 register (not stack-based — internal BSR target)
- **Return:** void
- **Description:** Same operation as mob_remove but called via BSR with d2 already set. Removes MOB from all 5 linked arrays (0x902000, 0x902800, 0x903000, 0x903800, 0x904066), updates priority bucket at 0x905F80, zeros the slot.
- **Callers:** award_walk_bonus, check_trap_wall_trigger, show_continue_screen

#### `mob_create` — 0x5DC58
- **Args:** (mob_id: word, tile: word, hpos: word, vpos: word, type: word, direction: word) — 6 longwords on stack
- **Return:** void
- **Description:** Installs a MOB into the hardware VRAM arrays. Writes tile to 0x902000, hpos to 0x902800, vpos to 0x903000. Sets type bits (bits 15-10) in 0x903800 and direction bits (bits 15-10) in 0x904066. Links into priority display list via sub-call 0x5DCBC.
- **Callers:** maze_place_object, player_start_in_maze, and many others

#### `strlen` — 0x45BE8
- **Args:** string pointer in a0 (register-based)
- **Return:** d0 = length (count of non-zero bytes)
- **Description:** Standard null-terminated string length counter.
- **Callers:** demo_speech_cmd, player_hurt_flash

#### `fill_buffer_spaces` — 0x4C70A
- **Args:** count from 0x904A9A (reads global)
- **Return:** void
- **Description:** Fills `count` bytes at 0x904AA4 with space characters (0x20), then null-terminates.
- **Callers:** demo_speech_cmd, player_hurt_flash

#### `compute_screen_coords` — 0x4CB50
- **Args:** (player_index: long, or -1 for center)
- **Return:** void, writes X to 0x904AA0, Y to 0x904AA2
- **Description:** Converts player's tile position to screen pixel coordinates for UI overlay positioning. If player -1, defaults to screen center (0x0E, 0x0F). Otherwise reads tile from 0x904BD8, extracts X/Y, adjusts relative to scroll registers 0x904008/0x90400A, divides/clamps to screen range.
- **Callers:** demo_speech_cmd, player_hurt_flash

#### `speech_countdown_flush` — 0x4CCBC
- **Args:** none (reads 0x904A9E timer)
- **Return:** void
- **Description:** Decrements speech timer at 0x904A9E. When it reaches zero, walks the speech ring buffer and clears stale entries by zeroing slots, advancing 0x904A96 pointer. Pure housekeeping.
- **Callers:** demo_speech_cmd, player_hurt_flash, main_msgbox_countdown (Phase 20)

#### `next_anim_frame` — 0x55440
- **Args:** (current_frame_byte, accumulator_word, class_modifier) — register-based
- **Return:** d0 = new frame byte
- **Description:** Animation state machine for player enter/death sequences. Adds or subtracts 1 from frame byte based on accumulator sign. Handles boundary wraps: 0x09→skip, 0x21→0x41, 0x5B→0x08/0x20, 0x07→0x5A, etc.
- **Callers:** player_enter_animation, player_death_sequence

#### `update_sprite_tile` — 0x4A44A
- **Args:** (player_slot, tile_offset, frame_byte, tile_base_word) — register/stack hybrid
- **Return:** void
- **Description:** Computes final tile index from frame byte and base. Calls OS 0x224 to get display list entry pointer, then writes tile coordinates with offsets into the sprite object.
- **Callers:** player_enter_animation, player_death_sequence

#### `schedule_sprite_update` — 0x554B6
- **Args:** (player_index, accumulator, frame_byte, tile_base)
- **Return:** void
- **Description:** Looks up tile attributes from frame byte and tile base. Calls OS 0x218 to write sprite tile word to display list.
- **Callers:** player_enter_animation

#### `copy_longwords` — 0x5FD6A
- **Args:** (count, src_ptr, dst_ptr)
- **Return:** void
- **Description:** Copies count+1 longwords from src to dst. Simple block copy.
- **Callers:** player_start_in_maze

#### `tile_on_screen_test` — 0x5E584
- **Args:** tile index (register-based)
- **Return:** d0 = 0xFF if on-screen, 0 if off
- **Description:** Extracts X/Y from tile index, computes pixel position relative to scroll (0x904008, 0x904AC4). Returns 0xFF if within visible window, 0 if clipped.
- **Callers:** player_start_in_maze

#### `rand_n` — 0x5FC4E
- **Args:** (N: long)
- **Return:** d0 = random value in [0, N)
- **Description:** LCG random number generator using seed at 0x904BFC.
- **Callers:** player_check_pickups, and likely many others

#### `random_word` — 0x5FC46 / 0x5FC4E
- **Entry 0x5FC46:** register-based, d0 = range
- **Entry 0x5FC4E:** stack-based, word at 0x6(a7) = range
- **Return:** d0 = random value in [0, range)
- **Description:** Linear Congruential Generator. Seed at 0x904BFC, multiplier 0x3619, increment 0x5D35. Result = floor((seed_new * range) / 65536).
- **Callers:** monster_generic_handler, main_walls_random_move, find_empty_tile, player_check_pickups, and many others

#### `write_tile_descriptor` — 0x5E542
- **Args:** d0.w = packed tile position (bits 9:5 = column, bits 4:0 = row), a0 = pointer to 4-word sprite descriptor, a1.w = palette base
- **Return:** void
- **Description:** Computes VRAM address at 0x900000 for a 2x2-tile block. Writes 4 words from template (a0) + palette base (a1) to: [slot+0], [slot+0x80], [slot+2], [slot+0x82]. The sprite table at 0x900000 is 128 columns x 256 rows of 2-byte entries.
- **Callers:** refresh_tile_visual, refresh_wall_visual, refresh_floor_visual

#### `refresh_tile_visual` — 0x5F5A0
- **Args:** d0.w = tile index, d1.w = tile type code (register-based)
- **Return:** void
- **Description:** Dispatches on tile type to select the correct 4-word sprite descriptor pointer from ROM tables (0x5C8A0/0x5C8A8/0x5CAA8/0x5BA70). Calls write_tile_descriptor. Then calls update_neighbor_tiles to propagate wall connectivity changes. Also handles diagonal neighbors.
- **Sub-calls:** write_tile_descriptor (0x5E542), refresh_floor_visual (0x5E888), refresh_wall_visual (0x5EAB8), update_neighbor_tiles (0x5F7F0)
- **Callers:** main_walls_random_move, check_trap_wall_trigger, cyclic walls

#### `update_neighbor_tiles` — 0x5F7F0
- **Args:** d0.w = tile X, d1.w = tile Y (register-based)
- **Return:** void
- **Description:** Iterates over 4 orthogonal neighbors. For each, calls get_wall_type (0x5F77A) to classify the neighbor (0=not wall, 1=horiz, 2=vert, 3=pillar). If it's a wall, calls update_wall_connection (0x5F876) to recompute the wall-segment graphic variant for connectivity.
- **Callers:** refresh_tile_visual, cyclic wall placement

#### `update_wall_connection` — 0x5F876
- **Args:** a0.w = tile X, a1.w = tile Y, d0.w = wall type (1/2/3)
- **Return:** void
- **Description:** Resolves the correct wall-segment graphic for a wall tile by examining all orthogonal neighbors. Builds a 4-bit connectivity bitmask (left/right/up/down) and indexes lookup tables at 0x5F9CE (straight walls, 16 entries), 0x5FACA (type-2 corners, 8 entries), 0x5FBDC (type-3 corners, 8 entries). Writes tile type, scroll attributes, and shape index to 0x902000/0x902800/0x903000/0x904066.
- **Sub-calls:** get_wall_type (0x5F77A)

#### `insert_mob_depth_sorted` — 0x5DF9C
- **Args:** (mob_slot: word at 0x22(a7), y_position: word at 0x26(a7))
- **Return:** void
- **Description:** Inserts a MOB into the Y-depth-sorted display chain. Computes Y-bucket from position (0x905F80, 64 entries). Walks the chain comparing Y positions to find insertion point. Patches forward/backward links in 0x903800 and 0x904066. Updates global head at 0x9049DE if needed.
- **Callers:** player_create_shot, player_start_in_maze, generator spawning

#### `player_sound_sprite_update` — 0x487CA
- **Args:** (player_index: long)
- **Return:** void
- **Description:** Updates sound effect and sprite animation state for one player. Guards on animation lock (0x904ACA) and countdown timer (0x904ACE). Selects animation frame count from player state bits, picks sprite set from facing/walk-cycle, calls play_sound_or_set_sprite. Arms animation lock and resets 1800-tick timer.
- **Sub-calls:** random_word (0x5FC4E), play_sound_mute_guarded (0x4AD4E)
- **Callers:** player_check_pickups, main_health_countdown

#### `play_sound_mute_guarded` — 0x4AD4E
- **Args:** (sound_id: long)
- **Return:** void
- **Description:** Like play_sound but first checks 0x904A24 bit 11 (mute flag). If muted, skips.
- **Callers:** player_check_pickups, player_hurt_flash

#### `start_attract_screen` — 0x44414
- **Args:** (new_game_mode: word at a6+0xa)
- **Return:** void
- **Description:** Sets game_mode (0x904918) to the arg value. Calls OS 0x14E (hardware init). Flushes pending speech (if 0x904A9E > 0, sets to 1 and calls 0x4CCBC). Plays sound 0x1 (silence) and 0x3C (music fade-out). Clears level counter (0x904000=0, 0x904004=1). Calls 0x5FCCE and 0x4341E (clear display). Dispatches based on mode: **-2 (TITLE)**: timer=0x5DD (25 sec), calls 0x4438E (init display config), 0x4DA3E. Every 13th title cycle: refreshes EEPROM settings via OS 0x1BA/0x236/0x1A8. If bit 14 of settings set and music counter (a3) zero: plays music 0x3B. **-1 (SCORES)**: timer=0x258 (10 sec), calls 0x4A124 (init score screen). **-3 (DEMO)**: timer=0x1C20 (119 sec), calls 0x449D4 (init demo level), clears frame counter. **-4 (LEGEND)**: timer=0x258, clears playfield (0x4529A), draws legend art (0x452D0(-1)), loads demo level (0x4CD1C).
- **Callers:** main_attract (Phase 25), coincheck (Phase 3)

#### `start_attract_to_game` — 0x44204
- **Args:** None
- **Return:** void
- **Description:** Transitions from attract to gameplay start. Clears level (0x904000=0), calls 0x40CC4(0). Flushes speech, clears damage flags (0x90487E=0, 0x9049E4=0). If in DEMO mode: calls 0x4341E (clear display). Plays sound 0x3C (music fade). Sets game_mode=0 (NORMAL), level=1. Initializes continue system: 0x904BB4/BAC = 0x7D30 (default pointers), 0x904BB0/BA8 = 0. Calls OS 0x14E. Plays sound 0x2 ("Noisy"). Clears playfield (0x4529A), spawns enemies (0x44DB4), sets up scores (0x438AE). Loops 4 players: draws character tiles to HUD via OS 0x25A using ROM tables (0x57340, 0x570B8, 0x570B4, 0x570CC, 0x570BC, 0x570DC, 0x570C4). Loads main tilemap via OS 0x200 (ROM 0x5709A, 0x8C00 bytes). Places players via 0x43486 with start coords from 0x904B58/0x904B5A. Sets attract timer to -1. Clears 0x90486E, 0x904AC6.
- **Callers:** coincheck (Phase 3), main_attract (Phase 25), main_start_game (Phase 22)

#### `player_init_for_coin` — 0x488CA
- **Args:** (player_index: word at a6+0xa)
- **Return:** void
- **Description:** Initializes a player slot when a coin is inserted. If in DEMO mode (0x904918 == 0xFFFD): sets health from ROM constant at 0x578A0. Otherwise: plays character announcement speech from ROM table 0x57002[player*4] via play_sound. If two_player_mode (0x9049E2 != 0): looks up health-per-coin from table at 0x57862 indexed by (settings & 0x1F), stores in player_health. Clears score accumulator (0x904990[player*4] = 0). Sets coin count to 1 (0x904B2A[player*2] = 1). Sets join timer to -1 (0x904A26[player*2] = 0xFFFF). Clears pickup byte (0x904ACA[player] = 0). Sets respawn timer to -1 (0x904ACE[player*2] = 0xFFFF). Sets player status to 0x10 ("selecting character") at 0x9049A0[player]. Calls player_cleanup_slot (0x452D0) with player index.
- **Callers:** coincheck (Phase 3), main_start_game (Phase 22)

#### `init_display` — 0x43486
- **Args:** (scroll_x: word at a6+0xa, scroll_y: word at a6+0xe)
- **Return:** void
- **Description:** Sets up the playfield scroll position and initializes color palettes. Waits for VBLANK by testing bit 3 of hardware port 0x803009 then spinning on VBLANK semaphore at 0x904002. Copies two blocks of 32 longwords from ROM palette data at 0x5AD1E to color RAM at 0x910000 (alpha palette) and 0x910100 (MOB palette) using copy_longwords (0x5FD6A). Level-dependent: if 0x904B5E < 6, uses playfield palette from ROM 0x5D7E8; otherwise from 0x5D828. Applies further color setup for special levels (scroll_x == 0x10 path). Sets scroll position from args, configures 0x904A4E (countdown timer) and 0x904B7C (attract timer). Clears 0x90486E and 0x904AC6.
- **Callers:** one_time_init, start_attract_to_game, main_start_game

#### `score_screen_color_cycle` — 0x4DE76
- **Args:** None
- **Return:** void
- **Description:** Simple palette rotation for the high-score display. Only runs every 16th frame (frame_counter & 0xF == 0). Saves 4 words from the end of color RAM alpha (0x910140 area), shifts 11 entries down by one word position (creating a scrolling effect), then writes the saved 4 words back to the beginning. This produces the cycling rainbow effect on the high-score text.
- **Callers:** main_logo_updcolors (Phase 1, in SCORES mode)

#### `scroll_apply` — 0x4D956
- **Args:** (x_delta: word at a6+0xa, y_delta: word at a6+0xe)
- **Return:** d0 = 0xFF if delta applied, 0 if no valid scroll target found
- **Description:** Applies a scroll delta to the playfield for title-screen animation. If both deltas are zero: writes 0x75 to 5 consecutive scroll anchor slots in 0x9038DE (stride 0x24 each), returns 0xFF. If non-zero: walks the MOB link list starting at 0x903840/0x902040, looking for scroll anchor tiles (MOB picture in range 0x2700-0x2728). When found: applies the delta. Otherwise continues scanning.
- **Callers:** main_logo_updcolors (Phase 1)

#### `init_display_list` — 0x42F86
- **Args:** None
- **Return:** void
- **Description:** Reads game configuration from EEPROM and initializes the display system. Spins on OS 0x184 until resource is available. Calls OS 0x24E to read EEPROM block into buffer at 0x904B8E. If result == 0xFFFE (first boot): initializes defaults — writes header bytes (0x05, 0x00, 0x68, 0x00), clears remaining fields, stores game_settings word (0x904A24), writes back via OS 0x24E with flag=1. Parses the buffer: byte 0 → 0x904010 (level number, validated against slapstic ROM pointer table at 0x38000), byte 1 → 0x90400E (difficulty bits & 7), byte 2 → 0x904018 (clamped to 0x68-0x72 range), byte 3 → 0x904016 (& 3), words 4-5 → 0x904B86 (stats, clamped to 0x7D0), 0x904B94 (settings). Sets EEPROM write timer to 0x8CA0.
- **Callers:** one_time_init (Phase 0)

#### `init_monster_system` — 0x49BD0
- **Args:** None
- **Return:** void
- **Description:** Initializes the monster/entity subsystem at startup. Reads game settings from EEPROM slot 0xC via OS 0x1A8. If bit 15 of settings is set (dirty flag): loops 4 players calling OS 0x1B4 with zero args to clear player state. Clears VBLANK semaphore (0x904002=0). Loops 4 players: for each, calls OS 0x1AE(player, 0) to read stored player stats. If stats are null (new game): clears d3 flag. Otherwise: calls OS 0x1AE(player, 4) to read extended stats. Initializes per-player control vectors and parameters from the read data.
- **Callers:** one_time_init (Phase 0)

#### `wall_place_playfield_update` — 0x5F024
- **Args:** d0 = tile column, d1 = tile row (register-based)
- **Return:** void
- **Description:** Complement of wall_remove_playfield_update (0x5E888). Places a wall tile on the playfield by computing the 2x2 tile sprite descriptor from ROM wall tile tables, writing it to VRAM via write_tile_descriptor (0x5E542), then calling update_neighbor_tiles (0x5F7F0) to propagate wall connectivity changes to adjacent tiles.
- **Callers:** main_walls_cyclic_move (Phase 18)

---

## Phase 0 — one_time_init (0x4327a) `DONE`

**Category:** Init (called once before main loop begins)

### `one_time_init` — 0x4327A

- **Address:** 0x4327A–0x4335E
- **Arguments:** None
- **Return value:** void
- **Registers saved:** a2, link a6

**Description:**

Called once from the main loop before the VBLANK wait begins. Performs full game initialization:

1. **Sound system reset** (0x43288): Calls `sound_system_reset` (0x42DC8) — flushes the sound ring buffer, resets speech counter, sends hardware reset command via OS 0x254.

2. **Clear game state** (0x4328E): Zeros `0x90400C` (game state byte).

3. **Initialize display** (0x43294): Calls `0x43486` with args (0, 0) — likely initializes the playfield display/tilemap.

4. **Read hardware config** (0x4329E–0x432D4):
   - Calls OS `0x236` — reads DIP switch / hardware configuration. Stores result to `0x9049E2` (two-player mode flag).
   - Calls OS `0x1A8` with arg 0xC — reads EEPROM slot 12 (game settings). Stores to `(a2)` = 0x904A24 (game settings word).
   - Calls OS `0x1A8` with arg 0xB — reads EEPROM slot 11 (game options). Masks with 0xFC, then calls OS `0x1C0` with (0xB, masked_value) to write it back (sanitizes the options word).

5. **ROM version check** (0x432DE): Checks bit 12 of game settings word (0x904A24). If set: reads word from ROM at `0x40070`, clears bit 12, writes back to settings. Then calls OS `0x1C0` with (0xC, new_settings) to update EEPROM.

6. **Initialize subsystems** (0x43300):
   - Calls `0x42F86` — initializes the display list / MOB system.
   - Calls `0x49BD0` — initializes monster/enemy subsystem.
   - Calls OS `0x14E` — hardware initialization (interrupts, timers).

7. **Initialize RAM variables** (0x43312–0x4334A):
   - Sets `0x904878` and `0x90487A` to 0x14 (decimal 20) — timers.
   - Clears `0x904B7E` (death timer), `0x904A5E` (state variable).
   - Sets player character types: `0x9048E8[0..3]` = {0, 1, 2, 3} — assigns warrior, valkyrie, wizard, elf as default characters for the 4 player slots.

8. **Start attract mode** (0x4334A): Calls `0x44414` with arg 0xFFFFFFFE (= -2 = GAMEMODE_TITLE) — this initializes the attract mode state machine, starting with the title screen.

**RAM variables written:**
| Address | Value | Description |
|---------|-------|-------------|
| 0x90400C | 0 | Game state byte |
| 0x9049E2 | from OS | Two-player mode flag |
| 0x904A24 | from EEPROM | Game settings/DIP switch word |
| 0x904878 | 0x14 | Timer A |
| 0x90487A | 0x14 | Timer B |
| 0x904B7E | 0 | Death timer |
| 0x904A5E | 0 | State variable |
| 0x9048E8 | 0,1,2,3 | Default character types for 4 players |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x42DC8 | sound_system_reset | SHARED |
| 0x43486 | init_display | DONE |
| 0x236 | OS: read_hardware_config | DONE (OS API) |
| 0x1A8 | OS: read_eeprom_slot | DONE (OS API) |
| 0x1C0 | OS: write_eeprom_slot | DONE (OS API) |
| 0x42F86 | init_display_list | DONE |
| 0x49BD0 | init_monster_system | DONE |
| 0x14E | OS: hardware_init | DONE (OS API) |
| 0x44414 | start_attract_screen | DONE |

---

## Phase 1 — main_logo_updcolors (0x4dcba) `DONE`

**Category:** Display — always called every frame

### `main_logo_updcolors` — 0x4DCBA

- **Address:** 0x4DCBA–0x4DE74
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2/a2-a3, link a6

**Description:**

Manages the Gauntlet II logo color cycling animation and title screen visual effects. Behavior depends on game_mode.

**Game mode dispatch (0x4DCCE–0x4DCFA):**
- If `game_mode == 0xFFFF` (SCORES): calls `score_screen_color_cycle` (0x4DE76), then exits. This animates the high-score screen colors.
- If `game_mode == 0xFFFE` (TITLE): falls through to the title screen animation logic if timer 0x904A18 >= 0. Otherwise returns.
- All other modes: returns immediately (no logo animation during gameplay or demo).

**Title screen animation (0x4DCFA–0x4DE6C):**
Two nested timers control the animation:

1. **Outer timer** at `0x904A18`: Counts down each frame. When it reaches negative, resets from ROM value at `0x5BA68`. Then performs a color-shift animation:
   - Copies 7 words from `0x910206` to `0x910204` (shifts color RAM MOB palette entries up by one slot each frame — this creates the scrolling rainbow effect on the logo text).
   - Repeats for 10 rows (d2 = 0..9), with 16-byte stride between rows.

2. **Inner timer** at `0x904A1A`: Counts down within each outer cycle. When negative, resets from ROM `0x5BA6A`. Then bounces a brightness value:
   - Adds `color_direction` (0x904A16) to the brightness accumulator at `*(a3)` (0x904A1C).
   - Clamps between bounds from ROM at `0x5BA6C` (min) and `0x5BA6E` (max).
   - When hitting a bound, negates `color_direction` (reverses the fade direction — creates pulsing).
   - Reads a new color value from a ROM animation sequence pointer at `0x904A20` (which advances by 2 each cycle through a table at 0x5AC20). Writes the combined value to color RAM at `0x910332`.

3. **Scroll animation** (0x4DDE8–0x4DE6C): When outer timer 0x904A14 (via a2) expires, advances a ROM pointer at `0x904A10` by 4 bytes. Reads a 4-byte record:
   - Byte 0: new timer value for a2 (or -1 for end, 0 to loop)
   - Byte 1: X scroll delta
   - Byte 2: Y scroll delta
   - Byte 3: Y scroll addend applied to `0x90400A` each frame while timer counts down
   - Calls `scroll_apply` (0x4D956) with (X_delta << 7, Y_delta << 7). If it returns 0xFF, loops back to read the next record.

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904918 | R | Game mode |
| 0x904A14 | RW | Logo scroll animation timer (via a2 pointer) |
| 0x904A16 | RW | Color direction (+/- for pulsing) |
| 0x904A18 | RW | Outer color cycle timer |
| 0x904A1A | RW | Inner brightness timer |
| 0x904A1C | RW | Brightness accumulator (via a3 pointer) |
| 0x904A1E | W | Current color value |
| 0x904A20 | RW | ROM animation sequence pointer |
| 0x904A10 | RW | ROM scroll record pointer |
| 0x90400A | RW | Playfield Y scroll |
| 0x910204 | W | Color RAM MOB palette (shifted for rainbow) |
| 0x910332 | W | Color RAM entry for logo brightness |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x4DE76 | score_screen_color_cycle | DONE |
| 0x4D956 | scroll_apply | DONE |

---

## Phase 2 — input_debounce (0x40644) `DONE`

**Category:** Input — always called every frame

### `input_debounce` — 0x40644

- **Address:** 0x40644–0x406B4
- **Arguments:** None
- **Return value:** void
- **Hand-written assembly** — no link/unlk, no movem, only uses d0 (scratch register)

**Description:**

Reads the 4 hardware joystick input ports and performs bit-serial debouncing via rotate-through-extend shift registers. For each of the 4 players:

1. Reads raw input word from hardware port (`0x803000 + player*2`)
2. Stores raw value to `player_input_raw` (`0x904920 + player*2`)
3. Shifts bit 0 of the raw input into debounce shift register A (`0x905F58 + player*2`) via `lsr.w #1, d0; roxl.w addr` — the LSR shifts the lowest bit into the eXtend flag, then ROXL rotates it into the shift register
4. Shifts bit 1 of the raw input into debounce shift register B (`0x905F60 + player*2`) via the same LSR/ROXL pair

The shift registers accumulate 16 consecutive frames of each input bit. Code elsewhere can AND multiple bits to require N frames of consistent input before accepting it (eliminating switch bounce and brief glitches). The `roxl` instruction is a telltale sign of hand-written assembly — no C compiler would generate this pattern.

**RAM variables written:**
| Address | Name | Description |
|---------|------|-------------|
| 0x904920 | player_input_raw[0] | Player 1 raw joystick word |
| 0x904922 | player_input_raw[1] | Player 2 raw joystick word |
| 0x904924 | player_input_raw[2] | Player 3 raw joystick word |
| 0x904926 | player_input_raw[3] | Player 4 raw joystick word |
| 0x905F58 | debounce_shift_a[0] | Player 1 bit-0 shift register |
| 0x905F5A | debounce_shift_a[1] | Player 2 bit-0 shift register |
| 0x905F5C | debounce_shift_a[2] | Player 3 bit-0 shift register |
| 0x905F5E | debounce_shift_a[3] | Player 4 bit-0 shift register |
| 0x905F60 | debounce_shift_b[0] | Player 1 bit-1 shift register |
| 0x905F62 | debounce_shift_b[1] | Player 2 bit-1 shift register |
| 0x905F64 | debounce_shift_b[2] | Player 3 bit-1 shift register |
| 0x905F66 | debounce_shift_b[3] | Player 4 bit-1 shift register |

**Hardware ports read:**
| Address | Description |
|---------|-------------|
| 0x803000 | Player 1 joystick |
| 0x803002 | Player 2 joystick |
| 0x803004 | Player 3 joystick |
| 0x803006 | Player 4 joystick |

**Sub-calls:** None (leaf function)

---

## Phase 3 — coincheck (0x42b6a) `DONE`

**Category:** Input/Economy — always called every frame

### `coincheck` — 0x42B6A

- **Address:** 0x42B6A–0x42D08
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2-d3, link a6 with 0 locals

**Description:**

Detects coin insertions and credits players. Uses a change-detection pattern: compares a coin counter longword at `0x904FEC` against a cached "last seen" value at `0x9049EA`. If they match (no new coins), returns immediately. If they differ, updates the cache and processes all 4 player slots.

**Per-player loop (d3 = 0..3):**

1. Calls OS `0x166` (check_coin_input) with player index. Returns non-zero in d0 if a coin was detected for this player.
2. If no coin for this player: skip to next player.
3. Checks `two_player_mode` at `0x9049E2`: if zero, skips credit logic.
4. **Attract mode transition:** If ALL four players have zero health (0x904980..0x90498C all zero) AND game_mode < 0 (attract): calls `start_attract_to_game` (0x44204) to begin transitioning from attract mode to gameplay.
5. **Player HAS health (active player re-coining):**
   - Increments per-player coin counter at `0x904B2A[d3*2]`
   - Looks up health-per-coin from ROM table at `0x57862`, indexed by `(game_settings & 0x1F)` (the GSETTING_COINHEALTH DIP switch value). Adds this health to `player_health[d3*4]` at 0x904980.
   - Decrements bonus byte at `0x90405F` if positive
   - Clears pickup byte at `0x904ACA[d3]`, sets respawn timer at `0x904ACE[d3*2] = -1`, sets join timer at `0x904A26[d3*2] = -1`
   - Sets redraw flag: `0x904908[d3] |= 2`
   - If coin count > `(difficulty_bits + 1)` (where difficulty = bits 8-9 of 0x904A24): calls `player_cleanup_slot` (0x452D0) to refresh HUD display
   - Plays coin-insert speech from ROM pointer table at `0x57002[d3*4]` via `play_sound` (0x4AD76)
6. **Player has NO health (new player joining):**
   - If player_status == 4 (dying animation): clears status, calls `update_maze_player_count` (0x44C7E)
   - Calls `player_init_for_coin` (0x488CA) with player index to set up the player's initial state for a new game

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904FEC | R | Hardware coin counter longword |
| 0x9049EA | RW | Cached last-seen coin counter (change detection) |
| 0x9049E2 | R | Two-player mode flag |
| 0x904980 | RW | Player health array (longwords, 4 entries) |
| 0x904918 | R | Game mode |
| 0x904B2A | RW | Per-player coin count (words) |
| 0x904A24 | R | Game settings/DIP switches |
| 0x90405F | RW | Bonus byte (decremented on coin) |
| 0x904ACA | W | Per-player pickup byte (cleared) |
| 0x904ACE | W | Per-player respawn timer (set to -1) |
| 0x904A26 | W | Per-player join timer (set to -1) |
| 0x904908 | RW | Per-player redraw flags |
| 0x9049A0 | RW | Player status byte array |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x166 | OS: check_coin_input | DONE (OS API) |
| 0x44204 | start_attract_to_game | DONE |
| 0x452D0 | player_cleanup_slot | SHARED (Phase 8) |
| 0x4AD76 | play_sound | SHARED |
| 0x44C7E | update_maze_player_count | SHARED (Phase 8) |
| 0x488CA | player_init_for_coin | DONE |

---

## Phase 4 — main_cycle_tport_and_ffield (0x40528) `DONE`

**Category:** Maze mechanics — skipped during dialog

### `main_cycle_tport_and_ffield` — 0x40528
- **Address:** 0x40528–0x405BE
- **Args:** None | **Return:** void | **Hand-written assembly** (no link/unlk)
- **Description:** Two independent palette-cycling systems. **Part 1** (transporter segments): 2-bit sub-frame divider at 0x904034 ticks every 4th frame. Position counter at 0x904030 bounces 0→4→0 via direction word at 0x904032 (±1). **Part 2** (forcefield colors): Step counter at 0x904049 cycles 0→7. Each step's duration = ROM table value + random(8) via 0x5FC46. On even steps: reads frame_counter bits [3:2] to select one of 4 color words from ROM table at 0x405C0, writes to forcefield_color at 0x904046. On odd steps: writes 0 (blink off).
- **Sub-calls:** 0x5FC46 (random_word, SHARED)

---

## Phase 5 — main_handle_potions (0x46fea) `DONE`

**Category:** Items/Pickups — skipped during dialog

### `main_handle_potions` — 0x46FEA
- **Address:** 0x46FEA–0x4715C
- **Args:** None | **Return:** void | **Saves:** d2/a2-a3
- **Description:** Per-frame potion processing for all 4 players. For each active player: reads fire button from joystick (0x905F58 in multiplayer, demo pointer in single). If button pattern == 0x1C ("use potion") AND level timer (0x904000) >= 0x73 AND potion count (0x904055[player]) > 0: decrements potion count, plays sound 0x1D, calls 0x45ACA to create explosion MOB visuals, calls 0x4C440 with damage flags 0x80000 (area-kill all visible monsters). Then checks player proximity via 0x54AF8 — if a player is nearby, applies invulnerability: sets bit 0 of 0x904890, writes 0xFFCF to invulnerability timer, plays sound 0xD5. If no potion: plays sound 0x44 ("no potion").
- **Sub-calls:** 0x4C440 (player_hurt_flash, SHARED), 0x45ACA (setup_potion_visuals), 0x54AF8 (check_player_proximity), 0x4AD76 (play_sound, SHARED)

---

## Phase 6 — main_open_doors (0x45c00) `DONE`

**Category:** Maze mechanics — skipped during dialog

### `main_open_doors` — 0x45C00
- **Address:** 0x45C00–0x45E3E
- **Args:** None | **Return:** void | **Saves:** d2-d4/a2-a3
- **Description:** Manages up to 8 concurrent door-opening animation slots. Each slot tracks a door tile being opened or closed via position word (0x904A76[slot*2]) and state (0x904A86[slot*2], 0–3). Per frame iterates all 8 slots. State machine: **State 0** = decrement position (close downward), **State 1** = increment X (advance open rightward), **State 2** = add 0x20 (step row down), **State 3** = decrement X (step left). Each state checks the MOB picture at the new position against door tile ranges (0x9D7C–0x9DAC and 0x9D18–0x9D38). On match: calls mob_unlink (0x5DDDA) to remove the door wall tile and transitions to the next state.
- **Sub-calls:** 0x5DDDA (mob_unlink, SHARED)

---

## Phase 7 — main_handle_shots (0x474f6) `DONE`

**Category:** Combat — skipped during dialog

### `main_handle_shots` — 0x474F6
- **Address:** 0x474F6–0x47C0C
- **Args:** None | **Return:** void | **Saves:** d2-d6/a2-a3
- **Description:** Per-frame shot projectile processing for 12 shot slots (0–3 = player, 4–7 = monster, 8–11 = generator). For each occupied slot: decrements cooldown timer at 0x90492A. Checks wall-stuck counter at 0x904B02. Calls 0x40906 (bounding-box collision test) to detect hits — returns target MOB slot or -1. On hit: calls 0x4AF50 (resolve_shot_hit) which dispatches on target type (player, monster, generator, chest, door, Death) applying damage, scoring, and despawning. Advances pixel position from velocity tables at 0x576E2 (X) and 0x57792 (Y). Detects new-tile entry by comparing against stored tile at 0x904942. On wall collision: calls 0x5E064 (mob_remove). For player shots (0–3): auto-fire logic checks fire button state and creates new shot by setting 0x9048BE[slot]=4.
- **Key sub-calls:** 0x40906 (shot_mob_collision), 0x4AF50 (resolve_shot_hit — large dispatcher ~0x500 bytes), 0x5E064 (mob_remove, SHARED), 0x5DF9C (insert_mob_depth_sorted, SHARED), 0x47DAE (spawn_explosion), 0x4AD76 (play_sound, SHARED)

---

## Phase 8 — main_move_players (0x4a53a) `DONE`

**Category:** Player movement — skipped during dialog, internal game_mode check

### `main_move_players` — 0x4a53a

- **Address:** 0x4a53a–0x4ad4c
- **Arguments:** None (all state from globals)
- **Return value:** void
- **Registers saved:** d2-d6/a2-a4, link a6 with 8 bytes locals
- **Local variables:**
  - -2(a6): total score delta accumulator across all players
  - -4(a6): count of active players that moved this frame
  - -6(a6): movement result code from `player_try_move` (0xF0 = no movement)

**Description:**

Processes movement, animation, powerup timers, and input for all 4 player slots each frame. Has three main sections: a game_mode gate, an optional demo playback preprocessor, and a per-player loop.

**1. Game mode gate (0x4a548–0x4a560):**
Reads `game_mode` at 0x904918.
- If >= 0 (NORMAL or TREAS_EXIT): skip demo section, go directly to per-player loop at 0x4a5f4.
- If == 0xFFFD (DEMO): fall through to demo playback section.
- Otherwise (TITLE/SCORES/LEGEND): jump to function exit at 0x4ad44 — no player processing.

**2. Demo playback section (0x4a560–0x4a5f0):**
Iterates d4 = 0..3 over all 4 player slots.
- `a2` → 0x904b76: per-player demo frame timer (byte array, 4 entries)
- `a3` → 0x904b66: per-player demo data pointer (longword array, 4 entries)

For each player: decrements timer byte at (a2+d4). When it reaches zero:
- Advances the demo data pointer by 2 bytes: `(a3+d4*4) += 2`
- Reads the command/timer byte at the new pointer position:
  - **Byte <= 0xFD:** Normal timer value — store as new countdown, proceed to next player.
  - **Byte == 0xFF:** Speech/sound command — reads second byte as argument, calls `demo_speech_cmd` (0x4c9a2) with args (player_index, argument), then loops back to read next command.
  - **Byte == 0xFE:** End-of-sequence / player switch — reads second byte, splits into hi nibble (direction) and lo nibble (player slot). Sets direction in `player_chartype` array (0x9048e8+slot*2). Calls `player_start_in_maze` (0x48bb6) with (slot). Resets timer to 1 and resets pointer to initial value from ROM table at 0x58098.

Then falls through to the normal per-player loop.

**3. Per-player loop (0x4a5f4–0x4acca), d4 = 0..3:**

Stores current player index to 0x904876. Reads player status byte from `player_status` array at 0x9049a0+d4. Dispatches based on status:

- **Status 0x20 ("entering"):** Calls `player_enter_animation` (0x54fe8). Skips remaining processing.
- **Status 0x04 ("dying"):** Calls `player_death_sequence` (0x49de6) with (player). Skips remaining.
- **Status 0x08 ("dead/respawn wait"):**
  - Increments respawn counter at 0x9049bc+d4*2.
  - Every 4th frame (counter & 3 == 0): cycles idle animation tile from `anim_table_idle` (0x58a4a), indexed by character type and direction.
  - When counter reaches 0x20: transitions to status 0x02 (removed). Calls `mob_remove` (0x5e064) with (player_slot + 0x14 = MOB ID). Clears player MOB slot. Decrements `level_players_active` (0x904928). If no players remain active: handles "all dead" logic — checks continue timers (0x904b7e, 0x904b80), and eventually calls `show_continue_screen` (0x4d476).
- **Status != any of the above (active gameplay, typically 0x08 after entry):**

**Active player processing (0x4a7c2–0x4aca0):**

a) **Pickup collision check:** Calls `player_check_pickups` (0x50e34) with (player). This detects standing on items, food, keys, etc.

b) **Powerup timer management (0x4a7e8–0x4a8a0):**
   Decrements four per-player powerup timers, clearing corresponding flag bits in `player_flags` (0x9048e0+d4*2) when each expires:
   - Invisibility timer at 0x905f50+d0*2 → clears bit 0
   - Reflective shots timer at 0x905f38+d0*2 → clears bit 1
   - Acid/slow timer at 0x905f40+d0*2 → clears bit 5. While active: every 8 frames drains 1 or 2 health from `player_health` (0x904980+d4*4), sets "needs redraw" flag (0x904908+d4 |= 2).
   - Stun timer at 0x905f48+d0*2 → (no flag clear, just expires)

c) **Input reading (0x4a8a2–0x4a908):**
   - If `game_mode` == 0 (NORMAL): reads hardware joystick from `player_input_debounced` at 0x904920+d4*2. If stunned (stun timer > 0): remaps input through stun remap table at 0x4a4fa, which garbles the direction bits cyclically.
   - If `game_mode` != 0 (DEMO): reads input directly from current demo data pointer at (0x904b66+d4*4), masks to 0xF3 (strips bits 2-3).

d) **Movement speed calculation (0x4a920–0x4a966):**
   - If health display counter (0x904000) < 0x73: computes speed from `player_speed_normal` table (0x580a8), indexed by character type × 2 (with +8 offset for powered mode via bit 0 of player_flags+1). Checks `player_anim_rate` table (0x580b8) against frame counter; if non-zero, adds 0x80 to speed (boost frames).
   - If health >= 0x73: forces speed to 0x100 (slow-walk, low health warning).

e) **Shooting detection and fight animation (0x4a966–0x4aa42):**
   - Checks bit 1 of input (fire button). If pressed and no fight already in progress: looks up direction from input nibble via table at 0x5811c, stores as `player_direction` (0x9049a4+d0*2). Sets animation counters.
   - If already fighting: checks `fighting_anim_end` table (0x58090) for end-of-animation threshold.

f) **Core movement call (0x4aa0a–0x4aa42):**
   - Sets 0x904bf2 = 2, clears 0x904a0e.
   - Calls `player_try_move` (0x41bf0) with 3 longword args: (player_index, speed, input_word). Returns movement result in d0.w, stored in local -6(a6).
   - Checks 0x904a0e: if non-zero, keeps current direction in 0x9049ac.

g) **Forcefield damage check (0x4aa42–0x4ab08):**
   - If `forcefield_active` (0x904046) != 0 and acid timer is zero:
     - Calls `check_forcefield_collision` (0x53346) with player MOB long. If returns non-zero: applies forcefield damage by reading health drain from `health_drain_table` (0x5813c) indexed by (character_type+powered_mode × 4). Subtracts from player_health. Updates damage display. Calls `player_hurt_flash` (0x4c440) with (player, 0x80000000, damage). Sets hurt cooldown timer at 0x905f30+d0*2 = 0x12.

h) **Animation tile update (0x4ab08–0x4ac30):**
   - If player is fighting (0x9049b4+d0*2 != 0): selects tile from `anim_table_shooting` (0x5874a), indexed by (anim_counter/4 & 3, direction, character_type × 64). Increments counter. At end of shooting animation: calls `player_create_shot` (0x53666) with (player). Clears fighting state.
   - If movement result != 0xF0 (player moved): selects tile from `anim_table_walking` (0x58a8a), indexed by (anim_counter/4 & 3, direction, character_type × 32). Increments counter.
   - If stationary and not fighting: selects tile from `anim_table_idle` (0x58a4a), indexed by (direction, character_type × 8).

i) **Invisibility flash (0x4ac30–0x4ac80):**
   - If invisible flag (bit 0 of 0x9048e0+d0) set and no dialog active: reads invisibility timer, shifts right 7, looks up flash mask from `invisibility_flash_masks` (0x58070). ANDs with frame_counter. If zero: writes tile 0x1709 (blank/hidden) to MOB picture — creating the flickering effect.

j) **Score accumulation (0x4ac80–0x4aca0):**
   - Reads per-player score delta from 0x90405a+d4 (byte), adds to local -2(a6) running total. Stores movement result in 0x9048f0+d0*2.

**4. Post-loop (0x4acd4–0x4ad44):**
- If any players moved this frame (-4(a6) != 0):
  - Increments walk distance counter at 0x90490c. Threshold: 0xa8c (2700) with treasure collected (local -2 != 0), or 0x4b0 (1200) without. If exceeded: calls `award_walk_bonus` (0x47fac), sets counter to -1 (disabled).
  - Increments global step counter at 0x9048c6. If reaches 0x5208 (21000): calls `check_trap_wall_trigger` (0x5e80c). If that returns non-zero: calls `play_sound` (0x4ad76) with arg 0x27 ("Trap / Walls Turn to Exits"). Clears counter, clears bits 3 and 6 of 0x90491e.

**RAM variables read/written:**
| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| 0x904918 | game_mode | R | Current game mode |
| 0x904b76 | demo_timer[4] | RW | Per-player demo countdown (bytes) |
| 0x904b66 | demo_ptr[4] | RW | Per-player demo data pointer (longs) |
| 0x9048e8 | player_chartype[4] | RW | Per-player character type (words) |
| 0x904876 | current_player | W | Index of player being processed |
| 0x9049a0 | player_status[4] | RW | Per-player status byte |
| 0x9049bc | respawn_counter[4] | RW | Per-player respawn frame counter |
| 0x9048c8 | player_mob_slot[4] | RW | Per-player MOB slot ID (words) |
| 0x904928 | level_players_active | RW | Count of active players |
| 0x9049dc | it_player | RW | Player who is IT |
| 0x904920 | player_input[4] | R | Debounced joystick input (words) |
| 0x9048e0 | player_flags[4] | RW | Per-player flag bits (words) |
| 0x905f50 | invis_timer[4] | RW | Invisibility countdown (words) |
| 0x905f38 | reflect_timer[4] | RW | Reflective shots countdown |
| 0x905f40 | acid_timer[4] | RW | Acid slow countdown |
| 0x905f48 | stun_timer[4] | RW | Stun countdown |
| 0x904980 | player_health[4] | RW | Player health (longwords) |
| 0x904908 | player_redraw[4] | RW | Per-player redraw flags (bytes) |
| 0x9049a4 | player_direction[4] | RW | Current facing direction (words) |
| 0x9049b4 | player_fighting[4] | RW | Fighting animation state (words) |
| 0x9049ac | player_walk_anim[4] | RW | Walking animation counter (words) |
| 0x904a54 | player_move_cooldown[4] | RW | Movement cooldown counter |
| 0x904bf2 | movement_type | W | Movement type flag |
| 0x904a0e | movement_blocked | RW | Whether movement was blocked |
| 0x904046 | forcefield_active | R | Forcefield system active flag |
| 0x904000 | health_display | R | Health bar display counter |
| 0x90490c | walk_dist_counter | RW | Distance-walked bonus counter |
| 0x9048c6 | step_counter | RW | Global step counter for trap trigger |
| 0x904006 | frame_counter | R | Global frame counter |
| 0x904a9e | dialog_timer | R | Dialog box active timer |
| 0x90405a | player_score_delta[4] | R | Per-player score increment (bytes) |
| 0x9048f0 | player_move_result[4] | W | Last movement result per player |
| 0x905f30 | hurt_cooldown[4] | W | Forcefield hurt cooldown timer |
| 0x904ba1 | continue_flags | R | Continue screen control flags |
| 0x904ba4 | continue_active | R | Continue screen active flag |
| 0x904bb0 | continue_ptr_a | R | Continue data pointer A |
| 0x904bb4 | continue_ptr_b | R | Continue data pointer B |
| 0x904ba8 | continue_dest_a | W | Continue destination A |
| 0x904bac | continue_dest_b | W | Continue destination B |
| 0x904878 | some_timer | RW | Decremented when non-zero |
| 0x904b52 | some_state | R | State comparison |
| 0x904b7e | death_timer_1 | RW | Death-related timer 1 |
| 0x904b80 | death_timer_2 | RW | Death-related timer 2 |
| 0x90491e | level_flags | RW | Level feature flag bits |

**Sub-calls (15 total):**

| Address | Name | Args | Status |
|---------|------|------|--------|
| 0x4c9a2 | demo_speech_cmd | (player_index: long, speech_id: long) | DONE |
| 0x48bb6 | player_start_in_maze | (player_slot: long) → d0=0xFF success | DONE |
| 0x54fe8 | player_enter_animation | (none — reads 0x904063 current player) | DONE |
| 0x49de6 | player_death_sequence | (player_index: long) | DONE |
| 0x5e064 | mob_remove | (mob_id: long) | SHARED |
| 0x4d476 | show_continue_screen | (none) | DONE |
| 0x50e34 | player_check_pickups | (player_index: long) | DONE |
| 0x41bf0 | player_try_move | (player: long, speed: long, input: long) → d0.w result | DONE |
| 0x53346 | check_forcefield_collision | (mob_long: long) → d0.w bool | DONE |
| 0x4c440 | player_hurt_flash | (player: long, flags: long, damage: long) → d0.w | DONE |
| 0x53666 | player_create_shot | (player_index: long) | DONE |
| 0x452d0 | player_cleanup_slot | (player_index: long) | DONE |
| 0x47fac | award_walk_bonus | (none) | DONE |
| 0x5e80c | check_trap_wall_trigger | (none) → d0.w bool | DONE |
| 0x4ad76 | play_sound | (sound_id: long) | SHARED |

**Sub-sub-calls discovered (deeper call tree):**

From `player_try_move` (0x41bf0) — the largest sub-tree:
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x42648 | tile_lookup_core | Reads 0x902000[d1], computes distance, sets CF if occupied | DONE |
| 0x4270c | probe_right | Checks tile at (X+2), calls 0x42648 | DONE |
| 0x426d4 | probe_left | Checks tile at (X-2), calls 0x42648 | DONE |
| 0x425d0 | probe_up | Boundary check + (Y+0x40) neighbor via 0x42648 | DONE |
| 0x4260c | probe_down | Boundary check + (Y-0x40) neighbor via 0x42648 | DONE |
| 0x42744 | squeeze_through_check | Tests pass-through flag, tile type, corner geometry | DONE |
| 0x4feb2 | corner_squeeze_geometry | Tests wall corner shape for diagonal squeeze-through | DONE |
| 0x4280e | door_traverse_right | Ray-march via 0x5e35e, spawn passage via 0x47c0e | DONE |
| 0x428a4 | door_traverse_left | Ray-march via 0x5e2a2 | DONE |
| 0x4293a | door_traverse_up | Ray-march via 0x5e1d8 | DONE |
| 0x429d0 | door_traverse_down | Ray-march via 0x5e10c | DONE |
| 0x5e35e | ray_march_right | Scans rightward: 3 neighbors, distance test in X/Y | DONE |
| 0x5e2a2 | ray_march_left | Mirrors right but column--, identical structure | DONE |
| 0x5e1d8 | ray_march_up | Scans upward: 3 neighbors (center/left/right) | DONE |
| 0x5e10c | ray_march_down | Mirrors up but row--, identical structure | DONE |
| 0x47c0e | spawn_passage_marker | Writes 0x924 to 0x902000, copies coords, links to display | DONE |
| 0x5de0a | copy_mob_slot | Copies 5 VRAM arrays, patches backlinks, clears source | DONE |
| 0x5de44 | update_mob_backlinks | Patches prev/next pointers, fixes bucket chain, updates 0x9049DE | DONE |
| 0x4e630 | erase_mob_old_pos | Computes tile-map index, writes blank at old position | DONE |
| 0x549ea | draw_mob_new_pos | View-culled MOB draw with scroll animation trigger | DONE |
| 0x511ac | tile_occupant_interact | Central dispatcher: food/key/enemy/portal/chest handlers | DONE |
| 0x52192 | mob_collision_test | Bounding-box overlap + type dispatch for combat/pickup/warp | DONE |
| 0x4590e | write_escalator_entrance | Writes escalator entrance record to 0x905048 | DONE |
| 0x45866 | write_escalator_exit | Writes escalator exit record | DONE |
| 0x427b4 | failed_door_post | Compute tile position and update MOB display after failed door | DONE |

From `check_trap_wall_trigger` (0x5e80c):
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x5f310 | mob_place_tile | Places tile, removes old MOB, updates visuals | DONE |
| 0x5f7f0 | update_neighbor_tiles | Tests 4 neighbors via get_wall_type, calls update_wall_connection | DONE |
| 0x5f5a0 | refresh_tile_visual | Type dispatch → sprite descriptor from ROM tables → VRAM | DONE |
| 0x5e542 | write_tile_descriptor | Writes 4 words (2x2 tile) to 0x900000 sprite table | DONE |
| 0x5f876 | update_wall_connection | 4-bit connectivity bitmask → lookup table → wall graphic | DONE |

From `player_start_in_maze` (0x48bb6):
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x48bec | player_start_inner | Heavy worker: finds tile, sets up sprite, links MOB | DONE |
| 0x48a36 | player_join_sequence | Announces player, resets controller, plays speech | DONE |
| 0x48f12 | tile_occupancy_test | Checks candidate tile for other players within 0x7C0 px | DONE |
| 0x5df9c | insert_mob_depth_sorted | Y-bucket sorted chain insertion via 0x905F80 | DONE |

From `show_continue_screen` (0x4d476):
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x4d1a4 | check_coin_eligibility | Checks DIP switches and player state for continue | DONE |
| 0x4d900 | count_active_players | Counts players with status 1/2/8/0x10 | DONE |
| 0x489b8 | remove_dying_player_sprites | Removes sprite slots for dying player | DONE |
| 0x486fe | update_bgm_volume | Updates background music volume/fade | DONE |
| 0x54ec6 | reset_attract_player | Resets attract-mode player animation state | DONE |

From `player_check_pickups` (0x50e34):
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x487ca | player_sound_sprite_update | Animation lock + frame select + sprite/sound dispatch | DONE |

From `player_cleanup_slot` (0x452d0):
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x45940 | draw_player_name | Draws character name tile in score HUD | DONE |
| 0x459a2 | draw_player_lives | Draws life-counter icons in score HUD | DONE |
| 0x45aca | draw_player_items_hud | Draws item/key icons in player's HUD strip | DONE |
| 0x4a2ca | draw_player_game_over | Renders "GAME OVER" banner with class graphic | DONE |

From `player_death_sequence` (0x49de6):
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x44c7e | update_maze_player_count | Decrements 0x904928, triggers all-dead state if 0 | DONE |

---

## Phase 9 — main_scroll_playfield (0x46caa) `DONE`

**Category:** Display — skipped during dialog

### `main_scroll_playfield` — 0x46CAA

- **Address:** 0x46CAA–0x46F54
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2-d6/a2-a4, link a6 with 8 bytes locals

**Description:**

Computes the ideal scroll position for the playfield camera based on all active players' positions, then smoothly scrolls toward that target. The algorithm finds the centroid of all active players while respecting the toroidal map wrapping.

**Gate check (0x46CB2–0x46CDA):**
If `level_players_active` (0x904928) is zero: returns. If game_mode is not NORMAL (0) or DEMO (0xFFFD): returns. (Only scrolls during actual gameplay or demo.)

**Phase 1 — Compute player extent (0x46CDE–0x46EC4):**

Sets up screen boundary coordinates from current scroll position at `0x904008` (X) and `0x90400A` (Y):
- d6 = left boundary (scroll_x - 0x98)
- Locals: -6(a6) = right boundary (left + 0x200), -4(a6) = Y reference, -8(a6) = Y bottom

Iterates d3 = -2(a6) from 0..3 over all players. For each active player:
- First pass: reads tile position from `0x904BD8[player*2]`, converts to view-relative coordinates (X×16, Y×row/2), wraps around ±0x200 for the toroidal map.
- Computes min/max X (a3/d5) and min/max Y (a4/d4) across all active players.
- Second pass: reads actual pixel position from MOB arrays `0x902800[slot*2]` (X>>7) and `0x903000[slot*2]` (Y>>7), same wrapping logic. Updates extent bounds, but clamps expansion to ±0xC8 pixels (prevents camera from jumping too far for a single distant player — the "rubber band" effect).

**Phase 2 — Compute target scroll (0x46ED2–0x46F00):**

Target X = average of (min_x, max_x) = `(a3 + d5) / 2`, then `- 0x68` (half-screen offset).
Target Y = average of (min_y, max_y) = `(a4 + d4) / 2`, then `0x1E8 - target_y - 0x6C` (inverts Y for screen coordinates).

**Phase 3 — Smooth scroll (0x46F00–0x46F4A):**

Compares target against current scroll:
- X delta = current_scroll_x - target_x. If delta >= 3: scroll left by 2. If delta <= -3: scroll right by 2. Otherwise: snap to target.
- Y delta = same logic with Y.

Calls `scroll_set_position` (0x46F56) with (new_x, new_y) to apply the scroll.

**Phase 4 — `scroll_set_position` (0x46F56):**

Clamps the scroll values:
- If bit 5 of `0x90491F` is clear (no X-wrap): clamps X to minimum 5.
- If bit 4 clear (no Y-wrap): clamps Y to minimum 5.
- Max clamp: both to 0x1FB.

Writes final X to `0x904008`, final Y to `0x90400A`. Applies hardware scroll by computing:
- `scroll_x << 4` → writes to `0x930000` (PF H-Scroll hardware register)
- `(0x100 - scroll_y) << 4 + 8` → writes to `0x905F6E` (PF V-Scroll register)

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904928 | R | Active player count |
| 0x904918 | R | Game mode |
| 0x904008 | RW | Playfield X scroll position |
| 0x90400A | RW | Playfield Y scroll position |
| 0x904BD8 | R | Per-player tile position (words) |
| 0x904BCE | R | Per-player "in maze" flag (negative = active) |
| 0x9048C8 | R | Per-player MOB slot |
| 0x902800 | R | MOB hpos array |
| 0x903000 | R | MOB vpos array |
| 0x90491F | R | Level flags (bit 5 = X-wrap, bit 4 = Y-wrap) |
| 0x930000 | W | Hardware PF H-Scroll register |
| 0x905F6E | W | Hardware PF V-Scroll register |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x46F56 | scroll_set_position | DONE (inline, documented above) |

---

## Phase 10 — main_move_monsters (0x49034) `DONE`

**Category:** Monster AI — skipped during dialog, gated by active player count

### `main_move_monsters` — 0x49034

- **Address:** 0x49034–0x490DA
- **Arguments:** None
- **Return value:** void
- **Registers saved:** a2, link a6 with 0 locals

**Description:**

Thin wrapper that sets up the monster processing loop. First checks `level_players_active` (0x904928) — if zero, exits immediately (no monsters move when no players active).

If players are active:
1. Computes screen boundary values for visibility culling:
   - Left boundary: `(scroll_x - 0x17) << 7` → 0x904A62
   - Top boundary: `(0xF9 - scroll_y) << 7` → 0x904A64
2. Finds a starting MOB in the priority bucket table (0x905F82), indexed by Y position of the scroll, reads MOB at that bucket → stores to 0x904A60 (current monster iteration pointer). Falls back to list head at 0x905F80 if bucket is empty.
3. Computes the Y boundary for the bottom-of-screen MOB row.
4. Calls `monster_loop_core` (0x40E6A) with that bottom boundary as a single word arg.

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904928 | R | Active player count |
| 0x904008 | R | Playfield X scroll position |
| 0x90400A | R | Playfield Y scroll position |
| 0x904A60 | W | Current monster iteration pointer |
| 0x904A62 | W | Left screen boundary (pixel, shifted) |
| 0x904A64 | W | Top screen boundary (pixel, shifted) |
| 0x905F80 | R | Priority bucket list head |
| 0x905F82 | R | Priority bucket array base |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x40E6A | monster_loop_core | DONE |

### `monster_generic_handler` — 0x492C0

- **Address:** 0x492C0–0x49598+
- **Arguments:** (mob_id: long, monster_type_index: long, speed: long)
- **Return value:** void
- **Registers saved:** d2-d6, link a6

**Description:**

Core AI for most monster types (ghosts, grunts, demons, lobbers, death). Controls both pathfinding and movement execution.

**Phase 1 — Speed/throttle (0x492C4–0x4931E):**
- If `0x904918 < 0` (throttle/attract mode): uses a global counter at 0x904B7A. Decrements it; when < 0, resets and allows a move with fixed speed (7 for types 0-2, 2 for others). Otherwise skips this frame.
- If normal mode: calls `random_word(32)`. If random >= speed parameter: skip this frame (probabilistic throttle — higher speed = more frequent moves). Otherwise: picks a random starting direction (0..3) for the search.

**Phase 2 — Direction search (0x49320–0x4943C):**
Tries up to 8 directions starting from a random or computed direction:
- Computes candidate tile using direction delta tables at 0x57B50 (X) and 0x57B68 (Y), each with 8 entries for the 8 directions.
- Calls `check_tile_passable` (0x48F12) for the candidate. If blocked, tries next direction.
- If passable: places MOB at new position via `mob_create` (0x5DC58) with position, type, and animation data.

**Key design observations:**
- **Player targeting**: `find_target_player` (0x41750) scans all players, selects nearest by Manhattan distance. Last target cached in 0x9049DC for persistence.
- **Pathfinding**: Direct line only — no flood-fill or A*. Tries up to 8 directions with random start offset biased toward player direction.
- **Movement rate**: Speed parameter (0–31) compared against random(32). Higher speed = more likely to move each frame.
- **Player damage**: Proximity detected when tile_type low nibble >= 0xC (player types). Damage accumulated in 0x904B3A; player killed at threshold 200.
- **Lobber throw**: Distance check 0x14–0x2C tiles, line-of-sight check, trajectory via sin/cos table at 0x580FC.
- **Sorcerer teleport**: Continuous direction-field increment; wrapping produces apparent teleport.

### `monster_loop_core` — 0x40E6A

- **Address:** 0x40E6A–0x41530 (+ second pass 0x41532–0x416F2+)
- **Arguments:** (bottom_boundary: word at 0x32(a7) after register save)
- **Return value:** void
- **Registers saved:** d2-d7/a2-a6 (no link)

**High-level structure:**

Sets up VRAM array pointers (a2=0x902000, a3=0x902800, a4=0x903000, a5=0x903800, a6=0x904066).

**Speed table construction (0x40EEC–0x40F5A):**
Builds a 10-entry speed table on the stack. Default speed = 0x80 for all types. Then checks `level_flags_byte` at 0x90491D — for each "fast monster" flag bit that's set, overrides the corresponding type's speed to 0x100 (double speed) from the ROM override table at 0x40E02.

Then checks `level_flags_byte` at 0x90491C bits 0-6 (masked with 0x73) for per-type speed overrides from the same 0x40E02 table.

**Monster count limit (0x40F5A–0x40FA0):**
Computes maximum monsters to process this frame from `monster_count_table` at 0x40E46, indexed by `(difficulty_setting << 3) + active_player_count - 1`. Adds 0x90405F (per-level bonus count). Caps at `level_number * 2`. If frame overflow flag (0x904916) is set, forces count to 0 (skip all monsters this frame).

**Main MOB walk loop (0x40FAE–0x414D4):**
Walks the linked list via 0x903800 (low 10 bits = next link). For each MOB:

1. Reads type from high byte of 0x903800[d2] (bits 15-10, masked to d6).
2. **Type 0xB8 (generator spawn):** Handles generator logic at 0x40FBE — increments generator tile, checks spawn conditions.
3. **Types 0x48–0xB4 (monsters):** First checks screen visibility (X within 0x7F80 of 0x904A62, Y within 0x8380 of 0x904A64). If off-screen, skips.
   - Types > 0x24 within range: Calls `monster_generic_handler` (0x492C0) with (mob_id, monster_type, speed_from_stack).
   - Type 0x20 (sorcerer): Special sorcerer handler with teleport/appear/disappear states. Reads hpos bit 5 (appearing) and bit 4 (teleporting). Calls 0x5FC46 (random) and 0x5FDE0 (find empty tile). Uses 0x5DE0A to move MOB slot. Animation from 0x58C0A table.
   - Types 0x00–0x1C: Additional special handlers including IT (0x59636 anim), acid puddle.
4. **Animation update (0x414A4–0x414B8):** After movement, updates MOB tile from animation table. Reads direction from low byte of 0x904066[d2], indexes into the idle animation pointer table at 0x40DB2 to get the per-type tile table, then reads tile word and writes to 0x902000[d2].
5. **Loop control (0x414C0–0x414D4):** Reads next link from current entry (0x903800 low 10 bits). If zero, uses list head 0x905F80. Doubles for word index. If equals the starting MOB (saved at 0x2E(a7)), the loop has gone full circle.

**Second pass (0x41532–0x416F2+):** Similar structure but handles generators specifically — types 0x4800–0xB7FF (excluding 0x6C00). Generators spawn new monsters when conditions are met.

**Key sub-calls in monster_loop_core:**
| Address | Name | Brief | Status |
|---------|------|-------|--------|
| 0x4AD76 | play_sound | Sound effects (slow motion start/end) | SHARED |
| 0x492C0 | monster_generic_handler | Main per-monster movement/AI for types > 0x24 | DONE |
| 0x5FC46 | random_word | LCG RNG: seed*0x3619+0x5D35, scaled by range | DONE |
| 0x5FDE0 | find_empty_tile | Spiral search for empty tile near MOB | DONE |
| 0x5DE0A | copy_mob_slot | Copies MOB data between slots | SHARED (Phase 8) |
| 0x4119A | monster_special_handler | Sorcerer teleport/acid spread/IT chase | DONE |
| 0x414A4 | monster_update_anim_tile | Reads direction, indexes anim table, writes tile | DONE (inline) |
| 0x41750 | find_target_player | Finds nearest player by Manhattan distance | DONE |
| 0x41B7E | apply_direction_from_delta | Computes direction from dx/dy between mobs | DONE |
| 0x510FC | compute_target_direction | 8-direction code from monster→player with wraparound | DONE |
| 0x495A6 | monster_move_speed_execute | Core movement: type dispatch, momentum, damage | DONE |
| 0x49498 | spawn_mob_at_position | Spawns mob at player position in slots 0x11-0x14 | DONE |
| 0x48F12 | check_tile_passable | Bounds + occupancy + proximity check for tile | SHARED |
| 0x49A3C | accumulate_hit_damage | Adds damage, kills player at 200 threshold | DONE |
| 0x49A98 | monster_despawn_timer | Per-mob countdown, random respawn on expiry | DONE |

---

## Phase 11 — main_handle_dragon (0x54454) `DONE`

**Category:** Monster AI (dragon) — skipped during dialog

### `main_handle_dragon` — 0x54454
- **Address:** 0x54454–0x54746
- **Args:** None | **Return:** void | **Saves:** d2-d4/a2-a3
- **Description:** Per-frame dragon boss manager. The dragon is a multi-segment creature following a 128-step circular path encoded at ROM 0x5D578. State machine driven by flags at 0x904890 and animation counter at 0x904892. **Head animation**: counter bounces, every 16th step indexes into sprite table at 0x5D508. **Fire breath**: bit 2 of state flags; oscillates counter, every 8 steps reads dragon-fire tile table at 0x5D568. **Forward movement**: increments counter mod 0x7F, reads path control bytes (fire flag, body shape) from path table at 0x5D578. Fire targeting via 0x540E8 (find player in fire arc); launches fireball via 0x54748 which positions projectile using sin/cos offsets from 0x5D428/0x5D430. Body segments updated from path table + 0x5D4B8 lookup. Dragon takes damage tracked at 0x90488C; death via 0x53D10.
- **Key sub-calls:** 0x540E8 (find_player_in_fire_arc), 0x54748 (launch_fireball), 0x53E4A (update_damage_state), 0x53D10 (dragon_death), 0x5FC4E (random, SHARED), 0x5DF68 (spawn_fireball_projectile)
- **Key RAM:** 0x904890 (state flags), 0x904892 (anim counter), 0x904894 (head slot), 0x90488E (segment index), 0x90488C (health), 0x90487C (fire cooldown), 0x904886 (path index)

---

## Phase 12 — main_thief_anim (0x4e8dc) `DONE`

**Category:** Monster AI (thief animation) — skipped during dialog

### `main_thief_anim` — 0x4E8DC
- **Address:** 0x4E8DC–0x4EE08
- **Args:** None | **Return:** void | **Saves:** d2-d5/a2-a3
- **Description:** Per-frame thief FSM. Reads thief slot from 0x904BA4 and state flags from 0x904BA0. Three modes: **Escape animation** (bit 2 set): cycles escape tile animation from table at 0x58C8A, plays escape sound when done. **Steal mode** (bit 3 set): targets player with most items (via 0x4FCF0), marks item stolen in 0x904060-0x904062. **Movement/steering**: computes direction from thief position to target tile using delta tables, manages approaching and fleeing. Walk animation selects tiles from 0x58C9A/0x58D6C (direction-walk-cycle tables). After theft: calls 0x4E4D8 to start fleeing sequence.
- **Key sub-calls:** 0x4FCF0 (find_richest_player), 0x4E1B8 (mark_item_stolen), 0x4E172 (abort_theft), 0x4EE7A (thief_move_engine), 0x4F912 (compute_path), 0x510FC (direction_to_target), 0x4C440 (damage_player), 0x4AD76 (play_sound, SHARED)
- **Key RAM:** 0x904BA4 (thief slot), 0x904BA0 (state flags), 0x904060 (theft lock), 0x904061 (victim player), 0x904062 (stolen item type), 0x904BBC (escape frame counter)

---

## Phase 13 — main_start_thief (0x4deb8) `DONE`

**Category:** Monster AI (thief spawning) — skipped during dialog

### `main_start_thief` — 0x4DEB8
- **Address:** 0x4DEB8–0x4DFF4
- **Args:** None | **Return:** void | **Saves:** d2-d4/a2
- **Description:** Thief spawn/cooldown manager. Timer at 0x904B9E counts down. When zero AND no active thief (0x904BA4 == 0): validates spawn tile at 0x904BBA via 0x48F12 (tile accessibility check). If valid: reads thief variant from state flags bit 7 (normal vs super-thief), selects tile graphic from 0x58D4C or 0x58E1E. Creates MOB via 0x5DC58 with computed pixel coordinates from tile position. Links to target player via 0x47C0E. Initializes path via 0x4F912, plays spawn sound (0x2D for normal, 0x29 for super). Resets animation state. Includes inline sub 0x4DFF6 that scores players by item value (keys=high, potions=medium, gold/treasure=variable) to select the richest target → 0x904B9A.
- **Sub-calls:** 0x48F12 (tile_check, SHARED), 0x5DC58 (mob_create, SHARED), 0x47C0E (link_mob), 0x51000 (init_direction), 0x4F912 (compute_path), 0x4AD76 (play_sound, SHARED)

---

## Phase 14 — main_health_countdown (0x466f6) `DONE`

**Category:** Player health — skipped during dialog

### `main_health_countdown` — 0x466F6
- **Address:** 0x466F6–0x46C5C
- **Args:** None | **Return:** void | **Saves:** d2-d6/a2-a5
- **Description:** Large per-frame health/state manager with 4 sections. **Section 1** (every 64th frame, 0x466F6–0x467A8): decrements health for each active player at 0x904980[d3*4]. If health < 200: calls 0x4C440 (low-health warning) + 0x487CA (dim sprite). **Section 2** (per-player per-frame, 0x467A8–0x46BF9): if health==0 (dead): spawns generator at player position via 0x5DC58, clears slots, decrements active count, checks all-dead → sets 0x904063=0xFF. If alive: processes score accumulator via 0x40628, calls 0x49D0E (score display), 0x452D0 (item effects). Spawns random items using ROM tables at 0x578EA/0x578DA. Manages heartbeat sounds from 0x57942 table. **Section 3**: if someone died this frame, redistributes experience to surviving players. Also contains inline sub 0x46CAA (camera scroll toward active players — same as Phase 9's logic).
- **Key sub-calls:** 0x4C440 (damage_flash, SHARED), 0x487CA (player_sound_sprite_update, SHARED), 0x5DC58 (mob_create, SHARED), 0x47C0E (link_mob), 0x5E064 (mob_remove, SHARED), 0x43360 (remove_player), 0x4590E (transfer_scroll_target), 0x40628 (process_score), 0x49D0E (update_score_display), 0x452D0 (player_cleanup_slot, SHARED), 0x44C7E (update_player_count, SHARED), 0x4E122 (update_thief_target), 0x4AD76 (play_sound, SHARED)

---

## Phase 15 — main_treasure_timer (0x4d29e) `DONE`

**Category:** Economy — skipped during dialog

### `main_treasure_timer` — 0x4D29E
- **Address:** 0x4D29E–0x4D474
- **Args:** None | **Return:** void | **Saves:** d2/a2-a4
- **Description:** Treasure room countdown. Decrements timer at 0x9049E8 each frame. On each full second (timer mod 60 == 0): calls OS 0x272 to display countdown number. At 10 seconds remaining: randomly selects exit door via 0x5FC4E if conditions met. Seconds 6–10 with active state: awards items from ROM table at 0x5ABE0 (per-second item award function pointers), plays sounds. At 0 seconds: calls end-of-treasure-room handler (0x4D476) which plays final jingle, disables thief, clears playfield 0x905000 region, sets transition timer to 300 frames. Sub-function 0x4D900 counts players in alive states (1/2/8/0x10).
- **Sub-calls:** 0x272 (OS: display_number), 0x5FC4E (random, SHARED), 0x4AD76 (play_sound, SHARED), 0x4AD4E (play_music), 0x4D476 (end_treasure_room), 0x452D0 (player_cleanup_slot, SHARED), 0x4D900 (count_active_players)

---

## Phase 16 — main_handle_death (0x4664c) `DONE`

**Category:** Player death — skipped during dialog

### `main_handle_death` — 0x4664C

- **Address:** 0x4664C–0x466F4
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2-d3/a2, link a6 with 0 locals

**Description:**

Manages two per-player damage-sound timer systems: forcefield contact sounds and Death (monster) contact sounds. Iterates d3 = 0..3 over all 4 player slots.

Caches `play_sound` address in a2 (`movea.l #0x4AD76, a2`) and calls via `jsr (a2)` as an optimization to avoid repeated absolute address encoding.

**Timer 1 — Forcefield hurt timer** at `0x904B4A[player*2]`:
- If zero: skip
- If negative: this is a new contact — plays sound 0x2E ("Player Touches Force Field"), negates the value to start the positive countdown
- Decrements by 1 each frame
- When reaches zero: plays sound 0x2F ("Force Field Silencer" — stops the force field sound loop)

**Timer 2 — Death touch timer** at `0x904B42[player*2]`:
- If zero: skip
- If negative: new contact — plays sound 0x20 ("Death Touches Player"), negates to start countdown
- Decrements by 1 each frame
- When reaches zero: plays sound 0x21 ("Death Silencer" — stops the death sound loop)

The pattern is: game code sets these timers to negative values (e.g. -30) when damage starts. This function detects the negative, plays the start sound, flips to positive, counts down, then plays the stop sound. This creates timed looping sound effects that automatically end.

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904B4A | RW | Per-player forcefield hurt timer (word array, 4 entries) |
| 0x904B42 | RW | Per-player Death touch timer (word array, 4 entries) |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x4AD76 | play_sound | SHARED — called via cached a2 register |

**Sound IDs used:**
| ID | Description |
|----|-------------|
| 0x2E | "Player Touches Force Field" (start loop) |
| 0x2F | "Force Field Silencer" (stop loop) |
| 0x20 | "Death Touches Player" (start loop) |
| 0x21 | "Death Silencer" (stop loop) |

---

## Phase 17 — main_exit_move (0x5287c) `DONE`

**Category:** Maze mechanics — skipped during dialog

### `main_exit_move` — 0x5287C
- **Address:** 0x5287C–0x52EC8
- **Args:** None | **Return:** void | **Saves:** d2-d5/a2
- **Description:** Handles "ExitMoves" level flag — periodically relocates the exit. Timer at 0x904A08 counts down. When zero: saves old exit MOB id (0x904A0A → 0x904A0C). Finds next exit position using step table at 0x5B7FC indexed by exit_count (0x904A06), wraps modulo count. Checks new position in 0x902000 — if occupied by player (palette >= 0xC): triggers exit-entering state via inline handler at 0x52B40 which sets player status to 0x08, positions exiting MOB, checks secret trick conditions. Otherwise: removes occupant via 0x5DDDA. Stamps new exit (writes 0x8001 to MOB picture, computes pixel coords, calls 0x5E536 for exit-open animation). Stamps old exit closed. Plays sound 0x31. When timer goes negative: flash animation alternates open/closed tiles at the old and new positions every 4 frames. On player exit: computes next level/maze numbers, awards 500 score, plays per-player exit speech from table at 0x5B788.
- **Key sub-calls:** 0x52B06 (exit_get_id), 0x52B40 (player_exit_handler), 0x5DDDA (mob_unlink, SHARED), 0x5E536 (pf_stamp_update), 0x5E892 (pf_floor_update), 0x4AD76 (play_sound, SHARED), 0x4E122 (thief_exit), 0x5DF80 (exit_create_player_anim), 0x52ECA (maze_checknum)
- **Key RAM:** 0x904A08 (exit timer), 0x904A0A (open exit id), 0x904A0C (close exit id), 0x904A06 (exit count), 0x90491C bit 14 (ExitMoves flag), 0x910740 (exit mob list)

---

## Phase 18 — main_walls_cyclic_move (0x5e62a) `DONE`

**Category:** Maze mechanics — skipped during dialog

### `main_walls_cyclic_move` — 0x5E62A

- **Address:** 0x5E62A–0x5E7A4
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2-d7/a2-a5 (saved only when work is done)

**Description:**

Manages walls that cycle through open/closed/appearing states on a fixed 120-frame (2-second) timer. Only active when level flag bit 3 of `0x90491E` is set (CyclicWalls flag).

**Gate checks (0x5E62A–0x5E658):**
1. Tests bit 3 of `0x90491E` — if clear, no cyclic walls → returns immediately at 0x5E7A4
2. Checks that at least one player has a non-zero MOB slot in `0x9048C8` or `0x9048CC` — if both zero, returns
3. Decrements timer at `0x90401A`. If it was already non-zero before decrement, returns (not time yet). When it hits zero, resets timer to 0x78 (120 frames) and proceeds with the wall cycle.

**Sound (0x5E660–0x5E678):**
If `health_display` (0x904000) < 0x73: plays sound 0x2B ("Cyclic Walls").

**Cycle phase management (0x5E692–0x5E6AC):**
Reads `wall_cycle_phase` byte from `0x90401C`, increments it. If it exceeds 3, wraps to 1. Cycle phases are 1, 2, 3 (phase 0 = unused). Writes new phase back.

**Tile iteration (0x5E6B2–0x5E76C):**
Iterates d3 = 0x20 to 0x3FF (tiles 32–1023, skipping the first row of 32 wall tiles):

- **Every 64th tile** (d3 & 0x3F == 0): clears VBLANK semaphore at `0x904002` to yield to the display system (prevents visual tearing during long operations).
- **Every 4th tile**: reads a cycle-assignment byte from `color_ram_spare` at `0x910600 + d3/4`. Each byte encodes which cycle phase a group of 4 tiles belongs to (2 bits each). Zero = not a cyclic wall → skips the entire group of 4.
- For each tile with a non-zero assignment:
  - Compares the tile's assigned phase (low 2 bits of color byte) against the OLD cycle phase (d5):
    - **Match old phase AND tile has wall (0x902000 == 0x8000):** REMOVE wall — zeros all 4 VRAM words for this slot (picture, hpos, vpos, link). Chains the removed tile via d7 for post-processing.
  - Compares against the NEW cycle phase (d2):
    - **Match new phase AND tile is empty (0x902000 == 0):** PLACE wall — writes wall type code (`(6 + phase) << 10`) to link array, 0x8000 to picture, computes X pixel position from tile column (`d3 << 10`) and Y pixel position from tile row (`(row XOR 0x3E0) << 6`). Chains via d7.

**Post-processing chain (0x5E770–0x5E7A0):**
Walks the chain of modified tiles (linked through d7/a5). For each:
- If picture word is zero (wall was removed): calls `wall_remove_playfield_update` (0x5E888)
- If picture word is non-zero (wall was placed): calls `wall_place_playfield_update` (0x5F024)
Then follows the chain via the low 10 bits of the link word.

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x90491E | R | Level flags (bit 3 = CyclicWalls) |
| 0x9048C8 | R | Player 1+2 MOB slot (longword check) |
| 0x9048CC | R | Player 3+4 MOB slot (longword check) |
| 0x90401A | RW | Cyclic wall timer (word, resets to 0x78) |
| 0x90401C | RW | Current wall cycle phase (byte, 1-3) |
| 0x904002 | W | VBLANK semaphore (cleared for yield) |
| 0x910600 | R | Color RAM spare — cycle phase assignments, 1 byte per 4 tiles |
| 0x904BA4 | R | Some state word (read but purpose unclear in this context) |
| 0x904000 | R | Health display counter |
| 0x902000 | RW | MOB picture array |
| 0x902800 | RW | MOB hpos array |
| 0x903000 | RW | MOB vpos (computed from tile row) |
| 0x904066 | RW | MOB link/direction array |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x4AD76 | play_sound (0x2B) | SHARED |
| 0x5E888 | wall_remove_playfield_update (refresh_floor_visual) | DONE |
| 0x5F024 | wall_place_playfield_update | DONE |

---

## Phase 19 — main_walls_random_move (0x5e41a) `DONE`

**Category:** Maze mechanics — skipped during dialog

### `main_walls_random_move` — 0x5E41A

- **Address:** 0x5E41A–0x5E534
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2/a2-a3 (saved only when processing)

**Description:**

Manages randomly appearing/disappearing walls. Each frame, walks the MOB list looking for WALL_RANDOM tiles and randomly toggles their visibility.

**Gate checks (0x5E41A–0x5E44E):**
1. Checks `game_mode` (0x904918): only runs in NORMAL (0) or DEMO (0xFFFD). Returns for all other modes.
2. Reads timer at `0x9048A6`:
   - If negative (0xFFFF): disabled, returns
   - If zero: falls through to process
   - If positive: decrements. When it hits zero AND current index equals target index (0x9048A2 == 0x9048A4): jumps to reset logic at 0x5E50C

**Walk and toggle (0x5E450–0x5E4F2):**
Walks the MOB link list via `0x903800` from current position `0x9048A4` toward target `0x9048A2`:
- For each tile: reads the type byte from 0x903800 high bits, shifts right 2, checks if == 6 (type 0x18 = WALL_RANDOM)
- When a random wall is found:
  - Calls `random_word` (0x5FC46) with range 32
  - If random result > 15 (50% chance): toggles wall visibility by XORing 0x8000 in `0x902000[tile*2]`. If result is now zero: d1=0 (wall removed); if non-zero: d1=2 (wall appeared). Calls `refresh_tile_visual` (0x5F5A0) to update the display.
  - Updates tracking indices in 0x9048A0/0x9048A4

**Reset logic (0x5E50C–0x5E534):**
When all random walls have been processed:
- Sets timer 0x9048A6 to 0x78 (120 frames = 2 sec) if game_mode >= 0, or 0x3C (60 frames = 1 sec) if attract mode
- Resets target to 0x9048A0 - 1 for the next cycle

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904918 | R | Game mode |
| 0x9048A6 | RW | Random wall timer (negative=disabled, 0=process, positive=countdown) |
| 0x9048A2 | RW | Random wall target index |
| 0x9048A4 | RW | Random wall current index |
| 0x9048A0 | RW | Random wall low water mark |
| 0x903800 | R | MOB link array (type in high bits) |
| 0x902000 | RW | MOB picture array (XOR 0x8000 to toggle visibility) |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x5FC46 | random_word | SHARED (see registry) |
| 0x5F5A0 | refresh_tile_visual | SHARED (see registry) |

---

## Phase 20 — main_msgbox_countdown (0x4ccbc) `DONE`

**Category:** UI/Dialog — always called every frame

### `main_msgbox_countdown` — 0x4CCBC

- **Address:** 0x4CCBC–0x4CD1A
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2-d3, link a6

**Description:**

This IS the `speech_countdown_flush` function documented in the shared registry — the same function serves double duty as both a main-loop phase and a sub-call from other functions (demo_speech_cmd, player_hurt_flash).

Decrements the dialog/message timer at `0x904A9E`. When it reaches zero, clears all pending speech entries from the display ring buffer:

1. Reads timer via `a0 = *(0x904A9E)`. If zero: exits immediately (no active message).
2. Decrements timer. If still non-zero: exits (message still displaying).
3. When timer reaches zero: loops d2 from 0 to `0x904A9C` (speech channel count). For each channel:
   - Inner loop d0 from 0 to `0x904A9A` (string length): walks the speech output pointer at `0x904A96`, reads each word pointer, zeros the word it points to (clears the display text).
   - Advances `0x904A96` by `(0x40 - string_length) * 2` bytes to skip padding between channels.

This effectively removes the on-screen message box text when the display timer expires.

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904A9E | RW | Dialog/message display timer (word) |
| 0x904A9C | R | Speech channel count |
| 0x904A9A | R | Speech string length |
| 0x904A96 | RW | Speech output ring buffer pointer |

**Sub-calls:** None (leaf function)

---

## Phase 21 — pick_character (0x42df4) `DONE`

**Category:** Player setup — always called every frame

### `pick_character` — 0x42DF4
- **Address:** 0x42DF4–0x42E98
- **Args:** None | **Return:** void | **Saves:** d2-d3/a2
- **Description:** Per-frame character selection handler. Iterates 4 player slots. For each slot with coin state == 0x10 (selecting): reads joystick from 0x904920[player*2]+1. Tests directional bits 4-7 in priority order — bit 7 clear→char 0 (warrior), bit 5→char 1 (valkyrie), bit 6→char 2 (wizard), bit 4→char 3 (elf). If selection changed from stored value at 0x9048E8[player*2]: writes new selection and calls 0x452D0 (player_cleanup_slot, SHARED) to update character display.
- **Sub-calls:** 0x452D0 (player_cleanup_slot, SHARED)

---

## Phase 22 — main_start_game (0x4800c) `DONE`

**Category:** Game flow — always called every frame

### `main_start_game` — 0x4800C
- **Address:** 0x4800C–0x486FC (~0x6F0 bytes)
- **Args:** None | **Return:** void | **Saves:** d2-d6/a2-a4
- **Description:** Large state machine managing attract→gameplay transition and mid-game player joining. Checks frame counter at 0x904AC6, attract flag at 0x904928. **State machine** keyed on countdown timer at 0x904A4E and level at 0x904000. **State 0** (start new round): calls 0x486FE (brightness setup), copies level from 0x904B52→0x904004, calls 0x40CF2 (maze init), 0x44DB4 (spawn enemies), 0x438AE (score display), 0x43486 (place players). Plays level-start sounds. **Countdown active**: every 60 frames displays countdown via OS 0x272. **Epilogue**: per-player mid-game join detection — reads fire button state, checks credits, spawns player via 0x48BB6/0x48A36, calls full init sequence (0x40CC4, 0x452D0, 0x436FE, 0x438AE, 0x43486).
- **Key sub-calls:** 0x486FE, 0x40CF2 (maze_init), 0x44DB4 (spawn_enemies), 0x438AE (score_display_setup), 0x43486 (place_players), 0x48BB6 (player_start_in_maze, SHARED), 0x48A36 (player_join), 0x44204 (attract_to_game), 0x488CA (player_init_coin), 0x452D0 (SHARED), 0x4AD76 (SHARED)

---

## Phase 23 — main_score_update (0x4715e) `DONE`

**Category:** Scoring — always called every frame

### `main_score_update` — 0x4715E
- **Address:** 0x4715E–0x474F4 (+ large sub at 0x474F6–0x47C0C)
- **Args:** None | **Return:** void | **Saves:** d2-d4/a2-a3
- **Description:** Three loops. **Loop 1** (d4=0..3, generators): decrements spawn timers at 0x90493A[d4*2]. When zero: kills generator MOB via 0x5E064(d4+0x10), clears 0x902000[(d4+0x11)*2]. **Loop 1b** (player 0 only, score star): animates score-star MOB at 0x902000[0x3A]. Frame milestones at d3=5 (save thief, kill via 0x5DDDA), d3=0xB (spawn new thief via 0x47CFE), d3=0x10 (restore), d3>=0x17 (cleanup via 0x5E064(0x1C), redraw via 0x4F912). **Loop 2** (d4=0..3, per-player score animations): same milestone structure using 0x50616/0x50662/0x50B88 for phases. **Loop 3** (d4=0..12, MOB animations): iterates entity MOB slots (0xD+), updates animation counters at 0x90497C, selects tiles from tables at 0x576B6/0x576D2/0x576DA based on value ranges. The sub-function at 0x474F6 manages all 12 active MOB positions, advancing sub-pixel accumulators from velocity tables.
- **Key sub-calls:** 0x5E064 (mob_remove, SHARED), 0x5DDDA (mob_unlink, SHARED), 0x47CFE (spawn_thief_mob), 0x510FC/0x51000 (score_display_helpers), 0x4F912 (redraw), 0x50616/0x50662/0x50B88 (score_anim_phases)

---

## Phase 24 — main_score_display (0x457c0) `DONE`

**Category:** Display — always called every frame

### `main_score_display` — 0x457C0
- **Address:** 0x457C0–0x45864
- **Args:** None | **Return:** void | **Saves:** link a6
- **Description:** Per-frame score/health HUD updater. Returns immediately in TITLE (0xFFFE) or SCORES (0xFFFF) modes. Selects one player per frame using `frame_counter & 3` → d0. Checks player status at 0x9049A0: if 4 (unused), skips. If player has MOB pointer at 0x904980: checks update flags at 0x904908. Bit 2 of 0x904007 AND bit 0 of flags → calls 0x45940 (flash_score_display: draws score digits with flash attribute via OS 0x260, clears bit 0). Bit 1 of flags OR health < 0xC8 → calls 0x459A2 (update_health_bar: draws health bar MOBs, adjusts tile base for poison/powered states using 0x904A26 and 0x905F40, renders via OS 0x260, clears bit 1). Also calls 0x45866 (display_score_for_player) to update character portrait and score digits in the HUD MOB table at 0x905048.
- **Key sub-calls:** 0x45940 (flash_score), 0x459A2 (update_health_bar), 0x45866 (display_score), 0x4AD76 (play_sound, SHARED), OS 0x260

---

## Phase 25 — main_attract (0x44562) `DONE`

**Category:** Attract mode state machine — always called every frame

### `main_attract` — 0x44562
- **Address:** 0x44562–0x449CA (~0x468 bytes, plus inline subs through 0x44DB4)
- **Args:** None | **Return:** void | **Saves:** d2-d4/a2
- **Description:** The attract-mode / treasure-room state machine. Uses game_state at 0x904918 (signed: negative = attract substates, 0 = in-game, positive = countdowns) and timer at 0x904B7C. **State -1** (0xFFFF, title screen): timer threshold 540 frames (9 sec). Tests joystick for 2-player start → 0x44414(-1). Tests 1-player → 0x44414(-2). **State -2** (0xFFFE, high-scores): threshold 1441 frames (24 sec). Same input checks. **State -3** (0xFFFD, legend/how-to-play): threshold 7140 frames (119 sec). Tests D-pad input. **Transition to demo** (0x447AC): sets state -4 (0xFFFC), clears playfield via 0x4529A, draws attract art via 0x452D0(-1), starts demo via 0x44414(-4). **State -4** (demo gameplay): manages demo level cycling via 0x90491A (demo level counter), loads levels via 0x4CD1C. **Timer expiry cycling**: advances through states -1→-2→-3→-4→-1. **In-game (state 0)**: every 60 frames displays countdown via OS 0x260 at row 0xD. Inline sub 0x449D4 (init_attract_title): loads demo level 0x66, initializes demo sequence, sets up 4 players. Inline sub 0x44C7E: draws character-select screen with portraits and "INSERT COIN" text. Inline sub 0x44DB4: thief-in-attract animation.
- **Key sub-calls:** 0x44414 (set_attract_state), 0x4529A (clear_playfield), 0x452D0 (SHARED), 0x4341E (clear_display), 0x4CD1C (load_demo_level), 0x44204 (attract_to_game), 0x438AE (score_setup), 0x43486 (place_players), 0x48BB6 (SHARED), 0x40D24 (load_level_tileset), 0x4AD76 (SHARED), 0x5FC4E (SHARED), OS 0x260/0x272

---

## Phase 26 — eeprom_timer (0x431ee) `DONE`

**Category:** Persistence — always called every frame

### `eeprom_timer` — 0x431EE

- **Address:** 0x431EE–0x43278
- **Arguments:** None
- **Return value:** void
- **Registers saved:** link a6 with 0 locals (no other saves — lightweight)

**Description:**

Periodically writes game settings to EEPROM to persist them across power cycles. Uses a countdown timer to avoid writing every frame (EEPROM has limited write endurance).

**Timer management (0x431F2–0x43200):**
Reads longword timer at address stored in `0x904012` (pointer to timer variable). If non-zero, decrements it. If still non-zero after decrement, returns immediately (not time to check yet).

**When timer expires (0x43204–0x43270):**
Resets timer to 0x8CA0 (36,000 frames ≈ 10 minutes at 60Hz). Then compares 6 RAM values against their cached "last written" copies to detect changes:

| RAM value | Cache (last written) | Description |
|-----------|---------------------|-------------|
| 0x904010 (word) | 0x904B8E (byte) | High scores page / stat byte 1 |
| 0x90400E (word) | 0x904B8F (byte) | Stat byte 2 |
| 0x904018 (word) | 0x904B90 (byte) | Stat byte 3 |
| 0x904016 (word) | 0x904B91 (byte) | Stat byte 4 |
| 0x904B86 (word) | 0x904B92 (word) | Game stats word |
| 0x904A24 (word) | 0x904B94 (word) | Game settings/options |

If ALL values match their caches: no write needed, returns. If ANY differ: calls `eeprom_write` (0x43192) to flush all values.

**Sub-calls:**
| Address | Name | Description | Status |
|---------|------|-------------|--------|
| 0x43192 | eeprom_write | Copies 6 values to write buffer at 0x904B8E, calls OS 0x24E to write EEPROM | DONE |

### `eeprom_write` — 0x43192

- **Address:** 0x43192–0x431EC
- **Arguments:** None
- **Return value:** void

**Description:**
Copies the 6 monitored RAM values into the write buffer at `0x904B8E` (4 bytes + 2 words = 8 bytes total). Then calls OS API `0x24E` (EEPROM write) with args: (buffer_ptr=0x904B8E, offset=0, count=1). This writes the cached game settings block to the EEPROM hardware at 0x802001.

---

## Phase 27 — sound_response (0x42d0a) `DONE`

**Category:** Audio — always called every frame

### `sound_response` — 0x42D0A

- **Address:** 0x42D0A–0x42DC6
- **Arguments:** None
- **Return value:** void
- **Registers saved:** a2-a3, link a6 with 0 locals

**Description:**

Processes responses from the sound CPU (the TMS5220 speech chip / Pokey / YM2151 subsystem). The sound CPU communicates asynchronously via hardware ports, and this function polls for and handles incoming responses.

Caches `sound_system_reset` function address in a2 (0x42DC8) and speech-enabled counter pointer in a3 (→ 0x9049EE).

**Step 1 — Poll sound CPU (0x42D1E):**
Calls OS API `0x178` (read sound CPU response). Returns 0xFFFF if no data available, otherwise the response byte in d0.

**Step 2 — Response dispatch (0x42D24–0x42D4E):**
- If 0xFFFF (no data): skip to step 3
- If speech counter (a3) is non-zero AND response == 0xFF: clears speech counter (speech finished) → go to step 3
- Otherwise: calls `sound_system_reset` (a2 = 0x42DC8) to re-sync the sound subsystem → done

**Step 3 — Idle processing (0x42D40–0x42DBE):**
Reads `sound_queue_state` at 0x9049F0. If low 3 bits are non-zero: calls `sound_system_reset` (re-sync needed) → done.

Otherwise: if speech counter 0x9049EE is non-zero, decrements it. When it reaches zero: calls `sound_system_reset` → done.

If speech counter already zero: decrements `sound_idle_timer` at 0x9049F2. When it goes negative:
- Clears 0x9049F0 (queue state)
- Calls OS `0x172` (send sound command) with args (7, 0x9049F0+1, 1) — sends an "are you there?" ping to the sound CPU
- If OS returns non-zero (sound CPU responded): resets idle timer to 0xF0 (240 frames), clears retry counter 0x9049F4
- If zero (no response): clears idle timer, increments retry counter at 0x9049F4. If retries exceed 0xB4 (180): calls `sound_system_reset` (full reset after ~3 seconds of no response)

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x9049EE | RW | Speech-in-progress counter (non-zero = speech playing) |
| 0x9049F0 | RW | Sound queue state word |
| 0x9049F2 | RW | Sound idle timer (countdown between pings) |
| 0x9049F4 | RW | Sound CPU retry counter |

**Sub-calls:**
| Address | Name | Description | Status |
|---------|------|-------------|--------|
| 0x178 | OS: read_sound_response | Polls sound CPU for response byte | DONE (OS API) |
| 0x172 | OS: send_sound_command | Sends command to sound CPU | DONE (OS API) |
| 0x42DC8 | sound_system_reset | Resets sound subsystem (see below) | DONE |

### `sound_system_reset` — 0x42DC8

- **Address:** 0x42DC8–0x42DF2
- **Arguments:** None
- **Return value:** void

**Description:**
Full sound subsystem reset. Calls OS `0x254` (hardware sound reset) with args (0, 0). Sets speech counter 0x9049EE to 0xB4 (180 frames grace period). Clears queue state 0x9049F0 and retry counter 0x9049F4. Calls `sound_queue_reset` (0x4ADAE) to flush the sound command ring buffer (fills 0x90404B[0..7] with 0xFF, zeros read/write heads at 0x904053/0x904054).

---

## Phase 28 — main_update_sound (0x4ae20) `DONE`

**Category:** Audio — always called every frame

### `main_update_sound` — 0x4AE20

- **Address:** 0x4AE20–0x4AE9E
- **Arguments:** None
- **Return value:** void
- **Registers saved:** d2/a2 (no link — uses movem only)

**Description:**

Drains the sound command ring buffer by sending queued sound commands to the hardware sound CPU. Called every frame.

**Gate checks (0x4AE24–0x4AE3A):**
- If `frame_overflow` (0x904916) is non-zero: skip (don't send sounds during frame overruns, to save time).
- If `speech_counter` (0x9049EE) is non-zero: skip (speech in progress, don't interrupt).

**Ring buffer drain loop (0x4AE3E–0x4AE98):**
`a2` points to the read-head byte at `0x904054`. Loop runs up to 8 iterations (d2 = 0..7):

1. Compare read-head (`*a2`) against write-head at `0x904053`. If equal: buffer empty → exit.
2. Read sound ID byte from ring buffer: `0x90404B[read_head]`.
3. Sign-extend to longword, push as arg, call OS `0x242` (send sound command to hardware).
4. If OS returns zero (hardware busy, couldn't accept): exit loop (will retry next frame).
5. If OS returns non-zero (accepted): write 0xFF to the buffer slot (marks as consumed). Advance read-head: `read_head = (read_head + 1) & 7`.
6. **Delay loop:** Executes a brief busy-wait (`moveq 4, d0; subq 1, d0; tst d0; bge loop` — 5 iterations ≈ a few microseconds). This gives the sound CPU time to process between consecutive commands.
7. Increment d2, loop back to drain more.

**RAM variables:**
| Address | R/W | Description |
|---------|-----|-------------|
| 0x904916 | R | Frame overflow flag |
| 0x9049EE | R | Speech-in-progress counter |
| 0x904054 | RW | Sound ring buffer read-head (byte, 0–7) |
| 0x904053 | R | Sound ring buffer write-head (byte, 0–7) |
| 0x90404B | RW | Sound ring buffer (8 bytes) |

**Sub-calls:**
| Address | Name | Status |
|---------|------|--------|
| 0x242 | OS: send_sound_command | DONE (OS API) |
