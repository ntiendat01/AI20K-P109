"""Durable post-decision orchestration; application-owned input and identity boundary."""

from __future__ import annotations

import json
from typing import Protocol

from src.models.evaluation import (
    Action,
    Actor,
    DecisionProposal,
    EvaluationResult,
    Feedback,
    FeedbackReceipt,
    RuntimeEvaluationContext,
)
from src.services.evaluation.engine import Evaluator, render_review
from src.services.evaluation.store import EvaluationStore, ReviewConflictError, fingerprint
from src.services.evaluation.validation import issue


class RepairModel(Protocol):
    def repair(self, proposal: object, evaluation: EvaluationResult) -> object:
        """Return a new untrusted output, with no ability to change the runtime context."""


class EvaluationWorkflow:
    def __init__(self, evaluator: Evaluator, store: EvaluationStore, repair_model: RepairModel | None = None) -> None:
        self.evaluator, self.store, self.repair_model = evaluator, store, repair_model

    def submit(self, output: object, context: RuntimeEvaluationContext) -> EvaluationResult:
        """Evaluate from gate one, persist every attempt, and allow at most two repairs."""
        if isinstance(output, DecisionProposal):
            output = output.model_dump(mode="json")
        automatic = False
        seen_outputs: set[str] = set()
        seen_issues: set[tuple[str, ...]] = set()
        while True:
            existing = self.store.reserve(output, context, automatic_repair=automatic)
            if existing is not None:
                return existing
            result = self.evaluator.evaluate(output, context)
            current = self.store.current(context.recommendation_id)
            digest = fingerprint(output)
            signature = tuple(sorted(i.code for i in result.issues))
            if result.overall_status == "repairable":
                if current["auto_repairs"] >= 2 or digest in seen_outputs or signature in seen_issues:
                    result.overall_status = "needs_input"
                    result.issues.append(issue("decision", "REPAIR_LIMIT_OR_NO_PROGRESS", "ESCALATE_REPAIR_LIMIT"))
                    result.required_actions = [
                        Action(
                            action_id="repair-limit",
                            type="ESCALATE_REPAIR_LIMIT",
                            route="manual_resolution",
                            issue_ids=[i.issue_id for i in result.issues],
                        )
                    ]
            result = self.store.finish(context, result)
            if result.overall_status != "repairable" or self.repair_model is None:
                return result
            seen_outputs.add(digest)
            seen_issues.add(signature)
            repair_with_context = getattr(self.repair_model, "repair_with_context", None)
            output = (
                repair_with_context(output, result, context)
                if callable(repair_with_context)
                else self.repair_model.repair(output, result)
            )
            if isinstance(output, DecisionProposal):
                output = output.model_dump(mode="json")
            context = context.model_copy(update={"recommendation_version": context.recommendation_version + 1})
            automatic = True

    def review_payload(self, recommendation_id: str, actor: Actor) -> dict[str, object]:
        """Resume after process restart without replaying any model or retrieval calls."""
        current = self.store.current(recommendation_id)
        context = RuntimeEvaluationContext.model_validate_json(current["context"])
        self._authorize(actor, context)
        if current["status"] != "awaiting_review":
            raise ReviewConflictError("Recommendation is not awaiting review")
        return render_review(
            DecisionProposal.model_validate(json.loads(current["proposal"])),
            EvaluationResult.model_validate_json(current["result"]),
            context,
        )

    @staticmethod
    def _authorize(actor: Actor, context: RuntimeEvaluationContext) -> None:
        from src.services.evaluation.store import ReviewForbiddenError

        if (
            actor.tenant_id != context.source_scope.tenant_id
            or context.case_id not in actor.case_ids
            or context.approval_role not in actor.roles
        ):
            raise ReviewForbiddenError("Actor cannot access this case")

    def feedback(self, feedback: Feedback, actor: Actor) -> FeedbackReceipt:
        return self.store.review(feedback, actor)
