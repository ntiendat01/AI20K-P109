import { escapeHtml, formatBudget, formatDate } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { takeFlash } from "../../core/session.js";
import { statusPill, errorState } from "../../core/ui-helpers.js";

export async function renderApprovals(session) {
  const content = document.querySelector("#page-content");
  content.innerHTML = `<section class="empty"><div><div class="card-icon">◌</div><h2>Đang tải danh sách chờ phê duyệt…</h2></div></section>`;
  try {
    const requests = await requestApi("/approvals", session);
    const flash = takeFlash();

    const rows = requests.length ? requests.map((r) => `
      <button class="pr-row" data-compare-pr="${r.id}">
        <div class="pr-primary">
          <strong>${escapeHtml(r.code)}</strong>
          <span>${escapeHtml(r.category)}</span>
        </div>
        <div>${statusPill(r.status)}</div>
        <div class="pr-due"><span>Hạn bàn giao</span><b>${formatDate(r.delivery_due_date)}</b></div>
        <div class="pr-budget">${formatBudget(r.estimated_budget)}</div>
        <span class="row-arrow" aria-hidden="true">›</span>
      </button>
    `).join("") : `
      <section class="empty">
        <div>
          <div class="card-icon">✓</div>
          <h2>Không có PR nào đang chờ duyệt</h2>
          <p>Tất cả các đề nghị mua đã được xử lý hoặc chưa được gửi sang hàng đợi phê duyệt.</p>
        </div>
      </section>
    `;

    content.innerHTML = `
      ${flash ? `<div class="flash-message ${flash.tone}"><span>✓</span>${escapeHtml(flash.message)}</div>` : ""}
      <section class="work-summary" aria-label="Tổng quan phê duyệt">
        <div><span>Chế độ duyệt</span><strong>HITL</strong><small>Con người quyết định cuối</small></div>
        <div><span>Đánh giá AI</span><strong>Đa tiêu chí</strong><small>Bằng chứng &amp; Điều kiện</small></div>
        <div><span>Đơn mua hàng</span><strong>PO Nháp</strong><small>Sinh sau khi duyệt</small></div>
      </section>
      <div class="list-heading">
        <div><h2>Hàng đợi xem xét phê duyệt</h2><p>Xem xét bảng so sánh và phân tích đề xuất của AI trước khi ra quyết định.</p></div>
      </div>
      <section class="pr-list">${rows}</section>
    `;
    content.querySelectorAll("[data-compare-pr]").forEach((btn) => btn.addEventListener("click", () => {
      window.location.hash = `#/comparison/${btn.dataset.comparePr}`;
    }));
  } catch (err) {
    content.innerHTML = errorState(err.message);
  }
}
