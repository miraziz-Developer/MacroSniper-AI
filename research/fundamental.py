"""Fundamental model: predict each release's surprise from indicators published before it, then gold's direction.

P(gold up) = P(inline)·½ + P(above)·P(up | above) + P(below)·P(up | below)       (law of total probability)

Everything is walk-forward: each release is predicted from a model fit only on earlier releases.
Run:  PYTHONPATH=. python research/fundamental.py DATA_DIR   (same DATA_DIR as research/analyze.py)
Writes research/FUNDAMENTAL.md.
"""

import math
import sys
from datetime import date, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

from research.analyze import binom_p, gold_features, load_nowcasts, logistic_fit, nowcast_before
from research.events import SERIES, parse_value, release_time_utc

# Leading indicators (FF names) that come out before each target in the same cycle
LEADS: Dict[str, List[str]] = {
    "ISM Manufacturing PMI": ["Empire State Manufacturing Index", "Philly Fed Manufacturing Index", "Chicago PMI",
                              "Flash Manufacturing PMI"],
    "ISM Services PMI": ["Flash Services PMI", "CB Consumer Confidence", "Prelim UoM Consumer Sentiment"],
    "Non-Farm Employment Change": ["ADP Non-Farm Employment Change", "ISM Manufacturing PMI", "ISM Services PMI",
                                   "CB Consumer Confidence"],
    "Unemployment Rate": ["ADP Non-Farm Employment Change", "CB Consumer Confidence"],
    "CPI m/m": ["PPI m/m", "Import Prices m/m"],
    "Core CPI m/m": ["Core PPI m/m", "Import Prices m/m"],
    "Core PCE Price Index m/m": ["Core CPI m/m", "Core PPI m/m"],
    "Retail Sales m/m": ["CB Consumer Confidence", "Prelim UoM Consumer Sentiment"],
    "PPI m/m": ["Import Prices m/m"],
}
USD_DOWN_WHEN_HIGHER = {"Unemployment Rate", "Unemployment Claims"}
LOOKBACK = timedelta(days=40)


def load_all(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, usecols=["DateTime", "Currency", "Event", "Actual", "Forecast"])
    df = df[df.Currency == "USD"].copy()
    df["day"] = df.DateTime.str.slice(0, 10).map(date.fromisoformat)
    df["actual"], df["forecast"] = df.Actual.map(parse_value), df.Forecast.map(parse_value)
    df = df.dropna(subset=["actual", "forecast"]).drop_duplicates(["Event", "day"]).sort_values("day")
    df["surprise"] = df.actual - df.forecast
    # z-score with an expanding scale (only past surprises), so no look-ahead in normalisation
    scale = df.groupby("Event").surprise.transform(lambda s: s.abs().expanding().mean().shift(1))
    df["z"] = (df.surprise / scale.replace(0, np.nan)).clip(-3, 3)
    return df.reset_index(drop=True)


def features_for(target: str, all_rel: pd.DataFrame, nowcasts) -> pd.DataFrame:
    rows = all_rel[all_rel.Event == target].copy()
    by_event = {e: g for e, g in all_rel.groupby("Event")}
    feats = {}
    for lead in LEADS.get(target, []):
        g = by_event.get(lead)
        vals = []
        for d in rows.day:
            prior = g[(g.day < d) & (g.day >= d - LOOKBACK)] if g is not None else []
            vals.append(prior.z.iloc[-1] if len(prior) and pd.notna(prior.z.iloc[-1]) else 0.0)
        feats[f"lead:{lead}"] = vals
    claims = by_event.get("Unemployment Claims")
    if target in ("Non-Farm Employment Change", "Unemployment Rate") and claims is not None:
        # labour-market trend: last 4 weeks of claims vs the 4 before (rising claims = weaker jobs)
        trend = []
        for d in rows.day:
            c = claims[claims.day < d].actual.tail(8)
            trend.append((c.tail(4).mean() / c.head(4).mean() - 1) * 100 if len(c) == 8 else 0.0)
        feats["claims_trend_pct"] = trend
    if target in ("CPI m/m", "Core CPI m/m"):
        core = target == "Core CPI m/m"
        feats["nowcast_gap"] = [
            (nc - f) if (nc := nowcast_before(nowcasts, d, core)) is not None else 0.0
            for d, f in zip(rows.day, rows.forecast)
        ]
    feats["prev_z"] = rows.z.shift(1).fillna(0).values
    feats["fcst_vs_prev_sign"] = np.sign(rows.forecast.values - rows.actual.shift(1).fillna(rows.forecast).values)
    out = rows[["day", "Event", "actual", "forecast", "surprise"]].copy()
    for k, v in feats.items():
        out[k] = v
    out["above"] = (out.surprise > 0).astype(float)
    out["inline"] = (out.surprise.abs() < 1e-9).astype(float)
    return out.reset_index(drop=True)


def walk_forward_probs(df: pd.DataFrame, feats: List[str], warmup: int = 36) -> pd.DataFrame:
    """P(above | not inline) and P(inline), each from data strictly before the release."""
    p_above, p_inline = [np.nan] * len(df), [np.nan] * len(df)
    for i in range(warmup, len(df)):
        past = df.iloc[:i]
        p_inline[i] = (past.inline.sum() + 1) / (len(past) + 2)
        nz = past[past.inline == 0]
        mu, sd = nz[feats].mean(), nz[feats].std().replace(0, 1).fillna(1)
        x = np.c_[np.ones(len(nz)), ((nz[feats] - mu) / sd).values]
        w = logistic_fit(x, nz.above.values, l2=3.0)
        xi = np.r_[1, ((df.loc[i, feats] - mu) / sd).values]
        p_above[i] = 1 / (1 + math.exp(-float(xi @ w)))
    df = df.copy()
    df["p_above"], df["p_inline"] = p_above, p_inline
    return df.dropna(subset=["p_above"])


def calibration(probs: np.ndarray, outcomes: np.ndarray) -> List[str]:
    lines = []
    for lo, hi in ((0.0, 0.4), (0.4, 0.45), (0.45, 0.55), (0.55, 0.6), (0.6, 1.01)):
        m = (probs >= lo) & (probs < hi)
        if m.sum():
            lines.append(f"{lo:.2f}–{min(hi, 1):.2f}: predicted {probs[m].mean():.0%}, happened {outcomes[m].mean():.0%} (n={m.sum()})")
    return lines


def main(data_dir: str) -> None:
    rel = load_all(f"{data_dir}/data_ff/forex_factory_cache.csv")
    nowcasts = load_nowcasts(f"{data_dir}/research/nowcast_month.json")
    lines = ["# Fundamental model report", "",
             "Walk-forward: every number below is an out-of-sample prediction made only with earlier data.", "",
             "## 1. Surprise direction (actual vs forecast) from leading indicators", "",
             "| Release | N | Accuracy (excl. inline) | Base rate | p-value | Confident ≥60% N | Confident acc | Brier |",
             "|---|---|---|---|---|---|---|---|"]
    preds = {}
    for target in LEADS:
        df = features_for(target, rel, nowcasts)
        df = df[df.day >= date(2010, 1, 1)].reset_index(drop=True)
        feats = [c for c in df.columns if c.startswith(("lead:", "claims_", "nowcast", "prev_z", "fcst_"))]
        pred = walk_forward_probs(df, feats)
        preds[target] = pred
        nz = pred[pred.inline == 0]
        hit = (nz.p_above >= 0.5) == (nz.above == 1)
        conf = nz[(nz.p_above >= 0.6) | (nz.p_above <= 0.4)]
        conf_hit = (conf.p_above >= 0.5) == (conf.above == 1)
        base = max(nz.above.mean(), 1 - nz.above.mean())
        brier = float(((nz.p_above - nz.above) ** 2).mean())
        lines.append(f"| {target} | {len(nz)} | {hit.mean():.1%} | {base:.1%} | {binom_p(int(hit.sum()), len(nz)):.3f} | "
                     f"{len(conf)} | {conf_hit.mean() if len(conf) else float('nan'):.1%} | {brier:.3f} |")

    # --- 2) gold direction via total probability
    lines += ["", "## 2. Gold 15-minute direction before the release (total-probability model)", "",
              "P(up | USD-positive surprise) learnt walk-forward from earlier releases of the same series.", ""]
    lines += ["| Release | N | Accuracy | p-value | Strong calls (|P−50%| ≥ 10%) N | Strong acc |", "|---|---|---|---|---|---|"]
    all_p, all_y = [], []
    for target, pred in preds.items():
        rows = []
        for _, r in pred.iterrows():
            g = gold_features(f"{data_dir}/duka", release_time_utc(r.day, SERIES[target][1]))
            if g is None:
                continue
            usd_dir = -1 if target in USD_DOWN_WHEN_HIGHER else 1
            usd_pos = (1 if r.surprise > 0 else -1 if r.surprise < 0 else 0) * usd_dir
            rows.append({"p_above": r.p_above, "p_inline": r.p_inline, "usd_dir": usd_dir, "usd_pos": usd_pos,
                         "gold_up": float(g["ret15"] > 0)})
        gdf = pd.DataFrame(rows)
        if len(gdf) < 40:
            continue
        probs = []
        for i in range(len(gdf)):
            past = gdf.iloc[:i]
            up_if_usd_pos = (past[past.usd_pos == 1].gold_up.sum() + 1) / ((past.usd_pos == 1).sum() + 2)
            up_if_usd_neg = (past[past.usd_pos == -1].gold_up.sum() + 1) / ((past.usd_pos == -1).sum() + 2)
            r = gdf.iloc[i]
            p_usd_pos = r.p_above if r.usd_dir == 1 else 1 - r.p_above
            p = r.p_inline * 0.5 + (1 - r.p_inline) * (p_usd_pos * up_if_usd_pos + (1 - p_usd_pos) * up_if_usd_neg)
            probs.append(p)
        gdf["p_up"] = probs
        gdf = gdf.iloc[24:]
        hit = (gdf.p_up >= 0.5) == (gdf.gold_up == 1)
        strong = gdf[(gdf.p_up - 0.5).abs() >= 0.10]
        s_hit = (strong.p_up >= 0.5) == (strong.gold_up == 1)
        all_p += list(gdf.p_up)
        all_y += list(gdf.gold_up)
        lines.append(f"| {target} | {len(gdf)} | {hit.mean():.1%} | {binom_p(int(hit.sum()), len(gdf)):.3f} | "
                     f"{len(strong)} | {s_hit.mean() if len(strong) else float('nan'):.1%} |")
    lines += ["", "Calibration of the gold probability (all releases pooled):", ""]
    lines += [f"- {c}" for c in calibration(np.array(all_p), np.array(all_y))]

    with open("research/FUNDAMENTAL.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


SIZE_EDGES = (0.5, 1.5)  # |surprise| / usual size: small < 0.5 <= medium < 1.5 <= large
LIVE_MINUTES = (1, 2, 3, 5, 10)
MOVE_EDGES = (-0.5, 0.0, 0.5, 1.0)  # signed move toward the expected side, in 15m ATRs


def _bucket(value: float, edges) -> int:
    return sum(value >= e for e in edges)


def export_live_tables(data_dir: str) -> List[str]:
    """Tables the bot quotes live: odds by surprise size at release, then odds given how price has moved."""
    import json

    from app.calendar.forexfactory import parse_number  # same units as the live calendar (225K -> 225)

    raw = pd.read_csv(f"{data_dir}/data_ff/forex_factory_cache.csv", usecols=["DateTime", "Currency", "Event", "Actual", "Forecast"])
    raw = raw[(raw.Currency == "USD") & raw.Event.isin(SERIES)].copy()
    raw["day"] = raw.DateTime.str.slice(0, 10).map(date.fromisoformat)
    raw["surprise"] = raw.Actual.map(parse_number) - raw.Forecast.map(parse_number)
    raw = raw.dropna(subset=["surprise"]).drop_duplicates(["Event", "day"])
    raw = raw[raw.day >= date(2012, 1, 1)]

    scale, by_size, live = {}, {}, {}
    for title, g in raw.groupby("Event"):
        scale[title] = float(g[g.surprise != 0].surprise.abs().median())  # median: COVID-era outliers distort a mean
        counts = {b: [0, 0, 0] for b in range(3)}  # n, against_1m, against_15m
        for _, r in g[g.surprise != 0].iterrows():
            f = gold_features(f"{data_dir}/duka", release_time_utc(r.day, SERIES[title][1]))
            if not f or not f["atr"]:
                continue
            expected = -np.sign(r.surprise) * (-1 if title in USD_DOWN_WHEN_HIGHER else 1)  # gold side
            size = _bucket(abs(r.surprise) / scale[title], SIZE_EDGES)
            c = counts[size]
            c[0] += 1
            c[1] += np.sign(f["ret1"]) == expected
            c[2] += np.sign(f["ret15"]) == expected
            closes = [x[3] for x in f["post"]]
            for k in LIVE_MINUTES:
                move = (closes[k - 1] - f["p0"]) * expected / f["atr"]
                cell = live.setdefault(f"{k}:{_bucket(move, MOVE_EDGES)}", [0, 0])
                cell[0] += 1
                cell[1] += np.sign(f["ret15"]) == expected
        by_size[title] = {str(b): {"n": n, "p1": round((a1 + 1) / (n + 2), 3), "p15": round((a15 + 1) / (n + 2), 3)}
                          for b, (n, a1, a15) in counts.items() if n >= 8}

    stats_path = "app/signals/stats.json"
    stats = json.load(open(stats_path))
    stats["surprise_scale"] = {k: round(v, 6) for k, v in scale.items()}
    stats["odds_by_size"] = by_size
    stats["live_odds"] = {k: {"n": n, "p15": round((h + 1) / (n + 2), 3)} for k, (n, h) in sorted(live.items())}
    stats["live_grid"] = {"minutes": list(LIVE_MINUTES), "move_edges_atr": list(MOVE_EDGES), "size_edges": list(SIZE_EDGES)}
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    lines = ["", "## 3. Live odds the bot quotes", "",
             "P(gold is on the expected side 15 min after release | minutes elapsed, move so far in 15m ATRs):", "",
             "| minute | < −0.5 ATR | −0.5…0 | 0…0.5 | 0.5…1 | > 1 ATR |", "|---|---|---|---|---|---|"]
    for k in LIVE_MINUTES:
        cells = [stats["live_odds"].get(f"{k}:{b}") for b in range(5)]
        lines.append(f"| {k} | " + " | ".join(f"{c['p15']:.0%} (n={c['n']})" if c else "—" for c in cells) + " |")
    return lines


if __name__ == "__main__":
    main(sys.argv[1])
    extra = export_live_tables(sys.argv[1])
    with open("research/FUNDAMENTAL.md", "a") as f:
        f.write("\n".join(extra) + "\n")
    print("\n".join(extra))
