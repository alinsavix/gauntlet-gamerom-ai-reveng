"""Compatibility alias for :mod:`gauntpy.game.mob`."""

import sys

from .game import mob as _implementation

sys.modules[__name__] = _implementation
