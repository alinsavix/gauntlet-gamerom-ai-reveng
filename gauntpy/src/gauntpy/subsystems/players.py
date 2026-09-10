"""Compatibility alias for :mod:`gauntpy.game.subsystems.players`."""

import sys

from ..game.subsystems import players as _implementation

sys.modules[__name__] = _implementation
