"""Snapshot-based sensors: one SQLite read for all entities per refresh."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Create one manager per entry; defer database reads until after setup."""
    instance = hass.data[DOMAIN][entry.entry_id]
    manager = ConsumptionSensorManager(entry, async_add_entities, instance["store"])
    instance["manager"] = manager
    manager.add_total_sensor()


class ConsumptionSensorManager:
    """Keep a consistent in-memory snapshot shared by all sensors."""

    def __init__(self, entry: ConfigEntry, add_entities: AddEntitiesCallback, store) -> None:
        self.entry = entry
        self.add_entities = add_entities
        self.store = store
        self.friendly_name = entry.data.get("friendly_name", "Electricity")
        self.ready = False
        self.total = {}
        self.years = {}
        self.months = {}
        self.daily = defaultdict(list)
        self.entities = []
        self.seen_years = set()
        self.seen_months = set()

    def add_total_sensor(self) -> None:
        entity = ConsumptionTotalSensor(self)
        self.entities.append(entity)
        self.add_entities([entity])

    async def async_refresh(self) -> None:
        """Refresh all entity values using one executor job, not one per sensor."""
        try:
            snapshot = await self.store.async_snapshot()
        except Exception:
            _LOGGER.exception("Could not read tracker snapshot: %s", self.entry.entry_id)
            return

        self.total = snapshot["total"][0] if snapshot["total"] else {}
        self.years = {r["nam"]: r for r in snapshot["yearly"]}
        self.months = {(r["nam"], r["thang"]): r for r in snapshot["monthly"]}
        daily = defaultdict(list)
        for row in snapshot["daily"]:
            day = date(row["nam"], row["thang"], row["ngay"]).isoformat()
            daily[day[:7]].append((day, row["san_luong"]))
        self.daily = daily
        self.ready = True

        new_entities = []
        for year in sorted(self.years, reverse=True):
            if year not in self.seen_years:
                new_entities.append(ConsumptionYearlySensor(self, year))
                self.seen_years.add(year)
        for year, month in sorted(self.months, reverse=True):
            if (year, month) not in self.seen_months:
                new_entities.append(ConsumptionMonthlySensor(self, year, month))
                self.seen_months.add((year, month))
        if new_entities:
            self.entities.extend(new_entities)
            self.add_entities(new_entities)
            _LOGGER.debug("Created %d period sensors for %s", len(new_entities), self.entry.entry_id)

        for entity in self.entities:
            if entity.hass is not None and entity.entity_id is not None:
                entity.async_write_ha_state()


class ConsumptionBase(SensorEntity):
    """A non-polling sensor backed by the manager's in-memory snapshot."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, manager: ConsumptionSensorManager, name: str, unique_suffix: str) -> None:
        self.manager = manager
        self._attr_name = name
        self._attr_unique_id = f"{manager.entry.entry_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, manager.entry.entry_id)})

    @property
    def available(self) -> bool:
        return self.manager.ready


class ConsumptionMonthlySensor(ConsumptionBase):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "VND"
    _attr_icon = "mdi:calendar-month"

    def __init__(self, manager: ConsumptionSensorManager, year: int, month: int) -> None:
        super().__init__(manager, f"{manager.friendly_name} - Tháng {month:02d}/{year}", f"bill_{year}_{month:02d}")
        self.year = year
        self.month = month
        # Existing monthly dashboard IDs use unpadded month numbers.
        self.entity_id = f"sensor.{slugify(f'{manager.friendly_name} Thang {month} {year}')}"

    @property
    def native_value(self) -> int | None:
        row = self.manager.months.get((self.year, self.month))
        return int(row.get("thanh_tien") or 0) if row else None

    @property
    def extra_state_attributes(self) -> dict:
        row = self.manager.months.get((self.year, self.month))
        if not row:
            return {}
        start = row.get("ngay_bat_dau")
        end = row.get("ngay_ket_thuc")
        selected = []
        if start and end:
            # A billing cycle can cross calendar months.
            selected = [(day, val) for days in self.manager.daily.values()
                        for day, val in days if start <= day <= end]
        selected.sort()
        vat = row.get("vat") if row.get("vat") is not None else 8
        return {
            "tong_san_luong_kwh": round(row.get("tong_san_luong") or 0, 3),
            "tong_tien_truoc_thue": int(row.get("thanh_tien") or 0),
            "tong_tien_sau_thue": int(row.get("thanh_tien_sau_thue") or 0),
            "vat_rate": f"{vat}%",
            "ky_hoa_don": f"{start} -> {end}",
            "chi_tiet_ngay": {f"Ngay_{int(day[-2:]):02d}": round(val, 3) for day, val in selected},
            "chi_tiet_ngay_iso": {day: round(val, 3) for day, val in selected},
            "data_source": "Monthly Detail",
        }


class ConsumptionYearlySensor(ConsumptionBase):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "VND"
    _attr_icon = "mdi:calendar-range"

    def __init__(self, manager: ConsumptionSensorManager, year: int) -> None:
        super().__init__(manager, f"{manager.friendly_name} - Năm {year}", f"bill_{year}")
        self.year = year

    @property
    def native_value(self) -> int | None:
        row = self.manager.years.get(self.year)
        return int(row.get("tong_tien") or 0) if row else None

    @property
    def extra_state_attributes(self) -> dict:
        row = self.manager.years.get(self.year)
        if not row:
            return {}
        vat = row.get("vat") if row.get("vat") is not None else 8
        return {
            "tong_san_luong_nam": round(row.get("tong_san_luong") or 0, 3),
            "tong_tien_truoc_thue": int(row.get("tong_tien") or 0),
            "tong_tien_sau_thue": int(row.get("tong_tien_sau_thue") or 0),
            "vat_rate": f"{vat}%",
            "chi_tiet_cac_thang": {
                f"Thang_{month:02d}": {
                    "san_luong_kwh": round(bill.get("tong_san_luong") or 0, 3),
                    "thanh_tien_vnd": int(bill.get("thanh_tien") or 0),
                    "thanh_tien_sau_thue_vnd": int(bill.get("thanh_tien_sau_thue") or 0),
                }
                for (year, month), bill in sorted(self.manager.months.items()) if year == self.year
            },
        }


class ConsumptionTotalSensor(ConsumptionBase):
    _attr_device_class = SensorDeviceClass.ENERGY
    # Revisions to historical days can lower totals; TOTAL_INCREASING would
    # create fictitious energy usage in long-term statistics after a correction.
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, manager: ConsumptionSensorManager) -> None:
        super().__init__(manager, f"{manager.friendly_name} Total All Time", "total_all_time")

    @property
    def native_value(self) -> float | None:
        if not self.manager.ready:
            return None
        return round(self.manager.total.get("tong_san_luong") or 0, 3)

    @property
    def extra_state_attributes(self) -> dict:
        row = self.manager.total
        if not row:
            return {"chi_tiet_tung_nam": {}}
        vat = row.get("vat") if row.get("vat") is not None else 8
        return {
            "tong_so_thang_du_lieu": row.get("tong_so_thang", 0),
            "thoi_diem_bat_dau": row.get("thoi_diem_bat_dau", "N/A"),
            "thoi_diem_ket_thuc": row.get("thoi_diem_ket_thuc", "N/A"),
            "tong_tien_tich_luy": int(row.get("tong_tien_tich_luy") or 0),
            "tong_tien_tich_luy_sau_thue": int(row.get("tong_tien_tich_luy_sau_thue") or 0),
            "current_vat_ref": f"{vat}%",
            "chi_tiet_tung_nam": {
                f"Nam_{year}": {
                    "tong_san_luong_kwh": round(bill.get("tong_san_luong") or 0, 3),
                    "tong_tien_vnd": int(bill.get("tong_tien") or 0),
                    "tong_tien_sau_thue_vnd": int(bill.get("tong_tien_sau_thue") or 0),
                }
                for year, bill in sorted(self.manager.years.items(), reverse=True)
            },
        }
