from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()
DATA_DIR = Path(os.getenv("TRAVEL_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
TRIPS_FILE = DATA_DIR / "trips.json"
PREFERENCES_FILE = DATA_DIR / "preferences.json"


class StorageError(RuntimeError):
    """Raised when persisted data cannot be read or safely written."""


def load_trips() -> list[dict[str, Any]]:
    with _LOCK:
        data = _read_json(TRIPS_FILE, [])
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise StorageError(f"Trip data in {TRIPS_FILE} must be a JSON array of objects.")
        return data


def load_trip(trip_id: str) -> dict[str, Any]:
    for trip in load_trips():
        if str(trip.get("id")) == str(trip_id):
            return trip
    raise KeyError(f"No saved trip found with id {trip_id}.")


def save_trip(trip_data: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        trips = load_trips()
        record = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **trip_data,
        }
        trips.append(record)
        _atomic_write(TRIPS_FILE, trips)
        logger.info("Saved trip %s", record["id"])
        return record


def update_trip(trip_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        trips = load_trips()
        for index, trip in enumerate(trips):
            if str(trip.get("id")) == str(trip_id):
                updated = {**trip, **changes, "id": trip["id"]}
                trips[index] = updated
                _atomic_write(TRIPS_FILE, trips)
                return updated
    raise KeyError(f"No saved trip found with id {trip_id}.")


def load_preferences() -> dict[str, Any]:
    with _LOCK:
        data = _read_json(PREFERENCES_FILE, {})
        if not isinstance(data, dict):
            raise StorageError(f"Preference data in {PREFERENCES_FILE} must be a JSON object.")
        return data


def save_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        _atomic_write(PREFERENCES_FILE, preferences)
        logger.info("Saved user preferences")
        return preferences


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Could not read persisted JSON from %s", path)
        raise StorageError(f"Could not read persisted data from {path}: {exc}") from exc


def _atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except (OSError, TypeError, ValueError) as exc:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)
        logger.exception("Could not write persisted JSON to %s", path)
        raise StorageError(f"Could not safely write persisted data to {path}: {exc}") from exc
