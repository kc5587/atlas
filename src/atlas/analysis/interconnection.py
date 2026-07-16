"""Transparent aggregation of public interconnection queue projects."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import median


@dataclass(frozen=True, slots=True)
class QueueProject:
    """One normalised project row from the Berkeley Lab queue dataset."""

    region_id: str
    status: str
    request_date: date
    operation_date: date | None
    capacity_mw: float

    def __post_init__(self) -> None:
        if not self.region_id.strip() or not self.status.strip():
            raise ValueError("queue project region and status are required")
        if self.capacity_mw < 0:
            raise ValueError("queue capacity cannot be negative")


def aggregate_queue_projects(
    projects: tuple[QueueProject, ...],
) -> tuple[dict[str, object], ...]:
    """Aggregate active capacity, outcomes, and realised queue duration."""

    grouped: defaultdict[str, list[QueueProject]] = defaultdict(list)
    for project in projects:
        grouped[project.region_id].append(project)
    output: list[dict[str, object]] = []
    for region_id, values in sorted(grouped.items()):
        active = tuple(item for item in values if item.status == "active")
        withdrawn = sum(item.status == "withdrawn" for item in values)
        completed = tuple(
            item
            for item in values
            if item.status == "operational" and item.operation_date is not None
        )
        denominator = sum(
            item.status in {"active", "withdrawn", "operational", "suspended"}
            for item in values
        )
        years = tuple(
            (item.operation_date - item.request_date).days / 365.25
            for item in completed
        )
        output.append(
            {
                "region_id": region_id,
                "sample_size": len(values),
                "active_project_count": len(active),
                "active_capacity_mw": round(sum(item.capacity_mw for item in active), 4),
                "withdrawal_rate": round(withdrawn / denominator, 4)
                if denominator
                else None,
                "operational_project_count": len(completed),
                "median_years_request_to_operation": round(median(years), 4)
                if years
                else None,
            }
        )
    return tuple(output)


def queue_project_as_dict(project: QueueProject) -> dict[str, object]:
    """Return a JSON-compatible project row for fixture and adapter tests."""

    return {
        "region_id": project.region_id,
        "status": project.status,
        "request_date": project.request_date.isoformat(),
        "operation_date": (
            None if project.operation_date is None else project.operation_date.isoformat()
        ),
        "capacity_mw": project.capacity_mw,
    }
