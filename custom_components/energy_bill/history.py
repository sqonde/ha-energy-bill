"""Monthly history projections."""

from datetime import timedelta

from .projection import project_month


def monthly_rows(days, tariffs, prepays, today, months=12):
    """Return projections for months with enough measurements."""
    if not days:
        return []
    first_day = min(day.day for day in days)
    starts = [today.replace(day=1)]
    for _ in range(months - 1):
        starts.append((starts[-1] - timedelta(days=1)).replace(day=1))
    rows = []
    for start in reversed(starts):
        if start < first_day:
            continue
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        result = project_month(
            days, tariffs, min(today, end - timedelta(days=1)), prepays=prepays
        )
        # shortcut: missing tariffs leave old rows; upgrade with targeted recorder cleanup.
        if result is not None:
            rows.append((start, result.supplier_cost, result.prepay))
    return rows
