"""Compatibility alias for :mod:`gauntpy.game.subsystems.player_names`."""

import sys

from ..game.subsystems import player_names as _implementation

sys.modules[__name__] = _implementation
