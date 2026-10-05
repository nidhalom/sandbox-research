import numpy as np

from botcore.params import Params

MISSING_VOLUME_IMPACT = 0.01  # assume 1% impact when volume is unknown


def trade_cost(notional: float, adv_quote: float, p: Params) -> float:
    """Fee + half-spread + square-root market impact, in quote currency."""
    if notional == 0:
        return 0.0
    if adv_quote and not np.isnan(adv_quote) and adv_quote > 0:
        impact = p.impact_coef * np.sqrt(notional / adv_quote)
    else:
        impact = MISSING_VOLUME_IMPACT
    return float(notional * (p.fee_rate + p.half_spread + impact))
