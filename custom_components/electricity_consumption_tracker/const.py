"""Constants for the Electricity Consumption Tracker integration."""
from datetime import datetime

DOMAIN = "electricity_consumption_tracker"
CONF_SOURCE_SENSOR = "source_sensor"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_FRIENDLY_NAME = "friendly_name"

# Lịch sử thuế VAT
# Format: "YYYY-MM-DD": rate (float)
# Ví dụ 0.08 tương đương 8%, 0.10 tương đương 10%
VAT_HISTORY = {
    "2019-01-01": 0.10,
    "2022-02-01": 0.08, # Nghị định 15/2022/NĐ-CP
    "2023-01-01": 0.10, # Hết giảm thuế
    "2023-07-01": 0.08, # Nghị định 44/2023/NĐ-CP
    "2024-01-01": 0.08, # Tiếp tục giảm thuế
    "2026-01-01": 0.08  # Hiện tại
}

# [HELPER] Hàm lấy VAT rate theo ngày
def get_vat_rate(year, month, day):
    target_date = f"{year}-{month:02d}-{day:02d}"
    valid_dates = [d for d in VAT_HISTORY if d <= target_date]
    if not valid_dates:
        # Nếu ngày cũ hơn dữ liệu đầu tiên, lấy dữ liệu cũ nhất
        return VAT_HISTORY[sorted(VAT_HISTORY.keys())[0]]
    else:
        # Lấy mốc thời gian gần nhất
        return VAT_HISTORY[sorted(valid_dates)[-1]]

# Biểu giá điện sinh hoạt (EVN)
# Format: "YYYY-MM-DD": [(limit_kwh, price_vnd), ..., (float('inf'), price_vnd)]
PRICE_HISTORY = {
    "2019-03-20": [(50, 1678), (50, 1734), (100, 2014), (100, 2536), (100, 2834), (float('inf'), 2927)],
    "2023-05-04": [(50, 1806), (50, 1866), (100, 2167), (100, 2729), (100, 3050), (float('inf'), 3151)],
    "2024-10-11": [(50, 1893), (50, 1956), (100, 2271), (100, 2860), (100, 3197), (float('inf'), 3302)],
    "2025-05-10": [(50, 1984), (50, 2050), (100, 2380), (100, 2998), (100, 3350), (float('inf'), 3460)]
}

SIGNAL_UPDATE_SENSORS = "electricity_consumption_tracker_update_signal"
