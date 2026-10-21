import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings
from app.core.database import init_db

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture(autouse=True)
async def setup_db(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "test-admin-token")
    await init_db()


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["app"] == "MacroSniper AI"


@pytest.mark.asyncio
async def test_events_and_signals_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Sync events
        sync_res = await ac.post("/api/events/sync", headers=ADMIN)
        assert sync_res.status_code == 200
        assert sync_res.json()["count"] >= 1

        # 2. Get today's events
        events_res = await ac.get("/api/events/today")
        assert events_res.status_code == 200
        events = events_res.json()
        assert len(events) >= 1
        event_id = events[0]["id"]

        # 3. Trigger T-3h step
        t3h_res = await ac.post(f"/api/events/{event_id}/trigger/t3h", headers=ADMIN)
        assert t3h_res.status_code == 200
        assert t3h_res.json()["state"] == "MACRO_ANALYZED"

        # 4. Trigger T-1h step
        t1h_res = await ac.post(f"/api/events/{event_id}/trigger/t1h?price=2650.00", headers=ADMIN)
        assert t1h_res.status_code == 200
        assert t1h_res.json()["state"] == "LIQUIDITY_MAPPED"

        # 5. Trigger T-2m step
        t2m_res = await ac.post(f"/api/events/{event_id}/trigger/t2m?price=2650.00", headers=ADMIN)
        assert t2m_res.status_code == 200

        # 6. Test ultra-fast webhook release
        webhook_res = await ac.post(
            "/api/webhook/actual-release",
            headers=ADMIN,
            json={
                "event_id": event_id,
                "actual": 3.6,
                "current_price": 2650.00,
            },
        )
        assert webhook_res.status_code == 200
        webhook_data = webhook_res.json()
        assert webhook_data["status"] == "executed"
        assert "is_confirmed" in webhook_data

        # 7. Check latest signals
        signals_res = await ac.get("/api/signals/latest")
        assert signals_res.status_code == 200

        # 8. Check Mini App HTML and Dashboard endpoints
        miniapp_html = await ac.get("/miniapp")
        assert miniapp_html.status_code == 200
        assert "MACRO SNIPER" in miniapp_html.text

        dashboard_res = await ac.get("/api/miniapp/dashboard")
        assert dashboard_res.status_code == 200
        dash_data = dashboard_res.json()
        assert dash_data["status"] == "online"
        assert "active_event" in dash_data
        assert "latest_signal" in dash_data


@pytest.mark.asyncio
async def test_admin_endpoints_reject_missing_or_wrong_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.post("/api/events/sync")).status_code == 403
        assert (await ac.post("/api/events/sync", headers={"X-Admin-Token": "nope"})).status_code == 403
        bad = await ac.post("/api/webhook/actual-release", json={"event_id": 1, "actual": 1.0})
        assert bad.status_code == 403


@pytest.mark.asyncio
async def test_trigger_unknown_event_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/events/999999/trigger/t3h", headers=ADMIN)
        assert res.status_code == 404
