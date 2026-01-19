"""Sensor platform for Electricity Consumption Tracker."""
import sqlite3
import os
import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensor platform."""
    # Lấy đường dẫn DB từ hass.data
    db_path = hass.data[DOMAIN][entry.entry_id]["db_path"]
    
    # Lấy tên hiển thị gốc từ cấu hình (ví dụ: "Điện Nhà Khải")
    base_name = entry.data.get("friendly_name", "Electricity")
    
    entities = []
    
    # 1. Tạo Sensor Tổng Tích Lũy (Luôn luôn có)
    entities.append(ConsumptionTotalSensor(db_path, f"{base_name} Total All Time", entry.entry_id))

    # 2. Quét DB để tìm các Năm và Tháng có dữ liệu
    if os.path.exists(db_path):
        try:
            # Chạy query trong executor để không chặn event loop
            def fetch_history():
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Lấy danh sách các năm
                cursor.execute("SELECT DISTINCT nam FROM monthly_bill ORDER BY nam DESC")
                years = [r[0] for r in cursor.fetchall()]
                
                # Lấy danh sách các cặp (năm, tháng)
                cursor.execute("SELECT nam, thang FROM monthly_bill ORDER BY nam DESC, thang DESC")
                months = cursor.fetchall() # List of (nam, thang)
                
                conn.close()
                return years, months

            years, months = await hass.async_add_executor_job(fetch_history)

            # 3. Tạo Sensor cho từng Năm (Dynamic Year)
            for year in years:
                # Tên sensor: "Điện Nhà Khải Bill 2024"
                name = f"{base_name} Bill {year}"
                entities.append(ConsumptionYearlySensor(db_path, name, year, entry.entry_id))

            # 4. Tạo Sensor cho từng Tháng (Dynamic Month)
            for year, month in months:
                # Tên sensor: "Điện Nhà Khải Bill 01/2024"
                name = f"{base_name} Bill {month:02d}/{year}"
                entities.append(ConsumptionMonthlySensor(db_path, name, year, month, entry.entry_id))
                
        except Exception as e:
            _LOGGER.error(f"Error scanning database for history sensors: {e}")

    # Thêm tất cả entities vào HA
    async_add_entities(entities, update_before_add=True)


class ConsumptionBase(SensorEntity):
    """Base class for consumption sensors."""
    
    def __init__(self, db_path, name, entry_id):
        self._db_path = db_path
        self._attr_name = name
        self._entry_id = entry_id
        # Đặt False để tự kiểm soát hoàn toàn tên hiển thị, tránh bị lặp tên device
        self._attr_has_entity_name = False 
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": entry_id, # Link vào device gốc
        }

class ConsumptionMonthlySensor(ConsumptionBase):
    """Sensor hiển thị tiền điện của một tháng cụ thể (VNĐ)."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "đ"

    def __init__(self, db_path, name, year, month, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        self._month = month
        # Unique ID cố định theo năm tháng: prefix_monthly_2024_1
        self._attr_unique_id = f"{entry_id}_monthly_{year}_{month}"
        self._attr_icon = "mdi:calendar-month"

    def update(self):
        """Fetch data from SQLite synchronously."""
        if not os.path.exists(self._db_path):
            return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            # Lấy tổng tiền và tổng số điện của tháng này
            cursor.execute(
                "SELECT thanh_tien, tong_san_luong FROM monthly_bill WHERE nam=? AND thang=?", 
                (self._year, self._month)
            )
            res = cursor.fetchone()
            
            # Lấy chi tiết từng ngày
            cursor.execute(
                "SELECT ngay, san_luong FROM daily_usage WHERE nam=? AND thang=? ORDER BY ngay ASC", 
                (self._year, self._month)
            )
            daily_rows = cursor.fetchall()
            conn.close()

            if res:
                self._attr_native_value = int(res[0]) # Thành tiền (VNĐ)
                self._attr_extra_state_attributes = {
                    "tong_san_luong_kwh": round(res[1], 2),
                    "thang_tinh_cuoc": f"{self._month}/{self._year}",
                    # Tạo dictionary chi tiết ngày giống file gốc: 'Ngay_01': 12.5
                    "chi_tiet_ngay": {f"Ngay_{r[0]:02d}": r[1] for r in daily_rows}
                }
            else:
                self._attr_native_value = 0
                self._attr_extra_state_attributes = {
                    "tong_san_luong_kwh": 0,
                    "chi_tiet_ngay": {}
                }
        except Exception as e:
            _LOGGER.error(f"Error updating monthly sensor {self._month}/{self._year}: {e}")

class ConsumptionYearlySensor(ConsumptionBase):
    """Sensor hiển thị tổng tiền điện trong năm (VNĐ)."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "đ"

    def __init__(self, db_path, name, year, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        # Unique ID cố định theo năm: prefix_yearly_2024
        self._attr_unique_id = f"{entry_id}_yearly_{year}"
        self._attr_icon = "mdi:calendar-range"

    def update(self):
        if not os.path.exists(self._db_path):
            return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            # Tính tổng tiền và tổng kWh cả năm
            cursor.execute("SELECT SUM(thanh_tien), SUM(tong_san_luong) FROM monthly_bill WHERE nam=?", (self._year,))
            res = cursor.fetchone()
            
            # Lấy chi tiết các tháng trong năm
            cursor.execute("SELECT thang, tong_san_luong, thanh_tien FROM monthly_bill WHERE nam=? ORDER BY thang ASC", (self._year,))
            month_rows = cursor.fetchall()
            conn.close()
            
            if res and res[0] is not None:
                self._attr_native_value = int(res[0])
                self._attr_extra_state_attributes = {
                    "tong_san_luong_nam_kwh": round(res[1] or 0, 2),
                    # Chi tiết từng tháng: 'Thang_1': {...}
                    "chi_tiet_cac_thang": {
                        f"Thang_{r[0]}": {
                            "san_luong_kwh": round(r[1], 2),
                            "thanh_tien_vnd": int(r[2])
                        } for r in month_rows
                    }
                }
            else:
                self._attr_native_value = 0
                self._attr_extra_state_attributes = {}
                
        except Exception as e:
            _LOGGER.error(f"Error updating yearly sensor {self._year}: {e}")

class ConsumptionTotalSensor(ConsumptionBase):
    """Sensor hiển thị tổng sản lượng điện tích lũy (All Time)."""
    
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, db_path, name, entry_id):
        super().__init__(db_path, name, entry_id)
        self._attr_unique_id = f"{entry_id}_total_accumulated"
        self._attr_icon = "mdi:lightning-bolt"

    def update(self):
        if not os.path.exists(self._db_path):
            return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            # Lấy tổng kWh và số tháng
            cursor.execute("SELECT tong_san_luong, tong_so_thang FROM total_usage")
            res = cursor.fetchone()
            
            # Lấy thống kê theo năm để hiển thị attribute
            cursor.execute("SELECT nam, SUM(tong_san_luong), SUM(thanh_tien) FROM monthly_bill GROUP BY nam ORDER BY nam DESC")
            year_rows = cursor.fetchall()
            conn.close()
            
            if res:
                self._attr_native_value = round(res[0], 2)
                
                # Tính tổng tiền tích lũy
                grand_total_money = sum([row[2] for row in year_rows]) if year_rows else 0
                
                self._attr_extra_state_attributes = {
                    "tong_so_thang_du_lieu": res[1],
                    "tong_tien_tich_luy_vnd": int(grand_total_money),
                    "chi_tiet_tung_nam": {
                        f"Nam_{row[0]}": {
                            "tong_san_luong_kwh": round(row[1], 2),
                            "tong_tien_vnd": int(row[2])
                        } for row in year_rows
                    }
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Error updating total sensor: {e}")
