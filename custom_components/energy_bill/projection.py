"""Daily energy and month projections."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from .tariffs import feed_in_day, prepayments_between, supplier_day_cost, tariff_on


@dataclass(frozen=True)
class DayEnergy:
    day: date
    import_kwh: float
    export_kwh: float
    solar_kwh: float | None


@dataclass(frozen=True)
class MonthResult:
    import_kwh: float
    supplier_cost: float
    supplier_cost_to_date: float
    feed_in: float
    prepay: float
    measured_days: int


def daily_mean(days, until: date, window: int) -> DayEnergy | None:
    """Average completed calendar days, including gaps."""
    selected = [d for d in days if until - timedelta(days=window) <= d.day < until]
    if not selected:
        return None
    solar = [d.solar_kwh for d in selected if d.solar_kwh is not None]
    return DayEnergy(
        until,
        sum(d.import_kwh for d in selected) / window,
        sum(d.export_kwh for d in selected) / window,
        sum(solar) / window if solar else None,
    )


def project_month(days, tariffs, today, window=28, prepays=()):
    """Project a month using completed daily readings and a recent mean."""
    mean = daily_mean(days, today, window)
    if mean is None:
        return None
    start = today.replace(day=1)
    end = start + timedelta(days=monthrange(today.year, today.month)[1])
    measured = {d.day: d for d in days if start <= d.day < today}
    imports = cost = cost_to_date = feed = 0.0
    day = start
    while day < end:
        tariff = tariff_on(tariffs, day)
        if tariff is None:
            return None
        energy = measured.get(day) if day < today else mean
        if energy is not None:
            imports += energy.import_kwh
            daily_cost = supplier_day_cost(tariff, energy.import_kwh, day)
            cost += daily_cost
            if day < today:
                cost_to_date += daily_cost
            feed += feed_in_day(tariff, energy.export_kwh)
        else:
            cost += supplier_day_cost(tariff, 0, day)
            cost_to_date += supplier_day_cost(tariff, 0, day)
        day += timedelta(days=1)
    return MonthResult(
        imports,
        cost,
        cost_to_date,
        feed,
        prepayments_between(prepays, start, end),
        len(measured),
    )
