"""Subsystem implementations, one module per work package.

Every main-loop call already exists here as a function with the ROM's name, its
address, and its references -- unimplemented ones are marked ``@stub`` and do
nothing. That means the loop runs from day one, ``mainloop.py`` imports real
names rather than looking anything up, and a work package is finished by
filling in a body and deleting a decorator.

Modules must not import each other: everything they share travels through
``GameState``, exactly as the original's subsystems shared working RAM. That is
what makes the work packages in ``PLAN.md`` independently assignable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

F = TypeVar("F", bound=Callable[..., object])


def stub(fn: F) -> F:
    """Mark a main-loop call as not yet implemented.

    Delete the decorator when the work package lands. ``python -m gauntpy``
    reports what is still stubbed.
    """
    fn.is_stub = True  # type: ignore[attr-defined]
    return fn


def is_stub(fn: Callable[..., object]) -> bool:
    return getattr(fn, "is_stub", False)
