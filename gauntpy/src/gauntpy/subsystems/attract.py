"""Compatibility alias for :mod:`gauntpy.game.subsystems.attract`."""

import sys

from ..game.subsystems import attract as _implementation

sys.modules[__name__] = _implementation
