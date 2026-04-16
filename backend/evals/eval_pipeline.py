"""
Pipeline Evaluation — End-to-End Live Test

Borrowed from the Anthropic cookbook "tool-evaluation" approach:
  - XML task files define test cases (target, competitors, report_type, depth,
    structural checks to verify)
  - Each task is run through the full LangGraph pipeline
  - Metrics collected: structural accuracy, duration per node, Exa call count,
    research matrix coverage, retry triggers, report length, sources count
  - Outputs a Markdown report matching the cookbook's report format

Requires all API keys to be set in .env:
  OPENAI_API_KEY, GOOGLE_API_KEY, EXA_API_KEY, MONGODB_URI

Usage:
  # Run a specific task file:
  python -m backend.evals.eval_pipeline --task backend/evals/eval_tasks/notion_pricing.xml

  # Run all task files in the default directory:
  python -m backend.evals.eval_pipeline

  # Save report to file:
  python -m backend.evals.eval_pipeline --output eval_report.md
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()


# ── XML task parsing ─────────────────────────────────────────────────────────

def parse_task_file(path: Path) -> Dict[str, Any]:
    """Parse one XML task file into a structured task dict."""
    tree = ET.parse(path)
    root = tree.getroot()
    task_el = root.find(".//task")
    if task_el is None:
        raise ValueError(f"No <task> element found in {path}")

    def _text(tag, default=""):
        el = task_el.find(tag)
        return el.text.strip() if el is not None and el.text else default

    competitors_raw = _text("competitors", "")
    competitors = [c.strip() for c in competitors_raw.split(",") if c.strip()]

    # Parse structural checks
    checks_el = task_el.find("structural_checks")
    checks: Dict[str, Any] = {
        "required_sections":              [],
        "min_report_length":              0,
        "min_sources":                    0,
        "battlecard_target":              None,
        "battlecard_has_competitors":     [],
        "battlecard_has_feature_matrix":  False,
        "battlecard_has_win_themes":      False,
        "battlecard_has_objection_handlers": False,
    }
    if checks_el is not None:
        for el in checks_el:
            tag = el.tag
            val = (el.text or "").strip()
            if tag == "required_section":
                checks["required_sections"].append(val)
            elif tag == "min_report_length":
                checks["min_report_length"] = int(val)
            elif tag == "min_sources":
                checks["min_sources"] = int(val)
            elif tag == "battlecard_target":
                checks["battlecard_target"] = val
            elif tag == "battlecard_has_competitor":
                checks["battlecard_has_competitors"].append(val)
            elif tag == "battlecard_has_feature_matrix":
                checks["battlecard_has_feature_matrix"] = val.lower() == "true"
            elif tag == "battlecard_has_win_themes":
                checks["battlecard_has_win_themes"] = val.lower() == "true"
            elif tag == "battlecard_has_objection_handlers":
                checks["battlecard_has_objection_handlers"] = val.lower() == "true"

    return {
        "id":           task_el.get("id", path.stem),
        "target":       _text("target_company"),
        "website":      _text("target_website"),
        "competitors":  competitors,
        "report_type":  _text("report_type", "full_analysis"),
        "depth":        _text("depth", "snapshot"),
        "checks":       checks,
    }


# ── Structural checking ───────────────────────────────────────────────────────

def run_structural_checks(
    task:      Dict[str, Any],
    report:    str,
    battlecard: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Run all structural checks defined in the task.
    Returns a list of {name, passed, detail} dicts.
    """
    checks   = task["checks"]
    results  = []

    def _check(name: str, passed: bool, detail: str = ""):
        results.append({"name": name, "passed": passed, "detail": detail})

    # Required sections (case-insensitive substring match in report)
    for section in checks["required_sections"]:
        found = section.lower() in report.lower()
        _check(
            f"Section contains '{section}'",
            found,
            "" if found else f"'{section}' not found in report",
        )

    # Min report length
    if checks["min_report_length"]:
        _check(
            f"Report length ≥ {checks['min_report_length']} chars",
            len(report) >= checks["min_report_length"],
            f"actual: {len(report)} chars",
        )

    # Min sources
    if checks["min_sources"]:
        # Count URLs in the sources section
        sources_match = re.search(
            r"##\s*Sources\s*\n([\s\S]+?)(?:\n##\s|\n#\s|\s*$)", report
        )
        source_count = 0
        if sources_match:
            lines = [l.strip() for l in sources_match.group(1).splitlines() if l.strip()]
            source_count = len(lines)
        _check(
            f"Min {checks['min_sources']} sources",
            source_count >= checks["min_sources"],
            f"actual: {source_count}",
        )

    # Battlecard target
    if checks["battlecard_target"] and battlecard:
        target_ok = battlecard.get("target") == checks["battlecard_target"]
        _check(
            f"Battlecard target = '{checks['battlecard_target']}'",
            target_ok,
            f"actual: '{battlecard.get('target')}'",
        )

    # Battlecard competitors
    for comp in checks["battlecard_has_competitors"]:
        if battlecard:
            found = comp in (battlecard.get("competitors") or [])
            _check(
                f"Battlecard includes competitor '{comp}'",
                found,
                "" if found else f"competitors list: {battlecard.get('competitors')}",
            )

    # Feature matrix
    if checks["battlecard_has_feature_matrix"] and battlecard:
        matrix = battlecard.get("feature_matrix") or []
        _check("Battlecard has feature_matrix", len(matrix) > 0, f"{len(matrix)} rows")

    # Win themes
    if checks["battlecard_has_win_themes"] and battlecard:
        wins = battlecard.get("win_themes") or []
        _check("Battlecard has win_themes", len(wins) > 0, f"{len(wins)} entries")

    # Objection handlers
    if checks["battlecard_has_objection_handlers"] and battlecard:
        handlers = battlecard.get("objection_handlers") or []
        _check("Battlecard has objection_handlers", len(handlers) > 0, f"{len(handlers)} entries")

    return results


# ── Node timing instrumentation ───────────────────────────────────────────────

class NodeTimer:
    """
    Records first-seen and last-seen timestamps per node from SSE status events.
    Used to estimate per-node wall-clock time.
    """
    def __init__(self):
        self._first: Dict[str, float] = {}
        self._last:  Dict[str, float] = {}

    def record(self, node: str, t: float):
        if node not in self._first:
            self._first[node] = t
        self._last[node] = t

    def durations(self) -> Dict[str, float]:
        return {
            node: round(self._last[node] - self._first[node], 2)
            for node in self._first
        }


# ── Single task runner ────────────────────────────────────────────────────────

async def run_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the full pipeline for one task.
    Returns a results dict with metrics + structural check outcomes.
    """
    from backend.graph import Graph

    target      = task["target"]
    website     = task["website"]
    competitors = task["competitors"]
    report_type = task["report_type"]
    depth       = task["depth"]

    # Build all_companies list (target first, then competitors)
    all_companies = [{"name": target, "website": website, "source": "target"}] + [
        {"name": c, "website": "", "source": "user"} for c in competitors
    ]

    graph = Graph(
        target_company = target,
        target_website = website,
        all_companies  = all_companies,
        report_type    = report_type,
        depth          = depth,
        output_format  = "markdown",
        job_id         = f"eval-{task['id']}-{int(time.time())}",
    )

    timer       = NodeTimer()
    exa_calls   = 0
    retry_triggered = False
    research_matrix: Dict[str, Any] = {}
    final_todo: Dict[str, Any] = {}

    t_start = time.monotonic()

    async for event in graph.run():
        t_now = time.monotonic()

        if event.get("type") == "status" and event.get("node"):
            timer.record(event["node"], t_now)

            # Approximate Exa call count from grounding + research status messages
            msg = event.get("message", "").lower()
            if "grounded" in msg or "exa" in msg:
                exa_calls += 1

        if event.get("type") == "todo":
            final_todo = event.get("todo_state", {})

        # Detect retry (evaluator sending status with retry info)
        if event.get("type") == "status" and "retry" in event.get("message", "").lower():
            retry_triggered = True

    t_total = round(time.monotonic() - t_start, 2)

    final_state = graph.get_final_state()
    report      = final_state.get("report", "")
    battlecard  = final_state.get("battlecard_data", {}) or {}

    # Research matrix stats from todo_state
    cells_total   = 0
    cells_success = 0
    cells_partial = 0
    cells_empty   = 0
    cells_error   = 0
    for company_dims in final_todo.values():
        for cell in company_dims.values():
            cells_total += 1
            s = cell.get("status", "")
            if s == "success": cells_success += 1
            elif s == "partial": cells_partial += 1
            elif s == "empty":   cells_empty   += 1
            elif s == "error":   cells_error   += 1

    coverage_pct = (
        round(100 * cells_success / cells_total, 1) if cells_total else 0.0
    )

    # Count sources from report
    sources_match = re.search(
        r"##\s*Sources\s*\n([\s\S]+?)(?:\n##\s|\n#\s|\s*$)", report
    )
    sources_count = 0
    if sources_match:
        sources_count = len([
            l for l in sources_match.group(1).splitlines() if l.strip()
        ])

    structural_results = run_structural_checks(task, report, battlecard)

    return {
        "task_id":         task["id"],
        "target":          target,
        "competitors":     competitors,
        "report_type":     report_type,
        "depth":           depth,
        "total_duration":  t_total,
        "node_durations":  timer.durations(),
        "exa_calls_approx": exa_calls,
        "research_matrix": {
            "total":   cells_total,
            "success": cells_success,
            "partial": cells_partial,
            "empty":   cells_empty,
            "error":   cells_error,
        },
        "coverage_pct":    coverage_pct,
        "retry_triggered": retry_triggered,
        "report_length":   len(report),
        "sources_count":   sources_count,
        "structural":      structural_results,
        "structural_score": sum(1 for r in structural_results if r["passed"]),
        "structural_total": len(structural_results),
        "report":          report,
        "battlecard":      battlecard,
    }


# ── Markdown report generator ─────────────────────────────────────────────────

def generate_report(results: List[Dict[str, Any]], run_date: str) -> str:
    """Generate a Markdown evaluation report (same style as the cookbook article)."""

    total_structural = sum(r["structural_total"] for r in results)
    passed_structural = sum(r["structural_score"] for r in results)
    accuracy = (passed_structural / total_structural * 100) if total_structural else 0

    avg_duration  = sum(r["total_duration"] for r in results) / len(results) if results else 0
    avg_exa_calls = sum(r["exa_calls_approx"] for r in results) / len(results) if results else 0
    avg_coverage  = sum(r["coverage_pct"] for r in results) / len(results) if results else 0

    lines = [
        "# Pipeline Evaluation Report",
        f"\n_Run date: {run_date}_\n",
        "## Summary\n",
        f"- **Tasks**: {len(results)}",
        f"- **Structural Accuracy**: {passed_structural}/{total_structural} ({accuracy:.1f}%)",
        f"- **Avg Duration**: {avg_duration:.1f}s",
        f"- **Avg Exa Calls (approx)**: {avg_exa_calls:.1f}",
        f"- **Avg Research Coverage**: {avg_coverage:.1f}%",
        "",
    ]

    for r in results:
        structural_pct = (
            round(100 * r["structural_score"] / r["structural_total"])
            if r["structural_total"] else 0
        )
        all_pass = r["structural_score"] == r["structural_total"]
        score_indicator = "✅" if all_pass else "⚠️"

        node_timing_str = " | ".join(
            f"{node} {dur}s" for node, dur in sorted(r["node_durations"].items())
        ) or "—"

        matrix = r["research_matrix"]
        matrix_str = (
            f"{matrix['success']} success / {matrix['partial']} partial / "
            f"{matrix['empty']} empty / {matrix['error']} error "
            f"(total: {matrix['total']})"
        )

        lines += [
            f"---\n",
            f"## Task: `{r['task_id']}`\n",
            f"**Target**: {r['target']}  ",
            f"**vs**: {', '.join(r['competitors'])}  ",
            f"**Type**: {r['report_type']}  **Depth**: {r['depth']}\n",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Structural Score | {score_indicator} {r['structural_score']}/{r['structural_total']} ({structural_pct}%) |",
            f"| Total Duration | {r['total_duration']}s |",
            f"| Report Length | {r['report_length']:,} chars |",
            f"| Sources Found | {r['sources_count']} |",
            f"| Exa Calls (approx) | {r['exa_calls_approx']} |",
            f"| Research Coverage | {r['coverage_pct']}% |",
            f"| Retry Triggered | {'Yes ⚠️' if r['retry_triggered'] else 'No'} |",
            f"",
            f"**Node Timing**: {node_timing_str}",
            f"",
            f"**Research Matrix**: {matrix_str}",
            f"",
            f"**Structural Checks**:",
        ]

        for check in r["structural"]:
            icon   = "✅" if check["passed"] else "❌"
            detail = f" _{check['detail']}_" if check["detail"] else ""
            lines.append(f"- {icon} {check['name']}{detail}")

        lines.append("")

    return "\n".join(lines)


# ── CLI entry point ───────────────────────────────────────────────────────────

async def _main():
    parser = argparse.ArgumentParser(description="Pipeline end-to-end evaluation")
    parser.add_argument(
        "--task", type=str, default=None,
        help="Path to a specific XML task file (default: run all in eval_tasks/)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Save Markdown report to this file path",
    )
    args = parser.parse_args()

    default_tasks_dir = Path(__file__).parent / "eval_tasks"

    if args.task:
        task_files = [Path(args.task)]
    else:
        task_files = sorted(default_tasks_dir.glob("*.xml"))

    if not task_files:
        print("No task files found. Use --task or add XML files to eval_tasks/")
        sys.exit(1)

    tasks = []
    for f in task_files:
        try:
            tasks.append(parse_task_file(f))
            print(f"Loaded task: {f.name}")
        except Exception as e:
            print(f"Failed to parse {f}: {e}")

    print(f"\nRunning {len(tasks)} task(s)...\n{'='*60}")

    results = []
    for task in tasks:
        print(f"\n▶ Task: {task['id']}  ({task['target']} vs {', '.join(task['competitors'])})")
        print(f"  report_type={task['report_type']}  depth={task['depth']}")
        t0 = time.monotonic()
        try:
            result = await run_task(task)
            results.append(result)
            dur = time.monotonic() - t0
            sc  = result["structural_score"]
            tot = result["structural_total"]
            cov = result["coverage_pct"]
            print(f"  ✅ Done in {dur:.1f}s | Structural {sc}/{tot} | Coverage {cov}%")
        except Exception as e:
            import traceback
            print(f"  ❌ Failed: {e}")
            traceback.print_exc()

    if not results:
        print("\nNo results to report.")
        sys.exit(1)

    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    report   = generate_report(results, run_date)

    print(f"\n{'='*60}")
    print(report)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(_main())
