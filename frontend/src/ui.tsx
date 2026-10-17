import { useEffect, useRef } from "react";
import { Icon } from "./Icon";
import { statusLabels } from "./config";

export function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}>{statusLabels[status] || status}</span>;
}

export function LoadingState({ label = "Đang tải dữ liệu…" }: { label?: string }) {
  return <section className="empty" role="status"><div><div className="card-icon"><Icon name="loader" /></div><p>{label}</p></div></section>;
}

export function ErrorState({ message, onRetry, retryLabel = "Thử lại" }: { message: string; onRetry?: () => void; retryLabel?: string }) {
  return <section className="empty error-state"><div><div className="card-icon"><Icon name="alert-triangle" /></div><h2>Không thể hiển thị dữ liệu</h2><p>{message}</p>{onRetry && <button className="secondary" type="button" onClick={onRetry}>{retryLabel}</button>}</div></section>;
}

export function Flash({ message, tone }: { message: string; tone: string }) {
  return <div className={`flash-message ${tone}`} role="status"><span><Icon name="check" /></span>{message}</div>;
}

export function ConfirmDialog({ title, description, confirmLabel = "Xóa", onConfirm, onCancel }: { title: string; description: string; confirmLabel?: string; onConfirm: () => void; onCancel: () => void }) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    document.body.classList.add("confirm-modal-open");
    cancelRef.current?.focus();
    const listener = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel(); };
    document.addEventListener("keydown", listener);
    return () => { document.body.classList.remove("confirm-modal-open"); document.removeEventListener("keydown", listener); };
  }, [onCancel]);
  return <div className="confirm-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"><div className="confirm-dialog-mark"><Icon name="alert-triangle" /></div><div><p className="section-kicker">Xác nhận thao tác</p><h2 id="confirm-dialog-title">{title}</h2><p>{description}</p></div><div className="confirm-dialog-actions"><button ref={cancelRef} className="secondary" type="button" onClick={onCancel}>Hủy</button><button className="danger-button" type="button" onClick={onConfirm}>{confirmLabel}</button></div></section></div>;
}

export function ProgressRail({ status }: { status: string }) {
  const states = [["awaiting_quotation", "01", "Thu thập báo giá"], ["comparing", "02", "So sánh lựa chọn"], ["pending_approval", "03", "Chờ phê duyệt"], ["approved", "04", "Hoàn tất"]];
  const active = status === "rejected" ? 2 : Math.max(0, states.findIndex(([key]) => key === status));
  return <ol className="progress-rail" aria-label="Tiến trình đề nghị mua">{states.map(([, number, label], index) => {
    const done = index < active || status === "approved";
    const current = index === active && status !== "approved";
    return <li key={number} className={`${done ? "done" : ""} ${current ? "current" : ""}`}><span>{done ? <Icon name="check" /> : number}</span><b>{label}</b></li>;
  })}</ol>;
}
