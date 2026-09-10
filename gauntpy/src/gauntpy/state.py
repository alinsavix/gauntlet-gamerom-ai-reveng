"""Compatibility alias for :mod:`gauntpy.game.state`."""

import sys

from .game import state as _implementation

sys.modules[__name__] = _implementation
