# 15. When nobody is playing

The blue Elf has a wall in the way. Instead of turning aside, the
demonstration holds the joystick toward it. A message says “PUSH MOVABLE
WALLS.” When the walk continues, the obstacle moves and the Elf follows.

This is a useful first lesson in Gauntlet II. Something that looks like
part of the maze can be acted upon, and ordinary movement is enough to
try it. No special pushing button appears. The same controls that take
the hero down an open corridor can change the corridor.

It is also a useful place to ask what we are watching. The game has not
stored pictures of an Elf pushing a wall. It has stored an instruction
to hold Down. Whether that instruction moves the hero, moves the wall,
or accomplishes nothing is decided by the working game.

The attract demonstration borrows almost everything we have followed
through the earlier chapters: collision, inventory, shots, monsters,
messages, transporters, and the shared view. Its special machinery is
small by comparison. It prepares a stage, supplies recorded controls,
and ends the performance before it becomes an ordinary session.

## Eight counts to the wall

![The stored maze used by the demo](img/ch15_demo_maze.png)

*Maze 102, rendered offline from the ROM-derived maze and graphics data
by the book's image generator. This is a layout illustration, not a
captured frame or a record of the Elf's route.*

Setup loads that particular maze rather than asking the normal
[maze-selection system](09_mazes_and_slapstic.md) for the next adventure.
It rebuilds the information panel, clears first-encounter message flags,
and joins player position 1, blue, as an Elf. The demo join supplies
2,000 health. The other three input streams begin inactive.

The position and the character are separate choices, just as they are
when a person plays. There is no special species of “demo Elf.” The
ordinary Elf movement and attacks will interpret the recording.

Here are the first nine pairs in that recording, beginning at ROM
address `0x581C4`. Numbers in the left column are hexadecimal; durations
in the middle column are decimal.

| Stored pair | Meaning | Place in the opening |
|-------------|---------|----------------------|
| `01 F3` | No switches, duration 1 | Initial record |
| `FF 00` | Show caption 0 | “BLUE / SELECTED / ELF” |
| `08 B3` | Down, duration 8 | Approach the movable wall |
| `FF 01` | Show caption 1 | “PUSH / MOVABLE / WALLS” |
| `90 B3` | Down, duration 144 | Keep pressing into the wall |
| `28 E3` | Right, duration 40 | Leave the pushing line |
| `10 D3` | Left, duration 16 | Change direction |
| `08 B3` | Down, duration 8 | Continue through the layout |
| `0E 93` | Down-left, duration 14 | Begin the next approach |

*Decoded ROM records, not a measured video timeline. Duration counts
belong to the input scheduler; command processing and other input
consumers have their own positions within a frame.*

Two bytes suffice for an ordinary record: a duration and a set of
switches. The switches are active low. A zero means pressed, matching
the electrical convention of the original controls. In `B3`, the Down
bit is clear; in `D3`, Left is clear. `F3` leaves every connected control
released. Its two cleared spare bits do not request an action.

The longer Down record is the important one. It does not say “move a
wall six cells.” It keeps asking to move in one direction. The collision
path recognizes a movable wall and tests whether the wall can move into
the space beyond. A successful push relocates the obstacle; later
movement attempts let the Elf follow. A blocked destination would still
be blocked during a demonstration.

That distinction gives the recording its economy. There is no need to
encode the push's individual pictures or duplicate its collision rules.
The stored maze supplies the opportunity and the held input supplies
the repeated request. The [living-maze rules](10_the_living_maze.md)
produce the action.

## A caption has a place in the engine

The `FF` pairs are commands, not exceptionally long button holds.
Their second byte selects a caption. The stream reader shows the
message, then continues through commands until it installs another
ordinary input record. Thus “PUSH MOVABLE WALLS” and the long Down
record are adjacent parts of one demonstration, not separately timed
pieces of footage.

The message uses the same box system as gameplay advice. With the
ordinary text setting it loads a countdown of 150, roughly two and a
half seconds at sixty updates per second. Reduce Text shortens that
countdown to 120. Neither number belongs to the recorded Down hold.

Recall the [dialog gate](07_the_games_clock.md). At the start of the
world portion of a frame, an active message skips sixteen gameplay
calls. Player movement, monster movement, and the routine that advances
demo records are inside that portion. Message countdown, sound service,
and attract-screen timing are outside it.

The game therefore has two useful clocks for our purposes. One measures
eligible advances of the script; the other measures the continuing
display frames. Reading a caption spends the second without steadily
spending the first.

```text
                            wall caption visible
Display frames:   approach |----------------------| pushing continues
Script progress:  Down 8   | long Down held here  | Down 144 runs on
World updates:    enabled | next gated frames skip| enabled again
Message timer:            | counts toward zero   |
Attract timer:    -------- continues throughout ------------------->
```

*Illustrative ordering diagram, not frame measurements. The frame that
creates the box has already passed the dialog gate; the pause applies
when subsequent frames test that gate.*

That last detail prevents an overly tidy mental model. Showing a
caption does not roll back the current frame or stop the processor in
the middle of the stream reader. Some work can complete before the
next gate check. But once the gate is taking its paused branch, the
record's remaining duration is preserved rather than counting down
behind the text.

The result is quite natural to watch. The message identifies an action,
gives us time to read, and lets the action proceed. Underneath, text has
changed which pieces of the engine are allowed to advance.

## The transporter needs both clocks

Later the Elf reaches a transporter while following `32 D3`: Left for
50 script counts. This time the advice is not an `FF` command waiting
at that location in the recording. The ordinary first-encounter path
raises the transporter message when the hero lands.

Some transporter work belongs to the world update, but its transition
animation also uses the score/effect work outside the dialog gate.
That effect can continue while the player's recording and ordinary
movement are paused. What looks like one continuous event on screen
crosses two scheduling regions.

The documented MAME 0.289 trace supplies a concrete example. The Elf
lands at logical slot 486, position `(92,240)`, while `32 D3` is still
current. After the message pause, enough Left remains to reach slot
483, position `(44,242)`, before changing records. These are positions
reported by that original-ROM trace, not coordinates measured from the
layout illustration above.

| Stage | Script side | Display/effect side |
|-------|-------------|---------------------|
| Reach the transporter | Left record is live | Transport begins |
| Landing raises advice | Remaining duration is preserved during gated frames | Box counts down; transition effect can advance |
| Box closes | Remaining Left continues | Hero finishes the move away from the landing |
| Record expires | Next direction becomes current | Ordinary demonstration proceeds |

*A schematic of the documented sequence. It deliberately does not
assign absolute frame numbers to the stage boundaries.*

Suppose we removed the message but otherwise kept those bytes.
The input scheduler could then consume Left during time that the
transport transition still occupies. When ordinary walking becomes
available again, less Left would remain. The next Down record could
arrive before the hero had cleared the obstruction below.

A caption is therefore not an optional subtitle laid over an
independent movie. Even advice generated by an encounter helps
determine where later recorded controls take effect. The ROM's Reduce
Text setting retains the full first-encounter message bank in negative
attract modes, though it shortens retained messages to 120 counts.
Shortening a pause and deleting its event are different operations.

## Friends arrive through the same door

The demonstration eventually says “HAVE FRIENDS JOIN IN ANY TIME.”
Two following command pairs make that proposition visible: `FE 20`
and `FE 03`.

Here the high nibble names a character and the low nibble names a
player position. `20` means Wizard at position 0, red; `03` means
Warrior at position 3, green. Each command sets the class and calls
`player_join`, then installs that position's recorded-input pointer.
The join uses the ordinary adjacent-player spawn search rather than
teleporting a prerecorded picture to a guaranteed screen coordinate.

![The three input streams of the recorded demo](img/ch15_demo_script.png)

*An offline diagram generated from the ROM's input pairs. Spans sum
stored hold durations, with joined streams aligned to the join commands.
The seconds axis is a nominal script-time scale, not elapsed viewing
time; captions and encounter pauses are not drawn to duration.*

The different input users choose their source separately. Movement
reads recorded directions; firing reads recorded Fire. Potion use
tests Magic in the current demo record rather than requiring the
debounced physical-button edge used during play. A late `01 F2`
record supplies that Magic press. The normal potion machinery spends
the collected inventory and produces its effects and advice.

The recording also contains long stretches of `F3`, no controls.
Those are waits, not stopped gameplay. Monsters and effects can act
while a scripted hero does nothing. A message pause is different:
it withholds whole groups of engine updates.

Finally, `00 F3` leaves the Elf's stream parked with all controls
released. Zero does not rewind the recording. Nor does reaching an
exit start another playable level: once all recorded actors have
finished their exit animations and the required shared effects have
cleared, a demo-specific handoff resets the players and expires the
attract timer. The legend follows.

## A prepared stage is not a saved world

The repeated maze, class, controls, and advice give the show much of its
familiar shape. Demo setup also resets the free-running frame counter,
aligning rules that consult its low bits. That is substantial preparation,
but it is not a complete saved state.

The demonstration shares the game's random-number stream. It does not
substitute recorded random results alongside the recorded joystick.
Object setup and live game behavior can draw from that stream, whose
position depends on earlier activity. A different result can alter an
encounter; altered encounters can in turn change later calls.

There is an important limit to that explanation. The attract path
does **not** apply the ordinary level-flag randomization: it keeps the
maze header's flags. We should not explain every difference by imagining
that maze 102 receives a freshly randomized set of hazards. Fixed flags
and a shared random stream can coexist.

An illustrative comparison is two runs that reach the same input
record with a monster in different positions. Both ask the Elf to
walk Left. One may produce unobstructed movement; the other may enter
combat or fail to move. The recording has not changed, but the state
read by the next collision test has.

This is why “the demo always does exactly this” needs a starting-state
qualification. The prepared route is real, and a trace can establish
what occurred in one execution. Neither establishes frame-perfect
replay after arbitrary prior play, settings, or random draws.

## The show around the walk

The demo is only one part of the invitation. A mode word and an outer
countdown organize the unattended sequence:

```text
Scores → Title → Demo → Items/rules → Monsters → Credits → Scores
 10 s     25 s   up to       10 s        10 s       10 s
                120 s
```

*Approximate durations at sixty updates per second. The loaded counts
are 600 for scores and each legend page, 1,501 for title, and 7,200
for demo. Exit completion or qualifying input can shorten a screen.*

The three explanatory pages share LEGEND mode and use a page counter
that counts down from two. A reader sees three pages; the main state
machine needs only one legend mode plus a small selector.

The scores present four separate class ladders. They rank
[score per coin](08_what_a_quarter_buys.md), so a larger raw score is
not automatically the better performance. Returning to these ladders
after showing three heroes makes the distinction between player
position and character class visible in another form.

The title changes the use of the display more dramatically. Its
background is a stored 40-by-25 tile map, while the logo is assembled
from motion objects. The letters and the “II” can move separately
without replacing the background or redrawing a full-screen picture.

The full motion program begins with these four-byte records:

| ROM bytes | Duration | Main logo V change | “II” V change | Playfield scroll change |
|-----------|----------|--------------------|---------------|-------------------------|
| `90 02 00 00` | 144 | +2 | 0 | 0 |
| `03 FE 00 02` | 3 | −2 | 0 | +2 |
| `06 01 00 FF` | 6 | +1 | 0 | −1 |

*Decoded start of the full program at `0x5AC2E`. Changes are signed
values in the program's coordinate convention; positive MOB V changes
move the artwork upward on screen.*

The main title rises into view, reverses briefly, and settles back.
The corresponding later records bring in the “II.” The short program
keeps the two principal entrances but omits those reversal records.
This is a motion description, not a sequence of replacement drawings.
The small background-scroll adjustments let scenery participate too.

Motion is only half of the effect. The color routine shifts entries
through ten motion-object palettes and injects a color whose intensity
rises and falls between bounds. When the intensity turns at its lower
bound, the sequence can advance to another color. The artwork's pixel
indices stay put while their meanings change, producing traveling
color and brightness across the assembled title.

A persistent intro state selects full or short motion. With attract
sound enabled, its zero case also requests the theme and reloads that
state to two; later title entries decrement it. This is separate from
the counter that refreshes operator settings on every thirteenth title
setup. Neither requires the whole game to restart between invitations.

## A small combat manual

The legend changes pace again. The item/rules page pairs names and
advice with illustrations. The monster page turns the three ways of
attacking into a comparison:

| Monster | Fight | Shoot | Magic |
|---------|-------|-------|-------|
| Ghost | NO | YES | YES |
| Grunt | YES | YES | YES |
| Demon | YES | YES | YES |
| Lobber | YES | YES | YES |
| Sorcerer | YES | YES | YES |
| Death | NO | NO | YES |
| Acid puddle | NO | NO | STUN |
| Super Sorcerer | NO | YES | STUN |
| IT | NO | STUN | NO |
| Dragon | NO | YES | STUN |

*Transcription of the ROM's displayed Fight/Shoot/Magic values, not
a new damage table or a claim that every attack works in every state.*

Its most useful information is the asymmetry. Someone who has been
shooting everything gets a reason to save a potion for Death. Someone
who expects contact fighting to work universally sees several NOs.
STUN warns that making a creature stop or change behavior is not the
same as destroying it.

The short labels cannot express all the rules behind them. A
[dragon](12_fighting_the_dragon.md) marked YES under Shoot still
has a vulnerable phase. The Super Sorcerer's magic response includes
revealing a phasing creature, not a universal persistent stun timer.
The matrix is an introduction to useful choices, not a replacement
for learning timing and state.

Maze 103 supplies the legend's underlying scenery. Opaque blank
alphanumeric cells conceal most of it behind a black reading area;
selected transparent rectangles expose illustrations. The next score
screen retains that maze but covers only its ladder boxes, leaving
scenery visible between them. The display layers that let text sit
above a dungeon also let the game decide how much dungeon a reading
page should reveal.

The final page acknowledges the work behind the show. Its names are
Ed Logg, Bob Flanagan, Sam Comstock, Susan G. McBride, Alan Murphy,
Will Noble, Pat McCarthy, Cris Drobny, Hal Canon, Brad Fuller, Earl
Vickers, Ken Hata, Mike Albaugh, and Dave Theurer, followed by “AND
MANY OTHERS.” Role labels span programming, graphics, engineering,
sound, physical cabinet design, technical work, and special thanks.

## Touching the controls without taking over

The attract sequence has a modest browsing interface of its own.
After an opening lockout of about one second, the four physical
positions offer these shortcuts:

| Position | Joystick direction | Attract-page button |
|----------|--------------------|---------------------|
| Red | Demo | Title |
| Blue | Legend; advance a page when already there | Scores |
| Yellow | Legend; advance a page when already there | Scores |
| Green | Demo | Title |

*Original-control routing. With paid pricing, either Fire or Magic
qualifies as the attract-page button. In free play, only Fire does;
Magic belongs to the separate start path.*

Advancing beyond the final legend page returns to scores. These
inputs select presentations; they do not replace the recorded
joysticks and let a spectator steer the demo Elf.

The lockout belongs only to that browsing behavior. A coin can interrupt
the show without waiting for it, and free play recognizes its qualifying
Magic press through a separate path. Character selection then leads
to a real join, where Magic commits the choice.

The opening wall push has done its job without becoming a different
game. It showed a rule by exercising it. Now the same movement request,
collision test, and movable wall can answer to a person.

### Source notes

- [Attract mode and demo playback](../doc/04_game_subsystems.md#6-attract-mode--demo-playback),
  §§6.1–6.4: screen setup, join decoding, documented MAME transporter
  trace, completion gates, and all four positions' interruption tests.
  The demo loader is `0x449D4`; `main_move_players` advances streams
  at `0x4A56E–0x4A5F0`. The opening pairs above were checked directly
  in `row76.bin` at `0x581C4–0x581D5`; joins are at `0x58234/0x58236`.
- [ROM table catalog](../doc/05_data_reference.md#5-rom-data-tables-catalog),
  §§5.3, 5.6–5.8: demo pointer table `0x58098`, caption pointers
  `0x5815C`, motion programs `0x5AC2E/0x5AC4E`, monster cells
  `0x5A56E`, and credit strings `0x5A9A8`. The displayed combat
  matrix and motion bytes were checked against those ROM records.
- [Main-loop structure](../doc/03_game_rom_structure.md#21-verified-main-loop-call-sequence-g2mainloop-0x42a66),
  §2.1: dialog gate and ordered callers. `demo_message_show`,
  `0x4CB24–0x4CB44`, selects 150 or 120 counts. First-encounter
  message-bank selection is at `0x4C4D0`; its attract path preserves
  messages rather than selecting the mostly empty reduced bank.
- [Level flags and randomization](../doc/04_game_subsystems.md#55-level-flags-load--randomization-maze_load_pickup_config-0x436fe),
  §5.5: the attract exclusion is explicit at `0x4374C–0x43760`.
  The shared RNG is at `0x5FC4E`; the repeatability discussion does
  not depend on claiming that a literal-address scan proves every
  possible initialization path absent.
- [Startup/attract contracts](../doc/generated/startup_attract_contracts.csv):
  named setup and display entry points. `start_attract_screen`,
  `0x4448E–0x44524`, supplies title counters and the demo frame reset;
  `main_logo_updcolors`, `0x4DCBA–0x4DE6C`, supplies palette shifts,
  intensity bounds, and motion-program consumption.
- [Book image generator](img/generate_images.py), `make_demo_maze`
  and `make_demo_script`: provenance and construction of both reused
  illustrations. The script figure sums stored durations; it is not
  evidence of exact elapsed time or absolute join frames.

[Previous: A machine that speaks](14_a_machine_that_speaks.md) |
[Contents](README.md) |
[Next: Waking the cabinet](16_waking_the_cabinet.md)
