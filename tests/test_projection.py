from datetime import date, timedelta

import pytest

from custom_components.energy_bill.projection import (
    DayEnergy,
    daily_mean,
    project_month,
)
from custom_components.energy_bill.tariffs import Tariff


def test_month_projection_and_tariff_change():
    today = date(2030, 4, 16)
    days = [DayEnergy(today - timedelta(days=i), 10, 2, None) for i in range(1, 29)]
    tariffs = [Tariff(date(2030, 1, 1), 0.3, 0.08, 120)]
    result = project_month(days, tariffs, today)
    assert result.import_kwh == pytest.approx(300)
    assert result.supplier_cost == pytest.approx(90 + 30 * 120 / 365)
    assert result.feed_in == pytest.approx(4.8)
    assert result.supplier_cost_to_date == pytest.approx(45 + 15 * 120 / 365)
    assert result.measured_days == 15
    tariffs.append(Tariff(date(2030, 4, 20), 0.4, 0.08, 180))
    result = project_month(days, tariffs, today)
    assert result.supplier_cost == pytest.approx(101 + (19 * 120 + 11 * 180) / 365)


def test_mean_counts_gaps_and_negative_changes():
    today = date(2030, 4, 16)
    days = [DayEnergy(today - timedelta(days=i), 10, 2, None) for i in range(1, 29)]
    days.pop(0)
    days[0] = DayEnergy(days[0].day, 20, 4, None)
    assert daily_mean(days, today, 28).import_kwh == pytest.approx(10)
    days[0] = DayEnergy(days[0].day, 19.9, 4, None)
    assert daily_mean(days, today, 28).import_kwh == pytest.approx(279.9 / 28)
    assert project_month([], [Tariff(date(2030, 1, 1), 0.3, 0.08, 120)], today) is None


def test_negative_change_and_missing_tariff():
    today = date(2030, 4, 16)
    days = [DayEnergy(today - timedelta(days=1), -0.1, 0, None)]
    result = project_month(days, [Tariff(date(2030, 1, 1), 0.3, 0.08, 120)], today)
    assert result.import_kwh == pytest.approx(-0.1 - 15 * 0.1 / 28)
    assert (
        project_month(days, [Tariff(date(2030, 4, 10), 0.3, 0.08, 120)], today) is None
    )
