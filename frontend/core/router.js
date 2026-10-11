import { roleConfig } from "../config/constants.js";
import { icon } from "./icons.js";
import { escapeHtml } from "../utils/formatting.js";
import { logout } from "../features/auth/auth.js";
import { renderWorkspace } from "../features/workspace/workspace.js";
import { renderNewPr, renderPrDetail } from "../features/purchase-request/purchase-request.js";
import { renderQuotationChooser } from "../features/quotations/quotation-chooser.js";
import { renderQuotations } from "../features/quotations/quotation-list.js";
import { renderComparison } from "../features/comparison/comparison.js";
import { renderApprovals } from "../features/approvals/approvals.js";
import { renderHistory } from "../features/history/history.js";
import { renderPoDetail } from "../features/purchase-order/purchase-order.js";

function pageMetadata(page) {
  if (page.startsWith("comparison/")) {
    return ["So sánh & Đề xuất Nhà cung cấp", "Bảng so sánh đa chiều, kiểm tra chính sách mua sắm và khuyến nghị từ AI Agent."];
  }
  if (page.startsWith("po/")) {
    return ["Đơn Mua Hàng (PO Nháp)", "Bản nháp đơn mua hàng được sinh sau khi Quản lý phê duyệt (HITL)."];
  }
  const copy = {
    workspace: ["Quản lý đề nghị mua", "Theo dõi các PR và trạng thái xử lý của bạn."],
    "new-pr": ["Tạo đề nghị mua", "Khai báo nhu cầu mua sắm trước khi thu thập báo giá."],
    quotations: ["Báo giá & so sánh", "Xác nhận báo giá trước khi AI so sánh."],
    approvals: ["Đề nghị chờ phê duyệt", "Xem đề xuất AI và ra quyết định cuối cùng."],
    history: ["Lịch sử phê duyệt & Đơn mua hàng", "Theo dõi các PO nháp đã duyệt và quyết định đã thực hiện."],
  };
  return copy[page] || ["Chi tiết đề nghị mua", "Thông tin và tiến độ xử lý PR."];
}

function isPermittedPage(role, page) {
  if (page.startsWith("comparison/") || page.startsWith("po/")) return true;
  return role === "procurement" && (page.startsWith("pr/") || page.startsWith("quotations/"))
    ? true
    : roleConfig[role].nav.some(([key]) => key === page);
}

export function displayDashboard(session) {
  const { user } = session;
  const config = roleConfig[user.role];
  const requested = window.location.hash.replace("#/", "") || config.home;
  const permitted = isPermittedPage(user.role, requested);
  const [title, subtitle] = pageMetadata(requested);
  const nav = config.nav.map(([key, iconName, label]) => `<button class="nav-button ${key === requested ? "active" : ""}" data-route="${key}"><span class="nav-icon" aria-hidden="true">${icon(iconName)}</span><span>${label}</span></button>`).join("");
  const main = permitted ? `<div id="page-content"><section class="empty"><div><div class="card-icon">◌</div><p>Đang tải dữ liệu…</p></div></section></div>` : `
    <section class="empty blocked"><div><div class="card-icon">⌧</div><h2>Khu vực bị giới hạn</h2><p>Tài khoản ${escapeHtml(config.label)} không có quyền truy cập trang này.</p></div></section>`;
  const app = document.querySelector("#app");
  app.innerHTML = `
    <section class="shell">
      <aside class="sidebar"><div class="brand"><span class="brand-mark" aria-hidden="true">${icon("brand")}</span><span>DotCom</span><small>OPS</small></div><div class="sidebar-rule"></div><p class="role-label">Khu vực của ${escapeHtml(config.label)}</p><nav aria-label="Điều hướng chính">${nav}</nav>
        <div class="sidebar-footer"><div class="identity"><div class="avatar">${escapeHtml(user.name[0])}</div><div>${escapeHtml(user.name)}<span>${escapeHtml(user.email)}</span></div></div><button class="logout" id="logout">Đăng xuất <span aria-hidden="true">↗</span></button></div>
      </aside>
      <main class="content"><div class="topline"><div><p class="page-context">${user.role === "procurement" ? "MUA SẮM / VẬN HÀNH" : "PHÊ DUYỆT / QUẢN LÝ"}</p><h1>${permitted ? escapeHtml(title) : "Truy cập không được phép"}</h1><p>${permitted ? escapeHtml(subtitle) : "Tài khoản này chưa được cấp quyền truy cập khu vực trên."}</p></div><span class="role-badge">${escapeHtml(config.label)}</span></div>${main}</main>
    </section>`;
  document.querySelectorAll("[data-route]").forEach((button) => button.addEventListener("click", () => { window.location.hash = `#/${button.dataset.route}`; displayDashboard(session); }));
  document.querySelector("#logout").addEventListener("click", () => logout(session));
  if (permitted) renderPage(session, requested);
}

async function renderPage(session, page) {
  if (page === "workspace") return renderWorkspace(session);
  if (page === "new-pr") return renderNewPr(session);
  if (page === "quotations") return renderQuotationChooser(session);
  if (page.startsWith("quotations/")) return renderQuotations(session, page.slice("quotations/".length));
  if (page.startsWith("pr/")) return renderPrDetail(session, page.slice(3));
  if (page.startsWith("comparison/")) return renderComparison(session, page.slice("comparison/".length));
  if (page.startsWith("po/")) return renderPoDetail(session, page.slice("po/".length));
  if (page === "approvals") return renderApprovals(session);
  if (page === "history") return renderHistory(session);
  const content = document.querySelector("#page-content");
  content.innerHTML = `<section class="empty"><div><div class="card-icon">⌁</div><h2>Tính năng đang được chuẩn bị</h2><p>Khu vực này sẽ được triển khai ở feature tiếp theo.</p></div></section>`;
}
