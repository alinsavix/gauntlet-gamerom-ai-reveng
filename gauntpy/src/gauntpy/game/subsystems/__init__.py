"""ROM routine families and their shared game-side helpers.

The main loop imports named routines directly and retains the ROM's explicit
call sequence. Cross-family calls are ordinary dependencies, not an exception:
the former import prohibition existed only for parallel implementation work.
Import a routine or table from its defining module, not through another
family's compatibility exports. Shared working RAM remains in ``GameState``.

This package deliberately exports nothing. Compatibility entry points in
individual modules are explicit; private helpers are not compatibility APIs.
"""

from __future__ import annotations
