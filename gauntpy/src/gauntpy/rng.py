"""The game's random number generator.

A 16-bit LCG, ported exactly from ``random_core`` (0x5FC2C).

Reference: ``doc/07_function_index.md`` (0x5FC2C/0x5FC46/0x5FC4E) and
``doc/05_data_reference.md`` 0x904BFC.

    seed = (seed * 0x3619 + 0x5D35) & 0xFFFF
    result = (bound * ((seed + 0x8000) & 0xFFFF)) >> 16

The ``+0x8000`` bias comes from the ``swap`` / ``asr.l #1`` / ``add.l``
sequence at 0x5FC3A-0x5FC40. Because the original multiply is ``MULS.W``, a
bound with bit 15 set is treated as signed and loses the ``[0, bound)``
guarantee; every observed caller passes a bound <= 0x7FFF.

Note: the hardware seed at 0x904BFC is *never explicitly initialized* and
free-runs across attract screens and sessions, so nothing in the original is
reproducible by re-entering a mode -- including the attract demo. We take a
seed explicitly so that our runs *are* reproducible, which is what makes
regression testing possible at all.
"""

from __future__ import annotations

MULTIPLIER = 0x3619
INCREMENT = 0x5D35


class GameRandom:
    """Port of the game's LCG. Bit-exact for bounds in [0, 0x7FFF]."""

    __slots__ = ("seed",)

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed & 0xFFFF

    def _advance(self) -> int:
        self.seed = (self.seed * MULTIPLIER + INCREMENT) & 0xFFFF
        return self.seed

    def getrandom(self, bound: int) -> int:
        """``getrandom(bound)`` -- uniform in [0, bound). Bound 0 yields 0."""
        seed = self._advance()
        if bound <= 0:
            return 0
        if bound > 0x7FFF:
            raise ValueError(
                f"bound {bound:#x} exceeds 0x7FFF; the original's signed "
                "MULS.W has no range guarantee there"
            )
        return (bound * ((seed + 0x8000) & 0xFFFF)) >> 16

    # Alias matching the ROM's register veneer at 0x5FC46.
    random_word = getrandom
