"""
Battlecard validator node.

Runs lightweight rule checks after battlecard extraction and before editor:
  - competitor list normalization (avoid single comma-joined string)
  - feature matrix unknown-ratio check
  - pricing comparison unknown-ratio check (can trigger targeted retry)
  - win/lose theme contradiction heuristics per competitor
  - comparison payload sanity checks
"""

from typing import Dict, Any, List, Tuple

from backend.classes.state import CompetitorResearchState
from backend.classes.config import MAX_EVALUATOR_RETRIES


def _normalize_competitors(raw: Any) -> Tuple[List[str], bool]:
    if not isinstance(raw, list):
        return [], False
    if len(raw) == 1 and isinstance(raw[0], str) and "," in raw[0]:
        parts = [p.strip() for p in raw[0].split(",") if p.strip()]
        return parts, True
    clean = [str(x).strip() for x in raw if str(x).strip()]
    return clean, False


def _unknown_ratio_feature_matrix(feature_matrix: Any) -> float:
    if not isinstance(feature_matrix, list) or not feature_matrix:
        return 1.0
    total = 0
    unknown = 0
    for row in feature_matrix:
        companies = row.get("companies", {}) if isinstance(row, dict) else {}
        if not isinstance(companies, dict):
            continue
        for value in companies.values():
            total += 1
            if str(value).strip().lower() == "unknown":
                unknown += 1
    if total == 0:
        return 1.0
    return unknown / total


def _unknown_ratio_pricing(pricing_rows: Any) -> float:
    if not isinstance(pricing_rows, list) or not pricing_rows:
        return 1.0
    total = 0
    unknown = 0
    for row in pricing_rows:
        if not isinstance(row, dict):
            continue
        total += 1
        model = str(row.get("model", "")).strip().lower()
        entry = row.get("entry_price")
        enterprise = row.get("enterprise")
        if model in ("", "unknown", "null", "none") and not entry and not enterprise:
            unknown += 1
    if total == 0:
        return 1.0
    return unknown / total


def _detect_theme_conflicts(battlecard: Dict[str, Any]) -> List[str]:
    wins = battlecard.get("win_themes", [])
    loses = battlecard.get("lose_themes", [])
    if not isinstance(wins, list) or not isinstance(loses, list):
        return []

    index: Dict[str, List[str]] = {}
    for item in wins:
        if not isinstance(item, dict):
            continue
        comp = str(item.get("vs_competitor", "")).strip().lower()
        theme = str(item.get("theme", "")).strip().lower()
        if comp and theme:
            index.setdefault(comp, []).append(theme)

    conflicts: List[str] = []
    for item in loses:
        if not isinstance(item, dict):
            continue
        comp = str(item.get("vs_competitor", "")).strip().lower()
        lose_theme = str(item.get("theme", "")).strip().lower()
        if not comp or not lose_theme:
            continue
        for win_theme in index.get(comp, []):
            # Simple contradiction heuristic: overlapping themes indicate likely direction flip.
            overlap = set(win_theme.split()) & set(lose_theme.split())
            if len(overlap) >= 2:
                conflicts.append(comp)
                break
    return sorted(set(conflicts))


def _dedupe_flags(flags: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for flag in flags:
        key = (flag.get("severity"), flag.get("code"), flag.get("dimension"), flag.get("message"))
        if key in seen:
            continue
        seen.add(key)
        out.append(flag)
    return out


async def battlecard_validator_node(state: CompetitorResearchState) -> Dict[str, Any]:
    battlecard = state.get("battlecard_data", {}) or {}
    comparisons = state.get("comparisons", {}) or {}
    active_dims = state.get("active_dimensions", []) or []
    research_scope = state.get("research_scope", {}) or {}
    competitor_rationale = state.get("competitor_rationale", {}) or {}
    retry_count = int(state.get("retry_count", 0) or 0)

    checks: List[Dict[str, Any]] = []
    quality_flags: List[Dict[str, Any]] = list(state.get("quality_flags", []) or [])
    retry_dimensions: List[str] = []
    events: List[Dict[str, Any]] = []

    competitors, fixed_competitors = _normalize_competitors(battlecard.get("competitors", []))
    if fixed_competitors:
        battlecard["competitors"] = competitors
        quality_flags.append({
            "severity": "warn",
            "code": "BATTLECARD_COMPETITOR_STRING",
            "message": "Normalized comma-joined competitor string into list.",
        })
    checks.append({
        "code": "competitor_list_shape",
        "passed": bool(competitors),
        "detail": f"count={len(competitors)}",
    })

    profiles = battlecard.get("competitor_profiles", [])
    profiles_ok = isinstance(profiles, list) and all(
        isinstance(p, dict) and p.get("name") for p in profiles
    )
    checks.append({
        "code": "competitor_profiles_shape",
        "passed": profiles_ok,
        "detail": f"count={len(profiles) if isinstance(profiles, list) else 0}",
    })
    if not profiles_ok:
        quality_flags.append({
            "severity": "warn",
            "code": "COMPETITOR_PROFILES_INVALID",
            "message": "competitor_profiles missing or malformed.",
        })

    feature_unknown_ratio = _unknown_ratio_feature_matrix(battlecard.get("feature_matrix", []))
    feature_ok = feature_unknown_ratio <= 0.65
    checks.append({
        "code": "feature_unknown_ratio",
        "passed": feature_ok,
        "detail": f"unknown_ratio={feature_unknown_ratio:.2f}",
    })
    if not feature_ok:
        quality_flags.append({
            "severity": "warn",
            "code": "FEATURE_MATRIX_TOO_MANY_UNKNOWNS",
            "message": f"Feature matrix unknown ratio is high ({feature_unknown_ratio:.0%}).",
        })

    pricing_unknown_ratio = _unknown_ratio_pricing(battlecard.get("pricing_comparison", []))
    pricing_ok = pricing_unknown_ratio <= 0.70
    pricing_rows = battlecard.get("pricing_comparison", [])
    pricing_shape_ok = isinstance(pricing_rows, list) and all(
        isinstance(r, dict) and "company" in r for r in pricing_rows
    )
    checks.append({
        "code": "pricing_unknown_ratio",
        "passed": pricing_ok,
        "detail": f"unknown_ratio={pricing_unknown_ratio:.2f}",
    })
    checks.append({
        "code": "pricing_shape",
        "passed": pricing_shape_ok,
        "detail": f"rows={len(pricing_rows) if isinstance(pricing_rows, list) else 0}",
    })
    if not pricing_shape_ok:
        quality_flags.append({
            "severity": "warn",
            "code": "PRICING_STRUCTURE_INVALID",
            "message": "pricing_comparison structure is invalid or incomplete.",
            "dimension": "product_pricing",
        })
    if not pricing_ok:
        if "product_pricing" in active_dims:
            quality_flags.append({
                "severity": "fail",
                "code": "PRICING_TOO_MANY_UNKNOWNS",
                "message": f"Pricing comparison has too many unknown entries ({pricing_unknown_ratio:.0%}).",
                "dimension": "product_pricing",
            })
            retry_dimensions.append("product_pricing")
        else:
            quality_flags.append({
                "severity": "info",
                "code": "PRICING_NOT_RESEARCHED",
                "message": "Pricing data sparse (not an active dimension for this report type).",
                "dimension": "product_pricing",
            })

    conflicts = _detect_theme_conflicts(battlecard)
    conflict_ok = len(conflicts) == 0
    checks.append({
        "code": "win_lose_conflicts",
        "passed": conflict_ok,
        "detail": "none" if conflict_ok else ", ".join(conflicts),
    })
    if conflicts:
        quality_flags.append({
            "severity": "fail",
            "code": "WIN_LOSE_THEME_CONFLICT",
            "message": f"Potential win/lose contradiction for: {', '.join(conflicts)}.",
        })

    comparisons_ok = isinstance(comparisons, dict) and len(comparisons) > 0
    checks.append({
        "code": "comparison_payload",
        "passed": comparisons_ok,
        "detail": f"dimensions={len(comparisons) if isinstance(comparisons, dict) else 0}",
    })
    if not comparisons_ok:
        quality_flags.append({
            "severity": "fail",
            "code": "EMPTY_COMPARISONS",
            "message": "No comparison content available for report compilation.",
        })

    lens = str(research_scope.get("lens", ""))
    threat_types = {
        str(v.get("threat_type", "")).strip()
        for v in competitor_rationale.values()
        if isinstance(v, dict)
    }
    cross_mix_risk = lens == "multi_business_mix" and len({t for t in threat_types if t}) >= 2
    checks.append({
        "code": "cross_business_unit_mix",
        "passed": not cross_mix_risk,
        "detail": f"lens={lens}, threat_types={sorted(threat_types)}",
    })
    if cross_mix_risk:
        quality_flags.append({
            "severity": "warn",
            "code": "CROSS_BUSINESS_UNIT_MIX",
            "message": "Potential cross-business-unit comparison detected; conclusions may mix non-comparable units.",
        })

    blocking_fail = any(f.get("severity") == "fail" for f in quality_flags)
    can_retry = retry_count < MAX_EVALUATOR_RETRIES
    should_retry = blocking_fail and bool(retry_dimensions) and can_retry

    validation_report = {
        "should_retry": should_retry,
        "retry_dimensions": retry_dimensions if should_retry else [],
        "checks": checks,
        "summary": (
            "Validator requested targeted retry."
            if should_retry
            else "Validator passed with warnings." if quality_flags else "Validator passed."
        ),
    }

    events.append({
        "type": "status",
        "node": "battlecard_validator",
        "message": validation_report["summary"],
    })

    if should_retry:
        events.append({
            "type": "status",
            "node": "battlecard_validator",
            "message": (
                f"Retrying dimensions: {', '.join(validation_report['retry_dimensions'])} "
                f"(attempt {retry_count + 1}/{MAX_EVALUATOR_RETRIES + 1})"
            ),
        })

    return {
        "battlecard_data": battlecard,
        "quality_flags": _dedupe_flags(quality_flags),
        "validation_report": validation_report,
        "retry_dimensions": validation_report["retry_dimensions"],
        "retry_count": retry_count + (1 if should_retry else 0),
        "events": events,
    }
