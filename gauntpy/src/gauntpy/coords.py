"""Compatibility alias for :mod:`gauntpy.game.coords`."""

import sys

from .game import coords as _implementation

sys.modules[__name__] = _implementation
