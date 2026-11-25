"""Tests for dated tariffs and prepayments."""

from datetime import date, timedelta

import pytest

from custom_components.energy_bill.tariffs import (
    Prepayment,
    Tariff,
    feed_in_day,
    prepayments_between,
    supplier_day_cost,
    tariff_on,
)


def test_tariff_on_handles_boundaries_and_unsorted_input():
    old = Tariff(date(2030, 1, 1), 0.30, 0.08, 120)
    new = Tariff(date(2030, 4, 1), 0.40, 0.08, 180)
    for tariffs in ([old, new], [new, old]):
        assert tariff_on(tariffs, date(2029, 12, 31)) is None
        assert tariff_on(tariffs, date(2030, 3, 31)) == old
        assert tariff_on(tariffs, date(2030, 4, 1)) == new
    assert tariff_on([], date(2030, 4, 1)) is None


def test_supplier_cost_and_feed_in_are_separate():
    tariff = Tariff(date(2030, 1, 1), 0.30, 0.08, 120)
    assert supplier_day_cost(tariff, 10, date(2030, 1, 7)) == pytest.approx(
        3.0 + 120 / 365
    )
    assert feed_in_day(tariff, 10) == pytest.approx(0.8)


def test_leap_year_base_fee_sums_to_annual_amount():
    tariff = Tariff(date(2032, 1, 1), 0.30, 0.08, 120)
    start = date(2032, 1, 1)
    assert sum(
        supplier_day_cost(tariff, 0, start + timedelta(days=offset))
        for offset in range(366)
    ) == pytest.approx(120)


def test_prepayments_use_terms_valid_on_each_due_date():
    old = Prepayment(date(2030, 1, 1), 100, 15, frozenset({12}))
    new = Prepayment(date(2030, 6, 1), 120, 15, frozenset({12}))
    assert prepayments_between([new, old], date(2030, 1, 1), date(2031, 1, 1)) == 1220
    changed = Prepayment(date(2030, 6, 16), 120, 15, frozenset())
    assert prepayments_between([old, changed], date(2030, 6, 15), date(2030, 7, 16)) == 220
    assert prepayments_between([old], date(2030, 1, 16), date(2030, 2, 15)) == 0
    assert prepayments_between([], date(2030, 1, 1), date(2031, 1, 1)) == 0


def test_payment_due_day_changes_and_duplicate_input():
    old = Prepayment(date(2030, 1, 1), 100, 5, frozenset())
    new = Prepayment(date(2030, 6, 10), 120, 20, frozenset())
    assert prepayments_between([old, new, new], date(2030, 6, 1), date(2030, 7, 1)) == 220
