"""LangGraph workflow for the Market Study Agent."""

import uuid
from typing import Any, AsyncIterator, Dict, List

from langgraph.graph import END, StateGraph

from backend.classes.config import DEPTH_CONFIGS
from backend.classes.state import ResearchState
from backend.nodes.citation_resolver import citation_resolver_node
from backend.nodes.compactor import compactor_node
from backend.nodes.cross_validator import cross_validator_node
from backend.nodes.editor import editor_node
from backend.nodes.output_formatter import output_formatter_node
from backend.nodes.theme_orchestrator import theme_orchestrator_node


async def router_node(state: ResearchState) -> Dict[str, Any]:
    default_depth = state.get("depth", "standard")
    theme_depths = state.get("theme_depths", {})
    theme_keys = list(state.get("selected_themes", []))
    theme_keys.extend(f"custom_{idx + 1}" for idx, _ in enumerate(state.get("custom_themes", [])))
    theme_depth_params = {
        theme_key: {
            key: DEPTH_CONFIGS.get(
                theme_depths.get(theme_key, default_depth),
                DEPTH_CONFIGS["standard"],
            )[key]
            for key in ("queries_per_theme", "results_per_query", "max_docs_per_theme")
        }
        for theme_key in theme_keys
    }
    return {
        "theme_depth_params": theme_depth_params,
        "events": [{
            "type": "status",
            "node": "router",
            "message": "Market study workflow initialized",
        }],
    }


def _build_graph() -> Any:
    wf = StateGraph(ResearchState)
    wf.add_node("router", router_node)
    wf.add_node("theme_orchestrator", theme_orchestrator_node)
    wf.add_node("cross_validator", cross_validator_node)
    wf.add_node("compactor", compactor_node)
    wf.add_node("editor", editor_node)
    wf.add_node("citation_resolver", citation_resolver_node)
    wf.add_node("output_formatter", output_formatter_node)

    wf.set_entry_point("router")
    wf.add_edge("router", "theme_orchestrator")
    wf.add_edge("theme_orchestrator", "cross_validator")
    wf.add_edge("cross_validator", "compactor")
    wf.add_edge("compactor", "editor")
    wf.add_edge("editor", "citation_resolver")
    wf.add_edge("citation_resolver", "output_formatter")
    wf.add_edge("output_formatter", END)
    return wf.compile()


_COMPILED_GRAPH = _build_graph()


class Graph:
    def __init__(
        self,
        *,
        research_domain: str,
        selected_themes: List[str],
        custom_themes: List[str],
        geography: List[str],
        time_range: Dict[str, str],
        depth: str = "standard",
        theme_depths: Dict[str, str] | None = None,
        output_format: str = "markdown",
        job_id: str | None = None,
    ) -> None:
        self._job_id = job_id or str(uuid.uuid4())
        self._final_state: Dict[str, Any] = {}
        self.initial_state: ResearchState = {
            "job_id": self._job_id,
            "research_domain": research_domain,
            "selected_themes": selected_themes,
            "custom_themes": custom_themes,
            "geography": geography,
            "time_range": time_range,
            "depth": depth,
            "theme_depths": theme_depths or {},
            "output_format": output_format,
            "theme_reports": [],
            "validation_report": {},
            "compacted_skeleton": {},
            "final_report_md": None,
            "citations_map": {},
            "report": "",
            "output": None,
            "events": [],
            "error": "",
        }

    @property
    def job_id(self) -> str:
        return self._job_id

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        async for chunk in _COMPILED_GRAPH.astream(self.initial_state, stream_mode="updates"):
            for _node, delta in chunk.items():
                if not isinstance(delta, dict):
                    continue
                self._final_state.update({k: v for k, v in delta.items() if k != "events"})
                for event in delta.get("events", []):
                    yield event

    def get_final_state(self) -> Dict[str, Any]:
        return self._final_state

    async def run_full(self) -> Dict[str, Any]:
        async for _ in self.run():
            pass
        return self.get_final_state()
