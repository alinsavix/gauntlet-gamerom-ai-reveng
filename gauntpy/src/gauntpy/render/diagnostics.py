"""Compatibility exports for immutable host diagnostics."""

from ..host.diagnostics import (
    DEBUG_PAGES,
    DEBUG_PANEL_WIDTH,
    DebugSnapshot,
    PlayerDebugSnapshot,
    capture_debug_snapshot,
    debug_page_lines,
    debug_snapshot_lines,
    derive_debug_events,
    render_debug_panel,
)

__all__ = [
    "DEBUG_PAGES", "DEBUG_PANEL_WIDTH", "DebugSnapshot", "PlayerDebugSnapshot",
    "capture_debug_snapshot", "debug_page_lines", "debug_snapshot_lines",
    "derive_debug_events", "render_debug_panel",
]
