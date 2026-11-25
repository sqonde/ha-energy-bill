"""Read recorder statistics and update the month projection."""

import logging
from datetime import datetime, time, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import prepayments_from_entry, tariffs_from_entry
from .projection import DayEnergy, project_month


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

    async def _async_update_data(self):
        today = dt_util.now().date()
        start = min(today.replace(day=1), today - timedelta(days=28))
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
            return None
        stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            dt_util.as_utc(local_start),
            dt_util.as_utc(datetime.combine(today, time.min, local_start.tzinfo)),
            ids,
            "day",
            {"energy": "kWh"},
            {"change"},
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
        return project_month(
            self.days,
            tariffs_from_entry(self.entry),
            today,
            prepays=prepayments_from_entry(self.entry),
        )
