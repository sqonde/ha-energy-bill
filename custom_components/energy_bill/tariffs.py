"""Dated tariffs and prepayments."""

from bisect import bisect_right
from calendar import isleap, monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Tariff:
    valid_from: date
    buy: float
    sell: float
    base_year: float


@dataclass(frozen=True)
class Prepayment:
    valid_from: date
    amount: float
    due_day: int
    skip_months: frozenset[int]


def tariff_on(tariffs, day: date) -> Tariff | None:
    """Return the tariff in force on a local calendar day."""
    ordered = sorted(tariffs, key=lambda tariff: tariff.valid_from)
    index = bisect_right(ordered, day, key=lambda tariff: tariff.valid_from)
    return ordered[index - 1] if index else None


def supplier_day_cost(t: Tariff, import_kwh: float, day: date) -> float:
    """Calculate import and daily base charges, excluding feed-in."""
    return import_kwh * t.buy + t.base_year / (366 if isleap(day.year) else 365)


def feed_in_day(t: Tariff, export_kwh: float) -> float:
    """Calculate feed-in pay separately from supplier cost."""
    return export_kwh * t.sell


def prepayments_between(prepays, start: date, end: date) -> float:
    """Sum payments due in the half-open date interval."""
    ordered = sorted(prepays, key=lambda prepay: prepay.valid_from)
    total = 0.0
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        for due_day in {prepay.due_day for prepay in ordered}:
            if not 1 <= due_day <= monthrange(year, month)[1]:
                continue
            due = date(year, month, due_day)
            index = bisect_right(ordered, due, key=lambda item: item.valid_from)
            if start <= due < end and index:
                prepay = ordered[index - 1]
                if prepay.due_day == due_day and month not in prepay.skip_months:
                    total += prepay.amount
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return total
