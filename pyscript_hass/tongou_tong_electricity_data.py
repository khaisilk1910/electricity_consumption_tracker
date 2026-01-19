import sqlite3
import os
from datetime import datetime

# ==============================================================================
# 1. CẤU HÌNH NGƯỜI DÙNG
# ==============================================================================

# Đường dẫn Database
DB_PATH = "/config/pyscript/tongou_tong_electricity_data.db"

# --- CẤU HÌNH ID SENSOR ---
SENSOR_ALL_TIME      = "sensor.tongou_electricity_total_all_time"
SENSOR_YEAR_PREFIX   = "sensor.tongou_electricity_bill_" # Sensor các năm sẽ có dạng: sensor.tongou_electricity_bill_2025

# --- CẤU HÌNH TÊN HIỂN THỊ ---
NAME_ALL_TIME      = "Tổng điện năng tiêu thụ (Tất cả)"
NAME_DYNAMIC_YEAR  = "Dữ liệu điện Năm {year}"

# --- CẤU HÌNH LỊCH SỬ GIÁ ĐIỆN (QUAN TRỌNG) ---
# Định dạng: "YYYY-MM-DD": [(Kwh_limit, Giá_VND), ...]
# Hệ thống sẽ so sánh ngày của dữ liệu để chọn bảng giá phù hợp nhất.
PRICE_HISTORY = {
    # Giá áp dụng từ 20/03/2019
    "2019-03-20": [
        (50, 1678),
        (50, 1734),
        (100, 2014),
        (100, 2536),
        (100, 2834),
        (float('inf'), 2927)
    ],
    # Giá áp dụng từ 04/05/2023
    "2023-05-04": [
        (50, 1728),
        (50, 1786),
        (100, 2074),
        (100, 2612),
        (100, 2919),
        (float('inf'), 3015)
    ],
    # Giá áp dụng từ 09/11/2023
    "2023-05-04": [
        (50, 1806),
        (50, 1866),
        (100, 2167),
        (100, 2729),
        (100, 3050),
        (float('inf'), 3151)
    ],
    # Giá áp dụng từ 11/10/2024
    "2024-10-11": [
        (50, 1893),
        (50, 1956),
        (100, 2271),
        (100, 2860),
        (100, 3197),
        (float('inf'), 3302)
    ],
    # Biểu giá bán lẻ điện (theo Quyết định số 1279/QĐ-BCT ngày 09/5/2025 của Bộ Công Thương)
    "2025-05-10": [
        (50, 1984),
        (50, 2050),
        (100, 2380),
        (100, 2998),
        (100, 3350),
        (float('inf'), 3460)
    ]
    # Khi có giá mới, bạn chỉ cần thêm dòng mới vào đây
}

# ==============================================================================
# 2. HÀM XỬ LÝ LOGIC
# ==============================================================================

def get_tiers_for_date(year, month):
    """
    Tìm bảng giá phù hợp cho tháng/năm cụ thể.
    """
    # Lấy ngày mùng 1 của tháng để so sánh
    target_date_str = f"{year}-{month:02d}-01"
    
    selected_tiers = None
    sorted_dates = sorted(PRICE_HISTORY.keys()) # Sắp xếp ngày tăng dần
    
    # Duyệt qua lịch sử để tìm mốc giá gần nhất (<= ngày hiện tại)
    for start_date in sorted_dates:
        if start_date <= target_date_str:
            selected_tiers = PRICE_HISTORY[start_date]
        else:
            break
            
    # Fallback: Nếu dữ liệu cũ hơn cả mốc đầu tiên, lấy mốc đầu tiên
    if selected_tiers is None:
        selected_tiers = PRICE_HISTORY[sorted_dates[0]]
        
    return selected_tiers

def calculate_tier_cost(total_kwh, year, month):
    """
    Tính tiền điện dựa trên tổng số kWh và thời gian (để áp dụng đúng giá)
    """
    if total_kwh is None: total_kwh = 0
    
    # Lấy bảng giá đúng thời điểm
    tiers = get_tiers_for_date(year, month)
    
    remaining_kwh = total_kwh
    total_cost = 0
    
    for limit, price in tiers:
        if remaining_kwh <= 0:
            break
        usage_in_tier = min(remaining_kwh, limit)
        total_cost += usage_in_tier * price
        remaining_kwh -= usage_in_tier
        
    return total_cost

def update_sensors_from_db(year, month, day=None):
    """
    Đọc DB và cập nhật trạng thái Sensor Home Assistant
    """
    conn = None
    try:
        year = int(year)
        month = int(month)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # ----------------------------------------------------------------------
        # 2. SENSOR TỔNG TẤT CẢ (ALL TIME)
        # ----------------------------------------------------------------------
        try:
            cursor.execute("SELECT SUM(tong_san_luong), COUNT(*) FROM monthly_bill")
            total_res = cursor.fetchone()
            grand_total_kwh = total_res[0] if total_res and total_res[0] else 0
            total_months_count = total_res[1] if total_res and total_res[1] else 0

            cursor.execute("""
                SELECT nam, SUM(tong_san_luong), SUM(thanh_tien) 
                FROM monthly_bill 
                GROUP BY nam 
                ORDER BY nam DESC
            """)
            yearly_stats = cursor.fetchall()
            
            details_by_year = {}
            grand_total_cost = 0
            
            for row in yearly_stats:
                y_nam = row[0]
                y_kwh = row[1] if row[1] else 0
                y_cost = row[2] if row[2] else 0
                grand_total_cost += y_cost
                
                details_by_year[f"Nam_{y_nam}"] = {
                    "tong_san_luong_kwh": round(y_kwh, 2),
                    "tong_tien_vnd": round(y_cost, 2)
                }

            state.set(
                SENSOR_ALL_TIME,
                value=round(grand_total_kwh, 2), # kWh vẫn giữ 2 số thập phân
                new_attributes={
                    "friendly_name": NAME_ALL_TIME,
                    "unit_of_measurement": "kWh",
                    "device_class": "energy",
                    "state_class": "total_increasing",
                    "tong_so_thang_du_lieu": total_months_count,
                    "tong_tien_tich_luy": round(grand_total_cost, 2),
                    "chi_tiet_tung_nam": details_by_year
                }
            )
        except Exception as e2:
             log.error(f"TONGOU: Lỗi Sensor All Time: {e2}")

        # ----------------------------------------------------------------------
        # 3. TỰ ĐỘNG TẠO SENSOR CHO TẤT CẢ CÁC NĂM (DYNAMIC YEAR)
        # ----------------------------------------------------------------------
        try:
            cursor.execute("SELECT DISTINCT nam FROM monthly_bill ORDER BY nam DESC")
            all_years = cursor.fetchall() 

            for y_row in all_years:
                target_year = y_row[0]
                cursor.execute("SELECT thang, tong_san_luong, thanh_tien FROM monthly_bill WHERE nam = ? ORDER BY thang ASC", (target_year,))
                rows = cursor.fetchall()
                
                year_cost = sum([(r[2] or 0) for r in rows])
                year_kwh = sum([(r[1] or 0) for r in rows])
                
                year_details = {}
                for r in rows:
                    year_details[f"Thang_{r[0]}"] = {
                        "san_luong_kwh": round(r[1] or 0, 2),
                        "thanh_tien_vnd": round(r[2] or 0, 2)
                    }
                
                # UPDATE: Dùng int() để bỏ số thập phân cho state tiền
                state.set(
                    f"{SENSOR_YEAR_PREFIX}{target_year}",
                    value=int(year_cost), 
                    new_attributes={
                        "friendly_name": NAME_DYNAMIC_YEAR.format(year=target_year),
                        "unit_of_measurement": "đ",
                        "device_class": "monetary",
                        "tong_san_luong_nam": round(year_kwh, 2),
                        "chi_tiet_cac_thang": year_details,
                        "data_source": "Auto Generated"
                    }
                )
        except Exception as e5:
            log.error(f"TONGOU: Lỗi Dynamic Year Sensors: {e5}")

        # ----------------------------------------------------------------------
        # 4. TỰ ĐỘNG TẠO SENSOR CHI TIẾT TỪNG THÁNG (NĂM NAY & NĂM TRƯỚC)
        # ----------------------------------------------------------------------
        try:
            # Chỉ lấy năm hiện tại và năm trước đó
            target_monthly_years = [year, year - 1] 

            for t_year in target_monthly_years:
                # Lấy danh sách các tháng có dữ liệu trong năm t_year
                cursor.execute("SELECT thang, tong_san_luong, thanh_tien FROM monthly_bill WHERE nam = ? ORDER BY thang ASC", (t_year,))
                months_in_year = cursor.fetchall()

                for m_row in months_in_year:
                    t_month = m_row[0]
                    t_kwh = m_row[1] if m_row[1] is not None else 0
                    t_cost = m_row[2] if m_row[2] is not None else 0

                    # Truy vấn chi tiết ngày
                    cursor.execute("SELECT ngay, san_luong FROM daily_usage WHERE nam = ? AND thang = ? ORDER BY ngay ASC", (t_year, t_month))
                    daily_rows_sub = cursor.fetchall()
                    
                    daily_details_sub = {}
                    for r_sub in daily_rows_sub:
                        val_sub = r_sub[1] if r_sub[1] is not None else 0
                        daily_details_sub[f"Ngay_{r_sub[0]}"] = round(val_sub, 2)
                    
                    sensor_id_monthly = f"{SENSOR_YEAR_PREFIX}{t_year}_{t_month:02d}"
                    
                    # UPDATE: Dùng int() để bỏ số thập phân cho state tiền
                    state.set(
                        sensor_id_monthly,
                        value=int(t_cost),
                        new_attributes={
                            "friendly_name": f"Tiền điện Tháng {t_month}/{t_year}",
                            "unit_of_measurement": "đ",
                            "device_class": "monetary",
                            "tong_san_luong_kwh": round(t_kwh, 2),
                            "chi_tiet_ngay": daily_details_sub,
                            "last_updated": f"{day}/{month}/{year}" if day else "Auto Update",
                            "data_source": "Monthly Detail Auto Gen"
                        }
                    )
        except Exception as e6:
            log.error(f"TONGOU: Lỗi Monthly Detail Sensors: {e6}")

    except Exception as e:
        log.error(f"TONGOU: Lỗi CHÍNH trong update_sensors_from_db: {e}")
    finally:
        if conn: conn.close()

# ==============================================================================
# 3. SERVICE VÀ TRIGGER
# ==============================================================================

@service
def tongou_tong_daily_save_log(year=None, month=None, day=None, sanluong=None):
    """
    Service dùng để lưu dữ liệu hàng ngày.
    """
    if year is None or month is None or day is None or sanluong is None:
        log.warning("TONGOU: Thiếu dữ liệu đầu vào (year, month, day, sanluong)")
        return

    conn = None
    try:
        year, month, day = int(year), int(month), int(day)
        sanluong = float(sanluong)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. Lưu daily_usage
        cursor.execute("""
            INSERT OR REPLACE INTO daily_usage (nam, thang, ngay, san_luong, don_vi)
            VALUES (?, ?, ?, ?, 'kWh')
        """, (year, month, day, sanluong))

        # 2. Tính monthly_bill
        cursor.execute("SELECT SUM(san_luong) FROM daily_usage WHERE nam = ? AND thang = ?", (year, month))
        res = cursor.fetchone()
        monthly_total_kwh = res[0] if res and res[0] is not None else 0
        
        # --- CẬP NHẬT: Tính tiền theo giá lịch sử ---
        monthly_cost = calculate_tier_cost(monthly_total_kwh, year, month)

        cursor.execute("""
            INSERT OR REPLACE INTO monthly_bill (nam, thang, tong_san_luong, don_vi_san_luong, thanh_tien, don_vi_tien)
            VALUES (?, ?, ?, 'kWh', ?, 'đ')
        """, (year, month, monthly_total_kwh, monthly_cost))

        # 3. Lưu total_usage
        cursor.execute("SELECT SUM(tong_san_luong), COUNT(*) FROM monthly_bill")
        total_res = cursor.fetchone()
        grand_total_kwh = total_res[0] if total_res and total_res[0] is not None else 0
        total_months_count = total_res[1] if total_res and total_res[1] is not None else 0

        cursor.execute("DELETE FROM total_usage")
        cursor.execute("INSERT INTO total_usage (tong_san_luong, don_vi, tong_so_thang) VALUES (?, 'kWh', ?)", 
                       (grand_total_kwh, total_months_count))

        conn.commit()
        conn.close()
        conn = None # Reset flag

        # 4. Gọi cập nhật sensor
        update_sensors_from_db(year, month, day)

    except Exception as e:
        log.error(f"TONGOU: Lỗi khi lưu log hàng ngày: {e}")
        if conn: conn.close()

@service
def tongou_recalculate_history():
    """
    Service MỚI: Chạy 1 lần để tính toán lại toàn bộ lịch sử tiền điện.
    """
    log.info("TONGOU: Bắt đầu tính toán lại toàn bộ lịch sử tiền điện...")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT nam, thang, tong_san_luong FROM monthly_bill")
        all_months = cursor.fetchall()
        
        updated_count = 0
        
        for row in all_months:
            y, m, kwh = row[0], row[1], row[2]
            new_cost = calculate_tier_cost(kwh, y, m)
            
            cursor.execute("""
                UPDATE monthly_bill 
                SET thanh_tien = ? 
                WHERE nam = ? AND thang = ?
            """, (new_cost, y, m))
            updated_count += 1
            
        conn.commit()
        log.info(f"TONGOU: Đã cập nhật lại giá tiền cho {updated_count} tháng.")
        
        now = datetime.now()
        conn.close()
        conn = None
        
        update_sensors_from_db(now.year, now.month, now.day)
        
    except Exception as e:
        log.error(f"TONGOU: Lỗi khi tính lại lịch sử: {e}")
        if conn: conn.close()

@time_trigger('startup')
def restore_sensor_state():
    """Khôi phục trạng thái khi khởi động lại"""
    now = datetime.now()
    log.info("TONGOU: Startup - Đang khôi phục sensor...")
    update_sensors_from_db(now.year, now.month, now.day)