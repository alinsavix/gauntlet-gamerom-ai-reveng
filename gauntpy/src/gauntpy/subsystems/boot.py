"""Compatibility alias for :mod:`gauntpy.game.subsystems.boot`."""

import sys

from ..game.subsystems import boot as _implementation

sys.modules[__name__] = _implementation
