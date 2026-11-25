"""Read recorder statistics and update the month projection."""

import logging
from datetime import datetime, time, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import periods_from_entry, prepayments_from_entry, tariffs_from_entry
from .projection import DayEnergy, project_month, project_period


class EnergyBillCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="Energy Bill",
            config_entry=entry,
            update_interval=timedelta(hours=1),
        )
        self.entry = entry
        self.days = []
        self.period = None

    async def _async_update_data(self):
        today = dt_util.now().date()
        periods = sorted(periods_from_entry(self.entry), key=lambda item: item["start"])
        current = next((p for p in reversed(periods) if p["start"] <= today), None)
        start = min(today.replace(day=1), today - timedelta(days=60))
        if current:
            start = min(
                start,
                current["start"] - timedelta(days=366),
                today - timedelta(days=366),
            )
        local_start = datetime.combine(
            start, time.min, dt_util.get_time_zone(self.hass.config.time_zone)
        )
        ids = {
            self.entry.data[k]
            for k in ("import_stat", "export_stat", "solar_stat")
            if self.entry.data.get(k)
        }
        if not ids:
            self.days = []
            self.period = None
            return None

        def read_statistics():
            stop = dt_util.as_utc(datetime.combine(today, time.min, local_start.tzinfo))
            daily_stats = statistics_during_period(
                self.hass,
                dt_util.as_utc(local_start),
                stop,
                ids,
                "day",
                {"energy": "kWh"},
                {"change", "state"},
            )
            first_hour = None
            if current and current.get("start_reading_kwh") is not None:
                rows = daily_stats.get(self.entry.data.get("import_stat"), [])
                period_rows = [
                    row
                    for row in rows
                    if dt_util.as_local(
                        datetime.fromtimestamp(row["start"], dt_util.UTC)
                    ).date()
                    >= current["start"]
                ]
                if period_rows:
                    first_day = dt_util.as_local(
                        datetime.fromtimestamp(period_rows[0]["start"], dt_util.UTC)
                    ).date()
                    if first_day > current["start"]:
                        day_start = datetime.combine(
                            first_day, time.min, local_start.tzinfo
                        )
                        day_end = datetime.combine(
                            first_day + timedelta(days=1), time.min, local_start.tzinfo
                        )
                        hourly = statistics_during_period(
                            self.hass,
                            dt_util.as_utc(day_start),
                            dt_util.as_utc(day_end),
                            {self.entry.data["import_stat"]},
                            "hour",
                            {"energy": "kWh"},
                            {"state", "change"},
                        )
                        first_hour = next(
                            iter(hourly.get(self.entry.data["import_stat"], [])), None
                        )
            return daily_stats, first_hour

        stats, first_hour = await get_instance(self.hass).async_add_executor_job(
            read_statistics
        )
        daily = {}
        for key in ("import_stat", "export_stat", "solar_stat"):
            values = {}
            for row in stats.get(self.entry.data.get(key), []):
                day = dt_util.as_local(
                    datetime.fromtimestamp(row["start"], dt_util.UTC)
                ).date()
                if row.get("change") is not None:
                    values[day] = row["change"]
            daily[key] = values
        self.days = [
            DayEnergy(
                day,
                value,
                daily["export_stat"].get(day, 0),
                daily["solar_stat"].get(day),
            )
            for day, value in daily["import_stat"].items()
        ]
        self.period = None
        if current:
            try:
                end = current["start"].replace(year=current["start"].year + 1)
            except ValueError:
                end = current["start"].replace(year=current["start"].year + 1, day=28)
            next_start = next(
                (p["start"] for p in periods if p["start"] > current["start"]), end
            )
            end = min(end, next_start)
            period_days = self.days
            first_state = None
            if (
                first_hour
                and first_hour.get("state") is not None
                and first_hour.get("change") is not None
            ):
                first_state = first_hour["state"]
                first_day = dt_util.as_local(
                    datetime.fromtimestamp(first_hour["start"], dt_util.UTC)
                ).date()
                period_days = [
                    DayEnergy(
                        d.day,
                        d.import_kwh - first_hour["change"],
                        d.export_kwh,
                        d.solar_kwh,
                    )
                    if d.day == first_day
                    else d
                    for d in self.days
                ]
            self.period = project_period(
                period_days,
                tariffs_from_entry(self.entry),
                prepayments_from_entry(self.entry),
                current["start"],
                end,
                self.entry.options.get("pv_month_kwh"),
                today,
                current.get("start_reading_kwh"),
                current.get("opening_balance", 0),
                first_state,
            )
        return project_month(
            self.days,
            tariffs_from_entry(self.entry),
            today,
            prepays=prepayments_from_entry(self.entry),
        )
