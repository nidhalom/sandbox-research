"""Phase 1 entry point: download data, backtest, tune walk-forward, validate, write the report."""
import argparse
import datetime as dt
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from botcore.metrics import equity_curve, summary, yearly_returns
from botcore.params import Params
from research.backtest import benchmark_equal_weight, benchmark_hold, build_market, run_backtest
from research.data import download_all
from research.panel import load_panel
from research.report import go_no_go, write_report
from research.sentiment import load_fear_greed
from research.tune import walk_forward
from research.validation import bootstrap_ci, daily_sr, deflated_sharpe, pbo

REPORTS = Path("reports")
MIN_TRIALS_FOR_STATS = 20


def table(rows: dict[str, dict], fmt: dict[str, str]) -> str:
    cols = list(fmt)
    lines = ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for name, vals in rows.items():
        lines.append(f"| {name} | " + " | ".join(format(vals[c], fmt[c]) for c in cols) + " |")
    return "\n".join(lines)


def yearly_table(series: dict[str, pd.Series]) -> str:
    df = pd.DataFrame({k: yearly_returns(v) for k, v in series.items()})
    lines = ["| Year | " + " | ".join(df.columns) + " |", "|---" * (len(df.columns) + 1) + "|"]
    for year, row in df.iterrows():
        lines.append(f"| {year} | " + " | ".join(f"{v:+.1%}" for v in row) + " |")
    return "\n".join(lines)


def chart(series: dict[str, pd.Series], path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    for name, r in series.items():
        eq = equity_curve(r)
        ax1.plot(eq.index, eq.values, label=name)
        ax2.plot(eq.index, (eq / eq.cummax() - 1).values, label=name)
    ax1.set_yscale("log")
    ax1.set_title("Growth of 1 (log scale)")
    ax2.set_title("Drawdown")
    ax1.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/spot_1d")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--first-test-year", type=int, default=2021)
    ap.add_argument("--train-start", default="2019-01-01")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args(argv)

    if not args.skip_download:
        print("downloading data (cached files are skipped)...")
        download_all(args.data)
    panel = load_panel(args.data)
    base = Params()
    market = build_market(panel, base, load_fear_greed("data/fear_greed.csv"))
    start = f"{args.first_test_year}-01-01"
    last_year = market.close.index[-1].year
    print(f"data {market.close.index[0].date()} -> {market.close.index[-1].date()}, {market.close.shape[1]} symbols")

    untuned = run_backtest(market, base, start)
    greed = run_backtest(market, replace(base, greed_threshold=80), start)
    worst_stops = run_backtest(market, replace(base, stop_fill=1.0), start)
    print(f"walk-forward {args.first_test_year}-{last_year}, {args.trials} trials per fold...")
    wf = walk_forward(market, base, args.first_test_year, last_year, args.train_start, args.trials)

    benchmarks = {"Hold BTC": benchmark_hold(market.close, "BTCUSDT", start),
                  "Equal-weight universe": benchmark_equal_weight(market, start)}
    last_fold = wf.trials[-1]
    all_trials = [r for fold in wf.trials for _, r in fold]
    enough = len(last_fold) >= MIN_TRIALS_FOR_STATS
    pbo_value = pbo(pd.DataFrame({k: r for k, (_, r) in enumerate(last_fold)})) if enough else None
    dsr = deflated_sharpe(wf.returns, [daily_sr(r) for r in all_trials]) if enough else None
    ci = bootstrap_ci(wf.returns)
    checks, go = go_no_go(wf.returns, benchmarks, ci, pbo_value)

    strategies = {"Walk-forward tuned (primary)": wf.returns, "Untuned defaults": untuned.returns,
                  "Untuned + Fear&Greed filter": greed.returns,
                  "Untuned, stops fill at day's low (worst case)": worst_stops.returns, **benchmarks}
    REPORTS.mkdir(exist_ok=True)
    chart(strategies, REPORTS / "phase1-equity.png")

    fmt = {"cagr": "+.1%", "max_dd": ".1%", "sharpe": ".2f"}
    chosen = "\n".join(f"- {y}: windows={p.windows}, atr_mult={p.atr_mult:.2f}, band={p.band:.3f}"
                       for y, p in wf.chosen.items())
    verdict = "**GO**: proceed to phase 2." if go else "**NO-GO**: do not build the live bot on this strategy yet."
    sections = {
        "Verdict": verdict + "\n\n" + "\n".join(f"- {'✅' if ok else '❌'} {name}" for name, ok in checks.items()),
        "Out-of-sample results": table({k: summary(v) for k, v in strategies.items()}, fmt)
                                 + "\n\n![equity](phase1-equity.png)",
        "Yearly returns": yearly_table(strategies),
        "Confidence (90%, stationary bootstrap) for the primary strategy":
            f"- CAGR: {ci['cagr'][0]:+.1%} to {ci['cagr'][1]:+.1%}\n"
            f"- Sharpe: {ci['sharpe'][0]:.2f} to {ci['sharpe'][1]:.2f}\n"
            f"- Max drawdown: {ci['max_dd'][0]:.1%} to {ci['max_dd'][1]:.1%}",
        "Overfitting checks": (
            f"- PBO (last fold, {len(last_fold)} trials): {pbo_value:.2f}\n"
            f"- Deflated Sharpe probability (all {len(all_trials)} trials): {dsr:.2f}\n"
            "- Both understate the true search: the design and untuned settings were chosen after a "
            "probe on 2020–2026 data, and Optuna's trials cluster, which narrows their spread."
            if enough else
            f"- Not computed: only {len(last_fold)} trials per fold (need ≥ {MIN_TRIALS_FOR_STATS})."),
        "Parameters chosen each year": chosen,
        "Trading activity": f"- Walk-forward: {wf.trades} trades, costs {wf.costs:,.0f} USDT "
                            f"(each year restarts at 10,000)\n"
                            f"- Untuned: {untuned.trades} trades, {untuned.stops} stops hit, "
                            f"costs {untuned.costs:,.0f} USDT on 10,000 start",
        "Caveats": "- Each walk-forward year restarts with fresh capital and brake state.\n"
                   "- Not fully out-of-sample: the strategy design, the 20% volatility target, the "
                   "brakes and the untuned defaults were chosen after a probe on 2020–2026 data; "
                   "walk-forward only re-tunes 5 parameters. Expect live results to be worse.\n"
                   "- Equal-weight benchmark pays no costs.\n"
                   "- Data ends at the last complete month in the Binance archive.",
        "Base parameters": "```\n" + "\n".join(f"{k} = {v}" for k, v in asdict(base).items()) + "\n```",
    }
    run_details = (f"- Generated: {dt.datetime.now():%Y-%m-%d %H:%M}\n"
                   f"- Command: run_phase1 --trials {args.trials} --first-test-year {args.first_test_year} "
                   f"--train-start {args.train_start}\n"
                   f"- Data: {market.close.shape[1]} symbol files, "
                   f"{market.close.index[0].date()} to {market.close.index[-1].date()}\n"
                   f"- Test period: {start} to {market.close.index[-1].date()}")
    path = write_report(REPORTS / "phase1-report.md", {"Run details": run_details, **sections})
    print(f"report written: {path.resolve()}  verdict: {'GO' if go else 'NO-GO'}")


if __name__ == "__main__":
    main()
