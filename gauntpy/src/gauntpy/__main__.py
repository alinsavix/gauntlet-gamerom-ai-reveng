"""Skeleton demo: run frames and show the loop's structure working.

    python -m gauntpy

Prints what a frame does, shows the dialog gate freezing exactly the sixteen
gameplay calls, shows the frame-overflow decay, and reports how much of the
game is still stubbed.
"""

from __future__ import annotations

import inspect

from . import mainloop
from .constants import GameMode
from .mainloop import check_frame_overflow, game_frame, tick
from .state import GameState
from .subsystems import is_stub


def _loop_calls() -> list[str]:
    """The names ``game_frame`` calls, in source order."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(game_frame)))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    calls.sort(key=lambda n: (n.lineno, n.col_offset))
    return [n.func.id for n in calls]


def main() -> None:
    state = GameState(game_mode=GameMode.NORMAL)
    names = _loop_calls()

    print(f"g2mainloop: {len(names)} calls per frame\n")

    tick(state)
    print(f"frame {state.frame_counter}: ran the full sequence")
    print(f"  first three : {', '.join(names[:3])}")
    print(f"  last three  : {', '.join(names[-3:])}")

    # A message box freezes the world band and nothing else.
    state.dialog_timer = 30
    tick(state)
    print(f"\nframe {state.frame_counter}: dialog_timer={state.dialog_timer}")
    print("  the 16 gameplay calls are skipped as one block; coins, sound,")
    print("  the message-box countdown, and the attract machine keep running")
    state.dialog_timer = 0

    # A long frame throttles the generators, then the signal decays.
    state.vblank_flag = 1        # the display finished another field mid-frame
    check_frame_overflow(state)
    print(f"\nframe ran long -> frame_overflow = {state.frame_overflow} "
          "(generators stop spawning)")
    for _ in range(4):
        tick(state)
        print(f"  good frame     -> frame_overflow = {state.frame_overflow}")

    stubbed = [n for n in names if is_stub(getattr(mainloop, n))]
    done = len(names) - len(stubbed)
    print(f"\n{done}/{len(names)} main-loop calls implemented, "
          f"{len(stubbed)} still stubbed.")
    print("See PLAN.md for the work packages that fill these in.")


if __name__ == "__main__":
    main()
