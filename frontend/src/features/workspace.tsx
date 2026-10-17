import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FileCheck, FileSpreadsheet, FileText, Printer, Trash2 } from "lucide-react";
import { apiRequest } from "../api";
import { useAuth } from "../AuthProvider";
import { statusLabels } from "../config";
import { Icon } from "../Icon";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { JsonObject, PurchaseRequest, Quotation } from "../types";
import { ConfirmDialog, ErrorState, LoadingState, StatusPill } from "../ui";
import { formatBudget, formatComparisonMoney, formatDate } from "../utils";

const PAGE_SIZE = 6;

type TimeRangeKey = "30d" | "90d" | "180d" | "365d";

const TIME_RANGES: Array<{ key: TimeRangeKey; label: string; days: number }> = [
  { key: "30d", label: "1 tháng", days: 30 },
  { key: "90d", label: "3 tháng", days: 90 },
  { key: "180d", label: "6 tháng", days: 180 },
  { key: "365d", label: "1 năm", days: 365 },
];

const PIE_COLORS = ["#147dab", "#7558d9", "#16836a", "#f59e0b", "#38bdf8", "#e11d48", "#8b5cf6"];

interface DeltaResult {
  text: string;
  tone: "good" | "bad" | "neutral";
  direction: "up" | "down" | "neutral";
}

function computeDelta(
  current: number,
  previous: number,
  mode: "positive-up" | "negative-up" | "neutral" = "positive-up"
): DeltaResult {
  if (previous === 0) {
    if (current === 0) {
      return { text: "— 0%", tone: "neutral", direction: "neutral" };
    }
    const tone = mode === "positive-up" ? "good" : mode === "negative-up" ? "bad" : "neutral";
    return { text: `↑ +${current} mới`, tone, direction: "up" };
  }
  const diff = current - previous;
  const pct = Math.round((diff / previous) * 100);
  if (diff > 0) {
    const tone = mode === "positive-up" ? "good" : mode === "negative-up" ? "bad" : "neutral";
    return { text: `↑ +${pct}%`, tone, direction: "up" };
  }
  if (diff < 0) {
    const tone = mode === "positive-up" ? "bad" : mode === "negative-up" ? "good" : "neutral";
    return { text: `↓ ${pct}%`, tone, direction: "down" };
  }
  return { text: "— 0%", tone: "neutral", direction: "neutral" };
}

function useRequests() {
  const { session } = useAuth();
  const [requests, setRequests] = useState<PurchaseRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = async () => {
    if (!session) return;
    setLoading(true); setError("");
    try { setRequests(await apiRequest<PurchaseRequest[]>(session.user.role === "manager" ? "/manager/prs" : "/prs", session)); }
    catch (exception) { setError(exception instanceof Error ? exception.message : "Không tải được danh sách đề nghị."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [session?.user.role]);
  return { requests, loading, error, reload: load };
}

function compactBudget(value: number) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} tr`;
  return formatBudget(value);
}

export function DashboardPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const { requests, loading, error, reload } = useRequests();
  const [timeRange, setTimeRange] = useState<TimeRangeKey>("180d");

  const employee = session?.user.role === "procurement";

  const { currentRequests, prevRequests } = useMemo(() => {
    const rangeConfig = TIME_RANGES.find((r) => r.key === timeRange) || TIME_RANGES[2];
    const durationMs = rangeConfig.days * 86400000;
    const now = Date.now();
    const currentStart = now - durationMs;
    const prevStart = now - 2 * durationMs;

    const current = requests.filter((r) => {
      const t = new Date(r.created_at).getTime();
      return !isNaN(t) && t >= currentStart && t <= now;
    });

    const prev = requests.filter((r) => {
      const t = new Date(r.created_at).getTime();
      return !isNaN(t) && t >= prevStart && t < currentStart;
    });

    return {
      currentRequests: current.length ? current : requests,
      prevRequests: prev,
    };
  }, [requests, timeRange]);

  const trend = useMemo(() => {
    const now = new Date();
    if (timeRange === "30d") {
      return Array.from({ length: 4 }, (_, index) => {
        const startDay = (3 - index) * 7;
        const endDay = (3 - index - 1) * 7;
        const startDate = new Date(now.getTime() - (startDay + 7) * 86400000);
        const endDate = new Date(now.getTime() - (endDay > 0 ? endDay * 86400000 : 0));
        const label = `Tuần ${index + 1}`;
        const periodRequests = requests.filter((r) => {
          const d = new Date(r.created_at);
          return !isNaN(d.getTime()) && d >= startDate && d <= endDate;
        });
        return {
          month: label,
          created: periodRequests.length,
          processed: periodRequests.filter((r) => ["approved", "rejected"].includes(r.status)).length,
        };
      });
    }

    const monthCount = timeRange === "90d" ? 3 : timeRange === "180d" ? 6 : 12;
    return Array.from({ length: monthCount }, (_, index) => {
      const date = new Date(now.getFullYear(), now.getMonth() - (monthCount - 1 - index), 1);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
      const monthRequests = requests.filter((r) => String(r.created_at || "").slice(0, 7) === key);
      return {
        month: date.toLocaleDateString("vi-VN", { month: "short" }),
        created: monthRequests.length,
        processed: monthRequests.filter((r) => ["approved", "rejected"].includes(r.status)).length,
      };
    });
  }, [requests, timeRange]);

  const pieData = useMemo(() => {
    const map = new Map<string, { name: string; count: number; value: number }>();
    currentRequests.forEach((req) => {
      const rawName = employee
        ? req.category || "Chưa phân loại"
        : req.metadata?.department || req.category || "Khác";
      const name = rawName.trim();
      const existing = map.get(name) || { name, count: 0, value: 0 };
      existing.count += 1;
      existing.value += Number(req.estimated_budget || 0);
      map.set(name, existing);
    });
    return Array.from(map.values())
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);
  }, [currentRequests, employee]);

  const pieTotal = pieData.reduce((sum, item) => sum + item.value, 0);

  const urgentEmployeeTasks = useMemo(() => {
    return requests
      .filter((r) => ["draft", "awaiting_quotation", "rejected", "comparing"].includes(r.status))
      .sort((a, b) => {
        const order = (s: string) => (s === "rejected" ? 3 : s === "awaiting_quotation" || s === "draft" ? 2 : 1);
        return order(b.status) - order(a.status);
      })
      .slice(0, 4);
  }, [requests]);

  const priorityManagerApprovals = useMemo(() => {
    return requests
      .filter((r) => r.status === "pending_approval")
      .sort((a, b) => Number(b.estimated_budget || 0) - Number(a.estimated_budget || 0))
      .slice(0, 4);
  }, [requests]);

  if (loading) return <LoadingState label="Đang tải dashboard…" />;
  if (error) return <ErrorState message={error} onRetry={() => void reload()} />;

  const currWaiting = currentRequests.filter((r) => ["draft", "awaiting_quotation"].includes(r.status)).length;
  const prevWaiting = prevRequests.filter((r) => ["draft", "awaiting_quotation"].includes(r.status)).length;

  const currProcessing = currentRequests.filter((r) => ["comparing", "pending_approval"].includes(r.status)).length;
  const prevProcessing = prevRequests.filter((r) => ["comparing", "pending_approval"].includes(r.status)).length;

  const currCompleted = currentRequests.filter((r) => r.status === "approved").length;
  const prevCompleted = prevRequests.filter((r) => r.status === "approved").length;

  const currRejected = currentRequests.filter((r) => r.status === "rejected").length;
  const prevRejected = prevRequests.filter((r) => r.status === "rejected").length;

  const currPending = currentRequests.filter((r) => r.status === "pending_approval").length;
  const prevPending = prevRequests.filter((r) => r.status === "pending_approval").length;

  const currApproved = currentRequests.filter((r) => r.status === "approved").length;
  const prevApproved = prevRequests.filter((r) => r.status === "approved").length;

  const currComparing = currentRequests.filter((r) => r.status === "comparing").length;
  const prevComparing = prevRequests.filter((r) => r.status === "comparing").length;

  const currManagerRejected = currentRequests.filter((r) => r.status === "rejected").length;
  const prevManagerRejected = prevRequests.filter((r) => r.status === "rejected").length;

  const pendingBudget = currentRequests
    .filter((r) => r.status === "pending_approval")
    .reduce((sum, r) => sum + Number(r.estimated_budget || 0), 0);

  const approvedBudget = currentRequests
    .filter((r) => r.status === "approved")
    .reduce((sum, r) => sum + Number(r.estimated_budget || 0), 0);

  const totalBudget = currentRequests.reduce(
    (sum, req) => sum + (employee && req.status !== "pending_approval" ? 0 : Number(req.estimated_budget || 0)),
    0
  );

  const employeeKpis = [
    {
      label: "Cần bổ sung báo giá",
      value: currWaiting,
      tone: "amber",
      subtext: "Hồ sơ chưa đủ báo giá",
      delta: computeDelta(currWaiting, prevWaiting, "negative-up"),
      targetStatus: "awaiting_quotation",
    },
    {
      label: "Đang xử lý & So sánh",
      value: currProcessing,
      tone: "sky",
      subtext: "Đang phân tích & thẩm định",
      delta: computeDelta(currProcessing, prevProcessing, "neutral"),
      targetStatus: "comparing",
    },
    {
      label: "Đã hoàn tất",
      value: currCompleted,
      tone: "mint",
      subtext: "Đã duyệt và chuyển PO",
      delta: computeDelta(currCompleted, prevCompleted, "positive-up"),
      targetStatus: "approved",
    },
    {
      label: "Cần xem lại",
      value: currRejected,
      tone: "rose",
      subtext: "Bị từ chối hoặc trả về",
      delta: computeDelta(currRejected, prevRejected, "negative-up"),
      targetStatus: "rejected",
    },
  ];

  const managerKpis = [
    {
      label: "Chờ bạn phê duyệt",
      value: currPending,
      tone: "violet",
      subtext: `${compactBudget(pendingBudget)} đang chờ`,
      delta: computeDelta(currPending, prevPending, "neutral"),
      targetStatus: "pending_approval",
    },
    {
      label: "Đã phê duyệt kỳ này",
      value: currApproved,
      tone: "mint",
      subtext: `${compactBudget(approvedBudget)} đã duyệt`,
      delta: computeDelta(currApproved, prevApproved, "positive-up"),
      targetStatus: "approved",
    },
    {
      label: "Đang thẩm định giá",
      value: currComparing,
      tone: "sky",
      subtext: "Hồ sơ đang phân tích TCO",
      delta: computeDelta(currComparing, prevComparing, "neutral"),
      targetStatus: "comparing",
    },
    {
      label: "Từ chối / Cần xem lại",
      value: currManagerRejected,
      tone: "rose",
      subtext: `${currentRequests.length ? Math.round((currManagerRejected / currentRequests.length) * 100) : 0}% tỷ lệ từ chối`,
      delta: computeDelta(currManagerRejected, prevManagerRejected, "negative-up"),
      targetStatus: "rejected",
    },
  ];

  const kpis = employee ? employeeKpis : managerKpis;

  const statuses: Array<[string, number, string]> = employee
    ? [
        ["Báo giá", currWaiting, "#f59e0b"],
        ["So sánh", currentRequests.filter((r) => r.status === "comparing").length, "#147dab"],
        ["Chờ duyệt", currentRequests.filter((r) => r.status === "pending_approval").length, "#7558d9"],
        ["Hoàn tất", currCompleted, "#16836a"],
      ]
    : [
        ["Chờ duyệt", currPending, "#7558d9"],
        ["Đã duyệt", currApproved, "#16836a"],
        ["Từ chối", currManagerRejected, "#bd4350"],
      ];

  const selectedRangeObj = TIME_RANGES.find((r) => r.key === timeRange) || TIME_RANGES[2];

  return (
    <section className="dashboard-view">
      <div className="dashboard-banner">
        <div className="dashboard-welcome">
          <h2>{employee ? `Xin chào, ${session?.user.name}!` : `Tổng quan phê duyệt mua sắm`}</h2>
          <p>
            {employee
              ? "Theo dõi tiến độ xử lý hồ sơ mua sắm và các đầu việc cần ưu tiên hành động."
              : `Hiện có ${currPending} đề nghị (${compactBudget(pendingBudget)}) đang chờ xem xét và phê duyệt.`}
          </p>
        </div>
        <div className="dashboard-time-filter" role="group" aria-label="Lọc thời gian">
          {TIME_RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              className={`dashboard-time-btn ${timeRange === r.key ? "active" : ""}`}
              onClick={() => setTimeRange(r.key)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <section className="dashboard-kpis">
        {kpis.map((kpi) => (
          <article
            key={kpi.label}
            className={`dashboard-kpi ${kpi.tone}`}
            onClick={() => navigate(`/requests?status=${kpi.targetStatus}`)}
            title={`Bấm để xem danh sách ${kpi.label}`}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") navigate(`/requests?status=${kpi.targetStatus}`);
            }}
          >
            <div className="dashboard-kpi-top">
              <span>{kpi.label}</span>
              <span className={`dashboard-kpi-delta ${kpi.delta.tone}`}>
                {kpi.delta.text}
              </span>
            </div>
            <div className="dashboard-kpi-val">
              <strong>{kpi.value}</strong>
            </div>
            <div className="dashboard-kpi-sub">{kpi.subtext}</div>
          </article>
        ))}
      </section>

      <section className="dashboard-grid">
        <article className="dashboard-card trend-card">
          <div className="card-heading">
            <div>
              <h3>Xu hướng đề nghị</h3>
              <p>Số lượng tạo mới và đã xử lý theo kỳ</p>
            </div>
            <span className="card-period">{selectedRangeObj.label} gần đây</span>
          </div>
          <div className="dashboard-chart">
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={trend} margin={{ top: 12, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e8eef3" />
                <XAxis dataKey="month" tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip
                  formatter={(val: any, name: any) => [
                    `${val} đề nghị`,
                    name === "created" ? "Tạo mới" : "Đã xử lý",
                  ]}
                />
                <Legend formatter={(value) => (value === "created" ? "Tạo mới" : "Đã xử lý")} />
                <Bar dataKey="created" name="created" fill="#147dab" radius={[5, 5, 0, 0]} />
                <Bar dataKey="processed" name="processed" fill="#7558d9" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="dashboard-card cost-card">
          <div className="card-heading">
            <div>
              <h3>{employee ? "Cơ cấu theo danh mục" : "Phân bổ chi tiêu"}</h3>
              <p>{employee ? "Tỷ trọng đề nghị theo nhóm hàng hóa" : "Ngân sách theo bộ phận/danh mục"}</p>
            </div>
          </div>
          {pieData.length ? (
            <>
              <div className="dashboard-chart" style={{ height: 160, marginTop: 10 }}>
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={65}
                      paddingAngle={3}
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={`cell-${entry.name}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: any, name: any) => [
                        compactBudget(Number(value) || 0),
                        String(name),
                      ]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="pie-legend">
                {pieData.map((item, index) => {
                  const pct = pieTotal > 0 ? Math.round((item.value / pieTotal) * 100) : 0;
                  return (
                    <div key={item.name} className="pie-legend-item">
                      <div className="pie-legend-left">
                        <span
                          className="pie-legend-color"
                          style={{ background: PIE_COLORS[index % PIE_COLORS.length] }}
                        />
                        <span title={item.name}>
                          {item.name.length > 18 ? `${item.name.slice(0, 18)}…` : item.name} ({item.count})
                        </span>
                      </div>
                      <strong className="pie-legend-value">
                        {compactBudget(item.value)} ({pct}%)
                      </strong>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="dashboard-empty-state">
              <div className="card-icon"><Icon name="search" /></div>
              <strong>Chưa có dữ liệu phân bổ</strong>
              <p>Chưa có đề nghị nào được ghi nhận trong kỳ đã chọn.</p>
            </div>
          )}
        </article>
      </section>

      <section className="dashboard-row-secondary">
        <article className="dashboard-card dashboard-tasks-card">
          <div className="card-heading">
            <div>
              <h3>{employee ? "⚡ Việc cần ưu tiên xử lý ngay" : "🕒 Hàng đợi phê duyệt ưu tiên"}</h3>
              <p>
                {employee
                  ? "Các đề nghị đang chờ bổ sung báo giá hoặc cần chỉnh sửa lại"
                  : "Các đề nghị có ngân sách lớn nhất đang chờ bạn xem xét"}
              </p>
            </div>
          </div>
          {employee ? (
            urgentEmployeeTasks.length ? (
              <div className="dashboard-tasks-list">
                {urgentEmployeeTasks.map((req) => {
                  const isRejected = req.status === "rejected";
                  const isWaitingQuote = ["draft", "awaiting_quotation"].includes(req.status);
                  const badgeTone = isRejected ? "rose" : isWaitingQuote ? "amber" : "sky";
                  const badgeText = isRejected ? "Cần chỉnh sửa" : isWaitingQuote ? "Thiếu báo giá" : "Đang so sánh";
                  const actionPath = isRejected
                    ? `/purchase-requests/${req.id}/workflow/1`
                    : isWaitingQuote
                    ? `/purchase-requests/${req.id}/workflow/2`
                    : `/purchase-requests/${req.id}/workflow/4`;
                  const actionLabel = isRejected ? "Sửa hồ sơ →" : isWaitingQuote ? "Tải báo giá →" : "Xem kết quả →";

                  return (
                    <div key={req.id} className="dashboard-task-item">
                      <div className="dashboard-task-info">
                        <div className="dashboard-task-title">
                          <Link to={`/purchase-requests/${req.id}/workflow`} className="request-link">
                            {req.code}
                          </Link>
                          <span>{req.category}</span>
                          <span className={`dashboard-task-badge ${badgeTone}`}>{badgeText}</span>
                        </div>
                        <div className="dashboard-task-meta">
                          <span>Ngân sách: <strong>{formatBudget(req.estimated_budget)}</strong></span>
                          <span>Hạn giao: <strong>{formatDate(req.delivery_due_date)}</strong></span>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="dashboard-task-action-btn"
                        onClick={() => navigate(actionPath)}
                      >
                        {actionLabel}
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="dashboard-empty-state">
                <div className="card-icon"><Icon name="check" /></div>
                <strong>Tuyệt vời! Không có việc tồn đọng</strong>
                <p>Tất cả đề nghị mua sắm đã có đủ báo giá hoặc đang được tiến hành xử lý.</p>
              </div>
            )
          ) : priorityManagerApprovals.length ? (
            <div className="dashboard-tasks-list">
              {priorityManagerApprovals.map((req) => (
                <div key={req.id} className="dashboard-task-item">
                  <div className="dashboard-task-info">
                    <div className="dashboard-task-title">
                      <Link to={`/purchase-requests/${req.id}/comparison`} className="request-link">
                        {req.code}
                      </Link>
                      <span>{req.category}</span>
                      <span className="dashboard-task-badge violet">Chờ duyệt</span>
                    </div>
                    <div className="dashboard-task-meta">
                      <span>Người yêu cầu: <strong>{req.metadata?.requested_by || req.creator_name || "—"}</strong></span>
                      <span>Dự toán: <strong>{formatBudget(req.estimated_budget)}</strong></span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="dashboard-task-action-btn primary"
                    onClick={() => navigate(`/purchase-requests/${req.id}/comparison`)}
                  >
                    Xem & Phê duyệt →
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="dashboard-empty-state">
              <div className="card-icon"><Icon name="check" /></div>
              <strong>Tất cả hồ sơ đã được xử lý</strong>
              <p>Hiện không có đề nghị nào đang chờ phê duyệt.</p>
            </div>
          )}
        </article>

        <article className="dashboard-card cost-card">
          <div className="card-heading">
            <div>
              <h3>{employee ? "Ngân sách dự kiến" : "Giá trị chờ phê duyệt"}</h3>
              <p>Tổng ngân sách của các đề nghị đang hiển thị</p>
            </div>
          </div>
          <strong className="dashboard-amount">{compactBudget(totalBudget)}</strong>
          <div className="status-bars">
            {statuses.map(([label, value, color]) => (
              <div key={label}>
                <span>{label}</span>
                <i>
                  <b
                    style={{
                      width: `${currentRequests.length ? Math.max(8, Math.round((value / currentRequests.length) * 100)) : 8}%`,
                      background: color,
                    }}
                  />
                </i>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </article>
      </section>
    </section>
  );
}

export function RequestListPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { requests, loading, error, reload } = useRequests();
  const paramStatus = searchParams.get("status");
  const [status, setStatus] = useState(() => paramStatus ?? (session?.user.role === "manager" ? "pending_approval" : ""));

  useEffect(() => {
    if (paramStatus !== null) {
      setStatus(paramStatus);
      setPage(1);
    }
  }, [paramStatus]);
  const [query, setQuery] = useState("");
  const [timeFilter, setTimeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [actionError, setActionError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<PurchaseRequest | null>(null);
  const [proposalInfo, setProposalInfo] = useState<Record<string, { vendor: string; amount: number }>>({});
  const employee = session?.user.role === "procurement";
  const pendingCount = requests.filter((request) => request.status === "pending_approval").length;

  useEffect(() => {
    if (employee || !session || !requests.length) return;
    let active = true;
    void Promise.allSettled(requests.map(async (request) => {
      const result = await apiRequest<JsonObject>(`/prs/${encodeURIComponent(request.id)}/analysis`, session);
      const selectedId = String(result.review?.preferred_supplier_id || result.decision_proposal?.preferred_supplier_id || "");
      const total = (result.tco_results || []).find((row: JsonObject) => row.supplier_id === selectedId);
      return [request.id, { vendor: result.supplier_names?.[selectedId] || "—", amount: Number(total?.total_tco || 0) }] as const;
    })).then((results) => {
      if (!active) return;
      setProposalInfo(Object.fromEntries(results.filter((result): result is PromiseFulfilledResult<readonly [string, { vendor: string; amount: number }]> => result.status === "fulfilled").map((result) => result.value)));
    });
    return () => { active = false; };
  }, [employee, requests, session]);

  const filtered = useMemo(() => requests.filter((request) => {
    if (status && request.status !== status) return false;
    if (!employee && !status && !["pending_approval", "approved", "rejected"].includes(request.status)) return false;
    if (query.trim() && ![request.code, request.category, request.creator_name].some((value) => String(value || "").toLocaleLowerCase("vi-VN").includes(query.trim().toLocaleLowerCase("vi-VN")))) return false;
    if (timeFilter && Date.now() - new Date(request.created_at).getTime() > Number(timeFilter) * 86400000) return false;
    return true;
  }), [requests, status, query, timeFilter, employee]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const managerTabs: Array<[string, string]> = [["pending_approval", `Chờ phê duyệt (${pendingCount})`], ["approved", "Đã duyệt"], ["rejected", "Đã từ chối"], ["", "Tất cả"]];
  const employeeTabs = [["", "Tất cả"], ...Object.entries(statusLabels)];

  const [printTarget, setPrintTarget] = useState<PrintTargetState | null>(null);

  const handlePrint = async (type: "pr" | "summary" | "proposal", request: PurchaseRequest) => {
    if (!session) return;
    setPrintTarget({ type, pr: request, loading: true });
    try {
      if (type === "pr") {
        const full = await apiRequest<PurchaseRequest>(`/prs/${encodeURIComponent(request.id)}`, session);
        setPrintTarget({ type, pr: request, fullPr: full, loading: false });
      } else {
        const [full, analysis, quotes] = await Promise.all([
          apiRequest<PurchaseRequest>(`/prs/${encodeURIComponent(request.id)}`, session),
          apiRequest<JsonObject>(`/prs/${encodeURIComponent(request.id)}/analysis`, session).catch(() => null),
          apiRequest<Quotation[]>(`/prs/${encodeURIComponent(request.id)}/quotations`, session).catch(() => []),
        ]);
        setPrintTarget({ type, pr: request, fullPr: full, analysis, quotations: quotes, loading: false });
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Không thể tải dữ liệu in.");
      setPrintTarget(null);
    }
  };

  if (loading) return <LoadingState label="Đang tải danh sách đề nghị…" />;
  if (error) return <ErrorState message={error} onRetry={() => void reload()} />;

  const remove = async () => {
    if (!session || !pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null); setActionError("");
    try { await apiRequest(`/prs/${encodeURIComponent(target.id)}`, session, { method: "DELETE" }); await reload(); }
    catch (exception) { setActionError(exception instanceof Error ? exception.message : "Không thể xóa đề nghị."); }
  };

  return <section className={`request-list-view ${employee ? "" : "manager-list-view"}`}>
    <div className="manager-tabs" role="tablist" aria-label="Trạng thái đề nghị">{(employee ? employeeTabs : managerTabs).map(([value, label]) => <button role="tab" aria-selected={status === value} key={value} className={status === value ? "active" : ""} onClick={() => { setStatus(value); setPage(1); }}>{label}</button>)}</div>
    <section className="request-controls"><label className="request-search"><span><Icon name="search" /></span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Tìm kiếm mã, tên đề nghị..." /></label>
      {!employee && <div className="manager-filters" role="group" aria-label="Lọc theo thời gian">{[["3", "3 ngày trước"], ["7", "7 ngày trước"], ["30", "30 ngày trước"]].map(([days, label]) => <button type="button" key={days} className={timeFilter === days ? "active" : ""} aria-pressed={timeFilter === days} onClick={() => { setTimeFilter((current) => current === days ? "" : days); setPage(1); }}>{label}</button>)}</div>}
    </section>
    <p className="error workspace-action-error" role="alert">{actionError}</p>
    <div className="requests-table-wrap"><table className="requests-table"><thead>{employee ? <tr><th>Đề nghị mua</th><th>Trạng thái</th><th>Ngân sách dự kiến</th><th>Hạn giao</th><th>Ngày tạo</th></tr> : <tr><th>Đề nghị mua</th><th>Người yêu cầu</th><th>Nhà cung cấp đề xuất</th><th>Ngân sách / Đề xuất</th><th>Ngày tạo &amp; Trạng thái</th></tr>}</thead><tbody>{rows.length ? rows.map((request) => {
      const detail = employee ? `/purchase-requests/${request.id}/workflow/1` : `/purchase-requests/${request.id}/comparison`;
      const edit = `/purchase-requests/${request.id}/workflow/1`;
      const canDelete = employee && !["pending_approval", "approved"].includes(request.status);
      const canPrintPr = Boolean(request.status !== "draft" || (request.items && request.items.length > 0) || Number(request.estimated_budget) > 0);
      const canPrintSummary = Boolean(
        ["comparing", "awaiting_buyer_review", "pending_manager_approval", "pending_approval", "approved", "rejected", "closed"].includes(request.status) ||
        (request.quotation_count !== undefined && request.quotation_count >= 2)
      );
      const canPrintProposal = Boolean(
        ["awaiting_buyer_review", "pending_manager_approval", "pending_approval", "approved", "rejected", "closed"].includes(request.status)
      );

      if (!employee) {
        const proposalAmount = proposalInfo[request.id]?.amount || 0;
        const budgetAmount = Number(request.estimated_budget) || 0;
        const hasProposal = proposalAmount > 0;
        const variancePct = hasProposal && budgetAmount > 0 ? ((proposalAmount / budgetAmount - 1) * 100) : null;
        const variancePositive = variancePct !== null && variancePct > 0;
        return (
          <tr
            key={request.id}
            className="request-row-interactive manager-row"
            onClick={() => navigate(detail)}
          >
            <td>
              <Link className="request-link" to={detail} onClick={(e) => e.stopPropagation()}>
                <strong>{request.code}</strong>
                <span>{request.category}</span>
              </Link>
            </td>
            <td>
              <span className="manager-requester">{request.metadata?.requested_by || request.creator_name || "—"}</span>
            </td>
            <td>
              <span className="manager-vendor-name">
                {proposalInfo[request.id]?.vendor || <span className="manager-vendor-loading">Đang tải…</span>}
              </span>
            </td>
            <td>
              <div className="manager-budget-cell">
                <strong>{formatBudget(hasProposal ? proposalAmount : budgetAmount)}</strong>
                {hasProposal && budgetAmount > 0 && variancePct !== null && (
                  <span className={`manager-variance-pill ${variancePositive ? "over" : "under"}`}>
                    {variancePositive ? "+" : ""}{variancePct.toFixed(1)}% so DT
                  </span>
                )}
                {!hasProposal && <small className="manager-budget-label">Dự toán</small>}
              </div>
            </td>
            <td>
              <div className="manager-date-status">
                <span className="manager-date">{new Date(request.created_at).toLocaleDateString("vi-VN")}</span>
                <StatusPill status={request.status} />
              </div>
            </td>
          </tr>
        );
      }

      return <tr key={request.id} className="request-row-interactive" onClick={() => navigate(edit)}>
        <td><Link className="request-link" to={edit} onClick={(e) => e.stopPropagation()}><strong>{request.code}</strong><span>{request.category}</span></Link></td>
        <td><StatusPill status={request.status} /></td>
        <td>{formatBudget(request.estimated_budget)}</td>
        <td>{formatDate(request.delivery_due_date)}</td>
        <td className="request-date-cell">
          <span>{new Date(request.created_at).toLocaleDateString("vi-VN")}</span>
          <div className="row-hover-actions" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className={`row-action-btn ${canPrintPr ? "" : "disabled"}`}
              disabled={!canPrintPr}
              title={canPrintPr ? "In đề nghị mua sắm (PDF)" : "PR chưa hoàn thành bước 1"}
              aria-label={canPrintPr ? "In đề nghị mua sắm (PDF)" : "PR chưa hoàn thành bước 1"}
              onClick={() => void handlePrint("pr", request)}
            >
              <FileText aria-hidden="true" />
            </button>
            <button
              type="button"
              className={`row-action-btn ${canPrintSummary ? "" : "disabled"}`}
              disabled={!canPrintSummary}
              title={canPrintSummary ? "In bảng tổng hợp báo giá (PDF)" : "Chưa hoàn thành bước tổng hợp báo giá (Bước 4)"}
              aria-label={canPrintSummary ? "In bảng tổng hợp báo giá (PDF)" : "Chưa hoàn thành bước tổng hợp báo giá (Bước 4)"}
              onClick={() => void handlePrint("summary", request)}
            >
              <FileSpreadsheet aria-hidden="true" />
            </button>
            <button
              type="button"
              className={`row-action-btn ${canPrintProposal ? "" : "disabled"}`}
              disabled={!canPrintProposal}
              title={canPrintProposal ? "In tờ trình đề xuất mua sắm (PDF)" : "Chưa hoàn thành bước đề xuất phương án (Bước 5)"}
              aria-label={canPrintProposal ? "In tờ trình đề xuất mua sắm (PDF)" : "Chưa hoàn thành bước đề xuất phương án (Bước 5)"}
              onClick={() => void handlePrint("proposal", request)}
            >
              <FileCheck aria-hidden="true" />
            </button>
            <button
              type="button"
              className={`row-action-btn danger ${canDelete ? "" : "disabled"}`}
              disabled={!canDelete}
              title={canDelete ? "Xóa đề nghị" : "Không thể xóa ở trạng thái này"}
              aria-label={canDelete ? "Xóa đề nghị" : "Không thể xóa ở trạng thái này"}
              onClick={() => setPendingDelete(request)}
            >
              <Trash2 aria-hidden="true" />
            </button>
          </div>
        </td>
      </tr>;
    }) : <tr><td className="request-empty" colSpan={5}><div><div className="card-icon"><Icon name="search" /></div><strong>Không tìm thấy đề nghị phù hợp</strong><p>Thử đổi từ khóa hoặc bộ lọc trạng thái.</p></div></td></tr>}</tbody></table></div>
    <nav className="pagination"><p className="request-result-count">Hiển thị <strong>{filtered.length ? (current - 1) * PAGE_SIZE + 1 : 0}–{Math.min(current * PAGE_SIZE, filtered.length)}</strong> trên <strong>{filtered.length}</strong> đề nghị</p><button className="pagination-button pagination-icon" disabled={current === 1} onClick={() => setPage(current - 1)}><Icon name="arrow-left" /></button><label className="pagination-jump"><input className="pagination-input" type="number" min="1" max={pages} value={current} onChange={(event) => setPage(Number(event.target.value) || 1)} /> / {pages}</label><button className="pagination-button pagination-icon" disabled={current === pages} onClick={() => setPage(current + 1)}><Icon name="arrow-right" /></button></nav>
    {pendingDelete && <ConfirmDialog title={`Xóa ${pendingDelete.code}?`} description="Toàn bộ báo giá và file gốc của đề nghị này cũng sẽ bị xóa vĩnh viễn." onCancel={() => setPendingDelete(null)} onConfirm={() => void remove()} />}
    {printTarget && createPortal(
      <PrintPreviewModal target={printTarget} onClose={() => setPrintTarget(null)} />,
      document.body,
    )}
  </section>;
}

interface PrintTargetState {
  type: "pr" | "summary" | "proposal";
  pr: PurchaseRequest;
  fullPr?: PurchaseRequest;
  analysis?: JsonObject | null;
  quotations?: Quotation[];
  loading?: boolean;
}

function PrintPreviewModal({
  target,
  onClose,
}: {
  target: PrintTargetState;
  onClose: () => void;
}) {
  const { pr, fullPr, analysis, quotations, loading, type } = target;

  if (loading) {
    return (
      <div className="workflow-modal-backdrop modal-backdrop-print">
        <div className="workflow-modal" style={{ maxWidth: 360, textAlign: "center", padding: "30px 20px" }}>
          <LoadingState label="Đang chuẩn bị bản in PDF…" />
        </div>
      </div>
    );
  }

  const title =
    type === "pr"
      ? "Bản in Đề nghị mua sắm (PR)"
      : type === "summary"
      ? "Bản in Bảng tổng hợp báo giá"
      : "Bản in Tờ trình đề xuất mua sắm";

  const items = fullPr?.items || pr.items || [];
  const quotesList = quotations || [];
  const selectedSupplierId = String(
    analysis?.review?.preferred_supplier_id ||
    analysis?.decision_proposal?.preferred_supplier_id ||
    ""
  );
  const selectedQuote = quotesList.find((q) => q.supplier_id === selectedSupplierId) || quotesList[0];
  const selectedSupplierName =
    selectedQuote?.supplier_name ||
    analysis?.supplier_names?.[selectedSupplierId] ||
    "Nhà cung cấp đề xuất";
  const selectedTco = (analysis?.tco_results || []).find((r: JsonObject) => r.supplier_id === selectedSupplierId);
  const proposedAmount = Number(selectedTco?.total_tco || 0);
  const budget = Number(pr.estimated_budget || 0);
  const variance = proposedAmount - budget;

  return (
    <div
      className="workflow-modal-backdrop modal-backdrop-print"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="workflow-modal print-preview-modal" role="dialog" aria-modal="true">
        <div className="print-modal-header">
          <div className="print-modal-title">
            <Printer aria-hidden="true" />
            <div>
              <h3>{title}</h3>
              <p>{pr.code} · {pr.category}</p>
            </div>
          </div>
          <div className="print-modal-actions">
            <button type="button" className="inline-primary" onClick={() => window.print()}>
              <Printer aria-hidden="true" /> In / Lưu PDF
            </button>
            <button type="button" className="secondary" onClick={onClose}>
              Đóng
            </button>
          </div>
        </div>

        <div className="print-modal-body">
          <div className="print-modal-document">
            {type === "pr" && (
              <>
                <div className="print-doc-header">
                  <div className="print-doc-brand">
                    <h2>CÔNG TY TNHH DOTCOM</h2>
                    <p>Hệ thống Mua sắm Doanh nghiệp · Phiếu yêu cầu nội bộ</p>
                  </div>
                  <div className="print-doc-meta">
                    <div>Mã PR: <strong>{pr.code}</strong></div>
                    <div>Ngày lập: <b>{new Date(pr.created_at).toLocaleDateString("vi-VN")}</b></div>
                    <div>Trạng thái: <span>{statusLabels[pr.status] || pr.status}</span></div>
                  </div>
                </div>

                <div className="print-doc-title">
                  <h1>PHIẾU ĐỀ NGHỊ MUA SẮM</h1>
                  <p>PURCHASE REQUEST</p>
                </div>

                <div className="print-doc-grid">
                  <div>Tên đề nghị: <strong>{pr.category}</strong></div>
                  <div>Người lập: <strong>{fullPr?.metadata?.requested_by || pr.metadata?.requested_by || pr.creator_name || "—"}</strong></div>
                  <div>Bộ phận yêu cầu: <strong>{fullPr?.metadata?.department || pr.metadata?.department || "Bộ phận Mua sắm"}</strong></div>
                  <div>Hạn giao hàng: <strong>{formatDate(pr.delivery_due_date)}</strong></div>
                  <div>Ngân sách dự kiến: <strong>{formatBudget(pr.estimated_budget)}</strong></div>
                  <div>Mục đích: <span>{fullPr?.metadata?.purpose || pr.metadata?.purpose || "Theo kế hoạch hoạt động"}</span></div>
                </div>

                <h4>DANH MỤC HÀNG HÓA / DỊCH VỤ YÊU CẦU</h4>
                <table className="print-doc-table">
                  <thead>
                    <tr>
                      <th className="text-center" style={{ width: 50 }}>STT</th>
                      <th>Tên sản phẩm / Quy cách kỹ thuật</th>
                      <th className="text-center" style={{ width: 80 }}>Số lượng</th>
                      <th className="text-center" style={{ width: 90 }}>Đơn vị tính</th>
                      <th>Ghi chú</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.length ? (
                      items.map((item, idx) => (
                        <tr key={item.id || item.item_id || idx}>
                          <td className="text-center">{idx + 1}</td>
                          <td><strong>{item.product_name}</strong>{item.product_code && <><br /><small style={{ color: "#64748b" }}>{item.product_code}</small></>}</td>
                          <td className="text-center">{item.quantity}</td>
                          <td className="text-center">{item.unit || "Cái"}</td>
                          <td>{item.notes || "—"}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="text-center">1</td>
                        <td><strong>{pr.category}</strong></td>
                        <td className="text-center">{pr.requested_quantity || pr.quantity || 1}</td>
                        <td className="text-center">{pr.requested_uom || "Lô"}</td>
                        <td>Theo danh mục đính kèm</td>
                      </tr>
                    )}
                  </tbody>
                </table>

                <div className="print-doc-signatures">
                  <div className="print-doc-sig-col">
                    <span>Người lập đề xuất</span>
                    <div className="print-doc-sig-space" />
                    <b>{fullPr?.metadata?.requested_by || pr.creator_name || "Nhân viên mua sắm"}</b>
                  </div>
                  <div className="print-doc-sig-col">
                    <span>Phụ trách bộ phận</span>
                    <div className="print-doc-sig-space" />
                    <b>Trưởng phòng</b>
                  </div>
                  <div className="print-doc-sig-col">
                    <span>Ban Giám đốc duyệt</span>
                    <div className="print-doc-sig-space">
                      {["approved", "pending_approval"].includes(pr.status) && (
                        <span className="print-doc-stamp">{pr.status === "approved" ? "✓ ĐÃ PHÊ DUYỆT" : "ĐANG CHỜ DUYỆT"}</span>
                      )}
                    </div>
                    <b>Đại diện Ban Giám đốc</b>
                  </div>
                </div>
              </>
            )}

            {type === "summary" && (
              <>
                <div className="print-doc-header">
                  <div className="print-doc-brand">
                    <h2>CÔNG TY TNHH DOTCOM</h2>
                    <p>Phòng Mua sắm &amp; Quản lý Tài sản · Bảng tổng hợp đối soát</p>
                  </div>
                  <div className="print-doc-meta">
                    <div>Tham chiếu PR: <strong>{pr.code}</strong></div>
                    <div>Ngày lập: <b>{new Date().toLocaleDateString("vi-VN")}</b></div>
                    <div>Số báo giá đối chiếu: <b>{quotesList.length} báo giá</b></div>
                  </div>
                </div>

                <div className="print-doc-title">
                  <h1>BẢNG TỔNG HỢP SO SÁNH BÁO GIÁ</h1>
                  <p>{pr.category}</p>
                </div>

                <div className="print-doc-grid">
                  <div>Mã hồ sơ: <strong>{pr.code}</strong></div>
                  <div>Dự toán ngân sách: <strong>{formatBudget(pr.estimated_budget)}</strong></div>
                  <div>Hạn giao hàng yêu cầu: <strong>{formatDate(pr.delivery_due_date)}</strong></div>
                  <div>Số lượng NCC tham gia: <strong>{quotesList.length} đơn vị</strong></div>
                </div>

                <h4>TỔNG HỢP CÁC PHƯƠNG ÁN BÁO GIÁ</h4>
                <table className="print-doc-table">
                  <thead>
                    <tr>
                      <th className="text-center" style={{ width: 40 }}>STT</th>
                      <th>Nhà cung cấp</th>
                      <th>File báo giá</th>
                      <th className="text-right">Tổng chi phí (TCO)</th>
                      <th>Thời gian giao</th>
                      <th>Bảo hành</th>
                      <th>Điều khoản thanh toán</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quotesList.length ? (
                      quotesList.map((q, idx) => {
                        const tco = (analysis?.tco_results || []).find((r: JsonObject) => r.supplier_id === q.supplier_id);
                        const total = tco ? Number(tco.total_tco) : q.items.reduce((acc, it) => acc + (it.line_total || it.quantity * it.unit_price), 0);
                        const isPref = q.supplier_id === selectedSupplierId;
                        return (
                          <tr key={q.id || idx} style={isPref ? { background: "#f0fdf4" } : {}}>
                            <td className="text-center">{idx + 1}</td>
                            <td><strong>{q.supplier_name}</strong>{isPref && <span style={{ marginLeft: 6, color: "#16a34a", fontSize: 11, fontWeight: 700 }}>(Khuyên dùng)</span>}</td>
                            <td><small style={{ color: "#64748b" }}>{q.source_filename}</small></td>
                            <td className="text-right"><strong>{formatComparisonMoney(total)} VNĐ</strong></td>
                            <td>{q.delivery_time || (q.lead_time_days ? `${q.lead_time_days} ngày` : "—")}</td>
                            <td>{q.warranty || (q.warranty_months ? `${q.warranty_months} tháng` : "—")}</td>
                            <td>{q.payment_terms || "Theo hợp đồng"}</td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={7} className="text-center" style={{ padding: 20 }}>Chưa có dữ liệu báo giá đối soát.</td>
                      </tr>
                    )}
                  </tbody>
                </table>

                <div className="print-doc-signatures">
                  <div className="print-doc-sig-col">
                    <span>Nhân viên tổng hợp đối soát</span>
                    <div className="print-doc-sig-space" />
                    <b>{pr.creator_name || "Nhân viên Mua sắm"}</b>
                  </div>
                  <div className="print-doc-sig-col">
                    <span>Trưởng phòng Mua sắm</span>
                    <div className="print-doc-sig-space" />
                    <b>Xác nhận đối soát</b>
                  </div>
                </div>
              </>
            )}

            {type === "proposal" && (
              <>
                <div className="print-doc-header">
                  <div className="print-doc-brand">
                    <h2>CÔNG TY TNHH DOTCOM</h2>
                    <p>Phòng Mua sắm &amp; Quản lý Tài sản · Tờ trình thẩm định phương án</p>
                  </div>
                  <div className="print-doc-meta">
                    <div>Số PR: <strong>{pr.code}</strong></div>
                    <div>Ngày lập tờ trình: <b>{new Date().toLocaleDateString("vi-VN")}</b></div>
                    <div>Trạng thái: <span>{statusLabels[pr.status] || pr.status}</span></div>
                  </div>
                </div>

                <div className="print-doc-title">
                  <h1>TỜ TRÌNH ĐỀ XUẤT LỰA CHỌN PHƯƠNG ÁN MUA SẮM</h1>
                  <p>{pr.category}</p>
                </div>

                <div className="print-doc-grid">
                  <div>Nhà cung cấp đề xuất: <strong style={{ color: "#0284c7" }}>{selectedSupplierName}</strong></div>
                  <div>Giá trị đề xuất: <strong>{formatBudget(proposedAmount || pr.estimated_budget)}</strong></div>
                  <div>Dự toán được duyệt: <strong>{formatBudget(pr.estimated_budget)}</strong></div>
                  <div>Chênh lệch ngân sách: <strong>{proposedAmount > 0 && budget > 0 ? `${variance > 0 ? "+" : ""}${formatBudget(variance)} (${(variance / budget * 100).toFixed(1)}%)` : "—"}</strong></div>
                  <div>Thời gian giao hàng: <strong>{selectedQuote?.delivery_time || "Theo thỏa thuận"}</strong></div>
                  <div>Bảo hành: <strong>{selectedQuote?.warranty || "Theo tiêu chuẩn NSX"}</strong></div>
                </div>

                <h4>CĂN CỨ VÀ ĐÁNH GIÁ TỪ HỆ THỐNG AGENT</h4>
                <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "14px 16px", marginBottom: 24, fontStyle: "italic", color: "#334155" }}>
                  {analysis?.review?.rationale || analysis?.decision_proposal?.rationale || "Đề xuất phương án tối ưu dựa trên phân tích tổng chi phí sở hữu (TCO), đối chiếu các điều khoản thương mại, thời gian giao hàng và chính sách bảo hành từ các báo giá đã thẩm định."}
                </div>

                {analysis?.manager_note && (
                  <>
                    <h4>Ý KIẾN CHỈ ĐẠO CỦA CẤP PHÊ DUYỆT</h4>
                    <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "12px 16px", marginBottom: 24, color: "#166534" }}>
                      {analysis.manager_note}
                    </div>
                  </>
                )}

                <div className="print-doc-signatures">
                  <div className="print-doc-sig-col">
                    <span>Đại diện Mua sắm</span>
                    <div className="print-doc-sig-space" />
                    <b>{pr.creator_name || "Người lập đề xuất"}</b>
                  </div>
                  <div className="print-doc-sig-col">
                    <span>Quản lý Phê duyệt</span>
                    <div className="print-doc-sig-space">
                      {pr.status === "approved" && (
                        <span className="print-doc-stamp">✓ ĐÃ PHÊ DUYỆT</span>
                      )}
                    </div>
                    <b>{pr.metadata?.requested_by || "Trưởng phòng Phê duyệt"}</b>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
