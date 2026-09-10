"""Compatibility alias for :mod:`gauntpy.game.eeprom_device`."""

import sys

from .game import eeprom_device as _implementation

sys.modules[__name__] = _implementation
