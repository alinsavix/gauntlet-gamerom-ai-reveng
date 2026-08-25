"""pygame host shell. PLAN.md §6 WP-2 step 5.

**pygame is an optional import.** Nothing at module import time touches it --
only constructing a ``HostShell`` does -- so ``import gauntpy.render.host``
never fails in a headless environment without pygame installed (the
requirement from PLAN.md §6 WP-2: "make pygame an OPTIONAL import ... only
the host shell needs it"). The compositor modules this file drives
(``compositor.py``, ``playfield.py``, ``mobs.py``, ``hud.py``,
``framebuffer.py``) import none of this back, so nothing about them depends
on pygame either.

``HostShell`` supplies exactly the two methods ``mainloop.g2mainloop``
expects (``wait_for_vblank(state)``, ``present(state)``), so
``g2mainloop(state, HostShell())`` drives the whole game loop directly, per
PLAN.md §6 WP-2 step 5's "Supplying ``wait_for_vblank``/``present`` lets
``g2mainloop`` drive your host directly."

**Input mapping.** Only ``subsystems/input.py``'s ``JOY_*`` bit constants are
imported here (a constants-only import, explicitly allowed by this
package's brief even though ``render/`` otherwise never imports
``subsystems/*``). Raw input words are **active low**
(``doc/04_game_subsystems.md`` §15; ``subsystems/input.py``'s own docstring)
-- ``JOY_IDLE`` (all bits set) means nothing pressed, and a held key clears
its bit. Getting this backwards inverts every control in the game, so it is
asserted in ``tests/test_render.py``'s ROM-free input-mapping test.

**The VBLANK semaphore is a hardware boundary, not a gap.** On the cabinet
``vblank_flag`` (0x904002) is set by an asynchronous interrupt, so it can be
re-raised *while* ``game_frame`` is still running -- that is exactly how
``check_frame_overflow`` learns the frame ran long. ``mainloop.tick()`` clears
it as its first statement and checks it afterward, so the only way to observe
an overflow is for something to set the flag between those two points. A
synchronous, single-threaded host has no such concurrent signal source: by
construction there is nothing running during ``game_frame`` that could raise
it. So under this host ``frame_overflow`` stays at zero and the generator
spawn throttling it gates never activates from real frame pressure.

That is a property of hosting the simulation synchronously, not something
this module leaves undone, and it is not fixable from the
``wait_for_vblank``/``present`` seam ``g2mainloop`` offers -- a host would
have to drive ``game_frame`` itself, or run it on another thread, to have
anywhere to put the interrupt. Tests that need overflow behaviour set
``state.frame_overflow`` directly, which is what the subsystems read anyway.
"""

from __future__ import annotations

from collections import deque

from ..constants import FRAMES_PER_SECOND
from ..state import GameState
from ..subsystems.input import JOY_DOWN, JOY_FIRE_BIT, JOY_IDLE, JOY_LEFT, JOY_MAGIC_BIT, JOY_RIGHT, JOY_UP
from .compositor import LOGICAL_HEIGHT, LOGICAL_WIDTH, RenderCache, render_frame
from .diagnostics import (
    DEBUG_PAGES,
    DEBUG_PANEL_WIDTH,
    capture_debug_snapshot,
    derive_debug_events,
    render_debug_panel,
)
from .debug_controls import debug_add_key, debug_add_potion, debug_skip_level
from .state_dump import dump_game_state

__all__ = [
    "PygameUnavailable", "HostShell", "DEFAULT_KEYMAP",
    "DEFAULT_COIN_KEY", "DEFAULT_PAUSE_KEY", "DEFAULT_DIAGNOSTICS_KEY",
    "DEFAULT_DIAGNOSTICS_NEXT_KEY", "DEFAULT_DIAGNOSTICS_PREV_KEY",
    "DEFAULT_DIAGNOSTICS_MOB_PREV_KEY", "DEFAULT_DIAGNOSTICS_MOB_NEXT_KEY",
    "DEFAULT_STATE_DUMP_KEY",
    "DEFAULT_SKIP_LEVEL_KEY", "DEFAULT_ADD_KEY_KEY", "DEFAULT_ADD_POTION_KEY",
]


class PygameUnavailable(RuntimeError):
    """Raised by ``HostShell()`` when pygame isn't installed. Callers that
    only want the compositor never hit this -- it is only raised by code
    that actually tries to open a window.
    """


#: pygame key attribute name -> JOY_* bit. Resolved against the real
#: ``pygame`` module lazily (inside ``HostShell.__init__``) so this table
#: itself doesn't require pygame to be importable.
DEFAULT_KEYMAP: dict[str, int] = {
    "K_UP": JOY_UP,
    "K_DOWN": JOY_DOWN,
    "K_LEFT": JOY_LEFT,
    "K_RIGHT": JOY_RIGHT,
    "K_LCTRL": JOY_FIRE_BIT,
    "K_SPACE": JOY_FIRE_BIT,
    "K_LALT": JOY_MAGIC_BIT,
    "K_RETURN": JOY_MAGIC_BIT,
}

#: Coin key: an edge (keydown), not a held bit, so it lives outside the JOY_*
#: keymap. "5" is the classic arcade coin slot. Pressing it bumps the host
#: player's 2-bit coin counter, exactly the signal ``coincheck`` polls.
DEFAULT_COIN_KEY = "K_5"
DEFAULT_PAUSE_KEY = "K_p"
DEFAULT_DIAGNOSTICS_KEY = "K_F1"
DEFAULT_DIAGNOSTICS_NEXT_KEY = "K_F3"
DEFAULT_DIAGNOSTICS_PREV_KEY = "K_F2"
DEFAULT_DIAGNOSTICS_MOB_PREV_KEY = "K_LEFTBRACKET"
DEFAULT_DIAGNOSTICS_MOB_NEXT_KEY = "K_RIGHTBRACKET"
DEFAULT_STATE_DUMP_KEY = "K_F4"
DEFAULT_SKIP_LEVEL_KEY = "K_F5"
DEFAULT_ADD_KEY_KEY = "K_F6"
DEFAULT_ADD_POTION_KEY = "K_F7"


class HostShell:
    """A pygame window, one player's keyboard mapped to
    ``state.player_input_raw``, and a 60Hz pump.

    ``assets`` may be supplied up front, or left ``None`` to construct a
    real ``AssetStore`` (which requires ROMs) lazily on first ``present()``
    -- this lets ``HostShell(assets=fake)`` be unit-tested without ROMs, and
    keeps ``__init__`` itself ROM-independent (only opening a window needs
    pygame; only drawing a frame needs ROMs).
    """

    def __init__(
        self,
        *,
        assets=None,
        scale: int = 4,
        player: int = 0,
        title: str = "gauntpy",
        keymap: dict[str, int] | None = None,
        diagnostics: bool = False,
    ) -> None:
        try:
            import pygame
        except ImportError as exc:
            raise PygameUnavailable(
                "gauntpy.render.host.HostShell needs pygame (or pygame-ce). "
                "Install the 'display' extra: pip install gauntpy[display]"
            ) from exc

        self._pygame = pygame
        self.scale = scale
        self.player = player
        self._assets = assets
        self._cache = RenderCache()
        self._title = title
        self.paused = False
        self.diagnostics_visible = diagnostics
        self.diagnostics_page = 0
        self.diagnostics_selected_mob = 0
        self._diagnostics_previous = None
        self._diagnostics_events: deque[str] = deque(maxlen=64)
        self.last_state_dump_path = None

        pygame.init()
        self.window = self._set_window_mode()
        pygame.display.set_caption(title)
        self.clock = pygame.time.Clock()

        keymap = keymap if keymap is not None else DEFAULT_KEYMAP
        self._keymap = {getattr(pygame, name): bit for name, bit in keymap.items()}
        self._coin_key = getattr(pygame, DEFAULT_COIN_KEY)
        self._pause_key = getattr(pygame, DEFAULT_PAUSE_KEY)
        self._diagnostics_key = getattr(pygame, DEFAULT_DIAGNOSTICS_KEY)
        self._diagnostics_next_key = getattr(
            pygame, DEFAULT_DIAGNOSTICS_NEXT_KEY,
        )
        self._diagnostics_prev_key = getattr(
            pygame, DEFAULT_DIAGNOSTICS_PREV_KEY,
        )
        self._diagnostics_mob_prev_key = getattr(
            pygame, DEFAULT_DIAGNOSTICS_MOB_PREV_KEY,
        )
        self._diagnostics_mob_next_key = getattr(
            pygame, DEFAULT_DIAGNOSTICS_MOB_NEXT_KEY,
        )
        self._state_dump_key = getattr(pygame, DEFAULT_STATE_DUMP_KEY)
        self._skip_level_key = getattr(pygame, DEFAULT_SKIP_LEVEL_KEY)
        self._add_key_key = getattr(pygame, DEFAULT_ADD_KEY_KEY)
        self._add_potion_key = getattr(pygame, DEFAULT_ADD_POTION_KEY)

    def _set_window_mode(self):
        game_width = LOGICAL_WIDTH * self.scale
        panel_width = DEBUG_PANEL_WIDTH if self.diagnostics_visible else 0
        return self._pygame.display.set_mode(
            (game_width + panel_width, LOGICAL_HEIGHT * self.scale)
        )

    # -- the g2mainloop interface --------------------------------------------

    def wait_for_vblank(self, state: GameState) -> None:
        """Pump the event queue, sample the keyboard into
        ``state.player_input_raw``, and block until the next 60Hz tick
        boundary. See the module docstring for why this does not attempt to
        drive ``state.vblank_flag``.
        """
        pygame = self._pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit(0)
            if event.type == pygame.KEYDOWN:
                if event.key == self._coin_key:
                    self._insert_coin(state)
                elif event.key == self._pause_key:
                    self.paused = not self.paused
                    pygame.display.set_caption(
                        f"{self._title} [PAUSED]" if self.paused else self._title
                    )
                elif event.key == self._diagnostics_key:
                    self.diagnostics_visible = not self.diagnostics_visible
                    self._diagnostics_previous = None
                    self.window = self._set_window_mode()
                elif event.key == self._state_dump_key:
                    self.last_state_dump_path = dump_game_state(state)
                    print(f"gauntpy state saved: {self.last_state_dump_path}")
                elif event.key == self._skip_level_key:
                    if debug_skip_level(state):
                        print(
                            "gauntpy skipped to "
                            f"level {state.levelnum_current} / maze {state.mazenum_current}"
                        )
                    else:
                        print("gauntpy level skip ignored outside active play")
                elif event.key == self._add_key_key:
                    if debug_add_key(state, self.player):
                        print(
                            f"gauntpy P{self.player + 1} keys: "
                            f"{state.players[self.player].keysnum}"
                        )
                    else:
                        print("gauntpy add-key ignored for inactive player")
                elif event.key == self._add_potion_key:
                    if debug_add_potion(state, self.player):
                        print(
                            f"gauntpy P{self.player + 1} potions: "
                            f"{state.players[self.player].potionsnum}"
                        )
                    else:
                        print("gauntpy add-potion ignored for inactive player")
                elif (
                    self.diagnostics_visible
                    and event.key == self._diagnostics_next_key
                ):
                    self.diagnostics_page = (
                        self.diagnostics_page + 1
                    ) % len(DEBUG_PAGES)
                elif (
                    self.diagnostics_visible
                    and event.key == self._diagnostics_prev_key
                ):
                    self.diagnostics_page = (
                        self.diagnostics_page - 1
                    ) % len(DEBUG_PAGES)
                elif (
                    self.diagnostics_visible
                    and event.key == self._diagnostics_mob_prev_key
                ):
                    self._step_diagnostics_mob(state, -1)
                elif (
                    self.diagnostics_visible
                    and event.key == self._diagnostics_mob_next_key
                ):
                    self._step_diagnostics_mob(state, 1)

        self._sample_input(state)
        self.clock.tick(FRAMES_PER_SECOND)

    def _insert_coin(self, state: GameState) -> None:
        """Bump this host player's 2-bit coin counter (0x904FEC layout).

        A coin is an *edge*: handled on keydown, not per-frame like the held
        JOY_* keys. ``coincheck`` reads the delta against ``last_coin_state``.
        """
        shift = self.player * 2
        current = (state.coin_counters >> shift) & 3
        state.coin_counters = (
            (state.coin_counters & ~(3 << shift)) | (((current + 1) & 3) << shift)
        )

    def _step_diagnostics_mob(self, state: GameState, delta: int) -> None:
        occupied = [
            slot for slot in range(1, len(state.mobs.picture))
            if state.mobs.picture[slot]
        ]
        if not occupied:
            self.diagnostics_selected_mob = 0
            return
        if self.diagnostics_selected_mob not in occupied:
            self.diagnostics_selected_mob = occupied[0 if delta >= 0 else -1]
            return
        index = occupied.index(self.diagnostics_selected_mob)
        self.diagnostics_selected_mob = occupied[(index + delta) % len(occupied)]

    def present(self, state: GameState) -> None:
        """Render the current state and flip it to the window."""
        if self._assets is None:
            from ..assets import AssetStore

            self._assets = AssetStore()

        fb, self._cache = render_frame(
            state, self._assets, cache=self._cache, paused=self.paused,
        )
        image = fb.image
        surface = self._pygame.image.frombuffer(image.tobytes(), image.size, image.mode).convert_alpha()
        if self.scale != 1:
            surface = self._pygame.transform.scale(
                surface, (LOGICAL_WIDTH * self.scale, LOGICAL_HEIGHT * self.scale)
            )
        self.window.blit(surface, (0, 0))
        if self.diagnostics_visible:
            snapshot = capture_debug_snapshot(
                state,
                paused=self.paused,
                selected_mob=self.diagnostics_selected_mob,
            )
            self.diagnostics_selected_mob = snapshot.selected_mob
            for event in derive_debug_events(self._diagnostics_previous, snapshot):
                self._diagnostics_events.append(
                    f"{snapshot.frame:05d} {event}"
                )
            self._diagnostics_previous = snapshot
            panel = render_debug_panel(
                snapshot,
                height=LOGICAL_HEIGHT * self.scale,
                page=self.diagnostics_page,
                events=tuple(self._diagnostics_events),
            )
            panel_surface = self._pygame.image.frombuffer(
                panel.tobytes(), panel.size, panel.mode,
            ).convert_alpha()
            self.window.blit(panel_surface, (LOGICAL_WIDTH * self.scale, 0))
        self._pygame.display.flip()

    # -- input ---------------------------------------------------------------

    def _sample_input(self, state: GameState) -> None:
        """Active-low raw word: start from ``JOY_IDLE`` (all bits set, i.e.
        nothing pressed) and clear the bit for each held key -- see module
        docstring.
        """
        pressed = self._pygame.key.get_pressed()
        raw = JOY_IDLE
        for keycode, bit in self._keymap.items():
            if pressed[keycode]:
                raw &= ~bit
        state.player_input_raw[self.player] = raw & 0xFFFF

    # -- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        self._pygame.quit()
