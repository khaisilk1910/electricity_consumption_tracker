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
from .const import DOMAIN, SIGNAL_UPDATE_SENSORS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensor platform."""
    db_path = hass.data[DOMAIN][entry.entry_id]["db_path"]
    friendly_name = entry.data.get("friendly_name", "Electricity")
    
    entities = []
    entities.append(ConsumptionTotalSensor(db_path, f"{friendly_name} Total All Time", entry.entry_id))

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
        self.async_schedule_update_ha_state(True)

class ConsumptionMonthlySensor(ConsumptionBase):
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
            
            cursor.execute("""
                SELECT thanh_tien, tong_san_luong, thanh_tien_sau_thue, vat 
                FROM monthly_bill WHERE nam=? AND thang=?
            """, (self._year, self._month))
            res = cursor.fetchone()
            
            cursor.execute("SELECT ngay, san_luong FROM daily_usage WHERE nam=? AND thang=? ORDER BY ngay ASC", (self._year, self._month))
            daily_rows = cursor.fetchall()
            conn.close()

            if res:
                pre_tax = int(res[0]) if res[0] else 0
                vat_val = res[3] if res[3] is not None else 8
                
                # [FIX] Logic fallback mạnh hơn: Nếu DB trả về <= 0 mà có tiền trước thuế -> Tự tính lại
                db_post_tax = res[2]
                if db_post_tax and db_post_tax > 0:
                    post_tax = int(db_post_tax)
                else:
                    post_tax = int(pre_tax * (1 + vat_val / 100))
                
                self._attr_native_value = pre_tax
                self._attr_extra_state_attributes = {
                    "tong_san_luong_kwh": round(res[1], 2),
                    "tong_tien_truoc_thue": pre_tax,
                    "tong_tien_sau_thue": post_tax,
                    "vat_rate": f"{vat_val}%",
                    "chi_tiet_ngay": {f"Ngay_{r[0]}": round(r[1], 2) for r in daily_rows},
                    "data_source": "Monthly Detail"
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error month: {e}")

class ConsumptionYearlySensor(ConsumptionBase):
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
            
            cursor.execute("""
                SELECT tong_tien, tong_san_luong, tong_tien_sau_thue, vat 
                FROM yearly_bill WHERE nam=?
            """, (self._year,))
            res = cursor.fetchone()
            
            cursor.execute("""
                SELECT thang, tong_san_luong, thanh_tien, thanh_tien_sau_thue 
                FROM monthly_bill WHERE nam=? ORDER BY thang ASC
            """, (self._year,))
            month_rows = cursor.fetchall()
            conn.close()
            
            if res:
                pre_tax = int(res[0]) if res[0] else 0
                vat_val = res[3] if res[3] is not None else 8

                # [FIX] Fallback cho Năm
                db_post_tax = res[2]
                if db_post_tax and db_post_tax > 0:
                    post_tax = int(db_post_tax)
                else:
                    post_tax = int(pre_tax * (1 + vat_val / 100))
                
                self._attr_native_value = pre_tax
                self._attr_extra_state_attributes = {
                    "tong_san_luong_nam": round(res[1], 2),
                    "tong_tien_truoc_thue": pre_tax,
                    "tong_tien_sau_thue": post_tax,
                    "vat_rate": f"{vat_val}%",
                    "chi_tiet_cac_thang": {
                        f"Thang_{r[0]}": {
                            "san_luong_kwh": round(r[1], 2),
                            "thanh_tien_vnd": int(r[2]),
                            "thanh_tien_sau_thue_vnd": int(r[3]) if r[3] and r[3] > 0 else int(r[2] * (1 + vat_val/100))
                        } for r in month_rows
                    }
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error year: {e}")

class ConsumptionTotalSensor(ConsumptionBase):
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
            
            cursor.execute("""
                SELECT tong_san_luong, tong_so_thang, 
                       thoi_diem_bat_dau, thoi_diem_ket_thuc, 
                       tong_tien_tich_luy, tong_tien_tich_luy_sau_thue, vat 
                FROM total_usage
            """)
            res = cursor.fetchone()
            
            cursor.execute("""
                SELECT nam, tong_san_luong, tong_tien, tong_tien_sau_thue 
                FROM yearly_bill ORDER BY nam DESC
            """)
            years_stats = cursor.fetchall()
            conn.close()
            
            if res:
                self._attr_native_value = round(res[0], 2)
                
                # [FIX] Fallback cho Tổng tích lũy
                total_pre = int(res[4]) if res[4] else 0
                db_total_post = res[5]
                vat_val = res[6] if res[6] is not None else 8

                if db_total_post and db_total_post > 0:
                    total_post = int(db_total_post)
                else:
                    total_post = int(total_pre * (1 + vat_val / 100))

                self._attr_extra_state_attributes = {
                    "tong_so_thang_du_lieu": res[1],
                    "thoi_diem_bat_dau": res[2],
                    "thoi_diem_ket_thuc": res[3],
                    "tong_tien_tich_luy": total_pre,
                    "tong_tien_tich_luy_sau_thue": total_post,
                    "current_vat_ref": f"{vat_val}%",
                    "chi_tiet_tung_nam": {
                        f"Nam_{y[0]}": {
                            "tong_san_luong_kwh": round(y[1], 2),
                            "tong_tien_vnd": int(y[2]),
                            "tong_tien_sau_thue_vnd": int(y[3]) if y[3] and y[3] > 0 else int(y[2] * (1 + vat_val/100))
                        } for y in years_stats
                    }
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error total: {e}")
