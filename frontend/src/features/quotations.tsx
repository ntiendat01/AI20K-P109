import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiRequest } from "../api";
import { useAuth } from "../AuthProvider";
import { DEMO_QUOTATION_FILENAMES, loadDemoQuotations } from "../demoSamples";
import { Icon } from "../Icon";
import type { JsonObject, PurchaseRequest, Quotation, QuotationItem } from "../types";
import { ConfirmDialog, ErrorState, LoadingState, StatusPill } from "../ui";
import { formatComparisonMoney, formatReviewMoney, parseReviewMoney } from "../utils";
import { SourceReview } from "./SourceReview";

type QueueFile = { file: File; status: "pending" | "uploading" | "done" | "failed"; error?: string };
type EditableQuoteItem = QuotationItem & { localId: string; sourceIndex?: number; sourceName?: string; sourceUnit?: string };
const editItem = (item: Partial<QuotationItem> = {}): EditableQuoteItem => ({ ...item, localId: crypto.randomUUID(), product_code: item.product_code || "", product_name: item.product_name || "", unit: item.unit || "", quantity: Number(item.quantity || 1), unit_price: Number(item.unit_price || 0), line_total: Number(item.line_total || 0) });

export function QuotationsPage() {
  const { session } = useAuth();
  const { requestId = "" } = useParams();
  const [request, setRequest] = useState<PurchaseRequest | null>(null);
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [matches, setMatches] = useState<JsonObject | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<QueueFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Quotation | "all" | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = async (keepActive = true) => {
    if (!session) return;
    setLoading(true); setError("");
    try {
      const [pr, quotes] = await Promise.all([apiRequest<PurchaseRequest>(`/prs/${encodeURIComponent(requestId)}`, session), apiRequest<Quotation[]>(`/prs/${encodeURIComponent(requestId)}/quotations`, session)]);
      setRequest(pr); setQuotations(quotes);
      const complete = quotes.length > 0 && quotes.every((quote) => quote.status === "confirmed");
      setMatches(complete ? await apiRequest<JsonObject>(`/prs/${encodeURIComponent(requestId)}/fuzzy-matches`, session) : null);
      if (!keepActive || !activeId || !quotes.some((quote) => quote.id === activeId)) setActiveId(quotes.find((quote) => quote.status === "unconfirmed")?.id || null);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được báo giá."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(false); }, [requestId, session]);
  const confirmed = quotations.filter((quote) => quote.status === "confirmed").length;
  const complete = quotations.length > 0 && confirmed === quotations.length;

  const addFiles = (files: FileList | File[]) => {
    const capacity = Math.max(0, 5 - quotations.length - queue.length);
    const next: QueueFile[] = [];
    let rejected = 0;
    Array.from(files).forEach((file) => {
      if (!file.name.toLowerCase().endsWith(".pdf") || file.size > 5 * 1024 * 1024 || next.length >= capacity) { rejected += 1; return; }
      if (queue.some((entry) => entry.file.name === file.name && entry.file.size === file.size)) return;
      next.push({ file, status: "pending" });
    });
    setQueue((current) => [...current, ...next]);
    setError(rejected ? `${rejected} file bị bỏ qua vì sai định dạng, vượt 5 MB hoặc giới hạn 5 báo giá.` : "");
  };
  const drop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); addFiles(event.dataTransfer.files); };
  const upload = async (entries = queue) => {
    if (!session || !entries.length) return;
    setUploading(true); setError("");
    const results: QueueFile[] = [];
    for (const [index, entry] of entries.entries()) {
      setQueue((current) => current.map((item, i) => i === index ? { ...item, status: "uploading" } : item));
      const body = new FormData(); body.append("file", entry.file); body.append("extraction_mode", "agent");
      try { await apiRequest(`/prs/${encodeURIComponent(requestId)}/quotations`, session, { method: "POST", body }); results.push({ ...entry, status: "done" }); }
      catch (exception) { results.push({ ...entry, status: "failed", error: exception instanceof Error ? exception.message : "Lỗi upload" }); }
      setQueue((current) => current.map((item, i) => i === index ? results[index] : item));
    }
    setQueue(results);
    const failures = results.filter((item) => item.status === "failed");
    if (failures.length) setError(failures.map((item) => `${item.file.name}: ${item.error}`).join(" | "));
    else setQueue([]);
    setUploading(false); await load(false);
  };
  const createDemo = async () => {
    if (uploading || queue.length) return;
    setUploading(true); setError("");
    try {
      const existing = new Set(quotations.map((quote) => quote.source_filename));
      const missing = DEMO_QUOTATION_FILENAMES.filter((filename) => !existing.has(filename));
      if (!missing.length) { setError("Hai báo giá mẫu đã được tải lên PR này."); return; }
      if (missing.length > 5 - quotations.length) { setError("Không đủ chỗ cho báo giá mẫu. PR chỉ nhận tối đa 5 báo giá."); return; }
      const entries: QueueFile[] = (await loadDemoQuotations()).filter((file) => missing.some((filename) => filename === file.name)).map((file) => ({ file, status: "pending" }));
      setQueue(entries);
      setError("");
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được báo giá mẫu."); }
    finally { setUploading(false); }
  };
  const remove = async () => {
    if (!session || !deleteTarget) return;
    const targets = deleteTarget === "all" ? quotations : [deleteTarget];
    setDeleteTarget(null); setError("");
    try { for (const quote of targets) await apiRequest(`/quotations/${encodeURIComponent(quote.id)}`, session, { method: "DELETE" }); await load(false); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể xóa báo giá."); await load(false); }
  };
  if (loading && !request) return <LoadingState label="Đang tải báo giá…" />;
  if (error && !request) return <ErrorState message={error} onRetry={() => void load(false)} />;
  if (!request) return null;
  return <><Link className="back-link" to={`/purchase-requests/${request.id}`}><Icon name="arrow-left" className="button-icon" /> Quay lại PR</Link><section className="quote-header"><div><p className="detail-code">{request.code}</p><h2>{request.category}</h2><p>{quotations.length ? complete ? `Đã đối chiếu và xác nhận ${confirmed}/${quotations.length} báo giá. Bảng tổng hợp đã sẵn sàng.` : `Đã xác nhận ${confirmed}/${quotations.length} báo giá.` : "Tải lên báo giá để bắt đầu đối chiếu."}</p></div><StatusPill status={request.status} /></section>
    <section className="quote-layout"><div className="quote-upload-panel"><h3>Tải báo giá</h3><p>Kéo thả hoặc chọn file PDF. Tối đa 5 file, mỗi file ≤ 5 MB.</p><div className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={drop}><div className="drop-zone-content"><div className="drop-zone-icon"><Icon name="upload" /></div><p className="drop-zone-label">Kéo thả file vào đây</p><p className="drop-zone-hint">hoặc</p><button className="secondary drop-zone-browse" type="button" onClick={() => fileInput.current?.click()}>Chọn file từ máy</button></div><input ref={fileInput} type="file" accept=".pdf,application/pdf" multiple hidden onChange={(event) => { if (event.target.files) addFiles(event.target.files); event.target.value = ""; }} /><div className="workflow-demo-actions"><button className="secondary" type="button" disabled={uploading || !!queue.length || quotations.length >= 5} onClick={() => void createDemo()}>{uploading ? "Đang tải báo giá mẫu…" : "Tạo dữ liệu mẫu"}</button><span>Nạp 2 file PDF báo giá mẫu. Nhấn “Tải lên & trích xuất” để bắt đầu xử lý.</span></div></div><div className="file-queue">{queue.map((entry, index) => <div key={`${entry.file.name}-${index}`} className={`file-queue-item ${entry.status}`}><div className="file-queue-info"><span className="file-queue-icon"><Icon name="file-text" /></span><div><strong>{entry.file.name}</strong><span>{(entry.file.size / 1024).toFixed(1)} KB · {entry.status === "pending" ? "Sẵn sàng" : entry.status === "uploading" ? "Đang xử lý…" : entry.status === "done" ? "Hoàn tất" : "Lỗi"}</span></div></div>{!uploading && <button className="file-queue-remove" onClick={() => setQueue((current) => current.filter((_, i) => i !== index))}><Icon name="close" /></button>}</div>)}</div><p className="error" role="alert">{error}</p><button className="inline-primary" disabled={!queue.length || uploading} onClick={() => void upload()}>{uploading ? "Đang tải lên & trích xuất…" : `Tải lên${queue.length ? ` ${queue.length} file` : ""} & trích xuất`}</button></div>
      <div className="quote-list-panel"><div className="quote-list-heading"><h3>Báo giá đã tải lên</h3>{quotations.length > 0 && <button className="quote-delete-all" onClick={() => setDeleteTarget("all")}>Xóa hết</button>}</div>{quotations.length ? quotations.map((quote) => <article key={quote.id} className="quote-record"><button className="quote-row" onClick={() => setActiveId(quote.id)}><div><strong>{quote.supplier_name}</strong><span>{quote.source_filename} · {quote.items.length} dòng hàng{quote.cache_hit ? " · dùng cache" : ""}</span></div><span className={`quote-state ${quote.status}`}>{quote.status === "confirmed" ? "Đã xác nhận" : "Cần xác nhận"}</span><span className="row-arrow"><Icon name="chevron-right" /></span></button><button className="quote-delete" onClick={() => setDeleteTarget(quote)}>Xóa</button></article>) : <p className="subtle-empty">Chưa có báo giá nào.</p>}</div></section>
    <section id="quote-editor" aria-live="polite">{activeId ? <QuotationEditor session={session!} quotationId={activeId} allQuotations={quotations} onChanged={() => void load(false)} onSelect={setActiveId} /> : complete ? <ReviewComplete requestId={request.id} confirmed={confirmed} /> : null}</section>
    {complete && matches && <FuzzyComparison session={session!} quotations={quotations} matchResults={matches} onChanged={() => void load(true)} />}
    {deleteTarget && <ConfirmDialog title={deleteTarget === "all" ? "Xóa toàn bộ báo giá?" : "Xóa báo giá này?"} description={deleteTarget === "all" ? `${quotations.length} file cùng dữ liệu trích xuất sẽ bị xóa vĩnh viễn.` : `File “${deleteTarget.source_filename}” và dữ liệu trích xuất sẽ bị xóa vĩnh viễn.`} confirmLabel={deleteTarget === "all" ? "Xóa hết" : "Xóa"} onCancel={() => setDeleteTarget(null)} onConfirm={() => void remove()} />}
  </>;
}

function ReviewComplete({ requestId, confirmed }: { requestId: string; confirmed: number }) {
  const navigate = useNavigate();
  return <section className="editor-card review-complete-card"><div className="review-complete-mark"><Icon name="check" /></div><div><p className="section-kicker">Đã hoàn tất rà soát</p><h3>Đã xác nhận {confirmed} báo giá</h3><p>Bảng tổng hợp đã được lập từ dữ liệu xác nhận và hiển thị ngay bên dưới.</p><div className="form-actions"><button className="inline-primary" onClick={() => document.getElementById("quote-comparison-title")?.scrollIntoView({ behavior: "smooth" })}>Xem bảng tổng hợp <Icon name="arrow-down" className="button-icon" /></button><button className="secondary" onClick={() => navigate(`/purchase-requests/${requestId}/comparison`)}>Phân tích &amp; đề xuất NCC <Icon name="arrow-right" className="button-icon" /></button></div></div></section>;
}

export function QuotationEditor({ session, quotationId, allQuotations, onChanged, onSelect, onReopen, onReextract, request, matchResults, onDirty, submitRequest = false, onSubmitRequestHandled }: {
  session: NonNullable<ReturnType<typeof useAuth>["session"]>; quotationId: string; allQuotations: Quotation[];
  onChanged: () => void; onSelect: (id: string | null) => void; onReopen?: (quote: Quotation) => void;
  onReextract?: (quote: Quotation) => void; request?: PurchaseRequest; matchResults?: JsonObject | null; onDirty?: () => void; submitRequest?: boolean; onSubmitRequestHandled?: () => void;
}) {
  const navigate = useNavigate();
  const [quote, setQuote] = useState<Quotation | null>(null);
  const [items, setItems] = useState<EditableQuoteItem[]>([]);
  const [form, setForm] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  useEffect(() => {
    if (!submitRequest) return;
    if (!loading && quote) {
      onSubmitRequestHandled?.();
      const form = document.getElementById("quote-confirm-form") as HTMLFormElement | null;
      form?.requestSubmit();
    }
  }, [submitRequest, loading, quote, onSubmitRequestHandled]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setQuote(null);
    void apiRequest<Quotation>(`/quotations/${encodeURIComponent(quotationId)}`, session).then((value) => {
      if (!active) return;
      setQuote(value);
      setItems(value.items.length ? value.items.map((item, index) => ({ ...editItem(item), sourceIndex: index, sourceName: item.product_name, sourceUnit: item.unit || "" })) : [editItem()]);
      setForm({ supplier_name: value.supplier_name || "", delivery_time: value.delivery_time || "", payment_terms: value.payment_terms || "", currency: value.currency || "VND", vat_rate: value.vat_rate == null ? "" : String(Number(value.vat_rate) * 100), vat_included: value.vat_included == null ? "" : String(value.vat_included), shipping_fee: value.shipping_fee == null ? "" : String(value.shipping_fee), lead_time_days: value.lead_time_days == null ? "" : String(value.lead_time_days), warranty_months: value.warranty_months == null ? "" : String(value.warranty_months) });
    }).catch((exception) => { if (active) setError(exception instanceof Error ? exception.message : "Không tải được báo giá."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [quotationId, session]);
  if (loading) return <LoadingState label="Đang tải dữ liệu trích xuất…" />;
  if (!quote) return <ErrorState message={error || "Không tìm thấy báo giá."} />;
  const update = (name: string, value: string) => setForm((current) => ({ ...current, [name]: value }));
  const updateItem = (localId: string, patch: Partial<EditableQuoteItem>) => {
    onDirty?.();
    setItems((current) => current.map((item) => {
      if (item.localId !== localId) return item;
      const next = { ...item, ...patch };
      if (patch.product_name !== undefined || patch.unit !== undefined) { next.matched_pr_item_id = null; next.match_status = null; }
      if (patch.quantity !== undefined || patch.unit_price !== undefined) next.line_total = Number((Number(next.quantity) * Number(next.unit_price || 0)).toFixed(2));
      return next;
    }));
  };
  const pending = allQuotations.filter((quotation) => quotation.status === "unconfirmed");
  if (quote.status === "confirmed") return <section className="editor-card"><h3>Đã xác nhận</h3><p>Báo giá của {quote.supplier_name} đã được lưu.</p><div className="form-actions"><button className="inline-primary" onClick={() => navigate(`/purchase-requests/${quote.pr_id}/workflow/4`)}>Xem bảng tổng hợp</button><button className="secondary" disabled={working} onClick={async () => {
    if (onReopen) { onReopen(quote); return; }
    setWorking(true); setError("");
    try { await apiRequest(`/quotations/${encodeURIComponent(quote.id)}/reopen`, session, { method: "POST" }); onChanged(); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể mở lại báo giá."); }
    finally { setWorking(false); }
  }}>Sửa dữ liệu và phân tích lại</button><button className="secondary" onClick={() => setSourceOpen(true)}>Mở file gốc</button></div>{error && <p className="error" role="alert">{error}</p>}{sourceOpen && <SourceReview session={session} quotation={quote} onClose={() => setSourceOpen(false)} />}</section>;
  const prItems = request?.items?.length ? request.items.map((item, index) => ({ id: item.item_id || item.id || `${request.id}:item:${item.order_index ?? index}`, name: item.product_name })) : request ? [{ id: `${request.id}:main`, name: request.category }] : [];
  const reviewedMatch = (item: EditableQuoteItem) => {
    const unchanged = item.product_name === item.sourceName && (item.unit || "") === item.sourceUnit;
    const suggestion = unchanged ? (matchResults?.results || []).find((result: JsonObject) => result.quote_item_id === `${quote.id}:item:${item.sourceIndex}`) : undefined;
    const status = String(item.match_status || suggestion?.status || suggestion?.best_match?.status || "UNMATCHED").toUpperCase();
    const targetId = item.match_status ? item.matched_pr_item_id : suggestion?.best_match?.pr_item_id;
    return { status, targetId, target: prItems.find((row) => row.id === targetId), score: suggestion?.best_match?.score };
  };
  const unresolved = request ? items.filter((item) => { const match = reviewedMatch(item); return match.status !== "REJECTED" && (!match.target || !["AUTO_MATCHED", "MANUAL_MATCHED"].includes(match.status)); }).length : 0;
  const subtotal = items.reduce((sum, item) => sum + Number(item.line_total || 0), 0);
  const factor = form.vat_included === "true" ? 1 : form.vat_rate === "" ? null : 1 + Number(form.vat_rate) / 100;
  const totalsReady = form.vat_included !== "" && form.shipping_fee !== "" && factor != null;
  const goodsTotal = totalsReady ? Number((subtotal * factor!).toFixed(2)) : null;
  const shippingTotal = totalsReady ? Number((Number(form.shipping_fee) * factor!).toFixed(2)) : null;
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    if (request && (!matchResults || unresolved)) { setError("Đối chiếu tên sản phẩm với yêu cầu PR ở từng dòng trước khi duyệt file."); return; }
    const required = ["vat_rate", "vat_included", "shipping_fee", "lead_time_days", "warranty_months"];
    if (required.some((name) => form[name] === "")) { setError("Hoàn tất VAT, phí giao hàng, thời gian giao và bảo hành trước khi xác nhận."); return; }
    setWorking(true);
    try {
      const confirmed = await apiRequest<Quotation>(`/quotations/${encodeURIComponent(quote.id)}/confirm`, session, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supplier_name: form.supplier_name, delivery_time: form.delivery_time, payment_terms: form.payment_terms, currency: form.currency, vat_rate: Number(form.vat_rate) / 100, vat_included: form.vat_included === "true", shipping_fee: Number(form.shipping_fee), lead_time_days: Number(form.lead_time_days), warranty_months: Number(form.warranty_months), goods_total_including_tax: goodsTotal, shipping_total_including_tax: shippingTotal,
          items: items.map(({ localId: _, sourceIndex: _index, sourceName: _name, sourceUnit: _unit, ...item }, index) => {
            const match = reviewedMatch(items[index]);
            return request ? { ...item, matched_pr_item_id: match.status === "REJECTED" ? null : match.targetId, match_status: match.status.toLowerCase() } : item;
          }),
        }),
      });
      const currentIndex = allQuotations.findIndex((value) => value.id === quote.id);
      const ordered = [...allQuotations.slice(currentIndex + 1), ...allQuotations.slice(0, currentIndex)];
      onSelect(ordered.find((value) => value.status === "unconfirmed")?.id || quote.id);
      setQuote(confirmed); onChanged();
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể xác nhận báo giá."); }
    finally { setWorking(false); }
  };
  return <section className="editor-card extraction-editor">
    <header className="extraction-pane-heading"><h3 className="text-title">Dữ liệu bóc tách được</h3><span className="text-small">Rê chuột vào sản phẩm để đối soát file gốc</span></header>
    <div className="extraction-editor-body">
      {!request && <div className="form-actions"><button className="secondary" type="button" disabled={working} onClick={async () => {
        if (onReextract) { onReextract(quote); return; }
        setWorking(true); setError("");
        try { await apiRequest(`/quotations/${encodeURIComponent(quote.id)}/re-extract`, session, { method: "POST" }); onChanged(); }
        catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể trích xuất lại."); }
        finally { setWorking(false); }
      }}>Trích xuất lại</button></div>}
      <div className="extraction-review-status"><span>Đã duyệt {allQuotations.length - pending.length}/{allQuotations.length} file</span>{request && <span>{!matchResults ? "Đang đối chiếu tên sản phẩm…" : unresolved ? `${unresolved} dòng cần xác nhận khớp tên` : "Đã đối chiếu tên sản phẩm"}</span>}</div>
      {!!quote.extraction_warnings?.length && <div className="warning-box">{quote.extraction_warnings.map((warning) => <div key={warning}>{warning}</div>)}</div>}
      <form id="quote-confirm-form" onSubmit={(event) => void submit(event)} onChangeCapture={() => onDirty?.()}>
        <fieldset disabled={working} className="extraction-fields">
          <div className="extraction-general-fields">
            <label>Nhà cung cấp<input value={form.supplier_name} onChange={(event) => update("supplier_name", event.target.value)} required minLength={2} /></label>
            <label>Tiền tệ<input value={form.currency} onChange={(event) => update("currency", event.target.value)} required /></label>
            <label className="extraction-wide">Điều khoản thanh toán<input value={form.payment_terms} onChange={(event) => update("payment_terms", event.target.value)} /></label>
          </div>
          <div className="items-heading"><h4 className="text-title">Danh mục sản phẩm trích xuất</h4><button type="button" className="secondary" onClick={() => { setItems((current) => [...current, editItem()]); onDirty?.(); }}><Icon name="plus" /> Thêm dòng</button></div>
          <div className="extraction-item-list">{items.map((item, index) => {
            const match = reviewedMatch(item);
            const settled = ["AUTO_MATCHED", "MANUAL_MATCHED"].includes(match.status) && !!match.target;
            return <article className="extraction-item" data-source-index={item.sourceIndex} key={item.localId}>
              <div className="extraction-item-heading"><strong>{index + 1}. {request ? match.status === "REJECTED" ? "Sản phẩm ngoài yêu cầu PR" : match.target?.name || "Chưa ghép với sản phẩm yêu cầu" : item.product_name || "Sản phẩm mới"}</strong><button type="button" className="workflow-icon-button danger" aria-label={`Xóa dòng ${index + 1}`} onClick={() => { setItems((current) => current.filter((row) => row.localId !== item.localId)); onDirty?.(); }}><Icon name="close" /></button></div>
              <label>Tên trên báo giá<input value={item.product_name} onChange={(event) => updateItem(item.localId, { product_name: event.target.value })} required /></label>
              {request && <div className="extraction-match">
                <span className={`extraction-match-status ${settled ? "matched" : "unresolved"}`}>{settled ? match.status === "MANUAL_MATCHED" ? "✓ Đã xác nhận khớp tên" : "✓ Tự động khớp tên" : match.status === "REJECTED" ? "Đã tách riêng khỏi yêu cầu PR" : "Cần xác nhận khớp tên"}{match.score != null && match.status !== "MANUAL_MATCHED" && match.status !== "REJECTED" ? ` · Độ khớp ${Math.round(Number(match.score) * 100)}%` : ""}</span>
                {match.status === "SUGGESTED" && match.target && <button className="secondary" type="button" onClick={() => updateItem(item.localId, { match_status: "MANUAL_MATCHED", matched_pr_item_id: match.targetId })}>Xác nhận khớp</button>}
                <details className="extraction-match-controls" open={!settled && match.status !== "REJECTED"}><summary>{settled || match.status === "REJECTED" ? "Thay đổi đối chiếu sản phẩm" : "Chọn sản phẩm yêu cầu hoặc tách riêng"}</summary><label>Đối chiếu với yêu cầu PR<select value={match.status === "REJECTED" ? "__rejected" : settled ? match.targetId : ""} onChange={(event) => updateItem(item.localId, { match_status: event.target.value === "__rejected" ? "REJECTED" : event.target.value ? "MANUAL_MATCHED" : "UNMATCHED", matched_pr_item_id: event.target.value === "__rejected" ? null : event.target.value || null })}><option value="">Chọn sản phẩm yêu cầu…</option>{prItems.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}<option value="__rejected">Tách riêng — ngoài yêu cầu PR</option></select></label></details>
              </div>}
              <div className="extraction-item-fields">
                <label>Mã hàng<input value={item.product_code} onChange={(event) => updateItem(item.localId, { product_code: event.target.value })} /></label>
                <label>Đơn vị<input value={item.unit} onChange={(event) => updateItem(item.localId, { unit: event.target.value })} /></label>
                <label>Số lượng<input type="number" min="1" step="1" value={item.quantity} onChange={(event) => updateItem(item.localId, { quantity: Number(event.target.value) })} required /></label>
                <label>Đơn giá ({form.currency})<input className={item.unit_price > 0 ? "" : "extraction-missing"} value={item.unit_price > 0 ? formatReviewMoney(item.unit_price) : ""} placeholder="Chưa có giá" inputMode="decimal" onChange={(event) => updateItem(item.localId, { unit_price: parseReviewMoney(event.target.value) })} required /></label>
              </div><div className="extraction-line-total"><label>Thành tiền ({form.currency})<input aria-label={`Thành tiền dòng ${index + 1}`} value={formatReviewMoney(item.line_total)} inputMode="decimal" onChange={(event) => updateItem(item.localId, { line_total: parseReviewMoney(event.target.value) })} required /></label></div>
            </article>;
          })}</div>
          <fieldset className="extraction-finance"><legend>Thuế, chi phí & điều kiện giao hàng</legend><div className="extraction-general-fields">
            <label>VAT (%) *<input type="number" min="0" max="100" step="0.01" value={form.vat_rate} onChange={(event) => update("vat_rate", event.target.value)} required /></label>
            <label>Giá và phí đã gồm VAT? *<select value={form.vat_included} onChange={(event) => update("vat_included", event.target.value)} required><option value="">Chưa xác định</option><option value="false">Chưa gồm VAT</option><option value="true">Đã gồm VAT</option></select></label>
            <label>Phí giao hàng *<input type="number" min="0" step="0.01" value={form.shipping_fee} onChange={(event) => update("shipping_fee", event.target.value)} required /></label>
            <label>Giao sau xác nhận đơn (ngày) *<input type="number" min="0" step="1" value={form.lead_time_days} onChange={(event) => update("lead_time_days", event.target.value)} required /></label>
            <label>Bảo hành (tháng) *<input type="number" min="0" step="1" value={form.warranty_months} onChange={(event) => update("warranty_months", event.target.value)} required /></label>
          </div></fieldset>
          <div className="extraction-total" role="status"><div><span>Tổng tiền gồm VAT & phí</span><small>{form.vat_included === "true" ? "Đơn giá đã gồm VAT" : `VAT ${form.vat_rate || "—"}%`}</small></div><strong>{goodsTotal == null ? "Chưa đủ dữ liệu" : `${formatReviewMoney(goodsTotal + Number(shippingTotal))} ${form.currency}`}</strong></div>
          {error && <p className="error" role="alert">{error}</p>}
          
        </fieldset>
      </form>
    </div>{sourceOpen && <SourceReview session={session} quotation={quote} onClose={() => setSourceOpen(false)} />}
  </section>;
}

const matchStatus = (match?: JsonObject) => String(match?.status || match?.best_match?.status || "unmatched").toLowerCase();
const comparable = (match?: JsonObject) => ["auto_matched", "manual_matched"].includes(matchStatus(match));
const itemId = (quotationId: string, index: number) => `${quotationId}:item:${index}`;

export function FuzzyComparison({ session, quotations, matchResults, onChanged, allowMatchMutation = true }: { session: NonNullable<ReturnType<typeof useAuth>["session"]>; quotations: Quotation[]; matchResults: JsonObject; onChanged: () => void; allowMatchMutation?: boolean }) {
  const [query, setQuery] = useState("");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const byId = new Map<string, JsonObject>((matchResults.results || []).map((result: JsonObject) => [result.quote_item_id, result]));
  const products = new Map<string, JsonObject>();
  quotations.forEach((quotation) => quotation.items.forEach((item, index) => { const id = itemId(quotation.id, index); const match = byId.get(id); const candidate = match?.best_match; const key = ["auto_matched", "suggested", "manual_matched"].includes(matchStatus(match)) && candidate?.pr_item_id ? `pr:${candidate.pr_item_id}` : `quote:${id}`; if (!products.has(key)) products.set(key, { name: candidate?.pr_item_name || item.product_name, unit: item.unit, quantity: item.quantity, terms: [candidate?.pr_item_name, item.product_name, item.product_code].filter(Boolean).join(" ").toLowerCase(), offers: {} }); products.get(key)!.offers[quotation.id] = { quotationId: quotation.id, id, item, match }; }));
  const rows = [...products.values()].filter((product) => !query || product.terms.includes(query.toLowerCase()));
  const act = async (offer: JsonObject, action: string, prItemId?: string) => {
    if (!allowMatchMutation) { setError("Chức năng ghép mặt hàng hiện đang bị tắt."); return; }
    if (action !== "REJECT" && !prItemId) { setError("Chọn mặt hàng PR trước khi ghép."); return; }
    setError("");
    try { await apiRequest(`/quotations/${encodeURIComponent(offer.quotationId)}/items/${encodeURIComponent(offer.id)}/confirm-match`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pr_item_id: prItemId || null, action }) }); onChanged(); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể cập nhật fuzzy match."); }
  };
  return <><section className="comparison-panel"><div className="comparison-heading"><div><p className="section-kicker">Đối chiếu fuzzy matching</p><h3 id="quote-comparison-title">Bảng so sánh báo giá</h3><p>Tên hàng theo mặt hàng PR do fuzzy matching chọn. Giá tốt nhất và tổng chỉ tính các dòng đã ghép.</p></div><span><b>{rows.length}</b> mặt hàng</span></div><p className="error">{error}</p><div className="comparison-toolbar"><label className="comparison-search"><Icon name="search" /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm theo tên mặt hàng…" /></label><div className="supplier-chips">{quotations.map((quote) => <button key={quote.id} className="supplier-chip" aria-pressed={!hidden.has(quote.id)} onClick={() => setHidden((current) => { const next = new Set(current); next.has(quote.id) ? next.delete(quote.id) : next.add(quote.id); return next; })}><span>◉</span>{quote.supplier_name}</button>)}</div></div><div className="comparison-scroll"><table className="comparison-table"><thead><tr><th rowSpan={2}>L/I</th><th rowSpan={2}>Mặt hàng PR</th><th rowSpan={2}>Đơn vị</th><th rowSpan={2}>SL</th>{quotations.filter((quote) => !hidden.has(quote.id)).map((quote) => <th key={quote.id} colSpan={2}>{quote.supplier_name}<small className="comparison-status confirmed">Đã xác nhận</small></th>)}</tr><tr>{quotations.filter((quote) => !hidden.has(quote.id)).flatMap((quote) => [<th key={`${quote.id}-unit`}>Đơn giá</th>, <th key={`${quote.id}-total`}>Tổng cộng</th>])}</tr></thead><tbody>{rows.map((product, index) => <tr key={`${product.name}-${index}`}><td>{index + 1}</td><th>{product.name}</th><td>{product.unit || "—"}</td><td>{product.quantity ?? "—"}</td>{quotations.filter((quote) => !hidden.has(quote.id)).flatMap((quote) => { const offer = product.offers[quote.id] as JsonObject | undefined; if (!offer) return [<td key={`${quote.id}-u`}>—</td>, <td key={`${quote.id}-t`}>—</td>]; const status = matchStatus(offer.match); const candidate = offer.match?.best_match; return [<td key={`${quote.id}-u`}><strong>{formatComparisonMoney(offer.item.unit_price)}</strong><div className={`fuzzy-match-cell ${status}`}><span className={`fuzzy-match-status ${status}`}>{status === "suggested" ? "Cần xác nhận" : status === "unmatched" ? "Chưa khớp" : status === "manual_matched" ? "Đã ghép" : "Tự động ghép"}</span><small className="comparison-source-name">Tên báo giá: {offer.item.product_name}</small>{status === "suggested" && candidate && <div className="fuzzy-match-actions"><button className="secondary" onClick={() => void act(offer, "CONFIRM", candidate.pr_item_id)}>Gộp</button><button className="secondary" onClick={() => void act(offer, "REJECT")}>Tách riêng</button></div>}{status === "unmatched" && !!offer.match?.candidates?.length && <ManualMatch candidates={offer.match.candidates} onMatch={(id) => void act(offer, "MAP_TO_NEW", id)} />}</div></td>, <td key={`${quote.id}-t`}>{formatComparisonMoney(offer.item.line_total)}</td>]; })}</tr>)}</tbody><tfoot><tr><th colSpan={4}>TỔNG ĐÃ GHÉP</th>{quotations.filter((quote) => !hidden.has(quote.id)).map((quote) => <td key={quote.id} colSpan={2}>{formatComparisonMoney(rows.reduce((sum, product) => { const offer = product.offers[quote.id]; return sum + (offer && comparable(offer.match) ? Number(offer.item.line_total) || 0 : 0); }, 0))}</td>)}</tr></tfoot></table></div></section>
    <section className="commercial-panel"><h3>Đánh giá thương mại</h3><div className="comparison-scroll"><table className="commercial-table"><thead><tr><th>Nhà cung cấp</th><th>Thời gian giao hàng</th><th>Điều khoản thanh toán</th><th>Bảo hành</th></tr></thead><tbody>{quotations.map((quote) => <tr key={quote.id}><th>{quote.supplier_name}</th><td>{quote.delivery_time || "—"}</td><td>{quote.payment_terms || "—"}</td><td>{quote.warranty || "—"}</td></tr>)}</tbody></table></div></section></>;
}

function ManualMatch({ candidates, onMatch }: { candidates: JsonObject[]; onMatch: (id: string) => void }) {
  const [selected, setSelected] = useState("");
  return <div className="fuzzy-match-actions"><select value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">Chọn mặt hàng PR…</option>{candidates.map((candidate) => <option key={candidate.pr_item_id} value={candidate.pr_item_id}>{candidate.pr_item_name}{Number.isFinite(Number(candidate.score)) ? ` · ${Math.round(Number(candidate.score) * 100)}%` : ""}</option>)}</select><button className="secondary" onClick={() => selected && onMatch(selected)}>Ghép</button></div>;
}
