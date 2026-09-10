"""Compatibility alias for :mod:`gauntpy.game.subsystems.input`."""

import sys

from ..game.subsystems import input as _implementation

sys.modules[__name__] = _implementation
