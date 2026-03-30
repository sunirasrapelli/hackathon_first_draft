"""
Phase 4 — Analyzer Agent

Calls Claude API to generate professional investment-banking-style
commentary sections from the extracted financial data.

Returns a structured dict of text blocks used by the report generator.
"""
import json
from typing import Any, Dict, List, Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import ANTHROPIC_API_KEY, MAX_TOKENS, MODEL_NAME
from models.company_data import FinancialData
from models.financial_statements import BalanceSheet, CashFlowStatement, IncomeStatement
from utils.logger import get_logger

log = get_logger()
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set — cannot generate commentary.")
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _build_data_summary(fd: FinancialData) -> str:
    """Serialize key financial metrics into a compact JSON for the prompt."""
    years = fd.sorted_years()
    summary: Dict[str, Any] = {
        "company": fd.company_name,
        "ticker": fd.ticker,
        "currency": fd.currency,
        "unit": fd.unit,
        "fiscal_years": years,
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
    }

    for yr in years:
        is_s = fd.get_income_statement(yr)
        bs_s = fd.get_balance_sheet(yr)
        cf_s = fd.get_cash_flow(yr)

        if is_s:
            summary["income_statement"][yr] = {
                "revenue": is_s.revenue,
                "ebitda": is_s.ebitda,
                "ebit": is_s.ebit,
                "pat": is_s.pat,
                "interest_expense": is_s.interest_expense,
                "depreciation_amortization": is_s.depreciation_amortization,
            }
        if bs_s:
            total_debt = (bs_s.long_term_debt or 0) + (bs_s.short_term_borrowings or 0)
            net_debt = total_debt - (bs_s.cash_and_equivalents or 0) - (bs_s.short_term_investments or 0)
            summary["balance_sheet"][yr] = {
                "total_assets": bs_s.total_assets,
                "total_equity": bs_s.total_equity,
                "total_debt": total_debt,
                "net_debt": net_debt,
                "working_capital": (bs_s.total_current_assets or 0) - (bs_s.total_current_liabilities or 0),
            }
        if cf_s:
            summary["cash_flow"][yr] = {
                "cfo": cf_s.cash_from_operations,
                "capex": cf_s.capex,
                "fcf": cf_s.free_cash_flow,
            }

    # Derived ratios (latest year)
    latest = years[-1] if years else None
    if latest:
        is_l = fd.get_income_statement(latest)
        bs_l = fd.get_balance_sheet(latest)
        if is_l and bs_l and is_l.revenue:
            total_debt_l = (bs_l.long_term_debt or 0) + (bs_l.short_term_borrowings or 0)
            summary["latest_ratios"] = {
                "gross_margin": round((is_l.gross_profit or 0) / is_l.revenue, 3) if is_l.gross_profit else None,
                "ebitda_margin": round((is_l.ebitda or 0) / is_l.revenue, 3) if is_l.ebitda else None,
                "net_margin": round((is_l.pat or 0) / is_l.revenue, 3) if is_l.pat else None,
                "roe": round((is_l.pat or 0) / (bs_l.total_equity or 1), 3) if bs_l.total_equity else None,
                "roa": round((is_l.pat or 0) / (bs_l.total_assets or 1), 3) if bs_l.total_assets else None,
                "de_ratio": round(total_debt_l / (bs_l.total_equity or 1), 2) if bs_l.total_equity else None,
            }

    return json.dumps(summary, indent=2, default=str)


_ANALYSIS_SYSTEM = """You are a senior equity research analyst at a top-tier investment bank.
You write precise, insightful, data-driven financial commentary in a professional but readable style.
Your analysis should:
- Lead with the most important insight for each section
- Reference specific numbers (% margins, growth rates, ratios) with context
- Note trends across years — improving, declining, stable
- Highlight risks and strengths
- Keep each section to 2–3 concise paragraphs
- Never use vague filler phrases ("it can be seen that...", "as shown above...")
- Write in present tense referring to the company's reported performance
"""

_ANALYSIS_USER = """Analyse the following financial data and produce commentary for each section.
Return a JSON object with these exact keys:
{{
  "executive_summary": "2-3 paragraphs — overall financial health, key themes",
  "revenue_analysis": "2 paragraphs — revenue growth, drivers, trends",
  "profitability_analysis": "2 paragraphs — margins, EBITDA, PAT, quality of earnings",
  "balance_sheet_analysis": "2 paragraphs — asset quality, leverage, working capital",
  "cash_flow_analysis": "2 paragraphs — CFO quality, FCF generation, capex discipline",
  "key_risks": "3–4 bullet points as a single string separated by newlines, each starting with •",
  "key_strengths": "3–4 bullet points as a single string separated by newlines, each starting with •"
}}

Financial Data:
{data}
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def generate_commentary(financial_data: FinancialData) -> Dict[str, str]:
    """
    Call Claude to generate investment-banking-style commentary.
    Returns a dict with keys: executive_summary, revenue_analysis, etc.
    Falls back to placeholder text if the API call fails.
    """
    log.info("Generating financial commentary via Claude API...")
    data_summary = _build_data_summary(financial_data)
    user_prompt = _ANALYSIS_USER.format(data=data_summary)

    client = _get_client()
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=3000,
        system=_ANALYSIS_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = response.content[0].text.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    commentary = json.loads(text)
    log.info("Commentary generated successfully.")
    return commentary


def generate_commentary_safe(financial_data: FinancialData) -> Dict[str, str]:
    """Wrapper that falls back to placeholder text on any error."""
    try:
        return generate_commentary(financial_data)
    except Exception as e:
        log.warning(f"Commentary generation failed ({e}) — using placeholders.")
        return {
            "executive_summary": (
                f"{financial_data.company_name} financial analysis covers "
                f"{', '.join(str(y) for y in financial_data.sorted_years())}. "
                "Please refer to the Excel workbook for detailed metrics and ratios."
            ),
            "revenue_analysis": "See Income Statement sheet for revenue trend analysis.",
            "profitability_analysis": "See Ratios sheet for margin and profitability analysis.",
            "balance_sheet_analysis": "See Balance Sheet and Ratios sheets for leverage analysis.",
            "cash_flow_analysis": "See Cash Flow sheet for FCF and cash conversion analysis.",
            "key_risks": "• Data sourced from company filings — verify independently\n• Forward projections are estimates based on historical trends",
            "key_strengths": "• Analysis generated from audited financial statements\n• Multiple valuation methods applied (DCF, DDM, Comps)",
        }
