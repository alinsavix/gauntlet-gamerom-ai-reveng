"""Compatibility alias for :mod:`gauntpy.game.subsystems.potions`."""

import sys

from ..game.subsystems import potions as _implementation

sys.modules[__name__] = _implementation
