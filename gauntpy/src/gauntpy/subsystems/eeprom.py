"""Compatibility alias for :mod:`gauntpy.game.subsystems.eeprom`."""

import sys

from ..game.subsystems import eeprom as _implementation

sys.modules[__name__] = _implementation
