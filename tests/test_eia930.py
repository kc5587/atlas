from datetime import date
from pathlib import Path

from atlas.ingest.eia930 import parse_eia930_files


def test_parse_eia930_bulk_balance(tmp_path: Path) -> None:
    path = tmp_path / "balance.csv"
    path.write_text(
        '"Balancing Authority","UTC Time at End of Hour","Demand (MW)","Net Generation (MW)"\n'
        'ERCO,"01/01/2022 7:00:00 AM",2251,1986\n'
        'OTHER,"01/01/2022 7:00:00 AM",1,2\n',
        encoding="utf-8",
    )

    observations = parse_eia930_files((path,), ("ERCO",), date(2026, 7, 3))

    assert len(observations) == 2
    assert {item.metric_id for item in observations} == {"demand", "net_generation"}
    assert observations[0].entity_id == "ERCO"
