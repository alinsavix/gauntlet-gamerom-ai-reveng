# 1. Enter the Gauntlet

Imagine a corridor with food at one end and a generator at the other. The
generator keeps producing ghosts. You can shoot the ghosts from where you
stand, but each one you destroy makes room for another. Your health is low.
The food would help, provided you reach it before somebody else eats it or
an arrow destroys it. A friend has found the exit and wants everyone to
leave.

There is no separate screen on which to settle this disagreement. Your
friend needs the same view of the maze that you do. Move far enough apart
and the edge of the screen becomes another obstacle. Meanwhile the health
number continues to fall, even when nothing touches you.

That situation contains much of Gauntlet II. Fighting buys access to space;
space contains things you need; other players have their own reasons for
wanting those things. Time has a price. The game can explain its buttons in
a few words, then spend an evening producing decisions from their
consequences.

This book follows those consequences into the machine. We will begin with
what you can do at the cabinet, then take one apparently simple action,
firing a shot, far enough apart to see why it feels the way it does.

## Choosing a place at the cabinet

Gauntlet II is Atari's 1986 sequel to Gauntlet. Up to four people play at
once, using four sets of controls arranged around a shared screen. Each
player position has an eight-way joystick, a Fire button, and a Magic
button. The positions have colors: red, blue, yellow, and green.

Your position's color follows you into the dungeon. It colors your hero and
identifies your information on the right-hand panel. The voice uses it too.
When the machine addresses the Blue Elf, it has identified both a person
at the controls and the character that person chose.

The distinction matters because color does not determine character. Any
position can choose any of the four heroes, including a hero somebody else
has already chosen. Four Wizards are a valid party. They still need four
different colors so everyone can tell which Wizard is theirs.

![The four heroes in four player-position colors](img/ch01_four_heroes.png)

*Warrior, Valkyrie, Wizard, and Elf, rendered from the graphics ROMs. These
color assignments are examples, not restrictions on character selection.*

Unless the game is set to free play, supply the credit its settings require. The
character-selection display lets you choose with the joystick: up for
Warrior, left for Valkyrie, down for Wizard, right for Elf. Magic commits
the choice and joins the game. There is no separate Start button. In play,
that same Magic button spends a carried potion.

The heroes give those simple controls different strengths. The Warrior has
a strong ordinary shot and is effective in a close fight. The Valkyrie's
armor makes many attacks less costly. The Wizard gets especially powerful
results from potions. The Elf moves quickly and fires fast-moving arrows.
These are useful first impressions, but the characters are more specific
than a list of superlatives suggests. The Elf's magic, for example, can be
as destructive as the Wizard's against ordinary monsters; strong
generators distinguish them.

You do not have to learn four control schemes. Character differences live
largely in tables of movement, damage, and magic effects, consulted by
shared code. A different hero changes the values with which the same
actions are carried out.

## Two buttons, many decisions

![Diagram of one player's controls](img/ch01_control_panel.png)

*A schematic of the controls, rather than a photograph of a particular
cabinet. Magic also serves as the start/join control.*

Moving the joystick asks your hero to walk in one of eight directions.
Touching an item picks it up when its rules permit. Touching food eats it.
Approaching a locked door with a key begins the process of opening it.
Stepping into an exit takes you out of the current level.

Close fighting also begins with movement. Push into a monster and the
character attacks without another button press. This can be convenient in
a crowded passage, but contact may cost health while you fight. Shooting
lets you attack from farther away: Fire launches your character's
projectile in the direction the hero faces. Magic uses a potion to affect
eligible creatures around the visible area, with results determined by the
character, its powers, and the target.

These actions share the same space. A corridor that gives an arrow a clear
line to a monster may also contain food. Some food can survive ordinary
shots; some can be destroyed. A potion lying on the floor can be set off
by a player's shot instead of being carried to a better place; monster
projectiles merely break a destructible potion. Firing therefore
requires a little more judgment than pointing toward the largest crowd.

The difference between destroying a monster and destroying its generator
is particularly important. A monster occupies the corridor now. A
generator creates future occupants. Clearing a few bodies may let you reach
the source and stop the stream; spending all your time shooting from a
safe distance can leave the source untouched.

Magic offers another way through the problem, but potions are inventory,
not an attack that recharges by waiting. Spending one now means not having
it at the next generator or the next encounter with Death. Even the
apparently generous act of clearing a room can start an argument if
another player thought the potion should have been saved.

The game often teaches a new situation with a message laid over the maze.
While one of these timed instructional messages is present, the ordinary
world update pauses. The monsters wait while you read. The game can
still speak and accept money. Later we will see how a single condition in
the main loop creates that division.

## Reading the room

![Annotated frame showing heroes, monsters, maze, and information panel](img/ch01_gameplay_annotated.png)

*A frame from the attract demo. The visible floor is only a window onto
the maze. The panel at the right keeps each player's health and score
separate even when the heroes are close together.*

The maze is larger than the view. As the party moves, the view scrolls over
it. We will call that view the camera, although there is no camera inside
the cabinet: the game changes the part of the stored world that the
display shows.

The distinction between world and window becomes obvious when someone
wants to go back. One player heads toward the exit while another returns
for a key. The camera has to respond to both. Its movement rules, together
with the rules that keep heroes near the visible area, restrict how far
the party can separate. A player who stops to fight can impede somebody
who would rather run.

Narrow passages add a more immediate form of negotiation. Heroes occupy
space. A friend can be in the way of your intended move even when the
floor beyond is clear. Doors, monsters, and other players can make a
route's usefulness depend on who goes first.

The right-hand panel helps you judge these situations. Health says who is
close to dying. Keys and potions show who can open a way or clear a crowd.
Character names distinguish people with different abilities. The
information is public, so a decision about taking food happens in front of
players who can see whether you needed it.

There are rules that make this social pressure more explicit. Some levels
allow player shots to stun or hurt other players. The IT creature can
mark one hero for special attention from monsters, and that player can
pass the condition by tagging another hero. Cooperation remains useful,
but the game gives people opportunities to bargain, retaliate, and save
themselves.

None of that requires the software to understand friendship. It needs
occupied cells, a camera, visible inventories, and rules for who gets the
effect of a collision. The human part takes place in front of the screen.

## The number that pays for everything

Health is the resource that connects these decisions. You lose it to
damage and gain it from food or additional paid credit. You also lose a
point on every sixty-fourth game frame while the health routine is
running. At the nominal sixty-frame-per-second pace, that is a little
slower than one point a second.

Waiting in an empty corner therefore does not stop the cost of playing.
The time charge is shared by the characters; armor does not protect you
from it. Damage spends the same supply faster. A bad encounter can consume
in moments the health that would otherwise have paid for a long walk.

Ordinary wholesome food restores 100 health. Other food has different
rules, including a variable-value kind encountered later. It is worth
learning the objects rather than treating every edible-looking picture as
an identical refill. What a coin adds is also configurable. The operator
sets the exchange rate, and the panel tells players what is on offer.

Consider what that does to the corridor at the beginning of this chapter.
The food is valuable, but reaching it might cost more health than eating
it restores. Fighting the generator may help the whole party, while the
player closest to it bears much of the immediate risk. Leaving can be the
better choice even with enemies and treasure still on screen.

The game does not require you to empty every room. Usually the practical
objective is to reach an exit with enough health to keep going. Score
rewards what you do along the way, and the distinction between survival
and scoring allows different players to judge the same route differently.

There is a second distinction on the high-score screen. The game ranks
score per coin rather than simply the largest accumulated total. Buying
more health can extend a game without making its eventual result more
efficient. The same quotient also appears in other rules we will meet,
so money reaches farther into the dungeon than the health display alone
suggests.

As your health falls below 200, the display and sound become harder to
ignore. The health number pulses. A heartbeat becomes more frequent as
the remaining supply gets smaller. Spoken warnings can identify you by
color and class. Your problem is now audible to everybody at the cabinet,
including the friend standing nearest the food.

## A party can outlive one player

Gauntlet II allows a player to join a game already underway. A new arrival
does not need to wait until the surviving heroes die or finish their
level. After credit and character selection, the game looks for a usable
place near the existing party. Placement depends on finding room; a
packed position can prevent the join from completing.

That makes the party changeable. You might begin alone, be joined by two
friends, lose one of them in a dangerous passage, and carry on with the
other. Each player has personal health and possessions, while the maze
and the progress through it belong to the session.

Exits respect that distinction. One hero can leave while others are still
in the maze. The remaining players must settle their own business before
the normal handoff to a new level. The game has to remember who has left,
who is still alive here, and who has died; four people do not advance
through one shared sequence of player states.

If the last player dies beyond the opening level, a timed continue offer
can keep the session going. Otherwise the machine works through the
applicable game-over and initials-entry displays and returns to its idle
show. The control panel is unchanged throughout. The meaning of a button
depends on whether you are choosing a character, fighting, or responding
to the continue offer.

## A dungeon that changes its terms

Progress brings more than larger crowds. The stored mazes carry rules as
well as layouts. A familiar shape can have different movement or hazard
conditions. Some levels wrap at their edges. Walls can move or conceal
passages. An exit may not stay where you first saw it.

There are creatures whose encounters have their own structure. The thief
selects a victim and follows a trail that the victim's movement has left
in memory. The dragon combines several visible pieces with a small
program controlling its head and attacks. Learning when it can be hurt is
part of fighting it.

Treasure rooms interrupt the ordinary journey with timed collection and
an escape requirement. Secret objectives can lead to separate challenge
rooms and, if the relevant conditions are met, a code for the game's
original contest. These systems reward attention to rules that are not
all visible when a level begins.

Even the sequence of ordinary mazes has a longer memory than one game.
The opening five follow a fixed order. After that, the game's stored
rotation helps decide what comes next. Two visits to level six need not
show the same place, because the machine remembers something about
previous play.

There is plenty here to learn by watching and experimenting. Looking
inside the program gives us another kind of understanding: it lets us
connect a visible rule to the state that makes it possible, then ask
where else that state has consequences.

We can begin with something much smaller than a changing dungeon. Stand
an Elf in a corridor, hold Fire, and watch how long it takes before the
second arrow appears.

### Sources and further reading

- Controls, character selection, joining, health, inventory, and shot
  interactions: [Game subsystems](../doc/04_game_subsystems.md), especially
  sections 4, 6.4, 22, and 26. `main_start_game` is at `0x4800C`;
  `main_health_countdown` is at `0x466F6`.
- The four character tables and player-position data:
  [Data reference](../doc/05_data_reference.md).
- Opening mazes and selection state that persists between play sessions:
  [Maze catalog](../doc/06_maze_catalog.md), section 3.
- The remaining chapters develop the systems introduced here. The
  [contents](README.md) is the reading route; the
  [glossary](appendix_glossary.md) is available without reading ahead.

[Next: One arrow in the air](02_one_arrow.md)
