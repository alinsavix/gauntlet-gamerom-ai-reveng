"""Compatibility alias for :mod:`gauntpy.game.playfield_vram`."""

import sys

from .game import playfield_vram as _implementation

sys.modules[__name__] = _implementation
