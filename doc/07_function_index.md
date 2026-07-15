# Gauntlet II — Function Index

*Consolidated index of documented functions and callable entry points. Addresses are in the game ROM (0x040000–0x05FFFF) unless noted. Coverage includes conventional functions, callable leaves, shared-body entries, tail entries, and register/stack wrappers.*

## Callable-entry coverage audit

**Confidence: Verified.** All 321 unique documented game-ROM callable entries
are covered by the checked contract catalogs linked in this chapter. Those
catalogs state arguments, returns, and every convention exception found by
fresh body/caller analysis; the union is checked by
`generated/generate_callable_coverage.py`. Purpose-level naming alone was formerly
insufficient, but the completed contract pass now supplies the missing ABI
evidence.

The target audit does not rely on prologue bytes. The checked
[`generated/control_targets.csv`](generated/control_targets.csv) independently analyzes all 321
documented game entries plus the 80 unique destinations proven by the 12
computed-dispatch tables, and deduplicates overlapping bodies. Its 1,129
direct sites comprise 996 calls/jumps to documented game entries, 124 calls to
documented OS API slots, eight calls to the named RAM palette stubs, and the
single 0x40146 watchdog-abort JMP to 0x10000. The last target is mechanically
verified; hardware-map and exception-path evidence make the watchdog-reset
outcome a **Strong inference**. The report also verifies all 12
computed-PC dispatch sites against the tables in `05_data_reference.md`, the
reset-vector jump at 0x40494, and the null assertion at 0x43A18. There are zero
unclassified direct targets and zero analysis failures.

An independent exhaustive opcode search for register-indirect `jsr` sites found no game-ROM calls through A1, A5, or A6. The actual game-ROM cases are:

- **A0:** the callback argument of `thief_probe_axis` (0x4EE2A), whose callers pass a verified tile-probe routine, plus the deliberate `jsr (0)` assertion at 0x43A18 when more than 32 transporters are discovered;
- **A2/A3:** fixed addresses hoisted into a saved register for repeated calls, including OS text/drawing vectors and already named game helpers such as `getrandom`, `maze_randomplace`, and the tile-visibility predicates; and
- **A4:** the fixed `dragon_player_proximity` address loaded by `mob_collision_test` and reused by its object handlers.

The null assertion is not a callable entry. The report contains 192
register-indirect callable `JSR` sites (132 through A2, 52 through A3, seven
through A4, and one through A0), plus the separately classified A0 null
assertion. All other indirect destinations are
the same named entries reached directly elsewhere; no additional anonymous
wrapper or shared body is implied by the register call itself. The
leaf/BSR-only sweep is represented by the explicitly indexed non-`LINK`
entries below (including the path-grid helpers, transporter pair helpers,
collision-preserving wrappers, playfield register entries, and placement
tails).

*Note: Corrections from FIXME.md are applied inline with `> **Correction:**` callouts.*

---

## 1. Main Loop Functions (all DONE)

**Confidence: Verified** for entry addresses, frame-loop membership, purposes,
and the checked void/no-argument contracts below.

**Callable-contract confidence: Verified.** `m2mainloop` names 29 direct
callees: `one_time_init` once and 28 frame services. A whole-ROM direct-call
scan finds 37 call sites to these entries; the only alternate callers are
seven additional calls to `main_msgbox_countdown` and one to
`main_open_doors`. None consumes `D0` or condition codes. Per-entry radare2
body analysis finds no positive `A6` argument access in framed functions and
no entry-stack argument access in the five frameless entries. Thus all 29
have the semantic contract `void f(void)` at every identified direct caller.
They use the normal convention unless listed as an exception below.

The non-normal control-transfer cases in this group are:

- **Verified:** `m2mainloop` takes no arguments and never returns; it enters an
  infinite VBLANK-synchronized dispatch loop after `one_time_init`.
- **Verified:** `game_vblank` is an interrupt entry, not a C-callable function.
  It saves and restores `D0-D1/A0-A2`, takes its inputs from hardware and
  globals, returns no value, and exits with `RTE` at 0x4049E.
- **Verified:** `input_debounce` is a hand-written no-argument leaf.  It
  clobbers `D0`, preserves the other registers by not touching them, and exits
  with `RTS`; its caller consumes no return value.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x42A66 | `m2mainloop` | Main game loop entry point; VBLANK-synchronized frame dispatch |
| 0x4017E | `game_vblank` | Game-ROM VBLANK interrupt handler: acknowledge watchdog/VBLANK, publish scroll registers, increment the semaphore, update palette effects/timers, and run the per-frame interrupt-side hooks before restoring registers |
| 0x40528 | `main_cycle_tport_and_ffield` | Advance transporter and forcefield palette-cycle state |
| 0x42B6A | `coincheck` | Per-frame coin/start input and player-credit handling |
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

The machine-readable callable/body inventory is
[`generated/main_loop_contracts.csv`](generated/main_loop_contracts.csv).  Regenerate and verify
the call opcodes, all direct call sites, and stack-argument absence with
`python3 generated/generate_main_loop_contracts.py --check --run-check`.

### 1.1 Reset/VBLANK, orchestration, sound-ring, and alpha contracts

**Confidence: Verified.** These 32 entries are independently body-checked in
addition to the 29 frame-service contracts above. The audit added every active
six-byte header/trampoline veneer, the exception body, eight ROM-pointer
palette leaves, and the game-options hook body; zero-filled optional hook
slots remain data rather than callable entries.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x40000 | `game_start_veneer` | void | does not return | Tail veneer to 0x4014C |
| 0x40006 | `game_vblank_veneer` | interrupt frame | target returns with `RTE` | Tail veneer to 0x4017E |
| 0x4000C | `game_irq1_watchdog_trap` | interrupt frame | does not return | Self-JMP trap |
| 0x40012 | `game_irq3_watchdog_trap` | interrupt frame | does not return | Self-JMP trap |
| 0x40018 | `game_irq2_watchdog_trap` | interrupt frame | does not return | Self-JMP trap |
| 0x4001E | `game_irq6_sound_veneer` | interrupt frame | target returns with `RTE` | Tail-jumps through OS 0x17E to the sound receive IRQ body |
| 0x40024 | `game_exception_veneer` | D0.w action (OS supplies zero) | does not return | Tail veneer to 0x40140 |
| 0x40030 | `game_playfield_init_veneer` | void | void | Tail veneer to 0x44A82 |
| 0x40048 | `game_options_veneer` | void | void | Tail veneer to 0x5317C |
| 0x40054 | `game_rom_verify_veneer` | void | D0.l packed ROM/Slapstic verification result | Tail veneer to 0x56EAA |
| 0x400DE | `scroll_to_slot_veneer` | `uint16 packed_slot` | void | Preserves target stack ABI |
| 0x400E4 | `init_display_veneer` | `uint16 main_palette_index, uint16 special_palette_variant` | void | Preserves target stack ABI |
| 0x400EA | `maze_setup_veneer` | `const uint8_t *maze_record` | void | Preserves target stack ABI |
| 0x400F0 | `pf_replace_veneer` | `uint16 packed_slot, uint16 new_type` | void | Preserves target stack ABI |
| 0x400F6 | `mob_clear_veneer` | `uint16 mob_slot` | void | Preserves target stack ABI |
| 0x40140 | `game_exception_abort` | D0.w action (OS supplies zero) | does not return | Zero enters watchdog abort; nonzero falls into `game_start` |

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x4014C | `game_start` | void | does not return | OS reset entry through veneer 0x40000; sets SR and tail-jumps to `m2mainloop` |
| 0x4017E | `game_vblank` | interrupt frame only | no value; `RTE` | Saves/restores D0-D1/A0-A2; may instead take abort/reset-vector paths |
| 0x42A66 | `m2mainloop` | void | does not return | Infinite VBLANK-semaphore loop after one-time initialization |
| 0x42DC8 | `sound_system_reset` | void | void | Calls OS `reset_sound_cpu(0,0)`, installs grace state, and resets the ring |
| 0x4ADAE | `sound_queue_reset` | void | void | Frameless leaf; fills eight slots and clears byte indices |
| 0x4ADD6 | `enqueue_sound` | `uint8 sound_id` | void | Seven-entry capacity; silently drops on full |
| 0x4D12E | `alpha_clear_rect` | `uint16 column, uint16 width, uint16 row, uint16 height` | void | Exact word/row dimensions; 64-word row stride; zero dimensions write nothing |
| 0x404A0 | `palette_power_warrior` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x404AE | `palette_hurt_warrior` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x404BC | `palette_power_valkyrie` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x404D0 | `palette_hurt_valkyrie` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x404E4 | `palette_power_wizard` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x404F8 | `palette_hurt_wizard` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x4050C | `palette_power_elf` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x4051A | `palette_hurt_elf` | D0.w cycle offset, A1 source, A2 destination | void | ROM-pointer frameless leaf |
| 0x5317C | `game_options_display` | void | void | Passes descriptor stream 0x5318C to OS API 0x248 |

Machine-readable source:
[`generated/orchestration_sound_contracts.csv`](generated/orchestration_sound_contracts.csv),
regenerated and body-checked by
`python3 generated/generate_orchestration_sound_contracts.py --check --run-check`.

---

## 2. Initialization Functions

**Confidence: Verified** for entries, purposes, arguments, and returns through
the applicable generated contract catalogs.

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
| 0x431EE | `eeprom_periodic_write` / `eeprom_timer` | 10-minute periodic EEPROM write timer |
| 0x42D0A | `sound_response` | Processes responses from sound CPU via OS API |
| 0x42DF4 | `character_select_input_update` | For each player in status 0x10, decode the active-low direction bits into class 0–3 and redraw that HUD slot when the selection changes; it does not search for an unused class |
| 0x44A82 | `game_playfield_init` | OS-called playfield-init hook reached through fixed jump-table slot 0x40030: load the attract display tilemap, write words 0x5000–0x500F at 0x901480, and clear OS words reached through vectors 0x1D8/0x1DC |

---

## 3. Monster System

**Confidence: Verified** for entries, purposes, and checked monster/combat
contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x40E6A | `monsters_everything` | Entry point: per-frame monster AI, movement, shots, generators |
| 0x40FAE | `monster_loop_core` | Interior per-MOB loop entry; inherits the `monsters_everything` saved-register/local-stack frame |
| 0x41750 | `monster_find_and_shoot` | Find nearest player, set direction, maybe shoot |
| 0x41B16 | `find_unused_shot` | Find empty shot MOB slot |
| 0x490DC | `monster_create_shot` | Create a monster shot MOB at monster's position |
| 0x492C0 | `handle_generate` | Generator spawn routine called by `monster_loop_core`: probability/retry gate, scan eight neighboring cells through the padded 12-word direction tables at 0x57B50/68/80, require a traversable empty cell, then create the selected tiered monster |
| 0x49446 | `death_potion_score` | Select a floating-score variant and score from the parallel Death/potion tables using `death_hits & 7`; draw the popup and return the score |
| 0x49498 | `playfield_showscore` | Displays floating score popup over dying monster |
| 0x495A6 | `monster_playerhit` | Monster overlapping player: apply damage, play sounds |
| 0x49A3C | `death_damage_accumulate` | Add damage to one player's Death counter; above 200, start a transporter-cycle effect on the Death MOB and remove it |
| 0x49A98 | `player_hurt_speech_timer` | Decrement one player's randomized hurt-speech cooldown; on expiry choose a class-specific hurt voice, unless acid-slowed, then reload from the active-player-count timing table |
| 0x5FDE0 | `supersorc_place` | Find empty spot behind player, place Super Sorcerer |
| 0x5FDB8 | `supersorc_place_helper` | Thin wrapper that loads MOB array base pointers then calls supersorc_place |

### 3.1 Monster / shot-combat callable contracts

**Confidence: Verified** for all stack/register inputs, returns, condition-code
results, and exceptional entry conventions below.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x40E6A | `monsters_everything` | `uint16 first_mob_offset` | void | Frameless; saves `D2-D7/A2-A6` before reading the normal argument |
| 0x40FAE | `monster_loop_core` | `D2.w` current doubled MOB offset; `A2-A6` arrays; outer local stack | Continues outer iteration/epilogue | Interior branch entry |
| 0x4119A | `monster_special_handler` | `D2.w` current offset, `D4/D5` H/V state, `D6.w` type; `A2-A6` arrays; pushed type word | Continues outer iteration/epilogue | Interior branch entry |
| 0x414A4 | `monster_update_anim_tile` | `D2.w` current offset, `D6.w` animation-table selector; `A2` picture, `A6` state | Continues outer iteration/epilogue | Interior branch entry |
| 0x41750 | `monster_find_and_shoot` | `D2.w` current offset; `A2-A4` picture/H/V, `A6` state; caller-pushed monster type | void | BSR-only shared-stack entry; reads type at 8(A6) after `LINK` |
| 0x41B16 | `find_unused_shot` | `D4.w` initial doubled shot offset; `A2` picture array | `D4.w` selected offset; Z = free | BSR-only register entry |
| 0x41B52 | `monster_shooter_in_view` | `D4.b` horizontal, `D5.b` vertical | `D4.l=-1` in view or zero outside; Z reflects result | BSR-only register entry |
| 0x41B7E | `apply_direction_from_delta` | `D2.w` current, `D3.w` target, `D4/D5` current H/V; `A3/A4` H/V, `A6` state | void; writes direction bits | BSR-only register entry |
| 0x490DC | `monster_create_shot` | `uint16 monster_slot, uint16 direction, uint16 shot_slot` | void | — |
| 0x492C0 | `handle_generate` | `uint16 generator_slot, uint16 generated_type, uint16 spawn_probability` | void | — |
| 0x495A6 | `monster_playerhit` | `uint16 player_slot, uint16 monster_slot` | void | — |
| 0x40906 | `shot_mob_collision` | `uint16 shot_mob_slot, uint16 shooter_id` | `D0.w` target slot or `-1` | Frameless; reads arguments before saving `D2-D7/A2-A3` |
| 0x40A78 | `shot_collision_candidate_core` | Candidate/shooter/limits/self/coordinates in `D0-D7`; H/V/picture arrays in `A0-A2` | `D0.w` candidate; `D2.w` type/result or `-1`; N = reject | BSR-only register entry; exact roles in CSV |
| 0x4AF50 | `resolve_shot_hit` | `uint16 target_slot_or_playfield_code, uint16 shooter_id` | `D0.l=0` survives or `-1` consumed | — |
| 0x4AEA0 | `shot_onscreen_check` | `uint16 target_slot, uint16 horizontal_limit, uint16 vertical_limit` | `D0.l=-1` in range or zero outside | — |
| 0x53818 | `shot_reflect_calc` | `uint16 target_slot_or_playfield_code, uint16 shooter_id` | `D0.w` reflected direction | Computed-dispatch body |
| 0x5303A | `wall_crumble` | `uint16 packed_slot, uint16 damage` | `D0.l=-1` destroyed or zero remains | — |
| 0x54112 | `dragon_shot_hit` | `uint16 target_slot, uint16 shooter_id` | void | — |
| 0x54B68 | `dragon_shot_hitbox_adjust` | Candidate/limits/shot H/V in `D0/D3/D5/D6/D7` | `D0.w` candidate, +0x1000 on overlap | Register leaf; clobbers `D2/D6/A3` |
| 0x47DAE | `shot_impact_spawn` | `uint16 target_slot, uint16 shooter_slot` | void | — |

The checked machine-readable form is
[`generated/monster_combat_contracts.csv`](generated/monster_combat_contracts.csv); regenerate and
reanalyze all 20 bodies with
`python3 generated/generate_monster_combat_contracts.py --check --run-check`.

---

## 4. Player System

**Confidence: Verified** for entries, purposes, and checked lifecycle,
runtime, movement, collision, and path contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x43360 | `player_resetcounters` | Reset one player's counters (health, score unchanged, power-ups cleared) |
| 0x4341E | `player_resetall` | Reset all four player slots |
| 0x45866 | `player_it_label_set` | Draw "IT" in one player's HUD and play the character-specific announcement plus transfer/first-IT sound; the caller, not this helper, writes `ram.it_player` |
| 0x4590E | `player_it_label_clear` | Erase one player's two-tile IT label; the caller owns `ram.it_player` |
| 0x45ACA | `player_inv_update` | Draw one player's key/potion inventory row and six power-up icons from the per-player bitfield; demo mode suppresses the key/potion row but still refreshes power-up icons |
| 0x48754 | `speech_welcome` | Play "welcome <character>" speech for joining player |
| 0x487CA | `player_lowhealth` | Play a one-shot contextual low-health voice warning for one player; gated by `player_lowhealth_spoken` and the signed respawn/speech timer, then loads that timer with 0x0708 frames |
| 0x488CA | `player_coindrop` / `player_init_for_coin` | Initialize player slot when a coin is inserted |
| 0x48A36 | `player_join_finalize` | Finalize a successful join: optional coin initialization/config persistence, status and on-level state, join sound, HUD redraw, and welcome speech |
| 0x48BB6 | `player_join` | Byte-index outer wrapper: call `player_start_inner`, then `player_join_finalize` only when placement succeeds |
| 0x49D0E | `highscore_check` | Rank the player's score-per-coin through OS 0x1C6; load `player_state_timer` with 2700 frames for initials entry or 600 frames for GAME OVER |
| 0x4D900 | `player_activecount` | Return the count of player statuses 1, 2, 8, or 0x10; statuses 0, 4, 0x20, and other values are excluded |
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
| 0x5DE44 | `moblist_remove_and_clear_regs` | Register-state unlink-and-clear entry: repair both links, the global head, and bucket heads, then zero all five slot words |
| 0x5DED4 | `moblist_unlink_regs` | Register-state unlink entry used by `moblist_remove`: repair forward/back links and list heads, then preserve the removed slot's upper object-state bits rather than clearing its five array words |
| 0x49DE6 | `player_death_sequence` | Per-frame death/name-entry handler; decrements the reused `player_state_timer` countdown |
| 0x54FE8 | `secret_name_entry_update` | Per-frame secret-winner name editor selected by `ram.secret_player`; builds and displays the completed secret code |
| 0x50E34 | `player_damage_sample_update` | Advance one player's 60-frame damage sample, low-health dialog/voice, and pending/average damage bookkeeping |
| 0x47FAC | `open_timed_doors` | Remove every active type-0x0D/0x0E door object and play sound 0x12 (`Doors Open`) when the idle timer expires |

### 4.1 EEPROM/configuration and player-lifecycle callable contracts

**Confidence: Verified.** Each row is checked against a freshly analyzed body;
the catalog records every direct control-transfer site. Empty exception cells
use the normal convention from §3.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x42DF4 | `character_select_input_update` | void | void | — |
| 0x42F86 | `eeprom_load_config` | void | void | Uses fixed OS EEPROM services 0x184 and 0x24E |
| 0x43192 | `eeprom_write` | void | void | Uses fixed OS EEPROM service 0x24E |
| 0x431EE | `eeprom_periodic_write` | void | void | — |
| 0x43360 | `player_resetcounters` | `uint16 player_index` | void | — |
| 0x4341E | `player_resetall` | void | void | — |
| 0x44C7E | `show_continue_prompt` | void | void | Calls fixed `draw_string` through A2=0x25A |
| 0x452D0 | `setup_infopanel` | `int16 player_selector` (`-1` = whole panel) | void | Calls fixed services through A2=0x25A and A3=0x142 |
| 0x48754 | `speech_welcome` | `uint16 player_index` | void | — |
| 0x488CA | `player_coindrop` | `uint16 player_index` | void | — |
| 0x489B8 | `remove_dying_player_sprites` | `uint16 player_index` | void | — |
| 0x48A36 | `player_join_finalize` | `uint16 player_index` | void | — |
| 0x48BB6 | `player_join` | `uint8 player_index` | void | Reads the low byte of the first normal stack slot at A6+0xB |
| 0x48BEC | `player_start_inner` | `uint16 player_index` | D0.l=-1 on successful placement/MOB initialization; 0 when no spawn position is usable | — |
| 0x49DE6 | `player_death_sequence` | `uint16 player_index` | void | — |
| 0x4A2CA | `draw_player_initials_entry` | `uint16 player_index` | void | — |
| 0x4D1A4 | `secret_bonus_earned` | void | D0.l=-1 when challenge progress earns the secret-room coin bonus; 0 otherwise | — |
| 0x4D476 | `show_level_end_bonus_screen` | void | void | Calls fixed `draw_string` through A3=0x25A |
| 0x4D900 | `player_activecount` | void | D0.l=0..4 count of statuses 1, 2, 8, or 0x10 | — |

Machine-readable source:
[`generated/player_lifecycle_contracts.csv`](generated/player_lifecycle_contracts.csv), regenerated
and body-checked by
`python3 generated/generate_player_lifecycle_contracts.py --check --run-check`.

### 4.2 Player movement / collision callable contracts

**Confidence: Verified** for caller locations, stack/register inputs, and
returns below. The four door-traversal rows are a **Strong inference** only for
the semantic interpretation “zero = path handled”; their shared-stack input
and Z-consuming callers are verified. Normal stack-ABI rows have no convention
exception.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x41BF0 | `player_try_move` | `uint16 player_index, int16 delta, uint16 movement_flags` | `D0.w` movement result; `0x00F0` = no movement | Frameless; saves `D2-D7/A2-A6` before reading normal arguments |
| 0x41C30 | `player_try_move_core` | `D0.w` doubled player index, `D6.w` delta, `D7.w` flags; `A2-A4` MOB arrays | `D0.w` movement result | Internal register-state reentry |
| 0x42648 | `tile_lookup_core` | `D1.w` candidate offset, `D2.w` current offset, `D3/D4` coordinates; `A2-A4` arrays | Carry = blocking; retains `D1` | BSR-only register entry |
| 0x425D0 | `probe_up` | `D2.w` current offset, `D3/D4` coordinates; `A2-A4` arrays | `D1.w` candidate; carry = blocked | Register entry; may tail-branch to tile core |
| 0x4260C | `probe_down` | Same as `probe_up` | `D1.w` candidate; carry = blocked | Register entry; may tail-branch to tile core |
| 0x426D4 | `probe_left` | Same as `probe_up` | `D1.w` candidate; carry = blocked | BSR-only register entry |
| 0x4270C | `probe_right` | Same as `probe_up` | `D1.w` candidate; carry = blocked | BSR-only register entry |
| 0x42744 | `squeeze_through_check` | `D1.w` candidate, `D2.w` current, `D5.w` doubled player; `A3` H-position array | `D0.l` boolean; Z reflects result | Register entry |
| 0x4FEB2 | `corner_squeeze_geometry` | `uint16 packed_slot, uint16 player_index` | `D0.l` boolean | — |
| 0x406B6 | `mob_probe_up` | `uint16 mob_slot` | `D0.w` blocking slot, `-1`, or boundary sentinel `0x0400` | Frameless stack leaf |
| 0x40732 | `mob_probe_down` | `uint16 mob_slot` | `D0.w` blocking slot, `-1`, or boundary sentinel `0x0400` | Frameless stack leaf |
| 0x4083A | `mob_probe_left` | `uint16 mob_slot` | `D0.w` blocking slot or `-1` | Frameless stack leaf |
| 0x408A0 | `mob_probe_right` | `uint16 mob_slot` | `D0.w` blocking slot or `-1` | Frameless stack leaf |
| 0x407A6 | `mob_probe_candidate` | `D1.w` candidate, `D2.w` current; `A0-A2` V/H/picture arrays | Carry = blocking; updates distance scratch | BSR-only register entry |
| 0x52192 | `mob_collision_test` | `uint16 candidate_slot, uint16 player_index` | `D0.l` boolean | — |
| 0x42598 | `mob_collision_test_preserve_d1_a` | `D1.w` candidate, `D5.w` doubled player | `D0.l` boolean; Z reflects result; preserves `D1` | Register wrapper |
| 0x425B4 | `mob_collision_test_preserve_d1_b` | Same as prior row | Same as prior row | Register wrapper |
| 0x4280E | `door_traverse_right` | `D2.w` current; `A2-A4` arrays; caller-saved `D5` coordinate | `D0.w` status; caller consumes Z | Register/shared-caller-stack entry |
| 0x428A4 | `door_traverse_left` | Same as prior row | Same as prior row | Register/shared-caller-stack entry |
| 0x4293A | `door_traverse_up` | Same as prior row | Same as prior row | Register/shared-caller-stack entry |
| 0x429D0 | `door_traverse_down` | Same as prior row | Same as prior row | Register/shared-caller-stack entry |
| 0x427B4 | `failed_door_post` | `D2.w` current, `D4-D7` coordinates/state; `A2-A4` arrays | void | BSR-only register entry |
| 0x5E35E | `ray_march_right` | `D2.w` current, `D3.w` clearance, `D4/D5` coordinates; `A2-A4` arrays | `D1.w` candidate or `-1`; N = failure; failure sets D2 bit 31 | Register entry |
| 0x5E2A2 | `ray_march_left` | Same as prior row | Same as prior row | Register entry |
| 0x5E1D8 | `ray_march_up` | Same as prior row | Same as prior row | Register entry |
| 0x5E10C | `ray_march_down` | Same as prior row | Same as prior row | Register entry |

The checked machine-readable form is
[`generated/player_collision_contracts.csv`](generated/player_collision_contracts.csv); regenerate
and reanalyze all 26 bodies with
`python3 generated/generate_player_collision_contracts.py --check --run-check`.

### 4.3 Player-runtime and name-entry callable contracts

**Confidence: Verified.** Each body below is freshly analyzed with the
configured 68010 loader, and the catalog records every discovered direct
control-transfer site. Normal rows use the stack ABI from §3; exception cells
also distinguish presentation-only helpers and global-selector entries.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x45866 | `player_it_label_set` | `uint16 player_index` | void | Presentation helper only; caller owns `ram.it_player` |
| 0x4590E | `player_it_label_clear` | `uint16 player_index` | void | Presentation helper only; caller owns `ram.it_player` |
| 0x45ACA | `player_inv_update` | `uint16 player_index` | void | — |
| 0x45BE8 | `string_length` | `const char *string` | D0.l = byte length excluding NUL | — |
| 0x47FAC | `open_timed_doors` | void | void | — |
| 0x487CA | `player_lowhealth` | `uint16 player_index` | void | — |
| 0x49446 | `death_potion_score` | `uint16 doubled_death_mob_offset` | D0.l = selected score | — |
| 0x49A3C | `death_damage_accumulate` | `uint16 player_index, uint16 death_mob_slot, uint32 damage` | void | — |
| 0x49A98 | `player_hurt_speech_timer` | `uint16 player_index` | void | — |
| 0x49B44 | `ascii_to_alpha_glyph` | `uint8 ascii_char` | D0.l = alpha glyph | Reads low byte at A6+0xB |
| 0x4A44A | `name_entry_draw_large_char` | `uint16 column, uint16 row, uint8 character, uint16 color` | void | Fixed OS services 0x224/0x20C |
| 0x50E34 | `player_damage_sample_update` | `uint16 player_index` | void | — |
| 0x511AC | `player_tile_interact` | `uint16 tile_mob_slot, uint16 player_index` | D0.l=-1 handled/consumed; 0 unhandled | Calls `sound_play` through fixed A2=0x4AD76 |
| 0x53666 | `player_create_shot` | `uint16 player_index` | void | — |
| 0x54FE8 | `secret_name_entry_update` | void | void | Selects player through `ram.secret_player` |
| 0x55440 | `name_entry_step_char` | `uint8 current_char, int16 direction, uint8 allow_backspace` | D0.l = wrapped next character | Byte arguments at A6+0xB/A6+0x13 |
| 0x554B6 | `name_entry_draw_char` | `uint16 column, uint16 row, uint8 character, uint16 color` | void | Fixed OS service 0x218 |
| 0x5554E | `name_entry_step_char_copy` | Same as 0x55440 | Same as 0x55440 | Byte-identical copy; no discovered direct site |
| 0x555C4 | `name_entry_draw_char_copy` | Same as 0x554B6 | void | Byte-identical copy; no discovered direct site |

Machine-readable source:
[`generated/player_runtime_contracts.csv`](generated/player_runtime_contracts.csv), regenerated
and body-checked by
`python3 generated/generate_player_runtime_contracts.py --check --run-check`.

---

## 5. Maze / Level System

**Confidence: Verified** for entries, purposes, and checked maze/Slapstic
contracts; explicitly noted semantic parameter labels remain **Strong
inference**.

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

### 5.1 Maze / Slapstic callable contracts

**Confidence: Verified** for caller locations, stack offsets, returns, and
exceptional conventions below, except the semantic names of
`maze_place_object`'s first and third arguments, which remain a **Strong
inference**. Normal rows use the stack ABI from `03_game_rom_structure.md`;
only exceptions are called out.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x40C78 | `find_maze` | Maze number in its wrapper caller's first longword | `D1.w` bank offset; writes `ptr_maze_data` | Frameless shared-stack helper; reads 8(A7) after the wrapper's nested JSR |
| 0x40CC4 | `maze_select_alt_bank` | `uint32 maze_number` | void | Frameless wrapper; `find_maze` consumes its argument |
| 0x40CF2 | `maze_init` | `uint32 maze_number` | void | Frameless wrapper; `find_maze` consumes its argument |
| 0x40D24 | `load_level_tileset` | `uint32 maze_number` | void | Frameless wrapper; `find_maze` consumes its argument |
| 0x40D4E | `maze_select_bank_special` | `uint32 maze_number` | void | Frameless wrapper; `find_maze` consumes its argument |
| 0x44AC2 | `maze_setupnew` | `const uint8_t *maze_record` | void | — |
| 0x4C1BC | `maze_decode` | `const uint8_t *maze_record` | void | — |
| 0x45E40 | `maze_place_object` | `uint16 slot_or_offset, uint16 object_type, uint16 scan_base` | void | — |
| 0x43F68 | `maze_addrandompickups` | `uint16 enable_random_pickups` | void | — |
| 0x42E9A | `maze_randomplace` | `uint16 object_type` | packed slot in `D0.l` | — |
| 0x4526A | `maze_show` | void | void | — |
| 0x4529A | `maze_hide` | void | void | — |
| 0x452D0 | `setup_infopanel` | `int16 player_selector` (`-1` = whole panel) | void | — |
| 0x462AE | `dragon_reserve_footprint_cell` | `uint16 packed_slot` | void | — |
| 0x4631C | `maze_tile_write_at` | `uint16 packed_slot, uint16 object_type, uint16 span_length` | void | — |
| 0x52ECA | `maze_checknum` | void | void | — |
| 0x4BE24 | `level_splash` | void | void | — |
| 0x438AE | `maze_new_level_setup` | void | void | — |
| 0x436FE | `maze_load_pickup_config` | `const uint8_t *maze_record` | void | — |
| 0x436CC | `get_random_maze_flags` | void | `uint32 level_flags` in `D0.l` | — |
| 0x43D8C | `maze_scan_objects` | `int16 scan_mode` | void | — |
| 0x43826 | `slapstic_cmd_bitwise` | void | void | — |
| 0x56E58 | `slapstic_cmd_bank0` | void | void | Clobbers `D0`; saves/restores `SR` |
| 0x56E6E | `slapstic_cmd_bank3` | void | void | Clobbers `D0`; saves/restores `SR` |
| 0x56E84 | `slapstic_cmd_bankX` | `D0.w` selector offset, `A0` bank-select base | void | Register arguments |
| 0x56E90 | `slapstic_cmd_maze_init` | `A0` source, `A1` destination; `D0` dummy bus value | void | Register arguments; branches to shared 0x56E54 tail |
| 0x56E98 | `slapstic_cmd_bankX_special` | `D0.w` selector offset, `A0` bank-select base | void | Register arguments |
| 0x56EAA | `slapstic_verify` | void | packed status/sums in `D0.l`; success = 0x0001FFFE | — |
| 0x46C5E | `scroll_to_slot` | `uint16 packed_slot` | void | — |
| 0x46F56 | `set_scroll_pos` | `int16 horizontal, int16 vertical` | void | — |

The checked machine-readable form is
[`generated/maze_contracts.csv`](generated/maze_contracts.csv); regenerate and reanalyze all 30
bodies with `python3 generated/generate_maze_contracts.py --check --run-check`.

---

## 6. Transporter / Forcefield System

**Confidence: Verified** for entries, purposes, route formats, and checked
contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x47CFE | `handle_tport` | Player touching transporter: create explosion anim, hide player |
| 0x47C0E | `tport_cycle_start` / `spawn_passage_marker` | Initialize transporter animation MOB at frame 0x924 |
| 0x47DAE | `shot_impact_spawn` | Spawn an impact/explosion at the target using the first free effect MOB in 0x0D–0x10. If all four are occupied it selects 0x0D + (`shooter_slot` & 3), preserves an active 0x924–0x95A transporter effect, and otherwise replaces that channel. Called throughout `resolve_shot_hit`. (Formerly listed as `tport_cycle_update`/`spawn_explosion`.) |
| 0x4E7C0 | `tport_find_id` | Search tport_pos_table for entry matching given maze position |
| 0x50ADE | `tport_check_dest` | Validate potential transport destination |
| 0x5DF8E | `tport_create_splodey` | Create sparkle/explosion animation at teleport destination |
| 0x5FC5E | `pf_isff` | Check if given maze coordinate has a forcefield tile |
| 0x40528 | `main_cycle_tport_and_ffield` | Per-frame forcefield/transporter palette cycling |
| 0x53398 | `forcefield_segments_setup` | Scan FORCEFIELDHUB (type 0x3F) tiles, encode segment/graphic state in `mob_state_link`, and build the forcefield segment table at 0x910780 |
| 0x53346 | `check_forcefield_collision` | Test whether player is touching a forcefield |
| 0x52F26 | `maze_forcefield_setup` | Pack groups of four maze object types 7–9 into the spare-color byte table; clear the corresponding hidden marker MOBs and disable the level feature if none were present |
| 0x52FBE | `consume_forcefield_code` | Return code 1–3 for maze object types 7–9 and clear that marker's picture/position/link fields; return 0 for every other type |

### 6.1 Transporter / forcefield callable contracts

**Confidence: Verified** for all stack/register inputs, returns, and exceptional
entry conventions below.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x47C0E | `tport_cycle_start` | `uint16 source_mob_slot, uint16 animation_channel` | void | — |
| 0x47CFE | `handle_tport` | `uint16 source_mob_slot, uint16 animation_channel` | void | — |
| 0x4E684 | `tport_route_connect` | `uint16 source_pos, uint16 destination_pos, uint16 approach_pos` | void | — |
| 0x4E73A | `tport_route_connect_if_empty` | Same three packed-position arguments | void | — |
| 0x4E7C0 | `tport_find_id` | `uint16 packed_maze_pos` | `D0.l`: one-based ID; `level_tport_count+1` when absent | — |
| 0x50224 | `player_tport` | `uint16 transporter_pos, uint16 player_index` | void | — |
| 0x50616 | `tport_player_flash` | `uint16 player_index` | void | — |
| 0x50662 | `tport_player_move` | `uint16 player_index` | void | — |
| 0x50ADE | `tport_check_dest` | `uint16 destination_mob_slot, uint16 player_index` | `D0.l=1` blocked, zero usable | — |
| 0x50B88 | `tport_restore_player_picture` | `uint16 player_index` | void | — |
| 0x5107A | `tport_route_write_pair` | `uint16 forward_id, uint16 reverse_id, uint32 forward_reverse_words` | void | Frameless leaf; third argument contains both words |
| 0x510BC | `tport_route_read_pair` | `uint16 forward_id, uint16 reverse_id` | Packed forward/reverse words in `D0.l` | Frameless leaf |
| 0x52F26 | `maze_forcefield_setup` | void | void | Calls `consume_forcefield_code` four times through `A2` |
| 0x52FBE | `consume_forcefield_code` | `uint16 marker_mob_slot` | `D0.l=1..3`, or zero | — |
| 0x53346 | `check_forcefield_collision` | `uint16 packed_maze_pos` | `D0.l=1` on forcefield, zero otherwise | — |
| 0x53398 | `forcefield_segments_setup` | void | void | — |
| 0x5DF5A | `mob_place_tport_anim` | `uint16 source_mob_slot, uint16 animation_channel` | void | Frameless entry branches into shared depth-list body after adding 0x0D to channel |
| 0x5DF8E | `tport_create_splodey` | Same two arguments | void | Frameless entry branches into shared depth-list body after adding 0x19 to channel |
| 0x5FC56 | `pf_isff_d0` | `D0.w` packed maze position | `D0.l=1` on segment, zero otherwise | Register entry sharing `pf_isff` body |
| 0x5FC5E | `pf_isff` | `uint16 packed_maze_pos` | `D0.l=1` on segment, zero otherwise | Frameless stack entry eight bytes after `pf_isff_d0`; own save frame, shared body at 0x5FC66 |

The checked machine-readable form is
[`generated/tport_forcefield_contracts.csv`](generated/tport_forcefield_contracts.csv); regenerate
and reanalyze all 20 entries plus the common depth-list body with
`python3 generated/generate_tport_forcefield_contracts.py --check --run-check`.

---

## 7. Dragon System

**Confidence: Verified** for entries, purposes, and checked proximity,
movement, segment, and shot contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x54454 | `main_handle_dragon` | Dragon state machine (sleeping/awake/stunned/turning/fire) |
| 0x549EA | `dragon_player_proximity` | Check if any player is in aggro range; start wake animation |
| 0x5496E | `dragon_setup_segments` | Derive and store all four 2×2 dragon segment MOB IDs from the primary cell and initialize dragon state/facing/movement/hit counters |
| 0x54748 | `dragon_fire_setup` | Fires one dragon fireball: sets fire cooldown (0x90487C) = 8, picks the origin segment MOB via table 0x5D4B8[pose+facing*2] from `dragon_seg_mob_ids` (0x904894), stores shot direction = facing |
| 0x53E4A | `dragon_choose_move_direction` | Compare the dragon with active players, test candidate maze cells, and update packed movement state/facing toward the best unobstructed direction |
| 0x53D10 | `dragon_update_segments` | Use the current path-program pose and facing to update the four dragon segment MOB positions/pictures |
| 0x540E8 | `dragon_find_free_shot_slot` | Scan physical dragon-shot MOB slots 8 down to 5 and return logical subslot 4 down to 1 for the first empty picture (0 if none) |

---

## 8. Thief / Mugger System

**Confidence: Verified** for entries, purposes, and checked thief-state,
collision, route, and transport contracts.

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
| 0x510BC | `tport_route_read_pair` | Leaf helper: return the selected forward route word in `D0` bits 31–16 and reverse route word in bits 15–0; a zero ID leaves its half zero |
| 0x4E7FC | `thief_test_move_tile` | Validate the thief's next tile, including transporter entry, blocked-direction tests, and corner-squeeze handling |
| 0x4EE0A | `thief_probe_axis` | Invoke a directional tile-probe callback, reject blocked/colliding results, and apply the supplied coordinate delta to the thief MOB |
| 0x4F5C8 | `thief_remove_and_drop_loot` | Remove the thief/effect MOBs, award 500 points when appropriate, restore route state, and respawn carried loot at the departure tile |
| 0x4F742 | `thief_handle_tile_collision` | Handle thief contact with players, shots, obstacles, and transporter tiles; applies contact damage and returns whether movement is blocked |
| 0x4FAD4 | `thief_enter_tport` | Select the linked transporter destination and route direction for the thief, then start the transporter transition when the destination is usable |
| 0x4FBFC | `thief_start_tport_anim` | Hide/remove the thief at a transporter, create its transition MOB, record source/destination state, and start the teleport sound/animation |
| 0x4E122 | `thief_exit` | Thief departure: animate exit, remove MOB, schedule next appearance |

---

## 9. Exit System

**Confidence: Verified** for entries, purposes, lookup/index semantics, and
checked transition/animation contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x52B06 | `exit_get_id` | Return the zero-based index of a packed position in `exit_pos_table`, or `level_exit_count` when absent |
| 0x52B40 | `player_exit_sequence` | Player exiting state machine; advance to next level when all done |
| 0x5DF80 | `exit_create_player_anim` | Create player exit animation MOB |

### 9.1 Dragon / thief / exit callable contracts

**Confidence: Verified** for all stack/register inputs, returns, and exceptional
entry conventions below. `main_handle_dragon`, `main_thief_anim`, and
`main_exit_move` were already present in the checked no-argument main-loop
batch; they are repeated here because this pass verifies their subsystem
bodies in more detail.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x54454 | `main_handle_dragon` | void | void | — |
| 0x549EA | `dragon_player_proximity` | `uint16 previous_pos, uint16 current_pos` | void | — |
| 0x5496E | `dragon_setup_segments` | `uint16 primary_dragon_mob_slot` | void | — |
| 0x54748 | `dragon_fire_setup` | `uint16 shot_mob_slot, uint16 variant_flag` | void | — |
| 0x53E4A | `dragon_choose_move_direction` | void | void | — |
| 0x53D10 | `dragon_update_segments` | void | void | — |
| 0x540E8 | `dragon_find_free_shot_slot` | void | `D0.l`: subslot 1–4, or zero | — |
| 0x54AF8 | `dragon_any_segment_near_screen` | void | `D0.l=-1` if any segment is near, zero otherwise | Four indirect calls through `A2` |
| 0x4DFF6 | `thief_target_calc` | void | void | — |
| 0x4E122 | `thief_exit` | void | void | — |
| 0x4E1FE | `thief_steal_from_player` | `uint16 player_index` | `D0.l=1` applied, zero suppressed | — |
| 0x4E432 | `thief_setup` | void | void | — |
| 0x4E4D8 | `thief_timer_set` | void | void | — |
| 0x4E7FC | `thief_test_move_tile` | `uint16 candidate_pos, uint16 object_type` | Nonzero if transporter/corner handling consumes the move; zero otherwise | — |
| 0x4E8DC | `main_thief_anim` | void | void | — |
| 0x4EE0A | `thief_probe_axis` | Probe callback, position-array base, signed coordinate delta | `D0.l`: candidate MOB slot or `-1` | Calls callback through `A0`; exact types in CSV |
| 0x4EE7A | `thief_move_engine` | Move flags and biased H/V deltas | `D0.l`: collision-direction code plus blocked-axis flag | Exact fields in CSV |
| 0x4F5C8 | `thief_remove_and_drop_loot` | `int16 score_player_or_minus1, uint16 replacement_mob_slot_or_zero` | void | — |
| 0x4F742 | `thief_handle_tile_collision` | `uint16 candidate_mob_slot` | `D0.l=-1` handled/blocked, zero clear | — |
| 0x4F912 | `thief_compute_path` | void | void | — |
| 0x4FAD4 | `thief_enter_tport` | `uint16 transporter_pos` | `D0.l=-1` transition started, zero rejected | Four indirect route-pair reads through `A2` |
| 0x4FBFC | `thief_start_tport_anim` | `uint16 destination_pos` | void | — |
| 0x5287C | `main_exit_move` | void | void | — |
| 0x52B06 | `exit_get_id` | `uint16 packed_exit_pos` | Zero-based index or `level_exit_count` | — |
| 0x52B40 | `player_exit_sequence` | `uint16 player_index, uint16 exit_mob_slot, uint16 exit_type` | void | — |
| 0x5DF80 | `exit_create_player_anim` | `uint16 source_mob_slot, uint16 animation_channel` | void | Frameless entry adds 0x15 to channel and branches into shared depth-list body |

The checked machine-readable form is
[`generated/dragon_thief_exit_contracts.csv`](generated/dragon_thief_exit_contracts.csv);
regenerate and reanalyze all 26 entries plus the common depth-list body with
`python3 generated/generate_dragon_thief_exit_contracts.py --check --run-check`.

---

## 10. Scoring / Coin / Dialog System

**Confidence: Verified** for entries, purposes, score/coin arithmetic, dialog
selection, and checked contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x42B6A | `coincheck` | Per-frame coin detection; handle player joining/coining |
| 0x40628 | `calc_score_per_coin` | Divide 32-bit value by 16-bit divisor for score-per-coin display |
| 0x49498 | `playfield_showscore` | Floating score popup over killed monster |
| 0x49D0E | `highscore_check` | Check if score ranks in top 10; set name-entry state |
| 0x4C440 | `dialog_first_encounter` | First-encounter dialogs (bitmasked per encounter type); returns whether the selected record has speech |
| 0x4C70A | `dialog_clear_message` / `fill_buffer_spaces` | Fill dialog message buffer with spaces then null terminator |
| 0x4C72A | `player_give_item_with_message` | Give power-up item; display associated dialog message |
| 0x4CB50 | `dialog_position_box` / `compute_screen_coords` | Position dialog box near player or at center |
| 0x4D476 | `show_level_end_bonus_screen` | Clear the alpha display, calculate and render ordinary treasure-room or secret-room coin bonuses, remove departing sprites, restore secret-room state, and advance to the saved maze/level |
| 0x4A124 | `attract_highscores` | Shows 4-way-split high-score-per-coin attract screen |
| 0x44C7E | `show_continue_prompt` | When no level players remain and all statuses are empty/selecting, draw the six-line PRESS START/WITHIN/TO CONTINUE prompt and seed title state; it does not decrement the active-player count |

**Confidence: Verified** for caller locations, stack offsets, returns, and
exceptional conventions below. Normal rows use the stack ABI from
`03_game_rom_structure.md`; only exceptions are called out.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x40628 | `calc_score_per_coin` | `uint32 score, uint16 coin_count` | Unsigned 32-bit quotient in `D0.l` | Frameless two-stage 68000 32/16 division leaf |
| 0x42B6A | `coincheck` | void | void | — |
| 0x452D0 | `setup_infopanel` | `int16 player_selector` (`-1` = whole panel) | void | — |
| 0x457C0 | `main_score_display` | void | void | — |
| 0x45940 | `draw_player_score` | `uint16 player_index` | void | — |
| 0x459A2 | `draw_player_health` | `uint16 player_index` | void | — |
| 0x4715E | `main_score_update` | void | void | — |
| 0x488CA | `player_coindrop` | `uint16 player_index` | void | — |
| 0x48B58 | `update_monster_bonus_from_score_per_coin` | void | void | — |
| 0x49498 | `playfield_showscore` | `uint16 source_mob_slot, uint16 popup_type_index` | void | — |
| 0x49BD0 | `highscore_table_init` | void | void | — |
| 0x49D0E | `highscore_check` | `uint16 player_index` | void | — |
| 0x4A124 | `attract_highscores` | void | void | Calls the fixed OS display service indirectly through `A2=0x200` |
| 0x4A2CA | `draw_player_initials_entry` | `uint16 player_index` | void | — |
| 0x4AD4E | `sound_speech_play` | `uint8 sound_id` | void | — |
| 0x4AD76 | `sound_play` | `uint8 sound_id` | void | — |
| 0x4C440 | `dialog_first_encounter` | `uint16 player_index, uint32 encounter_mask, [uint16 numeric_value]` | `D0.l=1` when record has speech, else 0 | Third argument is read only for the numeric-message record; other callers pass two arguments |
| 0x4C70A | `dialog_clear_message` | `int16 last_character_index` | void | — |
| 0x4C72A | `player_give_item_with_message` | `uint16 player_index, uint16 item_index` | `D0.l=1` newly granted, 0 already owned | — |
| 0x4CB50 | `dialog_position_box` | `int16 player_index_or_minus1` | void | — |
| 0x4CCBC | `main_msgbox_countdown` | void | void | — |
| 0x4D1A4 | `secret_bonus_earned` | void | `D0.l=-1` when challenge progress earns the secret-room coin bonus, else 0 | — |
| 0x4DE76 | `score_screen_color_cycle` | void | void | — |
| 0x5214C | `player_add_score_with_mult` | `uint16 player_index, uint16 base_score` | void | — |

The checked machine-readable form is
[`generated/score_coin_dialog_contracts.csv`](generated/score_coin_dialog_contracts.csv);
regenerate and reanalyze all 24 entries with
`python3 generated/generate_score_coin_dialog_contracts.py --check --run-check`.

---

## 11. Secret Room System

**Confidence: Verified** for entries, purposes, and checked secret-state/name
contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x486FE | `secret_check` **(RESOLVED)** | Level-transition secret-room bookkeeping: if a player entered the secret room, `secret_prev_maze` = maze# and interval 0x90487A += 15 (max 40); if nobody did, −2 (min 4); countdown 0x904878 reloaded. Called from `main_start_game` (0x480EC) and the `show_level_end_bonus_screen` epilogue (0x4D8DC). `update_bgm_volume` refuted (no sound state touched) |
| 0x54EC6 | `secret_getname` **(RESOLVED)** | Secret-room winner name-entry setup, gated by EEPROM settings bit 13: name buffer 0x904AA4 = 'A'+spaces, `player_status` = 0x20, draws "ENTER YOUR" / "'LAST-NAME FIRST-NAME'"; bit clear → status 2, short delay. `reset_attract_player` refuted |
| 0x54BE0 | `secret_code_build` | Build the six-character `XXX-XXX` secret code in `dialog_msg_buf`: CRC-CCITT-hash the entered name while skipping spaces, interleave three hash symbols with three symbols encoding the previous maze/trick/challenge tuple, and map 5-bit groups through the alphabet at 0x54CA6 |

### 11.1 Final thief-state and secret-room callable contracts

**Confidence: Verified.** This seven-row catalog completed the original
294-entry contract set and corrects four misleading thief helper names. The
later ROM-byte closure sweep added 27 shipped veneers, pointer-installed
leaves, and dormant/legacy entries; the current union is 321/321 as stated at
the start of this chapter.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x486FE | `secret_check` | void | void | Level-transition global bookkeeping only |
| 0x4E172 | `thief_end_dodge` | void | void | Clears dodge bit 3, flips low mode bits, and repairs route state when active |
| 0x4E1B8 | `thief_begin_dodge` | void | void | Sets dodge bit 3, flips low mode bits, and repairs route state when active |
| 0x4E630 | `thief_track_victim_move` | `uint16 new_packed_pos, uint16 player_index` | void | Updates only for the current victim and a changed position |
| 0x4FCF0 | `thief_find_aligned_shooter` | void | D0.l=player 0–3; -1 if none | Scans active players for an opposite-direction shot on the exact wrapped ray |
| 0x54BE0 | `secret_code_build` | void | void | Frameless global-buffer routine; preserves D2 |
| 0x54EC6 | `secret_getname` | void | void | Uses global winner/settings state; initializes entry or completes winner state |

Machine-readable source: [`generated/thief_secret_contracts.csv`](generated/thief_secret_contracts.csv),
regenerated and body-checked by
`python3 generated/generate_thief_secret_contracts.py --check --run-check`.

---

## 12. MOB (Sprite) Management

**Confidence: Verified** for entries, purposes, physical/logical slot biases,
and checked list/depth contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x5DC58 | `mob_create` | Frameless six-argument creator: insert a physical slot, then write picture, H/V position, object type, and object-state upper bits |
| 0x5DCBC | `moblist_insert` | Register entry that inserts an empty/0x8000 destination into the global and cumulative priority-head chains while preserving upper object fields |
| 0x5DD72 | `moblist_replace` | Move a source physical MOB into an empty destination slot, relink the destination, and clear the source |
| 0x5DDA8 | `moblist_remove` | Shipped normal-stack unlink-only wrapper that preserves picture/H/V and upper object type/state bits; no direct control site is currently discovered |
| 0x5DDDA | `moblist_remove_and_clear` | Normal-stack wrapper that unlinks a slot and zeros all five picture/H/V/link/state words |
| 0x5E064 | `mob_depth_remove` | Remove physical slot `argument+1` from the depth/priority lists and clear its depth key plus link/state words, leaving picture/H/V untouched |
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
| 0x5DE0A | `move_mob_slot` | Register entry: insert destination, copy source picture/H/V and upper type/state fields, then fall through to unlink-and-clear the source |
| 0x5DE44 | `moblist_remove_and_clear_regs` | Register entry used by `moblist_remove_and_clear`; repairs links/heads and zeros all five source words |
| 0x5DED4 | `moblist_unlink_regs` | Non-clearing register entry used by `moblist_remove`; shares the unlink algorithm but leaves the slot data intact apart from clearing link indices |
| 0x5DF5A | `mob_place_tport_anim` | Common depth-list placement entry for transporter animation slots; biases the supplied logical slot by 0x0D |
| 0x5DF68 | `mob_place_shot` | Common depth-list placement entry for shot MOB slots; uses the supplied slot without a bias (also used for dragon fireballs) |
| 0x5DF72 | `mob_place_anim` | Common depth-list placement entry for general animation slots; biases the logical slot by 0x11 |

### 12.1 MOB-list and depth-placement callable contracts

**Confidence: Verified.** These bodies were checked with the configured 68010
loader. The table distinguishes normal stack wrappers from register-only
entries and shared bodies; all listed returns are void because direct callers
do not consume D0 or condition codes.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x5DC58 | `mob_create` | `uint16 mob_slot, uint16 picture, uint16 hpos, uint16 vpos, uint16 object_type, uint16 object_state` | void | Frameless; saves D2-D7/A2-A6 before reading six normal slots |
| 0x5DCBC | `moblist_insert` | D1.w=doubled destination; A2-A6=five MOB arrays | void | BSR-only register entry |
| 0x5DD72 | `moblist_replace` | `uint16 source_slot, uint16 destination_slot` | void | Frameless saved-register wrapper |
| 0x5DDA8 | `moblist_remove` | `uint16 mob_slot` | void | Preserves object fields and upper type/state bits; no discovered direct site |
| 0x5DDDA | `moblist_remove_and_clear` | `uint16 mob_slot` | void | Frameless saved-register wrapper |
| 0x5DE0A | `move_mob_slot` | D2.w=doubled source, D1.w=doubled destination; A2-A6=five arrays | void | Falls through into 0x5DE44 |
| 0x5DE44 | `moblist_remove_and_clear_regs` | D2.w=doubled slot; A2-A6=five arrays | void | Register unlink-and-clear body |
| 0x5DED4 | `moblist_unlink_regs` | D2.w=doubled slot; A2-A6=five arrays | void | Register unlink-only body |
| 0x5DF68 | `mob_place_shot` | `uint16 depth_key, uint16 physical_slot` | void | Saves registers, slot bias 0, tail-branches to 0x5DFA6 |
| 0x5DF72 | `mob_place_anim` | `uint16 depth_key, uint16 logical_channel` | void | Physical slot=channel+0x11; tail-branches to shared body |
| 0x5DF9C | `mob_place_explosion` | `uint16 depth_key, uint16 logical_channel` | void | Physical slot=channel+1; falls through to shared body |
| 0x5DFA6 | `insert_mob_depth_sorted` | D7.w=resolved physical slot; first inherited wrapper argument=depth key | void | Shared saved-register body and epilogue |
| 0x5E064 | `mob_depth_remove` | `uint16 physical_slot_minus_one` | void | Resolves physical slot by adding 1 |

The checked machine-readable form is
[`generated/mob_list_contracts.csv`](generated/mob_list_contracts.csv); regenerate and reanalyze
all 13 entries with
`python3 generated/generate_mob_list_contracts.py --check --run-check`.

---

## 13. Playfield (Tile) System

**Confidence: Verified** for live entries, purposes, arguments, and returns.
The unreferenced `refresh_tile_visual_legacy` interpretation remains **Strong
inference** as labeled in its contract row.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x5F31E | `pf_replace` | Replace tile at given slot with new type; handle MOB/graphics update |
| 0x5E892 | `pf_floor_update` | Update floor/wall tile graphics at given position |
| 0x5E536 | `pf_stamp_update` | Update a 2×2 stamp on playfield (e.g., exit open/close animation) |
| 0x5F77A | `pf_isdoor` | Returns door class from picture word: 1 = connectable segment (pics 0x9D18–0x9D3B), 2 = pics 0x9D3C–0x9D7B, 3 = pics 0x9D7C–0x9DAC, 0 = not a door (column x=0 always 0) |
| 0x5F772 | `pf_isdoor_stack` | Stack-argument wrapper used by the vertical/horizontal door-endpoint scanners; loads X/Y into D0/D1 and falls through to `pf_isdoor` |
| 0x5F7F0 | `pf_door_update_surrounding_xy` | Register entry (`D0.w=x`, `D1.w=y`) used by tile-refresh code; wrap coordinates to 0–31, test the four neighbors, and redraw each neighboring door |
| 0x5F7FA | `pf_door_update_surrounding` | Redraws the 4 neighbors of a changed tile if they are doors (register-args entry at 0x5F7F0 = `pf_door_update_surrounding_xy`) |
| 0x5F5A0 | `refresh_tile_visual` | Dispatch on tile type → select descriptor → write to VRAM (fully traced — see `05_data_reference.md` §5 descriptor tables; floors offset tile codes by floorpattern×0x30, walls use per-pattern blocks + 8-neighbor connectivity) |
| 0x5E542 | `pf_stamp_update_regs` | Register entry that writes a four-word 2×2 descriptor plus a uniform addend to playfield VRAM |
| 0x5F876 | `pf_door_draw_xy` | Register-args entry (a0=x, a1=y, d0=door type) into `pf_door_draw` |
| 0x5F880 | `pf_door_draw` | Door tile graphic updater (860 B, was `fcn_5F880`): adjacent-door mask → picture table 0x5F9CE; isolated type-2/3 doors oriented by surrounding floor; stores mask in bits 10–13 of `0x904066[tile]` |
| 0x5EA2E | `pf_isblankfloor` | Register predicate: return -1 iff x is nonzero, picture is 0x8000, and object type is not 0x3F; otherwise 0. The former polarity/type description was contradicted. |
| 0x5E888 | `pf_floor_draw_xy` | Register-args entry into `pf_floor_update` (0x5E892); floor descriptor from 0x5BAE0, tile code += floorpattern×0x30 |
| 0x5E868 | `maze_special_floor` | No-argument setup leaf used only for wall patterns 6 and 11: scans all 1024 playfield/MOB picture words and converts every special-floor marker 0x8003 to ordinary floor 0x8000; returns with no result |
| 0x5EA00 | `maze_floor_decor` | No-argument 32×32 initialization pass: calls the register-entry `pf_floor_draw_xy(x,y)` for every maze cell, preserving D2–D3 and returning after exactly 1024 draws |
| 0x5EA26 | `pf_isblankfloor_stack` | Unreferenced stack-argument wrapper retained in the shipped code: loads `(x,y)` words from 6(A7)/10(A7) and falls through to register-entry `pf_isblankfloor` at 0x5EA2E |
| 0x5F2C0 | `maze_init_walls` | No-argument 32×32 wall-render pass. Unless level-flags byte 2 bit 7 suppresses it (except level 9999), draws cells whose picture is 0x8000 or 0x8003 through `pf_wall_draw_xy`; preserves D2–D3/A2 |
| 0x5F7C0 | `maze_doors_setup` | No-argument initial door-render pass over x=1..31 and y=0..31. Calls `pf_isdoor`; for each nonzero door type, passes x/y in A0/A1 and the type in D0 to `pf_door_draw_xy` |
| 0x5F024 | `wall_place_playfield_update` | Place wall tile; compute 2×2 descriptor; propagate to neighbors |
| 0x5F310 | `mob_place_tile` | Place tile; remove old MOB; update visuals |
| 0x5EAC2 | `pf_wall_draw_stack` | Shipped normal-stack `(x,y)` wall renderer sharing the 0x5EAB8 body; no discovered direct control site |

### 13.1 Playfield stamp, visibility, and floor callable contracts

**Confidence: Verified.** The checked bodies distinguish normal stack leaves,
register wrappers, and shared fall-through/tail bodies. Boolean values below
are exact D0.l results.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x5E536 | `pf_stamp_update` | `uint16 packed_position, const uint16 *descriptor4, uint16 addend` | void | Frameless normal-stack leaf |
| 0x5E542 | `pf_stamp_update_regs` | D0.w=packed position, A0=descriptor, A1.w=addend | void | Register entry |
| 0x5E57E | `tile_on_screen_d4` | D4.w=packed position | D0.l=-1 on screen; 0 outside | Register wrapper into shared saved-register body |
| 0x5E584 | `tile_on_screen_test` | `uint16 packed_position` | D0.l=-1 on screen; 0 outside | Normal-stack wrapper |
| 0x5E5D2 | `tile_near_screen_d4` | D4.w=packed position | D0.l=-1 near; 0 outside | Register wrapper into shared body |
| 0x5E5D8 | `tile_near_screen_test` | `uint16 packed_position` | D0.l=-1 near; 0 outside | Called indirectly through A2 by dragon code |
| 0x5E7A6 | `maze_place_object_types` | `uint8 object_type` | D0.l=1 if any type/type-3 match exists; else 0 | Frameless byte argument at saved A7+0x1B |
| 0x5E80C | `maze_convert_walls_to_exits` | void | D0.l=1 if any conversion occurred; else 0 | — |
| 0x5E868 | `maze_special_floor` | void | void | — |
| 0x5E888 | `pf_floor_draw_xy` | D0.w=x, D1.w=y | void | Register wrapper that skips stack argument loads |
| 0x5E892 | `pf_floor_update` | `uint16 x, uint16 y` | void | Normal-stack entry to shared renderer |
| 0x5EA00 | `maze_floor_decor` | void | void | Calls register entry for all 32×32 cells |
| 0x5EA26 | `pf_isblankfloor_stack` | `uint16 x, uint16 y` | D0.l=-1 eligible; 0 otherwise | Unreferenced stack wrapper falling through to 0x5EA2E |
| 0x5EA2E | `pf_isblankfloor` | D0.w=x, D1.w=y | D0.l=-1 eligible; 0 otherwise | Register body |
| 0x5EA66 | `pf_is_connectable_floor_xy` | D0.w=x, D1.w=y | D0.l=-1 connectable; 0 otherwise | Register entry sharing return leaves with 0x5EA2E |

Machine-readable source:
[`generated/playfield_floor_contracts.csv`](generated/playfield_floor_contracts.csv), regenerated
and body-checked by
`python3 generated/generate_playfield_floor_contracts.py --check --run-check`.

### 13.2 Wall and door playfield callable contracts

**Confidence: Verified.** This pass added the previously omitted shipped
entry at 0x5EAC2. All rows are body-checked; direct callers ignore D0 and
condition codes for the void render/update routines.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x5EAB8 | `pf_wall_draw` | D0.w=x, D1.w=y | void | Register wrapper into shared wall body |
| 0x5EAC2 | `pf_wall_draw_stack` | `uint16 x, uint16 y` | void | Normal-stack shared-body entry; no discovered direct site |
| 0x5F024 | `wall_place_playfield_update` | D0.w=x, D1.w=y | void | Register entry |
| 0x5F2C0 | `maze_init_walls` | void | void | 32×32 initialization pass |
| 0x5F310 | `mob_place_tile` | D0.w=packed slot, D1.w=new object type | void | Register wrapper into shared replacement body |
| 0x5F31E | `pf_replace` | `uint16 packed_slot, uint16 new_object_type` | void | Normal-stack shared-body entry |
| 0x5F598 | `refresh_tile_visual_stack` | `uint16 packed_slot, uint16 object_type` | void | Frameless stack wrapper falling through to 0x5F5A0 |
| 0x5F5A0 | `refresh_tile_visual` | D0.w=packed slot, D1.w=object type | void | Calls fixed `pf_isblankfloor` indirectly through A2=0x5EA2E |
| 0x5F644 | `refresh_tile_visual_legacy` | D0.w=packed slot, D1.w=object type | void | Unreferenced legacy two-way type-2 wall/floor entry sharing the redraw epilogue (**Strong inference**) |
| 0x5F772 | `pf_isdoor_stack` | `uint16 x, uint16 y` | D0.l=door class 1–3, or 0 | Frameless wrapper falling through to register body |
| 0x5F77A | `pf_isdoor` | D0.w=x, D1.w=y | D0.l=door class 1–3, or 0 | Register body |
| 0x5F7C0 | `maze_doors_setup` | void | void | 31×32 pass; X begins at 1 |
| 0x5F7F0 | `pf_door_update_surrounding_xy` | D0.w=x, D1.w=y | void | Register wrapper into shared four-neighbor body |
| 0x5F7FA | `pf_door_update_surrounding` | `uint16 x, uint16 y` | void | Normal-stack shared-body entry |
| 0x5F876 | `pf_door_draw_xy` | A0.w=x, A1.w=y, D0.w=door class | void | Register wrapper into shared door renderer |
| 0x5F880 | `pf_door_draw` | `uint16 x, uint16 y, uint16 door_class` | void | Calls fixed `pf_isdoor` indirectly through A2=0x5F77A |

Machine-readable source: [`generated/wall_door_contracts.csv`](generated/wall_door_contracts.csv),
regenerated and body-checked by
`python3 generated/generate_wall_door_contracts.py --check --run-check`.

---

## 14. Utility Functions

**Confidence: Verified** for entries, purposes, and checked RNG, memory,
display, and placement contracts.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x5FC22 | `random_seeded` | Dormant normal-stack seeded-RNG veneer: upper bound plus caller-supplied seed pointer |
| 0x5FC26 | `random_bound_stack_core` | Shared entry with upper bound on the inherited caller stack and seed pointer in A0 |
| 0x5FC2C | `random_core` | Register RNG body: zero-extended bound in D0.l and seed pointer in A0 |
| 0x5FC4E | `getrandom` / `rand_n` | LCG random: returns value in [0, N). Stack-based. Seed at 0x904BFC |
| 0x5FC46 | `random_word` / `getrandom_r` | Register-based variant of getrandom |
| 0x5FCCE | `pf_palette_clear` | Clear saved playfield colors plus alpha, MOB, playfield, and shadow color RAM through `memclear_core`; no arguments and no return value |
| 0x5FD58 | `memclear` | Clear exactly `count` longwords at ptr using a pre-tested DBRA loop |
| 0x5FD6A | `copy_longwords` | Copy exactly `count` longwords from src to dst using a pre-tested DBRA loop |
| 0x5FD80 | `palette_fade_copy` | Copy exactly `count` words from src to dst while subtracting delta and encoding unsigned underflow |
| 0x5FD14 | `display_state_clear` | Clear MOB-list bucket state, reset scroll and first MOB fields, then clear alpha/playfield VRAM through the register-count memory-clear core |
| 0x5FD64 | `memclear_core` | Register pre-test entry used by display clearing: A0=destination and D0=count, clearing exactly `count` longwords |
| 0x45BE8 | `string_length` | Return the byte length of a NUL-terminated string in D0.l |
| 0x510FC | `calc_direction` | Compute direction (0–7) from source to destination position |
| 0x511AC | `player_tile_interact` / `tile_occupant_interact` | Dispatch by tile type: food/key/enemy/portal/chest handlers |
| 0x49B44 | `ascii_to_alpha_glyph` | Convert name-entry ASCII/control characters to the alpha-layer font code: A–Z→0x0A–0x23, digits→0–9, selected punctuation→0x24/0x27–0x2C, backspace→0x32, default→0x25 |
| 0x4D12E | `alpha_clear_rect` | Clear a rectangular region of alpha VRAM; arguments are column, width, row, and height |
| 0x5554E | `name_entry_step_char_copy` | Byte-identical unreferenced copy of the live routine at 0x55440 |
| 0x555C4 | `name_entry_draw_char_copy` | Byte-identical unreferenced copy of the live routine at 0x554B6 |

### 14.1 RNG, memory, display-init, and Super Sorcerer contracts

**Confidence: Verified.** The count-based memory routines branch to DBRA
before executing their first transfer. A count of N therefore processes
exactly N elements, and zero processes none. The former N+1 descriptions were
**Contradicted**. The RNG pass also added three previously omitted shipped or
shared entries at 0x5FC22/0x5FC26/0x5FC2C.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x5FC22 | `random_seeded` | `uint16 upper_bound, uint16 *seed` | D0.l in [0, upper_bound), or 0 for bound 0 | Dormant normal-stack veneer; no discovered direct site |
| 0x5FC26 | `random_bound_stack_core` | `uint16 upper_bound` on inherited caller stack; A0=`seed` | D0.l in [0, upper_bound), or 0 for bound 0 | Mixed inherited-stack/register entry reached by `getrandom` |
| 0x5FC2C | `random_core` | D0.l=zero-extended upper bound; A0=`seed` | D0.l in [0, upper_bound), or 0 for bound 0 | Register shared body; advances the 16-bit seed |
| 0x5FC46 | `random_word` | D0.l=zero-extended upper bound | D0.l in [0, upper_bound), or 0 for bound 0 | Register wrapper using global seed 0x904BFC |
| 0x5FC4E | `getrandom` | `uint16 upper_bound` | D0.l in [0, upper_bound), or 0 for bound 0 | Normal-stack wrapper using global seed 0x904BFC |
| 0x5FCCE | `pf_palette_clear` | void | void | Tail-calls `memclear_core` for the final shadow-palette clear |
| 0x5FD14 | `display_state_clear` | void | void | Tail-calls `memclear_core` for the final playfield clear |
| 0x5FD58 | `memclear` | `uint16 count, uint32 *destination` | void | Normal-stack pre-tested loop; exactly count longwords |
| 0x5FD64 | `memclear_core` | D0.w=count; A0=destination | void | Register pre-test entry; exactly count longwords |
| 0x5FD6A | `copy_longwords` | `uint16 count, const uint32 *source, uint32 *destination` | void | Normal-stack pre-tested loop; exactly count longwords |
| 0x5FD80 | `palette_fade_copy` | `uint16 count, const uint16 *source, uint16 *destination, uint16 delta` | void | Exactly count words; preserves D2 |
| 0x5FDB8 | `supersorc_place_helper` | `uint16 target_mob_slot, uint16 starting_player_index` | D0.w=packed destination, or 0 | Loads fixed MOB bases and doubles the slot |
| 0x5FDE0 | `supersorc_place` | D0.w=starting player; D2.w=target MOB byte offset; A2/A3/A4=picture/H/V bases | D0.w=packed destination, or 0 | Register body; tries four players and three directions each |

The RNG recurrence is `seed = seed * 0x3619 + 0x5D35 (mod 2^16)`.
For the nonnegative bounds used by the game, the signed-multiply correction
maps every 16-bit seed to the documented half-open result range.
`pf_palette_clear` clears 0x40/0x80/0x40/0x40 longwords at color RAM
0x910000/0x910200/0x910500/0x910400 after zeroing the two saved playfield
colors. `display_state_clear` clears exactly 0x20 priority-head longwords,
0x3C0 alpha-VRAM longwords, and 0x800 playfield-VRAM longwords; it does not
write four bytes beyond the 0x905FFF priority table.

Machine-readable source: [`generated/utility_init_contracts.csv`](generated/utility_init_contracts.csv),
regenerated and body-checked by
`python3 generated/generate_utility_init_contracts.py --check --run-check`.

---

## 15. Sound Functions

**Confidence: Verified** for entries, command paths, queue behavior, and OS
API polarity.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x4AD76 | `sound_play` / `play_sound` | Enqueue sound ID into 8-slot circular ring buffer |
| 0x4AD4E | `sound_speech_play` / `play_sound_mute_guarded` | Like play_sound but check mute flag first |

---

## 16. Shot / Combat Functions

**Confidence: Verified** for entries, purposes, dispatch targets, damage
tables, and checked return polarity.

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x41B16 | `find_unused_shot` | Scan shot MOB array for slot with mob_picture == 0 |
| 0x490DC | `monster_create_shot` | Create a monster shot MOB; link into shot list |
| 0x53666 | `player_create_shot` | If the player's shot slot is free, create the direction/class-specific shot or explosion, play its class sound, and consume one supershot charge when present |
| 0x4AF50 | `resolve_shot_hit` | Full combat resolution for all target types (~0xED4 B, fully analyzed — see `04_game_subsystems.md` §30): `(target, shooter) → 0` shot survives / `-1` shot consumed; computed JMP 0x4B336 with table 0x4B338–0x4BB3; damage tables 0x596B6/0x596C2/0x596CE; monster tier system, generator degradation, secret-wall prizes, supershot/reflect |
| 0x40906 | `shot_mob_collision` | Bounding-box collision test for shot projectiles |
| 0x52192 | `mob_collision_test` | Bounding-box overlap + type dispatch for combat/pickup/warp |
| 0x47DAE | `shot_impact_spawn` | Spawns an impact/explosion effect at the target in shared effect MOB slots 0x0D–0x10 |
| 0x4AEA0 | `shot_onscreen_check` | Range/visibility check vs scroll registers 0x904026/28; gates door reactions to shots |
| 0x53818 | `shot_reflect_calc` | Computes the reflected direction when a reflect-power shot hits a wall (result → `0x9049C4[player]`) |
| 0x5303A | `wall_crumble` | Applies shot damage to a destructible wall (called from `resolve_shot_hit` with (target, damage)) |
| 0x54112 | `dragon_shot_hit` | Dragon damage handler: hit counts only while breathing fire and not sleeping/turning; 9th hit kills; on hit picks a new random path program with pose-matched fast-forward |

---

## 17. OS ROM API Calls (address < 0x10000)

**Confidence: Verified** for fixed API addresses and destinations. Concise
semantic names inherit the evidence labels in `02_os_rom.md`.

See `02_os_rom.md` for full descriptions. Summary table:

| API Address | Name | Args | Return |
|-------------|------|------|--------|
| 0x100 | `start_blink_text` | (text_desc_ptr, color, interval) | d0 = 1 allocated, 0 full |
| 0x106 | `format_decimal` | (value, buf_ptr, width, pad_mode) | void |
| 0x10C | `format_hex` | (value, buf_ptr, width, pad_mode) | void |
| 0x112 | `format_number` | (value, buf_ptr, format_char, format_mode, width) | void |
| 0x118 | `stop_text_effect` | (text_desc_ptr) | void |
| 0x11E | `start_progressive_text_clear` | (text_desc_ptr, interval) | d0 = 1 allocated, 0 full |
| 0x124 | `start_text_line_rotation` | (text_desc_ptr, color, signed_interval) | d0 = 1 allocated, 0 full |
| 0x12A | `start_timed_text` | (text_desc_ptr, color, interval) | d0 = 1 allocated, 0 full |
| 0x130 | `start_progressive_text` | (text_desc_ptr, color, interval) | d0 = 1 allocated, 0 full |
| 0x136 | `init_fullscreen_text_scroll` | (text_desc_ptr, color, interval) | d0 = 1 allocated, 0 full |
| 0x13C | `set_text_position` | (text_desc_ptr, coordinate0, coordinate1) | void; also clears descriptor byte 6 |
| 0x142 | `display_text` | (text_desc_ptr, color) | void |
| 0x148 | `process_text_effects` | () | void |
| 0x14E | `init_alpha_display` | () | void |
| 0x154 | `wait_vblanks` | (count: word) | void |
| 0x15A | `process_sound` | () | void |
| 0x160 | `calc_health_per_coin` | (player_index: long) | d0 = health value |
| 0x166 | `check_and_deduct_coin` | (player_index: long) | d0 = 1 if success |
| 0x16C | `process_coins` | (previous packed counters, current packed counters) | void |
| 0x172 | `send_sound_command` | (cmd: word, response_dest, response_count: word) | d0 = 1 accepted, 0 busy |
| 0x178 | `read_sound_data` | () | next ring byte, or -1 empty |
| 0x17E | `sound_receive_irq_body` | interrupt frame only | no value; exits with `RTE` |
| 0x184 | `eeprom_check_busy` | () | d0 = 1 if busy |
| 0x18A | `eeprom_process` | () | void (called every VBLANK) |
| 0x190 | `eeprom_init` | () | 0 initialized, 1 bad game header, -1 terminal error |
| 0x196 | `eeprom_request_write` | (region_index: long) | supplied region index |
| 0x19C | `record_player_session_histogram` | (player_index: word, coin_count: word) | void |
| 0x1A2 | `read_eeprom_setting` | (difficulty_row: long, bin: long) | byte, -1 bad bin, -2 unavailable row |
| 0x1A8 | `read_game_config` | (item_index: long) | decoded long, or -1 invalid |
| 0x1AE | `read_high_score_entry` | (class: word, rank: word) | expanded-entry pointer, or 0 invalid rank |
| 0x1B4 | `write_high_score_entry` | (class, rank, expanded_ptr) | 0 success, -1 rank, -2 score overflow |
| 0x1BA | `update_active_player_time_stats` | (active_mask: long) | 0x904F50 counter-base pointer |
| 0x1C0 | `write_eeprom_setting` | (config_index, value) | -1 invalid; otherwise delegated writer result |
| 0x1C6 | `rank_high_score` | (class: word, score: long) | `D0.l` = rank 0–9, 10 when absent, or -1 invalid |
| 0x1CC | `activate_player_time_tracking` | (player_index: long) | 0x904F50 counter-base pointer |
| 0x1D2 | `run_statistics_screens` | (allow_clear: long) | void |
| 0x200 | `display_large_text` | (text_desc_ptr) | d0 = alpha-cell advance |
| 0x20C | `display_large_char_at` | (alpha_ptr, glyph_index, color) | d0 = 1 or 2 cells |
| 0x212 | `display_large_char_raw` | (alpha_ptr, glyph_index, color) | d0 = 1 or 2 cells |
| 0x218 | `write_alpha_char` | (row, col, char, color) | void |
| 0x21E | `write_alpha_word` | (cell_index, value) | void |
| 0x224 | `calc_alpha_address` | (row, col) | d0 = address |
| 0x230 | `check_and_deduct_credits` | (required: long, player: long) | d0 = 1 consumed/free play, 0 insufficient |
| 0x236 | `get_coin_multiplier` | () | d0 = multiplier |
| 0x23C | `send_sound_command_wait` | (command: word) | `D0.l = 1` after accepted |
| 0x242 | `try_send_sound_command` | (command: word) | `D0.l = 1` accepted, 0 busy |
| 0x248 | `run_game_options` | (descriptor_stream_ptr) | delegated setting-writer result |
| 0x24E | `eeprom_read_block` | (dest_buf, block_index: word, mode) | 1 success, 0 unavailable, -1/-2 syndrome |
| 0x254 | `reset_sound_cpu` | (control: word, startup_command: word) | void |
| 0x25A | `draw_string` | (coordinate0, coordinate1, string_ptr, color) | d0 = source bytes including NUL |
| 0x260 | `display_decimal_value` | (coordinate0, coordinate1, value, width, pad_mode, color) | void |
| 0x266 | `display_hex_value` | (coordinate0, coordinate1, value, width, pad_mode, color) | void |
| 0x272 | `display_large_decimal_value` | (coordinate0, coordinate1, value, width, pad_mode, color) | d0 = alpha-cell advance |

---

## 18. Shared Functions Registry (cross-subsystem)

**Confidence: Verified** for addresses, aliases, and shared call sites.

These functions are called from multiple top-level subsystems:

| Address | Name | Brief Description |
|---------|------|-------------------|
| 0x42DC8 | `sound_system_reset` | Flush sound ring buffer, reset speech counter, send HW reset |
| 0x4C9A2 | `demo_speech_cmd` | Process 0xFF speech command in demo input stream |
| 0x48BEC | `player_start_inner` | Find a usable spawn tile, install character-specific RAM jump stubs, initialize player state/MOB data, and return -1 on success or 0 when placement fails |
| 0x48F12 | `tile_occupancy_test` / `check_tile_passable` | Return -1 only for an in-bounds empty candidate whose eight neighboring cells contain no MOB within 0x7C0 on both rendered axes |
| 0x55440 | `name_entry_step_char` | Increment/decrement and wrap a name-entry character through space, A–Z, and optional backspace |
| 0x4A44A | `name_entry_draw_large_char` | Draw a 2×2 name-entry character/control glyph using OS 0x224 and 0x20C |
| 0x554B6 | `name_entry_draw_char` | Draw one name-entry character with OS 0x218, translating backspace to glyph 0x3B and conditionally hiding spaces during cursor-flash palette phases |
| 0x4E630 | `thief_track_victim_move` | When the supplied player is the thief's victim and changed packed position, write the direction into the path grid and update `thief_victim_pos` |
| 0x4DE76 | `score_screen_color_cycle` | Every 16th frame: saves 4 words from 0x910140 area, shifts 11 color RAM entries one slot, writes saved words back to start — creates scrolling rainbow on high-score text |
| 0x4D956 | `scroll_apply` | Apply signed scroll deltas for title-screen animation. Both deltas zero → writes 0x75 to 5 scroll anchor slots at 0x9038DE (stride 0x24) and returns D0.l=-1. Non-zero → walks MOB list for scroll anchor tiles (picture in range 0x2700–0x2728) and returns D0.l=0 |
| 0x4DA3E | `title_logo_init` | No-argument TITLE initializer: build the multi-row logo MOBs, initialize brightness/color and full/short motion-program state, then start the logo off-screen with `scroll_apply(-128, 0)` |
| 0x449D4 | `attract_demo_init` / `demo_setup` | Initialize maze 102 for the DEMO attract screen, set up Elf player 1, and install demo stream pointer 0x581C4 |
| 0x40D24 | `load_level_tileset` | Load level tile data into VRAM |
| 0x4CD1C | `load_legend_page` | Load maze 103 for LEGEND mode and render the overview (selector 0), rules (selector 2), or monsters (other selector) page. The former `load_demo_level` name was contradicted by the body |
| 0x44DB4 | `show_level_start_screen` | Build the between-level/start display; after a secret-room win, replace the trick ID with a random 0x50–0x5D challenge, select maze 115 for tasks 0x50–0x56 or maze 116 for tasks 0x57–0x5D, set its timer, and show its qualifier |
| 0x40CF2 | `maze_init` | Maze initialization (called from main_start_game) |
| 0x4FCF0 | `thief_find_aligned_shooter` | Return the first active player 0–3 whose shot direction is opposite the thief's and whose wrapped position lies exactly on that shot ray; -1 if none |
| 0x4EE7A | `thief_move_engine` | Core thief movement/direction computation |
| 0x4F912 | `thief_compute_path` | Compute the thief's next maze position/direction, including diagonal alternatives and passability tests |
| 0x4E1B8 | `thief_begin_dodge` | Enter the shot-dodge submode and repair route state; formerly misnamed `mark_item_stolen` |
| 0x4E172 | `thief_end_dodge` | Leave the shot-dodge submode and repair route state; formerly misnamed `abort_theft` |
| 0x43192 | `eeprom_write` | Copy 6 monitored values to write buffer; flush via OS 0x24E |
| 0x4ADAE | `sound_queue_reset` | Fill ring buffer with 0xFF; zero read/write heads |
| 0x45940 | `draw_player_score` | Draw the player's 7-digit SCORE (`player_score` 0x904990[p]) via OS `display_decimal_value` (0x260) at row p*5+9, using the flash attribute at 0x57350[p], then clear `player_redraw` bit 0. The former `draw_player_name`/`flash_score_display` names were misleading. |
| 0x459A2 | `draw_player_health` | Draw bonus multiplier “×N” when greater than one and the player's 5-digit HEALTH value; apply low-health/acid palette dimming and clear `player_redraw` bit 1. This is numeric HUD rendering, not a health bar or lives display. |
| 0x4A2CA | `draw_player_initials_entry` | Render the score-per-coin value, high-score rank, “Enter your initials” labels, and the three editable initial sprites for one player |
| 0x54AF8 | `dragon_any_segment_near_screen` | Test the dragon's four segment positions with the indirect stack entry at 0x5E5D8; returns -1 when any segment is within the wider playfield window and 0 otherwise. Used by the potion handler's dragon-effect path. |
| 0x4D1A4 | `secret_bonus_earned` | Check the active secret-challenge code/progress and return whether the entrant earns the 5,000-per-coin secret-room bonus |
| 0x489B8 | `remove_dying_player_sprites` | Remove the two auxiliary sprite slots associated with a dying/departing player and clear that player's animation-state word |
| 0x50B88 | *(score animation phase)* | Score animation phase handler |
| 0x4119A | `monster_special_handler` | Sorcerer teleport/acid spread/IT chase logic |
| 0x40FAE | `monster_loop_core` | Interior per-MOB iteration entry within `monsters_everything`; inherits its saved-register/local-stack frame and MOB-array registers, and is reached by loop-back branches rather than a normal call |
| 0x46F56 | `scroll_set_position` | Apply scroll X/Y to hardware registers with clamping |
| 0x41B7E | `apply_direction_from_delta` | Compute direction code from dx/dy between MOBs |
| 0x40A78 | `shot_collision_candidate_core` | BSR-only candidate evaluator used by `shot_mob_collision`: reject empty/self/out-of-range slots, handle wrapped MOB coordinates, update signed/absolute separation scratch words, and return the candidate type/result in D2 |
| 0x41B52 | `monster_shooter_in_view` | BSR-only viewport gate before a monster fires: compare its byte-scale H/V coordinates with the culling origins; return D4=-1 when inside the allowed rectangle and zero otherwise |
| 0x41C30 | `player_try_move_core` | Internal register-state reentry for `player_try_move`; initializes the active player's MOB slot/coordinates and runs the directional collision/door/squeeze logic. Several branches BSR here to retry movement. |
| 0x42598 | `mob_collision_test_preserve_d1_a` | First of two byte-identical leaf wrappers: convert doubled MOB offsets D1/D5 back to slot IDs, call `mob_collision_test`, restore D1, and return its boolean in condition codes |
| 0x425B4 | `mob_collision_test_preserve_d1_b` | Second byte-identical copy of the D1-preserving `mob_collision_test` wrapper, reached by the alternate movement branches |
| 0x5E888 | `wall_remove_playfield_update` / `refresh_floor_visual` | Refresh floor visual after wall removal |
| 0x5EAB8 | `pf_wall_draw` (aka `refresh_wall_visual`) | Register `(D0=x,D1=y)` wall renderer: 8-neighbor connectivity mask → variant table 0x5EE24 (0x5EF24 for patterns 6/0xB); descriptor base by `wallpattern` (0–5: 0x5BBE0 + offsets 0x5EDD4; 6: 0x5D2F8; destructible ≥6: 0x5D3D0; 7+: random of 6 sets at 0x5EDF4) |
| 0x5EAC2 | `pf_wall_draw_stack` | Normal-stack `(uint16 x,uint16 y)` entry to the same wall-rendering body; retained but with no discovered direct control site |
| 0x4ADD6 | `enqueue_sound` | Low-level sound ID enqueue into ring buffer at 0x90404B; called by play_sound |
| 0x40CC4 | `maze_select_alt_bank` | Call `find_maze`, switch the Slapstic through the alternate bank-selection path, and store the resulting command offset at 0x904B8C. It does not clear maze state. |
| 0x40D4E | `maze_select_bank_special` | No-prologue callable bank-selection path used by `show_level_start_screen` and `main_start_game`; calls `find_maze` for either secret layout (115/116), executes the 0x38000/0x3FB4A/selected-bank Slapstic sequence through 0x56E98, and stores D1 at 0x904B8C |
| 0x54B68 | `dragon_shot_hitbox_adjust` | Register-argument leaf called only from `shot_mob_collision` after the candidate type is 0x3C: reset dragon escape/idle timers, test the moving head hitbox using the five-word padded offsets at 0x54BD6, and add 0x1000 to D0 when the shot overlaps the head |
| 0x449CC | `attract_noop_hook` | Deliberate empty routine called once at the end of the attract-screen timer/display update path |
| 0x48B58 | `update_monster_bonus_from_score_per_coin` | Sum active players' scores and inserted-coin counts, then add `(total_score >> 14) / total_coins` to the signed monster-cap bonus byte at 0x90405F |
| 0x4CDB8 | `draw_legend_monsters_page` | Render legend sub-page 1: “MONSTERS”, monster names, and their Fight/Shoot/Magic attributes |
| 0x4CFAE | `draw_legend_overview_page` | Render legend sub-page 0 from the two formatted text records at 0x5A99C and 0x5AB0E |
| 0x4CFDA | `draw_legend_rules_page` | Render legend sub-page 2: adjust its decorative MOBs, clear label rectangles, and draw the formatted rule/item text records |
| 0x50BB8 | `scan_move_path_interactions` | Repeatedly call a directional neighbor probe and resolve each encountered interior MOB/tile until the probe fails or the path is blocked |
| 0x50C7A | `resolve_move_tile_interaction` | Resolve a traversed tile; return -1 for blocking/preserved interactions and zero after removable-object cleanup, recursively retrying type 0x0F after thief/exit cleanup |
| 0x50D14 | `nearby_mob_clearance_test` | Scan eight neighboring cells and return -1 unless a qualifying MOB falls within the 0x7C0-by-0x7C0 rendered-axis window |
| 0x51E80 | `door_record_endpoints` | Classify a door picture and populate one two-ended door record in 0x904A76 (positions) and 0x904A86 (endpoint direction codes) |
| 0x51FAE | `door_scan_vertical_endpoints` | Test the immediate above/below cells, append direction codes 0/2, and return the endpoint count capped at two |
| 0x5207C | `door_scan_horizontal_endpoints` | Test the immediate left/right cells, append direction codes 3/1, and return the endpoint count capped at two |

### 18.1 Movement, path-grid, and door-record callable contracts

**Confidence: Verified.** All eleven rows are checked against fresh 68010
disassembly and their direct callers. Empty “normal stack” distinctions below
are stated where the former prose did not establish an ABI.

| Address | Name | Arguments | Return | Convention exception |
|---|---|---|---|---|
| 0x48F12 | `tile_occupancy_test` | `uint16 candidate_packed_slot` | D0.l=-1 usable; 0 blocked | Normal stack |
| 0x50BB8 | `scan_move_path_interactions` | `int16 (*neighbor_probe)(uint16 packed_slot), uint16 packed_slot, uint16 player_index` | void | Calls supplied probe through A2 until negative/blocked |
| 0x50C7A | `resolve_move_tile_interaction` | `uint16 mob_slot, uint16 player_index` | D0.l=-1 when interaction/type blocks cleanup; 0 after removal | Recurses for type 0x0F after thief/exit cleanup |
| 0x50D14 | `nearby_mob_clearance_test` | `uint16 candidate_packed_slot, uint16 excluded_player_index_or_4` | D0.l=-1 clear; 0 overlapping | Values 0–3 exclude hpos nibble 12+player; 4 excludes none |
| 0x50FD2 | `path_grid_set_low_direction` | `uint16 grid_index, uint8 direction` | void | Writes direction+1 to low nibble |
| 0x51000 | `path_grid_set_high_direction_if_empty` | `uint16 grid_index, uint8 direction` | void | Disabled by thief-mode bit 1; writes only an empty high nibble |
| 0x5103E | `path_grid_get_direction` | `uint16 grid_index` | D0.l=direction 0–7; 8 unset/invalid | Bit 1 selects high nibble, otherwise low |
| 0x510FC | `calc_direction` | `uint16 from_packed_slot, uint16 to_packed_slot` | D0.w=direction 0–7; 8 if equal | Honors horizontal/vertical wrap flags |
| 0x51E80 | `door_record_endpoints` | `uint16 packed_door_slot, uint16 player_index, uint16 door_object_type` | void | Fills the player's two endpoint records and calls `main_open_doors` |
| 0x51FAE | `door_scan_vertical_endpoints` | `uint16 packed_door_slot, uint16 player_index, uint16 next_endpoint_index` | D0.l=updated index, capped at 2 | Immediate above/below only; direction codes 0/2 |
| 0x5207C | `door_scan_horizontal_endpoints` | `uint16 packed_door_slot, uint16 player_index, uint16 next_endpoint_index` | D0.l=updated index, capped at 2 | Immediate left/right only; direction codes 3/1 |

Machine-readable source: [`generated/movement_path_contracts.csv`](generated/movement_path_contracts.csv),
regenerated and body-checked by
`python3 generated/generate_movement_path_contracts.py --check --run-check`.

---

## 19. Detailed Shared Function Behaviors

**Confidence: Verified** for the described bodies and caller-visible effects
unless an individual statement is explicitly labeled otherwise.

### `start_attract_screen` — 0x44414

Sets `game_mode` (0x904918) to arg value. Calls OS 0x14E (hardware init). If dialog timer > 0: sets to 1 and calls `speech_countdown_flush`. Plays sounds 0x1 (silence) + 0x3C (music fade-out). Clears level counter (0x904000=0, 0x904004=1). Calls `pf_palette_clear` (0x5FCCE) and `player_resetall` (0x4341E).

Dispatch by mode:
- **TITLE (-2):** timer = 0x5DD (25 sec). Calls `load_attract_display_tilemap` (0x4438E) and 0x4DA3E. Every 13th title cycle: refreshes EEPROM settings via OS 0x1BA/0x236/0x1A8. If bit 14 of settings set and music counter zero: plays music 0x3B.
- **SCORES (-1):** timer = 0x258 (10 sec). Calls `attract_highscores` (0x4A124).
- **DEMO (-3):** timer = 0x1C20 (119 sec). Calls `demo_setup` (0x449D4), clears frame counter.
- **LEGEND (-4):** timer = 0x258. Calls `maze_hide` (0x4529A), draws legend art via `setup_infopanel` (0x452D0(-1)), then calls `load_legend_page` (0x4CD1C) with the current page selector. That routine loads maze 103 and renders the selected explanatory page; it is not the maze-102 demo initializer.

### `start_attract_to_game` — 0x44204

Transitions from attract to gameplay. Clears level (0x904000=0). Flushes speech, clears damage flags (0x90487E=0, 0x9049E4=0). If DEMO mode: clears display. Plays sound 0x3C (music fade). Sets `game_mode=0` (NORMAL), level=1.

Initializes continue system: `0x904BB4/0x904BAC = 0x7D30` (default pointers), `0x904BB0/0x904BA8 = 0`. Calls OS 0x14E. Plays sound 0x2 ("Noisy"). Clears playfield via `maze_hide`, builds the level-start/challenge display via `show_level_start_screen` (0x44DB4), and sets up the maze via 0x438AE.

Loops 4 players: draws character tiles to HUD via OS 0x25A using ROM tables at 0x57340, 0x570B8, 0x570B4, 0x570CC, 0x570BC, 0x570DC, 0x570C4. Loads main tilemap via OS 0x200 from ROM 0x5709A (0x8C00 bytes). Initializes palettes via `init_display` (0x43486) with the main/special palette selectors at `0x904B58`/`0x904B5A`. Sets attract timer to -1.

### `init_display` — 0x43486

Args: `(main_palette_index: word, special_palette_variant: word)`. Initializes color palettes; it does not consume scroll coordinates. The normal values are the high and low nibbles of maze header byte 6. A main index of 0x10 selects the fixed palette block at 0x5AC5E instead of the normal 16-entry bank.

Waits for VBLANK by testing bit 3 of hardware port `0x803009`, then spinning on VBLANK semaphore at `0x904002`. Copies two adjacent 32-longword ROM views at `0x5AD1E` and `0x5AD9E` to color RAM at `0x910000` (alpha palette) and `0x910100` (MOB palette) via `copy_longwords` (0x5FD6A). The count argument is 0x20, and the pre-tested DBRA helper copies exactly that many elements.

Level-dependent palette: if `0x904B5E < 6`, uses biased base `0x5D7E8`; otherwise it uses `0x5D7C8`. In both cases the second argument in D3 selects a 32-byte entry, so the effective source is `base + D3×32`. This is one four-entry bank with overlapping views, not fixed “palette A/B” objects at 0x5D7E8/0x5D828. Sets `0x904A4E` (countdown timer) and `0x904B7C` (attract timer). Clears `0x90486E` and `0x904AC6`.

### Startup, Attract, Demo, Title, and Legend Contracts

**Confidence: Verified.** Each row is checked against a freshly analyzed body;
the generated catalog also records every direct control-transfer site. Empty
exception cells use the normal convention from §3.

| Address | Function | Arguments | Return | Exceptional convention |
|---|---|---|---|---|
| 0x4327A | `one_time_init` | void | void | — |
| 0x43486 | `init_display` | `uint16 main_palette_index`, `uint16 special_palette_variant` | void | Calls fixed `copy_longwords` through A2=0x5FD6A |
| 0x44204 | `start_attract_to_game` | void | void | — |
| 0x4438E | `load_attract_display_tilemap` | void | void | — |
| 0x44414 | `start_attract_screen` | `int16 screen_mode` | void | — |
| 0x44562 | `main_attract` | void | void | — |
| 0x449CC | `attract_noop_hook` | void | void | — |
| 0x449D4 | `attract_demo_init` | void | void | — |
| 0x44A82 | `game_playfield_init` | void | void | OS reaches it through the JMP veneer at 0x40030 |
| 0x44DB4 | `show_level_start_screen` | void | void | Calls fixed `draw_string` through A3=0x25A |
| 0x4800C | `main_start_game` | void | void | — |
| 0x4C9A2 | `demo_speech_cmd` | `uint16 player_index`, `uint16 message_index` | void | — |
| 0x4CD1C | `load_legend_page` | `uint16 page_selector` | void | — |
| 0x4CDB8 | `draw_legend_monsters_page` | void | void | Calls fixed `draw_string` through A3=0x25A |
| 0x4CFAE | `draw_legend_overview_page` | void | void | — |
| 0x4CFDA | `draw_legend_rules_page` | void | void | Calls `alpha_clear_rect` through A2=0x4D12E |
| 0x4D956 | `scroll_apply` | `int16 horizontal_delta`, `int16 vertical_delta` | D0.l=-1 for zero/zero anchor reset; 0 after nonzero scroll | — |
| 0x4DA3E | `title_logo_init` | void | void | — |
| 0x4DCBA | `main_logo_updcolors` | void | void | — |

Machine-readable source: [`generated/startup_attract_contracts.csv`](generated/startup_attract_contracts.csv),
regenerated and body-checked by
`python3 generated/generate_startup_attract_contracts.py --check --run-check`.

### `eeprom_load_config` — 0x42F86

Spins on OS 0x184 until resource is available. Calls OS 0x24E to read EEPROM block into buffer at `0x904B8E`.

On first boot (result == 0xFFFE): initializes defaults — writes header bytes (0x05, 0x00, 0x68, 0x00), clears remaining fields, stores game_settings word (0x904A24), writes back.

Parses buffer: byte 0 → `0x904010` (level number, validated against slapstic ROM pointer table at 0x38000), byte 1 → `0x90400E` (difficulty bits & 7), byte 2 → `0x904018` (clamped to 0x68–0x72 range), byte 3 → `0x904016` (& 3), words 4–5 → `0x904B86` (stats, clamped to 0x7D0) and `0x904B94` (settings). Sets EEPROM write timer to 0x8CA0 (≈10 minutes).

### `palette_fade_copy` — 0x5FD80

Args: `(count, src, dst, delta)`. Copies a word array from src to dst, subtracting `delta` from each word. If result underflows, wraps around using 12-bit color math: `result = (result & 0xFFF) | 0x1000`. This preserves the overflow/borrow bit used alongside the game's 12-bit IRGB color value.

The count is exact, not count-minus-one: a zero count performs no transfer.
More precisely, the underflow transform is applied only when the unsigned
16-bit subtraction borrows; otherwise the raw 16-bit difference is stored.

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

Args: D0.w = packed tile position (bits 9–5 = row, bits 4–0 =
column); A0 = pointer to the four-word descriptor; A1.w = palette/base
addend. It computes the byte address `0x900000 + (column << 8) + (row <<
2)` for the top-left of the maze tile's 2×2 block in the column-first 64×64
playfield-word grid, then writes the descriptor words at offsets `+0`,
`+0x80`, `+2`, and `+0x82`. **Contradicted and corrected:** the former bit
labels were reversed and the playfield was incorrectly described here as a
128×256 table; the raw instructions mask low bits with 0x1F and shift them
left eight, while masking high bits with 0x3E0 and shifting them right three.

### `maze_scan_objects` — 0x43D8C *(formerly `maze_food_mob_consume` — corrected)*

Multi-mode maze object scanner over all 0x400 `mob_link` tiles. Modes by argument (object types are the §3.14 Maze Object IDs, not the old "food" readings):
- **arg=0:** count **EXIT** tiles (type 0x10). Implements EXIT_CHOOSEONE: keeps one randomly chosen exit (slot → 0x904A0A); the others become fake exits (hpos |= 0x10) when LFLAG4 bit 6 (EXIT_FAKE) is set, otherwise are replaced with floor via `pf_replace`. When only one exit exists, clears LFLAG3 bit 6 (EXIT_MOVES, long bit 14 of 0x90491C).
- **arg=0xFFFF:** count **PLAYERSTART** tiles (type 0xF).
- **arg=N (N≥1):** count **food** (types 0x31 FOOD_DESTRUCTABLE / 0x32 FOOD_INVULN) — used by the has-food logic. (This food-counting mode is what led to the original misnaming.)
