# FIXME — Known Errors and Gaps in Analysis

Issues identified by reviewing REPORT.md, FUNCTIONS_PLAN.md, DETAILED_REPORT.md, ROM_COVERAGE.md, and GAME_ROM_KNOWN.md for consistency.

---

## Critical Errors / Factual Contradictions

### 1. `0x492c0` is misidentified in REPORT.md

**REPORT.md** calls it `handle_generate` and describes generator spawning logic: "Checks ram.monster_count against the level cap. Spawns a new monster MOB at the generator position using the maze-encoded monster type."

**FUNCTIONS_PLAN.md** (deeper analysis) identifies it as `monster_generic_handler` — the core movement/AI handler for standard monster types (ghosts, grunts, demons, lobbers, death). Arguments: `(mob_id: long, monster_type_index: long, speed: long)`. Generator spawning is handled *inline* within `monster_loop_core` at `0x41026`, not here.

**Action:** Correct REPORT.md section 2's description of `0x492c0`. The function is the per-monster movement/AI handler, not a generator spawner.

---

### 2. `0x44c7e` has conflicting names and descriptions

**REPORT.md section 8** renames it `show_continue_screen`: "Displays the PRESS START WITHIN X SECONDS TO CONTINUE GAME AT THIS LEVEL screen. Plays sound 0x3b, sets ram.continue_screen_active (0x904b82) = 1."

**FUNCTIONS_PLAN.md** (call-tree analysis) identifies it as `update_maze_player_count`: "Decrements 0x904928, triggers all-dead state if 0." This is a small utility function.

These cannot be the same function. FUNCTIONS_PLAN.md's description is more specific and comes from actual instruction tracing.

**Action:** `0x44c7e` is almost certainly `update_maze_player_count`. The "show continue screen" behavior REPORT.md attributed to it belongs elsewhere (see item 3). Correct REPORT.md section 8.

---

### 3. `0x4d476` — direct contradiction between documents

**REPORT.md section 13** (Remaining Unknowns): "fcn_4d476 (0x4d476): Not analyzed."

**FUNCTIONS_PLAN.md phase 8**: Lists `0x4d476` as `show_continue_screen` with status DONE and a full sub-call tree analyzed:
- `0x4d1a4` check_coin_eligibility
- `0x4d900` count_active_players
- `0x489b8` remove_dying_player_sprites
- `0x486fe` (see item 6)
- `0x54ec6` (see item 7)

**GAME_ROM_KNOWN.md** described it as "handles exiting the treasure room with people still active."

**Action:** Reconcile. FUNCTIONS_PLAN.md's analysis of `0x4d476` should supersede REPORT.md's "not analyzed" claim. Remove from Remaining Unknowns in REPORT.md. Verify whether the name `show_continue_screen` or the GAME_ROM_KNOWN.md description ("treasure room exit with active players") is more accurate — these could be the same screen (continue screen shown when exiting treasure room) or different entry points.

---

### 4. RAM `0x904908` is misidentified in REPORT.md

**REPORT.md section 3**: `ram.player_state (0x904908..0x90490e)` — "0=inactive, 1=active, 2=winning secret room, 3=exiting, 4=entering name"

**FUNCTIONS_PLAN.md** (from coincheck and main_move_players instruction analysis): `player_redraw[4]` at `0x904908` — per-player redraw flags (bytes). The player status/state array is at `0x9049A0`.

GAME_ROM_KNOWN.md was already uncertain about this address ("something involving player collisions").

**Action:** Correct REPORT.md section 3. `0x904908` = `player_redraw` flags. `0x9049A0` = player status bytes. Any code in REPORT.md that uses `ram.player_state` at `0x904908` with status values 0/1/2/3/4 is referencing the wrong address.

---

### 5. Player health width is wrong in REPORT.md

**REPORT.md section 3**: `ram.player_health — 16-bit health (0 = dead)`

**FUNCTIONS_PLAN.md** (multiple functions): `player_health[4]` at `0x904980` as **longwords** (32-bit). The acid damage path explicitly reads/writes `0x904980+d4*4` (longword stride).

**Action:** Correct REPORT.md. Health is a 32-bit longword at `0x904980`, not a 16-bit word. No specific address was given in REPORT.md's player array table — add `0x904980` explicitly.

---

## Name Conflicts — Require User Clarification

Both of the following were named in GAME_ROM_KNOWN.md (pre-provided authoritative knowledge) but were renamed in FUNCTIONS_PLAN.md after being found in the `show_continue_screen (0x4d476)` call tree without cross-checking original names.

### 6. `0x486fe` — `secret_check` vs `update_bgm_volume`

- **GAME_ROM_KNOWN.md**: `secret_check` — "check to see if we should enter secret room?"
- **REPORT.md section 7**: `secret_check` — detailed description: reads secret room monster type from maze data byte 0, tracks player score in secret room via `ram.secret_score_ctr`, gated by `ram.secret_room_active (0x904065)`
- **FUNCTIONS_PLAN.md** (found in 0x4d476 call tree): `update_bgm_volume` — "Updates background music volume/fade"

**Question for user:** Is the pre-existing identification `secret_check` still correct, or does this function actually update BGM volume? If the function truly checks secret rooms, FUNCTIONS_PLAN.md's renaming is wrong and should be reverted.

---

### 7. `0x54ec6` — `secret_getname` vs `reset_attract_player`

- **GAME_ROM_KNOWN.md**: `secret_getname` — "set up to get the player's name if they won the secret room"
- **REPORT.md section 7**: `secret_getname` — "Sets up the name entry screen for a player who won the secret room challenge. Sets ram.player_state = 2 for the winning player."
- **FUNCTIONS_PLAN.md** (found in 0x4d476 call tree): `reset_attract_player` — "Resets attract-mode player animation state"

**Question for user:** Same issue as above. Is `secret_getname` still correct? If so, FUNCTIONS_PLAN.md's renaming should be reverted.

---

## Functions Not Analyzed

### 8. `fcn_5f880` (0x5f880)

Listed in REPORT.md section 13 as "Not analyzed. Located near `pf_isdoor`/`pf_door_update_surrounding`, likely a door-adjacent tile helper." Does not appear in FUNCTIONS_PLAN.md at all.

**Action:** Analyze this function.

---

## Missing Detail (Documented But Incomplete)

### 9. `maze_decode` RLE format not documented

REPORT.md and DETAILED_REPORT.md describe the format as "run-length encoded; each run specifies tile type and count" but never give the actual byte encoding. Questions left open:
- Are type and count packed into one byte, or separate bytes?
- What is the bit layout of a run entry?
- How are wall-type and floor-type tiles encoded vs. object tiles?

**Action:** Decompile `maze_decode` (0x4c1bc) and document the RLE byte format explicitly.

---

### 10. Dragon path entry format (0x5D478) — only 1 byte decoded

ROM_COVERAGE.md documents 128-step × 16-byte entries. Only bit 0 of the first byte (fire flag) is documented. The remaining 15 bytes per entry (body segment shape, curvature, spacing) are not decoded.

**Action:** Analyze the loop in `main_handle_dragon` (0x54454) that reads from this table to decode the remaining fields.

---

### 11. `resolve_shot_hit` (~0x4af50) not individually analyzed

FUNCTIONS_PLAN.md phase 7 (`main_handle_shots`) describes this as "~0x500 bytes, dispatches on target type (player, monster, generator, chest, door, Death) applying damage, scoring, and despawning." No separate analysis entry exists for it despite it being large and handling all combat resolution.

**Action:** Give `resolve_shot_hit` (0x4af50) its own analysis entry covering at minimum: dispatch table structure, per-type damage application, scoring, and MOB despawn path.

---

### 12. EEPROM settings `0x904A24` bits 5–7 and 13 unknown

Documented in REPORT.md section 13. Known bits: 0–4 = COINHEALTH, 8–9 = difficulty, 10 = 2P mode, 11 = mute, 12 = ROM version, 14 = music enable, 15 = dirty flag. Bits 5–7 and 13 have no identified meaning.

**Action:** Search for reads of `0x904A24` that mask or test bits 5–7 or 13 to identify their purpose.

---

### 13. `ram.maze_pickup_config` bit layout is partially documented

REPORT.md/FUNCTIONS_PLAN.md document only three fields: bits 10:8 (pickup quantity), bit 14 (has food), and bit 2 of byte 3. The maze catalog in DETAILED_REPORT.md refers to many named flags (InvisWalls, CyclicWalls, ExitMoves, etc.) but their bit positions within `maze_pickup_config` are not mapped.

**Action:** Document the complete bit layout of `ram.maze_pickup_config` from analysis of the functions that read it (`maze_addrandompickups`, `main_open_doors`, `main_walls_cyclic_move`, etc.).
