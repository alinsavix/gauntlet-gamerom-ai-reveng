"""The game's random number generator.

A 16-bit LCG, ported exactly from ``random_core`` (0x5FC2C).

Reference: ``doc/07_function_index.md`` §14/§14.1 (0x5FC22/0x5FC26/0x5FC2C/
0x5FC46/0x5FC4E) and ``doc/05_data_reference.md`` 0x904BFC.

The whole routine, verified instruction by instruction against ``row76.bin``::

    0x5FC26  moveq  #0,d0          ; d0.l = 0
    0x5FC28  move.w 6(a7),d0       ;   ... | bound          (zero-extended)
    0x5FC2C  move.w (a0),d1        ; d1.w = seed
    0x5FC2E  muls.w #$3619,d1      ; d1.l = (int16)seed * 0x3619
    0x5FC32  addi.w #$5D35,d1      ; d1.w = (seed*0x3619 + 0x5D35) & 0xFFFF
    0x5FC36  move.w d1,(a0)        ; store the advanced seed
    0x5FC38  muls.w d0,d1          ; d1.l = (int16)seed' * (int16)bound
    0x5FC3A  swap   d0             ; d0.l = bound << 16
    0x5FC3C  asr.l  #1,d0          ; d0.l = (int16)bound * 0x8000
    0x5FC3E  add.l  d1,d0          ; d0.l = (int16)bound * (seed' + 0x8000)
    0x5FC40  swap   d0             ; take the high word ...
    0x5FC42  ext.l  d0             ;   ... sign-extended: an arithmetic >> 16
    0x5FC44  rts

so the result is::

    seed   = (seed * 0x3619 + 0x5D35) & 0xFFFF
    result = (int16(bound) * ((seed + 0x8000) & 0xFFFF)) >> 16      (floored)

``(seed + 0x8000) & 0xFFFF`` is not an approximation: the ``swap``/``asr.l``/
``add.l`` trio computes ``int16(seed) + 0x8000`` exactly, and adding 0x8000
to a signed 16-bit value spans the same 0..0xFFFF range as biasing the
unsigned one.

Width and sign, the part that is easy to get wrong: the multiply is
``MULS.W``, so a bound with bit 15 set is a *negative* 16-bit number and the
result comes back zero or negative -- the ``[0, bound)`` guarantee holds only
for bounds in ``[0, 0x7FFF]``, which is what every observed caller passes
(``doc/07_function_index.md`` §14.1). ``getrandom`` reproduces that signed
behaviour rather than rejecting it: a reimplementation that raises where the
ROM returns is its own kind of divergence, and it would hide -- rather than
reproduce -- a caller that ever passed such a bound. The range guarantee is
asserted in ``tests/test_rng.py``, where it belongs.

Note: the hardware seed at 0x904BFC is *never explicitly initialized* and
free-runs across attract screens and sessions, so nothing in the original is
reproducible by re-entering a mode -- including the attract demo. We take a
seed explicitly so that our runs *are* reproducible, which is what makes
regression testing possible at all.
"""

from __future__ import annotations

MULTIPLIER = 0x3619
INCREMENT = 0x5D35

#: The ``+0x8000`` bias synthesized by ``swap``/``asr.l #1``/``add.l``
#: at 0x5FC3A-0x5FC3E.
SEED_BIAS = 0x8000

#: Bounds at or below this keep the documented ``[0, bound)`` guarantee;
#: above it ``MULS.W`` reads the bound as negative (§14.1).
MAX_SAFE_BOUND = 0x7FFF


def _signed16(value: int) -> int:
    """Reinterpret the low 16 bits of ``value`` as a signed word."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


class GameRandom:
    """Port of the game's LCG -- bit-exact for every 16-bit bound."""

    __slots__ = ("seed",)

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed & 0xFFFF

    def _advance(self) -> int:
        self.seed = (self.seed * MULTIPLIER + INCREMENT) & 0xFFFF
        return self.seed

    def getrandom(self, bound: int) -> int:
        """``getrandom(bound)`` (0x5FC4E) -- uniform in [0, bound).

        The seed advances on *every* call, ``bound == 0`` included: the ROM
        stores the new seed before it so much as looks at the bound, so a draw
        that cannot produce a range still moves the shared stream on. Keeping
        that true is what lets a gauntpy run stay in step with the original.

        ``bound`` is a hardware word -- only its low 16 bits matter, and bit 15
        makes it negative (see the module docstring), so bounds outside
        ``[0, 0x7FFF]`` return the ROM's signed result rather than raising.
        """
        seed = self._advance()
        product = _signed16(bound) * ((seed + SEED_BIAS) & 0xFFFF)
        # swap + ext.l == an arithmetic >> 16, which Python's floor-shift
        # already matches for negative products.
        return product >> 16

    # Alias matching the ROM's register veneer at 0x5FC46.
    random_word = getrandom

    def random_seeded(self, bound: int, seed: int) -> tuple[int, int]:
        """``random_seeded`` (0x5FC22): draw from a caller-supplied seed.

        Dormant in the shipped ROM (no discovered call site, §14.1) but part
        of the same shared body, and the only way to draw without disturbing
        the global stream. Returns ``(result, new_seed)``; this instance's own
        seed is untouched.
        """
        scratch = GameRandom(seed)
        return scratch.getrandom(bound), scratch.seed
