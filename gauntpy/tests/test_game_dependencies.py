"""Game imports name their owners; ROM cross-family calls remain unrestricted."""

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest


GAME = Path(__file__).resolve().parents[1] / "src" / "gauntpy" / "game"
MODULES = {
    "gauntpy.game." + ".".join(path.relative_to(GAME).with_suffix("").parts): path
    for path in GAME.rglob("*.py") if path.name != "__init__.py"
}
TREES = {
    name: ast.parse(path.read_text(encoding="utf-8"))
    for name, path in MODULES.items()
}
FAMILY_FACADES = {
    "player_": "players",
    "monster_": "monsters",
    "shot_": "shots",
    "level_": "exits",
    "secret_rooms": "exits",
    "treasure_rooms": "exits",
    "mob_probes": "players",
}


def _provider(consumer, node):
    return resolve_name(
        "." * node.level + (node.module or ""),
        consumer.rpartition(".")[0],
    )


@pytest.mark.parametrize("consumer", sorted(MODULES))
def test_game_imports_use_defining_modules(consumer):
    for node in ast.walk(TREES[consumer]):
        if not isinstance(node, ast.ImportFrom):
            continue
        provider = _provider(consumer, node)
        if provider not in TREES:
            continue
        assert provider != consumer, f"{consumer}:{node.lineno} imports itself"
        reexports = {
            alias.asname or alias.name: imported
            for imported in TREES[provider].body
            if isinstance(imported, ast.ImportFrom)
            and _provider(provider, imported).startswith("gauntpy.game.")
            for alias in imported.names
        }
        for alias in node.names:
            assert alias.name not in reexports, (
                f"{consumer}:{node.lineno} imports {provider}.{alias.name} "
                "through a reexport instead of its defining module"
            )


@pytest.mark.parametrize("consumer", sorted(MODULES))
def test_extracted_families_do_not_import_their_compatibility_facade(consumer):
    name = consumer.rsplit(".", 1)[-1]
    facade = next(
        (facade for prefix, facade in FAMILY_FACADES.items()
         if name.startswith(prefix)),
        None,
    )
    if facade is None:
        return
    for node in ast.walk(TREES[consumer]):
        if isinstance(node, ast.Import):
            providers = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            provider = _provider(consumer, node)
            providers = [provider, *(f"{provider}.{alias.name}" for alias in node.names)]
        else:
            continue
        assert f"gauntpy.game.subsystems.{facade}" not in providers, (
            f"{consumer}:{node.lineno} depends on its compatibility facade"
        )
