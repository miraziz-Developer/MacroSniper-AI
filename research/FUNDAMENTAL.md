# Fundamental model report

Walk-forward: every number below is an out-of-sample prediction made only with earlier data.

## 1. Surprise direction (actual vs forecast) from leading indicators

| Release | N | Accuracy (excl. inline) | Base rate | p-value | Confident ≥60% N | Confident acc | Brier |
|---|---|---|---|---|---|---|---|
| ISM Manufacturing PMI | 147 | 55.1% | 51.0% | 0.124 | 90 | 56.7% | 0.264 |
| ISM Services PMI | 146 | 48.6% | 55.5% | 0.660 | 57 | 59.6% | 0.256 |
| Non-Farm Employment Change | 147 | 44.2% | 57.8% | 0.931 | 48 | 45.8% | 0.278 |
| Unemployment Rate | 114 | 53.5% | 58.8% | 0.256 | 79 | 57.0% | 0.259 |
| CPI m/m | 90 | 58.9% | 52.2% | 0.057 | 67 | 61.2% | 0.258 |
| Core CPI m/m | 94 | 56.4% | 53.2% | 0.128 | 68 | 58.8% | 0.270 |
| Core PCE Price Index m/m | 60 | 60.0% | 63.3% | 0.078 | 46 | 65.2% | 0.237 |
| Retail Sales m/m | 136 | 57.4% | 55.1% | 0.052 | 65 | 56.9% | 0.248 |
| PPI m/m | 124 | 56.5% | 51.6% | 0.089 | 46 | 56.5% | 0.251 |

## 2. Gold 15-minute direction before the release (total-probability model)

P(up | USD-positive surprise) learnt walk-forward from earlier releases of the same series.

| Release | N | Accuracy | p-value | Strong calls (|P−50%| ≥ 10%) N | Strong acc |
|---|---|---|---|---|---|
| ISM Manufacturing PMI | 123 | 48.0% | 0.706 | 29 | 55.2% |
| ISM Services PMI | 123 | 48.0% | 0.706 | 9 | 44.4% |
| Non-Farm Employment Change | 123 | 44.7% | 0.897 | 12 | 33.3% |
| Unemployment Rate | 123 | 43.9% | 0.925 | 0 | nan% |
| CPI m/m | 123 | 62.6% | 0.003 | 6 | 33.3% |
| Core CPI m/m | 123 | 61.0% | 0.010 | 2 | 50.0% |
| Core PCE Price Index m/m | 121 | 51.2% | 0.428 | 0 | nan% |
| Retail Sales m/m | 122 | 52.5% | 0.325 | 8 | 50.0% |
| PPI m/m | 122 | 59.8% | 0.019 | 13 | 38.5% |

Calibration of the gold probability (all releases pooled):

- 0.00–0.40: predicted 37%, happened 54% (n=46)
- 0.40–0.45: predicted 43%, happened 51% (n=115)
- 0.45–0.55: predicted 50%, happened 52% (n=682)
- 0.55–0.60: predicted 57%, happened 58% (n=227)
- 0.60–1.00: predicted 61%, happened 45% (n=33)

## 3. Live odds the bot quotes

P(gold is on the expected side 15 min after release | minutes elapsed, move so far in 15m ATRs):

| minute | < −0.5 ATR | −0.5…0 | 0…0.5 | 0.5…1 | > 1 ATR |
|---|---|---|---|---|---|
| 1 | 29% (n=287) | 40% (n=289) | 57% (n=513) | 72% (n=397) | 86% (n=822) |
| 2 | 19% (n=350) | 45% (n=271) | 56% (n=409) | 70% (n=398) | 90% (n=880) |
| 3 | 17% (n=355) | 40% (n=287) | 57% (n=401) | 74% (n=350) | 90% (n=915) |
| 5 | 15% (n=421) | 36% (n=266) | 59% (n=352) | 78% (n=318) | 92% (n=951) |
| 10 | 7% (n=498) | 30% (n=253) | 66% (n=298) | 88% (n=308) | 96% (n=951) |
