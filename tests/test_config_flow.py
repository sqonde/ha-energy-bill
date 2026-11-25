"""Configuration flows for Energy Bill."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from pytest_homeassistant.components.recorder.common import async_wait_recording_done


async def test_user_flow_requires_statistics(recorder_mock, hass):
    with patch(
        "custom_components.energy_bill.config_flow.async_get_manager",
        new=AsyncMock(return_value=None),
        create=True,
    ):
        result = await hass.config_entries.flow.async_init(
            "energy_bill", context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"import_stat": "sensor.missing"}
        )
    assert result["errors"]["base"] == "no_statistics"


async def test_add_tariff_and_reject_duplicate(recorder_mock, hass):
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    data = {"valid_from": "2030-04-01", "buy": 0.4, "sell": 0.08, "base_year": 180}
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "tariff"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], data
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "from 2030-04-01"
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "tariff"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], data
    )
    assert result["errors"]["base"] == "duplicate_date"


async def test_add_prepayment_and_period(recorder_mock, hass):
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    for kind, data in (
        (
            "prepayment",
            {
                "valid_from": "2030-04-01",
                "amount": 100,
                "due_day": 15,
                "skip_months": ["12"],
            },
        ),
        ("billing_period", {"start": "2030-04-01", "opening_balance": 0}),
    ):
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, kind), context={"source": "user"}
        )
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], data
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "from 2030-04-01"


async def test_diagnostics_include_subentries(recorder_mock, hass):
    from homeassistant.config_entries import ConfigSubentry
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.energy_bill.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = MockConfigEntry(domain="energy_bill", data={"import_stat": "sensor.grid"})
    entry.add_to_hass(hass)
    subentry = ConfigSubentry(
        data={"start": "2030-04-01"},
        subentry_type="billing_period",
        title="from 2030-04-01",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, subentry)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["entry"] == {"import_stat": "sensor.grid"}
    assert result["subentries"][0]["data"] == {"start": "2030-04-01"}


async def test_entry_helpers_convert_subentries(recorder_mock, hass):
    from datetime import date

    from homeassistant.config_entries import ConfigSubentry
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.energy_bill import periods_from_entry, prepayments_from_entry

    entry = MockConfigEntry(domain="energy_bill")
    entry.add_to_hass(hass)
    for kind, data in (
        (
            "prepayment",
            {
                "valid_from": "2030-04-01",
                "amount": 100,
                "due_day": 15,
                "skip_months": [12],
            },
        ),
        ("billing_period", {"start": "2030-04-01"}),
    ):
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(data=data, subentry_type=kind, title="test", unique_id=None),
        )
    prepay = prepayments_from_entry(entry)[0]
    assert prepay.valid_from == date(2030, 4, 1)
    assert prepay.skip_months == frozenset({12})
    assert periods_from_entry(entry)[0]["start"] == date(2030, 4, 1)


async def test_energy_preferences_prefill(recorder_mock, hass):
    from types import SimpleNamespace

    manager = SimpleNamespace(
        data={
            "energy_sources": [
                {
                    "type": "grid",
                    "stat_energy_from": "sensor.grid_in",
                    "stat_energy_to": "sensor.grid_out",
                },
                {"type": "solar", "stat_energy_from": "sensor.solar"},
            ]
        }
    )
    with patch(
        "custom_components.energy_bill.config_flow.async_get_manager",
        new=AsyncMock(return_value=manager),
    ):
        result = await hass.config_entries.flow.async_init(
            "energy_bill", context={"source": "user"}
        )
    fields = {
        key.schema: key.description.get("suggested_value")
        for key in result["data_schema"].schema
    }
    assert fields == {
        "import_stat": "sensor.grid_in",
        "export_stat": "sensor.grid_out",
        "solar_stat": "sensor.solar",
    }


async def test_reconfigure_and_delete_each_subentry(recorder_mock, hass):
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill", version=1, minor_version=1)
    entry.add_to_hass(hass)
    for kind, data, key in (
        (
            "tariff",
            {"valid_from": "2030-04-01", "buy": 0.4, "sell": 0.08, "base_year": 180},
            "valid_from",
        ),
        (
            "prepayment",
            {
                "valid_from": "2030-04-01",
                "amount": 100,
                "due_day": 15,
                "skip_months": ["12"],
            },
            "valid_from",
        ),
        ("billing_period", {"start": "2030-04-01"}, "start"),
    ):
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, kind), context={"source": "user"}
        )
        await hass.config_entries.subentries.async_configure(result["flow_id"], data)
        subentry = next(
            item for item in entry.subentries.values() if item.subentry_type == kind
        )
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, kind),
            context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
        )
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], data | {key: "2030-05-01"}
        )
        assert result["type"] == "abort"
        assert subentry.data[key] == "2030-05-01"
        assert subentry.title == "from 2030-05-01"
        assert hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
        assert subentry.subentry_id not in entry.subentries


async def test_prepayment_accepts_month_selection(recorder_mock, hass):
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill")
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "prepayment"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "valid_from": "2030-04-01",
            "amount": 100,
            "due_day": 15,
            "skip_months": ["12"],
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"]["skip_months"] == [12]


async def test_prepayment_form_can_be_rendered(recorder_mock, hass):
    import probatio
    from homeassistant.helpers import config_validation as cv
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill")
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "prepayment"), context={"source": "user"}
    )
    fields = probatio.to_field_list(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    assert next(field for field in fields if field["name"] == "skip_months")[
        "selector"
    ]["select"]["multiple"]


async def test_negative_tariff_price_is_rejected(recorder_mock, hass):
    import pytest
    import voluptuous as vol
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill")
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "tariff"), context={"source": "user"}
    )
    with pytest.raises(vol.Invalid):
        await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {"valid_from": "2030-04-01", "buy": -0.1, "sell": 0.08, "base_year": 120},
        )
    assert not entry.subentries


async def test_duplicate_dates_for_prepayment_and_period(recorder_mock, hass):
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill")
    entry.add_to_hass(hass)
    for kind, data in (
        ("prepayment", {"valid_from": "2030-04-01", "amount": 100, "due_day": 15}),
        ("billing_period", {"start": "2030-04-01"}),
    ):
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, kind), context={"source": "user"}
        )
        await hass.config_entries.subentries.async_configure(result["flow_id"], data)
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, kind), context={"source": "user"}
        )
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], data
        )
        assert result["errors"]["base"] == "duplicate_date"


async def test_user_flow_accepts_recorded_statistic(recorder_mock, hass):
    from datetime import UTC, datetime

    from homeassistant.components.recorder.models.statistics import StatisticMeanType
    from homeassistant.components.recorder.statistics import async_import_statistics

    async_import_statistics(
        hass,
        {
            "statistic_id": "sensor.grid",
            "source": "recorder",
            "name": None,
            "unit_of_measurement": "kWh",
            "unit_class": "energy",
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
        },
        [{"start": datetime(2030, 1, 1, tzinfo=UTC), "state": 1, "sum": 1}],
    )
    await async_wait_recording_done(hass)
    with patch(
        "custom_components.energy_bill.config_flow.async_get_manager",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            "energy_bill", context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"import_stat": "sensor.grid"}
        )
    assert result["type"] == "create_entry"
    assert result["data"] == {"import_stat": "sensor.grid"}


async def test_options_fetch_pvgis_and_report_connection_errors(recorder_mock, hass):
    from aiohttp import ClientError
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill", data={"import_stat": "sensor.grid"})
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    data = {
        "latitude": 0.0,
        "longitude": 0.0,
        "planes": [{"kwp": 1, "tilt": 30, "azimuth": 0}],
    }
    with patch(
        "custom_components.energy_bill.config_flow.async_fetch_pvgis",
        new=AsyncMock(side_effect=ClientError),
    ):
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], data
        )
    assert result["errors"]["base"] == "cannot_connect"
    with patch(
        "custom_components.energy_bill.config_flow.async_fetch_pvgis",
        new=AsyncMock(return_value=[100.0] * 12),
    ):
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], data
        )
    assert result["type"] == "create_entry"
    assert entry.options["pv_month_kwh"] == [100.0] * 12
    assert entry.options["planes"] == data["planes"]
    assert "latitude" not in entry.options


async def test_options_form_can_be_rendered(recorder_mock, hass):
    import probatio
    from homeassistant.helpers import config_validation as cv
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(domain="energy_bill")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fields = probatio.to_field_list(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    assert any(field["name"] == "planes" for field in fields)
