"""Energy Bill integration."""

from datetime import date

from homeassistant.const import Platform

from .tariffs import Prepayment, Tariff

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    """Set up an entry and reload when it changes."""
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass, entry):
    """Accept the initial entry version."""
    return entry.version == 1 and entry.minor_version == 1


def tariffs_from_entry(entry):
    """Read tariff subentries."""
    return [
        Tariff(
            date.fromisoformat(item.data["valid_from"]),
            item.data["buy"],
            item.data["sell"],
            item.data["base_year"],
        )
        for item in entry.subentries.values()
        if item.subentry_type == "tariff"
    ]


def prepayments_from_entry(entry):
    """Read prepayment subentries."""
    return [
        Prepayment(
            date.fromisoformat(item.data["valid_from"]),
            item.data["amount"],
            item.data["due_day"],
            frozenset(item.data.get("skip_months", [])),
        )
        for item in entry.subentries.values()
        if item.subentry_type == "prepayment"
    ]


def periods_from_entry(entry):
    """Read billing periods with dates converted for calculations."""
    return [
        dict(item.data) | {"start": date.fromisoformat(item.data["start"])}
        for item in entry.subentries.values()
        if item.subentry_type == "billing_period"
    ]
