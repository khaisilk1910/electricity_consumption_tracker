"""UI configuration and options flow for Electricity Consumption Tracker."""
from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BILLING_DAY, CONF_FRIENDLY_NAME, CONF_SOURCE_DAY_OFFSET,
    CONF_SOURCE_SENSOR, CONF_START_DATE_APPLY, CONF_UPDATE_INTERVAL,
    DEFAULT_APPLY_DATE, DOMAIN,
)


def _schema(defaults: dict, *, initial: bool) -> vol.Schema:
    """Declare selectable settings with explicit ranges and correct defaults."""
    fields = {}
    if initial:
        fields[vol.Required(CONF_FRIENDLY_NAME, default=defaults.get(CONF_FRIENDLY_NAME, "Electricity Home"))] = vol.All(
            str, vol.Strip(), vol.Length(min=1, max=80))
    fields[vol.Required(CONF_SOURCE_SENSOR, default=defaults.get(CONF_SOURCE_SENSOR, vol.UNDEFINED))] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor"))
    fields[vol.Required(CONF_UPDATE_INTERVAL, default=defaults.get(CONF_UPDATE_INTERVAL, 1))] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=1, max=24, step=1, mode="box", unit_of_measurement="h"))
    fields[vol.Required(CONF_BILLING_DAY, default=defaults.get(CONF_BILLING_DAY, 1))] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=1, max=28, step=1, mode="box"))
    fields[vol.Required(CONF_START_DATE_APPLY, default=defaults.get(CONF_START_DATE_APPLY, DEFAULT_APPLY_DATE))] = selector.DateSelector()
    fields[vol.Required(CONF_SOURCE_DAY_OFFSET, default=defaults.get(CONF_SOURCE_DAY_OFFSET, 0))] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=0, max=1, step=1, mode="box"))
    return vol.Schema(fields)


def _validate_user_input(values: dict) -> str | None:
    try:
        date.fromisoformat(values[CONF_START_DATE_APPLY])
        if int(values[CONF_BILLING_DAY]) not in range(1, 29):
            return "invalid_day"
        if int(values[CONF_SOURCE_DAY_OFFSET]) not in (0, 1):
            return "invalid_day"
        if not 1 <= int(values[CONF_UPDATE_INTERVAL]) <= 24:
            return "invalid_interval"
    except (ValueError, TypeError, KeyError):
        return "invalid_date"
    return None


class ConsumptionTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """New trackers may be created for any number of independent sources."""

    # Existing entries were created with version 1; no breaking data migration is needed.
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if error := _validate_user_input(user_input):
                errors["base"] = error
            else:
                return self.async_create_entry(title=user_input[CONF_FRIENDLY_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}, initial=True), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ConsumptionTrackerOptionsFlow()


class ConsumptionTrackerOptionsFlow(config_entries.OptionsFlowWithReload):
    """Allow source, period, and date offset changes with automatic reload."""

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            if error := _validate_user_input(user_input):
                errors["base"] = error
            else:
                return self.async_create_entry(title="", data=user_input)
        entry = self.config_entry
        defaults = {**entry.data, **entry.options, **(user_input or {})}
        return self.async_show_form(step_id="init", data_schema=_schema(defaults, initial=False), errors=errors)
