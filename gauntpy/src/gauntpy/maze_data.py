"""Compatibility alias for :mod:`gauntpy.game.maze_data`."""

import sys

from .game import maze_data as _implementation

sys.modules[__name__] = _implementation
