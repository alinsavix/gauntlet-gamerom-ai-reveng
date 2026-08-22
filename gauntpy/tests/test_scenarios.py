"""Deterministic scenario-runner contracts."""

from __future__ import annotations

from gauntpy.scenarios import SCENARIOS, main, run_scenario


def test_scenario_catalog_covers_the_recurring_fidelity_cases():
    assert set(SCENARIOS) == {
        "level1",
        "level7-seam",
        "forcefields",
        "dragon-range",
        "demo-playback",
        "close-combat",
    }


def test_forcefield_trace_is_deterministic_and_repeats():
    first = run_scenario("forcefields", frames=600, every=20)
    second = run_scenario("forcefields", frames=600, every=20)

    assert first == second
    colors = [row["forcefield"]["color"] for row in first]
    assert 0 in colors
    assert any(colors)
    assert first[0]["forcefield"]["segments"] == []
    assert first[1]["forcefield"]["segments"]


def test_close_combat_trace_resolves_the_point_blank_target():
    trace = run_scenario("close-combat", frames=3)

    assert trace[0]["creatures"].get(int(22), 0) == 1
    assert trace[-1]["creatures"].get(int(22), 0) == 0


def test_list_command_is_json(capsys):
    main(["list"])
    output = capsys.readouterr().out
    assert '"level7-seam"' in output
    assert '"demo-playback"' in output
