"""Print BDEW H25 monthly shares: python scripts/h25_month_shares.py <xlsx>.

Requires openpyxl==3.1.5, only for this script, not the integration.
"""

import sys
from datetime import date, timedelta

import openpyxl

sheet = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)["H25"]
rows = list(
    sheet.iter_rows(min_row=3, max_row=100, min_col=3, max_col=38, values_only=True)
)
profiles = {
    (month.month, day_type): sum(row[column] for row in rows[2:])
    for column, (month, day_type) in enumerate(zip(rows[0], rows[1], strict=True))
}
monthly = [0.0] * 12
for year in range(2026, 2036):
    day = date(year, 1, 1)
    while day.year == year:
        t = day.timetuple().tm_yday
        factor = -3.92e-10 * t**4 + 3.20e-7 * t**3 - 7.02e-5 * t**2 + 2.10e-3 * t + 1.24
        day_type = ("SA", "FT")[day.weekday() - 5] if day.weekday() >= 5 else "WT"
        monthly[day.month - 1] += profiles[day.month, day_type] * factor
        day += timedelta(days=1)
total = sum(monthly)
for value in monthly:
    print(f"{value / total:.6f}")
