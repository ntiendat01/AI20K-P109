"""Unit tests for fuzzy matching service — Phương án 3: Heuristic + Trigram.

Run:
    pytest tests/test_fuzzy_match.py -v
"""

from __future__ import annotations

import pytest

from src.models.fuzzy_match import BatchMatchResult, MatchStatus
from src.services.fuzzy_match import (
    PRItem,
    ProductMatchingService,
    QuoteItemInput,
    compute_composite_score,
    name_similarity,
    normalize_name,
    uom_similarity,
)

# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_lowercase_and_strip(self):
        assert normalize_name("  Thép D10  ") == "thep d10"

    def test_removes_diacritics(self):
        result = normalize_name("Thép xây dựng")
        assert result == "thep xay dung"

    def test_removes_stop_words(self):
        result = normalize_name("cái bàn ghế")
        # "cai" is a stop-word
        assert "cai" not in result

    def test_applies_synonym_inox(self):
        result = normalize_name("ống Inox 304")
        assert "thep khong gi" in result

    def test_removes_punctuation(self):
        result = normalize_name("Thép, D10-Hòa Phát")
        assert "," not in result
        assert "-" not in result

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_synonym_stainless_steel(self):
        r1 = normalize_name("Stainless Steel 304")
        r2 = normalize_name("Inox 304")
        # Both should normalize to contain the same canonical form
        assert "thep khong gi" in r1
        assert "thep khong gi" in r2

    def test_synonyms_only_replace_complete_words(self):
        assert normalize_name("Samsung Galaxy Tab") == "samsung galaxy tab"
        assert "thep khong gi" not in normalize_name("Kính cường lực Glass")
        assert "thep carbon" not in normalize_name("Items Classic")

    def test_complete_word_synonyms_still_apply(self):
        assert "thep khong gi" in normalize_name("Ống SS 304")
        assert normalize_name("Máy tính xách tay Dell") == "laptop dell"


# ---------------------------------------------------------------------------
# name_similarity
# ---------------------------------------------------------------------------


class TestNameSimilarity:
    def test_identical_names(self):
        assert name_similarity("Thép D10", "Thép D10") == pytest.approx(1.0)

    def test_high_similarity_minor_difference(self):
        score = name_similarity("Thép xây dựng D10", "Thép cuộn D10 Hòa Phát")
        assert score >= 0.50, f"Expected >= 0.50, got {score}"

    def test_rebar_specification_matches_across_supplier_wording(self):
        score = name_similarity(
            "Thép thanh vằn D16, CB400-V, TCVN 1651-2:2018",
            "Thép xây dựng D16 CB400-V",
        )
        assert score == pytest.approx(1.0)

    def test_low_similarity_different_products(self):
        score = name_similarity("Laptop Dell XPS", "Bàn ghế văn phòng")
        assert score < 0.40, f"Expected < 0.40, got {score}"

    def test_symmetry(self):
        a = "Thép D10"
        b = "Thép D10 Hòa Phát"
        assert abs(name_similarity(a, b) - name_similarity(b, a)) < 1e-9

    def test_empty_returns_zero(self):
        assert name_similarity("", "Thép D10") == 0.0
        assert name_similarity("Thép D10", "") == 0.0


# ---------------------------------------------------------------------------
# uom_similarity
# ---------------------------------------------------------------------------


class TestUomSimilarity:
    def test_same_uom(self):
        assert uom_similarity("kg", "kg") == pytest.approx(1.0)

    def test_same_uom_case_insensitive(self):
        assert uom_similarity("KG", "kg") == pytest.approx(1.0)

    @pytest.mark.parametrize(
        ("left", "right"),
        [("MT", "tấn"), ("Cái", "Chiếc"), ("Ream", "Ram")],
    )
    def test_exact_uom_aliases(self, left, right):
        assert uom_similarity(left, right) == pytest.approx(1.0)

    def test_convertible_uom_within_group(self):
        # kg and tấn are both weight units → 0.8
        score = uom_similarity("kg", "tấn")
        assert score == pytest.approx(0.8)

    def test_incompatible_uom(self):
        # Weight vs counting → 0.0
        score = uom_similarity("kg", "cái")
        assert score == pytest.approx(0.0)

    def test_missing_uom_neutral(self):
        assert uom_similarity(None, "kg") == pytest.approx(0.5)
        assert uom_similarity("kg", None) == pytest.approx(0.5)
        assert uom_similarity(None, None) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# ProductMatchingService.match_one
# ---------------------------------------------------------------------------


@pytest.fixture
def pr_items() -> list[PRItem]:
    return [
        PRItem(id="pr_001", name="Thép xây dựng D10", uom="tấn"),
        PRItem(id="pr_002", name="Laptop Dell XPS 15", uom="cái"),
        PRItem(id="pr_003", name="Bơm nước công nghiệp 5HP", uom="cái"),
    ]


class TestMatchOne:
    def test_high_confidence_auto_match(self, pr_items):
        service = ProductMatchingService()
        item = QuoteItemInput(id="q1", name="Thép xây dựng D10", uom="tấn")
        result = service.match_one(item, pr_items)
        assert result.best_match is not None
        assert result.best_match.pr_item_id == "pr_001"
        assert result.best_match.status == MatchStatus.AUTO_MATCHED
        assert result.best_match.score >= 0.90

    def test_similar_name_produces_candidate(self, pr_items):
        service = ProductMatchingService()
        # Near-identical name should strongly match pr_001
        item = QuoteItemInput(id="q2", name="Thép xây dựng D10 Hòa Phát", uom="tấn")
        result = service.match_one(item, pr_items)
        # Should match pr_001 with SUGGESTED or AUTO_MATCHED
        assert result.best_match is not None
        assert result.best_match.pr_item_id == "pr_001"

    @pytest.mark.parametrize(
        "quote_name",
        [
            "Thép xây dựng D16 CB400-V; thép thanh vằn, TCVN 1651-2:2018; nhãn hiệu Vina Kyoei",
            "Thép thanh vằn D16, CB400-V, TCVN 1651-2:2018",
        ],
    )
    def test_rebar_quotes_auto_match_the_same_pr_item(self, quote_name):
        service = ProductMatchingService()
        result = service.match_one(
            QuoteItemInput(id="quote_d16", name=quote_name, uom="MT"),
            [PRItem(id="pr_d16", name="Thép xây dựng D16 CB400-V", uom="tấn")],
        )

        assert result.best_match is not None
        assert result.best_match.pr_item_id == "pr_d16"
        assert result.best_match.status == MatchStatus.AUTO_MATCHED
        assert result.best_match.score == pytest.approx(1.0)

    def test_conflicting_numeric_specs_cannot_auto_match(self):
        service = ProductMatchingService()
        result = service.match_one(
            QuoteItemInput(id="quote_d10", name="Thép D10", uom="tấn"),
            [PRItem(id="pr_d12", name="Thép D12", uom="tấn")],
        )

        assert result.best_match is not None
        assert result.best_match.status == MatchStatus.SUGGESTED

    def test_unmatched_candidate_is_available_for_manual_mapping(self):
        service = ProductMatchingService()
        result = service.match_one(
            QuoteItemInput(id="quote_5440", name="Laptop Dell Latitude 5440", uom="cái"),
            [PRItem(id="pr_5540", name="Laptop Dell Latitude 5540", uom="kg")],
        )

        assert result.best_match is not None
        assert result.best_match.status == MatchStatus.UNMATCHED
        assert [candidate.pr_item_id for candidate in result.candidates] == ["pr_5540"]

    def test_unrelated_item_unmatched(self, pr_items):
        service = ProductMatchingService()
        item = QuoteItemInput(id="q3", name="Phần mềm kế toán Fast", uom="bản quyền")
        result = service.match_one(item, pr_items)
        assert result.best_match is None

    def test_synonym_dict_exact_match(self, pr_items):
        service = ProductMatchingService(synonym_dict={"thep xay dung d10": "pr_001"})
        item = QuoteItemInput(id="q4", name="Thép xây dựng D10", uom="tấn")
        result = service.match_one(item, pr_items)
        assert result.best_match is not None
        assert result.best_match.score == pytest.approx(1.0)
        assert result.best_match.status == MatchStatus.AUTO_MATCHED

    def test_normalized_name_stored(self, pr_items):
        service = ProductMatchingService()
        item = QuoteItemInput(id="q5", name="Thép  D10")
        result = service.match_one(item, pr_items)
        assert result.normalized_name != ""
        assert result.normalized_name == normalize_name("Thép  D10")


# ---------------------------------------------------------------------------
# ProductMatchingService.match (batch)
# ---------------------------------------------------------------------------


class TestBatchMatch:
    def test_batch_statistics(self, pr_items):
        service = ProductMatchingService()
        items = [
            QuoteItemInput(id="q1", name="Thép xây dựng D10", uom="tấn"),
            QuoteItemInput(id="q2", name="Phần mềm ABC hoàn toàn khác"),
        ]
        batch: BatchMatchResult = service.match(items, pr_items)
        assert batch.total == 2
        assert batch.auto_matched + batch.suggested + batch.unmatched == 2

    def test_empty_quote_items(self, pr_items):
        service = ProductMatchingService()
        batch = service.match([], pr_items)
        assert batch.total == 0

    def test_empty_pr_items(self):
        service = ProductMatchingService()
        items = [QuoteItemInput(id="q1", name="Thép D10")]
        batch = service.match(items, [])
        # No PR items to compare against → all unmatched
        assert batch.total == 1
        assert batch.unmatched == 1

    def test_learn_updates_synonym(self, pr_items):
        service = ProductMatchingService()
        # Before learning
        item = QuoteItemInput(id="q1", name="SD Thép D10 Hòa Phát Vinakyoto")
        service.match_one(item, pr_items)

        # Learn the mapping
        service.learn("SD Thép D10 Hòa Phát Vinakyoto", "pr_001")

        # After learning, should be exact match
        result_after = service.match_one(item, pr_items)
        assert result_after.best_match is not None
        assert result_after.best_match.score == pytest.approx(1.0)
        assert result_after.best_match.status == MatchStatus.AUTO_MATCHED


# ---------------------------------------------------------------------------
# Threshold boundary tests
# ---------------------------------------------------------------------------


class TestThresholds:
    """Verify that score thresholds map to correct MatchStatus."""

    def test_exact_match_is_auto(self, pr_items):
        service = ProductMatchingService()
        item = QuoteItemInput(id="q1", name="Laptop Dell XPS 15", uom="cái")
        result = service.match_one(item, pr_items)
        assert result.best_match is not None
        assert result.best_match.status == MatchStatus.AUTO_MATCHED

    def test_score_boundaries_direct(self):
        from src.services.fuzzy_match import _decide_status

        assert _decide_status(1.00) == MatchStatus.AUTO_MATCHED
        assert _decide_status(0.90) == MatchStatus.AUTO_MATCHED
        assert _decide_status(0.89) == MatchStatus.SUGGESTED
        assert _decide_status(0.70) == MatchStatus.SUGGESTED
        assert _decide_status(0.69) == MatchStatus.UNMATCHED
        assert _decide_status(0.00) == MatchStatus.UNMATCHED


# ---------------------------------------------------------------------------
# compute_composite_score weight sanity
# ---------------------------------------------------------------------------


class TestCompositeScore:
    def test_missing_attributes_renormalize_available_weights(self):
        score, n, u, a = compute_composite_score(
            "Thép D10",
            "kg",
            None,
            "Thép D10",
            "kg",
            None,
        )

        assert (n, u, a) == pytest.approx((1.0, 1.0, 0.5))
        assert score == pytest.approx(1.0)

    def test_weights_sum_correctly(self):
        """Perfect name, unit and attributes retain the three-weight formula."""
        score, n, u, a = compute_composite_score(
            "Thép D10",
            "kg",
            "D10 standard",
            "Thép D10",
            "kg",
            "D10 standard",
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_uom_mismatch_reduces_score(self):
        """Same name but incompatible UoM should pull score below perfect."""
        score_match, *_ = compute_composite_score(
            "Thép D10",
            "kg",
            None,
            "Thép D10",
            "kg",
            None,
        )
        score_mismatch, *_ = compute_composite_score(
            "Thép D10",
            "kg",
            None,
            "Thép D10",
            "cái",
            None,  # incompatible UoM
        )
        assert score_mismatch < score_match


@pytest.mark.parametrize(
    ("quote_name", "quote_uom", "pr_name", "pr_uom", "expected_status"),
    [
        ("Laptop Dell Latitude 5440", "Cái", "Laptop Dell Latitude 5440 i5", "Cái", MatchStatus.AUTO_MATCHED),
        ("Máy tính xách tay Dell Latitude 5440", "Cái", "Laptop Dell Latitude 5440", "Chiếc", MatchStatus.AUTO_MATCHED),
        ("Thép tấm inox 304 dày 2mm", "Tấm", "Thép tấm không gỉ 304 2mm", "Tấm", MatchStatus.SUGGESTED),
        ("Bàn làm việc gỗ 1m2", "Cái", "Bàn làm việc gỗ 1.2m", "Cái", MatchStatus.SUGGESTED),
        ("Giấy A4 Double A", "Ream", "Giấy in A4 Double A 70gsm", "Ream", MatchStatus.SUGGESTED),
        ("Giấy A4 Double A", "Ream", "Giấy A4 Double A", "Ram", MatchStatus.AUTO_MATCHED),
        ("Samsung Galaxy Tab", "Cái", "Máy tính bảng Samsung Galaxy Tab", "Cái", MatchStatus.SUGGESTED),
        ("Laptop Dell Latitude 5440", "Cái", "Laptop Dell Latitude 5540", "Cái", MatchStatus.SUGGESTED),
        ("Bơm nước công nghiệp 5HP", "Cái", "Laptop Dell XPS 15", "Cái", MatchStatus.UNMATCHED),
    ],
)
def test_golden_product_name_pairs(quote_name, quote_uom, pr_name, pr_uom, expected_status):
    result = ProductMatchingService().match_one(
        QuoteItemInput(id="quote", name=quote_name, uom=quote_uom),
        [PRItem(id="pr", name=pr_name, uom=pr_uom)],
    )

    if expected_status == MatchStatus.UNMATCHED:
        assert result.best_match is None
        return

    assert result.best_match is not None
    assert result.best_match.status == expected_status
