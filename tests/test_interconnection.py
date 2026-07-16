from datetime import date

import pytest

from atlas.analysis.interconnection import QueueProject, aggregate_queue_projects


def test_queue_aggregation_reports_capacity_withdrawals_and_wait_time() -> None:
    projects = (
        QueueProject("ERCO", "active", date(2022, 1, 1), None, 100),
        QueueProject("ERCO", "withdrawn", date(2021, 1, 1), None, 200),
        QueueProject("ERCO", "operational", date(2019, 1, 1), date(2023, 1, 1), 50),
    )

    result = aggregate_queue_projects(projects)[0]

    assert result["active_project_count"] == 1
    assert result["active_capacity_mw"] == 100
    assert result["withdrawal_rate"] == pytest.approx(1 / 3, abs=0.0001)
    assert result["median_years_request_to_operation"] == 4.0
