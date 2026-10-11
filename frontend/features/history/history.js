import { escapeHtml, formatBudget } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { takeFlash } from "../../core/session.js";
import { errorState } from "../../core/ui-helpers.js";

export async function renderHistory(session) {
  const content = document.querySelector("#page-content");
  content.innerHTML = `<section class="empty"><div><div class="card-icon">◌</div><h2>Đang tải lịch sử…</h2></div></section>`;
  try {
    const orders = await requestApi("/pos", session);
    const flash = takeFlash();

    const rows = orders.length ? orders.map((o) => `
      <button class="pr-row" data-go-po="${o.id}">
        <div class="pr-primary">
          <strong>${escapeHtml(o.code)}</strong>
          <span>PR gốc: ${escapeHtml(o.pr_code)} · NCC: ${escapeHtml(o.supplier_name)}</span>
        </div>
        <div><span class="status-pill status-draft">Bản nháp (PO)</span></div>
        <div class="pr-due"><span>Duyệt bởi</span><b>${escapeHtml(o.approver_name)}</b></div>
        <div class="pr-budget">${formatBudget(o.total_amount)}</div>
        <span class="row-arrow" aria-hidden="true">›</span>
      </button>
    `).join("") : `
      <section class="empty">
        <div>
          <div class="card-icon">◷</div>
          <h2>Chưa có Đơn mua hàng (PO) nào</h2>
          <p>Khi Quản lý phê duyệt các PR trong hàng đợi, các đơn mua hàng (PO nháp) sẽ xuất hiện tại đây.</p>
        </div>
      </section>
    `;

    content.innerHTML = `
      ${flash ? `<div class="flash-message ${flash.tone}"><span>✓</span>${escapeHtml(flash.message)}</div>` : ""}
      <div class="list-heading">
        <div><h2>Danh sách Đơn mua hàng đã phê duyệt (PO Nháp)</h2><p>Các PO được sinh tự động sau quyết định của Quản lý, ở trạng thái Nháp (chưa gửi đi bên ngoài).</p></div>
      </div>
      <section class="pr-list">${rows}</section>
    `;
    content.querySelectorAll("[data-go-po]").forEach((btn) => btn.addEventListener("click", () => {
      window.location.hash = `#/po/${btn.dataset.goPo}`;
    }));
  } catch (err) {
    content.innerHTML = errorState(err.message);
  }
}
