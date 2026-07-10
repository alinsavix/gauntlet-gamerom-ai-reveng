# Gauntlet II — Game ROM Structure

*Main loop, calling conventions, ROM layout, and coverage analysis for row76.bin.*

---

## 1. Game ROM Overview

- **File:** `row76.bin`
- **Address:** `0x040000–0x05FFFF` (128 KB, note: game ROM maps 0x040000–0x07FFFF as 256 KB but code/data fits in 128 KB)
- **Language:** C (Green Hills C compiler for 68000-family), plus hand-written assembly for a few leaf functions
- **Functions:** ~170 compiled C functions, all fully documented

### 1.1 ROM Layout

| Region | Address Range | Size | Content |
|--------|--------------|------|---------|
| Code | 0x40000–0x5561F | ~87 KB | All 170 compiled C functions + hand-written asm |
| Padding | 0x55620–0x56E53 | ~6 KB | Unused 0xFF (erased EPROM space) |
| Slapstic Trampolines | 0x56E54–0x56F00 | ~170 B | Bank-switch helper code (3 small functions) |
| Data Tables | 0x56F00–0x5FFB1 | ~37 KB | ROM tables, strings, palettes, animation data, tile descriptors |
| End Padding | 0x5FFB2–0x5FFFE | 76 B | Unused 0xFF |

### 1.2 Jump Table (`0x40000–0x40054`)

Ten JMP entries at fixed offsets, called from the OS ROM:

| Address | Target | Function |
|---------|--------|----------|
| `0x40000` | `0x4014C` | `game_start` — entry point from OS |
| `0x40006` | — | `game_vblank` — VBLANK handler |
| `0x4000C` | — | `game_irq1` handler |
| `0x40012` | — | `game_irq3` handler |
| `0x40018` | — | `game_irq2` handler |
| `0x4001E` | — | `game_irq6` handler |
| `0x40024` | — | `game_exception` handler |
| `0x40030` | — | `game_pf_init` — playfield initialization |
| `0x40042` | — | `game_vblank_hook` — supplemental VBLANK (input reading) |
| `0x40048` | — | `game_attract` — attract mode handler |
| `0x40054` | `0x56EAA` | `game_eeprom_config` — EEPROM config provider |

---

## 2. Main Loop Structure

### 2.1 Verified Main Loop Call Sequence (`m2mainloop`, 0x42A66)

> **Correction from REPORT.md:** The main loop does NOT execute everything every frame. It has a two-level conditional structure.

```
m2mainloop (0x42a66):
    link a6, #-4
    a2 = #0x904002              ; → VBLANK semaphore
    jsr one_time_init (0x4327a) ; runs once before first VBLANK
    a3 = address of local var

VBLANK_WAIT (0x42a7e):
    if (0x904002) == 0:         ; spin until VBLANK handler sets this
        clear local var
        goto VBLANK_WAIT

    (0x904006) += 1             ; increment frame counter
    (0x904002) = 0              ; clear VBLANK semaphore
    copy (0x904020) → (0x90401e)    ; save playfield color

    ── ALWAYS CALLED (every frame, all modes) ──────────────
    jsr main_logo_updcolors         (0x4dcba)
    jsr input_debounce              (0x40644)
    jsr coincheck                   (0x42b6a)

    ── DIALOG GATE ─────────────────────────────────────────
    if (0x904a9e) != 0:         ; dialog_timer active?
        goto SKIP_GAMEPLAY      ; YES → skip all 16 gameplay functions

    ── GAMEPLAY FUNCTIONS (skipped when dialog is active) ──
    jsr main_cycle_tport_and_ffield (0x40528)
    jsr main_handle_potions         (0x46fea)
    jsr main_open_doors             (0x45c00)
    jsr main_handle_shots           (0x474f6)
    jsr main_move_players           (0x4a53a)   ← has internal game_mode check
    jsr main_scroll_playfield       (0x46caa)
    jsr main_move_monsters          (0x49034)   ← gated by active player count
    jsr main_handle_dragon          (0x54454)
    jsr main_thief_anim             (0x4e8dc)   ← address corrected from GAME_ROM_KNOWN.md
    jsr main_start_thief            (0x4deb8)
    jsr main_health_countdown       (0x466f6)
    jsr main_treasure_timer         (0x4d29e)
    jsr main_handle_death           (0x4664c)
    jsr main_exit_move              (0x5287c)
    jsr main_walls_cyclic_move      (0x5e62a)
    jsr main_walls_random_move      (0x5e41a)

SKIP_GAMEPLAY (0x42b14):
    ── ALWAYS CALLED (every frame, all modes) ──────────────
    jsr main_msgbox_countdown       (0x4ccbc)
    jsr pick_character              (0x42df4)
    jsr main_start_game             (0x4800c)
    jsr main_score_update           (0x4715e)
    jsr main_score_display          (0x457c0)
    jsr main_attract                (0x44562)   ← attract mode state machine
    jsr eeprom_timer                (0x431ee)   ← periodic EEPROM write
    jsr sound_response              (0x42d0a)   ← process sound CPU responses
    jsr main_update_sound           (0x4ae20)

    ── FRAME OVERFLOW CHECK ─────────────────────────────────
    if (0x904002) != 0:         ; another VBLANK already?
        (0x904916) = 8          ; frame took too long
    else:
        (0x904916) >>= 1       ; decay overflow counter

    goto VBLANK_WAIT
```

### 2.2 VBLANK Synchronization

The game's VBLANK handler implementation is at **`0x4017E`**, reached via the jump table entry at `0x40006`. The VBLANK semaphore is at `0x904002` (word). The OS VBLANK handler sets it each field. The main loop spins on it, clears it after processing, and detects frame drops via `0x904916` (set to 8 if a second VBLANK occurred before processing finished).

> **Correction from REPORT.md:** The semaphore is at `0x904002`, not in `ram.os_flag` at `0x904000`. `0x904000` is the maze number.

### 2.3 Game Mode Variable

> **Correction from REPORT.md:** The game mode variable is `game_mode` at `0x904918`, **not** `ram.os_flag`. REPORT.md's description of "values below 0x5 are pre-game, 0x5–0x72 are normal gameplay" referred to the maze number, not game mode.

Game mode values:

| Value | Meaning |
|-------|---------|
| `0x0000` (GAMEMODE_NORMAL) | Normal gameplay |
| `0x0001` (GAMEMODE_TREAS_EXIT) | Treasure room exit |
| `0xFFFF` (GAMEMODE_SCORES) | High score attract screen |
| `0xFFFE` (GAMEMODE_TITLE) | Title screen attract |
| `0xFFFD` (GAMEMODE_DEMO) | Demo gameplay attract |
| `0xFFFC` (GAMEMODE_LEGEND) | Legend screen attract |

### 2.3 What Runs When — Complete Function Execution Matrix

| Function | Normal | TreasExit | Demo | Title/Scores/Legend | Dialog Active |
|----------|--------|-----------|------|---------------------|---------------|
| `main_logo_updcolors` | YES | YES | YES | YES | YES |
| `input_debounce` | YES | YES | YES | YES | YES |
| `coincheck` | YES | YES | YES | YES | YES |
| `main_cycle_tport_and_ffield` | YES | YES | YES | YES | **NO** |
| `main_handle_potions` | YES | YES | YES | YES | **NO** |
| `main_open_doors` | YES | YES | YES | YES | **NO** |
| `main_handle_shots` | YES | YES | YES | YES | **NO** |
| `main_move_players` | YES | YES | DEMO INPUT | **SKIPS** | **NO** |
| `main_scroll_playfield` | YES | YES | YES | YES | **NO** |
| `main_move_monsters` | YES | YES | if players | **SKIPS** | **NO** |
| `main_handle_dragon` | YES | YES | YES | YES | **NO** |
| `main_thief_anim` | YES | YES | YES | YES | **NO** |
| `main_start_thief` | YES | YES | YES | YES | **NO** |
| `main_health_countdown` | YES | YES | YES (1/64) | n/a | **NO** |
| `main_treasure_timer` | YES | YES | YES | YES | **NO** |
| `main_handle_death` | YES | YES | YES | YES | **NO** |
| `main_exit_move` | YES | YES | YES | YES | **NO** |
| `main_walls_cyclic_move` | YES | YES | YES | YES | **NO** |
| `main_walls_random_move` | YES | YES | YES | YES | **NO** |
| `main_msgbox_countdown` | YES | YES | YES | YES | YES |
| `pick_character` | YES | YES | YES | YES | YES |
| `main_start_game` | YES | YES | YES | YES | YES |
| `main_score_update` | YES | YES | YES | YES | YES |
| `main_score_display` | YES | YES | YES | YES | YES |
| `main_attract` | YES | YES | YES | YES | YES |
| `eeprom_timer` | YES | YES | YES | YES | YES |
| `sound_response` | YES | YES | YES | YES | YES |
| `main_update_sound` | YES | YES | YES | YES | YES |

### 2.4 Attract Mode State Machine (`main_attract`, 0x44562)

The attract mode cycles through four screens:
```
SCORES → TITLE → DEMO → LEGEND → SCORES → ...
```

Timers (frames at 60 Hz):
| Screen | Timer | Seconds |
|--------|-------|---------|
| TITLE | 0x5DD | ~25 sec |
| SCORES | 0x258 | ~10 sec |
| DEMO | 0x1C20 | ~119 sec |
| LEGEND | 0x258 | ~10 sec |

Every 13th TITLE cycle: refreshes EEPROM settings. If attract sounds are enabled (bit 14 of settings) and the music counter is zero: plays theme 0x3B ("Gauntlet II Theme Song").

---

## 3. Calling Convention

The game ROM is compiled C using a **stack-based, caller-cleanup convention** (cdecl) typical of the Green Hills C compiler for 68000 targets.

### 3.1 Prologue / Epilogue

```asm
; Prologue
link.w  a6, #-N            ; save old a6, set frame pointer, allocate N bytes of locals
movem.l <reg-list>, -(a7)  ; save callee-saved registers

; Epilogue
movem.l -offset(a6), <reg-list>  ; restore saved registers
unlk    a6                        ; restore old a6, deallocate locals
rts
```

`a6` is always the frame pointer. Local variables are at negative offsets from `a6`; arguments are at positive offsets.

A few heavily-used functions (e.g., `mob_create` at 0x5DC58) omit `link`/`unlk` and access arguments relative to `a7` directly — a hand-optimization, not a different convention.

### 3.2 Argument Passing

All arguments are pushed **right-to-left** (last argument pushed first) as **32-bit longwords**, even when the logical type is 16-bit. Values are sign- or zero-extended to 32 bits before pushing.

Common push idioms:
| Instruction | Effect |
|-------------|--------|
| `move.l dN, -(a7)` | Push register (already 32-bit) |
| `pea.l <ea>` | Push effective address (pointer arg) |
| `clr.l -(a7)` | Push zero |
| `pea.l 0x20.w` | Push immediate constant as longword |

Because the 68010 is **big-endian**, the low (meaningful) 16 bits of each longword slot sit at `+2` within the slot:

```asm
; Frame-pointer form:
;   a6+0  = saved old a6
;   a6+4  = return address
;   a6+8  = arg 1 longword  → low word at a6+0x0A
;   a6+C  = arg 2 longword  → low word at a6+0x0E
move.w  0xa(a6), d6      ; read arg 1 as word
move.w  0xe(a6), d3      ; read arg 2 as word
```

### 3.3 Caller Cleanup

The **caller** removes arguments after the call returns, typically with `lea`:

```asm
; Call mob_create with 6 longword args (24 bytes)
move.l  d0, -(a7)    ; arg 6
move.l  d0, -(a7)    ; arg 5
...
jsr     mob_create
lea     0x18(a7), a7  ; pop 24 bytes (6 × 4)
```

### 3.4 Return Values

Return values are passed in **d0**. Word-sized results use `d0.w`; longword/pointer results use `d0.l`. Void functions leave d0 undefined.

### 3.5 Register Classes

| Registers | Role | Convention |
|-----------|------|------------|
| d0–d1 | Scratch / temporaries | **Caller-saved** |
| d2–d7 | General purpose | **Callee-saved** |
| a0–a1 | Scratch / pointer temps | **Caller-saved** |
| a2–a5 | General purpose pointers | **Callee-saved** |
| a6 | Frame pointer | Saved/restored by `link`/`unlk` |
| a7 | Stack pointer | Managed implicitly |

### 3.6 Identifying Hand-Written Assembly

Telltale signs of non-compiler-generated code:
- No `link`/`unlk` and no `movem` save (only scratch registers used)
- No stack-based arguments (inputs arrive in registers or fixed memory)
- Unusual sequences not typical of compiler output (e.g., `roxl` for bit-serial I/O debouncing at `input_debounce`, 0x40644)
- Inline within the slapstic trampoline (bank-switch helpers at 0x56E58/0x56E6E)

---

## 4. ROM Coverage

### 4.1 Code Coverage

- **170 functions** found via `link a6` prologue search
- **0 undocumented functions** with standard prologues
- ~87 KB of code documented at function granularity
- All 29 main-loop top-level functions: **status DONE**

### 4.2 Data Tables Coverage

- **103 named data tables** documented in DETAILED_REPORT.md and FUNCTIONS_PLAN.md
- ~37 KB data region, ~99% understood

### 4.3 Previously Undocumented Areas — Now Decoded

The following major data areas were unlabeled but have since been decoded:

| Area | Size | Content |
|------|------|---------|
| Tile sprite descriptors (0x5BA90–0x5C88F) | ~3.6 KB | 8-byte 2×2-tile descriptors for floor/wall rendering |
| Special object tiles (0x5CB48–0x5D478) | ~2.4 KB | Sparse object tile index table + dense animation frame table |
| Tile pattern data + embedded code (0x5D848–0x5F9CE) | ~8.6 KB | Palette ramps, contest strings, connectivity table + tile rendering code |
| Wall connectivity tables (0x5F9CE–0x5FFFF) | ~1.6 KB | 16+9+9 entries for wall segment graphic selection |
| Speech/dialog strings (0x59716–0x5A200) | ~2.8 KB | Hint records, speech IDs, gameplay tips |
| In-game message strings (0x5A320–0x5AB1A) | ~2.0 KB | Power-up names, monster names, credits, bonus scoring |
| Palette cycling data (0x5B22E–0x5B64A) | ~1.1 KB | Hurt flash, poison shimmer, invulnerability shimmer |
| Character display config (0x570B4–0x57370) | ~700 B | Portrait offsets, sprite pointers, input bitmasks, auto-repeat timing |
| Demo/level config (0x57BD8–0x5858C) | ~2.5 KB | Level object placement, default high scores, demo streams, tip strings |
| Atari contest strings (0x5D9E8–0x5DAA0) | ~136 B | "SEND CONTEST ENTRY FORM TO ATARI GAMES CORP. CONTEST ENDS 12/19/86" |

### 4.4 Remaining Unknowns

The four unknowns formerly listed here (dragon path table format, dialog tip boundaries, tile pattern → descriptor mapping, EEPROM bits 5–7/13) have all been resolved by disassembly — see `05_data_reference.md` (data formats, §3.19 bytecodes, §5 ROM tables) and `04_game_subsystems.md` (§8 dragon, §30 shot resolution). The dragon path table turned out to be 5×16 bytes at 0x5D578, with the rest of its formerly claimed 2 KB being playfield palettes and contest strings.

For the current list of open questions, see `08_known_issues.md`.

### 4.5 Unused ROM Space

The 6,196-byte block of solid 0xFF between address 0x55620 and 0x56E53 is genuinely unused ROM space. This represents ~4.8% of the ROM — typical of 1980s arcade ROMs where compiled code didn't fill the entire EPROM chip.

### 4.6 Disassembly Note — `movea.l` Immediate Mode

Several radare2 disassembly listings display `movea.l 0x9XXXXX, an`, which **appears** to be a memory dereference but is often **IMMEDIATE mode** (loading the address literal into the register). Always confirm via raw byte inspection:

| Encoding | Instruction | Effect |
|----------|-------------|--------|
| `2X7C nnnnnnnn` (X = register) | `MOVEA.L #imm.l, aX` | Load address literal into aX (e.g., `207C` → a0, `227C` → a1, `247C` → a2, `267C` → a3) |
| `2X79 nnnnnnnn` | `MOVEA.L (abs.l), aX` | Load the longword *stored at* the address |

This affects any analysis that assumed these instructions were dereferencing pointers. For example, the dragon RAM locations at `0x904890–0x904894` are **direct word values** (not pointers), confirmed by raw byte checks.

---

## 5. `one_time_init` (0x4327A) — Initialization Before First Frame

Called once from the main loop before the first VBLANK wait. Performs full game initialization:

1. **Sound system reset** — flushes sound ring buffer, resets speech counter, sends hardware reset command via OS 0x254
2. **Clear game state** — zeros `0x90400C`
3. **Initialize display** — calls `init_display` (0x43486) with args (0, 0)
4. **Read hardware config** — calls OS 0x236 (DIP switches → `0x9049E2`), OS 0x1A8 slot 0xC (game settings → `0x904A24`), OS 0x1A8 slot 0xB (game options, sanitizes via OS 0x1C0)
5. **ROM version check** — checks bit 12 of settings; if set, reads from ROM 0x40070 and updates EEPROM
6. **Initialize subsystems** — calls `init_display_list` (0x42F86), `init_monster_system` (0x49BD0), OS 0x14E (hardware init)
7. **Initialize RAM variables** — sets timers, clears state variables, sets default character types {0,1,2,3}
8. **Start attract mode** — calls `start_attract_screen` (0x44414) with arg -2 (GAMEMODE_TITLE)
