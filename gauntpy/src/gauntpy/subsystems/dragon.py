"""Compatibility alias for :mod:`gauntpy.game.subsystems.dragon`."""

import sys

from ..game.subsystems import dragon as _implementation

sys.modules[__name__] = _implementation
