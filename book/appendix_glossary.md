# Appendix — Glossary and source guide

Use this as a quick way back into the book. The technical references
below provide addresses, tables, and detailed contracts when a definition
is not enough.

## The words that distinguish things

**Active low.** An input convention in which zero means a switch is
pressed. Important when reading raw joystick bytes or demo records.

**Alpha layer / text layer.** The character grid over the playfield and
sprites. An opaque cell can hide what is beneath it even when its
character is blank. [Painting the dungeon](05_painting_the_dungeon.md).

**Attract mode.** The idle game's cycle of scores, title, recorded
demonstration, and legend pages. [Attract and demo](15_attract_and_demo.md).

**Bank switching.** Selecting which part of a larger ROM appears in a
smaller address window. [Mazes and Slapstic](09_mazes_and_slapstic.md).

**Byte / word / longword.** Here, values of 8, 16, and 32 bits.
The 68010 stores multibyte values big-endian: most significant byte first.

**Debouncing.** Filtering mechanical switch bounce with a history of
input samples. [The game's clock](07_the_games_clock.md).

**Dialog gate.** The main-loop condition that suspends a block of gameplay
updates while a message remains active. The rest of the machine continues.

**EEPROM.** Electrically erasable persistent memory for settings and
records. Unlike working RAM, it retains information without power.
[Waking the cabinet](16_waking_the_cabinet.md).

**Frame / VBLANK.** A frame is a game update; VBLANK is the display's
vertical blanking interval, whose interrupt supplies its normal pacing.
The two should not be confused when an update runs long.

**Game mode.** State distinguishing ordinary play, transitions, and
attract presentations. Individual subsystems also have their own gates.

**Generator.** An object that creates ordinary monsters when its
timing, random-chance, processor-load, and placement conditions permit.
[The horde](04_the_horde.md).

**Hook.** A game-provided entry through which the OS invokes game-specific
work. An OS service is the opposite direction: the game calls shared code.

**Interrupt.** A hardware event that redirects the CPU to a handler,
such as the display's VBLANK or a sound-board reply.

**IT.** The tag state that makes one player a preferred monster target
and can pass through player contact. [Four players](03_four_players.md).

**Level / maze.** Level is progression depth. Maze is a stored layout.
A maze can be selected at different levels, with different applicable rules.

**Level flags.** Packed settings for a maze's behavior, such as wrapping,
moving walls, or special monster movement.

**MOB.** Motion object: a sprite slot described by parallel hardware
arrays, with additional software state. The same record participates
in gameplay. [A world in ten bytes](06_a_world_in_ten_bytes.md).

**Palette.** Colors selected by stored pixel indices. Changing palette
data can animate color without changing the picture.

**Pixel / tile / cell.** A pixel is one picture element; a playfield
tile is 8 by 8 pixels; a logical maze cell spans 16 by 16 pixels.
These are related coordinate spaces, not interchangeable units.

**Player position / class.** Position identifies one of four color-coded
control stations. Class identifies the chosen Warrior, Valkyrie, Wizard,
or Elf. [How to play](01_how_to_play.md).

**Playfield.** The scrolling tile layer representing the dungeon, larger
than the visible camera window.

**RNG.** Random-number generator. Its evolving state and the order of
requests determine the resulting sequence.

**Score per coin.** A player's score divided by their coin count, used
for the high-score ladders. [What a quarter buys](08_what_a_quarter_buys.md).

**Shot channel.** A reserved projectile slot. Channel occupancy is part
of what determines when another ordinary shot can be created.
[One arrow](02_one_arrow.md).

**Slapstic.** The protection device controlling access to banks of level
data through particular memory-access sequences.

**SLIP.** Starting link point: a display-band entry into the shared
motion-object chain, not a separate sprite list for every band.

**Slot.** An index into the MOB arrays. For cell-bound objects the slot
encodes maze location; reserved effect and projectile slots need
additional positioning and ordering information.

**Sound latch.** A one-byte handoff between processors. The outgoing
command latch and incoming response latch have different roles.
[A machine that speaks](14_a_machine_that_speaks.md).

**Stamp.** Four playfield tiles arranged as a 2-by-2 block, matching
one logical maze cell.

**Synthetic scenario.** A constructed test situation. It can isolate
behavior in gauntpy without establishing that the original game ever
created that situation. [gauntpy](17_gauntpy.md).

**Tier.** A strength stage. Ordinary monsters store it through the
horizontal-position word's palette field; generators use distinct
object types for their strength stages.

**Watchdog.** A hardware timer that resets the board if software stops
servicing it. Resetting execution is not repairing the cause.

## Where to look in the repository

| Question | Starting point |
|---|---|
| How is the board organized? | [Hardware reference](../doc/01_hardware.md) |
| What runs during boot or self-test? | [OS ROM](../doc/02_os_rom.md) |
| What is the main-loop order? | [Game ROM structure](../doc/03_game_rom_structure.md) |
| How does a gameplay mechanism work? | [Game subsystems](../doc/04_game_subsystems.md) |
| What does this address or table contain? | [Data reference](../doc/05_data_reference.md) |
| Which stored maze am I looking at? | [Maze catalog](../doc/06_maze_catalog.md) |
| What does this named routine take and return? | [Function index](../doc/07_function_index.md) |
| How can I inspect or reproduce an observation? | [gauntpy guide](17_gauntpy.md), [package README](../gauntpy/README.md) |
| How are ROM assets decoded? | [gex](../python-gex/README.md) |
| Where are checked tables and the disassembly setup? | [Generated-reference guide](../doc/generated/README.md), [radare2 loader](../doc/gauntlet_loader.r2) |

Start with the [technical index](../doc/INDEX.md) for the wider reference.
For what these sources can establish, return to
[Reading the ROMs](18_reading_the_roms.md).
