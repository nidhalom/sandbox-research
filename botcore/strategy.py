"""Pure strategy logic shared by the backtester (phase 1) and the live bot (phase 2)."""
import numpy as np
import pandas as pd

from botcore.params import Params


def trend_scores(close: pd.DataFrame, windows) -> pd.DataFrame:
    """Average of sign(close - SMA(n)) over the windows, long-only (clipped at 0)."""
    s = sum(np.sign(close - close.rolling(n, min_periods=n).mean()) for n in windows) / len(windows)
    return s.clip(lower=0).fillna(0)


def raw_weights(close: pd.DataFrame, scores: pd.DataFrame, vol_window: int) -> pd.DataFrame:
    rets = close / close.shift(1) - 1
    vol = rets.rolling(vol_window, min_periods=vol_window).std() * np.sqrt(365)
    w = scores / vol
    return w.replace([np.inf, -np.inf], np.nan).fillna(0)


def scale_to_target(raw: pd.Series, cov: pd.DataFrame, p: Params) -> pd.Series:
    raw = raw[raw > 0]
    if raw.empty:
        return raw
    c = cov.reindex(index=raw.index, columns=raw.index).fillna(0).values * 365
    port_vol = float(np.sqrt(max(raw.values @ c @ raw.values, 0.0)))
    if port_vol == 0:
        return raw * 0.0
    w = (raw * (p.vol_target / port_vol)).clip(upper=p.max_single)
    gross = w.sum()
    return w * (p.max_gross / gross) if gross > p.max_gross else w


def compute_raw(close: pd.DataFrame, p: Params) -> pd.DataFrame:
    return raw_weights(close, trend_scores(close, p.windows), p.vol_window)


def weights_for_day(raw_row: pd.Series, eligible_row: pd.Series, returns_window: pd.DataFrame,
                    p: Params) -> pd.Series:
    """Target weights for the next open, from data up to the last close."""
    raw = raw_row.where(eligible_row.reindex(raw_row.index, fill_value=False).astype(bool), 0.0)
    cols = raw[raw > 0].index
    cov = returns_window[cols].cov(min_periods=p.cov_window // 2)
    return scale_to_target(raw[cols], cov, p)
