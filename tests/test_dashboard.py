"""The example dashboard only uses entities the integration creates."""

import re
from pathlib import Path

import yaml
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

DASHBOARD = Path(__file__).parents[1] / "docs" / "dashboard.yaml"


async def test_dashboard_entities_exist(recorder_mock, hass):
    entry = MockConfigEntry(
        domain="energy_bill", data={"import_stat": "sensor.grid"}, minor_version=1
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert yaml.safe_load(DASHBOARD.read_text())["views"][0]["cards"]
    known = {
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    used = set(re.findall(r"sensor\.energy_bill_\w+", DASHBOARD.read_text()))
    assert used
    assert used <= known


def test_dashboard_chart_uses_external_monthly_statistics():
    dashboard = yaml.safe_load(DASHBOARD.read_text())
    chart = next(
        c for c in dashboard["views"][0]["cards"] if c["type"] == "statistics-graph"
    )
    assert chart["period"] == "month"
    assert chart["chart_type"] == "bar"
    assert chart["stat_types"] == ["mean"]
    assert {item["entity"] for item in chart["entities"]} == {
        "energy_bill:ENTRY_ID_supplier_cost",
        "energy_bill:ENTRY_ID_prepay",
    }
