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

# Import VAT rate
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, CONF_FRIENDLY_NAME, SIGNAL_UPDATE_SENSORS, get_vat_rate

_LOGGER = logging.getLogger(__name__)

SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): vol.Any(cv.date, cv.datetime),
    vol.Required("value"): vol.Coerce(float),
})

# Hàm tính tiền theo bậc thang
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

# Hàm tính toán cốt lõi (Core Calculation)
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
    
    # [LOGIC] Tính VAT dynamic theo tháng đó
    vat_rate = get_vat_rate(y, m, 1) # Lấy VAT ngày đầu tháng
    vat_int = int(vat_rate * 100)
    post_tax_cost = int(monthly_cost * (1 + vat_rate))

    cursor.execute("""
        INSERT OR REPLACE INTO monthly_bill 
        (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien, thanh_tien_sau_thue, vat)
        VALUES (?, ?, ?, 'kWh', ?, 'đ', ?, ?)
    """, (y, m, monthly_sum, monthly_cost, post_tax_cost, vat_int))
    
    # 3. Recalculate Yearly (Cho năm hiện tại)
    cursor.execute("""
        SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) 
        FROM monthly_bill WHERE nam=?
    """, (y,))
    row_year = cursor.fetchone()
    if row_year:
        cursor.execute("""
            INSERT OR REPLACE INTO yearly_bill
            (nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat)
            VALUES (?, ?, ?, ?, ?)
        """, (y, row_year[0] or 0, row_year[1] or 0, row_year[2] or 0, vat_int))

    # 4. Recalculate Total
    recalculate_total_usage(cursor)

# Hàm tách riêng để tính bảng Total (Dùng chung cho update và migration)
def recalculate_total_usage(cursor):
    cursor.execute("SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) FROM monthly_bill")
    row_total = cursor.fetchone()
    total_kwh = row_total[0] or 0.0
    total_money = row_total[1] or 0
    total_money_post_tax = row_total[2] or 0
    
    cursor.execute("SELECT COUNT(*) FROM monthly_bill")
    total_months = cursor.fetchone()[0] or 0
    
    # Tìm ngày Start/End
    start_str = "N/A"
    end_str = "N/A"
    
    cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam ASC, thang ASC, ngay ASC LIMIT 1")
    first = cursor.fetchone()
    if first: start_str = f"{first[2]:02d}/{first[1]:02d}/{first[0]}" # Format DD/MM/YYYY

    cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam DESC, thang DESC, ngay DESC LIMIT 1")
    last = cursor.fetchone()
    if last: end_str = f"{last[2]:02d}/{last[1]:02d}/{last[0]}"

    # Lấy VAT hiện tại (của ngày cuối cùng có dữ liệu)
    current_vat = 8
    if last:
        current_vat = int(get_vat_rate(last[0], last[1], last[2]) * 100)

    cursor.execute("DELETE FROM total_usage")
    cursor.execute("""
        INSERT INTO total_usage 
        (tong_san_luong, don_vi, tong_so_thang, thoi_diem_bat_dau, thoi_diem_ket_thuc, 
         tong_tien_tich_luy, tong_tien_tich_luy_sau_thue, vat) 
        VALUES (?, 'kWh', ?, ?, ?, ?, ?, ?)
    """, (total_kwh, total_months, start_str, end_str, total_money, total_money_post_tax, current_vat))


async def handle_override_global(hass: HomeAssistant, call: ServiceCall):
    entry_id = call.data.get("entry_id")
    if DOMAIN not in hass.data or entry_id not in hass.data[DOMAIN]: return

    db_path = hass.data[DOMAIN][entry_id]["db_path"]
    raw_date = call.data.get("date")
    val = call.data.get("value")
    
    if hasattr(raw_date, "date"): target_date = raw_date
    else:
        target_date = dt_util.parse_datetime(str(raw_date)) or dt_util.parse_date(str(raw_date))
    
    y, m, d = target_date.year, target_date.month, target_date.day
    
    def db_work_override():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        perform_db_calculation(cursor, y, m, d, val)
        conn.commit()
        conn.close()

    await hass.async_add_executor_job(db_work_override)
    async_dispatcher_send(hass, f"{SIGNAL_UPDATE_SENSORS}_{entry_id}")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def override_service_handler(call: ServiceCall):
        await handle_override_global(hass, call)
    hass.services.async_register(DOMAIN, "override_data", override_service_handler, schema=SERVICE_OVERRIDE_SCHEMA)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    storage_dir = hass.config.path("electricity_consumption_tracker")
    if not os.path.exists(storage_dir): os.makedirs(storage_dir, exist_ok=True)

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

    # --- HÀM KHỞI TẠO & MIGRATION ---
    def init_db():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Tạo các bảng nếu chưa có
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                nam INTEGER, thang INTEGER, ngay INTEGER, san_luong REAL, don_vi TEXT, PRIMARY KEY (nam, thang, ngay)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_bill (
                nam INTEGER, thang INTEGER, tong_san_luong REAL, don_vi_san_luong TEXT, 
                thanh_tien REAL, don_vi_tien TEXT, 
                thanh_tien_sau_thue REAL, vat INTEGER,
                PRIMARY KEY (nam, thang)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS yearly_bill (
                nam INTEGER, tong_san_luong REAL, tong_tien REAL, 
                tong_tien_sau_thue REAL, vat INTEGER,
                PRIMARY KEY (nam)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS total_usage (
                tong_san_luong REAL, don_vi TEXT, tong_so_thang INTEGER,
                thoi_diem_bat_dau TEXT, thoi_diem_ket_thuc TEXT,
                tong_tien_tich_luy REAL, tong_tien_tich_luy_sau_thue REAL, vat INTEGER
            )
        """)

        # 2. Migration Columns (Thêm cột cho bảng cũ)
        should_recalculate_history = False
        
        try:
            # Check monthly_bill
            cursor.execute("PRAGMA table_info(monthly_bill)")
            cols_monthly = [info[1] for info in cursor.fetchall()]
            if "thanh_tien_sau_thue" not in cols_monthly:
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN thanh_tien_sau_thue REAL DEFAULT 0")
                should_recalculate_history = True
            if "vat" not in cols_monthly:
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN vat INTEGER DEFAULT 8")

            # Check total_usage
            cursor.execute("PRAGMA table_info(total_usage)")
            cols_total = [info[1] for info in cursor.fetchall()]
            if "tong_tien_tich_luy_sau_thue" not in cols_total:
                cursor.execute("ALTER TABLE total_usage ADD COLUMN tong_tien_tich_luy_sau_thue REAL DEFAULT 0")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN thoi_diem_bat_dau TEXT")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN thoi_diem_ket_thuc TEXT")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN tong_tien_tich_luy REAL DEFAULT 0")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN vat INTEGER DEFAULT 8")

        except Exception as e:
            _LOGGER.error(f"Migration error: {e}")

        # 3. BACKFILL DATA (Quan trọng: Tính lại lịch sử nếu vừa thêm cột mới hoặc bảng yearly trống)
        cursor.execute("SELECT COUNT(*) FROM yearly_bill")
        is_yearly_empty = cursor.fetchone()[0] == 0
        
        if should_recalculate_history or is_yearly_empty:
            _LOGGER.info("Phát hiện update hoặc bảng Yearly trống. Đang tính toán lại toàn bộ lịch sử...")
            
            # A. Lấy tất cả các tháng đang có
            cursor.execute("SELECT nam, thang, thanh_tien FROM monthly_bill")
            all_months = cursor.fetchall()
            
            years_to_update = set()
            
            # B. Loop qua từng tháng để tính lại VAT & Sau thuế
            for row in all_months:
                y_his, m_his, money_his = row[0], row[1], row[2] or 0
                years_to_update.add(y_his)
                
                # Lấy VAT đúng thời điểm đó
                rate = get_vat_rate(y_his, m_his, 1)
                vat_val = int(rate * 100)
                post_tax = int(money_his * (1 + rate))
                
                # Update lại dòng đó
                cursor.execute("""
                    UPDATE monthly_bill 
                    SET thanh_tien_sau_thue = ?, vat = ?
                    WHERE nam = ? AND thang = ?
                """, (post_tax, vat_val, y_his, m_his))
            
            # C. Re-generate bảng Yearly_bill từ monthly_bill đã fix
            cursor.execute("DELETE FROM yearly_bill")
            for y_his in years_to_update:
                cursor.execute("""
                    SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) 
                    FROM monthly_bill WHERE nam=?
                """, (y_his,))
                res = cursor.fetchone()
                # Lấy VAT của tháng 12 hoặc tháng mới nhất làm VAT đại diện cho năm
                cursor.execute("SELECT vat FROM monthly_bill WHERE nam=? ORDER BY thang DESC LIMIT 1", (y_his,))
                vat_res = cursor.fetchone()
                vat_year = vat_res[0] if vat_res else 8
                
                cursor.execute("""
                    INSERT INTO yearly_bill (nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat)
                    VALUES (?, ?, ?, ?, ?)
                """, (y_his, res[0] or 0, res[1] or 0, res[2] or 0, vat_year))
                
            # D. Update Total Usage
            recalculate_total_usage(cursor)
            _LOGGER.info("Đã hoàn tất tính toán lại dữ liệu lịch sử.")

        conn.commit()
        conn.close()

    await hass.async_add_executor_job(init_db)

    # Core Update Logic
    async def update_data(now=None):
        source_entity = entry.options.get(CONF_SOURCE_SENSOR, entry.data.get(CONF_SOURCE_SENSOR))
        state = hass.states.get(source_entity)
        
        if not state or state.state in ["unknown", "unavailable"]: return
        try: current_kwh = float(state.state)
        except ValueError: return

        dt_now = dt_util.now()
        y, m, d = dt_now.year, dt_now.month, dt_now.day

        def db_work_update():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            perform_db_calculation(cursor, y, m, d, current_kwh)
            conn.commit()
            conn.close()

        await hass.async_add_executor_job(db_work_update)
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE_SENSORS}_{entry.entry_id}")

    interval = entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1))
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=interval)))
    entry.async_on_unload(async_track_time_change(hass, update_data, hour=23, minute=59, second=55))

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(update_listener))
    hass.async_create_task(update_data())
    
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
