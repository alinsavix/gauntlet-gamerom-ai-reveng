"""Compatibility alias for :mod:`gauntpy.game.subsystems.thief`."""

import sys

from ..game.subsystems import thief as _implementation

sys.modules[__name__] = _implementation
