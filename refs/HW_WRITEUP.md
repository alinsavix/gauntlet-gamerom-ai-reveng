# Gauntlet Hardware Analysis — Software RE Reference

## CPU & Address Space

- Main CPU: Motorola 68010

---

## Memory Map (Main CPU)

| Address      | Contents                        |
|--------------|---------------------------------|
| `0x900000`   | Playfield RAM (64x64 words)     |
| `0x902000`   | MOB Picture (tile index)        |
| `0x902800`   | MOB Horizontal Position         |
| `0x903000`   | MOB Vertical Position + Size    |
| `0x903800`   | MOB Link (forward linked list)  |
| `0x904066`   | MOB Backward Link (SW only)     |
| `0x905000`   | Alphanumeric (text) RAM         |
| `0x905f6e`   | Playfield vertical scroll reg   |
| `0x905f80`   | MOB linked list heads (64 words)|
| `0x910000`   | Color/Palette RAM               |
| `0x930000`   | Playfield horizontal scroll reg |

---

## Display Overview

- Resolution: **336x240**, 60 Hz
- Playfield (maze) is **512x512 pixels**; only ~240x240 is visible at once
- Scroll position controlled by registers at `0x905f6e` (vertical) and `0x930000` (horizontal)
- Two rendering layers (bottom to top):
  1. **Playfield** — the maze (walls, floor, doors)
  2. **Alphanumeric** — text overlay (scores, messages); can be transparent or opaque per-character

---

## Tiles

- Each tile is **8x8 pixels**, **4 bits per pixel** (16 colors per tile)
- Tile data is stored in graphics ROMs, split across 4 ROM chips (one per color bit plane: PLANE 0–3)
- Tile color indices index into **palette RAM** at `0x910000`

---

## Palette / Color RAM (`0x910000`)

Each color entry is **2 bytes** (16-bit word): 4 bits each for I (Intensity), R, G, B. Actual output = I * channel (0–225 range).

Total: **768 color entries**, 2 bytes each.

| Color Index Range | Type                | Layout                          |
|-------------------|---------------------|---------------------------------|
| 0 – 255           | Alphanumeric (text) | 2 banks × 16 palettes × 4 colors|
| 256 – 511         | MOBs (sprites)      | 16 palettes × 16 colors         |
| 512 – 639         | Playfield Shadow    | 8 palettes × 16 colors          |
| 640 – 767         | Playfield           | 8 palettes × 16 colors          |

**To get RAM byte offset:** multiply color index by 2.

### Color Index Formulas

| Layer         | Formula                                                              |
|---------------|----------------------------------------------------------------------|
| Alphanumeric  | `(palette_bank * 128) + (palette_number * 4) + pixel_color`         |
| MOB           | `256 + (palette * 16) + pixel_color`                                 |
| Playfield     | `640 + (palette * 16) + pixel_color` *(index within color RAM)*      |

> Note: The "Playfield Shadow" palette (512–639) appears to mirror the Playfield palette but at half intensity. Used when a MOB pixel has color index 1 (see MOB shadow behavior below).

---

## Playfield RAM (`0x900000`)

Layout: **64×64 grid** of 16-bit words, stored **column-first**:
- Index = `column * 64 + row`

Each word:

| Bits  | Meaning                                      |
|-------|----------------------------------------------|
| 15    | Horizontal flip (apparently unused in Gauntlet)|
| 14–12 | Palette number (0–7, indexes into Playfield palettes starting at color 640) |
| 11–0  | Tile number (must be in first 4096 tiles)    |

---

## MOBs (Sprites) — 1024 total

Each MOB is described by 4 parallel arrays in video RAM. MOB `n` is at offset `n*2` in each array.

### MOB Picture (`0x902000`)

| Bits  | Meaning                                                    |
|-------|------------------------------------------------------------|
| 14–0  | Tile number for **upper-left corner** of MOB               |
| 15    | Not used by hardware; used as a **software flag**          |

Tiles for a W×H MOB starting at tile T are laid out sequentially in row-major order:
```
T,   T+1, ..., T+W-1
T+W, T+W+1, ..., T+2W-1
...
```

### MOB Horizontal Position (`0x902800`)

| Bits  | Meaning                                    |
|-------|--------------------------------------------|
| 15–6  | Horizontal position on playfield (0–511)   |
| 5–4   | Software-only flags                        |
| 3–0   | Palette number (0–15, into MOB palettes)   |

### MOB Vertical Position (`0x903000`)

| Bits  | Meaning                                                           |
|-------|-------------------------------------------------------------------|
| 15–6  | Vertical position on playfield (0–511)                            |
| 5–3   | Horizontal size in tiles minus 1 (0 = 1 tile, 7 = 8 tiles)       |
| 2–0   | Vertical size in tiles minus 1 (0 = 1 tile, 7 = 8 tiles)         |

### MOB Link (`0x903800`)

| Bits  | Meaning                                                        |
|-------|----------------------------------------------------------------|
| 9–0   | MOB ID of next MOB in linked list (0 = end of list)            |
| 15–10 | Software-only                                                  |

- Linked list heads: 64 words at `0x905f80`, one per 8-pixel vertical band of the playfield
- Each band's list contains MOBs whose Y position falls in that scanline range
- Used by **software** for collision detection; uncertain if hardware follows these lists
- A backward-link table exists at `0x904066` but is believed to be software-only

### MOB Pixel Special Cases

| Pixel color index | Behavior                                                      |
|-------------------|---------------------------------------------------------------|
| 0                 | **Transparent** — shows layer below                           |
| 1                 | **Shadow** — subtracts 128 from the underlying playfield pixel|
| 2–15              | Normal — looks up color in MOB palette                        |

---

## Alphanumeric (Text) RAM (`0x905000`)

- Screen grid: **64×30 characters** (only left 42 columns are displayed)
- 1 word per character, 128 bytes per row

Each word:

| Bits  | Meaning                                                         |
|-------|-----------------------------------------------------------------|
| 15    | **Opaque flag** — if 1, color 0 is solid; if 0, color 0 is transparent |
| 14    | Palette bank (extra palette select bit)                         |
| 13–10 | Palette number (0–15)                                           |
| 9–0   | Character number (0–1023)                                       |

Character pixel data is stored in a dedicated ROM, not accessible by the main CPU. Each scanline of a character is **2 bytes**, deinterlaced into 2 bitplanes:
```
Raw bytes:   byte1=ABCDabcd  byte2=EFGHefgh
Bitplane 0:  abcdefgh
Bitplane 1:  ABCDEFGH
```

> The "black screen" between levels is the text layer filled with **opaque space characters**, not a disabled playfield.

---

## Layer Priority (highest to lowest)

1. Alphanumeric with opaque color 0 (bit 15 = 1)
2. Alphanumeric non-transparent pixels (color != 0, or bit 15 = 1)
3. MOBs (non-transparent pixels, color index != 0)
4. Playfield

---

## Software Notes

- The SLAPSTIC chip (sheet 4) performs bank switching for maze ROMs, it is triggered by the CPU accessing special addresses.
- The 6502 sound CPU is accessed via shared RAM; the communication protocol is software-defined.
