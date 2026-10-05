import io
import zipfile

import pandas as pd

from research import data

LISTING = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<IsTruncated>false</IsTruncated>
<CommonPrefixes><Prefix>data/spot/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>data/spot/monthly/klines/ETHBTC/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>data/spot/monthly/klines/LUNAUSDT/</Prefix></CommonPrefixes>
</ListBucketResult>"""

FILES = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<IsTruncated>false</IsTruncated>
<Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-12.zip</Key></Contents>
<Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-12.zip.CHECKSUM</Key></Contents>
<Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2025-01.zip</Key></Contents>
</ListBucketResult>"""

ROW_MS = b"1733011200000,100,110,90,105,1,1733097599999,5000,10,0,0,0\n"        # 2024-12-01, ms
ROW_US = b"1735689600000000,105,120,100,115,1,1735775999999999,6000,10,0,0,0\n"  # 2025-01-01, us


def zipped(csv: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("f.csv", csv)
    return buf.getvalue()


def test_list_usdt_symbols_keeps_only_usdt_pairs(monkeypatch):
    monkeypatch.setattr(data, "_get", lambda url, timeout=60: LISTING)
    assert data.list_usdt_symbols() == ["BTCUSDT", "LUNAUSDT"]


def test_parse_handles_milliseconds_and_microseconds():
    df = data.parse_kline_csv(ROW_MS + ROW_US)
    assert list(df["date"]) == [pd.Timestamp("2024-12-01"), pd.Timestamp("2025-01-01")]
    assert list(df["close"]) == [105.0, 115.0]
    assert list(df["quote_volume"]) == [5000.0, 6000.0]


def test_parse_skips_header_row():
    header = b"open_time,open,high,low,close,volume,close_time,quote_volume,count,tb,tq,ignore\n"
    assert len(data.parse_kline_csv(header + ROW_MS)) == 1


def test_download_symbol_writes_parquet(monkeypatch, tmp_path):
    def fake_get(url, timeout=60):
        if "prefix=" in url:
            return FILES
        return zipped(ROW_MS if "2024-12" in url else ROW_US)

    monkeypatch.setattr(data, "_get", fake_get)
    path = data.download_symbol("BTCUSDT", tmp_path)
    df = pd.read_parquet(path)
    assert len(df) == 2 and df["date"].is_monotonic_increasing


def test_download_symbol_quotes_non_ascii_symbol(monkeypatch, tmp_path):
    urls = []

    def fake_get(url, timeout=60):
        urls.append(url)
        return FILES.replace(b"BTCUSDT", "币安USDT".encode()) if "prefix=" in url else zipped(ROW_MS)

    monkeypatch.setattr(data, "_get", fake_get)
    assert data.download_symbol("币安USDT", tmp_path) is not None
    assert all(u.isascii() for u in urls)


def test_download_all_survives_non_ascii_error_on_cp1252_console(monkeypatch, tmp_path):
    def fake_download(sym, out_dir):
        if sym == "BADUSDT":
            raise RuntimeError("币安 failed")
        return tmp_path / f"{sym}.parquet"

    monkeypatch.setattr(data, "download_symbol", fake_download)
    monkeypatch.setattr("sys.stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    assert data.download_all(tmp_path, workers=2, symbols=["BADUSDT", "OKUSDT"]) == [tmp_path / "OKUSDT.parquet"]


def test_download_symbol_skips_existing(monkeypatch, tmp_path):
    (tmp_path / "BTCUSDT.parquet").write_bytes(b"x")
    monkeypatch.setattr(data, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    assert data.download_symbol("BTCUSDT", tmp_path) == tmp_path / "BTCUSDT.parquet"
