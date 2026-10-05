from dataclasses import dataclass

import numpy as np
import pandas as pd

from botcore.params import Params


@dataclass(frozen=True)
class BrakeState:
    peak: float
    mode: str = "normal"  # normal | half | paused | stopped
    paused_days: int = 0


def update_brakes(state: BrakeState, equity: float, p: Params) -> BrakeState:
    peak = max(state.peak, equity)
    if state.mode == "stopped":
        return BrakeState(peak, "stopped")
    if state.mode == "paused" and state.paused_days >= p.pause_max_days:
        return BrakeState(equity, "normal")
    dd = equity / peak - 1
    if dd <= p.brake_stop:
        mode = "stopped"
    elif dd <= p.brake_pause or (state.mode == "paused" and dd <= p.resume_level):
        mode = "paused"
    elif dd <= p.brake_half:
        mode = "half"
    else:
        mode = "normal"
    return BrakeState(peak, mode, state.paused_days + 1 if mode == "paused" and state.mode == "paused" else 0)


def atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, window: int) -> pd.DataFrame:
    prev = close.shift(1)
    tr = np.fmax(np.fmax((high - low).values, (high - prev).abs().values), (low - prev).abs().values)
    return pd.DataFrame(tr, index=close.index, columns=close.columns).rolling(window, min_periods=window).mean()
