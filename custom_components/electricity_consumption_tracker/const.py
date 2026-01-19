"""Constants for the Electricity Consumption Tracker integration."""

DOMAIN = "electricity_consumption_tracker"
CONF_SOURCE_SENSOR = "source_sensor"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_FRIENDLY_NAME = "friendly_name"

# Biểu giá điện sinh hoạt (EVN)
# Format: "YYYY-MM-DD": [(limit_kwh, price_vnd), ..., (float('inf'), price_vnd)]
PRICE_HISTORY = {
    "2019-03-20": [(50, 1678), (50, 1734), (100, 2014), (100, 2536), (100, 2834), (float('inf'), 2927)],
    "2023-05-04": [(50, 1806), (50, 1866), (100, 2167), (100, 2729), (100, 3050), (float('inf'), 3151)],
    "2024-10-11": [(50, 1893), (50, 1956), (100, 2271), (100, 2860), (100, 3197), (float('inf'), 3302)],
    "2025-05-10": [(50, 1984), (50, 2050), (100, 2380), (100, 2998), (100, 3350), (float('inf'), 3460)]
}
