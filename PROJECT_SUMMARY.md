# Financial Analysis Automation — Project Summary

> Built by Shikhar Kansal with Claude Code
> Last updated: March 30, 2026

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
│       └── manual_input_example.json   # Example JSON input for testing
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
- Claude API-based extractor (PDF → structured JSON)
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

### Phase 5 — Web Frontend ✅ (in progress)
- FastAPI backend with background job processing
- Drag-and-drop PDF/JSON upload
- Real-time progress tracking (polling)
- Download links for Excel + Word report
- Error handling with clean messages

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
# From a JSON file
python main.py --input tests/sample_data/manual_input_example.json

# From a PDF
python main.py --pdf path/to/annual_report.pdf --company "Sun Pharma" --years 2023 2024
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

- [ ] **PDF extractor improvement** — pdfplumber loses row labels & prior-year column on complex layouts; need word-position-based column detection
- [ ] **Web frontend** — `index.html` and `app.js` still need to be written
- [ ] **API key** — add `ANTHROPIC_API_KEY` to `.env` to unlock AI commentary
- [ ] **Charts in Word report** — embed chart images from Excel into the Word doc
- [ ] **Multi-year PDF support** — extract 3–5 year history from a single PDF

---

## Architecture Overview

```
PDF / JSON
    │
    ▼
[Extractor] ──Claude API──► FinancialData object
    │
    ▼
[Excel Builder] ──xlsxwriter──► .xlsx (IS + BS + CF + Ratios + Valuation + Charts)
    │
    ▼
[Verifier] ──cross-checks──► VerificationReport (pass/fail + issues)
    │
    ▼
[Analyzer] ──Claude API──► Commentary dict (section-by-section text)
    │
    ▼
[Report Generator] ──python-docx──► .docx Word report
    │
    ▼
[Web API] ──FastAPI──► Download links for both files
```
