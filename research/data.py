"""Download daily spot candles for every USDT pair, listed and delisted, from data.binance.vision."""
import io
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FILES = "https://data.binance.vision"
NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
KLINE_PREFIX = "data/spot/monthly/klines/"


def _get(url: str, timeout: int = 60) -> bytes:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def _list(prefix: str) -> tuple[list[str], list[str]]:
    """Return (sub-folder prefixes, file keys) under an S3 prefix, following pagination."""
    prefixes, keys, marker = [], [], ""
    while True:
        url = f"{BUCKET}?delimiter=/&prefix={urllib.parse.quote(prefix)}" + (f"&marker={urllib.parse.quote(marker)}" if marker else "")
        root = ET.fromstring(_get(url))
        prefixes += [p.text for p in root.findall("s3:CommonPrefixes/s3:Prefix", NS)]
        keys += [k.text for k in root.findall("s3:Contents/s3:Key", NS)]
        if root.findtext("s3:IsTruncated", namespaces=NS) != "true":
            return prefixes, keys
        marker = root.findtext("s3:NextMarker", namespaces=NS) or (keys or prefixes)[-1]


def list_usdt_symbols() -> list[str]:
    prefixes, _ = _list(KLINE_PREFIX)
    return sorted(s for s in (p.rstrip("/").split("/")[-1] for p in prefixes) if s.endswith("USDT"))


def parse_kline_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), header=None, dtype=str)
    if not df.iloc[0, 0].isdigit():
        df = df.iloc[1:]
    t = pd.to_numeric(df[0]).astype("int64")
    t = t.where(t < 10**14, t // 1000)  # files from 2025 on use microseconds
    out = pd.DataFrame({"date": pd.to_datetime(t.values, unit="ms").normalize()})
    for col, name in [(1, "open"), (2, "high"), (3, "low"), (4, "close"), (7, "quote_volume")]:
        out[name] = pd.to_numeric(df[col]).astype(float).values
    return out


def _csv_from_zip(raw: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return z.read(z.namelist()[0])


def download_symbol(symbol: str, out_dir: Path) -> Path | None:
    path = Path(out_dir) / f"{symbol}.parquet"
    if path.exists():
        return path
    _, keys = _list(f"{KLINE_PREFIX}{symbol}/1d/")
    zips = sorted(k for k in keys if k.endswith(".zip"))
    if not zips:
        return None
    frames = [parse_kline_csv(_csv_from_zip(_get(f"{FILES}/{urllib.parse.quote(k)}"))) for k in zips]
    df = pd.concat(frames).drop_duplicates("date").sort_values("date")
    df.to_parquet(path, index=False)
    return path


def download_all(out_dir, workers: int = 16, symbols: list[str] | None = None) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    symbols = symbols or list_usdt_symbols()

    def safe(sym):
        try:
            return download_symbol(sym, out_dir)
        except Exception as exc:  # one bad symbol must not stop the download
            print(ascii(f"skip {sym}: {exc}"))
            return None

    with ThreadPoolExecutor(workers) as ex:
        return [p for p in ex.map(safe, symbols) if p]
