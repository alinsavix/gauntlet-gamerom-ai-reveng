"""Capture and annotate the MAME-derived book figures.

Produces, into book/img/:
  ch01_gameplay_annotated.png  - the visual vocabulary, over a real frame
  ch08_camera_close.png        - party together, camera centred on the midpoint
  ch08_camera_spread.png       - party at the rubber-band limit
  ch10_hud_column.png          - one fully populated info-panel column

Requirements: MAME 0.179, a `gaunt2` romset, and the era-correct plugins.
The plugins shipped with this MAME install are from a much newer release and
abort every launch, so extract matching ones from the MAME git tree:

    git archive mame0179 plugins | tar -x -C <scratch>

Set MAME_EXE / ROMPATH / PLUGINS below (or via the environment) to match.

Everything here rides the attract demo, which Chapter 15 establishes is the
real engine on recorded input. The frame numbers are fixed because a cold
boot replays identically; re-derive them with pass1-style logging if the
romset differs. The info-panel figure additionally pokes an inventory into
RAM and calls the game's own panel renderer, which is stated in its caption.
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG_DIR = os.path.join(REPO, "book", "img")

MAME_EXE = os.environ.get("MAME_EXE", r"C:\portable\MAME\mame64.exe")
ROMPATH = os.environ.get("GEX_MAME_ROMPATH", os.path.join(REPO, "ROMs", ".."))
PLUGINS = os.environ.get("MAME_PLUGINS", "")

# Demo frames, chosen from a logging pass: a crowd scene, the party at the
# camera's rubber-band limit, and the party back together. All are free of
# message boxes, and every live hero is on screen.
FRAME_CROWD, FRAME_SPREAD, FRAME_CLOSE = 8400, 6528, 8740

# Hero screen positions at those frames, from the MOB position arrays and the
# scroll shadows: screen_x = hpos/2 - scroll_x + 12, screen_y = 509 - vpos/2 - scroll_y.
HEROES = {
    FRAME_CROWD: [(99, 128, "red"), (132, 130, "blue"), (164, 130, "green")],
    FRAME_SPREAD: [(97, 121, "red"), (90, 197, "blue"), (143, 229, "green")],
    FRAME_CLOSE: [(106, 60, "red"), (126, 57, "green")],
}

WHITE = (255, 255, 255)
BLACK = (24, 24, 24)
RULE = (110, 110, 110)
MARK = (235, 40, 40)
COOL = (30, 110, 210)

SNAP_LUA = r"""
local mach = manager:machine()
local mem  = mach.devices[":maincpu"].spaces["program"]
local want = {}
for w in string.gmatch(FRAMES, "%d+") do want[tonumber(w)] = true end
local n, seen, total = 0, 0, 0
for _ in pairs(want) do total = total + 1 end
emu.register_frame_done(function()
    n = n + 1
    if mem:read_u16(0x904918) ~= 0xFFFD then return end   -- demo only
    if want[n] then
        mach:video():snapshot()
        seen = seen + 1
        print("SNAP frame=" .. n)
        if seen >= total then mach:exit() end
    end
end)
"""

# Let the demo build a real level with three joined heroes, then flip game_mode
# to normal play (DEMO is what suppresses the key/potion row), poke a full
# inventory for the blue Elf, and call the game's own panel rebuild.
HUD_LUA = r"""
local m   = manager:machine()
local mem = m.devices[":maincpu"].spaces["program"]
local cpu = m.devices[":maincpu"]
local TRAP, n, st, t = 0x904FF8, 0, "wait", 0
local function call(addr, arg)
    mem:write_u16(TRAP, 0x60FE)                    -- bra.s * : return trap
    local sp = cpu.state["SP"].value - 8
    mem:write_u32(sp + 4, arg)
    mem:write_u32(sp, TRAP)
    cpu.state["SP"].value = sp
    cpu.state["PC"].value = addr
end
emu.register_frame_done(function()
    n, t = n + 1, t + 1
    if st == "wait" then
        if mem:read_u16(0x904918) == 0xFFFD and n >= TARGET
           and mem:read_u16(0x904928) >= 3 then
            mem:write_u16(0x904918, 0x0000)        -- normal play
            mem:write_u8(0x90405B, 5)              -- player 1 keys
            mem:write_u8(0x904056, 4)              -- player 1 potions
            mem:write_u16(0x9048E2, 0x0F3B)        -- player 1 power-up bits
            mem:write_u16(0x904910, 6)             -- player 1 treasure multiplier
            mem:write_u16(0x9049DC, 1)             -- player 1 is IT
            call(0x452D0, 0xFFFFFFFF)              -- setup_infopanel(-1)
            st, t = "painted", 0
        end
    elseif st == "painted" and t > 6 then
        m:video():snapshot()
        print("SNAP frame=" .. n)
        m:exit()
    end
end)
"""


def font(size):
    for name in ("consola.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def run_mame(script_body, preamble, snapdir, seconds):
    """Run one headless-ish MAME pass and return its snapshots in order."""
    if not os.path.exists(MAME_EXE):
        sys.exit(f"MAME not found at {MAME_EXE}; set MAME_EXE")
    with tempfile.TemporaryDirectory() as tmp:
        body = os.path.join(tmp, "body.lua")
        boot = os.path.join(tmp, "boot.lua")
        with open(body, "w") as fh:
            fh.write(script_body)
        with open(boot, "w") as fh:
            fh.write(f'{preamble}\ndofile("{body.replace(os.sep, "/")}")\n')
        cmd = [MAME_EXE, "gaunt2", "-rompath", ROMPATH, "-window", "-nothrottle",
               "-sound", "none", "-artpath", os.path.join(tmp, "noart"),
               "-autoboot_script", boot, "-snapshot_directory", snapdir,
               "-seconds_to_run", str(seconds)]
        if PLUGINS:
            cmd += ["-pluginspath", PLUGINS]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    # Pair each snapshot with the frame the script announced, so nothing
    # depends on filename ordering.
    frames = [int(line.split("frame=")[1].split()[0])
              for line in proc.stdout.splitlines() if "frame=" in line]
    out = os.path.join(snapdir, "gaunt2")
    names = sorted(n for n in os.listdir(out) if n[0].isdigit())
    return {fr: Image.open(os.path.join(out, n)).convert("RGB")
            for fr, n in zip(frames, names)}


def scale(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def callout(d, anchor, target, text, f, side, color=BLACK):
    """Label at `anchor` with a leader line running from the edge of the text
    that faces the image, so the line never crosses its own words."""
    tw = d.textlength(text, font=f)
    tx = anchor[0] - tw if side == "left" else anchor[0]
    d.text((tx, anchor[1]), text, fill=color, font=f, anchor="lm")
    edge = (anchor[0] + 8, anchor[1]) if side == "left" else (anchor[0] - 8, anchor[1])
    d.line([edge, target], fill=color, width=2)
    d.ellipse([target[0] - 4, target[1] - 4, target[0] + 4, target[1] + 4],
              outline=color, width=2)


def ring(d, cx, cy, color=MARK, r=15, width=3):
    """Circle a feature; cx/cy are canvas pixels, not screen pixels."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=width)


def tag(d, xy, text, f, fg):
    """Label drawn on a solid plate so it stays legible over dark artwork."""
    w = d.textlength(text, font=f)
    x, y = xy
    d.rectangle([x - 5, y - 11, x + w + 5, y + 11], fill=WHITE, outline=fg)
    d.text((x, y), text, fill=fg, font=f, anchor="lm")


def frame_canvas(shot, k, left, right, top, bottom):
    canvas = Image.new("RGB", (shot.width * k + left + right,
                               shot.height * k + top + bottom), WHITE)
    canvas.paste(scale(shot, k), (left, top))
    d = ImageDraw.Draw(canvas)
    d.rectangle([left - 1, top - 1, left + shot.width * k, top + shot.height * k],
                outline=RULE)
    return canvas, d


def make_gameplay(shot):
    """ch01: the visual vocabulary, labelled over a real frame."""
    k, L, R, T, B = 2, 210, 232, 22, 16
    canvas, d = frame_canvas(shot, k, L, R, T, B)
    f = font(16)
    px = lambda x, y: (L + x * k, T + y * k)

    for x, y, _ in HEROES[FRAME_CROWD]:
        ring(d, *px(x, y), MARK)
    for x, y in ((196, 40), (150, 74), (206, 96)):
        ring(d, *px(x, y), COOL, r=13)

    callout(d, (L - 18, T + 60), px(34, 30), "the maze: walls and floor", f, "left")
    callout(d, (L - 18, T + 150), px(60, 74), "monsters, converging", f, "left", COOL)
    callout(d, (L - 18, T + 262), px(99, 128), "three heroes, one", f, "left", MARK)
    d.text((L - 18 - d.textlength("colour per position", font=f), T + 282),
           "colour per position", fill=MARK, font=f, anchor="lm")
    callout(d, (L + shot.width * k + 18, T + 60), px(292, 26), "info panel", f, "right")
    callout(d, (L + shot.width * k + 18, T + 246), px(288, 122),
            "the IT label", f, "right")
    callout(d, (L + shot.width * k + 18, T + 400), px(296, 228),
            "what a coin buys", f, "right")
    d.text((L, T + shot.height * k + 4),
           "One frame of the attract demo. The screen is a camera window onto a "
           "much larger maze.", fill=BLACK, font=font(14), anchor="lt")
    canvas.save(os.path.join(IMG_DIR, "ch01_gameplay_annotated.png"))
    print("wrote ch01_gameplay_annotated.png")


def make_camera(shot_close, shot_spread):
    """ch08: the camera with the party together and at its limit."""
    for shot, frame, name, note in (
        (shot_close, FRAME_CLOSE, "ch08_camera_close.png",
         "Two heroes back together after the party split. Their extent is "
         "small, so a single window holds them both and the camera has nearly "
         "caught up with the midpoint it steers toward."),
        (shot_spread, FRAME_SPREAD, "ch08_camera_spread.png",
         "Three heroes strung out, the lowest hard against the bottom edge of "
         "the maze window. Once the party's extent passes the camera's "
         "rubber-band limit the camera stops chasing the outlier, and the edge "
         "holds everyone in one view."),
    ):
        k, L, R, T, B = 3, 16, 16, 16, 88
        canvas, d = frame_canvas(shot, k, L, R, T, B)
        f = font(17)
        pts = HEROES[frame]
        for x, y, _ in pts:
            ring(d, L + x * k, T + y * k, MARK, r=22, width=3)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        cx, cy = L + mx * k, T + my * k
        d.line([(cx - 13, cy), (cx + 13, cy)], fill=COOL, width=3)
        d.line([(cx, cy - 13), (cx, cy + 13)], fill=COOL, width=3)
        tag(d, (cx + 22, cy), "midpoint the camera steers toward", f, COOL)
        if frame == FRAME_SPREAD:
            ey = pts[-1][1]
            d.line([(L, T + ey * k), (L + shot.width * k, T + ey * k)],
                   fill=MARK, width=2)
            tag(d, (L + 14, T + ey * k - 26), "hero held at the edge", f, MARK)
        y = T + shot.height * k + 8
        for line in wrap(note, 78):
            d.text((L, y), line, fill=BLACK, font=font(15), anchor="lt")
            y += 19
        canvas.save(os.path.join(IMG_DIR, name))
        print("wrote", name)


def wrap(text, width):
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def make_hud(hud_shot, crowd_shot):
    """ch10: one populated info-panel column, plus the IT label in situ."""
    k = 5
    col = scale(hud_shot.crop((224, 96, 336, 168)), k)
    inset = scale(crowd_shot.crop((252, 104, 336, 119)), 3)
    L, R, T, B = 250, 250, 20, 150
    canvas = Image.new("RGB", (col.width + L + R, col.height + T + B), WHITE)
    canvas.paste(col, (L, T))
    d = ImageDraw.Draw(canvas)
    d.rectangle([L - 1, T - 1, L + col.width, T + col.height], outline=RULE)
    f = font(16)
    px = lambda x, y: (L + (x - 224) * k, T + (y - 96) * k)

    callout(d, (L - 16, T + 24), px(243, 101), "power-up icons", f, "left")
    callout(d, (L - 16, T + 96), px(238, 108), "treasure multiplier", f, "left")
    callout(d, (L - 16, T + 160), px(250, 123), "keys carried", f, "left")
    callout(d, (L + col.width + 16, T + 24), px(290, 99), "class, in this", f, "right")
    d.text((L + col.width + 16, T + 44), "position's colour", fill=BLACK, font=f,
           anchor="lm")
    callout(d, (L + col.width + 16, T + 100), px(268, 114), "score", f, "right")
    callout(d, (L + col.width + 16, T + 136), px(315, 114), "health", f, "right")
    callout(d, (L + col.width + 16, T + 176), px(315, 123), "potions carried", f,
            "right")

    iy = T + col.height + 30
    canvas.paste(inset, (L, iy))
    d.rectangle([L - 1, iy - 1, L + inset.width, iy + inset.height], outline=RULE)
    d.text((L + inset.width + 14, iy + inset.height / 2),
           "and when this player is IT, the label\n"
           "is stamped between score and health", fill=BLACK, font=f, anchor="lm")
    y = iy + inset.height + 12
    for line in wrap("Left: the game's own panel renderer, called through the "
                     "debugger after an inventory was poked into RAM, so every "
                     "field is populated at once. Right: the IT label as the "
                     "attract demo draws it, untouched.", 92):
        d.text((L - 240, y), line, fill=BLACK, font=font(14), anchor="lt")
        y += 18
    canvas.save(os.path.join(IMG_DIR, "ch10_hud_column.png"))
    print("wrote ch10_hud_column.png")


def main():
    with tempfile.TemporaryDirectory() as snaps:
        a = run_mame(SNAP_LUA,
                     f'FRAMES="{FRAME_SPREAD} {FRAME_CROWD} {FRAME_CLOSE}"',
                     os.path.join(snaps, "a"), 200)
        b = run_mame(HUD_LUA, f"TARGET={FRAME_CROWD}", os.path.join(snaps, "b"), 200)
        missing = [f for f in (FRAME_SPREAD, FRAME_CROWD, FRAME_CLOSE) if f not in a]
        if missing or not b:
            sys.exit(f"MAME snapshots missing {missing}; check ROM path and plugins")
        crowd = a[FRAME_CROWD]
        make_gameplay(crowd)
        make_camera(a[FRAME_CLOSE], a[FRAME_SPREAD])
        make_hud(next(iter(b.values())), crowd)


if __name__ == "__main__":
    main()
