# gauntpy — Known Issues

Issues discovered during implementation waves and the post-wave review. Each
entry notes which WP first encountered it, current status, and what to do about
it.

Status legend: **open** = needs action; **resolved** = fixed (kept for the
record).

All 28 main-loop calls and `one_time_init` are implemented. With the ROMs
present the suites are clean: **2559 passed, 1 skipped** (gauntpy) and
**700 passed** (gex). The six original blocked ROM tables have been transcribed
from `row76.bin`, the
disassembly-verifiable constants (player speed, exit timer, monster-speed
cadence, Death-contact damage) confirmed against radare2, and the
subsystem-isolation rule has been lifted (I-09/I-21/I-22 cross-imports wired).

WP-20 level-transition orchestration has landed: player exits drive the
next-level/maze computation and reload (I-12), players spawn into the maze from
their PLAYERSTART (I-08) and their record then migrates cell by cell as they
walk (S-63), firing works (N-02), and tile interaction is wired
into the player loop so pickups, doors, and exits all fire during gameplay.

The **front-end session flow** is now wired too: `start_attract_to_game`
(0x44204) leaves attract and loads level 1, so the `coincheck` →
`character_select_input_update` → `main_start_game` path takes a coin insert
through character select to a spawned hero — verified end-to-end through the
real frame loop (`test_level_transition.py::TestFrontEndFlow`). The playable
runner — `uv run gauntpy-play` — walks a hero around a real maze at 60 Hz,
advances level-to-level at an exit (N-05), and with `--attract` boots through
that whole front end live (coin key `5`, joystick to pick a class, Enter to
start).

---

## Open issues

### S-133 · non-ROM compatibility compensations remain

The callable audit records four non-ROM game-side compensations. DEMO can ignore
random walls, delete Grunts on its final input record, and retain a row-zero
flank in the public generic probe family, while score display compares host
latches because some producers omit dirty-bit writes. These remain open
root-cause work; a passing attract recording must not be mistaken for state
equivalence. S-137 removed the primary player mover's one-pixel integration and
reserved-row exception.

### S-126 · live-only downward block at level 17 / maze 16 `(396,176)`

The reported session blocks Down at player coordinate `(396,176)`, although no
visible object occupies the corridor below. This is not reproducible from a
fresh maze-16 state: with the camera snapped to the live player, gauntpy moves
to `(396,178)`, and direct ROM execution of `player_try_move` does the same.
The static maze records around slots `0x179`/`0x199` therefore do not explain
the report. A transient MOB record, stale camera origin, or another live RAM
field is required to distinguish the failing state.

F4 now captures that evidence without changing simulation memory. Reproduce
the block, press F4 once, and retain the printed JSON path under
`traces/state-dumps/`; the dump contains the complete player/MOB tables,
camera origins, maze state, path grids, all modeled video/color RAM, timers,
inputs, and RNG seed.

## Resolved issues

### S-171 · exhaustive game/sound-ROM command audit

All 97 gameplay sound/speech producers plus their three forwarding seams were
checked against `row76.bin`, direct disassembly, literal command tables, and the
companion sound-ROM command/channel catalogs. Every previously implemented
pickup, shot, monster, dragon, thief, door, wall, exit, countdown, dialog,
coin, attract, and control command uses the correct ID and index after S-170.
The audit found eight remaining lifecycle families rather than another isolated
wrong number.

Welcome and low-health sentences used ordinary `sound_play`, as did the spoken
suffix of the thief escape taunt. They now use `sound_speech_play`, honoring the
operator speech-disable bit while preserving the thief's ungated laugh.
Power-up grants now reproduce the ROM's name → `NOW HAS` (0x8D) → power-name
sequence; reduced text omits the first two phrases, speech-disable gates all
three, and the high-byte one-shot latch prevents a timed power from repeating
its announcement later in the same level.

Poisoned food/potions and player death now draw from the literal per-character
voice groups at 0x5791A through the 0x578DA/0x578EA pointer/count tables.
Player death plays that voice before transition effect 0x14-0x17. Real joins
restore character effect 0x09-0x0C, and an exhausted spawn search emits 0x43.
The level-start lifecycle restores slow-motion stop 0x39, mixer preset 0xD7,
ordinary level music 0x42, the secret-room theme at delay 0x14A, treasure music
0x3D-0x40 by active-player count, and the early/later speech tables and gates.

The host audit also replaced the one-off slow-motion rule with all 62 type-7
command chain records. Each active static recording now tracks its physical
channels and priorities: equal priority replaces an old member, higher priority
suppresses lower playback, and a lower sequence can resume when the winner
ends. For 0x37/0x38 the corrected sound-ROM fact is priority 8 versus 9 on YM
channel 8—not equal priority as S-170 originally stated. Mixed whole-command
WAVs cannot isolate stems when only part of a multi-channel sequence is
suppressed, but the host preserves the verified ownership and complete-command
audibility decisions. The allocator also models the 30 logical slots
record-by-record: on exhaustion it can reclaim only the requested physical
channel's lowest-priority member, and a rejected record abandons its chain
suffix. Fade commands leave their members in arbitration until the host ramp
ends, and explicit pygame channels 1-31 keep effects out of speech channel 0.

Fresh-session ordering was rechecked separately. `start_attract_to_game`
0x4425A-0x442AC emits 0x3C, 0x02, then reaches
`show_level_start_screen`'s 0xD7; transition-only 0x39/0x42 belong to
`main_start_game` 0x4812E-0x4814E and are not fabricated on that path.

### S-170 · potion/slow-motion audio and survivor greetings diverged

Three audible reports had separate causes. The ordinary good-potion arm in
`player_tile_interact` sent 0x0E, the red-player exit command. ROM
0x5176C-0x51786 increments the potion byte and sends 0x26, the shared
treasure/potion pickup sound, before refreshing inventory; the port now does
the same.

The slow-motion producer was already exact: `monsters_everything`
0x40EB0-0x40EDE decrements the timer, sends 0x38 with 30 frames left, and sends
0x39 at zero. The host-side mistake was treating every accepted type-7 WAV as
independent. Sound-ROM command 0x38 has priority 9 on the same physical YM
channel where loop 0x37 has priority 8, so it suppresses 0x37 immediately;
command 0x39 is the later explicit stop. Static playback performs that arbitration and
also replaces an older instance when the same looping command is restarted.

Ordinary level handoff also called `player_join_finalize` after placing each
survivor. The ROM's 0x4823C-0x4828A survivor loop never reaches that join
routine: it calls `player_start_inner`, restores status 1, redraws the panel,
and clears trick progress. Removing the false finalizer stops repeated join
sounds and `WELCOME <hero>` speech and preserves join-owned counters across
levels.

The host AUDIO diagnostics page now lists the latest twelve accepted commands
chronologically, one per line with both hexadecimal ID and description. Names
come from the local command-named WAV library plus explicit control-command
semantics, and remain immutable host snapshot data.

### S-169 · playable host emitted sound commands but played no audio

The game-side port already reproduced `sound_play` 0x4AD76, the busy-latch
fallback ring, the eight-attempt `main_update_sound` drain, recovery holdoff,
speech option, and every producer. Accepted bytes ended only in the persistent
`sound_log` oracle, so the pygame harness was silent.

The host now consumes newly accepted bytes and plays local command-named WAVs
without changing `GameState` or emulating the sound CPU. Ordinary effects can
overlap; Death, forcefield, and slow-motion recordings loop until the exact
type-5 stop mappings 0x21→0x20, 0x2F→0x2E, and 0x39→0x37. Commands 0x3C and
0x41 fade the theme and active treasure music. Speech follows the verified
TMS5220 admission contract: one current phrase, seven pending entries, lower
priority rejection, equal-priority append, and higher-priority pending-queue
flush without interrupting the current phrase. Global filter 0x01/0x02 and
mixer presets 0xD6-0xD9 affect host channels while the accepted command log
remains untouched. Loaded state dumps start at the end of their historical log
rather than replaying old audio.

The WAV library remains local and ignored as ROM-derived data. The runner uses
`gauntpy/sounds` by default, accepts `GAUNTPY_SOUND_DIR`, and reports when it
must continue without recordings.

### S-168 · playable host had no gamepad input adapter

The playable wrapper sampled only keyboard state even though pygame already
exposes connected controllers. `HostShell` now opens the first gamepad at
startup or hot-plug, maps its left stick and D-pad to the four verified
active-low direction bits, and maps buttons 0/1 to Fire/Magic. Buttons 6/7 are
edge-triggered coin/pause controls, matching the existing keyboard host actions.

This remains entirely on the host side. Keyboard and controller state are
composed into the same `player_input_raw` word, after which the existing
`input_debounce`, direction table, character-select, shooting, and potion paths
run unchanged. Regressions cover diagonal stick/D-pad composition, active-low
button polarity, and controller coin/pause edges without requiring physical
hardware.

### S-167 · thief deployment anchor and stunned potion behavior

Thief/mugger deployment placed the 3x3 actor at `cell_x * 16`, four pixels
right of the ROM. The `mob_create` argument at 0x4DF54-0x4DF64 is
`slot * 0x800 - 0x200 + palette`, which reduces to `cell_x * 16 - 4` in the
modeled H word. The transport destination path already used that correction.
Initial deployment now uses the same anchor, so the visitor follows one side of
its route cell through a two-cell corridor instead of appearing centered between
the two lanes.

Potion use while stunned was confirmed as original behavior. The main loop calls
`main_handle_potions` before `main_move_players`; ROM 0x46FEA checks only the
active MOB, Magic edge, maze gate, and potion count. It never reads
`player_stundelay`. A stunned player therefore cannot move but may drink a
potion, and the stun timer remains intact.

### S-166 · phantom player records, inventory caps, and thief boundary/effects

Frames 18687 and 43851 contained Python-only dynamic MOB remnants beside the
Elf. The former slot `0x0B1` held hero picture `0x1612` with every other word
zero; the latter slot `0x3E0` held the same picture and depth links but zero H/V,
object type, and state. Both violate `move_mob_slot` 0x5DE0A's five-word
transaction and were treated as occupied collision cells, producing the
invisible right block and the corrupt left obstacle. `main_move_players` now
removes this impossible modeled-MOB state before collision. Replaying both dumps
makes the requested move proceed without a renderer exception.

Frame 29864 exposed a separate thief seam bug. The thief at slot `0x3E0`,
`(508,492)`, needed the right-move flank response to nudge downward around wall
`0x3C1`. Python's generic `mob_probe_down` returned the boundary sentinel for
every row-31 record. ROM 0x40732 instead reads the proposed live V word and
returns clear while it remains nonnegative. The paired top probe likewise uses
its literal V comparison. Restoring both tests lets the thief reach Y=496, wrap,
and continue right into slot `0x3E1`.

ROM 0x4DF7E also calls `tport_cycle_start` when a thief/mugger deploys, and the
successful escape arm at 0x4EC10 does the same before clearing the visitor.
Those two missing game-side effect writes now produce the intended appearance
and disappearance poofs. Ordinary key and potion collection now enforces the
ROM's combined 12-item capacity at 0x51458/0x516E4, so the overfull frame-27506
player cannot increase either counter.

The F1 LEVEL labels were clarified rather than changing gameplay:
`MAZE SOURCE: CABINET ROTATION` says that levels above five select layouts from
the EEPROM-persisted cabinet rotation, while `TREASURE >30` describes only the
post-level-30 treasure-room prank voice gate. Thus level 111 / maze 29 correctly
shows `OFF (NOT TREASURE)`. The contest name editor also matches the ROM: its
0x0A8D-frame timeout is deliberately invisible, Fire or Magic commits each
character, reaching 29 characters finishes immediately, and timeout fills the
rest with spaces. The original screen supplies no explicit control legend or
countdown.

### S-165 · tagged wall impacts, incremental playfield cache, and diagnostics clarity

The frame-53450 level-112/maze-32 capture places the Elf at `(92,496)`. A
down-left shot reaches `(87,505)` and reports tagged playfield target `0x405`.
Gauntpy stripped the `0x400` tag before calling `shot_impact_spawn`, so the
effect copied H/V from fixed MOB slot 5, whose stale coordinates were
`(496,83)`. ROM 0x47E6A-0x47F80 keeps the tag: for any playfield target it
normalizes the depth key but copies position from shooter MOB `shooter+1`.
The game-side effect writer now preserves that identity and produces the
sparkle at `(87,505)` with depth key `0x025`. The same port now includes the
ROM's ordinary-target H correction and low-slot depth-key reconstruction.

The regular 30 ms render spikes in the frame-14495 capture were host cache
rebuilds, not scrolling or game timing. Living maze updates changed only a few
of the 4096 authoritative descriptor words, but any generation change decoded
the complete 512x512 indexed playfield again. The cache now retains a descriptor
signature and restamps only changed 8x8 words before recoloring through live
color RAM. A 300-frame replay of the capture went from 63 frames above 30 ms
(43.2 ms maximum) to none above 20 ms (16.5 ms maximum) on the same host.

F1 now has a separate FLAGS page showing the four raw bytes and their decoded
odd-angle/mirror/invisibility, speed, food/wall/exit, shot/trap/wrap/fake-exit
settings. LEVEL remains focused on timers and depth gates. The ROUTES page moves
its marker key below the text rows, so its boxes no longer overwrite
`DIRECTIONS`.

### S-164 · exhaustive LFLAG audit restored level-splash consumers

Every bit in the four-byte level-flags longword was traced from its ROM readers
to setup, simulation, modeled video RAM, and presentation. The gameplay paths
were complete after S-163: odd-angle and fast families; the two mirror bits;
trap/all-wall invisibility and one-hit invisible destructible walls; random
food; cyclic and one-/two-group setup walls; moving/choose-one/fake exits;
friendly-fire stun/damage; local/random traps; both wrap axes; and the
player-offscreen gates. Regressions now exercise every family selector, all
eight random-food field values, both deletable-wall forms, TrapsLocal culling,
both invisibility modes and the level-9999 override, wrap direction on both
axes, and friendly-fire priority.

One real omission remained. `level_splash` 0x4BE24–0x4C1B2 reads six LFLAG
conditions but gauntpy's merged start-screen implementation wrote only the
large level field and secret hint. It now writes the exact alpha records for
ShotStun, ShotHurt, PlayerOffscreen, InvisibleAllWalls,
InvisibleTrapWalls, and ExitMoves, plus the adjacent hidden-potion notice.
Their shared one-speech latch and one-in-four draws follow ROM order, so these
presentation branches also restore the correct global RNG stream. The same
routine now writes level 1's fixed `FIND EXIT TO NEXT LEVEL` line and the
ordinary `getrandom(9)` two-line gameplay tip, with the original bonus-room and
reduced-text gates. Literal strings live in `romtext.py`; rendering remains a
pure alpha-RAM consumer.

### S-163 · thief combat, seam monster scheduling, and maze-26 setup

The frame-2676 capture had the thief at slot `0x319` pursuing through a Demon
at `0x31A`. ROM `thief_handle_tile_collision` 0x4F89A–0x4F8D6 treats every
object type 18–45 as a fight: first contact stores `direction+1` and clears the
shared counter; the normal collision-animation arm increments it each frame;
after it passes 15 the routine spawns an impact, removes the blocking MOB, and
clears the latch. Gauntpy classified the monster as non-solid but neither
advanced the counter nor removed it, so the thief stayed in place forever.
The complete fight transaction and animation-counter increments are restored.

In the frame-21664 capture the camera crossed the vertical seam at
`scroll_y=492`. The unsigned culling rectangle correctly included the visible
row-1 monsters, but the separate SLIP-chain endpoint helper clamped its
`scroll+280` lookup to band 63. ROM `main_move_monsters`
0x49076–0x490CA masks both endpoints with `0x1F0` and indexes the biased table
at 0x905F82, making the walk wrap from the bottom of the depth chain through
row zero. Gauntpy now performs that exact masked lookup; the reported monsters
above and lower-right of the player resume movement and animation.

Maze 26 also had a genuine setup omission. Its LFLAG3 byte is `0x92`, including
`WallsDeletable1`. At 0x43BA0–0x43BCC the ROM draws one of the three trap
groups and calls `maze_place_object_types`; the companion bit-5 arm removes
the selected group plus its next cyclic neighbor. Gauntpy never ran either
arm, leaving all nine type-7/8/9 walls and closing the intended route to the
chosen exit. Level setup now removes the selected wall/trigger records through
the shared game-side helper and updates logical maze and playfield RAM. With
seed zero, maze 26 removes all three type-7 walls, retains the other six, and
the selected exit at slot `0x1A0` is reachable from the saved start at `0x230`.

### S-162 · RAM-alias audit found secret-room stash divergence

The exhaustive modeled-RAM overlap audit classified eight live groups. Six were
already faithful representation/lifetime views: OS/game reuse at 0x904006 and
0x904012–0x904015; popup timer 3 over reserved `mob_depth_key[0]`; effect
counters over unused row-zero depth keys 30/31; and the biased
`priority_bucket_heads_tail` view. Transporter-route cells and portrait padding
are spatially disjoint in every reachable index. S-160/S-162 complete the two
simultaneous aliases that required coupled writes.

The additional behavioral miss was secret inventory. Direct M68000 execution
of ROM 0x482D0–0x48334 confirms that entry writes winner keys to
`monster_spawn_probability_bonus` (0x90405F), winner potions to player 0's key
byte (0x90405A), and supershots to 0x905F6D, then clears the winner's indexed
inventory. The immediately following 0x48B58 call adds score-per-coin pressure
to the saved-key byte. Payout 0x4D86E–0x4D8A0 reads those same aliases in
instruction order. For winner zero, clearing their keys destroys the potion
stash; payout first restores keys, then reads that newly updated key byte as the
potion addend. For other winners, player 0's key byte holds their potion stash.

Gauntpy's dedicated stash fields had hidden all of those effects. Gameplay now
uses the canonical aliased fields, so secret-room generator pressure and return
inventory match the ROM. Tests cover winner zero, a nonzero winner, and mutation
of the saved-key byte by the post-spawn bonus update.

### S-161 · thief routing state had no live visualization

The F1 panel now includes a host-only ROUTES page. It captures the complete
route-grid byte view in the immutable post-frame snapshot and draws side-by-side
32x32 maps for the low pursuit and high escape nibbles. Eight colors identify
the compass directions; outlined cells mark the current, next, scheduled-start,
and victim positions. The page never reads mutable state during rendering and
does not write alpha RAM or the route grid.

### S-160 · thief route grid survived the alpha-RAM level clear

The two supplied stalls shared a deeper cause. In both captures the visitor was
escaping at cell `0x38D`; its high route nibble explicitly pointed east through
fixed maze-3 wall `0x38E`. Following the complete high-nibble chain showed that
this was not a newly computed route ending at an unset cell: it was an old
reverse path extending through `0x38E` to `0x3FF`.

The ROM cannot carry that path across a level. `ram.path_direction_grid` begins
at byte address 0x905054, exactly hidden alpha column 42. Its 24 rows each use
the 44 bytes in hidden columns 42-63. `maze_show` 0x4526A and `maze_hide`
0x4529A clear all 22 hidden words on every alpha row, implicitly erasing both
route nibbles. Gauntpy modeled `alpha_ram` and `path_direction_grid` separately
but applied the clear only to the former. The first visitor wrote routes over
whatever stale high nibbles happened to be empty; later escape consumed an old
eastward chain that was geometrically impossible in maze 3 and stopped at its
real wall.

Both display routines now apply the one physical-memory write to the modeled
route-grid view too, and `maze_hide` also performs its previously omitted
non-panel alpha clear. A regression plants the captured `0x38D -> 0x38E`
escape direction and proves the level handoff removes it.

### S-159 · F1 level page did not expose active depth gates

The LEVEL diagnostics page now derives a host-only summary from the immutable
snapshot: fixed/rotation maze selection, level-3 special pickups, level-6
hidden-potion/thief scheduling and current thief odds, post-6 adaptive-food and
bonus-room eligibility, level-12 dragon/trick-9 activation, post-30 treasure
countdown pranks, the generator cap, forcefield profile, and the current
modulo-400/modulo-160 hazard tier. Maze-specific exclusions are shown rather
than presenting every threshold as active in secret or non-treasure layouts.

### S-158 · contest-code hyphen rendered as a zero

The reported screenshot literally displayed `W1YOGNO`: its fourth apparent
`O` was the zero-shaped glyph produced when gauntpy sent `'-'` through the
generic OS large-font ASCII map. That table maps hyphen to index zero, the same
quad used by digit zero.

ROM `name_entry_draw_large_char` 0x4A44A has dedicated arms before the generic
mapping call. Hyphen writes the raw alpha-glyph quad
`0x7C/0xFE/0xFC/0x7E`; backspace similarly writes
`0x1C/0x1E/0xFC/0x7E`. The secret-code and initials writers now use this
game-specific routine, while ordinary OS large text retains its literal map.
Thus the underlying `W1Y-GN0` buffer is now displayed with the required dash;
the final zero still looks like an O in the arcade font.

### S-157 · verifier incorrectly required separately supplied game state

The first verifier reproduced code generation but asked for maze, trick, and
challenge as inputs. The contest form did not need those fields. ROM
`secret_code_build` 0x54C14–0x54C96 interleaves three name-CRC symbols at
positions 0/2/5 with three directly encoded state symbols at 1/4/6 and writes a
literal dash at position 3. Atari could recompute the name symbols and decode
the state symbols from the submitted `XXX-XXX` code itself.

The verifier and batch wrapper now accept only name and code, report whether
the name symbols match, and decode the previous maze, trick nibble, and
challenge. The generated buffer always has `-` at position 3 and never contains
letter O; S-158 records why the gauntpy screenshot nevertheless showed an
O-shaped glyph there.

### S-156 · direct level/maze selection and secret-code result teardown

`gauntpy-play --level N` treated every depth above five as though it selected
maze `N-1`. The ROM has no such mapping: levels 1-5 alone select mazes 0-4;
level 6 enters the EEPROM-backed rotation and later levels advance that
rotation. Direct play now follows the same rotation. The new independent
`--maze 0..116` pins a stored layout without changing level-gated behavior, and
the options may be combined for exact reproductions.

At frames 13028 and 15637 the mugger/thief occupied maze-3 cell `0x38D`,
targeted `0x38E`, and found its live type-2 `0x8000` wall marker.
`thief_move_engine` 0x4EE7A correctly restored the blocked axis. S-160
supersedes the original frozen-state conclusion: the selected route nibble was
not unset, but an impossible stale eastward escape route left behind because
the modeled hidden-alpha clear did not also clear its route-grid alias.

The reported lower-wall shadow gaps likewise are not missing modeled VRAM. In
the supplied state the horizontal run is continuous descriptor `0x723A`; the
visible notches are pixels authored into that ROM tile, with `0x724B` at real
junctions. No renderer mask was added.

The secret result page did contain a real omission. ROM 0x5528A-0x552DA first
clears all 29 editor cells before drawing `REMEMBER YOUR SECRET CODE`; gauntpy
layered the result over the entered name, producing the screenshot's surviving
`ALINSA` fragment. The game-side writer now clears that alpha-RAM row first.
The initial joystick pause is original: `secret_getname` loads
`name_entry_repeat_delay` with 0xA0, after which held input accelerates to one
step every 8-13 frames. A runnable `python -m gauntpy.secret_code_verifier`
checks an entered name/code and decodes the saved maze, trick, and challenge.

### S-155 · documentation/Python naming contract had drifted

A whole-codebase comparison now applies the approved semantic naming policy to
35 one-to-one `GameState` rows: 25 explicit policy names and ten prior
alignments retained. The same pass checks 36 direct Python routine rows and the
40 prior literal-table changes. Source, tests, `doc/`, the book, loader symbols,
generated contracts, and both naming audits now agree.

The two disputed routines were re-audited rather than inherited from prose.
`door_open_start` 0x51E80 is called after key-gated door interactions, builds
the two front records, and always calls `main_open_doors` at 0x51F9E.
`demo_message_show` 0x4C9A2 is called for a 0xFF demo record, draws one to three
lines through OS `draw_string`, and sets the dialog timer; its body contains no
sound or speech call. `secret_check_winner` remains the direct name for
0x4D1A4's objective predicate.

Persisted names are intentionally not compatible. The schema-1 renamed-field
migration and EEPROM renamed-rotation-key lookup have been removed; malformed
or stale shapes follow the existing rejection/default paths. The scripted-run
golden contains no affected field keys.

The audit deliberately retained representation names where there is no
one-to-one object: `MobTable` methods encapsulate several ROM leaves;
player-record fields omit a redundant `player_` prefix; `player_in_maze` is a
polarity-normalized view of `player_tport_phase`; Python lists replace the
sound-ring head/tail words; and merged/decomposed renderer, maze, probe, palette,
and dispatch helpers remain explicitly classified in `ROM_FUNCTION_AUDIT.csv`.
The complete human-readable rename and exception report is
[`NAMING_AUDIT.md`](NAMING_AUDIT.md).
Regressions join the crosswalk to `doc/07`, bind direct Python ports to their
selected symbol/module, bind modeled RAM fields and literal tables to `doc/05`,
reject stale persisted names, and scan all tracked audit surfaces for stale
policy identifiers. The exhaustive totals remain 322 callable rows: 272
complete equivalents, 50 intentional platform/ABI/representation omissions,
and no partial or missing gameplay rows.

### S-154 · complete level/maze setup audit closed four residual gaps

The complete `maze_new_level_setup` body (0x438AE–0x43D8A) and every Python
entry path were audited after the secret-exit and PLAYERSTART fixes. Four net
state differences remained.

LFLAG4 `TrapsRandom` drew no setup value, so type-10/11/12 trap identities never
rotated together as 0x439B0–0x43A8E requires. The 0x43AF0–0x43B5A authored-food
pass was absent, so levels above six never changed one non-secret-maze food to
adaptive picture 0x277B. Random-wall low/current/target fields were initialized
lazily on the first gameplay call rather than during the setup scan. Finally,
the secondary word at 0x90487E was not modeled: level setup could not clear its
bit 0, and an already-seen fake exit could not play repeat taunt 0xA6 once per
level.

All four now run in ROM order after playfield texture generation. Trap markers
and logical types rotate by one shared draw; one uniformly selected type-49/50
food becomes type 49/picture 0x277B; random-wall cursors are ready before play;
and `dialog_once_flags` is reset at level, game, and demo setup and consumed by
the fake-exit dialog path. Schema-1 state dumps default the newly modeled word
to zero. Restoring the authored-food draw also advances the shared RNG before
choose-one/fake-exit selection, correcting the deterministic level-16 outcomes.

The audit also corrected the secret-exit order from S-152: the ordinary
position-table scan precedes challenge generation, so generated secret exits
are live markers but do not enter that table. The caller-side duplicate scan
was removed. Apparent low-slot and transporter-array omissions were
representation differences with equivalent reachable state: transitions
install a fresh `MobTable`, and transporter consumers derive the same ordered
packed slots from live records.

### S-153 · treasure rooms retained solid PLAYERSTART records

Treasure layouts store one to five candidate PLAYERSTART cells. Gauntpy's
`select_player_start_slot` chose one, saved it, and cleared only that record,
leaving every loser as a visible `0x1E0D` MOB and an impassable type-15
collision target.

ROM `maze_scan_objects(-1)` 0x43D8C–0x43EC4 shares its post-selection loser
arm with exit scanning. The chosen start is saved to 0x9049E0 and replaced with
floor; each non-selected start is marked with hpos bit 4 only when LFLAG4 bit 6
is set, and otherwise is also replaced with floor. Treasure rooms do not set
that flag, so none of their stored start records remains live.

The setup helper now processes every candidate and updates both the MOB table
and logical maze before playfield initialization. A ROM-backed regression loads
all eleven treasure rooms and verifies that the saved spawn identity remains
while no PLAYERSTART survives in collision or logical maze state.

### S-152 · secret challenge mazes loaded without generated exits

Mazes 115 and 116 correctly decode with no stored `EXIT`, but gauntpy stopped
after loading that compressed data. The missing `maze_new_level_setup` arm at
0x43C20–0x43D10 indexes the literal 14-word table at 0x57056 by challenge code,
turns each matching type-0x28–0x2D generator into an exit, clears the other
generators in that range, and replaces ordinary types 0x13–0x18 with hidden
potions whose power picture derives from the former monster type.

That game-side setup now runs after playfield initialization and after the
exit-position scan. Every challenge code 0x50–0x5D produces at least one real
logical/MOB/playfield exit in its assigned secret maze, and the round-trip
regression now consumes one of those generated exits instead of calling
`player_exit_sequence` against the player's own slot.

The reported winner-name spacing is not another divergence. A direct MAME
0.289 capture made by calling `show_level_start_screen` 0x44DB4 with a red Elf
matches gauntpy: the ROM deliberately draws padded color and class records as
separate large-text fields at columns 0 and 13.

### S-151 · secret invitation stripped padded large winner labels

The invitation rendered `RED` as small text at alpha column 0, visibly pinning
it to the left edge while `ELF` appeared separately near the center. ROM
0x44FB8 and 0x44FE4 follow fixed-width string pointers and both call OS
large-text API 0x26C. The records are significantly padded: `" RED  "`,
`" BLUE "`, `"YELLOW"`, `"GREEN "` and `"WARRIOR "`, `"VALKYRIE"`,
`" WIZARD "`, `"  ELF   "`. Because the large space quad advances two cells,
those bytes are positioning data rather than cosmetic whitespace.

The game-side invitation writer now sends the literal padded records through
the modeled large-font writer at the ROM's columns 0 and 13. A regression
checks the first visible RED/ELF glyphs at columns 2 and 17 and verifies the
second glyph row, so a small-font or stripped-string reversion fails.

F8 now pauses and resumes only the current treasure/secret-room countdown. The
flag lives on the host, and `tick` gates only `main_treasure_timer`; player and
monster movement, combat, input, and the other main-loop calls continue. The
toggle is accepted only while a bonus-room timer exists and clears
automatically when that room ends.

### S-150 · F1 secret hints hid distinct objectives

The F1 LEVEL page initially reused the cabinet's deliberately vague hint
strings. That made tricks 1–4, 5–6, and 12/14 indistinguishable even though
their ROM consumers are different. It also exposed a stale prose label:
0x50C30–0x50C52 compares trick 1's transporter landing against object type
0x19 (Acid), not a Demon, while trick 4 is the separate corner-transport path
through a secret wall at 0x507B8.

The host page now gives an objective-specific instruction for all seventeen
maze-header IDs, including two food versus two secret-wall shots and separate
no-keys-or-potions, no-food, and no-treasure variants. The data reference,
subsystem reference, maze chapter, and fidelity rules now preserve the
many-to-one hint distinction.

The complete mapping review also rejected two tempting paraphrases. Trick 9
does not test for a hitless dragon kill: 0x52BF0 masks the progress byte with 3,
dragon fire increments it, and dragon death writes 2 unless it is already 1.
F1 therefore reports the literal low-two-bits predicate. Trick 17 is failed by
player-shot contact at 0x4B046 before damage/stun eligibility or the later
shooter/victim comparison, so F1 explicitly forbids every player hit, including
a reflected self-hit.

The adjacent challenge-room audit found no missing completion gate.
`secret_check_winner` 0x4D1A4 implements every 0x50–0x5D predicate, including
the exact counts, five-transporter bitmask, empty-monster scan, and five tasks
with no extra qualifier. The payout additionally requires the winning player
to have reached exit status 2/8; only a completed challenge awards 5,000 points
per coin and reaches `secret_getname`, whose contest-code editor remains gated
by game-settings bit 13.

### S-149 · secret-room testing required waiting through the pacing interval

The live objective is not derived continuously from
`secret_possible_counter`. ROM `maze_new_level_setup` 0x43930–0x43958 samples
that counter once and copies the current maze-header trick into
`secret_trick_id`; changing only the counter after the maze has loaded leaves the
current level unarmed. At the other end, `player_exit_sequence` 0x52B40 checks
the live task and writes `secret_player` before status 8, while
`show_level_start_screen` 0x44DD6–0x44E00 waits for that winner to reach status
2 before selecting secret maze 115/116.

F9 now opens the pacing gate, reruns that exact objective setup for the current
ordinary maze, and applies the normal solo-party cancellation, so entry still
requires performing its real trick and then exiting. From level 6 onward, F10
clears the ordinary task so later player exits cannot replace its selected
`secret_player`, then relies on the same exit animation and transition pipeline
for unconditional entry. Both reject bonus rooms and non-play states. The F1
LEVEL page names the current ordinary maze-header objective even while it is
unarmed, and explicitly suppresses bonus-room or stale tally-transition header
bytes; the README lists both host-only controls.

### S-148 · complete 72-hour behavior documentation audit

All 40 current-branch commits from the preceding 72 hours were compared against
their diffs, issue entries, `FIDELITY.md`, technical references, and narrative
chapters. Movement/probe ownership, narrow-lane response, fake-exit VRAM,
treasure entry, dragon proximity/stun, potion paths, secret-room flow,
demo/legend timing, save-state behavior, stat selectors, and host diagnostics
were already covered or correctly confined to host documentation.

Five residual gaps were corrected. Chapter 9's old random-stocking summary now
matches `maze_addrandompickups`' post-party ordering, signed add/remove behavior,
deferred loot, and level-three special draws; it no longer misattributes
`getrandom(32)` generator spawning to ordinary monster movement. Chapter 10 now
records `player_hurt_speech_timer`'s party-sized reload, acid silence gate, and
per-character second draw. Chapter 13 and `doc/04` now state that movable-wall
destination checks share monster `ray_march_*` geometry. The SCORES color cycle
is corrected from eleven shifts to the ROM's twelve moves over one 16-word
palette, in both `doc/04` and Chapter 15. Chapter 14 now gives the exact host
render-timing boundary: game raster composition/conversion/scale/blit only,
excluding diagnostics, display flip, input/event work, and the limiter wait.

### S-147 · recent corrected behavior documentation audit

The S-142 ROM findings were already present at the appropriate levels:
`doc/04`, `doc/05`, `doc/07`, and Chapters 10/12/14/15 cover poison direction
remapping, the full 0x7000 edge window, thief/mugger wall response, deterministic
host seeding, and render timing/scale. The synthetic evidence boundary and
self-contained fixture provenance were likewise present in `doc/INDEX`,
`FIDELITY.md`, and Chapter 17.

The audit found one substantive omission behind S-146. The references said
that victim movement writes breadcrumbs, but did not state the scheduling
order that makes those writes possible: `thief_setup` chooses the victim and
saves its start/current cell before `thief_timer_set` loads the arrival delay,
so movement during the whole countdown extends the route; deployment uses the
saved old cell and reloads a 0x3C entrance pause. They also omitted
`thief_compute_path`'s unset-nibble behavior: it preserves the prior direction,
which is reset to upward, rather than finding another route. These details now
appear in `doc/04`, the RAM rows in `doc/05`, and Chapter 12.

The host-only S-143–S-145 details remain explicitly synthetic rather than being
mixed into ROM subsystem claims. `doc/INDEX` and Chapter 17 now summarize their
operational guarantees—live-input default, early event arming, F1 queue/timers,
and self-contained F4 provenance—while directing the full format contract to
`gauntpy/scenarios/README.md`.

### S-146 · synthetic mugger spawned with no pursuit breadcrumbs

The `activate_thief` event set an explicit spawn cell and invoked the normal
deployment routine, but normal gameplay schedules that cell at the victim's old
position and spends the arrival delay recording every subsequent victim move
into the low route-grid nibbles. The synthetic shortcut supplied none. At frame
1200 the mugger spawned at slot `0x03C`, `path_grid_get_direction` returned
unset, and `thief_compute_path` retained reset direction zero, targeting row-zero
slot `0x01C` and stopping against its wall.

Scenario construction now arms the victim and arrival countdown immediately,
matching normal scheduling ownership. It finds a cardinal traversable bridge
from the explicit live spawn cell to the player's initial cell and writes that
route through `path_grid_set_low_direction`; ordinary player movement during
the countdown then extends the same route through
`thief_track_victim_move`. The normal deployment, diagonal optimization,
movement probes, cell handoff, and reverse escape-route production remain the
game's implementations. An unreachable requested spawn fails explicitly rather
than creating another inert visitor. The example disables mirroring and places
the mugger at row 1, column 16 above a complete wall row whose sole opening is
column 16, with the player below it. After its 60-frame arrival pause the mugger
advances downward through that forced lane.

### S-145 · synthetic event queue was invisible during interactive play

The F1 panel now has a `SCENARIO` page. For a loaded `.gsc` fixture it captures
host-only immutable rows for the scenario name, source filename, content hash,
live/scripted input mode, and fired/total count. Every scripted event remains
listed: pending entries show their absolute 16-bit target frame and `T-` frames
remaining, fired entries retain their target and action, and an anomalous
unfired event already behind the current frame is labeled `MISSED`. Ordinary
ROM-backed play reports that no synthetic fixture is loaded. The page reads the
attached host runtime and does not add fields to or mutate modeled arcade RAM.

### S-144 · example synthetic maze suppressed all interactive input

The committed `narrow-lane-thief.gsc` declared `input = idle`. The synthetic
controller correctly treated that as a persistent script and rewrote player
one's sampled keyboard word to idle before every tick, making the displayed
maze appear completely non-interactive. The example now uses `input = live`,
and omitted `input` fields default to live host control. Explicit `idle` and
direction values remain available for deterministic scripted runs; the headless
runner is still idle naturally because a fresh `GameState` starts with no
buttons pressed.

### S-143 · declarative synthetic maze fixtures and readable graph scale

`gauntpy-scenario run PATH.gsc` and `gauntpy-play --scenario PATH.gsc` now load
a versioned declarative fixture: manifest fields for the ordinary level-flags
longword, seed, hero, health, maze graphics selectors, and default frame count;
an exact 32x32 one-character grid; optional symbol bindings to any object ID;
and allowlisted absolute-frame events. The initial event vocabulary changes
scripted input or deploys a thief/mugger from a named empty cell through the
normal game-side routine. It cannot execute arbitrary code.

Construction uses the existing maze placement, MOB creation, forcefield, door,
exit, playfield/color-RAM, player-spawn, and info-panel writers. Synthetic
provenance remains host metadata rather than a modeled RAM field. F4 embeds the
normalized complete `.gsc` content, SHA-256, source filename, persistent input,
and fired-event indices at the dump root; resume verifies the hash and restores
pending events without needing the source file.

These fixtures are explicitly non-evidence. They can minimize a reproduction
and motivate a ROM/MAME trace, but a result observed only in one cannot become
a fidelity invariant, technical-document fact, or book claim. The committed
format guide and methodology chapter carry that boundary.

The PERFORMANCE graph now also reserves a left axis and labels zero, midpoint,
and ceiling in milliseconds. Its ceiling rounds upward in ten-millisecond
steps, so both the values and the 16.67 ms budget line have a readable scale.

### S-142 · captured mugger/edge stalls, poison wobble, seed controls, and timing graph

Frame 3876 on level 16 / maze 15 captured a mugger at `(241,127)` trying to
enter slot `0x12F` between the wall flanks at `0x12E`/`0x130`. The shared
three-cell probe correctly returned the right flank, but gauntpy stopped there.
`thief_move_engine` 0x4F1C4-0x4F2C2 tests that high-bit collision, compares the
perpendicular distance, and moves H one pixel away from the flank before probing
again. The mugger now centers to X=240 and proceeds down the lane instead of
remaining in its compact blocked pose indefinitely.

Frame 51368 on level 20 / maze 19 captured the Elf at `(491,320)`, slot `0x29F`,
beside the non-wrapping right edge. Down correctly hit left wall flank `0x2BE`,
but the automatic response from S-139 tried to center at X=492 and was rejected
by gauntpy's port-only 208-pixel screen span. The ROM compares the MOB anchor,
not its full 24-pixel box, against literal H window 0x7000 (224 pixels). Restoring
that gate permits the response and the following Down input enters the opening.

Poison food/potions already loaded and decremented the 0x4B0-frame word at
0x905F48, but its only gameplay consumer was missing. In normal play,
0x4A8B8-0x4A8EA uses `(frame_counter & 0x30) + input_direction_nibble` to read
the literal 64-byte table at 0x4A4FA and replaces only the active-low direction
nibble. Holding Up therefore alternates Up+Right, Up, Up+Left, Up across the four
phases while Fire/Magic remain untouched; the timer's final decrement disables
the remap immediately.

The playable host again defaults to seed zero for reproducible runs.
`--seed 1234` chooses an explicit 16-bit stream and `--seed random` requests one
host-random power-on word; neither path reseeds later. The F1 diagnostics also
keeps 120 host-only render samples, reports a rolling ten-frame average, and
adds a PERFORMANCE graph with the 16.67 ms budget line. This supersedes S-141's
host-random default while preserving its finding that the ROM never initializes
the seed itself.

### S-141 · forcefield hurt flash, fresh-run RNG, and render timing

Forcefield contact subtracted the correct health and armed its looping sound,
but did not flash the hero. The missing instruction was at the end of the same
ROM branch: after damage, dialog, and sound-timer work,
0x4AAFC-0x4AB06 writes 0x12 to `hurt_cooldown`. VBLANK
0x401DE-0x40304 then steps 0x12→0x0C→0x06→0 and copies the
player-position/character-specific hurt words into live MOB color RAM. The
Python branch now writes that game-side timer, so continuous forcefield contact
holds the first hurt color and leaving the beam completes the flash cycle.

Fake-exit selection itself was already the ROM path: `maze_scan_objects(0)`
calls `getrandom(exit_count)` at 0x43E2E, keeps that indexed exit real, and sets
hpos bit 4 on every loser when LFLAG4 bit 6 is active. Fresh gauntpy processes,
however, always initialized the ROM's otherwise-uninitialized `random_seed`
word to zero, so the complete pre-selection draw stream and its result repeated
on every launch. The playable host now supplies one random 16-bit power-on
value, then leaves the ROM LCG to free-run without reseeding. Explicit
`build_state(..., rng_seed=...)` remains deterministic for tests and replay;
level-16 regressions prove different initial words choose opposite real exits.

The F1 value was pygame Clock cadence (`get_time()`), so a healthy 60 Hz host
could report only 16/17 ms regardless of rendering cost. `HostShell.present`
now times the game raster's composition, conversion, scale, and window blit
directly with `perf_counter`, before drawing the diagnostics panel. The field is
named `RENDER` and excludes the frame limiter, input wait, diagnostics panel,
and display swap.

### S-140 · dragon stun never cleared on proximity-entry events

Frame 52867 correctly captured `dragon_state = 2`, but gauntpy treated that bit
as permanent until another potion. The main handler does freeze path, pose, and
fire while stunned, and there is no stun countdown. The missing owner was
`dragon_player_proximity` (0x549EA): after confirming that current entered the
wrapped head-column -4..+5 / row -5..+4 rectangle from a zero or outside
previous cell, its 0x54AD0 arm clears state bit 1 and plays sound 0xD5.

The Python helper had collapsed the two-cell contract to one point, used an
incorrect ±9/±5 box, handled only sleeping wake, and was not called from
ordinary player movement. It now preserves previous/current geometry, receives
every player move, starts/reverses sleep-wake state, and clears stun. Shot
handlers already call proximity before `dragon_shot_hit`; with the missing arm
restored, the first shot at the captured stunned dragon changes state 2→0 before
hits 6→7. The dragon therefore resumes posing, locking, and firing instead of
remaining harmless through the rest of the fight.

A second potion is a separate control path: it clears stun, sets bit 0, and
writes -49, reversing toward sleep. That count stops at zero until another
proximity entry starts +49; it does not automatically complete a two-part wake.
Regressions cover rectangle edges/wrap, outside→inside versus inside→inside
movement, direct player-move wiring, first-shot unstun-before-damage, and both
potion transitions.

### S-139 · narrow-lane response, treasure entry, dragon stun, and frame time

Three complete F4 captures exposed a missing movement path. Frame
8945 in level 16 / maze 15 blocks Down at `(365,223)` between wall-marker slots
`0x1F6`/`0x1F8`; frame 15793 in level 17 / maze 16 blocks Down at `(299,463)`
between `0x3D2`/`0x3D4`; and frame 24137 blocks Up at `(235,352)` between
`0x2AE`/`0x2B0`. In every case the center cell is empty and the two flanking
walls are 32 pixels apart.

`probe_up`/`probe_down` call `tile_lookup_core` for the center and both flanks;
its high-bit wall arm at 0x42688 rounds each marker's live H word and subtracts
four pixels before applying the strict `< 0x7C0` comparison. Consequently each
lane has one clear hero anchor: X=364, 300, and 236 respectively. The prior
analysis stopped there. The blocked-wall arms at 0x42108-0x421B8 and
0x4233C onward round the requested axis to a one-pixel response and nudge away
from the obstructing flank. Gauntpy omitted that response and forced manual
alignment. Holding the requested vertical direction now automatically centers
all three captured heroes and enters the gap on the next frame. The older
frame-10310 X=41 case likewise centers to X=44 in three frames.

The pre-room tally conclusion was also wrong. Although the image has an
already-zero branch from 0x4A77A to the tally routine, the live scheduler reaches
zero by decrementing `1 -> 0` and immediately calls `show_level_start_screen`,
which interleaves the room without a tally. An ordinary level cannot start with
zero through that path. Direct starts and historical snapshots can expose the
residual state, so gauntpy now preserves the reachable outcome and reserves the
visible tally for the treasure room's exit/timeout.

Super Sorcerer `STUN` remains a reveal rather than a persistent freeze:
0x415AC-0x415DC clears the phase flags/high animation state, and later dispatch
resumes the idle cycle. Dragon potion state is different. Frame 52867 has
`dragon_state = 2`, so the main handler gates animation, breath, and shots.
S-140 supersedes the former conclusion that only another potion releases it:
proximity-entry events, including the first shot at the dragon, clear stun.

The F1 overview also gained a host timing field beside the arcade frame number.
S-141 supersedes its original whole-frame cadence measurement with the actual
game-raster render duration. The measurement stays in the immutable host
snapshot and never enters `GameState` or modeled video RAM.

### S-138 · fake-exit VRAM removal and disputed ROM behaviors

On level 16 / maze 15, stepping on a fake exit made its artwork disappear.
The collision branch at 0x513DA-0x51424 calls
`moblist_remove_and_clear` at 0x51404 but never calls `pf_replace`; gauntpy
incorrectly coupled that MOB removal to `clear_cell_descriptor`. Fake-exit
contact now removes only the collision record, preserving the exit descriptor
and visible illusion while still showing first-encounter record 30 and
assigning the Don't Be Fooled objective byte.

One related report was verified as original behavior. Potion `STUN` is not a
persistent Super Sorcerer freeze:
0x415AC-0x415DC reveals every phasing target in the on-screen cull rectangle,
clears its flags/high animation state, and skips its remaining potion-frame
work; later passes resume the idle cycle at 0x4112C and may fire at 0x41142.
Off-screen phasing Super Sorcerers remain invisible. Regressions cover the
fake-exit descriptor, multi-target reveal/culling, and resumed firing. S-139
supersedes this entry's former pre-room-tally conclusion.

### S-137 · player movement integrated multi-pixel axes one pixel at a time

Gauntpy split every ordinary 1–3 pixel player axis into one-pixel probes and
kept any clear prefix before a later substep blocked. The ROM never does this:
`player_try_move_core` adds the complete D6 speed word once, probes the proposed
endpoint, and either retains or rolls back that whole axis before processing
the next one. Its only `D6=0x80` moves are explicit recursive collision-response
calls with separately constructed direction flags.

The workaround also concealed a probe-family conflation. The private
`probe_left`/`probe_right` at 0x426D4/0x4270C inspect one adjacent cell, while
private `probe_up`/`probe_down` inspect a three-cell forward row. They share
`tile_lookup_core` geometry with, but are not aliases of, the public generic
`mob_probe_*` leaves used by actors such as the thief. The private Down boundary
also tests the proposed signed V word in row 31, allowing Y=496 before rejecting
the wrap; it does not return the generic `0x0400` sentinel.

The mover now retains `active_mob_ids[player]` as probe origin, resolves the
complete H word before V, commits both words at the common migration tail, and
keeps ordinary blocked axes all-or-nothing. Horizontal and vertical rollback,
private horizontal flank ownership, the signed bottom boundary, the reported
maze-16 lane, cell migration, movable-wall cadence, and all three recorded demo
actors have regressions. A fresh MAME 0.289 all-actor trace confirms the third
demo actor reaches the exit from `(310,45)` and retires with the same stream
positions after the private-probe split.

### S-136 · complete state dumps could not resume play

F4 wrote all modeled fields to JSON, but the host had no inverse operation and
serialized the thief path grid as an opaque `bytearray(...)` repr. The runner
now accepts `--load-state PATH`, reconstructs `GameState`, `Player`,
`InfoPanel`, `MobTable`, RNG, decoded maze, tuple-keyed maps, sets, tuples, and
the path-grid bytearray, then enters the ordinary frame loop without running
boot or level setup. New dumps encode bytearrays as hex; the loader safely
accepts the earlier schema-1 repr form so already captured troubleshooting
states remain usable, and explicitly migrates the four game fields added since
schema 1 first shipped. It rejects unknown schemas and other mismatched state
shapes instead of manufacturing defaults.

Two independent loads of a real level-1 snapshot advance identically under the
same input, including player/MOB positions, RNG, playfield RAM, and alpha RAM.
Direct-start options are mutually exclusive with `--load-state`; host scale and
first-encounter suppression remain presentation/testing choices. A resumed
snapshot also disables external EEPROM writes, preventing a historical timer,
high-score table, or rotation value from rolling back a newer local EEPROM.

### S-135 · maze-16 narrow wall lane matches the ROM

The frame-10310 capture reproduces at level 17 / maze 16 with the Elf at
`(41,288)`, slot 579. Up probes the empty cell 547 plus wall flanks 546 and 548;
the corrected anchor of wall 546 is within the strict `0x7C0` H/V window, so
gauntpy blocks the move.

This is not a stale MOB or widened Python collision. Direct execution of
`probe_up` (0x425D0) and `tile_lookup_core` (0x42648) against the captured
picture/H/V arrays returns doubled wall slot 1092 with carry set, exactly as
gauntpy does. The two wall collision anchors are 32 pixels apart, leaving one
integer hero anchor, X=44, that clears both strict comparisons. The captured
powered Elf reaches it through the ROM speed cadence with Right, Right, Left,
then moves Up from `(44,288)` to `(44,285)`. No collision widening was made; a
regression preserves both the reported block and the reachable escape.

### S-134 · ROM/Python callable implementation gaps are closed

The exhaustive 322-entry crosswalk now classifies 272 callable entries as
complete Python equivalents and 50 as intentionally omitted hardware, ABI,
dead-code, C-runtime, or representation boundaries. No live entry remains
missing or partial.

`player_hurt_speech_timer` now follows 0x49A98's predecrement, randomized
active-party reload, acid silence gate, and literal per-character sound banks.
`maze_addrandompickups` now consumes the guaranteed hidden-potion countdown,
applies the solo-character/multiplayer/difficulty and spawn-bonus adjustments,
performs the ROM's forward-only random food-removal sweep, restores escaped
loot, and runs the level-three special-pickup draws after party placement.

The thief's 0x4E7FC route test now handles learned transporters and its
player-index-4 corner transition. Movable walls share the ROM ray-march
geometry instead of player probes. Level setup calls the new arbitrary-slot
`scroll_to_slot`. The SCORES cycle was rechecked and its existing full
16-word rotation was already exact: `moveq #0xB` plus the signed loop executes
twelve moves, not eleven.

### S-132 · secret-room invitations, hints, and direct triggers were incomplete

The secret challenge lifecycle selected maze 115/116 and could complete its
round trip, but `show_level_start_screen` left the 600-frame invitation curtain
blank. ROM 0x44F7E-0x450F8 writes `SECRET ROOM`, the winning player's color and
character, the two-line achievement message, both countdown fields, and the
task-specific qualifier from the 14 records at 0x573D4. Those are now literal
game-side alpha-RAM writes.

The separate `secret_need_hint` latch was produced by secret-wall and dragon
rewards but never consumed. `level_splash` 0x4C04E-0x4C108 writes `TO ENTER
SECRET ROOM:` between levels, uses the selected upcoming maze header's trick
when it is currently eligible (including the level-12 dragon gate), otherwise
chooses one of the 17 ROM hint strings, then clears the latch. It does not infer
the hint from the level just left.

The trigger audit also restored three direct `secret_player` writes: ordinary
transport into an exit (trick 3, 0x50916), corner transport through a secret
wall (trick 4, 0x507B8), and pushing a movable wall into an exit (trick 10,
0x42846-0x42A1A). Tricks 1-4 and 10 are completion-only producers and do not
increment `secret_tricks_flags`; the five-transporter challenge 0x56 remains
the distinct pad-bitmask consumer. Clearing the corner-transport wall now
unlinks its marker while retaining H/V geometry, preventing a stale depth-chain
link when the player occupies that cell.

### S-131 · character stat-table selector audit

Direct disassembly and raw ROM reads verified all five requested stat families
against their gauntpy consumers. No behavioral selector was wrong:

- Shot Power is low-byte bit 4. `resolve_shot_hit` reads
  `shot_damage_base_tbl`/`shot_damage_rand_tbl` at 0x596B6/0x596C2 using
  character 0-3 or character+8 when powered; supershots override damage with 3.
- Shot Speed is bit 3. `main_handle_shots` reads the signed X/Y tables at
  0x576E2/0x57792 using `character*8 + direction`, plus 0x28 entries when
  powered. A misleading `_VEL_SHOTPOWER` name and test title were corrected to
  Shot Speed; the implemented bit and values were already right.
- movement Speed is bit 0. `main_move_players` selects character or character+4
  from parallel tables 0x580A8/0x580B8, including their per-frame +0x80 cadence;
  mazes 0x73+ intentionally bypass them with fixed 0x100.
- Armor is bit 1 and selects the protected rows of each applicable incoming
  damage table: +0x20 entries in contact table 0x57A2E, +4 entries in monster
  shot table 0x596CE, and +4 longwords in forcefield table 0x5813C. Death's
  accumulator likewise selects its protected 3-point entry instead of 4.
- Fight Power is bit 2. `mob_collision_test` indexes hand power 0x5B7D4 and
  generator power 0x5B7EC by `character + 4*powered`. Its separate random range
  at 0x5B7E4 is indexed by cabinet player position, not character.

Cross-character regressions now protect the damage/velocity independence and
all eight normal/powered melee base selections.

### S-130 · potion flash and special-target magic paths were absent

`main_handle_potions` consumed inventory and ran the 28x16 effect matrix
immediately, but omitted several parts of the ROM path. At 0x47084-0x47098, drinking
or shooting a potion loads color 3 of the triggering player-position palette
into the 0x90401E latch. VBLANK copies that word to playfield color RAM 0x910510;
the next main-loop pass restores 0x90401E from the ordinary floor-color word at
0x904020. Gauntpy now models both RAM words and the one-field color-RAM write, so
the screen flash comes from authoritative playfield color state.

The same handler calls `dragon_any_segment_near_screen` before the ordinary MOB
scan. A visible active dragon gains stun bit 1; a second potion clears stun,
sets wake bit 0, and loads animation counter -49; a potion during wake starts or
reverses the 49-frame wake animation and plays sound 0xD5. Direct Unicorn
execution of ROM 0x46FEA confirmed those exact state/animation results and the
player-0 flash word 0xFF00.

The scan is an alternate `monsters_everything` pass, not an extra call before
ordinary monster updates; survivors therefore cannot act again on the potion
frame. It also has pre-matrix arms: magic sets an idle Acid puddle's
attack/stun phase and reveals a phasing Super Sorcerer, clearing their animation
state rather than removing them. A subsequent eligible Acid hit reaches its
zero matrix entry and destroys it. These paths now run before the literal
matrix. The matrix selector now also keeps `potion_player` as player/shot
provenance and reads the character separately, as 0x41588-0x41662 does. The
per-character outcomes were otherwise already correct: normal
Warrior/Valkyrie magic only weakens a full-tier Ghost, Wizard and Elf destroy
ordinary monster rows outright, and Elf demotes rather than clears a top-tier
generator.

### S-129 · F5 left the level-start splash permanently opaque

The immediate skip loaded and spawned the next level, then zeroed the shared
UI timer without running the timer-expiry teardown. The `LEVEL:` alpha words
therefore had no remaining owner that could clear them. F5 now mirrors the
normal expiry order: load the maze without players, run `maze_show`, then
spawn the surviving party and clear the host-side pending marker.

### S-128 · live troubleshooting required replaying whole levels

The host now provides three explicit non-arcade shortcuts. F5 computes the next
level/maze through the cabinet rotation, reloads it immediately, respawns the
active party, and snaps the camera while preserving inventory. F6 and F7 add
one key or potion to the selected host player and call `player_inv_update`, so
the authoritative counters and modeled alpha-RAM display remain synchronized.
Inactive players and non-gameplay level skips are rejected with a terminal
message rather than silently mutating partial state.

### S-127 · troubleshooting had no complete live-state capture

The F1 panel deliberately presents compact immutable projections, but that is
not enough to reconstruct a one-frame collision divergence. F4 now atomically
writes every modeled `GameState` field to a timestamped JSON file in the
Git-ignored `traces/state-dumps/` directory and prints its path. The serializer
includes slot-backed `MobTable` arrays, dataclass state, non-string-keyed maze
maps, RNG state, and all modeled display memory. It is host-only and read-only.

### S-125 · thief collision waited for its sprite origin to enter a wall

On level 16 / maze 15, a player at `(12,304)` can draw the thief east through
the one-cell pocket beside the wall at packed slot `0x262`. Gauntpy derived the
thief's candidate cell from its uncorrected sprite origin and did no collision
work until that point crossed X=32. The 24-pixel thief therefore advanced to
X=28, visibly buried itself in the wall, retained the stale open-cell MOB slot,
and became difficult or impossible to hit while blocking the pocket.

Direct ROM execution of `thief_move_engine` (0x4EE7A) with the maze-15 records
keeps the thief at X=12. Each axis first writes the proposed native H/V word,
then calls `thief_probe_axis` (0x4EE0A) with the generic three-cell
`mob_probe_*` callback. The live-anchor overlap detects slot `0x262` before the
sprite origin crosses the cell boundary. Clear space keeps the full 3/4-pixel
step; an overlapping occupied candidate consumes that axis, with its object
handler deciding player/item/transporter effects. The final 0x4F4A2 tail
computes the record's new slot with the same +12 H / +8 V body bias used by the
other dynamic MOB movers.

The thief/mugger mover now follows those rules, shares the generic probe without
the player's deferred-item policy, and migrates its MOB record from the biased
live anchor. A ROM-backed maze-15 regression protects the reported coordinate.
The host diagnostics font also increased from 11 to 12 pixels (heading 13 to
14), with an 11-pixel row pitch that still fits the complete overview at native
panel height.

### S-124 · level-1 top wall used transient row-zero MOB contents

The first live frame reassigns reserved MOB slots 1-16 from their setup-time
wall markers to the fixed shot/effect channels. The upward player probe then
treated those cleared slots as open floor, letting the hero rise from the ROM's
Y=16 limit to Y=10. At that depth, up-right movement could target reserved row
zero and become stuck instead of sliding along the wall.

The ROM does not inspect row-zero occupancy from a row-one player.
`player_try_move`'s internal `probe_up` (0x425D0-0x425DE) detects every doubled
row-one slot with `D2 <= 0x007E` and compares the proposed full V word against
`0xF080`; the hero's encoded 3x3 size bits make the next step above Y=16 block.
Gauntpy now models that coordinate boundary independently of the transient
fixed-channel pictures. A full-frame level-1 regression holds Up into the wall,
then Up+Right, and verifies the Y=16 stop and lateral slide.

### S-123 · diagnostics navigation order and game-panel frame overlay

Diagnostics page navigation now follows F2 = previous and F3 = next, matching
the panel legend. The decimal host frame counter has moved entirely to the F1
overview and is no longer composited over the arcade player-status area.
`PAUSED` remains the sole host marker on the game raster.

### S-122 · diagnostics exposed only one fixed overview

The F1 panel now has nine host-owned pages: overview, player input/runtime,
decoded demo records, level flags and timers, actor counts plus a raw selected
MOB inspector, thief/dragon AI, display-memory state, audio queues, and events.
F2/F3 page through them and brackets select occupied MOBs. The rolling event
history is derived from consecutive immutable snapshots while the panel is
open; no game-loop call or simulation producer was added.

### S-121 · diagnostics used Pillow's tiny bitmap font

The host panel now uses an anti-aliased system monospace face (Consolas on
Windows, DejaVu Sans Mono or Menlo elsewhere, with Pillow's scalable default as
a final fallback). The native panel is 320 pixels wide and player state is
compacted to two rows each, preserving the complete display at scale 1 without
scaling the glyph raster.

### S-120 · completed demo actors started playable level 2

When the third recorded actor finished its exit animation,
`players._status8_complete` ran gauntpy's normal immediate level-handoff helper.
That committed the demo's computed `level_next = 2`, loaded the next maze, and
respawned the three attract actors under keyboard control. The ROM instead
leaves the non-bonus transition to `main_start_game`: its 0x480B6 DEMO arm
waits for shared effect slots 13-16 to clear, calls `player_resetall`, closes
the dialog, and clears `attract_timer`. `main_attract` then advances from DEMO
to LEGEND later in the same frame. The port now preserves that ownership and
the completed puppet party cannot enter normal play.

### S-119 · playable host defaulted to 2x scale

The `gauntpy-play` CLI and `HostShell` now default to 4x game scaling.
`--scale` continues to override it, and the diagnostics panel remains unscaled.

### S-118 · diagnostics text inherited the game scale

The host initially scaled the complete 240x240 diagnostics raster by
`--scale`, making its small text blocky and consuming unnecessary width. The
game remains scaled normally, but the panel now keeps a fixed 240-pixel host
width and renders its font at native resolution; only its background height
extends to match the scaled game window.

### S-117 · host diagnostics shared the arcade alpha panel

The requested `MAZE nnn` and `P# x,y` diagnostics had been written into rows
27-28 of modeled alpha RAM, making host inspection modify arcade-visible state.
A toggleable F1 side panel now captures an immutable post-frame snapshot and
renders it with a host-owned PIL surface. It exposes mode, level/maze, camera,
RNG, IT owner, timers, demo pointers, MOB counts, and all four player records
without touching simulation or video RAM. The old alpha diagnostics were
removed; the game compositor remains the original 336x240 raster.

### S-114 … S-116 · demo potion, IT state, and movable-wall cadence

- **S-114:** `main_handle_potions` always read `debounce_shift_magic`, so the
  demo's active-low Magic bit at the current `demo_ptr` was never seen. The ROM
  branches at 0x47012: normal play matches the debounced `0x1C` edge, while any
  nonzero game mode tests bit 0 of the current demo record directly. The Elf now
  spends the potion, clears the on-screen monsters through the ordinary potion
  matrix, observes the resulting dialog pause, and reaches the exit.
- **S-115:** two independent IT paths were missing. `game_vblank`
  0x40328-0x4037A alternates alpha-color palettes 12-15 every 16 frames, flattening
  their three visible colors to color 0 and then restoring the ROM ramps; those
  modeled color-RAM writes now make the `0xB000 | player<<10` label flash. Player
  collision at 0x41DAC-0x41DEC also transfers `player_it` when the current holder
  runs into another hero and stuns the recipient for 0x40 frames. The recorded
  tag therefore moves the label from the red Wizard to the blue Elf.
- **S-116:** no movement change was made. Direct ROM execution and a fresh MAME
  0.289 RAM trace agree that the opening movable wall advances one pixel on a
  blocked push frame while the base Elf advances two pixels only when the
  collision gap permits it. The resulting 0/2-pixel hero cadence is original
  game state, not a Python interpolation defect; a regression protects the
  paired player/wall sequence.

### S-112 … S-113 · demo transporter timing and incomplete attract pages

- **S-112:** `tport_player_move` omitted the first-encounter dialog call at
  0x50840-0x5084C after selecting an ordinary transporter landing. In the
  attract demo that 150-frame dialog freezes `main_move_players` and the ROM
  script while the transporter animation continues outside the dialog-gated
  world band. Without it, the remaining LEFT record expired during the
  dissolve, leaving the Elf at `(92,256)` and preventing the recorded route
  from reaching the exit. The game-side dialog write is restored. A follow-up
  found that the runner's `--no-first-encounter-messages` option still
  suppressed this timing-critical DEMO dialog; suppression is now limited to
  non-DEMO play. The actual `play.bat --attract` configuration now follows the
  fresh MAME 0.289 command boundaries from the `(92,240)` landing through the
  exit.
- **S-113:** the rules legend transposed five of six `alpha_clear_rect`
  arguments, erasing labels and the first status-panel column instead of
  revealing maze-103 item art. It also omitted the centered LEGEND heading,
  used normalized spellings instead of ROM `DESTRUCTABLE`/`MOVEABLE`, and
  flattened the three text palettes. The monster page omitted the complete
  42-cell table at 0x5A56E: duplicated creature labels plus the Fight/Shoot/
  Magic `NO`/`YES`/`STUN` matrix. Those modeled alpha-RAM writes now follow
  0x4CDB8/0x4CFDA exactly. The SCORES page's top opaque boxes also began one
  row too high; rows 1-13 are opaque while row 0 remains maze-103 scenery,
  matching MAME 0.289.

### S-111 · maze-17 `(16,10)` seam report matches the ROM

No behavior change was made. With the live wrapped camera, gauntpy and direct
ROM execution agree at pixel `(16,10)`: left/right move to X=14/18, down moves
to Y=12, and up remains at Y=10 because the top wall blocks it. Interpreting
the reported Y as native/upward (screen Y=486) also matches for all cardinal
and diagonal inputs. Moving toward a wall may leave the sprite visibly closer
before the next frame blocks because collision compares corrected MOB anchors
with a strict 0x7C0 overlap and applies horizontal motion before vertical; that
is not evidence of a separate L/R seam defect at this coordinate.

### S-107 … S-110 · top-edge movement, Super Sorcerers, and special potions

- **S-107:** maze 17 at player pixel `(268,15)` reproduced a Python-only
  lateral block against the reserved row-zero wall. The original repair
  suppressed the generic probe's upper flank near rows 0–1. **Superseded by
  S-137:** the private player horizontal probe has no vertical flanks at all and
  retains the live record slot as its origin.
- **S-108:** the same investigation found the narrow-passage boundary mismatch:
  `player_try_move_core` keeps `active_mob_ids[player]` in D2, while the port's
  one-pixel integration re-quantized the corrected sprite origin into reserved
  row zero. Intermediate probes now fall back to the live record for slots
  0–31, preserving both ROM boundary behavior and the established one-pixel
  integration that prevents high-speed wall skipping. The shipped demo retains
  its prior port-side top-flank behavior because that is required to preserve
  the independently captured MAME maze-102 route and transporter landing.
  **Superseded by S-137:** primary probes no longer derive intermediate cells;
  private probe ownership and the full-axis transaction match the ROM directly.
- **S-109:** Super Sorcerer placement derived its start cell from the player's
  `x>>4`, shifting a correctly placed hero one cell left, then materialized the
  sorcerer without the ROM's four-pixel H correction. It now starts from
  `active_mob_ids`, writes destination H as `column*16-4`, preserves only the
  low six H/V bits at 0x5FF2C, and performs the literal eight-neighbour crowd
  scan. Cardinal and diagonal placements now match ROM execution and face their
  shots back along the chosen line.
- **S-110:** hidden potion type 61 was always converted into an inventory
  potion. The ROM decodes `(picture-0xA728)>>2` and first offers permanent power
  ID 0–5; only an already-owned power falls through to a potion (when inventory
  has room) or a solo 100-point award. The six stat powers and their sounds now
  apply, and `player_inv_update` writes the matching icon at the exact ROM
  columns 40, 39, 32, 31, 30, and 29.

### S-101 … S-106 · transportability, dragon/IT presentation, and maze diagnostics

- **S-101:** corner transport had stored the landing cell as
  `player_tport_type`, but the ROM clears that word at 0x5015C. The zero selects
  0x5078E's `pf_replace(landing, floor)` branch for ordinary 0x8000 wall
  markers. Transportability can now land on and erase those walls while leaving
  forcefield hubs and boundary cases protected; logical maze state, the MOB
  marker, and descriptor VRAM change together.
- **S-102:** `_probe_candidate_blocks` had bypassed collectible cells before
  `squeeze_through_check`. The ROM tests transport first, so a transportable
  player skips most adjacent items instead of collecting them. An item in the
  actual landing cell still goes through the relocation interaction and is
  collected.
- **S-103:** counted dragon hits changed paths but omitted 0x541E8-0x5422A's
  primary-segment hpos rewrite. Hits 1-2, 3-5, and 6-8 now select live MOB
  palettes 8, 7, and 6 before the ninth hit kills the dragon.
- **S-104:** maze 18, used by the direct level-19 runner start, genuinely
  decodes four IT creatures at slots 239, 327, 451, and 840. This is ROM maze
  content, not duplicate spawning. The separate display bug was real:
  `player_it_label_set` writes `0xB000 | player<<10`, not the ordinary
  player-text attribute, restoring the bright label.
- **S-105:** tight passages on the reported level-20 and level-22 areas exposed
  a collision-model shortcut: pictures with bit 15 set were rounded from their
  packed slot rather than their live H/V words. The 0x407EA-0x40820 and
  0x42688-0x426CE branches round the live words, which retain deliberate door
  and item placement corrections. The modeled probes now do the same.
- **S-106:** the bottom of the status panel now receives `MAZE nnn` and the
  first active player's `P# x,y` pixel coordinates. These requested diagnostics
  are explicit non-arcade content, but are written through modeled alpha RAM
  rather than composited as gameplay-looking renderer text. **Superseded by
  S-117:** they now live in the separate read-only host panel and no longer
  modify alpha RAM.

### S-100 · treasure rooms retained the ordinary panel header

`setup_infopanel` now follows its maze-number branch at 0x45314. It always
clears the first seven rows of the 13-column status panel, but only mazes below
0x68 rebuild the GAUNTLET II dungeon glyphs and `LEVEL n` field. Treasure and
secret rooms instead write the ROM 0x5758E descriptor: `TIME:` at alpha column
34, row 1, above the existing large countdown. This removes the stale logo and
level number shown by gauntpy while preserving the player blocks below.

### S-95 … S-99 · continue, dragon, thief-return, runner, and reported nonbugs

- **S-95:** the continue prompt drew its literal `WITHIN    SECONDS` line but
  omitted `main_attract`'s 0x44984-0x449B6 full-second writer. The live
  `attract_timer / 60` value now updates alpha column 13, row 14 as a two-digit
  field.
- **S-96:** the dragon collision retry discarded
  `dragon_shot_hitbox_adjust`'s tagged result after testing the moving head.
  Successful head overlaps now retain the post-shift `0x0800` tag consumed by
  `dragon_shot_hit`, so open-mouth hits increment `dragon_hits`. The close-range
  breath also honors its live `mob_vpos = 0x12` 3x3 size instead of being forced
  through the ordinary projectile 2x2 asset geometry.
- **S-97:** deterministic mugger/thief escape reaches the recorded start cell,
  clears the MOB, and resets both current-slot fields; the reported frozen
  actor was not reproducible through that ROM path. The related real omission
  was `maze_addrandompickups`' 0x44166-0x441A6 next-level return: escaped mugger
  food and thief loot are now placed through the ROM's random empty-cell walk,
  including encoded multiplier-bag value restoration.
- **S-98:** direct `gauntpy-play` now defaults to the Elf. `--character` remains
  available for selecting any of the four classes during testing.
- **S-99:** the treasure countdown position itself was verified: setup and the
  live timer both call OS large decimal at alpha column 34, row 2; a
  space-padded one-digit value begins two cells later by design. S-100 records
  the separate surrounding-header omission. Holding Fire against a wall still
  selects and advances the shooting table before each shot; a regression uses
  the hero's real `cell_x - 4` geometry and protects those visible frames.

### S-93 · death/continue lost the player spawn record

`maze_scan_objects(-1)` now selects and stores `maze_player_start_slot`
(0x9049E0), removes that marker just as `pf_replace` does, and
`player_start_inner` reuses the saved cell for first starts and post-death
continues. A failed loaded-maze placement is no longer finalized into an active
player with MOB slot zero. Successful continues rebuild the hero picture,
tracking words, and snap the camera so the player is immediately visible.

### S-94 · dragon wall/flame report confirmed as ROM behavior

No behavior change was made. `dragon_choose_move_direction` 0x53E4A tests both
leading footprint cells and skips the candidate at 0x53FE0-0x54044 when either
picture is the `0x8000` wall marker. Because target/distance publication happens
after those probes, a player approached through that wall does not establish the
close-range flame lock. A regression now protects this ROM ordering.

### S-88 … S-92 · exit, treasure, idle-door, and thief-route regressions

- **S-88:** moving exits now rebuild their 0x8001 marker H/V/link words from the
  destination slot (0x52984-0x52A32), so a later exit dissolve uses the new
  location rather than copied coordinates from the old slot.
- **S-89:** treasure-room entry now writes the ROM 0x572C6-0x57325 title and
  instruction page, including both initial countdown fields.
- **S-90:** `main_treasure_timer` writes the live large countdown at alpha
  column 34, row 2 on every full second (0x4D2FC-0x4D32A).
- **S-91:** the common post-spawn level tail now calls `thief_setup` and clears
  `idle_timer` at the ROM's 0x4835E/0x4836A sites, so timed doors are re-armed
  on every level.
- **S-92:** player transport now records the victim's forward/reverse transporter
  route; `thief_enter_tport` follows the two-stage route lookup at 0x4FAD4,
  creates the destination placeholder, and the transition completion repairs
  the reverse path before recomputing the next cell. `main_thief_anim` also
  honors the 0x4E900 transition-timer gate, so the thief cannot move while its
  dissolve is in flight.

### S-87 · half-width large glyphs were forced to two cells

`render_large_glyph_register` tests the right-hand quad word at 0x3280 and
returns an advance of one cell when it is zero. The alpha writer now does the
same instead of always writing and advancing two cells. In the level splash,
the colon's ROM quad `(0x6D, 0x6D, 0, 0)` therefore occupies only column 14;
column 15 remains the intended blank before the large decimal at column 16.

### S-86 · corrected large-font base and level-splash teardown

The OS `LEA 0x2C6(PC),A4` in `display_large_text` resolves to 0x34A2, not
0x34A6 or 0x34A4. The exact 128-byte ASCII map is now transcribed from that
effective address. On expiry, the level splash now also performs `maze_show`
(0x4526A): alpha columns 0–28 and hidden 42–63 are cleared while the opaque
13-column status panel is preserved, before waiting players are spawned.

### S-85 · remaining reconstructed large-font and HUD table shortcuts

The ROM-free large-font renderer now assigns digit/letter quadrant images through
the same OS 0x34A2 index map as the live alpha writer rather than enumerating
`0-9A-Z` against the quadrant table. The five `M_DUNGEON` glyph rows are also
literal transcriptions of ROM 0x574B8 rather than generated contiguous ranges.

### S-84 · level splash glyphs were corrupt and its hold never expired

The large-character writer now indexes the literal OS ROM map at 0x34A2 instead
of assuming digits begin at glyph quad zero; `LEVEL: 2` and other large text now
use the same alpha words as OS `display_large_text`/`display_large_decimal_value`.
The shared UI delay at 0x904A4E is now decremented by `main_start_game`, outside
the dialog-gated gameplay band, matching 0x4817C. The splash therefore expires
and places waiting players even when a message box is active.

### S-83 · boundary walls and gameplay presentation regressed after VRAM migration

- The reserved row-zero boundary now participates in the ROM's wall-adjacency
  predicate, so its horizontal neighbours (and the opposite vertical seam) use
  continuous wall stamps instead of isolated segments.
- Whole-panel setup now performs `maze_hide`'s opaque 13-column alpha fill before
  writing the header and player blocks, preventing playfield pixels from showing
  through the status area.
- `game_vblank`'s 32-word gradient at ROM 0x405E8 now drives alpha color RAM
  0x91002E, restoring the color cycle in the GAUNTLET II panel logo.
- The 0x4A748 transition gate now sends ordinary levels directly to the ROM's
  `LEVEL:` splash and reserves `show_level_end_bonus_screen` for bonus-room
  transitions. The 150/180/600-frame level-start hold now delays player placement.

### S-82 · MOB/front-end rendering bypassed modeled video memory

`GameState.mob_color_ram` now owns the complete 256-word MOB palette region.
`init_display`, player setup, hurt/power VBLANK effects, title cycling, and
SCORES cycling write the modeled color banks; the MOB compositor resolves every
sprite solely from its hpos palette nibble and that RAM. TITLE now writes the
ROM's fixed playfield tilemap/palette and procedurally builds all 159 MOB records
used by `title_logo_init`, including its two-group motion program. SCORES and all
three LEGEND pages reload maze 103 through normal display initialization.

The audit also completed the display-memory side of OS large text, ordinary
initials entry, the continue prompt, the secret-room 29-character editor and its
ROM-matched CRC secret code, plus the rules-page reveal windows/decorative MOB
writes. Temporary front-end/bonus alpha content is cleared at the same lifecycle
boundaries as the ROM. Direct game-content compositing has been removed; the only
host overlay left is the PAUSED indicator, plus ROM-free glyph
fallbacks.

### S-81 · playfield color RAM remained a palette snapshot

`GameState.playfield_color_ram` and `playfield_shadow_color_ram` now model all
128 IRGB words at 0x910500 and 0x910400. Level setup follows `init_display`:
palettes 0–3 clone the level floor palette, palette 4 receives the transporter
palette, palettes 5–7 are the exact staged wall fades, and the shadow bank is
derived by `palette_fade_copy`. Trap/stun VBLANK pulses, forcefield color steps,
and transporter records write the live banks; descriptor-only wall/exit changes
remain descriptor writes. The cached renderer resolves both normal and shadow
colors solely from these arrays.

### S-80 · playfield pixels bypassed modeled descriptor VRAM

`GameState.playfield_ram` now owns all 4096 column-first descriptor words.
Level setup commits random floor/wall texture choices once; shared ROM-shaped
writers update doors, exits, transporters, forcefields, traps, and living walls.
The compositor derives and generation-caches its normal/shadow rasters solely
from VRAM; `maze.data` remains logical state and per-effect draw overlays are no
longer on the live render path.

### S-79 · game alpha content bypassed modeled alpha VRAM

HUD fields, dialogs, high scores, legend/select text, and bonus tallies were
reconstructed directly in `render/hud.py` and `render/screens.py`. Their ROM
call sites now write complete attribute/glyph words into `GameState.alpha_ram`;
one generic alpha pass resolves opacity, bank/palette, glyph, and live
`alpha_color_ram` each frame. Only the host PAUSED overlay and
ROM-free glyph fallbacks bypass that layer.

### Twelfth-pass attract/HUD/wall presentation (S-76 … S-78)

- **S-76 · damaged destructible walls jumped to unrelated static palettes.**
  The ROM's `7-stage` value indexes live color RAM, not gex's wall-palette list.
  The overlay now keeps the level wall palette instead of turning pink/green
  after the first hit; the exact damage stage remains in simulation state.
- **S-77 · player status blocks lacked their alpha-palette backgrounds.**
  `init_display`'s two 0x20-longword copies from ROM 0x5AD1E now populate alpha
  color RAM 0x910000/0x910100. `setup_infopanel` writes opaque space cells with
  attributes 0xD000–0xDC00 into alpha RAM, and the renderer resolves color 0
  through that live RAM. The resulting dark red/blue/yellow/green values match
  MAME 0.289 without sampled RGBA constants.
- **S-78 · the SCORES overlay erased its maze scenery.** MAME shows score boxes
  over maze 103. Both SCORES and LEGEND now independently load maze 103 through
  their ROM setup paths. MAME also confirms LEGEND's 29-column opaque
  alpha curtain is intentionally black; its maze remains loaded as scenery
  behind that curtain rather than visibly filling the text area.

### Eleventh-pass presentation/attract regressions (S-71 … S-75)

- **S-71 · bounded right edges lost the repeated left-wall strip.** The S-70
  clamp was made symmetric. Updated MAME 0.289 comparison then exposed the
  deeper error: visible playfield cropping uses `pf_hscroll`, while
  `(pf_hscroll - 8) << 7` is only the collision-window origin. At the ROM's
  clamps, X=5 cuts the left edge correctly and X=292 wraps twelve pixels of the
  left boundary wall onto the right; MOBs remain non-wrapping.
- **S-72 · shootable secret walls used the special preview palette.** Secret
  walls must be visually indistinguishable from their level's regular walls.
  They now retain the level wall palette, as destructible walls already do.
- **S-73 · the IT label was absent from the host HUD.** The compositor now draws
  the ROM's literal `I`/`T` glyphs at alpha column 0x24 on the tracked player's
  SCORE/HEALTH row.
- **S-74 · demo transport used a hand-tuned landing and one sparkle.** A retained
  MAME 0.179 trace proves maze 102 moves player 1 from slot 492 `(180,240)` to
  slot 486 `(92,240)`: source dissolve through phase 21, destination effect from
  phase 22. The ROM direction-rotation search and second `handle_tport` call are
  now ported; the demo-only four-cell offset is gone.
- **S-75 · position-0 joystick input restarted the demo attract screen.** On the
  single-keyboard host, pressing a direction during DEMO now advances to LEGEND
  instead of reinitializing maze 102.

### Tenth-pass rendering regressions (S-69 … S-70)

- **S-69 · horizontal doors had a lower protrusion.** The playfield renderer
  treated `door_gfx_by_neighbors` picture words as four sequential tiles and
  baked a 2×2 stamp. The ROM writes a live MOB picture/H/V record per door
  cell. Doors now remain dynamic MOBs, and level setup ports the connected and
  isolated-door picture/position tables at 0x5F9CE–0x5FC11; removing a door
  refreshes its surviving neighbours.
- **S-70 · bounded left edges exposed wrapped world pixels.** The hardware
  scroll conversion subtracts eight pixels; masking that origin unconditionally
  turned the bounded left clamp into world X=509. The renderer now clamps that
  negative origin and disables opposite-edge MOB candidates on non-wrapping
  horizontal axes while preserving the hardware seam on wrapping levels.

### Ninth-pass live-play regressions (S-65 … S-68)

- **S-65 · forcefield visuals were frozen in the cached level raster.** The
  cycle state and repeated damage phases were live, but the compositor never
  applied `forcefield_color` after level setup. Runtime segment cells are now
  re-stamped through that color each frame, including wrapped beams.
- **S-66 · the top playfield boundary was discarded by shot collision.** The
  row-zero branch at 0x40A9A returns a `0x400`-tagged playfield target when an
  ordinary shot enters the top boundary. The port returned no hit, so reflective
  shots escaped instead of reaching `shot_reflect_calc`.
- **S-67 · transporter landings incorrectly rejected occupied cells.** The ROM
  removes the old player record, resolves or clears a destination occupant, and
  creates the player at that slot (0x508BA–0x509C8). The port now replaces
  permitted monsters and handles collectible landings while preserving the
  exact `tport_check_dest` blockers.
- **S-68 · corner-squeeze transport omitted the destination screen gate.**
  The 0x500A2 `level_flags_4`/`tile_on_screen_test` gate now rejects an
  off-screen wrapped destination, preventing transport through the left edge of
  non-scrolling levels such as level 8.

### S-64 · death reset orphaned the migrated player record

The death path used to call `player_resetcounters`, which cleared the player's
slot pointer before the live record was unlinked. The record therefore remained
in the cell and depth chain as an invisible blocker. Death now releases the
remembered live slot before resetting the per-player RAM.

### ROM-faithful live player record migration (S-63)

- **S-63 · a live player's MOB record now migrates by maze cell.** Every hero
  used to stay in the PLAYERSTART slot it spawned in while its H/V words roamed
  the maze, so "identity is location" — the rule the whole MOB table is built
  on — held for every object except the four that matter most. That single
  divergence needed a port-only overlay in each consumer: shot probes carried
  the player record as an extra candidate, `monsters._player_in_cell` resolved
  an "empty" cell to whichever hero was standing in it, the renderer widened
  its SLIP band window to keep an off-row hero visible, and the tile pass
  interacted with two cells per frame because the record's own centred cell
  handoff was missing.

  `player_try_move_core`'s tail (0x424CA-0x42526) is now ported literally.
  `coords.mob_cell_of` is the ROM's cell rule — `(V + 0x400) & 0xF800 ^ 0xF800`
  plus `(H + 0x600) >> 5`, the same arithmetic `monster_loop_core` uses at
  0x41358 — and `players.migrate_player_record` relocates the record with
  `MobTable.move_slot` (`move_mob_slot`, 0x5DE0A) whenever the hero crosses into
  a free cell. Picture, both position words with their live low fields, the
  PLAYERSTART object type and the state word carrying the player index all
  travel with it; the vacated cell is cleared; the depth chain and the SLIP
  bands follow. It refuses the managed low slots 0-0x1F and never overwrites an
  occupied cell — an occupied destination goes to `player_tile_interact` first,
  exactly as 0x42542 does, and the record follows the hero in on the same frame
  once the tile is consumed.

  Consumers lost their overlays: `shots.shot_collision_candidate_core` evaluates the probed
  cell's own occupant, `monsters` resolves contact and rendered occupancy from
  the cell, `render.mobs` walks one geometric band window, `player_tile_pos`
  and the forcefield query read the record's cell, `nearby_mob_clearance_test`
  is the ROM's eight-neighbour palette scan again, and the demo join scan starts
  from `active_mob_ids` instead of a re-derived pixel cell. The transporter,
  corner squeeze, exit and death paths all relocate or release the same record.
  `_push_movable_wall` also takes the ROM cell rule, matching `failed_door_post`
  (0x427B4) instruction for instruction.

  Monsters can no longer step into the square a hero occupies — they hit it
  instead (0x413A2) — which restores hand-to-hand contact that the fixed record
  had silently suppressed, because a monster in the hero's cell *was* the
  probe's own origin cell. The attract actor uses the same ordinary-monster
  melee path. Gauntpy's monster step order puts two port-only Grunts across the
  terminal recorded run; those divergent records are removed when they obstruct
  that final pair, rather than disabling collision globally or letting the Elf
  pass through a live MOB. Covered by `tests/test_player_record_migration.py`
  and the full demo test.

### Eighth-pass live combat/presentation audit (S-57 … S-62)

- **S-57 · real forcefield hubs produced no beam segments.** Maze placement
  stores hubs with marker picture 0x8000; segment setup tested the marker as a
  blocker before recognizing the partner hub, built an empty table once, and
  froze it for the level. Partner hubs are now recognized first, so every
  later random lit phase damages the same beam cells.
- **S-58 · lobbers led stationary players.** The lead calculation used the
  player's persistent facing rather than the achieved-movement word at
  0x9048F0. Player movement now publishes the active-low per-axis result and a
  stationary 0xF nibble selects the ROM's zero-padded direction row.
- **S-59 · demon fire used a base palette.** Fixed demon channels 5–8 now route
  palette nibble 0xE through player-color slot 2, matching the Wizard palette
  selected by the original projectile word; lobber channels remain base
  palette 1.
- **S-60 · pause was only visible in the window caption.** The host passes its
  pause state into the compositor, which draws `PAUSED` in the lower-right
  panel.
- **S-61 · point-blank shots could skip a monster.** The port-only roaming-player
  overlay replaced a cell's real occupant before the shot hitbox test. Real
  occupants are now evaluated first and player records were additional fallback
  candidates, preserving enemy-shot hits without hiding co-located sorcerers.
  Superseded by S-63: the overlay is gone entirely, because a live hero *is* the
  cell's occupant.
- **S-62 · floating score producers were incomplete.** Potion-killed Death now
  uses the exact eight-entry score/popup tables at 0x579D2/0x579E2. Treasure
  pickups allocate a visible 100-point popup, and popup integration tests cover
  depth placement through the renderer.

### Seventh-pass seam tracking audit (S-55)

- **S-55 · level 7 lost monster tracking across the left seam.** The
  `pixel << 7` position words use unsigned 16-bit overflow as one 512-pixel
  maze. Monster culling and projectile off-screen disposal did not, so the
  camera could show monsters and lobbers that the simulation treated as half a
  word away. Both windows now use the one-maze modulus; the vertical cull uses
  the exact upward-coordinate origin, and the shared tile-visibility helpers
  wrap Super Sorcerer and transporter candidates across either seam.

  Superseded in detail by S-56: the MOB words are now stored in the arcade's
  own encoding, so `512 << 7` *is* 0x10000 and the modulus is plain 16-bit
  arithmetic.

### Native MOB coordinate migration (S-56)

- **S-56 · the MOB H/V words are now the arcade's own.** gauntpy previously
  stored a position field one bit low (`pixel << 6`) with a downward vertical
  axis, and converted at every ROM boundary: correction tables halved on
  import, velocity/hitbox/window constants halved, the vertical axis flipped in
  the cull rectangle, the shot spawn tables, the dragon head deltas and the
  lobber lead. The state is now the hardware's: position in bits 15-7 over a
  seven-bit low field, one pixel per 0x80, and the vertical field counting up
  from the playfield floor exactly as `maze_place_object`'s `slot << 11`
  writes it. `coords` owns the encoding and the two boundary conversions
  (`screen_y`/`native_v` for a downward maze row, `sprite_top_y` for the
  renderer); every ROM table is now transcribed at its literal value, and one
  512-pixel maze wraps at 0x10000 with no explicit masking.

### Sixth-pass live-render/demo audit (S-44 … S-54)

- **S-44 · trap-controlled walls vanished during level setup.** Types 7–9 were
  compacted before the cyclic-wall flag was checked, consuming ordinary trap
  groups. Setup now compacts only cyclic levels; stepping on a trap clears its
  matching wall records and the corresponding maze descriptor cells.
- **S-45 · starts and continues used inconsistent health paths.** The direct
  runner now starts from factory settings, and paid starts/continues restore the
  complete configured starting-health entry. Demo and free-play joins take the
  ROM's 2000-health branch. The finalizer also runs the scripted join credit
  path, so late demo actors are alive rather than zero-health placeholders.
- **S-46 · special playfield stamps were missing or conflated.** EXITTO6 now
  uses its distinct 0x5C8A8 descriptor, transporter markers render as the
  0x49E–0x4A1 playfield stamp, and transporter index zero is transparent over
  the floor rather than an opaque black square.
- **S-47 · live color-RAM effects were frozen.** Trap and stun palettes now
  follow the alternating-field 0x4044↔0xA0AA and 0x2220↔0xEEE0 pulses.
  Transporter palette entries 8–13 consume all six records at 0x5AFAE.
  MOB palettes now live in the 256-word 0x910200 bank: init_display's exact
  0x5AE1E and Wizard-table copies, per-player spawn/hurt/power writes, and the
  title's ten-row shift plus 0x910332 brightness injection all mutate that RAM.
  MOB and title graphics remain indexed until the renderer resolves the live
  entries; title MOB composition itself remains deferred.
- **S-48 · the dragon never reached its flamethrower state.** Direction choice
  now uses the ROM compass, candidate-cell probes, target/distance packing,
  no-target sentinel and signed turn duration. Muzzle alignment updates the
  lock bit, close targets produce the sustained max-tier flame, and projectile
  direction is no longer rotated by 90 degrees.
- **S-49 · wrap-camera targets could remain exactly 512 pixels away.** The
  camera extent now includes the current center, folds each player into the
  register-relative window, and uses the 0x140 outlier threshold plus 200-pixel
  adjustment. This removes the endless left pan near the dragon/world seam.
- **S-50 · score-popup producers were disconnected.** Adaptive food uses the
  parallel 0x5B774 popup table, and special score bags display and award
  `special_bonus_score` rather than an invented fixed 200. Existing popup slots,
  depth placement and 60-frame retirement are now visible from pickup paths.
- **S-51 · the attract recording could not complete.** Hardware player palette
  nibbles 12–15 now select the correct hero color variant; centered interaction
  collects the row-straddling potion exactly once; shot-resistant potions are
  removed after pickup; adjacent-player joins use the four-cell ROM search; and
  the recorded Elf reaches the exit instead of dying or stopping below the
  final wall.
- **S-52 · frame inspection lacked a stable reference.** A host-only decimal
  frame counter is drawn in the lower-right status-panel corner after all game
  layers. It deliberately uses host text and is not presented as original art.
  **Superseded by S-123:** the frame now appears only on the separate F1
  diagnostics overview.
- **S-53 · completing the score-bag read path exposed missing writers.** A fresh
  level now seeds the ordinary 100-point bag value. Dragon death creates the
  score bag and randomized hidden potion at its two facing-dependent offsets,
  raises the hint latch, and changes the bag value to 2000. Previously the
  corrected pickup read could award zero because only the thief-return writer
  existed.
- **S-54 · the dragon loot audit exposed two placement corrections.** Mirroring
  a 2×2 dragon needs a one-cell post-mirror anchor correction before reserving
  its footprint. Dragon death now centers the dissolve by eight pixels, applies
  the two loot-offset records cumulatively, and keeps both prizes inside the
  cells just released by the four segments.

### Fifth-pass live-play and host-control audit (S-36 … S-43)

- **S-36 · ordinary exit markers had no render owner.** Exits were excluded
  from the cached terrain and only `exit_open_id` was overlaid, so normal static
  exits disappeared. The playfield overlay now stamps every live EXIT/EXITTO6
  marker and layers the moving-exit animation over its selected cell.
- **S-37 · two-pixel movement could cross a cell boundary before probing it.**
  Certain approach alignments stopped the hero one pixel inside a wall, which
  then made tangential movement look blocked. Each axis is now probed one pixel
  at a time while retaining the ROM's horizontal-before-vertical order; movable
  wall and fight contacts still cancel the entire axis for that frame. The
  first-level wall and attract push sequence both have exact regressions.
  **Superseded by S-137:** the root error was using pixel-derived/generic probe
  ownership. Primary movement now uses the ROM's full-axis private probes.
- **S-38 · projectile palettes were discarded.** `AssetStore.sprite` forced
  every 2x2 projectile through base palette 0. Lobber rocks now use live base
  palette 1; palette slots 12-15 resolve through the character/player colour
  bank, restoring Warrior arrows and the palette-14 demon/Super-Sorcerer shots.
- **S-39 · inventory keys used player-text colours.** Alpha keys and potions now
  use the dedicated KEYPAL/BOMBPAL IRGB ramps from `colors.c`, rather than the
  score/health palette. The exact 0xE000/0xF000 attribute families are recorded.
- **S-40 · enemy shots could not find roaming player records.** The Python port
  kept each hero in its PLAYERSTART record while changing H/V; the ROM migrates
  the record between cells. Shot probes substituted the live player record for
  the logical cell. Player spawn also writes the player index into
  `mob_state_link`, so damage is charged to the actual victim rather than
  player 0. Superseded by S-63, which migrates the record and retires the
  substitution.
- **S-41 · host pause was missing.** P toggles a host-only pause that keeps the
  event/render loop responsive while freezing the 60 Hz simulation.
- **S-42 · first-encounter boxes could not be disabled for testing.**
  `--no-first-encounter-messages` suppresses those alpha boxes and their
  gameplay gate while preserving encounter flags, speech and gameplay effects.
- **S-43 · structural audit.** The 28-call main loop, RAM-shaped `GameState`,
  five-array MOB model, depth chain/SLIPs and subsystem boundaries still map
  closely to the original. The reviewed shared `mob_depth_remove` primitive now
  lives on `MobTable`, maze placement helpers are public bridge APIs, and
  subsystem logic no longer imports gex directly. Python deliberately
  consolidates small C files and renders after simulation rather than writing
  VRAM inline.

### Fourth-pass source/MAME fidelity audit (S-28 … S-35)

- **S-28 · fixed-point scale and camera conversion.** The new original C
  sources and MAME confirm that hardware positions and velocities are `<<7`.
  Player, monster, thief, straight-shot and lobber vectors were converted once
  on import at the time; vertical camera, culling and shot windows use the
  ROM's inverted-V algebra. (S-56 later removed the conversion entirely by
  storing the hardware words themselves.)
- **S-29 · food identities were reversed.** `FOOD000` and `FOOD001-3` heal 100,
  `RFOD001` (0x277B) uses the exact 20-entry adaptive table, and only `PFOD001`
  (0x25ED) poisons for 50. Both destructible and shot-resistant food disappear
  when eaten.
- **S-30 · player collision dispatch was incomplete.** Movement now applies the
  horizontal axis before probing vertical, uses the hero-centre cell bias, and
  preserves `mob_collision_test`'s pass/block/fight contract. Pickups trigger
  once on cell entry; generators and ordinary monsters use the source fight
  tables; locked chests spend a key and reveal their ROM reward; traps remove
  their matching walls; stun floors use the character delay/sound tables.
  Death cannot be meleed, invisible sorcerers reveal before taking damage,
  Super Sorcerers relocate, and thieves are fightable.
- **S-31 · toroidal hardware rendering was clipped.** The playfield and shadow
  rasters wrap at both 512px seams, bottom clamp includes row 31 followed by row
  0, MOB band traversal covers both top and bottom wraps, and the full 336x240
  playfield/MOB raster exists beneath the alpha HUD. The 24px hero's right edge
  is hard-limited to the score-panel boundary.
- **S-32 · the attract recording outran and missed its scripted interactions.**
  Push frames now move only the wall, demo 0xFF records display their 120/150
  frame ROM message boxes, shooting cannot restart while its fixed projectile
  channel is occupied, and the demo follows the key/chest/trap/food/wall,
  transporter, stun-square and exit sequence end to end. Command-boundary
  positions through the opening half were checked directly against MAME RAM.
- **S-33 · maze-placed monsters started with the wrong compass state.** Their
  source direction 4 is converted to gauntpy direction 2 (down), and Super
  Sorcerers begin with the shipped invisible picture/flag outside legend mode.
- **S-34 · dragon footprint reservation was lazy.** Placement now writes the
  three 0x8002 reservation records and initializes the four segment IDs before
  the primary dragon becomes active.
- **S-35 · half the first-encounter text bank was absent.** All 32 message
  records and all 32 speech IDs are now present, including traps, stun floors,
  locked treasure, thief, Death, fake exits and forcefields.

### Third-pass live-play regressions (S-18 … S-27)

- **S-18 · player collision was cell-coarse.** The four movement probes named
  three neighbouring cells but skipped `mob_probe_candidate`'s 0x7C0 per-axis
  position test. A wall in a flank cell therefore blocked an entire row or
  column while the visible hero was still clear. Probes now test the proposed
  H/V anchor, including the software-marker rounding at 0x407EA-0x40834.
- **S-19 · hero geometry used its sprite origin as its logical cell.**
  `player_start_inner` stores a 3x3 hero four pixels left of its 16px cell, so
  tile interaction, thief tracking and monster contact now undo that correction.
  Transport/corner-squeeze landings use the same `cell_x-4, cell_y` origin.
  The renderer also restores the hardware's vertical convention: extra MOB
  rows draw upward, fixing the 8px player/monster collision offset.
- **S-20 · player screen gates were absent.** The exact
  `scroll_hpos_origin`/0x7000 and `scroll_vpos_origin`/0x7400 comparisons now
  prevent entry beneath the HUD and past the bottom edge unless
  `LFLAG4_PLAYER_OFFSCREEN` explicitly permits it. First-player placement snaps
  the camera before input, so level starts and the attract demo are not pinned
  by an uninitialized viewport.
- **S-21 · monster state changed without changing art.** The complete 64-word
  idle/moving/special animation banks at 0x58C0A-0x59635 are literal ROM
  tables. `monster_update_anim_tile` now writes the frame selected by the live
  animation counter and converted compass direction, so monsters turn and
  animate while walking. Contact facing resolves the hero's real MOB record
  (S-63 makes that the cell itself).
- **S-22 · opened doors survived in the terrain cache.** Door logic cleared MOB
  RAM, but the renderer rebuilds static door stamps from `maze.data`. Every
  living-maze clear now replaces that descriptor with `TILE_FLOOR`, which also
  invalidates the content-keyed playfield cache.
- **S-23 · 0x40E66 was assigned to the score multiplier.** Disassembly at
  0x48EE2-0x48F06 proves `{3,0,4,0}` initializes
  `monster_spawn_probability_bonus` for the first active player's class and is
  cleared by later joins. `player_bonusmult` remains at the reset value 1;
  credit initialization also reasserts the 1x/starting-health HUD baseline.
- **S-24 · living terrain updates were incomplete.** The renderer reads
  `maze.data`, not marker MOBs, so the descriptor API now covers doors,
  cyclic/random walls, destructible/secret/movable walls and the escape-timeout
  exit conversion. Removed terrain becomes floor and newly active cyclic/random
  walls are written back, preventing both phantom visible walls and invisible
  solid walls.
- **S-25 · live monster attack art was absent from gex.** The exact demon
  attack, Lobber throw and IT special banks at 0x594B6-0x59635 are now named
  actions in `monsters.jsonc`; every frame resolves through `AssetStore` instead
  of disappearing. A monster that crosses into a new MOB slot also writes its
  current facing/frame there immediately.
- **S-26 · VBLANK hurt feedback and join defaults.** The 0x905F30 timers now
  step 0x12→0x0C→0x06→0 and write the class-specific palette entries from
  0x5B20E+ into live player MOB color RAM, rather than invoking a renderer
  overlay. Paid and free-play joins both
  preserve `player_resetall`'s per-slot character default; `coincheck` had an
  invented Warrior assignment absent from 0x42B6A.
- **S-27 · living-terrain redraws were too expensive and level state leaked.**
  Content changes now restamp only the changed cell and its wrapped adjacency
  ring, reusing the original per-cell floor/wall random choices. A measured
  cyclic/random-wall toggle fell from a 138-198 ms full 512x512 rebuild to a
  2.7 ms median local update (under 4 ms worst observed), without retexturing
  shrub cells elsewhere or clipping the 24x16 movable-wall overhang.
  `select_forcefield_delay_profile` also clears the packed cyclic assignment,
  phase and timer so a prior level's wall map cannot corrupt the next maze.

### Second-pass audit · player and transition lifecycle (S-1 … S-9)

Nine concrete divergences found by re-reading the ROM against the port, all
closed and regression-tested.

- **S-1 · `player_stundelay` was dead state.** Every stun source wrote
  `0x904A54` and nothing read it. `main_move_players` now decrements it and,
  while it is still non-zero, branches to the forcefield check exactly as
  0x4A908-0x4A91C does: no speed lookup, no facing update, no
  `player_try_move`, no tile interaction. The forcefield charge also **moved
  after** the movement call (0x4AA42 follows 0x4AA1E), so walking into a live
  segment is billed on the frame the hero arrives.
- **S-2 · `highscore_check` (0x49D0E) and the death flow (0x46AC4) did not
  exist.** The death path now computes `player_scorepercoin`
  (`calc_score_per_coin`, 0x40628), wipes the slot through
  `player_resetcounters`, ranks the score-per-coin and either opens initials
  entry (rank 0-9, 0x0A8C dwell) or loads the 0x0258 GAME OVER dwell.
  `player_death_sequence` (0x49DE6) is the complete editor: the ±0xA0 velocity
  accumulator, the accelerating repeat delay, `name_entry_step_char` (0x55440),
  the Magic/Fire commit with its 0x78-frame arming gate and the backspace
  glyph, and the `write_high_score_entry` insertion at 0x4A0CA.
- **S-3 · `update_monster_spawn_bonus_from_score_per_coin` (0x48B58) was
  missing.** `monster_spawn_probability_bonus` (0x90405F) now gains
  `(party score >> 14) / party coins` at the level handoff (0x4834E) and a
  re-coin walks a positive value back one step (0x42C30).
- **S-4 · session resets leaked.** `player_resetcounters` (0x43360) and
  `player_resetall` (0x4341E) are implemented, called unconditionally from
  `start_attract_screen` (0x4446E) and from the DEMO arm of
  `start_attract_to_game` (0x4424A), so no inventory, power, timer or status
  survives into an attract screen or a fresh session.
- **S-5 · the status-8 exit animation delay was dropped.**
  `player_exit_sequence` sets status 8 (0x52C66), stands the exit-animation MOB
  up in `SLOT_EXIT_ANIMS`, and the level only ends when the last dissolve
  finishes (0x4A646-0x4A6E6 → 0x4A748-0x4A78C). The port's own death animation
  shares the byte, so `Player.exit_pending` keeps the two tails apart.
- **S-6 · locked treasure was a walk-in pickup.** Type 0x2F goes to the
  unhandled tail (jump table at 0x511CE), so a chest costs no key and pays
  nothing on contact; the supershot arm in `shots.py` owns its destruction.
- **S-7 · `dialog_first_encounter` dropped its numeric value.** Records 8-15
  share ROM line 0x59D80, and the value is now drawn into its gap as a
  two-digit right-aligned field (0x4C63C-0x4C67A): "PLAYER LOSES nn HEALTH".
- **S-8 · a fresh/absent/corrupt EEPROM booted on `game_settings = 0`.** It now
  installs `game_default_settings` (ROM 0x40070 = 0xE090) and synchronises
  `eeprom_settings_cache`, matching `one_time_init`'s bit-12 arm — which also
  means a factory cabinet has attract sound on, as the hardware does.
- **S-9 · the post-loop ran during the attract demo.** The "processed player"
  local is bumped at 0x4A8B4, which sits inside the `game_mode == 0` arm of the
  branch at 0x4A8A2 — the demo arm at 0x4A8F2 reads its joystick through
  `demo_ptr` and rejoins the common path at the stun gate without touching it.
  0x4ACD4 gates the **whole** post-loop on that local, so the port counted
  every active player unconditionally and let `idle_timer` and `escape_timer`
  run on the attract screen: timed doors could open and, after 0x5208 frames,
  the demo maze's walls would have been converted into exits. The counter is
  now written exactly where the ROM writes it, and the key accumulation moved
  to the active tail at 0x4AC8C, so a transporting player no longer counts and
  a stunned key holder still does.

### Second-pass audit · combat, rendering and integration (S-10 … S-17)

- **S-10 · sound fast path:** `sound_play` now sends immediately when the latch
  accepts, queues only on busy/holdoff, and logs each accepted command once.
- **S-11 · marker/MOB fidelity:** exact 0x8000/0x8001 marker words, live-slot
  chain-pointer preservation, solid forcefield hubs, hero spawn geometry and
  hardware-size clipping are implemented.
- **S-12 · player/session tails:** paid/free coin gating, full 32-word health
  table, ADD.L wrap, preserved commit health, high-score/continue lifecycle,
  forcefield clamp/cadence, welcome timing, spawn resets and late-join secret
  eligibility now match the ROM.
- **S-13 · rendering:** Wizard/Sorcerer picture ambiguity, SLIP top-edge culling,
  deterministic playfield RNG, effect/transition dispatch and all hero dissolve
  frames are fixed.
- **S-14 · combat data:** the thief collision table is 64-byte exact; potion
  blasts use the screen cull; generators use all eight wrapped candidates,
  proximity clearance, facing, size and initial art.
- **S-15 · projectile motion:** lobber accumulators, monster shot low-word
  geometry/art/depth and dragon breath channel/tier/counter/picture state are
  implemented.
- **S-16 · dragon pose:** the distinct 32-entry head-table index/sign and the
  16-entry fire-table index are both transcribed and contract-checked.
- **S-17 · core hero animation:** all four players select ROM idle/walk/fight/
  shoot/invisible pictures in the simulation core rather than the host runner.

### Final completion audit · all prior residuals

- **I-05/I-06 effects:** the four shared effect MOBs now have ROM allocation,
  picture cycles, byte aging and release. Kill sparkles and transporter/wall/
  Death dissolves no longer leak channels.
- **I-13/I-15 monsters:** exact contact, aim, culling, ray-march movement,
  animation, Super Sorcerer phases, traversal, lobber arcs and shot cadence are
  implemented and differentially checked against the ROM.
- **I-18 thief:** the route grid, movement/collision/animation engine, escape
  retracing, transporter handling, live-shot dodge, loot drop and rescheduling
  are implemented.
- **Transitions:** treasure rotation/return, moving exits, demo joins, attract
  expiry, bonuses and the complete secret-room challenge loop are implemented.
- **World/render/persistence:** forcefield segments, living walls/doors, dragon,
  exact camera clamps, ROM HUD/dialog/front-end rendering, high scores and both
  maze rotations are implemented.
- **Cleanup:** dead stub infrastructure and duplicated sound helpers were
  removed.

### I-02 · WP-5 · full corner-squeeze geometry

`squeeze_through_check` (0x42744) and the player branch of
`corner_squeeze_geometry` (0x4FEB2) are ported from the ROM. The gate now uses
the real transportability power (word bit 11), `movement_type` recursion guard,
candidate palette/shape exclusions, the `joystick_nibble_to_direction` table at
0x580FC, and the packed neighbour deltas at 0x5B64A/0x5B65C. An invulnerable
player can squeeze past a blocking flank or phase through a one-cell permitted
object; monster, player-start, exit, dragon, treasure-lock, and transporter
shapes reject exactly as in the ROM, including the top-border wrapped-row case.
The successful move uses the asynchronous transporter phase machine (dissolve,
relocate, restore and cleanup). Unicorn probes of the ROM confirmed the
empty-neighbour, one-cell-wall, monster-rejection, and transporter-rejection
outcomes. The directly coupled pickup bug was also fixed: the six temporary
power-ups occupy `player_powers` bits 8–13 rather than overwriting the six
character-upgrade bits 0–5.

### I-08 · WP-16/WP-20 · positioned player spawn

`player_start_inner` (0x48BEC) only recorded a spawn slot; the actual hero
placement lived in the runner. **Fixed:** `player_start_inner` now turns a
PLAYERSTART cell into the hero MOB (the marker MOB `maze.py` placed with the
hero base picture *becomes* the hero — obj_type stays PLAYERSTART so the monster
loop does not move/hurt it), sets facing/`player_in_maze`/`player_tile_pos`, and
skips a start another player already claimed. `main_start_game` now calls it so
a credited player spawns into a loaded maze, unifying the two former
`level_players_active` increment sites (resolves the I-R5 follow-up). Tested in
`test_level_transition.py`.

### I-12 · WP-15/WP-20 · level-transition orchestration

The exit path only set `game_mode = TREAS_EXIT`. **Fixed:** `exits.py` now
implements `player_exit_sequence` (0x52B40), `maze_checknum` (0x52ECA), and
`compute_next_level` (the 0x52DB2 tail) — the next-level/maze arithmetic and
cabinet rotation of doc/06 §3.2/§3.4 — and `show_level_end_bonus_screen`
(0x4D476) commits the computed level/maze, reloads the maze, and re-places the
survivors (via I-08). Tile interaction is wired into `main_move_players`, so
reaching an exit actually advances the level in the runner. Treasure-room
interleaving/rotation and per-player bonus rendering are included and verified
through real maze round trips.

### Front-end session flow · WP-16/WP-20 · attract → coin → select → play

`start_attract_to_game` (0x44204) was a stub that only flipped `game_mode` to
NORMAL, so a coin during attract left the player with no maze to spawn into.
**Fixed:** it now starts a fresh game — clears leftover per-player state (so a
demo hero cannot leak in) and loads **level 1 (maze 0)** via
`maze.reset_and_load_level`, guarded so a ROM-less environment still transitions
mode. `coincheck` falls through after it so the triggering coin also enters that
player into character select (one coin to play). With the maze loaded,
`character_select_input_update` and `main_start_game` (→ `player_start_inner`,
I-08) carry the player from a coin insert through class selection to a spawned
hero. Verified end-to-end through the real `tick()` loop
(`test_level_transition.py::TestFrontEndFlow`). The runner exposes it via
`gauntpy-play --attract` (coin key `5`); `render/host.py` gained the coin-key
edge handler. The title, high-score, legend, and character-select game routines
now write the same alpha VRAM consumed by the compositor's generic alpha pass.
They and the HUD use the **real ROM alpha font** (`gex.alphafont` decodes
`136043-1104.6p`'s 8x8 glyphs; `render/text.py` retains a PIL fallback), so the
text is the cabinet's own characters, not a placeholder. The **DEMO attract
screen** now loads maze 102's MOBs and drops the scripted Elf in
(`attract_demo_init`), so the demo rotation shows a real world; and the
**level-end bonus screen** renders the ROM's per-player
`100 x COINS / TREASURES x / BONUS =` rows (`100 x players x coins x treasures`,
§16; treasures counted by `player_tile_interact`, the world frozen on the
TREAS_EXIT phase) before the next maze loads.

**Resolved (title-logo tiles).** The extracted 96-MOB layout was correct, but
the first reconstruction placed rows by raw packed Y. MAME renders motion
objects at negated Y, so normalizing with `dest_y = max_raw_y - raw_y` restores
the six bands in top-to-bottom order. MAME's `ROM_RELOAD` also confirms gex's
existing 0x2000+ bank mapping already accounts for the rendered-code `^ 0x800`;
no decoder change was needed. `gex/data/title_logo.jsonc` now stores only the
reverse-engineered segment layout, `gex.title_logo` decodes its pixels from the
user's ROMs, and `AssetStore.title_logo` supplies the native 328x48 image to the
full-screen title renderer. The attract-timer-expiry caller at 0x448CE is wired.

### I-23 · WP-13/WP-2 · camera vs renderer scroll convention reconciled

`main_scroll_playfield` writes the ROM's *hardware* scroll registers (X shifted
by the 0x68 centering, Y the *inverted* `0x1E8 − midY − 0x6C`), while the
renderer wants a plain viewport top-left; feeding one to the other put the hero
off-screen, and the runner papered over it with its own `_center_camera`.
**Fixed:** the camera stays ROM-faithful (its tests unchanged), and a single
`camera.viewport_scroll(state, w, h)` recovers the party midpoint the registers
encode and re-centres it for the renderer's viewport, clamped to the 512px maze.
`render_frame` calls it once and hands the result to the playfield and MOB
layers; the runner's `_center_camera` is gone (spawn framing now uses the real
`camera.snap_camera`, and `main_scroll_playfield` inside `tick()` drives the
follow). The exact asymmetric ROM clamps, including bottom geometry, are
covered by tests.

### I-24 · WP-3 · placed-object pictures written at level setup

`maze.py` left every placed object's `mob_picture` at 0, so the runner had to
stamp wall markers and base pictures in two after-load passes. **Fixed:**
`maze._create_generic` now writes each object's picture from the master
`mazeobj_base_picture_tbl` (0x5868C, via gex `objparams.base_picture`) at
placement. That one table already encodes the collision-wall marker (`0x8000`
for solid walls, which `players._slot_is_blocking` reads), real sprites for
movable walls / doors / monsters / items, and the `0x8001` "own-MOB" markers
(left at picture 0). The runner's two passes are gone. **Collision follow-up
done:** `players._slot_is_blocking` now blocks on obj_type too, so movable walls
(real sprite `0x20F6`, not the `0x8000` marker) are solid again; static/trap/
random walls still block via the `0x8000` marker. Forcefield contact uses the
packed segment table rather than treating hubs as beam cells.

### I-R1 · WP-6/WP-11 · `forcefield_live_color` / `forcefield_color` conflict

WP-6 added `forcefield_live_color` to state.py's WP-11 block before WP-11
landed; WP-11 independently added `forcefield_color` for the same RAM address
(0x904046). **Fixed:** removed `forcefield_live_color`; kept `forcefield_color`.

### I-03 · WP-7 · Monster kill condition (resolved from the docs)

Was implemented as `new_health ≤ 0` (4 damage-1 hits for a ghost) per an
erroneous task brief. §26, PLAN §26, and book §11 all specify the live window
`[base-2, base]`, and potions.py already implemented it. **Fixed:** shots.py now
destroys a monster when the hpos nibble drops below `base-2` (a ghost spawned at
base 4 dies in 3 hits); `test_shots.py` updated. Ground rule 8 (doc wins).

### I-07 · WP-5/WP-13 · `player_tile_pos` / `player_in_maze` ownership

The camera was deriving these arrays itself. **Fixed:** `main_move_players`
(WP-5/6) now maintains them each frame from the player's pixel-derived current
cell, and `main_scroll_playfield` only reads them. The isolated camera tests set
the arrays directly.

### I-14 · WP-8 · Super Sorcerer placement

Was re-aim only. **Fixed:** `supersorc_place` now performs the documented
relocation — all four players cyclically, three directions behind facing (biases
{0,−1,+1}, clear runs {4,3,3}), rows 1–31, with an eight-cell proximity
rejection — relocating the MOB via `move_slot`. Covered by a new test.

### I-16 · WP-14 · `mob_effect_anim_counter` byte wrap

**Fixed:** `main_score_update` now masks the increment with `& 0xFF`.

### I-R2 · scan · Player current-cell contact used the stale spawn slot

Players kept a fixed record `mob_slot` and roamed via `hpos`/`vpos`. Monster and
thief contact checks compared against `player.mob_slot`, so a moved player could
only be hit at their **spawn** cell. **Fixed:** `monsters._player_in_cell` and
`thief._overlaps` derived the player's current cell from pixel position.
Regression test added (`test_contact_uses_current_cell_not_spawn_slot`).
Superseded by S-63: the record migrates, so `player.mob_slot` *is* the current
cell and both helpers ask the cell directly.

### I-R3 · scan · Players never died

`main_health_countdown` drained health into negative values but nothing
transitioned a player to `DYING` at zero, so a dead player kept playing forever.
**Fixed:** `main_move_players` now transitions an active player with
`health ≤ 0` to `DYING` (clamps health to 0, resets timers, decrements the
active count, plays the low-health cue). Two regression tests added.

### I-R4 · scan · Joystick direction bits were wrong (input.py / WP-5)

`input.py` and the inlined constants in `players.py` placed the four directions
at bits 2–5, which read the unconnected spare lines (bits 2–3) for UP/DOWN and
swapped LEFT/RIGHT. `05_data_reference.md` §3.11 (and §6.2 demo format, §22
character select) put directions at bits 4–7: RIGHT=4, LEFT=5, DOWN=6, UP=7.
**Fixed:** corrected `JOY_UP/DOWN/LEFT/RIGHT` (and `JOY_DIRECTIONS = 0xF0`) in
`input.py` and the inlined `_JOY_*` in `players.py`. The movement tests passed
before only because both sides shared the same wrong constants; new tests drive
the raw-word → `direction_bits` → `player_try_move` path directly. This
supersedes the former note N-01, which wrongly called both layouts correct —
`session.py` and `attract.py` had the right bits all along; `input.py` was buggy.

### I-R5 · scan · `level_players_active` was never decremented

The active-player count was incremented only in `player_start_inner` and never
decreased. **Fixed:** the death transition (I-R3) decrements it (guarded at 0),
and `main_start_game` increments it on join so the live join/die paths balance.
The two increment sites are unified when I-09's full spawn path lands.

### I-R6 · WP-10 · Thief wealth power-bit constants were wrong

`thief._player_wealth` had `_POWER_SPEED`, `_POWER_MAGIC`, and `_POWER_FIGHT`
pointing at the wrong bits (FIGHT, REFLECT, and MAGIC respectively). The
Character Powers enum (`05_data_reference.md` §3, 0x9048E0) is
SPEED=0, ARMOR=1, FIGHT=2, SHOTSPEED=3, SHOTPOWER=4, MAGIC=5. **Fixed:**
corrected all six masks and added a targeting regression test. (Resolves the
former Q-2 — the layout was documented after all.)

### I-R7 · WP-6 · forcefield damage was charged to every player unconditionally

`main_move_players` applied forcefield contact damage to every active player on
every frame the field colour was lit, with no check that the player was
actually on a forcefield — so a hero standing still in any maze with a lit field
lost ~1 HP/frame and died in seconds. The disassembly of the call site
(0x4AA42-0x4AA68) shows the damage is gated on a zero `acid_timer` **and** a
non-zero `check_forcefield_collision` (0x53346). **Fixed:** added a minimal
`_check_forcefield_collision` (player's current cell holds a `FORCEFIELDHUB`)
and the acid gate; the forcefield test now stands the player on a field cell,
and a new test asserts a lit field off the field deals nothing. Surfaced by the
playable runner (a level-1 hero was dying while idle).

### I-04/I-11/I-13/I-17/I-19/I-20 · ROM tables transcribed from row76.bin

The six blocked ROM tables were transcribed directly from the game ROM
(`row76.bin`, which maps game address `A` to file offset `A − 0x40000`,
big-endian; verified against the known `forcefield_damage_table` at 0x5813C and
the `maze_checknum` prologue probe). Each table is now a literal in the code
with its ROM address in a comment, verified byte-for-byte against the ROM:

- **I-19 `potion_effect_matrix` (0x5DA98, 448 B)** — real 28×16 matrix in
  `potions.py`. It confirmed every documented invariant *and* replaced the
  "always kills" placeholder with real per-character damage: a Warrior potion
  weakens a Ghost 4→2 (survives); Wizard/Elf/enhanced destroy it; an Elf potion
  demotes GEN_GHOST3→GEN_GHOST1. Tests updated to the real outcomes.
- **I-17 dragon path programs (0x5D578, 5×16 B)** plus `dragon_fire_segment_tbl`
  (0x5D4B8) and `dragon_head_pics` (0x5D528) — real programs in `dragon.py`,
  selected by `dragon_path_num`. Tests updated to program 0's fire positions.
- **I-13 `monster_contact_damage_table` (0x57A2E, 64 words) — tier-exact for the
  melee families.** Disassembly of `monster_playerhit` (0x495A6) + its 10-way
  jump table (0x49620) gave the exact recipe: `row = (hpos & 0xF) −
  mazeobj_hsize_tier_tbl[type] + 2 + per_type_offset`, then
  `damage = table[row*4 + character (+0x20 armored)]`. **Implemented** for the
  types whose behaviour is unambiguous: Grunt/Demon/Sorcerer/Aux-Grunt (offset
  +3, `_CONTACT_ROW`) now scale contact damage with the monster's live strength
  tier; **Ghost** (offset +0) additionally removes itself on contact (the kill
  path — ghosts explode); **Lobber** deals **no** contact damage (its handler is
  the empty epilogue 0x49A32 — only its thrown shots hurt). Acid, Super
  Sorcerer, Death, windup and kill scores are all implemented and verified
  against ROM execution.
- **I-04 `shot_damage_base_tbl` (0x596B6), `shot_damage_rand_tbl` (0x596C2),
  `monstshot_damage_tbl` (0x596CE)** — real bytes and exact row selection in
  `shots.py`. The
  transcription also surfaced two bugs, fixed here: the rand classes are {2, 8}
  (the code had {2, 10}), and the shot-power upgrade bit is 0x10 / POWER_SHOTPOWER
  (the code had 0x1000).
- **I-11 treasure countdown speech (0x5AB64, 11 longwords)** — real speech IDs
  in `exits.py`; `_countdown_speech` now speaks the number each second.
- **I-20 demo streams (0x5818C/0x581C4/0x5825A/0x5825C)** — real recorded input
  streams in `attract.py`; `attract_demo_init` installs them and selects the
  player-1 Elf. Full 0xFE joins/stream switching and the attract-sound option
  are implemented.

### I-01 · WP-5 · Player speed — resolved by disassembly

Was a flat 2 px/frame guess. Disassembly of `main_move_players` (0x4A92C-0x4A942)
showed the speed is read from `player_speed_normal` (ROM 0x580A8, transcribed
into `players.py`) at index `character + 4 × extra-speed-power`: base
Warrior/Valkyrie/Wizard = 0x80 (**2 px**), Elf = 0x100 (**4 px**), and the
extra-speed power (POWER_SPEED_BIT 0) raises everyone to 0x100 (4 px). **Fixed:**
`player_try_move` now uses per-character speed and the `player_anim_rate`
0x580B8 boost; regression tests cover both.

### I-10 · WP-15 · Moving-exit timer — resolved by disassembly

Was 0x78 ("approximate"). Disassembly of `main_exit_move` showed the game's
`exit_move_timer` (0x904A08) is loaded with **#0x12C (300 frames)** both at level
setup (0x43B90) and on reload (`move.w #0x12c,(a0)` at 0x52A74). The
disassembly also confirmed the ExitMoves gate is `level_flags & 0x4000`
(= `level_flags_3 & 0x40`, as implemented) and the relocation plays sound 0x31.
**Fixed:** `_EXIT_MOVE_TIMER_RELOAD` and the state default are now 0x12C; the
reload-value test updated.

### I-09 / I-21 / I-22 · subsystem-isolation rule lifted, cross-imports wired

The subsystem-isolation rule (subsystems never import each other) existed only
to keep parallel subagents from colliding; with that constraint removed, the
three issues that were purely a missing cross-import are fixed:

- **I-09 · WP-16** — `main_start_game` now calls the real
  `players.player_join_finalize` (setting `ALIVE_HERE` and running the join
  speech / HUD hook) instead of a bare status assignment. The first-player bonus
  and `level_players_active` accounting are preserved; the MOB spawn
  (`player_start_inner`) still needs a maze (I-08).
- **I-21 · WP-20** — `one_time_init` now calls `eeprom.eeprom_load_settings`
  (config load, §5 step 6) and hands off through the real
  `attract.start_attract_screen(TITLE)`, dropping the duplicated timer constant.
- **I-22 · WP-8/WP-7** — `monster_playerhit` now calls
  `shots.death_damage_accumulate` (made public) on Death contact, adding 4 (or 3
  with the armor power) to the per-player counter and dismissing the Death MOB
  past 200 — so Death is killable by contact, not only by supershots. Two
  regression tests added.

---

## Notes (not bugs, but worth remembering)

### N-02 · WP-7 · `player_create_shot` — implemented (firing)

**Resolved.** `player_create_shot` now spawns a shot in the firing player's
fixed channel (slot `player_index + 1`, in `SLOT_PLAYER_SHOTS`), seeding
`shot_dx/dy` from facing and gating on a free channel so a held Fire button
fires one shot at a time; the shot-speed power (bit 3) raises the speed. It
mirrors `monsters.monster_create_shot`. Tested in `test_level_transition.py`.
**Velocities now exact:** `_SHOT_VELOCITY` is transcribed from the ROM
`shot_velocity_x/y` tables (0x576E2/0x57792) — base rows 0-7 and the
shot-speed-power rows 8-15 — mapped by `_DIR_TO_SHOT_ROW`. This corrected the
diagonal speed: the ROM moves diagonals 0x100 (4 px/axis) vs cardinals 0x180
(6 px), where the old delta×speed model moved diagonals 6 px/axis (too fast).
The character shot sounds (Axe/Sword/Fireball/Arrow), projectile animation,
monster velocities and lobber arcs are implemented.

### N-03 · players.py · shadowed `@stub player_try_move` placeholder

**Resolved.** The isolation-era `@stub def player_try_move` and its now-unused
stub import were removed; only the real WP-5 implementation remains.

### N-04 · isolation-era duplication cleanup

**Resolved.** Subsystems now share `sound.sound_play`; the duplicated local
queue helpers and dead isolation-era stub marker are gone.

### N-05 · `play.py` · the playable runner and its remaining gaps

`gauntpy.play` (`uv run gauntpy-play`) is a minimum playable runner: it loads a
maze, drops a hero in (via the real spawn path, I-08), and drives the real
`game_frame` at 60 Hz in a pygame window with keyboard movement, genuine wall
collision, HUD, and health drain. The hero renders with its **real class
sprite** (gex's `heroes.jsonc`; see N-06); pictures come from `maze.py` now
(I-24) and the camera is the real `main_scroll_playfield`, converted to the
viewport by the compositor (I-23 — the old `_center_camera` workaround is gone).
Item pickup, firing (N-02),
and **level-to-level exits (I-12)** all work — walk into an exit and the next
level loads, so the runner now spans multiple levels. The **front-end flow**
works too: by default the runner drops mid-level, but `--attract` boots through
`one_time_init` → attract and lets you insert a coin (key `5`), pick a class,
and press Magic to start, driving the genuine `coincheck` →
`character_select_input_update` → `main_start_game` → spawn path (see the
"Resolved · front-end session flow" entry). The attract, high-score, legend,
and character-select routines write alpha VRAM rendered in the **real ROM alpha
font**, so `--attract` shows arcade-faithful text throughout, not a dark
window; the DEMO attract screen shows a real maze, each exit plays a "LEVEL
COMPLETE" bonus tally, and the title uses the ROM-native pixel wordmark. It is
the integration harness that surfaced I-R7, I-23, and I-24 — all now resolved.

### N-06 · gex sprite-data coverage (complete)

gex's `data/` now carries every table gauntpy needs to render the game world,
all extracted from the ROM (doc/04 §8, doc/05 §5–§8) and consumed by
`assets.py`. An audit confirms **every placed maze object type (0–63) resolves
a sprite** (the two `0x8001` marker types, EXIT/TRANSPORTER, render via their
own animated MOBs by design):

- **Monsters** — all ten families, **walk + idle** (`monsters.jsonc`; idle from
  the 0x40DB2 pointer table, equals walk for the four NULL-moving families).
- **Heroes** — four player classes, walk/idle/fight/shoot (`heroes.jsonc` +
  `heroes.py`, per-class palette).
- **Thief** (mugger reuses it) — walk/idle/walkcompact (`npcs.jsonc` +
  `npcs.py`).
- **Projectiles** — three shot tables, 2×2 sprites (`projectiles.jsonc` +
  `projectiles.py`, tile set + `projectile_stamp`).
- **Dragon** — head/body/pose/delta tables and runtime four-segment composition
  (`dragon.jsonc` + `dragon.py`).
- **Effects** — score-popup / floating-star picture tables (`effects.jsonc` +
  `effects.py`, 3×3 `star_stamp`).
- **Object parameter tables** — the four master 64-entry tables
  (`objparams.jsonc` + `objparams.py`: `base_picture`, `hpos_correction`,
  `vpos_offset`, `hsize_tier`, 0x5858C–0x5870B). **`base_picture` is the key
  addition**: it maps each object type to its picture, which is what lets
  gauntpy set `mob_picture` on decoded maze objects (previously always 0) so
  items, treasure, keys, potions, power-ups, and generators all render.
- **Items** — full pickup stamps already present; `items.py` now also exposes
  `item_stamp_for_picture` / `ITEM_PICTURE_INDEX` so a placed object's picture
  resolves straight to its stamp.

gauntpy's `assets.sprite()` dispatches pictures across projectiles, dragon
segments, effects, typed creatures/heroes/NPCs, items and sized raw ROM blocks.
The base-picture pass now lives in its proper
home — `maze._create_generic` writes each object's picture at placement (I-24) —
so decoded objects render end to end without any runner-side stamping. The
picture→sprite index uses explicit entity-kind disambiguation where art is
shared (notably Wizard/Sorcerer), so each MOB keeps the correct palette bank.

### Q-1 · Environment · pytest tmp-dir permission errors — RESOLVED

`test_eeprom.py` and `test_render.py` used to error with
`PermissionError: [WinError 5]` when pytest built its default `tmp_path` base on
`W:\zTEMP\TEMP` — an environment ACL quirk, not a code defect. **Fixed by the
environment owner;** the suite now runs clean with no `--basetemp` workaround.

### Q-2 · WP-6 · Distinct player-death sound

**Resolved.** Death uses the character-specific ROM commands 0x14–0x17
(Warrior/Valkyrie/Wizard/Elf).
