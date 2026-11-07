"""Electricity Consumption Tracker integration for Home Assistant 2026.11+."""
from __future__ import annotations

from datetime import date, timedelta
import sqlite3
import logging
import math
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BILLING_DAY, CONF_FRIENDLY_NAME, CONF_SOURCE_DAY_OFFSET,
    CONF_SOURCE_SENSOR, CONF_START_DATE_APPLY, CONF_UPDATE_INTERVAL,
    DEFAULT_APPLY_DATE, DOMAIN,
)
from .storage import ElectricityStore

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]
VERSION = "2026.11.1"
CARD_URL = "/electricity_consumption_ui/electricity-consumption-card.js"
CARD_RESOURCE = f"{CARD_URL}?v={VERSION}"

SERVICE_OVERRIDE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("date"): vol.Any(cv.date, cv.datetime),
    vol.Required("value"): vol.All(vol.Coerce(float), vol.Range(min=0)),
})


def _entry_settings(entry: ConfigEntry) -> tuple[int, date, int]:
    settings = {**entry.data, **entry.options}
    billing_day = int(settings.get(CONF_BILLING_DAY, 1))
    apply_date = date.fromisoformat(str(settings.get(CONF_START_DATE_APPLY, DEFAULT_APPLY_DATE)))
    offset = int(settings.get(CONF_SOURCE_DAY_OFFSET, 0))
    if not 1 <= billing_day <= 28 or offset not in (0, 1):
        raise ValueError("Invalid billing day or source day offset")
    return billing_day, apply_date, offset


async def _register_card_resource(hass: HomeAssistant) -> None:
    """Register one resource for all entries; never touch resources per entry."""
    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        mode = getattr(lovelace, "resource_mode", None)
        if resources and mode != "yaml":
            # First load the collection before examining or modifying it.
            # Avoids overwriting lazily initialized Lovelace resource storage.
            await resources.async_get_info()
            matches = [item for item in resources.async_items()
                       if item.get("url", "").split("?", 1)[0] == CARD_URL]
            if matches:
                existing = matches[0]
                if existing.get("url") != CARD_RESOURCE or existing.get("type", existing.get("res_type")) != "module":
                    await resources.async_update_item(existing["id"], {"url": CARD_RESOURCE, "res_type": "module"})
                    _LOGGER.info("Updated Lovelace card resource to %s", CARD_RESOURCE)
                if len(matches) > 1:
                    _LOGGER.warning("Found %d duplicate Electricity Tracker resources; remove extras from Dashboard resources", len(matches))
                return
            await resources.async_create_item({"url": CARD_RESOURCE, "res_type": "module"})
            _LOGGER.info("Registered Lovelace card resource: %s", CARD_RESOURCE)
        else:
            # YAML resource mode cannot be modified using the resource collection.
            # HA global frontend fallback registers the card once at startup.
            add_extra_js_url(hass, CARD_RESOURCE)
            _LOGGER.debug("Registered card as frontend extra JS (Lovelace YAML mode)")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, HomeAssistantError):
        _LOGGER.exception("Automatic card registration failed. Add %s as JavaScript module under Dashboard resources", CARD_RESOURCE)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the bundled frontend and service without per-entry I/O."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            "/electricity_consumption_ui",
            str(Path(__file__).parent / "frontend"),
            False,
        )
    ])
    async def _override_service(call: ServiceCall) -> None:
        await _handle_override(hass, call)

    hass.services.async_register(
        DOMAIN, "override_data", _override_service, schema=SERVICE_OVERRIDE_SCHEMA,
    )
    hass.async_create_background_task(
        _register_card_resource(hass), f"{DOMAIN} register card", eager_start=False
    )
    return True


async def _handle_override(hass: HomeAssistant, call: ServiceCall) -> None:
    """Validate and serialize manual historical daily readings."""
    entry_id = call.data["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)
    instance = hass.data.get(DOMAIN, {}).get(entry_id)
    if entry is None or entry.domain != DOMAIN or instance is None:
        raise HomeAssistantError(f"Electricity tracker entry not loaded: {entry_id}")
    value = float(call.data["value"])
    if not math.isfinite(value) or value < 0:
        raise HomeAssistantError("Daily kWh must be a non-negative finite number")
    raw_date = call.data["date"]
    if isinstance(raw_date, str):
        target_day = date.fromisoformat(raw_date[:10])
    elif hasattr(raw_date, "date"):
        target_day = raw_date.date()
    else:
        target_day = raw_date
    if target_day > dt_util.now().date():
        raise HomeAssistantError("Cannot override a future day")
    billing_day, apply_date, _ = _entry_settings(entry)
    changed = await instance["store"].async_write(target_day, value, billing_day, apply_date)
    if changed:
        if instance.get("manager"):
            await instance["manager"].async_refresh()
        _LOGGER.info("Manual override: entry=%s date=%s kWh=%.3f", entry_id, target_day, value)
    else:
        _LOGGER.debug("Manual override identical to existing reading: entry=%s date=%s", entry_id, target_day)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up one tracker; background data loads do not block HA startup."""
    storage_dir = Path(hass.config.path("electricity_consumption_tracker"))
    store = ElectricityStore(hass, storage_dir / f"electricity_data_{entry.entry_id}.db")
    # Schema creation is a small executor job. Entity setup must not race schema creation.
    await store.async_initialize()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "store": store, "manager": None, "last_source_warning": None,
    }
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_FRIENDLY_NAME, "Electricity Tracker"),
        manufacturer="Khaisilk1910",
        model="Electricity Consumption Tracker",
        sw_version=VERSION,
    )
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise

    async def _read_source(now=None) -> None:
        instance = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if instance is None:
            return
        settings = {**entry.data, **entry.options}
        entity_id = settings[CONF_SOURCE_SENSOR]
        sensor = hass.states.get(entity_id)
        warning = None
        kwh = None
        if sensor is None or sensor.state in ("unknown", "unavailable", "none", ""):
            warning = f"Source sensor {entity_id} is unavailable; no data written"
        else:
            try:
                kwh = float(sensor.state)
                unit = (sensor.attributes.get("unit_of_measurement") or "kWh").strip()
                if unit == "Wh":
                    kwh /= 1000
                elif unit != "kWh":
                    warning = f"Source {entity_id} reports unit {unit!r}; expected daily kWh/Wh"
                if kwh is None or not math.isfinite(kwh) or kwh < 0:
                    warning = f"Source {entity_id} has non-finite or negative reading: {sensor.state!r}"
            except (ValueError, TypeError, OverflowError):
                warning = f"Source {entity_id} has non-numeric reading: {sensor.state!r}"
        if warning:
            if instance["last_source_warning"] != warning:
                _LOGGER.warning("%s", warning)
                instance["last_source_warning"] = warning
            return
        instance["last_source_warning"] = None
        try:
            billing_day, apply_date, day_offset = _entry_settings(entry)
            target_date = dt_util.now().date() - timedelta(days=day_offset)
            changed = await store.async_write(target_date, kwh, billing_day, apply_date)
            if changed:
                _LOGGER.debug("Saved daily data: entry=%s source=%s date=%s kWh=%.3f", entry.entry_id, entity_id, target_date, kwh)
                if instance.get("manager"):
                    await instance["manager"].async_refresh()
        except (OSError, ValueError, TypeError, sqlite3.Error):
            _LOGGER.exception("Could not save daily source: entry=%s sensor=%s", entry.entry_id, entity_id)

    interval = int(entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1)))
    entry.async_on_unload(async_track_time_interval(hass, _read_source, timedelta(hours=interval)))
    entry.async_on_unload(async_track_time_change(hass, _read_source, hour=23, minute=59, second=55))

    async def _load_initial_data() -> None:
        try:
            billing_day, apply_date, _ = _entry_settings(entry)
            rebuilt = await store.async_rebuild_if_needed(billing_day, apply_date)
            if rebuilt:
                _LOGGER.info("Billing history synchronized for entry %s", entry.entry_id)
            await _read_source()
            instance = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if instance and instance.get("manager"):
                await instance["manager"].async_refresh()
        except Exception:
            _LOGGER.exception("Initial tracker data load failed for entry %s", entry.entry_id)

    entry.async_create_background_task(
        hass, _load_initial_data(), f"{DOMAIN} initial data", eager_start=False
    )
    _LOGGER.info("Tracker loaded: entry=%s source=%s interval=%sh", entry.entry_id,
                 entry.options.get(CONF_SOURCE_SENSOR, entry.data.get(CONF_SOURCE_SENSOR)), interval)
    return


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Unload sensors, scheduled callbacks and entry-scoped background tasks."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
