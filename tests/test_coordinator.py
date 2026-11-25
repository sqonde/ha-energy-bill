from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.components.recorder.common import async_wait_recording_done

from custom_components.energy_bill.coordinator import EnergyBillCoordinator


async def test_daily_statistics_across_dst(recorder_mock, hass, freezer):
    hass.config.time_zone = "Europe/Berlin"
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Berlin"))
    freezer.move_to("2030-11-01 12:00:00+00:00")
    metadata = {
        "has_mean": False,
        "has_sum": True,
        "mean_type": 0,
        "name": "Grid",
        "source": "recorder",
        "statistic_id": "sensor.grid",
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
    }
    start = datetime(2030, 10, 24, 22, tzinfo=UTC)
    async_import_statistics(
        hass,
        metadata,
        [
            {"start": start + timedelta(hours=i), "state": i, "sum": i}
            for i in range(169)
        ],
    )
    await async_wait_recording_done(hass)
    entry = MockConfigEntry(domain="energy_bill", data={"import_stat": "sensor.grid"})
    coordinator = EnergyBillCoordinator(hass, entry)
    await coordinator.async_refresh()
    days = {item.day.isoformat(): item.import_kwh for item in coordinator.days}
    assert days["2030-10-26"] == 24
    assert days["2030-10-27"] == 25
    assert days["2030-10-28"] == 24


async def test_month_sensors_show_projection(recorder_mock, hass, freezer):
    from homeassistant.config_entries import ConfigSubentry

    hass.config.time_zone = "UTC"
    dt_util.set_default_time_zone(dt_util.UTC)
    freezer.move_to("2030-04-16 12:00:00+00:00")
    metadata = {
        "has_mean": False,
        "has_sum": True,
        "mean_type": 0,
        "name": "Grid",
        "source": "recorder",
        "statistic_id": "sensor.grid",
        "unit_of_measurement": "Wh",
        "unit_class": "energy",
    }
    start = datetime(2030, 3, 17, tzinfo=UTC)
    async_import_statistics(
        hass,
        metadata,
        [
            {"start": start + timedelta(hours=i), "state": i * 1000, "sum": i * 1000}
            for i in range(30 * 24)
        ],
    )
    async_import_statistics(
        hass,
        metadata | {"statistic_id": "sensor.export"},
        [
            {"start": start + timedelta(hours=i), "state": i * 500, "sum": i * 500}
            for i in range(30 * 24)
        ],
    )
    await async_wait_recording_done(hass)
    entry = MockConfigEntry(
        domain="energy_bill",
        version=1,
        minor_version=1,
        data={"import_stat": "sensor.grid", "export_stat": "sensor.export"},
    )
    entry.add_to_hass(hass)
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
            title="tariff",
            unique_id=None,
        ),
    )
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                "valid_from": "2030-01-01",
                "amount": 100,
                "due_day": 15,
                "skip_months": [],
            },
            subentry_type="prepayment",
            title="prepayment",
            unique_id=None,
        ),
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_bill_month_import")
    assert float(state.state) == 720
    assert state.attributes["measured_days"] == 15
    assert float(
        hass.states.get("sensor.energy_bill_month_supplier_cost").state
    ) == pytest.approx(225.8630136986)
    assert float(
        hass.states.get("sensor.energy_bill_month_feed_in").state
    ) == pytest.approx(28.8)
    assert float(hass.states.get("sensor.energy_bill_month_prepayment").state) == 100


async def test_october_projection_includes_dst_day(recorder_mock, hass, freezer):
    from homeassistant.config_entries import ConfigSubentry

    hass.config.time_zone = "Europe/Berlin"
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Berlin"))
    freezer.move_to("2030-10-29 12:00:00+00:00")
    metadata = {
        "has_mean": False,
        "has_sum": True,
        "mean_type": 0,
        "name": "Grid",
        "source": "recorder",
        "statistic_id": "sensor.grid",
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
    }
    start = datetime(2030, 9, 29, 22, tzinfo=UTC)
    async_import_statistics(
        hass,
        metadata,
        [
            {"start": start + timedelta(hours=i), "state": i, "sum": i}
            for i in range(29 * 24 + 1)
        ],
    )
    await async_wait_recording_done(hass)
    entry = MockConfigEntry(domain="energy_bill", data={"import_stat": "sensor.grid"})
    entry.add_to_hass(hass)
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
            title="tariff",
            unique_id=None,
        ),
    )
    coordinator = EnergyBillCoordinator(hass, entry)
    await coordinator.async_refresh()
    assert coordinator.data.measured_days == 28
    assert coordinator.data.import_kwh == pytest.approx(745.107142857)
    assert (
        next(
            d.import_kwh for d in coordinator.days if d.day.isoformat() == "2030-10-27"
        )
        == 25
    )


async def test_read_failure_keeps_price_available(recorder_mock, hass, freezer):
    from unittest.mock import patch

    from homeassistant.config_entries import ConfigSubentry

    freezer.move_to("2030-04-16 12:00:00+00:00")
    entry = MockConfigEntry(
        domain="energy_bill",
        version=1,
        minor_version=1,
        data={"import_stat": "sensor.grid"},
    )
    entry.add_to_hass(hass)
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
            title="tariff",
            unique_id=None,
        ),
    )
    with patch(
        "custom_components.energy_bill.coordinator.statistics_during_period",
        side_effect=RuntimeError("read failed"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get("sensor.energy_bill_price_buy").state == "0.3"
    assert hass.states.get("sensor.energy_bill_month_import").state == "unavailable"


async def test_period_sensor_includes_opening_balance(recorder_mock, hass, freezer):
    from homeassistant.config_entries import ConfigSubentry

    hass.config.time_zone = "UTC"
    dt_util.set_default_time_zone(dt_util.UTC)
    freezer.move_to("2030-04-16 12:00:00+00:00")
    metadata = {
        "has_mean": False,
        "has_sum": True,
        "mean_type": 0,
        "name": "Grid",
        "source": "recorder",
        "statistic_id": "sensor.grid",
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
    }
    start = datetime(2030, 2, 14, tzinfo=UTC)
    async_import_statistics(
        hass,
        metadata,
        [
            {"start": start + timedelta(hours=i), "state": i, "sum": i}
            for i in range(61 * 24)
        ],
    )
    await async_wait_recording_done(hass)
    entry = MockConfigEntry(
        domain="energy_bill",
        version=1,
        minor_version=1,
        data={"import_stat": "sensor.grid"},
    )
    entry.add_to_hass(hass)
    for kind, data in (
        (
            "tariff",
            {"valid_from": "2030-01-01", "buy": 0.3, "sell": 0.08, "base_year": 0},
        ),
        ("billing_period", {"start": "2030-04-01", "opening_balance": 25}),
    ):
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(data=data, subentry_type=kind, title=kind, unique_id=None),
        )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    cost = float(hass.states.get("sensor.energy_bill_period_supplier_cost").state)
    balance = hass.states.get("sensor.energy_bill_period_balance")
    assert float(balance.state) == pytest.approx(25 - cost)
    assert balance.attributes["measured_days"] == 15
    assert "modelled_days" in balance.attributes["incomplete_reasons"]


async def test_first_meter_statistic_backfills_start_reading(
    recorder_mock, hass, freezer
):
    from datetime import date

    from homeassistant.config_entries import ConfigSubentry

    from custom_components.energy_bill.projection import project_period
    from custom_components.energy_bill.tariffs import Tariff

    hass.config.time_zone = "UTC"
    dt_util.set_default_time_zone(dt_util.UTC)
    freezer.move_to("2030-04-05 12:00:00+00:00")
    metadata = {
        "has_mean": False,
        "has_sum": True,
        "mean_type": 0,
        "name": "Grid",
        "source": "recorder",
        "statistic_id": "sensor.grid",
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
    }
    start = datetime(2030, 4, 4, tzinfo=UTC)
    async_import_statistics(
        hass,
        metadata,
        [
            {"start": start + timedelta(hours=i), "state": 130 + i, "sum": 130 + i}
            for i in range(24)
        ],
    )
    await async_wait_recording_done(hass)
    entry = MockConfigEntry(domain="energy_bill", data={"import_stat": "sensor.grid"})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={"start": "2030-04-01", "start_reading_kwh": 100},
            subentry_type="billing_period",
            title="period",
            unique_id=None,
        ),
    )
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={"valid_from": "2030-04-01", "buy": 0.3, "sell": 0, "base_year": 0},
            subentry_type="tariff",
            title="tariff",
            unique_id=None,
        ),
    )
    coordinator = EnergyBillCoordinator(hass, entry)
    await coordinator.async_refresh()
    adjusted = [coordinator.days[0].__class__(date(2030, 4, 4), 23, 0, None)]
    expected = project_period(
        adjusted,
        [Tariff(date(2030, 4, 1), 0.3, 0, 0)],
        [],
        date(2030, 4, 1),
        date(2031, 4, 1),
        None,
        date(2030, 4, 5),
        100,
        first_statistic_state=130,
    )
    assert coordinator.period.import_kwh == pytest.approx(expected.import_kwh)
