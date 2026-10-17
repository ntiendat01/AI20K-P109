import { useEffect, useMemo, useState } from "react";
import { Printer } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { apiRequest } from "../api";
import { useAuth } from "../AuthProvider";
import { Icon } from "../Icon";
import { takeFlash } from "../session";
import type { JsonObject } from "../types";
import { ErrorState, Flash, LoadingState } from "../ui";
import { formatBudget, formatComparisonMoney, formatDate } from "../utils";

type POSortKey = "code" | "pr_code" | "supplier_name" | "approver_name" | "approved_at" | "total_amount";
type POPageData = { items: JsonObject[]; page: number; page_size: number; total: number };

export function PurchaseOrdersPage() {
  const { session } = useAuth();
  const [pageData, setPageData] = useState<POPageData>({ items: [], page: 1, page_size: 10, total: 0 });
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<POSortKey>("approved_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const flash = useMemo(() => takeFlash(), []);
  const visibleOrders = pageData.items;
  const pageCount = Math.max(1, Math.ceil(pageData.total / pageSize));
  const currentPage = Math.min(pageData.page, pageCount);
  useEffect(() => {
    if (!session) return;
    let active = true;
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({
        page: String(page), page_size: String(pageSize), query: query.trim(),
        sort_by: sortKey, sort_direction: sortDirection,
      });
      setLoading(true);
      setError("");
      void apiRequest<POPageData>(`/pos/page?${params.toString()}`, session).then((result) => {
        if (!active) return;
        setPageData(result);
        setPage(result.page);
        setHasLoaded(true);
      }).catch((exception) => {
        if (active) setError(exception instanceof Error ? exception.message : "Không tải được danh sách PO.");
      }).finally(() => {
        if (active) setLoading(false);
      });
    }, query.trim() ? 250 : 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [session, page, pageSize, query, sortKey, sortDirection, retry]);
  if (loading && !hasLoaded) return <LoadingState label="Đang tải lịch sử PO…" />;
  if (error) return <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />;
  const sortBy = (key: POSortKey) => {
    if (sortKey === key) setSortDirection((current) => current === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDirection(key === "approved_at" || key === "total_amount" ? "desc" : "asc"); }
  };
  const sortLabel = (key: POSortKey) => sortKey === key ? (sortDirection === "asc" ? " ↑" : " ↓") : "";
  return <>{flash && <Flash {...flash} />}
    <section className="po-list-view" aria-label="Danh sách đơn mua hàng">
      <div className="po-list-controls">
        <label className="request-search"><span><Icon name="search" /></span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Tìm mã PO, PR, nhà cung cấp…" aria-label="Tìm kiếm PO" /></label>
      </div>
      <div className="requests-table-wrap po-table-wrap" aria-busy={loading}><table className="requests-table po-table"><thead><tr>
        <th aria-sort={sortKey === "code" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => sortBy("code")}>Mã PO{sortLabel("code")}</button></th>
        <th aria-sort={sortKey === "pr_code" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => sortBy("pr_code")}>PR gốc{sortLabel("pr_code")}</button></th>
        <th aria-sort={sortKey === "supplier_name" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => sortBy("supplier_name")}>Nhà cung cấp{sortLabel("supplier_name")}</button></th>
        <th>Trạng thái</th>
        <th aria-sort={sortKey === "approver_name" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => sortBy("approver_name")}>Người duyệt{sortLabel("approver_name")}</button></th>
        <th aria-sort={sortKey === "approved_at" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => sortBy("approved_at")}>Ngày duyệt{sortLabel("approved_at")}</button></th>
        <th aria-sort={sortKey === "total_amount" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}><button type="button" onClick={() => sortBy("total_amount")}>Tổng giá trị{sortLabel("total_amount")}</button></th>
      </tr></thead><tbody>{visibleOrders.length ? visibleOrders.map((order) => <tr key={String(order.id)}>
        <td><Link className="request-link" to={`/purchase-orders/${order.id}`}><strong>{order.code}</strong></Link></td>
        <td>{order.pr_code || "—"}</td><td>{order.supplier_name || "—"}</td>
        <td><span className="status-pill status-draft">Bản nháp (PO)</span></td><td>{order.approver_name || "—"}</td>
        <td>{formatDate(String(order.approved_at || order.created_at || "").slice(0, 10))}</td>
        <td><strong>{formatBudget(Number(order.total_amount || 0))}</strong></td>
      </tr>) : <tr><td className="request-empty" colSpan={7}><div><div className="card-icon"><Icon name="search" /></div><strong>{query.trim() ? "Không tìm thấy PO phù hợp" : "Chưa có Đơn mua hàng nào"}</strong><p>{query.trim() ? "Thử đổi từ khóa tìm kiếm." : "PO nháp sẽ xuất hiện sau khi Quản lý phê duyệt đề xuất."}</p></div></td></tr>}</tbody></table></div>
      <nav className="pagination" aria-label="Phân trang PO"><p className="request-result-count">Hiển thị <strong>{pageData.total ? (currentPage - 1) * pageSize + 1 : 0}–{Math.min(currentPage * pageSize, pageData.total)}</strong> trên <strong>{pageData.total}</strong> PO</p>
        <label className="po-page-size">Dòng mỗi trang<select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option></select></label>
        <button className="pagination-button" type="button" disabled={currentPage === 1} onClick={() => setPage(1)}>Đầu</button><button className="pagination-button pagination-icon" type="button" aria-label="Trang trước" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><Icon name="arrow-left" /></button>
        <label className="pagination-jump">Trang <input className="pagination-input" type="number" min="1" max={pageCount} value={currentPage} onChange={(event) => setPage(Math.max(1, Math.min(pageCount, Number(event.target.value) || 1)))} /> / {pageCount}</label>
        <button className="pagination-button pagination-icon" type="button" aria-label="Trang sau" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}><Icon name="arrow-right" /></button><button className="pagination-button" type="button" disabled={currentPage === pageCount} onClick={() => setPage(pageCount)}>Cuối</button>
      </nav>
    </section></>;
}

export function PurchaseOrderPage() {
  const { session } = useAuth();
  const { poId = "" } = useParams();
  const [po, setPo] = useState<JsonObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const flash = useMemo(() => takeFlash(), []);
  const load = async () => {
    if (!session) return; setLoading(true); setError("");
    try { setPo(await apiRequest<JsonObject>(`/pos/${encodeURIComponent(poId)}`, session)); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được PO."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [poId, session]);
  if (loading) return <LoadingState label="Đang tải Đơn mua hàng…" />;
  if (error || !po) return <ErrorState message={error || "Không tìm thấy PO."} onRetry={() => void load()} />;
  const back = "/purchase-orders";
  return <div className="po-view-wrapper"><div className="po-page-toolbar"><Link className="secondary po-back-button" to={back}><Icon name="arrow-left" /> Quay lại danh sách</Link><button className="secondary" type="button" onClick={() => window.print()}><Printer aria-hidden="true" /> In / Lưu PDF Đơn mua hàng</button></div>{flash && <Flash {...flash} />}<div className="po-document"><div className="po-watermark">BẢN NHÁP / DRAFT</div><div className="po-doc-header"><div className="po-doc-brand"><h2>CT TNHH DotCom</h2><p>Phòng Mua sắm &amp; Quản lý Tài sản · Đơn mua hàng chính thức</p></div><div className="po-doc-meta"><span className="po-status-badge">BẢN NHÁP (DRAFT)</span><div className="po-number">Số PO: <strong>{po.code}</strong></div><div>Ngày lập: <b>{formatDate(po.created_at.slice(0, 10))}</b></div><div>Tham chiếu PR: <Link to={`/purchase-requests/${po.pr_id}/comparison`}><b>{po.pr_code}</b></Link></div></div></div>
    <div className="po-vendor-grid"><div className="po-box"><h4>ĐƠN VỊ ĐẶT HÀNG (BUYER)</h4><p><strong>TRƯỜNG ĐẠI HỌC VINUNI</strong></p><p>Người duyệt: <b>{po.approver_name}</b></p><p>Thời điểm phê duyệt: {formatDate(po.approved_at.slice(0, 10))}</p></div><div className="po-box"><h4>NHÀ CUNG CẤP ĐƯỢC CHỌN</h4><p><strong className="text-primary">{po.supplier_name}</strong></p><p>Điều khoản thanh toán: {po.payment_terms || "Theo hợp đồng"}</p><p>Thời gian giao hàng: {po.delivery_time || "Theo thỏa thuận"}</p><p>Chính sách bảo hành: {po.warranty || "Theo tiêu chuẩn NSX"}</p></div></div>
    <div className="po-items-section"><table className="po-items-table"><thead><tr><th>STT</th><th>Tên mặt hàng / Quy cách kỹ thuật</th><th>ĐVT</th><th>SL</th><th>Đơn giá</th><th>Thành tiền</th></tr></thead><tbody>{(po.items || []).map((item: JsonObject, index: number) => <tr key={item.id || index}><td className="text-center">{index + 1}</td><td><strong>{item.product_name}</strong>{item.product_code && <><br /><small className="text-muted">{item.product_code}</small></>}</td><td className="text-center">{item.unit || "—"}</td><td className="text-center">{item.quantity}</td><td className="text-right">{formatComparisonMoney(item.unit_price)} VNĐ</td><td className="text-right"><strong>{formatComparisonMoney(item.line_total)} VNĐ</strong></td></tr>)}</tbody><tfoot>{po.subtotal != null && <><tr><td colSpan={5} className="text-right">Tiền hàng:</td><td className="text-right">{formatComparisonMoney(po.subtotal)} VND</td></tr><tr><td colSpan={5} className="text-right">Phí giao hàng:</td><td className="text-right">{formatComparisonMoney(po.shipping_amount)} VND</td></tr><tr><td colSpan={5} className="text-right">VAT bổ sung:</td><td className="text-right">{formatComparisonMoney(po.tax_amount)} VND</td></tr></>}<tr><td colSpan={5} className="text-right"><strong>TỔNG GIÁ TRỊ ĐƠN HÀNG:</strong></td><td className="text-right po-total-amount"><strong>{formatBudget(po.total_amount)}</strong></td></tr></tfoot></table></div>
    {po.manager_note && <div className="po-manager-note-box"><strong>Ghi chú chỉ đạo từ Quản lý phê duyệt:</strong><p>{po.manager_note}</p></div>}<div className="po-warning-callout"><span className="warn-icon">ℹ</span><div><strong>Tuân thủ quy trình bảo mật mua sắm:</strong><p>Đơn mua hàng này hiện ở trạng thái <b>Nháp nội bộ</b>. Hệ thống không tự động gửi đơn đặt hàng ra bên ngoài.</p></div></div><div className="po-signatures-grid"><div className="po-sig-col"><span>Đại diện Mua sắm</span><div className="sig-space" /><b>Người lập đề xuất</b></div><div className="po-sig-col"><span>Quản lý Phê duyệt</span><div className="sig-space"><span className="sig-stamp"><Icon name="check" className="button-icon" /> ĐÃ PHÊ DUYỆT</span></div><b>{po.approver_name}</b></div></div></div>
  </div>;
}
