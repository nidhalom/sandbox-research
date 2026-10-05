import numpy as np
import pandas as pd

from botcore.metrics import sharpe
from research.validation import bootstrap_ci, daily_sr, deflated_sharpe, pbo

IDX = pd.date_range("2019-01-01", periods=1500)


def test_bootstrap_ci_brackets_point_estimate():
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 1500), index=IDX)
    ci = bootstrap_ci(r, n=500)
    assert ci["sharpe"][0] < sharpe(r) < ci["sharpe"][1]
    assert ci["max_dd"][0] <= ci["max_dd"][1] <= 0


def test_deflated_sharpe_high_for_single_strong_strategy():
    r = pd.Series(np.random.default_rng(1).normal(0.003, 0.02, 1500), index=IDX)
    assert deflated_sharpe(r, [daily_sr(r)]) > 0.95


def test_deflated_sharpe_penalises_many_trials():
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.0008, 0.02, 1500), index=IDX)
    few = deflated_sharpe(r, list(rng.normal(0.0, 0.01, 2)))
    many = deflated_sharpe(r, list(rng.normal(0.0, 0.03, 500)))
    assert many < few


def test_pbo_about_half_for_pure_noise():
    M = pd.DataFrame(np.random.default_rng(3).normal(0, 0.01, (1600, 30)))
    assert 0.3 < pbo(M, S=8) < 0.7


def test_pbo_zero_when_one_trial_truly_dominates():
    M = pd.DataFrame(np.random.default_rng(4).normal(0, 0.01, (1600, 30)))
    M[0] += 0.01
    assert pbo(M, S=8) == 0.0
