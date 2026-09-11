"""The ROM adapter acquires data; game setup owns every state/RNG write."""

import ast
import inspect

import pytest

from gauntpy.game import maze
from gauntpy import maze_rom
from gauntpy.game.constants import GameMode
from gauntpy.render.state_dump import state_dump_payload
from gauntpy.game.state import GameState


def test_game_maze_module_does_not_import_the_decoder_directly():
    tree = ast.parse(inspect.getsource(maze))
    assert not [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] == "gex"
    ]


@pytest.mark.parametrize("reset", [False, True])
def test_failed_rom_acquisition_leaves_all_state_unchanged(monkeypatch, reset):
    state = GameState(
        levelnum_current=17, mazenum_current=16, level_players_active=2,
        thief_enter_time=123, monster_slowmo_timer=45,
    )
    state.mobs.picture[100] = 0x8000
    before = state_dump_payload(state)["state"]

    def unavailable(_number):
        raise maze.MazeError("deliberately unavailable test ROM")

    monkeypatch.setattr(maze, "decode_maze", unavailable)
    if reset:
        assert maze.reset_and_load_level(state, 18, maze_number=17) is False
    else:
        with pytest.raises(maze.MazeError, match="deliberately unavailable"):
            maze.load_level(state, 18, maze_number=17)
    assert state_dump_payload(state)["state"] == before


@pytest.mark.parametrize("number,missing_delimiter", [(0, False), (115, False), (116, True)])
def test_adapter_retains_the_final_maze_delimiter_exception(
    monkeypatch, number, missing_delimiter,
):
    record = [1, 2, 3]
    decoded = maze_rom.Maze()
    calls = []
    monkeypatch.setattr(maze_rom, "slapstic_read_maze", lambda index: record)

    def decompress(compressed, *, allow_missing_delimiter):
        calls.append((compressed, allow_missing_delimiter))
        return decoded

    monkeypatch.setattr(maze_rom, "maze_decompress", decompress)
    assert maze_rom.decode_maze(number) is decoded
    assert calls == [(record, missing_delimiter)]


def test_adapter_exposes_acquisition_errors_without_game_fallbacks(monkeypatch):
    def unavailable(_number):
        raise maze_rom.GexError("missing fixture")

    monkeypatch.setattr(maze_rom, "slapstic_read_maze", unavailable)
    with pytest.raises(maze.MazeError, match="could not decode maze 7") as error:
        maze_rom.decode_maze(7)
    assert isinstance(error.value.__cause__, maze_rom.GexError)


@pytest.mark.parametrize(
    "mode,requested_maze", [(GameMode.SCORES, 103), (GameMode.DEMO, 102)],
)
def test_rom_free_attract_requests_scenery_without_pretending_it_loaded(
    monkeypatch, mode, requested_maze,
):
    from gauntpy.game.subsystems.attract import start_attract_screen

    requests = []

    def unavailable(number):
        requests.append(number)
        raise maze.MazeError("deliberately unavailable test ROM")

    monkeypatch.setattr(maze, "decode_maze", unavailable)
    state = GameState(levelnum_current=42, mazenum_current=77)
    start_attract_screen(state, mode)
    assert requests == [requested_maze]
    assert state.levelnum_current == 1
    assert state.mazenum_current == 0
    assert state.maze is None
