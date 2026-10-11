import { escapeHtml, formatBudget, formatDate, formatComparisonMoney } from "../../utils/formatting.js";
import { requestApi } from "../../core/api.js";
import { takeFlash } from "../../core/session.js";
import { errorState } from "../../core/ui-helpers.js";

export async function renderPoDetail(session, poId) {
  const content = document.querySelector("#page-content");
  content.innerHTML = `<section class="empty"><div><div class="card-icon">◌</div><h2>Đang tải Đơn mua hàng…</h2></div></section>`;
  try {
    const po = await requestApi(`/pos/${encodeURIComponent(poId)}`, session);
    const flash = takeFlash();

    const itemsRows = po.items.map((it, idx) => `
      <tr>
        <td class="text-center">${idx + 1}</td>
        <td><strong>${escapeHtml(it.product_name)}</strong>${it.product_code ? `<br/><small class="text-muted">${escapeHtml(it.product_code)}</small>` : ""}</td>
        <td class="text-center">${escapeHtml(it.unit || "—")}</td>
        <td class="text-center">${it.quantity}</td>
        <td class="text-right">${formatComparisonMoney(it.unit_price)} VNĐ</td>
        <td class="text-right"><strong>${formatComparisonMoney(it.line_total)} VNĐ</strong></td>
      </tr>
    `).join("");

    content.innerHTML = `
      <div class="po-view-wrapper">
        <button class="back-link" id="po-back-btn">← Quay lại</button>
        ${flash ? `<div class="flash-message ${flash.tone}"><span>✓</span>${escapeHtml(flash.message)}</div>` : ""}
        
        <div class="po-document">
          <div class="po-watermark">BẢN NHÁP / DRAFT</div>
          
          <div class="po-doc-header">
            <div class="po-doc-brand">
              <h2>CT TNHH DotCom</h2>
              <p>Phòng Mua sắm &amp; Quản lý Tài sản · Đơn mua hàng chính thức</p>
            </div>
            <div class="po-doc-meta">
              <span class="po-status-badge">BẢN NHÁP (DRAFT)</span>
              <div class="po-number">Số PO: <strong>${escapeHtml(po.code)}</strong></div>
              <div>Ngày lập: <b>${formatDate(po.created_at.slice(0, 10))}</b></div>
              <div>Tham chiếu PR: <a href="#/comparison/${po.pr_id}"><b>${escapeHtml(po.pr_code)}</b></a></div>
            </div>
          </div>

          <div class="po-vendor-grid">
            <div class="po-box">
              <h4>ĐƠN VỊ ĐẶT HÀNG (BUYER)</h4>
              <p><strong>TRƯỜNG ĐẠI HỌC VINUNI</strong></p>
              <p>Người duyệt: <b>${escapeHtml(po.approver_name)}</b></p>
              <p>Thời điểm phê duyệt: ${formatDate(po.approved_at.slice(0, 10))}</p>
            </div>
            <div class="po-box">
              <h4>NHÀ CUNG CẤP ĐƯỢC CHỌN (SUPPLIER)</h4>
              <p><strong class="text-primary">${escapeHtml(po.supplier_name)}</strong></p>
              <p>Điều khoản thanh toán: ${escapeHtml(po.payment_terms || "Theo hợp đồng")}</p>
              <p>Thời gian giao hàng: ${escapeHtml(po.delivery_time || "Theo thỏa thuận")}</p>
              <p>Chính sách bảo hành: ${escapeHtml(po.warranty || "Theo tiêu chuẩn NSX")}</p>
            </div>
          </div>

          <div class="po-items-section">
            <table class="po-items-table">
              <thead>
                <tr>
                  <th style="width: 50px;" class="text-center">STT</th>
                  <th>Tên mặt hàng / Quy cách kỹ thuật</th>
                  <th style="width: 70px;" class="text-center">ĐVT</th>
                  <th style="width: 70px;" class="text-center">SL</th>
                  <th style="width: 150px;" class="text-right">Đơn giá</th>
                  <th style="width: 170px;" class="text-right">Thành tiền</th>
                </tr>
              </thead>
              <tbody>
                ${itemsRows}
              </tbody>
              <tfoot>
                ${po.subtotal == null ? "" : `<tr><td colspan="5" class="text-right">Tiền hàng ${po.prices_include_tax ? "(đơn giá đã gồm VAT)" : "(trước VAT)"}:</td><td class="text-right">${formatComparisonMoney(po.subtotal)} VND</td></tr><tr><td colspan="5" class="text-right">Phí giao hàng ${po.prices_include_tax ? "(đã gồm VAT)" : "(trước VAT)"}:</td><td class="text-right">${formatComparisonMoney(po.shipping_amount)} VND</td></tr><tr><td colspan="5" class="text-right">VAT bổ sung:</td><td class="text-right">${formatComparisonMoney(po.tax_amount)} VND</td></tr>`}
                <tr>
                  <td colspan="5" class="text-right"><strong>TỔNG GIÁ TRỊ ĐƠN HÀNG:</strong></td>
                  <td class="text-right po-total-amount"><strong>${formatBudget(po.total_amount)}</strong></td>
                </tr>
              </tfoot>
            </table>
          </div>

          ${po.manager_note ? `
            <div class="po-manager-note-box">
              <strong>Ghi chú chỉ đạo từ Quản lý phê duyệt:</strong>
              <p>${escapeHtml(po.manager_note)}</p>
            </div>
          ` : ""}

          <div class="po-warning-callout">
            <span class="warn-icon">ℹ</span>
            <div>
              <strong>Tuân thủ quy trình bảo mật mua sắm:</strong>
              <p>Đơn mua hàng này hiện ở trạng thái <b>Nháp nội bộ (Draft)</b>. Hệ thống tuyệt đối KHÔNG tự động gửi email hay gửi đơn đặt hàng ra bên ngoài nhằm đảm bảo tính toàn vẹn và kiểm soát ngân sách.</p>
            </div>
          </div>

          <div class="po-signatures-grid">
            <div class="po-sig-col">
              <span>Đại diện Mua sắm</span>
              <div class="sig-space"></div>
              <b>Người lập đề xuất</b>
            </div>
            <div class="po-sig-col">
              <span>Quản lý Phê duyệt</span>
              <div class="sig-space"><span class="sig-stamp">✓ ĐÃ PHÊ DUYỆT</span></div>
              <b>${escapeHtml(po.approver_name)}</b>
            </div>
          </div>
        </div>

        <div class="po-actions-bottom">
          <button class="secondary" id="btn-print-po" type="button">🖨 In / Lưu PDF Đơn mua hàng</button>
          <button class="inline-primary" id="btn-po-done" type="button">Hoàn tất</button>
        </div>
      </div>
    `;

    content.querySelector("#po-back-btn")?.addEventListener("click", () => {
      window.location.hash = session.user.role === "manager" ? "#/history" : `#/comparison/${po.pr_id}`;
    });
    content.querySelector("#btn-po-done")?.addEventListener("click", () => {
      window.location.hash = session.user.role === "manager" ? "#/history" : "#/workspace";
    });
    content.querySelector("#btn-print-po")?.addEventListener("click", () => {
      window.print();
    });
  } catch (err) {
    content.innerHTML = errorState(err.message);
  }
}
