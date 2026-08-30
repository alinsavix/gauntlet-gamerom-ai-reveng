from __future__ import annotations

from pathlib import Path

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
        assert index == 0
        return self.speech

    def Sound(self, path):
        return _Sound(path)

    def find_channel(self, force):
        assert force
        channel = _Channel()
        self.channels.append(channel)
        return channel

    def stop(self):
        self.stops += 1
        self.speech.stop()
        for channel in self.channels:
            channel.stop()


class _ReusingMixer(_Mixer):
    def find_channel(self, force):
        assert force
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
    assert mixer.channels[3].fades == [1000]
    assert mixer.channels[4].fades == [1000]


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
        1 / 3, 1 / 3, 1.0, 1.0,
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
