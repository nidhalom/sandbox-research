from pathlib import Path

import pandas as pd

FIELDS = ["open", "high", "low", "close", "quote_volume"]


def load_panel(data_dir) -> dict[str, pd.DataFrame]:
    frames = {p.stem: pd.read_parquet(p).set_index("date") for p in sorted(Path(data_dir).glob("*.parquet"))}
    if not frames:
        raise FileNotFoundError(f"no parquet files in {data_dir}")
    idx = pd.date_range(min(f.index.min() for f in frames.values()),
                        max(f.index.max() for f in frames.values()), freq="D")
    return {f: pd.DataFrame({s: df[f] for s, df in frames.items()}).reindex(idx) for f in FIELDS}
