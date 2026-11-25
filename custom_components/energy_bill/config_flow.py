"""Configuration flow for Energy Bill."""

from functools import partial

import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.components.energy import async_get_manager
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_metadata
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    DateSelector,
    NumberSelector,
    ObjectSelector,
    SelectSelector,
    StatisticSelector,
)

from .const import DOMAIN
from .pvgis import async_fetch_pvgis


class EnergyBillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Energy Bill configuration flow."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return EnergyBillOptionsFlow()

    @classmethod
    def async_get_supported_subentry_types(cls, config_entry):
        return {
            "tariff": TariffFlow,
            "prepayment": PrepaymentFlow,
            "billing_period": PeriodFlow,
        }

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            ids = set(user_input.values())
            metadata = await get_instance(self.hass).async_add_executor_job(
                partial(get_metadata, self.hass, statistic_ids=ids)
            )
            if ids <= metadata.keys():
                return self.async_create_entry(title="Energy Bill", data=user_input)
            errors["base"] = "no_statistics"
        manager = await async_get_manager(self.hass)
        defaults = {}
        for source in (manager.data or {}).get("energy_sources", []) if manager else []:
            if source["type"] == "grid":
                defaults.setdefault("import_stat", source.get("stat_energy_from"))
                defaults.setdefault("export_stat", source.get("stat_energy_to"))
            elif source["type"] == "solar":
                defaults.setdefault("solar_stat", source.get("stat_energy_from"))
        schema = vol.Schema(
            {
                vol.Required("import_stat"): StatisticSelector(),
                vol.Optional("export_stat"): StatisticSelector(),
                vol.Optional("solar_stat"): StatisticSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, defaults),
            errors=errors,
        )


class DatedFlow(config_entries.ConfigSubentryFlow):
    """Add or change a tariff."""

    async def async_step_user(self, user_input=None):
        return await self._step(user_input, False)

    async def async_step_reconfigure(self, user_input=None):
        return await self._step(user_input, True)

    async def _step(self, user_input, reconfigure):
        entry = self._get_entry()
        current = self._get_reconfigure_subentry() if reconfigure else None
        errors = {}
        if user_input is not None:
            if self.kind == "prepayment":
                user_input["skip_months"] = [
                    int(month) for month in user_input.get("skip_months", [])
                ]
            if any(
                item.subentry_type == self.kind
                and item is not current
                and item.data[self.date_key] == user_input[self.date_key]
                for item in entry.subentries.values()
            ):
                errors["base"] = "duplicate_date"
            else:
                title = f"from {user_input[self.date_key]}"
                if current:
                    return self.async_update_and_abort(
                        entry, current, title=title, data=user_input
                    )
                return self.async_create_entry(title=title, data=user_input)
        schema = self.schema
        suggested = dict(current.data) if current else {}
        if self.kind == "prepayment" and "skip_months" in suggested:
            suggested["skip_months"] = [
                str(month) for month in suggested["skip_months"]
            ]
        return self.async_show_form(
            step_id="reconfigure" if reconfigure else "user",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )


positive = vol.All(vol.Coerce(float), vol.Range(min=0))


class TariffFlow(DatedFlow):
    kind = "tariff"
    date_key = "valid_from"
    schema = vol.Schema(
        {
            vol.Required("valid_from"): DateSelector(),
            vol.Required("buy"): positive,
            vol.Required("sell"): positive,
            vol.Required("base_year"): positive,
        }
    )


class PrepaymentFlow(DatedFlow):
    kind = "prepayment"
    date_key = "valid_from"
    schema = vol.Schema(
        {
            vol.Required("valid_from"): DateSelector(),
            vol.Required("amount"): positive,
            vol.Required("due_day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=28)),
            vol.Optional("skip_months", default=[]): SelectSelector(
                {"options": [str(i) for i in range(1, 13)], "multiple": True}
            ),
        }
    )


class PeriodFlow(DatedFlow):
    kind = "billing_period"
    date_key = "start"
    schema = vol.Schema(
        {
            vol.Required("start"): DateSelector(),
            vol.Optional("start_reading_kwh"): positive,
            vol.Optional("opening_balance"): vol.Coerce(float),
        }
    )


class EnergyBillOptionsFlow(config_entries.OptionsFlow):
    """Configure solar planes and retrieve their monthly yield."""

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            planes = user_input["planes"]
            try:
                months = (
                    await async_fetch_pvgis(
                        async_get_clientsession(self.hass),
                        user_input["latitude"],
                        user_input["longitude"],
                        planes,
                    )
                    if planes
                    else None
                )
            except (
                ClientError,
                TimeoutError,
                ValueError,
                KeyError,
                TypeError,
                IndexError,
            ):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="", data={"planes": planes, "pv_month_kwh": months}
                )
        schema = vol.Schema(
            {
                vol.Required("latitude", default=self.hass.config.latitude): vol.All(
                    vol.Coerce(float), vol.Range(min=-90, max=90)
                ),
                vol.Required("longitude", default=self.hass.config.longitude): vol.All(
                    vol.Coerce(float), vol.Range(min=-180, max=180)
                ),
                vol.Required(
                    "planes", default=self.config_entry.options.get("planes", [])
                ): ObjectSelector(
                    {
                        "multiple": True,
                        "fields": {
                            "kwp": {
                                "label": "kWp",
                                "required": True,
                                "selector": NumberSelector(
                                    {"min": 0.001, "max": 1000000, "mode": "box"}
                                ),
                            },
                            "tilt": {
                                "label": "Tilt",
                                "required": True,
                                "selector": NumberSelector(
                                    {"min": 0, "max": 90, "mode": "box"}
                                ),
                            },
                            "azimuth": {
                                "label": "Azimuth",
                                "required": True,
                                "selector": NumberSelector(
                                    {"min": -180, "max": 180, "mode": "box"}
                                ),
                            },
                        },
                    }
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
