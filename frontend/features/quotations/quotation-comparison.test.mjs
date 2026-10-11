import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { isQuotationReviewComplete, quotationMatchItemId, renderQuotationComparison } from "./quotation-comparison.js";
import { AI_OCR_EXTRACTION_MODE, uploadFilesInParallel } from "./quotation-list.js";
import { ANALYSIS_LOADING_ANIMATION_SRC, renderBuyerApprovalAction, renderVerifiedRecommendation, waitForCompletedAnalysis } from "../comparison/comparison.js";
import { releaseNumberInputOnWheel } from "../../core/number-input-wheel.js";

const quotation = (id, status) => ({
  id,
  status,
  supplier_name: `Nhà cung cấp ${id}`,
  delivery_time: "2 ngày",
  payment_terms: "Thanh toán sau 30 ngày",
  warranty: "12 tháng",
  items: [{
    product_code: "D16",
    product_name: "Thép thanh D16",
    unit: "tấn",
    quantity: 20,
    unit_price: id === "a" ? 15_000_000 : 15_180_000,
    line_total: id === "a" ? 300_000_000 : 303_600_000,
  }],
});

test("does not create comparison tables before every quotation is confirmed", () => {
  const quotations = [quotation("a", "confirmed"), quotation("b", "unconfirmed")];

  assert.equal(isQuotationReviewComplete(quotations), false);
  assert.equal(renderQuotationComparison(quotations), "");
});

test("uses AI OCR as the only upload extraction mode", () => {
  assert.equal(AI_OCR_EXTRACTION_MODE, "agent");
});

test("does not let the mouse wheel change a number input", () => {
  let blurred = false;
  const numberInput = { tagName: "INPUT", type: "number", blur: () => { blurred = true; } };

  releaseNumberInputOnWheel({ target: numberInput });

  assert.equal(blurred, true);
});

test("keeps date inputs focused when the mouse wheel moves over them", () => {
  let blurred = false;
  const dateInput = { tagName: "INPUT", type: "date", blur: () => { blurred = true; } };

  releaseNumberInputOnWheel({ target: dateInput });

  assert.equal(blurred, false);
});

test("starts all OCR uploads before the first extraction finishes", async () => {
  const started = [];
  const completed = [];
  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  await uploadFilesInParallel(["slow.pdf", "fast.pdf"], async (file) => {
    started.push(file);
    await wait(file === "slow.pdf" ? 20 : 1);
    completed.push(file);
  });

  assert.deepEqual(started, ["slow.pdf", "fast.pdf"]);
  assert.deepEqual(completed, ["fast.pdf", "slow.pdf"]);
});

test("waits on the review screen until the analysis reaches a result", async () => {
  const statuses = [{ status: "running" }, { status: "awaiting_buyer_review" }];
  let calls = 0;

  const result = await waitForCompletedAnalysis(
    async () => statuses[calls++],
    { waitFor: async () => { }, now: () => 0, initialIntervalMs: 1 },
  );

  assert.equal(calls, 2);
  assert.equal(result.status, "awaiting_buyer_review");
});

test("uses the supplied Lottie asset for the analysis loading state", async () => {
  const [indexPage, asset] = await Promise.all([
    readFile(new URL("../../index.html", import.meta.url), "utf8"),
    readFile(new URL("../../assets/animations/loading.json", import.meta.url), "utf8"),
  ]);

  assert.equal(ANALYSIS_LOADING_ANIMATION_SRC, "assets/animations/loading.json");
  assert.match(indexPage, /@lottiefiles\/lottie-player@2\.0\.12/);
  assert.equal(JSON.parse(asset).v, "5.7.4");
});

test("places a centered buyer approval button after the review content", () => {
  const markup = renderBuyerApprovalAction(true);

  assert.match(markup, /class="review-submit-action"/);
  assert.match(markup, /id="submit-review"/);
  assert.match(markup, /id="submit-review-error"/);
  assert.doesNotMatch(markup, /<section|Bước cuối|Đã rà soát/);
  assert.equal(renderBuyerApprovalAction(false), "");
});

test("renders a verified recommendation as a ranked decision brief", () => {
  const run = {
    recommendation_version: 1,
    tco_results: [
      { supplier_id: "steel-vn", total_tco: 331_100_000, total_vat: 30_100_000, total_surcharges: 0 },
      { supplier_id: "steel-kyoei", total_tco: 333_960_000, total_vat: 30_360_000, total_surcharges: 0 },
    ],
    comparison_matrix: {
      matrix: {
        "steel-vn": { lead_time_days: { value: "5" }, warranty_months: { value: "18" } },
        "steel-kyoei": { lead_time_days: { value: "6" }, warranty_months: { value: "12" } },
      },
    },
    risk_flags: [{ supplier_id: "steel-kyoei", risk_type: "lead_time_exceeded", severity: "error", message: "Vượt hạn giao 1 ngày làm việc" }],
  };
  const review = {
    preferred_supplier_id: "steel-vn",
    ranked_supplier_ids: ["steel-vn", "steel-kyoei"],
    rationale: "Ưu tiên chi phí, tiến độ và bảo hành.",
  };
  const names = { "steel-vn": "CÔNG TY CỔ PHẦN THÉP VIỆT NHẬT", "steel-kyoei": "CÔNG TY TNHH THÉP VINA KYOEI" };
  const markup = renderVerifiedRecommendation(run, review, (id) => names[id]);

  assert.match(markup, /Đề xuất nhà cung cấp tốt nhất/);
  assert.match(markup, /CÔNG TY CỔ PHẦN THÉP VIỆT NHẬT/);
  assert.match(markup, /Khuyên dùng · Tối ưu nhất/);
  assert.match(markup, /Tiết kiệm 2\.860\.000 VND/);
  assert.match(markup, /Nhanh hơn 1 ngày lịch/);
  assert.match(markup, /Thời hạn bảo hành dài hơn 6 tháng/);
  assert.match(markup, /Rủi ro tiến độ/);
  assert.match(markup, /Vượt hạn giao 1 ngày làm việc/);
});

test("does not expose a legacy English rationale on the Vietnamese recommendation screen", () => {
  const run = {
    tco_results: [{ supplier_id: "a", total_tco: 100, total_vat: 0, total_surcharges: 0 }],
    comparison_matrix: { matrix: { a: { lead_time_days: { value: "5" }, warranty_months: { value: "12" } } } },
    risk_flags: [],
  };
  const review = {
    preferred_supplier_id: "a",
    ranked_supplier_ids: ["a"],
    rationale: "Supplier a has the lower calculated total TCO and a 5-day lead time.",
  };
  const markup = renderVerifiedRecommendation(run, review, () => "Nhà cung cấp A");

  assert.doesNotMatch(markup, /Supplier a has the lower calculated total TCO/);
  assert.match(markup, /Đề xuất dựa trên đối chiếu tổng chi phí, tiến độ giao hàng và bảo hành/);
});

test("replaces stored supplier UUIDs and raw VND amounts in a Vietnamese rationale", () => {
  const preferredId = "27fbc7fd-d7d3-46a2-9def-e2f458239fda";
  const alternativeId = "f0e604d7-efec-41e2-9acf-207f1dce15a4";
  const run = {
    tco_results: [
      { supplier_id: preferredId, total_tco: 331_100_000, total_vat: 0, total_surcharges: 0 },
      { supplier_id: alternativeId, total_tco: 333_960_000, total_vat: 0, total_surcharges: 0 },
    ],
    comparison_matrix: { matrix: {
      [preferredId]: { lead_time_days: { value: "7" }, warranty_months: { value: "18" } },
      [alternativeId]: { lead_time_days: { value: "6" }, warranty_months: { value: "12" } },
    } },
    risk_flags: [],
  };
  const review = {
    preferred_supplier_id: preferredId,
    ranked_supplier_ids: [preferredId, alternativeId],
    rationale: `Đề xuất ưu tiên nhà cung cấp ${preferredId} với TCO là 331100000.00 VND; nhà cung cấp ${alternativeId} có TCO 333960000.00 VND.`,
  };
  const names = { [preferredId]: "CÔNG TY CỔ PHẦN THÉP VIỆT NHẬT", [alternativeId]: "CÔNG TY TNHH THÉP VINA KYOEI" };
  const markup = renderVerifiedRecommendation(run, review, (id) => names[id]);

  assert.match(markup, /CÔNG TY CỔ PHẦN THÉP VIỆT NHẬT với TCO là 331\.100\.000 VND/);
  assert.match(markup, /CÔNG TY TNHH THÉP VINA KYOEI có TCO 333\.960\.000 VND/);
  assert.doesNotMatch(markup, new RegExp(preferredId));
  assert.doesNotMatch(markup, /331100000\.00 VND/);
});

test("creates both comparison tables from confirmed quotations only", () => {
  const quotations = [quotation("a", "confirmed"), quotation("b", "confirmed")];
  const markup = renderQuotationComparison(quotations);

  assert.equal(isQuotationReviewComplete(quotations), true);
  assert.match(markup, /Bảng so sánh báo giá/);
  assert.match(markup, /Đánh giá thương mại/);
  assert.match(markup, /Đối chiếu fuzzy matching/);
  assert.match(markup, /Chưa khớp/);
});

test("uses the fuzzy-matched PR name instead of frontend name heuristics", () => {
  const quotations = [quotation("a", "confirmed"), quotation("b", "confirmed")];
  quotations[0].items[0].product_name = "Thép thanh D16 CB400-V";
  quotations[1].items[0].product_name = "Thép xây dựng D16";
  const matches = {
    results: quotations.map((quote) => ({
      quote_item_id: quotationMatchItemId(quote.id, 0),
      quote_item_name: quote.items[0].product_name,
      normalized_name: "thep thanh d16",
      candidates: [],
      best_match: {
        pr_item_id: "pr-steel-16",
        pr_item_name: "Thép thanh vằn D16, CB400-V, TCVN 1651-2:2018",
        score: 0.95,
        status: "auto_matched",
      },
    })),
  };

  const markup = renderQuotationComparison(quotations, matches);

  assert.match(markup, /Thép thanh vằn D16, CB400-V, TCVN 1651-2:2018/);
  assert.match(markup, /Tự động ghép · 95%/);
  assert.match(markup, /TỔNG ĐÃ GHÉP/);
  assert.equal((markup.match(/data-comparison-row/g) || []).length, 1);
});

test("shows confirm, reject, and manual-map controls for fuzzy review states", () => {
  const quotes = [quotation("a", "confirmed")];
  const candidate = {
    pr_item_id: "pr-steel-16",
    pr_item_name: "Thép thanh vằn D16",
    score: 0.82,
    status: "suggested",
  };
  const suggested = renderQuotationComparison(quotes, {
    results: [{ quote_item_id: quotationMatchItemId("a", 0), best_match: candidate, candidates: [candidate] }],
  });
  const unmatched = renderQuotationComparison(quotes, {
    results: [{ quote_item_id: quotationMatchItemId("a", 0), best_match: null, candidates: [candidate] }],
  });

  assert.match(suggested, /Cần xác nhận · 82%/);
  assert.match(suggested, /data-fuzzy-action="CONFIRM"/);
  assert.match(suggested, /data-fuzzy-action="REJECT"/);
  assert.match(unmatched, /data-manual-pr-item/);
  assert.match(unmatched, /data-fuzzy-action="MAP_TO_NEW"/);
});
