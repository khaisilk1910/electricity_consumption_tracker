"""Sensor platform for Electricity Consumption Tracker."""
import sqlite3
import os
import logging
import homeassistant.util.dt as dt_util

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
    db_path = hass.data[DOMAIN][entry.entry_id]["db_path"]
    name = entry.data.get("friendly_name", "Electricity")
    
    # Lấy thời gian hiện tại để tạo sensor cho tháng/năm nay
    now = dt_util.now()
    
    entities = [
        ConsumptionMonthlySensor(db_path, f"{name} Monthly Bill", now.year, now.month, entry.entry_id),
        ConsumptionYearlySensor(db_path, f"{name} Yearly Bill", now.year, entry.entry_id),
        ConsumptionTotalSensor(db_path, f"{name} Total Usage", entry.entry_id)
    ]
    
    async_add_entities(entities, update_before_add=True)

class ConsumptionBase(SensorEntity):
    """Base class for consumption sensors."""
    
    def __init__(self, db_path, name, entry_id):
        self._db_path = db_path
        self._attr_name = name
        self._entry_id = entry_id
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": name,
        }

class ConsumptionMonthlySensor(ConsumptionBase):
    """Sensor hiển thị tiền điện tháng hiện tại (VNĐ)."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "đ"

    def __init__(self, db_path, name, year, month, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        self._month = month
        self._attr_unique_id = f"{entry_id}_monthly_{year}_{month}"
        self._attr_icon = "mdi:cash"

    def update(self):
        """Fetch data from SQLite synchronously."""
        if not os.path.exists(self._db_path):
            return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            # Lấy tổng tiền và tổng số điện
            cursor.execute(
                "SELECT thanh_tien, tong_san_luong FROM monthly_bill WHERE nam=? AND thang=?", 
                (self._year, self._month)
            )
            res = cursor.fetchone()
            
            # Lấy chi tiết từng ngày để đưa vào attributes
            cursor.execute(
                "SELECT ngay, san_luong FROM daily_usage WHERE nam=? AND thang=? ORDER BY ngay ASC", 
                (self._year, self._month)
            )
            daily_rows = cursor.fetchall()
            conn.close()

            if res:
                self._attr_native_value = int(res[0]) # Thành tiền
                self._attr_extra_state_attributes = {
                    "total_kwh_month": round(res[1], 2),
                    "billing_month": f"{self._month}/{self._year}",
                    "daily_breakdown_kwh": {f"{r[0]:02d}": r[1] for r in daily_rows}
                }
            else:
                self._attr_native_value = 0
                self._attr_extra_state_attributes = {
                    "total_kwh_month": 0,
                    "daily_breakdown_kwh": {}
                }
        except Exception as e:
            _LOGGER.error(f"Error updating monthly sensor: {e}")

class ConsumptionYearlySensor(ConsumptionBase):
    """Sensor hiển thị tổng tiền điện trong năm (VNĐ)."""
    
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "đ"

    def __init__(self, db_path, name, year, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        self._attr_unique_id = f"{entry_id}_yearly_{year}"
        self._attr_icon = "mdi:finance"

    def update(self):
        if not os.path.exists(self._db_path):
            return

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(thanh_tien) FROM monthly_bill WHERE nam=?", (self._year,))
            res = cursor.fetchone()
            conn.close()
            
            self._attr_native_value = int(res[0]) if res and res[0] is not None else 0
        except Exception as e:
            _LOGGER.error(f"Error updating yearly sensor: {e}")

class ConsumptionTotalSensor(ConsumptionBase):
    """Sensor hiển thị tổng sản lượng điện tích lũy (kWh)."""
    
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
            cursor.execute("SELECT tong_san_luong, tong_so_thang FROM total_usage")
            res = cursor.fetchone()
            conn.close()
            
            if res:
                self._attr_native_value = round(res[0], 2)
                self._attr_extra_state_attributes = {
                    "months_tracked": res[1]
                }
            else:
                self._attr_native_value = 0
        except Exception as e:
            _LOGGER.error(f"Error updating total sensor: {e}")
