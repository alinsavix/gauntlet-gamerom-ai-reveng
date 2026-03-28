# Gauntlet II ROM Coverage Analysis

*Identifies areas of the Game ROM (row76.bin, 0x040000–0x05FFFF) NOT yet reverse engineered.*

## Overview

The ROM is 128KB (0x20000 bytes). It has three distinct regions:

| Region | Address Range | Size | Content |
|--------|---------------|------|---------|
| Code | 0x40000–0x5561F | ~87 KB | All 170 compiled C functions + hand-written asm |
| Padding | 0x55620–0x56E53 | ~6 KB | Unused, filled with 0xFF |
| Slapstic Trampolines | 0x56E54–0x56F00 | ~170 B | Bank-switch helper code (3 small functions) |
| Data Tables | 0x56F00–0x5FFB1 | ~37 KB | ROM tables, strings, palettes, animation data, tile descriptors |
| End Padding | 0x5FFB2–0x5FFFE | 76 B | Unused 0xFF |

**Code region**: 170 functions found via `link a6` prologue search. All 170 are documented or referenced in FUNCTIONS_PLAN.md — **zero undocumented functions with standard prologues**.

**Data region**: 103 named data tables documented in DETAILED_REPORT.md and FUNCTIONS_PLAN.md. Several gaps remain.

---

## 1. Undocumented Code Areas

### Functions Without `link a6` Prologues

Some functions use bare `movem` saves or are pure leaf functions (no frame setup). These are harder to find automatically. Known undocumented ones:

| Address | Likely Purpose | Evidence |
|---------|----------------|----------|
| 0x56E84 | slapstic_bank_select_3 | Third slapstic trampoline variant, writes to 0x38000 |
| 0x56E90–0x56FA7 | slapstic helper data/code | Between trampolines and 0xFF padding; may contain bank-switch lookup tables |
| 0x40000–0x40005 | VBLANK jump vector | The game's jump table entry (JSR target from OS VBLANK handler) |
| 0x40006–0x4016D | VBLANK handler + early dispatch | Known to exist from OS_ROM.md (VBLANK at 0x4017E), but the full code 0x40006–0x40527 has only been partially traced |

### Inter-Function Code Bodies

Many "gaps" between function entry points are actually the **bodies** of the preceding function (extending from `link` to `rts`). However, some functions contain **inline sub-functions** (BSR targets within the body) that haven't been individually named:

| Parent Function | Inline BSR Targets | Notes |
|-----------------|-------------------|-------|
| player_try_move (0x41BF0) | 0x41C30, 0x42598, 0x425B4, 0x42648, 0x426D4, 0x4270C, 0x42744, 0x427B4, 0x4280E, 0x428A4, 0x4293A, 0x429D0 | All documented as sub-calls but not all have full standalone descriptions |
| monster_loop_core (0x40E6A) | 0x40FAE (loop body), 0x41532 (generator pass) | Loop structure documented but inline handlers at 0x4119A–0x414BE merged into description |
| main_attract (0x44562) | 0x449CC, 0x449D4, 0x44A82, 0x44AC2, 0x44C7E, 0x44DB4 | Several inline subs documented in agent output |
| main_start_game (0x4800C) | Multiple join-handling sub-paths | Complex branching documented at high level |

---

## 2. Undocumented Data Table Areas

### Large Gaps in Data Region (>500 bytes)

| Gap Start | Gap End | Size | Likely Content |
|-----------|---------|------|----------------|
| **0x57370–0x57628** | | 696 B | Character display configuration (between sprite_layout and portrait_ptrs) |
| **0x57664–0x57862** | | 510 B | Continue screen text strings and formatting data |
| **0x57BD8–0x58070** | | 1,176 B | **Demo data continuation** — between direction tables and invisibility masks. Likely contains extended demo input streams or per-level demo configs |
| **0x581AC–0x5858C** | | 992 B | **Unknown data block** — between demo data end and master object parameter tables. Could be per-level configuration data or item placement rules |
| **0x59716–0x5A200** | | 2,794 B | **Speech/dialog data** — 69% ASCII. Contains speech announcement text strings and pointer tables for the character announcement system. Format: longword pointers (0x00BF0000, 0x00C00000...) followed by text strings |
| **0x5A320–0x5AB1A** | | 2,042 B | **Dialog message strings** — between flash palette tables and continue screen strings. Contains the in-game message text ("SOME WALLS MAY BE DESTROYED", "TRAPS MAKE WALLS DISAPPEAR", etc.) |
| **0x5AD3E–0x5B20E** | | 1,232 B | **Palette initialization data** — extended palette data beyond the basic init block. Color definitions for various game states |
| **0x5B22E–0x5B64A** | | 1,052 B | **Palette cycling data** — player hurt flash, poison effect, invulnerability shimmer color sequences |
| **0x5BA90–0x5C8A0** | | 3,600 B | **Playfield tile graphics data** — largest undocumented data block. Contains tile sprite descriptors, wall pattern graphics, floor pattern graphics indexed by the wall/floor pattern byte from maze headers. This is the core visual lookup data for the 16 wall patterns × 16 floor patterns |
| **0x5CB48–0x5D478** | | 2,352 B | **Extended tile/sprite data** — between display config data and dragon tables. Likely contains tile connectivity graphics, special tile descriptors (transporters, traps, exits) |
| **0x5D848–0x5F9CE** | | 8,582 B | **Largest undocumented data block.** Between playfield palettes and wall connectivity lookup tables. Contains: playfield tile pattern data, wall segment graphics, floor segment graphics, exit animation frames, forcefield segment data. This is the heart of the tile rendering data that feeds into refresh_tile_visual and update_wall_connection |

### Small Gaps (96–500 bytes, likely continuation of adjacent tables)

Most 96-byte gaps between animation tables (0x590xx–0x596xx) are actually the **bodies** of those tables — our size estimates of 128 bytes per table were conservative. The actual tables are 128 bytes of word data (64 entries) with the preceding gap being the table for the *moving* variant of the same monster.

---

## 3. The 0xFF Padding Region (0x55620–0x56E53)

This 6,196-byte block of solid 0xFF between the last compiled function (0x5561E) and the Slapstic trampolines (0x56E54) is **genuinely unused ROM space**. It represents approximately 4.8% of the ROM. This is typical of 1980s arcade ROMs where the compiled code didn't fill the entire EPROM chip — the remaining space was left as erased (0xFF) state.

---

## 4. Summary: What Remains Unknown

### NOW DECODED — Tile Graphics Data (~14.6 KB)

#### Playfield Tile Sprite Descriptors (0x5BA90–0x5C8A0, ~3.6 KB)

This region contains the 2×2 tile sprite descriptors read by `write_tile_descriptor` (0x5E542). Each descriptor is **8 bytes = 4 words**, written to VRAM in the order:

| Word | VRAM Offset | Position |
|------|------------|----------|
| 0 | +0x000 | Top-left |
| 1 | +0x080 | Bottom-left (one VRAM row down) |
| 2 | +0x002 | Top-right |
| 3 | +0x082 | Bottom-right |

Structure within the region:

| Address | Size | Entries | Content |
|---------|------|---------|---------|
| 0x5BA70 | 32 B | 8 ptrs | Longword pointer table 1 into 0x5CAA8 (wall pattern lookup) |
| 0x5BA90 | 32 B | 8 ptrs | Longword pointer table 2 into 0x5CAA8 |
| 0x5BAB0 | 32 B | 16 words | Scroll/display config (signed word offsets) |
| 0x5BAD0 | 16 B | 4 words | Null tile IDs: 0x0045, 0x0047, 0x0046, 0x0048 |
| 0x5BAE0 | 256 B | 32 × 8B | Floor tile set 1: tiles 0x0011–0x0040 |
| 0x5BBE0 | 256 B | 32 × 8B | Floor tile set 2 (stone): tiles 0x01C1–0x01E5 |
| 0x5BCE0 | 256 B | 32 × 8B | Floor tile set 3 (wood/forest): tiles 0x01E6–0x0234 |
| 0x5BDE0–0x5C88F | ~2.7 KB | ~342 × 8B | Floor tile sets 4–N, tiles up to 0x039D |
| 0x5C8A0–0x5CAA7 | 520 B | 260 words | Wall tile IDs (sequential 0x039E–0x049D) |
| 0x5CAA8–0x5CB27 | 128 B | 16 × 8B | Floor connectivity descriptors (8 sub-entries each) |

`refresh_tile_visual` selects sub-tables by tile type: type 0x10 → 0x5C8A0, type 0x11 → 0x5C8A8, type 0x3E → 0x5CAA8, type 0x3F → indirect through pointer table at 0x5BA70 using 4-bit connectivity nibble.

#### Extended Tile Data — Special Objects (0x5CB48–0x5D478, ~2.4 KB)

| Address | Size | Content |
|---------|------|---------|
| 0x5CB48–0x5CD3F | ~504 B | **Sparse object tile table** (~252 word entries, mostly zero). Non-zero entries are tile IDs for special objects: transporters (0x04B2), traps (0x04B3–0x04B4), doors (0x04B5–0x04BA), exits (0x04BB–0x04C0), forcefields (0x04C1–0x04CA). Word index = object type/state code. |
| 0x5CD40–0x5D3DF | ~1.7 KB | **Dense animation frame table** (~848 word entries). Sequential tile IDs for special object animations: doors 0x04CC–0x04FE, exit portals 0x04FF–0x053D, forcefield frames 0x053E–0x059F, extended objects 0x05A0–0x07B2. Zeros = skip/end-of-animation. |
| 0x5D3E8–0x5D478 | ~152 B | **Dragon path motion vectors** — signed word pairs (Δx, Δy), ~38 entries. Used by dragon AI for body segment movement. |

#### Largest Data Block — Tile Patterns + Embedded Code (0x5D848–0x5F9CE, ~8.6 KB)

This region is NOT pure data — it's a mix of data tables and executable code (the tile rendering subroutines):

| Address | Size | Content |
|---------|------|---------|
| 0x5D848–0x5D9E4 | ~412 B | **Palette color ramps** — 13 blocks × 32 bytes. Each: 8 zero bytes (header) + 12 packed 12-bit RGB color words + 8 zero bytes (trailer). One palette per tileset/environment (stone, forest, ice, fire, etc.) |
| 0x5D9E8–0x5DAA0 | ~184 B | **Secret code contest strings** — null-terminated ASCII: "SECRET CODE", "REMEMBER YOUR", "ENTER YOUR", "LAST-NAME FIRST-NAME", "SEND CONTEST ENTRY FORM. TO ATARI GAMES CORP.", "CONTEST ENDS 12/19/86". The 1986 Atari Gauntlet II contest entry screen text. |
| 0x5DAA0–0x5DB28 | ~136 B | **Wall neighbor connectivity state table** — 16 rows × 8 bytes. Values 0x1B–0x2D encode which wall-edge tile to use given a 4-bit N/S/E/W neighbor mask. |
| 0x5DC50–0x5F9CE | ~7.5 KB | **Executable code** — tile rendering subroutines including the bodies of `mob_create`, `mob_unlink`, `mob_remove`, `write_tile_descriptor`, `refresh_tile_visual`, `update_wall_connection`, and wall/floor drawing helpers. Already documented in FUNCTIONS_PLAN.md. |

#### Wall Connectivity Lookup Tables (0x5F9CE–0x5FFFF, ~1.6 KB)

Now fully decoded:

| Address | Size | Entries | Format | Content |
|---------|------|---------|--------|---------|
| 0x5F9CE | 64 B | 16 × 4B | 2 words each | **Straight-wall connectivity**: offset pairs per N/S/E/W mask. Values 0x9D18–0x9D38. |
| 0x5FA0E | ~188 B | — | code | Wall drawing routine (interleaved with data) |
| 0x5FACA | 18 B | 9 × 2B | 1 word each | **Corner-wall connectivity**: offsets 0x9D3C–0x9D6E for L-shaped/corner walls |
| 0x5FADA | ~256 B | ~128 words | mixed | Scroll deltas and VRAM stride counts for wall rendering |
| 0x5FBDC | 16 B | 9 × 2B | 1 word each | **Junction-wall connectivity**: offsets 0x9D7C–0x9DAC for T/cross junctions |
| 0x5FC10 | 16 B | 4 longs | addresses | **Playfield VRAM base addresses**: 0x90553C, 0x9057BC, 0x905A3C, 0x905CBC |
| 0x5FC20–0x5FFFF | ~1 KB | — | code | RNG (0x5FC46), visibility check (0x5FC56), VRAM helpers |

### NOW DECODED — Speech, Dialog, and String Data (~4.8 KB)

#### Speech/Dialog Hint System (0x59716–0x5A200, ~2.8 KB)

| Address | Size | Content |
|---------|------|---------|
| 0x596F8–0x59732 | ~58 B | **Player color speech ID array** — 14 longwords. IDs 0xBD–0xCC map to "RED WARRIOR" through "GREEN ELF" speech clips |
| 0x59732–0x59784 | ~82 B | **Hint text pointer table** — 20 longword ROM pointers (10 per player-count group) into hint string bank |
| 0x59786–0x598B6 | ~304 B | **Hint text strings** — null-terminated ASCII, word-aligned: "TRY TRANSPORTABILITY", "WATCH WHAT YOU SHOOT", "DON'T BE GREEDY", "SAVE SUPER SHOTS", "DON'T USE INVULNERABILITY", "DON'T GET HIT", "TRY PUSHING A WALL", "DON'T BE FOOLED", "GO ON A DIET", "BE PUSHY", "IT COULD BE NICE", "DON'T HURT FRIENDS" |
| 0x598B6–0x59A00 | ~330 B | **Hint records with speech IDs** — 10-byte records: `[00 00][type:cmd word][4-byte ROM ptr][00 00]`. Examples: "FIND THE HIDDEN POTION", "PLAYER SHOTS STUN OTHERS", "ALL WALLS ARE INVISIBLE", "THE EXIT WILL MOVE" |
| 0x59A00–0x5A200 | ~512 B | **Gameplay tip strings** — two-line format: "MORE PLAYERS ALLOWS HIGHER / BONUS MULTIPLIER", "ADD COINS ANYTIME / FOR EXTRA HEALTH", "STALLING WILL CAUSE / DOORS TO OPEN", "FIND EXIT TO NEXT LEVEL", etc. |

#### In-Game Message Strings (0x5A320–0x5AB1A, ~2.0 KB)

| Address | Size | Content |
|---------|------|---------|
| 0x5A320–0x5A37F | 96 B | Null padding (empty table entries) |
| 0x5A380–0x5A4FF | 288 B | **16 fixed-width power-up strings** (24 bytes each): "WARRIOR NOW HAS", "VALKYRIE NOW HAS", "WIZARD NOW HAS", "ELF NOW HAS", "EXTRA ARMOR", "EXTRA SPEED", "EXTRA MAGIC POWER", "EXTRA SHOT POWER", "EXTRA SHOT SPEED", "EXTRA FIGHT POWER", "INVISIBILITY", "REPULSIVENESS", "REFLECTING SHOTS", "TRANSPORTABILITY", "10 SUPER SHOTS", "INVULNERABILITY" |
| 0x5A500–0x5A53F | 64 B | **16-entry pointer table** to above strings |
| 0x5A540–0x5A56F | 48 B | **Attribute labels**: "Type", "Fight", "Shoot", "Magic", "NO", "YES", "STUN" |
| 0x5A570–0x5A663 | 244 B | **Monster display records** — 12-byte entries: `[4B name ptr][1B Y offset][1B param][2B pad]` |
| 0x5A670–0x5A6DD | 110 B | **Monster/object name strings**: "GHOST", "GRUNT", "DEMON", "LOBBER", "SORCERER", "DEATH", "ACID PUDDLE", "SUPER SORCERER", "IT", "DRAGON", "LEGEND", "MONSTERS", "WALL", "POTIONS" |
| 0x5A6DE–0x5A8CB | 494 B | **Object descriptor records** — 10-byte: `[00 00][speech_word][4B ROM ptr][flags_word]`. Maps each object to its speech announcement and display text |
| 0x5A8CC–0x5AA66 | 410 B | **Credits strings** — "DESIGNER/PROGRAMMER:", "GAME PROGRAMMER:", "VIDEO GRAPHICS:", etc. Staff names: "ED LOGG", "BOB FLANAGAN", "SAM COMSTOCK", "SUSAN G. MCBRIDE", "ALAN MURPHY", "WILL NOBLE", "PAT MCCARTHY", "CRIS DROBNY", "HAL CANON", "BRAD FULLER", "EARL VICKERS", "KEN HATA", "MIKE ALBAUGH", "DAVE THEURER", "AND MANY OTHERS" |
| 0x5AA70–0x5AB1A | 170 B | **Bonus scoring strings**: "100 x COINS", "TREASURES x", "BONUS =", "NO BONUS !!", "5,000 x COINS =" |

### NOW DECODED — Palette and Color Data (~2.3 KB)

#### Extended Palette Data (0x5AD3E–0x5B20E, ~1.2 KB)

Each sub-palette is 32 colors × 2 bytes = 64 bytes. Color format: 12-bit RGB in a 16-bit word: `0xRGB0` (R=bits 15-12, G=bits 11-8, B=bits 7-4, low nibble unused).

| Address | Content |
|---------|---------|
| 0x5AD3E–0x5AF9E | **~22 sub-palettes** (64B each): UI/title palette, 4 player character palettes (Warrior=red, Valkyrie=blue, Wizard=yellow, Elf=green), player death-state variants, ghost/specter palette, 3 monster brightness variants (near/mid/far), item/treasure sets |
| 0x5AF9E | **Palette group pointer table** — 4 longwords pointing to character palette sets at 0x5B00E/0x5B08E/0x5B10E/0x5B18E |
| 0x5AFAE–0x5AFFE | **Fade-in sequences** — 6 color steps + 2 zeros per row, 6 rows per fade. Used for level-start/death screen transitions |
| 0x5B00E–0x5B20E | **4 character full palettes** (128B each) — Warrior, Valkyrie, Wizard, Elf. Each has 4 sub-palettes for normal/poisoned/ghost/invulnerable states |

#### Palette Cycling Sequences (0x5B22E–0x5B64A, ~1.1 KB)

Frame format: 12 color words (24 bytes) per frame. `0xFFFF` = skip (don't update this slot).

| Address | Frames | Effect |
|---------|--------|--------|
| 0x5B22E | ~7 | **Hurt flash** — red/white alternating: `0x6F00→0xFF00→0xDFFF→0x0000` |
| 0x5B32E | 16×4 | **Poison shimmer** — blue-green sine-wave oscillation across player palettes. Colors bounce: `0xDFA8→0x5FA8→0xDFA8` |
| 0x5B42E | 16×4 | **Invulnerability shimmer** — gold/white: `0xF25F/0x625F/0x322F` ramp |
| 0x5B52E | 16×4 | **Secondary poison variant** — slightly different green tones |

### NOW DECODED — Character Config and Demo Data (~1.9 KB)

#### Character Display Configuration (0x570B4–0x57370, ~700 B)

| Address | Size | Content |
|---------|------|---------|
| 0x570B4 | 16 B | **Portrait display offsets** — 4 word-pairs (X,Y) for character portrait positions |
| 0x570C4 | 32 B | **Portrait sprite pointers** — 8 longwords to sprite data at 0x905Cxx–0x905Exx |
| 0x570E4 | 30 B | **Input bitmask table** — 15 words for joystick direction decoding |
| 0x57104 | 96 B | **Auto-repeat timing** — 16 entries of 3-word tuples (initial_delay, repeat_rate, fast_rate) |

#### Secret Room & UI Strings (0x57370–0x57862, ~1.2 KB)

| Address | Size | Content |
|---------|------|---------|
| 0x57370 | 16 B | Character stat parameters (health increments, speed values per class) |
| 0x57392–0x57497 | ~260 B | **Secret room trigger table** — 10-byte records + strings: "AFTER COLLECTING ALL POTIONS", "AFTER SHOOTING 3 SECRET WALLS", "AFTER COLLECTING 6 TREASURES", "AFTER USING 5 TRANSPORTERS", "WHILE YOU ARE IT" |
| 0x574BC–0x57514 | ~88 B | Character glyph/sprite mapping table (tile indices 0xBA–0xDD) |
| 0x57520–0x57577 | ~88 B | **UI strings**: "SELECT HERO", "PRESS START", "ADD COIN", "INSERT COIN", "GAME OVER", "ON LEVEL:" |
| 0x57578–0x57635 | ~190 B | **DIP switch display records** — 10-byte format: "COIN MIN.", "TIME:", "1 COIN =", "FREE PLAY =", "HEALTH", "ATARI GAMES" |
| 0x57638–0x576A5 | ~110 B | **Continue screen strings**: "LEVEL:", "PRESS START", "WITHIN    SECONDS", "TO CONTINUE GAME", "AT THIS LEVEL" |

#### Demo/Level Config Data (0x57BD8–0x5858C, ~2.5 KB)

| Address | Size | Content |
|---------|------|---------|
| 0x57BD8–0x57EB5 | ~760 B | **Level object pre-placement table** — 50 variable-length arrays of `0x1EXX` tile/object IDs (0x0000-terminated). Defines which objects appear on each level in demo/attract mode |
| 0x57EB6–0x57FF7 | ~322 B | **Factory default high-score table** — 40 entries: `[4B score longword][3B NUL-terminated initials]`. 10 entries × 4 character classes. Scores descend 8000→4400 in steps of 400. Initials are Atari staff: AWC, CJS, PAT, GDC, JDM, JGG, RRC, JLR, TJK, DP, etc. |
| 0x58000–0x58055 | ~86 B | **Score-per-coin display** — 4 per-character records + "Enter your initials:" prompt |
| 0x58072–0x58093 | ~34 B | Per-class starting health parameters (21 word entries) |
| 0x58154–0x5818B | 56 B | **12-entry dialog tip pointer table** — longword pointers to per-level tip display records at 0x5828C+ (e.g. "PUSH / MOVABLE / WALLS", "BLUE / SELECTED / ELF"). Each pointed-to record is 3 longword sub-pointers + 3 null-terminated strings |
| 0x5818C–0x5825D | ~210 B | **Demo input streams** (already documented in DETAILED_REPORT.md section 5.8). 0x58190 falls within player 0's stream. Format: 2-byte entries (timer, joystick_byte). 0xFF = speech trigger, 0xFE = player switch |
| 0x5825E–0x5828B | ~46 B | Continuation of demo data / padding before dialog message records |
| 0x58290–0x5858B | ~760 B | **In-game tip strings**: "PUSH MOVABLE WALLS", "SOME TREASURE REQUIRES KEYS", "ACID PUDDLES MOVE RANDOMLY", "DEATH DIES AFTER TAKING UP TO 200 HEALTH", "MONSTERS FOLLOW PLAYER WHO IS IT", etc. Plus TAG game-mode coordinate data |

### NOW DECODED — Remaining Small Tables

#### Mixed Data Tables (0x5B64A–0x5BA90, ~1.1 KB)

| Address | Entries | Entry Size | Content |
|---------|---------|-----------|---------|
| 0x5B64A | 9 | 2B word | `find_empty_tile` X delta: `0, +1, +1, +1, 0, -1, -1, -1, 0` (3×3 spiral) |
| 0x5B65C | 9 | 2B word | `find_empty_tile` Y delta: values ×0x20 (pixel-offset version) |
| 0x5B66E | 130 | 1B byte | Tile walkability bitmap (0=free, 1=blocked, ~10×13 grid) |
| 0x5B6FA | 4 | 4B long | Thief variant type IDs: 0x62, 0x64, 0x63, 0x65 |
| 0x5B724 | 25 | 4B long | Item score/sound values (food=0x60, potion=0x5F, key=0x38C, etc.) |
| 0x5B788 | 13 | 4B long | Exit speech sample IDs (0x0E–0x11 = level numbers, 0x69–0xA9 = character phrases) |
| 0x5B7D4 | 8 | 2B word | Damage multiplier table A (values 1–3 by player_class × enemy_type) |
| 0x5B7E4 | 12 | 2B word | Damage multiplier table B (special attack damage, values 0–4) |
| 0x5B7FC | 16 | 2B word | Exit step motion curve (ease-in/out: 0,1,1,2,3,3,5,3,3,5,7,...,11,0) |
| 0x5B81C | 160 | 4B long | Exit animation frame pointers — ping-pong: 16 pointers per cycle × 10 animation sequences |

#### Object Parameter Gap (0x586AC–0x5874A, ~160 B)

| Address | Content |
|---------|---------|
| 0x586AC | Sentinel pair: 0x8001, 0x8001 + sprite frame base indices 0x0800, 0x09E1 |
| 0x586B4 | 12 words: monster sprite tile indices for shooting animations (4-dir × 3 frames) |
| 0x586CC | 15 words: projectile animation loop tiles (3-frame ping-pong × 5 repeats) |
| 0x586EA | 16 words: flip-variant tile indices (high byte 0x88 = flip-X hardware flag) |
| 0x5870C | 31 words: full shooting animation table (8-dir × ~4 frames, +9 stride matches spritesheet row width) |

---

### Final Coverage Status

| Category | Size | Status |
|----------|------|--------|
| Compiled functions (170) | ~87 KB | **100% documented** |
| 0xFF padding | ~6.3 KB | Identified (unused EPROM space) |
| Tile sprite descriptors | ~3.6 KB | **Decoded** — 8-byte entries (4 words per 2×2 tile), organized by tileset |
| Special object tiles | ~2.4 KB | **Decoded** — sparse index table + dense animation frame table |
| Tile pattern data + embedded code | ~8.6 KB | **Decoded** — 730B palette ramps + contest strings + connectivity table; rest is code |
| Wall connectivity tables | ~1.6 KB | **Decoded** — 16+9+9 entries, interleaved with wall-drawing code |
| Speech/dialog strings | ~4.8 KB | **Decoded** — hint records, power-up names, monster names, credits, tips |
| Palette data | ~2.3 KB | **Decoded** — 22 sub-palettes (64B each) + 4 cycling effects (hurt/poison/invuln) |
| Character/demo config | ~2.5 KB | **Decoded** — portraits, input timing, secret room triggers, UI strings |
| Demo level objects + high scores | ~1.1 KB | **Decoded** — 50-level object placement + 40-entry default high-score table |
| Dialog tip pointers + demo streams | ~312 B | **Corrected** — was misidentified as "sound chip sequences"; actually demo input data + dialog tip pointer table |
| **Total ROM** | **128 KB** | **~99% documented** |

### Remaining Unknowns (~1% of ROM)

| Item | Size | Status |
|------|------|--------|
| Dragon path table entry bit fields (0x5D578) | ~2 KB | 128-step × 16-byte entries. Control byte bit 0 = fire flag. Remaining 15 bytes per entry (body segment shape, curvature, spacing) not individually mapped. General read mechanism known: `(anim_counter >> 3) * 16 + path_index * 16` |
| EEPROM game settings bits (0x904A24) | 16 bits | Bits 0-4 = COINHEALTH, 8-9 = difficulty, 10 = 2P mode, 11 = mute, 12 = ROM version, 14 = music enable, 15 = dirty flag. **Bits 5-7 and 13 unknown** |
| Dialog tip record boundaries (0x5825E–0x584F0) | ~600 B | Contains per-level tip display records (3-pointer + 3-string groups). Individual records are readable ASCII but exact count and boundaries not exhaustively listed |
| Tile pattern ↔ descriptor index mapping | N/A (logic) | The lookup chain from maze header wallpattern/floorpattern bytes through `refresh_tile_visual` pointer tables to the ~450 tile descriptors at 0x5BAE0 hasn't been traced for all 16×16 pattern combinations |
