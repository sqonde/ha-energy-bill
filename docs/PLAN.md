# Energy Bill (Home Assistant integration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public Home Assistant custom integration that keeps dated electricity tariffs and prepayments, exposes the price valid now (for the energy dashboard and evcc), and projects grid import, the supplier's cost and the difference to the prepayments for the current month and the billing period.

**Architecture:** One config entry per grid connection (statistic ids of the grid import, export and PV yield meters); config subentries for tariffs, prepayments and billing periods. All arithmetic lives in pure modules without Home Assistant imports (`tariffs.py`, `projection.py`), tested with plain pytest. A `DataUpdateCoordinator` reads daily long-term statistics hourly, calls the pure modules, and sensors show the result. The price sensors do not depend on the coordinator, so a failing statistics read never takes the price away. Setup makes no network call; PVGIS is fetched only in the options flow and stored.

**Tech Stack:** Python 3.14, Home Assistant 2026.11 (config subentries, recorder `statistics_during_period`), `pytest-homeassistant` (not the deprecated `pytest-homeassistant-custom-component`), HA's aiohttp session for PVGIS, ruff.

**Requirements:**
- tariffs change at a date; a new tariff must be enterable in the UI without code changes, the old ones stay as history
- estimates of what is paid to the supplier, month and billing period, against the monthly prepayment (Abschlag)
- used for years and maintained as a public project; Home Assistant changes monthly, so CI checks proposed dependency updates
- amounts of money are shown only where the user puts them (dashboard), the integration only provides sensors
- prior art: "Energy Costs" (github.com/matzem79/home-assistant-energy-costs), see Decisions

Facts the plan relies on (checked in HA core 2026.11.3 by the review): the energy dashboard prices every meter state change at the price entity's value at that moment; while the price entity is unknown it skips and later charges the whole gap at the next valid price; switching from a fixed price to an entity keeps the cost statistic; `day` and `month` statistics buckets are local time.

## Global Constraints

- Domain `energy_bill`, name "Energy Bill", repo `github.com/sqonde/ha-energy-bill` (GitHub, not Codeberg: Marketplace/HACS installs from GitHub releases only, hassfest and the HACS check are GitHub Actions, and HA users report issues there)
- `manifest.json`: `version`, `documentation`, `issue_tracker`, `codeowners` (`@sqonde`), `iot_class: calculated`, `integration_type: service`, `config_flow: true`, `dependencies: ["recorder"]`, `after_dependencies: ["energy"]`; `hacs.json` in the repo root with `"homeassistant": "2026.11.0"`; config entry `VERSION = 1`, `MINOR_VERSION = 1` with an `async_migrate_entry` from the first release on
- Brand icon in `custom_components/energy_bill/brand/icon.png`
- Public repo: no real addresses, coordinates, hosts, names, dates or prices of any real user in code, tests, fixtures, README, LICENSE or history (tests use e.g. 2030-04-01, 0.30/0.40 EUR, coordinates 0.0/0.0 or 52.5/13.4); copyright holder "sqonde"; before every commit check the diff for personal data (real names, places, coordinates, addresses)
- Commit messages: Conventional Commits, one line, at most 72 characters, no body or trailers
- **Supplier cost** = import kWh × buy price + base fee. Feed-in pay is paid by the grid operator, not the supplier: it is never subtracted from the supplier cost or the balance, it has its own sensors
- Prices in EUR/kWh, base fee in EUR/year, billed per day (`base_year / days_in_year`); currency `hass.config.currency` as the sensor unit
- Price sensors: no device_class, `state_class: measurement`, unit `<currency>/kWh`. Amount sensors: `device_class: monetary`, unit `<currency>`, no state_class. Projections with no measured data are `unknown`, never a bare base fee
- A tariff is valid from 00:00 local time of its `valid_from` until the next tariff's `valid_from`
- Energy dashboard preferences (`energy.async_get_manager`) are undocumented: read them only to pre-fill the config flow
- Strings in `strings.json`, `translations/en.json`, `translations/de.json`
- CI runs tests against pinned `pytest-homeassistant`; weekly Dependabot pull requests check new releases and action updates

## Review Focus

1. Tariff change in the middle of a month or billing period: each day at the tariff valid that day, base fee per day (Task 2, Task 4)
2. The price sensor switches at local midnight of a future `valid_from` without a restart, and stays available when statistics or the network fail (Task 3)
3. Gaps in the statistics (HA down: the missed energy lands in the first bucket after restart) and meter resets: averages are taken over the window's total change divided by calendar days, never over "present days", and negative changes are not clamped (the recorder already handles resets) (Task 4)
4. Month boundaries and DST in Europe/Berlin, tested in the coordinator with the HA time zone set (Task 4)
5. Billing periods that do not start on 01-01 and drift with the meter-reading date; prepayments that change mid-period or are collected 11 times (Task 5)

---

### Task 1: Repository skeleton, CI and release

**Files:**
- Create: `custom_components/energy_bill/{__init__.py,manifest.json,const.py,strings.json,translations/en.json,translations/de.json,brand/icon.png}`, `hacs.json`, `README.md`, `LICENSE` (MIT, sqonde), `pyproject.toml` (ruff; pytest `asyncio_mode = "auto"`, `addopts = "-p no:respx"`), `requirements_test.txt` (`pytest-homeassistant==2026.11.3`), `.github/workflows/test.yml` (ruff; pytest on pinned), `.github/dependabot.yml` (weekly dependency and action updates), `.github/workflows/validate.yml` (hassfest, `hacs/action` `category: integration`), `scripts/release.sh <version>` (bump manifest, tag, push, `gh release create --verify-tag` with `energy_bill.zip` of `custom_components/energy_bill` attached)
- Test: `tests/test_init.py`

- [ ] **Step 1:** `test_setup_and_unload` (entry `LOADED`, then `NOT_LOADED`); `test_migrate_entry_v1_noop` (`async_migrate_entry` returns True for 1.1).
- [ ] **Step 2:** Run `pytest tests/test_init.py -v`. Expected: FAIL (integration missing).
- [ ] **Step 3:** `async_setup_entry`/`async_unload_entry` forwarding to `Platform.SENSOR`, update listener reloading the entry (subentry changes fire it), `async_migrate_entry`.
- [ ] **Step 4:** Run. Expected: PASS; `ruff check .` clean; leak check exit 0.
- [ ] **Step 5:** Commit `feat: integration skeleton, CI and release script`.

### Task 2: Tariffs and prepayments (pure)

**Files:** Create `custom_components/energy_bill/tariffs.py`; Test `tests/test_tariffs.py`

**Interfaces:**
- Produces: `Tariff(valid_from: date, buy: float, sell: float, base_year: float)`; `Prepayment(valid_from: date, amount: float, due_day: int, skip_months: frozenset[int])` (`skip_months` e.g. `{12}` for suppliers collecting 11 times); `tariff_on(tariffs, day) -> Tariff | None`; `supplier_day_cost(t, import_kwh, day) -> float` = `import*buy + base_year/days_in_year(day)`; `feed_in_day(t, export_kwh) -> float` = `export*sell`; `prepayments_between(prepays, start: date, end: date) -> float` (sum of amounts whose due date `due_day` of a month falls in `[start, end)`, using the prepayment valid on that due date, skipping `skip_months`)

- [ ] **Step 1:** Tests with tariffs (2030-01-01, 0.30/0.08, base 120) and (2030-04-01, 0.40/0.08, base 180): `tariff_on` on 03-31 is 0.30, on 04-01 is 0.40, on 2029-12-31 is None, unsorted input gives the same; `supplier_day_cost(t1, 10, date(2030,1,7)) == approx(3.0 + 120/365)`; base fee over all days of 2032 (leap) sums to `base_year`; feed-in is not part of `supplier_day_cost`. Prepayments 100 € due day 15 from 2030-01-01, 120 € from 2030-06-01, `skip_months={12}`: `prepayments_between(2030-01-01, 2031-01-01) == 5*100 + 6*120`; a change between due dates takes effect on the next due date.
- [ ] **Step 2:** Run `pytest tests/test_tariffs.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement with `bisect` on sorted `valid_from`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: dated tariffs, prepayments and daily supplier cost`.

### Task 3: Config flow, subentries, price sensors, diagnostics (release 0.1.0)

**Files:** Create `config_flow.py`, `sensor.py`, `diagnostics.py`; Modify `const.py`, `strings.json`, translations; Test `tests/test_config_flow.py`, `tests/test_price_sensor.py`

**Interfaces:**
- Consumes: `Tariff`, `Prepayment`, `tariff_on` (Task 2)
- Produces: entry data `import_stat`, `export_stat`, `solar_stat` (optional); subentry types `tariff` (`valid_from`, `buy`, `sell`, `base_year`), `prepayment` (`valid_from`, `amount`, `due_day`, `skip_months`), `billing_period` (`start`, optional `start_reading_kwh`, optional `opening_balance`); helpers in `__init__.py`: `tariffs_from_entry`, `prepayments_from_entry`, `periods_from_entry`; entities with stable unique ids `<entry_id>_price_buy`, `<entry_id>_price_sell`

- [ ] **Step 1:** Tests:
  - user step pre-fills import/export/solar from the energy preferences when present (mocked `async_get_manager`), works without them, rejects a statistic id without metadata (`no_statistics`)
  - each subentry type: add, reconfigure, delete; duplicate `valid_from`/`start` rejected (`duplicate_date`); negative prices rejected; titles like `"from 2030-04-01"`
  - price sensors with the two tariffs of Task 2, HA time zone `Europe/Berlin`: at 2030-03-31 23:59:59 local `price_buy` is 0.30; after `async_fire_time_changed` to 2030-04-01 00:00:00 local it is 0.40 without reload; before the first tariff `unknown` and a repair issue `no_tariff` exists, removed once a tariff is valid; adding a tariff updates the sensor; setup succeeds when the recorder has no statistics
  - diagnostics return entry data and subentries
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Config flow with three `StatisticSelector`s; `async_get_supported_subentry_types` returning the three flows with `async_step_user` and `async_step_reconfigure`. Price sensors re-evaluate at every local midnight (`async_track_time_change(hour=0, minute=0, second=0)`); no coordinator dependency.
- [ ] **Step 4:** Run. Expected: PASS; ruff clean; leak check 0; hassfest and HACS action green.
- [ ] **Step 5:** Commit `feat: tariff, prepayment and period subentries, price sensors`; `scripts/release.sh 0.1.0`.

### Task 4: Month projection (release 0.2.0)

**Files:** Create `projection.py`, `coordinator.py`; Modify `sensor.py`; Test `tests/test_projection.py`, `tests/test_coordinator.py`

**Interfaces:**
- Consumes: Task 2 functions; entry helpers (Task 3)
- Produces: `DayEnergy(day, import_kwh, export_kwh, solar_kwh | None)`; `daily_mean(days, until: date, window: int) -> DayEnergy` (total change of the window divided by the window's calendar days, also counting days without a bucket); `project_month(days, tariffs, today, window=28) -> MonthResult(import_kwh, supplier_cost, supplier_cost_to_date, feed_in, prepay, measured_days)`; `EnergyBillCoordinator(hass, entry)` updated hourly, reading day buckets (`statistics_during_period(..., "day", None, {"change"})`) from the earliest needed date in one executor call
- Days of the month before `today` measured; `today` and later estimated by `daily_mean`; each day costed at its tariff. No data in the window: `MonthResult` is None, sensors `unknown`.

- [ ] **Step 1:** Pure tests: 28 measured days of 10 kWh import, 2 kWh export, tariff 0.30/0.08, base 120: April 2030 with today 04-16 gives import 300 and supplier cost `300*0.30 + 30*120/365`, feed-in `60*0.08` separate; a tariff change on 04-20 costs 04-20..04-30 at the new price; a window with one missing day and the next day carrying two days' energy gives the same mean as without the gap; a negative change of -0.1 lowers the total by 0.1. Coordinator test with `recorder_mock`, `hass.config.time_zone = "Europe/Berlin"`: hourly statistics imported via `async_import_statistics` across the DST end of 2030-10-27 with literal expected kWh per day (e.g. 25 hours on that day); October counts 31 days.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Sensors `month_import` (kWh, `device_class: energy`, no state_class), `month_supplier_cost`, `month_supplier_cost_to_date`, `month_feed_in`, `month_prepay`, attribute `measured_days`. Commit `feat: month projection of grid import and supplier cost`; release 0.2.0.

### Task 5: Billing-period projection (release 0.3.0)

**Files:** Create `pvgis.py`, `profile.py` (BDEW H0 monthly consumption shares, 12 constants with source in a comment); Modify `projection.py`, `coordinator.py`, `config_flow.py` (options: PV planes, PVGIS fetch), `sensor.py`; Test `tests/test_projection.py`, `tests/test_pvgis.py`

**Interfaces:**
- Consumes: Task 4 functions; `prepayments_between` (Task 2)
- Produces: options `planes: list[{kwp, tilt, azimuth}]` (PVGIS convention: 0 south, -90 east, 90 west) and `pv_month_kwh: list[12 floats]`, filled only by the options flow; `async_fetch_pvgis(session, lat, lon, planes) -> list[float]`; `project_period(days, tariffs, prepays, period_start, period_end, pv_month_kwh | None, today, start_reading_kwh | None) -> PeriodResult(import_kwh, supplier_cost, feed_in, prepay, balance, measured_days)` with `balance = opening_balance + prepay - supplier_cost` (positive: refund) and `incomplete_reasons: list[str]` (e.g. `missing_tariff`, `modelled_days`)
- The current billing period is the latest `billing_period.start` up to today, ending one year later or at the next start. Measured days from statistics. If `start_reading_kwh` is set and the import statistic follows the meter register, days before the first statistic are covered by `first_statistic_state - start_reading_kwh`, spread evenly. Other days: consumption `c` = measured mean daily consumption of the last 60 days, rescaled by BDEW H0 shares (`c_m = c_window / share(window months) * share(m)`), consumption = import + solar - export; PV `p` = `pv_month_kwh[m]` per day; self-use `s = k * min(p, c)` with `k` = measured self-use / min(yield, consumption) over the last 60 days (default 0.6); import `c - s`. Without `solar_stat` or planes: import is modelled directly from its own mean with H0 shares. Each day costed at its tariff.
- `ponytail:` the H0 profile does not know the EV; once a full year of statistics exists, use the same month of the previous year instead of the model.

- [ ] **Step 1:** Tests: `async_fetch_pvgis` against a fixture with request coordinates 0.0/0.0 (`outputs.monthly.fixed[].E_m`, two planes summed; HTTP error → flow error `cannot_connect`); `project_period` for a period 2030-03-01..2031-03-01 with statistics from 2030-08-17 and today 2030-11-25, crossing a tariff change on 2031-01-01: sums against a hand computation in the test; with `start_reading_kwh` the gap before 08-17 uses the reading; without solar the import model applies; balance sign; prepayments with `skip_months`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement; the options flow pre-fills the location from the home zone (never stored in the repo) and stores `pv_month_kwh`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Sensors `period_import`, `period_supplier_cost`, `period_feed_in`, `period_prepay`, `period_balance`, attribute `measured_days`. README: measured vs modelled, how to add a tariff, prepayment and period, the meter reading at a price change. Commit `feat: billing-period projection with PV model and balance`; release 0.3.0.

## Decisions

- A failed upload may leave an incomplete release asset. The pipeline stops without replacing it; a person must resolve it before retrying. The protected v0.3.2 asset must never be deleted or replaced.
- H25 replaces H0 as the seasonality source (owner decision, 2026-11-25).
- Build instead of forking "Energy Costs" (matzem79, MIT, 0.2.3): reviewed 2026-11-25. Its domain model is sound (import and export settled separately with own billing starts, opening balance for a period begun before tracking, `incomplete_reasons` instead of silent zeros, DST-aware day split, backfill from statistics), but it keeps its own ledger fed by polling the meters every minute, bundles prices and prepayments in one tariff row in one options form, has no HA integration tests (unittest with mocks, CI on Python 3.13) and no price sensor or forecast; a fork would replace most of it. Take over, with attribution in the README: the opening balance (Task 5 `billing_period.opening_balance`), the export settlement as its own balance, and the completeness reasons as a sensor attribute
- Name `energy_bill` / "Energy Bill"; the release zip must install by unpacking it into `custom_components/` (some users install without the Marketplace)
- Feed-in shown separately, not netted against the supplier bill
- Consumption seasonality from the BDEW H0 profile until a year of data exists
- Task 1 includes minimal `config_flow.py` and `sensor.py` placeholders: Home Assistant loads the declared config flow and forwarded sensor platform during setup. Task 3 implements their user-facing behavior.
- CI uses an exact `pytest-homeassistant` pin. Weekly Dependabot pull requests provide early warning of new releases, with CI and review before updating the pin; no test job floats.
- `hacs.json` includes the integration name as well as the minimum Home Assistant version for HACS validation.
- Prepayment due days are limited to 1–28 so every selected day exists in every month.
- Releases use bump on pushes to main. The planned 0.1.0, 0.2.0 and 0.3.0 releases mean the releases containing Tasks 3, 4 and 5 respectively; versions follow commits (feat increments the minor version while 0.x). The release archive stamps the manifest version from the tag and unpacks into `custom_components/`.
- Month projections accept prepayments as an optional argument, since the planned result includes prepayments but its interface omitted them. A missing tariff makes the projection unknown rather than reporting an incomplete bill.
- The Task 5 calculation accepts the opening balance and the first recorder state as additional inputs: both are needed to calculate the stated balance and backfill the meter-reading gap. The first hourly state covers the gap; its change is removed from the first daily bucket to avoid counting that energy twice.
- Missing days between recorder buckets count as zero change, since the next bucket may contain their energy; the result marks `missing_statistics` because a tariff change inside the gap cannot be apportioned precisely. Days before the first bucket and future days are modelled unless a starting meter reading covers the earlier gap.
- The H0 shares are derived from the dynamised profile in the original BDEW 1999 tables. PVGIS requests use the checked API v5.3 and a 14% system loss.
- A period with a missing tariff keeps the import and prepayment estimates, but reports supplier cost, feed-in and balance as unknown rather than partial amounts.
- Without a solar model the projection uses recent export statistics for future feed-in, separately from the import estimate.
