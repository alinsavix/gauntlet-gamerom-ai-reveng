"""WP-12: potion use and blast resolution.

Acceptance (PLAN.md §6 WP-12): all four characters x reachable object types
produce the documented outcome; a potion always kills Death.
"""

from __future__ import annotations

from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus
from gauntpy.coords import encode_hpos, encode_vpos_at_y, pack_slot
from gauntpy.state import GameState
from gauntpy.subsystems.monsters import (
    _in_cull_rect,
    _supersorc_dispatch,
    _update_cull_rect,
)
from gauntpy.subsystems.potions import (
    main_handle_potions,
    potion_blast,
)
from gauntpy.subsystems.dragon import (
    _ST_STUNNED,
    _ST_WAKING,
    main_handle_dragon,
)
from gauntpy.subsystems.display import potion_flash_vblank
from gauntpy.subsystems.monsters import main_move_monsters
from gauntpy.subsystems import score
from gauntpy.subsystems.players import setup_infopanel


def _active(state: GameState, index: int, slot: int,
            character: int = Character.WARRIOR) -> None:
    p = state.players[index]
    p.status = PlayerStatus.ALIVE_HERE
    p.character = character
    p.mob_slot = slot
    state.level_players_active += 1
    state.mobs.hpos[slot] = encode_hpos((slot & 0x1F) * 16)
    state.mobs.vpos[slot] = encode_vpos_at_y((slot >> 5) * 16)


def _place(state: GameState, slot: int, obj_type: int, tier: int = 4) -> None:
    state.mobs.create(
        slot, tile=1,
        hpos=encode_hpos((slot & 0x1F) * 16, palette=tier),
        vpos=encode_vpos_at_y((slot >> 5) * 16),
        obj_type=obj_type, state=0,
    )


def _camera_on(state: GameState, slot: int) -> None:
    """Point the camera at ``slot``, the way ``camera.snap_camera`` would.

    A potion only clears what is on screen (0x41560-0x41584), and the origins
    it culls against are derived from the camera, so a blast test has to say
    where the camera is looking.  The box is 255 x 263 px around the midpoint,
    so this covers roughly seven cells either side of ``slot``.
    """
    x, y = (slot & 0x1F) * 16, (slot >> 5) * 16
    state.scroll_x = x - 0x68            # midX = scroll_x + 0x68
    state.scroll_y = y - 0x74            # midY = scroll_y + 0x74


#: Every blast test below aims here; it covers rows 1-17 and columns 2-16.
_FOCUS = pack_slot(9, 9)
#: Well outside that box on both axes.
_OFFSCREEN = pack_slot(25, 25)


class TestMagicGate:
    def test_no_press_no_effect(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.players[0].potionsnum = 2
        _place(state, pack_slot(8, 8), MazeObjIds.MONST_GHOST)
        # debounce register not at the edge value
        state.debounce_shift_magic[0] = 0xFFFF
        main_handle_potions(state)
        assert state.players[0].potionsnum == 2, "no potion consumed"
        assert state.mobs.obj_type(pack_slot(8, 8)) == int(MazeObjIds.MONST_GHOST)

    def test_press_consumes_potion_and_blasts(self):
        """A Wizard's magic press consumes a potion and clears a Ghost."""
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        state.players[0].potionsnum = 1
        _place(state, pack_slot(8, 8), MazeObjIds.MONST_GHOST)
        _camera_on(state, _FOCUS)
        state.debounce_shift_magic[0] = 0x1C     # magic press edge
        main_handle_potions(state)
        assert state.players[0].potionsnum == 0, "potion consumed"
        assert 0x1D in state.sound_log
        main_move_monsters(state)
        # Wizard column (0x12 col 2) is 0 -> Ghost destroyed.
        assert state.mobs.obj_type(pack_slot(8, 8)) == 0, "ghost destroyed"

    def test_stun_does_not_block_potion_use(self):
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        state.players[0].stundelay = 60
        state.players[0].potionsnum = 1
        _place(state, pack_slot(8, 8), MazeObjIds.MONST_GHOST)
        _camera_on(state, _FOCUS)
        state.debounce_shift_magic[0] = 0x1C

        main_handle_potions(state)

        assert state.players[0].stundelay == 60
        assert state.players[0].potionsnum == 0
        main_move_monsters(state)
        assert state.mobs.obj_type(pack_slot(8, 8)) == 0

    def test_demo_reads_magic_directly_from_the_current_record(self):
        state = GameState(game_mode=GameMode.DEMO)
        _active(state, 1, pack_slot(5, 5), character=Character.ELF)
        state.players[1].potionsnum = 1
        _place(state, pack_slot(8, 8), MazeObjIds.MONST_GHOST)
        _camera_on(state, _FOCUS)
        state.debounce_shift_magic[1] = 0xFFFF
        state.demo_streams[1] = [8, 0xF2]  # active-low Magic, no directions
        state.demo_timers[1] = 8

        main_handle_potions(state)

        assert state.players[1].potionsnum == 0
        main_move_monsters(state)
        assert state.mobs.obj_type(pack_slot(8, 8)) == 0

    def test_press_updates_alpha_inventory_at_the_rom_call_site(self):
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        state.players[0].potionsnum = 1
        state.debounce_shift_magic[0] = 0x1C
        setup_infopanel(state, 0)
        start = score.PLAYER_INV_ROW * score.ALPHA_ROW_STRIDE + score.INVENTORY_COLUMN
        assert any(
            word & 0x3FF
            for word in state.alpha_ram[start:start + score.INVENTORY_CELLS]
        )

        main_handle_potions(state)

        assert all(
            word & 0x3FF == 0
            for word in state.alpha_ram[start:start + score.INVENTORY_CELLS]
        )

    def test_no_potion_no_blast(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        _active(state, 0, pack_slot(5, 5))
        state.players[0].potionsnum = 0
        _place(state, pack_slot(8, 8), MazeObjIds.MONST_GHOST)
        state.debounce_shift_magic[0] = 0x1C
        main_handle_potions(state)
        assert state.mobs.obj_type(pack_slot(8, 8)) == int(MazeObjIds.MONST_GHOST)
        assert state.dialog_first_encounter_flags & 0x10
        assert state.dialog_player == 0
        assert any("COLLECT MAGIC POTION" in line for line in state.dialog_message)
        assert 0x44 in state.sound_log

    def test_successful_use_records_the_rom_potion_used_dialog_mask(self):
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 0, pack_slot(5, 5))
        state.players[0].potionsnum = 1
        state.debounce_shift_magic[0] = 0x1C

        main_handle_potions(state)

        assert state.dialog_first_encounter_flags & 0x00080000
        assert not state.dialog_first_encounter_flags & 0x10

    def test_use_arms_the_player_colored_playfield_flash(self):
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 1, pack_slot(5, 5), character=Character.VALKYRIE)
        state.players[1].potionsnum = 1
        state.debounce_shift_magic[1] = 0x1C
        state.playfield_color_base = 0x1234
        state.playfield_color_latch = 0x1234
        state.playfield_color_ram[8] = 0x1234

        main_handle_potions(state)
        assert state.playfield_color_latch == 0xF08F
        assert state.playfield_color_ram[8] == 0x1234

        potion_flash_vblank(state)
        assert state.playfield_color_ram[8] == 0xF08F

    def test_second_field_restores_the_ordinary_playfield_color(self):
        state = GameState(game_mode=GameMode.NORMAL)
        state.playfield_color_base = 0x5678
        state.playfield_color_latch = 0xFF00
        state.playfield_color_ram[8] = 0xFF00

        from gauntpy.mainloop import game_frame
        game_frame(state)
        potion_flash_vblank(state)

        assert state.playfield_color_latch == 0x5678
        assert state.playfield_color_ram[8] == 0x5678

    def test_on_screen_active_dragon_is_stunned(self):
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        state.players[0].potionsnum = 1
        state.debounce_shift_magic[0] = 0x1C
        dragon = pack_slot(9, 9)
        _place(state, dragon, MazeObjIds.MONST_DRAGON)
        state.dragon_seg_mob_ids = [dragon, dragon - 0x20, dragon + 1, dragon - 0x1F]
        state.dragon_mob_slot = dragon
        state.dragon_state = 0
        state.scroll_x = 0
        state.scroll_y = 0

        main_handle_potions(state)

        assert state.dragon_state & _ST_STUNNED
        for _ in range(120):
            main_handle_dragon(state)
        assert state.dragon_state == _ST_STUNNED
        assert state.dragon_anim_ctr == 0
        assert not any(state.mobs.picture[5:9])

    def test_second_potion_restarts_a_stunned_dragon_wake_transition(self):
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        state.players[0].potionsnum = 1
        state.debounce_shift_magic[0] = 0x1C
        dragon = pack_slot(9, 9)
        _place(state, dragon, MazeObjIds.MONST_DRAGON)
        state.dragon_seg_mob_ids = [dragon, dragon - 0x20, dragon + 1, dragon - 0x1F]
        state.dragon_mob_slot = dragon
        state.dragon_state = _ST_STUNNED
        state.scroll_x = 0
        state.scroll_y = 0

        main_handle_potions(state)

        assert state.dragon_state & _ST_WAKING
        assert not state.dragon_state & _ST_STUNNED
        assert state.dragon_anim_ctr == -0x31

        for _ in range(49):
            main_handle_dragon(state)
        assert state.dragon_state == _ST_WAKING
        assert state.dragon_anim_ctr == 0

        from gauntpy.subsystems.shots import dragon_player_proximity

        dragon_player_proximity(state, dragon)
        assert state.dragon_anim_ctr == 0x31
        for _ in range(49):
            main_handle_dragon(state)
        assert not state.dragon_state & (_ST_WAKING | _ST_STUNNED)

        for _ in range(240):
            main_handle_dragon(state)
        assert any(state.mobs.picture[5:9])


class TestBlastOutcomes:
    def test_potion_always_kills_death(self):
        for character in (Character.WARRIOR, Character.VALKYRIE,
                          Character.WIZARD, Character.ELF):
            state = GameState()
            _active(state, 0, pack_slot(5, 5), character=character)
            death_slot = pack_slot(9, 9)
            _place(state, death_slot, MazeObjIds.MONST_DEATH)
            _camera_on(state, _FOCUS)
            potion_blast(state, 0)
            assert state.mobs.obj_type(death_slot) == 0, \
                f"Death must die for character {character}"

    def test_death_potion_kill_awards_and_displays_the_rom_score(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        death_slot = pack_slot(9, 9)
        _place(state, death_slot, MazeObjIds.MONST_DEATH)
        state.death_hits = 1
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.players[0].score == 4000
        assert state.score_display_timer[0] == 0x3C
        assert state.mobs.picture[0x11] == 0x1DC0

    def test_it_is_immune(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        it_slot = pack_slot(9, 9)
        _place(state, it_slot, MazeObjIds.MONST_IT)
        _camera_on(state, _FOCUS)
        potion_blast(state, 0)
        assert state.mobs.obj_type(it_slot) == int(MazeObjIds.MONST_IT), \
            "IT is filtered before the lookup"

    def test_wizard_column_destroys_monster(self):
        """The Wizard column is zero everywhere -> destroy outright."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        ghost = pack_slot(9, 9)
        _place(state, ghost, MazeObjIds.MONST_GHOST, tier=4)
        _camera_on(state, _FOCUS)
        potion_blast(state, 0)
        assert state.mobs.obj_type(ghost) == 0

    def test_warrior_potion_weakens_ghost_but_does_not_kill(self):
        """ROM 0x12 col 0 = 2: a Warrior potion drops a Ghost 4→2 (survives)."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        ghost = pack_slot(9, 9)
        _place(state, ghost, MazeObjIds.MONST_GHOST, tier=4)
        _camera_on(state, _FOCUS)
        potion_blast(state, 0)
        assert state.mobs.obj_type(ghost) == int(MazeObjIds.MONST_GHOST), \
            "Warrior potion should not destroy a full-tier Ghost"
        assert state.mobs.hpos[ghost] & 0xF == 2, "tier should drop 4 → 2"

    def test_elf_potion_demotes_generator(self):
        """ROM 0x1E col 3 = 28: an Elf potion demotes GEN_GHOST3 → GEN_GHOST1."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.ELF)
        gen = pack_slot(9, 9)
        _place(state, gen, MazeObjIds.GEN_GHOST3)
        _camera_on(state, _FOCUS)
        potion_blast(state, 0)
        assert state.mobs.obj_type(gen) == int(MazeObjIds.GEN_GHOST1), \
            "GEN_GHOST3 should demote to GEN_GHOST1 under an Elf potion"

    def test_magic_stuns_idle_acid_before_a_second_blast_destroys_it(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.ELF)
        acid = pack_slot(9, 9)
        _place(state, acid, MazeObjIds.MONST_ACID)
        state.mobs.state_link[acid] |= 0xE000
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.obj_type(acid) == int(MazeObjIds.MONST_ACID)
        assert state.mobs.hpos[acid] & 0x10
        assert state.mobs.state_link[acid] & 0xE000 == 0
        assert state.mobs.picture[acid] == 0x2300

        potion_blast(state, 0)
        assert state.mobs.obj_type(acid) == 0

    def test_magic_reveals_phasing_super_sorcerer_instead_of_killing_it(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.ELF)
        sorcerer = pack_slot(9, 9)
        _place(state, sorcerer, MazeObjIds.MONST_SUPERSORC)
        state.mobs.hpos[sorcerer] |= 0x30
        state.mobs.state_link[sorcerer] |= 0xE000
        state.mobs.picture[sorcerer] = 0x1709
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.obj_type(sorcerer) == int(MazeObjIds.MONST_SUPERSORC)
        assert state.mobs.hpos[sorcerer] & 0x30 == 0
        assert state.mobs.state_link[sorcerer] & 0xE000 == 0
        assert state.mobs.picture[sorcerer] != 0x1709

    def test_magic_reveals_every_on_screen_phasing_super_sorcerer(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.ELF)
        on_screen = (pack_slot(8, 8), pack_slot(10, 10))
        for slot in (*on_screen, _OFFSCREEN):
            _place(state, slot, MazeObjIds.MONST_SUPERSORC)
            state.mobs.hpos[slot] |= 0x30
            state.mobs.state_link[slot] |= 0xE000
            state.mobs.picture[slot] = 0x1709
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        for slot in on_screen:
            assert state.mobs.hpos[slot] & 0x30 == 0
            assert state.mobs.state_link[slot] & 0xE000 == 0
            assert state.mobs.picture[slot] != 0x1709
        assert state.mobs.hpos[_OFFSCREEN] & 0x30 == 0x30
        assert state.mobs.state_link[_OFFSCREEN] & 0xE000 == 0xE000
        assert state.mobs.picture[_OFFSCREEN] == 0x1709

    def test_revealed_super_sorcerer_resumes_its_cycle_and_fires(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.ELF)
        sorcerer = pack_slot(9, 9)
        _place(state, sorcerer, MazeObjIds.MONST_SUPERSORC)
        state.mobs.hpos[sorcerer] |= 0x30
        state.mobs.state_link[sorcerer] |= 0xE000
        state.mobs.picture[sorcerer] = 0x1709
        _camera_on(state, _FOCUS)
        potion_blast(state, 0)

        for _ in range(8):
            _supersorc_dispatch(state, sorcerer, 0)

        assert any(state.mobs.picture[slot] for slot in range(5, 9))
        assert state.mobs.hpos[sorcerer] & 0x20

    def test_wizard_blast_clears_multiple_monsters(self):
        """The Wizard column is zero everywhere, so it destroys outright."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        slots = [pack_slot(9, 9), pack_slot(10, 10), pack_slot(11, 11)]
        for s in slots:
            _place(state, s, MazeObjIds.MONST_GRUNT)
        _camera_on(state, _FOCUS)
        potion_blast(state, 0)
        assert all(state.mobs.obj_type(s) == 0 for s in slots)

    def test_shot_triggered_uses_column_4(self):
        """ROM 0x12 col 4 = 1: a Warrior shot-triggered blast drops a Ghost 4→3."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        ghost = pack_slot(9, 9)
        _place(state, ghost, MazeObjIds.MONST_GHOST, tier=4)
        _camera_on(state, _FOCUS)
        potion_blast(state, 0, shot_triggered=True)
        assert state.mobs.hpos[ghost] & 0xF == 3, "shot-triggered col 4 does 1 damage"

    def test_magic_power_uses_the_bit8_matrix_column(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        state.players[0].powers = 0x0020
        ghost = pack_slot(9, 9)
        _place(state, ghost, MazeObjIds.MONST_GHOST, tier=4)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        # ROM 0x12 column 8 is zero: Magic-power Warrior magic destroys outright.
        assert state.mobs.obj_type(ghost) == 0

    def test_high_word_bit_does_not_select_the_magic_power_matrix_column(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        state.players[0].powers = 0x2000  # not the ROM's low-byte bit 5
        ghost = pack_slot(9, 9)
        _place(state, ghost, MazeObjIds.MONST_GHOST, tier=4)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.obj_type(ghost) == int(MazeObjIds.MONST_GHOST)
        assert state.mobs.hpos[ghost] & 0xF == 2

    def test_generator_refreshes_to_its_exact_rom_base_picture(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.ELF)
        gen = pack_slot(9, 9)
        _place(state, gen, MazeObjIds.GEN_GHOST3)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.obj_type(gen) == int(MazeObjIds.GEN_GHOST1)
        assert state.mobs.picture[gen] == 0x09AB

    def test_invalid_high_monster_tier_is_removed_after_damage(self):
        """The ROM accepts only the exact [base-2, base] tier window."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        ghost = pack_slot(9, 9)
        _place(state, ghost, MazeObjIds.MONST_GHOST, tier=6)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0, shot_triggered=True)  # entry 1: 6 -> 5 > base 4

        assert state.mobs.obj_type(ghost) == 0

    def test_potion_player_state_keeps_only_player_and_shot_provenance(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.VALKYRIE)
        state.players[0].powers = 0x0020

        potion_blast(state, 0, shot_triggered=True)

        assert state.potion_player == 0x04  # player 0 | shot 4

    def test_potion_scan_replaces_the_normal_monster_pass(self, monkeypatch):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        ghost = pack_slot(9, 9)
        _place(state, ghost, MazeObjIds.MONST_GHOST, tier=4)
        _camera_on(state, _FOCUS)
        state.playfield_color_base = 0x1234
        state.playfield_color_latch = 0xFF00
        state.potion_player = 0

        from gauntpy.subsystems import monsters
        monkeypatch.setattr(
            monsters, "monsters_everything",
            lambda *_args, **_kwargs: pytest.fail("ordinary monster pass ran"),
        )

        main_move_monsters(state)

        assert state.mobs.hpos[ghost] & 0x0F == 2

    def test_potion_is_rejected_on_maze_0x73_and_later(self):
        state = GameState(game_mode=GameMode.NORMAL)
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        state.players[0].potionsnum = 1
        state.debounce_shift_magic[0] = 0x1C
        state.mazenum_current = 0x73

        main_handle_potions(state)

        assert state.players[0].potionsnum == 1
        assert state.sound_log == [0x44]
        assert not state.dialog_first_encounter_flags & 0x10


class TestBlastCullWindow:
    """0x41560-0x41584 -- a potion clears the screen, not the level.

    Each candidate's H and V words have the camera-derived culling origins
    subtracted and are then compared *unsigned* against 0x7F80 / 0x8380 -- the
    same box ``monsters._in_cull_rect`` implements.  Anything outside it is
    skipped before the effect matrix is even consulted.
    """

    def test_near_monster_is_hit_and_far_monster_is_untouched(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        near, far = pack_slot(9, 9), _OFFSCREEN
        _place(state, near, MazeObjIds.MONST_GHOST, tier=4)
        _place(state, far, MazeObjIds.MONST_GHOST, tier=4)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.hpos[near] & 0xF == 2, "on-screen Ghost takes 2 tiers"
        assert state.mobs.obj_type(far) == int(MazeObjIds.MONST_GHOST)
        assert state.mobs.hpos[far] & 0xF == 4, "off-screen Ghost is untouched"

    def test_far_monster_is_not_destroyed_by_a_zero_matrix_entry(self):
        """The Wizard column destroys outright -- but only what is on screen."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        near, far = pack_slot(9, 9), _OFFSCREEN
        _place(state, near, MazeObjIds.MONST_DEATH)
        _place(state, far, MazeObjIds.MONST_DEATH)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.obj_type(near) == 0
        assert state.mobs.obj_type(far) == int(MazeObjIds.MONST_DEATH)
        assert state.mobs.picture[far] == 1, "record left completely alone"

    def test_near_generator_demotes_and_far_generator_does_not(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.ELF)
        near, far = pack_slot(9, 9), _OFFSCREEN
        _place(state, near, MazeObjIds.GEN_GHOST3)
        _place(state, far, MazeObjIds.GEN_GHOST3)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.obj_type(near) == int(MazeObjIds.GEN_GHOST1)
        assert state.mobs.picture[near] == 0x09AB
        assert state.mobs.obj_type(far) == int(MazeObjIds.GEN_GHOST3)
        assert state.mobs.picture[far] == 1, "off-screen generator keeps its art"

    def test_far_generator_is_not_destroyed_by_a_zero_matrix_entry(self):
        """GEN_GHOST1's Wizard column (0x1C col 2) is 0 -- destroy outright."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WIZARD)
        near, far = pack_slot(9, 9), _OFFSCREEN
        _place(state, near, MazeObjIds.GEN_GHOST1)
        _place(state, far, MazeObjIds.GEN_GHOST1)
        _camera_on(state, _FOCUS)

        potion_blast(state, 0)

        assert state.mobs.obj_type(near) == 0, "on-screen generator destroyed"
        assert state.mobs.obj_type(far) == int(MazeObjIds.GEN_GHOST1)

    def test_the_origins_are_recomputed_from_the_camera_each_blast(self):
        """The ROM recomputes them at 0x49052 immediately before the pass, so a
        blast follows the camera without anything else having to run first."""
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        left, right = pack_slot(9, 4), pack_slot(9, 24)
        _place(state, left, MazeObjIds.MONST_GHOST, tier=4)
        _place(state, right, MazeObjIds.MONST_GHOST, tier=4)

        _camera_on(state, left)
        potion_blast(state, 0)
        assert state.mobs.hpos[left] & 0xF == 2
        assert state.mobs.hpos[right] & 0xF == 4

        _camera_on(state, right)
        potion_blast(state, 0)
        assert state.mobs.hpos[right] & 0xF == 2

    def test_the_blast_matches_the_monster_loops_own_cull_test(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5), character=Character.WARRIOR)
        _camera_on(state, _FOCUS)
        slots = [pack_slot(r, c) for r in range(0, 32, 3) for c in range(0, 32, 3)]
        for slot in slots:
            _place(state, slot, MazeObjIds.MONST_GHOST, tier=4)
        _update_cull_rect(state)
        expected = {slot: _in_cull_rect(state, slot) for slot in slots}

        potion_blast(state, 0)

        for slot in slots:
            hit = (state.mobs.hpos[slot] & 0xF) == 2
            assert hit == expected[slot], f"{slot:#x} culled/hit disagree"
        assert any(expected.values()) and not all(expected.values())
