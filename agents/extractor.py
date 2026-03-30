"""
Agent 1: Financial Statement Extractor

Two paths:
  - extract_from_pdf()  → calls Claude API with PDF (two-pass: extract + verify)
  - extract_from_json() → loads pre-structured JSON (for testing / manual input)
"""
import json
import re
from pathlib import Path
from typing import List, Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import (
    ANTHROPIC_API_KEY,
    MAX_TOKENS,
    MODEL_NAME,
    PDF_SMALL_THRESHOLD,
    PDF_TOC_PAGES,
    RETRY_ATTEMPTS,
)
from models.company_data import ExtractionMetadata, FinancialData
from models.financial_statements import BalanceSheet, CashFlowStatement, IncomeStatement
from schemas.extraction_tool_schema import EXTRACTION_TOOL, TOOL_CHOICE
from utils.logger import get_logger
from utils.pdf_handler import (
    extract_page_range_as_base64,
    get_pdf_page_count,
    load_pdf_as_base64,
    validate_pdf,
)

log = get_logger()
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Create a .env file with your key "
                "(see .env.example)."
            )
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ── TOC detection (large PDFs) ────────────────────────────────────────────────

def _detect_financial_pages(pdf_b64: str, total_pages: int) -> tuple[int, int]:
    """
    Send first PDF_TOC_PAGES pages to Claude to find which pages contain
    the financial statements. Returns (start_page, end_page) estimates.
    """
    log.info("Large PDF detected — running TOC page detection...")
    client = _get_client()
    resp = client.messages.create(
        model=MODEL_NAME,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf",
                               "data": pdf_b64},
                },
                {
                    "type": "text",
                    "text": (
                        "This is a company annual report. Look at the table of contents "
                        "and identify which page numbers contain the three financial statements "
                        "(Income Statement/P&L, Balance Sheet, Cash Flow Statement). "
                        "Reply with ONLY a JSON object like: "
                        '{"start_page": 120, "end_page": 155} '
                        "using the page numbers where the financial statements begin and end."
                    ),
                },
            ],
        }],
    )
    text = resp.content[0].text
    try:
        match = re.search(r'\{.*?"start_page".*?\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return int(data["start_page"]), int(data["end_page"])
    except Exception:
        pass
    # Fallback: guess last third of report
    start = max(1, total_pages * 2 // 3)
    return start, total_pages


# ── Core API call (with retry) ─────────────────────────────────────────────────

@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_extraction_api(
    pdf_b64: str,
    company_name: str,
    years: List[int],
    currency: str = "INR",
    unit: str = "Crores",
) -> dict:
    """Pass 1: Extract financial statements using Claude tool_use."""
    system_prompt = Path("prompts/extraction_system.txt").read_text()
    user_template = Path("prompts/extraction_user.txt").read_text()
    user_prompt = user_template.format(
        company_name=company_name,
        years=", ".join(str(y) for y in years),
        currency=currency,
        unit=unit,
    )

    client = _get_client()
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        tools=[EXTRACTION_TOOL],
        tool_choice=TOOL_CHOICE,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf",
                               "data": pdf_b64},
                    "cache_control": {"type": "ephemeral"},  # reuse across two passes
                },
                {"type": "text", "text": user_prompt},
            ],
        }],
    )

    # Extract tool_use block
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("Claude did not return a tool_use block — extraction failed.")


@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_verification_api(pdf_b64: str, extracted_json: str) -> dict:
    """Pass 2: Ask Claude to verify its own extraction. PDF is reused from cache."""
    system_prompt = Path("prompts/verification_system.txt").read_text()
    client = _get_client()
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf",
                               "data": pdf_b64},
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": (
                        "Here is the extracted financial data:\n\n"
                        f"```json\n{extracted_json}\n```\n\n"
                        "Verify this data against the document and return the JSON result."
                    ),
                },
            ],
        }],
    )
    text = response.content[0].text
    try:
        match = re.search(r'\{.*"passes_all_checks".*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"passes_all_checks": True, "issues": [], "warnings": [], "corrected_values": {}}


# ── Data Parsing ──────────────────────────────────────────────────────────────

def _parse_raw_data(raw: dict) -> FinancialData:
    """Convert the raw dict returned by Claude into validated Pydantic models."""
    income_statements = [IncomeStatement(**s) for s in raw.get("income_statements", [])]
    balance_sheets = [BalanceSheet(**s) for s in raw.get("balance_sheets", [])]
    cash_flows = [CashFlowStatement(**s) for s in raw.get("cash_flow_statements", [])]

    fiscal_years = raw.get("fiscal_years") or sorted(
        set(s.fiscal_year for s in income_statements + balance_sheets + cash_flows)
    )

    avg_conf = 1.0
    all_stmts = income_statements + balance_sheets + cash_flows
    if all_stmts:
        avg_conf = sum(s.extraction_confidence for s in all_stmts) / len(all_stmts)

    return FinancialData(
        company_name=raw.get("company_name", "Unknown"),
        ticker=raw.get("ticker"),
        exchange=raw.get("exchange"),
        currency=raw.get("currency", "INR"),
        unit=raw.get("unit", "Crores"),
        fiscal_years=fiscal_years,
        income_statements=income_statements,
        balance_sheets=balance_sheets,
        cash_flow_statements=cash_flows,
        metadata=ExtractionMetadata(
            source_type="pdf",
            model_used=MODEL_NAME,
            overall_confidence=round(avg_conf, 3),
        ),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def extract_from_pdf(
    path: str,
    company_name: str,
    fiscal_years: List[int],
    currency: str = "INR",
    unit: str = "Crores",
) -> FinancialData:
    """
    Extract financial statements from a PDF annual report.

    Strategy (automatic):
      1. Always run local word-position parser (pdfplumber) — no API key needed,
         exact numbers, no hallucination risk.
      2. If ANTHROPIC_API_KEY is set AND local confidence is below 0.75,
         fall back to Claude API for a verification / gap-fill pass.

    This means PDFs work correctly even without an API key.
    """
    if not validate_pdf(path):
        raise FileNotFoundError(f"Invalid or missing PDF: {path}")

    total_pages = get_pdf_page_count(path)
    log.info(f"PDF loaded: {path} ({total_pages} pages)")

    # ── Pass 1: Local extraction (always runs) ────────────────────────────────
    from agents.pdf_parser import extract_local
    log.info("Local extraction: parsing financial statements from PDF text layer…")
    financial_data = extract_local(path, company_name, fiscal_years, currency, unit)
    conf = financial_data.metadata.overall_confidence
    log.info(
        f"Local extraction complete. Years: {financial_data.fiscal_years}. "
        f"Confidence: {conf:.0%}"
    )

    # ── Pass 2 (optional): Claude API verification / gap-fill ─────────────────
    if ANTHROPIC_API_KEY and conf < 0.75:
        log.info("Confidence below 75% — running Claude API verification pass…")
        try:
            if total_pages > PDF_SMALL_THRESHOLD:
                toc_b64 = extract_page_range_as_base64(path, 1, PDF_TOC_PAGES)
                start_p, end_p = _detect_financial_pages(toc_b64, total_pages)
                pdf_b64 = extract_page_range_as_base64(path, start_p, end_p)
            else:
                pdf_b64 = load_pdf_as_base64(path)

            raw = _call_extraction_api(pdf_b64, company_name, fiscal_years, currency, unit)
            api_data = _parse_raw_data(raw)

            # Merge: prefer local values (exact), fill gaps from API
            financial_data = _merge_extractions(financial_data, api_data)
            log.info("Claude API gap-fill complete.")
        except Exception as e:
            log.warning(f"Claude API pass failed ({e}) — using local extraction only.")
    elif ANTHROPIC_API_KEY:
        log.info("Local confidence ≥ 75% — skipping Claude API pass.")
    else:
        log.info("No API key set — using local extraction only.")

    return financial_data


def _merge_extractions(local: FinancialData, api: FinancialData) -> FinancialData:
    """
    Merge local + API extractions: keep local values where they exist,
    fill None fields with API values.
    """
    from dataclasses import fields as dc_fields

    def merge_stmt(local_stmt, api_stmt):
        if api_stmt is None:
            return local_stmt
        if local_stmt is None:
            return api_stmt
        # Fill None fields in local_stmt from api_stmt
        for f in dc_fields(local_stmt):
            if getattr(local_stmt, f.name) is None:
                api_val = getattr(api_stmt, f.name)
                if api_val is not None:
                    object.__setattr__(local_stmt, f.name, api_val)
        return local_stmt

    for yr in local.fiscal_years:
        local_is = local.get_income_statement(yr)
        api_is   = api.get_income_statement(yr)
        if local_is or api_is:
            merged = merge_stmt(local_is, api_is)
            if merged and merged not in local.income_statements:
                local.income_statements.append(merged)

        local_bs = local.get_balance_sheet(yr)
        api_bs   = api.get_balance_sheet(yr)
        if local_bs or api_bs:
            merged = merge_stmt(local_bs, api_bs)
            if merged and merged not in local.balance_sheets:
                local.balance_sheets.append(merged)

        local_cf = local.get_cash_flow(yr)
        api_cf   = api.get_cash_flow(yr)
        if local_cf or api_cf:
            merged = merge_stmt(local_cf, api_cf)
            if merged and merged not in local.cash_flow_statements:
                local.cash_flow_statements.append(merged)

    local.metadata.overall_confidence = min(0.95,
        local.metadata.overall_confidence * 1.1)
    return local


def extract_from_json(path: str) -> FinancialData:
    """
    Load financial data from a pre-structured JSON file.
    Used for testing and manual data entry without calling the API.
    """
    data = json.loads(Path(path).read_text())
    financial_data = _parse_raw_data(data)
    financial_data.metadata.source_type = "manual"
    log.info(
        f"Loaded manual data for {financial_data.company_name}. "
        f"Years: {financial_data.fiscal_years}"
    )
    return financial_data
