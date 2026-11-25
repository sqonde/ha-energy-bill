"""Price sensors use dated tariffs even without recorder statistics."""

from datetime import UTC

from pytest_homeassistant.common import MockConfigEntry


async def test_price_sensors_exist_without_statistics(recorder_mock, hass):
    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.energy_bill_price_buy") is not None
    assert hass.states.get("sensor.energy_bill_price_sell") is not None


async def test_price_changes_at_local_midnight(recorder_mock, hass, freezer):
    from datetime import datetime

    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.helpers import issue_registry as ir
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant.common import async_fire_time_changed

    hass.config.time_zone = "Europe/Berlin"
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Berlin"))
    freezer.move_to("2030-03-31 21:59:59+00:00")
    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    for day, buy in (("2030-01-01", 0.3), ("2030-04-01", 0.4)):
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data={"valid_from": day, "buy": buy, "sell": 0.08, "base_year": 120},
                subentry_type="tariff",
                title=day,
                unique_id=None,
            ),
        )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.energy_bill_price_buy").state == "0.3"
    assert not ir.async_get(hass).async_get_issue(
        "energy_bill", f"no_tariff_{entry.entry_id}"
    )
    freezer.move_to("2030-03-31 22:00:00+00:00")
    async_fire_time_changed(hass, datetime(2030, 3, 31, 22, tzinfo=UTC))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.energy_bill_price_buy").state == "0.4"


async def test_missing_tariff_issue_clears_after_add(recorder_mock, hass, freezer):
    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.helpers import issue_registry as ir

    freezer.move_to("2030-01-01 12:00:00+00:00")
    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    issue_id = f"no_tariff_{entry.entry_id}"
    assert hass.states.get("sensor.energy_bill_price_buy").state == "unknown"
    assert ir.async_get(hass).async_get_issue("energy_bill", issue_id)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                "valid_from": "2030-01-01",
                "buy": 0.3,
                "sell": 0.08,
                "base_year": 120,
            },
            subentry_type="tariff",
            title="from 2030-01-01",
            unique_id=None,
        ),
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.energy_bill_price_buy").state == "0.3"
    assert not ir.async_get(hass).async_get_issue("energy_bill", issue_id)


async def test_future_tariff_clears_issue_at_midnight(recorder_mock, hass, freezer):
    from datetime import UTC, datetime

    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.helpers import issue_registry as ir
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant.common import async_fire_time_changed

    hass.config.time_zone = "Europe/Berlin"
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Berlin"))
    freezer.move_to("2030-03-31 21:59:59+00:00")
    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                "valid_from": "2030-04-01",
                "buy": 0.4,
                "sell": 0.08,
                "base_year": 180,
            },
            subentry_type="tariff",
            title="from 2030-04-01",
            unique_id=None,
        ),
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    issue_id = f"no_tariff_{entry.entry_id}"
    assert hass.states.get("sensor.energy_bill_price_buy").state == "unknown"
    assert ir.async_get(hass).async_get_issue("energy_bill", issue_id)
    freezer.move_to("2030-03-31 22:00:00+00:00")
    async_fire_time_changed(hass, datetime(2030, 3, 31, 22, tzinfo=UTC))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.energy_bill_price_buy").state == "0.4"
    assert not ir.async_get(hass).async_get_issue("energy_bill", issue_id)


def test_price_sensors_do_not_poll():
    from custom_components.energy_bill.sensor import PriceSensor

    entry = MockConfigEntry(domain="energy_bill")
    assert not PriceSensor(entry, "buy").should_poll
    assert not PriceSensor(entry, "sell").should_poll


async def test_german_price_sensor_name(recorder_mock, hass):
    hass.config.language = "de"
    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    states = hass.states.async_all("sensor")
    assert any(
        state.attributes["friendly_name"] == "Energy Bill Bezugspreis"
        for state in states
    )
