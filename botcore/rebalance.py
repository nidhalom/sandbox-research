"""Turn target weights into exchange orders (pure: no network)."""
import math

QUOTE = "USDT"
BUY_BUFFER = 0.995  # keep a little cash for fees and price moves between sells and buys


def plan_orders(holdings: dict, prices: dict, targets: dict, cash: float, band: float = 0.05,
                min_notional: float = 5.0, steps: dict | None = None) -> list[dict]:
    """Market orders (by quote amount) that move holdings to `targets`; sells first, then buys.

    Nothing is traded unless some weight is more than `band` from its target. Orders smaller than
    `min_notional` are skipped; buys are scaled down to the cash available after the sells. A full
    exit (target 0) sells the held quantity rounded down to the lot step, never more than is owned.
    """
    steps = steps or {}
    values = {a: holdings.get(a, 0.0) * prices[a] for a in targets}
    total = cash + sum(values.values())
    if total <= 0:
        return []
    if all(abs(values[a] / total - targets[a]) <= band for a in targets):
        return []
    diff = {a: targets[a] * total - values[a] for a in targets}
    sells = []
    for a, d in diff.items():
        if d >= 0 or -d < min_notional:
            continue
        if targets[a] == 0 and a in steps:
            qty = math.floor(holdings[a] / steps[a] + 1e-9) * steps[a]
            sells.append({"symbol": a + QUOTE, "side": "SELL", "quantity": qty, "quote_qty": round(qty * prices[a], 2)})
        else:
            sells.append({"symbol": a + QUOTE, "side": "SELL", "quote_qty": round(-d, 2)})
    wanted = {a: d for a, d in diff.items() if d >= min_notional}
    budget = (cash + sum(o["quote_qty"] for o in sells)) * BUY_BUFFER
    scale = min(1.0, budget / sum(wanted.values())) if wanted else 0.0
    buys = [{"symbol": a + QUOTE, "side": "BUY", "quote_qty": round(d * scale, 2)}
            for a, d in wanted.items() if d * scale >= min_notional]
    return sells + buys
