"""WP-21 sub-deliverable 2 -- golden frame trace regression test.

Runs the fixed scripted-input sequence from ``tests/golden.py`` through
``tick()`` for a fixed, explicitly-seeded ``GameState`` and diffs the result
against ``tests/goldens/scripted_run_v1.json``, frame by frame. A change
anywhere in the simulation that touches a digested field -- today that is
realistically only ``input_debounce`` (WP-4, the only non-stub subsystem) and
the frame/RNG bookkeeping in ``mainloop.py`` -- fails here immediately, with
the exact frame and field named.

As WP-5 and later land, they start writing fields ``digest_frame`` already
reads (player health, mob chain, ...), and this test starts protecting them
for free -- no changes needed in this file.
"""

from __future__ import annotations

from golden import (
    GOLDEN_SEED,
    SCRIPTED_RUN_FRAMES,
    build_scripted_state,
    diff_trace,
    load_golden,
    run_scripted_trace,
)

GOLDEN_NAME = "scripted_run_v1.json"


def test_scripted_run_matches_the_golden_trace():
    state = build_scripted_state()
    trace = run_scripted_trace(state)
    golden = load_golden(GOLDEN_NAME)

    problems = diff_trace(trace, golden)
    assert not problems, (
        f"scripted run diverged from {GOLDEN_NAME}:\n  " + "\n  ".join(problems)
    )


def test_scripted_run_is_internally_deterministic():
    """Same seed, same script, same result -- checked without touching the
    golden file at all, so this still catches nondeterminism (e.g. an
    accidental `set` iteration or a stray `random.random()`) even if the
    golden fixture itself is stale or missing."""
    trace_a = run_scripted_trace(build_scripted_state())
    trace_b = run_scripted_trace(build_scripted_state())
    assert trace_a == trace_b


def test_golden_run_actually_exercises_input_debounce():
    """A sanity check on the script itself: if this stops being true, the
    golden trace has quietly stopped testing anything interesting."""
    state = build_scripted_state()
    trace = run_scripted_trace(state)

    magic_shift_values = {f["debounce_shift_magic"][0] for f in trace}
    assert len(magic_shift_values) > 1, "player 0's magic shift register never changed"

    # main_start_game's press-edge pattern (subsystems/input.py PRESS_PATTERN)
    # must actually occur somewhere in the scripted run.
    assert any((v & 0x1F) == 0x1C for v in magic_shift_values)


def test_digest_frame_is_integers_only():
    """PLAN.md ground rule 5: integers only, no floats, anywhere touching
    simulation state. Golden fixtures are exactly the place a stray float
    would sneak in unnoticed (JSON doesn't distinguish 1 from 1.0 by type
    the way Python does), so this checks the live digest, not the file."""
    state = build_scripted_state()
    frame = run_scripted_trace(state, num_frames=1)[0]

    def check(value: object, path: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                check(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                check(v, f"{path}[{i}]")
        else:
            assert isinstance(value, int), f"{path} is {type(value).__name__}, not int: {value!r}"

    check(frame, "frame")


def test_golden_seed_is_fixed_not_zero():
    """PLAN.md §21: the hardware seed free-runs and is never reproducible in
    the original, so a golden trace is only meaningful if *we* pin the seed.
    0 would also "work" but is indistinguishable from "forgot to seed it";
    require a real (nonzero) fixed value."""
    assert GOLDEN_SEED != 0
    state = build_scripted_state()
    assert state.rng.seed == GOLDEN_SEED


def test_scripted_run_frame_count_matches_the_golden():
    golden = load_golden(GOLDEN_NAME)
    assert len(golden) == SCRIPTED_RUN_FRAMES
