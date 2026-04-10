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

---

### 2.2 `0x54EC6` — `secret_getname` vs `reset_attract_player`

| Source | Name | Description |
|--------|------|-------------|
| GAME_ROM_KNOWN.md | `secret_getname` | "Set up to get the player's name if they won the secret room" |
| REPORT.md section 7 | `secret_getname` | Sets up name entry screen for secret room winner; sets `ram.player_state = 2` for winning player |
| FUNCTIONS_PLAN.md (from 0x4D476 call tree) | `reset_attract_player` | "Resets attract-mode player animation state" |

> **Conflict:** Same situation as 2.1. Two sources agree on `secret_getname`. The `reset_attract_player` name came from call-tree context alone. Prefer `secret_getname` but flag as uncertain.

---

## 3. Functions Not Analyzed

### 3.1 `fcn_5F880` (0x5F880)

Listed in REPORT.md section 13 as not analyzed. Located near `pf_isdoor` (0x5F77A) and `pf_door_update_surrounding` (likely 0x5F7F0). Likely a door-adjacent tile helper — possibly `update_wall_connection` (see FUNCTIONS_PLAN.md for 0x5F876). Does not appear as a named function in FUNCTIONS_PLAN.md.

> **Action needed:** Disassemble and identify. Given the neighborhood (door graphics helpers), likely handles selection of the correct door-segment graphic variant.

---

## 4. Missing Detail — Documented But Incomplete

### 4.1 `maze_decode` RLE Format Not Documented

REPORT.md and DETAILED_REPORT.md describe the format as "run-length encoded; each run specifies tile type and count" but never give the actual byte encoding. The actual bytecodes are listed in the `Maze Compression Bytecodes` enum in `05_data_reference.md` (from GAME_ROM_KNOWN.md), but the precise relationship to the HT1/HT2/VT1/VT2 horizontal/vertical type bytes is not fully traced through the decoder.

> **Action needed:** Decompile `maze_decode` (0x4C1BC) and verify the bytecode encoding matches the enum.

---

### 4.2 Dragon Path Table Entry Format (ROM 0x5D578)

128-step circular path table with 16 bytes per entry (~2 KB). From DETAILED_REPORT.md:

- Bit 0 of control byte: **fire-trigger flag** (confirmed by disassembly)
- Access pattern: `(animation_counter >> 3) * 16 + path_index * 16`
- Remaining 15 bytes per entry (body segment shape, curvature, spacing): **not decoded**

> **Action needed:** Trace the `main_handle_dragon` (0x54454) loop that reads from this table to identify per-field semantics.

---

### 4.3 `resolve_shot_hit` (~0x4AF50) Not Individually Analyzed

FUNCTIONS_PLAN.md phase 7 describes this as "~0x500 bytes, dispatches on target type (player, monster, generator, chest, door, Death) applying damage, scoring, and despawning." It is the largest unindividualized function in the code.

> **Action needed:** Give `resolve_shot_hit` (0x4AF50) its own analysis entry covering dispatch table structure, per-type damage application, scoring, and MOB despawn path.

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

---

## 5. Remaining ROM Unknowns (~1% of ROM)

From ROM_COVERAGE.md and DETAILED_REPORT.md section "Remaining Unknowns":

### 5.1 Dragon Path Table Bit Fields

**Location:** ROM 0x5D578, ~2 KB total  
**Format:** 128-step × 16-byte entries. Accessed via `(animation_counter >> 3) * 16 + path_index * 16`.  
**Known:** Control byte bit 0 = fire-trigger flag.  
**Unknown:** Remaining 15 bytes per entry — body segment shape, curvature, and inter-segment spacing fields.

### 5.2 Dialog Tip Record Boundaries

**Location:** ~600 bytes at ROM 0x5825E–0x584F0  
**Known:** Contains per-level tip display records (3-pointer + 3-string groups). The 12-entry pointer table at 0x58154 points into this range.  
**Unknown:** Exact count and individual record boundaries not exhaustively listed.

### 5.3 Tile Pattern → Descriptor Index Mapping

The ~450 tile sprite descriptors at 0x5BAE0–0x5C88F are organized as 32-entry blocks per tileset. The entry format is known (4 words = 2×2 tile, order TL/BL/TR/BR). However, the mapping from maze header `wallpattern` (0–15) and `floorpattern` (0–15) bytes to specific descriptor block indices has not been traced for all combinations. The code in `refresh_tile_visual` (0x5F5A0) selects tables via pointer indirection, making the mapping non-obvious.

---

## 6. Potentially Incorrect Information in Source Documents

The following items appeared in GAME_ROM_KNOWN.md or REPORT.md and may be inaccurate based on deeper analysis:

| Item | Source Claim | Assessment |
|------|-------------|------------|
| `main_thief_move` address | GAME_ROM_KNOWN.md: 0x4D8DC | **Wrong.** DETAILED_REPORT.md confirms the main loop calls 0x4E8DC (renamed `main_thief_anim`). The 0x4D8DC address may be an internal sub-function. |
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
| 0x904065 | `trick_tasknum` | `secret_room_active` | Non-zero if secret room active this level |
| 0x90487A | `secret_possible_counter` | `secret_score_ctr` | Score accumulated in secret room |
| 0x904878 | `secret_possible_start` | `secret_score_thresh` | Score threshold to win secret room |
| 0x904870 | `secret_prev_maze` | `secret_entry_frame` | Frame when player entered secret room |
| 0x904A9E | `dialog_timer` | `dialog_active` | Non-zero when dialog displayed; also counts down |
| 0x904B82 | `attract_title_count` | `continue_screen_active` | 1 when continue screen is showing |

---

## 9. Additional Function Name Conflicts (FUNCTIONS_PLAN.md vs GAME_ROM_KNOWN.md)

The deeper FUNCTIONS_PLAN.md analysis named some functions differently from the pre-existing GAME_ROM_KNOWN.md names when encountering them in call trees. GAME_ROM_KNOWN.md names are generally more authoritative.

| Address | GAME_ROM_KNOWN.md Name | FUNCTIONS_PLAN.md Name | Notes |
|---------|----------------------|----------------------|-------|
| 0x45866 | `player_it_set` | `write_escalator_exit` | GAME_ROM_KNOWN.md name is pre-existing and authoritative. FUNCTIONS_PLAN.md renamed it when found in Phase 8 call tree without cross-checking. |
| 0x4590E | `player_it_unset` | `write_escalator_entrance` | Same situation. The "escalator" names appear to be AI-generated and incorrect. |
| 0x45ACA | `player_inv_update` | `setup_potion_visuals` (Phase 5) / `draw_player_items_hud` (Phase 8) | GAME_ROM_KNOWN.md: "update display of player inventory (keys/potions/powers)". The Phase 5 description says it "create[s] explosion MOB visuals" at this address — possibly incorrect. Phase 8 "draw_player_items_hud" is consistent with player_inv_update. |
| 0x45940 | `flash_score_display` (Phase 24) | `draw_player_name` (Phase 8 call tree) | Phase 24 analysis: draws score digits with flash attribute. Phase 8 sub-call tree: draws character name tile in score HUD. Both come from within `player_cleanup_slot`; unclear if these are the same function serving dual purposes or a misidentification. |
| 0x459A2 | `update_health_bar` (Phase 24) | `draw_player_lives` (Phase 8 call tree) | Same conflict pattern as above. Phase 24: draws health bar MOBs. Phase 8: draws life-counter icons in HUD. |
| 0x90487E | `item_dlg_flags` (byte) | `dragon_encounter_flag` | GAME_ROM_KNOWN.md: "flags for item use dialogs to only display once". REPORT.md: "bit 0 = encounter triggered this level". These cannot both be correct. Deep analysis (REPORT.md) is more reliable, but the GAME_ROM_KNOWN.md name was pre-existing knowledge. |
| 0x90487F | `power_dlg_flags` (byte) | *(not re-analyzed)* | GAME_ROM_KNOWN.md: "flags for power dialogs to only display once". No cross-check available. |

---

## 10. Miscellaneous Notes

- Several RAM addresses in GAME_ROM_KNOWN.md have conflicting descriptions between sections (e.g., `0x904A66` appears twice with different descriptions: "possibly what part of the screen is visible" and "something to do with lobber shots").
- GAME_ROM_KNOWN.md's `0x904B7C` is labeled `attract_timer` but REPORT.md section 13 notes it is checked by `show_continue_screen` (must be ≠ 0xFFFF to show) and guesses it is `ram.continue_screen_inhibit`. These may coexist if the timer serves both purposes.
- REPORT.md section 13 notes `0x904066` (mob_anim array) may double as `ram.floor_anim_state[slot]` when read by `pf_floor_update` for type-0x3F floor animation state.
- REPORT.md section 13 notes the type-0x6 tile in `mob_link` (stored in `0x9048A0/0x9048A2`) is not definitively identified — possibly a player start marker or trapped area.
