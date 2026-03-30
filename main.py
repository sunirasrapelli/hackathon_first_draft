#!/usr/bin/env python3
"""
Financial Analysis AI — CLI Orchestrator

Usage:
  # From a PDF annual report
  python main.py --input reports/HDFC_AR_2024.pdf --company "HDFC Bank" --years "2022,2023,2024"

  # From a pre-structured JSON file (no API call needed)
  python main.py --input tests/sample_data/manual_input_example.json --manual
"""
import argparse
import sys
import time
from pathlib import Path

from utils.logger import get_logger

log = get_logger()


def parse_args():
    p = argparse.ArgumentParser(
        description="AI Financial Analysis Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--input", required=True,
                   help="Path to PDF annual report or JSON data file")
    p.add_argument("--company", default="",
                   help="Company name (required for PDF input)")
    p.add_argument("--years", default="",
                   help="Comma-separated fiscal years to extract, e.g. '2022,2023,2024'")
    p.add_argument("--currency", default="INR",
                   help="Currency code (default: INR)")
    p.add_argument("--unit", default="Crores",
                   help="Reporting unit: Crores or Millions (default: Crores)")
    p.add_argument("--manual", action="store_true",
                   help="Treat --input as a JSON file and skip Claude API extraction")
    p.add_argument("--output-dir", default="",
                   help="Override output directory for the Excel file")
    p.add_argument("--no-report", action="store_true",
                   help="Skip Word report generation (Excel only)")
    return p.parse_args()


def main():
    args = parse_args()
    input_path = args.input

    if not Path(input_path).exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    is_manual = args.manual or input_path.endswith(".json")

    if not is_manual and not args.company:
        print("ERROR: --company is required for PDF input", file=sys.stderr)
        sys.exit(1)

    fiscal_years = []
    if args.years:
        try:
            fiscal_years = [int(y.strip()) for y in args.years.split(",")]
        except ValueError:
            print("ERROR: --years must be comma-separated integers, e.g. '2022,2023,2024'",
                  file=sys.stderr)
            sys.exit(1)

    t0 = time.time()
    print("\n" + "=" * 60)
    print("  Financial Analysis AI")
    print("=" * 60)

    steps = "4" if not args.no_report else "3"

    # ── Step 1: Extract Financial Data ───────────────────────────────────────
    print(f"\n[1/{steps}] Extracting financial statements...")
    from agents.extractor import extract_from_json, extract_from_pdf

    if is_manual:
        financial_data = extract_from_json(input_path)
    else:
        financial_data = extract_from_pdf(
            path=input_path,
            company_name=args.company,
            fiscal_years=fiscal_years or list(range(2022, 2025)),
            currency=args.currency,
            unit=args.unit,
        )

    print(f"    Company  : {financial_data.company_name}")
    print(f"    Years    : {', '.join(str(y) for y in financial_data.sorted_years())}")
    print(f"    Currency : {financial_data.currency} ({financial_data.unit})")
    print(f"    Confidence: {financial_data.metadata.overall_confidence:.0%}")
    if financial_data.metadata.warnings:
        print(f"    Warnings : {len(financial_data.metadata.warnings)}")
        for w in financial_data.metadata.warnings[:3]:
            print(f"      ⚠ {w}")

    # ── Step 2: Build Excel Workbook ─────────────────────────────────────────
    print(f"\n[2/{steps}] Building Excel workbook with live formulas...")
    from agents.excel_builder import build_workbook

    output_path = None
    if args.output_dir:
        from pathlib import Path as _P
        from datetime import datetime
        safe = financial_data.company_name.replace(" ", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(_P(args.output_dir) / f"{safe}_{ts}.xlsx")

    excel_path = build_workbook(financial_data, output_path)
    print(f"    Excel    : {excel_path}")

    # ── Step 3: Verify ───────────────────────────────────────────────────────
    print(f"\n[3/{steps}] Running verification checks...")
    from agents.verifier import verify_workbook

    report = verify_workbook(excel_path, financial_data)
    status = "✓ PASS" if report.passes else "✗ FAIL"
    print(f"    Status   : {status}")
    if report.issues:
        for issue in report.issues:
            print(f"      ✗ {issue}")
    if report.warnings:
        for warn in report.warnings:
            print(f"      ⚠ {warn}")

    # ── Step 4: Generate commentary + Word report ─────────────────────────────
    report_path = None
    if not args.no_report:
        print("\n[4/4] Generating financial commentary & Word report...")
        from agents.analyzer import generate_commentary_safe
        from agents.report_generator import generate_report

        commentary = generate_commentary_safe(financial_data)
        report_path = generate_report(financial_data, commentary)
        print(f"    Report   : {report_path}")

    # ── Done ─────────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Excel  → {excel_path}")
    if report_path:
        print(f"  Report → {report_path}")
    print(f"{'=' * 60}\n")

    if not report.passes:
        sys.exit(1)


if __name__ == "__main__":
    main()
