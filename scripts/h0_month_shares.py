"""Print BDEW H0 monthly shares: python scripts/h0_month_shares.py <xls>.

Requires xlrd==2.0.2 from PyPI, only for this script, not the integration.
"""

import sys
from datetime import datetime, timedelta

import xlrd

sheet = xlrd.open_workbook(sys.argv[1]).sheet_by_name("Dynamischer Jahresverlauf")
monthly = [0.0] * 12
for row in range(5, 370):
    day = datetime(1899, 12, 30) + timedelta(days=sheet.cell_value(row, 2))
    monthly[day.month - 1] += sum(sheet.row_values(row, 3, 99))
total = sum(monthly)
for value in monthly:
    print(f"{value / total:.6f}")
