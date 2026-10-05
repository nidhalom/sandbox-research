# Design Spec — Crypto Trend Bot

**Date:** 2026-10-05 · **Status:** approved by owner 2026-10-05 · **Location:** `D:\sandbox`

## 1. Goal

Maximise profit over the next 6 months and beyond with an automated bot, while keeping the account's
worst drawdown (drop from its highest point) at or above **−35%**.

**Success means**: after fees, on data the strategy never saw, the bot earns clearly more than holding
cash, with better risk-adjusted returns than simply holding BTC or a basket of coins.

## 2. Hard rules

1. **Git: local commits only** in the personal `D:\sandbox` repo. **Never push**, never touch work repositories.
2. **No real money.** Development and live runs use Binance **Testnet** only. Moving to real money is a
   separate decision the owner makes after phase 2, on a venue chosen then (owner may trade through a
   US or UK company).
3. All project files live in `D:\sandbox`. Old projects are in `D:\sandbox\archive` (read-only reference).
4. Secrets only in `.env` (never in code, logs, or chat). Exchange keys: trading only, **withdrawals off**,
   IP-restricted when hosted.
5. **Shariah-aware trading**: live trading is spot only. No futures, no interest-bearing margin, no
   borrowing, no shorting. Leverage may appear in research reports for comparison only, never live.

## 3. Evidence behind the design

A throwaway probe (2020-06 → 2026-10, 10 Binance coins, daily candles, fees + slippage + funding counted)
gave:

| Strategy | CAGR | Max drawdown | Sharpe |
|---|---|---|---|
| Hold BTC | 41.5% | −77% | 0.89 |
| Hold 10-coin basket | 72% | −79% | 1.09 |
| Trend long/short | 17–28% | −85% to −95% | 0.70 |
| Trend long-only, portfolio vol target 15% | 26.8% | −29% | 1.25 |
| **Trend long-only, portfolio vol target 20%** | **35.2%** | **−36%** | **1.25** |
| Trend long-only, portfolio vol target 30% | 52.3% | −43% | 1.30 |

Conclusions used here:
- **Shorting lost money** → long-only.
- **Per-coin sizing did not control drawdown; portfolio-level volatility targeting did.**
- Return and drawdown trade off almost linearly; the owner chose the 20% volatility target (≈ −35%).

Known optimism in the probe: survivorship bias (coins picked from today's list), portfolio-level scaling
ignored its extra trading costs, futures prices used. **Phase 1 must remove these before any number is
trusted.** Expect real results to be lower.

## 4. Strategy (v1)

**Market**: spot crypto against USDT. No futures, no shorting, no leverage (gross exposure ≤ 100%),
permanently (hard rule 5). In the probe, removing leverage changed CAGR 35.2% → 32.9%, max drawdown
−35.6% → −29.0%, Sharpe 1.25 → 1.33, so the cap costs little.

**Universe**: at each rebalance, the top **N = 10** USDT spot pairs by trailing 30-day quote volume,
excluding stablecoins, leveraged tokens, and coins with < 180 days of history. Built **point-in-time**
from historical data, **including coins later delisted**. N shrinks automatically when capital is too
small for the exchange's minimum order size.

**Signal** (per coin, daily close): trend score = average of `sign(close − SMA(n))` for n ∈ {20, 50, 100},
clipped to ≥ 0. Score 0 = hold no position.

**Sizing**:
1. Raw weight per coin = score ÷ coin's 30-day annualised volatility.
2. Scale the whole book so the portfolio's estimated volatility (using the 60-day covariance matrix,
   so correlation between coins is counted) equals the **20% annual target**.
3. Cap gross exposure at 100% and any single coin at 30%.

**Rebalance**: once a day after the daily close. Skip trades smaller than a no-trade band (default 2% of
equity per coin) to save fees.

**Optional filter (researched in phase 1, kept only if it helps out-of-sample)**: Crypto Fear & Greed
Index. Extreme greed → scale exposure down; extreme fear → no forced selling.

## 5. Risk controls

| Layer | Rule (defaults; all backtested in phase 1) |
|---|---|
| Per position | Exchange-side stop order placed with every buy (stop at 3 × 14-day ATR below entry, trailed daily). Works even if the bot or network is down. |
| Drawdown brake 1 | Equity −20% from peak → target volatility halved |
| Drawdown brake 2 | −30% → no new buys, Telegram alert |
| Drawdown brake 3 | −35% → sell everything, bot stops until owner sends `/resume` |
| Resume after brake 2 | Automatically when drawdown recovers above −25% |
| Operational | Exchange unreachable > 15 min, or local and exchange balances disagree → stop trading, alert |
| Dead-man switch | External heartbeat (healthchecks.io); no ping for 2 h → alert |

## 6. Phases

Each phase gets its own implementation plan. Phase 2 starts only if phase 1's go criteria pass.

### Phase 1 — Research engine (offline)

- **Data**: Binance public archive (`data.binance.vision`): daily spot candles for all USDT pairs,
  including delisted ones, 2018 → today. Cached locally as Parquet. Fear & Greed history from alternative.me.
- **Backtester**: vectorised daily simulation. Costs: 0.10% fee per side (Binance spot standard rate),
  plus slippage estimated per coin from its traded volume. Orders execute at the next day's open; no
  look-ahead (all signals use data up to the previous close).
- **Tuning**: at most 6 parameters (SMA lengths, volatility target, stop distance, band, brake levels)
  searched with Optuna. **Every trial is logged.**
- **Validation**:
  - Walk-forward: tune on years 1…k, test on year k+1, roll forward.
  - Probability of Backtest Overfitting (CSCV method).
  - Deflated Sharpe ratio (adjusts for the number of trials).
  - Bootstrap confidence intervals for CAGR, Sharpe, and max drawdown.
  - Benchmarks: hold BTC, hold equal-weight basket of the same universe.
- **Deliverable**: `D:\sandbox\reports\phase1-report.md` with results, charts, and a plain go/no-go verdict.

**Go criteria** (all must pass, on out-of-sample periods only):
- Sharpe ≥ 1.0, and the lower bound of its 90% confidence interval ≥ 0.5
- Max drawdown no worse than −35%
- PBO < 0.3
- Sharpe higher than both benchmarks

If they fail, the report says so and recommends the next step instead of proceeding.

### Phase 2 — Live bot on Binance Testnet

**Components** (each a separate module with one job):

| Module | Job |
|---|---|
| `exchange` | Thin wrapper over ccxt. Swappable venue: Binance Testnet now, any spot exchange later. |
| `data` | Fetch latest candles; same code path as the backtester's signal input. |
| `strategy` | Pure functions: candles → target weights. **Shared with the backtester**, so live = tested logic. |
| `risk` | Applies brakes, caps, and stops to target weights. |
| `execution` | Turns weight changes into orders. Limit orders first, market fallback, idempotent client order IDs. |
| `state` | SQLite: positions, orders, equity history, brake status. Reconciles with the exchange on every start. |
| `telegram` | `/status`, `/pnl`, `/positions`, `/pause`, `/resume`, `/kill` (requires confirmation). Commands only from the owner's chat ID. Daily report and instant alerts. |
| `main` | Scheduler: daily rebalance after close, risk check every hour, heartbeat ping. |

**Error handling**: network/API errors retried with backoff; any error during order placement → stop,
reconcile, alert; never crash silently (top-level handler alerts, then exits so the supervisor restarts it).

**What Testnet proves**: the bot places and tracks orders correctly, survives restarts and network
failures, and brakes fire as designed. **It does not prove profitability**: Testnet order books and
prices are separate from the real market. Profit evidence comes from phase 1.

**Exit criteria**: 30 consecutive days on Testnet with no unhandled errors, no state mismatches, and every
Telegram command and brake exercised at least once (brakes forced in a test run).

### Phase 3 — Hosting

Docker image; cheap cloud VPS in a region the chosen exchange accepts (checked before choosing);
auto-restart on crash; logs rotated; secrets via environment file with restricted permissions.

## 7. Testing and audit

- `pytest`, tests written before the code (TDD), for every module.
- Backtester correctness tests: known-answer cases, no look-ahead (shifting future data must not change
  past signals), fees charged on every trade.
- **Independent audit by Fable 5.1** at the end of phase 1 (look-ahead, leakage, survivorship, cost
  errors, overfitting) and at the end of phase 2 (code and failure handling).

## 8. Project layout

```
D:\sandbox\
├── archive\              old projects (reference only)
├── docs\specs\           this spec
├── docs\plans\           implementation plans
├── botcore\              shared code: strategy, risk, costs
├── research\             phase 1: data download, backtester, tuning, validation
├── live\                 phase 2: exchange, execution, state, telegram, main
├── reports\              phase 1 report
├── tests\
├── .env.example
└── requirements.txt
```

Python 3.12. Main libraries: pandas, numpy, pyarrow, optuna, ccxt, python-telegram-bot, pytest.

## 9. Out of scope (v1)

Futures, shorting, funding-rate carry, leverage, high-frequency trading, social-media sentiment from
paid APIs, machine-learning price prediction.

## 10. Open items

- **Capital size** for real trading is unknown; it decides N and minimum-order handling. Testnet uses
  the Testnet balance.
- **Real-money venue** is decided by the owner later (depends on company jurisdiction). The `exchange`
  module keeps this swappable.
