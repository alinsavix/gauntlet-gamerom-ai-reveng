"""Compatibility alias for :mod:`gauntpy.game.subsystems.monsters`."""

import sys

from ..game.subsystems import monsters as _implementation

sys.modules[__name__] = _implementation
