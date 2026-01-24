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
    db_path = hass.data[DOMAIN][entry.entry_id]["db_path"]
    friendly_name = entry.data.get("friendly_name", "Electricity")
    
    manager = ElectricitySensorManager(hass, entry, async_add_entities, db_path, friendly_name)
    await manager.async_create_total_sensor()
    await manager.async_check_and_add_new_sensors()

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, 
            f"{SIGNAL_UPDATE_SENSORS}_{entry.entry_id}", 
            manager.async_check_and_add_new_sensors
        )
    )

class ElectricitySensorManager:
    def __init__(self, hass, entry, async_add_entities, db_path, friendly_name):
        self.hass = hass
        self.entry_id = entry.entry_id
        self.async_add_entities = async_add_entities
        self.db_path = db_path
        self.friendly_name = friendly_name
        self.existing_years = set()
        self.existing_months = set() 
        self.total_sensor_created = False

    async def async_create_total_sensor(self):
        if not self.total_sensor_created:
            self.async_add_entities([
                ConsumptionTotalSensor(self.db_path, f"{self.friendly_name} Total All Time", self.entry_id)
            ])
            self.total_sensor_created = True

    async def async_check_and_add_new_sensors(self):
        if not os.path.exists(self.db_path): return

        def get_existing_periods():
            found_years = []
            found_months = []
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT nam FROM monthly_bill ORDER BY nam DESC")
                found_years = [r[0] for r in cursor.fetchall()]
                cursor.execute("SELECT nam, thang FROM monthly_bill ORDER BY nam DESC, thang DESC")
                found_months = [(r[0], r[1]) for r in cursor.fetchall()]
                conn.close()
            except Exception as e:
                pass
            return found_years, found_months

        years, months = await self.hass.async_add_executor_job(get_existing_periods)
        new_entities = []

        for year in years:
            if year not in self.existing_years:
                name = f"{self.friendly_name} - Năm {year}"
                new_entities.append(ConsumptionYearlySensor(self.db_path, name, year, self.entry_id))
                self.existing_years.add(year)

        for year, month in months:
            if (year, month) not in self.existing_months:
                name = f"{self.friendly_name} - Tháng {month:02d}/{year}"
                new_entities.append(ConsumptionMonthlySensor(self.db_path, name, year, month, self.entry_id))
                self.existing_months.add((year, month))

        if new_entities:
            self.async_add_entities(new_entities)

class ConsumptionBase(SensorEntity):
    def __init__(self, db_path, name, entry_id):
        self._db_path = db_path
        self._attr_name = name
        self._entry_id = entry_id
        self._attr_has_entity_name = False 
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}, "name": entry_id}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{SIGNAL_UPDATE_SENSORS}_{self._entry_id}", self._async_force_update_callback)
        )

    @callback
    def _async_force_update_callback(self):
        self.async_schedule_update_ha_state(True)

    async def async_update(self):
        if not os.path.exists(self._db_path): return
        await self.hass.async_add_executor_job(self._update_data_sync)

    def _update_data_sync(self):
        raise NotImplementedError()

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

    def _update_data_sync(self):
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT thanh_tien, tong_san_luong, thanh_tien_sau_thue, vat, ngay_bat_dau, ngay_ket_thuc
                FROM monthly_bill WHERE nam=? AND thang=?
            """, (self._year, self._month))
            res = cursor.fetchone()
            
            daily_rows = []
            start_date_str = "N/A"
            end_date_str = "N/A"

            if res:
                # [FIX] Handle trường hợp NULL nếu migration chưa kịp chạy
                start_date_str = res[4] if res[4] else "N/A"
                end_date_str = res[5] if res[5] else "N/A"
                
                if start_date_str != "N/A" and end_date_str != "N/A":
                    cursor.execute(f"""
                        SELECT ngay, san_luong 
                        FROM daily_usage 
                        WHERE printf('%04d-%02d-%02d', nam, thang, ngay) BETWEEN ? AND ?
                        ORDER BY nam, thang, ngay ASC
                    """, (start_date_str, end_date_str))
                else:
                    cursor.execute("SELECT ngay, san_luong FROM daily_usage WHERE nam=? AND thang=? ORDER BY ngay ASC", (self._year, self._month))
                
                daily_rows = cursor.fetchall()

            conn.close()

            if res:
                pre_tax = int(res[0]) if res[0] else 0
                vat_val = res[3] if res[3] is not None else 8
                
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
                    "ky_hoa_don": f"{start_date_str} -> {end_date_str}",
                    "chi_tiet_ngay": {f"Ngay_{r[0]:02d}": round(r[1], 2) for r in daily_rows},
                    "data_source": "Monthly Detail"
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error month {self._month}/{self._year}: {e}")

class ConsumptionYearlySensor(ConsumptionBase):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "đ"

    def __init__(self, db_path, name, year, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        self._attr_unique_id = f"{entry_id}_bill_{year}"
        self._attr_icon = "mdi:calendar-range"

    def _update_data_sync(self):
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
                        f"Thang_{r[0]:02d}": {
                            "san_luong_kwh": round(r[1], 2),
                            "thanh_tien_vnd": int(r[2]),
                            "thanh_tien_sau_thue_vnd": int(r[3]) if r[3] and r[3] > 0 else int(r[2] * (1 + vat_val/100))
                        } for r in month_rows
                    }
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error year {self._year}: {e}")

class ConsumptionTotalSensor(ConsumptionBase):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, db_path, name, entry_id):
        super().__init__(db_path, name, entry_id)
        self._attr_unique_id = f"{entry_id}_total_all_time"
        self._attr_icon = "mdi:lightning-bolt"

    def _update_data_sync(self):
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
                SELECT nam, tong_san_luong, tong_tien, tong_tien_sau_thue, vat
                FROM yearly_bill ORDER BY nam DESC
            """)
            years_stats = cursor.fetchall()
            conn.close()
            
            if res:
                self._attr_native_value = round(res[0], 2)
                
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
                            "tong_tien_sau_thue_vnd": int(y[3]) if y[3] and y[3] > 0 else int(y[2] * (1 + (y[4] or 8)/100))
                        } for y in years_stats
                    }
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Update error total: {e}")
