"""Configuration flow for Energy Bill."""

from homeassistant import config_entries

from .const import DOMAIN


class EnergyBillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Energy Bill configuration flow."""

    VERSION = 1
    MINOR_VERSION = 1
