"""Compatibility alias for :mod:`gauntpy.game.subsystems.score`."""

import sys

from ..game.subsystems import score as _implementation

sys.modules[__name__] = _implementation
