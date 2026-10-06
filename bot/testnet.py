"""Binance Spot **Testnet** rebalancer (fake money only).

Strategies: `brake` (idea 5: half BTC while BTC is above its 200-day average, otherwise all gold) or
`fixed` (A1: 50/50 BTC + gold). Gold token: PAXG or XAUT.

Usage (from anywhere):
    python -m bot.testnet                     # dry run: prints the plan, sends nothing
    python -m bot.testnet --live              # sends MARKET orders to the Testnet (keys from .env)

Run it on **Tuesday shortly after 00:00 UTC**, right after Monday's daily candle
closes, and on the day after each quarter starts: that matches the backtest. `--live` refuses other
days unless `--force`. Keys: create them at https://testnet.binance.vision, put BINANCE_TESTNET_KEY=...
and BINANCE_TESTNET_SECRET=... in .env (gitignored). Never use real Binance keys.
"""
import argparse
import csv
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from botcore.rebalance import plan_orders

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://testnet.binance.vision"
SIGNAL_URL = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=202"
BASE_W = 0.5
STATE = ROOT / "bot" / "state.json"   # default state path (tests); real runs use paths_for()
STEPS = {"BTC": 0.00001, "PAXG": 0.0001, "XAUT": 0.0001}


def sign(query: str, secret: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def load_env(path=ROOT / ".env") -> dict:
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


def paths_for(strategy: str, gold: str) -> dict:
    """Each strategy keeps its own state and logs (all gitignored), so several can run side by side."""
    tag = f"{strategy}-{gold}"
    return {"state": ROOT / "bot" / f"state-{tag}.json", "fills": ROOT / "bot" / f"fills-{tag}.csv",
            "runs": ROOT / "bot" / f"runs-{tag}.csv"}


def signal_weights(closes: pd.Series, gold: str = "PAXG", strategy: str = "brake") -> dict:
    """Target weights from closed daily candles. gold="CASH": the non-BTC part stays in USDT."""
    if strategy == "fixed":
        btc = BASE_W
    else:
        if len(closes) < 200:
            raise ValueError("need at least 200 closed daily candles")
        btc = BASE_W if closes.iloc[-1] >= closes.iloc[-200:].mean() else 0.0
    return {"BTC": btc} if gold == "CASH" else {"BTC": btc, gold: 1.0 - btc}


def trading_day_ok(last_closed: pd.Timestamp) -> bool:
    """The backtest trades on Monday closes and on the first day of each quarter."""
    return last_closed.weekday() == 0 or (last_closed.month in (1, 4, 7, 10) and last_closed.day == 1)


def load_state(path=STATE, budget: float = 3000.0, assets=("BTC", "PAXG")) -> dict:
    """What the strategy owns. Testnet accounts start with free coins, so the wallet is not the strategy."""
    p = Path(path)
    state = json.loads(p.read_text()) if p.exists() else {"cash": budget}
    return {"cash": state["cash"], **{a: state.get(a, 0.0) for a in assets},
            **{k: v for k, v in state.items() if k not in ("cash", *assets)}}


def save_state(path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2))


def apply_fill(state: dict, symbol: str, side: str, resp: dict) -> dict:
    """Update the strategy's holdings from an order response, net of the fees actually charged."""
    asset, qty, quote = symbol.removesuffix("USDT"), float(resp["executedQty"]), float(resp["cummulativeQuoteQty"])
    fee_asset = sum(float(f["commission"]) for f in resp.get("fills", []) if f["commissionAsset"] == asset)
    fee_usdt = sum(float(f["commission"]) for f in resp.get("fills", []) if f["commissionAsset"] == "USDT")
    if side == "BUY":
        return {**state, asset: state.get(asset, 0.0) + qty - fee_asset, "cash": state["cash"] - quote - fee_usdt}
    return {**state, asset: state.get(asset, 0.0) - qty - fee_asset, "cash": state["cash"] + quote - fee_usdt}


def append_csv(path, row: dict) -> None:
    p = Path(path)
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def btc_daily_closes() -> pd.Series:
    rows = _get_json(SIGNAL_URL)
    now_ms = time.time() * 1000
    closed = [k for k in rows if k[6] < now_ms]
    return pd.Series([float(k[4]) for k in closed], index=pd.to_datetime([k[0] for k in closed], unit="ms"))


class Testnet:
    __test__ = False  # not a pytest test class

    def __init__(self, key: str, secret: str, base: str = BASE):
        if base != BASE:
            raise ValueError(f"refusing non-Testnet URL {base!r}")
        self.base, self._key, self._secret, self._offset = base, key, secret, None

    def __repr__(self):
        return "Testnet(base=%r, key=***, secret=***)" % self.base

    def _call(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = dict(params or {})
        headers = {}
        if signed:
            if self._offset is None:  # sync with the exchange clock once (avoids -1021 errors)
                self._offset = self._call("GET", "/api/v3/time")["serverTime"] - int(time.time() * 1000)
            params["timestamp"] = int(time.time() * 1000) + self._offset
            params["recvWindow"] = 5000
            q = urllib.parse.urlencode(params)
            params_q = q + "&signature=" + sign(q, self._secret)
            headers["X-MBX-APIKEY"] = self._key
        else:
            params_q = urllib.parse.urlencode(params)
        url = f"{self.base}{path}" + (f"?{params_q}" if method == "GET" and params_q else "")
        data = params_q.encode() if method == "POST" else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Binance Testnet error {e.code}: {e.read().decode(errors='replace')}") from None

    def prices(self, assets) -> dict:
        return {a: float(self._call("GET", "/api/v3/ticker/price", {"symbol": a + "USDT"})["price"]) for a in assets}

    def market_order(self, order: dict, client_id: str) -> dict:
        p = {"symbol": order["symbol"], "side": order["side"], "type": "MARKET", "newClientOrderId": client_id,
             "newOrderRespType": "FULL"}
        if "quantity" in order:
            p["quantity"] = f"{order['quantity']:.8f}".rstrip("0").rstrip(".")
        else:
            p["quoteOrderQty"] = f"{order['quote_qty']:.2f}"
        try:
            return self._call("POST", "/api/v3/order", p, signed=True)
        except (TimeoutError, urllib.error.URLError):
            # the order may have reached the exchange: look it up instead of sending it twice
            r = self._call("GET", "/api/v3/order", {"symbol": order["symbol"], "origClientOrderId": client_id}, signed=True)
            r.setdefault("fills", [])
            return r


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="send orders to the Testnet")
    ap.add_argument("--force", action="store_true", help="allow --live on a day the backtest would not trade")
    ap.add_argument("--budget", type=float, default=3000.0, help="USDT the strategy starts with")
    ap.add_argument("--strategy", choices=("brake", "fixed"), default="fixed")
    ap.add_argument("--gold", choices=("PAXG", "XAUT", "CASH"), default="CASH",
                    help="second asset; CASH keeps it in USDT")
    ap.add_argument("--check", action="store_true", help="only test the keys (read-only account call)")
    args = ap.parse_args(argv)
    env = load_env()
    key, secret = env.get("BINANCE_TESTNET_KEY"), env.get("BINANCE_TESTNET_SECRET")
    if args.check:
        if not (key and secret):
            raise SystemExit("No BINANCE_TESTNET_KEY / BINANCE_TESTNET_SECRET in .env")
        try:
            acct = Testnet(key, secret)._call("GET", "/api/v3/account", signed=True)
        except RuntimeError as e:
            raise SystemExit(f"Keys rejected by the Testnet: {e} "
                             "(-2014/-2015 usually means a real Binance key, "
                             "which does not work on the Testnet: create one at https://testnet.binance.vision)")
        held = {b["asset"]: b["free"] for b in acct["balances"] if b["asset"] in ("USDT", "BTC", "PAXG", "XAUT")}
        print("Keys work on the Testnet. canTrade:", acct.get("canTrade"), "| balances:", held)
        return
    if args.live and not (key and secret):
        raise SystemExit("--live needs BINANCE_TESTNET_KEY and BINANCE_TESTNET_SECRET in .env")
    assets = ("BTC",) if args.gold == "CASH" else ("BTC", args.gold)
    files = paths_for(args.strategy, args.gold)
    closes = btc_daily_closes()
    last = closes.index[-1]
    if args.live and not args.force and not trading_day_ok(last):
        raise SystemExit(f"Last closed candle is {last.date()} ({last.day_name()}): the strategy only trades "
                         "after a Monday close or a quarter's first day. Run Tuesday after 00:00 UTC, or use --force.")
    targets = signal_weights(closes, args.gold, args.strategy)
    client = Testnet(key or "", secret or "")
    prices = client.prices(assets)
    state = load_state(files["state"], args.budget, assets)
    holdings, cash = {a: state[a] for a in assets}, state["cash"]
    value = cash + sum(holdings[a] * prices[a] for a in assets)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Strategy {args.strategy} with {args.gold}: holds {holdings} + {cash:.2f} USDT = {value:.2f} USDT")
    print("Last closed BTC candle:", last.date(), "| target weights:", targets, "| prices:", prices)
    orders = plan_orders(holdings, prices, targets, cash, steps=STEPS)
    if not orders:
        print("Inside the 5-point band: nothing to do.")
    for i, o in enumerate(orders):
        what = f"{o['quantity']} {o['symbol'][:-4]}" if "quantity" in o else f"{o['quote_qty']:.2f} USDT"
        print(("SENDING " if args.live else "DRY RUN ") + f"{o['side']} {o['symbol']} for {what}")
        if not args.live:
            continue
        r = client.market_order(o, f"sbx{int(time.time())}{i}")
        print("  ->", r.get("status"), "filled", r.get("executedQty"), "for", r.get("cummulativeQuoteQty"))
        state = apply_fill(state, o["symbol"], o["side"], r)
        save_state(files["state"], state)  # after every fill, so a failed later order loses nothing
        append_csv(files["fills"], {"utc": now, "symbol": o["symbol"], "side": o["side"], "qty": r.get("executedQty"),
                           "quote": r.get("cummulativeQuoteQty"),
                           "fees": ";".join(f"{f['commission']} {f['commissionAsset']}" for f in r.get("fills", []))})
    if args.live:
        value = state["cash"] + sum(state[a] * prices[a] for a in assets)
        append_csv(files["runs"], {"utc": now, "strategy": args.strategy, "gold": args.gold, "btc_price": prices["BTC"],
                          "gold_price": prices.get(args.gold, ""), "btc_target": targets["BTC"], "value_usdt": round(value, 2)})


if __name__ == "__main__":
    main()
