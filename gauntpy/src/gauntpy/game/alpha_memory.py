"""The modeled word/byte views of hidden alpha RAM at 0x905054.

The route grid uses 44 bytes in each 0x80-byte row. Its unused stride padding
is retained for snapshot compatibility rather than treated as route cells.
"""

from __future__ import annotations

from .state import GameState

ALPHA_COLUMNS = 64
ROUTE_FIRST_COLUMN = 42
ROUTE_ROWS = 24
ROUTE_ROW_BYTES = 0x80
ROUTE_BASE_OFFSET = 0x54
# The transporter routes (0x905C54 forward, 0x905D54 back, 0x5107A) are 22 words a row in the
# same off-screen columns: alpha rows 24-25 and 26-27.
TPORT_ROUTE_ROWS = {24: ("tport_route_forward", 0), 25: ("tport_route_forward", 22),
                    26: ("tport_route_reverse", 0), 27: ("tport_route_reverse", 22)}


# ROM: helper | Python alias maintenance: alpha writes in rows 24-27's off-screen columns reach the transporter route tables.
def _publish_tport_route(state: GameState, row: int, column: int, word: int) -> None:
    table = TPORT_ROUTE_ROWS.get(row)
    if table is None or column < ROUTE_FIRST_COLUMN:
        return
    routes = getattr(state, table[0])
    index = table[1] + column - ROUTE_FIRST_COLUMN
    if index < len(routes):
        routes[index] = word


# ROM: direct os:0x3586 | Indexed raw-word alpha write matches the OS implementation contract and doc/02; additionally synchronizes the Python route-byte alias. API 0x021E targets this body and is not counted separately.
def write_alpha_word(state: GameState, index: int, word: int) -> None:
    """Publish a complete alpha word and both live route bytes, if aliased."""
    word &= 0xFFFF
    state.alpha_ram[index] = word
    row, column = divmod(index, ALPHA_COLUMNS)
    if row < ROUTE_ROWS and column >= ROUTE_FIRST_COLUMN:
        offset = row * ROUTE_ROW_BYTES + (column - ROUTE_FIRST_COLUMN) * 2
        state.path_direction_grid[offset] = word >> 8
        state.path_direction_grid[offset + 1] = word & 0xFF
    _publish_tport_route(state, row, column, word)


# ROM: helper | Python clipped-row bulk write plus route-byte shadow synchronization; not a separately identified OS fill or text routine.
def fill_alpha_words(state: GameState, start: int, count: int, word: int) -> None:
    """Fill a single clipped row, retaining the efficient visible-word slice."""
    word &= 0xFFFF
    state.alpha_ram[start:start + count] = [word] * count
    row, column = divmod(start, ALPHA_COLUMNS)
    if row < ROUTE_ROWS:
        for hidden_column in range(max(ROUTE_FIRST_COLUMN, column), column + count):
            offset = row * ROUTE_ROW_BYTES + (hidden_column - ROUTE_FIRST_COLUMN) * 2
            state.path_direction_grid[offset] = word >> 8
            state.path_direction_grid[offset + 1] = word & 0xFF
    elif row in TPORT_ROUTE_ROWS:
        for hidden_column in range(max(ROUTE_FIRST_COLUMN, column), column + count):
            _publish_tport_route(state, row, hidden_column, word)


# ROM: helper | Python byte/word alias-maintenance primitive, not the route-selection algorithms that call it.
def write_path_grid_byte(state: GameState, offset: int, value: int) -> None:
    """Publish a route byte without changing its neighboring alpha byte."""
    value &= 0xFF
    state.path_direction_grid[offset] = value
    word_index, low_byte = divmod(ROUTE_BASE_OFFSET + offset, 2)
    word = state.alpha_ram[word_index]
    state.alpha_ram[word_index] = (
        (word & 0xFF00) | value
        if low_byte
        else (word & 0x00FF) | (value << 8)
    )
