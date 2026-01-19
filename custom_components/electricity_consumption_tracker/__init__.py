"""The Electricity Consumption Tracker integration."""
import sqlite3
import os
import logging
import voluptuous as vol
from datetime import timedelta
import homeassistant.util.dt as dt_util

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send # [NEW] Import dispatcher

from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, CONF_FRIENDLY_NAME, SIGNAL_UPDATE_SENSORS

_LOGGER = logging.getLogger(__name__)

SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): vol.Any(cv.date, cv.datetime),
    vol.Required("value"): vol.Coerce(float),
})

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Electricity Consumption Tracker from a config entry."""
    
    # 1. Định nghĩa thư mục chứa DB: /config/electricity_consumption_tracker/
    storage_dir = hass.config.path("electricity_consumption_tracker")
    
    # 2. Tạo thư mục nếu chưa tồn tại
    if not os.path.exists(storage_dir):
        try:
            os.makedirs(storage_dir)
        except OSError as e:
            _LOGGER.error(f"Không thể tạo thư mục lưu trữ {storage_dir}: {e}")
            return False

    # 3. Định nghĩa đường dẫn file DB bên trong thư mục đó
    db_path = os.path.join(storage_dir, f"electricity_data_{entry.entry_id}.db")
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "db_path": db_path
    }

    # Register Device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_FRIENDLY_NAME, "Electricity Tracker"),
        manufacturer="Custom Component",
        model="Electricity Tracker DB Based",
        sw_version="2026.01.19",
    )

    # Initialize Database
    def init_db():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                nam INTEGER,
                thang INTEGER,
                ngay INTEGER,
                san_luong REAL,
                don_vi TEXT,
                PRIMARY KEY (nam, thang, ngay)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_bill (
                nam INTEGER,
                thang INTEGER,
                tong_san_luong REAL,
                don_vi_san_luong TEXT,
                thanh_tien REAL,
                don_vi_tien TEXT,
                PRIMARY KEY (nam, thang)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS total_usage (
                tong_san_luong REAL,
                don_vi TEXT,
                tong_so_thang INTEGER
            )
        """)
        conn.commit()
        conn.close()

    await hass.async_add_executor_job(init_db)

    # Helper Function: Calculate EVN Cost
    def calculate_cost(kwh, year, month):
        target_date = f"{year}-{month:02d}-01"
        valid_dates = [d for d in PRICE_HISTORY if d <= target_date]
        if not valid_dates:
            tiers = PRICE_HISTORY[sorted(PRICE_HISTORY.keys())[0]]
        else:
            tiers = PRICE_HISTORY[sorted(valid_dates)[-1]]
            
        cost = 0
        remaining_kwh = kwh
        
        for limit, price in tiers:
            if remaining_kwh <= 0:
                break
            usage = min(remaining_kwh, limit) if limit != float('inf') else remaining_kwh
            cost += usage * price
            remaining_kwh -= usage
            
        return round(cost)

    # Core Update Logic
    async def update_data(now=None):
        source_entity = entry.data[CONF_SOURCE_SENSOR]
        state = hass.states.get(source_entity)
        
        current_kwh = 0.0
        if not state or state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"Sensor {source_entity} unavailable")
            return
        else:
            try:
                current_kwh = float(state.state)
            except ValueError:
                return

        dt_now = dt_util.now()
        year, month, day = dt_now.year, dt_now.month, dt_now.day

        def db_work_update():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO daily_usage (nam, thang, ngay, san_luong, don_vi)
                VALUES (?, ?, ?, ?, 'kWh')
            """, (year, month, day, current_kwh))
            
            cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (year, month))
            monthly_sum = cursor.fetchone()[0] or 0.0
            
            monthly_cost = calculate_cost(monthly_sum, year, month)
            
            cursor.execute("""
                INSERT OR REPLACE INTO monthly_bill (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien)
                VALUES (?, ?, ?, 'kWh', ?, 'đ')
            """, (year, month, monthly_sum, monthly_cost))
            
            cursor.execute("SELECT SUM(tong_san_luong) FROM monthly_bill")
            total_kwh = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT COUNT(*) FROM monthly_bill")
            total_months = cursor.fetchone()[0] or 0
            
            cursor.execute("DELETE FROM total_usage")
            cursor.execute("INSERT INTO total_usage (tong_san_luong, don_vi, tong_so_thang) VALUES (?, 'kWh', ?)", (total_kwh, total_months))
            
            conn.commit()
            conn.close()

        await hass.async_add_executor_job(db_work_update)

    # Service: Override Data
    async def handle_override(call: ServiceCall):
        if call.data.get("entry_id") != entry.entry_id:
            return
            
        raw_date = call.data.get("date")
        val = call.data.get("value")
        
        if hasattr(raw_date, "date"):
            target_date = raw_date
        else:
            target_date = dt_util.parse_datetime(str(raw_date))
            if target_date is None:
                target_date = dt_util.parse_date(str(raw_date))
        
        y, m, d = target_date.year, target_date.month, target_date.day
        
        def db_work_override():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO daily_usage (nam, thang, ngay, san_luong, don_vi)
                VALUES (?, ?, ?, ?, 'kWh')
            """, (y, m, d, val))
            
            cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (y, m))
            monthly_sum = cursor.fetchone()[0] or 0.0
            monthly_cost = calculate_cost(monthly_sum, y, m)
            
            cursor.execute("""
                INSERT OR REPLACE INTO monthly_bill (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien)
                VALUES (?, ?, ?, 'kWh', ?, 'đ')
            """, (y, m, monthly_sum, monthly_cost))
            
            cursor.execute("SELECT SUM(tong_san_luong) FROM monthly_bill")
            total_kwh = cursor.fetchone()[0] or 0.0
            cursor.execute("SELECT COUNT(*) FROM monthly_bill")
            total_months = cursor.fetchone()[0] or 0
            
            cursor.execute("DELETE FROM total_usage")
            cursor.execute("INSERT INTO total_usage VALUES (?, 'kWh', ?)", (total_kwh, total_months))
            
            conn.commit()
            conn.close()

        await hass.async_add_executor_job(db_work_override)
        _LOGGER.info(f"Overridden data for {y}-{m}-{d}: {val} kWh")
        
        # [NEW] Gửi tín hiệu cập nhật cho các sensor
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE_SENSORS}_{entry.entry_id}")

    hass.services.async_register(DOMAIN, "override_data", handle_override, schema=SERVICE_OVERRIDE_SCHEMA)

    update_interval_hours = entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1))
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=update_interval_hours)))
    
    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
