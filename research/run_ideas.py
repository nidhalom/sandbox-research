"""Ideas 1, 3, 4, 4b, 5 (pre-registration docs/specs/2026-10-06-ideas-preregistration.md)."""
from pathlib import Path

import numpy as np
import pandas as pd

from botcore.metrics import summary
from botcore.portfolio import simulate
from research.gold import build_prices
from research.run_core import PLAN, core_verdict, describe, exit_fixed, months_later, plan_gain
from research.run_phase1 import chart, table, yearly_table
from research.sentiment import load_fear_greed

VOL_TARGET = 0.60
BASE_W = 0.5
BAND = 0.05
DYN_START, END = "2019-01-01", "2026-09-30"
I1_START, I1_END = "2017-08-17", "2020-08-31"
MIXES = (0.3, 0.4, 0.5)
FMT = {"cagr": "+.1%", "max_dd": ".1%", "sharpe": ".2f"}
FMT_ROLL = {"p10": "+.0%", "median": "+.0%", "p90": "+.0%", "worst": "+.0%", "lose": ".0%",
            "windows": "d", "independent": "d"}


def realized_vol(close: pd.Series, n: int) -> pd.Series:
    return close.pct_change().rolling(n).std() * np.sqrt(365)


def vol_weight(sigma: pd.Series) -> pd.Series:
    return BASE_W * np.minimum(1.0, VOL_TARGET / sigma)


def brake_weight(close: pd.Series) -> pd.Series:
    return pd.Series(np.where(close >= close.rolling(200).mean(), BASE_W, 0.0), index=close.index)


def future_vol(close: pd.Series) -> pd.Series:
    """Realized volatility over the next 30 days (known 30 days later)."""
    return realized_vol(close, 30).shift(-30)


def vol_features(close: pd.Series, fng: pd.Series) -> pd.DataFrame:
    f = pd.DataFrame({f"vol_{n}": realized_vol(close, n) for n in (7, 30, 90)})
    f["abs_r1"] = close.pct_change().abs()
    f["abs_r7"] = close.pct_change(7).abs()
    f["fng"] = fng.reindex(close.index).ffill()
    return f


def vol_train_end(cut: pd.Timestamp) -> pd.Timestamp:
    """Last row whose 30-day-ahead volatility is known at the close before `cut`."""
    return cut - pd.Timedelta(days=31)


def ai_vol_forecast(feats: pd.DataFrame, target: pd.Series, start=DYN_START, train_start="2018-02-01") -> pd.Series:
    from sklearn.ensemble import HistGradientBoostingRegressor

    out = []
    for year in range(pd.Timestamp(start).year, feats.index[-1].year + 1):
        cut = pd.Timestamp(f"{year}-01-01")
        train = feats.loc[train_start:vol_train_end(cut)]
        y = target.loc[train.index]
        ok = y.notna()
        model = HistGradientBoostingRegressor(random_state=0).fit(train[ok], y[ok])
        test = feats.loc[cut:f"{year}-12-31"]
        if len(test):
            out.append(pd.Series(model.predict(test), index=test.index))
    return pd.concat(out)


def targets_from(btc_w: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"BTC": btc_w, "GOLD": 1 - btc_w})


def returns(prices, weights=None, rule="none", targets=None) -> pd.Series:
    w = weights or {"BTC": BASE_W, "GOLD": 1 - BASE_W}
    v = simulate(prices[list(w)], {prices.index[0]: 1.0}, w, rule, band=BAND, targets=targets)["value"]
    return v.pct_change().dropna()


def dyn_verdict(s, btc, a1) -> list[str]:
    fails = []
    if s["max_dd"] < -0.40:
        fails.append("max drawdown worse than -40%")
    if s["cagr"] < 2 / 3 * btc["cagr"]:
        fails.append("CAGR below 2/3 of hold BTC")
    if s["sharpe"] <= btc["sharpe"]:
        fails.append("Sharpe not above hold BTC")
    if s["sharpe"] <= a1["sharpe"]:
        fails.append("Sharpe not above A1 (50/50 quarterly)")
    return fails


def verdict_text(fails):
    return "**GO** (Testnet paper trading only)" if not fails else "**NO-GO**: " + "; ".join(fails)


def idea1(px) -> list[str]:
    p1 = px.loc[I1_START:I1_END]
    btc = summary(returns(p1, {"BTC": 1.0}))
    rows, verdicts = {"Hold BTC": btc}, []
    for b in MIXES:
        w = {"BTC": b, "GOLD": 1 - b}
        s, never = summary(returns(p1, w, "quarterly")), summary(returns(p1, w))
        name = f"{b:.0%}/{1 - b:.0%} quarterly"
        rows[name], rows[f"{b:.0%}/{1 - b:.0%} never rebalanced"] = s, never
        verdicts.append(f"- {name}: {verdict_text(core_verdict(s, btc, never))}")
    full = {"Hold BTC": summary(returns(px, {"BTC": 1.0}))}
    for b in MIXES:
        full[f"{b:.0%}/{1 - b:.0%} quarterly"] = summary(returns(px, {"BTC": b, "GOLD": 1 - b}, "quarterly"))
    return ["## Idea 1 — BTC + gold on unseen gold history (2017-08-17 → 2020-08-31)", "", *verdicts, "",
            table(rows, FMT), "", "Full period 2017-08-17 → 2026-09-30 (informational):", "", table(full, FMT), ""]


def idea3(px) -> list[str]:
    extra = PLAN + [(m, 100.0) for m in range(7, 30)]
    starts = [s for s in pd.date_range("2017-09-01", px.index[-1], freq="W-MON")
              if months_later(px.index, s, 30) is not None]
    roll = {}
    for name, w, rule in [("Hold BTC", {"BTC": 1.0}, "none"),
                          ("50/50 quarterly", {"BTC": 0.5, "GOLD": 0.5}, "quarterly")]:
        for label, sched in [("plan only ($3,000)", PLAN), ("plan + $100/month ($5,300)", extra)]:
            g = [plan_gain(px[list(w)], w, rule, s, sched, exit_fixed(30), 30) for s in starts]
            roll[f"{name}, {label}"] = describe(g, starts, 30)
    return ["## Idea 3 — Monthly contributions, sold at month 30 (informational)", "",
            "Gain is on total money deposited. Weekly starts from 2017-09, heavily overlapping.", "",
            table(roll, FMT_ROLL), ""]


def ideas_dynamic(px) -> list[str]:
    close = px["BTC"]
    feats, target = vol_features(close, load_fear_greed("data/fear_greed.csv")), future_vol(close)
    ai, naive = ai_vol_forecast(feats, target), realized_vol(close, 30)
    p = px.loc[DYN_START:END]
    w4 = vol_weight(naive).loc[p.index]
    w4b = vol_weight(ai.clip(lower=0.05)).loc[p.index]
    w5 = brake_weight(close).loc[p.index]
    rets = {"Hold BTC": returns(p, {"BTC": 1.0}), "A1 50/50 quarterly": returns(p, rule="quarterly"),
            "4 volatility-scaled": returns(p, rule="dynamic", targets=targets_from(w4)),
            "4b AI volatility-scaled": returns(p, rule="dynamic", targets=targets_from(w4b)),
            "5 crash brake (200-day SMA)": returns(p, rule="dynamic", targets=targets_from(w5))}
    s = {n: summary(r) for n, r in rets.items()}
    known = target.loc[p.index].dropna().index
    mae_ai = (ai.loc[known] - target.loc[known]).abs().mean()
    mae_naive = (naive.loc[known] - target.loc[known]).abs().mean()
    ai_helps = mae_ai < mae_naive and s["4b AI volatility-scaled"]["sharpe"] > s["4 volatility-scaled"]["sharpe"]
    chart(rets, Path("reports/ideas-equity.png"))
    names = ("4 volatility-scaled", "4b AI volatility-scaled", "5 crash brake (200-day SMA)")
    return ["## Ideas 4, 4b, 5 — Dynamic BTC share, rest in gold (2019-01-01 → 2026-09-30)", "",
            *[f"- {n}: {verdict_text(dyn_verdict(s[n], s['Hold BTC'], s['A1 50/50 quarterly']))}" for n in names],
            "", table(s, FMT), "",
            f"Volatility forecast error (MAE, annualized vol): AI {mae_ai:.3f} vs naive 30-day {mae_naive:.3f}. "
            f"AI helps: **{'yes' if ai_helps else 'no'}**.",
            f"Average BTC weight: idea 4 {w4.mean():.0%}, idea 4b {w4b.mean():.0%}, idea 5 {w5.mean():.0%}.", "",
            "![equity](ideas-equity.png)", "", "### Yearly returns", "", yearly_table(rets), ""]


def main() -> None:
    px = build_prices()
    md = ["# Ideas 1–5 — Results", "",
          "Pre-registration: `docs/specs/2026-10-06-ideas-preregistration.md` (rules fixed before this run).",
          "Gold = COMEX futures (Yahoo GC=F) before 2020-09-01, PAXG after. Costs 0.15% per traded dollar. "
          "Not financial advice.", ""]
    md += idea1(px) + ideas_dynamic(px) + idea3(px)
    Path("reports/ideas-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote reports/ideas-report.md")


if __name__ == "__main__":
    main()
