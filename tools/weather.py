from __future__ import annotations

import logging
import urllib.parse
from datetime import date, timedelta
from typing import Any

from tools.base import request_json

logger = logging.getLogger(__name__)


def get_weather_forecast(destination: str, start_date: str, days: int) -> dict[str, Any]:
    """Fetch real Open-Meteo daily weather; unavailable data is never synthesized."""
    if not destination.strip() or days <= 0:
        return _unavailable("Destination and a positive day count are required.")
    try:
        start = date.fromisoformat(start_date)
    except ValueError:
        return _unavailable("A valid start date is required to fetch forecast data.")

    geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": destination, "count": 1, "language": "en", "format": "json"}
    )
    geocode, error = request_json(geocode_url)
    results = geocode.get("results") if isinstance(geocode, dict) else None
    if not results:
        return _unavailable(error or f"No coordinates found for {destination}.")

    coordinates = results[0]
    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return _unavailable("The geocoding service returned invalid coordinates.")

    end = start + timedelta(days=days - 1)
    forecast_limit = date.today() + timedelta(days=15)
    if end > forecast_limit:
        return _unavailable(
            f"Open-Meteo daily forecasts are currently available only through {forecast_limit.isoformat()}."
        )
    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
    )
    forecast, error = request_json(forecast_url)
    daily = forecast.get("daily") if isinstance(forecast, dict) else None
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
        return _unavailable(error or "The forecast provider returned no daily forecast.")

    days_result: list[dict[str, Any]] = []
    for index, forecast_date in enumerate(daily["time"][:days]):
        code = _at(daily.get("weather_code"), index)
        minimum = _at(daily.get("temperature_2m_min"), index)
        maximum = _at(daily.get("temperature_2m_max"), index)
        rain_probability = _at(daily.get("precipitation_probability_max"), index)
        days_result.append(
            {
                "date": forecast_date,
                "summary": _summarize_weather_code(code) if isinstance(code, (int, float)) else "Forecast unavailable",
                "temperature_range": _temperature_range(minimum, maximum),
                "precipitation_probability": rain_probability,
            }
        )

    if len(days_result) != days:
        return _unavailable("The provider returned an incomplete forecast for the requested dates.")
    logger.info("Tool call weather: retrieved %s forecast days for %s", len(days_result), destination)
    return {"status": "ok", "source": "Open-Meteo", "days": days_result, "warning": None}


def _unavailable(message: str) -> dict[str, Any]:
    logger.warning("Weather tool unavailable: %s", message)
    return {"status": "unavailable", "source": "Open-Meteo", "days": [], "warning": message}


def _at(values: Any, index: int) -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else None


def _temperature_range(minimum: Any, maximum: Any) -> str | None:
    if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        return None
    return f"{round(minimum)}°C to {round(maximum)}°C"


def _summarize_weather_code(code: int | float) -> str:
    if code == 0:
        return "Clear sky"
    if code in (1, 2, 3):
        return "Partly cloudy"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Weather conditions unavailable"
