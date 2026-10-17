import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiBlob, apiRequest, ApiError } from "../api";
import { useAuth } from "../AuthProvider";
import { ANALYSIS_POLL_INTERVAL_MS, ANALYSIS_POLL_MAX_WAIT_MS } from "../config";
import { Icon } from "../Icon";
import { setFlash, takeFlash } from "../session";
import type { JsonObject } from "../types";
import { ErrorState, Flash, LoadingState, StatusPill } from "../ui";
import { formatBudget, formatComparisonMoney, formatDate } from "../utils";

const statusCopy: Record<string, string> = {
  not_started: "Chưa phân tích", running: "Đang phân tích", awaiting_buyer_review: "Đề xuất đã kiểm chứng",
  pending_manager_approval: "Đang chờ Quản lý phê duyệt", needs_input: "Cần bổ sung dữ liệu", repairable: "Đề xuất cần sửa",
  technical_failure: "Phân tích chưa thành công", exception_required: "Cần quyết định ngoại lệ", no_viable_supplier: "Chưa có NCC đáp ứng",
  stale: "Cần phân tích lại", approved: "Đã duyệt", rejected: "Đã từ chối", awaiting_input: "Chờ cập nhật dữ liệu", awaiting_repair: "Chờ sửa đề xuất",
};

export function ComparisonPage() {
  const { session } = useAuth();
  const { requestId = "" } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<JsonObject | null>(null);
  const [review, setReview] = useState<JsonObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [showAnalysisLoading, setShowAnalysisLoading] = useState(false);
  const [managerNote, setManagerNote] = useState("");
  const [decisionOpen, setDecisionOpen] = useState<"approve" | "reject" | null>(null);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const flash = useMemo(() => takeFlash(), []);

  const load = useCallback(async () => {
    if (!session) return;
    setError("");
    try {
      const result = await apiRequest<JsonObject>(`/prs/${encodeURIComponent(requestId)}/analysis`, session);
      setRun(result);
      const shouldFetch = result.status === "awaiting_buyer_review" || (result.status === "pending_manager_approval" && session.user.role === "manager");
      setReview(shouldFetch && result.recommendation_id ? await apiRequest<JsonObject>(`/recommendations/${result.recommendation_id}/review`, session) : result.review || null);
      if (result.status !== "running") setShowAnalysisLoading(false);
    } catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được kết quả phân tích."); }
    finally { setLoading(false); }
  }, [requestId, session]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (run?.status !== "running" || !session) return;
    const controller = new AbortController();
    let timer = 0;
    let interval = ANALYSIS_POLL_INTERVAL_MS;
    const started = Date.now();
    const poll = async () => {
      if (controller.signal.aborted) return;
      if (Date.now() - started > ANALYSIS_POLL_MAX_WAIT_MS) { setError("Phân tích đang lâu hơn dự kiến. Hãy tải lại trạng thái hoặc thử lại sau."); setShowAnalysisLoading(false); return; }
      try {
        const result = await apiRequest<JsonObject>(`/prs/${encodeURIComponent(requestId)}/analysis`, session, { signal: controller.signal });
        if (result.status !== "running") { setRun(result); await load(); return; }
        interval = Math.min(Math.round(interval * 1.25), 5000); timer = window.setTimeout(poll, interval);
      } catch (exception) { if (!controller.signal.aborted) { setError(exception instanceof Error ? exception.message : "Không cập nhật được trạng thái phân tích."); setShowAnalysisLoading(false); } }
    };
    timer = window.setTimeout(poll, interval);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [run?.status, requestId, session, load]);

  if (loading && !run) return <LoadingState label="Đang tải kết quả phân tích…" />;
  if (error && !run) return <ErrorState message={error} onRetry={() => void load()} retryLabel="Tải lại phân tích" />;
  if (!run) return null;
  const pr = run.pr as JsonObject;
  const names: Record<string, string> = { ...(run.supplier_names || {}) };
  (run.tco_results || []).forEach((item: JsonObject) => { if (!names[item.supplier_id]) names[item.supplier_id] = item.supplier_id; });
  const supplierName = (id: string) => names[id] || "Nhà cung cấp";
  const buyerCanAct = session?.user.role === "procurement" && ["comparing", "awaiting_quotation"].includes(pr.status);
  const repairable = ["repairable", "technical_failure", "awaiting_repair", "rejected", "needs_input", "not_started", "stale"].includes(run.status);
  const canSubmit = review?.status === "proposed" && run.status === "awaiting_buyer_review" && session?.user.role === "procurement" && pr.status === "comparing";

  const analyze = async () => {
    if (!session) return; setWorking(true); setShowAnalysisLoading(true); setError("");
    try { const started = await apiRequest<JsonObject>(`/prs/${encodeURIComponent(requestId)}/analysis`, session, { method: "POST" }); setRun(started); if (started.status !== "running") await load(); }
    catch (exception) { if (exception instanceof ApiError && exception.status === 422) await load(); else { setError(exception instanceof Error ? exception.message : "Không thể bắt đầu phân tích."); setShowAnalysisLoading(false); } }
    finally { setWorking(false); }
  };
  const submitApproval = async () => {
    if (!session) return; setWorking(true); setError("");
    try { await apiRequest(`/analyses/${encodeURIComponent(run.analysis_id)}/submit-approval`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); setFlash("Đã gửi đề xuất cho Quản lý phê duyệt."); await load(); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không thể gửi duyệt."); }
    finally { setWorking(false); }
  };
  const decide = async (decision: "approve" | "reject") => {
    if (!session || !run.recommendation_id) return;
    if (decision === "reject" && !managerNote.trim()) { setError("Vui lòng nhập lý do từ chối."); return; }
    setWorking(true); setError("");
    const key = `review:${session.user.id}:${run.recommendation_id}:${run.recommendation_version}:${decision}`;
    let payload = JSON.parse(sessionStorage.getItem(key) || "null");
    if (!payload) { payload = { feedback_id: crypto.randomUUID(), recommendation_id: run.recommendation_id, recommendation_version: run.recommendation_version, idempotency_key: crypto.randomUUID(), decision, note: managerNote.trim(), acknowledged_uncertainty_ids: acknowledged }; sessionStorage.setItem(key, JSON.stringify(payload)); }
    try { await apiRequest<JsonObject>(`/recommendations/${run.recommendation_id}/feedback`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); setDecisionOpen(null); setFlash(decision === "approve" ? "Đã phê duyệt và tạo PO nháp." : "Đã từ chối đề xuất."); await load(); }
    catch (exception) { if (exception instanceof ApiError && [400, 403, 409, 422].includes(exception.status)) sessionStorage.removeItem(key); setError(exception instanceof Error ? exception.message : "Không thể lưu quyết định."); setWorking(false); }
  };

  const message = run.status === "running" ? "Hệ thống đang chuẩn hoá dữ liệu, gọi Agent và kiểm tra bằng chứng. Kết quả sẽ tự cập nhật."
    : run.status === "needs_input" ? (run.message || "Rà soát báo giá đã xác nhận rồi chạy lại phân tích.")
    : run.status === "pending_manager_approval" ? "Đề xuất đã được gửi vào hàng đợi phê duyệt."
    : run.message || "Xác nhận ít nhất 2 báo giá độc lập, VAT/phí, ngày giao và bảo hành để bắt đầu.";
  const manager = session?.user.role === "manager";
  const managerCanDecide = manager && run.status === "pending_manager_approval" && pr.status === "pending_approval" && !!review;
  const selectedId = String(review?.preferred_supplier_id || run.review?.preferred_supplier_id || "");
  const selectedTco = (run.tco_results || []).find((row: JsonObject) => row.supplier_id === selectedId);
  const proposed = Number(selectedTco?.total_tco || 0);
  const budget = Number(pr.estimated_budget || 0);
  const variance = proposed - budget;
  const matrix = run.comparison_matrix || {};
  const matrixIds: string[] = matrix.suppliers || [];
  const criterionLabels: Record<string, string> = { tco: "Tổng giá trị", total_tco: "Tổng giá trị", unit_price: "Đơn giá", lead_time_days: "Thời gian giao hàng", warranty_months: "Bảo hành" };
  return (
    <>
      {!manager && (
        <Link className="back-link" to={`/purchase-requests/${requestId}/quotations`}>
          <Icon name="arrow-left" className="button-icon" /> Báo giá
        </Link>
      )}
      {flash && <Flash {...flash} />}
      <div className="comparison-workspace">
        {manager && (
          <div className="manager-review-actions">
            <Link className="secondary manager-back-btn" to="/requests">
              <Icon name="arrow-left" className="button-icon" /> Danh sách chờ duyệt
            </Link>
            {managerCanDecide && (
              <div className="manager-decision-buttons">
                <button
                  type="button"
                  className="manager-reject-button"
                  onClick={() => { setManagerNote(""); setDecisionOpen("reject"); }}
                >
                  Từ chối đề nghị ✕
                </button>
                <button
                  type="button"
                  className="manager-approve-button"
                  onClick={() => { setManagerNote(""); setDecisionOpen("approve"); }}
                >
                  Phê duyệt đề nghị ✓
                </button>
              </div>
            )}
          </div>
        )}

        {manager && pr.status === "rejected" && (
          <div className="workflow-alert danger manager-status-alert">
            <div className="manager-alert-header">
              <Icon name="alert-triangle" />
              <strong>Hồ sơ chưa được phê duyệt</strong>
            </div>
            <p>{pr.rejection_reason || run.manager_note || "Hồ sơ cần được điều chỉnh trước khi trình duyệt lại."}</p>
          </div>
        )}

        {manager && pr.status === "approved" && (
          <div className="workflow-alert success manager-status-alert">
            <div className="manager-alert-header">
              <Icon name="check" />
              <strong>Hồ sơ đã được phê duyệt chính thức</strong>
            </div>
            {pr.po_id && <p>Hệ thống đã tự động tạo Đơn mua hàng (PO) số <strong>{pr.po_id}</strong>.</p>}
            {run.manager_note && <p>Ý kiến chỉ đạo: <em>{run.manager_note}</em></p>}
          </div>
        )}

        {manager && (
          <article className="workflow-card workflow-proposal-card manager-proposal-card">
            <div className="workflow-card-heading">
              <div>
                <p className="text-overline">TÓM TẮT THẨM ĐỊNH</p>
                <div className="manager-review-title-row">
                  <span className="manager-review-pr-code">{pr.code}</span>
                  <StatusPill status={pr.status} />
                  {pr.po_id && (
                    <Link className="workflow-chip success" to={`/purchase-orders/${pr.po_id}`}>
                      Mã PO: {pr.po_id}
                    </Link>
                  )}
                </div>
                <h2 className="text-title manager-proposal-title">{pr.category}</h2>
              </div>
              {selectedId && <span className="workflow-chip success">✓ Phương án được kiểm chứng</span>}
            </div>
            <div className="manager-financial-grid">
              <div className="manager-financial-item">
                <span className="manager-financial-label">DỰ TOÁN NGÂN SÁCH</span>
                <strong className="manager-financial-value">{formatBudget(budget)}</strong>
                <small className="manager-financial-hint">Ngân sách dự kiến được phê duyệt</small>
              </div>
              <div className="manager-financial-item highlight">
                <span className="manager-financial-label">GIÁ ĐỀ XUẤT ({supplierName(selectedId)})</span>
                <strong className="manager-financial-value">{proposed ? formatBudget(proposed) : "—"}</strong>
                {proposed > 0 && budget > 0 && (
                  <small className={`manager-financial-variance ${variance > 0 ? "over" : "under"}`}>
                    {variance > 0 ? "+" : ""}{(variance / budget * 100).toFixed(1)}% so với dự toán
                  </small>
                )}
              </div>
              <div className="manager-financial-item">
                <span className="manager-financial-label">CHÊNH LỆCH TÀI CHÍNH</span>
                <strong className={`manager-financial-value ${proposed && variance > 0 ? "variance-over" : proposed && variance < 0 ? "variance-under" : ""}`}>
                  {proposed ? `${variance > 0 ? "+" : ""}${formatBudget(variance)}` : "—"}
                </strong>
                <small className="manager-financial-hint">
                  {proposed > 0 ? (variance > 0 ? "Vượt ngân sách dự toán" : "Tiết kiệm so với ngân sách") : "Chưa có đề xuất"}
                </small>
              </div>
            </div>

            <div className="manager-explanation-grid">
              <article className="workflow-card manager-context-card">
                <div className="manager-context-card-header">
                  <span className="manager-context-card-kicker">Ý KIẾN &amp; NHU CẦU</span>
                  <strong className="manager-context-card-name">
                    {pr.metadata?.requested_by || pr.creator_name || "Người yêu cầu"}
                    {pr.metadata?.department ? ` · Bộ phận: ${pr.metadata.department}` : ""}
                  </strong>
                </div>
                <p className="manager-context-card-body">{run.buyer_confirmation?.note || pr.metadata?.purpose || "Chưa có ghi chú bổ sung từ người yêu cầu."}</p>
                <div className="manager-context-meta">
                  <span>Hạn giao hàng: <strong>{formatDate(pr.delivery_due_date)}</strong></span>
                  <span>Ngày tạo đề nghị: <strong>{new Date(pr.created_at).toLocaleDateString("vi-VN")}</strong></span>
                </div>
              </article>
              <article className="workflow-card manager-context-card">
                <div className="manager-context-card-header">
                  <span className="manager-context-card-kicker">CĂN CỨ KỸ THUẬT &amp; ĐỀ XUẤT TỐI ƯU</span>
                  <strong className="manager-context-card-name">{supplierName(selectedId)}</strong>
                </div>
                <p className="manager-context-card-body">{review?.rationale || run.decision_proposal?.rationale || "Chưa có giải trình kỹ thuật từ hệ thống."}</p>
              </article>
            </div>
          </article>
        )}

        {!manager && (
          <section className="detail-card">
            <div className="detail-heading">
              <div>
                <p className="detail-code">{pr.code}</p>
                <h2>{pr.category}</h2>
              </div>
              <StatusPill status={pr.status} />
            </div>
            <p>Ngân sách {formatBudget(pr.estimated_budget)} · Hạn giao {formatDate(pr.delivery_due_date)}</p>
          </section>
        )}

        {review ? (
          <div className={manager ? "manager-recommendation" : undefined}>
            <VerifiedRecommendation
              run={run}
              review={review}
              name={supplierName}
              onDownload={async (documentId) => {
                if (!session) return;
                try {
                  const { blob, response } = await apiBlob(`/recommendations/${run.recommendation_id}/sources/${encodeURIComponent(documentId)}`, session);
                  const url = URL.createObjectURL(blob);
                  const link = document.createElement("a");
                  link.href = url;
                  const disposition = response.headers.get("Content-Disposition") || "";
                  link.download = disposition.match(/filename="([^"]+)"/)?.[1] || "bao-gia-nguon";
                  link.click();
                  window.setTimeout(() => URL.revokeObjectURL(url), 10000);
                } catch (exception) {
                  setError(exception instanceof Error ? exception.message : "Không tải được nguồn.");
                }
              }}
            />
          </div>
        ) : (
          <section className="ai-hero-card">
            <p className="section-kicker">Phân tích nhà cung cấp</p>
            <h3>{statusCopy[run.status] || run.status}</h3>
            <p>{message}</p>
            {run.manager_note && (
              <div className="analysis-guidance">
                <strong>Ghi chú của Quản lý</strong>
                <p>{run.manager_note}</p>
              </div>
            )}
            {buyerCanAct && repairable && run.status !== "running" && (
              <button className="inline-primary" disabled={working} onClick={() => void analyze()}>
                {run.status === "technical_failure" ? "Thử lại phân tích" : "Phân tích bằng Agent"}
              </button>
            )}
            {run.status === "running" && (
              <div className="analysis-progress">
                <button className="inline-primary" disabled>Đang phân tích…</button>
                <p>Thường mất khoảng 20–60 giây.</p>
              </div>
            )}
          </section>
        )}

        {manager && matrixIds.length > 0 && (
          <section className="workflow-card manager-matrix-card">
            <div className="workflow-card-heading">
              <div>
                <p className="text-overline">ĐỐI CHIẾU TIÊU CHÍ</p>
                <h3 className="text-title">Bảng so sánh chi tiết ({matrixIds.length} Nhà cung cấp)</h3>
              </div>
            </div>
            <div className="workflow-table-scroll">
              <table className="workflow-table workflow-matrix">
                <thead>
                  <tr>
                    <th>Tiêu chí</th>
                    {matrixIds.map((id) => (
                      <th key={id} className={id === selectedId ? "workflow-recommended" : ""}>
                        <div className="manager-th-vendor">
                          <span>{supplierName(id)}</span>
                          {id === selectedId && <span className="workflow-chip success">⭐ Lựa chọn tối ưu</span>}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(matrix.criteria || []).map((criterion: string) => (
                    <tr key={criterion}>
                      <th>{criterionLabels[criterion] || criterion}</th>
                      {matrixIds.map((id) => {
                        const cell = matrix.matrix?.[id]?.[criterion];
                        return (
                          <td key={id} className={id === selectedId ? "workflow-recommended" : ""}>
                            <strong>{cell?.value ?? "—"}</strong>
                            {cell?.note && <small>{cell.note}</small>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {run.manager_note && review && (
          <section className="detail-card">
            <h3>Ghi chú của Quản lý</h3>
            <p>{run.manager_note}</p>
          </section>
        )}

        <p className="error" role="alert">{error}</p>

        {canSubmit && (
          <div className="review-submit-action">
            <button className="inline-primary btn-submit-approval" disabled={working} onClick={() => void submitApproval()}>
              {working ? "Đang gửi duyệt…" : <>Gửi Quản lý phê duyệt <Icon name="arrow-right" className="button-icon" /></>}
            </button>
          </div>
        )}

        {decisionOpen && (
          <div className="workflow-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDecisionOpen(null); }}>
            <section className="workflow-modal manager-decision-modal" role="dialog" aria-modal="true" aria-labelledby="manager-decision-title">
              <div className="workflow-modal-heading">
                <div>
                  <h2 id="manager-decision-title" className="text-h3">
                    {decisionOpen === "reject" ? "Từ chối đề nghị mua sắm" : "Xác nhận phê duyệt đề nghị"}
                  </h2>
                  <p className="manager-modal-subtitle">{pr.code}: {pr.category}</p>
                </div>
                <button className="workflow-modal-close" type="button" aria-label="Đóng" onClick={() => setDecisionOpen(null)}>×</button>
              </div>

              {decisionOpen === "approve" && (
                <div className="workflow-alert info manager-modal-summary">
                  <div className="manager-modal-summary-row">
                    <span>Nhà cung cấp được chọn:</span>
                    <strong>{supplierName(selectedId)}</strong>
                  </div>
                  <div className="manager-modal-summary-row">
                    <span>Tổng giá trị phê duyệt:</span>
                    <strong>{proposed ? formatBudget(proposed) : "Chưa có"}</strong>
                  </div>
                  <small className="manager-modal-summary-hint">
                    Sau khi phê duyệt, hệ thống sẽ tự động tạo Đơn mua hàng (PO) ở trạng thái dự thảo.
                  </small>
                </div>
              )}

              <label htmlFor="manager-note" className="manager-modal-label">
                {decisionOpen === "reject" ? "Lý do từ chối (bắt buộc) *" : "Ý kiến chỉ đạo thực hiện (tùy chọn)"}
              </label>
              <textarea
                id="manager-note"
                rows={4}
                maxLength={500}
                value={managerNote}
                onChange={(event) => setManagerNote(event.target.value)}
                placeholder={decisionOpen === "reject" ? "Nhập chi tiết lý do từ chối để nhân viên hoàn thiện lại hồ sơ..." : "Nhập ý kiến chỉ đạo thực hiện mua sắm (nếu có)..."}
              />

              {decisionOpen === "reject" && (
                <div className="manager-quick-reasons-wrap">
                  <span className="manager-quick-reasons-title">Chọn nhanh lý do gợi ý:</span>
                  <div className="manager-quick-reasons">
                    {["Vượt quá ngân sách cho phép", "Cần bổ sung thêm báo giá đối chứng", "Tiến độ giao hàng không phù hợp", "Chưa rõ quy cách kỹ thuật"].map((reason) => (
                      <button
                        key={reason}
                        className="quick-opt"
                        type="button"
                        onClick={() => setManagerNote((value) => value ? `${value}; ${reason}` : reason)}
                      >
                        + {reason}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {(review?.critical_uncertainty_ids || []).map((id: string) => (
                <label key={id} className="manager-risk-check">
                  <input
                    type="checkbox"
                    checked={acknowledged.includes(id)}
                    onChange={(event) => setAcknowledged((current) => event.target.checked ? [...current, id] : current.filter((value) => value !== id))}
                  />
                  <span>Tôi đã xem xét rủi ro bắt buộc này và chấp thuận phê duyệt.</span>
                </label>
              ))}

              <div className="workflow-modal-actions">
                <button className="secondary" type="button" onClick={() => setDecisionOpen(null)}>Hủy bỏ</button>
                <button
                  className={decisionOpen === "reject" ? "danger-button" : "manager-modal-approve-btn"}
                  type="button"
                  disabled={working || (decisionOpen === "reject" && !managerNote.trim())}
                  onClick={() => void decide(decisionOpen)}
                >
                  {working ? "Đang xử lý…" : decisionOpen === "reject" ? "Xác nhận từ chối" : "Phê duyệt & Tạo PO"}
                </button>
              </div>
            </section>
          </div>
        )}

        {pr.po_id && (
          <button className="inline-primary" onClick={() => navigate(`/purchase-orders/${pr.po_id}`)}>
            Mở PO nháp <Icon name="arrow-right" className="button-icon" />
          </button>
        )}
      </div>
      {showAnalysisLoading && <AnalysisLoading />}
    </>
  );
}


function AnalysisLoading() {
  useEffect(() => { document.body.classList.add("analysis-loading-open"); return () => document.body.classList.remove("analysis-loading-open"); }, []);
  return <div className="analysis-loading-backdrop"><section className="analysis-loading-dialog" role="dialog" aria-modal="true"><span className="source-review-spinner analysis-react-spinner" /><p className="section-kicker">Phân tích nhà cung cấp</p><h2>Agent đang phân tích báo giá</h2><p>Đang đối chiếu chi phí, thời gian giao và các điều kiện thương mại.</p><div className="analysis-loading-status" role="status"><span />Kết quả sẽ tự cập nhật.</div></section></div>;
}

function VerifiedRecommendation({ run, review, name, onDownload }: { run: JsonObject; review: JsonObject; name: (id: string) => string; onDownload: (documentId: string) => void }) {
  const rankedIds = (review.ranked || review.ranked_supplier_ids || []).map((entry: JsonObject | string) => typeof entry === "string" ? entry : entry.supplier_id);
  const tcoIds = (run.tco_results || []).map((entry: JsonObject) => entry.supplier_id);
  const preferred = review.preferred_supplier_id || rankedIds[0] || tcoIds[0];
  const ids = [...new Set([preferred, ...rankedIds, ...tcoIds].filter(Boolean))] as string[];
  const claims = Object.entries(review.claims || {}) as Array<[string, JsonObject]>;
  return <><section className="ai-hero-card recommendation-brief"><div className="recommendation-brief-meta"><span className="verified-brief-badge"><Icon name="check" className="button-icon" /> Đã kiểm chứng</span><span>Dữ liệu đã qua đối chiếu điều kiện mua sắm</span></div><p className="section-kicker">Đề xuất nhà cung cấp tốt nhất</p><div className="recommendation-title-row"><h3>{name(preferred)}</h3><span className="selected-supplier-badge"><Icon name="check" className="button-icon" /> Lựa chọn tối ưu #1</span></div></section>
    <section className="comparison-panel recommendation-ranking-card"><div className="recommendation-section-heading"><div><p className="section-kicker">Kết quả đã kiểm chứng</p><h3>So sánh &amp; Xếp hạng Nhà cung cấp</h3></div><p>{ids.length} nhà cung cấp trong phạm vi đánh giá</p></div><div className="comparison-scroll"><table className="comparison-table recommendation-ranking-table"><thead><tr><th>Thứ hạng</th><th>Nhà cung cấp</th><th>Tổng gồm VAT &amp; phí</th><th>VAT</th><th>Phí trước VAT</th><th>Đánh giá</th></tr></thead><tbody>{ids.map((id, index) => { const tco = (run.tco_results || []).find((item: JsonObject) => item.supplier_id === id) || {}; return <tr key={id} className={id === preferred ? "is-recommended" : ""}><td className="recommendation-rank">#{index + 1}</td><th>{name(id)}</th><td>{formatComparisonMoney(tco.total_tco)} VND</td><td>{formatComparisonMoney(tco.total_vat)} VND</td><td>{formatComparisonMoney(tco.total_surcharges)} VND</td><td><span className={`assessment-pill ${id === preferred ? "is-recommended" : "is-verified"}`}>{id === preferred ? "Khuyên dùng · Tối ưu nhất" : "Đã kiểm chứng"}</span></td></tr>; })}</tbody></table></div></section>
    <section className="detail-card agent-evidence-card"><div className="recommendation-section-heading"><div><p className="section-kicker">Lý do được ưu tiên</p><h3>💡 Căn cứ &amp; Đánh giá từ Agent</h3></div></div><p className="recommendation-rationale">{review.rationale || "Đề xuất dựa trên đối chiếu tổng chi phí, tiến độ giao hàng và bảo hành từ các báo giá đã xác nhận."}</p>{claims.length > 0 && <details className="recommendation-proof"><summary>Xem căn cứ và bằng chứng đã kiểm chứng</summary><ul className="verified-claims agent-claims">{claims.map(([id, claim]) => <li key={id}><strong>{(claim.supplier_ids || []).map(name).join(" / ")}</strong>{claim.evidence?.sources?.filter((source: JsonObject) => source.chunk?.source_kind === "human_edit").map((source: JsonObject, index: number) => <p key={index}>{source.exact_excerpt} <button className="secondary" onClick={() => onDownload(source.chunk.document_id)}>Tải file gốc</button></p>)}</li>)}</ul></details>}</section>
  </>;
}
