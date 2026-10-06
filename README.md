# Crypto Trend Research Engine

A research engine that tests whether a systematic trend-following strategy can make money on crypto
markets **after realistic costs and without the usual backtest biases**. It decides before any capital
is put at risk, and it is built to say "no" when the evidence says no.

**Phase 1 verdict: NO-GO.** A naive test on 10 hand-picked coins showed **+33% a year**. After removing
survivorship bias, modelling costs realistically and validating out-of-sample, the same idea delivered
**+1.8% a year**, against **+20.3%** for simply holding Bitcoin. The engine caught the mirage before it
cost anything.

## What it does

1. **Downloads survivorship-free data**: daily candles for all 757 Binance USDT spot pairs ever listed,
   including coins that were later delisted (LUNA, FTT…), from Binance's public archive.
2. **Builds a point-in-time universe**: each day, the 10 most traded coins *as known at that time*, with
   stablecoins, leveraged tokens and pegged assets excluded.
3. **Simulates the strategy day by day**: decisions use only data up to the previous close, orders fill at
   the next open, exchange-side stop-losses trigger intraday, and drawdown brakes cut risk in crashes.
4. **Charges realistic costs**: exchange fee, half-spread and square-root market impact on every trade;
   stop fills slip towards the day's low in flash crashes.
5. **Validates honestly**: walk-forward tuning (parameters chosen only on past data), bootstrap confidence
   intervals, Deflated Sharpe Ratio, and Probability of Backtest Overfitting (CSCV).
6. **Writes a go/no-go report** with pre-defined pass criteria.

## Strategy (long-only spot)

- Trend score per coin: average of `sign(close − SMA(n))` for n = 20, 50, 100.
- Position size: score ÷ volatility, then the whole portfolio is scaled to a 20% annual volatility target
  using the 60-day covariance matrix (so correlated coins are not double-counted).
- Caps: 30% per coin, 100% gross: no leverage, no shorting, no futures.
- Risk: 3×ATR trailing stops, drawdown brakes at −20% / −30% / −35%.

## Phase 1 results (Jan 2021 – Sep 2026, out-of-sample)

| | CAGR | Max drawdown | Sharpe |
|---|---|---|---|
| Strategy, walk-forward tuned | +1.8% | −39.1% | 0.19 |
| Strategy, fixed defaults | +1.3% | −30.1% | 0.17 |
| Hold BTC | +20.3% | −76.6% | 0.61 |
| Hold top-10 equal weight | +6.0% | −89.4% | 0.48 |

The strategy halved crash losses but gave up most of the upside. Full report:
[`reports/phase1-report.md`](reports/phase1-report.md).

### Follow-up: BTC + ETH only (pre-registered)

Rules were written down and committed **before** the run
([`docs/specs/2026-10-05-btc-eth-preregistration.md`](docs/specs/2026-10-05-btc-eth-preregistration.md)).
Verdict: **NO-GO**. The fixed rules made **+2.9% a year** (max drawdown −25%, Sharpe 0.28), against
+20.3% for holding BTC. It cut the 2022 crash from −64% to −15%, but missed most of the 2023–24 rally.
Full report: [`reports/btc-eth-report.md`](reports/btc-eth-report.md).

### Follow-up: BTC + gold core, holding rules and CPU ML (pre-registered)

Rules fixed before the runs in
[`docs/specs/2026-10-06-core-and-ml-preregistration.md`](docs/specs/2026-10-06-core-and-ml-preregistration.md).
Period Sep 2020 – Sep 2026, so hold BTC made +37.7% a year here (max drawdown −77%, Sharpe 0.85).

- **BTC + gold (PAXG) 50/50, rebalanced quarterly: NO-GO, but closest yet.** +35.4% a year, Sharpe 1.11
  (better than holding BTC), yet its max drawdown of −49.5% broke the pre-set −40% limit. Band
  rebalancing (40–60%): +31.3%, Sharpe 1.02, drawdown −50.3%. Gold's +110% run flatters both.
  Report: [`reports/core-report.md`](reports/core-report.md).
- **Holding rules (informational):** on the owner's $3,000 plan, holding longer mattered most; selling half
  at +30% cut the share of losing windows but gave up upside; staged exits did not help and staged entry was
  slightly worse (more losing windows).
- **Gradient-boosting model on BTC, CPU only: NO-GO.** +0.5% a year (Sharpe 0.25) against +43.8% for
  holding BTC over 2020–2026; its 7-day direction calls were right 50.2% of the time, a coin flip.
  Report: [`reports/ml-report.md`](reports/ml-report.md).

### Follow-up: five more ideas and a Testnet bot (pre-registered)

Rules in [`docs/specs/2026-10-06-ideas-preregistration.md`](docs/specs/2026-10-06-ideas-preregistration.md);
gold history before PAXG (2017–2020) comes from COMEX futures. Report with audit:
[`reports/ideas-report.md`](reports/ideas-report.md).

- **BTC + gold through the 2018 crash: NO-GO** for 30/70, 40/60 and 50/50 (drawdowns −43% to −59%).
- **Crash brake** (half BTC above its 200-day average, otherwise all gold): **nominal GO, in practice a tie.**
  2019–2026: +34.7% a year, drawdown −35%, Sharpe 1.21 vs 0.96 for holding BTC, but its Sharpe ties the
  simple 50/50 mix (1.2062 vs 1.2059) and flips with the start date, costs, check weekday or a one-day
  delay; it grows about 8 points a year slower than 50/50. Two independent audits (Fable, Opus) agree.
- **Volatility scaling, plain and AI-forecast: NO-GO.** The AI forecast of volatility was less accurate
  than plain 30-day volatility.
- **Monthly contributions** lowered the worst case in % terms but also the median gain (informational).
- **`bot/testnet.py`**: rebalances the crash-brake strategy on the Binance Spot **Testnet** (fake money),
  dry run by default, tracks only its own positions.

### Follow-up: BTC + cash, ensemble trend basket, funding-rate overlay (pre-registered)

- **BTC + cash** (30/70, 50/50, 70/30, quarterly), verdict on 2017–2020: **NO-GO** on drawdown (−43% to
  −70%), though every mix beat holding BTC on Sharpe. [`reports/cash-report.md`](reports/cash-report.md)
- **Ensemble trend basket** (9 breakout lookbacks, top-10 coins, volatility sizing; from Zarattini et al.),
  hold-out 2022–2026: **NO-GO**. +4.5% a year with only −11.9% drawdown and Sharpe 0.62 (hold BTC +13.3%,
  −67%, 0.50), but it is ~90% cash on average, so the return is too low.
- **Funding-rate overlay** (halve exposure when futures funding is extreme; signal only): helped in
  2020–21, did nothing in the hold-out: **dropped**. [`reports/ensemble-report.md`](reports/ensemble-report.md)

### Follow-up: spot grid bot (pre-registered)

Rules in [`docs/specs/2026-10-06-grid-preregistration.md`](docs/specs/2026-10-06-grid-preregistration.md),
hourly candles 2021–2026. Report: [`reports/grid-report.md`](reports/grid-report.md).

- **NO-GO on every criterion.** Relaunched monthly, the main BTC grid lost **−11.9% a year** (drawdown −70%)
  while holding BTC made +20%. The median 30-day grid made +2.4%, but gains are capped (average +3.8% when
  up) while losses are not (average −9.2% when down): a grid sells volatility.
- Of 2,094 daily launches on BTC and ETH, **none** made the +14% in 5 days shown on the Binance marketplace;
  the best was +5.5% (BTC) and +8.1% (ETH). Those listings are the luckiest of many bots, often on meme coins.

## Biases caught along the way

| Problem | Effect if ignored | Fix |
|---|---|---|
| **Survivorship bias**: testing on coins that exist today | Inflated returns (+33% → +1.8%) | Point-in-time universe including delisted coins |
| **Redenominations and reused tickers** (e.g. old LUNA vs LUNA 2.0, ×1000 price jumps) | Fake ×1000 returns | Series breaks: positions sold, history reset |
| **Delisting detected with future knowledge** | Subtle look-ahead | Delisting inferred only after a real data gap |
| **Optimistic stop fills** in flash crashes (10 Oct 2025: lows 12–57% below stops) | Understated losses | Fills slip towards the day's low, plus worst-case sensitivity |
| **Stablecoins in the universe** (RLUSD) | Capital parked in a dollar peg | Exclusion list plus minimum-volatility filter |
| **Brake deadlock**: a pause that could never end while in cash | Strategy stuck in cash for years | Pause ends after 30 days |
| **Overfitting** | Lucky parameters look like skill | Walk-forward, deflated Sharpe, PBO |

An independent audit of the engine is in [`reports/phase1-audit.md`](reports/phase1-audit.md).

## Project layout

```
bot/         Binance Spot Testnet rebalancer (fake money)
botcore/     strategy, risk and cost logic (pure functions, reusable by a live bot)
research/    data download, universe, backtester, validation, tuning, report
tests/       123 tests (pytest)
docs/        design spec, implementation plan, pre-registrations
reports/     generated reports and charts
```

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt

pytest -q                          # 123 tests

python -m research.run_phase1 --trials 60          # full study: downloads data, writes reports/phase1-report.md
python -m research.run_phase1 --skip-download --symbols BTCUSDT,ETHUSDT --max-single 0.5 \
       --primary untuned --report btc-eth --title "BTC + ETH Pre-registered Experiment"
python -m research.run_core                        # BTC + gold core and holding rules
python -m research.run_ml                          # CPU machine-learning test
python -m research.run_ideas                       # ideas 1-5 (needs data/gold_gc_yahoo.json)
python -m research.run_grid                        # spot grid bot study (hourly data)
python -m bot.testnet                              # Testnet rebalancer, dry run (add --live with Testnet keys)
```

The first run downloads about 35 MB of data from `data.binance.vision`. The full study takes about
30 minutes on a laptop.

## Tech

Python 3.12 · pandas · NumPy · SciPy · scikit-learn · Optuna · Matplotlib · pytest

## Disclaimer

Research code. Nothing here is financial advice, and no strategy in this repository is cleared for real
money.
