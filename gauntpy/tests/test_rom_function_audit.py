"""The ROM/Python audit must classify every callable entry exactly once."""

from __future__ import annotations

import csv
from dataclasses import fields
import importlib
from pathlib import Path
import re

from gauntpy.state import GameState


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "doc" / "generated" / "callable_contract_coverage.csv"
CROSSWALK = ROOT / "gauntpy" / "ROM_FUNCTION_AUDIT.csv"
FUNCTION_INDEX = ROOT / "doc" / "07_function_index.md"
DATA_REFERENCE = ROOT / "doc" / "05_data_reference.md"

MISSING = set()
PARTIAL = set()
OMITTED = {
    0x40000, 0x40006, 0x4000C, 0x40012, 0x40018, 0x4001E, 0x40024,
    0x40030, 0x40048, 0x40054, 0x400DE, 0x400E4, 0x400EA, 0x400F0,
    0x400F6, 0x40140, 0x4014C,
    0x40CC4, 0x40CF2, 0x40D24, 0x40D4E, 0x43826,
    0x56E58, 0x56E6E, 0x56E84, 0x56E90, 0x56E98, 0x56EAA,
    0x41C30, 0x42598, 0x425B4, 0x5DE44, 0x5DED4, 0x5E542,
    0x5E5D2, 0x5EA26, 0x5EAC2, 0x5F598, 0x5F772, 0x5FC56,
    0x5554E, 0x555C4, 0x5F644,
    0x449CC, 0x5317C,
    0x45BE8, 0x5FD58, 0x5FD64, 0x5FD6A,
    0x5E868,
}


def _inventory_addresses() -> set[int]:
    with INVENTORY.open(newline="", encoding="utf-8") as handle:
        return {int(row["address"], 16) for row in csv.DictReader(handle)}


def _addressed_names(
    path: Path, name_column: int, *, all_names: bool = False,
) -> dict[int, set[str]]:
    names: dict[int, set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = line.split("|")
        if len(cells) <= name_column:
            continue
        address = cells[1].strip()
        if not re.fullmatch(r"0x[0-9A-Fa-f]+", address):
            continue
        found = re.findall(r"`([^`]+)`", cells[name_column])
        if found:
            names.setdefault(int(address, 16), set()).update(
                found if all_names else found[:1]
            )
    return names


def test_every_callable_has_exactly_one_audit_class():
    inventory = _inventory_addresses()
    exceptions = MISSING | PARTIAL | OMITTED

    assert len(inventory) == 322
    assert not (MISSING & PARTIAL)
    assert not (MISSING & OMITTED)
    assert not (PARTIAL & OMITTED)
    assert exceptions <= inventory
    assert len(inventory - exceptions) == 272


def test_crosswalk_matches_the_callable_inventory_and_class_totals():
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 322
    assert {int(row["address"], 16) for row in rows} == _inventory_addresses()
    assert len({row["rom_name"] for row in rows}) == 322
    assert {
        status: sum(row["status"] == status for row in rows)
        for status in {"complete", "partial", "unnecessary", "missing_gameplay"}
    } == {
        "complete": 272,
        "partial": 0,
        "unnecessary": 50,
        "missing_gameplay": 0,
    }


def test_crosswalk_names_match_canonical_function_index():
    canonical = _addressed_names(FUNCTION_INDEX, 2)
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert all(int(row["address"], 16) in canonical for row in rows)
    assert not [
        (row["address"], row["rom_name"], sorted(canonical[int(row["address"], 16)]))
        for row in rows
        if row["rom_name"] not in canonical[int(row["address"], 16)]
    ]


def test_direct_python_ports_keep_canonical_function_names():
    direct_ports = {
        0x40A78: ("gauntpy.subsystems.shots", "shot_collision_candidate_core"),
        0x414A4: ("gauntpy.subsystems.monsters", "monster_update_anim_tile"),
        0x41B16: ("gauntpy.subsystems.monsters", "find_unused_shot"),
        0x41B52: ("gauntpy.subsystems.monsters", "monster_shooter_in_view"),
        0x41B7E: ("gauntpy.subsystems.monsters", "apply_direction_from_delta"),
        0x4526A: ("gauntpy.subsystems.display", "maze_show"),
        0x45940: ("gauntpy.subsystems.score", "draw_player_score"),
        0x459A2: ("gauntpy.subsystems.score", "draw_player_health"),
        0x46F56: ("gauntpy.subsystems.camera", "set_scroll_pos"),
        0x488CA: ("gauntpy.subsystems.session", "player_coindrop"),
        0x4A124: ("gauntpy.subsystems.score", "attract_highscores"),
        0x4A2CA: ("gauntpy.subsystems.score", "draw_player_initials_entry"),
        0x4C9A2: ("gauntpy.subsystems.score", "demo_speech_cmd"),
        0x4CB50: ("gauntpy.subsystems.score", "dialog_position_box"),
        0x4CD1C: ("gauntpy.subsystems.attract", "load_legend_page"),
        0x4D1A4: ("gauntpy.subsystems.exits", "secret_bonus_earned"),
        0x4D900: ("gauntpy.subsystems.exits", "player_activecount"),
        0x4E7C0: ("gauntpy.subsystems.maze_objects", "tport_find_id"),
        0x50BB8: ("gauntpy.subsystems.players", "scan_move_path_interactions"),
        0x51E80: ("gauntpy.subsystems.players", "door_record_endpoints"),
        0x5214C: ("gauntpy.subsystems.shots", "player_add_score_with_mult"),
        0x540E8: ("gauntpy.subsystems.dragon", "dragon_find_free_shot_slot"),
        0x545FA: ("gauntpy.subsystems.dragon", "dragon_head_pose_update"),
        0x54748: ("gauntpy.subsystems.dragon", "dragon_fire_setup"),
        0x5496E: ("gauntpy.subsystems.dragon", "dragon_setup_segments"),
        0x549EA: ("gauntpy.subsystems.shots", "dragon_player_proximity"),
        0x5E57E: ("gauntpy.subsystems.monsters", "tile_on_screen_d4"),
        0x5E584: ("gauntpy.subsystems.players", "tile_on_screen_test"),
        0x5E5D8: ("gauntpy.subsystems.dragon", "tile_near_screen_test"),
        0x5EA2E: ("gauntpy.subsystems.maze_objects", "pf_isblankfloor"),
        0x5F31E: ("gauntpy.subsystems.shots", "pf_replace"),
        0x5F7C0: ("gauntpy.subsystems.maze_objects", "maze_doors_setup"),
        0x5F7F0: ("gauntpy.subsystems.maze_objects", "pf_door_update_surrounding_xy"),
        0x5F876: ("gauntpy.subsystems.maze_objects", "pf_door_draw_xy"),
        0x5FDE0: ("gauntpy.subsystems.monsters", "supersorc_place"),
    }
    canonical = _addressed_names(FUNCTION_INDEX, 2)
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        crosswalk = {
            int(row["address"], 16): row for row in csv.DictReader(handle)
        }

    for address, (module_name, name) in direct_ports.items():
        assert canonical[address] == {name}
        assert callable(getattr(importlib.import_module(module_name), name))
        source_path = module_name.replace(".", "/") + ".py"
        assert crosswalk[address]["python_equivalent"].startswith(
            f"gauntpy/src/{source_path} ::"
        )
        assert name in crosswalk[address]["python_equivalent"]


def test_crosswalk_source_paths_exist():
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    paths = {
        match.group()
        for row in rows
        for match in re.finditer(
            r"gauntpy/src/gauntpy/[A-Za-z0-9_./-]+\.py",
            row["python_equivalent"],
        )
    }
    assert paths
    assert not [path for path in sorted(paths) if not (ROOT / path).is_file()]


def test_modeled_ram_fields_keep_canonical_data_reference_names():
    addressed_fields = {
        0x904002: "vblank_semaphore",
        0x90400E: "mazerand_adder",
        0x904010: "mazerand_num",
        0x904012: "timer_eepromwrite",
        0x90401A: "wallcycle_time",
        0x90401C: "wallcycle_type",
        0x904048: "ff_cycle_timer",
        0x904049: "ff_cycle_index",
        0x90404B: "soundqueue",
        0x90405F: "monster_spawn_probability_bonus",
        0x904063: "trick_player",
        0x904064: "trick_last",
        0x904065: "trick_tasknum",
        0x9048A0: "randwall_low_watermark",
        0x9048A2: "randwall_target",
        0x9048A4: "randwall_current",
        0x9048A6: "randwall_timer",
        0x9048F0: "player_joystick",
        0x9049EE: "speech_counter",
        0x9049F4: "sound_cpu_retry_count",
        0x904024: "collision_dist_H",
        0x904026: "collision_dist_V",
        0x904028: "shothit_dist_H",
        0x90402A: "shothit_dist_V",
        0x904A08: "exit_timer",
        0x904A4E: "global_ui_delay_timer",
        0x904A62: "monster_cull_h_origin",
        0x904A64: "monster_cull_v_origin",
        0x904A9A: "dialog_dim_H",
        0x904A9C: "dialog_dim_V",
        0x904B4A: "ff_hurt_timer",
        0x904B94: "eeprom_cache_settings",
    }
    canonical = _addressed_names(DATA_REFERENCE, 3, all_names=True)
    modeled = {field.name for field in fields(GameState)}

    for address, name in addressed_fields.items():
        assert name in canonical[address]
        assert name in modeled


def test_literal_tables_keep_canonical_data_reference_names():
    tables = {
        0x40E46: ("gauntpy.subsystems.monsters", "_MONSTER_SPAWN_PROBABILITY_TABLE"),
        0x576A8: ("gauntpy.subsystems.players", "_HEARTBEAT_MASK_TABLE"),
        0x57862: ("gauntpy.subsystems.session", "_HEALTH_PER_COIN_TABLE"),
        0x57942: ("gauntpy.subsystems.players", "_HEARTBEAT_SOUND_TABLE"),
        0x579D2: ("gauntpy.subsystems.potions", "_DEATH_POTION_SCORE_TABLE"),
        0x579E2: ("gauntpy.subsystems.potions", "_DEATH_POTION_POPUP_TYPE_TABLE"),
        0x579F2: ("gauntpy.subsystems.shots", "_SCORE_POPUP_PICTURE_TABLE"),
        0x57A2E: ("gauntpy.subsystems.monsters", "_MONSTER_CONTACT_DAMAGE_TABLE"),
        0x58A4A: ("gauntpy.subsystems.players", "_ANIM_TABLE_IDLE"),
        0x58A8A: ("gauntpy.subsystems.players", "_ANIM_TABLE_WALKING"),
        0x5884A: ("gauntpy.subsystems.players", "_ANIM_TABLE_FIGHTING"),
        0x5874A: ("gauntpy.subsystems.players", "_ANIM_TABLE_SHOOTING"),
        0x571DA: ("gauntpy.subsystems.maze_objects", "_FORCEFIELD_CYCLE_DELAY_PROFILES"),
        0x5737C: ("gauntpy.subsystems.exits", "_CHALLENGE_TIMER_RANDOM_MINUTES"),
        0x5864C: ("gauntpy.render.mobs", "_MAZEOBJ_HSIZE_TIER_TBL"),
        0x580FC: ("gauntpy.subsystems.monsters", "_JOYSTICK_NIBBLE_TO_DIRECTION"),
        0x57AAE: ("gauntpy.subsystems.monsters", "_CHARACTER_HURT_SOUND_BANKS"),
        0x57B50: ("gauntpy.subsystems.monsters", "_GENERATOR_CELL_DX"),
        0x578A2: ("gauntpy.subsystems.monsters", "_SPAWN_CANDIDATE_COLUMN_DELTA"),
        0x5AB90: ("gauntpy.subsystems.exits", "_TREASURE_FAKE_COUNTDOWN_SEQUENCES"),
        0x5AC2E: ("gauntpy.subsystems.attract", "_LOGO_MOTION_PROGRAM_FULL"),
        0x5AFAE: ("gauntpy.playfield_vram", "TPORT_PALETTE_CYCLE_BLOCKS"),
        0x5B7FC: ("gauntpy.subsystems.exits", "_EXIT_ROTATION_OFFSET_BY_COUNT"),
        0x5BAB0: ("gauntpy.subsystems.players", "_SHOT_REFLECT_HDELTA"),
        0x5BAC0: ("gauntpy.subsystems.players", "_SHOT_REFLECT_VDELTA"),
        0x5BAD0: ("gauntpy.subsystems.players", "_SHOT_REFLECT_SOUND_TBL"),
        0x5B62E: ("gauntpy.subsystems.thief", "_THIEF_STEALABLE_POWER_MASKS"),
        0x5B70A: ("gauntpy.subsystems.thief", "_THIEF_DIRECTION_STEP_SIZE"),
        0x5B72C: ("gauntpy.subsystems.players", "_CHARACTER_REPULSE_TIMER_INIT"),
        0x5D438: ("gauntpy.subsystems.dragon", "_DRAGON_HEAD_HDELTA"),
        0x5DA98: ("gauntpy.subsystems.potions", "_POTION_EFFECT_MATRIX"),
        0x5FDAC: ("gauntpy.subsystems.monsters", "_SUPERSORC_DIRECTION_BIAS"),
    }
    canonical = _addressed_names(DATA_REFERENCE, 3, all_names=True)

    for address, (module_name, constant_name) in tables.items():
        assert constant_name.removeprefix("_").lower() in {
            name.lower() for name in canonical[address]
        }
        assert hasattr(importlib.import_module(module_name), constant_name)
