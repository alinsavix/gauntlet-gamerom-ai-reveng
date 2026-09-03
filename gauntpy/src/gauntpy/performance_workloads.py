"""Host-only benchmark/stress workloads and integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import Character, GameMode, NULL_SLOT, NUM_MOB_SLOTS, NUM_SLIP_BANDS
from .state import GameState


@dataclass(frozen=True)
class PerformanceWorkload:
    """One deterministic state recipe used only by the host harness."""

    name: str
    description: str
    attract_mode: int | None = None
    level_maze: tuple[int, int] | None = None
    scenario_filename: str | None = None
    character: int = int(Character.ELF)
    setup: str | None = None


WORKLOADS = (
    PerformanceWorkload(
        "rom-title", "title attract screen", attract_mode=int(GameMode.TITLE),
    ),
    PerformanceWorkload(
        "rom-demo", "recorded attract-mode gameplay", attract_mode=int(GameMode.DEMO),
    ),
    PerformanceWorkload(
        "rom-dragon", "level 12 / maze 11 dragon gameplay", level_maze=(12, 11),
    ),
    PerformanceWorkload(
        "rom-moving-exits",
        "level 16 / maze 15 moving walls and fake exits",
        level_maze=(16, 15),
    ),
    PerformanceWorkload(
        "rom-scores", "high-score screen over maze 103", attract_mode=int(GameMode.SCORES),
    ),
    PerformanceWorkload(
        "rom-legend", "legend screen over maze 103", attract_mode=int(GameMode.LEGEND),
    ),
    PerformanceWorkload(
        "benchmark-empty",
        "open arena with automated movement, Fire, and Magic",
        scenario_filename="benchmark-empty.gsc",
    ),
    PerformanceWorkload(
        "benchmark-generators",
        "generator-dense arena",
        scenario_filename="benchmark-generators.gsc",
    ),
    PerformanceWorkload(
        "benchmark-mobs",
        "dense mix of every ordinary monster family",
        scenario_filename="benchmark-mobs.gsc",
    ),
    PerformanceWorkload(
        "benchmark-random-walls",
        "random-wall-heavy maze",
        scenario_filename="benchmark-random-walls.gsc",
    ),
    PerformanceWorkload(
        "benchmark-cyclic-walls",
        "cyclic-wall-heavy maze",
        scenario_filename="benchmark-cyclic-walls.gsc",
    ),
    PerformanceWorkload(
        "pathological-ten-dragons",
        "ten dragon anchors competing for the ROM's singleton dragon state",
        scenario_filename="pathological-ten-dragons.gsc",
    ),
    PerformanceWorkload(
        "pathological-slot-saturation",
        "almost every maze cell occupied by a linked MOB",
        scenario_filename="pathological-slot-saturation.gsc",
    ),
    PerformanceWorkload(
        "pathological-projectile-channels",
        "all twelve fixed projectile channels live simultaneously",
        scenario_filename="pathological-projectile-channels.gsc",
        setup="all-projectiles",
    ),
    PerformanceWorkload(
        "pathological-four-players",
        "four heroes moving, firing, and casting concurrently",
        scenario_filename="pathological-four-players.gsc",
        setup="four-players",
    ),
    PerformanceWorkload(
        "pathological-boxed-generators",
        "tier-three generators with no legal spawn cell",
        scenario_filename="pathological-boxed-generators.gsc",
    ),
    PerformanceWorkload(
        "pathological-overlapping-specials",
        "dragon footprints overwritten by exits and transporters",
        scenario_filename="pathological-overlapping-specials.gsc",
    ),
    PerformanceWorkload(
        "pathological-wall-intersection",
        "moving, random, cyclic, and forcefield walls sharing one arena",
        scenario_filename="pathological-wall-intersection.gsc",
    ),
    PerformanceWorkload(
        "pathological-wrap-seams",
        "actors and shots packed against horizontal and vertical wrap seams",
        scenario_filename="pathological-wrap-seams.gsc",
    ),
    PerformanceWorkload(
        "pathological-counter-wrap",
        "scripted input crossing the 16-bit frame-counter boundary",
        scenario_filename="pathological-counter-wrap.gsc",
        setup="counter-wrap",
    ),
)
WORKLOAD_BY_NAME = {workload.name: workload for workload in WORKLOADS}


def scenario_path(workload: PerformanceWorkload) -> Path:
    """Return a packaged synthetic workload's declarative fixture path."""
    if workload.scenario_filename is None:
        raise ValueError(f"{workload.name!r} is not a synthetic workload")
    return Path(__file__).resolve().parents[2] / "scenarios" / workload.scenario_filename


def selected_workloads(name: str | None) -> tuple[PerformanceWorkload, ...]:
    """Resolve a CLI selection, with ``None`` and ``all`` selecting the suite."""
    if name is None or name == "all":
        return WORKLOADS
    return (WORKLOAD_BY_NAME[name],)


def format_workload_catalog() -> str:
    """Return a stable terminal listing for workload discovery."""
    width = max(len(workload.name) for workload in WORKLOADS)
    return "\n".join(
        f"{workload.name:<{width}}  {workload.description}" for workload in WORKLOADS
    )


def prepare_workload_state(
    state: GameState, workload: PerformanceWorkload,
) -> None:
    """Apply fixture-only setup that declarative maze placement cannot express."""
    if workload.setup in {"four-players", "all-projectiles"}:
        _join_four_players(state)
    if workload.setup == "all-projectiles":
        _fill_projectile_channels(state)
    elif workload.setup == "counter-wrap":
        state.frame_counter = 0xFFF0
    elif workload.setup not in {None, "four-players"}:
        raise ValueError(f"unknown workload setup {workload.setup!r}")


def _join_four_players(state: GameState) -> None:
    from .constants import SLOT_PLAYER_SHOTS
    from .subsystems.players import player_join

    for slot in SLOT_PLAYER_SHOTS:
        state.mobs.unlink_and_clear(slot)
    for player_index, player in enumerate(state.players):
        player.character = player_index
        player.health = 20000
        player.potionsnum = 20
        player.direction = player_index * 2
        if player_index and not player.active:
            player_join(state, player_index)
        if not player.active:
            raise HarnessInvariantError(
                f"four-player workload could not place player {player_index + 1}"
            )


def _fill_projectile_channels(state: GameState) -> None:
    from .constants import MazeObjIds, SLOT_DEMON_SHOTS, SLOT_LOBBER_SHOTS
    from .subsystems.monsters import monster_create_shot
    from .subsystems.players import player_create_shot

    for player_index, direction in enumerate((0, 2, 6, 4)):
        state.players[player_index].direction = direction
        player_create_shot(state, player_index)

    demons = [
        slot for slot in state.mobs.iter_chain()
        if state.mobs.obj_type(slot) == int(MazeObjIds.MONST_DEMON)
    ]
    lobbers = [
        slot for slot in state.mobs.iter_chain()
        if state.mobs.obj_type(slot) == int(MazeObjIds.MONST_LOBBER)
    ]
    if len(demons) < 4 or len(lobbers) < 4:
        raise HarnessInvariantError(
            "projectile workload needs four demons and four lobbers"
        )
    for shot_slot in (*SLOT_DEMON_SHOTS, *SLOT_LOBBER_SHOTS):
        state.mobs.unlink_and_clear(shot_slot)
    for direction, (source, shot_slot) in zip(
        (2, 0, 4, 6), zip(demons[:4], SLOT_DEMON_SHOTS, strict=True), strict=True,
    ):
        monster_create_shot(state, source, direction, shot_slot)
    for direction, (source, shot_slot) in zip(
        (1, 3, 7, 5), zip(lobbers[:4], SLOT_LOBBER_SHOTS, strict=True), strict=True,
    ):
        monster_create_shot(state, source, direction, shot_slot)


class HarnessInvariantError(RuntimeError):
    """A host workload observed an internally inconsistent modeled state."""


def validate_runtime_invariants(
    state: GameState, *, workload: str, frame: int,
) -> None:
    """Fail immediately if the MOB chain or its SLIP bookmarks are corrupt."""
    mobs = state.mobs
    chain: list[int] = []
    seen: set[int] = set()
    slot = mobs.depth_list_head
    previous = NULL_SLOT

    while slot != NULL_SLOT:
        if not 0 < slot < NUM_MOB_SLOTS:
            raise HarnessInvariantError(
                f"{workload} frame {frame}: invalid MOB chain slot {slot}"
            )
        if slot in seen:
            raise HarnessInvariantError(
                f"{workload} frame {frame}: duplicate MOB chain slot {slot}"
            )
        if mobs.prev_slot(slot) != previous:
            raise HarnessInvariantError(
                f"{workload} frame {frame}: MOB {slot} previous link "
                f"{mobs.prev_slot(slot)} != {previous}"
            )
        seen.add(slot)
        chain.append(slot)
        previous = slot
        slot = mobs.next_slot(slot)

    expected_slips = [NULL_SLOT] * NUM_SLIP_BANDS
    marked = 0
    for slot in chain:
        band = mobs.band_of(slot)
        while marked <= band:
            expected_slips[marked] = slot
            marked += 1
        if marked >= NUM_SLIP_BANDS:
            break

    for band, (actual, expected) in enumerate(
        zip(mobs.slip_heads, expected_slips, strict=True)
    ):
        if actual not in seen and actual != NULL_SLOT:
            raise HarnessInvariantError(
                f"{workload} frame {frame}: SLIP {band} points outside the MOB chain "
                f"to {actual}"
            )
        if actual != expected:
            raise HarnessInvariantError(
                f"{workload} frame {frame}: SLIP {band} points to {actual}, "
                f"expected {expected}"
            )
