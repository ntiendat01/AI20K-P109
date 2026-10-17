"""One-time migration of the existing Chroma evidence index into PostgreSQL.

Run in a temporary Python environment with chromadb, psycopg and the backend
runtime dependencies installed. The production backend does not install Chroma.
Stop writes to the old index before invoking this script.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.domain.analysis.evaluation import Chunk
from src.infrastructure.evaluation.embedding import LocalLexicalEmbeddings
from src.infrastructure.evaluation.evidence import PostgresEvidenceAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chroma-dir", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("Set DATABASE_URL or pass --database-url")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if not args.chroma_dir.is_dir():
        parser.error("Chroma directory does not exist")

    # This optional import is intentionally isolated from the backend runtime.
    import chromadb

    source = chromadb.PersistentClient(path=str(args.chroma_dir))
    collection = source.get_collection("procurement-evidence-v1", embedding_function=None)
    target = PostgresEvidenceAdapter(args.database_url, LocalLexicalEmbeddings())
    total = collection.count()
    migrated = 0
    for offset in range(0, total, args.batch_size):
        records = collection.get(
            limit=args.batch_size,
            offset=offset,
            include=["documents", "metadatas"],
        )
        ids = records["ids"]
        documents = records["documents"]
        metadatas = records["metadatas"]
        if documents is None or metadatas is None:
            raise ValueError("Chroma returned no documents or metadatas")
        chunks = []
        for chunk_id, text, metadata in zip(ids, documents, metadatas, strict=True):
            if not isinstance(text, str) or not isinstance(metadata, dict):
                raise ValueError(f"Invalid Chroma row: {chunk_id}")
            record = json.loads(metadata["record_json"])
            chunk = Chunk.model_validate({**record, "chunk_id": chunk_id, "text": text})
            for field in (
                "tenant_id", "case_id", "supplier_id", "document_id",
                "document_hash", "source_kind", "chunk_hash",
            ):
                if metadata.get(field) != getattr(chunk, field):
                    raise ValueError(f"Chroma metadata mismatch for {chunk_id}: {field}")
            chunks.append(chunk)
        target.ingest(chunks)
        migrated += len(chunks)
        print(f"Migrated {migrated}/{total} evidence chunks")
    if migrated != total:
        raise RuntimeError(f"Incomplete migration: {migrated}/{total}")


if __name__ == "__main__":
    main()
