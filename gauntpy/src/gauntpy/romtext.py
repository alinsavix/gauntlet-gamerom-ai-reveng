"""Compatibility alias for :mod:`gauntpy.game.romtext`."""

import sys

from .game import romtext as _implementation

sys.modules[__name__] = _implementation
