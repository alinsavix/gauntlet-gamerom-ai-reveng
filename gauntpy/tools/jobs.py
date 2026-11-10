"""How many processes the checks may keep busy at once.

``GAUNTPY_JOBS`` sets it. Unset, it is a quarter of the logical CPUs, which leaves the
machine cool and responsive; a full machine's worth of Unicorn runs can overheat a laptop.
The suite's pytest-xdist workers, each tool's own pool and ``check_all.py``'s total all
stay inside it.
"""

from __future__ import annotations

import os


def default_jobs() -> int:
    text = os.environ.get("GAUNTPY_JOBS", "").strip()
    if text.isdigit() and int(text) > 0:
        return int(text)
    return max(1, (os.cpu_count() or 1) // 4)
