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
from homeassistant.helpers.event import async_track_time_interval, async_track_time_change
from homeassistant.helpers.dispatcher import async_dispatcher_send

# [MODIFIED] Import thêm get_vat_rate
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, CONF_FRIENDLY_NAME, SIGNAL_UPDATE_SENSORS, get_vat_rate

_LOGGER = logging.getLogger(__name__)

SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): vol.Any(cv.date, cv.datetime),
    vol.Required("value"): vol.Coerce(float),
})

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

# [NEW] Hàm tính toán tổng hợp (Dùng chung cho cả update và override)
def perform_db_calculation(cursor, y, m, d, val):
    # 1. Insert Daily
    cursor.execute("""
        INSERT OR REPLACE INTO daily_usage (nam, thang, ngay, san_luong, don_vi)
        VALUES (?, ?, ?, ?, 'kWh')
    """, (y, m, d, val))
    
    # 2. Calculate Monthly
    cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam=? AND thang=?", (y, m))
    monthly_sum = cursor.fetchone()[0] or 0.0
    
    monthly_cost = calculate_cost(monthly_sum, y, m)
    
    # [NEW] Tính VAT và Sau thuế
    vat_rate = get_vat_rate(y, m, 1) # Lấy VAT ngày đầu tháng
    vat_int = int(vat_rate * 100)    # Lưu 8 thay vì 0.08
    post_tax_cost = int(monthly_cost * (1 + vat_rate))

    # [MODIFIED] Insert Monthly (Thêm cột thanh_tien_sau_thue, vat)
    cursor.execute("""
        INSERT OR REPLACE INTO monthly_bill 
        (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien, thanh_tien_sau_thue, vat)
        VALUES (?, ?, ?, 'kWh', ?, 'đ', ?, ?)
    """, (y, m, monthly_sum, monthly_cost, post_tax_cost, vat_int))
    
    # 3. [NEW] Calculate Yearly
    cursor.execute("""
        SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) 
        FROM monthly_bill WHERE nam=?
    """, (y,))
    row_year = cursor.fetchone()
    year_kwh = row_year[0] or 0.0
    year_cost = row_year[1] or 0
    year_cost_post_tax = row_year[2] or 0
    
    cursor.execute("""
        INSERT OR REPLACE INTO yearly_bill
        (nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat)
        VALUES (?, ?, ?, ?, ?)
    """, (y, year_kwh, year_cost, year_cost_post_tax, vat_int))

    # 4. [MODIFIED] Calculate Total Usage (Tất cả thời gian)
    cursor.execute("SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) FROM monthly_bill")
    row_total = cursor.fetchone()
    total_kwh = row_total[0] or 0.0
    total_money = row_total[1] or 0
    total_money_post_tax = row_total[2] or 0
    
    cursor.execute("SELECT COUNT(*) FROM monthly_bill")
    total_months = cursor.fetchone()[0] or 0
    
    # [NEW] Tìm ngày bắt đầu và kết thúc
    start_str = "N/A"
    end_str = "N/A"
    
    # Ngày bắt đầu (MIN)
    cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam ASC, thang ASC, ngay ASC LIMIT 1")
    first_date = cursor.fetchone()
    if first_date:
        start_str = f"{first_date[0]}/{first_date[1]:02d}/{first_date[2]:02d}"

    # Ngày kết thúc (MAX)
    cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam DESC, thang DESC, ngay DESC LIMIT 1")
    last_date = cursor.fetchone()
    if last_date:
        end_str = f"{last_date[0]}/{last_date[1]:02d}/{last_date[2]:02d}"

    # VAT hiện tại để tham khảo trong bảng tổng
    current_vat_rate = get_vat_rate(y, m, d)
    current_vat_int = int(current_vat_rate * 100)

    cursor.execute("DELETE FROM total_usage")
    cursor.execute("""
        INSERT INTO total_usage 
        (tong_san_luong, don_vi, tong_so_thang, thoi_diem_bat_dau, thoi_diem_ket_thuc, 
         tong_tien_tich_luy, tong_tien_tich_luy_sau_thue, vat) 
        VALUES (?, 'kWh', ?, ?, ?, ?, ?, ?)
    """, (total_kwh, total_months, start_str, end_str, total_money, total_money_post_tax, current_vat_int))


async def handle_override_global(hass: HomeAssistant, call: ServiceCall):
    entry_id = call.data.get("entry_id")
    if DOMAIN not in hass.data or entry_id not in hass.data[DOMAIN]:
        _LOGGER.error(f"Entry ID {entry_id} không tìm thấy.")
        return

    db_path = hass.data[DOMAIN][entry_id]["db_path"]
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
        perform_db_calculation(cursor, y, m, d, val)
        conn.commit()
        conn.close()

    await hass.async_add_executor_job(db_work_override)
    _LOGGER.info(f"Overridden data for Entry {entry_id} - {y}-{m}-{d}: {val} kWh")
    async_dispatcher_send(hass, f"{SIGNAL_UPDATE_SENSORS}_{entry_id}")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def override_service_handler(call: ServiceCall):
        await handle_override_global(hass, call)

    hass.services.async_register(
        DOMAIN, "override_data", override_service_handler, schema=SERVICE_OVERRIDE_SCHEMA
    )
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    storage_dir = hass.config.path("electricity_consumption_tracker")
    if not os.path.exists(storage_dir):
        os.makedirs(storage_dir, exist_ok=True)

    db_path = os.path.join(storage_dir, f"electricity_data_{entry.entry_id}.db")
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"db_path": db_path}

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_FRIENDLY_NAME, "Electricity Tracker"),
        manufacturer="Custom Component",
        model="Electricity Tracker DB Based",
        sw_version="2026.01.30",
    )

    def init_db():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Tạo bảng daily_usage (Không đổi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                nam INTEGER, thang INTEGER, ngay INTEGER, san_luong REAL, don_vi TEXT, PRIMARY KEY (nam, thang, ngay)
            )
        """)
        
        # [MODIFIED] Bảng monthly_bill thêm cột
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_bill (
                nam INTEGER, thang INTEGER, tong_san_luong REAL, don_vi_san_luong TEXT, 
                thanh_tien REAL, don_vi_tien TEXT, 
                thanh_tien_sau_thue REAL, vat INTEGER,
                PRIMARY KEY (nam, thang)
            )
        """)
        
        # [NEW] Bảng yearly_bill
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS yearly_bill (
                nam INTEGER, tong_san_luong REAL, tong_tien REAL, 
                tong_tien_sau_thue REAL, vat INTEGER,
                PRIMARY KEY (nam)
            )
        """)
        
        # [MODIFIED] Bảng total_usage thêm cột
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS total_usage (
                tong_san_luong REAL, don_vi TEXT, tong_so_thang INTEGER,
                thoi_diem_bat_dau TEXT, thoi_diem_ket_thuc TEXT,
                tong_tien_tich_luy REAL, tong_tien_tich_luy_sau_thue REAL, vat INTEGER
            )
        """)

        # --- MIGRATION LOGIC (Tự động thêm cột cho DB cũ) ---
        try:
            # Check monthly_bill columns
            cursor.execute("PRAGMA table_info(monthly_bill)")
            columns = [info[1] for info in cursor.fetchall()]
            if "thanh_tien_sau_thue" not in columns:
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN thanh_tien_sau_thue REAL DEFAULT 0")
            if "vat" not in columns:
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN vat INTEGER DEFAULT 8")
            
            # Check total_usage columns
            cursor.execute("PRAGMA table_info(total_usage)")
            columns = [info[1] for info in cursor.fetchall()]
            if "thoi_diem_bat_dau" not in columns:
                cursor.execute("ALTER TABLE total_usage ADD COLUMN thoi_diem_bat_dau TEXT")
            if "thoi_diem_ket_thuc" not in columns:
                cursor.execute("ALTER TABLE total_usage ADD COLUMN thoi_diem_ket_thuc TEXT")
            if "tong_tien_tich_luy" not in columns:
                cursor.execute("ALTER TABLE total_usage ADD COLUMN tong_tien_tich_luy REAL DEFAULT 0")
            if "tong_tien_tich_luy_sau_thue" not in columns:
                cursor.execute("ALTER TABLE total_usage ADD COLUMN tong_tien_tich_luy_sau_thue REAL DEFAULT 0")
            if "vat" not in columns:
                cursor.execute("ALTER TABLE total_usage ADD COLUMN vat INTEGER DEFAULT 8")
                
        except Exception as e:
            _LOGGER.warning(f"Lỗi khi kiểm tra migration DB: {e}")
        # ----------------------------------------------------

        conn.commit()
        conn.close()

    await hass.async_add_executor_job(init_db)

    async def update_data(now=None):
        source_entity = entry.options.get(CONF_SOURCE_SENSOR, entry.data.get(CONF_SOURCE_SENSOR))
        state = hass.states.get(source_entity)
        
        current_kwh = 0.0
        if not state or state.state in ["unknown", "unavailable"]:
            return
        try:
            current_kwh = float(state.state)
        except ValueError:
            return

        dt_now = dt_util.now()
        year, month, day = dt_now.year, dt_now.month, dt_now.day

        def db_work_update():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            perform_db_calculation(cursor, year, month, day, current_kwh)
            conn.commit()
            conn.close()

        await hass.async_add_executor_job(db_work_update)
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE_SENSORS}_{entry.entry_id}")

    update_interval_hours = entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1))
    
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=update_interval_hours)))
    entry.async_on_unload(async_track_time_change(hass, update_data, hour=23, minute=59, second=55))

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(update_listener))
    hass.async_create_task(update_data())
    
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
