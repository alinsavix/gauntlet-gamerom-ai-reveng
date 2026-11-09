"""Keep real crash reports readable while Unicorn starts up."""

from __future__ import annotations

import faulthandler

from _pytest.faulthandler import fault_handler_stderr_fd_key
import pytest


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """Turn pytest's faulthandler off around ``Uc.mem_map`` and ``Uc.emu_start``.

    On 64-bit Windows the first ``mem_map`` starts Unicorn's engine, which reserves
    its code buffer and writes to it uncommitted; its own exception handler commits
    the memory and the write is retried. A long ``emu_start`` grows the same buffer
    the same way. faulthandler sees that access violation first and prints "Windows
    fatal exception" each time, which would bury a real crash. It has no way to
    report its file, so this takes it from pytest. A crash anywhere else is still
    reported.
    """
    crash_log = config.stash.get(fault_handler_stderr_fd_key, None)
    if crash_log is None:                         # -p no:faulthandler
        return
    try:
        import unicorn
    except ImportError:
        return
    def without_faulthandler(method):
        def call(self, *args, **kwargs):
            faulthandler.disable()
            try:
                return method(self, *args, **kwargs)
            finally:
                faulthandler.enable(file=crash_log)
        return call

    unicorn.Uc.mem_map = without_faulthandler(unicorn.Uc.mem_map)
    unicorn.Uc.emu_start = without_faulthandler(unicorn.Uc.emu_start)
