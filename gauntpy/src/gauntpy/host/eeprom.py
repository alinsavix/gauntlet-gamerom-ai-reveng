"""Host EEPROM JSON transport and explicit external-persistence policy."""

from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..game.eeprom_device import (
    EepromImage,
    EepromRotation,
    HighScoreImage,
    MemoryEepromStorage,
)
from ..game.subsystems.eeprom import HIGHSCORE_CLASSES, HIGHSCORE_RANKS

if TYPE_CHECKING:
    from ..game.state import GameState

_LOG = logging.getLogger(__name__)
DEFAULT_EEPROM_PATH = "gauntpy_eeprom.json"


class PersistencePolicy(Enum):
    READ_WRITE = "read-write"
    READ_ONLY = "read-only"
    ISOLATED = "isolated"


def _high_scores(data: object) -> HighScoreImage:
    if not isinstance(data, list) or len(data) != HIGHSCORE_CLASSES:
        raise ValueError("high_scores must contain four ladders")
    result = []
    for ladder in data:
        if not isinstance(ladder, list) or len(ladder) > HIGHSCORE_RANKS:
            raise ValueError("a high-score ladder must contain at most ten records")
        records = []
        for entry in ladder:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("a high-score record must contain score and initials")
            score, initials = entry
            if type(score) is not int or not isinstance(initials, str):
                raise ValueError("invalid high-score record types")
            records.append((score, initials))
        result.append(tuple(records))
    return tuple(result)


def _rotation(data: object) -> EepromRotation:
    if not isinstance(data, dict):
        raise ValueError("rotation must be an object")
    values = {}
    for name in EepromRotation.__dataclass_fields__:
        value = data.get(name)
        if type(value) is not int:
            raise ValueError(f"rotation.{name} must be an integer")
        values[name] = value
    return EepromRotation(**values)


def serialize_eeprom_snapshot(image: EepromImage | None) -> dict[str, object]:
    """Capture the device separately from working RAM, including a blank part."""
    data = None
    if image is not None:
        data = {
            "game_settings": image.game_settings,
            "two_player_mode": image.two_player_mode,
            "high_scores": None if image.high_scores is None else [
                [[score, initials] for score, initials in ladder]
                for ladder in image.high_scores
            ],
            "rotation": None if image.rotation is None else asdict(image.rotation),
        }
    return {"schema": 1, "image": data}


def parse_eeprom_snapshot(payload: object) -> EepromImage | None:
    """Strict snapshot parsing; unlike an operator file, damage is fatal."""
    if not isinstance(payload, dict) or set(payload) != {"schema", "image"}:
        raise ValueError("EEPROM envelope must contain exactly schema and image")
    if type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("unsupported EEPROM envelope schema")
    data = payload["image"]
    if data is None:
        return None
    if not isinstance(data, dict) or set(data) != set(EepromImage.__dataclass_fields__):
        raise ValueError("EEPROM image fields are incomplete or unknown")
    if type(data["game_settings"]) is not int:
        raise ValueError("EEPROM game_settings must be an integer")
    pricing = data["two_player_mode"]
    if pricing is not None and type(pricing) is not int:
        raise ValueError("EEPROM two_player_mode must be an integer or null")
    scores = None if data["high_scores"] is None else _high_scores(data["high_scores"])
    rotation = data["rotation"]
    if rotation is not None:
        if not isinstance(rotation, dict) or set(rotation) != set(EepromRotation.__dataclass_fields__):
            raise ValueError("EEPROM rotation fields are incomplete or unknown")
        rotation = _rotation(rotation)
    return EepromImage(data["game_settings"], pricing, scores, rotation)


class FileEepromStorage:
    """Re-read live edits, or retain accepted writes in a protected overlay."""

    def __init__(self, path: str | Path, *, policy: PersistencePolicy) -> None:
        if policy is PersistencePolicy.ISOLATED:
            raise ValueError("isolated EEPROM storage must use MemoryEepromStorage")
        self.path = Path(path)
        self.policy = policy
        self._overlay: EepromImage | None = None

    def read(self) -> EepromImage | None:
        if self._overlay is not None:
            return self._overlay
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("EEPROM image must be an object")
            settings = int(data["game_settings"])
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            _LOG.warning("Cannot read EEPROM image %s; using factory settings: %s", self.path, exc)
            return None

        pricing = None
        if "two_player_mode" in data:
            try:
                pricing = int(data["two_player_mode"])
            except (ValueError, TypeError, OverflowError) as exc:
                _LOG.warning("Ignoring corrupt EEPROM two_player_mode in %s: %s", self.path, exc)
        scores = None
        if "high_scores" in data:
            try:
                scores = _high_scores(data["high_scores"])
            except ValueError as exc:
                _LOG.warning("Ignoring corrupt EEPROM high_scores in %s: %s", self.path, exc)
        rotation = None
        if "rotation" in data:
            try:
                rotation = _rotation(data["rotation"])
            except ValueError as exc:
                _LOG.warning("Ignoring corrupt EEPROM rotation in %s: %s", self.path, exc)
        return EepromImage(settings, pricing, scores, rotation)

    def write(self, image: EepromImage) -> None:
        if self.policy is PersistencePolicy.READ_ONLY:
            self._overlay = image
            return
        from ..game.subsystems.eeprom import (
            GSETTING_COINTOSTART_MASK,
            GSETTING_COINTOSTART_SHIFT,
            GSETTING_DIFFICULTY_MASK,
            GSETTING_DIFFICULTY_SHIFT,
        )

        data = {name: value for name, value in asdict(image).items() if value is not None}
        # Retain the human-readable fields in the existing host file format.
        data["game_difficulty"] = (
            image.game_settings & GSETTING_DIFFICULTY_MASK
        ) >> GSETTING_DIFFICULTY_SHIFT
        data["coins_to_start"] = (
            (image.game_settings & GSETTING_COINTOSTART_MASK) >> GSETTING_COINTOSTART_SHIFT
        ) + 1
        payload = json.dumps(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                _LOG.warning("Cannot remove failed EEPROM write %s: %s", temporary, exc)
            raise


def bind_eeprom_storage(
    state: GameState, *, policy: PersistencePolicy | None = None,
) -> GameState:
    """Bind host configuration once; rebind to change policy, never arcade RAM."""
    if policy is None:
        policy = (
            PersistencePolicy.READ_WRITE if state.eeprom_persistence_enabled
            else PersistencePolicy.READ_ONLY
        )
    if policy is PersistencePolicy.ISOLATED:
        from ..game.subsystems.eeprom import eeprom_image

        state.eeprom_storage = MemoryEepromStorage(eeprom_image(state))
    else:
        state.eeprom_storage = FileEepromStorage(state.eeprom_save_path, policy=policy)
    return state
