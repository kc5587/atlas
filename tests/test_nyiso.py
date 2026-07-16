import io
import zipfile
from datetime import date
from pathlib import Path

from atlas.evidence import EvidenceKind, SourceRef
from atlas.ingest.nyiso import parse_nyiso_lbmp_zip


SOURCE = SourceRef(
    id="nyiso:dam-lbmp",
    url="https://mis.nyiso.com/public/P-2Alist.htm",
    publisher="New York Independent System Operator",
)


def test_nyiso_parser_aggregates_load_zones_by_timestamp(tmp_path: Path) -> None:
    content = "\n".join(
        (
            "Time Stamp,Name,PTID,LBMP ($/MWHr),Marginal Cost Losses ($/MWHr),Marginal Cost Congestion ($/MWHr)",
            "01/01/2024 00:00,CAPITL,1,10,0,0",
            "01/01/2024 00:00,CENTRL,2,20,0,0",
            "01/01/2024 00:00,PJM,3,999,0,0",
            "01/01/2024 01:00,CAPITL,1,30,0,0",
            "01/01/2024 01:00,CENTRL,2,50,0,0",
        )
    ).encode()
    path = tmp_path / "nyiso.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("20240101damlbmp_zone.csv", content)

    observations = parse_nyiso_lbmp_zip(path, SOURCE, date(2024, 1, 2))

    assert len(observations) == 2
    assert observations[0].entity_id == "NYIS"
    assert observations[0].value == 15.0
    assert observations[0].kind is EvidenceKind.INFERRED
    assert "nyiso_zone_mean_unweighted" in observations[0].quality_flags
