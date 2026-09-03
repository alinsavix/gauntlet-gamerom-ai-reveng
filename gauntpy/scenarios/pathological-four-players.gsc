format = gauntpy-synthetic-maze-v1
name = pathological-four-players
description = Four heroes issue concurrent movement, Fire, and Magic input.
frames = 900
level = 16
seed = 0
character = elf
health = 20000
input = idle

[events]
0 input p1 down
0 input p2 left
0 input p3 right
0 input p4 up
60 input p1 down-right
60 input p2 up-left
60 input p3 down-right
60 input p4 up-left
120 input p1 idle+magic
120 input p2 idle+magic
120 input p3 idle+magic
120 input p4 idle+magic
123 input p1 idle
123 input p2 idle
123 input p3 idle
123 input p4 idle
150 input p1 fire
150 input p2 fire
150 input p3 fire
150 input p4 fire
210 input p1 up-right
210 input p2 down-left
210 input p3 down-right
210 input p4 up-left
270 input p1 idle+magic
270 input p2 idle+magic
270 input p3 idle+magic
270 input p4 idle+magic
273 input p1 idle
273 input p2 idle
273 input p3 idle
273 input p4 idle
300 input p1 fire
300 input p2 fire
300 input p3 fire
300 input p4 fire
360 input p1 left
360 input p2 right
360 input p3 left
360 input p4 right
420 input p1 idle+magic
420 input p2 idle+magic
420 input p3 idle+magic
420 input p4 idle+magic
423 input p1 idle
423 input p2 idle
423 input p3 idle
423 input p4 idle
450 input p1 fire
450 input p2 fire
450 input p3 fire
450 input p4 fire
510 input p1 idle
510 input p2 idle
510 input p3 idle
510 input p4 idle

[maze]
################################
#..............................#
#............................E.#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#...............@..............#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
#..............................#
################################
