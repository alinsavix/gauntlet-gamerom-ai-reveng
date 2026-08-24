"""Read-only host diagnostics, separate from the arcade display pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from ..constants import (
    GENERATOR_TYPES,
    MONSTER_TYPES,
    Character,
    GameMode,
    PlayerStatus,
)
from ..coords import hpos_x, vpos_y
from ..state import GameState

DEBUG_PANEL_WIDTH = 240
DEBUG_PANEL_HEIGHT = 240

_BACKGROUND = (16, 18, 22, 255)
_HEADING = (120, 220, 255, 255)
_LABEL = (170, 180, 190, 255)
_VALUE = (235, 238, 242, 255)
_DIM = (105, 115, 125, 255)
_DIVIDER = (55, 62, 70, 255)


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
    paused: bool = False


def capture_debug_snapshot(
    state: GameState, *, paused: bool = False,
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

    # Slots 1-12 are the fixed projectile channels; ordinary maze actors live
    # in the packed-cell range beginning at 32. Slots 13-31 are shared effects
    # and remain represented in the overall occupied count.
    occupied = range(1, len(state.mobs.picture))
    creature_types = set(MONSTER_TYPES) | set(GENERATOR_TYPES)
    return DebugSnapshot(
        frame=int(state.frame_counter) & 0xFFFF,
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
        players=tuple(players),
        paused=paused,
    )


def _enum_name(enum_type, value: int) -> str:  # noqa: ANN001
    try:
        return enum_type(value).name
    except ValueError:
        return str(value)


def debug_snapshot_lines(snapshot: DebugSnapshot) -> tuple[tuple[str, str], ...]:
    """Format one snapshot as stable label/value rows for any host UI."""
    mode = _enum_name(GameMode, snapshot.mode)
    it = "none" if snapshot.player_it == 0xFFFF else f"P{snapshot.player_it + 1}"
    rows: list[tuple[str, str]] = [
        ("FRAME", f"{snapshot.frame:05d}" + ("  PAUSED" if snapshot.paused else "")),
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
        status = _enum_name(PlayerStatus, player.status)
        character = _enum_name(Character, player.character)
        position = (
            f"{player.x:03d},{player.y:03d}"
            if player.x is not None and player.y is not None
            else "---,---"
        )
        rows.extend((
            (
                f"P{player.index + 1} {character[:4]}",
                f"{status[:5]} hp={player.health} sc={player.score}",
            ),
            (
                f"P{player.index + 1} POS/SLOT",
                f"{position} / {player.slot:03X}",
            ),
            (
                f"P{player.index + 1} K/P POW",
                f"{player.keys}/{player.potions} {player.powers:04X} "
                f"ss={player.supershot} st={player.stun}",
            ),
        ))
    return tuple(rows)


def render_debug_panel(
    snapshot: DebugSnapshot,
    *,
    width: int = DEBUG_PANEL_WIDTH,
    height: int = DEBUG_PANEL_HEIGHT,
) -> Image.Image:
    """Render host diagnostics with PIL, never with the game's alpha layer."""
    image = Image.new("RGBA", (width, height), _BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((6, 4), "GAUNTPY INTERNAL STATE", font=font, fill=_HEADING)
    draw.text((width - 52, 4), "F1 HIDE", font=font, fill=_DIM)
    draw.line((5, 16, width - 6, 16), fill=_DIVIDER)

    y = 20
    row_height = 9
    label_x = 6
    value_x = 84
    for label, value in debug_snapshot_lines(snapshot):
        if y + row_height > height:
            break
        draw.text((label_x, y), label, font=font, fill=_LABEL)
        draw.text((value_x, y), value, font=font, fill=_VALUE)
        y += row_height
    return image
