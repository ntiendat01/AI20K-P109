"""Durable recommendation versions, compare-and-set review, and atomic audit."""
# allow: SIZE_OK -- lifecycle transitions and their transaction-scoped audit must remain atomic.

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from src.models.evaluation import Actor, EvaluationResult, Feedback, FeedbackReceipt, RuntimeEvaluationContext

logger = logging.getLogger(__name__)


class ReviewConflictError(ValueError):
    """Stale version, conflicting idempotency key, or invalid lifecycle transition."""


class ReviewForbiddenError(PermissionError):
    """Authenticated actor is not authorized for the requested operation."""


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class EvaluationStore:
    """Use a file path; independent connections make process/thread races transactional."""

    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            raise ValueError("Review storage must survive restart")
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS recommendations (
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL, status TEXT NOT NULL,
                    context TEXT NOT NULL, auto_repairs INTEGER NOT NULL DEFAULT 0,
                    buyer_revisions INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS evaluation_versions (
                    id TEXT NOT NULL, version INTEGER NOT NULL, proposal TEXT NOT NULL,
                    context TEXT NOT NULL, result TEXT, input_hash TEXT NOT NULL,
                    PRIMARY KEY (id, version)
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    recommendation_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    feedback_id TEXT NOT NULL UNIQUE, actor_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
                    receipt TEXT NOT NULL, state TEXT NOT NULL, applied_version INTEGER,
                    PRIMARY KEY (recommendation_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS evaluation_audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recommendation_id TEXT NOT NULL, version INTEGER NOT NULL,
                    actor_id TEXT NOT NULL, event TEXT NOT NULL, timestamp TEXT NOT NULL
                );
            """)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        except sqlite3.Error:
            logger.exception(
                "Database connection failed",
                extra={"event": "database_connection_failed", "storage_backend": "sqlite"},
            )
            raise
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException as error:
            db.rollback()
            logger.warning(
                "Database transaction rolled back",
                extra={
                    "event": "database_transaction_rolled_back",
                    "storage_backend": "sqlite",
                    "error_type": type(error).__name__,
                },
            )
            raise
        finally:
            db.close()

    @staticmethod
    def _audit(db: sqlite3.Connection, context: RuntimeEvaluationContext, actor: str, event: str) -> None:
        db.execute(
            "INSERT INTO evaluation_audit(recommendation_id, version, actor_id, event, timestamp) VALUES (?, ?, ?, ?, ?)",
            (context.recommendation_id, context.recommendation_version, actor, event, datetime.now(UTC).isoformat()),
        )

    def reserve(
        self, proposal: object, context: RuntimeEvaluationContext, *, automatic_repair: bool = False
    ) -> EvaluationResult | None:
        """Reserve a version before evaluating; identical retries can resume a crashed run."""
        payload = canonical(proposal)
        digest = fingerprint({"proposal": proposal, "context": context.model_dump(mode="json")})
        with self.transaction() as db:
            current = db.execute("SELECT * FROM recommendations WHERE id=?", (context.recommendation_id,)).fetchone()
            existing = db.execute(
                "SELECT * FROM evaluation_versions WHERE id=? AND version=?",
                (context.recommendation_id, context.recommendation_version),
            ).fetchone()
            if current:
                previous = RuntimeEvaluationContext.model_validate_json(current["context"])
                if (
                    previous.case_id != context.case_id
                    or previous.source_scope.tenant_id != context.source_scope.tenant_id
                ):
                    raise ReviewConflictError("Recommendation identity belongs to another case/tenant")
                if (
                    existing
                    and current["version"] == context.recommendation_version
                    and existing["input_hash"] == digest
                ):
                    return EvaluationResult.model_validate_json(existing["result"]) if existing["result"] else None
                if current["status"] in {"approved", "rejected", "closed"}:
                    raise ReviewConflictError("Terminal recommendation cannot be reopened")
                if context.recommendation_version != current["version"] + 1:
                    raise ReviewConflictError("Expected the next application-owned version")
                if automatic_repair and current["auto_repairs"] >= 2:
                    raise ReviewConflictError("Automatic repair limit reached")
                db.execute(
                    "UPDATE recommendations SET version=?, status='evaluating', context=?, auto_repairs=auto_repairs+? WHERE id=?",
                    (
                        context.recommendation_version,
                        context.model_dump_json(),
                        int(automatic_repair),
                        context.recommendation_id,
                    ),
                )
            else:
                if context.recommendation_version != 1 or automatic_repair:
                    raise ReviewConflictError("A recommendation starts at version 1")
                db.execute(
                    "INSERT INTO recommendations(id, version, status, context) VALUES (?, ?, 'evaluating', ?)",
                    (context.recommendation_id, context.recommendation_version, context.model_dump_json()),
                )
            db.execute(
                "INSERT INTO evaluation_versions(id, version, proposal, context, input_hash) VALUES (?, ?, ?, ?, ?)",
                (context.recommendation_id, context.recommendation_version, payload, context.model_dump_json(), digest),
            )
            self._audit(db, context, "application", "evaluation_started")
        return None

    def finish(self, context: RuntimeEvaluationContext, result: EvaluationResult) -> EvaluationResult:
        status = "awaiting_review" if result.overall_status == "ready_for_review" else result.overall_status
        with self.transaction() as db:
            version = db.execute(
                "SELECT result FROM evaluation_versions WHERE id=? AND version=?",
                (context.recommendation_id, context.recommendation_version),
            ).fetchone()
            if version and version["result"]:
                # A concurrent resume already committed this evaluation.
                return EvaluationResult.model_validate_json(version["result"])
            changed = db.execute(
                "UPDATE recommendations SET status=? WHERE id=? AND version=? AND status='evaluating'",
                (status, context.recommendation_id, context.recommendation_version),
            ).rowcount
            if changed != 1:
                raise ReviewConflictError("Evaluation was superseded")
            db.execute(
                "UPDATE evaluation_versions SET result=? WHERE id=? AND version=?",
                (result.model_dump_json(), context.recommendation_id, context.recommendation_version),
            )
            self._audit(db, context, "application", f"evaluation:{result.overall_status}")
        return result

    def current(self, recommendation_id: str) -> dict[str, object]:
        with self.transaction() as db:
            row = db.execute(
                "SELECT r.*, v.proposal, v.result FROM recommendations r JOIN evaluation_versions v ON r.id=v.id AND r.version=v.version WHERE r.id=?",
                (recommendation_id,),
            ).fetchone()
            if row is None:
                raise ReviewConflictError("Unknown recommendation")
            return dict(row)

    def review(self, feedback: Feedback, actor: Actor) -> FeedbackReceipt:
        """Authority, idempotency, lifecycle CAS, receipt and audit share one transaction."""
        with self.transaction() as db:
            current = db.execute("SELECT * FROM recommendations WHERE id=?", (feedback.recommendation_id,)).fetchone()
            if current is None:
                raise ReviewConflictError("Unknown recommendation")
            context = RuntimeEvaluationContext.model_validate_json(current["context"])
            if (
                actor.tenant_id != context.source_scope.tenant_id
                or context.case_id not in actor.case_ids
                or context.approval_role not in actor.roles
            ):
                raise ReviewForbiddenError("Actor cannot review this recommendation")
            digest = fingerprint(feedback.model_dump(mode="json"))
            existing = db.execute(
                "SELECT * FROM feedback WHERE recommendation_id=? AND idempotency_key=?",
                (feedback.recommendation_id, feedback.idempotency_key),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != digest or existing["actor_id"] != actor.actor_id:
                    raise ReviewConflictError("Idempotency key conflicts with an earlier action")
                return FeedbackReceipt.model_validate_json(existing["receipt"])
            if current["version"] != feedback.recommendation_version:
                raise ReviewConflictError("Stale recommendation version")
            changes = feedback.requested_changes
            if changes.rule_change and context.rule_change_role not in actor.roles:
                raise ReviewForbiddenError("Rule changes require policy authority")
            if feedback.decision == "close":
                allowed = current["status"] not in {"approved", "rejected", "closed", "evaluating"}
            else:
                allowed = current["status"] == "awaiting_review"
            if not allowed:
                raise ReviewConflictError("Recommendation is not awaiting this review action")
            if feedback.decision == "approve" and not set(context.critical_uncertainty_ids) <= set(
                feedback.acknowledged_uncertainty_ids
            ):
                raise ReviewConflictError("Required critical uncertainty acknowledgement is missing")
            if feedback.decision == "revise":
                external = bool(changes.preference_change or changes.data_corrections or changes.rule_change)
                status = "awaiting_input" if external else "awaiting_repair"
                route = (
                    "awaiting_rule_owner"
                    if changes.rule_change
                    else "awaiting_data_owner"
                    if changes.data_corrections
                    else "awaiting_preference_owner"
                    if changes.preference_change
                    else "repair_decision_llm"
                )
                state = "received"
            else:
                status = {"approve": "approved", "reject": "rejected", "close": "closed"}[feedback.decision]
                route = {"approve": "FINALIZE_APPROVAL", "reject": "FINALIZE_REJECTION", "close": "CLOSE_CASE"}[
                    feedback.decision
                ]
                state = "applied"
            receipt = FeedbackReceipt(
                feedback_id=feedback.feedback_id,
                recommendation_id=feedback.recommendation_id,
                recommendation_version=feedback.recommendation_version,
                state=state,
                workflow_status=status,
                route=route,
            )
            changed = db.execute(
                "UPDATE recommendations SET status=?, buyer_revisions=buyer_revisions+? WHERE id=? AND version=? AND status=?",
                (
                    status,
                    int(feedback.decision == "revise"),
                    feedback.recommendation_id,
                    feedback.recommendation_version,
                    current["status"],
                ),
            ).rowcount
            if changed != 1:
                raise ReviewConflictError("Concurrent review changed the recommendation")
            try:
                db.execute(
                    "INSERT INTO feedback(recommendation_id, idempotency_key, feedback_id, actor_id, payload_hash, payload, receipt, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        feedback.recommendation_id,
                        feedback.idempotency_key,
                        feedback.feedback_id,
                        actor.actor_id,
                        digest,
                        feedback.model_dump_json(),
                        receipt.model_dump_json(),
                        state,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ReviewConflictError("Feedback identity is already in use") from exc
            self._audit(db, context, actor.actor_id, f"feedback:{feedback.decision}:{route}")
            return receipt

    def mark_feedback_applied(self, feedback_id: str, context: RuntimeEvaluationContext) -> None:
        """Called by the change owner after applying changes and reevaluating a new version."""
        with self.transaction() as db:
            row = db.execute("SELECT * FROM feedback WHERE feedback_id=?", (feedback_id,)).fetchone()
            current = db.execute("SELECT * FROM recommendations WHERE id=?", (context.recommendation_id,)).fetchone()
            if not row or not current:
                raise ReviewConflictError("Unknown feedback or recommendation")
            feedback = Feedback.model_validate_json(row["payload"])
            if (
                feedback.recommendation_id != context.recommendation_id
                or feedback.recommendation_version >= context.recommendation_version
                or current["version"] != context.recommendation_version
                or current["status"] != "awaiting_review"
            ):
                raise ReviewConflictError("Feedback needs a new fully evaluated output")
            if row["state"] == "applied":
                return
            db.execute(
                "UPDATE feedback SET state='applied', applied_version=? WHERE feedback_id=?",
                (context.recommendation_version, feedback_id),
            )
            self._audit(db, context, "application", f"feedback_applied:{feedback_id}")
