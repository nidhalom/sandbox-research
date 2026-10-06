# Pre-registration — BTC + Cash, Quarterly Rebalancing

**Written:** 2026-10-06, before this backtest was run. Gold is set aside (Shariah status uncertain).

## Why

Every trading bot tested so far was NO-GO. Holding beat them, and mixing BTC with a steady asset
softened crashes. Without gold, the steady asset is cash. 50/50 BTC + cash quarterly was glimpsed once
on 2020–2026 during an audit (Sharpe 0.97 vs 0.85 for hold BTC), so that period is **not** used for the verdict.

## Rules

| Item | Value |
|---|---|
| Assets | BTCUSDT spot and cash (USDT or bank cash, earning 0%) |
| Mixes (BTC/cash) | **30/70, 50/50, 70/30**, all fixed now |
| Rebalancing | First trading day of each quarter, back to the mix |
| Costs | 0.15% per traded dollar (fee + half-spread); fills at the daily close |
| **Verdict period** | **2017-08-17 → 2020-08-31** (includes the 2018 crash; BTC + cash never examined here) |
| Also reported | Full 2017-08-17 → 2026-09-30; the owner's $3,000 plan (2,000 / +500 / +500) sold at 30 months, weekly starts from 2017-09, with p10 / median / p90 / worst / % losing and non-overlapping windows |

## GO criteria (per mix, verdict period, as in earlier pre-registrations)

All of: CAGR ≥ ⅔ of hold BTC; max drawdown no worse than −40%; Sharpe > hold BTC; Sharpe > the same mix
never rebalanced. Three mixes are tested; a pass by one of three is reported as such.

## Notes

Cash earning 0% is conservative (no interest is taken, by design). Whether USDT is acceptable is the
owner's scholar's decision; bank cash avoids the question but makes rebalancing slower. A GO justifies
Testnet paper trading only. Not financial advice.
