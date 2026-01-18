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
    vol.Required("date"): cv.any(cv.date, cv.datetime),
    vol.Required("value"): vol.Coerce(float),
})

async def async_setup_entry(hass, entry):
    db_dir = hass.config.path(f"custom_components/{DOMAIN}")
    if not os.path.exists(db_dir): os.makedirs(db_dir)
    db_path = os.path.join(db_dir, f"tracker_{entry.entry_id}.db")
    
    interval = entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1))

    # Khởi tạo Device Registry
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data[CONF_FRIENDLY_NAME],
        model="Electricity Tracker V1",
        sw_version="2026.01.18",
    )

    def init_db():
        """Tạo cấu trúc 3 bảng giống hệt file .db đính kèm."""
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS daily_usage (nam INTEGER, thang INTEGER, ngay INTEGER, san_luong REAL, don_vi TEXT, PRIMARY KEY (nam, thang, ngay))")
        conn.execute("CREATE TABLE IF NOT EXISTS monthly_bill (nam INTEGER, thang INTEGER, tong_san_luong REAL, don_vi_san_luong TEXT, thanh_tien REAL, don_vi_tien TEXT, PRIMARY KEY (nam, thang))")
        conn.execute("CREATE TABLE IF NOT EXISTS total_usage (tong_san_luong REAL, don_vi TEXT, tong_so_thang INTEGER)")
        conn.commit()
        conn.close()

    await hass.async_add_executor_job(init_db)

    def calculate_cost(kwh, year, month):
        target_date = f"{year}-{month:02d}-01"
        sorted_dates = sorted([d for d in PRICE_HISTORY if d <= target_date])
        tiers = PRICE_HISTORY[sorted_dates[-1]] if sorted_dates else PRICE_HISTORY[list(PRICE_HISTORY.keys())[0]]
        cost, rem = 0, kwh
        for limit, price in tiers:
            usage = min(rem, limit); cost += usage * price; rem -= usage
            if rem <= 0: break
        return cost

    async def update_data(now=None):
        source = entry.data[CONF_SOURCE_SENSOR]
        state = hass.states.get(source)
        val = 0.0
        if not state or state.state in ["unknown", "unavailable"]:
            async_create(hass, title="Lỗi Sensor", message=f"Sensor `{source}` không có dữ liệu.", notification_id=f"err_{entry.entry_id}")
        else:
            try: val = float(state.state)
            except: val = 0.0

        dt = datetime.datetime.now()
        def db_work():
            conn = sqlite3.connect(db_path)
            conn.execute("INSERT OR REPLACE INTO daily_usage VALUES (?, ?, ?, ?, 'kWh')", (dt.year, dt.month, dt.day, val))
            m_usage = conn.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (dt.year, dt.month)).fetchone()[0] or 0
            m_cost = calculate_cost(m_usage, dt.year, dt.month)
            conn.execute("INSERT OR REPLACE INTO monthly_bill VALUES (?, ?, ?, 'kWh', ?, 'đ')", (dt.year, dt.month, m_usage, m_cost))
            t_usage = conn.execute("SELECT SUM(tong_san_luong) FROM monthly_bill").fetchone()[0] or 0
            t_months = conn.execute("SELECT COUNT(*) FROM monthly_bill").fetchone()[0] or 0
            conn.execute("DELETE FROM total_usage")
            conn.execute("INSERT INTO total_usage VALUES (?, 'kWh', ?)", (t_usage, t_months))
            conn.commit(); conn.close()
        
        await hass.async_add_executor_job(db_work)
        await hass.config_entries.async_reload(entry.entry_id)

    async def handle_override(call):
        if call.data.get("entry_id") != entry.entry_id: return
        raw_dt, v = call.data.get("date"), call.data.get("value")
        d = raw_dt.date() if isinstance(raw_dt, datetime.datetime) else raw_dt
        def db_override():
            conn = sqlite3.connect(db_path)
            conn.execute("INSERT OR REPLACE INTO daily_usage VALUES (?, ?, ?, ?, 'kWh')", (d.year, d.month, d.day, v))
            m_usage = conn.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (d.year, d.month)).fetchone()[0] or 0
            m_cost = calculate_cost(m_usage, d.year, d.month)
            conn.execute("INSERT OR REPLACE INTO monthly_bill VALUES (?, ?, ?, 'kWh', ?, 'đ')", (d.year, d.month, m_usage, m_cost))
            conn.commit(); conn.close()
        await hass.async_add_executor_job(db_override)
        await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(DOMAIN, "override_data", handle_override, schema=SERVICE_OVERRIDE_SCHEMA)
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=interval)))
    entry.async_on_unload(entry.add_update_listener(lambda h, e: h.config_entries.async_reload(e.entry_id)))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
