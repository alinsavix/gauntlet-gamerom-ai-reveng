# Rewrite ledger: removed, moved, and deferred

This is an editorial review document, not part of the book's reading order.
It records substantive material left out of the September 2026 rewrite
and identifies places where useful detail could return. Repeated summaries,
routine sentence edits, and duplicate source references are not itemized.

The comparison manuscript is the tracked `book` directory at commit
`38f4958a075ea866ad2d7480f1bc8c497ebbf57a`. Its old filenames and section
titles below identify recoverable passages in Git history; they are not
links to files that still exist in the new book. A local snapshot was also
taken before rewriting. Git history is the durable shared reference.

**Deferred** means useful detail awaiting a fuller explanation.
**Moved** means the subject has a new home, often in shortened form.
**Removed** means deliberately excluded from the reader's book.
**Expanded** means the mechanism now has a developed explanation in the
September 9 full versions of Chapters 3-8; any remaining detail is named
in that row. This does not mean the old passage was restored verbatim.
An incorrect claim is not deferred material to reinsert: recover the
supported mechanism from the current evidence, not the old wording.

## The old chapters and their new homes

| Previous chapter | New home for the subject |
|------------------|--------------------------|
| 01, How to play | [1, Enter the Gauntlet](01_how_to_play.md); detailed combat in [2](02_one_arrow.md), multiplayer in [3](03_four_players.md) |
| 02, Introduction | Brief orientation in [README](README.md); provenance in [18](18_reading_the_roms.md) |
| 03, Hardware overview | [5, Painting the dungeon](05_painting_the_dungeon.md), [16, Waking the cabinet](16_waking_the_cabinet.md), [18](18_reading_the_roms.md) |
| 04, Display system | [5, Painting the dungeon](05_painting_the_dungeon.md) |
| 05, Boot and OS | [16, Waking the cabinet](16_waking_the_cabinet.md) |
| 06, Main loop | [7, The game's clock](07_the_games_clock.md); host tooling in [17](17_gauntpy.md) |
| 07, Session lifecycle | [1](01_how_to_play.md), [3](03_four_players.md), [8](08_what_a_quarter_buys.md), [9](09_mazes_and_slapstic.md), [13](13_secrets_and_treasure.md), [15](15_attract_and_demo.md) |
| 08, World in memory | [6, A world in ten bytes](06_a_world_in_ten_bytes.md); camera in [3](03_four_players.md) |
| 09, Mazes and Slapstic | [9, The next maze](09_mazes_and_slapstic.md) |
| 10, Players | [1](01_how_to_play.md), [2](02_one_arrow.md), [3](03_four_players.md), [8](08_what_a_quarter_buys.md) |
| 11, Monsters | [4, A room full of monsters](04_the_horde.md); shot mechanics in [2](02_one_arrow.md) |
| 12, Dragon, thief, mugger | Separate [thief](11_the_thiefs_trail.md) and [dragon](12_fighting_the_dragon.md) chapters |
| 13, Living maze | [10, The living maze](10_the_living_maze.md) and [13, Secrets and treasure](13_secrets_and_treasure.md) |
| 14, Score and economics | [8, What a quarter buys](08_what_a_quarter_buys.md); voice in [14](14_a_machine_that_speaks.md), host UI in [17](17_gauntpy.md) |
| 15, Attract and demo | [15, When nobody is playing](15_attract_and_demo.md) |
| 16, Sound | [14, A machine that speaks](14_a_machine_that_speaks.md) |
| 17, Methodology | [18, Reading the ROMs](18_reading_the_roms.md) |
| Appendix | Shorter [glossary and source map](appendix_glossary.md); editorial rules in [OUTLINE](OUTLINE.md) |

## Changes applying across the manuscript

| Material | Fate | Reason and possible restoration |
|----------|------|---------------------------------|
| Printed learning objectives, prerequisite lists, chapter summaries that repeat the opening | Removed | Their useful purpose survives in editorial questions and coverage planning. Do not restore the boilerplate. |
| Sentence-form bans and rigid chapter-opening requirements | Removed | Replaced with positive requirements for causal explanation, sources, examples, and readable prose. |
| Accounts of what earlier documentation got wrong | Removed | Correct mechanisms are integrated into new explanations. Research history remains in the technical documentation where appropriate. |
| Captured `gauntpy` bugs, exact coordinates from regressions, and instructions to future port maintainers | Removed | Keep implementation guidance in `gauntpy` and `doc`. Restore only if rewritten as a deliberate, useful investigation in Chapter 18. |
| Host save files, diagnostics, benchmarks, and stress modes embedded in arcade chapters | Moved | Chapter 17 explains current use and the simulation/host boundary. Fine-grained implementation history is omitted. |
| Exhaustive addresses, bit layouts, callable totals, table inventories, and audit counts | Mostly removed from body | Chapter source notes link to maintained references. A small layout or assembly example may return where it teaches a mechanism. |
| Claims that audit coverage establishes complete semantic understanding | Removed | Chapter 18 distinguishes structural coverage from behavior and from evidence about intent. |
| Promises of a future sound-ROM volume | Removed | State this book's scope without committing to another publication. |
| Old numbered image identifiers | Retained | All original image files remain available, even when not used in this pass. Renumbering the book does not require regenerating its art. |
| Old chapter filenames cited by Python documentation | Updated | References now point at the corresponding new chapters. These changes affect comments/documentation only, not simulation behavior. |
| Contributor instructions treating the book as a complete implementation reference | Updated | The gauntpy documentation now distinguishes the short narrative drafts from exact ROM contracts and asks future edits to revise explanations instead of appending repair history. |

## Opening and lifecycle material

### Former 01_how_to_play.md

The controls, color/class distinction, health economy, shared screen,
joining, exits, and major kinds of encounter remain in the full opening
chapter. The old feature-by-feature preview and long visual-vocabulary
list have been replaced by situations in which those features matter.

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "Choosing your hero": broad class superlatives | Rewritten / expanded | Chapter 2 supplies shot comparisons. Chapter 3 now works movement patterns, demon-shot armor costs, and a shared potion decision rather than assigning a universally best class. |
| "Health is money": food and damage summary | Rewritten | Ordinary wholesome food is 100 health; variable and poisoned variants need their own rules. Friendly fire depends on level flags. Chapter 8 owns the fuller accounting. |
| "The shape of a game": whole-session Mermaid graph | Deferred | A future diagram should show concurrent player lifecycles rather than imply every player dies, continues, and enters initials together. Candidate homes: Chapters 3 and 8. |
| "What makes it Gauntlet II": compact list of every feature and chapter number | Removed as a list | Subjects remain in the new reading plan. Expand them where their consequences can be explained, rather than rebuilding an introductory catalog. |
| Claimed first appearance level of the dragon | Deferred | Check the level-setup gate and distinguish authored placement from runtime enabling before restoring in Chapter 12. |
| Secret objectives described as belonging to every ordinary level | Rewritten | Eligibility and per-player/multiplayer conditions belong in Chapter 13; the introduction no longer universalizes them. |
| Control-panel illustration's embedded Fire/start caption | Corrected asset | The generator text and image now identify Magic as start/join. There is no correction note in the reader's chapter. |

### Former 02_introduction.md

The old introduction has no replacement chapter at the front. The book
now earns its technical detail through play before discussing the work
that produced the explanations.

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "Why this machine deserves a book": ROM-size comparison with web pages | Removed | The concrete game supplies the motivation. Storage figures may return in a useful compression or hardware comparison. |
| "What reverse engineered means here": project history, decades of manual work, AI-assisted pass, modern function names | Moved | Chapter 18 carries the short account; README gives only the reading orientation. |
| "The cast of chips": full early hardware cast | Moved | Chapter 5 introduces hardware with the picture it must produce; Chapter 14 introduces the sound processor when it becomes relevant. |
| "What thoroughly documented means": byte totals, region totals, contract counts, coverage claims | Removed | Maintained reports remain in `doc/generated`. Do not turn changing audit totals into the book's evidence argument. |
| "How to read this book": strict front-to-back dependency contract and confidence-label tutorial | Shortened / moved | README explains the new draft state. Chapter 18 explains evidence without making it a prerequisite for Chapter 1. |
| "The heartbeat, briefly" | Moved | Frames are introduced with the shot in Chapter 2 and developed in Chapter 7. |

### Former 07_session_lifecycle.md

This chapter was split because the start-to-finish player experience and
the entire implementation state machine need different levels of detail.
The new opening explains the experience. Detailed transitions can return
alongside the particular decisions they govern.

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "One evening, two stories" and "Four stories at once": global mode versus independent player status | Expanded; full status table deferred | Chapter 3 follows concurrent selection, fighting, exiting, and player endings. Chapter 8 distinguishes live top-up, continued-player initialization, and ranking. A full concurrent-state diagram and secret-winner states remain for later treatment. |
| "The idle machine": exact screen timers and one-second attract input lockouts | Moved / deferred | Chapter 15 owns idle-screen controls. Distinguish switching attract pages from starting a paid session. |
| "A coin becomes a hero": join wrapper, placement, finalizer, installed character helpers | Expanded / partly deferred | Chapter 3 works a failed and successful late-join placement before finalization. Chapter 8 follows credit into selection. Installed character-helper details remain in the technical docs. |
| Saved PLAYERSTART and removal of unused start markers | Partly expanded | Chapter 3 contrasts the remembered first-player start with a neighbor search for a late join. Chapter 9 still owns full setup and disposal of unused markers; port-failure commentary remains excluded. |
| "Starting a level": selection, curtain, decode, object scan, survivor placement, release | Deferred as a worked sequence | Best restored in Chapter 9 with one real layout. Preserve the distinction between continuing survivors and a fresh join; survivors do not receive another join welcome. |
| Level-entry sound presets, treasure music selected by party size, secret-room music timing, later taunts | Deferred | Chapters 13 and 14 can develop an audio timeline after the ordinary setup explanation. |
| "Leaving a level": individual exit animation and collective handoff | Expanded / partly deferred | Chapter 3 explains an exited player waiting while another remains in the maze. Chapter 10 can develop the exit animation and terrain interaction itself. |
| Treasure transitions and successful/failed secret-room pacing | Moved | Chapter 13. Exact intervals and tally fields need worked examples before restoration. |
| "Death, and the offer": exact ROM prompt and separate timer-field writer | Partly expanded | Chapter 8 explains continue gates and the prompt's Magic control, distinct from live top-up. Full text layout and separate field writer remain deferred; host repair history stays out. |
| Continued player's full starting health versus an active player's increment | Expanded | Chapter 8 works a 750-health paid assignment and a 120-to-870 live top-up. Both use the same selected paid-health value; assignment, addition, and the free-play/demo path remain distinct. |
| "The ceremony": 45-second initials entry and ten-second unranked display | Deferred detail | Chapter 8 for rankings; Chapter 16 for how results persist. |
| "The whole map": complete combined state diagram | Deferred | Do not reinsert unchanged. Draw a simplified concurrent example, then link to numeric states in the technical reference. |

## What the new second chapter deliberately leaves for later

The full shot chapter develops one cycle, not every branch of the combat
dispatcher. It retains the one-slot allocation, four-count launch,
selected speed/damage tables, ordinary grunt progression, generator
demotion, and the difference between a consumed and surviving projectile.

Chapters 4 and 6 now develop monster projectile channels, fractional
lobber motion and its late collision window, position-word packing, and
the separate Death counters. Chapters 3, 4, and 7 connect carried versus
shot-triggered potions to target effects and frame order.

Still deferred are complete direction-specific muzzle offsets, diagonal
velocity rows, ordinary shot animation/lifetime tables, reflection
geometry, special wall dispatch, and secret-objective hooks. Their
possible homes are Chapters 10, 12, and 13, or a focused later refinement.
Restore an exact branch only when a reader-facing example needs it.
The current source of truth is `doc/04_game_subsystems.md`, especially
sections 2.2, 3, and 26, plus the linked ROM tables.

## Hardware, display, and world representation

### Former 03_hardware_overview.md and 04_display_system.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| Hardware, "The main CPU": register and bus widths, address width, endianness, other 68000-family machines | Deferred | Chapter 5 needs only functional orientation; Chapter 18 can introduce byte order when reading a dump. |
| Hardware, "One address space": memory map, memory-mapped I/O, 4 KB spare-video workspace, unfitted main-RAM aperture | Partly expanded | Chapter 5 now includes memory-mapped controls and a functional hardware diagram. Full maps, spare workspace, and qualified unfitted-aperture evidence remain for Chapters 16 and 18 if needed. |
| Hardware, chip assembly and "Three images, three jobs": physical chip pairs, byte interleave, concatenation, checksums, full ROM inventory | Moved / deferred | Chapter 18 and the repository ROM instructions. Chapters 9, 14, and 16 introduce the level, sound, and OS roles in context. |
| Hardware, "The supporting cast": sound recovery, EEPROM unlock/cadence, LEDs and board enable, watchdog | Moved / deferred | Chapters 14 and 16. Add only diagnostic details that help a reader follow a failure. |
| Display, "Tiles": graphics banks, chip wiring, bit-plane reconstruction, graphics inaccessible to main CPU | Shortened / deferred | Chapter 5 retains the direct hardware fetch distinction. A bit-plane decoding example could return in Chapter 18. |
| Display, "Color by table": bank counts, address ranges, IRGB packing, analog intensity model | Expanded / partly deferred | Chapter 5 works palette selection, region sizes, one composed pixel, and IRGB shadow subtraction, including intensity seven reaching zero. Calibrated analog output and a complete address inventory remain deferred. The retained shadow illustration is explicitly approximate. |
| Display, "The playfield": descriptor bits, column-first storage, four-tile cell writes, adjoining-wall restamps | Expanded / partly moved | Chapter 5 calculates the four destinations for row 12, column 20, explains wall restamps, and distinguishes door removal revealing existing floor. Chapter 10 retains ownership of changing connectivity and traversal. |
| Display, host caches and frame-time spikes | Removed maintenance | Raster caches and invalidation policies remain implementation documentation. Host performance can be demonstrated in Chapter 17 without explaining a particular repair. |
| Display, "Motion objects": full dimension encodings and dragon tile-grid image | Expanded | Chapter 5 reuses `ch04_dragon_tiles.png`, works tile order and size-minus-one encoding, and distinguishes one stamp from the articulated encounter in Chapter 12. |
| Display, "The text layer": 64 stored versus 42 visible columns, character ROM, opacity bits | Expanded / partly moved | Chapter 5 explains stored/visible width, character ROM, transparent ink, opaque blanks, and the curtain. Chapter 11 still owns hidden-column route storage. |
| Display, palette programs and distinct exit descriptors | Moved / deferred | Transporter and special-floor cycles in Chapter 10; animated title colors in Chapter 15. |

### Former 08_world_in_memory.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "What a thing is": partial-record validation and cleanup obligations | Removed maintenance | Keep the ten-byte record; do not address future port maintainers in its explanation. |
| "Where a thing is": complete row/column, pixel, upward-V, and playfield-address conversion | Expanded | Chapters 5 and 6 connect cell 404 to playfield addresses, pixel anchors, upward V, packed H/V words, and the biased ownership change during a two-pixel move. |
| "Who gets which slot": all reserved IDs and row-zero setup markers | Partly expanded | Chapter 6 gives the fixed/dynamic ranges, projectile allocations, and reserved-border consequence. Exhaustive effect IDs and setup-marker inventory remain deferred. |
| "The chain": depth-key ties, exact remove/clear APIs, physical SLIP addresses | Partly expanded | Chapter 6 traces insertion, copied type/state with preserved new links, retirement of 404, and shared SLIP entry maintenance. Exhaustive tie rules, endpoint bookkeeping, APIs, and addresses remain reference material. |
| "Three users": asymmetric player probes, top/bottom guards, camera gates, seam arithmetic | Expanded / partly deferred | Chapter 3 develops axis probes, corner assistance, and camera gates; Chapter 6 separates direct shot candidates from traversal and works the 15.5-pixel movement threshold. Exhaustive seam/top/bottom cases remain deferred; capture stories stay removed. |
| "The invisible half": direction nibbles, thief routing, door endpoints, logical/visible walls | Moved | Chapters 10 and 11. |
| "One camera, four players": exact outlier adjustment, wrap folding, clamps, crop versus movement-test origins | Expanded | Chapter 3 works a four-player horizontal extent, smoothing, a wrap comparison, the outlier adjustment, and distinct player edge-test windows. Old screenshots remain unused pending caption review. |

## Player and monster detail

### Former 10_players.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "A hero, by the numbers": full movement, armor, forcefield, damage, and animation tables | Expanded comparisons; remainder deferred | Chapter 3 now works four-frame speed patterns, hand-power bases, and demon-shot armor costs beside Chapter 2's shot comparisons. Chapter 10 owns forcefields; full tables and the animation-strip asset remain optional. |
| "Joining the party": RAM palette helpers and all player-field initialization | Deferred | Restore only if a Chapter 5 hurt-flash example or Chapter 3 join trace needs it. |
| "From switches to intent": direction maps and separate facing/fighting state | Expanded / partly deferred | Chapters 3, 4, and 7 connect facing, achieved movement, lobber lead, held Fire, and Magic edges. Full direction-map inventories remain deferred. |
| "The maze pushes back": poison wobble, acid/stun distinctions, exact lane/camera cases | Expanded / partly moved | Chapter 3 uses complete axis proposals and explicit one-pixel wall responses, poison remapping, and movement stun. Chapter 4 develops Acid; remaining terrain cases belong in Chapter 10. Capture history stays removed. |
| "Swords and arrows": melee damage and cabinet-position random term | Expanded | Chapter 3 distinguishes class-indexed bases, generator hand power, and the separately position-indexed random term, with source references. |
| Shot effects and collision-index tagging | Deferred | Chapter 6 can show why an impact's position differs from its lookup identity; low-level porting warnings remain outside the book. |
| "Potions": complete matrix, shot/enhanced columns, zero semantics, special Acid/Super Sorcerer/dragon branches | Expanded / partly moved | Chapter 3 works all four ordinary users against ghosts and a strongest generator, including carried/shot columns and zero semantics. Chapter 4 covers Acid and Super Sorcerer exceptions; Chapter 7 follows the event across calls. Complete matrix remains deferred; Chapter 12 owns the dragon. |
| "The dwindling number": warning masks, incoming-damage commentary, randomized hurt cooldowns, death audio, reused timers | Moved / deferred | Health accounting in Chapter 8; voice rules in Chapter 14. Visual health pulsing does not accelerate along with heartbeat sound. |
| "Pockets and doors": twelve-item combined capacity and complete inventory-panel illustration | Partly expanded | Chapter 3 works nine keys plus three potions and making room for either kind. Full panel illustration remains deferred. Doors and idle opening belong in Chapter 10; message gating is developed in Chapter 7. |
| "The power-up shelf": six permanent powers, duplicate conversion, temporary invisibility/invulnerability/repulsion/reflection/supershot/transportability | Partly expanded / distributed | Chapter 3 distinguishes the six permanent powers, duplicate conversion, and temporary effects. Full duration tables remain deferred; transport, hidden rewards, and announcements retain their later homes. |
| "When friends become targets": IT color animation, precise friendly-fire damage/stun, sportsmanship hooks | Partly expanded | Chapter 3 develops directional tagging, recipient stun, optional shot stun/damage, and immunity gates. Detailed IT color animation and sportsmanship hooks remain for Chapters 5/13 if useful. |

### Former 11_monsters.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "The roster is a table": all types, families, animation pointers, roster image | Contrasts expanded; inventory deferred | Chapter 4 follows distinct threats through one room rather than listing every type and pointer. Full roster art/table remains deferred. |
| "One brain": fast/odd-angle family configuration, acid masks, slow motion, rotating traversal and culling | Partly expanded | Chapter 4 develops local targeting, occupancy, culling, fast/slow behavior, and Acid. Chapter 6 explains chain traversal and Chapter 7 its frame placement. Full flag/mask inventories remain deferred. |
| "Population controller": full difficulty matrix, signed bonus arithmetic, class-dependent solo initialization | Expanded; complete matrix deferred | Chapter 4 works two generator schedules, chance, level cap, failed placement, overload, and solo/later-join initialization. Chapter 8 calculates accumulated party feedback and live-coin relief. |
| "Specialists": lobber vector arithmetic, fractional motion, exact range gates | Expanded | Chapter 4 works achieved-movement lead, class scalars, range units, fractional accumulation, and the late collision window. A full trajectory/muzzle-offset table remains unnecessary to that example. |
| Super Sorcerer placement and phase transitions | Expanded | Chapter 4 explains rear placement searches and potion reveal followed by later idle behavior, not indefinite movement/attack stun. |
| Death's player-owned accumulator, strict greater-than-200 threshold, armor adjustment, supershots, separate global shot count | Expanded | Chapter 4 works the ninth supershot and contact thresholds, cross-encounter player ownership/reset, and the separate shot-count input to magic scoring. |
| "What a hit costs": complete scoring tables, supershot exceptions, destruction resetting idle timers | Moved / deferred | Chapters 2, 4, and 8; idle-world consequences in Chapter 10. |

### Former 06_main_loop.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "Locked to the beam": saved-state reconstruction, uncapped mode, benchmark internals, stress phases | Moved / shortened | Chapter 17 explains useful current options. Detailed host measurement internals and repair stories are removed. |
| Full named call sequence and mode matrix | Partly expanded | Chapter 7 includes the complete numbered 28-call strip with initializer separate, a five-frame Fire example, dialog timing, alternative potion work, and overflow decay. The exhaustive mode matrix remains in the technical reference. |
| "Cleaning up the electricity": rotate-through-carry and compiler interpretation | Deferred / moved | Chapter 18 for instruction-level evidence. Chapter 7 retains histories for Fire/Magic rather than claiming every direction switch is debounced this way. |
| "Three clocks": interrupt/frame/session taxonomy | Expanded / distributed | Chapter 7 distinguishes fields, interrupt service, frame visits, and skipped health opportunities. Chapter 8 contrasts VBLANK-tracked session time with health drain. Chapter 14 retains the full sound exchange. |
| Overload described as preventing all stutter | Removed claim | Chapter 7 describes a response to missed timing that suppresses spawning and defers sound work; it does not guarantee a fixed simulation rate. |

## Arcade game, companion, and evidence

### Former 05_boot_and_os.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "Two seconds of housekeeping": exact reset vectors, board-latch pulses, delays and watchdog writes | Deferred | Chapter 16 retains reset and watchdog roles. Do not restore an unmeasured startup-duration claim. |
| "Testing the floor": register-held continuation, region order, short/full pattern suites | Core mechanism retained; exact patterns deferred | Chapter 16 explicitly distinguishes the short route's first-word walking-bit stages from full-region testing. A full walkthrough can show one pattern and one failure. |
| "The failure policy": lane checksums, header checks, Slapstic hook, complete flowchart | Shortened / deferred | Chapter 16 distinguishes missing program from checksum failure and the game error entry's startup path. Financial explanations of why faults are tolerated were unsupported and removed. |
| Switch-polarity corrections and historical notes | Removed maintenance | The current self-test behavior is described without its correction history. |
| "Why there is an OS" / "The contract runs both ways": jump-table encoding, optional hooks, header scalars and API inventory | Relationship retained; layout deferred | Chapter 16 can expand one two-way call rather than all fields. Reuse decisions require historical evidence beyond the interface itself. |
| "Interrupts": vector dispatch, OS/game VBLANK ownership, self-jump traps and abort paths | Distributed / deferred | Chapter 7 handles timing. Chapter 16 can follow a specific exception without promising every fault produces a successful recovery. |
| "The operator's back room": every diagnostic screen, sprite controls, convergence, manual sound commands, options/statistics | Deferred | Chapter 16 should expand with actual screens. Pricing/statistics also belong in Chapter 8. |
| EEPROM record decoding and repair | Shortened / deferred | Chapter 16 retains redundant copies and correctable errors. Restore a worked record example, not a claim of whole-record transaction safety. |

### Former 15_attract_and_demo.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "The empty room": mode/timer table, screen-clearing order, legend counter | Durations retained; internal sequence deferred | Chapter 15 can add a small transition diagram and explain which layers persist between screens. |
| "The title screen keeps a small secret": settings-refresh and long-entrance cadences, motion record format, trajectories | Deferred | Chapter 15 keeps long/short entrances and optional theme. Restore a short real motion program with its visible path. |
| "The demo plays the game": complete setup, maze inventory, bit table, first nine input pairs | Selected example retained; remainder deferred | Chapter 15 keeps one decoded pair and both demo illustrations. Expand through an actual movement sequence. |
| "Where the recording is read": separate input consumers, exact join times, no-input spans, transporter coordinates | Deferred | Follow a caption or transport across the input consumers in Chapter 15; keep literal coordinates only when the diagram needs them. |
| "The captions stop the clock": all captions, detailed dual-clock timeline and Reduce Text behavior | Core mechanism retained; rest deferred / moved | Chapter 15 needs an illustrated script-versus-display timeline. Chapter 17 explains the usable Reduce Text option. |
| Keyboard attract routing, rescued demo paths, palette fallbacks, pickup approximations, push-cadence repair stories | Removed maintenance | A current shortcut can enter Chapter 17. Actual arcade pushing belongs in Chapters 3 or 10, without the port's development story. |
| Demo completion: final effect waits and same-frame exit handoff | Shortened | Chapter 15 retains DEMO-to-LEGEND rather than next-playable-level behavior. Exact gates can support its full timeline. |
| "How much repeats": fixed setup versus shared RNG and hazard rerolls | Retained distinction | The literal-address scan cannot alone prove that no other initialization or access exists. Chapter 18 explains that limit; Chapter 17 owns host seed options. |
| "When somebody touches controls": four-position shortcuts and pricing-dependent input masks | Deferred | Chapter 15 distinguishes selecting attract pages from starting a session. Add a compact control guide in expansion. |
| "The legend": combat matrix, complete credits, transparent rectangles, retained scenery, palette cycling | Shortened / deferred | Restore the matrix and credited people in Chapter 15. Detailed rectangles and palette writes belong with a Chapter 5 example or the technical reference. |
| Claims about what designers wanted noticed; modern "integration test" framing | Removed | Describe what the demo demonstrates. Source intentions separately. |

### Former 16_sound.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "Two bytes make a sentence" / "Speech as game design": complete warning selection, power-loss conditions, latch/cooldown lifecycle | Central example retained; branches deferred | Chapter 14 should follow one complete warning, including suppression. A cooldown does not mean automatic periodic repetition. |
| "The second computer": CPU clock, memory sizes, sound chips, pitch and mixer controls | Responsibilities retained; detail deferred | Chapter 14 can add a bounded sound-board sidebar, using hardware sources for chip-level behavior. |
| "The wire": exact ports, interrupt veneer, direct-reply destination, unsolicited response queue | Two-latch exchange retained; details deferred | Chapter 14 can diagram one command/reply transaction. |
| "Eight slots and one frame": retry arithmetic, exact attempt budget and ring indices | Queue capacity and busy behavior retained; arithmetic deferred | Chapter 14, if needed to explain audible delays or lost requests. |
| "Watching for a corpse": status timers, thresholds, acknowledgment and reset holdoff | Recovery mechanism retained; exact state machine deferred | Chapter 14. The assertion that a dead sound board leaves the game perfectly playable was removed because coins also depend on the board. |
| "The coins come back down the same wire": complete interrupt/service chain | Shortened | Chapters 8 and 14 can share a single illustrated quarter-to-credit trace. |
| "The vocabulary": full command examples, position-indexed effects, start/stop pairs | Selected examples retained; catalog omitted | Compare one looping effect with one spoken phrase in Chapter 14. Keep the full command inventory in its maintained CSV. |
| "What the technician hears": chip timeouts, RAM/ROM/IRQ faults, manual test menu | Moved / deferred | Chapter 16 owns the diagnostic tour; Chapter 14 retains the status reply's purpose. |
| Sound-channel priorities, treasure-music replacement/suppression, partial admission, fade ownership | Deferred useful behavior | A Chapter 14 sidebar could explain actual sound-board channel sharing. Chapter 17 already explains why mixed WAV files cannot fully reproduce partial suppression. |
| Host WAV layout, opt-in playback, accepted-byte stream, loops/fades, uncapped muting | Moved / shortened | Chapter 17 is the current-use guide. An advanced audio example can expand it without reproducing the whole audio module. |
| Catalog guesses, changed IDs, address-search and recovery-variable history | Removed maintenance | Supported meanings remain in the narrative. Chapter 18 can explain a method without becoming a chronological repair log. |

### Former 17_methodology.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "An evidence ladder": ranking different forms of evidence | Reworked | Chapter 18 explains what each source can establish. A reconstruction does not outrank an observed original-ROM operation. |
| Synthetic fixtures, immutable snapshots, scenario hashes/timers and event schemas | Practical use moved; deep representation deferred | Chapter 17 for usage; Chapter 18 for the distinction between synthetic and original evidence. Full schemas stay in developer docs. |
| ROM-to-Python crosswalk totals and deliberate omission totals | Removed from narrative | Keep changing inventory numbers in maintained audits. |
| "Proving a negative": RNG literal-address scan and missed short-call encoding | Claims narrowed; discovery story removed | Chapter 18 explicitly includes indirect, indexed, bulk-clear, and alias limitations. A future instruction example can compare encodings without telling the correction history. |
| "Keeping an AI-assisted pass honest": project history and accountability | Retained in proportion | Chapter 18; command-by-command generator tours and coverage tables were removed. |
| Contradicted-claim history, issue closure, assertions of complete runtime understanding | Removed | These are not material to reinsert as evidence of correctness. |
| "Fingerprints": stack frames, register classes, assembly exceptions, Green Hills inference | Deferred | Chapter 18 can show one compiler-shaped routine and one hand-written fragment. Specific vendor attribution needs its historical qualifications. |
| "Nine bytes that never run": Morse bytes, continuous bit segmentation/padding, chip interleave, affidavit | Deferred useful archaeology | A Chapter 18 sidebar is explicitly planned. Separate the decoded pattern from an inferred purpose for these particular bytes. |
| "A whole game asleep in the OS ROM": retained module, stale targets, earlier strings, shared part numbers | Deferred useful archaeology | Chapter 18, grounded in OS reference sections 10.5 and 12.4-12.8 and MAME definitions. A retained support module is not automatically an entire complete game. |
| "Where evidence stops": open-bus behavior, arbitrary fills, unused regions | General limits retained; examples deferred | Chapter 18 can add one hardware limit without claiming all other unknowns are closed. |
| "Where to go next": dense audit links and future publication promises | Shortened | Stable links remain in chapter notes and the appendix. |

Historical references worth preserving for those future sidebars:

- Ed Logg's [2012 Gauntlet postmortem slides](https://media.gdcvault.com/gdc2012/slides/Design%20Track/Logg_Ed_Gauntlet_Postmortem.pdf),
  especially the programming-environment slide and its qualification that
  the Green Hills post compiler came later. It discusses the original
  Gauntlet; sequel claims need their own support.
- [Logg's Centipede affidavit](https://arcadeblogger.com/wp-content/uploads/2019/06/ed-logg.pdf)
  and the [context article](https://arcadeblogger.com/2019/06/29/atari-centipedes-hidden-code-trap/).
  These establish historical use of Morse signatures, not an undocumented
  purpose for every similar pattern.
- MAME's `src/mame/atari/gauntlet.cpp` for board and ROM definitions.

### Former appendix and scattered companion details

| Old material | Fate | Restoration decision |
|--------------|------|----------------------|
| Glossary as a second creature/item catalog | Reduced | Keep definitions needed to read mechanisms; develop the creature or item in its chapter. |
| Audit terminology, counts, correction history, Morse and retained-module glossary entries | Removed / moved | Chapter 18 for methods and possible archaeology. |
| Long repository/source essay and issue-led navigation | Replaced | The appendix now maps reader questions to stable references. |
| Publication checklist | Removed from reading path | Editorial expectations live in OUTLINE; do not restore printed learning-objective boilerplate. |
| Old Chapters 6/14: nested benchmark boundaries | Replaced with current interface | Chapter 17 distinguishes input, game update, raster-through-blit, display flip, and cumulative host iteration. Do not restore obsolete measurement descriptions. |
| Render rolling-window length, graph-axis details, PAUSED placement, complete stress/workload catalog | Deferred companion detail | Chapter 17 can grow by adding a focused exercise. The current README is the full operational reference. |

## Mazes, special encounters, and scoring

### Former 09_mazes_and_slapstic.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "Levels are not mazes": complete record-range table | Condensed | Chapter 9 accounts for all 117 records in prose. Restore a compact visual key if it helps distinguish ordinary, treasure, and secret uses. |
| "Choosing the next maze": full candidate validation, resume substitution, wrap ordering | Deferred | Chapter 9 needs two complete sessions beside the algorithm. A wrap crossing does not itself guarantee a stride change; the final landing matters. |
| Level 999 returning to level 6; long trace from a fresh game configuration through level 119 | Deferred | Chapter 9. Preserve dependence on actual persistent game state rather than offer a permanent level-to-maze formula. |
| Rotation save scheduling and treasure detour restoration | Shortened | Chapter 9 retains the saved ordinary-maze distinction. Chapter 16 owns when writes become durable. |
| Treasure-room stride and separate persistent rotation | Condensed / deferred | Chapter 13 can give this its own small selector example. |
| Slapstic helper addresses, access ritual, boot verifier | Condensed / deferred | Chapter 9 explains the bank window. A real access-sequence inset could support the full chapter; verification at boot belongs in Chapter 16. |
| "Anatomy": byte-by-byte header and every flag | Deferred | Chapter 9 after the worked record. Keep the exhaustive layout in the reference. |
| "The decoder": every opcode class and the longer first-row trace | Deferred | The new draft retains three actual bytes. Expand that example through a row and an upward-written span. |
| Maze 116 ending without a delimiter and overlapping the bank table | Deferred useful storage detail | Chapter 9 as a boundary example, or Chapter 18 as a small investigation. This is shipped behavior, not merely a correction story. |
| "From tokens": all object materialization, anchors, start removal, wall-neighbor scans | Distributed / deferred | Chapter 6 for representation, Chapter 3 for placement, Chapter 9 for one complete setup sequence. |
| "Three kinds of random": flags, depth tiers, trap setup, pickup placement/removal order | Condensed / deferred | Chapters 9 and 10. Preserve deterministic selection versus randomized setup. |
| RNG equation and exact cross-system draw ordering | Deferred | Chapters 7 or 9 can show one coupling example. Chapter 15 handles repeatability; Chapter 17 handles host seed choices. |
| Level notices, speech priority, reduced-text tips | Moved / deferred | Chapter 14 for spoken information and Chapter 5 for display ownership. |

### Former 12_dragon_thief_mugger.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| Combined creature framing and claims about what the designers were willing to express | Replaced | Separate thief and dragon questions now carry Chapters 11 and 12. Intent claims need evidence. |
| "The dragon is four sprites": complete private-state and slot inventory | Condensed | Chapter 12 retains the four-piece encounter. Restore one geometry diagram, with representation details linked to Chapter 6. |
| Exact wrapped proximity bounds and every signed transition | Deferred | Chapter 12 keeps event-triggered waking, the 49-frame transition, and potion/shot effects. |
| "Five programs": full path table, other rhythms, exact pose/open-mouth indices | Condensed / deferred | Restore the path strip with distinct pose and open/closed artwork lookups. |
| Projectile origin/owner encoding, slot numbers, exact large/small size words | Deferred | Chapter 12 keeps shared channels and relative flame size. A firing diagram can introduce the native fields if useful. |
| "Nine hits": doubled collision tags and exact palette arithmetic | Deferred | One accepted-hit trace in Chapter 12 or an instruction example in Chapter 18. Remove all "dropping this breaks the port" framing. |
| Nine-hit palette bands and reward offsets | Condensed / deferred | Chapter 12 can add a damage-progress strip and prize-placement diagram. Duplicate reward paragraphs were removed. |
| Dragon contribution to a secret objective | Deferred | Chapter 13 must explain the actual masked progress-byte predicate. Do not restore the simplified claim that a clean killer necessarily qualifies. |
| Thief target and delay tables, scaling, clamps | Condensed / deferred | Chapter 11 retains valuation and separate delay measures. The delay's score is shifted by 13 before division; restore a sourced numerical example rather than the old unscaled formula. |
| Hidden-alpha route storage, nibble packing, reset owner, transporter tables | Core route retained; storage detail deferred | Chapter 11 should overlay pursuit and escape arrows; Chapter 6 can explain hidden-memory reuse. |
| Thief body probes, centering nudges, seam movement | Deferred | Chapter 11 only as needed for one corridor example; general collision belongs in Chapters 3 and 6. |
| Stuck-visitor captures, missing trail setup, stale state, exact repair coordinates | Removed maintenance | Correct routing and movement are presented without port postmortems. |
| Theft category weights, multiplier-loot encoding | Condensed / deferred | Chapter 11 can compare stealing an upgrade, potions, and the multiplier. Only multiplier theft resets the multiplier. |
| Pitched laughter, transport effects, kill cleanup, next-level placement stride | Recovery retained; detail distributed | Chapter 14 for voice, Chapter 11 for a returned-loot example, Chapter 9 for placement if necessary. |
| Mugger speed constants, palette/art banks, warning IDs | Condensed / deferred | Chapter 11 retains slower movement and 100-health theft. Restore a measured speed comparison rather than an unsupported "faster thief" characterization. |
| Successful-theft allowances versus deployment count | Retained explicitly | Killing a visitor before theft does not necessarily finish that variant's opportunities on the level. |

### Former 13_living_maze.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| Overall logical-type/rendering pipeline and demo illustration | Distributed | Chapter 10 keeps changing-route consequences. Chapters 5 and 6 explain picture and state. The existing door/forcefield image remains available. |
| "Doors": classes, endpoint masks, eight animation channels, neighboring restamps | Condensed / deferred | Chapter 10 should trace one connected opening shared by two players. |
| Key-sensitive idle thresholds, one-shot disabling and rearming | Deferred | Chapter 10 keeps the conditional door timer distinct from the 21,000-frame no-progress escape timer. |
| "Transporters": every rejection rule, animation stage, pad palette | Condensed / deferred | Chapter 10 needs one rejected and one usable destination. Chapter 11 owns thief link continuity; Chapter 5 owns palette effects. |
| "Forcefields": segment encoding, all phase durations, damage table, hurt flash and buzz timers | Condensed / deferred | Chapter 10 retains the live/dark damage distinction. Restore one class-dependent crossing-cost example. |
| Forcefield hub and palette-cache repair history | Removed | Segment discovery and live colors may return as mechanisms, not debugging stories. |
| "Walls": cyclic assignments, random scan, trap flags, invisible variants | Condensed / deferred | Chapter 10 should compare timed, random, and triggered changes with pictures. |
| Movable-wall 25-hit removal, crumble stages, strong-shot passage and reflection geometry | Deferred | Chapter 10 with a link back to Chapter 2's projectile lifecycle. |
| Secret-wall complete loot table and party-size odds | Condensed / deferred | Chapter 10 retains the possibility of a reward or Death. Expand with an actual risk comparison. |
| Maze-specific placement, palette mistakes and collision-engine lessons | Removed maintenance; real setup distinctions deferred | Chapters 6, 9, and 10 for the supported mechanisms. |
| "Exits": movement tables, animations, choose-one configuration | Condensed / deferred | Chapter 10 retains recorded exit positions rather than random-floor relocation, fake-art persistence, and no-progress conversion. |
| "Traps and special floors": stun, poison remap, acid slowdown/panel dim, offscreen gates | Deferred | Chapter 10 for hazards, Chapter 3 for control consequences, Chapter 5 for visual effects. |
| "Treasure rooms": full music/HUD setup, warning choices, false-countdown sequences | Condensed / deferred | Chapter 13 keeps the clock and joke; Chapters 14 and 5 can expand sound and display. |
| Treasure tally/curtain ordering and all payout fields | Selected worked example retained | Chapter 13 must keep successful exit separate from merely seeing a tally after timeout. |
| "Secret objective": all seventeen tasks, event hooks, hint aliases | Deferred | Chapter 13 should first trace one armed objective end to end, then offer a compact reference. |
| Misleading clue versus exact predicate, including masked "Don't Get Hit" state and harmless/reflected player shots | Deferred useful behavior | Chapter 13. These deserve careful explanation, not removal as inconvenient implementation details. |
| Availability counter values and success/miss adjustments | Condensed / deferred | Chapter 13 retains setup-time arming, solo cancellation, and changing opportunity intervals. |
| "Secret challenge": fourteen-code table, potion substitutions, timers, generated exits | Condensed / deferred | Chapter 13 keeps separate invitation/challenge tasks and exits created at setup. Restore one challenge construction sequence. |
| Secret-room scratch aliases and player-zero inventory consequences | Deferred useful RAM behavior | Chapter 6 for aliasing, with a carefully sourced consequence note in Chapter 13. Do not silently replace this with an idealized independent saved inventory. |
| Label padding, invitation timing, screenshot/renderer repair commentary | Presentation deferred; repair history removed | Chapter 5 for text layout; Chapter 13 for invitation pacing. |
| "Name entry": input repeat, timeouts, commits, buffer replacement, unusual glyphs | Deferred | Chapter 13 can give a usable name-entry example; Chapter 5 owns glyph mechanics. |
| Code's complete CRC construction and symbol interleave | Condensed / deferred | Chapter 13 retains name consistency, encoded state, and the objective's low-four-bit limitation. Expand with one actual decoded code. |
| "Checking the math": verifier commands, Python implementation, numerical example and emulated-ROM comparisons | Deferred | Chapter 18 for independent evidence; a small worked code can remain in Chapter 13. |
| Appended transport sparkle, EXIT TO 6 glyph, trap palette, and mirrored dragon geometry details | Relocated by subject | Chapters 5, 6, 9, and 12. These do not belong as an unrelated appendix to the secret-code explanation. |

### Former 14_score_and_economics.md

| Old section / information | Fate | Restoration decision |
|---------------------------|------|----------------------|
| "The quarter's journey": complete pricing multipliers, bonus units and helpers | Expanded; full configuration inventory deferred | Chapter 8 follows a one-unit/no-bonus transaction through the wrapped sound report, OS balance and deduction, selection/join, and live top-up. Pending bonus units remain distinct; every possible pricing combination is not enumerated. |
| "What things are worth": every award and four floating-score channels | Condensed / distributed | Chapter 8 for awards, Chapter 5 for popup capacity and presentation. |
| Multiplier described as exclusive to special bags; theft always resetting it | Removed inaccurate simplifications; examples expanded | Chapter 8 works three two-player ordinary pickups before their awards and a conditional multiplier theft. Chapter 11 owns pursuit and recovered loot. |
| Cross-class high-score comparison | Replaced | Chapter 8 compares two Warrior runs because the rankings are class-specific. |
| Spawn adjustment called a count cap or freshly recomputed value | Replaced / expanded | Chapter 8 works 196,608 party points on six coins adding two to the existing bonus, then a live coin reducing a positive value. Chapter 4 shows why a binding level cap can conceal that change. |
| "Info panel": column states, exact palettes, dirty-field cadence, pulse/IT effects and popup tables | Deferred / distributed | Chapter 5 for display, Chapter 8 for health/score meaning, Chapter 14 for spoken warnings. Host controls move to Chapter 17. |
| Advice masks, reduced-text records, speech gating | Deferred / moved | Chapters 7 and 14. Chapter 8 retains the continue offer without an entire dialog-system inventory. |
| "What the cabinet remembers": six-value save gate, check syndromes, byte-write retries | Deferred | Chapter 16 for storage mechanics; Chapter 8 for the information kept and its use. |
| "The operator": descriptor streams and histogram saturation/rescaling | Partly expanded | Chapter 8 works the shipped time-bin scale and a 180-second/three-coin session, distinguishes header parameters from live difficulty, and explains byte rescaling. It is an illustrative histogram calculation, not a new service-screen capture. Descriptor-driven menus remain in Chapter 16. |

## Review priorities for expansion

Chapters 3-8 now supply the four-player camera sequence, generator turns
and occupancy, a composed display pixel, one cell migrating through its
record and links, an ordered Fire/dialog/overload timeline, and worked
economic transactions. Their remaining table and diagram deferrals above
are review choices, not placeholders for unwritten chapters.

The highest-value next expansions are a real level being decoded in
Chapter 9, the thief's two route grids, the dragon's pose/fire timeline,
and a secret objective carried through a challenge and code. Exact tables
can support those examples once the examples have a reason to need them.

Mechanical inventories, port repair histories, and declarations of audit
completeness should not return merely because they occupied many pages in
the previous manuscript.
