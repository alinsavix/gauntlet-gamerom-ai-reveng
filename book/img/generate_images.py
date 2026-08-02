"""Generate book images for chapters 1 and 4 using python-gex.

Outputs (into book/img/):
  ch04_tile_zoom.png     - key sprite + enlarged single tile with pixel values + palette strip
  ch04_dragon_tiles.png  - 4x4-tile dragon stamp with tile grid and T+n labels
  ch01_four_heroes.png   - the four heroes, idle facing down, name labels
"""
import os
import struct
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GEX_ROM_DIR", os.path.join(REPO, "ROMs"))
sys.path.insert(0, os.path.join(REPO, "python-gex", "src"))

from PIL import Image, ImageDraw, ImageFont

from gex.palettes import GAUNTLET_PALETTES
from gex.render import blank_image, get_parsed_tile, write_tile_to_image
from gex.roms import coderom_get_bytes

IMG_DIR = os.path.join(REPO, "book", "img")
os.makedirs(IMG_DIR, exist_ok=True)

WHITE = (255, 255, 255, 255)
BLACK = (20, 20, 20, 255)
GRAY = (150, 150, 150, 255)
LIGHTGRAY = (185, 185, 185, 255)
HILITE = (220, 40, 40, 255)


def font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def words_at(addr: int, count: int) -> list[int]:
    raw = coderom_get_bytes(addr, count * 2)
    return list(struct.unpack(f">{count}H", raw))


SHADOW_RGBA = (140, 140, 140, 255)


class _ShadowColor:
    """Stand-in palette entry: MOB pixel value 1 darkens the layer below;
    over a white page background that reads as mid-gray."""

    def to_rgba(self):
        return SHADOW_RGBA


def render_tiles(base: int, xt: int, yt: int, ptype: str, pnum: int,
                 trans0: bool = True, shadow1: bool = True) -> Image.Image:
    """Render consecutive tiles with transparency and gray shadow pixels."""
    pal = list(GAUNTLET_PALETTES[ptype][pnum])
    if shadow1:
        pal[1] = _ShadowColor()
    img = blank_image(8 * xt, 8 * yt)
    for idx, num in enumerate(range(base, base + xt * yt)):
        y, x = divmod(idx, xt)
        write_tile_to_image(img, get_parsed_tile(num), pal, trans0, x * 8, y * 8)
    return img


def upscale(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def on_white(img: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", img.size, WHITE)
    bg.alpha_composite(img)
    return bg


def luminance(rgba) -> float:
    return 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]


idle = words_at(0x58A4A, 32)


# ---------------------------------------------------------------------------
# ch04_tile_zoom.png
# ---------------------------------------------------------------------------

def make_tile_zoom():
    key_base = 2812  # key stamp: 2x2 tiles 2812..2815, base palette 1
    zoom_tilenum = 2813  # top-right tile: the key's ring
    ptype, pnum = "base", 1
    pal = GAUNTLET_PALETTES[ptype][pnum]

    # Panel A: full key sprite (2x2 tiles) at 8x, tile grid, highlight top-right
    key_big = upscale(on_white(render_tiles(key_base, 2, 2, ptype, pnum)), 8)  # 128px
    d = ImageDraw.Draw(key_big)
    for i in (0, 64, 128):
        d.line([(i, 0), (i, 127)], fill=LIGHTGRAY, width=1)
        d.line([(0, i), (127, i)], fill=LIGHTGRAY, width=1)
    d.rectangle([64, 0, 127, 63], outline=HILITE, width=3)

    # Panel B: the ring tile at 32x with per-pixel hex values
    scale = 32
    tile = get_parsed_tile(zoom_tilenum)
    tile_big = upscale(on_white(render_tiles(zoom_tilenum, 1, 1, ptype, pnum)), scale)
    d = ImageDraw.Draw(tile_big)
    f = font(14)
    for j in range(8):
        for i in range(8):
            v = tile[j][i]
            if v == 0:
                text_col = LIGHTGRAY
            elif v == 1:
                text_col = WHITE
            else:
                text_col = BLACK if luminance(pal[v].to_rgba()) > 110 else WHITE
            d.text((i * scale + scale // 2, j * scale + scale // 2),
                   f"{v:X}", fill=text_col, font=f, anchor="mm")
    for i in range(9):
        d.line([(i * scale, 0), (i * scale, 255)], fill=LIGHTGRAY, width=1)
        d.line([(0, i * scale), (255, i * scale)], fill=LIGHTGRAY, width=1)

    # Panel C: palette strip
    sw = 32
    strip = Image.new("RGBA", (16 * sw, sw + 22), WHITE)
    d = ImageDraw.Draw(strip)
    f_small = font(13)
    for v in range(16):
        x0 = v * sw
        if v == 0:
            for cy in range(0, sw, 8):
                for cx in range(0, sw, 8):
                    c = (205, 205, 205, 255) if (cx // 8 + cy // 8) % 2 else WHITE
                    d.rectangle([x0 + cx, cy, x0 + cx + 8, cy + 8], fill=c)
        elif v == 1:
            d.rectangle([x0, 0, x0 + sw, sw], fill=SHADOW_RGBA)
        else:
            d.rectangle([x0, 0, x0 + sw, sw], fill=pal[v].to_rgba())
        d.rectangle([x0, 0, x0 + sw, sw], outline=GRAY, width=1)
        d.text((x0 + sw // 2, sw + 11), f"{v:X}", fill=BLACK, font=f_small, anchor="mm")

    # Compose: panels side by side, labels BELOW each panel
    pad = 24
    label_h = 28
    width = max(pad + 128 + pad + 256 + pad, pad + strip.width + pad)
    height = pad + 256 + label_h + pad // 2 + strip.height + label_h + pad // 2
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    f_label = font(15)

    ax, ay = pad, pad + (256 - 128) // 2
    out.alpha_composite(key_big, (ax, ay))
    d.text((ax + 64, pad + 256 + label_h // 2), "the key, 2×2 tiles",
           fill=BLACK, font=f_label, anchor="mm")

    bx = pad + 128 + pad
    out.alpha_composite(tile_big, (bx, pad))
    d.text((bx + 128, pad + 256 + label_h // 2), "ring tile, pixel values 0–F",
           fill=BLACK, font=f_label, anchor="mm")

    cy = pad + 256 + label_h + pad // 2
    out.alpha_composite(strip, (pad, cy))
    d.text((pad + strip.width // 2, cy + strip.height + label_h // 2 - 6),
           "palette entries 0–F (0 = transparent, 1 = shadow)",
           fill=BLACK, font=f_label, anchor="mm")

    out.convert("RGB").save(os.path.join(IMG_DIR, "ch04_tile_zoom.png"))
    print("wrote ch04_tile_zoom.png")


# ---------------------------------------------------------------------------
# ch04_dragon_tiles.png
# ---------------------------------------------------------------------------

def make_dragon_tiles():
    base = 8448  # dragon stamp, 4x4 tiles, base palette 8, per item_stamps.jsonc
    big = upscale(on_white(render_tiles(base, 4, 4, "base", 8)), 10)  # 320px
    d = ImageDraw.Draw(big)
    cell = 80
    for i in range(5):
        d.line([(i * cell, 0), (i * cell, big.height - 1)], fill=GRAY, width=1)
        d.line([(0, i * cell), (big.width - 1, i * cell)], fill=GRAY, width=1)
    f = font(15)
    for n in range(16):
        y, x = divmod(n, 4)
        label = "T" if n == 0 else f"T+{n}"
        tx, ty = x * cell + 5, y * cell + 4
        bbox = d.textbbox((tx, ty), label, font=f)
        d.rectangle([bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1],
                    fill=(255, 255, 255, 230))
        d.text((tx, ty), label, fill=BLACK, font=f)
    big.convert("RGB").save(os.path.join(IMG_DIR, "ch04_dragon_tiles.png"))
    print("wrote ch04_dragon_tiles.png")


# ---------------------------------------------------------------------------
# ch01_four_heroes.png
# ---------------------------------------------------------------------------

def make_four_heroes():
    # anim_table_idle 0x58A4A: 4 chars x 8 dirs, one word each; players are
    # 3x3-tile sprites (word strides of 27 = 3 walk frames x 9 tiles, and the
    # ghost table's stride of 9 with gex xsize/ysize 3 confirm the layout).
    # Direction order: UP, UP-RT, RT, DN-RT, DN, DN-LT, LT, UP-LT
    DIR_DOWN = 4
    heroes = [
        ("Warrior", "warrior", 0),   # red
        ("Valkyrie", "valkyrie", 1), # blue
        ("Wizard", "wizard", 2),     # yellow
        ("Elf", "elf", 3),           # green
    ]
    factor = 7
    sprite_px = 24 * factor  # 168
    pad = 24
    gap = 24
    label_h = 32
    width = pad * 2 + sprite_px * 4 + gap * 3
    height = pad + sprite_px + label_h + pad // 2
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    f = font(19)
    for i, (name, ptype, pnum) in enumerate(heroes):
        tilenum = idle[i * 8 + DIR_DOWN]
        print(f"{name}: idle-down tile {tilenum} (0x{tilenum:X}), palette {ptype}[{pnum}]")
        big = upscale(render_tiles(tilenum, 3, 3, ptype, pnum), factor)
        x = pad + i * (sprite_px + gap)
        canvas = Image.new("RGBA", (sprite_px, sprite_px), WHITE)
        canvas.alpha_composite(big)
        out.alpha_composite(canvas, (x, pad))
        d.text((x + sprite_px // 2, pad + sprite_px + label_h // 2),
               name, fill=BLACK, font=f, anchor="mm")
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch01_four_heroes.png"))
    print("wrote ch01_four_heroes.png")


# ---------------------------------------------------------------------------
# ch10_anim_frames.png
# ---------------------------------------------------------------------------

def make_anim_frames():
    # anim_table_walking 0x58A8A: 4 chars x 8 dirs x 4 frames (char*32 + dir*4 + frame)
    # anim_table_fighting 0x5884A: 4 chars x 8 dirs x 8 frames (char*64 + dir*8 + frame)
    # Direction order: UP, UP-RT, RT, DN-RT, DN, DN-LT, LT, UP-LT
    walking = words_at(0x58A8A, 128)
    fighting = words_at(0x5884A, 256)
    char = 0  # Warrior
    ptype, pnum = "warrior", 0
    factor = 5
    spr = 24 * factor  # 120
    pad = 20
    gap = 8
    label_w = 130
    rows = [
        ("walk down", [walking[char * 32 + 4 * 4 + f] for f in range(4)]),
        ("walk right", [walking[char * 32 + 2 * 4 + f] for f in range(4)]),
        ("walk up", [walking[char * 32 + 0 * 4 + f] for f in range(4)]),
        ("fight down", [fighting[char * 64 + 4 * 8 + f] for f in range(8)]),
    ]
    maxcols = max(len(tiles) for _, tiles in rows)
    width = pad + label_w + maxcols * (spr + gap) + pad
    height = pad + len(rows) * (spr + gap) + 26 + pad // 2
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    f = font(16)
    f_small = font(13)
    for r, (label, tiles) in enumerate(rows):
        y = pad + r * (spr + gap)
        d.text((pad, y + spr // 2), label, fill=BLACK, font=f, anchor="lm")
        for c, tilenum in enumerate(tiles):
            x = pad + label_w + c * (spr + gap)
            canvas = Image.new("RGBA", (spr, spr), WHITE)
            canvas.alpha_composite(upscale(render_tiles(tilenum, 3, 3, ptype, pnum), factor))
            out.alpha_composite(canvas, (x, y))
    for c in range(maxcols):
        x = pad + label_w + c * (spr + gap)
        d.text((x + spr // 2, height - 16), f"frame {c}",
               fill=BLACK, font=f_small, anchor="mm")
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch10_anim_frames.png"))
    print("wrote ch10_anim_frames.png")


# ---------------------------------------------------------------------------
# ch11_monster_roster.png
# ---------------------------------------------------------------------------

# A monster's MOB palette number is the low nibble of its horizontal-position
# word (doc/01_hardware.md 8.2), taken from mazeobj_hsize_tier_tbl (0x5864C).
# The live range is base-2 .. base, which is also its remaining health, so
# python-gex's per-monster stamp palette is a full-strength monster.
DIR_DOWN = 4  # UP, UP-RT, RT, DN-RT, DN, DN-LT, LT, UP-LT

MONSTER_ROSTER = [
    ("Ghost", "ghost"),
    ("Grunt", "grunt"),
    ("Demon", "demon"),
    ("Lobber", "lobber"),
    ("Sorcerer", "sorcerer"),
    ("Death", "death"),
    ("Acid puddle", "acid"),
    ("IT", "it"),
    ("Grunt generator", "generator1"),
]


def stamp_image(key: str) -> Image.Image:
    """Render one of python-gex's verified maze-object stamps."""
    from gex.items import item_get_stamp

    s = item_get_stamp(key)
    width = s.width
    height = len(s.numbers) // width
    pal = list(GAUNTLET_PALETTES[s.ptype][s.pnum])
    pal[1] = _ShadowColor()
    img = blank_image(8 * width, 8 * height)
    for idx, num in enumerate(s.numbers):
        y, x = divmod(idx, width)
        write_tile_to_image(img, get_parsed_tile(num), pal, True, x * 8, y * 8)
    return img


def cell_with(img: Image.Image, box: int, factor: int) -> Image.Image:
    """Centre an upscaled sprite in a square white cell."""
    big = upscale(img, factor)
    canvas = Image.new("RGBA", (box, box), WHITE)
    canvas.alpha_composite(big, ((box - big.width) // 2, (box - big.height) // 2))
    return canvas


def sprite_cell(tilenum: int, pnum: int, factor: int, size: int = 3,
                ptype: str = "base") -> Image.Image:
    px = 8 * size * factor
    canvas = Image.new("RGBA", (px, px), WHITE)
    canvas.alpha_composite(upscale(render_tiles(tilenum, size, size, ptype, pnum),
                                   factor))
    return canvas


def make_monster_roster():
    from gex.items import item_get_stamp

    factor = 5
    spr = 24 * factor
    pad, gap, label_h = 20, 16, 30
    cols = 5
    rows = (len(MONSTER_ROSTER) + cols - 1) // cols
    width = pad * 2 + cols * spr + (cols - 1) * gap
    height = pad + rows * (spr + label_h + gap)
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    f = font(17)
    for i, (name, key) in enumerate(MONSTER_ROSTER):
        r, c = divmod(i, cols)
        x = pad + c * (spr + gap)
        y = pad + r * (spr + label_h + gap)
        s = item_get_stamp(key)
        print(f"{name}: stamp {key} base tile {s.numbers[0]}, MOB palette {s.pnum}")
        out.alpha_composite(cell_with(stamp_image(key), spr, factor), (x, y))
        d.text((x + spr // 2, y + spr + label_h // 2), name,
               fill=BLACK, font=f, anchor="mm")
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch11_monster_roster.png"))
    print("wrote ch11_monster_roster.png")


# ---------------------------------------------------------------------------
# ch11_tier_palettes.png
# ---------------------------------------------------------------------------

def make_tier_palettes():
    """A grunt at each of its three health tiers. Health *is* the palette."""
    factor = 7
    spr = 24 * factor
    pad, gap, label_h = 20, 26, 52
    tiers = [("tier 1\npalette 2", 2), ("tier 2\npalette 3", 3), ("tier 3\npalette 4", 4)]
    width = pad * 2 + 3 * spr + 2 * gap
    height = pad + spr + label_h + pad // 2
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    f = font(16)
    tilenum = 2529  # grunt stamp base tile, per python-gex item_stamps
    for i, (label, pnum) in enumerate(tiers):
        x = pad + i * (spr + gap)
        out.alpha_composite(sprite_cell(tilenum, pnum, factor), (x, pad))
        d.text((x + spr // 2, pad + spr + label_h // 2 - 2), label,
               fill=BLACK, font=f, anchor="mm", align="center")
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch11_tier_palettes.png"))
    print("wrote ch11_tier_palettes.png")


# ---------------------------------------------------------------------------
# ch12_dragon_segments.png
# ---------------------------------------------------------------------------

def make_dragon_segments():
    """The sleeping dragon stamp with its 2x2 block of MOB slots marked."""
    factor = 11
    big = on_white(render_tiles(8448, 4, 4, "base", 8))
    big = upscale(big, factor)
    d = ImageDraw.Draw(big)
    half = big.width // 2
    d.line([(half, 0), (half, big.height - 1)], fill=HILITE, width=3)
    d.line([(0, half), (big.width - 1, half)], fill=HILITE, width=3)
    f = font(17)
    for n, (cx, cy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
        label = "head" if n == 0 else f"segment {n}"
        tx, ty = cx * half + 8, cy * half + 6
        bbox = d.textbbox((tx, ty), label, font=f)
        d.rectangle([bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2],
                    fill=(255, 255, 255, 235))
        d.text((tx, ty), label, fill=HILITE, font=f)
    big.convert("RGB").save(os.path.join(IMG_DIR, "ch12_dragon_segments.png"))
    print("wrote ch12_dragon_segments.png")


# ---------------------------------------------------------------------------
# ch12_thief_mugger.png
# ---------------------------------------------------------------------------

def make_thief_mugger():
    """Thief and mugger, facing down. main_start_thief adds 0 or 1 to the
    horizontal-position word, so they differ by one MOB palette number."""
    factor = 8
    spr = 24 * factor
    pad, gap, label_h = 22, 40, 32
    pairs = [("Thief", 0x58D1A, 0), ("Mugger", 0x58DEC, 1)]
    width = pad * 2 + 2 * spr + gap
    height = pad + spr + label_h + pad // 2
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    f = font(19)
    for i, (name, table, pnum) in enumerate(pairs):
        tilenum = words_at(table + DIR_DOWN * 2, 1)[0]
        print(f"{name}: idle-down tile {tilenum} (0x{tilenum:X}), MOB palette {pnum}")
        x = pad + i * (spr + gap)
        out.alpha_composite(sprite_cell(tilenum, pnum, factor), (x, pad))
        d.text((x + spr // 2, pad + spr + label_h // 2), name,
               fill=BLACK, font=f, anchor="mm")
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch12_thief_mugger.png"))
    print("wrote ch12_thief_mugger.png")


# ---------------------------------------------------------------------------
# ch13_secret_rooms.png / ch13_treasure_room.png
# ---------------------------------------------------------------------------

def render_maze(maze_num: int) -> Image.Image:
    """Render one stored maze via python-gex's validated decoder/renderer."""
    import tempfile

    from gex.mazedecode import maze_decompress
    from gex.pfrender import genpfimage
    from gex.roms import slapstic_read_maze

    maze = maze_decompress(slapstic_read_maze(maze_num),
                           allow_missing_delimiter=maze_num == 116)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"maze{maze_num}.png")
        genpfimage(maze, path)
        return Image.open(path).convert("RGBA")


def make_secret_rooms():
    """The two secret-room layouts, side by side."""
    pad, gap, label_h = 16, 24, 34
    left = render_maze(115)
    right = render_maze(116)
    h = max(left.height, right.height)
    width = pad * 2 + left.width + gap + right.width
    height = pad + h + label_h
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    f = font(17)
    out.alpha_composite(left, (pad, pad))
    out.alpha_composite(right, (pad + left.width + gap, pad))
    d.text((pad + left.width // 2, pad + h + label_h // 2 - 4),
           "layout 115 (first seven challenges)", fill=BLACK, font=f, anchor="mm")
    d.text((pad + left.width + gap + right.width // 2, pad + h + label_h // 2 - 4),
           "layout 116 (last seven challenges)", fill=BLACK, font=f, anchor="mm")
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch13_secret_rooms.png"))
    print("wrote ch13_secret_rooms.png")


def make_treasure_room():
    """Treasure room T1 (maze 104): treasure everywhere, exits on every side."""
    img = render_maze(104)
    pad = 16
    out = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), WHITE)
    out.alpha_composite(img, (pad, pad))
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch13_treasure_room.png"))
    print("wrote ch13_treasure_room.png")


# ---------------------------------------------------------------------------
# ch15_demo_maze.png
# ---------------------------------------------------------------------------

def make_demo_maze():
    """Maze 102, the layout the attract demo always plays."""
    img = render_maze(102)
    pad = 16
    out = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), WHITE)
    out.alpha_composite(img, (pad, pad))
    out.convert("RGB").save(os.path.join(IMG_DIR, "ch15_demo_maze.png"))
    print("wrote ch15_demo_maze.png")


# ---------------------------------------------------------------------------
# ch15_demo_script.png
# ---------------------------------------------------------------------------

DEMO_PTR_TBL = 0x58098
DEMO_STREAM_END = 0x5828C

IDLE_C = (208, 210, 214, 255)
MOVE_C = (70, 120, 200, 255)
FIRE_C = (215, 120, 40, 255)
MAGIC_C = (150, 80, 185, 255)
CAPTION_C = (30, 30, 30, 255)

ARROWS = {0x80: "↑", 0x40: "↓", 0x20: "←", 0x10: "→"}


def demo_stream_bounds() -> list[tuple[int, int]]:
    """Per-player (start, end) from the ROM pointer table plus the region end."""
    starts = [struct.unpack(">I", coderom_get_bytes(DEMO_PTR_TBL + i * 4, 4))[0]
              for i in range(4)]
    ends = sorted(starts + [DEMO_STREAM_END])
    return [(s, ends[ends.index(s) + 1]) for s in starts]


def demo_records(start: int, end: int) -> list[tuple[int, int]]:
    raw = coderom_get_bytes(start, end - start)
    return [(raw[i], raw[i + 1]) for i in range(0, len(raw), 2)]


def demo_events(start: int, end: int) -> list[dict]:
    """Flatten one stream into timed events on its own script clock."""
    out, t = [], 0
    for dur, arg in demo_records(start, end):
        if dur == 0xFF:
            out.append({"t": t, "kind": "caption", "arg": arg})
        elif dur == 0xFE:
            out.append({"t": t, "kind": "join", "player": arg & 0xF,
                        "cls": arg >> 4})
        else:
            out.append({"t": t, "kind": "hold", "dur": dur, "input": arg})
            t += dur
    return out


def make_demo_script():
    """The recorded attract-demo input, drawn on its own script clock."""
    bounds = demo_stream_bounds()
    ev = {p: demo_events(*bounds[p]) for p in range(4)}

    # Player 1 runs from frame 0; the others start where its join records fire.
    offset = {1: 0}
    for e in ev[1]:
        if e["kind"] == "join":
            offset[e["player"]] = e["t"]
    rows = [p for p in (1, 0, 3) if p in offset]

    span = max(offset[p] + sum(e["dur"] for e in ev[p] if e["kind"] == "hold")
               for p in rows)
    px_per_frame = 0.30
    pad, lab_w, row_h, gap = 16, 132, 34, 16
    plot_w = int(span * px_per_frame) + 2
    width = pad * 2 + lab_w + plot_w
    height = pad + len(rows) * (row_h + gap) + 74
    out = Image.new("RGBA", (width, height), WHITE)
    d = ImageDraw.Draw(out)
    fs, fa = font(15), font(16)

    names = {0: "red Wizard", 1: "blue Elf", 3: "green Warrior"}
    for r, p in enumerate(rows):
        top = pad + r * (row_h + gap)
        d.text((pad + lab_w - 10, top + row_h // 2), names[p], fill=BLACK,
               font=fs, anchor="rm")
        x0 = pad + lab_w
        for e in ev[p]:
            if e["kind"] != "hold":
                if e["kind"] == "caption":
                    x = x0 + (offset[p] + e["t"]) * px_per_frame
                    d.line([(x, top - 6), (x, top + row_h + 4)],
                           fill=CAPTION_C, width=1)
                    d.ellipse([x - 3, top - 9, x + 3, top - 3], fill=CAPTION_C)
                continue
            inp = e["input"]
            moving = (inp & 0xF0) != 0xF0
            fire, magic = not inp & 0x02, not inp & 0x01
            color = (MAGIC_C if magic else FIRE_C if fire else
                     MOVE_C if moving else IDLE_C)
            xa = x0 + (offset[p] + e["t"]) * px_per_frame
            xb = xa + e["dur"] * px_per_frame
            d.rectangle([xa, top, max(xb - 1, xa + 1), top + row_h], fill=color)
            if xb - xa >= 11:
                glyph = "".join(a for bit, a in ARROWS.items() if not inp & bit)
                if glyph:
                    d.text(((xa + xb) / 2, top + row_h / 2), glyph,
                           fill=WHITE, font=fa, anchor="mm")

    axis = pad + len(rows) * (row_h + gap) - gap + 12
    x0 = pad + lab_w
    d.line([(x0, axis), (x0 + span * px_per_frame, axis)], fill=GRAY, width=1)
    for sec in range(0, int(span / 60) + 1, 10):
        x = x0 + sec * 60 * px_per_frame
        d.line([(x, axis - 4), (x, axis + 4)], fill=GRAY, width=1)
        d.text((x, axis + 16), f"{sec}s", fill=BLACK, font=fs, anchor="mm")
    key = [("joystick held", MOVE_C), ("Fire", FIRE_C), ("Magic", MAGIC_C),
           ("nothing pressed", IDLE_C)]
    x = x0
    for text, color in key:
        d.rectangle([x, axis + 27, x + 13, axis + 40], fill=color)
        d.text((x + 19, axis + 34), text, fill=BLACK, font=fs, anchor="lm")
        x += 26 + d.textlength(text, font=fs)
    d.text((x0, axis + 56),
           "Script clock only: a caption box (●) freezes every stream while "
           "it is on screen.", fill=BLACK, font=fs, anchor="lm")

    out.convert("RGB").save(os.path.join(IMG_DIR, "ch15_demo_script.png"))
    print("wrote ch15_demo_script.png")


make_tile_zoom()
make_dragon_tiles()
make_four_heroes()
make_anim_frames()
make_monster_roster()
make_tier_palettes()
make_dragon_segments()
make_thief_mugger()
make_secret_rooms()
make_treasure_room()
make_demo_maze()
make_demo_script()
