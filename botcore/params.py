from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    # signal
    windows: tuple[int, int, int] = (20, 50, 100)
    vol_window: int = 30
    cov_window: int = 60
    # sizing
    vol_target: float = 0.20
    max_gross: float = 1.0
    max_single: float = 0.30
    band: float = 0.02
    # stops
    atr_window: int = 14
    atr_mult: float = 3.0
    stop_cooldown_days: int = 5
    stop_fill: float = 0.5  # fill this fraction of the way from the stop to the day's low
    # drawdown brakes
    brake_half: float = -0.20
    brake_pause: float = -0.30
    brake_stop: float = -0.35
    resume_level: float = -0.25
    pause_max_days: int = 30  # a pause in cash can never recover on its own; end it after this
    stop_resume_days: int = 30  # backtest stand-in for the owner's manual /resume
    # universe
    universe_size: int = 10
    min_history_days: int = 180
    volume_window: int = 30
    min_vol: float = 0.10  # annualised; filters stablecoins and pegged tokens
    max_gap_days: int = 3  # longer gap = delisting / new series
    break_ratio: float = 20.0  # one-step price jump beyond this = redenomination / reused symbol
    # costs
    fee_rate: float = 0.001
    half_spread: float = 0.0005
    impact_coef: float = 0.1
    delist_haircut: float = 0.10
    # optional Fear & Greed filter (None = off)
    greed_threshold: float | None = None
    greed_scale: float = 0.5
