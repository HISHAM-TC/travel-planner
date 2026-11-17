from __future__ import annotations

"""Compatibility exports for the original app package."""

from models.trip import TripRequest, trip_request_from_dict

__all__ = ["TripRequest", "trip_request_from_dict"]
