import json

import pandas as pd

from botcore.params import Params
from research import sentiment
from research.backtest import build_market
from research.tune import tune, walk_forward
from tests.conftest import make_panel


def test_fetch_fear_greed_parses_api(monkeypatch):
    payload = {"data": [{"value": "80", "timestamp": "1609545600"}, {"value": "20", "timestamp": "1609459200"}]}
    monkeypatch.setattr(sentiment, "_get", lambda url, timeout=60: json.dumps(payload).encode())
    s = sentiment.fetch_fear_greed()
    assert list(s.index) == [pd.Timestamp("2021-01-01"), pd.Timestamp("2021-01-02")]
    assert list(s.values) == [20.0, 80.0]


def test_load_fear_greed_uses_cache(monkeypatch, tmp_path):
    path = tmp_path / "fng.csv"
    pd.Series([50.0], index=pd.to_datetime(["2021-01-01"]), name="fng").to_csv(path)
    monkeypatch.setattr(sentiment, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    assert sentiment.load_fear_greed(path).iloc[0] == 50.0


def test_tune_returns_params_within_search_space():
    m = build_market(make_panel(n_days=600), Params(min_history_days=120))
    best = tune(m, Params(min_history_days=120), "2020-06-01", "2021-03-31", n_trials=3)
    f, mid, slow = best.windows
    assert 10 <= f <= 30 and 40 <= mid <= 80 and 90 <= slow <= 200 and 2.0 <= best.atr_mult <= 5.0


def test_walk_forward_concatenates_out_of_sample_years():
    m = build_market(make_panel(n_days=1100, start="2019-01-01"), Params(min_history_days=120))
    wf = walk_forward(m, Params(min_history_days=120), 2021, 2021, train_start="2019-07-01", n_trials=2)
    assert wf.returns.index.min() == pd.Timestamp("2021-01-01")
    assert wf.returns.index.max() == pd.Timestamp("2021-12-31")
    assert set(wf.chosen) == {2021} and len(wf.trials[0]) == 2


def test_walk_forward_reports_trades_and_costs():
    m = build_market(make_panel(n_days=1100, start="2019-01-01", drift=(0.003, 0.002, 0.001)),
                     Params(min_history_days=120))
    wf = walk_forward(m, Params(min_history_days=120), 2021, 2021, train_start="2019-07-01", n_trials=2)
    assert wf.trades > 0 and wf.costs > 0
