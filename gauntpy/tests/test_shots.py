"""WP-7 tests: shots and hit resolution.

Acceptance criteria (PLAN §6, WP-7 brief):
  1. Monster dies after the documented number of hits at each tier.
     Ghost (base=4): takes 4 hits of damage 1 each.
  2. Supershot pierces non-Death/IT monsters (resolve_shot_hit returns 0).
  3. Supershot does NOT pierce Death (returns -1, shot consumed).
  4. Movable wall dissolves at exactly hit 25.
  5. death_hits increments for every player shot (shooter_id 0-3).
  6. death_damage_counter: supershot adds 25; when counter > 200,
     Death MOB is dismissed and counter is cleared.
  7. Score multipliers: ghost class 10×, grunt class 5×.

All tests build GameState by hand and call resolve_shot_hit directly;
motion/animation internals are not tested here.
"""

from __future__ import annotations

import pytest

from gauntpy.constants import Character, MazeObjIds, PlayerPower, PlayerStatus
from gauntpy.coords import hpos_x, native_v, vpos_y
from gauntpy.state import GameState, Player
from gauntpy.subsystems import shots
from gauntpy.subsystems.shots import (
    _WALL_MOVE_DISSOLVE,
    main_handle_shots,
    resolve_shot_hit,
    shot_impact_spawn,
    shot_mob_collision,
    shot_reflect_calc,
    tport_cycle_start,
    wall_crumble,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_state() -> GameState:
    """Fresh GameState in normal gameplay mode with player 0 alive."""
    from gauntpy.constants import GameMode
    state = GameState(game_mode=GameMode.NORMAL)
    p = state.players[0]
    p.status = int(PlayerStatus.ALIVE_HERE)
    p.character = Character.WARRIOR
    p.health = 500
    p.bonusmult = 1
    p.supershot = 0
    return state


def _place_monster(state: GameState, slot: int,
                   obj_type: MazeObjIds, health_nibble: int) -> None:
    """Insert a monster MOB at ``slot`` with the given obj_type and health nibble.

    health_nibble occupies the low 4 bits of hpos (the palette field).

    Uses x=4 (= 0x004 → hpos = 0x100) to avoid accidentally setting
    hpos bit 12 (the sorcerer blink flag), which would fire when bit 6
    of x is 1 (x ≥ 64 and x < 128, e.g. x=100 = 0x64).
    """
    # link encodes obj_type in upper 6 bits; leave chain bits = 0.
    state.mobs.link[slot] = (int(obj_type) << 10) & 0xFFFF
    # hpos: x=4 occupies bits 15-7; palette = health_nibble.
    state.mobs.hpos[slot] = ((4 & 0x1FF) << 7) | (health_nibble & 0xF)
    state.mobs.vpos[slot] = native_v(4 & 0x1FF) << 7
    state.mobs.picture[slot] = 1   # non-zero = active
    # Insert into the depth chain so unlink_and_clear works cleanly.
    state.mobs.insert(slot)


def _place_wall(state: GameState, slot: int) -> None:
    """Insert a WALL_MOVABLE MOB at ``slot``."""
    state.mobs.link[slot] = (int(MazeObjIds.WALL_MOVABLE) << 10) & 0xFFFF
    state.mobs.hpos[slot] = (100 << 7)
    state.mobs.vpos[slot] = (native_v(100) << 7)
    state.mobs.picture[slot] = 1
    state.mobs.insert(slot)


# =============================================================================
# 1. Monster dies after correct hits
# =============================================================================

class TestMonsterKill:
    def test_ghost_dies_after_3_hits_damage_1(self):
        """Ghost spawned at base=4 dies after 3 damage-1 hits (§26 window).

        The live window is [base-2, base] = [2, 4]; the nibble leaves it below
        base-2 on the third hit (4 → 3 → 2 → 1 < 2 = dead).
        """
        state = _make_state()
        state.players[0].character = Character.ELF   # Elf: damage=1
        SLOT = 50
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=4)

        # First two hits: ghost survives (nibble 4→3→2, both inside [2,4]).
        for hit in range(2):
            result = resolve_shot_hit(state, SLOT, 0)
            assert result == -1, f"hit {hit+1}: shot should be consumed"
            assert state.mobs.picture[SLOT] != 0, \
                f"hit {hit+1}: ghost should still be alive"

        # Third hit: nibble 2 → 1, below base-2 → dead.
        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1
        assert state.mobs.picture[SLOT] == 0, "ghost should be dead after 3 hits"

    def test_demon_health_nibble_decrements(self):
        """Demon (base=8) survives when health > 0 after damage."""
        state = _make_state()
        state.players[0].character = Character.ELF   # Elf: damage=1
        SLOT = 51
        _place_monster(state, SLOT, MazeObjIds.MONST_DEMON, health_nibble=8)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1
        assert state.mobs.picture[SLOT] != 0     # still alive
        new_health = state.mobs.hpos[SLOT] & 0xF
        assert new_health == 7, "demon health should be 8-1=7 (Elf damage=1)"

    def test_grunt_dies_after_3_hits_damage_1(self):
        """Grunt (base=4, same window as ghost) dies after 3 damage-1 hits."""
        state = _make_state()
        state.players[0].character = Character.ELF   # Elf: damage=1
        SLOT = 52
        _place_monster(state, SLOT, MazeObjIds.MONST_GRUNT, health_nibble=4)

        for _ in range(2):
            resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[SLOT] != 0, "grunt still alive after 2 hits"

        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[SLOT] == 0, "grunt dead after 3 hits"


# =============================================================================
# 2. Supershot pierces non-Death monsters
# =============================================================================

class TestSupershot:
    def _supershot_player(self, state: GameState, player_index: int = 0) -> None:
        state.players[player_index].supershot = 1

    def test_supershot_pierces_ghost(self):
        """Supershot returns 0 (survives) against a non-Death monster."""
        state = _make_state()
        self._supershot_player(state)
        SLOT = 60
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=4)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == 0, "supershot should return 0 (pierce) against ghost"

    def test_supershot_kills_and_pierces_ghost(self):
        """Supershot kills the ghost (health≤0) AND the shot still survives."""
        state = _make_state()
        self._supershot_player(state)
        SLOT = 61
        # Health=1 so supershot (damage=3) kills it.
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == 0, "supershot pierces even after killing ghost"
        assert state.mobs.picture[SLOT] == 0, "ghost should be killed"

    def test_supershot_pierces_demon(self):
        """Supershot always pierces non-Death/IT monsters."""
        state = _make_state()
        self._supershot_player(state)
        SLOT = 62
        _place_monster(state, SLOT, MazeObjIds.MONST_DEMON, health_nibble=8)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == 0

    def test_supershot_pierces_sorcerer_even_when_blinking(self):
        """Supershot ignores the sorcerer's phased-out flag (hpos bit 4)."""
        state = _make_state()
        self._supershot_player(state)
        SLOT = 63
        _place_monster(state, SLOT, MazeObjIds.MONST_SORC, health_nibble=0xB)
        # Phased-out flag: hpos bit 4 = 0x0010 (0x4BB92).
        state.mobs.hpos[SLOT] |= 0x0010

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == 0, "supershot pierces even a blinking sorcerer"


# =============================================================================
# 3. Supershot blocked by Death
# =============================================================================

class TestSuperShotDeath:
    def test_supershot_does_not_pierce_death(self):
        """Supershot is consumed (returns -1) when hitting Death.  §26."""
        state = _make_state()
        state.players[0].supershot = 1
        SLOT = 70
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1, "supershot should be consumed by Death"

    def test_supershot_does_not_pierce_it(self):
        """Supershot is consumed (returns -1) when hitting IT.  §26."""
        state = _make_state()
        state.players[0].supershot = 1
        SLOT = 71
        _place_monster(state, SLOT, MazeObjIds.MONST_IT, health_nibble=0)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1, "supershot should be consumed by IT"

    def test_regular_shot_also_consumed_by_death(self):
        """A regular player shot is also consumed by Death."""
        state = _make_state()
        SLOT = 72
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1


# =============================================================================
# 4. Movable wall dissolves at hit 25
# =============================================================================

class TestMovableWall:
    def test_wall_dissolves_at_25_hits(self):
        """Movable wall is cleared after exactly 25 player-shot hits.  §26."""
        state = _make_state()
        SLOT = 80
        _place_wall(state, SLOT)

        # Hits 1-24: wall survives
        for i in range(24):
            result = resolve_shot_hit(state, SLOT, 0)
            assert result == -1, f"hit {i+1}: shot consumed"
            assert state.mobs.picture[SLOT] != 0, \
                f"hit {i+1}: wall should still exist"

        # Hit 25: wall dissolves
        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1
        assert state.mobs.picture[SLOT] == 0, \
            "wall should dissolve on the 25th hit"

    def test_wall_hit_accumulates(self):
        """Accumulated hit count grows by 0x400 per hit."""
        state = _make_state()
        SLOT = 81
        _place_wall(state, SLOT)

        resolve_shot_hit(state, SLOT, 0)
        assert state.movable_wall_hits.get(SLOT, 0) == 0x400

        resolve_shot_hit(state, SLOT, 0)
        assert state.movable_wall_hits.get(SLOT, 0) == 0x800

    def test_monster_shot_does_not_move_wall(self):
        """Monster shots (shooter_id ≥ 4) do not accumulate on movable walls."""
        state = _make_state()
        SLOT = 82
        _place_wall(state, SLOT)

        resolve_shot_hit(state, SLOT, 5)    # shooter_id=5 = monster shot
        assert state.movable_wall_hits.get(SLOT, 0) == 0
        assert state.mobs.picture[SLOT] != 0


class TestEffectSpawning:
    def test_kill_spawns_player_impact_in_first_free_channel(self):
        state = _make_state()
        target = 90
        _place_monster(
            state, target, MazeObjIds.MONST_GHOST, health_nibble=1,
        )

        resolve_shot_hit(state, target, 0)

        assert state.mobs.picture[0x0D] == 0x0EFC
        assert state.mob_effect_anim_counter[0] == 0

    def test_impact_preserves_full_pool_transporter_channel(self):
        state = _make_state()
        target = 90
        state.mobs.hpos[target] = 100 << 7
        state.mobs.vpos[target] = native_v(100) << 7
        for channel, slot in enumerate(range(0x0D, 0x11)):
            state.mobs.picture[slot] = 0x0924
            state.mob_effect_anim_counter[channel] = 0xFF

        shot_impact_spawn(state, target, 1)

        assert all(
            state.mobs.picture[slot] == 0x0924
            for slot in range(0x0D, 0x11)
        )

    def test_transporter_dissolve_seeds_rom_position_and_counter(self):
        state = _make_state()
        source = 91
        state.mobs.hpos[source] = (123 << 7) | 0x4F
        state.mobs.vpos[source] = (77 << 7) | 0x3F

        tport_cycle_start(state, source, 2)

        assert state.mobs.picture[0x0D] == 0x0924
        assert state.mobs.hpos[0x0D] == (
            (state.mobs.hpos[source] & 0xFF80) + 1
        )
        assert state.mobs.vpos[0x0D] == (
            (state.mobs.vpos[source] & 0xFF80) + 0x12
        )
        assert state.mob_effect_anim_counter[0] == 0xFF


# =============================================================================
# 5. death_hits increments on player shots
# =============================================================================

class TestDeathHits:
    def test_death_hits_only_counts_death_mob_hits(self):
        """``death_hits`` (0x904A5C) is a Death counter, not a shot counter.

        The ROM's only increment inside ``resolve_shot_hit`` is at 0x4BC18,
        inside the ``MONST_DEATH`` dispatch case; §26's "every player shot
        increments the separate global death_hits" means "every player shot
        *that reaches Death*".  ROM wins.
        """
        state = _make_state()
        assert state.death_hits == 0

        # Generic playfield wall (target >= 0x400): no Death involved.
        resolve_shot_hit(state, 0x400, 0)
        assert state.death_hits == 0

    def test_death_hits_increments_for_all_four_player_slots(self):
        """Each of the four player shooters increments the shared counter."""
        state = _make_state()
        for player_index in range(4):
            state.players[player_index].status = int(PlayerStatus.ALIVE_HERE)

        for player_index in range(4):
            slot = 200 + player_index
            _place_monster(state, slot, MazeObjIds.MONST_DEATH, health_nibble=0)
            resolve_shot_hit(state, slot, player_index)
        assert state.death_hits == 4

    def test_monster_shot_does_not_increment_death_hits(self):
        """Monster shots (shooter_id >= 4) do not increment death_hits.  §26."""
        state = _make_state()
        SLOT = 93
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)
        resolve_shot_hit(state, SLOT, 5)   # monster shot
        assert state.death_hits == 0

    def test_death_hits_does_not_increment_on_ghost_hit(self):
        """A monster that is not Death leaves death_hits alone (0x4BC18)."""
        state = _make_state()
        SLOT = 90
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=4)

        resolve_shot_hit(state, SLOT, 0)
        assert state.death_hits == 0

    def test_death_hits_increments_on_death_mob_hit(self):
        """death_hits increments when the target is the Death MOB itself."""
        state = _make_state()
        SLOT = 91
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)

        resolve_shot_hit(state, SLOT, 0)
        assert state.death_hits == 1


# =============================================================================
# 6. death_damage_counter: supershot adds 25, counter > 200 clears Death MOB
# =============================================================================

class TestDeathDamageAccumulate:
    def test_supershot_adds_25_to_counter(self):
        """A player supershot increments death_damage_counter by 25.  §3.6."""
        state = _make_state()
        state.players[0].supershot = 1
        SLOT = 100
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)

        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].death_damage_counter == 25

    def test_regular_shot_does_not_add_to_counter(self):
        """An ordinary player shot does NOT add to death_damage_counter.  §3.6."""
        state = _make_state()
        state.players[0].supershot = 0
        SLOT = 101
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)

        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].death_damage_counter == 0

    def test_ninth_supershot_dismisses_death(self):
        """Nine supershots dismiss Death (8 × 25 = 200, not > 200; 9 × 25 = 225 > 200).  §3.6."""
        state = _make_state()
        state.players[0].supershot = 1
        SLOT = 102
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)

        # Shots 1-8: counter reaches 200, Death MOB still present.
        for i in range(8):
            resolve_shot_hit(state, SLOT, 0)
            assert state.players[0].death_damage_counter == (i + 1) * 25, \
                f"after shot {i+1}: counter should be {(i+1)*25}"
            assert state.mobs.picture[SLOT] != 0, \
                f"after shot {i+1}: Death should still be present"

        # Shot 9: counter reaches 225 > 200 → Death dismissed, counter reset.
        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].death_damage_counter == 0, \
            "counter should be reset after Death is dismissed"
        assert state.mobs.picture[SLOT] == 0, \
            "Death MOB should be cleared after 9 supershots"

    def test_counter_is_per_player(self):
        """Each player has an independent death_damage_counter.  §3.6."""
        state = _make_state()
        state.players[0].supershot = 1
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].supershot = 0

        SLOT = 103
        _place_monster(state, SLOT, MazeObjIds.MONST_DEATH, health_nibble=0)

        # Player 0 shoots (supershot): counter for player 0 increases.
        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].death_damage_counter == 25
        assert state.players[1].death_damage_counter == 0    # not affected


# =============================================================================
# 7. Score multipliers: ghost class 10×, grunt class 5×
# =============================================================================

class TestScoreMultipliers:
    def test_ghost_kill_awards_10x_score(self):
        """Killing a ghost (class multiplier 10) scores damage × 10 × bonusmult.  §26."""
        state = _make_state()
        player = state.players[0]
        player.bonusmult = 1
        assert player.score == 0

        SLOT = 110
        # health=1 so one Warrior hit (damage 2... wait, Warrior=2 not 1).
        # Use health=2 so one Warrior shot (damage=2) kills it: 2-2=0 ≤ 0.
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=2)

        resolve_shot_hit(state, SLOT, 0)    # player 0 = Warrior, damage=2
        assert state.mobs.picture[SLOT] == 0, "ghost should be dead"
        # Score = damage × ghost_mult × bonusmult = 2 × 10 × 1 = 20
        assert player.score == 20, f"expected 20, got {player.score}"

    def test_grunt_kill_awards_5x_score(self):
        """Killing a grunt (class multiplier 5) scores damage × 5 × bonusmult.  §26."""
        state = _make_state()
        player = state.players[0]
        player.bonusmult = 1

        SLOT = 111
        _place_monster(state, SLOT, MazeObjIds.MONST_GRUNT, health_nibble=2)

        resolve_shot_hit(state, SLOT, 0)    # Warrior damage=2, kills grunt at health=2
        assert state.mobs.picture[SLOT] == 0, "grunt should be dead"
        # Score = 2 × 5 × 1 = 10
        assert player.score == 10, f"expected 10, got {player.score}"

    def test_ghost_vs_grunt_ratio_is_2x(self):
        """Ghost scores exactly twice as much as grunt for the same damage.  §26."""
        state_g = _make_state()
        state_r = _make_state()

        SLOT = 115
        _place_monster(state_g, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)
        _place_monster(state_r, SLOT, MazeObjIds.MONST_GRUNT, health_nibble=1)

        # Use Elf (damage=1) to avoid confusion with Warrior (damage=2).
        state_g.players[0].character = Character.ELF
        state_r.players[0].character = Character.ELF

        resolve_shot_hit(state_g, SLOT, 0)   # Elf hits ghost: 1 × 10 = 10
        resolve_shot_hit(state_r, SLOT, 0)   # Elf hits grunt: 1 × 5 = 5

        assert state_g.players[0].score == 10
        assert state_r.players[0].score == 5
        assert state_g.players[0].score == 2 * state_r.players[0].score

    def test_score_respects_bonusmult(self):
        """Score is multiplied by player.bonusmult (the bonus multiplier).  §26."""
        state = _make_state()
        player = state.players[0]
        player.character = Character.ELF    # damage=1, clean numbers
        player.bonusmult = 3               # 3× bonus

        SLOT = 116
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)

        resolve_shot_hit(state, SLOT, 0)
        # Score = 1 × 10 × 3 = 30
        assert player.score == 30

    def test_monster_shot_does_not_award_score(self):
        """Monster shots (shooter_id ≥ 4) do not award score to any player.  §26."""
        state = _make_state()
        SLOT = 117
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)

        # Monster shot (shooter_id=5)
        resolve_shot_hit(state, SLOT, 5)
        assert state.mobs.picture[SLOT] == 0, "ghost killed by monster shot"
        for p in state.players:
            assert p.score == 0, "no score for monster shot"


# =============================================================================
# Additional: sorcerer blinking immunity
# =============================================================================

class TestSorcererImmunity:
    def test_regular_shot_passes_through_blinking_sorcerer(self):
        """A non-supershot passes through a phased-out sorcerer (returns 0).

        The flag is hpos **bit 4** (0x0010), tested by ``btst #4`` on the low
        byte of the hpos word at 0x4BB92 -- not bit 12 as §26's prose says.
        ROM wins.
        """
        state = _make_state()
        state.players[0].supershot = 0
        SLOT = 120
        _place_monster(state, SLOT, MazeObjIds.MONST_SORC, health_nibble=0xB)
        state.mobs.hpos[SLOT] |= 0x0010    # set the phased-out bit

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == 0, "regular shot should pass through a phased sorcerer"
        # Sorcerer is unharmed
        assert state.mobs.hpos[SLOT] & 0xF == 0xB

    def test_regular_shot_hits_non_blinking_sorcerer(self):
        """A non-blinking sorcerer is hit normally by a regular shot."""
        state = _make_state()
        state.players[0].supershot = 0
        state.players[0].character = Character.ELF  # damage=1 for clean nibble check
        SLOT = 121
        _place_monster(state, SLOT, MazeObjIds.MONST_SORC, health_nibble=0xB)
        assert state.mobs.hpos[SLOT] & 0x0010 == 0, "_place_monster must not set the phase bit"

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1, "shot consumed by non-blinking sorcerer"
        assert state.mobs.hpos[SLOT] & 0xF == 0xA, "health decremented from 0xB to 0xA"


# =============================================================================
# Additional: generator tiers
# =============================================================================

class TestGenerators:
    def test_tier1_generator_dies_to_any_hit(self):
        """A tier-1 generator is destroyed by any hit, regardless of damage.  §26."""
        state = _make_state()
        SLOT = 130
        # GEN_GHOST1 = 28 → tier ((28-28)%3)+1 = 1
        state.mobs.link[SLOT] = (int(MazeObjIds.GEN_GHOST1) << 10) & 0xFFFF
        state.mobs.hpos[SLOT] = (100 << 7)
        state.mobs.vpos[SLOT] = (native_v(100) << 7)
        state.mobs.picture[SLOT] = 1
        state.mobs.insert(SLOT)

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1
        assert state.mobs.picture[SLOT] == 0, "tier-1 generator should be destroyed"

    def test_tier3_generator_degrades_on_damage_1(self):
        """A tier-3 generator degrades (not killed) by damage=1.  §26."""
        state = _make_state()
        SLOT = 131
        # GEN_GHOST3 = 30 → tier ((30-28)%3)+1 = 3
        state.mobs.link[SLOT] = (int(MazeObjIds.GEN_GHOST3) << 10) & 0xFFFF
        state.mobs.hpos[SLOT] = (100 << 7)
        state.mobs.vpos[SLOT] = (native_v(100) << 7)
        state.mobs.picture[SLOT] = 1
        state.mobs.insert(SLOT)

        # Player 0 is Warrior (damage=2), use Elf (damage=1) so tier 3 degrades.
        state.players[0].character = Character.ELF

        result = resolve_shot_hit(state, SLOT, 0)
        assert result == -1
        assert state.mobs.picture[SLOT] != 0, "tier-3 generator should NOT be killed by 1 damage"
        # obj_type should have dropped by 1 (from GEN_GHOST3=30 to GEN_GHOST2=29)
        new_type = state.mobs.obj_type(SLOT)
        assert new_type == int(MazeObjIds.GEN_GHOST2), \
            f"expected GEN_GHOST2={int(MazeObjIds.GEN_GHOST2)}, got {new_type}"

    def test_generator_kill_scores_at_the_generator_multiplier(self):
        """0x4BCB0 loads D5 = 10 for every generator tier, not the grunt 5."""
        state = _make_state()
        SLOT = 132
        state.mobs.link[SLOT] = (int(MazeObjIds.GEN_GRUNT1) << 10) & 0xFFFF
        state.mobs.hpos[SLOT] = (100 << 7)
        state.mobs.vpos[SLOT] = (native_v(100) << 7)
        state.mobs.picture[SLOT] = 1
        state.mobs.insert(SLOT)
        state.players[0].character = Character.ELF   # damage 1

        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].score == 1 * 10

    def test_generator_kill_resets_the_escape_timer(self):
        state = _make_state()
        SLOT = 133
        state.mobs.link[SLOT] = (int(MazeObjIds.GEN_SORC1) << 10) & 0xFFFF
        state.mobs.hpos[SLOT] = (100 << 7)
        state.mobs.vpos[SLOT] = (native_v(100) << 7)
        state.mobs.picture[SLOT] = 1
        state.mobs.insert(SLOT)
        state.escape_timer = 5000

        resolve_shot_hit(state, SLOT, 0)
        assert state.escape_timer == 0


# =============================================================================
# monstshot_damage_tbl -- the exact row formula (0x4B1AC-0x4B238)
# =============================================================================

class _FixedRandom:
    """Deterministic stand-in for ``GameRandom`` with a scripted draw list."""

    def __init__(self, values=()):
        self.values = list(values)
        self.draws = []
        self.seed = 0

    def getrandom(self, bound: int) -> int:
        self.draws.append(bound)
        return self.values.pop(0) if self.values else 0

    random_word = getrandom


class TestPlayerShotStatTables:
    """0x4AFA6 and 0x47846 keep shot power and shot speed independent."""

    def test_damage_tables_and_selectors_match_all_character_columns(self):
        assert shots._SHOT_DAMAGE_BASE_TBL == [
            2, 1, 1, 1,
            1, 1, 1, 1,
            2, 2, 2, 2,
        ]
        assert shots._SHOT_DAMAGE_RAND_TBL == [
            0, 0, 1, 0,
            0, 0, 0, 0,
            1, 0, 0, 0,
        ]
        for powered, expected in (
            (False, (2, 1, 2, 1)),
            (True, (3, 2, 2, 2)),
        ):
            for character, damage in enumerate(expected):
                state = _make_state()
                state.players[0].character = character
                state.players[0].powers = (
                    int(PlayerPower.SHOTPOWER) if powered else 0
                )
                state.rng = _FixedRandom([1])
                assert shots._shot_damage(state, 0) == damage

    def test_velocity_tables_use_shot_speed_not_shot_power(self):
        base_right = (0x180, 0x200, 0x200, 0x280)
        powered_right = (0x200, 0x280, 0x280, 0x380)
        for character in range(4):
            state = _make_state()
            state.players[0].character = character
            assert shots.shot_velocity(state, 0, 2)[0] == base_right[character]

            state.players[0].powers = int(PlayerPower.SHOTPOWER)
            assert shots.shot_velocity(state, 0, 2)[0] == base_right[character]

            state.players[0].powers = int(PlayerPower.SHOTSPEED)
            assert shots.shot_velocity(state, 0, 2)[0] == powered_right[character]


def _place_player_mob(state: GameState, slot: int, player_index: int,
                      x: int = 160, y: int = 160) -> None:
    """A player MOB: hpos palette >= 0xC is what marks the slot as a player."""
    state.mobs.link[slot] = 0
    state.mobs.hpos[slot] = ((x & 0x1FF) << 7) | 0x0C
    state.mobs.vpos[slot] = native_v(y & 0x1FF) << 7
    state.mobs.picture[slot] = 1
    state.mobs.set_state(slot, player_index)
    state.mobs.insert(slot)
    state.players[player_index].mob_slot = slot


def _arm_monster_shot(state: GameState, shooter_id: int, tier: int = 0) -> None:
    """Give a monster channel a live shot MOB carrying ``tier`` in hpos 4-5."""
    slot = shooter_id + 1
    state.mobs.picture[slot] = 1
    state.mobs.hpos[slot] = (160 << 7) | (tier & 0x30)
    state.mobs.vpos[slot] = native_v(160) << 7


class TestMonsterShotDamageIndex:
    """`monstshot_damage_tbl` row = character + 4*armour + tier (0x4B1AC)."""

    def _hit(self, character, armour, tier, shooter_id=4):
        state = _make_state()
        victim = state.players[1]
        victim.status = int(PlayerStatus.ALIVE_HERE)
        victim.character = character
        victim.health = 1000
        victim.powers = 0x02 if armour else 0
        _place_player_mob(state, 300, 1)
        _arm_monster_shot(state, shooter_id, tier)
        resolve_shot_hit(state, 300, shooter_id)
        return 1000 - victim.health

    def test_ordinary_monster_shot_row_zero(self):
        """Tier 0, unarmoured, channel < 8: row 0 = 4/3/5/4."""
        assert self._hit(Character.WARRIOR, False, 0) == 4
        assert self._hit(Character.VALKYRIE, False, 0) == 3
        assert self._hit(Character.WIZARD, False, 0) == 5
        assert self._hit(Character.ELF, False, 0) == 4

    def test_armour_moves_four_columns_along(self):
        """+4 selects row 1 = 3/2/4/3."""
        assert self._hit(Character.WARRIOR, True, 0) == 3
        assert self._hit(Character.WIZARD, True, 0) == 4

    def test_special_channel_adds_eight(self):
        """A channel >= 8 with no tier bits adds 8: row 2 = 3/3/3/3."""
        assert self._hit(Character.WARRIOR, False, 0, shooter_id=8) == 3
        assert self._hit(Character.WIZARD, False, 0, shooter_id=8) == 3
        assert self._hit(Character.WIZARD, True, 0, shooter_id=8) == 2

    def test_tier_bits_pick_the_strong_rows(self):
        """hpos 0x10/0x20/0x30 add 0x10/0x18/0x20 -- and 0x10 hurts most."""
        assert self._hit(Character.WIZARD, False, 0x10) == 15
        assert self._hit(Character.WIZARD, False, 0x20) == 10
        assert self._hit(Character.WIZARD, False, 0x30) == 10
        assert self._hit(Character.VALKYRIE, True, 0x10) == 7

    def test_tier_bits_beat_the_channel_addend(self):
        """A tiered shot from channel >= 8 uses the tier, never the +8."""
        assert self._hit(Character.WARRIOR, False, 0x10, shooter_id=9) == 12

    def test_damage_marks_the_health_panel_dirty(self):
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 301, 1)
        _arm_monster_shot(state, 4)
        resolve_shot_hit(state, 301, 4)
        assert state.health_dirty[1] == 1
        assert state.players[1].hurt_cooldown == 0x12

    def test_health_clamps_at_zero(self):
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 2
        _place_player_mob(state, 302, 1)
        _arm_monster_shot(state, 4)
        resolve_shot_hit(state, 302, 4)
        assert state.players[1].health == 0

    def test_collision_finds_the_players_migrated_record(self):
        state = _make_state()
        victim = state.players[1]
        victim.status = int(PlayerStatus.ALIVE_HERE)
        victim.health = 100
        # The hero's record migrates into the cell it stands in, so the probe
        # finds it as that cell's own occupant -- no port-side overlay.
        cell = (10 << 5) | 10
        _place_player_mob(state, cell, 1, x=160, y=160)
        _arm_monster_shot(state, 4)

        hit = shot_mob_collision(state, cell, 4)

        assert hit == cell
        resolve_shot_hit(state, hit, 4)
        assert victim.health < 100

    @pytest.mark.parametrize("victim_index", range(4))
    def test_monster_shot_damages_the_player_named_by_mob_state(
        self, victim_index,
    ):
        state = _make_state()
        for player in state.players:
            player.status = int(PlayerStatus.ALIVE_HERE)
            player.health = 100
        slot = 300 + victim_index
        _place_player_mob(state, slot, victim_index)
        _arm_monster_shot(state, 4)

        resolve_shot_hit(state, slot, 4)

        assert state.players[victim_index].health < 100
        assert all(
            player.health == 100
            for index, player in enumerate(state.players)
            if index != victim_index
        )


class TestAcidImmunity:
    def test_acid_slowed_player_ignores_monster_shots(self):
        """0x4B306: an acid-slowed victim takes no monster-shot damage."""
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        state.players[1].acid_timer = 30
        _place_player_mob(state, 303, 1)
        _arm_monster_shot(state, 4)
        result = resolve_shot_hit(state, 303, 4)
        assert state.players[1].health == 100
        assert result == -1

    def test_acid_slowed_victim_loses_trick_eight(self):
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].acid_timer = 30
        state.secret_trick_id = 8
        state.secret_tricks_flags[1] = 3
        _place_player_mob(state, 304, 1)
        _arm_monster_shot(state, 4)
        resolve_shot_hit(state, 304, 4)
        assert state.secret_tricks_flags[1] == 0

    def test_acid_puddle_type_lets_shots_pass(self):
        """MONST_ACID (0x19) dispatches to the no-effect leaf at 0x4B890."""
        state = _make_state()
        SLOT = 305
        _place_monster(state, SLOT, MazeObjIds.MONST_ACID, health_nibble=1)
        assert resolve_shot_hit(state, SLOT, 0) == 0
        assert state.mobs.picture[SLOT] != 0


class TestPlayerVersusPlayer:
    def test_shotstun_flag_stuns_and_clears_the_fighting_dir(self):
        state = _make_state()
        state.level_flags_4 = 0x01           # LFLAG4 bit 0: ShotStun
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        state.player_fighting_dir[1] = 5
        _place_player_mob(state, 310, 1)
        resolve_shot_hit(state, 310, 0)
        assert state.players[1].stundelay == 0x28
        assert state.players[1].hurt_cooldown == 0x12
        assert state.player_fighting_dir[1] == 0
        assert state.players[1].health == 100      # stun only, no damage

    def test_stun_clamps_at_0x5a(self):
        state = _make_state()
        state.level_flags_4 = 0x01
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].stundelay = 0x50
        _place_player_mob(state, 311, 1)
        resolve_shot_hit(state, 311, 0)
        assert state.players[1].stundelay == 0x5A

    def test_shothurt_flag_costs_two_health(self):
        state = _make_state()
        state.level_flags_4 = 0x02           # LFLAG4 bit 1: ShotHurt
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 312, 1)
        resolve_shot_hit(state, 312, 0)
        assert state.players[1].health == 98
        assert state.health_dirty[1] == 1

    def test_supershot_costs_ten_even_without_lflag4(self):
        state = _make_state()
        state.level_flags_4 = 0
        state.players[0].supershot = 1
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 313, 1)
        resolve_shot_hit(state, 313, 0)
        assert state.players[1].health == 90

    def test_plain_shot_with_no_flags_does_nothing(self):
        state = _make_state()
        state.level_flags_4 = 0
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 314, 1)
        assert resolve_shot_hit(state, 314, 0) == -1
        assert state.players[1].health == 100

    def test_trick_0x11_credits_shooting_another_player(self):
        state = _make_state()
        state.secret_trick_id = 0x11
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        _place_player_mob(state, 315, 1)
        resolve_shot_hit(state, 315, 0)
        assert state.secret_tricks_flags[0] == 1


# =============================================================================
# Remaining resolve_shot_hit dispatch cases
# =============================================================================

def _place_typed(state: GameState, slot: int, obj_type, *,
                 picture: int = 1, x: int = 160, y: int = 160,
                 palette: int = 0) -> None:
    state.mobs.link[slot] = (int(obj_type) << 10) & 0xFFFF
    state.mobs.hpos[slot] = ((x & 0x1FF) << 7) | (palette & 0x0F)
    state.mobs.vpos[slot] = native_v(y & 0x1FF) << 7
    state.mobs.picture[slot] = picture
    state.mobs.insert(slot)


class TestDispatchLeaves:
    @pytest.mark.parametrize("obj_type", [
        MazeObjIds.TILE_STUN, MazeObjIds.TILE_TRAP1, MazeObjIds.TILE_TRAP3,
        MazeObjIds.EXIT, MazeObjIds.EXITTO6, MazeObjIds.KEY,
        MazeObjIds.POWER_INVIS, MazeObjIds.POWER_REFLECT,
        MazeObjIds.POWER_SUPERSHOT, MazeObjIds.TRANSPORTER,
    ])
    def test_pass_through_types_return_zero(self, obj_type):
        """0x4B890: the shot is unaffected and the object untouched."""
        state = _make_state()
        SLOT = 340
        _place_typed(state, SLOT, obj_type)
        assert resolve_shot_hit(state, SLOT, 0) == 0
        assert state.mobs.picture[SLOT] != 0

    def test_random_wall_consumes_the_shot(self):
        """WALL_RANDOM's table entry points straight at the 0x4BDB4 tail."""
        state = _make_state()
        SLOT = 341
        _place_typed(state, SLOT, MazeObjIds.WALL_RANDOM)
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.picture[SLOT] != 0     # the wall itself survives

    def test_regular_wall_consumes_the_shot(self):
        state = _make_state()
        SLOT = 342
        _place_typed(state, SLOT, MazeObjIds.WALL_REGULAR)
        state.mobs.picture[1] = 1                # a live shot in channel 0
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.picture[1] == 0

    def test_max_tier_shot_bores_through_a_wall(self):
        """0x4B51E: hpos bits 4-5 both set means walls do not stop it."""
        state = _make_state()
        SLOT = 343
        _place_typed(state, SLOT, MazeObjIds.WALL_REGULAR)
        state.mobs.picture[5] = 1
        state.mobs.hpos[5] = (160 << 7) | 0x30
        assert resolve_shot_hit(state, SLOT, 4) == 0

    def test_playfield_tile_code_takes_the_wall_path(self):
        """0x400-0x7FF has no MOB: the shot is still consumed, not ignored."""
        state = _make_state()
        state.mobs.picture[1] = 1
        assert resolve_shot_hit(state, 0x400 | 342, 0) == -1
        assert state.mobs.picture[1] == 0

    def test_it_is_phased_out_rather_than_damaged(self):
        """0x4BC48 folds the state field down 3 bits and sets hpos bit 4."""
        state = _make_state()
        SLOT = 344
        _place_typed(state, SLOT, MazeObjIds.MONST_IT, palette=8)
        state.mobs.state_link[SLOT] = 0xE000 | (state.mobs.state_link[SLOT] & 0x3FF)
        prev_link = state.mobs.state_link[SLOT] & 0x3FF

        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.hpos[SLOT] & 0x10, "IT should be phased out"
        assert state.mobs.state_link[SLOT] == (0x1C00 | prev_link)
        assert state.mobs.picture[SLOT] != 0, "IT is never removed by a shot"

    def test_it_second_hit_only_masks_the_state_field(self):
        state = _make_state()
        SLOT = 345
        _place_typed(state, SLOT, MazeObjIds.MONST_IT, palette=0x18 & 0x0F)
        state.mobs.hpos[SLOT] |= 0x10
        state.mobs.state_link[SLOT] = 0xFC00
        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.state_link[SLOT] == 0x1C00

    def test_supersorc_dies_to_one_ordinary_shot(self):
        """0x4BBD0: escape timer cleared, removed, and scored at 100x."""
        state = _make_state()
        SLOT = 346
        state.players[0].character = Character.ELF     # damage 1
        state.escape_timer = 900
        _place_typed(state, SLOT, MazeObjIds.MONST_SUPERSORC, palette=0x0B)
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.picture[SLOT] == 0
        assert state.escape_timer == 0
        assert state.players[0].score == 100

    def test_supersorc_phase_bit_turns_the_shot_aside(self):
        state = _make_state()
        SLOT = 347
        _place_typed(state, SLOT, MazeObjIds.MONST_SUPERSORC, palette=0x0B)
        state.mobs.hpos[SLOT] |= 0x10
        assert resolve_shot_hit(state, SLOT, 0) == 0
        assert state.mobs.picture[SLOT] != 0

    def test_treasure_ignores_an_ordinary_shot(self):
        state = _make_state()
        SLOT = 348
        _place_typed(state, SLOT, MazeObjIds.TREASURE, palette=1)
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.picture[SLOT] != 0

    def test_supershot_breaks_treasure_and_carries_on(self):
        state = _make_state()
        SLOT = 349
        state.players[0].supershot = 1
        state.escape_timer = 700
        _place_typed(state, SLOT, MazeObjIds.TREASURE, palette=1)
        assert resolve_shot_hit(state, SLOT, 0) == 0
        assert state.mobs.picture[SLOT] == 0
        assert state.escape_timer == 0

    def test_supershot_on_treasure_credits_challenge_0x5a(self):
        state = _make_state()
        SLOT = 350
        state.players[0].supershot = 1
        state.secret_trick_id = 0x5A
        _place_typed(state, SLOT, MazeObjIds.TREASURE, palette=1)
        resolve_shot_hit(state, SLOT, 0)
        assert state.secret_tricks_flags[0] == 1

    def test_invulnerable_food_needs_a_supershot(self):
        state = _make_state()
        SLOT = 351
        _place_typed(state, SLOT, MazeObjIds.FOOD_INVULN, palette=1)
        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[SLOT] != 0
        state.players[0].supershot = 1
        assert resolve_shot_hit(state, SLOT, 0) == 0
        assert state.mobs.picture[SLOT] == 0

    def test_destructible_food_breaks_and_speaks(self):
        """Once the first-encounter box is spent, the shooter speaks (0x4B994)."""
        state = _make_state()
        SLOT = 352
        state.dialog_first_encounter_flags |= 0x02   # box already seen
        state.rng = _FixedRandom([0, 0])     # getrandom(3)==0 then getrandom(5)==0
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=0x0963)
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.picture[SLOT] == 0
        assert 0x61 in state.sound_log

    def test_the_first_encounter_dialog_suppresses_the_speech(self):
        """0x4B964: a dialog with speech means the shooter stays quiet."""
        state = _make_state()
        SLOT = 357
        state.rng = _FixedRandom([0, 0])
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=0x0963)
        resolve_shot_hit(state, SLOT, 0)
        assert state.dialog_first_encounter_flags & 0x02, "the box was shown"
        assert 0x61 not in state.sound_log

    def test_the_character_speech_line_comes_from_0x596f6(self):
        state = _make_state()
        state.players[2].status = int(PlayerStatus.ALIVE_HERE)
        state.players[2].character = Character.WIZARD
        SLOT = 358
        state.dialog_first_encounter_flags |= 0x02
        # Wizard shots draw getrandom(2) for damage first (0x4AFF4).
        state.rng = _FixedRandom([0, 0, 1])  # damage, getrandom(3)==0, getrandom(5)!=0
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=0x0963)
        resolve_shot_hit(state, SLOT, 2)
        # index = character + shooter*4 = 2 + 8 = 10 -> 0xC7, then the suffix.
        assert 0xC7 in state.sound_log
        assert 0x9A in state.sound_log

    def test_shooting_slow_motion_food_starts_the_timer(self):
        state = _make_state()
        SLOT = 353
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=0x25ED)
        resolve_shot_hit(state, SLOT, 0)
        assert state.monster_slowmo_timer == 0x258
        assert 0x37 in state.sound_log

    def test_shooting_slow_motion_potion_starts_the_longer_timer(self):
        state = _make_state()
        SLOT = 354
        _place_typed(state, SLOT, MazeObjIds.POT_DESTRUCTABLE, picture=0x20FC)
        resolve_shot_hit(state, SLOT, 0)
        assert state.monster_slowmo_timer == 0x4B0
        assert 0x37 in state.sound_log
        assert state.mobs.picture[SLOT] == 0

    def test_trick_five_credits_shooting_the_food(self):
        state = _make_state()
        SLOT = 355
        state.secret_trick_id = 5
        state.rng = _FixedRandom([1])
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=0x0963)
        resolve_shot_hit(state, SLOT, 0)
        assert state.secret_tricks_flags[0] == 1

    def test_monster_shot_into_the_dragon_just_despawns(self):
        state = _make_state()
        SLOT = 356
        _place_typed(state, SLOT, MazeObjIds.MONST_DRAGON, palette=8)
        state.mobs.picture[5] = 1
        state.mobs.hpos[5] = 160 << 7
        assert resolve_shot_hit(state, SLOT, 4) == -1
        assert state.mobs.picture[5] == 0
        assert state.mobs.picture[SLOT] != 0, "the dragon is untouched"


class TestSecretWall:
    def _shoot_secret_wall(self, rolls, players=1):
        state = _make_state()
        state.level_players_active = players
        # pf_replace stamps a freshly randomized floor before the prize draw.
        state.rng = _FixedRandom([0, *rolls])
        SLOT = 360
        _place_typed(state, SLOT, MazeObjIds.WALL_SECRET)
        result = resolve_shot_hit(state, SLOT, 0)
        return state, SLOT, result

    def test_reveal_plays_sound_and_consumes_the_shot(self):
        state, slot, result = self._shoot_secret_wall([0xF])
        assert result == -1
        assert 0x30 in state.sound_log
        assert state.secret_need_hint == 1

    def test_roll_above_the_player_budget_spawns_nothing(self):
        # players*2 + 2 == 4, so a roll of 4 or more yields no prize.
        state, slot, _ = self._shoot_secret_wall([4])
        assert state.mobs.picture[slot] == 0
        assert state.mobs.obj_type(slot) == 0

    def test_low_roll_spawns_death(self):
        state, slot, _ = self._shoot_secret_wall([0])
        assert state.mobs.obj_type(slot) == int(MazeObjIds.MONST_DEATH)

    def test_roll_two_spawns_a_treasure_bag(self):
        state, slot, _ = self._shoot_secret_wall([2], players=4)
        assert state.mobs.obj_type(slot) == int(MazeObjIds.TREASURE_BAG)

    def test_roll_four_spawns_an_invulnerable_potion(self):
        state, slot, _ = self._shoot_secret_wall([4], players=4)
        assert state.mobs.obj_type(slot) == int(MazeObjIds.POT_INVULN)

    def test_roll_five_spawns_invulnerable_food(self):
        state, slot, _ = self._shoot_secret_wall([5], players=4)
        assert state.mobs.obj_type(slot) == int(MazeObjIds.FOOD_INVULN)

    def test_roll_six_spawns_a_hidden_potion_with_a_random_picture(self):
        state, slot, _ = self._shoot_secret_wall([6, 3], players=4)
        assert state.mobs.obj_type(slot) == int(MazeObjIds.HIDDENPOT)
        assert state.mobs.picture[slot] == 0xA728 + 3 * 4

    def test_trick_six_credits_the_shooter(self):
        state = _make_state()
        state.level_players_active = 4
        state.secret_trick_id = 6
        state.rng = _FixedRandom([0, 0xF, 0])
        SLOT = 361
        _place_typed(state, SLOT, MazeObjIds.WALL_SECRET)
        resolve_shot_hit(state, SLOT, 0)
        assert state.secret_tricks_flags[0] == 1


class TestDestructibleWall:
    def test_lflag2_bit7_destroys_on_the_first_hit(self):
        state = _make_state()
        state.level_flags_2 = 0x80
        SLOT = 370
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.picture[SLOT] == 0

    def test_crumble_takes_three_damage_points(self):
        state = _make_state()
        state.players[0].character = Character.ELF      # damage 1
        SLOT = 371
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        for _ in range(2):
            resolve_shot_hit(state, SLOT, 0)
            assert state.mobs.picture[SLOT] != 0
        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[SLOT] == 0

    def test_warrior_crumbles_it_in_two(self):
        state = _make_state()                            # Warrior: damage 2
        SLOT = 372
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[SLOT] != 0
        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[SLOT] == 0

    def test_supershot_carries_on_through(self):
        state = _make_state()
        state.players[0].supershot = 1
        SLOT = 373
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        assert resolve_shot_hit(state, SLOT, 0) == 0


class TestDoors:
    def test_door_ignores_a_shot_outside_its_box(self):
        state = _make_state()
        SLOT = 380
        _place_typed(state, SLOT, MazeObjIds.DOOR_HORIZ)
        state.mobs.set_state(SLOT, 0x08)          # state bits 0x2000
        state.shot_sep_h = state.shot_sep_v = 0
        state.shot_sep_h_abs = state.shot_sep_v_abs = 0x400
        assert resolve_shot_hit(state, SLOT, 0) == 0

    def test_door_reacts_to_a_shot_inside_its_box(self):
        state = _make_state()
        SLOT = 381
        _place_typed(state, SLOT, MazeObjIds.DOOR_VERT)
        state.mobs.state_link[SLOT] = (
            state.mobs.state_link[SLOT] & 0x3FF
        ) | 0x2000
        state.shot_sep_h = 0x0100
        state.shot_sep_h_abs = 0x0100
        state.shot_sep_v = 0
        state.shot_sep_v_abs = 0
        state.mobs.picture[1] = 1
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.mobs.picture[1] == 0


# =============================================================================
# shot_mob_collision -- exact hitbox geometry (0x40906 / 0x40A78)
# =============================================================================

def _arm_player_shot(state: GameState, shooter_id: int = 0,
                     x: int = 160, y: int = 160, tier: int = 0) -> int:
    slot = shooter_id + 1
    state.mobs.picture[slot] = 1
    state.mobs.hpos[slot] = ((x & 0x1FF) << 7) | (tier & 0x30)
    state.mobs.vpos[slot] = native_v(y & 0x1FF) << 7
    state.shot_direction[shooter_id] = 2      # heading right
    return slot


class TestShotCollision:
    def test_hits_a_monster_sharing_its_cell(self):
        state = _make_state()
        state.players[0].mob_slot = 0x3FF          # not the target
        _arm_player_shot(state)
        cell = (10 << 5) | 10                      # pixel (160, 160)
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (160 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, cell, 0) == cell

    def test_dragon_head_overlap_retains_the_rom_tag_and_takes_damage(self):
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state)
        cell = (10 << 5) | 10
        _place_monster(state, cell, MazeObjIds.MONST_DRAGON, health_nibble=8)
        state.mobs.hpos[cell] = (160 << 7) | 8
        state.mobs.vpos[cell] = native_v(160) << 7
        state.dragon_facing = 2
        state.dragon_head_hpos = 160 << 7
        state.dragon_head_vpos = native_v(160) << 7
        state.dragon_path_num = 0
        state.dragon_anim_ctr = 8
        state.dragon_state = 0

        target = shot_mob_collision(state, cell, 0)
        assert target == cell | 0x0800
        assert resolve_shot_hit(state, target, 0) == -1
        assert state.dragon_hits == 1

    def test_a_point_blank_sorcerer_is_the_cells_own_occupant(self):
        """S-61: the shooter's own record must never displace a real occupant.

        With the record migrating, a hero standing next door simply is not in
        this cell, so the sorcerer sharing it is the only candidate.
        """
        state = _make_state()
        hero_record = (4 << 5) | 4
        cell = (10 << 5) | 10
        player = state.players[0]
        player.mob_slot = hero_record
        player.status = PlayerStatus.ALIVE_HERE
        state.mobs.picture[hero_record] = 0x100
        state.mobs.hpos[hero_record] = (160 << 7) | 0x0C
        state.mobs.vpos[hero_record] = native_v(160) << 7
        _arm_player_shot(state)
        _place_monster(
            state, cell, MazeObjIds.MONST_SORC, health_nibble=0x0B,
        )
        state.mobs.hpos[cell] = (160 << 7) | 0x0B
        state.mobs.vpos[cell] = native_v(160) << 7

        assert shot_mob_collision(state, cell, 0) == cell

    def test_the_probed_cell_resolves_to_the_hero_standing_in_it(self):
        state = _make_state()
        cell = (10 << 5) | 10
        player = state.players[0]
        # Identity is location: the hero's record *is* the cell it occupies.
        player.mob_slot = cell
        player.status = PlayerStatus.ALIVE_HERE
        state.mobs.picture[cell] = 0x100
        state.mobs.hpos[cell] = (160 << 7) | 0x0C
        state.mobs.vpos[cell] = native_v(160) << 7
        state.mobs.picture[5] = 1
        state.mobs.hpos[5] = 160 << 7
        state.mobs.vpos[5] = native_v(160) << 7
        state.shot_direction[4] = 2

        assert shot_mob_collision(state, cell, 4) == cell

    def test_never_hits_its_own_shooter(self):
        """0x40AA6: active_mob_ids[shooter] is excluded from every probe."""
        state = _make_state()
        cell = (10 << 5) | 10
        state.players[0].mob_slot = cell
        _arm_player_shot(state)
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (160 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, cell, 0) == -1

    def test_a_reflected_shot_may_hit_its_shooter(self):
        """0x409BA: the self index is poisoned once reflect_count leaves 4."""
        state = _make_state()
        cell = (10 << 5) | 10
        state.players[0].mob_slot = cell
        state.reflect_count[0] = 3
        _arm_player_shot(state)
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (160 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, cell, 0) == cell

    def test_a_target_too_far_right_is_rejected(self):
        """The Warrior box is 0x2C0 wide with a +0x100 bias (0x40ABC)."""
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state)
        cell = (10 << 5) | 11                      # the first probe for dir 2
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (176 << 7) | 4     # 16 px right: outside
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, cell - 1, 0) == -1

    def test_the_probe_ring_reaches_the_next_cell(self):
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state, x=170)
        cell = (10 << 5) | 11
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (172 << 7) | 4     # 2 px right of the shot
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, (10 << 5) | 10, 0) == cell

    def test_empty_slots_are_skipped(self):
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state)
        assert shot_mob_collision(state, (10 << 5) | 10, 0) == -1

    def test_max_tier_shot_passes_through_death(self):
        """0x40B58: type 0x18 is one of the 0xFF entries."""
        state = _make_state()
        cell = (10 << 5) | 10
        state.mobs.picture[5] = 1
        state.mobs.hpos[5] = (160 << 7) | 0x30
        state.mobs.vpos[5] = native_v(160) << 7
        state.shot_direction[4] = 2
        _place_monster(state, cell, MazeObjIds.MONST_DEATH, health_nibble=0)
        state.mobs.hpos[cell] = 160 << 7
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, cell, 4) == -1

    def test_max_tier_shot_still_hits_a_ghost(self):
        state = _make_state()
        cell = (10 << 5) | 10
        state.mobs.picture[5] = 1
        state.mobs.hpos[5] = (160 << 7) | 0x30
        state.mobs.vpos[5] = native_v(160) << 7
        state.shot_direction[4] = 2
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (160 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, cell, 4) == cell

    def test_collision_publishes_the_separations_for_the_door_check(self):
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state)
        cell = (10 << 5) | 10
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (160 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        shot_mob_collision(state, cell, 0)
        assert state.shot_sep_h == 0x200      # the ROM's +0x200
        assert state.shot_sep_v == 0


# =============================================================================
# main_handle_shots -- motion, animation, lifetime and disposal
# =============================================================================

def _centre_camera(state: GameState, x: int = 160, y: int = 160) -> None:
    """Put the shot window over ``(x, y)`` so nothing is culled off-screen."""
    state.scroll_x = x + 8
    state.scroll_y = y - 0x68


class TestMainHandleShots:
    def _running_shot(self, character=Character.WARRIOR, powers=0,
                      shooter_id=0, tier=0, direction=2):
        state = _make_state()
        state.players[0].character = character
        state.players[0].powers = powers
        state.players[0].mob_slot = 0x3FF
        slot = _arm_player_shot(state, shooter_id, tier=tier)
        state.shot_direction[shooter_id] = direction
        state.mobs.insert(slot, depth_key=(10 << 5) | 10)
        state.shot_owner_mob[shooter_id] = 0x3FF
        _centre_camera(state)
        return state, slot

    def test_shot_timers_tick_down(self):
        state = _make_state()
        state.shot_timer_next = [3, 0, 5, 0, 0, 0, 0, 1]
        main_handle_shots(state)
        assert state.shot_timer_next == [2, 0, 4, 0, 0, 0, 0, 0]

    def test_warrior_shot_uses_its_own_velocity_row(self):
        state, slot = self._running_shot()
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 163   # ROM 0x180 >> 7

    def test_elf_shot_is_faster(self):
        state, slot = self._running_shot(character=Character.ELF)
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 165   # ROM 0x280 >> 7

    def test_shot_speed_selects_the_0x28_row_block(self):
        state, slot = self._running_shot(powers=0x08)
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 164   # ROM 0x200 >> 7

    def test_diagonals_are_slower_per_axis(self):
        state, slot = self._running_shot(direction=1)         # up-right
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 162    # ROM 0x100 >> 7
        assert vpos_y(state.mobs.vpos[slot]) == 158    # upward

    def test_direction_zero_moves_up_the_maze(self):
        state, slot = self._running_shot(direction=0)
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 160
        assert vpos_y(state.mobs.vpos[slot]) == 157

    def _monster_shot(self, tier, shooter_id=4):
        state = _make_state()
        slot = shooter_id + 1
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = (160 << 7) | (tier & 0x30)
        state.mobs.vpos[slot] = native_v(160) << 7
        state.shot_direction[shooter_id] = 2
        state.mobs.insert(slot, depth_key=(10 << 5) | 10)
        state.shot_owner_mob[shooter_id] = 0x3FF
        state.shot_anim_lifetime_counter[shooter_id] = 5
        _centre_camera(state)
        return state, slot

    def test_ordinary_monster_shot_uses_the_0x20_row(self):
        state, slot = self._monster_shot(0)
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 163    # ROM 0x180 >> 7

    def test_live_monster_channel_damages_the_hero_in_the_cell(self):
        state, slot = self._monster_shot(0)
        victim = state.players[1]
        victim.status = int(PlayerStatus.ALIVE_HERE)
        victim.health = 100
        _place_player_mob(state, (10 << 5) | 10, 1, x=160, y=160)

        main_handle_shots(state)

        assert victim.health < 100
        assert state.mobs.picture[slot] == 0

    def test_tier_two_monster_shot_uses_the_0x48_row(self):
        state, slot = self._monster_shot(0x20)
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 165    # ROM 0x280 >> 7

    def test_max_tier_monster_shot_only_moves_on_even_frames(self):
        state, slot = self._monster_shot(0x30)
        state.frame_counter = 1
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 160    # held still
        state.frame_counter = 2
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 162    # ROM 0x100 >> 7

    def test_animation_counter_reloads_from_the_rom_table(self):
        state, slot = self._running_shot()
        state.shot_anim_lifetime_counter[0] = 0
        main_handle_shots(state)                 # frame 0 is an eligible frame
        assert state.shot_anim_lifetime_counter[0] == 0x0F   # Warrior reload

    def test_animation_only_advances_on_the_channels_own_frames(self):
        state, slot = self._running_shot()
        state.shot_anim_lifetime_counter[0] = 5
        state.frame_counter = 1                  # (frame ^ 0) & 1 != 0
        main_handle_shots(state)
        assert state.shot_anim_lifetime_counter[0] == 5

    def test_picture_comes_from_the_projectile_table(self):
        state, slot = self._running_shot()
        state.shot_anim_lifetime_counter[0] = 4
        main_handle_shots(state)
        # index = (dir*2 + counter) & 0xF + character << 4 = (4 + 3) = 7
        assert state.mobs.picture[slot] == 0x1CBB

    def test_special_channel_expires_and_explodes(self):
        """Channels 8-11 use the counter as a lifetime (0x47814)."""
        state = _make_state()
        slot = 9
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = 160 << 7
        state.mobs.vpos[slot] = native_v(160) << 7
        state.shot_direction[8] = 2
        state.mobs.insert(slot, depth_key=(10 << 5) | 10)
        state.shot_owner_mob[8] = 0x3FF
        state.shot_anim_lifetime_counter[8] = 0
        state.frame_counter = 1                  # not this channel's anim frame
        _centre_camera(state)
        main_handle_shots(state)
        assert state.mobs.picture[slot] == 0
        assert state.mobs.picture[0x0D] != 0     # the impact effect

    def test_a_new_special_channel_gets_its_rom_lifetime(self):
        """The port's creators do not seed 0x904B02, so the loop does (0x5480E)."""
        state = _make_state()
        slot = 9
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = 160 << 7
        state.mobs.vpos[slot] = native_v(160) << 7
        state.shot_dx[slot] = 4
        state.shot_dy[slot] = 0
        state.frame_counter = 1                  # not this channel's anim frame
        _centre_camera(state)
        main_handle_shots(state)
        assert state.shot_anim_lifetime_counter[8] == 0x20
        assert state.mobs.picture[slot] != 0, "a fresh dragon shot must survive"
        assert state.shot_owner_mob[8] == (10 << 5) | 10

    def test_a_new_monster_channel_gets_its_rom_reload(self):
        state = _make_state()
        slot = 5
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = 160 << 7
        state.mobs.vpos[slot] = native_v(160) << 7
        state.shot_dx[slot] = 6
        state.shot_dy[slot] = 0
        state.frame_counter = 1                  # (1 ^ 4) & 1 == 1: not eligible
        _centre_camera(state)
        main_handle_shots(state)
        assert state.shot_anim_lifetime_counter[4] == 0x01
        assert state.shot_direction[4] == 2

    def test_special_channel_does_not_collide_while_its_counter_is_high(self):
        state = _make_state()
        cell = (10 << 5) | 10
        slot = 9
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = 160 << 7
        state.mobs.vpos[slot] = native_v(160) << 7
        state.shot_direction[8] = 2
        state.mobs.insert(slot, depth_key=cell)
        state.shot_owner_mob[8] = 0x3FF
        state.shot_anim_lifetime_counter[8] = 0x20
        state.frame_counter = 1
        _centre_camera(state)
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (160 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        main_handle_shots(state)
        assert state.mobs.picture[cell] != 0, "no collision above counter 5"

    def test_the_screen_origins_are_the_roms_verbatim(self):
        """0x904AC2/4: ``(pf_hscroll - 8) << 7`` and
        ``(0x108 - pf_vscroll_lo) << 7``, both compared as ``word - origin``
        over a 16-bit maze that needs no explicit modulus."""
        state = _make_state()
        state.scroll_x = 0x100
        state.scroll_y = 0x80
        origin_h, origin_v = shots._screen_origins(state)
        assert origin_h == ((0x100 - 8) << 7) & 0xFFFF
        assert origin_v == ((0x108 - 0x80) << 7) & 0xFFFF

        # A shot at the top-left of that window has a small unsigned delta on
        # both axes, straight off the stored words.
        slot = 1
        state.mobs.hpos[slot] = (0x100 - 8) << 7
        state.mobs.vpos[slot] = ((0x108 - 0x80) << 7) & 0xFFFF
        assert (state.mobs.hpos[slot] - origin_h) & 0xFFFF == 0
        assert (state.mobs.vpos[slot] - origin_v) & 0xFFFF == 0

    def test_a_shot_that_leaves_the_window_is_removed(self):
        state, slot = self._running_shot()
        state.scroll_x = 500                     # window is far away
        state.scroll_y = 0x1F0 - 500 - 0x80
        main_handle_shots(state)
        assert state.mobs.picture[slot] == 0
        assert state.mobs.hpos[slot] == 0

    def test_a_shot_heading_back_toward_the_window_survives(self):
        """0x47748: only a shot travelling away from the window is dropped."""
        state, slot = self._running_shot(direction=2)   # moving right
        # Put the window just to the right of the shot, inside the tolerance.
        state.scroll_x = 160 + 8 + 12
        state.scroll_y = 160 - 0x68
        main_handle_shots(state)
        assert state.mobs.picture[slot] != 0

    def test_lobber_rock_survives_the_wrapped_left_camera(self):
        """The level-7 seam window starts near x=496 and continues at x=0."""
        state = _make_state()
        shooter_id = 8
        slot = shooter_id + 1
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = 44 << 7
        state.mobs.vpos[slot] = native_v(160) << 7
        state.shot_direction[shooter_id] = 2
        state.shot_anim_lifetime_counter[shooter_id] = 0x20
        state.lobber_shot_h_accum[0] = state.mobs.hpos[slot]
        state.lobber_shot_v_accum[0] = state.mobs.vpos[slot]
        state.lobber_shot_vec_h[0] = 0x80
        state.mobs.insert(slot, depth_key=(10 << 5) | 3)
        state.shot_owner_mob[shooter_id] = (10 << 5) | 3
        state.scroll_x = 504
        state.scroll_y = 160 - 0x68
        state.frame_counter = 1

        main_handle_shots(state)

        assert state.mobs.picture[slot] != 0
        assert hpos_x(state.mobs.hpos[slot]) & 0x1FF == 45

    def test_crossing_into_a_new_cell_rekeys_the_depth_entry(self):
        state, slot = self._running_shot()
        state.mobs.depth_key[slot] = (10 << 5) | 10
        for _ in range(3):                       # 3 x 6 px = 18 px right
            main_handle_shots(state)
            state.frame_counter += 1
        assert state.mobs.depth_key[slot] == (10 << 5) | 11

    def test_free_player_channels_rearm_the_reflect_counter(self):
        state = _make_state()
        state.reflect_count[0] = 0
        main_handle_shots(state)
        assert state.reflect_count[0] == 4

    def test_a_collision_resolves_and_clears_the_channel(self):
        state, slot = self._running_shot(character=Character.ELF)
        cell = (10 << 5) | 10
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[cell] = (160 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        main_handle_shots(state)
        assert state.mobs.hpos[cell] & 0xF == 3, "ghost took one damage"
        assert state.mobs.picture[slot] == 0, "the shot was consumed"


# =============================================================================
# The lobbed-rock / arc channels 8-11 (0x479C2)
# =============================================================================

def _arm_lobber(state: GameState, shooter_id: int = 8, x: int = 160,
                y: int = 160, vec_h: int = 0, vec_v: int = 0,
                palette: int = 5, size: int = 9, direction: int = 2) -> int:
    """Arm channel ``shooter_id`` exactly the way ``monster_create_shot`` does."""
    from gauntpy.subsystems.shots import lobber_accumulator_seed

    slot = shooter_id + 1
    state.mobs.picture[slot] = 1
    state.mobs.hpos[slot] = ((x & 0x1FF) << 7) | palette
    state.mobs.vpos[slot] = (native_v(y & 0x1FF) << 7) | size
    state.shot_direction[shooter_id] = direction
    state.mobs.insert(slot, depth_key=_cell_of(x, y))
    state.shot_owner_mob[shooter_id] = 0x3FF
    state.shot_anim_lifetime_counter[shooter_id] = 0x20
    state.lobber_shot_vec_h[shooter_id - 8] = vec_h
    state.lobber_shot_vec_v[shooter_id - 8] = vec_v
    lobber_accumulator_seed(state, shooter_id)
    # Put the shot well inside the disposal window on both axes, so only the
    # motion under test decides whether it survives.
    state.scroll_x = x - 128 + 8
    state.scroll_y = y - 0x68
    return slot


def _cell_of(x: int, y: int) -> int:
    return ((((y + 8) >> 4) & 0x1F) << 5) | (((x + 8) >> 4) & 0x1F)


class TestLobberArc:
    def _run(self, state: GameState, slot: int, frames: int) -> list[tuple[int, int]]:
        seen = []
        for _ in range(frames):
            main_handle_shots(state)
            state.frame_counter += 1
            seen.append((hpos_x(state.mobs.hpos[slot]),
                         vpos_y(state.mobs.vpos[slot])))
        return seen

    def test_the_accumulator_carries_the_sub_pixel_remainder(self):
        """0x479DE-0x47A06: 0xC0 per frame is 1.5 px, and the half is kept."""
        state = _make_state()
        slot = _arm_lobber(state, vec_h=0xC0, vec_v=0x60)

        assert self._run(state, slot, 4) == [
            (161, 160), (163, 159), (164, 158), (166, 157),
        ]

    def test_the_accumulator_itself_advances_by_the_raw_vector(self):
        state = _make_state()
        slot = _arm_lobber(state, vec_h=0xC0, vec_v=0x60)
        base_h = state.lobber_shot_h_accum[0]
        base_v = state.lobber_shot_v_accum[0]

        self._run(state, slot, 3)

        assert state.lobber_shot_h_accum[0] == base_h + 3 * 0xC0
        assert state.lobber_shot_v_accum[0] == base_v + 3 * 0x60

    def test_a_sub_pixel_lead_still_moves_the_rock_eventually(self):
        """A vector under one whole pixel per frame cannot survive rounding."""
        state = _make_state()
        slot = _arm_lobber(state, vec_h=0x20)          # 1/4 px per frame

        positions = [x for x, _ in self._run(state, slot, 8)]

        assert positions == [160, 160, 160, 161, 161, 161, 161, 162]

    def test_a_negative_vector_walks_the_accumulator_down(self):
        state = _make_state()
        slot = _arm_lobber(state, x=200, y=200, vec_h=-0xC0, vec_v=-0x60,
                           direction=6)

        assert self._run(state, slot, 4) == [
            (198, 201), (197, 202), (195, 203), (194, 203),
        ]

    def test_the_low_bits_of_both_words_survive_every_step(self):
        """0x479FE keeps ``hpos & 0x7F`` -- the native low field."""
        state = _make_state()
        slot = _arm_lobber(state, vec_h=0xC0, vec_v=0x60, palette=0xB, size=0x12)

        self._run(state, slot, 5)

        assert state.mobs.hpos[slot] & 0x7F == 0x0B
        assert state.mobs.vpos[slot] & 0x7F == 0x12

    def test_a_lobber_never_falls_back_to_the_velocity_tables(self):
        """0x478B4 branches away before ``shot_velocity_x/y`` is ever read."""
        state = _make_state()
        slot = _arm_lobber(state, vec_h=0, vec_v=0)
        state.shot_direction[8] = 2               # would be +6 px/frame if used

        self._run(state, slot, 3)

        assert hpos_x(state.mobs.hpos[slot]) == 160
        assert vpos_y(state.mobs.vpos[slot]) == 160

    def test_the_arc_ignores_the_tier_bits_a_velocity_row_would_use(self):
        state = _make_state()
        slot = _arm_lobber(state, vec_h=0xC0, palette=0x30 | 5)

        self._run(state, slot, 2)

        assert hpos_x(state.mobs.hpos[slot]) == 163      # still 1.5 px
        assert state.mobs.hpos[slot] & 0x7F == 0x35

    def test_a_channel_armed_by_hand_gets_its_accumulator_latched(self):
        """0x49216's seed, replayed by the go-live latch for anything else."""
        state = _make_state()
        slot = 9
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = (160 << 7) | 1
        state.mobs.vpos[slot] = (native_v(160) << 7) | 9
        state.lobber_shot_vec_h[0] = 0x100
        state.frame_counter = 1
        _centre_camera(state)

        main_handle_shots(state)

        assert state.lobber_shot_h_accum[0] == (160 << 7) + 0x100
        assert hpos_x(state.mobs.hpos[slot]) == 162
        assert state.mobs.hpos[slot] & 0x7F == 1

    def test_shot_dx_is_left_to_the_creator(self):
        """The vector never changes in flight, so nothing needs refreshing."""
        state = _make_state()
        slot = _arm_lobber(state, vec_h=0xC0, vec_v=0x60)
        state.shot_dx[slot] = 2               # monster_create_shot's rounding
        state.shot_dy[slot] = -1

        self._run(state, slot, 3)

        assert state.shot_dx[slot] == 2
        assert state.shot_dy[slot] == -1


def _rom_arc(pixel: int, low: int, vector: int, frames: int) -> list[int]:
    """0x479DE-0x47A0C transcribed literally, in the ROM's own words.

    The position mask is 0xFF80 and the low field everything under it.
    Returns the pixel the routine's ``lsr.w`` would have produced each frame.
    """
    accum = (pixel << 7) & 0xFFFF
    word = accum | low
    out = []
    for _ in range(frames):
        accum = (accum + vector) & 0xFFFF
        word = ((accum & 0xFF80) + (word & 0x007F)) & 0xFFFF
        out.append(word >> 7)
    return out


class TestLobberArcAgainstRom:
    """Differential: the port must be 0x479C2, word for word."""

    VECTORS = (0x10, 0x30, 0x60, 0x80, 0xC0, 0x140, -0x10, -0x60, -0x140)

    def _run(self, state: GameState, slot: int, frames: int) -> list[int]:
        """Advance ``frames`` times, keeping the disposal window out of it."""
        out = []
        for _ in range(frames):
            x = hpos_x(state.mobs.hpos[slot])
            y = vpos_y(state.mobs.vpos[slot])
            state.scroll_x = x - 128 + 8          # the shot sits well inside
            state.scroll_y = y - 0x68
            main_handle_shots(state)
            state.frame_counter += 1
            out.append(hpos_x(state.mobs.hpos[slot]))
        return out

    def test_the_port_runs_the_same_accumulator_algorithm(self):
        for vector in self.VECTORS:
            state = _make_state()
            slot = _arm_lobber(state, x=160, y=160, vec_h=vector, palette=0x0B)
            expected = _rom_arc(160, 0x0B, vector, 6)
            assert self._run(state, slot, 6) == expected, f"vector {vector:#x}"

    def test_a_whole_pixel_vector_lands_on_whole_pixels(self):
        """0x80 is exactly one pixel, so no remainder ever accumulates."""
        assert _rom_arc(160, 0x0B, 0x80, 4) == [161, 162, 163, 164]
        assert _rom_arc(160, 0x0B, -0x80, 4) == [159, 158, 157, 156]

    def test_the_low_field_is_never_disturbed(self):
        for low in (0x00, 0x05, 0x1F, 0x38, 0x7F):
            state = _make_state()
            slot = _arm_lobber(state, vec_h=0xC0, vec_v=-0xC0,
                               palette=low, size=low)
            self._run(state, slot, 5)
            assert state.mobs.hpos[slot] & 0x7F == low
            assert state.mobs.vpos[slot] & 0x7F == low


# =============================================================================
# Dragon fire in the demon channels (0x54748 -> 0x474F6)
# =============================================================================

def _arm_dragon_fire(state: GameState, shooter_id: int = 7, x: int = 160,
                     y: int = 160, direction: int = 2) -> int:
    """The channel state ``dragon_fire_setup``'s breath branch leaves behind."""
    slot = shooter_id + 1
    state.mobs.picture[slot] = 0x27D4
    state.mobs.hpos[slot] = ((x & 0x1FF) << 7) | 0x38     # tier 0x30, palette 8
    state.mobs.vpos[slot] = (native_v(y & 0x1FF) << 7) | 0x12     # 3x3 tiles
    state.shot_direction[shooter_id] = direction
    state.shot_anim_lifetime_counter[shooter_id] = 0x13
    state.shot_owner_mob[shooter_id] = 0x3FF
    state.mobs.insert(slot, depth_key=_cell_of(x, y))
    _centre_camera(state, x, y)
    return slot


class TestDragonFireChannel:
    def test_the_breath_is_a_max_tier_shot_on_a_demon_channel(self):
        state = _make_state()
        _arm_dragon_fire(state)
        assert shots._is_maxtier(state, 7)
        assert shots._shot_tier(state, 7) == 0x30

    def test_it_uses_the_0x50_velocity_block_on_even_frames_only(self):
        state = _make_state()
        slot = _arm_dragon_fire(state)

        state.frame_counter = 1
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 160, "held still"

        state.frame_counter = 2
        main_handle_shots(state)
        assert hpos_x(state.mobs.hpos[slot]) == 162   # ROM 0x100 >> 7

    def test_it_keeps_its_tier_and_palette_while_it_flies(self):
        state = _make_state()
        slot = _arm_dragon_fire(state)
        state.frame_counter = 2
        main_handle_shots(state)
        assert state.mobs.hpos[slot] & 0x7F == 0x38
        assert state.mobs.vpos[slot] & 0x7F == 0x12

    def test_it_does_not_expire_on_its_first_tick(self):
        """0x477E8 kills a max-tier channel at counter 0; 0x54814 seeds 0x13."""
        state = _make_state()
        slot = _arm_dragon_fire(state)
        for frame in range(8):
            state.frame_counter = frame
            main_handle_shots(state)
            assert state.mobs.picture[slot] != 0, f"died on frame {frame}"
        assert state.shot_anim_lifetime_counter[7] == 0x13 - 4

    def test_it_expires_once_the_counter_reaches_zero(self):
        state = _make_state()
        slot = _arm_dragon_fire(state)
        for frame in range(64):
            state.frame_counter = frame
            main_handle_shots(state)
            if state.mobs.picture[slot] == 0:
                break
        assert state.mobs.picture[slot] == 0
        # 0x13 = 19 animation ticks, one per odd frame, then 0x477E8 fires on
        # that same pass.
        assert frame == 2 * 0x13 - 1

    def test_its_animation_walks_the_special_projectile_block(self):
        state = _make_state()
        slot = _arm_dragon_fire(state)
        state.frame_counter = 2                  # (2 ^ 7) & 1 == 1: not ours
        main_handle_shots(state)
        assert state.shot_anim_lifetime_counter[7] == 0x13
        assert state.mobs.picture[slot] == 0x27D4    # index (2&6)*10 + 0x13
        state.frame_counter = 3
        main_handle_shots(state)
        assert state.mobs.picture[slot] == 0x27D4    # index 38, same artwork
        state.frame_counter = 5
        main_handle_shots(state)
        assert state.mobs.picture[slot] == 0x27D4    # index 37
        state.frame_counter = 7
        main_handle_shots(state)
        assert state.mobs.picture[slot] == 0x27DD    # index 36, next artwork

    def test_it_uses_the_fixed_max_tier_hitbox(self):
        """0x4094C swaps in the large box for any max-tier channel."""
        state = _make_state()
        cell = (10 << 5) | 10
        _arm_dragon_fire(state)
        _place_monster(state, cell, MazeObjIds.MONST_GHOST, health_nibble=4)
        # 12 px away: outside the 0x480/2 demon box, inside the 0x880/2 one.
        state.mobs.hpos[cell] = (172 << 7) | 4
        state.mobs.vpos[cell] = native_v(160) << 7
        assert shot_mob_collision(state, cell, 7) == cell

        # The same geometry on an ordinary demon channel misses.
        state.mobs.picture[7] = 1
        state.mobs.hpos[7] = (160 << 7) | 0x08
        state.mobs.vpos[7] = native_v(160) << 7
        state.shot_direction[6] = 2
        state.shot_owner_mob[6] = 0x3FF
        assert shot_mob_collision(state, cell, 6) == -1

    def test_it_deals_the_tier_three_damage_row(self):
        state = _make_state()
        _arm_dragon_fire(state)
        victim = state.players[0]
        victim.character = Character.WARRIOR
        victim.mob_slot = 0x30
        victim.health = 500
        state.mobs.link[0x30] = 0
        state.mobs.hpos[0x30] = (160 << 7) | 0x0C
        state.mobs.vpos[0x30] = native_v(160) << 7
        state.mobs.picture[0x30] = 1
        state.mobs.state_link[0x30] = 0

        resolve_shot_hit(state, 0x30, 7)

        assert victim.health == 500 - 8          # monstshot_damage_tbl[0x20]

    def test_it_raises_the_dragon_dialog_and_spends_dont_get_hit(self):
        from gauntpy.subsystems.exits import TRICK_NOGETHIT

        state = _make_state()
        _arm_dragon_fire(state)
        state.secret_trick_id = TRICK_NOGETHIT
        victim = state.players[0]
        victim.character = Character.WARRIOR
        victim.mob_slot = 0x30
        victim.health = 500
        state.mobs.link[0x30] = 0
        state.mobs.hpos[0x30] = (160 << 7) | 0x0C
        state.mobs.vpos[0x30] = native_v(160) << 7
        state.mobs.picture[0x30] = 1

        resolve_shot_hit(state, 0x30, 7)

        assert state.dialog_first_encounter_flags & (1 << 14)
        assert state.secret_tricks_flags[0] == 1

    def test_an_ordinary_demon_shot_stays_on_the_base_damage_row(self):
        """The same code path, without the 0x30 bits: row 0, record 10."""
        state = _make_state()
        slot = 7
        state.mobs.picture[slot] = 1
        state.mobs.hpos[slot] = (160 << 7) | 0x08
        state.mobs.vpos[slot] = native_v(160) << 7
        state.shot_direction[6] = 2
        victim = state.players[0]
        victim.character = Character.WARRIOR
        victim.mob_slot = 0x30
        victim.health = 500
        state.mobs.link[0x30] = 0
        state.mobs.hpos[0x30] = (160 << 7) | 0x0C
        state.mobs.vpos[0x30] = native_v(160) << 7
        state.mobs.picture[0x30] = 1

        resolve_shot_hit(state, 0x30, 6)

        assert victim.health == 500 - 4
        assert state.dialog_first_encounter_flags & (1 << 10)
        assert state.secret_tricks_flags[0] == 0


# =============================================================================
# Reflection (shot_reflect_calc, 0x53818)
# =============================================================================

class TestReflection:
    def test_a_cardinal_shot_reverses(self):
        state = _make_state()
        state.shot_direction[0] = 2               # right
        assert shot_reflect_calc(state, 0x400 | 300, 0) == 6

    def test_reflecting_spends_one_bounce_and_plays_the_sound(self):
        state = _make_state()
        state.shot_direction[0] = 0
        state.reflect_count[0] = 4
        shot_reflect_calc(state, 0x400 | 300, 0)
        assert state.reflect_count[0] == 3
        assert 0x2C in state.sound_log

    def test_a_reflecting_player_keeps_the_shot_alive(self):
        state = _make_state()
        state.players[0].powers = 0x400           # POWER_REFLECT
        state.shot_direction[0] = 2
        state.reflect_count[0] = 4
        SLOT = 390
        _place_typed(state, SLOT, MazeObjIds.WALL_REGULAR)
        assert resolve_shot_hit(state, SLOT, 0) == 0
        assert state.shot_direction[0] == 6
        assert state.reflect_count[0] == 3

    def test_the_last_bounce_consumes_the_shot(self):
        state = _make_state()
        state.players[0].powers = 0x400
        state.shot_direction[0] = 2
        state.reflect_count[0] = 1
        state.mobs.picture[1] = 1
        SLOT = 391
        _place_typed(state, SLOT, MazeObjIds.WALL_REGULAR)
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.reflect_count[0] == 0
        assert state.mobs.picture[1] == 0

    def test_a_wall_hit_is_remembered_for_the_next_bounce(self):
        state = _make_state()
        state.shot_direction[0] = 4
        shot_reflect_calc(state, 300, 0)
        assert state.player_shot_last_wall_pos[0] == 300


# =============================================================================
# HUD latches -- the ROM's player_redraw bits (0x904908), WP-14's
# score_dirty / health_dirty
# =============================================================================

def _clear_latches(state: GameState) -> None:
    """Both flags start dirty so the first frame draws; start clean instead."""
    for i in range(4):
        state.score_dirty[i] = 0
        state.health_dirty[i] = 0


class TestHudLatches:
    def test_a_kill_marks_the_shooters_score_panel_dirty(self):
        """0x5217C: player_add_score_with_mult ends with ``ori.b #1``."""
        state = _make_state()
        state.players[0].character = Character.ELF
        _clear_latches(state)
        SLOT = 400
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)

        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].score == 10
        assert state.score_dirty[0] == 1
        assert state.score_dirty[1] == 0, "only the shooter's panel is dirty"

    def test_a_surviving_monster_still_scores_and_latches(self):
        state = _make_state()
        state.players[0].character = Character.ELF
        _clear_latches(state)
        SLOT = 401
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=4)

        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[SLOT] != 0
        assert state.score_dirty[0] == 1

    def test_a_monster_shot_kill_latches_nothing(self):
        """0x4BD66 skips the score tail entirely for shooter >= 4."""
        state = _make_state()
        _clear_latches(state)
        SLOT = 402
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)
        _arm_monster_shot(state, 4)

        resolve_shot_hit(state, SLOT, 4)
        assert all(flag == 0 for flag in state.score_dirty)

    def test_generator_and_supersorc_kills_latch_too(self):
        state = _make_state()
        _clear_latches(state)
        SLOT = 403
        state.mobs.link[SLOT] = (int(MazeObjIds.GEN_GHOST1) << 10) & 0xFFFF
        state.mobs.hpos[SLOT] = 100 << 7
        state.mobs.vpos[SLOT] = native_v(100) << 7
        state.mobs.picture[SLOT] = 1
        state.mobs.insert(SLOT)
        resolve_shot_hit(state, SLOT, 0)
        assert state.score_dirty[0] == 1

        _clear_latches(state)
        SLOT = 404
        _place_typed(state, SLOT, MazeObjIds.MONST_SUPERSORC, palette=0x0B)
        resolve_shot_hit(state, SLOT, 0)
        assert state.score_dirty[0] == 1

    def test_monster_shot_damage_marks_the_victims_health_dirty(self):
        """0x4B282: ``ori.b #2`` on the victim, not the shooter."""
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 405, 1)
        _arm_monster_shot(state, 4)
        _clear_latches(state)

        resolve_shot_hit(state, 405, 4)
        assert state.players[1].health < 100
        assert state.health_dirty[1] == 1
        assert state.health_dirty[0] == 0

    def test_shothurt_marks_the_victims_health_dirty(self):
        state = _make_state()
        state.level_flags_4 = 0x02
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 406, 1)
        _clear_latches(state)

        resolve_shot_hit(state, 406, 0)
        assert state.players[1].health == 98
        assert state.health_dirty[1] == 1

    def test_supershot_on_a_player_marks_health_dirty(self):
        state = _make_state()
        state.level_flags_4 = 0
        state.players[0].supershot = 1
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 407, 1)
        _clear_latches(state)

        resolve_shot_hit(state, 407, 0)
        assert state.players[1].health == 90
        assert state.health_dirty[1] == 1

    def test_a_stun_only_hit_leaves_the_health_panel_clean(self):
        """The 0x4B074 stun path has no ``ori.b #2`` -- no health changed."""
        state = _make_state()
        state.level_flags_4 = 0x01
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        _place_player_mob(state, 408, 1)
        _clear_latches(state)

        resolve_shot_hit(state, 408, 0)
        assert state.players[1].stundelay == 0x28
        assert state.health_dirty[1] == 0

    def test_an_acid_immune_victim_leaves_the_health_panel_clean(self):
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 100
        state.players[1].acid_timer = 30
        _place_player_mob(state, 409, 1)
        _arm_monster_shot(state, 4)
        _clear_latches(state)

        resolve_shot_hit(state, 409, 4)
        assert state.players[1].health == 100
        assert state.health_dirty[1] == 0

    def test_the_info_panel_picks_a_shot_kill_up_on_the_next_turn(self):
        """End to end: the latch is what WP-14's main_score_display consumes."""
        from gauntpy.subsystems.score import info_panel, main_score_display

        state = _make_state()
        state.players[0].character = Character.ELF
        state.frame_counter = 0
        main_score_display(state)                 # settle player 0's panel
        _clear_latches(state)
        drawn = info_panel(state).players[0].score

        SLOT = 410
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)
        resolve_shot_hit(state, SLOT, 0)
        assert state.score_dirty[0] == 1

        main_score_display(state)
        assert info_panel(state).players[0].score == state.players[0].score
        assert info_panel(state).players[0].score != drawn
        assert state.score_dirty[0] == 0, "the draw clears the latch"


class TestScoreEffectAnimationInterop:
    """The impact/dissolve MOBs WP-7 spawns must age under WP-14's loop 3."""

    def test_an_impact_effect_ages_and_expires(self):
        from gauntpy.subsystems.score import main_score_update

        state = _make_state()
        SLOT = 411
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=1)
        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.picture[0x0D] == 0x0EFC

        for _ in range(16):
            main_score_update(state)
        assert state.mobs.picture[0x0D] == 0, "the pool channel is released"

    def test_a_transporter_dissolve_ages_through_its_own_cycle(self):
        from gauntpy.subsystems.score import main_score_update

        state = _make_state()
        source = 412
        state.mobs.hpos[source] = 160 << 7
        state.mobs.vpos[source] = native_v(160) << 7
        tport_cycle_start(state, source, 0)
        assert state.mobs.picture[0x0D] == 0x0924
        assert state.mob_effect_anim_counter[0] == 0xFF

        main_score_update(state)                  # 0xFF wraps to 0: frame zero
        assert state.mob_effect_anim_counter[0] == 0
        assert state.mobs.picture[0x0D] == 0x0924
        for _ in range(30):
            main_score_update(state)
        assert state.mobs.picture[0x0D] == 0


# =============================================================================
# First-encounter dialog records (0x4C440) -- exactly seven ROM call sites
# =============================================================================

def _records_raised(state: GameState) -> set:
    """Record numbers whose ``dialog_first_encounter`` flag is now set."""
    flags = state.dialog_first_encounter_flags
    return {bit for bit in range(32) if flags & (1 << bit)}


class TestEncounterRecords:
    def test_shooting_food_raises_record_1(self):
        """0x4B930 pushes 0x02: 'SOME FOOD DESTROYED BY SHOTS'."""
        state = _make_state()
        SLOT = 420
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=0x0963)
        resolve_shot_hit(state, SLOT, 0)
        assert _records_raised(state) == {shots._DIALOG_FOOD_SHOT}
        assert shots._DIALOG_FOOD_SHOT == 1

    def test_shooting_a_potion_raises_record_6(self):
        """0x4BA46 pushes 0x40: 'SHOOTING A POTION HAS A LESSER EFFECT'."""
        state = _make_state()
        SLOT = 421
        _place_typed(state, SLOT, MazeObjIds.POT_DESTRUCTABLE, picture=0x0987)
        resolve_shot_hit(state, SLOT, 0)
        assert shots._DIALOG_POTION_SHOT in _records_raised(state)
        assert shots._DIALOG_POTION_SHOT == 6
        assert state.playfield_color_latch == 0xFF00

    def test_shooting_poison_raises_record_7_instead(self):
        """0x4B8F0/0x4BA40 push 0x80 for the slow-motion pictures."""
        state = _make_state()
        SLOT = 422
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=0x25ED)
        resolve_shot_hit(state, SLOT, 0)
        assert _records_raised(state) == {shots._DIALOG_POISON_SHOT}
        assert shots._DIALOG_POISON_SHOT == 7

        state = _make_state()
        SLOT = 423
        _place_typed(state, SLOT, MazeObjIds.POT_DESTRUCTABLE, picture=0x20FC)
        resolve_shot_hit(state, SLOT, 0)
        assert _records_raised(state) == {shots._DIALOG_POISON_SHOT}

    def _monster_shot_record(self, shooter_id, tier):
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 500
        _place_player_mob(state, 424, 1)
        _arm_monster_shot(state, shooter_id, tier)
        resolve_shot_hit(state, 424, shooter_id)
        return _records_raised(state)

    def test_an_ordinary_monster_shot_raises_the_demon_record_10(self):
        """0x4B2D8 pushes 0x400 -- channels 4-7 are the demon shots."""
        assert self._monster_shot_record(4, 0) == {shots._DIALOG_DEMON_SHOT}
        assert shots._DIALOG_DEMON_SHOT == 10

    def test_a_special_channel_shot_raises_the_lobber_record_11(self):
        """0x4B2CE pushes 0x800 -- channels 8-11 are the lobber shots."""
        assert self._monster_shot_record(8, 0) == {shots._DIALOG_LOBBER_SHOT}
        assert shots._DIALOG_LOBBER_SHOT == 11

    def test_a_tier_one_shot_raises_record_16(self):
        assert self._monster_shot_record(4, 0x10) == {shots._DIALOG_STRONG_SHOT}
        assert shots._DIALOG_STRONG_SHOT == 16

    def test_a_tier_two_or_three_shot_raises_the_dragon_record_14(self):
        """0x4B292 pushes 0x4000 -- \"SHOOT DRAGON'S HEAD\"."""
        assert self._monster_shot_record(4, 0x20) == {shots._DIALOG_DRAGON_SHOT}
        assert self._monster_shot_record(4, 0x30) == {shots._DIALOG_DRAGON_SHOT}
        assert shots._DIALOG_DRAGON_SHOT == 14

    def test_shooting_another_player_raises_record_18(self):
        state = _make_state()
        state.level_flags_4 = 0
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        _place_player_mob(state, 425, 1)
        resolve_shot_hit(state, 425, 0)
        assert _records_raised(state) == {shots._DIALOG_PLAYER_SHOT}
        assert shots._DIALOG_PLAYER_SHOT == 18

    def test_shooting_a_destructible_wall_raises_record_22(self):
        state = _make_state()
        SLOT = 426
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        resolve_shot_hit(state, SLOT, 0)
        assert _records_raised(state) == {shots._DIALOG_WALL_SHOT}
        assert shots._DIALOG_WALL_SHOT == 22

    def test_the_box_is_shown_once_per_game(self):
        state = _make_state()
        for slot in (427, 428):
            _place_typed(state, slot, MazeObjIds.FOOD_DESTRUCTABLE,
                         picture=0x0963)
        resolve_shot_hit(state, 427, 0)
        shown = list(state.dialog_message)
        state.dialog_timer = 0
        state.dialog_message = []
        resolve_shot_hit(state, 428, 0)
        assert shown and state.dialog_message == [], "second shot is silent"

    def test_ghost_grunt_and_sorcerer_records_are_not_shot_records(self):
        """Records 8, 9 and 12 belong to monster *contact* (0x495A6).

        None of those three families fire projectiles, so no shot path can
        reach them; the ROM raises them from monster_playerhit's computed-mask
        calls at 0x4986A/0x49A2C, which is WP-8's.
        """
        contact_only = {8, 9, 12}
        state = _make_state()
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 5000
        _place_player_mob(state, 429, 1)

        # Every projectile encounter path, in one game.
        for shooter_id, tier in ((4, 0), (8, 0), (4, 0x10), (4, 0x20)):
            _arm_monster_shot(state, shooter_id, tier)
            resolve_shot_hit(state, 429, shooter_id)
        resolve_shot_hit(state, 429, 0)                 # player versus player
        for slot, obj_type, picture in (
            (430, MazeObjIds.FOOD_DESTRUCTABLE, 0x0963),
            (431, MazeObjIds.FOOD_DESTRUCTABLE, 0x25ED),
            (432, MazeObjIds.POT_DESTRUCTABLE, 0x0987),
            (433, MazeObjIds.WALL_DESTRUCTABLE, 1),
        ):
            _place_typed(state, slot, obj_type, picture=picture)
            resolve_shot_hit(state, slot, 0)

        raised = _records_raised(state)
        assert raised == {1, 6, 7, 10, 11, 14, 16, 18, 22}, (
            "the seven ROM call sites raise exactly these nine records"
        )
        assert not raised & contact_only

    def test_player_shot_record_shows_the_rom_message_without_speech(self):
        state = _make_state()
        assert shots._dialog(state, 0, shots._DIALOG_PLAYER_SHOT) == 0
        assert state.dialog_message == [
            "  SHOTS DO NOT HURT  ",
            " OTHER PLAYERS (YET) ",
        ]
        assert shots._DIALOG_PLAYER_SHOT in _records_raised(state)


# =============================================================================
# shot_timer_next (0x90492A) -- the demon/lobber cadence decrement at 0x4750C
# =============================================================================

class TestShotTimerNext:
    def test_only_the_eight_monster_channels_tick(self):
        state = _make_state()
        state.shot_timer_next = [4, 3, 2, 1, 9, 8, 7, 6]
        main_handle_shots(state)
        assert state.shot_timer_next == [3, 2, 1, 0, 8, 7, 6, 5]
        assert len(state.shot_timer_next) == 8, "0x90492A is 2 B x 8"

    def test_a_zero_timer_never_goes_negative(self):
        """0x47516 ``tst.w`` gates the ``subq`` -- zero stays zero."""
        state = _make_state()
        state.shot_timer_next = [0] * 8
        for _ in range(3):
            main_handle_shots(state)
        assert state.shot_timer_next == [0] * 8

    def test_the_timers_tick_even_with_no_live_shots(self):
        state = _make_state()
        state.shot_timer_next = [1] * 8
        assert all(state.mobs.picture[s] == 0 for s in range(1, 13))
        main_handle_shots(state)
        assert state.shot_timer_next == [0] * 8

    def test_the_timers_tick_before_any_channel_is_serviced(self):
        """0x4750C runs to completion before the per-channel loop at 0x47534."""
        state = _make_state()
        state.shot_timer_next = [2] * 8
        state.players[0].mob_slot = 0x3FF
        slot = _arm_player_shot(state)
        state.mobs.insert(slot, depth_key=(10 << 5) | 10)
        state.shot_owner_mob[0] = 0x3FF
        _centre_camera(state)
        main_handle_shots(state)
        assert state.shot_timer_next == [1] * 8
        assert state.mobs.picture[slot] != 0


# =============================================================================
# Probe wrapping (0x40A78-0x40AA4) -- the two maze-edge windows
# =============================================================================

class _FakeMaze:
    def __init__(self, wallpattern: int) -> None:
        self.wallpattern = wallpattern
        self.data = {}


def _probe_indices(cell: int, direction: int):
    """Every word index shot_mob_collision probes for one cell/direction."""
    index = (cell * 2) & 0xFFFF
    yield index
    row_base = index & 0x7C0
    for h_delta, v_delta in shots._PROBE_OFFSETS[direction & 7]:
        index = ((index + h_delta) & 0xFFFF) & 0x3E
        index = (index + v_delta + row_base) & 0xFFFF
        yield index


class TestProbeWrapWindows:
    def test_high_window_is_the_bottom_half_of_row_zero(self):
        """0x40A88/0x40A8A: V negative and <= 0xF3FF is 9 <= y <= 240."""
        state = _make_state()
        for y, expected in ((0, False), (8, False), (9, True),
                            (240, True), (241, False), (500, False)):
            state.mobs.vpos[1] = native_v(y & 0x1FF) << 7
            assert shots._wrap_allowed(state, 0) is expected, y

    def test_a_genuine_downward_overflow_needs_cell_row_31(self):
        """Only the bottom maze row can push a probe past the last cell."""
        for cell in range(1024):
            for direction in range(8):
                for index in _probe_indices(cell, direction):
                    if 0x800 <= index < 0x8000:
                        assert cell >> 5 == 31, (cell, direction, index)

    def test_cell_row_31_can_never_pass_the_wrap_window(self):
        """main_handle_shots re-keys after every move, so the shot's cell and
        its V word agree: a row-31 cell means y >= 488, outside 9..240."""
        state = _make_state()
        rows = 0
        for y in range(512):
            state.mobs.hpos[1] = 0
            state.mobs.vpos[1] = native_v(y) << 7
            if shots._shot_cell(state, 1) >> 5 != 31:
                continue
            rows += 1
            assert y >= 488, y
            assert not shots._wrap_allowed(state, 0), y
        assert rows, "no vertical position keys onto the bottom maze row"

    def test_the_only_wrapped_indices_land_on_row_31(self):
        """Every index that reaches the wrap branch is a negative one."""
        seen = 0
        for cell in range(1024):
            for direction in range(8):
                for index in _probe_indices(cell, direction):
                    if index >= 0x8000:
                        seen += 1
                        assert 0x7C0 <= ((index + 0x800) & 0xFFFF) < 0x800
        assert seen, "no probe ever leaves the top of the maze"

    def test_a_shot_in_row_zero_wraps_a_probe_round_to_row_31(self):
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state, 0, x=160, y=12)
        state.shot_direction[0] = 0                     # heading up
        target = (31 << 5) | 10
        _place_monster(state, target, MazeObjIds.MONST_GHOST, health_nibble=4)
        hit = shot_mob_collision(state, (0 << 5) | 10, 0)
        assert hit == target

    def test_a_max_tier_shot_never_wraps(self):
        """0x40A90: the biased hpos carries the max-tier sign bit."""
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state, 0, x=160, y=12, tier=0x30)
        state.shot_direction[0] = 0
        target = (31 << 5) | 10
        _place_monster(state, target, MazeObjIds.MONST_GHOST, health_nibble=4)
        assert shot_mob_collision(state, (0 << 5) | 10, 0) == -1

    def test_row_zero_returns_a_tagged_playfield_boundary(self):
        """0x40A9A: top-row shots return 0x400+cell, not a reserved MOB."""
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state, 0, x=160, y=4)
        state.shot_direction[0] = 0
        for slot in range(0x20):
            if slot in (1, 0x3FF):
                continue
            state.mobs.picture[slot] = 1
            state.mobs.hpos[slot] = 160 << 7
            state.mobs.vpos[slot] = native_v(4) << 7
        assert shot_mob_collision(state, (0 << 5) | 10, 0) == 0x400 | 10

    def test_reflective_shot_bounces_off_the_top_playfield_boundary(self):
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        state.players[0].powers = 0x400
        state.reflect_count[0] = 4
        _arm_player_shot(state, 0, x=160, y=8)
        state.shot_direction[0] = 1

        target = shot_mob_collision(state, (0 << 5) | 10, 0)

        assert target == 0x400 | 10
        assert resolve_shot_hit(state, target, 0) == 0
        assert state.shot_direction[0] == 3
        assert state.reflect_count[0] == 3

    def test_the_wrap_returns_the_cell_without_a_hitbox_test(self):
        """0x40A94 returns the wrapped index straight to the caller."""
        state = _make_state()
        state.players[0].mob_slot = 0x3FF
        _arm_player_shot(state, 0, x=160, y=12)
        state.shot_direction[0] = 0
        target = (31 << 5) | 10
        _place_monster(state, target, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.mobs.hpos[target] = (0 << 7) | 4        # nowhere near the shot
        state.mobs.vpos[target] = native_v(0) << 7
        assert shot_mob_collision(state, (0 << 5) | 10, 0) == target


# =============================================================================
# wall_crumble (0x5303A) -- the real tile-graphic stages
# =============================================================================

class TestWallCrumbleStages:
    def test_shrub_levels_walk_the_three_stamp_records(self):
        state = _make_state()
        state.maze = _FakeMaze(wallpattern=6)
        SLOT = 400
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        assert shots.wall_crumble_descriptor(state, SLOT) is None
        for stage in (1, 2):
            assert wall_crumble(state, SLOT, 1) == 0
            assert state.destructible_wall_stage[SLOT] == stage
            assert (shots.wall_crumble_descriptor(state, SLOT)
                    == shots._WALL_CRUMBLE_DESCS[stage])
        assert wall_crumble(state, SLOT, 1) == -1
        assert SLOT not in state.destructible_wall_stage

    def test_the_stamp_records_are_the_rom_descriptors(self):
        """0x5BA5C -> 0x5D3D0/0x5D3D8/0x5D3E0, four stamp words each."""
        assert shots._WALL_CRUMBLE_DESCS == (
            (0x07A7, 0x07A8, 0x07A9, 0x07AA),
            (0x07AB, 0x07AC, 0x07AD, 0x07AE),
            (0x07AF, 0x07B0, 0x07B1, 0x07B2),
        )

    def test_they_match_gex_shrub_destruct_stamps(self):
        gex_wall = pytest.importorskip("gex.wall")
        assert [list(d) for d in shots._WALL_CRUMBLE_DESCS] == [
            list(s) for s in gex_wall.SHRUB_DESTRUCT_STAMPS
        ]

    def test_non_shrub_levels_walk_the_palette_down_from_seven(self):
        state = _make_state()
        state.maze = _FakeMaze(wallpattern=0)
        SLOT = 401
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        assert shots.wall_crumble_palette(state, SLOT) == 7
        assert wall_crumble(state, SLOT, 1) == 0
        assert shots.wall_crumble_palette(state, SLOT) == 6
        assert wall_crumble(state, SLOT, 1) == 0
        assert shots.wall_crumble_palette(state, SLOT) == 5
        assert wall_crumble(state, SLOT, 1) == -1
        assert shots.wall_crumble_descriptor(state, SLOT) is None

    @pytest.mark.parametrize("wallpattern", [0, 5, 6, 11])
    @pytest.mark.parametrize("first,second", [(1, 2), (2, 1), (3, 0)])
    def test_both_branches_share_one_three_point_ladder(self, wallpattern,
                                                        first, second):
        state = _make_state()
        state.maze = _FakeMaze(wallpattern=wallpattern)
        SLOT = 402
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        if second:
            assert wall_crumble(state, SLOT, first) == 0
            assert wall_crumble(state, SLOT, second) == -1
        else:
            assert wall_crumble(state, SLOT, first) == -1

    def test_lflag2_bit7_still_wins_over_both_branches(self):
        state = _make_state()
        state.maze = _FakeMaze(wallpattern=6)
        state.level_flags_2 = 0x80
        SLOT = 403
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        assert wall_crumble(state, SLOT, 1) == -1
        assert state.mobs.picture[SLOT] == 0

    def test_an_unmatched_shrub_descriptor_destroys_outright(self):
        """0x53096: a tile whose stamp is in no record reads back huge."""
        state = _make_state()
        state.maze = _FakeMaze(wallpattern=6)
        SLOT = 404
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        state.destructible_wall_stage[SLOT] = 9
        assert wall_crumble(state, SLOT, 0) == -1
        assert state.mobs.picture[SLOT] == 0

    def test_destroying_a_wall_clears_the_tile(self):
        state = _make_state()
        state.maze = _FakeMaze(wallpattern=6)
        SLOT = 405
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        assert wall_crumble(state, SLOT, 3) == -1
        assert state.mobs.picture[SLOT] == 0
        assert state.mobs.link[SLOT] == 0
        assert SLOT not in state.destructible_wall_stage

    def test_a_missing_maze_falls_back_to_the_palette_branch(self):
        state = _make_state()
        assert state.maze is None
        SLOT = 406
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        assert wall_crumble(state, SLOT, 1) == 0
        assert shots.wall_crumble_palette(state, SLOT) == 6


# =============================================================================
# The shared routines resolve_shot_hit calls -- now real, not stubs
# =============================================================================

class TestDragonProximity:
    def _sleeping_dragon(self, state: GameState, head_cell: int) -> None:
        state.dragon_seg_mob_ids[0] = head_cell
        state.dragon_state = 0x01              # _ST_WAKING
        state.dragon_anim_ctr = 0

    def test_a_kill_inside_the_box_starts_the_wake(self):
        """0x549EA: the ROM re-checks the box from the kill cell."""
        state = _make_state()
        head = (10 << 5) | 10
        self._sleeping_dragon(state, head)
        shots._dragon_proximity(state, (13 << 5) | 15)      # offsets +3, +5
        assert state.dragon_anim_ctr == 0x31

    @pytest.mark.parametrize("cell_offset", [(0, 6), (5, 0)])
    def test_a_kill_outside_the_box_is_ignored(self, cell_offset):
        state = _make_state()
        head = (10 << 5) | 10
        self._sleeping_dragon(state, head)
        drow, dcol = cell_offset
        shots._dragon_proximity(state, ((10 + drow) << 5) | (10 + dcol))
        assert state.dragon_anim_ctr == 0

    def test_the_box_is_ten_by_ten_around_the_primary_segment(self):
        """0x54A10-0x54A66: columns -4..+5 and rows -5..+4."""
        state = _make_state()
        head = (10 << 5) | 10
        for dcol, drow, wakes in (
            (-4, -5, True), (5, 4, True), (-5, 0, False), (0, 5, False),
        ):
            self._sleeping_dragon(state, head)
            shots._dragon_proximity(state, ((10 + drow) << 5) | (10 + dcol))
            assert (state.dragon_anim_ctr == 0x31) is wakes

    def test_no_dragon_means_nothing_happens(self):
        state = _make_state()
        state.dragon_seg_mob_ids[0] = 0
        state.dragon_state = 0x01
        shots._dragon_proximity(state, (10 << 5) | 10)
        assert state.dragon_anim_ctr == 0

    def test_a_dragon_already_moving_is_left_alone(self):
        state = _make_state()
        self._sleeping_dragon(state, (10 << 5) | 10)
        state.dragon_anim_ctr = 7
        shots._dragon_proximity(state, (10 << 5) | 10)
        assert state.dragon_anim_ctr == 7

    def test_the_box_folds_on_a_wrapping_level(self):
        state = _make_state()
        self._sleeping_dragon(state, (10 << 5) | 1)
        shots._dragon_proximity(state, (10 << 5) | 30)      # dx 29 -> 3
        assert state.dragon_anim_ctr == 0x31

    def test_stun_clears_when_an_event_enters_the_box(self):
        state = _make_state()
        head = (10 << 5) | 10
        state.dragon_seg_mob_ids[0] = head
        state.dragon_state = 0x02

        shots._dragon_proximity(state, head)

        assert state.dragon_state == 0
        assert state.sound_log[-1] == 0xD5

    def test_movement_remaining_inside_the_box_does_not_clear_stun(self):
        state = _make_state()
        head = (10 << 5) | 10
        state.dragon_seg_mob_ids[0] = head
        state.dragon_state = 0x02

        shots._dragon_proximity(state, head + 1, head)

        assert state.dragon_state == 0x02

    def test_crossing_into_the_box_clears_stun(self):
        state = _make_state()
        head = (10 << 5) | 10
        state.dragon_seg_mob_ids[0] = head
        state.dragon_state = 0x02
        outside = (10 << 5) | 16
        inside = (10 << 5) | 15

        shots._dragon_proximity(state, inside, outside)

        assert state.dragon_state == 0

    def test_a_kill_wakes_the_dragon_through_resolve_shot_hit(self):
        state = _make_state()
        SLOT = (12 << 5) | 12
        self._sleeping_dragon(state, (12 << 5) | 12)
        _place_monster(state, SLOT, MazeObjIds.MONST_GHOST, health_nibble=4)
        state.players[0].character = Character.WIZARD
        resolve_shot_hit(state, SLOT, 0)
        assert state.dragon_anim_ctr == 0x31

    def test_first_shot_at_a_stunned_dragon_clears_stun_before_damage(self):
        state = _make_state()
        head = (12 << 5) | 12
        _place_monster(state, head, MazeObjIds.MONST_DRAGON, health_nibble=8)
        state.dragon_seg_mob_ids[0] = head
        state.dragon_state = 0x02
        state.dragon_path_num = 0
        state.dragon_anim_ctr = 8

        resolve_shot_hit(state, head | 0x0800, 0)

        assert state.dragon_state == 0
        assert state.dragon_hits == 1


class TestPlayfieldShowscore:
    def test_it_claims_the_first_free_popup_channel(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.MONST_GHOST, x=160, y=160)
        shots._playfield_showscore(state, SLOT, 0)
        assert state.score_display_timer == [0x3C, 0, 0, 0]
        assert state.mobs.picture[0x11] == 0x1C88
        assert state.mobs.hpos[0x11] == ((160 << 7) & 0xFF80) + 5
        assert state.mobs.vpos[0x11] == ((native_v(160) << 7) & 0xFF80) + 0x400 + 0x10

    def test_a_busy_channel_is_skipped(self):
        state = _make_state()
        state.score_display_timer = [4, 0, 0, 0]
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.MONST_GHOST)
        shots._playfield_showscore(state, SLOT, 0)
        assert state.score_display_timer == [4, 0x3C, 0, 0]
        assert state.mobs.picture[0x11] == 0
        assert state.mobs.picture[0x12] == 0x1C88

    def test_all_four_busy_shows_nothing(self):
        state = _make_state()
        state.score_display_timer = [1, 1, 1, 1]
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.MONST_GHOST)
        shots._playfield_showscore(state, SLOT, 0)
        assert state.score_display_timer == [1, 1, 1, 1]
        assert all(state.mobs.picture[0x11 + i] == 0 for i in range(4))

    def test_the_bonus_family_uses_the_other_bias(self):
        """0x4956A: popup types 10 and up nudge by 1 and 8, not 5 and 0x10."""
        state = _make_state()
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.MONST_GHOST, x=160, y=160)
        shots._playfield_showscore(state, SLOT, 10)
        assert state.mobs.picture[0x11] == 0x25F6
        assert state.mobs.hpos[0x11] == ((160 << 7) & 0xFF80) + 1
        assert state.mobs.vpos[0x11] == ((native_v(160) << 7) & 0xFF80) + 0x400 + 8

    def test_the_popup_joins_the_depth_chain_at_the_source(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.MONST_GHOST)
        shots._playfield_showscore(state, SLOT, 0)
        assert state.mobs.depth_key[0x11] == SLOT

    def test_the_super_sorcerer_raises_one(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.MONST_SUPERSORC, palette=4)
        resolve_shot_hit(state, SLOT, 0)
        assert state.score_display_timer[0] == 0x3C
        assert state.mobs.picture[0x11] == 0x1C88

    def test_the_timer_ages_out_through_wp14(self):
        from gauntpy.subsystems.score import main_score_update
        state = _make_state()
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.MONST_GHOST)
        shots._playfield_showscore(state, SLOT, 0)
        for _ in range(0x3C):
            main_score_update(state)
        assert state.score_display_timer[0] == 0
        assert state.mobs.picture[0x11] == 0


class TestThiefShotDead:
    """The thief MOB carries PLAYERSTART, so 0x4B784 is its dispatch case.

    WP-10 owns the whole 0x4F5C8 removal transaction; these check the handoff
    and that ``shots.py`` keeps no copy of it.
    """

    def _place_thief(self, state: GameState, slot: int) -> None:
        _place_typed(state, slot, MazeObjIds.PLAYERSTART)

    def _deploy_thief(self, state: GameState, slot: int) -> None:
        self._place_thief(state, slot)
        state.thief_current_pos = slot
        state.thief_mob_slot = slot

    def test_the_kill_calls_the_thief_api_with_the_rom_arguments(self, monkeypatch):
        """0x4B7E8 pushes (d3, d4): the shooter, then the thief's MOB slot."""
        from gauntpy.subsystems import thief as thief_module
        calls = []
        monkeypatch.setattr(
            thief_module, "thief_remove_and_drop_loot",
            lambda *args: calls.append(args),
        )
        state = _make_state()
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert calls == [(state, 0, SLOT)]

    def test_shots_keeps_no_copy_of_the_removal(self):
        """The shim is gone: no duplicate bounty or dissolve lives here."""
        assert not hasattr(shots, "_thief_remove_and_drop_loot")
        assert not hasattr(shots, "_THIEF_KILL_SCORE")

    def test_shooting_the_thief_pays_the_500_bounty(self):
        """0x4F5EA: player_add_score_with_mult(shooter, 0x1F4)."""
        state = _make_state()
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        state.score_dirty = [0, 0, 0, 0]
        assert resolve_shot_hit(state, SLOT, 0) == -1
        assert state.players[0].score == 500
        assert state.score_dirty[0] == 1

    def test_the_bounty_takes_the_bonus_multiplier(self):
        state = _make_state()
        state.players[0].bonusmult = 3
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].score == 1500

    def test_the_bounty_is_paid_exactly_once(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].score == 500, "500 twice means duplicated logic"

    def test_the_thief_is_removed_and_dissolves(self):
        """0x4F650/0x4F656: tport_cycle_start then mob_free."""
        state = _make_state()
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        resolve_shot_hit(state, SLOT, 0)
        assert any(state.mobs.picture[s] for s in range(0x0D, 0x11))
        assert state.thief_current_pos == 0
        assert state.thief_mob_slot == 0

    def test_no_thief_on_the_level_dissolves_nothing(self):
        """0x4F64A only runs the dissolve for a deployed thief."""
        state = _make_state()
        SLOT = (9 << 5) | 9
        self._place_thief(state, SLOT)                 # tile, but no thief out
        resolve_shot_hit(state, SLOT, 0)
        assert not any(state.mobs.picture[s] for s in range(0x0D, 0x11))
        assert state.players[0].score == 500           # 0x4F5EA is unconditional

    def test_the_carried_item_is_dropped_where_the_thief_died(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        state.thief_item_carried = int(MazeObjIds.KEY)
        resolve_shot_hit(state, SLOT, 0)
        assert state.mobs.obj_type(SLOT) == int(MazeObjIds.KEY)

    def test_a_mugger_at_full_speed_is_killed_not_slowed(self):
        state = _make_state()
        state.thief_speed = 0x200
        state.thief_mode = 0x80                        # THIEF_IS_MUGGER
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        state.mugger_item_carried = int(MazeObjIds.FOOD_INVULN)
        resolve_shot_hit(state, SLOT, 0)
        assert state.players[0].score == 500
        assert state.mugger_item_carried == 0
        assert state.mobs.obj_type(SLOT) == int(MazeObjIds.FOOD_INVULN)

    def test_slowing_the_mugger_pays_nothing(self):
        """0x4B78C: an ordinary shot only slows a mugger that is up to speed."""
        state = _make_state()
        state.thief_speed = 0x180
        state.thief_mode = 0x80
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        resolve_shot_hit(state, SLOT, 0)
        assert state.thief_speed == 0x200
        assert state.players[0].score == 0
        assert state.thief_current_pos == SLOT

    def test_a_supershot_kills_the_mugger_outright(self):
        """0x4B7AC: a supershot skips the slow-down branch."""
        state = _make_state()
        state.players[0].supershot = 1
        state.thief_speed = 0x180
        state.thief_mode = 0x80
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        resolve_shot_hit(state, SLOT, 0)
        assert state.thief_speed == 0x180
        assert state.players[0].score == 500

    def test_a_monster_shot_pays_nobody(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        self._deploy_thief(state, SLOT)
        _arm_monster_shot(state, 4)
        resolve_shot_hit(state, SLOT, 4)
        assert all(p.score == 0 for p in state.players)
        assert state.thief_current_pos == SLOT


class TestPfReplace:
    def test_replacing_with_floor_clears_the_cell(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        state.maze = _FakeMaze(wallpattern=0)
        state.maze.data[(9, 9)] = int(MazeObjIds.WALL_DESTRUCTABLE)
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        shots._pf_replace(state, SLOT, int(MazeObjIds.TILE_FLOOR))
        assert state.mobs.picture[SLOT] == 0
        assert state.mobs.link[SLOT] == 0
        assert state.mobs.obj_type(SLOT) == int(MazeObjIds.TILE_FLOOR)
        assert state.maze.data[(9, 9)] == int(MazeObjIds.TILE_FLOOR)

    def test_replacing_with_a_marker_stamps_the_new_tile(self):
        state = _make_state()
        SLOT = (9 << 5) | 9
        state.maze = _FakeMaze(wallpattern=0)
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE)
        shots._pf_replace(state, SLOT, int(MazeObjIds.WALL_REGULAR))
        assert state.mobs.obj_type(SLOT) == int(MazeObjIds.WALL_REGULAR)
        assert state.mobs.picture[SLOT] != 0
        assert state.maze.data[(9, 9)] == int(MazeObjIds.WALL_REGULAR)

    def test_a_static_tile_marker_keeps_its_position(self):
        """0x5F37E: picture 0x8000/0x8001 loses picture and type only."""
        state = _make_state()
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE,
                     picture=0x8000, x=160, y=160)
        shots._pf_replace(state, SLOT, int(MazeObjIds.TILE_FLOOR))
        assert state.mobs.picture[SLOT] == 0
        assert state.mobs.link[SLOT] == 0
        assert state.mobs.hpos[SLOT] == 160 << 7
        assert state.mobs.vpos[SLOT] == native_v(160) << 7

    def test_an_empty_cell_is_left_alone(self):
        """0x5F362: a zero picture falls straight through."""
        state = _make_state()
        SLOT = (9 << 5) | 9
        state.mobs.hpos[SLOT] = 160 << 7
        shots._pf_replace(state, SLOT, int(MazeObjIds.TILE_FLOOR))
        assert state.mobs.hpos[SLOT] == 160 << 7


class TestWallDestroyPosition:
    def test_the_burst_lands_on_the_wall_that_was_destroyed(self):
        """0x53106 stamps floor without clearing H/V, so 0x4B70C's burst
        still knows where the wall was."""
        state = _make_state()
        state.maze = _FakeMaze(wallpattern=6)
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE,
                     picture=0x8000, x=160, y=160)
        assert resolve_shot_hit(state, SLOT, 0) == -1   # Warrior: damage 2
        state.mobs.picture[SLOT] = 0x8000               # re-arm for hit two
        assert resolve_shot_hit(state, SLOT, 0) == -1
        effects = [s for s in range(0x0D, 0x11) if state.mobs.picture[s]]
        assert effects
        assert hpos_x(state.mobs.hpos[effects[-1]]) == 160

    def test_lflag2_clears_all_four_mob_words(self):
        """0x5305C-0x53092 zeroes link, vpos, hpos and picture in that order."""
        state = _make_state()
        state.level_flags_2 = 0x80
        SLOT = (9 << 5) | 9
        state.maze = _FakeMaze(wallpattern=0)
        state.maze.data[(9, 9)] = int(MazeObjIds.WALL_DESTRUCTABLE)
        _place_typed(state, SLOT, MazeObjIds.WALL_DESTRUCTABLE,
                     picture=0x8000, x=160, y=160)
        assert wall_crumble(state, SLOT, 1) == -1
        assert state.mobs.link[SLOT] == 0
        assert state.mobs.vpos[SLOT] == 0
        assert state.mobs.hpos[SLOT] == 0
        assert state.mobs.picture[SLOT] == 0
        assert state.maze.data[(9, 9)] == int(MazeObjIds.TILE_FLOOR)


# =============================================================================
# Residual scan -- nothing in WP-7 is left as a stub or a stand-in
# =============================================================================

_STUB_MARKERS = (
    "TODO", "FIXME", "XXX",
    "no-op", "placeholder", "the port has no", "stand-in",
    "not modelled", "not implemented", "approximat", "deviation",
    "for now", "stays a stub",
)


def _shots_source() -> str:
    import inspect
    return inspect.getsource(shots)


class TestNoResidualStubs:
    @pytest.mark.parametrize("marker", _STUB_MARKERS)
    def test_the_module_carries_no_stub_marker(self, marker):
        source = _shots_source().lower()
        assert marker.lower() not in source, (
            f"{marker!r} still appears in shots.py"
        )

    def test_every_cross_subsystem_call_reaches_a_real_owner(self):
        """The shared ROM routines resolve_shot_hit calls are all wired."""
        from gauntpy.subsystems import potions, score, thief
        assert callable(score.dialog_first_encounter)
        assert callable(potions.potion_blast)
        assert callable(thief.thief_remove_and_drop_loot)
        source = _shots_source()
        assert "from .thief import thief_remove_and_drop_loot" in source
        assert "from .score import dialog_first_encounter" in source

    def test_no_helper_is_left_with_an_empty_body(self):
        """A bare docstring with no statements was the old hook shape."""
        import inspect
        import textwrap
        empty = []
        for name, obj in vars(shots).items():
            if not inspect.isfunction(obj) or obj.__module__ != shots.__name__:
                continue
            body = textwrap.dedent(inspect.getsource(obj)).splitlines()
            statements = [
                line for line in body[1:]
                if line.strip() and not line.strip().startswith(("#", '"', "'"))
            ]
            if not statements:
                empty.append(name)
        assert empty == [], f"stub functions remain: {empty}"


# =============================================================================
# Secret-room progress (WP-15's counter) raised from the exact WP-7 sites
# =============================================================================

from gauntpy.subsystems.exits import (            # noqa: E402
    TRICK_NOGETHIT,
    TRICK_NOHURTFRIENDS,
    TRICK_NOUSEINVUL,
    TRICK_WATCHSHOOT1,
    TRICK_WATCHSHOOT2,
)

_TASK_SHOOT_SECRET_A = 0x52
_TASK_SHOOT_SECRET_B = 0x5B
_TASK_SHOOT_TREASURE = 0x5A


class TestSecretWallTrick:
    """0x4B672/0x4B67E/0x4B68A -- watch what you shoot (secret walls)."""

    def _shoot_secret_wall(self, state: GameState, shooter_id: int = 0) -> None:
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.WALL_SECRET)
        state.rng = _FixedRandom([15])          # roll high: no prize spawned
        resolve_shot_hit(state, SLOT, shooter_id)

    @pytest.mark.parametrize("trick", [
        TRICK_WATCHSHOOT2, _TASK_SHOOT_SECRET_A, _TASK_SHOOT_SECRET_B,
    ])
    def test_all_three_tasks_bump_the_shooter(self, trick):
        state = _make_state()
        state.secret_trick_id = trick
        self._shoot_secret_wall(state)
        assert state.secret_tricks_flags[0] == 1
        assert state.secret_tricks_flags[1:] == [0, 0, 0]

    def test_the_bump_accumulates(self):
        state = _make_state()
        state.secret_trick_id = _TASK_SHOOT_SECRET_A
        state.secret_tricks_flags[0] = 4
        self._shoot_secret_wall(state)
        assert state.secret_tricks_flags[0] == 5

    def test_a_negative_byte_restarts_at_one(self):
        """0x4B69A: ``blt`` takes the ``move.b #1`` arm."""
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT2
        state.secret_tricks_flags[0] = 0x80
        self._shoot_secret_wall(state)
        assert state.secret_tricks_flags[0] == 1

    def test_another_task_is_untouched(self):
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT1     # foods, not walls
        self._shoot_secret_wall(state)
        assert state.secret_tricks_flags[0] == 0

    def test_a_monster_shot_credits_nobody(self):
        """0x4B66A: the whole tail is behind ``cmpi.w #4,d3``."""
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT2
        _arm_monster_shot(state, 4)
        self._shoot_secret_wall(state, shooter_id=4)
        assert state.secret_tricks_flags == [0, 0, 0, 0]


class TestSupershotTreasureTrick:
    """0x4B826 (treasure, task 0x5A) and 0x4B840 (invulnerable food)."""

    def _shoot(self, state: GameState, obj_type) -> None:
        SLOT = (9 << 5) | 9
        state.players[0].supershot = 1
        _place_typed(state, SLOT, obj_type)
        resolve_shot_hit(state, SLOT, 0)

    def test_task_5a_counts_treasure(self):
        state = _make_state()
        state.secret_trick_id = _TASK_SHOOT_TREASURE
        self._shoot(state, MazeObjIds.TREASURE)
        assert state.secret_tricks_flags[0] == 1

    def test_task_5a_ignores_the_invulnerable_food(self):
        state = _make_state()
        state.secret_trick_id = _TASK_SHOOT_TREASURE
        self._shoot(state, MazeObjIds.FOOD_INVULN)
        assert state.secret_tricks_flags[0] == 0

    def test_task_5a_has_no_negative_restart(self):
        """0x4B83A is a bare ``addq.b #1``, unlike the other progress sites."""
        state = _make_state()
        state.secret_trick_id = _TASK_SHOOT_TREASURE
        state.secret_tricks_flags[0] = 0x80
        self._shoot(state, MazeObjIds.TREASURE)
        assert state.secret_tricks_flags[0] == 0x81

    def test_watchshoot1_counts_the_invulnerable_food(self):
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT1
        self._shoot(state, MazeObjIds.FOOD_INVULN)
        assert state.secret_tricks_flags[0] == 1

    def test_watchshoot1_restarts_from_a_negative_byte(self):
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT1
        state.secret_tricks_flags[0] = 0xFF
        self._shoot(state, MazeObjIds.FOOD_INVULN)
        assert state.secret_tricks_flags[0] == 1

    def test_without_a_supershot_nothing_is_counted(self):
        """0x4B822: the handler leaves before any trick test."""
        state = _make_state()
        state.secret_trick_id = _TASK_SHOOT_TREASURE
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.TREASURE)
        resolve_shot_hit(state, SLOT, 0)
        assert state.secret_tricks_flags[0] == 0


class TestFoodTrick:
    """0x4B904 -- ordinary food is what TRICK_WATCHSHOOT1 really watches."""

    def _shoot_food(self, state: GameState, picture: int = 1,
                    shooter_id: int = 0) -> None:
        SLOT = (9 << 5) | 9
        _place_typed(state, SLOT, MazeObjIds.FOOD_DESTRUCTABLE, picture=picture)
        resolve_shot_hit(state, SLOT, shooter_id)

    def test_shooting_food_bumps_the_shooter(self):
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT1
        self._shoot_food(state)
        assert state.secret_tricks_flags[0] == 1

    def test_a_negative_byte_restarts_at_one(self):
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT1
        state.secret_tricks_flags[0] = 0x90
        self._shoot_food(state)
        assert state.secret_tricks_flags[0] == 1

    def test_the_slow_motion_food_is_not_counted(self):
        """0x4B8FC branches past the trick test to the poison dialog."""
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT1
        self._shoot_food(state, picture=shots._PIC_SLOWMO_FOOD)
        assert state.secret_tricks_flags[0] == 0
        assert state.monster_slowmo_timer

    def test_another_task_is_untouched(self):
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT2
        self._shoot_food(state)
        assert state.secret_tricks_flags[0] == 0

    def test_a_monster_shot_credits_nobody(self):
        state = _make_state()
        state.secret_trick_id = TRICK_WATCHSHOOT1
        _arm_monster_shot(state, 4)
        self._shoot_food(state, shooter_id=4)
        assert state.secret_tricks_flags == [0, 0, 0, 0]


class TestNoHurtFriendsTrick:
    """0x4B046 -- shooting another player fails the objective outright."""

    def _shoot_player(self, state: GameState, shooter_id: int = 0) -> None:
        _place_player_mob(state, 320, 1)
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 500
        resolve_shot_hit(state, 320, shooter_id)

    def test_it_is_a_set_not_a_bump(self):
        """0x4B052 is ``move.b #1``: any prior progress is overwritten."""
        state = _make_state()
        state.secret_trick_id = TRICK_NOHURTFRIENDS
        state.secret_tricks_flags[0] = 5
        self._shoot_player(state)
        assert state.secret_tricks_flags[0] == 1

    def test_it_marks_the_shooter_not_the_victim(self):
        state = _make_state()
        state.secret_trick_id = TRICK_NOHURTFRIENDS
        self._shoot_player(state)
        assert state.secret_tricks_flags[0] == 1
        assert state.secret_tricks_flags[1] == 0

    def test_it_fires_even_when_no_damage_lands(self):
        """0x4B046 sits before every LFLAG4 damage branch."""
        state = _make_state()
        state.level_flags_4 = 0
        state.secret_trick_id = TRICK_NOHURTFRIENDS
        self._shoot_player(state)
        assert state.players[1].health == 500
        assert state.secret_tricks_flags[0] == 1

    def test_another_task_is_untouched(self):
        state = _make_state()
        state.secret_trick_id = TRICK_NOGETHIT
        self._shoot_player(state)
        assert state.secret_tricks_flags[0] == 0

    def test_a_monster_shot_credits_nobody(self):
        """0x4B042 sends channels 4-11 down the monster-shot path instead."""
        state = _make_state()
        state.secret_trick_id = TRICK_NOHURTFRIENDS
        _arm_monster_shot(state, 4)
        self._shoot_player(state, shooter_id=4)
        assert state.secret_tricks_flags == [0, 0, 0, 0]


class TestNoGetHitTrick:
    """0x4B2A2 -- only the dragon's own fire counts against the victim."""

    def _hit_player(self, state: GameState, tier: int, shooter_id: int = 4):
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].health = 1000
        _place_player_mob(state, 321, 1)
        _arm_monster_shot(state, shooter_id, tier)
        resolve_shot_hit(state, 321, shooter_id)

    def test_dragon_fire_bumps_the_victim(self):
        state = _make_state()
        state.secret_trick_id = TRICK_NOGETHIT
        self._hit_player(state, tier=0x30, shooter_id=8)     # index >= 0x18
        assert state.secret_tricks_flags[1] == 1

    def test_it_accumulates(self):
        state = _make_state()
        state.secret_trick_id = TRICK_NOGETHIT
        state.secret_tricks_flags[1] = 2
        self._hit_player(state, tier=0x30, shooter_id=8)
        assert state.secret_tricks_flags[1] == 3

    def test_an_ordinary_monster_shot_does_not_count(self):
        """0x4B2B4's dialog branches skip the bump entirely."""
        state = _make_state()
        state.secret_trick_id = TRICK_NOGETHIT
        self._hit_player(state, tier=0)
        assert state.secret_tricks_flags[1] == 0

    def test_another_task_is_untouched(self):
        state = _make_state()
        state.secret_trick_id = TRICK_NOHURTFRIENDS
        self._hit_player(state, tier=0x30, shooter_id=8)
        assert state.secret_tricks_flags[1] == 0


class TestNoUseInvulTrick:
    """0x4B306 -- an acid-slowed victim loses the objective."""

    def test_the_acid_immune_victim_is_cleared(self):
        state = _make_state()
        state.secret_trick_id = TRICK_NOUSEINVUL
        state.secret_tricks_flags[1] = 3
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].acid_timer = 30
        _place_player_mob(state, 322, 1)
        _arm_monster_shot(state, 4)
        resolve_shot_hit(state, 322, 4)
        assert state.secret_tricks_flags[1] == 0

    def test_another_task_keeps_its_progress(self):
        state = _make_state()
        state.secret_trick_id = TRICK_NOGETHIT
        state.secret_tricks_flags[1] = 3
        state.players[1].status = int(PlayerStatus.ALIVE_HERE)
        state.players[1].acid_timer = 30
        _place_player_mob(state, 323, 1)
        _arm_monster_shot(state, 4)
        resolve_shot_hit(state, 323, 4)
        assert state.secret_tricks_flags[1] == 3


class TestTrickWiringUsesWp15:
    def test_shots_writes_the_counter_only_through_exits(self):
        import re
        writes = re.findall(
            r"state\.secret_tricks_flags\[[^\]]*\]\s*(?:[-+*|&^]?=)",
            _shots_source(),
        )
        assert writes == [], "a raw secret_tricks_flags write is left in shots.py"

    def test_the_only_direct_read_is_the_signed_byte_test(self):
        """0x4B696 ``tst.b`` has no WP-15 entry point, so it stays inline."""
        import inspect
        source = _shots_source()
        assert source.count("state.secret_tricks_flags[") == 1
        assert "state.secret_tricks_flags[player_index] & 0x80" in (
            inspect.getsource(shots._trick_bump)
        )

    def test_the_progress_helpers_delegate(self, monkeypatch):
        from gauntpy.subsystems import exits as exits_module
        calls = []
        monkeypatch.setattr(exits_module, "secret_trick_progress",
                            lambda *a: calls.append(("progress",) + a[1:]))
        monkeypatch.setattr(exits_module, "secret_trick_set",
                            lambda *a: calls.append(("set",) + a[1:]))
        state = _make_state()
        shots._trick_bump(state, 0, TRICK_WATCHSHOOT1)
        state.secret_tricks_flags[0] = 0x80
        shots._trick_bump(state, 0, TRICK_WATCHSHOOT1)
        shots._trick_set(state, 2, TRICK_NOUSEINVUL, 0)
        assert calls == [
            ("progress", 0, TRICK_WATCHSHOOT1),
            ("set", 0, TRICK_WATCHSHOOT1, 1),
            ("set", 2, TRICK_NOUSEINVUL, 0),
        ]
