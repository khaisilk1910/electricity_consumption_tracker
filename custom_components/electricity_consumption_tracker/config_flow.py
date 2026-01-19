"""Config flow for Electricity Consumption Tracker."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, CONF_FRIENDLY_NAME

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
                    "min": 1,
                    "max": 24,
                    "step": 1,
                    "unit_of_measurement": "giờ",
                    "mode": "box"
                }),
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

        
        current_val = self._config_entry.options.get(
            CONF_UPDATE_INTERVAL, self._config_entry.data.get(CONF_UPDATE_INTERVAL, 1)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_UPDATE_INTERVAL, default=current_val): selector.NumberSelector({
                    "min": 1,
                    "max": 24,
                    "step": 1,
                    "unit_of_measurement": "giờ",
                    "mode": "box"
                }),
            })
        )
