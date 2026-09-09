# 7. The game's clock

An arrow crosses a doorway while a monster comes through it. The hero who
fired it steps backward, the view follows, and a generator finds room for
another creature. To the players, these are parts of one moving scene.
To the main processor, they are jobs carried out in an order.

That order can settle questions the picture alone leaves ambiguous. Does
a new arrow move immediately? Does the monster react to the player's old
position or the new one? If an instructional message appears halfway
through the work, does everything stop at that instant?

We can follow those questions through one repeated trip around the game.
The trip is a **frame update**: an ordered opportunity to change state,
normally paced by the display. It is not a promise that every object will
move, or that every routine will take the same amount of time.

## A signal from the screen

The CRT monitor draws horizontal scanlines, then returns from the bottom
of the visible field to begin another. The interval around that return
is **vertical blanking**, or VBLANK. Video hardware interrupts the main
processor at this cadence, about sixty times each second.

An interrupt briefly diverts the CPU from its current instructions.
The interrupt handler saves the working registers it needs, performs its
service, and normally returns to the interrupted program. The monsters
have not each acquired a second processor. The same CPU has temporarily
changed jobs.

One of the game handler's jobs is to set a word in memory that the main
loop watches. Think of it as a raised flag saying that another field has
arrived. While the flag is clear, the loop waits. When it sees the flag,
it increments the game frame counter, clears the flag, and begins the
next body of work.

This gives the game a convenient unit of time. A routine can count down
sixty updates rather than repeatedly calculating elapsed seconds. At the
normal pace, sixty updates take about a second. The qualification matters:
the counter measures visits through the program, not an independent
wall clock.

There are also two kinds of work at the boundary. The interrupt handler
publishes display-related state, including palette and scroll changes,
and services the sound-board exchange. The main loop decides what the
next game state should be. Drawing, interrupt service, and game updates
cooperate without becoming one indivisible operation.

The video circuitry described in Chapter 5 keeps producing a picture
from memory while the CPU does its work. A new picture and a completed
game update are related events, but they are not synonyms.

## One route, with a large bypass

Before the first repetition, the game runs a one-time initializer.
The repeated body then contains twenty-eight direct calls. Three occur
before a dialog check, sixteen form the gameplay group, and nine follow
it. An active dialog bypasses the middle group.

Here is the complete order in a compact strip. The names are those used
by this project's research, not surviving Atari source labels.

| Call | Routine | Place in the frame |
|------|---------|--------------------|
| 1 | `main_logo_updcolors` | Before the dialog gate |
| 2 | `input_debounce` | Sample controls |
| 3 | `coincheck` | Account for credit |
| 4 | `main_cycle_tport_and_ffield` | Gameplay begins: transporter/forcefield colors |
| 5 | `main_handle_potions` | Use carried magic |
| 6 | `main_open_doors` | Advance opening doors |
| 7 | `main_handle_shots` | Existing projectiles and new throw requests |
| 8 | `main_move_players` | Player movement and action animation |
| 9 | `main_scroll_playfield` | Camera |
| 10 | `main_move_monsters` | Ordinary monsters and generators |
| 11 | `main_handle_dragon` | Dragon |
| 12 | `main_thief_anim` | Existing thief or mugger |
| 13 | `main_start_thief` | Visitor arrival |
| 14 | `main_health_countdown` | Health and player endings |
| 15 | `main_treasure_timer` | Timed-room progress |
| 16 | `main_handle_death` | Death/forcefield sound timing |
| 17 | `main_exit_move` | Moving exits |
| 18 | `main_walls_cyclic_move` | Cyclic walls |
| 19 | `main_walls_random_move` | Random walls; gameplay group ends |
| 20 | `main_msgbox_countdown` | Dialog lifetime |
| 21 | `character_select_input_update` | Character choice |
| 22 | `main_start_game` | Joining and session/level transitions |
| 23 | `main_score_update` | Popups and transition effects |
| 24 | `main_score_display` | Information panel |
| 25 | `main_attract` | Idle-show and related display state |
| 26 | `eeprom_timer` | Persistent-state service |
| 27 | `sound_response` | Sound-board responses and recovery |
| 28 | `main_update_sound` | Outgoing sound queue |

The strip describes calls, not unconditional activity. A player routine
can return because the game is showing the title. The monster pass can
return because there are no active players. A generator that is visited
can still fail every condition required to create something.

Nor does a name necessarily describe everything inside a call.
`main_score_update` also advances transition effects; projectile motion
is the separate seventh call. Treating the strip as an order of visits
is more useful than imagining twenty-eight sealed departments.

For a player, the interesting parts are the handoffs between visits.
A door can advance before a projectile tests it. The camera sees player
positions after movement, while the following monster pass uses the
updated view. Each consumer reads the state available when its turn
arrives, rather than a universal snapshot taken at the frame's start.

## Follow Fire through five visits

Take an illustrative Elf standing still in a clear corridor. Its reserved
projectile slot is empty, it is not stunned or teleporting, and there is
no dialog. Call the first frame in which an eligible held Fire is read
frame A. We are describing the program's sequence, not measuring the
delay from a person's finger to the monitor.

The input service has already sampled the controls when the projectile
routine runs. For this empty player-shot slot, that routine can arm a
throw: it marks the shooting action and resets the animation counter.
Later in the same frame, the player routine advances that counter.

The shipped launch threshold is three, compared with the counter's
value before it is incremented. For this stationary, uninterrupted
example, the sequence is:

| Frame | Projectile call | Later player call |
|-------|-----------------|-------------------|
| A | Empty slot; arm the throw | Counter 0 becomes 1 |
| A + 1 | No live shot; existing throw remains armed | 1 becomes 2 |
| A + 2 | Still no live shot | 2 becomes 3 |
| A + 3 | Still no live shot | Previous value is 3: create the arrow |
| A + 4 | Process the live arrow | Continue player processing |

The arrow is created after that frame's projectile pass has already
finished. Its first ordinary flight update therefore belongs to the next
pass. Creation still installs a position and artwork; it does not wait
for flight to become a real record.

This distinction adds precision to Chapter 2's one-arrow rule. The
projectile slot controls whether a replacement may be armed, while the
player's action counter controls when the armed throw produces its shot.
The four counter updates are not four different drawings, and they are
not four projectile movements.

On subsequent frames, the live arrow is processed before the player
moves. Farther down the strip, ordinary monsters take their turn.
If a projectile interaction removes a monster, the later monster work
does not get to move that same removed record as though the hit had not
happened. If it merely weakens the target, the surviving record contains
the changed strength.

This is why reversing two calls would be a change to the game, not a
harmless rearrangement. A monster moved before the shot test could occupy
a different collision position. It would take an actual example and its
collision geometry to say which outcome changed, but the source of the
difference would already be clear.

## A button can mean a level or an edge

The switches are active low: zero means pressed. The input service saves
the raw input word for each player and also shifts Fire and Magic samples
into separate sixteen-bit histories. Each bit in a history records one
recent sample.

Such a history lets a consumer ask about a pattern across visits instead
of trusting one electrical transition. A mechanical contact can bounce
between open and closed as it settles. A pattern check can also distinguish
a new press from a button that has remained down.

This does not mean every action waits sixteen frames, or that every
joystick direction goes through the same history test. The histories
make recent samples available; individual consumers decide which samples
matter. In particular, ordinary shooting tests held Fire, whereas normal
carried-potion use requires the recognized Magic edge.

That matches two different requests. Holding Fire means keep trying when
the weapon is available. Holding Magic should not be confused with a
fresh series of potion requests on every frame. The useful distinction
is between the current state of a control and an event recognized from
its history.

## The pause has an address in the sequence

Now put an instructional message over our corridor. If its timer is
already nonzero when the main loop reaches the dialog check, calls 4
through 19 are skipped. The arrow does not fly, the hero does not walk,
and ordinary monsters do not move. The health routine is skipped too.

The control sample and coin check have already happened. The message
countdown, joining services, display work, and sound services still lie
ahead. A pause in the dungeon is not a pause in the whole program.

```text
wait for field -> colors -> controls -> coins
                                        |
                                 dialog active?
                                  /          \
                                no           yes
                                |             |
                       gameplay calls 4-19    |
                                |             |
                                '------.------'
                                       |
                    dialog countdown -> remaining services
                                       |
                              check for a late frame
```

*A simplified view of the loop's one large bypass. Individual routines
have further gates of their own.*

Consider two frames that both end with a message visible. In the first,
the timer was active before the gate, so gameplay never began. In the
second, the timer was clear at the gate, but a player interaction later
opened a dialog. That second frame has already admitted the whole
gameplay group. There is no new copy of the main-loop gate between every
pair of calls, and no rollback of the movement or collision that opened
the message.

The message countdown then runs at its usual place after the group.
On a frame where a previously active timer counts down to zero, the
skipped gameplay is not run retrospectively. The next trip reaches the
gate with the timer clear and can resume it.

There is a subtler consequence for periodic work. The game frame counter
continues advancing during dialogs. Health drain tests its low six bits,
charging a point when that global count is a multiple of sixty-four and
the health routine runs. It is not a private stopwatch that patiently
accumulates exactly sixty-four unpaused visits for each hero. A drain
opportunity skipped under a dialog is not billed afterward as a debt.

## Magic reaches another part of the frame

Suppose a stunned hero has a potion and presses Magic. The potion
handler runs before player movement and does not use the movement-stun
timer as a gate. It can consume the potion while the hero is still unable
to walk. It does not cure that timer; the later movement path still sees it.

The potion event also changes what a later call will do. Its flash is
represented by a playfield color latch. The monster pass compares that
latch with the ordinary floor color and selects its potion-effect scan
instead of its normal movement pass.

Eligible monsters in the scan receive the appropriate character- and
target-dependent effect. Surviving targets do not also get an ordinary
move and attack on that potion frame. This is a different kind of pause
from the dialog bypass: the monster routine was called, entered, and
did substantial work, but chose an alternative operation.

A player's shot can set off a destructible potion too. Projectile
handling also precedes the monster pass, so this event has a route into
the same frame's later potion scan. A monster projectile breaking that
item does not activate the same magic.

The picture of a flash connects several owners: an interaction selects
the event, the monster service consumes it, and VBLANK publishes its
palette value. The connection is carried by state, not by a single
routine that draws a flash and then somehow makes every consequence
happen at once.

## When the next field arrives too soon

All of this work must normally fit between fields. Some frames are
cheap; others contain crowded movement, collisions, effects, and sound
requests. The main loop checks its VBLANK flag again after call 28.
If the flag is already set, another field arrived before the work
finished.

That check records the lateness by setting `frame_overflow` to eight.
If a later frame finishes before another flag arrives, it shifts the
value right once, halving it with integer arithmetic.

An illustrative single overrun, followed by timely frames, looks like
this:

| Completed frame | Overflow during its work | Value after the final check |
|-----------------|--------------------------|-----------------------------|
| Late frame | 0, assuming no earlier overload | 8 |
| First timely frame | 8 | 4 |
| Second timely frame | 4 | 2 |
| Third timely frame | 2 | 1 |
| Fourth timely frame | 1 | 0 |
| Next timely frame | 0 | 0 |

The timing of that final check matters. The late frame does not go back
and cancel a monster it already created. The following four timely
frames see a nonzero overflow value while doing their work. If another
overrun occurs, the check reloads eight rather than continuing the decay.

While overflow is nonzero, the generator probability is forced to zero.
Even a generator whose turn has arrived and whose neighbors are empty
cannot pass that probability gate. Existing monsters are not deleted;
the game temporarily stops adding that source of work.

The final sound-queue dispatcher also defers its work while the signal
is nonzero. This does not mute the sound board, stop a phrase already
playing, or forbid every immediate sound send elsewhere in the frame.
It specifically defers the queue-draining service. The sound computer
and its interrupt exchange remain distinct from that service.

These are load-reduction measures after missed timing, not proof that
the game can never slow down. The semaphore is a flag, not a queue
containing one complete update for every field that passed. Nothing
here reconstructs all missed simulation time through a burst of
additional monster updates.

The display continues its rhythm while the game may advance less often.
For a player looking down the corridor, this means an empty square is
only part of the story of the next monster. A generator needs room,
its scheduled opportunity, its successful chance test, and a game that
is no longer suppressing births after late frames.

Another coin follows a different route. Its accounting call sits before
the dialog gate, and its physical reports arrive through the sound-board
exchange. The next chapter follows that transaction from the coin slot
to the health number, then into rules that make money affect more than
the length of one hero's life.

### Sources and further reading

- [Game ROM structure](../doc/03_game_rom_structure.md), sections 2.1-2.4:
  `g2mainloop` (`0x42A66`), its one-time initializer, the repeated
  twenty-eight-call order, dialog bypass, and overflow assignment/shift.
  The [call contracts](../doc/generated/main_loop_contracts.csv) include
  initialization separately.
- [Game subsystems](../doc/04_game_subsystems.md), sections 2.2, 4.3,
  4.6.1, 11.1-11.3, 15, and 25: action timing, health cadence, potion
  event, sound dispatch, input histories, and transition effects.
- The Fire timeline follows the empty-slot input arm at
  `0x47B72-0x47BF6`, the previous-counter comparison and creation call at
  `0x4ABD2-0x4ABF2`, and the threshold table at `0x58090`.
  It assumes a stationary eligible hero, uninterrupted gameplay, and
  no pre-existing shot; it is not a captured input-latency measurement.
- [Python main loop](../gauntpy/src/gauntpy/mainloop.py) presents the
  reconstructed order as readable calls. Its host timing is not evidence
  for the original processor's instruction budget.

[Previous: A world in ten bytes](06_a_world_in_ten_bytes.md) |
[Contents](README.md) |
[Next: What a quarter buys](08_what_a_quarter_buys.md)
