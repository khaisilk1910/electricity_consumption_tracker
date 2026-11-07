"""Constants and published Vietnamese residential electricity tariffs."""
from __future__ import annotations

from datetime import date

DOMAIN = "electricity_consumption_tracker"
CONF_SOURCE_SENSOR = "source_sensor"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_FRIENDLY_NAME = "friendly_name"
CONF_BILLING_DAY = "billing_day"
CONF_START_DATE_APPLY = "start_date_apply"
CONF_SOURCE_DAY_OFFSET = "source_day_offset"
DEFAULT_APPLY_DATE = "2024-01-01"
SIGNAL_UPDATE_SENSORS = "electricity_consumption_tracker_update_signal"

# Historical VAT is an estimate based on effective periods; invoice treatment may vary.
VAT_HISTORY = {
    "2019-01-01": 0.10,
    "2022-02-01": 0.08,
    "2023-01-01": 0.10,
    "2023-07-01": 0.08,
    "2024-01-01": 0.08,
    "2025-07-01": 0.08,
}

# kWh tier WIDTH and unit price before VAT, effective on the listed date.
# 2025: QD 1279/QD-BCT; 2026: QD 2892/QD-BCT (effective 2026-11-01).
PRICE_HISTORY = {
    "2019-03-20": [(50, 1678), (50, 1734), (100, 2014), (100, 2536), (100, 2834), (float("inf"), 2927)],
    "2023-05-04": [(50, 1728), (50, 1786), (100, 2074), (100, 2612), (100, 2919), (float("inf"), 3015)],
    "2023-11-09": [(50, 1806), (50, 1866), (100, 2167), (100, 2729), (100, 3050), (float("inf"), 3151)],
    "2024-10-11": [(50, 1893), (50, 1956), (100, 2271), (100, 2860), (100, 3197), (float("inf"), 3302)],
    "2025-05-10": [(50, 1984), (50, 2050), (100, 2380), (100, 2998), (100, 3350), (float("inf"), 3460)],
    "2026-11-01": [(100, 1901), (100, 2289), (200, 2894), (300, 3456), (float("inf"), 3844)],
}


def applicable_tariff(day: date) -> tuple[str, list[tuple[float, int]]]:
    """Get the last published residential tariff on or before a date."""
    key = max((key for key in PRICE_HISTORY if key <= day.isoformat()), default=min(PRICE_HISTORY))
    return key, PRICE_HISTORY[key]


def get_vat_rate(year: int, month: int, day: int) -> float:
    """Return configured historic estimate of VAT at the specified date."""
    target = date(year, month, day).isoformat()
    key = max((key for key in VAT_HISTORY if key <= target), default=min(VAT_HISTORY))
    return VAT_HISTORY[key]
