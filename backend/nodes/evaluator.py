"""
Evaluator node: rules-only quality gate after curator.
"""

from typing import Dict, Any, List

from backend.classes.state import CompetitorResearchState
from backend.classes.config import (
    QUALITY_THRESHOLDS,
    MAX_EVALUATOR_RETRIES,
    DIMENSION_LABELS_EN,
)
from backend.services import mongodb_service


def _evaluate_coverage(
    dim_stats: Dict[str, Dict[str, int]],
    companies: List[str],
    active_dimensions: List[str],
    min_docs: int,
    min_coverage: float,
) -> Dict[str, Dict[str, Any]]:
    report: Dict[str, Dict[str, Any]] = {}
    n_companies = max(len(companies), 1)

    for dim in active_dimensions:
        company_counts = dim_stats.get(dim, {})
        issues: List[str] = []

        companies_with_enough = sum(1 for c in companies if company_counts.get(c, 0) >= min_docs)
        coverage = companies_with_enough / n_companies

        if coverage < min_coverage:
            issues.append(
                f"Only {companies_with_enough}/{n_companies} companies have >= {min_docs} docs "
                f"({coverage:.0%} coverage, threshold {min_coverage:.0%})"
            )

        zero_doc = [c for c in companies if company_counts.get(c, 0) == 0]
        if zero_doc:
            issues.append(f"No docs for: {', '.join(zero_doc)}")

        if not issues:
            status = "pass"
        elif coverage >= 0.4:
            status = "warn"
        else:
            status = "fail"

        report[dim] = {"status": status, "coverage": round(coverage, 3), "issues": issues}

    return report


def _is_pricing_signal(text: str) -> bool:
    t = text.lower()
    tokens = (
        "pricing",
        "price",
        "usd",
        "eur",
        "$",
        "€",
        "/mo",
        "per seat",
        "quote",
        "rfq",
        "tier",
        "subscription",
        "license",
        "distributor",
    )
    return any(tok in t for tok in tokens)


def _pricing_evidence_check(
    pricing_docs: Dict[str, List[Dict[str, Any]]],
    companies: List[str],
) -> Dict[str, Any]:
    if not companies:
        return {"status": "warn", "issues": ["No companies to evaluate pricing evidence."], "unknown_ratio": 1.0}

    unknown_count = 0
    issues: List[str] = []
    evidence_mode_by_company: Dict[str, str] = {}

    for company in companies:
        docs = pricing_docs.get(company, []) or []
        has_public_price = False
        has_quote_signal = False

        for doc in docs:
            text = f"{doc.get('title', '')} {doc.get('content', '')}"
            if not _is_pricing_signal(text):
                continue
            lower = text.lower()
            if any(x in lower for x in ("$", "€", "usd", "eur", "/mo", "per seat", "per month")):
                has_public_price = True
            if any(x in lower for x in ("quote", "rfq", "contact sales", "request pricing")):
                has_quote_signal = True

        if has_public_price:
            evidence_mode_by_company[company] = "public_price"
        elif has_quote_signal:
            evidence_mode_by_company[company] = "quote_based"
        else:
            evidence_mode_by_company[company] = "unknown"
            unknown_count += 1

    unknown_ratio = unknown_count / max(len(companies), 1)
    if unknown_ratio >= 0.75:
        status = "fail"
        issues.append(
            f"Pricing evidence mostly unknown ({unknown_count}/{len(companies)} companies). "
            "Public pricing unavailable for most competitors."
        )
    elif unknown_ratio >= 0.5:
        status = "warn"
        issues.append(
            f"Pricing evidence partially missing ({unknown_count}/{len(companies)} companies). "
            "Prefer explicit quote-based evidence and mark gaps."
        )
    else:
        status = "pass"

    if any(v == "quote_based" for v in evidence_mode_by_company.values()) and status != "fail":
        issues.append("Quote-based procurement appears common; avoid direct numeric equivalence without caveats.")

    return {
        "status": status,
        "issues": issues,
        "unknown_ratio": round(unknown_ratio, 3),
        "evidence_mode_by_company": evidence_mode_by_company,
    }


async def evaluator_node(state: CompetitorResearchState) -> Dict[str, Any]:
    curation_stats: Dict[str, Any] = state.get("curation_stats", {})
    active_dimensions: List[str] = state.get("active_dimensions", [])
    all_companies: List[Dict[str, Any]] = state.get("all_companies", [])
    retry_count: int = state.get("retry_count", 0)
    curated_ref: str = state.get("curated_ref", "")

    companies = [c["name"] for c in all_companies]
    dim_stats = curation_stats.get("dim_stats", {})
    total_in = curation_stats.get("total_docs_in", 0)
    total_out = curation_stats.get("total_docs_out", 0)

    min_docs = QUALITY_THRESHOLDS["min_docs_per_dimension"]
    min_coverage = QUALITY_THRESHOLDS["min_companies_coverage"]

    events: List[Dict[str, Any]] = []
    quality_flags: List[Dict[str, Any]] = list(state.get("quality_flags", []) or [])

    eval_report = _evaluate_coverage(dim_stats, companies, active_dimensions, min_docs, min_coverage)

    # Pricing-specific stricter path.
    if "product_pricing" in active_dimensions and curated_ref:
        try:
            pricing_docs = await mongodb_service.get_dimension_data(curated_ref, "product_pricing", companies)
            pricing_check = _pricing_evidence_check(pricing_docs, companies)
        except Exception:
            pricing_check = {
                "status": "warn",
                "issues": ["Pricing evidence check skipped due to storage read failure."],
                "unknown_ratio": 1.0,
                "evidence_mode_by_company": {},
            }

        pricing_report = eval_report.get("product_pricing", {"status": "warn", "coverage": 0.0, "issues": []})
        pricing_report["pricing_unknown_ratio"] = pricing_check["unknown_ratio"]
        pricing_report["evidence_mode_by_company"] = pricing_check["evidence_mode_by_company"]
        pricing_report["issues"] = list(pricing_report.get("issues", [])) + list(pricing_check["issues"])

        current_status = pricing_report.get("status", "warn")
        if pricing_check["status"] == "fail":
            pricing_report["status"] = "fail"
            quality_flags.append(
                {
                    "severity": "fail",
                    "code": "PRICING_EVIDENCE_INSUFFICIENT",
                    "message": "Pricing evidence is mostly unknown; retry product_pricing research.",
                    "dimension": "product_pricing",
                }
            )
        elif pricing_check["status"] == "warn" and current_status == "pass":
            pricing_report["status"] = "warn"
            quality_flags.append(
                {
                    "severity": "warn",
                    "code": "PRICING_EVIDENCE_PARTIAL",
                    "message": "Pricing evidence is partially missing; report should mark data gaps clearly.",
                    "dimension": "product_pricing",
                }
            )

        eval_report["product_pricing"] = pricing_report

    # ── Per-company thin-data detection ──────────────────────────────────────
    # If a company is missing enough docs across most active dimensions, flag it
    # so the editor can add an explicit data-limitation note for that company.
    thin_threshold_dims = max(2, len(active_dimensions) // 2)  # >50% dims thin
    for company in companies:
        thin_dims = [
            d for d in active_dimensions
            if dim_stats.get(d, {}).get(company, 0) < min_docs
        ]
        if len(thin_dims) >= thin_threshold_dims:
            dim_labels = ", ".join(DIMENSION_LABELS_EN.get(d, d) for d in thin_dims)
            quality_flags.append(
                {
                    "severity": "warn",
                    "code": "COMPANY_THIN_DATA",
                    "message": (
                        f"{company} has sparse research data across "
                        f"{len(thin_dims)}/{len(active_dimensions)} dimensions "
                        f"({dim_labels}). Claims about this company may have lower confidence."
                    ),
                    "dimension": None,
                }
            )

    failed_dims = [d for d, r in eval_report.items() if r["status"] == "fail"]
    warn_dims = [d for d, r in eval_report.items() if r["status"] == "warn"]

    for dim, result in eval_report.items():
        label = DIMENSION_LABELS_EN.get(dim, dim)
        issues = "; ".join(result.get("issues", [])) if result.get("issues") else "OK"
        events.append(
            {
                "type": "status",
                "node": "evaluator",
                "dimension": dim,
                "message": f"{label}: {result['status'].upper()} - {issues}",
            }
        )

    can_retry = retry_count < MAX_EVALUATOR_RETRIES
    should_retry = bool(failed_dims) and can_retry
    evaluation_passed = not bool(failed_dims)
    retry_dimensions = failed_dims if should_retry else []

    if evaluation_passed:
        summary = (
            f"Quality gate PASSED - {total_out}/{total_in} docs kept"
            + (f"; {len(warn_dims)} dimension(s) warned" if warn_dims else "")
        )
    elif should_retry:
        summary = (
            f"Quality gate FAILED - retrying {', '.join(failed_dims)} "
            f"(attempt {retry_count + 1}/{MAX_EVALUATOR_RETRIES + 1})"
        )
    else:
        summary = (
            f"Quality gate FAILED with {len(failed_dims)} dimension(s), no retries left; "
            "continuing with partial data."
        )
        evaluation_passed = True

    events.append({"type": "status", "node": "evaluator", "message": summary})

    return {
        "evaluation_passed": evaluation_passed,
        "evaluation_report": eval_report,
        "retry_dimensions": retry_dimensions,
        "retry_count": retry_count + (1 if should_retry else 0),
        "quality_flags": quality_flags,
        "events": events,
    }
