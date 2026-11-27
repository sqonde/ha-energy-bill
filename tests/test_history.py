from datetime import date, timedelta

import pytest

from custom_components.energy_bill.history import monthly_rows
from custom_components.energy_bill.projection import DayEnergy
from custom_components.energy_bill.tariffs import Prepayment, Tariff


def test_monthly_rows_project_past_and_current_months():
    days = [
        DayEnergy(date(2030, 3, 1) + timedelta(days=i), 10, 0, None) for i in range(46)
    ]
    tariffs = [Tariff(date(2030, 1, 1), 0.3, 0, 0), Tariff(date(2030, 4, 1), 0.4, 0, 0)]
    prepays = [Prepayment(date(2030, 1, 1), 100, 15, frozenset())]
    rows = monthly_rows(days, tariffs, prepays, date(2030, 4, 16), months=3)
    assert [row[0] for row in rows] == [date(2030, 3, 1), date(2030, 4, 1)]
    assert rows[0][1:] == pytest.approx((93, 100))
    assert rows[1][1:] == pytest.approx((120, 100))


def test_first_partial_month_is_omitted():
    days = [
        DayEnergy(date(2030, 3, 17) + timedelta(days=i), 10, 0, None)
        for i in range(45)
    ]
    tariffs = [Tariff(date(2030, 1, 1), 0.3, 0, 0)]
    rows = monthly_rows(days, tariffs, [], date(2030, 5, 1), months=3)
    assert [row[0] for row in rows] == [date(2030, 4, 1), date(2030, 5, 1)]
