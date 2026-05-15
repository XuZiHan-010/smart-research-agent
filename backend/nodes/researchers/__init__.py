"""Legacy researcher package.

Competitor-dimension researchers were removed in the Market Study Agent
restructure. The package remains only so old imports fail softly during
transition instead of exposing stale registry state.
"""

RESEARCHER_REGISTRY = {}
