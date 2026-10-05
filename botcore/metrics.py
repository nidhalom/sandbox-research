import numpy as np
import pandas as pd

DAYS = 365


def equity_curve(r: pd.Series) -> pd.Series:
    return (1 + r.fillna(0)).cumprod()


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return 0.0
    return float((1 + r).prod() ** (DAYS / len(r)) - 1)


def max_drawdown(r: pd.Series) -> float:
    eq = equity_curve(r)
    return float((eq / eq.cummax() - 1).min())


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    s = r.std()
    if len(r) < 2 or s == 0 or np.isnan(s):
        return 0.0
    return float(r.mean() / s * np.sqrt(DAYS))


def yearly_returns(r: pd.Series) -> pd.Series:
    r = r.dropna()
    return (1 + r).groupby(r.index.year).prod() - 1


def summary(r: pd.Series) -> dict:
    return {"cagr": cagr(r), "max_dd": max_drawdown(r), "sharpe": sharpe(r)}
