"""JSON schemas exposed to OpenAI function calling."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "Fetch real daily weather for a destination and date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "days": {"type": "integer", "minimum": 1},
                },
                "required": ["destination", "start_date", "days"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": "Search OpenStreetMap within the requested destination areas and apply any specified dietary preference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "interests": {"type": "array", "items": {"type": "string"}},
                    "areas": {"type": "array", "items": {"type": "string"}},
                    "diet": {"type": "string"},
                    "food_styles": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["destination", "interests"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_travel_time",
            "description": "Estimate travel time between two verified place coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "destination": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                },
                "required": ["origin", "destination"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_trip_budget",
            "description": "Calculate category allocations and known trip costs in the requested currency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget": {"type": "number", "exclusiveMinimum": 0},
                    "days": {"type": "integer", "minimum": 1},
                    "currency": {"type": "string"},
                    "known_costs": {"type": "array", "items": {"type": "number", "minimum": 0}},
                    "budget_split": {
                        "type": "object",
                        "properties": {
                            "stay": {"type": "number", "minimum": 0},
                            "food": {"type": "number", "minimum": 0},
                            "transport": {"type": "number", "minimum": 0},
                            "activities": {"type": "number", "minimum": 0},
                            "misc": {"type": "number", "minimum": 0},
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["budget", "days", "currency"],
                "additionalProperties": False,
            },
        },
    },
]
