# 5. Painting the dungeon

Imagine following a ghost along a corridor. Its outline changes as it
moves. The floor slides sideways when the party advances. Your health
number stays in the same place at the right. When the ghost passes over a
pattern in the floor, the pattern remains visible around its body and
becomes darker beneath its shadow.

That apparently continuous picture combines several different kinds of
change. The ghost has moved within the maze; the view has moved over the
maze; a number has changed without moving at all. The machine does not
produce them by repeatedly painting a complete picture from scratch with
its main processor.

That processor is a Motorola 68010 running at about 7.16 million clock
cycles per second. The monitor displays 336 by 240 pixels about sixty
times a second: nearly 4.84 million visible pixels each second. There are
only about one and a half processor clocks per visible pixel, before
allowing any time for moving monsters, checking controls, or counting
health. Even a simple instruction takes several clocks.

The useful division is therefore not “game logic first, then have the CPU
paint everything.” The CPU describes the picture in memory. Dedicated
video circuitry reads that description and produces the pixels.

## Giving the drawing to somebody else

The 68010 executes the game's instructions: read the controls, attempt a
move, decide whether the ghost takes damage, choose its next animation
picture. **ROM**, read-only memory, holds the fixed program and data.
**RAM**, random-access memory, holds values the program can change.
Video RAM contains descriptions that both the CPU and the display
circuitry use.

The CPU does not need a special “draw ghost” instruction. It writes
ordinary numbers to particular memory addresses. Some select the artwork,
some its colors, and some its position. The display hardware gives those
addresses their visual meaning.

Other addresses lead to hardware controls rather than ordinary stored
data. These are **memory-mapped registers**: small hardware interfaces
reached through the processor's normal address space. A write to the
horizontal-scroll register changes where the video system looks into the
playfield. It does not copy the playfield to a new place. Reading an input
port similarly obtains the controls' electrical state, rather than a
number the program previously put there.

Here is the functional division, with most wiring deliberately omitted:

```text
program and data ROM ----> 68010 <---- controls
                            |
                  writes descriptions and controls
                            |
                            v
                video RAM + color RAM + scroll registers
                            |
                            v
graphics ROM ----------> video circuitry ----------> monitor

68010 <---- command/response latches ----> 6502 sound computer
```

*A functional diagram, not a board layout or bus-timing diagram. The
graphics ROM feeds the video circuitry directly; it is not a library of
pixel arrays that the 68010 copies into a screen buffer.*

Sound has its own processor, a 6502, reached through command and response
latches. The main game can request a sound without synthesizing its
waveform while drawing the maze. That separation will matter when we
follow speech; for now, it reinforces the distinction between deciding
what should happen and generating the physical output.

The video system still does substantial work. It must fetch descriptions
and artwork at the required pace. Sharing memory does not mean that all
accesses happen simultaneously without timing constraints. What the
division removes is the requirement for a game instruction to manufacture
every pixel every time the monitor needs it.

## A drawing made of numbers

The basic unit of maze and sprite artwork is an eight-by-eight-pixel
**tile**. Its 64 pixels live in graphics ROM. A tile number tells the video
circuitry which block of artwork to fetch.

Each pixel supplies four bits, a number from zero to fifteen, rather than
an intrinsic red, green, or blue value. That number selects an entry in a
**palette**, a small table of colors in RAM. The object chooses a palette;
the artwork's pixel chooses a color within it.

![A key, its enlarged tile of numbered pixels, and the palette supplying its colors](img/ch04_tile_zoom.png)

*ROM-derived key artwork, enlarged and annotated by the book's image
generator. Follow an ordinary numbered square to its palette entry. The
checkerboard and shadow swatch explain special MOB values 0 and 1; they
are not literal colors painted by those values during play.*

The key is a two-by-two-tile picture, sixteen pixels across. Its upper-right
tile contains part of the ring. Selecting that tile does not involve the
CPU understanding rings, outlines, or highlights. The image already exists;
the CPU supplies an index.

There are two importantly different ways to recolor such art. Change the
object's palette number and that object uses another existing table.
Change the colors inside a palette and every picture using those entries
can change together. The first lets four player positions share a
character's drawings while retaining different colors. It also supplies
the ordinary monster's visible strength steps. The second can animate a
transporter's colors while its tile numbers remain unchanged.

The layers have separate palette regions. Motion objects can select among
sixteen palettes of sixteen entries. The playfield has eight such
palettes, plus eight matching shadow palettes. Text has its own smaller
four-color palettes. A pixel numbered 9 in a floor tile therefore need not
match pixel 9 in a ghost.

A color entry is itself a sixteen-bit word: four bits each for intensity,
red, green, and blue. These are instructions to the color hardware, not
modern eight-bit RGB values. The intensity field gives the game a way to
change brightness while retaining the three color components. We will
use that distinction when the ghost's shadow reaches the floor.

## Leave the floor where it is

The bottom image layer is the **playfield**. Its stored grid is sixty-four
tiles across and sixty-four down. At eight pixels per tile, that gives a
512-by-512-pixel surface. Only a window onto it is visible, with the
right-hand information panel covering part of the display.

The maze used by gameplay is coarser: thirty-two by thirty-two cells,
sixteen pixels per cell. One logical cell therefore needs four playfield
tiles. A wall cell is not a single sixteen-pixel drawing fetched as one
unit; it is a two-by-two arrangement of the smaller hardware tiles.

Suppose, as an illustrative address calculation, that a wall occupies
maze row 12, column 20. Its upper-left playfield tile is at tile row 24,
column 40. Playfield RAM is stored **column-first**: advance one word in
memory and move down one tile; advance sixty-four words and move right.
A word is two bytes.

```text
One 16-by-16-pixel maze cell:

    top-left              top-right
    tile (40,24)          tile (41,24)
    base + 0 bytes        base + 128 bytes

    bottom-left           bottom-right
    tile (40,25)          tile (41,25)
    base + 2 bytes        base + 130 bytes

Coordinates above are (column,row), in 8-pixel tiles.
```

The top-left word index is `40 × 64 + 24 = 2584`. With playfield RAM
beginning at `0x900000`, its byte address is `0x901430`. The four-word
descriptor supplies top-left, top-right, bottom-left, and bottom-right
tile selections to those four destinations. This is a concrete eight-byte
change describing 256 pixels.

If a changing-wall rule replaces that cell with floor, the tile-update
path chooses the appropriate floor descriptor and writes the small block.
It also revisits neighboring walls where the connection pattern affects
their appearance. An adjoining wall may need a newly exposed end rather
than the drawing of a continuous segment.

Not every disappearing obstacle requires even those four writes. A door
can be a motion object over already-installed floor. Removing that door's
object reveals the floor without repainting it. The important distinction
is which representation supplied the visible obstacle, not whether the
player calls it part of the maze.

## Put the ghost above the floor

**Motion objects**, Atari's term for sprites and usually shortened to MOBs,
form the next layer. Their descriptions specify a starting tile, position,
palette, width, and height. Unlike a playfield tile, a MOB is not confined
to one fixed position in the grid.

A common hero or monster is three tiles wide and three tall: twenty-four
by twenty-four pixels. The hardware reads nine successive tiles, laying
them out left to right and then down to the next row. The program can move
the entire rectangle by changing its position words, or select a new pose
by changing the starting tile number.

That makes the ghost's walk two separable changes. Its coordinates move
the drawing through the corridor. Its animation state selects successive
drawings. Neither operation needs to erase the previous ghost from a
screen-sized painting. On the next scan, the floor supplies the old
location because the ghost's description now places it elsewhere.

![A dragon artwork stamp divided into sixteen consecutive tiles](img/ch04_dragon_tiles.png)

*One ROM-derived four-by-four dragon stamp, rendered and labeled for
explanation. T is tile 8448; the lower-right square is T+15. This isolated
stamp demonstrates tile order, not a captured dragon encounter or the
complete articulated dragon.*

The same scheme builds this larger picture. Width four means that the
second row begins at T+4, not T+1; changing height does not require sixteen
independently positioned sprites. The dimension fields encode “size minus
one,” so a stored value of three means four tiles. Each dimension can
describe one through eight tiles.

The live dragon encounter combines multiple pieces and separately moves
its head. That behavior belongs to its own chapter. Here the useful
observation is smaller: even a large, intricate drawing can be requested
with a starting number and two dimensions.

The rectangular boundary is not the creature's silhouette. MOB pixel
value zero is transparent. Where the surrounding rectangle contains zero,
the floor remains available to the final composition. The hardware's
rectangle can cross a wall edge without making all its empty corners
opaque.

## Keep the numbers still

The top layer is **alpha**, short for alphanumerics. It supplies text,
scores, messages, and the information panel. Its characters also occupy
eight-by-eight-pixel squares, but come from a separate character ROM and
use two bits per pixel: four possible values instead of sixteen.

The displayed width of 336 pixels fits forty-two characters. Memory
reserves sixty-four columns per row, of which only the left forty-two
appear. The distinction between stored and displayed columns will later
give the game a useful place to keep invisible information.

Each character description includes an opacity flag. Normally, character
pixel zero is transparent and the ink sits above the dungeon. Set the
flag and zero becomes opaque too, using the character's background color.
That lets the information panel cover the maze beneath it.

It also provides a curtain. Fill the play area with opaque space
characters using a black background and the dungeon disappears. The
underlying playfield and MOB descriptions can still exist and be changed.
When level construction is finished, transparent blanks reveal them.
Blackness here does not establish that the display has been switched off
or that all the layers underneath are empty.

## Resolve one pixel

We can now follow a small composition without pretending it is a captured
frame. Suppose one floor pixel has value 9 in playfield palette 2.
Its normal color is entry `640 + 2 × 16 + 9 = 681` in color RAM.
Above it, consider several possible samples from the ghost and the alpha
character.

| Alpha at this position | Selected MOB pixel | Result |
|---|---|---|
| Transparent zero | 0 | Normal floor color, entry 681 |
| Transparent zero | 6 | Color 6 from the MOB's selected palette |
| Transparent zero | 1 | Shadow floor color, entry 553 |
| Visible character ink | Any | The alpha ink's color |
| Opaque zero | Any | The alpha background's color |

*Illustrative samples at one output position. The table starts after MOB
overlap has supplied a sprite-layer sample; it is not an ordering rule for
every creature in a crowd.*

The first row gives the ghost its irregular outline. The second supplies
its body. The third is different from ordinary transparency and ordinary
color: MOB value one asks for the underlying **playfield** pixel through
the shadow palette.

For our sample, the shadow index is `512 + 2 × 16 + 9 = 553`, exactly 128
entries below the normal playfield index. That subtraction changes which
table is selected. It does not mean “subtract 128 from the brightness.”
Nor does the ghost paint translucent gray over whichever other sprite
happens to be behind it. This special case selects the floor's color.

![Three Warrior renderings isolating the pixels that cast a shadow](img/ch04_shadow.png)

*ROM-derived Warrior and floor artwork in an explanatory composition.
Left marks shadow pixels red; center omits them. The right panel
illustrates floor-dependent darkening, but its image generator halves
RGB channels. It is an approximation, not a pixel-exact rendering of the
game's intensity operation.*

The game's actual shadow-table construction subtracts seven from the
intensity nibble while keeping red, green, and blue. For example, the
illustrative packed color `0xFA84` becomes `0x8A84`: intensity fifteen
becomes eight, and the color components remain A, 8, and 4.

If the subtraction would borrow, because the original intensity is below
seven, the routine substitutes intensity one. Exactly seven subtracts to
zero without borrowing. “Half intensity” is consequently a useful visual
shorthand for full-intensity source colors, not the precise rule for
every entry. It is also not a measurement of the light produced by a
particular monitor.

Once the table exists, the same small set of shadow colors works beneath
every suitable MOB pixel across the playfield. If the ghost crosses a
different floor pattern, the shadow follows that pattern's colors. No
game routine has to inspect each newly covered floor pixel to repaint it.

## Move the window, not the maze

Return to the scrolling corridor. Both playfield and MOB positions belong
to the 512-pixel world. The scroll controls change their relationship to
the display, while alpha remains screen-fixed.

For a simple example away from the wrap boundary, take an effective view
origin of world position `(200,100)`. A floor feature at `(240,160)` appears
at `(40,60)` in the view. Move that origin two pixels right and the feature
appears at `(38,60)`. A stationary ghost over the feature shifts by the
same two screen pixels. These are downward-positive world coordinates
and an effective view origin, not literal packed register values.

MOB vertical coordinates require a conversion: they count upward from
the bottom of the playfield and locate the object's bottom edge. A
twenty-four-pixel-tall object extends upward from that edge. The display
must combine the anchor, height, and scroll; treating the stored vertical
number as the screen row of its top-left corner would place it incorrectly.

The coordinate fields have nine bits, so the hardware can roll around
after 512 pixels. That does not, by itself, permit a hero to walk through
the edge of a non-wrapping maze. Display arithmetic and movement rules
answer different questions.

Scrolling is therefore cheap in the specific sense that it avoids
copying a new screenful of floor. Choosing the camera position still
takes game work. Moving and ordering the monsters still takes work.
The machine has saved pixel painting, not made a crowded room free.

And the numbers that describe the ghost do more than feed the display.
They also help the game decide whether your next arrow reaches it.
Following that shared representation explains how the picture and the
fight remain connected without being the same thing.

## Source notes

- [Hardware reference](../doc/01_hardware.md), §§1–10: processors,
  memory-mapped interfaces, geometry, palettes, hardware fields, alpha,
  and scrolling. The diagram is functional rather than cycle-accurate.
- [Game subsystems](../doc/04_game_subsystems.md), §§7, 13, 17, and 23:
  palette changes, column-first descriptor writes, camera behavior, and
  upward MOB coordinates. §23.4 documents door removal leaving existing
  floor descriptors unchanged; the worked four-write example is a wall
  replacement, not a claim that every door opening restamps floor.
- Shadow arithmetic follows the ROM routine at `0x5FD80`, especially
  `0x5FD94–0x5FDA2`, and the palette setup call at `0x436B8`.
  The borrow branch distinguishes intensity seven from intensities
  below seven. Hardware-reference §6 supplies the palette regions;
  “subtract 128” in §8.6 concerns the palette index, not RGB brightness.
- All three retained images are explanatory renders of ROM-derived
  artwork, not gameplay captures. Their provenance is visible in
  [`generate_images.py`](img/generate_images.py), functions
  `make_tile_zoom`, `make_dragon_tiles`, and `make_shadow`. The shadow
  image's RGB-halving approximation is qualified in its caption.
  Existing `ch04` filenames are asset identifiers.

[Previous: A room full of monsters](04_the_horde.md) |
[Contents](README.md) |
[Next: A world in ten bytes](06_a_world_in_ten_bytes.md)
