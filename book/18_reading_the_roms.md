# 18. Reading the ROMs

The starting point of this project was not an empty prompt. Alinsa had
spent decades investigating Gauntlet II, collecting addresses, names,
behavioral observations, and descriptions of the hardware. An AI-assisted
reading built on that work. The resulting account still needs a human
owner: someone responsible for what a name means, which evidence
supports a sentence, and where the explanation stops.

Fluent prose is especially dangerous here because the machine cannot
object to a plausible story. A routine may look like a targeting function,
and a suggestive constant may resemble a distance. Neither impression
establishes who calls it or how the result is used.

## What would it take to explain one arrow?

Return to [the arrow from the beginning](02_one_arrow.md). On screen,
you see a projectile leave the Elf, hit something, and disappear. Begin
with a narrower question than “How does combat work?” Ask what permits
another shot to be created.

The investigation starts at the Fire-input consumer in `main_handle_shots`.
Follow its conditions to the reserved player-shot channel and the writes
that initialize a projectile. Record the input state, the occupied or
empty channel, the player identity, and the fields written on creation.
A function name is a bookmark for this chain, not a substitute for it.

Then follow the existing projectile. The collision search chooses a
candidate; `resolve_shot_hit` decides what that candidate means and
whether the shot is consumed. A monster hit can change the target's
strength and award score. Other targets and powers take different
branches. The caller's response to the return value matters as much as
the branch inside the hit routine: this is where a projectile's remaining
life becomes another future opportunity to fire.

Now the screen has a checkable explanation. A targeted runtime trace
can observe the input, channel creation, target change, and retirement.
Testing a surviving-shot case as well as a consumed-shot case checks
the distinction rather than merely confirming one successful hit.
The useful product is a chain from creation to consequence, with the
conditions at each link still attached.

## Which evidence answers which question?

The ROM image supplies the bytes. Disassembly gives those bytes an
instruction-level reading, but it must distinguish code from data and
recognize the ways control can arrive at an entry. Following callers,
tables, and state consumers makes that reading meaningful. Addresses
also need their context: a banked window is not a single unchanging
piece of storage.

Runtime observation supplies another view. A trace from MAME shows the
emulated machine taking a particular path under particular conditions.
It can settle whether an event occurs in that run, but it is not an
exhaustive survey of every possible state. Hardware wiring and historical
claims need suitable sources beyond the main CPU's instruction bytes.

`gauntpy` makes hypotheses executable and state convenient to inspect.
Agreement with an independently observed ROM run is useful corroboration.
Agreement between two Python functions based on the same interpretation
is weaker: they may share the same assumption. A synthetic scenario
demonstrates the model's behavior in a constructed situation, not that
Atari shipped that room.

Machine checks are valuable without being semantic proof. A table can
match its ROM bytes exactly while its purpose is misunderstood. Complete
address coverage can coexist with a mistaken explanation of a branch.
Checking contracts, ranges, and control targets reduces particular
uncertainties; it does not make the surrounding prose automatically true.

Absence claims need similar restraint. Scanning for a variable's literal
address can find direct references. It cannot, by itself, rule out access
through a register, an indexed base, a block clear, or another alias.
“No direct initialization was found in these paths” is a different claim
from “this word can never be initialized.”

## What can the ROM never tell us?

The labels used throughout this book are modern descriptive names, not
recovered Atari source symbols. Calling conventions can reveal how
arguments and results travel without uniquely identifying a compiler
vendor. Unused material can be described without knowing why it was
retained.

Likewise, a rule that produces effective play does not establish why its
author chose it. Credits identify people; interviews and contemporary
documents may describe decisions. Bytes establish mechanisms. Keeping
those sources distinct does not diminish the game. It lets the reader
enjoy an explanation without being asked to mistake a good story for
something the surviving evidence actually says.

### For the full chapter

Expand the arrow investigation with a short disassembly excerpt and a
matching runtime observation. Add a compact sidebar on compiler
fingerprints, the Morse copyright pattern, and retained OS material,
separating decoded facts from historical interpretation.

### Source notes

- Project background: [repository introduction](../README.md);
  earlier manual material: [game-ROM notes](../refs/GAME_ROM_KNOWN.md).
- Projectile contracts and consequences:
  [subsystems](../doc/04_game_subsystems.md), §26, and
  [function index](../doc/07_function_index.md), projectile/combat entries.
- Reproducible inspection: [radare2 loader](../doc/gauntlet_loader.r2) and
  [generated reference guide](../doc/generated/README.md). Calling
  conventions and the signature: [game ROM structure](../doc/03_game_rom_structure.md),
  §1.3 and §3.

[Previous: Gauntlet in Python](17_gauntpy.md) |
[Contents](README.md) |
[Glossary and source guide](appendix_glossary.md)
