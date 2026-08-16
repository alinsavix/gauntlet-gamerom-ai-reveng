"""Sound -- WP-18. Stubbed: the queue is real, the audio is not.

Implement the command queue, not the synthesis. Every emitted command gets
logged, which turns sound into a **test oracle** for the other packages ("this
event plays sound 0x37") rather than dead weight.

219 command IDs (0x00-0xDA); command 0x00 is reinitialize/stop-all, 0x06 the
command-count query, 0x07 the diagnostic fault query.

Reference: ``doc/04_game_subsystems.md`` §11; ``refs/soundcmds.csv``;
``book/16_sound.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def sound_play(state: GameState, sound_id: int) -> None:
    """0x4AD76 -- queue a sound command. Called from all over the game."""


@stub
def sound_speech_play(state: GameState, speech_id: int) -> None:
    """0x4AD4E -- queue a speech command. See §11.4."""


@stub
def sound_response(state: GameState) -> None:
    """0x42D0A -- process replies from the sound board. See §11.3."""


@stub
def main_update_sound(state: GameState) -> None:
    """0x4AE20 -- drain the outgoing sound command queue. See §11.2."""
