"""Compatibility alias for :mod:`gauntpy.game.subsystems.session`."""

import sys

from ..game.subsystems import session as _implementation

sys.modules[__name__] = _implementation
