# Chapter 2 — Welcome to the Machine (Introduction)

**This chapter answers:** What exactly was reverse engineered, what kind of
evidence is this book built on, and how should you read it?

**By the end you will understand:** what "reverse engineering" means for a
1986 arcade board, which pieces of Gauntlet II were analyzed and how
thoroughly, how the book signals its confidence in each claim, and the one
big architectural idea, a single loop ticking with the display, that
organizes everything to come.

**It builds on:** Chapter 1's picture of the game as the player sees it. From
here on, we work inward.

---

## Why this machine deserves a book

Chapter 1 described a game that runs four players at once, crowds of monsters
dense enough to dig through, a talking cabinet with a sense of humor,
wandering exits, a thief with a targeting algorithm, and a mail-in contest
implemented in code, all on hardware from 1986.

The program and level data behind that fit in 224 kilobytes: a 64 KB
operating-system ROM, a 128 KB game ROM, and a 32 KB level-data ROM. (Artwork
and sound have their own chips, and we'll meet them later.) Most web pages you
loaded this morning are larger, and that compression is what makes Gauntlet II
worth a guided tour. The machine is a complete, honest example of how
commercial games were built in the era: an operating system that publishes an
API, a compiled-C game sitting on top of it, hand-tuned assembly in the places
where speed mattered, and data tables driving the rest. It also stays small
enough that one book can walk through all of it without hand-waving. When
Chapter 11 explains how monsters decide where to walk, the explanation comes
from the instructions Atari shipped.

Two questions run in parallel from here on, chapter by chapter: *what does the
player experience?* and *what do the hardware, the data, and the software do
to produce it?*

## What "reverse engineered" means here

Nobody involved in this project has Atari's source code. What exists is what
every Gauntlet II cabinet carries: ROM chips full of bytes. **Reverse
engineering** means recovering the story from those bytes alone, separating
code from data, tracing what each routine reads and writes, decoding the
tables, and testing interpretations against the running game until the machine
has no more secrets *about what it does*. (What its authors were thinking is a
different matter, discussed below.)

This particular effort came in two waves. The project's owner spent, in their
words, a long time over a couple of *decades* manually reverse engineering
parts of the game: memory locations, function behavior, hardware quirks. That
accumulated knowledge then seeded a much faster AI-assisted pass, which
extended the analysis across the full ROMs and built *audits*, meaning
machine-checked inventories that verify the documentation against the actual
bytes. A claim like "this routine takes these arguments" now has a script
standing behind it, re-checking the ROM image on demand.

One consequence of having no source code deserves calling out now, because the
whole book depends on it: **every name you will read is a modern label.** When
later chapters talk about `g2mainloop` or `find_maze` or `player_join`, those
are names the project assigned to describe observed behavior. Whatever Atari's
programmers called the same routines is unrecoverable, since the shipped code
carries no symbols.

## The cast of chips

Chapter 3 tours the hardware properly. Here is the headline version, enough to
make the rest of this chapter work.

A Gauntlet II board is a small committee:

- **One main CPU**, a Motorola 68010, runs the operating system and the game
  itself: every rule, monster, and score you met in Chapter 1.
- **A second, separate computer** handles sound. It has its own processor (a
  6502) and 48 KB of its own ROM holding program and speech data alike,
  entirely separate from the three images below. The main CPU sends it short
  commands over a wire, along the lines of "play the food sound" or "say
  *Blue Warrior is about to die*."
- **Video hardware** draws the screen. The CPU never paints pixels. It writes
  *descriptions* into video memory, in the form of tile numbers, sprite
  records, and palette choices, and dedicated hardware turns those tables into
  a picture sixty times a second.
- **Three ROM images** hold the analyzed software: the **OS ROM** (boot,
  self-test, and shared services), the **game ROM** (all the gameplay), and
  the **Slapstic ROM** (the stored level data, reached through a
  copy-protection chip that gets its own war story in Chapter 9). Additional
  physical ROMs hold the graphics artwork, data this book's renderings lean
  on, though those chips live outside its three main subjects, as does the
  sound board's 48 KB.

The CPU spends its time writing descriptions, and other hardware does the
drawing. That division of labor explains more about this machine's design than
any other single fact.

## What "thoroughly documented" means

An early draft of this project's documentation claimed the ROMs were fully
understood, and later audits contradicted the claim. The precise version, the
one every chapter here stands on, is narrower and checkable.

For the **game ROM and OS ROM**, the documentation has *byte-level
accounting*: every one of the bytes in both images is classified, whether as
analyzed instructions (about 94 KB of them in the game ROM, across 34
executable regions), as named and cataloged data tables, or as explicitly
identified padding and dead residue. No byte is "mystery meat." On top of
that, every routine that can be called, meaning 322 entries in the game ROM
plus the OS's public services and internals, has a *checked contract* covering
its arguments, returns, and side effects, verified by scripts against the ROM
bytes.

For the **Slapstic ROM**, dedicated tooling decodes and validates all 117
stored maze records, and renders them to images that can be compared against
the running game.

Plenty of questions stay open, and they fall into two bins. Some things cannot
be known from ROM bytes at all, such as why a programmer chose something or
what a dead block of code was originally for; the code proves what it does far
more often than why. A few other behaviors need evidence beyond static
reading, such as a live trace, a cabinet, or a schematic, and the
documentation says so where that applies. This book inherits both kinds of
honesty.

## How to read this book

A few ground rules, so the machinery of the book stays out of your way:

**Chapters build in order.** Each one relies only on concepts introduced
before it, and when a later chapter needs an earlier idea, it says so with a
pointer. Front to back is the supported configuration. Skipping ahead carries
some risk, though the pointers will help you recover.

**"Under the hood" boxes are optional.** Every chapter ends with one: a short
list mapping the chapter's mechanisms and names to ROM addresses and to the
technical documentation in `doc/`, which remains the full-strength reference.
The chapter bodies stay free of raw addresses. Skip every box and the book
still works. Read them when you want to verify a claim or keep digging, since
each box is a trailhead.

**Confidence is stated honestly.** The underlying documentation labels every
finding: **Verified** (proven from the bytes and their consumers), **Strong
inference** (multiple observations agree, final proof absent), and weaker
grades down to claims that later evidence **Contradicted**. This book states
Verified material as plain fact and softens anything below it with wording
like "evidently" or "consistent with." A contradicted claim never appears
here, however beloved. Where a fun story is a story, it will be labeled lore.

**There's a glossary.** Every term of art (MOB, playfield, VBLANK, Slapstic,
attract mode, and friends) is defined when first introduced and again in the
appendix, alongside a map of the repository for readers who want the raw
materials.

One scope note: the sound board is a whole second computer with its own
reverse-engineering saga, and it gets its own future volume. This book covers
the main CPU's side of the conversation, what gets said to the sound board and
when (Chapter 16), and stops at that wire.

## The heartbeat, briefly

After the machine boots, everything you watched in Chapter 1 gets advanced by
**one loop** in the game ROM, which the project named `g2mainloop`. Input,
monsters, health, the thief's schemes, the scroll of the camera, the attract
mode's screens: all of it. The display hardware finishes drawing a frame sixty
times each second and raises a flag; the loop waits for that flag, runs one
update of the whole world, and goes back to waiting. Sixty heartbeats a
second, every second, from the moment the attract mode first appears until
someone pulls the plug.

That synchronization is why the game feels the way it does, why time in
Gauntlet II is counted in frames, and why this book keeps measuring things in
sixtieths of a second. Chapter 3 shows the hardware that makes the heartbeat
possible. Chapters 4 and 5 cover the display and the boot sequence on either
side of it, and Chapter 6 slows down to walk through one single beat, call by
call.

---

> **Under the hood**
>
> - The project's own account of its history, scope, and ROM assembly
>   instructions (chip pairings, interleaving, checksums): `README.md` at the
>   repository root.
> - The documentation index, analyzed-image table (OS 64 KB, game 128 KB,
>   Slapstic 32 KB), and audit status summary: `doc/INDEX.md`.
> - Byte-level accounting for the game ROM (93,722 instruction bytes across
>   34 executable ranges; gap-free region union):
>   `doc/generated/rom_regions.csv` and `doc/generated/rom_byte_coverage.csv`;
>   for the OS ROM: `doc/generated/os_rom_regions.csv` and
>   `doc/generated/os_rom_byte_coverage.csv`.
> - The 322 checked game-ROM callable contracts:
>   `doc/generated/callable_contract_coverage.csv`; the OS ROM's 269-row
>   contract union: `doc/generated/os_all_function_contracts.csv`.
> - Validation of all 117 stored maze records and their rendered images: the
>   `python-gex/` test suite and `doc/06_maze_catalog.md` with
>   `doc/generated/maze_catalog.csv`.
> - The five canonical confidence labels and the script that enforces them in
>   every documentation section: `doc/check_confidence_labels.py`; the honest
>   list of remaining unresolved questions: `doc/08_known_issues.md` and the
>   repository-root `SOL_ISSUES.md`.
> - The main loop teased above is `g2mainloop` (0x42A66); its verified call
>   sequence and VBLANK semaphore (the word at 0x904002) are in
>   `doc/03_game_rom_structure.md` §2.
