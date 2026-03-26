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

### 4.4 Monster Animation

Monster animation follows a similar pattern to players but is simpler. Each monster type has a fixed arrangement of animation tiles in the graphics ROM, organized as:

```
base_tile + (direction × frames_per_direction × tiles_per_frame) + (frame × tiles_per_frame)
```

Where `tiles_per_frame` = width × height of the monster sprite (e.g., 9 for a 3×3 monster like ghosts).

For example, ghost animation tiles (from python-gex cross-reference):

| Direction | Frame 0 | Frame 1 | Frame 2 | Frame 3 |
|-----------|---------|---------|---------|---------|
| Down (4) | 2048 | 2057 | 2066 | 2075 |
| Down-Right (3) | 2084 | 2093 | 2102 | 2111 |
| Right (2) | 2120 | 2129 | 2138 | 2147 |
| Up-Right (1) | 2156 | 2165 | 2174 | 2183 |
| Up (0) | 2192 | 2201 | 2210 | 2219 |
| Up-Left (5) | 2228 | 2237 | 2246 | 2255 |
| Left (6) | 2264 | 2273 | 2282 | 2291 |
| Down-Left (7) | 2304 | 2313 | 2322 | 2331 |

Note: The tiles in ROM are arranged in a different order than the software direction enum. The direction-to-tile mapping is handled by the animation update code within `monsters_everything`, which reads the direction from `mob_anim` bits 12-10 and the frame counter from bits 15-13, then computes the tile number and writes it to `mob_picture`.

The monster animation counter (bits 15-13 of mob_anim) is typically incremented within the per-monster-type movement handlers. Different monster types may advance their animation at different rates by incrementing only on certain frames (using the frame counter modulo a speed value).

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

### 5.2 Monster Data Tables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x40E02 | 28B | monster_speed_override | 7 longword speed values for monster types, used with fast-monster flags |
| 0x40E46 | ~32B | monster_count_table | Max monster count by difficulty + active player count |
| 0x4A4FA | ~64B | stun_input_remap | Input modification table for stunned players |

Monster tile numbers are assigned during maze object setup based on the MAZEOBJ type and are computed from base tile numbers. The specific base tiles for each monster type, cross-referenced with the python-gex data:

| Monster Type | MAZEOBJ ID | Base Tile | Size | Palette |
|-------------|-----------|-----------|------|---------|
| Ghost | 0x12 (18) | 2048 | 3×3 | 0 (or 4) |
| Grunt | 0x13 (19) | 2529 | 3×3 | 4 |
| Demon | 0x14 (20) | 6207 | 3×3 | 8 |
| Lobber | 0x15 (21) | 6999 | 3×2 | 11 |
| Sorcerer | 0x16 (22) | 5026 | 3×3 | 11 |
| Aux Grunt | 0x17 (23) | 2529 | 3×3 | 4 |
| Death | 0x18 (24) | 6773 | 3×3 | 0 |
| Acid | 0x19 (25) | 8960 | 3×3 | 1 |
| Super Sorc | 0x1A (26) | 5026 | 3×3 | 11 |
| IT | 0x1B (27) | 9728 | 3×3 | 8 |
| Dragon | 0x3C (60) | 8448 | 4×4 | 8 |

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

## Areas Requiring Further Analysis

The following areas were identified but not fully traced in this analysis pass:

1. **Monster animation tile computation**: The exact mechanism by which monster types select their animation tiles was not fully traced through `monsters_everything`. The tile numbers are likely computed from base tile + direction/frame offsets rather than looked up from explicit tables (unlike player animation which uses direct table lookups).

2. **Maze object placement**: The function(s) that scan the decoded maze data and call `mob_create` for each monster, item, and special object were not fully identified. This likely occurs within `maze_decode` (0x4c1bc) or a post-decode scan.

3. **Complete monster type parameter table**: While tile numbers and sizes are known from the python-gex cross-reference, the ROM location of the master table that maps MAZEOBJ type IDs to (tile, size, palette, speed, health, damage) was not found. This table likely exists in the 0x56000–0x58000 range based on nearby data tables.

4. **Per-monster movement handlers**: The `monsters_everything` function dispatches to type-specific movement handlers based on the MAZEOBJ type in mob_link bits 15-10. The dispatch mechanism and individual handler addresses were not fully cataloged.

5. **Force field segment table construction**: The function at 0x53398 builds the forcefield segment table at 0x910780 by scanning for FORCEFIELDHUB objects, but the complete segment format was not fully decoded.

---

*Analysis performed via radare2 disassembly of row9.bin (0x0), row76.bin (0x40000), and row10.bin (0x38000). Cross-referenced with python-gex tile data, soundcmds.csv, OS_ROM.md, HW_WRITEUP.md, and GAME_ROM_KNOWN.md.*
