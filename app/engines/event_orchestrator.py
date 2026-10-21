import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.redis_client import cache
from app.models.event import EconomicEvent, SniperSignal, EventState
from app.engines.calendar_watcher import CalendarWatcher, CalendarEventRaw
from app.engines.macro_engine import macro_engine
from app.engines.liquidity_engine import liquidity_engine
from app.engines.sniper_decision import sniper_engine, SniperOrder
from app.engines.safety_guard import safety_guard, SafetyEvaluationResult
from app.services.telegram_sender import telegram_notifier
from app.services.card_renderer import card_renderer
from app.services.mt5_copier import mt5_bridge
from app.engines.live_price_feed import live_price_feed

logger = logging.getLogger(__name__)


class EventOrchestrator:
    """
    Coordinates the 5-state lifecycle of macroeconomic news trading:
    SCHEDULED -> MACRO_ANALYZED -> LIQUIDITY_MAPPED -> TRAP_DEPLOYED -> LIVE_MONITORING -> CONFIRMED / KILL_SWITCH
    """

    def __init__(self, calendar_watcher: Optional[CalendarWatcher] = None):
        self.calendar_watcher = calendar_watcher or CalendarWatcher()

    async def sync_morning_schedule(self, session: AsyncSession) -> List[EconomicEvent]:
        """Runs every morning (e.g. 08:00 AM) to sync today's Tier-1 red events."""
        raw_events = await self.calendar_watcher.sync_todays_red_events()
        stored_events: List[EconomicEvent] = []

        for raw in raw_events:
            # Check if event already exists
            query = select(EconomicEvent).where(EconomicEvent.external_id == raw.external_id)
            result = await session.execute(query)
            existing = result.scalar_one_or_none()

            if not existing:
                event = EconomicEvent(
                    external_id=raw.external_id,
                    title=raw.title,
                    country=raw.country,
                    currency=raw.currency,
                    impact=raw.impact,
                    event_time=raw.event_time,
                    previous=raw.previous,
                    forecast=raw.forecast,
                    actual=raw.actual,
                    unit=raw.unit,
                    state=EventState.SCHEDULED,
                )
                session.add(event)
                stored_events.append(event)
            else:
                stored_events.append(existing)

        await session.commit()
        logger.info(f"Synchronized {len(stored_events)} events into SCHEDULED state.")
        return stored_events

    async def advance_to_t3h_macro(self, event_id: int, session: AsyncSession) -> Optional[EconomicEvent]:
        """T-3h Step: Transitions SCHEDULED -> MACRO_ANALYZED"""
        event = await session.get(EconomicEvent, event_id)
        if not event:
            logger.error(f"Event {event_id} not found.")
            return None

        analysis = macro_engine.analyze_event(
            event_title=event.title,
            forecast=event.forecast,
            previous=event.previous,
        )

        event.macro_score = analysis.macro_score
        event.analysis_summary = analysis.bias_summary
        event.state = EventState.MACRO_ANALYZED
        await session.commit()

        # Cache state in Redis
        await cache.set(f"event:{event.id}:state", event.state.value, ex=86400)
        await cache.set(f"event:{event.id}:macro_score", str(event.macro_score), ex=86400)
        logger.info(f"Event {event_id} transitioned to MACRO_ANALYZED with score {event.macro_score}")

        # Dispatch Telegram T-3h notification
        await telegram_notifier.send_t3h_macro_scan(
            event_title=event.title,
            macro_score=event.macro_score,
            summary_text=event.analysis_summary or "",
        )
        return event

    async def advance_to_t1h_liquidity(
        self,
        event_id: int,
        session: AsyncSession,
        current_price: float = 2650.00,
    ) -> Optional[EconomicEvent]:
        """T-1h Step: Transitions MACRO_ANALYZED -> LIQUIDITY_MAPPED"""
        event = await session.get(EconomicEvent, event_id)
        if not event:
            return None

        if current_price is None:
            current_price = await live_price_feed.get_live_gold_price()

        zones = liquidity_engine.scan_market_structure(
            symbol="XAUUSD",
            current_price=current_price,
        )

        event.liquidity_score = zones.liquidity_score
        event.state = EventState.LIQUIDITY_MAPPED
        await session.commit()

        # Cache liquidity coordinates in Redis
        await cache.set(f"event:{event.id}:state", event.state.value, ex=86400)
        await cache.set(f"event:{event.id}:liquidity_upper_ob", str(zones.upper_ob), ex=86400)
        await cache.set(f"event:{event.id}:liquidity_lower_ob", str(zones.lower_ob), ex=86400)
        await cache.set(f"event:{event.id}:atr_m15", str(zones.atr_m15), ex=86400)
        logger.info(f"Event {event_id} transitioned to LIQUIDITY_MAPPED")

        # Dispatch Telegram T-1h notification
        await telegram_notifier.send_t1h_liquidity_map(
            event_title=event.title,
            upper_ob=zones.upper_ob,
            lower_ob=zones.lower_ob,
            summary_text=zones.summary,
        )
        return event

    async def advance_to_t2m_pre_sniper(
        self,
        event_id: int,
        session: AsyncSession,
        current_price: float = 2650.00,
        intermarket_score: float = 10.0,
    ) -> Optional[SniperSignal]:
        """T-2m (4:58) Step: Transitions LIQUIDITY_MAPPED -> TRAP_DEPLOYED and creates SniperSignal"""
        event = await session.get(EconomicEvent, event_id)
        if not event:
            return None

        if current_price is None:
            current_price = await live_price_feed.get_live_gold_price()

        zones = {
            "upper_ob": round(current_price + 8.10, 2),
            "lower_ob": round(current_price - 8.10, 2),
            "liquidity_score": event.liquidity_score or 40.0,
        }
        atr_m15 = 4.50

        signal_order: SniperOrder = sniper_engine.generate_pre_sniper_signal(
            macro_score=event.macro_score,
            liquidity_zones=zones,
            current_price=current_price,
            atr_m15=atr_m15,
            intermarket_score=intermarket_score,
            symbol="XAUUSD",
        )

        event.intermarket_score = intermarket_score
        event.total_score = signal_order.total_score
        event.state = EventState.TRAP_DEPLOYED

        signal = SniperSignal(
            event_id=event.id,
            symbol=signal_order.symbol,
            bias=signal_order.bias,
            confidence=signal_order.confidence,
            current_price_at_t2m=current_price,
            atr_m15=atr_m15,
            limit_trap_type=signal_order.limit_trap_type,
            limit_trap_price=signal_order.limit_trap_price,
            limit_sl=signal_order.limit_sl,
            limit_tp=signal_order.limit_tp,
            stop_break_type=signal_order.stop_break_type,
            stop_break_price=signal_order.stop_break_price,
            stop_sl=signal_order.stop_sl,
            stop_tp=signal_order.stop_tp,
            status="ACTIVE" if signal_order.is_tradable else "NO_TRADE",
            raw_payload=signal_order.summary,
        )

        session.add(signal)
        await session.commit()
        await session.refresh(signal)

        # Cache active sniper signal
        await cache.set(f"event:{event.id}:state", event.state.value, ex=86400)
        await cache.set(f"signal:{signal.id}:trap_price", str(signal.limit_trap_price), ex=86400)
        logger.info(f"Event {event_id} deployed TRAP with signal ID {signal.id}!")

        # Render Dark-Mode Signal Card & Dispatch Telegram VIP Alert
        if signal_order.is_tradable:
            card_bytes = card_renderer.render_pre_sniper_card(
                event_title=event.title,
                bias=signal_order.bias,
                confidence=signal_order.confidence,
                current_price=current_price,
                limit_type=signal_order.limit_trap_type,
                limit_entry=signal_order.limit_trap_price,
                limit_sl=signal_order.limit_sl,
                limit_tp=signal_order.limit_tp,
                stop_type=signal_order.stop_break_type,
                stop_entry=signal_order.stop_break_price,
                stop_sl=signal_order.stop_sl,
                stop_tp=signal_order.stop_tp,
                total_score=signal_order.total_score,
                symbol=signal_order.symbol,
                market_action=signal_order.market_action,
                market_entry=signal_order.market_entry,
                market_sl=signal_order.market_sl,
                market_tp=signal_order.market_tp,
            )

            await telegram_notifier.send_458_sniper_signal(
                event_title=event.title,
                symbol=signal_order.symbol,
                bias=signal_order.bias,
                confidence=signal_order.confidence,
                limit_type=signal_order.limit_trap_type,
                limit_price=signal_order.limit_trap_price,
                limit_sl=signal_order.limit_sl,
                limit_tp=signal_order.limit_tp,
                stop_type=signal_order.stop_break_type,
                stop_price=signal_order.stop_break_price,
                stop_sl=signal_order.stop_sl,
                stop_tp=signal_order.stop_tp,
                card_image_bytes=card_bytes,
                market_action=signal_order.market_action,
                current_price=signal_order.market_entry or current_price,
                market_sl=signal_order.market_sl,
                market_tp=signal_order.market_tp,
            )

            # Auto-place bracket orders on MT5 Bridge
            await mt5_bridge.place_sniper_bracket_orders(
                symbol=signal_order.symbol,
                limit_type=signal_order.limit_trap_type,
                limit_price=signal_order.limit_trap_price,
                limit_sl=signal_order.limit_sl,
                limit_tp=signal_order.limit_tp,
                stop_type=signal_order.stop_break_type,
                stop_price=signal_order.stop_break_price,
                stop_sl=signal_order.stop_sl,
                stop_tp=signal_order.stop_tp,
            )

        return signal

    async def execute_instant_safety_verification(
        self,
        event_id: int,
        actual_value: float,
        session: AsyncSession,
        current_price: float = 2650.00,
    ) -> SafetyEvaluationResult:
        """
        T+1s Step (5:00:01):
        Instant 1-second actual release verification and Kill-Switch execution.
        """
        event = await session.get(EconomicEvent, event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")

        event.actual = actual_value
        event.deviation = round(actual_value - (event.forecast or 0.0), 4)

        # Retrieve associated active signal
        signal_query = select(SniperSignal).where(SniperSignal.event_id == event.id).order_by(SniperSignal.id.desc())
        signal_res = await session.execute(signal_query)
        signal = signal_res.scalars().first()

        predicted_bias = signal.bias if signal else ("BEARISH (SELL)" if event.total_score < 0 else "BULLISH (BUY)")

        evaluation = safety_guard.evaluate_release(
            event_title=event.title,
            predicted_bias=predicted_bias,
            actual=actual_value,
            forecast=event.forecast or 0.0,
            previous=event.previous,
            current_price=current_price,
            symbol=signal.symbol if signal else "XAUUSD",
        )

        # Render 5:00:01 Safety Alert Card & Dispatch Telegram Post
        card_bytes = card_renderer.render_safety_alert_card(
            event_title=event.title,
            is_confirmed=evaluation.is_confirmed,
            actual=actual_value,
            forecast=event.forecast or 0.0,
            headline=evaluation.headline,
            action_message=evaluation.message.split("\n")[0],
            symbol=signal.symbol if signal else "XAUUSD",
        )
        await telegram_notifier.send_safety_instant_alert(
            event_title=event.title,
            is_confirmed=evaluation.is_confirmed,
            actual=actual_value,
            forecast=event.forecast or 0.0,
            action_message=evaluation.message,
            card_image_bytes=card_bytes,
        )

        if evaluation.is_kill_switch_triggered:
            event.state = EventState.SAFETY_TRIGGERED
            if signal:
                signal.status = "CANCELLED_KILL_SWITCH"
                signal.is_kill_switch_triggered = True
                signal.kill_switch_reason = evaluation.message

            # Execute MT5 Emergency Kill-Switch Cancel & Market Flip
            await mt5_bridge.emergency_kill_switch_cancel_all(signal.symbol if signal else "XAUUSD")
            if evaluation.suggested_flip_order:
                flip = evaluation.suggested_flip_order
                await mt5_bridge.execute_market_flip(
                    symbol=flip["symbol"],
                    direction="BUY" if "BUY" in flip["action"] else "SELL",
                    sl=flip.get("sl"),
                    tp=flip.get("tp"),
                )
        else:
            event.state = EventState.DATA_CONFIRMED

        await session.commit()
        await cache.set(f"event:{event.id}:state", event.state.value, ex=86400)
        logger.info(f"Event {event_id} verified: state={event.state.value}")
        return evaluation


orchestrator = EventOrchestrator()
