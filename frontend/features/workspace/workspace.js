import { statusLabels } from "../../config/constants.js";
import { escapeHtml, formatBudget, formatDate } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { confirmDestructiveAction, statusPill, errorState } from "../../core/ui-helpers.js";

export async function renderWorkspace(session, selectedStatus = "") {
  const content = document.querySelector("#page-content");
  try {
    const allRequests = await requestApi("/prs", session);
    const requests = selectedStatus ? allRequests.filter((request) => request.status === selectedStatus) : allRequests;
    const filters = [["", "Tất cả"], ...Object.entries(statusLabels)].map(([value, label]) => `<button class="filter-button ${value === selectedStatus ? "active" : ""}" data-status="${value}">${label}</button>`).join("");
    const rows = requests.length ? requests.map((request) => {
      const canDelete = !["pending_approval", "approved"].includes(request.status);
      const rejectionNotice = request.rejection_reason
        ? `<p class="pr-rejection"><span aria-hidden="true">!</span><b>Cần xử lý lại:</b> ${escapeHtml(request.rejection_reason)}</p>`
        : "";
      return `<article class="pr-record ${request.rejection_reason ? "pr-record-returned" : ""}"><button class="pr-row" data-pr-id="${request.id}"><div class="pr-primary"><strong>${escapeHtml(request.code)}</strong><span>${escapeHtml(request.category)}</span>${rejectionNotice}</div><div>${statusPill(request.status)}</div><div class="pr-due"><span>Hạn giao</span><b>${formatDate(request.delivery_due_date)}</b></div><div class="pr-budget">${formatBudget(request.estimated_budget)}</div><span class="row-arrow" aria-hidden="true">›</span></button>${canDelete ? `<button class="pr-delete" type="button" data-delete-pr-id="${request.id}" aria-label="Xóa đề nghị mua ${escapeHtml(request.code)}">Xóa</button>` : ""}</article>`;
    }).join("") : `
      <section class="empty compact"><div><div class="card-icon">＋</div><h2>Chưa có đề nghị mua</h2><p>Tạo PR đầu tiên để bắt đầu thu thập báo giá.</p><button class="inline-primary" data-route="new-pr">Tạo đề nghị mua</button></div></section>`;
    const awaiting = allRequests.filter((request) => request.status === "awaiting_quotation").length;
    const inProgress = allRequests.filter((request) => ["comparing", "pending_approval"].includes(request.status)).length;
    content.innerHTML = `
      <section class="work-summary" aria-label="Tổng quan đề nghị mua">
        <div><span>Tổng đề nghị</span><strong>${allRequests.length}</strong><small>Trong không gian của bạn</small></div>
        <div><span>Cần bổ sung báo giá</span><strong>${awaiting}</strong><small>Đang chờ bước tiếp theo</small></div>
        <div><span>Đang xử lý</span><strong>${inProgress}</strong><small>So sánh hoặc chờ duyệt</small></div>
        <button class="inline-primary create-pr-button" data-route="new-pr"><span aria-hidden="true">+</span> Tạo đề nghị mua</button>
      </section>
      <div class="list-heading"><div><h2>Danh sách đề nghị</h2><p>Chọn một đề nghị để xem chi tiết và tiếp tục xử lý.</p></div><span>${requests.length} kết quả</span></div>
      <div class="toolbar"><div class="filters" aria-label="Lọc theo trạng thái">${filters}</div></div><p class="error workspace-action-error" id="workspace-action-error" role="alert"></p>
      <section class="pr-list"><div class="pr-table-header"><span>Đề nghị mua</span><span>Trạng thái</span><span>Hạn giao</span><span>Ngân sách dự kiến</span><span></span></div>${rows}</section>`;
    content.querySelectorAll("[data-status]").forEach((button) => button.addEventListener("click", () => renderWorkspace(session, button.dataset.status)));
    content.querySelectorAll("[data-pr-id]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/pr/${button.dataset.prId}`; }));
    content.querySelectorAll("[data-delete-pr-id]").forEach((button) => button.addEventListener("click", async () => {
      const request = allRequests.find((item) => item.id === button.dataset.deletePrId);
      if (!request || !await confirmDestructiveAction({ title: `Xóa ${request.code}?`, description: "Toàn bộ báo giá và file gốc của đề nghị này cũng sẽ bị xóa vĩnh viễn.", opener: button })) return;
      button.disabled = true;
      try {
        await requestApi(`/prs/${encodeURIComponent(request.id)}`, session, { method: "DELETE" });
        await renderWorkspace(session, selectedStatus);
      } catch (error) {
        content.querySelector("#workspace-action-error").textContent = error.message;
        button.disabled = false;
      }
    }));
    content.querySelectorAll("[data-route]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/${button.dataset.route}`; }));
  } catch (error) {
    content.innerHTML = errorState(error.message);
    content.querySelector("[data-retry]")?.addEventListener("click", () => renderWorkspace(session, selectedStatus));
  }
}
