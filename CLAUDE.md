# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
# Start API server (port 8000, auto-reload)
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
# or
python api.py

# Install Python deps
pip install -r requirements.txt
```

### Frontend
```bash
cd frontend

npm install
npm run dev      # Vite dev server on port 3000; proxies /api → localhost:8000
npm run build    # Production bundle → frontend/dist/ (served by FastAPI in prod)
npm run preview  # Preview the production build locally
```

### Eval scripts (no test framework — run as modules)
```bash
python -m backend.evals.eval_module1   # 44 state + config tests
python -m backend.evals.eval_module3   # curator / evaluator logic tests
python -m backend.evals.eval_module4   # comparator + battlecard + editor prompt tests
```

## Environment variables
Copy `.env.example` to `.env` and fill in:
```
OPENAI_API_KEY=        # GPT-4.1 (editor), GPT-4.1-mini (battlecard, query gen)
GOOGLE_API_KEY=        # Gemini 2.5 Flash (comparator)
EXA_API_KEY=           # Exa web search (all researchers + discovery)
MONGODB_URI=mongodb://localhost:27017
```

## Architecture

### Request lifecycle
1. **Frontend** (React/Vite, port 3000) → `POST /api/research/discover` → returns competitor suggestions
2. User confirms companies → `POST /api/research/start` → `job_id`
3. **Frontend** opens `GET /api/research/{job_id}/stream` (SSE) — drains `job_status[job_id]["events"]`
4. **FastAPI** runs `Graph.run()` as a `BackgroundTask`; events are appended to the in-memory queue
5. On completion: report + battlecard stored in **MongoDB**; `job_status` updated to `completed`

### LangGraph pipeline ([backend/graph.py](backend/graph.py))
10 nodes compiled once at module load into `_COMPILED_GRAPH`:

```
router → grounding → research_dispatcher → collector → curator → evaluator
                                                                    │
                                               ┌─[fail + retries]──┘
                                               │
                                         research_dispatcher  (retry failed dims only)
                                               │
                                         [pass / retries exhausted]
                                               ↓
                              comparator → battlecard_builder → editor → output_formatter
```

- **research_dispatcher** — N companies × M dimensions concurrency inside a single node via `asyncio.gather` + `asyncio.Semaphore`; dynamic fan-out avoids static LangGraph edge count requirement
- **evaluator** — pure-rules quality gate (no LLM); sets `retry_dimensions` on failure; conditional edge loops back to dispatcher for failed dims only; max retries controlled by `MAX_EVALUATOR_RETRIES` in config
- **curator** — writes full curated doc content to MongoDB; returns only `curated_ref = job_id` in State to prevent state bloat (~1.8 MB → ~50 KB)

### State design ([backend/classes/state.py](backend/classes/state.py))
- `InputState` — 8 user-facing fields (mirrors frontend form)
- `CompetitorResearchState` — full pipeline state; `research_results` and `events` both use `Annotated[List[Dict], operator.add]` for parallel fan-in accumulation
- `job_status` — in-memory `defaultdict` keyed by `job_id`; SSE layer only; not persisted to MongoDB

### Model allocation
| Node | Model | Reason |
|---|---|---|
| researchers (query gen) | GPT-4.1-mini | cheap, fast |
| comparator | Gemini 2.5 Flash | 6 parallel calls; cost-efficient |
| battlecard_builder | GPT-4.1-mini | structured JSON extraction |
| editor | GPT-4.1 | best prose quality; streams tokens via SSE |

### MongoDB schema ([backend/services/mongodb_service.py](backend/services/mongodb_service.py))
One document per job. Heavy fields (`curated_company_data`, `comparisons`) are written by pipeline nodes and excluded from the `/history` list projection. Edit history appended via `$push`. `get_dimension_data()` loads one dimension at a time to avoid memory spikes in the comparator.

### Key config ([backend/classes/config.py](backend/classes/config.py))
- `AVAILABLE_DIMENSIONS` — 6 dimension keys; maps to researcher classes via `RESEARCHER_REGISTRY` in `backend/nodes/researchers/__init__.py`
- `REPORT_TYPE_CONFIGS` — maps `report_type` → active dimensions + `comparator_focus` hint
- `DEPTH_CONFIGS` — maps `depth` → `queries_per_dim`, `results_per_query`, `max_docs_per_dim`
- `SEMAPHORE_*` constants — tune Exa API and researcher concurrency limits
- `QUALITY_THRESHOLDS` — evaluator quality gate: `min_docs_per_dimension=3`, `min_companies_coverage=0.6`

### Frontend state machine ([frontend/src/hooks/useResearch.ts](frontend/src/hooks/useResearch.ts))
`AppPhase`: `idle → discovering → confirming → running → completed | failed`

SSE event types: `status` (node progress), `todo` (N×M research matrix update), `stream` (editor token), `complete`, `error`. The `todo` event populates the research matrix grid in `ProgressTracker`. The `confirming` phase shows `DiscoveryPanel` for competitor selection before the pipeline starts.

## API endpoints ([api.py](api.py))

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/research/discover` | Auto-discover competitor suggestions |
| POST | `/api/research/start` | Launch pipeline → returns `job_id` |
| GET | `/api/research/{id}/stream` | SSE real-time events |
| GET | `/api/research/{id}/report` | Get completed report (202 if processing) |
| GET | `/api/research/{id}/battlecard` | Structured battlecard JSON |
| POST | `/api/research/{id}/edit` | Edit report (quick_edit / targeted_refresh / full_refresh) |
| GET | `/api/research/{id}/download` | Download as markdown / pdf / json |
| GET | `/api/research/history` | List past jobs (newest first) |
| DELETE | `/api/research/{id}` | Delete a job record |
| GET | `/api/health` | Health check |

## Researcher pattern ([backend/nodes/researchers/](backend/nodes/researchers/))

Each researcher extends `BaseResearcher` (in `base.py`) and defines:
- `DIMENSION` — string key matching `AVAILABLE_DIMENSIONS`
- `QUERY_PROMPT` — ChatPromptTemplate for query generation (in `backend/query_prompts.py`)
- `EXA_SEARCH_CONFIGS` — list of config dicts controlling Exa search behavior

`BaseResearcher.run()` flow: generate queries via LLM → fan out Exa searches per config → merge/dedupe by URL → return `{status, docs[], docs_found, ...}`.

### Exa SDK pitfalls
- The installed `exa_py` SDK does **NOT** support `use_autoprompt` — passing it raises `ValueError` and the bare `except` in `_search_single` silently swallows it. Never add `use_autoprompt` to any Exa call.
- `type="neural"` is the safe default. `type="auto"` may cause response parsing issues that bubble through `asyncio.gather(return_exceptions=False)` and discard all docs from the entire `_attempt`.
- `category="company"` and `category="people"` are in `_RESTRICTED_CATEGORIES` — Exa silently ignores `include_domains` and `start_published_date` when these categories are set. The code logs a warning when this happens.

## Prompt architecture ([backend/prompts.py](backend/prompts.py))

Three layers:
1. **Comparator prompts** (Gemini 2.5 Flash) — one per dimension, all share `_COMPARATOR_RULES`. Each prompt is **company-type adaptive**: SaaS / B2B industrial / consumer brand branches so the same pipeline works for startups and Fortune 500 companies.
2. **Battlecard prompt** (GPT-4.1-mini) — extracts structured JSON from comparator narratives (feature_matrix, pricing_comparison, win/lose themes, objection handlers).
3. **Editor prompts** (GPT-4.1) — L1 system persona + L2 template/metadata + L3 comparison data. Two variants: `EDITOR_COMPILE_PROMPT` (first generation) and `EDITOR_EDIT_PROMPT` (quick_edit / refresh).

**Query prompts** live separately in `backend/query_prompts.py` — one per dimension, also company-type adaptive. These generate the Exa search queries via GPT-4.1-mini.

## Discovery service ([backend/services/discovery_service.py](backend/services/discovery_service.py))

Three-step primary path: Exa news search (3 query variants, 12-month lookback) → GPT-4.1-mini competitor extraction → Exa URL lookup per candidate. Falls back to legacy direct Exa neural search if primary path returns empty.

## Verification
```bash
curl http://localhost:8000/api/health
# → {"status": "ok", ...}

curl -X POST http://localhost:8000/api/research/discover \
  -H "Content-Type: application/json" \
  -d '{"target_company": "Notion", "competitors": []}'
# → {"suggestions": [...]}
```
