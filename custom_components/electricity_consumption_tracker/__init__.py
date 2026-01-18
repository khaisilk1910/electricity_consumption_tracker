import sqlite3
import datetime
import voluptuous as vol
from datetime import timedelta
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.persistent_notification import async_create
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY

SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): cv.date,
    vol.Required("value"): vol.Coerce(float),
})

async def async_setup_entry(hass, entry):
    db_path = hass.config.path(f"custom_components/{DOMAIN}/tracker_{entry.entry_id}.db")
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
        state = hass.states.get(source_sensor)
        if not state or state.state in ["unknown", "unavailable"]:
            val = 0.0
            async_create(hass, title="Lỗi Sensor", message=f"Sensor `{source_sensor}` lỗi. Ghi nhận là 0.", notification_id=f"error_{entry.entry_id}")
        else:
            try: val = float(state.state)
            except ValueError: val = 0.0

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

    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=interval)))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True
