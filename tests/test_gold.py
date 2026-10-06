import pandas as pd
import pytest

from research.gold import splice


def test_splice_uses_gc_before_switch_paxg_after_and_never_backfills():
    idx = pd.date_range("2020-08-28", "2020-09-03", freq="D")
    gc = pd.Series([100.0, 102.0, 104.0], index=pd.DatetimeIndex(["2020-08-28", "2020-08-31", "2020-09-02"]))
    paxg = pd.Series([50.0, 55.0, 55.0, 60.5], index=pd.date_range("2020-08-31", periods=4, freq="D"))
    g = splice(gc, paxg, idx, switch="2020-09-01")
    assert g.loc["2020-08-29"] == pytest.approx(100.0)            # weekend: forward-filled
    assert g.loc["2020-08-31"] == pytest.approx(102.0)            # GC return before switch
    assert g.loc["2020-09-01"] == pytest.approx(102.0 * 1.1)      # PAXG return from switch
    assert g.loc["2020-09-03"] == pytest.approx(102.0 * 1.1 * 1.1)
    assert g.notna().all()
