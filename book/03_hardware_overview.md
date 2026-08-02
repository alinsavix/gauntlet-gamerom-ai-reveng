# Chapter 3 — The Machine (Hardware Overview)

**This chapter answers:** What hardware lives inside a Gauntlet II cabinet,
and how do its parts split up the work of running the game?

**By the end you will understand:** the main CPU and the single address space
it sees, how the physical ROM chips on the board become the analyzed images
this book studies, which jobs the three main images perform, and the design
idea the rest of the book leans on: the CPU maintains tables describing what
should appear, while dedicated video hardware turns those tables into pixels.

**It builds on:** Chapter 2's headline sketch of the cast of chips. This
chapter introduces each member properly and draws the map they all share.

---

## A screen too busy for its brain

Stand in front of the cabinet during the attract demo from Chapter 1. The
recorded Elf sprints through a maze while dozens of ghosts converge on him,
the maze scrolls underneath everyone, score digits tick over, and a message
crawls across the screen. Sixty times a second, all of it moves.

Run the arithmetic on that picture. The display is 336×240 pixels refreshed
60 times per second, which comes to about 4.8 million pixels every second.
The processor in charge of the game is a Motorola 68010 ticking along at
roughly 7.16 MHz, and a typical instruction costs it several clock cycles, so
it manages somewhere around a million instructions per second. Even if the
CPU did nothing except output pixels, it would fall behind the electron beam
before finishing a single frame.

The board resolves this with a division of labor. The CPU decides *what* is
on screen: it writes tile numbers into a maze grid, sprite records into
sprite tables, and color values into palette memory. Separate video circuitry
reads those tables continuously and paints the actual picture, frame after
frame, with no further help. When a ghost moves one pixel left, the CPU
updates one number in one table, and the video hardware does the rest.
Everything in Chapter 4 builds on this arrangement, and most of the game
code's apparent magic comes down to editing small tables very efficiently.

## The main CPU

The processor running the show is a Motorola 68010, a member of the 68000
family that also powered the Macintosh, the Amiga, the Atari ST, and early
Sun workstations. Inside an arcade cabinet full of custom video circuitry,
the CPU itself is the most ordinary part: a general-purpose microprocessor
that any programmer of the era could sit down and write for.

A few of its characteristics shape everything downstream, so they are worth
thirty seconds each:

- **32-bit registers, 16-bit bus.** The programmer works with sixteen 32-bit
  registers, but the chip talks to memory over a 16-bit external data bus, so
  memory traffic naturally happens in 16-bit *words*. The video hardware's
  tables are all built from these words, and the book will describe them that
  way.
- **A 24-bit address space.** The chip can address 16 MB of memory. Gauntlet
  II uses that room sparsely, scattering small islands of ROM, RAM, and
  hardware across it.
- **Big-endian byte order.** Multi-byte values are stored most significant
  byte first. When a later chapter shows a hex dump of a table, the bytes
  read in the order a human would write the number.
- **The 68010 specifically** is a minor revision of the original 68000, with
  small fixes around virtual memory and interrupt handling. For this book the
  distinction almost never matters, and "the CPU" will do from here on.

## One address space with everything in it

The 68010 has no separate instruction for talking to a device. Reading the
joysticks, resetting the watchdog, changing a palette entry: each of these is
an ordinary memory read or write to a particular address, a scheme called
**memory-mapped I/O**. One address space therefore contains the entire
machine, and learning the layout of that space is learning the machine.

Here is the map in simplified form, with the regions the book will keep
returning to:

| Region | Addresses | Size | What lives there |
|--------|-----------|------|------------------|
| OS ROM | `0x000000–0x00FFFF` | 64 KB | Boot, self-test, shared services (Ch. 5) |
| Slapstic ROM | `0x038000–0x03FFFF` | 32 KB | Level data, bank-switched (Ch. 9) |
| Game ROM | `0x040000–0x05FFFF` | 128 KB | The game itself |
| Main RAM | `0x800000–0x801FFF` | 8 KB | Working variables |
| EEPROM | `0x802000–0x8023FF` | 512 usable bytes | High scores, settings, statistics |
| Hardware I/O | `0x803000–0x8031FF` | 512 B | Inputs, watchdog, sound latches, LEDs |
| Playfield RAM | `0x900000–0x901FFF` | 8 KB | The maze tile grid (Ch. 4) |
| MOB RAM | `0x902000–0x903FFF` | 8 KB | Sprite tables (Ch. 4) |
| Video RAM spare | `0x904000–0x904FFF` | 4 KB | More working variables |
| Alpha RAM | `0x905000–0x905FFF` | 4 KB | The text overlay (Ch. 4) |
| Color RAM | `0x910000–0x9107FF` | 2 KB | Palettes (Ch. 4) |
| Scroll register | `0x930000` | 2 B | Playfield horizontal scroll (Ch. 4) |

Two things about this map deserve a moment of appreciation. First, look at
how little RAM there is. General-purpose variables get 8 KB of main RAM plus
a 4 KB spare corner of video memory that the designers pressed into service,
and inside that roughly 12 KB live four players' full records, hundreds of
monsters' worth of state, the camera, the thief's plans, the demo playback
machinery, and everything else the coming chapters describe. The video RAM
regions hold additional world state in the form of the tile grid and sprite
tables themselves, and Chapter 8 shows how the software treats those hardware
tables as its own data structures to stretch the budget.

Second, notice that video memory is shared territory. The CPU writes the
playfield grid, the sprite tables, the text overlay, and the palettes as if
they were ordinary RAM; the video circuitry reads the same memory as its
instructions for painting. That shared memory is the machine's entire
drawing interface: to change the picture, code changes the tables, and the
next frame comes out different.

## From chips on a board to files on a disk

The "game ROM" this book keeps referring to is an assembled 128 KB file,
while the board itself carries 8-bit ROM chips arranged in pairs. The pairing
follows from the bus: the CPU reads 16 bits at a time, and each chip can
supply half of that. One chip of a pair feeds the even byte lane and
its partner feeds the odd lane, so consecutive bytes of a program alternate
between two physical chips. Board schematics label chip sockets by grid
locations such as 7A and 7B, and this project names each pair by its row.

Reverse engineering begins by undoing that arrangement: read each chip,
interleave the byte streams, and get back the bytes in the order the CPU sees
them.

```
CPU address:   0      1      2      3      4      5    ...
supplied by:   7A[0]  7B[0]  7A[1]  7B[1]  7A[2]  7B[2] ...
```

The 128 KB game image takes one more step, because it spans two rows of
chips. The 7A/7B pair supplies the first 64 KB and the 6A/6B pair the second,
so the assembled file concatenates the interleaved row 7 with the interleaved
row 6. The result is `row76.bin`, the image whose bytes every analysis in
this book examines. The OS pair at 9A/9B interleaves into the 64 KB
`row9.bin`, and the level-data pair at 10A/10B into the 32 KB `row10.bin`.
Published checksums for all three (listed in the repository `README.md`) let
anyone rebuild the exact images from their own chips and confirm they are
reading the same bytes.

## Three images, three jobs

Those three assembled images divide the machine's software cleanly:

- **The OS ROM** owns the machine itself. It boots the board, tests the RAM
  and ROMs, and then stays resident, offering shared services (text drawing,
  coin accounting, EEPROM access, sound communication) through a fixed table
  of entry points that game code calls like a public API. Chapter 5 walks
  through its boot sequence and explains why an arcade board from 1986 has
  something worth calling an operating system.
- **The game ROM** is Gauntlet II: every rule, monster, table, and behavior
  from Chapter 1. It occupies most of this book.
- **The Slapstic ROM** stores the level data, the 117 maze records Chapter 9
  decodes. It earns its odd name from the Slapstic, an Atari copy-protection
  chip that sits between this ROM and the CPU and only reveals the right 8 KB
  bank after the software performs a specific sequence of accesses. Chapter 9
  tells that story.

These are the *analyzed logical images*, and the board holds other ROMs
besides. The artwork lives in dedicated graphics ROMs, split across four
chips with each chip holding one bit-plane of the 4-bit pixels<!-- ALINSA: verify this,
and also how many total chips there are for graphics ROM -->; the video
hardware reads those directly, and the CPU never sees them at all. A separate
character ROM feeds the text overlay under the same arrangement. The sound
board carries its own 48 KB of program and speech data for its own processor.
The renderings in this book draw on the graphics ROMs, and the code that
*uses* them, by writing tile numbers into video RAM, lives entirely in the
three images above.

## The display, briefly

The picture itself is 336×240 pixels, refreshed 60 times a second, and the
video hardware composes it from three layers. At the bottom of the stack, a
scrolling **playfield** shows a window onto a 512×512-pixel maze held as
a tile grid in playfield RAM, positioned by two scroll registers. Above it move
the **motion objects**, or MOBs, the hardware's name for sprites: players,
monsters, shots, and animations, described by records in MOB RAM. And finally,
in top is a text layer of alphanumeric characters which carries scores and messages,
and can be transparent or opaque per-character. Chapter 4 takes this apart properly,
down to individual tiles, palette entries, and the linked lists the sprite
hardware follows.

## The supporting cast

The rest of the hardware I/O region rounds out the machine.

**The sound computer.** Audio belongs to a second, complete computer on its
own corner of the board: a MOS 6502 with its own ROM and its own synthesis
and speech chips. The two processors share no memory. They converse through
single-byte latches in the I/O region: the main CPU writes a command byte ("play
the food sound", "say the Blue Warrior warning") to one address, the 6502 picks it up
and later posts response bytes back through another address, and a status bit reports
whether the latch is occupied. The main CPU can also reset the sound
processor through a control register when the conversation breaks down.
Keeping audio on separate hardware means music and speech cost the game loop
almost nothing, and Chapter 16 covers the protocol spoken across this
two-byte wire.

**The inputs.** Each of the four player positions presents one byte in the
I/O region: four joystick direction switches, Fire, Magic, and two unused
spare lines. The switches are wired *active-low*, reading 0 when pressed,
a common electrical convention worth remembering before Chapter 6 shows the
debouncing code that cleans these bits up. A separate status byte gathers
machine-level signals, including the self-test switch inside the coin door
and a bit that flips when the display finishes drawing each frame. That bit
is the heartbeat Chapter 2 promised, and Chapters 4 and 6 give it its proper
name, VBLANK. Coin switches follow their own path into the OS's coin
accounting, which Chapter 14 follows from switch closure to health.

**The EEPROM.** High scores, operator settings, and play statistics survive
power-off in a 512-byte electrically erasable PROM. It reads like ordinary
memory, but writing it is another matter: each write must be preceded by a poke
to an unlock register, and the part needs milliseconds per byte, an eternity
against a 16-millisecond frame. The OS therefore queues changes and trickles
them out one byte per frame behind the game's back, with checksums guarding
the stored records. Chapter 14 examines what the game chooses to remember.

**Latches and lights.** A handful of write-only registers control the board:
four LED outputs, a board-control latch<!-- ALINSA: what is this? -->, and an acknowledge register the
software writes to clear each frame's VBLANK signal.

**The watchdog.** One register does its job by being written to, and by
punishing silence. Unless software writes to the watchdog address every few
fractions of a second, a hardware timer expires and resets the entire
machine. An arcade cabinet earns money only while running, with nobody on
site to press a reset button, so a crashed game must revive itself; a machine
that wedges reboots into attract mode moments later. The obligation shapes
the software from its first instruction: boot code pets the watchdog
hundreds of times during its delay loops and RAM tests, and once the game is
running, the once-per-frame rhythm of the main loop keeps the timer fed as a
side effect. The watchdog will reappear in Chapter 5 as one of the boot
sequence's constant background duties.

That completes the tour of the parts: one conventional CPU holding the whole
machine in a single address space, three software images with distinct jobs,
video hardware that paints from shared tables, and a small crew of
specialists for sound, persistence, and self-preservation. Chapter 4 now
descends into the largest of those specialists and follows a tile number all
the way to a lit pixel.

---

> **Under the hood**
>
> - CPU identification, ~7.159 MHz clock, and the full memory map this
>   chapter simplifies: `doc/01_hardware.md` §1–2. The populated ranges are
>   Verified; the unpopulated decode apertures omitted here are discussed
>   under the map in that section.
> - Hardware I/O port table (player inputs at 0x803001/3/5/7, status register
>   0x803009, watchdog 0x803100, LEDs 0x803121–0x803127, sound command latch
>   0x803170/1, sound read 0x80300F, EEPROM unlock 0x803150, VBLANK
>   acknowledge 0x803140): `doc/01_hardware.md` §3.
> - Status-register bits (bit 3 self-test, bit 5 sound I/O full, bit 6
>   VBLANK): `doc/01_hardware.md` §3.1.
> - Joystick/button bit assignments (Magic bit 0, Fire bit 1, directions bits
>   4–7, active-low): `doc/05_data_reference.md` §3.11; the word-wide read
>   convention is noted in `doc/01_hardware.md` §3.
> - Video RAM sub-regions and scroll registers (vertical scroll is the word
>   at 0x905F6E, inside alpha RAM by hardware design): `doc/01_hardware.md`
>   §2.2 and §10.
> - EEPROM electrical details (28C04A, 512 data bytes on the odd byte lane of
>   0x802000–0x8023FF) and the OS's one-byte-per-VBLANK queued writer with
>   XOR checksums: `doc/01_hardware.md` §11 and `doc/02_os_rom.md` §8.
> - The boot-time watchdog-petting pattern and the interrupt traps that stop
>   feeding it to force a reset: `doc/02_os_rom.md` (boot sequence and
>   §"Watchdog Pattern").
> - Slapstic bank-switching trigger sequence and the three game-ROM helper
>   routines (0x56E58, 0x56E6E, 0x56E84): `doc/01_hardware.md` §11.
> - Chip part numbers, board locations, even/odd interleaving instructions,
>   and sha1 checksums for `row76.bin`, `row9.bin`, and `row10.bin`: the
>   Appendix of the repository `README.md`.
> - Coin sampling and credit services in the OS (`process_coins`,
>   `check_and_deduct_coin`): `doc/02_os_rom.md` §8.10.
