"""Versioned analytical export and static HTML report generation."""

from datetime import date, datetime
from html import escape
from collections.abc import Mapping
from typing import Any

from atlas.evidence import Observation
from atlas.scoring import BottleneckScore


EXECUTION_EVIDENCE = (
    {
        "title": "IEA Energy and AI",
        "url": "https://www.iea.org/reports/energy-and-ai/",
        "kind": "estimated",
        "role": "Global scenario context for data-centre energy demand and supply.",
    },
    {
        "title": "LBNL United States Data Center Energy Usage Report: 2025 Update",
        "url": (
            "https://eta-publications.lbl.gov/publications/"
            "united-states-data-center-energy-2025"
        ),
        "kind": "estimated",
        "role": "US demand scenarios and bottom-up methodology context.",
    },
    {
        "title": "EIA Wholesale Electricity and Natural Gas Market Data",
        "url": "https://www.eia.gov/electricity/wholesale/",
        "kind": "observed",
        "role": "Public wholesale price source and hub coverage limitations.",
    },
)


def build_export(
    scores: tuple[BottleneckScore, ...],
    generated_at: date | datetime,
    dataset_status: str,
) -> dict[str, Any]:
    """Return a versioned export with no references to mutable domain objects."""

    if not dataset_status.strip():
        raise ValueError("dataset_status is required")
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "dataset_status": dataset_status,
        "regions": [_serialize_score(score) for score in scores],
    }


def build_report_export(
    scores: tuple[BottleneckScore, ...],
    unavailable_regions: Mapping[str, str],
    capex_observations: tuple[Observation, ...],
    company_labels: Mapping[str, str],
    generated_at: date | datetime,
    dataset_status: str,
) -> dict[str, Any]:
    """Build the complete v1 report payload."""

    report = build_export(scores, generated_at, dataset_status)
    report["unavailable_regions"] = [
        {"region_id": region_id, "reason": reason}
        for region_id, reason in sorted(unavailable_regions.items())
    ]
    report["companies"] = _serialize_capex(capex_observations, company_labels)
    report["execution_evidence"] = [dict(item) for item in EXECUTION_EVIDENCE]
    return report


def render_report_html(report: Mapping[str, Any]) -> str:
    """Render a dependency-free, source-aware static report."""

    region_rows = "".join(_region_row(region) for region in report.get("regions", ()))
    region_cards = _region_cards(report)
    execution_rows = "".join(
        f"<li><span class='evidence-kind {escape(str(item['kind']))}'>"
        f"{escape(str(item['kind']))}</span> "
        f"<a href='{escape(str(item['url']))}'>"
        f"{escape(str(item['title']))}</a> — "
        f"{escape(str(item['role']))}</li>"
        for item in report.get("execution_evidence", ())
    )
    unavailable_rows = "".join(
        f"<tr><td>{escape(str(item['region_id']))}</td>"
        f"<td colspan='4'>Unavailable: {escape(str(item['reason']))}</td></tr>"
        for item in report.get("unavailable_regions", ())
    )
    company_rows = "".join(
        _company_row(company) for company in report.get("companies", ())
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Atlas v1</title>
<style>{_css()}</style></head><body>
<main><header><p class="eyebrow">ATLAS V1 · AI INFRASTRUCTURE BOTTLENECK MONITOR</p>
<h1>Where is AI infrastructure under pressure?</h1>
<p class="lede">Snapshot: {escape(str(report.get('generated_at', 'unknown')))} ·
Status: <strong>{escape(str(report.get('dataset_status', 'unknown')))}</strong></p></header>
<section><h2>Regional overview</h2><table><thead><tr>
<th>Region</th><th>Pressure</th><th>Confidence</th><th>Missing</th><th>Evidence</th>
</tr></thead><tbody>{region_rows}{unavailable_rows}</tbody></table></section>
<section><h2>Regional detail cards</h2><div class="cards">{region_cards}</div></section>
<section><h2>Company capital commitment</h2><table><thead><tr>
<th>Company</th><th>Latest filed capex</th><th>Prior filed capex</th><th>Change</th><th>Vintage</th>
</tr></thead><tbody>{company_rows}</tbody></table></section>
<section><h2>Execution-friction evidence</h2><ul>
{execution_rows}</ul></section>
<section><h2>Method and caveats</h2><p>
Pressure is descriptive, not a shortage probability or trading signal.
Missing data lowers confidence and is not treated as zero. “Supply tightness” is a
net-generation headroom proxy, not a formal reserve margin.</p>
<p><strong>Evidence key:</strong> <span class="evidence-kind observed">observed</span>
is directly reported; <span class="evidence-kind estimated">estimated</span> is
scenario or model-based; <span class="evidence-kind inferred">inferred</span> is
an Atlas analytical interpretation.</p></section>
</main></body></html>"""


def _serialize_score(score: BottleneckScore) -> dict[str, Any]:
    return {
        "region_id": score.region_id,
        "as_of": score.as_of.isoformat(),
        "pressure": round(score.pressure, 4),
        "confidence": round(score.confidence, 4),
        "missing_components": list(score.missing_components),
        "components": [
            {
                "name": component.name,
                "value": component.value,
                "weight": component.weight,
                "contribution": round(component.contribution, 4),
                "confidence": component.confidence,
                "observation_ids": list(component.observation_ids),
            }
            for component in score.components
        ],
    }


def _serialize_capex(
    observations: tuple[Observation, ...], labels: Mapping[str, str]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Observation]] = {}
    for observation in observations:
        if observation.metric_id == "capex":
            grouped.setdefault(observation.entity_id, []).append(observation)
    rows: list[dict[str, Any]] = []
    for entity_id, values in grouped.items():
        ordered = sorted(values, key=lambda observation: observation.period_end)
        latest = ordered[-1]
        prior = ordered[-2] if len(ordered) > 1 else None
        change = (
            None
            if prior is None or prior.value == 0
            else (latest.value / prior.value - 1) * 100
        )
        rows.append(
            {
                "company": labels.get(entity_id, entity_id),
                "entity_id": entity_id,
                "latest_value": latest.value,
                "latest_period_end": latest.period_end.isoformat(),
                "latest_vintage": latest.vintage,
                "prior_value": None if prior is None else prior.value,
                "prior_period_end": None if prior is None else prior.period_end.isoformat(),
                "change_vs_prior_pct": None if change is None else round(change, 4),
                "observation_ids": [latest.id] + ([] if prior is None else [prior.id]),
                "evidence_kind": latest.kind.value,
            }
        )
    return sorted(rows, key=lambda row: row["company"])


def _region_row(region: Mapping[str, Any]) -> str:
    missing = ", ".join(region.get("missing_components", ())) or "none"
    evidence = "<br>".join(
        f"{escape(str(component['name']))}: {component['value']}"
        for component in region.get("components", ())
        if component.get("value") is not None
    )
    return (
        f"<tr><td><strong>{escape(str(region['region_id']))}</strong></td>"
        f"<td>{region['pressure']:.1f}</td><td>{region['confidence']:.0%}</td>"
        f"<td>{escape(missing)}</td><td>{evidence or 'no component evidence'}</td></tr>"
    )


def _region_cards(report: Mapping[str, Any]) -> str:
    cards = [_region_card(region) for region in report.get("regions", ())]
    cards.extend(_unavailable_card(region) for region in report.get("unavailable_regions", ()))
    return "".join(cards)


def _region_card(region: Mapping[str, Any]) -> str:
    components = "".join(
        f"<li><strong>{escape(str(component['name']))}</strong>: "
        f"{component['value'] if component.get('value') is not None else 'unavailable'}"
        f" (confidence {component.get('confidence', 0):.0%})</li>"
        for component in region.get("components", ())
    )
    missing = ", ".join(region.get("missing_components", ())) or "none"
    return (
        f"<article class='card'><h3>{escape(str(region['region_id']))}</h3>"
        f"<p class='card-score'>{region['pressure']:.1f}<span>/100 pressure</span></p>"
        f"<p>As of {escape(str(region['as_of']))}; overall confidence "
        f"{region['confidence']:.0%}.</p><ul>{components}</ul>"
        f"<p class='muted'>Missing: {escape(missing)}</p></article>"
    )


def _unavailable_card(region: Mapping[str, Any]) -> str:
    return (
        f"<article class='card unavailable'><h3>{escape(str(region['region_id']))}</h3>"
        f"<p>Unavailable</p><p class='muted'>{escape(str(region['reason']))}</p></article>"
    )


def _company_row(company: Mapping[str, Any]) -> str:
    change = company.get("change_vs_prior_pct")
    change_text = "—" if change is None else f"{change:.1f}%"
    prior = company.get("prior_value")
    prior_text = "—" if prior is None else f"${prior:,.0f}"
    return (
        f"<tr><td>{escape(str(company['company']))}</td>"
        f"<td>${company['latest_value']:,.0f} "
        f"({escape(str(company['evidence_kind']))})</td>"
        f"<td>{prior_text}</td>"
        f"<td>{change_text}</td>"
        f"<td>{escape(str(company['latest_vintage']))}</td></tr>"
    )


def _css() -> str:
    return """body{margin:0;background:#f4f1ea;color:#222;font:16px/1.5 Georgia,serif}
main{max-width:1100px;margin:auto;padding:48px 24px}
h1{font-size:clamp(2.4rem,6vw,5rem);line-height:1;margin:12px 0 24px;max-width:800px}
h2{margin-top:56px;border-bottom:2px solid #222;padding-bottom:8px}
.eyebrow{font:700 12px/1.2 ui-monospace,monospace;letter-spacing:.12em;color:#b14b2f}
.lede{font-size:1.15rem;color:#555}
table{border-collapse:collapse;width:100%;background:#fff}
th,td{text-align:left;padding:12px;border-bottom:1px solid #ddd;vertical-align:top}
th{font:700 12px ui-monospace,monospace;text-transform:uppercase;background:#222;color:#fff}
section p{max-width:800px;color:#555}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.card{background:#fff;border:1px solid #ddd;padding:20px}
.card h3{margin-top:0;font:700 18px ui-monospace,monospace}
.card-score{font-size:2.6rem;margin:8px 0}.card-score span{font-size:.9rem;color:#777}
.card ul{padding-left:20px}.muted{color:#777}.unavailable{background:#eee}
.evidence-kind{font:700 11px ui-monospace,monospace;text-transform:uppercase;
padding:2px 5px;border-radius:3px}
.observed{background:#d7eadb}.estimated{background:#f6dfad}.inferred{background:#ded3ef}"""
