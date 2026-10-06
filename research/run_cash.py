"""BTC + cash, quarterly rebalancing (pre-registration docs/specs/2026-10-06-btc-cash-preregistration.md)."""
from pathlib import Path

import pandas as pd

from botcore.metrics import summary
from research.gold import build_prices
from research.run_core import PLAN, core_verdict, describe, exit_fixed, months_later, plan_gain
from research.run_ideas import FMT, FMT_ROLL, returns, verdict_text
from research.run_phase1 import chart, table, yearly_table

MIXES = (0.3, 0.5, 0.7)
V_START, V_END = "2017-08-17", "2020-08-31"


def prices() -> pd.DataFrame:
    px = build_prices()[["BTC"]].copy()
    px["CASH"] = 1.0
    return px


def mix(b: float) -> dict:
    return {"BTC": b, "CASH": 1 - b}


def main() -> None:
    px = prices()
    p = px.loc[V_START:V_END]
    btc = summary(returns(p, {"BTC": 1.0}))
    rows, verdicts = {"Hold BTC": btc}, []
    for b in MIXES:
        s, never = summary(returns(p, mix(b), "quarterly")), summary(returns(p, mix(b)))
        name = f"{b:.0%} BTC / {1 - b:.0%} cash quarterly"
        rows[name], rows[f"{b:.0%} BTC / {1 - b:.0%} cash never rebalanced"] = s, never
        verdicts.append(f"- {name}: {verdict_text(core_verdict(s, btc, never))}")
    full_rets = {"Hold BTC": returns(px, {"BTC": 1.0})}
    for b in MIXES:
        full_rets[f"{b:.0%}/{1 - b:.0%} quarterly"] = returns(px, mix(b), "quarterly")
    full = {n: summary(r) for n, r in full_rets.items()}
    starts = [s for s in pd.date_range("2017-09-01", px.index[-1], freq="W-MON")
              if months_later(px.index, s, 30) is not None]
    roll = {}
    for name, w, rule in [("Hold BTC", {"BTC": 1.0}, "none")] + [
            (f"{b:.0%} BTC / {1 - b:.0%} cash quarterly", mix(b), "quarterly") for b in MIXES]:
        g = [plan_gain(px[list(w)], w, rule, s, PLAN, exit_fixed(30), 30) for s in starts]
        roll[name] = describe(g, starts, 30)
    chart(full_rets, Path("reports/cash-equity.png"))
    md = ["# BTC + Cash — Results", "",
          "Pre-registration: `docs/specs/2026-10-06-btc-cash-preregistration.md` (rules fixed before this run).",
          "Cash earns 0%. Costs 0.15% per traded dollar. Not financial advice.", "",
          f"## Verdicts ({V_START} → {V_END}, includes the 2018 crash)", "", *verdicts, "", table(rows, FMT), "",
          "## Full period 2017-08-17 → 2026-09-30 (informational)", "", table(full, FMT), "",
          "![equity](cash-equity.png)", "", "### Yearly returns", "", yearly_table(full_rets), "",
          "## Owner's $3,000 plan, sold at month 30 (weekly starts from 2017-09, heavily overlapping)", "",
          table(roll, FMT_ROLL), ""]
    Path("reports/cash-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote reports/cash-report.md")


if __name__ == "__main__":
    main()
