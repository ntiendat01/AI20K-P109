import { useEffect, useMemo, useState } from "react";
import { apiBlob, apiRequest } from "../api";
import type { Session, Quotation, JsonObject } from "../types";
import { Icon } from "../Icon";
import { formatComparisonMoney } from "../utils";

export function SourceReview({ session, quotation, onClose }: { session: Session; quotation: Quotation; onClose: () => void }) {
  const [preview, setPreview] = useState<JsonObject | null>(null);
  const [pageUrls, setPageUrls] = useState<string[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    document.body.classList.add("source-review-open");
    const listener = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", listener);
    return () => { document.body.classList.remove("source-review-open"); document.removeEventListener("keydown", listener); };
  }, [onClose]);

  useEffect(() => {
    let disposed = false;
    const urls: string[] = [];
    setPreview(null); setPageUrls([]); setError("");
    void (async () => {
      try {
        const result = await apiRequest<JsonObject>(`/quotations/${encodeURIComponent(quotation.id)}/review-preview`, session);
        const blobs = await Promise.all((result.pages || []).map((page: JsonObject) => apiBlob(`/quotations/${encodeURIComponent(quotation.id)}/review-preview/pages/${page.number}`, session)));
        blobs.forEach(({ blob }) => urls.push(URL.createObjectURL(blob)));
        if (!disposed) { setPreview(result); setPageUrls(urls); const first = (result.matches || []).find((match: JsonObject) => match.region); setActive(first ? Number(first.item_index) : quotation.items.length ? 0 : null); }
      } catch (exception) { if (!disposed) setError(exception instanceof Error ? exception.message : "Không thể mở bản đối chiếu."); }
    })();
    return () => { disposed = true; urls.forEach(URL.revokeObjectURL); };
  }, [quotation.id, reloadKey, session]);

  const regions = useMemo(() => new Map<number, JsonObject>((preview?.matches || []).map((match: JsonObject) => [Number(match.item_index), match.region])), [preview]);
  const activeRegion = active == null ? null : regions.get(active);
  return <div className="source-review-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="source-review-dialog" role="dialog" aria-modal="true" aria-labelledby="source-review-dialog-title">
    <header className="source-review-dialog-header"><div><p className="section-kicker">Đối chiếu báo giá</p><h2 id="source-review-dialog-title">{preview ? "Đối chiếu với file gốc" : error ? "Không thể mở bản đối chiếu" : "Đang chuẩn bị file gốc"}</h2><p>{quotation.source_filename}</p></div><button className="source-review-close" type="button" onClick={onClose} aria-label="Đóng bản đối chiếu"><Icon name="close" /></button></header>
    {error ? <div className="source-review-error"><div className="card-icon">!</div><div><strong>File gốc chưa thể hiển thị</strong><p>{error}</p><button className="secondary" onClick={() => setReloadKey((value) => value + 1)}>Thử lại</button></div></div>
      : !preview ? <div className="source-review-loading"><span className="source-review-spinner" /><div><strong>Đang dựng bản đối chiếu</strong><p>Trang PDF và vị trí các dòng hàng đang được chuẩn bị.</p></div></div>
      : <div className="source-review-layout"><section className="source-review-items"><div className="source-review-pane-heading"><div><p className="section-kicker">Bảng trích xuất</p><h3>Dòng hàng đã trích xuất</h3><p>Rê chuột hoặc chọn một dòng để định vị trên bản gốc.</p></div><span className="source-item-count">{quotation.items.length} dòng</span></div><div className="source-review-table">{quotation.items.map((item, index) => { const region = regions.get(index); return <button key={index} className={`source-review-row ${active === index ? "active" : ""}`} type="button" aria-pressed={active === index} onMouseEnter={() => setActive(index)} onFocus={() => setActive(index)} onClick={() => setActive(index)}><span className="source-row-index">{index + 1}</span><span className="source-row-detail"><strong>{item.product_code ? `${item.product_code} · ` : ""}{item.product_name || "Dòng hàng chưa có tên"}</strong><small>{item.unit || "Chưa có đơn vị"} · SL {item.quantity}</small><span className={`source-match-status ${region ? "found" : "missing"}`}>{region ? `Đã định vị · tr. ${region.page}` : "Chưa định vị"}</span></span><span className="source-row-money"><small>Đơn giá</small><b>{formatComparisonMoney(item.unit_price)}</b></span><span className="source-row-money"><small>Thành tiền</small><b>{formatComparisonMoney(item.line_total)}</b></span></button>; })}</div><p className="source-review-edit-note">Cần chỉnh sửa? Đóng bản đối chiếu để cập nhật các trường trong biểu mẫu.</p></section>
        <section className="source-preview-pane"><div className="source-review-pane-heading source-preview-heading"><div><p className="section-kicker">File gốc</p><h3>{quotation.source_filename}</h3><p>{activeRegion ? `Đang tô sáng dòng ${(active ?? 0) + 1} trên trang ${activeRegion.page}.` : "Không tìm thấy vị trí tự động; hãy đối chiếu trực quan."}</p></div><span className="source-page-counter">Trang {activeRegion?.page || 1}/{preview.pages.length}</span></div><div className="source-preview-scroll">{preview.pages.map((page: JsonObject, pageIndex: number) => <figure className="source-preview-page" key={page.number}><div className="source-page-label">Trang {page.number}</div><div className="source-page-canvas"><img src={pageUrls[pageIndex]} alt={`Trang ${page.number} của ${quotation.source_filename}`} />{(preview.matches || []).filter((match: JsonObject) => match.region?.page === page.number).map((match: JsonObject) => { const region = match.region; const itemIndex = Number(match.item_index); return <span key={itemIndex} className={`source-row-highlight ${active === itemIndex ? "active" : ""}`} style={{ left: `${Number(region.x) / Number(page.width) * 100}%`, top: `${Number(region.y) / Number(page.height) * 100}%`, width: `${Number(region.width) / Number(page.width) * 100}%`, height: `${Number(region.height) / Number(page.height) * 100}%` }}><i>{itemIndex + 1}</i></span>; })}</div></figure>)}</div></section>
      </div>}
  </section></div>;
}
