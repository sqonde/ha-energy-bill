"""Diagnostics for Energy Bill."""


async def async_get_config_entry_diagnostics(hass, entry):
    """Return entry and subentry configuration."""
    return {
        "entry": dict(entry.data),
        "subentries": [
            {"type": item.subentry_type, "title": item.title, "data": dict(item.data)}
            for item in entry.subentries.values()
        ],
    }
