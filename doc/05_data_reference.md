# Gauntlet II — Data Reference

*RAM variable map, enums and constants, data structures, and ROM data tables catalog.*

---

## 1. Game RAM Variables (`0x904000–0x904FFF`)

*Note: `0x904908` is `player_redraw`, NOT `player_state`. Player status is at `0x9049A0`. Player health is a 32-bit longword at `0x904980`. See `08_known_issues.md` items 1.4 and 1.5.*

### 1.1 Core Game State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904000 | 2 B | `mazenum_current` | Current maze (not level) number |
| 0x904002 | 2 B | `vblank_semaphore` | Set by VBLANK handler; cleared by main loop after processing |
| 0x904004 | 2 B | `levelnum_current` | Current level (not maze) number |
| 0x904006 | 2 B | `framecount` | Frame counter (incremented every VBLANK) |
| 0x904008 | 2 B | `scrollreg_H` | Horizontal scroll register shadow |
| 0x90400A | 2 B | `scrollreg_V` | Vertical scroll register shadow |
| 0x90400C | 2 B | `playfieldbank` | Current playfield (maze) bank |
| 0x90400E | 2 B | `mazerand_adder` | Added to existing maze number to get next maze |
| 0x904010 | 2 B | `mazerand_num` | Next level is this number + mazerand_adder |
| 0x904012 | 4 B | `timer_eepromwrite` | Countdown timer for when to next write EEPROM data |
| 0x904016 | 2 B | `treas_mazerand_adder` | Same as mazerand_adder, but for treasure rooms |
| 0x904018 | 2 B | `treas_mazerand_num` | Same as mazerand_num, but for treasure rooms |
| 0x90401A | 2 B | `wallcycle_time` | Related to wall cycling |
| 0x90401C | 2 B | `wallcycle_type` | Related to wall cycling |
| 0x90401E | 2 B | `playfield_colorsave1` | Temp save for old playfield color |
| 0x904020 | 2 B | `playfield_colorsave2` | Temp save for old playfield color 2 |
| 0x904022 | 2 B | `potion_player` | Which player used a potion |
| 0x904024 | 2 B | `collision_dist_H` | Horizontal object collision distance |
| 0x904026 | 2 B | `collision_dist_V` | Vertical object collision distance |
| 0x904028 | 2 B | `shothit_dist_H` | Horizontal shot collision distance |
| 0x90402A | 2 B | `shothit_dist_V` | Vertical shot collision distance |
| 0x90402C | 2 B | *(unknown)* | Something to do with traps |
| 0x90402E | 2 B | *(unknown)* | Something to do with stuns |
| 0x904030 | 2 B | `tport_cycle_pos` | Transporter position counter (bounces 0→4→0) |
| 0x904032 | 2 B | `tport_cycle_dir` | Transporter cycle direction (±1) |
| 0x904034 | 2 B | `tport_cycle_divider` | 2-bit sub-frame divider; ticks every 4th frame |
| 0x904036 | 4 B | `ptr_playfield_color1` | Pointer to 1st playfield color set |
| 0x90403A | 4 B | `ptr_playfield_color2` | Pointer to 2nd playfield color set |
| 0x90403E | 4 B | `ptr_playfield_color3` | Pointer to 3rd playfield color set |
| 0x904042 | 4 B | `ptr_ff_color` | Pointer to forcefield color entry in Color RAM |
| 0x904046 | 2 B | `forcefield_color` | Current forcefield color word |
| 0x904048 | 2 B | `ff_cycle_timer` | Forcefield color cycle step timer |
| 0x904049 | 1 B | `ff_cycle_index` | Current step index into forcefield color table (0–7) |
| 0x90404B | 8 B | `soundqueue` | Array of 1-byte sound IDs in the queue |
| 0x904053 | 1 B | `soundqueue_head` | Head of sound queue |
| 0x904054 | 1 B | `soundqueue_tail` | Tail of sound queue |
| 0x904055 | 4 B | `player_potionsnum` | Array of 1-byte counters: potions per player |
| 0x90405A | 4 B | `player_keysnum` | Array of 1-byte counters: keys per player |
| 0x90405F | 1 B × 4 | `bonus_byte` | Decremented by 1 on coin insert (if positive). Cleared during player join. Possibly per-player difficulty-bonus credit tracker. |

### 1.2 MOB Animation Array

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904066 | 2 B × 1024 | `mob_anim[]` | Per-MOB: bits 15-13=anim counter, bits 12-10=direction, bits 9-0=back-link |

### 1.3 Secret Room State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904063 | 1 B | `trick_player` | Which player completed the secret trick |
| 0x904064 | 1 B | `trick_last` | Last secret trick completed |
| 0x904065 | 1 B | `trick_tasknum` | Trick task number / `secret_room_active` flag |

### 1.4 Maze Decompression

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904866 | 2 B | `maze_decomp_htype1` | Maze decompression horizontal special element type 1 |
| 0x904868 | 2 B | `maze_decomp_htype2` | Maze decompression horizontal special element type 2 |
| 0x90486A | 2 B | `maze_decomp_vtype1` | Maze decompression vertical special element type 1 |
| 0x90486C | 2 B | `maze_decomp_vtype2` | Maze decompression vertical special element type 2 |
| 0x90486E | 2 B | `secret_need_hint` | Set if next level should show a secret room hint |
| 0x904870 | 2 B | `secret_prev_maze` | Maze number when secret room was triggered |
| 0x904872 | 4 B | `secret_tricks_flags` | Array of 4 × 1B: per-player progress toward secret trick goal |
| 0x904878 | 2 B | `secret_possible_counter` | Counts down; when 0, secret room entry is possible |
| 0x90487A | 2 B | `secret_possible_start` | Starting value for secret_possible_counter |

### 1.5 Dragon State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x90487C | 2 B | `dragon_stun_timer` | Countdown while dragon is stunned |
| 0x90487E | 1 B | `dragon_encounter_flag` | Bit 0 = encounter triggered this level |
| 0x90487F | 1 B | *(unknown)* | Possibly power dialog flags |
| 0x904880 | 2 B | `dragon_hits` | Number of hits on the dragon |
| 0x904882 | 2 B | `dragon_target_hpos` | Horizontal position of current target player |
| 0x904884 | 2 B | `dragon_target_vpos` | Vertical position of current target player |
| 0x904886 | 2 B | `dragon_rand_dir` | Random direction preference for dragon movement |
| 0x90488C | 2 B | `dragon_move_state` | Dragon health tracking / movement sub-state |
| 0x90488E | 2 B | `dragon_facing` | Current facing direction (0–3 or 0–7) |
| 0x904890 | 2 B | `dragon_state` | State bitmask (see Dragon Activity enum) |
| 0x904892 | 2 B | `dragon_anim_ctr` | Animation counter (negative = waking, positive = active) |
| 0x904894 | 2 B | `dragon_mob_id` | Dragon's MOB slot ID (direct word value, not a pointer) |
| 0x90489C | 4 B | `ptr_exit_openclose_anim` | Pointer to exit open/close animation for current tileset |

### 1.6 Wall Randomizer

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x9048A0 | 2 B | *(unknown)* | Wall randomizer state |
| 0x9048A2 | 2 B | *(unknown)* | Wall randomizer state |
| 0x9048A4 | 2 B | *(unknown)* | Wall randomizer state |
| 0x9048A6 | 2 B | *(unknown)* | Wall randomizer state |

### 1.7 Player State Arrays

*All player arrays are indexed by player number (0–3)*

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x9048A8 | 2 B × 4 | *(unknown)* | Something to do with shots, indexed by player |
| 0x9048B2 | 2 B | `poison_timer` | Timer for slowdown from poison |
| 0x9048BC | 2 B | `thief_speed` | How fast the thief moves |
| 0x9048BE | 2 B × 4 | `reflect_count` | Number of times a player's shot has reflected |
| 0x9048C6 | 2 B | `escape_timer` | Frames since a player was last hit; at 20000, all walls turn to exits |
| 0x9048C8 | 2 B × ? | *(unknown)* | Might hold player's current maze location |
| 0x9048E0 | 2 B × 4 | `player_powers` | Per-player power bits (see Character Powers enum) |
| 0x9048E8 | 2 B × 4 | `player_character` | Per-player character identity (0=Warrior, 1=Valkyrie, 2=Wizard, 3=Elf) |
| 0x9048F0 | 2 B × 4 | `player_joystick` | Per-player last joystick direction |
| 0x9048F8 | 2 B × 4 | `lobber_shot_vec_h` | Horizontal component for lobber shots |
| 0x904900 | 2 B × 4 | `lobber_shot_vec_v` | Vertical component for lobber shots |
| **0x904908** | **1 B × 4** | **`player_redraw`** | **Per-player redraw flags. NOT player_state — see `08_known_issues.md` item 1.4** |
| 0x90490C | 2 B | `idle_timer` | Counts up if nothing happening; at 0xFFFF, doors have timed out |
| 0x90490E | 2 B × 4 | `player_bonusmult` | Per-player current bonus multiplier |
| 0x904876 | 2 B | `current_player` | Index (0–3) of the player currently being processed by `main_move_players`; written each iteration of the per-player loop |
| 0x904916 | 2 B | `frame_overflow` | Non-zero if frame took too long to render |
| 0x904918 | 2 B | `game_mode` | Game mode (see Game Modes enum) |
| 0x90491A | 2 B | `attract_legend` | Current legend screen number |
| 0x90491C | 4 B | `level_flags` | Flags for current level |
| 0x904920 | 2 B × 4 | `player_input_raw` | Per-player raw joystick input word |
| 0x904928 | 2 B | `level_players_active` | Number of active players on a level |
| 0x90492A | 2 B × 8 | `shot_timer_next` | Time until next demon/lobber shot |
| 0x904942 | 2 B × ? | *(unknown)* | Might be shot positions (0x0=upper left, 0x3FF=lower right) |
| 0x904B02 | 2 B | `shot_wall_stuck` | Wall-stuck counter for shot projectiles; checked by `main_handle_shots` |
| 0x90497C | 1 B × 4 | *(unknown)* | Related to explosion animation |
| **0x904980** | **4 B × 4** | **`player_health`** | **Per-player health (32-bit longwords). NOT 16-bit — see `08_known_issues.md` item 1.5** |
| 0x904990 | 4 B × 4 | `player_score` | Per-player current score (32-bit longwords) |
| 0x9049A0 | 1 B × 4 | `player_status` | Per-player status: 0x01=alive here, 0x02=alive next, 0x04=entering initials, 0x08=exiting, 0x10=selecting character, 0x20=entering, 0x04=dying |
| 0x9049A4 | 2 B × 4 | `player_facing_dir` | Per-player facing direction (0=up, 1=up-right, 2=right, 3=down-right, 4=down, 5=down-left, 6=left, 7=up-left) |
| 0x9049AC | 2 B × 4 | `player_fighting_dir` | Per-player fighting direction (1=up, 2=up-right, ..., 8=up-left) |
| 0x9049B4 | 2 B × 4 | `player_shooting` | Per-player: 0xFFFF if shooting, 0 otherwise |
| 0x9049BC | 2 B × 4 | `player_anim_counter` | Per-player free-running animation frame counter (incremented every active frame). Divided and masked to index walking/fighting/idle animation tables. Counter ÷4 &3 = walking frame; ÷2 &7 = fighting frame. |
| 0x9049C4 | 2 B × 12 | *(unknown)* | Direction player or mob shot is moving |
| 0x9049DC | 2 B | `player_it` | Player who is IT (0–3) or 0xFFFF (-1) if nobody |
| 0x9049DE | 2 B | *(unknown)* | Something to do with MOB IDs; camera target |
| 0x9049E0 | 2 B | *(unknown)* | Something to do with MOB IDs; level start slot |
| 0x9049E2 | 2 B | `two_player_mode` | Game pricing/two-player mode config |
| 0x9049E4 | 4 B | `dialog_first_encounter_flags` | Bitmask of which first-encounter dialogs have been shown |
| 0x9049E8 | 2 B | `treasure_timer` | Time spent in treasure room |
| 0x9049EA | 4 B | `last_coin_state` | Cached coin counter for edge detection |
| 0x9049EE | 2 B | *(unknown)* | Related to sounds |
| 0x9049F0 | 2 B | *(unknown)* | Related to sounds |
| 0x9049F2 | 2 B | *(unknown)* | Related to sounds |

### 1.8 Exit State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A06 | 2 B | `exit_count` | Number of exits in maze |
| 0x904A08 | 2 B | `exit_timer` | Timer until exit moves (ExitMoves flag) |
| 0x904A0A | 2 B | `exit_open_id` | MOB ID of exit currently opening |
| 0x904A0C | 2 B | `exit_close_id` | MOB ID of exit currently closing |
| 0x904A0E | 2 B | `movement_blocked` | Set non-zero by `player_try_move` when movement is blocked; used by `main_move_players` to keep current facing direction |

### 1.9 Logo / Color Cycling

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A10 | 4 B | `logo_scroll_ptr` | ROM scroll record pointer for title animation |
| 0x904A14 | 2 B | `logo_scroll_timer` | Logo scroll animation timer |
| 0x904A16 | 2 B | `logo_color_dir` | Color direction (+/- for pulsing) |
| 0x904A18 | 2 B | `logo_cycle_timer` | Outer color cycle timer. Reset value from ROM at `0x5BA68`. |
| 0x904A1A | 2 B | `logo_bright_timer` | Inner brightness timer. Reset value from ROM at `0x5BA6A`. |
| 0x904A1C | 2 B | `logo_bright_accum` | Brightness accumulator (via a3 pointer). Clamped between ROM min `0x5BA6C` and max `0x5BA6E`. |
| 0x904A1E | 2 B | `logo_color_cur` | Current logo color value; written to color RAM at `0x910332`. |
| 0x904A20 | 4 B | `logo_anim_ptr` | ROM animation sequence pointer (advances by 2 each cycle through table at `0x5AC20`). |
| 0x910204 | W | `color_ram_mob_pal` | Color RAM MOB palette start; shifted each frame for logo rainbow effect (7 words copied from 0x910206 → 0x910204, 10 rows × 16-byte stride). |
| 0x910332 | W | `color_ram_logo_bright` | Color RAM entry written each frame with current logo brightness value. |

### 1.10 Game Settings

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A24 | 2 B | `game_settings` | Game settings from EEPROM. See bit layout below. |
| 0x904A26 | 2 B × 4 | *(unknown)* | Per-player: time left to enter initials? |
| 0x904A2E | 2 B × 4 | *(unknown)* | Per-player: initial entry acceleration |
| 0x904A36 | 2 B × 4 | *(unknown)* | Per-player: related to initial entry |
| 0x904A3A | 4 B × 4 | *(unknown)* | Per-player: buffer for storing initials during entry |
| 0x904A4A | 1 B × 4 | *(unknown)* | Per-player: position in high score chart |

**`game_settings` (0x904A24) bit layout:**

| Bits | Meaning |
|------|---------|
| 0–4 | COINHEALTH setting (indexes health_per_coin table at 0x57862) |
| **5–7** | **Unknown** |
| 8–9 | Difficulty level (0–3) |
| 10 | 2-player mode flag |
| 11 | Sound mute flag |
| 12 | ROM version flag (cleared after first boot) |
| **13** | **Unknown** |
| 14 | Music/attract sound enable |
| 15 | Settings dirty flag |

### 1.11 Player Extended State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A4E | 2 B | *(unknown)* | Delay time between levels |
| 0x904A50 | 1 B × 4 | `player_treascount` | Count of treasures picked up by player |
| 0x904A54 | 2 B × 4 | `player_stundelay` | Timer for player being stunned |
| 0x904A5C | 2 B | `death_hits` | Number of times Death has been hit/shot |
| 0x904A5E | 2 B | *(unknown)* | State variable; cleared to 0 by `one_time_init` |
| 0x904A64 | 2 B | *(unknown)* | Possibly what part of the screen is visible (H) |
| 0x904A66 | 2 B | *(unknown)* | Possibly what part of the screen is visible (V) / lobber shots |
| 0x904A6E | 2 B × 4 | *(unknown)* | Something to do with lobber shots |
| 0x904A76 | 2 B × 8 | *(unknown)* | Something related to doors (door animation slot positions) |
| 0x904A86 | 2 B × 8 | *(unknown)* | Door animation slot states |

### 1.12 Dialog State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A96 | 4 B | `ptr_dialog_pos` | Pointer to dialog position in alpha RAM |
| 0x904A9A | 2 B | `dialog_dim_H` | Dialog horizontal dimension |
| 0x904A9C | 2 B | `dialog_dim_V` | Dialog vertical dimension |
| 0x904A9E | 2 B | `dialog_timer` | Active timer for dialog display; non-zero skips gameplay in main loop |
| 0x904AA0 | 2 B | `ptr_dialog_box_x` | Dialog X position pointer |
| 0x904AA2 | 2 B | `ptr_dialog_box_y` | Dialog Y position pointer |
| 0x904AA4 | 30 B | `ptr_dialog_msg` | Buffer for dialog message string |

### 1.13 Player Death / Respawn

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904AC6 | 4 B | *(unknown)* | Something related to welcoming players |
| 0x904ACA | 1 B × 4 | *(unknown)* | Per-player: related to dying / animation lock |
| 0x904ACE | 2 B × 4 | *(unknown)* | Per-player: respawn timer (0xFFFF = not dying) |
| 0x904AD6 | 2 B × 4 | *(unknown)* | Per-player: damage taken accumulator |
| 0x904ADE | 2 B × 4 | *(unknown)* | Per-player: damage taken / health |
| 0x904AF6 | 1 B × 4 | `player_eatcount` | Per-player count of foods eaten |
| 0x904AFA | 2 B × 4 | *(unknown)* | Possibly timer related to players taking damage |

### 1.14 Score and Coin State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904B1A | 4 B × 4 | `player_scorepercoin` | Per-player calculated score per coin |
| 0x904B2A | 2 B × 4 | `player_coincount` | Per-player number of coins inserted |
| 0x904B32 | 2 B × 4 | `player_onlevel` | Per-player what level player is on |
| 0x904B3A | 2 B × 4 | `player_dmgtaken_death` | Per-player amount of damage taken from Death |
| 0x904B42 | 2 B × 4 | *(unknown)* | Per-player something related to dying |
| 0x904B4A | 2 B × 4 | *(unknown)* | Per-player something related to dying |

### 1.15 Level / Maze State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904B52 | 2 B | `level_next` | Number of next level |
| 0x904B54 | 2 B | `maze_next` | Number of next maze |
| 0x904B56 | 2 B | *(unknown)* | Score for a pile of money (from dead thief) |
| 0x904B58 | 2 B | *(unknown)* | Floor color number |
| 0x904B5A | 2 B | *(unknown)* | Wall color number |
| 0x904B5C | 2 B | *(unknown)* | Floor pattern number |
| 0x904B5E | 2 B | *(unknown)* | Wall pattern number |
| 0x904B60 | 2 B | `attract_count` | Number of times through attract sequence |
| 0x904B66 | 4 B × 4 | `demo_ptr` | Per-player demo data pointer (longwords) |
| 0x904B76 | 1 B × 4 | `demo_timer` | Per-player demo frame timer (bytes) |
| 0x904B7A | 2 B | *(unknown)* | Timer related to monster generation |
| 0x904B7C | 2 B | `attract_timer` | Timer until next attract screen (or continue_screen_inhibit) |
| 0x904B7E | 2 B | `level_next_potion` | Level countdown to next hidden potion |
| 0x904B80 | 2 B | `level_next_treasure` | Level countdown to next treasure room |
| 0x904B82 | 2 B | `attract_title_count` | Title screen count; used to time theme music |
| 0x904B84 | 2 B | `level_tport_count` | Number of transporters on current level |
| 0x904B86 | 2 B | *(unknown)* | Game count |
| 0x904B88 | 4 B | `ptr_maze_data` | Pointer to current maze data |
| 0x904B8C | 2 B | `maze_slapstic_cmd_offset` | Offset to activate bank switch for current level |

### 1.16 Thief / Mugger State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904B98 | 2 B | `thief_victim_pos` | Last position of thief's target |
| 0x904B9A | 2 B | `thief_victim` | Player number of richest player |
| 0x904B9C | 2 B | *(unknown)* | Something to do with thief |
| 0x904B9E | 2 B | `thief_enter_time` | Timer for thief entrance to level |
| 0x904BA0 | 2 B | `thief_mode` | Thief's current mode (see Thief Modes enum) |
| 0x904BA2 | 2 B | *(unknown)* | Something for thief |
| 0x904BA4 | 2 B | *(unknown)* | Something for thief |
| 0x904BA6 | 2 B | *(unknown)* | Something for thief / thief animation |
| 0x904BA8 | 4 B | `mugger_item_nextlevel` | Item that the mugger carried to the next level |
| 0x904BAC | 4 B | `thief_item_nextlevel` | Item that the thief carried to the next level |
| 0x904BB0 | 4 B | `mugger_item_carried` | Item that the mugger is currently carrying |
| 0x904BB4 | 4 B | `thief_item_carried` | Item that the thief is currently carrying |
| 0x904BBA | 2 B | `thief_start_location` | Location of thief victim at start of level |
| 0x904BBC | 2 B | `thief_stolen_item` | Tile type of last item stolen by thief |

### 1.17 Transporter State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904BC0 | 2 B | *(unknown)* | Timer related to treasure room |
| 0x904BC2 | 2 B | *(unknown)* | Treasure room timer countdown |
| 0x904BC4 | 4 B | `ptr_tport_pic_save` | Longword pointer to per-slot saved MOB picture array |
| 0x904BC8 | 4 B | *(unknown)* | Transporter-related |
| 0x904BCC | 2 B | `tport_saved_mob_state` | Saved MOB state during transport (word) |
| 0x904BCE | 4 B | `ptr_tport_phase` | Longword pointer to per-slot transport phase array. **Also read by** `main_scroll_playfield` as per-player "in maze" flag (negative = active) — possible dual use. |
| 0x904BD6 | 4 B | `ptr_tport_frame_ctr` | Longword pointer to per-slot frame counter array |
| 0x904BD8 | 4 B | `ptr_tport_dest` | Longword pointer to per-slot destination slot array. **Also read by** `compute_screen_coords` (0x4CB50) and `main_scroll_playfield` (0x46CAA) as per-player tile position (words, stride 2). Likely dual-purpose: transporter destination = player tile location. |
| 0x904BE0 | 2 B | `tport_transition_mob` | MOB slot used for transition effect |
| 0x904BE2 | 4 B | `ptr_tport_type` | Longword pointer to per-slot transport type array |
| 0x904BEA | 2 B × 4 | *(unknown)* | Teleporter-related |

### 1.18 Miscellaneous

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904BF2 | 2 B | `movement_type` | Set to 2 by `main_move_players` before calling `player_try_move`; encodes movement type |
| 0x904BF4 | 2 B × 4 | *(unknown)* | Per-player timer for flashing at end of invisibility |
| 0x904BFC | 2 B | `random_seed` | LCG random number seed. RNG formula: `seed = seed * 0x3619 + 0x5D35`; result = `floor((seed_new * range) / 65536)` |
| 0x904940 | 2 B × ? | *(internal)* | Cleared by `mob_remove` (0x5E064) when a MOB is removed; associated with camera target / head-pointer tracking |
| 0x905F30 | 2 B × 4 | `hurt_cooldown` | Per-player forcefield hurt cooldown timer |
| 0x905F38 | 2 B × 4 | `reflect_timer` | Per-player reflective shots countdown |
| 0x905F40 | 2 B × 4 | `acid_timer` | Per-player acid slow countdown |
| 0x905F48 | 2 B × 4 | `stun_timer` | Per-player stun countdown |
| 0x905F50 | 2 B × 4 | `invis_timer` | Per-player invisibility countdown |
| 0x905F58 | 2 B × 4 | `debounce_shift_a` | Per-player bit-0 joystick debounce shift register |
| 0x905F60 | 2 B × 4 | `debounce_shift_b` | Per-player bit-1 joystick debounce shift register |
| 0x905F80 | 2 B | `mob_list_heads` | Head of the current Y-bucket MOB linked list (single word, first bucket) |
| 0x905F82 | 2 B × 64 | `priority_bucket_array` | Base of the 64-word Y-bucket array; `main_move_monsters` indexes this by current Y scroll position to find the starting MOB for iteration |
| 0x910700 | 2 B × 32 | `tport_pos_table` | Maze slot index for each transporter |
| 0x910780 | 2 B × ? | `ff_segment_table` | Forcefield segment list (terminated by 0); see subsystems doc for format |

---

## 2. OS RAM Variables

See `02_os_rom.md` section 9 for full OS RAM variable map (`0x904F00–0x904FFF`).

---

## 3. Enums and Constants

### 3.1 Alphanumeric Character Masks

| Name | Value |
|------|-------|
| ALPHACHAR_CHARNUM_MASK | 0x03FF (1023) |
| ALPHACHAR_PALETTE_PLAYER0 | 0x0400 (1024) |
| ALPHACHAR_PALETTE_PLAYER1 | 0x0800 (2048) |
| ALPHACHAR_PALETTE_PLAYER2 | 0x0C00 (3072) |
| ALPHACHAR_PALETTE_PLAYER3 | 0x1000 (4096) |
| ALPHACHAR_PALETTE_BLINK | 0x3000 (12288) |
| ALPHACHAR_PALETTE_NUM_MASK | 0x3C00 (15360) |
| ALPHACHAR_PALETTE_BANK_MASK | 0x4000 (16384) |
| ALPHACHAR_OPAQUE | 0x8000 (32768) |
| ALPHACHAR_KEY | 0xA1 (161) |
| ALPHACHAR_SWORD | 0xA2 (162) |
| ALPHACHAR_POTION | 0xA3 (163) |

### 3.2 Character Numbers

| Name | Value |
|------|-------|
| CHAR_WARRIOR | 0 |
| CHAR_VALKYRIE | 1 |
| CHAR_WIZARD | 2 |
| CHAR_ELF | 3 |

### 3.3 Character Powers (bit number)

| Name | Bit |
|------|-----|
| POWER_SPEED_BIT | 0 |
| POWER_ARMOR_BIT | 1 |
| POWER_FIGHT_BIT | 2 |
| POWER_SHOTSPEED_BIT | 3 |
| POWER_SHOTPOWER_BIT | 4 |
| POWER_MAGIC_BIT | 5 |
| POWER_INVISIBILITY_BIT | 6 |
| POWER_REPULSIVE_BIT | 7 |
| POWER_REFLECT_BIT | 8 |
| POWER_TRANSPORT_BIT | 9 |
| POWER_SUPERSHOT_BIT | 10 |
| POWER_INVULN_BIT | 11 |

### 3.4 Directions

| Name | Value |
|------|-------|
| DIRECTION_UP | 0 |
| DIRECTION_UPRIGHT | 1 |
| DIRECTION_RIGHT | 2 |
| DIRECTION_DOWNRIGHT | 3 |
| DIRECTION_DOWN | 4 |
| DIRECTION_DOWNLEFT | 5 |
| DIRECTION_LEFT | 6 |
| DIRECTION_MASK | 7 |
| DIRECTION_DN_MULT | 1024 |

### 3.5 Dialog First-Encounter Flags (bit positions in `0x9049E4`)

| Name | Value |
|------|-------|
| DLGFLAG_FOODHEALTH | 0x00000001 |
| DLGFLAG_SOMEFOODDESTROYED | 0x00000002 |
| DLGFLAG_COINSFORHEALTH | 0x00000004 |
| DLGFLAG_SAVEKEYS | 0x00000008 |
| DLGFLAG_POTIONBEFOREMAGIC | 0x00000010 |
| DLGFLAG_SAVEPOTIONS | 0x00000020 |
| DLGFLAG_SHOOTINGPOTION | 0x00000040 |
| DLGFLAG_SHOOTINGPOISON | 0x00000080 |
| DLGFLAG_HEALTHLOST_GHOST | 0x00000100 |
| DLGFLAG_HEALTHLOST_GRUNT | 0x00000200 |
| DLGFLAG_HEALTHLOST_DEMON | 0x00000400 |
| DLGFLAG_HEALTHLOST_LOBBER | 0x00000800 |
| DLGFLAG_HEALTHLOST_SORC | 0x00001000 |
| DLGFLAG_POISONED | 0x00002000 |
| DLGFLAG_HEALTHLOST_DRAGON | 0x00004000 |
| DLGFLAG_HEALTHLOST_ACID | 0x00008000 |
| DLGFLAG_HEALTHLOST_SUPERSORC | 0x00010000 |
| DLGFLAG_HEALTHLOST_DEATH | 0x00020000 |
| DLGFLAG_SHOTSNOTHURTYET | 0x00040000 |
| DLGFLAG_POTIONUSED | 0x00080000 |
| DLGFLAG_KILLTHIEF | 0x00100000 |
| DLGFLAG_STOLENNEXTLEVEL | 0x00200000 |
| DLGFLAG_SOMEWALLSDESTROYED | 0x00400000 |
| DLGFLAG_TRAPSWALLSDISAPPEAR | 0x00800000 |
| DLGFLAG_TRANSPORTERS | 0x01000000 |
| DLGFLAG_FULLKEYSPOTIONS | 0x02000000 |
| DLGFLAG_STUNTILES | 0x04000000 |
| DLGFLAG_SOMETREASURELOCKED | 0x08000000 |
| DLGFLAG_YOUAREIT | 0x10000000 |
| DLGFLAG_KILLMUGGER | 0x20000000 |
| DLGFLAG_FAKEEXIT | 0x40000000 |
| DLGFLAG_FORCEFIELD | 0x80000000 |

### 3.6 Door Types

| Name | Value |
|------|-------|
| DOOR_NONE | 0 |
| DOOR_INTERSECTION | 1 |
| DOOR_HORIZ | 2 |
| DOOR_VERT | 3 |

### 3.7 Dragon Activity (bit positions in `dragon_state`)

| Name | Bit |
|------|-----|
| DRAGON_SLEEPING_BIT | 0 |
| DRAGON_STUNNED_BIT | 1 |
| DRAGON_TURNING_BIT | 2 |
| DRAGON_LOCKED_BIT | 3 |

### 3.8 Fixed MOB IDs

| Name | Value |
|------|-------|
| FIXEDMOB_SHOTPLAYER0 | 1 |
| FIXEDMOB_SHOTPLAYER1 | 2 |
| FIXEDMOB_SHOTPLAYER2 | 3 |
| FIXEDMOB_SHOTPLAYER3 | 4 |
| FIXEDMOB_SHOTDEMON0 | 5 |
| FIXEDMOB_SHOTDEMON1 | 6 |
| FIXEDMOB_SHOTDEMON2 | 7 |
| FIXEDMOB_SHOTDEMON3 | 8 |
| FIXEDMOB_SHOTLOBBER0 | 9 |
| FIXEDMOB_SHOTLOBBER1 | 10 |
| FIXEDMOB_SHOTLOBBER2 | 11 |
| FIXEDMOB_SHOTLOBBER3 | 12 |
| FIXEDMOB_SHOTSPLODEY0 | 13 |
| FIXEDMOB_SHOTSPLODEY1 | 14 |
| FIXEDMOB_SHOTSPLODEY2 | 15 |
| FIXEDMOB_SHOTSPLODEY3 | 16 |
| FIXEDMOB_SCORING0 | 17 |
| FIXEDMOB_SCORING1 | 18 |
| FIXEDMOB_SCORING2 | 19 |
| FIXEDMOB_SCORING3 | 20 |
| FIXEDMOB_EXITING0 | 21 |
| FIXEDMOB_EXITING1 | 22 |
| FIXEDMOB_EXITING2 | 23 |
| FIXEDMOB_EXITING3 | 24 |
| FIXEDMOB_TPORT0 | 25 |
| FIXEDMOB_TPORT1 | 26 |
| FIXEDMOB_TPORT2 | 27 |
| FIXEDMOB_TPORT3 | 28 |
| FIXEDMOB_TPORT4 | 29 |

### 3.9 Game Modes

| Name | Value |
|------|-------|
| GAMEMODE_NORMAL | 0x0000 |
| GAMEMODE_TREAS_EXIT | 0x0001 |
| GAMEMODE_LEGEND | 0xFFFC |
| GAMEMODE_DEMO | 0xFFFD |
| GAMEMODE_TITLE | 0xFFFE |
| GAMEMODE_SCORES | 0xFFFF |

### 3.10 Game Settings (COINHEALTH values)

| Name | Value |
|------|-------|
| GSETTING_COINHEALTH_125–2000 | 1–31 (100-unit increments) |
| GSETTING_DIFFICULTY_MASK | 0x00E0 (224) |
| GSETTING_COINTOSTART_MASK | 0x0300 (768) |
| GSETTING_TEXT_REDUCE | 0x0400 (1024) |
| GSETTING_SPEECH_DISABLE | 0x0800 (2048) |
| GSETTING_RESET_FLAG | 0x1000 (4096) |
| GSETTING_ALLOW_CONTEST_FLAG | 0x2000 (8192) |
| GSETTING_ATTRACT_SOUNDS | 0x4000 (16384) |
| GSETTING_SCORE_RESET_FLAG | 0x8000 (32768) |

### 3.11 Joystick Input Bits

| Name | Bit |
|------|-----|
| JOY_MAGIC_BIT | 0 |
| JOY_FIRE_BIT | 1 |
| JOY_SPARE1_BIT | 2 |
| JOY_SPARE2_BIT | 3 |
| JOY_RIGHT_BIT | 4 |
| JOY_LEFT_BIT | 5 |
| JOY_DOWN_BIT | 6 |
| JOY_UP_BIT | 7 |

### 3.12 Level Flags

**Level Flags 1** (`level_flags[0]`):

| Name | Value |
|------|-------|
| LFLAG1_ODDANGLE_GHOSTS | 0x01 |
| LFLAG1_ODDANGLE_GRUNTS | 0x02 |
| LFLAG1_ODDANGLE_DEMONS | 0x04 |
| LFLAG1_ODDANGLE_LOBBERS | 0x08 |
| LFLAG1_ODDANGLE_SORCERERS | 0x10 |
| LFLAG1_ODDANGLE_AUX_GRUNTS | 0x20 |
| LFLAG1_ODDANGLE_DEATHS | 0x40 |
| LFLAG1_INVIS_TRAPWALLS | 0x80 |

**Level Flags 2** (`level_flags[1]`):

| Name | Value |
|------|-------|
| LFLAG2_FAST_GHOSTS | 0x01 |
| LFLAG2_FAST_GRUNTS | 0x02 |
| LFLAG2_FAST_DEMONS | 0x04 |
| LFLAG2_FAST_LOBBERS | 0x08 |
| LFLAG2_FAST_SORCERERS | 0x10 |
| LFLAG2_FAST_AUX_GRUNTS | 0x20 |
| LFLAG2_FAST_DEATHS | 0x40 |
| LFLAG2_INVIS_ALLWALLS | 0x80 |

**Level Flags 3** (`level_flags[2]`):

| Name | Value |
|------|-------|
| LFLAG3_RANDOMFOOD_0–7 | 0–7 (count) |
| LFLAG3_WALLS_CYCLIC | 0x08 |
| LFLAG3_WALLS_DELETABLE1 | 0x10 |
| LFLAG3_WALLS_DELETABLE2 | 0x20 |
| LFLAG3_EXIT_MOVES | 0x40 |
| LFLAG3_EXIT_CHOOSEONE | 0x80 |

**Level Flags 4** (`level_flags[3]`):

| Name | Value |
|------|-------|
| LFLAG4_SHOTS_STUN | 0x01 |
| LFLAG4_SHOTS_HURT | 0x02 |
| LFLAG4_TRAPS_LOCAL | 0x04 |
| LFLAG4_TRAPS_RANDOM | 0x08 |
| LFLAG4_WRAP_V | 0x10 |
| LFLAG4_WRAP_H | 0x20 |
| LFLAG4_EXIT_FAKE | 0x40 |
| LFLAG4_PLAYER_OFFSCREEN | 0x80 |

### 3.13 Maze Numbers

| Name | Value |
|------|-------|
| MAZENUM_FIRST | 5 |
| MAZENUM_LAST | 101 |
| MAZENUM_DEMO | 102 |
| MAZENUM_LEGEND_SCORES | 103 |
| MAZENUM_TREASURE_FIRST | 104 |
| MAZENUM_TREASURE_LAST | 114 |
| MAZENUM_SECRET | 115 |

### 3.14 Maze Object IDs (tile types in `mob_link` bits 15-10)

| Name | Value |
|------|-------|
| MAZEOBJ_TILE_FLOOR | 0 |
| MAZEOBJ_TILE_STUN | 1 |
| MAZEOBJ_WALL_REGULAR | 2 |
| MAZEOBJ_WALL_MOVABLE | 3 |
| MAZEOBJ_WALL_SECRET | 4 |
| MAZEOBJ_WALL_DESTRUCTABLE | 5 |
| MAZEOBJ_WALL_RANDOM | 6 |
| MAZEOBJ_WALL_TRAPCYC1 | 7 |
| MAZEOBJ_WALL_TRAPCYC2 | 8 |
| MAZEOBJ_WALL_TRAPCYC3 | 9 |
| MAZEOBJ_TILE_TRAP1 | 10 (0x0A) |
| MAZEOBJ_TILE_TRAP2 | 11 (0x0B) |
| MAZEOBJ_TILE_TRAP3 | 12 (0x0C) |
| MAZEOBJ_DOOR_HORIZ | 13 (0x0D) |
| MAZEOBJ_DOOR_VERT | 14 (0x0E) |
| MAZEOBJ_PLAYERSTART | 15 (0x0F) |
| MAZEOBJ_EXIT | 16 (0x10) |
| MAZEOBJ_EXITTO6 | 17 (0x11) |
| MAZEOBJ_MONST_GHOST | 18 (0x12) |
| MAZEOBJ_MONST_GRUNT | 19 (0x13) |
| MAZEOBJ_MONST_DEMON | 20 (0x14) |
| MAZEOBJ_MONST_LOBBER | 21 (0x15) |
| MAZEOBJ_MONST_SORC | 22 (0x16) |
| MAZEOBJ_MONST_AUX_GRUNT | 23 (0x17) |
| MAZEOBJ_MONST_DEATH | 24 (0x18) |
| MAZEOBJ_MONST_ACID | 25 (0x19) |
| MAZEOBJ_MONST_SUPERSORC | 26 (0x1A) |
| MAZEOBJ_MONST_IT | 27 (0x1B) |
| MAZEOBJ_GEN_GHOST1–3 | 28–30 |
| MAZEOBJ_GEN_GRUNT1–3 | 31–33 |
| MAZEOBJ_GEN_DEMON1–3 | 34–36 |
| MAZEOBJ_GEN_LOBBER1–3 | 37–39 |
| MAZEOBJ_GEN_SORC1–3 | 40–42 |
| MAZEOBJ_GEN_AUX_GRUNT1–3 | 43–45 |
| MAZEOBJ_TREASURE | 46 (0x2E) |
| MAZEOBJ_TREASURE_LOCKED | 47 (0x2F) |
| MAZEOBJ_TREASURE_BAG | 48 (0x30) |
| MAZEOBJ_FOOD_DESTRUCTABLE | 49 (0x31) |
| MAZEOBJ_FOOD_INVULN | 50 (0x32) |
| MAZEOBJ_POT_DESTRUCTABLE | 51 (0x33) |
| MAZEOBJ_POT_INVULN | 52 (0x34) |
| MAZEOBJ_KEY | 53 (0x35) |
| MAZEOBJ_POWER_INVIS | 54 (0x36) |
| MAZEOBJ_POWER_REPULSE | 55 (0x37) |
| MAZEOBJ_POWER_REFLECT | 56 (0x38) |
| MAZEOBJ_POWER_TRANSPORT | 57 (0x39) |
| MAZEOBJ_POWER_SUPERSHOT | 58 (0x3A) |
| MAZEOBJ_POWER_INVULN | 59 (0x3B) |
| MAZEOBJ_MONST_DRAGON | 60 (0x3C) |
| MAZEOBJ_HIDDENPOT | 61 (0x3D) |
| MAZEOBJ_TRANSPORTER | 62 (0x3E) |
| MAZEOBJ_FORCEFIELDHUB | 63 (0x3F) |

### 3.15 MOB Perspectives

| Direction | Value |
|-----------|-------|
| up | 0x0 |
| upright | 0x2 |
| right | 0x4 |
| downright | 0x6 |
| down | 0x8 |
| downleft | 0xA |
| left | 0xC |
| upleft | 0xE |

### 3.16 Player Status Bits

| Name | Value |
|------|-------|
| PSTATUS_ALIVEHERE | 0x01 |
| PSTATUS_ALIVENEXT | 0x02 |
| PSTATUS_INITIALS | 0x04 |
| PSTATUS_EXITING | 0x08 |
| PSTATUS_SELECT | 0x10 |
| PSTATUS_SCODE | 0x20 |

### 3.17 Secret Tricks

| Name | Value | Description |
|------|-------|-------------|
| TRICK_NONE | 0 | No trick |
| TRICK_TRANSPORT1 | 1 | Try Transportability (onto demon) |
| TRICK_TRANSPORT2 | 2 | Try Transportability (onto death) |
| TRICK_TRANSPORT3 | 3 | Try Transportability (into exit) |
| TRICK_TRANSPORT4 | 4 | Try Transportability (into exit, variant) |
| TRICK_WATCHSHOOT1 | 5 | Watch What You Shoot (shoot foods) |
| TRICK_WATCHSHOOT2 | 6 | Watch What You Shoot (shoot secret walls) |
| TRICK_SAVESUPERSHOTS | 7 | Save Super Shots |
| TRICK_NOUSEINVUL | 8 | Don't Use Invulnerability |
| TRICK_NOGETHIT | 9 | Don't Get Hit (while killing a dragon) |
| TRICK_PUSHWALL | 10 | Try Pushing a Wall |
| TRICK_NOFOOLED | 11 | Don't Be Fooled |
| TRICK_NOGREEDY1 | 12 | Don't Be Greedy (no keys or potions) |
| TRICK_NOGREEDY2 | 13 | Don't Be Greedy (no treasure) |
| TRICK_DIET | 14 | Go On a Diet (no food) |
| TRICK_BEPUSHY | 15 | Be Pushy |
| TRICK_IT | 16 | IT Could Be Nice |
| TRICK_NOHURTFRIENDS | 17 | Don't Hurt Friends |

### 3.18 Thief Modes

| Name | Value |
|------|-------|
| THIEF_DEAD | 0 |
| THIEF_PURSUE | 1 |
| THIEF_ESCAPE | 2 |
| THIEF_DODGE_BIT | 3 |
| THIEF_JUMPJUMP | 4 |
| THIEF_ENTER_OK_MUGGER_BIT | 5 |
| THIEF_IS_MUGGER_BIT | 7 |
| THIEF_DODGE | 0x08 |
| THIEF_ENTER_OK | 0x10 |
| THIEF_ENTER_OK_MUGGER | 0x20 |
| THIEF_IS_MUGGER | 0x80 |

### 3.19 Maze Compression Bytecodes

| Range | Description |
|-------|-------------|
| 0x00–0x3F | Add one of this kind (from element list) (mask 0x3F) |
| 0x40–0x4F | Use HT1 (horizontal type 1) with N = 1..16 |
| 0x50–0x5F | Use VT1 (vertical type 1) with N = 1..16 |
| 0x60–0x6F | Use HT2 (horizontal type 2) with N = 1..16 |
| 0x70–0x7F | Use VT2 (vertical type 2) with N = 1..16 |
| 0x80–0x9F | Repeat last type 1 to 32 times |
| 0xA0–0xAF | Repeat wall horizontally 1 to 16 times |
| 0xB0–0xBF | Repeat wall vertically 1 to 16 times |
| 0xC0–0xFF | Skip 1 to 32 times then add wall |

### 3.20 Maze Horizontal and Vertical Types (encoded in HT1/HT2/VT1/VT2 header bytes)

| Range | Description |
|-------|-------------|
| 0x00–0x3F | Repeat this type |
| 0x40–0x7F | Skip N spaces then add this type (mask 0x40) |
| 0x80–0xBF | Add this type then skip N spaces (mask 0x80) |
| 0xC0–0xFF | Repeat wall N times then add this type (mask 0xC0) |

---

## 4. Data Structures

### 4.1 Maze Data Structure (in Slapstic ROM)

| Offset | Size | Name | Description |
|--------|------|------|-------------|
| 0x00 | 1 B | `secret_trick` | Secret trick ID (see Secret Tricks enum). 0 = none |
| 0x01 | 1 B | `level_flags_1` | Odd-angle and invisible-trap flags |
| 0x02 | 1 B | `level_flags_2` | Fast-monster flags |
| 0x03 | 1 B | `level_flags_3` | Random food count + cyclic/destructible walls + exit behavior |
| 0x04 | 1 B | `level_flags_4` | Shot behavior + traps + wrap + fake exit + offscreen |
| 0x05 | 1 B | `playfield_patterns` | Wall/floor pattern index (selects visual tile set) |
| 0x06 | 1 B | `playfield_colors` | Color palette index |
| 0x07 | 1 B | `horizontal_type_1` | RLE H-span type 1 |
| 0x08 | 1 B | `horizontal_type_2` | RLE H-span type 2 |
| 0x09 | 1 B | `vertical_type_1` | RLE V-span type 1 |
| 0x0A | 1 B | `vertical_type_2` | RLE V-span type 2 |
| 0x0B | variable | `level_data` | RLE-compressed tile data |

### 4.2 Palette Entry (in Color RAM)

| Offset | Size | Name | Description |
|--------|------|------|-------------|
| 0x00 | 2 B | `color0` | IRGB color format (4 bits each: I=intensity, R, G, B) |
| 0x02 | 2 B | `color1` | IRGB |
| 0x04 | 2 B | `color2` | IRGB |
| ... | ... | ... | ... |
| 0x1E | 2 B | `color15` | IRGB |

### 4.3 Forcefield Segment Table Entry (at `0x910780`)

Each entry is a 16-bit word (table terminated by 0):

| Bits | Field | Description |
|------|-------|-------------|
| 15 | direction | 1 = horizontal segment, 0 = vertical segment |
| 14 | wrap | 1 = segment wraps around maze edge |
| 13–10 | length_m1 | Segment length minus 1 (0–15 → 1–16 tiles beyond hub) |
| 9–0 | hub_slot | Slot position of the forcefield hub (row × 32 + col) |

### 4.4 Tile Sprite Descriptor (8 bytes, for `write_tile_descriptor`)

Specifies a 2×2 block of playfield tiles. Written to VRAM at offsets from base:

| Word Index | VRAM Offset | Tile Position |
|------------|------------|---------------|
| Word 0 | +0x000 | Top-left |
| Word 1 | +0x080 | Bottom-left (one VRAM row down) |
| Word 2 | +0x002 | Top-right |
| Word 3 | +0x082 | Bottom-right |

### 4.5 High Score Entry (in EEPROM)

| Offset | Size | Description |
|--------|------|-------------|
| 0 | 3 B | Score (24-bit big-endian) |
| 3 | 3 B | Initials (3 characters encoded as base-40: A-Z=1-26, 0-9=27-36, space=0) |

### 4.6 `text_desc` Struct (for OS `display_text`)

```c
struct text_desc {
    uint8_t  row;         // Y position (0-29)
    uint8_t  col;         // X position (0-41)
    uint32_t string_ptr;  // pointer to null-terminated ASCII string
    uint8_t  repeat;      // continuation count (adds to scroll offset)
    uint32_t next_ptr;    // pointer to next text descriptor (for chaining)
};
```

---

## 5. ROM Data Tables Catalog

### 5.1 Code Region Data Tables (`0x40000–0x5561F`)

| Address | Size | Content |
|---------|------|---------|
| 0x405C0 | 8 B | Forcefield color table (4 words, one per animation step) |
| 0x405C8 | ~16 B | `palette_offset_by_walltype` — playfield palette offset indexed by wall pattern |
| 0x405D8 | ~16 B | `palette_offset2_by_walltype` — second palette offset table |
| 0x40E02 | 28 B | Monster speed override table (7 longwords): base speed=0x80, fast speed=0x100 |
| 0x40E46 | ~32 B | `monster_count_table` — max monsters to process per frame, indexed by `(difficulty_setting << 3) + active_player_count - 1`. Count increased by `0x90405F` per-level bonus. Capped at `level_number * 2`. If `frame_overflow` (0x904916) non-zero: forced to 0. |
| 0x4A4FA | ~30 B | Stun direction remap table (garbles joystick direction cyclically) |
| 0x4A86A | 12 B | Direction-from-input nibble lookup table |
| 0x4A920 | ~10 B | Player speed table (indexed by character type × 2) |
| 0x580A8 | ~16 B | `player_speed_normal` table (speed values per character × walk state) |
| 0x580B8 | ~8 B | `player_anim_rate` table (frame counter threshold for speed boost) |

### 5.2 Master Object Parameter Tables (`0x5858C–0x5868C`)

Four parallel 64-entry tables (one entry per maze object type, indexed 0–63):

| Table Address | Name | Content |
|---------------|------|---------|
| 0x5858C | `hpos_offset_table` | H-position offset subtracted during placement |
| 0x5860C | `vpos_size_table` | V-position addend + size encoding during placement |
| 0x5864C | `palette_table` | Palette number for each object type |
| 0x5868C | `base_tile_table` | Base tile number for each object type |

### 5.3 Animation Tables (`0x58090–0x58A90`)

| Address | Size | Content |
|---------|------|---------|
| 0x58090 | ~8 B | `fighting_anim_end` — end-of-animation threshold per direction |
| 0x58098 | 4 × 4B | Demo initial pointer table — ROM pointers to per-player demo streams |
| 0x5811C | ~16 B | Direction-from-fight-input table |
| 0x5813C | ~16 B | `health_drain_table` — forcefield damage indexed by character×powered mode |
| 0x5874A | variable | `anim_table_shooting` — shooting animation frames indexed by (counter/4 & 3, direction, char_type × 64) |
| 0x58A4A | variable | `anim_table_idle` — idle animation frames indexed by (direction, char_type × 8) |
| 0x58A8A | variable | `anim_table_walking` — walking animation frames indexed by (counter/4 & 3, direction, char_type × 32) |
| 0x58C8A | var | `anim_tiles_thief_escape` — thief escape/flee tile animation table |
| 0x58C9A | var | `anim_tiles_thief_walk_a` — thief walk-cycle direction tile table A |
| 0x58D4C | var | `anim_tiles_thief_normal` — normal thief tile graphics (used when state flags bit 7 = 0) |
| 0x58D6C | var | `anim_tiles_thief_walk_b` — thief walk-cycle direction tile table B |
| 0x58E1E | var | `anim_tiles_thief_super` — super-thief (mugger) tile graphics (used when state flags bit 7 = 1) |

### 5.4 Scoring / Speech Tables

| Address | Size | Content |
|---------|------|---------|
| 0x57002 | 4 × 4B | Per-player character announcement speech IDs (ROM pointer table) |
| 0x57012 | 13 × 4B | Random maze flags table (selected by `get_random_maze_flags` via getrandom(0xD)) |
| 0x57046 | variable | Slapstic command base lookup table A |
| 0x5704E | variable | Slapstic command base lookup table B |
| 0x57340 | variable | ROM pointers to character HUD tile data |
| 0x576E2 | var | `shot_velocity_x` — shot projectile X velocity table, indexed by shot direction; used by `main_handle_shots` to advance shot pixel positions |
| 0x57792 | var | `shot_velocity_y` — shot projectile Y velocity table, indexed by shot direction |
| 0x57862 | variable | Health-per-coin table (indexed by GSETTING_COINHEALTH bits 0-4) |
| 0x578DA | var | Random item spawning table A — ROM table read by `main_health_countdown` section 2 to determine which random items to spawn |
| 0x578EA | var | Random item spawning table B — second ROM table for random item spawning in `main_health_countdown` |
| 0x57942 | var | `heartbeat_sound_table` — heartbeat sound IDs per player/health state, read by `main_health_countdown` |
| 0x57B50 | 8 × 2B | `monster_dx_table` — monster movement X delta per direction (8 entries, one per compass direction) |
| 0x57B68 | 8 × 2B | `monster_dy_table` — monster movement Y delta per direction (8 entries); used by `monster_generic_handler` to compute candidate tile positions |
| 0x578A0 | 2 B | Demo mode starting health constant |
| 0x596CE | variable | Monster shot damage values per type |
| 0x596F8 | 14 × 4B | Player color speech ID array (IDs 0xBD–0xCC: "RED WARRIOR" through "GREEN ELF") |

### 5.5 Tile / Playfield Data (`0x5BA70–0x5FFFF`)

| Address | Size | Content |
|---------|------|---------|
| 0x5AC20 | var | `logo_brightness_seq` | Logo brightness animation sequence table (advanced by 2 each cycle via `logo_anim_ptr`) |
| 0x5BA68 | 2 B | `logo_outer_timer_init` | Logo outer color cycle timer reset value |
| 0x5BA6A | 2 B | `logo_inner_timer_init` | Logo inner brightness timer reset value |
| 0x5BA6C | 2 B | `logo_bright_min` | Logo brightness accumulator minimum clamp |
| 0x5BA6E | 2 B | `logo_bright_max` | Logo brightness accumulator maximum clamp |
| 0x5BA70 | 32 B | Pointer table 1 into floor connectivity descriptors |
| 0x5BA90 | 32 B | Pointer table 2 into floor connectivity descriptors |
| 0x5BAD0 | 16 B | Null tile IDs: 0x0045, 0x0047, 0x0046, 0x0048 |
| 0x5BAE0 | ~3.6 KB | Floor tile descriptors (32 entries × 4 tilesets × 8 bytes each) |
| 0x5C8A0 | 520 B | Wall tile IDs for type 0x10 tiles |
| 0x5C8A8 | — | Wall tile IDs for type 0x11 tiles |
| 0x5CAA8 | 128 B | Floor connectivity descriptors (16 × 8B, 8 sub-entries each) |
| 0x5CB48 | ~504 B | Sparse object tile table: tile IDs for transporters, traps, doors, exits, forcefields |
| 0x5CD40 | ~1.7 KB | Dense animation frame table: sequential tile IDs for special object animations |
| 0x5D3E8 | ~152 B | Dragon path motion vectors (signed word pairs, ~38 entries) |
| 0x5D4B8 | — | Dragon body segment tile lookup |
| 0x5D478 | — | Dragon X/Y position offsets |
| 0x5D508 | — | Dragon head sprites |
| 0x5D528 | — | Dragon X position offsets per path step |
| 0x5D568 | — | Dragon fire-breath tiles |
| 0x5D578 | ~2 KB | Dragon 128-step circular body path table (16 bytes per entry; see `08_known_issues.md`) |
| 0x5B20E | var | `palette_cycle_player0` — Player 0 hurt flash palette cycling data |
| 0x5B256 | var | `palette_cycle_player1` — Player 1 hurt flash palette cycling data |
| 0x5B29E | var | `palette_cycle_player2` — Player 2 hurt flash palette cycling data |
| 0x5B32E | var | `palette_cycle_player3` — Player 3 hurt flash palette cycling data |
| 0x5B3EE | var | `palette_cycle_player0_alt` — Alternate cycling (poison/invuln) for player 0 |
| 0x5B4AE | var | `palette_cycle_player2_alt` — Alternate cycling for player 2 |
| 0x5B81C | var | `exit_anim_table` — Exit open/close animation data, indexed by wall pattern × 64 |
| 0x5D7E8 | — | Playfield palette A (for level_flags wall pattern < 6) |
| 0x5D828 | — | Playfield palette B (for level_flags wall pattern ≥ 6) |
| 0x5D848 | ~412 B | Palette color ramps (13 blocks × 32 bytes, one per tileset environment) |
| 0x5D9E8 | ~136 B | Contest strings: "SECRET CODE", "REMEMBER YOUR CODE", etc. (contest ended 12/19/86) |
| 0x5DAA0 | ~136 B | Wall neighbor connectivity state table (16 rows × 8 bytes) |
| 0x5F9CE | 64 B | Straight-wall connectivity lookup (16 × 4B) |
| 0x5FACA | 18 B | Corner-wall connectivity lookup (9 × 2B) |
| 0x5FBDC | 16 B | Junction-wall connectivity lookup (9 × 2B) |
| 0x5FC10 | 16 B | Playfield VRAM base addresses (4 longwords) |

### 5.6 String / Dialog Data

| Address | Size | Content |
|---------|------|---------|
| 0x570B4 | 16 B | Portrait display offsets (4 word-pairs: X,Y) |
| 0x570C4 | 32 B | Portrait sprite pointers (8 longwords) |
| 0x570E4 | 30 B | Input bitmask table for joystick direction decoding |
| 0x57104 | 96 B | Auto-repeat timing (16 entries × 3-word tuples) |
| 0x57370 | — | Character stat parameters |
| 0x57392 | ~260 B | Secret room trigger text table (10-byte records + strings) |
| 0x574BC | ~88 B | Character glyph/sprite tile mapping table |
| 0x57520 | ~88 B | UI strings: "SELECT HERO", "PRESS START", "ADD COIN", "INSERT COIN", "GAME OVER", "ON LEVEL:" |
| 0x57578 | ~190 B | DIP switch display records |
| 0x57638 | ~110 B | Continue screen strings: "LEVEL:", "PRESS START", "WITHIN    SECONDS", "TO CONTINUE GAME", "AT THIS LEVEL" |
| 0x57644 | var | `continue_screen_text1` — "PRESS START..." line 1 |
| 0x57658 | var | `continue_screen_text2` — continue screen line 2 |
| 0x5766C | var | `continue_screen_text3` — continue screen line 3 |
| 0x571FA | 4 × 4B | `forcefield_color_table` — forcefield color pointers indexed by `(level & 3)` |
| 0x57BD8 | ~760 B | Level object pre-placement table (50 variable-length arrays) |
| 0x57EB6 | ~322 B | Factory default high-score table (40 entries, developer initials: AWC, CJS, PAT, etc.) |
| 0x58000 | ~86 B | Score-per-coin display + "Enter your initials:" prompt |
| 0x58154 | 48 B | 12-entry dialog tip pointer table |
| 0x5818C | ~210 B | Demo input streams (2-byte entries: timer + joystick_byte; 0xFF=speech, 0xFE=player switch) |
| 0x5825E | ~760 B | In-game tip strings + dialog records |
| 0x5828C | var | `dialog_message_ptrs` — pointers to dialog message strings, organized by encounter type |
| 0x59732 | ~82 B | Hint text pointer table (20 longword pointers) |
| 0x59786 | ~304 B | Hint text strings ("TRY TRANSPORTABILITY", "WATCH WHAT YOU SHOOT", etc.) |
| 0x598B6 | ~330 B | Hint records with speech IDs (10-byte: cmd word + ROM ptr) |
| 0x59A00 | ~512 B | Gameplay tip strings ("MORE PLAYERS ALLOWS HIGHER / BONUS MULTIPLIER", etc.) |
| 0x5A320 | ~288 B | 16 power-up name strings (24 bytes each): "WARRIOR NOW HAS", "EXTRA ARMOR", etc. |
| 0x5A570 | ~244 B | Monster display records (12-byte entries: name ptr + Y offset + params) |
| 0x5A670 | ~110 B | Monster/object name strings: "GHOST", "GRUNT", "DEMON", "LOBBER", "SORCERER", etc. |
| 0x5A6DE | ~494 B | Object descriptor records (10-byte: speech word + ROM ptr + flags) |
| 0x5A8CC | ~410 B | Credits strings: "ED LOGG", "BOB FLANAGAN", "SAM COMSTOCK", "ALAN MURPHY", etc. |
| 0x5AA70 | ~170 B | Bonus scoring strings: "100 x COINS", "TREASURES x", "BONUS =", "NO BONUS !!" |

### 5.7 Palette / Color Data

| Address | Size | Content |
|---------|------|---------|
| 0x5AD1E | ~64 B | Basic color RAM initialization data (alpha + MOB palettes) |
| 0x5AD3E | ~1.2 KB | Extended palette data (~22 sub-palettes × 64 bytes): UI, 4 character palettes, death variants, ghost, monster brightness variants, items |
| 0x5AFAE | ~80 B | Fade-in sequences (6 color steps per fade, 6 environment fades) |
| 0x5B00E | ~512 B | 4 character full palettes (128 B each): Warrior, Valkyrie, Wizard, Elf. Each has 4 sub-palettes (normal/poisoned/ghost/invulnerable) |
| 0x5B22E | ~80 B | Hurt flash palette sequence (red/white alternating) |
| 0x5B32E | ~256 B | Poison shimmer palette sequence (blue-green sine-wave) |
| 0x5B42E | ~256 B | Invulnerability shimmer sequence (gold/white ramp) |
| 0x5B52E | ~256 B | Secondary poison variant sequence |
| 0x5AC20 | variable | Logo brightness animation sequence table |

### 5.8 Demo Data

| Address | Size | Content |
|---------|------|---------|
| 0x58098 | 16 B | Initial demo pointer table (4 longwords, one per player) |
| 0x5818C | ~86 B | Player 0 demo input stream |
| 0x581C4 | ~150 B | Player 1 demo input stream (primary; Elf character) |
| 0x5825A | ~2 B | Player 2 demo input stream (minimal) |
| 0x5825C | ~2 B | Player 3 demo input stream (minimal) |

---

## 6. Verified MAZEOBJ Base Tile Values

All values confirmed against python-gex tile data. From master parameter tables at 0x5868C / 0x5864C:

| MAZEOBJ | Type ID | Base Tile (hex) | Base Tile (dec) | Palette |
|---------|---------|----------------|-----------------|---------|
| Ghost | 18 | 0x0800 | 2048 | 0x00 |
| Grunt | 19 | 0x09E1 | 2529 | 0x04 |
| Demon | 20 | 0x183F | 6207 | 0x08 |
| Lobber | 21 | 0x1B57 | 6999 | 0x0B |
| Sorcerer | 22 | 0x13A2 | 5026 | 0x0B |
| Aux Grunt | 23 | 0x09E1 | 2529 | 0x04 (shares with Grunt) |
| Death | 24 | 0x1A75 | 6773 | 0x00 |
| Acid | 25 | 0x2300 | 8960 | 0x01 |
| Super Sorc | 26 | 0x13A2 | 5026 | 0x0B (shares with Sorcerer) |
| IT | 27 | 0x2600 | 9728 | 0x08 |
| Ghost Gen 1/2/3 | 28/29/30 | 0x09AB/0x09B4/0x09BD | 2475/2484/2493 | 0x05 |
| Other Gen 1/2/3 | 31–45 | 0x09C6/0x09CF/0x09D8 | 2502/2511/2520 | 0x05 |
| Treasure | 46 | 0x0987 | 2439 | 0x01 |
| Treasure Locked | 47 | 0x25E4 | 9700 | 0x01 |
| Gold Bag | 48 | 0x09A2 | 2466 | 0x01 |
| Food (destr) | 49 | 0x0963 | 2403 | 0x01 |
| Food (invuln) | 50 | 0x096C | 2412 | 0x01 (random variant from table at 0x58F20) |
| Potion (destr) | 51 | 0x88FC | 2300+flag | 0x01 (bit 15 = software flag) |
| Potion (invuln) | 52 | 0x89FC | 2556+flag | 0x01 |
| Key | 53 | 0x8AFC | 2812+flag | 0x01 |
| Invisibility | 54 | 0x1700 | 5888 | 0x01 |
| Repulsiveness | 55 | 0x26FC | 9980 | 0x01 |
| Reflect | 56 | 0x24FC | 9468 | 0x01 |
| Transport | 57 | 0x23FC | 9212 | 0x01 |
| Super Shot | 58 | 0x2788 | 10120 | 0x01 |
| Invulnerability | 59 | 0x2784 | 10116 | 0x01 |
| Dragon | 60 | 0xA740 | 10048+flag | 0x08 (bit 15 = flag) |
| Hidden Potion | 61 | 0x0BFC | 3068 | 0x01 |
| Transporter | 62 | 0x8001 | marker | 0x00 (handled specially) |
| Forcefield Hub | 63 | 0x0C3F | 3135 | 0x00 |

---

## 7. Monster Animation Pointer Tables

### 7.1 Idle Animation Pointers (`0x40DB2`, 10 × 4B longwords)

| Index | Monster Type | Table Address |
|-------|-------------|---------------|
| 0 | Ghost | 0x058F26 |
| 1 | Grunt / Aux Grunt | 0x058FA6 |
| 2 | Demon | 0x0590A6 |
| 3 | Lobber | 0x0591A6 |
| 4 | Sorcerer / Super Sorc | 0x058C0A |
| 5 | Aux Grunt | 0x058FA6 (shared with Grunt) |
| 6 | Death | 0x0592A6 |
| 7 | Acid | 0x059336 |
| 8 | Super Sorc | 0x058C0A (shared with Sorcerer) |
| 9 | IT | 0x059436 |

### 7.2 Moving Animation Pointers (`0x40DDA`, 10 × 4B longwords)

NULL = use idle table for all states.

| Index | Monster Type | Table Address | Notes |
|-------|-------------|---------------|-------|
| 0 | Ghost | NULL | Ghosts use idle even when moving |
| 1 | Grunt | NULL | Same |
| 2 | Demon | 0x059026 | Separate moving animation |
| 3 | Lobber | 0x059126 | Separate moving animation |
| 4 | Sorcerer | NULL | Sorcerers don't visually move |
| 5 | Aux Grunt | 0x059226 | Has moving animation |
| 6 | Death | 0x059026 | Shares with Demon moving table |
| 7 | Acid | NULL | |
| 8 | Super Sorc | 0x059436 | Has moving animation |
| 9 | IT | NULL | |

### 7.3 Animation Table Addresses

Each animation table has 64 word entries: 8 counter values × 8 directions. Index computation: `index = (anim_counter × 8 + direction) × 2`.

| Address | Size | Name |
|---------|------|------|
| 0x40DB2 | 40 B | `monster_anim_idle_ptrs` (10 longword pointers) |
| 0x40DDA | 40 B | `monster_anim_moving_ptrs` (10 longword pointers) |
| 0x40E1E | 40 B | `monster_oddangle_table` (per-type direction adjustment) |
| 0x58C0A | 128 B | `anim_tiles_sorcerer` (Sorcerer/Super Sorc, 64 words) |
| 0x58F26 | 128 B | `anim_tiles_ghost` (64 words, verified) |
| 0x58FA6 | 128 B | `anim_tiles_grunt` (64 words, Grunt/Aux Grunt, verified) |
| 0x590A6 | 128 B | `anim_tiles_demon` |
| 0x591A6 | 128 B | `anim_tiles_lobber` |
| 0x592A6 | 128 B | `anim_tiles_death` |
| 0x59336 | 128 B | `anim_tiles_acid` |
| 0x59436 | 128 B | `anim_tiles_it` |
| 0x59026 | 128 B | `anim_tiles_demon_moving` |
| 0x59126 | 128 B | `anim_tiles_lobber_moving` |
| 0x59226 | 128 B | `anim_tiles_auxgrunt_moving` |
| 0x594B6 | 128 B | `anim_tiles_it_special` (IT chase state) |
| 0x595B6 | 128 B | `anim_tiles_lobber_throw` (Lobber throwing animation) |

### 7.4 Verified Ghost Animation Table (`0x58F26`)

| Counter | UP | UP-RT | RT | DN-RT | DN | DN-LT | LT | UP-LT |
|---------|----|-------|----|-------|----|-------|----|-------|
| 0–4 | 2192 | 2156 | 2120 | 2084 | 2048 | 2304 | 2264 | 2228 |
| 5 | 2201 | 2165 | 2129 | 2093 | 2057 | 2313 | 2273 | 2237 |
| 6 | 2210 | 2174 | 2138 | 2102 | 2066 | 2322 | 2282 | 2246 |
| 7 | 2219 | 2183 | 2147 | 2111 | 2075 | 2331 | 2291 | 2255 |

Pattern: frame 0 held for 5 ticks, then frames 1/2/3 each for 1 tick (0-0-0-0-0-1-2-3 cycle).

### 7.5 Verified Grunt Animation Table (`0x58FA6`)

Counter pattern: **0-0-0-1-2-2-3-0** — a bounce/ping-pong walk cycle. All tile numbers verified against python-gex. Grunt DOWN frame 0 = tile 2529 (= `0x09E1`). Aux Grunt shares this table.

---

## 8. Player Animation Tables (Complete)

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x58070 | 16 B | `invisibility_flash_masks` | Frame masks for invisibility pulsing, indexed by timer >> 7 |
| 0x58090 | 8 W | `fighting_anim_end` | Per-character × power-mode threshold for attack animation end |
| 0x580A8 | 8 W | `player_speed_normal` | Movement speed per character (×2 for normal/powered modes) |
| 0x580B8 | 8 W | `player_anim_rate` | Animation rate divisor per character type |
| 0x580C8 | 8 W | `player_collision_size` | Collision box dimensions per character type |
| 0x580D8 | 8 W | `player_delta_x` | Horizontal movement deltas per direction |
| 0x580E8 | 8 W | `player_delta_y` | Vertical movement deltas per direction |
| 0x580FC | var | `lobber_sin_cos_table` | Sin/cos offsets for lobber throw trajectory |
| 0x5813C | 32 B+ | `health_drain_table` | Health drain per tick, indexed by difficulty + character |
| 0x5874A | 256 B | `anim_table_shooting` | Shooting animation: 4 chars × 8 dirs × 4 frames (128 words) |
| 0x5884A | 512 B | `anim_table_fighting` | Fighting animation: 4 chars × 8 dirs × 8 frames (256 words) |
| 0x58A4A | 64 B | `anim_table_idle` | Idle/standing: 4 chars × 8 dirs × 1 frame (32 words) |
| 0x58A8A | 256 B | `anim_table_walking` | Walking animation: 4 chars × 8 dirs × 4 frames (128 words) |

**Animation counter mechanics:**
- Walking: `counter >> 2 & 3` → 4 frames, cycles every 16 game frames (~0.27 s/cycle)
- Fighting: `counter >> 1 & 7` → 8 frames, same rate
- Shooting: `counter >> 2 & 3` → 4 frames (same rate as walking)
- Idle: no counter; facing direction alone selects tile

---

## 9. Additional RAM Variables (from Phases 9–28 analysis)

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A60 | 2 B | `monster_iter_ptr` | Current monster iteration pointer |
| 0x904A62 | 2 B | `screen_left_boundary` | Left screen boundary for monster culling (pixel, shifted) |
| 0x904A64 | 2 B | `screen_top_boundary` | Top screen boundary for monster culling |
| 0x904B42 | 2 B × 4 | `death_touch_timer` | Per-player Death touch sound timer (negative = new contact) |
| 0x904B4A | 2 B × 4 | `ff_hurt_timer` | Per-player forcefield hurt sound timer |
| 0x904B8E | 1 B | `eeprom_cache_stat1` | EEPROM cache for 0x904010 |
| 0x904B8F | 1 B | `eeprom_cache_stat2` | EEPROM cache for 0x90400E |
| 0x904B90 | 1 B | `eeprom_cache_stat3` | EEPROM cache for 0x904018 |
| 0x904B91 | 1 B | `eeprom_cache_stat4` | EEPROM cache for 0x904016 |
| 0x904B92 | 2 B | `eeprom_cache_stats` | EEPROM cache for 0x904B86 (game stats word) |
| 0x904B94 | 2 B | `eeprom_cache_settings` | EEPROM cache for 0x904A24 (game settings) |
| 0x9049EE | 2 B | `speech_counter` | Non-zero = speech in progress; `main_update_sound` skips |
| 0x9049F0 | 2 B | `sound_queue_state` | Sound subsystem state word |
| 0x9049F2 | 2 B | `sound_idle_timer` | Countdown between sound CPU ping attempts |
| 0x9049F4 | 2 B | `sound_cpu_retry_count` | Sound CPU retry counter (reset > 180 = full reset) |
| 0x9048A0 | 2 B | `randwall_low_watermark` | Random wall low water mark |
| 0x9048A2 | 2 B | `randwall_target` | Random wall target index |
| 0x9048A4 | 2 B | `randwall_current` | Random wall current index |
| 0x9048A6 | 2 B | `randwall_timer` | Random wall timer (negative=disabled, 0=process, positive=countdown) |
| 0x910600 | 1 B × (tile_count/4) | `cycle_phase_assignments` | Color RAM Spare: cyclic wall phase assignment, 2 bits per tile |
| 0x905048 | var | `hud_mob_table` | HUD MOB tile data (score digits, character portraits) |
