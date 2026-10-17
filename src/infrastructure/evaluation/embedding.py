"""Stable 128-dimensional lexical embedding used by evidence retrieval."""

from __future__ import annotations

import hashlib
import re


class LocalLexicalEmbeddings:
    """Offline signed token hashing; exact source verification remains authoritative."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            vector = [0.0] * 128
            for token in re.findall(r"\w+", text.casefold()):
                digest = hashlib.sha256(token.encode()).digest()
                vector[digest[0] % 128] += 1 if digest[1] % 2 else -1
            norm = sum(value * value for value in vector) ** 0.5 or 1
            vectors.append([value / norm for value in vector])
        return vectors

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)
