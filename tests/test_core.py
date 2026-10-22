import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.billing.subscriptions import active_vip_chat_ids, extend_vip, get_or_create_user, record_payment
from app.core.config import normalize_database_url
from app.core.db import SessionLocal
from app.core.security import validate_init_data
from app.models import Event, utcnow

TOKEN = "123456:TEST-TOKEN"


def signed_init_data(user_id: int = 42, auth_date: int = None, token: str = TOKEN) -> str:
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAE", "user": json.dumps({"id": user_id, "first_name": "Ali"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_init_data_valid_tampered_expired():
    assert validate_init_data(signed_init_data(), TOKEN)["id"] == 42
    assert validate_init_data(signed_init_data(), "other:token") is None
    assert validate_init_data(signed_init_data().replace("Ali", "Bob"), TOKEN) is None
    assert validate_init_data(signed_init_data(auth_date=int(time.time()) - 2 * 86400), TOKEN) is None
    assert validate_init_data("", TOKEN) is None
    assert validate_init_data("garbage", TOKEN) is None


def test_database_url_normalization():
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert (
        normalize_database_url("postgresql://u:p@ep.neon.tech/db?sslmode=require&channel_binding=require")
        == "postgresql+asyncpg://u:p@ep.neon.tech/db"
    )
    assert normalize_database_url("sqlite+aiosqlite:///./x.db") == "sqlite+aiosqlite:///./x.db"


async def test_event_time_roundtrips_as_aware_utc():
    async with SessionLocal() as s:
        ev = Event(external_id="x", title="CPI m/m", event_time=datetime(2026, 10, 21, 17, 30, tzinfo=timezone(timedelta(hours=5))))
        s.add(ev)
        await s.commit()
        ev_id = ev.id
    async with SessionLocal() as s:
        loaded = await s.get(Event, ev_id)
        assert loaded.event_time == datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
        assert loaded.event_time.isoformat().endswith("+00:00")


async def test_vip_extension_stacks_and_payment_is_idempotent():
    async with SessionLocal() as s:
        user = await get_or_create_user(s, 777, "ali")
        assert not user.is_vip()
        assert await record_payment(s, user, "charge-1", 500, 30)
        first_until = user.vip_until
        assert first_until > utcnow() + timedelta(days=29)
        assert not await record_payment(s, user, "charge-1", 500, 30)  # Telegram retry: no double credit
    async with SessionLocal() as s:
        user = await get_or_create_user(s, 777)
        assert user.vip_until == first_until
        await extend_vip(s, user, 10)
        assert user.vip_until == first_until + timedelta(days=10)
        assert await active_vip_chat_ids(s) == [777]


async def test_get_or_create_user_is_stable():
    async with SessionLocal() as s:
        a = await get_or_create_user(s, 1)
        b = await get_or_create_user(s, 1)
        assert a.id == b.id


async def test_init_db_adds_new_nullable_columns_to_existing_tables():
    # Simulates the live Neon DB created before plans.result_r existed
    from sqlalchemy import inspect, text

    from app.core.db import engine, init_db

    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE plans DROP COLUMN result_r"))
    await init_db()
    async with engine.connect() as conn:
        cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("plans")})
    assert "result_r" in cols


async def test_promo_code_two_people_once_each(monkeypatch):
    from app.billing.subscriptions import redeem_promo
    from app.core.config import settings

    monkeypatch.setattr(settings, "PROMO_CODE", "Oltin2026")
    async with SessionLocal() as s:
        a, b, c = [await get_or_create_user(s, i) for i in (901, 902, 903)]
        assert await redeem_promo(s, a, "wrong") == "invalid"
        assert await redeem_promo(s, a, " oltin2026 ") == "ok"  # case/space tolerant
        assert a.vip_until > utcnow() + timedelta(days=29)
        assert await redeem_promo(s, a, "OLTIN2026") == "used"
        assert await redeem_promo(s, b, "Oltin2026") == "ok"
        assert await redeem_promo(s, c, "Oltin2026") == "exhausted"  # limit 2
        assert not c.is_vip()
    monkeypatch.setattr(settings, "PROMO_CODE", None)
    async with SessionLocal() as s:
        assert await redeem_promo(s, await get_or_create_user(s, 904), "anything") == "invalid"  # disabled
