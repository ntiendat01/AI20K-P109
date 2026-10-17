import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes.evaluation import router
from src.application.evaluation.engine import Evaluator
from src.infrastructure.evaluation.store import EvaluationStore
from src.application.evaluation.workflow import EvaluationWorkflow
from tests.fixtures.evaluation_cases import actor, adapter, context, proposal


@pytest.fixture
def review_app(tmp_path):
    app = FastAPI()
    app.include_router(router)
    app.state.evaluation_workflow = EvaluationWorkflow(Evaluator(adapter()), EvaluationStore(tmp_path / "api.sqlite"))
    app.state.evaluation_context_provider = lambda case_id, user: context()
    app.state.test_actor = actor()

    @app.middleware("http")
    async def authenticated_context(request, call_next):
        if app.state.test_actor is not None:
            request.state.actor = app.state.test_actor
        return await call_next(request)

    return app


@pytest.mark.asyncio
async def test_full_review_api_persists_approval_and_rejects_conflicting_click(review_app):
    async with AsyncClient(transport=ASGITransport(app=review_app), base_url="http://test") as client:
        response = await client.post(
            "/evaluations/cases/case-demo", json={"proposal": proposal().model_dump(mode="json")}
        )
        assert response.status_code == 200
        assert response.json()["overall_status"] == "ready_for_review"
        response = await client.get("/evaluations/rec-demo/review")
        assert response.status_code == 200
        assert response.json()["recommendation_version"] == 1
        payload = {
            "feedback_id": "feedback-api",
            "recommendation_id": "rec-demo",
            "recommendation_version": 1,
            "idempotency_key": "click-api",
            "decision": "approve",
        }
        first = await client.post("/evaluations/rec-demo/feedback", json=payload)
        duplicate = await client.post("/evaluations/rec-demo/feedback", json=payload)
        assert first.status_code == duplicate.status_code == 200
        assert first.json() == duplicate.json()
        assert first.json()["workflow_status"] == "approved"
        payload["decision"], payload["note"] = "reject", "Changed mind"
        assert (await client.post("/evaluations/rec-demo/feedback", json=payload)).status_code == 409
        assert (await client.get("/evaluations/rec-demo/review")).status_code == 409


@pytest.mark.asyncio
async def test_client_cannot_supply_policy_or_identity(review_app):
    async with AsyncClient(transport=ASGITransport(app=review_app), base_url="http://test") as client:
        data = {"proposal": proposal().model_dump(mode="json"), "runtime_context": context().model_dump(mode="json")}
        assert (await client.post("/evaluations/cases/case-demo", json=data)).status_code == 422
        review_app.state.test_actor = None
        assert (await client.get("/evaluations/rec-demo/review", headers={"X-Role": "buyer"})).status_code == 401
        review_app.state.test_actor = actor().model_copy(update={"tenant_id": "other-tenant"})
        assert (
            await client.post("/evaluations/cases/case-demo", json={"proposal": proposal().model_dump(mode="json")})
        ).status_code == 403


@pytest.mark.asyncio
async def test_invalid_output_routes_to_repair_and_never_review(review_app):
    async with AsyncClient(transport=ASGITransport(app=review_app), base_url="http://test") as client:
        response = await client.post("/evaluations/cases/case-demo", json={"proposal": {"approval_state": "approved"}})
        assert response.status_code == 200
        assert response.json()["overall_status"] == "repairable"
        assert (await client.get("/evaluations/rec-demo/review")).status_code == 409


@pytest.mark.asyncio
async def test_unconfigured_application_fails_closed(review_app):
    review_app.state.evaluation_workflow = None
    async with AsyncClient(transport=ASGITransport(app=review_app), base_url="http://test") as client:
        response = await client.post(
            "/evaluations/cases/case-demo", json={"proposal": proposal().model_dump(mode="json")}
        )
        assert response.status_code == 503
