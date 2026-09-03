"""Read-only host diagnostics, separate from the arcade display pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageDraw, ImageFont

from ..constants import (
    GENERATOR_TYPES,
    MONSTER_TYPES,
    Character,
    GameMode,
    MazeObjIds,
    PlayerStatus,
)
from ..coords import hpos_x, vpos_y
from ..state import GameState

DEBUG_PANEL_WIDTH = 320
DEBUG_PANEL_HEIGHT = 240
DEBUG_FONT_SIZE = 12
DEBUG_HEADING_FONT_SIZE = 14
DEBUG_ROW_HEIGHT = 11
DEBUG_PAGES = (
    "OVERVIEW",
    "PLAYERS",
    "DEMO",
    "LEVEL",
    "FLAGS",
    "ACTORS",
    "AI",
    "DISPLAY",
    "ROUTES",
    "AUDIO",
    "SCENARIO",
    "EVENTS",
    "PERFORMANCE",
)

_BACKGROUND = (16, 18, 22, 255)
_HEADING = (120, 220, 255, 255)
_LABEL = (170, 180, 190, 255)
_VALUE = (235, 238, 242, 255)
_DIM = (105, 115, 125, 255)
_DIVIDER = (55, 62, 70, 255)

# Host explanations of the seventeen maze-header objectives. The cabinet's ROM
# hints are deliberately vague and many-to-one; these follow the actual event
# producers and exit predicates instead.
_SECRET_OBJECTIVE_DETAILS = (
    "TRANSPORT NEXT TO ACID",
    "TRANSPORT NEXT TO DEATH",
    "TRANSPORT INTO EXIT",
    "TRANSPORT THRU SECRET WALL",
    "SHOOT 2 FOOD ITEMS",
    "SHOOT 2 SECRET WALLS",
    "EXIT WITH 11 SUPER SHOTS",
    "TAKE INVULN; AVOID HITS",
    "DRAGON FLAG LOW 2 BITS = 0",
    "PUSH MOVABLE WALL INTO EXIT",
    "AVOID FAKE EXITS",
    "COLLECT NO KEYS/POTIONS",
    "EAT NO FOOD",
    "COLLECT NO TREASURE",
    "ENTER EXIT ON PUSH RETRY",
    "EXIT WHILE IT",
    "SHOOT NO PLAYER (SELF TOO)",
)

_FONT_CANDIDATES = (
    (
        Path(r"C:\Windows\Fonts\consola.ttf"),
        Path(r"C:\Windows\Fonts\consolab.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
    ),
    (
        Path("/System/Library/Fonts/Menlo.ttc"),
        Path("/System/Library/Fonts/Menlo.ttc"),
    ),
)


@dataclass(frozen=True)
class PlayerDebugSnapshot:
    index: int
    status: int
    character: int
    health: int
    score: int
    slot: int
    x: int | None
    y: int | None
    keys: int
    potions: int
    powers: int
    supershot: int
    stun: int


@dataclass(frozen=True)
class DebugSnapshot:
    frame: int
    render_time_ms: float
    render_time_current_ms: float
    render_time_history_ms: tuple[float, ...]
    mode: int
    level: int
    maze: int
    scroll_x: int
    scroll_y: int
    rng_seed: int
    player_it: int
    active_players: int
    dialog_timer: int
    occupied_mobs: int
    creatures: int
    projectiles: int
    slowmo_timer: int
    forcefield_color: int
    demo_positions: tuple[int, ...]
    demo_timers: tuple[int, ...]
    players: tuple[PlayerDebugSnapshot, ...]
    selected_mob: int
    route_grid: bytes
    route_markers: tuple[int, int, int, int]
    page_rows: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    paused: bool = False


def _name(enum_type, value: int) -> str:  # noqa: ANN001
    try:
        return enum_type(value).name
    except ValueError:
        return str(value)


def _pressed_input_names(raw: int) -> str:
    names = (
        (0x80, "U"), (0x40, "D"), (0x20, "L"), (0x10, "R"),
        (0x02, "FIRE"), (0x01, "MAGIC"),
    )
    pressed = [name for mask, name in names if not (raw & mask)]
    return "+".join(pressed) if pressed else "idle"


def _player_page_rows(
    state: GameState, players: tuple[PlayerDebugSnapshot, ...],
) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for player in players:
        live = state.players[player.index]
        position = (
            f"{player.x:03d},{player.y:03d}"
            if player.x is not None and player.y is not None
            else "---,---"
        )
        rows.extend((
            (
                f"P{player.index + 1} {_name(Character, player.character)[:4]}",
                f"{_name(PlayerStatus, player.status)} hp{player.health} sc{player.score}",
            ),
            ("  POS/SLOT", f"{position} / {player.slot:03X} face{live.direction}"),
            (
                "  INPUT",
                f"{state.player_input_raw[player.index]:04X} "
                f"{_pressed_input_names(state.player_input_raw[player.index])}",
            ),
            (
                "  ACTION",
                f"db{state.debounce_shift_magic[player.index]:04X}/"
                f"{state.debounce_shift_fire[player.index]:04X} "
                f"a{live.anim_counter:04X} f{state.player_fighting_dir[player.index]} "
                f"s{state.player_shooting[player.index]:04X} "
                f"w{state.player_joystick[player.index]:02X}",
            ),
            (
                "  TIMERS",
                f"st{live.stundelay} acid{live.acid_timer} hurt{live.hurt_cooldown} "
                f"tp{state.player_tport_phase[player.index]}",
            ),
        ))
    return tuple(rows)


def _demo_page_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = [
        ("ACTIVE", f"P{state.demo_active_player + 1}"),
        ("MODE/TIMER", f"{int(state.game_mode)} / {state.attract_timer}"),
    ]
    for index in range(len(state.players)):
        stream = state.demo_streams[index]
        pos = state.demo_stream_pos[index]
        duration = stream[pos] if 0 <= pos < len(stream) else 0
        raw = stream[pos + 1] if 0 <= pos + 1 < len(stream) else 0xFF
        rows.extend((
            (
                f"P{index + 1} PTR/TIMER",
                f"{pos:03d}/{len(stream):03d}  ram={state.demo_timers[index]:03d}",
            ),
            ("  RECORD", f"dur={duration:02X} joy={raw:02X}"),
            ("  INPUT", _pressed_input_names(raw)),
        ))
    return tuple(rows)


def _level_page_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    transporters = sum(
        state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER)
        for slot in range(32, len(state.mobs.picture))
        if state.mobs.picture[slot]
    )
    maze_trick = int(getattr(state.maze, "secret", 0) or 0)
    if state.game_mode == int(GameMode.TREAS_EXIT):
        secret_trick = "n/a during transition"
    elif state.mazenum_current >= 104:
        secret_trick = "n/a in bonus room"
    elif 1 <= maze_trick <= len(_SECRET_OBJECTIVE_DETAILS):
        secret_trick = (
            f"{maze_trick:02X} {_SECRET_OBJECTIVE_DETAILS[maze_trick - 1]}"
        )
    else:
        secret_trick = "none"
    return (
        ("CURRENT", f"level {state.levelnum_current} maze {state.mazenum_current}"),
        ("NEXT", f"level {state.level_next} maze {state.maze_next}"),
        ("WRAP", f"H={int(state.wrap_h)} V={int(state.wrap_v)}"),
        ("ROTATION", f"resume={state.maze_number} stride={state.maze_stride}"),
        ("IDLE/ESCAPE", f"{state.idle_timer} / {state.escape_timer}"),
        ("TREASURE", f"timer={state.treasure_timer} next={state.level_next_treasure}"),
        ("POTION NEXT", str(state.level_next_potion)),
        ("BONUS", f"timer={state.global_delay_timer} amount={state.bonus_amount}"),
        ("EXITS", f"{len(state.exit_slots)} open={state.exit_open_id:03X}"),
        ("EXIT MOVE", f"timer={state.exit_move_timer} frame={state.exit_anim_frame}"),
        ("TRANSPORTERS", str(transporters)),
        ("SECRET TRICK", secret_trick),
        ("SECRET ID", f"{state.secret_trick_id:02X} last={state.secret_trick_last:02X}"),
        ("SECRET WIN", f"{state.secret_player} hint={state.secret_need_hint}"),
        ("SECRET COUNT", f"{state.secret_possible_counter}/{state.secret_possible_start}"),
        (
            "SECRET FLAGS",
            " ".join(f"{value:02X}" for value in state.secret_tricks_flags),
        ),
        *_level_gate_rows(state),
    )


def _enabled(value: int, entries: tuple[tuple[int, str], ...]) -> str:
    names = [name for mask, name in entries if value & mask]
    return " ".join(names) if names else "-"


def _flags_page_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    flag1 = int(state.level_flags)
    flag2 = int(state.level_flags_2)
    flag3 = int(state.level_flags_3)
    flag4 = int(state.level_flags_4)
    return (
        ("RAW 1-4", f"{flag1:02X} {flag2:02X} {flag3:02X} {flag4:02X}"),
        ("F1 ODD", _enabled(flag1, (
            (0x01, "GHO"), (0x02, "GRU"), (0x10, "SOR"),
            (0x20, "AUX"), (0x40, "DEA"),
        ))),
        ("F1 MIRROR", _enabled(flag1, ((0x04, "H"), (0x08, "V")))),
        ("F1 WALL", _enabled(flag1, ((0x80, "INVIS TRAP"),))),
        ("F2 FAST", _enabled(flag2, (
            (0x01, "GHO"), (0x02, "GRU"), (0x04, "DEM"),
            (0x08, "LOB"), (0x10, "SOR"), (0x20, "AUX"), (0x40, "DEA"),
        ))),
        ("F2 WALL", _enabled(flag2, ((0x80, "INVIS ALL"),))),
        ("F3 FOOD", str(flag3 & 0x07)),
        ("F3 WALL", _enabled(flag3, (
            (0x08, "CYCLIC"), (0x10, "DELETE1"), (0x20, "DELETE2"),
        ))),
        ("F3 EXIT", _enabled(flag3, ((0x40, "MOVES"), (0x80, "CHOOSE1")))),
        ("F4 SHOTS", _enabled(flag4, ((0x01, "STUN"), (0x02, "HURT")))),
        ("F4 TRAPS", _enabled(flag4, ((0x04, "LOCAL"), (0x08, "ROTATE")))),
        ("F4 WORLD", _enabled(flag4, ((0x10, "WRAP V"), (0x20, "WRAP H")))),
        ("F4 OTHER", _enabled(flag4, ((0x40, "FAKE EXIT"), (0x80, "OFFSCREEN")))),
    )


def _level_gate_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    """Project the ROM's direct level-number gates for the current level."""
    level = int(state.levelnum_current)
    maze = int(state.mazenum_current)
    thief_chance = min(max(level >> 3, 0), 8)
    if level < 6:
        thief = "OFF (<6)"
    elif maze >= 115:
        thief = "OFF (secret maze)"
    else:
        thief = f"{thief_chance}/8"

    if 5 <= maze <= 101:
        depth = level % 400
        traps_local = bool(state.level_flags_4 & 0x04)
        if depth > 297:
            hazard = "RANDOM" if traps_local else "RANDOM+WRAP"
        elif depth > 200:
            hazard = "RANDOM"
        elif depth > 103:
            hazard = "BASE" if traps_local else "WRAP"
        else:
            hazard = "BASE"
    elif 104 <= maze <= 114:
        depth = level % 160
        if depth > 120:
            hazard = "WRAP+OFFSCREEN"
        elif depth > 80:
            hazard = "OFFSCREEN"
        elif depth > 40:
            hazard = "WRAP"
        else:
            hazard = "BASE"
    else:
        hazard = "n/a"

    random_pickups = maze < 115
    return (
        ("MAZE SOURCE", "FIXED OPENING" if level <= 5 else "CABINET ROTATION"),
        ("GATE >=3", "SPECIAL PICKUP ON" if level >= 3 and random_pickups else "OFF"),
        (
            "GATE >=6",
            f"HIDDEN POT {'ON' if level >= 6 and random_pickups else 'OFF'}; "
            f"THIEF {thief}",
        ),
        (
            "GATE >6",
            "ADAPTIVE FOOD + BONUS ON"
            if level > 6 and random_pickups else "OFF",
        ),
        (
            "GATE >=12",
            "DRAGON + TRICK 09 ON" if level >= 12 else "OFF",
        ),
        (
            "TREASURE >30",
            "PRANK VOICE ELIGIBLE"
            if level > 30 and 104 <= maze <= 114 else "OFF (NOT TREASURE)",
        ),
        (
            "GENERATOR CAP",
            "NONE (LEVEL 1)" if level == 1 else f"{level * 2}",
        ),
        ("FF PROFILE", str(level & 3)),
        ("HAZARD DEPTH", hazard),
    )


def _actor_counts(state: GameState) -> tuple[tuple[int, int], ...]:
    counts: dict[int, int] = {}
    for slot in range(32, len(state.mobs.picture)):
        if not state.mobs.picture[slot]:
            continue
        obj_type = state.mobs.obj_type(slot)
        counts[obj_type] = counts.get(obj_type, 0) + 1
    return tuple(sorted(counts.items()))


def _actor_page_rows(
    state: GameState, selected_mob: int,
) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = [
        ("OCCUPIED", str(sum(bool(word) for word in state.mobs.picture[1:]))),
        ("CHAIN HEAD", f"{state.mobs.depth_list_head:03X}"),
        ("SELECT", f"{selected_mob:03X}  [ / ]"),
    ]
    if 0 < selected_mob < len(state.mobs.picture):
        obj_type = state.mobs.obj_type(selected_mob)
        rows.extend((
            ("  TYPE", f"{obj_type:02X} {_name(MazeObjIds, obj_type)}"),
            ("  PICTURE", f"{state.mobs.picture[selected_mob]:04X}"),
            ("  HPOS", f"{state.mobs.hpos[selected_mob]:04X} x={hpos_x(state.mobs.hpos[selected_mob])}"),
            ("  VPOS", f"{state.mobs.vpos[selected_mob]:04X} y={vpos_y(state.mobs.vpos[selected_mob])}"),
            ("  LINK", f"{state.mobs.link[selected_mob]:04X}"),
            ("  STATE/LINK", f"{state.mobs.state_link[selected_mob]:04X}"),
            ("  LINKED", str(int(state.mobs.is_linked(selected_mob)))),
            (
                "  DEPTH KEY",
                f"{state.mobs.sort_key(selected_mob):03X}",
            ),
        ))
    rows.append(("TYPE COUNTS", ""))
    for obj_type, count in _actor_counts(state)[:8]:
        rows.append((f"  {_name(MazeObjIds, obj_type)[:13]}", str(count)))
    return tuple(rows)


def _ai_page_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    return (
        ("IT TARGET", "none" if state.player_it == 0xFFFF else f"P{state.player_it + 1}"),
        ("MONSTER ITER", f"{state.monster_iter_ptr:03X}"),
        ("SPAWN BONUS", str(state.monster_spawn_probability_bonus)),
        ("GEN RETRY", str(state.monster_generation_retry_timer)),
        ("SLOWMO", str(state.monster_slowmo_timer)),
        ("THIEF MODE", str(state.thief_mode)),
        ("THIEF MOB", f"{state.thief_mob_slot:03X}"),
        ("THIEF VICTIM", str(state.thief_victim)),
        ("THIEF POS", f"{state.thief_previous_pos:03X}>{state.thief_current_pos:03X}>{state.thief_next_pos:03X}"),
        ("THIEF DIR", f"{state.thief_direction} path={state.thief_path_direction}"),
        ("THIEF ENTRY", f"{state.thief_enter_time} speed={state.thief_speed}"),
        ("THIEF LOOT", f"{state.thief_item_carried:08X}"),
        ("DRAGON STATE", f"{state.dragon_state:04X} hits={state.dragon_hits}"),
        ("DRAGON PATH", f"{state.dragon_path_num} anim={state.dragon_anim_ctr}"),
        ("DRAGON FACE", f"{state.dragon_facing} move={state.dragon_move_state:04X}"),
        ("DRAGON FIRE", str(state.dragon_fire_cooldown)),
        (
            "DRAGON MOBS",
            " ".join(f"{slot:03X}" for slot in state.dragon_seg_mob_ids),
        ),
    )


def _display_page_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    nonzero_slips = sum(bool(slot) for slot in state.mobs.slip_heads)
    try:
        chain_length: int | str = sum(1 for _ in state.mobs.iter_chain())
    except RuntimeError:
        chain_length = "CYCLE"
    return (
        ("SCROLL", f"{state.scroll_x},{state.scroll_y}"),
        ("PF GENERATION", str(state.playfield_generation)),
        ("COLOR GEN", str(state.playfield_color_generation)),
        ("PF WORDS", str(len(state.playfield_ram))),
        ("ALPHA WORDS", str(len(state.alpha_ram))),
        ("MOB HEAD", f"{state.mobs.depth_list_head:03X}"),
        ("MOB CHAIN", str(chain_length)),
        ("SLIP HEADS", f"{nonzero_slips}/64"),
        ("TPORT CYCLE", f"{state.tport_cycle_pos} dir={state.tport_cycle_dir}"),
        ("FORCEFIELD", f"{state.forcefield_color:04X} step={state.forcefield_step}"),
        ("FF TIMER", str(state.forcefield_step_timer)),
        ("FF SEGMENTS", str(len(state.forcefield_segment_table))),
        ("PALETTE A/B", f"{state.palette_pulse_dir_a}/{state.palette_pulse_dir_b}"),
        ("DISPLAY ENABLE", str(state.score_display_enabled)),
    )


def _route_page_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    return (
        ("GRID", "LOW PURSUIT / HIGH ESCAPE"),
        ("BOXES", "C=current N=next S=start V=victim"),
        ("DIRECTIONS", "N NE E SE S SW W NW"),
    )


def _audio_page_rows(
    state: GameState, descriptions: Mapping[int, str],
) -> tuple[tuple[str, str], ...]:
    rows = [
        ("QUEUE", " ".join(f"{value:02X}" for value in state.sound_queue) or "empty"),
        ("QUEUE / LOG", f"{len(state.sound_queue)} / {len(state.sound_log)}"),
        ("HOLDOFF / STATE", f"{state.sound_holdoff} / {state.sound_queue_state:04X}"),
        ("IDLE / RETRIES", f"{state.sound_idle_timer} / {state.sound_retry_count}"),
        ("INCOMING", " ".join(f"{value:02X}" for value in state.sound_incoming) or "empty"),
    ]
    recent = state.sound_log[-12:]
    if not recent:
        rows.append(("RECENT", "none"))
    else:
        for index, command in enumerate(recent, start=1 - len(recent)):
            description = descriptions.get(command, "Unknown command")
            rows.append((f"{index:+03d}", f"{command:02X} {description}"))
    return tuple(rows)


def _scenario_page_rows(state: GameState) -> tuple[tuple[str, str], ...]:
    from ..custom_scenario import synthetic_runtime_for

    runtime = synthetic_runtime_for(state)
    if runtime is None:
        return (("SCENARIO", "no synthetic fixture loaded"),)
    scenario = runtime.scenario
    input_mode = (
        "LIVE"
        if runtime.current_input is None
        else _pressed_input_names(runtime.current_input).upper()
    )
    rows: list[tuple[str, str]] = [
        ("NAME", scenario.name),
        ("SOURCE", scenario.source_name or "embedded"),
        ("HASH", scenario.sha256[:16]),
        ("INPUT", input_mode),
        ("EVENTS", f"{len(runtime.fired_events)}/{len(scenario.events)} fired"),
    ]
    for player_index, input_word in enumerate(runtime.additional_inputs, 2):
        if input_word is None:
            continue
        rows.append((
            f"INPUT P{player_index}",
            _pressed_input_names(input_word).upper(),
        ))
    current = int(state.frame_counter) & 0xFFFF
    for index, event in enumerate(scenario.events):
        action = " ".join((event.action, *event.args))
        if index in runtime.fired_events:
            value = f"FIRED @{event.frame:05d} {action}"
        elif event.frame >= current:
            value = f"T-{event.frame - current:05d} @{event.frame:05d} {action}"
        else:
            value = f"MISSED +{current - event.frame:05d} {action}"
        rows.append((f"EVT {index:02d}", value))
    return tuple(rows)


def capture_debug_snapshot(
    state: GameState, *, paused: bool = False, selected_mob: int = 0,
    render_time_ms: float = 0.0,
    render_time_current_ms: float | None = None,
    render_time_history_ms: tuple[float, ...] = (),
    sound_descriptions: Mapping[int, str] | None = None,
) -> DebugSnapshot:
    """Project live state into immutable host data without mutating the game."""
    players = []
    for player in state.players:
        slot = int(player.mob_slot)
        has_position = 0 < slot < len(state.mobs.hpos)
        players.append(
            PlayerDebugSnapshot(
                index=int(player.index),
                status=int(player.status),
                character=int(player.character),
                health=int(player.health),
                score=int(player.score),
                slot=slot,
                x=hpos_x(state.mobs.hpos[slot]) if has_position else None,
                y=vpos_y(state.mobs.vpos[slot]) if has_position else None,
                keys=int(player.keysnum),
                potions=int(player.potionsnum),
                powers=int(player.powers) & 0xFFFF,
                supershot=int(player.supershot),
                stun=int(player.stundelay),
            )
        )

    player_snapshots = tuple(players)
    occupied_slots = tuple(
        slot for slot in range(1, len(state.mobs.picture))
        if state.mobs.picture[slot]
    )
    if selected_mob not in occupied_slots:
        selected_mob = occupied_slots[0] if occupied_slots else 0

    # Slots 1-12 are the fixed projectile channels; ordinary maze actors live
    # in the packed-cell range beginning at 32. Slots 13-31 are shared effects
    # and remain represented in the overall occupied count.
    occupied = range(1, len(state.mobs.picture))
    creature_types = set(MONSTER_TYPES) | set(GENERATOR_TYPES)
    return DebugSnapshot(
        frame=int(state.frame_counter) & 0xFFFF,
        render_time_ms=float(render_time_ms),
        render_time_current_ms=float(
            render_time_ms if render_time_current_ms is None
            else render_time_current_ms
        ),
        render_time_history_ms=tuple(
            float(value) for value in render_time_history_ms
        ),
        mode=int(state.game_mode),
        level=int(state.levelnum_current),
        maze=int(state.mazenum_current),
        scroll_x=int(state.scroll_x),
        scroll_y=int(state.scroll_y),
        rng_seed=int(state.rng.seed) & 0xFFFF,
        player_it=int(state.player_it) & 0xFFFF,
        active_players=int(state.level_players_active),
        dialog_timer=int(state.dialog_timer),
        occupied_mobs=sum(bool(state.mobs.picture[slot]) for slot in occupied),
        creatures=sum(
            state.mobs.obj_type(slot) in creature_types
            for slot in range(32, len(state.mobs.picture))
            if state.mobs.picture[slot]
        ),
        projectiles=sum(bool(state.mobs.picture[slot]) for slot in range(1, 13)),
        slowmo_timer=int(state.monster_slowmo_timer),
        forcefield_color=int(state.forcefield_color) & 0xFFFF,
        demo_positions=tuple(int(value) for value in state.demo_stream_pos),
        demo_timers=tuple(int(value) for value in state.demo_timers),
        players=player_snapshots,
        selected_mob=selected_mob,
        route_grid=bytes(state.path_direction_grid),
        route_markers=(
            int(state.thief_current_pos),
            int(state.thief_next_pos),
            int(state.thief_start_location),
            int(state.thief_victim_pos),
        ),
        page_rows=(
            ("PLAYERS", _player_page_rows(state, player_snapshots)),
            ("DEMO", _demo_page_rows(state)),
            ("LEVEL", _level_page_rows(state)),
            ("FLAGS", _flags_page_rows(state)),
            ("ACTORS", _actor_page_rows(state, selected_mob)),
            ("AI", _ai_page_rows(state)),
            ("DISPLAY", _display_page_rows(state)),
            ("ROUTES", _route_page_rows(state)),
            ("AUDIO", _audio_page_rows(state, sound_descriptions or {})),
            ("SCENARIO", _scenario_page_rows(state)),
        ),
        paused=paused,
    )


@lru_cache(maxsize=4)
def _host_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a platform monospace font, with Pillow's scalable font as fallback."""
    index = 1 if bold else 0
    for pair in _FONT_CANDIDATES:
        path = pair[index]
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def debug_snapshot_lines(snapshot: DebugSnapshot) -> tuple[tuple[str, str], ...]:
    """Format one snapshot as stable label/value rows for any host UI."""
    mode = _name(GameMode, snapshot.mode)
    it = "none" if snapshot.player_it == 0xFFFF else f"P{snapshot.player_it + 1}"
    rows: list[tuple[str, str]] = [
        (
            "FRAME",
            f"{snapshot.frame:05d}  RENDER {snapshot.render_time_ms:.2f} ms"
            + ("  PAUSED" if snapshot.paused else ""),
        ),
        ("MODE", f"{mode} ({snapshot.mode})"),
        ("LEVEL / MAZE", f"{snapshot.level} / {snapshot.maze}"),
        ("CAMERA", f"{snapshot.scroll_x:03d}, {snapshot.scroll_y:03d}"),
        ("RNG", f"0x{snapshot.rng_seed:04X}"),
        ("PLAYERS / IT", f"{snapshot.active_players} / {it}"),
        ("DIALOG / SLOW", f"{snapshot.dialog_timer} / {snapshot.slowmo_timer}"),
        (
            "MOBS C/S",
            f"{snapshot.occupied_mobs}  {snapshot.creatures}/{snapshot.projectiles}",
        ),
        ("FORCEFIELD", f"0x{snapshot.forcefield_color:04X}"),
        (
            "DEMO PTR",
            " ".join(f"{value:03d}" for value in snapshot.demo_positions),
        ),
        (
            "DEMO TIMER",
            " ".join(f"{value:03d}" for value in snapshot.demo_timers),
        ),
    ]
    for player in snapshot.players:
        status = _name(PlayerStatus, player.status)
        character = _name(Character, player.character)
        position = (
            f"{player.x:03d},{player.y:03d}"
            if player.x is not None and player.y is not None
            else "---,---"
        )
        rows.extend((
            (
                f"P{player.index + 1} {character[:4]}",
                f"{status[:5]} hp{player.health} sc{player.score}",
            ),
            (
                f"P{player.index + 1} POS/K/P",
                f"{position} s{player.slot:03X} k{player.keys} p{player.potions} "
                f"w{player.powers:04X} x{player.supershot} t{player.stun}",
            ),
        ))
    return tuple(rows)


def derive_debug_events(
    previous: DebugSnapshot | None, current: DebugSnapshot,
) -> tuple[str, ...]:
    """Infer host-only events by comparing two immutable snapshots."""
    if previous is None:
        return ()
    events: list[str] = []
    if previous.mode != current.mode:
        events.append(
            f"mode {_name(GameMode, previous.mode)} -> {_name(GameMode, current.mode)}"
        )
    if (previous.level, previous.maze) != (current.level, current.maze):
        events.append(
            f"level/maze {previous.level}/{previous.maze} -> "
            f"{current.level}/{current.maze}"
        )
    if previous.player_it != current.player_it:
        old = "none" if previous.player_it == 0xFFFF else f"P{previous.player_it + 1}"
        new = "none" if current.player_it == 0xFFFF else f"P{current.player_it + 1}"
        events.append(f"IT {old} -> {new}")

    for before, after in zip(previous.players, current.players):
        prefix = f"P{after.index + 1}"
        if before.status != after.status:
            events.append(
                f"{prefix} {_name(PlayerStatus, before.status)} -> "
                f"{_name(PlayerStatus, after.status)}"
            )
        health_delta = after.health - before.health
        if health_delta:
            action = "health" if health_delta > 0 else "damage"
            events.append(f"{prefix} {action} {health_delta:+d} = {after.health}")
        score_delta = after.score - before.score
        if score_delta:
            events.append(f"{prefix} score {score_delta:+d} = {after.score}")
        if before.keys != after.keys:
            events.append(f"{prefix} keys {before.keys} -> {after.keys}")
        if before.potions != after.potions:
            events.append(f"{prefix} potions {before.potions} -> {after.potions}")
        if before.powers != after.powers:
            events.append(f"{prefix} powers {before.powers:04X} -> {after.powers:04X}")
        if before.slot != after.slot and (
            before.status != int(PlayerStatus.REMOVED)
            or after.status != int(PlayerStatus.REMOVED)
        ):
            events.append(f"{prefix} slot {before.slot:03X} -> {after.slot:03X}")
    return tuple(events)


def debug_page_lines(
    snapshot: DebugSnapshot,
    page: int,
    *,
    events: tuple[str, ...] = (),
) -> tuple[tuple[str, str], ...]:
    """Return stable rows for one diagnostics page."""
    page %= len(DEBUG_PAGES)
    name = DEBUG_PAGES[page]
    if name == "OVERVIEW":
        return debug_snapshot_lines(snapshot)
    if name == "EVENTS":
        if not events:
            return (("EVENT LOG", "no changes observed while panel was open"),)
        return tuple(
            (f"{index + 1:02d}", event)
            for index, event in enumerate(events[-20:])
        )
    if name == "PERFORMANCE":
        history = snapshot.render_time_history_ms
        return (
            ("RENDER AVG10", f"{snapshot.render_time_ms:.2f} ms"),
            ("CURRENT", f"{snapshot.render_time_current_ms:.2f} ms"),
            ("SAMPLES", str(len(history))),
            ("RANGE", (
                f"{min(history):.2f} - {max(history):.2f} ms"
                if history else "no samples"
            )),
        )
    return dict(snapshot.page_rows).get(name, ())


def _performance_graph_scale(
    history: tuple[float, ...],
) -> tuple[float, tuple[float, float, float]]:
    ceiling = max(20.0, ceil(max(history, default=0.0) / 10.0) * 10.0)
    return ceiling, (0.0, ceiling / 2.0, ceiling)


_ROUTE_COLORS = (
    (70, 130, 255, 255),   # N
    (70, 210, 255, 255),   # NE
    (70, 230, 120, 255),   # E
    (190, 235, 70, 255),   # SE
    (255, 205, 70, 255),   # S
    (255, 135, 70, 255),   # SW
    (235, 75, 75, 255),    # W
    (190, 90, 235, 255),   # NW
)
_ROUTE_MARKER_COLORS = (
    (255, 255, 255, 255),
    (255, 230, 50, 255),
    (70, 255, 120, 255),
    (70, 235, 255, 255),
)


def _route_direction(grid: bytes, slot: int, *, escape: bool) -> int:
    """Read one ROM path nibble through its 44-byte/128-byte-stride view."""
    if not 0 <= slot <= 0x3FF:
        return 8
    offset = (slot // 44) * 0x80 + slot % 44
    packed = grid[offset] >> (4 if escape else 0)
    direction = (packed & 0x0F) - 1
    return direction if 0 <= direction <= 7 else 8


def _draw_route_grids(
    draw: ImageDraw.ImageDraw, snapshot: DebugSnapshot, font: ImageFont.ImageFont,
) -> None:
    cell = 4
    top = 90
    lefts = (8, 174)
    marker_x = 8
    for label, color in zip(
        ("C", "N", "S", "V"), _ROUTE_MARKER_COLORS, strict=True,
    ):
        draw.rectangle(
            (marker_x, top - 26, marker_x + 6, top - 20), outline=color,
        )
        draw.text((marker_x + 9, top - 29), label, font=font, fill=_DIM)
        marker_x += 34
    for escape, left in zip((False, True), lefts, strict=True):
        draw.text(
            (left, top - 13),
            "HIGH ESCAPE" if escape else "LOW PURSUIT",
            font=font,
            fill=_LABEL,
        )
        draw.rectangle(
            (left - 1, top - 1, left + 32 * cell, top + 32 * cell),
            outline=_DIVIDER,
        )
        for slot in range(0x400):
            row, column = divmod(slot, 32)
            direction = _route_direction(
                snapshot.route_grid, slot, escape=escape,
            )
            if direction == 8:
                continue
            x = left + column * cell
            y = top + row * cell
            draw.rectangle(
                (x, y, x + cell - 1, y + cell - 1),
                fill=_ROUTE_COLORS[direction],
            )
        for slot, color in zip(
            snapshot.route_markers, _ROUTE_MARKER_COLORS, strict=True,
        ):
            if not 0 <= slot <= 0x3FF:
                continue
            row, column = divmod(slot, 32)
            x = left + column * cell
            y = top + row * cell
            draw.rectangle(
                (x, y, x + cell - 1, y + cell - 1),
                outline=color,
            )

    legend_y = top + 32 * cell + 7
    labels = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    x = 8
    for label, color in zip(labels, _ROUTE_COLORS, strict=True):
        draw.rectangle((x, legend_y + 2, x + 5, legend_y + 7), fill=color)
        draw.text((x + 8, legend_y), label, font=font, fill=_DIM)
        x += 36


def render_debug_panel(
    snapshot: DebugSnapshot,
    *,
    width: int = DEBUG_PANEL_WIDTH,
    height: int = DEBUG_PANEL_HEIGHT,
    page: int = 0,
    events: tuple[str, ...] = (),
) -> Image.Image:
    """Render host diagnostics with PIL, never with the game's alpha layer."""
    image = Image.new("RGBA", (width, height), _BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = _host_font(DEBUG_FONT_SIZE)
    heading_font = _host_font(DEBUG_HEADING_FONT_SIZE, bold=True)
    page %= len(DEBUG_PAGES)
    title = f"{page + 1}/{len(DEBUG_PAGES)} {DEBUG_PAGES[page]}"
    draw.text((8, 4), title, font=heading_font, fill=_HEADING)
    controls = "F1 HIDE  F2< F3>  [ ] MOB"
    controls_box = draw.textbbox((0, 0), controls, font=font)
    draw.text(
        (width - (controls_box[2] - controls_box[0]) - 8, 6),
        controls,
        font=font,
        fill=_DIM,
    )
    draw.line((7, 23, width - 8, 23), fill=_DIVIDER)

    y = 27
    row_height = DEBUG_ROW_HEIGHT
    label_x = 8
    value_x = 104
    for label, value in debug_page_lines(snapshot, page, events=events):
        if y + row_height > height:
            break
        draw.text((label_x, y), label, font=font, fill=_LABEL)
        draw.text((value_x, y), value, font=font, fill=_VALUE)
        y += row_height
    if DEBUG_PAGES[page] == "PERFORMANCE" and snapshot.render_time_history_ms:
        history = snapshot.render_time_history_ms
        left, top, right, bottom = 46, 82, width - 8, height - 10
        draw.rectangle((left, top, right, bottom), outline=_DIVIDER)
        ceiling, ticks = _performance_graph_scale(history)
        for value in ticks:
            tick_y = bottom - 1 - value * (bottom - top - 2) / ceiling
            label = f"{value:g} ms"
            label_box = draw.textbbox((0, 0), label, font=font)
            draw.text(
                (left - (label_box[2] - label_box[0]) - 5, tick_y - 5),
                label,
                font=font,
                fill=_DIM,
            )
            draw.line((left - 3, tick_y, right - 1, tick_y), fill=_DIVIDER)
        points = []
        for index, value in enumerate(history):
            x = left + 1 + index * (right - left - 2) / max(1, len(history) - 1)
            y = bottom - 1 - min(value, ceiling) * (bottom - top - 2) / ceiling
            points.append((x, y))
        if len(points) == 1:
            draw.point(points[0], fill=_HEADING)
        else:
            draw.line(points, fill=_HEADING, width=2)
        budget_y = bottom - 1 - 16.67 * (bottom - top - 2) / ceiling
        draw.line(
            (left + 1, budget_y, right - 1, budget_y),
            fill=(120, 80, 80, 255),
        )
    elif DEBUG_PAGES[page] == "ROUTES":
        _draw_route_grids(draw, snapshot, font)
    return image
