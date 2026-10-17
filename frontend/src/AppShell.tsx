import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { Icon } from "./Icon";
import { roleConfig } from "./config";
import { apiRequest } from "./api";
import type { JsonObject } from "./types";
import { cancelQuotationExtraction, clearQuotationJobs, hideExpiredQuotationJobs, hideQuotationJob, JOB_AUTO_HIDE_MS, useQuotationJobs } from "./quotationExtractionJobs";

type AnalysisJob = { prId: string; code: string; analysisId?: string; status: "running" | "stopping" | "completed" | "failed" | "cancelled"; hidden?: boolean; finishedAt?: number; error?: string };

function metadata(pathname: string, role: "procurement" | "manager"): [string, string] {
  if (pathname.includes("/workflow/")) {
    const step = Number(pathname.split("/workflow/")[1]);
    return ([
      ["Thông tin PR", "Xem và chỉnh sửa nhu cầu mua sắm."],
      ["Tải báo giá", "Thu thập báo giá từ các nhà cung cấp."],
      ["Trích xuất báo giá", "Đối soát dữ liệu với tài liệu gốc."],
      ["Tổng hợp thông tin", "So sánh các phương án mua sắm."],
      ["Kết quả đề xuất", "Xem phương án và gửi phê duyệt."],
    ] as [string, string][])[step - 1] || ["Quy trình tạo PR", "Từ khai báo nhu cầu đến kết quả đề xuất mua sắm."];
  }
  if (pathname.includes("/comparison")) return role === "manager" ? ["Chi tiết thẩm định & ra quyết định", "Đối chiếu số liệu trước khi phê duyệt đề nghị mua sắm."] : ["So sánh & Đề xuất Nhà cung cấp", "Bảng so sánh đa chiều, kiểm tra chính sách mua sắm và khuyến nghị từ AI Agent."];
  if (pathname.startsWith("/purchase-orders/")) return ["Đơn Mua Hàng (PO Nháp)", "Bản nháp đơn mua hàng được sinh sau khi Quản lý phê duyệt (HITL)."];
  if (pathname === "/purchase-orders") return ["Đơn mua hàng", "Tra cứu các PO nháp đã được Quản lý phê duyệt."];
  if (pathname === "/dashboard") return ["Dashboard", "Theo dõi chỉ số mua sắm và các việc cần ưu tiên."];
  if (pathname === "/settings") return ["Cấu hình hệ thống", role === "manager" ? "Thiết lập chính sách mua sắm, kiểm soát ngân sách và mô hình AI." : "Tùy chỉnh thông số bóc tách OCR, khớp danh mục và trải nghiệm làm việc."];
  if (pathname === "/requests") return role === "manager" ? ["Phê duyệt đề nghị mua sắm", "Theo dõi và thẩm định hồ sơ đang chờ phê duyệt."] : ["Danh sách đề nghị", "Tra cứu, theo dõi và xử lý các đề nghị mua hàng."];
  if (pathname === "/purchase-requests/new") return ["Tạo đề nghị mua", "Khai báo nhu cầu mua sắm trước khi thu thập báo giá."];
  if (pathname.includes("/quotations")) return ["Báo giá", "Tải lên, đối chiếu và xác nhận dữ liệu báo giá."];
  return ["Chi tiết đề nghị mua", "Thông tin và tiến độ xử lý PR."];
}

export function AppShell() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("dotcom-sidebar-collapsed") === "true");
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(() => {
    try {
      const job = JSON.parse(sessionStorage.getItem("dotcom-workflow-job") || "null") as AnalysisJob | null;
      if (job?.status === "stopping") return { ...job, status: "running" };
      return job && job.status !== "running" && !job.finishedAt ? { ...job, finishedAt: Date.now() } : job;
    }
    catch { return null; }
  });
  const quotationJobs = useQuotationJobs();
  useEffect(() => {
    const update = (event: Event) => setAnalysisJob((current) => {
      const incoming = (event as CustomEvent<AnalysisJob>).detail;
      const same = current?.prId === incoming.prId && (!current.analysisId || current.analysisId === incoming.analysisId);
      if (same && incoming.status === "running" && ["stopping", "cancelled"].includes(current?.status || "")) {
        sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(current));
        return current;
      }
      const next: AnalysisJob = {
        ...incoming,
        hidden: same ? current?.hidden : false,
        finishedAt: incoming.status === "running" ? undefined : same && current?.finishedAt ? current.finishedAt : Date.now(),
      };
      sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(next));
      return next;
    });
    window.addEventListener("workflow-analysis-status", update);
    return () => window.removeEventListener("workflow-analysis-status", update);
  }, []);
  useEffect(() => {
    if (!session || !analysisJob || analysisJob.status !== "running") return;
    const timer = window.setInterval(() => {
      void apiRequest<JsonObject>(`/prs/${encodeURIComponent(analysisJob.prId)}/analysis`, session).then((result) => {
        if (result.status === "running") return;
        setAnalysisJob((current) => {
          if (!current || current.status !== "running" || current.prId !== analysisJob.prId) return current;
          const completed = ["awaiting_buyer_review", "pending_manager_approval", "approved", "rejected"].includes(String(result.status));
          const next: AnalysisJob = { ...current, status: completed ? "completed" : "failed", finishedAt: Date.now(), error: completed ? undefined : String(result.message || "Không thể hoàn tất phân tích.") };
          sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(next));
          return next;
        });
      }).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [analysisJob, session]);
  useEffect(() => {
    const deadlines = quotationJobs.filter((job) => !job.hidden && job.finishedAt).map((job) => Number(job.finishedAt) + JOB_AUTO_HIDE_MS);
    if (analysisJob && !analysisJob.hidden && analysisJob.finishedAt) deadlines.push(analysisJob.finishedAt + JOB_AUTO_HIDE_MS);
    if (!deadlines.length) return;
    const timer = window.setTimeout(() => {
      hideExpiredQuotationJobs();
      setAnalysisJob((current) => {
        if (!current?.finishedAt || current.hidden || Date.now() - current.finishedAt < JOB_AUTO_HIDE_MS) return current;
        const next = { ...current, hidden: true };
        sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(next));
        return next;
      });
    }, Math.max(0, Math.min(...deadlines) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [analysisJob, quotationJobs]);
  if (!session) return null;
  const config = roleConfig[session.user.role];
  const [title, subtitle] = metadata(location.pathname, session.user.role);
  const showCreate = session.user.role === "procurement" && ["/dashboard", "/requests"].includes(location.pathname);
  const toggle = () => setCollapsed((value) => { localStorage.setItem("dotcom-sidebar-collapsed", String(!value)); return !value; });
  const hideAnalysis = () => setAnalysisJob((current) => {
    if (!current) return current;
    const next = { ...current, hidden: true };
    sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(next));
    return next;
  });
  const stopQuotation = async (id: string, prId: string) => {
    if (await cancelQuotationExtraction(id, session)) navigate(`/purchase-requests/${prId}/workflow/2`);
  };
  const stopAnalysis = async (job: AnalysisJob) => {
    setAnalysisJob((current) => current?.prId === job.prId && current.status === "running" ? { ...current, status: "stopping" } : current);
    try {
      const current = job.analysisId ? job : await apiRequest<JsonObject>(`/prs/${encodeURIComponent(job.prId)}/analysis`, session).then((result) => ({ ...job, analysisId: String(result.analysis_id || "") }));
      if (!current.analysisId) throw new Error("Không tìm thấy mã tiến trình phân tích.");
      const result = await apiRequest<JsonObject>(`/prs/${encodeURIComponent(job.prId)}/analysis/cancel`, session, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ analysis_id: current.analysisId }) });
      const resolvedStatus: AnalysisJob["status"] = result.status === "stale" ? "cancelled" : ["awaiting_buyer_review", "pending_manager_approval", "approved", "rejected"].includes(String(result.status)) ? "completed" : "failed";
      const next: AnalysisJob = { ...current, status: resolvedStatus, finishedAt: Date.now(), error: resolvedStatus === "failed" ? String(result.message || "Phân tích cần kiểm tra.") : undefined };
      setAnalysisJob((latest) => {
        const settled = { ...next, hidden: latest?.prId === next.prId ? latest.hidden : next.hidden };
        sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(settled));
        return settled;
      });
      window.dispatchEvent(new Event("workflow-analysis-cancelled"));
      navigate(`/purchase-requests/${job.prId}/workflow/4`);
    } catch (error) {
      setAnalysisJob((current) => {
        if (!current || current.prId !== job.prId) return current;
        const next: AnalysisJob = { ...current, status: "running", error: error instanceof Error ? error.message : "Không thể ngừng phân tích." };
        sessionStorage.setItem("dotcom-workflow-job", JSON.stringify(next));
        return next;
      });
    }
  };

  return <section className={`shell${collapsed ? " sidebar-collapsed" : ""}`}>
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand">
          <span className="brand-mark"><Icon name="brand" /></span>
          <span>DotCom</span>
        </div>
        <button
          className="sidebar-toggle"
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
        >
          <span className="sidebar-toggle-icon">
            <Icon name={collapsed ? "panel-left-open" : "panel-left-close"} />
          </span>
        </button>
      </div>
      <div className="sidebar-rule" />
      <nav aria-label="Điều hướng chính" className="sidebar-nav">
        {config.navGroups.map((group, groupIdx) => (
          <div key={group.title} className="nav-group">
            {groupIdx > 0 && <div className="nav-group-divider" />}
            <div className="nav-group-title">{group.title}</div>
            <div className="nav-group-items">
              {group.items.map(([path, iconName, label]) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) => `nav-button ${isActive ? "active" : ""}`}
                  title={label}
                >
                  <span className="nav-icon"><Icon name={iconName} /></span>
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      {session.user.role === "procurement" && ((!analysisJob?.hidden && analysisJob) || quotationJobs.some((job) => job.userId === session.user.id && !job.hidden)) && <div className="sidebar-jobs" aria-label="Tiến trình xử lý">
        {quotationJobs.filter((job) => job.userId === session.user.id && !job.hidden).map((job) => <div key={job.id} className={`sidebar-job ${job.status}`} title={job.errors.join(" | ")}><button className="sidebar-job-main" type="button" onClick={() => navigate(`/purchase-requests/${job.prId}/workflow/${job.status === "completed" ? 3 : 2}`)}><small>{job.status === "running" ? `ĐANG TRÍCH XUẤT • ${job.completed}/${job.total}` : job.status === "stopping" ? "ĐANG NGỪNG TRÍCH XUẤT" : job.status === "completed" ? "TRÍCH XUẤT XONG" : job.status === "cancelled" ? "ĐÃ NGỪNG TRÍCH XUẤT" : "TRÍCH XUẤT CẦN KIỂM TRA"}</small><strong>{job.code}</strong><span>{job.status === "running" ? "Đang đọc báo giá…" : job.status === "stopping" ? "Đang dừng file hiện tại…" : job.status === "completed" ? `${job.completed} báo giá sẵn sàng đối soát ✓` : job.status === "cancelled" ? "Có thể chỉnh sửa và tải lại." : `${job.completed}/${job.total} báo giá đã xử lý. Xem Bước 2.`}</span></button><div className="sidebar-job-actions"><button type="button" onClick={() => hideQuotationJob(job.id)} aria-label={`Ẩn tiến trình ${job.code}`}>Ẩn</button>{job.status === "running" && <button type="button" onClick={() => { void stopQuotation(job.id, job.prId); }} aria-label={`Ngừng trích xuất ${job.code}`}>Ngừng</button>}</div></div>)}
        {analysisJob && !analysisJob.hidden && <div className={`sidebar-job ${analysisJob.status}`}><button className="sidebar-job-main" type="button" onClick={() => navigate(`/purchase-requests/${analysisJob.prId}/workflow/${analysisJob.status === "completed" ? 5 : 4}`)}><small>{analysisJob.status === "running" ? "ĐANG XỬ LÝ • 1" : analysisJob.status === "stopping" ? "ĐANG NGỪNG PHÂN TÍCH" : analysisJob.status === "completed" ? "ĐÃ XỬ LÝ XONG • 1" : analysisJob.status === "cancelled" ? "ĐÃ NGỪNG PHÂN TÍCH" : "PHÂN TÍCH CẦN KIỂM TRA"}</small><strong>{analysisJob.code}</strong><span>{analysisJob.error || (analysisJob.status === "running" ? "Đang gọi AI đề xuất…" : analysisJob.status === "stopping" ? "Đang gửi lệnh ngừng…" : analysisJob.status === "completed" ? "Đã sẵn sàng kết quả đề xuất ✓" : analysisJob.status === "cancelled" ? "Có thể chỉnh sửa và chạy lại." : "Mở Bước 4 để kiểm tra.")}</span></button><div className="sidebar-job-actions"><button type="button" onClick={hideAnalysis} aria-label={`Ẩn tiến trình ${analysisJob.code}`}>Ẩn</button>{analysisJob.status === "running" && <button type="button" onClick={() => { void stopAnalysis(analysisJob); }} aria-label={`Ngừng phân tích ${analysisJob.code}`}>Ngừng</button>}</div></div>}
      </div>}
      <div className="sidebar-footer"><div className="identity"><div className="identity-copy"><strong>{session.user.name}</strong><span className="identity-role">{config.label}</span><span className="identity-email">{session.user.email}</span></div></div><div className="sidebar-actions"><button className="sidebar-action" type="button" aria-label="Thông báo" title="Thông báo"><Icon name="bell" /></button><button className="sidebar-action" type="button" onClick={() => { sessionStorage.removeItem("dotcom-workflow-job"); clearQuotationJobs(); void logout().then(() => navigate("/login")); }} aria-label="Đăng xuất" title="Đăng xuất"><Icon name="logout" /></button></div></div>
    </aside>
    <main className="content"><div className="topline"><div><h1>{title}</h1><p>{subtitle}</p></div>{showCreate && <button className="inline-primary page-header-action" onClick={() => navigate("/purchase-requests/new")}><Icon name="plus" className="button-icon" /> Tạo đề nghị mua</button>}</div><div id="page-content"><Outlet /></div></main>
  </section>;
}
