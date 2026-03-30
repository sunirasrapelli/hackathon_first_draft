"""
Top-level container model that groups all three financial statements
for a company, plus extraction metadata.
"""
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel

from models.financial_statements import BalanceSheet, CashFlowStatement, IncomeStatement


class ExtractionMetadata(BaseModel):
    source_type: Literal["pdf", "pdf_local", "manual", "url"] = "pdf"
    extraction_timestamp: datetime = datetime.now()
    model_used: str = "claude-sonnet-4-6"
    overall_confidence: float = 1.0
    warnings: List[str] = []


class FinancialData(BaseModel):
    company_name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    currency: str = "INR"
    unit: str = "Crores"
    fiscal_years: List[int] = []

    income_statements: List[IncomeStatement] = []
    balance_sheets: List[BalanceSheet] = []
    cash_flow_statements: List[CashFlowStatement] = []

    metadata: ExtractionMetadata = ExtractionMetadata()

    def get_income_statement(self, year: int) -> Optional[IncomeStatement]:
        return next((s for s in self.income_statements if s.fiscal_year == year), None)

    def get_balance_sheet(self, year: int) -> Optional[BalanceSheet]:
        return next((s for s in self.balance_sheets if s.fiscal_year == year), None)

    def get_cash_flow(self, year: int) -> Optional[CashFlowStatement]:
        return next((s for s in self.cash_flow_statements if s.fiscal_year == year), None)

    def sorted_years(self) -> List[int]:
        return sorted(self.fiscal_years)
