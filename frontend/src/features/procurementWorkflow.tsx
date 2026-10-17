import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, Eye, FileText, Plus, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { apiBlob, apiRequest, ApiError } from "../api";
import { useAuth } from "../AuthProvider";
import { ANALYSIS_POLL_INTERVAL_MS } from "../config";
import { DEMO_QUOTATION_FILENAMES, loadDemoItems, loadDemoQuotations } from "../demoSamples";
import { NumericDateInput } from "../NumericDateInput";
import { startQuotationExtraction, useQuotationJobs } from "../quotationExtractionJobs";
import type { JsonObject, PurchaseItem, PurchaseRequest, Quotation, Session } from "../types";
import { ErrorState, LoadingState } from "../ui";
import { formatBudget, formatComparisonMoney, formatDate, PURCHASE_ITEMS_CSV_TEMPLATE_URL } from "../utils";
import { QuotationEditor } from "./quotations";
import { SourceReview } from "./SourceReview";

const labels = ["Tạo PR", "Tải báo giá", "Trích xuất báo giá", "Tổng hợp thông tin", "Kết quả đề xuất"];
const quoteLimit = 5;
const quoteSizeLimit = 5 * 1024 * 1024;

type AnalysisView = JsonObject & { status: string; analysis_id?: string; recommendation_id?: string };
type DraftItem = PurchaseItem & { localId: string };
type Draft = { category: string; estimated_budget: string; delivery_due_date: string; requested_by: string; purpose: string; items: DraftItem[] };
type Impact = { label: string; before: string; after: string; level: 0 | 1 | 2 | 3; scope: string };

function draftOf(pr: PurchaseRequest): Draft {
  return {
    category: pr.category,
    estimated_budget: String(pr.estimated_budget),
    delivery_due_date: pr.delivery_due_date.slice(0, 10),
    requested_by: pr.metadata?.requested_by || pr.creator_name || "",
    purpose: pr.metadata?.purpose || "",
    items: (pr.items || []).map((item, index) => ({ ...item, item_id: item.item_id || item.id || `legacy-${pr.id}-${index}`, localId: item.item_id || item.id || `saved-${index}` })),
  };
}

function impactOf(pr: PurchaseRequest, draft: Draft): Impact[] {
  const changes: Impact[] = [];
  const add = (label: string, before: unknown, after: unknown, level: Impact["level"], scope: string) => {
    if (String(before ?? "") !== String(after ?? "")) changes.push({ label, before: String(before ?? "—"), after: String(after ?? "—"), level, scope });
  };
  add("Tên PR", pr.category, draft.category, 0, "Cập nhật nhãn");
  add("Ngân sách dự kiến", pr.estimated_budget, draft.estimated_budget, 1, "Tính lại B4–B5");
  add("Ngày nhận hàng", pr.delivery_due_date.slice(0, 10), draft.delivery_due_date, 1, "Đánh giá lại B4–B5");
  add("Người yêu cầu", pr.metadata?.requested_by || pr.creator_name, draft.requested_by, 0, "Cập nhật thông tin PR");
  add("Ghi chú / Mục đích", pr.metadata?.purpose, draft.purpose, 0, "Cập nhật thông tin PR");
  const original = draftOf(pr).items;
  for (const item of original) {
    const current = draft.items.find((row) => row.localId === item.localId);
    if (!current) { changes.push({ label: `Xóa sản phẩm: ${item.product_name}`, before: item.product_name, after: "Đã xóa", level: 3, scope: "Đối soát lại B3; hủy B4–B5" }); continue; }
    add(`Tên sản phẩm: ${item.product_name}`, item.product_name, current.product_name, 3, "Đối soát lại B3; hủy B4–B5");
    add(`Số lượng: ${item.product_name}`, item.quantity, current.quantity, 2, "Tính lại B3–B5");
    add(`Đơn vị: ${item.product_name}`, item.unit, current.unit, 2, "Đối soát lại B3–B5");
    add(`Ghi chú: ${item.product_name}`, item.notes, current.notes, 0, "Cập nhật nhãn");
  }
  for (const item of draft.items.filter((row) => !original.some((saved) => saved.localId === row.localId))) {
    changes.push({ label: `Thêm sản phẩm: ${item.product_name || "Chưa đặt tên"}`, before: "—", after: item.product_name || "Chưa đặt tên", level: 3, scope: "Đối soát lại B3; hủy B4–B5" });
  }
  return changes;
}

function updatePayload(pr: PurchaseRequest, draft: Draft) {
  return {
    category: draft.category.trim(),
    requested_quantity: draft.items.reduce((total, item) => total + Number(item.quantity), 0),
    requested_uom: draft.items[0]?.unit || pr.requested_uom || "Cái",
    target_currency: pr.target_currency || "VND",
    estimated_budget: Number(draft.estimated_budget),
    delivery_due_date: draft.delivery_due_date,
    metadata: { ...(pr.metadata || {}), requested_by: draft.requested_by.trim(), purpose: draft.purpose.trim() },
    items: draft.items.map(({ localId: _, ...item }, index) => ({ ...item, order_index: index, product_name: item.product_name.trim(), quantity: Number(item.quantity) })),
  };
}

function workflowPath(prId: string, step: number): string {
  return `/purchase-requests/${encodeURIComponent(prId)}/workflow/${step}`;
}

function resumeStep(pr: PurchaseRequest, quotes: Quotation[], analysis: AnalysisView | null): number {
  if (["pending_approval", "approved", "rejected"].includes(pr.status) || ["awaiting_buyer_review", "pending_manager_approval", "approved", "rejected", "closed"].includes(analysis?.status || "")) return 5;
  if (quotes.some((quote) => quote.status !== "confirmed" || quote.items.some((item) => !matchReviewed(item, pr)))) return 3;
  if (pr.status === "comparing" || (analysis?.status && !["not_started", "stale"].includes(analysis.status))) return 4;
  if (quotes.length >= 2 && quotes.every((quote) => quote.status === "confirmed")) return 4;
  if (quotes.length) return 3;
  return pr.status === "draft" ? 1 : 2;
}

function completedSteps(pr: PurchaseRequest, quotes: Quotation[], analysis: AnalysisView | null): number[] {
  const completed: number[] = [];
  if (pr.status !== "draft") completed.push(1);
  if (quotes.length) completed.push(2);
  if (quotes.length >= 2 && quotes.every((quote) => quote.status === "confirmed" && quote.items.length > 0 && quote.items.every((item) => matchReviewed(item, pr)))) completed.push(3);
  if (["awaiting_buyer_review", "pending_manager_approval", "approved", "rejected", "closed"].includes(analysis?.status || "") || ["pending_approval", "approved", "rejected"].includes(pr.status)) completed.push(4);
  if (analysis?.status === "approved" || pr.status === "approved") completed.push(5);
  return completed;
}

export function WorkflowStepper({ step, status = "", completed = [], processingStep, onStepChange }: { step: number; status?: string; completed?: number[]; processingStep?: number; onStepChange?: (step: number) => void }) {
  return <nav aria-label="Quy trình mua sắm" className="workflow-stepper"><ol>{labels.map((label, index) => {
    const number = index + 1;
    const done = completed.includes(number);
    const rejected = number === 5 && status === "rejected";
    const processing = number === (processingStep ?? (status === "running" ? 4 : 0));
    const content = <><span className="workflow-step-circle">{processing ? number : done ? <Check aria-hidden="true" /> : rejected ? "×" : number}</span><span className="workflow-step-copy"><strong>{number}. {label}</strong><small>{rejected ? "Bị từ chối" : status === "approved" && number === 5 ? "Đã duyệt" : processing ? number === 2 ? "Đang trích xuất…" : "Đang phân tích…" : number === step ? "Đang xem" : done ? "Đã hoàn thành" : "Chưa thực hiện"}</small></span></>;
    return <li key={label} className={`${number === step ? "active" : ""} ${done ? "done" : ""} ${rejected ? "rejected" : ""} ${processing ? "processing" : ""}`}>{onStepChange ? <button type="button" className="workflow-step" aria-current={number === step ? "step" : undefined} aria-label={`Bước ${number}: ${label}`} onClick={() => onStepChange(number)}>{content}</button> : <div className="workflow-step">{content}</div>}</li>;
  })}</ol></nav>;
}

function StepActions({ back, onBack, primary, onPrimary, disabled, working, tone = "default" }: { back?: string; onBack?: () => void; primary: string; onPrimary?: () => void; disabled?: boolean; working?: boolean; tone?: "default" | "info" | "pending" | "approved" | "rejected" }) {
  return <div className="workflow-actions workflow-step-actions"><div>{back && <button className="secondary" type="button" onClick={onBack}><ArrowLeft aria-hidden="true" />{back}</button>}</div><button className={`inline-primary workflow-action-${tone}`} type="button" onClick={onPrimary} disabled={disabled || working}>{working ? "Đang xử lý…" : primary}{!disabled && <ArrowRight aria-hidden="true" />}</button></div>;
}

function ImpactDialog({ changes, detail, confirm, onCancel, onConfirm, disabled, busy }: { changes: Impact[]; detail: string; confirm: string; onCancel: () => void; onConfirm: () => void; disabled?: boolean; busy?: boolean }) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return <div className="workflow-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}><section className="workflow-modal" role="dialog" aria-modal="true" aria-labelledby="impact-title"><div className="workflow-modal-heading"><AlertTriangle aria-hidden="true" /><div><h2 id="impact-title" className="text-h3">Cảnh báo: Thay đổi ảnh hưởng kết quả phân tích</h2><p className="text-body">{detail}</p></div><button className="workflow-modal-close" type="button" aria-label="Đóng cảnh báo" onClick={onCancel}>×</button></div><div className="workflow-table-scroll"><table className="workflow-table"><thead><tr><th>Nội dung thay đổi</th><th>Giá trị cũ</th><th>Giá trị mới</th><th>Phạm vi ảnh hưởng</th></tr></thead><tbody>{changes.map((change, index) => <tr key={`${change.label}-${index}`}><th>{change.label}</th><td>{change.before}</td><td>{change.after}</td><td><span className={`workflow-impact level-${change.level}`}>{change.scope}</span></td></tr>)}</tbody></table></div><p className="workflow-alert info">Dữ liệu gốc không thay đổi sẽ được giữ lại. Sau khi xác nhận, hãy đối soát các bước bị ảnh hưởng.</p>{disabled && <p className="workflow-alert warning" role="status">PR đang khóa chỉnh sửa ở trạng thái hiện tại.</p>}<div className="workflow-modal-actions"><button ref={cancelRef} className="secondary" type="button" onClick={onCancel}>Hủy bỏ</button><button className="inline-primary" type="button" onClick={onConfirm} disabled={disabled || busy}>{busy ? "Đang xử lý…" : confirm}</button></div></section></div>;
}

export function ProcurementWorkflowPage() {
  const { session } = useAuth();
  const { requestId = "", stepNumber } = useParams();
  const navigate = useNavigate();
  const [pr, setPr] = useState<PurchaseRequest | null>(null);
  const [quotes, setQuotes] = useState<Quotation[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadRevision, setLoadRevision] = useState(0);
  const quotationJobs = useQuotationJobs();
  const extractionJob = quotationJobs.find((job) => job.prId === requestId && job.userId === session?.user.id);
  const currentRequestId = useRef(requestId);
  currentRequestId.current = requestId;

  const refresh = useCallback(async () => {
    if (!session) return;
    const [request, quotations] = await Promise.all([
      apiRequest<PurchaseRequest>(`/prs/${encodeURIComponent(requestId)}`, session),
      apiRequest<Quotation[]>(`/prs/${encodeURIComponent(requestId)}/quotations`, session),
    ]);
    if (currentRequestId.current === requestId) { setPr(request); setQuotes(quotations); }
  }, [requestId, session]);
  const refreshAnalysis = useCallback(async () => {
    if (!session) return;
    const result = await apiRequest<AnalysisView>(`/prs/${encodeURIComponent(requestId)}/analysis`, session);
    if (currentRequestId.current === requestId) setAnalysis(result);
    return result;
  }, [requestId, session]);
  const refreshWorkflow = useCallback(async () => { await Promise.all([refresh(), refreshAnalysis()]); }, [refresh, refreshAnalysis]);

  useEffect(() => {
    let active = true;
    if (!session) return;
    setLoading(true); setError(""); setPr(null); setQuotes([]); setAnalysis(null);
    const id = encodeURIComponent(requestId);
    void Promise.all([
      apiRequest<PurchaseRequest>(`/prs/${id}`, session),
      apiRequest<Quotation[]>(`/prs/${id}/quotations`, session),
      apiRequest<AnalysisView>(`/prs/${id}/analysis`, session),
    ]).then(([request, quotations, result]) => {
      if (!active) return;
      setPr(request); setQuotes(quotations); setAnalysis(result);
    }).catch((exception) => { if (active) setError(exception instanceof Error ? exception.message : "Không tải được hồ sơ mua sắm."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [requestId, session, loadRevision]);
  useEffect(() => {
    if (analysis?.status !== "running") return;
    const timer = window.setInterval(() => { void refreshAnalysis().catch(() => undefined); }, ANALYSIS_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [analysis?.status, refreshAnalysis]);
  useEffect(() => {
    const refreshAfterCancel = () => { void refreshWorkflow().catch(() => undefined); };
    window.addEventListener("workflow-analysis-cancelled", refreshAfterCancel);
    return () => window.removeEventListener("workflow-analysis-cancelled", refreshAfterCancel);
  }, [refreshWorkflow]);
  useEffect(() => {
    if (!extractionJob || (extractionJob.completed === 0 && extractionJob.status === "running")) return;
    void refreshWorkflow().catch(() => undefined);
  }, [extractionJob?.completed, extractionJob?.status, refreshWorkflow]);
  useEffect(() => {
    if (!pr || !analysis || pr.id !== requestId) return;
    if (analysis.status !== "running" && !["awaiting_buyer_review", "pending_manager_approval", "approved", "rejected"].includes(analysis.status)) return;
    const job = { prId: pr.id, code: pr.code, analysisId: analysis.analysis_id, status: analysis.status === "running" ? "running" : "completed" };
    sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(job));
    window.dispatchEvent(new CustomEvent("workflow-analysis-status", { detail: job }));
  }, [pr?.id, pr?.code, analysis?.status, analysis?.analysis_id, requestId]);

  if (loading) return <LoadingState label="Đang tải luồng mua sắm…" />;
  if (error) return <ErrorState message={error} onRetry={() => setLoadRevision((current) => current + 1)} />;
  if (pr && pr.id !== requestId) return <LoadingState label="Đang tải hồ sơ mua sắm…" />;
  if (!pr || !session) return null;
  const landing = resumeStep(pr, quotes, analysis);
  const step = stepNumber === undefined ? landing : Number(stepNumber);
  if (stepNumber === undefined || !Number.isInteger(step) || step < 1 || step > 5) return <Navigate to={workflowPath(pr.id, landing)} replace />;
  const go = (target: number) => navigate(workflowPath(pr.id, target));

  return <div className="workflow-page"><WorkflowStepper step={step} completed={completedSteps(pr, quotes, analysis)} processingStep={["running", "stopping"].includes(extractionJob?.status || "") ? 2 : undefined} onStepChange={go} status={analysis?.status === "rejected" || pr.status === "rejected" ? "rejected" : analysis?.status === "approved" || pr.status === "approved" ? "approved" : analysis?.status || "editing"} />
    {analysis?.status === "running" && <div className="workflow-job" role="status"><RefreshCw aria-hidden="true" /><span>AI đang tạo đề xuất cho {pr.code}. Bạn có thể tiếp tục xem bảng tổng hợp; trạng thái sẽ tự cập nhật.</span></div>}
    {["running", "stopping"].includes(extractionJob?.status || "") && <div className="workflow-job" role="status"><RefreshCw aria-hidden="true" /><span>{extractionJob?.status === "stopping" ? "Đang ngừng trích xuất…" : `Đang trích xuất báo giá cho ${pr.code} (${extractionJob?.completed}/${extractionJob?.total}). Bạn có thể chuyển sang trang khác trong lúc chờ.`}</span></div>}
    {step === 1 && <RequestStep key={pr.id} pr={pr} quotes={quotes} session={session} onRefresh={refresh} onNext={() => go(2)} />}
    {step === 2 && <UploadStep pr={pr} quotes={quotes} analysis={analysis} session={session} onRefresh={refreshWorkflow} onBack={() => go(1)} onNext={() => go(3)} />}
    {step === 3 && <ReviewStep pr={pr} quotes={quotes} analysis={analysis} session={session} onRefresh={refreshWorkflow} onBack={() => go(2)} onNext={() => go(4)} />}
    {step === 4 && <ComparisonStep pr={pr} quotes={quotes} analysis={analysis} session={session} onRefreshAnalysis={refreshAnalysis} onBack={() => go(3)} onNext={() => go(5)} />}
    {step === 5 && <ProposalStep pr={pr} quotes={quotes} analysis={analysis} session={session} onRefreshAnalysis={refreshAnalysis} onBack={() => go(4)} onEdit={() => go(1)} />}
  </div>;
}

function RequestStep({ pr, quotes, session, onRefresh, onNext }: { pr: PurchaseRequest; quotes: Quotation[]; session: Session; onRefresh: () => Promise<void>; onNext: () => void }) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(pr));
  const [showImpact, setShowImpact] = useState(false);
  const [serverChanges, setServerChanges] = useState<Impact[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const changes = useMemo(() => impactOf(pr, draft), [pr, draft]);
  const changeItem = (id: string, patch: Partial<DraftItem>) => setDraft((current) => ({ ...current, items: current.items.map((item) => item.localId === id ? { ...item, ...patch } : item) }));
  const importItems = async (file?: File) => {
    if (!file || file.name.toLowerCase().endsWith(".csv") === false) { setError("Mẫu danh mục hiện hỗ trợ CSV."); return; }
    setImporting(true); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const result = await apiRequest<{ valid_items: PurchaseItem[]; errors: Array<{ row: number; message: string }> }>("/prs/extract-items", session, { method: "POST", body });
      if (result.valid_items.length) setDraft((current) => ({ ...current, items: result.valid_items.map((item) => ({ ...item, localId: crypto.randomUUID() })) }));
      if (result.errors.length) setError(result.errors.map((item) => `Dòng ${item.row}: ${item.message}`).join(" · "));
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể đọc file danh mục."); }
    finally { setImporting(false); }
  };
  const createDemo = async () => {
    setImporting(true); setError("");
    try { await importItems(await loadDemoItems()); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được dữ liệu mẫu."); }
    finally { setImporting(false); }
  };
  const save = async () => {
    setBusy(true); setError("");
    try {
      const updated = await apiRequest<PurchaseRequest>(`/prs/${encodeURIComponent(pr.id)}?expected_version=${pr.version || 1}`, session, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updatePayload(pr, draft)) });
      setDraft(draftOf(updated)); setShowImpact(false); await onRefresh(); onNext();
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể lưu PR."); }
    finally { setBusy(false); }
  };
  const locked = ["pending_approval", "approved", "cancelled"].includes(pr.status);
  const prepareImpact = async () => {
    setError(""); setBusy(true);
    try {
      const payload = updatePayload(pr, draft);
      const impact = await apiRequest<{ changes: Array<{ label: string; before: string; after: string; level: number; scope: string }> }>(`/prs/${encodeURIComponent(pr.id)}/change-impact`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const mapped = impact.changes.map((change) => ({ ...change, level: Math.max(0, Math.min(3, Number(change.level))) as Impact["level"] }));
      if (!mapped.some((change) => change.level > 0)) { await save(); return; }
      setServerChanges(mapped); setShowImpact(true);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể đánh giá ảnh hưởng thay đổi."); }
    finally { setBusy(false); }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!changes.length) { onNext(); return; }
    if (locked) { setShowImpact(true); return; }
    void prepareImpact();
  };
  return <section className="workflow-section"><form onSubmit={submit}><div className="workflow-actions"><span className="workflow-chip">PR đã được tạo</span><div className="workflow-action-right"><button className="secondary workflow-disabled-draft" type="button" disabled title="PR đã được tạo">⊘ Lưu nháp</button><button className={`inline-primary ${changes.length ? "workflow-save-button" : ""}`} type="submit" disabled={busy || locked}>{busy ? "Đang xử lý…" : changes.length ? "Lưu thay đổi" : "Tiếp tục →"}</button></div></div>
    <article className="workflow-card"><div className="workflow-card-heading"><div><p className="text-overline">BƯỚC 1 · ĐANG CHỈNH SỬA</p><h2 className="text-h2">Thông tin PR</h2></div></div><div className="workflow-form-grid">
      <label><span>Mã PR</span><input value={pr.code} readOnly /></label>
      <label><span>Tên PR</span><input value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })} minLength={3} required /></label>
      <label><span>Ngày nhận hàng dự kiến</span><NumericDateInput value={draft.delivery_due_date} onChange={(value) => { setDraft({ ...draft, delivery_due_date: value }); setError(""); }} required /></label>
      <label><span>Người yêu cầu</span><input value={draft.requested_by} onChange={(event) => setDraft({ ...draft, requested_by: event.target.value })} required /></label>
      <label><span>Ngân sách dự kiến (VND)</span><input type="number" min="1" step="0.01" value={draft.estimated_budget} onChange={(event) => setDraft({ ...draft, estimated_budget: event.target.value })} required /></label>
      <label className="workflow-form-wide"><span>Ghi chú / Mục đích</span><textarea rows={3} maxLength={2000} value={draft.purpose} onChange={(event) => setDraft({ ...draft, purpose: event.target.value })} /></label>
    </div></article>
    <article className="workflow-card"><div className="workflow-card-heading"><div><p className="text-overline">DANH MỤC MUA SẮM</p><h2 className="text-h2">Danh sách sản phẩm</h2></div><a className="template-link" href={PURCHASE_ITEMS_CSV_TEMPLATE_URL} download="template-vat-lieu-xay-dung.csv">Tải template CSV · Vật liệu xây dựng</a></div>
      <div className="workflow-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); void importItems(event.dataTransfer.files[0]); }}><UploadCloud aria-hidden="true" /><p>Kéo thả file CSV vào đây hoặc <label className="workflow-upload-label">chọn file<input type="file" accept=".csv" hidden onChange={(event) => void importItems(event.target.files?.[0])} /></label></p><small>{importing ? "Đang đọc danh mục…" : "Nhập danh mục từ mẫu CSV hoặc sửa trực tiếp bên dưới."}</small><div className="workflow-demo-actions"><button className="secondary" type="button" disabled={locked || importing || busy} onClick={() => void createDemo()}>{importing ? "Đang tạo dữ liệu mẫu…" : "Tạo dữ liệu mẫu"}</button><span>Nhập 3 vật liệu xây dựng từ file CSV mẫu. Lưu thay đổi để áp dụng vào PR.</span></div></div>
      <div className="workflow-table-scroll"><table className="workflow-table"><thead><tr><th>STT</th><th>Tên sản phẩm</th><th>Số lượng</th><th>Đơn vị tính</th><th>Ghi chú</th><th>Thao tác</th></tr></thead><tbody>{draft.items.map((item, index) => <tr key={item.localId}><td>{index + 1}</td><td><input aria-label={`Tên sản phẩm ${index + 1}`} value={item.product_name} onChange={(event) => changeItem(item.localId, { product_name: event.target.value })} required /></td><td><input aria-label={`Số lượng ${index + 1}`} type="number" min="1" value={item.quantity} onChange={(event) => changeItem(item.localId, { quantity: Number(event.target.value) })} required /></td><td><input aria-label={`Đơn vị ${index + 1}`} value={item.unit} onChange={(event) => changeItem(item.localId, { unit: event.target.value })} required /></td><td><input aria-label={`Ghi chú ${index + 1}`} value={item.notes || ""} onChange={(event) => changeItem(item.localId, { notes: event.target.value })} /></td><td><button className="workflow-icon-button danger" type="button" title="Xóa sản phẩm" aria-label={`Xóa sản phẩm ${index + 1}`} disabled={draft.items.length <= 1} onClick={() => setDraft((current) => ({ ...current, items: current.items.filter((row) => row.localId !== item.localId) }))}><Trash2 aria-hidden="true" /></button></td></tr>)}</tbody></table></div>
      <button className="secondary workflow-add-row" type="button" onClick={() => { const id = crypto.randomUUID(); setDraft((current) => ({ ...current, items: [...current.items, { localId: id, item_id: id, product_name: "", quantity: 1, unit: "Cái", notes: "" }] })); }}><Plus aria-hidden="true" /> Thêm dòng mới</button>
    </article>
    {!!changes.length && <p className="workflow-alert info" role="status">Có {changes.length} thay đổi chưa lưu. Các thay đổi ảnh hưởng kết quả sẽ được giải thích trước khi cập nhật.</p>}{locked && <p className="workflow-alert warning">PR đang chờ duyệt hoặc đã hoàn tất; không thể lưu chỉnh sửa.</p>}<p className="error" role="alert">{error}</p></form>
    {showImpact && <ImpactDialog changes={serverChanges || changes} detail="Chỉnh sửa này có thể yêu cầu đối soát lại báo giá hoặc tính lại ma trận so sánh và phương án đề xuất." confirm="Xác nhận & phân tích lại" disabled={locked} busy={busy} onCancel={() => setShowImpact(false)} onConfirm={() => void save()} />}
  </section>;
}

function UploadStep({ pr, quotes, analysis, session, onRefresh, onBack, onNext }: { pr: PurchaseRequest; quotes: Quotation[]; analysis: AnalysisView | null; session: Session; onRefresh: () => Promise<void>; onBack: () => void; onNext: () => void }) {
  const extractionJob = useQuotationJobs().find((job) => job.prId === pr.id && job.userId === session.user.id);
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<Quotation | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Quotation | null>(null);
  const [impactOpen, setImpactOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const locked = ["pending_approval", "approved", "cancelled"].includes(pr.status);
  const extracting = extractionJob?.status === "running" || extractionJob?.status === "stopping";
  const primaryAction = files.length
    ? analysis && analysis.status !== "not_started" ? "Trích xuất lại" : "Tiến hành trích xuất"
    : quotes.length && !extracting ? "Tiếp theo" : "Tiến hành trích xuất";
  const addFiles = (incoming: FileList | File[]) => {
    if (locked || extracting) return;
    const accepted = Array.from(incoming).filter((file) => file.name.toLowerCase().endsWith(".pdf") && file.size <= quoteSizeLimit);
    const capacity = Math.max(0, quoteLimit - quotes.length - files.length);
    setFiles((current) => [...current, ...accepted.slice(0, capacity)]);
    if (accepted.length !== Array.from(incoming).length || accepted.length > capacity) setError("Chỉ nhận tối đa 5 file PDF, mỗi file không quá 5 MB.");
    else setError("");
  };
  const upload = () => {
    if (!startQuotationExtraction(pr.id, pr.code, files, session)) return;
    setFiles([]); setError(""); setImpactOpen(false);
  };
  const createDemo = async () => {
    if (locked || extracting || busy || files.length) return;
    setBusy(true); setError("");
    try {
      const existing = new Set(quotes.map((quote) => quote.source_filename));
      const missing = DEMO_QUOTATION_FILENAMES.filter((filename) => !existing.has(filename));
      if (!missing.length) { setError("Hai báo giá mẫu đã được tải lên PR này."); return; }
      if (missing.length > quoteLimit - quotes.length) { setError("Không đủ chỗ cho báo giá mẫu. PR chỉ nhận tối đa 5 báo giá."); return; }
      const sampleFiles = (await loadDemoQuotations()).filter((file) => missing.some((filename) => filename === file.name));
      setFiles(sampleFiles);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được báo giá mẫu."); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!deleteTarget) return;
    setBusy(true); setError("");
    try { await apiRequest(`/quotations/${encodeURIComponent(deleteTarget.id)}`, session, { method: "DELETE" }); setDeleteTarget(null); setImpactOpen(false); await onRefresh(); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể xóa báo giá."); }
    finally { setBusy(false); }
  };
  const action = () => { if (!files.length) { onNext(); return; } if (analysis && analysis.status !== "not_started") setImpactOpen(true); else upload(); };
  const impactChanges: Impact[] = deleteTarget ? [{ label: "Xóa file báo giá", before: deleteTarget.source_filename, after: "Đã xóa", level: 2, scope: "Tính lại B3–B5" }] : files.map((file) => ({ label: "Thêm file báo giá", before: "—", after: file.name, level: 2, scope: "Trích xuất B3; tính lại B4–B5" }));
  return <section className="workflow-section"><StepActions back="Quay lại" onBack={onBack} primary={primaryAction} onPrimary={action} disabled={locked || extracting || (!files.length && !quotes.length)} working={busy} /><article className="workflow-card workflow-summary workflow-pr-summary"><div className="workflow-pr-summary-heading"><strong>{pr.code}: {pr.category}</strong><span className="workflow-chip">{pr.items?.length || 0} sản phẩm</span></div><dl className="workflow-summary-grid"><div><dt>Người yêu cầu</dt><dd>{pr.metadata?.requested_by || pr.creator_name}</dd></div><div><dt>Ngày nhận hàng dự kiến</dt><dd>{formatDate(pr.delivery_due_date)}</dd></div><div><dt>Ngân sách dự kiến</dt><dd>{formatComparisonMoney(pr.estimated_budget)} {pr.target_currency || "VND"}</dd></div><div><dt>Ngày tạo</dt><dd>{formatDate(pr.created_at)}</dd></div><div className="workflow-summary-wide"><dt>Mục đích / Ghi chú</dt><dd>{pr.metadata?.purpose || "—"}</dd></div></dl><section className="workflow-pr-products" aria-label="Danh sách sản phẩm trong đề nghị">{pr.items?.length ? <ol>{pr.items.map((item, index) => <li key={item.item_id || item.id || `${item.product_name}-${index}`}><span className="workflow-pr-product-index">{index + 1}</span><span className="workflow-pr-product-name">{item.product_name}</span><span className="workflow-pr-product-quantity">{Number(item.quantity).toLocaleString("vi-VN")} {item.unit}</span><span className="workflow-pr-product-notes">{item.notes || "—"}</span></li>)}</ol> : <p>Chưa có sản phẩm trong đề nghị.</p>}</section></article>
    <article className="workflow-card"><div className="workflow-card-heading"><div><p className="text-overline">BƯỚC 2</p><h2 className="text-h2">Danh sách tệp báo giá tải lên</h2></div></div><div className="workflow-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); addFiles(event.dataTransfer.files); }}><UploadCloud aria-hidden="true" /><p>Thả file PDF vào đây hoặc <button type="button" disabled={locked || extracting} onClick={() => fileInput.current?.click()}>chọn từ máy</button></p><small>Tối đa 5 file, mỗi file ≤ 5 MB</small><input ref={fileInput} type="file" accept=".pdf,application/pdf" multiple hidden disabled={locked || extracting} onChange={(event) => { if (event.target.files) addFiles(event.target.files); event.target.value = ""; }} /><div className="workflow-demo-actions"><button className="secondary" type="button" disabled={locked || extracting || busy || !!files.length || quotes.length >= quoteLimit} onClick={() => void createDemo()}>{busy ? "Đang tải báo giá mẫu…" : "Tạo dữ liệu mẫu"}</button><span>Nạp 2 file PDF báo giá vật liệu xây dựng vào danh sách. Nhấn “Tiến hành trích xuất” để bắt đầu xử lý.</span></div></div><div className="workflow-table-scroll"><table className="workflow-table"><thead><tr><th>STT</th><th>Tên file báo giá</th><th>Dung lượng</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{quotes.map((quote, index) => <tr key={quote.id}><td>{index + 1}</td><th>{quote.source_filename}<small>{quote.supplier_name}</small></th><td>—</td><td><span className="workflow-chip success">Trích xuất thành công</span></td><td><button className="workflow-icon-button" type="button" aria-label={`Xem ${quote.source_filename}`} title="Xem file" onClick={() => setPreview(quote)}><Eye aria-hidden="true" /></button><button className="workflow-icon-button danger" type="button" disabled={extracting} aria-label={`Xóa ${quote.source_filename}`} title="Xóa file" onClick={() => { setDeleteTarget(quote); setImpactOpen(true); }}><Trash2 aria-hidden="true" /></button></td></tr>)}{files.map((file, index) => <tr className="workflow-new-file" key={`${file.name}-${index}`}><td>{quotes.length + index + 1}</td><th>{file.name}</th><td>{(file.size / 1024 / 1024).toFixed(1)} MB</td><td><span className="workflow-chip warning">Chưa trích xuất</span></td><td><button className="workflow-icon-button danger" type="button" aria-label={`Bỏ ${file.name}`} onClick={() => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}><Trash2 aria-hidden="true" /></button></td></tr>)}</tbody></table></div>{!quotes.length && !files.length && <p className="workflow-empty">Chưa có tệp báo giá.</p>}</article>
    {locked && <p className="workflow-alert warning">Hồ sơ đã gửi duyệt hoặc hoàn tất; không thể thay đổi file báo giá.</p>}{extractionJob?.status === "failed" && <p className="workflow-alert warning" role="alert">{extractionJob.completed}/{extractionJob.total} báo giá đã trích xuất. {extractionJob.errors.join(" | ")} Chọn lại các file chưa hoàn tất để tiếp tục.</p>}{extractionJob?.status === "cancelled" && <p className="workflow-alert info" role="status">Đã ngừng trích xuất. Các báo giá hoàn tất trước đó vẫn được giữ lại; bạn có thể chỉnh sửa hoặc chọn lại file.</p>}{!!files.length && <p className="workflow-alert warning" role="status">{files.length} file mới sẽ được trích xuất; kết quả tổng hợp và đề xuất cần được cập nhật.</p>}<p className="error" role="alert">{error}</p>
    {preview && <SourceReview session={session} quotation={preview} onClose={() => setPreview(null)} />}
    {impactOpen && <ImpactDialog changes={impactChanges} detail={deleteTarget ? "Xóa file sẽ loại dữ liệu báo giá này khỏi lần tổng hợp tiếp theo." : "Các file cũ không thay đổi sẽ được giữ nguyên; kết quả phân tích và đề xuất cần tính lại."} confirm={deleteTarget ? "Xóa file báo giá" : "Xác nhận & trích xuất lại"} disabled={locked || extracting} busy={busy} onCancel={() => { setImpactOpen(false); setDeleteTarget(null); }} onConfirm={() => { if (deleteTarget) void remove(); else upload(); }} />}
  </section>;
}

function requestItems(pr: PurchaseRequest): PurchaseItem[] {
  return pr.items?.length ? pr.items : [{ item_id: `${pr.id}:main`, product_name: pr.category, quantity: pr.requested_quantity || pr.quantity || 1, unit: pr.requested_uom || "" }];
}

function requestItemId(pr: PurchaseRequest, item: PurchaseItem, index: number): string {
  return item.item_id || item.id || `${pr.id}:item:${item.order_index ?? index}`;
}

function matchReviewed(item: Quotation["items"][number], pr: PurchaseRequest): boolean {
  const status = String(item.match_status || "").toUpperCase();
  return status === "REJECTED" || ["AUTO_MATCHED", "MANUAL_MATCHED"].includes(status) && requestItems(pr).some((row, index) => requestItemId(pr, row, index) === item.matched_pr_item_id);
}

function savedOffer(quote: Quotation, prItemId: string) {
  const lines = quote.items.filter((item) => ["AUTO_MATCHED", "MANUAL_MATCHED"].includes(String(item.match_status || "").toUpperCase()) && item.matched_pr_item_id === prItemId);
  if (!lines.length) return undefined;
  const quantity = lines.reduce((sum, line) => sum + Number(line.quantity), 0);
  const total = lines.reduce((sum, line) => sum + Number(line.line_total), 0);
  return { ...lines[0], quantity, line_total: total, unit_price: lines.length === 1 ? Number(lines[0].unit_price) : quantity ? total / quantity : 0 };
}

function ReviewStep({ pr, quotes, analysis, session, onRefresh, onBack, onNext }: { pr: PurchaseRequest; quotes: Quotation[]; analysis: AnalysisView | null; session: Session; onRefresh: () => Promise<void>; onBack: () => void; onNext: () => void }) {
  const [activeId, setActiveId] = useState<string | null>(quotes.find((quote) => quote.status !== "confirmed")?.id || quotes[0]?.id || null);
  const [activeItemIndex, setActiveItemIndex] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const [revisionTarget, setRevisionTarget] = useState<{ quote: Quotation; action: "reopen" | "re-extract" } | null>(null);
  const [matches, setMatches] = useState<JsonObject | null>(null);
  const [matchRevision, setMatchRevision] = useState(0);
  const [approvalRequestId, setApprovalRequestId] = useState<string | null>(null);

  const [hasManualEdits, setHasManualEdits] = useState(false);
  const [summarizeWarning, setSummarizeWarning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const confirmed = quotes.filter((quote) => quote.status === "confirmed").length;
  const ready = quotes.length >= 2 && confirmed === quotes.length && quotes.every((quote) => quote.items.length > 0 && quote.items.every((item) => matchReviewed(item, pr)));
  const filesToConfirm = quotes.filter((quote) => quote.status !== "confirmed").length;
  const itemsToMatch = quotes.some((quote) => quote.items.length === 0 || quote.items.some((item) => !matchReviewed(item, pr)));
  const hasPriorAnalysis = !!analysis && !["not_started", "stale"].includes(analysis.status);
  const locked = ["pending_approval", "approved", "cancelled"].includes(pr.status);
  const activeQuote = quotes.find((quote) => quote.id === activeId);
  useEffect(() => {
    setActiveId((current) => quotes.some((quote) => quote.id === current) ? current : quotes.find((quote) => quote.status !== "confirmed")?.id || quotes[0]?.id || null);
  }, [quotes]);
  useEffect(() => {
    setMatches(null); setError("");
    if (!quotes.length) return;
    let active = true;
    void apiRequest<JsonObject>(`/prs/${encodeURIComponent(pr.id)}/fuzzy-matches`, session).then((result) => { if (active) setMatches(result); }).catch((exception) => { if (active) setError(exception instanceof Error ? exception.message : "Không tải được kết quả đối chiếu mặt hàng."); });
    return () => { active = false; };
  }, [quotes, pr.id, session, matchRevision]);
  const applyRevision = async () => {
    if (!revisionTarget || locked) return;
    setBusy(true); setError("");
    try {
      await apiRequest(`/quotations/${encodeURIComponent(revisionTarget.quote.id)}/${revisionTarget.action}`, session, { method: "POST" });
      await onRefresh(); setRevision((current) => current + 1); setRevisionTarget(null);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể cập nhật báo giá."); }
    finally { setBusy(false); }
  };
  const confirmMatch = async (index: number, targetId: string | null) => {
    if (!activeQuote || locked) return;
    setBusy(true); setError("");
    try {
      await apiRequest(`/quotations/${encodeURIComponent(activeQuote.id)}/items/${encodeURIComponent(`${activeQuote.id}:item:${index}`)}/confirm-match`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: targetId ? "CONFIRM" : "REJECT", pr_item_id: targetId }) });
      if (hasPriorAnalysis) setHasManualEdits(true);
      await onRefresh();
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể lưu kết quả đối chiếu."); }
    finally { setBusy(false); }
  };
  return <section className="workflow-section workflow-review"><StepActions back="Quay lại" onBack={onBack} primary={hasManualEdits && hasPriorAnalysis ? "Tổng hợp lại" : "Tiến hành tổng hợp"} onPrimary={() => hasManualEdits && hasPriorAnalysis ? setSummarizeWarning(true) : onNext()} disabled={!ready || busy} tone={hasManualEdits && hasPriorAnalysis ? "info" : "default"} />{!ready && !!quotes.length && <p className="workflow-alert warning">{filesToConfirm ? `Cần duyệt ${filesToConfirm} báo giá còn lại.` : itemsToMatch ? `Đã duyệt ${confirmed}/${quotes.length} báo giá. Hãy đối chiếu tên từng dòng với mặt hàng yêu cầu PR trong biểu mẫu bên dưới.` : "Cần ít nhất 2 báo giá đã xác nhận để tiến hành tổng hợp."}</p>}<article className="workflow-card workflow-file-list"><div className="workflow-card-heading"><div><h2 className="text-title">Danh sách báo giá tải lên</h2></div><span className="workflow-chip">Đã duyệt {confirmed}/{quotes.length}</span></div><div className="workflow-table-scroll"><table className="workflow-table"><thead><tr><th>STT</th><th>Tên file báo giá</th><th>Trạng thái trích xuất</th><th>Đánh giá AI</th><th>Thao tác</th></tr></thead><tbody>{quotes.map((quote, index) => <tr key={quote.id} className={activeId === quote.id ? "workflow-selected-file" : ""} onClick={() => { setActiveId(quote.id); setActiveItemIndex(null); }}><td>{index + 1}</td><th><FileText aria-hidden="true" />{quote.source_filename}</th><td><span className={`workflow-chip ${quote.extraction_warnings?.length ? "warning" : "success"}`}>{quote.extraction_warnings?.length ? "Cần đối soát" : "Đã trích xuất"}</span></td><td>{quote.extraction_warnings?.length ? `${quote.extraction_warnings.length} cảnh báo` : quote.items.length > 0 && quote.items.every((item) => matchReviewed(item, pr)) ? "Đã đối chiếu tên sản phẩm" : "Cần duyệt khớp tên"}</td><td><div className="workflow-file-actions"><button className={`secondary workflow-file-action workflow-file-action-approve ${activeId === quote.id ? "is-active" : ""}`} type="button" disabled={quote.status === "confirmed" || locked || busy || activeId !== quote.id} onClick={(event) => { event.stopPropagation(); setActiveId(quote.id); setApprovalRequestId(quote.id); }}><Check aria-hidden="true" />{quote.status === "confirmed" ? "Đã duyệt" : "Duyệt file"}</button><button className="secondary workflow-file-action" type="button" aria-label={`Trích xuất lại ${quote.source_filename}`} title="Trích xuất lại" disabled={quote.status === "confirmed" || locked || busy || activeId !== quote.id} onClick={(event) => { event.stopPropagation(); setRevisionTarget({ quote, action: "re-extract" }); }}><RefreshCw aria-hidden="true" />Trích xuất lại</button></div></td></tr>)}</tbody></table></div>{!quotes.length && <p className="workflow-empty">Hãy tải báo giá ở Bước 2 trước khi đối soát.</p>}</article>
    {activeQuote && <div className="workflow-review-split"><QuoteDocumentPreview session={session} quotation={activeQuote} activeIndex={activeItemIndex} /><div className="workflow-review-editor" onMouseOver={(event) => { const row = (event.target as HTMLElement).closest<HTMLElement>("[data-source-index]"); setActiveItemIndex(row?.dataset.sourceIndex == null ? null : Number(row.dataset.sourceIndex)); }} onFocusCapture={(event) => { const row = (event.target as HTMLElement).closest<HTMLElement>("[data-source-index]"); setActiveItemIndex(row?.dataset.sourceIndex == null ? null : Number(row.dataset.sourceIndex)); }}>{locked || activeQuote.status === "confirmed" ? <QuotationReadback quote={activeQuote} pr={pr} matches={matches} busy={busy} onMatch={(index, target) => void confirmMatch(index, target)} canReopen={!locked && activeQuote.status === "confirmed"} onReopen={() => setRevisionTarget({ quote: activeQuote, action: "reopen" })} /> : <QuotationEditor key={`${activeQuote.id}-${revision}`} session={session} quotationId={activeQuote.id} allQuotations={quotes} request={pr} matchResults={matches} submitRequest={approvalRequestId === activeQuote.id} onSubmitRequestHandled={() => setApprovalRequestId(null)} onDirty={() => setHasManualEdits(true)} onChanged={() => { void onRefresh(); }} onSelect={(id) => { setActiveId(id); setActiveItemIndex(null); }} onReopen={(quote) => setRevisionTarget({ quote, action: "reopen" })} onReextract={(quote) => setRevisionTarget({ quote, action: "re-extract" })} />}</div></div>}
    {locked && <p className="workflow-alert warning">Hồ sơ đang chờ duyệt hoặc đã hoàn tất; dữ liệu báo giá ở chế độ chỉ đọc.</p>}
    {revisionTarget && <ImpactDialog changes={[{ label: revisionTarget.action === "reopen" ? "Mở lại dữ liệu đã xác nhận" : "Trích xuất lại file", before: revisionTarget.quote.source_filename, after: "Cần đối soát lại", level: 2, scope: "Tính lại B4–B5" }]} detail="Dữ liệu gốc được giữ nguyên; kết quả phân tích và đề xuất sẽ được làm mới sau khi xác nhận lại báo giá." confirm="Xác nhận thay đổi" disabled={locked} busy={busy} onCancel={() => setRevisionTarget(null)} onConfirm={() => void applyRevision()} />}
    {summarizeWarning && <ImpactDialog changes={[{ label: "Dữ liệu bóc tách đã điều chỉnh", before: "Kết quả phân tích trước", after: "Dữ liệu đã xác nhận mới", level: 2, scope: "Tính lại B4–B5" }]} detail="Dữ liệu báo giá được chỉnh sửa thủ công. Ma trận so sánh và phương án đề xuất cần được tính lại." confirm="Xác nhận & tổng hợp lại" onCancel={() => setSummarizeWarning(false)} onConfirm={() => { setSummarizeWarning(false); onNext(); }} />}
    <p className="error" role="alert">{error}{error && !matches && <button className="secondary" type="button" onClick={() => setMatchRevision((current) => current + 1)}>Tải lại đối chiếu</button>}</p>
  </section>;
}

function QuotationReadback({ quote, pr, matches, canReopen, busy, onReopen, onMatch }: { quote: Quotation; pr: PurchaseRequest; matches: JsonObject | null; canReopen: boolean; busy: boolean; onReopen: () => void; onMatch: (index: number, targetId: string | null) => void }) {
  const requirements = requestItems(pr);
  return <article className="workflow-card workflow-quote-readback"><header className="extraction-pane-heading"><h2 className="text-title">Dữ liệu bóc tách đã duyệt</h2><span className="text-small">{quote.supplier_name}</span></header><div className="extraction-editor-body">
    <dl className="workflow-summary-grid"><div><dt>Giao hàng</dt><dd>{quote.delivery_time || "—"}</dd></div><div><dt>Thanh toán</dt><dd>{quote.payment_terms || "—"}</dd></div><div><dt>Bảo hành</dt><dd>{quote.warranty || "—"}</dd></div></dl>
    <div className="extraction-item-list">{quote.items.map((item, index) => {
      const target = requirements.find((row, rowIndex) => requestItemId(pr, row, rowIndex) === item.matched_pr_item_id);
      const suggestion = (matches?.results || []).find((row: JsonObject) => row.quote_item_id === `${quote.id}:item:${index}`)?.best_match;
      const reviewed = matchReviewed(item, pr);
      return <article className="extraction-item" data-source-index={index} key={index}><div className="extraction-item-heading"><strong>{index + 1}. {target?.product_name || (String(item.match_status).toUpperCase() === "REJECTED" ? "Sản phẩm ngoài yêu cầu PR" : "Chưa xác nhận sản phẩm PR")}</strong></div><p className="text-small">Tên trên báo giá: {item.product_name}</p><div className="extraction-line-total"><span>{item.quantity} {item.unit} × {formatComparisonMoney(item.unit_price)} {quote.currency}</span><strong>{formatComparisonMoney(item.line_total)} {quote.currency}</strong></div>
        {!reviewed && canReopen && <div className="extraction-match"><span className="extraction-match-status unresolved">Cần lưu đối chiếu tên ở bước 3</span>{suggestion && <button type="button" className="secondary" disabled={busy} onClick={() => onMatch(index, suggestion.pr_item_id)}>Xác nhận: {suggestion.pr_item_name}</button>}<label>Chọn sản phẩm yêu cầu<select value="" disabled={busy} onChange={(event) => { if (event.target.value) onMatch(index, event.target.value === "__rejected" ? null : event.target.value); }}><option value="">Chọn sản phẩm PR…</option>{requirements.map((row, rowIndex) => <option key={rowIndex} value={requestItemId(pr, row, rowIndex)}>{row.product_name}</option>)}<option value="__rejected">Tách riêng — ngoài yêu cầu PR</option></select></label></div>}
        {reviewed && <span className="extraction-match-status matched">✓ {String(item.match_status).toUpperCase() === "REJECTED" ? "Đã tách riêng" : "Đã đối chiếu tên sản phẩm"}</span>}
      </article>;
    })}</div>{canReopen && <button className="secondary" type="button" disabled={busy} onClick={onReopen}>Sửa dữ liệu và đối chiếu lại</button>}</div>
  </article>;
}

function QuoteDocumentPreview({ session, quotation, activeIndex }: { session: Session; quotation: Quotation; activeIndex: number | null }) {
  const [preview, setPreview] = useState<JsonObject | null>(null);
  const [pages, setPages] = useState<string[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const urls: string[] = [];
    setPreview(null); setPages([]); setError("");
    void (async () => {
      try {
        const result = await apiRequest<JsonObject>(`/quotations/${encodeURIComponent(quotation.id)}/review-preview`, session);
        const fetched = await Promise.all((result.pages || []).map((page: JsonObject) => apiBlob(`/quotations/${encodeURIComponent(quotation.id)}/review-preview/pages/${page.number}`, session)));
        fetched.forEach(({ blob }) => urls.push(URL.createObjectURL(blob)));
        if (active) { setPreview(result); setPages(urls); }
      } catch (exception) { if (active) setError(exception instanceof Error ? exception.message : "Không thể hiển thị file gốc."); }
    })();
    return () => { active = false; urls.forEach(URL.revokeObjectURL); };
  }, [quotation.id, session]);
  return <section className="workflow-document"><div className="workflow-document-heading"><p className="text-overline">FILE GỐC</p><h3 className="text-title">{quotation.source_filename}</h3><p>Rê chuột vào dòng hàng ở biểu mẫu để xem vị trí trích xuất.</p></div>{error ? <p className="workflow-alert warning">{error}</p> : !preview ? <p className="workflow-empty">Đang chuẩn bị bản xem trước…</p> : <div className="workflow-document-pages">{(preview.pages || []).map((page: JsonObject, pageIndex: number) => <figure key={page.number} className="workflow-document-page"><figcaption>Trang {page.number}</figcaption><div className="source-page-canvas"><img src={pages[pageIndex]} alt={`Trang ${page.number} của ${quotation.source_filename}`} />{(preview.matches || []).filter((match: JsonObject) => match.region?.page === page.number).map((match: JsonObject) => { const region = match.region; const itemIndex = Number(match.item_index); return <span key={itemIndex} className={`source-row-highlight ${activeIndex === itemIndex ? "active" : ""}`} style={{ left: `${Number(region.x) / Number(page.width) * 100}%`, top: `${Number(region.y) / Number(page.height) * 100}%`, width: `${Number(region.width) / Number(page.width) * 100}%`, height: `${Number(region.height) / Number(page.height) * 100}%` }}><i>{itemIndex + 1}</i></span>; })}</div></figure>)}</div>}</section>;
}

function ComparisonStep({ pr, quotes, analysis, session, onRefreshAnalysis, onBack, onNext }: { pr: PurchaseRequest; quotes: Quotation[]; analysis: AnalysisView | null; session: Session; onRefreshAnalysis: () => Promise<AnalysisView | undefined>; onBack: () => void; onNext: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ready = quotes.length >= 2 && quotes.every((quote) => quote.status === "confirmed" && quote.items.length > 0 && quote.items.every((item) => matchReviewed(item, pr)));
  const completed = analysis != null && ["awaiting_buyer_review", "pending_manager_approval", "approved", "rejected"].includes(analysis.status);
  const running = analysis?.status === "running";
  const start = async () => {
    if (completed) { onNext(); return; }
    if (!ready || running) return;
    setBusy(true); setError("");
    try { await apiRequest(`/prs/${encodeURIComponent(pr.id)}/analysis`, session, { method: "POST" }); await onRefreshAnalysis(); }
    catch (exception) { if (exception instanceof ApiError && exception.status === 422) await onRefreshAnalysis(); setError(exception instanceof Error ? exception.message : "Không thể tạo đề xuất."); }
    finally { setBusy(false); }
  };
  const currency = pr.target_currency || "VND";
  const totalFor = (quote: Quotation): number | null => {
    if (!ready) return null;
    const analyzed = completed ? (analysis?.tco_results || []).find((result: JsonObject) => result.supplier_id === quote.supplier_id)?.total_tco : null;
    if (analyzed != null) return Number(analyzed);
    if ((quote.currency || "VND") !== currency || quote.vat_rate == null || quote.vat_included == null || quote.shipping_fee == null) return null;
    const factor = quote.vat_included ? 1 : 1 + Number(quote.vat_rate);
    return Math.round((quote.items.reduce((sum, item) => sum + Number(item.line_total), 0) + Number(quote.shipping_fee)) * factor * 100) / 100;
  };
  const totals = quotes.map(totalFor);
  const comparableTotals = totals.length > 0 && totals.every((value) => value != null);
  const lowestTotal = comparableTotals ? Math.min(...totals.map(Number)) : null;
  const cheapest = lowestTotal == null ? undefined : quotes.find((quote) => totalFor(quote) === lowestTotal);
  const preferredSupplierId = completed ? String(analysis?.review?.preferred_supplier_id || analysis?.decision_proposal?.preferred_supplier_id || "") : "";
  const leadTimes = quotes.flatMap((quote) => quote.lead_time_days == null ? [] : [Number(quote.lead_time_days)]);
  const fastest = leadTimes.length ? Math.min(...leadTimes) : null;
  const warranties = quotes.flatMap((quote) => quote.warranty_months == null ? [] : [Number(quote.warranty_months)]);
  const longestWarranty = warranties.length ? Math.max(...warranties) : null;
  const sameCurrency = quotes.every((quote) => (quote.currency || "VND") === currency);
  return <section className="workflow-section workflow-comparison">
    <StepActions back="Quay lại" onBack={onBack} primary={completed ? "Xem kết quả đề xuất" : running ? "Đang tạo đề xuất AI…" : "Đề xuất kết quả"} onPrimary={() => void start()} disabled={!ready || running} working={busy} />
    {!ready && <p className="workflow-alert warning">Quay lại bước 3 để xác nhận báo giá và hoàn tất đối chiếu tên sản phẩm trước khi tổng hợp.</p>}
    <article className="workflow-card workflow-matrix-card" aria-label="Ma trận đối chiếu tiêu chí">
      <div className="workflow-table-scroll"><table className="workflow-table workflow-matrix"><caption className="visually-hidden">Ma trận đối chiếu từ các sản phẩm đã duyệt ở bước 3</caption><thead><tr><th>HẠNG MỤC / TIÊU CHÍ<small>Chỉ số tối ưu hiển thị màu xanh</small></th>{quotes.map((quote, index) => <th key={quote.id} className={quote.supplier_id === preferredSupplierId || quote.id === cheapest?.id ? "workflow-recommended" : ""}><div>{index + 1}. {quote.supplier_name}</div>{quote.id === cheapest?.id && <span className="workflow-chip success">CHI PHÍ THẤP NHẤT</span>}<small>{quote.source_filename}</small></th>)}</tr></thead>
      <tbody>{requestItems(pr).map((item, index) => {
        const id = requestItemId(pr, item, index);
        const offers = quotes.map((quote) => savedOffer(quote, id));
        const prices = offers.flatMap((offer) => offer ? [Number(offer.unit_price)] : []);
        const bestPrice = sameCurrency && prices.length ? Math.min(...prices) : null;
        return <tr key={id}><th>{index + 1}. {item.product_name}<small>Số lượng: {item.quantity} {item.unit}</small></th>{quotes.map((quote, quoteIndex) => {
          const offered = offers[quoteIndex]; const optimal = offered && Number(offered.unit_price) === bestPrice;
          return <td key={quote.id} className={optimal ? "workflow-optimal" : ""}>{offered ? <><strong>{formatComparisonMoney(offered.unit_price)} {quote.currency || "VND"}</strong>{optimal && <span className="workflow-best-badge">Tối ưu nhất</span>}<small>Tổng: {formatComparisonMoney(offered.line_total)} {quote.currency || "VND"}</small></> : <span className="text-small">Không có sản phẩm đã ghép</span>}</td>;
        })}</tr>;
      })}
      <tr><th>Thời gian giao hàng<small>Tiến độ thực hiện</small></th>{quotes.map((quote) => <td key={quote.id} className={quote.lead_time_days != null && quote.lead_time_days === fastest ? "workflow-optimal" : ""}><strong>{quote.delivery_time || (quote.lead_time_days != null ? `${quote.lead_time_days} ngày` : "—")}</strong>{quote.lead_time_days != null && quote.lead_time_days === fastest && <small>✓ Giao nhanh nhất</small>}</td>)}</tr>
      <tr><th>Bảo hành & công nợ<small>Điều khoản thương mại</small></th>{quotes.map((quote) => <td key={quote.id}><strong className={quote.warranty_months != null && quote.warranty_months === longestWarranty ? "workflow-positive" : ""}>{quote.warranty || (quote.warranty_months != null ? `${quote.warranty_months} tháng` : "—")}</strong><small>{quote.payment_terms || "Chưa có điều khoản thanh toán"}</small></td>)}</tr>
      <tr className="workflow-total-row"><th>TỔNG GIÁ TRỊ (GỒM VAT & PHÍ)<small>Ngân sách gốc: {formatBudget(pr.estimated_budget)}</small><small>Bao gồm cả sản phẩm ngoài PR</small></th>{quotes.map((quote) => {
        const total = totalFor(quote); const optimal = total != null && total === lowestTotal;
        const variance = total != null && Number(pr.estimated_budget) > 0 ? (total / Number(pr.estimated_budget) - 1) * 100 : null;
        return <td key={quote.id}><div className={optimal ? "workflow-total-value optimal" : "workflow-total-value"}><strong>{total != null ? `${formatComparisonMoney(total)} ${currency}` : "Chưa đủ dữ liệu quy đổi"}</strong>{variance != null && <small className={variance > 0 ? "workflow-variance" : "workflow-positive"}>{variance > 0 ? "+" : ""}{variance.toFixed(1)}% ngân sách</small>}{optimal && <span className="workflow-best-badge">★ Tiết kiệm nhất</span>}</div></td>;
      })}</tr></tbody></table></div>
      <div className="workflow-matrix-footer">
        <div className={`workflow-conclusion ${running ? "processing" : ""}`} role="status">{running ? <RefreshCw aria-hidden="true" /> : <Check aria-hidden="true" />}<div><strong>{running ? "Đang xây dựng phương án đề xuất" : completed ? "Đã hoàn tất đề xuất phương án" : "Kết luận tổng hợp từ dữ liệu đã duyệt"}</strong><p>{running ? "AI đang tổng hợp báo cáo. Bạn có thể theo dõi tiến độ trên thanh bên." : completed ? "Chọn “Xem kết quả đề xuất” để xem hồ sơ mua sắm ở bước 5." : !ready ? "Cần hoàn tất duyệt trích xuất ở bước 3." : cheapest ? `${cheapest.supplier_name} có tổng chi phí thấp nhất: ${formatComparisonMoney(lowestTotal)} ${currency}. Chọn “Đề xuất kết quả” để đánh giá phương án.` : "Chọn “Đề xuất kết quả” để phân tích và quy đổi chi phí."}</p></div></div>
        <p className="workflow-readonly">🔒 Chế độ xem kết quả tổng hợp (chỉ đọc): Số liệu và đối chiếu sản phẩm được lấy từ dữ liệu đã duyệt ở bước 3.</p>
      </div>
    </article>
    {analysis?.status === "needs_input" && <p className="workflow-alert warning">{analysis.message || "Cần bổ sung dữ liệu báo giá trước khi phân tích."}</p>}{analysis?.status === "stale" && analysis.message && <p className="workflow-alert info" role="status">{analysis.message}</p>}{error && <p className="error" role="alert">{error}</p>}
  </section>;
}

function ProposalStep({ pr, quotes, analysis, session, onRefreshAnalysis, onBack, onEdit }: { pr: PurchaseRequest; quotes: Quotation[]; analysis: AnalysisView | null; session: Session; onRefreshAnalysis: () => Promise<AnalysisView | undefined>; onBack: () => void; onEdit: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const status = analysis?.status || "not_started";
  const proposal = (analysis?.review || analysis?.decision_proposal || {}) as JsonObject;
  const selectedId = String(proposal.preferred_supplier_id || "");
  const selected = quotes.find((quote) => quote.supplier_id === selectedId);
  const selectedTco = (analysis?.tco_results || []).find((result: JsonObject) => result.supplier_id === selectedId);
  const ready = status === "awaiting_buyer_review" && proposal.status === "proposed" && !!analysis?.analysis_id;
  const pending = status === "pending_manager_approval" || pr.status === "pending_approval";
  const approved = status === "approved" || pr.status === "approved";
  const rejected = status === "rejected" || pr.status === "rejected" || !!pr.rejection_reason;
  const submit = async () => {
    if (!analysis?.analysis_id) return;
    setBusy(true); setError("");
    try { await apiRequest(`/analyses/${encodeURIComponent(analysis.analysis_id)}/submit-approval`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note: note.trim() || null }) }); await onRefreshAnalysis(); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể gửi duyệt."); }
    finally { setBusy(false); }
  };
  const proposedTotal = Number(selectedTco?.total_tco || 0);
  const variance = proposedTotal - Number(pr.estimated_budget);
  const others = quotes.filter((quote) => quote.id !== selected?.id);
  const rankedTotals = (analysis?.tco_results || []).map((result: JsonObject) => ({ name: quotes.find((quote) => quote.supplier_id === result.supplier_id)?.supplier_name || result.supplier_id, total: Number(result.total_tco) })).filter((row: { total: number }) => row.total > 0).sort((a: { total: number }, b: { total: number }) => a.total - b.total);
  return <section className="workflow-section workflow-proposal"><StepActions back={rejected ? "Quay lại chỉnh sửa" : "Quay lại"} onBack={rejected ? onEdit : onBack} primary={ready ? "Gửi duyệt đề nghị" : pending ? "Chờ duyệt" : approved ? "✓ ĐÃ PHÊ DUYỆT" : rejected ? "Gửi duyệt đề nghị ⊘" : "Chưa có đề xuất"} onPrimary={ready ? () => void submit() : undefined} disabled={!ready} working={busy} tone={approved ? "approved" : pending ? "pending" : rejected ? "rejected" : "default"} />
    {approved && <div className="workflow-alert success"><strong>Hồ sơ đã được phê duyệt chính thức.</strong>{pr.po_id && <> Đã tạo đơn mua hàng <Link to={`/purchase-orders/${pr.po_id}`}>{pr.po_id}</Link>.</>}{analysis?.manager_note && <p>Ý kiến phê duyệt: {analysis.manager_note}</p>}</div>}
    {rejected && <div className="workflow-alert danger"><strong>ĐỀ NGHỊ BỊ TỪ CHỐI PHÊ DUYỆT</strong><blockquote>{pr.rejection_reason || analysis?.manager_note || analysis?.message || "Vui lòng xem phản hồi của Quản lý và chỉnh sửa hồ sơ."}</blockquote></div>}
    {pending && <p className="workflow-alert warning">Hồ sơ đã gửi Quản lý phê duyệt và đang khóa chỉnh sửa.</p>}
    {!selected && <p className="workflow-alert warning">{pending || approved || rejected ? "Hồ sơ đã có trạng thái xử lý, nhưng kết quả đề xuất chi tiết hiện không có trong dữ liệu đã lưu." : "Chưa có phương án được kiểm chứng. Quay lại Bước 4 để phân tích dữ liệu hiện hành."}</p>}
    <article className="workflow-card workflow-proposal-card"><div className="workflow-card-heading"><div><h2 className="text-title">Tổng hợp đề xuất mua sắm: {pr.code}</h2></div>{selected && <span className="workflow-chip success">✓ Phương án được đề xuất</span>}</div>
      <div className="workflow-kpis"><div className="workflow-kpi-supplier"><span>ĐƠN VỊ ĐỀ XUẤT CHỌN</span><strong>{selected?.supplier_name || "—"}</strong></div><div className={`workflow-kpi-budget ${rejected ? "workflow-kpi-rejected" : ""}`}><span>TỔNG NGÂN SÁCH ĐỀ XUẤT</span><strong>{proposedTotal ? `${formatComparisonMoney(proposedTotal)} đ` : "—"}</strong><small className={variance > 0 ? "workflow-variance" : ""}>{proposedTotal ? `${variance > 0 ? "+" : ""}${formatComparisonMoney(variance)} đ so với dự toán (${formatBudget(pr.estimated_budget)})` : `Dự toán ${formatBudget(pr.estimated_budget)}`}</small></div><div><span>TIẾN ĐỘ & BẢO HÀNH</span><strong>{selected?.delivery_time || (selected?.lead_time_days != null ? `${selected.lead_time_days} ngày` : "—")}</strong><small>{selected?.warranty || (selected?.warranty_months != null ? `${selected.warranty_months} tháng` : "Chưa có bảo hành")}</small></div></div>
      <h3 className="text-title workflow-proposal-table-title">Bảng chi tiết hạng mục đề xuất chọn mua</h3>
      <div className="workflow-table-scroll"><table className="workflow-table workflow-proposal-table"><thead><tr><th>STT</th><th>Mặt hàng mua sắm</th><th>SL</th><th className="workflow-preferred-price">Đơn giá {selected?.supplier_name || "đề xuất"} (Chọn)</th>{others.map((quote) => <th key={quote.id}>Giá {quote.supplier_name}</th>)}</tr></thead><tbody>{requestItems(pr).map((item, index) => {
        const id = requestItemId(pr, item, index); const offer = selected ? savedOffer(selected, id) : undefined;
        return <tr key={id}><td>{index + 1}</td><th>{item.product_name}{offer && offer.product_name !== item.product_name && <small>Tên trên báo giá: {offer.product_name}</small>}</th><td>{offer?.quantity ?? item.quantity} {item.unit}</td><td className="workflow-preferred-price">{offer ? `${formatComparisonMoney(offer.unit_price)} ${selected?.currency || "VND"}` : "Chưa có sản phẩm đã ghép"}</td>{others.map((quote) => { const other = savedOffer(quote, id); return <td key={quote.id} className="workflow-alternative-price">{other ? `${formatComparisonMoney(other.unit_price)} ${quote.currency || "VND"}` : "—"}</td>; })}</tr>;
      })}{(selected?.items || []).filter((item) => !matchReviewed(item, pr) || String(item.match_status).toUpperCase() === "REJECTED").map((item, index) => <tr key={`extra-${index}`}><td>—</td><th>{item.product_name}<small>Ngoài danh mục PR / chưa ghép</small></th><td>{item.quantity} {item.unit}</td><td className="workflow-preferred-price">{formatComparisonMoney(item.unit_price)} {selected?.currency || "VND"}</td>{others.map((quote) => <td key={quote.id}>—</td>)}</tr>)}</tbody></table></div>
      <div className="workflow-commercial-summary">{rankedTotals.length > 1 && <p><strong>Tổng so sánh giá trị:</strong> {rankedTotals.map((row: { name: string; total: number }) => `${row.name} (${formatComparisonMoney(row.total)} đ)`).join(" < ")}</p>}<p><strong>Điều khoản thương mại:</strong> {selected?.payment_terms || "Chưa có điều khoản thanh toán."} {selected?.vat_included ? "Đơn giá đã bao gồm VAT." : "VAT và phí được tính trong tổng giá trị phân tích."}</p></div>
      <div className="workflow-rationale"><h3 className="text-title">Căn cứ & giải trình phương án</h3><p>{proposal.rationale || "Chưa có giải trình từ kết quả phân tích."}</p></div>
    </article>
    <article className="workflow-card workflow-note-card"><h2 className="text-title">Ghi chú bổ sung gửi người phê duyệt</h2>{ready ? <><textarea value={note} onChange={(event) => setNote(event.target.value)} rows={4} maxLength={1000} placeholder="Thông tin bổ sung để Quản lý xem xét…" /><p className="workflow-readonly">Lời nhắn này sẽ được gửi kèm thông báo cho người phê duyệt.</p></> : <><textarea readOnly rows={3} aria-label="Ghi chú đã gửi người phê duyệt" value={String(analysis?.buyer_confirmation?.note || "Không có ghi chú bổ sung.")} /><p className="workflow-readonly">🔒 Hồ sơ đã gửi duyệt hoặc đang ở chế độ chỉ đọc.</p></>}</article>{error && <p className="error" role="alert">{error}</p>}
  </section>;
}
