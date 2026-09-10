"""Canonical game ownership and identity-compatible historical import paths."""

import ast
import importlib
import inspect
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "src" / "gauntpy"
CORE_MODULES = (
    "alpha_memory", "constants", "coords", "eeprom_device", "mainloop", "maze",
    "maze_data", "mob", "playfield", "playfield_vram", "rng", "romtext", "state",
)
FAMILY_OWNERS = {
    "players": (
        "player_lifecycle", "player_items", "player_transport",
        "player_movement", "mob_probes",
    ),
    "exits": ("secret_rooms", "treasure_rooms", "level_transitions"),
    "monsters": ("monster_movement", "monster_shooting", "monster_spawning"),
    "shots": ("shot_damage", "shot_collision"),
}


@pytest.mark.parametrize("name", CORE_MODULES)
def test_legacy_core_modules_are_the_canonical_modules(name):
    legacy = importlib.import_module(f"gauntpy.{name}")
    canonical = importlib.import_module(f"gauntpy.game.{name}")
    assert legacy is canonical
    assert Path(canonical.__file__).parent == SOURCE / "game"


@pytest.mark.parametrize(
    "name",
    sorted(path.stem for path in (SOURCE / "subsystems").glob("*.py")
           if path.stem != "__init__"),
)
def test_legacy_subsystem_modules_are_the_canonical_modules(name):
    legacy = importlib.import_module(f"gauntpy.subsystems.{name}")
    canonical = importlib.import_module(f"gauntpy.game.subsystems.{name}")
    assert legacy is canonical


def test_legacy_monkeypatches_reach_the_same_game_module(monkeypatch):
    from gauntpy import mainloop
    from gauntpy.game import mainloop as canonical
    from gauntpy.game.state import GameState

    calls = []
    monkeypatch.setattr(mainloop, "game_frame", lambda state, **kwargs: calls.append(state))
    state = GameState()
    canonical.tick(state)
    assert calls == [state]


@pytest.mark.parametrize(
    "facade_name,owner_name",
    [(facade, owner) for facade, owners in FAMILY_OWNERS.items() for owner in owners],
)
def test_family_exports_preserve_function_identity(facade_name, owner_name):
    facade = importlib.import_module(f"gauntpy.game.subsystems.{facade_name}")
    owner = importlib.import_module(f"gauntpy.game.subsystems.{owner_name}")
    functions = {
        name: value for name, value in vars(owner).items()
        if inspect.isfunction(value) and value.__module__ == owner.__name__
        and name != "tport_find_id"  # Previously owned by thief and maze_objects.
    }
    assert functions
    for name, function in functions.items():
        assert getattr(facade, name) is function


def test_game_imports_neither_host_nor_rasterizer():
    forbidden = {"host", "render", "pygame", "PIL", "gex", "time", "random"}
    violations = []
    for path in (SOURCE / "game").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(forbidden.intersection(name.split(".")) for name in names):
                violations.append((str(path.relative_to(SOURCE)), node.lineno, names))
    assert violations == []


def test_legacy_game_paths_have_no_duplicate_implementations():
    paths = [SOURCE / f"{name}.py" for name in CORE_MODULES]
    paths.extend((SOURCE / "subsystems").glob("*.py"))
    for path in paths:
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.ClassDef))
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        ), path
