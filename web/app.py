"""
Phase 5 — FastAPI Web Server

Routes:
  GET  /                         → serve the upload UI
  POST /analyze                  → start analysis job, return job_id
  GET  /status/{job_id}          → poll job status + progress
  GET  /download/{job_id}/excel  → download Excel workbook
  GET  /download/{job_id}/report → download Word report
  GET  /health                   → health check
"""
import asyncio
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Make sure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from web.jobs import Job, create_job, get_job

UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Financial Analysis AI", version="1.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ── Serve UI ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())


# ── Start Analysis Job ────────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    company: str = Form(""),
    years: str = Form(""),
    currency: str = Form("INR"),
    unit: str = Form("Crores"),
):
    # Validate file type
    filename = file.filename or ""
    is_json = filename.endswith(".json")
    is_pdf  = filename.endswith(".pdf")
    if not (is_json or is_pdf):
        raise HTTPException(400, "Only .pdf or .json files are supported.")

    if is_pdf and not company.strip():
        raise HTTPException(400, "Company name is required for PDF uploads.")

    # Save uploaded file
    job = create_job()
    suffix = ".json" if is_json else ".pdf"
    saved_path = UPLOADS_DIR / f"{job.id}{suffix}"
    with open(saved_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Parse fiscal years
    fiscal_years = []
    if years.strip():
        try:
            fiscal_years = [int(y.strip()) for y in years.split(",") if y.strip()]
        except ValueError:
            raise HTTPException(400, "Years must be comma-separated integers, e.g. 2022,2023,2024")

    background_tasks.add_task(
        run_analysis,
        job=job,
        file_path=str(saved_path),
        is_json=is_json,
        company=company.strip(),
        fiscal_years=fiscal_years,
        currency=currency,
        unit=unit,
    )

    return JSONResponse({"job_id": job.id})


# ── Background Worker ─────────────────────────────────────────────────────────

async def run_analysis(
    job: Job,
    file_path: str,
    is_json: bool,
    company: str,
    fiscal_years: list,
    currency: str,
    unit: str,
):
    """Run the full pipeline in a background thread."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_sync, job, file_path, is_json,
                               company, fiscal_years, currency, unit)


def _run_sync(job: Job, file_path: str, is_json: bool,
              company: str, fiscal_years: list, currency: str, unit: str):
    """Synchronous pipeline — runs in a thread pool executor."""
    from datetime import datetime

    job.status = "running"

    try:
        # Step 1: Extract
        job.log("extract", "Extracting financial statements...")
        from agents.extractor import extract_from_json, extract_from_pdf

        if is_json:
            financial_data = extract_from_json(file_path)
        else:
            financial_data = extract_from_pdf(
                path=file_path,
                company_name=company,
                fiscal_years=fiscal_years or list(range(2022, 2025)),
                currency=currency,
                unit=unit,
            )
        job.log("extract",
                f"Extracted {len(financial_data.sorted_years())} year(s) for "
                f"{financial_data.company_name} "
                f"(confidence: {financial_data.metadata.overall_confidence:.0%})",
                done=True)

        # Step 2: Excel
        job.log("excel", "Building Excel workbook with live formulas...")
        from agents.excel_builder import build_workbook
        excel_path = build_workbook(financial_data)
        job.log("excel", f"Excel workbook built — {Path(excel_path).name}", done=True)

        # Step 3: Verify
        job.log("verify", "Running verification checks...")
        from agents.verifier import verify_workbook
        report = verify_workbook(excel_path, financial_data)
        if report.passes:
            job.log("verify", "All checks passed ✓", done=True)
        else:
            issues = "; ".join(report.issues[:2])
            job.log("verify", f"Verification issues: {issues}", done=True)

        # Step 4: Commentary + Report
        job.log("report", "Generating AI commentary & Word report...")
        from agents.analyzer import generate_commentary_safe
        from agents.report_generator import generate_report
        commentary = generate_commentary_safe(financial_data)
        report_path = generate_report(financial_data, commentary)
        job.log("report", f"Report generated — {Path(report_path).name}", done=True)

        job.files = {"excel": excel_path, "report": report_path}
        job.status = "done"
        job.finished_at = datetime.now().isoformat()

    except Exception as e:
        # Strip raw HTML from error messages (e.g. 502 gateway responses)
        import re as _re
        raw = str(e)
        clean = _re.sub(r"<[^>]+>", "", raw).strip()          # strip tags
        clean = _re.sub(r"\s+", " ", clean).strip()           # collapse whitespace
        clean = clean[:300] if len(clean) > 300 else clean    # cap length
        if not clean:
            clean = type(e).__name__
        job.log("error", clean)
        job.status = "error"
        job.error = clean
        job.finished_at = datetime.now().isoformat()

    finally:
        # Clean up uploaded file
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass


# ── Poll Status ───────────────────────────────────────────────────────────────

@app.get("/status/{job_id}")
def status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JSONResponse(job.to_dict())


# ── Download Files ────────────────────────────────────────────────────────────

@app.get("/download/{job_id}/excel")
def download_excel(job_id: str):
    job = get_job(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "File not ready")
    path = job.files.get("excel")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Excel file not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=Path(path).name,
    )


@app.get("/download/{job_id}/report")
def download_report(job_id: str):
    job = get_job(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "File not ready")
    path = job.files.get("report")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Report file not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=Path(path).name,
    )
