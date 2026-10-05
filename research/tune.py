from dataclasses import dataclass, replace

import optuna
import pandas as pd

from botcore.metrics import sharpe
from botcore.params import Params
from research.backtest import Market, run_backtest

optuna.logging.set_verbosity(optuna.logging.WARNING)


def suggest(trial, base: Params) -> Params:
    return replace(
        base,
        windows=(trial.suggest_int("w_fast", 10, 30), trial.suggest_int("w_mid", 40, 80),
                 trial.suggest_int("w_slow", 90, 200)),
        atr_mult=trial.suggest_float("atr_mult", 2.0, 5.0),
        band=trial.suggest_float("band", 0.01, 0.05),
    )


def tune(m: Market, base: Params, train_start, train_end, n_trials: int, seed: int = 0,
         log: list | None = None) -> Params:
    def objective(trial):
        p = suggest(trial, base)
        r = run_backtest(m, p, train_start, train_end).returns
        if log is not None:
            log.append((p, r))
        return sharpe(r)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials)
    return suggest(optuna.trial.FixedTrial(study.best_params), base)


@dataclass
class WalkForward:
    returns: pd.Series
    chosen: dict
    trials: list
    trades: int = 0
    costs: float = 0.0


def walk_forward(m: Market, base: Params, first_test_year: int, last_test_year: int, train_start,
                 n_trials: int) -> WalkForward:
    """Tune on everything before each test year, trade that year with the winner, roll forward."""
    pieces, chosen, trials, trades, costs = [], {}, [], 0, 0.0
    for year in range(first_test_year, last_test_year + 1):
        log: list = []
        best = tune(m, base, train_start, f"{year - 1}-12-31", n_trials, seed=year, log=log)
        chosen[year] = best
        trials.append(log)
        res = run_backtest(m, best, f"{year}-01-01", f"{year}-12-31")
        pieces.append(res.returns)
        trades += res.trades
        costs += res.costs
    return WalkForward(pd.concat(pieces), chosen, trials, trades, costs)
