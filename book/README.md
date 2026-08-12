# Gauntlet II: How It Works

A guided tour of the inside of a 1986 arcade machine. Gauntlet II put four
people around one cabinet, filled the screen with more monsters than seemed
reasonable, charged for health instead of lives, and did all of it on a
7 MHz processor with 128 KB of game code. This book explains how, working
outward from what a player sees toward the hardware, data structures, and
software that produce it. It is written for a hobbyist programmer: comfortable
with variables, arrays, memory, and hex, but owing no prior knowledge of
68000 assembly, arcade hardware, or this game's internals. Every factual claim
traces to the reverse-engineering documentation in [`doc/`](../doc/INDEX.md),
to the checked audit artifacts generated from the ROM images, or to an
identified external source. Chapters build in order, each ends with an
optional "Under the hood" box pointing at the addresses and documents behind
it, and uncertainty is stated rather than smoothed over.

## Contents

| # | Chapter | What it covers |
|---|---------|----------------|
| 1 | [Enter the Gauntlet](01_how_to_play.md) | What a player does at the cabinet, and which rules give Gauntlet II its character |
| 2 | [Welcome to the Machine](02_introduction.md) | What was reverse engineered, what counts as evidence here, and how to read the book |
| 3 | [The Machine](03_hardware_overview.md) | The 68010, the memory map, the three analyzed ROM images, and who does which job |
| 4 | [Painting the Screen](04_display_system.md) | Tiles, palettes, the playfield, motion objects, the text layer, and layer priority |
| 5 | [Waking Up](05_boot_and_os.md) | Power-on, destructive RAM tests, the real failure paths, the OS, and self-test |
| 6 | [The Heartbeat](06_main_loop.md) | One frame in twenty-eight calls, locked to VBLANK, with a dialog gate and an overload throttle |
| 7 | [From Coin Drop to Game Over](07_session_lifecycle.md) | The whole session as a state machine, with four player lifecycles running inside it |
| 8 | [The World in Memory](08_world_in_memory.md) | Three coordinate spaces, the MOB chain, collision, the camera, and why crowds are possible |
| 9 | [Building and Choosing a Level](09_mazes_and_slapstic.md) | Maze selection, the Slapstic copy-protection chip, the decoder, and the shared random stream |
| 10 | [The Heroes](10_players.md) | Class tables, joining, movement, fighting, magic, health, inventory, power-ups, and IT |
| 11 | [The Horde](11_monsters.md) | One dispatcher for many monsters, generators, type specialties, and hit resolution |
| 12 | [Special Guests](12_dragon_thief_mugger.md) | The three hand-tuned actors that sit outside the general monster engine |
| 13 | [A Living Maze](13_living_maze.md) | Doors, transporters, forcefields, misbehaving walls, treasure rooms, and the secret code |
| 14 | [Keeping Score](14_score_and_economics.md) | Coins into health, scoring, score per coin, the info panel, EEPROM, and operator settings |
| 15 | [The Show](15_attract_and_demo.md) | The attract cycle, the recorded demo, what actually repeats between runs, and the legend |
| 16 | [The Voice](16_sound.md) | The sound board as a second computer, the pair of one-byte latches, and the coins that ride them |
| 17 | [How We Know All This](17_methodology.md) | The evidence ladder, the audits, build fingerprints, a Morse copyright trap, and the limits |
| — | [Glossary and Repository Map](appendix_glossary.md) | Every term of art, where to look things up, source notes, and the publication checklist |

## A note on scope

The sound board is a second computer with its own reverse-engineering history.
Chapter 16 covers the main CPU's side of the conversation and stops at the
latch. Synthesis, music playback, and the speech data are reserved for a
future volume about the sound ROM.

## Images

Raster images live in [`img/`](img/) and are produced from the ROM images by
[`img/generate_images.py`](img/generate_images.py), which drives
[`python-gex`](../python-gex/) plus a little PIL. Running it requires the
Gauntlet II ROMs, which are not distributed here; the repository
[`README.md`](../README.md) lists the parts and checksums needed to build the
three analyzed images. Diagrams are authored inline as Mermaid and need no
files.
