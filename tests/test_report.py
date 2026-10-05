import numpy as np
import pandas as pd

from research.report import go_no_go, write_report

IDX = pd.date_range("2021-01-01", periods=730)


def test_go_when_all_criteria_pass():
    oos = pd.Series(np.random.default_rng(0).normal(0.002, 0.01, 730), index=IDX)
    bench = {"Hold BTC": pd.Series(np.random.default_rng(1).normal(0.0, 0.03, 730), index=IDX)}
    checks, go = go_no_go(oos, bench, {"sharpe": (1.2, 4.0)}, 0.1)
    assert go and all(checks.values())


def test_no_go_when_pbo_high():
    oos = pd.Series(np.random.default_rng(0).normal(0.002, 0.01, 730), index=IDX)
    checks, go = go_no_go(oos, {}, {"sharpe": (1.2, 4.0)}, 0.6)
    assert not go and not checks["PBO < 0.3"]


def test_write_report_creates_markdown(tmp_path):
    path = write_report(tmp_path / "r.md", {"Verdict": "GO", "Details": "| a |\n|---|\n| 1 |"})
    text = path.read_text(encoding="utf-8")
    assert "## Verdict" in text and "GO" in text


def test_no_go_when_overfitting_stats_unavailable():
    oos = pd.Series(np.random.default_rng(0).normal(0.002, 0.01, 730), index=IDX)
    checks, go = go_no_go(oos, {}, {"sharpe": (1.2, 4.0)}, None)
    assert not go and not checks["PBO < 0.3"]
