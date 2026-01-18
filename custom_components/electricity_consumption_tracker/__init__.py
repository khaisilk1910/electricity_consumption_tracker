import sqlite3
import datetime
import os
import voluptuous as vol
from datetime import timedelta
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.persistent_notification import async_create
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, CONF_FRIENDLY_NAME

SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): cv.date,
    vol.Required("value"): vol.Coerce(float),
})

async def async_setup_entry(hass, entry):
    """Thiết lập tích hợp."""
    db_dir = hass.config.path(f"custom_components/{DOMAIN}")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    db_path = os.path.join(db_dir, f"tracker_{entry.entry_id}.db")
    friendly_name = entry.data[CONF_FRIENDLY_NAME]
    
    # Lấy interval từ Options (ưu tiên) hoặc Data
    interval = entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1))

    # Đăng ký Thiết bị (Device) - Sửa lỗi lấy đầy đủ tên thân thiện
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=friendly_name, 
        model="Electricity Tracker V1",
        manufacturer="Custom Integration",
        sw_version="2026.01.18",
    )

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
        source = entry.data[CONF_SOURCE_SENSOR]
        state = hass.states.get(source)
        if not state or state.state in ["unknown", "unavailable", "none"]:
            val = 0.0
            async_create(hass, title="Lỗi Sensor", message=f"Sensor `{source}` không có dữ liệu. Ghi nhận là 0.", notification_id=f"err_{entry.entry_id}")
        else:
            try: val = float(state.state)
            except: val = 0.0

        dt = datetime.datetime.now()
        def db_work():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO daily_usage VALUES (?, ?, ?, ?)", (dt.year, dt.month, dt.day, val))
            cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (dt.year, dt.month))
            m_usage = cursor.fetchone()[0] or 0
            m_cost = calculate_cost(m_usage, dt.year, dt.month)
            cursor.execute("INSERT OR REPLACE INTO monthly_bill VALUES (?, ?, ?, ?)", (dt.year, dt.month, m_usage, m_cost))
            conn.commit()
            conn.close()
        await hass.async_add_executor_job(db_work)
        await hass.config_entries.async_reload(entry.entry_id)

    async def handle_override(call):
        if call.data.get("entry_id") != entry.entry_id: return
        d, v = call.data.get("date"), call.data.get("value")
        def db_override():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO daily_usage VALUES (?, ?, ?, ?)", (d.year, d.month, d.day, v))
            cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (d.year, d.month))
            m_usage = cursor.fetchone()[0] or 0
            m_cost = calculate_cost(m_usage, d.year, d.month)
            cursor.execute("INSERT OR REPLACE INTO monthly_bill VALUES (?, ?, ?, ?)", (d.year, d.month, m_usage, m_cost))
            conn.commit()
            conn.close()
        await hass.async_add_executor_job(db_override)
        await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(DOMAIN, "override_data", handle_override, schema=SERVICE_OVERRIDE_SCHEMA)
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=interval)))
    entry.async_on_unload(entry.add_update_listener(lambda h, e: h.config_entries.async_reload(e.entry_id)))
    
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
