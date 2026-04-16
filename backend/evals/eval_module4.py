"""
Module 4 Evaluation — Comparator + Battlecard Builder + Editor + Output Formatter

Categories:
  T1  Prompt coverage — all 6 dimensions have comparator prompts
  T2  Context formatting — _format_dimension_data, _bundle_comparisons
  T3  Battlecard JSON parsing — _safe_parse_json
  T4  Battlecard builder — metadata stamping, empty fallback
  T5  Editor context formatting — comparisons, battlecard summary, references
  T6  Output formatter — markdown passthrough, JSON schema
  T7  State field alignment — all new node return keys exist in State

Run: python -m pytest backend/evals/eval_module4.py -v
"""

import asyncio
import json
import sys
import os
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── Imports under test ────────────────────────────────────────────────────────
from backend.prompts import DIMENSION_COMPARATOR_PROMPTS, BATTLECARD_PROMPT, \
    EDITOR_COMPILE_PROMPT, EDITOR_EDIT_PROMPT
from backend.classes.config import AVAILABLE_DIMENSIONS, DIMENSION_LABELS_EN
from backend.classes.state import CompetitorResearchState
from backend.nodes.comparator import _format_dimension_data
from backend.nodes.battlecard_builder import (
    _bundle_comparisons, _parse_json as _safe_parse_json,
)
from backend.nodes.editor import (
    _format_comparisons, _format_battlecard_summary, _format_references,
)
from backend.nodes.output_formatter import _to_json


def run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════════
# T1 — Prompt coverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromptCoverage:

    def test_all_dimensions_have_comparator_prompt(self):
        """Every AVAILABLE_DIMENSION must have a comparator prompt."""
        missing = [d for d in AVAILABLE_DIMENSIONS if d not in DIMENSION_COMPARATOR_PROMPTS]
        assert not missing, f"Missing comparator prompts for: {missing}"

    def test_comparator_prompts_have_required_variables(self):
        """Each comparator prompt must accept target_company, competitors,
        comparator_focus, dimension_data."""
        required_vars = {
            "target_company",
            "competitors",
            "comparator_focus",
            "dimension_data",
            "comparison_basis",
            "competitor_rationale_text",
        }
        for dim, prompt in DIMENSION_COMPARATOR_PROMPTS.items():
            # Get input variables from the prompt template
            try:
                vars_in_prompt = set(prompt.input_variables)
            except AttributeError:
                # ChatPromptTemplate stores variables differently
                vars_in_prompt = set()
                for msg in prompt.messages:
                    if hasattr(msg, "prompt"):
                        vars_in_prompt |= set(msg.prompt.input_variables)
            missing = required_vars - vars_in_prompt
            assert not missing, f"{dim} prompt missing variables: {missing}"

    def test_battlecard_prompt_exists(self):
        assert BATTLECARD_PROMPT is not None

    def test_editor_compile_prompt_exists(self):
        assert EDITOR_COMPILE_PROMPT is not None

    def test_editor_edit_prompt_exists(self):
        assert EDITOR_EDIT_PROMPT is not None


# ═══════════════════════════════════════════════════════════════════════════════
# T2 — Context formatting
# ═══════════════════════════════════════════════════════════════════════════════

class TestContextFormatting:

    def _make_company_docs(self) -> Dict[str, List[Dict]]:
        return {
            "Acme": [
                {"url": "https://g2.com/acme", "title": "Acme Review", "content": "A" * 500},
                {"url": "https://acme.com",    "title": "Acme Home",   "content": "B" * 300},
            ],
            "Rival": [
                {"url": "https://rival.com", "title": "Rival Home", "content": "C" * 600},
            ],
        }

    def test_format_dimension_data_includes_all_companies(self):
        docs = self._make_company_docs()
        result = _format_dimension_data(docs, target_company="Acme", all_company_names=["Acme", "Rival"])
        assert "### Acme"  in result
        assert "### Rival" in result

    def test_format_dimension_data_respects_max_chars(self):
        docs = self._make_company_docs()
        result = _format_dimension_data(docs, target_company="Acme", all_company_names=["Acme", "Rival"], max_chars=200)
        # Should be much shorter than the full content (500+300+600 = 1400 raw chars)
        assert len(result) <= 900   # some overhead for headers/URLs/separators is expected

    def test_format_dimension_data_includes_url(self):
        docs = self._make_company_docs()
        result = _format_dimension_data(docs, target_company="Acme", all_company_names=["Acme", "Rival"])
        assert "g2.com" in result

    def test_format_dimension_data_empty_returns_empty(self):
        result = _format_dimension_data({}, target_company="Acme", all_company_names=["Acme"])
        assert result != ""   # empty input still renders a "no data" placeholder

    def test_bundle_comparisons_includes_all_dims(self):
        comparisons = {
            "product_pricing":    "Product pricing narrative text here",
            "market_position":    "Market position narrative text here",
            "customer_sentiment": "Customer sentiment narrative text here",
        }
        active = ["product_pricing", "market_position", "customer_sentiment"]
        result = _bundle_comparisons(comparisons, active)
        assert "Product & Pricing" in result or "product_pricing" in result.lower()
        assert "Market Position"   in result or "market_position" in result.lower()

    def test_bundle_comparisons_respects_max_chars(self):
        comparisons = {dim: "X" * 10_000 for dim in AVAILABLE_DIMENSIONS}
        result = _bundle_comparisons(comparisons, AVAILABLE_DIMENSIONS, max_chars=5_000)
        assert len(result) <= 8_000   # some overhead for section headers

    def test_bundle_comparisons_empty_returns_fallback(self):
        result = _bundle_comparisons({}, [], max_chars=1000)
        assert "No comparison data" in result


# ═══════════════════════════════════════════════════════════════════════════════
# T3 — Battlecard JSON parsing
# ═══════════════════════════════════════════════════════════════════════════════

class TestBattlecardJsonParsing:

    def _valid_battlecard_json(self) -> str:
        return json.dumps({
            "feature_matrix": [
                {"feature": "SSO", "companies": {"Acme": "yes", "Rival": "no"}}
            ],
            "pricing_comparison": [
                {"company": "Acme", "model": "per-seat", "entry_price": "$29/mo", "enterprise": "custom"}
            ],
            "win_themes": [
                {"vs_competitor": "Rival", "theme": "Better UX", "evidence": "G2 rating 4.8"}
            ],
            "lose_themes": [],
            "key_risks": ["Market saturation", "Pricing pressure"],
            "objection_handlers": [],
        })

    def test_parse_clean_json(self):
        raw = self._valid_battlecard_json()
        result = _safe_parse_json(raw)
        assert "feature_matrix" in result
        assert len(result["feature_matrix"]) == 1

    def test_parse_json_with_markdown_fences(self):
        raw = "```json\n" + self._valid_battlecard_json() + "\n```"
        result = _safe_parse_json(raw)
        assert "feature_matrix" in result

    def test_parse_invalid_json_returns_fallback(self):
        result = _safe_parse_json("this is not json at all")
        assert "parse_error" in result
        assert "raw_response" in result

    def test_parse_empty_string_returns_fallback(self):
        result = _safe_parse_json("")
        assert "parse_error" in result

    def test_parse_json_no_fence_prefix(self):
        raw = "```\n" + self._valid_battlecard_json() + "\n```"
        result = _safe_parse_json(raw)
        # Should strip fences regardless of json vs no-language marker
        assert not result.get("parse_error"), f"Got parse error: {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# T4 — Battlecard builder node (mocked LLM)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBattlecardBuilderNode:

    def _make_state(self) -> Dict:
        return {
            "comparisons": {
                "product_pricing": "Acme has better pricing. Rival charges more.",
                "market_position": "Acme leads in SMB. Rival dominates enterprise.",
            },
            "active_dimensions": ["product_pricing", "market_position"],
            "target_company": "Acme",
            "all_companies": [{"name": "Acme"}, {"name": "Rival"}],
            "curated_ref": "",   # empty — skip MongoDB write
        }

    def test_empty_comparisons_returns_empty_battlecard(self):
        from backend.nodes.battlecard_builder import battlecard_builder_node
        state = self._make_state()
        state["comparisons"] = {}
        result = run(battlecard_builder_node(state))
        bc = result["battlecard_data"]
        assert bc["target"] == "Acme"
        assert bc["feature_matrix"] == []

    def test_metadata_always_stamped(self):
        """Even with LLM mocked, metadata must be present."""
        from backend.nodes.battlecard_builder import battlecard_builder_node
        state = self._make_state()

        mock_chain_result = json.dumps({
            "feature_matrix": [], "pricing_comparison": [], "win_themes": [],
            "lose_themes": [], "key_risks": [], "objection_handlers": [],
            "target": "Acme", "competitors": ["Rival"],
        })

        with patch("backend.nodes.battlecard_builder._get_llm") as mock_llm_fn:
            mock_llm = MagicMock()
            mock_chain = AsyncMock(return_value=mock_chain_result)
            # Chain is prompt | llm | parser — patch ainvoke at the chain level
            mock_llm_fn.return_value = mock_llm
            with patch("backend.nodes.battlecard_builder.BATTLECARD_PROMPT") as mock_prompt:
                mock_chain_obj = MagicMock()
                mock_chain_obj.__or__ = MagicMock(return_value=mock_chain_obj)
                mock_chain_obj.ainvoke = AsyncMock(return_value=mock_chain_result)
                mock_prompt.__or__ = MagicMock(return_value=mock_chain_obj)
                result = run(battlecard_builder_node(state))

        bc = result["battlecard_data"]
        assert "target"       in bc
        assert "competitors"  in bc
        assert "generated_at" in bc
        assert bc["target"] == "Acme"
        assert "Rival" in bc["competitors"]

    def test_events_emitted(self):
        from backend.nodes.battlecard_builder import battlecard_builder_node
        state = self._make_state()
        state["comparisons"] = {}   # trigger empty path
        result = run(battlecard_builder_node(state))
        assert len(result["events"]) >= 1
        for e in result["events"]:
            assert e.get("node") == "battlecard_builder"


# ═══════════════════════════════════════════════════════════════════════════════
# T5 — Editor context formatting
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditorFormatting:

    def test_format_comparisons_includes_labels(self):
        comparisons = {"product_pricing": "Detailed pricing analysis here..."}
        result = _format_comparisons(comparisons, ["product_pricing"])
        assert "Product & Pricing" in result

    def test_format_comparisons_respects_max_chars(self):
        comparisons = {dim: "X" * 50_000 for dim in AVAILABLE_DIMENSIONS}
        result = _format_comparisons(comparisons, AVAILABLE_DIMENSIONS, max_chars=10_000)
        assert len(result) <= 15_000   # some overhead for headers

    def test_format_comparisons_empty_returns_fallback(self):
        result = _format_comparisons({}, [])
        assert "No research comparisons" in result

    def test_format_battlecard_summary_with_data(self):
        bc = {
            "feature_matrix": [
                {"feature": "SSO", "companies": {"Acme": "yes", "Rival": "no"}},
            ],
            "win_themes": [
                {"vs_competitor": "Rival", "theme": "Better UX", "evidence": "G2 4.8 stars"},
            ],
            "lose_themes": [
                {"vs_competitor": "Rival", "theme": "Price", "evidence": "Rival 20% cheaper"},
            ],
            "key_risks": ["Market saturation"],
        }
        result = _format_battlecard_summary(bc)
        assert "SSO"      in result
        assert "Better UX" in result
        assert "Price"    in result

    def test_format_battlecard_summary_parse_error_fallback(self):
        result = _format_battlecard_summary({"parse_error": True})
        assert "No battlecard data" in result

    def test_format_references_numbered(self):
        refs = ["https://g2.com", "https://gartner.com"]
        result = _format_references(refs)
        assert "1. https://g2.com"     in result
        assert "2. https://gartner.com" in result

    def test_format_references_empty(self):
        result = _format_references([])
        assert "No references" in result


# ═══════════════════════════════════════════════════════════════════════════════
# T6 — Output formatter
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputFormatter:

    def _make_json_args(self) -> Dict:
        return dict(
            target_company  = "Acme",
            all_companies   = [{"name": "Acme"}, {"name": "Rival"}],
            active_dims     = ["product_pricing", "market_position"],
            comparisons     = {
                "product_pricing": "Acme has better pricing.",
                "market_position": "Acme leads SMB segment.",
            },
            dimension_evidence = {
                "product_pricing": {
                    "confidence": "medium",
                    "data_gaps": ["Public pricing unavailable for Rival"],
                    "comparison_basis": "Pricing motion and transparency",
                    "evidence": [],
                }
            },
            competitor_rationale = {
                "Rival": {"why_included": "Same ICP overlap", "threat_type": "direct_competitor"}
            },
            research_scope = {
                "lens": "single_business_unit",
                "comparison_basis": "B2B adhesives product/pricing overlap",
            },
            battlecard_data = {"feature_matrix": [], "win_themes": []},
            references      = ["https://g2.com", "https://gartner.com"],
            report          = "# Acme Report\n\nExecutive summary here.",
            report_type     = "full_analysis",
            depth           = "standard",
            quality_flags   = [],
            validation_report = {},
        )

    def test_json_output_has_required_top_keys(self):
        result = _to_json(**self._make_json_args())
        for key in ("metadata", "comparisons", "battlecard", "references", "report_markdown"):
            assert key in result, f"Missing key: {key}"
        assert "quality_flags" in result
        assert "validation_report" in result

    def test_json_metadata_correct(self):
        result = _to_json(**self._make_json_args())
        meta = result["metadata"]
        assert meta["target_company"] == "Acme"
        assert "Rival" in meta["competitors"]
        assert meta["report_type"] == "full_analysis"
        assert meta["depth"] == "standard"
        assert "research_date" in meta

    def test_json_comparisons_have_label_and_narrative(self):
        result = _to_json(**self._make_json_args())
        pp = result["comparisons"]["product_pricing"]
        assert "label"     in pp
        assert "narrative" in pp
        assert "evidence_bundle" in pp
        assert pp["narrative"] == "Acme has better pricing."

    def test_json_references_preserved(self):
        result = _to_json(**self._make_json_args())
        assert result["references"] == ["https://g2.com", "https://gartner.com"]

    def test_json_report_markdown_preserved(self):
        result = _to_json(**self._make_json_args())
        assert "# Acme Report" in result["report_markdown"]

    def test_formatter_node_markdown_passthrough(self):
        from backend.nodes.output_formatter import output_formatter_node
        state: Dict[str, Any] = {
            "output_format":    "markdown",
            "report":           "# My Report",
            "target_company":   "Acme",
            "all_companies":    [{"name": "Acme"}],
            "active_dimensions": [],
            "comparisons":      {},
            "battlecard_data":  {},
            "references":       [],
            "report_type":      "full_analysis",
            "depth":            "standard",
        }
        result = run(output_formatter_node(state))
        assert result["output"] == "# My Report"
        assert len(result["events"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# T7 — State field alignment
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateAlignment:

    def _state_fields(self) -> set:
        import typing
        return set(typing.get_type_hints(CompetitorResearchState).keys())

    def test_comparator_returns_valid_state_fields(self):
        keys = {"comparisons", "dimension_evidence", "events"}
        unknown = keys - self._state_fields()
        assert not unknown, f"comparator returns unknown fields: {unknown}"

    def test_battlecard_builder_returns_valid_state_fields(self):
        keys = {"battlecard_data", "events"}
        unknown = keys - self._state_fields()
        assert not unknown, f"battlecard_builder returns unknown fields: {unknown}"

    def test_editor_returns_valid_state_fields(self):
        keys = {"report", "events"}
        unknown = keys - self._state_fields()
        assert not unknown, f"editor returns unknown fields: {unknown}"

    def test_output_formatter_returns_valid_state_fields(self):
        keys = {"output", "events"}
        unknown = keys - self._state_fields()
        assert not unknown, f"output_formatter returns unknown fields: {unknown}"

    def test_edit_mode_field_in_state(self):
        assert "edit_mode" in self._state_fields()

    def test_edit_instruction_field_in_state(self):
        assert "edit_instruction" in self._state_fields()

    def test_report_version_field_in_state(self):
        assert "report_version" in self._state_fields()

    def test_comparisons_field_is_dict(self):
        import typing
        hints = typing.get_type_hints(CompetitorResearchState)
        assert hints["comparisons"].__origin__ is dict

    def test_battlecard_data_field_is_dict(self):
        import typing
        hints = typing.get_type_hints(CompetitorResearchState)
        assert hints["battlecard_data"].__origin__ is dict


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
