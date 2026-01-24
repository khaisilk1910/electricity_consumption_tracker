"""The Electricity Consumption Tracker integration."""
import sqlite3
import os
import logging
import voluptuous as vol
from datetime import timedelta, date, datetime
import homeassistant.util.dt as dt_util

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.event import async_track_time_interval, async_track_time_change
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, 
    CONF_FRIENDLY_NAME, SIGNAL_UPDATE_SENSORS, get_vat_rate,
    CONF_BILLING_DAY, CONF_START_DATE_APPLY
)

_LOGGER = logging.getLogger(__name__)

SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): vol.Any(cv.date, cv.datetime),
    vol.Required("value"): vol.Coerce(float),
})

# --- HELPER FUNCTIONS ---

def get_billing_period(current_date: date, billing_day: int, apply_date: date):
    """Xác định ngày này thuộc về Hóa Đơn Tháng nào."""
    if current_date < apply_date:
        return current_date.year, current_date.month

    if billing_day == 1:
        return current_date.year, current_date.month
    
    if current_date.day < billing_day:
        return current_date.year, current_date.month
    else:
        next_month = current_date.month + 1
        year = current_date.year
        if next_month > 12:
            next_month = 1
            year += 1
        return year, next_month

def get_accurate_billing_range(year, month, billing_day, apply_date):
    """Dò tìm ngày bắt đầu/kết thúc chính xác của một tháng hóa đơn."""
    anchor_date = date(year, month, 1)
    
    start_date = anchor_date
    end_date = anchor_date

    # Dò ngược
    for i in range(1, 45):
        prev_d = anchor_date - timedelta(days=i)
        p_y, p_m = get_billing_period(prev_d, billing_day, apply_date)
        if p_y == year and p_m == month:
            start_date = prev_d
        else:
            break

    # Dò xuôi
    for i in range(1, 45):
        next_d = anchor_date + timedelta(days=i)
        n_y, n_m = get_billing_period(next_d, billing_day, apply_date)
        if n_y == year and n_m == month:
            end_date = next_d
        else:
            break

    return start_date, end_date

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
        if remaining_kwh <= 0: break
        usage = min(remaining_kwh, limit) if limit != float('inf') else remaining_kwh
        cost += usage * price
        remaining_kwh -= usage
    return round(cost)

def perform_db_calculation(cursor, y, m, d, val, billing_day, apply_date_str):
    apply_date = datetime.strptime(apply_date_str, "%Y-%m-%d").date()
    current_date_obj = date(y, m, d)

    # 1. Insert Daily (Lưu ngày dương lịch)
    cursor.execute("""
        INSERT OR REPLACE INTO daily_usage (nam, thang, ngay, san_luong, don_vi)
        VALUES (?, ?, ?, ?, 'kWh')
    """, (y, m, d, val))
    
    # 2. Xác định Billing Month
    b_year, b_month = get_billing_period(current_date_obj, billing_day, apply_date)
    
    # 3. Tính toán lại Tháng/Năm/Total
    _calculate_single_month(cursor, b_year, b_month, billing_day, apply_date)
    _calculate_single_year(cursor, b_year)
    recalculate_total_usage(cursor)

def _calculate_single_month(cursor, b_year, b_month, billing_day, apply_date):
    start_date, end_date = get_accurate_billing_range(b_year, b_month, billing_day, apply_date)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Tính tổng trong khoảng thời gian thực tế
    cursor.execute(f"""
        SELECT SUM(san_luong) 
        FROM daily_usage 
        WHERE printf('%04d-%02d-%02d', nam, thang, ngay) BETWEEN ? AND ?
    """, (start_str, end_str))
    
    monthly_sum = cursor.fetchone()[0] or 0.0
    monthly_cost = calculate_cost(monthly_sum, b_year, b_month)
    
    vat_rate = get_vat_rate(end_date.year, end_date.month, end_date.day)
    vat_int = int(vat_rate * 100)
    post_tax_cost = int(monthly_cost * (1 + vat_rate))

    # [CHANGE] Lưu thêm ngay_bat_dau, ngay_ket_thuc vào DB
    cursor.execute("""
        INSERT OR REPLACE INTO monthly_bill 
        (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien, 
         thanh_tien_sau_thue, vat, ngay_bat_dau, ngay_ket_thuc)
        VALUES (?, ?, ?, 'kWh', ?, 'đ', ?, ?, ?, ?)
    """, (b_year, b_month, monthly_sum, monthly_cost, post_tax_cost, vat_int, start_str, end_str))

def _calculate_single_year(cursor, year):
    cursor.execute("""
        SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) 
        FROM monthly_bill WHERE nam=?
    """, (year,))
    row_year = cursor.fetchone()
    
    cursor.execute("SELECT vat FROM monthly_bill WHERE nam=? ORDER BY thang DESC LIMIT 1", (year,))
    vat_res = cursor.fetchone()
    vat_year = vat_res[0] if vat_res else 8

    if row_year:
        cursor.execute("""
            INSERT OR REPLACE INTO yearly_bill
            (nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat)
            VALUES (?, ?, ?, ?, ?)
        """, (year, row_year[0] or 0, row_year[1] or 0, row_year[2] or 0, vat_year))

def recalculate_total_usage(cursor):
    cursor.execute("SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) FROM monthly_bill")
    row_total = cursor.fetchone()
    
    total_kwh = row_total[0] or 0.0
    total_money = row_total[1] or 0
    total_money_post_tax = row_total[2] or 0
    
    cursor.execute("SELECT COUNT(*) FROM monthly_bill")
    total_months = cursor.fetchone()[0] or 0
    
    start_str = "N/A"
    end_str = "N/A"
    
    cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam ASC, thang ASC, ngay ASC LIMIT 1")
    first = cursor.fetchone()
    if first and all(x is not None for x in first): 
        start_str = f"{first[2]:02d}/{first[1]:02d}/{first[0]}" 

    cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam DESC, thang DESC, ngay DESC LIMIT 1")
    last = cursor.fetchone()
    current_vat = 8
    if last and all(x is not None for x in last): 
        end_str = f"{last[2]:02d}/{last[1]:02d}/{last[0]}"
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
    entry = hass.config_entries.async_get_entry(entry_id)
    
    billing_day = entry.options.get(CONF_BILLING_DAY, entry.data.get(CONF_BILLING_DAY, 1))
    apply_date_str = entry.options.get(CONF_START_DATE_APPLY, entry.data.get(CONF_START_DATE_APPLY, "2024-01-01"))

    raw_date = call.data.get("date")
    val = call.data.get("value")
    
    if hasattr(raw_date, "date"): target_date = raw_date
    else:
        target_date = dt_util.parse_datetime(str(raw_date)) or dt_util.parse_date(str(raw_date))
    
    y, m, d = target_date.year, target_date.month, target_date.day
    
    def db_work_override():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        perform_db_calculation(cursor, y, m, d, val, billing_day, apply_date_str)
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
        manufacturer="Khaisilk1910",
        model="Electricity DB",
        sw_version="2026.01.30",
    )

    def init_db():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                nam INTEGER, thang INTEGER, ngay INTEGER, san_luong REAL, don_vi TEXT, PRIMARY KEY (nam, thang, ngay)
            )
        """)
        # [CHANGE] Thêm ngay_bat_dau, ngay_ket_thuc
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_bill (
                nam INTEGER, thang INTEGER, tong_san_luong REAL, don_vi_san_luong TEXT, 
                thanh_tien REAL, don_vi_tien TEXT, 
                thanh_tien_sau_thue REAL, vat INTEGER,
                ngay_bat_dau TEXT, ngay_ket_thuc TEXT,
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
        
        # Migration cho monthly_bill
        try:
            cursor.execute("PRAGMA table_info(monthly_bill)")
            cols = [info[1] for info in cursor.fetchall()]
            if "thanh_tien_sau_thue" not in cols:
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN thanh_tien_sau_thue REAL DEFAULT 0")
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN vat INTEGER DEFAULT 8")
            if "ngay_bat_dau" not in cols:
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN ngay_bat_dau TEXT")
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN ngay_ket_thuc TEXT")

            cursor.execute("PRAGMA table_info(total_usage)")
            cols_t = [info[1] for info in cursor.fetchall()]
            if "tong_tien_tich_luy_sau_thue" not in cols_t:
                cursor.execute("ALTER TABLE total_usage ADD COLUMN tong_tien_tich_luy_sau_thue REAL DEFAULT 0")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN thoi_diem_bat_dau TEXT")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN thoi_diem_ket_thuc TEXT")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN tong_tien_tich_luy REAL DEFAULT 0")
                cursor.execute("ALTER TABLE total_usage ADD COLUMN vat INTEGER DEFAULT 8")
        except Exception:
            pass

        conn.commit()
        conn.close()

    await hass.async_add_executor_job(init_db)

    async def update_data(now=None):
        source_entity = entry.options.get(CONF_SOURCE_SENSOR, entry.data.get(CONF_SOURCE_SENSOR))
        billing_day = entry.options.get(CONF_BILLING_DAY, entry.data.get(CONF_BILLING_DAY, 1))
        apply_date_str = entry.options.get(CONF_START_DATE_APPLY, entry.data.get(CONF_START_DATE_APPLY, "2024-01-01"))

        state = hass.states.get(source_entity)
        if not state or state.state in ["unknown", "unavailable"]: return
        try: current_kwh = float(state.state)
        except ValueError: return

        dt_now = dt_util.now()
        y, m, d = dt_now.year, dt_now.month, dt_now.day

        def db_work_update():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            perform_db_calculation(cursor, y, m, d, current_kwh, billing_day, apply_date_str)
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
    """Xử lý khi thay đổi Options."""
    db_path = hass.data[DOMAIN][entry.entry_id]["db_path"]
    billing_day = entry.options.get(CONF_BILLING_DAY, entry.data.get(CONF_BILLING_DAY, 1))
    apply_date_str = entry.options.get(CONF_START_DATE_APPLY, entry.data.get(CONF_START_DATE_APPLY, "2024-01-01"))

    def recalculate_history_process():
        _LOGGER.info(f"Đang tính toán lại TOÀN BỘ lịch sử từ ngày {apply_date_str}...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        apply_date = datetime.strptime(apply_date_str, "%Y-%m-%d").date()
        
        cursor.execute("""
            SELECT nam, thang, ngay FROM daily_usage 
            WHERE printf('%04d-%02d-%02d', nam, thang, ngay) >= ?
            ORDER BY nam, thang, ngay ASC LIMIT 1
        """, (apply_date_str,))
        
        first_impact = cursor.fetchone()
        
        if first_impact:
            start_year_wipe = first_impact[0]
            if first_impact[1] == 1 and billing_day > 1:
                start_year_wipe -= 1
            
            _LOGGER.info(f"Xóa dữ liệu thống kê cũ từ năm {start_year_wipe} để tính lại...")
            cursor.execute("DELETE FROM monthly_bill WHERE nam >= ?", (start_year_wipe,))
            cursor.execute("DELETE FROM yearly_bill WHERE nam >= ?", (start_year_wipe,))
            
            cursor.execute("""
                SELECT nam, thang, ngay, san_luong 
                FROM daily_usage 
                WHERE nam >= ?
                ORDER BY nam, thang, ngay
            """, (start_year_wipe,))
            
            all_data = cursor.fetchall()
            months_to_calc = set()
            
            for r in all_data:
                d_obj = date(r[0], r[1], r[2])
                b_y, b_m = get_billing_period(d_obj, billing_day, apply_date)
                months_to_calc.add((b_y, b_m))
            
            sorted_months = sorted(list(months_to_calc))
            for (b_y, b_m) in sorted_months:
                _calculate_single_month(cursor, b_y, b_m, billing_day, apply_date)
                
            years_to_calc = set([m[0] for m in sorted_months])
            for y_c in years_to_calc:
                _calculate_single_year(cursor, y_c)
            
        recalculate_total_usage(cursor)
        conn.commit()
        conn.close()
        _LOGGER.info("Hoàn tất tính toán lại lịch sử.")
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE_SENSORS}_{entry.entry_id}")

    await hass.async_add_executor_job(recalculate_history_process)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
