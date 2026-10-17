#!/usr/bin/env python3
# ruff: noqa: E402
"""Read-only consistency report for procurement workflow projections.

Usage: ``.venv/bin/python3 scripts/check_procurement_consistency.py``
The exit code is non-zero when discrepancies are found, making the command
suitable for a deployment check. It does not replay commands or edit records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

# Support direct execution from a checkout as documented below.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.procurement.workflow import ProcurementWorkflow
from src.core.config import get_settings
from src.infrastructure.evaluation.store import EvaluationStore
from src.infrastructure.repositories.purchase_orders import get_po_repository
from src.infrastructure.repositories.purchase_requests import get_pr_repository


def main() -> int:
    settings = get_settings()
    # ``audit_consistency`` needs only the durable evaluation store. Avoid
    # initializing evidence storage, providers or reconciliation, which would be
    # unrelated to a reporting-only command.
    evaluation = SimpleNamespace(store=EvaluationStore(settings.evaluation_database_path))
    workflow = ProcurementWorkflow(
        settings.procurement_workflow_path,
        evaluation,
        tenant_id=settings.procurement_tenant_id,
        running_timeout_seconds=settings.analysis_running_timeout_seconds,
    )
    findings = workflow.audit_consistency(get_pr_repository(), get_po_repository())
    print(json.dumps({"findings": findings, "count": len(findings)}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
