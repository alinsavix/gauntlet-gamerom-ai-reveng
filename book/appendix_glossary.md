# Appendix — Glossary and Repository Map

Two reference sections and two housekeeping ones: every term of art the book
introduces, a map of which repository file answers which kind of question, a
note on where external material came from, and the checklist this book is held
to before publication.

---

## Glossary

**Acid puddle.** A monster that moves like a hazard: it drifts, and contact
slows the player it touches rather than only damaging them. Chapter 11.

**Attract mode.** What the cabinet does when nobody is playing. Four screens
cycle: high scores, title, a recorded demo, and three legend pages. Each is one
value of `game_mode`. Chapter 15.

**Audit.** A machine-checked inventory that verifies a documentation claim
against the actual ROM bytes, regenerable by script. The project keeps audits
for callable contracts, control targets, RAM references, byte coverage, and
maze records. Chapters 2 and 17.

**Bank switching.** Making a large ROM visible to the CPU through a smaller
window by selecting which slice appears there. Gauntlet II's 32 KB of level
data is seen through an 8 KB aperture in four banks. Chapter 9.

**Big-endian.** Byte ordering in which the most significant byte of a
multi-byte value is stored first. The 68010 is big-endian, which is why a
16-bit argument sits in the *second* half of a 32-bit stack slot. Chapters 3
and 17.

**Callable contract.** A checked statement of one routine's purpose,
arguments, return behavior, and any deviation from the normal calling
convention. The game ROM has 321 of them, and a name alone is not accepted as
evidence for one. Chapter 17.

**Confidence labels.** The grading applied to every finding in the
documentation: **Verified** (proven from the bytes and their consumers),
**Strong inference** (observations agree, final proof absent), and weaker
grades down to **Contradicted** (disproved by later evidence, never to be
repeated). Chapters 2 and 17.

**Continue prompt.** The timed offer to resume at the current level after the
last player dies past level one. Its ROM text says PRESS START; the cabinet's
start button is Fire. Chapter 14.

**Debouncing.** Filtering the mechanical bounce out of a switch by requiring
several consecutive agreeing samples. Gauntlet II shifts each input bit into a
sixteen-frame history register, in hand-written assembly. Chapter 6.

**Demo.** The third attract screen: the real game engine running on recorded
joystick input from ROM rather than on a player. Chapter 15.

**Dialog gate.** The single test in the main loop that skips the entire
sixteen-call gameplay block while a message box is on screen, freezing the
world without stopping the machine. Chapter 6.

**Dragon.** A multi-MOB actor with its own state machine, flight-path programs,
and nine-hit defeat rule, sitting outside the ordinary monster dispatcher.
Chapter 12.

**EEPROM.** The small non-volatile memory holding operator settings, high
scores, maze rotation state, and statistics. Written one verified byte per
frame, with redundant copies and single-bit repair. Chapter 14.

**Forcefield.** A hazard built from a hub record and a run of segments, cycling
on and off on randomized timing, damaging whoever touches it while it is
active. Chapter 13.

**Frame.** One trip through the main loop, one sixtieth of a second. Every
duration in the game is denominated in frames. Chapter 6.

**Frame counter.** The word the main loop increments each frame, used to pace
health drain, info-panel refresh, and animation cycles. Chapter 6.

**Free play.** Operator pricing in which no coin is required. The OS reports it
as a coin multiplier of zero, which also changes which buttons can break the
attract cycle. Chapters 14 and 15.

**Game mode.** The one word distinguishing normal play, the treasure-room
transition, and the four attract screens. Most subsystems apply their own
additional gates. Chapter 6.

**Game ROM.** The 128 KB image holding the gameplay code and its data tables,
one of the three analyzed images. Chapter 3.

**Generator.** A maze object that periodically creates monsters, subject to a
per-level cap, a spawn probability, and a bounded search for a clear adjacent
cell. Chapter 11.

**Health.** The player's single resource: it drains with time, falls with
damage, and is bought with coins. There is no lives counter anywhere in RAM.
Chapters 1, 10, and 14.

**Hook.** An entry point the game ROM publishes in its header so the OS can
call into game-specific behavior for start, interrupts, tests, and options.
The reverse of an OS service. Chapter 5.

**Info panel.** The right-hand column showing level, one status column per
player position, and the operator's health-per-coin rate. Mostly text layer,
with MOB graphics for the fancier parts. Chapter 14.

**Interrupt.** Hardware temporarily redirecting the CPU into an OS-owned
handler, which may dispatch to a game hook. The two that matter here are
VBLANK and the sound processor's response. Chapter 5.

**IT.** Gauntlet II's tag mechanic. One player is IT, monsters preferentially
target them, and contact passes it on. Chapter 10.

**Legend.** The last attract screen: three explanatory pages drawn over a maze
used as scenery, covering items and terrain, the monster roster, and the
credits. Chapter 15.

**Level.** The player's progress count, which goes up as they exit. Distinct
from the **maze**, which is a stored layout record. The two are not related by
a simple formula. Chapter 9.

**Level flags.** Four bytes in a maze record's header that modify how the level
behaves: odd-angle or fast monsters, wraparound, invisible walls, moving
exits, and more. Two of the bits are re-randomized every time a level is
built. Chapter 9.

**Lobber.** A monster that throws projectiles in an arc, over walls. Chapter 11.

**Main loop.** The routine the game never leaves after boot, named
`g2mainloop` here, which advances every system by one frame and waits for the
next VBLANK. Chapter 6.

**Maze.** One of the 117 stored layout records in the Slapstic ROM, including
normal levels, treasure rooms, secret rooms, and the demo and legend
backgrounds. Chapter 9.

**MOB.** Motion object, the hardware's name for a sprite. Up to 1,024 numbered
slots, each described by four parallel tables in video RAM plus a software-only
state array. Used throughout after Chapter 4; Chapter 8 covers its role as a
game-state record.

**Morse signature.** Nine runtime-dead bytes in the game ROM header whose bits
decode as International Morse code to COPYRIGHT 1986 ATARI GAMES, following a
technique Atari used to prove ROM copying. Chapter 17.

**Mugger.** The thief's variant: the same state machine with one flag bit set,
stealing health instead of inventory and fighting on contact. Chapter 12.

**OS ROM.** The 64 KB image holding boot code, diagnostics, and the shared
services the game calls through a fixed jump table. The same physical part
shipped in Gauntlet and Gauntlet II. Chapters 5 and 17.

**Palette.** A set of colors that tile and sprite pixel values index into,
stored as intensity plus red, green, and blue. Chapter 4.

**Playfield.** The scrolling maze tile layer: a column-first 64×64 grid of tile
words forming a 512×512-pixel world, of which the screen shows a window.
Chapter 4.

**Player position.** One of the cabinet's four fixed, color-coded control slots
(red, blue, yellow, green), each with its own joystick, buttons, coin slot,
and info-panel column. Chapter 1.

**Potion.** The consumable the Magic button spends. Its effect on each target
comes from a character-and-power matrix rather than a single damage number.
Chapter 10.

**Power-up.** A timed or permanent enhancement to speed, shot power, shot
speed, magic, armor, fight strength, invisibility, invulnerability,
repulsiveness, reflection, supershots, or transportability. Chapter 10.

**Reverse engineering.** Recovering code, data structures, and behavior from
shipped ROM images, with no access to original source. Chapter 2.

**Runtime-dead.** Present in the ROM, never reached during execution. The
project documents such regions exactly without inventing purposes for them.
Chapter 17.

**Score per coin.** Each player's score divided by the coins they inserted.
This quotient, and not the raw score, is what the high-score table ranks, and
it feeds back into the monster cap. Chapter 14.

**Secret objective.** A hidden per-maze task, called a trick in the data, such
as avoiding treasure or shooting a particular thing. Completing one earns
entry to a secret challenge room. Chapter 13.

**Self-test.** The operator's diagnostic mode: memory and ROM tests, display
and switch tests, a sound test, configuration editors, and statistics screens.
Chapter 5.

**Semaphore.** The one word the VBLANK interrupt sets and the main loop
consumes, which is what locks the game's update rate to the display's refresh.
Chapter 6.

**Shot channel.** A reserved projectile slot. Each player position owns one,
which is why a hero can have only one ordinary shot in flight. Chapter 10.

**Slapstic.** The copy-protection chip that selects which bank of the level
ROM appears in the CPU's window, and only after a required access ritual.
Chapter 9.

**Slapstic ROM.** The 32 KB bank-switched image holding all 117 maze records,
one of the three analyzed images. Chapters 3 and 9.

**Slot, tile, and pixel coordinates.** The three related spaces a thing in the
maze occupies: a 32×32 logical maze grid for placement, a 64×64 grid of 8×8
tiles for rendering, and 0–511 pixel coordinates for sprites and camera.
Chapter 8.

**Sorcerer.** A monster that blinks out of view and may be immune while
hidden. Chapter 11.

**Sound latch.** The single byte-wide register the main CPU writes to send a
command to the sound board, with a status bit reporting whether the previous
byte has been collected. Chapter 16.

**Stamp.** A 2×2 block of playfield tiles written together whenever one logical
maze cell changes appearance. Chapter 4.

**Text layer.** The character grid drawn over everything else, carrying scores,
messages, and the between-level black curtain, with a per-character opaque
bit. Chapter 4.

**Thief.** A purpose-built actor that selects the wealthiest player, pursues
them, steals an item, and runs for the edge of the maze. Chapter 12.

**Tier.** A monster's remaining strength, carried in the same packed field as
its palette number, so a monster's health is literally its color. Chapter 11.

**Transporter.** A maze object that moves a player to another transporter,
with the destination chosen from a table built after the maze decodes.
Chapter 13.

**Treasure bag.** A special drop that raises the collector's treasure
multiplier and lowers every rival's. Chapter 14.

**Treasure multiplier.** The per-player factor applied to nearly every score
award before it is added. A thief reduces it to one. Chapter 14.

**Treasure room.** A timed bonus level reached on a countdown, with its own
layouts, music, and mischievous speech. Chapter 13.

**VBLANK.** The vertical blanking interval, the pause after the display
finishes drawing a field. The interrupt it raises is the game's clock.
Chapters 4 and 6.

**Watchdog.** A hardware timer that reboots the board unless software keeps
resetting it, so a wedged machine returns to attract mode instead of sitting
frozen. Chapters 3 and 5.

---

## Map of the repository

| If you want to know | Open |
|---------------------|------|
| The board, memory map, chips, and hardware registers | [`doc/01_hardware.md`](../doc/01_hardware.md), [`refs/HW_WRITEUP.md`](../refs/HW_WRITEUP.md) |
| Boot, interrupts, OS services, EEPROM, coin handling, self-test | [`doc/02_os_rom.md`](../doc/02_os_rom.md) |
| ROM layout, the main-loop call sequence, calling convention, coverage | [`doc/03_game_rom_structure.md`](../doc/03_game_rom_structure.md) |
| How any gameplay subsystem works, in detail | [`doc/04_game_subsystems.md`](../doc/04_game_subsystems.md) |
| What a RAM address holds, or what a ROM table contains | [`doc/05_data_reference.md`](../doc/05_data_reference.md) |
| Maze numbering, level progression, record format, level flags | [`doc/06_maze_catalog.md`](../doc/06_maze_catalog.md) |
| What a named function does and what its arguments are | [`doc/07_function_index.md`](../doc/07_function_index.md) |
| What is still unknown, and what was corrected when | [`doc/08_known_issues.md`](../doc/08_known_issues.md) |
| Where to start in the technical docs | [`doc/INDEX.md`](../doc/INDEX.md) |
| Machine-checked contracts, coverage, and reconciliation tables | [`doc/generated/`](../doc/generated/README.md) |
| Re-running every audit against your own ROM images | `make check` in [`doc/`](../doc/) |
| A ready-made annotated disassembly session | [`doc/gauntlet_loader.r2`](../doc/gauntlet_loader.r2) |
| Decoding or rendering tiles, sprites, stamps, and mazes | [`python-gex/`](../python-gex/) |
| Sound command numbers and their meanings | [`refs/soundcmds.csv`](../refs/soundcmds.csv) |
| The project owner's pre-existing manual notes | [`refs/GAME_ROM_KNOWN.md`](../refs/GAME_ROM_KNOWN.md) |
| How to build the three analyzed images from real parts | the repository [`README.md`](../README.md) |

---

## Source notes

Everything factual in this book traces to one of four places.

**The maintained documentation and its audits.** `doc/` and `doc/generated/`
are the normal source of truth, and the "Under the hood" boxes cite the exact
file and section. Where drafting these chapters found the documentation wrong,
the correction was applied there and logged in
[`doc/08_known_issues.md`](../doc/08_known_issues.md).

**The ROM images themselves.** Several claims were re-derived directly by
disassembly and by byte-level scans while writing, including Chapter 15's
finding that the random seed is never initialized, Chapter 16's tracing of the
coin path through the sound latch, and Chapter 17's independent decode of the
Morse signature.

**MAME.** Used as a secondary aid for hardware behavior the three analyzed
images cannot describe on their own. Chapter 16's account of the sound board
(the 6502's clock and memory map, the YM2151, POKEY, and TMS5220, the mixer
register, and the NMI and IRQ 6 wiring) comes from the memory-map comment
block and machine configuration in `src/mame/atari/gauntlet.cpp`. Chapter 17's
observation that Gauntlet and Gauntlet II ship the same OS ROM parts comes
from the ROM definitions in the same file, checked against the SHA-1 digests
of the images used here.

**External historical material.** Chapter 17's account of Atari's Morse-code
copyright traps rests on Ed Logg's affidavit concerning Centipede,
[available as a PDF](https://arcadeblogger.com/wp-content/uploads/2019/06/ed-logg.pdf),
with the surrounding story at
[Atari Centipede's Hidden Code Trap](https://arcadeblogger.com/2019/06/29/atari-centipedes-hidden-code-trap/).
The decoded Gauntlet II bytes are from this project; the technique and its
legal use are from that source.

Player culture and well-known Gauntlet stories appear only as lore, and are
labeled as such where they appear.

---

## Publication checklist

- [ ] Every chapter opens with its question, its promise, and what it builds on.
- [ ] Every chapter closes with an "Under the hood" box, and every address and
      document reference in those boxes resolves.
- [ ] Zero `**[needs verification]**` markers remain.
- [ ] Zero `**[image needed]**` markers remain; every image is either produced
      into `book/img/` or its passage rewritten to stand without one.
- [ ] Every image referenced by a chapter exists, and
      [`img/generate_images.py`](img/generate_images.py) regenerates all of
      the ROM-derived ones.
- [ ] Internal chapter links and the table of contents in
      [`README.md`](README.md) resolve.
- [ ] Terminology matches this glossary: MOB, playfield, text layer, Slapstic
      ROM, OS ROM, game ROM, player position, level versus maze.
- [ ] No Contradicted claim from `doc/08_known_issues.md` survives anywhere in
      the text.
- [ ] Verified material reads as fact; anything weaker carries an honest
      softener.
- [ ] Any correction a chapter made to `doc/` has been applied there, so no
      "Under the hood" box describes the documentation as saying something it
      no longer says.
- [ ] `make check` passes in `doc/`, so the artifacts the boxes cite are
      current.
