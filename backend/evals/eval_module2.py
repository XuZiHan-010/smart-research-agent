"""
Module 2 Evaluation — Researcher base + Grounding + Research Dispatcher + Collector

No API keys required — all Exa / LLM calls are mocked.

Categories:
  T1  BaseResearcher result schema
  T2  Researcher registry completeness
  T3  Deduplication and domain extraction
  T4  Grounding node paths (URL supplied vs auto-discover)
  T5  Research Dispatcher task fan-out
  T6  Research Dispatcher retry behaviour
  T7  Collector todo_state + collection_summary

Run:
  python -m pytest backend/evals/eval_module2.py -v
  # or without pytest:
  python -m backend.evals.eval_module2
"""

import asyncio
import sys
import os
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.nodes.researchers import RESEARCHER_REGISTRY
from backend.nodes.researchers.base import BaseResearcher, _extract_domain
from backend.classes.config import AVAILABLE_DIMENSIONS


def run(coro):
    return asyncio.run(coro)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_exa_result(url: str, score: float = 0.8, title: str = "Test Doc"):
    r = MagicMock()
    r.url            = url
    r.title          = title
    r.score          = score
    r.published_date = "2024-01-01"
    return r


def _make_exa_search_response(urls: List[str]):
    resp         = MagicMock()
    resp.results = [_make_exa_result(u) for u in urls]
    return resp


def _make_researcher(dimension: str) -> BaseResearcher:
    """Instantiate a real researcher class for the given dimension."""
    cls = RESEARCHER_REGISTRY[dimension]
    with patch("backend.nodes.researchers.base.ChatOpenAI"):
        return cls()


def _fake_generate_queries(company, n_queries, site_scrape):
    """Sync helper that returns n_queries fake queries."""
    return [f"{company} query {i}" for i in range(n_queries)]


# ═══════════════════════════════════════════════════════════════════════════════
# T1 — BaseResearcher result schema
# ═══════════════════════════════════════════════════════════════════════════════

class TestBaseResearcherSchema:

    REQUIRED_KEYS = {
        "status", "company", "dimension",
        "docs", "queries_run", "docs_found", "unique_domains",
        "error_code", "error_message",
    }

    def _mock_researcher(self, dimension="product_pricing") -> BaseResearcher:
        return _make_researcher(dimension)

    def test_success_result_has_all_keys(self):
        """A successful run must return a dict with all required keys."""
        researcher = self._mock_researcher()
        urls = [f"https://example{i}.com" for i in range(5)]

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(return_value=["q1", "q2"])):
                with patch.object(researcher, "_search_parallel",
                                  new=AsyncMock(return_value={
                                      u: {"url": u, "title": "T", "score": 0.7,
                                          "published_date": None}
                                      for u in urls
                                  })):
                    return await researcher.run("Acme", "", 2, 5)

        result = run(_run())
        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_success_status_when_3plus_docs(self):
        """≥3 docs → status = 'success'."""
        researcher = self._mock_researcher()
        urls = [f"https://ex{i}.com" for i in range(5)]

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(return_value=["q1"])):
                with patch.object(researcher, "_search_parallel",
                                  new=AsyncMock(return_value={
                                      u: {"url": u, "title": "T", "score": 0.8,
                                          "published_date": None}
                                      for u in urls
                                  })):
                    return await researcher.run("Acme", "", 1, 5)

        result = run(_run())
        assert result["status"] == "success", f"Expected success, got {result['status']}"

    def test_partial_status_when_fewer_than_3_docs(self):
        """<3 docs → status = 'partial'."""
        researcher = self._mock_researcher()
        urls = ["https://only-one.com"]

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(return_value=["q1"])):
                with patch.object(researcher, "_search_parallel",
                                  new=AsyncMock(return_value={
                                      u: {"url": u, "title": "T", "score": 0.7,
                                          "published_date": None}
                                      for u in urls
                                  })):
                    return await researcher.run("Acme", "", 1, 5)

        result = run(_run())
        assert result["status"] == "partial", f"Expected partial, got {result['status']}"

    def test_empty_status_when_no_docs(self):
        """No results from Exa → status = 'empty', error_code = 'NO_RESULTS'."""
        researcher = self._mock_researcher()

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(return_value=["q1"])):
                with patch.object(researcher, "_search_parallel",
                                  new=AsyncMock(return_value={})):
                    return await researcher.run("Acme", "", 1, 5)

        result = run(_run())
        assert result["status"] == "empty"
        assert result["error_code"] == "NO_RESULTS"
        assert result["docs"] == []

    def test_error_result_on_query_generation_failure(self):
        """Exception in query generation → status = 'error', error_code = 'EXCEPTION'."""
        researcher = self._mock_researcher()

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(side_effect=RuntimeError("LLM failed"))):
                return await researcher.run("Acme", "", 2, 5)

        result = run(_run())
        assert result["status"] == "error"
        assert result["error_code"] == "EXCEPTION"

    def test_docs_count_matches_docs_found(self):
        """docs_found must equal len(docs)."""
        researcher = self._mock_researcher()
        urls = [f"https://site{i}.com" for i in range(4)]

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(return_value=["q1"])):
                with patch.object(researcher, "_search_parallel",
                                  new=AsyncMock(return_value={
                                      u: {"url": u, "title": "T", "score": 0.8,
                                          "published_date": None}
                                      for u in urls
                                  })):
                    return await researcher.run("Acme", "", 1, 5)

        result = run(_run())
        assert result["docs_found"] == len(result["docs"]), \
            f"docs_found {result['docs_found']} != len(docs) {len(result['docs'])}"


# ═══════════════════════════════════════════════════════════════════════════════
# T2 — Researcher registry completeness
# ═══════════════════════════════════════════════════════════════════════════════

class TestResearcherRegistry:

    def test_all_dimensions_registered(self):
        """Every AVAILABLE_DIMENSION must have an entry in RESEARCHER_REGISTRY."""
        missing = [d for d in AVAILABLE_DIMENSIONS if d not in RESEARCHER_REGISTRY]
        assert not missing, f"Dimensions missing from registry: {missing}"

    def test_registry_dimension_matches_class_attribute(self):
        """Each registered class must declare a DIMENSION that matches its key."""
        mismatches = []
        for key, cls in RESEARCHER_REGISTRY.items():
            if cls.DIMENSION != key:
                mismatches.append(f"{key}: class.DIMENSION = '{cls.DIMENSION}'")
        assert not mismatches, f"DIMENSION mismatches: {mismatches}"

    def test_all_classes_are_subclasses_of_base(self):
        """Every researcher must extend BaseResearcher."""
        non_base = [
            k for k, cls in RESEARCHER_REGISTRY.items()
            if not issubclass(cls, BaseResearcher)
        ]
        assert not non_base, f"Not BaseResearcher subclasses: {non_base}"

    def test_all_classes_have_query_prompt(self):
        """Every researcher class must define a non-None QUERY_PROMPT."""
        missing_prompt = [
            k for k, cls in RESEARCHER_REGISTRY.items()
            if cls.QUERY_PROMPT is None
        ]
        assert not missing_prompt, f"Missing QUERY_PROMPT: {missing_prompt}"

    def test_no_extra_entries_in_registry(self):
        """Registry must not contain keys absent from AVAILABLE_DIMENSIONS."""
        extra = [k for k in RESEARCHER_REGISTRY if k not in AVAILABLE_DIMENSIONS]
        assert not extra, f"Extra registry keys not in AVAILABLE_DIMENSIONS: {extra}"


# ═══════════════════════════════════════════════════════════════════════════════
# T3 — Deduplication and domain extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeduplication:

    def test_duplicate_urls_deduped_keep_higher_score(self):
        """When the same URL appears from two queries, keep the higher-scored version."""
        researcher = _make_researcher("product_pricing")
        url = "https://g2.com/review"

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(return_value=["q1", "q2"])):
                call_count = 0

                async def mock_search(q, n, cfg):
                    nonlocal call_count
                    call_count += 1
                    # Same URL, different scores per query
                    score = 0.9 if call_count == 1 else 0.5
                    return {url: {"url": url, "title": "G2 Review", "score": score,
                                  "published_date": None}}

                with patch.object(researcher, "_search_single", new=mock_search):
                    return await researcher._attempt("Acme", "", 2, 3)

        result = run(_run())
        assert result["docs_found"] == 1, "Duplicate URL should be deduplicated"
        assert result["docs"][0]["score"] == 0.9, "Higher-scored version should be kept"

    def test_extract_domain_strips_www(self):
        assert _extract_domain("https://www.g2.com/reviews") == "g2.com"

    def test_extract_domain_handles_subdomains(self):
        result = _extract_domain("https://blog.notion.so/pricing")
        assert "notion.so" in result

    def test_extract_domain_handles_malformed(self):
        """Malformed URLs should not raise — return the input."""
        result = _extract_domain("not-a-url")
        assert isinstance(result, str)

    def test_unique_domains_counted_correctly(self):
        """unique_domains must count distinct domains, not URLs."""
        researcher = _make_researcher("product_pricing")
        docs_by_url = {
            "https://g2.com/r1":      {"url": "https://g2.com/r1",      "title": "A", "score": 0.8, "published_date": None},
            "https://g2.com/r2":      {"url": "https://g2.com/r2",      "title": "B", "score": 0.7, "published_date": None},
            "https://capterra.com/r1":{"url": "https://capterra.com/r1","title": "C", "score": 0.9, "published_date": None},
        }

        async def _run():
            with patch.object(researcher, "_generate_queries",
                              new=AsyncMock(return_value=["q1"])):
                with patch.object(researcher, "_search_parallel",
                                  new=AsyncMock(return_value=docs_by_url)):
                    return await researcher.run("Acme", "", 1, 5)

        result = run(_run())
        # 3 URLs but only 2 domains
        assert result["unique_domains"] == 2, \
            f"Expected 2 unique domains, got {result['unique_domains']}"


# ═══════════════════════════════════════════════════════════════════════════════
# T4 — Grounding node paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroundingNode:

    def _make_state(self, companies):
        return {"all_companies": companies}

    def test_empty_companies_returns_empty_scrapes(self):
        from backend.nodes.grounding import grounding_node
        result = run(grounding_node(self._make_state([])))
        assert result["site_scrapes"] == {}

    def test_url_provided_calls_scrape_url_not_search(self):
        """When website URL is given, _scrape_url must be called, not _find_and_scrape."""
        from backend.nodes.grounding import grounding_node
        state = self._make_state([{"name": "Notion", "website": "https://notion.so"}])

        with patch("backend.nodes.grounding._scrape_url",
                   new=AsyncMock(return_value="Notion scraped content")) as mock_scrape, \
             patch("backend.nodes.grounding._find_and_scrape",
                   new=AsyncMock(return_value="")) as mock_find:
            result = run(grounding_node(state))

        mock_scrape.assert_called_once()
        mock_find.assert_not_called()
        assert result["site_scrapes"]["Notion"] == "Notion scraped content"

    def test_no_url_calls_find_and_scrape(self):
        """When no website URL, _find_and_scrape must be called."""
        from backend.nodes.grounding import grounding_node
        state = self._make_state([{"name": "Obsidian", "website": ""}])

        with patch("backend.nodes.grounding._scrape_url",
                   new=AsyncMock(return_value="")) as mock_scrape, \
             patch("backend.nodes.grounding._find_and_scrape",
                   new=AsyncMock(return_value="Obsidian found content")) as mock_find:
            result = run(grounding_node(state))

        mock_find.assert_called_once()
        assert result["site_scrapes"]["Obsidian"] == "Obsidian found content"

    def test_grounding_failure_does_not_crash(self):
        """A scraping exception must not crash the node — it returns empty string."""
        from backend.nodes.grounding import grounding_node
        state = self._make_state([
            {"name": "Good", "website": "https://good.com"},
            {"name": "Bad",  "website": "https://bad.com"},
        ])

        async def _scrape(exa, url):
            if "bad" in url:
                raise RuntimeError("Network error")
            return "Good content"

        with patch("backend.nodes.grounding._scrape_url", new=_scrape):
            result = run(grounding_node(state))

        # Should still have the good company
        assert "Good" in result["site_scrapes"]

    def test_site_scrapes_keys_match_company_names(self):
        """site_scrapes keys must be company names (strings), not objects."""
        from backend.nodes.grounding import grounding_node
        companies = [
            {"name": "Alpha", "website": "https://alpha.com"},
            {"name": "Beta",  "website": ""},
        ]
        state = self._make_state(companies)

        with patch("backend.nodes.grounding._scrape_url",
                   new=AsyncMock(return_value="content")), \
             patch("backend.nodes.grounding._find_and_scrape",
                   new=AsyncMock(return_value="content")):
            result = run(grounding_node(state))

        scrape_keys = set(result["site_scrapes"].keys())
        expected    = {"Alpha", "Beta"}
        assert scrape_keys == expected, f"Expected {expected}, got {scrape_keys}"

    def test_events_contain_status_messages(self):
        """grounding_node must emit at least one status event per company + summary."""
        from backend.nodes.grounding import grounding_node
        state = self._make_state([{"name": "X", "website": "https://x.com"}])

        with patch("backend.nodes.grounding._scrape_url",
                   new=AsyncMock(return_value="some text")):
            result = run(grounding_node(state))

        events = result.get("events", [])
        assert len(events) >= 2, "Expected at least per-company event + summary event"
        assert all(e.get("type") == "status" for e in events)


# ═══════════════════════════════════════════════════════════════════════════════
# T5 — Research Dispatcher task fan-out
# ═══════════════════════════════════════════════════════════════════════════════

class TestResearchDispatcher:

    def _base_state(self, companies, dims, retry_dims=None):
        return {
            "all_company_names":  companies,
            "all_companies":      [{"name": c, "website": "", "source": "user"} for c in companies],
            "active_dimensions":  dims,
            "retry_dimensions":   retry_dims or [],
            "queries_per_dim":    2,
            "results_per_query":  3,
            "max_docs_per_dim":   5,
            "site_scrapes":       {c: "" for c in companies},
            "job_id":             "test-job-id",
            "events":             [],
        }

    def _make_fake_registry(self, dims: List[str], call_log: List):
        """
        Build a mock RESEARCHER_REGISTRY where each researcher records its
        (company, dimension) call in call_log.
        """
        registry = {}
        for dim in dims:
            _dim = dim  # capture loop variable

            async def fake_run(company, site_scrape, queries_per_dim,
                               results_per_query, _d=_dim):
                call_log.append((company, _d))
                return {
                    "status": "success", "company": company, "dimension": _d,
                    "docs": [], "queries_run": 2, "docs_found": 0,
                    "unique_domains": 0, "error_code": None, "error_message": None,
                }

            mock_cls = MagicMock(return_value=MagicMock(run=AsyncMock(side_effect=fake_run)))
            registry[_dim] = mock_cls
        return registry

    def test_correct_task_count_NxM(self):
        """N companies × M dimensions tasks must be spawned."""
        from backend.nodes.research_dispatcher import research_dispatcher_node

        companies = ["Alpha", "Beta"]
        dims      = ["product_pricing", "market_position", "traction_growth"]
        state     = self._base_state(companies, dims)
        call_log  = []

        with patch("backend.nodes.research_dispatcher.RESEARCHER_REGISTRY",
                   self._make_fake_registry(dims, call_log)):
            run(research_dispatcher_node(state))

        expected_count = len(companies) * len(dims)
        assert len(call_log) == expected_count, \
            f"Expected {expected_count} tasks, ran {len(call_log)}: {call_log}"

    def test_retry_runs_only_failed_dims(self):
        """When retry_dimensions is set, only those dims are dispatched."""
        from backend.nodes.research_dispatcher import research_dispatcher_node

        companies  = ["Alpha", "Beta"]
        all_dims   = ["product_pricing", "market_position", "traction_growth"]
        retry_dims = ["traction_growth"]
        state      = self._base_state(companies, all_dims, retry_dims=retry_dims)
        call_log   = []

        with patch("backend.nodes.research_dispatcher.RESEARCHER_REGISTRY",
                   self._make_fake_registry(all_dims, call_log)):
            run(research_dispatcher_node(state))

        # Only retry_dims × companies should run
        expected_count = len(companies) * len(retry_dims)
        assert len(call_log) == expected_count, \
            f"Expected {expected_count} retry tasks, ran {len(call_log)}: {call_log}"
        called_dims = {d for _, d in call_log}
        assert called_dims == set(retry_dims), \
            f"Expected dims {retry_dims}, got {called_dims}"


# ═══════════════════════════════════════════════════════════════════════════════
# T6 — Collector todo_state + collection_summary
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollector:

    def _make_research_result(self, company, dim, status, docs_found):
        return {
            "status": status, "company": company, "dimension": dim,
            "docs": [{"url": f"https://ex.com/{i}", "title": "T", "score": 0.8,
                      "published_date": None} for i in range(docs_found)],
            "queries_run": 2, "docs_found": docs_found,
            "unique_domains": docs_found, "error_code": None, "error_message": None,
        }

    def _base_state(self, research_results, companies, dims):
        return {
            "research_results":   research_results,
            "all_company_names":  companies,
            "active_dimensions":  dims,
            "job_id":             "test-job",
            "events":             [],
        }

    def test_todo_state_shape(self):
        """todo_state must be {company: {dim: {status, docs_found}}}."""
        from backend.nodes.collector import collector_node

        companies = ["Alpha", "Beta"]
        dims      = ["product_pricing", "traction_growth"]
        results   = [
            self._make_research_result("Alpha", "product_pricing", "success", 5),
            self._make_research_result("Alpha", "traction_growth", "partial", 2),
            self._make_research_result("Beta",  "product_pricing", "success", 4),
            self._make_research_result("Beta",  "traction_growth", "empty",   0),
        ]
        state  = self._base_state(results, companies, dims)
        output = run(collector_node(state))

        todo = output["todo_state"]
        for c in companies:
            assert c in todo, f"Company '{c}' missing from todo_state"
            for d in dims:
                assert d in todo[c], f"Dim '{d}' missing for company '{c}'"
                cell = todo[c][d]
                assert "status"    in cell, f"'status' key missing in todo_state[{c}][{d}]"
                assert "docs_found" in cell, f"'docs_found' key missing in todo_state[{c}][{d}]"

    def test_collection_summary_fields(self):
        """collection_summary must contain total_docs, total_companies, total_dimensions."""
        from backend.nodes.collector import collector_node

        results = [self._make_research_result("X", "product_pricing", "success", 3)]
        state   = self._base_state(results, ["X"], ["product_pricing"])
        output  = run(collector_node(state))

        summary = output.get("collection_summary", {})
        for key in ("total_docs", "total_companies", "total_dimensions"):
            assert key in summary, f"Missing key '{key}' in collection_summary"

    def test_todo_event_emitted(self):
        """Collector must emit a 'todo' SSE event for the frontend matrix."""
        from backend.nodes.collector import collector_node

        results = [self._make_research_result("X", "product_pricing", "success", 5)]
        state   = self._base_state(results, ["X"], ["product_pricing"])
        output  = run(collector_node(state))

        events     = output.get("events", [])
        todo_events = [e for e in events if e.get("type") == "todo"]
        assert todo_events, "Collector must emit at least one 'todo' event"
        assert "todo_state" in todo_events[0], "'todo_state' key missing from todo event"

    def test_status_mapping_success(self):
        """'success' research result → todo_state cell status = 'success'."""
        from backend.nodes.collector import collector_node

        results = [self._make_research_result("X", "product_pricing", "success", 5)]
        state   = self._base_state(results, ["X"], ["product_pricing"])
        output  = run(collector_node(state))

        assert output["todo_state"]["X"]["product_pricing"]["status"] == "success"

    def test_status_mapping_error(self):
        """'error' research result → todo_state cell status = 'error'."""
        from backend.nodes.collector import collector_node

        result = self._make_research_result("X", "product_pricing", "error", 0)
        result["error_code"] = "EXCEPTION"
        state  = self._base_state([result], ["X"], ["product_pricing"])
        output = run(collector_node(state))

        assert output["todo_state"]["X"]["product_pricing"]["status"] == "error"


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_class(cls_name, cls):
    import traceback
    instance = cls()
    methods  = [m for m in dir(cls) if m.startswith("test_")]
    passed   = []
    failed   = []

    print(f"\n{'─'*60}")
    print(f"  {cls_name}")
    print(f"{'─'*60}")

    for name in methods:
        try:
            getattr(instance, name)()
            print(f"  PASS  {name}")
            passed.append(name)
        except Exception as e:
            print(f"  FAIL  {name}")
            print(f"        {e}")
            traceback.print_exc()
            failed.append(name)

    return passed, failed


if __name__ == "__main__":
    test_classes = [
        ("T1  BaseResearcher result schema",    TestBaseResearcherSchema),
        ("T2  Researcher registry",             TestResearcherRegistry),
        ("T3  Deduplication + domain extraction", TestDeduplication),
        ("T4  Grounding node",                  TestGroundingNode),
        ("T5  Research Dispatcher fan-out",     TestResearchDispatcher),
        ("T6  Collector todo_state",            TestCollector),
    ]

    all_passed, all_failed = [], []
    for title, cls in test_classes:
        p, f = _run_class(title, cls)
        all_passed.extend(p)
        all_failed.extend(f)

    total = len(all_passed) + len(all_failed)
    pct   = int(100 * len(all_passed) / total) if total else 0

    print(f"\n{'='*60}")
    print(f"  Module 2 Evaluation Summary")
    print(f"{'='*60}")
    print(f"  Total : {total}")
    print(f"  Passed: {len(all_passed)}")
    print(f"  Failed: {len(all_failed)}")
    print(f"  Score : {pct}%")

    sys.exit(0 if not all_failed else 1)
