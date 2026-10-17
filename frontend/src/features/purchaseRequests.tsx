import { useEffect, useMemo, useState, type DragEvent, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiRequest, ApiError } from "../api";
import { useAuth } from "../AuthProvider";
import { Icon } from "../Icon";
import { NumericDateInput } from "../NumericDateInput";
import { BudgetQuickSelect } from "../BudgetQuickSelect";
import { loadDemoItems } from "../demoSamples";
import { setFlash, takeFlash } from "../session";
import type { PurchaseItem, PurchaseRequest, Quotation } from "../types";
import { ConfirmDialog, ErrorState, Flash, LoadingState, ProgressRail, StatusPill } from "../ui";
import { formatBudget, formatDate, PURCHASE_ITEMS_CSV_TEMPLATE_URL } from "../utils";
import { WorkflowStepper } from "./procurementWorkflow";

type EditableItem = PurchaseItem & { localId: string };
const newItem = (item: Partial<PurchaseItem> = {}): EditableItem => ({ localId: crypto.randomUUID(), product_name: item.product_name || "", quantity: Number(item.quantity || 1), unit: item.unit || "Cái", notes: item.notes || "" });

export function NewPurchaseRequestPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const now = useMemo(() => new Date(), []);
  const [code, setCode] = useState(`PR-${now.toISOString().slice(0, 10).replaceAll("-", "")}-${Math.floor(Math.random() * 10000).toString().padStart(4, "0")}`);
  const [category, setCategory] = useState(`Mua sắm thiết bị tháng ${now.getMonth() + 1}`);
  const [budget, setBudget] = useState("");
  const [currency, setCurrency] = useState("VND");
  const [delivery, setDelivery] = useState("");
  const [requester, setRequester] = useState(session?.user.name || "");
  const [purpose, setPurpose] = useState("");
  const [items, setItems] = useState<EditableItem[]>([newItem()]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [bulkErrors, setBulkErrors] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const minDate = new Date(now.getTime() + 86400000).toISOString().slice(0, 10);

  const updateItem = (localId: string, patch: Partial<EditableItem>) => setItems((current) => current.map((item) => item.localId === localId ? { ...item, ...patch } : item));
  const extractCsv = async (file?: File, demo = false) => {
    if (!file || !session) return;
    setUploading(true); setBulkErrors([]);
    const form = new FormData(); form.append("file", file);
    try {
      const result = await apiRequest<{ valid_items: PurchaseItem[]; errors: Array<{ row: number; message: string }> }>("/prs/extract-items", session, { method: "POST", body: form });
      if (result.valid_items?.length) {
        setItems(result.valid_items.map((item) => newItem(item)));
        if (demo && !result.errors?.length) {
          setCategory("Mua vật liệu xây dựng cho công trình mẫu");
          setBudget("16000000");
          setCurrency("VND");
          setDelivery(new Date(now.getTime() + 14 * 86400000).toISOString().slice(0, 10));
          setPurpose("Dữ liệu mẫu để trải nghiệm quy trình mua sắm vật liệu xây dựng.");
          setErrors({});
        }
      }
      setBulkErrors((result.errors || []).map((error) => `Dòng ${error.row}: ${error.message}`));
    } catch (exception) { setBulkErrors([exception instanceof Error ? exception.message : "Không thể đọc file CSV."]); }
    finally { setUploading(false); }
  };
  const createDemo = async () => {
    setUploading(true); setBulkErrors([]);
    try { await extractCsv(await loadDemoItems(), true); }
    catch (exception) { setBulkErrors([exception instanceof Error ? exception.message : "Không tải được dữ liệu mẫu."]); }
    finally { setUploading(false); }
  };

  const submit = async (event: FormEvent, isDraft: boolean) => {
    event.preventDefault();
    if (!session || submitting) return;
    if (!delivery || delivery < minDate) { setErrors({ delivery_due_date: "Ngày nhận hàng không được sớm hơn ngày mai." }); return; }
    const normalized = items.filter((item) => item.product_name.trim()).map((item, index) => ({ order_index: index, product_name: item.product_name.trim(), quantity: Number(item.quantity), unit: item.unit || "Cái", notes: item.notes || "" }));
    if (!normalized.length) { setErrors({ form: "Cần ít nhất một sản phẩm." }); return; }
    setSubmitting(true); setErrors({});
    try {
      const created = await apiRequest<PurchaseRequest>(`/prs${isDraft ? "?is_draft=true" : ""}`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, category, estimated_budget: Number(budget), target_currency: currency, delivery_due_date: delivery, metadata: { requested_by: requester.trim(), purpose: purpose.trim() }, items: normalized, requested_quantity: normalized.reduce((sum, item) => sum + item.quantity, 0), requested_uom: normalized[0].unit }) });
      setFlash(`Đã tạo ${created.code}. Bước tiếp theo: thu thập báo giá.`);
      navigate(`/purchase-requests/${created.id}/workflow/${isDraft ? 1 : 2}`);
    } catch (exception) {
      if (exception instanceof ApiError && exception.validationErrors) {
        const next: Record<string, string> = { form: "Dữ liệu chưa hợp lệ. Vui lòng kiểm tra các trường được đánh dấu." };
        exception.validationErrors.forEach((error) => { next[String(error.loc.at(-1))] = error.msg; }); setErrors(next);
      } else setErrors({ form: exception instanceof Error ? exception.message : "Không thể tạo PR." });
    } finally { setSubmitting(false); }
  };

  const drop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); void extractCsv(event.dataTransfer.files[0]); };
  return <section className="workflow-page create-pr-page">
    <WorkflowStepper step={1} />
    <form className="workflow-section" onSubmit={(event) => void submit(event, false)}>
      <div className="workflow-actions"><button className="secondary" type="button" onClick={() => navigate("/requests")}>← Quay lại</button><div className="workflow-action-right"><button className="secondary" type="button" disabled={submitting} onClick={(event) => { if (event.currentTarget.form?.reportValidity()) void submit(event, true); }}>Lưu nháp</button><button className="inline-primary" type="submit" disabled={submitting}>{submitting ? "Đang lưu…" : "Tạo PR & tiếp tục →"}</button></div></div>
      <article className="workflow-card">
        <div className="workflow-card-heading"><div><p className="text-overline">BƯỚC 1 · KHAI BÁO NHU CẦU</p><h2 className="text-h2">Thông tin PR</h2></div></div>
        <div className="workflow-form-grid">
          <label><span>Mã PR</span><input value={code} onChange={(event) => setCode(event.target.value)} maxLength={50} pattern="[A-Za-z0-9_-]+" required /><small>Chỉ dùng chữ, số, dấu gạch nối hoặc gạch dưới.</small><em className="field-error">{errors.code}</em></label>
          <label><span>Tên PR</span><input value={category} onChange={(event) => setCategory(event.target.value)} required /><em className="field-error">{errors.category}</em></label>
          <label><span>Ngày nhận hàng dự kiến</span><NumericDateInput value={delivery} onChange={(value) => { setDelivery(value); setErrors((current) => ({ ...current, delivery_due_date: "" })); }} min={minDate} required /><em className="field-error">{errors.delivery_due_date}</em></label>
          <label><span>Người yêu cầu</span><input value={requester} onChange={(event) => setRequester(event.target.value)} required /></label>
          <div className="workflow-budget-field"><label htmlFor="pr-budget">Ngân sách dự kiến ({currency})</label><BudgetQuickSelect id="pr-budget" value={budget} onChange={setBudget} /><em className="field-error">{errors.estimated_budget}</em></div>
          <label><span>Tiền tệ</span><select value={currency} onChange={(event) => setCurrency(event.target.value)}><option>VND</option><option>USD</option></select></label>
          <label className="workflow-form-wide"><span>Ghi chú / Mục đích</span><textarea rows={3} maxLength={2000} value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder="Mô tả nhu cầu và mục đích mua sắm" /></label>
        </div>
      </article>
      <article className="workflow-card">
        <div className="workflow-card-heading"><div><p className="text-overline">DANH MỤC MUA SẮM</p><h2 className="text-h2">Danh sách sản phẩm</h2></div><a className="template-link" href={PURCHASE_ITEMS_CSV_TEMPLATE_URL} download="template-vat-lieu-xay-dung.csv">Tải template CSV · Vật liệu xây dựng</a></div>
        <div className="workflow-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={drop}><span className="drop-zone-icon"><Icon name="file-text" /></span><p>Kéo thả file CSV vào đây hoặc <label className="workflow-upload-label">chọn file<input type="file" accept=".csv" hidden onChange={(event) => void extractCsv(event.target.files?.[0])} /></label></p><small>{uploading ? "Đang đọc danh sách sản phẩm…" : "Nhập danh mục từ mẫu CSV hoặc thêm từng dòng bên dưới."}</small><div className="workflow-demo-actions"><button className="secondary" type="button" disabled={uploading || submitting} onClick={() => void createDemo()}>{uploading ? "Đang tạo dữ liệu mẫu…" : "Tạo dữ liệu mẫu"}</button><span>Điền thông tin PR và nhập 3 vật liệu xây dựng từ file CSV mẫu.</span></div></div>
        {bulkErrors.map((error) => <p className="error" key={error}>{error}</p>)}
        <div className="workflow-table-scroll"><table className="workflow-table"><thead><tr><th>STT</th><th>Tên sản phẩm</th><th>Số lượng</th><th>Đơn vị tính</th><th>Ghi chú</th><th>Thao tác</th></tr></thead><tbody>{items.map((item, index) => <tr key={item.localId}><td>{index + 1}</td><td><input aria-label={`Tên sản phẩm ${index + 1}`} value={item.product_name} onChange={(event) => updateItem(item.localId, { product_name: event.target.value })} required /></td><td><input aria-label={`Số lượng ${index + 1}`} type="number" min="1" value={item.quantity} onChange={(event) => updateItem(item.localId, { quantity: Number(event.target.value) })} required /></td><td><input aria-label={`Đơn vị tính ${index + 1}`} value={item.unit} onChange={(event) => updateItem(item.localId, { unit: event.target.value })} required /></td><td><input aria-label={`Ghi chú ${index + 1}`} value={item.notes || ""} onChange={(event) => updateItem(item.localId, { notes: event.target.value })} /></td><td><button type="button" className="workflow-icon-button danger" aria-label={`Xóa sản phẩm ${index + 1}`} disabled={items.length <= 1} onClick={() => setItems((current) => current.filter((row) => row.localId !== item.localId))}><Icon name="close" /></button></td></tr>)}</tbody></table></div><button type="button" className="secondary workflow-add-row" onClick={() => setItems((current) => [...current, newItem()])}>+ Thêm dòng mới</button>
      </article>
      <p className="error" role="alert">{errors.form}</p>
    </form>
  </section>;
}

export function PurchaseRequestDetailPage() {
  const { session } = useAuth();
  const { requestId = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [request, setRequest] = useState<PurchaseRequest | null>(null);
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState(searchParams.get("edit") === "1");
  const [editCategory, setEditCategory] = useState("");
  const [editBudget, setEditBudget] = useState("");
  const flash = useMemo(() => takeFlash(), []);
  const load = async () => {
    if (!session) return;
    setLoading(true); setError("");
    try {
      const [pr, quotes] = await Promise.all([apiRequest<PurchaseRequest>(`/prs/${encodeURIComponent(requestId)}`, session), apiRequest<Quotation[]>(`/prs/${encodeURIComponent(requestId)}/quotations`, session)]);
      setRequest(pr); setQuotations(quotes); setEditCategory(pr.category); setEditBudget(String(pr.estimated_budget));
      if (searchParams.get("edit") === "1" && quotes.length === 0) setEditing(true);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được đề nghị."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [requestId, session]);
  if (loading) return <LoadingState label="Đang tải đề nghị…" />;
  if (error || !request) return <ErrorState message={error || "Không tìm thấy đề nghị."} onRetry={() => void load()} />;
  const canEdit = quotations.length === 0;
  const save = async (event: FormEvent) => {
    event.preventDefault(); if (!session) return; setActionError("");
    try {
      const updated = await apiRequest<PurchaseRequest>(`/prs/${encodeURIComponent(request.id)}`, session, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ category: editCategory, requested_quantity: request.requested_quantity || request.quantity, requested_uom: request.requested_uom || "Cái", target_currency: request.target_currency || "VND", estimated_budget: Number(editBudget), delivery_due_date: request.delivery_due_date, metadata: request.metadata, items: request.items || [] }) });
      setRequest(updated); setEditing(false); setSearchParams({}); setFlash(`Đã cập nhật ${updated.code}.`);
    } catch (exception) { setActionError(exception instanceof Error ? exception.message : "Không thể cập nhật PR."); }
  };
  const remove = async () => {
    if (!session) return; setConfirmDelete(false);
    try { await apiRequest(`/prs/${encodeURIComponent(request.id)}`, session, { method: "DELETE" }); setFlash(`Đã xóa ${request.code} cùng toàn bộ báo giá liên quan.`); navigate("/requests"); }
    catch (exception) { setActionError(exception instanceof Error ? exception.message : "Không thể xóa PR."); }
  };
  if (editing && canEdit) return <section className="creation-layout"><aside className="form-context"><span className="section-kicker">Cập nhật PR</span><h2>Sửa trước khi<br />nhận báo giá.</h2><p>Thông tin đã sửa sẽ được dùng khi bắt đầu tập hợp báo giá.</p></aside><section className="form-card"><div className="form-intro"><span className="step-number">01</span><div><h2>Chỉnh sửa thông tin PR</h2></div></div><form className="pr-form" onSubmit={(event) => void save(event)}><label htmlFor="edit-category">Tên hàng hóa / dịch vụ</label><textarea id="edit-category" rows={4} maxLength={500} value={editCategory} onChange={(event) => setEditCategory(event.target.value)} required /><label htmlFor="edit-budget">Ngân sách dự kiến (VND)</label><input id="edit-budget" type="number" min="1" step="0.01" value={editBudget} onChange={(event) => setEditBudget(event.target.value)} required /><p className="error">{actionError}</p><div className="form-actions"><button type="button" className="secondary" onClick={() => { setEditing(false); setSearchParams({}); }}>Hủy</button><button className="inline-primary" type="submit">Lưu thay đổi</button></div></form></section></section>;
  const guidance = canEdit ? "Chưa có báo giá nào. Bạn vẫn có thể chỉnh sửa thông tin PR." : `Đã tải ${quotations.length} báo giá. Xóa hết báo giá để chỉnh sửa thông tin PR.`;
  return <><Link className="back-link" to="/requests"><Icon name="arrow-left" className="button-icon" /> Danh sách đề nghị</Link>{flash && <Flash {...flash} />}<section className="detail-card"><div className="detail-heading"><div><p className="detail-code">{request.code}</p><h2>{request.category}</h2></div><StatusPill status={request.status} /></div><ProgressRail status={request.status} />{request.rejection_reason && <section className="return-notice"><span className="return-notice-mark">!</span><div><p>Quản lý yêu cầu xử lý lại</p><h3>{request.code} chưa được phê duyệt</h3><strong>Lý do từ chối</strong><blockquote>{request.rejection_reason}</blockquote></div></section>}<dl className="detail-grid"><div><dt>Người tạo</dt><dd>{request.creator_name}</dd></div><div><dt>Số lượng</dt><dd>{(request.requested_quantity || request.quantity || 0).toLocaleString("vi-VN")}</dd></div><div><dt>Ngân sách dự kiến</dt><dd>{formatBudget(request.estimated_budget)}</dd></div><div><dt>Hạn giao</dt><dd>{formatDate(request.delivery_due_date)}</dd></div><div><dt>Ngày tạo</dt><dd>{new Date(request.created_at).toLocaleDateString("vi-VN")}</dd></div></dl>
    {!!request.items?.length && <div className="request-items"><h4>Danh sách Sản phẩm</h4><div className="comparison-scroll"><table className="comparison-table"><thead><tr><th>Tên sản phẩm</th><th>Số lượng</th><th>Đơn vị</th><th>Ghi chú</th></tr></thead><tbody>{request.items.map((item, index) => <tr key={item.id || index}><td>{item.product_name}</td><td>{item.quantity}</td><td>{item.unit}</td><td>{item.notes || ""}</td></tr>)}</tbody></table></div></div>}
    <div className="next-action"><div><span>Việc cần làm tiếp theo</span><h3>{request.quotation_count ? "So sánh lựa chọn NCC và gửi duyệt" : "Tải báo giá đầu tiên"}</h3><p>{guidance}</p></div><div className="inline-actions"><button className="secondary" disabled={!canEdit} onClick={() => setEditing(true)}>Chỉnh sửa PR</button>{!!request.quotation_count && <button className="inline-primary" onClick={() => navigate(`/purchase-requests/${request.id}/comparison`)}>Bảng so sánh &amp; Đề xuất AI <Icon name="arrow-right" className="button-icon" /></button>}<button className="secondary" onClick={() => navigate(`/purchase-requests/${request.id}/quotations`)}>{request.quotation_count ? "Xem/Tải báo giá" : "Tải báo giá"}</button></div></div><p className="error">{actionError}</p><div className="form-actions detail-actions"><button className="danger-button" onClick={() => setConfirmDelete(true)}>Xóa đề nghị mua</button>{request.status === "comparing" ? <button className="inline-primary" onClick={() => navigate(`/purchase-requests/${request.id}/comparison`)}>Phân tích và gửi duyệt <Icon name="arrow-right" className="button-icon" /></button> : <button className="secondary" disabled>Chưa thể gửi duyệt</button>}</div></section>{confirmDelete && <ConfirmDialog title={`Xóa ${request.code}?`} description="Toàn bộ báo giá và file gốc của đề nghị này cũng sẽ bị xóa vĩnh viễn." onCancel={() => setConfirmDelete(false)} onConfirm={() => void remove()} />}</>;
}
