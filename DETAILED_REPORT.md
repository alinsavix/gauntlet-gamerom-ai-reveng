# Gauntlet II — Detailed ROM Reverse Engineering Report

*Deep analysis of the 68010 Game ROM (row76.bin, 0x040000–0x05FFFF), Slapstic ROM (row10.bin, 0x038000–0x03FFFF), and supporting OS ROM (row9.bin, 0x000000–0x00FFFF).*

*Builds on the initial REPORT.md with verified disassembly, corrected findings, and answers to specific open questions.*

---

## Table of Contents

1. [Main Loop Structure & Game Mode Dispatch](#1-main-loop-structure--game-mode-dispatch)
2. [MOB ID System & Maze Position Abstractions](#2-mob-id-system--maze-position-abstractions)
3. [Attract Mode & Demo Playback System](#3-attract-mode--demo-playback-system)
4. [MOB Animation System](#4-mob-animation-system)
5. [Data Tables Catalog](#5-data-tables-catalog)
6. [Corrections to Initial REPORT.md](#6-corrections-to-initial-reportmd)
7. [Maze Object Placement](#7-maze-object-placement-maze_place_object-0x45e40)
8. [Monster Movement Handler Dispatch](#8-monster-movement-handler-dispatch)
9. [Forcefield Segment Table Format](#9-forcefield-segment-table-format)
10. [Complete Maze Catalog](#10-complete-maze-catalog)
11. [Function Calling Convention](#11-function-calling-convention)

---

## 1. Main Loop Structure & Game Mode Dispatch

### 1.1 The Main Loop (`m2mainloop`, 0x42a66)

The initial report stated that everything in the main loop executes every frame. **This is incorrect.** The main loop has a two-level conditional structure:

1. **A dialog-active gate** that skips the entire gameplay portion when a message box is displayed.
2. **Internal game_mode checks** within individual functions that cause early returns during attract/demo modes.

Here is the verified call sequence with the dialog gate annotated:

```
m2mainloop (0x42a66):
    link a6, #-4
    a2 = #0x904002              ; → VBLANK semaphore
    jsr 0x4327a                 ; one-time init (details TBD)
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
        goto SKIP_GAMEPLAY      ; YES → skip all gameplay functions

    ── GAMEPLAY FUNCTIONS (skipped when dialog is active) ──
    jsr main_cycle_tport_and_ffield (0x40528)
    jsr main_handle_potions         (0x46fea)
    jsr main_open_doors             (0x45c00)
    jsr main_handle_shots           (0x474f6)
    jsr main_move_players           (0x4a53a)   ← has internal game_mode check
    jsr main_scroll_playfield       (0x46caa)
    jsr main_move_monsters          (0x49034)   ← gated by active player count
    jsr main_handle_dragon          (0x54454)
    jsr main_thief_anim             (0x4e8dc)   ← NOT 0x4d8dc as in prior docs
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

    ── FRAME OVERFLOW CHECK ────────────────────────────────
    if (0x904002) != 0:         ; another VBLANK already?
        (0x904916) = 8          ; frame took too long
    else:
        (0x904916) >>= 1       ; decay overflow counter

    goto VBLANK_WAIT
```

### 1.2 The VBLANK Synchronization

The main loop synchronizes to the display refresh (60 Hz) through a semaphore at `0x904002`. The game's VBLANK handler (at 0x4017e, jumped to via the jump table at 0x40006) increments this word each VBLANK. The main loop spins until it becomes non-zero, then clears it and processes one frame.

If the main loop takes longer than one frame (16.67 ms), the VBLANK semaphore will already be non-zero when the loop finishes. In this case, the frame overflow counter at `0x904916` is set to 8, then halved each subsequent on-time frame. Systems that check this flag can reduce workload to catch up.

### 1.3 Internal Game Mode Checks

Beyond the dialog gate, individual functions perform their own `game_mode` checks. The game mode variable is at `0x904918`, with these values:

| Value | Name | Signed | Description |
|-------|------|--------|-------------|
| 0 | GAMEMODE_NORMAL | 0 | Normal gameplay |
| 1 | GAMEMODE_TREAS_EXIT | +1 | Treasure room exit countdown |
| 0xFFFF | GAMEMODE_SCORES | -1 | High score display (attract) |
| 0xFFFE | GAMEMODE_TITLE | -2 | Title screen (attract) |
| 0xFFFD | GAMEMODE_DEMO | -3 | Demo gameplay (attract) |
| 0xFFFC | GAMEMODE_LEGEND | -4 | Legend/how-to-play (attract) |

Key function behavior by mode:

**`main_move_players` (0x4a53a):**
- `game_mode >= 0` → normal player movement (reads hardware joystick)
- `game_mode == DEMO` → demo playback mode (reads from demo data tables)
- `game_mode < 0 AND != DEMO` → returns immediately (no player processing)

**`main_move_monsters` (0x49034):**
- Gated by `level_players_active (0x904928)` rather than game_mode directly. When no players are active (attract modes other than demo), this returns immediately.

**`main_attract` (0x44562):**
- `game_mode > 0` → treasure room handling
- `game_mode == 0` → check if all players inactive; if so, trigger continue screen or transition to attract
- `game_mode < 0` → attract mode state machine (manages timers and screen transitions)

**`main_health_countdown` (0x466f6):**
- Only decrements health every 64th frame (`frame_counter & 0x3f == 0`).
- Does not check game_mode explicitly, but since player health arrays are empty during attract modes, this effectively no-ops.

### 1.4 Summary: What Runs When

| Function | Normal | Treas Exit | Demo | Title/Scores/Legend | Dialog Active |
|----------|--------|-----------|------|---------------------|---------------|
| logo_updcolors | YES | YES | YES | YES | YES |
| input_debounce | YES | YES | YES | YES | YES |
| coincheck | YES | YES | YES | YES | YES |
| cycle_tport_ffield | YES | YES | YES | YES | **NO** |
| handle_potions | YES | YES | YES | YES | **NO** |
| open_doors | YES | YES | YES | YES | **NO** |
| handle_shots | YES | YES | YES | YES | **NO** |
| move_players | YES | YES | DEMO INPUT | **SKIPS** | **NO** |
| scroll_playfield | YES | YES | YES | YES | **NO** |
| move_monsters | YES | YES | if players | **SKIPS** | **NO** |
| handle_dragon | YES | YES | YES | YES | **NO** |
| thief_anim | YES | YES | YES | YES | **NO** |
| start_thief | YES | YES | YES | YES | **NO** |
| health_countdown | YES | YES | YES (1/64) | n/a | **NO** |
| treasure_timer | YES | YES | YES | YES | **NO** |
| handle_death | YES | YES | YES | YES | **NO** |
| exit_move | YES | YES | YES | YES | **NO** |
| walls_cyclic | YES | YES | YES | YES | **NO** |
| walls_random | YES | YES | YES | YES | **NO** |
| msgbox_countdown | YES | YES | YES | YES | YES |
| pick_character | YES | YES | YES | YES | YES |
| start_game | YES | YES | YES | YES | YES |
| score_update | YES | YES | YES | YES | YES |
| score_display | YES | YES | YES | YES | YES |
| attract | YES | YES | YES | YES | YES |
| eeprom_timer | YES | YES | YES | YES | YES |
| sound_response | YES | YES | YES | YES | YES |
| update_sound | YES | YES | YES | YES | YES |

---

## 2. MOB ID System & Maze Position Abstractions

### 2.1 MOB (Motion Object) ID Space

The hardware supports 1024 MOB slots (IDs 0–1023). Each MOB has 4 words of hardware state in parallel VRAM arrays:

| Array | Base Address | Per-MOB offset | Contents |
|-------|-------------|---------------|----------|
| mob_picture | 0x902000 | id × 2 | Tile number (bits 14-0), software flag (bit 15) |
| mob_hpos | 0x902800 | id × 2 | X position (bits 15-6), flags (bits 5-4), palette (bits 3-0) |
| mob_vpos | 0x903000 | id × 2 | Y position (bits 15-6), width-1 (bits 5-3), height-1 (bits 2-0) |
| mob_link | 0x903800 | id × 2 | Maze object type (bits 15-10), next link (bits 9-0) |

Additionally, there is a software-only parallel array:

| Array | Base Address | Per-MOB offset | Contents |
|-------|-------------|---------------|----------|
| mob_anim | 0x904066 | id × 2 | Anim counter (bits 15-13), direction (bits 12-10), back-link (bits 9-0) |

#### Fixed MOB IDs (0–29)

The first 30 MOB slots are reserved for specific purposes and are never used for maze objects:

| ID Range | Count | Purpose |
|----------|-------|---------|
| 1–4 | 4 | Player shots (one per player) |
| 5–8 | 4 | Demon shots |
| 9–12 | 4 | Lobber shots |
| 13–16 | 4 | Shot explosion animations |
| 17–20 | 4 | Floating score popups |
| 21–24 | 4 | Player exit animations |
| 25–29 | 5 | Transporter animations |

MOB ID 0 serves as the linked-list terminator (null pointer).

#### Dynamic MOB IDs (30–1023)

Slots 30 and above are used for maze objects: monsters, generators, items, food, keys, potions, power-ups, doors, exits, transporters, and forcefields. During `maze_setupnew`, the MOB arrays are cleared and repopulated from the decompressed maze data.

### 2.2 Two Levels of Position Abstraction

Gauntlet uses two distinct coordinate systems, which I'll call **slot positions** and **pixel positions**.

#### Slot Positions (Maze Grid Coordinates)

The maze is a 32×32 grid of tiles. Each tile occupies a 16×16 pixel area on the 512×512 playfield. A **slot index** is a linear index into this grid:

```
slot_index = row × 32 + column    (range: 0–1023)
```

Alternatively, slot positions are encoded as 10-bit values:
```
encoded_pos = (row << 5) | column    (bits 9-5 = row, bits 4-0 = column)
```

This encoding is used by `calc_direction` (0x510fc) and various position comparison functions. The slot index directly corresponds to a MOB ID in the dynamic range — MOB slot 32 (for example) represents the maze tile at row 1, column 0.

#### Pixel Positions (Playfield Coordinates)

MOBs are positioned in pixel coordinates on the 512×512 playfield:

```
pixel_x = column × 16    (range: 0–496, stored in mob_hpos bits 15-6)
pixel_y = row × 16       (range: 0–496, stored in mob_vpos bits 15-6)
```

The pixel position has 10-bit resolution (0–511), but since it's stored in bits 15-6, the effective resolution is in units of 1 pixel (the value is pre-shifted left by 6 bits to include the size/palette fields in the lower bits).

#### Converting Between Systems

`scroll_to_slot` (0x46c5e) converts a slot index to pixel coordinates for centering the viewport:
```
row = (slot >> 5) & 0x1F
col = slot & 0x1F
pixel_x = col × 16
pixel_y = row × 16
```

#### Playfield RAM Mapping

The playfield RAM (0x900000) uses a 64×64 tile grid of 8×8 pixel tiles, stored column-first. Each maze tile (16×16 pixels) maps to a 2×2 block of playfield tiles:

```
pf_offset = (col × 2) × 64 + (row × 2)    ; top-left 8×8 tile of the 16×16 block
```

### 2.3 `mob_create` (0x5dc58) — How MOBs Are Placed

The `mob_create` function takes 6 arguments on the stack:

| Stack Offset | Argument | Description |
|-------------|----------|-------------|
| +0x06 | mob_id | Slot number (0–1023) |
| +0x0A | tile_number | Base tile for mob_picture |
| +0x0E | hpos_palette | Horizontal position with palette in low bits |
| +0x12 | vpos_size | Vertical position with tile dimensions in low bits |
| +0x16 | maze_obj_type | MAZEOBJ_* type stored in mob_link bits 15-10 |
| +0x1A | direction | Initial direction stored in mob_anim bits 15-10 |

The function:
1. Calls `moblist_insert` (0x5dcbc) to link the MOB into the spatial linked list
2. Writes tile_number to mob_picture
3. Writes hpos_palette to mob_hpos
4. Writes vpos_size to mob_vpos
5. Sets mob_link bits 15-10 = maze_obj_type (preserving the link in bits 9-0)
6. Sets mob_anim (0x904066) bits 15-10 = direction (preserving back-link in bits 9-0)

### 2.4 MOB Linked Lists

MOBs are organized into forward-linked lists by vertical band. The 64 list heads are at `0x905f80` (one per 8-pixel vertical band of the playfield). Each list chains MOBs whose Y position falls in that band, linked through mob_link bits 9-0.

A software backward-link is maintained in mob_anim (0x904066) bits 9-0 (and separately in a table at `0x904940`), enabling O(1) removal from the doubly-linked list.

---

## 3. Attract Mode & Demo Playback System

### 3.1 Attract Mode State Machine

The attract mode is driven by `main_attract` (0x44562), which runs every frame. The state machine cycles through four attract screens by decrementing `game_mode`:

```
SCORES (-1) → TITLE (-2) → DEMO (-3) → LEGEND (-4) → SCORES (-1) → ...
```

Each mode has a duration controlled by the attract timer at `0x904b7c`:

| Mode | Timer Value | Duration |
|------|------------|----------|
| SCORES (0xFFFF) | 0x21C (540) | 9 seconds |
| TITLE (0xFFFE) | 0x5A1 (1441) | ~24 seconds |
| DEMO (0xFFFD) | 0x1BE4 (7140) | ~2 minutes |
| LEGEND (0xFFFC) | 0x258 (600) per sub-screen | 10 seconds each |

The LEGEND mode has multiple sub-screens tracked by `attract_legend` (0x90491a), initially set to 2 and counting down. Each sub-screen displays a different tutorial/legend page.

When the attract timer reaches 0, the system transitions to the next mode:
1. `game_mode` is decremented
2. If reaching LEGEND: initialize legend sub-screen counter, call `maze_hide`, set up info panel
3. If wrapping past LEGEND: reset to SCORES (0xFFFF)
4. The setup function at `0x44414` is called with the new game_mode to configure the appropriate attract screen

#### Attract Mode Interruption

During attract, the code checks for coin insertion by examining raw joystick ports 0x904922 and 0x904924 (players 2 and 3) for button presses. The specific checks are:
- If `game_pricing_config (0x9049e2)` is non-zero: check for FIRE+MAGIC bits (0x03)
- If pricing config is zero (free play): check for FIRE bit only (0x02)

When a coin is detected and a start button pressed, `game_new_setup` (0x44204) is called to begin a new game.

### 3.2 Demo Setup (`demo_setup`, 0x449d4)

When transitioning to DEMO mode, this function:
1. Calls `maze_hide` (0x4529a) to blank the screen
2. Calls `setup_infopanel` (0x452d0) with arg=-1
3. Clears dialog flags (0x90487e, 0x9049e4)
4. Loads maze number 0x66 (102 = MAZENUM_DEMO) via 0x40d24
5. Calls `maze_new_level_setup` (0x438ae) to build the demo level
6. Sets up floor/wall colors
7. **Sets player_character[1] = 3** (Elf) and calls `player_join(1)` — Player 2 joins as an Elf
8. Initializes demo data pointer for player 1: `demo_pointer[1] = 0x581c4`
9. Loads the first timer byte from demo data: `demo_timer[1] = byte at 0x581c4`
10. Clears demo pointers and timers for players 0, 2, 3 (only player 1 has demo data in this setup)

### 3.3 Demo Data Format

Demo input data is stored in ROM as a stream of 2-byte entries. The data is read by `main_move_players` when `game_mode == DEMO`.

#### RAM Variables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904b66 | 4×4B | demo_pointer[0..3] | Current position in demo data stream (longword pointer per player) |
| 0x904b76 | 4×1B | demo_timer[0..3] | Frames remaining for current input (byte per player) |

#### Entry Format

Each 2-byte entry in the demo data stream:

```
Byte 0: Command/Timer
Byte 1: Data
```

**Normal input entry (byte0 = 0x01–0xFD):**
- byte0 = number of frames to hold this input (1–253)
- byte1 = joystick/button state (active-low, same format as hardware port)

**Speech/dialog command (byte0 = 0xFF):**
- byte1 = argument to the dialog function (0x4c9a2)
- Processing loops back immediately to read the next entry (no frame delay)

**Player join command (byte0 = 0xFE):**
- byte1 high nibble = character type (0=Warrior, 1=Valkyrie, 2=Wizard, 3=Elf)
- byte1 low nibble = player index (0–3)
- Calls `player_join` for that player, resets demo_timer to 1, and reloads demo_pointer from the initial pointer table
- Processing loops back to read next entry

#### Joystick Byte Encoding (Active-Low)

| Bit | Function | 0 = Pressed |
|-----|----------|-------------|
| 7 | UP | Moving up |
| 6 | DOWN | Moving down |
| 5 | LEFT | Moving left |
| 4 | RIGHT | Moving right |
| 3 | (spare) | Not connected |
| 2 | (spare) | Not connected |
| 1 | FIRE | Attacking |
| 0 | MAGIC | Using potion |

Example: `0xB3` = 1011_0011 → DOWN pressed (bit 6=0), all others released. Player moves down without attacking.
Example: `0xF3` = 1111_0011 → No directions pressed, no buttons. Player stands idle.

### 3.4 Demo Data Pointers

The initial demo data pointers are stored in a ROM table at **0x58098** (4 longwords):

| Player | Pointer | ROM Address |
|--------|---------|-------------|
| 0 | 0x05818C | Player 0 demo stream |
| 1 | 0x0581C4 | Player 1 demo stream (used in standard demo) |
| 2 | 0x05825A | Player 2 demo stream (very short/empty) |
| 3 | 0x05825C | Player 3 demo stream (very short/empty) |

The standard demo setup only activates Player 1 (as an Elf). Players 0, 2, and 3 have demo data available but are not activated in the normal attract cycle.

### 3.5 How Demo Input Reaches the Movement System

In `main_move_players` (0x4a53a), the per-player processing at 0x4a8a2 diverges based on game_mode:

**Normal gameplay (`game_mode == 0`):**
```asm
lea.l   (0x904920).l, a0       ; hardware joystick input array
move.w  (a0, d0.w), d6         ; d6 = raw joystick bits from hardware
```

**Demo mode (`game_mode != 0`):**
```asm
lea.l   (0x904b66).l, a0       ; demo pointer array
movea.l (a0, d1.w), a0         ; a0 = current demo data pointer for this player
move.w  (a0), d6               ; d6 = WORD from demo data (timer:input)
andi.w  #$00F3, d6             ; mask: keep direction bits (7-4) and fire/magic (1-0)
```

The AND with `0x00F3` strips the timer byte (high byte of the word) and clears the spare button bits (3-2), leaving only the directional and action inputs in d6. From this point, the movement code proceeds identically for both normal and demo input.

---

## 4. MOB Animation System

### 4.1 Animation State Storage

Each MOB's animation state is stored in the parallel array at `0x904066` (referred to as `mob_anim`):

| Bits | Field | Description |
|------|-------|-------------|
| 15-13 | anim_counter | Animation frame counter (0–7), incremented each processing frame |
| 12-10 | direction | Direction of travel/facing (0–7, matching DIRECTION_* enum) |
| 9-0 | back_link | Backward link for doubly-linked MOB list |

The direction field uses the standard 8-direction encoding:
```
0=UP, 1=UP-RIGHT, 2=RIGHT, 3=DOWN-RIGHT,
4=DOWN, 5=DOWN-LEFT, 6=LEFT, 7=UP-LEFT
```

### 4.2 Player Animation

Player characters have three animation modes, each using a different ROM tile lookup table:

#### Standing/Idle Animation (Table at 0x58A4A)

When the player is stationary (no direction input, not fighting):

```
index = character_type × 8 + facing_direction
tile = word at [0x58A4A + index × 2]
```

- **32 entries** (4 characters × 8 directions)
- Single frame per direction — no cycling

#### Walking Animation (Table at 0x58A8A)

When the player is moving but not attacking:

```
anim_counter = (0x9049BC[player]) >> 2    ; divide by 4
frame = anim_counter & 3                  ; 4 animation frames
index = character_type × 32 + facing_direction × 4 + frame
tile = word at [0x58A8A + index × 2]
```

- **128 entries** (4 characters × 8 directions × 4 frames)
- Counter incremented each frame; effective frame rate = game FPS / 4

#### Fighting/Shooting Animation (Table at 0x5884A)

When the player is attacking (sword/axe swing, shot animation):

```
anim_counter = (0x9049BC[player]) >> 1    ; divide by 2
frame = anim_counter & 7                  ; 8 animation frames
index = character_type × 64 + facing_direction × 8 + frame
tile = word at [0x5884A + index × 2]
```

- **256 entries** (4 characters × 8 directions × 8 frames)
- Counter incremented each frame; effective frame rate = game FPS / 2

#### Shooting Animation (Table at 0x5874A)

For the ranged attack animation (shooting projectiles):

```
index = character_type × 32 + facing_direction × 4 + frame
tile = word at [0x5874A + index × 2]
```

- **128 entries**, same structure as walking
- Used when `player_shooting[player] == -1`

### 4.3 Animation Counter Mechanics

The animation counter at `0x9049BC` is a per-player word that increments every frame the player is active. It is used as a free-running counter that's divided down (right-shifted) and masked to produce frame indices:

- **Walking**: counter >> 2, AND 3 → cycles through frames 0,1,2,3 every 16 game frames (~0.27 sec per cycle)
- **Fighting**: counter >> 1, AND 7 → cycles through frames 0-7 every 16 game frames
- **Standing**: no cycling; facing direction alone determines the tile

When the player stops moving, the animation counter continues running but only the facing direction matters (idle table has one tile per direction).

The fighting animation has a special end condition: when the counter reaches a threshold stored in a table at `0x58090` (per player × 2), the attack sequence ends and the shooting flag is cleared.

### 4.4 Monster Animation — Direct Tile Lookup Tables

**Correction:** The initial report assumed monsters use computed tile offsets. In fact, monster animation uses **direct tile lookup tables** identical in mechanism to player animation — each monster type has a 128-byte word table (64 entries) that maps `(counter, direction)` to an exact tile number.

#### Animation Tile Lookup Mechanism

At `0x414A4–0x414B8` in `monsters_everything`:

```asm
lea.l   (0x40DB2).l, a0         ; pointer table base (idle animation)
movea.l (a0, d6.w), a0          ; load animation table for this monster type
move.b  (a6, d2.w), d0          ; high byte of mob_anim[mob]
andi.w  #$FC, d0                ; mask to counter(3 bits) + direction(3 bits)
lsr.w   #1, d0                  ; make word index
move.w  (a0, d0.w), (a2, d2.w)  ; write tile number to mob_picture
```

The index computation: `index = (anim_counter × 8 + direction) × 2` — a word table indexed by the 6-bit combination of counter and direction.

#### Animation Pointer Tables

Two pointer tables select animation tables based on monster state:

**Idle/Stationary Table (0x40DB2)** — 10 longword pointers, used when the monster is not actively moving:

| Index | Monster Type | Table Address |
|-------|-------------|---------------|
| 0 | Ghost | 0x058F26 |
| 1 | Grunt | 0x058FA6 |
| 2 | Demon | 0x0590A6 |
| 3 | Lobber | 0x0591A6 |
| 4 | Sorcerer | 0x058C0A |
| 5 | Aux Grunt | 0x058FA6 (shared with Grunt) |
| 6 | Death | 0x0592A6 |
| 7 | Acid | 0x059336 |
| 8 | Super Sorc | 0x058C0A (shared with Sorcerer) |
| 9 | IT | 0x059436 |

**Moving/Chasing Table (0x40DDA)** — 10 longword pointers, used when the monster has bit 5 of mob_hpos set (actively moving):

| Index | Monster Type | Table Address | Notes |
|-------|-------------|---------------|-------|
| 0 | Ghost | 0x00000000 | NULL — ghosts use idle table even when moving |
| 1 | Grunt | 0x00000000 | NULL — same |
| 2 | Demon | 0x059026 | Separate moving animation |
| 3 | Lobber | 0x059126 | Separate moving animation |
| 4 | Sorcerer | 0x00000000 | NULL — sorcerers don't visually move |
| 5 | Aux Grunt | 0x059226 | Has moving animation |
| 6 | Death | 0x059026 | Shares with Demon moving table |
| 7 | Acid | 0x00000000 | NULL |
| 8 | Super Sorc | 0x059436 | Has moving animation |
| 9 | IT | 0x00000000 | NULL |

Monsters with NULL moving table pointers go through a different code path that uses the idle table for all states.

#### Table Format (Verified Against python-gex)

Each animation table has 64 word entries: 8 counter values × 8 directions. The tables encode animation timing by **repeating tile values** across multiple counter values.

**Ghost table (0x58F26) — verified:**

| Counter | UP (0) | UPRT (1) | RT (2) | DNRT (3) | DN (4) | DNLT (5) | LT (6) | UPLT (7) |
|---------|--------|----------|--------|----------|--------|----------|--------|----------|
| 0–4 | 2192 | 2156 | 2120 | 2084 | 2048 | 2304 | 2264 | 2228 |
| 5 | 2201 | 2165 | 2129 | 2093 | 2057 | 2313 | 2273 | 2237 |
| 6 | 2210 | 2174 | 2138 | 2102 | 2066 | 2322 | 2282 | 2246 |
| 7 | 2219 | 2183 | 2147 | 2111 | 2075 | 2331 | 2291 | 2255 |

*All values match python-gex ghost walk animation data exactly.* Ghosts show frame 0 for 5 ticks, then frames 1, 2, 3 each for 1 tick, producing a 0-0-0-0-0-1-2-3 cycle.

**Grunt table (0x58FA6) — verified:**

Counter pattern: 0-0-0-1-2-2-3-0 — a bounce/ping-pong walk cycle. All tile numbers verified against python-gex (grunt down frame 0 = 2529).

#### Counter Advancement

The counter (bits 15-13 of mob_anim) is incremented by `addi.w #$2000, (a6, d2.w)` — adding 0x2000 advances the 3-bit counter by 1. This happens once per monster processing frame, gated by frame-parity flags (even/odd frame skipping for speed control). The 3-bit counter wraps naturally from 7 → 0.

When the counter wraps (carry flag set from the add), the code optionally adjusts the direction for odd-angle monsters using the direction-adjust table at `0x40E1E`.

### 4.5 Tile Visibility Pulsing (Invisibility)

For players with the invisibility power-up, the code at 0x4ac30–0x4ac80 creates a pulsing visibility effect:

1. Read the player's powers from `0x9048E0`; check bit 0 (speed/invisibility)
2. If invisible and no dialog active: read from `0x905F50[player]` (invisibility timer)
3. Compute a frame mask from a table at `0x58070` based on the timer value
4. If `(frame_counter AND mask) != 0`: skip drawing (player invisible this frame)
5. Otherwise: replace mob_picture with `0x1709` (a blank/flash tile)

This creates the flickering invisibility effect by alternating between drawing and hiding the player sprite.

---

## 5. Data Tables Catalog

### 5.1 Player Data Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x58070 | 16B | invisibility_flash_masks | Frame masks for invisibility pulsing, indexed by timer >> 7 |
| 0x58090 | 8W | fighting_anim_end | Per-character × power-mode threshold for attack animation end |
| 0x58098 | 4×4B | demo_initial_pointers | Initial ROM pointers for demo input streams, per player |
| 0x580A8 | 8W | player_speed_normal | Movement speed per character (×2 for normal/powered modes) |
| 0x580B8 | 8W | player_anim_rate | Animation rate divisor per character type |
| 0x580C8 | 8W | player_collision_size | Collision box dimensions per character type |
| 0x580D8 | 8W | player_delta_x | Horizontal movement deltas per direction |
| 0x580E8 | 8W | player_delta_y | Vertical movement deltas per direction |
| 0x5813C | 32B+ | health_drain_table | Health drain per tick, indexed by difficulty + character |
| 0x5874A | 256B | anim_table_shooting | Shooting animation tiles: 4 chars × 8 dirs × 4 frames |
| 0x5884A | 512B | anim_table_fighting | Fighting animation tiles: 4 chars × 8 dirs × 8 frames |
| 0x58A4A | 64B | anim_table_idle | Idle/standing tiles: 4 chars × 8 dirs × 1 frame |
| 0x58A8A | 256B | anim_table_walking | Walking animation tiles: 4 chars × 8 dirs × 4 frames |

### 5.2 Master Object Parameter Tables (ROM)

The maze object placement function at `0x45E40` looks up creation parameters for each MAZEOBJ type from four parallel ROM tables. These tables are the **authoritative source** for tile numbers, palettes, sizes, and position offsets for every placeable object:

| Address | Size | Entry Size | Name | Description |
|---------|------|-----------|------|-------------|
| **0x5868C** | 128B | Word (2B) | **base_tile_table** | Base tile number per MAZEOBJ type (64 entries) |
| **0x5864C** | 64B | Byte (1B) | **palette_table** | MOB palette number per MAZEOBJ type (64 entries) |
| **0x5858C** | 128B | Word (2B) | **hpos_offset_table** | Horizontal position offset per type (64 entries) |
| **0x5860C** | 64B | Byte (1B) | **vpos_size_table** | Vertical position + sprite size byte per type (64 entries) |

The placement function reads these as:
```
tile    = base_tile_table[type]       ; word at 0x5868C + type×2
palette = palette_table[type]         ; byte at 0x5864C + type
h_off   = hpos_offset_table[type]     ; word at 0x5858C + type×2
vsize   = vpos_size_table[type]       ; byte at 0x5860C + type
```

**Verified base tile values (all confirmed against python-gex data):**

| MAZEOBJ | Type ID | Base Tile (hex) | Base Tile (dec) | Palette | Notes |
|---------|---------|----------------|-----------------|---------|-------|
| Ghost | 18 | 0x0800 | 2048 | 0x00 | |
| Grunt | 19 | 0x09E1 | 2529 | 0x04 | |
| Demon | 20 | 0x183F | 6207 | 0x08 | |
| Lobber | 21 | 0x1B57 | 6999 | 0x0B | |
| Sorcerer | 22 | 0x13A2 | 5026 | 0x0B | |
| Aux Grunt | 23 | 0x09E1 | 2529 | 0x04 | Shares tiles with Grunt |
| Death | 24 | 0x1A75 | 6773 | 0x00 | |
| Acid | 25 | 0x2300 | 8960 | 0x01 | |
| Super Sorc | 26 | 0x13A2 | 5026 | 0x0B | Shares tiles with Sorcerer |
| IT | 27 | 0x2600 | 9728 | 0x08 | |
| Ghost Gen 1 | 28 | 0x09AB | 2475 | 0x05 | |
| Ghost Gen 2 | 29 | 0x09B4 | 2484 | 0x05 | |
| Ghost Gen 3 | 30 | 0x09BD | 2493 | 0x05 | |
| Grunt Gen 1 | 31 | 0x09C6 | 2502 | 0x05 | |
| Grunt Gen 2 | 32 | 0x09CF | 2511 | 0x05 | |
| Grunt Gen 3 | 33 | 0x09D8 | 2520 | 0x05 | |
| Demon Gen 1-3 | 34-36 | 0x09C6-D8 | 2502-2520 | 0x05 | All non-ghost gens share tiles |
| Lobber Gen 1-3 | 37-39 | 0x09C6-D8 | 2502-2520 | 0x05 | |
| Sorc Gen 1-3 | 40-42 | 0x09C6-D8 | 2502-2520 | 0x05 | |
| AuxGrunt Gen 1-3 | 43-45 | 0x09C6-D8 | 2502-2520 | 0x05 | |
| Treasure | 46 | 0x0987 | 2439 | 0x01 | |
| Treasure Locked | 47 | 0x25E4 | 9700 | 0x01 | |
| Gold Bag | 48 | 0x09A2 | 2466 | 0x01 | |
| Food (destr) | 49 | 0x0963 | 2403 | 0x01 | |
| Food (invuln) | 50 | 0x096C | 2412 | 0x01 | Random variant from table at 0x58F20 |
| Potion (destr) | 51 | 0x88FC | 2300+flag | 0x01 | Bit 15 = software flag |
| Potion (invuln) | 52 | 0x89FC | 2556+flag | 0x01 | |
| Key | 53 | 0x8AFC | 2812+flag | 0x01 | |
| Invisibility | 54 | 0x1700 | 5888 | 0x01 | |
| Repulsiveness | 55 | 0x26FC | 9980 | 0x01 | |
| Reflect | 56 | 0x24FC | 9468 | 0x01 | |
| Transport | 57 | 0x23FC | 9212 | 0x01 | |
| Super Shot | 58 | 0x2788 | 10120 | 0x01 | |
| Invulnerability | 59 | 0x2784 | 10116 | 0x01 | |
| Dragon | 60 | 0xA740 | 10048+flag | 0x08 | Bit 15 = flag; uses different tiles than overview |
| Hidden Potion | 61 | 0x0BFC | 3068 | 0x01 | |
| Transporter | 62 | 0x8001 | marker | 0x00 | Handled specially |
| Forcefield Hub | 63 | 0x0C3F | 3135 | 0x00 | |

### 5.2b Monster Animation Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x40DB2 | 40B | monster_anim_idle_ptrs | 10 longword pointers to idle animation tile tables |
| 0x40DDA | 40B | monster_anim_moving_ptrs | 10 longword pointers to moving animation tile tables (NULL = use idle) |
| 0x40E1E | 40B | monster_oddangle_table | Per-type direction adjustment bytes for odd-angle movement |
| 0x58C0A | 128B | anim_tiles_sorcerer | Sorcerer/Super Sorc animation: 64 words (8 counters × 8 dirs) |
| 0x58F26 | 128B | anim_tiles_ghost | Ghost animation: 64 words |
| 0x58FA6 | 128B | anim_tiles_grunt | Grunt/Aux Grunt animation: 64 words |
| 0x590A6 | 128B | anim_tiles_demon | Demon animation: 64 words |
| 0x591A6 | 128B | anim_tiles_lobber | Lobber animation: 64 words |
| 0x592A6 | 128B | anim_tiles_death | Death animation: 64 words |
| 0x59336 | 128B | anim_tiles_acid | Acid animation: 64 words |
| 0x59436 | 128B | anim_tiles_it | IT animation: 64 words |
| 0x59026 | 128B | anim_tiles_demon_moving | Demon moving animation |
| 0x59126 | 128B | anim_tiles_lobber_moving | Lobber moving animation |
| 0x59226 | 128B | anim_tiles_auxgrunt_moving | Aux Grunt moving animation |

### 5.2c Other Monster Data Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x40E02 | 28B | monster_speed_override | 7 longword speed values for fast-monster level flags |
| 0x40E46 | ~32B | monster_count_table | Max monster count by difficulty + active player count |
| 0x4A4FA | ~64B | stun_input_remap | Input modification table for stunned players |
| 0x58F20 | 8B | food_invuln_variants | 4 word tile numbers for random invulnerable food variants |
| 0x594B6 | 128B | anim_tiles_it_special | IT special animation table (used for IT chase state) |
| 0x59536 | 128B | anim_tiles_generic_chase | Generic monster chase animation |
| 0x595B6 | 128B | anim_tiles_lobber_throw | Lobber throwing animation |

### 5.3 Item/Pickup Data Tables

From python-gex cross-reference, the tile numbers for items placed during maze setup:

| Item | MAZEOBJ ID | Base Tile | Size | Palette |
|------|-----------|-----------|------|---------|
| Key | 0x35 (53) | 2812 | 2×2 | 1 |
| Food (destructible) | 0x31 (49) | 2403 | 3×3 | 1 |
| Food (invuln) | 0x32 (50) | 2412/2421/2430 | 3×3 | 1 |
| Potion (destructible) | 0x33 (51) | 2300 | 2×2 | 1 |
| Potion (invuln) | 0x34 (52) | 2556 | 2×2 | 1 |
| Treasure | 0x2E (46) | 2439 | 3×3 | 1 |
| Treasure (locked) | 0x2F (47) | 9700 | 3×3 | 1 |
| Gold Bag | 0x30 (48) | 2466 | 3×3 | 1 |
| Invisibility | 0x36 (54) | 5888 | 3×3 | 1 |
| Transportability | 0x39 (57) | 9212 | 2×2 | 1 |
| Reflective Shots | 0x38 (56) | 9468 | 2×2 | 1 |
| Repulsiveness | 0x37 (55) | 9980 | 2×2 | 1 |
| Super Shot | 0x3A (58) | 10120 | 2×2 | 1 |
| Invulnerability | 0x3B (59) | 10116 | 2×2 | 1 |

### 5.4 Generator Data Tables

| Generator Type | MAZEOBJ IDs | Base Tile | Size | Palette |
|---------------|------------|-----------|------|---------|
| Ghost Gen 1/2/3 | 28/29/30 | 2475/2484/2493 | 3×3 | 5 |
| Other Gen 1/2/3 | 31-45 | 2502/2511/2520 | 3×3 | 5 |

Generator levels 1/2/3 have progressively more "damaged" sprites. Ghost generators have separate sprites from all other monster generators.

### 5.5 Maze Data Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x405C8 | ~16B | palette_offset_by_walltype | Byte table: playfield palette offset indexed by wall pattern |
| 0x405D8 | ~16B | palette_offset2_by_walltype | Second palette offset table |
| 0x571FA | 4×4B | forcefield_color_table | Forcefield color pointers indexed by (level & 3) |
| 0x5B81C | var | exit_anim_table | Exit open/close animation data, indexed by wall pattern × 64 |

### 5.6 Scoring & Economy Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x57862 | ~62W | health_per_coin | Health added per coin, indexed by GSETTING_COINHEALTH value (1–31) |
| 0x57012 | 13×4B | random_maze_flags | 13-entry table of maze feature flag longwords for `get_random_maze_flags` |

### 5.7 Dialog/Message Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x5828C+ | var | dialog_message_ptrs | Pointers to dialog message strings, organized by encounter type |
| 0x57644 | var | continue_screen_text1 | "PRESS START..." continue screen text |
| 0x57658 | var | continue_screen_text2 | Continue screen line 2 |
| 0x5766C | var | continue_screen_text3 | Continue screen line 3 |

### 5.8 Demo Data Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x58098 | 16B | demo_initial_ptrs | 4 longword initial pointers for demo input streams |
| 0x5818C | ~86B | demo_data_player0 | Demo input stream for player 0 |
| 0x581C4 | ~150B | demo_data_player1 | Demo input stream for player 1 (primary demo) |
| 0x5825A | ~2B | demo_data_player2 | Demo input stream for player 2 (minimal) |
| 0x5825C | ~2B | demo_data_player3 | Demo input stream for player 3 (minimal) |

### 5.9 Sound-Related Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x5B20E | var | palette_cycle_player0 | Palette cycling data for player 0 hurt flash |
| 0x5B256 | var | palette_cycle_player1 | Palette cycling data for player 1 |
| 0x5B29E | var | palette_cycle_player2 | Palette cycling data for player 2 |
| 0x5B32E | var | palette_cycle_player3 | Palette cycling data for player 3 |
| 0x5B3EE | var | palette_cycle_player0_alt | Alternate palette cycling |
| 0x5B4AE | var | palette_cycle_player2_alt | Alternate palette cycling |

---

## 6. Corrections to Initial REPORT.md

### 6.1 Main Loop Execution Model

**REPORT.md stated:** "Per-frame dispatch confirmed" with all functions running every frame.

**Correction:** The main loop has a significant conditional branch. When `dialog_timer (0x904a9e)` is non-zero, 16 gameplay functions are skipped entirely, jumping directly to the UI/attract/sound portion. Additionally, individual functions like `main_move_players` have internal checks that cause early returns based on game_mode. The main loop does NOT execute everything every frame.

### 6.2 Thief Animation Function Address

**REPORT.md listed:** `main_thief_move` at 0x4d8dc (from GAME_ROM_KNOWN.md).

**Correction:** The main loop calls `0x4e8dc`, not `0x4d8dc`. The function at 0x4e8dc handles thief animation and movement (checking `thief_mode` at 0x904ba0 and `thief_enter_time` at 0x904b9e). The address 0x4d8dc may be a different thief-related subroutine called from within the thief system rather than directly from the main loop.

### 6.3 Game Mode Values

**REPORT.md stated:** "values below 0x5 are pre-game, 0x5–0x72 are normal gameplay, ≥0x73 are special/attract modes" (referring to ram.os_flag).

**Correction:** The game mode variable is `game_mode` at `0x904918`, not `ram.os_flag`. The values are: 0 = normal, 1 = treasure exit, and negative values (0xFFFF through 0xFFFC as signed words) for attract modes. The os_flag / maze number at 0x904000 is a separate variable.

### 6.4 Previously Unknown Functions Identified

| Address | Old Name | New Name | Purpose |
|---------|----------|----------|---------|
| 0x4e8dc | (not listed) | main_thief_anim | Thief animation/movement update, called from main loop |
| 0x431ee | (not listed) | eeprom_timer | Periodic EEPROM write timer (10-minute interval) |
| 0x42d0a | (not listed) | sound_response | Processes responses from sound CPU via OS API |
| 0x4327a | (not listed) | mainloop_init | One-time initialization called at main loop entry |
| 0x44414 | (not listed) | attract_screen_setup | Sets up individual attract mode screens |

### 6.5 VBLANK Semaphore

**REPORT.md did not clearly identify** the VBLANK synchronization mechanism.

**Correction:** The VBLANK semaphore is at `0x904002` (a word). The VBLANK handler at 0x4017e increments it each field. The main loop spins on this, clears it after processing, and uses the overflow detection at `0x904916` to track frame drops.

---

## 7. Maze Object Placement (`maze_place_object`, 0x45E40)

### 7.1 Overview

`maze_decode` (0x4c1bc) calls `0x45E40` for each object token in the compressed maze data, passing `(slot_position, object_type, count)`. This function is the central dispatcher that creates all maze objects — walls, monsters, items, and special objects.

### 7.2 Dispatch by Object Type

The function categorizes objects into groups:

**Marker types** (written to mob_picture as special values for later processing):
- Types 2, 4, 5, 7, 8, 9 (walls), 0x3F (forcefield hub) → mob_picture = `0x8000`
- Type 5 (destructible wall) with specific wall patterns → mob_picture = `0x8003`
- Types 0xA–0xC (traps), 0x3E (transporter), 0x10–0x11 (exits), 1 (stun) → mob_picture = `0x8001`
- These markers are processed by the post-decode scan at `0x5F2C0` which calls `0x5EAB8` to render the actual playfield tiles.

**Dragon (type 0x3C):** Special multi-slot handling — the dragon occupies a 2×2 block of maze cells. Calls `0x5496E` (dragon setup) and `0x462AE` for each adjacent cell.

**Invulnerable food (type 0x32):** Random variant selection using `getrandom(3)` from a 4-entry table at `0x58F20` containing tile numbers `[0x096C, 0x0975, 0x097E, 0x0890]` (food variants 2412, 2421, 2430, and a 4th variant at 2192).

**All other types (monsters, items, generators, etc.):** Standard placement using the master parameter tables (Section 5.2):
1. Look up base tile from `base_tile_table[type]` (0x5868C)
2. Look up palette from `palette_table[type]` (0x5864C)
3. Compute pixel H position from slot index, subtract `hpos_offset_table[type]` (0x5858C)
4. Compute pixel V position from slot index, add `vpos_size_table[type]` (0x5860C)
5. For monster types 18–27: set initial direction = 4 (DOWN)
6. For super sorcerers (type 26) in non-attract mode: set tile to `0x1709` (invisible) and add flag `0x10` to hpos
7. Call `mob_create(slot, tile, hpos, vpos, type, direction)` at 0x5DC58

---

## 8. Monster Movement Handler Dispatch

### 8.1 Structure

`monsters_everything` (0x40E6A) does NOT use a jump table for per-type handlers. Instead, it uses a single shared handler at `0x4119A` with conditional branches for types needing special behavior.

The dispatch flow within the per-monster iteration:

```
1. Extract type from mob_link bits 15-10
2. Check: type == generator (types 28-45)?
   YES → generator spawning code (0x41026ff)
3. Check: type == super sorcerer (26)?
   YES → special sorcerer placement/teleport handler (0x4106A)
4. ALL other monster types (18-25, 27) → shared handler at 0x4119A
```

### 8.2 Shared Monster Handler (0x4119A)

The shared handler uses mob_hpos flag bits to determine monster state:

| Bit 5 | Bit 4 | State | Behavior |
|-------|-------|-------|----------|
| 1 | x | Moving | Advance animation counter, check collisions, continue movement |
| 0 | 1 | Chasing | Move toward target player, check for shooting opportunity |
| 0 | 0 | Idle | Find nearest player (call `monster_find_and_shoot` at 0x41750), start chasing |

Within the chasing state, specific types get special handling:
- **Sorcerer (d6=0x10):** Skips physical movement, only animates and shoots — sorcerers attack from a distance without moving
- **Acid (d6=0x1C):** Uses fixed direction advance value of 0x1E; acid puddles move in a fixed pattern
- **IT (d6=0x24):** Direction adjusted from the odd-angle table; IT creatures move erratically

All other monsters use the general chasing behavior: call `monster_find_and_shoot` to pick a target, then physically move toward it using the collision-checked movement functions at `0x5E10C` and `0x5E1D8`.

---

## 9. Forcefield Segment Table Format

### 9.1 Construction (0x53398)

The function at `0x53398` scans all maze slots for FORCEFIELDHUB objects (type 0x3F). For each hub, it traces connected forcefield segments in the +slot direction (horizontally along the row), building entries in the segment table at `0x910780`.

### 9.2 Segment Entry Format

Each entry in the table at `0x910780` is a 16-bit word, terminated by a zero entry:

| Bits | Field | Description |
|------|-------|-------------|
| 15 | direction | 1 = horizontal segment (extends along row), 0 = vertical segment (extends down column) |
| 14 | wrap | 1 = segment wraps around maze edge |
| 13-10 | length_m1 | Segment length minus 1 (0-15 → 1-16 tiles beyond hub) |
| 9-0 | hub_slot | Slot position (row × 32 + col) of the forcefield hub |

### 9.3 Collision Check (`pf_isff`, 0x5FC5E)

The reader iterates through the segment table:
1. Extract `hub_slot` from bits 9-0; compute `delta = query_slot - hub_slot`
2. Extract `length` from bits 13-10 + 1
3. If bit 14 (wrap): adjust delta for maze edge wrapping
4. If delta <= 0: query is at or before hub → no hit
5. If bit 15 (horizontal): check `delta < length` → hit if within range
6. If bit 15 clear (vertical): check same column (`(query XOR entry) & 0x1F == 0`), then check `delta/32 < length` → hit if within row range

---

## 10. Complete Maze Catalog

### 10.1 How Maze Lookup Works

`find_maze` (0x40C78) maps a maze number to a data pointer and slapstic bank:

1. Reads a **bank lookup table** at hardware address 0x39FE0 (slapstic bank 3, file offset 0x7FE0). Each byte packs four 2-bit bank numbers (one per maze, LSB first).
2. Reads the **pointer table** starting at the address stored at 0x38000 (which is 0x3800C). Each entry is a longword pointing to the maze data within the 32KB slapstic ROM address space (0x38000–0x3FFFF).

The slapstic ROM (row10.bin, 32KB) is divided into 4 banks of 8KB:

| Bank | File Offset | Address Range | Maze Range |
|------|------------|---------------|------------|
| 0 | 0x0000 | 0x38000–0x39FFF | Mazes 0–32 |
| 1 | 0x2000 | 0x3A000–0x3BFFF | Mazes 33–62 |
| 2 | 0x4000 | 0x3C000–0x3DFFF | Mazes 63–88 |
| 3 | 0x6000 | 0x3E000–0x3FFFF | Mazes 89–115 + bank table |

### 10.2 Maze Number Ranges

| Range | Count | Purpose |
|-------|-------|---------|
| 0–4 | 5 | Unused/placeholder |
| 5–101 | 97 | Gameplay levels (Level N = Maze N+4) |
| 102 | 1 | Demo level (attract mode) |
| 103 | 1 | Legend/high-scores screen |
| 104–114 | 11 | Treasure rooms |
| 115 | 1 | Secret room |

### 10.3 Flag Randomization Note

The flags listed below are the **base flags** stored in each maze's header. At runtime, `maze_load_pickup_config` (0x436FE) **randomly adds additional flags** based on the current level number (from `ram.os_flag`) and a frame-count seed. Higher levels get progressively more aggressive random modifiers — fast monsters, odd-angle movement, invisible walls, etc. — layered on top of the base flags. This means late-game levels can have nearly any combination of flags active regardless of what's in the maze header.

### 10.4 Flag Key

| Abbreviation | Meaning |
|-------------|---------|
| OddX | Monster type X moves at odd angles |
| FastX | Monster type X moves at double speed |
| InvisTrap | Trap walls are invisible |
| InvisWalls | All walls invisible |
| CyclicWalls | Walls cycle open/closed |
| DelWalls1/2 | Destructible walls (two tiers) |
| ExitMoves | Exit relocates periodically |
| Exit1of | Only one exit of several is real |
| ShotStun | Player shots stun other players |
| ShotHurt | Player shots damage other players |
| TrapLocal/Rand | Trap behavior variants |
| WrapV/H | Maze wraps vertically/horizontally |
| FakeExit | One or more exits are fake |
| Offscreen | Players can go off-screen |
| RndFood | Count of random food items placed (0–7) |

### 10.5 Complete Maze Table

Every gameplay level (Levels 1–97) has a secret trick — there are no levels without one.

| Maze | Level | Bank | Offset | Secret Trick | RndFood | Base Flags |
|-----:|------:|-----:|-------:|:-------------|--------:|:-----------|
| 0 | — | 0 | 0x01E0 | *(unused)* | 0 | (none) |
| 1 | — | 0 | 0x0262 | *(unused)* | 0 | (none) |
| 2 | — | 0 | 0x02F4 | *(unused)* | 2 | (none) |
| 3 | — | 0 | 0x037E | *(unused)* | 2 | FastGhost, FastDeath, ExitMoves |
| 4 | — | 0 | 0x0404 | *(unused)* | 0 | CyclicWalls |
| 5 | 1 | 0 | 0x04CC | WatchShoot2 (walls) | 0 | InvisWalls |
| 6 | 2 | 0 | 0x0555 | No Greedy (treasure) | 0 | WrapH |
| 7 | 3 | 0 | 0x0631 | No Greedy (treasure) | 4 | Exit1of, TrapLocal |
| 8 | 4 | 0 | 0x07AB | Be Pushy | 0 | DelWalls1 |
| 9 | 5 | 0 | 0x0858 | Transport3 (into exit) | 0 | (none) |
| 10 | 6 | 0 | 0x08D5 | Transport3 (into exit) | 4 | OddGhost, FastGrunt, CyclicWalls, Exit1of |
| 11 | 7 | 0 | 0x097E | WatchShoot1 (food) | 0 | Exit1of |
| 12 | 8 | 0 | 0x0A76 | No Invulnerability | 6 | FastGrunt, FastDeath, Exit1of |
| 13 | 9 | 0 | 0x0B48 | No Hit (dragon) | 0 | (none) |
| 14 | 10 | 0 | 0x0CA0 | No Invulnerability | 2 | OddGrunt, OddAuxGrunt, FastGrunt, CyclicWalls |
| 15 | 11 | 0 | 0x0D6F | Don't Be Fooled | 0 | OddGhost, FastGrunt, Exit1of, TrapLocal, WrapH, FakeExit |
| 16 | 12 | 0 | 0x0EB8 | Transport2 (onto death) | 2 | ExitMoves, ShotStun, TrapLocal, WrapH |
| 17 | 13 | 0 | 0x1011 | Transport4 (into exit) | 3 | WrapH |
| 18 | 14 | 0 | 0x10D0 | No Greedy (keys/pots) | 6 | CyclicWalls, ExitMoves |
| 19 | 15 | 0 | 0x11A0 | Diet (no food) | 0 | (none) |
| 20 | 16 | 0 | 0x12B3 | Save Super Shots | 5 | CyclicWalls |
| 21 | 17 | 0 | 0x13A6 | No Hurt Friends | 2 | Exit1of |
| 22 | 18 | 0 | 0x14FC | Transport2 (onto death) | 1 | InvisWalls, Exit1of |
| 23 | 19 | 0 | 0x15A4 | Transport3 (into exit) | 0 | CyclicWalls, WrapH |
| 24 | 20 | 0 | 0x1689 | WatchShoot1 (food) | 3 | DelWalls1 |
| 25 | 21 | 0 | 0x1789 | No Greedy (keys/pots) | 0 | ExitMoves, WrapH |
| 26 | 22 | 0 | 0x1895 | WatchShoot1 (food) | 2 | DelWalls1, Exit1of |
| 27 | 23 | 0 | 0x197D | Save Super Shots | 0 | WrapH |
| 28 | 24 | 0 | 0x1A88 | No Invulnerability | 3 | ShotStun |
| 29 | 25 | 0 | 0x1B3A | Transport2 (onto death) | 0 | WrapH |
| 30 | 26 | 0 | 0x1C21 | Be Pushy | 2 | (none) |
| 31 | 27 | 0 | 0x1D25 | No Hurt Friends | 0 | TrapLocal |
| 32 | 28 | 0 | 0x1E9B | Transport3 (into exit) | 0 | WrapH |
| 33 | 29 | 1 | 0x2000 | Don't Be Fooled | 2 | Exit1of, ShotHurt, FakeExit |
| 34 | 30 | 1 | 0x20B2 | WatchShoot1 (food) | 0 | (none) |
| 35 | 31 | 1 | 0x21FF | IT Could Be Nice | 0 | (none) |
| 36 | 32 | 1 | 0x22C1 | No Hurt Friends | 0 | WrapH |
| 37 | 33 | 1 | 0x2447 | IT Could Be Nice | 5 | Exit1of |
| 38 | 34 | 1 | 0x24FC | Push a Wall | 0 | (none) |
| 39 | 35 | 1 | 0x262D | Don't Be Fooled | 4 | FastDemon, Exit1of, ShotHurt, FakeExit |
| 40 | 36 | 1 | 0x2706 | Push a Wall | 0 | Exit1of, WrapH |
| 41 | 37 | 1 | 0x282D | No Hit (dragon) | 4 | (none) |
| 42 | 38 | 1 | 0x2906 | No Hurt Friends | 0 | DelWalls1, Exit1of, WrapV, WrapH |
| 43 | 39 | 1 | 0x2A90 | Transport4 (into exit) | 0 | OddAuxGrunt, WrapH |
| 44 | 40 | 1 | 0x2C0D | No Greedy (treasure) | 0 | WrapH |
| 45 | 41 | 1 | 0x2D6C | Diet (no food) | 2 | ShotHurt, WrapH |
| 46 | 42 | 1 | 0x2E39 | IT Could Be Nice | 0 | OddGhost, OddGrunt, OddDeath, FastGhost, FastSorc |
| 47 | 43 | 1 | 0x2F57 | No Hurt Friends | 1 | OddAuxGrunt, DelWalls1, Exit1of |
| 48 | 44 | 1 | 0x30A9 | WatchShoot1 (food) | 0 | (none) |
| 49 | 45 | 1 | 0x31DA | Save Super Shots | 0 | OddGrunt, OddAuxGrunt, Exit1of, ShotStun |
| 50 | 46 | 1 | 0x328B | IT Could Be Nice | 0 | WrapH |
| 51 | 47 | 1 | 0x337F | Push a Wall | 0 | FastGhost, FastGrunt, Exit1of |
| 52 | 48 | 1 | 0x342D | Diet (no food) | 0 | Exit1of, WrapH, FakeExit |
| 53 | 49 | 1 | 0x3530 | No Hurt Friends | 0 | OddAuxGrunt |
| 54 | 50 | 1 | 0x361B | No Invulnerability | 5 | (none) |
| 55 | 51 | 1 | 0x37F3 | Be Pushy | 1 | FastGrunt, FastDemon |
| 56 | 52 | 1 | 0x388C | Transport1 (onto demon) | 0 | (none) |
| 57 | 53 | 1 | 0x3966 | No Hurt Friends | 0 | Exit1of, ShotHurt |
| 58 | 54 | 1 | 0x3A55 | Transport1 (onto demon) | 0 | DelWalls1 |
| 59 | 55 | 1 | 0x3B4F | Transport1 (onto demon) | 0 | OddGrunt |
| 60 | 56 | 1 | 0x3C63 | Don't Be Fooled | 0 | FastSorc, Exit1of, FakeExit |
| 61 | 57 | 1 | 0x3D90 | No Greedy (keys/pots) | 0 | Exit1of, WrapH |
| 62 | 58 | 1 | 0x3EB9 | Push a Wall | 0 | WrapH |
| 63 | 59 | 2 | 0x4000 | No Greedy (keys/pots) | 0 | (none) |
| 64 | 60 | 2 | 0x417C | Transport4 (into exit) | 0 | FastAuxGrunt, FastDeath, CyclicWalls, Exit1of |
| 65 | 61 | 2 | 0x4294 | Transport2 (onto death) | 0 | (none) |
| 66 | 62 | 2 | 0x4382 | No Greedy (treasure) | 0 | ShotHurt, TrapLocal |
| 67 | 63 | 2 | 0x44DB | No Hit (dragon) | 0 | FastAuxGrunt |
| 68 | 64 | 2 | 0x45B9 | Transport3 (into exit) | 0 | WrapH |
| 69 | 65 | 2 | 0x46E1 | Don't Be Fooled | 0 | Exit1of, TrapRand, WrapV, WrapH, FakeExit |
| 70 | 66 | 2 | 0x47CB | WatchShoot2 (walls) | 0 | WrapH |
| 71 | 67 | 2 | 0x4932 | WatchShoot2 (walls) | 0 | Exit1of, FakeExit |
| 72 | 68 | 2 | 0x4A45 | Transport1 (onto demon) | 0 | FastAuxGrunt |
| 73 | 69 | 2 | 0x4B68 | Transport4 (into exit) | 0 | TrapLocal |
| 74 | 70 | 2 | 0x4D14 | Save Super Shots | 0 | ExitMoves, WrapV, WrapH |
| 75 | 71 | 2 | 0x4EB5 | Transport1 (onto demon) | 0 | WrapV, WrapH |
| 76 | 72 | 2 | 0x4FDD | No Greedy (treasure) | 0 | TrapRand, WrapH |
| 77 | 73 | 2 | 0x50F7 | Don't Be Fooled | 3 | FastGhost–FastDeath (all), CyclicWalls, Exit1of, FakeExit |
| 78 | 74 | 2 | 0x5254 | No Hit (dragon) | 0 | OddGhost, FastGrunt, FastLobber, FastSorc, TrapLocal |
| 79 | 75 | 2 | 0x535B | Push a Wall | 0 | TrapRand, WrapH |
| 80 | 76 | 2 | 0x546C | Transport2 (onto death) | 0 | ShotHurt, TrapLocal, WrapH |
| 81 | 77 | 2 | 0x55F7 | No Greedy (keys/pots) | 0 | WrapH |
| 82 | 78 | 2 | 0x5789 | Save Super Shots | 0 | WrapH |
| 83 | 79 | 2 | 0x5917 | Transport1 (onto demon) | 0 | FastGrunt, FastSorc |
| 84 | 80 | 2 | 0x5A2F | No Invulnerability | 0 | FastGhost, TrapRand |
| 85 | 81 | 2 | 0x5B41 | Save Super Shots | 0 | FastGrunt |
| 86 | 82 | 2 | 0x5C36 | Transport3 (into exit) | 0 | (none) |
| 87 | 83 | 2 | 0x5D73 | IT Could Be Nice | 0 | WrapH |
| 88 | 84 | 2 | 0x5EAD | No Invulnerability | 1 | DelWalls1 |
| 89 | 85 | 3 | 0x6000 | Be Pushy | 0 | (none) |
| 90 | 86 | 3 | 0x612E | No Hit (dragon) | 0 | DelWalls2 |
| 91 | 87 | 3 | 0x6291 | Push a Wall | 0 | FastAuxGrunt, CyclicWalls |
| 92 | 88 | 3 | 0x63A0 | No Greedy (keys/pots) | 0 | OddAuxGrunt, FastAuxGrunt, FastDeath, DelWalls2, Exit1of, ShotHurt |
| 93 | 89 | 3 | 0x64B7 | Push a Wall | 0 | InvisTrap, WrapV, WrapH |
| 94 | 90 | 3 | 0x65A6 | IT Could Be Nice | 4 | DelWalls1, ExitMoves |
| 95 | 91 | 3 | 0x669B | Transport2 (onto death) | 0 | ShotStun, TrapRand, WrapH |
| 96 | 92 | 3 | 0x6786 | No Greedy (treasure) | 4 | InvisTrap, ShotStun, TrapLocal |
| 97 | 93 | 3 | 0x68A3 | No Greedy (keys/pots) | 0 | ShotHurt |
| 98 | 94 | 3 | 0x69F4 | Diet (no food) | 0 | WrapH |
| 99 | 95 | 3 | 0x6B16 | No Hit (dragon) | 0 | OddGhost, WrapH |
| 100 | 96 | 3 | 0x6C3F | WatchShoot1 (food) | 0 | InvisTrap, InvisWalls |
| 101 | 97 | 3 | 0x6D35 | Transport4 (into exit) | 4 | Exit1of |
| | | | | | | |
| 102 | — | 3 | 0x6DF2 | **Demo Level** | 0 | OddGrunt, OddAuxGrunt, FastAuxGrunt |
| 103 | — | 3 | 0x6E6C | **Legend/Scores** | 0 | (none) |
| | | | | | | |
| 104 | T1 | 3 | 0x6ED1 | Diet (no food) | 0 | CyclicWalls, Exit1of, WrapH |
| 105 | T2 | 3 | 0x6FAA | Be Pushy | 0 | CyclicWalls, Exit1of |
| 106 | T3 | 3 | 0x7081 | WatchShoot2 (walls) | 0 | ExitMoves |
| 107 | T4 | 3 | 0x715B | Diet (no food) | 0 | DelWalls1, Exit1of |
| 108 | T5 | 3 | 0x7231 | Be Pushy | 1 | Exit1of, TrapLocal, WrapH |
| 109 | T6 | 3 | 0x7424 | Diet (no food) | 0 | DelWalls2, Exit1of |
| 110 | T7 | 3 | 0x7590 | WatchShoot2 (walls) | 0 | Exit1of, WrapH |
| 111 | T8 | 3 | 0x7715 | Be Pushy | 0 | Exit1of, WrapH |
| 112 | T9 | 3 | 0x7886 | WatchShoot2 (walls) | 0 | CyclicWalls, Exit1of |
| 113 | T10 | 3 | 0x79EF | WatchShoot2 (walls) | 0 | Exit1of |
| 114 | T11 | 3 | 0x7BC9 | Diet (no food) | 0 | InvisTrap, Exit1of, TrapLocal |
| | | | | | | |
| 115 | — | 3 | 0x7D29 | **Secret Room** | 0 | (none) |

### 10.6 Secret Trick Distribution

Every gameplay level has a secret trick. Distribution across Levels 1–97:

| Secret Trick | Count | Description |
|:-------------|------:|:------------|
| Transport1 (onto demon) | 6 | Use Transportability power-up to teleport onto a demon |
| Transport2 (onto death) | 6 | Teleport onto Death |
| Transport3 (into exit) | 6 | Teleport into the exit |
| Transport4 (into exit) | 5 | Teleport into the exit (variant) |
| WatchShoot1 (food) | 6 | Avoid shooting food items |
| WatchShoot2 (walls) | 3 | Shoot secret/destructible walls to find secrets |
| Save Super Shots | 6 | Don't waste super shot power-ups |
| No Invulnerability | 6 | Complete the level without using invulnerability |
| No Hit (dragon) | 6 | Kill the dragon without getting hit |
| Push a Wall | 7 | Try pushing a movable wall |
| Don't Be Fooled | 6 | Avoid fake exits |
| No Greedy (keys/pots) | 7 | Complete without collecting keys or potions |
| No Greedy (treasure) | 6 | Complete without collecting treasure |
| Diet (no food) | 4 | Complete without eating food |
| Be Pushy | 4 | Push movable walls aggressively |
| IT Could Be Nice | 6 | Use the IT mechanic strategically |
| No Hurt Friends | 7 | Don't damage other players |

---

## 11. Function Calling Convention

The majority of the Game ROM is compiled C. The calling convention is a standard **stack-based, caller-cleanup convention** consistent with the Green Hills C compiler that Atari Games used for 68000-family targets in this era. A small number of leaf functions (notably `input_debounce` at 0x40644 and parts of the Slapstic bank-switch trampoline) are hand-written assembly and do not follow this convention.

### 11.1 Prologue / Epilogue

Compiled functions follow this pattern:

```
; ── Prologue ──
link.w  a6, #-N             ; save old a6, set frame pointer, allocate N bytes of locals
movem.l <reg-list>, -(a7)   ; save callee-saved registers used by this function

; ── Epilogue ──
movem.l -offset(a6), <reg-list>   ; restore saved registers
unlk    a6                         ; restore old a6 and deallocate locals
rts
```

`a6` is always the frame pointer. Local variables live at negative offsets from `a6`; arguments live at positive offsets.

A few heavily-used functions (e.g. `mob_create` at 0x5dc58) omit the `link`/`unlk` and access arguments relative to `a7` instead, saving a few cycles. This is likely a hand-optimization or aggressive compiler flag rather than a different convention — the argument layout on the stack is identical.

### 11.2 Argument Passing

All arguments are pushed **right-to-left** (last argument pushed first) as **32-bit longwords**, even when the logical type is 16-bit. Values are sign- or zero-extended to 32 bits before the push. Common push idioms:

| Instruction | Effect |
|-------------|--------|
| `move.l dN, -(a7)` | Push a register (already extended to long) |
| `pea.l <ea>` | Push an effective address (pointer arg) |
| `clr.l -(a7)` | Push a zero argument |
| `pea.l 0x20.w` | Push an immediate constant as a longword |

Because the 68010 is **big-endian**, the low (meaningful) 16 bits of each longword slot sit at +2 within the slot. Functions that consume `int`-sized (16-bit) arguments therefore read them with a word-sized load at the +2 offset:

```
; Frame-pointer form (most functions):
;   a6+0  = saved old a6
;   a6+4  = return address
;   a6+8  = arg 1 longword  → low word at a6+0x0A
;   a6+C  = arg 2 longword  → low word at a6+0x0E
;   a6+10 = arg 3 longword  → low word at a6+0x12
;   ...
move.w  0xa(a6), d6      ; read arg 1 as a word
move.w  0xe(a6), d3      ; read arg 2 as a word
```

### 11.3 Caller Cleanup

The **caller** removes arguments from the stack after the call returns, typically with `lea`:

```
; Example: call mob_create with 6 longword args (24 bytes)
move.l  d0, -(a7)          ; arg 6
move.l  d0, -(a7)          ; arg 5
move.l  d0, -(a7)          ; arg 4
move.l  d0, -(a7)          ; arg 3
move.l  d0, -(a7)          ; arg 2
move.l  d0, -(a7)          ; arg 1
jsr     mob_create
lea     0x18(a7), a7       ; pop 24 bytes (6 × 4)
```

This is the cdecl convention: the caller knows how many arguments it pushed and cleans them up. No `rts #N` or callee-side stack adjustment is used anywhere in the ROM.

### 11.4 Return Values

Return values are passed in **d0**. Word-sized results use `d0.w`; longword/pointer results use `d0.l`. Functions that return void simply leave d0 undefined.

```
jsr     0x24e               ; OS API: allocate display list
move.w  d0, d2              ; capture 16-bit return value
```

### 11.5 Register Classes

| Registers | Role | Convention |
|-----------|------|-----------|
| d0–d1 | Scratch / temporaries | **Caller-saved** — any call may destroy these |
| d2–d7 | General purpose | **Callee-saved** — must be preserved across calls |
| a0–a1 | Scratch / pointer temps | **Caller-saved** — any call may destroy these |
| a2–a5 | General purpose pointers | **Callee-saved** — must be preserved across calls |
| a6 | Frame pointer | Saved/restored by `link`/`unlk` |
| a7 | Stack pointer | Managed implicitly |

Functions save only the callee-saved registers they actually use. For example, `main_handle_potions` (0x46fea) saves `d2/a2-a3`, while `mob_create` (0x5dc58) saves the full set `d2-d7/a2-a6`.

### 11.6 Identifying Hand-Written Assembly

A handful of functions are hand-written assembly rather than compiler output. Telltale signs:

- **No `link`/`unlk`** and **no `movem` save** — the function only uses scratch registers (d0-d1, a0-a1)
- **No stack-based arguments** — inputs arrive in registers or at fixed memory addresses
- **Unusual instruction sequences** not typical of compiler output (e.g. `roxl` for bit-serial I/O debouncing at 0x40644)
- **Inline within the Slapstic trampoline** — bank-switch helpers at 0x56E58/0x56E6E operate outside normal calling convention

---

## Previously Listed Unknowns — Now Resolved

The following items from the original analysis have been fully resolved by the complete function analysis (see FUNCTIONS_PLAN.md):

1. ~~**Monster health/damage tables**~~ — **RESOLVED.** Damage multiplier tables found at 0x5B7D4 (8 words, indexed by player_class × enemy_type, values 1–3) and 0x5B7E4 (12 words, special attack damage, values 0–4). Monster shot damage values at 0x596CE. Health is accumulated per-mob at RAM 0x904B3A; player is killed when accumulator exceeds 200, handled by `accumulate_hit_damage` (0x49A3C). Per-monster hit points are not in a separate table — they are encoded in the high bits of the MOB link word at 0x904066[mob*2] (bits 15-10), set during mob creation.

2. ~~**Monster speed tables**~~ — **RESOLVED.** All monster types share a base speed of 0x80, built on the stack in `monster_loop_core` (0x40E6A). The speed override table at 0x40E02 (7 longwords) overrides specific types to 0x100 (double speed) when fast-monster level flags are set in 0x90491D. Movement frequency is controlled probabilistically: each frame, `random(32)` is compared against the speed value — higher speed means higher chance of moving. There is no per-type base speed ROM table.

3. ~~**Dragon animation tables**~~ — **RESOLVED.** Fully traced in `main_handle_dragon` (0x54454). Dragon head sprites at ROM 0x5D508, fire-breath tiles at 0x5D568, body segment tile lookup at 0x5D4B8, X/Y position offsets at 0x5D528/0x5D478, 128-step circular body path at 0x5D578. The master table entry 0xA740 has bit 15 set as a software flag; actual display tiles are selected from the path table based on animation counter and segment index. Dragon health tracked at RAM 0x90488C; death sequence at 0x53D10.

4. ~~**Attract mode screen setup**~~ — **RESOLVED.** `start_attract_screen` (0x44414) fully disassembled. Dispatches on game_mode argument: -2 (TITLE) → timer 0x5DD, calls 0x4438E + 0x4DA3E, refreshes EEPROM every 13 cycles. -1 (SCORES) → timer 0x258, calls 0x4A124. -3 (DEMO) → timer 0x1C20, calls 0x449D4 (init demo level), clears frame counter. -4 (LEGEND) → timer 0x258, clears playfield, draws legend art, loads demo level.

## Remaining Unknowns

After complete analysis of all 170 functions and ~99% of ROM data tables, the following items remain not fully decoded:

1. **Dragon path table internal bit fields** (ROM 0x5D578, ~2 KB): The 128-step circular path table has 16 bytes per entry. Bit 0 of the control byte is the fire-trigger flag (confirmed by disassembly). The remaining 7 bits of the control byte and the purpose of the other 15 bytes per entry (which control body segment shape, curvature, and inter-segment spacing) have not been individually mapped. The general mechanism is understood — `main_handle_dragon` reads path entries indexed by `(animation_counter >> 3) * 16 + path_index * 16` — but the per-byte semantics within each 16-byte record are unknown.

2. **EEPROM game settings bit map** (RAM 0x904A24, 16 bits): Read from EEPROM slot 0xC at boot. Known bit assignments:
   - Bits 0–4: COINHEALTH setting (indexes `health_per_coin` table at 0x57862)
   - Bits 5–7: **Unknown** (read but purpose not identified)
   - Bits 8–9: Difficulty level (0–3)
   - Bit 10: 2-player mode flag
   - Bit 11: Sound mute flag
   - Bit 12: ROM version flag (cleared after first boot)
   - Bit 13: **Unknown**
   - Bit 14: Music/attract sound enable
   - Bit 15: Settings dirty flag (triggers player state reset in `init_monster_system`)

3. **~600 bytes at 0x5825E–0x584F0**: Between the end of demo input streams and the start of the in-game tip strings. Partially covered by the 12-entry dialog tip pointer table at 0x58154 (which points into this range) and the tip display records themselves (3-pointer + 3-string groups like "PUSH / MOVABLE / WALLS"). The records that these pointers reference are readable ASCII, but the exact boundaries and count of all tip record groups hasn't been exhaustively listed.

4. **Tile pattern index mapping**: The ~450 tile sprite descriptors at 0x5BAE0–0x5C88F are organized as 32-entry blocks per tileset. The entry format is known (4 words = 2×2 tile, order TL/BL/TR/BR). However, the mapping from the maze header's `wallpattern` (0–15) and `floorpattern` (0–15) bytes to specific descriptor block indices has not been worked out. The code in `refresh_tile_visual` (0x5F5A0) selects tables via pointer indirection, making the mapping non-obvious without tracing specific wallpattern/floorpattern values through the lookup chain.

---

*Analysis performed via radare2 disassembly of row9.bin (0x0), row76.bin (0x40000), and row10.bin (0x38000). Cross-referenced with python-gex tile data, soundcmds.csv, OS_ROM.md, HW_WRITEUP.md, and GAME_ROM_KNOWN.md.*

*Complete function analysis covering all 29 main-loop phases, 170 compiled functions, and ~120 KB of ROM data is documented in FUNCTIONS_PLAN.md and ROM_COVERAGE.md.*
