import { API_ROOT } from "../../config/constants.js";
import { escapeHtml, formatComparisonMoney } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";

function reviewItemSummary(item) {
  const code = (item.product_code || "").trim();
  return `${code ? `${code} · ` : ""}${item.product_name || "Dòng hàng chưa có tên"}`;
}

async function fetchReviewPageImage(session, quotationId, pageNumber) {
  const response = await fetch(`${API_ROOT}/quotations/${encodeURIComponent(quotationId)}/review-preview/pages/${pageNumber}`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Không thể hiển thị trang PDF này.");
  }
  return response.blob();
}

function sourceReviewMarkup(quotation, preview, pageUrls) {
  const matches = new Map(preview.matches.map((match) => [Number(match.item_index), match.region]));
  const rows = quotation.items.map((item, index) => {
    const region = matches.get(index);
    const location = region
      ? `<span class="source-match-status found">Đã định vị · tr. ${region.page}</span>`
      : `<span class="source-match-status missing">Chưa định vị</span>`;
    return `<button class="source-review-row" type="button" data-source-review-row="${index}" aria-pressed="false"><span class="source-row-index">${index + 1}</span><span class="source-row-detail"><strong>${escapeHtml(reviewItemSummary(item))}</strong><small>${escapeHtml(item.unit || "Chưa có đơn vị")} · SL ${escapeHtml(item.quantity)}</small>${location}</span><span class="source-row-money"><small>Đơn giá</small><b>${formatComparisonMoney(item.unit_price)}</b></span><span class="source-row-money"><small>Thành tiền</small><b>${formatComparisonMoney(item.line_total)}</b></span></button>`;
  }).join("");
  const highlights = preview.matches.reduce((output, match) => {
    if (!match.region) return output;
    const region = match.region;
    if (!output[region.page]) output[region.page] = [];
    output[region.page].push({ itemIndex: Number(match.item_index), region });
    return output;
  }, {});
  const pages = preview.pages.map((page, index) => {
    const overlays = (highlights[page.number] || []).map(({ itemIndex, region }) => {
      const left = (Number(region.x) / Number(page.width)) * 100;
      const top = (Number(region.y) / Number(page.height)) * 100;
      const width = (Number(region.width) / Number(page.width)) * 100;
      const height = (Number(region.height) / Number(page.height)) * 100;
      return `<span class="source-row-highlight" data-source-highlight="${itemIndex}" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%"><i aria-hidden="true">${itemIndex + 1}</i><span class="sr-only">Vùng dòng hàng ${itemIndex + 1}</span></span>`;
    }).join("");
    return `<figure class="source-preview-page" data-source-preview-page="${page.number}"><div class="source-page-label">Trang ${page.number}</div><div class="source-page-canvas"><img src="${pageUrls[index]}" alt="Trang ${page.number} của ${escapeHtml(quotation.source_filename)}" />${overlays}</div></figure>`;
  }).join("");

  return `<div class="source-review-layout"><section class="source-review-items" aria-labelledby="source-review-items-title"><div class="source-review-pane-heading"><div><p class="section-kicker">Bảng trích xuất</p><h3 id="source-review-items-title">Dòng hàng đã trích xuất</h3><p>Rê chuột hoặc chọn một dòng để định vị trên bản gốc.</p></div><span class="source-item-count">${quotation.items.length} dòng</span></div><div class="source-review-table" role="list">${rows || `<div class="source-review-empty">Chưa có dòng hàng để đối chiếu.</div>`}</div><p class="source-review-edit-note">Cần chỉnh sửa? Đóng bản đối chiếu để cập nhật các trường trong biểu mẫu.</p></section><section class="source-preview-pane" aria-labelledby="source-preview-title"><div class="source-review-pane-heading source-preview-heading"><div><p class="section-kicker">File gốc</p><h3 id="source-preview-title">${escapeHtml(quotation.source_filename)}</h3><p data-source-match-message>Chọn một dòng hàng để xem vị trí tương ứng.</p></div><span class="source-page-counter" data-source-page-counter>Trang 1/${preview.pages.length}</span></div><div class="source-preview-scroll" data-source-preview-scroll tabindex="0" aria-label="Các trang PDF gốc">${pages}</div></section></div>`;
}

function bindSourceReviewDialog(dialog, quotation, preview, pageUrls, opener) {
  const matchByIndex = new Map(preview.matches.map((match) => [Number(match.item_index), match.region]));
  const scrollArea = dialog.querySelector("[data-source-preview-scroll]");
  const pageCounter = dialog.querySelector("[data-source-page-counter]");
  const message = dialog.querySelector("[data-source-match-message]");
  const closeButton = dialog.querySelector("[data-close-source-review]");
  let isClosed = false;

  const close = () => {
    if (isClosed) return;
    isClosed = true;
    document.removeEventListener("keydown", onKeydown);
    pageUrls.forEach((url) => URL.revokeObjectURL(url));
    dialog.closest(".source-review-backdrop")?.remove();
    document.body.classList.remove("source-review-open");
    opener?.focus();
  };
  const onKeydown = (event) => {
    if (event.key === "Escape") close();
  };
  const activate = (itemIndex, shouldScroll = true) => {
    const region = matchByIndex.get(itemIndex);
    dialog.querySelectorAll("[data-source-review-row]").forEach((row) => {
      const isActive = Number(row.dataset.sourceReviewRow) === itemIndex;
      row.classList.toggle("active", isActive);
      row.setAttribute("aria-pressed", String(isActive));
    });
    dialog.querySelectorAll("[data-source-highlight]").forEach((highlight) => {
      highlight.classList.toggle("active", Number(highlight.dataset.sourceHighlight) === itemIndex);
    });
    if (!region) {
      if (message) message.textContent = "Không tìm thấy vị trí tự động; hãy đối chiếu trực quan trên file gốc.";
      return;
    }
    if (message) message.textContent = `Đang tô sáng dòng ${itemIndex + 1} trên trang ${region.page}.`;
    if (pageCounter) pageCounter.textContent = `Trang ${region.page}/${preview.pages.length}`;
    if (!shouldScroll || !scrollArea) return;
    const page = dialog.querySelector(`[data-source-preview-page="${region.page}"]`);
    const highlight = dialog.querySelector(`[data-source-highlight="${itemIndex}"]`);
    if (page) {
      const desiredTop = page.offsetTop + (highlight?.offsetTop || 0) - scrollArea.clientHeight * 0.35;
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      scrollArea.scrollTo({ top: Math.max(0, desiredTop), behavior: reducedMotion ? "auto" : "smooth" });
    }
  };

  dialog.querySelectorAll("[data-source-review-row]").forEach((row) => {
    const itemIndex = Number(row.dataset.sourceReviewRow);
    row.addEventListener("pointerenter", () => activate(itemIndex));
    row.addEventListener("focus", () => activate(itemIndex));
    row.addEventListener("click", () => activate(itemIndex));
  });
  closeButton?.addEventListener("click", close);
  dialog.closest(".source-review-backdrop")?.addEventListener("mousedown", (event) => {
    if (event.target === event.currentTarget) close();
  });
  document.addEventListener("keydown", onKeydown);
  const initial = preview.matches.find((match) => match.region);
  if (initial) activate(Number(initial.item_index), false);
  else if (quotation.items.length) activate(0, false);
  window.requestAnimationFrame(() => closeButton?.focus());
}

export async function openSourceReview(session, quotation, opener) {
  document.querySelector(".source-review-backdrop")?.remove();
  const launchElement = opener || document.activeElement;
  document.body.classList.add("source-review-open");
  document.body.insertAdjacentHTML("beforeend", `<div class="source-review-backdrop"><section class="source-review-dialog" role="dialog" aria-modal="true" aria-labelledby="source-review-dialog-title" tabindex="-1"><header class="source-review-dialog-header"><div><p class="section-kicker">Đối chiếu báo giá</p><h2 id="source-review-dialog-title">Đang chuẩn bị file gốc</h2><p>${escapeHtml(quotation.source_filename)}</p></div><button class="source-review-close" type="button" data-close-source-review aria-label="Đóng bản đối chiếu">×</button></header><div class="source-review-loading" data-source-review-content><span class="source-review-spinner" aria-hidden="true"></span><div><strong>Đang dựng bản đối chiếu</strong><p>Trang PDF và vị trí các dòng hàng đang được chuẩn bị.</p></div></div></section></div>`);
  const backdrop = document.querySelector(".source-review-backdrop");
  const dialog = backdrop.querySelector(".source-review-dialog");
  const closeLoadingDialog = () => {
    backdrop.remove();
    document.body.classList.remove("source-review-open");
    launchElement?.focus();
  };
  const onLoadingKeydown = (event) => {
    if (event.key === "Escape") {
      document.removeEventListener("keydown", onLoadingKeydown);
      closeLoadingDialog();
    }
  };
  dialog.querySelector("[data-close-source-review]").addEventListener("click", () => {
    document.removeEventListener("keydown", onLoadingKeydown);
    closeLoadingDialog();
  });
  document.addEventListener("keydown", onLoadingKeydown);

  try {
    const preview = await requestApi(`/quotations/${encodeURIComponent(quotation.id)}/review-preview`, session);
    const pageBlobs = await Promise.all(preview.pages.map((page) => fetchReviewPageImage(session, quotation.id, page.number)));
    const pageUrls = pageBlobs.map((blob) => URL.createObjectURL(blob));
    if (!document.body.contains(backdrop)) {
      pageUrls.forEach((url) => URL.revokeObjectURL(url));
      return;
    }
    document.removeEventListener("keydown", onLoadingKeydown);
    dialog.querySelector("#source-review-dialog-title").textContent = "Đối chiếu với file gốc";
    dialog.querySelector("[data-source-review-content]").outerHTML = sourceReviewMarkup(quotation, preview, pageUrls);
    bindSourceReviewDialog(dialog, quotation, preview, pageUrls, launchElement);
  } catch (error) {
    if (!document.body.contains(backdrop)) return;
    document.removeEventListener("keydown", onLoadingKeydown);
    dialog.querySelector("#source-review-dialog-title").textContent = "Không thể mở bản đối chiếu";
    dialog.querySelector("[data-source-review-content]").innerHTML = `<div class="source-review-error"><div class="card-icon">!</div><div><strong>File gốc chưa thể hiển thị</strong><p>${escapeHtml(error.message)}</p><button class="secondary" type="button" data-retry-source-review>Thử lại</button></div></div>`;
    dialog.querySelector("[data-retry-source-review]").addEventListener("click", () => {
      closeLoadingDialog();
      openSourceReview(session, quotation, launchElement);
    });
  }
}
