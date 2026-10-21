from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.billing.subscriptions import extend_vip, get_or_create_user
from app.core.config import settings
from app.core.db import SessionLocal
from app.main import app
from app.miniapp import routes
from app.models import Event, EventState, Plan, utcnow
from tests.test_core import TOKEN, signed_init_data

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", TOKEN)

    async def gold_price():
        return 4140.0, "test"

    monkeypatch.setattr(routes.market, "gold_price", gold_price)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _event_with_plan() -> int:
    async with SessionLocal() as s:
        ev = Event(external_id="e1", title="CPI m/m", event_time=utcnow() + timedelta(minutes=1), state=EventState.PLAN_SENT)
        s.add(ev)
        await s.flush()
        s.add(Plan(event_id=ev.id, price=4140, atr=4, range_high=4145, range_low=4134, buy_entry=4145.5, buy_sl=4139.5,
                   buy_tp1=4151.5, buy_tp2=4157.5, sell_entry=4133.5, sell_sl=4139.5, sell_tp1=4127.5, sell_tp2=4121.5,
                   primary=None, price_source="test"))
        await s.commit()
        return ev.id


async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200 and res.json()["database"] is True


async def test_miniapp_page(client):
    res = await client.get("/miniapp")
    assert res.status_code == 200 and "MacroSniper" in res.text


async def test_plan_hidden_from_guests_and_free_users(client):
    await _event_with_plan()
    guest = (await client.get("/api/app/state")).json()
    assert guest["plan"] is None and guest["plan_exists"] and not guest["user"]["verified"]
    assert guest["focus"]["title"] == "CPI m/m" and guest["focus"]["event_time"].endswith("+00:00")

    free = (await client.get("/api/app/state", headers={"X-Telegram-Init-Data": signed_init_data(42)})).json()
    assert free["user"]["verified"] and not free["user"]["is_vip"] and free["plan"] is None


async def test_plan_visible_to_vip(client):
    await _event_with_plan()
    async with SessionLocal() as s:
        await extend_vip(s, await get_or_create_user(s, 42), 30)
    vip = (await client.get("/api/app/state", headers={"X-Telegram-Init-Data": signed_init_data(42)})).json()
    assert vip["user"]["is_vip"] and vip["plan"]["buy"]["entry"] == 4145.5


async def test_forged_init_data_is_rejected(client):
    forged = signed_init_data(42, token="999:attacker")
    res = (await client.get("/api/app/state", headers={"X-Telegram-Init-Data": forged})).json()
    assert not res["user"]["verified"]
    assert (await client.post("/api/app/invoice", headers={"X-Telegram-Init-Data": forged})).status_code == 401


async def test_admin_endpoints_require_token(client):
    assert (await client.post("/api/admin/sync")).status_code == 403
    assert (await client.post("/api/admin/sync", headers={"X-Admin-Token": "nope"})).status_code == 403
    assert (await client.post("/api/admin/events/1/actual", json={"value": 1})).status_code == 403


async def test_admin_actual_resolves_once(client, monkeypatch):
    from app.pipeline import orchestrator

    async def noop(*a, **k):
        return 0

    for name in ("send_many", "send_channel", "send_admins"):
        monkeypatch.setattr(orchestrator.notifier, name, noop)
    event_id = await _event_with_plan()
    assert (await client.post(f"/api/admin/events/{event_id}/actual", headers=ADMIN, json={"value": 0.5})).status_code == 200
    assert (await client.post(f"/api/admin/events/{event_id}/actual", headers=ADMIN, json={"value": 0.5})).status_code == 409
    events = (await client.get("/api/events")).json()
    assert events[0]["state"] == "RESOLVED"
