"""PostgreSQL evidence storage and scoped vector retrieval."""

from __future__ import annotations

import hashlib

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from src.domain.analysis.evaluation import (
    Chunk,
    Claim,
    DecisionProposal,
    EvidenceArtifact,
    EvidenceSource,
    RetrievalTrace,
    RuntimeEvaluationContext,
    SourceScope,
)


class EvidenceUnavailableError(RuntimeError):
    """A transient corpus/index/service failure, distinct from a missing fact."""


class SourceIntegrityError(RuntimeError):
    """A returned record violated authorized scope or content integrity."""


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authorized(chunk: Chunk, scope: SourceScope, supplier_ids: list[str]) -> bool:
    return (
        chunk.tenant_id == scope.tenant_id
        and chunk.case_id == scope.case_id
        and scope.document_hashes.get(chunk.document_id) == chunk.document_hash
        and chunk.supplier_id in supplier_ids
        and chunk.source_kind in scope.source_kinds
        and content_hash(chunk.text) == chunk.chunk_hash
    )


def _vector_literal(values: list[float]) -> str:
    if len(values) != 128:
        raise ValueError("Evidence embedding must have 128 dimensions")
    return "[" + ",".join(format(value, ".17g") for value in values) + "]"


class PostgresEvidenceAdapter:
    """Store exact source records and their lexical vectors in the shared database."""

    def __init__(self, database_url: str, embeddings, *, k: int = 8, ready: bool = True) -> None:
        if k < 1:
            raise ValueError("k must be positive")
        self.database_url, self.embeddings, self.k, self.ready = database_url, embeddings, k, ready
        self.ensure_schema()

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    supplier_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    document_hash TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    record JSONB NOT NULL,
                    embedding vector(128) NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS evidence_chunks_scope_idx
                ON evidence_chunks (tenant_id, case_id, supplier_id, source_kind, document_id, document_hash)
                """
            )

    def ingest(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            if content_hash(chunk.text) != chunk.chunk_hash:
                raise SourceIntegrityError("Chunk content hash mismatch")
            if chunk.table_id and not (chunk.row_id and chunk.cell_locator):
                raise SourceIntegrityError("Table row/cell locators are required")
            if any(f.supplier_id != chunk.supplier_id for f in chunk.facts):
                raise SourceIntegrityError("Source fact supplier mismatch")
        if not chunks:
            return

        vectors = self.embeddings([chunk.text for chunk in chunks])
        rows = [
            (
                chunk.chunk_id,
                chunk.tenant_id,
                chunk.case_id,
                chunk.supplier_id,
                chunk.document_id,
                chunk.document_hash,
                chunk.source_kind,
                chunk.chunk_hash,
                chunk.text,
                Jsonb(chunk.model_dump(mode="json", exclude={"text", "chunk_id"})),
                _vector_literal(vector),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO evidence_chunks (
                        chunk_id, tenant_id, case_id, supplier_id, document_id,
                        document_hash, source_kind, chunk_hash, content, record, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        case_id = EXCLUDED.case_id,
                        supplier_id = EXCLUDED.supplier_id,
                        document_id = EXCLUDED.document_id,
                        document_hash = EXCLUDED.document_hash,
                        source_kind = EXCLUDED.source_kind,
                        chunk_hash = EXCLUDED.chunk_hash,
                        content = EXCLUDED.content,
                        record = EXCLUDED.record,
                        embedding = EXCLUDED.embedding
                    """,
                    rows,
                )

    @staticmethod
    def _scope(scope: SourceScope, suppliers: list[str]) -> tuple[str, tuple[object, ...]]:
        if not scope.document_hashes or not suppliers or not scope.source_kinds:
            raise SourceIntegrityError("Empty authorized source scope")
        clause = (
            "tenant_id = %s AND case_id = %s AND supplier_id = ANY(%s) "
            "AND source_kind = ANY(%s) AND (%s::jsonb ->> document_id) = document_hash"
        )
        params = (
            scope.tenant_id,
            scope.case_id,
            suppliers,
            list(scope.source_kinds),
            Jsonb(scope.document_hashes),
        )
        return clause, params

    def _get(self, ids: list[str], scope: SourceScope, suppliers: list[str]) -> list[Chunk]:
        if not ids:
            return []
        clause, params = self._scope(scope, suppliers)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence_chunks WHERE chunk_id = ANY(%s) AND " + clause,
                (list(dict.fromkeys(ids)), *params),
            ).fetchall()
        chunks: list[Chunk] = []
        try:
            for row in rows:
                chunk = Chunk.model_validate({**row["record"], "text": row["content"], "chunk_id": row["chunk_id"]})
                if row["chunk_id"] not in ids or not authorized(chunk, scope, suppliers):
                    raise SourceIntegrityError("Query/Get returned unauthorized or changed source")
                for field in (
                    "tenant_id", "case_id", "supplier_id", "document_id",
                    "document_hash", "source_kind", "chunk_hash",
                ):
                    if row[field] != getattr(chunk, field):
                        raise SourceIntegrityError("Indexed metadata mismatch")
                chunks.append(chunk)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise SourceIntegrityError("Malformed exact source record") from exc
        return chunks

    def retrieve(self, proposal: DecisionProposal, context: RuntimeEvaluationContext) -> list[EvidenceArtifact]:
        if not self.ready:
            raise EvidenceUnavailableError("Source index is not ready")
        try:
            return [self._claim(claim, context) for claim in proposal.claims]
        except (SourceIntegrityError, EvidenceUnavailableError):
            raise
        except (psycopg.Error, TimeoutError, ConnectionError, OSError) as exc:
            raise EvidenceUnavailableError("PostgreSQL evidence index unavailable") from exc
        except Exception as exc:
            raise EvidenceUnavailableError("PostgreSQL evidence query failed") from exc

    def _claim(self, claim: Claim, context: RuntimeEvaluationContext) -> EvidenceArtifact:
        ids: list[str] = []
        distances: list[float] = []
        # Query each supplier separately so one cannot crowd out the alternatives.
        for supplier in claim.supplier_ids:
            query = " ".join(
                [claim.text, claim.predicate.metric, supplier, claim.predicate.model_dump_json(), *claim.source_hints]
            )
            vector = _vector_literal(self.embeddings.embed_query([query])[0])
            clause, params = self._scope(context.source_scope, [supplier])
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT chunk_id, power(embedding <-> %s::vector, 2) AS distance "
                    "FROM evidence_chunks WHERE " + clause + " ORDER BY distance, chunk_id LIMIT %s",
                    (vector, *params, self.k),
                ).fetchall()
            ids.extend(row["chunk_id"] for row in rows)
            distances.extend(float(row["distance"]) for row in rows)

        plans = [
            plan for plan in context.calculations
            if plan.metric == claim.predicate.metric and plan.supplier_id in claim.supplier_ids
        ]
        ids.extend(chunk_id for plan in plans for chunk_id in plan.operand_chunk_ids)
        chunks = self._get(ids, context.source_scope, claim.supplier_ids)
        expansion_ids = [
            chunk_id
            for chunk in chunks
            for chunk_id in ([chunk.parent_chunk_id, chunk.original_chunk_id] + chunk.context_chunk_ids)
            if chunk_id and chunk_id not in {item.chunk_id for item in chunks}
        ]
        expanded = self._get(expansion_ids, context.source_scope, claim.supplier_ids)
        chunks = list({chunk.chunk_id: chunk for chunk in chunks + expanded}.values())
        return EvidenceArtifact(
            evidence_id=f"ev:{context.recommendation_id}:{context.recommendation_version}:{claim.claim_id}",
            recommendation_id=context.recommendation_id,
            recommendation_version=context.recommendation_version,
            claim_id=claim.claim_id,
            evidence_kind="comparative" if claim.category == "comparison" else "derived" if plans else "direct_source",
            sources=[EvidenceSource(chunk=chunk, exact_excerpt=chunk.text, context_excerpt=chunk.text) for chunk in chunks],
            retrieval_trace=RetrievalTrace(
                query_id=f"query:{claim.claim_id}",
                candidate_chunk_ids=list(dict.fromkeys(ids)),
                distances=distances,
                expansion_count=int(bool(expansion_ids)),
            ),
        )
