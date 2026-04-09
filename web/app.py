"""
FastAPI web server — Financial Analysis AI

Routes
------
GET  /                         Serve the upload UI
POST /analyze                  Start a background analysis job
GET  /status/{job_id}          Poll job status and progress
GET  /download/{job_id}/report Download the generated Word report
POST /chat/{job_id}            Chatbot: answer questions about the report
GET  /health                   Health check
"""
import asyncio
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import anthropic
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    ANTHROPIC_API_KEY,
    ERROR_MSG_MAX_LENGTH,
    MAX_UPLOAD_FILES,
    MAX_UPLOAD_SIZE_BYTES,
    MODEL_NAME,
)
from errors import AnalysisError, ExtractionError, ReportError, ValidationError
from web.jobs import Job, create_job, get_job

# ── Constants ─────────────────────────────────────────────────────────────────
UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# Commentary section keys and their display labels (shared with chat endpoint)
COMMENTARY_SECTIONS: Dict[str, str] = {
    "executive_summary":      "Executive Summary",
    "revenue_analysis":       "Revenue Analysis",
    "profitability_analysis": "Profitability Analysis",
    "balance_sheet_analysis": "Balance Sheet Analysis",
    "cash_flow_analysis":     "Cash Flow Analysis",
    "key_risks":              "Key Risks",
    "key_strengths":          "Key Strengths",
}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Financial Analysis AI", version="1.0")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "time": datetime.now().isoformat()}


# ── Serve UI ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ── Start Analysis Job ────────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    files:    List[UploadFile] = File(...),
    company:  str              = Form(""),
    years:    str              = Form(""),
    currency: str              = Form("INR"),
    unit:     str              = Form("Crores"),
) -> JSONResponse:
    if not files:
        raise HTTPException(400, "At least one file is required.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(400, f"Maximum {MAX_UPLOAD_FILES} files per request.")

    job           = create_job()
    saved_paths:   List[str]  = []
    is_json_flags: List[bool] = []

    for i, file in enumerate(files):
        filename = file.filename or ""
        is_json  = filename.endswith(".json")
        is_pdf   = filename.endswith(".pdf")

        if not (is_json or is_pdf):
            raise HTTPException(
                400, f"Unsupported file type: '{filename}'. Only .pdf or .json are accepted."
            )
        if is_pdf and not company.strip():
            raise HTTPException(400, "Company name is required for PDF uploads.")

        # Enforce upload size limit
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            size_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise HTTPException(400, f"'{filename}' exceeds the {size_mb} MB upload limit.")

        suffix     = ".json" if is_json else ".pdf"
        saved_path = UPLOADS_DIR / f"{job.id}_{i}{suffix}"
        saved_path.write_bytes(content)

        saved_paths.append(str(saved_path))
        is_json_flags.append(is_json)

    fiscal_years: List[int] = []
    if years.strip():
        try:
            fiscal_years = [int(y.strip()) for y in years.split(",") if y.strip()]
        except ValueError:
            raise HTTPException(
                400, "Years must be comma-separated integers, e.g. 2022,2023,2024"
            )

    background_tasks.add_task(
        _run_pipeline,
        job=job,
        file_paths=saved_paths,
        is_json_flags=is_json_flags,
        company=company.strip(),
        fiscal_years=fiscal_years,
        currency=currency,
        unit=unit,
    )
    return JSONResponse({"job_id": job.id})


# ── Background Pipeline ───────────────────────────────────────────────────────

async def _run_pipeline(
    job:           Job,
    file_paths:    List[str],
    is_json_flags: List[bool],
    company:       str,
    fiscal_years:  List[int],
    currency:      str,
    unit:          str,
) -> None:
    """Dispatch the synchronous pipeline to a thread-pool executor."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _run_pipeline_sync,
        job, file_paths, is_json_flags, company, fiscal_years, currency, unit,
    )


def _run_pipeline_sync(
    job:           Job,
    file_paths:    List[str],
    is_json_flags: List[bool],
    company:       str,
    fiscal_years:  List[int],
    currency:      str,
    unit:          str,
) -> None:
    """Synchronous pipeline — runs inside a thread-pool executor."""
    job.status = "running"

    try:
        financial_data = _step_extract(
            job, file_paths, is_json_flags, company, fiscal_years, currency, unit
        )
        commentary  = _step_commentary(job, financial_data)
        report_path = _step_report(job, financial_data, commentary)
        next_steps  = _step_next_steps(job, financial_data, commentary)

        job.files        = {"report": report_path}
        job.commentary   = commentary
        job.company_name = financial_data.company_name
        job.next_steps   = next_steps
        job.status       = "done"
        job.finished_at  = datetime.now().isoformat()

    except (ExtractionError, ValidationError, AnalysisError, ReportError) as exc:
        _fail_job(job, str(exc))
    except Exception as exc:
        _fail_job(job, _sanitise_error(str(exc)))
    finally:
        _cleanup_uploads(file_paths)


def _step_extract(
    job:           Job,
    file_paths:    List[str],
    is_json_flags: List[bool],
    company:       str,
    fiscal_years:  List[int],
    currency:      str,
    unit:          str,
):
    """Extract and merge financial data from all uploaded files."""
    from agents.extractor import (
        extract_from_json,
        extract_from_pdf,
        merge_financial_data,
        validate_relevance,
    )
    from models.company_data import FinancialData

    n = len(file_paths)
    job.log("extract", f"Extracting from {n} file(s)…")

    all_data = []
    for i, (fp, is_json) in enumerate(zip(file_paths, is_json_flags)):
        job.log("extract", f"Processing file {i + 1}/{n}…")
        if is_json:
            fd = extract_from_json(fp)
        else:
            fd = extract_from_pdf(
                path=fp,
                company_name=company,
                fiscal_years=fiscal_years or list(range(2022, 2025)),
                currency=currency,
                unit=unit,
            )
        validate_relevance(fd, Path(fp).name)
        all_data.append(fd)

    financial_data: FinancialData = merge_financial_data(all_data)
    job.log(
        "extract",
        f"Extracted {len(financial_data.sorted_years())} year(s) for "
        f"{financial_data.company_name} "
        f"(confidence: {financial_data.metadata.overall_confidence:.0%})",
        done=True,
    )
    return financial_data


def _step_commentary(job: Job, financial_data) -> Dict[str, str]:
    """Generate AI commentary sections via Claude."""
    from agents.analyzer import generate_commentary

    job.log("commentary", "Generating AI commentary…")
    commentary = generate_commentary(financial_data)
    job.log("commentary", "AI commentary generated ✓", done=True)
    return commentary


def _step_report(job: Job, financial_data, commentary: Dict[str, str]) -> str:
    """Build the Word report and return its path."""
    from agents.report_generator import generate_report

    job.log("report", "Building Word report…")
    report_path: str = generate_report(financial_data, commentary)
    job.log("report", f"Report built — {Path(report_path).name}", done=True)
    return report_path


def _step_next_steps(
    job: Job, financial_data, commentary: Dict[str, str]
) -> List[Dict[str, str]]:
    """Generate prioritised AI next-step recommendations."""
    from agents.analyzer import generate_next_steps

    job.log("next_steps", "Generating AI next steps…")
    next_steps = generate_next_steps(financial_data, commentary)
    job.log("next_steps", f"{len(next_steps)} next steps generated ✓", done=True)
    return next_steps


# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _fail_job(job: Job, message: str) -> None:
    job.log("error", message)
    job.status      = "error"
    job.error       = message
    job.finished_at = datetime.now().isoformat()


def _sanitise_error(raw: str) -> str:
    """Strip HTML tags and collapse whitespace from an error message."""
    clean = re.sub(r"<[^>]+>", "", raw).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:ERROR_MSG_MAX_LENGTH] or "An unexpected error occurred."


def _cleanup_uploads(file_paths: List[str]) -> None:
    for fp in file_paths:
        try:
            Path(fp).unlink(missing_ok=True)
        except OSError:
            pass


# ── Poll Status ───────────────────────────────────────────────────────────────

@app.get("/status/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JSONResponse(job.to_dict())


# ── Download Files ────────────────────────────────────────────────────────────

@app.get("/download/{job_id}/excel")
def download_excel(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "File not ready")
    path = job.files.get("excel")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Excel file not found")
    return FileResponse(
        path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=Path(path).name,
    )


@app.get("/download/{job_id}/report")
def download_report(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "File not ready")
    path = job.files.get("report")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Report file not found")
    return FileResponse(
        path,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        filename=Path(path).name,
    )


# ── Chatbot ───────────────────────────────────────────────────────────────────

class _ChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


class _ChatRequest(BaseModel):
    message: str
    history: List[_ChatMessage] = []


@app.post("/chat/{job_id}")
def chat(job_id: str, body: _ChatRequest) -> JSONResponse:
    job = get_job(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "Analysis not found or not yet complete")
    if not job.commentary:
        raise HTTPException(400, "No analysis context is available for this job")
    if not ANTHROPIC_API_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured on this server")

    # Build a readable context block from the stored commentary
    context = "\n\n".join(
        f"### {label}\n{job.commentary[key]}"
        for key, label in COMMENTARY_SECTIONS.items()
        if key in job.commentary and job.commentary[key]
    )

    system_prompt = (
        f"You are a financial analyst assistant. You have just completed an "
        f"AI-generated analysis of {job.company_name or 'this company'}. "
        f"Answer the user's questions using only the analysis below. "
        f"Be concise and precise. Reference specific figures or sections where relevant.\n\n"
        f"--- ANALYSIS REPORT ---\n{context}\n--- END OF REPORT ---"
    )

    messages = [{"role": m.role, "content": m.content} for m in body.history]
    messages.append({"role": "user", "content": body.message})

    client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    return JSONResponse({"reply": response.content[0].text})
