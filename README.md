# Energy Bill

A Home Assistant custom integration for electricity tariffs and bill projections.

Add the integration and choose the long-term statistics for grid import and,
optionally, grid export and solar production. Add tariff, prepayment and billing
period entries under the integration. A tariff starts at local midnight on its
valid-from date; add a new tariff for a price change and keep older tariffs for
history. Record the meter reading at each price change for checking your bill.

Add a billing period with the meter-reading date. Its optional starting meter
reading fills the gap before the first recorded statistic when the statistic
follows the same meter register. An opening balance carries an existing balance
into the period. Enter the monthly prepayment, due day and any skipped months.
Positive period balance means a projected refund. Feed-in pay is shown
separately and is not deducted from supplier costs.

In the integration options, enter the latitude and longitude and add each PV
plane's peak power, tilt and azimuth. Azimuth is 0 for south, -90 for east and
90 for west. When you save these options, the coordinates are sent to the
EU Joint Research Centre’s PVGIS service and are not stored in the entry.
The returned monthly estimates are stored. An empty plane list disables the PV model.

The month projection uses recorded daily statistics up to yesterday and a
28-calendar-day average for the remaining days. During the first 28 days, the
average includes days without data and may be low. The billing-period projection
uses recorded days and models the rest from recent consumption, seasonal H25
shares derived from the BDEW 2025 dynamised profile and, when configured, PV
yield and measured self-use. With a full year of daily statistics it uses the
corresponding previous-year day where available.
Missing buckets between readings count as zero change because the next bucket
may contain the missed energy. A price change inside such a gap can therefore
be attributed to the wrong tariff. Check `measured_days` and
`incomplete_reasons` on the period sensors. Estimates are not invoices.

The opening balance, separate export settlement, and completeness reasons are
inspired by [Energy Costs](https://github.com/matzem79/home-assistant-energy-costs)
(MIT license).

## Dashboard

`docs/dashboard.yaml` is an example Lovelace view with the Energy Bill sensors only.
Consumption, solar and cost per period stay in the Home Assistant Energy
dashboard. To use the example, open a dashboard, choose Edit dashboard,
open the raw configuration editor from the three-dot menu and paste the file's
content. It replaces the dashboard; to keep other views, paste the view under
`views:` as a list item instead.

In the Energy dashboard settings, set the grid import price to
`sensor.energy_bill_price_buy` and the export price to
`sensor.energy_bill_price_sell`.
