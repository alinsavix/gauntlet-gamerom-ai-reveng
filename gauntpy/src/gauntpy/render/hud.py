"""Alpha/HUD layer -- the text overlay: scores, health, player names, the
message box. PLAN.md §6 WP-2 step 3.

**Flagged design decision -- no ROM font.** ``doc/01_hardware.md`` §9
documents the alphanumeric layer's *format* precisely (64x30 character grid,
one word per cell: opaque flag, palette bank/number, character index into a
1,024-glyph set) but the glyph pixels themselves live in a dedicated
character ROM (``136043-1104.6p``) that WP-1's ``AssetStore`` does not
expose -- it was scoped to the graphics-tile ROMs only
(``PLAN.md`` §6 WP-1: ``tile``/``stamp``/``palette``/``sprite``, all backed
by ``gex``'s tile-graphics decoder, never the alpha character ROM). Decoding
that ROM was out of WP-1's stated scope and is out of WP-2's too (WP-2 is
"the compositor", not "extend the asset bridge"). Rather than block on that
gap, this module renders HUD text with PIL's bundled default bitmap font.
**This is not ROM-faithful pixel art** -- it is a clearly-labelled
placeholder. Extending ``AssetStore`` with an alpha-ROM decoder (mirroring
``tile()``) and swapping the implementation here is a natural follow-up; it
does not need to change this module's public functions.

The **content** this module draws (which numbers, which layout) follows
``doc/04_game_subsystems.md`` §14 (info panel / score display) as closely as
the currently-landed state supports:

- Player score (``Player.score``, up to 7 digits per §14.2) and health
  (``Player.health``, up to 5 digits) for each of the 4 player slots that is
  not ``PlayerStatus.REMOVED``.
- The bonus multiplier is shown next to health when greater than 1, per
  §14.2's "renders the bonus multiplier when greater than one".
- A message-box outline is drawn while ``state.dialog_timer`` is nonzero
  (§10.4/§10.5's first-encounter and continue dialogs use this timer as
  their gate), but **no message text**, because no landed work package
  (WP-14 owns this) yet stores *what* the dialog should say anywhere on
  ``GameState``. Drawing the box without text is a deliberate, visible
  placeholder rather than inventing dialog copy.

Layout: the HUD occupies the strip to the right of the playfield viewport
(see ``render/compositor.py``'s ``HUD_PANEL`` -- the 336x240 screen split,
also a flagged decision since the docs give no exact pixel boundary; see
that module's docstring).
"""

from __future__ import annotations

from ..constants import PlayerStatus
from ..state import GameState

__all__ = ["draw_hud"]

_TEXT_RGBA = (255, 255, 255, 255)
_DIM_RGBA = (160, 160, 160, 255)
_BOX_RGBA = (200, 200, 200, 255)

#: Per-character-class label, since Player stores only a numeric
#: ``constants.Character`` index (doc/04_game_subsystems.md §4.4 names the
#: four classes; no ROM string table is exposed to render/ -- these are our
#: own display labels, not transcribed ROM text).
_CLASS_LABELS = {0: "WARRIOR", 1: "VALKYRIE", 2: "WIZARD", 3: "ELF"}


def _font():
    """PIL's bundled default bitmap font -- see module docstring's "no ROM
    font" decision. Imported lazily so importing this module never requires
    a font file lookup at import time.
    """
    from PIL import ImageFont

    return ImageFont.load_default()


def _draw_text(draw, xy, text, fill=_TEXT_RGBA) -> None:
    draw.text(xy, text, fill=fill, font=_font())


def draw_hud(fb, state: GameState, panel: tuple[int, int, int, int]) -> None:
    """Draw the HUD strip into ``fb``.

    ``panel`` is ``(x, y, width, height)`` in framebuffer pixels -- the
    region reserved for the info panel (see module docstring).
    """
    from PIL import ImageDraw

    px, py, pw, ph = panel
    draw = ImageDraw.Draw(fb.image)
    draw.rectangle([px, py, px + pw - 1, py + ph - 1], fill=(0, 0, 0, 255))

    row_height = 24
    for i, player in enumerate(state.players):
        row_y = py + 4 + i * row_height
        if row_y + row_height > py + ph:
            break
        if player.status == PlayerStatus.REMOVED:
            _draw_text(draw, (px + 4, row_y), f"P{i + 1} ---", fill=_DIM_RGBA)
            continue

        label = _CLASS_LABELS.get(player.character, "?")
        _draw_text(draw, (px + 4, row_y), f"P{i + 1} {label}")
        _draw_text(draw, (px + 4, row_y + 9), f"{player.score:07d}")

        health_text = f"HP {player.health:05d}"
        if player.bonusmult > 1:
            health_text += f" x{player.bonusmult}"
        _draw_text(draw, (px + 4, row_y + 18), health_text, fill=_DIM_RGBA)

    # Message box: outline only while dialog_timer gates the frame -- see
    # module docstring's "no message text" note.
    if state.dialog_timer:
        box_w, box_h = min(pw - 8, 200), 40
        box_x = px + max(0, (pw - box_w) // 2)
        box_y = py + ph - box_h - 4
        draw.rectangle(
            [box_x, box_y, box_x + box_w - 1, box_y + box_h - 1],
            outline=_BOX_RGBA, fill=(0, 0, 0, 255),
        )
