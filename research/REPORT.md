# MacroSniper research report

Data: ForexFactory history 2012-01-03 → 2025-04-04, Dukascopy XAUUSD 1-minute candles, Cleveland Fed CPI nowcasts. All models walk-forward.

## 1. Can the surprise sign (actual > forecast) be predicted before release?

| Series | Features | N | Accuracy | Base rate | p-value | Confident (≥60%) N | Confident acc |
|---|---|---|---|---|---|---|---|
| cpi | fp, prev_surprise, nowcast_gap | 61 | 50.8% | 52.5% | 0.500 | 36 | 52.8% |
| core_cpi | fp, prev_surprise, nowcast_gap | 66 | 59.1% | 51.5% | 0.088 | 36 | 61.1% |
| nfp | fp, prev_surprise, adp_sign, claims4 | 129 | 53.5% | 58.1% | 0.241 | 41 | 48.8% |
| unemployment | fp, prev_surprise, claims4 | 98 | 58.2% | 58.2% | 0.065 | 62 | 61.3% |
| claims | fp, prev_surprise | 648 | 54.8% | 56.9% | 0.008 | 278 | 59.7% |
| retail | fp, prev_surprise | 122 | 58.2% | 55.7% | 0.043 | 53 | 54.7% |
| core_pce | fp, prev_surprise | 41 | 61.0% | 61.0% | 0.106 | 41 | 61.0% |
| ppi | fp, prev_surprise | 110 | 41.8% | 53.6% | 0.965 | 28 | 35.7% |
| ism_mfg | fp, prev_surprise | 134 | 44.8% | 53.7% | 0.902 | 32 | 40.6% |
| ism_svc | fp, prev_surprise | 133 | 63.9% | 55.6% | 0.001 | 73 | 67.1% |

## 2. Does gold follow the surprise? (after the number is out)

| Primary release | Slots | Gold moved against the USD surprise at +1m | at +15m | at +60m | Median |move| 15m ($) | Median 15m move / ATR |
|---|---|---|---|---|---|---|
| claims | 512 | 76% | 62% | 58% | 1.61 | 0.91 |
| ism_svc | 157 | 76% | 71% | 67% | 2.17 | 0.79 |
| ism_mfg | 156 | 81% | 68% | 62% | 2.25 | 0.87 |
| adp | 155 | 88% | 72% | 68% | 1.99 | 1.42 |
| retail | 139 | 78% | 63% | 65% | 2.30 | 1.23 |
| cpi | 133 | 80% | 65% | 64% | 3.31 | 2.05 |
| nfp | 123 | 84% | 80% | 71% | 6.06 | 3.67 |
| ppi | 104 | 82% | 65% | 63% | 1.58 | 0.85 |
| core_pce | 70 | 73% | 49% | 59% | 2.23 | 1.21 |
| fed_rate | 2 | 50% | 100% | 50% | 10.95 | 3.67 |

## 3. Predicting gold's 15-minute direction before the release (all slots)

N=1723, accuracy 52.5% vs base rate 50.9% (p=0.022); confident (≥60%) predictions: 67 at 40.3% (p=0.956); Brier 0.251 (0.250 = coin).

- adp: N=146, acc 54.8% (p=0.141), confident 1 at 0.0%
- claims: N=498, acc 50.6% (p=0.411), confident 5 at 40.0%
- core_pce: N=141, acc 52.5% (p=0.307), confident 0 at nan%
- cpi: N=147, acc 49.0% (p=0.629), confident 42 at 42.9%
- fed_rate: N=97, acc 52.6% (p=0.342), confident 0 at nan%
- ism_mfg: N=148, acc 49.3% (p=0.597), confident 7 at 14.3%
- ism_svc: N=148, acc 50.0% (p=0.533), confident 1 at 0.0%
- nfp: N=145, acc 55.2% (p=0.122), confident 5 at 40.0%
- ppi: N=118, acc 59.3% (p=0.027), confident 4 at 50.0%
- retail: N=135, acc 57.8% (p=0.043), confident 2 at 100.0%

## 4. Straddle backtest (OCO BUY STOP / SELL STOP, conservative fills)

Results in R (1R = stop-loss distance). $0.50 spread buffer in the levels plus slippage per fill. Half closed at TP1 with stop to break-even, rest at TP2, time stop after 120 minutes.

| Primary release | 2012–2020 trades | win | R/trade | 2021–2025 trades | win | R/trade |
|---|---|---|---|---|---|---|
| claims | 333 | 34% | -0.337 | 161 | 50% | +0.083 |
| ism_svc | 96 | 51% | +0.048 | 47 | 47% | +0.120 |
| adp | 105 | 46% | -0.013 | 49 | 45% | -0.066 |
| ism_mfg | 95 | 47% | -0.010 | 51 | 43% | -0.124 |
| nfp | 105 | 70% | +0.679 | 50 | 66% | +0.636 |
| cpi | 96 | 46% | -0.030 | 51 | 57% | +0.352 |
| core_pce | 90 | 38% | -0.252 | 50 | 40% | -0.222 |
| retail | 85 | 53% | +0.112 | 50 | 26% | -0.522 |
| ppi | 74 | 45% | -0.005 | 42 | 36% | -0.315 |
| fed_rate | 65 | 46% | -0.051 | 34 | 47% | +0.195 |

Parameter search on nfp/cpi only, tuned on 2012–2020 at $0.75 slippage:

| Params | 2012–2020 R/trade | 2021–2025 R/trade | 2021–2025 trades | win |
|---|---|---|---|---|
| {'entry_min': 0.2, 'entry_max': 0.8, 'sl_atr': 2.0, 'tp1_r': 1.5, 'tp2_r': 3.0} | +0.253 | +0.418 | 101 | 61% |
| {'entry_min': 0.3, 'entry_max': 0.8, 'sl_atr': 2.0, 'tp1_r': 1.5, 'tp2_r': 3.0} | +0.248 | +0.418 | 101 | 61% |
| {'entry_min': 0.5, 'entry_max': 0.8, 'sl_atr': 2.0, 'tp1_r': 1.5, 'tp2_r': 3.0} | +0.246 | +0.418 | 101 | 61% |
| {'entry_min': 0.2, 'entry_max': 0.8, 'sl_atr': 2.0, 'tp1_r': 1.5, 'tp2_r': 2.0} | +0.218 | +0.330 | 101 | 61% |
| {'entry_min': 0.3, 'entry_max': 0.8, 'sl_atr': 2.0, 'tp1_r': 1.5, 'tp2_r': 2.0} | +0.218 | +0.330 | 101 | 61% |

Production params {'entry_min': 0.3, 'entry_max': 0.8, 'sl_atr': 2.0, 'tp1_r': 1.5, 'tp2_r': 3.0} on nfp/cpi, slippage sensitivity:

- $0.00: 2012–2020 +0.528R (201), 2021–2025 +0.662R (101)
- $0.50: 2012–2020 +0.341R (201), 2021–2025 +0.493R (101)
- $0.75: 2012–2020 +0.248R (201), 2021–2025 +0.418R (101)
- $1.00: 2012–2020 +0.156R (201), 2021–2025 +0.349R (101)
- $1.50: 2012–2020 -0.020R (201), 2021–2025 +0.210R (101)
