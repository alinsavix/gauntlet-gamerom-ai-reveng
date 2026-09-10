"""Compatibility alias for :mod:`gauntpy.game.alpha_memory`."""

import sys

from .game import alpha_memory as _implementation

sys.modules[__name__] = _implementation
