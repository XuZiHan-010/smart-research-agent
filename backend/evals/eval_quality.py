"""
Quality Evaluation — LLM-as-Judge

Directly inspired by the Anthropic cookbook "tool-evaluation" article's
structured feedback approach:
  - A judge LLM evaluates the report using a rubric
  - Output is XML-tagged: <coverage>, <depth>, <accuracy>, <structure>,
    <battlecard>, <feedback>, <score>
  - Results are printed in a formatted summary (same style as the cookbook)

The judge is GPT-4.1-mini (fast + cheap for evaluation tasks).
The report under evaluation can come from:
  a) A live pipeline run (via --task XML file)
  b) A previously saved report file (via --report-file)

Usage:
  # Run pipeline then evaluate its output:
  python -m backend.evals.eval_quality --task backend/evals/eval_tasks/notion_pricing.xml

  # Evaluate a saved report markdown file:
  python -m backend.evals.eval_quality --report-file my_report.md \\
    --target Notion --competitors "Obsidian,Coda"

  # Save results to JSON:
  python -m backend.evals.eval_quality --task notion_pricing.xml --output results.json

Requires: OPENAI_API_KEY in .env
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()


# ── Judge prompt ──────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are an expert competitive intelligence analyst and report evaluator.
Your role is to critically assess competitive analysis reports on five dimensions.
Be rigorous, specific, and actionable. Do not inflate scores — a 10 should be rare.
Always ground your feedback in specific examples from the report."""

JUDGE_USER_TEMPLATE = """Evaluate the following competitive analysis report.

**Target Company**: {target}
**Competitors**: {competitors}
**Report Type**: {report_type}

---
{report_excerpt}
---

Score each dimension from 0 to 10 and provide structured feedback.
Return your evaluation using ONLY these XML tags (no other text outside the tags):

<coverage>
[Integer 0-10] Completeness: Does the report address all major competitive dimensions relevant
to the report type? Are there obvious gaps? Consider: pricing, product features, market position,
customer sentiment, growth signals — whichever are relevant to this report type.
</coverage>

<depth>
[Integer 0-10] Analytical depth: Does the analysis go beyond surface-level observations?
Are there specific data points, numbers, named sources, or direct comparisons rather than
generic statements? Deduct heavily for vague claims like "Company X has better UX" without evidence.
</depth>

<accuracy>
[Integer 0-10] Plausibility: Based on common knowledge, do the claims seem reasonable and
internally consistent? Flag any obvious factual errors or implausible assertions.
(Note: You are not verifying against live data — assess logical consistency only.)
</accuracy>

<structure>
[Integer 0-10] Readability and structure: Is the report well-organized with clear sections,
headers, and logical flow? Would an executive or investor find it easy to navigate?
</structure>

<battlecard>
[Integer 0-10] Battlecard utility: Are the win/lose themes specific and actionable for a sales team?
Does the feature matrix reflect real differentiators? Are objection handlers practical?
If no battlecard data is present, score 0.
</battlecard>

<feedback>
Provide 3-5 specific, actionable improvement suggestions. Each should reference a concrete
section or claim in the report. Follow this format for each item:
- [Section/Issue]: [What's missing or wrong] → [How to improve it]
</feedback>

<score>
[Float 0.0-10.0] Overall score — weighted average across all five dimensions.
</score>"""

_MAX_REPORT_CHARS = 12_000  # Judge context budget for the report


# ── XML tag extraction (same pattern as the cookbook article) ─────────────────

def _extract_tag(text: str, tag: str) -> str:
    """Extract content between <tag>…</tag>. Returns empty string if not found."""
    m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text)
    return m.group(1).strip() if m else ""


def _parse_score(text: str) -> float:
    """Parse first float-like number from a string."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


# ── Judge call ────────────────────────────────────────────────────────────────

async def judge_report(
    report:      str,
    target:      str,
    competitors: List[str],
    report_type: str,
) -> Dict[str, Any]:
    """
    Call the judge LLM and parse structured XML feedback.
    Returns a dict with per-dimension scores + feedback text.
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    report_excerpt = report[:_MAX_REPORT_CHARS]
    if len(report) > _MAX_REPORT_CHARS:
        report_excerpt += f"\n\n_[Report truncated at {_MAX_REPORT_CHARS} chars for evaluation]_"

    user_content = JUDGE_USER_TEMPLATE.format(
        target      = target,
        competitors = ", ".join(competitors),
        report_type = report_type,
        report_excerpt = report_excerpt,
    )

    llm = ChatOpenAI(
        model       = "gpt-4.1-mini",
        temperature = 0.1,
        api_key     = os.getenv("OPENAI_API_KEY", ""),
    )

    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=user_content),
    ]

    response  = await llm.ainvoke(messages)
    raw_text  = response.content

    coverage_raw  = _extract_tag(raw_text, "coverage")
    depth_raw     = _extract_tag(raw_text, "depth")
    accuracy_raw  = _extract_tag(raw_text, "accuracy")
    structure_raw = _extract_tag(raw_text, "structure")
    battlecard_raw= _extract_tag(raw_text, "battlecard")
    feedback      = _extract_tag(raw_text, "feedback")
    score_raw     = _extract_tag(raw_text, "score")

    return {
        "coverage":      _parse_score(coverage_raw),
        "depth":         _parse_score(depth_raw),
        "accuracy":      _parse_score(accuracy_raw),
        "structure":     _parse_score(structure_raw),
        "battlecard":    _parse_score(battlecard_raw),
        "feedback":      feedback,
        "score":         _parse_score(score_raw),
        "raw_response":  raw_text,
    }


# ── Display ───────────────────────────────────────────────────────────────────

def print_quality_result(
    result:      Dict[str, Any],
    target:      str,
    competitors: List[str],
):
    bar = "━" * 52

    def _bar_score(score: float) -> str:
        filled = int(round(score))
        return "█" * filled + "░" * (10 - filled) + f"  {score:.1f}/10"

    print(f"\nQuality Evaluation — {target} vs {', '.join(competitors)}")
    print(bar)
    print(f"  Coverage   {_bar_score(result['coverage'])}")
    print(f"  Depth      {_bar_score(result['depth'])}")
    print(f"  Accuracy   {_bar_score(result['accuracy'])}")
    print(f"  Structure  {_bar_score(result['structure'])}")
    print(f"  Battlecard {_bar_score(result['battlecard'])}")
    print(f"  {'─'*48}")
    print(f"  Score      {_bar_score(result['score'])}")
    print(f"\n  Feedback:")
    for line in result["feedback"].splitlines():
        if line.strip():
            print(f"    {line.strip()}")
    print()


# ── Pipeline runner (reuses eval_pipeline task parsing) ──────────────────────

async def run_pipeline_and_evaluate(task_path: Path) -> Dict[str, Any]:
    """Run the full pipeline for a task file, then judge the output."""
    from backend.evals.eval_pipeline import parse_task_file, run_task

    task   = parse_task_file(task_path)
    print(f"Running pipeline for task: {task['id']}")
    result = await run_task(task)

    report     = result.get("report", "")
    battlecard = result.get("battlecard", {})

    if not report:
        raise ValueError("Pipeline produced an empty report — cannot evaluate")

    print("Pipeline complete. Calling judge LLM...")
    judgment = await judge_report(
        report      = report,
        target      = task["target"],
        competitors = task["competitors"],
        report_type = task["report_type"],
    )

    return {
        "task_id":           task["id"],
        "target":            task["target"],
        "competitors":       task["competitors"],
        "report_type":       task["report_type"],
        "depth":             task["depth"],
        "pipeline_duration": result["total_duration"],
        "report_length":     result["report_length"],
        "structural_score":  f"{result['structural_score']}/{result['structural_total']}",
        "quality":           judgment,
    }


# ── CLI entry point ───────────────────────────────────────────────────────────

async def _main():
    parser = argparse.ArgumentParser(
        description="LLM-as-judge quality evaluation for research agent reports"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--task", type=str,
        help="XML task file — runs the pipeline then evaluates its output",
    )
    group.add_argument(
        "--report-file", type=str,
        help="Path to a saved Markdown report to evaluate directly",
    )
    parser.add_argument("--target",      type=str, default="Company",
                        help="Target company name (used with --report-file)")
    parser.add_argument("--competitors", type=str, default="",
                        help="Comma-separated competitors (used with --report-file)")
    parser.add_argument("--report-type", type=str, default="full_analysis",
                        help="Report type label (used with --report-file)")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results as JSON to this path")
    args = parser.parse_args()

    if args.task:
        result = await run_pipeline_and_evaluate(Path(args.task))
        print_quality_result(
            result["quality"],
            result["target"],
            result["competitors"],
        )
    else:
        # Evaluate a pre-existing report file
        report_text = Path(args.report_file).read_text(encoding="utf-8")
        competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]
        print(f"Evaluating: {args.report_file}")
        print(f"Target: {args.target}  |  Competitors: {', '.join(competitors)}")
        print("Calling judge LLM...")
        judgment = await judge_report(
            report      = report_text,
            target      = args.target,
            competitors = competitors,
            report_type = args.report_type,
        )
        result = {
            "task_id":    Path(args.report_file).stem,
            "target":     args.target,
            "competitors": competitors,
            "report_type": args.report_type,
            "quality":    judgment,
        }
        print_quality_result(judgment, args.target, competitors)

    if args.output:
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Results saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(_main())
