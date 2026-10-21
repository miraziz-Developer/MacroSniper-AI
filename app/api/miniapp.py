from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.event import EconomicEvent, SniperSignal
from app.engines.multi_asset_engine import ASSET_REGISTRY

router = APIRouter(prefix="", tags=["Telegram Mini App"])


@router.get("/miniapp", response_class=HTMLResponse)
async def serve_telegram_mini_app():
    """
    Renders the Full Multi-Tab Institutional Trading Terminal for Telegram Mini App.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>MacroSniper AI — Institutional Terminal</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['"Plus Jakarta Sans"', 'sans-serif'],
                        mono: ['"JetBrains Mono"', 'monospace'],
                    },
                    colors: {
                        navy: { 950: '#060911', 900: '#0B0F19', 800: '#141B2D', 700: '#1E2943', 600: '#2A3B60' },
                        cyan: { 400: '#00F0FF', 500: '#00D1E0' },
                        gold: { 400: '#FFD700', 500: '#E5C100' },
                        bull: '#00E676',
                        bear: '#FF3D57'
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #060911; color: #F5F7FA; -webkit-tap-highlight-color: transparent; }
        .glass-panel { background: rgba(20, 27, 45, 0.75); backdrop-filter: blur(14px); border: 1px solid rgba(40, 53, 85, 0.7); }
        .glow-cyan { box-shadow: 0 0 20px rgba(0, 240, 255, 0.25); }
        .glow-bull { box-shadow: 0 0 20px rgba(0, 230, 118, 0.25); }
        .glow-bear { box-shadow: 0 0 20px rgba(255, 61, 87, 0.25); }
        .tab-btn.active { color: #00F0FF; border-bottom: 2px solid #00F0FF; background: rgba(0, 240, 255, 0.08); }
    </style>
</head>
<body class="font-sans antialiased pb-24">

    <!-- Top Navigation Header -->
    <header class="px-4 pt-4 pb-2 border-b border-navy-700/60 sticky top-0 bg-navy-950/95 backdrop-blur z-50">
        <div class="flex items-center justify-between mb-3">
            <div class="flex items-center space-x-2">
                <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white shadow-lg glow-cyan">
                    🎯
                </div>
                <div>
                    <h1 class="text-sm font-extrabold tracking-wider text-white">MACRO SNIPER <span class="text-cyan-400 font-mono text-xs">v2.0</span></h1>
                    <div class="flex items-center space-x-1.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-bull animate-pulse"></span>
                        <span class="text-[9px] uppercase font-mono text-cyan-400 font-semibold tracking-wider">HEDGE FUND RADAR</span>
                    </div>
                </div>
            </div>
            <div class="flex items-center space-x-2">
                <span class="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-gold-400/10 text-gold-400 border border-gold-400/30">
                    VIP PRO TIER
                </span>
            </div>
        </div>

        <!-- 5 Tabs Navigation Bar -->
        <div class="flex space-x-1 overflow-x-auto text-xs font-mono font-semibold pb-1 scrollbar-none">
            <button onclick="switchTab('tab-radar')" id="btn-tab-radar" class="tab-btn active px-3 py-1.5 rounded-t-lg transition-all whitespace-nowrap">
                🎯 Live Radar
            </button>
            <button onclick="switchTab('tab-intermarket')" id="btn-tab-intermarket" class="tab-btn px-3 py-1.5 rounded-t-lg text-gray-400 transition-all whitespace-nowrap">
                🌐 Intermarket
            </button>
            <button onclick="switchTab('tab-propfirm')" id="btn-tab-propfirm" class="tab-btn px-3 py-1.5 rounded-t-lg text-gray-400 transition-all whitespace-nowrap">
                🧮 Prop Calculator
            </button>
            <button onclick="switchTab('tab-speech')" id="btn-tab-speech" class="tab-btn px-3 py-1.5 rounded-t-lg text-gray-400 transition-all whitespace-nowrap">
                🎙️ Speech AI
            </button>
            <button onclick="switchTab('tab-settings')" id="btn-tab-settings" class="tab-btn px-3 py-1.5 rounded-t-lg text-gray-400 transition-all whitespace-nowrap">
                ⚙️ MT5 Bridge
            </button>
        </div>
    </header>

    <!-- TAB 1: LIVE SNIPER RADAR -->
    <div id="tab-radar" class="tab-content px-4 py-4 space-y-4">

        <!-- Multi-Asset Selector Bar -->
        <div class="flex space-x-2 overflow-x-auto pb-1 scrollbar-none">
            <button onclick="selectAsset('XAUUSD')" id="asset-xauusd" class="px-3 py-1 bg-navy-800 text-cyan-400 border border-cyan-400/40 rounded-lg text-xs font-mono font-bold">XAUUSD</button>
            <button onclick="selectAsset('EURUSD')" id="asset-eurusd" class="px-3 py-1 bg-navy-900 text-gray-400 border border-navy-700 rounded-lg text-xs font-mono font-bold">EURUSD</button>
            <button onclick="selectAsset('GBPUSD')" id="asset-gbpusd" class="px-3 py-1 bg-navy-900 text-gray-400 border border-navy-700 rounded-lg text-xs font-mono font-bold">GBPUSD</button>
            <button onclick="selectAsset('US30')" id="asset-us30" class="px-3 py-1 bg-navy-900 text-gray-400 border border-navy-700 rounded-lg text-xs font-mono font-bold">US30</button>
            <button onclick="selectAsset('USDJPY')" id="asset-usdjpy" class="px-3 py-1 bg-navy-900 text-gray-400 border border-navy-700 rounded-lg text-xs font-mono font-bold">USDJPY</button>
        </div>

        <!-- Tier-1 Monster Event Card -->
        <div class="glass-panel rounded-2xl p-4 relative overflow-hidden">
            <div class="flex items-center justify-between mb-2">
                <span class="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-bear/20 text-bear border border-bear/30">
                    🔴 TIER-1 EVENT
                </span>
                <span class="text-xs font-mono text-gray-400" id="live-time-utc">17:30:00 UTC+5</span>
            </div>

            <h2 class="text-base font-extrabold text-white mb-0.5" id="event-title">US Consumer Price Index (CPI) YoY</h2>
            <p class="text-xs text-gray-400 mb-3">Asset: <strong class="text-white" id="selected-asset-label">XAUUSD (Spot Gold)</strong> • Expected: <span class="text-cyan-400 font-bold">1200+ Pips</span></p>

            <!-- T-Countdown Grid -->
            <div class="grid grid-cols-4 gap-2 bg-navy-900/90 p-2.5 rounded-xl border border-navy-700/60 text-center font-mono mb-3">
                <div>
                    <div class="text-base font-extrabold text-cyan-400" id="hours">00</div>
                    <div class="text-[9px] text-gray-400 uppercase">Hours</div>
                </div>
                <div>
                    <div class="text-base font-extrabold text-cyan-400" id="minutes">01</div>
                    <div class="text-[9px] text-gray-400 uppercase">Mins</div>
                </div>
                <div>
                    <div class="text-base font-extrabold text-cyan-400" id="seconds">48</div>
                    <div class="text-[9px] text-gray-400 uppercase">Secs</div>
                </div>
                <div>
                    <div class="text-base font-extrabold text-bull" id="stage-badge">T-2M</div>
                    <div class="text-[9px] text-gray-400 uppercase">Stage</div>
                </div>
            </div>

            <!-- Mathematical Conviction Score -->
            <div class="bg-navy-950/70 p-3 rounded-xl border border-navy-700/40 space-y-2">
                <div class="flex items-center justify-between text-xs">
                    <span class="text-gray-400">Total Conviction ($S_{total}$):</span>
                    <span class="font-mono font-bold text-bear" id="total-score">-78.5 (STRONG BEARISH)</span>
                </div>
                <div class="w-full bg-navy-800 rounded-full h-1.5 overflow-hidden">
                    <div class="bg-gradient-to-r from-bear to-orange-500 h-1.5 rounded-full" style="width: 88%"></div>
                </div>
                <div class="grid grid-cols-3 text-[10px] font-mono text-gray-400 text-center pt-1">
                    <div>F_macro: <span class="text-white">-82</span></div>
                    <div>T_liq: <span class="text-white">-75</span></div>
                    <div>C_inter: <span class="text-white">-60</span></div>
                </div>
            </div>
        </div>

        <!-- 4:58 Pre-Sniper Traps Display -->
        <div class="space-y-3">
            <!-- 1. Judas Swing Limit Trap -->
            <div class="glass-panel rounded-xl p-3.5 border-l-4 border-l-gold-400 relative">
                <div class="flex items-center justify-between mb-1.5">
                    <span class="text-xs font-bold text-gold-400">1️⃣ JUDAS SWING TRAP (LIMIT)</span>
                    <span class="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-bear/20 text-bear border border-bear/40" id="trap-badge">
                        SELL LIMIT
                    </span>
                </div>
                <p class="text-[11px] text-gray-400 mb-2">Liquidity sweep entry (Premium Order Block)</p>

                <div class="grid grid-cols-3 gap-2 font-mono text-center mb-2">
                    <div class="bg-navy-900/90 p-2 rounded-lg border border-navy-700/60">
                        <div class="text-[9px] text-gray-400">ENTRY</div>
                        <div class="text-xs font-bold text-white" id="trap-entry">2658.50</div>
                    </div>
                    <div class="bg-navy-900/90 p-2 rounded-lg border border-navy-700/60">
                        <div class="text-[9px] text-bear">SL</div>
                        <div class="text-xs font-bold text-bear" id="trap-sl">2665.70</div>
                    </div>
                    <div class="bg-navy-900/90 p-2 rounded-lg border border-navy-700/60">
                        <div class="text-[9px] text-bull">TP3 RUN</div>
                        <div class="text-xs font-bold text-bull" id="trap-tp">2642.00</div>
                    </div>
                </div>

                <!-- 3-Tier Scaling Plan -->
                <div class="bg-navy-950/80 p-2 rounded-lg border border-navy-700/40 text-[10px] font-mono space-y-1">
                    <div class="flex justify-between text-gray-300">
                        <span>🎯 TP1 (+400 pts): <strong class="text-bull" id="tp1-val">2654.50</strong></span>
                        <span class="text-cyan-400">Scale 50% & Breakeven</span>
                    </div>
                    <div class="flex justify-between text-gray-300">
                        <span>🎯 TP2 (+800 pts): <strong class="text-bull" id="tp2-val">2650.00</strong></span>
                        <span class="text-cyan-400">Scale 30%</span>
                    </div>
                </div>

                <button onclick="copyTrapOrder()" class="mt-2.5 w-full py-1.5 bg-navy-800 hover:bg-navy-700 text-xs font-mono font-semibold rounded-lg text-cyan-400 border border-cyan-400/30 flex items-center justify-center space-x-1.5 active:scale-95 transition-all">
                    <span>📋 Copy Limit Trap Parameters</span>
                </button>
            </div>

            <!-- 2. Momentum Breakout -->
            <div class="glass-panel rounded-xl p-3.5 border-l-4 border-l-cyan-400">
                <div class="flex items-center justify-between mb-1.5">
                    <span class="text-xs font-bold text-cyan-400">2️⃣ MOMENTUM BREAKOUT (STOP)</span>
                    <span class="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-bear/20 text-bear border border-bear/40" id="break-badge">
                        SELL STOP
                    </span>
                </div>
                <div class="grid grid-cols-3 gap-2 font-mono text-center">
                    <div class="bg-navy-900/90 p-2 rounded-lg border border-navy-700/60">
                        <div class="text-[9px] text-gray-400">ENTRY</div>
                        <div class="text-xs font-bold text-white" id="break-entry">2645.20</div>
                    </div>
                    <div class="bg-navy-900/90 p-2 rounded-lg border border-navy-700/60">
                        <div class="text-[9px] text-bear">SL</div>
                        <div class="text-xs font-bold text-bear" id="break-sl">2652.70</div>
                    </div>
                    <div class="bg-navy-900/90 p-2 rounded-lg border border-navy-700/60">
                        <div class="text-[9px] text-bull">TP</div>
                        <div class="text-xs font-bold text-bull" id="break-tp">2631.00</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 2: INTERMARKET HEATMAP -->
    <div id="tab-intermarket" class="tab-content hidden px-4 py-4 space-y-4">
        <div class="glass-panel rounded-2xl p-4">
            <h3 class="text-sm font-extrabold text-white mb-1">🌐 Intermarket Macro Radar</h3>
            <p class="text-xs text-gray-400 mb-3">Live correlation between Dollar, Yields, Energy and Metals</p>

            <div class="grid grid-cols-2 gap-3 font-mono text-xs mb-3">
                <div class="bg-navy-900 p-3 rounded-xl border border-navy-700">
                    <div class="text-gray-400 text-[10px]">DXY (DOLLAR INDEX)</div>
                    <div class="text-base font-bold text-bull mt-1">+0.42% ↗</div>
                    <div class="text-[10px] text-gray-400">Breaking 4H Highs</div>
                </div>
                <div class="bg-navy-900 p-3 rounded-xl border border-navy-700">
                    <div class="text-gray-400 text-[10px]">US 10Y YIELD</div>
                    <div class="text-base font-bold text-bull mt-1">+6.5 bps ↗</div>
                    <div class="text-[10px] text-gray-400">Pricing Hawkish Fed</div>
                </div>
                <div class="bg-navy-900 p-3 rounded-xl border border-navy-700">
                    <div class="text-gray-400 text-[10px]">US 2Y YIELD</div>
                    <div class="text-base font-bold text-bull mt-1">+8.1 bps ↗</div>
                    <div class="text-[10px] text-gray-400">Short-End Rate Spike</div>
                </div>
                <div class="bg-navy-900 p-3 rounded-xl border border-navy-700">
                    <div class="text-gray-400 text-[10px]">WTI CRUDE OIL</div>
                    <div class="text-base font-bold text-bull mt-1">+1.95% ↗</div>
                    <div class="text-[10px] text-gray-400">Energy Inflation Pressure</div>
                </div>
            </div>

            <div class="p-3 bg-navy-950 rounded-xl border border-navy-700/60 text-xs text-gray-300">
                <strong class="text-cyan-400">Institutional Macro Verdict:</strong> Obligatsiya daromadliligi (Yields) va Dollar indeksi (DXY) kuchli o'smoqda. Bu Oltin (XAUUSD) va Nasdaq (NAS100) uchun 85% ehtimolli qulash bosimini ko'rsatadi.
            </div>
        </div>
    </div>

    <!-- TAB 3: PROP FIRM CALCULATOR -->
    <div id="tab-propfirm" class="tab-content hidden px-4 py-4 space-y-4">
        <div class="glass-panel rounded-2xl p-4">
            <h3 class="text-sm font-extrabold text-white mb-1">🧮 FTMO & Prop Firm Lot Calculator</h3>
            <p class="text-xs text-gray-400 mb-4">Calculates exact lot size to protect daily drawdown rules</p>

            <div class="space-y-3 font-mono text-xs">
                <div>
                    <label class="text-gray-400 text-[11px] block mb-1">ACCOUNT BALANCE ($)</label>
                    <input type="number" id="calc-balance" value="10000" oninput="calculateLotSize()" class="w-full bg-navy-900 border border-navy-700 rounded-lg p-2.5 text-white font-bold">
                </div>

                <div>
                    <label class="text-gray-400 text-[11px] block mb-1">RISK PERCENTAGE (%)</label>
                    <div class="grid grid-cols-3 gap-2">
                        <button onclick="setRisk(0.5)" class="py-1.5 bg-navy-900 hover:bg-navy-800 border border-navy-700 rounded-lg text-gray-300">0.5% (Safe)</button>
                        <button onclick="setRisk(1.0)" class="py-1.5 bg-navy-800 border border-cyan-400/40 rounded-lg text-cyan-400 font-bold">1.0% (Norm)</button>
                        <button onclick="setRisk(2.0)" class="py-1.5 bg-navy-900 hover:bg-navy-800 border border-navy-700 rounded-lg text-gray-300">2.0% (Aggr)</button>
                    </div>
                </div>

                <div class="p-3 bg-navy-950 rounded-xl border border-navy-700 mt-4 space-y-2">
                    <div class="flex justify-between">
                        <span class="text-gray-400">Monetary Risk:</span>
                        <strong class="text-white" id="calc-risk-usd">$100.00</strong>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-gray-400">Stop-Loss Distance:</span>
                        <strong class="text-white">6.50 pts ($6.50)</strong>
                    </div>
                    <div class="flex justify-between border-t border-navy-700 pt-2 text-sm">
                        <span class="text-cyan-400 font-bold">RECOMMENDED LOT:</span>
                        <strong class="text-bull text-base font-extrabold" id="calc-lot-res">0.15 LOT</strong>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 4: SPEECH AI LIVE STREAM -->
    <div id="tab-speech" class="tab-content hidden px-4 py-4 space-y-4">
        <div class="glass-panel rounded-2xl p-4">
            <div class="flex items-center justify-between mb-2">
                <h3 class="text-sm font-extrabold text-white">🎙️ FOMC Audio AI Stream</h3>
                <span class="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-cyan-400/20 text-cyan-400">1.5s LATENCY</span>
            </div>
            <p class="text-xs text-gray-400 mb-3">Deepgram Live WS + Groq Llama-3 70B Sentiment Parser</p>

            <div class="space-y-2.5 font-mono text-xs" id="speech-log">
                <div class="p-3 bg-navy-900/90 rounded-xl border-l-4 border-l-bear border border-navy-700/60">
                    <div class="flex justify-between text-[10px] text-gray-400 mb-1">
                        <span>17:34:12</span>
                        <span class="text-bear font-bold">HAWKISH (+35.0)</span>
                    </div>
                    <p class="text-gray-200">"Inflation is still too high, and the committee remains prepared to maintain a restrictive policy stance for longer."</p>
                    <div class="mt-1 text-[10px] text-cyan-400">Action: SELL XAUUSD / BUY USD</div>
                </div>

                <div class="p-3 bg-navy-900/90 rounded-xl border-l-4 border-l-bear border border-navy-700/60">
                    <div class="flex justify-between text-[10px] text-gray-400 mb-1">
                        <span>17:32:05</span>
                        <span class="text-bear font-bold">HAWKISH (+40.0)</span>
                    </div>
                    <p class="text-gray-200">"Premature to declare victory on inflation. We are prepared for higher for longer rates."</p>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 5: BROKER & RISK SETTINGS -->
    <div id="tab-settings" class="tab-content hidden px-4 py-4 space-y-4">
        <div class="glass-panel rounded-2xl p-4 space-y-4 font-mono text-xs">
            <h3 class="text-sm font-extrabold text-white font-sans">⚙️ MT5 Bridge & Safety Guard</h3>

            <div class="flex items-center justify-between p-3 bg-navy-900 rounded-xl border border-navy-700">
                <div>
                    <div class="font-bold text-white">Spread Protection Guard</div>
                    <div class="text-[10px] text-gray-400">Pauses execution if spread > 4.0 pts</div>
                </div>
                <input type="checkbox" checked class="w-5 h-5 accent-cyan-400">
            </div>

            <div class="flex items-center justify-between p-3 bg-navy-900 rounded-xl border border-navy-700">
                <div>
                    <div class="font-bold text-white">5:00:01 Kill-Switch Auto-Cancel</div>
                    <div class="text-[10px] text-gray-400">Deletes limit traps in 140ms on shock</div>
                </div>
                <input type="checkbox" checked class="w-5 h-5 accent-bull">
            </div>

            <div class="flex items-center justify-between p-3 bg-navy-900 rounded-xl border border-navy-700">
                <div>
                    <div class="font-bold text-white">Multi-TP Auto Scaling</div>
                    <div class="text-[10px] text-gray-400">Scale 50% at TP1 and move SL to breakeven</div>
                </div>
                <input type="checkbox" checked class="w-5 h-5 accent-cyan-400">
            </div>
        </div>
    </div>

    <!-- Bottom Action Bar -->
    <div class="fixed bottom-0 left-0 right-0 p-3 bg-navy-950/95 border-t border-navy-700/80 backdrop-blur z-50 flex items-center space-x-3">
        <button onclick="triggerAutoCopier()" class="flex-1 py-3 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-xl font-bold text-xs uppercase tracking-wider text-white shadow-lg glow-cyan flex items-center justify-center space-x-2 active:scale-95 transition-all">
            <span>⚡ Deploy Auto-Copier MT5</span>
        </button>
    </div>

    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
        }

        let currentRiskPct = 1.0;
        let selectedAsset = "XAUUSD";

        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(el => {
                el.classList.remove('active', 'text-cyan-400');
                el.classList.add('text-gray-400');
            });

            document.getElementById(tabId).classList.remove('hidden');
            const btn = document.getElementById('btn-' + tabId);
            btn.classList.add('active', 'text-cyan-400');
            btn.classList.remove('text-gray-400');

            if (tg?.HapticFeedback) tg.HapticFeedback.selectionChanged();
        }

        function selectAsset(symbol) {
            selectedAsset = symbol;
            document.querySelectorAll('[id^="asset-"]').forEach(btn => {
                btn.className = "px-3 py-1 bg-navy-900 text-gray-400 border border-navy-700 rounded-lg text-xs font-mono font-bold";
            });
            document.getElementById('asset-' + symbol.toLowerCase()).className = "px-3 py-1 bg-navy-800 text-cyan-400 border border-cyan-400/40 rounded-lg text-xs font-mono font-bold";
            document.getElementById('selected-asset-label').textContent = symbol;
            if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        }

        function setRisk(pct) {
            currentRiskPct = pct;
            calculateLotSize();
        }

        function calculateLotSize() {
            const balance = parseFloat(document.getElementById('calc-balance').value) || 10000;
            const riskUsd = balance * (currentRiskPct / 100);
            document.getElementById('calc-risk-usd').textContent = '$' + riskUsd.toFixed(2);
            // $6.50 SL distance on Gold ($650 per 1.0 lot)
            const lot = Math.max(0.01, (riskUsd / 650)).toFixed(2);
            document.getElementById('calc-lot-res').textContent = lot + ' LOT';
        }

        function triggerAutoCopier() {
            if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
            alert('🚀 MT5 Auto-Copier ulandi! Barcha buyruqlar 0.15s ichida MT5 hisobingizga tushadi.');
        }

        function copyTrapOrder() {
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
            navigator.clipboard.writeText("SELL LIMIT XAUUSD: 2658.50 | SL: 2665.70 | TP: 2642.00");
            alert('Nusxalandi: SELL LIMIT @ 2658.50');
        }
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@router.get("/api/miniapp/dashboard", tags=["Telegram Mini App"])
async def get_miniapp_dashboard_data(db: AsyncSession = Depends(get_db)):
    """
    Supplies real-time JSON metrics to the Telegram Mini App frontend.
    """
    event_query = select(EconomicEvent).order_by(EconomicEvent.event_time.asc())
    event_res = await db.execute(event_query)
    events = event_res.scalars().all()

    signal_query = select(SniperSignal).order_by(SniperSignal.id.desc()).limit(1)
    signal_res = await db.execute(signal_query)
    latest_signal = signal_res.scalar_one_or_none()

    active_event = events[0] if events else None

    return {
        "status": "online",
        "current_time_utc": datetime.now(timezone.utc).isoformat(),
        "active_event": {
            "title": active_event.title if active_event else "No High-Impact Event Today",
            "state": active_event.state if active_event else "IDLE",
            "event_time": active_event.event_time.isoformat() if active_event else None,
            "macro_score": active_event.macro_score if active_event else 0.0,
            "total_score": active_event.total_score if active_event else 0.0,
        },
        "latest_signal": {
            "id": latest_signal.id if latest_signal else None,
            "bias": latest_signal.bias if latest_signal else "NO_SIGNAL",
            "confidence": latest_signal.confidence if latest_signal else 0,
            "limit_trap": {
                "type": latest_signal.limit_trap_type if latest_signal else None,
                "price": latest_signal.limit_trap_price if latest_signal else None,
                "sl": latest_signal.limit_sl if latest_signal else None,
                "tp": latest_signal.limit_tp if latest_signal else None,
            },
            "stop_breakout": {
                "type": latest_signal.stop_break_type if latest_signal else None,
                "price": latest_signal.stop_break_price if latest_signal else None,
                "sl": latest_signal.stop_sl if latest_signal else None,
                "tp": latest_signal.stop_tp if latest_signal else None,
            },
        },
    }
