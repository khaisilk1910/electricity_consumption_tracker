import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_UPDATE_INTERVAL, CONF_FRIENDLY_NAME

class ConsumptionTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_FRIENDLY_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_FRIENDLY_NAME): str,
                vol.Required(CONF_SOURCE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default=1): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=24, step=1, unit_of_measurement="giờ")
                ),
            })
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ConsumptionTrackerOptionsFlowHandler(config_entry)

class ConsumptionTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_UPDATE_INTERVAL, 
                        self.config_entry.data.get(CONF_UPDATE_INTERVAL, 1)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=24, step=1, unit_of_measurement="giờ")
                ),
            })
        )
