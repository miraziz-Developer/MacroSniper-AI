import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.event import EconomicEvent, SniperSignal
from app.engines.live_price_feed import live_price_feed
from app.engines.macro_engine import macro_engine
from app.engines.multi_asset_engine import multi_asset_engine
from app.models.event import EventState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Telegram Mini App"])


@router.get("/miniapp", response_class=HTMLResponse)
async def serve_telegram_mini_app():
    """
    Renders an ultra-clean, serious, TradingView/Bloomberg-style professional terminal.
    Zero gimmicks, zero cartoon effects. 100% focused on real trade execution for traders.
    """
    html_content = """<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>MacroSniper Pro — Treyder Terminali</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        body {
            background-color: #0b0f17;
            color: #f1f5f9;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            -webkit-tap-highlight-color: transparent;
        }
        .font-mono {
            font-family: 'JetBrains Mono', monospace;
        }
        .clean-card {
            background-color: #131b2e;
            border: 1px solid #1e293b;
        }
        .order-card {
            background-color: #0f172a;
            border: 1px solid #334155;
        }
        .toast {
            animation: fadeInOut 2.5s forwards;
        }
        @keyframes fadeInOut {
            0% { opacity: 0; transform: translateY(20px); }
            15% { opacity: 1; transform: translateY(0); }
            85% { opacity: 1; transform: translateY(0); }
            100% { opacity: 0; transform: translateY(-20px); }
        }
        .tab-btn.active {
            background-color: #1e293b;
            color: #ffffff;
            border-bottom: 2px solid #38bdf8;
        }
    </style>
</head>
<body class="p-4 max-w-lg mx-auto pb-24">

    <!-- Header: Serious Minimalist Branding -->
    <header class="flex items-center justify-between pb-3 border-b border-slate-800">
        <div>
            <div class="flex items-center space-x-2">
                <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                <h1 class="text-base font-bold tracking-tight text-white">MACRO SNIPER <span class="text-xs text-sky-400 font-semibold">PRO</span></h1>
            </div>
            <p class="text-xs text-slate-400 mt-0.5">XAU/USD Oltin va Asosiy Bozorlar Yangilik Tahlili</p>
        </div>
        <div class="text-right">
            <span class="text-[10px] font-mono font-medium px-2 py-1 rounded bg-slate-800 text-emerald-400 border border-slate-700">
                🟢 JONLI SERVER
            </span>
        </div>
    </header>

    <!-- Navigation Tabs -->
    <div class="flex mt-3 bg-slate-900 p-1 rounded-xl border border-slate-800 text-xs font-medium text-slate-400">
        <button id="tab-signal-btn" onclick="switchTab('signal')" class="tab-btn active flex-1 py-2 rounded-lg text-center transition-all">
            ⚡ Tezkor Signal
        </button>
        <button id="tab-calendar-btn" onclick="switchTab('calendar')" class="tab-btn flex-1 py-2 rounded-lg text-center transition-all">
            📅 Iqtisodiy Kalendar
        </button>
        <button id="tab-rules-btn" onclick="switchTab('rules')" class="tab-btn flex-1 py-2 rounded-lg text-center transition-all">
            📖 Yo'riqnoma
        </button>
    </div>

    <!-- ========================================== -->
    <!-- TAB 1: TEZKOR SIGNAL -->
    <!-- ========================================== -->
    <div id="tab-signal" class="mt-4 space-y-3">
        <!-- Live Gold Price Ticker Card -->
        <div class="clean-card rounded-xl p-3.5 flex items-center justify-between">
            <div>
                <div class="text-[11px] text-slate-400 font-medium">XAU/USD (OLTIN) BOZOR NARXI</div>
                <div class="text-2xl font-black font-mono text-amber-400 mt-0.5" id="live-gold-price">$4,136.50</div>
            </div>
            <div class="text-right font-mono text-xs">
                <span class="px-2 py-1 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800/60 text-[11px] font-semibold">
                    PAXG / USD FEED
                </span>
                <div class="text-[10px] text-slate-500 mt-1">Har 2 soniyada yangilanadi</div>
            </div>
        </div>

        <!-- Upcoming Event Card -->
        <div class="clean-card rounded-xl p-4">
            <div class="flex items-center justify-between text-xs mb-1.5">
                <span class="font-medium text-rose-400 flex items-center space-x-1">
                    <span class="w-2 h-2 rounded-full bg-rose-500 animate-ping"></span>
                    <span>🔴 TIER-1 YUQORI VOLATILLIK</span>
                </span>
                <span class="font-mono text-slate-400" id="news-time">Yuklanmoqda...</span>
            </div>

            <h2 class="text-base font-bold text-white mt-1" id="event-title">AQSH: Ishsizlik Arzalari (Unemployment Claims)</h2>
            <div class="flex items-center justify-between text-xs text-slate-300 mt-1 pb-2 border-b border-slate-800">
                <span>Kutilayotgan harakat: <strong class="text-emerald-400">100-150 pips (1000-1500 pts)</strong></span>
                <span class="font-mono text-sky-400 font-bold" id="countdown-timer">00:00:00</span>
            </div>

            <!-- Direction Box -->
            <div id="direction-container" class="mt-3 p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 flex items-center justify-between">
                <div>
                    <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">ASOSIY KUTILMA (AI TAHLIL)</div>
                    <div class="text-base font-extrabold text-rose-400 mt-0.5" id="bias-text">
                        📉 SOTISH (SELL)
                    </div>
                </div>
                <div class="text-right font-mono">
                    <div class="text-[10px] text-slate-400">ISHONCH</div>
                    <div class="text-sm font-bold text-white" id="confidence-text">85%</div>
                </div>
            </div>

            <!-- AI Reason -->
            <div class="mt-3 text-xs bg-slate-900/90 p-3 rounded-xl border border-slate-800 space-y-1">
                <div class="font-semibold text-slate-200 text-xs flex items-center space-x-1">
                    <span>🧠</span>
                    <span>Nega aynan ushbu yo'nalish tanlandi?</span>
                </div>
                <p class="text-[11px] text-slate-400 leading-relaxed" id="ai-reason">
                    Prognoz va avvalgi ko'rsatkichlar tahlili hamda fond bozoridagi likvidlik o'rganildi. Ushbu yangilik AQSH Dollariga ta'sir qilib, Oltinda kuchli harakat paydo qiladi.
                </p>
            </div>
        </div>

        <!-- 2 Order Options Section -->
        <div class="space-y-3">
            <div class="flex items-center justify-between pt-1">
                <h3 class="text-xs font-bold text-slate-300 uppercase tracking-wider">🎯 SAVDO BUYRUQLARI</h3>
                <span class="text-[11px] text-slate-400">Qulay variantni tanlang</span>
            </div>

            <!-- Option 1: Market Order (1 min before news) -->
            <div class="order-card rounded-xl p-3.5 border-l-4 border-l-amber-400">
                <div class="flex items-center justify-between mb-2">
                    <div>
                        <span class="text-xs font-bold text-amber-400 flex items-center space-x-1">
                            <span>⚡ 1-VARIANT: BOZOR NARXIDA (ENG ODDİY)</span>
                        </span>
                        <p class="text-[11px] text-slate-400">Yangilikdan 1 daqiqa oldin to'g'ridan-to'g'ri bosing</p>
                    </div>
                    <span class="text-xs font-mono font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40" id="market-badge">
                        MARKET SELL
                    </span>
                </div>

                <div class="grid grid-cols-3 gap-2 font-mono text-center text-xs my-2.5">
                    <div class="bg-slate-900 p-2 rounded border border-slate-800">
                        <div class="text-[10px] text-slate-400">KIRISH</div>
                        <div class="font-bold text-white text-sm" id="market-entry">Bozor narxi</div>
                    </div>
                    <div class="bg-slate-900 p-2 rounded border border-slate-800">
                        <div class="text-[10px] text-rose-400">STOP-LOSS</div>
                        <div class="font-bold text-rose-400 text-sm" id="market-sl">4145.00</div>
                    </div>
                    <div class="bg-slate-900 p-2 rounded border border-slate-800">
                        <div class="text-[10px] text-emerald-400">TAKE-PROFIT</div>
                        <div class="font-bold text-emerald-400 text-sm" id="market-tp">4118.00</div>
                    </div>
                </div>

                <button onclick="copyMarketOrder()" class="w-full py-2.5 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/40 rounded-lg text-xs font-bold text-amber-300 flex items-center justify-center space-x-1.5 transition-all">
                    <span>📋 Bozor Buyrug'i parametrlarini nusxalash</span>
                </button>
            </div>

            <!-- Option 2: Pending Stop Order -->
            <div class="order-card rounded-xl p-3.5 border-l-4 border-l-sky-500">
                <div class="flex items-center justify-between mb-2">
                    <div>
                        <span class="text-xs font-bold text-sky-400">🎯 2-VARIANT: KUTILAYOTGAN (STOP ORDER)</span>
                        <p class="text-[11px] text-slate-400">Narx birdaniga kuchli yo'nalishga uchib ketsa iladi</p>
                    </div>
                    <span class="text-xs font-mono font-bold px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40" id="stop-badge">
                        SELL STOP
                    </span>
                </div>

                <div class="grid grid-cols-3 gap-2 font-mono text-center text-xs my-2.5">
                    <div class="bg-slate-900 p-2 rounded border border-slate-800">
                        <div class="text-[10px] text-slate-400">KIRISH</div>
                        <div class="font-bold text-white text-sm" id="stop-entry">4130.00</div>
                    </div>
                    <div class="bg-slate-900 p-2 rounded border border-slate-800">
                        <div class="text-[10px] text-rose-400">STOP-LOSS</div>
                        <div class="font-bold text-rose-400 text-sm" id="stop-sl">4138.50</div>
                    </div>
                    <div class="bg-slate-900 p-2 rounded border border-slate-800">
                        <div class="text-[10px] text-emerald-400">TAKE-PROFIT</div>
                        <div class="font-bold text-emerald-400 text-sm" id="stop-tp">4114.00</div>
                    </div>
                </div>

                <button onclick="copyStopOrder()" class="w-full py-2.5 bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/40 rounded-lg text-xs font-bold text-sky-300 flex items-center justify-center space-x-1.5 transition-all">
                    <span>📋 Stop Order parametrlarini nusxalash</span>
                </button>
            </div>
        </div>

        <!-- Strategy Advice -->
        <div class="p-3 bg-slate-900/90 rounded-xl border border-slate-800 text-xs space-y-1">
            <div class="font-bold text-slate-200">💡 Treyderlar uchun Oltin Qoida:</div>
            <p class="text-slate-400 text-[11px] leading-relaxed">
                Yangilik chiqqanda narx kuchli sakraydi. <strong>70-100 pips foydaga</strong> kirishi bilan pozitsiyaning 50% ini yoping, qolgan qismiga esa Stop-Lossni ochilgan narxga (Bezubytok) o'tkazing!
            </p>
        </div>
    </div>

    <!-- ========================================== -->
    <!-- TAB 2: IQTISODIY KALENDAR (HAFTALIK REAL) -->
    <!-- ========================================== -->
    <div id="tab-calendar" class="mt-4 space-y-3 hidden">
        <div class="clean-card rounded-xl p-3">
            <div class="text-xs font-bold text-white flex items-center justify-between pb-2 border-b border-slate-800">
                <span>USHBU HAFTADAGI ASOSIY YANGILIKLAR</span>
                <span class="text-[10px] text-slate-400 font-normal">ForexFactory Jonli Feed</span>
            </div>
            <div id="calendar-list" class="divide-y divide-slate-800 mt-2">
                <div class="py-3 text-center text-xs text-slate-400">Kalendar yuklanmoqda...</div>
            </div>
        </div>
    </div>

    <!-- ========================================== -->
    <!-- TAB 3: YO'RIQNOMA VA QOIDALAR -->
    <!-- ========================================== -->
    <div id="tab-rules" class="mt-4 space-y-3 hidden">
        <div class="clean-card rounded-xl p-4 space-y-3 text-xs">
            <h3 class="font-bold text-sm text-white border-b border-slate-800 pb-2">Yangilikda Qanday Savdo Qilinadi?</h3>
            
            <div class="space-y-1">
                <div class="font-bold text-amber-400">1. Yangilikdan 1-2 daqiqa oldin:</div>
                <p class="text-slate-300 text-[11px] leading-relaxed">
                    Terminalni oching va berilgan signalni tekshiring. XAU/USD (Oltin) juftligini tayyorlab turing.
                </p>
            </div>

            <div class="space-y-1">
                <div class="font-bold text-amber-400">2. Qaysi buyruqni tanlash kerak?</div>
                <p class="text-slate-300 text-[11px] leading-relaxed">
                    Oddiy va tez harakat qilish uchun: <strong>1-Variant (Bozor buyrug'i)</strong> ni tanlang. Yangilikdan 1 daqiqa oldin BUY yoki SELL bosing va SL/TP ni qo'ying.
                </p>
            </div>

            <div class="space-y-1">
                <div class="font-bold text-amber-400">3. Birinchi impulsda nima qilish kerak?</div>
                <p class="text-slate-300 text-[11px] leading-relaxed">
                    Yangilik chiqqan soniyada 70-100 pips foyda ko'rinsa, darhol lotning 50% ini yoping, qolgan yarmining Stop-Lossini kirish narxiga suring (Bezubytok). Bu sizni 100% xavfdan asraydi.
                </p>
            </div>

            <div class="space-y-1">
                <div class="font-bold text-rose-400">4. Kill-Switch (Teskari chiqish holati):</div>
                <p class="text-slate-300 text-[11px] leading-relaxed">
                    Agar fakt raqam kutilmaganda mutlaqo teskari chiqsa, bot 17:30:01 da ogohlantirish beradi. Bunday holatda darhol pozitsiyani minimal zararda yopish tavsiya etiladi.
                </p>
            </div>
        </div>
    </div>

    <!-- Toast Notification Container -->
    <div id="toast-box" class="fixed bottom-6 left-4 right-4 z-50 flex justify-center pointer-events-none"></div>

    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
        }

        let targetEventTime = null;
        let globalSignalData = null;

        function switchTab(tab) {
            document.getElementById('tab-signal').classList.add('hidden');
            document.getElementById('tab-calendar').classList.add('hidden');
            document.getElementById('tab-rules').classList.add('hidden');

            document.getElementById('tab-signal-btn').classList.remove('active');
            document.getElementById('tab-calendar-btn').classList.remove('active');
            document.getElementById('tab-rules-btn').classList.remove('active');

            if (tab === 'signal') {
                document.getElementById('tab-signal').classList.remove('hidden');
                document.getElementById('tab-signal-btn').classList.add('active');
            } else if (tab === 'calendar') {
                document.getElementById('tab-calendar').classList.remove('hidden');
                document.getElementById('tab-calendar-btn').classList.add('active');
            } else if (tab === 'rules') {
                document.getElementById('tab-rules').classList.remove('hidden');
                document.getElementById('tab-rules-btn').classList.add('active');
            }
        }

        // Live gold price fetcher
        async function fetchSpotPrice() {
            try {
                const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT');
                if (res.ok) {
                    const data = await res.json();
                    const p = parseFloat(data.price).toFixed(2);
                    document.getElementById('live-gold-price').textContent = '$' + p;
                    document.getElementById('market-entry').textContent = p;
                }
            } catch (e) {
                // Ignore transient network errors
            }
        }

        // Dashboard sync
        async function fetchDashboard() {
            try {
                const res = await fetch('/api/miniapp/dashboard');
                if (res.ok) {
                    const data = await res.json();
                    globalSignalData = data;

                    // Event title & time
                    if (data.active_event) {
                        document.getElementById('event-title').textContent = data.active_event.title;
                        document.getElementById('news-time').textContent = data.active_event.tashkent_time_str || 'Bugun 17:30 da';
                        if (data.active_event.event_time) {
                            targetEventTime = new Date(data.active_event.event_time);
                        }
                        if (data.active_event.ai_reason) {
                            document.getElementById('ai-reason').textContent = data.active_event.ai_reason;
                        }
                    }

                    // Bias
                    const isBullish = data.is_bullish;
                    const biasEl = document.getElementById('bias-text');
                    const dirBox = document.getElementById('direction-container');
                    const mBadge = document.getElementById('market-badge');
                    const sBadge = document.getElementById('stop-badge');

                    if (isBullish) {
                        biasEl.textContent = '📈 SOTIB OLISH (BUY)';
                        biasEl.className = 'text-base font-extrabold text-emerald-400 mt-0.5';
                        dirBox.className = 'mt-3 p-3 rounded-xl bg-emerald-950/40 border border-emerald-800/60 flex items-center justify-between';
                        mBadge.textContent = 'MARKET BUY';
                        mBadge.className = 'text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
                        sBadge.textContent = 'BUY STOP';
                        sBadge.className = 'text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
                    } else {
                        biasEl.textContent = '📉 SOTISH (SELL)';
                        biasEl.className = 'text-base font-extrabold text-rose-400 mt-0.5';
                        dirBox.className = 'mt-3 p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 flex items-center justify-between';
                        mBadge.textContent = 'MARKET SELL';
                        mBadge.className = 'text-xs font-mono font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40';
                        sBadge.textContent = 'SELL STOP';
                        sBadge.className = 'text-xs font-mono font-bold px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40';
                    }

                    document.getElementById('confidence-text').textContent = (data.confidence || 85) + '%';

                    // Coordinates
                    if (data.market_order) {
                        document.getElementById('market-sl').textContent = data.market_order.sl.toFixed(2);
                        document.getElementById('market-tp').textContent = data.market_order.tp.toFixed(2);
                    }
                    if (data.stop_order) {
                        document.getElementById('stop-entry').textContent = data.stop_order.entry.toFixed(2);
                        document.getElementById('stop-sl').textContent = data.stop_order.sl.toFixed(2);
                        document.getElementById('stop-tp').textContent = data.stop_order.tp.toFixed(2);
                    }

                    // Render Calendar Tab
                    if (data.weekly_calendar && data.weekly_calendar.length > 0) {
                        renderCalendar(data.weekly_calendar);
                    }
                }
            } catch (e) {
                console.error(e);
            }
        }

        const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

        function renderCalendar(events) {
            const listEl = document.getElementById('calendar-list');
            listEl.innerHTML = '';
            events.forEach(ev => {
                const isHigh = ev.impact === 'High';
                const badgeColor = isHigh ? 'bg-rose-950/60 text-rose-400 border-rose-800/60' : 'bg-amber-950/60 text-amber-400 border-amber-800/60';
                const dt = new Date(ev.date);
                const timeStr = dt.toLocaleDateString('uz-UZ', { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

                const item = document.createElement('div');
                item.className = 'py-2.5 flex items-center justify-between text-xs';
                item.innerHTML = `
                    <div>
                        <div class="flex items-center space-x-1.5">
                            <span class="font-bold text-white">${esc(ev.country)}</span>
                            <span class="text-[10px] px-1.5 py-0.2 rounded border ${badgeColor}">${esc(ev.impact)}</span>
                            <span class="text-slate-400 font-mono text-[10px]">${timeStr}</span>
                        </div>
                        <div class="text-slate-200 font-medium mt-0.5 text-[11px]">${esc(ev.title)}</div>
                    </div>
                    <div class="text-right font-mono text-[11px]">
                        <div class="text-slate-400 text-[10px]">P: ${esc(ev.previous)}</div>
                        <div class="text-emerald-400 font-bold">F: ${esc(ev.forecast)}</div>
                    </div>
                `;
                listEl.appendChild(item);
            });
        }

        // Live countdown timer
        function updateCountdown() {
            if (!targetEventTime) {
                document.getElementById('countdown-timer').textContent = 'Kutilmoqda';
                return;
            }
            const now = new Date();
            const diff = targetEventTime - now;
            if (diff <= 0) {
                document.getElementById('countdown-timer').textContent = '⚡ Chiqdi!';
                return;
            }
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((diff % (1000 * 60)) / 1000);

            const pad = (n) => String(n).padStart(2, '0');
            document.getElementById('countdown-timer').textContent = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
        }

        function showToast(msg) {
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
            const box = document.getElementById('toast-box');
            box.innerHTML = `<div class="toast bg-emerald-500 text-slate-950 font-bold text-xs px-4 py-2.5 rounded-lg shadow-xl">${msg}</div>`;
            setTimeout(() => { box.innerHTML = ''; }, 2500);
        }

        function copyMarketOrder() {
            const action = globalSignalData?.is_bullish ? 'BUY' : 'SELL';
            const sl = document.getElementById('market-sl').textContent;
            const tp = document.getElementById('market-tp').textContent;
            const text = `MARKET ${action} XAUUSD | SL: ${sl} | TP: ${tp}`;
            navigator.clipboard.writeText(text);
            showToast(`✅ Bozor buyrug'i (${action}) nusxalandi!`);
        }

        function copyStopOrder() {
            const action = globalSignalData?.is_bullish ? 'BUY STOP' : 'SELL STOP';
            const entry = document.getElementById('stop-entry').textContent;
            const sl = document.getElementById('stop-sl').textContent;
            const tp = document.getElementById('stop-tp').textContent;
            const text = `${action} XAUUSD: ${entry} | SL: ${sl} | TP: ${tp}`;
            navigator.clipboard.writeText(text);
            showToast(`✅ Stop buyruq (${action}) nusxalandi!`);
        }

        // Initialize loops
        fetchSpotPrice();
        fetchDashboard();
        setInterval(fetchSpotPrice, 2000);
        setInterval(fetchDashboard, 6000);
        setInterval(updateCountdown, 1000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


def make_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/api/miniapp/dashboard", tags=["Telegram Mini App"])
async def get_miniapp_dashboard_data(db: AsyncSession = Depends(get_db)):
    """
    Supplies real-time JSON metrics, live price, and weekly calendar
    to the Telegram Mini App frontend.
    """
    # 1. Fetch live spot price of Gold
    try:
        live_price = await live_price_feed.get_live_gold_price()
    except Exception:
        live_price = 4140.00

    # 2. Query upcoming events from database
    now = datetime.now(timezone.utc)
    event_query = select(EconomicEvent).order_by(EconomicEvent.event_time.asc())
    event_res = await db.execute(event_query)
    events = event_res.scalars().all()

    future_events = [e for e in events if make_aware(e.event_time) >= now]
    future_usd = [e for e in future_events if e.currency == "USD"]
    active_event = (future_usd or future_events or [None])[0]

    # 3. Read cached calendar for weekly schedule
    cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ff_calendar_cache.json")
    weekly_schedule: List[Dict[str, Any]] = []
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                raw_cal = json.load(f)
                for item in raw_cal:
                    if item.get("impact") in ["High", "Medium"] and item.get("country") in [
                        "USD", "GBP", "EUR", "CAD", "NZD", "JPY", "AUD"
                    ]:
                        weekly_schedule.append({
                            "title": item.get("title"),
                            "country": item.get("country"),
                            "impact": item.get("impact"),
                            "date": item.get("date"),
                            "forecast": item.get("forecast") or "-",
                            "previous": item.get("previous") or "-",
                        })
        except Exception as e:
            logger.debug(f"Calendar read error: {e}")

    # 4. Determine directional bias
    is_bullish = False
    ai_reason = (
        "Prognoz va avvalgi ko'rsatkichlar tahlili hamda fond bozoridagi likvidlik o'rganildi. "
        "Ushbu yangilik AQSH Dollariga ta'sir qilib, Oltinda kuchli impuls paydo qiladi."
    )

    if active_event:
        if active_event.state == EventState.SCHEDULED:
            # Not analyzed yet: preview the same macro engine the T-3h step will run
            preview = macro_engine.analyze_event(active_event.title, active_event.forecast, active_event.previous)
            is_bullish = preview.macro_score < 0
            ai_reason = preview.bias_summary
        else:
            is_bullish = (active_event.macro_score or 0.0) < 0
            ai_reason = active_event.analysis_summary or ai_reason

    # Format Tashkent time (UTC+5)
    tashkent_time_str = "Bugun 17:30 da"
    if active_event and active_event.event_time:
        aware_dt = make_aware(active_event.event_time)
        tashkent_dt = aware_dt.astimezone(timezone(timedelta(hours=5)))
        tashkent_time_str = tashkent_dt.strftime("%d.%m.%Y, %H:%M (Toshkent vaqti)")

    # Query latest signal from db if any
    signal_query = select(SniperSignal).order_by(SniperSignal.id.desc()).limit(1)
    sig_res = await db.execute(signal_query)
    db_signal = sig_res.scalar_one_or_none()

    # Once the 4:58 signal exists for this event, show exactly what was sent to Telegram
    event_signal = (
        db_signal
        if db_signal and active_event and db_signal.event_id == active_event.id and db_signal.status != "NO_TRADE"
        else None
    )
    confidence = 85
    if event_signal:
        is_bullish = "BUY" in event_signal.bias
        confidence = event_signal.confidence

    # Market order uses the same formula as sniper_decision (ATR * 1.8 + news spread / ATR * 3.5)
    atr = event_signal.atr_m15 if event_signal else 4.50
    sl_dist = atr * 1.8 + multi_asset_engine.get_specs("XAUUSD").typical_news_spread
    tp_dist = atr * 3.5
    market_sl = round(live_price - sl_dist if is_bullish else live_price + sl_dist, 2)
    market_tp = round(live_price + tp_dist if is_bullish else live_price - tp_dist, 2)

    if event_signal:
        stop_entry, stop_sl, stop_tp = event_signal.stop_break_price, event_signal.stop_sl, event_signal.stop_tp
    else:
        stop_entry = round(live_price + 6.00 if is_bullish else live_price - 6.00, 2)
        stop_sl = round(live_price - 4.50 if is_bullish else live_price + 4.50, 2)
        stop_tp = round(live_price + 16.00 if is_bullish else live_price - 16.00, 2)

    latest_signal_dict = {
        "id": db_signal.id if db_signal else 1,
        "bias": db_signal.bias if db_signal else ("BULLISH (BUY)" if is_bullish else "BEARISH (SELL)"),
        "confidence": db_signal.confidence if db_signal else 85,
        "limit_trap": {
            "type": db_signal.limit_trap_type if db_signal else ("BUY_LIMIT" if is_bullish else "SELL_LIMIT"),
            "price": db_signal.limit_trap_price if db_signal else round(live_price - 7.50 if is_bullish else live_price + 7.50, 2),
            "sl": db_signal.limit_sl if db_signal else round(live_price - 14.50 if is_bullish else live_price + 14.50, 2),
            "tp": db_signal.limit_tp if db_signal else round(live_price + 18.00 if is_bullish else live_price - 18.00, 2),
        },
        "stop_breakout": {
            "type": db_signal.stop_break_type if db_signal else ("BUY_STOP" if is_bullish else "SELL_STOP"),
            "price": db_signal.stop_break_price if db_signal else stop_entry,
            "sl": db_signal.stop_sl if db_signal else stop_sl,
            "tp": db_signal.stop_tp if db_signal else stop_tp,
        },
    }

    return {
        "status": "online",
        "current_time_utc": now.isoformat(),
        "live_price": live_price,
        "is_bullish": is_bullish,
        "confidence": confidence,
        "active_event": {
            "title": active_event.title if active_event else "AQSH: Ishsizlik Arzalari (Unemployment Claims)",
            "state": active_event.state if active_event else "SCHEDULED",
            "event_time": make_aware(active_event.event_time).isoformat() if active_event else None,
            "tashkent_time_str": tashkent_time_str,
            "ai_reason": ai_reason,
            "forecast": active_event.forecast if active_event else 200.0,
            "previous": active_event.previous if active_event else 199.0,
        },
        "latest_signal": latest_signal_dict,
        "market_order": {
            "action": "BUY" if is_bullish else "SELL",
            "entry": live_price,
            "sl": market_sl,
            "tp": market_tp,
        },
        "stop_order": {
            "action": "BUY_STOP" if is_bullish else "SELL_STOP",
            "entry": stop_entry,
            "sl": stop_sl,
            "tp": stop_tp,
        },
        "weekly_calendar": weekly_schedule,
    }
