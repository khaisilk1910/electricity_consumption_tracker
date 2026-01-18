import sqlite3
import datetime
import os
import logging
from datetime import timedelta
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, PRICE_HISTORY, CONF_FRIENDLY_NAME

async def async_setup_entry(hass, entry):
    db_dir = hass.config.path(f"custom_components/{DOMAIN}")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    db_path = os.path.join(db_dir, f"tracker_{entry.entry_id}.db")
    
    # Lấy interval từ Options nếu có, nếu không lấy từ Data gốc
    interval = entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 1))

    # Đăng ký Device để hiển thị trong giao diện
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data[CONF_FRIENDLY_NAME],
        model="Electricity Tracker V1",
        manufacturer="Tongou Tracker",
        sw_version=entry.version,
    )

    # ... (Giữ nguyên phần init_db và calculate_cost)

    async def update_data(now=None):
        # Logic cập nhật dữ liệu giữ nguyên như cũ
        pass

    # Theo dõi thay đổi cấu hình (Options)
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    entry.async_on_unload(async_track_time_interval(hass, update_data, timedelta(hours=interval)))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def update_listener(hass, entry):
    """Cập nhật lại khi người dùng thay đổi Options."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
