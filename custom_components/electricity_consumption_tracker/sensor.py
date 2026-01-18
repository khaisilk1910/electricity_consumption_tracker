import sqlite3
import datetime
import os
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    db_path = hass.config.path(f"custom_components/{DOMAIN}/tracker_{entry.entry_id}.db")
    friendly_name = entry.data["friendly_name"]
    now = datetime.datetime.now()
    
    # Khởi tạo và gắn vào Device ID
    async_add_entities([
        ConsumptionMonthlySensor(db_path, f"{friendly_name} Monthly", now.year, now.month, entry.entry_id),
        ConsumptionYearlySensor(db_path, f"{friendly_name} Yearly", now.year, entry.entry_id),
        ConsumptionTotalSensor(db_path, f"{friendly_name} Total", entry.entry_id)
    ], True)

class ConsumptionBase(SensorEntity):
    """Class nền tảng để liên kết Device."""
    def __init__(self, db_path, name, entry_id):
        self._db_path = db_path
        self._attr_name = name
        self._entry_id = entry_id
        # Thông tin để Home Assistant gom nhóm vào một thiết bị
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": name.split(" ")[0], # Lấy phần tên chính
        }

class ConsumptionMonthlySensor(ConsumptionBase):
    def __init__(self, db_path, name, year, month, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year, self._month = year, month
        self._attr_unique_id = f"cons_{entry_id}_monthly"
        self._attr_native_unit_of_measurement = "đ"

    async def async_update(self):
        def fetch():
            if not os.path.exists(self._db_path): return None, []
            conn = sqlite3.connect(self._db_path)
            res = conn.execute("SELECT thanh_tien, tong_san_luong FROM monthly_bill WHERE nam=? AND thang=?", (self._year, self._month)).fetchone()
            daily = conn.execute("SELECT ngay, san_luong FROM daily_usage WHERE nam=? AND thang=? ORDER BY ngay ASC", (self._year, self._month)).fetchall()
            conn.close()
            return res, daily
        res, daily = await self.hass.async_add_executor_job(fetch)
        if res:
            self._attr_native_value = int(res[0])
            self._attr_extra_state_attributes = {
                "tong_san_luong_kwh": round(res[1], 2),
                "chi_tiet_ngay": {f"Ngay_{r[0]}": round(r[1], 2) for r in daily}
            }

class ConsumptionYearlySensor(ConsumptionBase):
    def __init__(self, db_path, name, year, entry_id):
        super().__init__(db_path, name, entry_id)
        self._year = year
        self._attr_unique_id = f"cons_{entry_id}_yearly"
        self._attr_native_unit_of_measurement = "đ"

    async def async_update(self):
        def fetch():
            if not os.path.exists(self._db_path): return None
            conn = sqlite3.connect(self._db_path)
            res = conn.execute("SELECT SUM(thanh_tien) FROM monthly_bill WHERE nam=?", (self._year,)).fetchone()
            conn.close()
            return res
        res = await self.hass.async_add_executor_job(fetch)
        self._attr_native_value = int(res[0]) if res and res[0] else 0

class ConsumptionTotalSensor(ConsumptionBase):
    def __init__(self, db_path, name, entry_id):
        super().__init__(db_path, name, entry_id)
        self._attr_unique_id = f"cons_{entry_id}_total"
        self._attr_native_unit_of_measurement = "kWh"

    async def async_update(self):
        def fetch():
            if not os.path.exists(self._db_path): return None
            conn = sqlite3.connect(self._db_path)
            res = conn.execute("SELECT SUM(tong_san_luong) FROM monthly_bill").fetchone()
            conn.close()
            return res
        res = await self.hass.async_add_executor_job(fetch)
        self._attr_native_value = round(res[0], 2) if res and res[0] else 0
