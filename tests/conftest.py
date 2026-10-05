import numpy as np
import pandas as pd


def make_panel(n_days=400, symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT"),
               drift=(0.004, 0.0, -0.004), vol=0.02, seed=0, start="2020-01-01"):
    """Synthetic daily OHLCV panel in the same shape load_panel returns."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n_days, freq="D")
    close = pd.DataFrame(
        {s: 100 * np.exp(np.cumsum(d + vol * rng.standard_normal(n_days))) for s, d in zip(symbols, drift)},
        index=idx,
    )
    open_ = close.shift(1).fillna(close.iloc[0])
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    qv = pd.DataFrame(1e7, index=idx, columns=close.columns)
    return {"open": open_, "high": high, "low": low, "close": close, "quote_volume": qv}
