"""Compatibility alias for :mod:`gauntpy.game.mainloop`."""

import sys

from .game import mainloop as _implementation

sys.modules[__name__] = _implementation
