"""Tests for integration setup and migration."""

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant.common import MockConfigEntry

from custom_components.energy_bill import async_migrate_entry


async def test_setup_and_unload(recorder_mock, hass):
    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_migrate_entry_v1_noop(hass):
    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    assert await async_migrate_entry(hass, entry)
