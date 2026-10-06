import numpy as np
import pandas as pd
import pytest

from bot.testnet import BASE, Testnet, append_csv, apply_fill, load_env, sign, signal_weights, trading_day_ok
from botcore.rebalance import plan_orders

PX = {"BTC": 100_000.0, "PAXG": 4_000.0}
T = {"BTC": 0.5, "PAXG": 0.5}


def test_signature_matches_binance_documentation_example():
    q = "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1&recvWindow=5000&timestamp=1499827319559"
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
    assert sign(q, secret) == "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"


def test_refuses_any_url_other_than_testnet():
    with pytest.raises(ValueError):
        Testnet("k", "s", base="https://api.binance.com")
    assert "s3cr3t" not in repr(Testnet("k", "s3cr3t", base=BASE))


def test_all_cash_buys_both_assets():
    orders = plan_orders({"BTC": 0.0, "PAXG": 0.0}, PX, T, cash=3000.0)
    assert [(o["symbol"], o["side"]) for o in orders] == [("BTCUSDT", "BUY"), ("PAXGUSDT", "BUY")]
    assert sum(o["quote_qty"] for o in orders) <= 3000.0 * 0.995 + 0.01


def test_no_orders_inside_band():
    assert plan_orders({"BTC": 0.0152, "PAXG": 0.37}, PX, T, cash=0.0) == []   # 1520 / 1480 = 50.7%


def test_sells_come_before_buys_when_brake_moves_btc_to_gold():
    orders = plan_orders({"BTC": 0.015, "PAXG": 0.375}, PX, {"BTC": 0.0, "PAXG": 1.0}, cash=0.0)
    assert [(o["symbol"], o["side"]) for o in orders] == [("BTCUSDT", "SELL"), ("PAXGUSDT", "BUY")]
    assert orders[0]["quote_qty"] == pytest.approx(1500.0)
    assert orders[1]["quote_qty"] <= 1500.0 * 0.995 + 0.01


def test_orders_below_exchange_minimum_are_skipped():
    orders = plan_orders({"BTC": 0.0, "PAXG": 0.0}, PX, {"BTC": 0.001, "PAXG": 0.999}, cash=3000.0, band=0.0)
    assert [o["symbol"] for o in orders] == ["PAXGUSDT"]


def test_signal_follows_200_day_average_on_closed_candles():
    up = pd.Series(np.r_[np.full(199, 100.0), 120.0])
    down = pd.Series(np.r_[np.full(199, 100.0), 80.0])
    assert signal_weights(up) == {"BTC": 0.5, "PAXG": 0.5}
    assert signal_weights(down) == {"BTC": 0.0, "PAXG": 1.0}
    assert signal_weights(down, gold="XAUT") == {"BTC": 0.0, "XAUT": 1.0}
    with pytest.raises(ValueError):
        signal_weights(up.iloc[:150])


def test_load_env_reads_keys_and_ignores_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# testnet\nBINANCE_TESTNET_KEY=abc\nBINANCE_TESTNET_SECRET = 'xyz'\n")
    assert load_env(p) == {"BINANCE_TESTNET_KEY": "abc", "BINANCE_TESTNET_SECRET": "xyz"}
    assert load_env(tmp_path / "missing.env") == {}


def test_strategy_tracks_only_its_own_positions(tmp_path):
    from bot.testnet import apply_fill, load_state, save_state
    path = tmp_path / "state.json"
    s = load_state(path, budget=3000.0)
    assert s == {"cash": 3000.0, "BTC": 0.0, "PAXG": 0.0}
    s = apply_fill(s, "BTCUSDT", "BUY", {"executedQty": "0.0175", "cummulativeQuoteQty": "1492.50", "fills": []})
    s = apply_fill(s, "BTCUSDT", "SELL", {"executedQty": "0.0075", "cummulativeQuoteQty": "640.00", "fills": []})
    save_state(path, s)
    assert load_state(path, budget=999.0) == pytest.approx({"cash": 3000.0 - 1492.5 + 640.0, "BTC": 0.01, "PAXG": 0.0})


def test_fees_are_taken_from_the_asset_they_are_charged_in():
    s = {"cash": 1000.0, "BTC": 0.0, "PAXG": 0.0}
    s = apply_fill(s, "BTCUSDT", "BUY", {"executedQty": "0.01", "cummulativeQuoteQty": "900",
                                         "fills": [{"commission": "0.00001", "commissionAsset": "BTC"}]})
    assert s["BTC"] == pytest.approx(0.00999) and s["cash"] == pytest.approx(100.0)
    s = apply_fill(s, "BTCUSDT", "SELL", {"executedQty": "0.005", "cummulativeQuoteQty": "450",
                                          "fills": [{"commission": "0.45", "commissionAsset": "USDT"}]})
    assert s["BTC"] == pytest.approx(0.00499) and s["cash"] == pytest.approx(100.0 + 449.55)


def test_full_exit_sells_the_held_quantity_rounded_down_to_the_step():
    orders = plan_orders({"BTC": 0.0123456, "PAXG": 0.0}, PX, {"BTC": 0.0, "PAXG": 1.0}, cash=0.0,
                         steps={"BTC": 0.00001, "PAXG": 0.0001})
    assert orders[0]["side"] == "SELL" and orders[0]["quantity"] == pytest.approx(0.01234)
    assert "quantity" not in orders[1]


def test_bot_only_trades_after_a_monday_or_quarter_start_candle():
    assert trading_day_ok(pd.Timestamp("2026-10-05"))          # Monday
    assert trading_day_ok(pd.Timestamp("2026-10-01"))          # first day of a quarter (Thursday)
    assert not trading_day_ok(pd.Timestamp("2026-10-07"))      # Wednesday


def test_append_csv_writes_header_once(tmp_path):
    p = tmp_path / "log.csv"
    append_csv(p, {"a": 1, "b": 2})
    append_csv(p, {"a": 3, "b": 4})
    assert p.read_text().splitlines() == ["a,b", "1,2", "3,4"]
