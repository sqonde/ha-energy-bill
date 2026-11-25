"""Current electricity prices."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import tariffs_from_entry
from .const import DOMAIN
from .coordinator import EnergyBillCoordinator
from .tariffs import tariff_on


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up current price sensors."""
    async_add_entities([PriceSensor(entry, kind) for kind in ("buy", "sell")])
    coordinator = EnergyBillCoordinator(hass, entry)
    await coordinator.async_refresh()
    async_add_entities(
        [
            MonthSensor(coordinator, entry, kind)
            for kind in (
                "import_kwh",
                "supplier_cost",
                "supplier_cost_to_date",
                "feed_in",
                "prepay",
            )
        ]
    )


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


class MonthSensor(CoordinatorEntity, SensorEntity):
    """Projected month total."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, kind):
        super().__init__(coordinator)
        self.kind = kind
        key = "import" if kind == "import_kwh" else kind
        self._attr_unique_id = f"{entry.entry_id}_month_{key}"
        self._attr_translation_key = f"month_{key}"
        self._attr_device_class = (
            SensorDeviceClass.ENERGY
            if kind == "import_kwh"
            else SensorDeviceClass.MONETARY
        )
        self._attr_native_unit_of_measurement = (
            UnitOfEnergy.KILO_WATT_HOUR
            if kind == "import_kwh"
            else coordinator.hass.config.currency
        )

    @property
    def native_value(self):
        return (
            getattr(self.coordinator.data, self.kind) if self.coordinator.data else None
        )

    @property
    def extra_state_attributes(self):
        return (
            {"measured_days": self.coordinator.data.measured_days}
            if self.coordinator.data
            else {}
        )
