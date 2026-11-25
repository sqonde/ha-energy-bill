"""Daily energy and month projections."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from .profile import H0
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


@dataclass(frozen=True)
class PeriodResult:
    import_kwh: float
    supplier_cost: float | None
    feed_in: float | None
    prepay: float
    balance: float | None
    measured_days: int
    incomplete_reasons: list[str]


def project_period(
    days,
    tariffs,
    prepays,
    period_start,
    period_end,
    pv_month_kwh,
    today,
    start_reading_kwh,
    opening_balance=0,
    first_statistic_state=None,
):
    """Project a billing period from completed daily statistics."""
    recent = [d for d in days if today - timedelta(days=60) <= d.day < today]
    if not recent:
        return None
    measured = {
        d.day: d for d in days if period_start <= d.day < min(today, period_end)
    }

    def share(day):
        return H0[day.month - 1] / monthrange(day.year, day.month)[1]

    window_share = sum(share(today - timedelta(days=i)) for i in range(1, 61))
    use_solar = pv_month_kwh is not None and all(
        d.solar_kwh is not None for d in recent
    )
    consumption = (
        sum(d.import_kwh + (d.solar_kwh or 0) - d.export_kwh for d in recent)
        if use_solar
        else sum(d.import_kwh for d in recent)
    )
    potential = min(sum(d.solar_kwh for d in recent), consumption) if use_solar else 0
    actual = sum(d.solar_kwh - d.export_kwh for d in recent) if use_solar else 0
    factor = actual / potential if potential > 0 else 0.6
    gap_import = None
    first = min(measured) if measured else period_start
    last = max(measured) if measured else period_start
    if (
        start_reading_kwh is not None
        and first_statistic_state is not None
        and first > period_start
    ):
        gap_import = (first_statistic_state - start_reading_kwh) / (
            first - period_start
        ).days
    history = {d.day: d for d in days}
    try:
        year_ago = today.replace(year=today.year - 1)
    except ValueError:
        year_ago = today.replace(year=today.year - 1, day=28)
    full_year = all(
        year_ago + timedelta(days=i) in history for i in range((today - year_ago).days)
    )
    imports = cost = feed = 0.0
    reasons = set()
    day = period_start
    while day < period_end:
        energy = measured.get(day)
        if energy is None:
            reasons.add("modelled_days")
            if first < day < last:
                reasons.add("missing_statistics")
                energy = DayEnergy(day, 0, 0, None)
            elif gap_import is not None and day < first:
                energy = DayEnergy(day, gap_import, 0, None)
            else:
                try:
                    previous = day.replace(year=day.year - 1)
                except ValueError:
                    previous = day.replace(year=day.year - 1, day=28)
                if full_year and previous in history:
                    energy = history[previous]
                else:
                    c = consumption * share(day) / window_share
                    pv = (
                        pv_month_kwh[day.month - 1] / monthrange(day.year, day.month)[1]
                        if use_solar
                        else 0
                    )
                    self_use = factor * min(pv, c)
                    energy = DayEnergy(
                        day,
                        c - self_use,
                        pv - self_use
                        if use_solar
                        else sum(d.export_kwh for d in recent) / 60,
                        pv if use_solar else None,
                    )
        tariff = tariff_on(tariffs, day)
        if tariff is None:
            reasons.add("missing_tariff")
        else:
            cost += supplier_day_cost(tariff, energy.import_kwh, day)
            feed += feed_in_day(tariff, energy.export_kwh)
        imports += energy.import_kwh
        day += timedelta(days=1)
    prepay = prepayments_between(prepays, period_start, period_end)
    return PeriodResult(
        imports,
        None if "missing_tariff" in reasons else cost,
        None if "missing_tariff" in reasons else feed,
        prepay,
        None if "missing_tariff" in reasons else opening_balance + prepay - cost,
        len(measured),
        sorted(reasons),
    )
