"""CPU machine-learning test on BTC (pre-registration 2026-10-06, part 3)."""
import argparse
from pathlib import Path

import pandas as pd

from botcore.metrics import summary
from botcore.portfolio import COST
from research.run_phase1 import chart, table, yearly_table
from research.sentiment import load_fear_greed
from research.validation import bootstrap_ci

HORIZON = 7
THRESHOLD = 0.55
TRAIN_START = "2018-02-01"
TEST_START = "2020-01-01"


def make_features(close: pd.Series, fng: pd.Series) -> pd.DataFrame:
    f = pd.DataFrame(index=close.index)
    for n in (1, 7, 30):
        f[f"ret_{n}"] = close.pct_change(n)
    f["vol_30"] = close.pct_change().rolling(30).std()
    for n in (20, 50, 100):
        f[f"sma_{n}"] = close / close.rolling(n).mean() - 1
    g = fng.reindex(close.index).ffill()
    f["fng"] = g
    f["fng_chg_7"] = g.diff(7)
    return f


def make_target(close: pd.Series) -> pd.Series:
    future = close.shift(-HORIZON)
    return (future > close).astype(float).where(future.notna())


def train_end(cut: pd.Timestamp) -> pd.Timestamp:
    """Last day whose 7-day target is known at the close before `cut`."""
    return cut - pd.Timedelta(days=HORIZON + 1)


def walk_forward_proba(feats: pd.DataFrame, target: pd.Series) -> pd.Series:
    from sklearn.ensemble import HistGradientBoostingClassifier

    out = []
    for year in range(pd.Timestamp(TEST_START).year, feats.index[-1].year + 1):
        cut = pd.Timestamp(f"{year}-01-01")
        train = feats.loc[TRAIN_START:train_end(cut)]
        y = target.loc[train.index]
        ok = y.notna()
        model = HistGradientBoostingClassifier(random_state=0).fit(train[ok], y[ok])
        test = feats.loc[cut:f"{year}-12-31"]
        if len(test):
            out.append(pd.Series(model.predict_proba(test)[:, 1], index=test.index))
    return pd.concat(out)


def strategy_returns(close, proba, threshold=THRESHOLD, cost=COST) -> pd.Series:
    pos = (proba > threshold).astype(float)              # decided at close t
    ret = close.pct_change().reindex(pos.index).fillna(0)
    switches = pos.diff().abs().fillna(pos.iloc[0])      # traded at close t
    return pos.shift(1).fillna(0) * ret - switches * cost


def ml_verdict(r, btc_r, ci) -> list[str]:
    s, fails = summary(r), []
    if s["sharpe"] < 1.0:
        fails.append("Sharpe below 1.0")
    if ci["sharpe"][0] < 0.5:
        fails.append("Sharpe CI lower bound below 0.5")
    if s["max_dd"] < -0.35:
        fails.append("max drawdown worse than -35%")
    if s["sharpe"] <= summary(btc_r)["sharpe"]:
        fails.append("Sharpe not above hold BTC")
    return fails

def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/spot_1d")
    args = ap.parse_args(argv)
    close = pd.read_parquet(Path(args.data) / "BTCUSDT.parquet").set_index("date")["close"]
    close.index = pd.to_datetime(close.index)
    close = close.loc[:"2026-09-30"]
    fng = load_fear_greed("data/fear_greed.csv")
    proba = walk_forward_proba(make_features(close, fng), make_target(close))
    r = strategy_returns(close, proba)
    btc = close.pct_change().reindex(r.index).fillna(0)
    ci = bootstrap_ci(r)
    fails = ml_verdict(r, btc, ci)
    pos = (proba > THRESHOLD).astype(float)
    hit = ((proba > 0.5) == (make_target(close).reindex(proba.index) == 1.0))[make_target(close).reindex(proba.index).notna()]
    rows = {"ML model": summary(r), "Hold BTC": summary(btc)}
    chart({"ML model": r, "Hold BTC": btc}, Path("reports/ml-equity.png"))
    md = [
        "# CPU Machine-Learning Test on BTC — Results",
        "",
        "Pre-registration: `docs/specs/2026-10-06-core-and-ml-preregistration.md` (rules fixed before this run).",
        f"Test {r.index[0].date()} → {r.index[-1].date()}, walk-forward yearly retraining, costs 0.15% per switch.",
        "One fixed configuration, no tuning loop, so PBO is not computed.",
        "",
        "## Verdict",
        "",
        "**GO** (Testnet paper trading only)" if not fails else "**NO-GO**: " + "; ".join(fails),
        "",
        table(rows, {"cagr": "+.1%", "max_dd": ".1%", "sharpe": ".2f"}),
        "",
        f"Sharpe 90% bootstrap CI: {ci['sharpe'][0]:.2f} to {ci['sharpe'][1]:.2f}. "
        f"Time in market: {pos.mean():.0%}. Switches: {int(pos.diff().abs().sum())}. "
        f"Direction hit rate (P>0.5 vs actual 7-day move): {hit.mean():.1%}.",
        "",
        "![equity](ml-equity.png)",
        "",
        "## Yearly returns",
        "",
        yearly_table({"ML model": r, "Hold BTC": btc}),
    ]
    Path("reports/ml-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote reports/ml-report.md")


if __name__ == "__main__":
    main()
