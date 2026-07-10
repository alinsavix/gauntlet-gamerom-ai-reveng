# Gauntlet II RE — Known Issues and Remaining Unknowns

*Open questions only. All previously listed issues (misidentified functions, name conflicts, the maze RLE format, the dragon path table, `resolve_shot_hit`, EEPROM bits 5–7/13, the level-flags/`maze_pickup_config` bit layout, dialog tip boundaries, and the tile pattern → descriptor mapping) have been resolved by disassembly and folded into the other documents: see `03_game_rom_structure.md` (ROM layout, disassembly notes), `04_game_subsystems.md` (subsystem behavior), `05_data_reference.md` (RAM/ROM data, enums), and `07_function_index.md` (per-function corrections).*

---

## 1. Open Questions

### 1.1 Aux/color-ramp palette indexing (0x5D848 region)

The color-ramp blocks at 0x5D848–0x5D9E7 (13 × 32 bytes, one per tileset environment; see `05_data_reference.md` §5) are referenced from monster-region code at **0x41666**, which points at **0x5D978** — mid-block if the stride is 32 bytes from 0x5D848. The indexing scheme for that reference is untraced.

### 1.2 Unidentified word table at 0x5825E–0x5828B

46 bytes of word-like data immediately preceding the dialog tip pointer table (0x5815C) and records (0x5828C). Not part of the tip records; purpose unknown.

### 1.3 Secret trick check against value 0x5A

`resolve_shot_hit`'s supershot-on-treasure hook compares `0x904065` (trick task number) against **0x5A (90)**, which is not in the §3.17 Secret Tricks enum (values 0–17). Either the byte carries a different encoding in that state, or there is an undocumented trick/secret-room id.

### 1.4 Door lookup data at 0x5FBDC

18 bytes between the end of `pf_door_draw` and `door_vpos_sub3` (0x5FBEE). Neighboring door tables are verified; this block's exact use is untraced.

### 1.5 Per-player word array at 0x904A26

Read by `update_health_bar` (0x459A2): when `(0x904A26[p] & 0xF) < 8`, the entry is not 0xFFFF, and `0x9048C8[p]` ≠ 0, the health display palette is dimmed (−0x1000). Located immediately after the EEPROM settings word. Identity unknown — possibly a per-player health-warning threshold or join-slot state.

---

## 2. Unresolved Name Conflicts (GAME_ROM_KNOWN.md vs REPORT.md)

| Address | GAME_ROM_KNOWN.md Name | REPORT.md Name | Notes |
|---------|----------------------|----------------|-------|
| 0x904A9E | `dialog_timer` | `dialog_active` | Non-zero when dialog displayed; also counts down |
| 0x904B82 | `attract_title_count` | `continue_screen_active` | 1 when continue screen is showing |

---

## 3. Miscellaneous Notes

- Several RAM addresses in GAME_ROM_KNOWN.md have conflicting descriptions between sections (e.g., `0x904A66` appears twice with different descriptions: "possibly what part of the screen is visible" and "something to do with lobber shots").
- GAME_ROM_KNOWN.md's `0x904B7C` is labeled `attract_timer` but REPORT.md section 13 notes it is checked by `show_continue_screen` (must be ≠ 0xFFFF to show) and guesses it is `ram.continue_screen_inhibit`. These may coexist if the timer serves both purposes.
- REPORT.md section 13 notes `0x904066` (mob_anim array) may double as `ram.floor_anim_state[slot]` when read by `pf_floor_update` for type-0x3F floor animation state. (Verified related uses: `pf_door_draw` stores the door-neighbor mask in bits 10–13; `resolve_shot_hit` reads the victim player number from bits 15–10 and the movable-wall hit counter from bits 10+.)
- REPORT.md section 13 notes the type-0x6 tile in `mob_link` (stored in `0x9048A0/0x9048A2`) is not definitively identified — possibly a player start marker or trapped area.
