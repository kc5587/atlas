"""Auditable evidence primitives used by ingestion and analysis."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from math import isfinite
from urllib.parse import urlparse


Temporal = date | datetime


class EvidenceKind(StrEnum):
    """How directly a value is supported by its source."""

    OBSERVED = "observed"
    ESTIMATED = "estimated"
    INFERRED = "inferred"


@dataclass(frozen=True, slots=True)
class SourceRef:
    """A stable citation for a source document or API endpoint."""

    id: str
    url: str
    publisher: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or not isinstance(self.publisher, str)
            or not self.id.strip()
            or not self.publisher.strip()
        ):
            raise ValueError("source id and publisher are required")
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source url must be an absolute http(s) URL")


@dataclass(frozen=True, slots=True)
class Observation:
    """One typed, time-bounded and provenance-linked data point."""

    id: str
    metric_id: str
    entity_id: str
    period_start: Temporal
    period_end: Temporal
    value: float
    unit: str
    source: SourceRef
    retrieved_at: Temporal
    vintage: str
    kind: EvidenceKind
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (self.id, self.metric_id, self.entity_id, self.unit, self.vintage)
        if any(not isinstance(field, str) or not field.strip() for field in required):
            raise ValueError("observation identifiers, unit, and vintage are required")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("observation value must be finite")
        if not isfinite(self.value):
            raise ValueError("observation value must be finite")
        if not isinstance(self.period_start, (date, datetime)) or not isinstance(
            self.period_end, (date, datetime)
        ):
            raise ValueError("observation periods must be dates or datetimes")
        if self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
