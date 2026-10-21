# MacroSniper v2 — XAUUSD makro yangilik rejalari

AQSH Tier-1 yangiliklari (CPI, NFP, FOMC, Claims, PCE, PPI, Retail Sales, GDP, ISM) uchun
XAUUSD bo'yicha **haqiqiy bozor ma'lumotiga asoslangan** savdo rejasini Telegram bot va Mini App
orqali VIP obunachilarga beradi. To'lov — Telegram Stars. Batafsil dizayn: [docs/SPEC.md](docs/SPEC.md).

## Qanday ishlaydi

```
ForexFactory (har 30 daq) ─► Event SCHEDULED
   T-3h  ─► Kontekst: DXY, US10Y (Yahoo) + prognoz/avvalgi  ─► VIP'larga "3 soat qoldi"
   T-2m  ─► Reja: 15m ATR(14) + 4 soatlik diapazon (Binance PAXG / COMEX) ─► BUY STOP + SELL STOP
   T+20s ─► Fakt: FMP (kalit bo'lsa) yoki admin /actual ─► qaysi order qoladi ─► VIP + kanal
```

- Har bosqich DB'da bir marta belgilanadi (`event_stages`) — restartdan keyin ham xabar takrorlanmaydi.
- Narx ma'lumoti olinmasa reja **yuborilmaydi**, adminga ogohlantirish ketadi (soxta raqam yo'q).
- Yo'nalish faqat kontekst balli |50| dan yuqori bo'lsa aytiladi, aks holda "faqat breakout".
- Barcha USD "High" va rejalashtiriladigan "Medium" relizlar (Claims, PMI…) olinadi.
- Nutqlar (Powell Speaks va h.k.) kalendarda ko'rinadi, lekin reja tuzilmaydi.

## Bot buyruqlari

| Hamma | Admin (`TELEGRAM_ADMIN_IDS`) |
|---|---|
| `/start` `/events` `/plan` `/status` `/vip` `/paysupport` | `/stats` · `/grant ID KUN` · `/revoke ID` · `/actual EVENT_ID QIYMAT` (ID'lar `/events` da) |

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
