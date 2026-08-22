"""ROM-regression tests for WP-9 dragon state, poses, and fire."""

from __future__ import annotations

from gauntpy.constants import MazeObjIds, PlayerStatus
from gauntpy.coords import decode_hpos, decode_vpos_at_y, encode_hpos, encode_vpos_at_y, pack_slot
from gauntpy.state import GameState
from gauntpy.subsystems.dragon import (
    _DRAGON_FIRE_SEGMENT_TBL,
    _DRAGON_HEAD_PICS,
    _DRAGON_PATH_PROGRAMS,
    _FIRE_H_BY_FACING,
    _FIRE_H_BY_POSE,
    _FIRE_V_BY_FACING,
    _FIRE_V_BY_POSE,
    _HEAD_HDELTA,
    _HEAD_VDELTA,
    _ST_LOCKED,
    _ST_STUNNED,
    _ST_TURNING,
    _ST_WAKING,
    _head_index,
    _pose_index,
    dragon_shot_hit,
    main_handle_dragon,
    setup_dragon_segments,
)
from gauntpy.subsystems.exits import TRICK_NOGETHIT
from gauntpy.subsystems.shots import shot_cell

# Same skip condition test_assets.py/test_monsters.py use: only the ROM
# byte-match checks need the real ROMs on disk.
from gex.roms import _rom_dir, TILE_ROMS  # noqa: E402

import pytest  # noqa: E402

_ROM_PATH = _rom_dir()
requires_roms = pytest.mark.skipif(
    not (_ROM_PATH.is_dir() and (_ROM_PATH / TILE_ROMS[0][0]).is_file()),
    reason=f"ROM files not available at {_ROM_PATH}",
)


class _FixedRNG:
    def __init__(self, *values: int) -> None:
        self.values = list(values)

    def getrandom(self, bound: int) -> int:  # noqa: ARG002
        return self.values.pop(0) if self.values else 0


def _place_dragon(state: GameState, primary: int = pack_slot(10, 10)) -> int:
    """Create all four records so pose-selected fire origins are observable."""
    row = primary & 0x3E0
    right = row | ((primary + 1) & 0x1F)
    segments = (primary, (primary - 0x20) & 0x3FF, right, (right - 0x20) & 0x3FF)
    for number, slot in enumerate(segments):
        state.mobs.create(
            slot,
            tile=0xA000 + number,
            hpos=encode_hpos(160 + number * 16),
            vpos=encode_vpos_at_y(160 + number * 16),
            obj_type=MazeObjIds.MONST_DRAGON,
        )
    setup_dragon_segments(state, primary)
    return primary


def _place_player(state: GameState, x: int, y: int) -> None:
    player = state.players[0]
    player.status = PlayerStatus.ALIVE_HERE
    player.health = 100
    player.mob_slot = 20
    state.mobs.hpos[20] = encode_hpos(x)
    state.mobs.vpos[20] = encode_vpos_at_y(y)


class TestSetupAndWake:
    def test_setup_uses_the_rom_2x2_segment_layout(self):
        state = GameState()
        primary = _place_dragon(state)

        assert state.dragon_seg_mob_ids == [primary, primary - 0x20, primary + 1, primary - 0x1F]
        assert state.dragon_state == _ST_WAKING
        assert state.dragon_facing == 4
        assert state.dragon_move_state == 0x1044

    def test_runtime_discovers_a_primary_dragon_left_by_level_decode(self):
        state = GameState()
        primary = pack_slot(10, 10)
        state.mobs.create(
            primary,
            tile=0xA2E0,
            hpos=encode_hpos(160),
            vpos=encode_vpos_at_y(160),
            obj_type=MazeObjIds.MONST_DRAGON,
        )

        main_handle_dragon(state)

        assert state.dragon_mob_slot == primary
        assert state.dragon_seg_mob_ids[0] == primary
        assert state.dragon_state & _ST_WAKING

    def test_sleeping_dragon_starts_wake_transition_when_party_is_near(self):
        state = GameState()
        _place_dragon(state)
        _place_player(state, 18 * 16, 10 * 16)

        main_handle_dragon(state)

        assert state.dragon_anim_ctr == 0x31
        assert state.dragon_state & _ST_WAKING

    def test_sleeping_dragon_does_not_wake_for_a_distant_party(self):
        state = GameState()
        _place_dragon(state)
        _place_player(state, 31 * 16, 31 * 16)

        main_handle_dragon(state)

        assert state.dragon_anim_ctr == 0

    def test_positive_wake_completion_selects_a_path_and_enters_active_state(self):
        state = GameState()
        _place_dragon(state)
        state.rng = _FixedRNG(3)
        state.dragon_anim_ctr = 1

        main_handle_dragon(state)

        assert state.dragon_anim_ctr == 0
        assert not state.dragon_state & _ST_WAKING
        assert state.dragon_path_num == 3


class TestPoseAndAttack:
    def test_phase_boundary_uses_the_raw_path_byte_for_the_head_picture(self):
        """0x54616-0x54626: the head index keeps the fire bit (byte + facing*4).

        The 16-entry ``pose + facing*2`` index belongs to the *fire* tables
        (0x5D4B8/0x5D4C8/0x5D4E8); the head picture and the two head delta
        tables are 32 entries deep and pick a mouth-open frame when bit 0 of
        the path byte is set.
        """
        state = GameState()
        primary = _place_dragon(state)
        state.dragon_state = 0
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 7  # advances to path 0, byte 1: pose 0, fire bit 1

        main_handle_dragon(state)

        assert state.dragon_anim_ctr == 8
        assert state.mobs.picture[primary] == 0xA2F0   # mouth open, not 0xA2E0
        assert decode_hpos(state.dragon_head_hpos)[0] == 180  # 160 + ROM 20
        # ROM V grows upward, so its +18 walks the head up the screen.
        assert decode_vpos_at_y(state.dragon_head_vpos)[0] == 142  # 160 - ROM 18

    def test_a_mouth_closed_phase_takes_the_even_head_entry(self):
        state = GameState()
        primary = _place_dragon(state)
        state.dragon_state = 0
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_path_num = 1     # program 1 byte 1 is 2: pose 1, fire bit 0
        state.dragon_anim_ctr = 7

        main_handle_dragon(state)

        assert state.mobs.picture[primary] == 0xA2C0   # index 2
        assert decode_hpos(state.dragon_head_hpos)[0] == 172  # 160 + ROM 12
        assert decode_vpos_at_y(state.dragon_head_vpos)[0] == 152  # 160 - ROM 8

    def test_the_head_words_carry_no_palette_or_sprite_size(self):
        """0x5466C/0x5469E mask both results with 0xFF80."""
        state = GameState()
        primary = _place_dragon(state)
        state.mobs.hpos[primary] = encode_hpos(160, palette=0x0B, flags=0x30)
        state.mobs.vpos[primary] = encode_vpos_at_y(160, 3, 3)
        state.dragon_state = 0
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 7

        main_handle_dragon(state)

        assert state.dragon_head_hpos & 0x7F == 0
        assert state.dragon_head_vpos & 0x7F == 0

    def test_the_head_extends_along_the_facing_when_the_mouth_opens(self):
        """The 32-entry tables' whole point: index+1 is the open-mouth frame."""
        openings = {}
        for facing, axis in ((0, "v"), (2, "h"), (4, "v"), (6, "h")):
            closed = (_HEAD_HDELTA[facing * 4], _HEAD_VDELTA[facing * 4])
            opened = (_HEAD_HDELTA[facing * 4 + 1], _HEAD_VDELTA[facing * 4 + 1])
            openings[facing] = (closed, opened)
            if axis == "h":
                assert closed[1] == opened[1], facing
                assert closed[0] != opened[0], facing
            else:
                assert closed[0] == opened[0], facing
                assert closed[1] != opened[1], facing
        # ROM up (facing 0) and ROM down (facing 4) move the head opposite ways.
        assert openings[0][1][1] > openings[0][0][1]
        assert openings[4][1][1] < openings[4][0][1]

    def test_fire_uses_topmost_free_channel_and_pose_selected_segment(self):
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_LOCKED
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 8  # path 0 byte 1 is a fire phase

        main_handle_dragon(state)

        assert state.dragon_anim_ctr == 8  # locked fire holds the phase
        # Slot 8 is the topmost *demon* channel (0x540E8 scans 8 down to 5), so
        # the shot's own channel index is 7.
        assert state.mobs.picture[8] == 0x27EF
        assert state.dragon_fire_cooldown == 8
        assert state.shot_anim_lifetime_counter[7] == 0x13   # 0x54814
        assert state.shot_direction[7] == 0
        # 0x547CA records the *pose-selected* segment as the owner even though
        # 0x547DC takes the position from segment 0.
        assert state.shot_owner_mob[7] == state.dragon_seg_mob_ids[3]
        assert decode_hpos(state.mobs.hpos[8])[0] == 176      # 160 + (-4 + 20)

    def test_breath_h_and_v_words_carry_the_rom_low_bytes(self):
        """0x54866/0x5486A give H 0x38; 0x5488C gives V 0x12."""
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_LOCKED
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 8

        main_handle_dragon(state)

        assert state.mobs.hpos[8] & 0x7F == 0x38
        assert decode_hpos(state.mobs.hpos[8])[1] == 0x30     # max-tier bits
        assert decode_hpos(state.mobs.hpos[8])[2] == 8        # palette
        assert state.mobs.vpos[8] & 0x7F == 0x12
        assert decode_vpos_at_y(state.mobs.vpos[8])[1:] == (3, 3)  # 3x3 tiles
        assert decode_vpos_at_y(state.mobs.vpos[8])[0] == 131      # 160 - (5 + 24)

    def test_long_range_fire_is_the_tier_two_fireball(self):
        """0x546DC: past three cells of the firing line the ROM takes 0x54894."""
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_LOCKED
        state.dragon_facing = 0
        state.dragon_move_state = 0x0400          # high byte 4 > 3
        state.dragon_anim_ctr = 8

        main_handle_dragon(state)

        assert state.mobs.hpos[8] & 0x7F == 0x2E
        assert state.mobs.vpos[8] & 0x7F == 0x09
        assert state.shot_anim_lifetime_counter[7] == 0x01    # 0x578C2 row 7
        # projectile_picture_table[dir*2 + 0x20 + counter] = entry 0x25
        assert state.mobs.picture[8] == 0x1CDB
        assert decode_hpos(state.mobs.hpos[8])[0] == 180      # no facing term

    def test_fire_is_depth_placed_at_its_own_cell(self):
        """0x54952 -- without the insert the channel probes from cell 0."""
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_LOCKED
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 8

        main_handle_dragon(state)

        assert state.mobs.depth_key[8] == shot_cell(state, 8)
        assert state.mobs.depth_key[8] != 0

    def test_fire_leaves_every_other_shot_channel_alone(self):
        """0x547D8 indexes by channel; indexing by MOB slot rearms a neighbour."""
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_LOCKED
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 8

        # A live demon shot on channel 5 and a live lobbed rock on channel 8,
        # both flying left, plus busy channels 6 and 7 so the dragon has to
        # take MOB slot 5 (channel 4).
        for slot in (6, 7, 8, 9):
            state.mobs.picture[slot] = 0x1234
        state.shot_direction[5] = 6
        state.shot_direction[8] = 6
        state.shot_anim_lifetime_counter[5] = 1
        state.shot_anim_lifetime_counter[8] = 0x20
        state.shot_owner_mob[5] = 111
        state.shot_owner_mob[8] = 222

        main_handle_dragon(state)

        assert state.mobs.picture[5] not in (0, 0x1234), "fired into channel 4"
        assert state.shot_direction[4] == 0
        assert state.shot_anim_lifetime_counter[4] == 0x13
        assert state.shot_direction[5] == 6
        assert state.shot_direction[8] == 6
        assert state.shot_anim_lifetime_counter[5] == 1
        assert state.shot_anim_lifetime_counter[8] == 0x20
        assert state.shot_owner_mob[5] == 111
        assert state.shot_owner_mob[8] == 222

    def test_the_head_and_the_muzzle_agree_on_the_vertical_axis(self):
        """Both ROM sites add their delta to an upward V word; the port must
        subtract in both, or the head and its own breath drift apart."""
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_LOCKED
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 8

        main_handle_dragon(state)

        head_index = _head_index(state)
        pose = _pose_index(state)
        seg_y = decode_vpos_at_y(state.mobs.vpos[state.dragon_seg_mob_ids[0]])[0]
        assert decode_vpos_at_y(state.dragon_head_vpos)[0] == \
            seg_y - _HEAD_VDELTA[head_index]
        assert decode_vpos_at_y(state.mobs.vpos[8])[0] == \
            seg_y - (_FIRE_V_BY_FACING[0] + _FIRE_V_BY_POSE[pose])

    def test_fire_skips_occupied_top_channel(self):
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_LOCKED
        state.dragon_facing = 0
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 8
        state.mobs.picture[8] = 0x1234

        main_handle_dragon(state)

        assert state.mobs.picture[8] == 0x1234
        assert state.mobs.picture[7] == 0x27EF

    def test_direction_change_enters_the_turn_transition(self):
        state = GameState()
        _place_dragon(state)
        _place_player(state, 400, 160)
        state.dragon_state = 0
        state.dragon_facing = 4
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 7

        main_handle_dragon(state)

        assert state.dragon_facing == 2
        assert state.dragon_state & _ST_TURNING

    def test_close_aligned_player_selects_breath_and_locks_the_flame(self):
        state = GameState()
        _place_dragon(state)
        _place_player(state, 176, 184)
        state.dragon_state = 0
        state.dragon_facing = 4
        state.dragon_move_state = 0x0240
        state.dragon_anim_ctr = 7

        main_handle_dragon(state)

        assert state.dragon_move_state == 0x0240
        assert state.shot_anim_lifetime_counter[7] == 0x13
        assert state.shot_direction[7] == 4
        assert state.dragon_state & _ST_LOCKED

    def test_no_live_player_publishes_the_no_target_sentinel(self):
        state = GameState()
        _place_dragon(state)
        state.dragon_state = 0
        state.dragon_facing = 2
        state.dragon_move_state = 0
        state.dragon_anim_ctr = 7

        main_handle_dragon(state)

        assert state.dragon_move_state == 0x1024
        assert state.dragon_move_state & 0x0F == 4

    def test_stun_freezes_path_but_the_shared_countdown_still_decrements(self):
        state = GameState()
        _place_dragon(state)
        state.dragon_state = _ST_STUNNED
        state.dragon_fire_cooldown = 2

        main_handle_dragon(state)

        assert state.dragon_fire_cooldown == 1
        assert state.dragon_state & _ST_STUNNED
        assert state.dragon_anim_ctr == 0


class TestDamage:
    def _exposed_dragon(self) -> tuple[GameState, int]:
        state = GameState()
        primary = _place_dragon(state)
        state.dragon_state = 0
        state.dragon_facing = 0
        state.dragon_anim_ctr = 8  # path 0 byte 1 == 1
        return state, primary

    def test_hit_requires_the_rom_tile_target_bias(self):
        state, primary = self._exposed_dragon()

        dragon_shot_hit(state, primary, 0)

        assert state.dragon_hits == 0

    def test_hit_switches_to_a_path_containing_the_same_raw_byte(self):
        state, primary = self._exposed_dragon()
        state.rng = _FixedRNG(1)

        dragon_shot_hit(state, 0x400 + primary, 0)

        assert state.dragon_hits == 1
        assert state.dragon_path_num == 1
        assert state.dragon_anim_ctr == 7 << 3  # program 1's first raw byte 1
        assert 0x3A in state.sound_log

    def test_hit_is_rejected_while_turning_or_mouth_closed(self):
        state, primary = self._exposed_dragon()
        state.dragon_state = _ST_TURNING
        dragon_shot_hit(state, 0x400 + primary, 0)
        assert state.dragon_hits == 0

        state.dragon_state = 0
        state.dragon_anim_ctr = 0
        dragon_shot_hit(state, 0x400 + primary, 0)
        assert state.dragon_hits == 0

    def test_ninth_exposed_hit_removes_all_four_segments(self):
        state, primary = self._exposed_dragon()
        state.rng = _FixedRNG(*([0] * 8))
        for _ in range(9):
            state.dragon_state = 0
            state.dragon_path_num = 0
            state.dragon_anim_ctr = 8
            dragon_shot_hit(state, 0x400 + primary, 0)

        assert state.dragon_mob_slot == 0
        assert state.dragon_seg_mob_ids == [0, 0, 0, 0]
        assert not any(
            state.mobs.obj_type(slot) == int(MazeObjIds.MONST_DRAGON)
            for slot in (primary, primary - 0x20, primary + 1, primary - 0x1F)
        )
        assert state.special_bonus_score == 2000
        assert state.secret_need_hint == 1
        assert {
            state.mobs.obj_type(slot) for slot in range(32, 1024)
        } >= {
            int(MazeObjIds.TREASURE_BAG),
            int(MazeObjIds.HIDDENPOT),
        }
        assert state.mobs.obj_type(pack_slot(9, 10)) == int(
            MazeObjIds.TREASURE_BAG
        )
        assert state.mobs.obj_type(pack_slot(10, 10)) == int(
            MazeObjIds.HIDDENPOT
        )
        effect = next(
            slot for slot in range(0x0D, 0x11)
            if state.mobs.picture[slot]
        )
        assert decode_hpos(state.mobs.hpos[effect])[0] == 168
        assert decode_vpos_at_y(state.mobs.vpos[effect])[0] == 152

    def test_dragon_kill_sets_no_get_hit_progress_to_two(self):
        state, primary = self._exposed_dragon()
        state.secret_trick_id = TRICK_NOGETHIT
        state.dragon_hits = 8

        dragon_shot_hit(state, 0x400 + primary, 2)

        assert state.secret_tricks_flags[2] == 2

    def test_disqualified_no_get_hit_player_stays_disqualified_on_dragon_kill(self):
        state, primary = self._exposed_dragon()
        state.secret_trick_id = TRICK_NOGETHIT
        state.secret_tricks_flags[1] = 1
        state.dragon_hits = 8

        dragon_shot_hit(state, 0x400 + primary, 1)

        assert state.secret_tricks_flags[1] == 1


# =============================================================================
# ROM differential: the pose/facing tables and the two index formulas
# =============================================================================

class TestPoseTablesAgainstRom:
    def test_the_two_index_formulas_are_not_interchangeable(self):
        """``_head_index`` is ``2 * _pose_index + fire bit`` -- never equal."""
        state = GameState()
        _place_dragon(state)
        state.dragon_state = 0
        for facing in (0, 2, 4, 6):
            state.dragon_facing = facing
            for path in range(5):
                state.dragon_path_num = path
                for phase in range(16):
                    state.dragon_anim_ctr = phase * 8
                    byte = _DRAGON_PATH_PROGRAMS[path][phase]
                    assert _pose_index(state) == (byte >> 1) + facing * 2
                    assert _head_index(state) == byte + facing * 4
                    assert _head_index(state) == 2 * _pose_index(state) + (byte & 1)

    def test_every_head_index_is_inside_the_thirty_two_entry_tables(self):
        for facing in (0, 2, 4, 6):
            for byte in range(8):
                index = byte + facing * 4
                assert 0 <= index < len(_HEAD_HDELTA) == 32
                assert index < len(_HEAD_VDELTA) == 32
                assert index < len(_DRAGON_HEAD_PICS) == 32

    @requires_roms
    def test_the_head_tables_are_the_rom_words(self):
        from gex.roms import coderom_get_bytes

        def word(addr: int) -> int:
            raw = int.from_bytes(coderom_get_bytes(addr, 2), "big")
            return raw - 0x10000 if raw >= 0x8000 else raw

        for index in range(32):
            assert _HEAD_HDELTA[index] == word(0x5D438 + index * 2) >> 7, index
            assert _HEAD_VDELTA[index] == word(0x5D478 + index * 2) >> 7, index
            assert _DRAGON_HEAD_PICS[index] == \
                word(0x5D528 + index * 2) & 0xFFFF, index

    @requires_roms
    def test_the_fire_tables_are_the_rom_words(self):
        from gex.roms import coderom_get_bytes

        def word(addr: int) -> int:
            raw = int.from_bytes(coderom_get_bytes(addr, 2), "big")
            return raw - 0x10000 if raw >= 0x8000 else raw

        for index in range(16):
            assert _DRAGON_FIRE_SEGMENT_TBL[index] == \
                coderom_get_bytes(0x5D4B8 + index, 1)[0], index
            assert _FIRE_H_BY_POSE[index] == word(0x5D4C8 + index * 2) >> 7, index
            assert _FIRE_V_BY_POSE[index] == word(0x5D4E8 + index * 2) >> 7, index
        for index in range(4):
            assert _FIRE_H_BY_FACING[index] == word(0x5D428 + index * 2) >> 7
            assert _FIRE_V_BY_FACING[index] == word(0x5D430 + index * 2) >> 7

    @requires_roms
    def test_the_path_programs_are_the_rom_bytes(self):
        from gex.roms import coderom_get_bytes

        for path in range(5):
            for phase in range(16):
                assert _DRAGON_PATH_PROGRAMS[path][phase] == \
                    coderom_get_bytes(0x5D578 + path * 16 + phase, 1)[0]
