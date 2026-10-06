"""Spot portfolio simulator: deposits, rebalancing and sells at daily closes."""
import pandas as pd

COST = 0.0015  # 0.10% fee + 0.05% half-spread per traded dollar


def _quarter_start(prev: pd.Timestamp, day: pd.Timestamp) -> bool:
    return day.month in (1, 4, 7, 10) and day.month != prev.month


def simulate(prices: pd.DataFrame, deposits: dict, weights: dict, rule: str = "none",
             band: float = 0.10, sells: dict | None = None, cost: float = COST,
             targets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily holdings `value` and cumulative `cash_out` from sales, starting at the first deposit.

    deposits: {date: dollars} bought at that close in `weights`. sells: {date: fraction of current
    holdings} sold at that close. rule: 'none', 'quarterly' (first trading day of Jan/Apr/Jul/Oct)
    or 'band' (any weight more than `band` from target, checked at each close).
    'dynamic' takes daily target weights from `targets` (columns = assets) and trades to them on
    Mondays and quarter starts when any weight is more than `band` away; deposits buy the day's targets.
    """
    if rule not in ("none", "quarterly", "band", "dynamic"):
        raise ValueError(f"unknown rule {rule!r}")
    if rule == "dynamic" and targets is None:
        raise ValueError("rule 'dynamic' needs targets")
    sells = sells or {}
    assets = list(weights)
    units = dict.fromkeys(assets, 0.0)
    cash_out, rows, prev = 0.0, [], None
    for day, p in prices.loc[min(deposits):, assets].iterrows():
        value = sum(units[a] * p[a] for a in assets)
        tw = targets.loc[day, assets].to_dict() if rule == "dynamic" else weights
        if prev is not None and value > 0 and rule != "none":
            w_now = {a: units[a] * p[a] / value for a in assets}
            drift = any(abs(w_now[a] - tw[a]) > band for a in assets)
            if rule == "quarterly":
                due = _quarter_start(prev, day)
            elif rule == "band":
                due = drift
            else:
                due = drift and (day.weekday() == 0 or _quarter_start(prev, day))
            if due:
                value -= sum(abs(w_now[a] - tw[a]) for a in assets) * value * cost
                units = {a: value * tw[a] / p[a] for a in assets}
        if day in deposits:
            for a in assets:
                units[a] += deposits[day] * tw[a] * (1 - cost) / p[a]
        if day in sells:
            f = sells[day]
            cash_out += f * sum(units[a] * p[a] for a in assets) * (1 - cost)
            units = {a: u * (1 - f) for a, u in units.items()}
        rows.append((day, sum(units[a] * p[a] for a in assets), cash_out))
        prev = day
    return pd.DataFrame(rows, columns=["date", "value", "cash_out"]).set_index("date")
