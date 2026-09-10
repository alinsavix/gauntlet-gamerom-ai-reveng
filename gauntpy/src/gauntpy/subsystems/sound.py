"""Compatibility alias for :mod:`gauntpy.game.subsystems.sound`."""

import sys

from ..game.subsystems import sound as _implementation

sys.modules[__name__] = _implementation
