# SDD ledger — plan: D:\sandbox\docs\plans\2026-10-05-phase1-research-engine.md
Setup: Ruling: owner allowed local commits (2026-10-05); repo D:\sandbox on main, no remote, no worktree (fresh personal repo, nothing to isolate from) — cost if wrong: none, never push
Setup: Ruling: added tests/__init__.py — tests import helpers via tests.conftest — cost if wrong: none
Setup: Ruling: .gitignore excludes archive/ (holds old .env secrets and nested .git repos) and data/ — cost if wrong: archive not versioned (it is reference only)
Pre-flight: T3 eligible_mask -> T6 build_market (bool frame): OK
Pre-flight: T4 compute_raw/weights_for_day -> T6 run_backtest: OK
Pre-flight: T5 BrakeState/update_brakes/atr/trade_cost -> T6: OK
Pre-flight: T6 Market/run_backtest -> T8 tune/walk_forward: OK
Pre-flight: T7 validation + T8 WalkForward -> T9 run_phase1: OK
Task 1: complete (tests: pytest tests/test_metrics.py -> 6 passed)
Task 2: complete (tests: pytest tests/test_data.py -> 5 passed)
Task 3: complete (tests: pytest tests/test_panel_universe.py -> 6 passed)
Task 4: complete (tests: pytest tests/test_strategy.py -> 7 passed)
Task 5: complete (tests: pytest tests/test_risk_costs.py -> 10 passed)
Task 6: complete (tests: pytest tests/test_backtest.py -> 8 passed)
Task 7: complete (tests: pytest tests/test_validation.py -> 5 passed)
Task 8: complete (tests: pytest tests/test_sentiment_tune.py -> 4 passed)
Task 9 (code): complete (tests: pytest -q -> 54 passed); real run pending full download
Task 9: Ruling: fixed downloader crash on non-ASCII symbols found in real run — test_download_symbol_quotes_non_ascii_symbol + test_download_all_survives_non_ascii_error RED->GREEN, suite 56/56 — cost if wrong: none
Task 10: Fable 5.1 audit written to reports/phase1-audit.md (1 Critical, 6 Important)
Final: fixed C1 stale report - report now records run details; replaced by full run output
Final: fixed I1 gaps/redenominations - test_price_jump_and_long_gap_are_breaks, test_break_resets_history_requirement, test_delisted_holding_is_liquidated_after_gap_with_haircut, test_redenomination_while_held_is_not_profit RED->GREEN, suite 64/64
Final: Ruling: delisting detection now causal (gap > 3 days) instead of last_valid_index (future knowledge) - removes look-ahead; cost if wrong: frozen positions for 3 days before sale
Final: fixed I2 stop fills - stop_fill=0.5 toward day's low + worst-case (fill at low) line in report - test_stop_fill_slips_toward_low_on_crash RED->GREEN
Final: fixed I3 stablecoins - RLUSD/USDE/BFUSD/FRAX/USDSB excluded + min_vol 10% filter - test_new_stablecoins_excluded, test_low_volatility_coin_not_eligible RED->GREEN
Final: fixed I4 caveat wording - report states it is not fully out-of-sample
Final: fixed I5 deflated Sharpe uses all folds' trials; PBO/DSR not computed under 20 trials - test_no_go_when_overfitting_stats_unavailable RED->GREEN
Final: fixed I6 run details + walk-forward trades/costs in report - test_walk_forward_reports_trades_and_costs RED->GREEN
Task 9: complete (full run: 756 symbols, 2021-2026, 60 trials/fold -> verdict NO-GO)
Final: finding (not fixed): pause brake deadlock - paused at -30% in cash can never recover above -25%, untuned run sat in cash 2023-2026; spec rule defect, needs owner decision
Follow-up (2026-10-05): pre-registration committed first; pause fix test_pause_ends_after_max_days_with_peak_reset + test_bot_trades_again_after_a_pause RED->GREEN, suite 66/66; BTC+ETH run -> NO-GO (untuned +2.9% CAGR, Sharpe 0.28, DD -25%; PBO 0.40); README drafted for owner review
Follow-up (2026-10-06): pre-registered core+ML experiments — A1 50/50 quarterly NO-GO (CAGR +35.4%, Sharpe 1.11, DD -49.5% > -40% limit), A2 band NO-GO (+31.3%, 1.02, -50.3%), hold BTC +37.7%/0.85/-76.6% (2020-09+); ML NO-GO (+0.5%, Sharpe 0.25, hit rate 50.2%); suite 86/86
Follow-up (2026-10-06): ideas 1-5 pre-registered — idea 1 BTC+gold 2017-2020 NO-GO (DD -43..-59%); idea 5 crash brake GO but fragile (Sharpe 1.2062 vs A1 1.2059, 1-day lag fails, SMA250 fails DD, brake into cash fails); 4/4b NO-GO (AI vol MAE 0.220 vs naive 0.190); Testnet bot added (dry run default, own-position state). Ruling: gold before 2020-09 from Yahoo GC=F via PowerShell (Git curl blocked by TLS inspection on this network; did not disable cert checks) — cost if wrong: futures-roll noise in 2017-2020 gold. Self-audit only (no subagent) — suite 103/103
Follow-up (2026-10-06 pm): grid bot pre-registered and run — NO-GO (BTC main monthly CAGR -11.9%, DD -69.8%; 0/2094 five-day launches reached +14%). Fable+Opus audits of ideas 1-5: all numbers reproduced, no look-ahead; idea 5 relabelled nominal GO / Sharpe tie with A1. Bot fixed per audits (fees, qty exits, idempotent orders, logs, day guard, clock sync, XAUT option). Ruling: kept idea 5 as the bot default (pre-registration says best GO strategy) and added --strategy fixed for A1 — cost if wrong: none, owner chooses. Ruling: grid test fixed in test after level float bug (110.00000000000001) — EPS tolerance. Suite 115/115
