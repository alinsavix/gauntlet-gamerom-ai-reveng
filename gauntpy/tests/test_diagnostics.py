"""Host-only diagnostics remain read-only and independent of arcade VRAM."""

from __future__ import annotations

from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus
from gauntpy.coords import encode_hpos, encode_vpos_at_y, pack_slot
from gauntpy.render.diagnostics import (
    DEBUG_PAGES,
    DEBUG_FONT_SIZE,
    DEBUG_PANEL_HEIGHT,
    DEBUG_PANEL_WIDTH,
    DEBUG_ROW_HEIGHT,
    _host_font,
    capture_debug_snapshot,
    debug_page_lines,
    debug_snapshot_lines,
    derive_debug_events,
    render_debug_panel,
)
from gauntpy.state import GameState


def _diagnostic_state() -> GameState:
    state = GameState(game_mode=GameMode.DEMO)
    state.frame_counter = 123
    state.levelnum_current = 7
    state.mazenum_current = 102
    state.scroll_x, state.scroll_y = 17, 29
    state.player_it = 1
    state.dialog_timer = 45
    state.demo_stream_pos = [0, 118, 0, 20]
    state.demo_timers = [0, 14, 0, 3]
    player = state.players[1]
    player.status = PlayerStatus.ALIVE_HERE
    player.character = Character.ELF
    player.health = 1600
    player.score = 250
    player.keysnum = 2
    player.potionsnum = 1
    slot = pack_slot(9, 12)
    player.mob_slot = slot
    state.mobs.create(
        slot, 0x1E0D, encode_hpos(188, palette=13), encode_vpos_at_y(144),
        MazeObjIds.PLAYERSTART, 1,
    )
    state.level_players_active = 1
    return state


def test_snapshot_projects_internal_state_without_mutating_the_game():
    state = _diagnostic_state()
    before = (
        state.frame_counter,
        state.player_it,
        tuple(state.demo_stream_pos),
        tuple(state.alpha_ram),
        tuple(state.mobs.picture),
    )

    snapshot = capture_debug_snapshot(state, paused=True)

    assert snapshot.frame == 123
    assert snapshot.mode == int(GameMode.DEMO)
    assert snapshot.player_it == 1
    assert snapshot.demo_positions == (0, 118, 0, 20)
    assert snapshot.players[1].character == int(Character.ELF)
    assert (snapshot.players[1].x, snapshot.players[1].y) == (188, 144)
    assert snapshot.paused
    assert before == (
        state.frame_counter,
        state.player_it,
        tuple(state.demo_stream_pos),
        tuple(state.alpha_ram),
        tuple(state.mobs.picture),
    )


def test_snapshot_rows_include_global_demo_and_player_state():
    rows = dict(debug_snapshot_lines(capture_debug_snapshot(_diagnostic_state())))

    assert rows["MODE"] == "DEMO (-3)"
    assert rows["LEVEL / MAZE"] == "7 / 102"
    assert rows["PLAYERS / IT"] == "1 / P2"
    assert rows["DEMO PTR"] == "000 118 000 020"
    assert "hp1600" in rows["P2 ELF"]
    assert rows["P2 POS/K/P"].startswith("188,144 s12C k2 p1")


def test_panel_is_a_separate_host_raster():
    state = _diagnostic_state()
    before_alpha = tuple(state.alpha_ram)

    image = render_debug_panel(capture_debug_snapshot(state))

    assert image.size == (DEBUG_PANEL_WIDTH, DEBUG_PANEL_HEIGHT)
    assert image.mode == "RGBA"
    assert image.getbbox() is not None
    assert tuple(state.alpha_ram) == before_alpha


def test_panel_uses_a_scalable_antialiased_font():
    from PIL import ImageFont

    font = _host_font(DEBUG_FONT_SIZE)
    assert isinstance(font, ImageFont.FreeTypeFont)
    assert DEBUG_FONT_SIZE == 12
    snapshot = capture_debug_snapshot(_diagnostic_state())
    assert 27 + len(debug_snapshot_lines(snapshot)) * DEBUG_ROW_HEIGHT <= \
        DEBUG_PANEL_HEIGHT


def test_every_diagnostics_page_has_read_only_rows():
    state = _diagnostic_state()
    selected = pack_slot(9, 12)
    snapshot = capture_debug_snapshot(state, selected_mob=selected)

    assert snapshot.selected_mob == selected
    for page, name in enumerate(DEBUG_PAGES):
        rows = debug_page_lines(
            snapshot, page, events=("00123 test event",),
        )
        assert rows, name
        image = render_debug_panel(
            snapshot, page=page, events=("00123 test event",), height=960,
        )
        assert image.size == (DEBUG_PANEL_WIDTH, 960)


def test_event_log_is_derived_from_snapshots_without_game_instrumentation():
    state = _diagnostic_state()
    before = capture_debug_snapshot(state)
    state.player_it = 2
    state.players[1].health -= 25
    state.players[1].score += 100
    state.players[1].potionsnum = 0
    after = capture_debug_snapshot(state)

    events = derive_debug_events(before, after)

    assert "IT P2 -> P3" in events
    assert "P2 damage -25 = 1575" in events
    assert "P2 score +100 = 350" in events
    assert "P2 potions 1 -> 0" in events


def test_corrupt_depth_chain_is_reported_without_crashing_the_host():
    state = _diagnostic_state()
    state.mobs.depth_list_head = 1
    state.mobs.set_next(1, 1)

    snapshot = capture_debug_snapshot(state)
    display_rows = dict(debug_page_lines(
        snapshot, DEBUG_PAGES.index("DISPLAY"),
    ))

    assert display_rows["MOB CHAIN"] == "CYCLE"
