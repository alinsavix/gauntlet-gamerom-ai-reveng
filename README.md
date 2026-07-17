# Gauntlet Game ROM Reverse Engineering with AI

## What

I (Alinsa) have been slowly reverse engineering parts of the Gauntlet II arcade game for... uhhh... a long time. I had previously had great success using AI to reverse engineer the Gauntlet sound ROMs, and wanted to see if it could do the same thing with the game ROM -- the main 68010 code that actually runs the game.

The game ROM is a much larger target than the sound ROM, but is also more tractable -- there's lots of text strings and sound effect numbers to help identify code sections, a little bit of time in MAME makes it easy to find the main loop and its major chunks, etc. So larger, but less mind-breaking to work with.

The Gauntlet II game ROM image is 128 KB and mixes compiled C, hand-written 68010 assembly, ROM-resident data, and padding. I've figured out a pretty significant chunk of the game ROM already, over the last decades, and I also provided the AI with much of this information (memory locations, function names, descriptions, etc) and a description of the hardware behavior, as a starting point to build on.

Although the results were not as impressive as the results of having the AI reverse engineer the sound ROMs (partially because the starting point was already fairly advanced) -- and I had to push it a lot more and be a lot more specific about the exact things I wanted it to work on -- the results are still fairly admirable. I feel like they need a human-based cleanup pass to better organize the findings, though!

The maintained audit now covers 321 callable game-ROM entries and 329 cataloged ROM-data ranges, along with a host of finer details about parts of the code I was already mostly familiar with.

## Results

The maintained reverse-engineering documentation is under [`doc/`](doc/INDEX.md). Start with [`doc/INDEX.md`](doc/INDEX.md), which links the hardware, OS, game-ROM, subsystem, data-reference, maze-catalog, function-index, and known-issues chapters.

Machine-readable CSV artifacts and their Python generators are kept together under [`doc/generated/`](doc/generated/README.md). The supported radare2 loader is [`doc/gauntlet_loader.r2`](doc/gauntlet_loader.r2).

## Finally

This project, combined with the sound ROM project, represents a pretty thorough reverse engineering of Gauntlet II. Between the OS ROM, the sound ROM, and the game ROM, the vast majority of the game's code is documented and understood, over the course of a few weeks -- far better than spending decades accomplishing less! (...though a lot of that work *did* make *this* work possible)

Still pretty cool, though.

--A


## Appendix: ROMs

The actual game ROMs from Gauntlet II are not included in this repository, for copyright reasons. If you want to make your own matching ROMs to use with the information here, you will need:

### Game ROM (row76.bin)

| Part Number | Board Location | Size | sha1sum |
|-------------|----------------|------|---------|
| 136043-1121.6a | 6A | 32kB | 3d93236aaffe6ef692e5073b1828633e8abf0ce4 |
| 136043-1122.6b | 6B | 32kB | 378c582c360440b808820bcd3be78ec6e8800c34 |
| 136043-1109.7a | 7A | 32kB | 7f51184840e3c96574836b8a00bfb4a7a5f508d0 |
| 136043-1110.7b | 7B | 32kB | dfce027ea50188659907be698aeb26f9d8bfab23 |

These need to be interleaved with the "A" ROMs as even bytes and the "B" ROMs as odd bytes, then concatenated row 7 followed by row 6, to form:

| File | Size | sha1sum |
|------|------|---------|
| row76.bin | 128kB | decbe6438b3a2618bd7fe79d14be034efadd7ff4 |

### Slapstic/Level Data ROM (row10.bin)

| Part Number | Board Location | Size | sha1sum |
|-------------|----------------|------|---------|
| 136043-1105.10a | 10A | 16kB | a9a03150f5a0ad6ce62c5cfdffb4a9f54340590c |
| 136043-1106.10b | 10B | 16kB | d2df4e5b036500dcc537a1e0025abb2a8c730bdd |

These need to be interleaved (as per above) to form:

| File | Board Location | Size | sha1sum |
|------|----------------|------|---------|
| row10.bin | — | 32kB | e4a36380f4a6394ad5cfb5aff5d7c8b352232d3d |

### OS ROM (row9.bin)

| Part Number | Board Location | Size | sha1sum |
|-------------|----------------|------|---------|
| 136037-1307.9a | 9A | 32kB | d5fa19e028a2f43658330c67c10e0c811d332780 |
| 136037-1308.9b | 9B | 32kB | 7467b2ec21b1b4fcc18ff9387ce891495f4b064c |

These need to be interleaved (as per above) to form:

| File | Size | sha1sum |
|------|------|---------|
| row9.bin | 64kB | 6e0d2026317e4a050fd79aac24ee0a644bf5a836 |
