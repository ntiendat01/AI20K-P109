import { escapeHtml, formatBudget, formatDate } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { setFlash, takeFlash } from "../../core/session.js";
import { confirmDestructiveAction, statusPill, prProgress, errorState } from "../../core/ui-helpers.js";
import { displayDashboard } from "../../core/router.js";

export function renderNewPr(session) {
  const content = document.querySelector("#page-content");
  const now = new Date();
  const minDate = new Date(now.getTime() + 86400000).toISOString().slice(0, 10);
  const defCode = `PR-${now.toISOString().slice(0, 7).replace('-', '')}-${Math.floor(Math.random() * 1000).toString().padStart(3, '0')}`;
  const defName = `Mua sắm thiết bị tháng ${now.getMonth() + 1}`;
  
  content.innerHTML = `<style>
.quick-opt { font-size:11px; padding:4px 8px; border:1px solid var(--line-strong); border-radius:12px; cursor:pointer; background:#fff; margin-right:4px; color:var(--text); transition:background 0.2s; }
.quick-opt:hover { background:#f5f7fa; }
.field-error { color: var(--red); font-size: 12px; margin-top: 4px; }
</style><section class="creation-layout"><aside class="form-context"><span class="section-kicker">Bước 01 / 03</span><h2>Tạo đề nghị<br />mua sắm.</h2><p>Ghi nhận nhu cầu trước, sau đó mới tập hợp báo giá và gửi phê duyệt.</p><ol class="creation-steps"><li class="active"><span>01</span><div><b>Khai báo nhu cầu</b><small>Thông tin PR và thời hạn</small></div></li><li><span>02</span><div><b>Đối chiếu báo giá</b><small>Tải lên và xác nhận dữ liệu</small></div></li><li><span>03</span><div><b>Gửi phê duyệt</b><small>Chuyển quyết định cho quản lý</small></div></li></ol></aside><section class="form-card"><div class="form-intro"><span class="step-number">01</span><div><h2>Thông tin đề nghị</h2><p>Lưu đề nghị để bắt đầu thu thập báo giá.</p></div></div><form id="pr-form" class="pr-form">
    <fieldset class="metadata-group" style="border:none; padding:0; margin-bottom: 20px;">
      <legend class="sr-only">Thông tin chung</legend>
      <div class="form-grid"><div><label for="pr-code">Mã PR</label><input id="pr-code" name="code" maxlength="50" pattern="[A-Za-z0-9_-]+" value="${defCode}" required /><small>Chỉ dùng chữ, số, dấu gạch nối hoặc gạch dưới.</small><div class="field-error" data-for="code"></div></div><div><label for="category">Danh mục / Tên PR</label><input id="category" name="category" value="${defName}" required /><div class="field-error" data-for="category"></div></div></div>
      <div class="form-grid"><div><label for="budget">Ngân sách dự kiến</label><input id="budget" name="estimated_budget" type="number" min="1" step="0.01" required /><div style="margin-top:6px; margin-bottom:8px"><button type="button" class="quick-opt" onclick="document.getElementById('budget').value=100000000">100 Triệu</button><button type="button" class="quick-opt" onclick="document.getElementById('budget').value=500000000">500 Triệu</button><button type="button" class="quick-opt" onclick="document.getElementById('budget').value=1000000000">1 Tỷ</button></div><div class="field-error" data-for="estimated_budget"></div></div><div><label for="currency">Tiền tệ</label><select id="currency" name="target_currency" style="width:100%; margin-bottom:20px; border: 1px solid var(--line-strong); border-radius: 7px; padding: 13px 14px; background: #fff;" required><option value="VND">VND</option><option value="USD">USD</option></select><div class="field-error" data-for="target_currency"></div></div></div>
      <div class="form-grid"><div><label for="delivery">Hạn giao</label><input id="delivery" name="delivery_due_date" type="date" min="${minDate}" required /><div style="margin-top:6px; margin-bottom:8px"><button type="button" class="quick-opt" onclick="document.getElementById('delivery').value=new Date(Date.now() + 7*86400000).toISOString().slice(0,10)">1 Tuần</button><button type="button" class="quick-opt" onclick="document.getElementById('delivery').value=new Date(Date.now() + 14*86400000).toISOString().slice(0,10)">2 Tuần</button><button type="button" class="quick-opt" onclick="document.getElementById('delivery').value=new Date(Date.now() + 30*86400000).toISOString().slice(0,10)">1 Tháng</button></div><div class="field-error" data-for="delivery_due_date"></div></div></div>
    </fieldset>
    <fieldset class="items-group" style="border:none; padding:0; margin-bottom: 20px;">
      <legend style="font-weight: 800; margin-bottom: 12px; color: var(--navy); display: flex; justify-content: space-between; align-items: center; width: 100%;">
        Danh sách Sản phẩm
        <a href="data:text/csv;base64,77u/VMOqbiBz4bqjbiBwaOG6qW0sU+G7kSBsxrDhu6NuZyzEkMahbiB24buLLEdoaSBjaMO6CkxhcHRvcCwxMCxDw6FpLETDoG5oIGNobyBkZXYKTW9uaXRvciwxMCxDw6FpLDI3IGluY2g=" download="template.csv" style="font-size: 12px; font-weight: normal; color: var(--blue); text-decoration: underline;">Tải template CSV</a>
      </legend>
      <div id="bulk-upload-zone" class="drop-zone">
        <div class="drop-zone-content">
          <span class="drop-zone-icon">📄</span>
          <p class="drop-zone-label">Kéo thả file CSV vào đây hoặc <span style="color:var(--blue);text-decoration:underline;">chọn file</span> để tải lên hàng loạt.</p>
          <p class="drop-zone-hint">Hệ thống sẽ trích xuất danh sách sản phẩm.</p>
        </div>
        <input type="file" id="bulk-upload-file" accept=".csv" style="display:none" />
      </div>
      <div id="bulk-upload-errors" class="error"></div>
      
      <table class="comparison-table" id="items-grid" style="min-width: 100%; margin-top: 16px; margin-bottom: 8px;">
        <thead>
          <tr>
            <th style="text-align:left">Tên sản phẩm</th>
            <th style="text-align:left">Số lượng</th>
            <th style="text-align:left">Đơn vị</th>
            <th style="text-align:left">Ghi chú</th>
            <th style="width:30px"></th>
          </tr>
        </thead>
        <tbody>
        </tbody>
      </table>
      <button type="button" class="secondary" id="add-row-btn" style="font-size:11px; padding:6px 10px;">+ Thêm dòng</button>
    </fieldset>
    <p id="pr-form-error" class="error" role="alert"></p>
    <div class="form-actions">
      <button type="button" class="secondary" data-route="workspace">Hủy</button>
      <button class="secondary" type="button" id="save-draft-btn">Lưu Nháp</button>
      <button class="inline-primary" type="submit" id="create-pr-btn">Tạo PR <span aria-hidden="true">→</span></button>
    </div>
  </form></section></section>`;
  
  content.querySelector("[data-route]").addEventListener("click", () => { window.location.hash = "#/workspace"; });
  content.querySelector("#pr-form").addEventListener("submit", (event) => submitPurchaseRequest(event, session, false));
  content.querySelector("#save-draft-btn").addEventListener("click", (event) => submitPurchaseRequest(event, session, true));
  
  setupItemsGrid(content);
  setupBulkUpload(content, session);
}

function setupItemsGrid(content) {
  const tbody = content.querySelector("#items-grid tbody");
  const addBtn = content.querySelector("#add-row-btn");
  
  const createRow = (item = {}) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="padding:4px"><input type="text" class="item-name" style="margin:0;padding:6px;font-size:12px" value="${escapeHtml(item.name || '')}" required /></td>
      <td style="padding:4px;width:80px"><input type="number" class="item-quantity" style="margin:0;padding:6px;font-size:12px" min="1" value="${item.quantity || 1}" required /></td>
      <td style="padding:4px;width:100px"><input type="text" class="item-uom" style="margin:0;padding:6px;font-size:12px" value="${escapeHtml(item.uom || 'Cái')}" required /></td>
      <td style="padding:4px"><input type="text" class="item-notes" style="margin:0;padding:6px;font-size:12px" value="${escapeHtml(item.notes || '')}" /></td>
      <td style="padding:4px;text-align:center"><button type="button" class="remove-item" style="padding:2px 6px;">×</button></td>
    `;
    tr.querySelector(".remove-item").addEventListener("click", () => {
      tr.remove();
    });
    tr.querySelector(".item-notes").addEventListener("keydown", (e) => {
      if (e.key === "Tab" && !e.shiftKey) {
        if (tr.nextElementSibling === null) {
          e.preventDefault();
          createRow();
          tbody.lastElementChild.querySelector(".item-name").focus();
        }
      }
    });
    tbody.appendChild(tr);
  };
  
  addBtn.addEventListener("click", () => createRow());
  createRow(); // start with one row
  
  content.addGridRows = (items) => {
    items.forEach(createRow);
  };
}

function setupBulkUpload(content, session) {
  const zone = content.querySelector("#bulk-upload-zone");
  const fileInput = content.querySelector("#bulk-upload-file");
  const errContainer = content.querySelector("#bulk-upload-errors");
  
  zone.addEventListener("click", () => fileInput.click());
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleBulkUpload(e.dataTransfer.files[0]);
    }
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      handleBulkUpload(fileInput.files[0]);
    }
  });
  
  const handleBulkUpload = async (file) => {
    errContainer.innerHTML = "";
    const formData = new FormData();
    formData.append("file", file);
    try {
      zone.style.opacity = "0.5";
      const response = await requestApi("/prs/extract-items", session, { method: "POST", body: formData }, true);
      if (response.valid_items && response.valid_items.length > 0) {
        content.querySelector("#items-grid tbody").innerHTML = ""; // clear current
        content.addGridRows(response.valid_items);
      }
      if (response.errors && response.errors.length > 0) {
        errContainer.innerHTML = response.errors.map(err => `<div>Dòng ${err.row}: ${escapeHtml(err.message)}</div>`).join("");
      }
    } catch (e) {
      errContainer.textContent = e.message;
    } finally {
      zone.style.opacity = "1";
      fileInput.value = "";
    }
  };
}

async function submitPurchaseRequest(event, session, isDraft) {
  if (event && event.preventDefault) event.preventDefault();
  const form = document.querySelector("#pr-form");
  if (!form.reportValidity()) return;
  
  const error = form.querySelector("#pr-form-error");
  const button = form.querySelector(isDraft ? "#save-draft-btn" : "#create-pr-btn");
  
  form.querySelectorAll('.field-error').forEach(el => el.textContent = "");
  
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData);
  
  payload.estimated_budget = Number(payload.estimated_budget);
  payload.target_currency = payload.target_currency || "VND";
  
  payload.items = [];
  const rows = form.querySelectorAll('#items-grid tbody tr');
  let orderIndex = 0;
  rows.forEach(row => {
    const name = row.querySelector('.item-name').value;
    if (!name) return;
    payload.items.push({
      order_index: orderIndex++,
      product_name: name,
      quantity: Number(row.querySelector('.item-quantity').value) || 1,
      unit: row.querySelector('.item-uom').value || 'Cái',
      notes: row.querySelector('.item-notes').value || ''
    });
  });
  
  if (!payload.items.length) {
    error.textContent = "Cần ít nhất một sản phẩm.";
    return;
  }
  
  // Calculate requested_quantity as sum
  payload.requested_quantity = payload.items.reduce((sum, item) => sum + item.quantity, 0);
  payload.requested_uom = payload.items[0].unit;
  
  error.textContent = "";
  const prevText = button.textContent;
  button.disabled = true;
  button.textContent = "Đang lưu…";
  try {
    const qs = isDraft ? "?is_draft=true" : "";
    const request = await requestApi("/prs" + qs, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    setFlash(`Đã tạo ${request.code}. Bước tiếp theo: thu thập báo giá.`);
    window.location.hash = `#/pr/${request.id}`;
  } catch (exception) {
    if (exception.validationErrors) {
      exception.validationErrors.forEach(err => {
          const field = err.loc[err.loc.length - 1];
          const errDiv = form.querySelector(`.field-error[data-for="${field}"]`);
          if (errDiv) errDiv.textContent = err.msg;
      });
      error.textContent = "Dữ liệu chưa hợp lệ. Vui lòng kiểm tra lại các trường được đánh dấu đỏ.";
    } else {
      error.textContent = exception.message;
    }
  } finally {
    button.disabled = false;
    button.textContent = prevText;
  }
}

export async function renderPrDetail(session, requestId) {
  const content = document.querySelector("#page-content");
  try {
    const [request, quotations] = await Promise.all([
      requestApi(`/prs/${encodeURIComponent(requestId)}`, session),
      requestApi(`/prs/${encodeURIComponent(requestId)}/quotations`, session),
    ]);
    const flash = takeFlash();
    const canEdit = quotations.length === 0;
    const editControl = canEdit
      ? `<button class="secondary" id="edit-pr" type="button">Chỉnh sửa PR</button>`
      : `<button class="secondary" type="button" disabled aria-describedby="edit-pr-lock">Chỉnh sửa PR</button>`;
    const quotationGuidance = canEdit
      ? "Chưa có báo giá nào. Bạn vẫn có thể chỉnh sửa tên hàng hóa và ngân sách dự kiến."
      : `Đã tải ${quotations.length} báo giá. Xóa hết báo giá để chỉnh sửa thông tin PR.`;
    const approvalControl = request.status === "comparing"
      ? `<button class="inline-primary" id="submit-approval">Phân tích và gửi duyệt <span aria-hidden="true">→</span></button>`
      : `<button class="secondary" disabled>${request.status === "awaiting_quotation" ? "Cần xác nhận báo giá trước" : "Chưa thể gửi duyệt"}</button>`;
    const rejectionNotice = request.rejection_reason
      ? `<section class="return-notice" role="status"><span class="return-notice-mark" aria-hidden="true">!</span><div><p>Quản lý yêu cầu xử lý lại</p><h3>${escapeHtml(request.code)} chưa được phê duyệt</h3><strong>Lý do từ chối</strong><blockquote>${escapeHtml(request.rejection_reason)}</blockquote><small>Rà soát báo giá hoặc đề xuất, sau đó phân tích và gửi lại để Quản lý duyệt.</small></div></section>`
      : "";
    const nextActionTitle = request.rejection_reason
      ? "Rà soát và gửi lại đề nghị"
      : request.quotation_count ? "So sánh lựa chọn NCC và gửi duyệt" : "Tải báo giá đầu tiên";
      
    let itemsHtml = "";
    if (request.items && request.items.length > 0) {
      itemsHtml = `
        <div style="margin:20px 0;">
          <h4 style="margin:0 0 10px;color:var(--navy);">Danh sách Sản phẩm</h4>
          <table class="comparison-table" style="min-width:100%; border:1px solid var(--line);">
            <thead>
              <tr>
                <th style="text-align:left">Tên sản phẩm</th>
                <th style="text-align:left">Số lượng</th>
                <th style="text-align:left">Đơn vị</th>
                <th style="text-align:left">Ghi chú</th>
              </tr>
            </thead>
            <tbody>
              ${request.items.map(item => `
                <tr>
                  <td style="padding:8px 13px; text-align:left">${escapeHtml(item.product_name)}</td>
                  <td style="padding:8px 13px; text-align:left">${item.quantity}</td>
                  <td style="padding:8px 13px; text-align:left">${escapeHtml(item.unit)}</td>
                  <td style="padding:8px 13px; text-align:left">${escapeHtml(item.notes || '')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }
      
    content.innerHTML = `<button class="back-link" data-route="workspace">← Danh sách đề nghị</button>${flash ? `<div class="flash-message ${flash.tone}"><span>✓</span>${escapeHtml(flash.message)}</div>` : ""}<section class="detail-card"><div class="detail-heading"><div><p class="detail-code">${escapeHtml(request.code)}</p><h2>${escapeHtml(request.category)}</h2></div>${statusPill(request.status)}</div>${prProgress(request.status)}${rejectionNotice}<dl class="detail-grid"><div><dt>Người tạo</dt><dd>${escapeHtml(request.creator_name)}</dd></div><div><dt>Số lượng</dt><dd>${(request.requested_quantity || request.quantity || 0).toLocaleString("vi-VN")}</dd></div><div><dt>Ngân sách dự kiến</dt><dd>${formatBudget(request.estimated_budget)}</dd></div><div><dt>Hạn giao</dt><dd>${formatDate(request.delivery_due_date)}</dd></div><div><dt>Ngày tạo</dt><dd>${new Date(request.created_at).toLocaleDateString("vi-VN")}</dd></div></dl>${itemsHtml}<div class="next-action"><div><span>Việc cần làm tiếp theo</span><h3>${nextActionTitle}</h3><p id="edit-pr-lock">${quotationGuidance}</p></div><div style="display:flex;gap:8px;flex-wrap:wrap;">${editControl}${request.quotation_count ? `<button class="inline-primary" data-comparison-route="${request.id}">Bảng so sánh &amp; Đề xuất AI →</button>` : ""}<button class="secondary" data-quotation-route="${request.id}">${request.quotation_count ? "Xem/Tải báo giá" : "Tải báo giá"}</button></div></div><div class="form-actions detail-actions"><button class="danger-button" id="delete-pr" type="button">Xóa đề nghị mua</button>${approvalControl}</div></section>`;
    content.querySelector("[data-route]").addEventListener("click", () => { window.location.hash = "#/workspace"; });
    content.querySelector("[data-quotation-route]").addEventListener("click", () => { window.location.hash = `#/quotations/${request.id}`; });
    content.querySelector("[data-comparison-route]")?.addEventListener("click", () => { window.location.hash = `#/comparison/${request.id}`; });
    content.querySelector("#submit-approval")?.addEventListener("click", () => { window.location.hash = `#/comparison/${request.id}`; });
    content.querySelector("#edit-pr")?.addEventListener("click", () => renderEditPr(session, request));
    content.querySelector("#delete-pr").addEventListener("click", () => deletePurchaseRequest(session, request));
  } catch (error) {
    content.innerHTML = errorState(error.message, "Tải lại đề nghị");
    content.querySelector("[data-retry]")?.addEventListener("click", () => renderPrDetail(session, requestId));
  }
}

function renderEditPr(session, request) {
  const content = document.querySelector("#page-content");
  content.innerHTML = `<section class="creation-layout"><aside class="form-context"><span class="section-kicker">Cập nhật PR</span><h2>Sửa trước khi<br />nhận báo giá.</h2><p>Thông tin đã sửa sẽ được dùng khi bạn bắt đầu tập hợp và đối chiếu báo giá.</p></aside><section class="form-card"><div class="form-intro"><span class="step-number">01</span><div><h2>Chỉnh sửa thông tin PR</h2><p>Kiểm tra lại tên hàng hóa và ngân sách dự kiến trước khi tải báo giá.</p></div></div><form id="edit-pr-form" class="pr-form"><label for="category">Tên hàng hóa / dịch vụ</label><textarea id="category" name="category" rows="4" maxlength="500" required>${escapeHtml(request.category)}</textarea><label for="budget">Ngân sách dự kiến (VND)</label><input id="budget" name="estimated_budget" type="number" min="1" step="0.01" value="${escapeHtml(String(request.estimated_budget))}" required /><p id="edit-pr-error" class="error" role="alert"></p><div class="form-actions"><button type="button" class="secondary" id="cancel-edit-pr">Hủy</button><button class="inline-primary" type="submit">Lưu thay đổi</button></div></form></section></section>`;
  content.querySelector("#cancel-edit-pr").addEventListener("click", () => renderPrDetail(session, request.id));
  content.querySelector("#edit-pr-form").addEventListener("submit", (event) => submitPurchaseRequestUpdate(event, session, request));
}

async function submitPurchaseRequestUpdate(event, session, request) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = form.querySelector("#edit-pr-error");
  const button = form.querySelector("button[type=submit]");
  const formData = Object.fromEntries(new FormData(form));
  
  const payload = {
    category: formData.category || request.category,
    requested_quantity: request.requested_quantity || request.quantity,
    requested_uom: request.requested_uom || "Cái",
    target_currency: request.target_currency || "VND",
    estimated_budget: Number(formData.estimated_budget) || request.estimated_budget,
    delivery_due_date: request.delivery_due_date,
    metadata: request.metadata,
    items: request.items || [],
  };
  
  error.textContent = "";
  button.disabled = true;
  button.textContent = "Đang lưu…";
  try {
    const updated = await requestApi(`/prs/${encodeURIComponent(request.id)}`, session, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    setFlash(`Đã cập nhật ${updated.code}.`);
    await renderPrDetail(session, request.id);
  } catch (exception) {
    error.textContent = exception.message;
  } finally {
    button.disabled = false;
    button.textContent = "Lưu thay đổi";
  }
}

async function deletePurchaseRequest(session, request) {
  const button = document.querySelector("#delete-pr");
  const confirmed = await confirmDestructiveAction({
    title: `Xóa ${request.code}?`,
    description: "Toàn bộ báo giá và file gốc của đề nghị này cũng sẽ bị xóa vĩnh viễn.",
    opener: button,
  });
  if (!confirmed) return;
  button.disabled = true;
  button.textContent = "Đang xóa…";
  try {
    await requestApi(`/prs/${encodeURIComponent(request.id)}`, session, { method: "DELETE" });
    setFlash(`Đã xóa ${request.code} cùng toàn bộ báo giá liên quan.`);
    window.location.hash = "#/workspace";
    displayDashboard(session);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Xóa đề nghị mua";
    const actionArea = button.closest(".detail-actions");
    actionArea.insertAdjacentHTML("beforebegin", `<p class="error action-error" role="alert">${escapeHtml(error.message)}</p>`);
  }
}
