"""Compatibility alias for :mod:`gauntpy.game.subsystems.shots`."""

import sys

from ..game.subsystems import shots as _implementation

sys.modules[__name__] = _implementation
