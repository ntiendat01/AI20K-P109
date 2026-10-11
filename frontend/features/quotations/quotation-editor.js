import { escapeHtml, formatReviewMoney, parseReviewMoney } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { openSourceReview } from "./source-review.js";
import { renderQuotations } from "./quotation-list.js";
import { runAnalysisFromReview } from "../comparison/comparison.js";

export function pendingQuotationsInReviewOrder(quotations) {
  return quotations.filter((quotation) => quotation.status === "unconfirmed");
}

export function nextUnconfirmedQuotation(quotations, currentQuotationId) {
  const currentIndex = quotations.findIndex((quotation) => quotation.id === currentQuotationId);
  const following = currentIndex < 0
    ? quotations
    : [...quotations.slice(currentIndex + 1), ...quotations.slice(0, currentIndex)];
  return following.find((quotation) => quotation.status === "unconfirmed") || null;
}

export function focusReviewTarget(editor) {
  const heading = editor.querySelector("[data-review-heading]");
  if (!heading) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.requestAnimationFrame(() => {
    heading.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    heading.focus({ preventScroll: true });
  });
}

export function scrollToComparison() {
  const comparison = document.querySelector("#quote-comparison-title");
  if (!comparison) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  comparison.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  comparison.focus({ preventScroll: true });
}

export function renderReviewComplete(session, quotations) {
  const editor = document.querySelector("#quote-editor");
  if (!editor) return;
  const confirmedCount = quotations.filter((quotation) => quotation.status === "confirmed").length;
  const targetPrId = quotations[0] && quotations[0].pr_id;
  editor.innerHTML = `<section class="editor-card review-complete-card"><div class="review-complete-mark" aria-hidden="true">✓</div><div><p class="section-kicker">Đã hoàn tất rà soát</p><h3 tabindex="-1" data-review-heading>Đã xác nhận ${confirmedCount} báo giá</h3><p>Bảng tổng hợp đã được lập từ dữ liệu xác nhận và hiển thị ngay bên dưới. Khi phân tích, Agent sẽ chạy ngay và đưa bạn đến kết quả sau khi hoàn tất.</p><div class="form-actions"><button class="inline-primary" type="button" data-scroll-comparison>Xem bảng tổng hợp báo giá ↓</button><button class="secondary" type="button" data-go-analysis>Phân tích &amp; đề xuất NCC →</button></div><p id="review-analysis-error" class="error" role="alert"></p></div></section>`;
  editor.querySelector("[data-scroll-comparison]").addEventListener("click", () => {
    scrollToComparison();
  });
  editor.querySelector("[data-go-analysis]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const error = editor.querySelector("#review-analysis-error");
    if (!targetPrId) return;
    error.textContent = "";
    button.disabled = true;
    try {
      await runAnalysisFromReview(session, targetPrId, button);
    } catch (exception) {
      error.textContent = exception.message || "Không thể bắt đầu phân tích. Hãy thử lại.";
      button.disabled = false;
    }
  });
  focusReviewTarget(editor);
}

function quotationItemRow(item = {}) {
  return `<div class="quote-item"><input class="item-code" value="${escapeHtml(item.product_code || "")}" placeholder="Mã hàng" maxlength="100" /><input class="item-name" value="${escapeHtml(item.product_name || "")}" placeholder="Tên hàng / dịch vụ" required maxlength="500" /><input class="item-unit" value="${escapeHtml(item.unit || "")}" placeholder="Đơn vị" maxlength="100" /><input class="item-quantity" value="${escapeHtml(item.quantity || "")}" type="number" min="1" step="1" placeholder="SL" required /><div class="money-field"><input class="item-unit-price" value="${escapeHtml(formatReviewMoney(item.unit_price))}" inputmode="decimal" pattern="[0-9., ]+" placeholder="Đơn giá" required /><span>VND</span></div><div class="money-field"><input class="item-total" value="${escapeHtml(formatReviewMoney(item.line_total))}" inputmode="decimal" pattern="[0-9., ]+" placeholder="Thành tiền" required /><span>VND</span></div><button class="remove-item" type="button" aria-label="Xóa dòng hàng">×</button></div>`;
}

const commercialFieldMessages = {
  vat_rate: "Nhập thuế suất VAT.",
  vat_included: "Chọn đơn giá và phí đã gồm VAT hay chưa.",
  shipping_fee: "Nhập phí giao hàng; nhập 0 nếu được miễn phí.",
  lead_time_days: "Nhập số ngày giao sau xác nhận đơn.",
  warranty_months: "Nhập thời hạn bảo hành; nhập 0 nếu không có bảo hành.",
};

function commercialFieldError(form, name) {
  return form.querySelector(`[data-field-error="${name}"]`);
}

function clearCommercialFieldError(form, name) {
  const field = form.elements[name];
  const error = commercialFieldError(form, name);
  if (!field || !error) return;
  field.removeAttribute("aria-invalid");
  if (field.getAttribute("aria-describedby") === error.id) field.removeAttribute("aria-describedby");
  error.hidden = true;
  error.textContent = "";
  error.closest(".form-field")?.classList.remove("has-error");
}

function showCommercialFieldError(form, name, message) {
  const field = form.elements[name];
  const error = commercialFieldError(form, name);
  if (!field || !error) return;
  field.setAttribute("aria-invalid", "true");
  field.setAttribute("aria-describedby", error.id);
  error.hidden = false;
  error.textContent = message;
  error.closest(".form-field")?.classList.add("has-error");
}

function isCommercialFieldValid(form, name) {
  const field = form.elements[name];
  const missing = field.value.trim() === "";
  const invalid = !missing && !field.validity.valid;
  if (missing || invalid) {
    showCommercialFieldError(form, name, invalid ? "Nhập một giá trị hợp lệ." : commercialFieldMessages[name]);
    return false;
  }
  clearCommercialFieldError(form, name);
  return true;
}

function firstInvalidCommercialField(form) {
  let firstInvalid = null;
  for (const name of Object.keys(commercialFieldMessages)) {
    if (!isCommercialFieldValid(form, name)) firstInvalid ??= form.elements[name];
  }
  return firstInvalid;
}

export async function renderQuotationEditor(session, quotationId, options = {}) {
  const editor = document.querySelector("#quote-editor");
  try {
    const quotation = await requestApi(`/quotations/${encodeURIComponent(quotationId)}`, session);
    const quotations = await requestApi(`/prs/${encodeURIComponent(quotation.pr_id)}/quotations`, session);
    if (quotation.status === "confirmed") {
      editor.innerHTML = `<section class="editor-card"><h3>Đã xác nhận</h3><p class="subtle-empty">Báo giá của ${escapeHtml(quotation.supplier_name)} đã được khóa để dùng ở bước so sánh.</p><div class="form-actions" style="margin-top: 14px;"><button class="inline-primary" type="button" data-go-comparison>Xem bảng so sánh &amp; Đề xuất NCC →</button><button class="secondary" data-open-source-review="${quotation.id}">Mở bản đối chiếu</button><button class="secondary" data-reopen-quote>Sửa dữ liệu và phân tích lại</button></div></section>`;
      editor.querySelector("[data-go-comparison]")?.addEventListener("click", () => {
        window.location.hash = `#/comparison/${encodeURIComponent(quotation.pr_id)}`;
      });
      editor.querySelector("[data-reopen-quote]").addEventListener("click", async (event) => {
        event.currentTarget.disabled = true;
        try { await requestApi(`/quotations/${quotation.id}/reopen`, session, { method: "POST" }); await renderQuotations(session, quotation.pr_id); }
        catch (error) { event.currentTarget.disabled = false; editor.insertAdjacentHTML("beforeend", `<p class="error" role="alert">${escapeHtml(error.message)}</p>`); }
      });
      editor.querySelector("[data-open-source-review]").addEventListener("click", (event) => openSourceReview(session, quotation, event.currentTarget));
      return;
    }
    const pending = pendingQuotationsInReviewOrder(quotations);
    const confirmedCount = quotations.length - pending.length;
    const hasNext = pending.length > 1;
    const items = quotation.items.length ? quotation.items.map(quotationItemRow).join("") : quotationItemRow();
    editor.innerHTML = `<section class="editor-card"><div class="editor-heading"><div><p class="section-kicker">Rà soát tuần tự</p><h3 tabindex="-1" data-review-heading>2. Đối chiếu và xác nhận</h3><p>Kiểm tra dữ liệu với file gốc. Bạn có thể sửa trước khi xác nhận.</p></div><div class="editor-actions"><button class="secondary" data-reextract="${quotation.id}">Trích xuất lại</button><button class="secondary" data-open-source-review="${quotation.id}">Mở file gốc</button></div></div><div class="review-queue" aria-label="Tiến độ rà soát báo giá"><div><span class="review-queue-label">Hàng đợi xác nhận</span><strong>Còn ${pending.length} báo giá cần xác nhận</strong></div><span>Đã xác nhận ${confirmedCount}/${quotations.length}</span></div>${options.message ? `<div class="review-transition" role="status"><span aria-hidden="true">✓</span>${escapeHtml(options.message)}</div>` : ""}${quotation.extraction_warnings.length ? `<div class="warning-box">${quotation.extraction_warnings.map(escapeHtml).join("<br />")}</div>` : ""}<form id="quote-confirm-form"><div class="form-grid"><div><label for="confirmed-supplier">Nhà cung cấp</label><input id="confirmed-supplier" name="supplier_name" value="${escapeHtml(quotation.supplier_name)}" required minlength="2" maxlength="200" /></div><div><label for="confirmed-delivery">Thời gian giao</label><input id="confirmed-delivery" name="delivery_time" value="${escapeHtml(quotation.delivery_time)}" maxlength="500" placeholder="VD: 7 ngày làm việc" /></div></div><label for="confirmed-payment">Điều khoản thanh toán</label><textarea id="confirmed-payment" name="payment_terms" rows="2" maxlength="1000" placeholder="VD: Thanh toán trong 30 ngày">${escapeHtml(quotation.payment_terms)}</textarea><fieldset class="agent-finance-fields"><legend>Số liệu dùng cho phân tích</legend><p>Hoàn tất các mục có dấu <span class="required-mark" aria-hidden="true">*</span> để xác nhận báo giá. Ngày giao tính theo ngày lịch sau xác nhận đơn hàng.</p><div class="form-grid"><div><label for="quote-currency">Tiền tệ</label><input id="quote-currency" name="currency" value="${escapeHtml(quotation.currency || 'VND')}" /></div><div class="form-field" data-confirmation-field="vat_rate"><label for="quote-vat">VAT (%) <span class="required-mark" aria-hidden="true">*</span></label><input id="quote-vat" name="vat_rate" type="number" min="0" max="100" step="0.01" aria-required="true" value="${quotation.vat_rate == null ? '' : Number(quotation.vat_rate) * 100}" /><p id="quote-vat-error" class="field-error" data-field-error="vat_rate" role="alert" hidden></p></div><div class="form-field" data-confirmation-field="vat_included"><label for="quote-tax-mode">Đơn giá và phí đã gồm VAT? <span class="required-mark" aria-hidden="true">*</span></label><select id="quote-tax-mode" name="vat_included" aria-required="true"><option value="">Chưa xác định</option><option value="false" ${quotation.vat_included === false ? 'selected' : ''}>Chưa gồm VAT</option><option value="true" ${quotation.vat_included === true ? 'selected' : ''}>Đã gồm VAT</option></select><p id="quote-tax-mode-error" class="field-error" data-field-error="vat_included" role="alert" hidden></p></div><div class="form-field" data-confirmation-field="shipping_fee"><label for="quote-shipping">Phí giao hàng (cùng cách tính VAT) <span class="required-mark" aria-hidden="true">*</span></label><input id="quote-shipping" name="shipping_fee" type="number" min="0" step="0.01" aria-required="true" value="${quotation.shipping_fee ?? ''}" /><p id="quote-shipping-error" class="field-error" data-field-error="shipping_fee" role="alert" hidden></p></div><div class="form-field" data-confirmation-field="lead_time_days"><label for="quote-lead-days">Giao sau xác nhận đơn (ngày lịch) <span class="required-mark" aria-hidden="true">*</span></label><input id="quote-lead-days" name="lead_time_days" type="number" min="0" step="1" aria-required="true" value="${quotation.lead_time_days ?? ''}" /><p id="quote-lead-days-error" class="field-error" data-field-error="lead_time_days" role="alert" hidden></p></div><div class="form-field" data-confirmation-field="warranty_months"><label for="quote-warranty">Bảo hành (tháng) <span class="required-mark" aria-hidden="true">*</span></label><input id="quote-warranty" name="warranty_months" type="number" min="0" step="1" aria-required="true" value="${quotation.warranty_months ?? ''}" /><p id="quote-warranty-error" class="field-error" data-field-error="warranty_months" role="alert" hidden></p></div></div><p id="confirmed-tax-totals" role="status"></p><p>Xác nhận dưới đây đồng thời xác nhận số liệu và tổng tiền gồm VAT hiển thị ở trên.</p></fieldset><div class="items-heading"><h4>Dòng hàng đã trích xuất</h4><button id="add-quote-item" class="secondary" type="button">+ Thêm dòng</button></div><div class="quote-items-header"><span>Mã hàng</span><span>Tên hàng / dịch vụ</span><span>Đơn vị</span><span>Số lượng</span><span>Đơn giá (VND)</span><span>Thành tiền (VND)</span><span></span></div><div id="quote-items">${items}</div><p id="quote-confirm-error" class="error" role="alert"></p><div class="form-actions"><button class="inline-primary" type="submit">${hasNext ? "Xác nhận & xem báo giá tiếp theo" : "Xác nhận và hoàn tất đối chiếu"}</button></div></form></section>`;
    editor.querySelector("[data-open-source-review]").addEventListener("click", (event) => openSourceReview(session, quotation, event.currentTarget));
    editor.querySelector("[data-reextract]").addEventListener("click", () => reextractQuotation(session, quotation));
    editor.querySelector("#add-quote-item").addEventListener("click", () => { editor.querySelector("#quote-items").insertAdjacentHTML("beforeend", quotationItemRow()); });
    editor.querySelector("#quote-items").addEventListener("click", (event) => { if (event.target.closest(".remove-item")) event.target.closest(".quote-item").remove(); });
    editor.querySelector("#quote-items").addEventListener("focusout", (event) => {
      if (event.target.matches(".item-unit-price, .item-total")) event.target.value = formatReviewMoney(event.target.value);
    });
    const confirmationForm = editor.querySelector("#quote-confirm-form");
    confirmationForm.addEventListener("input", (event) => {
      if (event.target.name in commercialFieldMessages) isCommercialFieldValid(confirmationForm, event.target.name);
      updateTaxTotals();
    });
    confirmationForm.addEventListener("change", (event) => {
      if (event.target.name in commercialFieldMessages) isCommercialFieldValid(confirmationForm, event.target.name);
      updateTaxTotals();
    });
    updateTaxTotals();
    confirmationForm.addEventListener("submit", (event) => confirmQuotation(event, session, quotation));
    if (options.focus) focusReviewTarget(editor);
  } catch (error) { editor.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`; }
}

async function reextractQuotation(session, quotation) {
  const button = document.querySelector(`[data-reextract="${quotation.id}"]`);
  if (button) { button.disabled = true; button.textContent = "Đang trích xuất…"; }
  try {
    await requestApi(`/quotations/${encodeURIComponent(quotation.id)}/re-extract`, session, { method: "POST" });
    await renderQuotations(session, quotation.pr_id, { reviewQuoteId: quotation.id });
  } catch (error) {
    if (button) { button.disabled = false; button.textContent = "Trích xuất lại"; }
    const formError = document.querySelector("#quote-confirm-error");
    if (formError) formError.textContent = error.message;
  }
}

async function confirmQuotation(event, session, quotation) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = form.querySelector("#quote-confirm-error");
  const button = form.querySelector("button[type=submit]");
  const firstInvalid = firstInvalidCommercialField(form);
  if (firstInvalid) {
    error.textContent = "";
    firstInvalid.focus();
    return;
  }
  const formData = new FormData(form);
  const items = [...form.querySelectorAll(".quote-item")].map((row) => ({ product_code: row.querySelector(".item-code").value, product_name: row.querySelector(".item-name").value, unit: row.querySelector(".item-unit").value, quantity: Number(row.querySelector(".item-quantity").value), unit_price: parseReviewMoney(row.querySelector(".item-unit-price").value), line_total: parseReviewMoney(row.querySelector(".item-total").value) }));
  error.textContent = "";
  button.disabled = true;
  button.textContent = "Đang xác nhận…";
  try {
    const confirmed = await requestApi(`/quotations/${encodeURIComponent(quotation.id)}/confirm`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...financialPayload(form), supplier_name: formData.get("supplier_name"), delivery_time: formData.get("delivery_time"), payment_terms: formData.get("payment_terms"), items }) });
    await renderQuotations(session, quotation.pr_id, {
      confirmedId: quotation.id,
      confirmedSupplier: confirmed.supplier_name,
    });
  } catch (exception) {
    error.textContent = exception.message;
    button.disabled = false;
    button.textContent = "Xác nhận dữ liệu báo giá";
  }
}

function financialPayload(form) {
  const value = (name) => form.elements[name].value;
  const number = (name) => value(name) === "" ? null : Number(value(name));
  const taxMode = value("vat_included");
  const rate = number("vat_rate");
  const shipping = number("shipping_fee");
  const factor = taxMode === "true" ? 1 : rate == null ? null : 1 + rate / 100;
  const subtotal = [...form.querySelectorAll(".item-total")].reduce((sum, input) => sum + Number(parseReviewMoney(input.value)), 0);
  const complete = taxMode !== "" && factor != null && shipping != null;
  return { currency: value("currency"), vat_rate: rate == null ? null : rate / 100,
    vat_included: taxMode === "" ? null : taxMode === "true", shipping_fee: shipping,
    lead_time_days: number("lead_time_days"), warranty_months: number("warranty_months"),
    goods_total_including_tax: complete ? Number((subtotal * factor).toFixed(2)) : null,
    shipping_total_including_tax: complete ? Number((shipping * factor).toFixed(2)) : null };
}

function updateTaxTotals() {
  const form = document.querySelector("#quote-confirm-form");
  if (!form) return;
  const fields = financialPayload(form);
  form.querySelector("#confirmed-tax-totals").textContent = fields.goods_total_including_tax == null
    ? "Hoàn tất VAT, cách tính VAT và phí giao hàng để tính tổng chi phí."
    : `Tổng hàng gồm VAT: ${formatReviewMoney(fields.goods_total_including_tax)} VND · Phí gồm VAT: ${formatReviewMoney(fields.shipping_total_including_tax)} VND · Tổng chi phí: ${formatReviewMoney(fields.goods_total_including_tax + fields.shipping_total_including_tax)} VND`;
}
