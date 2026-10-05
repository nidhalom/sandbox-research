from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

EULER = 0.5772156649


def _paths(x: np.ndarray, n: int, block: int, seed: int) -> np.ndarray:
    """Stationary bootstrap (Politis-Romano): resampled paths, shape (n, T)."""
    rng = np.random.default_rng(seed)
    T = len(x)
    restart = rng.random((n, T)) < 1 / block
    restart[:, 0] = True
    pos = np.arange(T)
    last = np.maximum.accumulate(np.where(restart, pos, 0), axis=1)
    starts = rng.integers(T, size=(n, T))
    idx = (np.take_along_axis(starts, last, axis=1) + (pos - last)) % T
    return x[idx]


def bootstrap_ci(r: pd.Series, n: int = 2000, block: int = 20, seed: int = 0) -> dict:
    x = r.dropna().values
    paths = _paths(x, n, block, seed)
    T = paths.shape[1]
    eq = np.cumprod(1 + paths, axis=1)
    stats = {
        "cagr": eq[:, -1] ** (365 / T) - 1,
        "sharpe": paths.mean(axis=1) / paths.std(axis=1, ddof=1) * np.sqrt(365),
        "max_dd": (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1),
    }
    return {k: (float(np.percentile(v, 5)), float(np.percentile(v, 95))) for k, v in stats.items()}


def daily_sr(r: pd.Series) -> float:
    x = r.dropna()
    s = x.std()
    return 0.0 if len(x) < 2 or s == 0 else float(x.mean() / s)


def deflated_sharpe(r: pd.Series, trial_daily_srs: list[float]) -> float:
    """Bailey & Lopez de Prado (2014): probability the true Sharpe exceeds the best expected by luck."""
    x = r.dropna().values
    T = len(x)
    sr = daily_sr(r)
    n_trials = len(trial_daily_srs)
    if n_trials > 1:
        sd = np.std(trial_daily_srs, ddof=1)
        sr0 = sd * ((1 - EULER) * norm.ppf(1 - 1 / n_trials) + EULER * norm.ppf(1 - 1 / (n_trials * np.e)))
    else:
        sr0 = 0.0
    g3, g4 = skew(x), kurtosis(x, fisher=False)
    denom = np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr**2, 1e-12))
    return float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))


def _col_sr(X: np.ndarray) -> np.ndarray:
    s = X.std(axis=0, ddof=1)
    return np.divide(X.mean(axis=0), s, out=np.zeros(X.shape[1]), where=s > 0)


def pbo(trial_returns: pd.DataFrame, S: int = 16) -> float:
    """Probability of Backtest Overfitting via combinatorially symmetric cross-validation."""
    X = trial_returns.dropna().values
    N = X.shape[1]
    blocks = np.array_split(np.arange(len(X)), S)
    logits = []
    for chosen in combinations(range(S), S // 2):
        ins = np.concatenate([blocks[b] for b in chosen])
        oos = np.concatenate([blocks[b] for b in range(S) if b not in chosen])
        sr_oos = _col_sr(X[oos])
        best = int(np.argmax(_col_sr(X[ins])))
        omega = ((sr_oos < sr_oos[best]).sum() + 1) / (N + 1)
        logits.append(np.log(omega / (1 - omega)))
    return float(np.mean(np.array(logits) <= 0))
