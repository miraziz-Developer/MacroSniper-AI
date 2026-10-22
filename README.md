# MacroSniper v2 — XAUUSD makro yangilik rejalari

AQSH Tier-1 yangiliklari (CPI, NFP, FOMC, Claims, PCE, PPI, Retail Sales, GDP, ISM) uchun
XAUUSD bo'yicha **haqiqiy bozor ma'lumotiga asoslangan** savdo rejasini Telegram bot va Mini App
orqali VIP obunachilarga beradi. To'lov — Telegram Stars. Batafsil dizayn: [docs/SPEC.md](docs/SPEC.md).

## Qanday ishlaydi

Hammasi 2012–2025 tarixida walk-forward usulida tekshirilgan: [research/REPORT.md](research/REPORT.md).

```
ForexFactory (har 10 daq, GitHub mirror zaxira) ─► Event
   T-2h  ─► Preview: "fakt yuqori → oltin X% hollarda tushgan" + rejaning tarixiy natijasi
   T-2m  ─► Reja: 15m ATR + 4 soatlik diapazon ─► BUY STOP / SELL STOP (OCO)
   T+20s ─► Fakt: FMP (kalit bo'lsa) yoki admin /actual ─► kutilgan yo'nalish + tarixiy %
   T+2h  ─► Hisob: reja 1 daqiqalik shamlar bo'yicha baholanadi (R), /results va Mini App'da ochiq
```

- Yangilikdan **oldin** yo'nalishni hech kim aniq bilmaydi — tarix buni tasdiqlaydi (~52%), shuning
  uchun tizim yo'nalish foizini to'qib chiqarmaydi, faqat tekshirilgan ssenariy ehtimollarini beradi.
- Reja faqat tarixda foyda bergan yangiliklarga beriladi (hozir NFP va CPI).
- Har bosqich DB'da bir marta belgilanadi — restartdan keyin xabar takrorlanmaydi.
- Narx ma'lumoti olinmasa reja **yuborilmaydi** (soxta raqam yo'q).

Tadqiqotni qayta ishga tushirish (ma'lumotlar repoga kirmaydi):

```bash
pip install pandas numpy httpx
PYTHONPATH=. python research/analyze.py DATA_DIR   # REPORT.md va app/signals/stats.json yangilanadi
```

## Bot buyruqlari

| Hamma | Admin (`TELEGRAM_ADMIN_IDS`) |
|---|---|
| `/start` `/events` `/plan` `/results` `/status` `/vip` `/paysupport` | `/stats` · `/grant ID KUN` · `/revoke ID` · `/actual EVENT_ID QIYMAT` (ID'lar `/events` da) |

## Lokal ishga tushirish

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN va TELEGRAM_ADMIN_IDS ni to'ldiring
uvicorn app.main:app --reload
pytest -q
```

## Render'ga bepul deploy

1. **Neon** (neon.tech) da bepul Postgres yarating va connection string'ni oling.
   Render'dagi SQLite har restartda o'chadi — obunalar yo'qolmasligi uchun Postgres shart.
2. Render → Blueprint → shu repo (`render.yaml`). Environment'da to'ldiring:
   `DATABASE_URL` (Neon), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`, ixtiyoriy `TELEGRAM_CHANNEL_ID`, `FMP_API_KEY`.
3. Uyg'oq turish avtomatik: Render `RENDER_EXTERNAL_URL` ni o'zi beradi va server har 10 daqiqada
   o'zining `/health` manzilini chaqiradi (bepul server 15 daqiqada uxlaydi). Qo'shimcha xizmat kerak emas.
4. @BotFather → Bot Settings → Menu Button / Mini App URL: `https://<servis>.onrender.com/miniapp`.
5. Kanal ishlatsangiz, botni kanalga admin qiling.

## Admin HTTP API

`X-Admin-Token: <ADMIN_API_TOKEN>` header bilan:

- `POST /api/admin/sync` — kalendarni hozir yangilash
- `POST /api/admin/events/{id}/actual` `{"value": 0.4}` — faktni kiritish
- `POST /api/admin/events/{id}/run/{context|plan}` — bosqichni qo'lda ishga tushirish (baribir bir marta)

Ommaviy: `GET /health`, `GET /api/events`, `GET /miniapp`.

## Cheklovlar

- Yahoo Finance rasmiy API emas; ishlamasa Binance zaxira, DXY/yields bo'lmasa kontekst "neytral".
- PAXG spot oltinni kuzatadi, lekin brokeringiz narxidan bir necha dollar farq qilishi mumkin —
  xabarlarda har bir order uchun narxdan masofa ham ko'rsatiladi.
- Bepul FMP tarifida fakt kechikishi mumkin; eng ishonchli yo'l — admin `/actual`.
- Bu moliyaviy maslahat emas.
