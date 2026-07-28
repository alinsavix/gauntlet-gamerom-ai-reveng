# Gauntlet II: How It Works — Book Outline

This file is the authoritative outline and style contract for a reader-friendly
book about the internals of the Gauntlet II arcade game, derived from the
reverse-engineering documentation in this repository. It is written so that a
writing agent can produce the final chapters from it without needing any other
briefing.

---

## Frontmatter: Goals, Audience, and Constraints

### Purpose

The technical documentation in `doc/` is exhaustive but written for someone
already deep in the game's internals: it is organized around addresses,
function contracts, and audit coverage. This book re-presents that knowledge
as a narrative that a newcomer can read front to back, with each chapter
building only on concepts introduced in earlier chapters.

### Audience

A **hobbyist programmer**: comfortable with general programming concepts
(variables, loops, arrays, lookup tables, memory, bits and hex numbers), but
with **no** knowledge of 68000-family assembly, arcade hardware, or this
game's internals. Do not assume they know what a sprite engine, an interrupt,
a palette, or a bank-switch is — each of these must be introduced before use.
Do assume they can read a short pseudocode block and a labeled table.

### Deliverable format

- A new directory `book/` at the repository root.
- One markdown file per chapter, numbered: `book/01_introduction.md`,
  `book/02_the_machine.md`, etc. (final filenames should match the chapter
  titles below, adjusted to `NN_snake_case.md`).
- A `book/README.md` containing a one-paragraph description of the book and a
  linked table of contents with a one-line summary per chapter.
- A final `book/appendix_glossary.md` (see Appendix section at the end).
- Target length: roughly **1,500–3,000 words per chapter** (the grab-bag
  chapters 10, 11, and 14 may run longer). Favor completeness of *concepts*
  over completeness of *inventory* — this book never needs to list every
  function, table, or maze.

### Voice and style rules

1. **Prose first.** Explain mechanisms in plain sentences. A reader should be
   able to follow every chapter without reading a single line of code.
2. **Pseudocode over assembly.** When showing logic, use short high-level
   pseudocode (Python-ish or C-ish, whichever reads cleaner). Raw 68010
   assembly is allowed only when the *assembly itself* is the point (e.g., a
   clever trick that pseudocode would hide), and must be explained line by
   line when used.
3. **Tables are welcome** when they mirror an actual table in the ROM —
   always label rows and columns with meaningful names, never raw offsets.
   Example of the desired register: instead of describing a speed lookup as
   address arithmetic, say "the game keeps a table in ROM with one column per
   character class and two rows — normal speed, and speed with an extra-speed
   potion" and show that table with labeled headers.
4. **Diagrams** (mermaid preferred) are encouraged when they
   genuinely simplify — flow of a frame, layering of the display, the
   maze-decode pipeline. Keep them small; a diagram that needs a legend longer
   than itself should be prose instead.
5. **Names in prose: yes. Addresses in prose: no.** Using a real function or
   variable name in body text (`g2mainloop`, `game_mode`, `find_maze`) is
   encouraged whenever it beats a roundabout description — especially for
   the higher-level functions a chapter keeps returning to. Introduce each
   name once in plain language ("the main loop, `g2mainloop`, …") and use it
   freely afterward. Raw hex addresses stay out of body prose. Every chapter
   still ends with an **"Under the hood"** box: a short bulleted list
   mapping the chapter's topics (including any names used in prose) to their
   addresses and the `doc/` file/section that covers them, for readers who
   want to go deeper. Format:

   > **Under the hood**
   > - The main loop described here is `g2mainloop` (0x42A66); the full
   >   verified call sequence is in `doc/03_game_rom_structure.md` §2.
   > - The VBLANK semaphore is the word at 0x904002.
6. **Introduce before use.** Each chapter may rely on concepts from earlier
   chapters only. If a later chapter needs a concept out of order, add a
   one-sentence reminder with a link back ("as covered in Chapter 3, sprites
   are drawn from four parallel tables").
7. **Consistent terminology.** First use: "motion objects — 'MOBs' — the
   hardware's name for sprites"; thereafter "MOB" or "sprite (MOB)". Use
   "playfield" for the maze tile layer, "text layer" for alphanumerics,
   "Slapstic ROM" for the bank-switched level-data ROM, "OS ROM" and
   "game ROM" for the other two. "Level" is what the player sees counted on
   screen; "maze" is the stored record (Level N = Maze N+4 — establish this
   once in Chapter 6 and stay consistent).
8. **Light, curious tone.** This is a tour, not a spec. Wry asides are fine;
   memes and forced jokes are not. Write like a good conference talk.

### Accuracy constraints (important)

- **Everything factual must trace back to `doc/`** (or `refs/HW_WRITEUP.md`).
  Do not fill factual gaps with guesses about "how arcade games usually
  work" — if the docs don't say it, either omit it, or write it anyway and
  flag it for review (see the needs-verification rule below).
- **MAME source is a legitimate research aid.** Consulting MAME's Gauntlet
  driver to understand a behavior well enough to explain it clearly is fine;
  just never cite or mention MAME as a source in the book text, and flag any
  claim that rests *only* on MAME with the needs-verification marker.
- **Folklore is flavor, not fact.** Well-known Gauntlet lore and player
  culture are welcome as color, framed as lore. Don't let folklore quietly
  become a factual claim about what the code does.
- The `doc/` files carry confidence labels (**Verified**, **Strong
  inference**, **Contradicted**, etc.). State Verified material as fact.
  Present Strong-inference material with a softener ("almost certainly",
  "the evidence points to"). Never present Contradicted claims; `doc/` files
  contain corrections of earlier wrong claims — always use the corrected
  version.
- **Needs-verification markers.** When a worthwhile detail can't be fully
  confirmed from `doc/`, don't water it down — write it at the intended
  level of specificity and flag it with the literal inline marker
  `**[needs verification]**` immediately after the claim (one marker per
  claim, grep-able), so a human pass can find and confirm or correct each
  one before publication.
- `python-gex/` (the ROM extractor) is a working demonstration of the data
  formats (tiles, stamps, maze records). Its source may be consulted to
  clarify formats, and the book may mention it as a companion tool, but the
  book must not require the reader to run it.

### Primary sources by chapter

| Chapter | Main sources |
|---------|--------------|
| 1 | `README.md`, `doc/INDEX.md` |
| 2 | `doc/01_hardware.md`, `refs/HW_WRITEUP.md` |
| 3 | `doc/01_hardware.md` (tiles, palettes, MOBs, alpha, priority) |
| 4 | `doc/02_os_rom.md` (boot, vectors, jump tables, self-test) |
| 5 | `doc/03_game_rom_structure.md` (main loop, game modes, VBLANK) |
| 6 | `doc/06_maze_catalog.md`, `doc/04_game_subsystems.md` §5, `doc/05_data_reference.md` §3.19–3.20, §4.1; `python-gex/` |
| 7 | `doc/04_game_subsystems.md` §4, §23; `doc/05_data_reference.md` §1.7, §1.11, §3 |
| 8 | `doc/04_game_subsystems.md` §3, §26; `doc/05_data_reference.md` §7 |
| 9 | `doc/04_game_subsystems.md` §8, §9 |
| 10 | `doc/04_game_subsystems.md` §7, §12, §16, §18, §19, §10.6 |
| 11 | `doc/04_game_subsystems.md` §10, §14, §20, §25; `doc/02_os_rom.md` §8.9–8.12 |
| 12 | `doc/04_game_subsystems.md` §6, §22; `doc/03_game_rom_structure.md` §2.5 |
| 13 | `doc/04_game_subsystems.md` §11; `doc/02_os_rom.md` §6.7, §8.7–8.8; `refs/soundcmds.csv` |
| 14 | `README.md`, `doc/03_game_rom_structure.md` §1.3, §4; `doc/08_known_issues.md`, `doc/02_os_rom.md` §10.5, §12 |

---

## Chapter 1 — Welcome to the Machine (Introduction)

*Sets expectations: what the game is, what "reverse engineering it" produced,
and how to read this book.*

- What Gauntlet II is (Atari Games, 1986; up to four players; the arcade
  context) and why its internals are worth a book: it's a complete, readable
  example of how a golden-age arcade game actually works.
- What this book is based on: a decades-long reverse-engineering effort,
  recently completed with AI assistance, that documented essentially every
  byte of the game's three program ROMs. What "reverse engineering" means
  here (reading the machine code and data the shipped game contains — no
  source code was ever available).
- The cast of chips, at a headline level: one main CPU running the show, a
  separate small computer dedicated to sound, video hardware that draws the
  screen from tables, and three ROMs with distinct jobs (OS ROM, game ROM,
  level-data ROM) — each gets proper treatment in later chapters.
- How to read this book: chapters build in order; every chapter ends with an
  "Under the hood" box pointing into the technical docs (`doc/`) for the
  reader who wants addresses and disassembly; a glossary appendix exists.
- A frame-of-reference teaser: everything the player experiences is produced
  sixty times per second by one loop of code — a promise the book will pay
  off in Chapter 5.

---

## Chapter 2 — The Machine (Hardware Overview)

*The reader leaves knowing what hardware exists and the single most important
idea in the whole book: the CPU doesn't draw anything — it fills in tables,
and the video hardware paints from them.*

- The main CPU: a Motorola 68010, the same family as early Macs and the
  Amiga; briefly what that means (16/32-bit, big-endian) and — for a 1986
  arcade machine — how surprisingly ordinary it is.
- Memory-mapped everything: one address space containing ROM, working RAM,
  video RAM, and hardware control registers, so "writing to the screen" and
  "writing to a variable" are the same instruction. Include a simplified
  memory map (a handful of labeled regions, not the full table).
- The three program ROMs and their jobs: the OS ROM (boot, self-test, shared
  services), the game ROM (all gameplay), and the Slapstic level-data ROM
  (the mazes, behind a bank-switching copy-protection chip — deferred to
  Chapter 6). Graphics live in separate ROMs the CPU can't even read.
- The display in one paragraph: a 336×240 screen refreshed 60 times a second,
  composed by hardware from three layers (maze tiles, sprites, text) — the
  full story is Chapter 3.
- The supporting cast: the sound board's own 6502 CPU (a second computer,
  Chapter 13), the EEPROM that remembers settings and high scores when
  unplugged, coin counters and joystick inputs as readable ports, and the
  watchdog timer that reboots the machine if the code ever stops checking in.

---

## Chapter 3 — Painting the Screen (The Display System)

*How three layers of tables become a picture. This chapter carries the
heaviest conceptual load in the book; lean on diagrams.*

- Tiles: everything visible is built from 8×8-pixel, 16-color tiles stored in
  graphics ROMs. The CPU never touches pixels; it places tile *numbers* into
  video RAM. Introduce palettes here: a tile's pixels are color *indices*,
  looked up in color RAM (with the intensity+RGB format explained briefly).
- The playfield layer: a 64×64 grid of tile words forming a 512×512-pixel
  world of which only a window is visible; the camera is just two scroll
  registers. Each grid word = tile number + palette choice. This is the maze:
  floors, walls, and doors are nothing more than grid entries.
- Motion objects (MOBs) — the sprite system: 1024 possible sprites, each
  described by four parallel tables (which picture, horizontal position,
  vertical position + size, link). Multi-tile sprites (like the huge Death
  figure or the dragon) come from the size fields. Explain the linked-list
  organization: 64 list heads, one per 8-pixel band of the playfield's
  height, each chaining together the sprites whose Y position falls in that
  band; the display hardware traverses these lists to draw, and the game
  walks the same lists itself for collision work.
- Sprite pixel special cases that give the game its look: color 0 is
  transparent, and color 1 is *shadow* — it darkens whatever is underneath
  instead of drawing a color (how monster/player shadows work for free).
- The text layer and layer priority: a character grid overlaying everything,
  with a per-character "opaque" bit; the famous fact that the black screen
  between levels is not the display turning off, but the text layer filled
  with opaque spaces. Close with the full layer-priority stack (text over
  sprites over playfield) and a one-diagram summary of the whole composition
  pipeline.

---

## Chapter 4 — Waking Up (Boot, the OS, and Self-Test)

*What happens between power-on and the attract screen, and the elegant
division of labor between the OS ROM and the game ROM.*

- The 68010's first breath: the CPU reads its initial stack pointer and start
  address from the very beginning of the OS ROM; the OS then tests RAM,
  checksums the ROMs, and refuses to continue (with an on-screen error) if
  anything fails. Explain the destructive-RAM-test trick of running with no
  usable RAM in the earliest stage.
- Why there's an "OS" at all: Atari shipped a common services layer — text
  drawing, coin/credit accounting, EEPROM storage, sound communication,
  self-test — so game code doesn't reimplement it. Frame it as an API:
  a fixed jump table at a known place in the OS ROM that game code calls.
- The contract in the other direction: the game ROM begins with a header of
  hook slots (start, per-frame interrupt, options screen, etc.) that the OS
  calls through. This two-way jump-table contract is what makes OS and game
  separately replaceable — and is why the OS ROM is shared across Atari
  System 1-era Gauntlet variants.
- Interrupts as the machine's pulse: what an interrupt is (hardware tapping
  the CPU on the shoulder), and the ones that matter here — chiefly the
  once-per-frame VBLANK interrupt (the 60 Hz heartbeat everything else
  synchronizes to, setting up Chapter 5) and the sound-CPU interrupt
  (Chapter 13). Mention the watchdog: unexpected interrupts are deliberately
  routed into traps that let the watchdog reboot the machine.
- Self-test mode: the operator-facing diagnostic world hidden behind a
  switch — RAM/ROM checks, color and sprite test screens, sound tests,
  coin-option and difficulty editors, and the statistics screens, all stored
  in the EEPROM the game reads its settings from at boot.

---

## Chapter 5 — The Heartbeat (The Main Loop)

*The single most important piece of code in the game: one loop, sixty times a
second, that runs everything the player ever sees.*

- The frame-lock idea: the game does one full update per screen refresh. The
  VBLANK interrupt sets a flag; the main loop finishes its work, then spins
  waiting for that flag before starting the next frame. Pseudocode of the
  whole loop skeleton (wait → housekeeping → gameplay → UI/sound → repeat).
- A guided walk through one frame's call list, grouped conceptually rather
  than exhaustively: always-run services (logo color cycling, input
  debouncing, coin check); the gameplay block (doors, shots, players,
  camera, monsters, dragon, thief, health drain, walls, exits…); the
  always-run tail (score display, attract state, EEPROM writes, sound).
- The dialog gate: when a message box is up, the entire sixteen-call gameplay
  block is skipped in one branch — which is why the world genuinely freezes
  during dialogs while scores and sound keep working.
- The mode variable: one word distinguishes normal play, treasure-room exit,
  and the attract-family modes (title, high scores, demo, legend); most
  subsystems check it themselves, so the same loop serves the whole game.
  Include a simplified "what runs when" table (a handful of representative
  rows, not all 29).
- Keeping time honestly: the frame counter, and the overflow detector that
  notices when a frame's work overran into the next VBLANK — the game's
  built-in "we're running late" signal, which decays back to zero when
  performance recovers.

---

## Chapter 6 — Building a Level (Mazes and the Slapstic)

*From a maze number to a playable level: bank-switched ROM, a compact
compression scheme, and a decoder that plants everything in the world.*

- Levels vs. mazes: the ROM stores 117 maze records — 97 playable levels
  (Level N = Maze N+4), a demo maze, the legend screen, eleven treasure
  rooms, and two secret rooms. The maze is the unit of storage; the level is
  the unit of play.
- The Slapstic: level data lives in a 32 KB ROM visible only through an 8 KB
  window, with a copy-protection chip choosing which quarter is visible;
  switching banks requires a specific access ritual. Why Atari did this, and
  how the game looks up a maze: a packed 2-bit bank table plus a 117-entry
  pointer table.
- Anatomy of a maze record: a small header (secret-trick code, level flags,
  wall/floor pattern and color choices, horizontal/vertical type bytes)
  followed by a compressed object stream. Explain the flag system with a
  table of the fun ones (invisible walls, wrap-around, moving exits, "shots
  stun other players"…).
- The decoder: the compressed stream is a bytecode walked with a cursor over
  the maze grid — draw runs of wall, skip, place object, repeat — expanding
  into logical walls, floors, doors, items, monsters, and generators. Show a
  small worked example (a few bytes → a few placed cells), using the format
  knowledge demonstrated by `python-gex`. Introduce here the two coordinate
  systems used everywhere after this: *slot* coordinates (maze grid cells)
  vs. *pixel* coordinates (playfield positions), and how a slot maps to a
  2×2 block of playfield tiles.
- Placement and finishing touches: objects become MOBs and tile records;
  post-decode scans build the transporter and exit tables; wall tiles get
  their connected shapes; and the difficulty spice — at higher levels the
  game *randomly adds* extra flags (fast monsters, invisible walls…) on top
  of the stored ones, plus randomly scattered food.

---

## Chapter 7 — The Heroes (Players)

*Everything about the four player characters: stats, movement, health,
inventory, and the strange democracy of a four-joystick cabinet.*

- The four classes as data: per-class stat tables in ROM (speed, shot power,
  shot speed, armor, magic…) — present one or two as labeled tables in the
  book's signature style. Character choice is literally a column index.
- Joining and leaving: coin-in creates a hero mid-game at a spawn point;
  what a "credit" buys under the different operator settings; name entry and
  how per-player state is organized (parallel arrays indexed by player,
  echoing the hardware's own style).
- Movement as negotiation: each frame, per player: read the debounced
  joystick, look up speed, propose a move in slot/pixel terms, and test it
  against walls, doors, monsters, and other players before committing —
  described as a pipeline, with the key insight that "walls" are consulted
  as game-state, not by reading pixels.
- Health as a currency: the constant drain timer, food, potions and other
  pickups via the tile-interaction dispatch (food, keys, treasure, doors,
  transporters, exit — each a case in one big "what did I just step on?"
  switch), damage, death, and what actually happens at zero health.
- Gauntlet II's signature player mechanics: the IT mechanic (tag — one
  player is "IT", labeled in their HUD, transferred by touch), shot-stun and
  friendly-fire flags from Chapter 6 affecting player-vs-player play, and
  the score multiplier system for treasure.

---

## Chapter 8 — The Horde (Monsters and Combat)

*Ghosts, grunts, demons, lobbers, sorcerers, and Death — how the game animates
a screenful of enemies on a 1986 CPU budget.*

- The monster roster as data: types, strength tiers (the palette tells you
  the tier), and per-type parameter tables; generators as a special kind of
  monster that spawns others, with spawn pacing rules.
- One brain, many bodies: monsters share a common handler with per-type
  hooks; each frame the game walks the monster list and gives each a small
  slice of decision-making. How "move toward the player" works on a grid,
  and what the odd-angle and double-speed level flags actually change.
- Type specialties: lobbers arc shots over walls, sorcerers blink in and out
  of existence, Death drains health by touch until it dies of overeating,
  ghosts damage-and-die on contact. Keep each to a paragraph — behavior, not
  exhaustive parameters.
- Shots and hit resolution: players and monsters share a projectile system;
  how a shot finds what it hit (using the per-band sprite lists from
  Chapter 3), damage accumulation versus instant kills, and stun behavior.
- Dying by the numbers: monster death, score awards, the death-potion
  mass-kill, and how corpses/scores are displayed with floating score MOBs —
  linking back to sprite machinery the reader already knows.

---

## Chapter 9 — Special Guests (The Dragon and the Thief)

*Two custom-built characters that live outside the common monster machinery.*

- Why they're special: both have private state machines and private data
  tables instead of the shared monster handler — the cost (code size) and
  the payoff (distinctive behavior).
- The dragon, Gauntlet II's mini-boss: a multi-sprite body (head, neck
  segments, body) assembled from MOBs; its state machine (dormant, active,
  attacking, dying) and fire-breathing attacks.
- The dragon's path system: pre-authored movement routes in ROM data that
  the dragon follows through the maze — a rare case of scripted movement in
  an otherwise reactive game.
- The thief and the mugger: the timer that decides when a thief visits
  (tuned by player wealth and level number — the game literally computes a
  weighted "wealth" score to pick the richest victim), its
  pursue/steal/escape state machine including shot-dodging, what it steals
  (an item or health), and the mugger variant (a mode flag on the same state
  machine; `doc/` records little beyond the flag itself, so describe
  mugger-specific behavior at full specificity but tag it
  **[needs verification]**).
- What their design says about the game: hand-tuned exceptions layered on a
  general engine — a pattern the reader will recognize from modern game
  development.

---

## Chapter 10 — A Living Maze (World Mechanics and Hazards)

*The tricks that keep 97 levels interesting: everything in the world that
moves, hides, teleports, or lies to you. Grab-bag chapter; more bullets by
design.*

- Transporters: how destination selection works, the sparkle animation, and
  the post-decode transporter table from Chapter 6 coming into play.
- Forcefields: segment tables, the color-cycling effect (palette animation,
  not redrawn graphics — callback to Chapter 3), and timed on/off patterns
  that make them passable.
- Walls that misbehave: cyclic walls that open and close on timers, the
  random wall-mover that relocates maze walls behind your back, destructible
  walls (two tiers), and invisible walls (a flag from Chapter 6 finally paid
  off: the tile is there, the graphics just aren't).
- Exits, honest and otherwise: normal exits, moving exits, fake exits,
  "only one of these exits is real", and the exit sequence that walks the
  player out and tallies the level.
- Traps and stun tiles: the tile types that hurt or hold you, and the acid
  puddle / slow-motion floor effects.
- Treasure rooms: the timed bonus levels between worlds — timer, scoring,
  and the special "treasure room exit" game mode from Chapter 5.
- Secret rooms: the hidden challenge system — per-level secret tricks (a
  table of examples: "don't shoot food", "stay invulnerable-free"…), the
  challenge codes, the two secret-room layouts they select, and how the game
  announces success.

---

## Chapter 11 — Keeping Score (Money, Scores, and Memory)

*The commercial machinery: coins to credits to health, scores to EEPROM, and
the HUD that displays it all.*

- Coin to credit to health: the coin-detection path in the main loop, the
  OS's coin/credit accounting, and operator-configurable "health per coin"
  economics — the arcade business model expressed as game settings.
- Scoring: what scores points, the treasure multiplier, floating score
  displays in the playfield, and the high-score check at game end with the
  initials-entry flow.
- The info panel: each player's HUD column (score, health, inventory icons,
  the IT label) as text-layer and MOB composition — a concrete payoff of
  Chapter 3's layer system.
- Dialogs and messages: the first-encounter dialog system ("Ghosts damage
  you on contact!") with its seen-it-before bit flags, the continue prompt,
  and how the dialog timer freezes gameplay (the Chapter 5 gate, seen from
  the other side).
- The EEPROM: what persists (settings, statistics, high scores), the
  redundant-block storage scheme that survives power loss mid-write, and the
  periodic write timer in the main loop — why the machine remembers you.

---

## Chapter 12 — The Show (Attract Mode and the Demo)

*What the machine does when nobody's playing — and how the self-playing demo
is a recording, not an AI.*

- The attract cycle as a state machine: high scores → title → self-playing
  demo → legend (monster/item explanations) → repeat, driven from the main
  loop by the mode variable introduced in Chapter 5.
- The demo is a tape: recorded joystick/button inputs stored in ROM, played
  back through the same input path real players use — with the consequence
  that the demo runs the real game engine on a real maze (the dedicated demo
  maze from Chapter 6).
- Determinism and its limits: why input playback works (same maze, same
  seeded starting state) and what the recording format looks like at a high
  level.
- Interruption: how a coin drop or start press exits attract mode cleanly at
  any point, and what gets reset on the way into a real game.
- Character select: the pre-game screen where each cabinet position claims a
  hero, its timeout, and how it hands off to level 1.

---

## Chapter 13 — The Voice (Sound, at Arm's Length)

*Broad strokes only: the sound hardware design, and how the game talks to it.
The sound board's internals get their own separate writeup.*

- A second computer for sound: the sound board runs its own 6502 CPU with
  its own ROM and its own synthesizer/speech chips; the main CPU never makes
  a sound itself — it sends requests. Why this split was standard practice
  (timing isolation, parallel development).
- The wire between them: byte-latch communication surfaced through OS
  services, with an interrupt on the main CPU when the sound CPU replies —
  connecting back to the interrupt map from Chapter 4.
- The game side of the conversation: a small queue in game RAM that gameplay
  code drops sound-command bytes into, drained once per frame by the main
  loop (Chapter 5's tail), plus the response handler that processes what the
  sound CPU sends back — including recovery if the sound CPU resets.
- Commands as vocabulary: sound effects, music cues, and speech are all just
  command numbers (with `refs/soundcmds.csv` as the phrasebook); a few
  concrete examples tied to moments the reader knows ("Elf shot the food" is
  a byte with a number).
- Where to go for the rest: an explicit pointer that voice synthesis, music
  playback, and the sound ROM's internals are covered in the companion sound
  writeup, not here.

---

## Chapter 14 — How We Know All This (Methodology and Curiosities)

*The closing chapter: how the reverse engineering was actually done, and the
treasures found along the way. May run long; it's the dessert course.*

- The toolkit: disassembly with radare2, live tracing in MAME, decades of
  prior manual work, and a recent AI-assisted push; what "every byte
  classified" means (code vs. data vs. padding) and how the audit kept the
  AI honest — machine-checked contracts per function, regenerable CSV
  reports, confidence labels on every claim.
- What the code itself revealed about its authors: compiled C with
  hand-written assembly hot paths, the compiler's fingerprints, calling
  conventions as archaeology, and the OS/game split as 1980s software
  engineering discipline.
- The Morse code Easter egg: nine bytes in the game ROM header that decode,
  bit by bit, to "COPYRIGHT 1986 ATARI GAMES" in Morse — a copyright trap in
  the tradition of Atari's Centipede affidavit. Show the decoding.
- Ghosts in the OS ROM: the runtime-dead "retained module" — a chunk of
  earlier Gauntlet game code, complete with gameplay hint strings and
  factory high-score tables, shipped inside every OS ROM but never executed.
- What remains unknown — and why that's the honest ending: open questions
  the ROMs alone can't answer (build provenance, intent behind reserved
  areas, physical open-bus behavior), plus an invitation: the full technical
  docs in `doc/`, the extractor in `python-gex/`, and everything the curious
  reader needs to go one level deeper.

---

## Appendix — Glossary (book/appendix_glossary.md)

- Alphabetical glossary of every term of art the book introduces (MOB,
  playfield, VBLANK, palette, bank switching, Slapstic, EEPROM, watchdog,
  attract mode, slot vs. pixel coordinates, generator, IT, …), each defined
  in one or two sentences consistent with its introduction in the chapters.
- A short "map of the repository" table: which `doc/` file to open for which
  kind of question, mirroring the per-chapter source table above.
