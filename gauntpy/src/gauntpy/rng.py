"""Compatibility alias for :mod:`gauntpy.game.rng`."""

import sys

from .game import rng as _implementation

sys.modules[__name__] = _implementation
