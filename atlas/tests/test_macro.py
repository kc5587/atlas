from pathlib import Path

import pandas as pd

import ingest.macro as macro
from ingest.macro import _csv_to_indexed_frame, normalize_macro


def test_csv_to_indexed_frame_parses_and_handles_missing():
    # FRED encodes missing observations as '.'
    csv = "DATE,DFF\n2024-01-01,5.33\n2024-01-02,.\n2024-01-03,5.40\n"
    frame = _csv_to_indexed_frame(csv, "DFF")
    assert list(frame.columns) == ["DFF"]
    assert len(frame) == 3
    assert pd.isna(frame["DFF"].iloc[1])
    # downstream normalize drops the missing row
    out = normalize_macro(frame, "DFF")
    assert len(out) == 2


def test_normalize_macro_long_format():
    raw = pd.DataFrame(
        {"DFF": [5.33, 5.33]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    out = normalize_macro(raw, "DFF")
    assert list(out.columns) == ["series_id", "date", "value"]
    assert out["series_id"].unique().tolist() == ["DFF"]
    assert len(out) == 2


def test_normalize_macro_drops_nan_values():
    raw = pd.DataFrame(
        {"DGS10": [4.0, None]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    out = normalize_macro(raw, "DGS10")
    assert len(out) == 1
    assert out["value"].iloc[0] == 4.0


def _good_frame(series_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": series_id,
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "value": [1.0, 2.0],
        }
    )


def test_run_continues_when_one_series_fails(tmp_path, monkeypatch):
    """A failing fetch for one series must not abort the whole run."""
    monkeypatch.setattr(macro, "DATA_RAW", tmp_path)
    monkeypatch.setattr(macro, "FRED_SERIES", {"BAD": "Broken", "GOOD": "Works"})

    def fake_fetch(series_id: str, start: str = "2010-01-01") -> pd.DataFrame:
        if series_id == "BAD":
            raise RuntimeError("FRED timeout")
        return _good_frame(series_id)

    monkeypatch.setattr(macro, "fetch_macro", fake_fetch)

    macro.run()  # must not raise

    out_dir = Path(tmp_path) / "macro"
    assert (out_dir / "GOOD.parquet").exists()
    assert not (out_dir / "BAD.parquet").exists()


def test_run_writes_empty_fallback_when_all_fail(tmp_path, monkeypatch):
    """When every series fails, at least one parquet must exist for the dbt glob."""
    monkeypatch.setattr(macro, "DATA_RAW", tmp_path)
    monkeypatch.setattr(macro, "FRED_SERIES", {"A": "a", "B": "b"})

    def always_fail(series_id: str, start: str = "2010-01-01") -> pd.DataFrame:
        raise RuntimeError("FRED down")

    monkeypatch.setattr(macro, "fetch_macro", always_fail)

    macro.run()  # must not raise

    out_dir = Path(tmp_path) / "macro"
    parquets = list(out_dir.glob("*.parquet"))
    assert parquets, "expected at least one fallback parquet"
    # the fallback must have the MACRO_SCHEMA columns and 0 rows
    df = pd.read_parquet(parquets[0])
    assert list(df.columns) == ["series_id", "date", "value"]
    assert len(df) == 0
