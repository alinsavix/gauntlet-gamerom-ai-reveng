"""Compatibility alias for :mod:`gauntpy.game.maze`."""

import sys

from .game import maze as _implementation

sys.modules[__name__] = _implementation
