"""Compatibility exports for host state snapshots and resume."""

from ..host.state_dump import (
    DEFAULT_STATE_DUMP_DIR,
    STATE_DUMP_SCHEMA,
    StateDumpError,
    dump_game_state,
    game_state_from_payload,
    load_game_state,
    state_dump_payload,
)

__all__ = [
    "DEFAULT_STATE_DUMP_DIR", "STATE_DUMP_SCHEMA", "StateDumpError",
    "dump_game_state", "game_state_from_payload", "load_game_state",
    "state_dump_payload",
]
