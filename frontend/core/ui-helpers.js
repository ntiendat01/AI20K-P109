import { statusLabels } from "../config/constants.js";
import { escapeHtml } from "../utils/formatting.js";

export function statusPill(status) {
  return `<span class="status-pill status-${status}">${escapeHtml(statusLabels[status])}</span>`;
}

export function prProgress(status) {
  const states = [
    ["awaiting_quotation", "01", "Thu thập báo giá"],
    ["comparing", "02", "So sánh lựa chọn"],
    ["pending_approval", "03", "Chờ phê duyệt"],
    ["approved", "04", "Hoàn tất"],
  ];
  const active = status === "rejected" ? 2 : Math.max(0, states.findIndex(([key]) => key === status));
  const completed = status === "approved";
  return `<ol class="progress-rail" aria-label="Tiến trình đề nghị mua">${states.map(([key, number, label], index) => {
    const done = index < active || completed;
    const current = index === active && !completed;
    return `<li class="${done ? "done" : ""} ${current ? "current" : ""}"><span>${done ? "✓" : number}</span><b>${label}</b></li>`;
  }).join("")}</ol>`;
}

export function errorState(message, retryLabel = "Thử lại") {
  return `<section class="empty error-state"><div><div class="card-icon">!</div><h2>Không thể hiển thị dữ liệu</h2><p>${escapeHtml(message)}</p><button class="secondary" type="button" data-retry>${retryLabel}</button></div></section>`;
}

export function confirmDestructiveAction({ title, description, confirmLabel = "Xóa", opener = document.activeElement }) {
  return new Promise((resolve) => {
    document.body.insertAdjacentHTML("beforeend", `<div class="confirm-backdrop" data-confirm-backdrop><section class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-description" tabindex="-1"><div class="confirm-dialog-mark" aria-hidden="true">!</div><div><p class="section-kicker">Xác nhận thao tác</p><h2 id="confirm-dialog-title">${escapeHtml(title)}</h2><p id="confirm-dialog-description">${escapeHtml(description)}</p></div><div class="confirm-dialog-actions"><button class="secondary" type="button" data-confirm-cancel>Hủy</button><button class="danger-button" type="button" data-confirm-accept>${escapeHtml(confirmLabel)}</button></div></section></div>`);
    const backdrop = document.querySelector("[data-confirm-backdrop]");
    const cancelButton = backdrop.querySelector("[data-confirm-cancel]");
    const acceptButton = backdrop.querySelector("[data-confirm-accept]");
    document.body.classList.add("confirm-modal-open");

    const close = (accepted) => {
      document.removeEventListener("keydown", handleKeydown);
      document.body.classList.remove("confirm-modal-open");
      backdrop.remove();
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus();
      resolve(accepted);
    };
    const handleKeydown = (event) => {
      if (event.key === "Escape") close(false);
      if (event.key === "Tab") {
        event.preventDefault();
        (document.activeElement === acceptButton ? cancelButton : acceptButton).focus();
      }
    };

    cancelButton.addEventListener("click", () => close(false));
    acceptButton.addEventListener("click", () => close(true));
    backdrop.addEventListener("mousedown", (event) => { if (event.target === backdrop) close(false); });
    document.addEventListener("keydown", handleKeydown);
    cancelButton.focus();
  });
}

export function showSuccessNotice({ title, description, actionLabel = "Đã hiểu", opener = document.activeElement }) {
  return new Promise((resolve) => {
    document.body.insertAdjacentHTML("beforeend", `<div class="success-backdrop" data-success-backdrop><section class="success-dialog" role="dialog" aria-modal="true" aria-labelledby="success-dialog-title" aria-describedby="success-dialog-description" tabindex="-1"><div class="success-dialog-mark" aria-hidden="true">✓</div><div><p class="section-kicker">Đã gửi thành công</p><h2 id="success-dialog-title">${escapeHtml(title)}</h2><p id="success-dialog-description">${escapeHtml(description)}</p></div><div class="success-dialog-actions"><button class="inline-primary" type="button" data-success-close>${escapeHtml(actionLabel)}</button></div></section></div>`);
    const backdrop = document.querySelector("[data-success-backdrop]");
    const closeButton = backdrop.querySelector("[data-success-close]");
    document.body.classList.add("success-modal-open");

    const close = () => {
      document.removeEventListener("keydown", handleKeydown);
      document.body.classList.remove("success-modal-open");
      backdrop.remove();
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus();
      resolve();
    };
    const handleKeydown = (event) => {
      if (event.key === "Escape") close();
      if (event.key === "Tab") {
        event.preventDefault();
        closeButton.focus();
      }
    };

    closeButton.addEventListener("click", close);
    backdrop.addEventListener("mousedown", (event) => { if (event.target === backdrop) close(); });
    document.addEventListener("keydown", handleKeydown);
    window.requestAnimationFrame(() => closeButton.focus());
  });
}
