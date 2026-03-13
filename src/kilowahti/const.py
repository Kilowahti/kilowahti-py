"""Pure constants for the kilowahti library."""

from __future__ import annotations

# API
API_BASE_URL = "https://api.spot-hinta.fi"
API_ENDPOINT_TODAY = "/Today"
API_ENDPOINT_TOMORROW = "/DayForward"
API_ENDPOINT_BOTH = "/TodayAndDayForward"

# Display units
UNIT_SNTPERKWH = "c/kWh"
UNIT_EUROKWH = "€/kWh"

# Control factor functions
CONTROL_FACTOR_LINEAR = "linear"
CONTROL_FACTOR_SINUSOIDAL = "sinusoidal"

# Score formulas
SCORE_FORMULA_DEFAULT = "default"
SCORE_FORMULA_RAW = "raw"

# Country presets: {code: (vat_rate, electricity_tax_snt_per_kwh)}
COUNTRY_PRESETS: dict[str, tuple[float, float]] = {
    "FI": (0.255, 2.253),
    "SE": (0.25, 0.439),
    "NO": (0.25, 0.0713),
    "DK": (0.25, 0.008),
    "EE": (0.22, 0.001),
    "LV": (0.22, 0.0),
    "LT": (0.22, 0.001),
    "DE": (0.19, 2.05),
    "NL": (0.21, 12.28),
    "FR": (0.20, 2.57),
    "AT": (0.20, 0.001),
    "BE": (0.21, 0.001),
    "PT": (0.23, 0.001),
    "HR": (0.25, 0.001),
    "IE": (0.23, 0.001),
    "LU": (0.17, 0.001),
    "Custom": (0.0, 0.0),
}

# Available API regions
API_REGIONS = [
    "FI",
    "EE",
    "LT",
    "LV",
    "DK1",
    "DK2",
    "NO1",
    "NO2",
    "NO3",
    "NO4",
    "NO5",
    "SE1",
    "SE2",
    "SE3",
    "SE4",
]
