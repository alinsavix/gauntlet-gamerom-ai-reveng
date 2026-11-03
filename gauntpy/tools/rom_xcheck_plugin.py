"""pytest plugin: compare every test's ``player_try_move`` call with ROM 0x41BF0.

From gauntpy, with the ROMs in place:

    set PYTHONPATH=src;tools
    python -m pytest -q -p rom_xcheck_plugin tests

The report goes to ``rom_xcheck.txt`` in the current directory. Mismatches are
leads, not verdicts: most come from fixtures the snapshot cannot represent (see
``rom_exec.py``). The architecture test that checks ``player_try_move``'s module
identity fails under this plugin, because the plugin wraps that function.
"""

from __future__ import annotations

import atexit
import copy
import os

import rom_exec
from gauntpy.game.subsystems import player_movement as pm

_results: list[tuple[str, object, object]] = []
_original = pm.player_try_move


def _wrapped(state, player_index, delta, movement_flags, **kwargs):
    if kwargs:
        return _original(state, player_index, delta, movement_flags, **kwargs)
    try:
        rom = rom_exec.rom_try_move(
            copy.deepcopy(state), player_index, delta, state.movement_type or 2,
        )
    except Exception as error:  # noqa: BLE001 -- a fixture the snapshot cannot load
        rom = ("error", repr(error))
    result = _original(state, player_index, delta, movement_flags)
    slot = state.players[player_index].mob_slot
    python = (result, slot, state.mobs.hpos[slot] & 0xFFF0, state.mobs.vpos[slot] & 0xFFFF)
    test = os.environ.get("PYTEST_CURRENT_TEST", "?").split(" ")[0]
    _results.append((test, rom, python))
    return result


def pytest_configure(config):
    pm.player_try_move = _wrapped


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        if getattr(item.module, "player_try_move", None) is _original:
            item.module.player_try_move = _wrapped


@atexit.register
def _report():
    with open("rom_xcheck.txt", "w", encoding="utf-8") as report:
        same = sum(1 for _, rom, python in _results if rom == python)
        report.write(f"{same}/{len(_results)} calls identical\n")
        for test, rom, python in _results:
            if rom != python:
                report.write(f"{test}\n   ROM {rom}\n   PY  {python}\n")
