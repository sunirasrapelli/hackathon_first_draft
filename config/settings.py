import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
EXCEL_DIR = OUTPUTS_DIR / "excel"
REPORTS_DIR = OUTPUTS_DIR / "reports"
LOGS_DIR = OUTPUTS_DIR / "logs"

for _d in (EXCEL_DIR, REPORTS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Anthropic ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME: str = "claude-sonnet-4-6"
MAX_TOKENS: int = 8192
RETRY_ATTEMPTS: int = 3
RETRY_WAIT_SECONDS: float = 2.0

# ── PDF Handling ─────────────────────────────────────────────────────────────
PDF_SMALL_THRESHOLD: int = 60   # pages — send whole PDF if ≤ this
PDF_TOC_PAGES: int = 15         # pages sent for table-of-contents detection

# ── Financial Defaults (used in Settings sheet and Phase-3 valuation) ────────
RISK_FREE_RATE: float = 0.067        # 6.7% (Indian 10Y Gsec approx)
EQUITY_RISK_PREMIUM: float = 0.055   # 5.5%
DEFAULT_BETA: float = 1.0
CORPORATE_TAX_RATE: float = 0.25     # 25% (India base rate)
TERMINAL_GROWTH_RATE: float = 0.04   # 4%

# ── Excel Visual Theme ───────────────────────────────────────────────────────
COLOR_NAVY = "#1F3864"
COLOR_GOLD = "#C9A84C"
COLOR_LIGHT_BLUE = "#EBF3FB"
COLOR_WHITE = "#FFFFFF"
COLOR_PASS_GREEN = "#C6EFCE"
COLOR_FAIL_RED = "#FFC7CE"
COLOR_SECTION_GRAY = "#D9D9D9"
