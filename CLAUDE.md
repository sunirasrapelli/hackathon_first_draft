# AI-Powered Financial Report Analysis — Claude Code Context

## What This Project Does

Upload a company's annual report (PDF or JSON) via a web UI. The system:
1. Extracts all three financial statements (Income Statement, Balance Sheet, Cash Flow)
2. Generates investment-grade AI commentary across 7 sections
3. Produces a Word (.docx) report
4. Surfaces 6 prioritised analyst next-step recommendations
5. Provides a contextual chatbot for follow-up questions about the report

No manual analyst work required.

---

## Tech Stack

| Layer | Tool | Notes |
|---|---|---|
| Backend | FastAPI 0.110+ | Background jobs via `BackgroundTasks` |
| AI | Claude claude-sonnet-4-6 | Anthropic SDK — tool use + messages API |
| PDF parsing | pdfplumber + pypdf | Local first; Claude API as fallback gap-fill |
| Report output | python-docx | Word (.docx) |
| Excel output | xlsxwriter | Built but de-wired — see Remaining Work |
| Data models | Pydantic v2 | Full validation; `@model_validator` for BS equations |
| Frontend | Vanilla JS + HTML | Single-file, no framework |
| Language | Python 3.11+ | |

---

## Directory Structure

```
Nurix-2026-Hackathon/
│
├── errors.py                    ← Custom exception hierarchy
├── main.py                      ← CLI entry point
├── requirements.txt
├── .env.example
├── CLAUDE.md                    ← You are here
├── PROJECT_SUMMARY.md           ← Phase-by-phase build history
│
├── config/
│   └── settings.py              ← All constants and thresholds — no magic numbers in code
│
├── agents/
│   ├── extractor.py             ← PDF/JSON → FinancialData (two-pass extraction)
│   ├── analyzer.py              ← Claude API → 7-section commentary + 6 next steps
│   ├── report_generator.py      ← FinancialData + commentary → .docx
│   ├── pdf_parser.py            ← pdfplumber word-position parser (local extraction)
│   ├── excel_builder.py         ← Full Excel workbook (de-wired — see Remaining Work)
│   ├── charts_builder.py        ← Chart embedding for Excel workbook
│   ├── valuation_builder.py     ← DCF, DDM, comparable company valuation sheets
│   └── verifier.py              ← Cross-checks extracted numbers
│
├── models/
│   ├── financial_statements.py  ← IncomeStatement, BalanceSheet, CashFlowStatement
│   └── company_data.py          ← FinancialData + ExtractionMetadata (Pydantic v2)
│
├── schemas/
│   └── extraction_tool_schema.py ← JSON schema for Claude tool-use extraction call
│
├── prompts/
│   ├── extraction_system.txt    ← System prompt for PDF extraction
│   ├── extraction_user.txt      ← User prompt template (company, years, currency, unit)
│   └── verification_system.txt  ← System prompt for extraction verification pass
│
├── utils/
│   ├── logger.py                ← RotatingFileHandler (10 MB, 5 backups), __name__ naming
│   ├── pdf_handler.py           ← PDF load / base64 encoding / page count helpers
│   ├── excel_styles.py          ← Navy/gold Excel styling constants
│   └── formula_registry.py      ← All Excel formulas centralised here
│
├── web/
│   ├── app.py                   ← FastAPI routes + background pipeline orchestration
│   ├── jobs.py                  ← Thread-safe in-memory job store
│   └── static/
│       ├── index.html           ← Drag-drop upload UI (B&W theme) + floating chatbot
│       └── app.js               ← Upload, progress polling, markdown rendering, chat
│
└── tests/
    └── sample_data/
        ├── manual_input_example.json
        └── tcs_fy2022_2024.json
```

---

## Running Locally

```bash
cd "Nurix-2026-Hackathon 11.03.33"
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env

# Web UI (primary)
uvicorn web.app:app --reload --port 8000
# → http://localhost:8000

# CLI
python main.py --input tests/sample_data/tcs_fy2022_2024.json
python main.py --input reports/HDFC_AR.pdf --company "HDFC Bank" --years "2022,2023,2024"
```

---

## Environment Variables

```
ANTHROPIC_API_KEY=sk-ant-...
```

Required for: AI commentary, next steps, chatbot, and Claude API gap-fill extraction.
Not required for: local pdfplumber extraction (Pass 1 always runs without an API key).

---

## How the Pipeline Works

```
PDF(s) / JSON(s)
    │
    ▼
[Extractor — agents/extractor.py]
  ├─ Pass 1: pdfplumber local parser (always — no API needed, exact numbers)
  └─ Pass 2: Claude API gap-fill (only if ANTHROPIC_API_KEY set AND confidence < 75%)
             └─ Large PDFs: TOC page detection → extract only financial statement pages
    │
    ▼
validate_relevance()        ← raises ValidationError for non-financial docs
merge_financial_data()      ← merges multi-file extractions; deduplicates by confidence
    │
    ▼
[Analyzer — agents/analyzer.py]
  generate_commentary()     → Dict[str, str]  (7 sections, ~3000 tokens)
    │
    ├──► [ReportGenerator — agents/report_generator.py] → .docx Word report
    │
    └──► generate_next_steps()  → List[Dict]  (exactly 6 prioritised items)
                │
                ▼
[FastAPI — web/app.py]
  GET  /status/{job_id}          ← progress polling (step-by-step done flags)
  GET  /download/{job_id}/report ← Word report download
  POST /chat/{job_id}            ← chatbot (uses job.commentary as context)
```

### Pipeline steps in `web/app.py`

`_run_pipeline_sync` is split into four focused step functions:

| Function | What it does |
|---|---|
| `_step_extract` | Runs extractor per file, validates, merges |
| `_step_commentary` | Calls `generate_commentary()` → Dict[str, str] |
| `_step_report` | Calls `generate_report()` → `.docx` path |
| `_step_next_steps` | Calls `generate_next_steps()` → List[Dict] |

---

## Extractor Detail (`agents/extractor.py`)

### Two-pass extraction strategy

**Pass 1 — local (always runs)**
`agents/pdf_parser.py` uses pdfplumber word-position detection to find tables and extract numbers. No API cost, no hallucination risk. Produces a `FinancialData` with a confidence score.

**Pass 2 — Claude API gap-fill (conditional)**
Runs only when `ANTHROPIC_API_KEY` is set AND local confidence < `CONFIDENCE_API_FALLBACK` (0.75).
- Large PDFs (> `PDF_SMALL_THRESHOLD` pages): sends first `PDF_TOC_PAGES` pages to Claude to detect which pages contain the financial statements, then extracts only those pages. Avoids sending entire 300-page reports.
- Small PDFs: sends the full document.
- Uses Claude tool-use (`EXTRACTION_TOOL` schema from `schemas/extraction_tool_schema.py`) to force structured JSON output.
- Results are merged with `_merge_extractions()`: local values take priority (exact pixels); API fills only `None` fields.
- Confidence is boosted by `CONFIDENCE_API_BOOST` (×1.10), capped at `CONFIDENCE_API_BOOST_CAP` (0.95).

### `merge_financial_data(data_list)`
When multiple files are uploaded, each file is extracted independently. This function merges them into one `FinancialData` — for duplicate fiscal years, keeps the statement with the higher `extraction_confidence`.

---

## Analyzer Detail (`agents/analyzer.py`)

### `generate_commentary(financial_data) → Dict[str, str]`
Builds a compact JSON summary of key metrics (`_build_data_summary`), sends to Claude with a senior equity analyst system prompt. Returns 7 keys:
`executive_summary`, `revenue_analysis`, `profitability_analysis`, `balance_sheet_analysis`, `cash_flow_analysis`, `key_risks`, `key_strengths`.

### `generate_next_steps(financial_data, commentary) → List[Dict]`
Uses the data summary + executive summary + key risks. Returns exactly 6 items, each with `title`, `description` (citing specific figures), `priority` (high/medium/low). Prompt enforces: ≥1 high, ≥2 medium, ≥1 low.

Both functions use `_parse_json_response()` to strip Markdown code fences before parsing JSON, and are wrapped with `tenacity` retry (up to `RETRY_ATTEMPTS` times, exponential backoff).

---

## Chatbot (`POST /chat/{job_id}`)

Builds a context block from `job.commentary` (the 7-section dict stored at job completion). Sends it as the system prompt alongside conversation history. Capped at `CHAT_MAX_HISTORY_PAIRS` (20) conversation pairs. Will not work if commentary generation failed — `job.commentary` will be empty.

---

## Error Hierarchy (`errors.py`)

All exceptions inherit from `FinAnalysisError`.

| Exception | When raised |
|---|---|
| `ConfigurationError` | Missing API key or invalid config |
| `ExtractionError` | PDF/JSON cannot be read or parsed |
| `ValidationError` | Not a financial doc, or confidence too low |
| `AnalysisError` | Claude API call for commentary/next steps fails |
| `ReportError` | Word report generation fails |

Never catch bare `Exception` in agent code — always raise a typed subclass.

---

## Configuration (`config/settings.py`)

All thresholds are here. Never use magic numbers in code.

| Constant | Default | Purpose |
|---|---|---|
| `CONFIDENCE_API_FALLBACK` | 0.75 | Below this → run Claude gap-fill pass |
| `CONFIDENCE_MIN_ACCEPT` | 0.25 | Below this → reject the document |
| `CONFIDENCE_API_BOOST` | 1.10 | Multiplier after successful gap-fill |
| `CONFIDENCE_API_BOOST_CAP` | 0.95 | Max confidence after boost |
| `MAX_UPLOAD_SIZE_BYTES` | 50 MB | Per-file upload limit |
| `MAX_UPLOAD_FILES` | 10 | Files per request |
| `ERROR_MSG_MAX_LENGTH` | 300 | Chars shown in UI error messages |
| `CHAT_MAX_HISTORY_PAIRS` | 20 | Conversation pairs kept for chatbot context |
| `PDF_SMALL_THRESHOLD` | — | Pages below this → send full PDF to Claude |
| `PDF_TOC_PAGES` | — | Pages sent for TOC/page detection on large PDFs |
| `RETRY_ATTEMPTS` | — | Tenacity retry count for all Claude API calls |
| `RETRY_WAIT_MIN/MAX` | — | Exponential backoff bounds |
| `MODEL_NAME` | claude-sonnet-4-6 | Model used across all API calls |
| `MAX_TOKENS` | — | Max tokens for extraction API calls |

---

## Code Standards

- Full type hints on all public functions
- No mutable default arguments — Pydantic models use `Field(default_factory=...)`
- Thread-safe lazy Anthropic client init with double-checked locking (`threading.Lock`) in both `extractor.py` and `analyzer.py`
- All imports at module level; heavy PDF libs deferred inside background task functions only
- Logger: `get_logger(__name__)` everywhere, `RotatingFileHandler` (10 MB, 5 backups)
- No magic numbers — all thresholds from `config/settings.py`
- `_parse_json_response()` in `analyzer.py` centralises JSON fence-stripping
- Never add `stream=True` to agent API calls — streaming + tool use adds unnecessary complexity

---

## Remaining Work

- **Tests** — `tests/` has sample data but zero pytest files
- **Docker** — no Dockerfile; `uvicorn` runs fine locally
- **Excel pipeline** — `excel_builder.py`, `charts_builder.py`, `valuation_builder.py` are complete but not wired into `main.py` or `web/app.py`
- **Job persistence** — in-memory `_store` in `jobs.py` is wiped on restart; swap for SQLite or Redis
- **Auth** — no authentication on any endpoint; any job ID is publicly accessible

---

## Key Design Decisions

**Why two-pass extraction?**
pdfplumber gives exact pixel-level numbers with zero hallucination risk. The Claude API pass only fills gaps when local confidence is low — keeps cost down, accuracy high.

**Why no LangChain / LlamaIndex?**
Anthropic SDK tool use handles structured extraction cleanly. An extra framework adds complexity with no benefit at this scale.

**Why in-memory job store?**
Zero infra dependencies — fine for demo/hackathon. SQLite (single file, no server) is the logical next step.

**Why Pydantic for financial models?**
Type safety + validation at the boundary. `@model_validator` enforces balance sheet equations; optional fields handle sparse multi-year data.

**Why TOC page detection for large PDFs?**
Sending a full 300-page annual report to Claude wastes tokens and hits context limits. Detecting financial statement page ranges from the TOC first means only 20–40 relevant pages are processed.
