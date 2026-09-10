"""Compatibility alias for :mod:`gauntpy.game.subsystems.player_animation`."""

import sys

from ..game.subsystems import player_animation as _implementation

sys.modules[__name__] = _implementation
