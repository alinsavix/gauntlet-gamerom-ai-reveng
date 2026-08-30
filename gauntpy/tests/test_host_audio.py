from __future__ import annotations

from pathlib import Path

from gauntpy.render import audio
from gauntpy.render.audio import SoundLibraryError, StaticSoundPlayer


class _Sound:
    def __init__(self, path):
        self.path = Path(path)


class _Channel:
    def __init__(self):
        self.busy = False
        self.sound = None
        self.loops = 0
        self.volume = 1.0
        self.stopped = 0
        self.fades = []

    def play(self, sound, loops=0):
        self.busy = True
        self.sound = sound
        self.loops = loops

    def get_busy(self):
        return self.busy

    def set_volume(self, volume):
        self.volume = volume

    def stop(self):
        self.busy = False
        self.stopped += 1

    def fadeout(self, milliseconds):
        self.busy = False
        self.fades.append(milliseconds)


class _Mixer:
    def __init__(self):
        self.speech = _Channel()
        self.channels = []
        self.stops = 0

    def Channel(self, index):
        if index == 0:
            return self.speech
        while len(self.channels) < index:
            self.channels.append(_Channel())
        return self.channels[index - 1]

    def Sound(self, path):
        return _Sound(path)

    def stop(self):
        self.stops += 1
        self.speech.stop()
        for channel in self.channels:
            channel.stop()


class _ReusingMixer(_Mixer):
    def Channel(self, index):
        if index == 0:
            return self.speech
        if not self.channels:
            self.channels.append(_Channel())
        return self.channels[0]


def _library(tmp_path, *commands):
    for command in commands:
        (tmp_path / f"0x{command:02X}_test.wav").touch()
    return tmp_path


def test_effect_commands_play_once_and_looping_commands_wait_for_their_stop(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x0D, 0x20))

    player.consume([0x0D, 0x20])

    assert [channel.sound.path.name for channel in mixer.channels] == [
        "0x0D_test.wav", "0x20_test.wav",
    ]
    assert [channel.loops for channel in mixer.channels] == [0, -1]

    player.consume([0x0D, 0x20, 0x21])

    assert mixer.channels[1].stopped == 1


def test_forcefield_slow_motion_and_music_controls_target_the_rom_commands(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(
        mixer, _library(tmp_path, 0x2E, 0x37, 0x3B, 0x3D, 0x3E),
    )
    player.consume([0x2E, 0x37, 0x3B, 0x3D, 0x3E])

    player.consume([0x2E, 0x37, 0x3B, 0x3D, 0x3E, 0x2F, 0x39, 0x3C, 0x41])

    assert mixer.channels[0].stopped == 1
    assert mixer.channels[1].stopped == 1
    assert mixer.channels[2].fades == [1000]
    assert mixer.channels[3].stopped == 1
    assert mixer.channels[4].fades == [1000]


def test_end_slow_motion_replaces_the_loop_before_the_final_silencer(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x37, 0x38))
    player.consume([0x37])
    loop = mixer.channels[0]

    player.consume([0x37, 0x38])

    assert loop.stopped == 0
    assert loop.volume == 0.0
    assert mixer.channels[1].sound.path.name == "0x38_test.wav"

    player.consume([0x37, 0x38, 0x39])
    assert loop.stopped == 1


def test_higher_priority_sound_suppresses_then_releases_a_lower_channel(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x45, 0x43))
    player.consume([0x45, 0x43])

    assert mixer.channels[0].volume == 0.0
    assert mixer.channels[1].volume == 1.0

    mixer.channels[1].busy = False
    player.consume([0x45, 0x43])

    assert mixer.channels[0].volume == 1.0


def test_equal_priority_replaces_the_old_physical_channel_member(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x48, 0x49))
    player.consume([0x48, 0x49])

    assert mixer.channels[0].stopped == 1
    assert mixer.channels[1].volume == 1.0


def test_type7_metadata_covers_every_sound_rom_sequence_command():
    assert len(audio._TYPE7_CHANNEL_PRIORITIES) == 62
    assert audio._TYPE7_CHANNEL_PRIORITIES[0x37] == ((8, 8),)
    assert audio._TYPE7_CHANNEL_PRIORITIES[0x38] == ((8, 9),)
    assert audio._TYPE7_CHANNEL_PRIORITIES[0x3B] == tuple(
        (channel, 61) for channel in range(4, 12)
    )


def test_fading_theme_retains_priority_until_the_ramp_finishes(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x3B, 0x42))

    player.consume([0x3B, 0x3C, 0x42])

    assert mixer.channels[0].fades == [1000]
    assert mixer.channels[1].volume == 0.0

    mixer.channels[0].busy = False
    player.consume([0x3B, 0x3C, 0x42])

    assert mixer.channels[1].volume == 1.0


def test_effect_allocator_skips_a_busy_lane_when_another_is_free(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x37, 0x38))
    player.consume([0x37])
    player._next_effect_channel = 1

    player.consume([0x37, 0x38])

    assert mixer.channels[0].sound.path.name == "0x37_test.wav"
    assert mixer.channels[0].stopped == 0
    assert mixer.channels[1].sound.path.name == "0x38_test.wav"


def _fill_type7_pool(player, members):
    for command, hardware_channel, priority in members:
        channel = _Channel()
        channel.busy = True
        playback = audio._Type7Playback(
            command, channel, {hardware_channel: priority},
        )
        player._type7_playbacks.append(playback)
        player._playing.setdefault(command, []).append(channel)


def test_full_logical_pool_rejects_lower_priority_record_and_chain_suffix(tmp_path):
    player = StaticSoundPlayer(_Mixer(), _library(tmp_path, 0x05))
    members = [(0x80 + index, 2 + index % 10, 10 + index) for index in range(28)]
    members.extend(((0xA0, 0, 7), (0xA1, 1, 9)))
    _fill_type7_pool(player, members)

    accepted = player._admit_type7_members(0x05)

    assert accepted == {0: 8}
    assert player._logical_member_count() == 29


def test_full_logical_pool_reclaims_requested_channel_lowest_priority(tmp_path):
    player = StaticSoundPlayer(_Mixer(), _library(tmp_path, 0x43))
    members = [(0x80 + index, 2 + index % 10, 10 + index) for index in range(29)]
    members.append((0xA0, 0, 2))
    _fill_type7_pool(player, members)

    accepted = player._admit_type7_members(0x43)

    assert accepted == {0: 51}
    assert player._logical_member_count() == 29


def test_a_reused_mixer_channel_is_detached_from_its_old_stop_target(tmp_path):
    mixer = _ReusingMixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x20, 0x0D))
    player.consume([0x20, 0x0D])

    player.consume([0x20, 0x0D, 0x21])

    assert mixer.channels[0].sound.path.name == "0x0D_test.wav"
    assert mixer.channels[0].stopped == 0


def test_speech_is_serial_and_higher_priority_flushes_only_pending_phrases(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(
        mixer, _library(tmp_path, 0x4A, 0x4B, 0x4C, 0xA1),
    )

    player.consume([0x4A, 0x4B, 0x4C])
    assert mixer.speech.sound.path.name == "0x4A_test.wav"
    assert list(player._speech_queue) == [(0x4B, 0), (0x4C, 0)]

    player.consume([0x4A, 0x4B, 0x4C, 0xA1])
    assert mixer.speech.sound.path.name == "0x4A_test.wav"
    assert list(player._speech_queue) == [(0xA1, 0x40)]

    mixer.speech.busy = False
    player.consume([0x4A, 0x4B, 0x4C, 0xA1])
    assert mixer.speech.sound.path.name == "0xA1_test.wav"


def test_full_speech_queue_rejects_even_a_higher_priority_arrival(tmp_path):
    commands = tuple(range(0x4A, 0x53)) + (0xA1,)
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, *commands))

    player.consume(list(range(0x4A, 0x52)))
    assert len(player._speech_queue) == 7
    player.consume([*range(0x4A, 0x52), 0xA1])

    assert len(player._speech_queue) == 7
    assert all(command != 0xA1 for command, _priority in player._speech_queue)


def test_filter_and_mixer_commands_update_live_host_channels(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(
        mixer, _library(tmp_path, 0x0D, 0x22, 0x3B, 0x3D, 0x4A),
    )
    player.consume([0x0D, 0x22, 0x3B, 0x3D, 0x4A])

    player.consume([0x0D, 0x22, 0x3B, 0x3D, 0x4A, 0x01])
    assert [channel.volume for channel in mixer.channels] == [0.0, 1.0, 1.0, 0.0]
    assert mixer.speech.volume == 0.0

    player.consume([0x0D, 0x22, 0x3B, 0x3D, 0x4A, 0x01, 0x02, 0xD7])
    assert [channel.volume for channel in mixer.channels] == [
        0.0, 1 / 3, 1.0, 0.0,
    ]
    assert mixer.speech.volume == 1.0


def test_reinitialize_stops_everything_and_clears_pending_speech(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x20, 0x4A, 0x4B))
    player.consume([0x20, 0x4A, 0x4B])

    player.consume([0x20, 0x4A, 0x4B, 0x00])

    assert mixer.stops == 1
    assert list(player._speech_queue) == []
    assert player._playing == {}


def test_missing_playable_command_is_an_explicit_library_error(tmp_path):
    player = StaticSoundPlayer(_Mixer(), tmp_path)

    try:
        player.consume([0x0D])
    except SoundLibraryError as exc:
        assert "0x0D" in str(exc)
    else:
        raise AssertionError("missing playable WAV should fail explicitly")


def test_skip_existing_does_not_replay_snapshot_history(tmp_path):
    mixer = _Mixer()
    player = StaticSoundPlayer(mixer, _library(tmp_path, 0x0D, 0x13))
    log = [0x0D]
    player.skip_existing(log)

    player.consume(log)
    assert mixer.channels == []
    log.append(0x13)
    player.consume(log)
    assert mixer.channels[0].sound.path.name == "0x13_test.wav"


def test_command_descriptions_come_from_wav_names_and_control_semantics(tmp_path):
    player = StaticSoundPlayer(
        _Mixer(), _library(tmp_path, 0x26, 0x4A),
    )

    assert player.command_descriptions[0x26] == "test"
    assert player.command_descriptions[0x39] == "Slow motion silencer"
