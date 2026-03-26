# Gauntlet OS ROM (row9.bin) - Comprehensive Reverse Engineering Analysis

## Overview

The Gauntlet OS ROM is a 64KB binary (`row9.bin`, mapped at `0x00000000-0x0000FFFF`) for the **Motorola 68010** CPU. It provides the complete hardware bootstrap, diagnostic/self-test mode, OS services (interrupt dispatch, video scrolling, input handling, EEPROM management, sound interface), and significant game-related code (attract mode, coin handling, player setup, text display, treasure rooms, high score management).

**Key Facts:**
- CPU: Motorola 68010 (32-bit addresses)
- Display: 336x240, 60Hz refresh
- ROM size: 65,536 bytes (0x10000)
- Initial SSP: `0x00904F00` (Video RAM Spare area)
- Initial PC: `0x000005E2` (reset_entry)
- Game ROM at: `0x040000-0x07FFFF`

---

## 1. ROM Memory Map

### 1.1 Address Space Layout

| Region | Address Range | Size | Description |
|--------|--------------|------|-------------|
| **OS ROM** | `0x000000-0x00FFFF` | 64 KB | This ROM - bootstrap, OS, diagnostics, game support |
| Slapstic ROM | `0x038000-0x03FFFF` | 32 KB | Level data (bank-switched) |
| **Game ROM** | `0x040000-0x07FFFF` | 256 KB | Main game program |
| **Main RAM** | `0x800000-0x801FFF` | 8 KB | General-purpose RAM |
| **EEPROM** | `0x802001-0x802FFF` | ~4 KB | High scores, settings, statistics (odd bytes only) |
| **Hardware I/O** | `0x803000-0x8031FF` | 512 B | Input ports, watchdog, sound, LEDs |
| **Playfield RAM** | `0x900000-0x901FFF` | 8 KB | Playfield tile map |
| **MOB RAM** | `0x902000-0x903FFF` | 8 KB | Motion object (sprite) data |
| **Video RAM Spare** | `0x904000-0x904FFF` | 4 KB | OS working variables |
| **Alpha RAM** | `0x905000-0x905FFF` | 4 KB | Alphanumeric character overlay |
| **Color RAM** | `0x910000-0x9107FF` | 2 KB | Color palettes |
| **PF H-Scroll** | `0x930000-0x930001` | 2 B | Playfield horizontal scroll register |

### 1.2 Hardware I/O Ports

| Address | R/W | Description |
|---------|-----|-------------|
| `0x803001` | R | Player 1 inputs |
| `0x803003` | R | Player 2 inputs |
| `0x803005` | R | Player 3 inputs |
| `0x803007` | R | Player 4 inputs |
| `0x803009` | R | VBLANK status / SoundIOFull / Self-test switch |
| `0x80300E` | R | Read from sound processor |
| `0x803100` | W | Watchdog reset |
| `0x803120` | W | Hardware latch (bit 0 = LED/board enable) |
| `0x803121` | W | LED 1 |
| `0x803123` | W | LED 2 |
| `0x803125` | W | LED 3 |
| `0x803127` | W | LED 4 |
| `0x80312E` | W | Sound processor reset/control |
| `0x803140` | W | VBLANK acknowledge |
| `0x803150` | W | EEPROM unlock |
| `0x803170` | W | Interrupt control register |
| `0x803171` | W | Write to sound processor |

### 1.3 Status Register Bits at `0x803009`

| Bit | Description |
|-----|-------------|
| 0 | Player 1 start button (active low, used for boot wait) |
| 3 | Self-test switch (1 = self-test active) |
| 5 | Sound I/O full |
| 6 | VBLANK status (toggles each field) |

---

## 2. M68010 Vector Table (`0x000000-0x000FF`)

The first 256 bytes of the ROM contain the 68010 exception vector table:

| Offset | Vector | Value | Target |
|--------|--------|-------|--------|
| `0x000` | Initial SSP | `0x00904F00` | Stack in Video RAM Spare |
| `0x004` | Initial PC | `0x000005E2` | `reset_entry` |
| `0x008` | Bus Error | `0x00000300` | `exception_handler` |
| `0x00C` | Address Error | `0x00000300` | `exception_handler` |
| `0x010` | Illegal Instruction | `0x00000300` | `exception_handler` |
| `0x014` | Divide by Zero | `0x00000300` | `exception_handler` |
| ... | (Other exceptions) | `0x00000300` | `exception_handler` |
| `0x064` | Autovector Level 1 | `0x00000314` | `irq1_handler` |
| `0x068` | Autovector Level 2 | `0x00000326` | `irq2_handler` |
| `0x06C` | Autovector Level 3 | `0x00000338` | `irq3_handler` |
| `0x070` | Autovector Level 4 | `0x0000034A` | `irq4_vblank_handler` |
| `0x078` | Autovector Level 6 | `0x0000036C` | `irq6_handler` |

---

## 3. OS API Jump Table (`0x000100-0x00027F`)

The jump table at `0x100` is the OS API entry point. It consists of `JMP <absolute>.l` instructions (6 bytes each). Game code and internal OS code call through these fixed addresses to access OS services. This allows the OS implementation to be relocated without changing the game ROM.

### 3.1 Jump Table Entries (`0x100-0x1D7`)

| Entry | Address | Target | Function Name | Category |
|-------|---------|--------|---------------|----------|
| 0x100 | `0x100` | `0x3162` | `start_scroll_text` | Text Effects |
| 0x106 | `0x106` | `0x2ABE` | `format_decimal` | Number Formatting |
| 0x10C | `0x10C` | `0x2A5E` | `format_hex` | Number Formatting |
| 0x112 | `0x112` | `0x2918` | `format_number` | Number Formatting |
| 0x118 | `0x118` | `0x30F4` | `stop_text_effect` | Text Effects |
| 0x11E | `0x11E` | `0x3156` | `start_scroll_type4` | Text Effects |
| 0x124 | `0x124` | `0x3122` | `start_scroll_updown` | Text Effects |
| 0x12A | `0x12A` | `0x3168` | `start_scroll_type1` | Text Effects |
| 0x130 | `0x130` | `0x316C` | `start_scroll_type3` | Text Effects |
| 0x136 | `0x136` | `0x3130` | `init_scroll_system` | Text Effects |
| 0x13C | `0x13C` | `0x35B2` | `set_text_position` | Text Display |
| 0x142 | `0x142` | `0x2E36` | `display_text` | Text Display |
| 0x148 | `0x148` | `0x2B3C` | `process_text_effects` | Text Effects |
| 0x14E | `0x14E` | `0x3522` | `init_alpha_display` | Alpha Display |
| 0x154 | `0x154` | `0x359A` | `wait_vblanks` | Timing |
| 0x15A | `0x15A` | `0x41FA` | `process_sound` | Sound |
| 0x160 | `0x160` | `0x3740` | `calc_health_per_coin` | Coin/Credit |
| 0x166 | `0x166` | `0x37C2` | `check_and_deduct_coin` | Coin/Credit |
| 0x16C | `0x16C` | `0x35C4` | `process_coins` | Coin/Credit |
| 0x172 | `0x172` | `0x4184` | `send_sound_command` | Sound |
| 0x178 | `0x178` | `0x42C8` | `read_sound_data` | Sound |
| 0x17E | `0x17E` | `0x427A` | `send_sound_immediate` | Sound |
| 0x184 | `0x184` | `0x4802` | `eeprom_check_busy` | EEPROM |
| 0x18A | `0x18A` | `0x432E` | `eeprom_process` | EEPROM |
| 0x190 | `0x190` | `0x44E8` | `eeprom_init` | EEPROM |
| 0x196 | `0x196` | `0x47A8` | `eeprom_request_write` | EEPROM |
| 0x19C | `0x19C` | `0x4038` | `process_coin_stats` | Statistics |
| 0x1A2 | `0x1A2` | `0x3860` | `read_eeprom_setting` | Config |
| 0x1A8 | `0x1A8` | `0x38C0` | `read_game_config` | Config |
| 0x1AE | `0x1AE` | `0x39B0` | `read_high_score_entry` | High Scores |
| 0x1B4 | `0x1B4` | `0x3A7E` | `write_high_score_entry` | High Scores |
| 0x1BA | `0x1BA` | `0x3BE8` | `get_eeprom_base` | EEPROM |
| 0x1C0 | `0x1C0` | `0x3CF6` | `write_eeprom_setting` | Config |
| 0x1C6 | `0x1C6` | `0x3F68` | `read_eeprom_config` | Config |
| 0x1CC | `0x1CC` | `0x401A` | `write_eeprom_config` | Config |
| 0x1D2 | `0x1D2` | `0x5454` | `run_self_test` | Diagnostics |

### 3.2 Data Table (`0x1D8-0x1F7`)

This area contains address constants (not JMP instructions):

| Offset | Value | Description |
|--------|-------|-------------|
| `0x1D8` | `0x00904006` | → `ram.pf_vscroll_hi` |
| `0x1DC` | `0x00904008` | → `ram.pf_hscroll` |
| `0x1E0` | `0x00904F8A` | → `ram.player_inputs_snapshot` |
| `0x1E4` | `0x00904004` | → `ram.vblank_occurred` |
| `0x1E8` | `0x0090400C` | → `ram.timer_countdown` |
| `0x1EC` | `0x0080300E` | → `hw.sound_read` (approx) |
| `0x1F0` | `0x00803170` | → `hw.interrupt_control` |
| `0x1F4` | `0x0090400A` | → `ram.pf_vscroll_lo` |

### 3.3 Jump Table Entries (`0x200-0x278`)

| Entry | Address | Target | Function Name | Category |
|-------|---------|--------|---------------|----------|
| 0x200 | `0x200` | `0x31D2` | `display_large_text` | Large Characters |
| 0x206 | `0x206` | `0x3346` | `display_large_char_styled` | Large Characters |
| 0x20C | `0x20C` | `0x32BC` | `display_large_char_at` | Large Characters |
| 0x212 | `0x212` | `0x32A0` | `display_large_char_raw` | Large Characters |
| 0x218 | `0x218` | `0x3044` | `write_alpha_char` | Alpha Display |
| 0x21E | `0x21E` | `0x3586` | `write_alpha_word` | Alpha Display |
| 0x224 | `0x224` | `0x2CE4` | `calc_alpha_address` | Alpha Display |
| 0x230 | `0x230` | `0x3804` | `check_credits` | Coin/Credit |
| 0x236 | `0x236` | `0x3706` | `get_coin_multiplier` | Coin/Credit |
| 0x23C | `0x23C` | `0x41C8` | `disable_interrupts` | Interrupt Control |
| 0x242 | `0x242` | `0x41CC` | `enable_interrupts` | Interrupt Control |
| 0x248 | `0x248` | `0x58C6` | `display_attract_screen` | Game Display |
| 0x24E | `0x24E` | `0x4822` | `eeprom_read_block` | EEPROM |
| 0x254 | `0x254` | `0x42F8` | `reset_sound_cpu` | Sound |
| 0x25A | `0x25A` | `0x2F04` | `draw_string` | Text Display |
| 0x260 | `0x260` | `0x2EB4` | `display_decimal_value` | Text Display |
| 0x266 | `0x266` | `0x2EEA` | `display_hex_value` | Text Display |
| 0x26C | `0x26C` | `0x332A` | `large_char_lookup` | Large Characters |
| 0x272 | `0x272` | `0x32DA` | `large_char_data` | Large Characters |
| 0x278 | `0x278` | `0x3310` | `large_char_render` | Large Characters |

---

## 4. Boot Sequence

### 4.1 Reset Entry (`0x5E2` - `reset_entry`)

The 68010 loads SSP from `0x000000` (= `0x904F00`) and PC from `0x000004` (= `0x5E2`).

```
1. Set SR = 0x2700 (supervisor mode, all interrupts masked)
2. Write 0x0001 to hardware latch (0x803120) - enable board
3. Write 0x0000 to hardware latch - reset pulse
4. Delay loop (0xFA0 iterations) petting watchdog
5. Write 0x0001 to hardware latch - re-enable
6. Read self-test switch (bit 3 of 0x803009)
7. If self-test: JMP selftest_boot (0x61E)
8. Otherwise:    JMP normal_boot (0x3A0)
```

### 4.2 Normal Boot (`0x3A0` - `normal_boot`)

Performs a quick memory test on each video RAM region. Uses `mem_test_quick` (0xA6A) which does multiple passes with walking-bit patterns. If any test fails, displays the error and waits for operator acknowledgment (VBLANK toggle + player 1 button).

```
1. Test Video RAM Spare     (0x904000-0x904FFE) → error: continue
2. Test Color RAM           (0x910000-0x9107FE) → error: display "COLOR RAM error"
3. Test Playfield RAM       (0x900000-0x901FFE) → error: display "PLAYFIELD RAM error"
4. Test Alpha RAM           (0x905000-0x905FFE) → error: display "ALPHA RAM error"
5. Test MOB RAM             (0x902000-0x903FFE) → error: display "MOTION OBJ RAM error"
6. On success: JMP main_init_cont (0x70C)
```

### 4.3 Self-Test Boot (`0x61E` - `selftest_boot`)

Same tests as normal boot but uses the more thorough `mem_test_thorough` (0xA2C). Also initializes Color RAM with an incrementing pattern first.

### 4.4 Main Init Continuation (`0x70C` - `main_init_cont`)

```
1.  Clear d5 (error flag)
2.  Clear ram.os_flag (0x904000)
3.  Clear all Color RAM (0x910000-0x9107FE) and set:
    - Color 0: 0x0000 (black)
    - Colors 1-3: 0xF00F (white)
    - Playfield color 0: 0x0000
4.  Enable hardware latch
5.  Reset stack to 0x904F00
6.  Call init_alpha_display (0x3522) - clears alpha overlay
7.  ROM Checksum:
    - Two byte accumulators: d0 initialized to 0, d1 initialized to 1
    - Loop 0x8000 times, adding even-addressed bytes to d0 and odd-addressed bytes to d1
    - Both must equal 0xFF after summing (so even bytes must sum to 0xFF, odd bytes must sum to 0xFE)
    - On failure: call rom_checksum_display (0xCC0)
    - In self-test mode: continue regardless
    - In normal mode: wait for operator acknowledgment
8.  Enable hardware latch again
9.  Pet watchdog
10. Set ram.game_hook_flag = 1 (assume no valid game ROM)
11. Check for valid game ROM:
    - 0x40000 must contain JMP instruction (0x4EF9)
    - Target address must be in range 0x40000-0x7FFFF
    - If invalid: display "NO GAME PROGRAM" and wait
12. If valid game ROM:
    - Clear ram.game_hook_flag
    - Validate game ROM checksums from table at 0x40080
    - Each entry: {source_addr, end_addr, length, checksum_present_flag}
    - Report any errors with "ROM at XXXXX error"
13. Validate EEPROM:
    - Call subroutine at 0x21A0
    - If invalid and not self-test: wait for operator
14. Clear Video RAM Spare (0x904000-0x904FFB, 4092 bytes via `move.l #0x3FE, d0` / `dbra` / `clr.l` loop)
15. Call eeprom_init (0x44E8)
16. Branch based on state:
    - Self-test mode + no errors: JMP game ROM start (0x40000)
    - Self-test mode + errors (d5=1): JMP os_vblank_mode_entry → self-test
    - Normal mode: JMP os_vblank_mode_entry → game attract
    - Error state (d5=2): invoke exception handler at 0x40024
```

---

## 5. Interrupt System

### 5.1 Architecture

All interrupt handlers follow the same pattern: check if the game ROM has installed a handler (by testing for a `JMP` instruction = opcode `0x4EF9` at the expected hook address), and if so, dispatch to it. If no game handler is installed, the interrupt returns silently via `RTE`.

This allows the OS ROM to work standalone (for self-test) and with any compatible game ROM.

### 5.2 Exception Handler (`0x300` - `exception_handler`)

```c
if (*(uint16_t*)0x40024 == 0x4EF9) {  // JMP opcode present?
    d0 = 0;                              // clear error code
    JMP 0x40024;                         // dispatch to game exception handler
}
RTE;                                     // otherwise, return from exception
```

### 5.3 IRQ1 Handler (`0x314` - `irq1_handler`)

Hooks to game ROM at `0x4000C`. Used for game-specific periodic tasks.

### 5.4 IRQ2 Handler (`0x326` - `irq2_handler`)

Hooks to game ROM at `0x40018`.

### 5.5 IRQ3 Handler (`0x338` - `irq3_handler`)

Hooks to game ROM at `0x40012`.

### 5.6 IRQ4 / VBLANK Handler (`0x34A` - `irq4_vblank_handler`)

The most important interrupt. Has two modes:

```c
if (ram.os_vblank_active != 0) {
    // OS is in control - use OS VBLANK handler
    JMP os_vblank_handler;               // at 0x0E5E
} else {
    // Game is in control
    if (*(uint16_t*)0x40006 == 0x4EF9) {
        JMP 0x40006;                     // dispatch to game VBLANK handler
    }
    WRITE(hw.vblank_ack);               // acknowledge VBLANK
    RTE;
}
```

### 5.7 IRQ6 Handler (`0x36C` - `irq6_handler`)

Handles sound processor communication:

```c
if (bit3(hw.vblank_selftest)) {          // self-test switch active?
    if (*(uint16_t*)0x4001E == 0x4EF9) {
        JMP 0x4001E;                     // dispatch to game IRQ6 handler
    }
    READ(0x80300E);                      // dummy read to clear interrupt
    RTE;
} else {
    // OS handles sound data
    ram.sound_data_recv = READ(0x80300E);
    ram.sound_data_flag = 0;             // signal data available
    RTE;
}
```

---

## 6. OS VBLANK System

### 6.1 OS VBLANK Mode Entry (`0xE14` - `os_vblank_mode_entry`)

Called when the OS takes control (self-test, attract mode, etc.). Sets up the OS to handle VBLANK interrupts directly:

```c
ram.os_vblank_active = 1;     // tell IRQ4 to use OS handler
ram.pf_vscroll_hi = 0;        // reset scroll positions
ram.pf_hscroll = 0;
ram.pf_vscroll_lo = 0;
ram.vblank_occurred = 0;
ram.os_flag = 0;
call 0x355C;                  // clear text effect state
SR = 0x2000;                  // enable all interrupts
call 0x129A(d5);              // OS main loop (d5 = mode flag)
SR = 0x2700;                  // disable interrupts
ram.os_vblank_active = 0;     // return VBLANK control to game
JMP 0x8EC;                    // return to boot sequence continuation
```

### 6.2 OS VBLANK Handler (`0xE5E` - `os_vblank_handler`)

Called every VBLANK (60Hz) when the OS is in control:

```c
// Save registers
PUSH d0-d1/a0-a1;

// Acknowledge and pet watchdog
WRITE(hw.vblank_ack);
WRITE(hw.watchdog);

// Update scroll registers from shadow variables
scroll_v = (ram.pf_vscroll_hi << 7) | ram.pf_vscroll_lo;
WRITE(0x905F6E, scroll_v);            // playfield vertical scroll
WRITE(0x930000, ram.pf_hscroll);      // playfield horizontal scroll

// Self-test switch check
if (bit3(hw.vblank_selftest)) {
    call eeprom_check_busy;            // check EEPROM status
    if (result == 0) {
        SR = 0x2700;                   // fatal: EEPROM failure during self-test
        infinite_loop();               // hang (watchdog will reset)
    }
}

// Signal VBLANK to main loop
ram.vblank_occurred = 1;

// Decrement countdown timer
ram.timer_countdown--;

// Process text scrolling effects
call process_text_effects;

// Input snapshot
if (ram.game_hook_flag == 0) {
    if (*(uint16_t*)0x40042 == 0x4EF9) {
        call 0x40042;                  // game VBLANK hook (reads inputs)
    }
} else {
    d0 = READ_LONG(0x803000);         // read all 4 player inputs directly
}
ram.player_inputs_snapshot = d0;

// Process EEPROM writes
call eeprom_process;

// Restore and return
POP d0-d1/a0-a1;
RTE;
```

---

## 7. Detailed Function Descriptions

### 7.1 Number Formatting Functions

#### `format_decimal` (`0x2ABE`, API `0x106`)

Converts a 32-bit unsigned integer to a decimal ASCII string.

**Stack parameters:**
- `+0x08(SP)`: Value to convert (long)
- `+0x0C(SP)`: Buffer pointer (address)
- `+0x12(SP)`: Field width (word)
- `+0x16(SP)`: Leading zeros flag (word, 0 = space-fill)

**Operation:** Repeatedly divides by 10, building the string right-to-left. Handles values > 99999 by splitting the division. Pads with spaces if leading-zero flag is not set.

#### `format_hex` (`0x2A5E`, API `0x10C`)

Converts a 32-bit value to hexadecimal ASCII string.

**Stack parameters:**
- `+0x04(SP)`: Value to convert (long)
- `+0x08(SP)`: Buffer pointer (address)
- `+0x0E(SP)`: Field width (word)
- `+0x12(SP)`: Uppercase flag (word)

#### `format_number` (`0x2918`, API `0x112`)

General-purpose number formatter supporting multiple bases and formats.

**Stack parameters:**
- `+0x08(SP)`: Buffer pointer (address)
- `+0x0F(SP)`: Format character (byte): `'d'`=decimal, `'s'`=signed, `'X'`/`'x'`/`'h'`=hex, `'o'`=octal, `'b'`=binary

### 7.2 Text Display Functions

#### `display_text` (`0x2E36`, API `0x142`)

The primary text display function. Displays a string at a position on the alpha overlay with support for both normal and scrolled display modes.

**Stack parameters:**
- `+0x04(SP)`: Text descriptor pointer (address to struct: {row, col, string_ptr, continuation})
- `+0x0A(SP)`: Color/attribute word

**Text descriptor struct:**
```c
struct text_desc {
    uint8_t row;          // +0: Y position (0-29)
    uint8_t col;          // +1: X position (0-41)
    uint32_t string_ptr;  // +2: pointer to null-terminated ASCII string
    uint8_t repeat;       // +6: continuation count (adds to scroll offset)
    uint32_t next_ptr;    // +8: pointer to next text descriptor (for chaining)
};
```

**Operation:** Calculates the alpha RAM address based on `ram.display_mode` (0x904F0E). In normal mode, `row * 64 + col` indexes into alpha RAM at `0x905000`. In scrolled mode (Gauntlet-specific), row is inverted (`41 - col`) and multiplied by 128 for the scrolling display format. Characters are written as words with color/attribute bits in the upper byte.

#### `draw_string` (`0x2F04`, API `0x25A`)

Draws an ASCII string directly to alpha RAM at a specified row/column.

**Stack parameters:**
- `+0x07(SP)`: Row (byte)
- `+0x0B(SP)`: Col (byte)
- `+0x0C(SP)`: String pointer (address)
- `+0x12(SP)`: Color/style (word): bits 0-1 select character style (0=normal, 1=uppercase shifted, 2=lowercase shifted)

**Returns:** D0 = number of characters written.

#### `display_decimal_value` (`0x2EB4`, API `0x260`)

Convenience function that formats a decimal number and displays it. Calls `format_decimal` to format, then `display_text` to show it.

#### `display_hex_value` (`0x2EEA`, API `0x266`)

Same as above but for hexadecimal values.

#### `write_alpha_char` (`0x3044`, API `0x218`)

Writes a single character to the alpha overlay at a given position.

**Stack parameters:**
- `+0x07(SP)`: Row (byte)
- `+0x0B(SP)`: Col (byte)
- `+0x0E(SP)`: Character value (word, includes color bits)
- `+0x12(SP)`: Color/style (word)

#### `calc_alpha_address` (`0x2CE4`, API `0x224`)

Calculates the linear address in alpha RAM for a given row/column.

**Stack parameters:**
- `+0x07(SP)`: Row (byte)
- `+0x0B(SP)`: Col (byte)

**Returns:** D0 = absolute address in alpha RAM (0x905000 + offset).

### 7.3 Alpha Display Management

#### `init_alpha_display` (`0x3522`, API `0x14E`)

Initializes the alpha character overlay. Detects whether a Gauntlet game ROM is present (checks `0x40072` for ROM type flag and `0x40000` for valid JMP). Sets `ram.display_mode` accordingly (1 for Gauntlet scrolling mode, 0 for standard). Clears all of alpha RAM.

#### `write_alpha_word` (`0x3586`, API `0x21E`)

Writes a raw 16-bit value to alpha RAM at a given offset.

**Stack parameters:**
- `+0x04(SP)`: Offset into alpha RAM (long, word index)
- `+0x0A(SP)`: Value to write (word)

### 7.4 Text Scroll/Effect System

The OS supports 4 simultaneous text effect slots (managed in `ram.text_effect_slots` at `0x904F18`). Each slot can run an independent text animation.

#### `init_scroll_system` (`0x3130`, API `0x136`)

Initializes the entire text scroll system. Sets scroll speed, clears scroll positions, then starts the first text effect.

**Stack parameters:**
- `+0x08(SP)`: Text descriptor pointer (address)
- `+0x0E(SP)`: Scroll speed (word, stored at `ram.scroll_speed`)

#### `start_scroll_text` (`0x3162`, API `0x100`)

Starts a type-2 text scroll effect in an available slot.

**Stack parameters:**
- `+0x0C(SP)`: Text descriptor pointer (address)
- `+0x0E(SP)`: Speed/delay (word)
- `+0x12(SP)`: Color attribute (word)

**Returns:** D0 = 1 if started successfully, 0 if no slots available.

#### `start_scroll_type1` (`0x3168`, API `0x12A`), `start_scroll_type3` (`0x316C`, API `0x130`), `start_scroll_type4` (`0x3156`, API `0x11E`)

Same as `start_scroll_text` but with different effect types:
- Type 1: Horizontal scroll right
- Type 2: Vertical scroll (default)
- Type 3: Horizontal scroll left
- Type 4: Instant display (no scroll, then clear after delay)

#### `start_scroll_updown` (`0x3122`, API `0x124`)

Starts a vertical scroll effect. Direction depends on the sign of the speed parameter (positive = down, negative = up).

#### `stop_text_effect` (`0x30F4`, API `0x118`)

Stops and clears a text effect by finding the slot using its descriptor pointer.

#### `process_text_effects` (`0x2B3C`, API `0x148`)

**Called every VBLANK** by the OS VBLANK handler. Processes all 4 text effect slots. Each slot has:
- A type (1-7) determining the animation behavior
- A speed counter (decremented each VBLANK)
- A phase counter for multi-step animations
- A pointer to the text descriptor

The state machine for each slot:
- **Type 1**: Clear the text (erase from screen)
- **Type 2**: Display text character by character (typewriter effect)
- **Type 3**: Scroll text horizontally from one column
- **Type 4**: Scroll text by shifting alpha RAM rows
- **Type 5**: Scroll text by shifting alpha RAM rows (reverse)
- **Type 6**: Reserved
- **Type 7**: Full display mode - scrolls entire screen, re-renders text each frame

### 7.5 Large Character Display System

Used for title screens, attract mode, and score displays. Renders characters using 2x2 or larger tile patterns.

#### `display_large_text` (`0x31D2`, API `0x200`)

Displays a string using large (multi-tile) characters on the alpha overlay.

**Stack parameters:**
- `+0x14(SP)`: Text descriptor with position, string pointer, and chaining info

**Operation:** Iterates through the string, looks up each character in the large character font table (at PC-relative offset `0x34A2`), and renders 2x2 tile blocks for each character. Supports both normal and scrolled display modes.

**Returns:** D0 = total pixel width of rendered text.

#### `display_large_char_raw` (`0x32A0`, API `0x212`)

Renders a single large character tile pattern.

#### `display_large_char_at` (`0x32BC`, API `0x20C`)

Renders a large character at a specified screen position.

### 7.6 VBLANK Synchronization

#### `wait_vblanks` (`0x359A`, API `0x154`)

Waits for a specified number of VBLANK interrupts. Uses `ram.vblank_occurred` (set by the OS VBLANK handler) as a synchronization semaphore.

**Stack parameters:**
- `+0x06(SP)`: Number of VBLANKs to wait (word)

**Operation:**
```c
while (count-- > 0) {
    while (ram.vblank_occurred == old_value) { }  // spin-wait
}
```

### 7.7 Sound System

#### `send_sound_command` (`0x4184`, API `0x172`)

Sends a sound command to the sound processor (Pokey/TMS5220/YM2151).

**Stack parameters:**
- `+0x06(SP)`: Sound command number (word)
- `+0x08(SP)`: Callback pointer for completion (address, 0 = no callback)
- `+0x0E(SP)`: Parameter byte (byte)

**Operation:**
1. Saves SR, sets interrupt level to 5 (masks sound IRQ)
2. Checks if sound I/O is full (bit 5 of `0x803009`)
3. If not full and no pending command: writes command to `0x803170`, stores callback
4. Returns 1 on success, 0 on failure
5. Restores SR

#### `process_sound` (`0x41FA`, API `0x15A`)

Processes the sound queue. Reads the sound status byte and compares with expected sequence number. If they differ, calls `process_coins` to handle coin-sound synchronization.

#### `read_sound_data` (`0x42C8`, API `0x178`)

Reads the next byte from the sound data receive buffer.

**Returns:** D0 = received byte, or 0xFF if buffer empty.

**Operation:** Maintains a circular buffer (15 entries) indexed by read/write pointers at `0x904F91` (read) and `0x904F92` (write). Data bytes are stored at `0x904F98+`.

#### `send_sound_immediate` (`0x427A`, API `0x17E`)

Sends a sound command bypassing the queue.

#### `reset_sound_cpu` (`0x42F8`, API `0x254`)

Resets the sound processor:
1. Clears bit 0 of `0x80312E` (assert reset)
2. Dummy-reads `0x80300E` (clear pending data)
3. Writes interrupt control register
4. Sets bit 0 of `0x80312E` (release reset)
5. Clears sound queue state

### 7.8 Interrupt Control

#### `disable_interrupts` (`0x41C8`, API `0x23C`)

Disables game interrupts by writing 0 to the interrupt control register (`0x803170`). Checks if sound I/O is not full before writing.

#### `enable_interrupts` (`0x41CC`, API `0x242`)

Enables game interrupts by writing a non-zero value to `0x803170`. Same hardware check as disable.

Both functions temporarily raise the interrupt priority to level 5 during the operation.

### 7.9 EEPROM Management

The EEPROM system is sophisticated, with error detection, write verification, and queued writes that happen during VBLANK.

#### `eeprom_init` (`0x44E8`, API `0x190`)

Initializes the EEPROM subsystem:
1. Validates game ROM presence
2. Reads difficulty settings from game ROM (`0x4006F`)
3. Calculates required EEPROM working space size
4. Allocates space from the stack (reduces SP)
5. Stores the allocation pointer at `ram.eeprom_config_ptr` (`0x904FFC`)
6. Falls through to the EEPROM data loading routine

#### `eeprom_process` (`0x432E`, API `0x18A`)

**Called every VBLANK.** Processes the EEPROM write queue one byte at a time:

1. Increments `ram.vblank_counter` (`0x904FF8`)
2. If an EEPROM write is in progress:
   - Compare EEPROM byte with expected value
   - If match: advance to next byte
   - If mismatch after retries: increment `ram.error_count`
3. If no write in progress, check request queue:
   - Dequeue next write request
   - Calculate source data pointer and EEPROM destination
   - Compute checksums (XOR-based, 5 check bytes per block)
   - Begin writing byte-by-byte with unlock sequence
4. If queue empty, check dirty flags:
   - Process any pending EEPROM region writes

**EEPROM Write Sequence:**
```c
saved_sr = SR;
SR |= 0x0700;                // disable all interrupts
WRITE(hw.eeprom_unlock);     // unlock EEPROM
WRITE(eeprom_addr, data);    // write the byte
SR = saved_sr;                // restore interrupts
```

#### `eeprom_check_busy` (`0x4802`, API `0x184`)

Checks if the EEPROM subsystem has any pending operations.

**Returns:** D0 = 1 if busy (operations pending), 0 if idle.

**Checks:** Write request bitmap, queue read/write pointers, and pending EEPROM address.

#### `eeprom_request_write` (`0x47A8`, API `0x196`)

Queues an EEPROM write request by setting a bit in the request bitmap at `ram.eeprom_work` (`0x904FA8`).

**Stack parameters:**
- `+0x04(SP)`: Region index (long, bit position in bitmap)

#### `eeprom_read_block` (`0x4822`, API `0x24E`)

Reads a block of data from EEPROM with verification.

**Stack parameters:**
- `+0x14(SP)`: Destination buffer (address)
- `+0x1A(SP)`: Block index (word)
- `+0x1C(SP)`: Mode (long, 0 = wait for idle first)

### 7.10 Coin/Credit System

#### `process_coins` (`0x35C4`, API `0x16C`)

Processes coin inputs and calculates credits. Called from the sound system when coin sounds are detected.

**Stack parameters:**
- `+0x0B(SP)`: Coin slot byte 1 (byte)
- `+0x0F(SP)`: Coin slot byte 2 (byte)

**Operation:**
1. Reads EEPROM config pointer for coin settings
2. Validates coin multiplier/adder configuration
3. For each of 4 player slots:
   - Reads coin counter increments
   - Applies multiplier and bonus adder
   - Updates per-player coin totals (`ram.coin_totals`)
   - Updates per-player pending credits (`ram.coin_pending`)
   - Processes "coins to start" requirement
   - Issues LED and sound feedback

#### `get_coin_multiplier` (`0x3706`, API `0x236`)

Reads the current coin multiplier from EEPROM configuration.

**Returns:** D0 = multiplier (1-4), or 0 if free play.

#### `calc_health_per_coin` (`0x3740`, API `0x160`)

Calculates the health value awarded per coin based on difficulty settings.

**Stack parameters:**
- `+0x08(SP)`: Player index (long)

**Returns:** D0 = health value per coin (0-24 scaled to game units). Returns 24 (0x18) if in free play mode.

**Operation:** Reads coin counter and pending credit, divides to get health-per-credit ratio, scales by 12/multiplier.

#### `check_and_deduct_coin` (`0x37C2`, API `0x166`)

Checks if a player has enough coins to start/continue and deducts them.

**Stack parameters:**
- `+0x10(SP)`: Player index (long)

**Returns:** D0 = 1 if coins deducted successfully, 0 if insufficient.

**Operation:** Checks if health-per-coin is >= 12 (minimum threshold). If so, deducts one credit's worth of coins from the player's accumulator.

#### `check_credits` (`0x3804`, API `0x230`)

Checks if a player has enough total value (pending + deposited) to meet a threshold.

**Stack parameters:**
- `+0x0C(SP)`: Required amount (long)
- `+0x10(SP)`: Player index (long)

**Returns:** D0 = 1 if sufficient, 0 if not.

### 7.11 Game Configuration (EEPROM Settings)

#### `read_eeprom_setting` (`0x3860`, API `0x1A2`)

Reads a single game setting from the EEPROM configuration tables.

**Stack parameters:**
- `+0x18(SP)`: Setting category (long, 0-7 = difficulty slot)
- `+0x1C(SP)`: Setting index within category (long, 0-19)

**Returns:** D0 = setting value (byte). Returns 0xFE if category out of range, 0xFF if index is 19 (max).

**Operation:** Uses the game ROM's difficulty byte (`0x4006F`) to select the current difficulty level (0-7). Indexes into the EEPROM config area at `eeprom_config_ptr + 0xE6 + (category * 20) + index`.

#### `read_game_config` (`0x38C0`, API `0x1A8`)

Reads a game configuration value with more complex encoding. Supports multi-byte values and different data widths.

**Stack parameters:**
- `+0x1C(SP)`: Config item index (long, 0-13)

**Returns:** D0 = config value (long).

**Special cases:**
- Index 13: Returns difficulty level directly from `0x4006F`
- Index > 13: Returns 0xFF (invalid)

#### `read_high_score_entry` (`0x39B0`, API `0x1AE`)

Reads a high score table entry.

**Stack parameters:**
- `+0x1A(SP)`: Player class (word, 0-3: Warrior/Valkyrie/Wizard/Elf)
- `+0x1E(SP)`: Entry rank (word, 0-9)

**Returns:** D0 = pointer to high score data structure, or 0 if invalid.

The high score structure contains:
- 3-byte score value (24-bit, big-endian)
- 3-byte initials (encoded as base-40 values)

#### `write_high_score_entry` (`0x3A7E`, API `0x1B4`)

Writes a high score entry to the table.

**Stack parameters:**
- `+0x0A(A6)`: Player class (word)
- `+0x0E(A6)`: Entry rank (word)
- `+0x10(A6)`: Pointer to score data structure

**Operation:**
1. Encodes 3-character initials as base-40 (A-Z = 1-26, 0-9 = 27-36, space = 0)
2. Sorts the entry into the correct position in the high score table
3. Shifts existing entries down to make room
4. Queues EEPROM write for the affected region

#### `write_eeprom_setting` (`0x3CF6`, API `0x1C0`)

Writes a game setting value to EEPROM.

#### `read_eeprom_config` (`0x3F68`, API `0x1C6`)

Reads an EEPROM configuration block.

#### `write_eeprom_config` (`0x401A`, API `0x1CC`)

Writes an EEPROM configuration block.

#### `get_eeprom_base` (`0x3BE8`, API `0x1BA`)

Returns the base pointer for a given EEPROM data section.

### 7.12 Statistics

#### `process_coin_stats` (`0x4038`, API `0x19C`)

Processes coin statistics and updates histogram data in EEPROM. Tracks per-player coin counts and time-per-coin metrics.

**Stack parameters:**
- `+0x1A(SP)`: Player index (word)
- `+0x1E(SP)`: Stat value (word, max 128)

### 7.13 Self-Test / Diagnostics

#### `run_self_test` (`0x5454`, API `0x1D2`)

Entry point for the diagnostic/self-test suite. Calls several sub-functions:
1. `0x4C38` - Initialize self-test display
2. `0x5098` - Run diagnostic tests
3. `0x4C66` - Cleanup/finalize

The self-test menu includes (based on strings found in ROM):
- **Switch Test**: Tests all player input switches with live display
- **Playfield Test**: Tests playfield RAM and display with bank selection
- **Alpha Test**: Tests alphanumeric overlay
- **Color Test**: Tests color RAM with named colors (White, Red, Green, Blue, Grey, Violet)
- **Convergence Test**: Displays convergence pattern
- **Motion Object Test**: Tests sprite system (Object, Picture, Horizontal, Vertical, Size, Color Palette)
- **Sound Test**: Full sound system diagnostics:
  - Tests sound CPU communication (3-second timeout)
  - Reports: Sound CPU Not Responding, Speech/Music Chip Timeout, Interrupt Error, RAM errors, ROM errors
  - Interactive sound selection (Move to select, Press to hear)
  - Music Chip Test, Effects Chip Test, Speech Chip Test
- **Statistics Display**: Shows coin/play statistics per player, histograms
- **Configuration**: Game Options, Coin Options (with DIP switch display)

#### `display_attract_screen` (`0x58C6`, API `0x248`)

Displays an attract mode or configuration screen. Sets up display headers from OS ROM data tables and delegates to either the default attract sequence or a custom display routine.

**Stack parameters:**
- `+0x08(SP)`: Mode (long, 0 = default attract, non-zero = custom)

**Operation:**
1. Calls `init_alpha_display` to clear screen
2. Calls `0x4C38` to initialize display
3. Selects screen header text descriptor based on ROM type flag (`0x40072`): Gauntlet uses `0x6CFE`, non-Gauntlet uses `0x6C78` (both contain OS ROM-internal strings like `"Game Options"`)
4. Displays header text via `display_text`
5. If mode == 0: calls `0x522A` (default attract sequence)
6. If mode != 0: reads screen config via `read_game_config(12)`, calls `0x5476` (custom display)
7. Calls `write_eeprom_setting` to save state

---

## 8. RAM Variable Map

### 8.1 Video RAM Spare - OS Working Area (`0x904000-0x904FFF`)

| Address | Size | Name | Description |
|---------|------|------|-------------|
| `0x904000` | word | `os_flag` | General OS state flag (cleared during init) |
| `0x904004` | word | `vblank_occurred` | Set to 1 each VBLANK by OS handler; used as sync semaphore |
| `0x904006` | word | `pf_vscroll_hi` | Playfield vertical scroll high bits (shadow) |
| `0x904008` | word | `pf_hscroll` | Playfield horizontal scroll value (shadow) |
| `0x90400A` | word | `pf_vscroll_lo` | Playfield vertical scroll low bits (shadow) |
| `0x90400C` | word | `timer_countdown` | Countdown timer (decremented each VBLANK) |
| `0x90400E` | word | `sound_data_recv` | Last byte received from sound CPU |
| `0x904010` | word | `sound_data_flag` | Cleared when sound data received (0 = data ready) |
| `0x904014` | word | `game_hook_flag` | 0 = game ROM hooks active; 1 = OS-only mode |
| `0x904F00` | long | `scroll_base` | Base value for scroll system |
| `0x904F02` | word | `scroll_speed` | Text scroll speed setting |
| `0x904F04` | word | `vblank_sync` | VBLANK synchronization counter |
| `0x904F06` | word | `scroll_direction` | Current scroll direction/offset |
| `0x904F08` | word | `scroll_counter` | Scroll frame counter |
| `0x904F0A` | word | `scroll_limit` | Scroll limit value |
| `0x904F0C` | word | `os_vblank_active` | 1 = OS handles VBLANK; 0 = game handles VBLANK |
| `0x904F0E` | word | `display_mode` | 0 = standard alpha; 1 = Gauntlet scrolling mode |
| `0x904F10` | 2w | `text_color` | Per-slot text color attributes |
| `0x904F18` | 4B | `text_effect_type` | Per-slot effect type (0=inactive, 1-7=active types) |
| `0x904F1C` | 8B | `text_effect_speed` | Per-slot speed/delay values (2 words) |
| `0x904F24` | 8B | `text_effect_counter` | Per-slot frame counters (2 words) |
| `0x904F2C` | 4B | `text_effect_phase` | Per-slot animation phase |
| `0x904F30` | 4B | `text_effect_step` | Per-slot step counter |
| `0x904F34` | 16B | `text_effect_desc` | Per-slot text descriptor pointers (4 longs) |
| `0x904F44` | long | `highscore_work_ptr` | Working pointer for high score operations |
| `0x904F8A` | long | `player_inputs_snapshot` | All 4 players' input state (snapshot from VBLANK) |
| `0x904F8E` | struct | `sound_queue` | Sound command queue structure |
| `0x904FA8` | struct | `eeprom_work` | EEPROM write request bitmap and work area |
| `0x904FC0` | byte | `error_count` | Cumulative EEPROM error count |
| `0x904FEC` | 4B | `coin_counters` | Per-player coin counter accumulators |
| `0x904FF0` | 4B | `coin_totals` | Per-player total coins deposited |
| `0x904FF4` | 4B | `coin_pending` | Per-player pending coin credits |
| `0x904FF8` | long | `vblank_counter` | Monotonic VBLANK counter (incremented each frame) |
| `0x904FFA` | byte | `eeprom_dirty_flag` | Non-zero if EEPROM needs flushing |
| `0x904FFC` | long | `eeprom_config_ptr` | Pointer to EEPROM configuration working area (allocated from stack) |

### 8.2 Game ROM Hook Vector Table (`0x40000-0x400FF`)

| Address | Size | Name | Description |
|---------|------|------|-------------|
| `0x40000` | 6B | `game_start` | JMP to game entry point (must be `0x4EF9` + address) |
| `0x40006` | 6B | `game_vblank` | JMP to game VBLANK handler |
| `0x4000C` | 6B | `game_irq1` | JMP to game IRQ1 handler |
| `0x40012` | 6B | `game_irq3` | JMP to game IRQ3 handler |
| `0x40018` | 6B | `game_irq2` | JMP to game IRQ2 handler |
| `0x4001E` | 6B | `game_irq6` | JMP to game IRQ6 handler |
| `0x40024` | 6B | `game_exception` | JMP to game exception handler |
| `0x4002A` | 6B | `game_startup_hook2` | Optional JMP to game startup hook, called after coin/text display init (`0x17D4`). Referenced at `0x143E`. Unused in Gauntlet (zeros). |
| `0x40030` | 6B | `game_pf_init` | JMP to playfield initialization |
| `0x40036` | 6B | `game_startup_hook1` | Optional JMP to game startup hook, called after attract display init (`0x1B20`). Referenced at `0x1426`. Unused in Gauntlet (zeros). |
| `0x4003C` | 6B | `game_startup_hook3` | Optional JMP to game startup hook, called after color palette init (`0x0FCA`). Referenced at `0x1456`. Unused in Gauntlet (zeros). |
| `0x40042` | 6B | `game_vblank_hook` | JMP to supplemental VBLANK handler (input reading) |
| `0x40048` | 6B | `game_attract` | JMP to game attract mode handler |
| `0x4004E` | 6B | `game_post_attract_hook` | Optional JMP to game post-attract handler (fallback: `run_self_test(1)`). Not present in all ROM versions (may be 0x00). |
| `0x40054` | 6B | `game_eeprom_config` | Optional JMP to EEPROM configuration provider. Returns a 32-bit value in D0: bit 16 = EEPROM layout flag, bits 8-15 = high config byte, bits 0-7 = low config byte. Fallback: `0x10000`. Referenced at `0x21AC`. In Gauntlet: JMP `0x56EAA`. |
| `0x40060` | 2B | `game_mob_fill_value` | Data word (not a JMP hook). Default fill value for motion object RAM during display init (`0x1632`). In Gauntlet: `0x0000`. Only used when `ram.game_hook_flag` (`0x904014`) is 0. |
| `0x40062` | 2B | `game_pf_fill_value` | Data word. Playfield RAM fill value used during game startup at `0x154C` (fills 0x1000 words at `0x900000`). In Gauntlet: `0x0010` (background tile). |
| `0x4006D` | 1B | `game_eeprom_start` | EEPROM game-section start index. OS uses `0x22 - value` as the boundary between shared and game-specific EEPROM entries. In Gauntlet: `0x01`. Referenced at `0x3E6E`, `0x45A4`. |
| `0x4006F` | 1B | `game_difficulty` | Difficulty/config byte (masked to 0-7 via `AND #7`). In Gauntlet: `0x2C` (effective difficulty 4). |
| `0x40070` | 2B | `game_screen_mode` | Screen mode word. Referenced at `0x4748` and `0x5908`. In Gauntlet: `0xE090`. |
| `0x40072` | 1B | `game_rom_type` | ROM type flag (non-zero = Gauntlet scrolling mode). Referenced 18 times in OS. In this Gauntlet ROM: `0x00` (standard mode - game handles its own scrolling). |
| `0x40074` | 4B | `game_button0_label_ptr` | Pointer to button 0 label string for self-test (e.g., `"WARRIOR <MAGIC> button"`). OS fallback: `"BUTTON 0"` |
| `0x40078` | 4B | `game_button1_label_ptr` | Pointer to button 1 label string for self-test (e.g., `"WARRIOR <FIRE> button"`). OS fallback: `"BUTTON 1"` |
| `0x4007C` | 4B | `game_joystick_label_ptr` | Pointer to joystick label string for self-test. OS fallback: `"JOYSTICK"` |
| `0x40080` | var | `game_checksum_tbl` | ROM checksum validation table |

---

## 9. Game-Related Strings

The ROM contains extensive game text (found in the data section):

### 9.1 Error Messages
- `"Working RAM error"`
- `"COLOR      RAM error at:"`
- `"PLAYFIELD  RAM error at:"`
- `"ALPHA      RAM error at:"`
- `"MOTION OBJ RAM error at:"`
- `"GAME       RAM error at:"`
- `"Main ROM error"`
- `"Game board RAM error"`
- `"NO GAME PROGRAM"`
- `"ROM at XXXXX error"` (for addresses 10000-88000)
- `"EEPROM ERROR"`

### 9.2 Self-Test Screens
- `"Switch Test"`, `"Playfield Test"`, `"Alpha Test"`, `"Color Test"`
- `"Convergence Test"`, `"Motion Object Test"`, `"Sound Test"`
- `"Statistics"`, `"Game Options"`, `"Coin Options"`

### 9.3 Sound Test Messages
- `"Testing Sound CPU"`, `"Wait 3 Seconds"`
- `"Sound Processor Not Responding"`
- `"Speech Chip Time Out"`, `"Music Chip Time Out"`
- `"Sound CPU Interrupt Error"`, `"Sound CPU RAM 1/2 Error"`, `"Sound CPU ROM 1/2/3 Error"`
- `"Sound CPU Status  : Good"`, `"Sound # :"`, `"Number of Sounds  :"`

### 9.4 Game Messages
- `"PRESS START"`, `"ADD   COIN"`, `"ADD   COINS"`, `"INSERT COIN"`
- `"GAME OVER"`, `"COIN MIN."`, `"TIME:"`
- `"PRESS START WITHIN 20 SECONDS TO CONTINUE GAME AT THIS LEVEL"`
- `"ATARI GAMES"`, `"@1985"`
- `"TREASURE ROOM"`, `"YOU HAVE    SECONDS TO COLLECT TREASURES"`
- `"YOU MUST EXIT TO RECEIVE BONUS POINTS"`

### 9.5 Configuration Options
- `"Game Difficulty"`: `"0 - Easiest"` through `"7 - Hardest"`
- `"Health Per Coin"`: `"1000"` through `"2000"` (in 100 increments)
- `"Coins to Start"`: `"1234"`
- `"Multiplier:"`, `"Bonus Adder:"`: Various options including `"Free Play"`
- `"Sounds in Attract Mode?"`, `"Disable Speech?"`, `"Reduce Text?"`
- `"Automatic Reset of High Score Tables?"`, `"Restore Factory Default Settings?"`
- `"Reset High Score Tables?"`

### 9.6 Gameplay Hints
- `"FIND THE HIDDEN POTION"`, `"STUN OTHER PLAYERS"`
- `"GHOSTS MUST BE SHOT"`, `"SOME FOOD CAN BE DESTROYED"`
- `"FIGHT HAND TO HAND BY RUNNING INTO GRUNTS"`
- `"BEWARE THE DEMONS WHICH SHOOT YOU"`
- `"SORCERERS MAY BE INVISIBLE"`, `"USE MAGIC TO KILL DEATH"`
- `"HOLD FIRE BUTTON TO SHOOT"`, `"RELEASE FIRE BUTTON TO MOVE"`
- `"GAME OVER WHEN HEALTH = 0"`

### 9.7 Legend/Stats
- `"WARRIOR:"`, `"VALKYRIE:"`, `"WIZARD:"`, `"ELF:"`
- `"FOOD:  HEALTH INCREASED BY 100"`
- `"SCORE PER COIN"`, `"WARRIORS"`, `"VALKYRIES"`, `"WIZARDS"`, `"ELVES"`
- `"INSERT COINS FOR MORE HEALTH"`

### 9.8 High Score
- `"Enter your initials:"`
- Player name data: HAL, KEN, BOB, MEA, CAD, ED, GEL, SMO, CJ (developer initials)

---

## 10. ROM Internal Structure

### 10.1 Code Regions

| Address Range | Size | Description |
|---------------|------|-------------|
| `0x0000-0x00FF` | 256 B | M68010 vector table |
| `0x0100-0x01D7` | 216 B | OS API jump table (36 JMP entries) |
| `0x01D8-0x01F7` | 32 B | Data address table |
| `0x01F8-0x01FF` | 8 B | Padding (zeros) |
| `0x0200-0x027F` | 128 B | OS API jump table continued (20 JMP entries + 1 unused slot at `0x22A`) |
| `0x0280-0x02FF` | 128 B | Additional data/padding |
| `0x0300-0x039F` | 160 B | Interrupt/exception handlers |
| `0x03A0-0x05E1` | 578 B | Normal boot RAM tests |
| `0x05E2-0x061D` | 60 B | Reset entry point |
| `0x061E-0x070B` | 238 B | Self-test boot RAM tests |
| `0x070C-0x0A2B` | 800 B | Main init, ROM checksum, game ROM validation |
| `0x0A2C-0x0C51` | 550 B | Memory test subroutines |
| `0x0C52-0x0E13` | 450 B | Error display, ROM checksum display, game ROM test helpers |
| `0x0E14-0x0EEC` | 217 B | OS VBLANK system |
| `0x0EEE-0x1299` | ~1 KB | Display helpers, playfield manipulation |
| `0x129A-0x1631` | ~900 B | OS main loop, self-test dispatch, attract mode logic |
| `0x1632-0x21FF` | ~3 KB | Self-test mode screens and menus |
| `0x2200-0x28FF` | ~1.8 KB | EEPROM validation, statistics display, config menus |
| `0x2918-0x2E35` | ~1.3 KB | Number formatting, text effect processing |
| `0x2E36-0x3521` | ~1.8 KB | Text display, string drawing, alpha RAM functions |
| `0x3522-0x35C3` | 162 B | Alpha display init, wait_vblanks, set_text_position |
| `0x35C4-0x3805` | ~580 B | Coin/credit system |
| `0x3806-0x4183` | ~2.4 KB | EEPROM settings, game config, high scores |
| `0x4184-0x42F7` | 372 B | Sound system, interrupt control |
| `0x42F8-0x4821` | ~1.3 KB | Sound reset, EEPROM process, EEPROM init |
| `0x4822-0x5453` | ~3.1 KB | EEPROM read/write, coin stats, config options |
| `0x5454-0x599F` | ~1.4 KB | Self-test diagnostics, attract screen |
| `0x59A0-0x6623` | ~3.2 KB | Data tables, lookup tables |
| `0x6624-0x6FFF` | ~2.5 KB | String data, font data, configuration tables |

### 10.2 Function Count Summary

| Category | Count |
|----------|-------|
| Interrupt/Exception Handlers | 6 |
| Boot/Init Functions | 7 |
| OS VBLANK System | 2 |
| Number Formatting | 3 |
| Text Display | 6 |
| Alpha Display Management | 2 |
| Text Scroll/Effects | 8 |
| Large Character Display | 6 |
| Timing | 1 |
| Sound System | 5 |
| Interrupt Control | 2 |
| EEPROM Management | 5 |
| Coin/Credit System | 5 |
| Game Config/Settings | 8 |
| Self-Test/Diagnostics | 2 |
| **Total Named Functions** | **68** |

---

## 11. Loading the radare2 Annotations

To load the analysis into radare2:

```bash
r2 -i gauntlet_os.r2 row9.bin
```

This will:
1. Set M68K/68010 architecture
2. Create all named functions at their correct addresses
3. Add hardware and RAM variable flags
4. Add comments at key locations

---

## 12. Key Architectural Insights

### 12.1 OS/Game Separation Pattern

The Gauntlet OS ROM implements a clean separation between OS services and game code through:

1. **Fixed API entry points** (jump table at 0x100) - game code never calls OS internals directly
2. **Hook-based interrupt dispatch** - each IRQ handler checks for a `JMP` instruction at the corresponding game ROM vector before dispatching
3. **VBLANK ownership flag** (`ram.os_vblank_active`) - cleanly switches between OS-managed and game-managed VBLANK handling
4. **Callback-based design** - the OS main loop calls game hooks through vectors at 0x40042 (VBLANK input hook), 0x40048 (attract mode), and optionally 0x4004E (post-attract). Self-test mode uses control label strings from 0x40074/0x40078/0x4007C to display game-specific button names.

### 12.2 Memory Test Pattern

The ROM uses an unusual "continuation address in A4" pattern for memory tests. Instead of returning via `RTS`, the test routines jump to `(A4)` which the caller pre-loads with the continuation address. This is effectively a simple form of continuation-passing style, avoiding the need for a working stack during early boot when RAM hasn't been validated yet.

### 12.3 EEPROM Reliability

The EEPROM system includes extensive error handling:
- XOR-based checksums (5 check bytes per block)
- Write verification with retry (4 retries per byte)
- Error counter that persists across writes
- Queue-based writes (one byte per VBLANK to avoid blocking)
- Hardware unlock sequence required for each write

### 12.4 Display Modes

The alpha overlay supports two modes:
- **Standard mode** (`display_mode = 0`): 42 columns x 30 rows, 2 bytes per character, sequential addressing
- **Gauntlet scrolling mode** (`display_mode = 1`): 42 columns x 30 rows but with column-major addressing (128 bytes per column), supporting smooth horizontal scrolling of the text overlay

### 12.5 Watchdog Pattern

Throughout the boot sequence, the watchdog is petted frequently. The pattern `move.w d0, hw.watchdog` appears hundreds of times. During long operations (memory tests, ROM checksum), the watchdog is petted inside inner loops. During error display, the code waits for VBLANK toggles while petting the watchdog, creating a "wait for operator" pattern:

```
loop:
    pet watchdog
    wait for VBLANK=1
    pet watchdog
    wait for VBLANK=0
    pet watchdog
    wait for VBLANK=1
    check button
    branch loop if not pressed
```
