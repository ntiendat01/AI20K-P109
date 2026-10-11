"""ProductMatchingService — Heuristic + Trigram fuzzy matching (Phương án 3).

Pipeline per item:
  1. Normalize item name (lowercase, strip diacritics, remove stop-words,
     apply synonym dictionary).
  2. For each PR candidate, compute composite score:
       score = 0.60 * name_score + 0.20 * uom_score + 0.20 * attr_score
       (or normalize the available weights when attributes are absent).
     where name_score uses Jaro-Winkler similarity on trigram-enriched tokens.
  3. Apply threshold decision:
       score >= 0.90  → AUTO_MATCHED
       0.70 <= score < 0.90 → SUGGESTED
       score < 0.70   → UNMATCHED
  4. Check SynonymDictionary first: if exact canonical match found → score = 1.0
     AUTO_MATCHED directly.

No external API calls, no LLM — purely deterministic and fast.
"""

from __future__ import annotations

import re
import unicodedata

from src.models.fuzzy_match import (
    BatchMatchResult,
    MatchCandidate,
    MatchResult,
    MatchStatus,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTO_MATCH_THRESHOLD = 0.90
SUGGEST_THRESHOLD = 0.70

# Score weights (must sum to 1.0)
WEIGHT_NAME = 0.60
WEIGHT_UOM = 0.20
WEIGHT_ATTR = 0.20

# Do not offer a manual-map candidate when its product name is too dissimilar.
# This protects the review UI from a same-unit but unrelated product.
MIN_NAME_SCORE_FOR_CANDIDATE = 0.55

# Stop-words to remove before comparison
STOP_WORDS: frozenset[str] = frozenset(
    [
        "cai",
        "chiec",
        "loai",
        "hang",
        "san",
        "pham",
        "vat",
        "lieu",
        "chat",
        "bo",
    ]
)

# Synonym/alias mapping: canonical form → list of variants (all lowercased, diacritics removed)
SYNONYM_MAP: dict[str, str] = {
    "inox": "thep khong gi",
    "thep khong gỉ": "thep khong gi",
    "thep khong gi": "thep khong gi",
    "ss": "thep khong gi",
    "stainless": "thep khong gi",
    "stainless steel": "thep khong gi",
    # Common product-name aliases
    "may tinh xach tay": "laptop",
    "notebook": "laptop",
    # UoM synonyms embedded in name
    "m3": "khoi",
    "khoi": "khoi",
    "cubic": "khoi",
    "m2": "met vuong",
    "sq m": "met vuong",
    # Material common shorthands
    "galv": "ma kem",
    "galvanized": "ma kem",
    "ms": "thep carbon",
    "mild steel": "thep carbon",
}

# UoM canonical groups for compatibility scoring
_UOM_GROUPS: list[frozenset[str]] = [
    frozenset(["cai", "chiec", "ea", "pcs", "hop", "thung", "ta"]),
    frozenset(["kg", "g", "gram", "tan", "tn", "mt", "metric ton", "metric tonne"]),
    frozenset(["m", "met", "cm", "mm"]),
    frozenset(["lit", "ml"]),
    frozenset(["cuon", "cay", "bao", "thanh", "bo"]),
]

# Spellings that denote the exact same unit, not merely units that can be
# converted to one another. They must therefore receive a score of 1.0.
_UOM_ALIASES: dict[str, str] = {
    "cai": "cai",
    "chiec": "cai",
    "ea": "cai",
    "pcs": "cai",
    "tan": "tan",
    "tn": "tan",
    "mt": "tan",
    "metric ton": "tan",
    "metric tonne": "tan",
    "ream": "ream",
    "ram": "ream",
    "rim": "ream",
}

_REBAR_DIAMETER_RE = re.compile(r"\bd\s*(\d+(?:[.,]\d+)?)\b")
_REBAR_GRADE_RE = re.compile(r"\bcb\s*(\d+)(?:\s*[- ]?([a-z]))?\b")


# ---------------------------------------------------------------------------
# Text normalization helpers
# ---------------------------------------------------------------------------


def _strip_diacritics(text: str) -> str:
    """Remove Vietnamese/Unicode diacritics, return ASCII-friendly string."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalize_name(name: str) -> str:
    """Return fully normalized item name for comparison.

    Steps:
    1. Lowercase.
    2. Strip diacritics.
    3. Remove punctuation (comma, dash, slash, dot, parens).
    4. Collapse whitespace.
    5. Remove stop-words.
    6. Apply synonym dictionary.
    """
    text = name.lower().strip()
    text = _strip_diacritics(text)
    # Remove common punctuation tokens
    text = re.sub(r"[,;:\-/\\.()[\]{}]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Apply synonyms first (multi-word first, then single-word)
    for variant, canonical in sorted(SYNONYM_MAP.items(), key=lambda x: -len(x[0])):
        normalized_variant = _strip_diacritics(variant.lower())
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(normalized_variant)}(?![a-z0-9])")
        text = pattern.sub(canonical, text)

    # Remove stop-words
    tokens = [t for t in text.split() if t not in STOP_WORDS]
    return " ".join(tokens)


def normalize_uom(uom: str | None) -> str:
    """Return lowercase, diacritic-free UoM key."""
    if not uom:
        return ""
    normalized = _strip_diacritics(uom.lower().strip())
    return _UOM_ALIASES.get(normalized, normalized)


# ---------------------------------------------------------------------------
# Similarity algorithms
# ---------------------------------------------------------------------------


def _trigrams(text: str) -> set[str]:
    """Generate character trigrams from text (padding with spaces)."""
    padded = f"  {text}  "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def _jaro(s1: str, s2: str) -> float:
    """Compute Jaro similarity between two strings."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    match_distance = max(len(s1), len(s2)) // 2 - 1
    match_distance = max(match_distance, 0)

    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)

    matches = 0
    transpositions = 0

    for i, c1 in enumerate(s1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len(s2))
        for j in range(start, end):
            if s2_matches[j] or c1 != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i, matched in enumerate(s1_matches):
        if not matched:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (matches / len(s1) + matches / len(s2) + (matches - transpositions / 2) / matches) / 3
    return jaro


def _jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    """Compute Jaro-Winkler similarity (prefix boost, p=0.1 by convention)."""
    jaro = _jaro(s1, s2)
    prefix = 0
    for c1, c2 in zip(s1, s2):
        if c1 == c2:
            prefix += 1
        else:
            break
        if prefix == 4:
            break
    return jaro + prefix * p * (1 - jaro)


def _trigram_similarity(text1: str, text2: str) -> float:
    """Compute trigram-based Dice coefficient similarity."""
    if text1 == text2:
        return 1.0
    tg1 = _trigrams(text1)
    tg2 = _trigrams(text2)
    if not tg1 and not tg2:
        return 1.0
    intersection = len(tg1 & tg2)
    return 2 * intersection / (len(tg1) + len(tg2))


def _rebar_specification_key(normalized_name: str) -> str:
    """Return a stable key for a rebar diameter and CB grade, when present.

    ``D16`` together with ``CB400-V`` identifies a rebar item even when a
    supplier adds a brand, TCVN standard, or different product wording.
    """
    diameter = _REBAR_DIAMETER_RE.search(normalized_name)
    grade = _REBAR_GRADE_RE.search(normalized_name)
    if not diameter or not grade:
        return ""
    grade_suffix = grade.group(2) or ""
    return f"d{diameter.group(1)} cb{grade.group(1)}{grade_suffix}"


def _numeric_tokens(name: str) -> set[str]:
    """Extract numeric specifications without discarding decimal separators."""
    normalized = _strip_diacritics(name.lower())
    return set(re.findall(r"\d+(?:[.,]\d+)?", normalized))


def _has_conflicting_numeric_specs(name1: str, name2: str) -> bool:
    """Return whether both product names carry incompatible numeric specs.

    Extra details are accepted when one side's set is a subset of the other
    (for example, a base laptop model versus the same model with an i5 CPU).
    Conflicting sets can still be proposed to a Buyer, but are never auto-map
    candidates.
    """
    nums1 = _numeric_tokens(name1)
    nums2 = _numeric_tokens(name2)
    return bool(nums1 and nums2 and not (nums1 <= nums2 or nums2 <= nums1))


def name_similarity(name1: str, name2: str) -> float:
    """Compute combined name similarity: average of Jaro-Winkler and trigram."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2:
        return 0.0
    rebar_key_1 = _rebar_specification_key(n1)
    rebar_key_2 = _rebar_specification_key(n2)
    if rebar_key_1 and rebar_key_1 == rebar_key_2:
        # Keep the public name-score contract: Jaro-Winkler and trigram are
        # both evaluated against the matching technical specification key.
        n1 = rebar_key_1
        n2 = rebar_key_2
    if n1 == n2:
        return 1.0
    jw = _jaro_winkler(n1, n2)
    tg = _trigram_similarity(n1, n2)
    # Weighted blend: trigram catches substring differences better
    return 0.4 * jw + 0.6 * tg


def uom_similarity(uom1: str | None, uom2: str | None) -> float:
    """Score UoM compatibility.

    - Same UoM (after normalization): 1.0.
    - Same UoM group (convertible): 0.8.
    - Different group: 0.0.
    - One or both missing: 0.5 (neutral — no penalty).
    """
    k1 = normalize_uom(uom1)
    k2 = normalize_uom(uom2)
    if not k1 or not k2:
        return 0.5
    if k1 == k2:
        return 1.0
    for group in _UOM_GROUPS:
        if k1 in group and k2 in group:
            return 0.8
    return 0.0


def attr_similarity(attr1: str | None, attr2: str | None) -> float:
    """Score additional attribute/description similarity (part numbers, dimensions)."""
    if not attr1 or not attr2:
        return 0.5  # neutral when either is missing
    # Extract numbers from both strings — differences in numeric tokens penalise heavily
    nums1 = set(re.findall(r"\d+(?:[.,]\d+)?", attr1))
    nums2 = set(re.findall(r"\d+(?:[.,]\d+)?", attr2))
    if nums1 or nums2:
        common = len(nums1 & nums2)
        total = len(nums1 | nums2)
        numeric_score = common / total if total else 1.0
    else:
        numeric_score = 1.0
    text_score = name_similarity(attr1, attr2)
    return 0.5 * numeric_score + 0.5 * text_score


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------


def compute_composite_score(
    quote_name: str,
    quote_uom: str | None,
    quote_attr: str | None,
    pr_name: str,
    pr_uom: str | None,
    pr_attr: str | None,
) -> tuple[float, float, float, float]:
    """Return (composite, name_score, uom_score, attr_score) for a pair."""
    n = name_similarity(quote_name, pr_name)
    u = uom_similarity(quote_uom, pr_uom)
    a = attr_similarity(quote_attr, pr_attr)
    if not quote_attr or not pr_attr:
        # An absent attribute is unknown, not evidence against a match. Score
        # only the available signals so a near-identical name is not capped by
        # the placeholder neutral value (0.5).
        composite = (WEIGHT_NAME * n + WEIGHT_UOM * u) / (WEIGHT_NAME + WEIGHT_UOM)
    else:
        composite = WEIGHT_NAME * n + WEIGHT_UOM * u + WEIGHT_ATTR * a
    return composite, n, u, a


def _decide_status(score: float) -> MatchStatus:
    if score >= AUTO_MATCH_THRESHOLD:
        return MatchStatus.AUTO_MATCHED
    if score >= SUGGEST_THRESHOLD:
        return MatchStatus.SUGGESTED
    return MatchStatus.UNMATCHED


def _candidate_status(score: float, quote_name: str, pr_name: str) -> MatchStatus:
    """Classify score while preventing automatic matches with conflicting specs."""
    status = _decide_status(score)
    if status == MatchStatus.AUTO_MATCHED and _has_conflicting_numeric_specs(quote_name, pr_name):
        return MatchStatus.SUGGESTED
    return status


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class PRItem:
    """Lightweight data holder for a PR item passed into the matching service."""

    __slots__ = ("id", "name", "uom", "description")

    def __init__(
        self,
        id: str,  # noqa: A002
        name: str,
        uom: str | None = None,
        description: str | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.uom = uom
        self.description = description


class QuoteItemInput:
    """Lightweight data holder for an extracted/confirmed QuoteItem."""

    __slots__ = ("id", "name", "uom", "description")

    def __init__(
        self,
        id: str,  # noqa: A002
        name: str,
        uom: str | None = None,
        description: str | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.uom = uom
        self.description = description


class ProductMatchingService:
    """Match extracted quote items against a list of PR items.

    Usage::

        service = ProductMatchingService(synonym_dict={"laptop lenovo": "laptop"})
        result = service.match(quote_items, pr_items)

    The synonym_dict (optional) represents learned pairs from the
    SynonymDictionary, keyed by canonical quote item name → pr_item_id.
    When an exact match is found, score = 1.0 and status = AUTO_MATCHED.
    """

    def __init__(
        self,
        synonym_dict: dict[str, str] | None = None,
    ) -> None:
        # synonym_dict: { normalize_name(original_quote_name) -> pr_item_id }
        self._synonyms: dict[str, str] = synonym_dict or {}

    def match_one(
        self,
        quote_item: QuoteItemInput,
        pr_items: list[PRItem],
    ) -> MatchResult:
        """Return MatchResult for a single quote item against all PR items."""
        normalized = normalize_name(quote_item.name)

        # 1. Exact synonym lookup → score = 1.0
        if normalized in self._synonyms:
            pr_id = self._synonyms[normalized]
            pr = next((p for p in pr_items if p.id == pr_id), None)
            if pr is not None:
                best = MatchCandidate(
                    pr_item_id=pr.id,
                    pr_item_name=pr.name,
                    score=1.0,
                    name_score=1.0,
                    uom_score=1.0,
                    attr_score=1.0,
                    status=MatchStatus.AUTO_MATCHED,
                )
                return MatchResult(
                    quote_item_id=quote_item.id,
                    quote_item_name=quote_item.name,
                    best_match=best,
                    candidates=[best],
                    normalized_name=normalized,
                )

        # 2. Score all PR items
        candidates: list[MatchCandidate] = []
        for pr in pr_items:
            score, n, u, a = compute_composite_score(
                quote_item.name,
                quote_item.uom,
                quote_item.description,
                pr.name,
                pr.uom,
                pr.description,
            )
            status = _candidate_status(score, quote_item.name, pr.name)
            if n >= MIN_NAME_SCORE_FOR_CANDIDATE:
                candidates.append(
                    MatchCandidate(
                        pr_item_id=pr.id,
                        pr_item_name=pr.name,
                        score=round(score, 4),
                        name_score=round(n, 4),
                        uom_score=round(u, 4),
                        attr_score=round(a, 4),
                        status=status,
                    )
                )

        # Sort best first
        candidates.sort(key=lambda c: c.score, reverse=True)
        best = candidates[0] if candidates else None

        return MatchResult(
            quote_item_id=quote_item.id,
            quote_item_name=quote_item.name,
            best_match=best,
            candidates=candidates,
            normalized_name=normalized,
        )

    def match(
        self,
        quote_items: list[QuoteItemInput],
        pr_items: list[PRItem],
    ) -> BatchMatchResult:
        """Run matching for all quote items and aggregate statistics."""
        results: list[MatchResult] = []
        auto_matched = suggested = unmatched = 0

        for qi in quote_items:
            r = self.match_one(qi, pr_items)
            results.append(r)
            if r.best_match is None:
                unmatched += 1
            elif r.best_match.status == MatchStatus.AUTO_MATCHED:
                auto_matched += 1
            elif r.best_match.status == MatchStatus.SUGGESTED:
                suggested += 1
            else:
                unmatched += 1

        return BatchMatchResult(
            total=len(results),
            auto_matched=auto_matched,
            suggested=suggested,
            unmatched=unmatched,
            results=results,
        )

    def learn(self, original_name: str, pr_item_id: str) -> None:
        """Persist a confirmed match into the in-memory synonym dictionary.

        Call this after Buyer CONFIRM action. In production, persist to
        a SynonymDictionary DB table as well.
        """
        key = normalize_name(original_name)
        self._synonyms[key] = pr_item_id


__all__ = [
    "ProductMatchingService",
    "PRItem",
    "QuoteItemInput",
    "compute_composite_score",
    "name_similarity",
    "normalize_name",
    "uom_similarity",
]
