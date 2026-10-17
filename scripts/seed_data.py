#!/usr/bin/env python3
# ruff: noqa: E402
"""Seed data script for AI Procurement Agent (Procura).

Scalable, high-performance seeder for datasets of arbitrary size:
- Automatically preserves historical time-series curves (e.g. 6-month growth)
  by dynamically shifting relative to current execution time.
- Atomic replacement in PostgreSQL (application_records) via single transaction.
- Incremental file sync for quotation PDFs into target upload directory.

Usage:
    python scripts/seed_data.py [--clean] [--dry-run] [--source-dir seeds]
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Reconfigure stdout for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.config import get_settings
from src.domain.procurement.contracts import PurchaseOrder
from src.domain.purchase_request import PurchaseRequest
from src.domain.quotation.confirmation import Quotation
from src.infrastructure.persistence.postgres import PostgresRecordStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_data")


def parse_iso(dt_str: str) -> datetime:
    """Parse ISO datetime string and normalize to UTC-aware datetime."""
    clean = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def adjust_dynamic_dates(
    prs: list[dict[str, Any]],
    quotations: list[dict[str, Any]],
    pos: list[dict[str, Any]],
) -> None:
    """Scalable date adjuster: shifts all relative historical dates forward to now.

    Calculates the delta between the latest record and current time, then shifts
    every record by that exact delta. This preserves any historical curve (e.g.,
    month-by-month growth over 6 months) while ensuring the newest data is always
    current.
    """
    if not prs:
        return

    now = datetime.now(UTC)
    latest_dt = max(parse_iso(pr["created_at"]) for pr in prs)
    shift_delta = now - latest_dt

    # Only shift if delta is significant (more than 1 hour)
    if abs(shift_delta.total_seconds()) < 3600:
        return

    logger.info("Shifting dataset timestamps by %s to align with now.", shift_delta)

    for pr in prs:
        created = parse_iso(pr["created_at"]) + shift_delta
        updated = parse_iso(pr["updated_at"]) + shift_delta
        pr["created_at"] = created.isoformat()
        pr["updated_at"] = updated.isoformat()

        if pr.get("delivery_due_date"):
            try:
                due_dt = datetime.fromisoformat(pr["delivery_due_date"])
                pr["delivery_due_date"] = str((due_dt + shift_delta).date())
            except ValueError:
                pass

    for q in quotations:
        created = parse_iso(q["created_at"]) + shift_delta
        q["created_at"] = created.isoformat()
        if q.get("confirmed_at"):
            confirmed = parse_iso(q["confirmed_at"]) + shift_delta
            q["confirmed_at"] = confirmed.isoformat()

    for po in pos:
        created = parse_iso(po["created_at"]) + shift_delta
        po["created_at"] = created.isoformat()
        if po.get("approved_at"):
            approved = parse_iso(po["approved_at"]) + shift_delta
            po["approved_at"] = approved.isoformat()


def sync_pdf_files(
    quotations: list[dict[str, Any]],
    source_documents_dir: Path,
    upload_root: Path,
    dry_run: bool,
) -> int:
    """Incremental copy of referenced PDF files into upload directory."""
    copied = 0
    available_pdfs = list(source_documents_dir.glob("*.pdf"))

    for q in quotations:
        pr_id = q["pr_id"]
        source_hash = q["source_hash"]
        source_filename = q.get("source_filename", "")

        src_pdf = source_documents_dir / f"{source_hash}.pdf"
        if not src_pdf.exists():
            matching = [c for c in available_pdfs if c.name == source_filename or c.name.startswith(source_hash)]
            if matching:
                src_pdf = matching[0]

        if not src_pdf.exists():
            logger.warning(
                "Source PDF not found for quote %s (%s): %s",
                q["id"],
                q["supplier_name"],
                src_pdf,
            )
            continue

        target_dir = upload_root / pr_id
        target_pdf = target_dir / f"{source_hash}.pdf"

        # Update source_path to match actual target location
        q["source_path"] = str(target_pdf).replace("\\", "/")

        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if not target_pdf.exists() or target_pdf.stat().st_size != src_pdf.stat().st_size:
                shutil.copy2(src_pdf, target_pdf)
                copied += 1
        else:
            copied += 1

    return copied


def seed_postgres(
    database_url: str,
    prs: list[dict[str, Any]],
    quotations: list[dict[str, Any]],
    pos: list[dict[str, Any]],
    clean: bool,
    dry_run: bool,
) -> None:
    """Insert or replace records in PostgreSQL application_records."""
    store = PostgresRecordStore(database_url)

    if dry_run:
        logger.info("[DRY RUN] Would write to PostgreSQL application_records:")
        logger.info("  - %d purchase requests", len(prs))
        logger.info("  - %d quotations", len(quotations))
        logger.info("  - %d purchase orders", len(pos))
        return

    logger.info("Writing records to PostgreSQL (%s)...", database_url.split("@")[-1])
    store.ensure_schema()

    if clean:
        logger.info("Replacing existing records in namespaces...")

    store.replace("purchase_requests", prs, created_key="created_at")
    store.replace("quotations", quotations, parent_key="pr_id", created_key="created_at")
    store.replace("purchase_orders", pos, parent_key="pr_id", created_key="created_at")


def seed_legacy_files(
    data_dir: Path,
    prs: list[dict[str, Any]],
    quotations: list[dict[str, Any]],
    pos: list[dict[str, Any]],
    clean: bool,
    dry_run: bool,
) -> None:
    """Write records to data/*.json legacy files."""
    if dry_run:
        logger.info("[DRY RUN] Would write to %s/*.json", data_dir)
        return

    data_dir.mkdir(parents=True, exist_ok=True)

    def write_json(path: Path, data: list[dict[str, Any]]) -> None:
        if not clean and path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
                merged = [item for item in existing if item["id"] not in {d["id"] for d in data}]
                merged.extend(data)
                data = merged
            except Exception:
                pass

        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    write_json(data_dir / "purchase_requests.json", prs)
    write_json(data_dir / "quotations.json", quotations)
    write_json(data_dir / "purchase_orders.json", pos)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed initial dataset for AI Procurement Agent (arbitrary size)."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=ROOT_DIR / "seeds",
        help="Path to seeds directory (default: ./seeds)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean/replace existing records in target database/files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying files or database",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "postgresql", "legacy", "both"],
        default="auto",
        help="Persistence target: 'auto' (follow .env), 'postgresql', 'legacy', or 'both'",
    )
    parser.add_argument(
        "--keep-static-dates",
        action="store_true",
        help="Keep exact timestamps without shifting relative to now",
    )

    args = parser.parse_args()
    settings = get_settings()

    source_data_dir = args.source_dir / "data"
    source_docs_dir = args.source_dir / "documents"

    if not source_data_dir.exists():
        logger.error("Seeds data directory not found at: %s", source_data_dir)
        return 1

    # 1. Load source JSON files
    pr_file = source_data_dir / "purchase_requests.json"
    quote_file = source_data_dir / "quotations.json"
    po_file = source_data_dir / "purchase_orders.json"

    for file_path in (pr_file, quote_file, po_file):
        if not file_path.exists():
            logger.error("Missing seed data file: %s", file_path)
            return 1

    with pr_file.open(encoding="utf-8") as f:
        prs = json.load(f)
    with quote_file.open(encoding="utf-8") as f:
        quotations = json.load(f)
    with po_file.open(encoding="utf-8") as f:
        pos = json.load(f)

    # 2. Adjust dynamic dates unless disabled
    if not args.keep_static_dates:
        adjust_dynamic_dates(prs, quotations, pos)

    # 3. Validate models
    try:
        for pr in prs:
            PurchaseRequest.model_validate(pr)
        for q in quotations:
            Quotation.model_validate(q)
        for po in pos:
            PurchaseOrder.model_validate(po)
        logger.info("All %d seed records passed Pydantic domain validation.", len(prs) + len(quotations) + len(pos))
    except Exception as exc:
        logger.error("Validation failed for seed data: %s", exc)
        return 1

    # 4. Sync PDF documents into upload directory
    upload_root = ROOT_DIR / settings.upload_dir
    files_synced = sync_pdf_files(quotations, source_docs_dir, upload_root, args.dry_run)
    logger.info("PDF synchronization: %d quotation files processed to %s", files_synced, upload_root)

    # 5. Persist records
    target_backend = args.backend
    if target_backend == "auto":
        target_backend = settings.persistence_backend

    if target_backend in ("postgresql", "both"):
        seed_postgres(
            settings.database_url,
            prs,
            quotations,
            pos,
            clean=args.clean,
            dry_run=args.dry_run,
        )

    if target_backend in ("legacy", "both"):
        data_dir = ROOT_DIR / "data"
        seed_legacy_files(
            data_dir,
            prs,
            quotations,
            pos,
            clean=args.clean,
            dry_run=args.dry_run,
        )

    # Breakdown by status and by month
    status_counts = Counter(pr["status"] for pr in prs)
    monthly_counts = Counter(pr["created_at"][:7] for pr in prs)

    # Print friendly report
    print("\n" + "=" * 65)
    print("  AI PROCUREMENT AGENT - 6-MONTH GROWTH SEED REPORT")
    print("=" * 65)
    print(f"Target Backend     : {target_backend.upper()}")
    print(f"Total PRs          : {len(prs)}")
    print(f"Total Quotations   : {len(quotations)}")
    print(f"Total POs          : {len(pos)}")
    print("-" * 65)
    print("Monthly Growth Breakdown:")
    for month in sorted(monthly_counts.keys()):
        print(f"  * Month {month} : {monthly_counts[month]:2d} PRs")
    print("-" * 65)
    print("Status Breakdown:")
    for status_name, count in sorted(status_counts.items()):
        print(f"  * {status_name:<20}: {count:2d} PRs")
    print("=" * 65)
    print("Status: SUCCESS! Dữ liệu tăng trưởng 6 tháng đã sẵn sàng.")
    print("=" * 65 + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
