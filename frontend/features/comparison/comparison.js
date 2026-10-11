import { escapeHtml, formatBudget, formatDate, formatComparisonMoney } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { ANALYSIS_POLL_INTERVAL_MS, ANALYSIS_POLL_MAX_WAIT_MS, API_ROOT } from "../../config/constants.js";
import { setFlash, takeFlash } from "../../core/session.js";
import { statusPill, errorState, showSuccessNotice } from "../../core/ui-helpers.js";

const statusCopy = {
  not_started: "Chưa phân tích", running: "Đang phân tích", awaiting_buyer_review: "Đề xuất đã kiểm chứng",
  pending_manager_approval: "Đang chờ Quản lý phê duyệt",
  needs_input: "Cần bổ sung dữ liệu", repairable: "Đề xuất cần sửa", technical_failure: "Phân tích chưa thành công",
  exception_required: "Cần quyết định ngoại lệ", no_viable_supplier: "Chưa có NCC đáp ứng",
  stale: "Cần phân tích lại", approved: "Đã duyệt (link PO)", rejected: "Đã từ chối", awaiting_input: "Chờ cập nhật dữ liệu", awaiting_repair: "Chờ sửa đề xuất",
};
const metrics = { tco: "Tổng chi phí", delivery_days: "Ngày giao", warranty_months: "Bảo hành" };
const units = { VND: "VND", calendar_day: "ngày lịch", month: "tháng" };
const issueCopy = {
  INVALID_OUTPUT_CONTRACT: "Đề xuất trả về chưa đúng cấu trúc; hệ thống có thể chạy lại.",
  UNKNOWN_RISK_USED_AS_SUPPORT: "Rủi ro chưa có dữ liệu đang bị dùng làm căn cứ đề xuất; cần tạo lại đề xuất.",
  UNKNOWN_RISK_AS_ASSERTION: "Rủi ro chưa có dữ liệu phải được ghi là điểm chưa chắc chắn, không phải căn cứ đề xuất.",
  MANDATORY_SOURCE_UNRESOLVED: "Một nhận định trong đề xuất chưa có bằng chứng xác thực; hãy chạy lại phân tích.",
  TCO_CLAIM_MISMATCH: "Số tổng chi phí trong đề xuất không khớp kết quả công cụ tính toán.",
  TOP_N_MISMATCH: "Số lượng nhà cung cấp được xếp hạng không khớp phạm vi phân tích.",
  INVALID_SHORTFALL: "Thông tin thiếu nhà cung cấp trong xếp hạng chưa hợp lệ.",
  DANGLING_OR_DUPLICATE_REFERENCE: "Đề xuất tham chiếu dữ liệu nội bộ không hợp lệ.",
};

let activeAnalysisPoll = null;
let activeAnalysisLoading = null;

export const ANALYSIS_LOADING_ANIMATION_SRC = "assets/animations/loading.json";

export function renderBuyerApprovalAction(canSubmitReview) {
  if (!canSubmitReview) return "";
  return `<div class="review-submit-action"><button class="inline-primary btn-submit-approval" id="submit-review" type="button">Gửi Quản lý phê duyệt →</button><p class="error" id="submit-review-error" role="alert"></p></div>`;
}

function numericValue(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function comparisonMetric(run, supplierId, metric) {
  const cell = run.comparison_matrix?.matrix?.[supplierId]?.[metric];
  return numericValue(cell?.value ?? cell);
}

function formatMetricDelta(value, unit) {
  if (!Number.isFinite(value)) return "—";
  const display = Number.isInteger(value) ? value.toLocaleString("vi-VN") : value.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
  return `${display} ${unit}`;
}

function recommendationSupplierIds(run, review) {
  const rankedIds = (review.ranked || review.ranked_supplier_ids || []).map((entry) => typeof entry === "string" ? entry : entry.supplier_id);
  const tcoIds = (run.tco_results || []).map((entry) => entry.supplier_id);
  const matrixIds = Object.keys(run.comparison_matrix?.matrix || {});
  return [...new Set([review.preferred_supplier_id, ...rankedIds, ...tcoIds, ...matrixIds])].filter(Boolean);
}

function riskLabel(risk) {
  if (!risk) return "Đã kiểm chứng";
  if (risk.risk_type?.includes("lead_time") || risk.risk_type?.includes("delivery")) return "Rủi ro tiến độ";
  if (risk.risk_type?.includes("warranty")) return "Rủi ro bảo hành";
  if (risk.risk_type?.includes("normalization")) return "Cần rà soát dữ liệu";
  return "Cần lưu ý";
}

function supplierRisks(run, supplierId) {
  return (run.risk_flags || []).filter((risk) => risk.supplier_id === supplierId);
}

function isVietnameseProse(value) {
  if (typeof value !== "string") return false;
  return /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i.test(value)
    || /\b(nhà cung cấp|đề xuất|chi phí|giao hàng|bảo hành|rủi ro|tổng chi phí)\b/i.test(value);
}

function localizeStoredRationale(value, supplierIds, name) {
  if (!isVietnameseProse(value)) return null;
  let localized = value.trim();
  for (const supplierId of supplierIds) localized = localized.split(supplierId).join(name(supplierId));
  localized = localized.replace(/\b(\d{4,})(?:\.0+)?\s*VND\b/gi, (_, amount) => `${formatComparisonMoney(amount)} VND`);
  return /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i.test(localized) ? null : localized;
}

function recommendationInsights(run, preferredId, alternativeId, name) {
  const preferredTco = numericValue((run.tco_results || []).find((item) => item.supplier_id === preferredId)?.total_tco);
  const alternativeTco = numericValue((run.tco_results || []).find((item) => item.supplier_id === alternativeId)?.total_tco);
  const preferredLeadTime = comparisonMetric(run, preferredId, "lead_time_days");
  const alternativeLeadTime = comparisonMetric(run, alternativeId, "lead_time_days");
  const preferredWarranty = comparisonMetric(run, preferredId, "warranty_months");
  const alternativeWarranty = comparisonMetric(run, alternativeId, "warranty_months");
  const costSaving = alternativeTco !== null && preferredTco !== null ? alternativeTco - preferredTco : null;
  const deliveryGain = alternativeLeadTime !== null && preferredLeadTime !== null ? alternativeLeadTime - preferredLeadTime : null;
  const warrantyGain = alternativeWarranty !== null && preferredWarranty !== null ? preferredWarranty - alternativeWarranty : null;
  const alternativeName = alternativeId ? name(alternativeId) : "phương án khác";

  return [
    preferredTco === null ? null : {
      tone: "cost",
      title: "Chi phí tối ưu (TCO)",
      detail: costSaving !== null && costSaving > 0
        ? `Tiết kiệm ${formatComparisonMoney(costSaving)} VND so với ${alternativeName}.`
        : `Tổng chi phí đã tính: ${formatComparisonMoney(preferredTco)} VND.`,
      signal: `Tối ưu chi phí: ${formatComparisonMoney(preferredTco)} VND`,
    },
    preferredLeadTime === null ? null : {
      tone: "delivery",
      title: "Tiến độ giao hàng",
      detail: deliveryGain !== null && deliveryGain > 0
        ? `Nhanh hơn ${formatMetricDelta(deliveryGain, "ngày lịch")} so với ${alternativeName}.`
        : `Giao trong ${formatMetricDelta(preferredLeadTime, "ngày lịch")} sau xác nhận đơn hàng.`,
      signal: deliveryGain !== null && deliveryGain > 0
        ? `Giao hàng: nhanh hơn ${formatMetricDelta(deliveryGain, "ngày")}`
        : `Giao hàng: ${formatMetricDelta(preferredLeadTime, "ngày lịch")}`,
    },
    preferredWarranty === null ? null : {
      tone: "warranty",
      title: "Chính sách bảo hành",
      detail: warrantyGain !== null && warrantyGain > 0
        ? `Thời hạn bảo hành dài hơn ${formatMetricDelta(warrantyGain, "tháng")} so với ${alternativeName}.`
        : `Thời hạn bảo hành: ${formatMetricDelta(preferredWarranty, "tháng")}.`,
      signal: warrantyGain !== null && warrantyGain > 0
        ? `Bảo hành: thêm ${formatMetricDelta(warrantyGain, "tháng")}`
        : `Bảo hành: ${formatMetricDelta(preferredWarranty, "tháng")}`,
    },
  ].filter(Boolean);
}

export function renderVerifiedRecommendation(run, review, name, evidenceMarkup = "") {
  const supplierIds = recommendationSupplierIds(run, review);
  const preferredId = review.preferred_supplier_id || supplierIds[0];
  const orderedSupplierIds = [...new Set([preferredId, ...supplierIds])].filter(Boolean);
  const alternativeId = orderedSupplierIds.find((supplierId) => supplierId !== preferredId);
  const insights = recommendationInsights(run, preferredId, alternativeId, name);
  const version = String(run.recommendation_version || 1);
  const versionLabel = version.includes(".") ? version : `${version}.0`;
  const nonPreferredRisk = orderedSupplierIds.flatMap((supplierId) => supplierId === preferredId ? [] : supplierRisks(run, supplierId).map((risk) => ({ ...risk, supplierId }))).at(0);
  const rankedRows = orderedSupplierIds.map((supplierId, index) => {
    const tco = (run.tco_results || []).find((item) => item.supplier_id === supplierId) || {};
    const risk = supplierRisks(run, supplierId)[0];
    const isPreferred = supplierId === preferredId;
    const assessment = isPreferred ? "Khuyên dùng · Tối ưu nhất" : riskLabel(risk);
    return `<tr class="${isPreferred ? "is-recommended" : ""}"><td class="recommendation-rank">#${index + 1}${index === 0 ? " <span aria-hidden=\"true\">♛</span>" : ""}</td><th scope="row">${escapeHtml(name(supplierId))}</th><td>${formatComparisonMoney(tco.total_tco)} VND</td><td>${formatComparisonMoney(tco.total_vat)} VND</td><td>${formatComparisonMoney(tco.total_surcharges)} VND</td><td><span class="assessment-pill ${isPreferred ? "is-recommended" : risk ? "has-risk" : "is-verified"}">${escapeHtml(assessment)}</span></td></tr>`;
  }).join("");
  const insightCards = insights.map((insight) => `<article class="agent-insight-card ${insight.tone}"><h4>${escapeHtml(insight.title)}</h4><p>${escapeHtml(insight.detail)}</p></article>`).join("");
  const signals = insights.map((insight) => `<li>${escapeHtml(insight.signal)}</li>`).join("");
  const localizedRationale = localizeStoredRationale(review.rationale, orderedSupplierIds, name);
  const rationale = localizedRationale
    ? `<p class="recommendation-rationale">${escapeHtml(localizedRationale)}</p>`
    : `<p class="recommendation-rationale">Đề xuất dựa trên đối chiếu tổng chi phí, tiến độ giao hàng và bảo hành từ các báo giá đã xác nhận.</p>`;
  const riskSummary = nonPreferredRisk
    ? `<aside class="recommendation-risk" role="note"><strong>⚠ Cảnh báo rủi ro (${escapeHtml(name(nonPreferredRisk.supplierId))}):</strong> ${escapeHtml(nonPreferredRisk.message || riskLabel(nonPreferredRisk))}</aside>`
    : `<aside class="recommendation-risk is-clear" role="note"><strong>✓ Phạm vi đã rà soát:</strong> Chưa ghi nhận cảnh báo rủi ro bổ sung trong dữ liệu báo giá đã xác nhận.</aside>`;
  const proof = evidenceMarkup ? `<details class="recommendation-proof"><summary>Xem căn cứ và bằng chứng đã kiểm chứng</summary><ul class="verified-claims agent-claims">${evidenceMarkup}</ul></details>` : "";

  return `<section class="ai-hero-card recommendation-brief">
    <div class="recommendation-brief-meta"><span class="verified-brief-badge">✓ Đã kiểm chứng</span><span>Dữ liệu đã qua đối chiếu điều kiện mua sắm</span></div>
    <p class="section-kicker">Đề xuất nhà cung cấp tốt nhất</p>
    <div class="recommendation-title-row"><h3>${escapeHtml(name(preferredId))}</h3><span class="selected-supplier-badge">✓ Lựa chọn tối ưu #1</span></div>
    ${signals ? `<ul class="recommendation-signals">${signals}</ul>` : ""}
  </section>
  <section class="comparison-panel recommendation-ranking-card">
    <div class="recommendation-section-heading"><div><p class="section-kicker">Kết quả đã kiểm chứng</p><h3>So sánh &amp; Xếp hạng Nhà cung cấp</h3></div><p>${orderedSupplierIds.length} nhà cung cấp trong phạm vi đánh giá</p></div>
    <div class="comparison-scroll"><table class="comparison-table recommendation-ranking-table"><thead><tr><th>Thứ hạng</th><th>Nhà cung cấp (NCC)</th><th>Tổng gồm VAT &amp; phí</th><th>VAT</th><th>Phí trước VAT</th><th>Đánh giá</th></tr></thead><tbody>${rankedRows}</tbody></table></div>
  </section>
  <section class="detail-card agent-evidence-card">
    <div class="recommendation-section-heading"><div><p class="section-kicker">Lý do được ưu tiên</p><h3>💡 Căn cứ &amp; Đánh giá từ Agent</h3></div></div>
    ${rationale}${insightCards ? `<p class="agent-insight-intro">${insights.length} điểm nổi bật của ${escapeHtml(name(preferredId))}</p><div class="agent-insight-grid">${insightCards}</div>` : ""}
    ${riskSummary}${proof}
  </section>`;
}

function openAnalysisLoading(opener) {
  if (activeAnalysisLoading) {
    activeAnalysisLoading.dialog.focus();
    return;
  }
  const launchElement = opener instanceof HTMLElement ? opener : document.activeElement;
  document.body.insertAdjacentHTML("beforeend", `<div class="analysis-loading-backdrop" data-analysis-loading><section class="analysis-loading-dialog" role="dialog" aria-modal="true" aria-labelledby="analysis-loading-title" aria-describedby="analysis-loading-description" tabindex="-1"><lottie-player class="analysis-loading-lottie" src="${ANALYSIS_LOADING_ANIMATION_SRC}" background="transparent" speed="1" renderer="svg" loop autoplay aria-hidden="true"></lottie-player><p class="section-kicker">Phân tích nhà cung cấp</p><h2 id="analysis-loading-title">Agent đang phân tích báo giá</h2><p id="analysis-loading-description">Đang đối chiếu chi phí, thời gian giao và các điều kiện thương mại.</p><div class="analysis-loading-status" role="status" aria-live="polite"><span aria-hidden="true"></span>Kết quả sẽ tự cập nhật.</div></section></div>`);
  const backdrop = document.querySelector("[data-analysis-loading]");
  const dialog = backdrop.querySelector(".analysis-loading-dialog");
  const onKeydown = (event) => {
    if (event.key === "Tab") {
      event.preventDefault();
      dialog.focus();
    }
  };
  activeAnalysisLoading = { backdrop, dialog, launchElement, onKeydown };
  document.body.classList.add("analysis-loading-open");
  document.addEventListener("keydown", onKeydown);
  window.requestAnimationFrame(() => dialog.focus());
}

function closeAnalysisLoading() {
  if (!activeAnalysisLoading) return;
  const { backdrop, launchElement, onKeydown } = activeAnalysisLoading;
  document.removeEventListener("keydown", onKeydown);
  backdrop.remove();
  document.body.classList.remove("analysis-loading-open");
  activeAnalysisLoading = null;
  if (launchElement instanceof HTMLElement && document.contains(launchElement)) launchElement.focus();
}

function stopAnalysisPolling() {
  activeAnalysisPoll?.controller.abort();
  activeAnalysisPoll = null;
}

const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export async function waitForCompletedAnalysis(getRun, options = {}) {
  const waitFor = options.waitFor || wait;
  const now = options.now || Date.now;
  const maximumWaitMs = options.maximumWaitMs || ANALYSIS_POLL_MAX_WAIT_MS;
  let interval = options.initialIntervalMs || ANALYSIS_POLL_INTERVAL_MS;
  const startedAt = now();

  while (now() - startedAt < maximumWaitMs) {
    await waitFor(interval);
    const run = await getRun();
    if (run.status !== "running") return run;
    interval = Math.min(Math.round(interval * 1.25), 5_000);
  }

  throw new Error("Phân tích đang lâu hơn dự kiến. Hãy thử lại sau.");
}

export async function runAnalysisFromReview(session, requestId, opener) {
  openAnalysisLoading(opener);
  try {
    const started = await requestApi(`/prs/${encodeURIComponent(requestId)}/analysis`, session, { method: "POST" });
    if (started.status === "running") {
      await waitForCompletedAnalysis(() => requestApi(`/prs/${encodeURIComponent(requestId)}/analysis`, session));
    }
    closeAnalysisLoading();
    window.location.hash = `#/comparison/${encodeURIComponent(requestId)}`;
  } catch (error) {
    closeAnalysisLoading();
    // Validation errors persist a repairable analysis run. Route to it so the
    // buyer sees the concrete fields to fix instead of a transient message.
    if (error.status === 422) {
      window.location.hash = `#/comparison/${encodeURIComponent(requestId)}`;
      return;
    }
    throw error;
  }
}

async function pollAnalysis(session, requestId) {
  stopAnalysisPolling();
  const controller = new AbortController();
  const poll = { requestId, controller };
  activeAnalysisPoll = poll;
  const cancelOnNavigation = () => {
    if (window.location.hash !== `#/comparison/${requestId}`) {
      controller.abort();
      closeAnalysisLoading();
    }
  };
  window.addEventListener("hashchange", cancelOnNavigation);
  const startedAt = Date.now();
  let interval = ANALYSIS_POLL_INTERVAL_MS;
  try {
    while (!controller.signal.aborted) {
      await wait(interval);
      // Hash navigation is the lifecycle boundary for this small SPA. Do not
      // leave a request alive after the buyer switches screen.
      if (window.location.hash !== `#/comparison/${requestId}`) return;
      const run = await requestApi(`/prs/${encodeURIComponent(requestId)}/analysis`, session, { signal: controller.signal });
      if (run.status !== "running") {
        if (activeAnalysisPoll === poll) activeAnalysisPoll = null;
        await renderComparison(session, requestId);
        return;
      }
      if (Date.now() - startedAt >= ANALYSIS_POLL_MAX_WAIT_MS) {
        const error = document.querySelector("#analysis-error");
        if (error) error.textContent = "Phân tích đang lâu hơn dự kiến. Bạn có thể tải lại trạng thái hoặc thử lại sau.";
        closeAnalysisLoading();
        return;
      }
      interval = Math.min(Math.round(interval * 1.25), 5_000);
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      const message = document.querySelector("#analysis-error");
      if (message) message.textContent = "Không cập nhật được trạng thái phân tích. Hãy tải lại trạng thái.";
      closeAnalysisLoading();
    }
  } finally {
    window.removeEventListener("hashchange", cancelOnNavigation);
    if (activeAnalysisPoll === poll) activeAnalysisPoll = null;
  }
}

export async function renderComparison(session, requestId) {
  stopAnalysisPolling();
  const content = document.querySelector("#page-content");
  content.innerHTML = `<section class="empty" role="status"><p>Đang tải kết quả phân tích…</p></section>`;
  try {
    const run = await requestApi(`/prs/${encodeURIComponent(requestId)}/analysis`, session);
    if (run.status !== "running") closeAnalysisLoading();
    const pr = run.pr;
    let review = null;
    if (run.status === "awaiting_buyer_review" || (run.status === "pending_manager_approval" && session.user.role === "manager")) review = await requestApi(`/recommendations/${run.recommendation_id}/review`, session);
    else if (run.status === "approved") review = run.review;
    const names = Object.fromEntries((run.tco_results || []).map((tco) => [tco.supplier_id, tco.supplier_id]));
    Object.assign(names, run.supplier_names || {});
    const name = (id) => names[id] || "Nhà cung cấp";
    const flash = takeFlash();
    const claimText = (claim) => {
      const p = claim.predicate;
      if (p.operator === "equals") return `${metrics[p.metric] || p.metric}: ${p.metric === "tco" ? formatComparisonMoney(p.value) : p.value} ${units[p.unit] || p.unit}${p.time_origin === "order_confirmation" ? " sau xác nhận đơn hàng" : ""}`;
      if (p.operator === "meets_criterion") return `${p.criterion}: ${p.value ? "Đáp ứng" : "Chưa đáp ứng"}`;
      return `${metrics[p.metric] || p.metric}: ${name(p.subject_supplier_id)} ${p.operator === "minimum" ? "thấp nhất" : p.operator === "maximum" ? "cao nhất" : p.operator === "greater_than" ? "cao hơn" : "thấp hơn"}${p.other_supplier_id ? ` ${name(p.other_supplier_id)}` : " trong các NCC"}`;
    };
    // The current decision contract exposes ranked_supplier_ids/tradeoffs;
    // retain the old verified-review shape as a backward-compatible renderer.
    const ranked = review?.ranked || (review?.ranked_supplier_ids || []).map((supplier_id) => ({ supplier_id, claim_ids: [] }));
    const claimsById = review?.claims || {};
    const criticalUncertaintyIds = review?.critical_uncertainty_ids || [];
    const managerActions = `<button class="danger-button" id="reject" type="button">Từ chối đề xuất</button><button class="inline-primary" id="approve" type="button">Phê duyệt và tạo PO nháp →</button>`;
    const managerApproval = session.user.role === "manager" && run.status === "pending_manager_approval" && pr.status === "pending_approval" && review
      ? `<section class="detail-card"><h3>Quyết định phê duyệt</h3><label for="manager-note">Ghi chú phê duyệt hoặc lý do từ chối</label><textarea id="manager-note" rows="3" maxlength="500" placeholder="Bắt buộc khi từ chối đề xuất"></textarea>${criticalUncertaintyIds.map((id) => `<label><input type="checkbox" data-acknowledge="${escapeHtml(id)}" /> Tôi đã xem xét rủi ro bắt buộc này.</label>`).join("")}<div class="form-actions">${managerActions}</div><p class="error" id="review-error" role="alert"></p></section>`
      : "";
    const claims = review ? Object.entries(claimsById).map(([id, claim]) => `<li id="claim-${escapeHtml(id)}"><strong>${escapeHtml(claim.supplier_ids.map(name).join(" / "))}</strong> — ${escapeHtml(claimText(claim))}<details><summary>Bằng chứng đã đối chiếu</summary>${claim.evidence.sources.filter((s) => s.chunk.source_kind === "human_edit").map((s) => `<p>${escapeHtml(s.exact_excerpt)} <small>(Số liệu Buyer đã xác nhận; liên kết file gốc)</small> <button class="secondary" data-review-source="${escapeHtml(s.chunk.document_id)}">Tải file gốc</button></p>`).join("")}</details></li>`).join("") : "";
    const verifiedRecommendation = review ? renderVerifiedRecommendation(run, review, name, claims) : "";
    const diagnostics = run.evaluation ? `<details><summary>Chi tiết kiểm tra</summary><ul>${run.evaluation.stage_results.map((s) => `<li>${escapeHtml(s.stage)}: ${escapeHtml(s.status)}</li>`).join("")}</ul>${run.evaluation.issues.map((i) => `<p>${escapeHtml(issueCopy[i.code] || "Cần tạo lại đề xuất theo dữ liệu đã xác nhận.")}</p>`).join("")}</details>` : "";
    const managerNote = run.manager_note ? `<div class="analysis-guidance"><strong>Ghi chú của Quản lý</strong><p>${escapeHtml(run.manager_note)}</p></div>` : "";
    const buyerCanAct = session.user.role === "procurement" && ["comparing", "awaiting_quotation"].includes(pr.status);
    const repairableRun = ["repairable", "technical_failure", "awaiting_repair", "rejected"].includes(run.status);
    const canSubmitReview = Boolean(review && review.status === "proposed" && run.status === "awaiting_buyer_review" && session.user.role === "procurement" && pr.status === "comparing");
    const submitReviewAction = renderBuyerApprovalAction(canSubmitReview);
    const analysisStatus = run.status === "needs_input" ? "Cần tạo lại đề xuất" : statusCopy[run.status] || run.status;
    const analysisMessage = run.status === "running"
      ? "Hệ thống đang chuẩn hoá dữ liệu, gọi Agent và kiểm tra bằng chứng. Kết quả sẽ tự cập nhật; không cần bấm lại."
      : run.status === "needs_input"
        ? (run.message || "Phiên phân tích này dùng dữ liệu báo giá chưa hợp lệ. Rà soát báo giá đã xác nhận rồi chạy lại phân tích.")
        : run.status === "pending_manager_approval"
          ? "Đề xuất đã được gửi vào hàng đợi phê duyệt. Bạn sẽ nhận được kết quả sau khi Quản lý hoàn tất xem xét."
          : run.message || "Xác nhận ít nhất 2 báo giá độc lập, VAT/phí, ngày giao và bảo hành để bắt đầu.";
    const analysisAction = run.status === "running"
      ? `<div class="analysis-progress" role="status" aria-live="polite"><button class="inline-primary" disabled aria-disabled="true">Đang phân tích…</button><p>Thường mất khoảng 20–60 giây. Bạn có thể chờ tại màn hình này.</p></div>`
      : buyerCanAct && run.status === "needs_input"
        ? `<button class="inline-primary" id="analyze">Chạy lại phân tích</button>`
        : buyerCanAct && repairableRun
          ? `<button class="inline-primary" id="analyze">${run.status === "technical_failure" ? "Thử lại phân tích" : "Chạy lại phân tích"}</button>`
          : buyerCanAct && !["awaiting_buyer_review", "pending_manager_approval", "approved"].includes(run.status)
            ? `<button class="inline-primary" id="analyze">Phân tích bằng Agent</button>`
            : "";
    content.innerHTML = `<button class="back-link" id="back-quotes">← Báo giá</button>${flash ? `<div class="flash-message ${flash.tone}" role="status">${escapeHtml(flash.message)}</div>` : ""}<div class="comparison-workspace">
      <section class="detail-card"><div class="detail-heading"><div><p class="detail-code">${escapeHtml(pr.code)}</p><h2>${escapeHtml(pr.category)}</h2></div>${statusPill(pr.status)}</div><p>Ngân sách ${formatBudget(pr.estimated_budget)} · Hạn giao ${formatDate(pr.delivery_due_date)}</p></section>
      ${review ? verifiedRecommendation : `<section class="ai-hero-card"><p class="section-kicker">Phân tích nhà cung cấp</p><h3>${escapeHtml(analysisStatus)}</h3><p>${escapeHtml(analysisMessage)}</p>${managerNote}${analysisAction}${diagnostics}</section>`}
      ${review && managerNote ? `<section class="detail-card"><h3>Ghi chú của Quản lý</h3><p>${escapeHtml(run.manager_note)}</p></section>` : ""}
      ${review && diagnostics ? `<section class="detail-card analysis-diagnostics">${diagnostics}</section>` : ""}
      <p id="analysis-error" class="error" role="alert"></p>
      ${submitReviewAction}
      ${managerApproval}
      ${pr.po_id ? `<button class="inline-primary" id="open-po">Mở PO nháp →</button>` : ""}</div>`;
    content.querySelectorAll("[data-review-source]").forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const response = await fetch(`${API_ROOT}/recommendations/${run.recommendation_id}/sources/${encodeURIComponent(button.dataset.reviewSource)}`, { headers: { Authorization: `Bearer ${session.access_token}` } });
        if (!response.ok) { const problem = await response.json(); throw new Error(problem.detail || "Không tải được nguồn đã kiểm chứng."); }
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a"); link.href = url;
        const disposition = response.headers.get("Content-Disposition") || "";
        const utfName = disposition.match(/filename\*=utf-8''([^;]+)/i);
        const plainName = disposition.match(/filename="([^"]+)"/i);
        link.download = utfName ? decodeURIComponent(utfName[1]) : plainName ? plainName[1] : "bao-gia-nguon";
        link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
      } catch (error) { content.querySelector("#analysis-error").textContent = error.message; }
      finally { button.disabled = false; }
    }));
    content.querySelectorAll("[data-claim-link]").forEach((link) => link.addEventListener("click", (event) => {
      event.preventDefault(); document.getElementById(`claim-${link.dataset.claimLink}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    content.querySelector("#back-quotes").addEventListener("click", () => { window.location.hash = session.user.role === "manager" ? "#/approvals" : `#/quotations/${requestId}`; });
    content.querySelector("#open-po")?.addEventListener("click", () => { window.location.hash = `#/po/${pr.po_id}`; });
    for (const [id, path, message] of [["analyze", "analysis", "Đang phân tích…"]]) {
      content.querySelector(`#${id}`)?.addEventListener("click", async (event) => {
        const button = event.currentTarget; button.disabled = true; button.textContent = message;
        content.querySelector("#analysis-error").textContent = "";
        if (id === "analyze") openAnalysisLoading(button);
        try {
          await requestApi(`/prs/${encodeURIComponent(requestId)}/${path}`, session, { method: "POST" });
          await renderComparison(session, requestId);
        } catch (error) {
          // Input validation now returns 422 synchronously, but its saved run
          // contains the field-by-field repair guidance the buyer needs.
          if (id === "analyze" && error.status === 422) { await renderComparison(session, requestId); return; }
          if (id === "analyze") closeAnalysisLoading();
          content.querySelector("#analysis-error").textContent = error.message;
          button.disabled = false;
          button.textContent = id === "analyze" ? "Thử phân tích lại" : "Thử gửi duyệt lại";
        }
      });
    }
    content.querySelector("#submit-review")?.addEventListener("click", async (event) => {
      const button = event.currentTarget; button.disabled = true; button.textContent = "Đang gửi duyệt…";
      const error = content.querySelector("#submit-review-error"); error.textContent = "";
      try {
        await requestApi(`/analyses/${encodeURIComponent(run.analysis_id)}/submit-approval`, session, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
        });
        await showSuccessNotice({
          title: "Đã gửi đề xuất cho Quản lý",
          description: "Đề xuất đã vào hàng đợi phê duyệt. Quản lý sẽ xem xét trước khi quyết định tạo PO nháp.",
          opener: button,
        });
        await renderComparison(session, requestId);
      } catch (error) {
        content.querySelector("#submit-review-error").textContent = error.message;
        button.disabled = false; button.textContent = "Thử gửi duyệt lại";
      }
    });
    for (const decision of ["approve", "reject"]) content.querySelector(`#${decision}`)?.addEventListener("click", async (event) => {
      const note = content.querySelector("#manager-note").value.trim();
      const error = content.querySelector("#review-error"); error.textContent = "";
      if (["reject", "revise"].includes(decision) && !note) { error.textContent = "Vui lòng nhập lý do hoặc nội dung cần giải thích lại."; return; }
      const buttons = content.querySelectorAll("#approve, #reject"); buttons.forEach((b) => { b.disabled = true; });
      const key = `review:${session.user.id}:${run.recommendation_id}:${run.recommendation_version}:${decision}`;
      let payload = JSON.parse(sessionStorage.getItem(key) || "null");
      if (!payload) { payload = { feedback_id: crypto.randomUUID(), recommendation_id: run.recommendation_id, recommendation_version: run.recommendation_version, idempotency_key: crypto.randomUUID(), decision, note, acknowledged_uncertainty_ids: [...content.querySelectorAll("[data-acknowledge]:checked")].map((input) => input.dataset.acknowledge) }; sessionStorage.setItem(key, JSON.stringify(payload)); }
      try {
        const result = await requestApi(`/recommendations/${run.recommendation_id}/feedback`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        setFlash(decision === "approve" ? "Đã phê duyệt và tạo PO nháp." : decision === "revise" ? "Đã chuyển yêu cầu giải thích lại cho Buyer chạy phiên bản mới." : "Đã từ chối đề xuất.");
        window.location.hash = result.po ? `#/po/${result.po.id}` : "#/approvals";
      } catch (exception) { if ([400, 403, 409, 422].includes(exception.status)) sessionStorage.removeItem(key); error.textContent = exception.message; buttons.forEach((b) => { b.disabled = false; }); }
    });
    if (run.status === "running") void pollAnalysis(session, requestId);
  } catch (error) { closeAnalysisLoading(); content.innerHTML = errorState(error.message, "Tải lại phân tích"); content.querySelector("[data-retry]")?.addEventListener("click", () => renderComparison(session, requestId)); }
}
