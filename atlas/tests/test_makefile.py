from pathlib import Path


def test_make_all_ingests_fundamentals_before_dbt_build():
    makefile = Path("Makefile").read_text()
    ingest_body = makefile.split("ingest:", maxsplit=1)[1].split("\nbuild:", maxsplit=1)[0]
    assert "python -m ingest.graph" in ingest_body
    assert "python -m ingest.fundamentals" in ingest_body
    assert ingest_body.index("python -m ingest.graph") < ingest_body.index(
        "python -m ingest.fundamentals"
    )
