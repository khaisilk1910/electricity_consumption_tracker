import sqlite3
import datetime
import os
import logging
from datetime import timedelta
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.persistent_notification import async_create
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, CONF_FRIENDLY_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    """Thiết lập tích hợp."""
    db_dir = hass.config.path(f"custom_components/{DOMAIN}")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    db_path = os.path.join(db_dir, f"tracker_{entry.entry_id}.db")
    
    # Ưu tiên lấy interval từ Options (nếu người dùng đã thay đổi)
    interval = entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1))

    # Tạo Thiết bị (Device) để hiển thị thông tin sensor và thời gian
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data[CONF_FRIENDLY_NAME],
        model="Electricity Tracker V1",
        manufacturer="Custom Integration",
        sw_version="2026.01.18", # Hiển thị ngày cập nhật bản code này
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
        state = hass.states.get(entry.data[CONF_SOURCE_SENSOR])
        if not state or state.state in ["unknown", "unavailable", "none"]:
            val = 0.0
            async_create(hass, title="Lỗi Sensor", message=f"Sensor nguồn lỗi. Ghi nhận là 0.", notification_id=f"err_{entry.entry_id}")
        else:
            try: val = float(state.state)
            except: val = 0.0

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

    # Lắng nghe sự kiện cập nhật Options
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    # Đăng ký vòng lặp cập nhật
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=interval)))
    
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def update_listener(hass, entry):
    """Tải lại tích hợp khi người dùng nhấn lưu Cấu hình."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
