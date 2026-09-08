"""Public graphical CLI and direct-play API.

Host startup and execution live in :mod:`gauntpy.host`; these imports preserve
``gauntpy-play``, ``python -m gauntpy.play``, and existing headless callers.
"""

from .host.application import MAX_MAZE_NUM, main, run
from .host.startup import build_state

__all__ = ["MAX_MAZE_NUM", "build_state", "main", "run"]


if __name__ == "__main__":
    main()
