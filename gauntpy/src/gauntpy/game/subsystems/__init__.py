"""Subsystem implementations, one module per work package.

Every main-loop call lives here as a function with the ROM's name, its
address, and its references. That means the loop runs from day one and
``mainloop.py`` imports real names rather than looking anything up.

Modules were originally forbidden from importing each other: everything they
shared travelled through ``GameState``, exactly as the original's subsystems
shared working RAM, which is what made the work packages in ``PLAN.md``
independently assignable. That rule has since been lifted (ISSUES I-09 /
I-21 / I-22) -- direct cross-imports are wired where the ROM's own call graph
has one -- but ``GameState`` is still the default way for two packages to
meet, and a new import between subsystems should be a deliberate choice, not
a convenience.

This package deliberately exports nothing. The ``@stub`` marker that used to
live here (a decorator setting ``fn.is_stub``, plus an ``is_stub`` predicate
``python -m gauntpy`` reported on) was removed once every main-loop call had a
body: with nothing left to mark, it only ever proved that nothing was marked.
``tests/test_mainloop.py`` now checks the stronger property directly -- that
no main-loop call has a body of nothing but a docstring.
"""

from __future__ import annotations
