"""Persistence interfaces for trips and user preferences."""

from storage.json_store import (
    StorageError,
    load_preferences,
    load_trip,
    load_trips,
    save_preferences,
    save_trip,
    update_trip,
)

__all__ = [
    "StorageError",
    "load_preferences",
    "load_trip",
    "load_trips",
    "save_preferences",
    "save_trip",
    "update_trip",
]
