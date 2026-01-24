"""The Electricity Consumption Tracker integration."""
import sqlite3
import os
import logging
import voluptuous as vol
from datetime import timedelta, date, datetime # [FIX] Đã thêm datetime
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
    """Xác định Tháng Hóa Đơn."""
    # Nếu ngày hiện tại < ngày áp dụng -> Dùng Calendar Month
    if current_date < apply_date:
        return current_date.year, current_date.month

    if billing_day == 1:
        return current_date.year, current_date.month
    
    # Nếu ngày hiện tại < ngày chốt -> Thuộc kỳ tháng hiện tại (nhưng logic EVN thường gọi là kỳ tháng T)
    # EVN: Chốt ngày 10/2 -> Kỳ tháng 2. (Từ 11/1 đến 10/2)
    # Logic code: Ngày < 10 -> Thuộc tháng hiện tại. Ngày >= 10 -> Thuộc tháng sau.
    # SỬA LẠI LOGIC CHUẨN EVN:
    # Kỳ 10/01 - 09/02: Được gọi là Hóa đơn Tháng 2.
    
    if current_date.day < billing_day:
        # Ví dụ: Ngày 5/2 (Chốt ngày 10). Thuộc kỳ (10/1 - 9/2) -> Tháng 2.
        return current_date.year, current_date.month
    else:
        # Ví dụ: Ngày 15/2 (Chốt ngày 10). Thuộc kỳ (10/2 - 9/3) -> Tháng 3.
        next_month = current_date.month + 1
        year = current_date.year
        if next_month > 12:
            next_month = 1
            year += 1
        return year, next_month

def get_billing_cycle_range(billing_year, billing_month, billing_day, apply_date):
    """Lấy ngày Start/End của một Billing Month."""
    # Kiểm tra xem tháng này có nằm trong vùng áp dụng không (dựa vào ngày đầu tháng)
    check_date = date(billing_year, billing_month, 1)
    
    if billing_day == 1 or check_date < apply_date:
        # Calendar Month
        start_date = date(billing_year, billing_month, 1)
        # Tìm ngày cuối tháng an toàn
        next_m = billing_month + 1
        next_y = billing_year
        if next_m > 12:
            next_m = 1
            next_y += 1
        end_date = date(next_y, next_m, 1) - timedelta(days=1)
        return start_date, end_date
    else:
        # Billing Cycle (Ví dụ Tháng 2, chốt ngày 10 -> Kỳ: 10/1 đến 09/2)
        
        # End Date: Ngày (billing_day - 1) của billing_month
        try:
            end_date = date(billing_year, billing_month, billing_day) - timedelta(days=1)
        except ValueError:
             # Fallback: Ngày cuối cùng của tháng nếu ngày chốt không tồn tại (vd 30/2)
             end_date = date(billing_year, billing_month, 28) # Tạm tính 28 cho an toàn

        # Start Date: Ngày (billing_day) của tháng trước
        prev_m = billing_month - 1
        prev_y = billing_year
        if prev_m < 1:
            prev_m = 12
            prev_y -= 1
        
        try:
            start_date = date(prev_y, prev_m, billing_day)
        except ValueError:
             # Fallback cho tháng trước nếu không có ngày đó
             start_date = date(prev_y, prev_m, 28)

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

    # 1. Insert Daily (Luôn lưu theo lịch dương thực tế)
    cursor.execute("""
        INSERT OR REPLACE INTO daily_usage (nam, thang, ngay, san_luong, don_vi)
        VALUES (?, ?, ?, ?, 'kWh')
    """, (y, m, d, val))
    
    # 2. Xác định Billing Month
    b_year, b_month = get_billing_period(current_date_obj, billing_day, apply_date)
    
    # 3. Lấy khoảng ngày query
    start_date, end_date = get_billing_cycle_range(b_year, b_month, billing_day, apply_date)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # 4. Tính tổng tháng
    cursor.execute(f"""
        SELECT SUM(san_luong) 
        FROM daily_usage 
        WHERE printf('%04d-%02d-%02d', nam, thang, ngay) BETWEEN ? AND ?
    """, (start_str, end_str))
    
    monthly_sum = cursor.fetchone()[0] or 0.0
    monthly_cost = calculate_cost(monthly_sum, b_year, b_month)
    
    vat_rate = get_vat_rate(b_year, b_month, 1)
    vat_int = int(vat_rate * 100)
    post_tax_cost = int(monthly_cost * (1 + vat_rate))

    cursor.execute("""
        INSERT OR REPLACE INTO monthly_bill 
        (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien, thanh_tien_sau_thue, vat)
        VALUES (?, ?, ?, 'kWh', ?, 'đ', ?, ?)
    """, (b_year, b_month, monthly_sum, monthly_cost, post_tax_cost, vat_int))
    
    # 5. Tính tổng năm (Dựa trên monthly_bill đã tính)
    cursor.execute("""
        SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) 
        FROM monthly_bill WHERE nam=?
    """, (b_year,))
    row_year = cursor.fetchone()
    if row_year:
        cursor.execute("""
            INSERT OR REPLACE INTO yearly_bill
            (nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat)
            VALUES (?, ?, ?, ?, ?)
        """, (b_year, row_year[0] or 0, row_year[1] or 0, row_year[2] or 0, vat_int))

    recalculate_total_usage(cursor)

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
    if first: start_str = f"{first[2]:02d}/{first[1]:02d}/{first[0]}" 

    cursor.execute("SELECT nam, thang, ngay FROM daily_usage ORDER BY nam DESC, thang DESC, ngay DESC LIMIT 1")
    last = cursor.fetchone()
    if last: end_str = f"{last[2]:02d}/{last[1]:02d}/{last[0]}"
    
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

    # Device Registry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_FRIENDLY_NAME, "Electricity Tracker"),
        manufacturer="Khaisilk1910",
        model="Electricity DB",
        sw_version="2026.01.30",
    )

    # --- INIT DB ---
    def init_db():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
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
        
        # Check Columns
        try:
            cursor.execute("PRAGMA table_info(monthly_bill)")
            cols = [info[1] for info in cursor.fetchall()]
            if "thanh_tien_sau_thue" not in cols:
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN thanh_tien_sau_thue REAL DEFAULT 0")
                cursor.execute("ALTER TABLE monthly_bill ADD COLUMN vat INTEGER DEFAULT 8")
            
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

    # --- UPDATE LOGIC ---
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
        _LOGGER.info(f"Đang tính toán lại lịch sử từ ngày {apply_date_str}...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        apply_date = datetime.strptime(apply_date_str, "%Y-%m-%d").date()
        
        # [FIX] XÓA DỮ LIỆU CŨ TRONG KHOẢNG THỜI GIAN ẢNH HƯỞNG ĐỂ TRÁNH TRÙNG LẶP/RÁC
        # Lấy năm/tháng của ngày áp dụng để xóa từ đó về sau
        start_year, start_month = get_billing_period(apply_date, billing_day, apply_date)
        
        # Xóa monthly_bill từ mốc này trở đi (để tính lại sạch sẽ)
        # Note: Logic xóa này đơn giản hóa bằng cách xóa >= năm hiện tại hoặc duyệt từng tháng.
        # Để an toàn nhất: Ta duyệt qua từng ngày trong DB >= apply_date để xác định tháng nào cần tính lại.
        
        cursor.execute("""
            SELECT nam, thang, ngay 
            FROM daily_usage 
            WHERE printf('%04d-%02d-%02d', nam, thang, ngay) >= ?
            ORDER BY nam, thang, ngay
        """, (apply_date_str,))
        
        rows = cursor.fetchall()
        affected_months = set()
        
        for r in rows:
            d_obj = date(r[0], r[1], r[2])
            b_y, b_m = get_billing_period(d_obj, billing_day, apply_date)
            affected_months.add((b_y, b_m))
            
        # Tính lại từng tháng bị ảnh hưởng
        for (b_y, b_m) in affected_months:
            start_date, end_date = get_billing_cycle_range(b_y, b_m, billing_day, apply_date)
            start_s = start_date.strftime("%Y-%m-%d")
            end_s = end_date.strftime("%Y-%m-%d")
            
            # Tính tổng
            cursor.execute(f"""
                SELECT SUM(san_luong) FROM daily_usage 
                WHERE printf('%04d-%02d-%02d', nam, thang, ngay) BETWEEN ? AND ?
            """, (start_s, end_s))
            
            monthly_sum = cursor.fetchone()[0] or 0.0
            monthly_cost = calculate_cost(monthly_sum, b_y, b_m)
            
            vat_rate = get_vat_rate(b_y, b_m, 1)
            vat_int = int(vat_rate * 100)
            post_tax = int(monthly_cost * (1 + vat_rate))
            
            # Update
            cursor.execute("""
                INSERT OR REPLACE INTO monthly_bill 
                (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien, thanh_tien_sau_thue, vat)
                VALUES (?, ?, ?, 'kWh', ?, 'đ', ?, ?)
            """, (b_y, b_m, monthly_sum, monthly_cost, post_tax, vat_int))

        # Tính lại Yearly (chỉ những năm bị ảnh hưởng)
        affected_years = set([x[0] for x in affected_months])
        for y_param in affected_years:
            cursor.execute("""
                SELECT SUM(tong_san_luong), SUM(thanh_tien), SUM(thanh_tien_sau_thue) 
                FROM monthly_bill WHERE nam=?
            """, (y_param,))
            res = cursor.fetchone()
            
            cursor.execute("SELECT vat FROM monthly_bill WHERE nam=? ORDER BY thang DESC LIMIT 1", (y_param,))
            vat_res = cursor.fetchone()
            vat_year = vat_res[0] if vat_res else 8
            
            cursor.execute("""
                INSERT OR REPLACE INTO yearly_bill (nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat)
                VALUES (?, ?, ?, ?, ?)
            """, (y_param, res[0] or 0, res[1] or 0, res[2] or 0, vat_year))
            
        recalculate_total_usage(cursor)
        conn.commit()
        conn.close()
        _LOGGER.info("Hoàn tất tính toán lại lịch sử.")

    await hass.async_add_executor_job(recalculate_history_process)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
