# Editorial outline: a game explained through its consequences

This is the editorial plan for the September 2026 rewrite. It replaces the
previous subsystem-first outline and its sentence-form restrictions.
The book's reading order is in [README](README.md). This file is working
material for authors, not a chapter for readers.

## The promise

A reader should finish a chapter able to explain or predict something
about Gauntlet II that they could previously only observe. The book
connects three kinds of knowledge: what a person does at the controls,
what rules govern the result, and how this machine implements those
rules.

The central question is how a compact arcade machine makes a crowded,
shared, commercially operated dungeon. Hardware limits are part of that
story. So are the camera, the voice, the competition over resources, the
operator's settings, and the persistence of information between games.

The intended reader is comfortable with ordinary programming ideas but
need not know assembly, arcade electronics, graphics terminology, or the
game. Introduce a domain-specific idea before relying on it. A curious
player should still be able to follow the prose without reading code.

## Shape of this pass

Chapters 1-8 are complete first-pass chapters. Chapters 1 and 2 established
the voice and explanatory depth; Chapters 3-8 were expanded on September 9
with worked multiplayer, generator, display, record-migration, timing, and
economic examples. Length follows the explanation, not a word-count quota.
Chapters 9-18 remain readable short drafts with concrete explanations and a
recognizable progression. Each short draft carries a "For the full chapter"
note after the narrative, separated from the reader's main path.

Expansion should add examples, causal links, diagrams, consequences, and
carefully chosen detail. It should not merely restore all the old
paragraphs. The [removal ledger](REWRITE_REMOVALS.md) is a review queue,
not an instruction to put everything back.

## Reading plan and coverage

### 1. Enter the Gauntlet

**Editorial question:** What decisions do these simple controls create?

Enter through an illustrative corridor, food, a generator, and a friend
who wants to leave. Establish the controls, position colors versus
classes, shared camera, health/time/money, ordinary exploration, joining,
exiting, and the longer journey through changing mazes. Explain enough
to make the next chapter playable in the reader's imagination. Avoid
turning the introduction into an exhaustive bestiary or a report on the
research project.

### 2. One arrow in the air

**Editorial question:** Why can moving closer let you shoot sooner?

Follow a held Fire action through the reserved shot record, launch
counter, flight, target interaction, and release of the reservation.
Distinguish elapsed travel from launch timing; show selected velocity
and damage entries with meaningful units. Work one grunt's damage
progression, then distinguish generator demotion. Reflection and piercing
show how a collision can keep the same shot alive. End with a model the
reader can apply, not a catalog of collision branches.

### 3. Three friends, one screen

**Editorial question:** Who decides where four players can go?

Follow a join into an occupied level and a disagreement about direction.
Connect class abilities, solid bodies, movement/corner assistance,
inventory, camera tracking and movement gates, IT, and optional friendly
fire. Show how camera calculations differ from the checks
that prevent a hero leaving the usable view. Give magic and its
class-dependent effects a worked shared-resource decision.

### 4. A room full of monsters

**Editorial question:** How do simple creatures become an overwhelming crowd?

Use a generator-filled corridor to join cheap target selection, local
movement, occupancy, staggered generation, spawn probability, and the
frame-overflow throttle. Show palette-as-health for ordinary monsters,
with generator type changes kept distinct. Develop ghosts, demons,
lobbers, sorcerers, Death, acid, IT, and Super Sorcerer as variations with
different consequences. In particular, lobber leading follows achieved
movement, not merely the way a hero faces.

### 5. Painting the dungeon

**Editorial question:** Who draws a picture too busy for the main processor?

Start with a familiar game frame and separate what the CPU changes from
what the video circuitry draws. Introduce the 68010, memory-mapped
hardware, tiles, palette lookup, the playfield, motion objects, the text
layer, priorities, and shadows. An annotated pixel or small image
composition should do more work than a complete address table. Physical
ROM organization belongs in a sidebar or the final source chapter.

### 6. A world in ten bytes

**Editorial question:** How does the game find the thing your arrow hit?

Build a usable picture of five parallel 16-bit words, a cell's packed
slot number, live pixel positions, fixed projectile/effect slots, and
dynamic records that move between cells. Trace one move through the
representation. Distinguish direct occupancy queries from the ordered
chain and its SLIP entry points. Show where the visible picture and the
collision state can differ without making the chapter a porting manual.

### 7. The game's clock

**Editorial question:** What keeps everything moving together?

Walk a frame through input, world work, and presentation/housekeeping.
Introduce VBLANK and the difference between being called and doing work.
Use a tutorial dialog to show what pauses and what continues. Describe
the overload signal as feedback after missed timing, not a guarantee
that a busy machine never slows. Keep host benchmarks and save-state
usage in Chapter 17.

### 8. What a quarter buys

**Editorial question:** What changes when somebody feeds the coin slot?

Connect coin reports from the sound board to credit, health, survival,
score per coin, party efficiency, generator probability, and the
operator's economic view. Distinguish ordinary and adaptive food,
starting health and active-player increments, personal and party
quotients, and stored adjustments versus immediate outcomes. Explain
score multipliers and treasure competition through a worked example.
Continue offers, rankings, and persistent statistics complete the loop.
Use a worked time-per-coin histogram with the shipped game-header scale;
distinguish those fixed parameters from the operator's live difficulty.

### 9. The next maze

**Editorial question:** Why isn't level six always the same place?

Trace the game's persistent state across two play sessions. Distinguish the progress
counter from the stored maze, the five fixed opening layouts, the
resume point, stride, and treasure rotation. Explain stored layouts
plus per-level rules. Follow a small compressed record fragment into
a floor/door/monster arrangement. Introduce the Slapstic as the
hardware gate through which the program reaches this data. Keep
selection's deterministic state distinct from random placement.

### 10. The living maze

**Editorial question:** What happens when the route changes while you use it?

Take a route through a door, transporter, and hazard; then change one
of its assumptions. Cover connected door geometry, transport routes,
forcefields, movable/cyclic/random/secret/destructible walls, genuine
and false exits, wrap, and the idle-driven opening of routes. Use
before-and-after pictures to show changes to traversal as well as
appearance.

### 11. The thief's trail

**Editorial question:** How does the thief know where you went?

Follow selection of a wealthy victim, the countdown, the trail written
before arrival, pursuit, theft, and escape. Show the victim-written and
visitor-written routes separately. Bring in the mugger as a variation
with different speed and loot, using actual constants if comparing
speed. Explain dodging and the later reappearance of stolen goods.
A route overlay is the central proposed illustration.

### 12. Fighting the dragon

**Editorial question:** What makes this encounter more than a large monster?

Connect its four pieces and moving head to authored pose/fire programs,
cooldowns, target alignment, waking and potion effects, and accepted
damage. Trace one accepted hit, the change of program without a pose
jump, and the nine-hit progression to rewards. Teach the vulnerable
moment before describing its fields. Show a short actual path program
and its on-screen poses in expansion.

### 13. Secrets and treasure

**Editorial question:** What else can the game ask you to accomplish?

Explain timed treasure collection and exit conditions before following
one hidden ordinary-maze objective into a challenge room and its result.
Distinguish eligibility, progress, violations, completion, and the
displayed code. Place the contest in history using its surviving ROM
text; do not infer mailing or prize procedures from an encoder.
Expand with an independently checked worked name/state/code example.

### 14. A machine that speaks

**Editorial question:** How does a warning belong to one player?

Start with color-and-class identification. Explain assembling phrases,
delivery timing, effects that begin and end, and competition for sound
communication. Introduce the second processor and the two-direction
latch exchange when needed. Trace the coin-status response without
pretending the chapter covers the whole sound ROM.

### 15. When nobody is playing

**Editorial question:** How does the machine demonstrate and teach its game?

Follow title, scores, demo, and legend. Explain recorded inputs being
consumed by the real engine, caption pauses, setup state, and the
limits of claiming identical playback. Treat the legend as a player
interface as well as a place for credits. A small input trace should
illuminate an observed action, rather than becoming a parser inventory.

### 16. Waking the cabinet

**Editorial question:** What must work before the screen can be trusted?

Follow power-on into tests and the OS/game handoff, then consider the
operator diagnosing a failure. Cover watchdog behavior, the division of
OS services and game policy, test-mode controls, and persistent memory.
Distinguish EEPROM repair/redundancy from transaction guarantees.
Detailed service descriptors and checksums remain in the technical docs.

### 17. Gauntlet in Python

**Editorial question:** How can we play with and look inside a reconstruction?

Give a practical start using the repository's supported tooling and
user-supplied ROMs. Explain the simulation, rendering, and host layers,
native modeled state, asset decoding, and sound playback's limits.
Walk through ordinary controls, full-playfield view, selected diagnostic
pages, and saved-state inspection/resumption. Explain performance tools
as measurements of the Python host. This is a companion guide, without
the history of fixes that produced it.

### 18. Reading the ROMs

**Editorial question:** What supports these explanations?

Keep the methodology in proportion: original bytes, names assigned by
researchers, disassembly, runtime observation, tests, and reconstruction
as a means of exposing assumptions. Use one small evidence chain.
Explain the limits of coverage statistics and claims about intent.
The author's long manual investigation and AI-assisted work belong here.
Interesting build and copyright traces are optional expansion material.

## Positive writing requirements

- Call the game "the game," never "the cabinet." Reserve "the cabinet"
  for attributes of the actual physical game cabinet, such as its
  control layout, coin door, or housing, not gameplay, program behavior,
  or persistent game state.
- Give the reader a concrete situation and a reason to care about the
  next technical idea. The motivating question is an editorial test,
  not compulsory text at the top of the page.
- Develop the connections between facts. Show what changes, what reads
  that state next, what the player sees, and which decision follows.
  Where useful, explain the plausible alternative the machine does
  not implement.
- Stay with a worked example long enough for the reader to use it.
  Label invented situations, simplified calculations, synthetic
  experiments, and captured observations for what they are.
- Introduce unfamiliar terms in place. Return to a concept with a little
  more depth when the new question needs it. Cross-references supplement
  the explanation rather than replacing its missing middle.
- Choose tables for comparisons and data whose labels carry meaning.
  Give units. Choose pseudocode for a short decision or state change.
  Use assembly only when the instructions themselves are the point.
- Treat pictures as explanations. Captions should say what to look at,
  where the picture came from, and what it establishes. Do not call a
  synthetic Python fixture an original-game observation.
- Let accurate uncertainty remain. Distinguish implemented behavior,
  inferred consequences, historical testimony, and authorial intent.
  Avoid unsupported claims that a design is unique or unprecedented.
- Keep readable source notes near their chapter. Routine names are
  helpful after explanation; addresses usually belong in the notes.
  A number of audited entries is not a substitute for a causal account.
- Prefer natural, varied prose over a prescribed sentence shape. Edit
  away repeated announcements, forced jokes, unexplained shorthand, and
  conclusions that merely repeat the opening.
- Keep the arcade narrative distinct from companion usage. A Python
  excerpt can explain a rule in any chapter. Host switches, diagnostics,
  benchmarks, and save files belong in Chapter 17.

## Source and revision discipline

Use maintained [technical documentation](../doc/INDEX.md) as the starting
map. When sources disagree, the ROM's actual operations and carefully
matched runtime observations outrank either the book or the Python model.
The reconstruction and a document used to build it are not independent
confirmation of each other.

Update the explanation itself when a finding changes. Read the whole
affected section and its consumers; do not append a corrective paragraph
while leaving a conflicting account in place. The technical correction
log can preserve the investigation history. The book should present the
best-supported current account.

Record substantive omissions in the removal ledger, including the old
location, what the draft retains, what it defers, and a proposed home.
Keep useful illustrations even when this pass does not use them. Source
assets retain their existing names to avoid unnecessary regeneration.

Review each expanded chapter against its editorial question and this
coverage plan. A chapter is ready when the reader can follow its causal
chain, its examples agree with the evidence, and its length is earned by
understanding rather than inventory.
