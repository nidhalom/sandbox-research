import numpy as np
import pandas as pd

from botcore.params import Params

STABLES = {
    "USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "PAX", "USDS", "UST", "USTC", "USDD", "PYUSD",
    "EURI", "AEUR", "XUSD", "USD1", "SUSD", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "UAH", "NGN",
    "ZAR", "PLN", "RON", "ARS", "JPY", "MXN", "COP", "CZK", "BIDR", "IDRT", "BKRW",
    "RLUSD", "USDE", "BFUSD", "FRAX", "USDSB",
}
LEVERAGED_UNDERLYINGS = {
    "BTC", "ETH", "BNB", "XRP", "LINK", "ADA", "DOT", "TRX", "XTZ", "EOS", "LTC", "BCH",
    "FIL", "SXP", "YFI", "UNI", "AAVE", "SUSHI", "1INCH", "XLM",
}


def is_excluded(symbol: str) -> bool:
    base = symbol.removesuffix("USDT")
    if base in STABLES:
        return True
    for suffix in ("UP", "DOWN", "BULL", "BEAR"):
        if base.endswith(suffix) and base[: -len(suffix)] in LEVERAGED_UNDERLYINGS:
            return True
    return False


def _positions(close: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(np.repeat(np.arange(len(close))[:, None], close.shape[1], axis=1),
                        index=close.index, columns=close.columns)


def gap_days(close: pd.DataFrame) -> pd.DataFrame:
    """Consecutive days without a price up to each date (0 on trading days, NaN before listing)."""
    pos = _positions(close)
    return pos - pos.where(close.notna()).ffill()


def series_breaks(close: pd.DataFrame, p: Params) -> pd.DataFrame:
    """True where a price series restarts: after a gap longer than max_gap_days, or on a one-step
    price jump beyond break_ratio (redenomination or a reused ticker)."""
    valid = close.notna()
    pos = _positions(close)
    last_pos = pos.where(valid).ffill().shift(1)
    ratio = close / close.ffill().shift(1)
    jump = (ratio > p.break_ratio) | (ratio < 1 / p.break_ratio)
    return valid & last_pos.notna() & ((pos - last_pos - 1 > p.max_gap_days) | jump)


def history_since_break(close: pd.DataFrame, breaks: pd.DataFrame) -> pd.DataFrame:
    valid = close.notna().astype(int)
    segments = breaks.cumsum()
    return pd.DataFrame({c: valid[c].groupby(segments[c]).cumsum() for c in close.columns}, index=close.index)


def eligible_mask(panel: dict[str, pd.DataFrame], p: Params) -> pd.DataFrame:
    """True where a symbol is in the universe at that day's close (uses data up to that close only)."""
    close, qv = panel["close"], panel["quote_volume"]
    history = history_since_break(close, series_breaks(close, p))
    vol = (close / close.shift(1) - 1).rolling(p.vol_window, min_periods=p.vol_window).std() * np.sqrt(365)
    allowed = pd.Series({s: not is_excluded(s) for s in close.columns})
    ok = (history >= p.min_history_days) & close.notna() & allowed & (vol >= p.min_vol)
    adv = qv.rolling(p.volume_window, min_periods=p.volume_window // 2).mean().where(ok)
    return adv.rank(axis=1, ascending=False, method="first") <= p.universe_size
