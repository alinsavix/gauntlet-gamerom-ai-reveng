# Gauntlet II Reverse Engineering — Documentation Index

*Consolidated findings from the Gauntlet II arcade game ROM reverse engineering project.*

---

## Project Overview

This project reverse-engineered the Gauntlet II arcade game (Atari Games, 1986) at the source-code level, using radare2 disassembly, MAME tracing, and AI-assisted analysis. Three ROMs were analyzed:

| ROM | File | Address | Size | Description |
|-----|------|---------|------|-------------|
| OS ROM | `row9.bin` | `0x000000–0x00FFFF` | 64 KB | Bootstrap, OS services, diagnostics |
| Slapstic ROM | `row10.bin` | `0x038000–0x03FFFF` | 32 KB | Level data (bank-switched, 4 × 8 KB banks) |
| Game ROM | `row76.bin` | `0x040000–0x07FFFF` | 128 KB | Main game program |

**CPU:** Motorola 68010 (32-bit, big-endian)  
**Display:** 336×240, 60 Hz

The game ROM is approximately 256 KB of compiled C (Green Hills C compiler) plus hand-written assembly, running on a 68010. ~170 functions and ~103 ROM data tables have been fully documented, covering ~99% of the game ROM.

---

## ROM File Checksums

### Game ROM (`row76.bin`, 128 KB)

Assembled from 4 chips (interleave A-chips as even bytes, B-chips as odd; concatenate rows 7 then 6):

| Part Number | Location | Size | sha1sum |
|-------------|----------|------|---------|
| 136043-1121.6a | 6A | 32 kB | `3d93236aaffe6ef692e5073b1828633e8abf0ce4` |
| 136043-1122.6b | 6B | 32 kB | `378c582c360440b808820bcd3be78ec6e8800c34` |
| 136043-1109.7a | 7A | 32 kB | `7f51184840e3c96574836b8a00bfb4a7a5f508d0` |
| 136043-1110.7b | 7B | 32 kB | `dfce027ea50188659907be698aeb26f9d8bfab23` |

**Combined:** `row76.bin`, 128 kB, sha1 `decbe6438b3a2618bd7fe79d14be034efadd7ff4`

### OS ROM (`row10.bin`, 32 KB)

| Part Number | Location | Size | sha1sum |
|-------------|----------|------|---------|
| 136043-1105.10a | 10A | 16 kB | `a9a03150f5a0ad6ce62c5cfdffb4a9f54340590c` |
| 136043-1106.10b | 10B | 16 kB | `d2df4e5b036500dcc537a1e0025abb2a8c730bdd` |

**Combined:** `row10.bin`, 32 kB, sha1 `e4a36380f4a6394ad5cfb5aff5d7c8b352232d3d`

### Slapstic/Level Data ROM (`row9.bin`, 64 KB)

| Part Number | Location | Size | sha1sum |
|-------------|----------|------|---------|
| 136037-1307.9a | 9A | 32 kB | `d5fa19e028a2f43658330c67c10e0c811d332780` |
| 136037-1308.9b | 9B | 32 kB | `7467b2ec21b1b4fcc18ff9387ce891495f4b064c` |

**Combined:** `row9.bin`, 64 kB, sha1 `6e0d2026317e4a050fd79aac24ee0a644bf5a836`

---

## Document Index

| File | Contents |
|------|----------|
| [01_hardware.md](01_hardware.md) | CPU, full memory map, hardware I/O ports, display system (tiles, palette, MOBs, alpha layer, layer priority) |
| [02_os_rom.md](02_os_rom.md) | OS ROM: boot sequence, interrupt system, VBLANK handler, complete API jump table and function reference |
| [03_game_rom_structure.md](03_game_rom_structure.md) | Game ROM: main loop (verified call sequence), calling convention, ROM layout and coverage |
| [04_game_subsystems.md](04_game_subsystems.md) | All game subsystems: monsters, players, maze/level, MOB animation, dragon, thief/mugger, transporters/forcefields, scoring/coin/dialog, attract mode/demo |
| [05_data_reference.md](05_data_reference.md) | RAM variable map, enums and constants, data structures, ROM data tables catalog |
| [06_maze_catalog.md](06_maze_catalog.md) | Complete 116-maze table (mazes 0–115, levels 1–97 plus treasure rooms and special mazes) |
| [07_function_index.md](07_function_index.md) | Consolidated index of all ~170 documented functions with addresses, names, and descriptions |
| [08_known_issues.md](08_known_issues.md) | Remaining open questions and unresolved name conflicts (resolved items have been folded into docs 03–07) |

---

## Radare2 Project Files

The radare2 project state is saved in `gauntlet.r2` and `gauntlet_r2_database.txt` in the repository root. To load:

```bash
r2 -i gauntlet.r2 row76.bin
```

This loads all function names, flags, comments, and type definitions into radare2 for interactive analysis. All annotations — the base set plus the corrections and additions from the 2026-07-09 analysis session — are embedded directly in `gauntlet.r2`.

Note that the project file does not set up memory maps. For correct addresses across all three ROMs, open them mapped first:

```bash
r2 -n row9.bin
> o row10.bin 0x38000 r-x ; o row76.bin 0x40000 r-x
> e asm.arch=m68k ; e asm.cpu=68010 ; e asm.bits=32
> . gauntlet.r2
```
