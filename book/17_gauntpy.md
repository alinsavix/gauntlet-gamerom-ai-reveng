# 17. Gauntlet in Python

A thief follows you around a corner. From the game screen, you can see
the pursuit; from a route display, you can see the directions you left
behind. Pause the action and those two pictures become a question you
can investigate. Which cell is the thief following now? Did your last
turn change its route, or has it already committed to the next cell?

`gauntpy` is this book's playable companion: a Python reconstruction
with controls for looking behind the screen. It does not execute the
68010 instruction stream or reproduce the board's electrical timing.
It implements the documented operations in Python. That makes its state
accessible, but also establishes a boundary around its evidence. Watching
the reconstruction follow a trail demonstrates what this model does,
not independently what the original ROM does.

We will start in an ordinary ROM maze, inspect the thief's preparations,
and preserve a moment worth returning to. Only then will we replace the
maze with a deliberately simplified experiment.

## Getting a window

You need Python 3.12 or newer, `uv`, this repository, the local
`python-gex` package, and your own matching ROM files. Here, “sibling”
means that `gauntpy` and `python-gex` sit beside one another inside the
repository root. The dependency configuration resolves `gex` from
`..\python-gex`; installing an unrelated package with a similar name is
not a substitute.

Neither the ROM images nor the optional ROM-derived sound recordings
are distributed here. The root [ROM appendix](../README.md#appendix-roms)
identifies the program and level images. The
[gex ROM list](../python-gex/README.md#tested-roms) also covers the graphics
assets needed to draw the game. Having enough bytes to decode a maze
does not necessarily mean that the renderer has its sprite and font data.

From the repository root, in PowerShell:

```powershell
python --version
uv --version
Test-Path .\python-gex\pyproject.toml
Set-Location .\gauntpy
uv run --all-extras gauntpy-play
```

The path check should return `True`. If it does not, restore the local
package checkout before continuing. `uv` supplies the project environment
and its optional rendering dependencies, including Pillow and pygame-ce;
there is no separate virtual-environment activation step. The first run
may need to resolve and install those dependencies.

The runner finds a `ROMs` directory at the repository root. To use another
directory, set its absolute path before launching:

```powershell
$env:GEX_ROM_DIR = 'D:\Games\GauntletII\ROMs'
uv run --all-extras gauntpy-play
```

That is an example location: substitute the directory containing your own
files. These and all subsequent commands assume the terminal is in
`gauntpy`. A missing-ROM error is a reason to check the file list and
directory, not to look for a switch that generates replacement assets.

The default drops an Elf directly into play at four-times display scale.
Arrows move, Ctrl or Space fires, and Alt or Enter uses Magic. Press `5`
to insert a coin and `P` to pause or resume. The first connected gamepad
can provide the same controls: D-pad or left stick moves, A fires, B uses
Magic, Back inserts a coin, and Start pauses. Keyboard and gamepad inputs
can be mixed. They reach the modeled input word before the game's
debouncing and player routines consume them.

Direct play skips the front-end journey. To take that journey instead,
close the window and run:

```powershell
uv run --all-extras gauntpy-play --attract
```

Insert a coin, choose a class with the arrows, and commit with Enter,
the Magic control. This enters through the modeled attract and
character-selection paths. It is a different starting state, not a title
screen pasted in front of the direct-start game.

## Looking farther without walking farther

For our ordinary-maze investigation, use:

```powershell
uv run --all-extras gauntpy-play --level 115 --maze 3 --character elf --keys 3 --potions 2 --seed 0 --full-playfield
```

The two numbers answer different questions. `--maze 3` fixes the stored
layout; `--level 115` supplies the depth consulted by level-dependent
rules. Without an explicit maze, the runner uses the game's maze
selection, including rotation after the opening levels. Fixing both
avoids confusing a different layout with different rules on familiar
ground.

The keys and potions are host-supplied starting inventory, not items we
have earned. This is an ordinary ROM layout under a declared experimental
setup. The high depth makes thief scheduling eligible without depending
on a low-depth appearance roll; it also affects other depth-sensitive
behavior. It does not promise that a visitor will reach a living player
at a particular wall-clock time.

`--full-playfield` shows the entire 512-by-512 world beside the gameplay
status panel. A white outline marks the ordinary 232-by-240 camera
viewport, splitting at wrap seams when necessary. The extra view belongs
to the host. It does not move the camera, enlarge the area used by
camera-dependent rules, or let players walk beyond their normal shared
screen constraints. Seeing an enemy outside that outline is not the
same as bringing it into the gameplay viewport.

This view defaults to native scale; add `--scale 2` if you have room.
Screen-wide text overlays are omitted, so return to the normal view for
title screens and captions. A dialog can still affect the simulation
even when this inspection view does not draw its box.

The seed fixes the initial random stream, not everything that happens
afterward. Moving differently changes encounters and later random
consumption. For another starting stream use `--seed 1234`; `--seed random`
asks the host to choose one. A useful report records the setup and
subsequent actions, not just “seed zero.”

For other focused tests, repeated `--power` options can supply temporary
powers such as `--power reflective-shots`. Inventory and power setup
options require direct play, not `--attract`. `--reduce-text` is different:
it selects the ROM's shorter advice path during normal play rather than
granting a resource. Most first-encounter messages disappear; retained
food advice is shorter. Attract mode retains its messages, but their
dialog duration also falls from 150 to 120 counts with Reduce Text.
Leave this switch off for the exercise so its dialog behavior remains
part of the stated starting conditions.

## Three places where a frame happens

Before opening the diagnostics, separate the game from the machinery
used to observe it.

`GameState` holds modeled working state: players, timers, maze data,
random state, and display memory. Its motion objects retain five
parallel arrays of native-format words. A moving monster can migrate
between cell-indexed records rather than remain one permanent Python
object. Packed positions, bit fields, and explicitly masked arithmetic
preserve relationships that ordinary unconstrained Python integers would
not preserve automatically.

The main loop advances this state through the ordered subsystem calls.
Calling `tick` performs a modeled frame; it does not wait for the next
sixtieth of a second. Game-side presentation routines also write modeled
playfield, alpha, and color memory. The alpha layer is the game's text
and overlay plane, not the host diagnostics panel.

The renderer then reads that display memory and combines it with
ROM-derived graphics to make pixels. Asset acquisition is separate from
game decisions: `gex` decodes artwork, while game-side maze setup still
chooses placements and consumes randomness. The renderer should not
decide where a potion belongs merely because it knows how to draw one.

Finally, the host owns the window, input sampling, pacing, sound playback,
and inspection controls. Its normal limiter targets sixty frames per
second. These boundaries let the same game state run without a window,
appear at different scales, or be inspected without adding debug text
to the game's own video memory.

They also help locate a disagreement. If a potion exists in the logical
maze but its display word is wrong, presentation needs investigation.
If the modeled display word is right but the pixels are wrong, look
farther along the rendering path. A screenshot alone cannot tell those
cases apart.

## Finding the thief before it arrives

Press **F1** to open diagnostics and **P** to pause while reading.
F1 alone does not pause play. **F2/F3** move backward and forward through
the pages; use their names rather than counting key presses.

Start with **OVERVIEW**. Confirm level, maze, mode, camera, and frame
number. On **PLAYERS**, check the Elf's health and supplied inventory.
The page also decodes raw inputs, useful when an apparently stubborn
hero is actually receiving a held control. Release movement and attack
keys before unpausing.

Next visit **LEVEL** and **FLAGS**. These distinguish running timers and
depth gates from the raw and decoded maze flags. They keep “the thief
has not appeared” from becoming a diagnosis by itself. An early level,
a secret-maze exclusion, a pending arrival, and an occupied deployment
cell are different situations.

Move to **AI**. The following values were checked by building the
command's direct-start state headlessly, before its first frame. They
are a textual reference, not a captured window; your interactive frame
will already have advanced by the time you pause.

| AI row at direct setup | Value | What it lets us conclude |
|------------------------|-------|-------------------------|
| `THIEF MODE` | `1` | Pursuit is selected, but this alone does not establish that a body exists. |
| `THIEF MOB` | `000` | No deployed thief record yet. |
| `THIEF VICTIM` | `0` | The target is player index zero, the first player. |
| `THIEF ENTRY` | `1380 speed=512` | An arrival countdown is armed; speed is a native position-word value, not 512 pixels per frame. |
| `THIEF POS` | `000>000>000` | The visitor has no active previous/current/next-cell sequence yet. |

The initial 1,380 counts correspond to 23 seconds at sixty eligible
countdown updates per second. Host pause, game-side gates, and deployment
conditions prevent treating that as an appointment. In particular, the
arrival starts from the victim's earlier cell. Remaining on that cell
can obstruct deployment instead of providing a convenient demonstration.

Unpause and walk away from the starting position along a clear route.
Make a recognizable turn if the layout permits. Keep the hero alive,
using ordinary combat or another coin if necessary, and do not leave
the level. You are not merely waiting: the selected victim's movement
writes the trail that makes the later pursuit intelligible.

Return to **ROUTES**. Two grids separate **LOW PURSUIT** from **HIGH
ESCAPE**. Each route byte contains two four-bit fields, called nibbles.
The low field records pursuit directions; the high field retains reverse
directions written during the visitor's outward journey. Colors encode
directions according to the page's compass legend. These are route data,
not a second rendering of walls.

The boxed markers mean `C=current`, `N=next`, `S=start`, and `V=victim`.
Before deployment, do not mistake unset visitor positions for an actor
waiting at the top of the map. Look instead for the victim marker and
the trail behind the route you just walked. A populated pursuit grid
with no thief body is meaningful: preparation precedes arrival.

If the visitor deploys, pause again. On **AI**, read `THIEF MOB`, then
visit **ACTORS** and use **[ / ]** to select that occupied slot. The
selected record exposes `PICTURE`, `HPOS`, `VPOS`, `LINK`, and
`STATE/LINK`; decoded pixel coordinates sit beside the raw position
words. This connects the visible visitor to
[the five-array record](06_a_world_in_ten_bytes.md), rather than merely
recognizing its sprite.

Do not use the decoded object-type label alone to identify it: the thief
deployment uses the `PLAYERSTART` object type. Its specialized state and
the `THIEF MOB` pointer supply the missing identity. After movement,
consult that pointer again. The record can migrate, so a selected slot
is not a permanent tracking tag attached to the thief.

Now compare the two pages around short stretches of resumed play.
`THIEF POS` gives previous, current, and next packed cells; the route
markers locate them spatially. The interesting question is whether the
next cell follows the victim's trail, not whether the visitor always
points directly at the hero. After theft, the escape mode reads the
other half of the route bytes. Changing direction then has an explanation
in state, rather than requiring a new story about the sprite.

This is an inspection procedure, not a promised sequence of encounters.
A mugger uses the same machinery with different behavior; a killed or
blocked visitor may not complete the sequence. Capture whichever
transition actually occurs. If nothing arrives, inspect the timer,
target, and deployment location before changing the experiment.

## Keeping the useful moment

While paused at a useful state, press **F4**. The terminal prints the
JSON filename saved under `traces\state-dumps`. Record what you were
trying to observe and which host interventions you used. “Before the
turn” is more useful when paired with the level, frame, and visitor slot.

F4 saves the complete modeled state, including players, MOB arrays and
links, logical maze, display memory, route grids, timers, inputs, and
RNG state. It is much more than the compact diagnostic view. Files are
versioned; incompatible state shapes are rejected rather than silently
loading only the fields that happen to match.

Close the window and resume with the filename printed by your run:

```powershell
uv run --all-extras gauntpy-play --load-state .\traces\state-dumps\your-capture.json --full-playfield --scale 1
```

Replace `your-capture.json`; it is not a supplied example file. Display
options can change because they do not rebuild the saved maze. Do not
append `--level`, `--maze`, `--character`, `--seed`, `--attract`,
`--scenario`, or inventory/power setup options. Resume already has its
starting state and rejects those competing requests.

Loading does not boot or run level setup again. It also does not replay
future controls: once resumed, new host input continues the experiment.
The host's `P` pause is not itself a modeled game field, so be ready to
pause the new window. Matching a saved frame does not guarantee that two
people will produce matching frames afterward.

Resumed sessions restore the captured EEPROM device image into isolated
memory and suppress external EEPROM-file writes. Loading an old encounter
therefore does not roll newer saved settings, scores, or rotation back
on disk. The game's EEPROM timer and accepted in-memory device writes
still operate; isolation is a host persistence policy, not frozen game
logic.

The **EVENTS** page serves a different purpose. Its rolling history
infers changes between diagnostic snapshots while the panel is open.
It is neither a complete instruction trace nor a history reconstructed
from before you opened F1. Use it to notice a transition, then keep the
full F4 state when the exact surrounding conditions matter.

## Starting the level again is not loading that capture

**F11** restores an in-memory checkpoint captured after direct-start
setup, or at the end of the first frame completing a new playable
level's setup. It restores the actual placed pickups, players, video
memory, timers, and random state. It does not ask the maze loader to
make another version that merely looks similar.

That makes F11 useful for trying a different turn before the thief
arrives. Every new playable level replaces the checkpoint, including
treasure and secret rooms. Attract screens and new-level splashes have
no usable checkpoint. After `--load-state`, F11 remains unavailable
until the next new level: an arbitrary mid-level capture cannot tell
the host how its level began, and F4 does not include that checkpoint.

Rewinding preserves `P` pause, clears diagnostic history and F8's room
timer hold, and displays the restored frame before continuing. Current
audio stops; historical speech or music is not rebuilt from the middle.
EEPROM writes remain isolated from the local file for the rest of
the run.

The neighboring function keys make more selective changes. **F5** skips
through the next level's normal splash using live maze rotation.
**F6/F7** grant one key or potion to the host player, updating inventory
and its display. These are useful for reaching a door or testing Magic,
but a comparison must acknowledge the granted resource.

**F8** holds only the treasure/secret-room timer. Movement, combat, and
other frame work continue; it is not an alternative to `P`. **F9** arms
the current maze's secret objective through its setup path, including
normal solo-party cancellation, so the trick still has to be performed.
From level six onward, **F10** forces the selected live player to qualify
for a secret room on exit; the exit and handoff still run. Neither key
demonstrates that an ordinary player earned qualification.

## Removing everything except the question

After the ordinary-maze exercise, a smaller space makes route behavior
easier to compare. An existing fixture supplies it:

```powershell
uv run --all-extras gauntpy-play --scenario .\scenarios\narrow-lane-thief.gsc --full-playfield
```

This is explicitly **synthetic**. Despite the filename, its scheduled
visitor is a mugger. The file specifies an Elf with 5,000 health, seed
zero, an open area divided by a wall with a one-cell gap, and an
`activate_thief 1 16 mugger` event at modeled frame 1,200. The coordinates
name the deployment cell; they are not the player's position.

The helper arms the victim and countdown at construction and builds an
initial traversable pursuit trail from that deployment point to the
player. Ordinary movement can then extend the trail before arrival.
This supplied bridge is an important intervention. It avoids waiting
for ordinary setup to produce our desired geometry, but cannot establish
that an original maze would produce the same trail.

Open **SCENARIO** to see the fixture name, content hash, live input mode,
and pending event with its remaining frame count. Let the player stand
still for a baseline, or make a deliberate route before the event.
Avoid exiting if you want to study this encounter. Then use **AI**,
**ACTORS**, and **ROUTES** as before. F11 returns to the captured fixture
start, including event progress; F4 embeds its normalized definition and
progress so resume does not depend on the `.gsc` file remaining unchanged.

For a repeatable no-window baseline:

```powershell
uv run gauntpy-scenario run .\scenarios\narrow-lane-thief.gsc --every 60 --output .\traces\scenarios\narrow-lane-thief.json
```

The file's default run is 1,500 frames. The headless runner supplies no
live movement, so this is the stationary baseline, not a replay of your
keyboard session. Its JSON identifies the result as synthetic and
contains 26 samples: setup plus every sixtieth frame. The compact digest
includes player, camera, and selected subsystem state, not every route
byte or thief field. Use F4 for a resumable full state; this trace file
is not accepted as one.

Repeatability here lets us isolate a question in the reconstruction.
Proving that answer for the original game still requires the ROM or
matched original execution.

## Hearing and timing the host

Audio is off by default. With `--sound`, accepted commands drive local
`sounds\0xNN_description.wav` recordings, or a library selected through
`GAUNTPY_SOUND_DIR`. A missing requested library produces a warning and
silent play. The **AUDIO** page still names the twelve most recently
accepted commands without recordings, which separates “the game asked
for sound” from “the host played it.”

Playback implements queue priorities, replacement, loops, and fades. It
does not emulate the 6502 or synthesize the sound chips. A premixed WAV
cannot separate individual instrumental parts when only some hardware
channels should be suppressed. Muting playback leaves modeled command
production intact; hearing a plausible mix is not proof of sound-board
equivalence.

For a host-performance comparison, use a fixed workload:

```powershell
uv run --all-extras gauntpy-play --benchmark 600 --workload benchmark-mobs
```

This is a graphical benchmark, not another headless trace. It measures
600 frames after warm-up, disables the limiter, sound, and external
EEPROM writes, and uses a named synthetic monster workload. Input,
complete game update, raster composition through window blitting, and
display flip are separate timing boundaries. The complete-loop row is
cumulative: do not add it to the others as another independent cost.

Compare like workloads, scales, and machines. The **PERFORMANCE** page
can reveal render-time spikes, but a slow renderer is not evidence that
the original monster routine exhausted its CPU budget. `--uncapped`
likewise removes the host wait and disables playback while retaining a
complete game update per rendered frame. It accelerates the companion,
not the historical processor.

The most useful result of these controls is a precise question: a saved
state, an identified field, and an action whose consequence you can
explain. That gives us something concrete to take back to the ROMs.

### Source notes

- Installation, controls, and option contracts:
  [gauntpy README](../gauntpy/README.md#play-it),
  [dependency configuration](../gauntpy/pyproject.toml), and
  [command parser](../gauntpy/src/gauntpy/host/application.py).
- Game/render/host boundaries:
  [state](../gauntpy/src/gauntpy/state.py),
  [MOB arrays](../gauntpy/src/gauntpy/mob.py),
  [main loop](../gauntpy/src/gauntpy/mainloop.py),
  [compositor](../gauntpy/src/gauntpy/render/compositor.py), and
  [host shell](../gauntpy/src/gauntpy/host/shell.py).
- The direct-start reference uses
  [startup](../gauntpy/src/gauntpy/host/startup.py),
  [thief setup and routing](../gauntpy/src/gauntpy/subsystems/thief.py), and
  [diagnostic row definitions](../gauntpy/src/gauntpy/host/diagnostics.py).
  [Chapter 11](11_the_thiefs_trail.md) explains pursuit and escape.
- Advice selection and dialog durations:
  [message routines](../gauntpy/src/gauntpy/subsystems/score.py).
- Capture and replay boundaries:
  [state dumps](../gauntpy/src/gauntpy/host/state_dump.py),
  [level restart](../gauntpy/src/gauntpy/host/level_restart.py), and
  [EEPROM host policy](../gauntpy/src/gauntpy/host/eeprom.py).
- Synthetic example:
  [fixture](../gauntpy/scenarios/narrow-lane-thief.gsc),
  [format and event semantics](../gauntpy/scenarios/README.md),
  [fixture construction](../gauntpy/src/gauntpy/custom_scenario.py), and
  [headless runner and digest](../gauntpy/src/gauntpy/scenarios.py).
  The 1,500-frame stationary run was checked without launching a GUI.
- Playback limitations and measurement boundaries:
  [audio host](../gauntpy/src/gauntpy/host/audio.py) and
  [performance workloads](../gauntpy/src/gauntpy/performance_workloads.py).

[Previous: Waking the cabinet](16_waking_the_cabinet.md) |
[Contents](README.md) |
[Next: Reading the ROMs](18_reading_the_roms.md)
