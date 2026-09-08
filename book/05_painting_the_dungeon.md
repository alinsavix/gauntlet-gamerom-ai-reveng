# 5. Painting the dungeon

The screen can be full of moving monsters while the floor scrolls beneath
them and four sets of scores remain still at the right. Behind that picture
is a Motorola 68010 running at about 7.16 MHz. That is modest power for
deciding the game, never mind drawing it.

The monitor displays 336 by 240 pixels about sixty times a second: nearly
five million visible pixels per second. An instruction takes several processor
clock cycles. Asking this CPU to calculate and write every displayed pixel
would consume more than the available time before any monster moved.

The game avoids that job. The CPU describes the picture in shared memory;
specialized video circuitry repeatedly turns the description into pixels.
Moving a ghost principally changes its position numbers, not a ghost-shaped
patch of a screen-sized painting.

## How much picture fits in one number?

The basic piece of maze and sprite artwork is an eight-by-eight-pixel
**tile** stored in graphics ROM. ROM holds fixed data; RAM can be changed
while the game runs. The CPU writes tile numbers into video RAM, and the
video hardware fetches the corresponding artwork directly from its ROMs.
The CPU need not inspect the drawing of a key to request that key's tiles.

Each tile pixel supplies a value from zero to fifteen rather than an
intrinsic color. A **palette**, a small color table in RAM, supplies the
color for that value.

![A key, its enlarged tile of numbered pixels, and the palette supplying its colors](img/ch04_tile_zoom.png)

*Follow one numbered square in the enlargement to the matching palette
entry below. The number belongs to the artwork; the displayed color comes
from a separate table.*

Change the palette and the same art changes appearance. That is how four
player colors can share a character's drawings, and how a monster's strength
can change its color. Editing color entries can also animate a transporter
without changing its tile numbers. The picture has several independent
controls: which drawing, which colors, and where it appears.

## Three layers instead of one painting

The bottom layer is the **playfield**, a grid of sixty-four by sixty-four
tiles. At eight pixels per tile, that describes a 512-pixel-square world.
The game's larger, sixteen-pixel maze cell occupies four playfield tiles.
Opening a door means updating a small block of this grid, not repainting
the entire visible dungeon.

Above it are **motion objects**, Atari's term for sprites, usually shortened
to MOBs. Each says where to draw, which tile begins its artwork, which palette
to use, and how many tiles wide and tall it is. Successive tiles form the
larger rectangle. A hero's three-by-three-tile picture is twenty-four pixels
wide, so its art can overhang a sixteen-pixel maze cell.

The top layer is **alpha**, short for alphanumerics: the character grid used
for scores and messages. Its characters have four pixel values rather than
sixteen. A character can have a transparent background, allowing letters to
float above the maze, or an opaque one that hides everything underneath.

That last option explains the between-level curtain. Fill the play area
with opaque blank characters and it goes dark, although the underlying
playfield and sprites still exist. Rewrite the maze behind that curtain,
then make the blanks transparent again. The display need not be shut down
to conceal construction.

## Which layer wins?

At a given screen position, visible alpha ink or an opaque alpha background
takes precedence. Otherwise a normal MOB pixel supplies the sprite color;
where no visible sprite pixel intervenes, the playfield shows.

Two MOB pixel values receive special treatment. Zero is transparent, giving
the rectangular sprite its irregular silhouette. One requests the shadow
version of the underlying **playfield** color. It is not a gray blob painted
over whatever happens to be below.

![Three Warrior renderings isolating the pixels that cast a shadow](img/ch04_shadow.png)

*Left: shadow pixels marked red. Center: those pixels omitted. Right: the
floor beneath them uses its darker palette. The shading follows the floor's
colors rather than replacing them with a single sprite color.*

The game prepares that darker palette by lowering color intensity. Full
intensity becomes roughly half intensity, though the actual operation is
an intensity subtraction rather than halving every red, green, and blue
value. Small color-table work supplies shadows across the whole maze.

## Why does scrolling cost so little?

The playfield grid remains in place while two scroll values select the
visible window. The video hardware applies the corresponding relationship
to motion objects; the alpha score panel remains screen-fixed. The CPU
changes the view's origin instead of copying a new screenful of floor.

There are thus two quite different questions behind a ghost crossing a
corridor: what does the game change about the ghost, and how does the
hardware show the result? The next chapter follows the first question into
the same tables that have just supplied the picture.

## For the full chapter

Add a cutaway of one screen position resolving alpha, MOB transparency,
shadow, and playfield. Expand the dragon's multi-tile artwork using the
existing `ch04_dragon_tiles.png` asset, and show a door cell's four tile
writes. Keep a brief board diagram for CPU, video memory, graphics ROM,
and independent sound computer; leave address-map and chip-socket detail
to the hardware reference.

## Source notes

- [Hardware reference](../doc/01_hardware.md), §§1 and 4–9: clock, display
  geometry, tile and palette formats, layers, sprite dimensions, and alpha.
  §6 documents the shadow palette's intensity subtraction precisely.
- [Game subsystems](../doc/04_game_subsystems.md), §§7, 13, and 17:
  palette animation, tile updates, and camera scroll.
- The key and shadow illustrations are retained ROM-derived explanatory
  renders. They isolate drawing mechanisms rather than document observed
  gameplay. Their original `ch04` filenames are asset identifiers.

[Previous: A room full of monsters](04_the_horde.md) |
[Contents](README.md) |
[Next: A world in ten bytes](06_a_world_in_ten_bytes.md)
