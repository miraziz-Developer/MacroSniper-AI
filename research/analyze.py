"""Can anything known *before* a US release predict its surprise and gold's direction? And does the straddle pay?

Every model is evaluated walk-forward (fit only on releases before the one being predicted).

Run:  PYTHONPATH=. python research/analyze.py DATA_DIR
DATA_DIR holds data_ff/forex_factory_cache.csv, duka/*.bi5 (research/gold.py), research/nowcast_month.json.
Writes research/REPORT.md.
"""

import json
import math
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.signals.plan import (
    ENTRY_MAX_ATR, ENTRY_MIN_ATR, SL_ATR, TP1_R, TP2_R, build_plan, simulate,
)
from research.events import SERIES, load_releases
from research.gold import load_day, window

# Which series drives a shared release slot (first match wins) and how much each series counts in it
PRIORITY = ["fed_rate", "nfp", "cpi", "core_cpi", "core_pce", "retail", "ppi", "ism_mfg", "ism_svc", "adp", "claims"]
WEIGHT = {"nfp": 1.0, "unemployment": 0.5, "ahe": 0.5, "cpi": 0.7, "core_cpi": 1.0, "core_pce": 1.0, "retail": 0.7,
          "core_retail": 0.5, "ppi": 0.5, "core_ppi": 0.5, "ism_mfg": 1.0, "ism_svc": 1.0, "adp": 1.0, "claims": 1.0,
          "fed_rate": 1.0}
SPLIT = pd.Timestamp("2021-01-01", tz="UTC")  # tune <= 2020, validate 2021+
PLAN_SERIES = ["nfp", "cpi"]  # the only releases where the straddle held up out of sample


# ---------------------------------------------------------------- data


def load_nowcasts(path: str) -> Dict[tuple, List[tuple]]:
    """{(year, month) target: [(date, cpi_nowcast, core_cpi_nowcast), ...]} as published day by day."""
    out: Dict[tuple, List[tuple]] = {}
    for entry in json.load(open(path)):
        year, month = map(int, entry["chart"]["subcaption"].split("-"))
        labels = [c.get("label", "") for c in entry["categories"][0]["category"]]
        series = {s["seriesname"]: [x.get("value", "") for x in s["data"]] for s in entry["dataset"]}
        rows = []
        for i, label in enumerate(labels):
            if "/" not in label or i >= len(series["CPI Inflation"]):
                continue
            m, d = map(int, label.split("/"))
            y = year + (1 if m < month else 0)
            cpi, core = series["CPI Inflation"][i], series["Core CPI Inflation"][i]
            if cpi and core:
                rows.append((date(y, m, d), float(cpi), float(core)))
        out[(year, month)] = rows
    return out


def nowcast_before(nowcasts, release_day: date, core: bool) -> Optional[float]:
    target = (release_day.year - 1, 12) if release_day.month == 1 else (release_day.year, release_day.month - 1)
    rows = [r for r in nowcasts.get(target, []) if r[0] < release_day]
    return (rows[-1][2] if core else rows[-1][1]) if rows else None


def gold_features(duka_dir: str, t: datetime) -> Optional[dict]:
    t = t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
    day = load_day(duka_dir, t.date())
    if not day:
        return None
    pre = window(day, t - timedelta(minutes=240), 240)
    post = window(day, t, 121)
    if len(pre) < 200 or len(post) < 100:
        return None
    p0 = pre[-1][3]  # close of the minute before release
    bars15 = [pre[i : i + 15] for i in range(len(pre) - 225, len(pre), 15)]
    agg = [(b[0][0], max(x[1] for x in b), min(x[2] for x in b), b[-1][3]) for b in bars15 if b]
    trs = [max(h - l, abs(h - pc), abs(l - pc)) for (_, h, l, _), (_, _, _, pc) in zip(agg[1:], agg[:-1])]
    rng = pre[-16 * 15 :] if len(pre) >= 240 else pre
    return {
        "p0": p0,
        "atr": float(np.mean(trs[-14:])) if trs else None,
        "range_high": max(x[1] for x in rng),
        "range_low": min(x[2] for x in rng),
        "drift": p0 - pre[0][0],
        "ret1": post[0][3] - p0,
        "ret15": post[min(14, len(post) - 1)][3] - p0,
        "ret60": post[min(59, len(post) - 1)][3] - p0,
        "post": post,
    }


# ---------------------------------------------------------------- models


def logistic_fit(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 300) -> np.ndarray:
    """Plain L2 logistic regression via Newton steps (x already includes an intercept column)."""
    w = np.zeros(x.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-x @ w))
        grad = x.T @ (p - y) + l2 * np.r_[0, w[1:]]
        hess = x.T @ (x * (p * (1 - p))[:, None]) + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def walk_forward(df: pd.DataFrame, features: List[str], target: str, warmup: int = 36) -> pd.DataFrame:
    """Predict each row from a model fit on all earlier rows only."""
    df = df.dropna(subset=features + [target]).reset_index(drop=True)
    probs = [np.nan] * len(df)
    for i in range(warmup, len(df)):
        train = df.iloc[:i]
        mu, sd = train[features].mean(), train[features].std().replace(0, 1)
        xt = np.c_[np.ones(i), ((train[features] - mu) / sd).values]
        w = logistic_fit(xt, train[target].values)
        xi = np.r_[1, ((df.loc[i, features] - mu) / sd).values]
        probs[i] = 1 / (1 + math.exp(-float(xi @ w)))
    df["prob"] = probs
    return df.dropna(subset=["prob"])


def binom_p(k: int, n: int) -> float:
    """One-sided P(X >= k) for a fair coin (normal approximation)."""
    if n == 0:
        return 1.0
    z = (k - 0.5 * n - 0.5) / math.sqrt(0.25 * n)
    return 0.5 * math.erfc(z / math.sqrt(2))


def score(pred: pd.DataFrame, target: str, confident: float = 0.60) -> dict:
    hit = (pred.prob >= 0.5) == (pred[target] == 1)
    conf = pred[(pred.prob >= confident) | (pred.prob <= 1 - confident)]
    conf_hit = (conf.prob >= 0.5) == (conf[target] == 1)
    base = max(pred[target].mean(), 1 - pred[target].mean())
    return {
        "n": len(pred),
        "acc": hit.mean(),
        "base": base,
        "p": binom_p(int(hit.sum()), len(pred)),
        "conf_n": len(conf),
        "conf_acc": conf_hit.mean() if len(conf) else float("nan"),
        "conf_p": binom_p(int(conf_hit.sum()), len(conf)),
        "brier": float(((pred.prob - pred[target]) ** 2).mean()),
    }


# ---------------------------------------------------------------- straddle backtest


def backtest(slots: pd.DataFrame, params: dict, slippage: float) -> dict:
    """Same build_plan/simulate code the live bot uses for its track record."""
    rs = []
    for g in slots.gold:
        plan = build_plan(g["p0"], g["atr"], g["range_high"], g["range_low"], **params)
        rs.append(simulate(plan, g["post"], slippage))
    rs = np.array([r for r in rs if r is not None])
    traded = rs[rs != 0]
    return {
        "slots": len(rs),
        "trades": len(traded),
        "win": float((traded > 0).mean()) if len(traded) else float("nan"),
        "exp_r": float(traded.mean()) if len(traded) else float("nan"),
        "total_r": float(traded.sum()),
    }


# ---------------------------------------------------------------- main


def main(data_dir: str) -> None:
    rel = load_releases(f"{data_dir}/data_ff/forex_factory_cache.csv")
    nowcasts = load_nowcasts(f"{data_dir}/research/nowcast_month.json")
    rel = rel[rel.release_utc >= pd.Timestamp("2012-01-01", tz="UTC")].copy()

    # --- per-series pre-release features (only information available before the release)
    rel["raw_up"] = (rel.surprise > 0).astype(float).where(rel.surprise != 0)
    rel["fp"] = np.sign(rel.forecast - rel.previous)
    rel["prev_surprise"] = rel.groupby("series").surprise.shift(1).pipe(np.sign)
    def gap(series: str, day: date, forecast: float) -> float:
        nc = nowcast_before(nowcasts, day, core=series == "core_cpi") if series in ("cpi", "core_cpi") else None
        return nc - forecast if nc is not None else np.nan  # nowcasts start in 2013

    rel["nowcast_gap"] = [gap(s, d, f) for s, d, f in zip(rel.series, rel.local_date, rel.forecast)]
    adp = rel[rel.series == "adp"][["release_utc", "surprise"]].rename(columns={"surprise": "adp_s"})
    claims = rel[rel.series == "claims"][["release_utc", "surprise"]].copy()
    claims["claims4"] = np.sign(claims.surprise).rolling(4).sum()
    rel = pd.merge_asof(rel.sort_values("release_utc"), adp.sort_values("release_utc"), on="release_utc",
                        direction="backward", tolerance=pd.Timedelta(days=4), allow_exact_matches=False)
    rel = pd.merge_asof(rel, claims[["release_utc", "claims4"]].sort_values("release_utc"), on="release_utc",
                        direction="backward", allow_exact_matches=False)
    rel["adp_sign"] = np.sign(rel.adp_s)

    lines: List[str] = ["# MacroSniper research report", "",
                        f"Data: ForexFactory history {rel.release_utc.min():%Y-%m-%d} → {rel.release_utc.max():%Y-%m-%d}, "
                        "Dukascopy XAUUSD 1-minute candles, Cleveland Fed CPI nowcasts. All models walk-forward.", ""]

    # --- 1) surprise predictability per series
    lines += ["## 1. Can the surprise sign (actual > forecast) be predicted before release?", "",
              "| Series | Features | N | Accuracy | Base rate | p-value | Confident (≥60%) N | Confident acc |",
              "|---|---|---|---|---|---|---|---|"]
    tests = {
        "cpi": ["fp", "prev_surprise", "nowcast_gap"],
        "core_cpi": ["fp", "prev_surprise", "nowcast_gap"],
        "nfp": ["fp", "prev_surprise", "adp_sign", "claims4"],
        "unemployment": ["fp", "prev_surprise", "claims4"],
        "claims": ["fp", "prev_surprise"],
        "retail": ["fp", "prev_surprise"],
        "core_pce": ["fp", "prev_surprise"],
        "ppi": ["fp", "prev_surprise"],
        "ism_mfg": ["fp", "prev_surprise"],
        "ism_svc": ["fp", "prev_surprise"],
    }
    surprise_scores = {}
    for series, feats in tests.items():
        df = rel[rel.series == series]
        pred = walk_forward(df, feats, "raw_up", warmup=24)
        s = score(pred, "raw_up")
        surprise_scores[series] = (s, pred)
        lines.append(f"| {series} | {', '.join(feats)} | {s['n']} | {s['acc']:.1%} | {s['base']:.1%} | {s['p']:.3f} | "
                     f"{s['conf_n']} | {s['conf_acc']:.1%} |")

    # --- 2) slots + gold reaction
    rows = []
    for t, grp in rel.groupby("release_utc"):
        primary = next((s for s in PRIORITY if s in set(grp.series)), grp.series.iloc[0])
        usd = float(sum(WEIGHT.get(s, 0.5) * u for s, u in zip(grp.series, grp.usd_surprise)))
        g = gold_features(f"{data_dir}/duka", t)
        if g:
            rows.append({"release_utc": t, "primary": primary, "usd_score": usd, "gold": g, **{k: g[k] for k in
                         ("atr", "drift", "ret1", "ret15", "ret60")}})
    slots = pd.DataFrame(rows)
    slots = slots[slots.atr > 0]

    lines += ["", "## 2. Does gold follow the surprise? (after the number is out)", "",
              "| Primary release | Slots | Gold moved against the USD surprise at +1m | at +15m | at +60m | Median |move| 15m ($) | Median 15m move / ATR |",
              "|---|---|---|---|---|---|---|"]
    nz = slots[slots.usd_score != 0]
    for primary, grp in sorted(nz.groupby("primary"), key=lambda kv: -len(kv[1])):
        agree = lambda col: (np.sign(grp[col]) == -np.sign(grp.usd_score)).mean()  # noqa: E731
        lines.append(f"| {primary} | {len(grp)} | {agree('ret1'):.0%} | {agree('ret15'):.0%} | {agree('ret60'):.0%} | "
                     f"{grp.ret15.abs().median():.2f} | {(grp.ret15.abs() / grp.atr).median():.2f} |")

    # --- 3) direct pre-release gold direction model at slot level
    # Express each pre-release signal in "USD direction" (+ = USD-positive) and weight-sum it per slot
    usd_dir = np.where(rel.series.isin(["unemployment", "claims"]), -1.0, 1.0)
    w = rel.series.map(WEIGHT).fillna(0.5)
    signals = pd.DataFrame({
        "release_utc": rel.release_utc,
        "fp_usd": rel.fp.fillna(0) * usd_dir * w,
        "prev_usd": rel.prev_surprise.fillna(0) * usd_dir * w,
        "now_usd": np.sign(rel.nowcast_gap.fillna(0)) * w,
    })
    agg = signals.groupby("release_utc", as_index=False).sum()
    s3 = slots.merge(agg, on="release_utc")
    s3["drift_atr"] = s3.drift / s3.atr
    s3["gold_up"] = (s3.ret15 > 0).astype(float)
    pred3 = walk_forward(s3, ["fp_usd", "prev_usd", "now_usd", "drift_atr"], "gold_up", warmup=100)
    sc3 = score(pred3, "gold_up")
    lines += ["", "## 3. Predicting gold's 15-minute direction before the release (all slots)", "",
              f"N={sc3['n']}, accuracy {sc3['acc']:.1%} vs base rate {sc3['base']:.1%} (p={sc3['p']:.3f}); "
              f"confident (≥60%) predictions: {sc3['conf_n']} at {sc3['conf_acc']:.1%} (p={sc3['conf_p']:.3f}); "
              f"Brier {sc3['brier']:.3f} (0.250 = coin).", ""]
    for primary, grp in pred3.groupby("primary"):
        if len(grp) >= 40:
            s = score(grp, "gold_up")
            lines.append(f"- {primary}: N={s['n']}, acc {s['acc']:.1%} (p={s['p']:.3f}), confident {s['conf_n']} at {s['conf_acc']:.1%}")

    # --- 4) straddle backtest: tune on NFP/CPI 2012–2020, validate on 2021–2025
    lines += ["", "## 4. Straddle backtest (OCO BUY STOP / SELL STOP, conservative fills)", "",
              "Results in R (1R = stop-loss distance). $0.50 spread buffer in the levels plus slippage per fill. "
              "Half closed at TP1 with stop to break-even, rest at TP2, time stop after 120 minutes.", ""]
    production = dict(entry_min=ENTRY_MIN_ATR, entry_max=ENTRY_MAX_ATR, sl_atr=SL_ATR, tp1_r=TP1_R, tp2_r=TP2_R)
    lines += ["| Primary release | 2012–2020 trades | win | R/trade | 2021–2025 trades | win | R/trade |",
              "|---|---|---|---|---|---|---|"]
    for primary, grp in sorted(slots.groupby("primary"), key=lambda kv: -len(kv[1])):
        a = backtest(grp[grp.release_utc < SPLIT], production, 0.5)
        b = backtest(grp[grp.release_utc >= SPLIT], production, 0.5)
        lines.append(f"| {primary} | {a['trades']} | {a['win']:.0%} | {a['exp_r']:+.3f} | {b['trades']} | {b['win']:.0%} | {b['exp_r']:+.3f} |")

    plannable = slots[slots.primary.isin(PLAN_SERIES)]
    train, test = plannable[plannable.release_utc < SPLIT], plannable[plannable.release_utc >= SPLIT]
    grid = [dict(entry_min=a, entry_max=b, sl_atr=c, tp1_r=d, tp2_r=e)
            for a in (0.2, 0.3, 0.5) for b in (0.8, 1.0, 1.5) for c in (1.0, 1.5, 2.0, 2.5)
            for d in (1.0, 1.5) for e in (2.0, 3.0) if a < b and d < e]
    ranked = sorted(((backtest(train, g, 0.75)["exp_r"], g) for g in grid), key=lambda x: -x[0])
    lines += ["", f"Parameter search on {'/'.join(PLAN_SERIES)} only, tuned on 2012–2020 at $0.75 slippage:", "",
              "| Params | 2012–2020 R/trade | 2021–2025 R/trade | 2021–2025 trades | win |", "|---|---|---|---|---|"]
    for r, g in ranked[:5]:
        t = backtest(test, g, 0.75)
        lines.append(f"| {g} | {r:+.3f} | {t['exp_r']:+.3f} | {t['trades']} | {t['win']:.0%} |")
    lines += ["", f"Production params {production} on {'/'.join(PLAN_SERIES)}, slippage sensitivity:", ""]
    for slip in (0.0, 0.5, 0.75, 1.0, 1.5):
        a, b = backtest(train, production, slip), backtest(test, production, slip)
        lines.append(f"- ${slip:.2f}: 2012–2020 {a['exp_r']:+.3f}R ({a['trades']}), 2021–2025 {b['exp_r']:+.3f}R ({b['trades']})")

    # --- export the numbers the live bot quotes to subscribers
    title_of = {v[0]: k for k, v in SERIES.items()}
    stats = {"generated_from": f"{slots.release_utc.min():%Y-%m} – {slots.release_utc.max():%Y-%m}",
             "reaction": {}, "straddle": {}}
    for primary, grp in nz.groupby("primary"):
        if len(grp) >= 30:
            against = lambda col: float((np.sign(grp[col]) == -np.sign(grp.usd_score)).mean())  # noqa: E731
            stats["reaction"][title_of[primary]] = {
                "n": len(grp), "against_1m": round(against("ret1"), 3), "against_15m": round(against("ret15"), 3),
                "median_move_15m": round(float(grp.ret15.abs().median()), 2),
            }
    for primary in PLAN_SERIES:
        r = backtest(slots[slots.primary == primary], production, 0.5)
        stats["straddle"][title_of[primary]] = {k: round(r[k], 3) for k in ("trades", "win", "exp_r", "total_r")}
    with open("app/signals/stats.json", "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    out = "research/REPORT.md"
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
