"""Potions and magic -- WP-12.

The ``potion_effect_matrix`` (0x5DA98) is 28 records x 16 bytes for object
types 0x12-0x2D, indexed ``(object_type << 4) + character + trigger_flags``,
where bit 2 marks a shot-triggered potion and bit 3 the enhanced-magic variant.

**A zero entry destroys the target outright.** There is no "no effect" encoding
for monsters at all -- read the 0x5DA98 entry in the data reference in full
before implementing.

Reference: ``doc/05_data_reference.md`` (0x5DA98); ``doc/04_game_subsystems.md``
§4.6.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_handle_potions(state: GameState) -> None:
    """0x46FEA -- potion use and blast resolution.

    Gated on the debounced Magic press, the same ``== 0x1C`` pattern
    ``main_start_game`` matches (tested at 0x47020).
    """
