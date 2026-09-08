"""Compatibility exports for host troubleshooting controls."""

from ..host.debug_controls import (
    debug_add_key,
    debug_add_potion,
    debug_enable_secret_room,
    debug_force_secret_room,
    debug_skip_level,
)

__all__ = [
    "debug_add_key", "debug_add_potion", "debug_enable_secret_room",
    "debug_force_secret_room", "debug_skip_level",
]
