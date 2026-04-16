"""
Briefing node — synthesises curated documents into per-dimension briefings.

Uses Gemini 2.5 Flash (huge context window, fast, cost-efficient).
All active dimensions run in parallel (semaphore limits to 3 concurrent).
"""

import asyncio
import os
from typing import Dict, Any, List

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser

from backend.classes.state import ResearchState, DIMENSION_LABELS_EN
from backend.prompts import DIMENSION_BRIEFING_PROMPTS

load_dotenv()

MAX_CONTEXT_CHARS  = 80_000   # safety cap fed to Claude per dimension
MAX_CONCURRENT     = 3        # parallel briefings


class Briefing:
    def __init__(self) -> None:
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
        )

    async def run(self, state: ResearchState) -> Dict[str, Any]:
        curated = state.get("curated_data", {})
        active  = state["research_plan"]["active_dimensions"]
        company = state["company"]
        events: List[Dict] = []

        events.append({
            "type":    "briefing_start",
            "step":    "briefing",
            "message": f"Generating {len(active)} briefings in parallel…",
        })

        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def _bounded(dim: str) -> tuple[str, str]:
            async with sem:
                text = await self._generate(company, dim, curated.get(dim, {}))
                return dim, text

        pairs = await asyncio.gather(*[_bounded(d) for d in active])
        briefings: Dict[str, str] = dict(pairs)

        for dim, text in briefings.items():
            label = DIMENSION_LABELS_EN.get(dim, dim)
            events.append({
                "type":      "briefing_complete",
                "dimension": dim,
                "chars":     len(text),
                "message":   f"{label} briefing ready ({len(text)} chars)",
            })

        events.append({
            "type":    "all_briefings_done",
            "step":    "briefing",
            "message": "All briefings generated",
        })

        return {"briefings": briefings, "events": events}

    # ── per-dimension synthesis ───────────────────────────────────────────────

    async def _generate(self, company: str, dimension: str, docs: Dict) -> str:
        prompt = DIMENSION_BRIEFING_PROMPTS.get(dimension)
        if prompt is None:
            return f"No briefing prompt found for dimension: {dimension}"

        context = self._format_context(docs)
        chain   = prompt | self.llm | StrOutputParser()
        return await chain.ainvoke({"company": company, "context": context})

    @staticmethod
    def _format_context(docs: Dict) -> str:
        """Format curated docs as a readable context block for the LLM."""
        parts: List[str] = []
        for url, doc in list(docs.items())[:20]:   # cap at 20 docs
            title   = doc.get("title", "Untitled")
            content = doc.get("content", "").strip()
            score   = doc.get("score", 0)

            snippet = content[:MAX_CONTEXT_CHARS // max(len(docs), 1)]
            parts.append(
                f"### [{title}]({url})  (relevance: {score:.2f})\n{snippet}"
            )

        result = "\n\n".join(parts)
        return result[:MAX_CONTEXT_CHARS]
