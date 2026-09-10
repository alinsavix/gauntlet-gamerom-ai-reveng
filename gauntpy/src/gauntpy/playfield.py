"""Compatibility alias for :mod:`gauntpy.game.playfield`."""

import sys

from .game import playfield as _implementation

sys.modules[__name__] = _implementation
