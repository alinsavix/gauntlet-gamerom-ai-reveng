# Appendix: Glossary and source map

This appendix is a way back into an explanation, not another bestiary.
The glossary distinguishes terms that are easy to confuse; the source
map leads from a subject in the book to the research behind it. Exact
addresses, full tables, and callable contracts live in those references
rather than being duplicated here.

## Reading the numbers

Unless marked otherwise, numbers in the prose are decimal. The prefix
`0x` marks hexadecimal, base sixteen: `0x10` means sixteen and `0xFF`
means 255. Hexadecimal is convenient for packed fields because one digit
represents four bits. An address such as `0x904006` names a location;
it is not a count of frames simply because a frame counter lives there.

| Notation or unit | Meaning in this book |
|---|---|
| Bit | One binary digit, zero or one; bit 0 is the least significant |
| Byte | Eight bits |
| Word / longword | Sixteen / thirty-two bits in the 68010 discussion |
| KiB | 1,024 bytes; a 128 KiB image contains 131,072 bytes |
| Pixel | One element of the displayed picture |
| Playfield tile | An 8-by-8-pixel background graphic |
| Maze cell / stamp | A 16-by-16-pixel logical area / its four background tiles |
| Pixels per update | A movement quantity, not automatically a sustained speed |
| Eligible update | A visit on which the relevant rule actually runs |

The 68010 stores multibyte values *big-endian*, most significant byte
first. The bytes `12 34` therefore form the word `0x1234`, not `0x3412`.
A word's bits can also be interpreted as signed or unsigned: `0xFFFF`
is 65,535 unsigned or minus one in signed two's-complement form. Which
meaning applies depends on the consuming instructions.

Timing examples use the nominal rate of approximately sixty updates
per second where stated. A counter that advances only when gameplay
is eligible does not keep counting during a dialog pause. A frame that
overruns its display interval introduces a different distinction.
[The game's clock](07_the_games_clock.md) develops both cases.

## Glossary

### A-D

**Active low.** A switch-input convention in which a cleared bit means
pressed. Demo records use this convention too; a zero bit is not
necessarily an absence of input. [Chapter 15](15_attract_and_demo.md).

**Adaptive food.** Food whose health award follows an adjustment path
rather than the ordinary wholesome-food award. It must also be kept
distinct from poisoned food. [Chapter 8](08_what_a_quarter_buys.md).

**Alpha layer.** The hardware's character grid, also called the text
layer. An opaque blank can hide lower layers; transparent character
backgrounds let them show through. Stored columns outside the visible
picture also provide working space. [Chapters 5](05_painting_the_dungeon.md)
and [11](11_the_thiefs_trail.md).

**Attract mode.** The idle presentation cycle of scores, title,
recorded-input demonstration, and legend pages. Page-selection inputs
do not take control of the scripted heroes.
[Chapter 15](15_attract_and_demo.md).

**Bank switching.** Changing which part of a larger storage device
appears through a smaller address window. Identifying a byte in that
window requires the selected bank as well as the address.
[Chapter 9](09_mazes_and_slapstic.md).

**Breadcrumb.** Informal name for a direction stored in a route grid.
The victim's pursuit trail and the thief's escape trail have separate
writers and uses. [Chapter 11](11_the_thiefs_trail.md).

**Camera.** The visible window onto the larger world. Calculating its
scroll position and deciding whether a player may move near an edge
are related but separate operations. [Chapter 3](03_four_players.md).

**Channel.** A reserved resource with a particular owner or purpose.
A projectile channel is not a sound channel. The player's shot
reservation remains occupied while that shot survives.
[Chapters 2](02_one_arrow.md) and [14](14_a_machine_that_speaks.md).

**Checksum.** A value calculated from data to detect changes or errors.
Matching a ROM checksum does not establish what its code means.
EEPROM check information and the secret-code checksum have their own
formats and consumers. [Chapters 13](13_secrets_and_treasure.md),
[16](16_waking_the_cabinet.md), and [18](18_reading_the_roms.md).

**Collision candidate.** An object or terrain result proposed for an
interaction. Candidate selection is distinct from deciding damage,
reflection, immunity, or whether a projectile is consumed.
[Chapter 6](06_a_world_in_ten_bytes.md).

**Contract.** A description of a routine's inputs, outputs, side effects,
and calling requirements. A checked address or function name alone is
not that description. [Chapter 18](18_reading_the_roms.md).

**Credit / recorded coin count.** Credit is the OS's priced balance
available for a start or health purchase. The game maintains its own
player coin counts for gameplay accounting. Both differ from raw coin
reports returned by the sound board. [Chapter 8](08_what_a_quarter_buys.md).

**Debouncing.** Filtering a sequence of mechanical-switch samples so
contact bounce is not treated as a series of deliberate presses.
[Chapter 7](07_the_games_clock.md).

**Descriptor.** Stored data interpreted by another routine or device:
for example, a tile descriptor selects artwork, while an option
descriptor helps shared menu code present and edit a setting.
[Chapters 5](05_painting_the_dungeon.md) and
[16](16_waking_the_cabinet.md).

**Dialog gate.** The condition that skips a block of gameplay calls
while a message is active. Message timing, coin handling, and other work
outside that block can continue. [Chapter 7](07_the_games_clock.md).

### E-M

**EEPROM.** Electrically erasable persistent memory. It retains settings
and records without power; the OS validates and queues writes to it.
Error correction and redundant copies are not a guarantee against
every interrupted update. [Chapter 16](16_waking_the_cabinet.md).

**Emulator / reconstruction.** An emulator such as MAME executes the
original program within a model of its hardware. `gauntpy` implements
interpreted game operations in Python instead of executing the 68010
instruction stream. [Chapters 17](17_gauntpy.md) and
[18](18_reading_the_roms.md).

**Escape timer.** The long-running eligible-update counter that can
eventually open routes. It is separate from the input-related idle
timer and from bonus-room countdowns.
[Chapter 10](10_the_living_maze.md).

**Frame.** Depending on context, a displayed image or one pass through
the game's repeated update. The book identifies the difference when
display timing, missed deadlines, or skipped work matters.
[Chapter 7](07_the_games_clock.md).

**Frame overflow.** The game's indication that another display
semaphore has arrived before the current work finishes. Its feedback
can reduce generation activity; it is not proof that busy play never
slows. [Chapters 4](04_the_horde.md) and [7](07_the_games_clock.md).

**Game mode / player status.** Game mode describes a shared phase such
as play or an attract presentation. Player status describes one
participant's state. One player may be leaving while another remains
active. [Chapters 3](03_four_players.md) and
[15](15_attract_and_demo.md).

**Generator.** An object that attempts to produce monsters, subject to
timing, probability, load feedback, and placement conditions. Its
strength stages are different object types, not ordinary monster
palette tiers. [Chapter 4](04_the_horde.md).

**Hook / service.** A hook lets the OS enter game-supplied code. An OS
service lets the game request shared work in the other direction.
[Chapter 16](16_waking_the_cabinet.md).

**Interrupt.** An event that redirects CPU execution to a handler.
VBLANK and a sound-board response use different interrupt paths.
[Chapters 7](07_the_games_clock.md) and
[14](14_a_machine_that_speaks.md).

**IRGB.** The palette-word organization containing intensity and red,
green, and blue components. The game's shadow calculation changes
intensity; an illustrative RGB-halving render is only an approximation.
[Chapter 5](05_painting_the_dungeon.md).

**IT.** The transferable tag state that changes which player ordinary
monster targeting prefers. Preference does not remove obstacles or
guarantee every creature can reach that player.
[Chapters 3](03_four_players.md) and [4](04_the_horde.md).

**Latch / cooldown.** A latch remembers that a condition or event has
been registered. A cooldown limits when another action is eligible.
The low-health warning has both; waiting out its cooldown does not
clear its latch. [Chapter 14](14_a_machine_that_speaks.md).

**Level / maze.** Level is progression depth; maze identifies a stored
layout. Persistent selection state and level-dependent setup prevent a
level number alone from identifying the finished room.
[Chapter 9](09_mazes_and_slapstic.md).

**Level flags.** Packed bits enabling behavior such as wrapping or
special movement. Stored header flags and the final runtime flags can
differ after setup. [Chapters 9](09_mazes_and_slapstic.md) and
[10](10_the_living_maze.md).

**MOB.** Motion object, Atari's term for a sprite. The book also uses
MOB record for the related five-word representation: hardware-facing
picture, position, and link data plus software state. That record
participates in gameplay as well as drawing.
[Chapter 6](06_a_world_in_ten_bytes.md).

### O-S

**Occupancy.** The state used to determine what occupies a location.
It is not simply the visible pixels: decorative or hidden artwork and
logical obstruction can differ. [Chapters 6](06_a_world_in_ten_bytes.md)
and [10](10_the_living_maze.md).

**OS.** The resident operating-system ROM providing boot, diagnostics,
and services shared with the game. It remains involved after startup.
[Chapter 16](16_waking_the_cabinet.md).

**Palette.** A lookup from stored pixel indices to colors. Changing
palette entries can change appearance without changing the artwork.
Some object fields also use palette-related bits as gameplay state.
[Chapters 4](04_the_horde.md) and [5](05_painting_the_dungeon.md).

**Phase / pose.** A phase is a step in an attack or animation program;
a pose is the visible arrangement it selects. Dragon phases also carry
fire state. Entering a vulnerable fire phase does not guarantee a
projectile channel was available. [Chapter 12](12_fighting_the_dragon.md).

**Player position / class.** Position identifies a red, blue, yellow,
or green control station. Class identifies its chosen Warrior,
Valkyrie, Wizard, or Elf. Several positions can choose the same class.
[Chapter 1](01_how_to_play.md).

**Playfield.** The scrolling tile layer used for the dungeon background,
larger than the camera's visible window. It is distinct from motion
objects and the text layer. [Chapter 5](05_painting_the_dungeon.md).

**RAM / ROM.** Working read-write memory / read-only program or asset
storage. The graphics ROMs serve video hardware directly; their bytes
are not all available as ordinary data to the main processor.
[Chapters 5](05_painting_the_dungeon.md) and
[18](18_reading_the_roms.md).

**RNG / seed.** A random-number generator evolves stored state to
produce a sequence; a seed supplies starting state. Shared consumers
and their order matter. Equal seeds do not guarantee equal runs from
different setups and inputs. [Chapters 15](15_attract_and_demo.md)
and [17](17_gauntpy.md).

**Score multiplier / score per coin.** The multiplier changes eligible
awards and can be redistributed through multiplayer treasure collection.
Score per coin is a quotient used in separate character-class rankings.
They are not two names for one bonus.
[Chapter 8](08_what_a_quarter_buys.md).

**Secret objective / challenge.** An ordinary-maze objective can qualify
a player for an invitation. The subsequent challenge room has a
separate task, timer, and success condition. A clue is not a complete
specification of either predicate.
[Chapter 13](13_secrets_and_treasure.md).

**Slapstic.** The protection device controlling level-ROM bank access
through particular memory-access sequences.
[Chapter 9](09_mazes_and_slapstic.md).

**SLIP.** Starting link point: an entry for a display band into the
shared motion-object chain. It is not an independent sprite list for
each band. [Chapter 6](06_a_world_in_ten_bytes.md).

**Slot.** An index into the parallel MOB arrays. Cell-bound objects
use slots encoding maze location; reserved projectiles and effects
have different allocation rules.
[Chapter 6](06_a_world_in_ten_bytes.md).

**Sound latch.** A one-byte handoff between the main and sound
processors. Command and response latches run in opposite directions.
Sending a byte is not proof that its requested speech was heard.
[Chapter 14](14_a_machine_that_speaks.md).

**Synthetic scenario.** An invented starting arrangement used to
isolate behavior in the reconstruction. It is not a stored arcade maze
or an original-ROM observation. [Chapters 17](17_gauntpy.md) and
[18](18_reading_the_roms.md).

### T-W

**Tier.** A strength stage. Ordinary monsters encode strength in
palette-related state; generator stages use distinct object types.
[Chapters 2](02_one_arrow.md) and [4](04_the_horde.md).

**Trace.** A record of events or state changes. Its scope matters:
an instruction trace, a post-frame snapshot, and the host's
snapshot-derived event log expose different information.
[Chapters 17](17_gauntpy.md) and [18](18_reading_the_roms.md).

**Transporter.** A terrain mechanism that selects a destination and
tests possible landing cells. An empty landing cell can be legal;
the destination pad is not the entire landing test.
[Chapter 10](10_the_living_maze.md).

**VBLANK.** Vertical blanking, the display interval whose interrupt
provides normal frame pacing and other scheduled work. It can occur
while the main loop is still finishing a previous update.
[Chapter 7](07_the_games_clock.md).

**Watchdog.** A hardware timer that resets the board if software stops
servicing it. Resetting execution can recover from a stopped program
without repairing a faulty component.
[Chapter 16](16_waking_the_cabinet.md).

**Wrap.** Joining opposite world edges for the operations that support
it. Wrapped coordinates still need the correct collision and camera
rules; a drawing crossing a seam alone does not establish traversal.
[Chapters 3](03_four_players.md) and [10](10_the_living_maze.md).

## From a reader's question to the research

Start with the chapter for the explanation, then use its source notes
to select the narrower contract or table. The technical documents are
organized by subsystem, so their numbers do not correspond to the
book's chapter numbers.

| Subject | Book explanation | Technical starting point |
|---|---|---|
| Controls, classes, joining, shared camera | [1](01_how_to_play.md), [3](03_four_players.md) | [Subsystems](../doc/04_game_subsystems.md): player movement, selection, joining |
| Shot reservation, damage, collision | [2](02_one_arrow.md), [6](06_a_world_in_ten_bytes.md) | [Subsystems](../doc/04_game_subsystems.md), sections 2.2 and 26; [combat contracts](../doc/generated/monster_combat_contracts.csv) |
| Crowds, generation, monster differences | [4](04_the_horde.md) | [Subsystems](../doc/04_game_subsystems.md), section 3 |
| Layers, colors, object records | [5](05_painting_the_dungeon.md), [6](06_a_world_in_ten_bytes.md) | [Hardware](../doc/01_hardware.md); [data reference](../doc/05_data_reference.md) |
| Frame ordering and pauses | [7](07_the_games_clock.md) | [Game ROM structure](../doc/03_game_rom_structure.md), section 2.1 |
| Health, credit, rankings, statistics | [8](08_what_a_quarter_buys.md) | [Subsystems](../doc/04_game_subsystems.md), section 10; [OS ROM](../doc/02_os_rom.md) |
| Maze identity, bank access, decoding | [9](09_mazes_and_slapstic.md) | [Maze catalog](../doc/06_maze_catalog.md); [maze data](../doc/generated/maze_catalog.csv) |
| Doors, walls, transport, exits | [10](10_the_living_maze.md) | [Subsystems](../doc/04_game_subsystems.md); chapter notes identify individual consumers |
| Thief, mugger, pursuit and escape | [11](11_the_thiefs_trail.md) | [Subsystems](../doc/04_game_subsystems.md), section 9 |
| Dragon programs and accepted damage | [12](12_fighting_the_dragon.md) | [Subsystems](../doc/04_game_subsystems.md), section 8 |
| Bonus qualification and contest encoding | [13](13_secrets_and_treasure.md) | [Subsystems](../doc/04_game_subsystems.md); [data reference](../doc/05_data_reference.md) |
| Speech selection and processor exchange | [14](14_a_machine_that_speaks.md) | [Subsystems](../doc/04_game_subsystems.md); [OS ROM](../doc/02_os_rom.md); [sound command table](../doc/generated/soundcmds.csv) |
| Demonstration, legend, idle controls | [15](15_attract_and_demo.md) | [Subsystems](../doc/04_game_subsystems.md), section 6; [demo data](../doc/05_data_reference.md), section 5.8 |
| Boot, diagnostics, persistent storage | [16](16_waking_the_cabinet.md) | [OS ROM](../doc/02_os_rom.md) |
| Playing and inspecting the reconstruction | [17](17_gauntpy.md) | [gauntpy README](../gauntpy/README.md); [scenario guide](../gauntpy/scenarios/README.md) |
| Disassembly, provenance, retained material | [18](18_reading_the_roms.md) | [Function index](../doc/07_function_index.md); [loader](../doc/gauntlet_loader.r2); [generated-reference guide](../doc/generated/README.md) |

The [technical index](../doc/INDEX.md) is the entry point for the wider
research. The [function index](../doc/07_function_index.md) maps modern
routine names to addresses and contracts. The
[data reference](../doc/05_data_reference.md) supplies field layouts and
ROM tables; [generated catalogs](../doc/generated/README.md) provide
machine-readable counterparts and their checkers.

Where a broad reference uses looser wording than a chapter's specifically
cited consumer, follow the actual operations rather than counting which
description is repeated more often. Chapter 18 explains why independent
ROM evidence matters more than agreement between derived accounts.

## Images, tools, and historical sources

Captions distinguish ROM-derived artwork, constructed diagrams,
reconstruction output, and observed game frames. A ROM-derived picture
establishes what the stored art contains; a schematic explains a
relationship; neither becomes an original-game observation just because
it resembles the screen.

Image filenames beginning `chNN_` retain the earlier manuscript's asset
identifiers. Their numbers are not the current chapter order. Follow the
image's caption and surrounding explanation rather than its filename.

The repository's [ROM requirements](../README.md#appendix-roms) identify
the user-supplied program and level images. The local
[gex documentation](../python-gex/README.md) describes asset decoding
and required graphics ROMs. That link requires the separate local
`python-gex` checkout described in Chapter 17; it is not a promise that
the book repository distributes either gex or the ROMs.

For historical context, Ed Logg's
[2012 Gauntlet postmortem](https://media.gdcvault.com/gdc2012/slides/Design%20Track/Logg_Ed_Gauntlet_Postmortem.pdf)
discusses the original game's development. His
[Centipede affidavit](https://arcadeblogger.com/wp-content/uploads/2019/06/ed-logg.pdf)
and its [context article](https://arcadeblogger.com/2019/06/29/atari-centipedes-hidden-code-trap/)
document an earlier Morse-signature example. These sources establish
context for their own subjects, not undocumented decisions made for
Gauntlet II. The distinction between a surviving mechanism and an
explanation of its author's intent remains part of reading the sources.

[Previous: Reading the ROMs](18_reading_the_roms.md) |
[Contents](README.md)
