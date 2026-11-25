"""Energy Bill integration."""

from homeassistant.const import Platform

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
