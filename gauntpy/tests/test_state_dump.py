"""Complete host-only state dump contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace

from gauntpy.state import GameState
from gauntpy.render.state_dump import dump_game_state, state_dump_payload


def test_payload_contains_complete_modeled_memory_without_mutating_state():
    state = GameState()
    state.frame_counter = 123
    state.rng.seed = 0x4567
    state.alpha_ram[7] = 0xABCD
    state.playfield_ram[11] = 0x1357
    state.mob_color_ram[13] = 0x2468
    state.mobs.picture[42] = 0x1E0D
    state.mobs.hpos[42] = 0x222C
    state.players[0].health = 999
    state.maze = SimpleNamespace(data={(3, 4): 2}, mazenum=16)
    before = (
        state.frame_counter,
        state.rng.seed,
        tuple(state.mobs.picture),
        tuple(state.alpha_ram),
    )

    payload = state_dump_payload(state)
    dumped = payload["state"]

    assert payload["schema"] == 1
    assert payload["frame"] == 123
    assert dumped["rng"]["seed"] == 0x4567
    assert dumped["alpha_ram"][7] == 0xABCD
    assert dumped["playfield_ram"][11] == 0x1357
    assert dumped["mob_color_ram"][13] == 0x2468
    assert dumped["mobs"]["picture"][42] == 0x1E0D
    assert dumped["mobs"]["hpos"][42] == 0x222C
    assert dumped["players"][0]["health"] == 999
    assert dumped["maze"]["data"] == [{"key": [3, 4], "value": 2}]
    assert before == (
        state.frame_counter,
        state.rng.seed,
        tuple(state.mobs.picture),
        tuple(state.alpha_ram),
    )


def test_dump_writes_parseable_unique_json_files(tmp_path):
    state = GameState(frame_counter=77)

    first = dump_game_state(state, tmp_path)
    second = dump_game_state(state, tmp_path)

    assert first != second
    assert json.loads(first.read_text(encoding="utf-8"))["frame"] == 77
    assert json.loads(second.read_text(encoding="utf-8"))["state"]["frame_counter"] == 77
