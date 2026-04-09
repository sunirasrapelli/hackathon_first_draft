# Financial Analysis Automation — Project Summary

> Built by Shikhar Kansal with Claude Code
> Last updated: March 31, 2026

---

## What This Project Does

An AI-powered system that takes a company's annual report (PDF or JSON) and:
1. **Extracts** all three financial statements (Income Statement, Balance Sheet, Cash Flow)
2. **Builds** a professional Excel workbook with live formulas — exactly how an investment banker would
3. **Calculates** 20+ financial ratios, DCF valuation, DDM, and comparable company analysis
4. **Verifies** every number twice (cross-checks balance sheet equation, cash reconciliation, etc.)
5. **Generates** a Word report with AI-written commentary on the company's financial health
6. **Serves** everything through a web UI — drag-drop a PDF, get Excel + report back

---

## Project Structure

```
Financial-automation/
│
├── agents/                      # Core pipeline agents
│   ├── extractor.py             # Extracts financials from PDF/JSON via Claude API
│   ├── excel_builder.py         # Builds the full Excel workbook (IS, BS, CF, Ratios, Valuation)
│   ├── charts_builder.py        # Embeds charts into Excel (revenue trends, margins, etc.)
│   ├── valuation_builder.py     # DCF, DDM, Comparable company valuation sheet
│   ├── verifier.py              # Cross-checks all numbers for accuracy
│   ├── analyzer.py              # Generates AI commentary via Claude API
│   ├── report_generator.py      # Creates the final Word (.docx) report
│   └── pdf_parser.py            # PDF text/table extraction (pdfplumber + pymupdf)
│
├── models/                      # Data models (Pydantic)
│   ├── financial_statements.py  # IncomeStatement, BalanceSheet, CashFlow models
│   ├── company_data.py          # CompanyData — the central data object
│   └── extraction_result.py     # ExtractionResult with confidence scores
│
├── utils/
│   ├── excel_styles.py          # Navy/gold color scheme, fonts, borders
│   ├── formula_registry.py      # All Excel formulas in one place
│   └── logger.py                # Logging setup
│
├── schemas/
│   └── extraction_tool_schema.py  # JSON schema for Claude's tool-use extraction
│
├── prompts/
│   ├── extraction_system.txt    # System prompt for financial extraction
│   ├── extraction_user.txt      # User prompt template
│   └── verification_system.txt  # System prompt for verification
│
├── config/
│   └── settings.py              # API keys, output paths, model settings
│
├── web/                         # Phase 5 — Web Frontend
│   ├── app.py                   # FastAPI backend (upload, status, download routes)
│   ├── jobs.py                  # In-memory job store with progress tracking
│   └── static/
│       ├── index.html           # Drag-drop upload UI (navy/gold theme)
│       └── app.js               # Polling, progress bar, download logic
│
├── tests/
│   └── sample_data/
│       ├── manual_input_example.json   # Example JSON input for testing
│       └── tcs_fy2022_2024.json        # TCS multi-year sample dataset
│
├── outputs/                     # Generated files (gitignored)
│   ├── excel/                   # .xlsx workbooks
│   ├── reports/                 # .docx Word reports
│   └── logs/                    # Run logs
│
├── main.py                      # CLI entry point
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
└── PROJECT_SUMMARY.md           # This file
```

---

## Phases Completed

### Phase 1 — Core Pipeline (CLI) ✅
- Data models for all 3 financial statements
- Hybrid PDF extractor: local pdfplumber parser runs first (no API needed); Claude API used only as a fallback gap-fill pass when local confidence < 75%
- `validate_relevance()` guard — rejects non-financial documents before processing
- `merge_financial_data()` — merges multiple per-year FinancialData objects into one combined dataset (deduplicates by confidence)
- JSON manual input support
- Logging and output management

### Phase 2 — Excel Workbook Builder ✅
- **Income Statement sheet** — Revenue, EBITDA, PAT with 5-year trends
- **Balance Sheet sheet** — Assets, Liabilities, Equity with proper grouping
- **Cash Flow sheet** — CFO, CFI, CFF with FCF calculation
- **Ratios sheet** — 20+ ratios: liquidity, profitability, leverage, efficiency
- **Valuation sheet** — DCF (WACC, terminal value), DDM, Comparable multiples, sensitivity table
- **Cover sheet** — Company overview, key metrics snapshot
- Professional navy/gold formatting matching investment bank style
- All cells use live Excel formulas (no hardcoded values)
- Double-verification: balance sheet equation check, cash reconciliation

### Phase 3 — Charts ✅
- Revenue & EBITDA trend (column chart)
- Margin trends — Gross, EBITDA, Net (line chart)
- Cash flow breakdown — CFO, CFI, CFF (clustered column)
- Return metrics — ROE, ROA, ROCE (line chart)
- All charts embedded in the Excel workbook on a dedicated Charts sheet

### Phase 4 — Word Report ✅
- Executive Summary
- Income Statement analysis section
- Balance Sheet health section
- Cash Flow analysis section
- Ratio commentary
- Valuation summary
- AI-generated commentary (Claude claude-sonnet-4-6) — requires `ANTHROPIC_API_KEY`
- Falls back to template commentary if no API key is set
- **AI Next Steps** (`generate_next_steps()`): generates exactly 6 prioritised analyst recommendations (title, 2-sentence description, priority: high/medium/low) grounded in the company's actual numbers

### Phase 5 — Web Frontend ✅
- FastAPI backend with background job processing
- **Multi-file upload**: accepts multiple PDFs or JSONs in one request; extracts each, validates relevance, then merges into a single dataset
- Drag-and-drop PDF/JSON upload (navy/gold UI — `index.html` + `app.js` complete)
- Real-time progress tracking (step-by-step polling with done flags)
- Download link for Word report
- AI next-steps surface in the results panel (priority-tagged cards)
- Error handling with clean messages (HTML stripped from API errors, capped at 300 chars)
- Job store exposes `next_steps` field via `/status/{job_id}`

---

## How to Run

### Setup
```bash
cd Financial-automation
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

### CLI (direct)
```bash
# From a JSON file (auto-detected by .json extension)
python main.py --input tests/sample_data/tcs_fy2022_2024.json

# From a PDF
python main.py --input path/to/annual_report.pdf --company "Sun Pharma" --years "2022,2023,2024"

# Skip Word report (Excel only)
python main.py --input report.pdf --company "HDFC Bank" --years "2023,2024" --no-report
```

### Web UI
```bash
uvicorn web.app:app --reload --port 8000
# Open http://localhost:8000
```

---

## Key Tech Stack

| Purpose | Library |
|---------|---------|
| AI extraction & commentary | `anthropic` (Claude claude-sonnet-4-6) |
| PDF text extraction | `pdfplumber`, `pymupdf` |
| Excel generation | `xlsxwriter` |
| Word report | `python-docx` |
| Web backend | `fastapi`, `uvicorn` |
| Data validation | `pydantic` |
| Environment config | `python-dotenv` |

---

## Sample Output Files

- `outputs/excel/Infosys_Limited_20260327_130324.xlsx` — full 7-sheet workbook
- `outputs/reports/Infosys_Limited_Report_20260327_130329.docx` — Word report
- `outputs/excel/SUNPHARMA_20260327_145338.xlsx` — Sun Pharma workbook
- `outputs/reports/SUNPHARMA_Report_20260327_145343.docx` — Sun Pharma report

---

## Remaining Work

- [ ] **PDF extractor accuracy** — pdfplumber can lose row labels & prior-year column on complex multi-column layouts; word-position-based column detection would improve confidence scores
- [ ] **Excel workbook** — `excel_builder.py` exists but the CLI and web pipeline no longer invoke it; re-wire if Excel download is needed again
- [ ] **Charts in Word report** — embed chart images from Excel into the Word doc
- [ ] **Persistent job store** — current in-memory store is lost on server restart; back with Redis or Supabase for production
- [ ] **API key** — add `ANTHROPIC_API_KEY` to `.env` to unlock AI commentary and next steps

---

## Architecture Overview

```
PDF(s) / JSON(s)
    │
    ▼
[Extractor — per file]
  ├─ Pass 1: pdfplumber local parser (always, no API needed)
  └─ Pass 2: Claude API gap-fill (only if confidence < 75%)
    │
    ▼
[validate_relevance()]  ── rejects non-financial docs
    │
    ▼
[merge_financial_data()]  ── combines multi-file extractions
    │
    ▼
[Analyzer] ──Claude API──► Commentary dict (7 sections)
    │
    ├──► [Report Generator] ──python-docx──► .docx Word report
    │
    └──► [Analyzer] ──Claude API──► Next Steps (6 prioritised items)
                │
                ▼
[Web API] ──FastAPI──► /download/{id}/report + next_steps in /status/{id}
```
