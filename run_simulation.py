#!/usr/bin/env python3
"""
MacroSniper AI — Full Lifecycle Demo & Simulation Script
Executes all 5 stages of macroeconomic news execution and generates visual signal cards.
"""

import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

# Ensure python path includes current directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.database import init_db, AsyncSessionLocal
from app.models.event import EconomicEvent, EventState, EventImpact
from app.engines.event_orchestrator import EventOrchestrator
from app.engines.calendar_watcher import CalendarWatcher, MockCalendarProvider, CalendarEventRaw
from app.services.card_renderer import card_renderer
from app.services.mt5_copier import mt5_bridge
from app.engines.safety_guard import safety_guard


async def run_full_simulation():
    print("\n" + "=" * 70)
    print("🎯 MACRO SNIPER AI — TO'LIQ ISHLASH SIKLI SIMULATSIYASI")
    print("=" * 70)

    # 0. Ensure static cards directory exists
    os.makedirs("static/cards", exist_ok=True)
    await init_db()

    now = datetime.now(timezone.utc)
    mock_cpi = CalendarEventRaw(
        external_id=f"DEMO_CPI_{now.strftime('%Y%m%d%H%M')}",
        title="US Consumer Price Index (CPI) YoY",
        country="US",
        currency="USD",
        impact=EventImpact.HIGH,
        event_time=now + timedelta(hours=3),
        previous=3.1,
        forecast=3.2,
    )
    watcher = CalendarWatcher(providers=[MockCalendarProvider([mock_cpi])])
    orchestrator = EventOrchestrator(calendar_watcher=watcher)

    async with AsyncSessionLocal() as session:
        # =========================================================================
        # 1. BOSQICH: 10:00 (SCHEDULED) — Iqtisodiy Kalendar Skaneri
        # =========================================================================
        print("\n[1/5] ☀️ 10:00 AM — Morning Calendar Discovery:")
        events = await orchestrator.sync_morning_schedule(session)
        event = events[0]
        print(f"  • Voqea: {event.title} ({event.country} {event.currency})")
        print(f"  • Kutilayotgan vaqt: {event.event_time.strftime('%H:%M:%S UTC')}")
        print(f"  • Holat: {event.state.value}")

        # =========================================================================
        # 2. BOSQICH: 14:30 (T-3h) — Fundamental AI Skaneri (F_macro)
        # =========================================================================
        print("\n[2/5] 🧠 14:30 (T-3h) — Fundamental AI Engine:")
        event = await orchestrator.advance_to_t3h_macro(event.id, session)
        # Set high conviction inflation pressure for demonstration
        event.macro_score = -82.0  # Strong Bearish Gold / Hawkish USD
        await session.commit()
        print(f"  • F_macro Score: {event.macro_score:+0.1f}")
        print(f"  • Boshlang'ich kutilma: XAUUSD SELL (USD Inflyatsiya bosimi yuqori)")
        print(f"  • Holat: {event.state.value}")

        # =========================================================================
        # 3. BOSQICH: 16:30 (T-1h) — MT5 Likvidlik va Order Block Xaritasi
        # =========================================================================
        print("\n[3/5] 📊 16:30 (T-1h) — MT5 Liquidity Map Engine:")
        current_gold_price = 2650.00
        event = await orchestrator.advance_to_t1h_liquidity(event.id, session, current_price=current_gold_price)
        print(f"  • XAUUSD Joriy Narx: ${current_gold_price:.2f}")
        print(f"  • Upper Order Block (Sell Limit Zonalari): $2658.50")
        print(f"  • Lower Order Block (Buy Limit Zonalari):  $2642.00")
        print(f"  • T_liquidity Score: {event.liquidity_score:+0.1f}")
        print(f"  • Holat: {event.state.value}")

        # =========================================================================
        # 4. BOSQICH: 17:28 (T-2m / 4:58) — Pre-Sniper Buyruqlar & Visual Card
        # =========================================================================
        print("\n[4/5] 🎯 17:28 (4:58) — Pre-Sniper Order Matrix & Visual Card:")
        signal = await orchestrator.advance_to_t2m_pre_sniper(
            event.id, session, current_price=current_gold_price, intermarket_score=-40.0
        )
        print(f"  • Ishonch darajasi: {signal.confidence}% ({signal.bias})")
        print(f"  • 1-Variant (Judas Swing Trap): {signal.limit_trap_type} @ ${signal.limit_trap_price:.2f}")
        print(f"    - Stop-Loss: ${signal.limit_sl:.2f} | Take-Profit: ${signal.limit_tp:.2f} (+1200 pips)")
        print(f"  • 2-Variant (Breakout Stop):    {signal.stop_break_type} @ ${signal.stop_break_price:.2f}")
        print(f"    - Stop-Loss: ${signal.stop_sl:.2f} | Take-Profit: ${signal.stop_tp:.2f} (+1000 pips)")

        # Render and save real card to disk
        card_bytes = card_renderer.render_pre_sniper_card(
            event_title=event.title,
            bias=signal.bias,
            confidence=signal.confidence,
            current_price=current_gold_price,
            limit_type=signal.limit_trap_type,
            limit_entry=signal.limit_trap_price,
            limit_sl=signal.limit_sl,
            limit_tp=signal.limit_tp,
            stop_type=signal.stop_break_type,
            stop_entry=signal.stop_break_price,
            stop_sl=signal.stop_sl,
            stop_tp=signal.stop_tp,
            total_score=event.total_score,
            symbol=signal.symbol,
        )
        card_path = "static/cards/cpi_sniper_signal.png"
        with open(card_path, "wb") as f:
            f.write(card_bytes.getvalue())
        print(f"  📸 Infografika kartochkasi saqlandi: {os.path.abspath(card_path)}")

        # =========================================================================
        # 5. BOSQICH A: 17:30:01 (DATA CONFIRMED) — 75% Oddiy Senariy
        # =========================================================================
        print("\n[5/5 - Senariy A] ⚡ 17:30:01 — Actual Data Confirmed (+1150 Pips Target):")
        confirmed_actual = 3.5  # Higher inflation -> Confirms XAUUSD Bearish Sell
        res_confirmed = await orchestrator.execute_instant_safety_verification(
            event_id=event.id,
            actual_value=confirmed_actual,
            session=session,
            current_price=current_gold_price,
        )
        print(f"  • Actual: {confirmed_actual}% vs Forecast: {event.forecast}% (Deviation: +0.30%)")
        print(f"  • Tahlil: {res_confirmed.headline}")
        print(f"  • Buyruq: {res_confirmed.action} — Traplarni ushlab turing!")
        
        card_confirmed_path = "static/cards/cpi_actual_confirmed.png"
        card_conf_bytes = card_renderer.render_safety_alert_card(
            event_title=event.title,
            is_confirmed=True,
            actual=confirmed_actual,
            forecast=event.forecast or 3.2,
            headline=res_confirmed.headline,
            action_message="TARGET CONFIRMED! Hold positions for +1000 pips move!",
            symbol="XAUUSD",
        )
        with open(card_confirmed_path, "wb") as f:
            f.write(card_conf_bytes.getvalue())
        print(f"  📸 Tasdiqlash kartochkasi saqlandi: {os.path.abspath(card_confirmed_path)}")

        # =========================================================================
        # 5. BOSQICH B: 17:30:01 (KILL-SWITCH ANOMALY) — Favqulodda Himoya
        # =========================================================================
        print("\n[5/5 - Senariy B] 🚨 17:30:01 — Data Shock (Kill-Switch Emergency Cancel & Flip):")
        shock_actual = 2.6  # Much lower inflation -> Opposite shock!
        res_shock = safety_guard.evaluate_release(
            event_title=event.title,
            predicted_bias="BEARISH (SELL)",
            actual=shock_actual,
            forecast=3.2,
            current_price=current_gold_price,
            symbol="XAUUSD",
        )
        print(f"  • Actual: {shock_actual}% vs Forecast: 3.2% (Teskari Syurpriz!)")
        print(f"  • Xavfsizlik signali: {res_shock.headline}")
        print(f"  • MT5 Buyrug'i: < 150 ms ichida barcha Limit orderlar CANCEL qilindi!")
        print(f"  • Yangi Market Flip: MARKET BUY XAUUSD (TP: ${current_gold_price + 15.0:.2f})")

        card_shock_path = "static/cards/cpi_kill_switch_triggered.png"
        card_shock_bytes = card_renderer.render_safety_alert_card(
            event_title=event.title,
            is_confirmed=False,
            actual=shock_actual,
            forecast=3.2,
            headline=res_shock.headline,
            action_message="CANCEL ALL PENDING ORDERS! FLIP MARKET BUY XAUUSD!",
            symbol="XAUUSD",
        )
        with open(card_shock_path, "wb") as f:
            f.write(card_shock_bytes.getvalue())
        print(f"  📸 Kill-Switch kartochkasi saqlandi: {os.path.abspath(card_shock_path)}")

    print("\n" + "=" * 70)
    print("✅ TO'LIQ SIKL MUVAFFAQIYATLI YAKUNLANDI!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_full_simulation())
