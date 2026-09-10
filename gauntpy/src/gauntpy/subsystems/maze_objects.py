"""Compatibility alias for :mod:`gauntpy.game.subsystems.maze_objects`."""

import sys

from ..game.subsystems import maze_objects as _implementation

sys.modules[__name__] = _implementation
