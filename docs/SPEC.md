# MacroSniper — Refactoring Spetsifikatsiyasi (v2)

## 1. G'oya

USD bo'yicha Tier-1 yangiliklar (CPI, NFP, FOMC, Claims, PCE, PPI, Retail Sales, GDP, ISM)
oldidan XAUUSD uchun **haqiqiy bozor ma'lumotiga asoslangan** savdo rejasini VIP obunachilarga
Telegram va Mini App orqali beradi, yangilik chiqqach natijani tasdiqlaydi.

## 2. Eski versiyadagi asosiy muammolar

| Muammo | Oqibat |
|---|---|
| Macro/intermarket kirishlari kodga yozilgan konstantalar | Har CPI = doim SELL, har FOMC = doim hawkish |
| Likvidlik zonalari = narx ± $8.10, ATR = doim 4.50 | Darajalar bozorga bog'liq emas |
| "AI" yo'q, MT5 Renderda ishlamaydi, Speech AI ulanmagan | Va'da qilingan funksiyalar ishlamaydi |
| Actual manbasi yo'q | Natija bosqichi hech qachon avtomatik ishlamaydi |
| Obuna/to'lov yo'q, Mini App hammaga ochiq | VIP kontent bepul |
| SQLite Renderda har restartda o'chadi | Holatlar yo'qoladi |

## 3. Signal mantiqi (tarixda tekshirilgan)

Asos: [research/REPORT.md](../research/REPORT.md) — ForexFactory tarixi 2012–2025 + Dukascopy XAUUSD
1 daqiqalik shamlar, barcha modellar walk-forward (faqat o'tmish bilan o'qitilgan).

Topilmalar:
- Yangilikdan **oldin** oltin yo'nalishini bepul ma'lumot bilan bashorat qilib bo'lmaydi (~52%, tanga darajasi).
  Shuning uchun tizim "BUY 85%" kabi yo'nalish da'vo qilmaydi.
- Raqam chiqqach oltin syurprizga qarshi tomonga 1 daqiqada 73–88% hollarda harakat qiladi —
  bu foydalanuvchiga **ssenariy ehtimoli** sifatida beriladi ("fakt yuqori → oltin 84% hollarda tushgan").
- OCO straddle faqat NFP'da barqaror musbat (2012–2020 +0.68R, 2021–2025 +0.64R), CPI zaif musbat;
  boshqa yangiliklarda manfiy. Reja faqat backtest'i musbat bo'lgan yangiliklarga beriladi.

Bosqichlar (faqat rejaga loyiq yangiliklar uchun):
1. **T-2h — Preview:** tarixiy ssenariylar va rejaning tarixiy natijasi.
2. **T-2m — Reja:** 15m ATR(14) va 4 soatlik diapazon; kirish diapazondan tashqarida 0.3–0.8 ATR,
   SL 2 ATR (=1R), TP1 1.5R (yarmi, SL→kirish), TP2 3R, 30 daqiqada ochilmasa bekor, 2 soatda yopiladi.
3. **T+0 — Natija:** fakt − prognoz → kutilgan yo'nalish va uning tarixiy ehtimoli.
4. **T+2h — Hisob:** reja haqiqiy 1 daqiqalik shamlar bo'yicha backtest bilan **bir xil kod**
   (`app/signals/plan.py::simulate`) orqali baholanadi, natija R da saqlanadi va ochiq ko'rsatiladi.

Parametrlar va statistikalar `research/analyze.py` → `app/signals/stats.json` orqali yangilanadi.

## 4. Ma'lumot manbalari (bepul)

| Ma'lumot | Asosiy | Zaxira |
|---|---|---|
| Oltin narxi, 15m va 1m shamlar | Binance `PAXGUSDT` | Yahoo `GC=F` |
| Tarix (tadqiqot) | Hugging Face `Tropstan/Forex_Factory_Calendar` (MIT), Dukascopy | — |
| Kalendar | ForexFactory haftalik JSON (1 soat kesh + disk kesh): USD High + rejalashtiriladigan Medium (Claims, PMI…) | — |
| Actual | `FMP_API_KEY` bo'lsa avtomatik; admin `/actual`; admin webhook | — |

Tashqi so'rovlar: timeout, keshlash. Narx manbasi ishlamasa signal **yuborilmaydi**
(soxta qiymat ishlatilmaydi) va adminga xabar ketadi.

## 5. Obuna

- To'lov: **Telegram Stars (XTR)** — Telegram raqamli tovarlar uchun talab qiladi,
  serverda karta ma'lumoti yo'q, tashqi provayder kerak emas.
- Signallar faol VIP'larga shaxsiy xabar (DM); ixtiyoriy kanalga qisqa anons va natija.
- Muddati tugaganda avtomatik FREE.

## 6. Mini App

- HTML alohida faylda. API so'rovlari Telegram `initData` HMAC imzosi bilan tekshiriladi.
- FREE: kalendar + o'tgan natijalar. VIP: joriy reja va darajalar.
- Ko'rsatiladigan raqamlar = Telegram'ga yuborilgan reja (bitta manba: DB).

## 7. Admin

Bot buyruqlari (`TELEGRAM_ADMIN_IDS`): `/stats`, `/grant <tg_id> <kun>`, `/revoke <tg_id>`,
`/actual <event_id> <qiymat>`. HTTP admin endpointlari `X-Admin-Token` bilan.

## 8. Arxitektura

Modulli monolit, bitta jarayon (FastAPI + aiogram polling + APScheduler), bitta instans.

```
app/
  core/       config, db, security (initData, admin token)
  market/     data.py (Yahoo/Binance), indicators.py (ATR, diapazon)
  calendar/   forexfactory.py, actuals.py
  signals/    rules.py, context.py, plan.py, outcome.py   — sof funksiyalar
  pipeline/   orchestrator.py, scheduler.py               — idempotent bosqichlar
  billing/    subscriptions.py
  telegram/   bot.py, handlers.py, admin.py, notifier.py, texts.py
  miniapp/    routes.py, index.html
  main.py
```

Idempotentlik: har bosqich `event_stages(event_id, stage)` unikal yozuvi bilan belgilanadi —
restartdan keyin ham xabar ikki marta ketmaydi.

## 9. Infratuzilma (bepul)

- DB: **Neon** bepul doimiy Postgres (`DATABASE_URL`); SQLite faqat lokal/test.
  `postgres://` avtomatik `postgresql+asyncpg://` ga aylantiriladi.
- Render free + UptimeRobot `/health` har 5 daqiqada (aks holda server uxlaydi).
- Versiyalar qotirilgan, `PYTHON_VERSION=3.12.7`.

## 10. Olib tashlandi

MT5 auto-copier (Linux'da ishlamaydi), Live Speech AI (ulanmagan), multi-asset,
tasdiqlanmagan va'dalar ("AI", "0.2 soniya", "500–2000 punkt").

## 11. Risklar

- Yahoo rasmiy API emas: format o'zgarishi mumkin (zaxira — Binance).
- FMP bepul tarifida actual kechikishi mumkin; ishonchli yo'l — admin `/actual`.
- Moliyaviy maslahat emas; har xabarda risk ogohlantirishi.
