# Chapter 2 — Welcome to the Machine (Introduction)

**This chapter answers:** What exactly was reverse engineered, what kind of
evidence is this book built on, and how should you read it?

**By the end you will understand:** what "reverse engineering" means for a
1986 arcade board, which pieces of Gauntlet II were analyzed and how
thoroughly, how the book signals its confidence in each claim, and the one
big architectural idea — a single loop ticking with the display — that
organizes everything to come.

**It builds on:** Chapter 1's picture of the game as the player sees it. From
here on, we work inward.

---

## Why this machine deserves a book

Chapter 1 described a game that runs four players, crowds of monsters dense
enough to dig through, a talking cabinet with a sense of humor, wandering
exits, a thief with a targeting algorithm, and a mail-in contest implemented
in code — all at once, on hardware from 1986.

The program and level data that do this fit in 224 kilobytes: a 64 KB
operating-system ROM, a 128 KB game ROM, and a 32 KB level-data ROM. (The
artwork and sound have their own chips; we'll meet them later.) That's
smaller than the web page you probably read this morning, and it is exactly
this compression that makes Gauntlet II worth a guided tour. The machine is
big enough to be a complete, honest example of how commercial games were
really built — an operating system with an API, a compiled-C game on top,
hand-tuned assembly where it counted, and everything else driven by data
tables — yet small enough that one book can walk through the whole thing
without hand-waving. When Chapter 11 says "monsters decide where to walk like
*this*," it isn't a simplified fable; it's what the shipped instructions do.

So the book runs two questions in parallel, chapter by chapter: *what does
the player experience?* and *what do the hardware, the data, and the software
actually do to produce it?* Chapter 1 was the last chapter that only asked
the first question.

## What "reverse engineered" means here

Nobody involved in this project has Atari's source code. What exists is what
every Gauntlet II cabinet carries: ROM chips full of bytes. **Reverse
engineering** means recovering the story from those bytes alone — separating
code from data, tracing what each routine reads and writes, decoding the
tables, and testing interpretations against the running game until the
machine has no more secrets *about what it does*. (What its authors were
thinking is a different matter — more on that below.)

This particular effort came in two waves. The project's owner spent — their
words — a long time over a couple of *decades* manually reverse engineering
parts of the game: memory locations, function behavior, hardware quirks. That
accumulated knowledge then seeded a much faster AI-assisted pass, which
extended the analysis across the full ROMs and, just as importantly, built
*audits*: machine-checked inventories that verify the documentation against
the actual bytes, so that a claim like "this routine takes these arguments"
isn't just something a human once believed, but something a script re-checks
against the ROM image.

One consequence of having no source code deserves calling out now, because
the whole book depends on it: **every name you will read is a modern label.**
When later chapters talk about `g2mainloop` or `find_maze` or `player_join`,
those are names the project assigned to describe observed behavior. The
original programmers' names for them are unrecoverable — Atari's are lost to
us, and the code doesn't carry them.

## The cast of chips

Chapter 3 tours the hardware properly; here is the headline version so the
rest of this chapter makes sense.

A Gauntlet II board is a small committee:

- **One main CPU** — a Motorola 68010 — runs the operating system and the
  game itself: every rule, monster, and score you met in Chapter 1.
- **A second, separate computer** handles sound. It has its own processor
  (a 6502) and 48 KB of its own ROM — program and speech data alike, entirely
  separate from the three images below; the main CPU just sends it short
  commands — "play the food sound," "say *Blue Warrior is about to die*" —
  over a wire.
- **Video hardware** draws the screen. Crucially, the CPU does not paint
  pixels: it writes *descriptions* — tile numbers, sprite records, palette
  choices — into video memory, and dedicated hardware turns those tables into
  a picture, sixty times a second.
- **Three ROM images** hold the analyzed software: the **OS ROM** (boot,
  self-test, and shared services), the **game ROM** (all the gameplay), and
  the **Slapstic ROM** (the stored level data, reached through a
  copy-protection chip that will get its own war story in Chapter 9).
  Additional physical ROMs hold the graphics artwork — data this book's
  renderings lean on, though the chips themselves, like the sound board's
  48 KB, live outside its three main subjects.

If you take one idea from this list, take the third: *the CPU mostly
describes; other hardware does.* That division of labor explains more of this
machine's design than any other single fact.

## What "thoroughly documented" means — precisely

It is easy to claim a ROM is "fully understood," and this project's own
history shows why you shouldn't say it loosely: an early draft of the
documentation made exactly that claim, and the later audits contradicted it.
So here is the precise version, and it's what every chapter of this book
stands on.

For the **game ROM and OS ROM**, the documentation has *byte-level
accounting*: every one of the bytes in both images is classified — as
analyzed instructions (about 94 KB of them in the game ROM, across 34
executable regions), as named and cataloged data tables, or as explicitly
identified padding and dead residue. No byte is "mystery meat." On top of
that, every routine that can be called — 321 entries in the game ROM, plus
the OS's public services and internals — has a *checked contract*: its
arguments, returns, and side effects, verified by scripts against the ROM
bytes rather than trusted from prose.

For the **Slapstic ROM**, dedicated tooling decodes and validates all 117
stored maze records, and renders them to images that can be compared against
the running game.

What thoroughness does *not* mean: that every question is answered. The
honest remainder falls into two bins. First, some things are not knowable
from ROM bytes at all — why a programmer chose something, what a dead block
of code was originally for. The code proves what it does far more often than
why. Second, a few behaviors need evidence beyond static reading — a live
trace, a cabinet, a schematic — and the documentation says so instead of
guessing. This book inherits both kinds of honesty.

## How to read this book

A few ground rules, so the machinery of the book stays out of your way:

**Chapters build in order.** Each one relies only on concepts introduced
before it, and when a later chapter needs an earlier idea, it says so with a
pointer. Reading front to back is the supported configuration; skipping ahead
is at your own risk (though pointers will help you recover).

**"Under the hood" boxes are optional.** Every chapter ends with one: a short
list mapping the chapter's mechanisms and names to ROM addresses and to the
technical documentation in `doc/`, which remains the full-strength reference.
The chapter bodies themselves stay free of raw addresses. If you never read a
single box, the book still works; if you want to verify a claim or keep
digging, the box is your trailhead.

**Confidence is stated honestly.** The underlying documentation labels every
finding — **Verified** (proven from the bytes and their consumers), **Strong
inference** (multiple observations agree, final proof absent), and weaker
grades down to claims that were outright **Contradicted** by later evidence.
This book states Verified material as plain fact, softens anything less
("evidently," "consistent with"), and never repeats a contradicted claim, no
matter how beloved. Where a fun story is just a story, it will be labeled
lore, not fact.

**There's a glossary.** Every term of art — MOB, playfield, VBLANK, Slapstic,
attract mode, and friends — is defined when first introduced and again in the
appendix, alongside a map of the repository for readers who want the raw
materials.

And one scope note: the sound board is a whole second computer with its own
reverse-engineering saga, and it gets its own future volume. This book covers
the main CPU's side of the conversation — what gets said to the sound board
and when (Chapter 16) — and stops at that wire.

## The heartbeat, briefly

Here is the teaser that frames the next four chapters.

After the machine boots, essentially everything you watched in Chapter 1 —
input, monsters, health, the thief's schemes, the scroll of the camera, the
attract mode's screens — is advanced by **one loop** in the game ROM, which
the project named `g2mainloop`. The display hardware finishes drawing a frame
sixty times each second and raises a flag; the loop waits for that flag,
runs one update of the whole world, and goes back to waiting. Sixty
heartbeats a second, every second, from the moment the attract mode first
appears until someone pulls the plug.

That synchronization is why the game feels the way it does, why time in
Gauntlet II is counted in frames, and why this book keeps measuring things in
sixtieths of a second. Chapter 3 shows the hardware that makes the heartbeat
possible, Chapters 4 and 5 show the display and the boot sequence on either
side of it — and Chapter 6 slows down and walks through one single beat, call
by call.

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
> - The 321 checked game-ROM callable contracts:
>   `doc/generated/callable_contract_coverage.csv`; the OS ROM's 256-row
>   contract union: `doc/generated/os_all_function_contracts.csv`.
> - Validation of all 117 stored maze records and their rendered images: the
>   `python-gex/` test suite and `doc/06_maze_catalog.md` with
>   `doc/generated/maze_catalog.csv`.
> - The five canonical confidence labels and the script that enforces them in
>   every documentation section: `doc/check_confidence_labels.py`; the honest
>   list of remaining unresolved questions: `doc/08_known_issues.md`.
> - The main loop teased above is `g2mainloop` (0x42A66); its verified call
>   sequence and VBLANK semaphore (the word at 0x904002) are in
>   `doc/03_game_rom_structure.md` §2.
