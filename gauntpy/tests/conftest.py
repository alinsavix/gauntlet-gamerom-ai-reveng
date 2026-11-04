"""Keep real crash reports readable while Unicorn starts up."""

from __future__ import annotations

import faulthandler

from _pytest.faulthandler import fault_handler_stderr_fd_key
import pytest


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """Turn pytest's faulthandler off around ``Uc.mem_map``.

    On 64-bit Windows the first ``mem_map`` starts Unicorn's engine, which reserves
    its code buffer and writes to it uncommitted; its own exception handler commits
    the memory and the write is retried. faulthandler sees that access violation
    first and prints "Windows fatal exception" for every machine, which would bury a
    real crash. It has no way to report its file, so this takes it from pytest.
    """
    crash_log = config.stash.get(fault_handler_stderr_fd_key, None)
    if crash_log is None:                         # -p no:faulthandler
        return
    try:
        import unicorn
    except ImportError:
        return
    mem_map = unicorn.Uc.mem_map

    def mem_map_without_faulthandler(self, *args, **kwargs):
        faulthandler.disable()
        try:
            return mem_map(self, *args, **kwargs)
        finally:
            faulthandler.enable(file=crash_log)

    unicorn.Uc.mem_map = mem_map_without_faulthandler
