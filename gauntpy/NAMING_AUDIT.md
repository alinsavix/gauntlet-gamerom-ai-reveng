# gauntpy naming audit

This report records the naming audit completed in commit `bc2139a`. It compares
the Python reimplementation with the address-associated names in
[`../doc/07_function_index.md`](../doc/07_function_index.md) and
[`../doc/05_data_reference.md`](../doc/05_data_reference.md). Those references
are canonical for one-to-one ROM routines, modeled RAM fields, and literal ROM
tables.

## Result

No unresolved one-to-one naming discrepancy remains in the audited surfaces.

| Surface | Result |
|---|---:|
| Modeled `GameState` fields renamed | 35 |
| Direct Python routines renamed | 36 |
| Table-definition changes | 40 |
| Unclassified one-to-one discrepancies | 0 |

The table work comprises 39 identifier replacements and one dependent alias
correction (`_SPAWN_HEALTH` now references the canonical
`_MAZEOBJ_HSIZE_TIER_TBL`).

## Method

1. Treat the ROM address as identity.
2. Take the primary name for that address from `doc/07_function_index.md` or
   `doc/05_data_reference.md`.
3. Rename a Python symbol when it represents that ROM object one-to-one.
4. Retain a Python-specific name only at an explicit representation boundary.
5. Record compatibility migrations for names that appeared in persisted files.
6. Enforce the result through `tests/test_rom_function_audit.py`.

## Modeled RAM fields

| Previous Python name | Canonical name |
|---|---|
| `vblank_flag` | `vblank_semaphore` |
| `player_walk_dirs` | `player_joystick` |
| `forcefield_hurt_timer` | `ff_hurt_timer` |
| `shot_sep_h` | `shothit_dist_H` |
| `shot_sep_h_abs` | `collision_dist_H` |
| `shot_sep_v` | `shothit_dist_V` |
| `shot_sep_v_abs` | `collision_dist_V` |
| `spawn_probability_bonus` | `monster_spawn_probability_bonus` |
| `cull_rect_x` | `monster_cull_h_origin` |
| `cull_rect_y` | `monster_cull_v_origin` |
| `forcefield_step` | `ff_cycle_index` |
| `forcefield_step_timer` | `ff_cycle_timer` |
| `forcefield_segments` | `ff_segment_table` |
| `cyclic_wall_timer` | `wallcycle_time` |
| `cyclic_wall_phase` | `wallcycle_type` |
| `cyclic_wall_assign` | `cycle_phase_assignments` |
| `random_wall_timer` | `randwall_timer` |
| `random_wall_low_mark` | `randwall_low_watermark` |
| `random_wall_target` | `randwall_target` |
| `random_wall_current` | `randwall_current` |
| `player_tile_pos` | `player_tile_or_tport_dest` |
| `dialog_box_width` | `dialog_dim_H` |
| `dialog_box_rows` | `dialog_dim_V` |
| `exit_move_timer` | `exit_timer` |
| `secret_winner` | `trick_player` |
| `secret_trick_id` | `trick_tasknum` |
| `secret_trick_last` | `trick_last` |
| `bonus_timer` | `global_ui_delay_timer` |
| `sound_queue` | `soundqueue` |
| `sound_holdoff` | `speech_counter` |
| `sound_retry_count` | `sound_cpu_retry_count` |
| `eeprom_write_timer` | `timer_eepromwrite` |
| `eeprom_settings_cache` | `eeprom_cache_settings` |
| `maze_resume` | `mazerand_num` |
| `maze_stride` | `mazerand_adder` |

## Direct routines

| Previous Python name | Canonical name |
|---|---|
| `_load_legend_page` | `load_legend_page` |
| `_scroll_set_position` | `set_scroll_pos` |
| `maze_show_alpha` | `maze_show` |
| `setup_dragon_segments` | `dragon_setup_segments` |
| `_update_dragon_pose` | `dragon_head_pose_update` |
| `_tile_near_screen` | `tile_near_screen_test` |
| `_dragon_find_free_shot_slot` | `dragon_find_free_shot_slot` |
| `_dragon_fire_setup` | `dragon_fire_setup` |
| `_count_active_players` | `player_activecount` |
| `secret_check_winner` | `secret_bonus_earned` |
| `_is_blank_floor` | `pf_isblankfloor` |
| `_draw_door_graphic` | `pf_door_draw_xy` |
| `refresh_surrounding_door_graphics` | `pf_door_update_surrounding_xy` |
| `setup_door_graphics` | `maze_doors_setup` |
| `_transporter_id` | `tport_find_id` |
| `_refresh_monster_picture` | `monster_update_anim_tile` |
| `_shooter_in_view` | `monster_shooter_in_view` |
| `_face_after_contact` | `apply_direction_from_delta` |
| `_find_free_shot_slot` | `find_unused_shot` |
| `_tile_on_screen` | `tile_on_screen_d4` |
| `_supersorc_place` | `supersorc_place` |
| `_tile_on_screen_test` | `tile_on_screen_test` |
| `tport_arrival_interact` | `scan_move_path_interactions` |
| `door_open_start` | `door_record_endpoints` |
| `write_info_panel_backdrop` | `maze_hide` |
| `write_high_score_screen` | `attract_highscores` |
| `write_player_initials_entry` | `draw_player_initials_entry` |
| `_draw_player_score` | `draw_player_score` |
| `_draw_player_health` | `draw_player_health` |
| `_position_dialog_box` | `dialog_position_box` |
| `demo_message_show` | `demo_speech_cmd` |
| `player_init_for_coin` | `player_coindrop` |
| `_score_add` | `player_add_score_with_mult` |
| `_dragon_proximity` | `dragon_player_proximity` |
| `_pf_replace` | `pf_replace` |
| `_candidate_core` | `shot_collision_candidate_core` |

## ROM tables

| Previous Python name | Canonical name |
|---|---|
| `TRANSPORTER_COLOR_CYCLE` | `TPORT_PALETTE_CYCLE_BLOCKS` |
| `_TITLE_MOTION_FULL` | `_LOGO_MOTION_PROGRAM_FULL` |
| `_HEAD_HDELTA` | `_DRAGON_HEAD_HDELTA` |
| `_HEAD_VDELTA` | `_DRAGON_HEAD_VDELTA` |
| `_EXIT_MOVE_STRIDE` | `_EXIT_ROTATION_OFFSET_BY_COUNT` |
| `_CHALLENGE_TIMER_RANDOM` | `_CHALLENGE_TIMER_RANDOM_MINUTES` |
| `_TREASURE_FAKE_COUNTDOWN` | `_TREASURE_FAKE_COUNTDOWN_SEQUENCES` |
| `_FORCEFIELD_DELAY_PROFILES` | `_FORCEFIELD_CYCLE_DELAY_PROFILES` |
| `_HURT_SPEECH_SOUNDS` | `_CHARACTER_HURT_SOUND_BANKS` |
| `_SPAWN_PROB_TABLE` | `_MONSTER_SPAWN_PROBABILITY_TABLE` |
| `_MONSTER_CONTACT_DAMAGE_TBL` | `_MONSTER_CONTACT_DAMAGE_TABLE` |
| `_MAZEOBJ_HSIZE_TIER` | `_MAZEOBJ_HSIZE_TIER_TBL` |
| `_SHOOT_AXIS_THRESHOLDS` | `_MONSTER_SHOOT_AXIS_THRESHOLDS` |
| `_MONSTER_ODDANGLE_TBL` | `_MONSTER_ODDANGLE_TABLE` |
| `_GEN_CANDIDATE_COL` | `_GENERATOR_CELL_DX` |
| `_GEN_CANDIDATE_ROW` | `_GENERATOR_CELL_DY` |
| `_GEN_CANDIDATE_DIR` | `_GENERATOR_SPAWN_DIRECTION` |
| `_OCCUPANCY_NEIGHBOUR_COL` | `_SPAWN_CANDIDATE_COLUMN_DELTA` |
| `_OCCUPANCY_NEIGHBOUR_ROW` | `_SPAWN_CANDIDATE_ROW_DELTA` |
| `_WALK_NIBBLE_TO_DIRECTION` | `_JOYSTICK_NIBBLE_TO_DIRECTION` |
| `_SUPERSORC_BIAS` | `_SUPERSORC_DIRECTION_BIAS` |
| `_SUPERSORC_RUN` | `_SUPERSORC_PROBE_STEPS` |
| `_HEALTH_SOUND_MASK_TABLE` | `_HEARTBEAT_MASK_TABLE` |
| `_HEARTBEAT_SOUND` | `_HEARTBEAT_SOUND_TABLE` |
| `_PLAYER_SHOT_SOUND` | `_SHOT_REFLECT_SOUND_TBL` |
| `_SHOT_SPAWN_DH` | `_SHOT_REFLECT_HDELTA` |
| `_SHOT_SPAWN_DV` | `_SHOT_REFLECT_VDELTA` |
| `_PLAYER_DEATH_PICTURE` | `_ANIM_TABLE_IDLE` |
| `_PLAYER_IDLE_PICTURE` | `_ANIM_TABLE_IDLE` |
| `_PLAYER_WALKING_PICTURE` | `_ANIM_TABLE_WALKING` |
| `_PLAYER_FIGHTING_PICTURE` | `_ANIM_TABLE_FIGHTING` |
| `_PLAYER_SHOOTING_PICTURE` | `_ANIM_TABLE_SHOOTING` |
| `_REPULSE_TIMER_INIT` | `_CHARACTER_REPULSE_TIMER_INIT` |
| `_RANDOM_FOOD_POPUP` | `_PICKUP_SCORE_POPUP_TYPES` |
| `_DEATH_POTION_SCORE` | `_DEATH_POTION_SCORE_TABLE` |
| `_DEATH_POTION_POPUP` | `_DEATH_POTION_POPUP_TYPE_TABLE` |
| `_SCORE_POPUP_PICTURE` | `_SCORE_POPUP_PICTURE_TABLE` |
| `_STEALABLE_POWER_MASKS` | `_THIEF_STEALABLE_POWER_MASKS` |
| `_THIEF_DIRECTION_STEP_FLAGS` | `_THIEF_DIRECTION_STEP_SIZE` |

`_SPAWN_HEALTH` retained its name because it is a Python view rather than a
separate ROM table; its source was corrected from `_MAZEOBJ_HSIZE_TIER` to
`_MAZEOBJ_HSIZE_TIER_TBL`.

## Persisted-data compatibility

- Schema-1 F4 state dumps translate every previous `GameState` field through
  `_SCHEMA_1_RENAMED_FIELDS`.
- EEPROM JSON accepts legacy `maze_resume` and `maze_stride` keys when canonical
  keys are absent. The next save writes `mazerand_num` and `mazerand_adder`.
- The deterministic scripted-run golden uses `vblank_semaphore`.

## Remaining intentional discrepancies

These are representation differences, not unresolved naming drift.

| Category | Reason |
|---|---|
| Merged or decomposed routines | Python may combine assembly wrappers/shared bodies or split interrupt work among state writers. `ROM_FUNCTION_AUDIT.csv` records the equivalent owner. |
| `MobTable` methods | The class encapsulates multiple MOB list, insertion, removal, relocation, and depth-placement leaves rather than exposing every ABI entry. |
| Player-record fields | Fields on a `Player` object omit a redundant `player_` prefix that is necessary for global ROM arrays. |
| `player_in_maze` | This is a polarity-normalized Python view of the ROM's `player_tport_phase`, not a second one-to-one word. |
| Sound queue indices | Python list operations replace the ROM ring's separate byte buffer and head/tail words. |
| Host/container state | Diagnostics, snapshots, decoded maze objects, and renderer caches have no one-to-one arcade RAM identity. |
| Slapstic and ABI veneers | gauntpy consumes decoded maze data and does not emulate bank-switch command leaves, CPU traps, stack veneers, or register-entry aliases. |

The exhaustive callable-level exceptions remain in
[`ROM_FUNCTION_AUDIT.csv`](ROM_FUNCTION_AUDIT.csv), with a human-readable
function-coverage overview in
[`ROM_FUNCTION_AUDIT.md`](ROM_FUNCTION_AUDIT.md).

## Regression coverage

`tests/test_rom_function_audit.py` now:

- joins all 322 callable rows to the canonical function index;
- imports direct Python ports under their canonical names;
- verifies crosswalk source paths;
- binds addressed `GameState` fields to `doc/05_data_reference.md`; and
- binds literal table identifiers to their documented addresses.

The completed audit passed both full gauntpy modes:

- ROM-backed: 2,450 passed, 10 skipped.
- ROM-free: 2,201 passed, 259 skipped.

