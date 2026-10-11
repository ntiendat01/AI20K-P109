import { escapeHtml } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { confirmDestructiveAction, statusPill } from "../../core/ui-helpers.js";
import { renderQuotationComparison, bindQuotationComparison, isQuotationReviewComplete } from "./quotation-comparison.js";
import { renderQuotationEditor, pendingQuotationsInReviewOrder, renderReviewComplete, nextUnconfirmedQuotation } from "./quotation-editor.js";

export const AI_OCR_EXTRACTION_MODE = "agent";

export async function renderQuotations(session, requestId, options = {}) {
  const content = document.querySelector("#page-content");
  try {
    const [request, quotations] = await Promise.all([requestApi(`/prs/${encodeURIComponent(requestId)}`, session), requestApi(`/prs/${encodeURIComponent(requestId)}/quotations`, session)]);
    const reviewComplete = isQuotationReviewComplete(quotations);
    const fuzzyMatchResults = reviewComplete
      ? await requestApi(`/prs/${encodeURIComponent(requestId)}/fuzzy-matches`, session)
      : null;
    const confirmedCount = quotations.filter((quotation) => quotation.status === "confirmed").length;
    const reviewSummary = quotations.length
      ? reviewComplete
        ? `Đã đối chiếu và xác nhận ${confirmedCount}/${quotations.length} báo giá. Bảng tổng hợp đã sẵn sàng.`
        : `Đã xác nhận ${confirmedCount}/${quotations.length} báo giá. Hoàn tất đối chiếu để lập bảng tổng hợp.`
      : "Tải lên báo giá để bắt đầu đối chiếu.";
    const quoteRows = quotations.length ? quotations.map((quotation) => `<article class="quote-record"><button class="quote-row" data-quote-id="${quotation.id}"><div><strong>${escapeHtml(quotation.supplier_name)}</strong><span>${escapeHtml(quotation.source_filename)} · ${quotation.items.length} dòng hàng${quotation.cache_hit ? " · dùng cache" : ""}</span></div><span class="quote-state ${quotation.status}">${quotation.status === "confirmed" ? "Đã xác nhận" : "Cần xác nhận"}</span><span class="row-arrow">›</span></button><button class="quote-delete" type="button" data-delete-quote-id="${quotation.id}" aria-label="Xóa báo giá ${escapeHtml(quotation.source_filename)}">Xóa</button></article>`).join("") : `<p class="subtle-empty">Chưa có báo giá nào. Upload file đầu tiên ở biểu mẫu bên dưới.</p>`;
    content.innerHTML = `<button class="back-link" data-route="quotations">← Chọn PR khác</button><section class="quote-header"><div><p class="detail-code">${escapeHtml(request.code)}</p><h2>${escapeHtml(request.category)}</h2><p>${escapeHtml(reviewSummary)}</p></div>${statusPill(request.status)}</section><section class="quote-layout"><div class="quote-upload-panel"><h3>Tải báo giá</h3><p>Kéo thả hoặc chọn file PDF. Tối đa 5 file, mỗi file ≤ 5 MB.</p><div class="drop-zone" id="drop-zone"><div class="drop-zone-content"><div class="drop-zone-icon">⇪</div><p class="drop-zone-label">Kéo thả file vào đây</p><p class="drop-zone-hint">hoặc</p><button class="secondary drop-zone-browse" type="button" id="browse-btn">Chọn file từ máy</button></div><input id="quote-files" type="file" accept=".pdf,application/pdf" multiple hidden /></div><div id="file-queue" class="file-queue"></div><p class="error" id="quote-upload-error" role="alert"></p><button class="inline-primary" type="button" id="upload-all-btn" disabled>Tải lên & trích xuất</button></div><div class="quote-list-panel"><div class="quote-list-heading"><h3>Báo giá đã tải lên</h3>${quotations.length ? `<button class="quote-delete-all" type="button" data-delete-all-quotes>Xóa hết</button>` : ""}</div>${quoteRows}</div></section><section id="quote-editor" aria-live="polite"></section>${reviewComplete ? '<section id="quote-comparison"></section>' : ""}`;
    content.querySelector("[data-route]").addEventListener("click", () => { window.location.hash = "#/quotations"; });
    content.querySelectorAll("[data-quote-id]").forEach((button) => button.addEventListener("click", () => renderQuotationEditor(session, button.dataset.quoteId)));
    content.querySelectorAll("[data-delete-quote-id]").forEach((button) => button.addEventListener("click", async () => {
      const quotation = quotations.find((item) => item.id === button.dataset.deleteQuoteId);
      if (!quotation || !await confirmDestructiveAction({ title: "Xóa báo giá này?", description: `File “${quotation.source_filename}” và dữ liệu trích xuất sẽ bị xóa vĩnh viễn.`, opener: button })) return;
      button.disabled = true;
      try {
        await requestApi(`/quotations/${encodeURIComponent(quotation.id)}`, session, { method: "DELETE" });
        await refreshAfterQuotationDeletion(session, requestId, window.scrollY);
      } catch (error) {
        content.querySelector("#quote-upload-error").textContent = error.message;
        button.disabled = false;
      }
    }));
    content.querySelector("[data-delete-all-quotes]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const confirmed = await confirmDestructiveAction({
        title: "Xóa toàn bộ báo giá?",
        description: `${quotations.length} file đã tải lên cùng dữ liệu trích xuất sẽ bị xóa vĩnh viễn.`,
        confirmLabel: "Xóa hết",
        opener: button,
      });
      if (!confirmed) return;

      const scrollPosition = window.scrollY;
      let deletedCount = 0;
      button.disabled = true;
      button.textContent = "Đang xóa…";
      try {
        for (const quotation of quotations) {
          await requestApi(`/quotations/${encodeURIComponent(quotation.id)}`, session, { method: "DELETE" });
          deletedCount += 1;
        }
        await refreshAfterQuotationDeletion(session, requestId, scrollPosition);
      } catch (error) {
        if (deletedCount) {
          await refreshAfterQuotationDeletion(session, requestId, scrollPosition);
          document.querySelector("#quote-upload-error").textContent = `Đã xóa ${deletedCount}/${quotations.length} báo giá. ${error.message}`;
        } else {
          content.querySelector("#quote-upload-error").textContent = error.message;
          button.disabled = false;
          button.textContent = "Xóa hết";
        }
      }
    });
    if (reviewComplete) {
      const comparison = content.querySelector("#quote-comparison");
      const renderFuzzyComparison = () => {
        comparison.innerHTML = renderQuotationComparison(quotations, fuzzyMatchResults);
        bindQuotationComparison(comparison, {
          session,
          matchResults: fuzzyMatchResults,
          onMatchUpdated: renderFuzzyComparison,
        });
      };
      renderFuzzyComparison();
    }
    const pending = pendingQuotationsInReviewOrder(quotations);
    if (pending.length && !options.preserveScroll) {
      // Extraction is ready for all files at this point.  Open the first
      // unconfirmed quotation so the user can begin the required review
      // without having to select a PDF from the list.
      const target = options.reviewQuoteId ? pending.find((q) => q.id === options.reviewQuoteId)
        : options.confirmedId ? nextUnconfirmedQuotation(quotations, options.confirmedId) : pending[0];
      await renderQuotationEditor(session, (target || pending[0]).id, {
        focus: true,
        message: options.confirmedSupplier
          ? `Đã xác nhận ${options.confirmedSupplier}. Tiếp theo: ${(target || pending[0]).supplier_name}.`
          : `Bắt đầu rà soát ${pending.length} báo giá theo thứ tự tải lên.`,
      });
    } else if (quotations.length > 0 && !options.preserveScroll) {
      renderReviewComplete(session, quotations);
    }

    /* Drop zone logic */
    const dropZone = content.querySelector("#drop-zone");
    const fileInput = content.querySelector("#quote-files");
    const browseBtn = content.querySelector("#browse-btn");
    const fileQueue = content.querySelector("#file-queue");
    const uploadBtn = content.querySelector("#upload-all-btn");
    const uploadError = content.querySelector("#quote-upload-error");
    if (options.uploadError) uploadError.textContent = options.uploadError;
    const uploadCapacity = Math.max(0, 5 - quotations.length);
    let pendingFiles = [];

    function updateQueue() {
      uploadBtn.disabled = pendingFiles.length === 0;
      uploadBtn.textContent = pendingFiles.length ? `Tải lên ${pendingFiles.length} file & trích xuất` : "Tải lên & trích xuất";
      fileQueue.innerHTML = pendingFiles.map((file, index) => {
        const sizeKb = (file.size / 1024).toFixed(1);
        return `<div class="file-queue-item"><div class="file-queue-info"><span class="file-queue-icon">📄</span><div><strong>${escapeHtml(file.name)}</strong><span>${sizeKb} KB</span></div></div><button class="file-queue-remove" type="button" data-remove="${index}" aria-label="Xóa file">×</button></div>`;
      }).join("");
      fileQueue.querySelectorAll("[data-remove]").forEach((button) => button.addEventListener("click", () => {
        pendingFiles.splice(Number(button.dataset.remove), 1);
        updateQueue();
      }));
    }

    function addFiles(files) {
      uploadError.textContent = "";
      const validSuffixes = [".pdf"];
      let rejected = 0;
      let overLimit = 0;
      for (const file of Array.from(files)) {
        const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
        if (!validSuffixes.includes(ext)) { rejected++; continue; }
        if (file.size > 5 * 1024 * 1024) { rejected++; continue; }
        if (pendingFiles.some((f) => f.name === file.name && f.size === file.size)) continue;
        if (pendingFiles.length >= uploadCapacity) { overLimit++; continue; }
        pendingFiles.push(file);
      }
      const notices = [];
      if (rejected) notices.push(`${rejected} file bị bỏ qua (sai định dạng hoặc vượt 5 MB).`);
      if (overLimit) notices.push(`PR chỉ có thể có tối đa 5 báo giá. ${overLimit} file vượt quá đã bị bỏ qua.`);
      uploadError.textContent = notices.join(" ");
      updateQueue();
    }

    browseBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => { if (fileInput.files.length) addFiles(fileInput.files); fileInput.value = ""; });

    dropZone.addEventListener("dragover", (event) => { event.preventDefault(); dropZone.classList.add("drag-over"); });
    dropZone.addEventListener("dragleave", (event) => { event.preventDefault(); dropZone.classList.remove("drag-over"); });
    dropZone.addEventListener("drop", (event) => { event.preventDefault(); dropZone.classList.remove("drag-over"); if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files); });

    uploadBtn.addEventListener("click", () => uploadMultipleQuotations(session, requestId, pendingFiles, fileQueue, uploadBtn, uploadError));
    return { request, quotations };
  } catch (error) { content.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`; }
}

async function refreshAfterQuotationDeletion(session, requestId, scrollPosition) {
  await renderQuotations(session, requestId, { preserveScroll: true });
  window.scrollTo({ top: scrollPosition, behavior: "auto" });
}

export function uploadFilesInParallel(files, upload) {
  return Promise.all(files.map((file, index) => upload(file, index)));
}

async function uploadMultipleQuotations(session, requestId, files, queueEl, uploadBtn, errorEl) {
  errorEl.textContent = "";
  uploadBtn.disabled = true;
  const total = files.length;
  let completed = 0;

  /* Show progress per file */
  const items = queueEl.querySelectorAll(".file-queue-item");
  items.forEach((item) => { item.querySelector(".file-queue-remove").style.display = "none"; });

  const results = await uploadFilesInParallel(files, async (file, index) => {
    const item = items[index];
    if (item) { item.classList.add("uploading"); item.insertAdjacentHTML("beforeend", `<span class="file-queue-status uploading-status">Đang xử lý…</span>`); }
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("extraction_mode", AI_OCR_EXTRACTION_MODE);
      await requestApi(`/prs/${encodeURIComponent(requestId)}/quotations`, session, { method: "POST", body: formData });
      if (item) { item.classList.remove("uploading"); item.classList.add("done"); const statusEl = item.querySelector(".file-queue-status"); if (statusEl) statusEl.textContent = "✓ Hoàn tất"; statusEl?.classList.remove("uploading-status"); statusEl?.classList.add("done-status"); }
      return { file, error: null };
    } catch (exception) {
      if (item) { item.classList.remove("uploading"); item.classList.add("failed"); const statusEl = item.querySelector(".file-queue-status"); if (statusEl) statusEl.textContent = "✗ Lỗi"; statusEl?.classList.remove("uploading-status"); statusEl?.classList.add("failed-status"); }
      return { file, error: exception.message };
    } finally {
      completed += 1;
      uploadBtn.textContent = `Đã xử lý ${completed}/${total} file…`;
    }
  });
  const errors = results.filter((result) => result.error).map((result) => `${result.file.name}: ${result.error}`);

  if (errors.length) errorEl.textContent = `Một số file chưa được trích xuất: ${errors.join(" | ")}`;

  /* The refreshed page automatically opens the first unconfirmed quote. */
  setTimeout(async () => {
    await renderQuotations(session, requestId, errors.length ? { uploadError: errorEl.textContent } : {});
  }, 600);
}
