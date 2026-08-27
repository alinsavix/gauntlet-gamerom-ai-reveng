# Gauntlet II — Data Reference

*RAM variable map, enums and constants, data structures, and ROM data tables catalog.*

---

## 1. Game RAM Variables (`0x904000–0x904FFF`)

**Confidence: Verified** for address, extent, access width, and observed
read/write role unless a row explicitly carries another label. The generated
callable and linear operand reports cover every ROM-encoded base/literal.

### 1.1 Core Game State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904000 | 2 B | `mazenum_current` / `os_flag` | Current maze number in normal game logic. The shared OS uses the same word as its status/version flag during boot and diagnostics; the two names are lifetime/context views of one word. |
| 0x904002 | 2 B | `vblank_semaphore` | Set by VBLANK handler; cleared by main loop after processing |
| 0x904004 | 2 B | `levelnum_current` | Current level (not maze) number |
| 0x904006 | 2 B | `pf_vscroll_hi` / `frame_counter` | Two lifetime views of one word, like 0x904000 and 0x90400E. While the **OS** owns VBLANK (boot, self-test, OS attract lane) the handler at 0xE5E combines it with `pf_vscroll_lo` to program the hardware scroll. While the **game** owns VBLANK it is a free-running frame counter: `g2mainloop` increments it at 0x42A86, `main_health_countdown` gates the 1-point health drain on `& 0x3F` (0x4670C), `main_score_display` services player `& 3` (0x457DE), the color/animation cyclers test `& 0xF` and `& 0xC` (0x40328, 0x4059C), and the DEMO branch of `start_attract_screen` clears it at 0x44524. No game-side site treats it as a scroll value. |
| 0x904008 | 2 B | `pf_hscroll` | Horizontal playfield-scroll shadow. |
| 0x90400A | 2 B | `pf_vscroll_lo` | Low portion of the playfield vertical-scroll shadow. |
| 0x90400C | 2 B | `timer_countdown` | OS countdown decremented from VBLANK; game startup also clears it when resetting shared state. |
| 0x90400E | 2 B | `mazerand_adder` / `sound_data_recv` | **Maze-rotation stride**, 0–7: extra mazes advanced per level once the current maze is ≥ 5 (`player_exit_sequence` 0x52DFE). Bumped `(x+1) & 7` whenever a step sequence ends on maze 5 (0x52E24–0x52E30), i.e. on each lap wrap or a resume value still at its home position. EEPROM-backed via cache byte 0x904B8F, masked to 0–7 on load (0x43026). Fresh-EEPROM default 0. The OS uses the same word as its sound-response receive word during boot; the two names are lifetime views of one word. See `06_maze_catalog.md` §3.2. |
| 0x904010 | 2 B | `mazerand_num` / `sound_data_flag` | **Maze-rotation resume position**: where this cabinet's rotation through mazes 5–101 currently stands. `maze_checknum` (0x52EDE) substitutes it for a candidate maze of exactly 5, which is how level 6 enters the rotation. Written only by `main_health_countdown` 0x46A0E — when the last player dies (`level_players_active` = 0) on level ≥ 6, it records `mazenum_current`. EEPROM-backed via cache byte 0x904B8E; `eeprom_load_config` forces it to 5 if below 5 or if its pointer-table entry is dead (0x43002–0x4301C). Fresh-EEPROM default 5. The OS uses the same word as its sound-response availability word during boot. See `06_maze_catalog.md` §3.2–§3.3. |
| 0x904012 | 4 B overlapping view | `timer_eepromwrite` | Game EEPROM-write countdown, decremented as a longword and normally reloaded to 0x8CA0. Its low word at 0x904014 aliases the OS boot-only `game_hook_flag`: the OS initializes/tests that word while validating the game header, then the running game reuses the same storage as the countdown. |
| 0x904016 | 2 B | `treas_mazerand_adder` | **Treasure-rotation stride**, 0–3. `show_level_start_screen` advances `treas_mazerand_num` by `this + 1` (0x44ECA–0x44ED2), so the effective step is 1–4, and bumps it `(x+1) & 3` when the rotation lands exactly on maze 104 (0x44F06–0x44F14). EEPROM-backed via cache byte 0x904B91, masked to 0–3 on load (0x43062). Fresh-EEPROM default 0. See `06_maze_catalog.md` §3.5. |
| 0x904018 | 2 B | `treas_mazerand_num` | **Next treasure maze**, 104–114. Copied into `mazenum_current` when a treasure room is entered (0x44EB2–0x44EB8), then advanced by `treas_mazerand_adder + 1`; values above 114 wrap by subtracting 11 (0x44EE4–0x44EF6). EEPROM-backed via cache byte 0x904B90; `eeprom_load_config` forces it to 104 if outside 104–114 (0x4303E–0x43054). Fresh-EEPROM default 104. See `06_maze_catalog.md` §3.5. |
| 0x90401A | 2 B | `wallcycle_time` | Cyclic-wall update countdown. Forcefield/maze setup clears it; `main_walls_cyclic_move` performs an update when the predecrement value is zero and reloads 0x78 (120 frames). |
| 0x90401C | 1 B active + 1 B padding | `wallcycle_type` | Current cyclic-wall phase byte. Setup clears it; each update advances 0→1→2→3→1. The phase is compared with the low two bits of each `vram.color_spare` control byte to decide which wall group disappears and which next group appears. The second byte is not read. |
| 0x90401E | 2 B | `playfield_color_latch` | Live palette-0 color-8 latch. VBLANK copies it to playfield color RAM 0x910510 at 0x401D4. The main loop restores it from 0x904020 each frame; potion use temporarily replaces it with color 3 of the triggering player-position alpha palette, producing a one-field screen flash. |
| 0x904020 | 2 B | `playfield_color_base` | Ordinary level floor color restored into 0x90401E at 0x42A8E before the gameplay calls. Initialized alongside 0x90401E from the selected playfield palette at 0x435B0-0x435BA (or fixed palette word 0x5AC6E at 0x4368E-0x4369E). |
| 0x904022 | 2 B | `potion_player` | Potion owner plus trigger flags: player index in bits 0-1, shot-triggered bit 2; the matrix consumer adds enhanced-magic bit 3 locally. |
| 0x904024 | 2 B | `collision_dist_H` | Horizontal object collision distance |
| 0x904026 | 2 B | `collision_dist_V` | Vertical object collision distance |
| 0x904028 | 2 B | `shothit_dist_H` | Horizontal shot collision distance |
| 0x90402A | 2 B | `shothit_dist_V` | Vertical shot collision distance |
| 0x90402C | 2 B | `palette_pulse_dir_b` | Direction flag (0 increasing, −1 decreasing) for the second VBL-driven color pulse; flips at color bounds 0x4044/0xA0AA |
| 0x90402E | 2 B | `palette_pulse_dir_a` | Direction flag for the first VBL-driven color pulse; flips at bounds 0x2220/0xEEE0 |
| 0x904030 | 2 B | `tport_cycle_pos` | Transporter position counter (bounces 0→4→0) |
| 0x904032 | 2 B | `tport_cycle_dir` | Transporter cycle direction (±1) |
| 0x904034 | 2 B | `tport_cycle_divider` | 2-bit sub-frame divider; ticks every 4th frame |
| 0x904036 | 4 B | `ptr_playfield_color1` | Pointer to 1st playfield color set |
| 0x90403A | 4 B | `ptr_playfield_color2` | Pointer to 2nd playfield color set |
| 0x90403E | 4 B | `ptr_playfield_color3` | Pointer to 3rd playfield color set |
| 0x904042 | 4 B | `ptr_ff_cycle_delay` | Pointer to the selected eight-byte forcefield cycle-delay profile in ROM 0x571DA–0x571F9. `game_start` installs profile 0 and maze setup selects `(level & 3)`. |
| 0x904046 | 2 B | `forcefield_color` | Current forcefield color word |
| 0x904048 | 2 B | `ff_cycle_timer` | Forcefield color cycle step timer |
| 0x904049 | 1 B | `ff_cycle_index` | Current step index into forcefield color table (0–7) |
| 0x90404A | 1 B | `thief_path_direction` | Current route direction byte. `thief_compute_path` preserves this byte when `path_grid_get_direction` returns unset (8), replacing it only with a decoded direction 0–7; reset value zero therefore continues upward if a caller creates a thief without first supplying breadcrumbs. |
| 0x90404B | 8 B | `soundqueue` | Array of 1-byte sound IDs in the queue |
| 0x904053 | 1 B | `soundqueue_head` | Head of sound queue |
| 0x904054 | 1 B | `soundqueue_tail` | Tail of sound queue |
| 0x904055 | 4 B | `player_potionsnum` | Array of 1-byte counters: potions per player |
| 0x90405A | 4 B | `player_keysnum` | Array of 1-byte counters: keys per player |
| 0x90405F | 1 B | `monster_spawn_probability_bonus` | Signed global modifier added to `monster_spawn_probability_table` before each generator's random spawn gate. `update_monster_spawn_bonus_from_score_per_coin` (0x48B58) adds `(sum(active scores) >> 14) / sum(active players' inserted coins)`; coin insertion decrements it while positive. Several transition paths temporarily save/restore player key/potion adjustments through this byte, so it is not a four-player array. |

### 1.2 MOB Animation Array

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904066 | 2 B × 1024 | `mob_state_link[]` (historically `mob_anim`) | Per-slot multiplexed state. Bits 9–0 are always the backward MOB-list link. Bits 15–10 are object-specific: monster animation/direction, player number for player MOBs, door/forcefield graphic state, or movable-wall hit count. See `04_game_subsystems.md` §2.1. |

### 1.3 Secret Room State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904063 | 1 B | `trick_player` | Which player completed the secret trick / is in the secret room (a.k.a. `secret_room_player`; 0–3, 0xFF = none; reset each level by `maze_new_level_setup`) |
| 0x904064 | 1 B | `trick_last` | Last secret trick completed |
| 0x904065 | 1 B | `trick_tasknum` | Current secret objective. During an ordinary maze it is the header's trick ID (0x01–0x11; §3.17). After a player wins entry to the secret challenge, `show_level_start_screen` (0x44DB4) saves that ID in `trick_last` and replaces this byte with a random challenge code 0x50–0x5D. Thus comparisons against values such as 0x5A are a second, valid namespace rather than malformed trick IDs. Zero means no active secret objective. |

### 1.4 Maze Decompression

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904866 | 2 B | `maze_decomp_htype1` | Maze decompression horizontal special element type 1 |
| 0x904868 | 2 B | `maze_decomp_htype2` | Maze decompression horizontal special element type 2 |
| 0x90486A | 2 B | `maze_decomp_vtype1` | Maze decompression vertical special element type 1 |
| 0x90486C | 2 B | `maze_decomp_vtype2` | Maze decompression vertical special element type 2 |
| 0x90486E | 2 B | `secret_need_hint` | Discovery latch set by opening a secret wall or killing the dragon. `level_splash` consumes it between levels: writes the hint header and either the eligible selected maze-header objective or a random objective hint, then clears it. |
| 0x904870 | 2 B | `secret_prev_maze` | Maze number when secret room was triggered |
| 0x904872 | 4 B | `secret_tricks_flags` | Array of 4 × 1B: per-player progress toward secret trick goal |
| 0x904878 | 2 B | `secret_possible_counter` | Counts down; when 0, secret room entry is possible |
| 0x90487A | 2 B | `secret_possible_start` | Starting value for secret_possible_counter |
| 0x904060 | 1 B | `thief_pursuit_direction` | Signed shot-dodge direction latch. `-1` means no direction has yet been latched; after `thief_find_aligned_shooter` selects a player, `main_thief_anim` stores the first computed dodge direction and uses a nonnegative value to gate direction changes. |
| 0x904061 | 1 B | `thief_pursuit_player` | Player selected by `thief_find_aligned_shooter` when the thief enters shot-dodge mode. It indexes that player's MOB and shot-direction entry. |
| 0x904062 | 1 B | `thief_pursuit_shot_direction` | Snapshot of byte 1 of the selected player's `shot_direction` word. If the live value changes while the pursuit gate is active, theft is aborted. |

### 1.5 Dragon State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x90487C | 2 B | `dragon_fire_cooldown` | Fire cooldown/hold timer: set to 8 by `dragon_fire_setup` (0x54748), decremented per frame in `main_handle_dragon`, gates fireball rate and holds the path counter during locked-in sustained fire. |
| 0x90487E | 2 B | `dialog_once_flags` | WORD bitfield of "dialog shown once" flags (one bit per dialog id; tested/set by `dialog_first_encounter` code). **Bit 0 = dragon first-encounter dialog** (the old `dragon_encounter_flag`); bit 0 cleared per level by `maze_new_level_setup`, whole word cleared at game init. |
| 0x904880 | 2 B | `dragon_hits` | Number of hits on the dragon (9th hit = death) |
| 0x904882 | 2 B | `dragon_head_hpos` | Horizontal position of the dragon's HEAD: `(mob_hpos[dragon_seg_mob_ids[0]] + head hdelta) & 0xFF80` (0x5466C) — position field only, no palette. |
| 0x904884 | 2 B | `dragon_head_vpos` | Vertical position of the dragon's head, `(mob_vpos[seg 0] + head vdelta) & 0xFF80` (0x5469E), delta table 0x5D478 |
| 0x904886 | 2 B | `dragon_path_num` | Current path program number 0–4 (row into `dragon_path_programs` 0x5D578); re-randomized via getrandom(5) on every hit. |
| 0x90488C | 2 B | `dragon_move_state` | Dragon movement sub-state; low nibble also limits simultaneous fireballs (< 4 to fire) |
| 0x90488E | 2 B | `dragon_facing` | Current cardinal facing encoded as 0, 2, 4, or 6. Head pose/fire tables use `(path_byte >> 1) + dragon_facing × 2`, producing four non-overlapping four-entry pose blocks; spawn-offset tables use `dragon_facing >> 1`. |
| 0x904890 | 2 B | `dragon_state` | State bitmask: bit 0 sleeping/wake transition (zero is normal active), bit 1 stunned, bit 2 turning, bit 3 locked flame. `dragon_player_proximity` clears stun on a proximity-box entry event. |
| 0x904892 | 2 B | `dragon_anim_ctr` | Signed sleep/wake/turn counter or active 0–127 path counter. Path phase = ctr >> 3. A reverse-to-sleep count stops at zero until a proximity entry starts +49. |
| 0x904894 | 2 B × 4 | `dragon_seg_mob_ids` | Dragon segment MOB slot IDs: [0] = head/main MOB (used by `main_handle_dragon`), [1..3] = body segments (0x904896/98/9A, previously undocumented); fireballs spawn from the segment selected by table 0x5D4B8[pose + facing*2] |
| 0x90489C | 4 B | `ptr_exit_openclose_anim` | Pointer to exit open/close animation for current tileset |

### 1.6 Wall Randomizer

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x9048A0 | 2 B | `randwall_low_watermark` | Lower scan bound for random-wall tiles; maze setup initializes it from the first `MAZEOBJ_WALL_RANDOM` (type 6) slot |
| 0x9048A2 | 2 B | `randwall_target` | Random-wall scan target/bound; initialized from the same first type-6 slot |
| 0x9048A4 | 2 B | `randwall_current` | Current random-wall scan cursor |
| 0x9048A6 | 2 B | `randwall_timer` | Negative = disabled, zero = process, positive = countdown; reloads to 0x78 normally or 0x3C in attract mode |

### 1.7 Player State Arrays

*All player arrays are indexed by player number (0–3)*

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x9048A8 | 2 B × 4 | `player_shot_last_wall_pos` | Per-player/shot-channel packed maze position of the most recent wall or reflection contact. `shot_reflect_calc` uses it to disambiguate wraparound/corner bounces and suppress an immediate repeat collision; normal shot cleanup updates or clears the saved position. |
| 0x9048B0 | 2 B | `thief_direction_change_pos` | Packed thief cell saved when `main_thief_anim` changes direction in the constrained movement mode. While nonzero and unequal to the current cell it suppresses the gated move; cleared when that direction-change constraint is reset. |
| 0x9048B2 | 2 B | `monster_slowmo_timer` | **Global monster slow-motion countdown, not a player debuff.** While nonzero, `monsters_everything` (0x40EB0–0x40EE8) tests frame bit 0 and, on even frames, pops its arguments and jumps straight to the loop exit at 0x4152C — the entire monster pass is skipped, so every monster moves at half rate. When it is zero the handler instead doubles the frame word (0x40EEC) so the later `btst #1` phase test stays aligned. `resolve_shot_hit` loads 0x0258 (600 frames) at 0x4B8B0 and 0x04B0 (1200 frames) at 0x4B9EC with sound 0x37; the countdown itself plays sound 0x38 at 30 remaining and 0x39 at expiry; `maze_new_level_setup` clears it at 0x438C2. It is one global word, not a per-player array. |
| 0x9048B4 | 2 B × 4 | `player_deferred_move_flags` | Per-player movement flags accumulated by recursive collision/corner-squeeze retries. `player_try_move` ORs the saved word into its incoming flags and immediately clears the array element; directional paths set bits 0x10/0x20 and related retry state. |
| 0x9048BC | 2 B | `thief_speed` | How fast the thief moves |
| 0x9048BE | 2 B × 4 | `reflect_count` | Number of times a player's shot has reflected |
| 0x9048C6 | 2 B | `escape_timer` | Frames since a player was last hit; at 20000, all walls turn to exits |
| 0x9048C8 | 2 B × 12 | `active_mob_ids` | Logical actor/projectile channel → hardware MOB slot mapping. Entries 0–3 are the four player MOB IDs; later entries are used for monster/dragon shot channels. Exact range 0x9048C8–0x9048DF. |
| 0x9048E0 | 2 B × 4 | `player_powers` | Per-player power bits (see Character Powers enum) |
| 0x9048E8 | 2 B × 4 | `player_character` | Per-player character identity (0=Warrior, 1=Valkyrie, 2=Wizard, 3=Elf) |
| 0x9048F0 | 2 B × 4 | `player_joystick` | Per-player last joystick direction |
| 0x9048F8 | 2 B × 4 | `lobber_shot_vec_h` | Horizontal component for lobber shots |
| 0x904900 | 2 B × 4 | `lobber_shot_vec_v` | Vertical component for lobber shots |
| 0x904908 | 1 B × 4 | `player_redraw` | Per-player redraw flags (bit 0 = score needs redraw, cleared by `draw_player_score`; bit 1 = health, set on damage, cleared by `draw_player_health`). |
| 0x90490C | 2 B | `idle_timer` | Counts up while the post-player-loop activity gate is set. Above 0x04B0 or 0x0A8C (selected by caller state), `open_timed_doors` removes type-0x0D/0x0E door objects and this word becomes 0xFFFF to disable further increments. The common level-start tail clears it at 0x4836A after `thief_setup`, re-arming timed doors every level. |
| 0x90490E | 2 B × 4 | `player_bonusmult` | Per-player current bonus multiplier |
| 0x904876 | 2 B | `current_player` | Index (0–3) of the player currently being processed by `main_move_players`; written each iteration of the per-player loop |
| 0x904916 | 2 B | `frame_overflow` | Non-zero if frame took too long to render |
| 0x904918 | 2 B | `game_mode` | Game mode (see Game Modes enum) |
| 0x90491A | 2 B | `attract_legend` | Current legend screen number |
| 0x90491C | 4 B | `level_flags` | Level-flags longword = maze header bytes 1–4 big-endian (byte 0 = `level_flags_1` at 0x90491C, byte 1 = `level_flags_2`, byte 2 = `level_flags_3`, byte 3 = `level_flags_4`; see §3.12 enums, verified reader-by-reader). This IS the variable historically called `ram.maze_pickup_config`. Assembled and per-level randomized by `maze_load_pickup_config` (0x436FE); LFLAG3 bit 6 (ExitMoves) is cleared by `maze_scan_objects` when only one exit exists |
| 0x904920 | 2 B × 4 | `player_input_raw` | Per-player raw joystick input word |
| 0x904928 | 2 B | `level_players_active` | Number of active players on a level |
| 0x90492A | 2 B × 8 | `shot_timer_next` | Time until next demon/lobber shot |
| 0x90493A | 2 B × 4 overlapping view | `score_display_timer` | Four 60-frame timers for the temporary score/effect MOB slots. `playfield_showscore` claims a zero entry and loads 60; `main_score_update` decrements it and removes the corresponding slot when it expires. Element 3 at 0x904940 aliases reserved `mob_depth_key[0]`. |
| 0x904940 | 2 B × 32 overlapping view | `mob_depth_key` | Per-managed-MOB depth/packed-position key used by the Y-sorted display-list insertion code, exact range 0x904940–0x90497F. General list code indexes `base + slot×2`; shot processing uses the biased base 0x904942 for logical slot 1 onward. Reserved element 0 at 0x904940 safely aliases `score_display_timer[3]`; the final two nominal words alias `mob_effect_anim_counter`. |
| 0x90497C | 1 B × 4 overlapping view | `mob_effect_anim_counter` | Four per-channel counters for temporary transporter/score-star effect MOBs. `tport_cycle_start` initializes a selected byte to 0xFF; loop 3 of `main_score_update` increments it and advances/removes pictures in the 0x924–0x95A family. This view aliases `mob_depth_key[30..31]`. |
| 0x904B02 | 24 B (12 words) | `shot_anim_lifetime_counter` | One word per projectile channel (`MOB slot - 1`). `main_handle_shots` decrements the selected word every eligible frame. For channels 0–7, expiration reloads it from `shot_counter_reload` and advances the projectile picture; for lobber channels 8–11, the four 0x20 reload values act as lifetime counters and zero triggers impact/removal handling (0x477E8 also removes a *max-tier* channel 4–7 at zero, which is how the dragon's breath expires). Shot creation and reflection paths initialize or clear the same indexed words; `dragon_fire_setup` writes 0x13 into `[shot_slot-1]` for the close-range breath (0x54814). |
| 0x904980 | 4 B × 4 | `player_health` | Per-player health (32-bit longwords, stride 4). |
| 0x904990 | 4 B × 4 | `player_score` | Per-player current score (32-bit longwords) |
| 0x9049A0 | 1 B × 4 | `player_status` | Per-player status: 0x01=alive here, 0x02=alive next, 0x04=death/high-score sequence (including initials when qualified), 0x08=exiting/respawn wait, 0x10=selecting character, 0x20=secret-winner name entry |
| 0x9049A4 | 2 B × 4 | `player_facing_dir` | Per-player facing direction (0=up, 1=up-right, 2=right, 3=down-right, 4=down, 5=down-left, 6=left, 7=up-left) |
| 0x9049AC | 2 B × 4 | `player_fighting_dir` | Per-player fighting direction (1=up, 2=up-right, ..., 8=up-left) |
| 0x9049B4 | 2 B × 4 | `player_shooting` | Per-player: 0xFFFF if shooting, 0 otherwise |
| 0x9049BC | 2 B × 4 | `player_anim_counter` | Per-player free-running animation frame counter (incremented every active frame). Divided and masked to index walking/fighting/idle animation tables. Counter ÷4 &3 = walking frame; ÷2 &7 = fighting frame. |
| 0x9049C4 | 2 B × 12 | `shot_direction` | Direction/state word for each of 12 projectile channels. Values 0–7 are compass directions; reflection and special-shot paths also retain flag bits in the same word. |
| 0x9049DC | 2 B | `player_it` | Player who is IT (0–3) or 0xFFFF (-1) if nobody |
| 0x9049DE | 2 B | `mob_depth_list_head` | Head MOB ID of the global depth-sorted display list; the placement routines update it when inserting before the current first MOB |
| 0x9049E0 | 2 B | `maze_player_start_slot` | Packed maze slot randomly selected by `maze_scan_objects(-1)` from the PLAYERSTART records before that marker is replaced with floor. It remains the first-player and post-death continue spawn even after no PLAYERSTART marker remains live. |
| 0x9049E2 | 2 B | `two_player_mode` | Game pricing/two-player mode config |
| 0x9049E4 | 4 B | `dialog_first_encounter_flags` | Bitmask of which first-encounter dialogs have been shown |
| 0x9049E8 | 2 B | `treasure_timer` | Time spent in treasure room |
| 0x9049EA | 4 B | `last_coin_state` | Cached coin counter for edge detection |
| 0x9049EE | 2 B | `speech_counter` | **Sound-board recovery holdoff, not a speech timer.** The only nonzero store is 0x42DDA in `sound_system_reset`, which loads 0xB4 (180 frames); `sound_response` clears it when the rebooted sound CPU answers 0xFF, decrements it otherwise, and resets again if it reaches zero unanswered. While nonzero, `sound_play` (0x4AD7E) skips the immediate send and queues, and `main_update_sound` (0x4AE36) skips the drain. A byte-level scan of `row76.bin` for the address finds references only at 0x42D14, 0x42DDA, 0x4AD7E and 0x4AE36; nothing in the speech path writes it. The name is retained for continuity with the loader symbols. See `04_game_subsystems.md` §11.3. |
| 0x9049F0 | 2 B | `sound_queue_state` | Destination for the one-byte reply to status command 0x07, which `sound_response` directs at its low byte (0x9049F1). Nonzero low three bits are the sound board's own error report and force `sound_system_reset`. |
| 0x9049F2 | 2 B | `sound_idle_timer` | Countdown between sound-CPU response/ping attempts |
| 0x9049F4 | 2 B | `sound_cpu_retry_count` | Sound-CPU retry counter; a sustained failure above 180 triggers the full reset path. |
| 0x9049F6 | 2 B × 4 | `player_hurt_palette_offset` | Per-player byte offsets into the four class-specific hurt-palette cycles. Player setup initializes each entry to `character × 0x12`; `game_vblank` adds the selected word to that player's cycle base. |
| 0x9049FE | 2 B × 4 | `player_power_palette_offset` | Per-player byte offsets into the four class-specific power-palette cycles. Player setup initializes each entry to `character × 0x30`; `game_vblank` adds the selected word to that player's cycle base. |

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
| 0x904A26 | 2 B × 4 | `player_state_timer` | Reused per-player timer. During live play below 200 health, `main_health_countdown` increments it modulo 0x8000: the low nibble produces the 8-frames-dim/8-frames-normal health-number pulse, and `timer & heartbeat_mask[health >> 5] == 0` schedules the heartbeat sound. During death/high-score handling it is instead a countdown: 0x0A8C = 2700 frames (45 s) for initials entry, 0x0258 = 600 frames (10 s) for the GAME OVER display. `0xFFFF` disables the timer. |
| 0x904A2E | 2 B × 4 | `name_entry_scroll_velocity` | Signed per-player character-selection velocity/accumulator, clamped to ±0xA0 and fed to `name_entry_step_char` during ordinary or secret name entry |
| 0x904A36 | 1 B × 4 | `name_entry_repeat_delay` | Per-player byte countdown that delays auto-repeat while the initials joystick remains held; the former 2-byte element size overlapped the buffer at 0x904A3A |
| 0x904A3A | 4 B × 4 | `player_initials_buf` | Four-byte per-player working record: byte 0 is the selected initials cursor/state and bytes 1–3 hold the three editable characters (initialized to 'A') |
| 0x904A4A | 1 B × 4 | `player_highscore_rank` | Per-player rank returned by the high-score qualification API; 0–9 qualifies and values outside that range skip initials entry |

**`game_settings` (0x904A24) bit layout:**

| Bits | Meaning |
|------|---------|
| 0–4 | COINHEALTH setting: index 0–31 into `health_per_coin_table` (0x57862), giving 100–2000 in 25/50/100-unit steps |
| 5–7 | Operator-facing **Game Difficulty** setting (0–7), implemented chiefly as monster-generation tuning: selects the row of `monster_spawn_probability_table` (0x40E46) for each generator's probability out of 32 — `andi.w #0xE0,d3; lsr.w #3,d3; add.w level_players_active,d3; subq.l #1,d3; lea 0x40E46,a0` at 0x40F62–0x40F70. It also scales the solo-play Warrior/Wizard random-pickup reduction in `maze_addrandompickups`. MAME's Game Options screen confirms Atari's label; disassembly establishes the actual effects. |
| 8–9 | **Coins to Start** in the OS operator editor: values 0–3 display 1–4. MAME's Game Options screen rendered value 0 as “1” from the default word 0xE090. No normal game-code reader masks 0x0300; the meaning is Verified for operator configuration/storage, not as a gameplay consumer. |
| 10 | **Reduced-text / short-dwell selector**, not a 2-player flag (the two-player config word is `two_player_mode` at 0x9049E2). Eleven read sites mask 0x0400; 0x4523C selects `global_ui_delay_timer` 0xB4 vs 0x96, and §5.6 `first_encounter_alt_message_ptrs` selects the compact message set from the same bit |
| 11 | Speech disable. Masked at 0x4AD5A gating the `sound_play` at 0x4AD76, and §5.5 `treasure_timeout_speech` forces element 0 from the same bit |
| 12 | **Restore Factory Default Settings** request in the OS operator editor. MAME rendered the clear default bit as “No.” No normal game-code reader masks 0x1000; the meaning is Verified for the editor/schema. |
| 13 | Secret-room winner name-entry enable: gates the ENTER-YOUR-NAME flow in `secret_getname` (0x54EC6); when clear, winners get `player_status` = 2 and a short between-level delay (verified — sole reader) |
| 14 | Music/attract sound enable |
| 15 | **Reset High Score Tables** request in the OS operator editor. MAME rendered the set default bit as “Yes.” No normal game-code reader masks 0x8000; the meaning is Verified for the editor/schema. |

### 1.11 Player Extended State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A4E | 2 B | `global_ui_delay_timer` | Shared display/input holdoff timer. Level setup loads 150/180/600 frames and `main_start_game` waits for zero before entering the maze; secret-name entry and related UI code reuse it for cursor/input pacing. While nonzero it also suppresses treasure countdown processing. |
| 0x904A50 | 1 B × 4 | `player_treascount` | Count of treasures picked up by player |
| 0x904A54 | 2 B × 4 | `player_stundelay` | Timer for player being stunned |
| 0x904A5C | 2 B | `death_hits` | Global hit count shared by all players and Death MOBs. Every player shot that hits Death, ordinary or supershot, increments it; `death_potion_score` uses `death_hits & 7` to select the score and popup variant. It is distinct from the four per-player Death-damage accumulators at 0x904B3A and does not control Death's >200 dismissal threshold. |
| 0x904A5E | 2 B | `unused_init_word_904a5e` | Write-only in the program ROM: `one_time_init` clears this word, and no reader or other writer exists. It is retained here so the initialized RAM location is not mistaken for an unidentified live state variable. |
| 0x904A62 | 2 B | `monster_cull_h_origin` | Horizontal origin for monster visibility/culling, computed as `(pf_hscroll - 0x17) << 7` |
| 0x904A64 | 2 B | `monster_cull_v_origin` | Vertical origin for monster visibility/culling, computed as `(0xF9 - pf_vscroll_lo) << 7` |
| 0x904A66 | 2 B × 4 | `lobber_shot_h_accum` | Per-lobber-projectile horizontal subpixel accumulator; updated from velocity table 0x9048F8 and converted back into MOB hpos |
| 0x904A6E | 2 B × 4 | `lobber_shot_v_accum` | Matching vertical subpixel accumulator; updated from velocity table 0x904900 and converted back into MOB vpos |
| 0x904A76 | 2 B × 4 × 2 | `door_endpoint_pos[4][2]` | Four two-ended door records. Each word is a packed maze position; `door_record_endpoints` (0x51E80) and its vertical/horizontal scanners populate the two endpoints. |
| 0x904A86 | 2 B × 4 × 2 | `door_endpoint_dir[4][2]` | Direction code parallel to `door_endpoint_pos`: vertical scans write 0 for above and 2 for below; horizontal scans write 3 for left and 1 for right. Door pictures ≥0x9D7C directly install 0/2 and pictures ≥0x9D3C directly install 3/1. Consumed by the door-opening/traversal logic. |

### 1.12 Dialog State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A96 | 4 B | `ptr_dialog_pos` | Pointer to dialog position in alpha RAM |
| 0x904A9A | 2 B | `dialog_dim_H` | Dialog horizontal dimension |
| 0x904A9C | 2 B | `dialog_dim_V` | Dialog vertical dimension |
| 0x904A9E | 2 B | `dialog_timer` | Dialog lifetime countdown. Nonzero means a dialog is active and suppresses conflicting gameplay/display work; `main_msgbox_countdown` decrements it and erases the box when it reaches zero. Values of 1 are also used to force immediate cleanup during screen transitions. |
| 0x904AA0 | 2 B | `ptr_dialog_box_x` | Dialog X position pointer |
| 0x904AA2 | 2 B | `ptr_dialog_box_y` | Dialog Y position pointer |
| 0x904AA4 | 30 B | `dialog_msg_buf` | Buffer for dialog/name-entry message string (the buffer itself, not a pointer — `secret_getname` fills it with 'A' + 28 spaces + NUL directly) |

### 1.13 Player Death / Respawn

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904AC2 | 2 B | `scroll_hpos_origin` | Wrapped fixed-point horizontal screen origin, computed by `set_scroll_pos` as `(pf_hscroll - 8) << 7`. Player/shot boundary tests subtract it from MOB horizontal positions. |
| 0x904AC4 | 2 B | `scroll_vpos_origin` | Wrapped fixed-point vertical screen origin, computed by `set_scroll_pos` as `(0x108 - pf_vscroll_lo) << 7`. Player/shot visibility and boundary tests subtract it from MOB vertical positions. |
| 0x904AC6 | 4 B | `welcome_elapsed_frames` | Frames elapsed in the current game/start loop. Cleared whenever a new maze/player-join presentation is built and incremented once per `main_start_game` call. `speech_welcome` uses 600 as both its initial delay and reload value before speaking the joining character's name. |
| 0x904ACA | 1 B × 4 | `player_lowhealth_spoken` | Per-player one-shot latch for the low-health voice warning. `player_lowhealth` returns immediately when set, sets it after the warning, and player death/join setup clears it. |
| 0x904ACE | 2 B × 4 | `player_respawn_speech_timer` | Per-player signed countdown shared by death/respawn processing and low-health speech pacing. `-1` is the inactive/ready sentinel; the actor loop decrements nonnegative entries, and a low-health warning loads 0x0708 frames. |
| 0x904AD6 | 2 B × 4 | `player_pending_damage` | Per-player damage accumulated by hit resolution since the periodic player-state update. The update uses it for low-health warning thresholds, adds it into `player_damage_total`, then clears it. |
| 0x904ADE | 2 B × 4 | `player_damage_total` | Per-player cumulative damage statistic, increased from `player_pending_damage` and saturated at 0x7D00. It is divided by the associated play/health-update count when deciding contextual speech. |
| 0x904AE6 | 2 B × 4 | `player_damage_sample_timer` | Per-player signed 60-frame sampling timer. Join setup loads 60; `player_damage_sample_update` counts it down, processes pending damage at zero, and reloads 60. |
| 0x904AEE | 2 B × 4 | `player_damage_sample_count` | Number of completed damage-sampling intervals for each player. The contextual-speech test divides cumulative damage by this count; it is reset when an averaging window ends. |
| 0x904AF6 | 1 B × 4 | `player_eatcount` | Per-player count of foods eaten |
| 0x904AFA | 2 B × 4 | `hurt_speech_timer` | Per-player randomized cooldown for class-specific hurt speech. `player_hurt_speech_timer` decrements and reloads it; negative means a new voice may be played. |

### 1.14 Score and Coin State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904B1A | 4 B × 4 | `player_scorepercoin` | **Verified:** per-player unsigned 32-bit score divided by the player's 16-bit inserted-coin count through `calc_score_per_coin`; this is the metric passed to OS `rank_high_score` (0x1C6), not merely an attract-display cache |
| 0x904B2A | 2 B × 4 | `player_coincount` | Per-player number of coins inserted |
| 0x904B32 | 2 B × 4 | `player_onlevel` | Per-player what level player is on |
| 0x904B3A | 2 B × 4 | `player_death_damage_counter` | Per-player Death-damage accumulator used by `death_damage_accumulate`. Death contact adds 4 normally or 3 when `player_powers` byte 1 bit 1 is set; a supershot adds 25, while an ordinary shot does not add to this counter. A total strictly greater than 200 clears the counter and dismisses the supplied Death MOB with a transporter-cycle effect. The value can span Death MOBs within one level, but successful `player_start_inner` placement clears it on normal level entry or player join. |
| 0x904B4A | 2 B × 4 | `ff_hurt_timer` | Per-player forcefield-contact hurt/sound cooldown |
| 0x904B42 | 2 B × 4 | `death_touch_timer` | Per-player cooldown/state for contact with Death |

### 1.15 Level / Maze State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904B52 | 2 B | `level_next` | Number of next level. Written only by `player_exit_sequence`: `levelnum_current + 1` on an ordinary exit, wrapping to 6 by subtracting 994 when it would exceed 999 (0x52DC6–0x52DE0); a flat 6 on the `MAZEOBJ_EXITTO6` path (0x52E38). Committed to `levelnum_current` by `main_start_game` (0x480F2) and the `show_level_end_bonus_screen` epilogue (0x4D8EC). While a level is being played it equals the current level number, which is why `main_move_players` tests it against 6 before running the treasure countdown. |
| 0x904B54 | 2 B | `maze_next` | Number of next maze. Written only by `player_exit_sequence` and `maze_checknum`; see `06_maze_catalog.md` §3.2 for the full selection algorithm. Committed to `mazenum_current` by `main_start_game` (0x480FC) and the bonus-screen epilogue (0x4D8E2), and also restored into `mazenum_current` by `main_health_countdown` (0x469F6) when the last player dies inside a treasure room. |
| 0x904B56 | 2 B | `special_bonus_score` | Point value shown/awarded for the current special dropped bonus. Defaults to 100, is derived from the carried thief/mugger item encoding (`value >> 6`), and is set to 2000 for the dragon bonus. |
| 0x904B58 | 2 B | `playfield_palette_index` | High nibble of maze header byte 6. Selects one of the 16 main 32-byte palettes at 0x5D5C8; value 0x10 is also used by callers as the fixed special-palette sentinel. It is not a scroll coordinate. |
| 0x904B5A | 2 B | `playfield_special_variant` | Low nibble of maze header byte 6. `init_display` multiplies it by 32 when selecting from the special palette bank at 0x5D7C8/0x5D7E8. It is not a scroll coordinate. |
| 0x904B5C | 2 B | `floorpattern` | Floor graphic pattern selected from the maze header |
| 0x904B5E | 2 B | `wallpattern` | Wall graphic pattern selected from the maze header |
| 0x904B60 | 2 B | `attract_count` | Number of times through attract sequence |
| 0x904B66 | 4 B × 4 | `demo_ptr` | Per-player demo data pointer (longwords) |
| 0x904B76 | 1 B × 4 | `demo_timer` | Per-player demo frame timer (bytes) |
| 0x904B7A | 2 B | `monster_generation_retry_timer` | Signed retry delay used by `handle_generate` in the special negative-generation state: it counts down, clamps to zero on expiry, and only then permits the forced generation attempt. |
| 0x904B7C | 2 B | `attract_timer` | Attract/display-mode lifetime countdown. `start_attract_screen` loads 0x05DD for TITLE, 0x0258 for SCORES/LEGEND, or 0x1C20 for DEMO; `main_attract` decrements it and advances modes at expiry. Gameplay/continue paths also use it as a transition gate. `0xFFFF` is the disabled sentinel, not a separate continue-screen-inhibit meaning. |
| 0x904B7E | 2 B | `level_next_potion` | Level countdown to next hidden potion |
| 0x904B80 | 2 B | `level_next_treasure` | Level countdown to next treasure room. Seeded with `getrandom(3) + 3` (3–5) by `maze_new_level_setup` when `levelnum_current` reaches 6 (0x438E4–0x438FC), and reloaded from the same expression by `show_level_start_screen` each time it fires (0x44E9C–0x44EAC). `main_move_players` decrements it once per level on the end-of-level path, and only while `mazenum_current` < 104 and `level_next` > 6 (0x4A756–0x4A788). Zero at level start selects a treasure room. See `06_maze_catalog.md` §3.5. |
| 0x904B82 | 2 B | `title_intro_state` | Small persistent title-intro state/counter. On TITLE setup, zero can trigger the theme and become 2; later entries decrement it. `show_continue_prompt` seeds it to 1, and logo setup chooses between ROM animation sequences 0x5AC2E/0x5AC4E according to zero vs nonzero. It is not a “continue screen active” boolean. |
| 0x904B84 | 2 B | `level_tport_count` | Number of transporters on current level |
| 0x904B86 | 2 B | `games_played_counter` | Persistent completed-game/statistics counter mirrored to EEPROM at 0x904B92. It increments when all four player-health slots are empty, is capped for high-score entry, and at 2000 triggers the settings/unlock update before resetting. |
| 0x904B88 | 4 B | `ptr_maze_data` | Pointer to current maze data |
| 0x904B8C | 2 B | `maze_slapstic_cmd_offset` | Offset to activate bank switch for current level |

### 1.16 Thief / Mugger State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904B98 | 2 B | `thief_victim_pos` | Last packed position of the thief's target. Scheduling initializes it before the arrival countdown; every later victim cell handoff updates it and writes the old-to-new direction into the pursuit nibble. |
| 0x904B9A | 2 B | `thief_victim` | Player number of the richest player, selected before `thief_enter_time` is loaded so movement during the delay records the route. |
| 0x904B9C | 2 B | `thief_direction` | Current thief movement/animation direction (0–8). It is produced by `calc_direction` and selects the directional row in the normal and compact thief animation tables. |
| 0x904B9E | 2 B | `thief_enter_time` | Initially the scheduled arrival countdown. Deployment at zero creates the thief/mugger at `thief_start_location` and reloads this word with 0x3C for the entrance pause; ordinary thief animation remains gated until it becomes negative. |
| 0x904BA0 | 2 B | `thief_mode` | Thief's current mode (see Thief Modes enum) |
| 0x904BA2 | 2 B | `thief_previous_pos` | Previous thief maze/MOB slot. Movement copies `thief_next_pos` here before calculating the following cell; exit/steal and route-recovery code use it as the cell behind the thief. |
| 0x904BA4 | 2 B | `thief_current_pos` | Thief's current maze cell, which is also the hardware MOB slot occupied by the thief. It indexes the MOB arrays and is replaced whenever movement transfers the thief into a new cell; zero means no active thief. |
| 0x904BA6 | 2 B | `thief_next_pos` | Candidate/next maze cell for thief movement. It initially equals the spawn cell, is recomputed from direction deltas, and becomes `thief_previous_pos` on the next route step. |
| 0x904BA8 | 4 B | `mugger_item_nextlevel` | Item that the mugger carried to the next level; nonzero makes `maze_addrandompickups` place type 0x32 food |
| 0x904BAC | 4 B | `thief_item_nextlevel` | Item that the thief carried to the next level; `0x7D30` means empty, otherwise bits 5–0 are the pickup type and the upper value shifted right 6 restores `special_bonus_score` for a multiplier bag |
| 0x904BB0 | 4 B | `mugger_item_carried` | Item that the mugger is currently carrying |
| 0x904BB4 | 4 B | `thief_item_carried` | Item that the thief is currently carrying |
| 0x904BB8 | 2 B | `thief_collision_direction_code` | One-based direction/contact code set when the thief first collides with its target player (`thief_direction + 1`). It suppresses repeated damage during the same contact and is folded into `thief_move_engine`'s return adjustment; zero means no active contact code. |
| 0x904BBA | 2 B | `thief_start_location` | Target player's packed cell when the visitor is scheduled, before the arrival delay. Deployment later creates the thief/mugger at this saved old location while the pursuit grid leads toward the player's newer cells. |
| 0x904BBC | 2 B | `thief_stolen_item` | Tile type of last item stolen by thief |
| 0x904BBE | 2 B | `thief_tport_active` | Thief transporter-transition latch. `thief_start_tport_anim` sets it to one; normal movement clears it, and occupied-cell replacement is suppressed while it is nonzero. |

### 1.17 Transporter State

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904BC0 | 2 B | `treasure_announcement_delay` | Inter-announcement delay during the treasure-room countdown. The decrement is inside the full-second path, so its units are countdown seconds rather than frames; the warning lines load 1 or 2 from 0x5AC18. `-1` disables it on the continue screen. |
| 0x904BC2 | 2 B | `treasure_voice_set` | Treasure-countdown voice-sequence selector (0 or 1–4), chosen at the ten-second mark. It selects one of four ROM sound-pointer rows for the remaining numbered announcements and is cleared after use. |
| 0x904BC4 | 2 B × 4 | `tport_saved_picture` | Per-player saved MOB picture words. `tport_restore_player_picture` indexes this array with `player × 2`; exact range 0x904BC4–0x904BCB. |
| 0x904BCC | 2 B | `tport_saved_mob_state` | Saved MOB state during transport (word) |
| 0x904BCE | 2 B × 4 | `player_tport_phase` | Per-player transport phase/state words. `main_scroll_playfield` also treats a negative value as “player active/in maze”; exact range 0x904BCE–0x904BD5. |
| 0x904BD6 | 2 B | `tport_frame_counter` | Shared transporter transition frame counter. The animation path increments the word and tests its low bit through byte 0x904BD7. |
| 0x904BD8 | 2 B × 4 | `player_tile_or_tport_dest` | Per-player packed destination/tile-position words. Transport code uses them as destination slots; `compute_screen_coords` and `main_scroll_playfield` use the same values as player tile positions. Exact range 0x904BD8–0x904BDF. |
| 0x904BE0 | 2 B | `tport_transition_mob` | MOB slot used for transition effect |
| 0x904BE2 | 2 B × 4 | `player_tport_type` | Per-player transporter type/source-state words, exact range 0x904BE2–0x904BE9. |
| 0x904BEA | 2 B × 4 | `player_tport_route_state` | Per-player transporter direction/route state. Player teleport movement reads its direction nibble, and route-building passes the word into `tport_route_connect`. |

### 1.18 Miscellaneous

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904BF2 | 2 B | `movement_type` | Set to 2 by `main_move_players` before calling `player_try_move`; encodes movement type |
| 0x904BF4 | 8 B | *(unused gap)* | No static program-ROM reference exists. The old claim that this was an invisibility-flash timer is false: flicker uses `invis_timer` at 0x905F50 together with the mask table at 0x58070. |
| 0x904BFC | 2 B | `random_seed` | LCG random number seed. RNG formula for the observed bounds 0–0x7FFF: `seed = seed * 0x3619 + 0x5D35`; result = `floor(range * ((seed_new + 0x8000) & 0xFFFF) / 65536)`. The `swap` / `asr.l #1` / `add.l` sequence at 0x5FC3A–0x5FC40 supplies the `+0x8000` bias. Because the multiply is `MULS.W`, a range with bit 15 set is treated as signed and does not have the normal `[0,range)` guarantee. **The seed is never explicitly initialized.** A byte-level scan of both `row76.bin` and `row9.bin` for the 32-bit address finds exactly two references, the `lea` instructions at 0x5FC48 (`random_word`) and 0x5FC50 (`getrandom`), matching `generated/ram_operands.csv`. No boot path, `one_time_init`, level-start path, or attract/demo setup writes it, and no bulk clear covers it (`maze_setupnew`'s `memclear_words` calls span 0x902000, 0x904066, and 0x905F80 only). Its power-on value is whatever the destructive video-RAM-spare test leaves behind, and it then free-runs one step per draw across attract screens and sessions alike. Consequence: nothing in the cabinet is reproducible by re-entering a mode, including the attract demo. gauntpy deliberately defaults its playable host to zero for repeatable testing, accepts an explicit 16-bit value, and offers host-random initialization on request; all three are one-time power-on values and never reseed the running stream. |
| 0x904C00 | 2 B | `vblank_abort_guard` (formerly `vblank_palette_inhibit` / `vblank_abort_latch`) | **Strong inference:** ordinary spare RAM cleared by the OS's startup range clear; no later explicit reference writes it, and its only literal reference in either ROM is the read at 0x401CA. Nonzero, or a VBLANK semaphore reaching 0x40, branches to the watchdog-abort JMP at 0x40146. Target 0x10000 is in a decoded but unpopulated OS-ROM aperture, not an unmapped address. If its fetch faults, the OS exception handler clears D0 and the game exception hook deliberately re-enters the same JMP; for any non-faulting empty-bus value, execution has still stopped servicing the 128 ms watchdog. Thus the stable semantic result is a watchdog reset, while the exact first fetched word is board-state dependent. |
| 0x905F00 | 6 B × 4 | `player_hurt_palette_stubs` | Four RAM-resident absolute-JMP stubs, one per player. `player_join_setup` writes opcode 0x4EF9 and a character-specific target into each six-byte record; `game_vblank` calls the selected stub during hurt cycling. Exact range 0x905F00–0x905F17. |
| 0x905F18 | 6 B × 4 | `player_power_palette_stubs` | Parallel four-entry absolute-JMP stub table for power cycling, patched by player setup and called by `game_vblank`. Exact range 0x905F18–0x905F2F. |
| 0x905F30 | 2 B × 4 | `hurt_cooldown` | Per-player hurt-palette timer. Monster/shot/forcefield hits load 0x12; `game_vblank` subtracts 6 per field and uses the 0x0C/0x06 states to copy the class-specific white-flash entries from 0x5B20E+ into live color RAM, restoring the base entries at zero. It does not gate damage. |
| 0x905F38 | 2 B × 4 | `repulse_timer` | Per-player repulsiveness countdown; expiry clears `player_powers` bit 9 |
| 0x905F40 | 2 B × 4 | `acid_timer` | Per-player acid slow countdown |
| 0x905F48 | 2 B × 4 | `dizzy_timer` | Per-player poison-dizziness countdown. Poison food/potions load 0x4B0; normal-play movement decrements it, then while nonzero remaps the active-low direction nibble through `stun_direction_remap` at 0x4A4FA. |
| 0x905F50 | 2 B × 4 | `invis_timer` | Per-player invisibility countdown |
| 0x905F58 | 2 B × 4 | `debounce_shift_magic` | Per-player **Magic-button** (JOY_MAGIC_BIT, bit 0) sample history. `input_debounce` (0x40644) does `lsr.w #1,d0` to shift the raw bit into X, then `roxl.w` this word, so the **newest sample lands in bit 0** and older samples migrate toward bit 15. Player *n* uses `0x905F58 + n×2`. |
| 0x905F60 | 2 B × 4 | `debounce_shift_fire` | Per-player **Fire-button** (JOY_FIRE_BIT, bit 1) sample history, updated by the second `lsr.w`/`roxl.w` pair at 0x40658–0x4065A with the same newest-in-bit-0 ordering. Player *n* uses `0x905F60 + n×2`. |
| 0x905F68 | 1 B × 4 | `player_supershot` | Per-player supershot state (POWER_SUPERSHOT pickup): while > 0, shots do 3 damage to ordinary monsters (10 to players), pierce through monsters (except Death/IT), hit blinking sorcerers, and break treasure/invulnerable items. Death is a special case: a supershot adds a fixed 25 to the shooting player's `player_death_damage_counter` via `death_damage_accumulate`. |
| 0x905F6D | 1 B | `secret_saved_supershot` | Single-byte secret-room transition scratch. `main_start_game` saves the selected secret entrant's supershot byte here before clearing the ordinary per-player value; `show_level_end_bonus_screen` adds it back to that player on return. The former continue-screen interpretation was contradicted. |
| 0x905F80 | 2 B × 64 | `priority_bucket_heads` | Complete cumulative head table for the one depth/priority chain, exact range 0x905F80–0x905FFF. Insertion/removal updates entries from the selected band toward element 0; `main_move_monsters` uses element 0 as its fallback head. |
| 0x905F82 | 2 B × 63 overlapping tail view | `priority_bucket_heads_tail` | Elements 1–63 of `priority_bucket_heads`. Scroll-indexed traversal addresses this tail base. |
| 0x905C54 | 256 B (2 B cells, 22 per 0x80-B row) | `tport_route_forward` | Forward transporter/pathfinding connection table, exact range 0x905C54–0x905D53. Cell address is `base + (id / 22) * 0x80 + (id % 22) * 2`, verified at `tport_route_write_pair` 0x51082–0x51092. One-based transporter IDs 1–32 reach only row-0 offsets 0x02–0x2A and row-1 offsets 0x00–0x14. Bits 15–8 hold the linked transporter ID and the low nibble holds direction+1 (0 means no route). MAME observed live route cells coexisting with all portrait words: portrait destinations begin at padding offset 0x36, beyond the route index domain. This is safe simultaneous spatial reuse, not lifetime-separated aliasing. |
| 0x905D54 | 256 B (2 B cells, 22 per 0x80-B row) | `tport_route_reverse` | Reverse-direction companion to `tport_route_forward`, exact range 0x905D54–0x905E53, with the same padded-row addressing, reachable offsets, and word format. `tport_route_connect` (0x4E684) writes both directions; 0x4E73A only fills an empty route. MAME route-call tracing confirmed that its live cells do not overlap the portrait padding. |
| 0x910700 | 2 B × 32 | `tport_pos_table` | Maze slot index for each transporter |
| 0x910780 | 2 B × 64 | `ff_segment_table` | Forcefield segment list, exact range 0x910780–0x9107FF. Setup clears all 64 words, emits at most 62 records, and leaves a zero terminator. Record bits: 9–0 start packed maze cell; 13–10 segment length minus one; bit 14 horizontal-wrap correction; bit 15 set for horizontal segments and clear for vertical. |

---

## 2. OS RAM Variables

**Confidence: Verified** for addresses and observable use; see
`02_os_rom.md` §9 for the evidence-qualified OS map.

See `02_os_rom.md` section 9 for full OS RAM variable map (`0x904F00–0x904FFF`).

---

## 3. Enums and Constants

**Confidence: Verified** for numeric values, and for every enum bound to a ROM
table — §3.2–3.6, §3.10, §3.12–3.14, §3.17, §3.19 and §3.20 had their
cardinality and index rule re-derived from the consuming instructions.

Eight sections bind to no ROM table: §3.1, §3.7, §3.8, §3.9, §3.11, §3.15,
§3.16 and §3.18. Each now carries its own label naming the individual values a
compare or bit-test operand confirms and the ones nothing distinguishes. A
numeric slot can be certain while its name is not; where no instruction
separates one name from another the name is labelled **Unknown** even though
the encoding stays Verified.

### 3.1 Alphanumeric Character Masks

**Confidence: Unknown** for all twelve names. These are alpha-RAM/OS text-path
constants; no game-ROM consumer was traced for any of them, so the field splits
are transcribed from the loader symbols rather than from a verified use site.

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
| POWER_INVISIBILITY_BIT | 8 |
| POWER_REPULSIVE_BIT | 9 |
| POWER_REFLECT_BIT | 10 |
| POWER_TRANSPORT_BIT | 11 |
| POWER_SUPERSHOT_BIT | 12 |
| POWER_INVULN_BIT | 13 |

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

**Confidence: Verified** that bits 0–3 live in `dragon_state` (0x904890);
**Unknown** for all four names. All seven references to 0x904890 were
disassembled over a fourteen-instruction window and contain no `btst`, `bclr`
or `bset` on that address, so nothing in the shipped code distinguishes
SLEEPING from STUNNED, TURNING or LOCKED.

| Name | Bit |
|------|-----|
| DRAGON_SLEEPING_BIT | 0 |
| DRAGON_STUNNED_BIT | 1 |
| DRAGON_TURNING_BIT | 2 |
| DRAGON_LOCKED_BIT | 3 |

### 3.8 Fixed MOB IDs

**Confidence: Verified** that 1–29 are reserved MOB slot numbers in
`vram.mob_picture`. A 600-second MAME attract trace dynamically identified
player-shot slots 2/4, demon-shot slot 5, effect slots 13/14, score slot 17,
exit slots 21/22/24, and transporter slot 26 from their creation and animation
PCs. Together with the code's `base + player/channel` indexing, these events
verify the named slot families; not every member became live in that demo
corpus.

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

**Confidence: Verified** for GAMEMODE_NORMAL, TREAS_EXIT, DEMO, TITLE and
SCORES: each appears as a `cmpi.w` operand against `game_mode` (0x904918).
**Unknown** for GAMEMODE_LEGEND 0xFFFC — no compare against that value exists;
the legend lane is reached only through the `tst.w game_mode` / `bge` sign test
(for example at 0x4C4E0).

| Name | Value |
|------|-------|
| GAMEMODE_NORMAL | 0x0000 |
| GAMEMODE_TREAS_EXIT | 0x0001 |
| GAMEMODE_LEGEND | 0xFFFC |
| GAMEMODE_DEMO | 0xFFFD |
| GAMEMODE_TITLE | 0xFFFE |
| GAMEMODE_SCORES | 0xFFFF |

### 3.10 Game Settings (COINHEALTH values)

**Confidence: Verified** for gameplay fields with an observed mask and for the
three OS-operator fields observed in MAME. The latter have no normal game-code
reader; their names describe option-editor/EEPROM semantics. This table and
the `game_settings` bit layout in §1.10 are the same sixteen bits and must
agree.

| Name | Value | Evidence |
|------|-------|----------|
| GSETTING_COINHEALTH | 0x001F, index 0–31 into `health_per_coin_table` (0x57862) = 100–2000 in 25/50/100 steps | `andi #0xFF` at 0x430A8; table read by `coincheck`/`player_coindrop` |
| GSETTING_DIFFICULTY_MASK | 0x00E0 (224) | OS Game Options field “Game Difficulty”; `andi.w #0xE0` at 0x40F62 selects the `monster_spawn_probability_table` row, so its principal verified gameplay effect is generator spawn probability |
| GSETTING_COINTOSTART_MASK | 0x0300 (768) | OS Game Options field “Coins to Start,” values 0–3 → 1–4; dynamically verified in MAME, with no normal game-code reader |
| GSETTING_TEXT_REDUCE | 0x0400 (1024) | 11 read sites, e.g. 0x4523C |
| GSETTING_SPEECH_DISABLE | 0x0800 (2048) | 0x4AD5A |
| GSETTING_RESET_FLAG | 0x1000 (4096) | OS Game Options action “Restore Factory Default Settings”; dynamically verified in MAME, with no normal game-code reader |
| GSETTING_ALLOW_CONTEST_FLAG | 0x2000 (8192) | sole reader 0x54EE2 in `secret_getname` |
| GSETTING_ATTRACT_SOUNDS | 0x4000 (16384) | sole reader 0x444E0 gating `sound_play(0x3B)` |
| GSETTING_SCORE_RESET_FLAG | 0x8000 (32768) | OS Game Options action “Reset High Score Tables”; dynamically verified in MAME, with no normal game-code reader |

### 3.11 Joystick Input Bits

**Confidence: Verified** for bits 0, 1 and 4–7. `btst #4/#5/#6/#7` on
`player_input_raw` (0x904920) plus `andi #0xF0` isolate the direction nibble,
and `joystick_nibble_to_direction` (0x580FC) decodes as **active-low**,
reproducing all eight compass directions plus 8 = none, which fixes RIGHT=4,
LEFT=5, DOWN=6, UP=7 exactly. Bits 0 and 1 are pinned by `input_debounce`
(0x40644), whose two `lsr.w #1` / `roxl.w` pairs feed `debounce_shift_magic`
and `debounce_shift_fire` in that order. **Unknown** for JOY_SPARE1_BIT (2) and
JOY_SPARE2_BIT (3): no consumer tests either bit.

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
| MAZENUM_SECRET_1 | 115 |
| MAZENUM_SECRET_2 | 116 |

`MAZENUM_FIRST`/`MAZENUM_LAST` bound the **rotation** (mazes 5–101), not the
set of playable mazes: mazes 0–4 are the fixed opening levels 1–5 of every
session. There is no `level = maze + 4` relationship — see
`06_maze_catalog.md` §3 for the selection algorithm.

`show_level_start_screen` selects maze 115 for challenge codes 0x50–0x56 and
maze 116 for codes 0x57–0x5D. Pointer entry 116 (`0x3FE48` after bank
normalization) is therefore live maze data, not merely an end sentinel.

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

### 3.15 Direction-table byte offsets

**Confidence: Verified.** These even values are `2 * direction`, used as byte
offsets into picture-word tables, not perspective nibbles encoded in a MOB
picture word. At 0x4AC1A the player direction is doubled; 0x4AC2A indexes the
idle picture-word table at 0x58A4A with the result. MAME observed the selected
words written to live player MOBs. The compass names follow the independently
verified active-low joystick direction map.

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

**Confidence: Verified** for all six bits: operands 0x01, 0x02, 0x04, 0x08,
0x10 and 0x20 all appear in bit-test or mask instructions across the fifty-one
references to `player_status` (0x9049A0).

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
| TRICK_TRANSPORT1 | 1 | Try Transportability (land beside Acid) |
| TRICK_TRANSPORT2 | 2 | Try Transportability (onto death) |
| TRICK_TRANSPORT3 | 3 | Try Transportability (into exit) |
| TRICK_TRANSPORT4 | 4 | Try Transportability (corner-transport through a secret wall) |
| TRICK_WATCHSHOOT1 | 5 | Watch What You Shoot (shoot two food items) |
| TRICK_WATCHSHOOT2 | 6 | Watch What You Shoot (shoot two secret walls) |
| TRICK_SAVESUPERSHOTS | 7 | Save Super Shots (exit with at least 11) |
| TRICK_NOUSEINVUL | 8 | Don't Use Invulnerability (collect it, then avoid monster contact/fire while protected) |
| TRICK_NOGETHIT | 9 | Don't Get Hit (literal exit predicate: progress low two bits are zero; dragon fire increments progress, while killing the dragon writes 2 unless it was already 1) |
| TRICK_PUSHWALL | 10 | Try Pushing a Wall (push a movable wall into an exit) |
| TRICK_NOFOOLED | 11 | Don't Be Fooled (avoid fake exits) |
| TRICK_NOGREEDY1 | 12 | Don't Be Greedy (no keys or potions) |
| TRICK_DIET | 13 | Go On a Diet (no food) |
| TRICK_NOGREEDY2 | 14 | Don't Be Greedy (no treasure) |
| TRICK_BEPUSHY | 15 | Be Pushy (enter the exit on a recursive collision-response move) |
| TRICK_IT | 16 | IT Could Be Nice (exit while IT) |
| TRICK_NOHURTFRIENDS | 17 | Don't Hurt Friends (hit no player with a shot, including the shooter after reflection, even when damage/stun is suppressed) |

After a player earns the secret challenge, `show_level_start_screen` (0x44DB4) replaces the maze trick ID with `0x50 + getrandom(14)`. These **challenge task codes** occupy 0x50–0x5D and are evaluated against `secret_tricks_flags`; they are distinct from the maze-header enum above. The optional qualifier-display records are at 0x573D4 (14 records × 8 bytes). Verified examples include 0x50 “AFTER COLLECTING 6 TREASURES,” 0x51/0x5D “AFTER COLLECTING ALL POTIONS,” 0x52/0x5B “AFTER SHOOTING 3 SECRET WALLS,” 0x56 “AFTER USING 5 TRANSPORTERS,” 0x5A “AFTER REMOVING ALL TREASURE,” and 0x5C “WHILE YOU ARE IT.” The `resolve_shot_hit` check at 0x4B826 is the 0x5A task hook: a player's supershot hitting ordinary treasure (object type 0x2E) increments that player's progress byte.

Ordinary tricks 1–4 and 10 do not use that progress array as a completion
counter. Their transport/movable-wall paths write `trick_player` directly at
the successful event; only later exit/status checks decide whether the winner
enters the challenge room.

### 3.18 Thief Modes

**Confidence: Verified** for THIEF_DEAD 0, THIEF_PURSUE 1, THIEF_ESCAPE 2,
THIEF_DODGE_BIT 3, THIEF_IS_MUGGER_BIT 7, THIEF_DODGE 0x08 and THIEF_IS_MUGGER
0x80 — observed as `btst #1/#3/#7` and masks 0x02, 0x03, 0x08, 0x80 and 0xFFF7
on `thief_mode` (0x904BA0). **Unknown** for THIEF_JUMPJUMP 4,
THIEF_ENTER_OK_MUGGER_BIT 5, THIEF_ENTER_OK 0x10 and THIEF_ENTER_OK_MUGGER
0x20: no instruction tests or sets them.

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
| 0x00–0x3F | Add one of this kind (from element list) (mask 0x3F); becomes the "last type" |
| 0x40–0x4F | Use HT1 (horizontal type 1) with N = 1..16 (low nibble + 1) |
| 0x50–0x5F | Use VT1 (vertical type 1) with N = 1..16 |
| 0x60–0x6F | Use HT2 (horizontal type 2) with N = 1..16 |
| 0x70–0x7F | Use VT2 (vertical type 2) with N = 1..16 |
| 0x80–0x9F | Repeat last type 1 to 32 times (low 5 bits + 1). Note: "last type" initializes to HT2 before any bytecode |
| 0xA0–0xAF | Repeat wall horizontally 1 to 16 times |
| 0xB0–0xBF | Repeat wall vertically 1 to 16 times |
| 0xC0–0xDF | Skip 1 to 32 times (**no wall added** — verified in decoder; earlier docs merged this with the next row) |
| 0xE0–0xFF | Skip 1 to 32 times then add one wall |

*Decoder verified (`maze_decode` 0x4C1BC): the 0x40–0x7F selector is `(byte>>4)&3` via the pointer table at 0x59B54 = [&HT1, &VT1, &HT2, &VT2]; run count always comes from the bytecode's low nibble; the H/V type byte contributes the §3.20 mode (top 2 bits) and element (low 6 bits). Vertical runs write toward decreasing slot numbers with stride −32 (−31 in the odd-angle case) and advance the main cursor by 1. The game stops at cursor 0x400; mazes 0–115 have a trailing zero file delimiter that is not consumed by the decoder, while maze 116 is the sole exception and has no delimiter. Confidence: Verified.*

### 3.20 Maze Horizontal and Vertical Types (encoded in HT1/HT2/VT1/VT2 header bytes)

| Range | Description |
|-------|-------------|
| 0x00–0x3F | Repeat this type |
| 0x40–0x7F | Skip N spaces then add this type (mask 0x40) |
| 0x80–0xBF | Add this type then skip N spaces (mask 0x80) |
| 0xC0–0xFF | Repeat wall N times then add this type (mask 0xC0) |

---

## 4. Data Structures

**Confidence: Verified** for field offsets, widths, and element counts from
all accessed views.

### 4.1 Maze Data Structure (in Slapstic ROM)

| Offset | Size | Name | Description |
|--------|------|------|-------------|
| 0x00 | 1 B | `secret_trick` | Secret trick ID (see Secret Tricks enum). 0 = none |
| 0x01 | 1 B | `level_flags_1` | Odd-angle and invisible-trap flags |
| 0x02 | 1 B | `level_flags_2` | Fast-monster flags |
| 0x03 | 1 B | `level_flags_3` | Random food count + cyclic/destructible walls + exit behavior |
| 0x04 | 1 B | `level_flags_4` | Shot behavior + traps + wrap + fake exit + offscreen |
| 0x05 | 1 B | `playfield_patterns` | Wall/floor pattern index (selects visual tile set) |
| 0x06 | 1 B | `playfield_colors` | Packed palette selectors: high nibble = main palette index written to 0x904B58; low nibble = special-palette variant written to 0x904B5A. |
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
| Word 1 | +0x080 | Top-right (one playfield column right) |
| Word 2 | +0x002 | Bottom-left (one playfield row down) |
| Word 3 | +0x082 | Bottom-right |

Playfield RAM is column-first (`doc/01_hardware.md` §7), so the +2-byte step
advances the row (down) and the +0x80-byte step advances the column (right).
See `doc/04_game_subsystems.md` §13.2 for the correction note.

### 4.5 High Score Entry (in EEPROM)

**Confidence: Verified.** Each class owns ten consecutive five-byte records
at OS configuration-image offset `0x1E + class * 50`. The three initials are packed
together into one 16-bit base-40 integer.

| Offset | Size | Description |
|--------|------|-------------|
| 0 | 3 B | Score (24-bit big-endian) |
| 3 | 2 B | Three initials as one big-endian base-40 value (space=0, A-Z=1-26, 0-9=27-36) |

`read_high_score_entry` expands a record into a separate seven-byte RAM view
at `0x904F44`: a 32-bit score followed by three ASCII bytes. That expanded
view is the input accepted by `write_high_score_entry`; it is not the EEPROM
layout.

### 4.6 `text_desc` Struct (for OS `display_text`)

```c
struct text_desc {              // 8 bytes for a leaf, 12 when chained
    uint8_t  a;                 // +0  see note: role swaps with display_mode
    uint8_t  b;                 // +1
    uint32_t string_ptr;        // +2  pointer to NUL-terminated ASCII string
    uint16_t flags;             // +6  high byte is the repeat/continuation count
    uint32_t next_ptr;          // +8  present only when the link is followed
};
```

Layout verified in `display_text` (0x2E3E). Bytes +0 and +1 are consumed by two
`move.b (a2)+`, then `movea.l (a2)+,a0` takes +2..+5 as the string pointer.
The continuation byte is read at **+6 without incrementing** (`move.b (a2),d1`),
`text_repeat_bias` (OS RAM 0x904F00) is added **to it**, one is subtracted, and
a result of zero or less ends the chain; otherwise `movea.l 0x2(a2),a2` loads
the link from **+8**. The link is therefore at +8, not immediately after the
count, and the count is not added to a scroll offset.

The §5.6 rows model +6..+7 as a 16-bit `flags` word: 0x0000 is a leaf and
0x0200 means "followed by a longword link", which is exactly repeat = 2.

The logical byte roles do not change with `display_mode`: +0 is column and +1
is row. In the normal path (0x2E6C) the cell address is
`(row × 64 + column) × 2`. The fullscreen/rotated path (0x2E4E) changes only
the memory transform to `(column × 64 + (0x29 − row)) × 2`.

---

## 5. ROM Data Tables Catalog

### 5.0 Boundary and indexed-base audit

**Confidence: Contradicted** for the former implication that every part of this
audit was already reproducible from checked-in artifacts. The top-level ROM
union is now mechanically verified by
[`generated/rom_regions.csv`](generated/rom_regions.csv): it covers every byte from 0x40000 through
0x5FFFF with no gap or overlap, verifies both solid-0xFF padding ranges, and
separates the final 0xE19E checksum word. The finer audit is now independently
generated as [`generated/rom_byte_coverage.csv`](generated/rom_byte_coverage.csv),
[`generated/rom_catalog_reconciliation.csv`](generated/rom_catalog_reconciliation.csv), and
[`generated/rom_flag_reconciliation.csv`](generated/rom_flag_reconciliation.csv), plus
[`generated/rom_range_overlaps.csv`](generated/rom_range_overlaps.csv).

**Confidence: Verified.** Fresh analysis of all 322 indexed entries plus 80
computed-dispatch destinations accounts for every byte of the two mixed
code/data regions as an instruction byte or named ROM range. All 322 parsed §5
rows have exact address/size matches in `gauntlet.r2`, while the reverse report
gives all 347 non-code ROM flags an exact §5 or game-header row. The overlap
report classifies 8 deliberate nested/alternate views and contains no
code/data collision. `generated/rom_byte_coverage_failures.csv` is empty.

**These reconciliation reports prove address and size agreement only.** Both
sides derive from the same catalog, so an exact match says nothing about
element width, index rule, or meaning; every semantic claim below rests on a
named consumer instruction instead. A semantic-use audit of all §5 rows
replaced the earlier row count of 329: false or duplicated rows were removed
and several extents, bases and value lists were corrected.

**Confidence: Verified** for the documented callable set: the generated
[`generated/ram_operands.csv`](generated/ram_operands.csv) independently analyzes all 322 unique
game-ROM entry addresses in `07_function_index.md` with symbol substitution
disabled. It extracts 318 distinct explicit `0x904000–0x905FFF` literals,
including address-register bases used for indexed access; every literal lands
in at least one named loader flag, and no function analysis fails. The empty
`generated/ram_operand_failures.csv` is retained so failures cannot disappear silently.

**Confidence: Verified** for ROM-encoded RAM operands. The independent
[`generated/ram_linear_reconciliation.csv`](generated/ram_linear_reconciliation.csv) decodes all
34 ranges already proven executable by the byte audit—93,722 instruction
bytes without a gap—and finds exactly the same 318 RAM literals as the
callable-anchored report. There are no linear-only or callable-only candidates,
and `generated/ram_linear_scan_failures.csv` is empty. This test cannot discover an
address synthesized entirely at runtime; those cases are documented from
their construction sites. Array sizes in the RAM catalog are total extents;
element widths and strides are stated separately.

For ROM data, every catalog start has a matching project flag, and adjacent structures with live consumers have explicit totals or exact end addresses. The remaining non-code bytes are accounted for as named padding/reserved ranges or as explicitly bounded runtime-dead residue. Overlapping flags are retained only where code demonstrably uses multiple views (including aggregate/demo-stream, animation, palette, exit-descriptor, and special-object views). A byte pattern alone was not used to create a table meaning.

### 5.1 Code Region Data Tables (`0x40000–0x5561F`)

| Address | Size | Content |
|---------|------|---------|
| 0x4009C | 9 B | `game_copyright_morse_signature` — bytes `AE D6 8C 17 FB 90 6A 33 80`; the first 69 MSB-first bits, interpreted as `0 = Morse dot` and `1 = Morse dash`, decode to `COPYRIGHT 1986 ATARI GAMES`. The final three zero bits are byte-alignment padding. The range has no runtime xref or consumer; its anti-copy/code-trap purpose is Strong inference, while the bytes and decoded text are Verified. See §1.3 of the game-ROM structure chapter. |
| 0x405C0 | 8 B | Forcefield color table (4 words, one per animation step) |
| 0x405C8 | 16 B | `palette_offset_by_floorpattern` — 16 one-byte playfield palette offsets indexed by **floorpattern**, exact range 0x405C8–0x405D7. Sole consumer `maze_setupnew` 0x44BBE–0x44BC6 reads `(a2)` where `a2 = ram.floorpattern` (0x904B5C, loaded at 0x44AD0); floorpattern is the **high** nibble of maze header byte 5 (`lsr.b #4` at 0x44B7C, stored 0x44B82) while `wallpattern` is the low nibble (0x44B8C). Only indices 0–8 are reachable: every one of the 117 shipped mazes has a header-byte-5 high nibble of 0–8. The former `_by_walltype` name was **Contradicted**. |
| 0x405D8 | 16 B | `palette_offset2_by_floorpattern` — second 16-byte palette-offset table, indexed by the same `(a2) = ram.floorpattern` value at 0x44BDA–0x44BE2; exact range 0x405D8–0x405E7 |
| 0x405E8 | 64 B | `vscroll_alpha_gradient` — 32 words from 0xF00F down to 0xF000 and then 0xF000 through 0xFF00. `game_vblank` folds the vertical-scroll phase, halves it to an even byte offset, and writes the selected word to alpha color RAM 0x91002E. |
| 0x40B58 | 64 B | `mob_collision_type_filter` — one byte for each object type after `mob_link`'s packed type byte is shifted right by two; the collision candidate helper returns the selected 0x00/0xFF eligibility value. |
| 0x40B98 | 24 B | `shot_collision_width` — 12 projectile-slot/character hitbox-width words. Player shots index by character; other shot slots index directly. |
| 0x40BB0 | 24 B | `shot_collision_height` — 12 parallel hitbox-height words, selected through the width-table base plus 0x18. |
| 0x40BC8 | 8 B | `dragon_shot_collision_width` — four character-indexed width words for the dragon-head collision adjustment path. |
| 0x40BD0 | 8 B | `dragon_shot_collision_height` — four parallel height words selected at width base +8. |
| 0x40BD8 | 160 B | `shot_collision_probe_offsets` — eight direction records × five signed horizontal/vertical word pairs. `shot_mob_collision` probes the five adjusted candidate positions in order. |
| 0x40D78 | 18 B | `monster_kill_score_by_multiplier` — nine score words `{0,10,20,...,80}` indexed by the player's current bonus multiplier after a normal monster kill. |
| 0x40D8A | 40 B | `monster_shoot_axis_thresholds` — ten pairs of direction/monster-class threshold words used by `monster_find_and_shoot` when comparing the two player-axis deltas. **Confidence: Strong inference** for the record labels; range and indexed accesses are verified. |
| 0x40DB2 | 40 B | `monster_anim_idle_ptrs` — ten longword animation pointers in monster-index order; shared/null entries encode shared banks or no separate bank. |
| 0x40DDA | 40 B | `monster_anim_moving_ptrs` — ten parallel moving-animation pointers `{NULL, 0x59026, 0x59126, NULL, 0x59226, 0x59026, 0x592B6, 0x593B6, NULL, NULL}`; see §7.2 for the per-type mapping. |
| 0x40E1E | 40 B | `monster_oddangle_table` — ten four-byte per-type direction-adjustment records consumed by the monster movement path. |
| 0x40E66 | 4 B | `monster_spawn_probability_bonus_bytes` — live character-indexed **byte** table `{3,0,4,0}` = Warrior 3, Valkyrie 0, Wizard 4, Elf 0, not two words and not residue. In `player_start_inner`, only the join that makes `level_players_active == 1` doubles the player index, loads `player_character[player_index]` at 0x48EEC, and uses that class 0–3 at 0x48EF6; every later join clears the bonus at 0x48F00. MAME ordinary coin/select/join runs reached all four indices and a two-player run confirmed the later-join clear. `maze_addrandompickups` at 0x44110 uses the same table while adjusting solo Warrior/Wizard pickups. The next bytes `48 E7 3F 3E` are a `movem.l` prologue, so the table is exactly 0x40E66–0x40E69. **Confidence: Verified.** |
| 0x41BD0 | 32 B | `player_character_collision_block_matrix` — 4×4 word matrix indexed by moving character ×8 plus encountered character ×2. A nonzero cell defers movement in the corresponding directional player-collision path. |
| 0x40E02 | 28 B | `monster_level_flag_overrides` — seven four-byte padded records. Only byte 0 of each record is read; bytes 1–3 are zero. The leading bytes are `{0x80,0xC0,0,0,0xA0,0xA0,0x80}`. `monsters_everything` walks the seven bits of `(level_flags_1 & 0x73)` and, for each set bit, copies the corresponding leading byte into the high byte of that class's four-byte stack control value. The default control values retain low word 0x0080 or 0x0100 according to `level_flags_2`; this is a per-class control override table, not a seven-longword speed table. |
| 0x40E46 | 32 B | `monster_spawn_probability_table` — generator **spawn probability out of 32**: 8 rows (EEPROM settings 0x904A24 **bits 5–7**, labelled “Game Difficulty” by the operator UI) × 4 columns (players−1). Index = `((settings & 0xE0) >> 3) + players − 1`. Values: v0 = 4,11,15,18 up to v7 = 18,25,29,32. Added to `int8(0x90405F)` per-level bonus. Capped at `level_number * 2` (except level 1). If `frame_overflow` (0x904916) non-zero: forced to 0. `handle_generate` compares the result against `getrandom(32)` (0x49300–0x4930E) and spawns only when the table value wins; the former `monster_count_table` name and "max monsters to process per frame" reading were **Contradicted**. See `04_game_subsystems.md` §3.4. |
| 0x4A4FA | 64 B | `dizzy_direction_remap` — 4 rows × 16 bytes, ending immediately before `main_move_players` at 0x4A53A. While `dizzy_timer` remains nonzero after its decrement, normal play indexes it with `(frame_counter & 0x30) + ((raw_input >> 4) & 0x0F)` and replaces only the active-low direction nibble. |
| 0x58070 | 32 B | `invisibility_flash_masks` — sixteen phase masks used by the player invisibility flicker path. |
| 0x580A8 | 16 B | `player_speed_normal` — 8 words indexed by character × normal/powered state |
| 0x580B8 | 16 B | `player_anim_rate` — 8 words parallel to `player_speed_normal`; mask/divider used to add the temporary 0x80 speed boost |
| 0x580C8 | 16 B | `lobber_lead_distance` — eight per-character target-lead scalars (four normal, four powered) read only by the lobber aim path at 0x419A6; see the Player Movement / Physics table above. Not collision dimensions. |
| 0x580D8 | 18 B | `player_delta_x` — **nine** signed horizontal movement-delta words `{0,+2,+2,+2,0,−2,−2,−2,0}` for directions 0–8, exact range 0x580D8–0x580E9. Element 8 is the no-direction case. |
| 0x580EA | 18 B | `player_delta_y` — nine signed vertical movement-delta words `{+2,+2,0,−2,−2,−2,0,+2,0}` for directions 0–8, exact range 0x580EA–0x580FB. The base is proven by `monster_find_and_shoot` 0x419B0, `muls.w -0x12(a0,d6.w),d7` with `a0 = 0x580FC`, i.e. 0x580FC−0x12 = 0x580EA; the old 0x580E8 start was off by one element. |
| 0x580FC | 32 B | `joystick_nibble_to_direction` — sixteen words mapping the **active-low** joystick direction nibble to direction 0–7, with 8 meaning no valid direction: `{8,8,8,8,8,7,1,0,8,5,3,4,8,6,2,8}`. Because 8 is produced for eight of the sixteen nibbles, the delta tables it feeds must have nine entries. |
| 0x5850E | 125 B | `attract_display_run_ctrl` — control stream used with `attract_display_tile_stream` (0x5CB28). Each byte supplies palette bits in 7–5 and a run length in bits 4–0; function 0x4438E consumes a new byte when the preceding run expires. The 125 low-five-bit run lengths sum exactly to 1000 output tiles. |
| 0x5858B | 1 B | `pad_5858b` — zero alignment byte between the attract-display control stream and the master object tables. |

### 5.2 Master Object Parameter Tables (`0x5858C–0x5868C`)

Four parallel 64-entry tables (one entry per maze object type, indexed 0–63). Their element widths differ; together they occupy the contiguous 0x5858C–0x5870B range:

| Table Address | Element / Total Size | Name | Content |
|---------------|----------------------|------|---------|
| 0x5858C | word / 128 B | `mazeobj_hpos_correction_tbl` | Per-type centering/correction word subtracted from the packed horizontal position. Native position units (0x80 per pixel), so its only nonzero entry, 512, is 4 px — half the overhang of a 24 px sprite in a 16 px cell |
| 0x5860C | byte / 64 B | `mazeobj_vpos_offset_tbl` | Low-byte vertical-position addend/size encoding |
| 0x5864C | byte / 64 B | `mazeobj_hsize_tier_tbl` | Low nibble ORed into the packed horizontal-position word. Per `01_hardware.md` §8.2 that field is the **MOB palette number** (bits 3–0); horizontal size lives in the vertical-position word. For monsters the same nibble is also the three-step health/tier value used by combat, so a monster's remaining health *is* its palette. Verified bases: ghost/grunt/aux grunt 4, generators 5, demon 8, lobber/sorcerer/Super Sorcerer 11, IT 8, acid 1, Death 0; live range is `[base−2, base]`. These match the per-monster stamp palettes in `python-gex`. |
| 0x5868C | word / 128 B | `mazeobj_base_picture_tbl` | Base picture word for each object type; ends at 0x5870B |

### 5.2.1 Computed dispatch tables

All game-ROM computed JMPs use signed 16-bit PC-relative displacements. The JMP base is the address immediately after the JMP instruction; several loads deliberately use a backward-biased PC base so an unnormalized object type indexes the table directly.

| Table | Entries | Index and base rule |
|-------|---------|---------------------|
| 0x45C46 `door_open_direction_jumptbl` | 4 × 2 B | `main_open_doors`: direction 0–3, doubled; displacement and JMP base 0x45C46 |
| 0x49620 `monster_playerhit_jumptbl` | 10 × 2 B | **Contradicted and corrected:** target/monster class 0x12–0x1B is doubled without subtraction; the backward-biased load base 0x495FC maps it to the actual table at 0x49620–0x49633, also the JMP displacement base. The former 28-entry/0–0x1B description included live instructions before the table. |
| 0x4B338 `resolve_shot_hit_jumptbl` | 62 × 2 B | Object type **1–0x3E**, doubled **without subtraction**; guards `cmpi.w #1`/`blt` and `cmpi.w #0x3E`/`bgt` at 0x4B31E–0x4B32A. The load uses the backward-biased base **0x4B336** (`move.w 0x4B336(pc,d0.w),d0` at 0x4B330); the JMP base is 0x4B338. Type 0x2E resolves to 0x4B80E, whose body re-tests `cmpi.w #0x2E,-0x2(a6)` at 0x4B830 |
| 0x4FE08 `richest_player_tie_jumptbl` | 8 × 2 B | Eight tie/eligibility states, doubled; displacement and JMP base 0x4FE08 |
| 0x51200 `player_tile_lowtype_jumptbl` | 8 × 2 B | Object type 0x0A–0x11 is doubled without subtraction; load base is biased to 0x511EC, making the accessed table 0x51200–0x5120F; JMP base 0x51200 |
| 0x5122A `player_tile_object_jumptbl` | 17 × 2 B | Object type 0x2E–0x3E, doubled without subtraction; load base 0x511CE biases accesses to 0x5122A–0x5124B; JMP base 0x5122A |
| 0x52210 `mob_collision_object_jumptbl` | 53 × 2 B | Object type **0x0A–0x3E**, doubled without subtraction; guards `cmpi.w #0x0A`/`blt` and `cmpi.w #0x3E`/`bgt` at 0x521F6–0x52202. Load base 0x521FC biases accesses to **0x52210–0x52279**; JMP base 0x52210. Structural proof of the end: the entry for type 0x0F targets 0x5227A, the first byte after the last entry |
| 0x538FE `shot_reflect_center_jumptbl` | 5 × 2 B | Signed delta −2…2 indexes around a centered load base 0x53902; JMP base 0x538FE |
| 0x53924 `shot_reflect_neg42_jumptbl` | 5 × 2 B | Delta −0x42…−0x3E is normalized by subtracting −0x42; JMP base 0x53924 |
| 0x53948 `shot_reflect_neg22_jumptbl` | 5 × 2 B | Delta −0x22…−0x1E is not normalized; backward-biased load base 0x5398C maps it to 0x53948–0x53951; JMP base 0x53948 |
| 0x5396A `shot_reflect_pos1e_jumptbl` | 5 × 2 B | Delta 0x1E…0x22 is not normalized; backward-biased load base 0x5392E maps it to 0x5396A–0x53973; JMP base 0x5396A |
| 0x53992 `shot_reflect_pos3e_jumptbl` | 5 × 2 B | Delta 0x3E…0x42 is normalized by subtracting 0x3E; JMP base 0x53992 |

### 5.3 Animation Tables (`0x58090–0x58A90`)

| Address | Size | Content |
|---------|------|---------|
| 0x58090 | 8 B | `fighting_anim_end` — four words, one per player slot, used as the current fighting-animation termination threshold; 0x58098 begins the unrelated demo pointer table |
| 0x58098 | 4 × 4B | Demo initial pointer table — ROM pointers to per-player demo streams |
| 0x5811C | 32 B | `fight_direction_map` — 16 words indexed by the 4-bit fight-input nibble |
| 0x5813C | 32 B | `forcefield_damage_table` — **8 longwords** of forcefield contact damage, index `character + 4 × armor-power`, ending at 0x5815B. Sole consumer `main_move_players` 0x4AA96: `lea 0x5813C,a0; move.l (a0,d1.w),d2`, subtracted from the longword `player_health` slot at 0x4AAA8. It is reached only after `tst.w ram.forcefield_color` (0x4AA42), a zero `acid_timer` test (0x4AA56) and a nonzero return from `check_forcefield_collision` (0x4AA68), so it prices **forcefield contact**, not the per-frame time drain, which is charged flat elsewhere. The index is built at 0x4AA7C–0x4AA94: `btst.b #1,0x1(a0,d0.w)` on `player_powers` (POWER_ARMOR_BIT) selects the +4 half, then `player_character` is added and the sum scaled ×4. Values `{2,2,6,4}` unarmored and `{1,1,5,3}` armored. The former `health_drain_table` name and 16-word element size were **Contradicted**. |
| 0x5874A | 256 B | `anim_table_shooting` — shooting animation frames indexed by (counter/4 & 3, direction, char_type × 64) |
| 0x5870C | 62 B | `dead_picture_word_block` — 31 picture-code words between the 64-entry object base-picture table and the shooting animation table. The object table's verified index is limited to 0–63 and no encoded pointer/xref reaches 0x5870C, so these shipped words are runtime-dead residue. |
| 0x5884A | 512 B | `anim_table_fighting` — fighting animation frames indexed by (counter/2 & 7, direction, char_type × 128) |
| 0x58A4A | 64 B | `anim_table_idle` — idle animation frames indexed by (direction, char_type × 8) |
| 0x58A8A | 256 B | `anim_table_walking` — walking animation frames indexed by (counter/4 & 3, direction, char_type × 32) |
| 0x58B8A | 128 B | `projectile_picture_table` — 64 picture words shared by player shots, monster shots, reflected shots, and dragon fire. Callers combine direction, projectile/character class, and animation phase into the word index. |
| 0x58C0A | 128 B | `anim_tiles_sorcerer` — 64-word Sorcerer/Super-Sorcerer direction/phase animation bank. |
| 0x58C8A | 16 B | `thief_escape_anim` — 8 picture words indexed by `(thief_anim_counter−28)/4 & 7` |
| 0x58C9A | 128 B | `thief_walk_anim` — normal thief, 8 directions × 8 frames (64 words); exact range 0x58C9A–0x58D19 |
| 0x58D1A | 18 B | `thief_idle_by_direction` — normal thief, **nine** picture words for directions 0–8, exact range 0x58D1A–0x58D2B. `main_thief_anim` 0x4EDCA–0x4EDD4 indexes it with `ram.thief_direction × 2` and applies no upper guard, and `calc_direction` (0x510FC) returns 8 when both deltas are zero (0x5119C–0x511A4). Element 8 (0x0DF3) duplicates element 4, so the no-movement case reuses the DOWN picture. |
| 0x58D2C | 64 B | `thief_walk_anim_compact` — normal thief alternate cycle, 8 directions × 4 frames (32 words). The formerly named address 0x58D4C is element 16, used as the initial spawn picture, not a table start. |
| 0x58D6C | 128 B | `mugger_walk_anim` — super-thief/mugger, 8 directions × 8 frames (64 words); exact range 0x58D6C–0x58DEB |
| 0x58DEC | 18 B | `mugger_idle_by_direction` — mugger, nine picture words for directions 0–8, exact range 0x58DEC–0x58DFD, indexed identically at 0x4EDE6. Element 8 (0x2409) again duplicates element 4. |
| 0x58DFE | 64 B | `mugger_walk_anim_compact` — mugger alternate cycle, 8 directions × 4 frames (32 words). Address 0x58E1E is interior element 16 used as the mugger's initial spawn picture. |
| 0x58E3E | 160 B | `special_projectile_picture_table` — 80 picture words used by special player-shot and dragon-fire animation paths; the index combines facing/direction and phase. Exact range 0x58E3E–0x58EDD. |
| 0x58EDE | 66 B | `monster_projectile_picture_table` — 33 picture words used by ordinary monster/shot rendering, exact range 0x58EDE–0x58F1F. |
| 0x58F20 | 6 B | `invulnerable_food_pictures` — three picture words selected by `getrandom(3)` for maze object type 0x32; ends immediately before `anim_tiles_ghost` at 0x58F26 |
| 0x58F26 | 128 B | `anim_tiles_ghost` — 64-word Ghost direction/phase animation bank. |
| 0x58FA6 | 128 B | `anim_tiles_grunt` — 64-word Grunt/Auxiliary-Grunt animation bank. |
| 0x59026 | 128 B | `anim_tiles_grunt_moving` — separate moving bank shared by Grunt and Auxiliary Grunt. |
| 0x590A6 | 128 B | `anim_tiles_demon` — 64-word Demon animation bank. |
| 0x59126 | 128 B | `anim_tiles_demon_moving` — separate Demon moving bank. |
| 0x591A6 | 128 B | `anim_tiles_lobber` — 64-word Lobber animation bank. |
| 0x59226 | 128 B | `anim_tiles_sorcerer_moving` — separate Sorcerer moving bank. |
| 0x592A6 | 128 B | `anim_tiles_death` — 64-word Death animation bank. |
| 0x592B6 | 128 B | `anim_tiles_death_moving_view` — biased overlapping 64-word moving view beginning 16 bytes into `anim_tiles_death`. |
| 0x59336 | 128 B | `anim_tiles_acid` — 64-word Acid animation bank. |
| 0x593B6 | 128 B | `anim_tiles_acid_moving` — separate Acid moving bank. |
| 0x59436 | 128 B | `anim_tiles_it` — 64-word IT animation bank. |
| 0x594B6 | 128 B | `anim_tiles_it_special` — IT chase/special-state animation bank. |
| 0x59536 | 128 B | `anim_tiles_monster_special_attack` — non-Lobber special-attack direction/phase bank. |
| 0x595B6 | 128 B | `anim_tiles_lobber_throw` — Lobber throwing-animation bank. |
| 0x59636 | 128 B | `anim_tiles_monster_special_state` — shared special-state direction/phase bank. |

### 5.4 Scoring / Speech Tables

| Address | Size | Content |
|---------|------|---------|
| 0x54BD6 | 10 B | `dragon_head_hitbox_offsets` — five padded words `{0x0400,0,0x0400,0,0x0400}`. `dragon_shot_hitbox_adjust` indexes overlapping H/V pairs with `(dragon_facing & 6)`, giving the cardinal head displacement without a wrap branch. |
| 0x54CA6 | 32 B | `secret_code_alphabet` — exact 5-bit symbol alphabet `0123456789ABCDEFGHJKMNPQRSTUWXYZ` (I, L, O, and V omitted), used for all six characters of the displayed secret code. |
| 0x54CC6 | 512 B | `secret_code_crc16_table` — 256 big-endian words, the standard CRC-CCITT/0x1021 lookup table. `secret_code_build` uses it to hash the entered name, skipping spaces; exact range 0x54CC6–0x54EC5, immediately before `secret_getname`. |
| 0x5318C | 442 B | `game_options_descriptor_stream` — game-specific operator-options stream passed by `game_options_display` (0x5317C) to OS API 0x248. It contains tagged prompts and choices for resetting scores/defaults, attract sound, difficulty, health per coin, coins to start, secret codes, speech, and reduced text; exact range 0x5318C–0x53345. |
| 0x57002 | 4 × 4B | Per-player character announcement speech IDs (ROM pointer table) |
| 0x57012 | 13 × 4B | Random maze flags table (selected by `get_random_maze_flags` via getrandom(0xD)) |
| 0x57046 | 8 B | `slapstic_bitwise_addr_a` — four word offsets indexed by half the current slapstic command offset |
| 0x5704E | 8 B | `slapstic_bitwise_addr_b` — four parallel word offsets for the second access in `slapstic_cmd_bitwise` |
| 0x57056 | 28 B | `challenge_target_object_types` — 14 object-type words indexed by `trick_tasknum - 0x50`: `{0x2C,0x2A,0x2A,0x29,0x2D,0x28,0x2B,0x2D,0x28,0x2C,0x29,0x2A,0x2A,0x2B}`. Secret-challenge setup uses the selected type while scanning eligible maze objects. |
| 0x57072 | 66 B | `character_select_instruction_chain` — three formatted-text nodes plus inline NUL strings “CHARACTER”, “TO SELECT”, and “USE JOYSTICK”, exact range 0x57072–0x570B3. Nodes use `{row,column,string_ptr,flags[,previous_ptr]}`; the latter two have flag 0x0200 and link backward to form the chain. |
| 0x57340 | 16 B | `character_hud_text_ptrs` — four longword pointers to character HUD/name strings |
| 0x57350 | 8 B | `player_text_palette_words` — four player-indexed alpha/text attribute words `{0xD000,0xD400,0xD800,0xDC00}`. Score, health, entry animation, dialog, and information-panel paths pass the selected word as the player's text palette/attribute. |
| 0x57358 | 8 B | `treasure_room_duration` — four words `{0x04B0,0x05A0,0x05DC,0x0618}` = 1200/1440/1500/1560 frames (20/24/25/26 s at 60 Hz), indexed by `player_activecount` (0x4D900) minus one. `show_level_start_screen` loads the selected word, adds 1, and stores it in `treasure_timer` (0x9049E8) at 0x44F1A–0x44F32, so a treasure room lasts longer with more players. The base literal in that path is 0x57358, not the 0x57350 text-palette base above; this block was previously and incorrectly catalogued as `dead_position_word_block`. |
| 0x57360 | 28 B | `challenge_timer_base` — 14 words indexed by challenge code 0x50–0x5D; base duration in frames |
| 0x5737C | 28 B | `challenge_timer_random_minutes` — 14 word random-range values; `getrandom(value) × 60` is added to the corresponding base duration |
| 0x576E2 | 176 B | `shot_velocity_x` — 88 signed words: four player-character rows, one ordinary-monster row, four Shot-Speed-powered character rows, tier-2 monster shots, and max-tier shots. Player index = `character*8 + direction`, plus 0x28 entries when `player_powers` bit 3 is set; monster offsets are 0x20/0x48/0x50. Ends at 0x57791. |
| 0x57792 | 176 B | `shot_velocity_y` — 88 signed words parallel to `shot_velocity_x`, with the same Shot-Speed bit-3 selector; ends at 0x57841. |
| 0x57862 | 64 B | `health_per_coin_table` — 32 words indexed by `GSETTING_COINHEALTH` bits 0–4 (index 0–31): 100, 125, 150, 175, 200, 225, 250, then 300–1000 in 50s, then 1100–2000 in 100s. The word at 0x578A0 is element 31 rather than a separate constant |
| 0x57842 | 16 B | `player_power_palette_handler_ptrs` — four absolute game-code pointers selected by character and written into the RAM-resident power-palette JMP stub during player setup. |
| 0x57852 | 16 B | `player_hurt_palette_handler_ptrs` — four character-selected handler pointers written into the parallel hurt-palette JMP stub. |
| 0x578A2 | 16 B | `spawn_candidate_column_delta` — eight signed word column deltas `{−1,+1,0,0,+1,+1,−1,−1}` used by player join, tile-occupancy, pickup, and supersorcerer placement searches. |
| 0x578B2 | 16 B | `spawn_candidate_row_delta` — eight packed-maze row deltas `{0,0,−0x20,+0x20,−0x20,+0x20,+0x20,−0x20}` parallel to the column table. |
| 0x578C2 | 24 B | `shot_counter_reload` — 12 projectile-channel words `{0xF,1,1,0,1,1,1,1,0x20,0x20,0x20,0x20}`. `main_handle_shots` covers exactly channels 0–11: player channels 0–3 select the first four entries by character when advancing their pictures; monster-shot channels 4–7 use the next four; lobber channels 8–11 use the final four 0x20 lifetime values. `monster_create_shot` and `dragon_fire_setup`'s long-range branch (0x548A4) copy the corresponding channel entry into `shot_anim_lifetime_counter`; the dragon's close-range breath bypasses the table and writes a literal 0x13 (0x54814). Exact range 0x578C2–0x578D9; 0x578D2 is an interior element, not a separate table. |
| 0x578DA | 16 B | `random_item_group_ptrs` — four longword pointers, indexed by character/player class |
| 0x578EA | 8 B | `random_item_group_counts` — four word counts parallel to `random_item_group_ptrs`; selects the random entry within each pointed-to group |
| 0x578F2 | 24 B | `score_spin_picture_cycle` — 12 picture words forming a symmetric 0x1DCF…0x1E00…0x1DCF effect cycle. |
| 0x5790A | 16 B | `start_game_player_count_sounds` — four longword sound commands `{0x40,0x3F,0x3E,0x3D}` indexed by active-player count minus one. |
| 0x5791A | 24 B | `random_item_group_values` — payload for the four groups referenced at 0x578DA: lengths 2,1,1,2 and longword values `{0xBB,0x87}`, `{0xB5}`, `{0xBA}`, `{0xB9,0xBC}`. |
| 0x57932 | 16 B | `player_transition_sound_ids` — four player-indexed longword sound IDs 0x14–0x17. |
| 0x57942 | 16 B | `heartbeat_sound_table` — four longword heartbeat sound IDs, indexed by player number |
| 0x57952 | 16 B | `player_coin_sound_ids` — four player-indexed longword coin/join sound IDs 9–12. |
| 0x57962 | 12 B | `early_level_speech_choices` — three longword speech IDs `{0x55,0x56,0x57}` selected randomly by the early/special-level start path. |
| 0x5796E | 12 B | `later_level_speech_choices` — three longword speech IDs `{0x55,0x58,0x5E}` selected by the later-level path. |
| 0x5797A | 16 B | `character_lowhealth_speech` — four longword speech IDs `{0x5A,0x5B,0x5D,0x5C}`. **Contradicted and corrected:** the index is not the character. `player_lowhealth` (0x487CA) selects entries 0–2 with `getrandom(3)` at 0x48856, and reaches entry 3 ("ALL YOUR POWERS WILL BE LOST!") only through the branch at 0x48812–0x48850, which requires a nonzero masked `player_powers`, `getrandom(8) > 3`, and more than one power bit set. The chosen phrase is preceded by a separate `sound_speech_play` of `speech_charname_tbl[character + player × 4]` (0x596F6), so the spoken sentence is two commands. |
| 0x5798A | 36 B | `generator_spawn_object_type` — 18 words: object types 0x12–0x17, each repeated for its three generator/tier variants. |
| 0x579AE | 36 B | `generator_spawn_vpos_correction` — 18 signed words parallel to the object-type table, repeating `{2,1,0}` for each generated monster class. |
| 0x579D2 | 16 B | `death_potion_score_table` — eight score words `{1000,4000,2000,6000,1000,8000,1000,2000}` indexed by `death_hits & 7`; `death_potion_score` returns the selected word. |
| 0x579E2 | 16 B | `death_potion_popup_type_table` — eight parallel `playfield_showscore` popup-type words `{2,5,3,7,2,9,2,3}` indexed by `death_hits & 7`. The former “random table” description was contradicted. |
| 0x579F2 | 60 B | `score_popup_picture_table` — 15 longword records indexed by `playfield_showscore`'s score type; exact range 0x579F2–0x57A2D. The record stride is 4 (`asl.w #2,d0` at 0x494EA) but only the **low word at record+2** is read: `move.w 0x2(a1,d0.w),(a0,d1.w)` at 0x494F2 writes it straight into a MOB picture word, and the high word is never read. |
| 0x57A2E | 128 B | `monster_contact_damage_table` — 64 words arranged as normal and powered-player halves. `monster_playerhit` indexes by contact class and character, adding 0x20 entries for the powered state. |
| 0x57AAE | 132 B | `character_hurt_sound_banks` — four contiguous longword sound-ID banks for Warrior, Valkyrie, Wizard, and Elf with lengths 4,10,10,9. |
| 0x57B32 | 10 B | `hurt_speech_cooldown_base` — five words indexed by `level_players_active` 0–4: `{0,8,12,14,20}`. `player_hurt_speech_timer` 0x49AD0–0x49ADE does `move.w ram.level_players_active,d0; add.w d0,d0; movea.l #0x57B32,a0; move.w (a0,d0.w),d0`, and a `getrandom(8)` component (0x49AC4–0x49AC8) is added. The former list `{8,12,14,20,5}` was shifted one element and its final value was the high word of `character_hurt_sound_ptrs[0]` at 0x57B3C. |
| 0x57B3C | 16 B | `character_hurt_sound_ptrs` — four longword pointers into the character hurt-sound banks. |
| 0x57B4C | 4 B | `character_hurt_sound_counts` — byte counts `{4,10,10,9}` parallel to the pointer table. |
| 0x57B50 | 12 × 2B | `generator_cell_dx` — signed maze-column deltas for directions 0–7, followed by a duplicate of entries 0–3. `handle_generate` starts at a random index 0–3 and scans eight consecutive entries, so this four-word tail implements wraparound without an AND/modulo operation. |
| 0x57B68 | 12 × 2B | `generator_cell_dy` — signed packed-maze row deltas (0, ±0x20) parallel to `generator_cell_dx`, with the same duplicated 0–3 tail. |
| 0x57B80 | 12 × 2B | `generator_spawn_direction` — direction/animation codes `{0,2,4,6,1,3,5,7}`, again followed by duplicated entries `{0,2,4,6}` for the unmodded eight-cell scan. |
| 0x57B98 | 8 × 2B | `monster_shot_spawn_h_offset` — eight direction-indexed horizontal muzzle offsets for ordinary monster shots. Every entry is a multiple of 0x100, i.e. a whole ROM pixel (0x80), so adding one to a `& 0xFF80`-masked shooter word cannot disturb the low field. |
| 0x57BA8 | 8 × 2B | `monster_shot_spawn_v_offset` — matching vertical muzzle offsets, on the ROM's upward V axis. |
| 0x57BB8 | 8 × 2B | `lobber_shot_spawn_h_offset` — horizontal launch offsets for lobber projectiles, same whole-pixel property. `monster_create_shot` adds the word to the masked shooter position; `monster_find_and_shoot` separately reads the signed **high byte** (0x419EE) when deriving the lobber's lead velocity. |
| 0x57BC8 | 8 × 2B | `lobber_shot_spawn_v_offset` — matching vertical launch offsets. Ends at 0x57BD7, immediately before `unreferenced_tile_word_block`. |
| 0x596B6 | 12 B | `shot_damage_base_tbl` — three four-character rows `{2,1,1,1}`, `{1,1,1,1}`, `{2,2,2,2}`. Player shots select character 0–3 or character+8 with Shot Power bit 4; the middle row is reached by monster-channel class IDs. |
| 0x596C2 | 12 B | `shot_damage_rand_tbl` — parallel random flags, nonzero only for base Wizard class 2 and Shot-Power Warrior class 8; each adds `getrandom(2)`. |
| 0x596CE | 40 B | `monstshot_damage_tbl` — ten four-character incoming-damage rows. Index starts with victim character, adds 4 for Armor bit 1, then adds the projectile tier/channel class offset 0, 8, 0x10, 0x18, or 0x20. |
| 0x596F6 | 16 × 4 B | `speech_charname_tbl` — 4 characters × 4 player colors, longword sound IDs 0xBD–0xCC (“RED WARRIOR” through “GREEN ELF”); exact range 0x596F6–0x59735 |
| 0x56FA8 | 88 B | `pad_56fa8` — solid 0xFF alignment/padding between the runtime-dead duplicated `slapstic_verify` suffix and the first table at 0x57002; exact range 0x56FA8–0x56FFF. |
| 0x57000 | 2 B | `residue_word_57000` — the word 0xDD09. It is not 0xFF, so it is not part of the pad above, and no consumer references it. **Confidence: Verified** for the bytes and for the absence of a consumer; **Unknown** for purpose. |

### 5.5 Tile / Playfield Data (`0x5BA70–0x5FFFF`)

| Address | Size | Content |
|---------|------|---------|
| 0x5AC20 | 14 B | `logo_brightness_seq` |
| 0x5AC5E | 192 B | `fixed_playfield_palette_bank` |
| 0x5AC2E | 32 B | `logo_motion_program_full` |
| 0x5AC4E | 16 B | `logo_motion_program_short` |
| 0x5BA5C | 12 B | `wall_crumble_stage_ptrs` — three longword pointers `{0x5D3D0,0x5D3D8,0x5D3E0}`, one per destructible-wall stage, i.e. the three 8-byte descriptors of `wall_desc_destructible`. `wall_crumble` 0x5310E–0x5311A does `asl.w #2,d0; movea.l #0x5BA5C,a0; move.l (a0,d0.w),-(a7)` and passes the result to `pf_stamp_update`. This table was previously hidden inside the over-claimed 1024-byte `exit_desc_by_floorpattern` extent; correcting that extent to 576 B exposed it. |
| 0x5BA68 | 2 B | `logo_outer_timer_init` |
| 0x5BA6A | 2 B | `logo_inner_timer_init` |
| 0x5BA6C | 2 B | `logo_bright_min` |
| 0x5BA6E | 2 B | `logo_bright_max` |
| 0x5BA70 | 64 B | `forcefield_gfx_ptrs` — one 16-longword pointer table (not two 8-entry tables) into forcefield/floor tile descriptors at 0x5CAB0–0x5CB20; indexed by the 4-bit forcefield graphic state |
| 0x5BAB0 | 16 B | `shot_reflect_hdelta` — 8 signed horizontal-position correction words indexed by reflected shot direction |
| 0x5BAC0 | 16 B | `shot_reflect_vdelta` — 8 signed vertical-position correction words parallel to `shot_reflect_hdelta` |
| 0x5BAD0 | 16 B | `shot_reflect_sound_tbl` — four longword sound IDs indexed by player character: 0x45, 0x47, 0x46, 0x48 |
| 0x5BAE0 | 256 B | `floor_desc_base` — 32 contiguous 8-byte floor descriptors, exact range 0x5BAE0–0x5BBDF. `pf_floor_draw` selects the connectivity variant here and offsets each tile code by `floorpattern × 0x30`; it does not select a separate floor block. Wall data begins independently at 0x5BBE0. |
| 0x5BBE0 | 3264 B | `wall_desc_blocks` — six normal wall-pattern blocks × 68 descriptors × 8 bytes, exact range 0x5BBE0–0x5C89F. Each descriptor contains four picture words written to the tile's 2×2 playfield cells. `wall_pattern_offsets` contains descriptor-index bases `{0x000,0x044,...,0x154}`; `pf_wall_draw` adds the connectivity variant and multiplies by eight. |
| 0x5C8A0 | 8 B | `floor_type10_desc` — single four-word 2×2 descriptor selected directly for tile type 0x10. The former 520-byte size incorrectly swallowed the unrelated sequential block that follows. |
| 0x5C8A8 | 8 B | `floor_type11_desc` — single four-word 2×2 descriptor selected directly for tile type 0x11. |
| 0x5C8B0 | 504 B | `exit_tile_descs` — pool of **63 eight-byte 2×2 tile descriptors** (252 consecutive words 0x03A2–0x049D), exact range 0x5C8B0–0x5CAA7. Every one of the 144 longwords in `exit_desc_by_floorpattern` records 0–8 points into this range, and a whole-image dword scan finds exactly 63 distinct 8-byte-aligned targets here — one per descriptor. The former runtime-dead classification was **Contradicted**; the descriptors are consumed through the exit-descriptor pointer records. |
| 0x5CAA8 | 128 B | `floor_type3e_descs` — 16 four-word/8-byte 2×2 descriptors selected for tile type 0x3E. Forcefield graphics pointers also target overlapping descriptors from 0x5CAB0 through 0x5CB20. |
| 0x5CB28 | 2000 B | `attract_display_tile_stream` — exactly 1000 words (40 columns × 25 rows), ending at 0x5D2F7. Function 0x4438E combines each word's low 12-bit tile number with palette bits from the RLE control stream at 0x5850E, then writes the result column-major to playfield VRAM. Subranges beginning at 0x5CB48 and 0x5CD40 are named as overlapping views into this tile-number stream rather than disjoint ROM regions, but no renderer that indexes them directly has been found — see those two rows. |
| 0x5CB48 | 504 B overlapping view | `special_object_tile_numbers` — a named subrange of `attract_display_tile_stream`. **No indexing consumer was found**: the only reference into 0x5CB28–0x5D2F7 is `movea.l #0x5CB28,a2` at 0x4439E, which walks the stream sequentially. **Confidence: Verified** for the range; **Unknown** for the claim that a special-object renderer indexes it directly. |
| 0x5CD40 | 1464 B overlapping view | `special_object_anim_tiles` — a named subrange running to the end of `attract_display_tile_stream` at 0x5D2F7, with the same evidence gap as the row above. **Confidence: Verified** for the range; **Unknown** for the animation-frame indexing claim. |
| 0x5D2F8 | 216 B | `wall_desc_pattern6` — 27 eight-byte 2×2 wall descriptors used when `wallpattern == 6`, selected by `wall_conn_variant_tbl6`; exact range 0x5D2F8–0x5D3CF. |
| 0x5D3D0 | 24 B | `wall_desc_destructible` — three eight-byte 2×2 descriptors for successive destructible-wall stages, beginning with tile groups 0x07A7, 0x07AB, and 0x07AF. `wall_crumble` compares the first word of each descriptor to identify the current stage. |
| 0x5D3E8 | 16 B | `dragon_probe_delta_a` — four `{column_delta,row_delta}` word pairs for the first footprint cell tested in each cardinal direction. Column deltas are ±1/0; row deltas are ±0x20/0 in packed maze coordinates. |
| 0x5D3F8 | 16 B | `dragon_probe_delta_b` — parallel four-pair offsets for the second footprint cell tested by `dragon_choose_move_direction`. |
| 0x5D408 | 16 B | `dragon_spawn_offset_a` — four horizontal words at 0x5D408 followed by four vertical words at 0x5D410, indexed by `dragon_facing >> 1`; positions the first secondary dragon segment at creation. |
| 0x5D418 | 16 B | `dragon_spawn_offset_b` — matching H/V arrays for the second secondary segment. |
| 0x5D428 | 16 B | `dragon_facing_offset` — four horizontal words at 0x5D428 and four vertical words at 0x5D430. Combined with the pose-dependent tables at 0x5D4C8/0x5D4E8 for segment collision and attack positioning. |
| 0x5D438 | 64 B | `dragon_head_hdelta` — **32** head hpos delta words, indexed by `path byte + dragon_facing × 4` (0x54616–0x54626), where facing is encoded 0/2/4/6. Twice the 16-entry pose index plus the path byte's fire bit, so each (pose, facing) has a mouth-closed and a mouth-open entry (verified against the disassembly and the ROM words) |
| 0x5D478 | 64 B | `dragon_head_vdelta` — matching **32** vpos delta words, same index. The ROM's V axis grows upward, so a positive entry moves the head up the screen (verified) |
| 0x5D4B8 | 16 B | `dragon_fire_segment_tbl` — 16 signed bytes: segment index in `dragon_seg_mob_ids` from which a fireball spawns, indexed by `(path byte >> 1) + dragon_facing × 2`. |
| 0x5D4C8 | 32 B | `dragon_pose_hdelta` — 16 horizontal position words indexed by pose/facing, combined with `dragon_facing_offset` during collision and attack positioning. |
| 0x5D4E8 | 32 B | `dragon_pose_vdelta` — matching 16 vertical words. |
| 0x5D508 | 32 B | `dragon_body_pics` — 16 picture words selected by animation phase plus facing; used while turning/stunned and for the normal body animation. |
| 0x5D528 | 80 B | `dragon_head_pics` — the first **64 bytes are 32** head picture words indexed by `path byte + dragon_facing × 4`; the final 16 bytes (0x5D568) are 8 separately selected pictures (verified; the old "0x5D508 head sprites"/"0x5D568 fire-breath tiles" rows described parts of this range, and the "16 head picture words" count contradicted the 64-byte extent it was given) |
| 0x5D578 | 80 B | `dragon_path_programs` — 5 path programs × 16 bytes (see `04_game_subsystems.md` §8.3). Byte = (pose<<1)\|fire-bit; one byte per 8-frame phase |
| 0x5D5C8 | 512 B | `playfield_palettes` — 16 × 32-byte (16 IRGB words) playfield palettes, indexed by the high nibble of maze-header `playfield_colors`; copied to color RAM 0x910500 by `init_display` (entry = index×32; the word at entry+16 is also stored to 0x904020/0x90401E). |
| 0x5D7C8 | 128 B | `playfield_special_palette_bank` — four contiguous 32-byte palettes through 0x5D847. In `init_display`, wall patterns ≥6 use this base and select an entry with `variant_D3 × 32`. |
| 0x5B20E | 72 B | `player0_hurt_palette_cycle` — normal hurt/flash cycle for player 0 |
| 0x5B256 | 72 B | `player1_hurt_palette_cycle` — player 1 normal cycle |
| 0x5B29E | 72 B | `player2_hurt_palette_cycle` — player 2 normal cycle |
| 0x5B2E6 | 72 B | `player3_hurt_palette_cycle` — player 3 normal cycle; ends at 0x5B32D |
| 0x5B32E | 192 B | `player0_power_palette_cycle` — extended poison/invisibility/invulnerability cycle for player 0 |
| 0x5B3EE | 192 B | `player1_power_palette_cycle` — player 1 extended cycle |
| 0x5B4AE | 192 B | `player2_power_palette_cycle` — player 2 extended cycle |
| 0x5B56E | 192 B | `player3_power_palette_cycle` — player 3 extended cycle; ends at 0x5B62D |
| 0x5B62E | 12 B | `thief_stealable_power_masks` — six words tested in order against `player_powers`: `{0x10,1,8,0x20,2,4}`. |
| 0x5B63A | 16 B | `thief_contact_damage` — eight character/powered-state damage words indexed as character +4 when protection is present. |
| 0x5B64A | 18 B | `direction_column_delta` — nine signed words for directions 0–8: `{0,+1,+1,+1,0,−1,−1,−1,0}`. |
| 0x5B65C | 18 B | `direction_row_delta` — nine packed-maze row deltas: `{−0x20,−0x20,0,+0x20,+0x20,+0x20,0,−0x20,0}`. |
| 0x5B66E | 64 B | `maze_object_traversability_flags` — one byte per maze object type, tested by movement and transporter probes. |
| 0x5B6AE | 64 B | `thief_collision_remove_flags` — one byte per object type; a nonzero entry makes thief collision remove that object. |
| 0x5B6EE | 12 B | `thief_hurt_sound_choices` — three longword sound IDs `{0x66,0x67,0x68}` selected by `getrandom(3)` after the thief damages a player. |
| 0x5B6FA | 8 B | `thief_player_speech_ids` — two longword speech IDs `{0x62,0x64}` selected for the normal thief's victim/player variant. |
| 0x5B702 | 8 B | `mugger_player_speech_ids` — two parallel longword speech IDs `{0x63,0x65}` for the mugger/super-thief variant. |
| 0x5B70A | 18 B | `thief_direction_step_size` — nine direction-indexed movement words `{0x70,0x60,0xE0,0xA0,0xB0,0x90,0xD0,0x50,0xF0}` passed into `thief_move_engine`. |
| 0x5B71C | 8 B | `tport_direction_rotation` — eight bytes `{0,7,1,6,2,5,3,4}`, a full permutation of directions 0–7. `tport_player_move` 0x50708–0x5071C reads `move.b (a2,d0.w),d1` from this base, adds a stored direction, masks `& 7`, and uses the result to index `direction_column_delta` (0x5B64A). The former list `{1,6,2,5,3,4,0,0}` was shifted two bytes and zero-padded, and was not a permutation. |
| 0x5B724 | 8 B | `damage_comment_speech_ids` — two longword speech IDs `{0x60,0x5F}`. |
| 0x5B72C | 8 B | `character_repulse_timer_init` — four character-indexed words `{0x038C,0x04B8,0x0260,0x038C}`. |
| 0x5B734 | 8 B | `character_stun_delay_add` — four character-indexed words `{0x78,0x2D,0x78,0x3C}` (Warrior 120, Valkyrie 45, Wizard 120, Elf 60). `player_tile_interact` 0x51318–0x5132E reads `player_character[player]`, doubles it, and indexes this base; 0x51350 additionally reads element 2 absolutely (`move.w 0x5B738.l,d3`). The former list was shifted one element. |
| 0x5B73C | 16 B | `tile_effect_sound_ids` — four **character-indexed** longword sound IDs `{0x32,0x34,0x32,0x33}`, exact range 0x5B73C–0x5B74B. `player_tile_interact` 0x512E8–0x512FE reads `player_character[player]`, scales it `asl.w #2`, and indexes this base, so the table must hold four entries. The alternate branch at 0x51334 is `MOVE.L (0x5B744).L,-(SP)` (opcode 0x2F39) — an absolute read of interior **element 2**, not a second table base. The former split into two 2-entry tables, and the value list `{0x34,0x32}` for 0x5B744, were both **Contradicted**. |
| 0x5B74C | 40 B | `pickup_score_values` — 20 score words indexed by normalized pickup/result code. |
| 0x5B774 | 20 B | `pickup_score_popup_types` — 20 byte popup-type indices parallel to `pickup_score_values`. |
| 0x5B788 | 16 B | `level_exit_sound_ids` — four player-indexed longword sound IDs 0x0E–0x11. |
| 0x5B798 | 40 B | `pickup_random_sound_banks` — ten longword sound IDs partitioned into four banks of lengths 3,2,3,2 at 0x5B798/0x5B7A4/0x5B7AC/0x5B7B8. |
| 0x5B7C0 | 16 B | `pickup_random_sound_ptrs` — four longword pointers to the variable-length banks at 0x5B798; the byte counts used by the same dispatcher are stored at 0x5B7D0. |
| 0x5B7D0 | 4 B | `pickup_random_sound_counts` — byte counts `{3,2,3,2}` parallel to `pickup_random_sound_ptrs`; the pickup class selects a bank, then `getrandom(count)` selects its longword sound ID. |
| 0x5B7D4 | 16 B | `collision_hpos_base_by_case` (`player_hand_power`) — eight words `{2,2,1,1,3,3,2,2}` indexed by `character + 4*Fight-power` (`mob_collision_test` builds D4 at 0x521AE-0x521D0, then reads this table at 0x52400). The selected base plus the random component below is subtracted from the monster's tier nibble at 0x52416. |
| 0x5B7E4 | 8 B | `collision_hpos_random_range_by_player` (`player_hand_random_range`) — four **cabinet-player-position** words `{0,0,0,2}`, indexed by player number D3 and passed to `getrandom` at 0x523E4-0x523F6. This dimension is intentionally not character. |
| 0x5B7EC | 16 B | `collision_bonus_threshold_by_case` (`generator_fight_power`) — eight words `{3,2,0,0,4,3,0,1}`, indexed by the same `character + 4*Fight-power` D4. Generator collision branches compare the selected threshold against `getrandom(4)` before awarding score and removing or degrading the generator. Exact range ends at 0x5B7FB. |
| 0x5B7FC | 32 B | `exit_rotation_offset_by_count` — 32 one-byte offsets indexed by `exit_count`; `main_exit_move` adds the selected offset to its current exit cursor and reduces it modulo the count. Exact range ends at 0x5B81B. |
| 0x5B81C | 576 B | `exit_desc_by_floorpattern` — **9** floor-pattern records × 64 bytes, each record holding 16 absolute longword pointers into `exit_tile_descs` (0x5C8B0). Setup selects a record with `floorpattern << 6` (`asl.l #4` then `asl.l #2` at 0x44B9E–0x44BA0, base `movea.l #0x5B81C,a0` at 0x44BA2); `main_exit_move` reads record offsets 0 and 0x20 directly and offsets 0x20–0x3C in four-byte animation steps. `floorpattern` is the high nibble of maze header byte 5 and is 0–8 across all 117 shipped mazes, so record 8 ends at 0x5BA5B and the exact indexed range is **0x5B81C–0x5BA5B**. Records 0–8 hold 16/16 valid pointers; the bytes at 0x5BA5C onward hold no pointers (0x00002, 0xFF00FD80) and 0x5BA5C is itself an independent longword-table base used by `wall_crumble` (`movea.l #0x5BA5C,a0` at 0x53114). The former 16-record/1024-byte extent, and the "intentional overlap" it created with the logo constants, forcefield pointers, shot-reflect tables, floor descriptors and wall-descriptor bank, were **Contradicted**. |
| 0x5D7E8 | 96 B overlapping view | `playfield_special_palette_lowwall_view` — entries 1–3 of the four-entry bank. Wall patterns <6 use this biased base and likewise add `variant_D3 × 32`; therefore 0x5D808 and 0x5D828 are indexed entries, not independent or unreferenced palette objects. |
| 0x5D848 | 416 B | `unconsumed_block_5d848` — 416 bytes with **no runtime consumer**. A whole-image 32-bit operand scan finds exactly one target inside 0x5D848–0x5D9E7: 0x5D978, and that is the `potion_effect_matrix` biased base (`lea 0x5D978,a0` at 0x41666), not a palette access — its first reachable index is object type 0x12 × 16, which lands at 0x5DA98. The former "13 blocks × 32 bytes, 12 colors + 4 zero words, one per tileset environment" reading was derived from the byte pattern alone, which §5.0 forbids. **Confidence: Verified** for the range and for the absence of any consumer; **Unknown** for structure and purpose. |
| 0x5D9E8 | 176 B | `secretcode_text_recs` and contest strings, ending at 0x5DA97: "SECRET CODE", "REMEMBER YOUR", and the Atari contest address/deadline text; referenced from code at 0x552EA |
| 0x5DA98 | 448 B | `potion_effect_matrix` — 28 records × 16 bytes for object types 0x12–0x2D, ending exactly at 0x5DC57 before `mob_create`. The sole consumer is the potion-blast MOB scan at 0x4153E–0x41728; its `lea 0x5D978` at 0x41664 is the only reference to the biased base anywhere in the ROM (0x5DA98 itself is never referenced). Index = `(object_type << 4) + player_character[potion_player] + trigger_flags`: bits 0–1 are the drinker's character read from `player_character` (0x9048E8), bit 2 marks a shot-triggered potion (`resolve_shot_hit` stores `shooter + 4` into `potion_player` at 0x4BA88, versus the bare player index stored by `main_handle_potions` at 0x4707E), and bit 3 selects the enhanced-magic variant (`player_powers` high-byte bit 5, tested at 0x4159C). **A zero entry destroys a target that reaches the lookup** — `move.b (a0,d1.w),d0` at 0x4166A is followed by `beq 0x416CA`, which removes the MOB. Pre-lookup special arms matter: IT is filtered at 0x4155C; a phasing Super Sorcerer is revealed at 0x415AC-0x415DC; an idle Acid puddle is put into its attack/stun phase at 0x415E6-0x41604. Only the other Super Sorcerer/Acid states reach their all-zero rows. Nonzero entries split by object class: generators replace their type/picture, while monsters subtract tier damage and are removed if the result leaves the three-tier valid window. The Wizard column is zero in every reachable row; the Elf column is zero for monster rows and lower generator tiers, while each top generator tier is demoted to tier 1. |
| 0x5EDD4 | 32 B | `wall_pattern_offsets` — 16 words: per-wallpattern offset into `wall_desc_blocks` (verified) |
| 0x5EDF4 | 48 B | `wall_random_desc_ptrs` — two groups of 6 descriptor-set pointers for random-wall patterns 7+ (verified) |
| 0x5EE24 | 256 B | `wall_conn_variant_tbl` — 8-neighbor connectivity mask → wall variant byte (verified) |
| 0x5EF24 | 256 B | `wall_conn_variant_tbl6` — alternate variant table for wallpatterns 6 and 0xB (verified) |
| 0x5F9CE | 32 B | `door_gfx_by_neighbors` — 16 words: door picture by 4-bit adjacent-door mask (verified in `pf_door_draw`; formerly "straight-wall connectivity") |
| 0x5FACA | 18 B | `door_gfx_type2` — 9 picture words for isolated type-2 doors, indexed by the same 3×3 negative/neither/positive blank-floor orientation used by type 3 |
| 0x5FADC | 18 B | `door_hpos_sub2` — type-2 horizontal-position subtract corrections parallel to `door_gfx_type2` |
| 0x5FAEE | 18 B | `door_vpos_add2` — type-2 vertical-position add corrections; ends at 0x5FAFF immediately before the type-3 orientation code |
| 0x5FBDC | 18 B | `door_gfx_type3` — 9 picture words for isolated type-3 doors. The index is a 3×3 combination of vertical and horizontal blank-floor orientation: blank on the negative side, neither, or blank on the positive side. `pf_door_draw` computes an even byte offset 0,2,...,16 and reads the picture at 0x5FBDC; the same offset selects the vpos corrections below. |
| 0x5FBEE | 18 B | `door_vpos_sub3` — type-3 door vpos subtract offsets (verified) |
| 0x5FC00 | 18 B | `door_vpos_add3` — 9 type-3 vertical-position add offsets parallel to the picture/subtract tables; exact range 0x5FC00–0x5FC11 |
| 0x5FC12 | 16 B | `player_inventory_vram_ptrs` — four longword pointers (one per player) to the HUD inventory-icon rows; the old 0x5FC10 start overlapped the last `door_vpos_add3` word |
| 0x5FDAC | 6 B | `supersorc_direction_bias` — three signed words `{0,-1,+1}`. `supersorc_place` adds one to the starting direction when testing its three placement alternatives. |
| 0x5FDB2 | 6 B | `supersorc_probe_steps` — three words `{4,3,3}` parallel to `supersorc_direction_bias`; number of successive cells required to be clear for each alternative. Code begins immediately at 0x5FDB8. |
| 0x55512 | 60 B | `dead_name_entry_epilogue_fragments` — four unreachable compiled-code suffixes after `name_entry_draw_char` returns and before the duplicate full function at 0x5554E. No branch, call, pointer, or fall-through reaches them; they depend on an already-established A6 frame and are runtime-dead residue rather than callable entries. |
| 0x56F5C | 76 B | `dead_slapstic_verify_suffix` — duplicated loop/return suffix after the live `slapstic_verify` return at 0x56F5A. Its branches target the live body's interior, but no control edge enters the suffix; classified as runtime-dead compiled residue. |
| 0x5FF98 | 26 B | `dead_truncated_supersorc_epilogues` — two truncated copies of `supersorc_place` epilogue tails immediately before the final erased pad. Neither begins with a complete instruction sequence/control entry and no edge reaches either fragment. |

### 5.6 String / Dialog Data

| Address | Size | Content |
|---------|------|---------|
| 0x570B4 | 8 B | `portrait_display_offsets` — two four-byte arrays: X positions `{12,5,12,18}` at 0x570B4 and Y positions `{24,26,29,26}` at 0x570B8, indexed by character. |
| 0x570BC | 8 B | `portrait_alpha_words` — four words `{0x841C,0x841C,0x841E,0x841D}` written to the character-specific alpha destinations in `portrait_alpha_dest_ptrs`. |
| 0x570C4 | 8 B | `portrait_sprite_words` — four character portrait picture words `{0x841D,0x841E,0x841F,0x841F}` written through `portrait_sprite_dest_ptrs`. |
| 0x570CC | 16 B | `portrait_alpha_dest_ptrs` — four longword destinations parallel to `portrait_alpha_words`; MAME observed writes to 0x905C9A, 0x905D16, 0x905D96, and 0x905E1A, all in unreachable transporter-row padding. |
| 0x570DC | 16 B | `portrait_sprite_dest_ptrs` — four longword destinations parallel to `portrait_sprite_words`; MAME observed writes to 0x905C9C, 0x905D20, 0x905DA0, and 0x905E1C. The ROM range ends at 0x570EB. |
| 0x570EC | 32 B | `joystick_direction_bitmasks` — 16 words `{00FE,00FC,00FD,00F9,00FB,00F3,00F7,00E7,00EF,00CF,00DF,009F,00BF,003F,007F,007E}`, exact range 0x570EC–0x5710B. **No consumer of any kind exists**: a whole-image 32-bit operand scan finds no reference, and the nearest bound bases (0x570DC and 0x5710C) both index forward. Their complements form a 16-step single-bit/adjacent-pair ring, which contradicts a 4-bit nibble domain, so the former "indexed by the four-bit joystick-direction nibble" claim is withdrawn. **Confidence: Verified** for the bytes and the absence of a consumer; **Unknown** for the index rule and purpose. |
| 0x5710C | 108 B | `floor_palette_color_indices` — nine floor-pattern rows × six words. `init_display` selects row `floorpattern × 6`; columns 0–2 are used when `wallpattern >= 11`, columns 3–5 otherwise. Each word is a color index added to `(playfield_palette_index << 4)` before reading three palette words. Exact range 0x5710C–0x57177. |
| 0x57178 | 96 B | `service_instruction_text_chain` — formatted-text nodes and inline strings “CLEARING STATS”, “TO ABORT”, “WARRIOR BUTTONS”, and “PRESS BOTH”, exact range 0x57178–0x571D7. Nodes use the same 8/12-byte linked descriptor format as the legend chains. |
| 0x571D8 | 2 B | `forcefield_delay_alignment` — zero alignment word immediately before the live delay profiles; no consumer discovered. |
| 0x571DA | 32 B | `forcefield_cycle_delay_profiles` — four profiles × eight bytes: `{10,20,10,20,10,20,20,40}`, `{10,20,08,10,10,20,08,40}`, `{08,08,08,20,10,20,08,40}`, and `{10,10,20,20,40,40,08,40}`. `main_cycle_tport_and_ffield` adds `random_word(8)` to the next byte of the selected profile to reload `ff_cycle_timer`. |
| 0x57398 | 60 B | `challenge_shared_qualifier_text` — the shared “AFTER COLLECTING ALL POTIONS” and “AFTER SHOOTING 3 SECRET WALLS” strings, ending at 0x573D3 |
| 0x573D4 | 112 B | `challenge_qualifier_descs` — 14 × 8-byte `text_desc`-style records indexed by challenge code−0x50. Layout: byte row, byte column, longword string pointer, word zero/reserved; a null pointer suppresses the qualifier. |
| 0x57444 | 104 B | `challenge_unique_qualifier_text` — strings unique to individual challenge codes, ending at 0x574AB |
| 0x574AC | 8 B | `challenge_it_desc` — extra text descriptor for the “IT” suffix used by challenge 0x5C; string at 0x574B4 |
| 0x574B4 | 4 B | `challenge_it_text` — NUL-terminated "IT" string |
| 0x574B8 | 102 B | `character_glyph_rows` — variable-length, zero-terminated rows of consecutive alpha/sprite glyph codes used for character graphics; exact range 0x574B8–0x5751D |
| 0x5751E | 90 B | UI strings: " SELECT HERO ", "PRESS START", "ADD COIN", "INSERT COIN", "GAME OVER", "ON LEVEL:"; exact range 0x5751E–0x57577. The block starts at 0x5751E — `pea.l 0x5751E` at 0x4575A is the live push and the first two bytes are the leading space and `S` of " SELECT HERO "; nothing references 0x57520 |
| 0x5815C | 48 B | `dialog_tip_ptrs` — 12 longword pointers to the between-level tip records (note: not 0x58154; the two preceding longs are unrelated) |
| 0x5828C | 642 B | `dialog_tip_records` (exact range 0x5828C–0x5850D) — 12 records, each 3 longword string pointers (NULL = unused line) plus inline strings: 0 "BLUE / SELECTED / ELF" (join-banner template); 1 PUSH MOVABLE WALLS; 2 SOME TREASURE REQUIRES KEYS; 3 THERE CAN BE MORE THAN ONE TRAP; 4 ACID PUDDLES MOVE RANDOMLY; 5 SOME WALLS CAN BE SHOT AND TURN INTO GOOD OR BAD; 6 DEATH DIES AFTER TAKING UP TO 200 HEALTH; 7 HAVE FRIENDS JOIN IN ANY TIME; 8 MONSTERS FOLLOW PLAYER WHO IS IT; 9 SOME WALLS MOVE RANDOMLY; 10 MONSTERS MAY MOVE DIFFERENTLY; 11 TAG, YOU'RE IT. |
| 0x57578 | 188 B | DIP-switch display records; exact range 0x57578–0x57633. The chain's last node begins at 0x57628 with flags 0x0200 and its four-byte back-link 0x0005761C occupies 0x57630–0x57633 |
| 0x57634 | 16 B | Continue-screen header: an 8-byte `text_desc` `{column 4, row 9, string_ptr 0x5763C, flags 0}` followed by the NUL-terminated "LEVEL:" label at 0x5763C; exact range 0x57634–0x57643. `show_level_start_screen` pushes `pea.l 0x57634.l` at 0x451E0 and calls OS API 0x200; nothing references 0x57638 |
| 0x57644 | 20 B | `continue_blank_line` — fixed-width blank line, not the PRESS START text |
| 0x57658 | 20 B | `continue_press_start` — fixed-width "PRESS START" line |
| 0x5766C | 20 B | `continue_within_seconds` — fixed-width "WITHIN    SECONDS" line |
| 0x57680 | 20 B | `continue_game_line` — fixed-width "TO CONTINUE GAME" line |
| 0x57694 | 20 B | `continue_level_line` — fixed-width "AT THIS LEVEL" line, ending at 0x576A7 |
| 0x576A8 | 14 B | `heartbeat_mask_table` — seven words selected by `health >> 5`: 0x1F, 0x3F, 0x3F, 0x7F, 0x7F, 0xFF, 0xFF |
| 0x576B6 | 28 B | `score_star_picture_cycle` — 14 picture words used by the long floating-score/star animation in `main_score_update`; repeated pairs advance through 0x0924–0x095A. |
| 0x576D2 | 8 B | `score_effect_picture_cycle_a` — four words `{0x0EFC,0x0EFC,0x0FFC,0x10FC}` used by one four-frame score-effect branch. |
| 0x576DA | 8 B | `score_effect_picture_cycle_b` — four words `{0x1C5C,0x1C5C,0x1C60,0x1C64}` used by the alternate branch. |
| 0x571FA | 4 × 4B | `forcefield_cycle_delay_ptrs` — pointers to the four eight-byte profiles at 0x571DA/0x571E2/0x571EA/0x571F2, indexed by `(level & 3)` during maze setup. The former “color table” name was contradicted by the consumer, which uses these bytes only as randomized timer bases. |
| 0x5720A | 8 B | `secret_player_palette_words` — four player-indexed text attributes `{0x8400,0x8800,0x8C00,0x9000}` used for the secret-room winner's color label. |
| 0x57212 | 16 B | `player_color_name_ptrs` — four longword pointers to fixed-width color strings `" RED  "`, `" BLUE "`, `"YELLOW"`, and `"GREEN "` at 0x57222–0x57241. |
| 0x57222 | 32 B | `player_color_name_strings` — four padded eight-byte/NUL-terminated color labels targeted by `player_color_name_ptrs`. `show_level_start_screen` passes them to OS large-text API 0x26C at column 0; the leading large-space glyph supplies the intended margin. |
| 0x57242 | 16 B | `character_name_ptrs` — four pointers to the padded character labels WARRIOR, VALKYRIE, WIZARD, and ELF at 0x57252–0x57279. |
| 0x57252 | 40 B | `character_name_strings` — four fixed-width ten-byte character labels `"WARRIOR "`, `"VALKYRIE"`, `" WIZARD "`, and `"  ELF   "` targeted by `character_name_ptrs` and drawn as large text at column 13. |
| 0x5727A | 180 B | `level_start_message_strings` — NUL-terminated strings used by `show_level_start_screen`, from “SECRET ROOM” through “LEVEL ”; exact range 0x5727A–0x5732D. Call sites pass explicit row/column/attribute arguments rather than using a descriptor table. |
| 0x5732E | 6 B | `player_power_icon_column_offsets` — bytes `{0x0B,0x0A,0x03,0x02,0x01,0x00}` read by `player_inv_update` at 0x45BBA–0x45BC0. Added to the name-row base at alpha column 29, they place power bits 0–5 at columns 40, 39, 32, 31, 30, and 29. |
| 0x57334 | 12 B | `player_power_icon_words` — six complete alpha words `{0x983B,0x9D7A,0xA0A2,0xA49C,0xA97B,0xACA3}` parallel to the column offsets and selected by low-byte `player_powers` bits 0–5 at 0x45B9E–0x45BDC. The former `dead_header_byte_block` and `level_start_*` classifications were **Contradicted** by the direct `player_inv_update` consumer. |
| 0x5758E | 14 B | `bonus_time_header_desc` — text descriptor `{column 34,row 1,string_ptr 0x57596,flags 0}` followed by `"TIME:"`; `setup_infopanel` uses it for maze numbers 0x68 and above after blanking the ordinary logo/level region |
| 0x57BD8 | 738 B | `dead_tile_word_block` — runtime-dead ROM residue containing 369 uninterrupted big-endian words, exact range 0x57BD8–0x57EB9. Nearly every value is a 0x1Exx tile/picture code (many 0x1E13 blanks); there are no terminators or pointer boundaries. Whole-ROM pointer/xref and immediate/computed-base searches found no game or OS consumer. Although 369 factors as 9×41, the shipped code supplies no dimensions or orientation, so this must not be promoted to a live rectangular-map interpretation. |
| 0x57EBA | 320 B | `factory_highscore_records` — exactly 40 eight-byte records through 0x57FF9. Each record is `{uint32_be score, char initials[3], uint8 zero}`; records are arranged as four character-class lists of ten because initialization adds `class × 0x50 + rank × 8`. Starts with score 0x1F40 and initials `AWC`. |
| 0x57FFA | 118 B | Score-per-coin display records plus the “Enter your initials:” prompt, exact range 0x57FFA–0x5806F. The block opens with an 8-byte `text_desc` `{column 6, row 14, string_ptr 0x58002, flags 0}` whose string is “SCORE PER COIN”; `attract_highscores` pushes `pea.l 0x57FFA` at 0x4A1AA and nothing references 0x58000 |
| 0x5818C | 256 B aggregate view | Four adjacent demo-player streams through 0x5828B, split by the pointer table at 0x58098 into 56, 150, 2, and 48 bytes. Commands are 2-byte pairs. First byte 0x00–0xFD = frame duration and second byte = recorded input; 0xFF = show dialog tip whose index is the second byte; 0xFE = join/switch demo player encoded by the second byte. |
| 0x59736 | 80 B | `hint_text_ptrs` — 20 longword pointers, ending at 0x59785 immediately before the strings. The old 0x59732 address overlapped the final 0xCC entry of `speech_charname_tbl`. |
| 0x59786 | 306 B | Hint text strings (“TRY TRANSPORTABILITY”, “WATCH WHAT YOU SHOOT”, etc.), exact range 0x59786–0x598B7, including the final string's NUL and its even-alignment pad |
| 0x598B8 | 228 B | `hint_text_desc_records` — seven units, each an 8-byte `text_desc` `{u8, u8, u32 string_ptr, u16 flags}` followed by its inline NUL-terminated string; exact range 0x598B8–0x5999B. `level_splash` pushes `pea.l 0x598B8.l` at 0x4BE6E and nothing references 0x598B6, which is the previous string's NUL plus pad. The first record is `03 15 | 00 05 98 C0 | 00 00` → “FIND THE HIDDEN POTION”. Every `flags` field is 0x0000, so **there is no speech-ID field**; the former “10-byte units … command/speech metadata” description was **Contradicted** |
| 0x5999C | 440 B | Gameplay tip strings (“MORE PLAYERS ALLOWS HIGHER”, “BONUS MULTIPLIER”, “ADD MORE PLAYERS FOR”, “GREATER FIREPOWER”, “ADD COINS ANYTIME”, …), exact range 0x5999C–0x59B53 before the maze-decompression pointer table |
| 0x59B54 | 16 B | `maze_decomp_type_ptrs` — four longword pointers selected by `(bytecode >> 4) & 3`: HT1, VT1, HT2, VT2 |
| 0x59B64 | 24 B | `powerup_bit_masks` — 12 words indexed by power-up ID 0–11: `{0x0002,0x0001,0x0020,0x0010,0x0008,0x0004,0x0100,0x0200,0x0400,0x0800,0x1000,0x2000}`. `player_give_item_with_message` rejects an already-owned bit, ORs the word into `player_powers`, and uses high-byte bits as one-shot dialog latches. |
| 0x59B7C | 48 B | `powerup_speech_ids` — 12 longword speech-command IDs parallel to `powerup_bit_masks`: `{0x8F,0x90,0x91,0x92,0x93,0x94,0x8E,0xD1,0xCF,0xD0,0,0}`. A zero entry suppresses power-up speech. |
| 0x59BAC | 1620 B | `first_encounter_message_records` — variable-sized storage for the 32 first-encounter message records through 0x5A1FF. Every pointer in the normal/alternate tables targets a 12-byte record `{line0_ptr,line1_ptr,line2_ptr}`; zero line pointers shorten the box. Each record is followed by its NUL-terminated inline strings, and multiple pointer-table entries may be null or alias an existing record. |
| 0x5A200 | 128 B | `first_encounter_message_ptrs` — 32 longword pointers indexed by the bit number selected from `dialog_first_encounter_flags`. This is the normal message set; entries point into `first_encounter_message_records`. |
| 0x5A280 | 128 B | `first_encounter_speech_ids` — 32 longword speech-command IDs parallel to both message-pointer tables. Zero suppresses speech; the nonzero shipped entries include 0x9D, 0xA8, 0x9E, 0xB6–0xB8, and 0xD2. |
| 0x5A300 | 128 B | `first_encounter_alt_message_ptrs` — alternate 32-pointer view selected only when game-settings bit 10 is set and `game_mode` is nonnegative. Entry 0 points to the compact FOOD/DRINK message at 0x59BE8 and the remaining shipped entries are null. Exact range 0x5A300–0x5A37F; the old 0x5A320 “padding” classification was false. |
| 0x5A380 | 384 B | `powerup_name_strings` — 16 fixed-width 24-byte strings: four “<character> NOW HAS” prefixes plus 12 power-up names; exact range 0x5A380–0x5A4FF |
| 0x5A500 | 64 B | `powerup_name_ptrs` — 16 longword pointers to the fixed-width strings |
| 0x5A540 | 46 B | Monster-legend header/value strings (“Type”, “Fight”, “Shoot”, “Magic”, blank, “NO”, “YES”, “STUN”), ending at 0x5A56D |
| 0x5A56E | 258 B | `monster_legend_cells` — 42 `{long string_ptr; word text_attribute}` cells followed by one all-zero sentinel record; exact range 0x5A56E–0x5A66F. `draw_legend_monsters_page` consumes four live cells per creature (name, Fight, Shoot, Magic); two single-space name records create the top-list gap before DRAGON while the lower ten-row matrix stays contiguous. Values route through attributes 0x9000 (name), 0x8800 (NO), 0x8400 (YES), and 0x8C00 (STUN). The old 0x5A570 start landed two bytes inside the first pointer. |
| 0x5A670 | 110 B | Monster/object name strings: “GHOST”, “GRUNT”, “DEMON”, “LOBBER”, “SORCERER”, etc.; exact range 0x5A670–0x5A6DD |
| 0x5A6DE | 284 B | `legend_powerup_desc_chain` — inline labels plus the formatted-text descriptor chain headed at 0x5A7E8, exact range 0x5A6DE–0x5A7F9. It lists FOOD, MAGIC, POTIONS, INVISIBILITY, INVULNERABILITY, REPULSIVENESS, REFLECTIVE SHOTS, 10 SUPER SHOTS, TRANSPORTABILITY, DESTRUCTABLE, and MOVEABLE. |
| 0x5A7FA | 116 B | `legend_object_desc_chain` — descriptor/string chain headed at 0x5A858, exact range 0x5A7FA–0x5A86D. It lists EXIT, TRAP, STUN TILE, FORCE FIELD, KEY, and TREASURE. |
| 0x5A86E | 94 B | `legend_wallfloor_desc_chain` — descriptor/string chain headed at 0x5A8AE, exact range 0x5A86E–0x5A8CB. It lists TEMPORARY, POTIONS, PERMANENT, POTIONS, and WALL/FLOOR TYPES. Nodes are `{uint8 row, uint8 column, uint32 string_ptr, uint16 flags}`; flag 0 is the leaf, while flag 0x0200 is followed by a longword link to the preceding node. |
| 0x5A8CC | 220 B | `legend_credit_roles_chain` — eight inline role labels and their formatted-text chain, headed at 0x5A99C and ending at 0x5A9A7. Labels include DESIGNER/PROGRAMMER, GAME PROGRAMMER, VIDEO GRAPHICS, ENGINEER, TECHNICIAN, SOUND DESIGN, CABINET DESIGN, and SPECIAL THANKS TO. |
| 0x5A9A8 | 192 B | `legend_credit_name_strings` — 15 inline credit strings from ED LOGG through AND MANY OTHERS, exact range 0x5A9A8–0x5AA67. |
| 0x5AA68 | 178 B | `legend_credit_names_chain` — formatted-text descriptors for the 15 names, leaf at 0x5AA68 and head at 0x5AB0E; exact range 0x5AA68–0x5AB19. `draw_legend_overview_page` passes this head to OS service 0x142. The former `bonus_scoring_strings` interpretation of 0x5AA70 was false: these bytes are row/column/string/flags/link records, not text. |
| 0x5AB1A | 12 B | `treasure_bonus_coin_label` — NUL-terminated `100 x COINS`, used by the ordinary level-end bonus screen. |
| 0x5AB26 | 12 B | `treasure_bonus_treasure_label` — NUL-terminated `TREASURES x`. |
| 0x5AB32 | 8 B | `treasure_bonus_equals_label` — NUL-terminated `BONUS =`. |
| 0x5AB3A | 12 B | `treasure_no_bonus_label` — NUL-terminated `NO BONUS !!`. |
| 0x5AB46 | 18 B | `treasure_5000_coin_label` — NUL-terminated `5,000 x COINS = `, used by the secret bonus branch. |
| 0x5AB58 | 12 B | `treasure_no_bonus_label_alt` — second NUL-terminated `NO BONUS !!` string. These six labels are consumed by `show_level_end_bonus_screen` at 0x4D5B6–0x4D800. |
| 0x5AB64 | 44 B | `treasure_seconds_speech` — 11 longword sound IDs indexed directly by seconds remaining 0–10: ZERO, ONE, TWO, …, TEN. The zero entry is bypassed by the timeout branch but makes the numeric table direct-indexed. |
| 0x5AB90 | 80 B | `treasure_fake_countdown_sequences` — four sequences × five longword number-speech IDs. On later levels a nonzero `treasure_voice_set` selects one deliberately scrambled spoken countdown for displayed seconds 10 through 6. |
| 0x5ABE0 | 16 B | `treasure_fake_countdown_ptrs` — four longword pointers to the five-entry sequences at 0x5AB90/0x5ABA4/0x5ABB8/0x5ABCC. |
| 0x5ABF0 | 8 B | `treasure_fakeout_speech` — two longword speech IDs, JUST KIDDING and FOOLED YOU, selected after the fake countdown reaches displayed second 6. |
| 0x5ABF8 | 16 B | `treasure_timeout_speech` — four longword timeout speech IDs `{ZERO, BETTER LUCK NEXT TIME, ZERO, LOOKS LIKE YOU LOSE}`. Settings bit 11 forces element 0; otherwise `getrandom(4)` selects an entry. |
| 0x5AC08 | 16 B | `treasure_warning_speech` — four longword six-second warnings: BETTER HURRY, TIME IS RUNNING OUT, TIME'S ON MY SIDE, and CAN YOU MAKE IT. |
| 0x5AC18 | 8 B | `treasure_warning_delay` — four words `{1,2,2,2}` parallel to `treasure_warning_speech`; loaded into the once-per-second announcement-delay counter. Ends at 0x5AC1F immediately before `logo_brightness_seq`. |

### 5.7 Palette / Color Data

| Address | Size | Content |
|---------|------|---------|
| 0x5AD1E | 128 B copy view | `alpha_palette_init` — source for `copy_longwords(0x20, ...)`. The helper's pre-tested DBRA loop copies exactly 32 longwords, ending at 0x5AD9D. The interior view at 0x5AD80 supplies `game_vblank` 0x40328-0x4037A: every 16 frames it alternately flattens and restores colors 1-3 of alpha palettes 12-15 at 0x910062-0x91007E, flashing the four player-specific IT labels without changing alpha RAM. |
| 0x5AD9E | 128 B copy view | `mob_palette_init` — second 32-longword initialization block, ending at 0x5AE1D; it begins immediately after `alpha_palette_init` rather than overlapping it. Its consumer forms the address in a data register rather than as a literal, which is why static operand scans report it unreferenced: `init_display` 0x434DA–0x434E0 does `move.l #0x5AD1E,d0; addi.l #0x80,d0`, pushes the result with the destination 0x910100 and count 0x20, and calls `copy_longwords`. |
| 0x5AE1E | 384 B copy view | `mob_palette_extended` — source for `copy_longwords(0x60, ...)`, therefore exactly 96 longwords through 0x5AF9D; it ends immediately before `character_palette_ptrs`. |
| 0x5AF9E | 16 B | `character_palette_ptrs` — four pointers to the 128-byte character palettes at 0x5B00E/0x5B08E/0x5B10E/0x5B18E. It does **not** overlap the bulk palette-copy views: those tile 0x5AD1E–0x5AF9D exactly and end immediately before this table. The copy to color RAM 0x910380 at 0x4360A is `MOVE.L (0x5AFA6).L,-(SP)` (opcode 0x2F39), a **dereference of entry 2** of this table, so the source is 0x5B10E — the Wizard palette — not a separate 128-byte block at 0x5AFA6. The former `aux_palette_init` row was **Contradicted**; the sibling calls at 0x434C8 and 0x435F8 use `PEA` (0x4879) when an address is meant. |
| 0x5AFAE | 96 B | `tport_palette_cycle_blocks` — six 16-byte blocks. VBL selects a block with `tport_cycle_pos << 4` and copies its first six color words to 0x910590; exact range 0x5AFAE–0x5B00D |
| 0x5B00E | 512 B | Four character full palettes (128 B each): Warrior, Valkyrie, Wizard, Elf. Each has four 32-byte sub-palettes (normal/poisoned/ghost/invulnerable); exact range 0x5B00E–0x5B20D |
The exact per-player cycle blocks are cataloged in §5.5. Addresses 0x5B22E, 0x5B42E, and 0x5B52E are interior palette elements, not independent table starts.

### 5.8 Demo Data

| Address | Size | Content |
|---------|------|---------|
| 0x5818C | 56 B | Player 0 demo input stream (28 command pairs), ending at 0x581C3 |
| 0x581C4 | 150 B | Player 1 demo input stream (75 command pairs; primary Elf script), ending at 0x58259 |
| 0x5825A | 2 B | Player 2 demo input stream (one minimal command pair) |
| 0x5825C | 48 B | Player 3/final demo-stream tail through 0x5828B; the pointer at 0x580A4 starts at 0x5825C, so the formerly isolated 0x5825E–0x5828B bytes belong to this stream |

---

## 6. Verified MAZEOBJ Base Tile Values

**Confidence: Verified** from the indexed table and renderer consumers.

All values confirmed against python-gex tile data. From master parameter tables at 0x5868C / 0x5864C. The final column was formerly labeled “Palette”; disassembly shows it is the low-nibble horizontal-size value, reused as the monster health/tier base.

| MAZEOBJ | Type ID | Base Tile (hex) | Base Tile (dec) | H-size / Tier Base |
|---------|---------|----------------|-----------------|--------------------|
| Ghost | 18 | 0x0800 | 2048 | 0x04 |
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

**Confidence: Verified** for pointer values, record boundaries, and live
monster-type indexing.

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

NULL = use idle table for all states. Values read directly from `row76.bin`;
the earlier version of this table was wrong for eight of the ten entries and
contradicted §5.3 and §7.3 of this same document.

| Index | Monster Type | Table Address | Notes |
|-------|-------------|---------------|-------|
| 0 | Ghost | NULL | Ghosts use idle even when moving |
| 1 | Grunt | 0x059026 | `anim_tiles_grunt_moving` |
| 2 | Demon | 0x059126 | `anim_tiles_demon_moving` |
| 3 | Lobber | NULL | Uses idle when moving |
| 4 | Sorcerer | 0x059226 | `anim_tiles_sorcerer_moving` |
| 5 | Aux Grunt | 0x059026 | Shares the Grunt moving bank |
| 6 | Death | 0x0592B6 | `anim_tiles_death_moving_view`, biased 16 bytes into `anim_tiles_death` |
| 7 | Acid | 0x0593B6 | `anim_tiles_acid_moving` |
| 8 | Super Sorc | NULL | Uses idle when moving |
| 9 | IT | NULL | |

### 7.3 Animation Table Addresses

Each animation table has 64 word entries: 8 counter values × 8 directions. Index computation: `index = (anim_counter × 8 + direction) × 2`.

| Address | Size | Name |
|---------|------|------|
| 0x40DB2 | 40 B | `monster_anim_idle_ptrs` (10 longword pointers) |
| 0x40DDA | 40 B | `monster_anim_moving_ptrs` (10 longword pointers) |
| 0x40E02 | 28 B | `monster_level_flag_overrides` — seven four-byte padded records with leading bytes `{0x80,0xC0,0,0,0xA0,0xA0,0x80}`. `monsters_everything` scans level-flags mask 0x73 one bit at a time and, for each set bit, copies the corresponding record's first byte over the parallel default 0x80 byte in its per-type stack configuration; the other three bytes of every record are padding. |
| 0x40E1E | 40 B | `monster_oddangle_table` — ten four-byte records in monster-index order, addressed by the `(object_type − 18) × 4` offset the monster loop keeps in `D6` (see `04_game_subsystems.md` §3.3). **Confidence: Verified** byte roles: **+0** is an attack-transition selector tested for zero and sign at 0x4143C (0 = family never takes that path; the negative 0xFF of Sorcerer/Super Sorcerer takes a separate route); **+1** is a rate mask ANDed with the frame byte at 0x413FA/0x41460, so the family acts only when `frame & mask` is zero; **+2** is both an animation-counter addend (0x41424) and, through its bit 0, the flag that drives entry into the attack state with picture 0x1709 (0x4146E–0x4148A); **+3** is the animation-counter addend used by the moving state (0x411C0). Values: Ghost `0E 06 80 00`, Grunt `00 06 40 40`, Demon `00 06 00 40`, Lobber `00 02 20 00`, Sorcerer `FF 06 FF 00`, Aux Grunt `00 06 40 40`, Death `00 06 40 E0`, Acid `00 02 00 00`, Super Sorcerer `FF 06 FF 00`, IT `01 02 00 00`. The former "per-type direction adjustment" summary described only part of the +2/+3 use. |
| 0x58C0A | 128 B | `anim_tiles_sorcerer` (Sorcerer/Super Sorc, 64 words) |
| 0x58F26 | 128 B | `anim_tiles_ghost` (64 words, verified) |
| 0x58FA6 | 128 B | `anim_tiles_grunt` (64 words, Grunt/Aux Grunt, verified) |
| 0x590A6 | 128 B | `anim_tiles_demon` |
| 0x591A6 | 128 B | `anim_tiles_lobber` |
| 0x592A6 | 128 B | `anim_tiles_death` |
| 0x59336 | 128 B | `anim_tiles_acid` |
| 0x59436 | 128 B | `anim_tiles_it` |
| 0x59026 | 128 B | `anim_tiles_grunt_moving` — shared by Grunt and Auxiliary Grunt |
| 0x59126 | 128 B | `anim_tiles_demon_moving` |
| 0x59226 | 128 B | `anim_tiles_sorcerer_moving` |
| 0x592B6 | 128 B overlapping view | `anim_tiles_death_moving_view` — biased 16 bytes into `anim_tiles_death`; the 64-word moving lookup deliberately continues through 0x59335 |
| 0x593B6 | 128 B | `anim_tiles_acid_moving` — exact range 0x593B6–0x59435 |
| 0x594B6 | 128 B | `anim_tiles_it_special` (IT chase state) |
| 0x595B6 | 128 B | `anim_tiles_lobber_throw` (Lobber throwing animation) |
| 0x59536 | 128 B | `anim_tiles_monster_special_attack` — 64-word direction/phase table selected by `monster_special_handler` for its non-lobber special attack state. |
| 0x59636 | 128 B | `anim_tiles_monster_special_state` — 64-word direction/phase table selected by two special-state branches in `monsters_everything`. |

The idle and moving pointer tables at 0x40DB2/0x40DDA each contain ten longwords in monster-index order: Ghost, Grunt, Demon, Lobber, Sorcerer, Auxiliary Grunt, Death, Acid, Super Sorcerer, IT. Idle aliases Sorcerer/Super Sorcerer and Grunt/Auxiliary Grunt. Moving aliases Grunt/Auxiliary Grunt and contains null pointers for Ghost, Lobber, Super Sorcerer, and IT; these zero entries are sentinel “no separate moving bank” values, not missing ROM pointers.

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

**Confidence: Verified** for ranges, dimensions, and player animation
consumers.

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x58070 | 32 B | `invisibility_flash_masks` | Sixteen words indexed by the invisibility timer phase (`timer >> 7`); values decay from 4 to 2 to 1 and the upper half remains 1. Exact range 0x58070–0x5808F. |
| 0x58090 | 4 W | `fighting_anim_end` | Per-player current threshold for attack animation end |
| 0x580A8 | 8 W | `player_speed_normal` | Movement speed per character (×2 for normal/powered modes) |
| 0x580B8 | 8 W | `player_anim_rate` | Animation rate divisor per character type |
| 0x580C8 | 8 W | `lobber_lead_distance` | Per-character target-lead distance scalar used by `monster_find_and_shoot` (0x419A6) to predict where the target player will move. Four normal entries `{96,112,96,128}` (Warrior, Valkyrie, Wizard, Elf) followed by four powered entries `{128,128,128,160}`; the firing path selects the powered half via the +8 at 0x41992. The lobber multiplies this scalar by the target's facing unit vector (`player_delta_x`/`player_delta_y`) and adds the result to the aim point. **Confidence: Verified** by disassembly — this table has exactly one consumer in the ROM, at 0x419A6, and is reached only through base 0x580FC. The former `player_collision_size` / "collision box dimensions" label was **Contradicted**: no collision-detection code reads this table, and the values rank like character movement speed, not box sizes. |
| 0x580D8 | 9 W | `player_delta_x` | Per-direction horizontal movement deltas `{0,+2,+2,+2,0,−2,−2,−2,0}` for directions 0–8. **Sole consumer is the lobber lead** at `monster_find_and_shoot` (0x419AC), which multiplies the entry for the *target's* facing direction by `lobber_lead_distance` (0x580C8) to project where the player will move; no player-movement code reads this table. The "movement deltas" label is accurate — these model player motion — but the reader is the lobber, not the player mover. Verified by disassembly: reached only via base 0x580FC−0x24. Element 8 exists because the direction fed in comes from `joystick_nibble_to_direction`, which returns 8 for no valid direction. |
| 0x580EA | 9 W | `player_delta_y` | Per-direction vertical movement deltas `{+2,+2,0,−2,−2,−2,0,+2,0}`, parallel to `player_delta_x`; same sole consumer (`monster_find_and_shoot` at 0x419B0, base 0x580FC−0x12 = **0x580EA**). |
| 0x580FC | 32 B | `joystick_nibble_to_direction` | Sixteen words mapping the high joystick-input nibble to direction 0–7; 8 means no valid direction. The nibble is **active-low**: `{8,8,8,8,8,7,1,0,8,5,3,4,8,6,2,8}` reproduces all eight compass directions. Used by player/thief/transporter movement—not a lobber sine/cosine table. |
| 0x5813C | 32 B | `forcefield_damage_table` | 8 longwords of forcefield contact damage; index `character + 4 × armor-power`. Charged only on a nonzero `check_forcefield_collision` return — see §5.3 |
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

## 9. Additional RAM Variables

**Confidence: Verified** for addresses, extents, and observed use. This
section is retained as a provenance grouping; its ranges also participate in
the complete §1 RAM map and generated operand checks.

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904A60 | 2 B | `monster_iter_ptr` | Current monster iteration pointer |
| 0x904A62 | 2 B | `monster_cull_h_origin` | Horizontal monster-culling origin, `(pf_hscroll - 0x17) << 7` |
| 0x904A64 | 2 B | `monster_cull_v_origin` | Vertical monster-culling origin, `(0xF9 - pf_vscroll_lo) << 7` |
| 0x904B42 | 2 B × 4 | `death_touch_timer` | Per-player Death touch sound timer (negative = new contact) |
| 0x904B4A | 2 B × 4 | `ff_hurt_timer` | Per-player forcefield hurt sound timer |
| 0x904B8E | 1 B | `eeprom_cache_stat1` | EEPROM cache for 0x904010 |
| 0x904B8F | 1 B | `eeprom_cache_stat2` | EEPROM cache for 0x90400E |
| 0x904B90 | 1 B | `eeprom_cache_stat3` | EEPROM cache for 0x904018 |
| 0x904B91 | 1 B | `eeprom_cache_stat4` | EEPROM cache for 0x904016 |
| 0x904B92 | 2 B | `eeprom_cache_stats` | EEPROM cache for 0x904B86 (game stats word) |
| 0x904B94 | 2 B | `eeprom_cache_settings` | EEPROM cache for 0x904A24 (game settings) |
| 0x9049EE | 2 B | `speech_counter` | Sound-board recovery holdoff (see §1.9); `sound_play` and `main_update_sound` stand down while nonzero |
| 0x9049F0 | 2 B | `sound_queue_state` | Reply buffer for status command 0x07; low three bits are the board's error report |
| 0x9049F2 | 2 B | `sound_idle_timer` | Countdown between sound CPU ping attempts |
| 0x9049F4 | 2 B | `sound_cpu_retry_count` | Sound CPU retry counter (reset > 180 = full reset) |
| 0x9048A0 | 2 B | `randwall_low_watermark` | Random wall low water mark |
| 0x9048A2 | 2 B | `randwall_target` | Random wall target index |
| 0x9048A4 | 2 B | `randwall_current` | Random wall current index |
| 0x9048A6 | 2 B | `randwall_timer` | Random wall timer (negative=disabled, 0=process, positive=countdown) |
| 0x910600 | 1 B × (tile_count/4) | `cycle_phase_assignments` | Color RAM Spare: cyclic wall phase assignment, 2 bits per tile |
| 0x905048 | 3072 B | `hud_mob_table` | HUD tile workspace arranged as 24 rows × 128 bytes (64 words), exact range 0x905048–0x905C47. Player HUD columns use row index `player*5 + field`; for example the IT overlay writes rows `player*5 + 8`. The following 12 bytes through 0x905C53 are padding before `tport_route_forward`. |
| 0x905054 | overlapping 24 × 128 B view | `path_direction_grid` | Gameplay/pathfinding view spanning exactly 0x905054–0x905C53, immediately before `tport_route_forward`. Cell `id` is `base + (id / 44) * 0x80 + (id % 44)`; each byte packs two direction+1 nibbles (0 means unset). Valid packed maze IDs are 0x000–0x3FF, so the highest reachable byte is 0x905BDF (ID 1023); row tails and the rest of the final padded row are not indexed. The view overlaps `hud_mob_table` and its following 12-byte pad. |
