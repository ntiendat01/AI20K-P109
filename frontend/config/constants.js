export const API_ROOT = "/api/v1";
export const storageKey = "procura_demo_session";
export const flashKey = "procura_ui_flash";
// Browser-side polling limits. Keep these explicit so product can tune the
// experience without coupling the static frontend to server configuration.
export const ANALYSIS_POLL_INTERVAL_MS = 2_000;
export const ANALYSIS_POLL_MAX_WAIT_MS = 6 * 60 * 1_000;

export const roleConfig = {
  procurement: {
    label: "Nhân viên mua sắm",
    home: "workspace",
    nav: [
      ["workspace", "workspace", "Không gian làm việc"],
      ["new-pr", "request", "Tạo đề nghị mua"],
      ["quotations", "quotations", "Báo giá & so sánh"],
    ],
  },
  manager: {
    label: "Quản lý duyệt",
    home: "approvals",
    nav: [
      ["approvals", "approvals", "PR chờ duyệt"],
      ["history", "history", "Lịch sử phê duyệt"],
    ],
  },
};

export const statusLabels = {
  draft: "Nháp",
  awaiting_quotation: "Chờ báo giá",
  comparing: "Đang so sánh",
  pending_approval: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
};
