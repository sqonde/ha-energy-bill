"""Current electricity prices."""

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import tariffs_from_entry
from .const import DOMAIN
from .tariffs import tariff_on


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up current price sensors."""
    async_add_entities([PriceSensor(entry, kind) for kind in ("buy", "sell")])


class PriceSensor(SensorEntity):
    """Price valid on the current local day."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry, kind):
        self.entry = entry
        self.kind = kind
        self._attr_unique_id = f"{entry.entry_id}_price_{kind}"
        self._attr_translation_key = f"price_{kind}"

    async def async_added_to_hass(self):
        self._attr_native_unit_of_measurement = f"{self.hass.config.currency}/kWh"
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._midnight, hour=0, minute=0, second=0
            )
        )
        self._refresh()

    @callback
    def _midnight(self, now):
        self._refresh()
        self.async_write_ha_state()

    def _refresh(self):
        tariff = tariff_on(tariffs_from_entry(self.entry), dt_util.now().date())
        issue_id = f"no_tariff_{self.entry.entry_id}"
        if tariff is None:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="no_tariff",
                config_entry_id=self.entry.entry_id,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._attr_native_value = getattr(tariff, self.kind) if tariff else None
