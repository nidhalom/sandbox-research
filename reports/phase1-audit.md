# Phase 1 Audit: Research Engine and Report

Auditor: independent review (Fable 5.1), 2026-10-05. Scope: `botcore/*.py`, `research/*.py`, `tests/`, `data/spot_1d/*.parquet`, `reports/phase1-report.md`.
How I checked: I read all the code. I ran light read-only scripts over the 756 parquet files: a price-anomaly scan, eligibility reconstruction, and four short 1–2 month backtest windows around known crash events. I ran `pytest` (56 passed). I did not run `run_phase1.py` or any full backtest. A full run (`--skip-download --trials 60`) was still in progress when I wrote this, so the figures in its final report still need checking against the items below.

**Bottom line:** I found no look-ahead in the decision path and no train/test leakage in the walk-forward. The engine is basically sound. The current report file can't be trusted, because it is a smoke run built on partial data. There are several ways the numbers could come out wrong:
- a latent data-integrity hole that could create returns of ×1000 or more out of nothing (redenominations, a reused symbol, interior gaps)
- optimistic stop fills on flash-crash days, including one inside the test window
- a stablecoin leaking into the universe
- the overfitting statistics understate how many trials were really run
- the "walk-forward is the honest line" claim, which is overstated

---

## Critical

### C1. The existing `reports/phase1-report.md` is a stale smoke run built on a partly downloaded dataset
- Evidence: the report and chart were written at 20:10:49. The parquet files were written between 20:05 and 20:58, and the download log says 757 symbols. The report says "PBO (last fold, **2 trials**)" and shows only 2025–2026 test years, so it used `--first-test-year 2025 --trials 2`. Downloads run in alphabetical order, so many late-alphabet majors were probably missing at 20:10. I recomputed one figure on the complete data: the equal-weight benchmark for 2025 is **−36.2%**, but the report says **−55.5%** (2026: −30.9% against −53.6%). Hold-BTC matches (−6.3%) because BTC was already downloaded.
- Effect: every number in that file is unreliable, the NO-GO verdict included. A PBO from 2 trials means nothing.
- Fix: discard it and use the output of the full run. Have `run_phase1.py` stamp the report with run metadata: CLI args (trials, first test year, train start), symbol count, data date range, the list of skipped downloads, a code hash, and wall-clock time. Refuse to compute PBO or the deflated Sharpe with fewer than about 20 trials, or print "not meaningful".

## Important

### I1. Prices are not adjusted for redenominations or a reused symbol, and interior data gaps are not treated as halts or delistings (could create returns of ×1000 or more out of nothing)
- Where: `research/panel.py:14` (raw concatenation), `research/backtest.py:37` and `:82-85` (`last_valid` is the *final* valid date, so an interior gap is never a delisting), `:88` and `:106` (a position is frozen at the stale price while `open` is NaN), `:147` (marked at the ffilled close), `botcore/risk.py:31-34` (no stop can fire during the gap because `low` is NaN).
- Evidence from the data scan (the moves span the gap):
  - `LUNAUSDT`: old LUNA last closes at 0.00005 (2022-05-13). After a 17-day gap the same symbol becomes LUNA 2.0 and opens at 1.00 (2022-05-31), a **×20,000** move. Old LUNA was in the top-10 universe through 2022-05-13.
  - `COCOSUSDT` ×1000 (2021-01-23), `QUICKUSDT` ÷1000 (2023-07-21), `SUNUSDT` ÷1000 (2021-06-18), `DREPUSDT` ×100 (2021-04-02), `BNXUSDT` (2023-02-22), `VENUSDT` (2018-10-19). All are redenominations across 3–5 day gaps.
  - `FTTUSDT`: last trade 2022-11-15 at 1.43, then a **310-day** gap, then it resumes at 1.10 on 2023-09-22. FTT was in the universe 2022-11-08 to 11-15.
  - Also, `history = close.notna().cumsum()` (`research/universe.py:29`) counts old LUNA's history for LUNA 2.0, so the 180-day listing rule is skipped for a different asset.
- Effect today: I checked the windows around LUNA and FTT with default parameters, and neither was held at the moment its gap began. The trend filter had already taken them to zero, and the other symbols were never in the top 10. So the default-parameter results are probably **not** contaminated now. But any position open when such a gap starts is revalued at an unrelated price, with no stop possible. One hit at the 30% cap turns into +30,000% or −30% of equity. It would also dominate an Optuna trial's Sharpe and get that trial selected. This is a "fake profit" mechanism that only the trend filter happens to keep away.
- Fix: (a) keep a corporate-actions table covering redenominations, symbol reuse (LUNA → split into LUNA_OLD and LUNA2), and ticker migrations, and split or rescale those series. (b) In the backtest, treat any gap longer than N days (say 3) while a position is held as a delisting. Liquidate at the last close minus the haircut, then start a fresh history if the symbol comes back. (c) Add a data-quality guard that fails the run if any |close-to-close log return| > 3 spans a gap, unless the corporate-actions table whitelists it.

### I2. Stops fill at the stop price on flash-crash days, which is optimistic (one such day is in the test window)
- Where: `research/backtest.py:135-136`, `px = min(O, stop)`.
- Evidence: in a short window run (2025-09-01 → 10-12, default parameters), on **2025-10-10** these positions were stopped out at their stop prices. The day's lows were far lower: DOGE low −57% below its stop, BNB −23%, ETH −18%, SOL −15%, BTC −12%. Weighted by position size, filling at the low instead would cost about **7% of equity on that one day**. Also, on 2020-03-12 the `LINKUSDT` daily low is 0.0001 (stop 3.38, 16% weight; `RLCUSDT` shows the same pattern), and on 2021-05-19 ADA's low was −34% below its stop. On Binance, stop-market orders fill into the cascade, not at the trigger.
- Direction: optimistic. It flatters the very days the stop layer exists for, and 2025-10-10 is in the out-of-sample period.
- Fix: model slippage in the fill, for example `px = min(O, stop) - k * (min(O, stop) - low)` with k around 0.25–0.5. Or report a fill-at-low sensitivity line alongside the main result. At minimum, report how much the go/no-go numbers move under k = 0.5.

### I3. Stablecoin `RLUSDUSDT` (also `USDEUSDT`, `BFUSDUSDT`, `FRAXUSDT`, `USDSBUSDT`) is missing from the exclusion list
- Where: `research/universe.py:5-9`.
- Evidence: RLUSD is in the top-10 universe 2026-07-20 → 2026-09-24. Its volatility is about 1%, so `score/vol` is huge, and the strategy repeatedly puts **30% (the cap)** into it as `sign(close − SMA)` flips on noise. Mean weight is 0.085 over the window. Because its raw weight dominates the vector, the vol scaling in `botcore/strategy.py:25-31` also shrinks every other coin's weight. It also adds round-trip costs on 30% notional each time it flips. The equal-weight benchmark gets a zero-return member as well.
- Direction: pessimistic for 2026 for both the strategy and the benchmark. It is still a contamination of the out-of-sample period, and it inflates trade and cost counts.
- Fix: add RLUSD, USDE, BFUSD, FRAX, USDSB, and, as a policy decision, gold tokens PAXG and XAUT (PAXG is in the universe for 85 days in 2026). Add a generic guard as well: exclude any symbol whose 60-day annualised vol is below 5%.

### I4. The walk-forward is not truly out of sample for the structural parameters, and the report says it is
- Where: `research/run_phase1.py:111-113` (caveat text), `research/tune.py:13-20` (only windows, atr_mult and band are tuned), spec line 27 (the probe ran on 2020-06 → 2026-10).
- Several choices were made after seeing the full 2020–2026 probe: vol_target, caps, brakes, ATR window, cooldown, cov and vol windows, universe size, the 2/3-majority score clipping, and the strategy family itself. The walk-forward only re-tunes 5 numbers inside that frame.
- Direction: optimistic. The bias is in the design itself, so it can't be measured exactly.
- Fix: reword the caveat ("walk-forward re-tunes 5 parameters; the strategy design and the other parameters were chosen after a full-sample probe"). Keep a true holdout from now on: paper-trade, or hold back the period after the probe. Count the probe configurations in the deflated Sharpe's trial count (see I5).

### I5. The overfitting statistics understate how much searching was done
- Where: `research/run_phase1.py:82-84`, `research/validation.py:42-55`.
  - The deflated Sharpe uses only the **last fold's 60 trials** for both N and the variance of trial Sharpes. The real search is at least 60 × 6 folds, plus the probe and the design iterations. TPE also concentrates its samples near the optimum, which shrinks `std(trial SRs)`. Both effects make SR₀ too low and the deflated Sharpe probability too high (optimistic).
  - PBO is also computed only on the last fold's in-sample matrix of TPE-clustered trials, which are near-duplicates. That makes the PBO less informative (the direction varies; the tie handling at `validation.py:74` leans conservative).
- Fix: compute the deflated Sharpe with N = all trials across folds plus an honest estimate of the design trials. Take the variance from a uniform/random-sampled set of trials, not from TPE output. Report the PBO for each fold, and also on a random-search trial set.

### I6. The report has no run provenance, so its numbers can't be checked
- Where: `research/run_phase1.py:97-117`.
- No trial count, test-year range, symbol count or skipped-symbol list is recorded. There are no walk-forward trades, costs or turnover either; only the untuned run's are shown. `download_all` swallows failures silently (`research/data.py:84-89`): the log lists 757 symbols but there are 756 files, and I couldn't identify the missing one offline. C1 is exactly the failure this would have caught.
- Fix: add a "Run metadata" section, walk-forward trades/costs/turnover, and the skipped-symbol list. Fail the run if any download failed, unless the symbol is explicitly allowed to be skipped.

## Minor

1. **Ticker migrations are treated as delistings** (`research/backtest.py:82-85`): BCHABC → BCH (2019-11-28, BCHABC was in the universe at the time), MATIC → POL, FTM → S, RNDR → RENDER, BTT → BTTC. The 10% haircut is a fake loss, and the successor needs 180 fresh days, so BCH was out of the universe 2019-11 → 2020-05. This is pessimistic and mostly hits the training folds. Fix: map these in the corporate-actions table (I1).
2. **Suspect ticks inflate ATR**: LINK and RLC lows of 0.0001 on 2020-03-12, a BUSD open of 238.7 on 2019-09-20, a WBTC low of 5,209 on 2024-11-23, and many 2025-10-10 wicks. The effect is that ATR(14) is inflated for 14 days and stops sit too far away. Fix: winsorise or flag single-candle wicks over 80% when the close recovers, or add ATR sensitivity.
3. **`TONUSDT` data ends exactly 2026-06-30** (a month end; it was in the universe until 06-05). Check whether this is a real delisting or a missing archive month. A missing month would trigger a false delisting haircut. `AEURUSDT` ends 2026-07-31 too.
4. **Leveraged tokens `BULLUSDT`/`BEARUSDT`** (the BTC 3x tokens from 2019–20) slip past `is_excluded` (`research/universe.py:20-22`) because the base is empty. They were never in the universe, so the effect is nil. Wrapped duplicates (WBTC, WBETH, BETH, BNSOL) are also not excluded.
5. **"Fill at next open" is effectively the same price as the signal**: Binance's daily open is the previous close (median |open/prev close − 1| = 0.03%). This is not look-ahead, but it assumes the bot trades within seconds of 00:00 UTC. Fix: add a sensitivity case that fills at the open plus X bps, or at the 1-hour VWAP.
6. **Vol targeting ignores the caps**: `botcore/strategy.py:29-31` clips at 30% and then does not re-scale the rest, so realised portfolio vol falls short of target whenever a low-vol coin is clipped. `cov.fillna(0)` (`:25`) treats a missing variance as zero, which would over-scale a coin with sparse returns.
7. **Walk-forward restarts** (`research/tune.py:53`): each year starts from fresh cash and fresh brake, stop and cooldown state, and the year-end portfolio is dropped without exit costs. The cost effect is small. Brake behaviour across year boundaries is not tested. This is disclosed in the report.
8. **The equal-weight benchmark is flattered**: no costs, close-to-close entry at the decision close, and delisted names drop out of the mean (NaN return) instead of losing value (`research/backtest.py:173-176`). This only makes the "beat the benchmark" check harder, so it is conservative. It also includes RLUSD (I3).
9. **The no-look-ahead test is weak** (`tests/test_backtest.py:27-35`): it scales prices but not `quote_volume`, so the universe timing is never exercised. It doesn't check that the targets for day *t* are unchanged when day *t*'s close, high, low or volume change. There are no tests for interior gaps or redenominations.
10. **`Result.costs` leaves out delist haircuts**, and the report doesn't break costs down (fee, spread, impact).
11. **No capacity analysis**: at 10k USDT the sqrt impact is negligible. The results say nothing about larger capital.

---

## Checked and found OK

- **Decision timing**: targets use `raw.iloc[i-1]`, `eligible.iloc[i-1]`, `returns.iloc[i-60:i]`, `ADV[i-1]` and `ATR[i-1]`, all known at the previous close. Orders fill at `open[i]`.
- **The trailing stop** is updated from `close[i]` and `ATR[i]` after the close, so it only takes effect the next day. A gap through the stop fills at the open. Same-day stops on fresh buys are valid, because the low comes after the open.
- **The universe is point-in-time**: rolling 30-day quote volume up to that close, at least 180 days of history, and a close present that day. Delisted coins are included. The archive covers old delisted pairs well (BCC, BCHSV, VEN, MCO, ERD, NPXS, LEND, the UST family and others). Most delisted coins left the top 10 long before they were delisted: only BCC, BCHABC and TON were in the universe at delisting.
- **Using `last_valid` to detect delisting** relies on future knowledge, but only to time the liquidation one day after the last trade, at the last close minus 10%. The announcement crash is already in the price series. I judge this acceptable and roughly neutral to conservative (see I1 for gaps).
- **No train/test leakage in the walk-forward**: tuning ends Dec 31, testing starts Jan 1, and all indicators are backward-looking rolling windows. Warm-up uses only past data. The parameters are fixed before the test year.
- **Cost accounting**: fee, half-spread and impact are charged on every rebalance trade and every stop exit. Sells run before buys. The buy scaling never overdraws cash (cost is concave in notional, plus the 0.999 buffer). No trade happens on NaN-open days; there are no open-NaN/close-present cells in the data anyway.
- **Equity, units, weights, returns**: marks use the ffilled close, the first-day return is measured against initial capital, and weights are recorded at the close.
- **Brakes and cooldown**: the half, pause and stop thresholds and the resume hysteresis behave as specified. Cooldown blocks exactly `stop_cooldown_days` days.
- **Data parsing**: microsecond timestamps from 2025 on are handled. There are no non-positive prices, no NaN opens or closes, and only one high/low inconsistency (AUDUSDT). Daily alignment is UTC 00:00.
- **Fear & Greed**: the value dated *t−1* is used for the open of *t*, so no look-ahead.
- **Statistics formulas**: Sharpe and CAGR annualised with 365 days (right for crypto). The deflated Sharpe formula (SR₀ via the expected max of N, skew and non-excess kurtosis, T−1) matches Bailey & López de Prado. PBO/CSCV ranking and logits are correct. The stationary bootstrap (Politis–Romano, geometric blocks, wrap-around) is correct. The 90% CIs come from the 5th and 95th percentiles.
- **Tests**: 56 pass.
