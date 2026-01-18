import sqlite3
import datetime
import os
import logging
import voluptuous as vol
from datetime import timedelta
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.persistent_notification import async_create
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, CONF_FRIENDLY_NAME

_LOGGER = logging.getLogger(__name__)

# Schema định nghĩa tham số cho Service
SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): cv.date,
    vol.Required("value"): vol.Coerce(float),
})

async def async_setup_entry(hass, entry):
    """Thiết lập tích hợp khi người dùng thêm entry từ UI."""
    db_dir = hass.config.path(f"custom_components/{DOMAIN}")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    db_path = os.path.join(db_dir, f"tracker_{entry.entry_id}.db")
    source_sensor = entry.data[CONF_SOURCE_SENSOR]
    interval = entry.data[CONF_UPDATE_INTERVAL]
    friendly_name = entry.data[CONF_FRIENDLY_NAME]

    def init_db():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS daily_usage (nam INTEGER, thang INTEGER, ngay INTEGER, san_luong REAL, PRIMARY KEY (nam, thang, ngay))")
        cursor.execute("CREATE TABLE IF NOT EXISTS monthly_bill (nam INTEGER, thang INTEGER, tong_san_luong REAL, thanh_tien REAL, PRIMARY KEY (nam, thang))")
        conn.commit()
        conn.close()

    await hass.async_add_executor_job(init_db)

    def calculate_cost(kwh, year, month):
        target_date = f"{year}-{month:02d}-01"
        sorted_dates = sorted([d for d in PRICE_HISTORY if d <= target_date])
        tiers = PRICE_HISTORY[sorted_dates[-1]] if sorted_dates else PRICE_HISTORY[list(PRICE_HISTORY.keys())[0]]
        cost, rem = 0, kwh
        for limit, price in tiers:
            usage = min(rem, limit)
            cost += usage * price
            rem -= usage
            if rem <= 0: break
        return cost

    async def update_data(now=None):
        """Hàm cập nhật dữ liệu định kỳ."""
        state = hass.states.get(source_sensor)
        if not state or state.state in ["unknown", "unavailable", "none"]:
            val = 0.0
            async_create(hass, title="Lỗi Sensor", message=f"Sensor `{source_sensor}` lỗi. Ghi nhận là 0.", notification_id=f"err_{entry.entry_id}")
        else:
            try:
                val = float(state.state)
            except (ValueError, TypeError):
                val = 0.0

        dt = datetime.datetime.now()
        def db_work():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO daily_usage VALUES (?, ?, ?, ?)", (dt.year, dt.month, dt.day, val))
            cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (dt.year, dt.month))
            m_kwh = cursor.fetchone()[0] or 0
            m_cost = calculate_cost(m_kwh, dt.year, dt.month)
            cursor.execute("INSERT OR REPLACE INTO monthly_bill VALUES (?, ?, ?, ?)", (dt.year, dt.month, m_kwh, m_cost))
            conn.commit()
            conn.close()
        await hass.async_add_executor_job(db_work)

    # Đăng ký hàm cập nhật định kỳ
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=interval)))

    # Logic xử lý Service override_data
    async def handle_override(call):
        if call.data.get("entry_id") != entry.entry_id:
            return
        d, v = call.data.get("date"), call.data.get("value")
        def db_override():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO daily_usage VALUES (?, ?, ?, ?)", (d.year, d.month, d.day, v))
            cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (d.year, d.month))
            m_kwh = cursor.fetchone()[0] or 0
            m_cost = calculate_cost(m_kwh, d.year, d.month)
            cursor.execute("INSERT OR REPLACE INTO monthly_bill VALUES (?, ?, ?, ?)", (d.year, d.month, m_kwh, m_cost))
            conn.commit()
            conn.close()
        await hass.async_add_executor_job(db_override)
        _LOGGER.info(f"Dữ liệu đã được ghi đè cho ngày {d} với giá trị {v}")

    # Đăng ký Service vào hệ thống
    hass.services.async_register(DOMAIN, "override_data", handle_override, schema=SERVICE_OVERRIDE_SCHEMA)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass, entry):
    """Hủy nạp tích hợp."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    return unload_ok
