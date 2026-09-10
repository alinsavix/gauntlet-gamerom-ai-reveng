"""Compatibility alias for :mod:`gauntpy.game.subsystems.display`."""

import sys

from ..game.subsystems import display as _implementation

sys.modules[__name__] = _implementation
