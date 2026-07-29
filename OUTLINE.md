# Gauntlet II: How It Works — Book Outline

This file is the authoritative outline and style contract for a reader-friendly
book about the internals of the Gauntlet II arcade game, derived from the
reverse-engineering documentation in this repository. It is written so that a
writing agent can produce the final chapters without needing any other
briefing.

---

## Frontmatter: Goals, Audience, and Constraints

### Purpose

The technical documentation in `doc/` is extensive but written for someone
already deep in the game's internals: it is organized around addresses,
function contracts, data ranges, and audit coverage. This book re-presents that
knowledge as a narrative that a newcomer can read front to back, with each
chapter building only on concepts introduced in earlier chapters.

The book should answer two questions in parallel:

1. What does the player experience, and what rules make Gauntlet II feel like
   Gauntlet II?
2. How do the cabinet's hardware, data structures, and software cooperate to
   create that experience?

The result should feel like a guided tour of a complete game, not a simplified
function index.

### Audience

A **hobbyist programmer**: comfortable with general programming concepts
(variables, loops, functions, arrays, lookup tables, memory, bits, bytes, and
hex numbers), but with **no** knowledge of 68000-family assembly, arcade
hardware, or this game's internals. Do not explain elementary programming
ideas, but do introduce domain-specific concepts such as sprites, interrupts,
palettes, bank switching, memory-mapped hardware, and VBLANK before relying on
them.

Assume the reader can follow short pseudocode, labeled tables, diagrams, and a
small amount of hexadecimal notation. Do not assume they have played Gauntlet
II recently—or at all.

### Deliverable format

- A new directory `book/` at the repository root.
- One markdown file per chapter, numbered: `book/01_how_to_play.md`,
  `book/02_introduction.md`, etc. Final filenames should match the chapter
  titles below, adjusted to `NN_snake_case.md`.
- A `book/README.md` containing a one-paragraph description of the book and a
  linked table of contents with a one-line summary per chapter.
- A final `book/appendix_glossary.md` (see the Appendix section).
- There is **no hard chapter count or word limit**. Most chapters will probably
  land around 1,500–3,000 words, but clarity determines length. Split a chapter
  when it contains two different mental models or when a newcomer would benefit
  from a pause; do not compress an important explanation merely to hit a target.
- Favor completeness of *concepts* over completeness of *inventory*. The book
  never needs to list every function, table, maze, or object ID.

### Chapter-opening contract

Every chapter begins with a short statement of:

- what question the chapter answers;
- what the reader will understand by the end; and
- which earlier concepts it builds upon.

Whenever practical, begin with a concrete player-visible moment—a coin drop, a
crowd of ghosts, a moving wall, a spoken warning—and then work inward toward
the mechanism.

### Voice and style rules

1. **Prose first.** Explain mechanisms in plain sentences. A reader should be
   able to follow every chapter without reading a single line of code.
2. **Pseudocode over assembly.** When showing logic, use short high-level
   pseudocode (Python-ish or C-ish, whichever reads cleaner). Raw 68010
   assembly is allowed only when the *assembly itself* is the point, and must
   be explained line by line when used.
3. **Tables are welcome** when they mirror an actual table in ROM. Always label
   rows and columns with meaningful names, never raw offsets. For example,
   describe a speed table as rows for normal/powered state and columns for
   character class, then show those labels.
4. **Use actual game graphics when they clarify.** Annotated screenshots,
   isolated sprites, maze renderings from `python-gex/`, and small crops of the
   HUD are especially useful in Chapters 1, 4, 8, 9, 10, and 13. Every image
   must teach something that would take longer to explain in prose.
5. **Diagrams** (Mermaid preferred) are encouraged when they genuinely
   simplify—flow of a frame, layer composition, a MOB record, a session
   lifecycle, or the maze-decode pipeline. Keep them small.
6. **Names in prose: yes. Addresses in prose: no.** Using a real function or
   variable name in body text (`g2mainloop`, `game_mode`, `find_maze`) is
   encouraged when it beats a roundabout description. Introduce each name once
   in plain language and use it freely afterward. Raw addresses stay out of
   body prose.
7. Every chapter ends with an **"Under the hood"** box: a short bulleted list
   mapping the chapter's important mechanisms and names to their addresses and
   the `doc/` file/section that covers them. This box is optional reading and
   may be more technical than the chapter body. Format:

   > **Under the hood**
   > - The main loop described here is `g2mainloop` (0x42A66); the verified
   >   call sequence is in `doc/03_game_rom_structure.md` §2.
   > - The VBLANK semaphore is the word at 0x904002.
8. **Introduce before use.** Each chapter may rely on concepts from earlier
   chapters only. If a later chapter needs a concept out of order, add a
   one-sentence reminder and link back.
9. **Consistent terminology.** First use: "motion objects—MOBs—the hardware's
   name for sprites"; thereafter "MOB" or "sprite (MOB)." Use "playfield" for
   the maze tile layer, "text layer" for alphanumerics, "Slapstic ROM" for the
   bank-switched level-data ROM, and "OS ROM" and "game ROM" for the other two
   analyzed ROM images. Use "level" for the player's progress count and "maze"
   for a stored layout record. Do **not** publish a simple level-to-maze formula
   until the maze-selection research task below is resolved.
10. **Light, curious tone.** This is a tour, not a specification. Wry asides
    are fine; memes and forced jokes are not. Write like a good conference
    talk.

### Accuracy and source constraints

- Everything factual must trace to the maintained `doc/` chapters,
  `refs/HW_WRITEUP.md`, the checked artifacts in `doc/generated/`, the
  radare2 annotations, `python-gex/`, or an explicitly identified external
  source.
- The current main documentation is the normal source of truth.
  `doc/08_known_issues.md` is primarily a historical correction log; consult it
  when a claim looks suspicious or provenance/intent is involved, but do not
  organize the book around it.
- The project owner's clarifications in this outline are part of the source
  briefing. If they conflict with the maintained documentation, reconcile the
  conflict before drafting the affected chapter rather than silently choosing
  one.
- MAME source and tracing are legitimate secondary research aids, especially
  for hardware behavior that cannot be observed from ROM bytes alone. They
  were not the project's primary tool. Cite MAME honestly when a claim
  materially depends on it; do not make it the default explanation or conceal
  its use.
- `python-gex/` is a working demonstration of graphics and maze formats. Its
  code and rendered output may be used to explain those formats, but the book
  must not require the reader to run it.
- The documentation carries confidence labels (**Verified**, **Strong
  inference**, **Contradicted**, etc.). State Verified material as fact.
  Present Strong-inference material with a softener. Never repeat a
  Contradicted claim.
- **Needs-verification markers are draft-only.** A drafting agent may put
  `**[needs verification]**` immediately after a worthwhile unresolved claim,
  but the finished book must contain **zero** such markers. Each must be
  verified, rewritten with an honest uncertainty statement, or removed during
  final review.
- Separate **observed behavior** from **historical provenance**, **authorial
  intent**, and **design interpretation**. The code can prove what it does much
  more often than why its authors chose to do it.
- Folklore is flavor, not fact. Player culture and well-known Gauntlet stories
  are welcome when framed as lore and sourced when practical.

### Research gates before affected chapters are drafted

These are targeted rechecks, not invitations to redo the whole project:

1. **Normal maze order and the maze randomizer.** The project owner confirms
   that stored mazes 0–5 are the first six normal levels and that randomized
   maze selection begins afterward. This conflicts with the current
   `doc/06_maze_catalog.md` range table and the `Level N = Maze N+4` wording.
   Revisit `maze_checknum`, `maze_next`, the saved randomizer state around
   0x90400E/0x904010, level-start/exit callers, EEPROM initialization, and the
   separate treasure-room randomizer. Correct the maintained documentation,
   then give Chapter 9 the exact algorithm: activation point, state update,
   allowed range, wrap behavior, repeat behavior, and special-case paths.
2. **MOB depth/priority chains.** Reconfirm the relationship among the global
   doubly linked chain, forward/back links, the 64 cumulative priority heads,
   hardware traversal, collision queries, and monster iteration. Use targeted
   disassembly and, if useful, MAME tracing or instrumentation. This mechanism
   is central to explaining how the game supports unusually large crowds, so
   Chapter 8 must not inherit a convenient but inaccurate "64 separate lists"
   story.
3. **Mugger differences.** Treat the mugger as a variant of the thief state
   machine that fights/inflicts damage and steals health rather than inventory.
   Verify whether its speed or timing actually differs before saying that it
   is faster.
4. **Demo determinism.** The recorded-input format, pointers, timers, setup
   path, and primary Elf stream are already verified in the ROM documentation.
   Before explaining *why* playback remains synchronized, verify exactly how
   the random seed and other initial state are established. Do not use the
   vague phrase "same seeded state" without showing the setup path.
5. **Secret-code verifier.** Independently reproduce `secret_code_build` from
   its disassembly and checked data tables. Capture at least one in-game
   name/state/code example and confirm that the independent implementation
   produces the same `XXX-XXX` result. Chapter 13 should explain what can be
   verified from the displayed code alone and what requires the entered name
   or saved challenge context.

### Primary sources by chapter

| Chapter | Main sources |
|---------|--------------|
| 1 | `doc/04_game_subsystems.md`, `doc/05_data_reference.md`, in-game legend/strings and selected rendered graphics |
| 2 | `README.md`, `doc/INDEX.md` |
| 3 | `doc/01_hardware.md`, `refs/HW_WRITEUP.md`, ROM assembly instructions in `README.md` |
| 4 | `doc/01_hardware.md`, `refs/HW_WRITEUP.md`, `doc/04_game_subsystems.md` §13, §24 |
| 5 | `doc/02_os_rom.md` (boot, vectors, jump tables, self-test, error paths) |
| 6 | `doc/03_game_rom_structure.md` §2, `doc/04_game_subsystems.md` §15 |
| 7 | `doc/04_game_subsystems.md` §4, §6, §10, §12, §16, §22; `doc/03_game_rom_structure.md` §2.3–2.5 |
| 8 | `doc/01_hardware.md` §7–10; `doc/04_game_subsystems.md` §1, §13, §17, §23–24; `doc/05_data_reference.md` §1 |
| 9 | `doc/06_maze_catalog.md`, `doc/04_game_subsystems.md` §5, `doc/05_data_reference.md` §3.12–3.20 and §4.1, `refs/GAME_ROM_KNOWN.md`, `python-gex/` |
| 10 | `doc/04_game_subsystems.md` §2, §4, §15, §22–23, §26; `doc/05_data_reference.md` §1.7, §1.11, §3, §5 |
| 11 | `doc/04_game_subsystems.md` §3, §26; `doc/05_data_reference.md` §7 |
| 12 | `doc/04_game_subsystems.md` §8–9; `doc/05_data_reference.md` thief/dragon state and data tables |
| 13 | `doc/04_game_subsystems.md` §7, §10.6, §12–13, §16, §18–19, §21, §26; `doc/05_data_reference.md` secret-code data |
| 14 | `doc/04_game_subsystems.md` §10, §14, §20, §25; `doc/02_os_rom.md` §8.9–8.13 |
| 15 | `doc/04_game_subsystems.md` §6; `doc/03_game_rom_structure.md` §2.5; `doc/05_data_reference.md` demo tables |
| 16 | `doc/04_game_subsystems.md` §11; `doc/02_os_rom.md` §6.7, §8.7–8.8; `refs/soundcmds.csv` |
| 17 | `README.md`, `doc/03_game_rom_structure.md` §1.3, §3–4; the Ed Logg Centipede affidavit linked in the chapter; selected audit artifacts |

---

## Chapter 1 — Enter the Gauntlet (How the Game Plays)

*The player's-eye foundation. Before asking how the machine works, establish
what it is trying to accomplish.*

- The cabinet and the immediate experience: up to four people standing at four
  color-coded control stations, exploring a scrolling maze together while
  monsters pour from generators. The objective is simple—survive, find the
  exit, and keep going—but the systems underneath it are not.
- The controls and moment-to-moment verbs: an eight-way joystick, Fire, and
  Magic; walking, fighting/shooting, using potions, collecting items, opening
  doors with keys, eating food, and reaching exits. Use a labeled control-panel
  diagram and one annotated gameplay screenshot.
- The four heroes—Warrior, Valkyrie, Wizard, and Elf—and the broad tradeoffs
  among fight strength, armor, magic, movement, and shooting. Keep this at the
  level of player expectations; the exact tables come in Chapter 10.
- Health as both life and arcade currency: it drains with time, falls from
  damage, rises with food or inserted coins, and makes continued play a
  visible economic choice. Briefly introduce score, treasure, inventory, and
  the score multiplier without explaining their storage yet.
- The shape of a game: coin/start, choose a hero, enter a level, explore and
  fight, exit, occasionally visit treasure or secret rooms, die or continue,
  and eventually return to high scores and attract mode. Chapter 7 will turn
  this into a complete state diagram.
- What makes Gauntlet II distinctive: join-in-progress multiplayer, the IT/tag
  mechanic, friendly-fire variants, moving and invisible walls, transporters,
  the dragon, thief/mugger, treasure rooms, secret challenges, and a very large
  number of simultaneous monsters. This is a preview, not an exhaustive rules
  chapter.
- A visual vocabulary for the rest of the book: identify the maze/playfield,
  heroes and monsters, generators, floor items, the HUD, text messages, and the
  visible camera window. Later chapters can point back to this annotated image.

---

## Chapter 2 — Welcome to the Machine (Introduction)

*Sets expectations: what was reverse engineered, what kind of evidence the
book uses, and how to read it.*

- Why Gauntlet II's internals are worth a book: it is a complete, readable
  example of how a 1986 arcade game turns compact data and modest CPUs into a
  busy four-player world.
- What this book is based on: decades of manual reverse engineering followed by
  an AI-assisted documentation and audit effort. Explain "reverse engineering"
  here as recovering code, data structures, and behavior from the shipped ROM
  images rather than working from original source.
- The cast of chips at headline level: one main CPU running the game, a second
  computer dedicated to sound, video hardware that draws from tables, and
  three analyzed ROM images with distinct jobs—OS, main game, and
  bank-switched level data. Graphics and sound data live in additional physical
  ROMs.
- What "thoroughly documented" means precisely: the supplied game and OS images
  have byte-level code/data accounting and checked callable contracts, while
  the level-data tooling validates all stored maze records. Avoid the looser
  and misleading phrase "every function and table fully understood."
- How to read the book: chapters build in order; optional "Under the hood"
  boxes point into `doc/`; confidence and uncertainty are stated honestly; a
  glossary and repository map are available at the end.
- A frame-of-reference teaser: after boot, nearly everything the player sees is
  advanced by one recurring loop synchronized to the 60 Hz display. Chapter 6
  will slow down one trip through that loop.

---

## Chapter 3 — The Machine (Hardware Overview)

*The reader leaves knowing what hardware exists and the most important design
idea: the CPU usually describes what should appear, while specialized video
hardware paints it.*

- The main CPU: a Motorola 68010; briefly explain its 16-bit external data bus,
  32-bit address/register model, big-endian byte order, and why it is a
  relatively conventional general-purpose processor inside an arcade cabinet.
- Memory-mapped everything: one address space containing ROM, working RAM,
  video RAM, EEPROM, input ports, and hardware control registers. Include a
  simplified memory map with a handful of labeled regions.
- **From physical chips to analyzable images:** the board uses pairs of 8-bit
  ROM chips on the 68010's 16-bit bus. One chip supplies the even byte lane and
  its partner the odd byte lane; reverse engineering first interleaves those
  bytes into CPU order. Explain how the row 7 and row 6 game pairs are then
  concatenated, and show a tiny `even[0], odd[0], even[1], odd[1]` diagram.
- The three analyzed ROM images and their jobs: OS ROM (boot, diagnostics,
  shared services), game ROM (gameplay), and Slapstic ROM (bank-switched maze
  data). Distinguish these logical images from the larger collection of
  physical program, graphics, and sound chips.
- The display in one paragraph: a 336×240 screen refreshed at 60 Hz, composed
  from a scrolling playfield, motion objects, and text. Defer the full
  explanation to Chapter 4.
- The supporting cast: the sound board's 6502 CPU, EEPROM, joystick/coin/start
  inputs, output latches and LEDs, and the watchdog that reboots a machine
  whose software stops checking in.

---

## Chapter 4 — Painting the Screen (The Display System)

*How tables in video RAM become a picture. This chapter explains rendering;
Chapter 8 later explains how the same records participate in game state,
ordering, and collision.*

- Tiles and palettes: visible art is built from small indexed-color graphics
  stored in ROM. The CPU writes tile numbers and palette choices, not pixels.
  Explain 8×8, 4-bit-per-pixel tiles and the intensity-plus-RGB palette format
  using one enlarged tile and palette example.
- The playfield layer: a column-first 64×64 grid of tile words forming a
  512×512-pixel world, of which the screen shows a window. Two scroll
  registers move that window. Each logical 16×16 maze cell normally expands to
  a 2×2 block of playfield tiles.
- Motion objects—MOBs, or sprites: up to 1024 numbered slots, each described by
  four parallel hardware tables for picture, horizontal position/palette,
  vertical position/size, and link. Show how a MOB ID addresses the same entry
  in all four tables and how multi-tile sprites build the dragon or large
  effects.
- Introduce MOB traversal cautiously: the hardware follows links rather than
  scanning every possible slot for every line. State only the verified
  high-level fact here; defer the global chain and 64 cumulative entry heads to
  Chapter 8 after the targeted recheck.
- Sprite pixel special cases: color index 0 is transparent and index 1 selects
  the shadow treatment for the underlying playfield pixel. Use a crop showing
  a monster/player shadow.
- The text layer and layer priority: a character grid overlays the action,
  with a per-character opaque bit. The black screen between levels is the text
  layer filled with opaque spaces, not the monitor or playfield turning off.
  Close with a small diagram of text over MOBs over the playfield, including
  the transparent cases.
- Make the boundary explicit: playfield words and MOB pictures are the *visible
  representation*. Walls, doors, players, monsters, and items also have
  logical state that cannot be recovered merely by reading the resulting
  pixels. Chapter 8 explains that second half.

---

## Chapter 5 — Waking Up (Boot, the OS, and Self-Test)

*What happens between power-on and the attract screen, including the real error
paths rather than a simplified "everything passes or boot stops" story.*

- The 68010's first breath: it reads its initial stack pointer and start address
  from the beginning of the OS ROM, masks interrupts, resets/enables board
  hardware, services the watchdog during delays, and chooses normal or
  self-test boot from the cabinet switch.
- Destructive RAM testing before RAM can be trusted: the short and full test
  state machines, their continuation-address convention, and why early boot
  cannot casually use the stack it is trying to verify.
- The exact failure policy: working/video RAM failures are identified and
  displayed while the sequence continues through later tests; OS/game ROM
  validation and "NO GAME PROGRAM" have their own paths; self-test and normal
  boot dispatch differently after accumulated errors. Use a flowchart that
  shows what continues, what enters diagnostics, and what waits.
- Why there is an "OS" at all: text drawing, coin accounting, EEPROM, sound
  communication, input and diagnostic services live behind fixed API jump
  veneers so game code can call stable entry points.
- The contract in the other direction: the game ROM header supplies hooks the
  OS may call for start, interrupts, tests, options, and other game-specific
  behavior. Explain this two-way interface without claiming more historical
  interchangeability than the evidence proves.
- Interrupts as the machine's pulse: hardware temporarily redirects the CPU to
  OS-owned vector handlers, which may dispatch to game hooks. Emphasize VBLANK
  and sound communication; introduce the watchdog/reset paths.
- Self-test and the operator's cabinet: color, alpha, MOB, switch, sound, RAM,
  and ROM tests; configuration editors; coin options; and statistics screens.
  Later chapters revisit the operator settings from the business/game-design
  side.

---

## Chapter 6 — The Heartbeat (The Main Loop)

*One synchronized loop advances gameplay, presentation, persistence, and sound.
This is the software's per-frame loop, distinct from the complete player
session covered in Chapter 7.*

- The frame-lock idea: a VBLANK interrupt publishes a semaphore once per screen
  refresh; the main loop waits for it, consumes it, performs one update, and
  waits again. Show high-level pseudocode.
- A guided walk through one frame's 29 direct calls, grouped conceptually:
  always-run input/coin/color services; the gameplay block; then messages,
  selection/start logic, score/UI, attract mode, EEPROM, and sound.
- Input sampling and debouncing: raw four-player controls are read every frame;
  hand-written rotate/shift logic keeps short electrical bounces from becoming
  extra button presses. Save the control interpretation itself for Chapter 10.
- The dialog gate: while a message box is active, the sixteen-call gameplay
  block is skipped as a unit, genuinely freezing movement and hazards while
  post-gameplay UI and sound work continue.
- The mode variable: one word distinguishes normal play, treasure-room exit,
  and the four attract-family modes. Most subsystems also apply their own
  player/mode gates, so "called" does not always mean "does work." Include a
  compact representative matrix.
- Keeping time honestly: the frame counter and overflow signal that notices a
  second VBLANK arriving before the frame is finished, then decays when the
  workload recovers.
- Close by separating three scales of time used in the book: interrupts happen
  during a frame; the main loop advances one frame; the session state machine
  carries the player from coin drop to game over.

---

## Chapter 7 — From Coin Drop to Game Over (The Session Lifecycle)

*A single map of the whole experience. Later chapters can explain each branch
without losing the reader in disconnected subsystem details.*

- Begin in attract mode: title, scores, demo, and legend run until a coin/start
  path transfers control into a real session. Explain paid versus free-play
  only at a high level here.
- Starting and joining: a cabinet position gains health/credit, enters
  character-selection state, chooses a hero with the joystick, receives a HUD
  column, and is placed at a usable spawn. The same lifecycle supports friends
  joining a level already in progress.
- Starting a level: choose the next stored maze, show the level/secret
  presentation, load and construct the world, position existing players, set
  the camera, and release the input/UI delay into ordinary play.
- Playing and leaving: active players move through the same per-frame loop until
  they die, exit, or trigger a treasure/secret transition. Multiple players may
  be in different per-player states while the global session continues.
- Level transitions: exit animations, bonus/tally screens, treasure rooms,
  secret challenges, and restoration of the saved normal-game level/maze state.
  Point forward to Chapters 9 and 13 for the exact selection rules.
- Death and continuation: health reaches zero, death/respawn presentation runs,
  surviving players may keep the level alive, and an all-player loss can lead
  to the timed continue prompt at the current level.
- End of session: score-per-coin ranking, ordinary initials entry when
  qualified, game-over timing, statistics/persistence updates, and return to
  attract mode.
- Use one state diagram with separate lanes for global mode and per-player
  status. The point is not to enumerate every numeric state but to show how
  independent player lifecycles coexist inside one cabinet session.

---

## Chapter 8 — The World in Memory (Objects, Coordinates, and Crowds)

*The bridge between rendering and gameplay. Explain what a "thing in the maze"
is, how it is located, and how hundreds of things can be maintained without
turning the game into a pile of pixels.*

- Three related coordinate spaces: a packed 32×32 maze-slot grid for logical
  placement, a 64×64 grid of 8×8 playfield tiles for rendering, and 0–511
  pixel coordinates for MOBs and camera movement. Show one cell traced through
  all three representations, including object-specific origin offsets.
- A MOB slot as both hardware record and software object handle: four video-RAM
  arrays plus the software-only state/back-link array. The upper link/state
  bits carry object type or object-specific state; the same field means
  animation/direction for a monster, player identity for a hero, door shape
  state for a door, and hit count for a movable wall.
- Fixed and dynamic identities: reserved low slots for shots, explosions,
  score popups, exit animations, and transporter effects; dynamic slots for
  maze objects. Explain why a numbered slot is useful without implying that
  all 1024 are active or visible at once.
- **The MOB chain, after the research gate:** one depth/priority-sorted doubly
  linked chain, a global head, forward and backward links, and 64 cumulative
  vertical/priority entry heads into that same chain. Show insertion, removal,
  and traversal with a diagram; explicitly contrast this with the incorrect
  mental model of 64 independent lists.
- Rendering order, monster iteration, and collision: identify which operations
  follow the shared chain, which enter through a cumulative head, and which
  probe neighboring maze slots or fixed projectile channels. Do not blur
  hardware display traversal and software collision merely because they share
  link data.
- Logical state versus visible tile: walls and doors can have MOB/object
  records and neighbor/endpoint state even though the player ultimately sees
  playfield tiles. Explain the path-grid nibbles and per-player door endpoint
  records at a conceptual level.
- The multiplayer camera: compute the active-player extent, constrain outliers
  with the rubber-band limit, choose the midpoint, move smoothly toward it,
  and account for wraparound/offscreen level flags. Pair the algorithm with two
  annotated screenshots showing close and widely separated players.
- Why crowds are possible: compact parallel arrays, fixed-size IDs, linked
  traversal, hardware sprite composition, simple per-monster decisions, and
  bounded per-frame work. Present this as an evidence-backed design reading,
  not a claim that any one data structure alone created Gauntlet's crowds.

---

## Chapter 9 — Building and Choosing a Level (Mazes and the Slapstic)

*From level progression to a playable world: choose a stored maze, expose its
bank, decode a compact record, and construct the logical and visible state
introduced in Chapter 8.*

- Levels versus stored mazes: the Slapstic ROM contains 117 records numbered
  0–116, including normal layouts, demo/legend material, treasure rooms, and
  two secret-room layouts. Establish the corrected normal progression:
  **mazes 0–5 are always the first six levels**, after which the maze selector
  begins randomizing later layouts. Do not retain `Level N = Maze N+4`.
- **The maze-selection randomizer:** after completing the research gate,
  explain the exact algorithm and state in plain pseudocode—when it activates,
  how it chooses/advances the next maze, its legal normal-maze range, how it
  prevents or permits repeats, wrap/endgame behavior, and what EEPROM state
  preserves. Separately explain the treasure-room selector and the fixed
  demo, legend, and secret paths.
- The Slapstic: a 32 KB level-data image visible through an 8 KB CPU window,
  with a copy-protection chip selecting the bank after a required access
  ritual. Explain the 2-bit bank table and 117-entry pointer table without
  drowning the reader in bus cycles.
- Anatomy of a maze record: secret objective, four bytes of level flags,
  wall/floor art and palette choices, four horizontal/vertical span types, and
  a compressed object stream. Show a labeled header.
- The decoder: a bytecode stream walks a cursor over the 32×32 logical grid,
  placing object types, repeating horizontal/vertical spans, repeating the
  previous type, or skipping cells. Show a small verified worked example and a
  matching `python-gex` rendering.
- Placement and construction: tokens become logical object/MOB records or
  marker records; visible 2×2 tile descriptors are selected; post-decode scans
  find the player start, build transporter/exit tables, connect walls and
  doors, initialize forcefields, and center the camera.
- **Do not confuse two kinds of randomization.** Maze selection chooses which
  stored layout comes next. Level-flag randomization modifies how a chosen maze
  behaves, adding late-game hazards such as faster/odd-angle monsters,
  wraparound, or invisible walls. Random pickup placement is a third,
  object-placement step.
- The game's RNG in one page or less: a small deterministic 16-bit
  linear-congruential generator feeds maze selection/flags (once verified),
  pickup placement, AI choices, forcefield timing, secret tasks, and other
  systems. Show the recurrence or short pseudocode, then focus on how one
  shared stream creates coupling among apparently unrelated events.

---

## Chapter 10 — The Heroes (Players, Controls, and Inventory)

*Everything the active-player update does: selection, movement, attacks,
health, items, powers, animation, and four-player interaction.*

- The four classes as data: per-class ROM tables for movement speed, fighting,
  shot damage/speed, armor, and magic. Present a few labeled tables and connect
  them to the broad tradeoffs introduced in Chapter 1.
- Selection, joining, and player state: each cabinet position owns a player
  record and HUD color; character selection is a per-player state, not merely
  one pre-game screen. Successful joining finds a clear spawn, creates a player
  MOB, installs character-specific palette handlers, and initializes status,
  speech, and counters.
- From raw controls to intent: active-low joystick/button bits, per-frame
  debouncing, conversion of direction nibbles to one of eight directions, and
  the distinction among movement, Fire, and Magic. Keep electrical details in
  Chapter 6 and focus here on game meaning.
- Movement as negotiation: look up speed, propose a pixel/slot movement, probe
  walls, door geometry, corners, monsters, and players, account for wrap/offscreen
  flags and stun/slow effects, then commit or reject. Refer back to Chapter 8's
  coordinate and collision model.
- Fighting and shooting: standing, walking, fighting, and shooting animation
  tables; how attack direction and animation timing lead to projectile
  creation; fixed per-player shot channels; ordinary shot power, upgraded
  power, supershots, piercing/reflection, and the one-shot-at-a-time constraints
  visible to the player.
- Magic and potions: the Magic button consumes a carried potion; a
  character/powered-state matrix determines damage or transformation across
  monster and generator types. Use a compact labeled slice of the real matrix
  rather than listing all 28×16 entries.
- Health, damage, and death: constant drain, armor and contact/projectile
  damage, food and coins as replenishment, low-health pulsing/heartbeat and
  speech, poison/acid timing, accumulated damage statistics, zero-health state,
  and the continue path from Chapter 7.
- Inventory and doors: keys, potions, treasure multiplier, and power-up icons
  in the HUD; collecting a key versus spending it; door endpoints and
  direction-aware traversal; timed door opening. Keep door rendering and world
  mutation in Chapter 13.
- The power-up vocabulary: extra speed, shot speed/power, magic, armor/fight,
  invisibility, invulnerability, repulsiveness, reflect, supershots,
  transportability, and relevant one-shot/dialog behavior. Explain effects and
  durations by category rather than as a bitmask dump.
- Gauntlet II's player-vs-player layer: IT transfer and HUD announcement,
  monsters targeting IT, shot-stun and shot-hurt level flags, supershot damage,
  and how cooperative play can temporarily become competitive.

---

## Chapter 11 — The Horde (Monsters and Combat)

*Ghosts, grunts, demons, lobbers, sorcerers, Death, acid, and special variants:
how the game animates and fights a crowd on a 1986 CPU budget.*

- The monster roster as data: types, strength tiers (also reflected in
  palette/packed state), per-type parameters, and the distinction among
  ordinary monsters, generators, acid, Super Sorcerer, Death, and IT-related
  behavior.
- One brain, many bodies: the common monster dispatcher and shared handler;
  small state codes for moving/chasing; simple target selection; grid/path
  decisions; and level flags that enable odd-angle or double-speed behavior.
  Explain how monsters react to the current IT player when appropriate.
- Generators: object types that periodically create other monsters, using
  per-level caps, spawn probability, tier/type tables, and a bounded scan for a
  clear adjacent cell. Connect the cap to operator difficulty and active play.
- Type specialties: ghosts damage-and-die on contact, demons shoot, lobbers arc
  projectiles over walls, sorcerers blink and may be immune while hidden,
  acid moves and slows, Super Sorcerers use special placement, and Death drains
  health until its special threshold is met.
- Shots and hit resolution: fixed player/monster projectile channels, movement
  and collision, player/monster/wall/item/dragon targets, ordinary versus
  supershot rules, stun/friendly-fire behavior, and why the result depends on
  both target type and level flags.
- Dying by the numbers: packed monster tier/health changes, destruction,
  score awards, potion mass damage, corpse/effect animation, and floating score
  MOBs. Tie the visual effects back to Chapters 4 and 8.

---

## Chapter 12 — Special Guests (The Dragon, Thief, and Mugger)

*Purpose-built actors that sit outside the common monster path and show how the
game layers hand-tuned exceptions over a general engine.*

- Why they are special: private state, dedicated MOB slots/data, custom path or
  targeting code, and specialized damage/animation handling rather than the
  ordinary monster dispatcher.
- The dragon as a multi-MOB actor: head/body segments, spawn offsets, dormant
  and active phases, turning/sleeping/fire constraints, nine-hit defeat
  behavior, and the special bonus/drop path.
- Dragon path programs: five compact authored sequences controlling pose/fire
  timing, plus random path changes that preserve pose continuity after a hit.
  Use an annotated sequence and sprite composite.
- The thief: wealth-based victim selection, level/wealth-dependent appearance
  timer, pursue/steal/escape states, path recording, shot-alignment detection
  and dodging, transport interactions, theft priority, carried loot, and exit.
- The mugger: the same broad state machine with its variant flag, animations,
  speech, carried-state fields, fighting/contact behavior, and **health theft
  rather than ordinary inventory theft**. Include speed/timing differences only
  if the research gate verifies them.
- What these exceptions teach: ROM space and special-case code were spent where
  they produced memorable encounters, while shared MOB, coordinate, collision,
  sound, and rendering systems still did most of the supporting work.

---

## Chapter 13 — A Living Maze (Doors, Hazards, Treasure, and Secrets)

*The systems that make stored layouts change underneath the players—and the
complete path from an ordinary secret objective to a verifiable secret code.*

- Doors and keys as a complete system: logical door objects, connected/isolated
  shapes, endpoint records, key consumption, direction-aware traversal, manual
  and timed opening, neighbor redraw, and the "Doors Open" presentation.
  Refer back to Chapter 10 for inventory ownership.
- Transporters: post-decode destination tables, destination selection,
  saved/restored player graphics, sparkle/transition MOBs, state changes, and
  interactions with thieves and secret objectives.
- Forcefields: hub/segment records, horizontal/vertical runs, palette animation,
  randomized on/off timing, collision damage/sound timers, and when the field
  becomes passable.
- Walls that misbehave: cyclic groups, random appearance/disappearance,
  movable walls with hit accumulation, destructible and secret walls,
  invisible walls, trap-wall conversions, prizes or danger hidden behind
  walls, and the exact distinction between a logical wall and its current
  graphic.
- Exits, honest and otherwise: ordinary exits, moving exits, one-real-exit
  selection, fake exits, exit animations, and the long-time escape behavior
  that can convert walls into exits. Explain how the next-maze calculation
  connects back to Chapter 9.
- Traps and special floors: stun tiles, acid puddles, slow-motion effects,
  wraparound/offscreen geometry, and how tile interaction dispatch turns a
  stepped-on object type into player state.
- Treasure rooms: selection among the treasure layouts, saved normal-session
  state, countdown and deliberately mischievous speech, treasure scoring,
  timeout, bonus tally, and restoration to ordinary progression.
- **Ordinary secret objectives:** every normal maze's trick/task state, examples
  such as avoiding treasure or shooting walls/food, per-player progress and
  violation hooks spread across movement/combat/item systems, and the event
  that earns entry to a secret challenge.
- **Secret challenge rooms:** save the previous maze/trick, choose one of
  challenge codes 0x50–0x5D, select secret layout 115 or 116, display the
  qualifier and time limit, track the selected objective, award the
  5,000-per-coin bonus, and distinguish these challenge codes from ordinary
  maze-header trick IDs.
- **Name entry and the `XXX-XXX` secret code:** the operator setting that
  enables contest/name entry, editing the winner's name, CRC-CCITT hashing
  while ignoring spaces, combining name-derived symbols with
  maze/trick/challenge state, the 32-character alphabet, interleaving the six
  symbols, and the original contest text.
- **How to verify a code:** include readable pseudocode or a short independent
  reference implementation derived from `secret_code_build`, walk one captured
  in-game example end to end, and explain which inputs are necessary to
  reproduce or validate it. The code in the book must be tested against the
  game, not merely transcribed from the documentation.

---

## Chapter 14 — Keeping Score (UI, Arcade Economics, and Memory)

*Coins, health, score, presentation, operator policy, and persistence: the
commercial and informational layer surrounding the action.*

- Coin to credit to health: hardware/OS coin samples, per-player coin counts,
  coins-to-start rules, active-player re-coining, configurable health per coin,
  and why Gauntlet's business model is visible directly in its player state.
- Scoring: pickups, monster awards, the treasure multiplier, special bonuses,
  floating score displays, and the difference between the live raw score and
  the value used for ranking.
- **Score per coin:** compute each player's score divided by their inserted
  coins, pass that metric to the OS ranking service, and show how the four-way
  high-score display makes efficiency—not just total spending—the comparison.
  This deserves a small worked example.
- The HUD/info panel: score, health, class/name, inventory icons, multiplier,
  IT label, GAME OVER/selection states, and the combination of text-layer and
  MOB graphics used to present it.
- Dialogs and messages: first-encounter advice, seen-before flags, power-up and
  item messages, the continue prompt, and the Chapter 6 dialog gate that
  freezes gameplay without stopping the whole frame loop.
- EEPROM: what persists, queued writes, redundant/checksummed storage and
  recovery behavior, the periodic write timer, high scores, settings, and
  statistics. Explain durability without making a stronger power-failure
  guarantee than the verified codec/worker behavior supports.
- The operator's view: difficulty/extra-monster setting, health per coin, coins
  to start, attract sound, speech, secret-code/name-entry option, reduced text,
  reset/default controls, and coin options. Keep the settings table concise.
- Statistics and tuning evidence: active-player time, games/session data,
  normalized score/coin histograms and other operator screens—enough to show
  that the cabinet measured how people played, without cataloging every EEPROM
  byte.

---

## Chapter 15 — The Show (Attract Mode, Demo Playback, and Legend)

*What the cabinet does when nobody is playing, and how recorded control input
uses the real game engine as a presentation system.*

- The attract cycle as a state machine: high scores → title → demo → legend →
  repeat, driven from the same main loop and `game_mode` introduced in
  Chapter 6. Include the real timers and the occasional title/settings work.
- The demo is a recording, not game-playing AI: four ROM stream pointers,
  two-byte duration/input records, active-low joystick bits, and special
  command bytes for dialog/speech or player switching. The standard demo sets
  up maze 102 and uses the player-1 Elf stream.
- Source the claim directly: trace `attract_demo_init` into the same
  `main_move_players`, potion, shot, transporter, and input consumers used by
  real play. A short decoded run of records should show recorded input becoming
  visible movement.
- Determinism, precisely: after the research gate, explain which state is reset
  or fixed (maze, player/class, pointers/timers, frame state, RNG seed if
  verified), which normal random/game systems remain active, and how divergence
  is avoided or tolerated. Do not merely say "the game is deterministic."
- Interruption: coin/start handling, paid/free-play differences, and the
  one-second lockout at the beginning of each attract screen before qualifying
  input transfers to a real session.
- The legend pages: maze 103 as presentation background; overview, rules, and
  monster/power/item explanations; how the game reuses playfield and text
  rendering to teach itself.

---

## Chapter 16 — The Voice (Sound, at Arm's Length)

*The main-game side of sound communication. Detailed sound-board synthesis,
music, and speech-ROM internals are reserved for a future volume.*

- A second computer for sound: the sound board's 6502 CPU, its own ROM and
  sound/speech hardware, and the architectural advantage of running audio work
  separately from the 68010's game loop.
- The wire between them: byte-latch communication exposed through OS services,
  status/full bits, reset/control paths, and the main-CPU interrupt used when
  responses arrive.
- The game side of the conversation: a small command queue in game RAM,
  once-per-frame draining from the main-loop tail, a receive/response handler,
  and recovery behavior when the sound processor resets or stops responding.
- Commands as vocabulary: effects, music, and spoken phrases are command
  numbers. Use `refs/soundcmds.csv` for a few concrete examples tied to moments
  already covered, such as joining, low health, doors, food, the thief, and
  treasure countdowns.
- Speech as game design: character/color-specific phrases, contextual warnings,
  attract/option gating, one-shot dialog flags, and how audio helps four players
  understand a crowded screen.
- Scope boundary: explicitly say that synthesizer programming, voice
  reconstruction, music playback, and the sound ROM will be covered in a
  **future volume**; do not point to a nonexistent companion document.

---

## Chapter 17 — How We Know All This (Methodology and Curiosities)

*How the reverse engineering was performed, how claims were checked, and what
the ROMs reveal—or cannot reveal—about the people and process behind the game.*

- The toolkit and evidence ladder: decades of manual notes, radare2
  disassembly/annotation, targeted MAME tracing, `python-gex` rendering,
  AI-assisted analysis, and generated contract/coverage reports. Explain what
  each tool can and cannot prove.
- Keeping the AI and humans honest: byte classification, callable contracts,
  control-target and RAM-reference reconciliation, regenerable CSV artifacts,
  confidence labels, independent implementations, screenshots/traces, and the
  difference between semantic naming and mechanical verification.
- What the code reveals about its construction: compiled C conventions,
  compiler-vendor attribution as inference, hand-written assembly leaves such
  as input debouncing and Slapstic access, table-driven data, and the disciplined
  OS/game interface.
- The Morse copyright trap: nine runtime-dead game-ROM bytes decode to
  `COPYRIGHT 1986 ATARI GAMES`. Explain Atari's documented technique using Ed
  Logg's Centipede affidavit, which describes a nonfunctional data pattern read
  as International Morse code and used to prove copying:
  <https://arcadeblogger.com/wp-content/uploads/2019/06/ed-logg.pdf>. Present
  Gauntlet II's decoded bytes and the historical evidence together.
- A brief ghost in the OS image: a runtime-dead retained game-support payload
  exists in the supplied OS ROM. Mention it only as an archaeological
  curiosity. Its exact provenance is not encoded; a possible relationship to
  earlier Atari System 1 software such as Marble Madness is a future research
  question, not a fact needed by this volume.
- What cannot be recovered from runtime artifacts alone: exact build
  provenance, original symbol names, intent behind reserved/dead regions, and
  physical open-bus values. End by distinguishing an unanswered historical
  question from an undocumented runtime behavior.
- Where to go next: the technical chapters in `doc/`, generated audits,
  radare2 loader, maze/graphics tools in `python-gex/`, the future sound volume,
  and concrete follow-up projects such as System 1 BIOS comparison.

---

## Appendix — Glossary and Repository Map (`book/appendix_glossary.md`)

- Alphabetical glossary of every term of art the book introduces: MOB,
  playfield, VBLANK, palette, bank switching, Slapstic, EEPROM, watchdog,
  attract mode, maze versus level, slot/tile/pixel coordinates, generator,
  IT, score per coin, and so on. Each definition should match its first use.
- A short "map of the repository" table: which `doc/` file, generated artifact,
  reference, or tool to open for each kind of question.
- A compact source note for external material used by the book, including MAME
  references and the Ed Logg affidavit, so provenance remains visible without
  turning chapter prose into academic apparatus.
- A checklist for final publication: chapter-opening promises present,
  diagrams/images sourced, "Under the hood" boxes checked, internal links
  valid, terminology consistent, and zero `**[needs verification]**` markers.
