"""Fetch monthly PV output for each configured plane."""

import math

from aiohttp import ClientTimeout

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"


async def async_fetch_pvgis(session, lat, lon, planes):
    """Return the combined monthly yield in kWh."""
    totals = [0.0] * 12
    for plane in planes:
        params = {
            "lat": lat,
            "lon": lon,
            "peakpower": plane["kwp"],
            "loss": 14,
            "angle": plane["tilt"],
            "aspect": plane["azimuth"],
            "outputformat": "json",
        }
        async with session.get(
            PVGIS_URL, params=params, timeout=ClientTimeout(total=30)
        ) as response:
            response.raise_for_status()
            data = await response.json()
        rows = data["outputs"]["monthly"]["fixed"]
        if len(rows) != 12 or {row["month"] for row in rows} != set(range(1, 13)):
            raise ValueError("Invalid PVGIS monthly data")
        for row in rows:
            value = row["E_m"]
            if (
                not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError("Invalid PVGIS monthly yield")
            totals[row["month"] - 1] += value
    return totals
