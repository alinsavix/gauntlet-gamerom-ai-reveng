"""Compatibility alias for :mod:`gauntpy.game.subsystems.exits`."""

import sys

from ..game.subsystems import exits as _implementation

sys.modules[__name__] = _implementation
