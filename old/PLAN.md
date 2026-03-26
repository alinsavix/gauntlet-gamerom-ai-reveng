# Gauntlet II ROM Reverse Engineering Plan

## Context

Ongoing reverse engineering of the Gauntlet II arcade game (Motorola 68010). Three ROM files:
- `row9.bin` → mapped at `0x000000` (OS ROM, already fully analyzed in OS_ROM.md — do not re-analyze)
- `row10.bin` → mapped at `0x038000` (Slapstic/level data ROM)
- `row76.bin` → mapped at `0x040000` (Game ROM, 256KB, primary target)

The game ROM is **largely compiled C code** (old compiler, possibly nonstandard calling convention). Some sections may be hand-crafted assembly typical of embedded systems. Treat register/stack usage empirically — don't assume a specific ABI.

Existing knowledge is in `GAME_ROM_KNOWN.md`. The radare2 project `gauntlet.r2` has prior analysis. Output goes to `REPORT.md` and into the r2 project.

**Naming policy**: Name functions, RAM locations, and ROM tables as soon as their purpose is clear. Update names if better understanding is discovered later.

**Ask for help**: If something is unclear after reasonable analysis effort, ask the user for clarification rather than guessing.

---

## Phase 1: Setup (Session Initialization)

1. **Check for existing session** via `mcp__radare2__list_sessions`
2. **Open session** with `mcp__radare2__open_session` if none exists; open `row9.bin` with `mcp__radare2__open_file`
3. **Load project**: `Po gauntlet.r2` via `mcp__radare2__run_command`
4. **Fix duplicate mappings**: Run `om` to list all file mappings. If row9.bin appears more than once, remove extras with `om- <id>` keeping only the mapping at physical `0x0`
5. **Verify layout**:
   - `row9.bin` at `0x000000`
   - `row10.bin` at `0x038000`
   - `row76.bin` at `0x040000`
6. **Save checkpoint**: `PS gauntlet.r2`

---

## Phase 2: Main Loop & Game Initialization

### 2.1 Jump Table Verification (0x40000–0x40054)
- Disassemble the 10 JMP entries at game ROM start
- Confirm all targets match GAME_ROM_KNOWN.md section 2.2

### 2.2 Game Start (0x4014c — `game_start`)
- Decompile to understand initialization order
- Identify all RAM regions initialized and with what values
- Look for ROM data tables being loaded

### 2.3 Main Loop (0x42a66 — `m2mainloop`)
- Decompile to map per-frame call sequence
- Verify each `main_*` function is accounted for in GAME_ROM_KNOWN.md section 2.3
- Identify any unlisted functions called
- Note game_mode dispatch logic (e.g., GAMEMODE_NORMAL, GAMEMODE_TITLE, etc.)

**Save**: `PS gauntlet.r2`

---

## Phase 3: Monster System

Target functions:
- `monsters_everything` (0x40e6a) — entry point for all monster logic per frame
- `monster_find_and_shoot` (0x41750) — targeting, direction setting, shooting decision
- `monster_create_shot` (0x490dc) — shot mob creation
- `handle_generate` (0x492c0) — generator spawning logic
- `main_move_monsters` (0x49034) — per-frame monster movement dispatch
- `death_potion` (0x49446) — death killed by potion
- `death_damagetrack` (0x49a3c) — death damage tracking
- `find_unused_shot` (0x41b16) — find a free shot slot
- `monster_playerhit` (0x495a6) — monster hitting a player

For each: decompile, understand parameters, rename local variables, add comments in r2.

Identify and name any unlisted helper functions called by the above.

**Save**: `PS gauntlet.r2`

---

## Phase 4: Player System

Target functions:
- `main_move_players` (0x4a53a) — per-frame player movement
- `player_resetcounters` (0x43360) — all player state fields reset
- `player_resetall` (0x4341e) — reset all players
- `player_it_set` (0x45866) / `player_it_unset` (0x4590e) — IT mechanic
- `player_inv_update` (0x45aca) — inventory display
- `player_add_score_with_mult` (0x5214c) — scoring with bonus multiplier
- `player_lowhealth` (0x487ca) — low health handling / dying flag
- `player_coindrop` (0x488ca) — coin drop / health from coin
- `player_join` (0x48bb6) / `player_join2` (0x48a36) — player joining
- `sound_player_hurt` (0x49a98) — hurt sound logic
- `player_activecount` (0x4d900) — count active players
- `player_tport` (0x50224) — player uses transporter

For each: understand arguments (player number typically passed in a register), verify/clarify RAM arrays (health, score, status, powers, etc.).

Fill gaps in RAM table (0x904908–0x9049c4 range).

**Save**: `PS gauntlet.r2`

---

## Phase 5: Level/Maze System

Target functions:
- `find_maze` (0x40c78) — maze lookup by number, slapstic bank in d1
- `maze_setupnew` (0x44ac2) — full new maze setup
- `maze_decode` (0x4c1bc) — maze data decompression
- `maze_addrandompickups` (0x43f68) — random pickup placement
- `maze_randomplace` (0x42e9a) — place an object randomly in maze
- `maze_show` (0x4526a) / `maze_hide` (0x4529a) — alpha layer show/hide
- `maze_checknum` (0x52eca) — maze number validation/wraparound
- `level_splash` (0x4be24) — new level splash screen
- `setup_infopanel` (0x452d0) — right-side info panel

Clarify maze data structure (fix/extend the table in GAME_ROM_KNOWN.md with actual field offsets from maze_decode).

Understand slapstic bank switching integration (`slapstic_cmd_bitwise` at 0x43826, etc.).

**Save**: `PS gauntlet.r2`

---

## Phase 6: Thief, Mugger & Exit Systems

### Thief/Mugger:
- `thief_target_calc` (0x4dff6) — wealth calculation and target selection
- `thief_setup` (0x4e432) — thief initialization for level
- `thief_timer_set` (0x4e4d8) — timer based on wealth/level
- `main_start_thief` (0x4deb8) — wait and deploy thief
- `main_thief_move` (0x4e8dc) — thief movement state machine
- `thief_exit` (0x4e122) — thief departing logic

Fill thief RAM unknowns: 0x904b9c, 0x904ba2–0x904ba6, 0x904bbc.

### Exit System:
- `main_exit_move` (0x5287c) — moving exit logic
- `exit_get_id` (0x52b06) — exit ID lookup
- `exit_create_player_anim` (0x5df80) — player exit animation
- Unknown at 0x52b40 — player exiting sequence

**Save**: `PS gauntlet.r2`

---

## Phase 7: Transporter & Forcefield Systems

Target functions:
- `handle_tport` (0x47cfe) — transporter activation handling
- `tport_find_id` (0x4e7c0) — transporter ID lookup
- `tport_check_dest` (0x50ade) — validate transport destination
- `tport_create_splodey` (0x5df8e) — transport explosion animation
- Unknown at 0x50616, 0x50662 — transporter-related, determine purpose

Fill transporter RAM unknowns: 0x904bc4–0x904bea.

Forcefield:
- `pf_isff` (0x5fc5e) — check if coordinate has forcefield
- RAM: 0x904042 (pointer), 0x904046 (color), 0x904048 (unknown)

**Save**: `PS gauntlet.r2`

---

## Phase 8: Dragon System

Target functions:
- `main_handle_dragon` (0x54454) — full dragon state machine (sleeping, stunned, turning, locked)
- Unknown at 0x549ea — likely dragon-related helper
- `secret_check` (0x486fe) — check if secret room should be entered
- `secret_getname` (0x54ec6) — get name if player won secret room

Fill dragon RAM unknowns: 0x90487c, 0x904882, 0x904884, 0x904892, 0x904894.

**Save**: `PS gauntlet.r2`

---

## Phase 9: Scoring, Coin & Dialog Systems

### Scoring/Coin:
- `coincheck` (0x42b6a) — coin insertion handling
- `calc_score_per_coin` (0x40628) — score-per-coin calculation
- `playfield_showscore` (0x49498) — overlay score on screen for kill/eat
- `player_add_score_with_mult` (0x5214c) — score with bonus multiplier
- Unknown at 0x49d0e — high score check

Identify RAM unknowns: 0x9049e2 (game pricing), 0x9049ea (coin count).

### Dialog:
- `dialog_first_encounter` (0x4c440) — first-encounter dialog handling
- `player_give_item_with_message` (0x4c72a) — give item with dialog
- Unknown at 0x4c70a — clear message buffer
- Unknown at 0x4cb50 — dialog box placement

Fill dialog RAM unknowns: 0x904aa0, 0x904aa2, 0x904aa4.

**Save**: `PS gauntlet.r2`

---

## Phase 10: Remaining Unknown Functions & Cleanup

Investigate remaining partially-known/unnamed functions:
- `0x436cc`, `0x436fe` — random maze flags
- `0x438ae` — new maze/level setup helper
- `0x43d8c` — adds random foods to maze
- `0x44c7e` — dialog-related
- `0x47c0e` — explosion animation handling
- `0x511ac` — collision handling
- `0x52b40` — player exiting sequence
- `0x5df5a`, `0x5df68`, `0x5df72` — shot graphics helpers
- `0x5df9c` — explosion animation creation
- `0x5e064` — unlink/free a shot
- `0x5e584` — transporter destination check

Also analyze key utility functions if not yet understood:
- `getrandom` (0x5fc5e) — random number generator
- `memclear` (0x5fd58) / `memcpy` (0x5fd6a) — memory utilities
- `pf_replace` (0x5f31e) — playfield tile replacement
- `pf_floor_update` (0x5e892) — floor pattern update

Review all RAM unknowns and provide best-guess names for anything determinable.

**Final save**: `PS gauntlet.r2`

---

## Phase 11: Output — REPORT.md

Create `/mnt/d/Users/alinsa/Documents/SmartGit/gauntlet-game-ai-reveng-claude/REPORT.md` with:
- **New findings per subsystem** — functions newly named, understood, or corrected
- **Data structure clarifications** — especially maze data and MOB array
- **RAM variable identifications** — newly named or corrected
- **Corrections** — any entries in GAME_ROM_KNOWN.md that appear wrong based on analysis
- **Remaining unknowns** — what couldn't be determined and why

---

## Key Files

- `gauntlet.r2` — r2 project (load with `Po gauntlet.r2`, save with `PS gauntlet.r2`)
- `row76.bin` — Game ROM (primary analysis target)
- `row10.bin` — Slapstic ROM (level data)
- `GAME_ROM_KNOWN.md` — existing knowledge base
- `soundcmds.csv` — sound command reference (useful for identifying code by sound usage)
- `REPORT.md` — output file (create/update throughout)

---

## Important Notes

- **Never re-analyze row9.bin** (OS ROM — already done)
- **Save with `PS`** (uppercase) after each phase — if it fails, create `emergency.r2` manually and stop
- **Big-endian CPU** — 68010 word/longword byte order is MSB-first
- **Calling convention**: Likely some old nonstandard C convention. Determine empirically from call sites — don't assume registers/stack ABI
- **Sound IDs** from `soundcmds.csv` are a strong clue to function purpose
- **Ask the user** if analysis of a function is unclear after reasonable effort
- **Name things immediately** — don't wait to name functions, RAM locations, or ROM tables once purpose is known; refine names as understanding deepens
