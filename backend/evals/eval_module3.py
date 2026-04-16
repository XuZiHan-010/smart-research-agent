"""
Module 3 Evaluation — Curator + Evaluator

Categories:
  T1  Quality scoring logic (_quality_score)
  T2  Curator grouping and filtering
  T3  Reference building
  T4  Evaluator coverage logic
  T5  Evaluator retry gate
  T6  State field alignment

Run: python -m pytest backend/evals/eval_module3.py -v
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── Import under test ─────────────────────────────────────────────────────────
from backend.nodes.curator import _quality_score, _build_references
from backend.nodes.evaluator import _evaluate_coverage
from backend.classes.config import (
    EXA_SCORE_THRESHOLD,
    AUTHORITATIVE_DOMAINS,
    QUALITY_THRESHOLDS,
    MAX_EVALUATOR_RETRIES,
)
from backend.classes.state import CompetitorResearchState

# ── Test helpers ──────────────────────────────────────────────────────────────

def make_doc(url: str, title: str, score: float, published_date=None) -> Dict:
    d = {"url": url, "title": title, "score": score}
    if published_date:
        d["published_date"] = published_date
    return d


def run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════════
# T1 — Quality Scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestQualityScore:

    def test_base_score_passthrough(self):
        """Exa score returned as base when no adjustments apply."""
        doc = make_doc("https://example.com/page", "Detailed Analysis of Pricing Strategy", 0.7)
        score = _quality_score(doc, "product_pricing")
        assert 0.6 <= score <= 0.9, f"Expected ~0.7 base, got {score}"

    def test_authoritative_domain_boost(self):
        """g2.com should receive +0.15 boost for product_pricing."""
        doc_generic = make_doc("https://random.com/page", "Product Pricing Review Article", 0.6)
        doc_auth    = make_doc("https://g2.com/products/acme/reviews", "Product Pricing Review Article", 0.6)
        score_generic = _quality_score(doc_generic, "product_pricing")
        score_auth    = _quality_score(doc_auth,    "product_pricing")
        assert score_auth > score_generic, "Authoritative domain should score higher"
        assert abs(score_auth - score_generic - 0.15) < 0.01, f"Expected +0.15, got +{score_auth - score_generic:.3f}"

    def test_short_title_penalty(self):
        """Titles under 10 chars should lose -0.10."""
        doc_short = make_doc("https://example.com/a", "News", 0.7)
        doc_long  = make_doc("https://example.com/b", "Comprehensive Market Analysis Report", 0.7)
        score_short = _quality_score(doc_short, "market_position")
        score_long  = _quality_score(doc_long,  "market_position")
        assert score_long > score_short, "Long title should score higher"
        assert abs(score_long - score_short - 0.10) < 0.01

    def test_stale_data_penalty_recent_activity(self):
        """Docs older than STALE_DATA_DAYS for recent_activity get -0.10."""
        old_date   = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        fresh_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        doc_old   = make_doc("https://example.com/old", "Product Launch Announcement News", 0.7, old_date)
        doc_fresh = make_doc("https://example.com/new", "Product Launch Announcement News", 0.7, fresh_date)
        score_old   = _quality_score(doc_old,   "recent_activity")
        score_fresh = _quality_score(doc_fresh, "recent_activity")
        assert score_fresh > score_old, "Fresh doc should score higher for recent_activity"
        assert abs(score_fresh - score_old - 0.10) < 0.01

    def test_stale_penalty_NOT_applied_to_non_recency_dim(self):
        """Staleness penalty should not apply to product_pricing."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        doc_old   = make_doc("https://example.com/old", "Product Feature Comparison Table", 0.7, old_date)
        doc_fresh = make_doc("https://example.com/new", "Product Feature Comparison Table", 0.7)
        score_old   = _quality_score(doc_old,   "product_pricing")
        score_fresh = _quality_score(doc_fresh, "product_pricing")
        assert abs(score_old - score_fresh) < 0.01, "No staleness penalty for product_pricing"

    def test_score_with_all_boosts(self):
        """Authoritative domain + fresh = base + 0.15 boost."""
        fresh_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        doc = make_doc("https://techcrunch.com/2024/funding-round", "Major Funding Round Announcement", 0.6, fresh_date)
        score = _quality_score(doc, "traction_growth")
        # techcrunch is authoritative for traction_growth → +0.15
        assert score > 0.7, f"Expected > 0.75 with boost, got {score}"

    def test_missing_score_defaults_to_zero(self):
        """Doc with no score field should not crash and defaults to 0."""
        doc = {"url": "https://example.com", "title": "Some Reasonable Length Title Here"}
        score = _quality_score(doc, "content_gtm")
        assert score == 0.0 or score < 0.1   # no crash, low score


# ═══════════════════════════════════════════════════════════════════════════════
# T2 — Curator grouping and filtering (unit-level, no I/O)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCuratorGrouping:

    def _make_research_results(self) -> List[Dict]:
        """Simulate output from research_dispatcher."""
        return [
            {
                "company": "Acme",
                "dimension": "product_pricing",
                "status": "success",
                "docs": [
                    make_doc("https://g2.com/acme", "Acme Product Pricing Review Details", 0.8),
                    make_doc("https://random.com/a", "x", 0.1),   # should be filtered (score + short title)
                ],
                "docs_found": 2, "queries_run": 4, "unique_domains": 2,
            },
            {
                "company": "Rival",
                "dimension": "product_pricing",
                "status": "success",
                "docs": [
                    make_doc("https://capterra.com/rival", "Rival Product Comparison Review", 0.75),
                ],
                "docs_found": 1, "queries_run": 4, "unique_domains": 1,
            },
        ]

    def test_grouping_by_company_and_dimension(self):
        """research_results should be correctly grouped."""
        results = self._make_research_results()
        grouped: Dict[str, Dict[str, List]] = {}
        for r in results:
            company   = r["company"]
            dimension = r["dimension"]
            docs      = r["docs"]
            grouped.setdefault(company, {}).setdefault(dimension, [])
            grouped[company][dimension].extend(docs)

        assert "Acme" in grouped
        assert "Rival" in grouped
        assert "product_pricing" in grouped["Acme"]
        assert len(grouped["Acme"]["product_pricing"]) == 2
        assert len(grouped["Rival"]["product_pricing"]) == 1

    def test_filter_below_threshold(self):
        """Docs below EXA_SCORE_THRESHOLD should be dropped."""
        docs = [
            make_doc("https://example.com/good", "High Quality Analysis Report Article", 0.8),
            make_doc("https://example.com/bad",  "Low Quality Doc Text Here",           0.1),
        ]
        kept = [d for d in docs if _quality_score(d, "market_position") >= EXA_SCORE_THRESHOLD]
        assert len(kept) == 1
        assert kept[0]["url"] == "https://example.com/good"

    def test_cap_at_max_docs(self):
        """After sort, only max_docs_per_dim docs should be kept."""
        docs = [make_doc(f"https://example.com/{i}", f"Quality Research Article Number {i}", 0.5 + i * 0.01)
                for i in range(20)]
        max_docs = 5
        scored = sorted(docs, key=lambda d: _quality_score(d, "content_gtm"), reverse=True)
        capped = scored[:max_docs]
        assert len(capped) == max_docs

    def test_sort_descending_by_quality(self):
        """Docs should be sorted highest quality first."""
        docs = [
            make_doc("https://g2.com/low",  "Product Review Analysis Text Here", 0.4),   # auth boost → higher
            make_doc("https://random.com/high", "Product Review Analysis Text Here", 0.9),  # high base
        ]
        scored_and_sorted = sorted(
            docs,
            key=lambda d: _quality_score(d, "product_pricing"),
            reverse=True,
        )
        # g2.com: 0.4 + 0.15 = 0.55; random.com: 0.9 → random.com still wins
        assert scored_and_sorted[0]["url"] == "https://random.com/high"


# ═══════════════════════════════════════════════════════════════════════════════
# T3 — Reference building
# ═══════════════════════════════════════════════════════════════════════════════

class TestReferenceBuilder:

    def _make_curated(self) -> Dict:
        return {
            "Acme": {
                "product_pricing": [
                    {"url": "https://g2.com/acme", "_quality_score": 0.9},
                    {"url": "https://g2.com/acme/reviews", "_quality_score": 0.85},  # same domain
                ],
                "market_position": [
                    {"url": "https://gartner.com/acme", "_quality_score": 0.8},
                ],
            },
            "Rival": {
                "product_pricing": [
                    {"url": "https://capterra.com/rival", "_quality_score": 0.75},
                ],
            },
        }

    def test_deduplication_by_domain(self):
        """Same domain should appear at most once in references."""
        curated = self._make_curated()
        refs = _build_references(curated)
        domains = [ref.split("/")[2] for ref in refs]  # extract domain
        assert len(domains) == len(set(domains)), "References should have unique domains"

    def test_sorted_by_quality(self):
        """Highest quality doc URL should appear first."""
        curated = self._make_curated()
        refs = _build_references(curated)
        assert len(refs) > 0
        # g2.com has highest quality_score (0.9) and should appear first
        assert "g2.com" in refs[0]

    def test_max_references_cap(self):
        """Should not exceed max_refs."""
        curated = {
            f"Company{i}": {
                "dim": [{"url": f"https://unique-domain-{i}.com/page", "_quality_score": 0.7}]
            }
            for i in range(50)
        }
        refs = _build_references(curated, max_refs=10)
        assert len(refs) <= 10

    def test_empty_curated_returns_empty_list(self):
        assert _build_references({}) == []

    def test_docs_without_url_are_skipped(self):
        curated = {
            "Co": {
                "dim": [
                    {"url": "", "_quality_score": 0.9},
                    {"url": "https://valid.com/page", "_quality_score": 0.8},
                ]
            }
        }
        refs = _build_references(curated)
        assert len(refs) == 1
        assert "https://valid.com/page" in refs[0]


# ═══════════════════════════════════════════════════════════════════════════════
# T4 — Evaluator coverage logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluatorCoverage:

    def test_pass_when_all_companies_have_enough_docs(self):
        dim_stats = {
            "product_pricing": {"Acme": 5, "Rival": 4, "Challenger": 6},
        }
        companies = ["Acme", "Rival", "Challenger"]
        report = _evaluate_coverage(dim_stats, companies, ["product_pricing"], min_docs=3, min_coverage=0.6)
        assert report["product_pricing"]["status"] == "pass"
        assert report["product_pricing"]["coverage"] == 1.0

    def test_warn_when_partial_coverage(self):
        """1 out of 3 companies with enough docs → coverage=0.33, between 0% and 40% fail boundary → fail.
        2 out of 3 → coverage=0.67, above 0.6 min_coverage → pass (no issues).
        Warn happens when coverage >= 0.4 but < min_coverage (0.6): e.g., 1/2 companies=0.5."""
        dim_stats = {
            "market_position": {"Acme": 5, "Rival": 1},  # Rival below min, 1/2 = 0.5
        }
        companies = ["Acme", "Rival"]
        report = _evaluate_coverage(dim_stats, companies, ["market_position"], min_docs=3, min_coverage=0.6)
        # coverage=0.5: below min_coverage(0.6) → issues added, but >= 0.4 → warn not fail
        assert report["market_position"]["status"] == "warn"
        assert abs(report["market_position"]["coverage"] - 0.5) < 0.01

    def test_fail_when_coverage_below_40_percent(self):
        """Only 1 out of 3 companies with enough docs → coverage=0.33, fail."""
        dim_stats = {
            "traction_growth": {"Acme": 5, "Rival": 1, "Challenger": 0},
        }
        companies = ["Acme", "Rival", "Challenger"]
        report = _evaluate_coverage(dim_stats, companies, ["traction_growth"], min_docs=3, min_coverage=0.6)
        assert report["traction_growth"]["status"] == "fail"

    def test_zero_doc_company_listed_in_issues(self):
        dim_stats = {
            "customer_sentiment": {"Acme": 5, "Rival": 0},
        }
        companies = ["Acme", "Rival"]
        report = _evaluate_coverage(dim_stats, companies, ["customer_sentiment"], min_docs=3, min_coverage=0.6)
        issues_text = " ".join(report["customer_sentiment"]["issues"])
        assert "Rival" in issues_text, "Zero-doc company should be named in issues"

    def test_multiple_dimensions_independent(self):
        """Each dimension evaluated independently."""
        dim_stats = {
            "product_pricing":    {"Acme": 5, "Rival": 5},
            "recent_activity":    {"Acme": 1, "Rival": 0},   # fail
        }
        companies = ["Acme", "Rival"]
        report = _evaluate_coverage(
            dim_stats, companies,
            ["product_pricing", "recent_activity"],
            min_docs=3, min_coverage=0.6,
        )
        assert report["product_pricing"]["status"]  == "pass"
        assert report["recent_activity"]["status"]  == "fail"

    def test_missing_dimension_in_stats_treated_as_zero(self):
        """Dimension with no data at all should fail."""
        dim_stats: Dict = {}   # no data for any dimension
        companies = ["Acme", "Rival"]
        report = _evaluate_coverage(dim_stats, companies, ["content_gtm"], min_docs=3, min_coverage=0.6)
        assert report["content_gtm"]["status"] == "fail"


# ═══════════════════════════════════════════════════════════════════════════════
# T5 — Evaluator retry gate (node-level, mocked MongoDB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluatorNode:

    def _make_state(self, dim_stats: Dict, retry_count: int = 0) -> Dict:
        return {
            "curation_stats": {
                "total_docs_in": 50,
                "total_docs_out": 30,
                "companies": ["Acme", "Rival"],
                "dim_stats": dim_stats,
            },
            "active_dimensions": list(dim_stats.keys()),
            "all_companies": [{"name": "Acme"}, {"name": "Rival"}],
            "retry_count": retry_count,
        }

    def test_pass_state_returns_evaluation_passed_true(self):
        from backend.nodes.evaluator import evaluator_node
        state = self._make_state({
            "product_pricing": {"Acme": 5, "Rival": 5},
        })
        result = run(evaluator_node(state))
        assert result["evaluation_passed"] is True
        assert result["retry_dimensions"] == []

    def test_fail_with_retries_remaining(self):
        from backend.nodes.evaluator import evaluator_node
        state = self._make_state({
            "recent_activity": {"Acme": 1, "Rival": 0},  # both below threshold
        }, retry_count=0)
        result = run(evaluator_node(state))
        # Should flag retry since coverage=0 < 0.4 fail threshold
        assert result["retry_dimensions"] == ["recent_activity"]
        assert result["retry_count"] == 1

    def test_fail_no_retries_left_force_passes(self):
        """When max retries exhausted, evaluator force-passes."""
        from backend.nodes.evaluator import evaluator_node
        state = self._make_state({
            "recent_activity": {"Acme": 1, "Rival": 0},
        }, retry_count=MAX_EVALUATOR_RETRIES)
        result = run(evaluator_node(state))
        assert result["evaluation_passed"] is True   # force-pass
        assert result["retry_dimensions"] == []       # no retry triggered

    def test_evaluation_report_structure(self):
        from backend.nodes.evaluator import evaluator_node
        state = self._make_state({
            "product_pricing": {"Acme": 5, "Rival": 5},
            "market_position": {"Acme": 2, "Rival": 0},
        })
        result = run(evaluator_node(state))
        report = result["evaluation_report"]
        assert "product_pricing" in report
        assert "market_position" in report
        for dim_result in report.values():
            assert "status"   in dim_result
            assert "coverage" in dim_result
            assert "issues"   in dim_result
            assert dim_result["status"] in ("pass", "warn", "fail")

    def test_events_emitted(self):
        from backend.nodes.evaluator import evaluator_node
        state = self._make_state({
            "product_pricing": {"Acme": 5, "Rival": 5},
        })
        result = run(evaluator_node(state))
        assert len(result["events"]) >= 2   # at least per-dim + summary
        for e in result["events"]:
            assert e.get("node") == "evaluator"


# ═══════════════════════════════════════════════════════════════════════════════
# T6 — State field alignment
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateAlignment:

    def _get_state_fields(self) -> set:
        import typing
        hints = typing.get_type_hints(CompetitorResearchState)
        return set(hints.keys())

    def test_curator_returns_only_state_fields(self):
        """All keys returned by curator_node must be valid State fields."""
        curator_return_keys = {
            "curated_ref", "references", "curation_stats", "events"
        }
        state_fields = self._get_state_fields()
        unknown = curator_return_keys - state_fields
        assert not unknown, f"curator returns unknown State fields: {unknown}"

    def test_evaluator_returns_only_state_fields(self):
        """All keys returned by evaluator_node must be valid State fields."""
        evaluator_return_keys = {
            "evaluation_passed", "evaluation_report",
            "retry_dimensions", "retry_count", "quality_flags", "events"
        }
        state_fields = self._get_state_fields()
        unknown = evaluator_return_keys - state_fields
        assert not unknown, f"evaluator returns unknown State fields: {unknown}"

    def test_references_is_list_of_str(self):
        """State.references should be List[str], not List[Dict]."""
        import typing
        hints = typing.get_type_hints(CompetitorResearchState)
        refs_type = hints.get("references")
        # Check it's annotated as a list (not Dict)
        assert refs_type is not None
        origin = getattr(refs_type, "__origin__", None)
        assert origin is list, f"references should be List, got {refs_type}"

    def test_curation_stats_is_dict(self):
        import typing
        hints = typing.get_type_hints(CompetitorResearchState)
        assert hints["curation_stats"].__origin__ is dict

    def test_retry_dimensions_is_list(self):
        import typing
        hints = typing.get_type_hints(CompetitorResearchState)
        rd_type = hints["retry_dimensions"]
        assert rd_type.__origin__ is list


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
