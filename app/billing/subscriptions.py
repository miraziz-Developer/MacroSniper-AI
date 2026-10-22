from datetime import timedelta
from typing import List, Optional

import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Payment, User, utcnow

VIP_PAYLOAD = "vip"  # invoice payload for the Stars subscription


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: Optional[str] = None, first_name: Optional[str] = None
) -> User:
    user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:  # concurrent /start from the same user
            await session.rollback()
            return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one()
    elif user.blocked_bot or (username and user.username != username):
        user.blocked_bot = False
        user.username = username or user.username
        await session.commit()
    return user


async def extend_vip(session: AsyncSession, user: User, days: int) -> User:
    now = utcnow()
    start = user.vip_until if user.vip_until and user.vip_until > now else now
    user.vip_until = start + timedelta(days=days)
    await session.commit()
    return user


async def revoke_vip(session: AsyncSession, user: User) -> None:
    user.vip_until = None
    await session.commit()


async def record_payment(session: AsyncSession, user: User, charge_id: str, stars: int, days: int) -> bool:
    """Credits a Stars payment exactly once; returns False if this charge was already processed."""
    session.add(Payment(telegram_charge_id=charge_id, user_id=user.id, stars=stars, days=days))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return False
    await extend_vip(session, user, days)  # commits payment and extension together
    return True


async def active_vip_chat_ids(session: AsyncSession) -> List[int]:
    rows = await session.execute(
        select(User.telegram_id).where(User.vip_until > utcnow(), User.blocked_bot.is_(False))
    )
    return list(rows.scalars())


async def redeem_promo(session: AsyncSession, user: User, code: str) -> str:
    """Free VIP for the first PROMO_LIMIT people with the code: ok | invalid | used | exhausted.

    shortcut: two simultaneous redemptions of the last slot can both succeed; fine for a handful of codes.
    """
    if not settings.PROMO_CODE or not secrets.compare_digest(code.strip().lower(), settings.PROMO_CODE.strip().lower()):
        return "invalid"
    charge_id = f"promo:{user.telegram_id}"
    if await session.scalar(select(Payment.id).where(Payment.telegram_charge_id == charge_id)):
        return "used"
    used = await session.scalar(select(func.count(Payment.id)).where(Payment.telegram_charge_id.like("promo:%")))
    if used >= settings.PROMO_LIMIT:
        return "exhausted"
    return "ok" if await record_payment(session, user, charge_id, 0, settings.PROMO_DAYS) else "used"

