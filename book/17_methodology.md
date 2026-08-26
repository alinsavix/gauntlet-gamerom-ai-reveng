# Chapter 17 — How We Know All This (Methodology and Curiosities)

**This chapter answers:** Where did every claim in this book come from, how
were they checked, and what did the ROMs refuse to say?

**By the end you will understand:** what each tool in this project can and
cannot prove, the machinery that keeps an AI-assisted analysis honest, the
fingerprints the original build left in the code, a copyright trap hidden in
nine bytes nobody ever executes, a whole second game asleep inside the OS ROM,
and where the recoverable evidence stops.

**It builds on:** Chapter 2's overview of the project, and a general
familiarity with everything since.

---

## An evidence ladder

Sixteen chapters of confident sentences deserve an accounting. The claims in
this book rest on different kinds of evidence, and they are not equally
strong.

At the bottom sits **playing the game**, which produces hypotheses and nothing
else. Watching a thief steal your key tells you an event exists. It cannot
tell you which routine ran, what state changed, or why the thief chose you.
Decades of the project owner's notes started here and climbed upward by
guesswork and patience.

Below even that evidentiary rung sit gauntpy's **synthetic scenarios**. A small
ASCII maze can isolate a one-cell passage, arrange an otherwise rare collision,
or deploy a thief at a precise frame. It is valuable because it removes noise,
not because Atari shipped that room. A result seen only there proves how the
Python model responds to invented input. It may motivate a ROM or MAME test, but
it cannot become a claim in this book, the technical references, or the
fidelity invariants until primary evidence independently confirms it. The
fixture, trace, and state dump all retain an explicit synthetic label to keep
that boundary visible.

Above that sits **disassembly**. radare2 turns bytes into instructions, and
this project keeps a checked-in loader script that reconstructs the whole
annotated session: memory maps, symbol names, function boundaries, data
flags. Disassembly proves what an instruction sequence would do if executed.
It proves nothing about whether anything executes it, which is why a
disassembly-only reading can spend hours documenting a routine that has been
dead since 1986.

Above that sit the **reconciliation reports**, and they are where this project
gets its confidence. Two matter most. A control-target report resolves every
call and jump in the image, direct and computed, and reports how many
destinations remain unexplained: currently 1,129 direct sites, 206 indirect,
81 computed-dispatch destinations, zero unresolved. On the OS side the same
report carries 392 site/owner rows across 384 distinct control sites. A RAM-operand report does the same for data, listing every
absolute address the code touches and which functions touch it, with an
independent linear sweep agreeing on all 318 literals in the game ROM. The
first tells you whether code is reachable. The second tells you who can
possibly have written a variable.

Above that sits **execution**. Targeted MAME tracing observes the machine
actually running, which is the only way to settle questions the ROM bytes
cannot answer on their own. MAME's driver source was also the honest citation
for the far side of Chapter 16's sound latch, since nothing in these three
images describes the 6502's wiring. MAME was a secondary aid here rather than
the project's main instrument, and this book cites it wherever a claim
depends on it.

At the top sits **independent reimplementation**. Chapter 13's secret-code
verifier is the clearest example: the algorithm was rebuilt from the
disassembly in Python and then run against codes the real game produced. When
your reimplementation and the arcade cabinet agree on `XXX-XXX`, you
understand the routine. When they disagree, you have learned something more
valuable.

A complete ROM analysis is not the same claim as a complete reimplementation.
The callable inventory currently has 322 entries, while gauntpy's independent
crosswalk classifies 272 live entries as complete and fifty as deliberately
omitted platform/ABI/dead boundaries, with no live entry partial or missing. It also
records explicit Python-only corrections separately: making the attract demo
finish by ignoring a wall or deleting an actor proves only that the recording
was rescued, not that the preceding game state matches the ROM.

## Proving a negative

Two of this book's findings came from a technique worth naming, because it
runs the ladder backwards.

Chapter 15 claims the random number generator is never seeded. That is a
claim about *absence*, and no amount of reading code proves it. What proves it
is exhaustion: scan both ROM images for every occurrence of the four bytes
that encode the seed's address, and find exactly two, both inside the
generator's own wrappers. Nothing else in 192 KB can reach the word. The same
sweep is what the RAM-operand report performs continuously, which is why the
finding survives regeneration.

The technique has a trap, and this project walked into it. Chapter 16 traces
the coin path through an OS routine that appeared to have no callers at all,
because the first sweep looked only for the 68010's 32-bit absolute call
encoding. The game reaches that routine through the 16-bit form, which
addresses the low 64 KB in two fewer bytes and looks nothing like the
pattern being searched for. An exhaustive search is only as exhaustive as the
encodings you remember to include. The correction was to sweep all four forms,
and it turned an apparently orphaned service into the reason quarters work.

## Keeping an AI-assisted pass honest

Chapter 2 said this documentation came from decades of manual work followed
by a much faster AI-assisted pass. The interesting part of that arrangement is
not the speed. It is the discipline required to make the output trustworthy,
because a language model will produce a fluent, plausible, and entirely
invented description of a function all day long.

The project's answer is to refuse to treat a name as evidence. Every one of
the game ROM's 322 callable entries carries a *contract*: purpose, arguments,
return behavior, and any deviation from the normal calling convention. Each
contract is checked by a generator script against the actual bytes, and the
coverage report reconciles all 322 against those checked catalogs. A function
called `find_maze` earns that name only after something mechanical confirms it
takes a maze number and returns a record pointer.

The artifacts are regenerable, which is the load-bearing property. Running
`make check` from the documentation directory rebuilds and re-verifies the
whole set against the ROM images:

| Artifact | What it proves |
|----------|----------------|
| Callable contracts (322 entries) | Every reachable entry has a body-checked ABI |
| Contract coverage | No indexed entry lacks a contract |
| Control targets | Every branch destination is accounted for |
| RAM operands, plus an independent linear sweep | Every absolute data reference has a named owner |
| ROM byte coverage | Every byte is analyzed code or a named range |
| Catalog and flag reconciliation | Every documented table matches a real byte range |
| Maze catalog | All 117 stored records decode |
| Confidence labels | Every chapter section carries a graded claim |

The numbers that suite prints are the audit's actual state: 131,072 game ROM
bytes with 93,722 identified as instructions across 34 executable ranges, 322
catalogued data rows over 321 distinct addresses, 347 non-code flags, eight
intentional overlapping views, 318 RAM literals, all 65,536 OS bytes
classified into 33 segments across 14 top-level regions with 269 contracts and
42 data ranges, and empty failure sets throughout.

Two habits matter more than the totals. The first is that a **contradicted**
claim stays visible. An early draft of this project's documentation asserted
that every function and table was fully understood; later audits disproved it,
and the correction sits in the index where the boast used to be. The
`08_known_issues.md` file is a running log of exactly this, drafting the
chapters of this book has added entries to it more than once, and anything the
latest audit raised but could not close is written down in `SOL_ISSUES.md` at
the repository root.

The second is the confidence grading this book has been quietly obeying
throughout. Verified means checked against bytes. Strong inference means the
evidence points one way with nothing contradicting it. Contradicted means an
earlier claim was disproved and must never be repeated. When a sentence in
this book hedges, the hedge is load-bearing.

## Fingerprints of the original build

The ROM cannot tell you who wrote it. It can tell you a surprising amount
about *how*.

Almost all of the game ROM is compiled C, and its shape is unmistakable. Every
ordinary function opens with `link a6` to establish a frame pointer, saves
callee-saved registers with a `movem`, reads its arguments at positive offsets
from `a6`, and returns a value in `d0`. Arguments are pushed right to left as
32-bit longwords even when the value is a 16-bit word, and the caller cleans
the stack afterward. Registers split into scratch and callee-saved classes
along a consistent line, and the audit records every routine that departs from
it rather than smoothing the exceptions away.

The specific compiler is a different kind of claim. The convention matches
what the Green Hills C compiler produced for 68000 targets, and the
documentation records that as the likely toolchain. There is no build stamp in
the image, so the vendor attribution is inference, and the convention itself is
the part that is verified.

Ed Logg's Gauntlet postmortem complicates the attribution without settling it.
His slide on the programming environment lists a VAX for compiles and edits,
terminals, C as a language still new to the group in the mid-1980s, and then
six words: "Greenhills C post compiler came later." That could place Green
Hills after the original Gauntlet, which would still leave the 1986 sequel
inside the window. It could equally name a Green Hills *post-compiler*, an
optimizer run over another compiler's output, which would account for a
familiar convention arriving by an unfamiliar route. The slide does not say
which, and the bytes cannot arbitrate. What this project can prove is the
convention; the vendor behind it stays an open question.

Hand-written assembly stands out immediately once you know the compiled shape,
because it breaks all of it at once: no frame, no register saves, inputs
arriving in registers or fixed memory, and instructions no compiler emits.
Three examples recur in this book. Chapter 6's input debouncing is built
around a rotate-through-extend instruction doing bit-serial shifting. Chapter
9's Slapstic access needs an exact sequence of reads and writes that no
compiler could be trusted to preserve. And `mob_create`, called constantly by
everything that puts an object in the maze, skips the frame pointer entirely
and reads its arguments straight off the stack pointer, which is a hand
optimization of the ordinary convention rather than a departure from it.

The third fingerprint is everywhere and easy to miss: this game is mostly
tables. Speeds, damage, animation frames, palettes, spawn parameters, maze
records, dragon flight paths, speech phrases, the potion effect matrix, the
2×2 tile descriptors. The code is a small interpreter for a large pile of
authored data, which is what let a handful of people tune a game this varied
inside 128 KB.

## Nine bytes that never run

Inside the game ROM's header block, in a runtime-dead stretch among the hooks
the OS calls, sit nine bytes that nothing reads:

```text
AE D6 8C 17 FB 90 6A 33 80
```

Written out as bits, most significant first, and read as International Morse
code with 0 for a dot and 1 for a dash, they group like this:

```text
-.-. --- .--. -.-- .-. .. --. .... -      COPYRIGHT
.---- ----. ---.. -....                   1986
.- - .- .-. ..                            ATARI
--. .- -- . ...                           GAMES
```

The stream runs 69 bits and the last three bits of the ninth byte are zero
padding. No character or word separators are stored, which is why the grouping
matters: the bitstream is continuous, and the reader has to know where the
letters end. Everything in that block is Verified, including an independent
decode performed while writing this chapter.

What the bytes are *for* is inference, and the historical record is what makes
it a strong one. Atari embedded ownership statements in ROM bits that no
program executes and no player sees, so that a competitor who copied the ROM
would copy the signature along with it. The technique is described in Ed
Logg's affidavit concerning Centipede, which explains a nonfunctional data
pattern read as Morse code and used as evidence of copying. The affidavit is
[available here](https://arcadeblogger.com/wp-content/uploads/2019/06/ed-logg.pdf),
with the story told at
[Atari Centipede's Hidden Code Trap](https://arcadeblogger.com/2019/06/29/atari-centipedes-hidden-code-trap/).

It is a good trap. A bootlegger dumping the ROM copies it without knowing.
Removing it requires understanding that a runtime-dead nine-byte constant in
the header is meaningful, which is precisely the understanding a bootlegger
lacks. And in the reconstructed image the signature is contiguous, though on
the physical board it is split byte by byte across the 7A and 7B chips, so
even reading it off one chip gets you nothing.

## A whole game asleep in the OS ROM

Chapter 5 described the OS ROM as boot code, diagnostics, and shared services.
It is also a graveyard.

Slightly less than half of the 64 KB image is a complete, self-consistent
software module that Gauntlet II never touches. Its executable partition runs
from 0x8000 to 0x9A0F, interrupted by two islands of table data, and the
audit has extracted 34 entry contracts from it: monster updates, direction
choosing, object-list insertion and removal, four directional path probes, a
recursive movement worker, cell-occupancy tests. It is a monster and movement
engine. Beyond it, most of the rest of the image is data: option menus, status
tables, factory high scores, tutorial descriptors, hint text, legend text,
tile descriptors, palettes.

Nothing in Gauntlet II transfers control into any of it. Better than that, the
module gives itself away: it contains absolute calls to three addresses in the
main game ROM which are not callable entry points in this build and land in
the middle of unrelated instruction bodies. It was linked against a different
game.

Which one is not encoded anywhere in the image, but the text leaves little
room. The strings include TREASURE ROOM, YOU HAVE SECONDS TO COLLECT
TREASURES, WARRIOR: VALKYRIE: WIZARD: ELF:, GHOSTS MUST BE SHOT, USE MAGIC TO
KILL DEATH, GAME OVER WHEN HEALTH = 0, and a copyright reading 1985. There is
also an option list, with its own difficulty and health-per-coin menus, that
live Gauntlet II ignores in favor of the stream Chapter 14 described in its
own ROM.

The physical parts settle it. The OS ROM pair in a Gauntlet II cabinet carries
Atari part numbers 136037-1307 and 136037-1308, and MAME loads those same two
parts, at identical checksums, for the 1985 Gauntlet sets and for Gauntlet II
alike. The two games ship the same OS chips. Gauntlet II simply supplies its
own game-support code in its own ROM and leaves its predecessor's asleep in
the shared part.

Treat that as an archaeological curiosity rather than a load-bearing fact. The
runtime-dead status, the byte boundaries, and the 34 contracts are Verified.
The reading that this is the earlier game's support module is Strong
inference, since the original link map is gone and no revision stamp survives.
Comparing this payload against other Atari System 1 era BIOS images is a
follow-up project, not a question this volume needed answered.

## Where the evidence stops

Some questions have no answer in these files, and saying so precisely is part
of the work.

**Build provenance** is gone. There is no compiler version, no build date, no
link map, no source path. The toolchain is an inference from code shape.

**Symbol names** are gone. Every name in this book, `g2mainloop` and
`find_maze` and `player_join` and the rest, was invented by the people
documenting the game to describe what the code does. None of them appeared in
the original source, and some earlier guesses have been contradicted and
renamed as the evidence improved.

**Intent behind dead regions** is unrecoverable. The image contains a handful
of data blocks with no pointer, no cross-reference, and no consumer anywhere:
one large and two small, after this audit moved three former members of the
list back into the living. Their contents and boundaries are documented
exactly. Their purpose is not, and the project's rule is that an appealing
geometric pattern in a dead block does not earn a semantic label. The same
applies to 6,196 bytes of solid 0xFF sitting between two live regions, about
five percent of the ROM, for which the image encodes no reason.

**Physical open-bus values** cannot come from a ROM dump at all. Decoded but
unpopulated sockets return whatever the board's electrical state produces, and
no normal game path depends on the answer.

The distinction those four share is worth stating plainly, because it governs
how the whole project reports itself. An **unanswered historical question**
asks about people, decisions, and build environments that were never encoded
in the shipped artifact. An **undocumented runtime behavior** would be a gap in
the analysis of something the artifact does contain. This project's backlog
has none of the second kind left for the game and OS images. What remains is
entirely the first kind, and no amount of further disassembly will close it.

## Where to go next

If this book worked, it left you wanting the primary material.

The maintained technical documentation lives in `doc/`, starting at its index,
and it is the full-strength version of everything here: hardware, the OS ROM,
game ROM structure, subsystems, the data reference, the maze catalog, the
function index, and the known-issues log. The generated audits and their
Python generators sit alongside it and can be re-run against your own ROM
images. The radare2 loader script rebuilds the annotated disassembly session,
which is the fastest way to start poking at something yourself.

For graphics and maze data, `python-gex` decodes and renders tiles, sprites,
stamps, and all 117 maze records. Several images in this book came straight
out of it.

Two larger threads are open. The sound ROM has its own reverse engineering
behind it and deserves the future volume Chapter 16 promised: synthesis,
music, and the speech data that says your name. And the retained module above
invites a comparison against other Atari BIOS images of the period, which
would turn a strong inference into a settled one.

The appendix that follows collects the vocabulary this book introduced and
maps the repository, so you know which file answers which kind of question.

---

> **Under the hood**
>
> - Project overview, ROM inventory, and the corrected coverage claims:
>   `doc/INDEX.md`; assembly instructions for the three images and their
>   checksums are in the repository `README.md`.
> - Calling convention, register classes, and the hand-written-assembly tells:
>   `doc/03_game_rom_structure.md` §3.1–3.6. Named examples: `input_debounce`
>   (0x40644, `roxl`), the Slapstic helpers (0x56E58/0x56E6E), and the
>   frameless `mob_create` (0x5DC58).
> - The Green Hills attribution and its counterweight: the convention is in
>   `doc/03_game_rom_structure.md` §3.1; the "Greenhills C post compiler came
>   later" line is slide 18 of Ed Logg's 2012 GDC
>   [Gauntlet Postmortem](https://media.gdcvault.com/gdc2012/slides/Design%20Track/Logg_Ed_Gauntlet_Postmortem.pdf),
>   which covers the 1985 original rather than this 1986 sequel.
> - Coverage figures: `doc/03_game_rom_structure.md` §4.1–4.2 and the
>   `make check` output. The unused block is 0x55620–0x56E53 (§4.5); the
>   blocks that remain genuinely unreferenced are 0x57BD8–0x57EB9,
>   0x571D8–0x571D9, and 0x5870C–0x58749 (§4.4). Three ranges once listed
>   there — 0x5C8B0, 0x57332, and 0x57358 — turned out to have live
>   consumers.
> - Audit generators and artifacts: `doc/generated/`, with the regeneration
>   entry point `make check` in `doc/`. The loader is
>   `doc/gauntlet_loader.r2`.
> - Morse signature: 0x4009C–0x400A4, `doc/03_game_rom_structure.md` §1.3.
>   The nine bytes are `AE D6 8C 17 FB 90 6A 33 80`; the 69-bit stream was
>   re-decoded independently for this chapter and matches, with three zero
>   padding bits.
> - Retained OS module: executable partition 0x8000–0x9A0F with two data
>   islands, 34 entry contracts, and stale absolute calls to 0x48064,
>   0x49C36, and 0x49572; data partition 0x9A10–0xF9F9 in thirteen groups,
>   with 0xF9FA–0xFFFF verified zero fill: `doc/02_os_rom.md` §10.5, strings
>   in §12.4–12.8. The shared part numbers 136037-1307.9a and 136037-1308.9b
>   appear in MAME's `src/mame/atari/gauntlet.cpp` under `gauntlet`,
>   `gauntletj`, `gaunt2`, `gaunt22p`, and `gaunt22p1` at identical SHA-1
>   digests, which match the images used by this project.
> - Unresolvable questions, stated as such: `doc/08_known_issues.md`, section
>   "Unresolvable from the supplied artifacts"; still-open audit findings:
>   `SOL_ISSUES.md` at the repository root.
> - The reimplementation standard in practice: Chapter 13's `secret_code_build`
>   reproduction, checked against codes generated by the running game.
