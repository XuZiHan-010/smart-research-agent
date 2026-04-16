"""
Planner node — translates user inputs into a concrete research plan.

No LLM needed here; it's a deterministic config step.
Output:
  research_plan = {
    "active_dimensions": [...],
    "queries_per_dimension": int,
    "results_per_query": int,
  }
"""

from typing import Dict, Any

from backend.classes.state import ResearchState, AVAILABLE_DIMENSIONS, DIMENSION_LABELS_EN

_DEPTH_CONFIG = {
    "quick":    {"queries_per_dimension": 2, "results_per_query": 3},
    "standard": {"queries_per_dimension": 4, "results_per_query": 5},
    "deep":     {"queries_per_dimension": 6, "results_per_query": 8},
}


class Planner:
    async def run(self, state: ResearchState) -> Dict[str, Any]:
        depth  = state.get("depth", "standard").lower()
        config = _DEPTH_CONFIG.get(depth, _DEPTH_CONFIG["standard"])

        # Validate selected dimensions (ignore unknown keys)
        active = [d for d in state.get("dimensions", []) if d in AVAILABLE_DIMENSIONS]

        research_plan: Dict[str, Any] = {
            "active_dimensions":    active,
            "queries_per_dimension": config["queries_per_dimension"],
            "results_per_query":    config["results_per_query"],
        }

        dim_labels = [DIMENSION_LABELS_EN[d] for d in active]
        events = [{
            "type":    "plan_complete",
            "step":    "planner",
            "message": (
                f"Research plan ready — {len(active)} dimensions: "
                f"{', '.join(dim_labels)} | "
                f"depth: {depth} ({config['queries_per_dimension']} queries × "
                f"{config['results_per_query']} results each)"
            ),
            "research_plan": research_plan,
        }]

        return {"research_plan": research_plan, "events": events}
