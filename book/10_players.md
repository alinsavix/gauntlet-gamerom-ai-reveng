# Chapter 10 — The Heroes (Players, Controls, and Inventory)

**This chapter answers:** What is a player, from the machine's point of view —
and how do up to four of them move, fight, drink potions, go shopping for
power-ups, and die, all inside one shared frame?

**By the end you will understand:** how the four character classes exist as
data tables; what actually happens when someone joins a game in progress; the
pipeline from joystick switches to intent; movement as a negotiation with the
world; how melee, shots, and potions deal their damage; the full life of the
health number; inventory, doors, and the power-up vocabulary; and the moments
when cooperative play quietly becomes competitive.

**It builds on:** the frame loop from Chapter 6 (each system here is one of
its per-frame calls), the session lifecycle from Chapter 7, Chapter 8's world
model — maze slots, pixel coordinates, and MOBs, the motion-object records
that represent every moving thing — and Chapter 9's freshly constructed
level.

---

## A friend with a coin

Start with the most Gauntlet II moment there is. You're alone on level nine,
health sagging, when a friend walks up, drops a coin, holds the stick left,
and presses start. A valkyrie materializes in a clear cell near where you're
standing, her stats column lights up in blue on the info panel, and the
cabinet says, in its best announcer voice, "Welcome, Blue Valkyrie."

Nothing about that moment is special-cased. Joining mid-level runs the same
machinery as starting a fresh game, and by the end of this chapter you'll
have seen every gear in it: the character-selection state your friend was
briefly in, the spawn search that found her a safe cell, the MOB that now
carries her around, the tables that make her a valkyrie rather than a wizard,
and the shared per-frame update — one of the sixteen gameplay calls inside
`g2mainloop` — that treats her exactly like you, sixty times a second.

## A hero, by the numbers

The four classes feel different to play, and the differences are almost
entirely *data*. There is one body of player code; being a Warrior or an Elf
means indexing that code's tables with a different character number
(0 Warrior, 1 Valkyrie, 2 Wizard, 3 Elf<!-- AGENT: make this a small table --> — an ID you'll see reused
everywhere).

Per-class ROM tables cover, among other things:

- **movement speed** — one entry per character, in normal and powered
  states (the extra-speed power-up selects the second column);
- **health drain** — how fast time itself eats you, indexed by character
  and difficulty;
- **shot damage** — what your projectiles do;
- **armor** — how badly monster shots and contact hurt *you*, again by
  character;
- **magic** — a whole matrix, covered in its own section below.

The shot-damage table is small enough to show in full, with its two
modifiers: <!-- AGENT: we should swap the rows and columns here, so
that the columns are by hero, and the rows are by power up, which
matches the layout in ROM. I think, anyhow. Verify before changing
anything! -->

| Hero | Normal shot | With shot-power upgrade | Super shot |
|------|------------|-------------------------|------------|
| Warrior | 2 | 2 (+0–1 random) | 3 |
| Valkyrie | 1 | 2 | 3 |
| Wizard | 1 (+0–1 random) | 2 | 3 |
| Elf | 1 | 2 | 3 |

(Basic monsters die in one to three points of damage depending on their
tier, so these small numbers matter more than they look; Chapter 11 does the
bookkeeping.) Armor works the same way in the other direction: incoming
monster-shot damage is looked up by monster type *and* victim character, and
the table is kindest to the Valkyrie and cruelest to the Wizard. The famous
class tradeoffs from Chapter 1 are, concretely, just these lookups. <!-- AGENT: we
should actually show each of the major player-power-associated-tables
here, if they're not included elsewhere in the book -->

![Walking and fighting animation frames for one hero](img/ch10_anim_frames.png)

> **[image needed]** `book/img/ch10_anim_frames.png`: a grid of one
> character's sprites rendered from the graphics ROMs with `python-gex` —
> ideally the Warrior's walking frames (4 frames × 8 directions, or one row
> of 4 frames for two or three directions) beside his fighting frames, scaled
> 3–4×, with row labels for direction and column labels for frame number.
> This illustrates the "4 chars × 8 dirs × N frames" animation tables
> described below.

Even a hero's *look* is table-driven. Each player has a free-running
animation counter, and four ROM tables — idle, walking, fighting, shooting —
are indexed by character, facing direction, and a few bits of that counter to
pick the sprite for this frame. Walking cycles four frames roughly every
quarter second; fighting runs an eight-frame swing; shooting is a four-frame
throw. Nothing anywhere "plays an animation" — every frame, the current
counter value simply *is* the animation.

## Joining the party

Now the join itself, in order.

A coin gives a dead station health-credit and drops it into
**character-selection state** — one of the per-player status values from
Chapter 7, not a separate screen. The game is still running; your friend is
choosing a hero *while* you fight. Selection reads her joystick directly: up
offers the Warrior, left the Valkyrie, down the Wizard, right the Elf, and
each change repaints her info-panel column to preview the choice.

When the choice is committed (Chapter 7's session machinery owns the exact
trigger), the actual placement runs:

1. **Find ground.** The spawn search probes candidate cells using the same
   offset tables the game's other placement searches use — the level's
   player-start marker is the recorded fallback anchor for joins — looking
   for a cell that is genuinely clear: traversable floor, no occupant, no
   rendered MOB crowding any of its eight neighbors. Only a successful
   placement lets the join proceed; the finalizer never runs without a spot
   to stand. <!-- AGENT: this probably needs to note that when a second (or third,
   or fourth) player joins, it tries to add them immediately next to an existing
   player, only falling back to the maze start if those are unavailable, and 
   giving an error buzz if no location is available. This needs to be verified. -->
2. **Build the body.** A MOB is created at that cell and its slot is
   recorded as this player's — from here on, "player 2" is an index into the
   same five parallel arrays as every monster (Chapter 8), plus a family of
   per-player state arrays: health, score, facing, powers, inventory,
   timers.
3. **Install the character.** Two small per-player handler slots in RAM are
   pointed at character-specific palette routines — one for the "hurt" flash
   cycle, one for power-state color cycling — which the display update calls
   every frame thereafter. This is why a poisoned wizard and a poisoned
   warrior each flicker in their own class's colors: the *handler itself*
   was chosen at join time.
4. **Announce.** Counters and per-player state are initialized, the active
   player count goes up, the join sound plays, the info-panel column is
   drawn for real, and the speech system greets the newcomer by color and
   class.

Death runs this film backward — but that's the end of the chapter.

## From switches to intent

Chapter 6 showed the electrical half: raw joystick words read every frame,
active-low (a pressed switch reads 0), filtered through hand-written
debouncing. This chapter picks up at the clean result: for each player, a
byte whose high four bits are up/down/left/right and whose low bits include
**Fire** and **Magic**.

The game converts those four direction bits into *intent* with a sixteen-entry
lookup: every combination of the four switches maps to one of eight
compass directions or to "no direction" (that's how up+left becomes a clean
diagonal, and contradictory combinations resolve to nothing). The result
feeds three separate pieces of per-player state — and keeping them separate
is what makes the controls feel right:

- **facing direction** — the way your sprite looks and shoots; updated as
  you move, and deliberately left unchanged when a move is rejected;
- **fighting direction** — a parallel direction used while an attack
  animation is in flight, with its own sixteen-entry input map;
- **the buttons** — Fire arms the shooting sequence; Magic asks to drink a
  potion. Each is a request, not an instant action: the per-frame player
  update decides if and when the request is honored.

## Movement is a negotiation

Walking sounds simple and is anything but: the maze pushes back. Each frame,
the player update proposes a move and the movement routine — the project
calls it `player_try_move` — either commits it or explains why not:

```
speed = speed_table[character][powered?]
delta = direction_deltas[facing] scaled by speed
        (reduced if stunned, poisoned, or acid-slowed)

result = try_move(player, delta, flags):
    probe the target cell(s) for walls and blocking objects
    if a door: run direction-aware door traversal (have a key?)
    if blocked diagonally: try the corner "squeeze" geometry check
    if blocked by monster or player: stop (bodies are solid)
    honor the level's wrap flags at maze edges
    commit the move, or report "blocked"
```

A few details make this negotiation feel polished. The **corner squeeze**
retries a blocked diagonal as an L-shaped slide, so brushing a corner steers
you around it instead of stopping you dead. A **blocked** result sets a flag
the caller uses to keep your facing unchanged, so a failed step never
scrambles your aim. Movement against the **camera window** is constrained too:
unless the level flags say otherwise, you can't walk somewhere the shared
screen refuses to follow (Chapter 8's rubber-band, seen from the other
side). And the slow-effects are stacking debuffs on the proposal itself:
stun freezes it briefly, poison drags it for ten or twenty seconds, walking
through acid slows you while you're in it.

All of the wall, door, and occupancy probes work on Chapter 8's packed maze
slots and the traversability table introduced there — movement is the
biggest customer of that machinery.

## Swords and arrows

Gauntlet II's melee is famously implicit: there is no "sword button." Walk
into a monster and your hero *fights* — the eight-frame fighting animation
runs in your fighting direction, and the collision between the two bodies is
resolved through class data: the monster's contact damage against your
armor table on one side, your class's fighting ability on the other. The
upgrade item called "extra fight power" and the armor power-up both act
here.

Shooting is the explicit half. Pressing Fire starts the four-frame shooting
animation; when the animation *completes*, the shot actually spawns —
provided your shot channel is free. That wind-up is why firing feels like a
throw rather than a laser. The projectile takes your facing direction, a velocity
from a per-direction/per-class table, and a picture from your class.

The most important rule is the channel: **each player owns exactly one shot
MOB**, one of the fixed low slots from Chapter 8. One arrow in flight per
elf. Your next shot cannot exist until the current one lands, so standing
close makes you objectively faster — the defining rhythm of Gauntlet
marksmanship, implemented as a slot allocation rule.

When a shot arrives somewhere interesting, one large resolution routine —
`resolve_shot_hit`, the busiest intersection in the combat system — decides
what happens, dispatching on what was hit: monster, generator, player, wall,
door, food, potion, dragon, Death. Its monster-and-generator side belongs to
Chapter 11; its player-vs-player side closes this chapter. Two of its
verdicts matter everywhere: a shot is either *consumed* by the hit or
*survives* it — supershots pierce through most monsters, and with the
reflect power a shot can bounce off a wall instead of dying there.

## Potions and the Magic button

Press Magic with a potion in your pocket, and the drink dispatches a blast
against every eligible monster and generator around. What it does to each is
not a formula but a lookup — a genuinely pretty piece of 1986 data design.

In ROM sits a **potion-effect matrix**: one 16-byte record for each of the
28 monster and generator object types. Within a record, the entry is
selected by *who* is drinking (the four characters) and *how* the magic was
triggered — a drunk potion or one set off by a shot — plus a flag for
whether the drinker owns the **extra magic power** upgrade. The entry for a
monster type is a damage value; the entry for a generator type is a
*replacement* — the generator transforms into the object named by the table,
which is how a strong magic user doesn't just dent a ghost generator but
demotes or deletes it.

One matrix, and every question answers itself. Why does the Wizard's potion
level a room while the Warrior's just singes it? Different columns. Why does
a shot-triggered potion fizzle compared to a drunk one? Different trigger
row — the game charges you for clumsiness by table lookup. Why did that
generator turn into rubble for one player and merely downgrade for another?
Same answer. (The dragon, as always, is special: the potion handler gives it
a private check of its own — Chapter 12.)

> **[needs verification]** A worked slice of the real matrix — e.g. the
> ghost, demon, and ghost-generator records across all four characters,
> normal versus enhanced magic — should be extracted from the ROM
> (`potion_effect_matrix`, 28 × 16 bytes) and shown here as a labeled table.
> The matrix's structure and indexing are verified; the documentation does
> not list the individual byte values.

## The dwindling number

Chapter 1 called health both life bar and cash register. Here is its
complete life story, every entry verified in the per-frame code:

**Down.** Time itself drains health on a steady cadence — the amount comes
from a table indexed by character and the operator's difficulty setting, so
the tax rate is a tuning knob. Monster contact subtracts through the
contact-damage table (with its powered-player half), monster shots through
the armor table, hazards and special monsters through their own paths.
Damage isn't only applied — it's *sampled*: a 60-frame window accumulates
what you've taken, maintains a running average, and uses it to decide when
the situation deserves spoken commentary.

**Up.** Food adds a flat hundred. Coins add the operator-configured amount.
That's the whole list — health is scarce by design.

**The warnings.** Below 200 health, a per-player timer starts driving the
low-health show: the health number on the info panel pulses dim and bright
in a steady eight-frame rhythm, and a heartbeat sound plays on a cadence
selected by a mask table indexed by how low you are — the lower the health,
the more often the mask fires, so the heartbeat genuinely accelerates as you
fade. The spoken warning ("… is about to die!", "… needs food, badly") is a
one-shot latch per life, so the cabinet frightens your friends exactly once
per emergency.

**Zero.** The death sequence runs, your MOB winds down, and the per-player
timer that drove your heartbeat is bluntly *reused* as your death
countdown — 45 seconds if your score-per-coin ranked for initials entry, 10
seconds of GAME OVER display if it didn't. (The same word, two jobs,
depending on whether you're alive: a very 1986 economy.) If you were the
last player standing, Chapter 7's continue prompt takes it from here.

**Poison, a footnote with teeth.** Some food and some potions are poison
variants, distinguished by their sprite. Shooting one releases the toxin on
you — a ten-to-twenty-second slowdown, announced by sound — which converts
"don't shoot the food" from etiquette into self-interest.

## Pockets and doors

A hero's inventory is spartan: a count of **keys**, a count of **potions**,
the **score multiplier**, and the power-up bits below. The info-panel column
renders it directly — rows of key and potion icons, the multiplier when it
exceeds one — so your pockets are always public.

![One player's info-panel column, annotated](img/ch10_hud_column.png)

> **[image needed]** `book/img/ch10_hud_column.png`: a MAME screenshot crop
> of a single player's info-panel column mid-game, annotated with callouts
> for: score, health value, hero name in station color, the key/potion icon
> rows, the power-up icons, the score multiplier (if present), and the "IT"
> label position. Capture with a player who holds several keys and potions
> and at least one power-up.

Keys are collected by walking over them and *spent* without ceremony: touch
a locked door with a key in pocket and the door system takes over. Doors are
more than wall-with-a-lock — each is a logical object with recorded
**endpoints** and direction codes, so traversal is direction-aware, and
opening one animates through the door renderer (up to eight doors can be
mid-animation at once). The world-side of doors — how the maze graph
changes, how neighbors redraw — is Chapter 13's; the player-side rule is
simply *one key, one opening*. And if the party dawdles long enough, an idle
timer gives up and opens every door on the level for free, with a "Doors
open" announcement — the dungeon would like you to keep moving.

Around all of this hovers the advice system: the first time you meet a
mechanic — first key, first locked treasure, first transporter, first potion
wasted by a stray shot — a one-time dialog box freezes gameplay (Chapter 6's
dialog gate) and explains it. Each tip is a bit in a 32-bit seen-it mask, so
the machine nags precisely once per lesson.

## The power-up shelf

Beyond food and cash, the floor offers power-ups — presented, like most
things in this dungeon, in bottle form. The game's own legend screen sorts
them into two shelves, and the implementation agrees:

**The permanent shelf** — six upgrades that set a bit in your power word and
stay with you: **extra speed**, **extra armor**, **extra fight power**,
**extra shot speed**, **extra shot power**, and **extra magic power**. Each
one selects the better column of a table you've already met in this
chapter — speed's powered column, the contact table's powered half, melee
strength, projectile velocity, the damage table's upgraded column, the
potion matrix's enhanced variant. Six bits, six icons on your info-panel
column; the thief (Chapter 12) appraises exactly these when choosing his
victim.

**The temporary shelf** — timed or metered effects:

- **Invisibility** — monsters lose track of you; as the timer runs out,
  your sprite flickers at an accelerating rate (a mask table indexed by the
  timer's phase — the flicker *is* the fuel gauge).
- **Invulnerability** — damage immunity on a timer, with its own palette
  cycling so everyone can see you're briefly a demigod.
- **Repulsiveness** — the anti-magnet: monsters keep their distance while
  it lasts.
- **Reflective shots** — your projectiles bounce off walls instead of dying
  there, with a per-bounce recalculated direction.
- **Super shots** — a metered pack of screen-clearing ammunition (the
  legend advertises ten): while charges remain, every shot does top damage,
  pierces through ordinary monsters, ignores a blinking sorcerer's
  immunity, breaks "unbreakable" items, and hurts things nothing else can
  hurt. Each fired shot burns one charge.
- **Transportability** — loosens the transporter rules, letting you arrive
  in places ordinarily off-limits; the game's secret challenges go so far
  as to dare you to land on a demon, or on Death itself.

## When friends become targets

Everything above treats the four heroes as colleagues. Gauntlet II keeps a
little venom in reserve.

**IT.** Touch the darting IT creature and the IT variable — a single word
naming the cursed player, or nobody — points at you. The presentation
half is instant: "IT" is stenciled into your info-panel column in your
colors, and the cabinet announces the transfer by name. The gameplay half is
that monster targeting *accounts for the IT player* when choosing whom to
chase: the crowd's attention finds you. Tag another hero and the label, the
announcement, and the crowd's attention move on. It's the one mechanic where
touching a friend is an act of aggression.

**Friendly fire, by level flags.** On levels flagged **shots stun**, a
teammate's shot freezes you mid-stride for a beat and knocks your attack out
of your hands; on the rarer **shots hurt** levels it also costs a couple of
health. And regardless of flags, a **supershot** is honest artillery: catch
a friend with one and they lose ten health. Four players, one shared screen,
metered ammunition — the game knows exactly what it's inviting.

**The dungeon is watching.** One of the hidden secret-room objectives from
Chapter 13 is literally named "Don't Hurt Friends" — and the shot-resolution
code files the report the instant you shoot a teammate. The machine keeps
score on your sportsmanship.

That's a player: a character number indexing a stack of tables, a MOB in
the crowd, a dozen timers, a power word, and a health number spending itself
sixty ticks a second. Next chapter, the other side of the collision: the
horde.

---

> **Under the hood**
>
> - The per-frame player update walked through here is `main_move_players`
>   (0x4A53A); its status dispatch and post-loop door/idle behavior are in
>   `doc/04_game_subsystems.md` §4.1. Character selection is
>   `character_select_input_update` (0x42DF4), §22.
> - Joining: `player_join` (0x48BB6) → `player_start_inner` (0x48BEC) →
>   `player_join_finalize` (0x48A36), §4.4. Spawn probing uses the
>   candidate-offset tables at 0x578A2/0x578B2 and `tile_occupancy_test`
>   (§23.4). Character palette handlers: pointer tables 0x57842/0x57852 into
>   RAM JMP stubs at 0x905F00, §2.4.
> - Input: raw words at 0x904920, direction decode via
>   `joystick_nibble_to_direction` (0x580FC) and `fight_direction_map`
>   (0x5811C); facing/fighting state at 0x9049A4/0x9049AC. Debounce itself:
>   `input_debounce` (0x40644), §15.
> - Movement: `player_try_move` (0x41BF0) and its probe/traversal graph,
>   §4.2 and `doc/generated/player_collision_contracts.csv`; blocked-facing
>   flag `movement_blocked` (0x904A0E); speed table `player_speed_normal`
>   (0x580A8); slow effects `player_stundelay` (0x904A54) and `poison_timer`
>   (0x9048B2).
> - Animation tables: idle/walking/fighting/shooting at
>   0x58A4A/0x58A8A/0x5884A/0x5874A with counter mechanics in
>   `doc/05_data_reference.md` §8.
> - Shooting: `player_create_shot` (0x53666); one fixed shot MOB per player
>   (`FIXEDMOB_SHOTPLAYER0–3`, §3.8); velocities 0x576E2/0x57792. Combat
>   resolution: `resolve_shot_hit` (0x4AF50), `doc/04_game_subsystems.md`
>   §26, with `shot_damage_base_tbl` (0x596B6), `monstshot_damage_tbl`
>   (0x596CE, Valkyrie best / Wizard worst), and `player_supershot`
>   (0x905F68).
> - Potions: `main_handle_potions` (0x46FEA); `potion_effect_matrix`
>   (0x5DA98, 28 types × 16 bytes; character bits, shot-trigger bit,
>   enhanced-magic bit; damage for monsters, replacement type for
>   generators), `doc/05_data_reference.md` §5.
> - Health: `main_health_countdown` (0x466F6), §4.3; `health_drain_table`
>   (0x5813C); `health_per_coin_table` (0x57862); heartbeat mask table
>   0x576A8; damage sampling `player_damage_sample_update` (0x50E34); the
>   dual-use `player_state_timer` (0x904A26) and score-per-coin ranking
>   `highscore_check` (0x49D0E), §10.3.
> - Pickups and doors: `player_tile_interact` (0x511AC), §4.6; key/potion
>   counters 0x90405A/0x904055; `door_record_endpoints` (0x51E80) with
>   endpoint records 0x904A76/0x904A86; `main_open_doors` (0x45C00);
>   idle-timer door opening via `idle_timer` (0x90490C). Inventory/icon
>   rendering: `player_inv_update` (0x45ACA). First-encounter tips:
>   `dialog_first_encounter` (0x4C440), §10.4.
> - Power-ups: `player_powers` (0x9048E0) with the bit enum in
>   `doc/05_data_reference.md` §3.3; `invisibility_flash_masks` (0x58070).
> - PvP: IT variable 0x9049DC and `player_it_label_set` (0x45866), §4.5;
>   shot-stun/shot-hurt level flags (§3.12) and the player-victim branch of
>   `resolve_shot_hit` (§26), including the −10 supershot case and the
>   trick-0x11 "shot another player" secret hook.
