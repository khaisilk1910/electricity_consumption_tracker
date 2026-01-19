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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIGNAL_UPDATE_SENSORS, VAT_RATE # [NEW] Import VAT_RATE

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensor platform."""
    db_path = hass.data[DOMAIN][entry.entry_id]["db_path"]
    friendly_name = entry.data.get("friendly_name", "Electricity")
    
    entities = []
    
    # 1. Luôn tạo Sensor Tổng
    entities.append(ConsumptionTotalSensor(db_path, f"{friendly_name} Total All Time", entry.entry_id))

    # 2. Quét Database (Auto-Discovery)
    if os.path.exists(db_path):
        def scan_database():
            found_years = []
            found_months = []
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT nam FROM monthly_bill ORDER BY nam DESC")
                found_years = [r[0] for r in cursor.fetchall()]
                cursor.execute("SELECT nam, thang FROM monthly_bill ORDER BY nam DESC, thang DESC")
                found_months = cursor.fetchall()
                conn.close()
            except Exception as e:
                _LOGGER.error(f"Lỗi khi quét database {db_path}: {e}")
            return found_years, found_months

        years, months = await hass.async_add_executor_job(scan_database)
        
        for year in years:
            name = f"{friendly_name} - Năm {year}"
            entities.append(ConsumptionYearlySensor(db_path, name, year, entry.entry_id))

        for year, month in months:
            name = f"{friendly_name} - Tháng {month}/{year}"
            entities.append(ConsumptionMonthlySensor(db_path, name, year, month, entry.entry_id))
    
    async_add_entities(entities, update_before_add=True)


class ConsumptionBase(SensorEntity):
    """Class cơ bản."""
    def __init__(self, db_path, name, entry_id):
        self._db_path = db_path
        self._attr_name = name
        self._entry_id = entry_id
        self._attr_has_entity_name = False 
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": entry_id, 
        }

    async def async_added_to_hass(self):
        """Đăng ký lắng nghe sự kiện update."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_SENSORS}_{self._entry_id}",
                self._force_update_callback
            )
        )

    @callback
    def _force_update_callback(self):
        """Ép buộc cập nhật lại state."""
        self.async_schedule_update_ha_state(True)

class ConsumptionMonthlySensor(ConsumptionBase):
    """Sensor hiển thị chi tiết Tháng."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "đ"

    def __init__(self, db_path, name, year, month, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        self._month = month
        self._attr_unique_id = f"{entry_id}_bill_{year}_{month:02d}"
        self._attr_icon = "mdi:calendar-month"

    def update(self):
        if not os.path.exists(self._db_path): return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT thanh_tien, tong_san_luong FROM monthly_bill WHERE nam=? AND thang=?", (self._year, self._month))
            res = cursor.fetchone()
            
            cursor.execute("SELECT ngay, san_luong FROM daily_usage WHERE nam=? AND thang=? ORDER BY ngay ASC", (self._year, self._month))
            daily_rows = cursor.fetchall()
            conn.close()

            if res:
                pre_tax = int(res[0])
                # [UPDATE] Tính thuế VAT 8%
                post_tax = int(pre_tax * (1 + VAT_RATE))
                
                self._attr_native_value = pre_tax
                self._attr_extra_state_attributes = {
                    "tong_san_luong_kwh": round(res[1], 2),
                    "tong_tien_truoc_thue": pre_tax,
                    "tong_tien_sau_thue": post_tax, # [NEW] Attribute mới
                    "vat_rate": f"{int(VAT_RATE*100)}%",
                    "chi_tiet_ngay": {f"Ngay_{r[0]}": round(r[1], 2) for r in daily_rows},
                    "data_source": "Monthly Detail Auto Gen"
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error month {self._month}/{self._year}: {e}")

class ConsumptionYearlySensor(ConsumptionBase):
    """Sensor hiển thị chi tiết Năm."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "đ"

    def __init__(self, db_path, name, year, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        self._attr_unique_id = f"{entry_id}_bill_{year}"
        self._attr_icon = "mdi:calendar-range"

    def update(self):
        if not os.path.exists(self._db_path): return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT SUM(thanh_tien), SUM(tong_san_luong) FROM monthly_bill WHERE nam=?", (self._year,))
            res = cursor.fetchone()
            
            cursor.execute("SELECT thang, tong_san_luong, thanh_tien FROM monthly_bill WHERE nam=? ORDER BY thang ASC", (self._year,))
            month_rows = cursor.fetchall()
            conn.close()
            
            if res and res[0] is not None:
                pre_tax = int(res[0])
                # [UPDATE] Tính thuế VAT 8%
                post_tax = int(pre_tax * (1 + VAT_RATE))
                
                self._attr_native_value = pre_tax
                self._attr_extra_state_attributes = {
                    "tong_san_luong_nam": round(res[1], 2),
                    "tong_tien_truoc_thue": pre_tax,
                    "tong_tien_sau_thue": post_tax, # [NEW] Attribute mới
                    "vat_rate": f"{int(VAT_RATE*100)}%",
                    "chi_tiet_cac_thang": {
                        f"Thang_{r[0]}": {
                            "san_luong_kwh": round(r[1], 2),
                            "thanh_tien_vnd": int(r[2]),
                            "thanh_tien_sau_thue_vnd": int(r[2] * (1 + VAT_RATE)) # [NEW] Thêm vào chi tiết tháng
                        } for r in month_rows
                    },
                    "data_source": "Auto Generated"
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error year {self._year}: {e}")

class ConsumptionTotalSensor(ConsumptionBase):
    """Sensor hiển thị Tổng Tích Lũy."""
    
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, db_path, name, entry_id):
        super().__init__(db_path, name, entry_id)
        self._attr_unique_id = f"{entry_id}_total_all_time"
        self._attr_icon = "mdi:lightning-bolt"

    def update(self):
        if not os.path.exists(self._db_path): return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT tong_san_luong, tong_so_thang FROM total_usage")
            res = cursor.fetchone()
            
            cursor.execute("SELECT nam, SUM(tong_san_luong), SUM(thanh_tien) FROM monthly_bill GROUP BY nam ORDER BY nam DESC")
            years_stats = cursor.fetchall()
            conn.close()
            
            if res:
                self._attr_native_value = round(res[0], 2)
                grand_total_money = sum([y[2] for y in years_stats]) if years_stats else 0
                # [UPDATE] Tính thuế
                grand_total_post_tax = int(grand_total_money * (1 + VAT_RATE))

                self._attr_extra_state_attributes = {
                    "tong_so_thang_du_lieu": res[1],
                    "tong_tien_tich_luy": int(grand_total_money),
                    "tong_tien_tich_luy_sau_thue": grand_total_post_tax, # [NEW] Attribute mới
                    "vat_rate": f"{int(VAT_RATE*100)}%",
                    "chi_tiet_tung_nam": {
                        f"Nam_{y[0]}": {
                            "tong_san_luong_kwh": round(y[1], 2),
                            "tong_tien_vnd": int(y[2]),
                            "tong_tien_sau_thue_vnd": int(y[2] * (1 + VAT_RATE)) # [NEW] Thêm vào chi tiết năm
                        } for y in years_stats
                    }
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error total: {e}")
