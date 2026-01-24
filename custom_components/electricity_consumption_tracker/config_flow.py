"""Config flow for Electricity Consumption Tracker."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.util.dt as dt_util # Import này quan trọng
from .const import (
    DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, CONF_FRIENDLY_NAME,
    CONF_BILLING_DAY, CONF_START_DATE_APPLY
)

class ConsumptionTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_FRIENDLY_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_FRIENDLY_NAME, default="Electricity Home"): str,
                vol.Required(CONF_SOURCE_SENSOR): selector.EntitySelector({
                    "domain": "sensor"
                }),
                vol.Required(CONF_UPDATE_INTERVAL, default=1): selector.NumberSelector({
                    "min": 1, "max": 24, "step": 1, "unit_of_measurement": "giờ", "mode": "box"
                }),
                vol.Required(CONF_BILLING_DAY, default=1): selector.NumberSelector({
                    "min": 1, "max": 28, "step": 1, "mode": "box"
                }),
                # Default ngày hiện tại
                vol.Required(CONF_START_DATE_APPLY, default=dt_util.now().strftime("%Y-%m-%d")): selector.DateSelector(),
            }),
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ConsumptionTrackerOptionsFlowHandler(config_entry)

class ConsumptionTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry 

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            CONF_UPDATE_INTERVAL, self._config_entry.data.get(CONF_UPDATE_INTERVAL, 1)
        )
        current_sensor = self._config_entry.options.get(
            CONF_SOURCE_SENSOR, self._config_entry.data.get(CONF_SOURCE_SENSOR)
        )
        current_billing_day = self._config_entry.options.get(
            CONF_BILLING_DAY, self._config_entry.data.get(CONF_BILLING_DAY, 1)
        )
        current_start_date = self._config_entry.options.get(
            CONF_START_DATE_APPLY, self._config_entry.data.get(CONF_START_DATE_APPLY, dt_util.now().strftime("%Y-%m-%d"))
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SOURCE_SENSOR, default=current_sensor): selector.EntitySelector({
                    "domain": "sensor"
                }),
                vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): selector.NumberSelector({
                    "min": 1, "max": 24, "step": 1, "unit_of_measurement": "giờ", "mode": "box"
                }),
                vol.Required(CONF_BILLING_DAY, default=current_billing_day): selector.NumberSelector({
                    "min": 1, "max": 28, "step": 1, "mode": "box"
                }),
                vol.Required(CONF_START_DATE_APPLY, default=current_start_date): selector.DateSelector(),
            })
        )
