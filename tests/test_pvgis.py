from aiohttp import web

from custom_components.energy_bill.pvgis import async_fetch_pvgis


async def test_fetch_sums_monthly_yield_for_two_planes(
    aiohttp_client, monkeypatch, socket_enabled
):
    async def pvgis(request):
        assert request.query["lat"] == "0.0"
        assert request.query["lon"] == "0.0"
        return web.json_response(
            {
                "outputs": {
                    "monthly": {
                        "fixed": [
                            {
                                "month": month,
                                "E_m": month * float(request.query["peakpower"]),
                            }
                            for month in range(1, 13)
                        ]
                    }
                }
            }
        )

    app = web.Application()
    app.router.add_get("/PVcalc", pvgis)
    client = await aiohttp_client(app)
    monkeypatch.setattr(
        "custom_components.energy_bill.pvgis.PVGIS_URL", str(client.make_url("/PVcalc"))
    )
    result = await async_fetch_pvgis(
        client.session,
        0.0,
        0.0,
        [
            {"kwp": 1, "tilt": 30, "azimuth": -90},
            {"kwp": 2, "tilt": 30, "azimuth": 90},
        ],
    )
    assert result == [3 * month for month in range(1, 13)]


async def test_fetch_rejects_invalid_monthly_yield(
    aiohttp_client, monkeypatch, socket_enabled
):
    import pytest

    async def pvgis(request):
        return web.json_response(
            {
                "outputs": {
                    "monthly": {
                        "fixed": [{"month": month, "E_m": -1} for month in range(1, 13)]
                    }
                }
            }
        )

    app = web.Application()
    app.router.add_get("/PVcalc", pvgis)
    client = await aiohttp_client(app)
    monkeypatch.setattr(
        "custom_components.energy_bill.pvgis.PVGIS_URL", str(client.make_url("/PVcalc"))
    )
    with pytest.raises(ValueError):
        await async_fetch_pvgis(
            client.session, 0.0, 0.0, [{"kwp": 1, "tilt": 30, "azimuth": 0}]
        )
