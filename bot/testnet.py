"""Binance Spot **Testnet** rebalancer for the crash-brake strategy (idea 5). Fake money only.

Usage:
    python -m bot.testnet            # dry run: prints the plan, sends nothing
    python -m bot.testnet --live     # sends MARKET orders to the Testnet (keys from .env)

Run it once a week (Monday). Keys: create them at https://testnet.binance.vision and put
BINANCE_TESTNET_KEY=... and BINANCE_TESTNET_SECRET=... in .env (gitignored). Never use real keys.
"""
import argparse
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from botcore.rebalance import plan_orders

BASE = "https://testnet.binance.vision"
SIGNAL_URL = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=202"
ASSETS = ("BTC", "PAXG")
BASE_W = 0.5
STATE = Path("bot/state.json")  # the strategy's own cash and coins (gitignored)


def sign(query: str, secret: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def load_env(path=".env") -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def signal_weights(closes: pd.Series) -> dict:
    """Crash brake on closed daily candles: half BTC above the 200-day average, otherwise all gold."""
    if len(closes) < 200:
        raise ValueError("need at least 200 closed daily candles")
    btc = BASE_W if closes.iloc[-1] >= closes.iloc[-200:].mean() else 0.0
    return {"BTC": btc, "PAXG": 1.0 - btc}


def load_state(path=STATE, budget: float = 3000.0) -> dict:
    """What the strategy owns. Testnet accounts start with free coins, so the wallet is not the strategy."""
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return {"cash": budget, **dict.fromkeys(ASSETS, 0.0)}


def save_state(path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2))


def apply_fill(state: dict, symbol: str, side: str, resp: dict) -> dict:
    asset, qty, quote = symbol.removesuffix("USDT"), float(resp["executedQty"]), float(resp["cummulativeQuoteQty"])
    sign_ = 1 if side == "BUY" else -1
    return {**state, asset: state[asset] + sign_ * qty, "cash": state["cash"] - sign_ * quote}


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def btc_daily_closes() -> pd.Series:
    rows = _get_json(SIGNAL_URL)
    now_ms = time.time() * 1000
    return pd.Series([float(k[4]) for k in rows if k[6] < now_ms])  # closed candles only


class Testnet:
    __test__ = False  # not a pytest test class
    def __init__(self, key: str, secret: str, base: str = BASE):
        if base != BASE:
            raise ValueError(f"refusing non-Testnet URL {base!r}")
        self.base, self._key, self._secret = base, key, secret

    def __repr__(self):
        return "Testnet(base=%r, key=***, secret=***)" % self.base

    def _call(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = dict(params or {})
        headers = {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            q = urllib.parse.urlencode(params)
            params_q = q + "&signature=" + sign(q, self._secret)
            headers["X-MBX-APIKEY"] = self._key
        else:
            params_q = urllib.parse.urlencode(params)
        url = f"{self.base}{path}" + (f"?{params_q}" if method == "GET" and params_q else "")
        data = params_q.encode() if method == "POST" else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def prices(self) -> dict:
        return {a: float(self._call("GET", "/api/v3/ticker/price", {"symbol": a + "USDT"})["price"]) for a in ASSETS}

    def balances(self) -> dict:
        acct = self._call("GET", "/api/v3/account", signed=True)
        return {b["asset"]: float(b["free"]) for b in acct["balances"]}

    def market_order(self, symbol: str, side: str, quote_qty: float) -> dict:
        return self._call("POST", "/api/v3/order", {"symbol": symbol, "side": side, "type": "MARKET",
                                                    "quoteOrderQty": f"{quote_qty:.2f}"}, signed=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="send orders to the Testnet")
    ap.add_argument("--budget", type=float, default=3000.0, help="USDT the strategy manages")
    args = ap.parse_args(argv)
    env = load_env()
    key, secret = env.get("BINANCE_TESTNET_KEY"), env.get("BINANCE_TESTNET_SECRET")
    targets = signal_weights(btc_daily_closes())
    client = Testnet(key or "", secret or "")
    prices = client.prices()
    if args.live and not (key and secret):
        raise SystemExit("--live needs BINANCE_TESTNET_KEY and BINANCE_TESTNET_SECRET in .env")
    state = load_state(STATE, args.budget)
    holdings, cash = {a: state[a] for a in ASSETS}, state["cash"]
    value = cash + sum(holdings[a] * prices[a] for a in ASSETS)
    print(f"Strategy holds {holdings} + {cash:.2f} USDT = {value:.2f} USDT (from {STATE})")
    print("Target weights:", targets, "| prices:", prices)
    orders = plan_orders(holdings, prices, targets, cash)
    if not orders:
        print("Inside the 5-point band: nothing to do.")
    for o in orders:
        print(("SENDING " if args.live else "DRY RUN ") + f"{o['side']} {o['symbol']} for {o['quote_qty']:.2f} USDT")
        if args.live:
            r = client.market_order(o["symbol"], o["side"], o["quote_qty"])
            print("  ->", r.get("status"), "filled", r.get("executedQty"), "for", r.get("cummulativeQuoteQty"))
            state = apply_fill(state, o["symbol"], o["side"], r)
            save_state(STATE, state)  # after every fill, so a failed later order loses nothing


if __name__ == "__main__":
    main()
