"""Ensemble trend basket (#1) and funding-rate overlay (#3)
(pre-registration docs/specs/2026-10-06-ensemble-trend-funding-preregistration.md)."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from botcore.ensemble import ensemble_fraction, hysteresis, run_book
from botcore.metrics import summary
from botcore.params import Params
from research.funding import download_funding, funding_signal
from research.panel import load_panel
from research.run_ideas import FMT
from research.run_phase1 import chart, table, yearly_table
from research.universe import eligible_mask

START, END = "2018-01-01", "2026-09-30"
DEV, HOLD = ("2018-01-01", "2021-12-31"), ("2022-01-01", "2026-09-30")
N, VOL_TGT, BAND = 10, 0.25, 0.20
COSTS = (0.002, 0.001, 0.003)


def monthly_universe(mask: pd.DataFrame) -> pd.DataFrame:
    firsts = mask[mask.index.day == 1]
    return firsts.reindex(mask.index, method="ffill").fillna(False).astype(bool)


def overlay(index, f) -> pd.Series:
    return hysteresis(funding_signal(f).reindex(index), on=0.30, off=0.10)


def apply_overlay(targets, force, on):
    t = targets.mul(1 - 0.5 * on, axis=0)
    f = force | pd.DataFrame(np.repeat((on.diff().fillna(0) != 0).to_numpy()[:, None], targets.shape[1], axis=1),
                             index=targets.index, columns=targets.columns)
    return t, f


def slice_summary(eq: pd.Series, period) -> dict:
    return summary(eq.pct_change().loc[period[0]:period[1]].dropna())


def build(panel):
    mask = eligible_mask(panel, replace(Params(), min_history_days=365, universe_size=N)).loc[START:END]
    uni = monthly_universe(mask)
    coins = [c for c in uni.columns if uni[c].any()]
    if "BTCUSDT" not in coins:
        coins.append("BTCUSDT")
    o, c, uni = (panel["open"].loc[START:END, coins], panel["close"].loc[START:END, coins], uni[coins])
    full_close = panel["close"][coins].loc[:END]
    frac = pd.DataFrame({s: ensemble_fraction(full_close[s]) for s in coins}).loc[START:END]
    sigma = full_close.pct_change().rolling(90, min_periods=90).std().loc[START:END] * np.sqrt(365)
    ens_t = (uni * (1 / N) * frac * np.minimum(1, VOL_TGT / sigma)).fillna(0)
    ens_f = (frac.diff().fillna(0) != 0) | (uni != uni.shift().fillna(False))
    ew_t = (uni * (1 / N)).astype(float)
    month_start = pd.Series(c.index.day == 1, index=c.index)
    ew_f = pd.DataFrame(np.repeat(month_start.to_numpy()[:, None], len(coins), axis=1), index=c.index, columns=coins)
    btc_t = pd.DataFrame(0.0, index=c.index, columns=coins)
    btc_t["BTCUSDT"] = 1.0
    btc_f = pd.DataFrame(False, index=c.index, columns=coins)
    btc_f.iloc[0] = True
    return o, c, {"Ensemble trend basket": (ens_t, ens_f), "Equal-weight top-10 (monthly)": (ew_t, ew_f),
                  "Hold BTC": (btc_t, btc_f)}


def ens_verdict(s, btc, ew) -> list[str]:
    fails = []
    floor = 2 / 3 * btc["cagr"] if btc["cagr"] > 0 else 0.0
    if s["cagr"] < floor:
        fails.append("CAGR below 2/3 of hold BTC" if btc["cagr"] > 0 else "CAGR below 0")
    if s["max_dd"] < -0.40:
        fails.append("max drawdown worse than -40%")
    if s["sharpe"] <= btc["sharpe"]:
        fails.append("Sharpe not above hold BTC")
    if s["sharpe"] <= ew["sharpe"]:
        fails.append("Sharpe not above equal-weight basket")
    return fails


def main() -> None:
    panel = load_panel("data/spot_1d")
    o, c, books = build(panel)
    on = overlay(c.index, pd.read_parquet(download_funding()))
    eqs, rows = {}, {}
    for cost in COSTS:
        for name, (t, f) in books.items():
            eqs[(name, cost)] = run_book(o, c, t, f, band=BAND if name.startswith("Ensemble") else 1e9, cost=cost)
            if name != "Equal-weight top-10 (monthly)":
                ot, of = apply_overlay(t, f, on)
                eqs[(name + " + funding overlay", cost)] = run_book(
                    o, c, ot, of, band=BAND if name.startswith("Ensemble") else 1e9, cost=cost)
    names = list(dict.fromkeys(n for n, _ in eqs))
    for period, label in [(HOLD, "Hold-out 2022-01 → 2026-09"), (DEV, "Development 2018 → 2021")]:
        rows[label] = {f"{n} ({cost:.2%})": slice_summary(eqs[(n, cost)], period) for cost in COSTS for n in names}
    h = rows["Hold-out 2022-01 → 2026-09"]
    btc, ew = h["Hold BTC (0.20%)"], h["Equal-weight top-10 (monthly) (0.20%)"]
    v1 = ens_verdict(h["Ensemble trend basket (0.20%)"], btc, ew)
    def keep(base):
        a, b = h[f"{base} (0.20%)"], h[f"{base} + funding overlay (0.20%)"]
        return b["sharpe"] > a["sharpe"] and b["max_dd"] > a["max_dd"]
    od = slice_summary(eqs[("Hold BTC + funding overlay", 0.002)], ("2020-01-01", "2021-12-31"))
    odb = slice_summary(eqs[("Hold BTC", 0.002)], ("2020-01-01", "2021-12-31"))
    primary = {n: eqs[(n, 0.002)].pct_change().loc[HOLD[0]:].dropna() for n in names}
    chart(primary, Path("reports/ensemble-equity.png"))
    md = ["# Ensemble Trend Basket and Funding-Rate Overlay — Results", "",
          "Pre-registration: `docs/specs/2026-10-06-ensemble-trend-funding-preregistration.md` (rules fixed before "
          "this run). Survivorship-free Binance spot universe; trades at next open. Not financial advice.", "",
          "## Verdicts (hold-out 2022-01-01 → 2026-09-30, 0.20% per side)", "",
          "- #1 Ensemble trend basket: " + ("**GO** (Testnet paper trading only)" if not v1 else "**NO-GO**: " + "; ".join(v1)),
          f"- #3 Funding overlay on hold BTC: **{'keep' if keep('Hold BTC') else 'drop'}**",
          f"- #3 Funding overlay on the ensemble basket: **{'keep' if keep('Ensemble trend basket') else 'drop'}**",
          f"- Overlay ON {on.loc[HOLD[0]:].mean():.0%} of hold-out days ({on.mean():.0%} of all days since 2018).", "",
          *[s for label, r in rows.items() for s in (f"## {label}", "", table(r, FMT), "")],
          f"Funding overlay, development 2020–2021 on hold BTC: with {od['sharpe']:.2f} Sharpe / {od['max_dd']:.1%} DD, "
          f"without {odb['sharpe']:.2f} / {odb['max_dd']:.1%}.", "",
          "![equity](ensemble-equity.png)", "", "### Yearly returns (hold-out, 0.20%)", "", yearly_table(primary), ""]
    Path("reports/ensemble-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote reports/ensemble-report.md")


if __name__ == "__main__":
    main()
