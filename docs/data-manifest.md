# Data manifest

`data/` is gitignored. These are the inputs used by the 2026-10-06 studies (SHA-256, first 16 hex).

| File | Bytes | SHA-256 |
|---|---|---|
| `data/fear_greed.csv` | 53,769 | `b8e4bc583d03a731…` |
| `data/gold_gc_yahoo.json` | 234,061 | `82f38f73deabcbb8…` |
| `data/spot_1d/BTCUSDT.parquet` | 151,552 | `ebd7a35fac806bf6…` |
| `data/spot_1d/ETHUSDT.parquet` | 144,318 | `0e5db437b87b1b04…` |
| `data/spot_1d/PAXGUSDT.parquet` | 80,468 | `d4759c3a4a68e12a…` |
| `data/spot_1h/BTCUSDT.parquet` | 2,333,363 | `08aebe67e7f09cb3…` |
| `data/spot_1h/ETHUSDT.parquet` | 2,139,169 | `93309fae8ecceab5…` |

Sources:
- `spot_1d/`, `spot_1h/`: Binance public archive, data.binance.vision (`python -m research.run_phase1`, `research.data.download_hourly`).
- `gold_gc_yahoo.json`: Yahoo Finance chart API, `GC=F`, daily, 2017-01-01 → 2026-09-30, downloaded 2026-10-06 with
  PowerShell `Invoke-WebRequest "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?period1=1483228800&period2=1790812800&interval=1d"`.
- `fear_greed.csv`: alternative.me Fear & Greed API (`research.sentiment.load_fear_greed`).
