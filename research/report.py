from pathlib import Path

import pandas as pd

from botcore.metrics import max_drawdown, sharpe


def go_no_go(oos: pd.Series, benchmarks: dict, ci: dict, pbo_value: float | None) -> tuple[dict, bool]:
    s = sharpe(oos)
    checks = {
        "Sharpe ≥ 1.0": s >= 1.0,
        "Sharpe 90% CI lower bound ≥ 0.5": ci["sharpe"][0] >= 0.5,
        "Max drawdown no worse than −35%": max_drawdown(oos) >= -0.35,
        "PBO < 0.3": pbo_value is not None and pbo_value < 0.3,
    }
    for name, b in benchmarks.items():
        checks[f"Sharpe above {name}"] = s > sharpe(b.reindex(oos.index).fillna(0))
    return checks, all(checks.values())


def write_report(path, sections: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ["# Phase 1 Research Report", ""]
    for title, text in sections.items():
        body += [f"## {title}", "", text, ""]
    path.write_text("\n".join(body), encoding="utf-8")
    return path
