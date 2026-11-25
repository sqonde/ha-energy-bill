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


def test_period_projection_without_statistics_is_unknown():
    from custom_components.energy_bill.projection import project_period

    result = project_period(
        [],
        [Tariff(date(2030, 1, 1), 0.3, 0.08, 120)],
        [],
        date(2030, 3, 1),
        date(2031, 3, 1),
        None,
        date(2030, 11, 25),
        None,
    )
    assert result is None


def test_completed_period_costs_each_day_and_prepayments():
    from custom_components.energy_bill.projection import project_period
    from custom_components.energy_bill.tariffs import Prepayment

    start = date(2030, 4, 1)
    days = [DayEnergy(start + timedelta(days=i), 10, 2, None) for i in range(30)]
    tariffs = [Tariff(start, 0.3, 0.08, 0), Tariff(date(2030, 4, 20), 0.4, 0.08, 0)]
    prepays = [Prepayment(start, 100, 15, frozenset())]
    result = project_period(
        days, tariffs, prepays, start, date(2030, 5, 1), None, date(2030, 5, 1), None
    )
    assert result.import_kwh == pytest.approx(300)
    assert result.supplier_cost == pytest.approx(101)
    assert result.feed_in == pytest.approx(4.8)
    assert result.prepay == 100
    assert result.balance == pytest.approx(-1)
    assert result.measured_days == 30


def test_period_models_days_and_counts_skipped_prepayment():
    from custom_components.energy_bill.projection import project_period
    from custom_components.energy_bill.tariffs import Prepayment

    today = date(2030, 12, 1)
    days = [DayEnergy(today - timedelta(days=i), 10, 0, None) for i in range(1, 61)]
    result = project_period(
        days,
        [Tariff(date(2030, 1, 1), 0.3, 0, 0)],
        [Prepayment(date(2030, 1, 1), 100, 15, frozenset({12}))],
        date(2030, 12, 1),
        date(2031, 1, 1),
        None,
        today,
        None,
    )
    assert result.import_kwh == pytest.approx(357.301086035585)
    assert result.supplier_cost == pytest.approx(107.1903258106755)
    assert result.prepay == 0
    assert result.balance == pytest.approx(-107.1903258106755)
    assert "modelled_days" in result.incomplete_reasons


def test_period_start_reading_covers_earlier_days():
    from custom_components.energy_bill.projection import project_period

    start = date(2030, 4, 1)
    today = date(2030, 4, 5)
    days = [DayEnergy(date(2030, 4, 4), 10, 0, None)]
    result = project_period(
        days,
        [Tariff(start, 0.3, 0, 0)],
        [],
        start,
        today,
        None,
        today,
        100,
        first_statistic_state=130,
    )
    assert result.import_kwh == pytest.approx(40)
    assert result.supplier_cost == pytest.approx(12)


def test_period_uses_solar_to_model_self_use():
    from custom_components.energy_bill.projection import project_period

    today = date(2030, 12, 1)
    days = [DayEnergy(today - timedelta(days=i), 6, 2, 6) for i in range(1, 61)]
    result = project_period(
        days,
        [Tariff(date(2030, 1, 1), 0.3, 0.08, 0)],
        [],
        today,
        date(2031, 1, 1),
        [0] * 11 + [310],
        today,
        None,
    )
    # Recent consumption is 10 kWh/day; 4 of 6 kWh solar is self-used.
    assert result.import_kwh == pytest.approx(150.6344193689)
    assert result.feed_in == pytest.approx(8.2666666667)


def test_period_uses_previous_year_when_complete():
    from custom_components.energy_bill.projection import project_period

    today = date(2030, 4, 1)
    days = [DayEnergy(today - timedelta(days=i), 10, 2, None) for i in range(1, 366)]
    days.append(DayEnergy(date(2029, 4, 1), 20, 3, None))
    result = project_period(
        days,
        [Tariff(date(2029, 1, 1), 0.3, 0.08, 0)],
        [],
        today,
        today + timedelta(days=1),
        None,
        today,
        None,
    )
    assert result.import_kwh == pytest.approx(20)
    assert result.feed_in == pytest.approx(0.24)


def test_period_gap_between_buckets_does_not_double_count():
    from custom_components.energy_bill.projection import project_period

    start = date(2030, 4, 1)
    today = date(2030, 4, 4)
    days = [
        DayEnergy(start, 10, 0, None),
        DayEnergy(start + timedelta(days=2), 20, 0, None),
    ]
    result = project_period(
        days, [Tariff(start, 0.3, 0, 0)], [], start, today, None, today, None
    )
    assert result.import_kwh == 30
    assert result.supplier_cost == pytest.approx(9)


def test_period_projects_feed_in_without_solar_model():
    from custom_components.energy_bill.projection import project_period

    today = date(2030, 12, 1)
    days = [DayEnergy(today - timedelta(days=i), 10, 2, None) for i in range(1, 61)]
    result = project_period(
        days,
        [Tariff(date(2030, 1, 1), 0.3, 0.08, 0)],
        [],
        today,
        today + timedelta(days=10),
        None,
        today,
        None,
    )
    assert result.feed_in == pytest.approx(1.6)


def test_solar_factor_uses_totals_across_window():
    from custom_components.energy_bill.projection import project_period

    today = date(2030, 12, 1)
    days = [DayEnergy(today - timedelta(days=i), 10, 0, 0) for i in range(1, 31)]
    days += [DayEnergy(today - timedelta(days=i), 0, 9, 10) for i in range(31, 61)]
    result = project_period(
        days,
        [Tariff(date(2030, 1, 1), 0.3, 0.08, 0)],
        [],
        today,
        today + timedelta(days=1),
        [0] * 11 + [310],
        today,
        None,
    )
    # 30 kWh self-used / min(300 kWh yield, 330 kWh consumption) = 0.1.
    assert result.import_kwh == pytest.approx(5.7052915346)


def test_period_missing_tariff_does_not_report_partial_bill():
    from custom_components.energy_bill.projection import project_period

    start = date(2030, 4, 1)
    days = [DayEnergy(start + timedelta(days=i), 10, 0, None) for i in range(2)]
    result = project_period(
        days,
        [Tariff(date(2030, 4, 2), 0.3, 0, 0)],
        [],
        start,
        date(2030, 4, 3),
        None,
        date(2030, 4, 3),
        None,
    )
    assert result.import_kwh == pytest.approx(20)
    assert result.supplier_cost is None
    assert result.balance is None
    assert "missing_tariff" in result.incomplete_reasons


def test_year_projection_with_tariff_change_and_meter_gap():
    from custom_components.energy_bill.projection import project_period
    from custom_components.energy_bill.tariffs import Prepayment

    start = date(2030, 3, 1)
    today = date(2030, 11, 25)
    first = date(2030, 8, 17)
    days = [DayEnergy(first + timedelta(days=i), 10, 0, None) for i in range(100)]
    tariffs = [Tariff(start, 0.3, 0.08, 0), Tariff(date(2031, 1, 1), 0.4, 0.08, 0)]
    prepays = [Prepayment(start, 100, 15, frozenset({12}))]
    result = project_period(
        days,
        tariffs,
        prepays,
        start,
        date(2031, 3, 1),
        None,
        today,
        0,
        opening_balance=50,
        first_statistic_state=1690,
    )
    # The 60-day window spans 5 September, 31 October and 24 November days.
    # The gap and measured days total 2690 kWh; seasonal future days add 1120.2124758894.
    assert result.import_kwh == pytest.approx(3810.2124758894)
    assert result.supplier_cost == pytest.approx(1212.4985205457)
    assert result.prepay == 1100
    assert result.balance == pytest.approx(-62.4985205457)
    assert result.measured_days == 100
