"""WP-6 tests: player lifecycle, health, powers, and tile interaction.

Acceptance criteria (PLAN §6, WP-6 brief):
  1. main_health_countdown drains exactly one point per 64 frames, regardless
     of character class or difficulty (no per-class variance).
  2. player_tile_interact: food tile adds exactly 100 health; key tile
     increments player.keysnum.
  3. Forcefield damage table: all 8 character × armor combinations yield the
     documented values.
  4. Dying status sequence: DYING(0x04) → RESPAWN_WAIT(0x08) → REMOVED;
     when the last player is removed, show_continue_prompt is called.
  5. player_add_score_with_mult: adds base_score × bonusmult; does NOT call
     highscore_check.
  6. main_handle_death: a negative forcefield_hurt_timer plays sound 0x2E;
     when the countdown reaches 0, sound 0x2F plays.

Later sections cover the routines that used to be stubs or guesses, each
checked against ``row76.bin`` rather than the prose docs:
  11. player_lowhealth (0x487CA) -- latch, spacing timer, phrase selection.
  12. speech_welcome (0x48754) and the join finalizer.
  13. setup_infopanel / player_inv_update / show_continue_prompt /
      secret_name_entry_update.
  14. maze_convert_walls_to_exits (0x5E80C) and the escape timeout.
  15. player_tport (0x50224) and its three screening leaves.
  16. player_create_shot spawn picture and position (0x53666).
"""

from __future__ import annotations

from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus
from gauntpy.coords import hpos_x, native_v, vpos_y
from gauntpy.coords import decode_hpos, decode_vpos_at_y, slot_to_pixels
from gauntpy.state import GameState, Player
from gauntpy.subsystems import players as gp
from gauntpy.subsystems.sound import main_update_sound


# =============================================================================
# Helpers
# =============================================================================

def _active_state(game_mode: int = GameMode.NORMAL) -> GameState:
    """Return a GameState in normal gameplay with all players REMOVED."""
    return GameState(game_mode=game_mode)


def _make_player_active(state: GameState, player_index: int,
                        character: int = Character.WARRIOR,
                        health: int = 500,
                        mob_slot: int = 30) -> Player:
    """Put a player into ALIVE_HERE status.

    ``mob_slot`` is non-zero by default because main_health_countdown's drain
    gate at 0x46744 requires ``active_mob_ids[p] != 0``: a player with no MOB
    does not drain and does not run the heartbeat pass.
    """
    p = state.players[player_index]
    p.status = int(PlayerStatus.ALIVE_HERE)
    p.character = character
    p.health = health
    p.mob_slot = mob_slot
    return p


def _emitted(state: GameState) -> list[int]:
    """Every command the board has been given: the immediate sends plus
    whatever one more drain pass gets off the ring (§11.1-11.2)."""
    main_update_sound(state)
    return list(state.sound_log)


def _make_food_slot(state: GameState, destructable: bool = True,
                    poisoned: bool = False) -> int:
    """Insert a food MOB into slot 32 and return its slot number.

    Only PFOD001 is poisoned; ordinary FOOD000 and FOOD001-3 are good.
    """
    slot = 32
    obj_type = (int(MazeObjIds.FOOD_DESTRUCTABLE) if destructable
                else int(MazeObjIds.FOOD_INVULN))
    picture = (
        gp._POISONED_FOOD_PICTURE if poisoned
        else gp._WHOLESOME_FOOD_PICTURE
    )
    state.mobs.create(slot, tile=picture, hpos=0, vpos=0, obj_type=obj_type)
    return slot


def _make_key_slot(state: GameState) -> int:
    slot = 33
    state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                      obj_type=int(MazeObjIds.KEY))
    return slot


# =============================================================================
# 1. Health drain -- flat one-point-per-64-frames, no class variance (§4.3)
# =============================================================================

class TestMainHealthCountdown:

    def test_no_drain_on_non_gate_frame(self):
        """Health must not change on frames where frame_counter & 0x3F != 0."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        state.frame_counter = 1  # 1 & 0x3F = 1, not 0 -- no drain
        gp.main_health_countdown(state)
        assert p.health == 500

    def test_drains_exactly_one_point_on_gate_frame(self):
        """On frame_counter & 0x3F == 0 each active player loses exactly 1."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        state.frame_counter = 64  # 64 & 0x3F == 0
        gp.main_health_countdown(state)
        assert p.health == 499

    def test_drain_rate_is_class_independent(self):
        """Warrior, Valkyrie, Wizard, and Elf all lose the same 1 point."""
        for char in (Character.WARRIOR, Character.VALKYRIE,
                     Character.WIZARD, Character.ELF):
            state = _active_state()
            p = _make_player_active(state, 0, character=char, health=500)
            state.frame_counter = 0  # gate open
            gp.main_health_countdown(state)
            assert p.health == 499, \
                f"character {char!r} drained {500 - p.health} instead of 1"

    def test_only_active_players_drain(self):
        """REMOVED player must not lose health."""
        state = _active_state()
        # Player 0 active, player 1 REMOVED.
        _make_player_active(state, 0, health=500)
        state.players[1].health = 300  # REMOVED status (default)
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert state.players[0].health == 499
        assert state.players[1].health == 300, "REMOVED player must not drain"

    def test_health_is_32bit_longword_no_mask(self):
        """Health is a signed 32-bit longword; negatives are representable.

        The drain skips a player who is *exactly* at zero (0x46720 tests the
        longword, so it is an equality gate, not a floor): health that damage
        has already pushed negative keeps draining and never wraps.
        """
        state = _active_state()
        p = _make_player_active(state, 0, health=0)
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert p.health == 0, "0-health player must not drain further (0x46720)"

        p.health = -5           # e.g. an overshooting forcefield hit
        gp.main_health_countdown(state)
        assert p.health == -6, "negative health must survive unmasked"

    def test_drain_skipped_without_a_mob(self):
        """active_mob_ids[p] == 0 blocks the drain (0x46744)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500, mob_slot=0)
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert p.health == 500

    def test_drain_skipped_while_acid_slowed(self):
        """A non-zero acid_timer (0x905F40) blocks the drain (0x46754)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.acid_timer = 30
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert p.health == 500

    def test_drain_requires_status_exactly_alive_here(self):
        """0x46730 compares player_status against 1, not a bit test."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.status = int(PlayerStatus.ALIVE_NEXT)
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert p.health == 500

    def test_drain_marks_health_dirty(self):
        """Each drained point raises player_redraw bit 1 (0x4676A)."""
        state = _active_state()
        _make_player_active(state, 0, health=500)
        state.health_dirty[0] = 0
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert state.health_dirty[0] == 1

    def test_low_health_timer_increments_below_threshold(self):
        """Below 200 health the state_timer increments each frame (§4.3)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=100)
        p.state_timer = 0
        state.frame_counter = 1  # not a drain frame
        gp.main_health_countdown(state)
        assert p.state_timer == 1

    def test_low_health_timer_untouched_at_200_or_above(self):
        """main_health_countdown does *not* reset the timer at 200+ health.

        §4.3 says it does; the ROM's second pass simply skips the player at
        0x46B86.  The 0xFFFF write lives in player_resetcounters (0x433B4),
        coincheck (0x42C64) and the food branch of player_tile_interact
        (0x51D24) -- see TestFoodRearmsLowHealthWarning below.
        """
        state = _active_state()
        p = _make_player_active(state, 0, health=200)
        p.state_timer = 42
        state.frame_counter = 1
        gp.main_health_countdown(state)
        assert p.state_timer == 42

    def test_heartbeat_uses_rom_mask_table_and_per_player_sound(self):
        """0x576A8 gates 0x18 + player, not the spoken warning (0x46BC0)."""
        assert gp._HEARTBEAT_MASK_TABLE == [
            0x1F, 0x3F, 0x3F, 0x7F, 0x7F, 0xFF, 0xFF,
        ]
        assert gp._HEARTBEAT_SOUND_TABLE == [0x18, 0x19, 0x1A, 0x1B]

        state = _active_state()
        p = _make_player_active(state, 1, health=0x20)   # health >> 5 == 1
        p.state_timer = 0x3F        # +1 -> 0x40, 0x40 & 0x3F == 0 -> fires
        state.frame_counter = 1
        gp.main_health_countdown(state)
        assert 0x19 in state.sound_log

    def test_heartbeat_silent_between_pulses(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=0x20)
        p.state_timer = 0           # +1 -> 1, 1 & 0x3F != 0
        state.frame_counter = 1
        gp.main_health_countdown(state)
        assert state.sound_log == []

    def test_lowhealth_speech_fires_on_the_drain_tick(self):
        """player_lowhealth is called from the drain path, not the cadence.

        0x4677E shows the "insert coins for more health" box first (record 2),
        so the log carries that box's own speech/chime ahead of the warning.
        """
        state = _active_state()
        _make_player_active(state, 0, character=Character.WARRIOR, health=150)
        state.frame_counter = 0     # drain frame
        gp.main_health_countdown(state)
        # charname phrase then one of the four low-health phrases (0x48884/0x4889C)
        emitted = state.sound_log
        assert 0xBD in emitted
        assert any(p in emitted for p in gp._CHARACTER_LOWHEALTH_SPEECH)
        assert emitted.index(0xBD) < min(
            emitted.index(p) for p in gp._CHARACTER_LOWHEALTH_SPEECH if p in emitted
        )
        assert state.player_lowhealth_spoken[0] == 1
        # The ROM's drain loop finishes for all four players before the
        # per-frame loop runs, so the same frame already spends one tick of the
        # freshly loaded 0x708 (0x467D8).
        assert state.player_respawn_speech_timer[0] == 0x708 - 1

    def test_low_health_shows_the_insert_coins_box(self):
        """0x4677E: record 2 rides along with the spoken warning."""
        from gauntpy.subsystems.score import DIALOG_MESSAGES

        state = _active_state()
        _make_player_active(state, 0, health=150)
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert state.dialog_message == list(DIALOG_MESSAGES[2])
    def test_respawn_speech_timer_counts_down(self):
        """0x467C8-0x467D8 decrements the timer while it is non-negative."""
        state = _active_state()
        _make_player_active(state, 0, health=500)
        state.player_respawn_speech_timer[0] = 3
        state.frame_counter = 1
        gp.main_health_countdown(state)
        assert state.player_respawn_speech_timer[0] == 2
        state.player_respawn_speech_timer[0] = -1
        gp.main_health_countdown(state)
        assert state.player_respawn_speech_timer[0] == -1

    def test_drain_fires_every_64_frames(self):
        """Over 128 frames exactly two drain events occur."""
        state = _active_state()
        p = _make_player_active(state, 0, health=1000)
        for frame in range(1, 129):
            state.frame_counter = frame & 0xFFFF
            gp.main_health_countdown(state)
        # frame 64 and 128 are the gate frames
        assert p.health == 1000 - 2


# =============================================================================
# 2. Tile interaction: food and key (§4.6)
# =============================================================================

class TestPlayerTileInteract:

    def test_food_adds_100_health(self):
        """Food tile adds exactly 100 health (§4.6)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=300)
        slot = _make_food_slot(state, destructable=True)
        result = gp.player_tile_interact(state, slot, 0)
        assert result == -1, "food must return -1 (handled)"
        assert p.health == 400

    def test_food_plays_sound_0x0D(self):
        """Food tile plays sound 0x0D (§4.6)."""
        state = _active_state()
        _make_player_active(state, 0, health=100)
        slot = _make_food_slot(state)
        gp.player_tile_interact(state, slot, 0)
        _emitted(state)
        assert 0x0D in state.sound_log

    def test_destructable_food_is_removed_after_pickup(self):
        """FOOD_DESTRUCTABLE must be removed from the mob table."""
        state = _active_state()
        _make_player_active(state, 0, health=100)
        slot = _make_food_slot(state, destructable=True)
        gp.player_tile_interact(state, slot, 0)
        assert not state.mobs.is_occupied(slot)

    def test_invuln_food_is_removed_after_pickup(self):
        """Non-destructible food resists shots, but collect() still deletes it."""
        state = _active_state()
        _make_player_active(state, 0, health=100)
        slot = _make_food_slot(state, destructable=False)
        gp.player_tile_interact(state, slot, 0)
        assert not state.mobs.is_occupied(slot)

    def test_adaptive_food_uses_the_low_health_word_modulo_twenty(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=7)
        slot = _make_food_slot(state)
        state.mobs.picture[slot] = gp._RANDOM_FOOD_PICTURE

        gp.player_tile_interact(state, slot, 0)

        assert p.health == 207  # table[7] = 200
        assert state.score_display_timer[0] == 60
        assert state.mobs.picture[0x11] == 0x25FE

    def test_key_increments_keysnum(self):
        """Key tile increments player.keysnum (§4.6)."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.keysnum = 0
        slot = _make_key_slot(state)
        result = gp.player_tile_interact(state, slot, 0)
        assert result == -1
        assert p.keysnum == 1

    def test_key_plays_sound_0x13(self):
        """Key pickup plays sound 0x13 (§4.6)."""
        state = _active_state()
        _make_player_active(state, 0)
        slot = _make_key_slot(state)
        gp.player_tile_interact(state, slot, 0)
        _emitted(state)
        assert 0x13 in state.sound_log

    def test_key_is_removed_after_pickup(self):
        state = _active_state()
        _make_player_active(state, 0)
        slot = _make_key_slot(state)
        gp.player_tile_interact(state, slot, 0)
        assert not state.mobs.is_occupied(slot)

    def test_power_pickups_use_rom_bits_eight_through_thirteen(self):
        """``powerup_bit_masks`` (0x59B64) puts the six pickups at bits 8-13.

        Corrected twice: they are not bits 0-5 and not bits 6-11.  The mapping
        is pinned from both ends -- the tile jump table at 0x5122A routes each
        type to the arm that pushes its power-up ID, and the three timed powers
        are switched back off with a ``bclr`` on the word's *high* byte
        (0x4A80E/0x4A826/0x4A880).
        """
        from gauntpy.constants import PlayerPower

        expected = {
            MazeObjIds.POWER_INVIS: PlayerPower.INVIS,          # 0x0100
            MazeObjIds.POWER_REPULSE: PlayerPower.REPULSE,      # 0x0200
            MazeObjIds.POWER_REFLECT: PlayerPower.REFLECT,      # 0x0400
            MazeObjIds.POWER_TRANSPORT: PlayerPower.TRANSPORT,  # 0x0800
            MazeObjIds.POWER_SUPERSHOT: PlayerPower.SUPERSHOT,  # 0x1000
            MazeObjIds.POWER_INVULN: PlayerPower.INVULN,        # 0x2000
        }
        assert [int(m) for m in expected.values()] == [
            0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000,
        ]
        for obj_type, mask in expected.items():
            state = _active_state()
            player = _make_player_active(state, 0)
            player.powers = 0x003F          # every stat power already held
            slot = 35
            state.mobs.create(
                slot, tile=1, hpos=0, vpos=0, obj_type=int(obj_type),
            )

            gp.player_tile_interact(state, slot, 0)

            assert player.powers == 0x003F | int(mask)

    def test_the_mask_table_matches_the_rom_image(self):
        from gauntpy.constants import POWERUP_BIT_MASKS, POWERUP_ITEM_ID

        assert POWERUP_BIT_MASKS == (
            0x0002, 0x0001, 0x0020, 0x0010, 0x0008, 0x0004,
            0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000,
        )
        assert [POWERUP_ITEM_ID[int(t)] for t in (
            MazeObjIds.POWER_INVIS, MazeObjIds.POWER_REPULSE,
            MazeObjIds.POWER_REFLECT, MazeObjIds.POWER_TRANSPORT,
            MazeObjIds.POWER_SUPERSHOT, MazeObjIds.POWER_INVULN,
        )] == [6, 7, 8, 9, 10, 11]

    def test_stat_power_bits_are_unchanged(self):
        """The low six were never in dispute; two are ROM-confirmed."""
        from gauntpy.constants import PlayerPower

        assert int(PlayerPower.SPEED) == 0x01      # btst #0, 0x4A932
        assert int(PlayerPower.ARMOR) == 0x02      # btst #1, 0x4AA82
        assert int(PlayerPower.SHOTSPEED) == 0x08

    def test_an_already_owned_power_is_not_regranted(self):
        """0x4C762: player_give_item_with_message returns 0 and speaks nothing
        when the bit is already set."""
        from gauntpy.constants import PlayerPower

        state = _active_state()
        player = _make_player_active(state, 0)
        player.powers = int(PlayerPower.INVIS)
        slot = 36
        state.mobs.create(slot, tile=1, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POWER_INVIS))

        gp.player_tile_interact(state, slot, 0)

        assert player.powers == int(PlayerPower.INVIS)
        assert 0x8E not in state.sound_log, "no repeat announcement"

    def test_power_pickup_announces_and_chimes(self):
        """The grant speaks powerup_speech_ids[id] (0x59B7C) and the arm plays
        sound 0x26 (0x5187A), not 0x37."""
        state = _active_state()
        _make_player_active(state, 0)
        slot = 37
        state.mobs.create(slot, tile=1, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POWER_INVIS))

        gp.player_tile_interact(state, slot, 0)

        assert state.sound_log[:3] == [0xBD, 0x8D, 0x8E]
        assert 0x26 in state.sound_log
        assert 0x37 not in state.sound_log

    def test_reduced_text_speaks_only_the_power_name(self):
        state = _active_state()
        state.game_settings = 0x0400
        _make_player_active(state, 0)

        assert gp._player_give_item_id(state, 0, 6)

        assert state.sound_log == [0x8E]

    def test_speech_disable_suppresses_the_complete_power_announcement(self):
        state = _active_state()
        state.game_settings = 1 << 11
        _make_player_active(state, 0)

        assert gp._player_give_item_id(state, 0, 6)

        assert state.sound_log == []

    def test_supershot_pickup_adds_eleven_charges(self):
        """0x51874 ``addi.b #$b`` -- and it accumulates."""
        state = _active_state()
        player = _make_player_active(state, 0)
        for i in range(2):
            slot = 38 + i
            state.mobs.create(slot, tile=1, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.POWER_SUPERSHOT))
            gp.player_tile_interact(state, slot, 0)
        assert player.supershot == 22

    def test_timed_powers_arm_their_countdowns(self):
        state = _active_state()
        player = _make_player_active(state, 0, character=Character.VALKYRIE)
        for i, (obj_type, check) in enumerate((
            (MazeObjIds.POWER_INVIS,
             lambda: state.player_invis_timer[0] == 0x4B0),        # 0x517D4
            (MazeObjIds.POWER_REPULSE,
             lambda: state.player_repulse_timer[0] == 0x04B8),     # 0x5181A
            (MazeObjIds.POWER_INVULN,
             lambda: player.acid_timer == 0x384),                  # 0x5189E
        )):
            slot = 40 + i
            state.mobs.create(slot, tile=1, hpos=0, vpos=0,
                              obj_type=int(obj_type))
            gp.player_tile_interact(state, slot, 0)
            assert check(), f"{obj_type!r} did not arm its countdown"

    def test_zero_slot_returns_unhandled(self):
        """Slot 0 (NULL_SLOT) must return 0 without side-effects."""
        state = _active_state()
        _make_player_active(state, 0)
        result = gp.player_tile_interact(state, 0, 0)
        assert result == 0

    def test_treasure_adds_score(self):
        """Treasure tile adds score via player_add_score_with_mult (§4.6).

        Solo play, so the treasure arm's multiplier block leaves the value
        alone: no +2 (0x51A16) and 2 is exactly the ``2 x active`` cap.
        """
        state = _active_state()
        p = _make_player_active(state, 0)
        state.level_players_active = 1
        p.bonusmult = 2
        slot = 34
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        before = p.score
        gp.player_tile_interact(state, slot, 0)
        # 100 base score × multiplier 2 = 200
        assert p.score == before + 200

    def test_door_requires_key(self):
        """A door cannot be traversed without a key."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.keysnum = 0
        slot = 35
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        result = gp.player_tile_interact(state, slot, 0)
        assert result == 0, "door with no key must return 0 (unhandled)"
        assert state.mobs.is_occupied(slot), "door must not be removed"

    def test_door_consumed_with_key(self):
        """A door is consumed and the key is spent when the player has one."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.keysnum = 1
        slot = 35
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        result = gp.player_tile_interact(state, slot, 0)
        assert result == -1
        assert p.keysnum == 0
        assert not state.mobs.is_occupied(slot)


# =============================================================================
# 3. Forcefield damage table (§4.3 TRAP 4)
# =============================================================================

class TestForcefieldDamageTable:

    # Expected values: {Warrior:2, Valkyrie:2, Wizard:6, Elf:4} unarmored
    #                  {Warrior:1, Valkyrie:1, Wizard:5, Elf:3} with extra armor
    _EXPECTED = {
        (Character.WARRIOR,  False): 2,
        (Character.VALKYRIE, False): 2,
        (Character.WIZARD,   False): 6,
        (Character.ELF,      False): 4,
        (Character.WARRIOR,  True):  1,
        (Character.VALKYRIE, True):  1,
        (Character.WIZARD,   True):  5,
        (Character.ELF,      True):  3,
    }

    @staticmethod
    def _stand_on_forcefield(state: GameState, p) -> None:  # noqa: ANN001
        """Place the player on a beam between two forcefield hubs."""
        from gauntpy.constants import MazeObjIds
        from gauntpy.coords import encode_hpos, encode_vpos_at_y, pack_slot
        slot = pack_slot(5, 5)
        # The live record owns the cell it stands in.
        p.mob_slot = slot
        state.mobs.hpos[p.mob_slot] = encode_hpos(5 * 16)
        state.mobs.vpos[p.mob_slot] = encode_vpos_at_y(5 * 16)
        for hub in (pack_slot(5, 3), pack_slot(5, 7)):
            state.mobs.create(
                hub, tile=1, hpos=0, vpos=0,
                obj_type=MazeObjIds.FORCEFIELDHUB, state=0,
            )

    def test_all_combinations(self):
        """All 8 character × armor combinations yield the documented value."""
        for (char, armored), expected_dmg in self._EXPECTED.items():
            state = _active_state()
            state.forcefield_color = 1  # field is lit
            p = _make_player_active(state, 0, character=char, health=1000)
            p.powers = 0x02 if armored else 0x00
            self._stand_on_forcefield(state, p)
            initial = p.health
            # Single frame of contact, no drain this frame.
            state.frame_counter = 1
            gp.main_move_players(state)
            actual_dmg = initial - p.health
            assert actual_dmg == expected_dmg, (
                f"char={char!r} armored={armored}: "
                f"expected {expected_dmg} dmg, got {actual_dmg}"
            )

    def test_no_damage_when_field_blinked_off(self):
        """forcefield_color == 0 means the field is blinked off (§4.3 TRAP 5)."""
        state = _active_state()
        state.forcefield_color = 0  # blinked off
        p = _make_player_active(state, 0, character=Character.WIZARD,
                                health=1000)
        self._stand_on_forcefield(state, p)
        state.frame_counter = 1
        gp.main_move_players(state)
        assert p.health == 1000, "blinked-off field must deal no damage"

    def test_no_damage_when_not_touching_a_forcefield(self):
        """A lit field charges nothing to a player who isn't on one (contact gate)."""
        state = _active_state()
        state.forcefield_color = 1  # lit, but the player is nowhere near a field
        p = _make_player_active(state, 0, character=Character.WIZARD,
                                health=1000)
        state.frame_counter = 1
        gp.main_move_players(state)
        assert p.health == 1000, "lit field must not drain a player off the field"

    def test_forcefield_underflow_clamps_health_to_zero(self):
        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(
            state, 0, character=Character.WIZARD, health=2,
        )
        self._stand_on_forcefield(state, p)

        gp.main_move_players(state)

        assert p.health == 0

    def test_continuing_contact_refreshes_the_16_frame_timer(self):
        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000)
        self._stand_on_forcefield(state, p)
        state.forcefield_hurt_timer[0] = 7

        gp.main_move_players(state)

        assert state.forcefield_hurt_timer[0] == 0x10

    def test_unpaired_hub_does_not_hurt(self):
        from gauntpy.coords import encode_hpos, encode_vpos_at_y, pack_slot

        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000)
        p.mob_slot = 30
        state.mobs.hpos[p.mob_slot] = encode_hpos(5 * 16)
        state.mobs.vpos[p.mob_slot] = encode_vpos_at_y(5 * 16)
        state.mobs.create(
            pack_slot(5, 5), tile=1, hpos=0, vpos=0,
            obj_type=MazeObjIds.FORCEFIELDHUB,
        )

        gp.main_move_players(state)

        assert p.health == 1000

    def test_wall_breaks_forcefield_pair(self):
        from gauntpy.coords import pack_slot

        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000)
        self._stand_on_forcefield(state, p)
        state.mobs.create(
            pack_slot(5, 4), tile=0x8000, hpos=0, vpos=0,
            obj_type=MazeObjIds.WALL_REGULAR,
        )

        gp.main_move_players(state)

        assert p.health == 1000


# =============================================================================
# 4. Dying status sequence (§4.1)
# =============================================================================

class TestDyingStatusSequence:

    def _setup_dying(self, player_index: int = 0) -> GameState:
        state = _active_state()
        player = state.players[player_index]
        player.status = int(PlayerStatus.DYING)
        player.state_timer = 0
        return state

    def test_dying_is_a_countdown_not_a_count_up(self):
        """0x49E12-0x49E1E decrements player_state_timer once per frame."""
        state = self._setup_dying(0)
        p = state.players[0]
        p.state_timer = 3
        for expected in (2, 1):
            gp.main_move_players(state)
            assert p.state_timer == expected
            assert p.status == int(PlayerStatus.DYING)
        # 0x4A068 tests the countdown on the very frame it reaches zero, so the
        # dwell ends there rather than a frame later.
        gp.main_move_players(state)
        assert p.state_timer == 0
        assert p.status == int(PlayerStatus.RESPAWN_WAIT)

    def test_dying_transitions_to_respawn_wait(self):
        """An expired countdown ends status 0x04 (0x4A06C)."""
        state = self._setup_dying(0)
        gp.main_move_players(state)
        assert state.players[0].status == int(PlayerStatus.RESPAWN_WAIT), \
            "DYING must transition to RESPAWN_WAIT"

    def test_name_entry_and_game_over_reloads_are_the_rom_values(self):
        """highscore_check's two loads: 0x0A8C initials, 0x0258 GAME OVER."""
        assert gp._NAME_ENTRY_TIMEOUT == 0x0A8C
        assert gp._GAME_OVER_TIMEOUT == 0x0258

    def test_zero_health_unranked_player_is_removed(self):
        """An unranked zero-health player remains cleared after highscore_check.

        Regression: without this the player kept playing with negative health.
        """
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        state.level_players_active = 1
        p.health = 0
        gp.main_move_players(state)
        assert p.status == int(PlayerStatus.REMOVED)
        assert state.level_players_active == 0, "active count must decrement"

    def test_death_rearms_the_low_health_warning(self):
        """player_resetcounters/player_coindrop clear the latch and timer."""
        state = _active_state()
        p = _make_player_active(state, 0, health=0)
        state.player_lowhealth_spoken[0] = 1
        state.player_respawn_speech_timer[0] = 500
        gp.main_move_players(state)
        assert state.player_lowhealth_spoken[0] == 0
        assert state.player_respawn_speech_timer[0] == -1

    def test_negative_health_unranked_player_is_removed_and_clamped(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        state.level_players_active = 1
        p.health = -50            # e.g. a big forcefield/contact hit
        gp.main_move_players(state)
        assert p.status == int(PlayerStatus.REMOVED)
        assert p.health == 0, "health should clamp to 0 on death"

    def test_death_transition_plays_character_sfx(self):
        state = _active_state()
        p = _make_player_active(
            state, 0, character=Character.WIZARD, health=0,
        )
        state.level_players_active = 1

        gp.main_move_players(state)

        assert 0x16 in state.sound_log

    def test_respawn_wait_animation_runs_on_the_four_frame_cadence(self):
        """0x4A646-0x4A696: one animation step per four frames, 7 down to 4."""
        state = _active_state()
        p = state.players[0]
        p.status = int(PlayerStatus.RESPAWN_WAIT)
        p.character = int(Character.WARRIOR)
        p.mob_slot = 30
        p.anim_counter = 0
        state.player_death_anim_frame[0] = 7

        for _ in range(4):
            gp.main_move_players(state)
        assert state.player_death_anim_frame[0] == 6
        assert state.mobs.picture[30] == gp._ANIM_TABLE_IDLE[6]

        for _ in range(8):
            gp.main_move_players(state)
        assert state.player_death_anim_frame[0] == 4
        assert p.status == int(PlayerStatus.RESPAWN_WAIT)

    def test_respawn_wait_transitions_to_removed(self):
        """After RESPAWN_WAIT threshold, player becomes REMOVED (0x00)."""
        state = _active_state()
        p = state.players[0]
        p.status = int(PlayerStatus.RESPAWN_WAIT)
        p.anim_counter = 0
        state.player_death_anim_frame[0] = 4    # animation already finished
        for _ in range(gp._RESPAWN_WAIT_LIMIT + 1):
            gp.main_move_players(state)
        assert p.status == int(PlayerStatus.REMOVED)

    def test_removal_clears_the_it_player(self):
        """0x4A6D6: removing the IT player resets 0x9049DC to 0xFFFF."""
        state = _active_state()
        p = state.players[0]
        p.status = int(PlayerStatus.RESPAWN_WAIT)
        p.anim_counter = 0
        state.player_death_anim_frame[0] = 4
        state.player_it = 0
        for _ in range(gp._RESPAWN_WAIT_LIMIT + 1):
            gp.main_move_players(state)
        assert state.player_it == 0xFFFF

    def test_show_continue_prompt_called_when_last_player_removed(self):
        """show_continue_prompt must be called when no players remain (§4.1)."""
        called = []
        original = gp.show_continue_prompt

        def _mock(st: GameState) -> None:
            called.append(True)

        gp.show_continue_prompt = _mock
        try:
            state = _active_state()
            p = state.players[0]
            p.status = int(PlayerStatus.RESPAWN_WAIT)
            state.player_death_anim_frame[0] = 4
            p.anim_counter = gp._RESPAWN_WAIT_LIMIT - 1  # one frame before removal
            gp.main_move_players(state)
            assert called, "show_continue_prompt must fire when last player removed"
        finally:
            gp.show_continue_prompt = original

    def test_show_continue_not_called_when_other_players_active(self):
        """show_continue_prompt must NOT fire if another player is still active."""
        called = []
        original = gp.show_continue_prompt

        def _mock(st: GameState) -> None:
            called.append(True)

        gp.show_continue_prompt = _mock
        try:
            state = _active_state()
            # Player 0 near removal, player 1 still active.
            state.players[0].status = int(PlayerStatus.RESPAWN_WAIT)
            state.player_death_anim_frame[0] = 4
            state.players[0].anim_counter = gp._RESPAWN_WAIT_LIMIT - 1
            _make_player_active(state, 1, health=500)
            gp.main_move_players(state)
            assert not called, "must NOT call show_continue_prompt while player 1 is alive"
        finally:
            gp.show_continue_prompt = original

    def test_full_lifecycle_dying_to_removed(self):
        """Full DYING → RESPAWN_WAIT → REMOVED sequence without error."""
        state = self._setup_dying(0)
        for _ in range(200):
            gp.main_move_players(state)
        assert state.players[0].status == int(PlayerStatus.REMOVED)


# =============================================================================
# 5. player_add_score_with_mult (§4.7)
# =============================================================================

class TestPlayerAddScoreWithMult:

    def test_adds_base_score_times_multiplier(self):
        """Total added = base_score × player.bonusmult (§4.7)."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score = 0
        p.bonusmult = 3
        gp.player_add_score_with_mult(state, 0, 100)
        assert p.score == 300

    def test_multiplier_one_adds_base_score(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score = 500
        p.bonusmult = 1
        gp.player_add_score_with_mult(state, 0, 250)
        assert p.score == 750

    def test_accumulates_across_calls(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score = 0
        p.bonusmult = 2
        gp.player_add_score_with_mult(state, 0, 100)
        gp.player_add_score_with_mult(state, 0, 50)
        assert p.score == 300

    def test_does_not_call_highscore_check(self):
        """Contradicted: highscore_check is NOT called (§4.7)."""
        # If highscore_check existed and raised, this test would catch it.
        # We verify the function completes cleanly for a very large score.
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score = 0
        p.bonusmult = 9
        gp.player_add_score_with_mult(state, 0, 999999)
        assert p.score == 9 * 999999  # 8,999,991

    def test_score_is_32bit_no_truncation(self):
        """Score is a 32-bit longword; no masking (§4.3 TRAP 2 parallel)."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score = 0xFFFF0000
        p.bonusmult = 1
        gp.player_add_score_with_mult(state, 0, 0x10000)
        # Must exceed 32-bit unsigned range -- Python ints do not overflow.
        assert p.score == 0xFFFF0000 + 0x10000


# =============================================================================
# 6. main_handle_death -- looping sound timers (§21)
# =============================================================================

class TestMainHandleDeath:

    def test_negative_forcefield_timer_plays_0x2E(self):
        """A negative forcefield_hurt_timer → sound 0x2E (§21)."""
        state = _active_state()
        state.forcefield_hurt_timer[0] = -30
        gp.main_handle_death(state)
        _emitted(state)
        assert 0x2E in state.sound_log, \
            "negative forcefield_hurt_timer must play sound 0x2E"

    def test_negative_forcefield_timer_negated_after_start_sound(self):
        """Timer flips positive so the countdown begins (§21)."""
        state = _active_state()
        state.forcefield_hurt_timer[0] = -30
        gp.main_handle_death(state)
        assert state.forcefield_hurt_timer[0] == 30

    def test_forcefield_timer_counts_down(self):
        """Positive timer decrements by 1 per frame (§21)."""
        state = _active_state()
        state.forcefield_hurt_timer[0] = 10
        gp.main_handle_death(state)
        assert state.forcefield_hurt_timer[0] == 9

    def test_forcefield_timer_zero_plays_0x2F(self):
        """When the forcefield countdown reaches 0, sound 0x2F plays (§21)."""
        state = _active_state()
        state.forcefield_hurt_timer[0] = 1  # one step from zero
        gp.main_handle_death(state)
        _emitted(state)
        assert 0x2F in state.sound_log, \
            "forcefield timer reaching 0 must play sound 0x2F"
        assert state.forcefield_hurt_timer[0] == 0

    def test_zero_forcefield_timer_plays_no_sound(self):
        """A timer already at 0 (no contact) plays nothing."""
        state = _active_state()
        state.forcefield_hurt_timer[0] = 0
        gp.main_handle_death(state)
        _emitted(state)
        assert 0x2E not in state.sound_log
        assert 0x2F not in state.sound_log

    def test_negative_death_touch_timer_plays_0x20(self):
        """A negative death_touch_timer → sound 0x20 (§21)."""
        state = _active_state()
        state.death_touch_timer[0] = -20
        gp.main_handle_death(state)
        _emitted(state)
        assert 0x20 in state.sound_log

    def test_death_touch_timer_zero_plays_0x21(self):
        """death_touch_timer countdown reaching 0 plays sound 0x21 (§21)."""
        state = _active_state()
        state.death_touch_timer[0] = 1
        gp.main_handle_death(state)
        _emitted(state)
        assert 0x21 in state.sound_log

    def test_all_four_players_handled_independently(self):
        """All four player slots are processed in a single call (§21)."""
        state = _active_state()
        for i in range(4):
            state.forcefield_hurt_timer[i] = -5
        gp.main_handle_death(state)
        for i in range(4):
            assert state.forcefield_hurt_timer[i] == 5, \
                f"player {i} timer should have been negated"
        _emitted(state)
        # One 0x2E per player = four occurrences.
        assert state.sound_log.count(0x2E) == 4


# =============================================================================
# 7. player_damage_sample_update (§4.3 TRAP 3)
# =============================================================================

class TestPlayerDamageSampleUpdate:

    def test_timer_decrements_each_call(self):
        """damage_sample_timer decrements by 1 per call before expiry."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.damage_sample_timer = 10
        gp.player_damage_sample_update(state, 0)
        assert p.damage_sample_timer == 9

    def test_timer_reloads_at_60_on_expiry(self):
        """At window expiry the timer reloads to 60 (§4.3)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.damage_sample_timer = 1
        gp.player_damage_sample_update(state, 0)
        assert p.damage_sample_timer == 60

    def test_pending_damage_above_20_accumulates(self):
        """pending_damage > 20 is added to cumulative_damage at expiry (§4.3)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.damage_sample_timer = 1
        p.pending_damage = 50
        p.cumulative_damage = 0
        gp.player_damage_sample_update(state, 0)
        assert p.cumulative_damage == 50

    def test_pending_damage_at_or_below_20_not_accumulated(self):
        """pending_damage ≤ 20 is ignored (below threshold, §4.3)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.damage_sample_timer = 1
        p.pending_damage = 20
        p.cumulative_damage = 0
        gp.player_damage_sample_update(state, 0)
        assert p.cumulative_damage == 0

    def test_cumulative_damage_saturates_at_0x7D00(self):
        """cumulative_damage saturates at 0x7D00 (§4.3)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.damage_sample_timer = 1
        p.pending_damage = 9999
        p.cumulative_damage = 0x7C00
        gp.player_damage_sample_update(state, 0)
        assert p.cumulative_damage == 0x7D00

    def test_pending_damage_cleared_on_expiry(self):
        """pending_damage is reset to 0 after the window expires (§4.3)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.damage_sample_timer = 1
        p.pending_damage = 100
        gp.player_damage_sample_update(state, 0)
        assert p.pending_damage == 0


# =============================================================================
# 8. player_join helpers (§4.4)
# =============================================================================

class TestPlayerJoin:

    def test_join_without_maze_does_nothing(self):
        """player_join with maze=None leaves status REMOVED (§4.4)."""
        state = _active_state()
        assert state.maze is None
        gp.player_join(state, 0)
        assert state.players[0].status == int(PlayerStatus.REMOVED)

    def test_join_with_spawn_tile_sets_alive(self):
        """player_join sets status ALIVE_HERE when a spawn tile exists (§4.4)."""
        state = _active_state()
        # Provide a dummy maze object so player_start_inner doesn't bail early.
        state.maze = object()
        # Put a PLAYERSTART in the mob table.
        state.mobs.create(50, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.PLAYERSTART))
        gp.player_join(state, 0)
        assert state.players[0].status == int(PlayerStatus.ALIVE_HERE)


# =============================================================================
# 9. player_tile_interact with score multiplier
# =============================================================================

class TestScoreMultiplierInTileInteract:

    def test_treasure_score_uses_bonusmult(self):
        """Treasure pickup score is multiplied by bonusmult (§4.6 + §4.7).

        The multiplier is capped at ``2 x level_players_active`` by the arm
        itself (0x51A48), so a solo run can only ever score at x2.
        """
        state = _active_state()
        p = _make_player_active(state, 0)
        state.level_players_active = 1
        p.bonusmult = 5           # above the solo cap
        p.score = 0
        slot = 40
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        gp.player_tile_interact(state, slot, 0)
        assert p.bonusmult == 2   # clamped to 2 x 1
        assert p.score == 200     # 100 base × the clamped 2


# =============================================================================
# 10. open_timed_doors
# =============================================================================

class TestOpenTimedDoors:

    def test_removes_horizontal_doors(self):
        state = _active_state()
        slot = 36
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        gp.open_timed_doors(state)
        assert not state.mobs.is_occupied(slot)

    def test_removes_vertical_doors(self):
        state = _active_state()
        slot = 37
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_VERT))
        gp.open_timed_doors(state)
        assert not state.mobs.is_occupied(slot)

    def test_plays_sound_0x12_only_when_a_door_was_removed(self):
        """0x47FF0 gates the "Doors Open" command on the removed flag."""
        state = _active_state()
        gp.open_timed_doors(state)
        _emitted(state)
        assert 0x12 not in state.sound_log, \
            "no doors on the level means no sound (0x47FF0)"

        state = _active_state()
        state.mobs.create(39, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_VERT))
        gp.open_timed_doors(state)
        _emitted(state)
        assert 0x12 in state.sound_log

    def test_non_door_mobs_are_not_removed(self):
        state = _active_state()
        slot = 38
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.FOOD_DESTRUCTABLE))
        gp.open_timed_doors(state)
        assert state.mobs.is_occupied(slot), \
            "open_timed_doors must only remove DOOR_HORIZ/VERT"


# =============================================================================
# 11. player_lowhealth (0x487CA) -- latch, spacing timer, phrase selection
# =============================================================================

class TestPlayerLowHealth:

    def test_speaks_charname_then_phrase(self):
        """Two speech commands: charname (0x596F6) then phrase (0x5797A)."""
        state = _active_state()
        _make_player_active(state, 2, character=Character.ELF, health=50)
        gp.player_lowhealth(state, 2)
        # index = character + player * 4 = 3 + 8 = 11 -> 0xC8
        assert state.sound_log[0] == 0xC8
        assert state.sound_log[1] in gp._CHARACTER_LOWHEALTH_SPEECH

    def test_latch_makes_it_one_shot(self):
        state = _active_state()
        _make_player_active(state, 0, health=50)
        gp.player_lowhealth(state, 0)
        assert state.player_lowhealth_spoken[0] == 1
        state.sound_log.clear()
        gp.player_lowhealth(state, 0)
        assert state.sound_log == [], "latch must suppress the repeat (0x487DE)"

    def test_non_negative_speech_timer_blocks(self):
        """0x487F0: the routine only speaks while the timer is negative."""
        state = _active_state()
        _make_player_active(state, 0, health=50)
        state.player_respawn_speech_timer[0] = 0
        gp.player_lowhealth(state, 0)
        assert state.sound_log == []
        assert state.player_lowhealth_spoken[0] == 0

    def test_operator_speech_disable_keeps_state_but_silences_both_phrases(self):
        state = _active_state()
        state.game_settings = 1 << 11
        _make_player_active(state, 0, health=100)

        gp.player_lowhealth(state, 0)

        assert state.sound_log == []
        assert state.player_lowhealth_spoken[0] == 1
        assert state.player_respawn_speech_timer[0] == 0x708

    def test_reloads_the_speech_timer(self):
        state = _active_state()
        _make_player_active(state, 0, health=50)
        gp.player_lowhealth(state, 0)
        assert state.player_respawn_speech_timer[0] == 0x708

    def test_powers_phrase_needs_two_bits_and_the_random_gate(self):
        """Entry 3 requires powers & 0xFF, getrandom(8) > 3 and >1 bit set."""
        # A single power bit can never reach entry 3 (0x4884A subtracts one).
        for seed in range(24):
            state = GameState(game_mode=GameMode.NORMAL)
            state.rng.seed = seed
            p = _make_player_active(state, 0, health=50)
            p.powers = 0x01                     # exactly one low bit
            gp.player_lowhealth(state, 0)
            assert state.sound_log[1] != gp._CHARACTER_LOWHEALTH_SPEECH[3]

    def test_powers_phrase_is_reachable_with_two_bits(self):
        """With two low power bits some seed must reach entry 3."""
        reached = False
        for seed in range(64):
            state = GameState(game_mode=GameMode.NORMAL)
            state.rng.seed = seed
            p = _make_player_active(state, 0, health=50)
            p.powers = 0x03                     # speed + armour
            gp.player_lowhealth(state, 0)
            if state.sound_log[1] == gp._CHARACTER_LOWHEALTH_SPEECH[3]:
                reached = True
                break
        assert reached, "entry 3 must be reachable through the powers branch"

    def test_high_powers_bits_do_not_count(self):
        """0x4880A masks with 0x00FF, so bits 8-11 cannot open the branch."""
        for seed in range(24):
            state = GameState(game_mode=GameMode.NORMAL)
            state.rng.seed = seed
            p = _make_player_active(state, 0, health=50)
            p.powers = 0x0F00                   # reflect/transport/super/invuln
            gp.player_lowhealth(state, 0)
            assert state.sound_log[1] != gp._CHARACTER_LOWHEALTH_SPEECH[3]


class TestFoodRearmsLowHealthWarning:

    def test_food_back_to_200_disables_the_cadence_and_clears_the_latch(self):
        """0x51D06-0x51D32, the real home of §4.3's "reset to 0xFFFF"."""
        state = _active_state()
        p = _make_player_active(state, 0, health=150)
        p.state_timer = 42
        state.player_lowhealth_spoken[0] = 1
        slot = _make_food_slot(state, destructable=True)
        gp.player_tile_interact(state, slot, 0)
        assert p.health == 250
        assert p.state_timer == 0xFFFF
        assert state.player_lowhealth_spoken[0] == 0
        assert state.health_dirty[0] == 1

    def test_food_that_does_not_reach_200_leaves_the_warning_armed(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=50)
        p.state_timer = 42
        state.player_lowhealth_spoken[0] = 1
        slot = _make_food_slot(state, destructable=True)
        gp.player_tile_interact(state, slot, 0)
        assert p.health == 150
        assert p.state_timer == 42
        assert state.player_lowhealth_spoken[0] == 1


# =============================================================================
# 12. speech_welcome (0x48754)
# =============================================================================

class TestSpeechWelcome:

    def test_leadin_only_when_solo_and_below_the_delay(self):
        """level_players_active == 1 speaks 0x59 but stops before the name."""
        state = _active_state()
        state.level_players_active = 1
        state.welcome_elapsed_frames = 0
        gp.speech_welcome(state, 0)
        assert state.sound_log == [gp._SPEECH_WELCOME_LEADIN]

    def test_silent_when_not_solo_and_below_the_delay(self):
        state = _active_state()
        state.level_players_active = 2
        state.welcome_elapsed_frames = 0
        gp.speech_welcome(state, 0)
        assert state.sound_log == []

    def test_full_greeting_above_the_delay(self):
        """Lead-in then speech_charname_tbl[character + player * 4]."""
        state = _active_state()
        state.level_players_active = 3
        state.welcome_elapsed_frames = 0x258
        state.players[1].character = int(Character.WIZARD)
        gp.speech_welcome(state, 1)
        # index = 2 + 1 * 4 = 6 -> 0xC3
        assert state.sound_log == [gp._SPEECH_WELCOME_LEADIN, 0xC3]

    def test_reloads_the_elapsed_counter(self):
        state = _active_state()
        state.welcome_elapsed_frames = 5000
        gp.speech_welcome(state, 0)
        assert state.welcome_elapsed_frames == 0x258

    def test_operator_speech_disable_silences_welcome(self):
        state = _active_state()
        state.game_settings = 1 << 11
        state.level_players_active = 1
        state.welcome_elapsed_frames = 0x258

        gp.speech_welcome(state, 0)

        assert state.sound_log == []

    def test_join_finalize_greets_and_rearms_the_low_health_warning(self):
        from gauntpy.subsystems.score import info_panel

        state = _active_state()
        state.level_players_active = 1
        state.player_lowhealth_spoken[0] = 1
        state.player_respawn_speech_timer[0] = 900
        state.players[0].health = 700
        gp.player_join_finalize(state, 0)
        assert state.players[0].status == int(PlayerStatus.ALIVE_HERE)
        assert state.players[0].state_timer == 0xFFFF
        assert state.player_lowhealth_spoken[0] == 0
        assert state.player_respawn_speech_timer[0] == -1
        assert gp._SPEECH_WELCOME_LEADIN in state.sound_log
        # setup_infopanel rebuilds the joining player's column at once.
        field = info_panel(state).players[0]
        assert field.score_drawn and field.health_drawn
        assert field.health == 700

    def test_join_finalize_plays_the_character_join_sound_before_welcome(self):
        state = _active_state()
        state.level_players_active = 1
        state.players[0].character = int(Character.ELF)

        gp.player_join_finalize(state, 0)

        assert state.sound_log[:2] == [0x0C, gp._SPEECH_WELCOME_LEADIN]


# =============================================================================
# 13. Cross-package hooks: HUD, inventory, continue prompt, secret name entry
# =============================================================================

class TestHudHooks:
    """setup_infopanel/player_inv_update drive WP-14's real InfoPanel latch
    (``state.info_panel``), not a local flag of their own."""

    @staticmethod
    def _field(state: GameState, player_index: int):
        from gauntpy.subsystems.score import info_panel

        return info_panel(state).players[player_index]

    def test_setup_infopanel_draws_one_player(self):
        state = _active_state()
        p = _make_player_active(state, 2, health=321)
        p.score = 4242
        state.score_dirty = [1, 1, 1, 1]
        state.health_dirty = [1, 1, 1, 1]

        gp.setup_infopanel(state, 2)

        field = self._field(state, 2)
        assert field.score_drawn and field.health_drawn
        assert field.score == 4242
        assert field.health == 321
        # The draw the redraw bits were asking for has just happened.
        assert state.score_dirty == [1, 1, 0, 1]
        assert state.health_dirty == [1, 1, 0, 1]
        assert not self._field(state, 0).score_drawn

    def test_setup_infopanel_minus_one_rebuilds_the_whole_panel(self):
        state = _active_state()
        for i in range(4):
            _make_player_active(state, i, health=100 + i)
        state.score_dirty = [1, 1, 1, 1]
        state.health_dirty = [1, 1, 1, 1]

        gp.setup_infopanel(state, -1)

        for i in range(4):
            field = self._field(state, i)
            assert field.score_drawn and field.health_drawn
            assert field.health == 100 + i
        assert state.score_dirty == [0, 0, 0, 0]
        assert state.health_dirty == [0, 0, 0, 0]

    def test_it_label_uses_the_rom_white_attribute_family(self):
        from gauntpy.subsystems import score

        state = _active_state()
        _make_player_active(state, 2, health=100)
        state.player_it = 2

        gp.setup_infopanel(state, 2)

        row = 2 * score.PLAYER_BLOCK_STRIDE + score.PLAYER_LABEL_ROW
        words = state.alpha_ram[
            row * score.ALPHA_ROW_STRIDE + score.IT_LABEL_COLUMN:
            row * score.ALPHA_ROW_STRIDE + score.IT_LABEL_COLUMN + 2
        ]
        assert [word & 0xFC00 for word in words] == [0xB800, 0xB800]

    def test_panel_bottom_contains_no_host_diagnostics(self):
        from gauntpy.subsystems import score

        state = _active_state()
        player = _make_player_active(state, 0, health=100, mob_slot=(10 << 5) | 12)
        state.mazenum_current = 19
        state.mobs.hpos[player.mob_slot] = 188 << 7
        state.mobs.vpos[player.mob_slot] = native_v(160) << 7

        gp.setup_infopanel(state, -1)

        for row in (27, 28):
            start = row * score.ALPHA_ROW_STRIDE + score.PANEL_COLUMN
            words = state.alpha_ram[start:start + score.PANEL_WIDTH]
            assert all(word & 0x03FF == 0 for word in words)

    def test_setup_infopanel_ignores_an_out_of_range_selector(self):
        state = _active_state()
        gp.setup_infopanel(state, 9)
        assert not self._field(state, 0).score_drawn

    def test_player_inv_update_relatches_the_panel_row(self):
        state = _active_state()
        p = _make_player_active(state, 1, health=250)
        p.bonusmult = 4

        gp.player_inv_update(state, 1)

        field = self._field(state, 1)
        assert field.health_drawn
        assert field.health == 250
        assert field.bonusmult == 4

    def test_key_pickup_refreshes_the_panel_immediately(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=175)
        slot = _make_key_slot(state)

        gp.player_tile_interact(state, slot, 0)

        assert p.keysnum == 1
        assert self._field(state, 0).health_drawn, (
            "a pickup must re-latch the panel row, not wait four frames"
        )

    def test_potion_pickup_refreshes_the_panel(self):
        state = _active_state()
        p = _make_player_active(state, 3, health=175)
        slot = 44
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POT_DESTRUCTABLE))

        gp.player_tile_interact(state, slot, 3)

        assert p.potionsnum == 1
        assert self._field(state, 3).health_drawn
        assert 0x26 in state.sound_log
        assert 0x0E not in state.sound_log

    def test_overfull_player_cannot_pick_up_a_potion(self):
        for obj_type in (MazeObjIds.POT_DESTRUCTABLE, MazeObjIds.POT_INVULN):
            state = _active_state()
            player = _make_player_active(state, 0, health=175)
            player.keysnum = 5
            player.potionsnum = 11
            slot = 44
            state.mobs.create(
                slot, tile=0x1234, hpos=0, vpos=0, obj_type=int(obj_type),
            )

            assert gp.player_tile_interact(state, slot, 0) == 0

            assert (player.keysnum, player.potionsnum) == (5, 11)
            assert state.mobs.obj_type(slot) == int(obj_type)

    def test_overfull_player_cannot_pick_up_a_key(self):
        state = _active_state()
        player = _make_player_active(state, 0, health=175)
        player.keysnum = 5
        player.potionsnum = 11
        slot = _make_key_slot(state)

        assert gp.player_tile_interact(state, slot, 0) == 0

        assert (player.keysnum, player.potionsnum) == (5, 11)
        assert state.mobs.obj_type(slot) == int(MazeObjIds.KEY)

    def test_power_up_pickup_refreshes_the_panel(self):
        state = _active_state()
        _make_player_active(state, 0, health=175)
        slot = 45
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POWER_INVULN))

        gp.player_tile_interact(state, slot, 0)

        assert self._field(state, 0).health_drawn


class TestRedrawBitsOnEveryValueChange:
    """``player_redraw`` (0x904908): bit 0 score, bit 1 health.  Every value
    write in this module raises the matching bit so WP-14 repaints."""

    def test_food_raises_the_health_bit(self):
        state = _active_state()
        _make_player_active(state, 0, health=300)
        state.health_dirty = [0, 0, 0, 0]
        gp.player_tile_interact(state, _make_food_slot(state), 0)
        assert state.health_dirty[0] == 1

    def test_health_drain_raises_the_health_bit(self):
        state = _active_state()
        _make_player_active(state, 0, health=300)
        state.health_dirty = [0, 0, 0, 0]
        state.frame_counter = 0
        gp.main_health_countdown(state)
        assert state.health_dirty[0] == 1

    def test_forcefield_damage_raises_the_health_bit(self):
        from gauntpy.coords import pack_slot

        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000, mob_slot=pack_slot(5, 5))
        state.mobs.hpos[p.mob_slot] = (5 * 16) << 7
        state.mobs.vpos[p.mob_slot] = native_v(5 * 16) << 7
        for hub in (pack_slot(5, 3), pack_slot(5, 7)):
            state.mobs.create(hub, tile=1, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.FORCEFIELDHUB))
        state.health_dirty = [0, 0, 0, 0]
        state.frame_counter = 1

        gp.main_move_players(state)

        assert p.health < 1000
        assert state.health_dirty[0] == 1

    def test_death_rebuilds_the_panel_column(self):
        from gauntpy.subsystems.score import info_panel

        state = _active_state()
        p = _make_player_active(state, 0, health=0)
        p.score = 777
        gp.main_move_players(state)
        field = info_panel(state).players[0]
        assert field.health_drawn and field.health == 0     # 0x46AD0
        assert field.score == 777

    def test_treasure_raises_the_score_bit(self):
        state = _active_state()
        _make_player_active(state, 1)
        state.score_dirty = [0, 0, 0, 0]
        slot = 46
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        gp.player_tile_interact(state, slot, 1)
        assert state.score_dirty[1] == 1


class TestShowContinuePrompt:

    def _ready(self) -> GameState:
        state = _active_state()
        state.level_players_active = 0
        state.levelnum_current = 4
        state.attract_timer = 0x5DD
        return state

    def test_draws_when_every_gate_passes(self):
        state = self._ready()
        gp.show_continue_prompt(state)
        assert 0x3B in state.sound_log          # "Gauntlet II Theme Song"
        assert state.title_intro_state == 1
        start = 13 * 64 + 5
        assert "".join(
            chr(word & 0x3FF) if word & 0x3FF else " "
            for word in state.alpha_ram[start:start + 19]
        ) == "   PRESS START     "

    def test_blocked_while_players_remain_on_the_level(self):
        state = self._ready()
        state.level_players_active = 1
        gp.show_continue_prompt(state)
        assert state.sound_log == []

    def test_blocked_on_level_1(self):
        state = self._ready()
        state.levelnum_current = 1
        gp.show_continue_prompt(state)
        assert state.sound_log == []

    def test_blocked_by_the_disabled_attract_timer_sentinel(self):
        state = self._ready()
        state.attract_timer = 0xFFFF
        gp.show_continue_prompt(state)
        assert state.sound_log == []

    def test_blocked_by_any_non_idle_player_status(self):
        state = self._ready()
        state.players[3].status = int(PlayerStatus.ALIVE_NEXT)
        gp.show_continue_prompt(state)
        assert state.sound_log == []

    def test_selecting_status_is_allowed(self):
        state = self._ready()
        state.players[3].status = int(PlayerStatus.SELECTING)
        gp.show_continue_prompt(state)
        assert 0x3B in state.sound_log


class TestSecretNameEntry:

    def test_secret_code_matches_the_rom_crc_pipeline(self):
        state = GameState()
        state.secret_name_buffer = list(b"ALINSA" + b" " * 23)
        state.secret_trick_last = 5
        state.secret_trick_id = 0x5A
        state.secret_prev_maze = 73

        assert gp.secret_code_build(state) == "FB9-AD9"

    def test_secret_code_result_clears_the_old_name_row(self):
        state = _active_state()
        state.secret_player = 0
        state.game_settings |= 0x2000
        gp.secret_getname(state)
        state.secret_name_buffer = list(b"ALINSA" + b" " * 20 + b"TDV")
        state.secret_code = "FB9-AD9"

        from gauntpy.subsystems.score import write_secret_code_result

        write_secret_code_result(state, 0)

        row = 7
        assert all(
            state.alpha_ram[row * 64 + column] & 0x01FF == 0
            for column in range(29)
            if not 7 <= column <= 20
        )

    def test_secret_code_dash_uses_name_entry_control_glyphs(self):
        from gauntpy.subsystems.score import write_secret_code_result

        state = _active_state()
        state.secret_code = "W1Y-GN0"
        write_secret_code_result(state, 0)

        row, column, attribute = 7, 13, 0x8400
        assert state.alpha_ram[row * 64 + column] == attribute + 0x7C
        assert state.alpha_ram[(row + 1) * 64 + column] == attribute + 0xFE
        assert state.alpha_ram[row * 64 + column + 1] == attribute + 0xFC
        assert state.alpha_ram[(row + 1) * 64 + column + 1] == attribute + 0x7E

    def test_timeout_builds_code_then_hands_the_player_back(self):
        state = _active_state()
        state.secret_player = 1
        p = state.players[1]
        state.game_settings |= 0x2000
        gp.secret_getname(state)
        assert p.status == int(PlayerStatus.SECRET_NAME_ENTRY)
        assert state.alpha_ram[1 * 64 + 4] & 0x0100
        state.global_delay_timer = 4
        gp.main_move_players(state)
        assert p.status == int(PlayerStatus.ALIVE_NEXT)   # 0x54FD4
        assert state.secret_player == -1                  # 0x54FDA
        assert len(state.secret_code) == 7
        assert state.secret_code[3] == "-"

    def test_ignores_a_winner_index_that_is_not_a_player(self):
        state = _active_state()
        state.secret_player = -1
        state.players[0].status = int(PlayerStatus.SECRET_NAME_ENTRY)
        state.players[0].state_timer = 5
        gp.main_move_players(state)
        assert state.players[0].state_timer == 5


# =============================================================================
# 14. maze_convert_walls_to_exits (0x5E80C) and the escape timeout
# =============================================================================

class TestMazeConvertWallsToExits:

    @staticmethod
    def _wall(state: GameState, slot: int, obj_type: int) -> None:
        state.mobs.create(slot, tile=0x8000, hpos=0, vpos=0, obj_type=obj_type)

    def test_converts_solid_walls_to_exits(self):
        state = _active_state()
        self._wall(state, 100, int(MazeObjIds.WALL_REGULAR))
        assert gp.maze_convert_walls_to_exits(state) == 1
        assert state.mobs.obj_type(100) == int(MazeObjIds.EXIT)
        assert state.mobs.picture[100] == 0

    def test_converts_movable_walls_by_their_base_picture(self):
        state = _active_state()
        state.mobs.create(101, tile=0x20F6, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.WALL_MOVABLE))
        assert gp.maze_convert_walls_to_exits(state) == 1
        assert state.mobs.obj_type(101) == int(MazeObjIds.EXIT)

    def test_conversion_updates_the_rendered_descriptor(self):
        from types import SimpleNamespace

        state = _active_state()
        slot = (8 << 5) | 9
        state.maze = SimpleNamespace(data={
            (9, 8): int(MazeObjIds.WALL_REGULAR),
        })
        self._wall(state, slot, int(MazeObjIds.WALL_REGULAR))

        assert gp.maze_convert_walls_to_exits(state) == 1
        assert state.maze.data[(9, 8)] == int(MazeObjIds.EXIT)

    def test_forcefield_hubs_survive(self):
        """0x5E844 excludes object type 0x3F."""
        state = _active_state()
        self._wall(state, 102, int(MazeObjIds.FORCEFIELDHUB))
        assert gp.maze_convert_walls_to_exits(state) == 0
        assert state.mobs.obj_type(102) == int(MazeObjIds.FORCEFIELDHUB)

    def test_ordinary_objects_are_untouched(self):
        state = _active_state()
        state.mobs.create(103, tile=0x1234, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        assert gp.maze_convert_walls_to_exits(state) == 0
        assert state.mobs.obj_type(103) == int(MazeObjIds.TREASURE)

    def test_returns_zero_when_nothing_changed(self):
        assert gp.maze_convert_walls_to_exits(_active_state()) == 0

    def test_converted_exit_carries_its_cell_position(self):
        state = _active_state()
        slot = (7 << 5) | 9
        self._wall(state, slot, int(MazeObjIds.WALL_SECRET))
        gp.maze_convert_walls_to_exits(state)
        assert hpos_x(state.mobs.hpos[slot]) == 9 * 16
        assert vpos_y(state.mobs.vpos[slot]) == 7 * 16

    def test_escape_timeout_fires_and_plays_sound_0x27(self):
        """0x4AD06-0x4AD3C: convert, announce, reset, clear the level flags."""
        state = _active_state()
        _make_player_active(state, 0, health=500)
        self._wall(state, 104, int(MazeObjIds.WALL_REGULAR))
        state.escape_timer = gp._ESCAPE_TIMER_LIMIT - 1
        state.level_flags_3 = 0xFF
        gp.main_move_players(state)
        assert state.mobs.obj_type(104) == int(MazeObjIds.EXIT)
        assert 0x27 in state.sound_log
        assert state.escape_timer == 0
        assert state.level_flags_3 == 0xFF & ~(0x08 | 0x40)

    def test_escape_timeout_is_silent_when_nothing_converted(self):
        state = _active_state()
        _make_player_active(state, 0, health=500)
        state.escape_timer = gp._ESCAPE_TIMER_LIMIT - 1
        gp.main_move_players(state)
        assert 0x27 not in state.sound_log

    def test_post_loop_is_gated_on_an_active_player(self):
        """0x4ACD4: no active player this frame, no timers advance."""
        state = _active_state()
        state.escape_timer = 5
        state.idle_timer = 5
        gp.main_move_players(state)
        assert state.escape_timer == 5
        assert state.idle_timer == 5


class TestDoorIdleTimeout:

    def test_threshold_without_keys(self):
        state = _active_state()
        _make_player_active(state, 0, health=500)
        state.mobs.create(200, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        state.idle_timer = gp._DOOR_IDLE_THRESHOLD_NO_KEYS
        gp.main_move_players(state)
        assert not state.mobs.is_occupied(200)
        assert state.idle_timer == -1        # ROM writes 0xFFFF at 0x4AD02

    def test_key_holder_extends_the_threshold(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.keysnum = 1
        state.mobs.create(201, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        state.idle_timer = gp._DOOR_IDLE_THRESHOLD_NO_KEYS
        gp.main_move_players(state)
        assert state.mobs.is_occupied(201), \
            "a key holder pushes the timeout out to 0xA8C (0x4ACEC)"

    def test_negative_timer_disables_further_increments(self):
        state = _active_state()
        _make_player_active(state, 0, health=500)
        state.idle_timer = -1
        gp.main_move_players(state)
        assert state.idle_timer == -1


# =============================================================================
# 15. player_tport (0x50224) -- discovery, screening and the landing commit
# =============================================================================

def _pack(row: int, col: int) -> int:
    return (row << 5) | col


class TestPlayerTport:
    """Every candidate here sits inside tile_on_screen_test's window for a
    camera parked at the origin: columns 0-13, rows 0-14 (0x5E584)."""

    def _world(self, pads=((5, 5), (5, 9))) -> tuple[GameState, int]:
        state = _active_state()
        p = _make_player_active(state, 0, health=500, mob_slot=30)
        state.mobs.hpos[30] = (5 * 16 + 8) << 7
        state.mobs.vpos[30] = native_v(5 * 16 + 8) << 7
        for row, col in pads:
            state.mobs.create(_pack(row, col), tile=0, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.TRANSPORTER))
        return state, _pack(*pads[0])

    def test_records_the_source_in_the_route_state(self):
        state, source = self._world()
        gp.player_tport(state, 0, source)
        assert state.player_tport_route_state[0] == source

    def test_arms_the_transition_instead_of_moving(self):
        """0x504F2-0x5052A: the producer picks the cell and hands over.

        The hero does not move on the pickup frame -- WP-14's loop 2 runs the
        dissolve, this file relocates at the move milestone, and loop 2 re-forms
        the hero at the far end.
        """
        state, source = self._world()
        before_h = state.mobs.hpos[30]
        before_v = state.mobs.vpos[30]

        assert gp.player_tport(state, 0, source) == -2

        # Scan order is direction 0..7 and the final loop keeps only the
        # diagonals, so direction 1 (up-right of the destination) wins.
        assert state.player_tile_or_tport_dest[0] == _pack(4, 10)     # 0x50606
        assert state.player_tport_type[0] == _pack(5, 9)    # 0x5051A
        assert state.player_tport_phase[0] == 0             # 0x5052A
        assert state.mobs.picture[0x19] == gp._TPORT_ARRIVAL_PICTURE
        assert state.mobs.hpos[30] == before_h, "no immediate commit"
        assert state.mobs.vpos[30] == before_v

    def test_plays_the_transport_sound(self):
        state, source = self._world()
        gp.player_tport(state, 0, source)
        assert 0x28 in state.sound_log

    def test_picks_the_nearest_pad_by_manhattan_distance(self):
        state, source = self._world(pads=((5, 5), (5, 12), (7, 6)))
        gp.player_tport(state, 0, source)
        # (7,6) is 3 away, (5,12) is 7 away -> the destination is (7,6).
        assert state.player_tile_or_tport_dest[0] == _pack(6, 7)

    def test_off_screen_pads_are_not_candidates(self):
        """A pad outside tile_on_screen_test's window is skipped (0x502D8)."""
        state, source = self._world(pads=((5, 5), (20, 20)))
        gp.player_tport(state, 0, source)
        # No usable destination -> the source pad is the destination (0x503AA).
        assert state.player_tile_or_tport_dest[0] == _pack(4, 6)

    def test_aborts_when_no_landing_cell_is_clear(self):
        state, source = self._world()
        for row in range(4, 7):
            for col in range(8, 11):
                slot = _pack(row, col)
                if state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER):
                    continue
                state.mobs.picture[slot] = 0x8000        # solid wall marker
        before = state.mobs.hpos[30]
        assert gp.player_tport(state, 0, source) == 0
        assert state.mobs.hpos[30] == before
        assert 0x28 not in state.sound_log

    def test_doors_block_a_landing_cell_without_a_key(self):
        """tport_check_dest returns 1 for door types when keysnum is 0."""
        state, _ = self._world()
        slot = _pack(4, 10)
        state.mobs.create(slot, tile=0x1000, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        assert gp.tport_check_dest(state, slot, 0) == 1
        state.players[0].keysnum = 1
        assert gp.tport_check_dest(state, slot, 0) == 0

    def test_transporter_visibility_wraps_across_the_maze_seam(self):
        state = GameState(scroll_x=480, scroll_y=4 * 16)

        assert gp.tile_on_screen_test(state, _pack(4, 2))
        assert not gp.tile_on_screen_test(state, _pack(4, 20))

    def test_another_players_sprite_blocks_a_landing_cell(self):
        state, _ = self._world()
        slot = _pack(4, 10)
        state.mobs.create(slot, tile=0x1000, hpos=0x0D, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        assert gp.tport_check_dest(state, slot, 0) == 1   # palette 0x0D = P2
        assert gp.tport_check_dest(state, slot, 1) == 0   # ... its owner

    def test_clearance_test_rejects_a_cell_another_player_stands_on(self):
        state, _ = self._world()
        # 8 px past the origin of (4,10) puts the other hero's record in the
        # neighbouring cell (4,11), which is what the ROM's neighbour scan sees.
        other_slot = _pack(4, 11)
        _make_player_active(state, 1, health=500, mob_slot=other_slot)
        state.mobs.create(
            other_slot, tile=0x1E0D,
            hpos=((10 * 16 + 8) << 7) | 0x0D,
            vpos=native_v(4 * 16 + 8) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART), state=1,
        )
        assert not gp.nearby_mob_clearance_test(state, _pack(4, 10), 0)
        assert gp.nearby_mob_clearance_test(state, _pack(4, 10), 1)

    def test_transportability_power_keeps_the_player_on_its_own_pad(self):
        """0x50252 tests ``btst #3`` of the powers high byte -- word bit 11,
        the bit ``POWER_TRANSPORT`` grants -- and short-circuits the
        destination search (0x5025A)."""
        state, source = self._world()
        state.players[0].powers = gp._POWER_TRANSPORT
        assert gp.player_tport(state, 0, source) == -2
        assert state.player_tile_or_tport_dest[0] == _pack(4, 6)    # diagonal of (5,5)

    def test_secret_trick_0x56_records_the_pad_index(self):
        state, source = self._world(pads=((5, 5), (5, 9), (7, 6)))
        state.secret_trick_id = 0x56
        gp.player_tport(state, 0, _pack(7, 6))
        # tport_find_id is one-based: sorted index 2 becomes bit 3.
        assert state.secret_tricks_flags[0] & (1 << 3)

    def test_contention_raises_the_required_clear_count(self):
        """0x504BA-0x504E6 adds one per player already bound for the pad."""
        state, source = self._world()
        # Leave exactly one clear landing cell around the destination.
        keep = _pack(4, 10)
        for row in range(4, 7):
            for col in range(8, 11):
                slot = _pack(row, col)
                if slot == keep or state.mobs.obj_type(slot) == int(
                        MazeObjIds.TRANSPORTER):
                    continue
                state.mobs.picture[slot] = 0x8000
        # No contention: one clear cell is enough.
        assert gp.player_tport(state, 0, source) == -2

        state, source = self._world()
        for row in range(4, 7):
            for col in range(8, 11):
                slot = _pack(row, col)
                if slot == keep or state.mobs.obj_type(slot) == int(
                        MazeObjIds.TRANSPORTER):
                    continue
                state.mobs.picture[slot] = 0x8000
        state.player_tport_type[2] = _pack(5, 9)
        state.player_tport_phase[2] = 0
        assert gp.player_tport(state, 0, source) == 0

    def test_tile_interact_propagates_the_abort(self):
        state, source = self._world()
        for row in range(4, 7):
            for col in range(8, 11):
                slot = _pack(row, col)
                if state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER):
                    continue
                state.mobs.picture[slot] = 0x8000
        assert gp.player_tile_interact(state, source, 0) == 0

    def test_tile_interact_reports_a_completed_teleport(self):
        state, source = self._world()
        assert gp.player_tile_interact(state, source, 0) == -1


# =============================================================================
# 16. player_create_shot spawn picture and position (0x53666)
# =============================================================================

class TestShotSpawnGeometry:

    def _shooter(self, direction: int, character: int = Character.WARRIOR):
        state = _active_state()
        p = _make_player_active(state, 0, character=character, mob_slot=30)
        state.mobs.hpos[30] = (100) << 7
        state.mobs.vpos[30] = native_v(200) << 7
        p.direction = direction
        return state, p

    def test_tables_match_the_rom_image(self):
        assert gp._SHOT_REFLECT_HDELTA == [
            0x0200, 0x0500, 0x0600, 0x0300, 0x0200, -0x0080, -0x0200, -0x0100,
        ]
        assert gp._SHOT_REFLECT_VDELTA == [
            0x0700, 0x0300, 0x0180, -0x0080, -0x0100, -0x0280, 0x0180, 0x0380,
        ]
        assert gp._PORT_DIR_TO_ROM_DIR == [2, 3, 4, 5, 6, 7, 0, 1]
        assert gp._PLAYER_SHOT_PICTURE[:8] == [
            0x1C9F, 0x1CA7, 0x1CAF, 0x1CB7, 0x1CBF, 0x1CC7, 0x1CCF, 0x1C97,
        ]

    def test_picture_comes_from_the_rom_table(self):
        state, _ = self._shooter(direction=0)          # port right = ROM 2
        gp.player_create_shot(state, 0)
        assert state.mobs.picture[1] == gp._PLAYER_SHOT_PICTURE[2]

    def test_picture_is_per_character(self):
        state, _ = self._shooter(direction=0, character=Character.WIZARD)
        gp.player_create_shot(state, 0)
        assert state.mobs.picture[1] == gp._PLAYER_SHOT_PICTURE[2 * 8 + 2]

    def test_spawn_offset_is_applied(self):
        state, _ = self._shooter(direction=0)          # right -> ROM dir 2
        gp.player_create_shot(state, 0)
        assert hpos_x(state.mobs.hpos[1]) == 100 + 12
        assert vpos_y(state.mobs.vpos[1]) == 200 - 3

    def test_upward_shot_spawns_above_the_player(self):
        state, _ = self._shooter(direction=6)          # up -> ROM dir 0
        gp.player_create_shot(state, 0)
        assert hpos_x(state.mobs.hpos[1]) == 100 + 4
        assert vpos_y(state.mobs.vpos[1]) == 200 - 14

    def test_palette_identifies_the_owning_player(self):
        state = _active_state()
        p = _make_player_active(state, 2, mob_slot=32)
        state.mobs.hpos[32] = 100 << 7
        state.mobs.vpos[32] = native_v(200) << 7
        gp.player_create_shot(state, 2)
        assert (state.mobs.hpos[3] & 0x0F) == gp._SHOT_PALETTE_BASE + 2

    def test_shot_is_two_tiles_square(self):
        state, _ = self._shooter(direction=0)
        gp.player_create_shot(state, 0)
        assert (state.mobs.vpos[1] & 0x7F) == 9      # width 2, height 2

    def test_channel_stays_busy_until_the_shot_clears(self):
        state, _ = self._shooter(direction=0)
        gp.player_create_shot(state, 0)
        first = state.mobs.hpos[1]
        gp.player_create_shot(state, 0)
        assert state.mobs.hpos[1] == first


# =============================================================================
# 17. Remaining audit fixes
# =============================================================================

class TestScoreRedrawBit:

    def test_add_score_with_mult_sets_the_redraw_bit(self):
        """§4.7: the routine sets score-redraw bit 0 as well as the score."""
        state = _active_state()
        _make_player_active(state, 1)
        state.score_dirty = [0, 0, 0, 0]
        gp.player_add_score_with_mult(state, 1, 100)
        assert state.score_dirty == [0, 1, 0, 0]


class TestHandleTport:

    def test_places_the_sparkle_on_the_players_own_channel(self):
        """0x47D10: the effect slot is 0x19 + player, not a shared pool."""
        state = _active_state()
        p = _make_player_active(state, 2, mob_slot=30)
        state.mobs.hpos[30] = (0x1234 & 0xFF80)
        state.mobs.vpos[30] = (0x2345 & 0xFF80)
        gp.handle_tport(state, 30, 2)
        slot = 0x19 + 2
        assert state.mobs.picture[slot] == gp._TPORT_ARRIVAL_PICTURE
        assert state.mobs.hpos[slot] == (state.mobs.hpos[30] & 0xFF80) + 1
        assert state.mobs.vpos[slot] == (state.mobs.vpos[30] & 0xFF80) + 0x12

    def test_reuses_a_busy_channel(self):
        state = _active_state()
        _make_player_active(state, 0, mob_slot=30)
        state.mobs.create(0x19, tile=0x1111, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        gp.handle_tport(state, 30, 0)
        assert state.mobs.picture[0x19] == gp._TPORT_ARRIVAL_PICTURE


class TestDeathAnimationSeed:

    def test_frame_starts_from_the_rom_facing(self):
        """The ROM's animation frame is player_facing_dir itself (0x4A672)."""
        state = _active_state()
        p = _make_player_active(state, 0, health=0)
        p.direction = 2                 # port "down" -> ROM 4
        gp.main_move_players(state)
        assert state.player_death_anim_frame[0] == 4

    def test_death_clears_the_live_migrated_record_before_reset(self):
        state = _active_state()
        slot = (10 << 5) | 10
        p = _make_player_active(state, 0, health=0, mob_slot=slot)
        state.level_players_active = 1
        state.mobs.create(
            slot, tile=0x1E0D,
            hpos=(160 << 7) | 0x0C,
            vpos=native_v(160) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART),
            state=0,
        )

        gp.main_move_players(state)

        assert p.mob_slot == 0
        assert not state.mobs.is_occupied(slot)
        assert not state.mobs.is_linked(slot)

    def test_player_start_inner_clears_the_death_damage_counter(self):
        state = _active_state()
        state.maze = object()
        state.mobs.create(60, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.PLAYERSTART))
        p = state.players[0]
        p.death_damage_counter = 17
        p.pending_damage = 50
        p.cumulative_damage = 70
        p.damage_sample_timer = 1
        p.hurt_cooldown = 9
        state.forcefield_hurt_timer[0] = 7
        state.death_touch_timer[0] = 8
        assert gp.player_start_inner(state, 0) == -1
        assert p.death_damage_counter == 0
        assert p.pending_damage == 0
        assert p.cumulative_damage == 0
        assert p.damage_sample_timer == 60
        assert p.hurt_cooldown == 0
        assert state.forcefield_hurt_timer[0] == 0
        assert state.death_touch_timer[0] == 0
        assert state.secret_tricks_flags[0] == 0xFF
        x, _flags, palette = decode_hpos(state.mobs.hpos[p.mob_slot])
        y, width, height = decode_vpos_at_y(state.mobs.vpos[p.mob_slot])
        cell_x, cell_y = slot_to_pixels(p.mob_slot)
        assert (x, y) == (cell_x - 4, cell_y)
        assert palette == 0x0C
        assert (width, height) == (3, 3)

    def test_player_start_records_the_victim_index_for_shot_damage(self):
        state = _active_state()
        state.maze = object()
        slots = [60, 61, 62, 63]
        for slot in slots:
            state.mobs.create(
                slot, tile=0, hpos=0, vpos=0,
                obj_type=int(MazeObjIds.PLAYERSTART),
            )

        for player_index in range(4):
            assert gp.player_start_inner(state, player_index) == -1
            slot = state.players[player_index].mob_slot
            assert state.mobs.state(slot) == player_index


# =============================================================================
# 18. Integration with WP-11's living-maze routines (maze_objects.py)
# =============================================================================

class TestForcefieldUsesTheSegmentTable:
    """players.py no longer keeps its own hub scan; it queries the packed
    segment table WP-11 builds (0x53398) through check_forcefield_collision
    (0x53346/0x5FC5E)."""

    def test_duplicate_scan_is_gone(self):
        assert not hasattr(gp, "_forcefield_cells")
        assert not hasattr(gp, "_FORCEFIELD_BLOCKERS")

    def test_contact_builds_the_table_when_driven_standalone(self):
        from gauntpy.coords import pack_slot

        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000, mob_slot=pack_slot(5, 5))
        state.mobs.hpos[p.mob_slot] = (5 * 16) << 7
        state.mobs.vpos[p.mob_slot] = native_v(5 * 16) << 7
        for hub in (pack_slot(5, 3), pack_slot(5, 7)):
            state.mobs.create(hub, tile=1, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.FORCEFIELDHUB))
        assert not state.forcefield_segments_ready

        gp.main_move_players(state)

        assert state.forcefield_segments_ready
        assert state.forcefield_segment_table, "the packed segment table must be built"
        assert p.health < 1000

    def test_query_follows_the_table_not_the_mob_grid(self):
        """A hand-written segment hurts even with no hub MOBs on the level."""
        from gauntpy.coords import pack_slot

        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000, mob_slot=pack_slot(5, 5))
        state.mobs.hpos[p.mob_slot] = (5 * 16) << 7
        state.mobs.vpos[p.mob_slot] = native_v(5 * 16) << 7
        # horizontal, length 4, hub at (5,3) -- see doc/04 §7.3.
        state.forcefield_segment_table = [0x8000 | (3 << 10) | pack_slot(5, 3)]
        state.forcefield_segments_ready = True

        gp.main_move_players(state)

        assert p.health == 1000 - 2, "the segment word alone must drive contact"

    def test_wrapped_segment_is_honoured(self):
        """The wrap bit is a segment field the old grid scan could not see."""
        from gauntpy.coords import pack_slot

        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000, mob_slot=pack_slot(5, 1))
        state.mobs.hpos[p.mob_slot] = (1 * 16) << 7
        state.mobs.vpos[p.mob_slot] = native_v(5 * 16) << 7
        # horizontal + wrap, length 4, hub at (5,30): covers 31, 0, 1.
        state.forcefield_segment_table = [
            0x8000 | 0x4000 | (3 << 10) | pack_slot(5, 30)
        ]
        state.forcefield_segments_ready = True

        gp.main_move_players(state)

        assert p.health < 1000


class TestOpenTimedDoorsDelegates:

    def test_shares_wp11s_implementation(self):
        from gauntpy.subsystems import maze_objects

        state = _active_state()
        state.mobs.create(300, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        state.mobs.create(301, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_VERT))
        calls = []
        original = maze_objects.open_timed_doors

        def _spy(st):
            calls.append(st)
            return original(st)

        maze_objects.open_timed_doors = _spy
        try:
            gp.open_timed_doors(state)
        finally:
            maze_objects.open_timed_doors = original

        assert calls, "players.open_timed_doors must hand off to WP-11"
        assert not state.mobs.is_occupied(300)
        assert not state.mobs.is_occupied(301)
        assert state.sound_log.count(0x12) == 1


class TestDoorOpeningFronts:
    """A key does not just delete a door: it starts the two opening fronts at
    0x904A76/0x904A86 that WP-11's main_open_doors walks along the door line."""

    _DOOR_HORIZ_PICTURE = 0x9D3C
    _DOOR_VERT_PICTURE = 0x9D7C

    def _door_line(self, state: GameState, slots, picture, obj_type) -> None:
        for slot in slots:
            state.mobs.create(slot, tile=picture, hpos=0, vpos=0,
                              obj_type=int(obj_type))

    def test_vertical_door_seeds_up_and_down(self):
        state = _active_state()
        _make_player_active(state, 1)
        slot = (8 << 5) | 8
        self._door_line(state, [slot - 0x20, slot, slot + 0x20],
                        self._DOOR_VERT_PICTURE, MazeObjIds.DOOR_VERT)
        gp.door_open_start(state, slot, 1)
        # door_open_start ends by stepping both fronts once (0x51F9E), so they
        # now sit on the cells above and below, which are already open.
        assert state.door_endpoint_dir[2:4] == [0, 2]
        assert state.door_endpoint_pos[2:4] == [slot - 0x20, slot + 0x20]
        assert not state.mobs.is_occupied(slot - 0x20)
        assert not state.mobs.is_occupied(slot + 0x20)

    def test_horizontal_door_seeds_left_and_right(self):
        state = _active_state()
        _make_player_active(state, 0)
        slot = (8 << 5) | 8
        self._door_line(state, [slot - 1, slot, slot + 1],
                        self._DOOR_HORIZ_PICTURE, MazeObjIds.DOOR_HORIZ)
        gp.door_open_start(state, slot, 0)
        assert state.door_endpoint_dir[0:2] == [3, 1]
        assert state.door_endpoint_pos[0:2] == [slot - 1, slot + 1]
        assert not state.mobs.is_occupied(slot - 1)
        assert not state.mobs.is_occupied(slot + 1)

    def test_junction_scans_both_axes_in_object_type_order(self):
        state = _active_state()
        _make_player_active(state, 0)
        slot = (8 << 5) | 8
        state.mobs.create(
            slot, tile=0x9D38, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.DOOR_HORIZ),
        )
        state.mobs.create(
            slot - 1, tile=0x9D3C, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.DOOR_HORIZ),
        )
        state.mobs.create(
            slot - 0x20, tile=0x9D7C, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.DOOR_VERT),
        )

        gp.door_open_start(state, slot, 0)

        assert state.door_endpoint_dir[0:2] == [3, 0]
        assert state.mobs.picture[slot - 1] == 0
        assert state.mobs.picture[slot - 0x20] == 0
        assert state.door_endpoint_pos[0:2] == [slot - 1, slot - 0x20]

    def test_junction_endpoint_scan_rejects_reserved_row_zero(self):
        state = _active_state()
        _make_player_active(state, 0)
        slot = (1 << 5) | 8
        state.mobs.create(
            slot, tile=0x9D38, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.DOOR_HORIZ),
        )
        reserved = slot - 0x20
        state.mobs.create(
            reserved, tile=0x9D3C, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.DOOR_HORIZ),
        )

        gp.door_open_start(state, slot, 0)

        assert state.door_endpoint_pos[0:2] == [0, 0]
        assert state.mobs.picture[reserved] == 0x9D3C

    def test_a_front_dies_at_the_end_of_the_door_line(self):
        state = _active_state()
        _make_player_active(state, 0)
        slot = (8 << 5) | 8
        self._door_line(state, [slot], self._DOOR_HORIZ_PICTURE,
                        MazeObjIds.DOOR_HORIZ)
        gp.door_open_start(state, slot, 0)
        assert state.door_endpoint_pos[0:2] == [0, 0]

    def test_each_player_owns_its_own_channel_pair(self):
        state = _active_state()
        slot = (8 << 5) | 8
        self._door_line(state, [slot - 1, slot, slot + 1],
                        self._DOOR_HORIZ_PICTURE, MazeObjIds.DOOR_HORIZ)
        gp.door_open_start(state, slot, 3)
        assert state.door_endpoint_pos[6:8] == [slot - 1, slot + 1]
        assert state.door_endpoint_pos[0:6] == [0] * 6

    def test_tile_interact_unlocks_announces_and_resets_the_escape_timer(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.keysnum = 2
        state.escape_timer = 5000
        slot = (8 << 5) | 8
        self._door_line(state, [slot, slot + 1], self._DOOR_HORIZ_PICTURE,
                        MazeObjIds.DOOR_HORIZ)

        assert gp.player_tile_interact(state, slot, 0) == -1

        assert p.keysnum == 1
        assert not state.mobs.is_occupied(slot)
        assert 0x12 in state.sound_log
        assert state.escape_timer == 0
        assert state.health_dirty[0] == 1

    def test_the_front_walks_the_rest_of_the_door_line(self):
        from gauntpy.subsystems.maze_objects import main_open_doors

        state = _active_state()
        p = _make_player_active(state, 0)
        p.keysnum = 1
        slot = (8 << 5) | 8
        line = [slot, slot + 1, slot + 2]
        self._door_line(state, line, self._DOOR_HORIZ_PICTURE,
                        MazeObjIds.DOOR_HORIZ)

        gp.player_tile_interact(state, slot, 0)
        # door_open_start already ran one step (0x51F9E).
        assert not state.mobs.is_occupied(slot + 1)
        main_open_doors(state)
        assert not state.mobs.is_occupied(slot + 2)

    def test_no_key_leaves_the_door_and_the_fronts_alone(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.keysnum = 0
        state.escape_timer = 5000
        slot = (8 << 5) | 8
        self._door_line(state, [slot], self._DOOR_HORIZ_PICTURE,
                        MazeObjIds.DOOR_HORIZ)

        assert gp.player_tile_interact(state, slot, 0) == 0

        assert state.mobs.is_occupied(slot)
        assert state.door_endpoint_pos == [0] * 8
        assert state.escape_timer == 5000
        assert 0x12 not in state.sound_log


# =============================================================================
# 19. Demo playback (§6.2, main_move_players 0x4A560-0x4A5F0)
# =============================================================================

def _demo_state(streams, active=1) -> GameState:
    """A DEMO-mode state with hand-written record streams installed."""
    state = GameState(game_mode=GameMode.DEMO)
    for i, stream in enumerate(streams):
        state.demo_streams[i] = list(stream)
    state.demo_active_player = active
    return state


class TestDemoPlaybackDoesNotWriteHardwareInput:
    """0x4A560-0x4A5F0 touches demo_timer and demo_ptr and nothing else."""

    def test_player_input_raw_is_never_written(self):
        # 0xD1 has the active-low FIRE bit clear; 0x33 holds two directions.
        state = _demo_state([[], [1, 0xD1, 4, 0x33, 4, 0xF3], [], []])
        for _ in range(24):
            gp.main_move_players(state)
        assert state.player_input_raw == [0xFFFF] * 4, (
            "the recorded joystick must never reach the hardware input array"
        )

    def test_only_the_record_cursor_and_timer_move(self):
        state = _demo_state([[], [3, 0xF3, 5, 0xB3], [], []])
        gp.main_move_players(state)                 # arms and spends one frame
        assert state.demo_timers[1] == 2
        assert state.demo_stream_pos[1] == 0
        gp.main_move_players(state)
        gp.main_move_players(state)                 # timer reaches 0 -> advance
        assert state.demo_stream_pos[1] == 2
        assert state.demo_timers[1] == 5            # 0x4A5E6 loads byte 0 only

    def test_a_zero_timer_slot_is_inert(self):
        """0x4A56E skips a slot whose timer is zero -- the ROM's null pointer."""
        state = _demo_state([[9, 0x03], [1, 0xF3], [], []], active=1)
        gp.main_move_players(state)
        assert state.demo_stream_pos[0] == 0
        assert state.demo_timers[0] == 0

    def test_only_the_selected_slot_is_armed(self):
        state = _demo_state([[7, 0xF3], [4, 0xF3], [7, 0xF3], [7, 0xF3]], active=1)
        gp.main_move_players(state)
        assert state.demo_timers == [0, 3, 0, 0]

    def test_an_exhausted_stream_leaves_the_slot_inert(self):
        state = _demo_state([[], [1, 0xF3], [], []])
        for _ in range(8):
            gp.main_move_players(state)
        assert state.demo_timers[1] == 0


class TestDemoRecordWord:

    def test_word_is_the_records_two_bytes(self):
        """0x506B6 reads a word: (timer << 8) | joystick."""
        state = _demo_state([[], [6, 0xB3], [], []])
        gp.main_move_players(state)
        assert gp.demo_record_word(state, 1) == 0x06B3

    def test_idle_for_a_slot_the_demo_never_started(self):
        state = _demo_state([[6, 0xB3], [6, 0xB3], [], []], active=1)
        gp.main_move_players(state)
        assert gp.demo_record_word(state, 0) == 0xFFFF
        assert gp.demo_record_word(state, 2) == 0xFFFF

    def test_idle_when_the_stream_is_empty(self):
        state = _demo_state([[], [], [], []])
        assert gp.demo_record_word(state, 1) == 0xFFFF

    def test_word_is_stable_while_the_record_is_held(self):
        state = _demo_state([[], [4, 0xB3, 4, 0xF3], [], []])
        gp.main_move_players(state)
        first = gp.demo_record_word(state, 1)
        gp.main_move_players(state)
        assert gp.demo_record_word(state, 1) == first

    def test_selector_follows_the_game_mode(self):
        """0x50690: DEMO reads the record, every other mode the hardware word."""
        state = _demo_state([[], [6, 0xB3], [], []])
        gp.main_move_players(state)
        state.player_input_raw[1] = 0x1234
        assert gp.player_joystick_word(state, 1) == 0x06B3
        state.game_mode = int(GameMode.NORMAL)
        assert gp.player_joystick_word(state, 1) == 0x1234


class TestDemoDrivesMovementAndFire:

    def _elf(self, state: GameState) -> Player:
        p = state.players[1]
        p.status = int(PlayerStatus.ALIVE_HERE)
        p.health = 500
        # The record *is* the cell it stands in, so place it consistently:
        # slot 40 is row 1 / column 8, and a 24px hero's origin is 4px left of
        # its cell.
        p.mob_slot = 40
        state.mobs.hpos[40] = (8 * 16 - 4) << 7
        state.mobs.vpos[40] = native_v(1 * 16) << 7
        return p

    def test_recorded_direction_moves_the_hero(self):
        # 0xE3: bit 4 (RIGHT) clear -> right held, buttons released.
        state = _demo_state([[], [40, 0xE3], [], []])
        p = self._elf(state)
        x0 = hpos_x(state.mobs.hpos[p.mob_slot])
        gp.main_move_players(state)
        assert hpos_x(state.mobs.hpos[p.mob_slot]) > x0

    def test_idle_record_moves_nothing(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        p = self._elf(state)
        x0 = hpos_x(state.mobs.hpos[p.mob_slot])
        gp.main_move_players(state)
        assert hpos_x(state.mobs.hpos[p.mob_slot]) == x0

    def test_recorded_fire_plays_the_throw_before_creating_a_shot(self):
        # 0xF1: bit 1 (FIRE) clear -> fire held.
        state = _demo_state([[], [40, 0xF1], [], []])
        self._elf(state)
        gp.main_move_players(state)
        assert state.player_shooting[1]
        assert state.mobs.picture[2] == 0
        for _ in range(3):
            gp.main_move_players(state)
        assert state.mobs.picture[2] != 0, "player 1's shot channel is slot 2"

    def test_hardware_input_cannot_drive_a_demo_hero(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        p = self._elf(state)
        state.player_input_raw[1] = 0xFFFF & ~0x10   # RIGHT held on the cabinet
        x0 = hpos_x(state.mobs.hpos[p.mob_slot])
        gp.main_move_players(state)
        assert hpos_x(state.mobs.hpos[p.mob_slot]) == x0


class TestDemoJoinRecords:
    """0x4A5B2-0x4A5DE: ``FE nn`` -- high nibble character, low nibble slot."""

    def test_join_writes_the_character_and_arms_the_slot(self):
        state = _demo_state([[], [1, 0xF3, 0xFE, 0x20, 9, 0xF3], [], []])
        gp.main_move_players(state)                 # arm, timer 1 -> 0, advance
        assert int(state.players[0].character) == 2      # high nibble = Wizard
        assert state.demo_timers[0] == 1                 # 0x4A5CC
        assert state.demo_stream_pos[0] == 0             # 0x4A5DE
        assert state.demo_timers[1] == 9                 # walk continued

    def test_join_calls_player_join(self):
        joined = []
        original = gp.player_join

        def _spy(st, index):
            joined.append(index)
            return original(st, index)

        gp.player_join = _spy
        try:
            state = _demo_state([[], [1, 0xF3, 0xFE, 0x13, 9, 0xF3], [], []])
            gp.main_move_players(state)
        finally:
            gp.player_join = original
        assert joined == [3], "the low nibble selects the joining slot"

    def test_back_to_back_join_records(self):
        """Player 1's ROM stream carries ``FE 20 FE 03`` (0x58234)."""
        state = _demo_state(
            [[5, 0xF3], [1, 0xF3, 0xFE, 0x20, 0xFE, 0x03, 7, 0xF3],
             [], [6, 0xF3, 8, 0xF3]]
        )
        gp.main_move_players(state)
        assert int(state.players[0].character) == 2
        assert int(state.players[3].character) == 0
        # Slot 0 is scanned before slot 1, so it still holds the kick-off timer.
        assert state.demo_timers[0] == 1
        assert state.demo_stream_pos[0] == 0
        assert state.demo_timers[1] == 7

    def test_a_joined_slot_starts_running_its_own_stream(self):
        """A slot joined *after* the scanned one is reached in the same 0..3
        loop, so it spends its kick-off frame and advances.

        The kick-off timer of 1 (0x4A5CC) stands in for record 0's own timer:
        the walk always begins with ``addq.l #2`` (0x4A584), so a slot joined
        mid-demo starts at record 1.  Only the slot ``attract_demo_init`` seeds
        honours record 0, because that path loads the timer straight from it
        (0x44A48).
        """
        state = _demo_state(
            [[], [1, 0xF3, 0xFE, 0x03, 9, 0xF3], [], [5, 0xF3, 8, 0xB3]]
        )
        gp.main_move_players(state)
        assert state.demo_timers[3] == 8
        assert state.demo_stream_pos[3] == 2
        assert gp.demo_record_word(state, 3) == 0x08B3

    def test_a_slot_joined_earlier_in_the_loop_waits_a_frame(self):
        state = _demo_state(
            [[5, 0xF3, 8, 0xF3], [1, 0xF3, 0xFE, 0x00, 9, 0xF3], [], []]
        )
        gp.main_move_players(state)
        assert state.demo_timers[0] == 1        # kick-off, not yet spent
        assert state.demo_stream_pos[0] == 0
        gp.main_move_players(state)
        assert state.demo_timers[0] == 8        # record 1 loaded
        assert state.demo_stream_pos[0] == 2

    def test_a_self_join_record_cannot_hang_the_frame(self):
        """``FE`` naming the slot being scanned reloads that slot's own pointer
        (0x4A5DE) straight back onto the same record -- a malformed stream the
        ROM would spin on forever.  The walk is bounded by the stream length so
        the frame still ends."""
        state = _demo_state([[], [1, 0xF3, 0xFE, 0x31, 4, 0xF3], [], []])
        gp.main_move_players(state)
        assert int(state.players[1].character) == 3

    def test_caption_record_is_consumed_and_the_walk_continues(self):
        state = _demo_state([[], [1, 0xF3, 0xFF, 0x05, 12, 0xF3], [], []])
        gp.main_move_players(state)
        assert state.demo_stream_pos[1] == 4
        assert state.demo_timers[1] == 12


class TestDemoDoesNotDisturbAttractOrTheSession:
    """End to end: a running demo must not restart an attract screen and must
    not start a free-play session."""

    def _run_demo(self, frames: int) -> GameState:
        from gauntpy.subsystems.attract import main_attract, start_attract_screen
        from gauntpy.subsystems.input import input_debounce
        from gauntpy.subsystems.session import coincheck, main_start_game

        state = GameState()
        start_attract_screen(state, int(GameMode.DEMO))
        for frame in range(frames):
            state.frame_counter = frame
            input_debounce(state)
            coincheck(state)
            gp.main_move_players(state)
            main_start_game(state)
            main_attract(state)
        return state

    def test_the_recorded_stream_really_would_trip_the_tests(self):
        """Guard the guard: the P1 stream carries bytes with the active-low
        FIRE/MAGIC and direction bits clear, so writing them into
        player_input_raw is not a harmless mistake."""
        from gauntpy.subsystems.attract import _DEMO_STREAMS

        joysticks = _DEMO_STREAMS[1][1::2]
        assert any((b & 0x03) != 0x03 for b in joysticks)
        assert any((b & 0xF0) != 0xF0 for b in joysticks)

    def test_demo_never_switches_the_attract_screen(self):
        state = self._run_demo(400)
        assert state.game_mode == int(GameMode.DEMO)

    def test_demo_leaves_the_hardware_input_idle(self):
        state = self._run_demo(400)
        assert state.player_input_raw == [0xFFFF] * 4

    def test_demo_never_arms_a_debounced_press_edge(self):
        from gauntpy.subsystems.input import magic_press_edge

        state = self._run_demo(400)
        assert not any(magic_press_edge(state, p) for p in range(4))

    def test_demo_does_not_start_a_free_play_session(self):
        state = self._run_demo(400)
        state.two_player_mode = 0        # free play: a Magic edge would join
        assert state.game_mode == int(GameMode.DEMO)
        assert state.credits == 0
        assert [int(p.status) for p in (state.players[0], state.players[2],
                                        state.players[3])] == [0, 0, 0]

    def test_the_demo_hero_actually_moves(self):
        """The split must not have turned playback off: the Elf still runs."""
        state = self._run_demo(400)
        elf = state.players[1]
        if elf.mob_slot == 0:
            import pytest
            pytest.skip("demo maze needs the ROMs")
        assert state.demo_stream_pos[1] > 0
        assert state.demo_timers[1] != 0


# =============================================================================
# 20. Treasure credit goes to its collector (0x519F0-0x519F8)
# =============================================================================

class TestTreasureAttribution:
    """``player_treascount`` (0x904A50) is the treasure factor of the per-player
    level-end bonus, so every pickup names its collector through WP-15's
    ``exits.treasure_collected`` -- which also owns the level total."""

    @staticmethod
    def _treasure(state: GameState, slot: int, obj_type) -> int:
        state.mobs.create(slot, tile=0, hpos=0, vpos=0, obj_type=int(obj_type))
        return slot

    def test_plain_treasure_credits_the_collector(self):
        state = _active_state()
        _make_player_active(state, 2)
        slot = self._treasure(state, 50, MazeObjIds.TREASURE)
        gp.player_tile_interact(state, slot, 2)
        assert state.player_treascount == [0, 0, 1, 0]
        assert state.score_display_timer[0] == 0x3C
        assert state.mobs.picture[0x11] == 0x1DB4

    def test_treasure_bag_credits_the_collector(self):
        state = _active_state()
        _make_player_active(state, 1)
        slot = self._treasure(state, 51, MazeObjIds.TREASURE_BAG)
        gp.player_tile_interact(state, slot, 1)
        assert state.player_treascount == [0, 1, 0, 0]

    def test_locked_treasure_is_not_a_walk_in_pickup(self):
        """Type 0x2F goes to the unhandled tail (0x511CE table -> 0x51E60).

        A chest is opened by shooting it, so walking into one with a key in
        hand must neither spend the key nor credit a treasure.
        """
        state = _active_state()
        p = _make_player_active(state, 3)
        p.keysnum = 1
        slot = self._treasure(state, 52, MazeObjIds.TREASURE_LOCKED)
        assert gp.player_tile_interact(state, slot, 3) == 0
        assert state.player_treascount == [0, 0, 0, 0]
        assert p.keysnum == 1, "the key is not spent"
        assert state.mobs.obj_type(slot) == int(MazeObjIds.TREASURE_LOCKED)

    def test_locked_treasure_without_a_key_credits_nothing(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.keysnum = 0
        slot = self._treasure(state, 53, MazeObjIds.TREASURE_LOCKED)
        assert gp.player_tile_interact(state, slot, 0) == 0
        assert state.player_treascount == [0, 0, 0, 0]
        assert state.level_treasures == 0

    def test_the_level_total_is_not_double_counted(self):
        """The pickup arm must not bump ``level_treasures`` itself: WP-15's
        write site already does, and doing both would pay the bonus screen for
        treasure nobody picked up."""
        state = _active_state()
        _make_player_active(state, 0)
        for i, kind in enumerate((MazeObjIds.TREASURE, MazeObjIds.TREASURE_BAG)):
            gp.player_tile_interact(state, self._treasure(state, 60 + i, kind), 0)
        assert state.level_treasures == 2
        assert state.player_treascount == [2, 0, 0, 0]

    def test_every_pickup_is_attributed(self):
        """``_treasure_shares`` credits any unattributed remainder to the first
        recipient; with the pickup path attributing, the remainder is zero."""
        state = _active_state()
        _make_player_active(state, 1)
        _make_player_active(state, 3)
        gp.player_tile_interact(
            state, self._treasure(state, 70, MazeObjIds.TREASURE), 1)
        gp.player_tile_interact(
            state, self._treasure(state, 71, MazeObjIds.TREASURE), 3)
        gp.player_tile_interact(
            state, self._treasure(state, 72, MazeObjIds.TREASURE_BAG), 3)
        assert state.player_treascount == [0, 1, 0, 2]
        assert sum(state.player_treascount) == state.level_treasures

    def test_the_score_award_still_differs_per_treasure_type(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        state.level_players_active = 1     # solo: multiplier stays at 1
        p.score = 0
        gp.player_tile_interact(
            state, self._treasure(state, 80, MazeObjIds.TREASURE), 0)
        assert p.score == 100
        state.special_bonus_score = 200
        gp.player_tile_interact(
            state, self._treasure(state, 81, MazeObjIds.TREASURE_BAG), 0)
        assert p.score == 300
        assert state.score_display_timer[0] == 60
        # A locked chest pays nothing at all from the walk path.
        p.keysnum = 1
        assert gp.player_tile_interact(
            state, self._treasure(state, 82, MazeObjIds.TREASURE_LOCKED), 0) == 0
        assert p.score == 300

    def test_spawning_clears_the_previous_levels_credit(self):
        """0x48E86: player_start_inner's per-player init zeroes the count."""
        state = _active_state()
        state.maze = object()
        state.mobs.create(90, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.PLAYERSTART))
        state.player_treascount[0] = 7
        assert gp.player_start_inner(state, 0) == -1
        assert state.player_treascount[0] == 0


# =============================================================================
# 21. First-encounter dialogs at their ROM call sites (0x4C440)
# =============================================================================

class TestPickupDialogs:
    """``score.dialog_first_encounter`` is wired at the addresses the ROM calls
    it from; the mask's set bit number picks the record."""

    @staticmethod
    def _lines(index: int) -> list[str]:
        from gauntpy.subsystems.score import DIALOG_MESSAGES

        return list(DIALOG_MESSAGES[index])

    def test_masks_match_their_record_numbers(self):
        assert gp._DIALOG_FOOD == 1 << 0
        assert gp._DIALOG_LOW_HEALTH == 1 << 2
        assert gp._DIALOG_KEYS == 1 << 3
        assert gp._DIALOG_SAVE_POTIONS == 1 << 5
        assert gp._DIALOG_POISONED == 1 << 13

    def test_food_shows_record_0(self):
        state = _active_state()
        _make_player_active(state, 0, health=300)
        gp.player_tile_interact(state, _make_food_slot(state), 0)
        assert state.dialog_message == self._lines(0)      # 0x51CDE
        assert state.dialog_player == 0

    def test_key_shows_record_3(self):
        state = _active_state()
        _make_player_active(state, 0)
        gp.player_tile_interact(state, _make_key_slot(state), 0)
        assert state.dialog_message == self._lines(3)      # 0x51620

    def test_potion_shows_record_5(self):
        state = _active_state()
        _make_player_active(state, 2)
        slot = 47
        state.mobs.create(slot, tile=0x1234, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POT_DESTRUCTABLE))
        gp.player_tile_interact(state, slot, 2)
        assert state.dialog_message == self._lines(5)      # 0x51796
        assert state.dialog_player == 2

    def test_each_record_is_one_shot(self):
        state = _active_state()
        _make_player_active(state, 0, health=300)
        gp.player_tile_interact(state, _make_food_slot(state), 0)
        from gauntpy.subsystems.score import dialog_clear_message
        dialog_clear_message(state)
        state.dialog_timer = 0
        gp.player_tile_interact(state, _make_food_slot(state), 0)
        assert state.dialog_message == [], "first-encounter flags are one-shot"

    def test_forcefield_contact_shows_its_own_record(self):
        from gauntpy.coords import pack_slot

        state = _active_state()
        state.forcefield_color = 1
        p = _make_player_active(state, 0, health=1000, mob_slot=pack_slot(5, 5))
        state.mobs.hpos[p.mob_slot] = (5 * 16) << 7
        state.mobs.vpos[p.mob_slot] = native_v(5 * 16) << 7
        for hub in (pack_slot(5, 3), pack_slot(5, 7)):
            state.mobs.create(hub, tile=1, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.FORCEFIELDHUB))
        gp.main_move_players(state)
        # 0x4AAEE pushes 0x80000000; the flag is what is observable here.
        assert state.dialog_first_encounter_flags & gp._DIALOG_FORCEFIELD

    def test_damage_sample_shows_the_insert_coins_box(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=150)
        p.damage_sample_timer = 1
        gp.player_damage_sample_update(state, 0)          # 0x50EB0
        assert state.dialog_message == self._lines(2)


class TestPoisonedPickups:
    """Food and potions come in two variants and the *picture* says which:
    wholesome food is 0x277B (0x51B86), a poisoned potion is 0x20FC (0x5163A)."""

    def test_poisoned_food_costs_fifty_and_shows_record_13(self):
        from gauntpy.subsystems.score import DIALOG_MESSAGES, _dialog_line

        state = _active_state()
        p = _make_player_active(state, 0, health=300)
        slot = _make_food_slot(state, poisoned=True)
        gp.player_tile_interact(state, slot, 0)
        assert p.health == 250                                   # 0x51C4A
        assert state.player_dizzy_timer[0] == 0x4B0              # 0x51C68
        # Record 13 shares the numeric line, so the 50 the caller passed is
        # drawn into it (0x4C63C-0x4C67A).
        assert state.dialog_message == [
            _dialog_line(line, 50) for line in DIALOG_MESSAGES[13]
        ]
        assert state.dialog_message[1] == "  PLAYER LOSES 50 HEALTH  "

    def test_poisoned_potion_costs_fifty_and_grants_nothing(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=300)
        slot = 48
        state.mobs.create(slot, tile=gp._POISONED_POTION_PICTURE,
                          hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POT_DESTRUCTABLE))
        gp.player_tile_interact(state, slot, 0)
        assert p.health == 250
        assert p.potionsnum == 0, "a poisoned potion is not collected"
        assert state.player_dizzy_timer[0] == 0x4B0

    def test_poison_damage_floors_at_zero(self):
        state = _active_state()
        p = _make_player_active(state, 0, health=20)
        gp.player_tile_interact(state, _make_food_slot(state, poisoned=True), 0)
        assert p.health == 0

    def test_poison_uses_the_character_random_voice_bank(self):
        state = _active_state()
        _make_player_active(state, 0, character=Character.VALKYRIE, health=300)
        slot = 48
        state.mobs.create(
            slot, tile=gp._POISONED_POTION_PICTURE, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.POT_DESTRUCTABLE),
        )

        gp.player_tile_interact(state, slot, 0)

        assert 0xB5 in state.sound_log
        assert not any(command in range(0x14, 0x18) for command in state.sound_log)

    def test_wholesome_food_clears_the_dizzy_timer(self):
        state = _active_state()
        _make_player_active(state, 0, health=300)
        state.player_dizzy_timer[0] = 500
        gp.player_tile_interact(state, _make_food_slot(state), 0)   # 0x51CDA
        assert state.player_dizzy_timer[0] == 0

    def test_the_dizzy_timer_runs_down(self):
        state = _active_state()
        _make_player_active(state, 0, health=500)
        state.player_dizzy_timer[0] = 3
        for expected in (2, 1, 0):
            gp.main_move_players(state)                             # 0x4A89E
            assert state.player_dizzy_timer[0] == expected

    def test_dizzy_timer_remaps_live_movement_by_frame_phase(self):
        cases = (
            (0x00, gp._JOY_UP, gp._JOY_UP | gp._JOY_RIGHT),
            (0x00, gp._JOY_DOWN, gp._JOY_DOWN | gp._JOY_LEFT),
            (0x10, gp._JOY_UP, gp._JOY_UP),
            (0x20, gp._JOY_UP, gp._JOY_UP | gp._JOY_LEFT),
        )
        for frame, raw_direction, expected_direction in cases:
            state = _active_state()
            _make_player_active(state, 0, health=500)
            state.frame_counter = frame
            state.level_flags_4 |= 0x80
            state.player_dizzy_timer[0] = 2
            state.player_input_raw[0] = 0xFFFF & ~raw_direction

            from unittest.mock import patch
            with patch.object(gp, "player_try_move", return_value=0xF0) as move:
                gp.main_move_players(state)

            assert move.call_args.args[2] == expected_direction

    def test_last_dizzy_frame_expires_before_input_remap(self):
        state = _active_state()
        _make_player_active(state, 0, health=500)
        state.level_flags_4 |= 0x80
        state.player_dizzy_timer[0] = 1
        state.player_input_raw[0] = 0xFFFF & ~gp._JOY_UP

        from unittest.mock import patch
        with patch.object(gp, "player_try_move", return_value=0xF0) as move:
            gp.main_move_players(state)

        assert state.player_dizzy_timer[0] == 0
        assert move.call_args.args[2] == gp._JOY_UP


# =============================================================================
# 22. Treasure bonus multiplier (0x51A16-0x51AAE)
# =============================================================================

class TestTreasureBonusMultiplier:
    """A treasure moves ``player_bonusmult`` (0x90490E, a 16-bit word) around
    the table: +2 to the collector, capped at 2 x active, -1 from everyone
    else."""

    @staticmethod
    def _treasure(state: GameState, slot: int = 55) -> int:
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        return slot

    def _party(self, count: int) -> GameState:
        state = _active_state()
        for i in range(count):
            _make_player_active(state, i, mob_slot=30 + i)
        state.level_players_active = count
        return state

    def test_solo_play_does_not_bump(self):
        """0x51A16: ``level_players_active == 1`` skips the +2 entirely."""
        state = self._party(1)
        state.players[0].bonusmult = 1
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[0].bonusmult == 1

    def test_multi_player_adds_two(self):
        state = self._party(3)
        state.players[0].bonusmult = 1
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[0].bonusmult == 3      # 0x51A2A

    def test_the_cap_is_twice_the_active_count(self):
        state = self._party(2)
        state.players[0].bonusmult = 4              # already at 2 x 2
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[0].bonusmult == 4      # +2 then clamped back

    def test_the_cap_also_trims_a_value_that_was_already_over(self):
        state = self._party(2)
        state.players[0].bonusmult = 9
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[0].bonusmult == 4      # 0x51A60

    def test_solo_cap_is_two(self):
        state = self._party(1)
        state.players[0].bonusmult = 7
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[0].bonusmult == 2

    def test_every_other_live_player_loses_one(self):
        state = self._party(4)
        for i in range(4):
            state.players[i].bonusmult = 5
        gp.player_tile_interact(state, self._treasure(state), 1)
        assert state.players[1].bonusmult == 7      # 5 + 2, cap 8
        assert [state.players[i].bonusmult for i in (0, 2, 3)] == [4, 4, 4]

    def test_the_others_floor_at_one(self):
        state = self._party(2)
        state.players[0].bonusmult = 1
        state.players[1].bonusmult = 1
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[1].bonusmult == 1      # 0x51A84 ``bls``

    def test_a_dead_player_keeps_its_multiplier(self):
        """0x51A74 skips a player whose health is zero."""
        state = self._party(3)
        for i in range(3):
            state.players[i].bonusmult = 4
        state.players[2].health = 0
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[1].bonusmult == 3
        assert state.players[2].bonusmult == 4

    def test_the_victims_panel_is_marked(self):
        state = self._party(2)
        state.players[0].bonusmult = 3
        state.players[1].bonusmult = 3
        state.health_dirty = [0, 0, 0, 0]
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.health_dirty[1] == 1           # 0x51AA2

    def test_the_score_uses_the_updated_multiplier(self):
        """0x51AC4 runs after the block, so the award sees the new value."""
        state = self._party(2)
        state.players[0].bonusmult = 1
        state.players[0].score = 0
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[0].bonusmult == 3
        assert state.players[0].score == 300        # 100 x the *new* 3

    def test_the_multiplier_is_a_16_bit_word(self):
        state = self._party(2)
        state.players[0].bonusmult = 0xFFFF
        gp.player_tile_interact(state, self._treasure(state), 0)
        # ``addq.w #2`` on 0xFFFF wraps to 1, which is under the 2 x 2 cap and
        # so survives the clamp -- the width is observable.
        assert state.players[0].bonusmult == 1

    def test_treasure_rooms_skip_the_block(self):
        """0x519FE/0x51A08: mazes 0x68-0x72 branch away before it."""
        state = self._party(3)
        state.mazenum_current = 0x68
        state.players[0].bonusmult = 1
        gp.player_tile_interact(state, self._treasure(state), 0)
        assert state.players[0].bonusmult == 1

    def test_a_bag_uses_the_same_block_as_a_coin_pile(self):
        state = self._party(2)
        state.players[0].bonusmult = 1
        slot = 56
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE_BAG))
        gp.player_tile_interact(state, slot, 0)
        assert state.players[0].bonusmult == 3

    def test_a_chest_does_not_reach_the_block_at_all(self):
        """0x2F is unhandled by the tile dispatch, so no multiplier moves."""
        state = self._party(2)
        state.players[0].keysnum = 1
        state.players[0].bonusmult = 1
        slot = 56
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE_LOCKED))
        assert gp.player_tile_interact(state, slot, 0) == 0
        assert state.players[0].bonusmult == 1


# =============================================================================
# 23. Timed-power naming, resolved from the ROM's consumers
# =============================================================================

class TestTimedPowerSemantics:

    def test_bit_9_is_repulsiveness_not_reflection(self):
        """0x4185C ``btst #1`` on the powers high byte is the make-monsters-flee
        test, and 0x4176C ``btst #0`` is the invisible-so-untargetable one.
        Reflection is a different power: shots read bit 10 at 0x4B4B0."""
        from gauntpy.constants import PlayerPower
        from gauntpy.subsystems import shots

        assert int(PlayerPower.REPULSE) == 0x0200
        assert int(PlayerPower.INVIS) == 0x0100
        assert int(PlayerPower.REFLECT) == 0x0400
        assert shots._POWER_REFLECT == int(PlayerPower.REFLECT)

    def test_the_repulse_pickup_arms_the_repulse_timer(self):
        state = _active_state()
        _make_player_active(state, 0, character=Character.WIZARD)
        slot = 57
        state.mobs.create(slot, tile=1, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POWER_REPULSE))
        gp.player_tile_interact(state, slot, 0)
        assert state.player_repulse_timer[0] == gp._CHARACTER_REPULSE_TIMER_INIT[2]
        assert state.players[0].powers & int(
            __import__("gauntpy.constants", fromlist=["PlayerPower"]).PlayerPower.REPULSE
        )

    def test_the_repulse_timer_expiry_clears_bit_9(self):
        from gauntpy.constants import PlayerPower

        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.powers = int(PlayerPower.REPULSE)
        state.player_repulse_timer[0] = 1
        gp.main_move_players(state)                       # 0x4A826
        assert not (p.powers & int(PlayerPower.REPULSE))

    def test_bit_13_is_a_damage_over_time_flag_not_invulnerability(self):
        """The 0x3B pickup arms 900 frames of 1-2 health lost every eighth
        frame (0x5189E then 0x4A838-0x4A85E) -- the opposite of protection."""
        from gauntpy.constants import PlayerPower

        assert int(PlayerPower.ACID_AFFLICTION) == 0x2000
        assert int(PlayerPower.INVULN) == int(PlayerPower.ACID_AFFLICTION)

        state = _active_state()
        p = _make_player_active(state, 0, health=1000)
        slot = 58
        state.mobs.create(slot, tile=1, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POWER_INVULN))
        gp.player_tile_interact(state, slot, 0)
        assert p.acid_timer == 0x384
        assert p.powers & int(PlayerPower.ACID_AFFLICTION)

        state.frame_counter = 8          # gated frame, bit 3 set -> 1 point
        gp.main_move_players(state)
        assert p.health < 1000, "the 0x3B pickup hurts, it does not protect"

    def test_the_affliction_bit_clears_with_its_countdown(self):
        from gauntpy.constants import PlayerPower

        state = _active_state()
        p = _make_player_active(state, 0, health=500)
        p.powers = int(PlayerPower.ACID_AFFLICTION)
        p.acid_timer = 1
        state.frame_counter = 1          # ungated, so no damage this frame
        gp.main_move_players(state)                       # 0x4A880
        assert p.acid_timer == 0
        assert not (p.powers & int(PlayerPower.ACID_AFFLICTION))


# =============================================================================
# 24. The asynchronous transporter / corner-squeeze transition
# =============================================================================

class TestTransportTransition:
    """players.py produces (pad, landing cell, phase, animation MOB) and WP-14's
    ``main_score_update`` loop 2 consumes: dissolve at step 5, move at 0x0B,
    re-form at 0x10, retire past 0x16.  Nothing commits immediately."""

    _HERO_PICTURE = 0x1E0D

    def _world(self):
        state = _active_state()
        player_slot = _pack(5, 6)
        p = _make_player_active(state, 0, health=500, mob_slot=player_slot)
        state.mobs.create(
            player_slot,
            tile=self._HERO_PICTURE,
            hpos=(5 * 16 + 8) << 7,
            vpos=native_v(5 * 16 + 8) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART),
            state=0,
        )
        for row, col in ((5, 5), (5, 9)):
            state.mobs.create(_pack(row, col), tile=0, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.TRANSPORTER))
        return state, p, _pack(5, 5)

    @staticmethod
    def _frame(state: GameState) -> None:
        """The two loop members this transition spans, in frame order."""
        from gauntpy.subsystems.score import main_score_update

        gp.main_move_players(state)
        main_score_update(state)

    def _run(self, state: GameState, frames: int = 80):
        trace = []
        for frame in range(frames):
            state.frame_counter = frame
            self._frame(state)
            player_slot = state.players[0].mob_slot
            trace.append((
                state.player_tport_phase[0],
                state.mobs.picture[player_slot],
                hpos_x(state.mobs.hpos[player_slot]),
                vpos_y(state.mobs.vpos[player_slot]),
                state.mobs.picture[0x19],
            ))
            if state.player_tport_phase[0] < 0:
                break
        return trace

    def test_loop_2_drives_the_phase(self):
        state, _, source = self._world()
        gp.player_tport(state, 0, source)
        assert state.player_tport_phase[0] == 0
        self._frame(state)
        assert state.player_tport_phase[0] == 1, "loop 2 owns the counter"

    def test_the_hero_dissolves_then_moves_then_re_forms(self):
        state, _, source = self._world()
        state.player_input_raw[0] = 0xFFFF & ~0x20  # LEFT
        gp.player_tport(state, 0, source)
        trace = self._run(state)

        # Step 5 (phase 10) replaces the hero with the ROM flash picture.
        save = next(i for i, t in enumerate(trace) if t[0] == 10)
        assert trace[save][1] == 0x1709
        # The move lands at the milestone phase and not before.
        moved = next(i for i, t in enumerate(trace) if (t[2], t[3]) != (88, 88))
        assert trace[moved][0] >= gp._TRANSITION_MOVE_PHASE
        assert (trace[moved][2], trace[moved][3]) == (8 * 16 - 4, 5 * 16)
        # The flash frame persists for the whole flight.
        assert trace[moved][1] == 0x1709
        effect_slot = 0x19
        assert hpos_x(state.mobs.hpos[effect_slot]) == 8 * 16 - 4
        assert vpos_y(state.mobs.vpos[effect_slot]) == 5 * 16
        # Step 0x10 (phase 32) puts the picture back.
        restore = next(i for i, t in enumerate(trace) if t[0] == 32)
        assert trace[restore][1] == self._HERO_PICTURE

    def test_the_transition_retires_itself(self):
        state, _, source = self._world()
        gp.player_tport(state, 0, source)
        trace = self._run(state)
        assert trace[-1][0] < 0, "phase returns to its idle sentinel"
        assert state.mobs.picture[0x19] == 0, "the animation MOB is released"
        slot = state.players[0].mob_slot
        assert (
            hpos_x(state.mobs.hpos[slot]),
            vpos_y(state.mobs.vpos[slot]),
        ) == (10 * 16 - 4, 4 * 16)

    def test_gameplay_is_frozen_while_in_flight(self):
        """0x4A7E8: a non-negative phase skips the rest of the active path."""
        state, p, source = self._world()
        p.keysnum = 0
        state.player_input_raw[0] = 0xFFFF & ~0x10      # RIGHT held
        gp.player_tport(state, 0, source)
        p.health = 500
        p.anim_counter = 0
        state.player_invis_timer[0] = 5

        for _ in range(6):
            self._frame(state)

        assert p.anim_counter == 0, "no animation tick while transporting"
        assert state.player_invis_timer[0] == 5, "no power timers either"
        assert state.mobs.picture[1] == 0, "and no shooting"

    def test_the_camera_destination_is_not_dragged_back(self):
        state, _, source = self._world()
        gp.player_tport(state, 0, source)
        for _ in range(4):
            self._frame(state)
        assert state.player_tile_or_tport_dest[0] == _pack(4, 10), (
            "player_tile_or_tport_dest must keep pointing at the destination"
        )

    def test_player_transition_does_not_claim_a_shared_effect_slot(self):
        """0x47324 calls tport_player_move; no 0x0D-0x10 sparkle is spawned."""
        state, _, source = self._world()
        gp.player_tport(state, 0, source)
        for _ in range(30):
            self._frame(state)
        assert not any(state.mobs.picture[0x0D + c] for c in range(4))

    def test_a_second_transporter_hop_works(self):
        """The machine must be reusable, not one-shot."""
        state, _, source = self._world()
        gp.player_tport(state, 0, source)
        self._run(state)
        assert gp.player_tport(state, 0, _pack(5, 9)) == -2
        trace = self._run(state)
        assert trace[-1][0] < 0
        slot = state.players[0].mob_slot
        assert (
            hpos_x(state.mobs.hpos[slot]),
            vpos_y(state.mobs.vpos[slot]),
        ) == (6 * 16 - 4, 4 * 16)

    def test_a_full_game_frame_drives_it(self):
        """Through ``tick`` -- every loop member in its real order."""
        from gauntpy.mainloop import tick

        state, _, source = self._world()
        gp.player_tport(state, 0, source)
        for _ in range(80):
            tick(state)
            if state.player_tport_phase[0] < 0:
                break
        assert state.player_tport_phase[0] < 0
        slot = state.players[0].mob_slot
        assert state.mobs.picture[slot] == self._HERO_PICTURE
        assert (
            hpos_x(state.mobs.hpos[slot]),
            vpos_y(state.mobs.vpos[slot]),
        ) == (10 * 16 - 4, 4 * 16)


class TestCornerSqueezeUsesTheSameTransition:

    def _world(self):
        from gauntpy.constants import PlayerPower

        state = _active_state()
        player_slot = _pack(5, 6)
        p = _make_player_active(state, 0, health=500, mob_slot=player_slot)
        p.powers = int(PlayerPower.TRANSPORT)
        state.mobs.create(
            player_slot,
            tile=0x1E0D,
            hpos=(5 * 16 + 8) << 7,
            vpos=native_v(5 * 16 + 8) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART),
            state=0,
        )
        state.movement_type = 1
        return state, p

    def test_it_arms_rather_than_commits(self):
        state, player = self._world()
        before = (
            state.mobs.hpos[player.mob_slot], state.mobs.vpos[player.mob_slot],
        )

        assert gp.corner_squeeze_geometry(
            state, player.mob_slot, 0, 0x10,        # JOY_RIGHT
        ) == -2

        assert state.player_tport_phase[0] == 0
        assert state.mobs.picture[0x19] == gp._TPORT_ARRIVAL_PICTURE
        assert (
            state.mobs.hpos[player.mob_slot], state.mobs.vpos[player.mob_slot],
        ) == before

    def test_it_completes_through_loop_2(self):
        from gauntpy.subsystems.score import main_score_update

        state, player = self._world()
        gp.corner_squeeze_geometry(state, player.mob_slot, 0, 0x10)
        target = state.player_tile_or_tport_dest[0]
        for frame in range(80):
            state.frame_counter = frame
            gp.main_move_players(state)
            main_score_update(state)
            if state.player_tport_phase[0] < 0:
                break
        assert state.player_tport_phase[0] < 0
        slot = state.players[0].mob_slot
        assert hpos_x(state.mobs.hpos[slot]) == (target & 0x1F) * 16 - 4
        assert vpos_y(state.mobs.vpos[slot]) == (target >> 5) * 16

    def test_held_direction_does_not_redirect_corner_squeeze_landing(self):
        from gauntpy.subsystems.input import JOY_IDLE, JOY_RIGHT
        from gauntpy.subsystems.score import main_score_update

        state, player = self._world()
        gp.corner_squeeze_geometry(state, player.mob_slot, 0, JOY_RIGHT)
        target = state.player_tile_or_tport_dest[0]
        state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT

        for frame in range(80):
            state.frame_counter = frame
            gp.main_move_players(state)
            main_score_update(state)
            if state.player_tport_phase[0] < 0:
                break

        assert state.players[0].mob_slot == target


# =============================================================================
# 25. Secret-room objective reporting (WP-15's secret_trick_progress/_set)
#
# The ROM guards every site with ``cmpi.b #<code>,secret_trick_id`` and then
# either bumps or assigns that player's ``secret_tricks_flags`` byte.  Full map
# of the sites this subsystem owns, by ROM address:
#
#   0x5027E / 0x509E4  trick 0x56  transporter pads, source and destination
#   0x50C30 / 0x50C42  tricks 1/2  transported next to acid / death
#   0x5140A            trick 0x0B  fooled by a fake exit          (assignment)
#   0x514D4            trick 0x0C  key pickup
#   0x5179C            trick 0x0C  potion pickup
#   0x518B2            trick 0x08  invulnerability pickup         (assignment)
#   0x518FA / 0x51908  tasks 0x51/0x5D  hidden pot
#   0x519C2 / 0x519CE / 0x519DA  0x0E, 0x50, 0x5A  treasure -- reported by
#                                exits.treasure_collected, not repeated here
#   0x51C0C / 0x51CEE  trick 0x0D  food, both variants
# =============================================================================

def _trick_state(trick_id: int) -> GameState:
    state = _active_state()
    state.secret_trick_id = trick_id
    return state


class TestGreedyObjectiveSites:
    """0x514D4 and 0x5179C -- keys and potions both feed trick 0x0C."""

    def test_key_pickup_reports_progress(self):
        state = _trick_state(gp._TRICK_NOGREEDY1)
        p = _make_player_active(state, 0)
        slot = _make_key_slot(state)
        gp.player_tile_interact(state, slot, 0)
        assert state.secret_tricks_flags[0] == 1
        assert p.keysnum == 1

    def test_potion_pickup_reports_progress(self):
        state = _trick_state(gp._TRICK_NOGREEDY1)
        _make_player_active(state, 0)
        slot = 34
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POT_DESTRUCTABLE))
        gp.player_tile_interact(state, slot, 0)
        assert state.secret_tricks_flags[0] == 1

    def test_progress_accumulates_across_both(self):
        """One shared counter -- 0x514DE and 0x517AA bump the same byte."""
        state = _trick_state(gp._TRICK_NOGREEDY1)
        _make_player_active(state, 0)
        gp.player_tile_interact(state, _make_key_slot(state), 0)
        slot = 34
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POT_DESTRUCTABLE))
        gp.player_tile_interact(state, slot, 0)
        assert state.secret_tricks_flags[0] == 2

    def test_a_poisoned_potion_is_not_greed(self):
        """0x5179C sits on the good-potion path, past the 0x5163A branch."""
        state = _trick_state(gp._TRICK_NOGREEDY1)
        _make_player_active(state, 0)
        slot = 34
        state.mobs.create(slot, tile=gp._POISONED_POTION_PICTURE,
                          hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POT_DESTRUCTABLE))
        gp.player_tile_interact(state, slot, 0)
        assert state.secret_tricks_flags[0] == 0

    def test_a_different_objective_is_not_touched(self):
        """The ``cmpi.b`` guard: any other level objective ignores the site."""
        state = _trick_state(gp._TRICK_NOUSEINVUL)
        _make_player_active(state, 0)
        gp.player_tile_interact(state, _make_key_slot(state), 0)
        assert state.secret_tricks_flags[0] == 0

    def test_only_the_collecting_player_is_credited(self):
        state = _trick_state(gp._TRICK_NOGREEDY1)
        _make_player_active(state, 0)
        _make_player_active(state, 1)
        gp.player_tile_interact(state, _make_key_slot(state), 1)
        assert state.secret_tricks_flags == [0, 1, 0, 0]


class TestKeyPickupRomTail:
    """0x514EA-0x514FE, the instructions immediately after the trick site."""

    def test_a_key_clears_the_escape_timer(self):
        state = _active_state()
        _make_player_active(state, 0)
        state.escape_timer = 900
        gp.player_tile_interact(state, _make_key_slot(state), 0)
        assert state.escape_timer == 0        # 0x514EA: clr.w (a3)

    def test_a_key_is_worth_a_hundred(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.bonusmult = 1
        gp.player_tile_interact(state, _make_key_slot(state), 0)
        assert p.score == 100                 # 0x514F4: pea $64

    def test_the_key_award_uses_the_bonus_multiplier(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.bonusmult = 3
        gp.player_tile_interact(state, _make_key_slot(state), 0)
        assert p.score == 300                 # 0x514FE: player_add_score_with_mult
        assert state.score_dirty[0] == 1

    def test_the_key_still_sounds_and_counts(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        gp.player_tile_interact(state, _make_key_slot(state), 0)
        assert p.keysnum == 1
        assert 0x13 in _emitted(state)


class TestInvulnerabilityObjectiveIsAnAssignment:
    """0x518B2 -- ``move.b #$1``, not ``addq.b #1``."""

    def _pickup(self, state):
        slot = 35
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POWER_INVULN))
        gp.player_tile_interact(state, slot, 0)

    def test_pickup_sets_the_flag(self):
        state = _trick_state(gp._TRICK_NOUSEINVUL)
        _make_player_active(state, 0)
        self._pickup(state)
        assert state.secret_tricks_flags[0] == 1

    def test_a_second_pickup_does_not_push_the_byte_past_one(self):
        state = _trick_state(gp._TRICK_NOUSEINVUL)
        _make_player_active(state, 0)
        self._pickup(state)
        self._pickup(state)
        assert state.secret_tricks_flags[0] == 1, "0x518C8 assigns"

    def test_other_powerups_do_not_report(self):
        state = _trick_state(gp._TRICK_NOUSEINVUL)
        _make_player_active(state, 0)
        slot = 36
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.POWER_INVIS))
        gp.player_tile_interact(state, slot, 0)
        assert state.secret_tricks_flags[0] == 0

    def test_the_power_itself_still_arms(self):
        state = _trick_state(gp._TRICK_NOUSEINVUL)
        p = _make_player_active(state, 0)
        self._pickup(state)
        assert p.acid_timer == gp._INVULN_TIMER_LOAD


class TestHiddenPotObjectiveCodes:
    """0x518FA/0x51908 -- two codes, one shared ``addq.b #1`` at 0x5191A."""

    def _pot(self, state):
        slot = 37
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.HIDDENPOT))
        gp.player_tile_interact(state, slot, 0)

    def test_code_51_reports(self):
        state = _trick_state(gp._TASK_HIDDENPOT_A)
        _make_player_active(state, 0)
        self._pot(state)
        assert state.secret_tricks_flags[0] == 1

    def test_code_5d_reports(self):
        state = _trick_state(gp._TASK_HIDDENPOT_B)
        _make_player_active(state, 0)
        self._pot(state)
        assert state.secret_tricks_flags[0] == 1

    def test_the_two_codes_never_both_fire(self):
        """0x51904 ``beq`` jumps *into* the bump, so it happens once."""
        state = _trick_state(gp._TASK_HIDDENPOT_A)
        _make_player_active(state, 0)
        self._pot(state)
        self._pot(state)
        assert state.secret_tricks_flags[0] == 2

    def test_an_unrelated_code_is_ignored(self):
        state = _trick_state(0x50)      # "collect 6 treasures", not the pot
        _make_player_active(state, 0)
        self._pot(state)
        assert state.secret_tricks_flags[0] == 0

    def test_the_potion_is_still_collected(self):
        state = _trick_state(gp._TASK_HIDDENPOT_A)
        p = _make_player_active(state, 0)
        self._pot(state)
        assert p.potionsnum == 1

    def test_special_potions_grant_stat_powers_and_write_their_icons(self):
        from gauntpy.subsystems import score

        for item_id, mask in enumerate((
            0x0002, 0x0001, 0x0020, 0x0010, 0x0008, 0x0004,
        )):
            state = _active_state()
            player = _make_player_active(state, 0)
            slot = 37
            state.mobs.create(
                slot, tile=0xA728 + item_id * 4, hpos=0, vpos=0,
                obj_type=int(MazeObjIds.HIDDENPOT),
            )

            assert gp.player_tile_interact(state, slot, 0) == -1

            assert player.powers & mask
            assert player.potionsnum == 0
            row = score.PLAYER_NAME_ROW
            bit = mask.bit_length() - 1
            column = score.POWER_ICON_COLUMNS[bit]
            assert state.alpha_ram[
                row * score.ALPHA_ROW_STRIDE + column
            ] == score.POWER_ICON_WORDS[bit]


class TestFoodAndTreasureObjectiveSites:
    """0x51C0C/0x51CEE (food) and 0x519C2 (treasure).

    The ROM's compares are 0x0D for food and 0x0E for treasure, which is the
    opposite way round from WP-15's ``TRICK_NOGREEDY2``/``TRICK_DIET``
    comments.  These follow the ROM.  The treasure codes themselves are part of
    ``exits.treasure_collected``'s block, so this arm only proves it does not
    report them a second time.
    """

    def _treasure(self, state, player_index=0):
        slot = 38
        state.mobs.create(slot, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.TREASURE))
        gp.player_tile_interact(state, slot, player_index)

    def test_wholesome_food_reports(self):
        state = _trick_state(gp._TRICK_FOOD)
        _make_player_active(state, 0, health=100)
        gp.player_tile_interact(state, _make_food_slot(state), 0)
        assert state.secret_tricks_flags[0] == 1

    def test_poisoned_food_reports_too(self):
        """0x51C0C is on the poisoned path and bumps the same byte."""
        state = _trick_state(gp._TRICK_FOOD)
        _make_player_active(state, 0, health=500)
        slot = _make_food_slot(state, poisoned=True)
        gp.player_tile_interact(state, slot, 0)
        assert state.secret_tricks_flags[0] == 1

    def test_a_treasure_reports_exactly_once(self):
        """The 0x519C2 block lives in exits.treasure_collected; this arm must
        not add a second bump or a "collect six" task would finish in three."""
        from gauntpy.subsystems import exits

        state = _trick_state(exits.TRICK_NOGREEDY2)
        _make_player_active(state, 0)
        self._treasure(state)
        assert state.secret_tricks_flags[0] == 1

    def test_six_treasures_take_six_pickups(self):
        from gauntpy.subsystems import exits

        state = _trick_state(0x50)
        _make_player_active(state, 0)
        for _ in range(6):
            self._treasure(state)
        assert state.secret_tricks_flags[0] == 6
        assert exits.secret_trick_check is not None

    def test_food_and_treasure_do_not_cross_report(self, monkeypatch):
        """This arm contributes no objective progress of its own.

        With WP-15's write site stubbed out, a treasure pickup must leave the
        byte alone -- whatever code the real ``treasure_collected`` reports is
        that routine's business.  (For the record, the ROM compares 0x0E at
        0x519C2 for treasure and 0x0D at 0x51C0C/0x51CEE for food; exits.py
        currently reports ``TRICK_NOGREEDY2`` = 0x0D for treasure, so the two
        share a code they should not.)
        """
        from gauntpy.subsystems import exits

        state = _trick_state(gp._TRICK_FOOD)
        _make_player_active(state, 0)
        monkeypatch.setattr(exits, "treasure_collected", lambda *a, **k: None)
        self._treasure(state)
        assert state.secret_tricks_flags[0] == 0

    def test_treasure_credit_is_unaffected(self):
        state = _trick_state(gp._TRICK_FOOD)
        _make_player_active(state, 0)
        self._treasure(state)
        assert state.player_treascount[0] == 1
        assert state.level_treasures == 1


class TestFakeExitObjective:
    """0x513DA -- hpos bit 4 makes an exit an illusion (both 0x10 and 0x11)."""

    def _exit_slot(self, state, fake: bool,
                   obj_type: int = int(MazeObjIds.EXIT)) -> int:
        slot = 39
        state.mobs.create(slot, tile=0,
                          hpos=gp._FAKE_EXIT_FLAG if fake else 0,
                          vpos=0, obj_type=obj_type)
        return slot

    def test_a_fake_exit_does_not_exit(self, monkeypatch):
        state = _trick_state(gp._TRICK_NOFOOLED)
        _make_player_active(state, 0)
        called = []
        monkeypatch.setattr(gp, "player_exit_sequence",
                            lambda *a, **k: called.append(a))
        gp.player_tile_interact(state, self._exit_slot(state, True), 0)
        assert called == [], "0x513EA takes the illusion branch"

    def test_a_fake_exit_satisfies_the_objective(self):
        state = _trick_state(gp._TRICK_NOFOOLED)
        _make_player_active(state, 0)
        gp.player_tile_interact(state, self._exit_slot(state, True), 0)
        assert state.secret_tricks_flags[0] == 1

    def test_the_objective_is_an_assignment(self):
        """0x5141E ``move.b #$1`` -- being fooled twice is still 1."""
        state = _trick_state(gp._TRICK_NOFOOLED)
        _make_player_active(state, 0)
        for _ in range(2):
            gp.player_tile_interact(state, self._exit_slot(state, True), 0)
        assert state.secret_tricks_flags[0] == 1

    def test_collision_record_is_removed_but_exit_descriptor_remains(self):
        state = _trick_state(gp._TRICK_NOFOOLED)
        _make_player_active(state, 0)
        slot = self._exit_slot(state, True)
        from gauntpy.playfield_vram import (
            read_tile_descriptor, write_tile_descriptor,
        )
        exit_descriptor = (0x39E, 0x39F, 6, 6)
        write_tile_descriptor(state, slot, exit_descriptor)
        gp.player_tile_interact(state, slot, 0)
        assert state.mobs.obj_type(slot) == 0     # 0x51404
        assert read_tile_descriptor(state, slot) == exit_descriptor, \
            "moblist_remove_and_clear does not call pf_replace"

    def test_a_fake_exit_speaks_record_thirty(self):
        """0x513EC pushes mask 0x40000000 -- bit 30 selects the record.

        WP-14's ``dialog_first_encounter`` returns without a box when the
        record is NULL, so the observable is the one-shot flag it latches.
        """
        state = _trick_state(gp._TRICK_NOFOOLED)
        _make_player_active(state, 0)
        gp.player_tile_interact(state, self._exit_slot(state, True), 0)
        assert state.dialog_first_encounter_flags & gp._DIALOG_FAKE_EXIT

    def test_a_real_exit_still_exits(self, monkeypatch):
        state = _trick_state(gp._TRICK_NOFOOLED)
        _make_player_active(state, 0)
        called = []
        monkeypatch.setattr(gp, "player_exit_sequence",
                            lambda *a, **k: called.append(a))
        gp.player_tile_interact(state, self._exit_slot(state, False), 0)
        assert len(called) == 1
        assert state.secret_tricks_flags[0] == 0

    def test_exitto6_takes_the_same_branch(self, monkeypatch):
        """0x511EC dispatches types 0x10 and 0x11 to the one arm."""
        state = _trick_state(gp._TRICK_NOFOOLED)
        _make_player_active(state, 0)
        monkeypatch.setattr(gp, "player_exit_sequence", lambda *a, **k: None)
        slot = self._exit_slot(state, True, int(MazeObjIds.EXITTO6))
        gp.player_tile_interact(state, slot, 0)
        assert state.secret_tricks_flags[0] == 1


class TestTransporterObjectiveSites:
    """0x5027E/0x509E4 (pad bitmask) and 0x50C30/0x50C42 (landing)."""

    def _world(self, trick_id: int):
        state = _trick_state(trick_id)
        _make_player_active(state, 0, mob_slot=30)
        state.mobs.hpos[30] = (5 * 16 + 8) << 7
        state.mobs.vpos[30] = native_v(5 * 16 + 8) << 7
        for row, col in ((5, 5), (5, 9)):
            state.mobs.create(_pack(row, col), tile=0, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.TRANSPORTER))
        return state, _pack(5, 5), _pack(5, 9)

    def test_both_pads_are_recorded(self):
        """0x5027E marks the source, 0x509E4 the destination."""
        state, source, dest = self._world(gp._TRICK_VISIT_TPORTS)
        gp.player_tport(state, 0, source)
        pads = gp._tport_pos_table(state)
        expected = (
            (1 << (pads.index(source) + 1))
            | (1 << (pads.index(dest) + 1))
        )
        assert state.secret_tricks_flags[0] == expected

    def test_the_mask_accumulates_rather_than_counting(self):
        state, source, _ = self._world(gp._TRICK_VISIT_TPORTS)
        gp.player_tport(state, 0, source)
        first = state.secret_tricks_flags[0]
        state.player_tport_phase[0] = -1
        gp.player_tport(state, 0, source)
        assert state.secret_tricks_flags[0] == first, "OR, not add"

    def test_a_different_objective_leaves_the_mask_alone(self):
        state, source, _ = self._world(gp._TRICK_NOGREEDY1)
        gp.player_tport(state, 0, source)
        assert state.secret_tricks_flags[0] == 0

    def _land_beside(self, trick_id: int, monster_type: int):
        state, source, dest = self._world(trick_id)
        neighbour = gp._direction_neighbor(dest, 0)
        state.mobs.create(neighbour, tile=0x2000, hpos=0, vpos=0,
                          obj_type=monster_type)
        gp.player_tport(state, 0, source)
        return state

    def test_transported_beside_acid_wins_trick_one(self):
        state = self._land_beside(gp._TRICK_TRANSPORT1,
                                  int(MazeObjIds.MONST_ACID))
        assert state.secret_player == 0        # 0x50C52

    def test_transported_beside_death_wins_trick_two(self):
        state = self._land_beside(gp._TRICK_TRANSPORT2,
                                  int(MazeObjIds.MONST_DEATH))
        assert state.secret_player == 0

    def test_the_two_landing_tricks_want_different_monsters(self):
        """0x50C3A wants 0x19 and 0x50C4C wants 0x18 -- not interchangeable."""
        state = self._land_beside(gp._TRICK_TRANSPORT1,
                                  int(MazeObjIds.MONST_DEATH))
        assert state.secret_player == -1
        state = self._land_beside(gp._TRICK_TRANSPORT2,
                                  int(MazeObjIds.MONST_ACID))
        assert state.secret_player == -1

    def test_landing_beside_nothing_wins_nothing(self):
        state, source, _ = self._world(gp._TRICK_TRANSPORT1)
        gp.player_tport(state, 0, source)
        assert state.secret_player == -1

    def test_transporting_into_an_exit_wins_trick_three(self):
        state, _, _ = self._world(3)
        landing = _pack(6, 6)
        state.mobs.create(
            landing, tile=0x8001, hpos=6 * 16 << 7,
            vpos=native_v(6 * 16) << 7, obj_type=int(MazeObjIds.EXIT),
        )

        gp._move_player_to_slot(state, 0, landing)

        assert state.secret_player == 0

    def test_corner_transport_through_a_secret_wall_wins_trick_four(self):
        state = _trick_state(4)
        source = _pack(5, 5)
        landing = _pack(6, 6)
        state.mobs.create(
            source, tile=0x2000, hpos=(5 * 16 - 4) << 7,
            vpos=native_v(5 * 16) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART),
        )
        player = state.players[0]
        player.status = int(PlayerStatus.ALIVE_HERE)
        player.mob_slot = source
        state.mobs.create(
            landing, tile=0x8000, hpos=6 * 16 << 7,
            vpos=native_v(6 * 16) << 7,
            obj_type=int(MazeObjIds.WALL_SECRET),
        )
        state.player_tport_route_state[0] = source
        state.player_tport_type[0] = 0
        state.player_tile_or_tport_dest[0] = landing

        gp.tport_player_move(state, 0)

        assert state.secret_player == 0
        assert state.mobs.obj_type(landing) == int(MazeObjIds.PLAYERSTART)


class TestTransporterArrivalInteracts:
    """0x50A18-0x50A66 -- the four cells around the destination are entered."""

    def _world(self):
        state = _active_state()
        _make_player_active(state, 0, mob_slot=30)
        state.mobs.hpos[30] = (5 * 16 + 8) << 7
        state.mobs.vpos[30] = native_v(5 * 16 + 8) << 7
        for row, col in ((5, 5), (5, 9)):
            state.mobs.create(_pack(row, col), tile=0, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.TRANSPORTER))
        return state, _pack(5, 5), _pack(5, 9)

    def test_a_neighbouring_key_is_picked_up(self):
        state, source, dest = self._world()
        neighbour = gp._direction_neighbor(dest, 2)
        state.mobs.create(neighbour, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.KEY))
        gp.player_tport(state, 0, source)
        assert state.players[0].keysnum == 1

    def test_all_four_orthogonal_neighbours_are_visited(self):
        state, source, dest = self._world()
        for direction in (0, 2, 4, 6):
            state.mobs.create(gp._direction_neighbor(dest, direction),
                              tile=0, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.KEY))
        gp.player_tport(state, 0, source)
        assert state.players[0].keysnum == 4

    def test_diagonals_are_not_visited(self):
        state, source, dest = self._world()
        for direction in (1, 3, 5, 7):
            state.mobs.create(gp._direction_neighbor(dest, direction),
                              tile=0, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.KEY))
        gp.player_tport(state, 0, source)
        assert state.players[0].keysnum == 0

    def test_a_mid_cell_mob_is_rejected(self):
        """0x50BF2 -- palette nibble >= 0x0C means it is not settled here."""
        state, source, dest = self._world()
        neighbour = gp._direction_neighbor(dest, 2)
        state.mobs.create(neighbour, tile=0, hpos=0x0C, vpos=0,
                          obj_type=int(MazeObjIds.KEY))
        gp.player_tport(state, 0, source)
        assert state.players[0].keysnum == 0

    def test_placeholder_pictures_are_rejected(self):
        """0x50C02/0x50C16 -- 0x8001 and 0x8000 mean nothing is drawn."""
        for picture in (0x8000, 0x8001):
            state, source, dest = self._world()
            neighbour = gp._direction_neighbor(dest, 2)
            state.mobs.create(neighbour, tile=picture, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.KEY))
            gp.player_tport(state, 0, source)
            assert state.players[0].keysnum == 0, hex(picture)

    def test_the_transition_still_arms(self):
        """The scan runs at arm time and must not commit the move (0x5060A)."""
        state, source, dest = self._world()
        neighbour = gp._direction_neighbor(dest, 2)
        state.mobs.create(neighbour, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.KEY))
        assert gp.player_tport(state, 0, source) == -2
        assert state.player_tport_phase[0] == 0
        assert hpos_x(state.mobs.hpos[30]) == 5 * 16 + 8, "no immediate move"


# =============================================================================
# 34. The stun gate in the active phase (main_move_players 0x4A908-0x4A91C)
# =============================================================================

class TestStunDelayGate:
    """``player_stundelay`` (0x904A54) is decremented once per frame and, while
    it is still non-zero afterwards, the ROM jumps straight to the forcefield
    check -- the speed lookup, the facing update, the shot test and
    ``player_try_move`` are all skipped."""

    @staticmethod
    def _moving_state(stundelay: int = 0):
        from gauntpy.subsystems.input import JOY_IDLE, JOY_RIGHT

        state = _active_state()
        p = _make_player_active(state, 0, health=1000)
        p.stundelay = stundelay
        state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT   # active low: held
        return state, p

    def test_the_countdown_runs_down_once_per_frame(self):
        state, p = self._moving_state(stundelay=3)
        for expected in (2, 1, 0):
            gp.main_move_players(state)
            assert p.stundelay == expected

    def test_a_stunned_player_does_not_move(self, monkeypatch):
        moves = []
        monkeypatch.setattr(gp, "player_try_move",
                            lambda *a, **k: moves.append(a))
        state, _p = self._moving_state(stundelay=3)
        gp.main_move_players(state)
        gp.main_move_players(state)
        assert moves == [], "0x4A91C skips player_try_move while stunned"

    def test_the_frame_the_countdown_expires_moves_again(self, monkeypatch):
        moves = []
        monkeypatch.setattr(gp, "player_try_move",
                            lambda *a, **k: moves.append(a))
        state, p = self._moving_state(stundelay=1)
        gp.main_move_players(state)
        assert p.stundelay == 0
        assert len(moves) == 1, "0x4A918 tests the value *after* the decrement"

    def test_a_stunned_player_does_not_pick_things_up(self, monkeypatch):
        picked = []
        monkeypatch.setattr(gp, "player_tile_interact",
                            lambda *a, **k: picked.append(a))
        state, _p = self._moving_state(stundelay=5)
        gp.main_move_players(state)
        assert picked == []

    def test_a_stunned_player_is_still_charged_by_a_forcefield(self):
        """0x4A91C branches *to* the forcefield check, not past it."""
        from gauntpy.coords import pack_slot

        state, p = self._moving_state(stundelay=5)
        state.forcefield_color = 1
        p.mob_slot = pack_slot(5, 5)
        state.mobs.hpos[p.mob_slot] = (5 * 16) << 7
        state.mobs.vpos[p.mob_slot] = native_v(5 * 16) << 7
        state.forcefield_segment_table = [0x8000 | (3 << 10) | pack_slot(5, 3)]
        state.forcefield_segments_ready = True

        gp.main_move_players(state)

        assert p.health == 1000 - 2       # Warrior, unarmoured (0x5813C)
        assert p.stundelay == 4
        assert p.hurt_cooldown == 0x12
        before = tuple(state.mob_color_ram[192:208])
        gp.player_hurt_palette_vblank(state)
        assert p.hurt_cooldown == 0x0C
        assert tuple(state.mob_color_ram[192:208]) != before


class TestForcefieldIsChargedAfterTheMove:
    """0x4AA42 sits after the ``player_try_move`` call at 0x4AA1E, so walking
    into a live segment is charged on the frame the hero arrives -- not one
    frame later, as it was when the check ran first."""

    def test_arriving_in_a_segment_costs_health_on_the_same_frame(self, monkeypatch):
        from gauntpy.coords import pack_slot
        from gauntpy.subsystems.input import JOY_IDLE, JOY_RIGHT

        state = _active_state()
        p = _make_player_active(state, 0, health=1000, mob_slot=pack_slot(5, 4))
        # The hero starts one cell to the left of the beam.
        state.mobs.hpos[p.mob_slot] = (4 * 16) << 7
        state.mobs.vpos[p.mob_slot] = native_v(5 * 16) << 7
        state.forcefield_color = 1
        state.forcefield_segment_table = [0x8000 | (3 << 10) | pack_slot(5, 3)]
        state.forcefield_segments_ready = True
        state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT

        def _step(st, index, delta, flags, *, track_thief=True):
            # The real mover writes H/V and migrates the record inside
            # ``player_try_move``, before the forcefield check at 0x4AA42.
            st.mobs.hpos[st.players[index].mob_slot] = (5 * 16) << 7
            gp.migrate_player_record(st, index)

        monkeypatch.setattr(gp, "player_try_move", _step)

        gp.main_move_players(state)

        assert p.health == 1000 - 2, "the arrival frame is charged"


# =============================================================================
# 35. highscore_check (0x49D0E) and the death flow that calls it (0x46AC4)
# =============================================================================

class TestScorePerCoin:
    def test_the_ranked_value_is_score_divided_by_coins(self):
        """0x40628, called at 0x46A18 -- an unsigned 32-by-16 divide."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score, p.coin_count = 9_001, 4
        assert gp.calc_score_per_coin(state, 0) == 2250
        assert p.score_per_coin == 2250

    def test_a_coinless_player_does_not_divide_by_zero(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score, p.coin_count = 500, 0
        assert gp.calc_score_per_coin(state, 0) == 500


class TestHighscoreCheck:
    def test_a_ranking_score_opens_initials_entry(self):
        from gauntpy.subsystems import score

        state = _active_state()
        p = _make_player_active(state, 0, character=Character.WIZARD)
        p.score_per_coin = 1_000_000
        gp.highscore_check(state, 0)
        assert p.highscore_rank == 0                    # 0x904A4A
        assert p.status == int(PlayerStatus.DYING)      # 0x49DA6
        assert p.state_timer == gp._NAME_ENTRY_TIMEOUT  # 0x49D88 = 0x0A8C
        assert p.name_entry_velocity == 0               # 0x49D98
        assert p.initials_cursor == 0                   # 0x49D9C
        assert p.name_entry_repeat_delay == 0xA0        # 0x49D78
        # The ladder itself is untouched until the initials are committed.
        assert score.high_scores(state)[Character.WIZARD][0][0] == 8000

    def test_a_non_ranking_score_gets_the_game_over_dwell(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score_per_coin = 10
        p.status = int(PlayerStatus.ALIVE_HERE)
        gp.highscore_check(state, 0)
        assert p.highscore_rank == gp._HIGHSCORE_NO_RANK == 10
        assert p.state_timer == gp._GAME_OVER_TIMEOUT   # 0x49DCA = 0x0258
        assert p.status == int(PlayerStatus.ALIVE_HERE), "0x49DC0 skips the status"

    def test_the_rank_is_the_score_per_coin_not_the_raw_score(self):
        """§10.3: four coins' worth of score does not rank on one coin's."""
        state = _active_state()
        p = _make_player_active(state, 0)
        p.score, p.coin_count = 8_400, 4          # 2100 per coin: nowhere near
        gp.calc_score_per_coin(state, 0)
        gp.highscore_check(state, 0)
        assert p.highscore_rank == gp._HIGHSCORE_NO_RANK


class TestDeathFlow:
    """The ROM's death block, main_health_countdown 0x467E0-0x46B7E."""

    @staticmethod
    def _kill(character: int = Character.WARRIOR, score: int = 0,
              coins: int = 1, level: int = 2) -> GameState:
        state = _active_state()
        state.levelnum_current = level
        p = _make_player_active(state, 0, character=character, health=1)
        p.score, p.coin_count = score, coins
        p.keysnum, p.potionsnum, p.powers = 4, 2, 0x0333
        p.supershot, p.stundelay, p.bonusmult = 7, 9, 6
        state.level_players_active = 1
        state.player_it = 0
        p.health = 0
        gp.main_move_players(state)
        return state

    def test_death_wipes_the_inventory_and_the_powers(self):
        """player_resetcounters at 0x4699A -- not just a status change."""
        state = self._kill()
        p = state.players[0]
        assert (p.keysnum, p.potionsnum, p.powers) == (0, 0, 0)
        assert (p.supershot, p.stundelay, p.bonusmult) == (0, 0, 1)
        assert p.mob_slot == 0
        assert state.player_tport_phase[0] == -1

    def test_death_keeps_the_character_and_the_score(self):
        state = self._kill(character=Character.ELF, score=1234)
        p = state.players[0]
        assert p.character == int(Character.ELF)
        assert p.score == 1234, "the ladder and the panel still need it"

    def test_death_computes_score_per_coin_and_ranks_it(self):
        state = self._kill(score=40_000, coins=2)
        p = state.players[0]
        assert p.score_per_coin == 20_000        # 0x46A18
        assert p.highscore_rank == 0             # 0x46AC4 -> 0x49D0E
        assert p.status == int(PlayerStatus.DYING)
        assert p.state_timer == gp._NAME_ENTRY_TIMEOUT

    def test_an_ordinary_death_gets_the_game_over_dwell(self):
        state = self._kill(score=100)
        p = state.players[0]
        assert p.highscore_rank == gp._HIGHSCORE_NO_RANK
        assert p.state_timer == gp._GAME_OVER_TIMEOUT
        assert p.status == int(PlayerStatus.REMOVED)

    def test_death_drops_the_it_player_and_the_active_count(self):
        state = self._kill()
        assert state.player_it == 0xFFFF         # 0x469C4
        assert state.level_players_active == 0   # 0x469DA

    def test_death_still_plays_the_character_sound(self):
        """0x46B2A, after highscore_check and the panel rebuild."""
        state = self._kill(character=Character.WIZARD)
        assert 0x16 in state.sound_log

    def test_death_voice_precedes_the_character_transition_sound(self):
        state = self._kill(character=Character.VALKYRIE)
        voice = state.sound_log.index(0xB5)
        transition = state.sound_log.index(0x15)
        assert voice < transition

    def test_last_player_death_arms_level_one_attract_timeout(self):
        state = self._kill(level=1)
        assert state.attract_timer == 0x0258

    def test_last_player_death_shows_continue_after_level_one(self):
        state = self._kill(level=2)
        assert state.attract_timer == 0x05DD
        assert state.title_intro_state == 1


class TestNameEntry:
    """The initials editor, player_death_sequence 0x49E20-0x4A116."""

    @staticmethod
    def _entering(state=None) -> GameState:
        from gauntpy.subsystems.input import JOY_IDLE

        state = state or _active_state()
        p = _make_player_active(state, 0, character=Character.VALKYRIE)
        p.score_per_coin = 1_000_000
        gp.highscore_check(state, 0)
        state.player_input_raw[0] = JOY_IDLE
        state.debounce_shift_magic[0] = 0xFFFF
        state.debounce_shift_fire[0] = 0xFFFF
        return state

    @staticmethod
    def _hold(state: GameState, mask: int) -> None:
        from gauntpy.subsystems.input import JOY_IDLE

        state.player_input_raw[0] = JOY_IDLE & ~mask

    def test_the_ring_is_backspace_space_a_to_z(self):
        """0x55440: 8 -> space -> 'A'..'Z' -> 8, and back the other way."""
        step = gp.name_entry_step_char
        assert step(0x08, +1, True) == 0x20
        assert step(0x20, +1, True) == ord("A")
        assert step(ord("A"), +1, True) == ord("B")
        assert step(ord("Z"), +1, True) == 0x08
        assert step(ord("Z"), +1, False) == 0x20, "no backspace at the first slot"
        assert step(0x08, -1, True) == ord("Z")
        assert step(0x20, -1, True) == 0x08
        assert step(0x20, -1, False) == ord("Z")
        assert step(ord("A"), -1, True) == 0x20

    def test_up_walks_the_letter_forward_on_the_repeat_cadence(self):
        from gauntpy.subsystems.input import JOY_UP

        state = self._entering()
        p = state.players[0]
        self._hold(state, JOY_UP)
        # The first press has to run the 0xA0 delay down before it steps.
        for _ in range(0xA0):
            gp.main_move_players(state)
        assert p.initials[0] == ord("B"), "one step once the delay expires"
        assert p.name_entry_velocity == 0xA0, "the accumulator clamps at 0xA0"
        # At full velocity the reload is the minimum, 8 frames.
        assert p.name_entry_repeat_delay == gp._NAME_ENTRY_REPEAT_BASE
        for _ in range(gp._NAME_ENTRY_REPEAT_BASE):
            gp.main_move_players(state)
        assert p.initials[0] == ord("C")

    def test_down_walks_it_backward(self):
        from gauntpy.subsystems.input import JOY_DOWN

        state = self._entering()
        p = state.players[0]
        p.name_entry_repeat_delay = 1
        self._hold(state, JOY_DOWN)
        gp.main_move_players(state)
        assert p.initials[0] == 0x20      # 'A' - 1 = space
        assert p.name_entry_velocity == -1

    def test_releasing_the_stick_zeroes_the_accumulator(self):
        from gauntpy.subsystems.input import JOY_IDLE, JOY_UP

        state = self._entering()
        p = state.players[0]
        self._hold(state, JOY_UP)
        for _ in range(10):
            gp.main_move_players(state)
        assert p.name_entry_velocity == 10
        state.player_input_raw[0] = JOY_IDLE
        gp.main_move_players(state)
        assert p.name_entry_velocity == 0

    def test_a_press_commits_a_letter_and_buys_more_time(self):
        state = self._entering()
        p = state.players[0]
        p.state_timer = 0x900                       # under the 0xA14 arming gate
        state.debounce_shift_magic[0] = 0x0C        # 0x49F7E
        gp.main_move_players(state)
        assert p.initials_cursor == 1               # 0x4A008
        assert p.state_timer == gp._NAME_ENTRY_STEP_TIMEOUT   # 0x4A00E

    def test_the_first_frames_ignore_the_button(self):
        """0x49FAA: the press that killed the hero must not commit an initial."""
        state = self._entering()
        p = state.players[0]
        state.debounce_shift_magic[0] = 0x0C
        gp.main_move_players(state)
        assert p.initials_cursor == 0

    def test_a_backspace_glyph_walks_the_cursor_back(self):
        state = self._entering()
        p = state.players[0]
        p.state_timer = 0x900
        p.initials_cursor = 1
        p.initials[1] = gp._NAME_ENTRY_BACKSPACE
        state.debounce_shift_fire[0] = 0x0C         # 0x49F9E: Fire commits too
        gp.main_move_players(state)
        assert p.initials_cursor == 0               # 0x4A016

    def test_three_committed_initials_write_the_record(self):
        from gauntpy.subsystems import score

        state = self._entering()
        p = state.players[0]
        p.initials = [ord("A"), ord("B"), ord("C")]
        p.state_timer = 0x900
        for _ in range(3):
            state.debounce_shift_magic[0] = 0x0C
            gp.main_move_players(state)
            if p.status != int(PlayerStatus.DYING):
                break                       # the third commit ended the dwell
            state.debounce_shift_magic[0] = 0xFFFF
            gp.main_move_players(state)

        ladder = score.high_scores(state)[int(Character.VALKYRIE)]
        assert ladder[0] == (1_000_000, "ABC")      # OS 0x1B4 at 0x4A0CA
        assert len(ladder) == score.HIGHSCORE_RANKS, "the tenth record falls off"
        assert p.state_timer == gp._GAME_OVER_TIMEOUT          # 0x4A0FE
        assert state.debounce_shift_magic[0] == 0              # 0x4A0F6
        assert state.debounce_shift_fire[0] == 0               # 0x4A0F2
        assert p.status == int(PlayerStatus.REMOVED)

    def test_the_countdown_expiring_also_writes_the_record(self):
        """0x4A068: zero on the clock ends the dwell wherever the cursor is."""
        from gauntpy.subsystems import score

        state = self._entering()
        p = state.players[0]
        p.initials = [ord("Z"), 0x20, gp._NAME_ENTRY_BACKSPACE]
        p.state_timer = 1
        gp.main_move_players(state)
        ladder = score.high_scores(state)[int(Character.VALKYRIE)]
        assert ladder[0] == (1_000_000, "Z  "), "a backspace glyph stores as a space"
        assert p.status == int(PlayerStatus.REMOVED)

    def test_an_unranked_player_never_edits_anything(self):
        state = _active_state()
        p = _make_player_active(state, 0)
        p.status = int(PlayerStatus.DYING)
        p.highscore_rank = gp._HIGHSCORE_NO_RANK
        p.state_timer = 2
        p.initials = [ord("A")] * 3
        state.debounce_shift_magic[0] = 0x0C
        gp.main_move_players(state)
        assert p.initials == [ord("A")] * 3
        assert p.initials_cursor == 0
        assert p.status == int(PlayerStatus.DYING)

    def test_ranked_entry_writes_prompt_score_rank_and_large_initials(self):
        state = self._entering()
        p = state.players[0]
        gp.setup_infopanel(state, 0)

        row = 7
        assert "".join(
            chr(word & 0x3FF) if word & 0x3FF else " "
            for word in state.alpha_ram[row * 64 + 29:row * 64 + 36]
        ).startswith("  Enter")
        assert state.alpha_ram[row * 64 + 36] & 0x0100
        assert state.alpha_ram[(row + 1) * 64 + 36] & 0x0100
        assert p.highscore_rank == 0

    def test_the_whole_death_to_removal_lifecycle_runs(self):
        """End to end: a ranked hero dies, enters initials, commits them, plays
        the death animation and leaves the level."""
        from gauntpy.subsystems import score

        state = _active_state()
        p = _make_player_active(state, 0, character=Character.ELF, health=1)
        p.score, p.coin_count = 500_000, 1
        state.level_players_active = 1
        p.health = 0

        gp.main_move_players(state)                      # the death frame
        assert p.status == int(PlayerStatus.DYING)
        assert p.highscore_rank == 0

        p.initials = [ord("G"), ord("D"), ord("C")]
        p.state_timer = 0x900
        for _ in range(3):
            state.debounce_shift_magic[0] = 0x0C
            gp.main_move_players(state)
            if p.status != int(PlayerStatus.DYING):
                break
            state.debounce_shift_magic[0] = 0xFFFF
            gp.main_move_players(state)
        assert score.high_scores(state)[int(Character.ELF)][0] == (500_000, "GDC")

        for _ in range(200):
            gp.main_move_players(state)
        assert p.status == int(PlayerStatus.REMOVED)


# =============================================================================
# 36. Status 0x08 carries two meanings and they must not be conflated
# =============================================================================

class TestExitingIsNotRespawnWait:
    """``player_exit_sequence`` (0x52C66) is the ROM's only writer of status 8;
    this port also parks a dying hero there for its own death animation, so
    ``exit_pending`` has to keep the two tails apart."""

    def test_the_two_names_are_the_same_byte(self):
        assert int(PlayerStatus.EXITING) == int(PlayerStatus.RESPAWN_WAIT) == 0x08

    def test_a_dying_hero_ends_removed_and_never_ends_the_level(self):
        ended = []
        state = _active_state()
        p = state.players[0]
        p.status = int(PlayerStatus.RESPAWN_WAIT)
        p.exit_pending = 0
        p.mob_slot = 30
        state.player_death_anim_frame[0] = 4
        state.level_players_active = 1

        from gauntpy.subsystems import exits

        original = exits.show_level_end_bonus_screen
        exits.show_level_end_bonus_screen = lambda st: ended.append(st)
        try:
            for _ in range(gp._RESPAWN_WAIT_LIMIT + 8):
                gp.main_move_players(state)
        finally:
            exits.show_level_end_bonus_screen = original

        assert p.status == int(PlayerStatus.REMOVED)
        assert ended == [], "a death is not an exit"
        assert state.level_players_active == 1, "the death path already counted it"

    def test_an_exiting_hero_ends_alive_next_and_releases_its_mob(self):
        state = _active_state()
        p = state.players[0]
        p.status = int(PlayerStatus.EXITING)
        p.exit_pending = 1
        p.mob_slot = 21                       # SLOT_EXIT_ANIMS[0]
        state.mobs.create(21, tile=0x1234, hpos=0, vpos=0, obj_type=0)
        state.player_death_anim_frame[0] = 4
        state.level_players_active = 2        # somebody else is still playing
        state.player_it = 0

        for _ in range(gp._RESPAWN_WAIT_LIMIT + 8):
            gp.main_move_players(state)

        assert p.status == int(PlayerStatus.ALIVE_NEXT)   # 0x4A6B2
        assert p.exit_pending == 0
        assert p.mob_slot == 0                            # 0x4A6D2
        assert state.mobs.picture[21] == 0                # 0x4A6C0
        assert state.player_it == 0xFFFF                  # 0x4A6DE
        assert state.level_players_active == 1            # 0x4A6E6

    def test_the_dissolve_frames_come_from_the_exit_table(self):
        """0x4A796 indexes 0x5870A by ``character * 8 + counter >> 2``."""
        state = _active_state()
        p = state.players[0]
        p.status = int(PlayerStatus.EXITING)
        p.exit_pending = 1
        p.character = int(Character.ELF)
        p.mob_slot = 24                       # SLOT_EXIT_ANIMS[3]
        p.anim_counter = 0
        state.player_death_anim_frame[0] = 4
        state.level_players_active = 2

        seen = []
        for _ in range(gp._RESPAWN_WAIT_LIMIT):
            gp.main_move_players(state)
            picture = state.mobs.picture[24]
            if picture and (not seen or seen[-1] != picture):
                seen.append(picture)

        expected = gp._PLAYER_EXIT_PICTURE[3 * 8: 3 * 8 + 8]
        assert seen == [expected[i] for i in range(1, 8)], (
            "one frame per four counter steps, 0x5870A"
        )

    def test_the_exit_table_is_the_rom_block(self):
        assert len(gp._PLAYER_EXIT_PICTURE) == 32
        assert gp._PLAYER_EXIT_PICTURE[:8] == [
            0x0C3F, 0x1087, 0x1090, 0x1099, 0x10A2, 0x10AB, 0x10B4, 0x10BD,
        ]
        assert gp._PLAYER_EXIT_PICTURE[8] == 0x1148
        assert gp._PLAYER_EXIT_PICTURE[16] == 0x13A2
        assert gp._PLAYER_EXIT_PICTURE[24] == 0x1548


# =============================================================================
# 30. Player animation pictures (main_move_players 0x4AB08-0x4AC7A)
# =============================================================================

class TestHeroPictures:
    """The core owns hero pictures so a headless/full multiplayer tick never
    leaves a PLAYERSTART base picture for the renderer to resolve."""

    _PLAYERSTART_PICTURE = 0x1E0D

    @staticmethod
    def _hero(state: GameState, player_index: int, character: Character,
              slot: int, direction: int = 0) -> Player:
        player = _make_player_active(
            state, player_index, character=character, health=500, mob_slot=slot,
        )
        player.direction = direction
        state.mobs.create(
            slot,
            TestHeroPictures._PLAYERSTART_PICTURE,
            (((slot & 0x1F) * 16) + 8) << 7,
            native_v(((slot >> 5) * 16) + 8) << 7,
            MazeObjIds.PLAYERSTART,
            player_index,
        )
        return player

    def test_literal_animation_tables_match_the_rom_dimensions_and_sentinels(self):
        assert len(gp._ANIM_TABLE_IDLE) == 4 * 8
        assert len(gp._ANIM_TABLE_WALKING) == 4 * 8 * 4
        assert len(gp._ANIM_TABLE_FIGHTING) == 4 * 8 * 8
        assert len(gp._ANIM_TABLE_SHOOTING) == 4 * 8 * 4
        assert gp._ANIM_TABLE_WALKING[:4] == (0x0BCF, 0x0BD8, 0x0BE1, 0x0BD8)
        assert gp._ANIM_TABLE_FIGHTING[128:136] == (
            0x1412, 0x14C6, 0x14C6, 0x14CF,
            0x14CF, 0x14C6, 0x14C6, 0x1412,
        )
        assert gp._ANIM_TABLE_SHOOTING[96:100] == (
            0x156C, 0x1524, 0x1524, 0x1524,
        )

    def test_headless_idle_tick_replaces_the_playerstart_picture(self):
        state = _active_state()
        player = self._hero(state, 0, Character.WIZARD, 0x80, direction=6)

        gp.main_move_players(state)

        rom_direction = gp._PORT_DIR_TO_ROM_DIR[player.direction]
        assert state.mobs.picture[player.mob_slot] == gp._ANIM_TABLE_IDLE[
            int(Character.WIZARD) * 8 + rom_direction
        ]
        assert player.anim_counter == 0

    def test_full_headless_tick_replaces_the_playerstart_picture(self):
        from gauntpy.mainloop import tick

        state = _active_state()
        player = self._hero(state, 0, Character.VALKYRIE, 0x80, direction=2)

        tick(state)

        rom_direction = gp._PORT_DIR_TO_ROM_DIR[player.direction]
        assert state.mobs.picture[player.mob_slot] == gp._ANIM_TABLE_IDLE[
            int(Character.VALKYRIE) * 8 + rom_direction
        ]

    def test_core_updates_all_four_active_heroes_on_a_multiplayer_walk_tick(self):
        from gauntpy.subsystems.input import JOY_RIGHT

        state = _active_state()
        heroes = [
            self._hero(state, i, Character(i), 0x80 + i * 0x20)
            for i in range(4)
        ]
        state.player_input_raw = [0xFFFF & ~JOY_RIGHT] * 4

        gp.main_move_players(state)

        right = gp._PORT_DIR_TO_ROM_DIR[0]
        for character, player in enumerate(heroes):
            assert state.mobs.picture[player.mob_slot] == gp._ANIM_TABLE_WALKING[
                character * 32 + right * 4
            ]
            assert state.mobs.picture[player.mob_slot] != self._PLAYERSTART_PICTURE
            assert player.anim_counter == 1

    def test_shooting_uses_the_rom_player_table_before_spawning_the_shot(self):
        from gauntpy.subsystems.input import JOY_FIRE_BIT

        state = _active_state()
        player = self._hero(state, 0, Character.WIZARD, 0x80, direction=0)
        state.player_input_raw[0] = 0xFFFF & ~JOY_FIRE_BIT

        gp.main_move_players(state)

        right = gp._PORT_DIR_TO_ROM_DIR[player.direction]
        assert state.player_shooting[0] == -1
        assert state.mobs.picture[player.mob_slot] == gp._ANIM_TABLE_SHOOTING[
            int(Character.WIZARD) * 32 + right * 4
        ]
        assert player.anim_counter == 1

        for _ in range(3):
            gp.main_move_players(state)
        assert state.mobs.picture[1] == gp._PLAYER_SHOT_PICTURE[
            int(Character.WIZARD) * 8 + right
        ]

    def test_wall_contact_does_not_hide_the_held_fire_animation(self):
        from gauntpy.mainloop import tick
        from gauntpy.coords import pack_slot
        from gauntpy.subsystems.input import JOY_FIRE_BIT, JOY_RIGHT

        state = _active_state()
        slot = pack_slot(10, 10)
        wall = pack_slot(10, 11)
        player = self._hero(state, 0, Character.ELF, slot, direction=0)
        state.mobs.hpos[slot] = (10 * 16 - 4) << 7
        state.mobs.create(
            wall, 0x8000, 11 * 16 << 7, native_v(10 * 16) << 7,
            MazeObjIds.WALL_REGULAR,
        )
        state.player_input_raw[0] = 0xFFFF & ~(JOY_RIGHT | JOY_FIRE_BIT)

        pictures = []
        for _ in range(10):
            tick(state)
            pictures.append(state.mobs.picture[player.mob_slot])

        right = gp._PORT_DIR_TO_ROM_DIR[player.direction]
        row = int(Character.ELF) * 32 + right * 4
        assert set(pictures) >= {
            gp._ANIM_TABLE_SHOOTING[row],
            gp._ANIM_TABLE_SHOOTING[row + 1],
        }

    def test_fighting_selects_its_eight_frame_table(self):
        state = _active_state()
        player = self._hero(state, 0, Character.ELF, 0x80, direction=7)
        state.player_fighting_dir[0] = 1
        player.anim_counter = 14

        gp.update_player_sprite(state, 0)

        rom_direction = gp._PORT_DIR_TO_ROM_DIR[player.direction]
        assert state.mobs.picture[player.mob_slot] == gp._ANIM_TABLE_FIGHTING[
            int(Character.ELF) * 64 + rom_direction * 8 + 7
        ]

    def test_wizard_picture_resolves_through_the_wizard_entity(self):
        """Wizard/Sorcerer tiles overlap, so the player record must supply the
        entity kind that gives assets the Wizard palette bank."""
        from gauntpy.assets import AssetStore
        from gauntpy.render.mobs import sprite_kind

        state = _active_state()
        player = self._hero(state, 0, Character.WIZARD, 0x80)
        gp.update_player_sprite(state, 0)

        picture = state.mobs.picture[player.mob_slot]
        assert sprite_kind(state, player.mob_slot) == "wizard"
        assert AssetStore._frame_for(picture, "wizard").monster_type == "wizard"

    def test_exported_updater_preserves_a_transporter_flash(self):
        state = _active_state()
        player = self._hero(state, 0, Character.VALKYRIE, 0x80)
        state.player_tport_phase[0] = 0
        state.mobs.picture[player.mob_slot] = gp._PLAYER_INVISIBLE_PICTURE

        gp.update_player_sprites(state)

        assert state.mobs.picture[player.mob_slot] == gp._PLAYER_INVISIBLE_PICTURE


# =============================================================================
# 37. The post-loop is gated on a counter only normal play writes (0x4A8B4)
# =============================================================================

class TestPostLoopIsNormalPlayOnly:
    """``main_move_players`` bumps its "processed" local at 0x4A8B4, which sits
    inside the ``game_mode == 0`` arm of the branch at 0x4A8A2 -- the demo arm
    at 0x4A8F2 reads its joystick from ``demo_ptr`` and jumps straight to the
    stun gate.  0x4ACD4 then gates the *whole* post-loop on that local, so the
    timed-door sweep and the escape-timeout wall conversion never run while the
    attract demo is playing."""

    _RIGHT_HELD = 0xE3          # bit 4 (RIGHT) clear, buttons released

    def _demo_hero(self, state: GameState) -> Player:
        p = state.players[1]
        p.status = int(PlayerStatus.ALIVE_HERE)
        p.health = 500
        p.mob_slot = 40
        state.mobs.hpos[40] = (8 * 16 - 4) << 7
        state.mobs.vpos[40] = native_v(1 * 16) << 7
        return p

    def _normal_hero(self, state: GameState) -> Player:
        from gauntpy.subsystems.input import JOY_IDLE, JOY_RIGHT

        p = _make_player_active(state, 1, health=500, mob_slot=40)
        state.mobs.hpos[40] = (8 * 16 - 4) << 7
        state.mobs.vpos[40] = native_v(1 * 16) << 7
        state.player_input_raw[1] = JOY_IDLE & ~JOY_RIGHT
        return p

    # -- the demo hero still plays -------------------------------------------

    def test_the_demo_hero_still_moves(self):
        state = _demo_state([[], [40, self._RIGHT_HELD], [], []])
        p = self._demo_hero(state)
        x0 = hpos_x(state.mobs.hpos[p.mob_slot])
        gp.main_move_players(state)
        assert hpos_x(state.mobs.hpos[p.mob_slot]) > x0, (
            "the demo arm at 0x4A8F2 rejoins the common path at 0x4A908"
        )

    def test_the_demo_hero_still_picks_things_up(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        p = self._demo_hero(state)
        # The cell next door, which the hero walks into on the tile pass.
        food_slot = p.mob_slot + 1
        state.mobs.hpos[p.mob_slot] = (9 * 16 - 4) << 7
        state.mobs.create(food_slot, tile=gp._WHOLESOME_FOOD_PICTURE,
                          hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.FOOD_DESTRUCTABLE))
        gp.main_move_players(state)
        assert p.health == 600, "food is still eaten during the demo"

    def test_the_demo_hero_still_runs_its_power_timers(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        self._demo_hero(state)
        state.player_invis_timer[1] = 3
        gp.main_move_players(state)
        assert state.player_invis_timer[1] == 2

    # -- but none of the post-loop work happens ------------------------------

    def test_the_idle_timer_does_not_advance_during_the_demo(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        self._demo_hero(state)
        state.idle_timer = 5
        for _ in range(10):
            gp.main_move_players(state)
        assert state.idle_timer == 5, "0x4ACD4 skips the whole block"

    def test_timed_doors_never_open_during_the_demo(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        self._demo_hero(state)
        state.mobs.create(200, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        state.idle_timer = gp._DOOR_IDLE_THRESHOLD_WITH_KEYS
        for _ in range(4):
            gp.main_move_players(state)
        assert state.mobs.is_occupied(200), "no timed-door sweep on the attract screen"
        assert state.idle_timer == gp._DOOR_IDLE_THRESHOLD_WITH_KEYS

    def test_the_escape_timer_does_not_advance_during_the_demo(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        self._demo_hero(state)
        state.escape_timer = 7
        for _ in range(10):
            gp.main_move_players(state)
        assert state.escape_timer == 7

    def test_walls_are_never_converted_to_exits_during_the_demo(self):
        state = _demo_state([[], [40, 0xF3], [], []])
        self._demo_hero(state)
        wall = 300
        state.mobs.create(wall, tile=gp._WALL_PICTURE, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.WALL_REGULAR))
        state.escape_timer = gp._ESCAPE_TIMER_LIMIT - 1
        state.sound_log.clear()
        for _ in range(4):
            gp.main_move_players(state)
        assert state.mobs.obj_type(wall) == int(MazeObjIds.WALL_REGULAR)
        assert gp._SOUND_ESCAPE_WALLS not in state.sound_log

    # -- normal play does all of it ------------------------------------------

    def test_normal_play_advances_both_timers(self):
        state = _active_state()
        self._normal_hero(state)
        state.idle_timer = 5
        state.escape_timer = 7
        gp.main_move_players(state)
        assert state.idle_timer == 6
        assert state.escape_timer == 8

    def test_normal_play_opens_the_timed_doors(self):
        state = _active_state()
        self._normal_hero(state)
        state.mobs.create(200, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        state.idle_timer = gp._DOOR_IDLE_THRESHOLD_NO_KEYS
        gp.main_move_players(state)
        assert not state.mobs.is_occupied(200)
        assert state.idle_timer == -1

    def test_normal_play_still_converts_walls_at_the_escape_timeout(self):
        state = _active_state()
        self._normal_hero(state)
        wall = 300
        state.mobs.create(wall, tile=gp._WALL_PICTURE, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.WALL_REGULAR))
        state.escape_timer = gp._ESCAPE_TIMER_LIMIT - 1
        gp.main_move_players(state)
        assert state.escape_timer == 0
        assert state.mobs.obj_type(wall) == int(MazeObjIds.EXIT)

    def test_a_normal_frame_with_nobody_playing_is_gated_too(self):
        """The counter is per *player*: an empty level leaves it at zero."""
        state = _active_state()
        state.idle_timer = 5
        state.escape_timer = 7
        gp.main_move_players(state)
        assert (state.idle_timer, state.escape_timer) == (5, 7)

    def test_a_transporting_player_is_not_counted(self):
        """0x4A7EC branches to the next player before 0x4A8B4 is reached."""
        state = _active_state()
        self._normal_hero(state)
        state.player_tport_phase[1] = 0
        state.idle_timer = 5
        state.escape_timer = 7
        gp.main_move_players(state)
        assert (state.idle_timer, state.escape_timer) == (5, 7)

    def test_the_key_count_comes_from_the_active_tail(self):
        """0x4AC8C runs after the sprite update, so a stunned key holder still
        pushes the door threshold out to 0xA8C."""
        state = _active_state()
        p = self._normal_hero(state)
        p.keysnum = 1
        p.stundelay = 5
        state.mobs.create(201, tile=0, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.DOOR_HORIZ))
        state.idle_timer = gp._DOOR_IDLE_THRESHOLD_NO_KEYS
        gp.main_move_players(state)
        assert state.mobs.is_occupied(201)
        assert state.idle_timer == gp._DOOR_IDLE_THRESHOLD_NO_KEYS + 1
