"""Compatibility alias for :mod:`gauntpy.game.subsystems.camera`."""

import sys

from ..game.subsystems import camera as _implementation

sys.modules[__name__] = _implementation
