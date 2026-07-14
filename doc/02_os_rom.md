# Gauntlet II — OS ROM Analysis (row9.bin)

*Comprehensive reverse engineering analysis of the 64 KB OS ROM mapped at `0x000000–0x00FFFF`.*

---

## 1. Overview

**Confidence: Verified** for vector values, ROM size, initial state, and the
service categories directly exercised by the game ROM.

The OS ROM provides:
- Complete hardware bootstrap (memory tests, ROM checksum validation)
- Diagnostic/self-test mode
- OS services via a fixed API jump table (interrupt dispatch, video, input, EEPROM, sound, coin handling)
- Game-related code (attract mode infrastructure, high scores, configuration)

**Key Facts:**
- CPU: Motorola 68010
- ROM size: 65,536 bytes
- Initial SSP: `0x00904F00` (Video RAM Spare area)
- Initial PC: `0x000005E2` (`reset_entry`)
- Game ROM at: `0x040000–0x07FFFF`

---

## 2. M68010 Vector Table (`0x000000–0x0000FF`)

**Confidence: Verified** by byte-exact vector decoding.

| Offset | Vector | Value | Target |
|--------|--------|-------|--------|
| `0x000` | Initial SSP | `0x00904F00` | Stack in Video RAM Spare |
| `0x004` | Initial PC | `0x000005E2` | `reset_entry` |
| `0x008` | Bus Error | `0x00000300` | `exception_handler` |
| `0x00C` | Address Error | `0x00000300` | `exception_handler` |
| `0x010` | Illegal Instruction | `0x00000300` | `exception_handler` |
| `0x014` | Divide by Zero | `0x00000300` | `exception_handler` |
| `...` | (Other exceptions) | `0x00000300` | `exception_handler` |
| `0x064` | Autovector Level 1 | `0x00000314` | `irq1_handler` |
| `0x068` | Autovector Level 2 | `0x00000326` | `irq2_handler` |
| `0x06C` | Autovector Level 3 | `0x00000338` | `irq3_handler` |
| `0x070` | Autovector Level 4 | `0x0000034A` | `irq4_vblank_handler` |
| `0x078` | Autovector Level 6 | `0x0000036C` | `irq6_handler` |

---

## 3. OS API Jump Table

**Confidence: Verified** for every entry address and JMP destination.
Function names/categories are **Strong inference** from implementation and
game callers except where a detailed contract below is explicitly Verified.

The jump table at `0x100` is the OS API entry point. It consists of `JMP <absolute>.l` instructions (6 bytes each). Game code calls through these fixed addresses to access OS services, allowing the OS implementation to be relocated without changing the game ROM.

### 3.1 Jump Table Entries (`0x100–0x1D7`)

| Address | Target | Function Name | Category |
|---------|--------|---------------|----------|
| `0x100` | `0x3162` | `start_scroll_text` | Text Effects |
| `0x106` | `0x2ABE` | `format_decimal` | Number Formatting |
| `0x10C` | `0x2A5E` | `format_hex` | Number Formatting |
| `0x112` | `0x2918` | `format_number` | Number Formatting |
| `0x118` | `0x30F4` | `stop_text_effect` | Text Effects |
| `0x11E` | `0x3156` | `start_scroll_type4` | Text Effects |
| `0x124` | `0x3122` | `start_scroll_updown` | Text Effects |
| `0x12A` | `0x3168` | `start_scroll_type1` | Text Effects |
| `0x130` | `0x316C` | `start_scroll_type3` | Text Effects |
| `0x136` | `0x3130` | `init_scroll_system` | Text Effects |
| `0x13C` | `0x35B2` | `set_text_position` | Text Display |
| `0x142` | `0x2E36` | `display_text` | Text Display |
| `0x148` | `0x2B3C` | `process_text_effects` | Text Effects |
| `0x14E` | `0x3522` | `init_alpha_display` | Alpha Display |
| `0x154` | `0x359A` | `wait_vblanks` | Timing |
| `0x15A` | `0x41FA` | `process_sound` | Sound |
| `0x160` | `0x3740` | `calc_health_per_coin` | Coin/Credit |
| `0x166` | `0x37C2` | `check_and_deduct_coin` | Coin/Credit |
| `0x16C` | `0x35C4` | `process_coins` | Coin/Credit |
| `0x172` | `0x4184` | `send_sound_command` | Sound |
| `0x178` | `0x42C8` | `read_sound_data` | Sound |
| `0x17E` | `0x427A` | `send_sound_immediate` | Sound |
| `0x184` | `0x4802` | `eeprom_check_busy` | EEPROM |
| `0x18A` | `0x432E` | `eeprom_process` | EEPROM |
| `0x190` | `0x44E8` | `eeprom_init` | EEPROM |
| `0x196` | `0x47A8` | `eeprom_request_write` | EEPROM |
| `0x19C` | `0x4038` | `process_coin_stats` | Statistics |
| `0x1A2` | `0x3860` | `read_eeprom_setting` | Config |
| `0x1A8` | `0x38C0` | `read_game_config` | Config |
| `0x1AE` | `0x39B0` | `read_high_score_entry` | High Scores |
| `0x1B4` | `0x3A7E` | `write_high_score_entry` | High Scores |
| `0x1BA` | `0x3BE8` | `get_eeprom_base` | EEPROM |
| `0x1C0` | `0x3CF6` | `write_eeprom_setting` | Config |
| `0x1C6` | `0x3F68` | `rank_high_score` | High Scores |
| `0x1CC` | `0x401A` | `write_eeprom_config` | Config |
| `0x1D2` | `0x5454` | `run_self_test` | Diagnostics |

### 3.2 Data Address Table (`0x1D8–0x1F7`)

| Offset | Value | Points To |
|--------|-------|-----------|
| `0x1D8` | `0x00904006` | `ram.pf_vscroll_hi` |
| `0x1DC` | `0x00904008` | `ram.pf_hscroll` |
| `0x1E0` | `0x00904F8A` | `ram.player_inputs_snapshot` |
| `0x1E4` | `0x00904004` | `ram.vblank_occurred` |
| `0x1E8` | `0x0090400C` | `ram.timer_countdown` |
| `0x1EC` | `0x0080300E` | `hw.sound_read` |
| `0x1F0` | `0x00803170` | `hw.sound_command_word` |
| `0x1F4` | `0x0090400A` | `ram.pf_vscroll_lo` |

### 3.3 Jump Table Entries (`0x200–0x278`)

| Address | Target | Function Name | Category |
|---------|--------|---------------|----------|
| `0x200` | `0x31D2` | `display_large_text` | Large Characters |
| `0x206` | `0x3346` | `display_large_char_styled` | Large Characters |
| `0x20C` | `0x32BC` | `display_large_char_at` | Large Characters |
| `0x212` | `0x32A0` | `display_large_char_raw` | Large Characters |
| `0x218` | `0x3044` | `write_alpha_char` | Alpha Display |
| `0x21E` | `0x3586` | `write_alpha_word` | Alpha Display |
| `0x224` | `0x2CE4` | `calc_alpha_address` | Alpha Display |
| `0x230` | `0x3804` | `check_credits` | Coin/Credit |
| `0x236` | `0x3706` | `get_coin_multiplier` | Coin/Credit |
| `0x23C` | `0x41C8` | `send_sound_command_wait` | Sound |
| `0x242` | `0x41CC` | `try_send_sound_command` | Sound |
| `0x248` | `0x58C6` | `display_attract_screen` | Game Display |
| `0x24E` | `0x4822` | `eeprom_read_block` | EEPROM |
| `0x254` | `0x42F8` | `reset_sound_cpu` | Sound |
| `0x25A` | `0x2F04` | `draw_string` | Text Display |
| `0x260` | `0x2EB4` | `display_decimal_value` | Text Display |
| `0x266` | `0x2EEA` | `display_hex_value` | Text Display |
| `0x26C` | `0x332A` | `large_char_lookup` | Large Characters |
| `0x272` | `0x32DA` | `large_char_data` | Large Characters |
| `0x278` | `0x3310` | `large_char_render` | Large Characters |

---

## 4. Game ROM Header and Hook Tables (`0x40000–0x4013F`)

**Confidence: Verified** for bytes, ranges, OS consumers, and active JMP
targets. Rows explicitly described as unreferenced remain **Unknown** in
original build-time purpose and are unresolvable from the supplied runtime
artifacts; their bytes, boundaries, and lack of runtime consumers are
Verified, and no meaning is inferred from their values.

| Address | Size | Name | Description |
|---------|------|------|-------------|
| `0x40000` | 6 B | `game_start_veneer` | JMP to game entry point (must be `0x4EF9` + address) |
| `0x40006` | 6 B | `game_vblank_veneer` | JMP to game VBLANK handler |
| `0x4000C` | 6 B | `game_irq1_watchdog_trap` | Self-JMP trap; leaves the watchdog unserviced |
| `0x40012` | 6 B | `game_irq3_watchdog_trap` | Self-JMP trap; leaves the watchdog unserviced |
| `0x40018` | 6 B | `game_irq2_watchdog_trap` | Self-JMP trap; leaves the watchdog unserviced |
| `0x4001E` | 6 B | `game_irq6_sound_veneer` | JMP through OS API 0x17E to the sound receive IRQ body |
| `0x40024` | 6 B | `game_exception_veneer` | JMP to `game_exception_abort` at 0x40140 |
| `0x4002A` | 6 B | `game_startup_hook2_slot` | Optional post coin/text-display initialization hook tested by the OS. All six bytes are zero in Gauntlet II, so the OS skips it. |
| `0x40030` | 6 B | `game_playfield_init_veneer` | Optional game playfield-initialization hook. `os_main_loop` verifies the slot begins with JMP, then calls it indirectly through A0; Gauntlet II targets 0x44A82. If absent, the OS clears 0x1000 playfield words itself. |
| `0x40036` | 6 B | `game_startup_hook1_slot` | Optional post-attract-display initialization hook; zero-filled and therefore skipped in Gauntlet II. |
| `0x4003C` | 6 B | `game_startup_hook3_slot` | Optional post-palette initialization hook; zero-filled and therefore skipped in Gauntlet II. |
| `0x40042` | 6 B | `game_vblank_hook_slot` | Optional supplemental VBLANK hook. The OS calls it only when its first word is JMP opcode 0x4EF9; Gauntlet II ships six zero bytes here, so input remains handled by the ordinary OS/game VBL paths. |
| `0x40048` | 6 B | `game_options_veneer` | JMP to the game-specific options/configuration display at 0x5317C; the former `game_attract` name was **Contradicted** by the target body and descriptor strings. |
| `0x4004E` | 6 B | `game_post_attract_hook_slot` | Optional post-attract hook tested by the OS; zero-filled and skipped in Gauntlet II. |
| `0x40054` | 6 B | `game_eeprom_config_veneer` | Optional JMP to EEPROM configuration provider. Returns D0: bit 16 = EEPROM layout flag, bits 8-15 = high config byte, bits 0-7 = low config byte. In Gauntlet: JMP `0x56EAA`. |
| `0x4005A` | 6 B | `game_header_ff_pad_4005a` | Solid 0xFF padding between the final hook and scalar header values. |
| `0x40060` | 2 B | `game_mob_fill_value` | Default fill value for MOB RAM during display init. In Gauntlet: `0x0000`. |
| `0x40062` | 2 B | `game_pf_fill_value` | Playfield RAM fill value during startup. In Gauntlet: `0x0010` (background tile). |
| `0x40064` | 9 B | `game_reserved_header_40064` | Bytes `00 01 00 02 00 03 00 00 00`; no OS/game runtime consumer found. |
| `0x4006D` | 1 B | `game_eeprom_start` | EEPROM game-section start index. In Gauntlet: `0x01`. |
| `0x4006E` | 1 B | `game_reserved_header_4006e` | Zero reserved byte; no runtime consumer found. |
| `0x4006F` | 1 B | `game_difficulty` | Difficulty/config byte (masked to 0-7). In Gauntlet: `0x2C` (effective difficulty 4). |
| `0x40070` | 2 B | `game_screen_mode` | Screen mode word. In Gauntlet: `0xE090`. |
| `0x40072` | 1 B | `game_rom_type` | ROM type flag (non-zero = Gauntlet scrolling mode). In Gauntlet: `0x00`. |
| `0x40073` | 1 B | `game_reserved_header_40073` | Value 1; no runtime consumer found. |
| `0x40074` | 4 B | `game_button0_label_ptr` | Pointer to button 0 label string for self-test. |
| `0x40078` | 4 B | `game_button1_label_ptr` | Pointer to button 1 label string for self-test. |
| `0x4007C` | 4 B | `game_joystick_label_ptr` | Pointer to joystick label string for self-test. |
| `0x40080` | 24 B | `game_checksum_tbl` | One 16-byte descriptor `{start=0x40000, end=0x5FFFF, chunk_count=0x8000, enabled=1}`, followed by the 8-byte zero terminator. The OS reads start/end first and stops when the terminator's end is zero. |
| `0x40098` | 16 B | `game_unreferenced_header_words` | Four unreferenced longwords; not consumed by either checksum-parser path. No runtime meaning assigned. |
| `0x400A8` | 54 B | `game_header_ff_pad` | 0xFF fill ending at 0x400DD. |
| `0x400DE` | 6 B | `scroll_to_slot_veneer` | JMP to `scroll_to_slot` (0x46C5E). |
| `0x400E4` | 6 B | `init_display_veneer` | JMP to `init_display` (0x43486). |
| `0x400EA` | 6 B | `maze_setup_veneer` | JMP to `maze_setupnew` (0x44AC2). |
| `0x400F0` | 6 B | `pf_replace_veneer` | JMP to `pf_replace` (0x5F31E). |
| `0x400F6` | 6 B | `mob_clear_veneer` | JMP to `moblist_remove_and_clear` (0x5DDDA). |
| `0x400FC` | 6 B | `game_unreferenced_ram_value_pair` | Longword 0x00904894 followed by word 0x872E. No static OS/game consumer; retained as an unassigned header constant pair. |
| `0x40102` | 17 B | `game_joystick_label` | NUL-terminated “WARRIOR joystick”. |
| `0x40113` | 22 B | `game_fire_label` | NUL-terminated “WARRIOR <FIRE> button”. |
| `0x40129` | 23 B | `game_magic_label` | NUL-terminated “WARRIOR <MAGIC> button”; ends at 0x4013F immediately before game code. |

---

## 5. Boot Sequence

**Confidence: Verified** for control flow, hardware writes, test ranges, and
checksum comparisons. Higher-level intent labels such as “enable board” are
**Strong inference** from the write sequence and hardware reference.

### 5.1 Reset Entry (`0x5E2`)

The 68010 loads SSP from `0x000000` (= `0x904F00`) and PC from `0x000004` (= `0x5E2`).

```
1. Set SR = 0x2700 (supervisor mode, all interrupts masked)
2. Write 0x0001 to hardware latch (0x803120) — enable board
3. Write 0x0000 to hardware latch — reset pulse
4. Delay loop (0xFA0 iterations) petting watchdog
5. Write 0x0001 to hardware latch — re-enable
6. Read self-test switch (bit 3 of 0x803009)
7. If self-test: JMP selftest_boot (0x61E)
8. Otherwise:    JMP normal_boot (0x3A0)
```

### 5.2 Normal Boot (`0x3A0`)

Performs a quick memory test on each video RAM region. Uses `mem_test_quick` (0xA6A) with multiple walking-bit patterns. Test order:

```
1. Test Video RAM Spare     (0x904000–0x904FFE) → error: continue anyway
2. Test Color RAM           (0x910000–0x9107FE) → error: display "COLOR RAM error"
3. Test Playfield RAM       (0x900000–0x901FFE) → error: display "PLAYFIELD RAM error"
4. Test Alpha RAM           (0x905000–0x905FFE) → error: display "ALPHA RAM error"
5. Test MOB RAM             (0x902000–0x903FFE) → error: display "MOTION OBJ RAM error"
6. On success: JMP main_init_cont (0x70C)
```

### 5.3 Self-Test Boot (`0x61E`)

Same tests as normal boot but uses `mem_test_thorough` (0xA2C). Also initializes Color RAM with an incrementing pattern first.

### 5.4 Main Init Continuation (`0x70C`)

```
1.  Clear d5 (error flag)
2.  Clear ram.os_flag (0x904000)
3.  Clear all Color RAM (0x910000–0x9107FE); set colors 1–3 to 0xF00F (white)
4.  Enable hardware latch
5.  Reset stack to 0x904F00
6.  Call init_alpha_display (0x3522) — clears alpha overlay
7.  ROM Checksum:
    - Two byte accumulators: d0 init=0, d1 init=1
    - Loop 0x8000 times, adding even-addressed bytes to d0, odd to d1
    - Both must equal 0xFF (even bytes sum to 0xFF, odd bytes sum to 0xFE)
    - On failure: call rom_checksum_display (0xCC0)
    - In self-test mode: continue regardless
8.  Check for valid game ROM:
    - 0x40000 must contain JMP instruction (0x4EF9)
    - Target address must be in range 0x40000–0x7FFFF
    - If invalid: display "NO GAME PROGRAM" and wait
9.  If valid game ROM: validate checksums from table at 0x40080
10. Validate EEPROM
11. Clear Video RAM Spare (0x904000–0x904FFB, 4092 bytes)
12. Call eeprom_init (0x44E8)
13. Dispatch:
    - Self-test + no errors: JMP game ROM start (0x40000)
    - Self-test + errors: JMP os_vblank_mode_entry → self-test
    - Normal mode: JMP os_vblank_mode_entry → game attract
```

> **Architectural note:** The OS ROM uses an unusual "continuation address in A4" pattern for memory tests during early boot. Instead of returning via `RTS`, test routines jump to `(A4)` pre-loaded with the continuation address. This is continuation-passing style used when the stack hasn't been validated yet.

---

## 6. Interrupt System

**Confidence: Verified** for dispatch tests, hook addresses, register/memory
effects, and RTE/tail-JMP behavior.

### 6.1 Architecture

All interrupt handlers follow the same pattern: check if the game ROM has installed a handler (by testing for a `JMP` instruction = opcode `0x4EF9` at the expected hook address), and if so dispatch to it. If no game handler is installed, return via `RTE`.

### 6.2 Exception Handler (`0x300`)

```c
if (*(uint16_t*)0x40024 == 0x4EF9) {
    d0 = 0;
    JMP 0x40024;  // dispatch to game exception handler
}
RTE;
```

### 6.3 IRQ1 Handler (`0x314`) — Hooks to game ROM at `0x4000C`

### 6.4 IRQ2 Handler (`0x326`) — Hooks to game ROM at `0x40018`

### 6.5 IRQ3 Handler (`0x338`) — Hooks to game ROM at `0x40012`

### 6.6 IRQ4 / VBLANK Handler (`0x34A`) — The most important interrupt

```c
if (ram.os_vblank_active != 0) {
    JMP os_vblank_handler;   // OS is in control
} else {
    // Game is in control
    if (*(uint16_t*)0x40006 == 0x4EF9) {
        JMP 0x40006;         // dispatch to game VBLANK handler
    }
    WRITE(hw.vblank_ack);
    RTE;
}
```

### 6.7 IRQ6 Handler (`0x36C`) — Sound processor communication

```c
if (bit3(hw.vblank_selftest)) {   // self-test switch active?
    if (*(uint16_t*)0x4001E == 0x4EF9) {
        JMP 0x4001E;              // dispatch to game IRQ6 handler
    }
    READ(0x80300E);               // dummy read to clear interrupt
    RTE;
} else {
    // OS handles sound data
    ram.sound_data_recv = READ(0x80300E);
    ram.sound_data_flag = 0;      // signal data available
    RTE;
}
```

---

## 7. OS VBLANK System

**Confidence: Verified** for the shown control flow and state updates.

### 7.1 OS VBLANK Mode Entry (`0xE14`)

Called when the OS takes control (self-test, attract mode, etc.):

```c
ram.os_vblank_active = 1;  // tell IRQ4 to use OS handler
ram.pf_vscroll_hi = 0;
ram.pf_hscroll = 0;
ram.pf_vscroll_lo = 0;
ram.vblank_occurred = 0;
ram.os_flag = 0;
call 0x355C;               // clear text effect state
SR = 0x2000;               // enable all interrupts
call 0x129A(d5);           // OS main loop (d5 = mode flag)
SR = 0x2700;               // disable interrupts
ram.os_vblank_active = 0;  // return VBLANK control to game
JMP 0x8EC;                 // return to boot continuation
```

### 7.2 OS VBLANK Handler (`0xE5E`) — Called every VBLANK (60 Hz) when OS is in control

```c
PUSH d0-d1/a0-a1;
WRITE(hw.vblank_ack);
WRITE(hw.watchdog);

// Update scroll registers from shadow variables
scroll_v = (ram.pf_vscroll_hi << 7) | ram.pf_vscroll_lo;
WRITE(0x905F6E, scroll_v);
WRITE(0x930000, ram.pf_hscroll);

// Signal VBLANK to main loop
ram.vblank_occurred = 1;
ram.timer_countdown--;

// Process text scrolling effects
call process_text_effects;

// Input snapshot
if (ram.game_hook_flag == 0) {
    if (*(uint16_t*)0x40042 == 0x4EF9) {
        call 0x40042;   // game VBLANK hook (reads inputs)
    }
} else {
    d0 = READ_LONG(0x803000);  // read all 4 player inputs directly
}
ram.player_inputs_snapshot = d0;

call eeprom_process;
POP d0-d1/a0-a1;
RTE;
```

---

## 8. Detailed OS Function Reference

**Confidence: Verified** for addresses and observable effects unless a
subsection says otherwise. Concise purpose names and semantic parameter labels
are **Strong inference** from the bodies and their Gauntlet II callers.

### 8.1 Number Formatting

#### `format_decimal` (`0x2ABE`, API `0x106`)
Converts a 32-bit unsigned integer to decimal ASCII string.

**Stack:** `+0x08`: value (long); `+0x0C`: buffer pointer; `+0x12`: field width (word); `+0x16`: leading-zeros flag.  
Divides by 10 repeatedly, builds string right-to-left. Handles values >99999 by splitting the division.

#### `format_hex` (`0x2A5E`, API `0x10C`)
Converts a 32-bit value to hexadecimal ASCII string.

**Stack:** `+0x04`: value (long); `+0x08`: buffer pointer; `+0x0E`: field width (word); `+0x12`: uppercase flag.

#### `format_number` (`0x2918`, API `0x112`)
General-purpose formatter. Format character at `+0x0F(SP)`: `'d'`=decimal, `'s'`=signed, `'X'/'x'/'h'`=hex, `'o'`=octal, `'b'`=binary.

### 8.2 Text Display

#### `display_text` (`0x2E36`, API `0x142`)
Primary text display function. Displays a string at a position on the alpha overlay with scroll effect support.

**Stack:** `+0x04`: text descriptor pointer; `+0x0A`: color/attribute word.

Text descriptor struct:
```c
struct text_desc {
    uint8_t  row;         // Y position (0-29)
    uint8_t  col;         // X position (0-41)
    uint32_t string_ptr;  // pointer to null-terminated ASCII string
    uint8_t  repeat;      // continuation count
    uint32_t next_ptr;    // pointer to next descriptor (for chaining)
};
```

In scrolled mode (Gauntlet-specific): row is inverted (`41 - col`) and multiplied by 128 for column-major addressing.

#### `draw_string` (`0x2F04`, API `0x25A`)
Draws ASCII string directly to alpha RAM at row/column.

**Stack:** `+0x07`: row (byte); `+0x0B`: col (byte); `+0x0C`: string pointer; `+0x12`: color/style word (bits 0–1 select character style: 0=normal, 1=uppercase-shifted, 2=lowercase-shifted).  
**Returns:** D0 = number of characters written.

#### `display_decimal_value` (`0x2EB4`, API `0x260`)
Convenience: formats decimal number then calls `display_text`.

#### `display_hex_value` (`0x2EEA`, API `0x266`)
Same but for hexadecimal values.

#### `write_alpha_char` (`0x3044`, API `0x218`)
Writes a single character to alpha overlay at a given position.

**Stack:** `+0x07`: row; `+0x0B`: col; `+0x0E`: character value (word); `+0x12`: color/style.

#### `calc_alpha_address` (`0x2CE4`, API `0x224`)
Calculates the linear address in alpha RAM for row/column.

**Returns:** D0 = absolute address (0x905000 + offset).

### 8.3 Alpha Display Management

#### `init_alpha_display` (`0x3522`, API `0x14E`)
Initializes the alpha overlay. Detects Gauntlet game ROM (checks `0x40072`), sets `ram.display_mode` (1 = Gauntlet scrolling, 0 = standard), clears all alpha RAM.

#### `write_alpha_word` (`0x3586`, API `0x21E`)
Writes a raw 16-bit value to alpha RAM at a given offset.

### 8.4 Text Scroll/Effect System

The OS supports 4 simultaneous text effect slots (state at `0x904F18`). Types:
- **Type 1**: Clear text
- **Type 2**: Typewriter effect (character by character)
- **Type 3**: Horizontal scroll from one column
- **Type 4**: Scroll by shifting alpha RAM rows
- **Type 5**: Reverse row scroll
- **Type 7**: Full display mode — scrolls entire screen

#### `start_scroll_text` (`0x3162`, API `0x100`)
Starts a type-2 vertical scroll effect.

**Stack:** `+0x0C`: text descriptor pointer; `+0x0E`: speed/delay; `+0x12`: color.  
**Returns:** D0 = 1 if started, 0 if no slots available.

#### `start_scroll_type1/3/4` (API `0x12A/0x130/0x11E`)
- Type 1: Horizontal scroll right
- Type 3: Horizontal scroll left
- Type 4: Instant display (no scroll, clear after delay)

#### `start_scroll_updown` (`0x3122`, API `0x124`)
Vertical scroll. Positive speed = down, negative = up.

#### `stop_text_effect` (`0x30F4`, API `0x118`)
Stops and clears a text effect slot by descriptor pointer.

#### `process_text_effects` (`0x2B3C`, API `0x148`)
**Called every VBLANK.** Processes all 4 text effect slots. Each slot has type, speed counter, phase counter, and text descriptor pointer.

#### `init_scroll_system` (`0x3130`, API `0x136`)
Initializes the entire text scroll system. Clears scroll positions, then starts the first text effect.

### 8.5 Large Character Display

Used for title screens, attract mode, and score displays. Renders characters using 2×2 or larger tile patterns.

#### `display_large_text` (`0x31D2`, API `0x200`)
Displays a string using large (multi-tile) characters on the alpha overlay. Looks up each character in the large character font table at PC-relative offset `0x34A2`, renders 2×2 tile blocks.

**Returns:** D0 = total pixel width of rendered text.

#### `display_large_char_raw` (`0x32A0`, API `0x212`)
Renders a single large character tile pattern.

#### `display_large_char_at` (`0x32BC`, API `0x20C`)
Renders a large character at a specified screen position.

### 8.6 VBLANK Synchronization

#### `wait_vblanks` (`0x359A`, API `0x154`)
Waits for N VBLANK interrupts. Uses `ram.vblank_occurred` as sync semaphore.

**Stack:** `+0x06`: count (word).

```c
while (count-- > 0) {
    while (ram.vblank_occurred == old_value) { }  // spin-wait
}
```

### 8.7 Sound System

#### `send_sound_command` (`0x4184`, API `0x172`)
Sends a sound command to the sound processor.

**Stack:** `+0x06`: sound command number (word); `+0x08`: callback pointer; `+0x0E`: parameter byte.

1. Save SR, set interrupt level to 5 (mask sound IRQ)
2. Check if sound I/O is full (bit 5 of `0x803009`)
3. If not full: write command to `0x803170`, store callback
4. Return 1 on success, 0 on failure

#### `process_sound` (`0x41FA`, API `0x15A`)
Processes the sound queue. Reads sound status byte, compares with expected sequence number.

#### `read_sound_data` (`0x42C8`, API `0x178`)
Reads the next byte from the sound data receive buffer. Circular buffer (15 entries) at `0x904F98+`. Read pointer at `0x904F91`, write pointer at `0x904F92`.

**Returns:** D0 = received byte, or 0xFF if empty.

#### `send_sound_immediate` (`0x427A`, API `0x17E`)
Sends a sound command bypassing the queue.

#### `reset_sound_cpu` (`0x42F8`, API `0x254`)
Resets the sound processor: asserts reset via `0x80312E`, clears pending data, releases reset, clears sound queue state.

### 8.8 Sound-Latch Submission

#### `send_sound_command_wait` (`0x41C8`, API `0x23C`)

**Confidence: Verified.** Takes a sound-command word at stack offset +6,
temporarily raises the interrupt mask, and retries while SoundIOFull is set.
Once the latch is available it writes the command to `0x803170` and returns
1. The former `disable_interrupts` name was contradicted by the body.

#### `try_send_sound_command` (`0x41CC`, API `0x242`)

**Confidence: Verified.** Has the same command-word input and hardware write,
but makes one attempt: `D0.l = 1` when accepted and `D0.l = 0` when the sound
latch is busy. The former `enable_interrupts` name was contradicted by both
the body and the game-ROM callers.

### 8.9 EEPROM Management

The EEPROM system includes XOR-based checksums, write verification with retries, queued writes (one byte per VBLANK), and an error counter.

#### `eeprom_init` (`0x44E8`, API `0x190`)
Initializes EEPROM subsystem. Reads difficulty settings from game ROM (`0x4006F`), calculates required working space, allocates from the stack, stores pointer at `ram.eeprom_config_ptr` (`0x904FFC`).

#### `eeprom_process` (`0x432E`, API `0x18A`)
**Called every VBLANK.** Processes one byte of pending EEPROM writes. Increments `ram.vblank_counter` (`0x904FF8`). Manages write queue with verification and retry (4 retries per byte). Computes XOR checksums (5 check bytes per block).

EEPROM write sequence:
```c
saved_sr = SR;
SR |= 0x0700;              // disable all interrupts
WRITE(hw.eeprom_unlock);   // unlock EEPROM (0x803150)
WRITE(eeprom_addr, data);  // write the byte
SR = saved_sr;
```

#### `eeprom_check_busy` (`0x4802`, API `0x184`)
Returns D0 = 1 if EEPROM subsystem has pending operations, 0 if idle.

#### `eeprom_request_write` (`0x47A8`, API `0x196`)
Queues an EEPROM write by setting a bit in the request bitmap at `ram.eeprom_work` (`0x904FA8`).

**Stack:** `+0x04`: region index (long, bit position in bitmap).

#### `eeprom_read_block` (`0x4822`, API `0x24E`)
Reads a block of data from EEPROM with verification.

**Stack:** `+0x14`: destination buffer; `+0x1A`: block index (word); `+0x1C`: mode (long, 0 = wait for idle first).

### 8.10 Coin/Credit System

#### `process_coins` (`0x35C4`, API `0x16C`)
Processes coin inputs and calculates credits. For each of 4 player slots: reads coin counter increments, applies multiplier/bonus, updates totals, processes "coins to start" requirement, issues LED and sound feedback.

#### `get_coin_multiplier` (`0x3706`, API `0x236`)
Reads current coin multiplier from EEPROM configuration.

**Returns:** D0 = multiplier (1–4), or 0 for free play.

#### `calc_health_per_coin` (`0x3740`, API `0x160`)
Calculates health value awarded per coin based on difficulty settings.

**Stack:** `+0x08`: player index (long).  
**Returns:** D0 = health value per coin. Returns 24 (0x18) in free play mode.

#### `check_and_deduct_coin` (`0x37C2`, API `0x166`)
Checks if player has enough coins to start/continue and deducts them.

**Stack:** `+0x10`: player index (long).  
**Returns:** D0 = 1 if deducted, 0 if insufficient.

#### `check_credits` (`0x3804`, API `0x230`)
Checks if a player has enough total value to meet a threshold.

**Stack:** `+0x0C`: required amount (long); `+0x10`: player index (long).  
**Returns:** D0 = 1 if sufficient, 0 if not.

### 8.11 Game Configuration (EEPROM Settings)

#### `read_eeprom_setting` (`0x3860`, API `0x1A2`)
Reads a single game setting from EEPROM configuration tables.

**Stack:** `+0x18`: setting category (0–7); `+0x1C`: setting index within category (0–19).  
**Returns:** D0 = setting value byte. Returns 0xFE if category out of range, 0xFF if index is 19.

#### `read_game_config` (`0x38C0`, API `0x1A8`)
Reads a game configuration value. Supports multi-byte values and different data widths.

**Stack:** `+0x1C`: config item index (0–13).  
**Returns:** D0 = config value (long). Index 13 returns difficulty level from `0x4006F`.

#### `read_high_score_entry` (`0x39B0`, API `0x1AE`)
Reads a high score table entry.

**Stack:** `+0x1A`: player class (0–3: Warrior/Valkyrie/Wizard/Elf); `+0x1E`: entry rank (0–9).  
**Returns:** D0 = pointer to score data (3-byte score + 3-byte initials), or 0 if invalid.

#### `write_high_score_entry` (`0x3A7E`, API `0x1B4`)
Writes a high score entry. Encodes 3-character initials as base-40 (A-Z=1-26, 0-9=27-36, space=0). Sorts into correct table position. Queues EEPROM write.

#### `get_eeprom_base` (`0x3BE8`, API `0x1BA`)
Returns base pointer for a given EEPROM data section.

#### `write_eeprom_setting` (`0x3CF6`, API `0x1C0`) — Writes a game setting value to EEPROM.

#### `rank_high_score` (`0x3F68`, API `0x1C6`)

**Confidence: Verified.** Takes a character-class index and a 24-bit score
value, compares it with that class's ten EEPROM high-score entries, and
returns rank 0–9, 10 when it does not rank, or -1 when the value does not fit
the three-byte score format. The former `read_eeprom_config` label was
contradicted by the implementation.

#### `write_eeprom_config` (`0x401A`, API `0x1CC`) — Writes an EEPROM configuration block.

### 8.12 Statistics

#### `process_coin_stats` (`0x4038`, API `0x19C`)
Processes coin statistics and updates histogram data in EEPROM.

**Stack:** `+0x1A`: player index (word); `+0x1E`: stat value (word, max 128).

### 8.13 Self-Test / Diagnostics

#### `run_self_test` (`0x5454`, API `0x1D2`)
Entry point for the diagnostic/self-test suite. Self-test menu includes:
- **Switch Test** — Tests all player input switches with live display
- **Playfield Test** — Tests playfield RAM and display with bank selection
- **Alpha Test** — Tests alphanumeric overlay
- **Color Test** — Tests color RAM with named colors (White, Red, Green, Blue, Grey, Violet)
- **Convergence Test** — Displays convergence pattern
- **Motion Object Test** — Tests sprite system (Object, Picture, Horizontal, Vertical, Size, Color Palette)
- **Sound Test** — Full sound system diagnostics:
  - Tests sound CPU communication (3-second timeout)
  - Reports: Sound CPU Not Responding, Speech/Music Chip Timeout, Interrupt Error, RAM/ROM errors
  - Interactive sound selection, Music/Effects/Speech Chip tests
- **Statistics** — Coin/play statistics per player, histograms
- **Configuration** — Game Options, Coin Options (with DIP switch display)

#### `display_attract_screen` (`0x58C6`, API `0x248`)
Displays an attract mode or configuration screen. Calls `init_alpha_display`, initializes display headers from OS ROM data tables, delegates to either the default attract sequence or a custom display routine.

---

## 9. OS RAM Variable Map

**Confidence: Verified** for address, access width, and directly observed
read/write behavior. Generic names such as `os_flag` retain **Strong
inference** semantics where several OS paths reuse the storage.

### 9.1 Video RAM Spare — OS Working Area (`0x904000–0x904FFF`)

| Address | Size | Name | Description |
|---------|------|------|-------------|
| `0x904000` | word | `os_flag` | General OS state flag |
| `0x904004` | word | `vblank_occurred` | Set to 1 each VBLANK; used as sync semaphore |
| `0x904006` | word | `pf_vscroll_hi` | Playfield vertical scroll high bits (shadow) |
| `0x904008` | word | `pf_hscroll` | Playfield horizontal scroll (shadow) |
| `0x90400A` | word | `pf_vscroll_lo` | Playfield vertical scroll low bits (shadow) |
| `0x90400C` | word | `timer_countdown` | Countdown timer (decremented each VBLANK) |
| `0x90400E` | word | `sound_data_recv` | Last byte received from sound CPU |
| `0x904010` | word | `sound_data_flag` | Cleared when sound data received |
| `0x904014` | word | `game_hook_flag` | 0 = game ROM hooks active; 1 = OS-only mode |
| `0x904F00` | long | `scroll_base` | Base value for scroll system |
| `0x904F02` | word | `scroll_speed` | Text scroll speed setting |
| `0x904F04` | word | `vblank_sync` | VBLANK synchronization counter |
| `0x904F06` | word | `scroll_direction` | Current scroll direction/offset |
| `0x904F08` | word | `scroll_counter` | Scroll frame counter |
| `0x904F0A` | word | `scroll_limit` | Scroll limit value |
| `0x904F0C` | word | `os_vblank_active` | 1 = OS handles VBLANK; 0 = game handles VBLANK |
| `0x904F0E` | word | `display_mode` | 0 = standard alpha; 1 = Gauntlet scrolling mode |
| `0x904F10` | 4 B | `text_color` | Per-slot text color attributes (2 words) |
| `0x904F18` | 4 B | `text_effect_type` | Per-slot effect type (0=inactive, 1-7=active types) |
| `0x904F1C` | 8 B | `text_effect_speed` | Per-slot speed/delay values (2 words) |
| `0x904F24` | 8 B | `text_effect_counter` | Per-slot frame counters (2 words) |
| `0x904F2C` | 4 B | `text_effect_phase` | Per-slot animation phase |
| `0x904F30` | 4 B | `text_effect_step` | Per-slot step counter |
| `0x904F34` | 16 B | `text_effect_desc` | Per-slot text descriptor pointers (4 longs) |
| `0x904F44` | long | `highscore_work_ptr` | Working pointer for high score operations |
| `0x904F8A` | long | `player_inputs_snapshot` | All 4 players' input state (snapshot from VBLANK) |
| `0x904F8E` | struct | `sound_queue` | Sound command queue structure |
| `0x904FA8` | struct | `eeprom_work` | EEPROM write request bitmap and work area |
| `0x904FC0` | byte | `error_count` | Cumulative EEPROM error count |
| `0x904FEC` | 4 B | `coin_counters` | Per-player coin counter accumulators |
| `0x904FF0` | 4 B | `coin_totals` | Per-player total coins deposited |
| `0x904FF4` | 4 B | `coin_pending` | Per-player pending coin credits |
| `0x904FF8` | long | `vblank_counter` | Monotonic VBLANK counter (incremented each frame) |
| `0x904FFA` | byte | `eeprom_dirty_flag` | Non-zero if EEPROM needs flushing |
| `0x904FFC` | long | `eeprom_config_ptr` | Pointer to EEPROM config working area (allocated from stack) |

---

## 10. ROM Code Layout

**Confidence: Strong inference.** Boundaries are byte-exact annotations, but
the broad prose category assigned to a range may combine code and local data.

| Address Range | Size | Description |
|---------------|------|-------------|
| `0x0000–0x00FF` | 256 B | M68010 vector table |
| `0x0100–0x01D7` | 216 B | OS API jump table (36 JMP entries) |
| `0x01D8–0x01F7` | 32 B | Data address table |
| `0x0200–0x027F` | 128 B | OS API jump table continued (20 JMP entries) |
| `0x0300–0x039F` | 160 B | Interrupt/exception handlers |
| `0x03A0–0x05E1` | 578 B | Normal boot RAM tests |
| `0x05E2–0x061D` | 60 B | Reset entry point |
| `0x061E–0x070B` | 238 B | Self-test boot RAM tests |
| `0x070C–0x0A2B` | 800 B | Main init, ROM checksum, game ROM validation |
| `0x0A2C–0x0E13` | ~2 KB | Memory test subroutines, error display, helpers |
| `0x0E14–0x0EEC` | 217 B | OS VBLANK system |
| `0x0EEE–0x1299` | ~1 KB | Display helpers, playfield manipulation |
| `0x129A–0x1631` | ~900 B | OS main loop, self-test dispatch, attract mode logic |
| `0x1632–0x21FF` | ~3 KB | Self-test mode screens and menus |
| `0x2200–0x28FF` | ~1.8 KB | EEPROM validation, statistics, config menus |
| `0x2918–0x2E35` | ~1.3 KB | Number formatting, text effect processing |
| `0x2E36–0x3521` | ~1.8 KB | Text display, string drawing, alpha RAM functions |
| `0x3522–0x35C3` | 162 B | Alpha display init, wait_vblanks, set_text_position |
| `0x35C4–0x3805` | ~580 B | Coin/credit system |
| `0x3806–0x4183` | ~2.4 KB | EEPROM settings, game config, high scores |
| `0x4184–0x42F7` | 372 B | Sound system, interrupt control |
| `0x42F8–0x5453` | ~4.5 KB | Sound reset, EEPROM process/init, read/write, coin stats |
| `0x5454–0x599F` | ~1.4 KB | Self-test diagnostics, attract screen |
| `0x59A0–0x6FFF` | ~5.8 KB | Data tables, lookup tables, string data, font data |

**Total named OS ROM functions:** 68

---

## 11. Key Architectural Notes

**Confidence: Verified** for the API/hook/VBLANK mechanisms and watchdog write
sites; “separation pattern” and “callback-based design” are architectural
summaries of those observations.

### OS/Game Separation Pattern

1. **Fixed API entry points** (jump table at 0x100) — game code never calls OS internals directly
2. **Hook-based interrupt dispatch** — each IRQ handler checks for a JMP instruction at the corresponding game ROM vector
3. **VBLANK ownership flag** (`ram.os_vblank_active`) — cleanly switches between OS-managed and game-managed VBLANK
4. **Callback-based design** — OS main loop calls game hooks through vectors at 0x40042, 0x40048, and optionally 0x4004E

### Watchdog Pattern

Throughout the boot sequence, `move.w d0, hw.watchdog` appears hundreds of times. During error display, code waits for VBLANK toggles while petting the watchdog:
```
loop:
    pet watchdog
    wait for VBLANK=1 → pet watchdog → wait for VBLANK=0 → pet watchdog → wait for VBLANK=1
    check button
    loop if not pressed
```

---

## 12. Game-Related Strings in OS ROM

**Confidence: Verified** as NUL-terminated ROM text. The subsection titles
describe their call-site use where traced; strings alone are not proof that
every phrase is reachable in this game revision.

The OS ROM data section contains extensive game text:

### 12.1 Error Messages
- `"Working RAM error"`, `"COLOR RAM error at:"`, `"PLAYFIELD RAM error at:"`
- `"ALPHA RAM error at:"`, `"MOTION OBJ RAM error at:"`, `"GAME RAM error at:"`
- `"Main ROM error"`, `"Game board RAM error"`, `"NO GAME PROGRAM"`
- `"ROM at XXXXX error"` (for addresses 10000–88000), `"EEPROM ERROR"`

### 12.2 Self-Test Screen Labels
- `"Switch Test"`, `"Playfield Test"`, `"Alpha Test"`, `"Color Test"`
- `"Convergence Test"`, `"Motion Object Test"`, `"Sound Test"`
- `"Statistics"`, `"Game Options"`, `"Coin Options"`

### 12.3 Sound Test Messages
- `"Testing Sound CPU"`, `"Wait 3 Seconds"`
- `"Sound Processor Not Responding"`, `"Speech Chip Time Out"`, `"Music Chip Time Out"`
- `"Sound CPU Interrupt Error"`, `"Sound CPU RAM 1/2 Error"`, `"Sound CPU ROM 1/2/3 Error"`
- `"Sound CPU Status  : Good"`, `"Sound # :"`, `"Number of Sounds  :"`

### 12.4 Game Messages
- `"PRESS START"`, `"ADD   COIN"`, `"ADD   COINS"`, `"INSERT COIN"`
- `"GAME OVER"`, `"COIN MIN."`, `"TIME:"`
- `"PRESS START WITHIN 20 SECONDS TO CONTINUE GAME AT THIS LEVEL"`
- `"ATARI GAMES"`, `"@1985"`
- `"TREASURE ROOM"`, `"YOU HAVE    SECONDS TO COLLECT TREASURES"`
- `"YOU MUST EXIT TO RECEIVE BONUS POINTS"`

### 12.5 Configuration Option Strings
- `"Game Difficulty"`: `"0 - Easiest"` through `"7 - Hardest"`
- `"Health Per Coin"`: `"1000"` through `"2000"` (100-unit increments)
- `"Coins to Start"`: `"1234"`
- `"Multiplier:"`, `"Bonus Adder:"`: Various options including `"Free Play"`
- `"Sounds in Attract Mode?"`, `"Disable Speech?"`, `"Reduce Text?"`
- `"Automatic Reset of High Score Tables?"`, `"Restore Factory Default Settings?"`
- `"Reset High Score Tables?"`

### 12.6 Gameplay Hints (displayed in attract mode)
- `"FIND THE HIDDEN POTION"`, `"STUN OTHER PLAYERS"`
- `"GHOSTS MUST BE SHOT"`, `"SOME FOOD CAN BE DESTROYED"`
- `"FIGHT HAND TO HAND BY RUNNING INTO GRUNTS"`
- `"BEWARE THE DEMONS WHICH SHOOT YOU"`
- `"SORCERERS MAY BE INVISIBLE"`, `"USE MAGIC TO KILL DEATH"`
- `"HOLD FIRE BUTTON TO SHOOT"`, `"RELEASE FIRE BUTTON TO MOVE"`
- `"GAME OVER WHEN HEALTH = 0"`

### 12.7 Legend/Stats Strings
- `"WARRIOR:"`, `"VALKYRIE:"`, `"WIZARD:"`, `"ELF:"`
- `"FOOD:  HEALTH INCREASED BY 100"`
- `"SCORE PER COIN"`, `"INSERT COINS FOR MORE HEALTH"`

### 12.8 High Score Default Initials
Developer initials in the factory-default high score table: HAL, KEN, BOB, MEA, CAD, ED, GEL, SMO, CJ

---

## 13. Loading the radare2 Annotations

**Confidence: Verified** for the supported three-ROM loader described in
`INDEX.md`; the older one-ROM command below is retained only as historical
project context.

The OS ROM analysis was performed with a separate radare2 project. To load into radare2:

```bash
r2 -i gauntlet_os.r2 row9.bin
```

This sets M68K/68010 architecture, creates all named functions, adds hardware/RAM variable flags, and adds comments at key locations.

> **Note:** The main project file `gauntlet.r2` loads all three ROMs together (row76.bin at 0x40000, row9.bin at 0x0, row10.bin at 0x38000). See `INDEX.md` for full loading instructions.
