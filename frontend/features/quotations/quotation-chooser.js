import { escapeHtml } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { statusPill } from "../../core/ui-helpers.js";

export async function renderQuotationChooser(session) {
  const content = document.querySelector("#page-content");
  try {
    const requests = await requestApi("/prs", session);
    const rows = requests.length ? requests.map((request) => `<button class="pr-row" data-quote-pr="${request.id}"><div><strong>${escapeHtml(request.code)}</strong><span>${escapeHtml(request.category)}</span></div><div>${statusPill(request.status)}</div><div class="pr-budget">${request.quotation_count} báo giá xác nhận</div><span class="row-arrow">›</span></button>`).join("") : `<section class="empty compact"><div><div class="card-icon">＋</div><h2>Chưa có PR để tải báo giá</h2><p>Hãy tạo một đề nghị mua trước.</p><button class="inline-primary" data-route="new-pr">Tạo đề nghị mua</button></div></section>`;
    content.innerHTML = `<div class="notice"><span>✦</span><div><strong>Xác nhận thủ công là bắt buộc.</strong> Dữ liệu AI trích xuất chỉ được dùng để so sánh sau khi bạn kiểm tra và xác nhận.</div></div><section class="pr-list">${rows}</section>`;
    content.querySelectorAll("[data-quote-pr]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/quotations/${button.dataset.quotePr}`; }));
    content.querySelectorAll("[data-route]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/${button.dataset.route}`; }));
  } catch (error) { content.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`; }
}
