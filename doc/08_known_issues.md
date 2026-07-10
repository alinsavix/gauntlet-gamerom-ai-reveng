# Gauntlet II RE — Known Issues, FIXMEs, and Remaining Unknowns

*Documents all known errors, name conflicts, and unresolved questions in the analysis.*

---

## 1. Critical Errors / Factual Contradictions (from FIXME.md)

### 1.1 `0x492C0` — Misidentified in REPORT.md

**REPORT.md** called this `handle_generate` and described generator spawning logic: "Checks `ram.monster_count` against the level cap. Spawns a new monster MOB at the generator position using the maze-encoded monster type."

> **Correction:** FUNCTIONS_PLAN.md (deeper analysis) identifies `0x492C0` as `monster_generic_handler` — the core movement/AI handler for standard monster types (ghosts, grunts, demons, lobbers, death). Arguments: `(mob_id: long, monster_type_index: long, speed: long)`. Generator spawning is handled *inline* within `monster_loop_core` at `0x41026`, not at this address.

---

### 1.2 `0x44C7E` — Conflicting Names

**REPORT.md section 8** renamed this `show_continue_screen` and described it as displaying the "PRESS START WITHIN X SECONDS TO CONTINUE" screen.

> **Correction:** FUNCTIONS_PLAN.md (call-tree analysis) identifies `0x44C7E` as `update_maze_player_count` — a small utility that decrements `0x904928` (level active player count) and triggers the all-dead state if it reaches zero. It is called from `player_death_sequence` (0x49DE6).
>
> The `show_continue_screen` behavior belongs to `0x4D476` (see item 1.3).

---

### 1.3 `0x4D476` — Direct Contradiction Between Documents

**REPORT.md section 13** listed `0x4D476` as "Not analyzed."

**GAME_ROM_KNOWN.md** described it as "handles exiting the treasure room with people still active."

> **Correction:** FUNCTIONS_PLAN.md phase 8 identifies `0x4D476` as `show_continue_screen` with full sub-call tree analyzed. It handles the "all players dead — show continue screen" logic, calling:
> - `0x4D1A4` check_coin_eligibility
> - `0x4D900` count_active_players
> - `0x489B8` remove_dying_player_sprites
> - `0x486FE` (see conflict item 2.1)
> - `0x54EC6` (see conflict item 2.2)
>
> Status: DONE. The "treasure room exit" description from GAME_ROM_KNOWN.md may refer to a different entry point within the same function, or may be incorrect.

---

### 1.4 RAM `0x904908` — Misidentified in REPORT.md

**REPORT.md section 3** documented `ram.player_state (0x904908..0x90490E)` with values 0=inactive, 1=active, 2=winning secret room, 3=exiting, 4=entering name.

> **Correction:** FUNCTIONS_PLAN.md (from coincheck and main_move_players instruction analysis): `0x904908` is `player_redraw[4]` — per-player redraw flags (bytes). Any REPORT.md code that treats `0x904908` as a state value (0/1/2/3/4) is reading the wrong address.
>
> The actual player status/state array is at `0x9049A0` (`player_status[4]`).

---

### 1.5 Player Health Width — Wrong in REPORT.md

**REPORT.md section 3** stated `ram.player_health — 16-bit health (0 = dead)`.

> **Correction:** Player health is stored as **32-bit longwords** at `0x904980` (stride 4, 4 players). The acid damage path explicitly reads/writes `0x904980 + d4*4` (longword stride). REPORT.md was wrong about both the width and the base address.

---

## 2. Name Conflicts — Require User Clarification

These functions were named in GAME_ROM_KNOWN.md (pre-provided authoritative knowledge) but were renamed in FUNCTIONS_PLAN.md after being found in the `show_continue_screen (0x4D476)` call tree without checking against the original names.

### 2.1 `0x486FE` — `secret_check` vs `update_bgm_volume`

| Source | Name | Description |
|--------|------|-------------|
| GAME_ROM_KNOWN.md | `secret_check` | "Check to see if we should enter secret room?" |
| REPORT.md section 7 | `secret_check` | Reads secret room monster type from maze data byte 0, tracks player score via `ram.secret_score_ctr`, gated by `ram.secret_room_active (0x904065)` |
| FUNCTIONS_PLAN.md (from 0x4D476 call tree) | `update_bgm_volume` | "Updates background music volume/fade" |

> **Conflict:** The pre-existing identification `secret_check` is corroborated by two sources. The `update_bgm_volume` name was assigned based only on call-tree context from 0x4D476 without cross-checking. Until this is resolved by disassembly verification, prefer `secret_check` but treat the name as uncertain.

> **RESOLVED (disassembly verified):** `secret_check` is correct; `update_bgm_volume` is refuted (the function touches no sound state). Full behavior: called at level transition (from `main_start_game` at 0x480EC when the between-level delay 0x904A4E expires, and from the `show_continue_screen` epilogue at 0x4D8DC). If the secret room was active this level (`0x904065` ≠ 0): if a valid player (0–3) is in `0x904063`, it records the current maze number into `secret_prev_maze` (0x904870) and adds 15 to `secret_possible_start` (0x90487A, clamped at 40); if nobody entered, it subtracts 2 (floor 4). Either way `secret_possible_counter` (0x904878) is reloaded from the start value. Note: REPORT.md's score-based names for these variables are also refuted (see §8).

---

### 2.2 `0x54EC6` — `secret_getname` vs `reset_attract_player`

| Source | Name | Description |
|--------|------|-------------|
| GAME_ROM_KNOWN.md | `secret_getname` | "Set up to get the player's name if they won the secret room" |
| REPORT.md section 7 | `secret_getname` | Sets up name entry screen for secret room winner; sets `ram.player_state = 2` for winning player |
| FUNCTIONS_PLAN.md (from 0x4D476 call tree) | `reset_attract_player` | "Resets attract-mode player animation state" |

> **Conflict:** Same situation as 2.1. Two sources agree on `secret_getname`. The `reset_attract_player` name came from call-tree context alone. Prefer `secret_getname` but flag as uncertain.

> **RESOLVED (disassembly verified):** `secret_getname` is correct; `reset_attract_player` is refuted. The function reads EEPROM settings word 0x904A24 **bit 13**: if set, it sets up the name-entry screen for the secret-room winner (`0x904063`): 30-byte name buffer at 0x904AA4 initialized to `'A'` + 28 spaces, `player_status` (0x9049A0) = 0x20 (entering-name state), between-level delay 0x904A4E = 0xA8D, and draws "ENTER YOUR" / "'LAST-NAME FIRST-NAME'" via OS calls (records at 0x5DA16/0x5DA2A). If bit 13 is clear: `player_status` = 2, delay = 0x385, and 0x904063 = 0xFF. This also resolves EEPROM bit 13 (see 4.4).

---

## 3. Functions Not Analyzed

### 3.1 `fcn_5F880` (0x5F880)

Listed in REPORT.md section 13 as not analyzed. Located near `pf_isdoor` (0x5F77A) and `pf_door_update_surrounding` (likely 0x5F7F0). Likely a door-adjacent tile helper — possibly `update_wall_connection` (see FUNCTIONS_PLAN.md for 0x5F876). Does not appear as a named function in FUNCTIONS_PLAN.md.

> **Action needed:** Disassemble and identify. Given the neighborhood (door graphics helpers), likely handles selection of the correct door-segment graphic variant.

> **RESOLVED:** 0x5F880 = `pf_door_draw` (860 bytes) — the door tile graphic updater, exactly as hypothesized. Register-args entry at 0x5F876 (`pf_door_draw_xy`: a0=x, a1=y, d0=door type from `pf_isdoor`); stack-args entry at 0x5F880. For type-1 doors (pictures 0x9D18–0x9D38) it builds a 4-bit adjacent-door mask (L=2, down=4, R=8, up=0x10) and takes the picture from the 16-word table `door_gfx_by_neighbors` (0x5F9CE), writing picture/hpos/vpos for the tile and storing the mask in bits 10–13 of `0x904066[tile]`. Isolated type-2/3 doors get orientation from surrounding plain floor (`pf_isblankfloor` 0x5EA2E, new) using tables 0x5FACA (type 2) and vpos-offset tables 0x5FBEE/0x5FC00 (type 3). Called by `maze_doors_setup` (all 32×32 tiles) and `pf_door_update_surrounding` (register entry 0x5F7F0, stack 0x5F7FA). `pf_isdoor` return verified: 1 for pics 0x9D18–0x9D3B, 2 for 0x9D3C–0x9D7B, 3 for 0x9D7C–0x9DAC, else 0.

---

## 4. Missing Detail — Documented But Incomplete

### 4.1 `maze_decode` RLE Format Not Documented

REPORT.md and DETAILED_REPORT.md describe the format as "run-length encoded; each run specifies tile type and count" but never give the actual byte encoding. The actual bytecodes are listed in the `Maze Compression Bytecodes` enum in `05_data_reference.md` (from GAME_ROM_KNOWN.md), but the precise relationship to the HT1/HT2/VT1/VT2 horizontal/vertical type bytes is not fully traced through the decoder.

> **Action needed:** Decompile `maze_decode` (0x4C1BC) and verify the bytecode encoding matches the enum.

> **RESOLVED (fully traced):** The enum in `05_data_reference.md` §3.19 is verified with **one correction**: bytecodes **0xC0–0xDF skip 1–32 tiles WITHOUT adding a wall**; only **0xE0–0xFF** skip 1–32 then add one wall. Precise decoder semantics (b = bytecode, n5 = b&0x1F, n4 = b&0xF):
> - `maze_decode(mazeptr)` copies header HT1/HT2/VT1/VT2 (offsets 7/8/9/0xA) to 0x904866/68/6A/6C; "last type" initializes to **HT2**; the tile cursor starts at slot 0x20 (row 0 is never written); data begins at maze+0xB; decode loops until cursor ≥ 0x400 (no terminator byte).
> - 0x40–0x7F: `(b>>4)&3` selects HT1/VT1/HT2/VT2 via pointer table 0x59B54; N = n4+1 (1–16); the *type byte's* top 2 bits select the §3.20 mode (00 = write N of type, 40 = N skips then 1 type, 80 = 1 type then N skips, C0 = N walls then 1 type); the type byte's low 6 bits are the element. N always comes from the bytecode's low nibble. Bit 4 of the bytecode (VT ranges) selects the vertical writer.
> - Writers: `maze_tile_write(slot,type,count)` = horizontal consecutive slots, returns next cursor; type 0 = advance only; it also **suppresses element 0x3C (MAZEOBJ_MONST_DRAGON) when game_mode==0 and level < 12** — dragons never spawn from maze data before level 12 in a normal game. `maze_tile_write_at` = vertical, stride 32 (31 for odd-angle mazes via level-flags long 0x90491C bit 26 + flags_4 bit 5), writes downward and returns slot+1.
> - Tile type constants confirmed against §3.14: 0 = floor/skip, 2 = MAZEOBJ_WALL_REGULAR.

---

### 4.2 Dragon Path Table Entry Format (ROM 0x5D578)

128-step circular path table with 16 bytes per entry (~2 KB). From DETAILED_REPORT.md:

- Bit 0 of control byte: **fire-trigger flag** (confirmed by disassembly)
- Access pattern: `(animation_counter >> 3) * 16 + path_index * 16`
- Remaining 15 bytes per entry (body segment shape, curvature, spacing): **not decoded**

> **Action needed:** Trace the `main_handle_dragon` (0x54454) loop that reads from this table to identify per-field semantics.

> **RESOLVED — the table's structure was misunderstood.** It is **5 path programs × 16 bytes = 80 bytes** (0x5D578–0x5D5C7), not 128×16 ≈ 2 KB. Row = `dragon_path_num` (0x904886, 0–4); byte index = `dragon_anim_ctr` (0x904892) >> 3 (one byte per 8-frame phase; the counter wraps at 128, which is where "128 steps" came from). Byte format: **bit 0 = fire trigger (confirmed)**; the full byte (0–7) is the head pose selector: `idx = byte + facing*4` indexes the head picture table 0x5D528, hpos-delta table 0x5D438 and vpos-delta table 0x5D478 (deltas added to the dragon MOB position produce the head position 0x904882/0x904884). Firing: bit 0 set + cooldown 0x90487C==0 + (0x90488C&0xF)<4 → shot alloc (0x540E8) then `dragon_fire_setup` (0x54748): cooldown=8, fireball spawns from the segment MOB chosen by signed-byte table 0x5D4B8[pose+facing*2] applied to the **4-word segment MOB-id array at 0x904894**. While locked-in (state bit 3), fire bytes hold the counter (sustained fire) until cooldown expires. The dragon only takes damage while a fire byte is active (mouth open) and not sleeping/turning; 9 hits kill it; each hit picks a new random path (0–4) and fast-forwards it to a byte matching the current pose for seamless animation. There are no per-entry "body segment shape/curvature/spacing" fields — body segments are separate MOBs (ids at 0x904894+2/4/6).

---

### 4.3 `resolve_shot_hit` (~0x4AF50) Not Individually Analyzed

FUNCTIONS_PLAN.md phase 7 describes this as "~0x500 bytes, dispatches on target type (player, monster, generator, chest, door, Death) applying damage, scoring, and despawning." It is the largest unindividualized function in the code.

> **Action needed:** Give `resolve_shot_hit` (0x4AF50) its own analysis entry covering dispatch table structure, per-type damage application, scoring, and MOB despawn path.

> **RESOLVED — fully analyzed.** See the new `resolve_shot_hit` section in `04_game_subsystems.md` (and the r2 comment at 0x4AF50). Highlights: signature `resolve_shot_hit(target, shooter) → 0` (shot survives: pierce/reflect) or `-1` (shot consumed); dispatch on `mob_link>>10` via 62-entry jump table at 0x4B336; damage tables 0x596B6/0x596C2/0x596CE; monster health lives in the target's hpos low nibble with per-type tier bases in table 0x5864C; generator tier degradation; secret-wall random prize spawner; supershot (0x905F68) / reflect (powers bit 10) mechanics; poison food/potion variants; per-level LFLAG4 shots-stun/shots-hurt friendly fire.

---

### 4.4 EEPROM Settings `0x904A24` — Bits 5–7 and 13 Unknown

Word at `0x904A24`, read from EEPROM slot 0xC at boot. Documented bit map:

| Bits | Meaning |
|------|---------|
| 0–4 | COINHEALTH setting (indexes `health_per_coin` table at 0x57862) |
| **5–7** | **Unknown** |
| 8–9 | Difficulty level (0–3) |
| 10 | 2-player mode flag |
| 11 | Sound mute flag |
| 12 | ROM version flag (cleared after first boot) |
| **13** | **Unknown** |
| 14 | Music/attract sound enable |
| 15 | Settings dirty flag (triggers player state reset in `init_monster_system`) |

> **Action needed:** Search for reads of `0x904A24` that mask or test bits 5–7 or 13.

> **RESOLVED — all 35 read sites of 0x904A24 examined.**
> - **Bits 5–7 (mask 0xE0) = "extra monsters" difficulty tuning (value 0–7).** Two readers: (1) `monsters_everything` (0x40E6A) at 0x40F5C — the per-frame monster processing cap = `int8(0x90405F)` + `monster_count_table` (0x40E46) `[(settings&0xE0)>>3 + players−1]`, capped at level×2 (except level 1), forced to 0 on `frame_overflow`. Table rows (players 1–4): v0: 4,11,15,18 … v7: 18,25,29,32 (+2 per row per value). Note: the 05_data_reference 0x40E46 entry previously attributed the index to "difficulty_setting" — difficulty (bits 8–9) is *not* involved. (2) `maze_addrandompickups` at 0x43FD4 — in single-player games with Warrior or Wizard, removes 1–3 random pickups (more at higher values).
> - **Bit 13 (mask 0x2000) = secret-room winner name-entry enable.** Single reader: `secret_getname` (0x54EC6) — see 2.2.

---

### 4.5 `ram.maze_pickup_config` Bit Layout Partially Documented

Word/longword at `ram.maze_pickup_config`. Only three field positions are confirmed from FUNCTIONS_PLAN.md analysis:

| Bits | Meaning |
|------|---------|
| 10:8 | Pickup quantity selector used by `maze_addrandompickups` |
| 14 | "Has food" flag — cleared by `maze_food_mob_consume` when only 1 food remains |
| Bit 2 of byte 3 | Checked by `get_random_maze_flags` to restrict certain random flags |

The maze catalog in DETAILED_REPORT.md refers to named flags (InvisWalls, CyclicWalls, ExitMoves, etc.) but their bit positions within `maze_pickup_config` are not mapped.

> **Action needed:** Document the complete bit layout from analysis of all functions that read `maze_pickup_config` (`maze_addrandompickups`, `main_open_doors`, `main_walls_cyclic_move`, etc.).

> **RESOLVED — identity established: `maze_pickup_config` IS the level-flags longword at 0x90491C.** `maze_load_pickup_config` (0x436FE) assembles maze header bytes 1–4 big-endian into it: byte 0 = `level_flags_1` (0x90491C), byte 1 = `level_flags_2` (0x90491D), byte 2 = `level_flags_3` (0x90491E), byte 3 = `level_flags_4` (0x90491F). The LFLAG enums in `05_data_reference.md` §3.12 are correct and now verified reader-by-reader (all 56 code references decoded). Corrections to this item's earlier claims:
> - "bits 10:8 pickup quantity" = long bits 10:8 = **LFLAG3 bits 0–2 = random food/pickup count** ✓.
> - **"bit 14 has food" was WRONG**: long bit 14 = LFLAG3 bit 6 = `EXIT_MOVES`, read by `main_exit_move` (0x528A0) and cleared by `maze_scan_objects` (0x43D8C, formerly misnamed `maze_food_mob_consume`) when only one exit exists, and by `main_exit_move` itself.
> - "byte 3 bit 2" = LFLAG4 bit 2 `TRAPS_LOCAL`, doubling as the inhibitor for the deep-level random flag additions in `get_random_maze_flags`.
> - Named maze flags map: InvisWalls = LFLAG2 bit 7 (all walls; checked ×5 in playfield draw code) and LFLAG1 bit 7 (trap walls only); CyclicWalls = LFLAG3 bit 3; ExitMoves = LFLAG3 bit 6; Exit1of = LFLAG3 bit 7 (choose-one, implemented in `maze_scan_objects`); WrapV/WrapH = LFLAG4 bits 4/5 (checked in scroll + shot movement; also picks the odd-angle vertical stride 31/32 in `maze_tile_write_at`); ShotStun/ShotHurt = LFLAG4 bits 0/1 (verified in `resolve_shot_hit`); fake exits = LFLAG4 bit 6; offscreen = LFLAG4 bit 7 (checked ×12 in monster movement).
> - Per-level randomization: LFLAG1 bits 2–3 are XOR'd with getrandom(4) every level; deep levels (past the designed 100) OR in `get_random_maze_flags` plus 0x30 (wraps) or 0xB0 (wraps+offscreen) unless TRAPS_LOCAL is set.

---

## 5. Remaining ROM Unknowns (~1% of ROM)

From ROM_COVERAGE.md and DETAILED_REPORT.md section "Remaining Unknowns":

### 5.1 Dragon Path Table Bit Fields — RESOLVED

**Corrected format:** 5 path programs × 16 bytes = 80 bytes (0x5D578–0x5D5C7); the "128×16 ≈ 2 KB" model was wrong (128 is the animation counter range; 16 bytes = 16 phases of 8 frames). Byte = (pose << 1) | fire: bit 0 = fire trigger ✓, byte value 0–7 = head pose selector combined with facing (`idx = byte + facing*4`) into head picture table 0x5D528 and hpos/vpos delta tables 0x5D438/0x5D478. Preceding tables in the region: 0x5D4B8 = signed fire-origin segment offsets. See 4.2 for full mechanics. Program data (hex rows): r0 `00 01 00 02 04 06 07 06 04 02 03 02 04 05 04 02`, r1 `00 02 04 06 07 05 03 01` ×2, r2 `00 01 03 02 04 06 07 05 04 02 03 05 04 02 03 01`, r3 `00 02 04 07 05 03 04 07 04 02 01 00 02 04 05 02`, r4 `00 03 04 07 06 05 02 01 02 04 07 05 04 02 03 01`.

**The ~1.1 KB the old model wrongly attributed to the dragon (0x5D5C8–0x5DA15) is now accounted for:**
- 0x5D5C8–0x5D7C7: `playfield_palettes` — **16 × 32-byte (16 IRGB words) playfield palettes, indexed by the maze header `playfield_colors` byte (0–15)**. The palette-setup function (~0x43490) copies entry index×32 into color RAM 0x910500; the word at entry+16 is also stored to 0x904020/0x90401E. This mapping was previously undocumented.
- 0x5D7C8 / 0x5D7E8: two special palettes, used when the palette index is ≥ 0x10 (references at 0x43526/0x43510; the pre-existing "palette A/B" rows overlap here).
- 0x5D808–0x5D9E7: additional 32-byte palette entries and the 13 × 32-byte color ramps (12 colors + 4 zero words each) already partially catalogued at 0x5D848.
- 0x5D9E8–0x5DA15: `secretcode_text_recs` — "SECRET CODE" / "REMEMBER YOUR" contest strings in the same {x, y, string-ptr} record format as the ENTER-YOUR records that follow at 0x5DA16 (referenced from 0x552EA).

> **New open item:** code at 0x41666 (monster region) references 0x5D978, which falls mid-block if the color-ramp stride is 32 bytes from 0x5D848 — the indexing scheme for that reference is untraced.

### 5.2 Dialog Tip Record Boundaries — RESOLVED

Pointer table is at **0x5815C** (12 longwords; the earlier "0x58154" included two unrelated longs). Each record = 3 longword string pointers (NULL = unused line) + inline NUL-terminated strings. Records span **0x5828C–0x5850C** (bytes 0x5825E–0x5828B are a separate, unidentified word table).

| # | Address | Len | Text |
|---|---------|-----|------|
| 0 | 0x5828C | 48 | "   BLUE   " / " SELECTED " / "   ELF    " (join-banner template) |
| 1 | 0x582BC | 42 | PUSH / MOVABLE / WALLS |
| 2 | 0x582E6 | 48 | SOME TREASURE / REQUIRES KEYS |
| 3 | 0x58316 | 60 | THERE CAN BE / MORE THAN ONE / TRAP |
| 4 | 0x58352 | 44 | ACID PUDDLES / MOVE RANDOMLY |
| 5 | 0x5837E | 72 | SOME WALLS CAN / BE SHOT AND TURN / INTO GOOD OR BAD |
| 6 | 0x583C6 | 72 | DEATH DIES AFTER / TAKING UP TO 200 / HEALTH |
| 7 | 0x5840E | 60 | HAVE FRIENDS / JOIN IN / ANY TIME |
| 8 | 0x5844A | 66 | MONSTERS FOLLOW / PLAYER WHO IS / IT |
| 9 | 0x5848C | 48 | SOME WALLS MOVE / RANDOMLY |
| 10 | 0x584BC | 52 | MONSTERS MAY MOVE / DIFFERENTLY |
| 11 | 0x584F0 | 29 | TAG, YOU'RE IT |

### 5.3 Tile Pattern → Descriptor Index Mapping — RESOLVED

Traced through `refresh_tile_visual` (0x5F5A0) → `pf_floor_draw` (0x5E888/0x5E892) and `pf_wall_draw` (0x5EAB8/0x5EAC2):

- **Floors:** `floorpattern` (0x904B5C) does *not* select a descriptor block. Descriptors come from the base block at 0x5BAE0 (variant chosen by wall proximity); the final tile code is offset by **floorpattern × 0x30** (48 tiles per floor set), plus palette attribute.
- **Walls:** an 8-neighbor connectivity mask (a neighbor counts if its picture ≠ 0x8000 or its link type is 0x3F floor) indexes the 256-byte variant table 0x5EE24 (alt table 0x5EF24 for wallpatterns 6/0xB). Descriptor base by `wallpattern` (0x904B5E): patterns 0–5 → 0x5BBE0 + word-offset table 0x5EDD4[pattern] (stride 0x44 units ≈ 17 descriptors/pattern); pattern 6 → 0x5D2F8; destructible (type 5) walls with pattern ≥ 6 → 0x5D3D0 (otherwise pattern forced to 5); patterns 7–0xA/0xC–0xF → **random per-tile**: getrandom(6) picks one of six descriptor-set pointers at 0x5EDF4 (pattern 7 uses a second group at +0x18). Final descriptor = base + variant×8, written as TL(+0)/BL(+0x80)/TR(+2)/BR(+0x82) words each +0x7000 into `vram.playfield + y*256 + x*4`.
- Fixed descriptors: transporter → 0x5CAA8, exit → 0x5C8A0, exit-to-6 → 0x5C8A8, forcefield hub → pointer table 0x5BA70 indexed by `(0x904066[slot]>>2)&0xF`.
- Invisible walls (LFLAG2 bit 7, or LFLAG1 bit 7 for trap walls) skip the draw except on level 9999.

---

## 6. Potentially Incorrect Information in Source Documents

The following items appeared in GAME_ROM_KNOWN.md or REPORT.md and may be inaccurate based on deeper analysis:

| Item | Source Claim | Assessment |
|------|-------------|------------|
| `main_thief_move` address | GAME_ROM_KNOWN.md: 0x4D8DC | **Wrong — confirmed a typo for 0x4E8DC.** 0x4D8DC is not a function entry at all: it is the epilogue of `show_continue_screen` (0x4D476) — `jsr secret_check`, maze#←maze_next, level←level_next, `unlk/rts`. The `main_thief_move` flag at 0x4D8DC has been removed. |
| `game_mode` variable | REPORT.md: "values ≤5 = pre-game, ≥0x73 = attract" (referring to `ram.os_flag`) | **Wrong.** Game mode is at `0x904918`; the values are 0=normal, 1=treasure exit, and 0xFFFF–0xFFFC for attract modes. `0x904000` is the maze number. |
| `0x904908` = `player_state` | REPORT.md section 3 | **Wrong.** See item 1.4. |
| Player health = 16-bit at unknown address | REPORT.md section 3 | **Wrong.** See item 1.5. |
| `0x44C7E` = `show_continue_screen` | REPORT.md section 8 | **Wrong.** See items 1.2 and 1.3. |
| `0x492C0` = `handle_generate` | REPORT.md section 2 | **Wrong.** See item 1.1. |

---

## 7. Assembly Disambiguation — `movea.l` Immediate Mode

Several radare2 disassembly listings display `movea.l 0x9XXXXX, an` which **appears** to be a memory dereference but is actually **IMMEDIATE mode** (loading the address literal into the register). Confirmed via raw byte inspection:

| Encoding | Instruction | Effect |
|----------|-------------|--------|
| `247c nnnnnnnn` | `MOVEA.L #imm.l, a2` | Load address literal into a2 |
| `267c nnnnnnnn` | `MOVEA.L #imm.l, a3` | Load address literal into a3 |
| `207c nnnnnnnn` | `MOVEA.L #imm.l, a0` | Load address literal into a0 |

This affects any analysis that assumed these instructions were dereferencing pointers. The dragon RAM locations at `0x904890–0x904894` are **direct word values** (not pointers), confirmed by raw byte checks. `ram.dragon_mob_id` (0x904894) is a direct word-sized MOB slot ID.

---

## 8. RAM Name Conflicts — GAME_ROM_KNOWN.md vs REPORT.md

The following addresses have different names in different source documents. REPORT.md names are from deeper instruction-level analysis and are generally more accurate.

| Address | GAME_ROM_KNOWN.md Name | REPORT.md Name | Notes |
|---------|----------------------|----------------|-------|
| 0x904063 | `trick_player` | `secret_room_player` | Player index in secret room (0xFF=none) |
| 0x904065 | `trick_tasknum` | `secret_room_active` | Non-zero if secret room active this level. Also holds the trick TYPE id (observed: 5 = shoot food, 9 = get hit by strong monster shot, 0x11 = shoot another player, 0x5A = supershot the treasure) |
| 0x904878 | `secret_possible_counter` | ~~`secret_score_thresh`~~ | **RESOLVED: GRK name correct.** Countdown in LEVELS (init 20, decremented once per level at 0x4A748); when 0, `maze_new_level_setup` may activate a secret room. REPORT's score interpretation refuted. *(This table previously listed 0x904878/0x90487A swapped.)* |
| 0x90487A | `secret_possible_start` | ~~`secret_score_ctr`~~ | **RESOLVED: GRK name correct.** Start/base value: `secret_check` adds 15 (max 40) when a player entered the secret room, subtracts 2 (min 4) when nobody did, then reloads the countdown. |
| 0x904870 | `secret_prev_maze` | ~~`secret_entry_frame`~~ | **RESOLVED: GRK name correct.** Receives the *maze number* (word read of 0x904000), not a frame count. |
| 0x904A9E | `dialog_timer` | `dialog_active` | Non-zero when dialog displayed; also counts down |
| 0x904B82 | `attract_title_count` | `continue_screen_active` | 1 when continue screen is showing |

---

## 9. Additional Function Name Conflicts (FUNCTIONS_PLAN.md vs GAME_ROM_KNOWN.md)

The deeper FUNCTIONS_PLAN.md analysis named some functions differently from the pre-existing GAME_ROM_KNOWN.md names when encountering them in call trees. GAME_ROM_KNOWN.md names are generally more authoritative.

| Address | GAME_ROM_KNOWN.md Name | FUNCTIONS_PLAN.md Name | Resolution (disassembly verified) |
|---------|----------------------|----------------------|-------|
| 0x45866 | `player_it_set` | ~~`write_escalator_exit`~~ | **GRK CONFIRMED.** Draws the letters 'I' (0x49) and 'T' (0x54) into the player's HUD column (0x905048 + (p*5+8)*128), plays a per-character "you're IT" speech from table 0x596F6, then 0xD4 (first IT) or 0xD3. Current IT player is the word at **0x9049DC** (`it_player`, 0xFFFF = none). Escalator name refuted. |
| 0x4590E | `player_it_unset` | ~~`write_escalator_entrance`~~ | **GRK CONFIRMED.** Writes two blank tiles (0xD000 \| p<<10) over the "IT" label. Escalator name refuted. |
| 0x45ACA | `player_inv_update` | ~~`setup_potion_visuals`~~ / `draw_player_items_hud` | **GRK CONFIRMED** (and Phase-8's `draw_player_items_hud` is the same concept). Draws the 12-slot inventory icon row in the player HUD (VRAM row pointer table [0x5FC12][p]): key icons (char 0xA1) × `player_keysnum` (0x90405A), potion icons × `player_potionsnum` (0x904055), blanks for the rest. Phase-5 "explosion MOB visuals" refuted. |
| 0x45940 | `flash_score_display` (Phase 24) | ~~`draw_player_name`~~ | **Phase 24 essentially correct.** Draws the player's 7-digit SCORE (`player_score` 0x904990[p]) via OS `display_decimal_value` (0x260) at row p*5+9, attribute from flash table 0x57350[p]; clears `player_redraw` **bit 0**. A more precise name would be `draw_player_score`. "draw_player_name" refuted. |
| 0x459A2 | `update_health_bar` (Phase 24) | ~~`draw_player_lives`~~ | **Phase 24 closest, but it is numeric, not a bar.** Draws the bonus multiplier "×N" (`player_bonusmult` 0x90490E[p], when >1) above the score row, then the 5-digit HEALTH value (`player_health` 0x904980[p]) at column 0x25; palette shifted −0x1000 (warning state via 0x904A26[p]) or −0x2000 (acid-slowed). Clears `player_redraw` **bit 1**. Precise name: `draw_player_health`. "draw_player_lives" refuted (Gauntlet has no lives). |
| 0x90487E | `item_dlg_flags` (byte) | `dragon_encounter_flag` | **Both partially right — it is one WORD bitfield `dialog_once_flags`** (covering GRK's 0x90487E *and* 0x90487F bytes). The dialog code tests bit (1<<id) at 0x4C7A0 and ORs table masks at 0x4C7B8; **bit 0 = dragon first-encounter dialog** (set at 0x4C482 — REPORT's "dragon_encounter_flag" was describing that one bit). Bit 0 cleared per level by `maze_new_level_setup` (0x438E0); whole word cleared at 0x4423C/0x449EE. |
| 0x90487F | `power_dlg_flags` (byte) | *(not re-analyzed)* | Subsumed by the word bitfield above — the high-numbered dialog bits live in this byte. |

---

## 10. Miscellaneous Notes

- Several RAM addresses in GAME_ROM_KNOWN.md have conflicting descriptions between sections (e.g., `0x904A66` appears twice with different descriptions: "possibly what part of the screen is visible" and "something to do with lobber shots").
- GAME_ROM_KNOWN.md's `0x904B7C` is labeled `attract_timer` but REPORT.md section 13 notes it is checked by `show_continue_screen` (must be ≠ 0xFFFF to show) and guesses it is `ram.continue_screen_inhibit`. These may coexist if the timer serves both purposes.
- REPORT.md section 13 notes `0x904066` (mob_anim array) may double as `ram.floor_anim_state[slot]` when read by `pf_floor_update` for type-0x3F floor animation state.
- REPORT.md section 13 notes the type-0x6 tile in `mob_link` (stored in `0x9048A0/0x9048A2`) is not definitively identified — possibly a player start marker or trapped area.
