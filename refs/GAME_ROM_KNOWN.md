## 1. ROM Memory Map

### 1.1 Address Space Layout

| Region | Address Range | Size | Description |
|--------|--------------|------|-------------|
| **OS ROM** | `0x000000-0x00FFFF` | 64 KB | This ROM - bootstrap, OS, diagnostics, game support |
| **Slapstic ROM** | `0x038000-0x03FFFF` | 32 KB | Level data (bank-switched) |
| **Game ROM** | `0x040000-0x07FFFF` | 256 KB | Main game program |
| **Main RAM** | `0x800000-0x801FFF` | 8 KB | General-purpose RAM |
| **EEPROM** | `0x802001-0x802FFF` | ~4 KB | High scores, settings, statistics (odd bytes only) |
| **Hardware I/O** | `0x803000-0x8031FF` | 512 B | Input ports, watchdog, sound, LEDs |
| **Playfield RAM** | `0x900000-0x901FFF` | 8 KB | Playfield tile map |
| **MOB RAM** | `0x902000-0x903FFF` | 8 KB | Motion object (sprite) data |
| **Video RAM Spare** | `0x904000-0x904FFF` | 4 KB | OS working variables |
| **Alpha RAM** | `0x905000-0x905FFF` | 4 KB | Alphanumeric character overlay |
| **Color RAM** | `0x910000-0x9107FF` | 2 KB | Color palettes |
| **PF H-Scroll** | `0x930000-0x930001` | 2 B | Playfield horizontal scroll register |
| **PF V-Scroll** | `0x905f6e-0x905f6f` | 2 B | Playfield vertical scroll register |

### 1.2 Hardware I/O Ports

| Address | R/W | Description |
|---------|-----|-------------|
| `0x803001` | R | Player 1 inputs |
| `0x803003` | R | Player 2 inputs |
| `0x803005` | R | Player 3 inputs |
| `0x803007` | R | Player 4 inputs |
| `0x803009` | R | VBLANK status / SoundIOFull / Self-test switch |
| `0x80300F` | R | Read from sound processor |
| `0x803100` | W | Watchdog |
| `0x803120` | W | Hardware latch (bit 0 = LED/board enable) |
| `0x803121` | W | LED 1 |
| `0x803123` | W | LED 2 |
| `0x803125` | W | LED 3 |
| `0x803127` | W | LED 4 |
| `0x80312F` | W | Sound processor reset/control |
| `0x803140` | W | VBLANK acknowledge |
| `0x803150` | W | EEPROM unlock |
| `0x803170` | W | Interrupt control register |
| `0x803171` | W | Write to sound processor |
| `0x905f6f` | RW | Playfield ROM bank select |

### 1.3 Video RAM

| Address Range | Description |
|---------------|-------------|
| 0x900000 - 0x901fff | Playfield RAM |
| 0x902000 - 0x9027ff | MOB Picture |
| 0x902800 - 0x902fff | MOB Horizontal Position |
| 0x903000 - 0x9037ff | MOB Vertical Position |
| 0x903800 - 0x903fff | MOB Link |
| 0x904000 - 0x904fff | Video RAM Spare |
| 0x905000 - 0x905fff | Alphanumerics RAM |
| 0x910000 - 0x9101ff | Color RAM Alpha |
| 0x910200 - 0x9103ff | Color RAM MOB |
| 0x910400 - 0x9104ff | Color RAM Playfield Shadow |
| 0x910500 - 0x9105ff | Color RAM Playfield |
| 0x910600 - 0x9107ff | Color RAM Spare |

### 1.4 Status Register Bits at `0x803009`

| Bit | Description |
|-----|-------------|
| 0 | Player 1 start button (active low, used for boot wait) |
| 3 | Self-test switch (1 = self-test active) |
| 5 | Sound I/O full |
| 6 | VBLANK status (toggles each field) |

> **Superseded.** The bit 0 and bit 3 rows above are wrong and are kept only
> as the original note. The OS ROM never reads bit 0 of this port — the boot
> acknowledge waits poll bit 0 of `0x803001` (player 1 Magic) — and bit 3 is
> active low, reading 0 when the self-test switch is engaged. See
> `doc/01_hardware.md` §3.1 and `doc/02_os_rom.md` §5.7 for the verified
> version and the disassembled evidence.

## 2. Known ROM contents

### 2.1 Jump Table Entries

| Address | Target | Function Name |
|---------|--------|---------------|
| `0x40000` | `0x4014c` | `game_start` |
| `0x40000` | `game_start` | JMP to game entry point (must be `0x4EF9` + address) |
| `0x40006` | `game_vblank` | JMP to game VBLANK handler |
| `0x4000C` | `game_irq1` | JMP to game IRQ1 handler |
| `0x40012` | `game_irq3` | JMP to game IRQ3 handler |
| `0x40018` | `game_irq2` | JMP to game IRQ2 handler |
| `0x4001E` | `game_irq6` | JMP to game IRQ6 handler |
| `0x40024` | `game_exception` | JMP to game exception handler |
| `0x40030` | `game_pf_init` | JMP to playfield initialization |
| `0x40042` | `game_vblank_hook` | JMP to supplemental VBLANK handler (input reading) |
| `0x40048` | `game_attract` | JMP to game attract mode handler |
| `0x40054` | `game_eeprom_config` | Optional JMP to EEPROM configuration provider. Returns a 32-bit value in D0: bit 16 = EEPROM layout flag, bits 8-15 = high config byte, bits 0-7 = low config byte. Fallback: `0x10000`. Referenced at `0x21AC`. In Gauntlet: JMP `0x56EAA`. |


### 2.2 Game ROM Functions

| Address | Name | Description |
|---------|------|-------------|
| 0x4014c | game_start | Game entrypoint/startup (called from OS ROM) |
| 0x40528 | main_cycle_tport_and_ffield | Palette cycling for transporters & forcefields |
| 0x40628 | calc_score_per_coin | calculate score per coin |
| 0x40644 | input_debounce | copies player inputs into RAM |
| 0x40c78 | find_maze | puts address of next maze in 0x904b88 and a0, slapstic bank in d1 |
| 0x40e6a | monsters_everything | handle monster movements, slowmo, generators, shooting, monster animation, player potion usage, and more |
| 0x41750 | monster_find_and_shoot | monster id in d2, finds which player is closest and sets the monster's direction, and maybe shoots |
| 0x41b16 | find_unused_shot | something to do with finding unused shots |
| 0x42a66 | mainloop | the main loop for the game, runs in a loop forever |
| 0x42b6a | coincheck | |
| 0x42df4 | pick_character | |
| 0x42e9a | maze_randomplace | pass it a maze object id, it'll place it somewhere, returns location in d0 |
| 0x43360 | player_resetcounters | takes a player number, resets keys, potions, status, bonus mult, timers, etc |
| 0x4341e | player_resetall | reset all players |
| 0x436cc |  | something to do with random maze flags |
| 0x436fe |  | something to do with random maze flags |
| 0x43826 | slapstic_cmd_bitwise | slapstic bank change |
| 0x438ae | | something to do with setting up new maze/level |
| 0x43d8c| | seems to add random foods to a maze |
| 0x43f68 | maze_addrandompickups | adds random pickups based on maze header, difficulty, stolen items, etc |
| 0x44204 | game_new_setup | set up for new game |
| 0x449d4 | | set up the attract mode demo, maybe |
| 0x44ac2 | maze_setupnew | takes pointer to maze data, does new maze setup (not sure of entire set of tasks) |
| 0x44c7e | | something to do with dialogs |
| 0x4526a | maze_show | clear the alpha layer to show the level |
| 0x4529a | maze_hide | fill alpha layer to hide the level |
| 0x452d0 | setup_infopanel | set up the right-side info panel |
| 0x45866 | player_it_set | set player as it |
| 0x4590e | player_it_unset | set player as not it |
| 0x45aca | player_inv_update | update display of player inventory (keys/potions/powers) |
| 0x45be8 | stridx | takes pointer to string, returns offset of next null byte |
| 0x47c0e | | something to do with handling explosion animations |
| 0x47cfe | handle_tport | something to do with handling transporter |
| 0x486fe | secret_check | check to see if we should enter secret room? |
| 0x48754 | speech_welcome | takes player number, makes "welcome <whoever>" speech happen |
| 0x487ca | player_lowhealth | sets dying flag on player, does "is about to die" speech, etc |
| 0x488ca | player_coindrop | make coindrop noise, checks number of coins, adds to health, puts in "select character" mode |
| 0x48a36 | player_join2 | handle player joining, with sfx, sets the level they're on, resets food count, triggers speech, etc |
| 0x48bb6 | player_join | handle player joining |
| 0x490dc | monster_create_shot | takes monster mob id, direction of shot, and mob id to use for shot, creates a monster's shot |
| 0x492c0 | handle_generate | handles generating monsters from a generator, I think |
| 0x49446 | death_potion | handles death being killed by potion |
| 0x49498 | playfield_showscore | takes mob id and amount to score, overlays score for that mob dying (or that food being collected) at that spot |
| 0x495a6 | monster_playerhit | handles monster hitting a player - removes health, plays sounds, removes monster if needed (e.g. is a host), etc |
| 0x49a3c | death_damagetrack | tracks damage dealt by a death, removes the death if >= 200 |
| 0x49a98 | sound_player_hurt | takes the player id (and maybe something else) and if it's been long enough, plays an appropriate 'hurt' sound ("ow" or whatever) |
| 0x49d0e | | some kind of checking to see if the player got a high score |
| 0x4a124 | attract_highscores | shows the 4-way-split "high score per coin" attract screen
| 0x4ad4e | sound_speech_play | takes speech sound id, and plays it, unless speech is disabled in settings |
| 0x4ad76 | sound_play | takes a sound id, plays it |
| 0x4be24 | level_splash | show splash screen for new level |
| 0x4c1bc | maze_decode | takes pointer to maze data, handle decoding and setting up maze |
| 0x4c440 | dialog_first_encounter | handle "first encounter" dialogs (and not displaying them if it's not the first encounter) |
| 0x4c70a | | takes number of chars to clear, clears them in message buffer, adds mull terminator |
| 0x4c72a | player_give_item_with_message | takes player number and item id and gives item to the player, with dialog if needed |
| 0x4cb50 | | something to do with placing dialog boxes |
| 0x4d476 | | handles exiting the treasure room with people still active |
| 0x4d900 | player_activecount | returns number of active players (alive here, alive next level, swirling, or selecting characters) |
| 0x4dff6 | thief_target_calc | calculates player with highest value. adders to calculate value: shot power=0x3e8, extra speed=0x2bc, extra shot speed=0x1f4, extra magic power=0x12c, extra armor=0xc8, extra fight power=0x64, potions=0x3 each, bonus mult=0x1 each, keys=0x2 each |
| 0x4e122 | thief_exit | thief is done (or his target is gone), send him away |
| 0x4e432 | thief_setup | something to do with setting thief up |
| 0x4e4d8 | thief_timer_set | if there's a target, and it's an appropriate level, set a timer for thief based on wealth, level number, and other things |
| 0x4e7c0 | tport_find_id | takes the mob id of a transporter, returns the transporter id |
| 0x50224 | player_tport | something to do with player using transporter |
| 0x50616 | | something to do with player using transporter |
| 0x50662 | | something to do with player using transporter |
| 0x50ade | tport_check_dest | takes player number and mob id of possible destination, and returns 0 if we can transport there (1 if not) |
| 0x510fc | calc_direction | takes a source and destination location (for both, lower 5 bits are horizontal position, next 5 bits are vertical), calculates the direction from source to dest, and returns that value (0=up, 1=up right, etc) |
| 0x511ac | | something to do with handling collisions |
| 0x5214c | player_add_score_with_mult | takes player number and score to add, and multiplies the score by the player's bonus and adds it to the player's score |
| 0x52b06 | exit_get_id | takes a mob id, returns an exit id (uses the last exit in the list if mobid isn't an exit) |
| 0x52b40 | | handles player exiting, not sure the exact list of things |
| 0x52eca | maze_checknum | checks to see if the next maze number is valid. handles maze number wraparound if needed |
| 0x549ea | | something with dragon |
| 0x54ec6 | secret_getname | set up to get the player's name if they won the secret room |
| 0x56e58 | slapstic_cmd_bank0 | change to slapstic bank 0 |
| 0x56e6e | slapstic_cmd_bank3 | change to slapstic bank 3 |
| 0x56e84 | slapstic_cmd_bankX | change to slapstic bank based on input |
| 0x56eaa | slapstic_verify | checks slapstic, returns 0x1fffe if good |
| 0x5dc58 | mob_create | creates a mob on-screen, takes as args: new mob id, new tile number, position horizontal (with palette info bundled), position vertical (including X & Y sizes), maze object id for the mob, and direction of animation/travel |
| 0x5dcbc | moblist_insert | insert new item into the mob linked lists |
| 0x5dd72 | moblist_replace | takes source mob id, destination mob id, replaces the destination with the source, and unlinks the original destination |
| 0x5dda8 | moblist_remove | removes a given mob from the mob linked lists |
| 0x5ddda | moblist_remove_and_clear | removes a mob from the linked lists and clears... something? |
| 0x5df5a | | something to do with shot graphics |
| 0x5df68 | | something to do with shot graphics |
| 0x5df72 | | something to do with shots |
| 0x5df80 | exit_create_player_anim | creates the player exiting animation |
| 0x5df8e | tport_create_splodey | create the exploding animation thing for transporting |
| 0x5df9c | | create a splodey animation for "explosion" related to various things |
| 0x5e064 | | seems to unlink a shot when we don't need it any more... maybe player shots only? |
| 0x5e536 | pf_stamp_update | update a 2x2 stamp on the playfield, with optional palette. used for example for exit open/close animation |
| 0x5e584 | | seems to maybe be checking if a transporter destination |
| 0x5e892 | pf_floor_update | sets proper playfield pattern based on proximity to walls, etc |
| 0x5f31e | pf_replace | replaces whatever is at a given playfield location with something new, and fixes up walls and doors around it so they look right |
| 0x5f77a | pf_isdoor | takes playfield coordinates, 0 = not door, 1 = door intersection, 2 = horizontal door, 3 = vertical door |
| 0x5f7fa | pf_door_update_surrounding | given coordinates, check to see if positions around it are doors, and update the graphics for those locations |
| 0x5f880 | | something to do with setting the right door graphics |
| 0x5fc4e | getrandom | takes a max value and returns a random number up to that value |
| 0x5fc5e | pf_isff | check to see if a given coordinate has a forcefield |
| 0x5fcce | pf_palette_clear | clears the playfield palette, I think? |
| 0x5fd58 | memclear | takes a memory address and a number of longwords to clear, and clears them |
| 0x5fd6a | memcpy | takes a source address, a destination address, and a number of longwords to copy, and copies them |
| 0x5fde0 | supersorc_place | take a player number and a super sorcerer mob id, and find an empty spot behind the player, place them there, point them in the player's direction, and return the location |

### 2.3 Main Loop Functions

| Address | Name | Description |
|---------|------|-------------|
| 0x42a66 | g2mainloop | game main loop entry point |
| 0x44562 | main_attract | handle attract mode |
| 0x457c0 | main_score_display | displays player scores |
| 0x45c00 | main_open_doors | handle opening of doors |
| 0x4664c | main_handle_death | handle death things |
| 0x466f6 | main_health_countdown | handles automatic health lowering |
| 0x46caa | main_scroll_playfield | handle playfield scrolling |
| 0x46fea | main_handle_potions | handle potion usage |
| 0x4715e | main_score_update | handle updating player scores |
| 0x474f6 | main_handle_shots | handle various shots |
| 0x4800c | main_start_game | handle starting a new game |
| 0x49034 | main_move_monsters | handle moving the monsters |
| 0x4a53a | main_move_players | handle moving players around |
| 0x4ae20 | main_update_sound | handles sounds and the sound queue |
| 0x4ccbc | main_msgbox_countdown | handles the timer for displayed dialogs |
| 0x4d29e | main_treasure_timer | handles treasure room timer, handles the speech for it, etc |
| 0x4dcba | main_logo_updcolors | handles updating the colors of the logo |
| 0x4deb8 | main_start_thief | wait for timer then start thief on level |
| 0x4e8dc | main_thief_move | handle moving the thief |
| 0x5287c | main_exit_move | handle moving exits |
| 0x54454 | main_handle_dragon | handle dragon updates |
| 0x5e41a | main_walls_random_move | handle movement of random walls |
| 0x5e62a | main_walls_cyclic_move | handle movement of cyclic walls |


## 3. Known RAM Contents

### 3.1. Main RAM variables

| Address | Size | Name | Description |
|---------|------|------|-------------|
| 0x904000 | 2B | mazenum_current | Current maze (not level) number |
| 0x904004 | 2B | levelnum_current | Current level (not maze) number |
| 0x904006 | 2B | framecount | Frame counter |
| 0x904008 | 2B | scrollreg_H | Horizontal scroll |
| 0x90400a | 2B | scrollreg_V | Vertical scroll |
| 0x90400c | 2B | playfieldbank | Current playfield (maze?) bank |
| 0x90400e | 2B | maze_stride | added (plus 1) to existing maze number to get next maze |
| 0x904010 | 2B | maze_number | next level is this number + maze_stride |
| 0x904012 | 4B | eeprom_write_timer | countdown timer for when to next write eeprom data |
| 0x904016 | 2B | treas_mazerand_adder | Same as maze_stride, but for treasure rooms |
| 0x904018 | 2B | treas_mazerand_num | Same as maze_number, but for treasure rooms |
| 0x90401a | 2B | cyclic_wall_timer | Related to wall cycling |
| 0x90401c | 2B | cyclic_wall_phase | Related to wall cycling |
| 0x90401e | 2B | playfield_colorsave1 | Temp for saving old playfield color |
| 0x904020 | 2B | playfield_colorsave2 | Temp for saving old playfield color? |
| 0x904022 | 2B | potion_player | Which player used a potion |
| 0x904024 | 2B | collision_dist_H | horizontal object collision distance |
| 0x904026 | 2B | collision_dist_V | vertical object collision distance |
| 0x904028 | 2B | shothit_dist_H | horizontal shot distance |
| 0x90402a | 2B | shothit_dist_V | vertical shot distance |
| 0x90402c | 2B | | something to do with traps |
| 0x90402e | 2B | | something to do with stuns |
| 0x904030 | 2B | | something to do with transporter |
| 0x904032 | 2B | | something to do with transporter |
| 0x904034 | 2B | | something to do with transporter |
| 0x904036 | 4B | ptr_playfield_color1 | Pointer to 1st playfield colors |
| 0x90403a | 4B | ptr_playfield_color2 | Pointer to 2nd playfield colors |
| 0x90403e | 4B | ptr_playfield_color3 | Pointer to 3nd playfield colors |
| 0x904042 | 4B | | Pointer to something about color cycling forcefields |
| 0x904046 | 2B | forcefield_color | Color for forcefield |
| 0x904048 | 2B | | Something related to forcefields |
| 0x90404b | 8B | sound_queue | array of 1 byte sound ids in the queue |
| 0x904053 | 1B | sound_queue_head | Head of sound queue |
| 0x904054 | 1B | sound_queue_tail | Tail of sound queue |
| 0x904055 | 4B | player_potionsnum | Array of 1 byte counters for how many potions each player has |
| 0x90405a | 4B | player_keysnum | Array of 1 byte counters for how many keys each player has |
| 0x90405f | 4B | | Derived from player score per coin, might be difficulty-related? |
| 0x904063 | 1B | secret_player | Which player completed the secret trick |
| 0x904064 | 1B | secret_trick_last | Last secret trick completed |
| 0x904065 | 1B | secret_trick_id | Trick or task number? |
| 0x904066 | 2B | | array, I think 512 2B entries, something to do with mobs? D15-D13 are animation count, D12-D10 are direction of travel |
| 0x904866 | 2B | maze_decomp_htype1 | Maze decompression horizontal special element type 1 |
| 0x904868 | 2B | maze_decomp_htype2 | Maze decompression horizontal special element type 2 |
| 0x90486a | 2B | maze_decomp_vtype1 | Maze decompression vertical special element type 1 |
| 0x90486c | 2B | maze_decomp_vtype2 | Maze decompression vertical special element type 2 |
| 0x90486e | 2B | secret_need_hint | Set if next level should show a secret room hint |
| 0x904870 | 2B | secret_prev_maze | Store the current maze number when secret room triggered |
| 0x904872 | 1B | secret_tricks_flags | array of 4 1B entries, indexed by player number, used to track players' progress towards secret trick goal |
| 0x904878 | 2B | secret_possible_counter | counts down, when it hits 0 it's possible to enter the secret room |
| 0x90487a | 2B | secret_possible_start | starting value for secret_possible_counter |
| 0x90487c | 2B | | Something dragon-related? |
| 0x90487e | 1B | item_dlg_flags | flags for item use dialogs to only display once |
| 0x90487f | 1B | power_dlg_flags | flags for power dialogs ot only display once (might be reversed with item_dlg_flags) |
| 0x904880 | 2B | dragon_hits | number of hits on the dragon |
| 0x904882 | 2B | | possibly related to position of dragon's head |
| 0x904884 | 2B | | possibly related to position of dragon's head |
| 0x904890 | 2B | dragon_state | Current dragon state: 0x00 = normal, 0x01 = sleeping, 0x02 = stunned, 0x04 = turning, 0x08 = locked in |
| 0x904892 | 2B | | related to dragon head position. might be a timer? |
| 0x904894 | 2B | | possibly the dragon MOB id or something? |
| 0x90489c | 4B | ptr_exit_openclose_anim | pointer to exit open/close animation for current tileset |
| 0x9048a0 | 2B | | something to do with wall randomizer |
| 0x9048a2 | 2B | | something to do with wall randomizer |
| 0x9048a4 | 2B | | something to do with wall randomizer |
| 0x9048a6 | 2B | | something to do with wall randomizer |
| 0x9048a8 | 2B | | array indexed by player, something to do with shots |
| 0x8048b2 | 2B | poison_timer | timer for slowdown from poison (I think) |
| 0x9048bc | 2B | thief_speed | how fast the thief moves |
| 0x9048be | 2B | reflect_count | array of 4 2B entries, indexed by player number, holds number of times a player's shot has reflected |
| 0x9048c6 | 2B | escape_timer | number of frames since a player was last hit by a monster, all walls turn to exits at 20000 |
| 0x9048c8 | 2B | | array of 2B elements, might be indexed by player, might hold the location of the player in the maze, might affect camera location, too |
| 0x9048e0 | 2B[4] | player_powers | array of 4 2B elements, indexed by player number, holds powers that player has, indexed by enum defined elsewhere |
| 0x9048e8 | 2B[4] | player_character | array of 4 2B elements, indexed by player number, holds identity of character for player |
| 0x9048f0 | 2B[4] | player_joystick | indexed by player number, holds direction player's joystick was pressed last frame |
| 0x9048f8 | 2B[4] | lobber_shot_vec_h | maybe indexed by player, horizontal index for lobber shots (target?) |
| 0x904900 | 2B[4] | lobber_shot_vec_v | maybe indexed by player, vertical index for lobber shots (target?) |
| 0x904908 | 2B[4] | | indexed by player number, something involving player collisions |
| 0x90490c | 2B | idle_timer | counts up if nothing happening, eventually clears doors. 0xffff (-1) if doors already timed out |
| 0x90490e | 2B[4] | player_bonusmult | indexed by player, current bonus multiplier |
| 0x904916 | 2B | frame_overflow | frame overflow flag - frame took too long to render |
| 0x904918 | 2B | game_mode | game mode. 0 for normal play. other values in associated enum |
| 0x90491a | 2B | attract_legend | current legend screen number |
| 0x90491c | 4B | level_flags | flags for current level |
| 0x904920 | 2B | | indexed by player, seems to be copies of joystick direction and button flags? |
| 0x904928 | 2B | level_players_active | number of active players on a level |
| 0x90492a | 2B[8] | shot_timer_next | time until next demon/lobber shot |
| 0x90493a | 2B[4] | | related to when a player's score gets cleared, maybe? |
| 0x904942 | 2B[?] | | might be shot positions (0x0 = upper left, 0x3ff = lower right), array of unknown size |
| 0x90497c | 1B[4] | | related to explosion animation |
| 0x904980 | 4B[4] | player_health | indexed by player, player's current health |
| 0x904990 | 4B[4] | player_score | indexed by player, player's current score |
| 0x9049a0 | 1B[4] | player_status | indexed by player, 0x01 = alive on this level, 0x02 = alive on next level, 0x04 = entering initials, 0x08 = spinning in exit |
| 0x9049a4 | 2B[4] | player_facing_dir | indexed by player, direction of player facing, probably different from other places facing is determined. 0=up, 1=up/right, 2=right, 3=down/right, 4=down, 5=down/left, 6=left, 7=up/left |
| 0x9049ac | 2B[4] | player_fighting_dir | indexed by player, direction player is fighting. seems to be a different set of values: 1=up, 2=up/right, 3=right, 4=down/right, 5=down, 6=down/left, 7=left, 8=up/left |
| 0x9049b4 | 2B[4] | player_shooting | indexed by player, 0xffff (-1) if player is shooting, 0x0 otherwise |
| 0x9049bc | 2B[4] | | indexed by player, something to do with character animation state |
| 0x9049c4 | 2B[12] | | length possibly wrong. Direction player or mob shot is moving, maybe |
| 0x9049dc | 2B | player_it | player who is it (0x0 - 0x3) or 0xffff (-1) if nobody |
| 0x9049de | 2B | | something to do with mob IDs |
| 0x9049e0 | 2B | | something to do with mob IDs |
| 0x9049e2 | 2B | | something to do with game pricing |
| 0x9049e4 | 4B | dialog_first_encounter_flags | which dialog messages we've seen so far, matches to ROM structure somewhere, and a dialog flags enum |
| 0x9049e8 | 2B | treasure_timer | how long (ticks? not sure) we've been in the treasure room, I think |
| 0x9049ea | 4B | | coin count of some description |
| 0x9049ee | 2B | | something related to sounds |
| 0x9049f0 | 2B | | something related to sounds |
| 0x9049f2 | 2B | | something related to sounds |
| 0x9049f4 | 2B | | something related to sounds |
| 0x904a06 | 2B | exit_count | number of exits in maze (total number of positions, for moving exits) |
| 0x904a08 | 2B | exit_move_timer | timer until exit moves, probably |
| 0x904a0a | 2B | exit_open_id | possibly mob id of exit currently opening |
| 0x904a0c | 2B | exit_close_id | possibly mob id of exit currently closing |
| 0x904a10 | 4B | | something to do with logo colors (color cycling?) |
| 0x904a14 | 2B | | something to do with logo colors (color cycling?) |
| 0x904a16 | 2B | | something to do with logo colors (color cycling?) |
| 0x904a18 | 2B | | something to do with logo colors (color cycling?) |
| 0x904a1a | 2B | | something to do with logo colors (color cycling?) |
| 0x904a1c | 2B | | something to do with logo colors (color cycling?) |
| 0x904a1e | 2B | | something to do with logo colors (color cycling?) |
| 0x904a20 | 4B | | something to do with logo colors (color cycling?) |
| 0x904a24 | 2B | game_settings | game settings from eeprom, D15 = unknown, D14 = sound in attract mode, D13 = high score related, D12 = unknown (enable secret code?), D11 = disable speech, D10 = unknown, D8-D9 = coins to start, D5-D7 = difficulty, D0 - D4 = unknown |
| 0x904a26 | 2B[4] | | indexed by player, might be time left to enter initials? |
| 0x904a2e | 2B[4] | | indexed by player, related to initial entry acceleration |
| 0x904a36 | 2B[4] | | indexed by player, related to initial entry |
| 0x904a3a | 4B[4] | | indexed by player, buffer for storing initials during entry |
| 0x904a4a | 1B[4] | | indexed by player, calculated position in high score chart for this character |
| 0x904a4e | 2B | | related to delay time between levels |
| 0x904a50 | 1B[4] | player_treascount | count of treasures picked up by player |
| 0x904a54 | 2B[4] | player_stundelay | timer for player being stunned |
| 0x904a5c | 2B | death_hits | number of times death has been hit/shot |
| 0x904a64 | 2B | | possibly what part of the screen is visible (horizontally) |
| 0x904a66 | 2B | | possibly what part of the screen is visible (vertically) |
| 0x904a66 | 2B | | something to do with lobber shots |
| 0x904a6e | 2B[4] | | something to do with lobber shots |
| 0x904a76 | 2B[8] | | something related to doors |
| 0x904a86 | 2B[8] | | something related to doors |
| 0x904a96 | 4B | ptr_dialog_pos | pointer to dialog position in alphamem |
| 0x904a9a | 2B | dialog_box_width | dialog horizontal dimension |
| 0x904a9c | 2B | dialog_box_height | dialog vertical dimension |
| 0x904a9e | 2B | dialog_timer | pause timer for dialog display |
| 0x904aa0 | 2B | | something related to dialogs |
| 0x904aa2 | 2B | | something related to dialogs |
| 0x904aa4 | 1B[30] | | buffer related to dialogs |
| 0x904ac6 | 4B | | something related to welcoming players |
| 0x904aca | 1B[4] | | indexed by player, related to a player dying |
| 0x904ace | 2B[4] | | indexed by player, timer related to player dying |
| 0x904ad6 | 2B[4] | | indexed by player, related to how much damage player has taken |
| 0x904ade | 2B[4] | | indexed by player, related to how much damage player has taken or player health |
| 0x904af6 | 1B[4] | player_eatcount | indexed by player, number of foods they've eaten |
| 0x904afa | 2B[4] | | possibly timer related to players taking damage |
| 0x904b1a | 4B[4] | player_scorepercoin | indexed by player, calculated score per coin for player |
| 0x904b2a | 2B[4] | player_coincount | indexed by player, number of coins inserted |
| 0x904b32 | 2B[4] | player_onlevel | indexed by player, what level player is on |
| 0x904b3a | 2B[4] | player_dmgtaken_death | indexed by player, amount of damage taken from death |
| 0x904b42 | 2B[4] | | indexed by player, something related to player dying |
| 0x904b4a | 2B[4] | | indexed by player, something related to player dying |
| 0x904b52 | 2B | level_next | number of next level |
| 0x904b54 | 2B | maze_next | number of next maze |
| 0x904b56 | 2B | | score for a pile of money (e.g. from dead thief) |
| 0x904b58 | 2B | | floor color number |
| 0x904b5a | 2B | | wall color number |
| 0x904b5c | 2B | | floor pattern number |
| 0x904b5e | 2B | | wall pattern number |
| 0x904b60 | 2B | attract_count | number of times through attract sequence counter |
| 0x904b66 | 4B[4] | | something to do with gameplay demo inputs |
| 0x904b76 | 1B[4] | | something to do with gameplay demo inputs |
| 0x904b7a | 2B | | timer related to monster generation |
| 0x904b7c | 2B | attract_timer | timer until next attract screen |
| 0x904b7e | 2B | level_next_potion | level countdown to next hidden potion |
| 0x904b80 | 2B | level_next_treasuer | level countdown to next treasure room |
| 0x904b82 | 2B | attract_title_count | count of title screen, so we know when to do theme |
| 0x904b84 | 2B | level_tport_count | number of transporters on current level |
| 0x904b86 | 2B | | game count (not sure what this means) |
| 0x904b88 | 4B | ptr_maze_data | pointer to current maze data |
| 0x904b8c | 2B | maze_slapstic_cmd_offset | offset from slapstic command base to activate bank switch for current level |
| 0x904b98 | 2B | thief_victim_pos | last position of thief's target (tile number?)
| 0x904b9a | 2B | thief_victim | player number of richest player |
| 0x904b9c | 2B | | something to do with thief |
| 0x904b9e | 2B | thief_enter_time | timer for thief entrance to level |
| 0x904ba0 | 2B | thief_mode | thief's current mode, covered in enum |
| 0x904ba2 | 2B | | something for thief |
| 0x904ba4 | 2B | | something for thief |
| 0x904ba6 | 2B | | something for thief |
| 0x904ba8 | 4B | mugger_item_nextlevel | item that the mugger carried to the next level |
| 0x904bac | 4B | thief_item_nextlevel | item that the thief carried to the next level |
| 0x904bb0 | 4B | mugger_item_carried | item that the mugger is currently carrying |
| 0x904bb4 | 4B | thief_item_carried | item that the thief is currently carrying |
| 0x904bba | 2B | thief_start_location | location of thief victim at start of level |
| 0x904bbc | 2B | | something to do with thief animation |
| 0x904bc0 | 2B | | timer related to treasure room |
| 0x904bc2 | 2B | | related to treasure room timer countdown |
| 0x904bc4 | 2B[5] | | might be teleporter related |
| 0x904bce | 2B[5] | | something teleporter related |
| 0x904bd8 | 2B[5] | | something teleporter related |
| 0x904be2 | 2B[4] | | something teleporter related |
| 0x904bea | 2B[4] | | something teleporter related |
| 0x904bf4 | 2B[4] | | indexed by player, timer for flashing player for end of invisibility |
| 0x904bfc | 2B | random_seed | random number seed |


### 3.2. Known OS RAM Variables (may be read/written by gamne code)
| Address | Size | Name | Description |
|---------|------|------|-------------|
| `0x904F00` | 2B | `scroll_base` | Base value for scroll system |
| `0x904F02` | 2B | `scroll_speed` | Text scroll speed setting |
| `0x904F04` | 2B | `vblank_sync` | VBLANK synchronization counter |
| `0x904F06` | 2B | `scroll_direction` | Current scroll direction/offset |
| `0x904F08` | 2B | `scroll_counter` | Scroll frame counter |
| `0x904F0A` | 2B | `scroll_limit` | Scroll limit value |
| `0x904F0C` | 2B | `os_vblank_active` | 1 = OS handles VBLANK; 0 = game handles VBLANK |
| `0x904F0E` | 2B | `display_mode` | 0 = standard alpha; 1 = Gauntlet scrolling mode |
| `0x904F10` | ?? | `text_color` | Per-slot text color attributes |
| `0x904F18` | 4B | `text_effect_type` | Per-slot effect type (0=inactive, 1-7=active types) |
| `0x904F1C` | 8B | `text_effect_speed` | Per-slot speed/delay values (2 words) |
| `0x904F24` | 8B | `text_effect_counter` | Per-slot frame counters (2 words) |
| `0x904F2C` | 4B | `text_effect_phase` | Per-slot animation phase |
| `0x904F30` | 4B | `text_effect_step` | Per-slot step counter |
| `0x904F34` | 16B | `text_effect_desc` | Per-slot text descriptor pointers (4 longs) |
| `0x904F44` | 4B | `highscore_work_ptr` | Working pointer for high score operations |
| `0x904F8A` | 4B | `player_inputs_snapshot` | All 4 players' input state (snapshot from VBLANK) |
| `0x904F8E` | struct | `sound_queue` | Sound command queue structure |
| `0x904FA8` | struct | `eeprom_work` | EEPROM write request bitmap and work area |
| `0x904FC0` | 1B | `error_count` | Cumulative EEPROM error count |
| `0x904FEC` | 4B | `coin_counters` | Per-player coin counter accumulators |
| `0x904FF0` | 4B | `coin_totals` | Per-player total coins deposited |
| `0x904FF4` | 4B | `coin_pending` | Per-player pending coin credits |
| `0x904FF8` | 2B | `vblank_counter` | Monotonic VBLANK counter (incremented each frame) |
| `0x904FFA` | 1B | `eeprom_dirty_flag` | Non-zero if EEPROM needs flushing |
| `0x904FFC` | 4B | `eeprom_config_ptr` | Pointer to EEPROM configuration working area (allocated from stack) |


## 4. Useful Enums

### Alphachar Masks
| Name | Value |
|------|-------|
| ALPHACHAR_CHARNUM_MASK | 1023 |
| ALPHACHAR_PALETTE_PLAYER0 | 1024 |
| ALPHACHAR_PALETTE_PLAYER1 | 2048 |
| ALPHACHAR_PALETTE_PLAYER2 | 3072 |
| ALPHACHAR_PALETTE_PLAYER3 | 4096 |
| ALPHACHAR_PALETTE_BLINK | 12288 |
| ALPHACHAR_PALETTE_NUM_MASK | 15360 |
| ALPHACHAR_PALETTE_BANK_MASK | 16384 |
| ALPHACHAR_OPAQUE | 32768 |

### Alphachars
| Name | Value |
|------|-------|
| ALPHACHAR_KEY | 161 |
| ALPHACHAR_SWORD | 162 |
| ALPHACHAR_POTION | 163 |

### Character Numbers
| Name | Value |
|------|-------|
| CHAR_WARRIOR | 0 |
| CHAR_VALKYRIE | 1 |
| CHAR_WIZARD | 2 |
| CHAR_ELF | 3 |

### Character Powers (bit number)
| Name | Value |
|------|-------|
| POWER_SPEED_BIT | 0 |
| POWER_ARMOR_BIT | 1 |
| POWER_FIGHT_BIT | 2 |
| POWER_SHOTSPEED_BIT | 3 |
| POWER_SHOTPOWER_BIT | 4 |
| POWER_MAGIC_BIT | 5 |
| POWER_INVISIBILITY_BIT | 6 |
| POWER_REPULSIVE_BIT | 7 |
| POWER_REFLECT_BIT | 8 |
| POWER_TRANSPORT_BIT | 9 |
| POWER_SUPERSHOT_BIT | 10 |
| POWER_INVULN_BIT | 11 |

### Directions
| Name | Value |
|------|-------|
| DIRECTION_UP | 0 |
| DIRECTION_UPRIGHT | 1 |
| DIRECTION_RIGHT | 2 |
| DIRECTION_DOWNRIGHT | 3 |
| DIRECTION_DOWN | 4 |
| DIRECTION_DOWNLEFT | 5 |
| DIRECTION_LEFT | 6 |
| DIRECTION_MASK | 7 |
| DIRECTION_DN_MULT | 1024 |

### Dialog Flags
| Name | Value |
|------|-------|
| DLGFLAG_FOODHEALTH | 1 |
| DLGFLAG_SOMEFOODDESTROYED | 2 |
| DLGFLAG_COINSFORHEALTH | 4 |
| DLGFLAG_SAVEKEYS | 8 |
| DLGFLAG_POTIONBEFOREMAGIC | 16 |
| DLGFLAG_SAVEPOTIONS | 32 |
| DLGFLAG_SHOOTINGPOTION | 64 |
| DLGFLAG_SHOOTINGPOISON | 128 |
| DLGFLAG_HEALTHLOST_GHOST | 256 |
| DLGFLAG_HEALTHLOST_GRUNT | 512 |
| DLGFLAG_HEALTHLOST_DEMON | 1024 |
| DLGFLAG_HEALTHLOST_LOBBER | 2048 |
| DLGFLAG_HEALTHLOST_SORC | 4096 |
| DLGFLAG_POISONED | 8192 |
| DLGFLAG_HEALTHLOST_DRAGON | 16384 |
| DLGFLAG_HEALTHLOST_ACID | 32768 |
| DLGFLAG_HEALTHLOST_SUPERSORC | 65536 |
| DLGFLAG_HEALTHLOST_DEATH | 131072 |
| DLGFLAG_SHOTSNOTHURTYET | 262144 |
| DLGFLAG_POTIONUSED | 524288 |
| DLGFLAG_KILLTHIEF | 1048576 |
| DLGFLAG_STOLENNEXTLEVEL | 2097152 |
| DLGFLAG_SOMEWALLSDESTROYED | 4194304 |
| DLGFLAG_TRAPSWALLSDISAPPEAR | 8388608 |
| DLGFLAG_TRANSPORTERS | 16777216 |
| DLGFLAG_FULLKEYSPOTIONS | 33554432 |
| DLGFLAG_STUNTILES | 67108864 |
| DLGFLAG_SOMETREASURELOCKED | 134217728 |
| DLGFLAG_YOUAREIT | 268435456 |
| DLGFLAG_KILLMUGGER | 536870912 |
| DLGFLAG_FAKEEXIT | 1073741824 |
| DLGFLAG_FORCEFIELD | 2147483648 |

### Door Types
| Name | Value |
|------|-------|
| DOOR_NONE | 0 |
| DOOR_INTERSECTION | 1 |
| DOOR_HORIZ | 2 |
| DOOR_VERT | 3 |

### Dragon Activity (bit number)
| Name | Value |
|------|-------|
| DRAGON_SLEEPING_BIT | 0 |
| DRAGON_STUNNED_BIT | 1 |
| DRAGON_TURNING_BIT | 2 |
| DRAGON_LOCKED_BIT | 3 |

### Fixed MOB IDs
| Name | Value |
|------|-------|
| FIXEDMOB_SHOTPLAYER0 | 1 |
| FIXEDMOB_SHOTPLAYER1 | 2 |
| FIXEDMOB_SHOTPLAYER2 | 3 |
| FIXEDMOB_SHOTPLAYER4 | 4 |
| FIXEDMOB_SHOTDEMON0 | 5 |
| FIXEDMOB_SHOTDEMON1 | 6 |
| FIXEDMOB_SHOTDEMON2 | 7 |
| FIXEDMOB_SHOTDEMON3 | 8 |
| FIXEDMOB_SHOTLOBBER0 | 9 |
| FIXEDMOB_SHOTLOBBER1 | 10 |
| FIXEDMOB_SHOTLOBBER2 | 11 |
| FIXEDMOB_SHOTLOBBER3 | 12 |
| FIXEDMOB_SHOTSPLODEY0 | 13 |
| FIXEDMOB_SHOTSPLODEY1 | 14 |
| FIXEDMOB_SHOTSPLODEY2 | 15 |
| FIXEDMOB_SHOTSPLODEY3 | 16 |
| FIXEDMOB_SCORING0 | 17 |
| FIXEDMOB_SCORING1 | 18 |
| FIXEDMOB_SCORING2 | 19 |
| FIXEDMOB_SCORING3 | 20 |
| FIXEDMOB_EXITING0 | 21 |
| FIXEDMOB_EXITING1 | 22 |
| FIXEDMOB_EXITING2 | 23 |
| FIXEDMOB_EXITING3 | 24 |
| FIXEDMOB_TPORT0 | 25 |
| FIXEDMOB_TPORT1 | 26 |
| FIXEDMOB_TPORT2 | 27 |
| FIXEDMOB_TPORT3 | 28 |
| FIXEDMOB_TPORT4 | 29 |

### Game Modes
| Name | Value |
|------|-------|
| GAMEMODE_NORMAL | 0 |
| GAMEMODE_TREAS_EXIT | 1 |
| GAMEMODE_LEGEND | 65532 |
| GAMEMODE_DEMO | 65533 |
| GAMEMODE_TITLE | 65534 |
| GAMEMODE_SCORES | 65535 |

### Game Settings
| Name | Value |
|------|-------|
| GSETTING_COINHEALTH_125 | 1 |
| GSETTING_COINHEALTH_150 | 2 |
| GSETTING_COINHEALTH_175 | 3 |
| GSETTING_COINHEALTH_200 | 4 |
| GSETTING_COINHEALTH_225 | 5 |
| GSETTING_COINHEALTH_250 | 6 |
| GSETTING_COINHEALTH_300 | 7 |
| GSETTING_COINHEALTH_350 | 8 |
| GSETTING_COINHEALTH_400 | 9 |
| GSETTING_COINHEALTH_450 | 10 |
| GSETTING_COINHEALTH_500 | 11 |
| GSETTING_COINHEALTH_550 | 12 |
| GSETTING_COINHEALTH_600 | 13 |
| GSETTING_COINHEALTH_650 | 14 |
| GSETTING_COINHEALTH_700 | 15 |
| GSETTING_COINHEALTH_750 | 16 |
| GSETTING_COINHEALTH_800 | 17 |
| GSETTING_COINHEALTH_850 | 18 |
| GSETTING_COINHEALTH_900 | 19 |
| GSETTING_COINHEALTH_950 | 20 |
| GSETTING_COINHEALTH_1000 | 21 |
| GSETTING_COINHEALTH_1100 | 22 |
| GSETTING_COINHEALTH_1200 | 23 |
| GSETTING_COINHEALTH_1300 | 24 |
| GSETTING_COINHEALTH_1400 | 25 |
| GSETTING_COINHEALTH_1500 | 26 |
| GSETTING_COINHEALTH_1600 | 27 |
| GSETTING_COINHEALTH_1700 | 28 |
| GSETTING_COINHEALTH_1800 | 29 |
| GSETTING_COINHEALTH_1900 | 30 |
| GSETTING_COINHEALTH_2000 | 31 |
| GSETTING_DIFFICULTY_MASK | 224 |
| GSETTING_COINTOSTART_MASK | 768 |
| GSETTING_TEXT_REDUCE | 1024 |
| GSETTING_SPEECH_DISABLE | 2048 |
| GSETTING_RESET_FLAG | 4096 |
| GSETTING_ALLOW_CONTEST_FLAG | 8192 |
| GSETTING_ATTRACT_SOUNDS | 16384 |
| GSETTING_SCORE_RESET_FLAG | 32768 |

### Joystick Inputs (bit number)
| Name | Value |
|------|-------|
| JOY_MAGIC_BIT | 0 |
| JOY_FIRE_BIT | 1 |
| JOY_SPARE1_BIT | 2 |
| JOY_SPARE2_BIT | 3 |
| JOY_RIGHT_BIT | 4 |
| JOY_LEFT_BIT | 5 |
| JOY_DOWN_BIT | 6 |
| JOY_UP_BIT | 7 |

### Level Flags 1
| Name | Value |
|------|-------|
| LFLAG1_ODDANGLE_GHOSTS | 1 |
| LFLAG1_ODDANGLE_GRUNTS | 2 |
| LFLAG1_ODDANGLE_DEMONS | 4 |
| LFLAG1_ODDANGLE_LOBBERS | 8 |
| LFLAG1_ODDANGLE_SORCERERS | 16 |
| LFLAG1_ODDANGLE_AUX_GRUNTS | 32 |
| LFLAG1_ODDANGLE_DEATHS | 64 |
| LFLAG1_INVIS_TRAPWALLS | 128 |

### Level Flags 2
| Name | Value |
|------|-------|
| LFLAG2_FAST_GHOSTS | 1 |
| LFLAG2_FAST_GRUNTS | 2 |
| LFLAG2_FAST_DEMONS | 4 |
| LFLAG2_FAST_LOBBERS | 8 |
| LFLAG2_FAST_SORCERERS | 16 |
| LFLAG2_FAST_AUX_GRUNTS | 32 |
| LFLAG2_FAST_DEATHS | 64 |
| LFLAG2_INVIS_ALLWALLS | 128 |

### Level Flags 3
| Name | Value |
|------|-------|
| LFLAG3_RANDOMFOOD_0 | 0 |
| LFLAG3_RANDOMFOOD_1 | 1 |
| LFLAG3_RANDOMFOOD_2 | 2 |
| LFLAG3_RANDOMFOOD_3 | 3 |
| LFLAG3_RANDOMFOOD_4 | 4 |
| LFLAG3_RANDOMFOOD_5 | 5 |
| LFLAG3_RANDOMFOOD_6 | 6 |
| LFLAG3_RANDOMFOOD_7 | 7 |
| LFLAG3_WALLS_CYCLIC | 8 |
| LFLAG3_WALLS_DELETABLE1 | 16 |
| LFLAG3_WALLS_DELETABLE2 | 32 |
| LFLAG3_EXIT_MOVES | 64 |
| LFLAG3_EXIT_CHOOSEONE | 128 |

### Level Flags 4
| Name | Value |
|------|-------|
| LFLAG4_SHOTS_STUN | 1 |
| LFLAG4_SHOTS_HURT | 2 |
| LFLAG4_TRAPS_LOCAL | 4 |
| LFLAG4_TRAPS_RANDOM | 8 |
| LFLAG4_WRAP_V | 16 |
| LFLAG4_WRAP_H | 32 |
| LFLAG4_EXIT_FAKE | 64 |
| LFLAG4_PLAYER_OFFSCREEN | 128 |

### Maze Numbers
| Name | Value |
|------|-------|
| MAZENUM_FIRST | 5 |
| MAZENUM_LAST | 101 |
| MAZENUM_DEMO | 102 |
| MAZENUM_LEGEND_SCORES | 103 |
| MAZENUM_TRESURE_FIRST | 104 |
| MAZENUM_TREASURE_LAST | 114 |
| MAZENUM_SECRET | 115 |

### Maze Object IDs
| Name | Value |
|------|-------|
| MAZEOBJ_TILE_FLOOR | 0 |
| MAZEOBJ_TILE_STUN | 1 |
| MAZEOBJ_WALL_REGULAR | 2 |
| MAZEOBJ_WALL_MOVABLE | 3 |
| MAZEOBJ_WALL_SECRET | 4 |
| MAZEOBJ_WALL_DESTRUCTABLE | 5 |
| MAZEOBJ_WALL_RANDOM | 6 |
| MAZEOBJ_WALL_TRAPCYC1 | 7 |
| MAZEOBJ_WALL_TRAPCYC2 | 8 |
| MAZEOBJ_WALL_TRAPCYC3 | 9 |
| MAZEOBJ_TILE_TRAP1 | 10 |
| MAZEOBJ_TILE_TRAP2 | 11 |
| MAZEOBJ_TILE_TRAP3 | 12 |
| MAZEOBJ_DOOR_HORIZ | 13 |
| MAZEOBJ_DOOR_VERT | 14 |
| MAZEOBJ_PLAYERSTART | 15 |
| MAZEOBJ_EXIT | 16 |
| MAZEOBJ_EXITTO6 | 17 |
| MAZEOBJ_MONST_GHOST | 18 |
| MAZEOBJ_MONST_GRUNT | 19 |
| MAZEOBJ_MONST_DEMON | 20 |
| MAZEOBJ_MONST_LOBBER | 21 |
| MAZEOBJ_MONST_SORC | 22 |
| MAZEOBJ_MONST_AUX_GRUNT | 23 |
| MAZEOBJ_MONST_DEATH | 24 |
| MAZEOBJ_MONST_ACID | 25 |
| MAZEOBJ_MONST_SUPERSORC | 26 |
| MAZEOBJ_MONST_IT | 27 |
| MAZEOBJ_GEN_GHOST1 | 28 |
| MAZEOBJ_GEN_GHOST2 | 29 |
| MAZEOBJ_GEN_GHOST3 | 30 |
| MAZEOBJ_GEN_GRUNT1 | 31 |
| MAZEOBJ_GEN_GRUNT2 | 32 |
| MAZEOBJ_GEN_GRUNT3 | 33 |
| MAZEOBJ_GEN_DEMON1 | 34 |
| MAZEOBJ_GEN_DEMON2 | 35 |
| MAZEOBJ_GEN_DEMON3 | 36 |
| MAZEOBJ_GEN_LOBBER1 | 37 |
| MAZEOBJ_GEN_LOBBER2 | 38 |
| MAZEOBJ_GEN_LOBBER3 | 39 |
| MAZEOBJ_GEN_SORC1 | 40 |
| MAZEOBJ_GEN_SORC2 | 41 |
| MAZEOBJ_GEN_SORC3 | 42 |
| MAZEOBJ_GEN_AUX_GRUNT1 | 43 |
| MAZEOBJ_GEN_AUX_GRUNT2 | 44 |
| MAZEOBJ_GEN_AUX_GRUNT3 | 45 |
| MAZEOBJ_TREASURE | 46 |
| MAZEOBJ_TREASURE_LOCKED | 47 |
| MAZEOBJ_TREASURE_BAG | 48 |
| MAZEOBJ_FOOD_DESTRUCTABLE | 49 |
| MAZEOBJ_FOOD_INVULN | 50 |
| MAZEOBJ_POT_DESTRUCTABLE | 51 |
| MAZEOBJ_POT_INVULN | 52 |
| MAZEOBJ_KEY | 53 |
| MAZEOBJ_POWER_INVIS | 54 |
| MAZEOBJ_POWER_REPULSE | 55 |
| MAZEOBJ_POWER_REFLECT | 56 |
| MAZEOBJ_POWER_TRANSPORT | 57 |
| MAZEOBJ_POWER_SUPERSHOT | 58 |
| MAZEOBJ_POWER_INVULN | 59 |
| MAZEOBJ_MONST_DRAGON | 60 |
| MAZEOBJ_HIDDENPOT | 61 |
| MAZEOBJ_TRANSPORTER | 62 |
| MAZEOBJ_FORCEFIELDHUB | 63 |

### MOB Perspectives
| Name | Value |
|------|-------|
| 0x0 | up |
| 0x2 | upright |
| 0x4 | right |
| 0x6 | downright |
| 0x8 | down |
| 0xa | downleft |
| 0xc | left |
| 0xe | upleft |

### Player Status
| Name | Value |
|------|-------|
| PSTATUS_ALIVEHERE | 1 |
| PSTATUS_ALIVENEXT | 2 |
| PSTATUS_INITIALS | 4 |
| PSTATUS_EXITING | 8 |
| PSTATUS_SELECT | 16 |
| PSTATUS_SCODE | 32 |

### Secret Tricks
| Name | Value | Description |
|------|-------|-------------|
| TRICK_NONE | 0 | No trick |
| TRICK_TRANSPORT1 | 1 | Try Transportability (onto demon) |
| TRICK_TRANSPORT2 | 2 | Try Transportability (onto death) |
| TRICK_TRANSPORT3 | 3 | Try Transportability (into exit) |
| TRICK_TRANSPORT4 | 4 | Try Transportability (into exit) |
| TRICK_WATCHSHOOT1 | 5 | Watch What You Shoot (shoot foods) |
| TRICK_WATCHSHOOT2 | 6 | Watch What You Shoot (shoot secret walls) |
| TRICK_SAVESUPERSHOTS | 7 | Save Super Shots |
| TRICK_NOUSEINVUL | 8 | Don't Use Invulnerability |
| TRICK_NOGETHIT | 9 | Don't Get Hit (while killing a dragon) |
| TRICK_PUSHWALL | 10 | Try Pushing a Wall |
| TRICK_NOFOOLED | 11 | Don't Be Fooled |
| TRICK_NOGREEDY1 | 12 | Don't Be Greedy (no keys or potions) |
| TRICK_NOGREEDY2 | 13 | Don't Be Greedy (no treasure) |
| TRICK_DIET | 14 | Go On a Diet (no food) |
| TRICK_BEPUSHY | 15 | Be Pushy |
| TRICK_IT | 16 | IT Could Be Nice |
| TRICK_NOHURTFRIENDS | 17 | Don't Hurt Friends |

### Maze Horizontal and Vertical Types
| Range | Description |
|------|-------|
| 0x00 - 0x3F | Repeat this type |
| 0x40 - 0x7F | Skip N spaces and then add this type (mask 0x40) |
| 0x80 - 0xBF | Add this type and then skip N spaces (mask 0x80) |
| 0xC0 - 0xFF | Repeat wall N times and then add this type (mask 0xc0) |

### Maze Compression Bytecodes
| Range | Description |
|-------|-------------|
| 0x00 - 0x3F | Add one of this kind (from element list) (mask 0x3F) |
| 0x40 - 0x4f | Use HT1 w/ N = 1 .. 16 |
| 0x50 - 0x5f | Use VT1 w/ N = 1 .. 16 |
| 0x60 - 0x6f | Use HT2 w/ N = 1 .. 16 |
| 0x70 - 0x7f | Use VT2 w/ N = 1 .. 16 |
| 0x80 - 0x9f | Repeat last type 1 to 32 times |
| 0xa0 - 0xaf | Repeat wall horizontally 1 to 16 times |
| 0xb0 - 0xbf | Repeat wall vertically 1 to 16 times |
| 0xc0 - 0xff | Skip 1 to 32 times than add wall |

### Thief Modes
| Name | Value |
|------|-------|
| THIEF_DEAD | 0 |
| THIEF_PURSUE | 1 |
| THIEF_ESCAPE | 2 |
| THIEF_DODGE_BIT | 3 |
| THIEF_JUMPJUMP | 4 |
| THIEF_ENTER_OK_MUGGER_BIT | 5 |
| THIEF_IS_MUGGER_BIT | 7 |
| THIEF_DODGE | 8 |
| THIEF_ENTER_OK | 16 |
| THIEF_ENTER_OK_MUGGER | 32 |
| THIEF_IS_MUGGER | 128 |

## Data Structures

### Maze Data
| offset | length | name | description |
|--------|--------|------|-------------|
| 0x00 | 1B | secret_trick | see secret trick enum |
| 0x01 | 1B | level_flags_1 | see enums |
| 0x01 | 1B | level_flags_2  | see enums |
| 0x01 | 1B | level_flags_3  | see enums |
| 0x01 | 1B | level_flags_4  | see enums |
| 0x01 | 1B | playfield_patterns | |
| 0x01 | 1B | playfield_colors | |
| 0x01 | 1B | horizontal_type_1 | |
| 0x01 | 1B | horizontal_type_2 | |
| 0x01 | 1B | vertical_type_1 | |
| 0x01 | 1B | vertical_type_2 | |
| 0x01 | variable | level_data| |

### Palette (with alpha)
| offset | length | name | description |
|--------|--------|------|-------------|
| 0x00 | 2B | color0 | irgbcolor format |
| 0x02 | 2B | color1 | irgbcolor format |
| 0x04 | 2B | color2 | irgbcolor format |
| 0x06 | 2B | color3 | irgbcolor format |
