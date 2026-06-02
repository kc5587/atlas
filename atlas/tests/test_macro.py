import pandas as pd

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
