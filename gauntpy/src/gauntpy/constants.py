"""Compatibility alias for :mod:`gauntpy.game.constants`."""

import sys

from .game import constants as _implementation

sys.modules[__name__] = _implementation
